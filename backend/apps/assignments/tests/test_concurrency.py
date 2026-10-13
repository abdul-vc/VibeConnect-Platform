"""Phase 2F Part C focused test suite: Concurrency Races.

Tests 49–51 (3 tests):
- 49: Concurrency last-seat race yields exactly one success and one SeatLimitExceededError.
- 50: Concurrency duplicate assignment race yields exactly one success and one ALREADY_ASSIGNED.
- 51: Concurrency reactivation vs membership end resolves deterministically without orphaned active assignments.
"""

from datetime import timedelta
from decimal import Decimal
import threading
import uuid

from django.contrib.auth import get_user_model
from django.db import close_old_connections
from django.test import TransactionTestCase
from django.utils import timezone

from apps.access_control.models import Role
from apps.access_control.services.provisioning import provision_organization_defaults
from apps.assignments.models import AssignmentStatus, UserProductAssignment
from apps.assignments.services import (
    assign_user_to_product,
    reactivate_user_assignment,
    suspend_user_assignment,
)
from apps.assignments.services.exceptions import (
    AlreadyAssignedError,
    InvalidStateTransitionError,
    MembershipIneligibleError,
    SeatLimitExceededError,
)
from apps.organizations.membership_services import end_membership
from apps.organizations.models import (
    MembershipStatus,
    MembershipType,
    Organization,
    OrganizationMembership,
    OrganizationStatus,
)
from apps.plans.models import (
    BillingInterval,
    Plan,
    PlanCurrency,
    PlanPrice,
    PlanProduct,
    PlanQuota,
    PlanVersion,
    PlanVersionStatus,
    QuotaLimitType,
    QuotaResetPeriod,
    QuotaScope,
)
from apps.product_registry.models import Product, ProductStatus
from apps.subscriptions.models import (
    OrganizationSubscription,
    SubscriptionProductEntitlement,
    SubscriptionQuotaEntitlement,
    SubscriptionStatus,
)

PlatformUser = get_user_model()


