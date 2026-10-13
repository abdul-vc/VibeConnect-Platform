"""Phase 2F Part C focused test suite: Assignment Services and Lifecycle Integration.

Tests 33–48 (16 tests):
- 33: Create assignment allocates 1 seat and creates requested module rows.
- 34: Suspend active assignment preserves seat reservation and module rows.
- 35: Suspend idempotency performs zero writes and preserves timestamps/reason.
- 36: Reactivate suspended assignment restores active state and preserves suspension history.
- 37: Reactivate idempotency performs zero writes and preserves timestamps.
- 38: Revoke assignment releases seat reservation immediately.
- 39: Revoke idempotency performs zero writes and preserves timestamps.
- 40: Central user suspension denies effective access while preserving assignments/seats.
- 41: Central user disablement denies effective access while preserving assignments/seats.
- 42: Membership suspension denies effective access while preserving assignments/seats.
- 43: Membership reactivation restores effective access.
- 44: End membership with second admin succeeds and cascades assignment revocation.
- 45: Retire organization cascades revocation across active and suspended assignments.
- 46: Dormant product restores effective access after snapshot update.
- 47: Plan downgrade over-allocation grandfathers existing assignments while blocking new ones.
- 48: Strict evaluation denial precedence verification.
"""

from datetime import timedelta
from decimal import Decimal
import uuid

from django.contrib.auth import get_user_model
from django.test import TransactionTestCase
from django.utils import timezone

from apps.access_control.models import Role
from apps.access_control.services.provisioning import provision_organization_defaults
from apps.assignments.models import AssignmentStatus, UserModuleAssignment, UserProductAssignment
from apps.assignments.services import (
    assign_user_to_product,
    evaluate_user_product_access,
    reactivate_user_assignment,
    replace_user_module_assignments,
    resolve_governing_seat_pool,
    revoke_user_assignment,
    suspend_user_assignment,
)
from apps.assignments.services.exceptions import (
    AlreadyAssignedError,
    AssignmentNotFoundError,
    InvalidReasonError,
    InvalidStateTransitionError,
    MembershipIneligibleError,
    ModuleNotEntitledError,
    OrganizationNotActiveError,
    ProductInactiveError,
    ProductNotEntitledError,
    SeatLimitExceededError,
    SubscriptionUnavailableError,
    UserDisabledError,
    UserInactiveError,
)
from apps.entitlements.models import EntitlementStatus, OrganizationProductEntitlement
from apps.identity.services import disable_user, reactivate_user, suspend_user
from apps.organizations.membership_services import (
    end_membership,
    reactivate_membership,
    suspend_membership,
)
from apps.organizations.models import (
    MembershipStatus,
    MembershipType,
    Organization,
    OrganizationMembership,
    OrganizationStatus,
)
from apps.organizations.services import retire_organization
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


