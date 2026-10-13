from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.assignments.models import UserProductAssignment
from apps.developer_console.models import DeveloperApplication
from apps.developer_console.services.key_service import generate_api_key
from apps.entitlements.models import EntitlementStatus, OrganizationProductEntitlement
from apps.organizations.models import MembershipStatus, MembershipType, Organization, OrganizationMembership, OrganizationStatus
from apps.product_registry.models import Product, ProductStatus

User = get_user_model()


class DeveloperReadApiTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()

        # Admin user
        self.user_admin = User.objects.create_user(
            email="admin@tenant1.local",
            password="TestPassword123!",
            full_name="Admin One",
        )
        # End user
        self.user_member = User.objects.create_user(
            email="member@tenant1.local",
            password="TestPassword123!",
            full_name="Member One",
        )

        # Tenant 1 (Alpha)
        self.org1 = Organization.objects.create(
            code="tenant_alpha",
            name="Tenant Alpha",
            status=OrganizationStatus.ACTIVE,
            created_by=self.user_admin,
            updated_by=self.user_admin,
        )
        self.membership_admin = OrganizationMembership.objects.create(
            organization=self.org1,
            user=self.user_admin,
            membership_type=MembershipType.MEMBER,
            status=MembershipStatus.ACTIVE,
            joined_at=timezone.now(),
        )
        self.membership_member = OrganizationMembership.objects.create(
            organization=self.org1,
            user=self.user_member,
            membership_type=MembershipType.MEMBER,
            status=MembershipStatus.ACTIVE,
            joined_at=timezone.now(),
        )

        # Tenant 2 (Beta) for cross-tenant isolation testing
        self.org2 = Organization.objects.create(
            code="tenant_beta",
            name="Tenant Beta",
            status=OrganizationStatus.ACTIVE,
            created_by=self.user_admin,
            updated_by=self.user_admin,
        )

        # Developer Application for Tenant 1
        self.app1 = DeveloperApplication.objects.create(
            organization=self.org1,
            name="Alpha Application",
            created_by=self.user_admin,
            status="active",
        )

        # Full-scoped Key for Tenant 1
        self.key1_obj, self.key1_raw = generate_api_key(
            name="Full Scope Key",
            application=self.app1,
            scopes=[
                "catalog:read",
                "organization:read",
                "entitlements:read",
                "assignments:read",
            ],
        )

        # Products
        self.active_prod = Product.objects.create(
            code="lms",
            name="Learning Management System",
            description="LMS platform",
            status=ProductStatus.ACTIVE,
            created_by=self.user_admin,
            updated_by=self.user_admin,
        )
        self.draft_prod = Product.objects.create(
            code="draft_tool",
            name="Draft Tool",
            description="Under development",
            status=ProductStatus.DRAFT,
            created_by=self.user_admin,
            updated_by=self.user_admin,
        )

        # Entitlements for Tenant 1
        self.ent1 = OrganizationProductEntitlement.objects.create(
            organization=self.org1,
            product=self.active_prod,
            status=EntitlementStatus.ACTIVE,
            created_by=self.user_admin,
            updated_by=self.user_admin,
        )
        # Entitlements for Tenant 2 (must not be visible to Tenant 1)
        self.ent2 = OrganizationProductEntitlement.objects.create(
            organization=self.org2,
            product=self.active_prod,
            status=EntitlementStatus.ACTIVE,
            created_by=self.user_admin,
            updated_by=self.user_admin,
        )

        # Assignment for Tenant 1
        self.assign1 = UserProductAssignment.objects.create(
            organization=self.org1,
            user=self.user_member,
            membership=self.membership_member,
            product=self.active_prod,
            status="active",
            created_by=self.user_admin,
            updated_by=self.user_admin,
        )

    def tearDown(self):
        cache.clear()

    def test_catalog_products_read_and_visibility(self):
        # 1. Unauthenticated -> 401
        res = self.client.get("/api/v1/developer/catalog/products/")
        self.assertEqual(res.status_code, 401)

        # 2. Authenticated with catalog:read
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.key1_raw}")
        res = self.client.get("/api/v1/developer/catalog/products/")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("results", data)
        self.assertIn("count", data)

        product_codes = [p["code"] for p in data["results"]]
        # Active product must appear
        self.assertIn("lms", product_codes)
        # Draft product must NOT appear
        self.assertNotIn("draft_tool", product_codes)

    def test_organization_read_and_data_minimization(self):
        # Authenticated with organization:read
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.key1_raw}")
        res = self.client.get("/api/v1/developer/organization/")
        self.assertEqual(res.status_code, 200)
        data = res.json()

        # Check tenant identity matches Tenant 1
        self.assertEqual(data["id"], str(self.org1.id))
        self.assertEqual(data["code"], "tenant_alpha")
        self.assertEqual(data["name"], "Tenant Alpha")
        self.assertEqual(data["status"], "active")
        self.assertIn("created_at", data)

        # Verify no sensitive billing/internal data leaked
        self.assertNotIn("billing", data)
        self.assertNotIn("invoice", data)
        self.assertNotIn("created_by", data)
        self.assertNotIn("updated_by", data)

    def test_entitlements_read_and_tenant_isolation(self):
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.key1_raw}")
        res = self.client.get("/api/v1/developer/entitlements/")
        self.assertEqual(res.status_code, 200)
        data = res.json()

        self.assertIn("results", data)
        results = data["results"]
        # Must only return Tenant 1's entitlement
        ent_ids = [item["id"] for item in results]
        self.assertIn(str(self.ent1.id), ent_ids)
        self.assertNotIn(str(self.ent2.id), ent_ids)

        # Data minimization check
        item = results[0]
        self.assertEqual(item["product_code"], "lms")
        self.assertEqual(item["status"], "active")
        self.assertIn("granted_at", item)
        self.assertNotIn("connector", item)

    def test_assignments_read_and_tenant_isolation(self):
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.key1_raw}")
        res = self.client.get("/api/v1/developer/assignments/")
        self.assertEqual(res.status_code, 200)
        data = res.json()

        self.assertIn("results", data)
        results = data["results"]
        self.assertEqual(len(results), 1)

        item = results[0]
        self.assertEqual(item["id"], str(self.assign1.id))
        self.assertEqual(item["user_id"], str(self.user_member.id))
        self.assertEqual(item["user_email"], "member@tenant1.local")
        self.assertEqual(item["user_full_name"], "Member One")
        self.assertEqual(item["product_code"], "lms")
        self.assertEqual(item["status"], "active")

        # Data minimization check: no passwords, tokens, or roles
        self.assertNotIn("password", item)
        self.assertNotIn("token", item)
        self.assertNotIn("membership_type", item)

    def test_scope_enforcement_across_endpoints(self):
        # Create key with ONLY organization:read
        _, key_limited = generate_api_key(
            name="Org Only Key",
            application=self.app1,
            scopes=["organization:read"],
        )
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {key_limited}")

        # organization/ works
        res = self.client.get("/api/v1/developer/organization/")
        self.assertEqual(res.status_code, 200)

        # catalog/products/ fails with 403 INSUFFICIENT_SCOPE
        res = self.client.get("/api/v1/developer/catalog/products/")
        self.assertEqual(res.status_code, 403)
        self.assertEqual(res.json().get("error"), "INSUFFICIENT_SCOPE")

        # entitlements/ fails with 403 INSUFFICIENT_SCOPE
        res = self.client.get("/api/v1/developer/entitlements/")
        self.assertEqual(res.status_code, 403)
        self.assertEqual(res.json().get("error"), "INSUFFICIENT_SCOPE")

        # assignments/ fails with 403 INSUFFICIENT_SCOPE
        res = self.client.get("/api/v1/developer/assignments/")
        self.assertEqual(res.status_code, 403)
        self.assertEqual(res.json().get("error"), "INSUFFICIENT_SCOPE")
