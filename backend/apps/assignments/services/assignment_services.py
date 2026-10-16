"""User Product and Module Assignment Services.

Provides transactional domain mutation services for assigning, suspending,
reactivating, revoking user product access, replacing enabled modules, and
cascading lifecycle transitions across organizations and memberships.
"""

from datetime import datetime
from typing import Any
import uuid

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from apps.assignments.models import AssignmentStatus, UserModuleAssignment, UserProductAssignment
from apps.auditlog.models import AuditAction, AuditOperationSource, AuditTargetType
from apps.auditlog.services import record_audit_event
from apps.assignments.services.exceptions import (
    AlreadyAssignedError,
    AssignmentNotFoundError,
    InvalidModuleIdsError,
    InvalidReasonError,
    InvalidStateTransitionError,
    MembershipIneligibleError,
    ModuleNotEntitledError,
    OrganizationNotActiveError,
    ProductInactiveError,
    ProductNotEntitledError,
    SeatLimitExceededError,
    SubscriptionUnavailableError,
    UserDisabledError,
    UserInactiveError,
)
from apps.assignments.services.seat_engine import (
    get_temporally_eligible_subscription,
    resolve_governing_seat_pool,
)
from apps.organizations.models import MembershipStatus, Organization, OrganizationMembership, OrganizationStatus
from apps.product_registry.models import CatalogStatus, Product, ProductModule, ProductStatus

PlatformUser = get_user_model()


def _validate_reason(reason: Any) -> str:
    """Validate that reason is a non-empty string between 1 and 500 characters after trimming."""
    if not isinstance(reason, str):
        raise InvalidReasonError(
            "Reason must be a non-empty string between 1 and 500 characters.",
            code="INVALID_REASON",
        )
    trimmed = reason.strip()
    if not (1 <= len(trimmed) <= 500):
        raise InvalidReasonError(
            "Reason must be between 1 and 500 characters.",
            code="INVALID_REASON",
        )
    return trimmed


