"""Phase 2F Part B focused test suite: Seat Engine and Access Eligibility.

Tests 13–32 and 81–86 (26 tests total):
- 13–17: Status-aware temporal subscription boundaries (trial and paid, active vs boundary expiration, suspended/cancelled/expired).
- 18: Multiple active subscriptions fail closed.
- 19: Direct grant cannot allocate seats or grant product access.
- 20–22: Quota precedence (product-scoped over plan-shared) and mixed-pool usage isolation.
- 23: Unrelated quota keys ignored.
- 24: Quota ambiguity/duplicates fail closed.
- 25: Unsupported limit types fail closed.
- 26: Decimal normalization (integral accepted, non-integral rejected).
- 27: Negative and fractional limits rejected.
- 28: Soft quotas fail closed.
- 29: Missing quota resolves to SEAT_QUOTA_UNCONFIGURED.
- 30: Unlimited quota resolution.
- 31–32: Suspended and revoked seat counting.
- 81–82: Product catalog inactive/retired and restoration.
- 83–84: Module catalog inactive/retired and restoration.
- 85: Module snapshot omission and restoration.
- 86: Subscription suspension and restoration.
"""

from datetime import timedelta
from decimal import Decimal
from unittest import mock
import uuid

from django.contrib.auth import get_user_model
from django.test import TransactionTestCase
from django.utils import timezone

from apps.assignments.models import AssignmentStatus, UserModuleAssignment, UserProductAssignment
from apps.assignments.services.eligibility import evaluate_user_product_access
from apps.assignments.services.exceptions import (
    InvalidSeatQuotaConfigError,
    MultipleActiveSubscriptionsError,
    ProductNotEntitledError,
    SeatQuotaUnconfiguredError,
)
from apps.assignments.services.seat_engine import (
    get_temporally_eligible_subscription,
    normalize_seat_limit,
    resolve_seat_pool,
)
from apps.entitlements.models import EntitlementStatus, OrganizationProductEntitlement
from apps.organizations.models import MembershipStatus, Organization, OrganizationMembership, OrganizationStatus
from apps.plans.models import (
    BillingInterval,
    Plan,
    PlanCurrency,
    PlanPrice,
    PlanProduct,
    PlanModule,
    PlanQuota,
    PlanVersion,
    PlanVersionStatus,
    QuotaLimitType,
    QuotaResetPeriod,
    QuotaScope,
)
from apps.product_registry.models import CatalogStatus, Product, ProductModule, ProductStatus
from apps.subscriptions.models import (
    OrganizationSubscription,
    SubscriptionModuleEntitlement,
    SubscriptionProductEntitlement,
    SubscriptionQuotaEntitlement,
    SubscriptionStatus,
)

PlatformUser = get_user_model()


