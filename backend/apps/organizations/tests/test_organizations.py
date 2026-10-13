"""Organizations Backend Test Suite.

Verifies authentication, authorization, CSRF protection, data normalization,
model invariants, PostgreSQL constraints, safe exception handling, lifecycle transitions,
concurrency safety, and deterministic ordering.
"""

import threading
import uuid
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import IntegrityError, connection, transaction
from django.db.models import ProtectedError
from django.test import TestCase, TransactionTestCase
from rest_framework import status
from rest_framework.test import APIClient

from apps.organizations.models import Organization, OrganizationStatus
from apps.product_registry.models import Product

User = get_user_model()


class OrganizationRegistryTests(TestCase):
    """Test suite for VibeConnect Organization Registry endpoints and domain invariants."""

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
        response = self.client.get("/api/v1/organizations/")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_authenticated_non_owner_returns_403(self):
        self.client.force_login(self.non_owner)
        response = self.client.get("/api/v1/organizations/")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_inactive_owner_returns_401(self):
        self.client.force_login(self.inactive_owner)
        response = self.client.get("/api/v1/organizations/")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    # --- Creation & Defaults Tests ---

    def test_create_organization_success(self):
        self.client.force_login(self.owner)
        payload = {
            "code": "acme-corp",
            "name": "Acme Corporation",
            "description": "Enterprise customer account.",
        }
        response = self.client.post("/api/v1/organizations/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["code"], "acme-corp")
        self.assertEqual(response.data["name"], "Acme Corporation")
        self.assertEqual(response.data["description"], "Enterprise customer account.")
        self.assertEqual(response.data["status"], OrganizationStatus.DRAFT)
        self.assertEqual(response.data["created_by"]["id"], str(self.owner.id))
        self.assertEqual(response.data["created_by"]["full_name"], "Platform Owner")
        self.assertNotIn("email", response.data["created_by"])
        self.assertNotIn("password", response.data["created_by"])

    def test_create_sets_audit_users(self):
        self.client.force_login(self.owner)
        payload = {"code": "beta-org", "name": "Beta Org"}
        response = self.client.post("/api/v1/organizations/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        org = Organization.objects.get(code="beta-org")
        self.assertEqual(org.created_by, self.owner)
        self.assertEqual(org.updated_by, self.owner)

    def test_create_code_normalization(self):
        self.client.force_login(self.owner)
        payload = {"code": "  GAMMA_CORP  ", "name": "Gamma Corp"}
        response = self.client.post("/api/v1/organizations/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["code"], "gamma_corp")

    # --- Code & Field Validation Tests ---

    def test_create_duplicate_code_returns_400(self):
        self.client.force_login(self.owner)
        Organization.objects.create(
            code="delta-org",
            name="Delta Org",
            created_by=self.owner,
            updated_by=self.owner,
        )
        payload = {"code": "delta-org", "name": "Another Delta Org"}
        response = self.client.post("/api/v1/organizations/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("code", response.data)

    def test_create_case_insensitive_duplicate_code_returns_400(self):
        self.client.force_login(self.owner)
        Organization.objects.create(
            code="epsilon-org",
            name="Epsilon Org",
            created_by=self.owner,
            updated_by=self.owner,
        )
        payload = {"code": "EPSILON-ORG", "name": "Different Name"}
        response = self.client.post("/api/v1/organizations/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("code", response.data)

    def test_create_invalid_code_regex_returns_400(self):
        self.client.force_login(self.owner)
        invalid_codes = [
            "-starts-with-hyphen",
            "ends-with-hyphen-",
            "_starts-with-underscore",
            "ends-with-underscore_",
            "has double--hyphen",
            "has double__underscore",
            "has space",
            "has@symbol",
            "has.dots",
            "has/slashes",
        ]
        for code in invalid_codes:
            response = self.client.post(
                "/api/v1/organizations/",
                {"code": code, "name": "Test Org"},
                format="json",
            )
            self.assertEqual(
                response.status_code,
                status.HTTP_400_BAD_REQUEST,
                f"Expected 400 for code: {code}",
            )
            self.assertIn("code", response.data)

    def test_create_blank_code_or_name_returns_400(self):
        self.client.force_login(self.owner)
        res1 = self.client.post("/api/v1/organizations/", {"code": "   ", "name": "Valid Name"}, format="json")
        self.assertEqual(res1.status_code, status.HTTP_400_BAD_REQUEST)

        res2 = self.client.post("/api/v1/organizations/", {"code": "valid-code", "name": "   "}, format="json")
        self.assertEqual(res2.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_exceeding_max_lengths_returns_400(self):
        self.client.force_login(self.owner)
        res1 = self.client.post(
            "/api/v1/organizations/",
            {"code": "a" * 51, "name": "Valid Name"},
            format="json",
        )
        self.assertEqual(res1.status_code, status.HTTP_400_BAD_REQUEST)

        res2 = self.client.post(
            "/api/v1/organizations/",
            {"code": "valid-code", "name": "a" * 151},
            format="json",
        )
        self.assertEqual(res2.status_code, status.HTTP_400_BAD_REQUEST)

        res3 = self.client.post(
            "/api/v1/organizations/",
            {"code": "valid-code", "name": "Valid Name", "description": "a" * 1001},
            format="json",
        )
        self.assertEqual(res3.status_code, status.HTTP_400_BAD_REQUEST)

    # --- Field Whitelisting & Protection Tests ---

    def test_create_rejects_protected_fields(self):
        self.client.force_login(self.owner)
        protected_payloads = [
            {"code": "p-1", "name": "P1", "id": str(uuid.uuid4())},
            {"code": "p-2", "name": "P2", "status": "active"},
            {"code": "p-3", "name": "P3", "created_at": "2026-01-01T00:00:00Z"},
            {"code": "p-4", "name": "P4", "created_by": str(self.owner.id)},
            {"code": "p-5", "name": "P5", "updated_by": str(self.owner.id)},
        ]
        for payload in protected_payloads:
            response = self.client.post("/api/v1/organizations/", payload, format="json")
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_rejects_unknown_fields(self):
        self.client.force_login(self.owner)
        payload = {"code": "valid-org", "name": "Valid Org", "unknown_field": "injected"}
        response = self.client.post("/api/v1/organizations/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("unknown_field", response.data)

    # --- List & Detail Retrieval Tests ---

    def test_list_organizations_pagination(self):
        self.client.force_login(self.owner)
        for i in range(12):
            Organization.objects.create(
                code=f"org-{i:02d}",
                name=f"Organization {i}",
                created_by=self.owner,
                updated_by=self.owner,
            )
        response = self.client.get("/api/v1/organizations/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 12)
        self.assertEqual(len(response.data["results"]), 10)
        self.assertIsNotNone(response.data["next"])
        self.assertIsNone(response.data["previous"])

    def test_retrieve_organization_detail(self):
        self.client.force_login(self.owner)
        org = Organization.objects.create(
            code="detail-org",
            name="Detail Org",
            description="Detailed account context.",
            created_by=self.owner,
            updated_by=self.owner,
        )
        response = self.client.get(f"/api/v1/organizations/{org.id}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["id"], str(org.id))
        self.assertEqual(response.data["code"], "detail-org")
        self.assertEqual(response.data["name"], "Detail Org")
        self.assertEqual(response.data["description"], "Detailed account context.")
        self.assertEqual(response.data["created_by"]["id"], str(self.owner.id))
        self.assertEqual(response.data["created_by"]["full_name"], "Platform Owner")
        self.assertNotIn("email", response.data["created_by"])

    def test_retrieve_nonexistent_uuid_returns_404(self):
        self.client.force_login(self.owner)
        random_id = uuid.uuid4()
        response = self.client.get(f"/api/v1/organizations/{random_id}/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    # --- Search, Filter & Ordering Tests ---

    def test_search_by_name_and_code(self):
        self.client.force_login(self.owner)
        Organization.objects.create(code="alpha-inc", name="First Alphabet", created_by=self.owner, updated_by=self.owner)
        Organization.objects.create(code="beta-corp", name="Second Beta", created_by=self.owner, updated_by=self.owner)

        res_code = self.client.get("/api/v1/organizations/?search=alpha")
        self.assertEqual(res_code.status_code, status.HTTP_200_OK)
        self.assertEqual(res_code.data["count"], 1)
        self.assertEqual(res_code.data["results"][0]["code"], "alpha-inc")

        res_name = self.client.get("/api/v1/organizations/?search=Alphabet")
        self.assertEqual(res_name.status_code, status.HTTP_200_OK)
        self.assertEqual(res_name.data["count"], 1)

    def test_search_max_length_validation(self):
        self.client.force_login(self.owner)
        response = self.client.get(f"/api/v1/organizations/?search={'a' * 101}")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("search", response.data)

    def test_search_blank_or_whitespace_ignored(self):
        self.client.force_login(self.owner)
        Organization.objects.create(code="test-org", name="Test Org", created_by=self.owner, updated_by=self.owner)
        response = self.client.get("/api/v1/organizations/?search=   ")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["count"], 1)

    def test_filter_by_status(self):
        self.client.force_login(self.owner)
        Organization.objects.create(code="draft-org", name="Draft Org", status=OrganizationStatus.DRAFT, created_by=self.owner, updated_by=self.owner)
        Organization.objects.create(code="active-org", name="Active Org", status=OrganizationStatus.ACTIVE, created_by=self.owner, updated_by=self.owner)

        res = self.client.get("/api/v1/organizations/?status=active")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["count"], 1)
        self.assertEqual(res.data["results"][0]["code"], "active-org")

    def test_filter_invalid_status_returns_400(self):
        self.client.force_login(self.owner)
        response = self.client.get("/api/v1/organizations/?status=nonexistent")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("status", response.data)

    def test_deterministic_ordering(self):
        self.client.force_login(self.owner)
        o1 = Organization.objects.create(code="a-org", name="Alpha", created_by=self.owner, updated_by=self.owner)
        o2 = Organization.objects.create(code="z-org", name="Zulu", created_by=self.owner, updated_by=self.owner)

        res_asc = self.client.get("/api/v1/organizations/?ordering=name")
        self.assertEqual(res_asc.status_code, status.HTTP_200_OK)
        self.assertEqual(res_asc.data["results"][0]["code"], "a-org")

        res_desc = self.client.get("/api/v1/organizations/?ordering=-name")
        self.assertEqual(res_desc.status_code, status.HTTP_200_OK)
        self.assertEqual(res_desc.data["results"][0]["code"], "z-org")

    def test_invalid_ordering_returns_400(self):
        self.client.force_login(self.owner)
        response = self.client.get("/api/v1/organizations/?ordering=secret_column")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("ordering", response.data)

    # --- Pagination Edge Cases ---

    def test_pagination_invalid_page_size_returns_400(self):
        self.client.force_login(self.owner)
        res1 = self.client.get("/api/v1/organizations/?page_size=-5")
        self.assertEqual(res1.status_code, status.HTTP_400_BAD_REQUEST)

        res2 = self.client.get("/api/v1/organizations/?page_size=notanumber")
        self.assertEqual(res2.status_code, status.HTTP_400_BAD_REQUEST)

    def test_pagination_oversized_page_size_clamped(self):
        self.client.force_login(self.owner)
        for i in range(5):
            Organization.objects.create(code=f"org-{i}", name=f"Org {i}", created_by=self.owner, updated_by=self.owner)
        response = self.client.get("/api/v1/organizations/?page_size=200")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 5)

    def test_pagination_out_of_range_page_returns_404(self):
        self.client.force_login(self.owner)
        response = self.client.get("/api/v1/organizations/?page=999")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    # --- Partial Update (PATCH) Tests ---

    def test_patch_organization_name_and_description(self):
        self.client.force_login(self.owner)
        org = Organization.objects.create(
            code="edit-org",
            name="Old Name",
            description="Old Description",
            created_by=self.owner,
            updated_by=self.owner,
        )
        response = self.client.patch(
            f"/api/v1/organizations/{org.id}/",
            {"name": "New Name", "description": "New Description"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["name"], "New Name")
        self.assertEqual(response.data["description"], "New Description")

    def test_patch_rejects_immutable_code(self):
        self.client.force_login(self.owner)
        org = Organization.objects.create(code="imm-org", name="Org", created_by=self.owner, updated_by=self.owner)
        response = self.client.patch(
            f"/api/v1/organizations/{org.id}/",
            {"code": "new-code"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("code", response.data)

    def test_patch_rejects_empty_payload(self):
        self.client.force_login(self.owner)
        org = Organization.objects.create(code="empty-org", name="Org", created_by=self.owner, updated_by=self.owner)
        response = self.client.patch(f"/api/v1/organizations/{org.id}/", {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("detail", response.data)

    def test_patch_rejects_protected_fields(self):
        self.client.force_login(self.owner)
        org = Organization.objects.create(code="prot-org", name="Org", created_by=self.owner, updated_by=self.owner)
        response = self.client.patch(
            f"/api/v1/organizations/{org.id}/",
            {"created_at": "2026-01-01T00:00:00Z"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_patch_rejects_unknown_fields(self):
        self.client.force_login(self.owner)
        org = Organization.objects.create(code="unk-org", name="Org", created_by=self.owner, updated_by=self.owner)
        response = self.client.patch(
            f"/api/v1/organizations/{org.id}/",
            {"custom_key": "val"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_patch_no_op_preserves_timestamps_and_updater(self):
        self.client.force_login(self.owner)
        org = Organization.objects.create(
            code="noop-org",
            name="Noop Name",
            description="Noop Desc",
            status=OrganizationStatus.DRAFT,
            created_by=self.owner,
            updated_by=self.owner,
        )
        initial_updated_at = org.updated_at
        response = self.client.patch(
            f"/api/v1/organizations/{org.id}/",
            {"name": "Noop Name", "description": "Noop Desc", "status": OrganizationStatus.DRAFT},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        org.refresh_from_db()
        self.assertEqual(org.updated_at, initial_updated_at)

    # --- Lifecycle State Machine Tests ---

    def test_lifecycle_draft_to_active_success(self):
        self.client.force_login(self.owner)
        org = Organization.objects.create(code="t-org-1", name="Org 1", status=OrganizationStatus.DRAFT, created_by=self.owner, updated_by=self.owner)
        response = self.client.patch(f"/api/v1/organizations/{org.id}/", {"status": OrganizationStatus.ACTIVE}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], OrganizationStatus.ACTIVE)

    def test_lifecycle_draft_to_retired_success(self):
        self.client.force_login(self.owner)
        org = Organization.objects.create(code="t-org-2", name="Org 2", status=OrganizationStatus.DRAFT, created_by=self.owner, updated_by=self.owner)
        response = self.client.patch(f"/api/v1/organizations/{org.id}/", {"status": OrganizationStatus.RETIRED}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], OrganizationStatus.RETIRED)

    def test_lifecycle_draft_to_suspended_rejected(self):
        self.client.force_login(self.owner)
        org = Organization.objects.create(code="t-org-3", name="Org 3", status=OrganizationStatus.DRAFT, created_by=self.owner, updated_by=self.owner)
        response = self.client.patch(f"/api/v1/organizations/{org.id}/", {"status": OrganizationStatus.SUSPENDED}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("status", response.data)

    def test_lifecycle_active_to_suspended_success(self):
        self.client.force_login(self.owner)
        org = Organization.objects.create(code="t-org-4", name="Org 4", status=OrganizationStatus.ACTIVE, created_by=self.owner, updated_by=self.owner)
        response = self.client.patch(f"/api/v1/organizations/{org.id}/", {"status": OrganizationStatus.SUSPENDED}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], OrganizationStatus.SUSPENDED)

    def test_lifecycle_active_to_retired_success(self):
        self.client.force_login(self.owner)
        org = Organization.objects.create(code="t-org-5", name="Org 5", status=OrganizationStatus.ACTIVE, created_by=self.owner, updated_by=self.owner)
        response = self.client.patch(f"/api/v1/organizations/{org.id}/", {"status": OrganizationStatus.RETIRED}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], OrganizationStatus.RETIRED)

    def test_lifecycle_suspended_to_active_success(self):
        self.client.force_login(self.owner)
        org = Organization.objects.create(code="t-org-6", name="Org 6", status=OrganizationStatus.SUSPENDED, created_by=self.owner, updated_by=self.owner)
        response = self.client.patch(f"/api/v1/organizations/{org.id}/", {"status": OrganizationStatus.ACTIVE}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], OrganizationStatus.ACTIVE)

    def test_lifecycle_suspended_to_retired_success(self):
        self.client.force_login(self.owner)
        org = Organization.objects.create(code="t-org-7", name="Org 7", status=OrganizationStatus.SUSPENDED, created_by=self.owner, updated_by=self.owner)
        response = self.client.patch(f"/api/v1/organizations/{org.id}/", {"status": OrganizationStatus.RETIRED}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], OrganizationStatus.RETIRED)

    def test_lifecycle_retired_record_read_only_rejection(self):
        self.client.force_login(self.owner)
        org = Organization.objects.create(code="t-org-8", name="Org 8", status=OrganizationStatus.RETIRED, created_by=self.owner, updated_by=self.owner)
        response = self.client.patch(f"/api/v1/organizations/{org.id}/", {"name": "New Name After Retirement"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("status", response.data)

    def test_lifecycle_same_status_no_op(self):
        self.client.force_login(self.owner)
        org = Organization.objects.create(code="t-org-9", name="Org 9", status=OrganizationStatus.ACTIVE, created_by=self.owner, updated_by=self.owner)
        response = self.client.patch(f"/api/v1/organizations/{org.id}/", {"status": OrganizationStatus.ACTIVE}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], OrganizationStatus.ACTIVE)

    # --- HTTP Methods Enforcement ---

    def test_put_method_returns_405(self):
        self.client.force_login(self.owner)
        org = Organization.objects.create(code="put-org", name="Org", created_by=self.owner, updated_by=self.owner)
        response = self.client.put(f"/api/v1/organizations/{org.id}/", {"name": "Put Name"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_delete_method_returns_405(self):
        self.client.force_login(self.owner)
        org = Organization.objects.create(code="del-org", name="Org", created_by=self.owner, updated_by=self.owner)
        response = self.client.delete(f"/api/v1/organizations/{org.id}/")
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_head_and_options_methods(self):
        self.client.force_login(self.owner)
        res_head = self.client.head("/api/v1/organizations/")
        self.assertEqual(res_head.status_code, status.HTTP_200_OK)

        res_opt = self.client.options("/api/v1/organizations/")
        self.assertEqual(res_opt.status_code, status.HTTP_200_OK)

    # --- Direct Database Constraint Tests (Bypass Serializer) ---

    def test_db_constraint_unique_code_case_insensitive(self):
        Organization.objects.create(code="db-unique", name="Org 1", created_by=self.owner, updated_by=self.owner)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Organization.objects.create(code="DB-UNIQUE", name="Org 2", created_by=self.owner, updated_by=self.owner)

    def test_db_constraint_lowercase_code_enforced(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Organization.objects.create(code="UPPERCASE-CODE", name="Org", created_by=self.owner, updated_by=self.owner)

    def test_db_constraint_code_format_enforced(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Organization.objects.create(code="invalid--code", name="Org", created_by=self.owner, updated_by=self.owner)

    def test_db_constraint_status_valid_enforced(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Organization.objects.create(code="valid-code", name="Org", status="bogus_status", created_by=self.owner, updated_by=self.owner)

    def test_db_foreign_key_protect_audit_users(self):
        org = Organization.objects.create(code="fk-org", name="Org", created_by=self.owner, updated_by=self.owner)
        with self.assertRaises(ProtectedError):
            self.owner.delete()

    # --- Product Registry Regression ---

    def test_product_registry_unaffected(self):
        self.client.force_login(self.owner)
        res = self.client.get("/api/v1/products/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)


class OrganizationConcurrencyTests(TransactionTestCase):
    """Concurrency and transactional row locking tests for Organization updates."""

    def setUp(self):
        self.owner = User.objects.create_user(
            email="conc_owner@domain.com",
            password="SecurePassword123!",
            full_name="Concurrency Owner",
            is_platform_owner=True,
            is_active=True,
        )

    def test_concurrent_patch_select_for_update_lifecycle_safety(self):
        """Verifies that select_for_update prevents invalid state transitions during race conditions."""
        org = Organization.objects.create(
            code="conc-org",
            name="Concurrent Org",
            status=OrganizationStatus.DRAFT,
            created_by=self.owner,
            updated_by=self.owner,
        )

        event_a_locked = threading.Event()
        event_a_committed = threading.Event()
        result_b = {}

        def thread_a_retires():
            connection.connect()
            try:
                with transaction.atomic():
                    locked_org = Organization.objects.select_for_update().get(pk=org.pk)
                    event_a_locked.set()
                    # Simulate processing delay while holding row lock
                    event_a_committed.wait(timeout=2.0)
                    locked_org.status = OrganizationStatus.RETIRED
                    locked_org.save(update_fields=["status", "updated_at"])
            finally:
                connection.close()

        def thread_b_attempts_update():
            connection.connect()
            try:
                # Wait until thread A has acquired select_for_update lock
                event_a_locked.wait(timeout=2.0)
                client = APIClient()
                client.force_login(self.owner)

                # Signal thread A to commit and release lock
                event_a_committed.set()

                # Thread B should block until thread A commits, then read the RETIRED state and fail
                response = client.patch(
                    f"/api/v1/organizations/{org.id}/",
                    {"status": OrganizationStatus.ACTIVE},
                    format="json",
                )
                result_b["status_code"] = response.status_code
                result_b["data"] = response.data
            finally:
                connection.close()

        t_a = threading.Thread(target=thread_a_retires)
        t_b = threading.Thread(target=thread_b_attempts_update)

        t_a.start()
        t_b.start()

        t_a.join(timeout=3.0)
        t_b.join(timeout=3.0)

        # Thread B must have been rejected because the row became RETIRED
        self.assertEqual(result_b.get("status_code"), status.HTTP_400_BAD_REQUEST)
        self.assertIn("status", result_b.get("data", {}))

    def tearDown(self):
        from django.db import connections
        connections.close_all()
        super().tearDown()


class TestOrganizationAccessControlProvisioning(TestCase):
    """Verifies Phase 2E default access control provisioning during organization creation."""

    def setUp(self):
        self.owner = User.objects.create_user(
            email="owner_prov@domain.com",
            password="SecurePassword123!",
            full_name="Platform Owner",
            is_platform_owner=True,
            is_active=True,
        )
        self.client = APIClient()
        self.client.force_login(self.owner)

    def test_api_organization_creation_creates_exact_default_policies_and_ceilings(self):
        from apps.access_control.models import (
            OrganizationConsoleModulePolicy,
            OrganizationPermissionCeiling,
        )
        from apps.auditlog.models import AuditAction, AuditLog

        payload = {"code": "prov-org", "name": "Provisioning Org"}
        response = self.client.post("/api/v1/organizations/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        org = Organization.objects.get(code="prov-org")

        # Verify exact default module policies
        policies = list(
            OrganizationConsoleModulePolicy.objects.filter(organization=org).values_list(
                "console_module__key", "is_enabled"
            )
        )
        self.assertEqual(len(policies), 3)
        policy_dict = dict(policies)
        self.assertEqual(policy_dict, {"tenant_landing": True, "tenant_roles": True, "tenant_my_products": True})

        # Ensure no po_* policies created
        po_policies = OrganizationConsoleModulePolicy.objects.filter(
            organization=org, console_module__key__startswith="po_"
        )
        self.assertFalse(po_policies.exists())

        # Verify exact default permission ceilings
        ceilings = list(
            OrganizationPermissionCeiling.objects.filter(organization=org).values_list(
                "permission__key", "is_allowed"
            )
        )
        self.assertEqual(len(ceilings), 4)
        ceiling_dict = dict(ceilings)
        self.assertEqual(
            ceiling_dict,
            {"roles.view": True, "roles.manage": True, "roles.assign": True, "products.view": True},
        )

        # Verify single audit event: ORGANIZATION_CREATED only
        audit_events = AuditLog.objects.filter(organization_id=org.id)
        self.assertEqual(audit_events.count(), 1)
        self.assertEqual(audit_events.first().action, AuditAction.ORGANIZATION_CREATED)
        self.assertFalse(
            AuditLog.objects.filter(
                organization_id=org.id,
                action__in=[
                    AuditAction.CONSOLE_MODULE_POLICY_CHANGED,
                    AuditAction.PERMISSION_CEILING_CHANGED,
                ],
            ).exists()
        )

    def test_provisioning_and_organization_creation_rollback_when_registry_unavailable(self):
        from apps.access_control.models import ConsoleModule
        from apps.auditlog.models import AuditAction, AuditLog

        # Deactivate required module tenant_roles
        module = ConsoleModule.objects.get(key="tenant_roles")
        module.is_active = False
        module.save(update_fields=["is_active"])

        try:
            payload = {"code": "fail-org", "name": "Fail Org"}
            response = self.client.post("/api/v1/organizations/", payload, format="json")
            self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)

            # Organization must not exist (rolled back)
            self.assertFalse(Organization.objects.filter(code="fail-org").exists())

            # No audit event recorded
            self.assertFalse(
                AuditLog.objects.filter(
                    action=AuditAction.ORGANIZATION_CREATED,
                    target_repr="Fail Org",
                ).exists()
            )
        finally:
            module.is_active = True
            module.save(update_fields=["is_active"])

