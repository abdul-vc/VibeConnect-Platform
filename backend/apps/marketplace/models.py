"""Marketplace Domain Models (Phase 6A Stage 3).

Defines the TenantProductRequest model for organization-level product adoption and
plan tier requests initiated by Tenant Administrators.
"""

import uuid
from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.organizations.models import Organization
from apps.product_registry.models import Product


class TenantProductRequestStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    APPROVED = "approved", "Approved"
    REJECTED = "rejected", "Rejected"
    CANCELLED = "cancelled", "Cancelled"


class TenantProductRequest(models.Model):
    """Organization-level product adoption or enterprise tier request initiated by a Tenant Admin.

    Governs commercial interest and adoption workflows prior to organization entitlement.
    """

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="tenant_product_requests",
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.PROTECT,
        related_name="tenant_product_requests",
    )
    requested_plan = models.ForeignKey(
        "plans.PlanVersion",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="tenant_product_requests",
        help_text="Optional commercial plan tier requested by the tenant.",
    )
    requester = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="submitted_tenant_product_requests",
        help_text="Tenant Administrator who submitted the adoption request.",
    )
    status = models.CharField(
        max_length=20,
        choices=TenantProductRequestStatus.choices,
        default=TenantProductRequestStatus.PENDING,
        db_index=True,
    )
    notes = models.TextField(
        blank=True,
        default="",
        help_text="Optional notes or requirements from the Tenant Administrator.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "tenant_product_requests"
        verbose_name = "Tenant Product Request"
        verbose_name_plural = "Tenant Product Requests"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "product"],
                condition=Q(status="pending"),
                name="uniq_pending_tenant_product_request",
            ),
        ]

    def __str__(self) -> str:
        return f"TenantProductRequest {self.id} [{self.status}] org={self.organization.code} product={self.product.code}"
