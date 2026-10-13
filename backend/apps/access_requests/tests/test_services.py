"""Authoritative Test Suite for Access Requests & Approvals (Phase 3F).

Tests cover:
- Request creation & validation
- Duplicate request conflict detection
- Membership eligibility validation
- Approval granting assignment via Phase 2F engine
- Denial with mandatory reason (1-500 chars)
- Re-validation failure at decision time (seat capacity exceeded retains pending status)
- Membership ended auto-cancels pending request
- Append-only decision history immutability
- API endpoints (list, create, approve, deny, cancel)
"""

from decimal import Decimal
import uuid

from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from apps.access_control.models import (
    AccessPermission,
    ConsoleModule,
    OrganizationConsoleModulePolicy,
    OrganizationPermissionCeiling,
    Role,
    RolePermission,
    RoleStatus,
)
from apps.access_requests.models import (
    AccessRequest,
    AccessRequestDecision,
    AccessRequestDecisionType,
    AccessRequestStatus,
)
from apps.access_requests.services import (
    AccessRequestError,
    AccessRequestNotFoundError,
    DuplicateAccessRequestError,
    InvalidReasonError,
    InvalidRequestStatusError,
    approve_access_request,
    cancel_access_request,
    create_access_request,
    deny_access_request,
)
from apps.assignments.models import AssignmentStatus, UserProductAssignment
from apps.assignments.services import (
    AlreadyAssignedError,
    MembershipIneligibleError,
    SeatLimitExceededError,
)
from apps.auditlog.models import AuditAction, AuditLog
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
    PlanModule,
    PlanPrice,
    PlanProduct,
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
    SubscriptionProductEntitlement,
    SubscriptionQuotaEntitlement,
    SubscriptionStatus,
)
from apps.subscriptions.services import _reconcile_subscription_snapshots

PlatformUser = get_user_model()


