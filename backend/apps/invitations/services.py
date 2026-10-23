"""User Invitations Domain Services (Phase 3C).

Provides secure invitation issuance, token hashing, server-side validation,
atomic activation, existing-user membership linking, and audit logging.
"""

from datetime import timedelta
import logging
from typing import Any
import uuid

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import validate_email
from django.db import transaction
from django.utils import timezone

from apps.auditlog.models import AuditAction, AuditOperationSource, AuditTargetType
from apps.auditlog.services import record_audit_event
from apps.identity.models import UserStatus
from apps.invitations.models import (
    InvitationStatus,
    UserInvitation,
    generate_invitation_token,
    hash_token,
)
from apps.notifications.services import send as notification_send
from apps.organizations.models import (
    MembershipStatus,
    MembershipType,
    Organization,
    OrganizationMembership,
)

logger = logging.getLogger(__name__)
PlatformUser = get_user_model()


class InvitationError(Exception):
    """Base exception for invitation domain operations."""

    def __init__(self, message: str, code: str = "INVITATION_ERROR"):
        super().__init__(message)
        self.message = message
        self.code = code


class InvitationNotFoundError(InvitationError):
    def __init__(self, message: str = "Invalid or unrecognized invitation link."):
        super().__init__(message, code="INVITATION_NOT_FOUND")


class InvitationAlreadyUsedError(InvitationError):
    def __init__(self, message: str = "This invitation has already been accepted."):
        super().__init__(message, code="INVITATION_ALREADY_USED")


class InvitationExpiredError(InvitationError):
    def __init__(self, message: str = "This invitation has expired."):
        super().__init__(message, code="INVITATION_EXPIRED")


class InvitationRevokedError(InvitationError):
    def __init__(self, message: str = "This invitation has been revoked."):
        super().__init__(message, code="INVITATION_REVOKED")


class DuplicateInvitationError(InvitationError):
    def __init__(self, message: str = "An active invitation for this email already exists."):
        super().__init__(message, code="DUPLICATE_INVITATION")


class InvitationValidationError(InvitationError):
    def __init__(self, message: str, code: str = "INVALID_INVITATION_DATA"):
        super().__init__(message, code=code)


