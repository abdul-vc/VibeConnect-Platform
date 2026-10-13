"""Focused unit test suite for Phase 2C Stage 2 Subscription Domain Services.

Contains exactly 20 focused tests verifying:
1. Exact required public service names exist and obsolete names are removed.
2. Calendar-month and authoritative get_interval_months utilities.
3. Start subscription trial with snapshots (no reconciliation audit).
4. Create direct active subscription (no reconciliation audit).
5. Prevent duplicate open subscriptions per organization.
6. Rejection of subscription creation for retired organizations.
7. Rejection of subscription creation for non-active plan versions.
8. Rejection of subscription creation for mismatched plan prices.
9. Trial conversion to active and rejection for non-trialing subscriptions.
10. Subscription suspension with documented reason.
11. Subscription reactivation.
12. Subscription cancellation with documented reason.
13. Immediate plan change with historical predecessor/successor chain.
14. Subscription reconciliation writes only subscription snapshots; direct grants remain unchanged.
15. No-op manual reconciliation emits no audit event.
16. Material repair reconciliation emits exactly one SUBSCRIPTION_RECONCILED audit.
17. Effective access helpers (read-only direct grants fallback).
18. Effective scoped quota retrieval helper.
19. Idempotent expire_trial_subscriptions batch service and management command.
20. Atomic organization retirement subscription cancellation.
"""

from datetime import datetime, timezone as dt_timezone
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIRequestFactory

from apps.auditlog.models import AuditAction, AuditLog, AuditTargetType
from apps.entitlements.models import EntitlementStatus, OrganizationProductEntitlement
from apps.organizations.models import Organization, OrganizationStatus
from apps.organizations.views import OrganizationViewSet
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
from apps.subscriptions import services
from apps.subscriptions.models import (
    OrganizationSubscription,
    SubscriptionProductEntitlement,
    SubscriptionStatus,
)
from apps.subscriptions.services import (
    SubscriptionNotFoundError,
    SubscriptionValidationError,
    _reconcile_subscription_snapshots,
    cancel_open_subscriptions_for_organization,
    cancel_subscription,
    change_subscription_plan,
    convert_trial_to_active,
    create_active_subscription,
    expire_trial_subscriptions,
    get_active_subscription,
    get_effective_quota,
    has_capability_access,
    has_module_access,
    has_product_access,
    reactivate_subscription,
    reconcile_subscription_entitlements,
    start_subscription_trial,
    suspend_subscription,
)
from apps.subscriptions.utils import (
    add_calendar_months,
    calculate_period_end,
    calculate_trial_end,
    get_interval_months,
)

User = get_user_model()


