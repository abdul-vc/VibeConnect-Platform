"""Comprehensive PostgreSQL-backed test suite for OrganizationProductEntitlement.

Covers authentication, authorization, validation, parent eligibility, conditional uniqueness,
lifecycle state machine, real concurrency locking, N+1 query bounding, and data minimization.
"""

import threading
import unittest.mock as mock
import uuid
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import IntegrityError, connection, connections, transaction
from django.db.models import ProtectedError
from django.test import TestCase, TransactionTestCase
from rest_framework import status
from rest_framework.test import APIClient

from apps.entitlements.models import EntitlementStatus, OrganizationProductEntitlement
from apps.organizations.models import Organization, OrganizationStatus
from apps.product_registry.models import Product, ProductStatus

User = get_user_model()


class EntitlementTestBase:
    """Helper mixin to set up users, active parents, and authenticated clients."""

    def create_owner(self, email="owner@vibeconnect.io", name="Platform Owner"):
        return User.objects.create_user(
            email=email,
            password="SecurePassword123!",
            full_name=name,
            is_platform_owner=True,
            is_active=True,
        )

    def create_member(self, email="member@vibeconnect.io", name="Regular User"):
        return User.objects.create_user(
            email=email,
            password="SecurePassword123!",
            full_name=name,
            is_platform_owner=False,
            is_active=True,
        )

    def create_org(self, code="acme", name="Acme Corp", status=OrganizationStatus.ACTIVE, user=None):
        creator = user or self.owner
        return Organization.objects.create(
            code=code,
            name=name,
            status=status,
            created_by=creator,
            updated_by=creator,
        )

    def create_prod(self, code="lms-test", name="LMS Test", status=ProductStatus.ACTIVE, user=None):
        creator = user or self.owner
        return Product.objects.create(
            code=code,
            name=name,
            status=status,
            created_by=creator,
            updated_by=creator,
        )


