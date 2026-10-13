"""VibeConnect Organization Membership Domain Services (Phase 2D Stage 2).

Provides transactional, pessimistic-locking domain services for:
- Membership creation (requires active organization & active user)
- Membership-type mutation (tenant_admin <-> member)
- Membership lifecycle transitions: active <-> suspended, active/suspended -> ended
- Explicit restore of ended memberships (capturing prior joined_at/ended_at snapshots in audit metadata)
- Conflict handling (MEMBERSHIP_ALREADY_EXISTS vs MEMBERSHIP_ENDED_RESTORE_REQUIRED)
- Append-only audit trail recording
"""

from typing import Any
import uuid

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.auditlog.models import AuditAction, AuditOperationSource, AuditTargetType
from apps.auditlog.services import record_audit_event
from apps.identity.models import UserStatus
from apps.organizations.models import (
    MembershipStatus,
    MembershipType,
    Organization,
    OrganizationMembership,
    OrganizationStatus,
)

PlatformUser = get_user_model()


class MembershipServiceError(Exception):
    """Base exception for membership domain service errors."""

    def __init__(self, message: str, code: str = "MEMBERSHIP_SERVICE_ERROR"):
        super().__init__(message)
        self.message = message
        self.code = code


class MembershipValidationError(MembershipServiceError):
    """Raised when membership input data fails validation."""

    def __init__(self, message: str, code: str = "INVALID_MEMBERSHIP_DATA"):
        super().__init__(message, code=code)


class LmsRoleDemotionUnsupportedError(MembershipValidationError):
    """Raised when attempting to downgrade a tenant admin who holds an active LMS assignment.

    LMS role demotion is not currently supported by upstream integration.
    """

    def __init__(
        self,
        message: str = (
            "Cannot downgrade Tenant Admin to Member: user holds an active LMS product assignment "
            "and LMS role demotion is not currently supported by upstream integration. "
            "Suspend or revoke the LMS product assignment before changing the membership role."
        ),
        code: str = "LMS_ROLE_DEMOTION_UNSUPPORTED",
    ):
        super().__init__(message, code=code)


class MembershipNotFoundError(MembershipServiceError):
    """Raised when a membership record cannot be found."""

    def __init__(self, message: str, code: str = "MEMBERSHIP_NOT_FOUND"):
        super().__init__(message, code=code)


class OrganizationNotActiveError(MembershipServiceError):
    """Raised when an operation requires an active organization but the target is inactive."""

    def __init__(self, message: str, code: str = "ORGANIZATION_NOT_ACTIVE"):
        super().__init__(message, code=code)


class UserNotActiveError(MembershipServiceError):
    """Raised when an operation requires an active user but the target is inactive."""

    def __init__(self, message: str, code: str = "USER_NOT_ACTIVE"):
        super().__init__(message, code=code)


class MembershipAlreadyExistsError(MembershipServiceError):
    """Raised when creating a membership for a user who already has an active or suspended membership."""

    def __init__(self, message: str, code: str = "MEMBERSHIP_ALREADY_EXISTS"):
        super().__init__(message, code=code)


class MembershipEndedRestoreRequiredError(MembershipServiceError):
    """Raised when creating a membership for a user who already has an ended membership.

    Ended memberships must be explicitly restored rather than recreated.
    """

    def __init__(self, message: str, code: str = "MEMBERSHIP_ENDED_RESTORE_REQUIRED"):
        super().__init__(message, code=code)


class InvalidMembershipTransitionError(MembershipServiceError):
    """Raised when an invalid lifecycle transition is requested."""

    def __init__(self, message: str, code: str = "INVALID_MEMBERSHIP_TRANSITION"):
        super().__init__(message, code=code)


class MembershipNotEndedError(MembershipServiceError):
    """Raised when attempting to restore a membership that is not ended."""

    def __init__(self, message: str, code: str = "MEMBERSHIP_NOT_ENDED"):
        super().__init__(message, code=code)