class SubscriptionServicesTests(TestCase):
    """Test suite covering Phase 2C Stage 2 domain services and lifecycle operations."""

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

    # 1. Exact required public service names contract
    def test_01_required_public_service_names_exist(self):
        """Verify exact required public service names exist and obsolete names are removed."""
        expected_names = [
            "start_subscription_trial",
            "create_active_subscription",
            "convert_trial_to_active",
            "change_subscription_plan",
            "suspend_subscription",
            "reactivate_subscription",
            "cancel_subscription",
            "expire_trial_subscriptions",
            "reconcile_subscription_entitlements",
            "cancel_open_subscriptions_for_organization",
            "_reconcile_subscription_snapshots",
            "has_product_access",
            "has_module_access",
            "has_capability_access",
            "get_effective_quota",
        ]
        for name in expected_names:
            self.assertTrue(
                hasattr(services, name),
                f"Required service '{name}' is missing from apps.subscriptions.services",
            )

        # Ensure competing/obsolete aliases do not exist
        obsolete_names = [
            "create_trial_subscription",
            "expire_trial",
            "reconcile_organization_product_entitlements",
            "cancel_subscriptions_for_retired_org",
        ]
        for name in obsolete_names:
            self.assertFalse(
                hasattr(services, name),
                f"Obsolete service alias '{name}' must not be exposed",
            )

    # 2. Calendar-month utilities and get_interval_months
    def test_02_calendar_month_utilities_and_get_interval_months(self):
        """Calendar-month calculations and authoritative get_interval_months mapping."""
        self.assertEqual(get_interval_months(BillingInterval.MONTHLY), 1)
        self.assertEqual(get_interval_months(BillingInterval.QUARTERLY), 3)
        self.assertEqual(get_interval_months(BillingInterval.ANNUAL), 12)
        with self.assertRaises(ValueError):
            get_interval_months("invalid_interval")

        dt1 = datetime(2025, 1, 31, 12, 0, 0, tzinfo=dt_timezone.utc)
        res_feb = add_calendar_months(dt1, 1)
        self.assertEqual((res_feb.year, res_feb.month, res_feb.day), (2025, 2, 28))

        dt_leap = datetime(2024, 1, 31, 12, 0, 0, tzinfo=dt_timezone.utc)
        self.assertEqual(add_calendar_months(dt_leap, 1).day, 29)

        self.assertEqual(calculate_period_end(dt1, BillingInterval.MONTHLY).month, 2)
        self.assertEqual(calculate_period_end(dt1, BillingInterval.QUARTERLY).month, 4)
        self.assertEqual(calculate_period_end(dt1, BillingInterval.ANNUAL).year, 2026)

        trial_end = calculate_trial_end(dt1, 14)
        self.assertEqual((trial_end - dt1).days, 14)
        with self.assertRaises(ValueError):
            calculate_trial_end(dt1, 0)

    # 3. Start subscription trial
    def test_03_start_subscription_trial(self):
        """Start subscription trial creates snapshots and emits trial started audit without reconciliation audit."""
        sub = start_subscription_trial(
            organization_id=self.org.id,
            plan_version_id=self.plan_version.id,
            plan_price_id=self.plan_price.id,
            actor=self.user,
            trial_days=14,
            change_reason="Initial trial",
        )
        self.assertEqual(sub.status, SubscriptionStatus.TRIALING)
        self.assertTrue(sub.started_as_trial)
        self.assertIsNotNone(sub.trial_started_at)
        self.assertIsNotNone(sub.trial_ends_at)
        self.assertIsNone(sub.current_period_start)

        # Snapshots created
        self.assertEqual(sub.product_entitlements.count(), 1)
        self.assertEqual(sub.module_entitlements.count(), 1)
        self.assertEqual(sub.capability_entitlements.count(), 1)
        self.assertEqual(sub.quota_entitlements.count(), 1)

        # Verification of audit logs: SUBSCRIPTION_TRIAL_STARTED emitted, NO SUBSCRIPTION_RECONCILED emitted
        self.assertTrue(
            AuditLog.objects.filter(
                action=AuditAction.SUBSCRIPTION_TRIAL_STARTED,
                target_id=sub.id,
            ).exists()
        )
        self.assertFalse(
            AuditLog.objects.filter(
                action=AuditAction.SUBSCRIPTION_RECONCILED,
                target_id=sub.id,
            ).exists()
        )

    # 4. Create direct active subscription
    def test_04_create_active_subscription(self):
        """Direct active subscription creation populates active billing period and audit trail without reconciliation audit."""
        sub = create_active_subscription(
            organization_id=self.org.id,
            plan_version_id=self.plan_version.id,
            plan_price_id=self.plan_price.id,
            actor=self.user,
        )
        self.assertEqual(sub.status, SubscriptionStatus.ACTIVE)
        self.assertFalse(sub.started_as_trial)
        self.assertIsNotNone(sub.current_period_start)
        self.assertIsNotNone(sub.current_period_end)

        self.assertTrue(
            AuditLog.objects.filter(
                action=AuditAction.SUBSCRIPTION_CREATED,
                target_id=sub.id,
            ).exists()
        )
        self.assertFalse(
            AuditLog.objects.filter(
                action=AuditAction.SUBSCRIPTION_RECONCILED,
                target_id=sub.id,
            ).exists()
        )

    # 5. Prevent duplicate open subscription
    def test_05_prevent_duplicate_open_subscription(self):
        """Organization cannot have more than one open subscription simultaneously."""
        start_subscription_trial(
            organization_id=self.org.id,
            plan_version_id=self.plan_version.id,
            plan_price_id=self.plan_price.id,
            actor=self.user,
        )
        with self.assertRaises(SubscriptionValidationError) as ctx:
            create_active_subscription(
                organization_id=self.org.id,
                plan_version_id=self.plan_version.id,
                plan_price_id=self.plan_price.id,
                actor=self.user,
            )
        self.assertIn("already has an open subscription", str(ctx.exception))

    # 6. Rejection for retired organization
    def test_06_rejection_for_retired_organization(self):
        """Cannot create subscription for a retired organization."""
        self.org.status = OrganizationStatus.RETIRED
        self.org.save(update_fields=["status"])

        with self.assertRaises(SubscriptionValidationError) as ctx:
            start_subscription_trial(
                organization_id=self.org.id,
                plan_version_id=self.plan_version.id,
                plan_price_id=self.plan_price.id,
                actor=self.user,
            )
        self.assertIn("retired organization", str(ctx.exception))

    # 7. Rejection for non-active plan version
    def test_07_rejection_for_non_active_plan_version(self):
        """Cannot subscribe to draft or retired plan versions."""
        draft_ver = PlanVersion.objects.create(
            plan=self.plan,
            version=2,
            status=PlanVersionStatus.DRAFT,
            created_by=self.user,
            updated_by=self.user,
        )
        price = PlanPrice.objects.create(
            plan_version=draft_ver,
            currency=PlanCurrency.USD,
            billing_interval=BillingInterval.MONTHLY,
            amount=Decimal("150.00"),
            created_by=self.user,
            updated_by=self.user,
        )
        with self.assertRaises(SubscriptionValidationError) as ctx:
            create_active_subscription(
                organization_id=self.org.id,
                plan_version_id=draft_ver.id,
                plan_price_id=price.id,
                actor=self.user,
            )
        self.assertIn("must be 'active'", str(ctx.exception))

    # 8. Rejection for mismatched plan price
    def test_08_rejection_for_mismatched_plan_price(self):
        """PlanPrice must belong to the specified PlanVersion."""
        other_plan = Plan.objects.create(
            code="starter",
            name="Starter Plan",
            created_by=self.user,
            updated_by=self.user,
        )
        other_ver = PlanVersion.objects.create(
            plan=other_plan,
            version=1,
            status=PlanVersionStatus.ACTIVE,
            activated_at=timezone.now(),
            created_by=self.user,
            updated_by=self.user,
        )
        other_price = PlanPrice.objects.create(
            plan_version=other_ver,
            currency=PlanCurrency.USD,
            billing_interval=BillingInterval.MONTHLY,
            amount=Decimal("49.00"),
            created_by=self.user,
            updated_by=self.user,
        )
        with self.assertRaises(SubscriptionValidationError) as ctx:
            create_active_subscription(
                organization_id=self.org.id,
                plan_version_id=self.plan_version.id,
                plan_price_id=other_price.id,
                actor=self.user,
            )
        self.assertIn("does not belong", str(ctx.exception))

    # 9. Trial conversion to active
    def test_09_convert_trial_to_active(self):
        """Trialing subscription converts to active and sets active billing period."""
        sub = start_subscription_trial(
            organization_id=self.org.id,
            plan_version_id=self.plan_version.id,
            plan_price_id=self.plan_price.id,
            actor=self.user,
        )
        activated = convert_trial_to_active(subscription_id=sub.id, actor=self.user)
        self.assertEqual(activated.status, SubscriptionStatus.ACTIVE)
        self.assertIsNotNone(activated.current_period_start)
        self.assertIsNotNone(activated.current_period_end)

        self.assertTrue(
            AuditLog.objects.filter(
                action=AuditAction.SUBSCRIPTION_TRIAL_CONVERTED,
                target_id=sub.id,
            ).exists()
        )

        # Converting a non-trialing subscription raises ValidationError
        with self.assertRaises(SubscriptionValidationError):
            convert_trial_to_active(subscription_id=activated.id, actor=self.user)

    # 10. Suspend subscription
    def test_10_suspend_subscription(self):
        """Active subscription can be suspended with documented reason."""
        sub = create_active_subscription(
            organization_id=self.org.id,
            plan_version_id=self.plan_version.id,
            plan_price_id=self.plan_price.id,
            actor=self.user,
        )
        suspended = suspend_subscription(
            subscription_id=sub.id,
            actor=self.user,
            reason="Payment past due",
        )
        self.assertEqual(suspended.status, SubscriptionStatus.SUSPENDED)
        self.assertEqual(suspended.suspension_reason, "Payment past due")

        self.assertTrue(
            AuditLog.objects.filter(
                action=AuditAction.SUBSCRIPTION_SUSPENDED,
                target_id=sub.id,
            ).exists()
        )

    # 11. Reactivate subscription
    def test_11_reactivate_subscription(self):
        """Suspended subscription can be reactivated."""
        sub = create_active_subscription(
            organization_id=self.org.id,
            plan_version_id=self.plan_version.id,
            plan_price_id=self.plan_price.id,
            actor=self.user,
        )
        suspend_subscription(subscription_id=sub.id, actor=self.user, reason="Hold")
        reactivated = reactivate_subscription(subscription_id=sub.id, actor=self.user)
        self.assertEqual(reactivated.status, SubscriptionStatus.ACTIVE)
        self.assertEqual(reactivated.suspension_reason, "")

        self.assertTrue(
            AuditLog.objects.filter(
                action=AuditAction.SUBSCRIPTION_REACTIVATED,
                target_id=sub.id,
            ).exists()
        )

    # 12. Cancel subscription
    def test_12_cancel_subscription(self):
        """Open subscription cancels and records cancellation reason and timestamps."""
        sub = create_active_subscription(
            organization_id=self.org.id,
            plan_version_id=self.plan_version.id,
            plan_price_id=self.plan_price.id,
            actor=self.user,
        )
        cancelled = cancel_subscription(
            subscription_id=sub.id,
            actor=self.user,
            reason="Customer request",
        )
        self.assertEqual(cancelled.status, SubscriptionStatus.CANCELLED)
        self.assertIsNotNone(cancelled.cancelled_at)
        self.assertIsNotNone(cancelled.ended_at)
        self.assertEqual(cancelled.cancellation_reason, "Customer request")

        self.assertTrue(
            AuditLog.objects.filter(
                action=AuditAction.SUBSCRIPTION_CANCELLED,
                target_id=sub.id,
            ).exists()
        )

    # 13. Immediate plan change with historical successor record
    def test_13_change_subscription_plan_immediate_successor(self):
        """Plan change cancels predecessor and creates active linked successor without reconciliation audit."""
        old_sub = create_active_subscription(
            organization_id=self.org.id,
            plan_version_id=self.plan_version.id,
            plan_price_id=self.plan_price.id,
            actor=self.user,
        )

        pro_plan = Plan.objects.create(
            code="pro_plan",
            name="Pro Plan",
            created_by=self.user,
            updated_by=self.user,
        )
        pro_ver = PlanVersion.objects.create(
            plan=pro_plan,
            version=1,
            status=PlanVersionStatus.ACTIVE,
            activated_at=timezone.now(),
            created_by=self.user,
            updated_by=self.user,
        )
        pro_price = PlanPrice.objects.create(
            plan_version=pro_ver,
            currency=PlanCurrency.USD,
            billing_interval=BillingInterval.MONTHLY,
            amount=Decimal("99.00"),
            created_by=self.user,
            updated_by=self.user,
        )
        PlanProduct.objects.create(
            plan_version=pro_ver,
            product=self.product,
            created_by=self.user,
        )

        successor = change_subscription_plan(
            subscription_id=old_sub.id,
            new_plan_version_id=pro_ver.id,
            new_plan_price_id=pro_price.id,
            actor=self.user,
            change_reason="Downgrade to Pro",
        )

        old_sub.refresh_from_db()
        self.assertEqual(old_sub.status, SubscriptionStatus.CANCELLED)
        self.assertEqual(successor.status, SubscriptionStatus.ACTIVE)
        self.assertEqual(successor.previous_subscription_id, old_sub.id)
        self.assertEqual(successor.plan_code_snapshot, "pro_plan")

        self.assertTrue(
            AuditLog.objects.filter(
                action=AuditAction.SUBSCRIPTION_PLAN_CHANGED,
                target_id=successor.id,
            ).exists()
        )
        self.assertFalse(
            AuditLog.objects.filter(
                action=AuditAction.SUBSCRIPTION_RECONCILED,
                target_id=successor.id,
            ).exists()
        )

    # 14. Subscription reconciliation writes only subscription snapshots and leaves direct grants untouched
    def test_14_subscription_reconciliation_snapshots_only_and_direct_grants_unchanged(self):
        """Reconciliation writes only subscription snapshots; direct grants (OrganizationProductEntitlement) are never modified."""
        # Create a pre-existing direct grant in DRAFT status
        direct_grant = OrganizationProductEntitlement.objects.create(
            organization=self.org,
            product=self.product,
            status=EntitlementStatus.DRAFT,
            created_by=self.user,
            updated_by=self.user,
        )

        sub = create_active_subscription(
            organization_id=self.org.id,
            plan_version_id=self.plan_version.id,
            plan_price_id=self.plan_price.id,
            actor=self.user,
        )

        # Run snapshot reconciliation directly
        repaired = _reconcile_subscription_snapshots(sub)
        self.assertEqual(repaired, 0)  # already fully populated during creation

        # Verify direct grant is completely untouched (still DRAFT)
        direct_grant.refresh_from_db()
        self.assertEqual(direct_grant.status, EntitlementStatus.DRAFT)
        self.assertEqual(OrganizationProductEntitlement.objects.filter(organization=self.org).count(), 1)

    # 15. No-op manual reconciliation emits no audit event
    def test_15_noop_manual_reconciliation_emits_no_audit(self):
        """Manual reconciliation on fully populated subscription returns 0 and emits no audit log."""
        sub = create_active_subscription(
            organization_id=self.org.id,
            plan_version_id=self.plan_version.id,
            plan_price_id=self.plan_price.id,
            actor=self.user,
        )

        repaired_count = reconcile_subscription_entitlements(
            subscription_id=sub.id,
            actor=self.user,
        )
        self.assertEqual(repaired_count, 0)

        # No SUBSCRIPTION_RECONCILED audit log was emitted
        self.assertFalse(
            AuditLog.objects.filter(
                action=AuditAction.SUBSCRIPTION_RECONCILED,
                target_id=sub.id,
            ).exists()
        )

    # 16. Material repair emits exactly one reconciliation audit
    def test_16_material_repair_emits_exactly_one_reconciliation_audit(self):
        """Reconciliation that repairs missing snapshots emits exactly one SUBSCRIPTION_RECONCILED audit."""
        sub = create_active_subscription(
            organization_id=self.org.id,
            plan_version_id=self.plan_version.id,
            plan_price_id=self.plan_price.id,
            actor=self.user,
        )

        # Simulate missing product snapshot by deleting it via raw DB connection
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute(
                "DELETE FROM subscription_product_entitlements WHERE subscription_id = %s",
                [str(sub.id)],
            )

        self.assertEqual(sub.product_entitlements.count(), 0)

        repaired_count = reconcile_subscription_entitlements(
            subscription_id=sub.id,
            actor=self.user,
        )
        self.assertEqual(repaired_count, 1)
        self.assertEqual(sub.product_entitlements.count(), 1)

        # Exactly one reconciliation audit event emitted
        reconcile_logs = AuditLog.objects.filter(
            action=AuditAction.SUBSCRIPTION_RECONCILED,
            target_id=sub.id,
        )
        self.assertEqual(reconcile_logs.count(), 1)
        self.assertEqual(reconcile_logs.first().metadata["repaired_count"], 1)

    # 17. Effective access helpers (read-only direct grants fallback)
    def test_17_effective_access_helpers(self):
        """Access helpers check subscription entitlements and fallback to direct grants without modifying them."""
        sub = create_active_subscription(
            organization_id=self.org.id,
            plan_version_id=self.plan_version.id,
            plan_price_id=self.plan_price.id,
            actor=self.user,
        )
        self.assertTrue(has_product_access(self.org.id, "lms_core"))
        self.assertTrue(has_module_access(self.org.id, "lms_core", "assessments"))
        self.assertTrue(has_capability_access(self.org.id, "auto_grading"))
        self.assertFalse(has_product_access(self.org.id, "non_existent"))

        # Suspend subscription -> subscription access is paused
        suspend_subscription(subscription_id=sub.id, actor=self.user, reason="Test")
        self.assertFalse(has_product_access(self.org.id, "lms_core"))

        # Add an active direct grant -> direct grant provides read-only fallback access
        OrganizationProductEntitlement.objects.create(
            organization=self.org,
            product=self.product,
            status=EntitlementStatus.ACTIVE,
            created_by=self.user,
            updated_by=self.user,
        )
        self.assertTrue(has_product_access(self.org.id, "lms_core"))

    # 18. Scoped quota retrieval helper
    def test_18_effective_quota_helpers(self):
        """get_effective_quota retrieves plan-scoped and target-scoped quotas."""
        create_active_subscription(
            organization_id=self.org.id,
            plan_version_id=self.plan_version.id,
            plan_price_id=self.plan_price.id,
            actor=self.user,
        )
        quota_ent = get_effective_quota(self.org.id, "max_users", scope="plan")
        self.assertIsNotNone(quota_ent)
        self.assertEqual(quota_ent.limit_value, 100)
        self.assertEqual(quota_ent.unit, "users")

        non_existent = get_effective_quota(self.org.id, "storage_gb", scope="plan")
        self.assertIsNone(non_existent)

    # 19. Idempotent expire_trial_subscriptions batch service and management command
    def test_19_expire_trial_subscriptions_and_command(self):
        """expire_trial_subscriptions service and expire_trials command expire overdue trials."""
        sub = start_subscription_trial(
            organization_id=self.org.id,
            plan_version_id=self.plan_version.id,
            plan_price_id=self.plan_price.id,
            actor=self.user,
        )
        # Fast-forward trial into the past via DB cursor (preserving trial_ends_at > trial_started_at)
        past_end = timezone.now() - timezone.timedelta(days=1)
        past_start = past_end - timezone.timedelta(days=14)
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE organization_subscriptions SET trial_started_at = %s, trial_ends_at = %s WHERE id = %s",
                [past_start, past_end, str(sub.id)],
            )

        expired_count = expire_trial_subscriptions()
        self.assertEqual(expired_count, 1)

        sub.refresh_from_db()
        self.assertEqual(sub.status, SubscriptionStatus.EXPIRED)
        self.assertIsNotNone(sub.ended_at)

        # Calling again is idempotent (0 expired)
        self.assertEqual(expire_trial_subscriptions(), 0)

        # Calling management command runs cleanly
        call_command("expire_trials")

    # 20. Atomic organization retirement calls cancel_open_subscriptions_for_organization
    def test_20_organization_retirement_calls_cancel_open_subscriptions(self):
        """Retiring an organization calls cancel_open_subscriptions_for_organization and cancels open subscriptions."""
        sub = create_active_subscription(
            organization_id=self.org.id,
            plan_version_id=self.plan_version.id,
            plan_price_id=self.plan_price.id,
            actor=self.user,
        )

        # Retire organization via OrganizationViewSet API
        factory = APIRequestFactory()
        request = factory.patch(
            f"/api/v1/organizations/{self.org.id}/",
            {"status": "retired"},
            format="json",
        )
        request.user = self.user
        view = OrganizationViewSet.as_view({"patch": "partial_update"})
        response = view(request, pk=str(self.org.id))

        self.assertEqual(response.status_code, 200)
        sub.refresh_from_db()
        self.assertEqual(sub.status, SubscriptionStatus.CANCELLED)
        self.assertEqual(sub.cancellation_reason, "Organization retired")

        self.assertTrue(
            AuditLog.objects.filter(
                action=AuditAction.SUBSCRIPTION_CANCELLED,
                target_id=sub.id,
            ).exists()
        )
