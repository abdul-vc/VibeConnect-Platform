"""User Product and Module Assignments Domain Models.

Defines UserProductAssignment (the authoritative seat allocation record)
and UserModuleAssignment for the VibeConnect platform.
"""

import uuid
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone


class AssignmentImmutabilityError(ValidationError):
    """Raised when an attempt is made to mutate immutable identity fields of an assignment."""
    pass


class MembershipValidationError(ValidationError):
    """Raised when membership organization or user does not match the assignment."""
    pass


class AssignmentStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    SUSPENDED = "suspended", "Suspended"
    REVOKED = "revoked", "Revoked"


# Identity fields that cannot be altered after creation
_ASSIGNMENT_IMMUTABLE_FIELDS = {
    "organization_id",
    "user_id",
    "membership_id",
    "product_id",
    "assigned_at",
    "created_by_id",
}
_ASSIGNMENT_IMMUTABLE_PYTHON_NAMES = {
    "organization",
    "user",
    "membership",
    "product",
    "assigned_at",
    "created_by",
}


class UserProductAssignment(models.Model):
    """Authoritative seat allocation and user product assignment record.

    Represents an individual user's seat allocation to an entitled catalog Product.
    An assignment row in status 'active' or 'suspended' reserves exactly 1 seat
    in the governing subscription seat pool. A 'revoked' assignment releases the seat.

    Intentionally Deferred Invariants (enforced in service layer in subsequent parts):
    - target membership must be active;
    - target product must be subscription-entitled;
    - seat availability must be validated;
    - lifecycle transitions must be service-controlled;
    - audit events must be written transactionally.
    """

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        help_text="Globally unique identifier for the seat assignment.",
    )
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.PROTECT,
        null=False,
        blank=False,
        db_index=True,
        related_name="user_product_assignments",
        help_text="Organization owning the seat allocation.",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=False,
        blank=False,
        db_index=True,
        related_name="user_product_assignments",
        help_text="Central platform user assigned to the product.",
    )
    membership = models.ForeignKey(
        "organizations.OrganizationMembership",
        on_delete=models.PROTECT,
        null=False,
        blank=False,
        db_index=True,
        related_name="user_product_assignments",
        help_text="Active organization membership anchoring the user to this tenant.",
    )
    product = models.ForeignKey(
        "product_registry.Product",
        on_delete=models.PROTECT,
        null=False,
        blank=False,
        db_index=True,
        related_name="user_product_assignments",
        help_text="Entitled product catalog item.",
    )
    status = models.CharField(
        max_length=20,
        choices=AssignmentStatus.choices,
        default=AssignmentStatus.ACTIVE,
        null=False,
        blank=False,
        db_index=True,
        help_text="Lifecycle state: active, suspended, or revoked.",
    )
    assigned_at = models.DateTimeField(
        default=timezone.now,
        editable=False,
        null=False,
        help_text="Timestamp when the product was initially assigned.",
    )
    last_suspended_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp of most recent suspension. Preserved permanently across reactivation.",
    )
    last_reactivated_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp of most recent reactivation.",
    )
    revoked_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp when the assignment was terminated.",
    )
    suspension_reason = models.CharField(
        max_length=500,
        blank=True,
        default="",
        help_text="Reason for the most recent suspension. Preserved across reactivation.",
    )
    revocation_reason = models.CharField(
        max_length=500,
        blank=True,
        default="",
        help_text="Reason for termination.",
    )
    launch_console = models.CharField(
        max_length=50,
        blank=True,
        default="",
        help_text="Selected launch console destination for product ('tenant_console', 'normal_user_console').",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=False,
        blank=False,
        editable=False,
        related_name="+",
        help_text="User who created the assignment.",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=False,
        blank=False,
        related_name="+",
        help_text="User who last updated the assignment.",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        editable=False,
        help_text="Record creation timestamp.",
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        editable=False,
        help_text="Record last modification timestamp.",
    )

    class Meta:
        db_table = "user_product_assignments"
        verbose_name = "User Product Assignment"
        verbose_name_plural = "User Product Assignments"
        ordering = ["-assigned_at", "-id"]
        indexes = [
            models.Index(fields=["organization", "product", "status"], name="assign_org_prod_stat_idx"),
            models.Index(fields=["organization", "user", "status"], name="assign_org_user_stat_idx"),
            models.Index(fields=["user", "status"], name="assign_user_stat_idx"),
            models.Index(fields=["membership", "status"], name="assign_membership_stat_idx"),
            models.Index(fields=["-assigned_at", "-id"], name="assign_time_id_idx"),
        ]
        constraints = [
            # A. Valid status constraint
            models.CheckConstraint(
                condition=models.Q(status__in=AssignmentStatus.values),
                name="assign_status_valid",
            ),
            # B. Revoked timestamp consistency:
            # status='revoked' requires revoked_at IS NOT NULL;
            # status!='revoked' requires revoked_at IS NULL.
            models.CheckConstraint(
                condition=(
                    (models.Q(status="revoked") & models.Q(revoked_at__isnull=False))
                    | (~models.Q(status="revoked") & models.Q(revoked_at__isnull=True))
                ),
                name="assign_revoked_at_sync",
            ),
            # C. Suspension timestamp requirement:
            # status='suspended' requires last_suspended_at IS NOT NULL.
            # Active and revoked assignments may retain historical last_suspended_at.
            models.CheckConstraint(
                condition=(
                    (models.Q(status="suspended") & models.Q(last_suspended_at__isnull=False))
                    | ~models.Q(status="suspended")
                ),
                name="assign_suspended_at_sync",
            ),
            # D. Open-assignment uniqueness:
            # Only one open assignment may exist for (organization, user, product) where status != 'revoked'.
            models.UniqueConstraint(
                fields=["organization", "user", "product"],
                condition=~models.Q(status="revoked"),
                name="unique_open_user_product_assignment",
            ),
        ]

    def _validate_membership_consistency(self):
        """Ensure membership.organization == self.organization and membership.user == self.user."""
        if self.membership_id:
            # Check foreign key ID values
            membership_org_id = getattr(self.membership, "organization_id", None)
            membership_user_id = getattr(self.membership, "user_id", None)
            if membership_org_id and membership_org_id != self.organization_id:
                raise MembershipValidationError("Membership organization does not match assignment organization.")
            if membership_user_id and membership_user_id != self.user_id:
                raise MembershipValidationError("Membership user does not match assignment user.")

    def clean(self):
        super().clean()
        self._validate_membership_consistency()

    def save(self, *args, **kwargs):
        # Immutability enforcement on existing instances
        if not self._state.adding and self.pk:
            update_fields = kwargs.get("update_fields")
            if update_fields is not None:
                normalized = set()
                for f in update_fields:
                    normalized.add(f)
                    if f.endswith("_id"):
                        normalized.add(f[:-3])
                    else:
                        normalized.add(f + "_id")
                blocked = normalized & (_ASSIGNMENT_IMMUTABLE_FIELDS | _ASSIGNMENT_IMMUTABLE_PYTHON_NAMES)
                if blocked:
                    raise AssignmentImmutabilityError(
                        f"Immutable assignment field(s) cannot be updated: "
                        f"{', '.join(sorted(blocked - {'id', 'id_id'}))}."
                    )
            else:
                persisted = (
                    UserProductAssignment.objects
                    .filter(pk=self.pk)
                    .values(*_ASSIGNMENT_IMMUTABLE_FIELDS)
                    .first()
                )
                if persisted is not None:
                    for field in _ASSIGNMENT_IMMUTABLE_FIELDS:
                        current_val = getattr(self, field)
                        persisted_val = persisted[field]
                        if current_val != persisted_val:
                            raise AssignmentImmutabilityError(
                                f"Field '{field}' is immutable and cannot be changed after creation."
                            )

        self._validate_membership_consistency()

        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.user_id} -> {self.product_id} [{self.status}]"


