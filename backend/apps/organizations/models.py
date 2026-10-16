"""Organizations Domain Models.

Defines the central Organization catalog and lifecycle state machine for VibeConnect.
"""

import uuid
from django.conf import settings
from django.db import models
from django.db.models import Q
from django.db.models.functions import Lower


class OrganizationStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    ACTIVE = "active", "Active"
    SUSPENDED = "suspended", "Suspended"
    RETIRED = "retired", "Retired"


ALLOWED_STATUS_TRANSITIONS: dict[OrganizationStatus, set[OrganizationStatus]] = {
    OrganizationStatus.DRAFT: {
        OrganizationStatus.ACTIVE,
        OrganizationStatus.RETIRED,
    },
    OrganizationStatus.ACTIVE: {
        OrganizationStatus.SUSPENDED,
        OrganizationStatus.RETIRED,
    },
    OrganizationStatus.SUSPENDED: {
        OrganizationStatus.ACTIVE,
        OrganizationStatus.RETIRED,
    },
    OrganizationStatus.RETIRED: set(),  # Terminal state: zero further transitions
}


class Organization(models.Model):
    """Registered organization account managed by the VibeConnect control plane."""

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    code = models.CharField(
        max_length=50,
    )
    name = models.CharField(
        max_length=150,
    )
    description = models.CharField(
        max_length=1000,
        blank=True,
        default="",
    )
    status = models.CharField(
        max_length=20,
        choices=OrganizationStatus.choices,
        default=OrganizationStatus.DRAFT,
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
    )
    updated_at = models.DateTimeField(
        auto_now=True,
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_organizations",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="updated_organizations",
    )

    class Meta:
        db_table = "organizations"
        verbose_name = "Organization"
        verbose_name_plural = "Organizations"
        ordering = ["-created_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                Lower("code"),
                name="org_code_ci_uniq",
            ),
            models.CheckConstraint(
                condition=Q(code=Lower("code")),
                name="org_code_lower",
            ),
            models.CheckConstraint(
                condition=Q(code__regex=r"^[a-z0-9]+(?:[-_][a-z0-9]+)*$"),
                name="org_code_format",
            ),
            models.CheckConstraint(
                condition=Q(status__in=OrganizationStatus.values),
                name="org_status_valid",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.code})"


class MembershipStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    SUSPENDED = "suspended", "Suspended"
    ENDED = "ended", "Ended"


class MembershipType(models.TextChoices):
    TENANT_ADMIN = "tenant_admin", "Tenant Admin"
    MEMBER = "member", "Member"


class OrganizationMembership(models.Model):
    """Tracks a PlatformUser's membership in an Organization.

    Lifecycle states: active → suspended → active (reactivatable),
    active/suspended → ended (terminal; rejoin via explicit restore).
    An ended membership cannot re-enter active/suspended without
    calling the restore service.
    """

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        help_text="Globally unique identifier for the membership record.",
    )
    organization = models.ForeignKey(
        Organization,
        on_delete=models.PROTECT,
        related_name="memberships",
        help_text="The organization this membership belongs to.",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="organization_memberships",
        help_text="The platform user who holds this membership.",
    )
    membership_type = models.CharField(
        max_length=20,
        choices=MembershipType.choices,
        default=MembershipType.MEMBER,
        help_text="Functional role this membership grants within the organization.",
    )
    status = models.CharField(
        max_length=20,
        choices=MembershipStatus.choices,
        default=MembershipStatus.ACTIVE,
        db_index=True,
        help_text="Current lifecycle state of the membership.",
    )
    joined_at = models.DateTimeField(
        help_text="Timestamp when the membership was originally created or last restored.",
    )
    ended_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp when the membership was ended (terminal unless restored).",
    )
    role = models.ForeignKey(
        "access_control.Role",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="memberships",
        help_text="Explicitly assigned administrative role. Null for regular members.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "organization_memberships"
        verbose_name = "Organization Membership"
        verbose_name_plural = "Organization Memberships"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "user"],
                name="org_membership_user_uniq",
            ),
            models.CheckConstraint(
                condition=Q(status__in=MembershipStatus.values),
                name="org_membership_status_valid",
            ),
            models.CheckConstraint(
                condition=Q(membership_type__in=MembershipType.values),
                name="org_membership_type_valid",
            ),
            # ended memberships must have ended_at set; non-ended must not
            models.CheckConstraint(
                condition=(
                    (Q(status="ended") & Q(ended_at__isnull=False))
                    | (Q(status__in=["active", "suspended"]) & Q(ended_at__isnull=True))
                ),
                name="org_membership_ended_at_sync",
            ),
            models.CheckConstraint(
                condition=(
                    (Q(membership_type=MembershipType.TENANT_ADMIN) & Q(role__isnull=False))
                    | (Q(membership_type=MembershipType.MEMBER) & Q(role__isnull=True))
                ),
                name="membership_type_role_sync",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.user_id} @ {self.organization_id} [{self.status}]"
