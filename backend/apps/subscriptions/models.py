"""VibeConnect Phase 2C Subscriptions Domain Models.

Implements the organisation-scoped subscription lifecycle, commercial snapshot,
and entitlement snapshot tables. All models in this module are treated as
immutable historical records once created; mutability is restricted to defined
lifecycle-transition fields via explicit save(update_fields=[...]) calls from
Stage-2 domain services.

Immutability boundary:
  Application-enforced via SubscriptionQuerySet / EntitlementQuerySet delete/update
  overrides and instance delete/save overrides. Privileged PostgreSQL users, raw SQL
  queries, and database migrations are outside this boundary.
"""

import uuid
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q

# Re-export plans enums so subscription snapshot fields use identical choices.
from apps.plans.models import (
    BillingInterval,
    PlanCurrency,
    QuotaLimitType,
    QuotaResetPeriod,
    QuotaScope,
)


# ---------------------------------------------------------------------------
# Subscription status
# ---------------------------------------------------------------------------

class SubscriptionStatus(models.TextChoices):
    TRIALING = "trialing", "Trialing"
    ACTIVE = "active", "Active"
    SUSPENDED = "suspended", "Suspended"
    CANCELLED = "cancelled", "Cancelled"
    EXPIRED = "expired", "Expired"


# ---------------------------------------------------------------------------
# Queryset / Manager — application-level historical protection
# ---------------------------------------------------------------------------

class SubscriptionQuerySet(models.QuerySet):
    """QuerySet that enforces append-only immutability for OrganizationSubscription."""

    def delete(self):
        raise ValidationError(
            "Subscriptions cannot be deleted; they are immutable historical records."
        )

    def update(self, **kwargs):
        raise ValidationError(
            "Subscriptions cannot be bulk updated; use instance save(update_fields=[...]) "
            "for permitted lifecycle-field transitions."
        )

    def bulk_update(self, objs, fields, batch_size=None):
        raise ValidationError(
            "Subscriptions cannot be bulk updated; use instance save(update_fields=[...]) "
            "for permitted lifecycle-field transitions."
        )


class SubscriptionManager(models.Manager):
    """Manager that returns the immutability-enforcing SubscriptionQuerySet."""

    def get_queryset(self):
        return SubscriptionQuerySet(self.model, using=self._db)

    def bulk_update(self, objs, fields, batch_size=None):
        raise ValidationError(
            "Subscriptions cannot be bulk updated; use instance save(update_fields=[...]) "
            "for permitted lifecycle-field transitions."
        )


class EntitlementQuerySet(models.QuerySet):
    """QuerySet that enforces append-only immutability for subscription entitlement snapshots."""

    def delete(self):
        raise ValidationError(
            "Subscription entitlements cannot be deleted; they are immutable historical records."
        )

    def update(self, **kwargs):
        raise ValidationError(
            "Subscription entitlements cannot be updated; they are immutable historical records."
        )

    def bulk_update(self, objs, fields, batch_size=None):
        raise ValidationError(
            "Subscription entitlements cannot be bulk updated; they are immutable historical records."
        )


class EntitlementManager(models.Manager):
    """Manager that returns the immutability-enforcing EntitlementQuerySet."""

    def get_queryset(self):
        return EntitlementQuerySet(self.model, using=self._db)

    def bulk_update(self, objs, fields, batch_size=None):
        raise ValidationError(
            "Subscription entitlements cannot be bulk updated; they are immutable historical records."
        )


# ---------------------------------------------------------------------------
# OrganizationSubscription
# ---------------------------------------------------------------------------

# Fields whose values are fixed at creation time. Any attempt to mutate them
# on an existing record is rejected by save().
_SUB_IMMUTABLE_FIELDS = frozenset([
    "id",
    "organization_id",
    "plan_version_id",
    "plan_price_id",
    "plan_code_snapshot",
    "plan_name_snapshot",
    "version_number_snapshot",
    "previous_subscription_id",
    "currency",
    "billing_interval",
    "amount",
    "started_as_trial",
    "trial_started_at",
    "trial_ends_at",
    "change_reason",
    "created_by_id",
    "created_at",
])

