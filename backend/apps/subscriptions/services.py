"""VibeConnect Subscriptions Domain Services (Phase 2C Stage 2).

Implements the lifecycle management, entitlement snapshots, idempotent reconciliation,
and effective access determination for organization subscriptions with deterministic locking.
"""

from datetime import datetime
from decimal import Decimal
from typing import Any
import uuid

from django.db import transaction
from django.utils import timezone

from apps.auditlog.models import AuditAction, AuditOperationSource, AuditTargetType
from apps.auditlog.services import record_audit_event
from apps.entitlements.models import EntitlementStatus, OrganizationProductEntitlement
from apps.organizations.models import Organization, OrganizationStatus
from apps.plans.models import PlanPrice, PlanVersion, PlanVersionStatus, QuotaScope
from apps.subscriptions.models import (
    OrganizationSubscription,
    SubscriptionCapabilityEntitlement,
    SubscriptionModuleEntitlement,
    SubscriptionProductEntitlement,
    SubscriptionQuotaEntitlement,
    SubscriptionStatus,
)
from apps.subscriptions.utils import (
    calculate_period_end,
    calculate_trial_end,
)


class SubscriptionServiceError(Exception):
    """Base exception for subscription domain service errors."""
    pass


class SubscriptionValidationError(SubscriptionServiceError):
    """Raised when domain validation rules or constraints fail."""
    pass


class SubscriptionNotFoundError(SubscriptionServiceError):
    """Raised when a subscription record cannot be found."""
    pass


# ---------------------------------------------------------------------------
# Entitlement Reconciliation (Add-only Idempotent Snapshots)
# ---------------------------------------------------------------------------

def _reconcile_subscription_snapshots(subscription: OrganizationSubscription) -> int:
    """Add-only, idempotent reconciliation of subscription entitlement snapshots.

    Populates missing product, module, capability, and quota snapshots strictly from
    the subscription's bound PlanVersion without mutating or deleting existing records.
    Direct grants (OrganizationProductEntitlement) are never touched.

    Returns the number of repaired (newly created) snapshot rows.
    """
    repaired_count = 0
    plan_version = subscription.plan_version

    # 1. Product entitlements snapshot
    for plan_prod in plan_version.packaged_products.select_related("product").all():
        if not SubscriptionProductEntitlement.objects.filter(
            subscription=subscription,
            product=plan_prod.product,
        ).exists():
            SubscriptionProductEntitlement.objects.create(
                subscription=subscription,
                organization=subscription.organization,
                product=plan_prod.product,
                plan_product=plan_prod,
                product_code_snapshot=plan_prod.product.code,
                product_name_snapshot=plan_prod.product.name,
            )
            repaired_count += 1

    # 2. Module entitlements snapshot
    for plan_mod in plan_version.packaged_modules.select_related("module").all():
        if not SubscriptionModuleEntitlement.objects.filter(
            subscription=subscription,
            module=plan_mod.module,
        ).exists():
            SubscriptionModuleEntitlement.objects.create(
                subscription=subscription,
                organization=subscription.organization,
                module=plan_mod.module,
                plan_module=plan_mod,
                module_code_snapshot=plan_mod.module.code,
                module_name_snapshot=plan_mod.module.name,
            )
            repaired_count += 1

    # 3. Capability entitlements snapshot
    for plan_cap in plan_version.packaged_capabilities.select_related("capability").all():
        if not SubscriptionCapabilityEntitlement.objects.filter(
            subscription=subscription,
            capability=plan_cap.capability,
        ).exists():
            SubscriptionCapabilityEntitlement.objects.create(
                subscription=subscription,
                organization=subscription.organization,
                capability=plan_cap.capability,
                plan_capability=plan_cap,
                capability_code_snapshot=plan_cap.capability.code,
                capability_name_snapshot=plan_cap.capability.name,
            )
            repaired_count += 1

    # 4. Quota entitlements snapshot
    for plan_q in plan_version.quotas.select_related(
        "plan_product__product",
        "plan_module__module",
        "plan_capability__capability",
    ).all():
        target_prod = plan_q.plan_product.product if plan_q.plan_product else None
        target_mod = plan_q.plan_module.module if plan_q.plan_module else None
        target_cap = plan_q.plan_capability.capability if plan_q.plan_capability else None

        q_filter = {
            "subscription": subscription,
            "quota_key": plan_q.quota_key,
            "scope": plan_q.scope,
        }
        if plan_q.scope == QuotaScope.PRODUCT:
            q_filter["product"] = target_prod
        elif plan_q.scope == QuotaScope.MODULE:
            q_filter["module"] = target_mod
        elif plan_q.scope == QuotaScope.CAPABILITY:
            q_filter["capability"] = target_cap

        if not SubscriptionQuotaEntitlement.objects.filter(**q_filter).exists():
            target_code = target_prod.code if target_prod else (target_mod.code if target_mod else (target_cap.code if target_cap else ""))
            target_name = target_prod.name if target_prod else (target_mod.name if target_mod else (target_cap.name if target_cap else ""))

            SubscriptionQuotaEntitlement.objects.create(
                subscription=subscription,
                organization=subscription.organization,
                plan_quota=plan_q,
                quota_key=plan_q.quota_key,
                name=plan_q.name,
                scope=plan_q.scope,
                product=target_prod,
                module=target_mod,
                capability=target_cap,
                target_code_snapshot=target_code,
                target_name_snapshot=target_name,
                limit_type=plan_q.limit_type,
                limit_value=plan_q.limit_value,
                unit=plan_q.unit,
                is_hard_limit=plan_q.is_hard_limit,
                reset_period=plan_q.reset_period,
            )
            repaired_count += 1

    return repaired_count


