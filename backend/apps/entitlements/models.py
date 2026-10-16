"""Entitlements Domain Models.

Implements OrganizationProductEntitlement mapping between active Organizations
and active Products with strict lifecycle transitions and conditional uniqueness.
"""

import uuid
from django.conf import settings
from django.db import models


class EntitlementStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    ACTIVE = "active", "Active"
    SUSPENDED = "suspended", "Suspended"
    REVOKED = "revoked", "Revoked"


ALLOWED_ENTITLEMENT_TRANSITIONS: dict[str, set[str]] = {
    EntitlementStatus.DRAFT: {
        EntitlementStatus.ACTIVE,
        EntitlementStatus.REVOKED,
    },
    EntitlementStatus.ACTIVE: {
        EntitlementStatus.SUSPENDED,
        EntitlementStatus.REVOKED,
    },
    EntitlementStatus.SUSPENDED: {
        EntitlementStatus.ACTIVE,
        EntitlementStatus.REVOKED,
    },
    EntitlementStatus.REVOKED: set(),
}


class OrganizationProductEntitlement(models.Model):
    """Associative model representing an organization's entitlement to a product.

    Preserves closed historical evidence: revoked records remain permanently read-only,
    while future re-purchases can register a new draft record for the same pair.
    """

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.PROTECT,
        related_name="product_entitlements",
    )
    product = models.ForeignKey(
        "product_registry.Product",
        on_delete=models.PROTECT,
        related_name="organization_entitlements",
    )
    status = models.CharField(
        max_length=20,
        choices=EntitlementStatus.choices,
        default=EntitlementStatus.DRAFT,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_entitlements",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="updated_entitlements",
    )

    class Meta:
        db_table = "organization_product_entitlements"
        ordering = ["-created_at", "-id"]
        verbose_name = "Organization Product Entitlement"
        verbose_name_plural = "Organization Product Entitlements"
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "product"],
                condition=~models.Q(status=EntitlementStatus.REVOKED),
                name="org_product_open_entitlement_uniq",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    status__in=[
                        EntitlementStatus.DRAFT,
                        EntitlementStatus.ACTIVE,
                        EntitlementStatus.SUSPENDED,
                        EntitlementStatus.REVOKED,
                    ]
                ),
                name="org_product_entitlement_status_valid",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.organization_id} - {self.product_id} ({self.status})"
