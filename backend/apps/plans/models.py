"""VibeConnect Phase 2B Plans & Pricing Domain Models.

Multi-tenant SaaS plan packaging and pricing domain schema.
"""

import re
import uuid
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator
from django.db import models
from django.db.models import F, Q
from django.db.models.functions import Lower

CODE_REGEX = r"^[a-z0-9]+(?:[-_][a-z0-9]+)*$"
code_validator = RegexValidator(
    regex=CODE_REGEX,
    message="Code must be lowercase alphanumeric and may contain single hyphens or underscores as internal separators.",
)

UNIT_REGEX = r"^[a-z0-9_]+$"
unit_validator = RegexValidator(
    regex=UNIT_REGEX,
    message="Unit must be lowercase alphanumeric with underscores.",
)


class Plan(models.Model):
    """Platform plan packaging entity.

    Immutable code contract, no status, active, or archive flags.
    """

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    code = models.CharField(
        max_length=50,
        validators=[code_validator],
    )
    name = models.CharField(
        max_length=100,
    )
    description = models.CharField(
        max_length=1000,
        blank=True,
        default="",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        editable=False,
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        editable=False,
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_plans",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="updated_plans",
    )
    is_public = models.BooleanField(
        default=False,
        db_index=True,
        help_text="Whether this plan appears in the unauthenticated public catalog.",
    )

    class Meta:
        db_table = "plans"
        verbose_name = "Plan"
        verbose_name_plural = "Plans"
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["-created_at", "-id"], name="plan_created_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(code__regex=CODE_REGEX),
                name="plan_code_format",
            ),
            models.UniqueConstraint(
                Lower("code"),
                name="plan_code_ci_unq",
            ),
        ]

    def clean(self):
        super().clean()
        if self.code:
            if self.code != self.code.lower():
                raise ValidationError({"code": "Plan code must be strictly lowercase."})
            if not re.match(CODE_REGEX, self.code):
                raise ValidationError({"code": "Plan code format is invalid."})

    def save(self, *args, **kwargs):
        if self.code:
            self.code = self.code.lower()
        if not self._state.adding and self.pk:
            orig = Plan.objects.filter(pk=self.pk).values_list("code", flat=True).first()
            if orig is not None and orig != self.code:
                raise ValidationError("Plan code is immutable.")
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} ({self.code})"


class PlanVersionStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    ACTIVE = "active", "Active"
    RETIRED = "retired", "Retired"


class PlanVersion(models.Model):
    """Versioned lifecycle state of a Plan."""

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    plan = models.ForeignKey(
        "plans.Plan",
        on_delete=models.PROTECT,
        related_name="versions",
    )
    version = models.PositiveIntegerField()
    status = models.CharField(
        max_length=20,
        choices=PlanVersionStatus.choices,
        default=PlanVersionStatus.DRAFT,
    )
    change_summary = models.CharField(
        max_length=500,
        blank=True,
        default="",
    )
    activated_at = models.DateTimeField(
        null=True,
        blank=True,
    )
    retired_at = models.DateTimeField(
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        editable=False,
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        editable=False,
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_plan_versions",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="updated_plan_versions",
    )

    class Meta:
        db_table = "plan_versions"
        verbose_name = "Plan Version"
        verbose_name_plural = "Plan Versions"
        ordering = ["plan", "-version"]
        indexes = [
            models.Index(fields=["plan", "status", "-version"], name="plan_ver_plan_stat_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["plan", "version"],
                name="plan_version_unq",
            ),
            models.UniqueConstraint(
                fields=["plan"],
                condition=Q(status=PlanVersionStatus.ACTIVE),
                name="plan_version_one_active_unq",
            ),
            models.CheckConstraint(
                condition=Q(version__gt=0),
                name="plan_version_gt_zero",
            ),
            models.CheckConstraint(
                condition=Q(status__in=PlanVersionStatus.values),
                name="plan_version_status_valid",
            ),
            models.CheckConstraint(
                condition=(
                    (Q(status=PlanVersionStatus.DRAFT) & Q(activated_at__isnull=True) & Q(retired_at__isnull=True))
                    | (Q(status=PlanVersionStatus.ACTIVE) & Q(activated_at__isnull=False) & Q(retired_at__isnull=True))
                    | (
                        Q(status=PlanVersionStatus.RETIRED)
                        & Q(retired_at__isnull=False)
                        & (
                            Q(activated_at__isnull=True)
                            | Q(retired_at__gte=F("activated_at"))
                        )
                    )
                ),
                name="plan_version_lifecycle_timestamps",
            ),
        ]

    def clean(self):
        super().clean()
        if self.version is not None and self.version <= 0:
            raise ValidationError({"version": "Version must be greater than 0."})
        if self.status == PlanVersionStatus.DRAFT:
            if self.activated_at is not None or self.retired_at is not None:
                raise ValidationError("Draft version cannot have activated_at or retired_at set.")
        elif self.status == PlanVersionStatus.ACTIVE:
            if self.activated_at is None:
                raise ValidationError("Active version must have activated_at set.")
            if self.retired_at is not None:
                raise ValidationError("Active version cannot have retired_at set.")
        elif self.status == PlanVersionStatus.RETIRED:
            if self.retired_at is None:
                raise ValidationError("Retired version must have retired_at set.")
            if (
                self.activated_at is not None
                and self.retired_at < self.activated_at
            ):
                raise ValidationError("retired_at cannot precede activated_at.")

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.plan.code} v{self.version} ({self.status})"


