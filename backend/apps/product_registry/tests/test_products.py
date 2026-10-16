"""Product Registry Backend Test Suite.

Verifies authentication, authorization, CSRF protection, data normalization,
model invariants, PostgreSQL constraints, safe exception handling, lifecycle transitions,
and deterministic ordering.
"""

import uuid
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from apps.product_registry.models import Product, ProductStatus

User = get_user_model()


class ProductRegistryTests(TestCase):
    """Test suite for VibeConnect Product Registry endpoints and domain invariants."""

    def setUp(self):
        self.owner = User.objects.create_user(
            email="owner@domain.com",
            password="SecurePassword123!",
            full_name="Platform Owner",
            is_platform_owner=True,
            is_active=True,
        )
        self.non_owner = User.objects.create_user(
            email="regular@domain.com",
            password="SecurePassword123!",
            full_name="Regular User",
            is_platform_owner=False,
            is_active=True,
        )
        self.inactive_owner = User.objects.create_user(
            email="inactive@domain.com",
            password="SecurePassword123!",
            full_name="Inactive Owner",
            is_platform_owner=True,
            is_active=False,
        )
        self.client = APIClient()

    # --- Authentication & Permission Tests ---

    def test_unauthenticated_list_returns_401(self):
        response = self.client.get("/api/v1/products/")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_authenticated_non_owner_list_returns_403(self):
        self.client.force_login(self.non_owner)
        response = self.client.get("/api/v1/products/")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_inactive_session_user_returns_401(self):
        self.client.force_login(self.inactive_owner)
        response = self.client.get("/api/v1/products/")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_active_platform_owner_can_list_empty(self):
        self.client.force_login(self.owner)
        response = self.client.get("/api/v1/products/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 0)
        self.assertEqual(response.data["results"], [])

    # --- Product Creation Tests ---

    def test_platform_owner_creates_product_as_draft(self):
        self.client.force_login(self.owner)
        payload = {
            "code": "lms",
            "name": "Learning Management System",
            "description": "Multi-tenant corporate learning platform.",
        }
        response = self.client.post("/api/v1/products/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["code"], "lms")
        self.assertEqual(response.data["name"], "Learning Management System")
        self.assertEqual(response.data["status"], "draft")
        self.assertEqual(response.data["created_by"]["id"], str(self.owner.id))
        self.assertEqual(response.data["created_by"]["full_name"], "Platform Owner")
        self.assertEqual(response.data["updated_by"]["id"], str(self.owner.id))
        # Ensure email is not leaked in audit summary
        self.assertNotIn("email", response.data["created_by"])

        # Verify database record
        product = Product.objects.get(code="lms")
        self.assertEqual(product.status, ProductStatus.DRAFT)
        self.assertEqual(product.created_by, self.owner)
        self.assertEqual(product.updated_by, self.owner)

    def test_create_product_without_csrf_returns_403(self):
        csrf_client = APIClient(enforce_csrf_checks=True)
        csrf_client.force_login(self.owner)
        payload = {
            "code": "lms",
            "name": "Learning Management System",
        }
        response = csrf_client.post("/api/v1/products/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(Product.objects.count(), 0)

    def test_create_product_with_valid_csrf_succeeds(self):
        csrf_client = APIClient(enforce_csrf_checks=True)
        csrf_client.force_login(self.owner)
        # Fetch CSRF token
        csrf_res = csrf_client.get("/api/v1/auth/csrf/")
        csrf_token = csrf_client.cookies[settings.CSRF_COOKIE_NAME].value

        payload = {
            "code": "crm",
            "name": "Customer Relationship Management",
        }
        response = csrf_client.post(
            "/api/v1/products/",
            payload,
            format="json",
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(Product.objects.filter(code="crm").exists())

    # --- Code Normalization & Validation Tests ---

    def test_code_normalization_uppercase_and_whitespace(self):
        self.client.force_login(self.owner)
        payload = {
            "code": "  HRMS-CORE  ",
            "name": "HR Management System",
        }
        response = self.client.post("/api/v1/products/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["code"], "hrms-core")
        self.assertTrue(Product.objects.filter(code="hrms-core").exists())

    def test_code_with_internal_spaces_rejected(self):
        self.client.force_login(self.owner)
        payload = {
            "code": "my product",
            "name": "My Product",
        }
        response = self.client.post("/api/v1/products/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("code", response.data)

    def test_code_with_invalid_symbols_rejected(self):
        self.client.force_login(self.owner)
        for invalid_code in ["$app!", "app@core", "-leading", "trailing-", "double--sep"]:
            response = self.client.post(
                "/api/v1/products/",
                {"code": invalid_code, "name": "App"},
                format="json",
            )
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, msg=f"Failed for {invalid_code}")

    def test_duplicate_code_case_insensitive_rejected(self):
        self.client.force_login(self.owner)
        Product.objects.create(
            code="vms",
            name="Vendor Management System",
            status=ProductStatus.DRAFT,
            created_by=self.owner,
            updated_by=self.owner,
        )
        response = self.client.post(
            "/api/v1/products/",
            {"code": "VMS", "name": "Duplicate VMS"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("code", response.data)

    def test_whitespace_only_name_rejected(self):
        self.client.force_login(self.owner)
        response = self.client.post(
            "/api/v1/products/",
            {"code": "ats", "name": "   "},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("name", response.data)

    def test_create_with_protected_status_field_rejected(self):
        self.client.force_login(self.owner)
        response = self.client.post(
            "/api/v1/products/",
            {"code": "lms", "name": "LMS", "status": "active"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("status", response.data)

    def test_create_with_protected_audit_field_rejected(self):
        self.client.force_login(self.owner)
        response = self.client.post(
            "/api/v1/products/",
            {"code": "lms", "name": "LMS", "created_by": str(uuid.uuid4())},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("created_by", response.data)

    def test_create_with_unknown_field_rejected(self):
        self.client.force_login(self.owner)
        response = self.client.post(
            "/api/v1/products/",
            {"code": "lms", "name": "LMS", "unknown_field": "val"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("unknown_field", response.data)

    # --- Product Retrieval Tests ---

    def test_retrieve_existing_product_detail(self):
        self.client.force_login(self.owner)
        product = Product.objects.create(
            code="lms",
            name="Learning Management System",
            description="Training suite",
            status=ProductStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )
        response = self.client.get(f"/api/v1/products/{product.id}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["id"], str(product.id))
        self.assertEqual(response.data["code"], "lms")
        self.assertEqual(response.data["status"], "active")
        self.assertEqual(response.data["created_by"]["full_name"], "Platform Owner")

    def test_retrieve_non_existent_uuid_returns_404(self):
        self.client.force_login(self.owner)
        random_uuid = uuid.uuid4()
        response = self.client.get(f"/api/v1/products/{random_uuid}/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_retrieve_malformed_uuid_returns_404(self):
        self.client.force_login(self.owner)
        response = self.client.get("/api/v1/products/invalid-uuid-string/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    # --- Product Partial Update Tests ---

    def test_patch_product_name_and_description_updates_updated_by(self):
        second_owner = User.objects.create_user(
            email="owner2@domain.com",
            password="SecurePassword123!",
            full_name="Second Owner",
            is_platform_owner=True,
            is_active=True,
        )
        product = Product.objects.create(
            code="lms",
            name="LMS Initial",
            description="Initial desc",
            status=ProductStatus.DRAFT,
            created_by=self.owner,
            updated_by=self.owner,
        )

        self.client.force_login(second_owner)
        response = self.client.patch(
            f"/api/v1/products/{product.id}/",
            {"name": "LMS Enterprise", "description": "Updated desc"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["name"], "LMS Enterprise")
        self.assertEqual(response.data["description"], "Updated desc")
        self.assertEqual(response.data["updated_by"]["id"], str(second_owner.id))
        self.assertEqual(response.data["updated_by"]["full_name"], "Second Owner")
        self.assertEqual(response.data["created_by"]["id"], str(self.owner.id))

    def test_patch_without_csrf_returns_403(self):
        product = Product.objects.create(
            code="lms",
            name="LMS",
            status=ProductStatus.DRAFT,
            created_by=self.owner,
            updated_by=self.owner,
        )
        csrf_client = APIClient(enforce_csrf_checks=True)
        csrf_client.force_login(self.owner)
        response = csrf_client.patch(
            f"/api/v1/products/{product.id}/",
            {"name": "New LMS"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        product.refresh_from_db()
        self.assertEqual(product.name, "LMS")

    def test_patch_immutable_code_rejected(self):
        product = Product.objects.create(
            code="lms",
            name="LMS",
            status=ProductStatus.DRAFT,
            created_by=self.owner,
            updated_by=self.owner,
        )
        self.client.force_login(self.owner)
        response = self.client.patch(
            f"/api/v1/products/{product.id}/",
            {"code": "new-lms"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("code", response.data)

    def test_patch_empty_body_rejected(self):
        product = Product.objects.create(
            code="lms",
            name="LMS",
            status=ProductStatus.DRAFT,
            created_by=self.owner,
            updated_by=self.owner,
        )
        self.client.force_login(self.owner)
        response = self.client.patch(f"/api/v1/products/{product.id}/", {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_patch_protected_field_rejected(self):
        product = Product.objects.create(
            code="lms",
            name="LMS",
            status=ProductStatus.DRAFT,
            created_by=self.owner,
            updated_by=self.owner,
        )
        self.client.force_login(self.owner)
        response = self.client.patch(
            f"/api/v1/products/{product.id}/",
            {"created_by": str(uuid.uuid4())},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    # --- Lifecycle State Machine Tests ---

    def test_valid_lifecycle_transitions(self):
        self.client.force_login(self.owner)
        product = Product.objects.create(
            code="lms",
            name="LMS",
            status=ProductStatus.DRAFT,
            created_by=self.owner,
            updated_by=self.owner,
        )

        # 1. Draft -> Active
        res = self.client.patch(f"/api/v1/products/{product.id}/", {"status": "active"}, format="json")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["status"], "active")

        # 2. Active -> Inactive
        res = self.client.patch(f"/api/v1/products/{product.id}/", {"status": "inactive"}, format="json")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["status"], "inactive")

        # 3. Inactive -> Active
        res = self.client.patch(f"/api/v1/products/{product.id}/", {"status": "active"}, format="json")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["status"], "active")

        # 4. Active -> Retired
        res = self.client.patch(f"/api/v1/products/{product.id}/", {"status": "retired"}, format="json")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["status"], "retired")

    def test_idempotent_same_status_patch_allowed_no_op(self):
        self.client.force_login(self.owner)
        product = Product.objects.create(
            code="crm",
            name="CRM",
            status=ProductStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )
        original_updated_at = product.updated_at
        res = self.client.patch(f"/api/v1/products/{product.id}/", {"status": "active"}, format="json")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["status"], "active")
        product.refresh_from_db()
        self.assertEqual(product.updated_at, original_updated_at)

    def test_retired_product_idempotent_metadata_patch_allowed(self):
        self.client.force_login(self.owner)
        product = Product.objects.create(
            code="vms",
            name="Old VMS",
            status=ProductStatus.RETIRED,
            created_by=self.owner,
            updated_by=self.owner,
        )
        res = self.client.patch(
            f"/api/v1/products/{product.id}/",
            {"name": "Archived VMS", "status": "retired"},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["name"], "Archived VMS")
        self.assertEqual(res.data["status"], "retired")

    def test_retired_product_cannot_transition_to_other_status(self):
        self.client.force_login(self.owner)
        product = Product.objects.create(
            code="vms",
            name="VMS",
            status=ProductStatus.RETIRED,
            created_by=self.owner,
            updated_by=self.owner,
        )
        for target_status in ["active", "inactive", "draft"]:
            res = self.client.patch(
                f"/api/v1/products/{product.id}/",
                {"status": target_status},
                format="json",
            )
            self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertIn("status", res.data)

    def test_invalid_status_string_rejected(self):
        self.client.force_login(self.owner)
        product = Product.objects.create(
            code="lms",
            name="LMS",
            status=ProductStatus.DRAFT,
            created_by=self.owner,
            updated_by=self.owner,
        )
        res = self.client.patch(
            f"/api/v1/products/{product.id}/",
            {"status": "bogus_status"},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    # --- Search, Filtering & Pagination Tests ---

    def test_search_by_name_and_code(self):
        self.client.force_login(self.owner)
        Product.objects.create(code="lms-core", name="Learning Hub", created_by=self.owner, updated_by=self.owner)
        Product.objects.create(code="hrms", name="HR Platform", created_by=self.owner, updated_by=self.owner)

        # Search by code
        res = self.client.get("/api/v1/products/?search=lms")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["count"], 1)
        self.assertEqual(res.data["results"][0]["code"], "lms-core")

        # Search by name
        res = self.client.get("/api/v1/products/?search=HR")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["count"], 1)
        self.assertEqual(res.data["results"][0]["code"], "hrms")

    def test_search_overlong_query_rejected(self):
        self.client.force_login(self.owner)
        long_query = "a" * 101
        res = self.client.get(f"/api/v1/products/?search={long_query}")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_filter_by_status(self):
        self.client.force_login(self.owner)
        Product.objects.create(code="p1", name="Product 1", status=ProductStatus.DRAFT, created_by=self.owner, updated_by=self.owner)
        Product.objects.create(code="p2", name="Product 2", status=ProductStatus.ACTIVE, created_by=self.owner, updated_by=self.owner)

        res = self.client.get("/api/v1/products/?status=active")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["count"], 1)
        self.assertEqual(res.data["results"][0]["code"], "p2")

    def test_filter_by_invalid_status_rejected(self):
        self.client.force_login(self.owner)
        res = self.client.get("/api/v1/products/?status=unknown_status")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_pagination_and_invalid_page_size_rejected(self):
        self.client.force_login(self.owner)
        for i in range(15):
            Product.objects.create(code=f"prod-{i}", name=f"Product {i}", created_by=self.owner, updated_by=self.owner)

        # Default page_size=10
        res = self.client.get("/api/v1/products/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["count"], 15)
        self.assertEqual(len(res.data["results"]), 10)

        # Custom valid page_size=5
        res = self.client.get("/api/v1/products/?page_size=5")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res.data["results"]), 5)

        # Negative page_size
        res = self.client.get("/api/v1/products/?page_size=-1")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

        # Zero page_size
        res = self.client.get("/api/v1/products/?page_size=0")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

        # Non-integer page_size
        res = self.client.get("/api/v1/products/?page_size=abc")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_deterministic_ordering_with_tie_breaker(self):
        self.client.force_login(self.owner)
        Product.objects.create(code="b-prod", name="Product B", created_by=self.owner, updated_by=self.owner)
        Product.objects.create(code="a-prod", name="Product A", created_by=self.owner, updated_by=self.owner)

        res = self.client.get("/api/v1/products/?ordering=name")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["results"][0]["name"], "Product A")
        self.assertEqual(res.data["results"][1]["name"], "Product B")

    def test_unsupported_methods_return_405(self):
        self.client.force_login(self.owner)
        product = Product.objects.create(
            code="lms",
            name="LMS",
            status=ProductStatus.DRAFT,
            created_by=self.owner,
            updated_by=self.owner,
        )
        put_res = self.client.put(f"/api/v1/products/{product.id}/", {"name": "LMS"}, format="json")
        self.assertEqual(put_res.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

        del_res = self.client.delete(f"/api/v1/products/{product.id}/")
        self.assertEqual(del_res.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    # --- PostgreSQL Database Constraint Tests ---

    def test_database_constraint_product_code_lower(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Product.objects.create(
                    code="UPPER",
                    name="Upper Product",
                    created_by=self.owner,
                    updated_by=self.owner,
                )

    def test_database_constraint_product_code_format(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Product.objects.create(
                    code="invalid code with space",
                    name="Invalid Space Product",
                    created_by=self.owner,
                    updated_by=self.owner,
                )

    def test_database_constraint_product_status_valid(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Product.objects.create(
                    code="invalid-status-prod",
                    name="Invalid Status",
                    status="non_existent_status",
                    created_by=self.owner,
                    updated_by=self.owner,
                )

    def test_database_constraint_product_code_ci_uniq(self):
        Product.objects.create(
            code="uniq-code",
            name="First Product",
            created_by=self.owner,
            updated_by=self.owner,
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Product.objects.create(
                    code="uniq-code",
                    name="Second Product",
                    created_by=self.owner,
                    updated_by=self.owner,
                )