class AssignmentServicesTests(TransactionTestCase):
    """Part C automated domain services and lifecycle integration test suite."""

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
            membership_type=MembershipType.MEMBER,
            status=MembershipStatus.ACTIVE,
            joined_at=timezone.now(),
        )

        self.user_2 = PlatformUser.objects.create(
            email=f"user2_{uuid.uuid4().hex[:6]}@example.com",
            full_name="User Two",
            status="active",
            is_active=True,
        )
        self.membership_2 = OrganizationMembership.objects.create(
            organization=self.org,
            user=self.user_2,
            membership_type=MembershipType.MEMBER,
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
        self.module_3 = ProductModule.objects.create(
            product=self.product_1,
            code="mod3",
            name="Module Three",
            status=CatalogStatus.ACTIVE,
            created_by=self.actor,
            updated_by=self.actor,
        )
        self.module_direct = ProductModule.objects.create(
            product=self.product_1,
            code="mod_direct",
            name="Direct Module",
            status=CatalogStatus.ACTIVE,
            created_by=self.actor,
            updated_by=self.actor,
        )
        self.plan_mod_3 = PlanModule.objects.create(
            plan_version=self.plan_version,
            plan_product=self.plan_prod_1,
            module=self.module_3,
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

        # Active Subscription
        now = timezone.now()
        self.sub = OrganizationSubscription.objects.create(
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
            current_period_start=now - timedelta(days=5),
            current_period_end=now + timedelta(days=25),
            created_by=self.actor,
            updated_by=self.actor,
        )
        self.sub_prod_1 = SubscriptionProductEntitlement.objects.create(
            subscription=self.sub,
            organization=self.org,
            product=self.product_1,
            plan_product=self.plan_prod_1,
            product_code_snapshot=self.product_1.code,
            product_name_snapshot=self.product_1.name,
        )
        self.sub_mod_1 = SubscriptionModuleEntitlement.objects.create(
            subscription=self.sub,
            organization=self.org,
            module=self.module_1,
            plan_module=self.plan_mod_1,
            module_code_snapshot=self.module_1.code,
            module_name_snapshot=self.module_1.name,
        )
        self.sub_mod_2 = SubscriptionModuleEntitlement.objects.create(
            subscription=self.sub,
            organization=self.org,
            module=self.module_2,
            plan_module=self.plan_mod_2,
            module_code_snapshot=self.module_2.code,
            module_name_snapshot=self.module_2.name,
        )
        self.sub_mod_3 = SubscriptionModuleEntitlement.objects.create(
            subscription=self.sub,
            organization=self.org,
            module=self.module_3,
            plan_module=self.plan_mod_3,
            module_code_snapshot=self.module_3.code,
            module_name_snapshot=self.module_3.name,
        )
        self.sub_quota = SubscriptionQuotaEntitlement.objects.create(
            subscription=self.sub,
            organization=self.org,
            plan_quota=self.plan_quota,
            quota_key="seats",
            name="Plan Seats",
            scope=QuotaScope.PLAN,
            limit_type=QuotaLimitType.NUMERIC,
            limit_value=10,
            unit="seats",
            reset_period=QuotaResetPeriod.MONTHLY,
            is_hard_limit=True,
        )

    # -------------------------------------------------------------------------
    # Test 33: Create Assignment Service Success
    # -------------------------------------------------------------------------
    def test_33_create_assignment_service_success(self):
        """assign_user_to_product allocates one seat and creates requested module rows."""
        assignment = assign_user_to_product(
            organization_id=self.org.id,
            user_id=self.user_1.id,
            membership_id=self.membership_1.id,
            product_id=self.product_1.id,
            module_ids=[self.module_1.id, self.module_2.id],
            actor=self.actor,
        )
        self.assertIsNotNone(assignment)
        self.assertEqual(assignment.status, AssignmentStatus.ACTIVE)
        self.assertEqual(assignment.organization_id, self.org.id)
        self.assertEqual(assignment.user_id, self.user_1.id)
        self.assertEqual(assignment.membership_id, self.membership_1.id)
        self.assertEqual(assignment.product_id, self.product_1.id)
        self.assertEqual(assignment.created_by, self.actor)
        self.assertEqual(assignment.updated_by, self.actor)

        # 1. Start with enabled modules [A, B]
        mods = list(assignment.module_assignments.order_by("module__code"))
        self.assertEqual(len(mods), 2)
        self.assertTrue(mods[0].is_enabled)
        self.assertEqual(mods[0].module_id, self.module_1.id)
        self.assertTrue(mods[1].is_enabled)
        self.assertEqual(mods[1].module_id, self.module_2.id)

        # Seat pool consumption
        pool = resolve_governing_seat_pool(
            organization_id=self.org.id,
            product_id=self.product_1.id,
            subscription=self.sub,
        )
        self.assertEqual(pool.consumed_seats, 1)
        self.assertEqual(pool.available_seats, 9)

        # Effective access evaluates to True
        access = evaluate_user_product_access(
            organization_id=self.org.id,
            user_id=self.user_1.id,
            product_id=self.product_1.id,
        )
        self.assertTrue(access.has_access)
        self.assertEqual(access.assignment_status, "active")
        self.assertEqual(len(access.enabled_module_ids), 2)

        # Record module B row and assignment timestamps
        row_b_initial = UserModuleAssignment.objects.get(assignment=assignment, module_id=self.module_2.id)
        b_initial_updated_at = row_b_initial.updated_at

        # 2. Replace selection with [B, C]
        replace_user_module_assignments(
            assignment_id=assignment.id,
            module_ids=[self.module_2.id, self.module_3.id],
            actor=self.actor,
        )

        # 3. Module A row still exists with is_enabled=False
        row_a = UserModuleAssignment.objects.get(assignment=assignment, module_id=self.module_1.id)
        self.assertFalse(row_a.is_enabled)

        # 4. Module B remains enabled and its unchanged row timestamp is preserved
        row_b = UserModuleAssignment.objects.get(assignment=assignment, module_id=self.module_2.id)
        self.assertTrue(row_b.is_enabled)
        self.assertEqual(row_b.updated_at, b_initial_updated_at)

        # 5. Module C row is created with is_enabled=True
        row_c = UserModuleAssignment.objects.get(assignment=assignment, module_id=self.module_3.id)
        self.assertTrue(row_c.is_enabled)

        # 6. No module row is physically deleted (all 3 exist)
        self.assertEqual(UserModuleAssignment.objects.filter(assignment=assignment).count(), 3)

        # Identical enabled-module set is a true no-op (zero writes, unchanged assignment timestamp)
        assignment.refresh_from_db()
        assign_ts = assignment.updated_at
        replace_user_module_assignments(
            assignment_id=assignment.id,
            module_ids=[self.module_2.id, self.module_3.id],
            actor=self.actor,
        )
        assignment.refresh_from_db()
        self.assertEqual(assignment.updated_at, assign_ts)

        # 7. Empty replacement disables all rows without deleting them
        replace_user_module_assignments(
            assignment_id=assignment.id,
            module_ids=[],
            actor=self.actor,
        )
        self.assertEqual(UserModuleAssignment.objects.filter(assignment=assignment).count(), 3)
        self.assertEqual(UserModuleAssignment.objects.filter(assignment=assignment, is_enabled=True).count(), 0)
        self.assertEqual(UserModuleAssignment.objects.filter(assignment=assignment, is_enabled=False).count(), 3)

        # 8. A direct grant cannot authorize module replacement when subscription snapshot does not entitle module
        OrganizationProductEntitlement.objects.create(
            organization=self.org,
            product=self.product_1,
            status=EntitlementStatus.ACTIVE,
            created_by=self.actor,
            updated_by=self.actor,
        )
        with self.assertRaises(ModuleNotEntitledError):
            replace_user_module_assignments(
                assignment_id=assignment.id,
                module_ids=[self.module_direct.id],
                actor=self.actor,
            )

        # Revoked assignment rejects module replacement with INVALID_STATE_TRANSITION
        revoke_user_assignment(
            assignment_id=assignment.id,
            reason="Revoking for transition test",
            actor=self.actor,
        )
        with self.assertRaises(InvalidStateTransitionError):
            replace_user_module_assignments(
                assignment_id=assignment.id,
                module_ids=[self.module_2.id],
                actor=self.actor,
            )

    # -------------------------------------------------------------------------
    # Test 34: Suspend Active Assignment
    # -------------------------------------------------------------------------
    def test_34_suspend_active_assignment(self):
        """suspend_user_assignment transitions to suspended, stores reason, and preserves seat."""
        assignment = assign_user_to_product(
            organization_id=self.org.id,
            user_id=self.user_1.id,
            membership_id=self.membership_1.id,
            product_id=self.product_1.id,
            module_ids=[self.module_1.id],
            actor=self.actor,
        )

        suspended = suspend_user_assignment(
            assignment_id=assignment.id,
            reason="Temporary sabbatical leave",
            actor=self.actor,
        )
        self.assertEqual(suspended.status, AssignmentStatus.SUSPENDED)
        self.assertEqual(suspended.suspension_reason, "Temporary sabbatical leave")
        self.assertIsNotNone(suspended.last_suspended_at)

        # Suspended assignments continue reserving the seat
        pool = resolve_governing_seat_pool(
            organization_id=self.org.id,
            product_id=self.product_1.id,
            subscription=self.sub,
        )
        self.assertEqual(pool.consumed_seats, 1)
        self.assertEqual(pool.available_seats, 9)

        # Module rows remain unaltered
        mods = list(suspended.module_assignments.all())
        self.assertEqual(len(mods), 1)
        self.assertTrue(mods[0].is_enabled)

        # Effective access evaluates to False
        access = evaluate_user_product_access(
            organization_id=self.org.id,
            user_id=self.user_1.id,
            product_id=self.product_1.id,
        )
        self.assertFalse(access.has_access)
        self.assertEqual(access.denial_code, "ASSIGNMENT_SUSPENDED")

    # -------------------------------------------------------------------------
    # Test 35: Suspend Idempotency
    # -------------------------------------------------------------------------
    def test_35_suspend_idempotency(self):
        """Suspending an already suspended assignment is a true no-op with zero writes."""
        assignment = assign_user_to_product(
            organization_id=self.org.id,
            user_id=self.user_1.id,
            membership_id=self.membership_1.id,
            product_id=self.product_1.id,
            actor=self.actor,
        )
        suspend_user_assignment(
            assignment_id=assignment.id,
            reason="Original reason",
            actor=self.actor,
        )
        assignment.refresh_from_db()
        orig_updated_at = assignment.updated_at
        orig_suspended_at = assignment.last_suspended_at
        orig_reason = assignment.suspension_reason

        # Second suspend call
        res = suspend_user_assignment(
            assignment_id=assignment.id,
            reason="Different reason ignored",
            actor=self.actor,
        )
        res.refresh_from_db()
        self.assertEqual(res.status, AssignmentStatus.SUSPENDED)
        self.assertEqual(res.updated_at, orig_updated_at)
        self.assertEqual(res.last_suspended_at, orig_suspended_at)
        self.assertEqual(res.suspension_reason, orig_reason)

    # -------------------------------------------------------------------------
    # Test 36: Reactivate Suspended Assignment
    # -------------------------------------------------------------------------
    def test_36_reactivate_suspended_assignment(self):
        """reactivate_user_assignment transitions to active and preserves suspension history."""
        assignment = assign_user_to_product(
            organization_id=self.org.id,
            user_id=self.user_1.id,
            membership_id=self.membership_1.id,
            product_id=self.product_1.id,
            actor=self.actor,
        )
        suspend_user_assignment(
            assignment_id=assignment.id,
            reason="Prior investigation",
            actor=self.actor,
        )
        assignment.refresh_from_db()
        prior_suspended_at = assignment.last_suspended_at

        reactivated = reactivate_user_assignment(
            assignment_id=assignment.id,
            actor=self.actor,
        )
        self.assertEqual(reactivated.status, AssignmentStatus.ACTIVE)
        self.assertIsNotNone(reactivated.last_reactivated_at)
        # Prior suspension timestamps and reason are permanently preserved
        self.assertEqual(reactivated.last_suspended_at, prior_suspended_at)
        self.assertEqual(reactivated.suspension_reason, "Prior investigation")

        # Effective access evaluates to True
        access = evaluate_user_product_access(
            organization_id=self.org.id,
            user_id=self.user_1.id,
            product_id=self.product_1.id,
        )
        self.assertTrue(access.has_access)

    # -------------------------------------------------------------------------
    # Test 37: Reactivate Idempotency
    # -------------------------------------------------------------------------
    def test_37_reactivate_idempotency(self):
        """Reactivating an already active assignment is a true no-op with zero writes."""
        assignment = assign_user_to_product(
            organization_id=self.org.id,
            user_id=self.user_1.id,
            membership_id=self.membership_1.id,
            product_id=self.product_1.id,
            actor=self.actor,
        )
        assignment.refresh_from_db()
        orig_updated_at = assignment.updated_at
        orig_reactivated_at = assignment.last_reactivated_at

        res = reactivate_user_assignment(
            assignment_id=assignment.id,
            actor=self.actor,
        )
        res.refresh_from_db()
        self.assertEqual(res.status, AssignmentStatus.ACTIVE)
        self.assertEqual(res.updated_at, orig_updated_at)
        self.assertEqual(res.last_reactivated_at, orig_reactivated_at)

    # -------------------------------------------------------------------------
    # Test 38: Revoke Assignment Releases Seat
    # -------------------------------------------------------------------------
    def test_38_revoke_assignment_releases_seat(self):
        """revoke_user_assignment immediately releases seat reservation and preserves rows."""
        assignment = assign_user_to_product(
            organization_id=self.org.id,
            user_id=self.user_1.id,
            membership_id=self.membership_1.id,
            product_id=self.product_1.id,
            module_ids=[self.module_1.id],
            actor=self.actor,
        )
        pool_before = resolve_governing_seat_pool(
            organization_id=self.org.id,
            product_id=self.product_1.id,
            subscription=self.sub,
        )
        self.assertEqual(pool_before.consumed_seats, 1)

        revoked = revoke_user_assignment(
            assignment_id=assignment.id,
            reason="User departed the company",
            actor=self.actor,
        )
        self.assertEqual(revoked.status, AssignmentStatus.REVOKED)
        self.assertIsNotNone(revoked.revoked_at)
        self.assertEqual(revoked.revocation_reason, "User departed the company")

        # Seat is released immediately
        pool_after = resolve_governing_seat_pool(
            organization_id=self.org.id,
            product_id=self.product_1.id,
            subscription=self.sub,
        )
        self.assertEqual(pool_after.consumed_seats, 0)
        self.assertEqual(pool_after.available_seats, 10)

        # Rows are physically preserved
        self.assertTrue(UserProductAssignment.objects.filter(id=assignment.id).exists())
        self.assertEqual(UserModuleAssignment.objects.filter(assignment_id=assignment.id).count(), 1)

        # Access is denied
        access = evaluate_user_product_access(
            organization_id=self.org.id,
            user_id=self.user_1.id,
            product_id=self.product_1.id,
        )
        self.assertFalse(access.has_access)
        self.assertEqual(access.denial_code, "ASSIGNMENT_NOT_FOUND")

    # -------------------------------------------------------------------------
    # Test 39: Revoke Idempotency
    # -------------------------------------------------------------------------
    def test_39_revoke_idempotency(self):
        """Revoking an already revoked assignment is a true no-op with zero writes."""
        assignment = assign_user_to_product(
            organization_id=self.org.id,
            user_id=self.user_1.id,
            membership_id=self.membership_1.id,
            product_id=self.product_1.id,
            actor=self.actor,
        )
        revoke_user_assignment(
            assignment_id=assignment.id,
            reason="Initial revocation",
            actor=self.actor,
        )
        assignment.refresh_from_db()
        orig_updated_at = assignment.updated_at
        orig_revoked_at = assignment.revoked_at
        orig_reason = assignment.revocation_reason

        # Second revoke call
        res = revoke_user_assignment(
            assignment_id=assignment.id,
            reason="Ignored new reason",
            actor=self.actor,
        )
        res.refresh_from_db()
        self.assertEqual(res.status, AssignmentStatus.REVOKED)
        self.assertEqual(res.updated_at, orig_updated_at)
        self.assertEqual(res.revoked_at, orig_revoked_at)
        self.assertEqual(res.revocation_reason, orig_reason)

    # -------------------------------------------------------------------------
    # Test 40: Central User Suspension Denies Access
    # -------------------------------------------------------------------------
    def test_40_central_user_suspension_denies_access(self):
        """Central user suspension denies access without mutating assignment or releasing seat."""
        assignment = assign_user_to_product(
            organization_id=self.org.id,
            user_id=self.user_1.id,
            membership_id=self.membership_1.id,
            product_id=self.product_1.id,
            actor=self.actor,
        )
        suspend_user(
            actor=self.actor,
            user_id=self.user_1.id,
            reason="Security review suspension",
        )

        # Assignment row and status remain active
        assignment.refresh_from_db()
        self.assertEqual(assignment.status, AssignmentStatus.ACTIVE)

        # Seat remains consumed
        pool = resolve_governing_seat_pool(
            organization_id=self.org.id,
            product_id=self.product_1.id,
            subscription=self.sub,
        )
        self.assertEqual(pool.consumed_seats, 1)

        # Effective access evaluates to False
        access = evaluate_user_product_access(
            organization_id=self.org.id,
            user_id=self.user_1.id,
            product_id=self.product_1.id,
        )
        self.assertFalse(access.has_access)
        self.assertEqual(access.denial_code, "USER_INACTIVE")

    # -------------------------------------------------------------------------
    # Test 41: Central User Disablement Denies Access
    # -------------------------------------------------------------------------
    def test_41_central_user_disablement_denies_access(self):
        """Central user disablement denies access with USER_DISABLED without releasing seat."""
        assignment = assign_user_to_product(
            organization_id=self.org.id,
            user_id=self.user_1.id,
            membership_id=self.membership_1.id,
            product_id=self.product_1.id,
            actor=self.actor,
        )
        disable_user(
            actor=self.actor,
            user_id=self.user_1.id,
            reason="Permanent termination",
        )

        # Seat remains consumed
        pool = resolve_governing_seat_pool(
            organization_id=self.org.id,
            product_id=self.product_1.id,
            subscription=self.sub,
        )
        self.assertEqual(pool.consumed_seats, 1)

        # Effective access evaluates to USER_DISABLED
        access = evaluate_user_product_access(
            organization_id=self.org.id,
            user_id=self.user_1.id,
            product_id=self.product_1.id,
        )
        self.assertFalse(access.has_access)
        self.assertEqual(access.denial_code, "USER_DISABLED")

    # -------------------------------------------------------------------------
    # Test 42: Membership Suspension Denies Access
    # -------------------------------------------------------------------------
    def test_42_membership_suspension_denies_access(self):
        """Membership suspension denies access with MEMBERSHIP_INELIGIBLE while preserving seats."""
        assignment = assign_user_to_product(
            organization_id=self.org.id,
            user_id=self.user_1.id,
            membership_id=self.membership_1.id,
            product_id=self.product_1.id,
            actor=self.actor,
        )
        suspend_membership(
            actor=self.actor,
            membership_id=self.membership_1.id,
            reason="Compliance suspension",
        )

        # Seat remains consumed
        pool = resolve_governing_seat_pool(
            organization_id=self.org.id,
            product_id=self.product_1.id,
            subscription=self.sub,
        )
        self.assertEqual(pool.consumed_seats, 1)

        # Effective access evaluates to False
        access = evaluate_user_product_access(
            organization_id=self.org.id,
            user_id=self.user_1.id,
            product_id=self.product_1.id,
        )
        self.assertFalse(access.has_access)
        self.assertEqual(access.denial_code, "MEMBERSHIP_INELIGIBLE")

    # -------------------------------------------------------------------------
    # Test 43: Membership Reactivation Restores Access
    # -------------------------------------------------------------------------
    def test_43_membership_reactivation_restores_access(self):
        """Reactivating a suspended membership restores effective access automatically."""
        assignment = assign_user_to_product(
            organization_id=self.org.id,
            user_id=self.user_1.id,
            membership_id=self.membership_1.id,
            product_id=self.product_1.id,
            actor=self.actor,
        )
        suspend_membership(
            actor=self.actor,
            membership_id=self.membership_1.id,
            reason="Temporary suspension",
        )
        self.assertFalse(
            evaluate_user_product_access(
                organization_id=self.org.id,
                user_id=self.user_1.id,
                product_id=self.product_1.id,
            ).has_access
        )

        # Reactivate membership via domain service
        reactivate_membership(
            actor=self.actor,
            membership_id=self.membership_1.id,
        )

        access = evaluate_user_product_access(
            organization_id=self.org.id,
            user_id=self.user_1.id,
            product_id=self.product_1.id,
        )
        self.assertTrue(access.has_access)

    # -------------------------------------------------------------------------
    # Test 44: End Membership with Second Admin Success
    # -------------------------------------------------------------------------
    def test_44_end_membership_with_second_admin_success(self):
        """Ending a membership with a second admin cascades assignment revocation atomically."""
        from apps.access_control.models import AccessPermission, ConsoleModule, Role, RolePermission, RoleStatus

        mod, _ = ConsoleModule.objects.get_or_create(
            key="tenant_roles",
            defaults={"display_name": "Roles", "target_context": "tenant", "is_core": True, "is_active": True},
        )
        p_manage, _ = AccessPermission.objects.get_or_create(
            key="roles.manage",
            defaults={"console_module": mod, "display_name": "Manage Roles", "category": "roles", "is_active": True},
        )
        p_assign, _ = AccessPermission.objects.get_or_create(
            key="roles.assign",
            defaults={"console_module": mod, "display_name": "Assign Roles", "category": "roles", "is_active": True},
        )
        admin_role = Role.objects.create(
            organization=self.org,
            code=f"admin_role_{uuid.uuid4().hex[:6]}",
            name="Tenant Admin Role",
            status=RoleStatus.ACTIVE,
            is_system_role=False,
            created_by=self.actor,
            updated_by=self.actor,
        )
        RolePermission.objects.create(role=admin_role, permission=p_manage)
        RolePermission.objects.create(role=admin_role, permission=p_assign)

        admin_1_user = PlatformUser.objects.create(
            email=f"admin1_{uuid.uuid4().hex[:6]}@example.com",
            full_name="Admin One",
            status="active",
            is_active=True,
        )
        admin_1_mem = OrganizationMembership.objects.create(
            organization=self.org,
            user=admin_1_user,
            membership_type=MembershipType.TENANT_ADMIN,
            role=admin_role,
            status=MembershipStatus.ACTIVE,
            joined_at=timezone.now(),
        )

        admin_2_user = PlatformUser.objects.create(
            email=f"admin2_{uuid.uuid4().hex[:6]}@example.com",
            full_name="Admin Two",
            status="active",
            is_active=True,
        )
        admin_2_mem = OrganizationMembership.objects.create(
            organization=self.org,
            user=admin_2_user,
            membership_type=MembershipType.TENANT_ADMIN,
            role=admin_role,
            status=MembershipStatus.ACTIVE,
            joined_at=timezone.now(),
        )

        assignment = assign_user_to_product(
            organization_id=self.org.id,
            user_id=admin_1_user.id,
            membership_id=admin_1_mem.id,
            product_id=self.product_1.id,
            actor=self.actor,
        )
        self.assertEqual(assignment.status, AssignmentStatus.ACTIVE)

        # End admin_1's membership (admin_2 preserves the last-admin guard)
        ended_mem = end_membership(
            actor=self.actor,
            membership_id=admin_1_mem.id,
            reason="Admin resigned",
        )
        self.assertEqual(ended_mem.status, MembershipStatus.ENDED)

        # Cascaded revocation of assignment
        assignment.refresh_from_db()
        self.assertEqual(assignment.status, AssignmentStatus.REVOKED)
        self.assertEqual(assignment.revocation_reason, "Membership ended")
        self.assertIsNotNone(assignment.revoked_at)

        # Seat was released
        pool = resolve_governing_seat_pool(
            organization_id=self.org.id,
            product_id=self.product_1.id,
            subscription=self.sub,
        )
        self.assertEqual(pool.consumed_seats, 0)

    # -------------------------------------------------------------------------
    # Test 45: Retire Organization Cascades Revocation
    # -------------------------------------------------------------------------
    def test_45_retire_organization_cascades_revocation(self):
        """Retiring an organization cascades revocation across active and suspended assignments."""
        assign_1 = assign_user_to_product(
            organization_id=self.org.id,
            user_id=self.user_1.id,
            membership_id=self.membership_1.id,
            product_id=self.product_1.id,
            actor=self.actor,
        )
        assign_2 = assign_user_to_product(
            organization_id=self.org.id,
            user_id=self.user_2.id,
            membership_id=self.membership_2.id,
            product_id=self.product_1.id,
            actor=self.actor,
        )
        suspend_user_assignment(
            assignment_id=assign_2.id,
            reason="Suspended user",
            actor=self.actor,
        )

        retire_organization(organization_id=self.org.id, actor=self.actor)

        self.org.refresh_from_db()
        self.assertEqual(self.org.status, OrganizationStatus.RETIRED)

        # Subscriptions cancelled
        self.sub.refresh_from_db()
        self.assertEqual(self.sub.status, SubscriptionStatus.CANCELLED)

        # Both assignments revoked
        assign_1.refresh_from_db()
        self.assertEqual(assign_1.status, AssignmentStatus.REVOKED)
        self.assertEqual(assign_1.revocation_reason, "Organization retired")

        assign_2.refresh_from_db()
        self.assertEqual(assign_2.status, AssignmentStatus.REVOKED)
        self.assertEqual(assign_2.revocation_reason, "Organization retired")

        # History preserved
        self.assertTrue(UserProductAssignment.objects.filter(id=assign_1.id).exists())
        self.assertTrue(UserProductAssignment.objects.filter(id=assign_2.id).exists())

    # -------------------------------------------------------------------------
    # -------------------------------------------------------------------------
    # Test 46: Dormant Product Restores After Snapshot Update
    # -------------------------------------------------------------------------
    def test_46_dormant_product_restores_after_snapshot_update(self):
        """Omission of product from snapshot renders assignment dormant; restoration restores access."""
        from apps.subscriptions.services import change_subscription_plan

        assignment = assign_user_to_product(
            organization_id=self.org.id,
            user_id=self.user_1.id,
            membership_id=self.membership_1.id,
            product_id=self.product_1.id,
            actor=self.actor,
        )
        self.assertTrue(
            evaluate_user_product_access(
                organization_id=self.org.id,
                user_id=self.user_1.id,
                product_id=self.product_1.id,
            ).has_access
        )

        # Plan v2 omits product_1 (packages only product_2)
        plan_omitted = Plan.objects.create(
            code=f"omit_{uuid.uuid4().hex[:6]}",
            name="Plan Omit Product",
            is_public=True,
            created_by=self.actor,
            updated_by=self.actor,
        )
        plan_v2 = PlanVersion.objects.create(
            plan=plan_omitted,
            version=1,
            status=PlanVersionStatus.ACTIVE,
            activated_at=timezone.now(),
            created_by=self.actor,
            updated_by=self.actor,
        )
        plan_price_v2 = PlanPrice.objects.create(
            plan_version=plan_v2,
            currency=PlanCurrency.USD,
            billing_interval=BillingInterval.MONTHLY,
            amount=Decimal("150.00"),
            created_by=self.actor,
            updated_by=self.actor,
        )
        PlanProduct.objects.create(
            plan_version=plan_v2,
            product=self.product_2,
            created_by=self.actor,
        )
        PlanQuota.objects.create(
            plan_version=plan_v2,
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

        sub_omitted = change_subscription_plan(
            subscription_id=self.sub.id,
            new_plan_version_id=plan_v2.id,
            new_plan_price_id=plan_price_v2.id,
            actor=self.actor,
            change_reason="Switch to plan omitting product 1",
        )

        # Assignment remains active in DB, but effective access is False
        assignment.refresh_from_db()
        self.assertEqual(assignment.status, AssignmentStatus.ACTIVE)
        access_dormant = evaluate_user_product_access(
            organization_id=self.org.id,
            user_id=self.user_1.id,
            product_id=self.product_1.id,
        )
        self.assertFalse(access_dormant.has_access)
        self.assertEqual(access_dormant.denial_code, "PRODUCT_NOT_ENTITLED")

        # Plan v3 restores product_1
        plan_restored = Plan.objects.create(
            code=f"rest_{uuid.uuid4().hex[:6]}",
            name="Plan Restore Product",
            is_public=True,
            created_by=self.actor,
            updated_by=self.actor,
        )
        plan_v3 = PlanVersion.objects.create(
            plan=plan_restored,
            version=1,
            status=PlanVersionStatus.ACTIVE,
            activated_at=timezone.now(),
            created_by=self.actor,
            updated_by=self.actor,
        )
        plan_price_v3 = PlanPrice.objects.create(
            plan_version=plan_v3,
            currency=PlanCurrency.USD,
            billing_interval=BillingInterval.MONTHLY,
            amount=Decimal("200.00"),
            created_by=self.actor,
            updated_by=self.actor,
        )
        PlanProduct.objects.create(
            plan_version=plan_v3,
            product=self.product_1,
            created_by=self.actor,
        )
        PlanQuota.objects.create(
            plan_version=plan_v3,
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

        change_subscription_plan(
            subscription_id=sub_omitted.id,
            new_plan_version_id=plan_v3.id,
            new_plan_price_id=plan_price_v3.id,
            actor=self.actor,
            change_reason="Restore product 1",
        )

        access_restored = evaluate_user_product_access(
            organization_id=self.org.id,
            user_id=self.user_1.id,
            product_id=self.product_1.id,
        )
        self.assertTrue(access_restored.has_access)

    # -------------------------------------------------------------------------
    # Test 47: Plan Downgrade Over-Allocation Grandfathering
    # -------------------------------------------------------------------------
    def test_47_plan_downgrade_over_allocation_grandfathering(self):
        """Plan downgrade preserves grandfathered access for existing assignments while blocking new ones."""
        from apps.subscriptions.services import change_subscription_plan

        # Switch to initial 2-seat plan
        plan_2seats = Plan.objects.create(
            code=f"p2s_{uuid.uuid4().hex[:6]}",
            name="Plan 2 Seats",
            is_public=True,
            created_by=self.actor,
            updated_by=self.actor,
        )
        plan_v2 = PlanVersion.objects.create(
            plan=plan_2seats,
            version=1,
            status=PlanVersionStatus.ACTIVE,
            activated_at=timezone.now(),
            created_by=self.actor,
            updated_by=self.actor,
        )
        plan_price_v2 = PlanPrice.objects.create(
            plan_version=plan_v2,
            currency=PlanCurrency.USD,
            billing_interval=BillingInterval.MONTHLY,
            amount=Decimal("100.00"),
            created_by=self.actor,
            updated_by=self.actor,
        )
        PlanProduct.objects.create(
            plan_version=plan_v2,
            product=self.product_1,
            created_by=self.actor,
        )
        PlanQuota.objects.create(
            plan_version=plan_v2,
            quota_key="seats",
            name="Seats",
            scope=QuotaScope.PLAN,
            limit_type=QuotaLimitType.NUMERIC,
            limit_value=2,  # 2 seats
            unit="seats",
            reset_period=QuotaResetPeriod.MONTHLY,
            created_by=self.actor,
            updated_by=self.actor,
        )
        sub_2seats = change_subscription_plan(
            subscription_id=self.sub.id,
            new_plan_version_id=plan_v2.id,
            new_plan_price_id=plan_price_v2.id,
            actor=self.actor,
        )

        assign_1 = assign_user_to_product(
            organization_id=self.org.id,
            user_id=self.user_1.id,
            membership_id=self.membership_1.id,
            product_id=self.product_1.id,
            actor=self.actor,
        )
        assign_2 = assign_user_to_product(
            organization_id=self.org.id,
            user_id=self.user_2.id,
            membership_id=self.membership_2.id,
            product_id=self.product_1.id,
            actor=self.actor,
        )

        # Suspend assign_2 to verify reactivation works during overallocation
        suspend_user_assignment(
            assignment_id=assign_2.id,
            reason="Temp",
            actor=self.actor,
        )

        # Downgrade to 1-seat plan
        plan_1seat = Plan.objects.create(
            code=f"p1s_{uuid.uuid4().hex[:6]}",
            name="Plan 1 Seat",
            is_public=True,
            created_by=self.actor,
            updated_by=self.actor,
        )
        plan_v3 = PlanVersion.objects.create(
            plan=plan_1seat,
            version=1,
            status=PlanVersionStatus.ACTIVE,
            activated_at=timezone.now(),
            created_by=self.actor,
            updated_by=self.actor,
        )
        plan_price_v3 = PlanPrice.objects.create(
            plan_version=plan_v3,
            currency=PlanCurrency.USD,
            billing_interval=BillingInterval.MONTHLY,
            amount=Decimal("50.00"),
            created_by=self.actor,
            updated_by=self.actor,
        )
        PlanProduct.objects.create(
            plan_version=plan_v3,
            product=self.product_1,
            created_by=self.actor,
        )
        PlanQuota.objects.create(
            plan_version=plan_v3,
            quota_key="seats",
            name="Seats",
            scope=QuotaScope.PLAN,
            limit_type=QuotaLimitType.NUMERIC,
            limit_value=1,  # Downgraded to 1 seat
            unit="seats",
            reset_period=QuotaResetPeriod.MONTHLY,
            created_by=self.actor,
            updated_by=self.actor,
        )
        sub_downgraded = change_subscription_plan(
            subscription_id=sub_2seats.id,
            new_plan_version_id=plan_v3.id,
            new_plan_price_id=plan_price_v3.id,
            actor=self.actor,
        )

        pool = resolve_governing_seat_pool(
            organization_id=self.org.id,
            product_id=self.product_1.id,
            subscription=sub_downgraded,
        )
        self.assertEqual(pool.total_limit, 1)
        self.assertEqual(pool.consumed_seats, 2)
        self.assertFalse(pool.is_capacity_available)
        self.assertEqual(pool.over_allocated_amount, 1)

        # Grandfathered active access remains intact
        access_1 = evaluate_user_product_access(
            organization_id=self.org.id,
            user_id=self.user_1.id,
            product_id=self.product_1.id,
        )
        self.assertTrue(access_1.has_access)

        # New allocations are blocked
        user_3 = PlatformUser.objects.create(
            email=f"user3_{uuid.uuid4().hex[:6]}@example.com",
            full_name="User Three",
            status="active",
            is_active=True,
        )
        membership_3 = OrganizationMembership.objects.create(
            organization=self.org,
            user=user_3,
            membership_type=MembershipType.MEMBER,
            status=MembershipStatus.ACTIVE,
            joined_at=timezone.now(),
        )
        with self.assertRaises(SeatLimitExceededError):
            assign_user_to_product(
                organization_id=self.org.id,
                user_id=user_3.id,
                membership_id=membership_3.id,
                product_id=self.product_1.id,
                actor=self.actor,
            )

        # Reactivation of suspended assignment remains allowed
        reactivated = reactivate_user_assignment(
            assignment_id=assign_2.id,
            actor=self.actor,
        )
        self.assertEqual(reactivated.status, AssignmentStatus.ACTIVE)
        self.assertTrue(
            evaluate_user_product_access(
                organization_id=self.org.id,
                user_id=self.user_2.id,
                product_id=self.product_1.id,
            ).has_access
        )

    # -------------------------------------------------------------------------
    # Test 48: Evaluate User Product Access Denial Precedence
    # -------------------------------------------------------------------------
    def test_48_evaluate_user_product_access_denial_precedence(self):
        """Access evaluation strictly respects the 8-level deterministic denial precedence."""
        assignment = assign_user_to_product(
            organization_id=self.org.id,
            user_id=self.user_1.id,
            membership_id=self.membership_1.id,
            product_id=self.product_1.id,
            actor=self.actor,
        )

        # Precedence 1: ORGANIZATION_INACTIVE
        self.org.status = OrganizationStatus.SUSPENDED
        self.org.save(update_fields=["status"])
        res1 = evaluate_user_product_access(
            organization_id=self.org.id,
            user_id=self.user_1.id,
            product_id=self.product_1.id,
        )
        self.assertEqual(res1.denial_code, "ORGANIZATION_INACTIVE")
        self.org.status = OrganizationStatus.ACTIVE
        self.org.save(update_fields=["status"])

        # Precedence 2: USER_DISABLED / USER_INACTIVE
        # Test USER_INACTIVE on user_1
        suspend_user(actor=self.actor, user_id=self.user_1.id, reason="Testing precedence")
        res2_inact = evaluate_user_product_access(
            organization_id=self.org.id,
            user_id=self.user_1.id,
            product_id=self.product_1.id,
        )
        self.assertEqual(res2_inact.denial_code, "USER_INACTIVE")
        reactivate_user(actor=self.actor, user_id=self.user_1.id)

        # Test USER_DISABLED on a disabled user
        user_dis = PlatformUser.objects.create(
            email=f"dis_{uuid.uuid4().hex[:6]}@example.com",
            full_name="Disabled User",
            status="active",
            is_active=True,
        )
        OrganizationMembership.objects.create(
            organization=self.org,
            user=user_dis,
            membership_type=MembershipType.MEMBER,
            status=MembershipStatus.ACTIVE,
            joined_at=timezone.now(),
        )
        disable_user(actor=self.actor, user_id=user_dis.id, reason="Testing disablement precedence")
        res2_dis = evaluate_user_product_access(
            organization_id=self.org.id,
            user_id=user_dis.id,
            product_id=self.product_1.id,
        )
        self.assertEqual(res2_dis.denial_code, "USER_DISABLED")

        # Precedence 3: MEMBERSHIP_INELIGIBLE
        suspend_membership(actor=self.actor, membership_id=self.membership_1.id, reason="Testing precedence")
        res3 = evaluate_user_product_access(
            organization_id=self.org.id,
            user_id=self.user_1.id,
            product_id=self.product_1.id,
        )
        self.assertEqual(res3.denial_code, "MEMBERSHIP_INELIGIBLE")
        reactivate_membership(actor=self.actor, membership_id=self.membership_1.id)

        # Precedence 4: SUBSCRIPTION_UNAVAILABLE
        self.sub.status = SubscriptionStatus.SUSPENDED
        self.sub.save(update_fields=["status"])
        res4 = evaluate_user_product_access(
            organization_id=self.org.id,
            user_id=self.user_1.id,
            product_id=self.product_1.id,
        )
        self.assertEqual(res4.denial_code, "SUBSCRIPTION_UNAVAILABLE")
        self.sub.status = SubscriptionStatus.ACTIVE
        self.sub.save(update_fields=["status"])

        # Precedence 5: PRODUCT_INACTIVE
        self.product_1.status = ProductStatus.INACTIVE
        self.product_1.save(update_fields=["status"])
        res5 = evaluate_user_product_access(
            organization_id=self.org.id,
            user_id=self.user_1.id,
            product_id=self.product_1.id,
        )
        self.assertEqual(res5.denial_code, "PRODUCT_INACTIVE")
        self.product_1.status = ProductStatus.ACTIVE
        self.product_1.save(update_fields=["status"])

        # Precedence 6: PRODUCT_NOT_ENTITLED (test against product_2 which is not in subscription snapshot)
        res6 = evaluate_user_product_access(
            organization_id=self.org.id,
            user_id=self.user_1.id,
            product_id=self.product_2.id,
        )
        self.assertEqual(res6.denial_code, "PRODUCT_NOT_ENTITLED")

        # Precedence 7: ASSIGNMENT_NOT_FOUND (when revoked or missing)
        revoke_user_assignment(
            assignment_id=assignment.id,
            reason="Revoked",
            actor=self.actor,
        )
        res7 = evaluate_user_product_access(
            organization_id=self.org.id,
            user_id=self.user_1.id,
            product_id=self.product_1.id,
        )
        self.assertEqual(res7.denial_code, "ASSIGNMENT_NOT_FOUND")

        # Create fresh assignment and suspend it -> Precedence 8: ASSIGNMENT_SUSPENDED
        assignment2 = assign_user_to_product(
            organization_id=self.org.id,
            user_id=self.user_1.id,
            membership_id=self.membership_1.id,
            product_id=self.product_1.id,
            actor=self.actor,
        )
        suspend_user_assignment(
            assignment_id=assignment2.id,
            reason="Suspended",
            actor=self.actor,
        )
        res8 = evaluate_user_product_access(
            organization_id=self.org.id,
            user_id=self.user_1.id,
            product_id=self.product_1.id,
        )
        self.assertEqual(res8.denial_code, "ASSIGNMENT_SUSPENDED")

        # Reactivate -> All pass -> has_access=True
        reactivate_user_assignment(
            assignment_id=assignment2.id,
            actor=self.actor,
        )
        res9 = evaluate_user_product_access(
            organization_id=self.org.id,
            user_id=self.user_1.id,
            product_id=self.product_1.id,
        )
        self.assertTrue(res9.has_access)
        self.assertIsNone(res9.denial_code)

