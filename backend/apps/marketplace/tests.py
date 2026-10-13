"""Focused Unit & Service Tests for Marketplace (Phase 6A Stage 3).

Validates the minimum contract:
1. TenantProductRequest creation by valid Tenant Admin
2. Duplicate pending request is rejected (and conditional constraint allows after terminal status)
3. Requested plan must belong to selected product
4. LMS integration readiness permits enablement service
5. Integration-pending product cannot be enabled and creates no entitlement/provisioning job
6. LMS enablement uses canonical entitlement service and does not directly call Integration Hub
7. Cross-tenant operation is rejected
"""

from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.access_control.constants import CONTEXT_TENANT
from apps.access_control.models import Role
from apps.entitlements.models import EntitlementStatus, OrganizationProductEntitlement
from apps.integration_hub.models import (
    ConnectorStatus,
    IntegrationConnector,
    ProvisioningJob,
)
from apps.marketplace.models import TenantProductRequest, TenantProductRequestStatus
from apps.marketplace.services import (
    CrossTenantAccessError,
    DuplicateTenantProductRequestError,
    IntegrationPendingError,
    PlanMismatchError,
    TenantAdminRequiredError,
    create_tenant_product_request,
    enable_marketplace_product,
    is_product_integration_ready,
)
from apps.organizations.models import (
    MembershipStatus,
    MembershipType,
    Organization,
    OrganizationMembership,
    OrganizationStatus,
)
from apps.plans.models import PlanPrice
from apps.plans.services import add_plan_product, create_plan
from apps.product_registry.models import CatalogStatus, Product, ProductFeature, ProductModule, ProductStatus
from apps.showcase.models import ProductShowcaseMedia, ProductShowcaseProfile, ShowcaseVisibility

User = get_user_model()