def check_and_audit_seat_over_allocation(
    *,
    subscription: OrganizationSubscription,
    detection_context: str = "reconciliation",
    actor: Any = None,
    correlation_id: uuid.UUID | str | None = None,
    operation_source: str | None = None,
) -> bool:
    """Detect and record plan-shared seat over-allocation for a subscription.

    Returns True if over-allocation was detected and recorded, False otherwise.
    """
    from apps.assignments.services.seat_engine import (
        CANONICAL_SEAT_QUOTA_KEYS,
        resolve_seat_pool,
    )

    has_plan_quota = subscription.quota_entitlements.filter(
        quota_key__in=CANONICAL_SEAT_QUOTA_KEYS,
        product_id__isnull=True,
    ).exists()
    if not has_plan_quota:
        return False

    product_override_ids = set(
        subscription.quota_entitlements.filter(
            quota_key__in=CANONICAL_SEAT_QUOTA_KEYS,
            product_id__isnull=False,
        ).values_list("product_id", flat=True)
    )

    first_governed_pe = (
        subscription.product_entitlements.exclude(
            product_id__in=product_override_ids
        )
        .first()
    )
    if not first_governed_pe:
        return False

    try:
        resolution = resolve_seat_pool(
            organization_id=subscription.organization_id,
            product_id=first_governed_pe.product_id,
            subscription=subscription,
        )
    except Exception:
        return False

    if resolution.pool_scope == "plan" and resolution.over_allocated_amount > 0:
        if actor is None:
            from apps.identity.services import get_system_service_actor
            actor = get_system_service_actor()
            effective_source = operation_source or AuditOperationSource.INTEGRATION
        else:
            effective_source = operation_source or (
                AuditOperationSource.INTEGRATION
                if getattr(actor, "email", "") == "system@vibeconnect.internal"
                else AuditOperationSource.INTERACTIVE
            )

        corr_id = correlation_id or uuid.uuid4()

        record_audit_event(
            action=AuditAction.SEAT_OVER_ALLOCATION_DETECTED,
            target_type=AuditTargetType.SUBSCRIPTION,
            target_id=subscription.id,
            target_repr=f"Subscription {subscription.id} Seat Pool",
            actor=actor,
            organization_id=subscription.organization_id,
            operation_source=effective_source,
            correlation_id=corr_id,
            metadata={
                "organization_code": subscription.organization.code,
                "pool_scope": resolution.pool_scope,
                "pool_key": resolution.pool_key,
                "governed_product_ids": [str(pid) for pid in sorted(resolution.governed_product_ids, key=str)],
                "total_limit": resolution.total_limit,
                "consumed_seats": resolution.consumed_seats,
                "over_allocated_amount": resolution.over_allocated_amount,
                "detection_context": detection_context,
            },
        )
        return True

    return False


