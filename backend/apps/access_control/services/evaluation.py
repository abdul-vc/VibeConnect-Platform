"""Centralized Server-Side Permission Evaluation Engine for VibeConnect Phase 2E (Stage 3).

Provides authoritative evaluation of effective permissions and allowed console modules
with request-scoped memoization.
"""

from dataclasses import dataclass
from typing import Any
import uuid

from apps.access_control.constants import (
    CONTEXT_PLATFORM_OWNER,
    CONTEXT_SUPPORT,
    CONTEXT_TENANT,
    PLATFORM_OWNER_MODULE_KEYS,
    SUPPORT_MODULE_CONSOLE,
    SUPPORT_PERMISSION_KEYS,
)
from apps.access_control.models import (
    AccessPermission,
    ConsoleModule,
    ConsoleModuleContext,
    OrganizationConsoleModulePolicy,
    OrganizationPermissionCeiling,
    PlatformRoleAssignment,
    RolePermission,
    RoleStatus,
)
from apps.organizations.models import (
    MembershipStatus,
    MembershipType,
    Organization,
    OrganizationMembership,
    OrganizationStatus,
)


@dataclass(frozen=True)
class AccessEvaluationResult:
    """Immutable evaluation result for a user under a specific console context."""

    context_type: str
    organization_id: str | None
    effective_permissions: list[str]
    allowed_modules: list[str]

    def has_permission(self, permission: str) -> bool:
        return permission in self.effective_permissions

    def has_module(self, module: str) -> bool:
        return module in self.allowed_modules


