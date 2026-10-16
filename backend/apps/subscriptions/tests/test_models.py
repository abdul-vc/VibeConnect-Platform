"""Model and schema test suite for Phase 2C Subscriptions domain.

Validates:
1. Plan.is_public field and index.
2. Subscription AuditAction choices and AuditTargetType choices.
3. Subscription domain model definitions, table names, and reverse accessors.
4. Application-level immutability and deletion guards (instances and querysets).
5. Database constraints (single open subscription, trial origin, date validity,
   status transitions, non-negative amount, typed quota scope targets, and uniqueness).
6. Protected foreign keys preventing deletion of referenced entities.
"""

from decimal import Decimal
import uuid

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, models, transaction
from django.db.models.deletion import ProtectedError
from django.test import TestCase
from django.utils import timezone

from apps.auditlog.models import AuditAction, AuditLog, AuditTargetType
from apps.organizations.models import Organization, OrganizationStatus
from apps.plans.models import (
    BillingInterval,
    Plan,
    PlanCurrency,
    PlanPrice,
    PlanProduct,
    PlanModule,
    PlanCapability,
    PlanQuota,
    PlanVersion,
    PlanVersionStatus,
    QuotaLimitType,
    QuotaResetPeriod,
    QuotaScope,
)
from apps.product_registry.models import (
    CatalogStatus,
    Product,
    ProductCapability,
    ProductFeature,
    ProductModule,
    ProductStatus,
)
from apps.subscriptions.models import (
    OrganizationSubscription,
    SubscriptionCapabilityEntitlement,
    SubscriptionModuleEntitlement,
    SubscriptionProductEntitlement,
    SubscriptionQuotaEntitlement,
    SubscriptionStatus,
)

User = get_user_model()


