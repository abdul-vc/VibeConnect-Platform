"""VibeConnect User Lifecycle Services (Phase 2D Stage 2).

Provides transactional, pessimistic-locking domain services for:
- Safe user creation (non-privileged, unusable password)
- Safe profile updates (full_name only)
- User lifecycle transitions: active→suspended/disabled, suspended→active/disabled
- Terminal disabled enforcement (no transitions out of disabled)
- In-transaction row-locked protection for the final active Platform Owner
- Append-only audit trail recording
"""

from typing import Any
import uuid

from django.contrib.auth import get_user_model
from django.db import transaction

from apps.auditlog.models import AuditAction, AuditOperationSource, AuditTargetType
from apps.auditlog.services import record_audit_event
from apps.identity.constants import SYSTEM_SERVICE_ACTOR_EMAIL
from apps.identity.models import UserStatus

PlatformUser = get_user_model()


class UserServiceError(Exception):
    """Base exception for user domain service errors."""

    def __init__(self, message: str, code: str = "USER_SERVICE_ERROR"):
        super().__init__(message)
        self.message = message
        self.code = code


class UserValidationError(UserServiceError):
    """Raised when user input data fails validation."""

    def __init__(self, message: str, code: str = "INVALID_USER_DATA"):
        super().__init__(message, code=code)


class UserNotFoundError(UserServiceError):
    """Raised when a user record cannot be found."""

    def __init__(self, message: str, code: str = "USER_NOT_FOUND"):
        super().__init__(message, code=code)


class UserAlreadyExistsError(UserServiceError):
    """Raised when attempting to create a user with an already-registered email."""

    def __init__(self, message: str, code: str = "USER_ALREADY_EXISTS"):
        super().__init__(message, code=code)


class InvalidUserTransitionError(UserServiceError):
    """Raised when an invalid lifecycle transition is requested."""

    def __init__(self, message: str, code: str = "INVALID_USER_TRANSITION"):
        super().__init__(message, code=code)


class UserDisabledTerminalError(UserServiceError):
    """Raised when attempting any transition out of or on a terminal disabled user."""

    def __init__(self, message: str, code: str = "USER_DISABLED_TERMINAL"):
        super().__init__(message, code=code)


class UserAlreadyActiveError(UserServiceError):
    """Raised when attempting to reactivate an already active user."""

    def __init__(self, message: str = "User is already active.", code: str = "USER_ALREADY_ACTIVE"):
        super().__init__(message, code=code)


class LastPlatformOwnerError(UserServiceError):
    """Raised when an action would deactivate or revoke the final active Platform Owner."""

    def __init__(self, message: str, code: str = "CANNOT_DEACTIVATE_LAST_PLATFORM_OWNER"):
        super().__init__(message, code=code)


def _validate_actor(actor: Any) -> None:
    """Validate that actor is an authenticated, active platform owner."""
    if not actor or not getattr(actor, "is_authenticated", False) or not getattr(actor, "is_active", False):
        raise UserValidationError("Actor must be an active, authenticated platform user.", code="INVALID_ACTOR")
    if not getattr(actor, "is_platform_owner", False):
        raise UserValidationError("Actor must possess Platform Owner privileges.", code="INSUFFICIENT_PRIVILEGES")


def create_user(
    *,
    actor: Any,
    email: str,
    full_name: str = "",
    correlation_id: uuid.UUID | str | None = None,
) -> PlatformUser:
    """Create a new user with status=active and unusable password.

    General user creation must never grant platform-owner, staff, or superuser privileges.
    """
    _validate_actor(actor)

    if not isinstance(email, str) or not email.strip():
        raise UserValidationError("A valid email address is required.", code="INVALID_EMAIL")

    normalized_email = email.strip().lower()
    cleaned_full_name = full_name.strip() if isinstance(full_name, str) else ""

    if PlatformUser.objects.filter(email__iexact=normalized_email).exists():
        raise UserAlreadyExistsError(
            "A user with this email address already exists.",
            code="USER_ALREADY_EXISTS",
        )

    with transaction.atomic():
        user = PlatformUser(
            email=normalized_email,
            full_name=cleaned_full_name,
            status=UserStatus.ACTIVE,
            is_active=True,
            is_platform_owner=False,
            is_staff=False,
            is_superuser=False,
        )
        user.set_unusable_password()
        user.save()

        record_audit_event(
            action=AuditAction.USER_CREATED,
            target_type=AuditTargetType.USER,
            target_id=user.id,
            target_repr=user.email,
            actor=actor,
            organization_id=None,
            operation_source=AuditOperationSource.INTERACTIVE,
            correlation_id=correlation_id,
            metadata={
                "email": user.email,
                "full_name": user.full_name,
                "status": "active",
            },
        )

    return user