def evaluate_access(
    user: Any,
    context_type: str,
    organization_id: uuid.UUID | str | None = None,
) -> AccessEvaluationResult:
    """Evaluate effective permissions and allowed modules from trusted server-side state.

    Enforces:
    - User authentication and active status.
    - Context-specific eligibility (Platform Owner vs Tenant Admin).
    - Multi-tenant boundary isolation.
    - Role validity, scoping, and active status.
    - Organization module policy and permission ceiling constraints.
    """
    clean_org_str = str(organization_id) if organization_id is not None else None

    # Base user eligibility
    if not user or not getattr(user, "is_authenticated", False) or not getattr(user, "is_active", False):
        return AccessEvaluationResult(
            context_type=context_type,
            organization_id=clean_org_str,
            effective_permissions=[],
            allowed_modules=[],
        )

    if getattr(user, "status", None) != "active":
        return AccessEvaluationResult(
            context_type=context_type,
            organization_id=clean_org_str,
            effective_permissions=[],
            allowed_modules=[],
        )

    # Platform Owner evaluation
    if context_type == CONTEXT_PLATFORM_OWNER:
        if not getattr(user, "is_platform_owner", False):
            return AccessEvaluationResult(
                context_type=CONTEXT_PLATFORM_OWNER,
                organization_id=None,
                effective_permissions=[],
                allowed_modules=[],
            )

        po_modules = list(
            ConsoleModule.objects.filter(
                target_context=ConsoleModuleContext.PLATFORM_OWNER,
                is_active=True,
            )
            .order_by("sort_order", "key")
            .values_list("key", flat=True)
        )
        if not po_modules:
            po_modules = list(PLATFORM_OWNER_MODULE_KEYS)

        return AccessEvaluationResult(
            context_type=CONTEXT_PLATFORM_OWNER,
            organization_id=None,
            effective_permissions=[],
            allowed_modules=po_modules,
        )

    # Tenant Admin evaluation
    if context_type == CONTEXT_TENANT:
        if not organization_id:
            return AccessEvaluationResult(
                context_type=CONTEXT_TENANT,
                organization_id=None,
                effective_permissions=[],
                allowed_modules=[],
            )

        try:
            clean_org_uuid = (
                uuid.UUID(str(organization_id))
                if not isinstance(organization_id, uuid.UUID)
                else organization_id
            )
        except (ValueError, TypeError):
            return AccessEvaluationResult(
                context_type=CONTEXT_TENANT,
                organization_id=clean_org_str,
                effective_permissions=[],
                allowed_modules=[],
            )

        org = Organization.objects.filter(
            id=clean_org_uuid,
            status=OrganizationStatus.ACTIVE,
        ).first()
        if not org:
            return AccessEvaluationResult(
                context_type=CONTEXT_TENANT,
                organization_id=str(clean_org_uuid),
                effective_permissions=[],
                allowed_modules=[],
            )

        membership = (
            OrganizationMembership.objects.filter(
                organization=org,
                user=user,
                membership_type=MembershipType.TENANT_ADMIN,
                status=MembershipStatus.ACTIVE,
            )
            .select_related("role")
            .first()
        )
        if not membership:
            return AccessEvaluationResult(
                context_type=CONTEXT_TENANT,
                organization_id=str(org.id),
                effective_permissions=[],
                allowed_modules=[],
            )

        role = membership.role
        if not role or role.status != RoleStatus.ACTIVE:
            return AccessEvaluationResult(
                context_type=CONTEXT_TENANT,
                organization_id=str(org.id),
                effective_permissions=[],
                allowed_modules=[],
            )

        # Scoping rule: System role is platform-wide (organization is None);
        # Custom role must strictly belong to target organization.
        if not role.is_system_role and role.organization_id != org.id:
            return AccessEvaluationResult(
                context_type=CONTEXT_TENANT,
                organization_id=str(org.id),
                effective_permissions=[],
                allowed_modules=[],
            )

        # 1. Allowed modules calculation
        allowed_modules: list[str] = []
        tenant_modules = ConsoleModule.objects.filter(
            target_context=ConsoleModuleContext.TENANT,
            is_active=True,
        ).order_by("sort_order", "key")

        enabled_policies = set(
            OrganizationConsoleModulePolicy.objects.filter(
                organization=org,
                is_enabled=True,
            ).values_list("console_module_id", flat=True)
        )

        for mod in tenant_modules:
            if mod.is_core:
                allowed_modules.append(mod.key)
            elif mod.key in enabled_policies:
                allowed_modules.append(mod.key)

        # 2. Effective permissions calculation
        role_perms = set(
            RolePermission.objects.filter(role=role)
            .values_list("permission_id", flat=True)
        )

        if not role_perms:
            return AccessEvaluationResult(
                context_type=CONTEXT_TENANT,
                organization_id=str(org.id),
                effective_permissions=[],
                allowed_modules=allowed_modules,
            )

        allowed_ceilings = set(
            OrganizationPermissionCeiling.objects.filter(
                organization=org,
                permission_id__in=role_perms,
                is_allowed=True,
            ).values_list("permission_id", flat=True)
        )

        active_enabled_modules = set(
            ConsoleModule.objects.filter(
                target_context=ConsoleModuleContext.TENANT,
                is_active=True,
                key__in=enabled_policies,
            ).values_list("key", flat=True)
        )

        eligible_perm_keys = role_perms.intersection(allowed_ceilings)

        effective_perms_qs = AccessPermission.objects.filter(
            key__in=eligible_perm_keys,
            is_active=True,
            console_module_id__in=active_enabled_modules,
        ).values_list("key", flat=True)

        effective_perms = sorted(set(k for k in effective_perms_qs if k != "*"))

        return AccessEvaluationResult(
            context_type=CONTEXT_TENANT,
            organization_id=str(org.id),
            effective_permissions=effective_perms,
            allowed_modules=allowed_modules,
        )

    # Support Console evaluation (Phase 6C)
    if context_type == CONTEXT_SUPPORT:
        if getattr(user, "is_platform_owner", False):
            support_perms = list(
                AccessPermission.objects.filter(
                    console_module__target_context=ConsoleModuleContext.SUPPORT,
                    is_active=True,
                    console_module__is_active=True,
                )
                .order_by("sort_order", "key")
                .values_list("key", flat=True)
            )
            if not support_perms:
                support_perms = list(SUPPORT_PERMISSION_KEYS)
            return AccessEvaluationResult(
                context_type=CONTEXT_SUPPORT,
                organization_id=None,
                effective_permissions=sorted(support_perms),
                allowed_modules=[SUPPORT_MODULE_CONSOLE],
            )

        assignments = PlatformRoleAssignment.objects.filter(
            user=user,
            role__status=RoleStatus.ACTIVE,
            role__is_system_role=True,
            role__organization__isnull=True,
        ).select_related("role")

        if not assignments.exists():
            return AccessEvaluationResult(
                context_type=CONTEXT_SUPPORT,
                organization_id=None,
                effective_permissions=[],
                allowed_modules=[],
            )

        role_ids = assignments.values_list("role_id", flat=True)
        active_role_perms = AccessPermission.objects.filter(
            role_permissions__role_id__in=role_ids,
            is_active=True,
            console_module__is_active=True,
            console_module__target_context=ConsoleModuleContext.SUPPORT,
        ).distinct()

        effective_perms = sorted(list(active_role_perms.values_list("key", flat=True)))
        allowed_mods = sorted(
            list(
                ConsoleModule.objects.filter(
                    permissions__in=active_role_perms,
                    is_active=True,
                )
                .distinct()
                .values_list("key", flat=True)
            )
        )

        return AccessEvaluationResult(
            context_type=CONTEXT_SUPPORT,
            organization_id=None,
            effective_permissions=effective_perms,
            allowed_modules=allowed_mods,
        )

    # Unknown context type
    return AccessEvaluationResult(
        context_type=context_type,
        organization_id=clean_org_str,
        effective_permissions=[],
        allowed_modules=[],
    )


def get_request_evaluation(
    request: Any,
    user: Any,
    context_type: str,
    organization_id: uuid.UUID | str | None = None,
) -> AccessEvaluationResult:
    """Retrieve or compute request-scoped access evaluation result.

    Memoized strictly on the request object for the lifetime of that request.
    Never caches across requests or in session/persistent storage.
    """
    clean_org_id = str(organization_id) if organization_id is not None else None
    user_id = str(getattr(user, "id", "")) if user else ""
    cache_key = (user_id, context_type, clean_org_id)

    if request is not None and hasattr(request, "_access_evaluations"):
        if cache_key in request._access_evaluations:
            return request._access_evaluations[cache_key]

    result = evaluate_access(user, context_type, organization_id)

    if request is not None:
        if not hasattr(request, "_access_evaluations"):
            request._access_evaluations = {}
        request._access_evaluations[cache_key] = result

    return result