class AccessRequestsTestSuite(APITestCase):
    """Authoritative test cases for Phase 3F Access Requests & Approvals."""

    def setUp(self):
        super().setUp()
        cache.clear()
        self.password = "SecurePassword123!"

        # 1. System Service Actor
        self.system_actor, _ = PlatformUser.objects.get_or_create(
            email="system@vibeconnect.internal",
            defaults={
                "full_name": "VibeConnect System Engine",
                "status": "active",
                "is_active": True,
                "is_staff": True,
                "is_platform_owner": True,
                "is_superuser": False,
            },
        )

        # 2. Platform Owner
        self.owner = PlatformUser.objects.create_user(
            email="owner_ar@vibeconnect.internal",
            password=self.password,
            full_name="Platform Owner AR",
            status="active",
            is_active=True,
            is_platform_owner=True,
        )

        # 3. Organization
        self.org = Organization.objects.create(
            code="org-ar-test",
            name="Org Access Requests Test",
            status=OrganizationStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )

        # 4. Access Control setup: ConsoleModule, Permissions, Role
        self.module, _ = ConsoleModule.objects.get_or_create(
            key="tenant_product_assignments",
            defaults={
                "display_name": "User Product Assignments",
                "target_context": "tenant",
                "is_core": False,
                "is_active": True,
                "sort_order": 50,
            },
        )
        self.perm_view, _ = AccessPermission.objects.get_or_create(
            key="assignments.view",
            defaults={
                "console_module": self.module,
                "display_name": "View Product Assignments",
                "category": "Tenant Administration",
                "is_active": True,
                "sort_order": 1,
            },
        )
        self.perm_manage, _ = AccessPermission.objects.get_or_create(
            key="assignments.manage",
            defaults={
                "console_module": self.module,
                "display_name": "Manage Product Assignments",
                "category": "Tenant Administration",
                "is_active": True,
                "sort_order": 2,
            },
        )
        self.system_role, _ = Role.objects.get_or_create(
            code="system_tenant_admin",
            defaults={
                "name": "System Tenant Administrator",
                "is_system_role": True,
                "status": RoleStatus.ACTIVE,
                "organization": None,
            },
        )
        RolePermission.objects.get_or_create(role=self.system_role, permission=self.perm_view)
        RolePermission.objects.get_or_create(role=self.system_role, permission=self.perm_manage)

        OrganizationConsoleModulePolicy.objects.get_or_create(
            organization=self.org,
            console_module=self.module,
            defaults={"is_enabled": True, "updated_by": self.owner},
        )
        for p in [self.perm_view, self.perm_manage]:
            OrganizationPermissionCeiling.objects.get_or_create(
                organization=self.org,
                permission=p,
                defaults={"is_allowed": True, "updated_by": self.owner},
            )

        self.ar_module, _ = ConsoleModule.objects.get_or_create(
            key="tenant_access_requests",
            defaults={
                "display_name": "Access Requests & Approvals",
                "target_context": "tenant",
                "is_core": False,
                "is_active": True,
                "sort_order": 35,
            },
        )
        self.ar_perm_view, _ = AccessPermission.objects.get_or_create(
            key="access_requests.view",
            defaults={
                "console_module": self.ar_module,
                "display_name": "View Access Requests",
                "category": "access_requests",
                "is_active": True,
                "sort_order": 10,
            },
        )
        self.ar_perm_manage, _ = AccessPermission.objects.get_or_create(
            key="access_requests.manage",
            defaults={
                "console_module": self.ar_module,
                "display_name": "Manage Access Requests",
                "category": "access_requests",
                "is_active": True,
                "sort_order": 20,
            },
        )
        self.ar_perm_decide, _ = AccessPermission.objects.get_or_create(
            key="access_requests.decide",
            defaults={
                "console_module": self.ar_module,
                "display_name": "Decide Access Requests",
                "category": "access_requests",
                "is_active": True,
                "sort_order": 25,
            },
        )
        for p in [self.ar_perm_view, self.ar_perm_manage, self.ar_perm_decide]:
            RolePermission.objects.get_or_create(role=self.system_role, permission=p)

        OrganizationConsoleModulePolicy.objects.get_or_create(
            organization=self.org,
            console_module=self.ar_module,
            defaults={"is_enabled": True, "updated_by": self.owner},
        )
        for p in [self.ar_perm_view, self.ar_perm_manage, self.ar_perm_decide]:
            OrganizationPermissionCeiling.objects.get_or_create(
                organization=self.org,
                permission=p,
                defaults={"is_allowed": True, "updated_by": self.owner},
            )

        # 5. Users and Memberships
        self.admin_user = PlatformUser.objects.create_user(
            email="admin_ar@vibeconnect.internal",
            password=self.password,
            full_name="AR Admin User",
            status="active",
            is_active=True,
            is_platform_owner=False,
        )
        self.membership_admin = OrganizationMembership.objects.create(
            organization=self.org,
            user=self.admin_user,
            membership_type=MembershipType.TENANT_ADMIN,
            status=MembershipStatus.ACTIVE,
            role=self.system_role,
            joined_at=timezone.now(),
        )

        self.member_user = PlatformUser.objects.create_user(
            email="member_ar@vibeconnect.internal",
            password=self.password,
            full_name="AR Member User",
            status="active",
            is_active=True,
            is_platform_owner=False,
        )
        self.membership_member = OrganizationMembership.objects.create(
            organization=self.org,
            user=self.member_user,
            membership_type=MembershipType.MEMBER,
            status=MembershipStatus.ACTIVE,
            role=None,
            joined_at=timezone.now(),
        )

        # 6. Catalog Product and Subscription
        now = timezone.now()
        self.product = Product.objects.create(
            code="ar_lms_core",
            name="AR LMS Core",
            status=ProductStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )
        self.plan = Plan.objects.create(
            code="ar_plan",
            name="AR Plan",
            created_by=self.owner,
            updated_by=self.owner,
        )
        self.plan_version = PlanVersion.objects.create(
            plan=self.plan,
            version=1,
            status=PlanVersionStatus.ACTIVE,
            activated_at=now,
            created_by=self.owner,
            updated_by=self.owner,
        )
        self.plan_price = PlanPrice.objects.create(
            plan_version=self.plan_version,
            currency="USD",
            amount=Decimal("99.00"),
            billing_interval=BillingInterval.MONTHLY,
            created_by=self.owner,
            updated_by=self.owner,
        )
        self.plan_prod = PlanProduct.objects.create(
            plan_version=self.plan_version,
            product=self.product,
            created_by=self.owner,
        )
        self.plan_quota = PlanQuota.objects.create(
            plan_version=self.plan_version,
            quota_key="seats",
            name="Product Seats",
            scope=QuotaScope.PLAN,
            limit_type=QuotaLimitType.NUMERIC,
            limit_value=1,  # Capacity of 1 seat for testing ceiling limits
            unit="seats",
            is_hard_limit=True,
            reset_period=QuotaResetPeriod.NEVER,
            created_by=self.owner,
            updated_by=self.owner,
        )

        self.subscription = OrganizationSubscription.objects.create(
            organization=self.org,
            plan_version=self.plan_version,
            plan_price=self.plan_price,
            plan_code_snapshot="ar_plan",
            plan_name_snapshot="AR Plan",
            version_number_snapshot=1,
            billing_interval="monthly",
            currency="USD",
            amount=Decimal("99.00"),
            status=SubscriptionStatus.ACTIVE,
            current_period_start=now,
            current_period_end=now + timezone.timedelta(days=30),
            created_by=self.owner,
            updated_by=self.owner,
        )
        _reconcile_subscription_snapshots(self.subscription)

    def test_create_access_request_success(self):
        """Active tenant member can request access to active product."""
        req = create_access_request(
            organization=self.org,
            requester=self.member_user,
            product=self.product,
            reason="Need LMS access for learning path.",
        )
        self.assertEqual(req.status, AccessRequestStatus.PENDING)
        self.assertEqual(req.requester, self.member_user)
        self.assertEqual(req.product, self.product)
        self.assertEqual(req.organization, self.org)
        self.assertEqual(req.reason, "Need LMS access for learning path.")

        # Verify audit log
        audit = AuditLog.objects.filter(
            action=AuditAction.ACCESS_REQUEST_CREATED,
            target_id=req.id,
        ).first()
        self.assertIsNotNone(audit)
        self.assertEqual(audit.actor, self.member_user)

    def test_duplicate_pending_request_conflict(self):
        """Duplicate pending request for same user and product is rejected."""
        create_access_request(
            organization=self.org,
            requester=self.member_user,
            product=self.product,
            reason="First request.",
        )
        with self.assertRaises(DuplicateAccessRequestError):
            create_access_request(
                organization=self.org,
                requester=self.member_user,
                product=self.product,
                reason="Duplicate request.",
            )

    def test_membership_ineligible_cannot_request(self):
        """User without active membership cannot create request."""
        outsider = PlatformUser.objects.create_user(
            email="outsider@vibeconnect.internal",
            password=self.password,
            full_name="Outsider",
        )
        with self.assertRaises(MembershipIneligibleError):
            create_access_request(
                organization=self.org,
                requester=outsider,
                product=self.product,
            )

    def test_approve_access_request_grants_assignment(self):
        """Approval assigns product via Phase 2F engine and creates immutable decision."""
        req = create_access_request(
            organization=self.org,
            requester=self.member_user,
            product=self.product,
            reason="Requesting LMS.",
        )
        approved_req, assignment = approve_access_request(
            request_id=req.id,
            approver=self.admin_user,
            reason="Approved for Q3 training.",
        )

        self.assertEqual(approved_req.status, AccessRequestStatus.APPROVED)
        self.assertIsNotNone(assignment)
        self.assertEqual(assignment.user, self.member_user)
        self.assertEqual(assignment.product, self.product)
        self.assertEqual(assignment.status, AssignmentStatus.ACTIVE)

        # Check decision record
        decision = AccessRequestDecision.objects.filter(request=approved_req).first()
        self.assertIsNotNone(decision)
        self.assertEqual(decision.decision, AccessRequestDecisionType.APPROVED)
        self.assertEqual(decision.approver, self.admin_user)
        self.assertEqual(decision.reason, "Approved for Q3 training.")

        # Check audit log
        audit = AuditLog.objects.filter(
            action=AuditAction.ACCESS_REQUEST_APPROVED,
            target_id=approved_req.id,
        ).first()
        self.assertIsNotNone(audit)

    def test_approval_fails_gracefully_when_seats_exceeded(self):
        """When seat capacity is reached, approval raises error and request stays pending."""
        # Member 1 consumes the single seat (capacity limit_value = 1)
        req1 = create_access_request(
            organization=self.org,
            requester=self.member_user,
            product=self.product,
        )
        approve_access_request(request_id=req1.id, approver=self.admin_user)

        # Member 2 creates request
        member_2 = PlatformUser.objects.create_user(
            email="member2_ar@vibeconnect.internal",
            password=self.password,
            full_name="Member 2",
        )
        OrganizationMembership.objects.create(
            organization=self.org,
            user=member_2,
            membership_type=MembershipType.MEMBER,
            status=MembershipStatus.ACTIVE,
            joined_at=timezone.now(),
        )
        req2 = create_access_request(
            organization=self.org,
            requester=member_2,
            product=self.product,
        )

        # Approving member 2 must raise SeatLimitExceededError and remain pending
        with self.assertRaises(SeatLimitExceededError):
            approve_access_request(request_id=req2.id, approver=self.admin_user)

        req2.refresh_from_db()
        self.assertEqual(req2.status, AccessRequestStatus.PENDING)

    def test_membership_ended_auto_cancels_on_approval(self):
        """If requester membership ended before decision, request is auto-cancelled."""
        req = create_access_request(
            organization=self.org,
            requester=self.member_user,
            product=self.product,
        )

        # Suspend or terminate member's membership
        self.membership_member.status = MembershipStatus.SUSPENDED
        self.membership_member.save(update_fields=["status"])

        with self.assertRaises(MembershipIneligibleError):
            approve_access_request(request_id=req.id, approver=self.admin_user)

        req.refresh_from_db()
        self.assertEqual(req.status, AccessRequestStatus.CANCELLED)

    def test_deny_access_request_with_reason(self):
        """Approver denies request with mandatory reason between 1 and 500 chars."""
        req = create_access_request(
            organization=self.org,
            requester=self.member_user,
            product=self.product,
        )
        denied_req = deny_access_request(
            request_id=req.id,
            approver=self.admin_user,
            reason="Not eligible for this product at this stage.",
        )

        self.assertEqual(denied_req.status, AccessRequestStatus.DENIED)
        decision = AccessRequestDecision.objects.filter(request=denied_req).first()
        self.assertIsNotNone(decision)
        self.assertEqual(decision.decision, AccessRequestDecisionType.DENIED)
        self.assertEqual(decision.reason, "Not eligible for this product at this stage.")

        # Verify audit log
        audit = AuditLog.objects.filter(
            action=AuditAction.ACCESS_REQUEST_DENIED,
            target_id=denied_req.id,
        ).first()
        self.assertIsNotNone(audit)

    def test_deny_access_request_invalid_reason(self):
        """Denying without a valid reason raises InvalidReasonError."""
        req = create_access_request(
            organization=self.org,
            requester=self.member_user,
            product=self.product,
        )
        with self.assertRaises(InvalidReasonError):
            deny_access_request(request_id=req.id, approver=self.admin_user, reason="   ")

        with self.assertRaises(InvalidReasonError):
            deny_access_request(request_id=req.id, approver=self.admin_user, reason="x" * 501)

    def test_append_only_decision_history_enforced(self):
        """AccessRequestDecision records are append-only; update/delete is prohibited."""
        req = create_access_request(
            organization=self.org,
            requester=self.member_user,
            product=self.product,
        )
        approve_access_request(request_id=req.id, approver=self.admin_user)

        decision = AccessRequestDecision.objects.filter(request=req).first()
        decision.reason = "Modified reason"
        with self.assertRaises(ValidationError):
            decision.save()

        with self.assertRaises(ValidationError):
            decision.delete()

    def test_cancel_access_request_by_requester(self):
        """Requester can cancel their own pending request."""
        req = create_access_request(
            organization=self.org,
            requester=self.member_user,
            product=self.product,
        )
        cancelled = cancel_access_request(request_id=req.id, actor=self.member_user)
        self.assertEqual(cancelled.status, AccessRequestStatus.CANCELLED)

    def test_api_endpoints_flow(self):
        """End-to-end API test for Access Requests."""
        client = APIClient()
        client.force_authenticate(user=self.member_user)

        # 1. Create request
        create_url = "/api/v1/access-requests/"
        response = client.post(
            create_url,
            {
                "organization_id": str(self.org.id),
                "product_id": str(self.product.id),
                "reason": "Learning path request",
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        request_id = response.data["id"]

        # 2. List requests (Member sees own request)
        list_response = client.get(f"{create_url}?organization_id={self.org.id}")
        self.assertEqual(list_response.status_code, status.HTTP_200_OK)
        self.assertEqual(list_response.data["count"], 1)

        # 3. Approver logs in and approves
        client.force_authenticate(user=self.admin_user)
        approve_url = f"/api/v1/access-requests/{request_id}/approve/"
        approve_response = client.post(approve_url, {"reason": "Granted via API"}, format="json")
        self.assertEqual(approve_response.status_code, status.HTTP_200_OK)
        self.assertEqual(approve_response.data["status"], AccessRequestStatus.APPROVED)
        self.assertIsNotNone(approve_response.data["assignment_id"])

        # Check assignment exists
        self.assertTrue(
            UserProductAssignment.objects.filter(
                organization=self.org,
                user=self.member_user,
                product=self.product,
                status=AssignmentStatus.ACTIVE,
            ).exists()
        )