class UserInactiveCannotRestoreError(MembershipServiceError):
    """Raised when attempting to restore a membership for an inactive user."""

    def __init__(self, message: str, code: str = "USER_INACTIVE_CANNOT_RESTORE"):
        super().__init__(message, code=code)


def _validate_actor(actor: Any) -> None:
    """Validate that actor is an authenticated, active platform owner."""
    if not actor or not getattr(actor, "is_authenticated", False) or not getattr(actor, "is_active", False):
        raise MembershipValidationError("Actor must be an active, authenticated platform user.", code="INVALID_ACTOR")
    if not getattr(actor, "is_platform_owner", False):
        raise MembershipValidationError("Actor must possess Platform Owner privileges.", code="INSUFFICIENT_PRIVILEGES")


def create_membership(
    *,
    actor: Any,
    organization_id: uuid.UUID | str,
    user_id: uuid.UUID | str,
    membership_type: str = MembershipType.MEMBER,
    correlation_id: uuid.UUID | str | None = None,
) -> OrganizationMembership:
    """Create a new active membership for an active user in an active organization."""
    _validate_actor(actor)

    if membership_type not in MembershipType.values:
        raise MembershipValidationError(
            f"Invalid membership_type '{membership_type}'. Valid choices: {list(MembershipType.values)}.",
            code="INVALID_MEMBERSHIP_TYPE",
        )

    with transaction.atomic():
        # Validate organization exists and is active
        org = Organization.objects.filter(pk=organization_id).first()
        if not org:
            raise MembershipNotFoundError(f"Organization '{organization_id}' not found.", code="ORGANIZATION_NOT_FOUND")

        if org.status != OrganizationStatus.ACTIVE:
            raise OrganizationNotActiveError(
                "Cannot create membership in an organization that is not active.",
                code="ORGANIZATION_NOT_ACTIVE",
            )

        # Validate user exists and is active
        user = PlatformUser.objects.filter(pk=user_id).first()
        if not user:
            raise MembershipNotFoundError(f"User '{user_id}' not found.", code="USER_NOT_FOUND")

        if user.status != UserStatus.ACTIVE or not user.is_active:
            raise UserNotActiveError(
                "Cannot grant membership to an inactive user.",
                code="USER_NOT_ACTIVE",
            )

        # Check existing membership on the unique (organization, user) pair
        existing = OrganizationMembership.objects.select_for_update().filter(
            organization=org, user=user
        ).first()

        if existing:
            if existing.status in (MembershipStatus.ACTIVE, MembershipStatus.SUSPENDED):
                raise MembershipAlreadyExistsError(
                    "User already has an active or suspended membership in this organization.",
                    code="MEMBERSHIP_ALREADY_EXISTS",
                )
            if existing.status == MembershipStatus.ENDED:
                raise MembershipEndedRestoreRequiredError(
                    "User has an ended membership in this organization. Explicit restore is required.",
                    code="MEMBERSHIP_ENDED_RESTORE_REQUIRED",
                )

        assigned_role = None
        if membership_type == MembershipType.TENANT_ADMIN:
            from apps.access_control.models import Role
            assigned_role = Role.objects.get(code="system_tenant_admin", is_system_role=True)

        try:
            with transaction.atomic():
                membership = OrganizationMembership.objects.create(
                    organization=org,
                    user=user,
                    membership_type=membership_type,
                    role=assigned_role,
                    status=MembershipStatus.ACTIVE,
                    joined_at=timezone.now(),
                    ended_at=None,
                )
        except IntegrityError:
            # Handle concurrent race condition on (organization, user) unique constraint
            concurrent_existing = OrganizationMembership.objects.filter(
                organization=org, user=user
            ).first()
            if concurrent_existing and concurrent_existing.status == MembershipStatus.ENDED:
                raise MembershipEndedRestoreRequiredError(
                    "User has an ended membership in this organization. Explicit restore is required.",
                    code="MEMBERSHIP_ENDED_RESTORE_REQUIRED",
                )
            raise MembershipAlreadyExistsError(
                "User already has a membership in this organization.",
                code="MEMBERSHIP_ALREADY_EXISTS",
            )

        record_audit_event(
            action=AuditAction.MEMBERSHIP_CREATED,
            target_type=AuditTargetType.MEMBERSHIP,
            target_id=membership.id,
            target_repr=f"{org.code}:{user.email}",
            actor=actor,
            organization_id=org.id,
            operation_source=AuditOperationSource.INTERACTIVE,
            correlation_id=correlation_id,
            metadata={
                "organization_code": org.code,
                "user_email": user.email,
                "membership_type": membership.membership_type,
                "status": "active",
            },
        )

    return membership