@transaction.atomic
def reconcile_subscription_entitlements(
    *,
    subscription_id: uuid.UUID | str,
    actor: Any,
    correlation_id: uuid.UUID | str | None = None,
    operation_source: str | None = None,
) -> int:
    """Perform on-demand idempotent reconciliation of subscription entitlement snapshots.

    Emits SUBSCRIPTION_RECONCILED audit event only when missing snapshots were repaired (repaired_count > 0).
    No-op reconciliation emits no audit event.
    Checks and records plan-shared seat over-allocation if present.
    """
    try:
        sub = (
            OrganizationSubscription.objects
            .select_for_update()
            .select_related("organization", "plan_version")
            .get(pk=subscription_id)
        )
    except OrganizationSubscription.DoesNotExist:
        raise SubscriptionNotFoundError("Subscription not found.")

    Organization.objects.select_for_update().get(pk=sub.organization_id)

    repaired_count = _reconcile_subscription_snapshots(sub)

    if repaired_count > 0:
        record_audit_event(
            action=AuditAction.SUBSCRIPTION_RECONCILED,
            target_type=AuditTargetType.SUBSCRIPTION,
            target_id=sub.id,
            target_repr=f"Subscription {sub.id}",
            actor=actor,
            organization_id=sub.organization_id,
            operation_source=operation_source or AuditOperationSource.INTERACTIVE,
            correlation_id=correlation_id,
            metadata={
                "organization_code": sub.organization.code,
                "repaired_count": repaired_count,
            },
        )

    check_and_audit_seat_over_allocation(
        subscription=sub,
        detection_context="reconciliation",
        actor=actor,
        correlation_id=correlation_id,
        operation_source=operation_source,
    )

    return repaired_count


# ---------------------------------------------------------------------------
# Subscription Lifecycle Services
# ---------------------------------------------------------------------------

@transaction.atomic
def start_subscription_trial(
    *,
    organization_id: uuid.UUID | str,
    plan_version_id: uuid.UUID | str,
    plan_price_id: uuid.UUID | str,
    actor: Any,
    trial_days: int = 14,
    change_reason: str = "",
) -> OrganizationSubscription:
    """Create a new trialing subscription with immutable commercial snapshots and trial boundaries."""
    # 1. Lock Organization
    try:
        org = Organization.objects.select_for_update().get(pk=organization_id)
    except Organization.DoesNotExist:
        raise SubscriptionNotFoundError("Organization not found.")

    if org.status == OrganizationStatus.RETIRED:
        raise SubscriptionValidationError("Cannot create subscription for a retired organization.")

    # 2. Check for existing open subscription (Org -> Subscription lock)
    open_sub = (
        OrganizationSubscription.objects
        .select_for_update()
        .filter(
            organization=org,
            status__in=[
                SubscriptionStatus.TRIALING,
                SubscriptionStatus.ACTIVE,
                SubscriptionStatus.SUSPENDED,
            ],
        )
        .first()
    )
    if open_sub:
        raise SubscriptionValidationError(
            f"Organization '{org.code}' already has an open subscription ({open_sub.id}) with status '{open_sub.status}'."
        )

    # 3. Lock PlanVersion and PlanPrice
    try:
        plan_version = (
            PlanVersion.objects
            .select_related("plan")
            .get(pk=plan_version_id)
        )
    except PlanVersion.DoesNotExist:
        raise SubscriptionValidationError("Plan version not found.")

    if plan_version.status != PlanVersionStatus.ACTIVE:
        raise SubscriptionValidationError(
            f"Cannot subscribe to plan version with status '{plan_version.status}'; must be 'active'."
        )

    try:
        plan_price = PlanPrice.objects.get(pk=plan_price_id, plan_version=plan_version)
    except PlanPrice.DoesNotExist:
        raise SubscriptionValidationError("Plan price does not belong to the selected plan version.")

    # 4. Compute trial timeline
    now = timezone.now()
    trial_ends = calculate_trial_end(now, trial_days)

    # 5. Create Subscription
    subscription = OrganizationSubscription.objects.create(
        organization=org,
        plan_version=plan_version,
        plan_price=plan_price,
        plan_code_snapshot=plan_version.plan.code,
        plan_name_snapshot=plan_version.plan.name,
        version_number_snapshot=plan_version.version,
        billing_interval=plan_price.billing_interval,
        currency=plan_price.currency,
        amount=plan_price.amount,
        started_as_trial=True,
        trial_started_at=now,
        trial_ends_at=trial_ends,
        status=SubscriptionStatus.TRIALING,
        change_reason=change_reason,
        created_by=actor,
        updated_by=actor,
    )

    # 6. Reconcile snapshots on initial creation (emits no reconciliation audit)
    _reconcile_subscription_snapshots(subscription)

    # 7. Record trial started audit event
    record_audit_event(
        action=AuditAction.SUBSCRIPTION_TRIAL_STARTED,
        target_type=AuditTargetType.SUBSCRIPTION,
        target_id=subscription.id,
        target_repr=f"Subscription {subscription.id}",
        actor=actor,
        organization_id=org.id,
        operation_source=AuditOperationSource.INTERACTIVE,
        metadata={
            "organization_code": org.code,
            "plan_code": plan_version.plan.code,
            "plan_version": plan_version.version,
            "trial_days": trial_days,
            "trial_ends_at": trial_ends.isoformat(),
            "status": "trialing",
        },
    )

    return subscription


