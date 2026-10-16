"""Product Registry Domain Models.

Defines the central Product catalog and lifecycle state machine for VibeConnect.
"""

import uuid
from django.conf import settings
from django.db import models
from django.db.models import Q
from django.db.models.functions import Lower


class ProductStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    ACTIVE = "active", "Active"
    INACTIVE = "inactive", "Inactive"
    RETIRED = "retired", "Retired"


ALLOWED_STATUS_TRANSITIONS: dict[ProductStatus, set[ProductStatus]] = {
    ProductStatus.DRAFT: {ProductStatus.ACTIVE, ProductStatus.INACTIVE, ProductStatus.RETIRED},
    ProductStatus.ACTIVE: {ProductStatus.INACTIVE, ProductStatus.RETIRED},
    ProductStatus.INACTIVE: {ProductStatus.ACTIVE, ProductStatus.RETIRED},
    ProductStatus.RETIRED: set(),  # Terminal state: zero further transitions
}


class Product(models.Model):
    """Registered product/service managed by the VibeConnect control plane."""

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    code = models.CharField(
        max_length=50,
    )
    name = models.CharField(
        max_length=100,
    )
    description = models.CharField(
        max_length=1000,
        blank=True,
        default="",
    )
    status = models.CharField(
        max_length=20,
        choices=ProductStatus.choices,
        default=ProductStatus.DRAFT,
    )
    parent = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sub_products",
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
        related_name="created_products",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="updated_products",
    )

    class Meta:
        db_table = "products"
        verbose_name = "Product"
        verbose_name_plural = "Products"
        ordering = ["-created_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                Lower("code"),
                name="product_code_ci_uniq",
            ),
            models.CheckConstraint(
                condition=Q(code=Lower("code")),
                name="product_code_lower",
            ),
            models.CheckConstraint(
                condition=Q(code__regex=r"^[a-z0-9]+(?:[-_][a-z0-9]+)*$"),
                name="product_code_format",
            ),
            models.CheckConstraint(
                condition=Q(status__in=ProductStatus.values),
                name="product_status_valid",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.code})"


class CatalogStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    ACTIVE = "active", "Active"
    RETIRED = "retired", "Retired"


ALLOWED_CATALOG_STATUS_TRANSITIONS: dict[CatalogStatus, set[CatalogStatus]] = {
    CatalogStatus.DRAFT: {CatalogStatus.ACTIVE, CatalogStatus.RETIRED},
    CatalogStatus.ACTIVE: {CatalogStatus.RETIRED},
    CatalogStatus.RETIRED: set(),  # Terminal state
}