def assign_user_to_product(
    *,
    organization_id: uuid.UUID | str,
    user_id: uuid.UUID | str,
    product_id: uuid.UUID | str,
    module_ids: list[uuid.UUID | str] | None = None,
    membership_id: uuid.UUID | str | None = None,
    actor: Any,
    at_time: datetime | None = None,
    correlation_id: uuid.UUID | str | None = None,
    operation_source: str = AuditOperationSource.INTERACTIVE,
) -> UserProductAssignment:
    """Atomically create a new active product seat assignment.

    Deterministic lock and validation sequence:
    1. Lock Organization root (confirm active).
    2. Confirm central user is active and not disabled.
    3. Lock OrganizationSubscription (temporal check).
    4. Lock OrganizationMembership (confirm active, matches org and user).
    5. Check existing non-revoked assignment (reject ALREADY_ASSIGNED before capacity).
    6. Validate product catalog status and subscription snapshot entitlement.
    7. Resolve governing seat pool and check capacity (SEAT_LIMIT_EXCEEDED).
    8. Validate requested module IDs (deduplicate, max 100, catalog-active, in snapshot).
    9. Create UserProductAssignment and UserModuleAssignment rows.
    """
    if actor is None:
        raise ValueError("Authoritative actor is required.")

    clean_org_id = uuid.UUID(str(organization_id))
    clean_user_id = uuid.UUID(str(user_id))
    clean_product_id = uuid.UUID(str(product_id))

    effective_time = at_time or timezone.now()

    with transaction.atomic():
        # 1. Lock Organization root
        try:
            org = Organization.objects.select_for_update().get(id=clean_org_id)
        except Organization.DoesNotExist:
            raise OrganizationNotActiveError(
                f"Organization '{clean_org_id}' not found.",
                code="ORGANIZATION_NOT_ACTIVE",
            )

        if org.status != OrganizationStatus.ACTIVE:
            raise OrganizationNotActiveError(
                f"Organization '{clean_org_id}' is not in active status.",
                code="ORGANIZATION_NOT_ACTIVE",
            )

        # 2. Confirm central user is active and not disabled
        try:
            user = PlatformUser.objects.get(id=clean_user_id)
        except PlatformUser.DoesNotExist:
            raise UserInactiveError(
                f"Platform user '{clean_user_id}' does not exist.",
                code="USER_INACTIVE",
            )

        if user.status == "disabled" or getattr(user, "is_active", True) is False:
            raise UserDisabledError(
                "Central user account is disabled or deactivated.",
                code="USER_DISABLED",
            )

        if user.status != "active":
            raise UserInactiveError(
                f"Central user account is not active (status='{user.status}').",
                code="USER_INACTIVE",
            )

        # 3. Lock OrganizationSubscription
        subscription = get_temporally_eligible_subscription(
            organization_id=clean_org_id,
            at_time=effective_time,
            for_update=True,
        )
        if not subscription:
            raise SubscriptionUnavailableError(
                "No open, temporally eligible subscription exists for this organization.",
                code="SUBSCRIPTION_UNAVAILABLE",
            )

        # 4. Lock OrganizationMembership
        if membership_id is not None:
            clean_membership_id = uuid.UUID(str(membership_id))
        else:
            active_mem = OrganizationMembership.objects.filter(
                organization_id=clean_org_id,
                user_id=clean_user_id,
                status=MembershipStatus.ACTIVE,
            ).first()
            if not active_mem:
                raise MembershipIneligibleError(
                    "User has no active membership in this organization.",
                    code="MEMBERSHIP_INELIGIBLE",
                )
            clean_membership_id = active_mem.id

        try:
            membership = OrganizationMembership.objects.select_for_update().get(id=clean_membership_id)
        except OrganizationMembership.DoesNotExist:
            raise MembershipIneligibleError(
                f"Membership '{clean_membership_id}' does not exist.",
                code="MEMBERSHIP_INELIGIBLE",
            )

        if membership.organization_id != clean_org_id:
            raise MembershipIneligibleError(
                "Membership does not belong to the requested organization.",
                code="MEMBERSHIP_INELIGIBLE",
            )

        if membership.user_id != clean_user_id:
            raise MembershipIneligibleError(
                "Membership does not belong to the requested user.",
                code="MEMBERSHIP_INELIGIBLE",
            )

        if membership.status != MembershipStatus.ACTIVE:
            raise MembershipIneligibleError(
                f"Membership is not active (status='{membership.status}').",
                code="MEMBERSHIP_INELIGIBLE",
            )

        # 5. Check existing non-revoked assignment BEFORE capacity rejection
        existing = (
            UserProductAssignment.objects.select_for_update()
            .filter(
                organization_id=clean_org_id,
                user_id=clean_user_id,
                product_id=clean_product_id,
                status__in=[AssignmentStatus.ACTIVE, AssignmentStatus.SUSPENDED],
            )
            .order_by("id")
            .first()
        )
        if existing:
            raise AlreadyAssignedError(
                f"User already holds an open ({existing.status}) assignment for product '{clean_product_id}'.",
                code="ALREADY_ASSIGNED",
            )

        # 6. Validate product catalog status and snapshot entitlement
        try:
            product = Product.objects.get(id=clean_product_id)
        except Product.DoesNotExist:
            raise ProductInactiveError(
                f"Product '{clean_product_id}' does not exist in catalog.",
                code="PRODUCT_INACTIVE",
            )

        if product.status != ProductStatus.ACTIVE:
            raise ProductInactiveError(
                f"Product '{clean_product_id}' is not active in the catalog (status='{product.status}').",
                code="PRODUCT_INACTIVE",
            )

        if not subscription.product_entitlements.filter(product_id=clean_product_id).exists():
            raise ProductNotEntitledError(
                f"Product '{clean_product_id}' is not entitled under the subscription snapshot.",
                code="PRODUCT_NOT_ENTITLED",
            )

        # 7. Resolve governing seat pool and check capacity
        seat_pool = resolve_governing_seat_pool(
            organization_id=clean_org_id,
            product_id=clean_product_id,
            subscription=subscription,
        )
        if seat_pool.limit_type == "numeric" and not seat_pool.is_capacity_available:
            raise SeatLimitExceededError(
                f"Seat limit exceeded for governing pool '{seat_pool.pool_key}'.",
                code="SEAT_LIMIT_EXCEEDED",
            )

        # 8. Validate requested module IDs
        deduped_module_ids: list[uuid.UUID] = []
        if module_ids:
            seen = set()
            for m in module_ids:
                mid = uuid.UUID(str(m))
                if mid not in seen:
                    seen.add(mid)
                    deduped_module_ids.append(mid)

        if len(deduped_module_ids) > 100:
            raise InvalidModuleIdsError(
                "Maximum 100 module IDs allowed.",
                code="INVALID_MODULE_IDS",
            )

        if deduped_module_ids:
            entitled_sub_module_ids = set(
                subscription.module_entitlements.values_list("module_id", flat=True)
            )
            catalog_modules = {
                mod.id: mod
                for mod in ProductModule.objects.filter(id__in=deduped_module_ids)
            }
            for mid in deduped_module_ids:
                mod = catalog_modules.get(mid)
                if not mod or mod.product_id != clean_product_id or mod.status != CatalogStatus.ACTIVE:
                    raise InvalidModuleIdsError(
                        f"Module '{mid}' is invalid, does not belong to product '{clean_product_id}', or is inactive.",
                        code="INVALID_MODULE_IDS",
                    )
                if mid not in entitled_sub_module_ids:
                    raise ModuleNotEntitledError(
                        f"Module '{mid}' is not entitled under the subscription snapshot.",
                        code="MODULE_NOT_ENTITLED",
                    )

        # 9. Create UserProductAssignment
        assignment = UserProductAssignment(
            organization=org,
            user=user,
            membership=membership,
            product=product,
            status=AssignmentStatus.ACTIVE,
            assigned_at=effective_time,
            created_by=actor,
            updated_by=actor,
        )
        assignment.save()

        # 10. Create UserModuleAssignment rows
        for mid in deduped_module_ids:
            UserModuleAssignment.objects.create(
                assignment=assignment,
                module_id=mid,
                is_enabled=True,
            )

        # 11. Record audit event
        assigned_module_codes = sorted(
            list(
                ProductModule.objects.filter(id__in=deduped_module_ids).values_list("code", flat=True)
            )
        )
        consumed_after = seat_pool.consumed_seats + 1
        available_after = None if seat_pool.total_limit is None else max(0, seat_pool.total_limit - consumed_after)

        record_audit_event(
            action=AuditAction.USER_PRODUCT_ASSIGNED,
            target_type=AuditTargetType.USER_PRODUCT_ASSIGNMENT,
            target_id=assignment.id,
            target_repr=f"Assignment {assignment.id} ({product.code} -> {user.email})",
            actor=actor,
            organization_id=org.id,
            operation_source=operation_source,
            correlation_id=correlation_id,
            metadata={
                "organization_code": org.code,
                "user_id": str(user.id),
                "user_email": user.email,
                "product_id": str(product.id),
                "product_code": product.code,
                "subscription_id": str(subscription.id),
                "pool_scope": seat_pool.pool_scope,
                "pool_key": seat_pool.pool_key,
                "governed_product_ids": [str(pid) for pid in sorted(seat_pool.governed_product_ids)],
                "quota_entitlement_id": str(seat_pool.quota_entitlement_id),
                "quota_key": seat_pool.quota_key,
                "total_limit": seat_pool.total_limit,
                "consumed_seats_after": consumed_after,
                "available_seats_after": available_after,
                "assigned_module_ids": [str(mid) for mid in sorted(deduped_module_ids)],
                "assigned_module_codes": assigned_module_codes,
            },
        )

        # 12. LMS Lifecycle Integration Hook
        from apps.integration_hub.lifecycle_service import handle_user_lms_assignment_active
        handle_user_lms_assignment_active(assignment, actor=actor, source="assign_user_to_product")

        return assignment


