"""Access Control Views (Phase 2E Stages 4 & 5).

Provides:
- Platform Owner APIs (Stage 4):
  1. GET   /api/v1/organizations/{organization_id}/console-policies/
  2. PATCH /api/v1/organizations/{organization_id}/console-policies/{module_key}/
  3. GET   /api/v1/organizations/{organization_id}/permission-ceilings/
  4. PATCH /api/v1/organizations/{organization_id}/permission-ceilings/{permission_key}/
- Tenant Admin APIs (Stage 5):
  1. GET   /api/v1/tenant/access-catalog/
  2. GET   /api/v1/tenant/roles/
  3. POST  /api/v1/tenant/roles/
  4. GET   /api/v1/tenant/roles/{role_id}/
  5. PATCH /api/v1/tenant/roles/{role_id}/
  6. POST  /api/v1/tenant/roles/{role_id}/retire/
  7. GET   /api/v1/tenant/admin-memberships/
  8. PATCH /api/v1/tenant/admin-memberships/{membership_id}/role/
"""

import uuid
from typing import Any

from django.db import transaction
from django.db.models import Case, Count, IntegerField, Prefetch, Q, Value, When
from rest_framework import exceptions, status
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.access_control.constants import CONTEXT_TENANT, PREDEFINED_SUPPORT_ROLES
from apps.access_control.models import (
    AccessPermission,
    ConsoleModule,
    OrganizationConsoleModulePolicy,
    OrganizationPermissionCeiling,
    PlatformRoleAssignment,
    Role,
    RolePermission,
    RoleStatus,
)
from apps.access_control.permissions import HasConsoleModule, HasConsolePermission
from rest_framework.permissions import BasePermission
from apps.access_control.serializers import (
    AdministrativeMembershipSerializer,
    ConsoleModulePolicyItemSerializer,
    ConsoleModulePolicyUpdateSerializer,
    MembershipRoleAssignSerializer,
    PermissionCeilingItemSerializer,
    PermissionCeilingUpdateSerializer,
    PlatformSupportOperatorAssignSerializer,
    PlatformSupportOperatorSerializer,
    RoleCreateSerializer,
    RoleSerializer,
    RoleUpdateSerializer,
    TenantAccessCatalogResponseSerializer,
)
from apps.auditlog.models import AuditAction, AuditOperationSource, AuditTargetType
from apps.auditlog.services import record_audit_event
from apps.identity.models import PlatformUser, UserStatus

from apps.access_control.services.assignment_services import assign_membership_role
from apps.access_control.services.ceiling_services import set_permission_ceiling
from apps.access_control.services.evaluation import get_request_evaluation
from apps.access_control.services.guards import (
    AccessControlValidationError,
    InsufficientPrivilegesError,
    LastAdminProtectionError,
    ModuleCannotBeDisabledError,
    ModuleNotFoundError,
    OrganizationNotActiveError,
    PermissionNotFoundError,
    PermissionOutsideCeilingError,
    RoleAlreadyExistsError,
    RoleInUseError,
    RoleNotAssignableToMemberError,
    RoleNotFoundError,
    RoleRetiredError,
    SystemRoleImmutableError,
)
from apps.access_control.services.policy_services import set_console_module_policy
from apps.access_control.services.role_services import create_role, retire_role, update_role
from apps.identity.authentication import EnforcedSessionAuthentication
from apps.identity.permissions import IsPlatformOwnerContext
from apps.organizations.models import (
    MembershipStatus,
    MembershipType,
    Organization,
    OrganizationMembership,
    OrganizationStatus,
)


def _get_target_organization(organization_id: Any) -> Organization:
    """Validate and resolve target organization by UUID for Platform Owner endpoints.

    Raises 404 with ORGANIZATION_NOT_FOUND if invalid UUID or organization not found.
    """
    try:
        clean_id = uuid.UUID(str(organization_id))
    except (ValueError, TypeError):
        raise exceptions.NotFound(
            {"code": "ORGANIZATION_NOT_FOUND", "detail": f"Organization '{organization_id}' not found."}
        )

    org = Organization.objects.filter(id=clean_id).first()
    if not org:
        raise exceptions.NotFound(
            {"code": "ORGANIZATION_NOT_FOUND", "detail": f"Organization '{organization_id}' not found."}
        )
    return org