@transaction.atomic
def create_active_subscription(
    *,
    organization_id: uuid.UUID | str,
    plan_version_id: uuid.UUID | str,
    plan_price_id: uuid.UUID | str,
    actor: Any,
    current_period_start: datetime | None = None,
    change_reason: str = "",
) -> OrganizationSubscription:
    """Create a direct active subscription with immutable commercial snapshots and initial billing period."""
    # 1. Lock Organization
    try:
        org = Organization.objects.select_for_update().get(pk=organization_id)
    except Organization.DoesNotExist:
        raise SubscriptionNotFoundError("Organization not found.")

    if org.status == OrganizationStatus.RETIRED:
        raise SubscriptionValidationError("Cannot create subscription for a retired organization.")

    # 2. Check for existing open subscription
    open_sub = (
        OrganizationSubscription.objects
        .select_for_update()
        .filter(
            organization=org,
            status__in=[
                SubscriptionStatus.TRIALING,
                SubscriptionStatus.ACTIVE,
                SubscriptionStatus.SUSPENDED,
            ],
        )
        .first()
    )
    if open_sub:
        raise SubscriptionValidationError(
            f"Organization '{org.code}' already has an open subscription ({open_sub.id}) with status '{open_sub.status}'."
        )

    # 3. Lock PlanVersion and PlanPrice
    try:
        plan_version = (
            PlanVersion.objects
            .select_related("plan")
            .get(pk=plan_version_id)
        )
    except PlanVersion.DoesNotExist:
        raise SubscriptionValidationError("Plan version not found.")

    if plan_version.status != PlanVersionStatus.ACTIVE:
        raise SubscriptionValidationError(
            f"Cannot subscribe to plan version with status '{plan_version.status}'; must be 'active'."
        )

    try:
        plan_price = PlanPrice.objects.get(pk=plan_price_id, plan_version=plan_version)
    except PlanPrice.DoesNotExist:
        raise SubscriptionValidationError("Plan price does not belong to the selected plan version.")

    # 4. Period dates
    start_dt = current_period_start or timezone.now()
    end_dt = calculate_period_end(start_dt, plan_price.billing_interval)

    # 5. Create Subscription
    subscription = OrganizationSubscription.objects.create(
        organization=org,
        plan_version=plan_version,
        plan_price=plan_price,
        plan_code_snapshot=plan_version.plan.code,
        plan_name_snapshot=plan_version.plan.name,
        version_number_snapshot=plan_version.version,
        billing_interval=plan_price.billing_interval,
        currency=plan_price.currency,
        amount=plan_price.amount,
        started_as_trial=False,
        status=SubscriptionStatus.ACTIVE,
        current_period_start=start_dt,
        current_period_end=end_dt,
        change_reason=change_reason,
        created_by=actor,
        updated_by=actor,
    )

    # 6. Reconcile snapshots on initial creation (emits no reconciliation audit)
    _reconcile_subscription_snapshots(subscription)

    # 7. Record audit event
    record_audit_event(
        action=AuditAction.SUBSCRIPTION_CREATED,
        target_type=AuditTargetType.SUBSCRIPTION,
        target_id=subscription.id,
        target_repr=f"Subscription {subscription.id}",
        actor=actor,
        organization_id=org.id,
        operation_source=AuditOperationSource.INTERACTIVE,
        metadata={
            "organization_code": org.code,
            "plan_code": plan_version.plan.code,
            "plan_version": plan_version.version,
            "billing_interval": plan_price.billing_interval,
            "currency": plan_price.currency,
            "amount": f"{plan_price.amount:.2f}",
            "status": "active",
        },
    )

    return subscription