def suspend_user_assignment(
    *,
    assignment_id: uuid.UUID | str,
    reason: str,
    actor: Any,
    at_time: datetime | None = None,
    correlation_id: uuid.UUID | str | None = None,
    operation_source: str = AuditOperationSource.INTERACTIVE,
) -> UserProductAssignment:
    """Atomically suspend an active user product assignment.

    Rules:
    - Active: require trimmed reason (1-500 chars), set status='suspended',
      last_suspended_at=effective_time, suspension_reason=reason, updated_by=actor.
    - Already suspended: idempotent no-op (0 writes, unchanged timestamps, unchanged reason).
    - Revoked: reject with INVALID_STATE_TRANSITION.
    """
    if actor is None:
        raise ValueError("Authoritative actor is required.")

    clean_id = uuid.UUID(str(assignment_id))
    effective_time = at_time or timezone.now()

    with transaction.atomic():
        pre = (
            UserProductAssignment.objects.filter(id=clean_id)
            .values("organization_id", "status")
            .first()
        )
        if not pre:
            raise AssignmentNotFoundError(
                f"Assignment '{clean_id}' not found.",
                code="ASSIGNMENT_NOT_FOUND",
            )

        if pre["status"] == AssignmentStatus.REVOKED:
            raise InvalidStateTransitionError(
                "Cannot suspend a revoked assignment.",
                code="INVALID_STATE_TRANSITION",
            )

        if pre["status"] == AssignmentStatus.SUSPENDED:
            # Idempotent no-op: zero database writes, preserve timestamps and reason
            return UserProductAssignment.objects.get(id=clean_id)

        trimmed_reason = _validate_reason(reason)

        Organization.objects.select_for_update().get(id=pre["organization_id"])
        assignment = UserProductAssignment.objects.select_for_update().get(id=clean_id)

        if assignment.status == AssignmentStatus.REVOKED:
            raise InvalidStateTransitionError(
                "Cannot suspend a revoked assignment.",
                code="INVALID_STATE_TRANSITION",
            )

        if assignment.status == AssignmentStatus.SUSPENDED:
            return assignment

        assignment.status = AssignmentStatus.SUSPENDED
        assignment.last_suspended_at = effective_time
        assignment.suspension_reason = trimmed_reason
        assignment.updated_by = actor
        assignment.save(update_fields=["status", "last_suspended_at", "suspension_reason", "updated_by", "updated_at"])

        record_audit_event(
            action=AuditAction.USER_PRODUCT_SUSPENDED,
            target_type=AuditTargetType.USER_PRODUCT_ASSIGNMENT,
            target_id=assignment.id,
            target_repr=f"Assignment {assignment.id} ({assignment.product.code} -> {assignment.user.email})",
            actor=actor,
            organization_id=assignment.organization_id,
            operation_source=operation_source,
            correlation_id=correlation_id,
            metadata={
                "organization_code": assignment.organization.code,
                "user_id": str(assignment.user_id),
                "user_email": assignment.user.email,
                "product_id": str(assignment.product_id),
                "product_code": assignment.product.code,
                "previous_status": "active",
                "resulting_status": "suspended",
                "suspension_reason": trimmed_reason,
            },
        )

        # LMS Lifecycle Integration Hook
        from apps.integration_hub.lifecycle_service import handle_user_lms_assignment_suspended
        handle_user_lms_assignment_suspended(assignment, actor=actor, reason=trimmed_reason)

        return assignment