class UserModuleAssignment(models.Model):
    """Individual module assignment under a parent product seat assignment.

    Represents module-level entitlement toggling for an assigned user.
    Module assignments never consume seats independently.
    """

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        help_text="Globally unique identifier for the module assignment.",
    )
    assignment = models.ForeignKey(
        UserProductAssignment,
        on_delete=models.CASCADE,
        null=False,
        blank=False,
        db_index=True,
        related_name="module_assignments",
        help_text="Parent product seat assignment.",
    )
    module = models.ForeignKey(
        "product_registry.ProductModule",
        on_delete=models.PROTECT,
        null=False,
        blank=False,
        db_index=True,
        related_name="user_module_assignments",
        help_text="Assigned module from the product's catalog.",
    )
    is_enabled = models.BooleanField(
        default=True,
        null=False,
        blank=False,
        db_index=True,
        help_text="Designates whether the user has access to this module.",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        editable=False,
        help_text="Record creation timestamp.",
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        editable=False,
        help_text="Record last modification timestamp.",
    )

    class Meta:
        db_table = "user_module_assignments"
        verbose_name = "User Module Assignment"
        verbose_name_plural = "User Module Assignments"
        ordering = ["module__code", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["assignment", "module"],
                name="unique_assignment_module",
            ),
        ]

    def __str__(self) -> str:
        return f"Assignment {self.assignment_id} -> Module {self.module_id} (enabled={self.is_enabled})"
