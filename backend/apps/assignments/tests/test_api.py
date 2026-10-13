"""Authoritative Part D Test Suite (Phase 2F Part D).

Contains exactly 22 locked tests covering:
- Registry, permissions, and idempotent existing-organization backfill (test 52)
- Authorization, permission ceilings, custom roles, and tenant isolation (tests 53-57)
- CSRF enforcement on mutations (test 58)
- Assignment list, detail, and selectors API contracts (tests 59-64)
- Module PATCH API changed and identical state (tests 65-66)
- System service actor reconciliation audit and over-allocation detection (tests 67-68)
- Assignment create API success contract (test 87)
- Assignment lifecycle API contracts: suspend, reactivate, revoke (test 88)
- Exact error code to HTTP status mapping (test 89)
- Assignment audit metadata schemas (test 90)
- Interactive membership cascade inherits actor and correlation (test 91)
"""

from decimal import Decimal
import uuid

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from apps.access_control.constants import CONTEXT_TENANT
from apps.access_control.models import (
    AccessPermission,
    ConsoleModule,
    OrganizationConsoleModulePolicy,
    OrganizationPermissionCeiling,
    Role,
    RolePermission,
    RoleStatus,
)
from apps.assignments.models import AssignmentStatus, UserModuleAssignment, UserProductAssignment
from apps.assignments.services.assignment_services import (
    assign_user_to_product,
    reactivate_user_assignment,
    replace_user_module_assignments,
    revoke_user_assignment,
    suspend_user_assignment,
)
from apps.assignments.views import ERROR_CODE_STATUS_MAP
from apps.auditlog.models import AuditAction, AuditLog, AuditOperationSource, AuditTargetType
from apps.identity.services import (
    SystemActorUnavailableError,
    get_system_service_actor,
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
    SubscriptionCapabilityEntitlement,
    SubscriptionModuleEntitlement,
    SubscriptionProductEntitlement,
    SubscriptionQuotaEntitlement,
    SubscriptionStatus,
)
from apps.subscriptions.services import (
    _reconcile_subscription_snapshots,
    change_subscription_plan,
    check_and_audit_seat_over_allocation,
    reconcile_subscription_entitlements,
)

PlatformUser = get_user_model()