class SubscriptionsSchemaModelTests(TestCase):
    """Schema, immutability, and constraint tests for apps.subscriptions."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="platform_owner@vibeconnect.test",
            password="SecurePassword123!",
            full_name="Platform Owner",
            is_platform_owner=True,
        )
        self.org = Organization.objects.create(
            name="Acme Corp",
            code="acme",
            status=OrganizationStatus.ACTIVE,
            created_by=self.user,
            updated_by=self.user,
        )
        self.product = Product.objects.create(
            name="LMS Core",
            code="lms_core",
            status=ProductStatus.ACTIVE,
            created_by=self.user,
            updated_by=self.user,
        )
        self.module = ProductModule.objects.create(
            product=self.product,
            name="Assessments",
            code="assessments",
            status=CatalogStatus.ACTIVE,
            created_by=self.user,
            updated_by=self.user,
        )
        self.feature = ProductFeature.objects.create(
            module=self.module,
            name="Grading Feature",
            code="grading_feat",
            status=CatalogStatus.ACTIVE,
            created_by=self.user,
            updated_by=self.user,
        )
        self.capability = ProductCapability.objects.create(
            feature=self.feature,
            name="Auto Grading",
            code="auto_grading",
            status=CatalogStatus.ACTIVE,
            created_by=self.user,
            updated_by=self.user,
        )
        self.plan = Plan.objects.create(
            code="enterprise",
            name="Enterprise Plan",
            is_public=False,
            created_by=self.user,
            updated_by=self.user,
        )
        self.plan_version = PlanVersion.objects.create(
            plan=self.plan,
            version=1,
            status=PlanVersionStatus.ACTIVE,
            activated_at=timezone.now(),
            created_by=self.user,
            updated_by=self.user,
        )
        self.plan_price = PlanPrice.objects.create(
            plan_version=self.plan_version,
            currency=PlanCurrency.USD,
            billing_interval=BillingInterval.MONTHLY,
            amount=Decimal("199.00"),
            created_by=self.user,
            updated_by=self.user,
        )
        self.plan_product = PlanProduct.objects.create(
            plan_version=self.plan_version,
            product=self.product,
            created_by=self.user,
        )
        self.plan_module = PlanModule.objects.create(
            plan_version=self.plan_version,
            plan_product=self.plan_product,
            module=self.module,
            created_by=self.user,
        )
        self.plan_capability = PlanCapability.objects.create(
            plan_version=self.plan_version,
            plan_module=self.plan_module,
            capability=self.capability,
            created_by=self.user,
        )
        self.plan_quota = PlanQuota.objects.create(
            plan_version=self.plan_version,
            quota_key="max_users",
            name="Max Users",
            scope=QuotaScope.PLAN,
            limit_type=QuotaLimitType.NUMERIC,
            limit_value=100,
            unit="users",
            reset_period=QuotaResetPeriod.MONTHLY,
            created_by=self.user,
            updated_by=self.user,
        )

    # -----------------------------------------------------------------------
    # 1. Plan.is_public & Audit Enums
    # -----------------------------------------------------------------------

    def test_plan_is_public_field(self):
        """Plan.is_public defaults to False and is indexed."""
        field = Plan._meta.get_field("is_public")
        self.assertIsInstance(field, models.BooleanField)
        self.assertFalse(field.default)
        self.assertTrue(field.db_index)

    def test_subscription_audit_enums(self):
        """AuditAction has 9 subscription actions and AuditTargetType has SUBSCRIPTION."""
        expected_actions = [
            "subscription_created",
            "subscription_trial_started",
            "subscription_trial_converted",
            "subscription_trial_expired",
            "subscription_plan_changed",
            "subscription_suspended",
            "subscription_reactivated",
            "subscription_cancelled",
            "subscription_reconciled",
        ]
        for action in expected_actions:
            self.assertIn(action, AuditAction.values)

        self.assertIn("subscription", AuditTargetType.values)
        self.assertEqual(AuditTargetType.SUBSCRIPTION, "subscription")

    # -----------------------------------------------------------------------
    # 2. Table Names and Schema Setup
    # -----------------------------------------------------------------------

    def test_exact_table_names(self):
        """All 5 models use explicit table names matching the specification."""
        self.assertEqual(
            OrganizationSubscription._meta.db_table,
            "organization_subscriptions",
        )
        self.assertEqual(
            SubscriptionProductEntitlement._meta.db_table,
            "subscription_product_entitlements",
        )
        self.assertEqual(
            SubscriptionModuleEntitlement._meta.db_table,
            "subscription_module_entitlements",
        )
        self.assertEqual(
            SubscriptionCapabilityEntitlement._meta.db_table,
            "subscription_capability_entitlements",
        )
        self.assertEqual(
            SubscriptionQuotaEntitlement._meta.db_table,
            "subscription_quota_entitlements",
        )

    def test_exact_model_fields(self):
        """Verify the exact authorized field set for each subscription model."""
        def get_fields(model):
            return {f.name for f in model._meta.fields}

        self.assertEqual(
            get_fields(OrganizationSubscription),
            {
                "id",
                "organization",
                "plan_version",
                "plan_price",
                "previous_subscription",
                "plan_code_snapshot",
                "plan_name_snapshot",
                "version_number_snapshot",
                "currency",
                "billing_interval",
                "amount",
                "status",
                "started_as_trial",
                "trial_started_at",
                "trial_ends_at",
                "current_period_start",
                "current_period_end",
                "cancelled_at",
                "ended_at",
                "change_reason",
                "cancellation_reason",
                "suspension_reason",
                "created_by",
                "updated_by",
                "created_at",
                "updated_at",
            },
        )
        self.assertEqual(
            get_fields(SubscriptionProductEntitlement),
            {
                "id",
                "subscription",
                "organization",
                "product",
                "plan_product",
                "product_code_snapshot",
                "product_name_snapshot",
                "created_at",
            },
        )
        self.assertEqual(
            get_fields(SubscriptionModuleEntitlement),
            {
                "id",
                "subscription",
                "organization",
                "module",
                "plan_module",
                "module_code_snapshot",
                "module_name_snapshot",
                "created_at",
            },
        )
        self.assertEqual(
            get_fields(SubscriptionCapabilityEntitlement),
            {
                "id",
                "subscription",
                "organization",
                "capability",
                "plan_capability",
                "capability_code_snapshot",
                "capability_name_snapshot",
                "created_at",
            },
        )
        self.assertEqual(
            get_fields(SubscriptionQuotaEntitlement),
            {
                "id",
                "subscription",
                "organization",
                "plan_quota",
                "quota_key",
                "name",
                "scope",
                "product",
                "module",
                "capability",
                "target_code_snapshot",
                "target_name_snapshot",
                "limit_type",
                "limit_value",
                "unit",
                "is_hard_limit",
                "reset_period",
                "created_at",
            },
        )

    # -----------------------------------------------------------------------
    # 3. Model Creation & Happy Path
    # -----------------------------------------------------------------------

    def test_create_trial_subscription_happy_path(self):
        """Create a valid trial subscription with all snapshots populated."""
        now = timezone.now()
        ends = now + timezone.timedelta(days=14)
        sub = OrganizationSubscription.objects.create(
            organization=self.org,
            plan_version=self.plan_version,
            plan_price=self.plan_price,
            plan_code_snapshot=self.plan.code,
            plan_name_snapshot=self.plan.name,
            version_number_snapshot=self.plan_version.version,
            billing_interval=self.plan_price.billing_interval,
            currency=self.plan_price.currency,
            amount=self.plan_price.amount,
            started_as_trial=True,
            trial_started_at=now,
            trial_ends_at=ends,
            status=SubscriptionStatus.TRIALING,
            created_by=self.user,
            updated_by=self.user,
        )
        self.assertIsNotNone(sub.id)
        self.assertEqual(sub.status, SubscriptionStatus.TRIALING)
        self.assertTrue(sub.started_as_trial)
        self.assertIsNone(sub.current_period_start)
        self.assertIsNone(sub.current_period_end)

    def test_create_active_subscription_happy_path(self):
        """Create a valid direct active subscription."""
        now = timezone.now()
        period_end = now + timezone.timedelta(days=30)
        sub = OrganizationSubscription.objects.create(
            organization=self.org,
            plan_version=self.plan_version,
            plan_price=self.plan_price,
            plan_code_snapshot=self.plan.code,
            plan_name_snapshot=self.plan.name,
            version_number_snapshot=self.plan_version.version,
            billing_interval=self.plan_price.billing_interval,
            currency=self.plan_price.currency,
            amount=self.plan_price.amount,
            started_as_trial=False,
            status=SubscriptionStatus.ACTIVE,
            current_period_start=now,
            current_period_end=period_end,
            created_by=self.user,
            updated_by=self.user,
        )
        self.assertIsNotNone(sub.id)
        self.assertEqual(sub.status, SubscriptionStatus.ACTIVE)
        self.assertFalse(sub.started_as_trial)
        self.assertIsNone(sub.trial_started_at)
        self.assertIsNone(sub.trial_ends_at)

    # -----------------------------------------------------------------------
    # 4. Immutability and Deletion Guards
    # -----------------------------------------------------------------------

    def test_instance_delete_rejected(self):
        """Direct instance deletion on OrganizationSubscription raises ValidationError."""
        now = timezone.now()
        sub = OrganizationSubscription.objects.create(
            organization=self.org,
            plan_version=self.plan_version,
            plan_price=self.plan_price,
            plan_code_snapshot=self.plan.code,
            plan_name_snapshot=self.plan.name,
            version_number_snapshot=self.plan_version.version,
            billing_interval=self.plan_price.billing_interval,
            currency=self.plan_price.currency,
            amount=self.plan_price.amount,
            started_as_trial=True,
            trial_started_at=now,
            trial_ends_at=now + timezone.timedelta(days=14),
            status=SubscriptionStatus.TRIALING,
            created_by=self.user,
            updated_by=self.user,
        )
        with self.assertRaises(ValidationError) as ctx:
            sub.delete()
        self.assertIn("Subscriptions cannot be deleted", str(ctx.exception))

    def test_queryset_delete_rejected(self):
        """QuerySet bulk deletion on OrganizationSubscription raises ValidationError."""
        now = timezone.now()
        OrganizationSubscription.objects.create(
            organization=self.org,
            plan_version=self.plan_version,
            plan_price=self.plan_price,
            plan_code_snapshot=self.plan.code,
            plan_name_snapshot=self.plan.name,
            version_number_snapshot=self.plan_version.version,
            billing_interval=self.plan_price.billing_interval,
            currency=self.plan_price.currency,
            amount=self.plan_price.amount,
            started_as_trial=True,
            trial_started_at=now,
            trial_ends_at=now + timezone.timedelta(days=14),
            status=SubscriptionStatus.TRIALING,
            created_by=self.user,
            updated_by=self.user,
        )
        with self.assertRaises(ValidationError) as ctx:
            OrganizationSubscription.objects.filter(organization=self.org).delete()
        self.assertIn("Subscriptions cannot be deleted", str(ctx.exception))

    def test_queryset_update_rejected(self):
        """QuerySet bulk update on OrganizationSubscription raises ValidationError."""
        now = timezone.now()
        OrganizationSubscription.objects.create(
            organization=self.org,
            plan_version=self.plan_version,
            plan_price=self.plan_price,
            plan_code_snapshot=self.plan.code,
            plan_name_snapshot=self.plan.name,
            version_number_snapshot=self.plan_version.version,
            billing_interval=self.plan_price.billing_interval,
            currency=self.plan_price.currency,
            amount=self.plan_price.amount,
            started_as_trial=True,
            trial_started_at=now,
            trial_ends_at=now + timezone.timedelta(days=14),
            status=SubscriptionStatus.TRIALING,
            created_by=self.user,
            updated_by=self.user,
        )
        with self.assertRaises(ValidationError) as ctx:
            OrganizationSubscription.objects.filter(organization=self.org).update(status="active")
        self.assertIn("Subscriptions cannot be bulk updated", str(ctx.exception))

    def test_immutable_field_mutation_full_save_rejected(self):
        """Mutating an immutable field in full save() raises ValidationError."""
        now = timezone.now()
        sub = OrganizationSubscription.objects.create(
            organization=self.org,
            plan_version=self.plan_version,
            plan_price=self.plan_price,
            plan_code_snapshot=self.plan.code,
            plan_name_snapshot=self.plan.name,
            version_number_snapshot=self.plan_version.version,
            billing_interval=self.plan_price.billing_interval,
            currency=self.plan_price.currency,
            amount=self.plan_price.amount,
            started_as_trial=True,
            trial_started_at=now,
            trial_ends_at=now + timezone.timedelta(days=14),
            status=SubscriptionStatus.TRIALING,
            created_by=self.user,
            updated_by=self.user,
        )
        sub.amount = Decimal("999.00")
        with self.assertRaises(ValidationError) as ctx:
            sub.save()
        self.assertIn("amount", str(ctx.exception))

    def test_immutable_field_mutation_update_fields_rejected(self):
        """Specifying an immutable field in update_fields raises ValidationError."""
        now = timezone.now()
        sub = OrganizationSubscription.objects.create(
            organization=self.org,
            plan_version=self.plan_version,
            plan_price=self.plan_price,
            plan_code_snapshot=self.plan.code,
            plan_name_snapshot=self.plan.name,
            version_number_snapshot=self.plan_version.version,
            billing_interval=self.plan_price.billing_interval,
            currency=self.plan_price.currency,
            amount=self.plan_price.amount,
            started_as_trial=True,
            trial_started_at=now,
            trial_ends_at=now + timezone.timedelta(days=14),
            status=SubscriptionStatus.TRIALING,
            created_by=self.user,
            updated_by=self.user,
        )
        with self.assertRaises(ValidationError) as ctx:
            sub.save(update_fields=["plan_version_id", "status"])
        self.assertIn("Immutable subscription field(s) cannot be updated", str(ctx.exception))

    def test_mutable_field_update_fields_permitted(self):
        """Permitted lifecycle fields can be saved via update_fields."""
        now = timezone.now()
        sub = OrganizationSubscription.objects.create(
            organization=self.org,
            plan_version=self.plan_version,
            plan_price=self.plan_price,
            plan_code_snapshot=self.plan.code,
            plan_name_snapshot=self.plan.name,
            version_number_snapshot=self.plan_version.version,
            billing_interval=self.plan_price.billing_interval,
            currency=self.plan_price.currency,
            amount=self.plan_price.amount,
            started_as_trial=True,
            trial_started_at=now,
            trial_ends_at=now + timezone.timedelta(days=14),
            status=SubscriptionStatus.TRIALING,
            created_by=self.user,
            updated_by=self.user,
        )
        # Convert trial to active
        period_start = timezone.now()
        period_end = period_start + timezone.timedelta(days=30)
        sub.status = SubscriptionStatus.ACTIVE
        sub.current_period_start = period_start
        sub.current_period_end = period_end
        sub.save(update_fields=["status", "current_period_start", "current_period_end", "updated_at"])

        sub.refresh_from_db()
        self.assertEqual(sub.status, SubscriptionStatus.ACTIVE)
        self.assertEqual(sub.current_period_start, period_start)
        self.assertEqual(sub.current_period_end, period_end)

    def test_bulk_update_rejected(self):
        """OrganizationSubscription bulk_update raises ValidationError."""
        now = timezone.now()
        sub = OrganizationSubscription.objects.create(
            organization=self.org,
            plan_version=self.plan_version,
            plan_price=self.plan_price,
            plan_code_snapshot=self.plan.code,
            plan_name_snapshot=self.plan.name,
            version_number_snapshot=self.plan_version.version,
            billing_interval=self.plan_price.billing_interval,
            currency=self.plan_price.currency,
            amount=self.plan_price.amount,
            started_as_trial=True,
            trial_started_at=now,
            trial_ends_at=now + timezone.timedelta(days=14),
            status=SubscriptionStatus.TRIALING,
            created_by=self.user,
            updated_by=self.user,
        )
        with self.assertRaises(ValidationError) as ctx:
            OrganizationSubscription.objects.filter(id=sub.id).bulk_update([sub], ["status"])
        self.assertIn("Subscriptions cannot be bulk updated", str(ctx.exception))

        with self.assertRaises(ValidationError) as ctx:
            OrganizationSubscription.objects.bulk_update([sub], ["status"])
        self.assertIn("Subscriptions cannot be bulk updated", str(ctx.exception))

    def test_change_reason_immutable_after_creation(self):
        """change_reason is captured at creation and cannot be modified afterwards."""
        now = timezone.now()
        sub = OrganizationSubscription.objects.create(
            organization=self.org,
            plan_version=self.plan_version,
            plan_price=self.plan_price,
            plan_code_snapshot=self.plan.code,
            plan_name_snapshot=self.plan.name,
            version_number_snapshot=self.plan_version.version,
            billing_interval=self.plan_price.billing_interval,
            currency=self.plan_price.currency,
            amount=self.plan_price.amount,
            started_as_trial=True,
            trial_started_at=now,
            trial_ends_at=now + timezone.timedelta(days=14),
            status=SubscriptionStatus.TRIALING,
            change_reason="Initial trial signup",
            created_by=self.user,
            updated_by=self.user,
        )
        self.assertEqual(sub.change_reason, "Initial trial signup")

        # Mutating via save() raises ValidationError
        sub.change_reason = "Altered reason"
        with self.assertRaises(ValidationError) as ctx:
            sub.save()
        self.assertIn("change_reason", str(ctx.exception))

        # Mutating via update_fields raises ValidationError
        sub.refresh_from_db()
        sub.change_reason = "Altered reason"
        with self.assertRaises(ValidationError) as ctx:
            sub.save(update_fields=["change_reason"])
        self.assertIn("change_reason", str(ctx.exception))

    def test_cancellation_and_suspension_reasons_mutable(self):
        """cancellation_reason and suspension_reason can be set during lifecycle updates."""
        now = timezone.now()
        sub = OrganizationSubscription.objects.create(
            organization=self.org,
            plan_version=self.plan_version,
            plan_price=self.plan_price,
            plan_code_snapshot=self.plan.code,
            plan_name_snapshot=self.plan.name,
            version_number_snapshot=self.plan_version.version,
            billing_interval=self.plan_price.billing_interval,
            currency=self.plan_price.currency,
            amount=self.plan_price.amount,
            started_as_trial=False,
            current_period_start=now,
            current_period_end=now + timezone.timedelta(days=30),
            status=SubscriptionStatus.ACTIVE,
            created_by=self.user,
            updated_by=self.user,
        )
        # Suspend with reason
        sub.status = SubscriptionStatus.SUSPENDED
        sub.suspension_reason = "Non-payment of invoice"
        sub.save(update_fields=["status", "suspension_reason", "updated_at"])
        sub.refresh_from_db()
        self.assertEqual(sub.status, SubscriptionStatus.SUSPENDED)
        self.assertEqual(sub.suspension_reason, "Non-payment of invoice")

        # Cancel with reason
        ended_at = timezone.now()
        sub.status = SubscriptionStatus.CANCELLED
        sub.cancelled_at = ended_at
        sub.ended_at = ended_at
        sub.cancellation_reason = "Customer churn"
        sub.save(update_fields=["status", "cancelled_at", "ended_at", "cancellation_reason", "updated_at"])
        sub.refresh_from_db()
        self.assertEqual(sub.status, SubscriptionStatus.CANCELLED)
        self.assertEqual(sub.cancellation_reason, "Customer churn")

    # -----------------------------------------------------------------------
    # 5. Database Constraints on OrganizationSubscription
    # -----------------------------------------------------------------------

    def test_single_open_subscription_constraint(self):
        """At most one open (trialing, active, suspended) subscription per organization."""
        now = timezone.now()
        OrganizationSubscription.objects.create(
            organization=self.org,
            plan_version=self.plan_version,
            plan_price=self.plan_price,
            plan_code_snapshot=self.plan.code,
            plan_name_snapshot=self.plan.name,
            version_number_snapshot=self.plan_version.version,
            billing_interval=self.plan_price.billing_interval,
            currency=self.plan_price.currency,
            amount=self.plan_price.amount,
            started_as_trial=True,
            trial_started_at=now,
            trial_ends_at=now + timezone.timedelta(days=14),
            status=SubscriptionStatus.TRIALING,
            created_by=self.user,
            updated_by=self.user,
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                OrganizationSubscription.objects.create(
                    organization=self.org,
                    plan_version=self.plan_version,
                    plan_price=self.plan_price,
                    plan_code_snapshot=self.plan.code,
                    plan_name_snapshot=self.plan.name,
                    version_number_snapshot=self.plan_version.version,
                    billing_interval=self.plan_price.billing_interval,
                    currency=self.plan_price.currency,
                    amount=self.plan_price.amount,
                    started_as_trial=False,
                    status=SubscriptionStatus.ACTIVE,
                    current_period_start=now,
                    current_period_end=now + timezone.timedelta(days=30),
                    created_by=self.user,
                    updated_by=self.user,
                )

    def test_negative_amount_rejected_by_db(self):
        """sub_amount_gte_zero constraint rejects negative amounts."""
        now = timezone.now()
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                OrganizationSubscription.objects.create(
                    organization=self.org,
                    plan_version=self.plan_version,
                    plan_price=self.plan_price,
                    plan_code_snapshot=self.plan.code,
                    plan_name_snapshot=self.plan.name,
                    version_number_snapshot=self.plan_version.version,
                    billing_interval=self.plan_price.billing_interval,
                    currency=self.plan_price.currency,
                    amount=Decimal("-10.00"),
                    started_as_trial=True,
                    trial_started_at=now,
                    trial_ends_at=now + timezone.timedelta(days=14),
                    status=SubscriptionStatus.TRIALING,
                    created_by=self.user,
                    updated_by=self.user,
                )

    def test_trial_origin_fields_constraint(self):
        """started_as_trial=True requires trial dates; False forbids them."""
        now = timezone.now()
        # started_as_trial=True without dates must fail
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                OrganizationSubscription.objects.create(
                    organization=self.org,
                    plan_version=self.plan_version,
                    plan_price=self.plan_price,
                    plan_code_snapshot=self.plan.code,
                    plan_name_snapshot=self.plan.name,
                    version_number_snapshot=self.plan_version.version,
                    billing_interval=self.plan_price.billing_interval,
                    currency=self.plan_price.currency,
                    amount=self.plan_price.amount,
                    started_as_trial=True,
                    trial_started_at=None,
                    trial_ends_at=None,
                    status=SubscriptionStatus.TRIALING,
                    created_by=self.user,
                    updated_by=self.user,
                )

    def test_active_dates_valid_constraint(self):
        """Active subscription requires current_period_start and current_period_end."""
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                OrganizationSubscription.objects.create(
                    organization=self.org,
                    plan_version=self.plan_version,
                    plan_price=self.plan_price,
                    plan_code_snapshot=self.plan.code,
                    plan_name_snapshot=self.plan.name,
                    version_number_snapshot=self.plan_version.version,
                    billing_interval=self.plan_price.billing_interval,
                    currency=self.plan_price.currency,
                    amount=self.plan_price.amount,
                    started_as_trial=False,
                    status=SubscriptionStatus.ACTIVE,
                    current_period_start=None,
                    current_period_end=None,
                    created_by=self.user,
                    updated_by=self.user,
                )

    def test_cancelled_at_valid_constraint(self):
        """status=cancelled requires cancelled_at to be non-null and ended_at non-null."""
        now = timezone.now()
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                # cancelled without cancelled_at
                OrganizationSubscription.objects.create(
                    organization=self.org,
                    plan_version=self.plan_version,
                    plan_price=self.plan_price,
                    plan_code_snapshot=self.plan.code,
                    plan_name_snapshot=self.plan.name,
                    version_number_snapshot=self.plan_version.version,
                    billing_interval=self.plan_price.billing_interval,
                    currency=self.plan_price.currency,
                    amount=self.plan_price.amount,
                    started_as_trial=False,
                    status=SubscriptionStatus.CANCELLED,
                    cancelled_at=None,
                    ended_at=now,
                    created_by=self.user,
                    updated_by=self.user,
                )

    # -----------------------------------------------------------------------
    # 6. Child Entitlement Snapshot Models & Quota Scope Constraints
    # -----------------------------------------------------------------------

    def test_create_entitlements_happy_path(self):
        """Create child product, module, capability, and quota entitlement snapshots."""
        now = timezone.now()
        sub = OrganizationSubscription.objects.create(
            organization=self.org,
            plan_version=self.plan_version,
            plan_price=self.plan_price,
            plan_code_snapshot=self.plan.code,
            plan_name_snapshot=self.plan.name,
            version_number_snapshot=self.plan_version.version,
            billing_interval=self.plan_price.billing_interval,
            currency=self.plan_price.currency,
            amount=self.plan_price.amount,
            started_as_trial=True,
            trial_started_at=now,
            trial_ends_at=now + timezone.timedelta(days=14),
            status=SubscriptionStatus.TRIALING,
            created_by=self.user,
            updated_by=self.user,
        )

        pe = SubscriptionProductEntitlement.objects.create(
            subscription=sub,
            organization=self.org,
            product=self.product,
            plan_product=self.plan_product,
            product_code_snapshot=self.product.code,
            product_name_snapshot=self.product.name,
        )
        me = SubscriptionModuleEntitlement.objects.create(
            subscription=sub,
            organization=self.org,
            module=self.module,
            plan_module=self.plan_module,
            module_code_snapshot=self.module.code,
            module_name_snapshot=self.module.name,
        )
        ce = SubscriptionCapabilityEntitlement.objects.create(
            subscription=sub,
            organization=self.org,
            capability=self.capability,
            plan_capability=self.plan_capability,
            capability_code_snapshot=self.capability.code,
            capability_name_snapshot=self.capability.name,
        )
        qe = SubscriptionQuotaEntitlement.objects.create(
            subscription=sub,
            organization=self.org,
            plan_quota=self.plan_quota,
            quota_key="max_users",
            name="Max Users",
            scope=QuotaScope.PLAN,
            limit_type=QuotaLimitType.NUMERIC,
            limit_value=100,
            unit="users",
            is_hard_limit=True,
            reset_period=QuotaResetPeriod.MONTHLY,
        )

        self.assertIsNotNone(pe.id)
        self.assertIsNotNone(me.id)
        self.assertIsNotNone(ce.id)
        self.assertIsNotNone(qe.id)

    def test_entitlement_delete_rejected(self):
        """Child entitlement instances cannot be deleted."""
        now = timezone.now()
        sub = OrganizationSubscription.objects.create(
            organization=self.org,
            plan_version=self.plan_version,
            plan_price=self.plan_price,
            plan_code_snapshot=self.plan.code,
            plan_name_snapshot=self.plan.name,
            version_number_snapshot=self.plan_version.version,
            billing_interval=self.plan_price.billing_interval,
            currency=self.plan_price.currency,
            amount=self.plan_price.amount,
            started_as_trial=True,
            trial_started_at=now,
            trial_ends_at=now + timezone.timedelta(days=14),
            status=SubscriptionStatus.TRIALING,
            created_by=self.user,
            updated_by=self.user,
        )
        pe = SubscriptionProductEntitlement.objects.create(
            subscription=sub,
            organization=self.org,
            product=self.product,
            plan_product=self.plan_product,
            product_code_snapshot=self.product.code,
            product_name_snapshot=self.product.name,
        )
        with self.assertRaises(ValidationError):
            pe.delete()

    def test_quota_scope_target_valid_constraint(self):
        """sub_quota_scope_target_valid constraint enforces typed scope target alignment."""
        now = timezone.now()
        sub = OrganizationSubscription.objects.create(
            organization=self.org,
            plan_version=self.plan_version,
            plan_price=self.plan_price,
            plan_code_snapshot=self.plan.code,
            plan_name_snapshot=self.plan.name,
            version_number_snapshot=self.plan_version.version,
            billing_interval=self.plan_price.billing_interval,
            currency=self.plan_price.currency,
            amount=self.plan_price.amount,
            started_as_trial=True,
            trial_started_at=now,
            trial_ends_at=now + timezone.timedelta(days=14),
            status=SubscriptionStatus.TRIALING,
            created_by=self.user,
            updated_by=self.user,
        )

        # Plan scope but product FK is populated -> must fail
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                SubscriptionQuotaEntitlement.objects.create(
                    subscription=sub,
                    organization=self.org,
                    plan_quota=self.plan_quota,
                    quota_key="mismatched_scope",
                    name="Mismatched",
                    scope=QuotaScope.PLAN,
                    product=self.product,  # Violation!
                    limit_type=QuotaLimitType.NUMERIC,
                    limit_value=50,
                    unit="count",
                    is_hard_limit=True,
                    reset_period=QuotaResetPeriod.MONTHLY,
                )

        # Product scope but product FK is NULL -> must fail
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                SubscriptionQuotaEntitlement.objects.create(
                    subscription=sub,
                    organization=self.org,
                    plan_quota=self.plan_quota,
                    quota_key="mismatched_scope_2",
                    name="Mismatched 2",
                    scope=QuotaScope.PRODUCT,
                    product=None,  # Violation!
                    limit_type=QuotaLimitType.NUMERIC,
                    limit_value=50,
                    unit="count",
                    is_hard_limit=True,
                    reset_period=QuotaResetPeriod.MONTHLY,
                )

    # -----------------------------------------------------------------------
    # 7. Referential Protection (PROTECT)
    # -----------------------------------------------------------------------

    def test_referential_protection_on_organization(self):
        """Deleting an organization with a subscription raises ProtectedError."""
        now = timezone.now()
        OrganizationSubscription.objects.create(
            organization=self.org,
            plan_version=self.plan_version,
            plan_price=self.plan_price,
            plan_code_snapshot=self.plan.code,
            plan_name_snapshot=self.plan.name,
            version_number_snapshot=self.plan_version.version,
            billing_interval=self.plan_price.billing_interval,
            currency=self.plan_price.currency,
            amount=self.plan_price.amount,
            started_as_trial=True,
            trial_started_at=now,
            trial_ends_at=now + timezone.timedelta(days=14),
            status=SubscriptionStatus.TRIALING,
            created_by=self.user,
            updated_by=self.user,
        )
        with self.assertRaises(ProtectedError):
            self.org.delete()

    def test_referential_protection_on_plan_version(self):
        """Deleting a plan_version with a subscription raises ProtectedError."""
        now = timezone.now()
        OrganizationSubscription.objects.create(
            organization=self.org,
            plan_version=self.plan_version,
            plan_price=self.plan_price,
            plan_code_snapshot=self.plan.code,
            plan_name_snapshot=self.plan.name,
            version_number_snapshot=self.plan_version.version,
            billing_interval=self.plan_price.billing_interval,
            currency=self.plan_price.currency,
            amount=self.plan_price.amount,
            started_as_trial=True,
            trial_started_at=now,
            trial_ends_at=now + timezone.timedelta(days=14),
            status=SubscriptionStatus.TRIALING,
            created_by=self.user,
            updated_by=self.user,
        )
        with self.assertRaises(ProtectedError):
            self.plan_version.delete()

    # -----------------------------------------------------------------------
    # 8. Advanced Constraints, Multiple Closed Subscriptions, & Reverse Accessors
    # -----------------------------------------------------------------------

    def test_multiple_closed_subscriptions_allowed(self):
        """Multiple closed (cancelled or trial_expired) subscriptions can exist for the same org."""
        now = timezone.now()
        # First cancelled subscription
        s1 = OrganizationSubscription.objects.create(
            organization=self.org,
            plan_version=self.plan_version,
            plan_price=self.plan_price,
            plan_code_snapshot=self.plan.code,
            plan_name_snapshot=self.plan.name,
            version_number_snapshot=self.plan_version.version,
            billing_interval=self.plan_price.billing_interval,
            currency=self.plan_price.currency,
            amount=self.plan_price.amount,
            started_as_trial=False,
            status=SubscriptionStatus.CANCELLED,
            cancelled_at=now,
            ended_at=now,
            created_by=self.user,
            updated_by=self.user,
        )
        # Second expired trial subscription
        s2 = OrganizationSubscription.objects.create(
            organization=self.org,
            plan_version=self.plan_version,
            plan_price=self.plan_price,
            plan_code_snapshot=self.plan.code,
            plan_name_snapshot=self.plan.name,
            version_number_snapshot=self.plan_version.version,
            billing_interval=self.plan_price.billing_interval,
            currency=self.plan_price.currency,
            amount=self.plan_price.amount,
            started_as_trial=True,
            trial_started_at=now - timezone.timedelta(days=14),
            trial_ends_at=now,
            status=SubscriptionStatus.EXPIRED,
            ended_at=now,
            created_by=self.user,
            updated_by=self.user,
        )
        self.assertIsNotNone(s1.id)
        self.assertIsNotNone(s2.id)

    def test_trial_expired_must_start_as_trial(self):
        """sub_expired_trial_origin rejects status=expired when started_as_trial=False."""
        now = timezone.now()
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                OrganizationSubscription.objects.create(
                    organization=self.org,
                    plan_version=self.plan_version,
                    plan_price=self.plan_price,
                    plan_code_snapshot=self.plan.code,
                    plan_name_snapshot=self.plan.name,
                    version_number_snapshot=self.plan_version.version,
                    billing_interval=self.plan_price.billing_interval,
                    currency=self.plan_price.currency,
                    amount=self.plan_price.amount,
                    started_as_trial=False,  # Violation!
                    status=SubscriptionStatus.EXPIRED,
                    ended_at=now,
                    created_by=self.user,
                    updated_by=self.user,
                )

    def test_reverse_accessors(self):
        """Verify explicit reverse accessors from Organization, PlanVersion, and PlanPrice."""
        now = timezone.now()
        sub = OrganizationSubscription.objects.create(
            organization=self.org,
            plan_version=self.plan_version,
            plan_price=self.plan_price,
            plan_code_snapshot=self.plan.code,
            plan_name_snapshot=self.plan.name,
            version_number_snapshot=self.plan_version.version,
            billing_interval=self.plan_price.billing_interval,
            currency=self.plan_price.currency,
            amount=self.plan_price.amount,
            started_as_trial=True,
            trial_started_at=now,
            trial_ends_at=now + timezone.timedelta(days=14),
            status=SubscriptionStatus.TRIALING,
            created_by=self.user,
            updated_by=self.user,
        )
        self.assertIn(sub, self.org.subscriptions.all())
        self.assertIn(sub, self.plan_version.subscriptions.all())
        self.assertIn(sub, self.plan_price.subscriptions.all())

    def test_audit_subscription_constraints(self):
        """Verify DB constraints on AuditLog for subscription events."""
        # 1. Valid subscription audit event
        sub_id = uuid.uuid4()
        audit_log = AuditLog.objects.create(
            actor=self.user,
            actor_name=self.user.full_name,
            action=AuditAction.SUBSCRIPTION_CREATED,
            target_type=AuditTargetType.SUBSCRIPTION,
            target_id=sub_id,
            target_repr=f"Subscription {sub_id}",
            organization_id=self.org.id,
            operation_source="interactive",
        )
        self.assertIsNotNone(audit_log.id)

        # 2. Subscription target_type without organization_id must violate audit_subscription_org_id_req
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                AuditLog.objects.create(
                    actor=self.user,
                    actor_name=self.user.full_name,
                    action=AuditAction.SUBSCRIPTION_CREATED,
                    target_type=AuditTargetType.SUBSCRIPTION,
                    target_id=sub_id,
                    target_repr=f"Subscription {sub_id}",
                    organization_id=None,  # Violation!
                    operation_source="interactive",
                )

        # 3. Subscription action with non-subscription target_type must violate audit_subscription_target_match
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                AuditLog.objects.create(
                    actor=self.user,
                    actor_name=self.user.full_name,
                    action=AuditAction.SUBSCRIPTION_CREATED,
                    target_type=AuditTargetType.PRODUCT,  # Violation!
                    target_id=sub_id,
                    target_repr=f"Subscription {sub_id}",
                    organization_id=self.org.id,
                    operation_source="interactive",
                )