class PlanCurrency(models.TextChoices):
    INR = "INR", "INR"
    USD = "USD", "USD"
    EUR = "EUR", "EUR"
    GBP = "GBP", "GBP"


class BillingInterval(models.TextChoices):
    MONTHLY = "monthly", "Monthly"
    QUARTERLY = "quarterly", "Quarterly"
    ANNUAL = "annual", "Annual"


class PlanPrice(models.Model):
    """Pricing configuration for a PlanVersion."""

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    plan_version = models.ForeignKey(
        "plans.PlanVersion",
        on_delete=models.CASCADE,
        related_name="prices",
    )
    currency = models.CharField(
        max_length=3,
        choices=PlanCurrency.choices,
    )
    billing_interval = models.CharField(
        max_length=20,
        choices=BillingInterval.choices,
    )
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[
            MinValueValidator(Decimal("0.00")),
            MaxValueValidator(Decimal("9999999999.99")),
        ],
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        editable=False,
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        editable=False,
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="+",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="+",
    )

    class Meta:
        db_table = "plan_prices"
        verbose_name = "Plan Price"
        verbose_name_plural = "Plan Prices"
        constraints = [
            models.UniqueConstraint(
                fields=["plan_version", "currency", "billing_interval"],
                name="plan_price_ver_curr_int_unq",
            ),
            models.CheckConstraint(
                condition=Q(amount__gte=0),
                name="plan_price_amount_gte_zero",
            ),
            models.CheckConstraint(
                condition=Q(currency__in=PlanCurrency.values),
                name="plan_price_currency_allowed",
            ),
            models.CheckConstraint(
                condition=Q(billing_interval__in=BillingInterval.values),
                name="plan_price_interval_valid",
            ),
        ]

    def clean(self):
        super().clean()
        if self.amount is not None and self.amount < Decimal("0.00"):
            raise ValidationError({"amount": "Amount must be greater than or equal to 0.00."})

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.plan_version} - {self.currency} {self.amount} / {self.billing_interval}"


class PlanProduct(models.Model):
    """Product packaging mapping for a PlanVersion."""

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    plan_version = models.ForeignKey(
        "plans.PlanVersion",
        on_delete=models.CASCADE,
        related_name="packaged_products",
    )
    product = models.ForeignKey(
        "product_registry.Product",
        on_delete=models.PROTECT,
        related_name="+",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        editable=False,
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="+",
    )

    class Meta:
        db_table = "plan_products"
        verbose_name = "Plan Product"
        verbose_name_plural = "Plan Products"
        constraints = [
            models.UniqueConstraint(
                fields=["plan_version", "product"],
                name="plan_product_ver_prod_unq",
            ),
        ]

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.plan_version} -> Product {self.product_id}"


class PlanModule(models.Model):
    """Module packaging mapping within a packaged product."""

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    plan_version = models.ForeignKey(
        "plans.PlanVersion",
        on_delete=models.CASCADE,
        related_name="packaged_modules",
    )
    plan_product = models.ForeignKey(
        "plans.PlanProduct",
        on_delete=models.CASCADE,
        related_name="packaged_modules",
    )
    module = models.ForeignKey(
        "product_registry.ProductModule",
        on_delete=models.PROTECT,
        related_name="+",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        editable=False,
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="+",
    )

    class Meta:
        db_table = "plan_modules"
        verbose_name = "Plan Module"
        verbose_name_plural = "Plan Modules"
        constraints = [
            models.UniqueConstraint(
                fields=["plan_version", "module"],
                name="plan_module_ver_mod_unq",
            ),
        ]

    def clean(self):
        super().clean()
        if self.plan_product_id and self.plan_version_id:
            if self.plan_product.plan_version_id != self.plan_version_id:
                raise ValidationError("plan_product must belong to the same plan_version.")

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.plan_version} -> Module {self.module_id}"