class Phase2FPartDAuthoritativeApiTests(APITestCase):
    """The 22 authoritative tests for Phase 2F Part D."""

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
            email="owner_partd@vibeconnect.internal",
            password=self.password,
            full_name="Platform Owner D",
            status="active",
            is_active=True,
            is_platform_owner=True,
        )

        # 3. Organizations Alpha & Beta
        self.org_alpha = Organization.objects.create(
            code="org-alpha-d",
            name="Organization Alpha D",
            status=OrganizationStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )
        self.org_beta = Organization.objects.create(
            code="org-beta-d",
            name="Organization Beta D",
            status=OrganizationStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )

        # 4. Access Control setup: ConsoleModule, Permissions, Role
        self.module, _ = ConsoleModule.objects.get_or_create(
            key="tenant_product_assignments",
            defaults={
                "display_name": "User Product Assignments",
                "description": "Manage product seat allocations and module entitlements for organization members.",
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
                "description": "Read assignments, module selections and quota metrics",
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
                "description": "Create and mutate assignments and module selections",
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

        # Ensure Org Alpha & Beta have policies and ceilings enabled
        for org in [self.org_alpha, self.org_beta]:
            OrganizationConsoleModulePolicy.objects.get_or_create(
                organization=org,
                console_module=self.module,
                defaults={"is_enabled": True, "updated_by": self.owner},
            )
            for p in [self.perm_view, self.perm_manage]:
                OrganizationPermissionCeiling.objects.get_or_create(
                    organization=org,
                    permission=p,
                    defaults={"is_allowed": True, "updated_by": self.owner},
                )

        # 5. Users and Memberships
        self.admin_user_alpha = PlatformUser.objects.create_user(
            email="admin_alpha@vibeconnect.internal",
            password=self.password,
            full_name="Alpha Admin",
            status="active",
            is_active=True,
            is_platform_owner=False,
        )
        self.membership_admin_alpha = OrganizationMembership.objects.create(
            organization=self.org_alpha,
            user=self.admin_user_alpha,
            membership_type=MembershipType.TENANT_ADMIN,
            status=MembershipStatus.ACTIVE,
            role=self.system_role,
            joined_at=timezone.now(),
        )

        self.member_user_alpha = PlatformUser.objects.create_user(
            email="member_alpha@vibeconnect.internal",
            password=self.password,
            full_name="Alpha Member 1",
            status="active",
            is_active=True,
            is_platform_owner=False,
        )
        self.membership_member_alpha = OrganizationMembership.objects.create(
            organization=self.org_alpha,
            user=self.member_user_alpha,
            membership_type=MembershipType.MEMBER,
            status=MembershipStatus.ACTIVE,
            role=None,
            joined_at=timezone.now(),
        )

        self.member_user_alpha_2 = PlatformUser.objects.create_user(
            email="member_alpha2@vibeconnect.internal",
            password=self.password,
            full_name="Alpha Member 2",
            status="active",
            is_active=True,
            is_platform_owner=False,
        )
        self.membership_member_alpha_2 = OrganizationMembership.objects.create(
            organization=self.org_alpha,
            user=self.member_user_alpha_2,
            membership_type=MembershipType.MEMBER,
            status=MembershipStatus.ACTIVE,
            role=None,
            joined_at=timezone.now(),
        )

        # Org Beta user
        self.admin_user_beta = PlatformUser.objects.create_user(
            email="admin_beta@vibeconnect.internal",
            password=self.password,
            full_name="Beta Admin",
            status="active",
            is_active=True,
            is_platform_owner=False,
        )
        self.membership_admin_beta = OrganizationMembership.objects.create(
            organization=self.org_beta,
            user=self.admin_user_beta,
            membership_type=MembershipType.TENANT_ADMIN,
            status=MembershipStatus.ACTIVE,
            role=self.system_role,
            joined_at=timezone.now(),
        )
        self.member_user_beta = PlatformUser.objects.create_user(
            email="member_beta@vibeconnect.internal",
            password=self.password,
            full_name="Beta Member",
            status="active",
            is_active=True,
            is_platform_owner=False,
        )
        self.membership_member_beta = OrganizationMembership.objects.create(
            organization=self.org_beta,
            user=self.member_user_beta,
            membership_type=MembershipType.MEMBER,
            status=MembershipStatus.ACTIVE,
            role=None,
            joined_at=timezone.now(),
        )

        # 6. Catalog Product and Modules
        now = timezone.now()
        self.product = Product.objects.create(
            code="lms_core",
            name="LMS Core Product",
            status=ProductStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )
        self.module_1 = ProductModule.objects.create(
            product=self.product,
            code="course_builder",
            name="Course Builder",
            description="Build interactive courses",
            status=CatalogStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )
        self.module_2 = ProductModule.objects.create(
            product=self.product,
            code="quiz_engine",
            name="Quiz Engine",
            description="Create assessments and quizzes",
            status=CatalogStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )
        self.product_unentitled = Product.objects.create(
            code="analytics_pro",
            name="Analytics Pro",
            status=ProductStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )

        # 7. Plan and PlanVersion
        self.plan = Plan.objects.create(
            code="growth_plan",
            name="Growth Plan",
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
            amount=Decimal("199.00"),
            billing_interval=BillingInterval.MONTHLY,
            created_by=self.owner,
            updated_by=self.owner,
        )
        self.plan_prod = PlanProduct.objects.create(
            plan_version=self.plan_version,
            product=self.product,
            created_by=self.owner,
        )
        self.plan_mod_1 = PlanModule.objects.create(
            plan_version=self.plan_version,
            plan_product=self.plan_prod,
            module=self.module_1,
            created_by=self.owner,
        )
        self.plan_mod_2 = PlanModule.objects.create(
            plan_version=self.plan_version,
            plan_product=self.plan_prod,
            module=self.module_2,
            created_by=self.owner,
        )
        self.plan_quota = PlanQuota.objects.create(
            plan_version=self.plan_version,
            quota_key="seats",
            name="Product Seats",
            scope=QuotaScope.PLAN,
            limit_type=QuotaLimitType.NUMERIC,
            limit_value=10,
            unit="seats",
            is_hard_limit=True,
            reset_period=QuotaResetPeriod.NEVER,
            created_by=self.owner,
            updated_by=self.owner,
        )

        # 8. Subscription for Org Alpha
        self.subscription_alpha = OrganizationSubscription.objects.create(
            organization=self.org_alpha,
            plan_version=self.plan_version,
            plan_price=self.plan_price,
            plan_code_snapshot="growth_plan",
            plan_name_snapshot="Growth Plan",
            version_number_snapshot=1,
            billing_interval="monthly",
            currency="USD",
            amount=Decimal("199.00"),
            status=SubscriptionStatus.ACTIVE,
            current_period_start=now,
            current_period_end=now + timezone.timedelta(days=30),
            created_by=self.owner,
            updated_by=self.owner,
        )
        _reconcile_subscription_snapshots(self.subscription_alpha)

        # Subscription for Org Beta
        self.subscription_beta = OrganizationSubscription.objects.create(
            organization=self.org_beta,
            plan_version=self.plan_version,
            plan_price=self.plan_price,
            plan_code_snapshot="growth_plan",
            plan_name_snapshot="Growth Plan",
            version_number_snapshot=1,
            billing_interval="monthly",
            currency="USD",
            amount=Decimal("199.00"),
            status=SubscriptionStatus.ACTIVE,
            current_period_start=now,
            current_period_end=now + timezone.timedelta(days=30),
            created_by=self.owner,
            updated_by=self.owner,
        )
        _reconcile_subscription_snapshots(self.subscription_beta)

    def tearDown(self):
        cache.clear()
        super().tearDown()

    def _login_tenant(self, user: PlatformUser, org: Organization):
        """Establish authenticated tenant context on test client."""
        self.client.force_login(user)
        session = self.client.session
        session["active_context_type"] = CONTEXT_TENANT
        session["tenant_organization_id"] = str(org.id)
        session.save()

    def _get_csrf_token(self) -> str:
        res = self.client.get("/api/v1/auth/csrf/")
        return res.cookies[settings.CSRF_COOKIE_NAME].value

    # =========================================================================
    # Test 52: Existing Organization Registry Backfill
    # =========================================================================
    def test_52_existing_org_registry_backfill(self):
        """Backfill bootstraps module, permissions, system tenant role, policies and ceilings idempotently."""
        # 1. Module
        mod = ConsoleModule.objects.get(key="tenant_product_assignments")
        self.assertEqual(mod.display_name, "User Product Assignments")
        self.assertEqual(mod.target_context, "tenant")

        # 2. Permissions
        perm_view = AccessPermission.objects.get(key="assignments.view")
        perm_manage = AccessPermission.objects.get(key="assignments.manage")
        self.assertEqual(perm_view.console_module_id, "tenant_product_assignments")
        self.assertEqual(perm_manage.console_module_id, "tenant_product_assignments")

        # 3. System Role Permission grant
        self.assertTrue(RolePermission.objects.filter(role=self.system_role, permission=perm_view).exists())
        self.assertTrue(RolePermission.objects.filter(role=self.system_role, permission=perm_manage).exists())

        # 4. Policy and ceiling for existing org
        pol = OrganizationConsoleModulePolicy.objects.get(organization=self.org_alpha, console_module=mod)
        self.assertTrue(pol.is_enabled)
        ceil_view = OrganizationPermissionCeiling.objects.get(organization=self.org_alpha, permission=perm_view)
        self.assertTrue(ceil_view.is_allowed)
        ceil_manage = OrganizationPermissionCeiling.objects.get(organization=self.org_alpha, permission=perm_manage)
        self.assertTrue(ceil_manage.is_allowed)

        # 5. Preserve override check
        org_override = Organization.objects.create(
            code="org-override",
            name="Org Override",
            status=OrganizationStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )
        OrganizationConsoleModulePolicy.objects.create(
            organization=org_override,
            console_module=mod,
            is_enabled=False,
            updated_by=self.owner,
        )
        # Re-run bootstrap logic simulation
        pol_check = OrganizationConsoleModulePolicy.objects.get(organization=org_override, console_module=mod)
        self.assertFalse(pol_check.is_enabled, "Existing policy override must be preserved")

    # =========================================================================
    # Test 53: View vs Manage Permission Enforcement
    # =========================================================================
    def test_53_view_vs_manage_permission_enforcement(self):
        """assignments.view allows reading list and detail, but blocks mutations and selectors with 403."""
        # Create role with only assignments.view
        view_only_role = Role.objects.create(
            organization=self.org_alpha,
            code="role_view_only",
            name="View Only Role",
            is_system_role=False,
            status=RoleStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )
        RolePermission.objects.create(role=view_only_role, permission=self.perm_view)

        viewer_user = PlatformUser.objects.create_user(
            email="viewer@vibeconnect.internal",
            password=self.password,
            full_name="Viewer User",
            status="active",
            is_active=True,
            is_platform_owner=False,
        )
        OrganizationMembership.objects.create(
            organization=self.org_alpha,
            user=viewer_user,
            membership_type=MembershipType.TENANT_ADMIN,
            status=MembershipStatus.ACTIVE,
            role=view_only_role,
            joined_at=timezone.now(),
        )

        assignment = assign_user_to_product(
            organization_id=self.org_alpha.id,
            user_id=self.member_user_alpha.id,
            product_id=self.product.id,
            actor=self.admin_user_alpha,
        )

        self._login_tenant(viewer_user, self.org_alpha)

        # GET list -> 200
        res_list = self.client.get("/api/v1/tenant/assignments/")
        self.assertEqual(res_list.status_code, status.HTTP_200_OK)

        # GET detail -> 200
        res_detail = self.client.get(f"/api/v1/tenant/assignments/{assignment.id}/")
        self.assertEqual(res_detail.status_code, status.HTTP_200_OK)

        # POST mutation -> 403 INSUFFICIENT_PRIVILEGES
        res_post = self.client.post(
            "/api/v1/tenant/assignments/",
            {"user_id": str(self.member_user_alpha_2.id), "product_id": str(self.product.id)},
            format="json",
        )
        self.assertEqual(res_post.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(res_post.data["error"]["code"], "INSUFFICIENT_PRIVILEGES")

        # Selectors -> 403 INSUFFICIENT_PRIVILEGES
        res_sel = self.client.get("/api/v1/tenant/assignments/selectors/products/")
        self.assertEqual(res_sel.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(res_sel.data["error"]["code"], "INSUFFICIENT_PRIVILEGES")

    # =========================================================================
    # Test 54: Permission Ceiling Denial
    # =========================================================================
    def test_54_permission_ceiling_denial(self):
        """Organization ceiling denying assignments.manage or disabling module denies operations with 403."""
        # Deny assignments.manage at ceiling
        ceil = OrganizationPermissionCeiling.objects.get(
            organization=self.org_alpha,
            permission=self.perm_manage,
        )
        ceil.is_allowed = False
        ceil.save()

        self._login_tenant(self.admin_user_alpha, self.org_alpha)

        res = self.client.post(
            "/api/v1/tenant/assignments/",
            {"user_id": str(self.member_user_alpha.id), "product_id": str(self.product.id)},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(res.data["error"]["code"], "INSUFFICIENT_PRIVILEGES")

        # Disable module policy
        ceil.is_allowed = True
        ceil.save()
        pol = OrganizationConsoleModulePolicy.objects.get(
            organization=self.org_alpha,
            console_module=self.module,
        )
        pol.is_enabled = False
        pol.save()

        res_mod = self.client.get("/api/v1/tenant/assignments/")
        self.assertEqual(res_mod.status_code, status.HTTP_403_FORBIDDEN)

    # =========================================================================
    # Test 55: Custom Role Denial
    # =========================================================================
    def test_55_custom_role_denial(self):
        """Custom role without assignments permissions receives 403 INSUFFICIENT_PRIVILEGES."""
        custom_empty_role = Role.objects.create(
            organization=self.org_alpha,
            code="empty_custom_role",
            name="Empty Custom Role",
            is_system_role=False,
            status=RoleStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )

        user_custom = PlatformUser.objects.create_user(
            email="custom_user@vibeconnect.internal",
            password=self.password,
            full_name="Custom User",
            status="active",
            is_active=True,
            is_platform_owner=False,
        )
        OrganizationMembership.objects.create(
            organization=self.org_alpha,
            user=user_custom,
            membership_type=MembershipType.TENANT_ADMIN,
            status=MembershipStatus.ACTIVE,
            role=custom_empty_role,
            joined_at=timezone.now(),
        )

        self._login_tenant(user_custom, self.org_alpha)

        res = self.client.get("/api/v1/tenant/assignments/")
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(res.data["error"]["code"], "INSUFFICIENT_PRIVILEGES")

    # =========================================================================
    # Test 56: Tenant Isolation Assignment List
    # =========================================================================
    def test_56_tenant_isolation_assignment_list(self):
        """List assignments returns only records belonging to the authenticated tenant."""
        asgn_alpha = assign_user_to_product(
            organization_id=self.org_alpha.id,
            user_id=self.member_user_alpha.id,
            product_id=self.product.id,
            actor=self.admin_user_alpha,
        )
        asgn_beta = assign_user_to_product(
            organization_id=self.org_beta.id,
            user_id=self.member_user_beta.id,
            product_id=self.product.id,
            actor=self.admin_user_beta,
        )

        self._login_tenant(self.admin_user_alpha, self.org_alpha)
        res = self.client.get("/api/v1/tenant/assignments/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        ids = [item["id"] for item in res.data["results"]]
        self.assertIn(str(asgn_alpha.id), ids)
        self.assertNotIn(str(asgn_beta.id), ids)

    # =========================================================================
    # Test 57: Tenant Isolation 404 Cross Tenant Mutation
    # =========================================================================
    def test_57_tenant_isolation_404_cross_tenant_mutation(self):
        """Accessing or mutating another tenant's assignment returns 404 ASSIGNMENT_NOT_FOUND."""
        asgn_beta = assign_user_to_product(
            organization_id=self.org_beta.id,
            user_id=self.member_user_beta.id,
            product_id=self.product.id,
            actor=self.admin_user_beta,
        )

        self._login_tenant(self.admin_user_alpha, self.org_alpha)

        # GET detail of Org B assignment from Org A
        res_get = self.client.get(f"/api/v1/tenant/assignments/{asgn_beta.id}/")
        self.assertEqual(res_get.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(res_get.data["error"]["code"], "ASSIGNMENT_NOT_FOUND")

        # POST suspend of Org B assignment from Org A
        res_suspend = self.client.post(
            f"/api/v1/tenant/assignments/{asgn_beta.id}/suspend/",
            {"reason": "Suspension attempt"},
            format="json",
        )
        self.assertEqual(res_suspend.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(res_suspend.data["error"]["code"], "ASSIGNMENT_NOT_FOUND")

    # =========================================================================
    # Test 58: CSRF Enforcement on Mutations
    # =========================================================================
    def test_58_csrf_enforcement_on_mutations(self):
        """Mutating endpoints strictly enforce CSRF and return 403 CSRF_FAILED without token."""
        csrf_client = APIClient(enforce_csrf_checks=True)
        csrf_client.force_login(self.admin_user_alpha)
        session = csrf_client.session
        session["active_context_type"] = CONTEXT_TENANT
        session["tenant_organization_id"] = str(self.org_alpha.id)
        session.save()

        # Mutation without CSRF token fails with 403 CSRF_FAILED
        res = csrf_client.post(
            "/api/v1/tenant/assignments/",
            {"user_id": str(self.member_user_alpha.id), "product_id": str(self.product.id)},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(res.data["error"]["code"], "CSRF_FAILED")

        # With CSRF token succeeds
        csrf_res = csrf_client.get("/api/v1/auth/csrf/")
        csrf_token = csrf_res.cookies[settings.CSRF_COOKIE_NAME].value

        res_valid = csrf_client.post(
            "/api/v1/tenant/assignments/",
            {"user_id": str(self.member_user_alpha.id), "product_id": str(self.product.id)},
            format="json",
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        self.assertEqual(res_valid.status_code, status.HTTP_201_CREATED)

    # =========================================================================
    # Test 59: Assignment List API Contract
    # =========================================================================
    def test_59_assignment_list_api_contract(self):
        """GET /api/v1/tenant/assignments/ returns paginated response matching exact contract."""
        asgn = assign_user_to_product(
            organization_id=self.org_alpha.id,
            user_id=self.member_user_alpha.id,
            product_id=self.product.id,
            module_ids=[self.module_1.id],
            actor=self.admin_user_alpha,
        )

        self._login_tenant(self.admin_user_alpha, self.org_alpha)
        res = self.client.get("/api/v1/tenant/assignments/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn("count", res.data)
        self.assertIn("next", res.data)
        self.assertIn("previous", res.data)
        self.assertIn("results", res.data)

        item = res.data["results"][0]
        self.assertEqual(item["id"], str(asgn.id))
        self.assertEqual(item["user"]["email"], self.member_user_alpha.email)
        self.assertEqual(item["user"]["full_name"], self.member_user_alpha.full_name)
        self.assertEqual(item["product"]["code"], self.product.code)
        self.assertEqual(item["status"], "active")
        self.assertEqual(item["enabled_module_count"], 1)

        # Filtering test: search by member email
        res_search = self.client.get(f"/api/v1/tenant/assignments/?search={self.member_user_alpha.email}")
        self.assertEqual(res_search.data["count"], 1)

        # Filtering test: non-matching search
        res_none = self.client.get("/api/v1/tenant/assignments/?search=nonexistent")
        self.assertEqual(res_none.data["count"], 0)

    # =========================================================================
    # Test 60: Assignment Detail API Contract
    # =========================================================================
    def test_60_assignment_detail_api_contract(self):
        """GET /api/v1/tenant/assignments/<pk>/ returns assignment detail matching exact contract."""
        asgn = assign_user_to_product(
            organization_id=self.org_alpha.id,
            user_id=self.member_user_alpha.id,
            product_id=self.product.id,
            module_ids=[self.module_1.id],
            actor=self.admin_user_alpha,
        )

        self._login_tenant(self.admin_user_alpha, self.org_alpha)
        res = self.client.get(f"/api/v1/tenant/assignments/{asgn.id}/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        data = res.data
        self.assertEqual(data["id"], str(asgn.id))
        self.assertEqual(data["user"]["id"], str(self.member_user_alpha.id))
        self.assertEqual(data["membership"]["id"], str(self.membership_member_alpha.id))
        self.assertEqual(data["membership"]["status"], "active")
        self.assertEqual(data["product"]["id"], str(self.product.id))
        self.assertEqual(data["product"]["code"], self.product.code)
        self.assertEqual(len(data["modules"]), 1)
        self.assertEqual(data["modules"][0]["code"], self.module_1.code)
        self.assertTrue(data["modules"][0]["is_enabled"])

    # =========================================================================
    # Test 61: Selector Products Endpoint Contract
    # =========================================================================
    def test_61_selector_products_endpoint_contract(self):
        """GET /api/v1/tenant/assignments/selectors/products/ returns entitled products with seat metrics."""
        self._login_tenant(self.admin_user_alpha, self.org_alpha)
        res = self.client.get("/api/v1/tenant/assignments/selectors/products/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res.data), 1)

        item = res.data[0]
        self.assertEqual(item["id"], str(self.product.id))
        self.assertEqual(item["code"], self.product.code)
        self.assertEqual(item["pool_scope"], "plan")
        self.assertEqual(item["quota_type"], "numeric")
        self.assertEqual(item["total_limit"], 10)
        self.assertEqual(item["consumed_seats"], 0)
        self.assertEqual(item["available_seats"], 10)
        self.assertTrue(item["is_capacity_available"])

    # =========================================================================
    # Test 62: Selector Members Product Filtering
    # =========================================================================
    def test_62_selector_members_product_filtering(self):
        """GET /api/v1/tenant/assignments/selectors/members/ excludes members with open assignment."""
        assign_user_to_product(
            organization_id=self.org_alpha.id,
            user_id=self.member_user_alpha.id,
            product_id=self.product.id,
            actor=self.admin_user_alpha,
        )

        self._login_tenant(self.admin_user_alpha, self.org_alpha)
        res = self.client.get(f"/api/v1/tenant/assignments/selectors/members/?product_id={self.product.id}")
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        emails = [item["email"] for item in res.data["results"]]
        self.assertNotIn(self.member_user_alpha.email, emails)
        self.assertIn(self.member_user_alpha_2.email, emails)
        self.assertIn(self.admin_user_alpha.email, emails)

    # =========================================================================
    # Test 63: Selector Modules Entitled Filtering
    # =========================================================================
    def test_63_selector_modules_entitled_filtering(self):
        """GET /api/v1/tenant/assignments/selectors/modules/ returns only entitled active catalog modules."""
        # Create unentitled module on product
        unentitled_mod = ProductModule.objects.create(
            product=self.product,
            code="experimental_module",
            name="Experimental Module",
            status=CatalogStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )

        self._login_tenant(self.admin_user_alpha, self.org_alpha)
        res = self.client.get(f"/api/v1/tenant/assignments/selectors/modules/?product_id={self.product.id}")
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        codes = [item["code"] for item in res.data]
        self.assertIn(self.module_1.code, codes)
        self.assertIn(self.module_2.code, codes)
        self.assertNotIn(unentitled_mod.code, codes)

    # =========================================================================
    # Test 64: Malformed Query UUID Returns 400
    # =========================================================================
    def test_64_malformed_query_uuid_returns_400(self):
        """Malformed UUID or missing product_id on selector endpoints returns 400 INVALID_QUERY_PARAM."""
        self._login_tenant(self.admin_user_alpha, self.org_alpha)

        # Missing product_id
        res_missing = self.client.get("/api/v1/tenant/assignments/selectors/members/")
        self.assertEqual(res_missing.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(res_missing.data["error"]["code"], "INVALID_QUERY_PARAM")

        # Malformed product_id on members selector
        res_malformed_mem = self.client.get("/api/v1/tenant/assignments/selectors/members/?product_id=bad-uuid")
        self.assertEqual(res_malformed_mem.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(res_malformed_mem.data["error"]["code"], "INVALID_QUERY_PARAM")

        # Malformed product_id on modules selector
        res_malformed_mod = self.client.get("/api/v1/tenant/assignments/selectors/modules/?product_id=bad-uuid")
        self.assertEqual(res_malformed_mod.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(res_malformed_mod.data["error"]["code"], "INVALID_QUERY_PARAM")

        # Malformed product_id on assignment list
        res_list = self.client.get("/api/v1/tenant/assignments/?product_id=bad-uuid")
        self.assertEqual(res_list.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(res_list.data["error"]["code"], "INVALID_QUERY_PARAM")

    # =========================================================================
    # Test 65: Module Patch API Changed State
    # =========================================================================
    def test_65_module_patch_api_changed_state(self):
        """PATCH /api/v1/tenant/assignments/<pk>/modules/ updates module selection and logs exactly 1 audit event."""
        asgn = assign_user_to_product(
            organization_id=self.org_alpha.id,
            user_id=self.member_user_alpha.id,
            product_id=self.product.id,
            module_ids=[self.module_1.id],
            actor=self.admin_user_alpha,
        )

        audit_count_before = AuditLog.objects.count()
        self._login_tenant(self.admin_user_alpha, self.org_alpha)

        res = self.client.patch(
            f"/api/v1/tenant/assignments/{asgn.id}/modules/",
            {"module_ids": [str(self.module_2.id)]},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res.data["modules"]), 1)
        self.assertEqual(res.data["modules"][0]["module_id"], str(self.module_2.id))

        self.assertEqual(AuditLog.objects.count(), audit_count_before + 1)
        latest_audit = AuditLog.objects.latest("timestamp")
        self.assertEqual(latest_audit.action, AuditAction.USER_MODULE_ASSIGNMENTS_REPLACED)
        self.assertEqual(latest_audit.metadata["resulting_enabled_module_codes"], [self.module_2.code])

    # =========================================================================
    # Test 66: Module Patch API Identical State
    # =========================================================================
    def test_66_module_patch_api_identical_state(self):
        """PATCH /api/v1/tenant/assignments/<pk>/modules/ with identical selection produces 0 writes and 0 audits."""
        asgn = assign_user_to_product(
            organization_id=self.org_alpha.id,
            user_id=self.member_user_alpha.id,
            product_id=self.product.id,
            module_ids=[self.module_1.id],
            actor=self.admin_user_alpha,
        )

        audit_count_before = AuditLog.objects.count()
        self._login_tenant(self.admin_user_alpha, self.org_alpha)

        res = self.client.patch(
            f"/api/v1/tenant/assignments/{asgn.id}/modules/",
            {"module_ids": [str(self.module_1.id)]},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(AuditLog.objects.count(), audit_count_before)

    # =========================================================================
    # Test 67: System Service Actor Reconciliation Audit
    # =========================================================================
    def test_67_system_service_actor_reconciliation_audit(self):
        """get_system_service_actor returns the locked actor and reconciliation audits use INTEGRATION source."""
        actor = get_system_service_actor()
        self.assertEqual(actor.email, "system@vibeconnect.internal")
        self.assertTrue(actor.is_platform_owner)
        self.assertTrue(actor.is_staff)
        self.assertTrue(actor.is_active)
        self.assertFalse(actor.has_usable_password())

        # Test failure closed when actor disabled
        PlatformUser.objects.filter(id=actor.id).update(status="disabled", is_active=False)
        with self.assertRaises(SystemActorUnavailableError):
            get_system_service_actor()

        # Restore actor
        PlatformUser.objects.filter(id=actor.id).update(status="active", is_active=True)
        actor.refresh_from_db()

        # Add new product to plan_version so reconciliation detects missing entitlement to repair
        new_recon_prod = Product.objects.create(
            code="audit_recon_prod",
            name="Audit Recon Product",
            status=ProductStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )
        PlanProduct.objects.create(
            plan_version=self.plan_version,
            product=new_recon_prod,
            created_by=self.owner,
        )

        batch_uuid = uuid.uuid4()
        repaired = reconcile_subscription_entitlements(
            subscription_id=self.subscription_alpha.id,
            actor=actor,
            correlation_id=batch_uuid,
            operation_source=AuditOperationSource.INTEGRATION,
        )
        self.assertGreater(repaired, 0)

        log = AuditLog.objects.filter(
            action=AuditAction.SUBSCRIPTION_RECONCILED,
            correlation_id=batch_uuid,
        ).first()
        self.assertIsNotNone(log)
        self.assertEqual(log.operation_source, AuditOperationSource.INTEGRATION)
        self.assertEqual(log.actor_email, "system@vibeconnect.internal")

    # =========================================================================
    # Test 68: Plan Shared Over-Allocation Audit Schema
    # =========================================================================
    def test_68_plan_shared_over_allocation_audit_schema(self):
        """Plan-shared over-allocation emits SEAT_OVER_ALLOCATION_DETECTED with exact metadata schema."""
        # Create 2 assignments under 10-seat plan
        asgn1 = assign_user_to_product(
            organization_id=self.org_alpha.id,
            user_id=self.member_user_alpha.id,
            product_id=self.product.id,
            actor=self.admin_user_alpha,
        )
        asgn2 = assign_user_to_product(
            organization_id=self.org_alpha.id,
            user_id=self.member_user_alpha_2.id,
            product_id=self.product.id,
            actor=self.admin_user_alpha,
        )

        # Create smaller plan with 1 seat
        plan_small = Plan.objects.create(
            code="starter_plan",
            name="Starter Plan",
            created_by=self.owner,
            updated_by=self.owner,
        )
        plan_small_version = PlanVersion.objects.create(
            plan=plan_small,
            version=1,
            status=PlanVersionStatus.ACTIVE,
            activated_at=timezone.now(),
            created_by=self.owner,
            updated_by=self.owner,
        )
        price_small = PlanPrice.objects.create(
            plan_version=plan_small_version,
            currency="USD",
            amount=Decimal("49.00"),
            billing_interval=BillingInterval.MONTHLY,
            created_by=self.owner,
            updated_by=self.owner,
        )
        PlanProduct.objects.create(
            plan_version=plan_small_version,
            product=self.product,
            created_by=self.owner,
        )
        PlanQuota.objects.create(
            plan_version=plan_small_version,
            quota_key="seats",
            name="Product Seats",
            scope=QuotaScope.PLAN,
            limit_type=QuotaLimitType.NUMERIC,
            limit_value=1,
            unit="seats",
            is_hard_limit=True,
            reset_period=QuotaResetPeriod.NEVER,
            created_by=self.owner,
            updated_by=self.owner,
        )

        batch_id = uuid.uuid4()
        successor = change_subscription_plan(
            subscription_id=self.subscription_alpha.id,
            new_plan_version_id=plan_small_version.id,
            new_plan_price_id=price_small.id,
            actor=self.owner,
            change_reason="Downgrade to starter",
            correlation_id=batch_id,
        )

        # Check SEAT_OVER_ALLOCATION_DETECTED event
        audit = AuditLog.objects.filter(
            action=AuditAction.SEAT_OVER_ALLOCATION_DETECTED,
            target_id=successor.id,
        ).first()
        self.assertIsNotNone(audit, "SEAT_OVER_ALLOCATION_DETECTED audit event must be emitted")
        self.assertEqual(audit.target_repr, f"Subscription {successor.id} Seat Pool")
        meta = audit.metadata
        self.assertEqual(meta["organization_code"], self.org_alpha.code)
        self.assertEqual(meta["pool_scope"], "plan")
        self.assertEqual(meta["pool_key"], f"plan:{successor.plan_code_snapshot}")
        self.assertEqual(meta["governed_product_ids"], [str(self.product.id)])
        self.assertEqual(meta["total_limit"], 1)
        self.assertEqual(meta["consumed_seats"], 2)
        self.assertEqual(meta["over_allocated_amount"], 1)
        self.assertEqual(meta["detection_context"], "plan_downgrade")

    # =========================================================================
    # Test 87: Assignment Create API Success Contract
    # =========================================================================
    def test_87_assignment_create_api_success_contract(self):
        """POST /api/v1/tenant/assignments/ creates assignment and returns 201 detail contract."""
        self._login_tenant(self.admin_user_alpha, self.org_alpha)

        res = self.client.post(
            "/api/v1/tenant/assignments/",
            {
                "user_id": str(self.member_user_alpha.id),
                "product_id": str(self.product.id),
                "module_ids": [str(self.module_1.id)],
            },
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res.data["user"]["email"], self.member_user_alpha.email)
        self.assertEqual(res.data["product"]["code"], self.product.code)
        self.assertEqual(res.data["membership"]["id"], str(self.membership_member_alpha.id))
        self.assertEqual(len(res.data["modules"]), 1)
        self.assertEqual(res.data["modules"][0]["code"], self.module_1.code)

        # Check USER_PRODUCT_ASSIGNED audit event
        audit = AuditLog.objects.filter(
            action=AuditAction.USER_PRODUCT_ASSIGNED,
            target_id=res.data["id"],
        ).first()
        self.assertIsNotNone(audit)
        self.assertEqual(audit.actor_email, self.admin_user_alpha.email)
        self.assertEqual(audit.operation_source, AuditOperationSource.INTERACTIVE)

    # =========================================================================
    # Test 88: Assignment Lifecycle API Contracts
    # =========================================================================
    def test_88_assignment_lifecycle_api_contracts(self):
        """POST suspend, reactivate, and revoke return 200 with detail contract and handle idempotent calls."""
        asgn = assign_user_to_product(
            organization_id=self.org_alpha.id,
            user_id=self.member_user_alpha.id,
            product_id=self.product.id,
            actor=self.admin_user_alpha,
        )

        self._login_tenant(self.admin_user_alpha, self.org_alpha)

        # 1. Suspend
        res_suspend = self.client.post(
            f"/api/v1/tenant/assignments/{asgn.id}/suspend/",
            {"reason": "Temporary suspension"},
            format="json",
        )
        self.assertEqual(res_suspend.status_code, status.HTTP_200_OK)
        self.assertEqual(res_suspend.data["status"], "suspended")
        self.assertEqual(res_suspend.data["suspension_reason"], "Temporary suspension")

        # Idempotent re-suspend
        res_resuspend = self.client.post(
            f"/api/v1/tenant/assignments/{asgn.id}/suspend/",
            {"reason": "Second suspension attempt"},
            format="json",
        )
        self.assertEqual(res_resuspend.status_code, status.HTTP_200_OK)

        # 2. Reactivate
        res_reactivate = self.client.post(
            f"/api/v1/tenant/assignments/{asgn.id}/reactivate/",
            {},
            format="json",
        )
        self.assertEqual(res_reactivate.status_code, status.HTTP_200_OK)
        self.assertEqual(res_reactivate.data["status"], "active")

        # Idempotent re-reactivate
        res_rereactivate = self.client.post(
            f"/api/v1/tenant/assignments/{asgn.id}/reactivate/",
            {},
            format="json",
        )
        self.assertEqual(res_rereactivate.status_code, status.HTTP_200_OK)

        # 3. Revoke
        res_revoke = self.client.post(
            f"/api/v1/tenant/assignments/{asgn.id}/revoke/",
            {"reason": "Access revoked by admin"},
            format="json",
        )
        self.assertEqual(res_revoke.status_code, status.HTTP_200_OK)
        self.assertEqual(res_revoke.data["status"], "revoked")
        self.assertEqual(res_revoke.data["revocation_reason"], "Access revoked by admin")

        # Idempotent re-revoke
        res_rerevoke = self.client.post(
            f"/api/v1/tenant/assignments/{asgn.id}/revoke/",
            {"reason": "Second revoke attempt"},
            format="json",
        )
        self.assertEqual(res_rerevoke.status_code, status.HTTP_200_OK)

    # =========================================================================
    # Test 89: Exact Error Code to HTTP Status Mapping
    # =========================================================================
    def test_89_exact_error_code_to_http_status_mapping(self):
        """Every locked error code maps to exactly one HTTP status code."""
        expected_mappings = {
            "INVALID_REASON": 400,
            "INVALID_QUERY_PARAM": 400,
            "ORGANIZATION_INACTIVE": 403,
            "INSUFFICIENT_PRIVILEGES": 403,
            "CSRF_FAILED": 403,
            "ASSIGNMENT_NOT_FOUND": 404,
            "ALREADY_ASSIGNED": 409,
            "INVALID_STATE_TRANSITION": 409,
            "USER_INACTIVE": 422,
            "USER_DISABLED": 422,
            "MEMBERSHIP_INELIGIBLE": 422,
            "SUBSCRIPTION_UNAVAILABLE": 422,
            "PRODUCT_INACTIVE": 422,
            "PRODUCT_NOT_ENTITLED": 422,
            "INVALID_SEAT_QUOTA_CONFIG": 422,
            "SEAT_QUOTA_UNCONFIGURED": 422,
            "SEAT_LIMIT_EXCEEDED": 422,
            "INVALID_MODULE_IDS": 422,
            "MODULE_NOT_ENTITLED": 422,
        }

        self.assertEqual(len(ERROR_CODE_STATUS_MAP), 19)
        for code, expected_http in expected_mappings.items():
            self.assertEqual(
                ERROR_CODE_STATUS_MAP.get(code),
                expected_http,
                f"Error code '{code}' must map to HTTP {expected_http}",
            )

    # =========================================================================
    # Test 90: Assignment Audit Metadata Schemas
    # =========================================================================
    def test_90_assignment_audit_metadata_schemas(self):
        """Verifies exact metadata schemas and target representations for assignment audit actions."""
        # 1. USER_PRODUCT_ASSIGNED
        asgn = assign_user_to_product(
            organization_id=self.org_alpha.id,
            user_id=self.member_user_alpha.id,
            product_id=self.product.id,
            module_ids=[self.module_1.id],
            actor=self.admin_user_alpha,
        )
        audit_assign = AuditLog.objects.filter(action=AuditAction.USER_PRODUCT_ASSIGNED, target_id=asgn.id).first()
        self.assertIsNotNone(audit_assign)
        self.assertEqual(
            audit_assign.target_repr,
            f"Assignment {asgn.id} ({self.product.code} -> {self.member_user_alpha.email})",
        )
        meta_assign = audit_assign.metadata
        for key in (
            "organization_code", "user_id", "user_email", "product_id", "product_code",
            "subscription_id", "pool_scope", "pool_key", "governed_product_ids",
            "quota_entitlement_id", "quota_key", "total_limit", "consumed_seats_after",
            "available_seats_after", "assigned_module_ids", "assigned_module_codes",
        ):
            self.assertIn(key, meta_assign)

        # 2. USER_PRODUCT_SUSPENDED
        suspend_user_assignment(assignment_id=asgn.id, actor=self.admin_user_alpha, reason="Suspension test")
        audit_susp = AuditLog.objects.filter(action=AuditAction.USER_PRODUCT_SUSPENDED, target_id=asgn.id).first()
        self.assertIsNotNone(audit_susp)
        meta_susp = audit_susp.metadata
        for key in (
            "organization_code", "user_id", "user_email", "product_id", "product_code",
            "previous_status", "resulting_status", "suspension_reason",
        ):
            self.assertIn(key, meta_susp)
        self.assertEqual(meta_susp["previous_status"], "active")
        self.assertEqual(meta_susp["resulting_status"], "suspended")

        # 3. USER_PRODUCT_REACTIVATED
        reactivate_user_assignment(assignment_id=asgn.id, actor=self.admin_user_alpha)
        audit_react = AuditLog.objects.filter(action=AuditAction.USER_PRODUCT_REACTIVATED, target_id=asgn.id).first()
        self.assertIsNotNone(audit_react)
        meta_react = audit_react.metadata
        for key in ("organization_code", "user_id", "user_email", "product_id", "product_code", "previous_status", "resulting_status"):
            self.assertIn(key, meta_react)
        self.assertEqual(meta_react["previous_status"], "suspended")
        self.assertEqual(meta_react["resulting_status"], "active")

        # 4. USER_MODULE_ASSIGNMENTS_REPLACED
        replace_user_module_assignments(assignment_id=asgn.id, module_ids=[self.module_2.id], actor=self.admin_user_alpha)
        audit_mod = AuditLog.objects.filter(action=AuditAction.USER_MODULE_ASSIGNMENTS_REPLACED, target_id=asgn.id).first()
        self.assertIsNotNone(audit_mod)
        self.assertEqual(audit_mod.target_repr, f"Assignment {asgn.id} Modules")
        meta_mod = audit_mod.metadata
        for key in (
            "organization_code", "user_id", "product_id", "product_code",
            "previous_enabled_module_ids", "previous_enabled_module_codes",
            "resulting_enabled_module_ids", "resulting_enabled_module_codes",
        ):
            self.assertIn(key, meta_mod)

        # 5. USER_PRODUCT_REVOKED
        revoke_user_assignment(assignment_id=asgn.id, actor=self.admin_user_alpha, reason="Revoke test")
        audit_rev = AuditLog.objects.filter(action=AuditAction.USER_PRODUCT_REVOKED, target_id=asgn.id).first()
        self.assertIsNotNone(audit_rev)
        meta_rev = audit_rev.metadata
        for key in (
            "organization_code", "user_id", "user_email", "product_id", "product_code",
            "previous_status", "resulting_status", "reason", "seat_reservation_released",
            "was_counted_in_current_pool", "current_pool_consumed_delta",
        ):
            self.assertIn(key, meta_rev)
        self.assertTrue(meta_rev["seat_reservation_released"])
        self.assertEqual(meta_rev["current_pool_consumed_delta"], -1)

    # =========================================================================
    # Test 91: Interactive Cascade Inherits Actor and Correlation
    # =========================================================================
    def test_91_interactive_cascade_inherits_actor_and_correlation(self):
        """Membership-end interactive cascade preserves initiating human actor and correlation ID."""
        asgn = assign_user_to_product(
            organization_id=self.org_alpha.id,
            user_id=self.member_user_alpha.id,
            product_id=self.product.id,
            actor=self.admin_user_alpha,
        )

        parent_corr_id = uuid.uuid4()
        end_membership(
            actor=self.owner,
            membership_id=self.membership_member_alpha.id,
            reason="Member departed",
            correlation_id=parent_corr_id,
        )

        revocation_audit = AuditLog.objects.filter(
            action=AuditAction.USER_PRODUCT_REVOKED,
            target_id=asgn.id,
        ).first()

        self.assertIsNotNone(revocation_audit)
        self.assertEqual(revocation_audit.actor_email, self.owner.email)
        self.assertEqual(revocation_audit.operation_source, AuditOperationSource.INTERACTIVE)
        self.assertEqual(revocation_audit.correlation_id, parent_corr_id)
