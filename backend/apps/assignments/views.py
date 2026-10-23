"""Assignment Domain API Views (Phase 2F Part D).

Implements:
- /api/v1/tenant/assignments/ (GET list, POST create)
- /api/v1/tenant/assignments/<uuid:pk>/ (GET detail)
- /api/v1/tenant/assignments/<uuid:pk>/suspend/ (POST suspend)
- /api/v1/tenant/assignments/<uuid:pk>/reactivate/ (POST reactivate)
- /api/v1/tenant/assignments/<uuid:pk>/revoke/ (POST revoke)
- /api/v1/tenant/assignments/<uuid:pk>/modules/ (PATCH replace modules)
- /api/v1/tenant/assignments/selectors/products/ (GET product selector)
- /api/v1/tenant/assignments/selectors/members/ (GET member selector)
- /api/v1/tenant/assignments/selectors/modules/ (GET module selector)
"""

import uuid
from typing import Any

from django.db.models import Count, Q
from rest_framework import exceptions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.access_control.constants import CONTEXT_TENANT
from apps.access_control.permissions import HasConsoleModule, HasConsolePermission
from apps.access_control.views import RequireTenantContext, get_tenant_organization_from_request
from apps.assignments.models import AssignmentStatus, UserProductAssignment
from apps.assignments.pagination import AssignmentPagination
from apps.assignments.serializers import (
    AssignmentCreateSerializer,
    AssignmentDetailSerializer,
    AssignmentListSerializer,
    AssignmentModuleReplaceSerializer,
    AssignmentReasonSerializer,
    SelectorMemberSerializer,
    SelectorModuleSerializer,
    SelectorProductSerializer,
)
from apps.assignments.services.assignment_services import (
    assign_user_to_product,
    reactivate_user_assignment,
    replace_user_module_assignments,
    revoke_user_assignment,
    suspend_user_assignment,
)
from apps.assignments.services.exceptions import (
    AlreadyAssignedError,
    AssignmentNotFoundError,
    AssignmentServiceError,
    InvalidModuleIdsError,
    InvalidReasonError,
    InvalidSeatQuotaConfigError,
    InvalidStateTransitionError,
    MembershipIneligibleError,
    ModuleNotEntitledError,
    OrganizationNotActiveError,
    ProductInactiveError,
    ProductNotEntitledError,
    SeatLimitExceededError,
    SeatQuotaUnconfiguredError,
    SubscriptionUnavailableError,
    UserDisabledError,
    UserInactiveError,
)
from apps.assignments.services.seat_engine import (
    get_temporally_eligible_subscription,
    resolve_seat_pool,
)
from apps.auditlog.models import AuditOperationSource
from apps.entitlements.models import EntitlementStatus, OrganizationProductEntitlement
from apps.identity.authentication import EnforcedSessionAuthentication
from apps.organizations.models import MembershipStatus, OrganizationMembership
from apps.product_registry.models import CatalogStatus, Product, ProductModule, ProductStatus


class InvalidQueryParamError(AssignmentServiceError):
    """Raised when a query parameter is missing or invalid."""

    def __init__(self, message: str = "Invalid query parameter.", code: str = "INVALID_QUERY_PARAM"):
        super().__init__(message, code=code)


ERROR_CODE_STATUS_MAP = {
    "INVALID_REASON": status.HTTP_400_BAD_REQUEST,
    "INVALID_QUERY_PARAM": status.HTTP_400_BAD_REQUEST,
    "ORGANIZATION_INACTIVE": status.HTTP_403_FORBIDDEN,
    "INSUFFICIENT_PRIVILEGES": status.HTTP_403_FORBIDDEN,
    "CSRF_FAILED": status.HTTP_403_FORBIDDEN,
    "ASSIGNMENT_NOT_FOUND": status.HTTP_404_NOT_FOUND,
    "ALREADY_ASSIGNED": status.HTTP_409_CONFLICT,
    "INVALID_STATE_TRANSITION": status.HTTP_409_CONFLICT,
    "USER_INACTIVE": status.HTTP_422_UNPROCESSABLE_ENTITY,
    "USER_DISABLED": status.HTTP_422_UNPROCESSABLE_ENTITY,
    "MEMBERSHIP_INELIGIBLE": status.HTTP_422_UNPROCESSABLE_ENTITY,
    "SUBSCRIPTION_UNAVAILABLE": status.HTTP_422_UNPROCESSABLE_ENTITY,
    "PRODUCT_INACTIVE": status.HTTP_422_UNPROCESSABLE_ENTITY,
    "PRODUCT_NOT_ENTITLED": status.HTTP_422_UNPROCESSABLE_ENTITY,
    "INVALID_SEAT_QUOTA_CONFIG": status.HTTP_422_UNPROCESSABLE_ENTITY,
    "SEAT_QUOTA_UNCONFIGURED": status.HTTP_422_UNPROCESSABLE_ENTITY,
    "SEAT_LIMIT_EXCEEDED": status.HTTP_422_UNPROCESSABLE_ENTITY,
    "INVALID_MODULE_IDS": status.HTTP_422_UNPROCESSABLE_ENTITY,
    "MODULE_NOT_ENTITLED": status.HTTP_422_UNPROCESSABLE_ENTITY,
}


