"""Access Requests & Approvals Domain Models (Phase 3F).

Provides schema for access requests, decision logging, ceiling validation,
and immutable append-only decision auditability.
"""

import uuid
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from apps.organizations.models import Organization
from apps.product_registry.models import Product


class AccessRequestStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    APPROVED = "approved", "Approved"
    DENIED = "denied", "Denied"
    CANCELLED = "cancelled", "Cancelled"


class AccessRequestDecisionType(models.TextChoices):
    APPROVED = "approved", "Approved"
    DENIED = "denied", "Denied"


class AccessRequest(models.Model):
    """Product access request initiated by a tenant member or administrator."""

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="access_requests",
    )
    requester = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="access_requests",
    )
    product = models.ForeignKey(
        Product,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="access_requests",
    )
    status = models.CharField(
        max_length=20,
        choices=AccessRequestStatus.choices,
        default=AccessRequestStatus.PENDING,
        db_index=True,
    )
    requested_modules = models.JSONField(
        default=list,
        blank=True,
        help_text="Optional list of module IDs requested with the product.",
    )
    reason = models.TextField(
        blank=True,
        default="",
        help_text="Justification provided by requester for access.",
    )
    requested_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "access_requests"
        verbose_name = "Access Request"
        verbose_name_plural = "Access Requests"
        ordering = ["-requested_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "requester", "product"],
                condition=Q(status="pending"),
                name="uniq_pending_access_request_per_user_product",
            ),
        ]

    def __str__(self) -> str:
        return f"AccessRequest {self.id} [{self.status}] by {self.requester_id} for {self.product_id}"


class AccessRequestDecision(models.Model):
    """Immutable, append-only decision audit record on an access request."""

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    request = models.ForeignKey(
        AccessRequest,
        on_delete=models.CASCADE,
        related_name="decisions",
    )
    approver = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="access_decisions",
    )
    decision = models.CharField(
        max_length=20,
        choices=AccessRequestDecisionType.choices,
        db_index=True,
    )
    reason = models.TextField(
        blank=True,
        default="",
        help_text="Mandatory explanation on denial; optional on approval.",
    )
    decided_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "access_request_decisions"
        verbose_name = "Access Request Decision"
        verbose_name_plural = "Access Request Decisions"
        ordering = ["decided_at"]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError("AccessRequestDecision records are append-only and cannot be modified.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("AccessRequestDecision records are immutable and cannot be deleted.")

    def __str__(self) -> str:
        return f"Decision {self.decision} on Request {self.request_id} by {self.approver_id}"