def _lock_membership_target(
    membership_id: uuid.UUID | str,
) -> tuple[Organization, OrganizationMembership, list[OrganizationMembership]]:
    """Resolve and lock target membership according to global lock order:
    1. Non-locking lookup of organization_id.
    2. Lock Organization row.
    3. Lock all tenant_admin memberships for that organization in deterministic order.
    4. If target is a member, lock the target member row after tenant_admins.
    5. Relevant Role rows ordered by ID.
    6. Relevant RolePermission rows ordered by ID.
    7. PlatformUser rows where required ordered by ID.
    """
    from apps.access_control.models import Role, RolePermission

    clean_id = uuid.UUID(str(membership_id))
    pre = (
        OrganizationMembership.objects.filter(id=clean_id)
        .values("organization_id", "membership_type")
        .first()
    )
    if not pre:
        raise MembershipNotFoundError(f"Membership '{membership_id}' not found.", code="MEMBERSHIP_NOT_FOUND")

    org_id = pre["organization_id"]
    org = Organization.objects.select_for_update().filter(id=org_id).first()
    if not org:
        raise OrganizationNotActiveError(f"Organization '{org_id}' not found.", code="ORGANIZATION_NOT_ACTIVE")

    tenant_admins = list(
        OrganizationMembership.objects.select_for_update()
        .filter(organization_id=org_id, membership_type=MembershipType.TENANT_ADMIN)
        .order_by("id")
    )

    if pre["membership_type"] == MembershipType.TENANT_ADMIN:
        target = next((m for m in tenant_admins if m.id == clean_id), None)
        if not target:
            raise MembershipNotFoundError(f"Membership '{membership_id}' not found.", code="MEMBERSHIP_NOT_FOUND")
    else:
        target = (
            OrganizationMembership.objects.select_for_update()
            .filter(id=clean_id)
            .first()
        )
        if not target:
            raise MembershipNotFoundError(f"Membership '{membership_id}' not found.", code="MEMBERSHIP_NOT_FOUND")

    all_locked_mems = list(tenant_admins)
    if pre["membership_type"] != MembershipType.TENANT_ADMIN and target:
        all_locked_mems.append(target)

    # 3. Relevant Role rows ordered by ID
    role_ids = {m.role_id for m in all_locked_mems if m.role_id}
    roles = list(Role.objects.select_for_update().filter(id__in=role_ids).order_by("id"))
    roles_by_id = {r.id: r for r in roles}

    # 4. Relevant RolePermission rows ordered by ID
    if role_ids:
        list(RolePermission.objects.select_for_update().filter(role_id__in=role_ids).order_by("id"))

    # 5. PlatformUser rows where required
    user_ids = {m.user_id for m in all_locked_mems}
    users = list(PlatformUser.objects.select_for_update().filter(id__in=user_ids).order_by("id"))
    users_by_id = {u.id: u for u in users}

    # Attach loaded models in memory
    for m in all_locked_mems:
        m.organization = org
        if m.role_id:
            m.role = roles_by_id.get(m.role_id)
        m.user = users_by_id.get(m.user_id)

    return org, target, tenant_admins