class PlanCapability(models.Model):
    """Capability packaging mapping within a packaged module."""

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    plan_version = models.ForeignKey(
        "plans.PlanVersion",
        on_delete=models.CASCADE,
        related_name="packaged_capabilities",
    )
    plan_module = models.ForeignKey(
        "plans.PlanModule",
        on_delete=models.CASCADE,
        related_name="packaged_capabilities",
    )
    capability = models.ForeignKey(
        "product_registry.ProductCapability",
        on_delete=models.PROTECT,
        related_name="+",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        editable=False,
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="+",
    )

    class Meta:
        db_table = "plan_capabilities"
        verbose_name = "Plan Capability"
        verbose_name_plural = "Plan Capabilities"
        constraints = [
            models.UniqueConstraint(
                fields=["plan_version", "capability"],
                name="plan_capability_ver_cap_unq",
            ),
        ]

    def clean(self):
        super().clean()
        if self.plan_module_id and self.plan_version_id:
            if self.plan_module.plan_version_id != self.plan_version_id:
                raise ValidationError("plan_module must belong to the same plan_version.")

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.plan_version} -> Capability {self.capability_id}"


class QuotaScope(models.TextChoices):
    PLAN = "plan", "Plan"
    PRODUCT = "product", "Product"
    MODULE = "module", "Module"
    CAPABILITY = "capability", "Capability"



class QuotaLimitType(models.TextChoices):
    NUMERIC = "numeric", "Numeric"
    UNLIMITED = "unlimited", "Unlimited"


class QuotaResetPeriod(models.TextChoices):
    NEVER = "never", "Never"
    MONTHLY = "monthly", "Monthly"
    ANNUAL = "annual", "Annual"