@transaction.atomic
def convert_trial_to_active(
    *,
    subscription_id: uuid.UUID | str,
    actor: Any,
) -> OrganizationSubscription:
    """Convert an existing trialing subscription to active and establish its active billing period."""
    # 1. Lock Org -> Subscription
    try:
        sub = (
            OrganizationSubscription.objects
            .select_for_update()
            .select_related("organization", "plan_version", "plan_price")
            .get(pk=subscription_id)
        )
    except OrganizationSubscription.DoesNotExist:
        raise SubscriptionNotFoundError("Subscription not found.")

    org = Organization.objects.select_for_update().get(pk=sub.organization_id)
    if org.status == OrganizationStatus.RETIRED:
        raise SubscriptionValidationError("Cannot activate subscription for a retired organization.")

    if sub.status != SubscriptionStatus.TRIALING:
        raise SubscriptionValidationError(
            f"Only trialing subscriptions can be converted to active (current status: '{sub.status}')."
        )

    # 2. Establish period
    now = timezone.now()
    period_end = calculate_period_end(now, sub.billing_interval)

    sub.status = SubscriptionStatus.ACTIVE
    sub.current_period_start = now
    sub.current_period_end = period_end
    sub.updated_by = actor
    sub.save(update_fields=["status", "current_period_start", "current_period_end", "updated_by", "updated_at"])

    # 3. Record audit event
    record_audit_event(
        action=AuditAction.SUBSCRIPTION_TRIAL_CONVERTED,
        target_type=AuditTargetType.SUBSCRIPTION,
        target_id=sub.id,
        target_repr=f"Subscription {sub.id}",
        actor=actor,
        organization_id=org.id,
        operation_source=AuditOperationSource.INTERACTIVE,
        metadata={
            "organization_code": org.code,
            "plan_code": sub.plan_code_snapshot,
            "plan_version": sub.version_number_snapshot,
            "billing_interval": sub.billing_interval,
            "currency": sub.currency,
            "amount": f"{sub.amount:.2f}",
            "previous_status": "trialing",
            "resulting_status": "active",
        },
    )

    return sub


def _expire_single_trial(
    subscription: OrganizationSubscription,
    actor: Any = None,
) -> OrganizationSubscription:
    """Private helper to expire a single trialing subscription."""
    if subscription.status != SubscriptionStatus.TRIALING:
        raise SubscriptionValidationError(
            f"Only trialing subscriptions can expire (current status: '{subscription.status}')."
        )
    if not subscription.started_as_trial:
        raise SubscriptionValidationError("Only subscriptions started as trial can expire.")

    now = timezone.now()
    subscription.status = SubscriptionStatus.EXPIRED
    subscription.ended_at = now
    if actor is not None:
        subscription.updated_by = actor
        subscription.save(update_fields=["status", "ended_at", "updated_by", "updated_at"])
    else:
        subscription.save(update_fields=["status", "ended_at", "updated_at"])

    record_actor = actor or subscription.updated_by
    if record_actor and getattr(record_actor, "is_platform_owner", False):
        record_audit_event(
            action=AuditAction.SUBSCRIPTION_TRIAL_EXPIRED,
            target_type=AuditTargetType.SUBSCRIPTION,
            target_id=subscription.id,
            target_repr=f"Subscription {subscription.id}",
            actor=record_actor,
            organization_id=subscription.organization_id,
            operation_source=AuditOperationSource.INTERACTIVE,
            metadata={
                "organization_code": subscription.organization.code,
                "plan_code": subscription.plan_code_snapshot,
                "plan_version": subscription.version_number_snapshot,
                "previous_status": "trialing",
                "resulting_status": "expired",
            },
        )

    return subscription


@transaction.atomic
def expire_trial_subscriptions(*, actor: Any = None) -> int:
    """Idempotent batch service to expire overdue trial subscriptions.

    Returns the count of successfully expired subscriptions.
    """
    now = timezone.now()
    overdue_trials = (
        OrganizationSubscription.objects
        .select_for_update()
        .select_related("organization", "plan_version")
        .filter(
            status=SubscriptionStatus.TRIALING,
            started_as_trial=True,
            trial_ends_at__lte=now,
        )
        .order_by("created_at")
    )

    expired_count = 0
    for trial in overdue_trials:
        _expire_single_trial(trial, actor=actor)
        expired_count += 1

    return expired_count