def reactivate_user_assignment(
    *,
    assignment_id: uuid.UUID | str,
    actor: Any,
    at_time: datetime | None = None,
    correlation_id: uuid.UUID | str | None = None,
    operation_source: str = AuditOperationSource.INTERACTIVE,
) -> UserProductAssignment:
    """Atomically reactivate a suspended user product assignment.

    Rules:
    - Suspended: revalidate organization, user, membership, temporal subscription,
      catalog product, snapshot entitlement, and seat quota validity.
      Change status to 'active', set last_reactivated_at, preserve last_suspended_at
      and suspension_reason. Set updated_by.
      Reactivation is never blocked by full/overallocated pool.
    - Already active: idempotent no-op (0 writes, unchanged timestamps).
    - Revoked: reject with INVALID_STATE_TRANSITION.
    """
    if actor is None:
        raise ValueError("Authoritative actor is required.")

    clean_id = uuid.UUID(str(assignment_id))
    effective_time = at_time or timezone.now()

    with transaction.atomic():
        pre = (
            UserProductAssignment.objects.filter(id=clean_id)
            .values("organization_id", "status")
            .first()
        )
        if not pre:
            raise AssignmentNotFoundError(
                f"Assignment '{clean_id}' not found.",
                code="ASSIGNMENT_NOT_FOUND",
            )

        if pre["status"] == AssignmentStatus.REVOKED:
            raise InvalidStateTransitionError(
                "Cannot reactivate a revoked assignment.",
                code="INVALID_STATE_TRANSITION",
            )

        if pre["status"] == AssignmentStatus.ACTIVE:
            # Idempotent no-op: zero writes, preserve timestamps
            return UserProductAssignment.objects.get(id=clean_id)

        # Lock in deterministic order:
        # 1. Organization
        org = Organization.objects.select_for_update().get(id=pre["organization_id"])
        if org.status != OrganizationStatus.ACTIVE:
            raise OrganizationNotActiveError(
                f"Organization '{org.id}' is not active.",
                code="ORGANIZATION_NOT_ACTIVE",
            )

        # 2. Subscription
        subscription = get_temporally_eligible_subscription(
            organization_id=org.id,
            at_time=effective_time,
            for_update=True,
        )
        if not subscription:
            raise SubscriptionUnavailableError(
                "No open, temporally eligible subscription exists for this organization.",
                code="SUBSCRIPTION_UNAVAILABLE",
            )

        # 3. Assignment
        assignment = (
            UserProductAssignment.objects.select_for_update()
            .select_related("membership", "user", "product")
            .get(id=clean_id)
        )

        if assignment.status == AssignmentStatus.REVOKED:
            raise InvalidStateTransitionError(
                "Cannot reactivate a revoked assignment.",
                code="INVALID_STATE_TRANSITION",
            )

        if assignment.status == AssignmentStatus.ACTIVE:
            return assignment

        # 4. Membership lock and validation
        membership = OrganizationMembership.objects.select_for_update().get(id=assignment.membership_id)
        if (
            membership.organization_id != org.id
            or membership.user_id != assignment.user_id
            or membership.status != MembershipStatus.ACTIVE
        ):
            raise MembershipIneligibleError(
                "Membership is ineligible or not active.",
                code="MEMBERSHIP_INELIGIBLE",
            )

        # Central User check
        user = assignment.user
        if user.status == "disabled" or getattr(user, "is_active", True) is False:
            raise UserDisabledError(
                "Platform user account is disabled or deactivated.",
                code="USER_DISABLED",
            )
        if user.status != "active":
            raise UserInactiveError(
                f"Platform user account status is '{user.status}'.",
                code="USER_INACTIVE",
            )

        # Product catalog check
        product = assignment.product
        if product.status != ProductStatus.ACTIVE:
            raise ProductInactiveError(
                f"Product '{product.id}' is not active in catalog.",
                code="PRODUCT_INACTIVE",
            )

        # Subscription product entitlement snapshot check
        if not subscription.product_entitlements.filter(product_id=product.id).exists():
            raise ProductNotEntitledError(
                f"Product '{product.id}' is not entitled under subscription snapshot.",
                code="PRODUCT_NOT_ENTITLED",
            )

        # Validate governing seat pool validity (raises if unconfigured or ambiguous)
        resolve_governing_seat_pool(
            organization_id=org.id,
            product_id=product.id,
            subscription=subscription,
        )

        # Mutate status to active, preserving last_suspended_at and suspension_reason
        assignment.status = AssignmentStatus.ACTIVE
        assignment.last_reactivated_at = effective_time
        assignment.updated_by = actor
        assignment.save(update_fields=["status", "last_reactivated_at", "updated_by", "updated_at"])

        record_audit_event(
            action=AuditAction.USER_PRODUCT_REACTIVATED,
            target_type=AuditTargetType.USER_PRODUCT_ASSIGNMENT,
            target_id=assignment.id,
            target_repr=f"Assignment {assignment.id} ({product.code} -> {user.email})",
            actor=actor,
            organization_id=org.id,
            operation_source=operation_source,
            correlation_id=correlation_id,
            metadata={
                "organization_code": org.code,
                "user_id": str(user.id),
                "user_email": user.email,
                "product_id": str(product.id),
                "product_code": product.code,
                "previous_status": "suspended",
                "resulting_status": "active",
            },
        )

        # LMS Lifecycle Integration Hook
        from apps.integration_hub.lifecycle_service import handle_user_lms_assignment_reactivated
        handle_user_lms_assignment_reactivated(assignment, actor=actor)

        return assignment