def update_user_profile(
    *,
    actor: Any,
    user_id: uuid.UUID | str,
    full_name: str,
    correlation_id: uuid.UUID | str | None = None,
) -> PlatformUser:
    """Safe profile update: modifies only full_name."""
    _validate_actor(actor)

    if not isinstance(full_name, str):
        raise UserValidationError("full_name must be a string.", code="INVALID_USER_DATA")

    cleaned_full_name = full_name.strip()

    with transaction.atomic():
        user = PlatformUser.objects.select_for_update().filter(pk=user_id).first()
        if not user:
            raise UserNotFoundError(f"User '{user_id}' not found.", code="USER_NOT_FOUND")

        user.full_name = cleaned_full_name
        user.save(update_fields=["full_name", "updated_at"])

        record_audit_event(
            action=AuditAction.USER_UPDATED,
            target_type=AuditTargetType.USER,
            target_id=user.id,
            target_repr=user.email,
            actor=actor,
            organization_id=None,
            operation_source=AuditOperationSource.INTERACTIVE,
            correlation_id=correlation_id,
            metadata={
                "email": user.email,
                "full_name": user.full_name,
            },
        )

    return user


def suspend_user(
    *,
    actor: Any,
    user_id: uuid.UUID | str,
    reason: str | None = None,
    correlation_id: uuid.UUID | str | None = None,
) -> PlatformUser:
    """Suspend an active user. Rejects suspension of terminal disabled or already suspended users.

    Protects the final active Platform Owner under pessimistic locking.
    """
    _validate_actor(actor)

    from apps.access_control.models import Role, RolePermission
    from apps.access_control.services.guards import evaluate_structural_last_admin
    from apps.organizations.models import MembershipStatus, MembershipType, Organization, OrganizationMembership

    # Non-locking lookup to identify organizations where target user holds active tenant_admin membership
    affected_org_ids = list(
        OrganizationMembership.objects.filter(
            user_id=user_id,
            membership_type=MembershipType.TENANT_ADMIN,
            status=MembershipStatus.ACTIVE,
        )
        .values_list("organization_id", flat=True)
        .distinct()
    )
    affected_org_ids.sort()

    with transaction.atomic():
        if affected_org_ids:
            # 1. Lock affected Organizations ordered by ID
            list(Organization.objects.select_for_update().filter(id__in=affected_org_ids).order_by("id"))
            # 2. Lock all tenant_admin memberships for those organizations ordered by ID
            locked_tenant_admins = list(
                OrganizationMembership.objects.select_for_update()
                .filter(organization_id__in=affected_org_ids, membership_type=MembershipType.TENANT_ADMIN)
                .order_by("id")
            )
            # 3. Relevant Role rows ordered by ID
            role_ids = {m.role_id for m in locked_tenant_admins if m.role_id}
            roles = list(Role.objects.select_for_update().filter(id__in=role_ids).order_by("id"))
            roles_by_id = {r.id: r for r in roles}
            # 4. Relevant RolePermission rows ordered by ID
            if role_ids:
                list(RolePermission.objects.select_for_update().filter(role_id__in=role_ids).order_by("id"))
            # 5. PlatformUser rows where required
            user_ids = {m.user_id for m in locked_tenant_admins}
            users = list(PlatformUser.objects.select_for_update().filter(id__in=user_ids).order_by("id"))
            users_by_id = {u.id: u for u in users}
            for m in locked_tenant_admins:
                if m.role_id:
                    m.role = roles_by_id.get(m.role_id)
                m.user = users_by_id.get(m.user_id)

            # Evaluate projected last-capable-Tenant-Admin invariant for every affected organization
            for org_id in affected_org_ids:
                org_admins = [m for m in locked_tenant_admins if m.organization_id == org_id]
                evaluate_structural_last_admin(
                    organization_id=org_id,
                    suspended_user_id=user_id,
                    locked_tenant_admins=org_admins,
                )

        # Lock all active qualifying human platform owners in canonical order to prevent concurrent deactivation races
        active_owners = list(
            PlatformUser.objects.select_for_update()
            .filter(is_platform_owner=True, status=UserStatus.ACTIVE)
            .exclude(email=SYSTEM_SERVICE_ACTOR_EMAIL)
            .order_by("id")
        )

        user = PlatformUser.objects.select_for_update().filter(pk=user_id).first()
        if not user:
            raise UserNotFoundError(f"User '{user_id}' not found.", code="USER_NOT_FOUND")

        if user.status == UserStatus.DISABLED:
            raise UserDisabledTerminalError(
                "Disabled user is in a terminal state and cannot be modified.",
                code="USER_DISABLED_TERMINAL",
            )

        if user.status == UserStatus.SUSPENDED:
            raise InvalidUserTransitionError(
                "User is already suspended.",
                code="INVALID_USER_TRANSITION",
            )

        if user.email == SYSTEM_SERVICE_ACTOR_EMAIL:
            raise UserValidationError(
                "System service actor cannot be suspended.",
                code="SYSTEM_ACTOR_IMMUTABLE",
            )

        if user.is_platform_owner and user.status == UserStatus.ACTIVE and user.email != SYSTEM_SERVICE_ACTOR_EMAIL:
            remaining_owners = [o for o in active_owners if o.pk != user.pk]
            if len(remaining_owners) == 0:
                raise LastPlatformOwnerError(
                    "Cannot suspend the final active Platform Owner.",
                    code="CANNOT_DEACTIVATE_LAST_PLATFORM_OWNER",
                )

        previous_status = user.status
        user.status = UserStatus.SUSPENDED
        user.is_active = False
        user.save(update_fields=["status", "is_active", "updated_at"])

        metadata = {
            "email": user.email,
            "previous_status": previous_status,
            "resulting_status": "suspended",
        }
        if reason:
            metadata["reason"] = str(reason).strip()

        record_audit_event(
            action=AuditAction.USER_SUSPENDED,
            target_type=AuditTargetType.USER,
            target_id=user.id,
            target_repr=user.email,
            actor=actor,
            organization_id=None,
            operation_source=AuditOperationSource.INTERACTIVE,
            correlation_id=correlation_id,
            metadata=metadata,
        )

    return user