class ProductModule(models.Model):
    """Major functional area belonging to one Product."""

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.PROTECT,
        related_name="modules",
    )
    code = models.CharField(
        max_length=50,
    )
    name = models.CharField(
        max_length=100,
    )
    description = models.CharField(
        max_length=1000,
        blank=True,
        default="",
    )
    display_order = models.IntegerField(
        default=0,
    )
    status = models.CharField(
        max_length=20,
        choices=CatalogStatus.choices,
        default=CatalogStatus.DRAFT,
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
        related_name="created_product_modules",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="updated_product_modules",
    )

    class Meta:
        db_table = "product_modules"
        verbose_name = "Product Module"
        verbose_name_plural = "Product Modules"
        ordering = ["display_order", "created_at", "id"]
        constraints = [
            models.UniqueConstraint(
                models.F("product"),
                Lower("code"),
                name="module_product_code_ci_uniq",
            ),
            models.UniqueConstraint(
                models.F("product"),
                Lower("name"),
                name="module_product_name_ci_uniq",
            ),
            models.CheckConstraint(
                condition=Q(code=Lower("code")),
                name="module_code_lower",
            ),
            models.CheckConstraint(
                condition=Q(code__regex=r"^[a-z0-9]+(?:[-_][a-z0-9]+)*$"),
                name="module_code_format",
            ),
            models.CheckConstraint(
                condition=Q(status__in=CatalogStatus.values),
                name="module_status_valid",
            ),
            models.CheckConstraint(
                condition=Q(display_order__gte=0),
                name="module_display_order_non_neg",
            ),
        ]
        indexes = [
            models.Index(fields=["product", "status", "display_order", "id"], name="mod_prod_stat_order_idx"),
            models.Index(fields=["product", "-created_at", "-id"], name="mod_prod_created_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.code})"


class ProductFeature(models.Model):
    """Functional unit belonging to one ProductModule."""

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    module = models.ForeignKey(
        ProductModule,
        on_delete=models.PROTECT,
        related_name="features",
    )
    code = models.CharField(
        max_length=50,
    )
    name = models.CharField(
        max_length=100,
    )
    description = models.CharField(
        max_length=1000,
        blank=True,
        default="",
    )
    display_order = models.IntegerField(
        default=0,
    )
    status = models.CharField(
        max_length=20,
        choices=CatalogStatus.choices,
        default=CatalogStatus.DRAFT,
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
        related_name="created_product_features",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="updated_product_features",
    )

    class Meta:
        db_table = "product_features"
        verbose_name = "Product Feature"
        verbose_name_plural = "Product Features"
        ordering = ["display_order", "created_at", "id"]
        constraints = [
            models.UniqueConstraint(
                models.F("module"),
                Lower("code"),
                name="feature_module_code_ci_uniq",
            ),
            models.UniqueConstraint(
                models.F("module"),
                Lower("name"),
                name="feature_module_name_ci_uniq",
            ),
            models.CheckConstraint(
                condition=Q(code=Lower("code")),
                name="feature_code_lower",
            ),
            models.CheckConstraint(
                condition=Q(code__regex=r"^[a-z0-9]+(?:[-_][a-z0-9]+)*$"),
                name="feature_code_format",
            ),
            models.CheckConstraint(
                condition=Q(status__in=CatalogStatus.values),
                name="feature_status_valid",
            ),
            models.CheckConstraint(
                condition=Q(display_order__gte=0),
                name="feature_display_order_non_neg",
            ),
        ]
        indexes = [
            models.Index(fields=["module", "status", "display_order", "id"], name="feat_mod_stat_order_idx"),
            models.Index(fields=["module", "-created_at", "-id"], name="feat_mod_created_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.code})"


class ProductCapability(models.Model):
    """The smallest catalogued action or ability belonging to one ProductFeature."""

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    feature = models.ForeignKey(
        ProductFeature,
        on_delete=models.PROTECT,
        related_name="capabilities",
    )
    code = models.CharField(
        max_length=50,
    )
    name = models.CharField(
        max_length=100,
    )
    description = models.CharField(
        max_length=1000,
        blank=True,
        default="",
    )
    display_order = models.IntegerField(
        default=0,
    )
    status = models.CharField(
        max_length=20,
        choices=CatalogStatus.choices,
        default=CatalogStatus.DRAFT,
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
        related_name="created_product_capabilities",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="updated_product_capabilities",
    )

    class Meta:
        db_table = "product_capabilities"
        verbose_name = "Product Capability"
        verbose_name_plural = "Product Capabilities"
        ordering = ["display_order", "created_at", "id"]
        constraints = [
            models.UniqueConstraint(
                models.F("feature"),
                Lower("code"),
                name="cap_feat_code_ci_uniq",
            ),
            models.UniqueConstraint(
                models.F("feature"),
                Lower("name"),
                name="cap_feat_name_ci_uniq",
            ),
            models.CheckConstraint(
                condition=Q(code=Lower("code")),
                name="cap_code_lower",
            ),
            models.CheckConstraint(
                condition=Q(code__regex=r"^[a-z0-9]+(?:[-_][a-z0-9]+)*$"),
                name="cap_code_format",
            ),
            models.CheckConstraint(
                condition=Q(status__in=CatalogStatus.values),
                name="cap_status_valid",
            ),
            models.CheckConstraint(
                condition=Q(display_order__gte=0),
                name="cap_display_order_non_neg",
            ),
        ]
        indexes = [
            models.Index(fields=["feature", "status", "display_order", "id"], name="cap_feat_stat_order_idx"),
            models.Index(fields=["feature", "-created_at", "-id"], name="cap_feat_created_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.code})"