def issue_invitation(
    *,
    organization: Organization,
    email: str,
    full_name: str = "",
    role: Any = None,
    membership_type: str = MembershipType.MEMBER,
    product: Any = None,
    product_ids: list[str] | None = None,
    module_ids: list[str] | None = None,
    invited_by: Any = None,
    expiry_days: int = 7,
) -> tuple[UserInvitation, str]:
    """Issue a new hashed user invitation and dispatch email.

    Args:
        organization: Target organization.
        email: Recipient email address.
        full_name: Optional recipient full name.
        role: Optional administrative Role.
        membership_type: Functional membership type (member or tenant_admin).
        product: Optional product tie for direct entitlement.
        product_ids: Optional list of product IDs to pre-assign upon onboarding/activation.
        module_ids: Optional list of module IDs to pre-assign upon onboarding/activation.
        invited_by: PlatformUser actor issuing the invitation.
        expiry_days: Days before token expires (default: 7).

    Returns:
        tuple[UserInvitation, str]: The saved invitation model and raw single-use token.
    """
    clean_email = email.strip().lower()
    try:
        validate_email(clean_email)
    except DjangoValidationError:
        raise InvitationValidationError("A valid email address is required.", code="INVALID_EMAIL")

    if membership_type not in MembershipType.values:
        raise InvitationValidationError(f"Invalid membership_type: {membership_type}")

    # Enforce role-membership constraint: tenant_admin requires role; member requires no role
    if membership_type == MembershipType.TENANT_ADMIN and not role:
        raise InvitationValidationError("Tenant admin invitations require an assigned administrative role.")
    if membership_type == MembershipType.MEMBER and role:
        raise InvitationValidationError("Regular member invitations cannot have an administrative role.")

    # Check for existing pending invitation
    existing = UserInvitation.objects.filter(
        organization=organization,
        email=clean_email,
        status=InvitationStatus.PENDING,
    ).first()

    if existing:
        if existing.is_expired():
            existing.status = InvitationStatus.EXPIRED
            existing.save(update_fields=["status", "updated_at"])
        else:
            raise DuplicateInvitationError(
                "An active invitation for this email already exists in this organization."
            )

    raw_token, token_hash = generate_invitation_token()
    expires_at = timezone.now() + timedelta(days=expiry_days)

    if product is None and product_ids:
        from apps.product_registry.models import Product
        product = Product.objects.filter(id=product_ids[0]).first()

    invitation = UserInvitation.objects.create(
        organization=organization,
        full_name=full_name.strip() if full_name else "",
        product=product,
        product_ids=product_ids or [],
        module_ids=module_ids or [],
        email=clean_email,
        role=role,
        membership_type=membership_type,
        token_hash=token_hash,
        status=InvitationStatus.PENDING,
        expires_at=expires_at,
        invited_by=invited_by,
    )

    # Derive role display name
    if membership_type == MembershipType.TENANT_ADMIN:
        role_name = role.name if role and hasattr(role, "name") else "Tenant Administrator"
    else:
        role_name = role.name if role and hasattr(role, "name") else "Member"

    # Construct activation link from configured frontend base URL and raw single-use token
    frontend_base = getattr(settings, "FRONTEND_BASE_URL", "").rstrip("/")
    activation_url = f"{frontend_base}/invitations/accept/{raw_token}"

    body_template = (
        "Hello,\n\n"
        "You have been invited to join {{ org_name }} on VibeConnect as a {{ role_name }}.\n\n"
        "Please click the secure link below to activate your account and establish your password:\n"
        "{{ activation_url }}\n\n"
        "This invitation link is single-use and will expire on {{ expires_at }}.\n"
        "You must set your own password upon visiting this link to complete your account activation.\n\n"
        "If you did not expect this invitation, please ignore this email."
    )

    # Dispatch notification and track delivery
    try:
        delivery = notification_send(
            template_code="user_invitation",
            recipient_email=clean_email,
            context={
                "org_name": organization.name,
                "org_code": organization.code,
                "role_name": role_name,
                "activation_url": activation_url,
                "expires_at": str(invitation.expires_at),
                "body_template": body_template,
            },
            execute_sync=True,
        )
        if delivery and delivery.status == "failed":
            logger.error(
                "Invitation notification delivery permanently failed for invitation %s: %s",
                invitation.id,
                delivery.failure_reason,
            )
    except Exception as exc:
        logger.error(
            "Invitation notification delivery dispatch failed for invitation %s: %s",
            invitation.id,
            exc,
        )
        raise

    # Record audit event
    record_audit_event(
        action=AuditAction.INVITATION_ISSUED,
        target_type=AuditTargetType.INVITATION,
        target_id=invitation.id,
        target_repr=f"Invitation for {clean_email} to {organization.code}",
        actor=invited_by,
        organization_id=organization.id,
        operation_source=AuditOperationSource.INTERACTIVE,
        metadata={
            "invitation_id": str(invitation.id),
            "email": clean_email,
            "organization_id": str(organization.id),
            "organization_code": organization.code,
            "membership_type": membership_type,
        },
    )

    return invitation, raw_token


def validate_invitation(raw_token: str) -> UserInvitation:
    """Validate a raw invitation token and enforce server-side expiration.

    Args:
        raw_token: Raw URL-safe token.

    Returns:
        UserInvitation: Validated invitation record.
    """
    if not raw_token or not raw_token.strip():
        raise InvitationNotFoundError()

    token_hash = hash_token(raw_token)
    invitation = (
        UserInvitation.objects.select_related("organization", "role")
        .filter(token_hash=token_hash)
        .first()
    )

    if not invitation:
        raise InvitationNotFoundError()

    if invitation.status == InvitationStatus.ACCEPTED:
        raise InvitationAlreadyUsedError()

    if invitation.status == InvitationStatus.REVOKED:
        raise InvitationRevokedError()

    if invitation.is_expired() or invitation.status == InvitationStatus.EXPIRED:
        if invitation.status != InvitationStatus.EXPIRED:
            invitation.status = InvitationStatus.EXPIRED
            invitation.save(update_fields=["status", "updated_at"])
        raise InvitationExpiredError()

    return invitation