@transaction.atomic
def suspend_subscription(
    *,
    subscription_id: uuid.UUID | str,
    actor: Any,
    reason: str = "",
) -> OrganizationSubscription:
    """Suspend an active subscription with a documented suspension reason."""
    try:
        sub = (
            OrganizationSubscription.objects
            .select_for_update()
            .select_related("organization")
            .get(pk=subscription_id)
        )
    except OrganizationSubscription.DoesNotExist:
        raise SubscriptionNotFoundError("Subscription not found.")

    Organization.objects.select_for_update().get(pk=sub.organization_id)

    if sub.status != SubscriptionStatus.ACTIVE:
        raise SubscriptionValidationError(
            f"Cannot suspend subscription with status '{sub.status}'; must be 'active'."
        )

    sub.status = SubscriptionStatus.SUSPENDED
    sub.suspension_reason = reason
    sub.updated_by = actor
    sub.save(update_fields=["status", "suspension_reason", "updated_by", "updated_at"])

    record_audit_event(
        action=AuditAction.SUBSCRIPTION_SUSPENDED,
        target_type=AuditTargetType.SUBSCRIPTION,
        target_id=sub.id,
        target_repr=f"Subscription {sub.id}",
        actor=actor,
        organization_id=sub.organization_id,
        operation_source=AuditOperationSource.INTERACTIVE,
        metadata={
            "organization_code": sub.organization.code,
            "plan_code": sub.plan_code_snapshot,
            "plan_version": sub.version_number_snapshot,
            "suspension_reason": reason,
            "previous_status": "active",
            "resulting_status": "suspended",
        },
    )

    return sub


@transaction.atomic
def reactivate_subscription(
    *,
    subscription_id: uuid.UUID | str,
    actor: Any,
) -> OrganizationSubscription:
    """Reactivate a suspended subscription."""
    try:
        sub = (
            OrganizationSubscription.objects
            .select_for_update()
            .select_related("organization")
            .get(pk=subscription_id)
        )
    except OrganizationSubscription.DoesNotExist:
        raise SubscriptionNotFoundError("Subscription not found.")

    org = Organization.objects.select_for_update().get(pk=sub.organization_id)
    if org.status == OrganizationStatus.RETIRED:
        raise SubscriptionValidationError("Cannot reactivate subscription for a retired organization.")

    if sub.status != SubscriptionStatus.SUSPENDED:
        raise SubscriptionValidationError(
            f"Cannot reactivate subscription with status '{sub.status}'; must be 'suspended'."
        )

    sub.status = SubscriptionStatus.ACTIVE
    sub.suspension_reason = ""
    sub.updated_by = actor
    sub.save(update_fields=["status", "suspension_reason", "updated_by", "updated_at"])

    record_audit_event(
        action=AuditAction.SUBSCRIPTION_REACTIVATED,
        target_type=AuditTargetType.SUBSCRIPTION,
        target_id=sub.id,
        target_repr=f"Subscription {sub.id}",
        actor=actor,
        organization_id=sub.organization_id,
        operation_source=AuditOperationSource.INTERACTIVE,
        metadata={
            "organization_code": sub.organization.code,
            "plan_code": sub.plan_code_snapshot,
            "plan_version": sub.version_number_snapshot,
            "previous_status": "suspended",
            "resulting_status": "active",
        },
    )

    return sub


@transaction.atomic
def cancel_subscription(
    *,
    subscription_id: uuid.UUID | str,
    actor: Any,
    reason: str = "",
) -> OrganizationSubscription:
    """Cancel an open subscription and mark it terminal."""
    try:
        sub = (
            OrganizationSubscription.objects
            .select_for_update()
            .select_related("organization")
            .get(pk=subscription_id)
        )
    except OrganizationSubscription.DoesNotExist:
        raise SubscriptionNotFoundError("Subscription not found.")

    Organization.objects.select_for_update().get(pk=sub.organization_id)

    if sub.status not in (SubscriptionStatus.TRIALING, SubscriptionStatus.ACTIVE, SubscriptionStatus.SUSPENDED):
        raise SubscriptionValidationError(
            f"Cannot cancel closed subscription with status '{sub.status}'."
        )

    now = timezone.now()
    prev_status = sub.status
    sub.status = SubscriptionStatus.CANCELLED
    sub.cancelled_at = now
    sub.ended_at = now
    sub.cancellation_reason = reason
    sub.updated_by = actor
    sub.save(update_fields=["status", "cancelled_at", "ended_at", "cancellation_reason", "updated_by", "updated_at"])

    record_audit_event(
        action=AuditAction.SUBSCRIPTION_CANCELLED,
        target_type=AuditTargetType.SUBSCRIPTION,
        target_id=sub.id,
        target_repr=f"Subscription {sub.id}",
        actor=actor,
        organization_id=sub.organization_id,
        operation_source=AuditOperationSource.INTERACTIVE,
        metadata={
            "organization_code": sub.organization.code,
            "plan_code": sub.plan_code_snapshot,
            "plan_version": sub.version_number_snapshot,
            "cancellation_reason": reason,
            "previous_status": prev_status,
            "resulting_status": "cancelled",
        },
    )

    return sub