def get_tenant_organization_from_request(request: Any) -> Organization:
    """Resolve and return active tenant organization from session context."""
    session = getattr(request, "session", None)
    if not session:
        raise exceptions.PermissionDenied(
            {"code": "TENANT_CONTEXT_REQUIRED", "detail": "Tenant context required."}
        )
    org_id = session.get("tenant_organization_id")
    if not org_id:
        raise exceptions.PermissionDenied(
            {"code": "TENANT_CONTEXT_REQUIRED", "detail": "Tenant context required."}
        )
    try:
        clean_id = uuid.UUID(str(org_id))
    except (ValueError, TypeError):
        raise exceptions.PermissionDenied(
            {"code": "TENANT_CONTEXT_REQUIRED", "detail": "Invalid tenant context."}
        )
    org = Organization.objects.filter(id=clean_id, status=OrganizationStatus.ACTIVE).first()
    if not org:
        raise exceptions.PermissionDenied(
            {"code": "ORGANIZATION_NOT_ACTIVE", "detail": "Organization not found or inactive."}
        )
    return org


def _format_validation_error(serializer: Any) -> Response:
    """Format serializer validation errors to standard project error contract."""
    first_err = next(iter(serializer.errors.values()))
    err_msg = str(first_err[0]) if isinstance(first_err, list) and first_err else str(first_err)
    return Response(
        {
            "code": "VALIDATION_ERROR",
            "detail": err_msg,
            "errors": serializer.errors,
        },
        status=status.HTTP_400_BAD_REQUEST,
    )


class TenantAccessControlPagination(PageNumberPagination):
    """Standard pagination for tenant access control listings."""

    page_size = 10
    page_size_query_param = "page_size"
    max_page_size = 100


# =========================================================================
# Stage 4: Platform Owner Views
# =========================================================================