def update_membership_type(
    *,
    actor: Any,
    membership_id: uuid.UUID | str,
    new_membership_type: str,
    correlation_id: uuid.UUID | str | None = None,
) -> OrganizationMembership:
    """Update membership_type (e.g. member <-> tenant_admin). Ended memberships cannot be updated."""
    _validate_actor(actor)

    if new_membership_type not in MembershipType.values:
        raise MembershipValidationError(
            f"Invalid membership_type '{new_membership_type}'. Valid choices: {list(MembershipType.values)}.",
            code="INVALID_MEMBERSHIP_TYPE",
        )

    with transaction.atomic():
        org, membership, tenant_admins = _lock_membership_target(membership_id)

        if membership.status == MembershipStatus.ENDED:
            raise InvalidMembershipTransitionError(
                "Cannot update membership type of an ended membership.",
                code="INVALID_MEMBERSHIP_TRANSITION",
            )

        if membership.membership_type == new_membership_type:
            return membership

        previous_type = membership.membership_type

        if new_membership_type == MembershipType.TENANT_ADMIN:
            from apps.access_control.models import Role

            system_role = Role.objects.get(code="system_tenant_admin", is_system_role=True)
            membership.membership_type = MembershipType.TENANT_ADMIN
            membership.role = system_role
            membership.save(update_fields=["membership_type", "role", "updated_at"])

            # Lifecycle hook: Trigger LMS role synchronization if user holds active LMS assignment
            from apps.integration_hub.lifecycle_service import handle_user_membership_promoted_to_admin

            handle_user_membership_promoted_to_admin(membership, actor=actor)
        else:
            # Tenant Admin -> Member: fail-closed safeguard against unsupported LMS role demotion
            from apps.assignments.models import AssignmentStatus, UserProductAssignment
            from apps.integration_hub.lifecycle_service import LMS_PRODUCT_CODES

            has_active_lms_assignment = UserProductAssignment.objects.filter(
                organization=membership.organization,
                user=membership.user,
                status=AssignmentStatus.ACTIVE,
                product__code__in=LMS_PRODUCT_CODES,
            ).exists()

            if has_active_lms_assignment:
                raise LmsRoleDemotionUnsupportedError(
                    f"Cannot downgrade Tenant Admin '{membership.user.email}' to Member: "
                    "user holds an active LMS product assignment and LMS role demotion is not currently supported. "
                    "Suspend or revoke the LMS product assignment before changing the membership role.",
                    code="LMS_ROLE_DEMOTION_UNSUPPORTED",
                )

            # Tenant Admin -> Member: evaluate projected last-admin invariant
            from apps.access_control.services.guards import evaluate_structural_last_admin

            evaluate_structural_last_admin(
                organization_id=membership.organization_id,
                downgraded_membership_id=membership.id,
                locked_tenant_admins=tenant_admins,
            )
            membership.membership_type = MembershipType.MEMBER
            membership.role = None
            membership.save(update_fields=["membership_type", "role", "updated_at"])

        record_audit_event(
            action=AuditAction.MEMBERSHIP_UPDATED,
            target_type=AuditTargetType.MEMBERSHIP,
            target_id=membership.id,
            target_repr=f"{membership.organization.code}:{membership.user.email}",
            actor=actor,
            organization_id=membership.organization_id,
            operation_source=AuditOperationSource.INTERACTIVE,
            correlation_id=correlation_id,
            metadata={
                "organization_code": membership.organization.code,
                "user_email": membership.user.email,
                "previous_membership_type": previous_type,
                "resulting_membership_type": new_membership_type,
            },
        )

    return membership