class AssignmentConcurrencyTests(TransactionTestCase):
    """Part C automated concurrency and race conditions test suite."""

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

        self.user_a = PlatformUser.objects.create(
            email=f"usera_{uuid.uuid4().hex[:6]}@example.com",
            full_name="User A",
            status="active",
            is_active=True,
        )
        self.membership_a = OrganizationMembership.objects.create(
            organization=self.org,
            user=self.user_a,
            membership_type=MembershipType.MEMBER,
            status=MembershipStatus.ACTIVE,
            joined_at=timezone.now(),
        )

        self.user_b = PlatformUser.objects.create(
            email=f"userb_{uuid.uuid4().hex[:6]}@example.com",
            full_name="User B",
            status="active",
            is_active=True,
        )
        self.membership_b = OrganizationMembership.objects.create(
            organization=self.org,
            user=self.user_b,
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

        # Plan hierarchy with exactly 1 seat
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
        self.plan_quota = PlanQuota.objects.create(
            plan_version=self.plan_version,
            quota_key="seats",
            name="Seats",
            scope=QuotaScope.PLAN,
            limit_type=QuotaLimitType.NUMERIC,
            limit_value=1,  # Exactly 1 seat limit
            unit="seats",
            reset_period=QuotaResetPeriod.MONTHLY,
            created_by=self.actor,
            updated_by=self.actor,
        )

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
        self.sub_quota = SubscriptionQuotaEntitlement.objects.create(
            subscription=self.sub,
            organization=self.org,
            plan_quota=self.plan_quota,
            quota_key="seats",
            name="Plan Seats",
            scope=QuotaScope.PLAN,
            limit_type=QuotaLimitType.NUMERIC,
            limit_value=1,  # 1 seat limit
            unit="seats",
            reset_period=QuotaResetPeriod.MONTHLY,
            is_hard_limit=True,
        )

    # -------------------------------------------------------------------------
    # Test 49: Concurrency Last Seat Race
    # -------------------------------------------------------------------------
    def test_49_concurrency_last_seat_race(self):
        """Two concurrent threads racing for the last seat yield exactly one success and one SeatLimitExceededError."""
        barrier = threading.Barrier(2)
        results = []
        errors = []
        lock = threading.Lock()

        def _worker(user, membership):
            close_old_connections()
            try:
                barrier.wait(timeout=10.0)
                res = assign_user_to_product(
                    organization_id=self.org.id,
                    user_id=user.id,
                    membership_id=membership.id,
                    product_id=self.product_1.id,
                    actor=self.actor,
                )
                with lock:
                    results.append(res)
            except Exception as e:
                with lock:
                    errors.append(e)
            finally:
                close_old_connections()

        t1 = threading.Thread(target=_worker, args=(self.user_a, self.membership_a))
        t2 = threading.Thread(target=_worker, args=(self.user_b, self.membership_b))

        t1.start()
        t2.start()

        t1.join(timeout=10.0)
        t2.join(timeout=10.0)

        self.assertFalse(t1.is_alive(), "Thread 1 deadlocked")
        self.assertFalse(t2.is_alive(), "Thread 2 deadlocked")

        self.assertEqual(len(results), 1, f"Expected exactly 1 success, got {len(results)}")
        self.assertEqual(len(errors), 1, f"Expected exactly 1 failure, got {len(errors)}")
        self.assertIsInstance(errors[0], SeatLimitExceededError)
        self.assertEqual(errors[0].code, "SEAT_LIMIT_EXCEEDED")

        # Database invariant: exactly one active assignment row exists
        self.assertEqual(
            UserProductAssignment.objects.filter(
                organization_id=self.org.id,
                product_id=self.product_1.id,
                status=AssignmentStatus.ACTIVE,
            ).count(),
            1,
        )

    # -------------------------------------------------------------------------
    # Test 50: Concurrency Duplicate Assignment Race
    # -------------------------------------------------------------------------
    def test_50_concurrency_duplicate_assignment_race(self):
        """Two concurrent threads racing to assign same user yield one success and one ALREADY_ASSIGNED."""
        barrier = threading.Barrier(2)
        results = []
        errors = []
        lock = threading.Lock()

        def _worker():
            close_old_connections()
            try:
                barrier.wait(timeout=10.0)
                res = assign_user_to_product(
                    organization_id=self.org.id,
                    user_id=self.user_a.id,
                    membership_id=self.membership_a.id,
                    product_id=self.product_1.id,
                    actor=self.actor,
                )
                with lock:
                    results.append(res)
            except Exception as e:
                with lock:
                    errors.append(e)
            finally:
                close_old_connections()

        t1 = threading.Thread(target=_worker)
        t2 = threading.Thread(target=_worker)

        t1.start()
        t2.start()

        t1.join(timeout=10.0)
        t2.join(timeout=10.0)

        self.assertFalse(t1.is_alive(), "Thread 1 deadlocked")
        self.assertFalse(t2.is_alive(), "Thread 2 deadlocked")

        self.assertEqual(len(results), 1, f"Expected exactly 1 success, got {len(results)}")
        self.assertEqual(len(errors), 1, f"Expected exactly 1 failure, got {len(errors)}")
        self.assertIsInstance(errors[0], AlreadyAssignedError)
        self.assertEqual(errors[0].code, "ALREADY_ASSIGNED")

        # Database invariant: exactly one assignment row exists for user_a
        self.assertEqual(
            UserProductAssignment.objects.filter(
                organization_id=self.org.id,
                user_id=self.user_a.id,
                product_id=self.product_1.id,
            ).count(),
            1,
        )

    # -------------------------------------------------------------------------
    # Test 51: Concurrency Reactivation vs Membership End
    # -------------------------------------------------------------------------
    def test_51_concurrency_reactivation_vs_membership_end(self):
        """Reactivation vs membership ending resolves deterministically; never produces active assignment on ended membership."""
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
            email=f"admin1_c_{uuid.uuid4().hex[:6]}@example.com",
            full_name="Admin One C",
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
            email=f"admin2_c_{uuid.uuid4().hex[:6]}@example.com",
            full_name="Admin Two C",
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

        # Create assignment for admin_1 and suspend it
        assignment = assign_user_to_product(
            organization_id=self.org.id,
            user_id=admin_1_user.id,
            membership_id=admin_1_mem.id,
            product_id=self.product_1.id,
            actor=self.actor,
        )
        suspend_user_assignment(
            assignment_id=assignment.id,
            reason="Initial suspension",
            actor=self.actor,
        )

        barrier = threading.Barrier(2)
        errors = []
        lock = threading.Lock()

        def _reactivate_worker():
            close_old_connections()
            try:
                barrier.wait(timeout=10.0)
                reactivate_user_assignment(
                    assignment_id=assignment.id,
                    actor=self.actor,
                )
            except Exception as e:
                with lock:
                    errors.append(("reactivate", e))
            finally:
                close_old_connections()

        def _end_membership_worker():
            close_old_connections()
            try:
                barrier.wait(timeout=10.0)
                end_membership(
                    actor=self.actor,
                    membership_id=admin_1_mem.id,
                    reason="Admin resigning",
                )
            except Exception as e:
                with lock:
                    errors.append(("end_membership", e))
            finally:
                close_old_connections()

        t1 = threading.Thread(target=_reactivate_worker)
        t2 = threading.Thread(target=_end_membership_worker)

        t1.start()
        t2.start()

        t1.join(timeout=10.0)
        t2.join(timeout=10.0)

        self.assertFalse(t1.is_alive(), "Reactivate worker deadlocked")
        self.assertFalse(t2.is_alive(), "End membership worker deadlocked")

        # Invariant check:
        admin_1_mem.refresh_from_db()
        assignment.refresh_from_db()

        # If membership ended, assignment MUST be revoked (never active on ended membership)
        if admin_1_mem.status == MembershipStatus.ENDED:
            self.assertEqual(
                assignment.status,
                AssignmentStatus.REVOKED,
                "Assignment must not remain active/suspended if membership was ended",
            )
            self.assertEqual(assignment.revocation_reason, "Membership ended")