def revoke_user_assignment(
    *,
    assignment_id: uuid.UUID | str,
    reason: str,
    actor: Any,
    at_time: datetime | None = None,
    correlation_id: uuid.UUID | str | None = None,
    operation_source: str = AuditOperationSource.INTERACTIVE,
) -> UserProductAssignment:
    """Atomically revoke an active or suspended user product assignment.

    Rules:
    - Active or Suspended: require trimmed reason (1-500 chars), set status='revoked',
      revoked_at=effective_time, revocation_reason=reason, updated_by=actor.
      Immediately releases seat reservation.
      Allowed even when assignment is dormant (expired subscription, plan omitted product).
    - Already revoked: idempotent no-op (0 writes, do not validate reason, preserve timestamps).
    """
    if actor is None:
        raise ValueError("Authoritative actor is required.")

    clean_id = uuid.UUID(str(assignment_id))
    effective_time = at_time or timezone.now()

    with transaction.atomic():
        pre = (
            UserProductAssignment.objects.filter(id=clean_id)
            .values("organization_id", "status")
            .first()
        )
        if not pre:
            raise AssignmentNotFoundError(
                f"Assignment '{clean_id}' not found.",
                code="ASSIGNMENT_NOT_FOUND",
            )

        if pre["status"] == AssignmentStatus.REVOKED:
            # Idempotent no-op: do not validate reason, zero writes, preserve timestamps
            return UserProductAssignment.objects.get(id=clean_id)

        trimmed_reason = _validate_reason(reason)

        Organization.objects.select_for_update().get(id=pre["organization_id"])
        assignment = UserProductAssignment.objects.select_for_update().get(id=clean_id)

        if assignment.status == AssignmentStatus.REVOKED:
            return assignment

        prev_status_str = assignment.status.lower()
        assignment.status = AssignmentStatus.REVOKED
        assignment.revoked_at = effective_time
        assignment.revocation_reason = trimmed_reason
        assignment.updated_by = actor
        assignment.save(update_fields=["status", "revoked_at", "revocation_reason", "updated_by", "updated_at"])

        sub = get_temporally_eligible_subscription(assignment.organization_id, at_time=effective_time)
        was_counted = bool(sub and sub.product_entitlements.filter(product_id=assignment.product_id).exists())
        delta = -1 if was_counted else 0

        record_audit_event(
            action=AuditAction.USER_PRODUCT_REVOKED,
            target_type=AuditTargetType.USER_PRODUCT_ASSIGNMENT,
            target_id=assignment.id,
            target_repr=f"Assignment {assignment.id} ({assignment.product.code} -> {assignment.user.email})",
            actor=actor,
            organization_id=assignment.organization_id,
            operation_source=operation_source,
            correlation_id=correlation_id,
            metadata={
                "organization_code": assignment.organization.code,
                "user_id": str(assignment.user_id),
                "user_email": assignment.user.email,
                "product_id": str(assignment.product_id),
                "product_code": assignment.product.code,
                "previous_status": prev_status_str,
                "resulting_status": "revoked",
                "reason": trimmed_reason,
                "seat_reservation_released": True,
                "was_counted_in_current_pool": was_counted,
                "current_pool_consumed_delta": delta,
            },
        )

        # LMS Lifecycle Integration Hook
        from apps.integration_hub.lifecycle_service import handle_user_lms_assignment_revoked
        handle_user_lms_assignment_revoked(assignment, actor=actor, reason=trimmed_reason)

        return assignment