class SeatEngineAndEligibilityTests(TransactionTestCase):
    """Part B automated test suite covering pure seat engine and access eligibility."""

    def setUp(self):
        super().setUp()
        self.actor = PlatformUser.objects.create(
            email=f"owner_{uuid.uuid4().hex[:6]}@example.com",
            full_name="Platform Owner",
            status="active",
            is_active=True,
            is_platform_owner=True,
        )
        self.org = Organization.objects.create(
            code=f"org-{uuid.uuid4().hex[:6]}",
            name="Test Organization",
            status=OrganizationStatus.ACTIVE,
            created_by=self.actor,
            updated_by=self.actor,
        )
        self.user_1 = PlatformUser.objects.create(
            email=f"user1_{uuid.uuid4().hex[:6]}@example.com",
            full_name="User One",
            status="active",
            is_active=True,
        )
        self.membership_1 = OrganizationMembership.objects.create(
            organization=self.org,
            user=self.user_1,
            membership_type="member",
            status=MembershipStatus.ACTIVE,
            joined_at=timezone.now(),
        )
        self.product_1 = Product.objects.create(
            code=f"prod1_{uuid.uuid4().hex[:6]}",
            name="Product One",
            status=ProductStatus.ACTIVE,
            created_by=self.actor,
            updated_by=self.actor,
        )
        self.product_2 = Product.objects.create(
            code=f"prod2_{uuid.uuid4().hex[:6]}",
            name="Product Two",
            status=ProductStatus.ACTIVE,
            created_by=self.actor,
            updated_by=self.actor,
        )
        self.module_1 = ProductModule.objects.create(
            product=self.product_1,
            code="mod1",
            name="Module One",
            status=CatalogStatus.ACTIVE,
            created_by=self.actor,
            updated_by=self.actor,
        )
        self.module_2 = ProductModule.objects.create(
            product=self.product_1,
            code="mod2",
            name="Module Two",
            status=CatalogStatus.ACTIVE,
            created_by=self.actor,
            updated_by=self.actor,
        )

        # Plan hierarchy
        self.plan = Plan.objects.create(
            code=f"plan_{uuid.uuid4().hex[:6]}",
            name="Test Plan",
            is_public=True,
            created_by=self.actor,
            updated_by=self.actor,
        )
        self.plan_version = PlanVersion.objects.create(
            plan=self.plan,
            version=1,
            status=PlanVersionStatus.ACTIVE,
            activated_at=timezone.now(),
            created_by=self.actor,
            updated_by=self.actor,
        )
        self.plan_price = PlanPrice.objects.create(
            plan_version=self.plan_version,
            currency=PlanCurrency.USD,
            billing_interval=BillingInterval.MONTHLY,
            amount=Decimal("100.00"),
            created_by=self.actor,
            updated_by=self.actor,
        )
        self.plan_prod_1 = PlanProduct.objects.create(
            plan_version=self.plan_version,
            product=self.product_1,
            created_by=self.actor,
        )
        self.plan_prod_2 = PlanProduct.objects.create(
            plan_version=self.plan_version,
            product=self.product_2,
            created_by=self.actor,
        )
        self.plan_mod_1 = PlanModule.objects.create(
            plan_version=self.plan_version,
            plan_product=self.plan_prod_1,
            module=self.module_1,
            created_by=self.actor,
        )
        self.plan_mod_2 = PlanModule.objects.create(
            plan_version=self.plan_version,
            plan_product=self.plan_prod_1,
            module=self.module_2,
            created_by=self.actor,
        )
        self.plan_quota = PlanQuota.objects.create(
            plan_version=self.plan_version,
            quota_key="seats",
            name="Seats",
            scope=QuotaScope.PLAN,
            limit_type=QuotaLimitType.NUMERIC,
            limit_value=10,
            unit="seats",
            reset_period=QuotaResetPeriod.MONTHLY,
            created_by=self.actor,
            updated_by=self.actor,
        )

    def _create_subscription(
        self,
        organization=None,
        status=SubscriptionStatus.ACTIVE,
        started_as_trial=False,
        trial_started_at=None,
        trial_ends_at=None,
        current_period_start=None,
        current_period_end=None,
        cancelled_at=None,
        ended_at=None,
        include_modules=True,
    ):
        org = organization or self.org
        now = timezone.now()
        if status == SubscriptionStatus.ACTIVE and current_period_start is None:
            current_period_start = now - timedelta(days=5)
            current_period_end = now + timedelta(days=25)
        elif status == SubscriptionStatus.TRIALING and trial_started_at is None:
            started_as_trial = True
            trial_started_at = now - timedelta(days=3)
            trial_ends_at = now + timedelta(days=11)
        elif status == SubscriptionStatus.SUSPENDED and current_period_start is None:
            current_period_start = now - timedelta(days=5)
            current_period_end = now + timedelta(days=25)
        elif status == SubscriptionStatus.CANCELLED:
            if current_period_start is None:
                current_period_start = now - timedelta(days=5)
                current_period_end = now + timedelta(days=25)
            if cancelled_at is None:
                cancelled_at = now
            if ended_at is None:
                ended_at = now
        elif status == SubscriptionStatus.EXPIRED:
            started_as_trial = True
            if trial_started_at is None:
                trial_started_at = now - timedelta(days=10)
                trial_ends_at = now - timedelta(days=1)
            if ended_at is None:
                ended_at = now

        sub = OrganizationSubscription.objects.create(
            organization=org,
            plan_version=self.plan_version,
            plan_price=self.plan_price,
            plan_code_snapshot=self.plan.code,
            plan_name_snapshot=self.plan.name,
            version_number_snapshot=self.plan_version.version,
            billing_interval=self.plan_price.billing_interval,
            currency=self.plan_price.currency,
            amount=self.plan_price.amount,
            started_as_trial=started_as_trial,
            trial_started_at=trial_started_at,
            trial_ends_at=trial_ends_at,
            status=status,
            current_period_start=current_period_start,
            current_period_end=current_period_end,
            cancelled_at=cancelled_at,
            ended_at=ended_at,
            created_by=self.actor,
            updated_by=self.actor,
        )
        # Snapshot product entitlements
        SubscriptionProductEntitlement.objects.create(
            subscription=sub,
            organization=org,
            product=self.product_1,
            plan_product=self.plan_prod_1,
            product_code_snapshot=self.product_1.code,
            product_name_snapshot=self.product_1.name,
        )
        SubscriptionProductEntitlement.objects.create(
            subscription=sub,
            organization=org,
            product=self.product_2,
            plan_product=self.plan_prod_2,
            product_code_snapshot=self.product_2.code,
            product_name_snapshot=self.product_2.name,
        )
        if include_modules:
            # Snapshot module entitlements
            SubscriptionModuleEntitlement.objects.create(
                subscription=sub,
                organization=org,
                module=self.module_1,
                plan_module=self.plan_mod_1,
                module_code_snapshot=self.module_1.code,
                module_name_snapshot=self.module_1.name,
            )
            SubscriptionModuleEntitlement.objects.create(
                subscription=sub,
                organization=org,
                module=self.module_2,
                plan_module=self.plan_mod_2,
                module_code_snapshot=self.module_2.code,
                module_name_snapshot=self.module_2.name,
            )
        return sub

    # -------------------------------------------------------------------------
    # Tests 13–17: Temporal Subscription Boundaries
    # -------------------------------------------------------------------------
    def test_13_temporal_trial_active(self):
        """Subscription is eligible when trial_started_at <= at_time < trial_ends_at."""
        now = timezone.now()
        sub = self._create_subscription(
            status=SubscriptionStatus.TRIALING,
            started_as_trial=True,
            trial_started_at=now - timedelta(days=2),
            trial_ends_at=now + timedelta(days=5),
        )
        resolved = get_temporally_eligible_subscription(self.org.id, at_time=now)
        self.assertIsNotNone(resolved)
        self.assertEqual(resolved.id, sub.id)

    def test_14_temporal_trial_boundary_expiration(self):
        """Subscription is ineligible when at_time == trial_ends_at or after."""
        now = timezone.now()
        ends_at = now + timedelta(days=5)
        self._create_subscription(
            status=SubscriptionStatus.TRIALING,
            started_as_trial=True,
            trial_started_at=now - timedelta(days=2),
            trial_ends_at=ends_at,
        )
        # Exactly on the upper boundary -> ineligible
        self.assertIsNone(get_temporally_eligible_subscription(self.org.id, at_time=ends_at))
        # After boundary -> ineligible
        self.assertIsNone(get_temporally_eligible_subscription(self.org.id, at_time=ends_at + timedelta(seconds=1)))
        # Before start -> ineligible
        before_start = now - timedelta(days=3)
        self.assertIsNone(get_temporally_eligible_subscription(self.org.id, at_time=before_start))

    def test_15_temporal_paid_active(self):
        """Subscription is eligible when current_period_start <= at_time < current_period_end."""
        now = timezone.now()
        sub = self._create_subscription(
            status=SubscriptionStatus.ACTIVE,
            current_period_start=now - timedelta(days=1),
            current_period_end=now + timedelta(days=29),
        )
        resolved = get_temporally_eligible_subscription(self.org.id, at_time=now)
        self.assertIsNotNone(resolved)
        self.assertEqual(resolved.id, sub.id)

    def test_16_temporal_paid_boundary_expiration(self):
        """Subscription is ineligible when at_time == current_period_end or after."""
        now = timezone.now()
        period_end = now + timedelta(days=20)
        self._create_subscription(
            status=SubscriptionStatus.ACTIVE,
            current_period_start=now - timedelta(days=10),
            current_period_end=period_end,
        )
        # Exactly on upper boundary -> ineligible
        self.assertIsNone(get_temporally_eligible_subscription(self.org.id, at_time=period_end))
        # After boundary -> ineligible
        self.assertIsNone(get_temporally_eligible_subscription(self.org.id, at_time=period_end + timedelta(seconds=1)))

    def test_17_temporal_suspended_cancelled_expired(self):
        """Subscriptions with suspended, cancelled, or expired status are ineligible."""
        now = timezone.now()
        # 1. Suspended
        org_susp = Organization.objects.create(
            code=f"susp-{uuid.uuid4().hex[:6]}",
            name="Susp Org",
            status=OrganizationStatus.ACTIVE,
            created_by=self.actor,
            updated_by=self.actor,
        )
        self._create_subscription(
            organization=org_susp,
            status=SubscriptionStatus.SUSPENDED,
            current_period_start=now - timedelta(days=5),
            current_period_end=now + timedelta(days=25),
        )
        self.assertIsNone(get_temporally_eligible_subscription(org_susp.id, at_time=now))

        # 2. Cancelled
        org_canc = Organization.objects.create(
            code=f"canc-{uuid.uuid4().hex[:6]}",
            name="Canc Org",
            status=OrganizationStatus.ACTIVE,
            created_by=self.actor,
            updated_by=self.actor,
        )
        self._create_subscription(
            organization=org_canc,
            status=SubscriptionStatus.CANCELLED,
            current_period_start=now - timedelta(days=5),
            current_period_end=now + timedelta(days=25),
        )
        self.assertIsNone(get_temporally_eligible_subscription(org_canc.id, at_time=now))

        # 3. Expired
        org_exp = Organization.objects.create(
            code=f"exp-{uuid.uuid4().hex[:6]}",
            name="Exp Org",
            status=OrganizationStatus.ACTIVE,
            created_by=self.actor,
            updated_by=self.actor,
        )
        self._create_subscription(
            organization=org_exp,
            status=SubscriptionStatus.EXPIRED,
            started_as_trial=True,
            trial_started_at=now - timedelta(days=10),
            trial_ends_at=now - timedelta(days=1),
        )
        self.assertIsNone(get_temporally_eligible_subscription(org_exp.id, at_time=now))

    # -------------------------------------------------------------------------
    # Test 18: Multiple Active Subscriptions Fail Closed
    # -------------------------------------------------------------------------
    def test_18_multiple_eligible_subscriptions_fail_closed(self):
        """Corrupt data exposing multiple eligible subscriptions raises MultipleActiveSubscriptionsError."""
        now = timezone.now()
        org_multi = Organization.objects.create(
            code=f"multi-{uuid.uuid4().hex[:6]}",
            name="Multi Sub Org",
            status=OrganizationStatus.ACTIVE,
            created_by=self.actor,
            updated_by=self.actor,
        )

        sub_1 = OrganizationSubscription(
            id=uuid.uuid4(),
            organization=org_multi,
            plan_version=self.plan_version,
            plan_price=self.plan_price,
            plan_code_snapshot="plan1",
            plan_name_snapshot="Plan 1",
            version_number_snapshot=1,
            billing_interval=BillingInterval.MONTHLY,
            currency=PlanCurrency.USD,
            amount=Decimal("100.00"),
            status=SubscriptionStatus.ACTIVE,
            current_period_start=now - timedelta(days=5),
            current_period_end=now + timedelta(days=25),
            created_by=self.actor,
            updated_by=self.actor,
        )

        sub_2 = OrganizationSubscription(
            id=uuid.uuid4(),
            organization=org_multi,
            plan_version=self.plan_version,
            plan_price=self.plan_price,
            plan_code_snapshot="plan2",
            plan_name_snapshot="Plan 2",
            version_number_snapshot=1,
            billing_interval=BillingInterval.MONTHLY,
            currency=PlanCurrency.USD,
            amount=Decimal("100.00"),
            status=SubscriptionStatus.ACTIVE,
            current_period_start=now - timedelta(days=5),
            current_period_end=now + timedelta(days=25),
            created_by=self.actor,
            updated_by=self.actor,
        )

        # Mock the queryset return to simulate corrupt data having multiple eligible subscriptions
        with mock.patch("apps.assignments.services.seat_engine.OrganizationSubscription.objects.filter") as mock_filter:
            mock_filter.return_value = [sub_1, sub_2]
            with self.assertRaises(MultipleActiveSubscriptionsError):
                get_temporally_eligible_subscription(org_multi.id, at_time=now)

    # -------------------------------------------------------------------------
    # Test 19: Direct Grant Cannot Allocate Seat
    # -------------------------------------------------------------------------
    def test_19_direct_grant_cannot_allocate_seat(self):
        """Direct OrganizationProductEntitlement grants do not authorize seat allocation."""
        now = timezone.now()
        sub = self._create_subscription(status=SubscriptionStatus.ACTIVE)

        # Third product NOT in subscription snapshot
        product_unentitled = Product.objects.create(
            code=f"unentitled_{uuid.uuid4().hex[:6]}",
            name="Unentitled Product",
            status=ProductStatus.ACTIVE,
            created_by=self.actor,
            updated_by=self.actor,
        )

        # Create direct grant
        OrganizationProductEntitlement.objects.create(
            organization=self.org,
            product=product_unentitled,
            status=EntitlementStatus.ACTIVE,
            created_by=self.actor,
            updated_by=self.actor,
        )

        # resolve_seat_pool must reject product not in subscription
        with self.assertRaises(ProductNotEntitledError):
            resolve_seat_pool(
                organization_id=self.org.id,
                product_id=product_unentitled.id,
                subscription=sub,
            )

        # evaluate_user_product_access must deny access
        result = evaluate_user_product_access(
            organization_id=self.org.id,
            user_id=self.user_1.id,
            product_id=product_unentitled.id,
            at_time=now,
        )
        self.assertFalse(result.has_access)
        self.assertEqual(result.denial_code, "PRODUCT_NOT_ENTITLED")

    # -------------------------------------------------------------------------
    # Tests 20–22: Quota Precedence and Mixed-Pool Isolation
    # -------------------------------------------------------------------------
    def test_20_product_scoped_precedence(self):
        """Product-specific quota takes precedence over plan-shared quota."""
        sub = self._create_subscription(status=SubscriptionStatus.ACTIVE)

        # Plan-wide quota: 20 seats
        SubscriptionQuotaEntitlement.objects.create(
            subscription=sub,
            organization=self.org,
            plan_quota=self.plan_quota,
            quota_key="seats",
            name="Plan Seats",
            scope=QuotaScope.PLAN,
            product=None,
            limit_type=QuotaLimitType.NUMERIC,
            limit_value=20,
            unit="seats",
            is_hard_limit=True,
            reset_period=QuotaResetPeriod.MONTHLY,
        )

        # Product-scoped quota for product_1: 5 seats
        quota_prod = SubscriptionQuotaEntitlement.objects.create(
            subscription=sub,
            organization=self.org,
            plan_quota=self.plan_quota,
            quota_key="seats",
            name="Product 1 Seats",
            scope=QuotaScope.PRODUCT,
            product=self.product_1,
            limit_type=QuotaLimitType.NUMERIC,
            limit_value=5,
            unit="seats",
            is_hard_limit=True,
            reset_period=QuotaResetPeriod.MONTHLY,
        )

        resolution = resolve_seat_pool(
            organization_id=self.org.id,
            product_id=self.product_1.id,
            subscription=sub,
        )
        self.assertEqual(resolution.subscription_id, sub.id)
        self.assertEqual(resolution.quota_entitlement_id, quota_prod.id)
        self.assertEqual(resolution.pool_scope, "product")
        self.assertEqual(resolution.pool_key, f"product:{self.product_1.id}")
        self.assertEqual(resolution.quota_key, "seats")
        self.assertEqual(resolution.limit_type, "numeric")
        self.assertEqual(resolution.total_limit, 5)
        self.assertEqual(resolution.consumed_seats, 0)
        self.assertEqual(resolution.available_seats, 5)
        self.assertTrue(resolution.is_capacity_available)
        self.assertEqual(resolution.over_allocated_amount, 0)
        self.assertEqual(resolution.governed_product_ids, [self.product_1.id])

    def test_21_plan_shared_fallback(self):
        """Plan-shared quota is used when no product-specific quota exists."""
        sub = self._create_subscription(status=SubscriptionStatus.ACTIVE)

        # Plan-wide quota: 15 seats
        quota_plan = SubscriptionQuotaEntitlement.objects.create(
            subscription=sub,
            organization=self.org,
            plan_quota=self.plan_quota,
            quota_key="seats",
            name="Plan Seats",
            scope=QuotaScope.PLAN,
            product=None,
            limit_type=QuotaLimitType.NUMERIC,
            limit_value=15,
            unit="seats",
            is_hard_limit=True,
            reset_period=QuotaResetPeriod.MONTHLY,
        )

        # product_2 has no product-specific quota
        resolution = resolve_seat_pool(
            organization_id=self.org.id,
            product_id=self.product_2.id,
            subscription=sub,
        )
        self.assertEqual(resolution.subscription_id, sub.id)
        self.assertEqual(resolution.quota_entitlement_id, quota_plan.id)
        self.assertEqual(resolution.pool_scope, "plan")
        self.assertEqual(resolution.pool_key, f"plan:{sub.plan_code_snapshot}")
        self.assertEqual(resolution.quota_key, "seats")
        self.assertEqual(resolution.limit_type, "numeric")
        self.assertEqual(resolution.total_limit, 15)
        self.assertEqual(resolution.consumed_seats, 0)
        self.assertEqual(resolution.available_seats, 15)
        self.assertTrue(resolution.is_capacity_available)
        self.assertEqual(resolution.over_allocated_amount, 0)
        self.assertEqual(
            resolution.governed_product_ids,
            sorted([self.product_1.id, self.product_2.id]),
        )

    def test_22_mixed_pool_isolation(self):
        """Product-specific pool assignments do not consume plan-shared pool capacity."""
        sub = self._create_subscription(status=SubscriptionStatus.ACTIVE)

        # Product 1 specific: 5 seats
        SubscriptionQuotaEntitlement.objects.create(
            subscription=sub,
            organization=self.org,
            plan_quota=self.plan_quota,
            quota_key="seats",
            name="Product 1 Seats",
            scope=QuotaScope.PRODUCT,
            product=self.product_1,
            limit_type=QuotaLimitType.NUMERIC,
            limit_value=5,
            unit="seats",
            is_hard_limit=True,
            reset_period=QuotaResetPeriod.MONTHLY,
        )

        # Plan-wide shared: 10 seats
        SubscriptionQuotaEntitlement.objects.create(
            subscription=sub,
            organization=self.org,
            plan_quota=self.plan_quota,
            quota_key="seats",
            name="Plan Shared Seats",
            scope=QuotaScope.PLAN,
            product=None,
            limit_type=QuotaLimitType.NUMERIC,
            limit_value=10,
            unit="seats",
            is_hard_limit=True,
            reset_period=QuotaResetPeriod.MONTHLY,
        )

        # 2 assignments to Product 1
        UserProductAssignment.objects.create(
            organization=self.org,
            user=self.user_1,
            membership=self.membership_1,
            product=self.product_1,
            status=AssignmentStatus.ACTIVE,
            created_by=self.actor,
            updated_by=self.actor,
        )

        user_2 = PlatformUser.objects.create(
            email=f"user2_{uuid.uuid4().hex[:6]}@example.com",
            full_name="User Two",
            status="active",
            is_active=True,
        )
        membership_2 = OrganizationMembership.objects.create(
            organization=self.org,
            user=user_2,
            membership_type="member",
            status=MembershipStatus.ACTIVE,
            joined_at=timezone.now(),
        )
        UserProductAssignment.objects.create(
            organization=self.org,
            user=user_2,
            membership=membership_2,
            product=self.product_1,
            status=AssignmentStatus.ACTIVE,
            created_by=self.actor,
            updated_by=self.actor,
        )

        # 1 assignment to Product 2 (which uses plan-shared pool)
        UserProductAssignment.objects.create(
            organization=self.org,
            user=self.user_1,
            membership=self.membership_1,
            product=self.product_2,
            status=AssignmentStatus.ACTIVE,
            created_by=self.actor,
            updated_by=self.actor,
        )

        # Check Product 1 resolution: 2 consumed out of 5, available = 3
        res_prod1 = resolve_seat_pool(organization_id=self.org.id, product_id=self.product_1.id, subscription=sub)
        self.assertEqual(res_prod1.consumed_seats, 2)
        self.assertEqual(res_prod1.available_seats, 3)

        # Check Product 2 resolution: 1 consumed out of 10, available = 9
        res_prod2 = resolve_seat_pool(organization_id=self.org.id, product_id=self.product_2.id, subscription=sub)
        self.assertEqual(res_prod2.consumed_seats, 1)
        self.assertEqual(res_prod2.available_seats, 9)

    # -------------------------------------------------------------------------
    # Tests 23–25: Quota Key & Type Validation
    # -------------------------------------------------------------------------
    def test_23_unrelated_quota_keys_ignored(self):
        """Unrelated quota keys (storage_gb, api_calls) are ignored by seat engine."""
        sub = self._create_subscription(status=SubscriptionStatus.ACTIVE)

        # Unrelated quotas
        SubscriptionQuotaEntitlement.objects.create(
            subscription=sub,
            organization=self.org,
            plan_quota=self.plan_quota,
            quota_key="storage_gb",
            name="Storage",
            scope=QuotaScope.PLAN,
            limit_type=QuotaLimitType.NUMERIC,
            limit_value=500,
            unit="gb",
            is_hard_limit=True,
            reset_period=QuotaResetPeriod.MONTHLY,
        )

        # Seat quota
        SubscriptionQuotaEntitlement.objects.create(
            subscription=sub,
            organization=self.org,
            plan_quota=self.plan_quota,
            quota_key="seats",
            name="Plan Seats",
            scope=QuotaScope.PLAN,
            limit_type=QuotaLimitType.NUMERIC,
            limit_value=8,
            unit="seats",
            is_hard_limit=True,
            reset_period=QuotaResetPeriod.MONTHLY,
        )

        resolution = resolve_seat_pool(organization_id=self.org.id, product_id=self.product_1.id, subscription=sub)
        self.assertEqual(resolution.total_limit, 8)
        self.assertEqual(resolution.quota_key, "seats")

    def test_24_quota_ambiguity_duplicate_rejection(self):
        """Duplicate or ambiguous seat quotas at same scope fail closed."""
        sub = self._create_subscription(status=SubscriptionStatus.ACTIVE)

        # Both seats and max_seats defined at plan scope
        SubscriptionQuotaEntitlement.objects.create(
            subscription=sub,
            organization=self.org,
            plan_quota=self.plan_quota,
            quota_key="seats",
            name="Seats",
            scope=QuotaScope.PLAN,
            limit_type=QuotaLimitType.NUMERIC,
            limit_value=10,
            unit="seats",
            is_hard_limit=True,
            reset_period=QuotaResetPeriod.MONTHLY,
        )
        SubscriptionQuotaEntitlement.objects.create(
            subscription=sub,
            organization=self.org,
            plan_quota=self.plan_quota,
            quota_key="max_seats",
            name="Max Seats",
            scope=QuotaScope.PLAN,
            limit_type=QuotaLimitType.NUMERIC,
            limit_value=12,
            unit="seats",
            is_hard_limit=True,
            reset_period=QuotaResetPeriod.MONTHLY,
        )

        with self.assertRaises(InvalidSeatQuotaConfigError) as ctx:
            resolve_seat_pool(organization_id=self.org.id, product_id=self.product_1.id, subscription=sub)
        self.assertIn("Duplicate or ambiguous", str(ctx.exception))

    def test_25_unsupported_seat_limit_type_fail_closed(self):
        """Seat quota with unsupported limit_type fails closed."""
        with self.assertRaises(InvalidSeatQuotaConfigError):
            normalize_seat_limit(limit_type="metered", limit_value=10, is_hard_limit=True)

        with self.assertRaises(InvalidSeatQuotaConfigError):
            normalize_seat_limit(limit_type="tiered", limit_value=10, is_hard_limit=True)

    # -------------------------------------------------------------------------
    # Tests 26–30: Quota Normalization Edge Cases
    # -------------------------------------------------------------------------
    def test_26_quota_normalization_decimal_handling(self):
        """Integral Decimal accepted as integer; non-integral Decimal rejected."""
        # Decimal("10.0") accepted as 10
        self.assertEqual(normalize_seat_limit(limit_type="numeric", limit_value=Decimal("10.0"), is_hard_limit=True), 10)
        self.assertEqual(normalize_seat_limit(limit_type="numeric", limit_value=Decimal("10.00"), is_hard_limit=True), 10)

        # Decimal("10.5") rejected
        with self.assertRaises(InvalidSeatQuotaConfigError):
            normalize_seat_limit(limit_type="numeric", limit_value=Decimal("10.5"), is_hard_limit=True)

    def test_27_invalid_quota_negative_and_fractional(self):
        """Negative and fractional seat limits fail closed without truncation."""
        with self.assertRaises(InvalidSeatQuotaConfigError):
            normalize_seat_limit(limit_type="numeric", limit_value=-5, is_hard_limit=True)

        with self.assertRaises(InvalidSeatQuotaConfigError):
            normalize_seat_limit(limit_type="numeric", limit_value=5.5, is_hard_limit=True)

        with self.assertRaises(InvalidSeatQuotaConfigError):
            normalize_seat_limit(limit_type="numeric", limit_value="5.5", is_hard_limit=True)

    def test_28_soft_quota_fail_closed(self):
        """Soft seat quotas (is_hard_limit=False) fail closed in Phase 2F."""
        with self.assertRaises(InvalidSeatQuotaConfigError):
            normalize_seat_limit(limit_type="numeric", limit_value=10, is_hard_limit=False)

        with self.assertRaises(InvalidSeatQuotaConfigError):
            normalize_seat_limit(limit_type="unlimited", limit_value=None, is_hard_limit=False)

    def test_29_missing_quota_unconfigured(self):
        """Missing seat quota raises SeatQuotaUnconfiguredError."""
        sub = self._create_subscription(status=SubscriptionStatus.ACTIVE)
        # Zero quotas created on sub
        with self.assertRaises(SeatQuotaUnconfiguredError):
            resolve_seat_pool(organization_id=self.org.id, product_id=self.product_1.id, subscription=sub)

    def test_30_unlimited_pool_resolution(self):
        """Unlimited quota returns total_limit=None and available_seats=None."""
        sub = self._create_subscription(status=SubscriptionStatus.ACTIVE)
        quota_unl = SubscriptionQuotaEntitlement.objects.create(
            subscription=sub,
            organization=self.org,
            plan_quota=self.plan_quota,
            quota_key="seats",
            name="Unlimited Seats",
            scope=QuotaScope.PLAN,
            limit_type=QuotaLimitType.UNLIMITED,
            limit_value=None,
            unit="seats",
            is_hard_limit=True,
            reset_period=QuotaResetPeriod.MONTHLY,
        )
        resolution = resolve_seat_pool(organization_id=self.org.id, product_id=self.product_1.id, subscription=sub)
        self.assertEqual(resolution.subscription_id, sub.id)
        self.assertEqual(resolution.quota_entitlement_id, quota_unl.id)
        self.assertEqual(resolution.limit_type, "unlimited")
        self.assertIsNone(resolution.total_limit)
        self.assertIsNone(resolution.available_seats)
        self.assertTrue(resolution.is_capacity_available)
        self.assertEqual(resolution.over_allocated_amount, 0)

    # -------------------------------------------------------------------------
    # Tests 31–32: Suspended and Revoked Seat Counting
    # -------------------------------------------------------------------------
    def test_31_suspended_seat_counting(self):
        """Suspended assignments count toward consumed seats and reserve capacity."""
        sub = self._create_subscription(status=SubscriptionStatus.ACTIVE)
        SubscriptionQuotaEntitlement.objects.create(
            subscription=sub,
            organization=self.org,
            plan_quota=self.plan_quota,
            quota_key="seats",
            name="Seats",
            scope=QuotaScope.PLAN,
            limit_type=QuotaLimitType.NUMERIC,
            limit_value=2,
            unit="seats",
            is_hard_limit=True,
            reset_period=QuotaResetPeriod.MONTHLY,
        )

        now = timezone.now()
        # 1 active assignment
        UserProductAssignment.objects.create(
            organization=self.org,
            user=self.user_1,
            membership=self.membership_1,
            product=self.product_1,
            status=AssignmentStatus.ACTIVE,
            created_by=self.actor,
            updated_by=self.actor,
        )

        # 1 suspended assignment
        user_2 = PlatformUser.objects.create(
            email=f"user2_{uuid.uuid4().hex[:6]}@example.com",
            full_name="User Two",
            status="active",
            is_active=True,
        )
        membership_2 = OrganizationMembership.objects.create(
            organization=self.org,
            user=user_2,
            membership_type="member",
            status=MembershipStatus.ACTIVE,
            joined_at=now,
        )
        UserProductAssignment.objects.create(
            organization=self.org,
            user=user_2,
            membership=membership_2,
            product=self.product_1,
            status=AssignmentStatus.SUSPENDED,
            last_suspended_at=now,
            created_by=self.actor,
            updated_by=self.actor,
        )

        # Capacity full: consumed=2, available=0, is_capacity_available=False
        resolution = resolve_seat_pool(organization_id=self.org.id, product_id=self.product_1.id, subscription=sub)
        self.assertEqual(resolution.consumed_seats, 2)
        self.assertEqual(resolution.available_seats, 0)
        self.assertFalse(resolution.is_capacity_available)
        self.assertEqual(resolution.over_allocated_amount, 0)

        # Over-allocation/full capacity: existing active assignment retains access
        access_active = evaluate_user_product_access(
            organization_id=self.org.id,
            user_id=self.user_1.id,
            product_id=self.product_1.id,
            at_time=now,
        )
        self.assertTrue(access_active.has_access)
        self.assertEqual(access_active.assignment_status, "active")

        # Suspended assignment evaluation asserts assignment_status="suspended" and empty module collections
        access_suspended = evaluate_user_product_access(
            organization_id=self.org.id,
            user_id=user_2.id,
            product_id=self.product_1.id,
            at_time=now,
        )
        self.assertFalse(access_suspended.has_access)
        self.assertEqual(access_suspended.denial_code, "ASSIGNMENT_SUSPENDED")
        self.assertEqual(access_suspended.assignment_status, "suspended")
        self.assertEqual(access_suspended.enabled_module_ids, [])
        self.assertEqual(access_suspended.enabled_module_codes, [])

    def test_32_revoked_seat_release(self):
        """Revoked assignments do not count toward consumed seats."""
        sub = self._create_subscription(status=SubscriptionStatus.ACTIVE)
        SubscriptionQuotaEntitlement.objects.create(
            subscription=sub,
            organization=self.org,
            plan_quota=self.plan_quota,
            quota_key="seats",
            name="Seats",
            scope=QuotaScope.PLAN,
            limit_type=QuotaLimitType.NUMERIC,
            limit_value=5,
            unit="seats",
            is_hard_limit=True,
            reset_period=QuotaResetPeriod.MONTHLY,
        )

        now = timezone.now()
        # 1 active
        UserProductAssignment.objects.create(
            organization=self.org,
            user=self.user_1,
            membership=self.membership_1,
            product=self.product_1,
            status=AssignmentStatus.ACTIVE,
            created_by=self.actor,
            updated_by=self.actor,
        )

        # 1 revoked
        user_2 = PlatformUser.objects.create(
            email=f"user2_{uuid.uuid4().hex[:6]}@example.com",
            full_name="User Two",
            status="active",
            is_active=True,
        )
        membership_2 = OrganizationMembership.objects.create(
            organization=self.org,
            user=user_2,
            membership_type="member",
            status=MembershipStatus.ACTIVE,
            joined_at=now,
        )
        UserProductAssignment.objects.create(
            organization=self.org,
            user=user_2,
            membership=membership_2,
            product=self.product_1,
            status=AssignmentStatus.REVOKED,
            revoked_at=now,
            created_by=self.actor,
            updated_by=self.actor,
        )

        resolution = resolve_seat_pool(organization_id=self.org.id, product_id=self.product_1.id, subscription=sub)
        self.assertEqual(resolution.consumed_seats, 1)
        self.assertEqual(resolution.available_seats, 4)

    # -------------------------------------------------------------------------
    # Tests 81–86: Lifecycle and Access Evaluator Dynamics
    # -------------------------------------------------------------------------
    def test_81_product_catalog_inactive_denies_access(self):
        """Inactive or retired product catalog item denies product access."""
        sub = self._create_subscription(status=SubscriptionStatus.ACTIVE)
        assignment = UserProductAssignment.objects.create(
            organization=self.org,
            user=self.user_1,
            membership=self.membership_1,
            product=self.product_1,
            status=AssignmentStatus.ACTIVE,
            created_by=self.actor,
            updated_by=self.actor,
        )

        # Retire product catalog item
        self.product_1.status = ProductStatus.RETIRED
        self.product_1.save(update_fields=["status"])

        result = evaluate_user_product_access(
            organization_id=self.org.id,
            user_id=self.user_1.id,
            product_id=self.product_1.id,
        )
        self.assertFalse(result.has_access)
        self.assertEqual(result.denial_code, "PRODUCT_INACTIVE")
        self.assertIsNone(result.assignment_status)
        self.assertEqual(result.enabled_module_ids, [])
        self.assertEqual(result.enabled_module_codes, [])

    def test_82_product_catalog_restoration_restores_access(self):
        """Restoring product catalog item restores access immediately."""
        sub = self._create_subscription(status=SubscriptionStatus.ACTIVE)
        assignment = UserProductAssignment.objects.create(
            organization=self.org,
            user=self.user_1,
            membership=self.membership_1,
            product=self.product_1,
            status=AssignmentStatus.ACTIVE,
            created_by=self.actor,
            updated_by=self.actor,
        )
        UserModuleAssignment.objects.create(assignment=assignment, module=self.module_1, is_enabled=True)

        # First retired -> denied
        self.product_1.status = ProductStatus.RETIRED
        self.product_1.save(update_fields=["status"])
        denied = evaluate_user_product_access(organization_id=self.org.id, user_id=self.user_1.id, product_id=self.product_1.id)
        self.assertFalse(denied.has_access)
        self.assertEqual(denied.enabled_module_ids, [])
        self.assertEqual(denied.enabled_module_codes, [])

        # Restored -> granted
        self.product_1.status = ProductStatus.ACTIVE
        self.product_1.save(update_fields=["status"])
        result = evaluate_user_product_access(organization_id=self.org.id, user_id=self.user_1.id, product_id=self.product_1.id)
        self.assertTrue(result.has_access)
        self.assertIsNone(result.denial_code)
        self.assertEqual(result.assignment_status, "active")
        self.assertEqual(result.enabled_module_ids, [self.module_1.id])
        self.assertEqual(result.enabled_module_codes, ["mod1"])

    def test_83_module_catalog_inactive_denies_module_access(self):
        """Inactive module catalog item denies that module while preserving product access."""
        sub = self._create_subscription(status=SubscriptionStatus.ACTIVE)
        assignment = UserProductAssignment.objects.create(
            organization=self.org,
            user=self.user_1,
            membership=self.membership_1,
            product=self.product_1,
            status=AssignmentStatus.ACTIVE,
            created_by=self.actor,
            updated_by=self.actor,
        )
        UserModuleAssignment.objects.create(assignment=assignment, module=self.module_1, is_enabled=True)
        UserModuleAssignment.objects.create(assignment=assignment, module=self.module_2, is_enabled=True)

        # Retire module 1
        self.module_1.status = CatalogStatus.RETIRED
        self.module_1.save(update_fields=["status"])

        result = evaluate_user_product_access(
            organization_id=self.org.id,
            user_id=self.user_1.id,
            product_id=self.product_1.id,
        )
        self.assertTrue(result.has_access)
        self.assertEqual(result.assignment_status, "active")
        self.assertNotIn("mod1", result.enabled_module_codes)
        self.assertNotIn(self.module_1.id, result.enabled_module_ids)
        self.assertIn("mod2", result.enabled_module_codes)
        self.assertIn(self.module_2.id, result.enabled_module_ids)

    def test_84_module_catalog_restoration_restores_enabled_module(self):
        """Restoring module catalog item restores enabled module access."""
        sub = self._create_subscription(status=SubscriptionStatus.ACTIVE)
        assignment = UserProductAssignment.objects.create(
            organization=self.org,
            user=self.user_1,
            membership=self.membership_1,
            product=self.product_1,
            status=AssignmentStatus.ACTIVE,
            created_by=self.actor,
            updated_by=self.actor,
        )
        UserModuleAssignment.objects.create(assignment=assignment, module=self.module_1, is_enabled=True)

        # Retire then restore module 1
        self.module_1.status = CatalogStatus.RETIRED
        self.module_1.save(update_fields=["status"])
        denied = evaluate_user_product_access(organization_id=self.org.id, user_id=self.user_1.id, product_id=self.product_1.id)
        self.assertEqual(denied.enabled_module_ids, [])
        self.assertEqual(denied.enabled_module_codes, [])

        self.module_1.status = CatalogStatus.ACTIVE
        self.module_1.save(update_fields=["status"])
        result = evaluate_user_product_access(organization_id=self.org.id, user_id=self.user_1.id, product_id=self.product_1.id)
        self.assertEqual(result.enabled_module_ids, [self.module_1.id])
        self.assertEqual(result.enabled_module_codes, ["mod1"])

    def test_85_module_snapshot_omission_and_restoration(self):
        """Module omitted from plan snapshot denies module access; restoring snapshot restores access."""
        # Create subscription omitting module entitlements from initial snapshot
        sub = self._create_subscription(status=SubscriptionStatus.ACTIVE, include_modules=False)
        assignment = UserProductAssignment.objects.create(
            organization=self.org,
            user=self.user_1,
            membership=self.membership_1,
            product=self.product_1,
            status=AssignmentStatus.ACTIVE,
            created_by=self.actor,
            updated_by=self.actor,
        )
        UserModuleAssignment.objects.create(assignment=assignment, module=self.module_1, is_enabled=True)

        result = evaluate_user_product_access(organization_id=self.org.id, user_id=self.user_1.id, product_id=self.product_1.id)
        self.assertTrue(result.has_access)
        self.assertNotIn("mod1", result.enabled_module_codes)
        self.assertNotIn(self.module_1.id, result.enabled_module_ids)

        # Restore module 1 in subscription snapshot
        SubscriptionModuleEntitlement.objects.create(
            subscription=sub,
            organization=self.org,
            module=self.module_1,
            plan_module=self.plan_mod_1,
            module_code_snapshot=self.module_1.code,
            module_name_snapshot=self.module_1.name,
        )

        result_restored = evaluate_user_product_access(organization_id=self.org.id, user_id=self.user_1.id, product_id=self.product_1.id)
        self.assertIn("mod1", result_restored.enabled_module_codes)
        self.assertIn(self.module_1.id, result_restored.enabled_module_ids)

    def test_86_subscription_suspension_and_restoration(self):
        """Subscription suspension denies access; reactivation restores access."""
        now = timezone.now()
        sub = self._create_subscription(status=SubscriptionStatus.ACTIVE)
        UserProductAssignment.objects.create(
            organization=self.org,
            user=self.user_1,
            membership=self.membership_1,
            product=self.product_1,
            status=AssignmentStatus.ACTIVE,
            created_by=self.actor,
            updated_by=self.actor,
        )

        # Suspend subscription
        sub.status = SubscriptionStatus.SUSPENDED
        sub.save(update_fields=["status"])

        result_susp = evaluate_user_product_access(organization_id=self.org.id, user_id=self.user_1.id, product_id=self.product_1.id)
        self.assertFalse(result_susp.has_access)
        self.assertEqual(result_susp.denial_code, "SUBSCRIPTION_UNAVAILABLE")
        self.assertFalse(result_susp.is_subscription_eligible)
        self.assertIsNone(result_susp.assignment_status)
        self.assertEqual(result_susp.enabled_module_ids, [])
        self.assertEqual(result_susp.enabled_module_codes, [])

        # Reactivate subscription
        sub.status = SubscriptionStatus.ACTIVE
        sub.save(update_fields=["status"])

        result_active = evaluate_user_product_access(organization_id=self.org.id, user_id=self.user_1.id, product_id=self.product_1.id)
        self.assertTrue(result_active.has_access)
        self.assertIsNone(result_active.denial_code)
        self.assertEqual(result_active.assignment_status, "active")
        self.assertTrue(result_active.is_subscription_eligible)
