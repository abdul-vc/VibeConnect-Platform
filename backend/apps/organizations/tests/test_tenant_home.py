"""Authoritative Tests for Tenant Admin Console Shell & App Launcher (Phase 2G Part A).

Covers:
1. Multi-product tenant with full hierarchy (modules -> features -> capabilities).
2. Zero-product tenant (active membership but zero product assignments -> empty array, 200 OK).
3. Suspended-subscription tenant with active direct grant (direct grant product is accessible).
4. Ceiling-restricted tenant (permission ceiling revocation excludes console module).
5. User without active membership in active context (403 Forbidden).
6. Multi-tenant isolation (cross-tenant data never leaks).
7. Unauthenticated and non-tenant context rejection.
8. Effective access service layer unit test.
"""

from decimal import Decimal
import uuid

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

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
from apps.assignments.constants import AccessState, DenialCode, ModuleState
from apps.assignments.models import AssignmentStatus, UserModuleAssignment, UserProductAssignment
from apps.assignments.services.effective_access import compute_user_tenant_effective_access
from apps.entitlements.models import EntitlementStatus, OrganizationProductEntitlement
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

PlatformUser = get_user_model()


class TenantHomeApiTests(APITestCase):
    """Test suite for /api/v1/tenant/home/ and effective access computation."""

    def setUp(self):
        super().setUp()
        cache.clear()
        self.password = "SecurePassword123!"

        # 1. Platform Owner
        self.owner = PlatformUser.objects.create_user(
            email="owner@vibeconnect.internal",
            password=self.password,
            full_name="Platform Owner",
            status="active",
            is_active=True,
            is_platform_owner=True,
        )

        # 2. Organizations
        self.org_alpha = Organization.objects.create(
            name="Alpha Corp",
            code="alpha-corp",
            status=OrganizationStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )
        self.org_beta = Organization.objects.create(
            name="Beta Corp",
            code="beta-corp",
            status=OrganizationStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )

        # 3. Console Modules & Permissions
        self.mod_landing, _ = ConsoleModule.objects.get_or_create(
            key="tenant_landing",
            defaults={
                "display_name": "Tenant Console",
                "description": "Core tenant landing overview.",
                "target_context": "tenant",
                "is_core": True,
                "is_active": True,
                "sort_order": 10,
            },
        )
        self.mod_roles, _ = ConsoleModule.objects.get_or_create(
            key="tenant_roles",
            defaults={
                "display_name": "Roles & Permissions",
                "description": "Role management workspace.",
                "target_context": "tenant",
                "is_core": False,
                "is_active": True,
                "sort_order": 20,
            },
        )
        self.mod_assignments, _ = ConsoleModule.objects.get_or_create(
            key="tenant_product_assignments",
            defaults={
                "display_name": "User Product Assignments",
                "description": "Assignment workspace.",
                "target_context": "tenant",
                "is_core": False,
                "is_active": True,
                "sort_order": 30,
            },
        )

        self.perm_roles_view, _ = AccessPermission.objects.get_or_create(
            key="roles.view",
            defaults={
                "console_module": self.mod_roles,
                "display_name": "View Roles",
                "description": "View roles",
                "category": "roles",
                "is_active": True,
                "sort_order": 1,
            },
        )
        self.perm_assignments_view, _ = AccessPermission.objects.get_or_create(
            key="assignments.view",
            defaults={
                "console_module": self.mod_assignments,
                "display_name": "View Assignments",
                "description": "View assignments",
                "category": "assignments",
                "is_active": True,
                "sort_order": 1,
            },
        )

        # 4. System Tenant Admin Role
        self.sys_role, _ = Role.objects.get_or_create(
            code="system_tenant_admin",
            defaults={
                "name": "System Tenant Administrator",
                "is_system_role": True,
                "status": RoleStatus.ACTIVE,
                "organization": None,
            },
        )
        RolePermission.objects.get_or_create(role=self.sys_role, permission=self.perm_roles_view)
        RolePermission.objects.get_or_create(role=self.sys_role, permission=self.perm_assignments_view)

        # 5. Policies & Ceilings for Org Alpha
        OrganizationConsoleModulePolicy.objects.get_or_create(
            organization=self.org_alpha,
            console_module=self.mod_roles,
            defaults={"is_enabled": True, "updated_by": self.owner},
        )
        OrganizationConsoleModulePolicy.objects.get_or_create(
            organization=self.org_alpha,
            console_module=self.mod_assignments,
            defaults={"is_enabled": True, "updated_by": self.owner},
        )
        OrganizationPermissionCeiling.objects.get_or_create(
            organization=self.org_alpha,
            permission=self.perm_roles_view,
            defaults={"is_allowed": True, "updated_by": self.owner},
        )
        OrganizationPermissionCeiling.objects.get_or_create(
            organization=self.org_alpha,
            permission=self.perm_assignments_view,
            defaults={"is_allowed": True, "updated_by": self.owner},
        )

        # 6. Users
        self.admin_alpha = PlatformUser.objects.create_user(
            email="admin@alpha.internal",
            password=self.password,
            full_name="Alpha Admin",
            status="active",
            is_active=True,
            is_platform_owner=False,
        )
        self.membership_admin_alpha = OrganizationMembership.objects.create(
            organization=self.org_alpha,
            user=self.admin_alpha,
            membership_type=MembershipType.TENANT_ADMIN,
            status=MembershipStatus.ACTIVE,
            role=self.sys_role,
            joined_at=timezone.now(),
        )

        self.member_alpha = PlatformUser.objects.create_user(
            email="member@alpha.internal",
            password=self.password,
            full_name="Alpha Member",
            status="active",
            is_active=True,
            is_platform_owner=False,
        )
        self.membership_member_alpha = OrganizationMembership.objects.create(
            organization=self.org_alpha,
            user=self.member_alpha,
            membership_type=MembershipType.MEMBER,
            status=MembershipStatus.ACTIVE,
            role=None,
            joined_at=timezone.now(),
        )

        # 7. Products and Catalog Hierarchy
        self.prod_lms = Product.objects.create(
            code="lms",
            name="Learning Management System",
            description="LMS platform",
            status=ProductStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )
        self.mod_courses = ProductModule.objects.create(
            product=self.prod_lms,
            code="courses",
            name="Course Catalog",
            description="Manage courses",
            status=CatalogStatus.ACTIVE,
            display_order=1,
            created_by=self.owner,
            updated_by=self.owner,
        )
        self.feat_video = ProductFeature.objects.create(
            module=self.mod_courses,
            code="video_streaming",
            name="Video Streaming",
            status=CatalogStatus.ACTIVE,
            display_order=1,
            created_by=self.owner,
            updated_by=self.owner,
        )
        self.cap_hd = ProductCapability.objects.create(
            feature=self.feat_video,
            code="hd_playback",
            name="HD Playback",
            status=CatalogStatus.ACTIVE,
            display_order=1,
            created_by=self.owner,
            updated_by=self.owner,
        )

        self.prod_hrms = Product.objects.create(
            code="hrms",
            name="Human Resources System",
            description="HRMS platform",
            status=ProductStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )
        self.mod_payroll = ProductModule.objects.create(
            product=self.prod_hrms,
            code="payroll",
            name="Payroll Module",
            description="Payroll operations",
            status=CatalogStatus.ACTIVE,
            display_order=1,
            created_by=self.owner,
            updated_by=self.owner,
        )

        # 8. Plan & Active Subscription for Org Alpha
        self.plan = Plan.objects.create(
            code="enterprise_plan",
            name="Enterprise Plan",
            created_by=self.owner,
            updated_by=self.owner,
        )
        self.plan_version = PlanVersion.objects.create(
            plan=self.plan,
            version=1,
            status=PlanVersionStatus.ACTIVE,
            activated_at=timezone.now(),
            created_by=self.owner,
            updated_by=self.owner,
        )
        self.plan_price = PlanPrice.objects.create(
            plan_version=self.plan_version,
            currency="USD",
            billing_interval=BillingInterval.MONTHLY,
            amount=Decimal("100.00"),
            created_by=self.owner,
            updated_by=self.owner,
        )
        self.plan_prod_lms = PlanProduct.objects.create(
            plan_version=self.plan_version,
            product=self.prod_lms,
            created_by=self.owner,
        )
        self.plan_mod_courses = PlanModule.objects.create(
            plan_version=self.plan_version,
            plan_product=self.plan_prod_lms,
            module=self.mod_courses,
            created_by=self.owner,
        )
        self.plan_quota = PlanQuota.objects.create(
            plan_version=self.plan_version,
            quota_key="seats",
            name="LMS Seats",
            scope=QuotaScope.PLAN,
            limit_type=QuotaLimitType.NUMERIC,
            limit_value=20,
            unit="seats",
            reset_period=QuotaResetPeriod.MONTHLY,
            created_by=self.owner,
            updated_by=self.owner,
        )

        self.subscription_alpha = OrganizationSubscription.objects.create(
            organization=self.org_alpha,
            plan_version=self.plan_version,
            plan_price=self.plan_price,
            plan_code_snapshot="enterprise_plan",
            plan_name_snapshot="Enterprise Plan",
            version_number_snapshot=self.plan_version.version,
            currency="USD",
            billing_interval=BillingInterval.MONTHLY,
            amount=Decimal("100.00"),
            status=SubscriptionStatus.ACTIVE,
            current_period_start=timezone.now() - timezone.timedelta(days=5),
            current_period_end=timezone.now() + timezone.timedelta(days=25),
            created_by=self.owner,
            updated_by=self.owner,
        )
        self.sub_prod_ent_lms = SubscriptionProductEntitlement.objects.create(
            subscription=self.subscription_alpha,
            organization=self.org_alpha,
            product=self.prod_lms,
            plan_product=self.plan_prod_lms,
            product_code_snapshot="lms",
            product_name_snapshot="Learning Management System",
        )
        self.sub_mod_ent_courses = SubscriptionModuleEntitlement.objects.create(
            subscription=self.subscription_alpha,
            organization=self.org_alpha,
            module=self.mod_courses,
            plan_module=self.plan_mod_courses,
            module_code_snapshot="courses",
            module_name_snapshot="Course Catalog",
        )
        self.sub_quota_seats = SubscriptionQuotaEntitlement.objects.create(
            subscription=self.subscription_alpha,
            organization=self.org_alpha,
            plan_quota=self.plan_quota,
            quota_key="seats",
            name="LMS Seats",
            unit="seats",
            scope=QuotaScope.PLAN,
            limit_type=QuotaLimitType.NUMERIC,
            limit_value=20,
            is_hard_limit=True,
            reset_period=QuotaResetPeriod.MONTHLY,
        )

    def _login_tenant(self, user: PlatformUser, org: Organization):
        self.client.force_login(user)
        session = self.client.session
        session["active_context_type"] = CONTEXT_TENANT
        session["tenant_organization_id"] = str(org.id)
        session.save()

    # =========================================================================
    # 1. Multi-Product Tenant Test
    # =========================================================================
    def test_multi_product_tenant_returns_hierarchy_and_modules(self):
        """Multi-product tenant returns full module/feature/capability trees and console modules."""
        # Add HRMS as direct grant to Org Alpha
        OrganizationProductEntitlement.objects.create(
            organization=self.org_alpha,
            product=self.prod_hrms,
            status=EntitlementStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )

        # Assign admin to LMS with courses module
        assign_lms = UserProductAssignment.objects.create(
            organization=self.org_alpha,
            user=self.admin_alpha,
            membership=self.membership_admin_alpha,
            product=self.prod_lms,
            status=AssignmentStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )
        UserModuleAssignment.objects.create(
            assignment=assign_lms,
            module=self.mod_courses,
            is_enabled=True,
        )

        # Assign admin to HRMS with payroll module
        assign_hrms = UserProductAssignment.objects.create(
            organization=self.org_alpha,
            user=self.admin_alpha,
            membership=self.membership_admin_alpha,
            product=self.prod_hrms,
            status=AssignmentStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )
        UserModuleAssignment.objects.create(
            assignment=assign_hrms,
            module=self.mod_payroll,
            is_enabled=True,
        )

        self._login_tenant(self.admin_alpha, self.org_alpha)
        response = self.client.get("/api/v1/tenant/home/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()

        self.assertEqual(data["schema_version"], "1.0")
        self.assertEqual(data["organization"]["id"], str(self.org_alpha.id))
        self.assertEqual(data["organization"]["code"], "alpha-corp")
        self.assertEqual(data["membership"]["membership_type"], "tenant_admin")
        self.assertEqual(data["membership"]["role"]["code"], "system_tenant_admin")

        # 2 entitled products returned
        prod_codes = [p["code"] for p in data["entitled_products"]]
        self.assertIn("lms", prod_codes)
        self.assertIn("hrms", prod_codes)

        # Inspect LMS hierarchy: module -> feature -> capability
        lms_item = next(p for p in data["entitled_products"] if p["code"] == "lms")
        self.assertEqual(len(lms_item["modules"]), 1)
        mod_item = lms_item["modules"][0]
        self.assertEqual(mod_item["code"], "courses")
        self.assertEqual(len(mod_item["features"]), 1)
        feat_item = mod_item["features"][0]
        self.assertEqual(feat_item["code"], "video_streaming")
        self.assertEqual(len(feat_item["capabilities"]), 1)
        cap_item = feat_item["capabilities"][0]
        self.assertEqual(cap_item["code"], "hd_playback")

        # Inspect Console modules
        console_keys = [m["key"] for m in data["console_modules"]]
        self.assertIn("tenant_landing", console_keys)
        self.assertIn("tenant_roles", console_keys)
        self.assertIn("tenant_product_assignments", console_keys)

        # Inspect Seat Summary
        self.assertGreaterEqual(data["seat_summary"]["total_assigned_seats"], 2)

    # =========================================================================
    # 2. Zero-Product Tenant Test
    # =========================================================================
    def test_zero_product_tenant_returns_empty_array_200_ok(self):
        """Active member with zero product assignments receives empty entitled_products array."""
        self._login_tenant(self.member_alpha, self.org_alpha)
        response = self.client.get("/api/v1/tenant/home/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(data["schema_version"], "1.0")
        self.assertEqual(data["entitled_products"], [])
        self.assertEqual(data["products"], [])
        self.assertEqual(data["membership"]["membership_type"], "member")
        # Regular members have no admin console modules
        self.assertEqual(data["console_modules"], [])

    # =========================================================================
    # 3. Suspended-Subscription Tenant with Active Direct Grant
    # =========================================================================
    def test_suspended_subscription_with_direct_grant_counts(self):
        """Active direct grant continues to entitle product even if subscription is suspended."""
        # Suspend subscription
        self.subscription_alpha.status = SubscriptionStatus.SUSPENDED
        self.subscription_alpha.save(update_fields=["status"])

        # Grant HRMS directly to Alpha
        OrganizationProductEntitlement.objects.create(
            organization=self.org_alpha,
            product=self.prod_hrms,
            status=EntitlementStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )

        # Assign user to LMS (from suspended sub) and HRMS (from direct grant)
        assign_lms = UserProductAssignment.objects.create(
            organization=self.org_alpha,
            user=self.admin_alpha,
            membership=self.membership_admin_alpha,
            product=self.prod_lms,
            status=AssignmentStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )
        assign_hrms = UserProductAssignment.objects.create(
            organization=self.org_alpha,
            user=self.admin_alpha,
            membership=self.membership_admin_alpha,
            product=self.prod_hrms,
            status=AssignmentStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )
        UserModuleAssignment.objects.create(
            assignment=assign_hrms,
            module=self.mod_payroll,
            is_enabled=True,
        )

        self._login_tenant(self.admin_alpha, self.org_alpha)
        response = self.client.get("/api/v1/tenant/home/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()

        # LMS is NOT entitled because subscription is suspended and no direct grant exists
        # HRMS IS entitled because of the active direct grant
        entitled_codes = [p["code"] for p in data["entitled_products"]]
        self.assertNotIn("lms", entitled_codes)
        self.assertIn("hrms", entitled_codes)

    # =========================================================================
    # 4. Ceiling-Restricted Tenant Test
    # =========================================================================
    def test_ceiling_revocation_excludes_console_module(self):
        """Permission ceiling revocation takes precedence and removes console module from list."""
        # Revoke ceiling for assignments.view
        ceiling = OrganizationPermissionCeiling.objects.get(
            organization=self.org_alpha,
            permission=self.perm_assignments_view,
        )
        ceiling.is_allowed = False
        ceiling.save()

        self._login_tenant(self.admin_alpha, self.org_alpha)
        response = self.client.get("/api/v1/tenant/home/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()

        console_keys = [m["key"] for m in data["console_modules"]]
        # tenant_roles remains visible
        self.assertIn("tenant_roles", console_keys)
        # tenant_product_assignments is excluded because ceiling was revoked
        self.assertNotIn("tenant_product_assignments", console_keys)

    # =========================================================================
    # 5. User Without Active Membership Test
    # =========================================================================
    def test_user_without_active_membership_rejected_403(self):
        """User without active membership in the active tenant context is rejected with 403."""
        unaffiliated_user = PlatformUser.objects.create_user(
            email="stranger@vibeconnect.internal",
            password=self.password,
            full_name="Stranger",
            status="active",
            is_active=True,
            is_platform_owner=False,
        )

        self._login_tenant(unaffiliated_user, self.org_alpha)
        response = self.client.get("/api/v1/tenant/home/")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        data = response.json()
        self.assertEqual(data["code"], "MEMBERSHIP_INELIGIBLE")

    # =========================================================================
    # 6. Multi-Tenant Boundary Isolation Test
    # =========================================================================
    def test_cross_tenant_isolation(self):
        """User assigned to products in Org Alpha sees zero products when in Org Beta context."""
        # Create membership for user in Org Beta as well
        OrganizationMembership.objects.create(
            organization=self.org_beta,
            user=self.admin_alpha,
            membership_type=MembershipType.TENANT_ADMIN,
            status=MembershipStatus.ACTIVE,
            role=self.sys_role,
            joined_at=timezone.now(),
        )

        # Assign user to LMS strictly within Org Alpha
        UserProductAssignment.objects.create(
            organization=self.org_alpha,
            user=self.admin_alpha,
            membership=self.membership_admin_alpha,
            product=self.prod_lms,
            status=AssignmentStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )

        # Login under Org Beta context
        self._login_tenant(self.admin_alpha, self.org_beta)
        response = self.client.get("/api/v1/tenant/home/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        # Org Beta has no LMS subscription/grant and no Org Beta assignment for this user
        self.assertEqual(data["organization"]["id"], str(self.org_beta.id))
        self.assertEqual(data["entitled_products"], [])

    # =========================================================================
    # 7. Unauthenticated and Missing Context Tests
    # =========================================================================
    def test_unauthenticated_request_rejected_401(self):
        """Anonymous requests return 401."""
        response = self.client.get("/api/v1/tenant/home/")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_missing_tenant_context_rejected_403(self):
        """Authenticated user without active tenant context returns 403 TENANT_CONTEXT_REQUIRED."""
        self.client.force_login(self.admin_alpha)
        # No session active_context_type set
        response = self.client.get("/api/v1/tenant/home/")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.json()["code"], "TENANT_CONTEXT_REQUIRED")

    # =========================================================================
    # 8. Service Layer Direct Unit Test
    # =========================================================================
    def test_effective_access_service_unit(self):
        """Direct unit test of compute_user_tenant_effective_access service."""
        result = compute_user_tenant_effective_access(self.admin_alpha, self.org_alpha)
        self.assertIsInstance(result, dict)
        self.assertEqual(result["schema_version"], "1.0")
        self.assertEqual(result["organization"]["id"], str(self.org_alpha.id))
        self.assertIn("seat_summary", result)

    # =========================================================================
    # 9. 10-State Access Matrix Test (Phase 2G)
    # =========================================================================
    def test_access_state_matrix_covers_all_ten_states(self):
        """The effective access computation deterministically outputs all 10 access states."""
        now = timezone.now()

        # 1. State: available
        assign_avail = UserProductAssignment.objects.create(
            organization=self.org_alpha,
            user=self.admin_alpha,
            membership=self.membership_admin_alpha,
            product=self.prod_lms,
            status=AssignmentStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )
        UserModuleAssignment.objects.create(
            assignment=assign_avail,
            module=self.mod_courses,
            is_enabled=True,
        )

        res = compute_user_tenant_effective_access(self.admin_alpha, self.org_alpha)
        prod_map = {p["code"]: p for p in res["products"]}
        self.assertEqual(prod_map["lms"]["access_state"], AccessState.AVAILABLE)
        self.assertIsNone(prod_map["lms"]["denial_code"])
        self.assertEqual(len(prod_map["lms"]["eligible_modules"]), 1)
        self.assertEqual(prod_map["lms"]["eligible_modules"][0]["module_state"], ModuleState.AVAILABLE)

        # 2. State: not_assigned
        # Direct grant HRMS to org_alpha, but do NOT assign admin_alpha
        OrganizationProductEntitlement.objects.create(
            organization=self.org_alpha,
            product=self.prod_hrms,
            status=EntitlementStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )
        res = compute_user_tenant_effective_access(self.admin_alpha, self.org_alpha)
        prod_map = {p["code"]: p for p in res["products"]}
        self.assertEqual(prod_map["hrms"]["access_state"], AccessState.NOT_ASSIGNED)
        self.assertEqual(prod_map["hrms"]["denial_code"], DenialCode.NOT_ASSIGNED)

        # 3. State: subscription_inactive
        # Create dedicated org_suspended with a suspended subscription
        org_suspended = Organization.objects.create(
            name="Suspended Org",
            code="suspended-org",
            status=OrganizationStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )
        OrganizationMembership.objects.create(
            organization=org_suspended,
            user=self.admin_alpha,
            membership_type=MembershipType.TENANT_ADMIN,
            status=MembershipStatus.ACTIVE,
            role=self.sys_role,
            joined_at=now,
        )
        prod_crm = Product.objects.create(
            code="crm",
            name="CRM System",
            status=ProductStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )
        sub_inactive = OrganizationSubscription.objects.create(
            organization=org_suspended,
            plan_version=self.plan_version,
            plan_price=self.plan_price,
            plan_code_snapshot="enterprise_plan",
            plan_name_snapshot="Enterprise Plan",
            version_number_snapshot=1,
            currency="USD",
            billing_interval=BillingInterval.MONTHLY,
            amount=Decimal("100.00"),
            status=SubscriptionStatus.SUSPENDED,
            current_period_start=now - timezone.timedelta(days=5),
            current_period_end=now + timezone.timedelta(days=25),
            created_by=self.owner,
            updated_by=self.owner,
        )
        SubscriptionProductEntitlement.objects.create(
            subscription=sub_inactive,
            organization=org_suspended,
            product=prod_crm,
            plan_product=self.plan_prod_lms,
            product_code_snapshot="crm",
            product_name_snapshot="CRM System",
        )
        res_suspended = compute_user_tenant_effective_access(self.admin_alpha, org_suspended)
        prod_map_suspended = {p["code"]: p for p in res_suspended["products"]}
        self.assertEqual(prod_map_suspended["crm"]["access_state"], AccessState.SUBSCRIPTION_INACTIVE)
        self.assertEqual(prod_map_suspended["crm"]["denial_code"], DenialCode.SUBSCRIPTION_INACTIVE)

        # 4. State: entitlement_unavailable
        # Create active prod_analytics in catalog, org has no subscription or grant for it
        prod_analytics = Product.objects.create(
            code="analytics",
            name="Analytics Platform",
            status=ProductStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )
        res = compute_user_tenant_effective_access(self.admin_alpha, self.org_alpha)
        prod_map = {p["code"]: p for p in res["products"]}
        self.assertEqual(prod_map["analytics"]["access_state"], AccessState.ENTITLEMENT_UNAVAILABLE)
        self.assertEqual(prod_map["analytics"]["denial_code"], DenialCode.ENTITLEMENT_UNAVAILABLE)

        # 5. State: assignment_suspended
        assign_avail.status = AssignmentStatus.SUSPENDED
        assign_avail.last_suspended_at = now
        assign_avail.save(update_fields=["status", "last_suspended_at"])
        res = compute_user_tenant_effective_access(self.admin_alpha, self.org_alpha)
        prod_map = {p["code"]: p for p in res["products"]}
        self.assertEqual(prod_map["lms"]["access_state"], AccessState.ASSIGNMENT_SUSPENDED)
        self.assertEqual(prod_map["lms"]["denial_code"], DenialCode.ASSIGNMENT_SUSPENDED)

        # 6. State: assignment_revoked
        assign_avail.status = AssignmentStatus.REVOKED
        assign_avail.revoked_at = now
        assign_avail.save(update_fields=["status", "revoked_at"])
        res = compute_user_tenant_effective_access(self.admin_alpha, self.org_alpha)
        prod_map = {p["code"]: p for p in res["products"]}
        self.assertEqual(prod_map["lms"]["access_state"], AccessState.ASSIGNMENT_REVOKED)
        self.assertEqual(prod_map["lms"]["denial_code"], DenialCode.ASSIGNMENT_REVOKED)

        # 7. State: module_unavailable
        # Create a product with direct grant where user's assigned module is disabled
        prod_mod_test = Product.objects.create(
            code="mod_test",
            name="Module Test Product",
            status=ProductStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )
        mod_test_item = ProductModule.objects.create(
            product=prod_mod_test,
            code="test_mod",
            name="Test Module",
            status=CatalogStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )
        OrganizationProductEntitlement.objects.create(
            organization=self.org_alpha,
            product=prod_mod_test,
            status=EntitlementStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )
        assign_mod_test = UserProductAssignment.objects.create(
            organization=self.org_alpha,
            user=self.admin_alpha,
            membership=self.membership_admin_alpha,
            product=prod_mod_test,
            status=AssignmentStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )
        UserModuleAssignment.objects.create(
            assignment=assign_mod_test,
            module=mod_test_item,
            is_enabled=False,
        )
        res = compute_user_tenant_effective_access(self.admin_alpha, self.org_alpha)
        prod_map = {p["code"]: p for p in res["products"]}
        self.assertEqual(prod_map["mod_test"]["access_state"], AccessState.MODULE_UNAVAILABLE)
        self.assertEqual(prod_map["mod_test"]["denial_code"], DenialCode.MODULE_UNAVAILABLE)

        # 8. State: access_expired
        # Create dedicated org_expired with expired subscription
        org_expired = Organization.objects.create(
            name="Expired Org",
            code="expired-org",
            status=OrganizationStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )
        OrganizationMembership.objects.create(
            organization=org_expired,
            user=self.admin_alpha,
            membership_type=MembershipType.TENANT_ADMIN,
            status=MembershipStatus.ACTIVE,
            role=self.sys_role,
            joined_at=now,
        )
        prod_billing = Product.objects.create(
            code="billing_app",
            name="Billing App",
            status=ProductStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )
        sub_expired = OrganizationSubscription.objects.create(
            organization=org_expired,
            plan_version=self.plan_version,
            plan_price=self.plan_price,
            plan_code_snapshot="enterprise_plan",
            plan_name_snapshot="Enterprise Plan",
            version_number_snapshot=1,
            currency="USD",
            billing_interval=BillingInterval.MONTHLY,
            amount=Decimal("100.00"),
            status=SubscriptionStatus.EXPIRED,
            started_as_trial=True,
            trial_started_at=now - timezone.timedelta(days=60),
            trial_ends_at=now - timezone.timedelta(days=30),
            current_period_start=now - timezone.timedelta(days=60),
            current_period_end=now - timezone.timedelta(days=30),
            ended_at=now - timezone.timedelta(days=30),
            created_by=self.owner,
            updated_by=self.owner,
        )
        SubscriptionProductEntitlement.objects.create(
            subscription=sub_expired,
            organization=org_expired,
            product=prod_billing,
            plan_product=self.plan_prod_lms,
            product_code_snapshot="billing_app",
            product_name_snapshot="Billing App",
        )
        res_expired = compute_user_tenant_effective_access(self.admin_alpha, org_expired)
        prod_map_exp = {p["code"]: p for p in res_expired["products"]}
        self.assertEqual(prod_map_exp["billing_app"]["access_state"], AccessState.ACCESS_EXPIRED)
        self.assertEqual(prod_map_exp["billing_app"]["denial_code"], DenialCode.ACCESS_EXPIRED)

        # 9. State: product_unavailable
        prod_retired = Product.objects.create(
            code="retired_app",
            name="Retired Application",
            status=ProductStatus.RETIRED,
            created_by=self.owner,
            updated_by=self.owner,
        )
        UserProductAssignment.objects.create(
            organization=self.org_alpha,
            user=self.admin_alpha,
            membership=self.membership_admin_alpha,
            product=prod_retired,
            status=AssignmentStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )
        res = compute_user_tenant_effective_access(self.admin_alpha, self.org_alpha)
        prod_map = {p["code"]: p for p in res["products"]}
        self.assertEqual(prod_map["retired_app"]["access_state"], AccessState.PRODUCT_UNAVAILABLE)
        self.assertEqual(prod_map["retired_app"]["denial_code"], DenialCode.PRODUCT_UNAVAILABLE)

        # 10. State: membership_inactive
        # Set membership to suspended
        self.membership_admin_alpha.status = MembershipStatus.SUSPENDED
        self.membership_admin_alpha.save(update_fields=["status"])
        res = compute_user_tenant_effective_access(self.admin_alpha, self.org_alpha)
        for p in res["products"]:
            self.assertEqual(p["access_state"], AccessState.MEMBERSHIP_INACTIVE)
            self.assertEqual(p["denial_code"], DenialCode.MEMBERSHIP_INACTIVE)