class OrganizationConsolePolicyListView(APIView):
    """List tenant console module policies for an organization (Platform Owner only)."""

    authentication_classes = [EnforcedSessionAuthentication]
    permission_classes = [IsPlatformOwnerContext]

    def get(self, request, organization_id: uuid.UUID, *args, **kwargs) -> Response:
        org = _get_target_organization(organization_id)

        modules = ConsoleModule.objects.filter(target_context="tenant").order_by("sort_order", "key")
        policies = {
            p.console_module_id: p
            for p in OrganizationConsoleModulePolicy.objects.filter(organization=org)
        }

        items = []
        for mod in modules:
            policy = policies.get(mod.key)
            if mod.is_core:
                is_enabled = True
                can_disable = False
            else:
                is_enabled = policy.is_enabled if policy else False
                can_disable = True

            items.append({
                "module_key": mod.key,
                "display_name": mod.display_name,
                "description": mod.description,
                "is_core": mod.is_core,
                "is_active": mod.is_active,
                "is_enabled": is_enabled,
                "can_disable": can_disable,
                "updated_at": policy.updated_at if policy else None,
            })

        serializer = ConsoleModulePolicyItemSerializer(items, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class OrganizationConsolePolicyDetailView(APIView):
    """Update tenant console module policy for an organization (Platform Owner only)."""

    authentication_classes = [EnforcedSessionAuthentication]
    permission_classes = [IsPlatformOwnerContext]

    def patch(self, request, organization_id: uuid.UUID, module_key: str, *args, **kwargs) -> Response:
        org = _get_target_organization(organization_id)

        serializer = ConsoleModulePolicyUpdateSerializer(data=request.data)
        if not serializer.is_valid():
            return _format_validation_error(serializer)

        correlation_id = getattr(request, "correlation_id", None)

        try:
            policy = set_console_module_policy(
                actor=request.user,
                organization_id=org.id,
                module_key=module_key,
                is_enabled=serializer.validated_data["is_enabled"],
                correlation_id=correlation_id,
            )
        except ModuleNotFoundError as e:
            return Response({"code": e.code, "detail": e.message}, status=status.HTTP_404_NOT_FOUND)
        except ModuleCannotBeDisabledError as e:
            return Response({"code": e.code, "detail": e.message}, status=status.HTTP_400_BAD_REQUEST)
        except OrganizationNotActiveError as e:
            return Response({"code": e.code, "detail": e.message}, status=status.HTTP_403_FORBIDDEN)
        except AccessControlValidationError as e:
            return Response({"code": e.code, "detail": e.message}, status=status.HTTP_400_BAD_REQUEST)
        except InsufficientPrivilegesError as e:
            return Response({"code": e.code, "detail": e.message}, status=status.HTTP_403_FORBIDDEN)

        mod = ConsoleModule.objects.get(key=module_key)
        item = {
            "module_key": mod.key,
            "display_name": mod.display_name,
            "description": mod.description,
            "is_core": mod.is_core,
            "is_active": mod.is_active,
            "is_enabled": policy.is_enabled,
            "can_disable": not mod.is_core,
            "updated_at": policy.updated_at,
        }
        return Response(ConsoleModulePolicyItemSerializer(item).data, status=status.HTTP_200_OK)


class OrganizationPermissionCeilingListView(APIView):
    """List permission ceilings for an organization (Platform Owner only)."""

    authentication_classes = [EnforcedSessionAuthentication]
    permission_classes = [IsPlatformOwnerContext]

    def get(self, request, organization_id: uuid.UUID, *args, **kwargs) -> Response:
        org = _get_target_organization(organization_id)

        permissions = (
            AccessPermission.objects.filter(
                console_module__target_context="tenant",
                is_active=True,
            )
            .select_related("console_module")
            .order_by("sort_order", "key")
        )
        ceilings = {
            c.permission_id: c
            for c in OrganizationPermissionCeiling.objects.filter(organization=org)
        }

        items = []
        for perm in permissions:
            ceiling = ceilings.get(perm.key)
            items.append({
                "permission_key": perm.key,
                "display_name": perm.display_name,
                "description": perm.description,
                "category": perm.category,
                "console_module": perm.console_module_id,
                "is_active": perm.is_active,
                "is_allowed": ceiling.is_allowed if ceiling else False,
                "updated_at": ceiling.updated_at if ceiling else None,
            })

        serializer = PermissionCeilingItemSerializer(items, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class OrganizationPermissionCeilingDetailView(APIView):
    """Update permission ceiling for an organization (Platform Owner only)."""

    authentication_classes = [EnforcedSessionAuthentication]
    permission_classes = [IsPlatformOwnerContext]

    def patch(self, request, organization_id: uuid.UUID, permission_key: str, *args, **kwargs) -> Response:
        org = _get_target_organization(organization_id)

        serializer = PermissionCeilingUpdateSerializer(data=request.data)
        if not serializer.is_valid():
            return _format_validation_error(serializer)

        correlation_id = getattr(request, "correlation_id", None)

        try:
            ceiling = set_permission_ceiling(
                actor=request.user,
                organization_id=org.id,
                permission_key=permission_key,
                is_allowed=serializer.validated_data["is_allowed"],
                correlation_id=correlation_id,
            )
        except PermissionNotFoundError as e:
            return Response({"code": e.code, "detail": e.message}, status=status.HTTP_400_BAD_REQUEST)
        except AccessControlValidationError as e:
            return Response({"code": e.code, "detail": e.message}, status=status.HTTP_400_BAD_REQUEST)
        except OrganizationNotActiveError as e:
            return Response({"code": e.code, "detail": e.message}, status=status.HTTP_403_FORBIDDEN)
        except InsufficientPrivilegesError as e:
            return Response({"code": e.code, "detail": e.message}, status=status.HTTP_403_FORBIDDEN)

        perm = AccessPermission.objects.select_related("console_module").get(key=permission_key)
        item = {
            "permission_key": perm.key,
            "display_name": perm.display_name,
            "description": perm.description,
            "category": perm.category,
            "console_module": perm.console_module_id,
            "is_active": perm.is_active,
            "is_allowed": ceiling.is_allowed,
            "updated_at": ceiling.updated_at,
        }
        return Response(PermissionCeilingItemSerializer(item).data, status=status.HTTP_200_OK)


# =========================================================================
# Stage 5: Tenant Admin Views
# =========================================================================

class RequireTenantContext(BasePermission):
    """Enforce that the request has an active server-side tenant session context.

    Rejects unauthenticated requests with 401.
    Rejects requests without active tenant session context with 403 TENANT_CONTEXT_REQUIRED.
    """

    def has_permission(self, request, view) -> bool:
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            raise exceptions.NotAuthenticated()

        session = getattr(request, "session", None)
        if not session or session.get("active_context_type") != CONTEXT_TENANT:
            raise exceptions.PermissionDenied(
                {"code": "TENANT_CONTEXT_REQUIRED", "detail": "Tenant context required."}
            )
        return True


class TenantAccessCatalogView(APIView):
    """Catalog of modules and permissions grantable by the current Tenant Admin."""

    authentication_classes = [EnforcedSessionAuthentication]
    permission_classes = [RequireTenantContext, HasConsoleModule, HasConsolePermission]
    required_console_module = "tenant_roles"
    required_console_permission = "roles.view"

    def get(self, request, *args, **kwargs) -> Response:
        org = get_tenant_organization_from_request(request)
        eval_result = get_request_evaluation(request, request.user, CONTEXT_TENANT, org.id)
        actor_effective_perms = set(eval_result.effective_permissions)

        enabled_module_keys = set(
            OrganizationConsoleModulePolicy.objects.filter(
                organization=org,
                is_enabled=True,
            ).values_list("console_module_id", flat=True)
        )
        allowed_ceiling_keys = set(
            OrganizationPermissionCeiling.objects.filter(
                organization=org,
                is_allowed=True,
            ).values_list("permission_id", flat=True)
        )

        grantable_keys = allowed_ceiling_keys.intersection(actor_effective_perms)

        grantable_permissions = (
            AccessPermission.objects.filter(
                key__in=grantable_keys,
                is_active=True,
                console_module__target_context="tenant",
                console_module__is_active=True,
                console_module_id__in=enabled_module_keys,
            )
            .order_by("sort_order", "key")
        )

        grantable_module_keys = set(grantable_permissions.values_list("console_module_id", flat=True))

        active_modules = (
            ConsoleModule.objects.filter(
                target_context="tenant",
                is_active=True,
                key__in=grantable_module_keys,
            )
            .order_by("sort_order", "key")
        )

        modules_data = [
            {
                "key": m.key,
                "display_name": m.display_name,
                "description": m.description,
            }
            for m in active_modules
        ]
        perms_data = [
            {
                "key": p.key,
                "display_name": p.display_name,
                "category": p.category,
                "console_module": p.console_module_id,
            }
            for p in grantable_permissions
        ]

        response_data = {
            "modules": modules_data,
            "permissions": perms_data,
        }
        serializer = TenantAccessCatalogResponseSerializer(response_data)
        return Response(serializer.data, status=status.HTTP_200_OK)


class TenantRoleListView(APIView):
    """List or create administrative roles for the active tenant organization."""

    authentication_classes = [EnforcedSessionAuthentication]
    permission_classes = [RequireTenantContext, HasConsoleModule, HasConsolePermission]
    required_console_module = "tenant_roles"
    pagination_class = TenantAccessControlPagination

    def get_required_console_permission(self) -> str:
        return "roles.manage" if self.request.method == "POST" else "roles.view"

    def get(self, request, *args, **kwargs) -> Response:
        org = get_tenant_organization_from_request(request)

        queryset = (
            Role.objects.filter(
                Q(is_system_role=True, organization__isnull=True)
                | Q(organization=org)
            )
            .exclude(code__in=PREDEFINED_SUPPORT_ROLES)
            .annotate(
                is_system_first=Case(
                    When(is_system_role=True, then=Value(0)),
                    default=Value(1),
                    output_field=IntegerField(),
                ),
                assigned_members_count=Count("memberships", distinct=True),
            )
            .prefetch_related(
                Prefetch(
                    "role_permissions",
                    queryset=RolePermission.objects.select_related("permission").order_by(
                        "permission__sort_order", "permission__key"
                    ),
                )
            )
            .order_by("is_system_first", "name", "code", "id")
        )

        paginator = self.pagination_class()
        page = paginator.paginate_queryset(queryset, request, view=self)
        serializer = RoleSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    def post(self, request, *args, **kwargs) -> Response:
        org = get_tenant_organization_from_request(request)

        serializer = RoleCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return _format_validation_error(serializer)

        correlation_id = getattr(request, "correlation_id", None)

        try:
            role = create_role(
                actor=request.user,
                organization_id=org.id,
                code=serializer.validated_data["code"],
                name=serializer.validated_data["name"],
                description=serializer.validated_data.get("description", ""),
                permission_keys=serializer.validated_data["permission_keys"],
                correlation_id=correlation_id,
            )
        except RoleAlreadyExistsError as e:
            return Response({"code": e.code, "detail": e.message}, status=status.HTTP_409_CONFLICT)
        except (PermissionNotFoundError, RoleNotFoundError) as e:
            return Response({"code": e.code, "detail": e.message}, status=status.HTTP_400_BAD_REQUEST)
        except (AccessControlValidationError, PermissionOutsideCeilingError) as e:
            return Response({"code": e.code, "detail": e.message}, status=status.HTTP_400_BAD_REQUEST)
        except InsufficientPrivilegesError as e:
            return Response({"code": e.code, "detail": e.message}, status=status.HTTP_403_FORBIDDEN)

        role_with_perms = (
            Role.objects.annotate(assigned_members_count=Count("memberships", distinct=True))
            .prefetch_related(
                Prefetch(
                    "role_permissions",
                    queryset=RolePermission.objects.select_related("permission").order_by(
                        "permission__sort_order", "permission__key"
                    ),
                )
            )
            .get(id=role.id)
        )
        return Response(RoleSerializer(role_with_perms).data, status=status.HTTP_201_CREATED)


class TenantRoleDetailView(APIView):
    """Retrieve or update an administrative role."""

    authentication_classes = [EnforcedSessionAuthentication]
    permission_classes = [RequireTenantContext, HasConsoleModule, HasConsolePermission]
    required_console_module = "tenant_roles"

    def get_required_console_permission(self) -> str:
        return "roles.manage" if self.request.method == "PATCH" else "roles.view"

    def _get_role(self, role_id: Any, org: Organization) -> Role:
        try:
            clean_id = uuid.UUID(str(role_id))
        except (ValueError, TypeError):
            raise exceptions.NotFound({"code": "ROLE_NOT_FOUND", "detail": "Role not found."})

        role = (
            Role.objects.filter(
                Q(is_system_role=True, organization__isnull=True)
                | Q(organization=org)
            )
            .exclude(code__in=PREDEFINED_SUPPORT_ROLES)
            .filter(id=clean_id)
            .annotate(assigned_members_count=Count("memberships", distinct=True))
            .prefetch_related(
                Prefetch(
                    "role_permissions",
                    queryset=RolePermission.objects.select_related("permission").order_by(
                        "permission__sort_order", "permission__key"
                    ),
                )
            )
            .first()
        )
        if not role:
            raise exceptions.NotFound({"code": "ROLE_NOT_FOUND", "detail": "Role not found."})
        return role

    def get(self, request, role_id: uuid.UUID, *args, **kwargs) -> Response:
        org = get_tenant_organization_from_request(request)
        role = self._get_role(role_id, org)
        return Response(RoleSerializer(role).data, status=status.HTTP_200_OK)

    def patch(self, request, role_id: uuid.UUID, *args, **kwargs) -> Response:
        org = get_tenant_organization_from_request(request)

        # Pre-check role belongs to org or system
        self._get_role(role_id, org)

        serializer = RoleUpdateSerializer(data=request.data)
        if not serializer.is_valid():
            return _format_validation_error(serializer)

        correlation_id = getattr(request, "correlation_id", None)

        try:
            role = update_role(
                actor=request.user,
                organization_id=org.id,
                role_id=role_id,
                name=serializer.validated_data.get("name"),
                description=serializer.validated_data.get("description"),
                permission_keys=serializer.validated_data.get("permission_keys"),
                correlation_id=correlation_id,
            )
        except RoleNotFoundError as e:
            return Response({"code": e.code, "detail": e.message}, status=status.HTTP_404_NOT_FOUND)
        except (
            SystemRoleImmutableError,
            RoleRetiredError,
            AccessControlValidationError,
            PermissionNotFoundError,
            PermissionOutsideCeilingError,
            LastAdminProtectionError,
        ) as e:
            return Response({"code": e.code, "detail": e.message}, status=status.HTTP_400_BAD_REQUEST)
        except InsufficientPrivilegesError as e:
            return Response({"code": e.code, "detail": e.message}, status=status.HTTP_403_FORBIDDEN)

        role_with_perms = (
            Role.objects.annotate(assigned_members_count=Count("memberships", distinct=True))
            .prefetch_related(
                Prefetch(
                    "role_permissions",
                    queryset=RolePermission.objects.select_related("permission").order_by(
                        "permission__sort_order", "permission__key"
                    ),
                )
            )
            .get(id=role.id)
        )
        return Response(RoleSerializer(role_with_perms).data, status=status.HTTP_200_OK)


class TenantRoleRetireView(APIView):
    """Retire an unused custom organization role."""

    authentication_classes = [EnforcedSessionAuthentication]
    permission_classes = [RequireTenantContext, HasConsoleModule, HasConsolePermission]
    required_console_module = "tenant_roles"
    required_console_permission = "roles.manage"

    def post(self, request, role_id: uuid.UUID, *args, **kwargs) -> Response:
        org = get_tenant_organization_from_request(request)

        try:
            clean_id = uuid.UUID(str(role_id))
        except (ValueError, TypeError):
            return Response({"code": "ROLE_NOT_FOUND", "detail": "Role not found."}, status=status.HTTP_404_NOT_FOUND)

        correlation_id = getattr(request, "correlation_id", None)

        try:
            role = retire_role(
                actor=request.user,
                organization_id=org.id,
                role_id=clean_id,
                correlation_id=correlation_id,
            )
        except RoleNotFoundError as e:
            return Response({"code": e.code, "detail": e.message}, status=status.HTTP_404_NOT_FOUND)
        except (
            SystemRoleImmutableError,
            RoleRetiredError,
            RoleInUseError,
            LastAdminProtectionError,
            AccessControlValidationError,
        ) as e:
            return Response({"code": e.code, "detail": e.message}, status=status.HTTP_400_BAD_REQUEST)
        except InsufficientPrivilegesError as e:
            return Response({"code": e.code, "detail": e.message}, status=status.HTTP_403_FORBIDDEN)

        role_with_perms = (
            Role.objects.annotate(assigned_members_count=Count("memberships", distinct=True))
            .prefetch_related(
                Prefetch(
                    "role_permissions",
                    queryset=RolePermission.objects.select_related("permission").order_by(
                        "permission__sort_order", "permission__key"
                    ),
                )
            )
            .get(id=role.id)
        )
        return Response(RoleSerializer(role_with_perms).data, status=status.HTTP_200_OK)


class TenantAdminMembershipListView(APIView):
    """List tenant administrator memberships for the active organization."""

    authentication_classes = [EnforcedSessionAuthentication]
    permission_classes = [RequireTenantContext, HasConsoleModule, HasConsolePermission]
    required_console_module = "tenant_roles"
    required_console_permission = "roles.view"
    pagination_class = TenantAccessControlPagination

    def get(self, request, *args, **kwargs) -> Response:
        org = get_tenant_organization_from_request(request)

        membership_type_param = request.query_params.get("membership_type")
        if membership_type_param == "all":
            queryset = (
                OrganizationMembership.objects.filter(organization=org)
                .select_related("user", "role")
                .order_by("-joined_at", "-id")
            )
        elif membership_type_param in MembershipType.values:
            queryset = (
                OrganizationMembership.objects.filter(
                    organization=org,
                    membership_type=membership_type_param,
                )
                .select_related("user", "role")
                .order_by("-joined_at", "-id")
            )
        else:
            queryset = (
                OrganizationMembership.objects.filter(
                    organization=org,
                    membership_type=MembershipType.TENANT_ADMIN,
                )
                .select_related("user", "role")
                .order_by("-joined_at", "-id")
            )

        status_param = request.query_params.get("status")
        if status_param is not None:
            if status_param not in MembershipStatus.values:
                allowed_str = ", ".join(MembershipStatus.values)
                return Response(
                    {
                        "code": "VALIDATION_ERROR",
                        "detail": f"Invalid status '{status_param}'. Allowed: {allowed_str}.",
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
            queryset = queryset.filter(status=status_param)

        paginator = self.pagination_class()
        page = paginator.paginate_queryset(queryset, request, view=self)
        serializer = AdministrativeMembershipSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)


class TenantAdminMembershipRoleView(APIView):
    """Assign or reset an administrative role on a tenant admin membership."""

    authentication_classes = [EnforcedSessionAuthentication]
    permission_classes = [RequireTenantContext, HasConsoleModule, HasConsolePermission]
    required_console_module = "tenant_roles"
    required_console_permission = "roles.assign"

    def patch(self, request, membership_id: uuid.UUID, *args, **kwargs) -> Response:
        org = get_tenant_organization_from_request(request)

        try:
            clean_mem_id = uuid.UUID(str(membership_id))
        except (ValueError, TypeError):
            return Response(
                {"code": "MEMBERSHIP_NOT_FOUND", "detail": "Membership not found in this organization."},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = MembershipRoleAssignSerializer(data=request.data)
        if not serializer.is_valid():
            return _format_validation_error(serializer)

        correlation_id = getattr(request, "correlation_id", None)
        target_role_id = serializer.validated_data["role_id"]

        try:
            membership = assign_membership_role(
                actor=request.user,
                organization_id=org.id,
                membership_id=clean_mem_id,
                role_id=target_role_id,
                correlation_id=correlation_id,
            )
        except RoleNotFoundError as e:
            return Response({"code": e.code, "detail": e.message}, status=status.HTTP_404_NOT_FOUND)
        except AccessControlValidationError as e:
            if e.code == "MEMBERSHIP_NOT_FOUND":
                return Response({"code": e.code, "detail": e.message}, status=status.HTTP_404_NOT_FOUND)
            return Response({"code": e.code, "detail": e.message}, status=status.HTTP_400_BAD_REQUEST)
        except (
            RoleRetiredError,
            RoleNotAssignableToMemberError,
            LastAdminProtectionError,
        ) as e:
            return Response({"code": e.code, "detail": e.message}, status=status.HTTP_400_BAD_REQUEST)
        except InsufficientPrivilegesError as e:
            return Response({"code": e.code, "detail": e.message}, status=status.HTTP_403_FORBIDDEN)

        refreshed_mem = (
            OrganizationMembership.objects.select_related("user", "role")
            .get(id=membership.id)
        )
        return Response(AdministrativeMembershipSerializer(refreshed_mem).data, status=status.HTTP_200_OK)


class PlatformSupportOperatorListView(APIView):
    """Platform Owner API for listing and granting predefined Support Operator roles."""

    authentication_classes = [EnforcedSessionAuthentication]
    permission_classes = [IsPlatformOwnerContext]

    def get(self, request, *args, **kwargs) -> Response:
        assignments = (
            PlatformRoleAssignment.objects.filter(
                role__code__in=PREDEFINED_SUPPORT_ROLES,
                role__is_system_role=True,
                role__organization__isnull=True,
            )
            .select_related("user", "role")
            .order_by("-created_at")
        )
        serializer = PlatformSupportOperatorSerializer(assignments, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request, *args, **kwargs) -> Response:
        serializer = PlatformSupportOperatorAssignSerializer(data=request.data)
        if not serializer.is_valid():
            return _format_validation_error(serializer)

        user_id = serializer.validated_data["user_id"]
        role_code = serializer.validated_data["role_code"]

        target_user = PlatformUser.objects.filter(id=user_id).first()
        if not target_user:
            return Response(
                {"code": "USER_NOT_FOUND", "detail": f"Target user '{user_id}' not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        if getattr(target_user, "status", None) != UserStatus.ACTIVE or not target_user.is_active:
            return Response(
                {"code": "USER_NOT_ACTIVE", "detail": "Target user account is inactive or disabled."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if getattr(target_user, "is_platform_owner", False) or getattr(target_user, "is_superuser", False):
            return Response(
                {
                    "code": "CANNOT_ASSIGN_TO_OWNER",
                    "detail": "Platform Owner or superuser accounts cannot be granted support operator roles.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        role = Role.objects.filter(
            code=role_code,
            is_system_role=True,
            organization__isnull=True,
            status=RoleStatus.ACTIVE,
        ).first()
        if not role:
            return Response(
                {"code": "ROLE_NOT_FOUND", "detail": f"Support role '{role_code}' not found or inactive."},
                status=status.HTTP_404_NOT_FOUND,
            )

        with transaction.atomic():
            assignment, created = PlatformRoleAssignment.objects.get_or_create(
                user=target_user,
                role=role,
            )

            if created:
                record_audit_event(
                    action=AuditAction.SUPPORT_ROLE_GRANTED,
                    target_type=AuditTargetType.USER,
                    target_id=target_user.id,
                    target_repr=f"Granted support role '{role.code}' to user {target_user.id}",
                    actor=request.user,
                    organization_id=None,
                    operation_source=AuditOperationSource.INTERACTIVE,
                    correlation_id=getattr(request, "correlation_id", None),
                    metadata={
                        "target_user_id": str(target_user.id),
                        "role_code": role.code,
                        "role_id": str(role.id),
                        "assignment_id": str(assignment.id),
                    },
                )

        return Response(
            PlatformSupportOperatorSerializer(assignment).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class PlatformSupportOperatorDetailView(APIView):
    """Platform Owner API for revoking predefined Support Operator roles."""

    authentication_classes = [EnforcedSessionAuthentication]
    permission_classes = [IsPlatformOwnerContext]

    def delete(
        self,
        request,
        pk: uuid.UUID | None = None,
        user_id: uuid.UUID | None = None,
        role_code: str | None = None,
        *args,
        **kwargs,
    ) -> Response:
        assignment = None
        if pk:
            assignment = PlatformRoleAssignment.objects.filter(
                id=pk,
                role__code__in=PREDEFINED_SUPPORT_ROLES,
            ).select_related("user", "role").first()
            if not assignment:
                assignment = PlatformRoleAssignment.objects.filter(
                    user_id=pk,
                    role__code__in=PREDEFINED_SUPPORT_ROLES,
                ).select_related("user", "role").first()

        if not assignment and user_id and role_code:
            assignment = PlatformRoleAssignment.objects.filter(
                user_id=user_id,
                role__code=role_code,
                role__code__in=PREDEFINED_SUPPORT_ROLES,
            ).select_related("user", "role").first()

        if not assignment:
            return Response(status=status.HTTP_204_NO_CONTENT)

        target_user = assignment.user
        role = assignment.role
        assignment_id_str = str(assignment.id)

        with transaction.atomic():
            assignment.delete()

            record_audit_event(
                action=AuditAction.SUPPORT_ROLE_REVOKED,
                target_type=AuditTargetType.USER,
                target_id=target_user.id,
                target_repr=f"Revoked support role '{role.code}' from user {target_user.id}",
                actor=request.user,
                organization_id=None,
                operation_source=AuditOperationSource.INTERACTIVE,
                correlation_id=getattr(request, "correlation_id", None),
                metadata={
                    "target_user_id": str(target_user.id),
                    "role_code": role.code,
                    "role_id": str(role.id),
                    "assignment_id": assignment_id_str,
                },
            )

        return Response(status=status.HTTP_204_NO_CONTENT)

