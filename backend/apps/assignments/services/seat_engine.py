"""Seat Engine and Quota Resolution Services.

Provides deterministic seat-pool resolution, quota normalization,
status-aware temporal subscription boundaries, and seat-counting queries.
"""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
import uuid
from typing import Any

from django.db.models import Q
from django.utils import timezone

from apps.assignments.models import AssignmentStatus, UserProductAssignment
from apps.assignments.services.exceptions import (
    InvalidSeatQuotaConfigError,
    MultipleActiveSubscriptionsError,
    ProductNotEntitledError,
    SeatQuotaUnconfiguredError,
)
from apps.subscriptions.models import OrganizationSubscription, SubscriptionStatus

CANONICAL_SEAT_QUOTA_KEYS = frozenset(["seats", "max_seats"])


@dataclass(frozen=True)
class SeatQuotaResolution:
    """Resolved seat capacity, scope, and consumption metrics for a product."""

    subscription_id: uuid.UUID
    quota_entitlement_id: uuid.UUID
    pool_scope: str  # "product" | "plan"
    pool_key: str  # e.g. "product:<uuid>" or "plan:<code>"
    quota_key: str  # "seats" | "max_seats"
    limit_type: str  # "numeric" | "unlimited"
    total_limit: int | None  # None if unlimited
    consumed_seats: int
    available_seats: int | None  # None if unlimited
    is_capacity_available: bool  # True if unlimited or available_seats > 0
    over_allocated_amount: int  # max(0, consumed - total_limit) if numeric else 0
    governed_product_ids: list[uuid.UUID]


def get_temporally_eligible_subscription(
    organization_id: uuid.UUID,
    at_time: datetime | None = None,
    for_update: bool = False,
) -> OrganizationSubscription | None:
    """Resolve the single open, temporally eligible subscription for an organization.

    Temporal boundaries:
    - Trialing: trial_started_at <= at_time < trial_ends_at
    - Active: current_period_start <= at_time < current_period_end
    - Suspended, cancelled, expired, future-starting, and boundary-ended subscriptions are ineligible.
    - Multiple active/eligible subscriptions fail closed with MultipleActiveSubscriptionsError.
    """
    if at_time is None:
        at_time = timezone.now()

    qs = OrganizationSubscription.objects.filter(
        Q(
            organization_id=organization_id,
            status=SubscriptionStatus.TRIALING,
            trial_started_at__lte=at_time,
            trial_ends_at__gt=at_time,
        )
        | Q(
            organization_id=organization_id,
            status=SubscriptionStatus.ACTIVE,
            current_period_start__lte=at_time,
            current_period_end__gt=at_time,
        )
    )
    if for_update:
        qs = qs.select_for_update()

    eligible_subs = list(qs)

    if not eligible_subs:
        return None

    if len(eligible_subs) > 1:
        raise MultipleActiveSubscriptionsError(
            f"Multiple ({len(eligible_subs)}) active subscriptions detected for organization '{organization_id}'."
        )

    return eligible_subs[0]


def normalize_seat_limit(
    *,
    limit_type: str,
    limit_value: Any,
    is_hard_limit: bool,
) -> int | None:
    """Normalize a seat quota limit into a non-negative integer or None for unlimited.

    Rules:
    - is_hard_limit must be True (Phase 2F fails closed on soft seat quotas).
    - limit_type 'unlimited' requires limit_value is None.
    - limit_type 'numeric' requires limit_value is non-null integer or integral Decimal.
    - Negative, fractional, malformed, or unsupported limit types fail closed.
    """
    if not is_hard_limit:
        raise InvalidSeatQuotaConfigError("Soft seat quotas (is_hard_limit=False) fail closed in Phase 2F.")

    if limit_type == "unlimited":
        if limit_value is not None:
            raise InvalidSeatQuotaConfigError("Unlimited seat quota cannot have a non-null limit_value.")
        return None

    if limit_type == "numeric":
        if limit_value is None:
            raise InvalidSeatQuotaConfigError("Numeric seat quota must have a non-null limit_value.")

        if isinstance(limit_value, Decimal):
            if limit_value % 1 != 0:
                raise InvalidSeatQuotaConfigError(f"Non-integral Decimal seat limit '{limit_value}' is not permitted.")
            int_val = int(limit_value)
        elif isinstance(limit_value, float):
            if not limit_value.is_integer():
                raise InvalidSeatQuotaConfigError(f"Fractional seat limit '{limit_value}' is not permitted.")
            int_val = int(limit_value)
        elif isinstance(limit_value, str):
            try:
                dec = Decimal(limit_value.strip())
                if dec % 1 != 0:
                    raise InvalidSeatQuotaConfigError(f"Fractional string seat limit '{limit_value}' is not permitted.")
                int_val = int(dec)
            except Exception as e:
                if isinstance(e, InvalidSeatQuotaConfigError):
                    raise
                raise InvalidSeatQuotaConfigError(f"Malformed seat limit string '{limit_value}'.")
        elif isinstance(limit_value, int):
            int_val = limit_value
        else:
            raise InvalidSeatQuotaConfigError(f"Unsupported limit_value type '{type(limit_value).__name__}'.")

        if int_val < 0:
            raise InvalidSeatQuotaConfigError(f"Negative seat limit '{int_val}' is not permitted.")

        return int_val

    raise InvalidSeatQuotaConfigError(f"Unsupported quota limit_type '{limit_type}'.")