def replace_user_module_assignments(
    *,
    assignment_id: uuid.UUID | str,
    module_ids: list[uuid.UUID | str],
    actor: Any,
    at_time: datetime | None = None,
    correlation_id: uuid.UUID | str | None = None,
    operation_source: str = AuditOperationSource.INTERACTIVE,
) -> UserProductAssignment:
    """Atomically replace the enabled modules for an active or suspended assignment.

    Rules:
    - Assignment must be active or suspended. Revoked returns INVALID_STATE_TRANSITION.
    - Deduplicate requested module IDs (max 100).
    - Every requested module must belong to the assignment product, be catalog-active,
      and be present in the subscription module-entitlement snapshot.
    - Empty selection is valid and disables all modules.
    - Included IDs become enabled; omitted existing IDs become disabled;
      missing rows are created; rows are never physically deleted.
    - Completely identical enabled set is a true no-op (0 writes, no assignment updated_at change).
    - Changed replacement updates assignment.updated_by and assignment.updated_at.
    """
    if actor is None:
        raise ValueError("Authoritative actor is required.")

    clean_id = uuid.UUID(str(assignment_id))
    effective_time = at_time or timezone.now()

    # Deduplicate requested module IDs
    deduped_module_ids: list[uuid.UUID] = []
    seen = set()
    for m in module_ids:
        mid = uuid.UUID(str(m))
        if mid not in seen:
            seen.add(mid)
            deduped_module_ids.append(mid)

    if len(deduped_module_ids) > 100:
        raise InvalidModuleIdsError(
            "Maximum 100 module IDs allowed.",
            code="INVALID_MODULE_IDS",
        )

    requested_set = set(deduped_module_ids)

    with transaction.atomic():
        pre = (
            UserProductAssignment.objects.filter(id=clean_id)
            .values("organization_id", "product_id", "status")
            .first()
        )
        if not pre:
            raise AssignmentNotFoundError(
                f"Assignment '{clean_id}' not found.",
                code="ASSIGNMENT_NOT_FOUND",
            )

        if pre["status"] == AssignmentStatus.REVOKED:
            raise InvalidStateTransitionError(
                "Cannot replace modules on a revoked assignment.",
                code="INVALID_STATE_TRANSITION",
            )

        # Lock Organization -> Subscription -> Assignment -> Module Assignments
        org = Organization.objects.select_for_update().get(id=pre["organization_id"])

        subscription = get_temporally_eligible_subscription(
            organization_id=org.id,
            at_time=effective_time,
            for_update=True,
        )
        if not subscription:
            raise SubscriptionUnavailableError(
                "No open, temporally eligible subscription exists for this organization.",
                code="SUBSCRIPTION_UNAVAILABLE",
            )

        assignment = UserProductAssignment.objects.select_for_update().get(id=clean_id)
        if assignment.status == AssignmentStatus.REVOKED:
            raise InvalidStateTransitionError(
                "Cannot replace modules on a revoked assignment.",
                code="INVALID_STATE_TRANSITION",
            )

        # Validate requested modules if any
        if deduped_module_ids:
            entitled_module_ids = set(
                subscription.module_entitlements.values_list("module_id", flat=True)
            )
            catalog_modules = {
                mod.id: mod
                for mod in ProductModule.objects.filter(id__in=deduped_module_ids)
            }
            for mid in deduped_module_ids:
                mod = catalog_modules.get(mid)
                if not mod or mod.product_id != assignment.product_id or mod.status != CatalogStatus.ACTIVE:
                    raise InvalidModuleIdsError(
                        f"Module '{mid}' is invalid, does not belong to product '{assignment.product_id}', or is inactive.",
                        code="INVALID_MODULE_IDS",
                    )
                if mid not in entitled_module_ids:
                    raise ModuleNotEntitledError(
                        f"Module '{mid}' is not entitled under the subscription snapshot.",
                        code="MODULE_NOT_ENTITLED",
                    )

        # Lock existing module rows ordered by ID
        existing_module_rows = list(
            UserModuleAssignment.objects.select_for_update()
            .filter(assignment=assignment)
            .order_by("id")
        )
        existing_by_mid = {uma.module_id: uma for uma in existing_module_rows}
        current_enabled_ids = {uma.module_id for uma in existing_module_rows if uma.is_enabled}

        if current_enabled_ids == requested_set:
            # Completely identical enabled set: true no-op!
            return assignment

        # Apply changes:
        # 1. Existing rows that should be disabled or re-enabled
        for uma in existing_module_rows:
            if uma.is_enabled and uma.module_id not in requested_set:
                uma.is_enabled = False
                uma.save(update_fields=["is_enabled", "updated_at"])
            elif not uma.is_enabled and uma.module_id in requested_set:
                uma.is_enabled = True
                uma.save(update_fields=["is_enabled", "updated_at"])

        # 2. Missing rows to create
        for mid in deduped_module_ids:
            if mid not in existing_by_mid:
                UserModuleAssignment.objects.create(
                    assignment=assignment,
                    module_id=mid,
                    is_enabled=True,
                )

        # 3. Changed replacement updates assignment.updated_by and assignment.updated_at
        assignment.updated_by = actor
        assignment.save(update_fields=["updated_by", "updated_at"])

        prev_enabled_module_ids = sorted(list(current_enabled_ids))
        prev_codes = sorted(
            list(
                ProductModule.objects.filter(id__in=prev_enabled_module_ids).values_list("code", flat=True)
            )
        )
        res_enabled_module_ids = sorted(list(requested_set))
        res_codes = sorted(
            list(
                ProductModule.objects.filter(id__in=res_enabled_module_ids).values_list("code", flat=True)
            )
        )

        record_audit_event(
            action=AuditAction.USER_MODULE_ASSIGNMENTS_REPLACED,
            target_type=AuditTargetType.USER_PRODUCT_ASSIGNMENT,
            target_id=assignment.id,
            target_repr=f"Assignment {assignment.id} Modules",
            actor=actor,
            organization_id=assignment.organization_id,
            operation_source=operation_source,
            correlation_id=correlation_id,
            metadata={
                "organization_code": assignment.organization.code,
                "user_id": str(assignment.user_id),
                "product_id": str(assignment.product_id),
                "product_code": assignment.product.code,
                "previous_enabled_module_ids": [str(mid) for mid in prev_enabled_module_ids],
                "previous_enabled_module_codes": prev_codes,
                "resulting_enabled_module_ids": [str(mid) for mid in res_enabled_module_ids],
                "resulting_enabled_module_codes": res_codes,
            },
        )

        return assignment