def reactivate_user(
    *,
    actor: Any,
    user_id: uuid.UUID | str,
    correlation_id: uuid.UUID | str | None = None,
) -> PlatformUser:
    """Reactivate a suspended user. Only suspended→active is permitted.

    Disabled users can NEVER be reactivated.
    """
    _validate_actor(actor)

    with transaction.atomic():
        user = PlatformUser.objects.select_for_update().filter(pk=user_id).first()
        if not user:
            raise UserNotFoundError(f"User '{user_id}' not found.", code="USER_NOT_FOUND")

        if user.status == UserStatus.DISABLED:
            raise UserDisabledTerminalError(
                "Disabled user is in a terminal state and cannot be reactivated.",
                code="USER_DISABLED_TERMINAL",
            )

        if user.status == UserStatus.ACTIVE:
            raise UserAlreadyActiveError(
                "User is already active.",
                code="USER_ALREADY_ACTIVE",
            )

        previous_status = user.status
        user.status = UserStatus.ACTIVE
        user.is_active = True
        user.save(update_fields=["status", "is_active", "updated_at"])

        record_audit_event(
            action=AuditAction.USER_REACTIVATED,
            target_type=AuditTargetType.USER,
            target_id=user.id,
            target_repr=user.email,
            actor=actor,
            organization_id=None,
            operation_source=AuditOperationSource.INTERACTIVE,
            correlation_id=correlation_id,
            metadata={
                "email": user.email,
                "previous_status": previous_status,
                "resulting_status": "active",
            },
        )

    return user