class PlanQuota(models.Model):
    """Scoped usage limit definition for a PlanVersion."""

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    plan_version = models.ForeignKey(
        "plans.PlanVersion",
        on_delete=models.CASCADE,
        related_name="quotas",
    )
    scope = models.CharField(
        max_length=20,
        choices=QuotaScope.choices,
    )
    plan_product = models.ForeignKey(
        "plans.PlanProduct",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="quotas",
    )
    plan_module = models.ForeignKey(
        "plans.PlanModule",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="quotas",
    )
    plan_capability = models.ForeignKey(
        "plans.PlanCapability",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="quotas",
    )
    quota_key = models.CharField(
        max_length=64,
        validators=[code_validator],
    )
    name = models.CharField(
        max_length=100,
    )
    unit = models.CharField(
        max_length=32,
        validators=[unit_validator],
    )
    limit_type = models.CharField(
        max_length=20,
        choices=QuotaLimitType.choices,
    )
    limit_value = models.BigIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(9223372036854775807)],
    )
    is_hard_limit = models.BooleanField(
        default=True,
    )
    reset_period = models.CharField(
        max_length=20,
        choices=QuotaResetPeriod.choices,
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        editable=False,
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        editable=False,
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="+",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="+",
    )

    class Meta:
        db_table = "plan_quotas"
        verbose_name = "Plan Quota"
        verbose_name_plural = "Plan Quotas"
        indexes = [
            models.Index(fields=["plan_version", "scope"], name="quota_ver_scope_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(scope__in=QuotaScope.values),
                name="quota_scope_valid",
            ),
            models.CheckConstraint(
                condition=Q(unit__regex=UNIT_REGEX),
                name="quota_unit_format",
            ),
            models.CheckConstraint(
                condition=Q(limit_type__in=QuotaLimitType.values),
                name="quota_limit_type_valid",
            ),
            models.CheckConstraint(
                condition=Q(reset_period__in=QuotaResetPeriod.values),
                name="quota_reset_period_valid",
            ),
            models.CheckConstraint(
                condition=Q(quota_key__regex=CODE_REGEX),
                name="quota_key_format",
            ),
            models.CheckConstraint(
                condition=(
                    (
                        Q(limit_type=QuotaLimitType.NUMERIC)
                        & Q(limit_value__isnull=False)
                        & Q(limit_value__gte=0)
                        & Q(limit_value__lte=9223372036854775807)
                    )
                    | (Q(limit_type=QuotaLimitType.UNLIMITED) & Q(limit_value__isnull=True))
                ),
                name="quota_limit_type_value_valid",
            ),
            models.CheckConstraint(
                condition=(
                    (
                        Q(scope=QuotaScope.PLAN)
                        & Q(plan_product__isnull=True)
                        & Q(plan_module__isnull=True)
                        & Q(plan_capability__isnull=True)
                    )
                    | (
                        Q(scope=QuotaScope.PRODUCT)
                        & Q(plan_product__isnull=False)
                        & Q(plan_module__isnull=True)
                        & Q(plan_capability__isnull=True)
                    )
                    | (
                        Q(scope=QuotaScope.MODULE)
                        & Q(plan_product__isnull=True)
                        & Q(plan_module__isnull=False)
                        & Q(plan_capability__isnull=True)
                    )
                    | (
                        Q(scope=QuotaScope.CAPABILITY)
                        & Q(plan_product__isnull=True)
                        & Q(plan_module__isnull=True)
                        & Q(plan_capability__isnull=False)
                    )
                ),
                name="quota_scope_target_valid",
            ),
            models.UniqueConstraint(
                fields=["plan_version", "quota_key"],
                condition=Q(scope=QuotaScope.PLAN),
                name="quota_plan_scope_key_unq",
            ),
            models.UniqueConstraint(
                fields=["plan_version", "plan_product", "quota_key"],
                condition=Q(scope=QuotaScope.PRODUCT),
                name="quota_product_scope_key_unq",
            ),
            models.UniqueConstraint(
                fields=["plan_version", "plan_module", "quota_key"],
                condition=Q(scope=QuotaScope.MODULE),
                name="quota_module_scope_key_unq",
            ),
            models.UniqueConstraint(
                fields=["plan_version", "plan_capability", "quota_key"],
                condition=Q(scope=QuotaScope.CAPABILITY),
                name="quota_capability_scope_key_unq",
            ),
        ]

    def clean(self):
        super().clean()
        if self.quota_key:
            if self.quota_key != self.quota_key.lower():
                raise ValidationError({"quota_key": "Quota key must be strictly lowercase."})
            if not re.match(CODE_REGEX, self.quota_key):
                raise ValidationError({"quota_key": "Quota key format is invalid."})

        if self.unit:
            if not isinstance(self.unit, str) or self.unit != self.unit.strip() or any(c.isspace() for c in self.unit):
                raise ValidationError({"unit": "Unit cannot contain whitespace."})
            if self.unit != self.unit.lower():
                raise ValidationError({"unit": "Unit must be lowercase."})
            if not re.match(UNIT_REGEX, self.unit):
                raise ValidationError({"unit": "Unit format is invalid."})

        # Validate limit_type vs limit_value
        if self.limit_type == QuotaLimitType.NUMERIC:
            if self.limit_value is None:
                raise ValidationError({"limit_value": "Numeric limit requires limit_value."})
            if self.limit_value < 0 or self.limit_value > 9223372036854775807:
                raise ValidationError({"limit_value": "Limit value must be between 0 and 9223372036854775807."})
        elif self.limit_type == QuotaLimitType.UNLIMITED:
            if self.limit_value is not None:
                raise ValidationError({"limit_value": "Unlimited quota must not specify limit_value."})

        # Validate scope target
        if self.scope == QuotaScope.PLAN:
            if self.plan_product_id or self.plan_module_id or self.plan_capability_id:
                raise ValidationError("Plan-scoped quota must not target product, module, or capability.")
        elif self.scope == QuotaScope.PRODUCT:
            if not self.plan_product_id or self.plan_module_id or self.plan_capability_id:
                raise ValidationError("Product-scoped quota must specify plan_product only.")
            if self.plan_product.plan_version_id != self.plan_version_id:
                raise ValidationError("plan_product must belong to the same plan_version.")
        elif self.scope == QuotaScope.MODULE:
            if self.plan_product_id or not self.plan_module_id or self.plan_capability_id:
                raise ValidationError("Module-scoped quota must specify plan_module only.")
            if self.plan_module.plan_version_id != self.plan_version_id:
                raise ValidationError("plan_module must belong to the same plan_version.")
        elif self.scope == QuotaScope.CAPABILITY:
            if self.plan_product_id or self.plan_module_id or not self.plan_capability_id:
                raise ValidationError("Capability-scoped quota must specify plan_capability only.")
            if self.plan_capability.plan_version_id != self.plan_version_id:
                raise ValidationError("plan_capability must belong to the same plan_version.")

    def save(self, *args, **kwargs):
        if self.quota_key:
            self.quota_key = self.quota_key.lower()
        self.full_clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.plan_version} - {self.name} ({self.quota_key}): {self.limit_type}"
