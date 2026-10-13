"""Access Evaluation Services.

Provides internal, pure evaluation of effective user product and module access
consumed by Phase 2G App Launcher and authorization helpers. Zero HTTP dependency.
"""

from dataclasses import dataclass
from datetime import datetime
import uuid

from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.assignments.models import AssignmentStatus, UserProductAssignment
from apps.assignments.services.exceptions import MultipleActiveSubscriptionsError
from apps.assignments.services.seat_engine import get_temporally_eligible_subscription
from apps.organizations.models import MembershipStatus, Organization, OrganizationMembership, OrganizationStatus
from apps.product_registry.models import CatalogStatus, Product, ProductStatus

PlatformUser = get_user_model()


@dataclass(frozen=True)
class UserProductAccessResult:
    """Immutable result structure for effective product and module access evaluation."""

    has_access: bool
    denial_code: str | None
    denial_reason: str | None
    assignment_status: str | None
    is_subscription_eligible: bool
    enabled_module_ids: list[uuid.UUID]
    enabled_module_codes: list[str]


def evaluate_user_product_access(
    *,
    organization_id: uuid.UUID,
    user_id: uuid.UUID,
    product_id: uuid.UUID,
    at_time: datetime | None = None,
) -> UserProductAccessResult:
    """Evaluate whether a central user holds effective access to a product and its modules.

    Deterministic Denial Precedence:
    1. Organization ACTIVE -> ORGANIZATION_INACTIVE
    2. Central User ACTIVE -> USER_DISABLED or USER_INACTIVE
    3. Organization Membership ACTIVE -> MEMBERSHIP_INELIGIBLE
    4. Subscription temporally eligible -> SUBSCRIPTION_UNAVAILABLE
    5. Catalog Product ACTIVE -> PRODUCT_INACTIVE
    6. SubscriptionProductEntitlement in snapshot -> PRODUCT_NOT_ENTITLED
    7. UserProductAssignment exists (not revoked) -> ASSIGNMENT_NOT_FOUND
    8. UserProductAssignment status ACTIVE -> ASSIGNMENT_SUSPENDED
    9. All pass -> has_access=True, populated enabled modules
    """
    if at_time is None:
        at_time = timezone.now()

    # 1. Organization Check
    org = Organization.objects.filter(id=organization_id).first()
    if not org or org.status != OrganizationStatus.ACTIVE:
        return UserProductAccessResult(
            has_access=False,
            denial_code="ORGANIZATION_INACTIVE",
            denial_reason="Organization is not in active status.",
            assignment_status=None,
            is_subscription_eligible=False,
            enabled_module_ids=[],
            enabled_module_codes=[],
        )

    # 2. Central User Check
    user = PlatformUser.objects.filter(id=user_id).first()
    if not user:
        return UserProductAccessResult(
            has_access=False,
            denial_code="USER_INACTIVE",
            denial_reason="Platform user record does not exist.",
            assignment_status=None,
            is_subscription_eligible=False,
            enabled_module_ids=[],
            enabled_module_codes=[],
        )

    if user.status == "disabled" or getattr(user, "is_active", True) is False:
        return UserProductAccessResult(
            has_access=False,
            denial_code="USER_DISABLED" if user.status == "disabled" else "USER_INACTIVE",
            denial_reason="Platform user account is disabled or deactivated.",
            assignment_status=None,
            is_subscription_eligible=False,
            enabled_module_ids=[],
            enabled_module_codes=[],
        )

    if user.status != "active":
        return UserProductAccessResult(
            has_access=False,
            denial_code="USER_INACTIVE",
            denial_reason=f"Platform user account status is '{user.status}'.",
            assignment_status=None,
            is_subscription_eligible=False,
            enabled_module_ids=[],
            enabled_module_codes=[],
        )

    # 3. Organization Membership Check
    membership = OrganizationMembership.objects.filter(
        organization_id=organization_id,
        user_id=user_id,
    ).first()

    if not membership or membership.status != MembershipStatus.ACTIVE:
        return UserProductAccessResult(
            has_access=False,
            denial_code="MEMBERSHIP_INELIGIBLE",
            denial_reason="User holds no active membership in this organization.",
            assignment_status=None,
            is_subscription_eligible=False,
            enabled_module_ids=[],
            enabled_module_codes=[],
        )

    # 4. Temporal Subscription Check
    try:
        subscription = get_temporally_eligible_subscription(
            organization_id=organization_id,
            at_time=at_time,
        )
    except MultipleActiveSubscriptionsError:
        subscription = None

    if not subscription:
        return UserProductAccessResult(
            has_access=False,
            denial_code="SUBSCRIPTION_UNAVAILABLE",
            denial_reason="No open, temporally eligible subscription exists for this organization.",
            assignment_status=None,
            is_subscription_eligible=False,
            enabled_module_ids=[],
            enabled_module_codes=[],
        )

    # 5. Catalog Product Check
    product = Product.objects.filter(id=product_id).first()
    if not product or product.status != ProductStatus.ACTIVE:
        return UserProductAccessResult(
            has_access=False,
            denial_code="PRODUCT_INACTIVE",
            denial_reason="Target catalog product is not in active status.",
            assignment_status=None,
            is_subscription_eligible=True,
            enabled_module_ids=[],
            enabled_module_codes=[],
        )

    # 6. Subscription Product Entitlement Snapshot Check
    if not subscription.product_entitlements.filter(product_id=product_id).exists():
        return UserProductAccessResult(
            has_access=False,
            denial_code="PRODUCT_NOT_ENTITLED",
            denial_reason="Product is not entitled in active subscription snapshot.",
            assignment_status=None,
            is_subscription_eligible=True,
            enabled_module_ids=[],
            enabled_module_codes=[],
        )

    # 7. UserProductAssignment Check
    assignment = (
        UserProductAssignment.objects.filter(
            organization_id=organization_id,
            user_id=user_id,
            product_id=product_id,
        )
        .exclude(status=AssignmentStatus.REVOKED)
        .first()
    )

    if not assignment:
        return UserProductAccessResult(
            has_access=False,
            denial_code="ASSIGNMENT_NOT_FOUND",
            denial_reason="No open product assignment exists for this user and product.",
            assignment_status=None,
            is_subscription_eligible=True,
            enabled_module_ids=[],
            enabled_module_codes=[],
        )

    # 8. Assignment Status Check
    if assignment.status != AssignmentStatus.ACTIVE:
        return UserProductAccessResult(
            has_access=False,
            denial_code="ASSIGNMENT_SUSPENDED",
            denial_reason=f"User product assignment status is '{assignment.status}'.",
            assignment_status=assignment.status,
            is_subscription_eligible=True,
            enabled_module_ids=[],
            enabled_module_codes=[],
        )

    # 9. All Core Checks Passed -> Resolve Enabled Modules
    # Modules must be:
    # - is_enabled=True on UserModuleAssignment
    # - CatalogStatus.ACTIVE on ProductModule
    # - Present in subscription.module_entitlements snapshot
    entitled_sub_module_ids = set(
        subscription.module_entitlements.values_list("module_id", flat=True)
    )

    active_user_modules = (
        assignment.module_assignments.filter(
            is_enabled=True,
            module__status=CatalogStatus.ACTIVE,
            module_id__in=entitled_sub_module_ids,
        )
        .select_related("module")
        .order_by("module__code", "module_id")
    )

    enabled_ids = [uma.module_id for uma in active_user_modules]
    enabled_codes = [uma.module.code for uma in active_user_modules]

    return UserProductAccessResult(
        has_access=True,
        denial_code=None,
        denial_reason=None,
        assignment_status=assignment.status,
        is_subscription_eligible=True,
        enabled_module_ids=enabled_ids,
        enabled_module_codes=enabled_codes,
    )