# Python attribute names (no _id suffix) used to normalise update_fields checks.
_SUB_IMMUTABLE_PYTHON_NAMES = frozenset([
    "id",
    "organization",
    "plan_version",
    "plan_price",
    "plan_code_snapshot",
    "plan_name_snapshot",
    "version_number_snapshot",
    "previous_subscription",
    "currency",
    "billing_interval",
    "amount",
    "started_as_trial",
    "trial_started_at",
    "trial_ends_at",
    "change_reason",
    "created_by",
    "created_at",
])

# Fields explicitly allowed to be mutated during permitted lifecycle transitions.
_SUB_LIFECYCLE_MUTABLE_FIELDS = frozenset([
    "status",
    "current_period_start",
    "current_period_end",
    "cancelled_at",
    "ended_at",
    "cancellation_reason",
    "suspension_reason",
    "updated_at",
    "updated_by",
    "updated_by_id",
])


class OrganizationSubscription(models.Model):
    """Subscription lifecycle record for a single organisation.

    One organisation may have at most one open (trialing / active / suspended)
    subscription at any time, enforced by the ``org_single_current_sub_unq``
    partial unique index. Terminal records (cancelled / expired) accumulate as
    an immutable historical log.
    """

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    # --- Provenance FKs (all PROTECT, all immutable after creation) ---
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.PROTECT,
        related_name="subscriptions",
        null=False,
        blank=False,
    )
    plan_version = models.ForeignKey(
        "plans.PlanVersion",
        on_delete=models.PROTECT,
        related_name="subscriptions",
        null=False,
        blank=False,
    )
    plan_price = models.ForeignKey(
        "plans.PlanPrice",
        on_delete=models.PROTECT,
        related_name="subscriptions",
        null=False,
        blank=False,
    )
    previous_subscription = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        related_name="successor_subscriptions",
        null=True,
        blank=True,
        help_text="The immediately preceding subscription, if any (e.g. after plan change).",
    )

    # --- Commercial & Plan Identity Snapshots (immutable after creation) ---
    plan_code_snapshot = models.CharField(max_length=50)
    plan_name_snapshot = models.CharField(max_length=100)
    version_number_snapshot = models.PositiveIntegerField()
    billing_interval = models.CharField(
        max_length=20,
        choices=BillingInterval.choices,
    )
    currency = models.CharField(
        max_length=3,
        choices=PlanCurrency.choices,
    )
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        help_text="Snapshot of the agreed amount; 0.00 for free/trial subscriptions.",
    )

    # --- Trial origin (immutable snapshot) ---
    started_as_trial = models.BooleanField(
        default=False,
        editable=False,
        help_text="True if this subscription was originally created as a trial.",
    )
    trial_started_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Populated when started_as_trial=True.",
    )
    trial_ends_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Populated when started_as_trial=True.",
    )

    # --- Lifecycle status ---
    status = models.CharField(
        max_length=20,
        choices=SubscriptionStatus.choices,
        default=SubscriptionStatus.TRIALING,
    )

    # --- Active billing period (lifecycle-mutable) ---
    current_period_start = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Null while status=trialing; set on activation.",
    )
    current_period_end = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Null while status=trialing; set on activation.",
    )

    # --- Terminal timestamps (lifecycle-mutable, set once) ---
    cancelled_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)

    # --- Reason fields (lifecycle-mutable) ---
    change_reason = models.CharField(max_length=255, blank=True, default="")
    cancellation_reason = models.CharField(max_length=255, blank=True, default="")
    suspension_reason = models.CharField(max_length=255, blank=True, default="")

    # --- Provenance actors ---
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_subscriptions",
        null=False,
        blank=False,
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="updated_subscriptions",
        null=False,
        blank=False,
    )

    # --- Timestamps ---
    created_at = models.DateTimeField(auto_now_add=True, editable=False)
    updated_at = models.DateTimeField(auto_now=True, editable=False)

    objects = SubscriptionManager()

    class Meta:
        db_table = "organization_subscriptions"
        verbose_name = "Organization Subscription"
        verbose_name_plural = "Organization Subscriptions"
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(
                fields=["organization", "status"],
                name="sub_org_status_idx",
            ),
            models.Index(
                fields=["status", "trial_ends_at"],
                name="sub_trial_exp_idx",
            ),
            models.Index(
                fields=["-created_at", "-id"],
                name="sub_created_idx",
            ),
        ]
        constraints = [
            # 1. At most one open subscription per organisation.
            models.UniqueConstraint(
                fields=["organization"],
                condition=Q(status__in=["trialing", "active", "suspended"]),
                name="org_single_current_sub_unq",
            ),
            # 2. A subscription cannot be its own predecessor.
            models.CheckConstraint(
                condition=Q(previous_subscription__isnull=True) | ~Q(previous_subscription=F("id")),
                name="sub_no_self_predecessor",
            ),
            # 3. Amount must be non-negative.
            models.CheckConstraint(
                condition=Q(amount__gte=Decimal("0.00")),
                name="sub_amount_gte_zero",
            ),
            # 4. Trial origin timestamps co-exist with started_as_trial flag.
            models.CheckConstraint(
                condition=(
                    (
                        Q(started_as_trial=True)
                        & Q(trial_started_at__isnull=False)
                        & Q(trial_ends_at__isnull=False)
                    )
                    | (
                        Q(started_as_trial=False)
                        & Q(trial_started_at__isnull=True)
                        & Q(trial_ends_at__isnull=True)
                    )
                ),
                name="sub_trial_origin_fields_valid",
            ),
            # 5. Trialing subscriptions must not have active billing periods.
            models.CheckConstraint(
                condition=(
                    (
                        Q(status="trialing")
                        & Q(started_as_trial=True)
                        & Q(current_period_start__isnull=True)
                        & Q(current_period_end__isnull=True)
                    )
                    | ~Q(status="trialing")
                ),
                name="sub_trial_dates_valid",
            ),
            # 6. trial_ends_at must be strictly after trial_started_at.
            models.CheckConstraint(
                condition=(
                    Q(trial_ends_at__gt=F("trial_started_at"))
                    | Q(trial_started_at__isnull=True)
                ),
                name="sub_trial_ends_gt_started",
            ),
            # 7. Active and suspended subscriptions must have billing periods.
            models.CheckConstraint(
                condition=(
                    (
                        Q(status__in=["active", "suspended"])
                        & Q(current_period_start__isnull=False)
                        & Q(current_period_end__isnull=False)
                    )
                    | ~Q(status__in=["active", "suspended"])
                ),
                name="sub_active_dates_valid",
            ),
            # 8. current_period_end must be strictly after current_period_start.
            models.CheckConstraint(
                condition=(
                    Q(current_period_end__gt=F("current_period_start"))
                    | Q(current_period_start__isnull=True)
                ),
                name="sub_period_end_gt_start",
            ),
            # 9. cancelled_at is set iff status=cancelled.
            models.CheckConstraint(
                condition=(
                    (Q(status="cancelled") & Q(cancelled_at__isnull=False))
                    | (~Q(status="cancelled") & Q(cancelled_at__isnull=True))
                ),
                name="sub_cancelled_at_valid",
            ),
            # 10. ended_at is set iff status in {cancelled, expired}.
            models.CheckConstraint(
                condition=(
                    (Q(status__in=["cancelled", "expired"]) & Q(ended_at__isnull=False))
                    | (~Q(status__in=["cancelled", "expired"]) & Q(ended_at__isnull=True))
                ),
                name="sub_closed_ended_at_valid",
            ),
            # 11. Only trial-origin subscriptions can expire.
            models.CheckConstraint(
                condition=(
                    (Q(status="expired") & Q(started_as_trial=True))
                    | ~Q(status="expired")
                ),
                name="sub_expired_trial_origin",
            ),
        ]

    # -----------------------------------------------------------------------
    # Application-level immutability enforcement
    # -----------------------------------------------------------------------

    def delete(self, *args, **kwargs):
        raise ValidationError(
            "Subscriptions cannot be deleted; they are immutable historical records."
        )

    def save(self, *args, **kwargs):
        """Enforce immutable-field contract before delegating to Django ORM.

        - New records (self._state.adding=True): all fields allowed.
        - Existing records with update_fields: reject if any immutable field
          is included in the update set.
        - Existing records without update_fields (full save): compare every
          immutable field against the persisted value; reject on any change.
        """
        update_fields = kwargs.get("update_fields")

        if not self._state.adding:
            if update_fields is not None:
                normalized = set()
                for f in update_fields:
                    normalized.add(f)
                    if f.endswith("_id"):
                        normalized.add(f[:-3])
                    else:
                        normalized.add(f + "_id")

                blocked = normalized & (_SUB_IMMUTABLE_FIELDS | _SUB_IMMUTABLE_PYTHON_NAMES)
                if blocked:
                    raise ValidationError(
                        f"Immutable subscription field(s) cannot be updated: "
                        f"{', '.join(sorted(blocked - {'id', 'id_id'}))}."
                    )
            else:
                persisted = (
                    OrganizationSubscription.objects
                    .filter(pk=self.pk)
                    .values(*_SUB_IMMUTABLE_FIELDS)
                    .first()
                )
                if persisted is not None:
                    for field in _SUB_IMMUTABLE_FIELDS:
                        current_val = getattr(self, field)
                        persisted_val = persisted[field]
                        if current_val != persisted_val:
                            raise ValidationError(
                                {field: (
                                    f"Field '{field}' is immutable and cannot be changed "
                                    "after the subscription has been created."
                                )}
                            )

        super().save(*args, **kwargs)

    def __str__(self):
        return (
            f"Subscription {self.id} | org={self.organization_id} "
            f"| {self.status} | plan_version={self.plan_version_id}"
        )