def revoke_assignments_for_membership(
    *,
    membership_id: uuid.UUID | str,
    actor: Any,
    reason: str = "Membership ended",
    at_time: datetime | None = None,
    correlation_id: uuid.UUID | str | None = None,
    operation_source: str = AuditOperationSource.INTERACTIVE,
) -> list[UserProductAssignment]:
    """Revoke all active and suspended assignments tied to a membership.

    Used when membership ends. Atomic, deterministic order, preserves history.
    """
    clean_id = uuid.UUID(str(membership_id))
    effective_time = at_time or timezone.now()
    trimmed_reason = _validate_reason(reason)

    with transaction.atomic():
        assignments = list(
            UserProductAssignment.objects.select_for_update()
            .filter(membership_id=clean_id)
            .exclude(status=AssignmentStatus.REVOKED)
            .order_by("id")
        )
        revoked_list = []
        for assignment in assignments:
            prev_status = assignment.status
            assignment.status = AssignmentStatus.REVOKED
            assignment.revoked_at = effective_time
            assignment.revocation_reason = trimmed_reason
            assignment.updated_by = actor
            assignment.save(update_fields=["status", "revoked_at", "revocation_reason", "updated_by", "updated_at"])

            sub = get_temporally_eligible_subscription(assignment.organization_id, at_time=effective_time)
            was_counted = bool(sub and sub.product_entitlements.filter(product_id=assignment.product_id).exists())
            delta = -1 if was_counted else 0

            record_audit_event(
                action=AuditAction.USER_PRODUCT_REVOKED,
                target_type=AuditTargetType.USER_PRODUCT_ASSIGNMENT,
                target_id=assignment.id,
                target_repr=f"Assignment {assignment.id} ({assignment.product.code} -> {assignment.user.email})",
                actor=actor,
                organization_id=assignment.organization_id,
                operation_source=operation_source,
                correlation_id=correlation_id,
                metadata={
                    "organization_code": assignment.organization.code,
                    "user_id": str(assignment.user_id),
                    "user_email": assignment.user.email,
                    "product_id": str(assignment.product_id),
                    "product_code": assignment.product.code,
                    "previous_status": prev_status.lower(),
                    "resulting_status": "revoked",
                    "reason": trimmed_reason,
                    "seat_reservation_released": True,
                    "was_counted_in_current_pool": was_counted,
                    "current_pool_consumed_delta": delta,
                },
            )
            # LMS Lifecycle Integration Hook
            from apps.integration_hub.lifecycle_service import handle_user_lms_assignment_revoked
            handle_user_lms_assignment_revoked(assignment, actor=actor, reason=trimmed_reason)

            revoked_list.append(assignment)

        return revoked_list