def resolve_seat_pool(
    *,
    organization_id: uuid.UUID,
    product_id: uuid.UUID,
    subscription: OrganizationSubscription,
) -> SeatQuotaResolution:
    """Resolve the governing seat pool and capacity metrics for a product.

    Precedence:
    1. Product-specific quota (quota_key in ('seats', 'max_seats') and product_id=product_id).
    2. Plan-shared quota fallback (quota_key in ('seats', 'max_seats') and product_id is None).
    3. Missing quota -> SeatQuotaUnconfiguredError.
    4. Duplicate or ambiguous quotas at the same scope -> InvalidSeatQuotaConfigError.
    5. Unrelated quota keys are ignored.
    """
    # 1. Product must be entitled in the subscription snapshot
    if not subscription.product_entitlements.filter(product_id=product_id).exists():
        raise ProductNotEntitledError(
            f"Product '{product_id}' is not entitled under subscription '{subscription.id}'."
        )

    # 2. Check product-specific seat quota
    product_quotas = list(
        subscription.quota_entitlements.filter(
            quota_key__in=CANONICAL_SEAT_QUOTA_KEYS,
            product_id=product_id,
        )
    )

    if len(product_quotas) > 1:
        raise InvalidSeatQuotaConfigError(
            f"Duplicate or ambiguous seat quota configuration at product scope for product '{product_id}'."
        )

    if len(product_quotas) == 1:
        quota = product_quotas[0]
        total_limit = normalize_seat_limit(
            limit_type=quota.limit_type,
            limit_value=quota.limit_value,
            is_hard_limit=quota.is_hard_limit,
        )

        consumed_seats = UserProductAssignment.objects.filter(
            organization_id=organization_id,
            product_id=product_id,
            status__in=[AssignmentStatus.ACTIVE, AssignmentStatus.SUSPENDED],
        ).count()

        if total_limit is None:
            available_seats = None
            is_capacity_available = True
            over_allocated_amount = 0
        else:
            available_seats = max(0, total_limit - consumed_seats)
            is_capacity_available = consumed_seats < total_limit
            over_allocated_amount = max(0, consumed_seats - total_limit)

        return SeatQuotaResolution(
            subscription_id=subscription.id,
            quota_entitlement_id=quota.id,
            pool_scope="product",
            pool_key=f"product:{product_id}",
            quota_key=quota.quota_key,
            limit_type=quota.limit_type,
            total_limit=total_limit,
            consumed_seats=consumed_seats,
            available_seats=available_seats,
            is_capacity_available=is_capacity_available,
            over_allocated_amount=over_allocated_amount,
            governed_product_ids=[product_id],
        )

    # 3. Fallback to plan-shared seat quota
    plan_quotas = list(
        subscription.quota_entitlements.filter(
            quota_key__in=CANONICAL_SEAT_QUOTA_KEYS,
            product_id__isnull=True,
        )
    )

    if len(plan_quotas) > 1:
        raise InvalidSeatQuotaConfigError(
            f"Duplicate or ambiguous seat quota configuration at plan scope for subscription '{subscription.id}'."
        )

    if len(plan_quotas) == 1:
        quota = plan_quotas[0]
        total_limit = normalize_seat_limit(
            limit_type=quota.limit_type,
            limit_value=quota.limit_value,
            is_hard_limit=quota.is_hard_limit,
        )

        # Governed products = all entitled products in subscription minus those with product overrides
        product_override_ids = set(
            subscription.quota_entitlements.filter(
                quota_key__in=CANONICAL_SEAT_QUOTA_KEYS,
                product_id__isnull=False,
            ).values_list("product_id", flat=True)
        )

        governed_product_ids = sorted(
            subscription.product_entitlements.exclude(
                product_id__in=product_override_ids,
            ).values_list("product_id", flat=True)
        )

        consumed_seats = UserProductAssignment.objects.filter(
            organization_id=organization_id,
            product_id__in=governed_product_ids,
            status__in=[AssignmentStatus.ACTIVE, AssignmentStatus.SUSPENDED],
        ).count()

        if total_limit is None:
            available_seats = None
            is_capacity_available = True
            over_allocated_amount = 0
        else:
            available_seats = max(0, total_limit - consumed_seats)
            is_capacity_available = consumed_seats < total_limit
            over_allocated_amount = max(0, consumed_seats - total_limit)

        return SeatQuotaResolution(
            subscription_id=subscription.id,
            quota_entitlement_id=quota.id,
            pool_scope="plan",
            pool_key=f"plan:{subscription.plan_code_snapshot}",
            quota_key=quota.quota_key,
            limit_type=quota.limit_type,
            total_limit=total_limit,
            consumed_seats=consumed_seats,
            available_seats=available_seats,
            is_capacity_available=is_capacity_available,
            over_allocated_amount=over_allocated_amount,
            governed_product_ids=governed_product_ids,
        )

    # 4. No quota configured at either scope
    raise SeatQuotaUnconfiguredError(
        f"No seat quota configured for product '{product_id}' under plan '{subscription.plan_code_snapshot}'."
    )


# Alias for canonical architecture naming
resolve_governing_seat_pool = resolve_seat_pool