def accept_invitation(
    *,
    raw_token: str,
    password: str,
    full_name: str = "",
) -> dict[str, Any]:
    """Atomically accept an invitation, set password, and create/link account.

    Args:
        raw_token: The raw token string.
        password: New account password.
        full_name: Invitee full name.

    Returns:
        dict: Summary of user and organization identity.
    """
    if not raw_token or not raw_token.strip():
        raise InvitationNotFoundError()

    token_hash = hash_token(raw_token)

    with transaction.atomic():
        # Lock invitation row to eliminate double-spend concurrency
        invitation = (
            UserInvitation.objects.select_for_update(of=("self",))
            .select_related("organization", "role")
            .filter(token_hash=token_hash)
            .first()
        )

        if not invitation:
            raise InvitationNotFoundError()

        if invitation.status == InvitationStatus.ACCEPTED:
            raise InvitationAlreadyUsedError()

        if invitation.status == InvitationStatus.REVOKED:
            raise InvitationRevokedError()

        if invitation.is_expired():
            invitation.status = InvitationStatus.EXPIRED
            invitation.save(update_fields=["status", "updated_at"])
            raise InvitationExpiredError()

        # Validate password rules using Django standard validators
        try:
            validate_password(password)
        except DjangoValidationError as exc:
            raise InvitationValidationError("; ".join(exc.messages), code="INVALID_PASSWORD")

        # Create or retrieve PlatformUser
        clean_email = invitation.email.strip().lower()
        user = PlatformUser.objects.filter(email__iexact=clean_email).first()

        resolved_name = (full_name.strip() if full_name else "") or (invitation.full_name or "")
        if user:
            # Existing account in system (cross-tenant user or inactive stub)
            if not user.is_active or not user.has_usable_password():
                user.set_password(password)
                user.is_active = True
                user.status = UserStatus.ACTIVE
            if resolved_name and not user.full_name:
                user.full_name = resolved_name
            user.save()
        else:
            user = PlatformUser.objects.create_user(
                email=clean_email,
                password=password,
                full_name=resolved_name,
                is_active=True,
                status=UserStatus.ACTIVE,
            )

        # Create or reactivate OrganizationMembership
        membership = OrganizationMembership.objects.filter(
            organization=invitation.organization,
            user=user,
        ).first()

        if membership:
            membership.status = MembershipStatus.ACTIVE
            membership.membership_type = invitation.membership_type
            membership.role = invitation.role
            membership.ended_at = None
            membership.save()
        else:
            membership = OrganizationMembership.objects.create(
                organization=invitation.organization,
                user=user,
                membership_type=invitation.membership_type,
                role=invitation.role,
                status=MembershipStatus.ACTIVE,
                joined_at=timezone.now(),
            )

        # Mark invitation accepted
        invitation.status = InvitationStatus.ACCEPTED
        invitation.accepted_at = timezone.now()
        invitation.save()

        # Provision pre-assigned products and modules
        p_ids = list(invitation.product_ids) if invitation.product_ids else []
        if not p_ids and invitation.product_id:
            p_ids = [str(invitation.product_id)]
        m_ids = list(invitation.module_ids) if invitation.module_ids else []

        if p_ids:
            from apps.assignments.services.assignment_services import assign_user_to_product
            from apps.product_registry.models import ProductModule
            for pid in p_ids:
                try:
                    prod_mods = list(
                        ProductModule.objects.filter(
                            product_id=pid,
                            id__in=m_ids,
                            status="active",
                        ).values_list("id", flat=True)
                    ) if m_ids else None

                    assign_user_to_product(
                        organization_id=invitation.organization_id,
                        user_id=user.id,
                        product_id=pid,
                        module_ids=prod_mods,
                        membership_id=membership.id,
                        actor=user,
                    )
                except Exception as exc:
                    logger.warning("Auto-assignment for product %s on invitation accept: %s", pid, exc)

        # Void any duplicate pending invitations for the same email and organization
        UserInvitation.objects.filter(
            organization=invitation.organization,
            email=clean_email,
            status=InvitationStatus.PENDING,
        ).exclude(id=invitation.id).update(status=InvitationStatus.EXPIRED)

        # Audit log event
        record_audit_event(
            action=AuditAction.INVITATION_ACCEPTED,
            target_type=AuditTargetType.INVITATION,
            target_id=invitation.id,
            target_repr=f"Invitation accepted for {clean_email} to {invitation.organization.code}",
            actor=user,
            organization_id=invitation.organization.id,
            operation_source=AuditOperationSource.INTERACTIVE,
            metadata={
                "invitation_id": str(invitation.id),
                "email": clean_email,
                "organization_id": str(invitation.organization.id),
                "organization_code": invitation.organization.code,
                "user_id": str(user.id),
            },
        )

        return {
            "user_id": str(user.id),
            "email": user.email,
            "full_name": user.full_name,
            "organization_id": str(invitation.organization.id),
            "organization_code": invitation.organization.code,
            "organization_name": invitation.organization.name,
        }
