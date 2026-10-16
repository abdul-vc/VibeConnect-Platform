"""User Invitations Domain Models (Phase 3C).

Stores hashed, one-use invitation tokens with server-side expiry,
tenant boundary isolation, and audit log integration.
Plaintext tokens are NEVER stored in the database or logs.
"""

import hashlib
import secrets
import uuid
from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone

from apps.organizations.models import MembershipType, Organization


def hash_token(raw_token: str) -> str:
    """Return SHA-256 hex digest of a raw invitation token."""
    return hashlib.sha256(raw_token.strip().encode("utf-8")).hexdigest()


def generate_invitation_token() -> tuple[str, str]:
    """Generate a URL-safe raw token and its SHA-256 hash.

    Returns:
        tuple[str, str]: (raw_token, token_hash)
    """
    raw_token = secrets.token_urlsafe(32)
    return raw_token, hash_token(raw_token)


class InvitationStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    ACCEPTED = "accepted", "Accepted"
    EXPIRED = "expired", "Expired"
    REVOKED = "revoked", "Revoked"


class UserInvitation(models.Model):
    """Secure, hashed single-use user invitation record."""

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="user_invitations",
    )
    product = models.ForeignKey(
        "product_registry.Product",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="user_invitations",
    )
    email = models.EmailField(
        max_length=254,
        db_index=True,
    )
    role = models.ForeignKey(
        "access_control.Role",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="user_invitations",
    )
    membership_type = models.CharField(
        max_length=20,
        choices=MembershipType.choices,
        default=MembershipType.MEMBER,
    )
    token_hash = models.CharField(
        max_length=128,
        db_index=True,
        help_text="SHA-256 digest of the one-use invitation token.",
    )
    status = models.CharField(
        max_length=20,
        choices=InvitationStatus.choices,
        default=InvitationStatus.PENDING,
        db_index=True,
    )
    expires_at = models.DateTimeField(
        db_index=True,
    )
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="sent_invitations",
    )
    accepted_at = models.DateTimeField(
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "user_invitations"
        verbose_name = "User Invitation"
        verbose_name_plural = "User Invitations"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "email"],
                condition=Q(status="pending"),
                name="uniq_pending_invitation_per_org_email",
            ),
        ]

    def is_expired(self) -> bool:
        """Check if invitation has expired past its validity window."""
        return timezone.now() >= self.expires_at

    def __str__(self) -> str:
        return f"Invitation for {self.email} to {self.organization_id} [{self.status}]"