@transaction.atomic
def change_subscription_plan(
    *,
    subscription_id: uuid.UUID | str,
    new_plan_version_id: uuid.UUID | str,
    new_plan_price_id: uuid.UUID | str,
    actor: Any,
    change_reason: str = "",
    correlation_id: uuid.UUID | str | None = None,
) -> OrganizationSubscription:
    """Perform an immediate plan change by cancelling the predecessor and creating a linked successor."""
    # 1. Lock Org -> Current Subscription
    try:
        current_sub = (
            OrganizationSubscription.objects
            .select_for_update()
            .select_related("organization")
            .get(pk=subscription_id)
        )
    except OrganizationSubscription.DoesNotExist:
        raise SubscriptionNotFoundError("Subscription not found.")

    org = Organization.objects.select_for_update().get(pk=current_sub.organization_id)
    if org.status == OrganizationStatus.RETIRED:
        raise SubscriptionValidationError("Cannot change plan for a retired organization.")

    if current_sub.status not in (SubscriptionStatus.TRIALING, SubscriptionStatus.ACTIVE, SubscriptionStatus.SUSPENDED):
        raise SubscriptionValidationError(
            f"Cannot change plan on terminal subscription (status='{current_sub.status}')."
        )

    # 2. Lock New PlanVersion & PlanPrice
    try:
        new_plan_version = (
            PlanVersion.objects
            .select_related("plan")
            .get(pk=new_plan_version_id)
        )
    except PlanVersion.DoesNotExist:
        raise SubscriptionValidationError("New plan version not found.")

    if new_plan_version.status != PlanVersionStatus.ACTIVE:
        raise SubscriptionValidationError(
            f"Cannot subscribe to non-active plan version (status='{new_plan_version.status}')."
        )

    try:
        new_plan_price = PlanPrice.objects.get(pk=new_plan_price_id, plan_version=new_plan_version)
    except PlanPrice.DoesNotExist:
        raise SubscriptionValidationError("Plan price does not belong to the selected plan version.")

    # 3. Close old subscription
    now = timezone.now()
    prev_plan_code = current_sub.plan_code_snapshot
    prev_plan_version = current_sub.version_number_snapshot

    current_sub.status = SubscriptionStatus.CANCELLED
    current_sub.cancelled_at = now
    current_sub.ended_at = now
    current_sub.cancellation_reason = f"Plan changed to {new_plan_version.plan.code} v{new_plan_version.version}"
    current_sub.updated_by = actor
    current_sub.save(update_fields=["status", "cancelled_at", "ended_at", "cancellation_reason", "updated_by", "updated_at"])

    # 4. Create successor subscription
    period_end = calculate_period_end(now, new_plan_price.billing_interval)
    successor = OrganizationSubscription.objects.create(
        organization=org,
        plan_version=new_plan_version,
        plan_price=new_plan_price,
        previous_subscription=current_sub,
        plan_code_snapshot=new_plan_version.plan.code,
        plan_name_snapshot=new_plan_version.plan.name,
        version_number_snapshot=new_plan_version.version,
        billing_interval=new_plan_price.billing_interval,
        currency=new_plan_price.currency,
        amount=new_plan_price.amount,
        started_as_trial=False,
        status=SubscriptionStatus.ACTIVE,
        current_period_start=now,
        current_period_end=period_end,
        change_reason=change_reason,
        created_by=actor,
        updated_by=actor,
    )

    # 5. Snapshots for successor (emits no reconciliation audit on creation)
    _reconcile_subscription_snapshots(successor)

    # 6. Record plan change audit event
    record_audit_event(
        action=AuditAction.SUBSCRIPTION_PLAN_CHANGED,
        target_type=AuditTargetType.SUBSCRIPTION,
        target_id=successor.id,
        target_repr=f"Subscription {successor.id}",
        actor=actor,
        organization_id=org.id,
        operation_source=AuditOperationSource.INTERACTIVE,
        correlation_id=correlation_id,
        metadata={
            "organization_code": org.code,
            "previous_plan_code": prev_plan_code,
            "previous_plan_version": prev_plan_version,
            "resulting_plan_code": new_plan_version.plan.code,
            "resulting_plan_version": new_plan_version.version,
            "change_reason": change_reason,
        },
    )

    # 7. Check and audit plan-shared seat over-allocation (does not block plan change)
    check_and_audit_seat_over_allocation(
        subscription=successor,
        detection_context="plan_downgrade",
        actor=actor,
        correlation_id=correlation_id,
    )

    return successor