def disable_user(
    *,
    actor: Any,
    user_id: uuid.UUID | str,
    reason: str | None = None,
    correlation_id: uuid.UUID | str | None = None,
) -> PlatformUser:
    """Disable an active or suspended user into the terminal disabled state.

    Protects the final active Platform Owner under pessimistic locking.
    """
    _validate_actor(actor)

    from apps.access_control.models import Role, RolePermission
    from apps.access_control.services.guards import evaluate_structural_last_admin
    from apps.organizations.models import MembershipStatus, MembershipType, Organization, OrganizationMembership

    # Non-locking lookup to identify organizations where target user holds active tenant_admin membership
    affected_org_ids = list(
        OrganizationMembership.objects.filter(
            user_id=user_id,
            membership_type=MembershipType.TENANT_ADMIN,
            status=MembershipStatus.ACTIVE,
        )
        .values_list("organization_id", flat=True)
        .distinct()
    )
    affected_org_ids.sort()

    with transaction.atomic():
        if affected_org_ids:
            # 1. Lock affected Organizations ordered by ID
            list(Organization.objects.select_for_update().filter(id__in=affected_org_ids).order_by("id"))
            # 2. Lock all tenant_admin memberships for those organizations ordered by ID
            locked_tenant_admins = list(
                OrganizationMembership.objects.select_for_update()
                .filter(organization_id__in=affected_org_ids, membership_type=MembershipType.TENANT_ADMIN)
                .order_by("id")
            )
            # 3. Relevant Role rows ordered by ID
            role_ids = {m.role_id for m in locked_tenant_admins if m.role_id}
            roles = list(Role.objects.select_for_update().filter(id__in=role_ids).order_by("id"))
            roles_by_id = {r.id: r for r in roles}
            # 4. Relevant RolePermission rows ordered by ID
            if role_ids:
                list(RolePermission.objects.select_for_update().filter(role_id__in=role_ids).order_by("id"))
            # 5. PlatformUser rows where required
            user_ids = {m.user_id for m in locked_tenant_admins}
            users = list(PlatformUser.objects.select_for_update().filter(id__in=user_ids).order_by("id"))
            users_by_id = {u.id: u for u in users}
            for m in locked_tenant_admins:
                if m.role_id:
                    m.role = roles_by_id.get(m.role_id)
                m.user = users_by_id.get(m.user_id)

            # Evaluate projected last-capable-Tenant-Admin invariant for every affected organization
            for org_id in affected_org_ids:
                org_admins = [m for m in locked_tenant_admins if m.organization_id == org_id]
                evaluate_structural_last_admin(
                    organization_id=org_id,
                    disabled_user_id=user_id,
                    locked_tenant_admins=org_admins,
                )

        # Lock all active qualifying human platform owners in canonical order
        active_owners = list(
            PlatformUser.objects.select_for_update()
            .filter(is_platform_owner=True, status=UserStatus.ACTIVE)
            .exclude(email=SYSTEM_SERVICE_ACTOR_EMAIL)
            .order_by("id")
        )

        user = PlatformUser.objects.select_for_update().filter(pk=user_id).first()
        if not user:
            raise UserNotFoundError(f"User '{user_id}' not found.", code="USER_NOT_FOUND")

        if user.status == UserStatus.DISABLED:
            raise UserDisabledTerminalError(
                "User is already disabled.",
                code="USER_DISABLED_TERMINAL",
            )

        if user.email == SYSTEM_SERVICE_ACTOR_EMAIL:
            raise UserValidationError(
                "System service actor cannot be disabled.",
                code="SYSTEM_ACTOR_IMMUTABLE",
            )

        if user.is_platform_owner and user.status == UserStatus.ACTIVE and user.email != SYSTEM_SERVICE_ACTOR_EMAIL:
            remaining_owners = [o for o in active_owners if o.pk != user.pk]
            if len(remaining_owners) == 0:
                raise LastPlatformOwnerError(
                    "Cannot disable the final active Platform Owner.",
                    code="CANNOT_DEACTIVATE_LAST_PLATFORM_OWNER",
                )

        previous_status = user.status
        user.status = UserStatus.DISABLED
        user.is_active = False
        user.save(update_fields=["status", "is_active", "updated_at"])

        metadata = {
            "email": user.email,
            "previous_status": previous_status,
            "resulting_status": "disabled",
        }
        if reason:
            metadata["reason"] = str(reason).strip()

        record_audit_event(
            action=AuditAction.USER_DISABLED,
            target_type=AuditTargetType.USER,
            target_id=user.id,
            target_repr=user.email,
            actor=actor,
            organization_id=None,
            operation_source=AuditOperationSource.INTERACTIVE,
            correlation_id=correlation_id,
            metadata=metadata,
        )

    return user