# ---------------------------------------------------------------------------
# SubscriptionProductEntitlement
# ---------------------------------------------------------------------------

class SubscriptionProductEntitlement(models.Model):
    """Snapshot of a product entitlement captured at subscription creation.

    One row per (subscription, product) pair. Provenance back to the exact
    PlanProduct slot that was active when the subscription was created.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    subscription = models.ForeignKey(
        "subscriptions.OrganizationSubscription",
        on_delete=models.PROTECT,
        related_name="product_entitlements",
        null=False,
        blank=False,
    )
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.PROTECT,
        related_name="sub_product_entitlements",
        null=False,
        blank=False,
        help_text="Denormalised from subscription for efficient per-org queries.",
    )
    product = models.ForeignKey(
        "product_registry.Product",
        on_delete=models.PROTECT,
        related_name="sub_product_entitlements",
        null=False,
        blank=False,
    )
    # Provenance — non-null link to the exact plan slot.
    plan_product = models.ForeignKey(
        "plans.PlanProduct",
        on_delete=models.PROTECT,
        related_name="+",
        null=False,
        blank=False,
    )
    # Snapshots
    product_code_snapshot = models.CharField(max_length=50)
    product_name_snapshot = models.CharField(max_length=100)

    created_at = models.DateTimeField(auto_now_add=True, editable=False)

    objects = EntitlementManager()

    class Meta:
        db_table = "subscription_product_entitlements"
        verbose_name = "Subscription Product Entitlement"
        verbose_name_plural = "Subscription Product Entitlements"
        constraints = [
            models.UniqueConstraint(
                fields=["subscription", "product"],
                name="sub_prod_entitlement_unq",
            ),
        ]
        indexes = [
            models.Index(
                fields=["organization", "product"],
                name="sub_prod_org_prod_idx",
            ),
        ]

    def delete(self, *args, **kwargs):
        raise ValidationError(
            "Subscription entitlements cannot be deleted; they are immutable historical records."
        )

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError(
                "Subscription product entitlements are immutable and cannot be modified after creation."
            )
        super().save(*args, **kwargs)

    def __str__(self):
        return f"SubProdEntitlement sub={self.subscription_id} product={self.product_code_snapshot}"


# ---------------------------------------------------------------------------
# SubscriptionModuleEntitlement
# ---------------------------------------------------------------------------

class SubscriptionModuleEntitlement(models.Model):
    """Snapshot of a module entitlement captured at subscription creation."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    subscription = models.ForeignKey(
        "subscriptions.OrganizationSubscription",
        on_delete=models.PROTECT,
        related_name="module_entitlements",
        null=False,
        blank=False,
    )
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.PROTECT,
        related_name="sub_module_entitlements",
        null=False,
        blank=False,
    )
    module = models.ForeignKey(
        "product_registry.ProductModule",
        on_delete=models.PROTECT,
        related_name="sub_module_entitlements",
        null=False,
        blank=False,
    )
    # Provenance
    plan_module = models.ForeignKey(
        "plans.PlanModule",
        on_delete=models.PROTECT,
        related_name="+",
        null=False,
        blank=False,
    )
    # Snapshots
    module_code_snapshot = models.CharField(max_length=50)
    module_name_snapshot = models.CharField(max_length=100)

    created_at = models.DateTimeField(auto_now_add=True, editable=False)

    objects = EntitlementManager()

    class Meta:
        db_table = "subscription_module_entitlements"
        verbose_name = "Subscription Module Entitlement"
        verbose_name_plural = "Subscription Module Entitlements"
        constraints = [
            models.UniqueConstraint(
                fields=["subscription", "module"],
                name="sub_mod_entitlement_unq",
            ),
        ]
        indexes = [
            models.Index(
                fields=["organization", "module"],
                name="sub_mod_org_mod_idx",
            ),
        ]

    def delete(self, *args, **kwargs):
        raise ValidationError(
            "Subscription entitlements cannot be deleted; they are immutable historical records."
        )

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError(
                "Subscription module entitlements are immutable and cannot be modified after creation."
            )
        super().save(*args, **kwargs)

    def __str__(self):
        return f"SubModEntitlement sub={self.subscription_id} module={self.module_code_snapshot}"