class MarketplaceStage3ServiceTests(TestCase):
    """Test suite strictly validating Phase 6A Stage 3 domain requirements."""

    def setUp(self):
        # Platform Owner
        self.owner = User.objects.create_user(
            email="owner_test@vibeconnect.io",
            password="SecurePassword123!",
            full_name="Platform Owner",
            is_platform_owner=True,
            is_active=True,
        )

        # Organization A
        self.org_a = Organization.objects.create(
            code="tenant-alpha",
            name="Tenant Alpha",
            status=OrganizationStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )

        # Organization B (for cross-tenant validation)
        self.org_b = Organization.objects.create(
            code="tenant-beta",
            name="Tenant Beta",
            status=OrganizationStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )

        # System Tenant Admin role (required by DB check constraint: membership_type_role_sync)
        self.tenant_admin_role, _ = Role.objects.get_or_create(
            organization=None,
            code="system_tenant_admin",
            defaults={
                "name": "Tenant Administrator",
                "description": "System role",
                "is_system_role": True,
                "status": "active",
            },
        )

        # Tenant Admin for Org A
        self.admin_a = User.objects.create_user(
            email="admin_a@alpha.io",
            password="SecurePassword123!",
            full_name="Admin Alpha",
            is_platform_owner=False,
            is_active=True,
        )
        OrganizationMembership.objects.create(
            organization=self.org_a,
            user=self.admin_a,
            membership_type=MembershipType.TENANT_ADMIN,
            status=MembershipStatus.ACTIVE,
            role=self.tenant_admin_role,
            joined_at=timezone.now(),
        )

        # Regular Member for Org A (not admin)
        self.member_a = User.objects.create_user(
            email="member_a@alpha.io",
            password="SecurePassword123!",
            full_name="Member Alpha",
            is_platform_owner=False,
            is_active=True,
        )
        OrganizationMembership.objects.create(
            organization=self.org_a,
            user=self.member_a,
            membership_type=MembershipType.MEMBER,
            status=MembershipStatus.ACTIVE,
            joined_at=timezone.now(),
        )

        # LMS Product — code "lms" is in LMS_PRODUCT_CODES frozenset → integration-ready
        self.lms_product = Product.objects.create(
            code="lms",
            name="Learning Management System",
            status=ProductStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )
        # Connector code "lms" is matched by get_or_create_lms_connector_instance
        IntegrationConnector.objects.create(
            code="lms",
            name="LMS Connector",
            product=self.lms_product,
            status=ConnectorStatus.ACTIVE,
        )

        # WMS Product — code "wms" NOT in LMS_PRODUCT_CODES → integration-pending
        self.wms_product = Product.objects.create(
            code="wms",
            name="Warehouse Management System",
            status=ProductStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )
        IntegrationConnector.objects.create(
            code="wms-connector",
            name="WMS Connector",
            product=self.wms_product,
            status=ConnectorStatus.ACTIVE,
        )

        # LMS Plan via canonical service; pv is DRAFT with LMS product linked
        _, self.lms_plan_version = create_plan(
            code="lms-standard",
            name="LMS Standard",
            actor=self.owner,
        )
        add_plan_product(
            plan_version_id=self.lms_plan_version.id,
            product_id=self.lms_product.id,
            actor=self.owner,
        )

        # WMS Plan via canonical service; pv is DRAFT with WMS product linked
        _, self.wms_plan_version = create_plan(
            code="wms-standard",
            name="WMS Standard",
            actor=self.owner,
        )
        add_plan_product(
            plan_version_id=self.wms_plan_version.id,
            product_id=self.wms_product.id,
            actor=self.owner,
        )

    # 1. TenantProductRequest creation by valid Tenant Admin
    def test_01_tenant_product_request_creation_by_valid_tenant_admin(self):
        """A valid Tenant Admin can submit a product adoption request for their organization."""
        req = create_tenant_product_request(
            organization=self.org_a,
            requester=self.admin_a,
            product=self.wms_product,
            requested_plan=self.wms_plan_version,
            notes="Interested in trial for warehouse team.",
        )
        self.assertIsNotNone(req.id)
        self.assertEqual(req.organization, self.org_a)
        self.assertEqual(req.product, self.wms_product)
        self.assertEqual(req.requested_plan, self.wms_plan_version)
        self.assertEqual(req.requester, self.admin_a)
        self.assertEqual(req.status, TenantProductRequestStatus.PENDING)
        self.assertEqual(req.notes, "Interested in trial for warehouse team.")

    # 2. Duplicate pending request is rejected; allowed once resolved
    def test_02_duplicate_pending_request_rejected(self):
        """Duplicate pending requests for same org + product are rejected; allowed after cancellation."""
        create_tenant_product_request(
            organization=self.org_a,
            requester=self.admin_a,
            product=self.wms_product,
            notes="First request",
        )

        with self.assertRaises(DuplicateTenantProductRequestError):
            create_tenant_product_request(
                organization=self.org_a,
                requester=self.admin_a,
                product=self.wms_product,
                notes="Second request",
            )

        # Cancel first request; new pending request must now succeed
        TenantProductRequest.objects.filter(
            organization=self.org_a,
            product=self.wms_product,
            status=TenantProductRequestStatus.PENDING,
        ).update(status=TenantProductRequestStatus.CANCELLED)

        req2 = create_tenant_product_request(
            organization=self.org_a,
            requester=self.admin_a,
            product=self.wms_product,
            notes="Second request after cancellation",
        )
        self.assertEqual(req2.status, TenantProductRequestStatus.PENDING)

    # 3. Requested plan must belong to selected product
    def test_03_requested_plan_must_belong_to_selected_product(self):
        """Passing a plan version that belongs to a different product raises PlanMismatchError."""
        with self.assertRaises(PlanMismatchError):
            create_tenant_product_request(
                organization=self.org_a,
                requester=self.admin_a,
                product=self.lms_product,
                requested_plan=self.wms_plan_version,  # Belongs to WMS, not LMS
                notes="Mismatched plan request",
            )

    # 4. LMS integration readiness permits enablement service
    def test_04_lms_integration_readiness_permits_enablement(self):
        """LMS is integration-ready and can be enabled by a Platform Owner (satisfies both
        _require_active_tenant_admin guard and ENTITLEMENT_CREATED platform-owner audit requirement)."""
        self.assertTrue(is_product_integration_ready(self.lms_product))

        job_count_before = ProvisioningJob.objects.count()

        # Platform owner passes _require_active_tenant_admin (explicit bypass) and
        # satisfies ENTITLEMENT_CREATED audit action which requires platform owner privileges.
        entitlement = enable_marketplace_product(
            organization=self.org_a,
            actor=self.owner,
            product=self.lms_product,
        )
        self.assertIsNotNone(entitlement.id)
        self.assertEqual(entitlement.organization, self.org_a)
        self.assertEqual(entitlement.product, self.lms_product)
        self.assertEqual(entitlement.status, EntitlementStatus.ACTIVE)

        # Lifecycle hook must have enqueued a ProvisioningJob for the organization
        self.assertGreater(ProvisioningJob.objects.count(), job_count_before)
        self.assertTrue(
            ProvisioningJob.objects.filter(organization=self.org_a).exists()
        )

    # 5. Integration-pending product cannot be enabled and creates no entitlement/provisioning job
    def test_05_integration_pending_product_cannot_be_enabled(self):
        """Unintegrated products (e.g. WMS) fail with IntegrationPendingError with 0 mutations."""
        self.assertFalse(is_product_integration_ready(self.wms_product))

        ent_count_before = OrganizationProductEntitlement.objects.count()
        job_count_before = ProvisioningJob.objects.count()

        with self.assertRaises(IntegrationPendingError):
            enable_marketplace_product(
                organization=self.org_a,
                actor=self.admin_a,
                product=self.wms_product,
            )

        self.assertEqual(OrganizationProductEntitlement.objects.count(), ent_count_before)
        self.assertEqual(ProvisioningJob.objects.count(), job_count_before)

    # 6. LMS enablement delegates exclusively to canonical entitlement service
    def test_06_lms_enablement_uses_canonical_entitlement_service(self):
        """enable_marketplace_product delegates to create_or_activate_entitlement."""
        stub_entitlement = MagicMock()
        stub_entitlement.id = "mock-uuid"
        stub_entitlement.organization = self.org_a
        stub_entitlement.product = self.lms_product
        stub_entitlement.status = EntitlementStatus.ACTIVE

        with patch("apps.marketplace.services.create_or_activate_entitlement") as mock_ent:
            mock_ent.return_value = stub_entitlement

            enable_marketplace_product(
                organization=self.org_a,
                actor=self.owner,
                product=self.lms_product,
            )

            mock_ent.assert_called_once()
            _, kwargs = mock_ent.call_args
            self.assertEqual(kwargs["organization"], self.org_a)
            self.assertEqual(kwargs["product"], self.lms_product)
            self.assertEqual(kwargs["actor"], self.owner)

    # 7. Cross-tenant operations are rejected
    def test_07_cross_tenant_operation_is_rejected(self):
        """A Tenant Admin of Org A cannot request or enable products for Org B."""
        # Cross-org request raises CrossTenantAccessError
        with self.assertRaises(CrossTenantAccessError):
            create_tenant_product_request(
                organization=self.org_b,
                requester=self.admin_a,
                product=self.wms_product,
            )

        # Cross-org enablement raises CrossTenantAccessError
        with self.assertRaises(CrossTenantAccessError):
            enable_marketplace_product(
                organization=self.org_b,
                actor=self.admin_a,
                product=self.lms_product,
            )

        # Regular member (not admin) in own org raises TenantAdminRequiredError for request
        with self.assertRaises(TenantAdminRequiredError):
            create_tenant_product_request(
                organization=self.org_a,
                requester=self.member_a,
                product=self.wms_product,
            )

        # Regular member (not admin) in own org raises TenantAdminRequiredError for enablement
        with self.assertRaises(TenantAdminRequiredError):
            enable_marketplace_product(
                organization=self.org_a,
                actor=self.member_a,
                product=self.lms_product,
            )