def revoke_assignments_for_organization(
    *,
    organization_id: uuid.UUID | str,
    actor: Any,
    reason: str = "Organization retired",
    at_time: datetime | None = None,
    correlation_id: uuid.UUID | str | None = None,
    operation_source: str = AuditOperationSource.INTERACTIVE,
) -> list[UserProductAssignment]:
    """Revoke all active and suspended assignments belonging to an organization.

    Used when an organization is retired. Atomic, deterministic order, preserves history.
    """
    clean_id = uuid.UUID(str(organization_id))
    effective_time = at_time or timezone.now()
    trimmed_reason = _validate_reason(reason)

    with transaction.atomic():
        Organization.objects.select_for_update().get(id=clean_id)
        assignments = list(
            UserProductAssignment.objects.select_for_update()
            .filter(organization_id=clean_id)
            .exclude(status=AssignmentStatus.REVOKED)
            .order_by("id")
        )
        revoked_list = []
        for assignment in assignments:
            prev_status = assignment.status
            assignment.status = AssignmentStatus.REVOKED
            assignment.revoked_at = effective_time
            assignment.revocation_reason = trimmed_reason
            assignment.updated_by = actor
            assignment.save(update_fields=["status", "revoked_at", "revocation_reason", "updated_by", "updated_at"])

            sub = get_temporally_eligible_subscription(assignment.organization_id, at_time=effective_time)
            was_counted = bool(sub and sub.product_entitlements.filter(product_id=assignment.product_id).exists())
            delta = -1 if was_counted else 0

            record_audit_event(
                action=AuditAction.USER_PRODUCT_REVOKED,
                target_type=AuditTargetType.USER_PRODUCT_ASSIGNMENT,
                target_id=assignment.id,
                target_repr=f"Assignment {assignment.id} ({assignment.product.code} -> {assignment.user.email})",
                actor=actor,
                organization_id=assignment.organization_id,
                operation_source=operation_source,
                correlation_id=correlation_id,
                metadata={
                    "organization_code": assignment.organization.code,
                    "user_id": str(assignment.user_id),
                    "user_email": assignment.user.email,
                    "product_id": str(assignment.product_id),
                    "product_code": assignment.product.code,
                    "previous_status": prev_status.lower(),
                    "resulting_status": "revoked",
                    "reason": trimmed_reason,
                    "seat_reservation_released": True,
                    "was_counted_in_current_pool": was_counted,
                    "current_pool_consumed_delta": delta,
                },
            )
            # LMS Lifecycle Integration Hook
            from apps.integration_hub.lifecycle_service import handle_user_lms_assignment_revoked
            handle_user_lms_assignment_revoked(assignment, actor=actor, reason=trimmed_reason)

            revoked_list.append(assignment)

        return revoked_list