class EntitlementAPITests(TestCase, EntitlementTestBase):
    """Functional API and model tests for OrganizationProductEntitlement."""

    def setUp(self):
        self.owner = self.create_owner()
        self.member = self.create_member()
        self.org = self.create_org()
        self.prod = self.create_prod()
        self.client = APIClient()

    # -------------------------------------------------------------------------
    # 1. Authentication & Authorization
    # -------------------------------------------------------------------------

    def test_unauthenticated_requests_return_401(self):
        url = "/api/v1/organization-product-entitlements/"
        self.assertEqual(self.client.get(url).status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(
            self.client.post(url, {"organization_id": str(self.org.id), "product_id": str(self.prod.id)}, format="json").status_code,
            status.HTTP_401_UNAUTHORIZED,
        )
        fake_id = uuid.uuid4()
        self.assertEqual(self.client.get(f"{url}{fake_id}/").status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(
            self.client.patch(f"{url}{fake_id}/", {"status": "active"}, format="json").status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

    def test_inactive_platform_owner_returns_401(self):
        self.owner.is_active = False
        self.owner.save(update_fields=["is_active"])
        self.client.force_login(self.owner)
        res = self.client.get("/api/v1/organization-product-entitlements/")
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_authenticated_non_owner_returns_403(self):
        self.client.force_login(self.member)
        res = self.client.get("/api/v1/organization-product-entitlements/")
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_csrf_protection_enforced_on_mutations(self):
        csrf_client = APIClient(enforce_csrf_checks=True)
        csrf_client.force_login(self.owner)

        # 1. Mutation without CSRF token header returns 403
        res_no_csrf = csrf_client.post(
            "/api/v1/organization-product-entitlements/",
            {"organization_id": str(self.org.id), "product_id": str(self.prod.id)},
            format="json",
        )
        self.assertEqual(res_no_csrf.status_code, status.HTTP_403_FORBIDDEN)

        # 2. Mutation with valid CSRF token header succeeds
        csrf_resp = csrf_client.get("/api/v1/auth/csrf/")
        csrf_cookie_name = settings.CSRF_COOKIE_NAME
        self.assertIn(csrf_cookie_name, csrf_resp.cookies)
        csrf_token = csrf_resp.cookies[csrf_cookie_name].value

        res_with_csrf = csrf_client.post(
            "/api/v1/organization-product-entitlements/",
            {"organization_id": str(self.org.id), "product_id": str(self.prod.id)},
            format="json",
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        self.assertEqual(res_with_csrf.status_code, status.HTTP_201_CREATED)

    def test_csrf_protection_enforced_on_patch_mutations(self):
        """Directly verifies CSRF protection on PATCH requests."""
        csrf_client = APIClient(enforce_csrf_checks=True)
        csrf_client.force_login(self.owner)

        ent = OrganizationProductEntitlement.objects.create(
            organization=self.org,
            product=self.prod,
            status=EntitlementStatus.DRAFT,
            created_by=self.owner,
            updated_by=self.owner,
        )

        # 1. PATCH without CSRF token returns 403
        res_no_csrf = csrf_client.patch(
            f"/api/v1/organization-product-entitlements/{ent.id}/",
            {"status": "active"},
            format="json",
        )
        self.assertEqual(res_no_csrf.status_code, status.HTTP_403_FORBIDDEN)

        # 2. PATCH with valid CSRF token header succeeds
        csrf_resp = csrf_client.get("/api/v1/auth/csrf/")
        csrf_cookie_name = settings.CSRF_COOKIE_NAME
        self.assertIn(csrf_cookie_name, csrf_resp.cookies)
        csrf_token = csrf_resp.cookies[csrf_cookie_name].value

        res_with_csrf = csrf_client.patch(
            f"/api/v1/organization-product-entitlements/{ent.id}/",
            {"status": "active"},
            format="json",
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        self.assertEqual(res_with_csrf.status_code, status.HTTP_200_OK)
        self.assertEqual(res_with_csrf.data["status"], "active")

    # -------------------------------------------------------------------------
    # 2. Creation & Validation
    # -------------------------------------------------------------------------

    def test_create_draft_entitlement_success(self):
        self.client.force_login(self.owner)
        res = self.client.post(
            "/api/v1/organization-product-entitlements/",
            {"organization_id": str(self.org.id), "product_id": str(self.prod.id)},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res.data["status"], EntitlementStatus.DRAFT)
        self.assertEqual(res.data["organization"]["id"], str(self.org.id))
        self.assertEqual(res.data["product"]["id"], str(self.prod.id))
        self.assertEqual(res.data["created_by"]["id"], str(self.owner.id))
        self.assertEqual(res.data["created_by"]["full_name"], self.owner.full_name)

    def test_create_rejects_client_supplied_status(self):
        self.client.force_login(self.owner)
        res = self.client.post(
            "/api/v1/organization-product-entitlements/",
            {
                "organization_id": str(self.org.id),
                "product_id": str(self.prod.id),
                "status": "active",
            },
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("status", res.data)

    def test_create_rejects_protected_and_unknown_fields_matrix(self):
        """Verifies that POST rejects status, protected fields, embedded entities, and unknown fields."""
        self.client.force_login(self.owner)
        forbidden_fields = [
            ("id", str(uuid.uuid4())),
            ("status", "active"),
            ("created_at", "2026-01-01T00:00:00Z"),
            ("updated_at", "2026-01-01T00:00:00Z"),
            ("created_by", str(uuid.uuid4())),
            ("updated_by", str(uuid.uuid4())),
            ("organization", {"id": str(self.org.id)}),
            ("product", {"id": str(self.prod.id)}),
            ("unknown_field", "value"),
        ]

        for field_name, field_val in forbidden_fields:
            with self.subTest(field=field_name):
                res = self.client.post(
                    "/api/v1/organization-product-entitlements/",
                    {
                        "organization_id": str(self.org.id),
                        "product_id": str(self.prod.id),
                        field_name: field_val,
                    },
                    format="json",
                )
                self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST, f"Field '{field_name}' was not rejected")
                self.assertIn(field_name, res.data)

    def test_create_rejects_non_active_organization(self):
        self.client.force_login(self.owner)
        for non_active_status in [OrganizationStatus.DRAFT, OrganizationStatus.SUSPENDED, OrganizationStatus.RETIRED]:
            ineligible_org = self.create_org(code=f"org-{non_active_status}", status=non_active_status)
            res = self.client.post(
                "/api/v1/organization-product-entitlements/",
                {"organization_id": str(ineligible_org.id), "product_id": str(self.prod.id)},
                format="json",
            )
            self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertIn("organization_id", res.data)

    def test_create_rejects_non_active_product(self):
        self.client.force_login(self.owner)
        for non_active_status in [ProductStatus.DRAFT, ProductStatus.INACTIVE, ProductStatus.RETIRED]:
            ineligible_prod = self.create_prod(code=f"prod-{non_active_status}", status=non_active_status)
            res = self.client.post(
                "/api/v1/organization-product-entitlements/",
                {"organization_id": str(self.org.id), "product_id": str(ineligible_prod.id)},
                format="json",
            )
            self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertIn("product_id", res.data)

    def test_create_rejects_malformed_and_missing_uuids(self):
        self.client.force_login(self.owner)
        # Malformed Organization UUID
        res1 = self.client.post(
            "/api/v1/organization-product-entitlements/",
            {"organization_id": "not-a-uuid", "product_id": str(self.prod.id)},
            format="json",
        )
        self.assertEqual(res1.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("organization_id", res1.data)

        # Missing Organization
        res2 = self.client.post(
            "/api/v1/organization-product-entitlements/",
            {"organization_id": str(uuid.uuid4()), "product_id": str(self.prod.id)},
            format="json",
        )
        self.assertEqual(res2.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("organization_id", res2.data)

        # Malformed Product UUID
        res3 = self.client.post(
            "/api/v1/organization-product-entitlements/",
            {"organization_id": str(self.org.id), "product_id": "not-a-uuid"},
            format="json",
        )
        self.assertEqual(res3.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("product_id", res3.data)

        # Missing Product
        res4 = self.client.post(
            "/api/v1/organization-product-entitlements/",
            {"organization_id": str(self.org.id), "product_id": str(uuid.uuid4())},
            format="json",
        )
        self.assertEqual(res4.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("product_id", res4.data)

    def test_create_locks_organization_before_product(self):
        """Verifies that create locks Organization before Product in deterministic order."""
        self.client.force_login(self.owner)
        lock_order = []

        orig_org_sfu = Organization.objects.select_for_update
        orig_prod_sfu = Product.objects.select_for_update

        def spy_org_sfu(*args, **kwargs):
            lock_order.append("Organization")
            return orig_org_sfu(*args, **kwargs)

        def spy_prod_sfu(*args, **kwargs):
            lock_order.append("Product")
            return orig_prod_sfu(*args, **kwargs)

        with mock.patch.object(Organization.objects, "select_for_update", side_effect=spy_org_sfu), \
             mock.patch.object(Product.objects, "select_for_update", side_effect=spy_prod_sfu):
            res = self.client.post(
                "/api/v1/organization-product-entitlements/",
                {"organization_id": str(self.org.id), "product_id": str(self.prod.id)},
                format="json",
            )
            self.assertEqual(res.status_code, status.HTTP_201_CREATED)

        self.assertEqual(lock_order, ["Organization", "Product"])

    # -------------------------------------------------------------------------
    # 3. Database Constraints, History, and Exception Handling
    # -------------------------------------------------------------------------

    def test_conditional_unique_constraint_rejects_duplicate_open_entitlement(self):
        self.client.force_login(self.owner)
        res1 = self.client.post(
            "/api/v1/organization-product-entitlements/",
            {"organization_id": str(self.org.id), "product_id": str(self.prod.id)},
            format="json",
        )
        self.assertEqual(res1.status_code, status.HTTP_201_CREATED)

        res2 = self.client.post(
            "/api/v1/organization-product-entitlements/",
            {"organization_id": str(self.org.id), "product_id": str(self.prod.id)},
            format="json",
        )
        self.assertEqual(res2.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("non_field_errors", res2.data)

    def test_re_purchase_allowed_after_revocation(self):
        self.client.force_login(self.owner)
        res1 = self.client.post(
            "/api/v1/organization-product-entitlements/",
            {"organization_id": str(self.org.id), "product_id": str(self.prod.id)},
            format="json",
        )
        e1_id = res1.data["id"]

        res_revoke = self.client.patch(
            f"/api/v1/organization-product-entitlements/{e1_id}/",
            {"status": "revoked"},
            format="json",
        )
        self.assertEqual(res_revoke.status_code, status.HTTP_200_OK)

        res2 = self.client.post(
            "/api/v1/organization-product-entitlements/",
            {"organization_id": str(self.org.id), "product_id": str(self.prod.id)},
            format="json",
        )
        self.assertEqual(res2.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res2.data["status"], EntitlementStatus.DRAFT)

        self.assertEqual(
            OrganizationProductEntitlement.objects.filter(organization=self.org, product=self.prod).count(),
            2,
        )

    def test_db_constraint_org_product_open_entitlement_uniq_direct(self):
        OrganizationProductEntitlement.objects.create(
            organization=self.org,
            product=self.prod,
            status=EntitlementStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                OrganizationProductEntitlement.objects.create(
                    organization=self.org,
                    product=self.prod,
                    status=EntitlementStatus.DRAFT,
                    created_by=self.owner,
                    updated_by=self.owner,
                )

    def test_db_constraint_status_valid_direct(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                OrganizationProductEntitlement.objects.create(
                    organization=self.org,
                    product=self.prod,
                    status="invalid_status",
                    created_by=self.owner,
                    updated_by=self.owner,
                )

    def test_known_integrity_error_converted_to_safe_400(self):
        """Simulated IntegrityError with org_product_open_entitlement_uniq becomes safe HTTP 400 without DB leakage."""
        self.client.force_login(self.owner)

        class MockDiag:
            constraint_name = "org_product_open_entitlement_uniq"

        class MockCause(Exception):
            diag = MockDiag()

        exc = IntegrityError("duplicate key value violates unique constraint")
        exc.__cause__ = MockCause()

        with mock.patch.object(OrganizationProductEntitlement.objects, "create", side_effect=exc):
            res = self.client.post(
                "/api/v1/organization-product-entitlements/",
                {"organization_id": str(self.org.id), "product_id": str(self.prod.id)},
                format="json",
            )
            self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertIn("non_field_errors", res.data)
            raw_data = str(res.data)
            self.assertNotIn("org_product_open_entitlement_uniq", raw_data)
            self.assertNotIn("duplicate key", raw_data)
            self.assertNotIn("SELECT", raw_data)
            self.assertNotIn("INSERT", raw_data)

    def test_unknown_integrity_error_re_raised(self):
        """Simulated IntegrityError with unknown constraint is re-raised and not converted."""
        self.client.force_login(self.owner)

        class MockDiag:
            constraint_name = "some_foreign_table_fk_constraint"

        class MockCause(Exception):
            diag = MockDiag()

        exc = IntegrityError("violates foreign key constraint")
        exc.__cause__ = MockCause()

        with mock.patch.object(OrganizationProductEntitlement.objects, "create", side_effect=exc):
            with self.assertRaises(IntegrityError):
                self.client.post(
                    "/api/v1/organization-product-entitlements/",
                    {"organization_id": str(self.org.id), "product_id": str(self.prod.id)},
                    format="json",
                )

    # -------------------------------------------------------------------------
    # 4. Lifecycle State Machine & PATCH Locking
    # -------------------------------------------------------------------------

    def test_complete_lifecycle_transition_matrix(self):
        """Verifies every allowed, rejected, and no-op transition in the lifecycle state machine."""
        self.client.force_login(self.owner)

        # 1. Allowed transitions:
        # Draft -> Active
        e1 = OrganizationProductEntitlement.objects.create(
            organization=self.org, product=self.prod, status=EntitlementStatus.DRAFT,
            created_by=self.owner, updated_by=self.owner
        )
        res = self.client.patch(f"/api/v1/organization-product-entitlements/{e1.id}/", {"status": "active"}, format="json")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["status"], "active")

        # Active -> Suspended
        res = self.client.patch(f"/api/v1/organization-product-entitlements/{e1.id}/", {"status": "suspended"}, format="json")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["status"], "suspended")

        # Suspended -> Active
        res = self.client.patch(f"/api/v1/organization-product-entitlements/{e1.id}/", {"status": "active"}, format="json")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["status"], "active")

        # Active -> Revoked
        res = self.client.patch(f"/api/v1/organization-product-entitlements/{e1.id}/", {"status": "revoked"}, format="json")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["status"], "revoked")

        # Draft -> Revoked
        p2 = self.create_prod(code="lms-p2")
        e2 = OrganizationProductEntitlement.objects.create(
            organization=self.org, product=p2, status=EntitlementStatus.DRAFT,
            created_by=self.owner, updated_by=self.owner
        )
        res = self.client.patch(f"/api/v1/organization-product-entitlements/{e2.id}/", {"status": "revoked"}, format="json")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["status"], "revoked")

        # Suspended -> Revoked
        p3 = self.create_prod(code="lms-p3")
        e3 = OrganizationProductEntitlement.objects.create(
            organization=self.org, product=p3, status=EntitlementStatus.SUSPENDED,
            created_by=self.owner, updated_by=self.owner
        )
        res = self.client.patch(f"/api/v1/organization-product-entitlements/{e3.id}/", {"status": "revoked"}, format="json")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["status"], "revoked")

        # 2. Rejected transitions:
        # Draft -> Suspended
        p4 = self.create_prod(code="lms-p4")
        e4 = OrganizationProductEntitlement.objects.create(
            organization=self.org, product=p4, status=EntitlementStatus.DRAFT,
            created_by=self.owner, updated_by=self.owner
        )
        res = self.client.patch(f"/api/v1/organization-product-entitlements/{e4.id}/", {"status": "suspended"}, format="json")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

        # Active -> Draft
        p5 = self.create_prod(code="lms-p5")
        e5 = OrganizationProductEntitlement.objects.create(
            organization=self.org, product=p5, status=EntitlementStatus.ACTIVE,
            created_by=self.owner, updated_by=self.owner
        )
        res = self.client.patch(f"/api/v1/organization-product-entitlements/{e5.id}/", {"status": "draft"}, format="json")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

        # Suspended -> Draft
        p6 = self.create_prod(code="lms-p6")
        e6 = OrganizationProductEntitlement.objects.create(
            organization=self.org, product=p6, status=EntitlementStatus.SUSPENDED,
            created_by=self.owner, updated_by=self.owner
        )
        res = self.client.patch(f"/api/v1/organization-product-entitlements/{e6.id}/", {"status": "draft"}, format="json")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

        # Revoked -> Draft / Active / Suspended / Revoked (all rejected)
        p7 = self.create_prod(code="lms-p7")
        e7 = OrganizationProductEntitlement.objects.create(
            organization=self.org, product=p7, status=EntitlementStatus.REVOKED,
            created_by=self.owner, updated_by=self.owner
        )
        for target in ["draft", "active", "suspended", "revoked"]:
            res = self.client.patch(f"/api/v1/organization-product-entitlements/{e7.id}/", {"status": target}, format="json")
            self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST, f"Revoked to {target} was not rejected")

        # 3. Same-status no-ops:
        for st in [EntitlementStatus.DRAFT, EntitlementStatus.ACTIVE, EntitlementStatus.SUSPENDED]:
            px = self.create_prod(code=f"lms-noop-{st}")
            ex = OrganizationProductEntitlement.objects.create(
                organization=self.org, product=px, status=st,
                created_by=self.owner, updated_by=self.owner
            )
            old_updated_at = ex.updated_at
            res_noop = self.client.patch(f"/api/v1/organization-product-entitlements/{ex.id}/", {"status": st}, format="json")
            self.assertEqual(res_noop.status_code, status.HTTP_200_OK)
            ex.refresh_from_db()
            self.assertEqual(ex.updated_at, old_updated_at)

    def test_activation_fails_if_parent_is_not_active(self):
        self.client.force_login(self.owner)

        # 1. Fails if Organization is suspended
        ent = OrganizationProductEntitlement.objects.create(
            organization=self.org,
            product=self.prod,
            status=EntitlementStatus.DRAFT,
            created_by=self.owner,
            updated_by=self.owner,
        )
        self.org.status = OrganizationStatus.SUSPENDED
        self.org.save(update_fields=["status"])

        res = self.client.patch(
            f"/api/v1/organization-product-entitlements/{ent.id}/",
            {"status": "active"},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("status", res.data)

        # 2. Fails if Product is inactive
        self.org.status = OrganizationStatus.ACTIVE
        self.org.save(update_fields=["status"])
        self.prod.status = ProductStatus.INACTIVE
        self.prod.save(update_fields=["status"])

        res2 = self.client.patch(
            f"/api/v1/organization-product-entitlements/{ent.id}/",
            {"status": "active"},
            format="json",
        )
        self.assertEqual(res2.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("status", res2.data)

    def test_patch_no_op_preserves_timestamps_and_updater(self):
        self.client.force_login(self.owner)

        ent = OrganizationProductEntitlement.objects.create(
            organization=self.org,
            product=self.prod,
            status=EntitlementStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )
        old_updated_at = ent.updated_at

        res = self.client.patch(
            f"/api/v1/organization-product-entitlements/{ent.id}/",
            {"status": "active"},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        ent.refresh_from_db()
        self.assertEqual(ent.updated_at, old_updated_at)
        self.assertEqual(ent.updated_by, self.owner)

    def test_patch_rejects_protected_immutable_and_unknown_fields_matrix(self):
        """Verifies that PATCH rejects empty body, missing status, immutable parent keys, protected fields, and unknown fields."""
        self.client.force_login(self.owner)
        ent = OrganizationProductEntitlement.objects.create(
            organization=self.org, product=self.prod, status=EntitlementStatus.DRAFT,
            created_by=self.owner, updated_by=self.owner
        )

        # 1. Completely empty payload
        res_empty = self.client.patch(f"/api/v1/organization-product-entitlements/{ent.id}/", {}, format="json")
        self.assertEqual(res_empty.status_code, status.HTTP_400_BAD_REQUEST)

        # 2. Payload without status
        res_no_status = self.client.patch(
            f"/api/v1/organization-product-entitlements/{ent.id}/",
            {"organization_id": str(uuid.uuid4())},
            format="json",
        )
        self.assertEqual(res_no_status.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("organization_id", res_no_status.data)
        self.assertIn("status", res_no_status.data)

        # 3. Subtests for immutable, protected, and unknown fields sent alongside status
        forbidden_fields = [
            ("id", str(uuid.uuid4())),
            ("organization_id", str(uuid.uuid4())),
            ("product_id", str(uuid.uuid4())),
            ("organization", {"id": str(uuid.uuid4())}),
            ("product", {"id": str(uuid.uuid4())}),
            ("created_at", "2026-01-01T00:00:00Z"),
            ("updated_at", "2026-01-01T00:00:00Z"),
            ("created_by", str(uuid.uuid4())),
            ("updated_by", str(uuid.uuid4())),
            ("unknown_field", "forbidden_value"),
        ]

        for field_name, field_val in forbidden_fields:
            with self.subTest(field=field_name):
                res = self.client.patch(
                    f"/api/v1/organization-product-entitlements/{ent.id}/",
                    {"status": "active", field_name: field_val},
                    format="json",
                )
                self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST, f"Field '{field_name}' was not rejected")
                self.assertIn(field_name, res.data)

    # -------------------------------------------------------------------------
    # 5. Detail Retrieve, Response Shapes & Data Minimization
    # -------------------------------------------------------------------------

    def test_retrieve_malformed_and_nonexistent_uuid_returns_safe_404(self):
        """Directly verifies authenticated Platform Owner receives safe 404 on malformed and nonexistent UUIDs."""
        self.client.force_login(self.owner)

        # Malformed UUID
        res_malformed = self.client.get("/api/v1/organization-product-entitlements/not-a-valid-uuid/")
        self.assertEqual(res_malformed.status_code, status.HTTP_404_NOT_FOUND)
        self.assertNotIn("Traceback", str(res_malformed.data))
        self.assertNotIn("SELECT", str(res_malformed.data))

        # Nonexistent UUID
        res_missing = self.client.get(f"/api/v1/organization-product-entitlements/{uuid.uuid4()}/")
        self.assertEqual(res_missing.status_code, status.HTTP_404_NOT_FOUND)
        self.assertNotIn("Traceback", str(res_missing.data))
        self.assertNotIn("SELECT", str(res_missing.data))

    def test_response_shapes_and_audit_user_data_minimization(self):
        self.client.force_login(self.owner)
        ent = OrganizationProductEntitlement.objects.create(
            organization=self.org,
            product=self.prod,
            status=EntitlementStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )

        # 1. Compact list response
        res_list = self.client.get("/api/v1/organization-product-entitlements/")
        self.assertEqual(res_list.status_code, status.HTTP_200_OK)
        item = res_list.data["results"][0]
        self.assertEqual(
            set(item.keys()),
            {"id", "organization", "product", "status", "created_at", "updated_at"},
        )
        self.assertNotIn("created_by", item)

        # 2. Detailed retrieve response
        res_detail = self.client.get(f"/api/v1/organization-product-entitlements/{ent.id}/")
        self.assertEqual(res_detail.status_code, status.HTTP_200_OK)
        data = res_detail.data
        self.assertIn("created_by", data)
        self.assertIn("updated_by", data)

        # Audit user must expose ONLY id and full_name
        self.assertEqual(set(data["created_by"].keys()), {"id", "full_name"})
        self.assertEqual(set(data["updated_by"].keys()), {"id", "full_name"})
        for forbidden in ["email", "password", "is_platform_owner", "is_staff", "is_superuser"]:
            self.assertNotIn(forbidden, data["created_by"])
            self.assertNotIn(forbidden, data["updated_by"])

    # -------------------------------------------------------------------------
    # 6. Querying, Filtering, Ordering, and Pagination
    # -------------------------------------------------------------------------

    def test_filtering_and_search(self):
        self.client.force_login(self.owner)
        OrganizationProductEntitlement.objects.create(
            organization=self.org,
            product=self.prod,
            status=EntitlementStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )

        # Filter by organization_id
        res_org = self.client.get(f"/api/v1/organization-product-entitlements/?organization_id={self.org.id}")
        self.assertEqual(res_org.status_code, status.HTTP_200_OK)
        self.assertEqual(res_org.data["count"], 1)

        # Filter by product_id
        res_prod = self.client.get(f"/api/v1/organization-product-entitlements/?product_id={self.prod.id}")
        self.assertEqual(res_prod.status_code, status.HTTP_200_OK)
        self.assertEqual(res_prod.data["count"], 1)

        # Malformed organization_id
        res_bad_org = self.client.get("/api/v1/organization-product-entitlements/?organization_id=bad-uuid")
        self.assertEqual(res_bad_org.status_code, status.HTTP_400_BAD_REQUEST)

        # Malformed product_id
        res_bad_prod = self.client.get("/api/v1/organization-product-entitlements/?product_id=bad-uuid")
        self.assertEqual(res_bad_prod.status_code, status.HTTP_400_BAD_REQUEST)

        # Search by organization name
        res_search = self.client.get("/api/v1/organization-product-entitlements/?search=Acme")
        self.assertEqual(res_search.status_code, status.HTTP_200_OK)
        self.assertEqual(res_search.data["count"], 1)

        # Search by product code
        res_search_prod = self.client.get(f"/api/v1/organization-product-entitlements/?search={self.prod.code}")
        self.assertEqual(res_search_prod.status_code, status.HTTP_200_OK)
        self.assertEqual(res_search_prod.data["count"], 1)

        # Search query > 100 chars
        res_long_search = self.client.get(f"/api/v1/organization-product-entitlements/?search={'a' * 101}")
        self.assertEqual(res_long_search.status_code, status.HTTP_400_BAD_REQUEST)

    def test_ordering_and_deterministic_tie_breakers(self):
        self.client.force_login(self.owner)
        OrganizationProductEntitlement.objects.create(
            organization=self.org,
            product=self.prod,
            status=EntitlementStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )

        for valid_order in [
            "created_at", "-created_at", "status", "-status",
            "organization", "-organization", "product", "-product",
        ]:
            res = self.client.get(f"/api/v1/organization-product-entitlements/?ordering={valid_order}")
            self.assertEqual(res.status_code, status.HTTP_200_OK, f"Failed for ordering {valid_order}")

        # Internal field names must be rejected publicly
        res_internal = self.client.get("/api/v1/organization-product-entitlements/?ordering=organization__code")
        self.assertEqual(res_internal.status_code, status.HTTP_400_BAD_REQUEST)

    def test_pagination_and_duplicate_singleton_parameters(self):
        self.client.force_login(self.owner)

        # Invalid page_size (non-integer, negative, zero)
        for bad_size in ["abc", "-5", "0"]:
            res = self.client.get(f"/api/v1/organization-product-entitlements/?page_size={bad_size}")
            self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

        # Invalid page (non-integer, zero, negative, out-of-range returns 404)
        for bad_page in ["abc", "0", "-1", "999"]:
            res = self.client.get(f"/api/v1/organization-product-entitlements/?page={bad_page}")
            self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

        # Duplicate singleton parameters
        res_dup = self.client.get("/api/v1/organization-product-entitlements/?status=draft&status=active")
        self.assertEqual(res_dup.status_code, status.HTTP_400_BAD_REQUEST)

        # Unknown query parameter is ignored
        res_unknown = self.client.get("/api/v1/organization-product-entitlements/?unknown_filter=true")
        self.assertEqual(res_unknown.status_code, status.HTTP_200_OK)

    def test_query_optimization_select_related_bounded(self):
        self.client.force_login(self.owner)
        for i in range(5):
            org = self.create_org(code=f"org-test-{i}", name=f"Org {i}")
            prod = self.create_prod(code=f"prod-test-{i}", name=f"Prod {i}")
            OrganizationProductEntitlement.objects.create(
                organization=org,
                product=prod,
                status=EntitlementStatus.ACTIVE,
                created_by=self.owner,
                updated_by=self.owner,
            )

        # Execute query within bounded query count (session + count + 1 select_related query)
        with self.assertNumQueries(7):
            res = self.client.get("/api/v1/organization-product-entitlements/?page_size=10")
            self.assertEqual(res.status_code, status.HTTP_200_OK)
            self.assertEqual(len(res.data["results"]), 5)

    # -------------------------------------------------------------------------
    # 7. Referential Integrity & Method Restrictions
    # -------------------------------------------------------------------------

    def test_deletion_protection_on_foreign_keys(self):
        OrganizationProductEntitlement.objects.create(
            organization=self.org,
            product=self.prod,
            status=EntitlementStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )

        with self.assertRaises(ProtectedError):
            self.org.delete()

        with self.assertRaises(ProtectedError):
            self.prod.delete()

        with self.assertRaises(ProtectedError):
            self.owner.delete()

    def test_unsupported_methods_return_405(self):
        self.client.force_login(self.owner)
        ent = OrganizationProductEntitlement.objects.create(
            organization=self.org,
            product=self.prod,
            status=EntitlementStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )

        self.assertEqual(
            self.client.put(
                f"/api/v1/organization-product-entitlements/{ent.id}/",
                {"status": "active"},
                format="json",
            ).status_code,
            status.HTTP_405_METHOD_NOT_ALLOWED,
        )
        self.assertEqual(
            self.client.delete(
                f"/api/v1/organization-product-entitlements/{ent.id}/",
            ).status_code,
            status.HTTP_405_METHOD_NOT_ALLOWED,
        )


class EntitlementConcurrencyTests(TransactionTestCase, EntitlementTestBase):
    """PostgreSQL-backed concurrency tests using real threads and row locking."""

    def setUp(self):
        self.owner = self.create_owner(email="conc_owner@vibeconnect.io")
        self.org = self.create_org(code="conc-org", user=self.owner)
        self.prod = self.create_prod(code="conc-prod", user=self.owner)

    def tearDown(self):
        connections.close_all()
        super().tearDown()

    def test_concurrent_post_creation_duplicate_safety(self):
        """Two concurrent POST requests for the same pair: exactly one succeeds and one safely receives 400."""
        barrier = threading.Barrier(2)
        results = []

        def worker():
            connection.connect()
            try:
                client = APIClient()
                client.force_login(self.owner)
                barrier.wait(timeout=5.0)
                res = client.post(
                    "/api/v1/organization-product-entitlements/",
                    {"organization_id": str(self.org.id), "product_id": str(self.prod.id)},
                    format="json",
                )
                results.append(res.status_code)
            finally:
                connection.close()

        t1 = threading.Thread(target=worker)
        t2 = threading.Thread(target=worker)
        t1.start()
        t2.start()
        t1.join(timeout=5.0)
        t2.join(timeout=5.0)

        self.assertEqual(len(results), 2)
        self.assertIn(status.HTTP_201_CREATED, results)
        self.assertIn(status.HTTP_400_BAD_REQUEST, results)
        self.assertEqual(OrganizationProductEntitlement.objects.filter(organization=self.org, product=self.prod).count(), 1)

    def test_concurrent_activation_racing_with_organization_deactivation(self):
        """Verifies that select_for_update prevents activating an entitlement if Organization deactivates concurrently."""
        ent = OrganizationProductEntitlement.objects.create(
            organization=self.org,
            product=self.prod,
            status=EntitlementStatus.DRAFT,
            created_by=self.owner,
            updated_by=self.owner,
        )

        event_org_locked = threading.Event()
        event_committed = threading.Event()
        result_activation = {}

        def thread_deactivate_org():
            connection.connect()
            try:
                with transaction.atomic():
                    locked_org = Organization.objects.select_for_update().get(pk=self.org.pk)
                    event_org_locked.set()
                    event_committed.wait(timeout=3.0)
                    locked_org.status = OrganizationStatus.SUSPENDED
                    locked_org.save(update_fields=["status"])
            finally:
                connection.close()

        def thread_activate_entitlement():
            connection.connect()
            try:
                event_org_locked.wait(timeout=3.0)
                client = APIClient()
                client.force_login(self.owner)
                event_committed.set()
                res = client.patch(
                    f"/api/v1/organization-product-entitlements/{ent.id}/",
                    {"status": "active"},
                    format="json",
                )
                result_activation["status"] = res.status_code
                result_activation["data"] = res.data
            finally:
                connection.close()

        t1 = threading.Thread(target=thread_deactivate_org)
        t2 = threading.Thread(target=thread_activate_entitlement)
        t1.start()
        t2.start()
        t1.join(timeout=5.0)
        t2.join(timeout=5.0)

        # Activation must have blocked, observed SUSPENDED org status, and returned HTTP 400
        self.assertEqual(result_activation.get("status"), status.HTTP_400_BAD_REQUEST)
        self.assertIn("status", result_activation.get("data", {}))

    def test_concurrent_activation_racing_with_product_deactivation(self):
        """Verifies that select_for_update prevents activating an entitlement if Product deactivates concurrently."""
        ent = OrganizationProductEntitlement.objects.create(
            organization=self.org,
            product=self.prod,
            status=EntitlementStatus.DRAFT,
            created_by=self.owner,
            updated_by=self.owner,
        )

        event_prod_locked = threading.Event()
        event_committed = threading.Event()
        result_activation = {}

        def thread_deactivate_prod():
            connection.connect()
            try:
                with transaction.atomic():
                    locked_prod = Product.objects.select_for_update().get(pk=self.prod.pk)
                    event_prod_locked.set()
                    event_committed.wait(timeout=3.0)
                    locked_prod.status = ProductStatus.INACTIVE
                    locked_prod.save(update_fields=["status"])
            finally:
                connection.close()

        def thread_activate_entitlement():
            connection.connect()
            try:
                event_prod_locked.wait(timeout=3.0)
                client = APIClient()
                client.force_login(self.owner)
                event_committed.set()
                res = client.patch(
                    f"/api/v1/organization-product-entitlements/{ent.id}/",
                    {"status": "active"},
                    format="json",
                )
                result_activation["status"] = res.status_code
                result_activation["data"] = res.data
            finally:
                connection.close()

        t1 = threading.Thread(target=thread_deactivate_prod)
        t2 = threading.Thread(target=thread_activate_entitlement)
        t1.start()
        t2.start()
        t1.join(timeout=5.0)
        t2.join(timeout=5.0)

        # Activation must have blocked, observed INACTIVE product status, and returned HTTP 400
        self.assertEqual(result_activation.get("status"), status.HTTP_400_BAD_REQUEST)
        self.assertIn("status", result_activation.get("data", {}))

    @classmethod
    def tearDownClass(cls):
        connections.close_all()
        super().tearDownClass()