class MarketplaceStage4APITests(TestCase):
    """Focused REST API tests validating Phase 6A Stage 4 contract."""

    def setUp(self):
        # Platform Owner
        self.owner = User.objects.create_user(
            email="owner_stage4@vibeconnect.io",
            password="SecurePassword123!",
            full_name="Platform Owner",
            is_platform_owner=True,
            is_active=True,
        )

        # Organization A
        self.org_a = Organization.objects.create(
            code="tenant-alpha",
            name="Tenant Alpha",
            status=OrganizationStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )

        # Organization B (for cross-tenant validation)
        self.org_b = Organization.objects.create(
            code="tenant-beta",
            name="Tenant Beta",
            status=OrganizationStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )

        # System Tenant Admin role (for check constraint)
        self.tenant_admin_role, _ = Role.objects.get_or_create(
            organization=None,
            code="system_tenant_admin",
            defaults={
                "name": "Tenant Administrator",
                "description": "System role",
                "is_system_role": True,
                "status": "active",
            },
        )

        # Tenant Admin for Org A
        self.admin_a = User.objects.create_user(
            email="admin_a_api@alpha.io",
            password="SecurePassword123!",
            full_name="Admin Alpha",
            is_platform_owner=False,
            is_active=True,
        )
        OrganizationMembership.objects.create(
            organization=self.org_a,
            user=self.admin_a,
            membership_type=MembershipType.TENANT_ADMIN,
            role=self.tenant_admin_role,
            status=MembershipStatus.ACTIVE,
            joined_at=timezone.now(),
        )

        # Tenant Member for Org A (regular member, cannot enable/request)
        self.member_a = User.objects.create_user(
            email="member_a_api@alpha.io",
            password="SecurePassword123!",
            full_name="Member Alpha",
            is_platform_owner=False,
            is_active=True,
        )
        OrganizationMembership.objects.create(
            organization=self.org_a,
            user=self.member_a,
            membership_type=MembershipType.MEMBER,
            status=MembershipStatus.ACTIVE,
            joined_at=timezone.now(),
        )

        # Tenant Admin for Org B
        self.admin_b = User.objects.create_user(
            email="admin_b_api@beta.io",
            password="SecurePassword123!",
            full_name="Admin Beta",
            is_platform_owner=False,
            is_active=True,
        )
        OrganizationMembership.objects.create(
            organization=self.org_b,
            user=self.admin_b,
            membership_type=MembershipType.TENANT_ADMIN,
            role=self.tenant_admin_role,
            status=MembershipStatus.ACTIVE,
            joined_at=timezone.now(),
        )

        # Products
        self.lms_product = Product.objects.create(
            code="lms",
            name="Learning Management System",
            description="Enterprise LMS for employee learning.",
            status=ProductStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )
        self.wms_product = Product.objects.create(
            code="wms",
            name="Warehouse Management System",
            description="Inventory and logistics system.",
            status=ProductStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )

        # LMS Integration Connector (Active)
        IntegrationConnector.objects.create(
            code="lms-connector",
            name="LMS Connector",
            product=self.lms_product,
            status=ConnectorStatus.ACTIVE,
        )

        # LMS Showcase Profile & Media
        self.lms_showcase = ProductShowcaseProfile.objects.create(
            product=self.lms_product,
            tagline="Next-gen Learning Platform",
            overview="Scalable enterprise LMS built for modern training.",
            visibility=ShowcaseVisibility.PUBLISHED,
            created_by=self.owner,
            updated_by=self.owner,
        )
        ProductShowcaseMedia.objects.create(
            profile=self.lms_showcase,
            media_type="screenshot",
            title="LMS Dashboard Preview",
            url="https://cdn.example.com/lms-preview.png",
            display_order=1,
            created_by=self.owner,
        )

        # LMS Module & Feature
        self.lms_mod = ProductModule.objects.create(
            product=self.lms_product,
            code="courses",
            name="Course Management",
            description="Create and assign courses",
            status=CatalogStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )
        self.lms_feat = ProductFeature.objects.create(
            module=self.lms_mod,
            code="authoring",
            name="Course Authoring",
            description="Interactive lesson builder",
            status=CatalogStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )

        # LMS Plan (Public)
        lms_plan, self.lms_plan_version = create_plan(
            code="lms-standard",
            name="LMS Standard",
            actor=self.owner,
        )
        lms_plan.is_public = True
        lms_plan.save()
        add_plan_product(
            plan_version_id=self.lms_plan_version.id,
            product_id=self.lms_product.id,
            actor=self.owner,
        )
        self.lms_plan_version.status = "active"
        self.lms_plan_version.activated_at = timezone.now()
        self.lms_plan_version.save()
        PlanPrice.objects.create(
            plan_version=self.lms_plan_version,
            currency="USD",
            amount="50.00",
            billing_interval="monthly",
            created_by=self.owner,
            updated_by=self.owner,
        )

        # WMS Plan
        _, self.wms_plan_version = create_plan(
            code="wms-standard",
            name="WMS Standard",
            actor=self.owner,
        )
        add_plan_product(
            plan_version_id=self.wms_plan_version.id,
            product_id=self.wms_product.id,
            actor=self.owner,
        )
        self.wms_plan_version.status = "active"
        self.wms_plan_version.activated_at = timezone.now()
        self.wms_plan_version.save()

    def _login_tenant(self, user, org):
        self.client.force_login(user)
        session = self.client.session
        session["active_context_type"] = CONTEXT_TENANT
        session["tenant_organization_id"] = str(org.id)
        session.save()

    # 1. Authenticated tenant catalog returns correct tenant overlay
    def test_01_authenticated_tenant_catalog_returns_correct_tenant_overlay(self):
        """GET /api/v1/marketplace/products/ returns products with correct tenant overlay."""
        self._login_tenant(self.admin_a, self.org_a)
        response = self.client.get("/api/v1/marketplace/products/")
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertGreaterEqual(len(data), 2)
        by_code = {p["code"]: p for p in data}

        # LMS: operational and available
        lms = by_code["lms"]
        self.assertEqual(lms["integration_status"], "operational")
        self.assertEqual(lms["tenant_state"], "available")
        self.assertTrue(lms["can_enable"])
        self.assertTrue(lms["can_request"])
        self.assertEqual(lms["tagline"], "Next-gen Learning Platform")
        self.assertEqual(lms["icon_url"], "https://cdn.example.com/lms-preview.png")
        self.assertIn("id", lms)
        self.assertIn("plans_count", lms)

        # WMS: pending and integration_pending
        wms = by_code["wms"]
        self.assertEqual(wms["integration_status"], "pending")
        self.assertEqual(wms["tenant_state"], "integration_pending")
        self.assertFalse(wms["can_enable"])
        self.assertTrue(wms["can_request"])

    # 2. Product detail respects tenant visibility
    def test_02_product_detail_respects_tenant_visibility(self):
        """GET /api/v1/marketplace/products/<code_or_id>/ returns full tenant-aware detail."""
        self._login_tenant(self.admin_a, self.org_a)

        # Resolve by code
        res_code = self.client.get("/api/v1/marketplace/products/lms/")
        self.assertEqual(res_code.status_code, 200)
        detail = res_code.json()
        self.assertEqual(detail["code"], "lms")
        self.assertEqual(detail["tagline"], "Next-gen Learning Platform")
        self.assertTrue(len(detail["modules"]) >= 1)
        self.assertEqual(detail["modules"][0]["code"], "courses")
        self.assertEqual(detail["modules"][0]["features"][0]["code"], "authoring")
        self.assertTrue(len(detail["plans"]) >= 1)
        self.assertEqual(detail["plans"][0]["plan_code"], "lms-standard")
        self.assertIsNone(detail["entitlement"])
        self.assertIsNone(detail["pending_request"])
        self.assertTrue(detail["can_enable"])
        self.assertTrue(detail["can_request"])

        # Resolve by UUID
        res_uuid = self.client.get(f"/api/v1/marketplace/products/{self.lms_product.id}/")
        self.assertEqual(res_uuid.status_code, 200)

        # Non-existent product returns 404
        res_404 = self.client.get("/api/v1/marketplace/products/unknown-product-xyz/")
        self.assertEqual(res_404.status_code, 404)
        self.assertEqual(res_404.json()["code"], "PRODUCT_NOT_FOUND")

    # 3. Tenant Admin can enable LMS
    def test_03_tenant_admin_can_enable_lms(self):
        """POST /api/v1/marketplace/products/lms/enable/ enables LMS and activates entitlement."""
        self._login_tenant(self.admin_a, self.org_a)
        response = self.client.post(
            "/api/v1/marketplace/products/lms/enable/",
            data={"plan_version_id": str(self.lms_plan_version.id)},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)

        # Entitlement is now ACTIVE for Org A
        ent = OrganizationProductEntitlement.objects.get(
            organization=self.org_a,
            product=self.lms_product,
        )
        self.assertEqual(ent.status, EntitlementStatus.ACTIVE)

        # Subsequent detail reports installed
        res_detail = self.client.get("/api/v1/marketplace/products/lms/")
        self.assertEqual(res_detail.json()["tenant_state"], "installed")
        self.assertFalse(res_detail.json()["can_enable"])

        # Idempotent second enablement returns 200 without duplicate creation
        res_idempotent = self.client.post(
            "/api/v1/marketplace/products/lms/enable/",
            data={"plan_version_id": str(self.lms_plan_version.id)},
            content_type="application/json",
        )
        self.assertEqual(res_idempotent.status_code, 200)

    # 4. Non-admin cannot enable
    def test_04_non_admin_cannot_enable(self):
        """Regular tenant member receives 403 when attempting to enable product."""
        self._login_tenant(self.member_a, self.org_a)
        response = self.client.post(
            "/api/v1/marketplace/products/lms/enable/",
            data={},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["code"], "TENANT_ADMIN_REQUIRED")

        # Zero entitlement created
        self.assertFalse(
            OrganizationProductEntitlement.objects.filter(
                organization=self.org_a,
                product=self.lms_product,
            ).exists()
        )

    # 5. WMS / integration-pending product enable is rejected with zero mutation
    def test_05_wms_integration_pending_product_enable_is_rejected(self):
        """Enable request on unintegrated product returns 422 with INTEGRATION_PENDING and zero mutation."""
        self._login_tenant(self.admin_a, self.org_a)
        response = self.client.post(
            "/api/v1/marketplace/products/wms/enable/",
            data={},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["code"], "INTEGRATION_PENDING")

        # Zero entitlements and zero provisioning jobs created
        self.assertEqual(
            OrganizationProductEntitlement.objects.filter(
                organization=self.org_a,
                product=self.wms_product,
            ).count(),
            0,
        )
        self.assertEqual(
            ProvisioningJob.objects.filter(
                organization=self.org_a,
            ).count(),
            0,
        )

    # 6. Tenant Admin can create product adoption request
    def test_06_tenant_admin_can_create_product_adoption_request(self):
        """POST /api/v1/marketplace/products/<code_or_id>/request/ creates TenantProductRequest."""
        self._login_tenant(self.admin_a, self.org_a)
        response = self.client.post(
            "/api/v1/marketplace/products/wms/request/",
            data={
                "requested_plan_id": str(self.wms_plan_version.id),
                "notes": "Requesting WMS evaluation.",
            },
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(data["status"], "pending")
        self.assertEqual(data["product_code"], "wms")
        self.assertEqual(data["organization_code"], "tenant-alpha")
        self.assertEqual(data["notes"], "Requesting WMS evaluation.")

        # Zero entitlement created
        self.assertEqual(
            OrganizationProductEntitlement.objects.filter(
                organization=self.org_a,
                product=self.wms_product,
            ).count(),
            0,
        )

    # 7. Duplicate pending request is rejected
    def test_07_duplicate_pending_request_is_rejected(self):
        """Second request while first is pending returns 409 DUPLICATE_PRODUCT_REQUEST."""
        self._login_tenant(self.admin_a, self.org_a)
        res1 = self.client.post(
            "/api/v1/marketplace/products/wms/request/",
            data={"notes": "First attempt"},
            content_type="application/json",
        )
        self.assertEqual(res1.status_code, 201)

        res2 = self.client.post(
            "/api/v1/marketplace/products/wms/request/",
            data={"notes": "Duplicate attempt"},
            content_type="application/json",
        )
        self.assertEqual(res2.status_code, 409)
        self.assertEqual(res2.json()["code"], "DUPLICATE_PRODUCT_REQUEST")

    # 8. Public catalog exposes only public data
    def test_08_public_catalog_exposes_only_public_data(self):
        """GET /api/v1/public/marketplace/products/ requires no auth and exposes zero tenant state."""
        self.client.logout()
        response = self.client.get("/api/v1/public/marketplace/products/")
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertTrue(len(data) >= 1)
        for item in data:
            self.assertNotIn("tenant_state", item)
            self.assertNotIn("can_enable", item)
            self.assertNotIn("can_request", item)
            self.assertNotIn("entitlement", item)
            self.assertIn("id", item)
            self.assertIn("code", item)
            self.assertIn("name", item)

    # 9. Cross-tenant isolation is enforced
    def test_09_cross_tenant_isolation_is_enforced(self):
        """User accessing mismatched organization context receives 403 CROSS_TENANT_ACCESS_DENIED."""
        # Admin A has session set to Org B (which they are NOT a member of)
        self.client.force_login(self.admin_a)
        session = self.client.session
        session["active_context_type"] = CONTEXT_TENANT
        session["tenant_organization_id"] = str(self.org_b.id)
        session.save()

        res_cat = self.client.get("/api/v1/marketplace/products/")
        self.assertEqual(res_cat.status_code, 403)
        self.assertEqual(res_cat.json()["code"], "CROSS_TENANT_ACCESS_DENIED")

        res_enable = self.client.post("/api/v1/marketplace/products/lms/enable/")
        self.assertEqual(res_enable.status_code, 403)
        self.assertEqual(res_enable.json()["code"], "CROSS_TENANT_ACCESS_DENIED")

        # Missing tenant context entirely (authenticated without active tenant context)
        self.client.force_login(self.admin_a)
        session = self.client.session
        session.pop("active_context_type", None)
        session.pop("tenant_organization_id", None)
        session.save()

        res_no_ctx = self.client.get("/api/v1/marketplace/products/")
        self.assertEqual(res_no_ctx.status_code, 403)
        self.assertEqual(res_no_ctx.json()["code"], "TENANT_CONTEXT_REQUIRED")

    # 10. Regular member cannot access tenant marketplace
    def test_10_regular_member_cannot_access_tenant_marketplace(self):
        """A regular tenant member cannot access marketplace catalog or operations."""
        self._login_tenant(self.member_a, self.org_a)

        res_cat = self.client.get("/api/v1/marketplace/products/")
        self.assertEqual(res_cat.status_code, 403)
        self.assertEqual(res_cat.json()["code"], "TENANT_ADMIN_REQUIRED")

        res_detail = self.client.get("/api/v1/marketplace/products/lms/")
        self.assertEqual(res_detail.status_code, 403)
        self.assertEqual(res_detail.json()["code"], "TENANT_ADMIN_REQUIRED")

        res_enable = self.client.post(
            "/api/v1/marketplace/products/lms/enable/",
            data={},
            content_type="application/json",
        )
        self.assertEqual(res_enable.status_code, 403)
        self.assertEqual(res_enable.json()["code"], "TENANT_ADMIN_REQUIRED")