def suspend_membership(
    *,
    actor: Any,
    membership_id: uuid.UUID | str,
    reason: str | None = None,
    correlation_id: uuid.UUID | str | None = None,
) -> OrganizationMembership:
    """Suspend an active membership. Rejects already suspended or ended memberships."""
    _validate_actor(actor)

    with transaction.atomic():
        org, membership, tenant_admins = _lock_membership_target(membership_id)

        if membership.status == MembershipStatus.SUSPENDED:
            raise InvalidMembershipTransitionError(
                "Membership is already suspended.",
                code="INVALID_MEMBERSHIP_TRANSITION",
            )

        if membership.status == MembershipStatus.ENDED:
            raise InvalidMembershipTransitionError(
                "Cannot suspend an ended membership.",
                code="INVALID_MEMBERSHIP_TRANSITION",
            )

        if membership.membership_type == MembershipType.TENANT_ADMIN:
            from apps.access_control.services.guards import evaluate_structural_last_admin

            evaluate_structural_last_admin(
                organization_id=membership.organization_id,
                suspended_membership_id=membership.id,
                locked_tenant_admins=tenant_admins,
            )

        previous_status = membership.status
        membership.status = MembershipStatus.SUSPENDED
        membership.save(update_fields=["status", "updated_at"])

        metadata = {
            "organization_code": membership.organization.code,
            "user_email": membership.user.email,
            "previous_status": previous_status,
            "resulting_status": "suspended",
        }
        if reason:
            metadata["reason"] = str(reason).strip()

        record_audit_event(
            action=AuditAction.MEMBERSHIP_SUSPENDED,
            target_type=AuditTargetType.MEMBERSHIP,
            target_id=membership.id,
            target_repr=f"{membership.organization.code}:{membership.user.email}",
            actor=actor,
            organization_id=membership.organization_id,
            operation_source=AuditOperationSource.INTERACTIVE,
            correlation_id=correlation_id,
            metadata=metadata,
        )

    return membership


def reactivate_membership(
    *,
    actor: Any,
    membership_id: uuid.UUID | str,
    correlation_id: uuid.UUID | str | None = None,
) -> OrganizationMembership:
    """Reactivate a suspended membership. Requires active organization and active user.

    Ended memberships must use restore_membership.
    """
    _validate_actor(actor)

    with transaction.atomic():
        org, membership, tenant_admins = _lock_membership_target(membership_id)

        if membership.organization.status != OrganizationStatus.ACTIVE:
            raise OrganizationNotActiveError(
                "Cannot reactivate membership in an organization that is not active.",
                code="ORGANIZATION_NOT_ACTIVE",
            )

        if membership.user.status != UserStatus.ACTIVE or not membership.user.is_active:
            raise UserNotActiveError(
                "Cannot reactivate membership for an inactive user.",
                code="USER_NOT_ACTIVE",
            )

        if membership.status == MembershipStatus.ACTIVE:
            raise InvalidMembershipTransitionError(
                "Membership is already active.",
                code="INVALID_MEMBERSHIP_TRANSITION",
            )

        if membership.status == MembershipStatus.ENDED:
            raise InvalidMembershipTransitionError(
                "Ended membership cannot be reactivated; restore is required.",
                code="INVALID_MEMBERSHIP_TRANSITION",
            )

        previous_status = membership.status
        membership.status = MembershipStatus.ACTIVE
        membership.save(update_fields=["status", "updated_at"])

        record_audit_event(
            action=AuditAction.MEMBERSHIP_REACTIVATED,
            target_type=AuditTargetType.MEMBERSHIP,
            target_id=membership.id,
            target_repr=f"{membership.organization.code}:{membership.user.email}",
            actor=actor,
            organization_id=membership.organization_id,
            operation_source=AuditOperationSource.INTERACTIVE,
            correlation_id=correlation_id,
            metadata={
                "organization_code": membership.organization.code,
                "user_email": membership.user.email,
                "previous_status": previous_status,
                "resulting_status": "active",
            },
        )

    return membership