# ---------------------------------------------------------------------------
# SubscriptionCapabilityEntitlement
# ---------------------------------------------------------------------------

class SubscriptionCapabilityEntitlement(models.Model):
    """Snapshot of a capability entitlement captured at subscription creation."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    subscription = models.ForeignKey(
        "subscriptions.OrganizationSubscription",
        on_delete=models.PROTECT,
        related_name="capability_entitlements",
        null=False,
        blank=False,
    )
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.PROTECT,
        related_name="sub_capability_entitlements",
        null=False,
        blank=False,
    )
    capability = models.ForeignKey(
        "product_registry.ProductCapability",
        on_delete=models.PROTECT,
        related_name="sub_capability_entitlements",
        null=False,
        blank=False,
    )
    # Provenance
    plan_capability = models.ForeignKey(
        "plans.PlanCapability",
        on_delete=models.PROTECT,
        related_name="+",
        null=False,
        blank=False,
    )
    # Snapshots
    capability_code_snapshot = models.CharField(max_length=50)
    capability_name_snapshot = models.CharField(max_length=100)

    created_at = models.DateTimeField(auto_now_add=True, editable=False)

    objects = EntitlementManager()

    class Meta:
        db_table = "subscription_capability_entitlements"
        verbose_name = "Subscription Capability Entitlement"
        verbose_name_plural = "Subscription Capability Entitlements"
        constraints = [
            models.UniqueConstraint(
                fields=["subscription", "capability"],
                name="sub_cap_entitlement_unq",
            ),
        ]
        indexes = [
            models.Index(
                fields=["organization", "capability"],
                name="sub_cap_org_cap_idx",
            ),
        ]

    def delete(self, *args, **kwargs):
        raise ValidationError(
            "Subscription entitlements cannot be deleted; they are immutable historical records."
        )

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError(
                "Subscription capability entitlements are immutable and cannot be modified after creation."
            )
        super().save(*args, **kwargs)

    def __str__(self):
        return f"SubCapEntitlement sub={self.subscription_id} capability={self.capability_code_snapshot}"


# ---------------------------------------------------------------------------
# SubscriptionQuotaEntitlement
# ---------------------------------------------------------------------------

class SubscriptionQuotaEntitlement(models.Model):
    """Snapshot of a quota entitlement captured at subscription creation.

    Typed nullable FKs (product / module / capability) mirror the scope model
    from PlanQuota. No generic target_id / GenericForeignKey is used.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    subscription = models.ForeignKey(
        "subscriptions.OrganizationSubscription",
        on_delete=models.PROTECT,
        related_name="quota_entitlements",
        null=False,
        blank=False,
    )
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.PROTECT,
        related_name="sub_quota_entitlements",
        null=False,
        blank=False,
    )
    # Provenance
    plan_quota = models.ForeignKey(
        "plans.PlanQuota",
        on_delete=models.PROTECT,
        related_name="+",
        null=False,
        blank=False,
    )

    # --- Quota snapshot ---
    quota_key = models.CharField(max_length=64)
    name = models.CharField(max_length=100)
    scope = models.CharField(max_length=20, choices=QuotaScope.choices)

    # --- Typed scope target FKs (exactly one is non-null for non-plan scopes) ---
    product = models.ForeignKey(
        "product_registry.Product",
        on_delete=models.PROTECT,
        related_name="+",
        null=True,
        blank=True,
    )
    module = models.ForeignKey(
        "product_registry.ProductModule",
        on_delete=models.PROTECT,
        related_name="+",
        null=True,
        blank=True,
    )
    capability = models.ForeignKey(
        "product_registry.ProductCapability",
        on_delete=models.PROTECT,
        related_name="+",
        null=True,
        blank=True,
    )

    # Target snapshots
    target_code_snapshot = models.CharField(max_length=50, blank=True, default="")
    target_name_snapshot = models.CharField(max_length=100, blank=True, default="")

    limit_type = models.CharField(max_length=20, choices=QuotaLimitType.choices)
    limit_value = models.BigIntegerField(
        null=True,
        blank=True,
        help_text="Null when limit_type=unlimited.",
    )
    unit = models.CharField(max_length=32)
    is_hard_limit = models.BooleanField(default=True)
    reset_period = models.CharField(max_length=20, choices=QuotaResetPeriod.choices)

    created_at = models.DateTimeField(auto_now_add=True, editable=False)

    objects = EntitlementManager()

    class Meta:
        db_table = "subscription_quota_entitlements"
        verbose_name = "Subscription Quota Entitlement"
        verbose_name_plural = "Subscription Quota Entitlements"
        indexes = [
            models.Index(
                fields=["organization", "quota_key", "scope"],
                name="sub_q_org_key_idx",
            ),
        ]
        constraints = [
            # Scope-target integrity mirrors PlanQuota.quota_scope_target_valid.
            models.CheckConstraint(
                condition=(
                    (
                        Q(scope="plan")
                        & Q(product__isnull=True)
                        & Q(module__isnull=True)
                        & Q(capability__isnull=True)
                    )
                    | (
                        Q(scope="product")
                        & Q(product__isnull=False)
                        & Q(module__isnull=True)
                        & Q(capability__isnull=True)
                    )
                    | (
                        Q(scope="module")
                        & Q(product__isnull=True)
                        & Q(module__isnull=False)
                        & Q(capability__isnull=True)
                    )
                    | (
                        Q(scope="capability")
                        & Q(product__isnull=True)
                        & Q(module__isnull=True)
                        & Q(capability__isnull=False)
                    )
                ),
                name="sub_quota_scope_target_valid",
            ),
            # Unique quota key per scope per subscription.
            models.UniqueConstraint(
                fields=["subscription", "quota_key"],
                condition=Q(scope="plan"),
                name="sub_q_plan_unq",
            ),
            models.UniqueConstraint(
                fields=["subscription", "product", "quota_key"],
                condition=Q(scope="product"),
                name="sub_q_prod_unq",
            ),
            models.UniqueConstraint(
                fields=["subscription", "module", "quota_key"],
                condition=Q(scope="module"),
                name="sub_q_mod_unq",
            ),
            models.UniqueConstraint(
                fields=["subscription", "capability", "quota_key"],
                condition=Q(scope="capability"),
                name="sub_q_cap_unq",
            ),
        ]

    def delete(self, *args, **kwargs):
        raise ValidationError(
            "Subscription entitlements cannot be deleted; they are immutable historical records."
        )

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError(
                "Subscription quota entitlements are immutable and cannot be modified after creation."
            )
        super().save(*args, **kwargs)

    def __str__(self):
        return (
            f"SubQuotaEntitlement sub={self.subscription_id} "
            f"key={self.quota_key} scope={self.scope}"
        )