@transaction.atomic
def cancel_open_subscriptions_for_organization(
    *,
    org: Organization,
    actor: Any,
    reason: str = "Organization retired",
) -> list[OrganizationSubscription]:
    """Atomically cancel any open subscriptions for a given organization."""
    cancelled_subs = []
    open_subs = (
        OrganizationSubscription.objects
        .select_for_update()
        .filter(
            organization=org,
            status__in=[
                SubscriptionStatus.TRIALING,
                SubscriptionStatus.ACTIVE,
                SubscriptionStatus.SUSPENDED,
            ],
        )
    )

    now = timezone.now()
    for sub in open_subs:
        prev_status = sub.status
        sub.status = SubscriptionStatus.CANCELLED
        sub.cancelled_at = now
        sub.ended_at = now
        sub.cancellation_reason = reason
        sub.updated_by = actor
        sub.save(update_fields=["status", "cancelled_at", "ended_at", "cancellation_reason", "updated_by", "updated_at"])

        record_audit_event(
            action=AuditAction.SUBSCRIPTION_CANCELLED,
            target_type=AuditTargetType.SUBSCRIPTION,
            target_id=sub.id,
            target_repr=f"Subscription {sub.id}",
            actor=actor,
            organization_id=org.id,
            operation_source=AuditOperationSource.INTERACTIVE,
            metadata={
                "organization_code": org.code,
                "plan_code": sub.plan_code_snapshot,
                "plan_version": sub.version_number_snapshot,
                "cancellation_reason": reason,
                "previous_status": prev_status,
                "resulting_status": "cancelled",
            },
        )
        cancelled_subs.append(sub)

    return cancelled_subs


# ---------------------------------------------------------------------------
# Effective Access Helpers (Read-Only)
# ---------------------------------------------------------------------------

def get_active_subscription(organization_id: uuid.UUID | str) -> OrganizationSubscription | None:
    """Return the current active or trialing subscription for an organization."""
    return (
        OrganizationSubscription.objects
        .filter(
            organization_id=organization_id,
            status__in=[SubscriptionStatus.TRIALING, SubscriptionStatus.ACTIVE],
        )
        .order_by("-created_at")
        .first()
    )


def has_product_access(organization_id: uuid.UUID | str, product_code: str) -> bool:
    """Determine if an organization has effective access to a given product.

    Queries active subscription snapshot or active direct grant (read-only).
    """
    sub = get_active_subscription(organization_id)
    if sub is not None and sub.product_entitlements.filter(product_code_snapshot=product_code).exists():
        return True

    # Check direct grant as fallback (read-only)
    return OrganizationProductEntitlement.objects.filter(
        organization_id=organization_id,
        product__code=product_code,
        status=EntitlementStatus.ACTIVE,
    ).exists()


def has_module_access(
    organization_id: uuid.UUID | str,
    product_code: str,
    module_code: str,
) -> bool:
    """Determine if an organization has effective access to a module within a product."""
    sub = get_active_subscription(organization_id)
    if sub is None:
        return False
    return sub.module_entitlements.filter(
        module_code_snapshot=module_code,
        module__product__code=product_code,
    ).exists()


def has_capability_access(
    organization_id: uuid.UUID | str,
    capability_code: str,
) -> bool:
    """Determine if an organization has effective access to a specific capability."""
    sub = get_active_subscription(organization_id)
    if sub is None:
        return False
    return sub.capability_entitlements.filter(capability_code_snapshot=capability_code).exists()


def get_effective_quota(
    organization_id: uuid.UUID | str,
    quota_key: str,
    scope: str = "plan",
    target_id: uuid.UUID | str | None = None,
) -> SubscriptionQuotaEntitlement | None:
    """Retrieve the effective quota entitlement for an organization."""
    sub = get_active_subscription(organization_id)
    if sub is None:
        return None

    qs = sub.quota_entitlements.filter(quota_key=quota_key, scope=scope)
    if scope == "product" and target_id is not None:
        qs = qs.filter(product_id=target_id)
    elif scope == "module" and target_id is not None:
        qs = qs.filter(module_id=target_id)
    elif scope == "capability" and target_id is not None:
        qs = qs.filter(capability_id=target_id)

    return qs.first()