class SystemActorUnavailableError(UserServiceError):
    """Raised when the locked system service actor is missing, inactive, or misconfigured."""

    def __init__(self, message: str = "System service actor is unavailable.", code: str = "SYSTEM_ACTOR_UNAVAILABLE"):
        super().__init__(message, code=code)


def get_system_service_actor() -> PlatformUser:
    """Return the active locked system service actor.

    Fails closed when the actor is missing, inactive or invalid.
    Raises SystemActorUnavailableError. Never silently falls back to a human user.
    """
    actor_email = SYSTEM_SERVICE_ACTOR_EMAIL
    actor = PlatformUser.objects.filter(email=actor_email).first()
    if not actor:
        raise SystemActorUnavailableError(f"System service actor '{actor_email}' not found.")
    if not actor.is_active or actor.status != UserStatus.ACTIVE:
        raise SystemActorUnavailableError(f"System service actor '{actor_email}' is not active.")
    if not actor.is_staff or not actor.is_platform_owner or actor.is_superuser:
        raise SystemActorUnavailableError(f"System service actor '{actor_email}' has invalid configuration flags.")
    return actor


def anonymize_user(
    user_id: uuid.UUID | str,
    actor: Any,
    reason: str | None = None,
    correlation_id: uuid.UUID | None = None,
) -> PlatformUser:
    """Anonymize a platform user's live personal data without mutating historical audit records.

    Phase 6F-2 Implementation:
    - Replaces directly-identifying attributes (email, full_name) with pseudonymous values.
    - Sets account status to disabled and inactive, sets unusable password, clears external subject.
    - Preserves primary key UUID to maintain database referential integrity across PROTECT relationships.
    - Strictly preserves historical AuditLog rows as immutable historical fact (NO AuditLog row is deleted or modified).
    - Prevents anonymizing the last active Platform Owner.
    - Records an append-only audit log entry for the de-identification action.
    """
    _validate_actor(actor)

    with transaction.atomic():
        try:
            user = PlatformUser.objects.select_for_update().get(pk=user_id)
        except (PlatformUser.DoesNotExist, ValueError):
            raise UserNotFoundError(f"User with id '{user_id}' not found.")

        if user.email == SYSTEM_SERVICE_ACTOR_EMAIL:
            raise UserValidationError(
                "System service actor cannot be anonymized.",
                code="SYSTEM_ACTOR_IMMUTABLE",
            )

        if getattr(user, "is_platform_owner", False) and user.is_active:
            active_owners = list(
                PlatformUser.objects.select_for_update()
                .filter(is_platform_owner=True, is_active=True, status=UserStatus.ACTIVE)
                .exclude(email=SYSTEM_SERVICE_ACTOR_EMAIL)
            )
            remaining_owners = [o for o in active_owners if o.pk != user.pk]
            if len(remaining_owners) == 0:
                raise LastPlatformOwnerError(
                    "Cannot anonymize the final active Platform Owner.",
                    code="CANNOT_ANONYMIZE_LAST_PLATFORM_OWNER",
                )


        pseudonym_email = f"anonymized-{user.id}@redacted.vibeconnect.local"
        user.email = pseudonym_email
        user.full_name = "Redacted User"
        user.status = UserStatus.DISABLED
        user.is_active = False
        user.auth_provider = None
        user.external_subject_id = None
        user.set_unusable_password()

        user.save(
            update_fields=[
                "email",
                "full_name",
                "status",
                "is_active",
                "auth_provider",
                "external_subject_id",
                "password",
                "updated_at",
            ]
        )

        metadata = {
            "pseudonymized_identity": pseudonym_email,
            "audit_immutability_note": "Historical audit log rows remain immutable and unmutated.",
        }
        if reason:
            metadata["reason"] = str(reason).strip()

        record_audit_event(
            action=AuditAction.USER_ANONYMIZED,
            target_type=AuditTargetType.USER,
            target_id=user.id,
            target_repr=pseudonym_email,
            actor=actor,
            organization_id=None,
            operation_source=AuditOperationSource.INTERACTIVE,
            correlation_id=correlation_id,
            metadata=metadata,
        )

    return user