def _get_correlation_id(request: Any) -> uuid.UUID | None:
    corr = getattr(request, "correlation_id", None) or request.headers.get("X-Correlation-ID")
    if corr:
        try:
            return uuid.UUID(str(corr))
        except (ValueError, TypeError):
            pass
    return None


class BaseAssignmentView(APIView):
    """Base APIView for assignment endpoints enforcing auth, module policy, permissions, and error envelope."""

    authentication_classes = [EnforcedSessionAuthentication]
    permission_classes = [RequireTenantContext, HasConsoleModule, HasConsolePermission]
    required_console_module = "tenant_product_assignments"
    required_console_permission = "assignments.view"

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        request.organization = get_tenant_organization_from_request(request)

    def handle_exception(self, exc):
        # 1. CSRF failures from EnforcedSessionAuthentication
        if isinstance(exc, exceptions.PermissionDenied) and "CSRF" in str(exc):
            return Response(
                {
                    "error": {
                        "code": "CSRF_FAILED",
                        "message": "CSRF verification failed.",
                        "details": {},
                    }
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        # 2. PermissionDenied / Inactive Org / Ceilings
        if isinstance(exc, exceptions.PermissionDenied):
            detail = exc.detail
            if isinstance(detail, dict):
                code = detail.get("code", "INSUFFICIENT_PRIVILEGES")
                msg = detail.get("detail", str(exc))
            else:
                code = "INSUFFICIENT_PRIVILEGES"
                msg = str(detail)

            if code == "ORGANIZATION_NOT_ACTIVE":
                code = "ORGANIZATION_INACTIVE"
            elif code not in ("ORGANIZATION_INACTIVE", "INSUFFICIENT_PRIVILEGES", "CSRF_FAILED"):
                code = "INSUFFICIENT_PRIVILEGES"

            return Response(
                {
                    "error": {
                        "code": code,
                        "message": msg,
                        "details": {},
                    }
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        # 3. Known domain exceptions mapping to ERROR_CODE_STATUS_MAP
        exc_code = getattr(exc, "code", None)
        if isinstance(exc, OrganizationNotActiveError):
            exc_code = "ORGANIZATION_INACTIVE"

        if exc_code in ERROR_CODE_STATUS_MAP:
            return Response(
                {
                    "error": {
                        "code": exc_code,
                        "message": str(exc),
                        "details": {},
                    }
                },
                status=ERROR_CODE_STATUS_MAP[exc_code],
            )

        # 4. DRF NotFound
        if isinstance(exc, exceptions.NotFound):
            return Response(
                {
                    "error": {
                        "code": "ASSIGNMENT_NOT_FOUND",
                        "message": str(exc),
                        "details": {},
                    }
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        # 5. DRF ValidationError
        if isinstance(exc, exceptions.ValidationError):
            msg = str(exc)
            return Response(
                {
                    "error": {
                        "code": "INVALID_QUERY_PARAM" if "query" in msg.lower() else "INVALID_REASON",
                        "message": msg,
                        "details": exc.detail if isinstance(exc.detail, dict) else {},
                    }
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        return super().handle_exception(exc)


class AssignmentListCreateView(BaseAssignmentView):
    """List assignments (GET) or create a new assignment (POST)."""

    pagination_class = AssignmentPagination

    def get_required_console_permission(self) -> str:
        if self.request.method == "POST":
            return "assignments.manage"
        return "assignments.view"

    def get(self, request, *args, **kwargs) -> Response:
        org = request.organization
        qs = (
            UserProductAssignment.objects.filter(organization=org)
            .select_related("user", "product")
            .annotate(
                enabled_module_count=Count(
                    "module_assignments",
                    filter=Q(module_assignments__is_enabled=True),
                )
            )
        )

        # Filtering: status
        status_param = request.query_params.get("status")
        if status_param:
            qs = qs.filter(status=status_param.lower())

        # Filtering: product_id
        product_id_param = request.query_params.get("product_id")
        if product_id_param:
            try:
                prod_uuid = uuid.UUID(str(product_id_param))
                qs = qs.filter(product_id=prod_uuid)
            except (ValueError, TypeError):
                raise InvalidQueryParamError(
                    "Query parameter 'product_id' must be a valid UUID.",
                    code="INVALID_QUERY_PARAM",
                )

        # Filtering: search
        search_param = request.query_params.get("search")
        if search_param:
            search_trimmed = search_param.strip()
            qs = qs.filter(
                Q(user__full_name__icontains=search_trimmed)
                | Q(user__email__icontains=search_trimmed)
                | Q(product__name__icontains=search_trimmed)
            )

        # Ordering: -assigned_at, -id
        qs = qs.order_by("-assigned_at", "-id")

        paginator = self.pagination_class()
        page = paginator.paginate_queryset(qs, request, view=self)
        serializer = AssignmentListSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    def post(self, request, *args, **kwargs) -> Response:
        serializer = AssignmentCreateSerializer(data=request.data)
        if not serializer.is_valid():
            if "module_ids" in serializer.errors:
                raise InvalidModuleIdsError(
                    "Invalid module_ids.", code="INVALID_MODULE_IDS"
                )
            raise InvalidQueryParamError(
                str(serializer.errors), code="INVALID_QUERY_PARAM"
            )

        user_id = serializer.validated_data["user_id"]
        product_id = serializer.validated_data["product_id"]
        module_ids = serializer.validated_data.get("module_ids", [])

        assignment = assign_user_to_product(
            organization_id=request.organization.id,
            user_id=user_id,
            product_id=product_id,
            module_ids=module_ids,
            actor=request.user,
            correlation_id=_get_correlation_id(request),
            operation_source=AuditOperationSource.INTERACTIVE,
        )

        detail_serializer = AssignmentDetailSerializer(assignment)
        return Response(detail_serializer.data, status=status.HTTP_201_CREATED)


class AssignmentDetailView(BaseAssignmentView):
    """Retrieve assignment detail (GET)."""

    required_console_permission = "assignments.view"

    def get(self, request, pk: uuid.UUID, *args, **kwargs) -> Response:
        assignment = (
            UserProductAssignment.objects.filter(
                id=pk, organization=request.organization
            )
            .select_related("user", "product", "membership__role")
            .prefetch_related("module_assignments__module")
            .first()
        )
        if not assignment:
            raise AssignmentNotFoundError(
                f"Assignment '{pk}' not found.", code="ASSIGNMENT_NOT_FOUND"
            )

        serializer = AssignmentDetailSerializer(assignment)
        return Response(serializer.data, status=status.HTTP_200_OK)


class AssignmentSuspendView(BaseAssignmentView):
    """Suspend an assignment (POST)."""

    required_console_permission = "assignments.manage"

    def post(self, request, pk: uuid.UUID, *args, **kwargs) -> Response:
        assignment = UserProductAssignment.objects.filter(
            id=pk, organization=request.organization
        ).first()
        if not assignment:
            raise AssignmentNotFoundError(
                f"Assignment '{pk}' not found.", code="ASSIGNMENT_NOT_FOUND"
            )

        serializer = AssignmentReasonSerializer(data=request.data)
        if not serializer.is_valid():
            raise InvalidReasonError(
                "Reason must be between 1 and 500 characters.", code="INVALID_REASON"
            )

        reason = serializer.validated_data["reason"]
        updated = suspend_user_assignment(
            assignment_id=pk,
            actor=request.user,
            reason=reason,
            correlation_id=_get_correlation_id(request),
        )

        detail_serializer = AssignmentDetailSerializer(updated)
        return Response(detail_serializer.data, status=status.HTTP_200_OK)


class AssignmentReactivateView(BaseAssignmentView):
    """Reactivate a suspended assignment (POST)."""

    required_console_permission = "assignments.manage"

    def post(self, request, pk: uuid.UUID, *args, **kwargs) -> Response:
        assignment = UserProductAssignment.objects.filter(
            id=pk, organization=request.organization
        ).first()
        if not assignment:
            raise AssignmentNotFoundError(
                f"Assignment '{pk}' not found.", code="ASSIGNMENT_NOT_FOUND"
            )

        updated = reactivate_user_assignment(
            assignment_id=pk,
            actor=request.user,
            correlation_id=_get_correlation_id(request),
        )

        detail_serializer = AssignmentDetailSerializer(updated)
        return Response(detail_serializer.data, status=status.HTTP_200_OK)


class AssignmentRevokeView(BaseAssignmentView):
    """Revoke an assignment (POST)."""

    required_console_permission = "assignments.manage"

    def post(self, request, pk: uuid.UUID, *args, **kwargs) -> Response:
        assignment = UserProductAssignment.objects.filter(
            id=pk, organization=request.organization
        ).first()
        if not assignment:
            raise AssignmentNotFoundError(
                f"Assignment '{pk}' not found.", code="ASSIGNMENT_NOT_FOUND"
            )

        serializer = AssignmentReasonSerializer(data=request.data)
        if not serializer.is_valid():
            raise InvalidReasonError(
                "Reason must be between 1 and 500 characters.", code="INVALID_REASON"
            )

        reason = serializer.validated_data["reason"]
        updated = revoke_user_assignment(
            assignment_id=pk,
            actor=request.user,
            reason=reason,
            correlation_id=_get_correlation_id(request),
        )

        detail_serializer = AssignmentDetailSerializer(updated)
        return Response(detail_serializer.data, status=status.HTTP_200_OK)


class AssignmentModulesView(BaseAssignmentView):
    """Replace module selections on an assignment (PATCH)."""

    required_console_permission = "assignments.manage"

    def patch(self, request, pk: uuid.UUID, *args, **kwargs) -> Response:
        assignment = UserProductAssignment.objects.filter(
            id=pk, organization=request.organization
        ).first()
        if not assignment:
            raise AssignmentNotFoundError(
                f"Assignment '{pk}' not found.", code="ASSIGNMENT_NOT_FOUND"
            )

        serializer = AssignmentModuleReplaceSerializer(data=request.data)
        if not serializer.is_valid():
            raise InvalidModuleIdsError(
                "Invalid module IDs provided.", code="INVALID_MODULE_IDS"
            )

        module_ids = serializer.validated_data.get("module_ids", [])
        if len(module_ids) > 100:
            raise InvalidModuleIdsError(
                "Maximum 100 module IDs allowed.", code="INVALID_MODULE_IDS"
            )

        updated = replace_user_module_assignments(
            assignment_id=pk,
            module_ids=module_ids,
            actor=request.user,
            correlation_id=_get_correlation_id(request),
        )

        detail_serializer = AssignmentDetailSerializer(updated)
        return Response(detail_serializer.data, status=status.HTTP_200_OK)


class SelectorProductsView(BaseAssignmentView):
    """List entitled products with seat capacity metrics for selection (GET)."""

    required_console_permission = "assignments.manage"

    def get(self, request, *args, **kwargs) -> Response:
        sub = get_temporally_eligible_subscription(request.organization.id)
        
        sub_prod_ids = set()
        if sub:
            sub_prod_ids = set(
                sub.product_entitlements.values_list("product_id", flat=True)
            )

        direct_grants = OrganizationProductEntitlement.objects.filter(
            organization=request.organization,
            status=EntitlementStatus.ACTIVE,
        )
        direct_prod_ids = set(direct_grants.values_list("product_id", flat=True))

        all_entitled_prod_ids = sub_prod_ids | direct_prod_ids
        if not all_entitled_prod_ids:
            return Response([])

        products = (
            Product.objects.filter(id__in=all_entitled_prod_ids, status=ProductStatus.ACTIVE)
            .order_by("name", "code", "id")[:100]
        )

        items = []
        for p in products:
            if sub and p.id in sub_prod_ids:
                try:
                    res = resolve_seat_pool(
                        organization_id=request.organization.id,
                        product_id=p.id,
                        subscription=sub,
                    )
                    items.append(
                        {
                            "id": str(p.id),
                            "code": p.code,
                            "name": p.name,
                            "pool_scope": res.pool_scope,
                            "quota_type": res.limit_type,
                            "total_limit": res.total_limit,
                            "consumed_seats": res.consumed_seats,
                            "available_seats": res.available_seats,
                            "is_capacity_available": res.is_capacity_available,
                        }
                    )
                    continue
                except Exception:
                    pass

            consumed_seats = UserProductAssignment.objects.filter(
                organization=request.organization,
                product=p,
                status__in=[AssignmentStatus.ACTIVE, AssignmentStatus.SUSPENDED],
            ).count()
            items.append(
                {
                    "id": str(p.id),
                    "code": p.code,
                    "name": p.name,
                    "pool_scope": "direct_grant",
                    "quota_type": "unlimited",
                    "total_limit": None,
                    "consumed_seats": consumed_seats,
                    "available_seats": None,
                    "is_capacity_available": True,
                }
            )

        return Response(items)


class SelectorMembersView(BaseAssignmentView):
    """List assignable members for a selected product (GET)."""

    pagination_class = AssignmentPagination
    required_console_permission = "assignments.manage"

    def get(self, request, *args, **kwargs) -> Response:
        product_id_str = request.query_params.get("product_id")
        if not product_id_str:
            raise InvalidQueryParamError(
                "Query parameter 'product_id' is required.", code="INVALID_QUERY_PARAM"
            )

        try:
            product_uuid = uuid.UUID(str(product_id_str))
        except (ValueError, TypeError):
            raise InvalidQueryParamError(
                "Query parameter 'product_id' must be a valid UUID.",
                code="INVALID_QUERY_PARAM",
            )

        qs = OrganizationMembership.objects.filter(
            organization=request.organization,
            status=MembershipStatus.ACTIVE,
        )

        # Exclude members already holding an open assignment (ACTIVE or SUSPENDED)
        assigned_user_ids = UserProductAssignment.objects.filter(
            organization=request.organization,
            product_id=product_uuid,
            status__in=[AssignmentStatus.ACTIVE, AssignmentStatus.SUSPENDED],
        ).values_list("user_id", flat=True)
        qs = qs.exclude(user_id__in=assigned_user_ids)

        search = request.query_params.get("search")
        if search:
            search_trimmed = search.strip()
            qs = qs.filter(
                Q(user__full_name__icontains=search_trimmed)
                | Q(user__email__icontains=search_trimmed)
            )

        qs = qs.select_related("user", "role").order_by("user__email", "id")

        paginator = self.pagination_class()
        page = paginator.paginate_queryset(qs, request, view=self)

        results = [
            {
                "membership_id": str(m.id),
                "user_id": str(m.user.id),
                "email": m.user.email,
                "full_name": m.user.full_name,
                "role_code": m.role.code if m.role else m.membership_type,
            }
            for m in page
        ]

        return paginator.get_paginated_response(results)


class SelectorModulesView(BaseAssignmentView):
    """List entitled active modules for a selected product (GET)."""

    required_console_permission = "assignments.manage"

    def get(self, request, *args, **kwargs) -> Response:
        product_id_str = request.query_params.get("product_id")
        if not product_id_str:
            raise InvalidQueryParamError(
                "Query parameter 'product_id' is required.", code="INVALID_QUERY_PARAM"
            )

        try:
            product_uuid = uuid.UUID(str(product_id_str))
        except (ValueError, TypeError):
            raise InvalidQueryParamError(
                "Query parameter 'product_id' must be a valid UUID.",
                code="INVALID_QUERY_PARAM",
            )

        sub = get_temporally_eligible_subscription(request.organization.id)
        is_direct_granted = OrganizationProductEntitlement.objects.filter(
            organization=request.organization,
            product_id=product_uuid,
            status=EntitlementStatus.ACTIVE,
        ).exists()

        if not sub and not is_direct_granted:
            return Response([])

        if sub and sub.product_entitlements.filter(product_id=product_uuid).exists():
            entitled_module_ids = list(
                sub.module_entitlements.filter(
                    module__product_id=product_uuid
                ).values_list("module_id", flat=True)
            )
            modules = (
                ProductModule.objects.filter(
                    id__in=entitled_module_ids,
                    product_id=product_uuid,
                    status=CatalogStatus.ACTIVE,
                )
                .order_by("name", "code", "id")[:100]
            )
        else:
            modules = (
                ProductModule.objects.filter(
                    product_id=product_uuid,
                    status=CatalogStatus.ACTIVE,
                )
                .order_by("name", "code", "id")[:100]
            )

        items = [
            {
                "id": str(m.id),
                "code": m.code,
                "name": m.name,
                "description": m.description,
                "is_entitled": True,
            }
            for m in modules
        ]

        return Response(items)