def end_membership(
    *,
    actor: Any,
    membership_id: uuid.UUID | str,
    reason: str | None = None,
    correlation_id: uuid.UUID | str | None = None,
) -> OrganizationMembership:
    """End an active or suspended membership, setting ended_at to current timestamp."""
    _validate_actor(actor)

    with transaction.atomic():
        org, membership, tenant_admins = _lock_membership_target(membership_id)

        if membership.status == MembershipStatus.ENDED:
            raise InvalidMembershipTransitionError(
                "Membership is already ended.",
                code="INVALID_MEMBERSHIP_TRANSITION",
            )

        if membership.membership_type == MembershipType.TENANT_ADMIN:
            from apps.access_control.services.guards import evaluate_structural_last_admin

            evaluate_structural_last_admin(
                organization_id=membership.organization_id,
                ended_membership_id=membership.id,
                locked_tenant_admins=tenant_admins,
            )

        previous_status = membership.status
        now = timezone.now()
        membership.status = MembershipStatus.ENDED
        membership.ended_at = now
        # Role is preserved while ended
        membership.save(update_fields=["status", "ended_at", "updated_at"])

        # Phase 2F Part C: cascade revocation of all non-revoked assignments for this membership
        from apps.assignments.services import revoke_assignments_for_membership

        revoke_assignments_for_membership(
            membership_id=membership.id,
            actor=actor,
            reason="Membership ended",
            at_time=now,
            correlation_id=correlation_id,
            operation_source=AuditOperationSource.INTERACTIVE,
        )

        metadata = {
            "organization_code": membership.organization.code,
            "user_email": membership.user.email,
            "previous_status": previous_status,
            "resulting_status": "ended",
            "ended_at": now.isoformat(),
        }
        if reason:
            metadata["reason"] = str(reason).strip()

        record_audit_event(
            action=AuditAction.MEMBERSHIP_ENDED,
            target_type=AuditTargetType.MEMBERSHIP,
            target_id=membership.id,
            target_repr=f"{membership.organization.code}:{membership.user.email}",
            actor=actor,
            organization_id=membership.organization_id,
            operation_source=AuditOperationSource.INTERACTIVE,
            correlation_id=correlation_id,
            metadata=metadata,
        )

    return membership


def restore_membership(
    *,
    actor: Any,
    membership_id: uuid.UUID | str,
    correlation_id: uuid.UUID | str | None = None,
) -> OrganizationMembership:
    """Explicitly restore an ended membership on the existing unique row.

    Preserves existing membership_type and assigned role without mutation.
    Captures prior joined_at and ended_at timestamps in append-only audit metadata
    before setting new joined_at and clearing ended_at.
    """
    _validate_actor(actor)

    with transaction.atomic():
        org, membership, tenant_admins = _lock_membership_target(membership_id)

        if membership.organization.status != OrganizationStatus.ACTIVE:
            raise OrganizationNotActiveError(
                "Cannot restore membership in an organization that is not active.",
                code="ORGANIZATION_NOT_ACTIVE",
            )

        if membership.user.status != UserStatus.ACTIVE or not membership.user.is_active:
            raise UserInactiveCannotRestoreError(
                "Cannot restore membership for an inactive user.",
                code="USER_INACTIVE_CANNOT_RESTORE",
            )

        if membership.status != MembershipStatus.ENDED:
            raise MembershipNotEndedError(
                f"Only ended memberships can be restored; current status is '{membership.status}'.",
                code="MEMBERSHIP_NOT_ENDED",
            )

        prior_joined_at = membership.joined_at.isoformat() if membership.joined_at else ""
        prior_ended_at = membership.ended_at.isoformat() if membership.ended_at else ""
        new_joined_at = timezone.now()

        membership.status = MembershipStatus.ACTIVE
        membership.joined_at = new_joined_at
        membership.ended_at = None
        # Preserve assigned role, do not reset

        membership.save(update_fields=["status", "joined_at", "ended_at", "updated_at"])

        record_audit_event(
            action=AuditAction.MEMBERSHIP_RESTORED,
            target_type=AuditTargetType.MEMBERSHIP,
            target_id=membership.id,
            target_repr=f"{membership.organization.code}:{membership.user.email}",
            actor=actor,
            organization_id=membership.organization_id,
            operation_source=AuditOperationSource.INTERACTIVE,
            correlation_id=correlation_id,
            metadata={
                "organization_code": membership.organization.code,
                "user_email": membership.user.email,
                "prior_joined_at": prior_joined_at,
                "prior_ended_at": prior_ended_at,
                "new_joined_at": new_joined_at.isoformat(),
                "membership_type": membership.membership_type,
            },
        )

    return membership
