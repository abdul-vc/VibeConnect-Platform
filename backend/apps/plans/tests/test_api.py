"""VibeConnect Phase 2B Plans API Tests.

Comprehensive test suite verifying:
- Authentication and Platform Owner authorization
- Strict payload validation (unknown fields, empty PATCH, protected fields, malformed UUID)
- Plan and PlanVersion lifecycle endpoints
- Pricing endpoints, currency allowlist, canonical amounts, and duplicate handling
- Product, Module, and Capability packaging endpoints, ancestry checks, and cascade deletions
- Quota endpoints, scope-target consistency, numeric limits, and BIGINT safety
- List querying, filtering, search, deterministic ordering, and bounded pagination
- Audit event generation on mutations and zero audit events on rejected requests
"""

from decimal import Decimal
import uuid
from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import resolve, reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.auditlog.models import AuditAction, AuditLog, AuditTargetType
from apps.plans.services import create_plan
from apps.plans.views import (
    PlanCapabilityViewSet,
    PlanModuleViewSet,
    PlanPriceViewSet,
    PlanProductViewSet,
    PlanQuotaViewSet,
    PlanVersionViewSet,
    PlanViewSet,
)
from apps.plans.models import (
    BillingInterval,
    Plan,
    PlanCapability,
    PlanCurrency,
    PlanModule,
    PlanPrice,
    PlanProduct,
    PlanQuota,
    PlanVersion,
    PlanVersionStatus,
    QuotaLimitType,
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

User = get_user_model()


class PlansApiTests(TestCase):
    """API test suite for Phase 2B Plans & Pricing REST endpoints."""

    def setUp(self):
        super().setUp()
        Plan.objects.all().delete()
        self.owner = User.objects.create_user(
            email="owner@vibeconnect.internal",
            password="SecurePassword123!",
            full_name="Platform Owner",
            is_active=True,
            is_platform_owner=True,
        )
        self.non_owner = User.objects.create_user(
            email="regular@vibeconnect.internal",
            password="SecurePassword123!",
            full_name="Regular User",
            is_active=True,
            is_platform_owner=False,
        )
        self.client = APIClient()

    def _create_active_catalog_tree(self):
        prod = Product.objects.create(
            code=f"prod_{uuid.uuid4().hex[:6]}",
            name="LMS Core",
            status=ProductStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )
        mod = ProductModule.objects.create(
            product=prod,
            code=f"mod_{uuid.uuid4().hex[:6]}",
            name="Courses",
            status=CatalogStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )
        feat = ProductFeature.objects.create(
            module=mod,
            code=f"feat_{uuid.uuid4().hex[:6]}",
            name="Video Player",
            status=CatalogStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )
        cap = ProductCapability.objects.create(
            feature=feat,
            code=f"cap_{uuid.uuid4().hex[:6]}",
            name="HD Streaming",
            status=CatalogStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )
        return prod, mod, feat, cap

    # =========================================================================
    # 1. Authentication & Authorization
    # =========================================================================

    def test_approved_url_and_method_contract_matrix(self):
        dummy = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
        route_matrix = [
            ("plan-list-create", {}, "/api/v1/plans/", PlanViewSet, {"get": "list", "post": "create"}),
            ("plan-detail", {"pk": dummy}, f"/api/v1/plans/{dummy}/", PlanViewSet, {"get": "retrieve", "patch": "partial_update", "head": "retrieve"}),
            ("plan-version-list-create", {"plan_id": dummy}, f"/api/v1/plans/{dummy}/versions/", PlanVersionViewSet, {"get": "list", "post": "create"}),
            ("plan-version-detail", {"pk": dummy}, f"/api/v1/plan-versions/{dummy}/", PlanVersionViewSet, {"get": "retrieve", "patch": "partial_update"}),
            ("plan-version-clone", {"pk": dummy}, f"/api/v1/plan-versions/{dummy}/clone/", PlanVersionViewSet, {"post": "clone"}),
            ("plan-version-readiness", {"pk": dummy}, f"/api/v1/plan-versions/{dummy}/readiness/", PlanVersionViewSet, {"get": "readiness"}),
            ("plan-version-activate", {"pk": dummy}, f"/api/v1/plan-versions/{dummy}/activate/", PlanVersionViewSet, {"post": "activate"}),
            ("plan-version-retire", {"pk": dummy}, f"/api/v1/plan-versions/{dummy}/retire/", PlanVersionViewSet, {"post": "retire"}),
            ("plan-price-list-create", {"version_id": dummy}, f"/api/v1/plan-versions/{dummy}/prices/", PlanPriceViewSet, {"get": "list", "post": "create"}),
            ("plan-price-detail", {"pk": dummy}, f"/api/v1/plan-prices/{dummy}/", PlanPriceViewSet, {"get": "retrieve", "patch": "partial_update", "delete": "destroy"}),
            ("plan-product-list-create", {"version_id": dummy}, f"/api/v1/plan-versions/{dummy}/products/", PlanProductViewSet, {"get": "list", "post": "create"}),
            ("plan-product-detail", {"pk": dummy}, f"/api/v1/plan-products/{dummy}/", PlanProductViewSet, {"get": "retrieve", "delete": "destroy"}),
            ("plan-module-list-create", {"version_id": dummy}, f"/api/v1/plan-versions/{dummy}/modules/", PlanModuleViewSet, {"get": "list", "post": "create"}),
            ("plan-module-detail", {"pk": dummy}, f"/api/v1/plan-modules/{dummy}/", PlanModuleViewSet, {"get": "retrieve", "delete": "destroy"}),
            ("plan-capability-list-create", {"version_id": dummy}, f"/api/v1/plan-versions/{dummy}/capabilities/", PlanCapabilityViewSet, {"get": "list", "post": "create"}),
            ("plan-capability-detail", {"pk": dummy}, f"/api/v1/plan-capabilities/{dummy}/", PlanCapabilityViewSet, {"get": "retrieve", "delete": "destroy"}),
            ("plan-quota-list-create", {"version_id": dummy}, f"/api/v1/plan-versions/{dummy}/quotas/", PlanQuotaViewSet, {"get": "list", "post": "create"}),
            ("plan-quota-detail", {"pk": dummy}, f"/api/v1/plan-quotas/{dummy}/", PlanQuotaViewSet, {"get": "retrieve", "patch": "partial_update", "delete": "destroy"}),
        ]
        for name, kwargs, expected_path, expected_view, expected_actions in route_matrix:
            with self.subTest(route=name):
                resolved_url = reverse(name, kwargs=kwargs)
                self.assertEqual(resolved_url, expected_path)
                match = resolve(expected_path)
                self.assertEqual(match.func.cls, expected_view)
                actual_actions = dict(match.func.actions)
                if "get" in actual_actions and "head" in expected_actions and "head" not in actual_actions:
                    actual_actions["head"] = actual_actions["get"]
                self.assertEqual(actual_actions, expected_actions)

    def test_forbidden_methods_return_405_and_zero_audit(self):
        self.client.force_login(self.owner)
        dummy = str(uuid.uuid4())
        forbidden_calls = [
            ("put", f"/api/v1/plans/{dummy}/"),
            ("delete", f"/api/v1/plans/{dummy}/"),
            ("put", f"/api/v1/plan-versions/{dummy}/"),
            ("delete", f"/api/v1/plan-versions/{dummy}/"),
            ("put", f"/api/v1/plan-prices/{dummy}/"),
            ("put", f"/api/v1/plan-products/{dummy}/"),
            ("patch", f"/api/v1/plan-products/{dummy}/"),
            ("put", f"/api/v1/plan-modules/{dummy}/"),
            ("patch", f"/api/v1/plan-modules/{dummy}/"),
            ("put", f"/api/v1/plan-capabilities/{dummy}/"),
            ("patch", f"/api/v1/plan-capabilities/{dummy}/"),
            ("put", f"/api/v1/plan-quotas/{dummy}/"),
            ("delete", "/api/v1/plans/"),
            ("delete", f"/api/v1/plan-versions/{dummy}/prices/"),
            ("delete", f"/api/v1/plan-versions/{dummy}/products/"),
            ("delete", f"/api/v1/plan-versions/{dummy}/modules/"),
            ("delete", f"/api/v1/plan-versions/{dummy}/capabilities/"),
            ("delete", f"/api/v1/plan-versions/{dummy}/quotas/"),
        ]
        audits_before = AuditLog.objects.count()
        for method, path in forbidden_calls:
            with self.subTest(method=method, path=path):
                call = getattr(self.client, method)
                resp = call(path, {}, format="json")
                self.assertEqual(resp.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        self.assertEqual(AuditLog.objects.count(), audits_before)

    def test_authentication_and_authorization_matrix(self):
        plan, v = create_plan(code="auth_matrix_plan", name="Auth Plan", actor=self.owner)
        representative_routes = [
            "/api/v1/plans/",
            f"/api/v1/plans/{plan.id}/versions/",
            f"/api/v1/plan-versions/{v.id}/prices/",
            f"/api/v1/plan-versions/{v.id}/products/",
            f"/api/v1/plan-versions/{v.id}/modules/",
            f"/api/v1/plan-versions/{v.id}/capabilities/",
            f"/api/v1/plan-versions/{v.id}/quotas/",
            f"/api/v1/plans/{plan.id}/",
            f"/api/v1/plan-versions/{v.id}/",
        ]
        for url in representative_routes:
            with self.subTest(route=url, auth="unauthenticated"):
                client = APIClient()
                resp = client.get(url)
                self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)
            with self.subTest(route=url, auth="non_owner"):
                client = APIClient()
                client.force_login(self.non_owner)
                resp = client.get(url)
                self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
            with self.subTest(route=url, auth="owner"):
                client = APIClient()
                client.force_login(self.owner)
                resp = client.get(url)
                self.assertEqual(resp.status_code, status.HTTP_200_OK)

    # =========================================================================
    # 2. Strict Payloads & Unknown Field Rejection
    # =========================================================================

    def test_unknown_field_rejected_with_400(self):
        self.client.force_login(self.owner)
        resp = self.client.post("/api/v1/plans/", {
            "code": "starter",
            "name": "Starter",
            "unknown_foo": "bar",
        }, format="json")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("unknown_foo", resp.data)

    def test_empty_patch_rejected_with_400(self):
        self.client.force_login(self.owner)
        resp = self.client.post("/api/v1/plans/", {
            "code": "starter_patch",
            "name": "Starter Patch",
        }, format="json")
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        plan_id = resp.data["id"]

        patch_resp = self.client.patch(f"/api/v1/plans/{plan_id}/", {}, format="json")
        self.assertEqual(patch_resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("detail", patch_resp.data)

    def test_read_only_and_protected_field_mutation_rejected_with_400(self):
        self.client.force_login(self.owner)
        resp = self.client.post("/api/v1/plans/", {
            "code": "immutable_code",
            "name": "Immutable Code Plan",
        }, format="json")
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        plan_id = resp.data["id"]

        patch_resp = self.client.patch(f"/api/v1/plans/{plan_id}/", {
            "code": "new_code",
            "name": "New Name",
        }, format="json")
        self.assertEqual(patch_resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("code", patch_resp.data)

    def test_malformed_uuid_in_path_returns_404(self):
        self.client.force_login(self.owner)
        resp = self.client.get("/api/v1/plans/not-a-valid-uuid/")
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_strict_write_contract_matrix(self):
        self.client.force_login(self.owner)
        plan, v = create_plan(code="strict_write_plan", name="Strict Write Plan", actor=self.owner)

        # 1. Malformed UUID in payload fields
        with self.subTest(check="malformed_uuid_in_payload"):
            resp = self.client.post(f"/api/v1/plan-versions/{v.id}/products/", {
                "product_id": "not-a-valid-uuid",
            }, format="json")
            self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertIn("product_id", resp.data)

        # 2. Server-owned / read-only fields supplied in writes
        write_rejections = [
            ("post", "/api/v1/plans/", {"code": "p_id", "name": "P", "id": str(uuid.uuid4())}, "id"),
            ("patch", f"/api/v1/plans/{plan.id}/", {"created_at": "2026-01-01T00:00:00Z"}, "created_at"),
            ("post", f"/api/v1/plans/{plan.id}/versions/", {"status": "active"}, "status"),
            ("patch", f"/api/v1/plan-versions/{v.id}/", {"version": 99}, "version"),
            ("post", f"/api/v1/plan-versions/{v.id}/prices/", {"currency": "USD", "billing_interval": "monthly", "amount": "10.00", "plan_version_id": str(v.id)}, "plan_version_id"),
            ("patch", f"/api/v1/plans/{plan.id}/", {"code": "new_code"}, "code"),
            ("post", f"/api/v1/plan-versions/{v.id}/quotas/", {"scope": "plan", "quota_key": "k", "name": "N", "unit": "count", "limit_type": "numeric", "limit_value": "1", "target_id": str(uuid.uuid4())}, "target_id"),
        ]
        audits_before = AuditLog.objects.count()
        for method, path, payload, rejected_field in write_rejections:
            with self.subTest(method=method, path=path, rejected_field=rejected_field):
                call = getattr(self.client, method)
                r = call(path, payload, format="json")
                self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertIn(rejected_field, r.data)
        # Verify zero audit records and zero partial mutations on rejected requests
        self.assertEqual(AuditLog.objects.count(), audits_before)

    # =========================================================================
    # 3. Plan & PlanVersion Endpoints
    # =========================================================================

    def test_plan_create_atomic_version1_and_read_dto(self):
        self.client.force_login(self.owner)
        resp = self.client.post("/api/v1/plans/", {
            "code": "pro_plan",
            "name": "Pro Plan",
            "description": "Professional tier",
            "change_summary": "Initial commercial definition",
        }, format="json")
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        plan_id = resp.data["id"]

        # Detail assertions
        detail_resp = self.client.get(f"/api/v1/plans/{plan_id}/")
        self.assertEqual(detail_resp.status_code, status.HTTP_200_OK)
        data = detail_resp.data
        self.assertEqual(data["code"], "pro_plan")
        self.assertEqual(data["name"], "Pro Plan")
        self.assertEqual(data["total_versions_count"], 1)
        self.assertIsNone(data["active_version"])
        self.assertIsNotNone(data["latest_version"])
        self.assertEqual(data["latest_version"]["version"], 1)
        self.assertEqual(data["latest_version"]["status"], "draft")
        self.assertEqual(data["created_by_email"], self.owner.email)
        self.assertNotIn("versions", data)  # No unbounded versions array

    def test_plan_update_modifies_name_and_description(self):
        self.client.force_login(self.owner)
        create_resp = self.client.post("/api/v1/plans/", {
            "code": "update_plan",
            "name": "Old Name",
            "description": "Old Desc",
        }, format="json")
        plan_id = create_resp.data["id"]

        patch_resp = self.client.patch(f"/api/v1/plans/{plan_id}/", {
            "name": "New Name",
            "description": "New Desc",
        }, format="json")
        self.assertEqual(patch_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(patch_resp.data["name"], "New Name")
        self.assertEqual(patch_resp.data["description"], "New Desc")

    def test_plan_version_crud_lifecycle_and_conflict(self):
        self.client.force_login(self.owner)
        plan_resp = self.client.post("/api/v1/plans/", {
            "code": "lifecycle_plan",
            "name": "Lifecycle Plan",
        }, format="json")
        plan_id = plan_resp.data["id"]
        v1_id = plan_resp.data["latest_version"]["id"]

        # 1. Update draft change_summary
        v1_patch = self.client.patch(f"/api/v1/plan-versions/{v1_id}/", {
            "change_summary": "Updated summary",
        }, format="json")
        self.assertEqual(v1_patch.status_code, status.HTTP_200_OK)
        self.assertEqual(v1_patch.data["change_summary"], "Updated summary")

        # 2. Retire Draft version
        retire_resp = self.client.post(f"/api/v1/plan-versions/{v1_id}/retire/", {}, format="json")
        self.assertEqual(retire_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(retire_resp.data["status"], "retired")

        # 3. Patch retired version must return 409 Conflict
        bad_patch = self.client.patch(f"/api/v1/plan-versions/{v1_id}/", {
            "change_summary": "Should fail",
        }, format="json")
        self.assertEqual(bad_patch.status_code, status.HTTP_409_CONFLICT)
        self.assertIn("immutable", bad_patch.data["detail"].lower())

        # 4. Create new draft version (v2)
        v2_resp = self.client.post(f"/api/v1/plans/{plan_id}/versions/", {
            "change_summary": "Version 2 draft",
        }, format="json")
        self.assertEqual(v2_resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(v2_resp.data["version"], 2)
        self.assertEqual(v2_resp.data["status"], "draft")

        # 5. Clone version 2 -> creates version 3
        clone_resp = self.client.post(f"/api/v1/plan-versions/{v2_resp.data['id']}/clone/", {
            "change_summary": "Cloned from v2",
        }, format="json")
        self.assertEqual(clone_resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(clone_resp.data["version"], 3)
        self.assertEqual(clone_resp.data["status"], "draft")

    def test_version_readiness_response_dto(self):
        self.client.force_login(self.owner)
        plan_resp = self.client.post("/api/v1/plans/", {
            "code": "readiness_plan",
            "name": "Readiness Plan",
        }, format="json")
        v1_id = plan_resp.data["latest_version"]["id"]

        readiness_resp = self.client.get(f"/api/v1/plan-versions/{v1_id}/readiness/")
        self.assertEqual(readiness_resp.status_code, status.HTTP_200_OK)
        data = readiness_resp.data
        self.assertIn("is_ready", data)
        self.assertIn("blockers", data)
        self.assertIn("warnings", data)
        self.assertIn("prices_count", data)
        self.assertIn("products_count", data)
        self.assertIn("catalog_health", data)
        self.assertIn("stale_items", data)
        self.assertFalse(data["is_ready"])  # No prices or products packaged yet
        self.assertEqual(data["catalog_health"], "healthy")

    def test_no_plan_or_version_delete_routes(self):
        self.client.force_login(self.owner)
        resp1 = self.client.delete("/api/v1/plans/some-id/")
        self.assertIn(resp1.status_code, [status.HTTP_404_NOT_FOUND, status.HTTP_405_METHOD_NOT_ALLOWED])
        resp2 = self.client.delete("/api/v1/plan-versions/some-id/")
        self.assertIn(resp2.status_code, [status.HTTP_404_NOT_FOUND, status.HTTP_405_METHOD_NOT_ALLOWED])

    # =========================================================================
    # 4. Pricing Endpoints
    # =========================================================================

    def test_pricing_endpoints_currency_allowlist_canonical_amount_and_conflict(self):
        self.client.force_login(self.owner)
        plan_resp = self.client.post("/api/v1/plans/", {"code": "price_plan", "name": "Price Plan"}, format="json")
        v1_id = plan_resp.data["latest_version"]["id"]

        # 1. Valid price creation
        price_resp = self.client.post(f"/api/v1/plan-versions/{v1_id}/prices/", {
            "currency": "USD",
            "billing_interval": "monthly",
            "amount": "19.99",
        }, format="json")
        self.assertEqual(price_resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(price_resp.data["amount"], "19.99")
        price_id = price_resp.data["id"]

        # 2. Duplicate price creation returns 409
        dup_resp = self.client.post(f"/api/v1/plan-versions/{v1_id}/prices/", {
            "currency": "USD",
            "billing_interval": "monthly",
            "amount": "25.00",
        }, format="json")
        self.assertEqual(dup_resp.status_code, status.HTTP_409_CONFLICT)

        # 3. Unsupported currency returns 400
        bad_curr_resp = self.client.post(f"/api/v1/plan-versions/{v1_id}/prices/", {
            "currency": "AUD",
            "billing_interval": "monthly",
            "amount": "19.99",
        }, format="json")
        self.assertEqual(bad_curr_resp.status_code, status.HTTP_400_BAD_REQUEST)

        # 4. Non-canonical amounts return 400
        for bad_amt in [19.99, "19.9", "019.99", "19.999", None]:
            bad_amt_resp = self.client.post(f"/api/v1/plan-versions/{v1_id}/prices/", {
                "currency": "EUR",
                "billing_interval": "annual",
                "amount": bad_amt,
            }, format="json")
            self.assertEqual(bad_amt_resp.status_code, status.HTTP_400_BAD_REQUEST)

        # 5. Patch price amount
        patch_resp = self.client.patch(f"/api/v1/plan-prices/{price_id}/", {
            "amount": "29.99",
        }, format="json")
        self.assertEqual(patch_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(patch_resp.data["amount"], "29.99")

        # 6. Delete price
        del_resp = self.client.delete(f"/api/v1/plan-prices/{price_id}/")
        self.assertEqual(del_resp.status_code, status.HTTP_204_NO_CONTENT)

    # =========================================================================
    # 5. Packaging Endpoints (Product, Module, Capability)
    # =========================================================================

    def test_packaging_endpoints_and_cascade_delete(self):
        self.client.force_login(self.owner)
        prod, mod, feat, cap = self._create_active_catalog_tree()

        plan_resp = self.client.post("/api/v1/plans/", {"code": "pack_plan", "name": "Pack Plan"}, format="json")
        v1_id = plan_resp.data["latest_version"]["id"]

        # 1. Add Product
        pp_resp = self.client.post(f"/api/v1/plan-versions/{v1_id}/products/", {
            "product_id": str(prod.id),
        }, format="json")
        self.assertEqual(pp_resp.status_code, status.HTTP_201_CREATED)
        pp_id = pp_resp.data["id"]

        # 2. Add Module
        pm_resp = self.client.post(f"/api/v1/plan-versions/{v1_id}/modules/", {
            "plan_product_id": pp_id,
            "module_id": str(mod.id),
        }, format="json")
        self.assertEqual(pm_resp.status_code, status.HTTP_201_CREATED)
        pm_id = pm_resp.data["id"]

        # 3. Add Capability
        pc_resp = self.client.post(f"/api/v1/plan-versions/{v1_id}/capabilities/", {
            "plan_module_id": pm_id,
            "capability_id": str(cap.id),
        }, format="json")
        self.assertEqual(pc_resp.status_code, status.HTTP_201_CREATED)
        pc_id = pc_resp.data["id"]

        # 4. Attach Quota under capability
        q_resp = self.client.post(f"/api/v1/plan-versions/{v1_id}/quotas/", {
            "scope": "capability",
            "quota_key": "stream_hours",
            "name": "Stream Hours",
            "unit": "hours",
            "limit_type": "numeric",
            "limit_value": "100",
            "plan_capability_id": pc_id,
        }, format="json")
        self.assertEqual(q_resp.status_code, status.HTTP_201_CREATED)
        q_id = q_resp.data["id"]

        # 5. Delete PlanProduct triggers cascade deletion of modules, capabilities, and quotas
        del_pp = self.client.delete(f"/api/v1/plan-products/{pp_id}/")
        self.assertEqual(del_pp.status_code, status.HTTP_204_NO_CONTENT)

        self.assertFalse(PlanProduct.objects.filter(id=pp_id).exists())
        self.assertFalse(PlanModule.objects.filter(id=pm_id).exists())
        self.assertFalse(PlanCapability.objects.filter(id=pc_id).exists())
        self.assertFalse(PlanQuota.objects.filter(id=q_id).exists())

    # =========================================================================
    # 6. Quota Endpoints
    # =========================================================================

    def test_quota_contract_numeric_zero_bigint_and_validation(self):
        self.client.force_login(self.owner)
        plan_resp = self.client.post("/api/v1/plans/", {"code": "quota_plan", "name": "Quota Plan"}, format="json")
        v1_id = plan_resp.data["latest_version"]["id"]

        # 1. Numeric zero "0" accepted
        q0_resp = self.client.post(f"/api/v1/plan-versions/{v1_id}/quotas/", {
            "scope": "plan",
            "quota_key": "api_calls_zero",
            "name": "Zero Calls",
            "unit": "count",
            "limit_type": "numeric",
            "limit_value": "0",
        }, format="json")
        self.assertEqual(q0_resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(q0_resp.data["limit_value"], "0")

        # 2. BIGINT above JavaScript safe integer remains exact string
        bigint_str = "9007199254740992"
        q_big_resp = self.client.post(f"/api/v1/plan-versions/{v1_id}/quotas/", {
            "scope": "plan",
            "quota_key": "large_quota",
            "name": "Large Quota",
            "unit": "requests",
            "limit_type": "numeric",
            "limit_value": bigint_str,
        }, format="json")
        self.assertEqual(q_big_resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(q_big_resp.data["limit_value"], bigint_str)

        # 3. Leading zeros rejected
        bad_q = self.client.post(f"/api/v1/plan-versions/{v1_id}/quotas/", {
            "scope": "plan",
            "quota_key": "bad_leading",
            "name": "Bad",
            "unit": "count",
            "limit_type": "numeric",
            "limit_value": "05",
        }, format="json")
        self.assertEqual(bad_q.status_code, status.HTTP_400_BAD_REQUEST)

        # 4. Patch quota approved fields
        patch_resp = self.client.patch(f"/api/v1/plan-quotas/{q0_resp.data['id']}/", {
            "name": "Updated Zero Calls",
            "limit_value": "100",
        }, format="json")
        self.assertEqual(patch_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(patch_resp.data["name"], "Updated Zero Calls")
        self.assertEqual(patch_resp.data["limit_value"], "100")

        # 5. Patch quota immutable identity rejected
        bad_patch = self.client.patch(f"/api/v1/plan-quotas/{q0_resp.data['id']}/", {
            "quota_key": "cannot_change_key",
        }, format="json")
        self.assertEqual(bad_patch.status_code, status.HTTP_400_BAD_REQUEST)

    # =========================================================================
    # 7. List Querying, Filtering, Ordering & Pagination
    # =========================================================================

    def test_plan_list_filters_ordering_and_pagination(self):
        self.client.force_login(self.owner)
        for i in range(25):
            self.client.post("/api/v1/plans/", {
                "code": f"batch_plan_{i:02d}",
                "name": f"Batch Plan {i:02d}",
            }, format="json")

        # 1. Default page size = 20
        list_resp = self.client.get("/api/v1/plans/")
        self.assertEqual(list_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(list_resp.data["results"]), 20)
        self.assertEqual(list_resp.data["count"], 25)

        # 2. Custom page_size = 10
        page10_resp = self.client.get("/api/v1/plans/?page_size=10")
        self.assertEqual(page10_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(page10_resp.data["results"]), 10)

        # 3. Invalid ordering rejected with 400
        bad_order_resp = self.client.get("/api/v1/plans/?ordering=unsupported_col")
        self.assertEqual(bad_order_resp.status_code, status.HTTP_400_BAD_REQUEST)

        # 4. Invalid boolean filter rejected with 400
        bad_bool_resp = self.client.get("/api/v1/plans/?has_active_version=invalid")
        self.assertEqual(bad_bool_resp.status_code, status.HTTP_400_BAD_REQUEST)

        # 5. Search filter
        search_resp = self.client.get("/api/v1/plans/?search=batch_plan_05")
        self.assertEqual(search_resp.status_code, status.HTTP_200_OK)
        # 6. Invalid page sizes (zero, negative, non-integer, >100) return 400
        for bad_ps in [0, -1, "abc", 101]:
            with self.subTest(bad_page_size=bad_ps):
                bad_ps_resp = self.client.get(f"/api/v1/plans/?page_size={bad_ps}")
                self.assertEqual(bad_ps_resp.status_code, status.HTTP_400_BAD_REQUEST)

        # 7. catalog_health filter: healthy, degraded, all valid; others 400
        for valid_h in ["healthy", "degraded", "all"]:
            with self.subTest(valid_catalog_health=valid_h):
                h_resp = self.client.get(f"/api/v1/plans/?catalog_health={valid_h}")
                self.assertEqual(h_resp.status_code, status.HTTP_200_OK)
        bad_h_resp = self.client.get("/api/v1/plans/?catalog_health=broken")
        self.assertEqual(bad_h_resp.status_code, status.HTTP_400_BAD_REQUEST)

        # 8. Boolean filters accept only true, false, all
        for bf in ["has_active_version", "has_draft_version"]:
            for valid_val in ["true", "false", "all"]:
                with self.subTest(filter=bf, val=valid_val):
                    r = self.client.get(f"/api/v1/plans/?{bf}={valid_val}")
                    self.assertEqual(r.status_code, status.HTTP_200_OK)
            bad_bf = self.client.get(f"/api/v1/plans/?{bf}=maybe")
            self.assertEqual(bad_bf.status_code, status.HTTP_400_BAD_REQUEST)

        # 9. Unsupported query parameter returns 400
        unsupported_param_resp = self.client.get("/api/v1/plans/?unexpected_filter=foo")
        self.assertEqual(unsupported_param_resp.status_code, status.HTTP_400_BAD_REQUEST)

        # 10. catalog_health is not a persisted DB column
        self.assertNotIn("catalog_health", [f.name for f in Plan._meta.fields])

    def test_serialization_and_number_formats_comprehensive(self):
        self.client.force_login(self.owner)
        plan, v = create_plan(code="num_contract_plan", name="Num Contract Plan", actor=self.owner)

        # 1. Price non-canonical formats rejected
        bad_amounts = [
            19.99, "19.9", "19.999", "019.99", "+19.99", "-19.99",
            "1,000.00", " 19.99 ", "1e2", "NaN", "Infinity",
        ]
        for bad_amt in bad_amounts:
            with self.subTest(bad_amount=bad_amt):
                r = self.client.post(f"/api/v1/plan-versions/{v.id}/prices/", {
                    "currency": "USD",
                    "billing_interval": "monthly",
                    "amount": bad_amt,
                }, format="json")
                self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

        # 2. Valid price string format
        valid_p = self.client.post(f"/api/v1/plan-versions/{v.id}/prices/", {
            "currency": "USD",
            "billing_interval": "monthly",
            "amount": "0.00",
        }, format="json")
        self.assertEqual(valid_p.status_code, status.HTTP_201_CREATED)
        self.assertEqual(valid_p.data["amount"], "0.00")

        # 3. Quota numeric zero and leading zero rejection
        for bad_q_val in ["00", "01", "000100", "+5", "-5", "1.5", "1e3"]:
            with self.subTest(bad_quota_val=bad_q_val):
                r = self.client.post(f"/api/v1/plan-versions/{v.id}/quotas/", {
                    "scope": "plan",
                    "quota_key": f"bad_q_{abs(hash(str(bad_q_val))) % 10000}",
                    "name": "Bad Quota",
                    "unit": "count",
                    "limit_type": "numeric",
                    "limit_value": bad_q_val,
                }, format="json")
                self.assertEqual(r.status_code, status.HTTP_400_BAD_REQUEST)

        # 4. Quota maximum BIGINT and boundary rejection
        max_bigint = "9223372036854775807"
        beyond_bigint = "9223372036854775808"
        max_q = self.client.post(f"/api/v1/plan-versions/{v.id}/quotas/", {
            "scope": "plan",
            "quota_key": "max_bigint_q",
            "name": "Max BIGINT",
            "unit": "count",
            "limit_type": "numeric",
            "limit_value": max_bigint,
        }, format="json")
        self.assertEqual(max_q.status_code, status.HTTP_201_CREATED)
        self.assertEqual(max_q.data["limit_value"], max_bigint)

        over_q = self.client.post(f"/api/v1/plan-versions/{v.id}/quotas/", {
            "scope": "plan",
            "quota_key": "over_bigint_q",
            "name": "Over BIGINT",
            "unit": "count",
            "limit_type": "numeric",
            "limit_value": beyond_bigint,
        }, format="json")
        self.assertEqual(over_q.status_code, status.HTTP_400_BAD_REQUEST)

        # 5. Plan detail returns summary objects without embedding full version history
        detail_resp = self.client.get(f"/api/v1/plans/{plan.id}/")
        self.assertEqual(detail_resp.status_code, status.HTTP_200_OK)
        self.assertIn("active_version", detail_resp.data)
        self.assertIn("latest_version", detail_resp.data)
        self.assertNotIn("versions", detail_resp.data)

        # 6. Readiness stale items types strictly valid
        readiness_resp = self.client.get(f"/api/v1/plan-versions/{v.id}/readiness/")
        self.assertEqual(readiness_resp.status_code, status.HTTP_200_OK)
        allowed_types = {"product", "module", "feature", "capability"}
        for item in readiness_resp.data.get("stale_items", []):
            self.assertIn(item["type"], allowed_types)

    def test_query_count_stability_1_vs_10_plans(self):
        self.client.force_login(self.owner)
        Plan.objects.all().delete()

        # 1 Plan query count
        create_plan(code="stab_plan_00", name="Stability Plan 00", actor=self.owner)
        with CaptureQueriesContext(connection) as ctx1:
            resp1 = self.client.get("/api/v1/plans/?page_size=10")
            self.assertEqual(resp1.status_code, status.HTTP_200_OK)
            self.assertEqual(len(resp1.data["results"]), 1)

        # 9 more Plans (total 10)
        for i in range(1, 10):
            create_plan(code=f"stab_plan_{i:02d}", name=f"Stability Plan {i:02d}", actor=self.owner)

        with CaptureQueriesContext(connection) as ctx10:
            resp10 = self.client.get("/api/v1/plans/?page_size=10")
            self.assertEqual(resp10.status_code, status.HTTP_200_OK)
            self.assertEqual(len(resp10.data["results"]), 10)

        # Query counts must be bounded and independent of returned row count
        count_1 = len(ctx1.captured_queries)
        count_10 = len(ctx10.captured_queries)
        self.assertEqual(count_1, count_10)
        self.assertLessEqual(count_10, 15)

    # =========================================================================
    # 8. Audit Trail Integration
    # =========================================================================

    def test_successful_api_mutation_generates_audit_and_rejected_generates_zero(self):
        self.client.force_login(self.owner)
        audits_count_before = AuditLog.objects.count()

        # Successful creation -> generates audit events (plan_created, plan_version_created)
        resp = self.client.post("/api/v1/plans/", {
            "code": "audit_gen_plan",
            "name": "Audit Gen Plan",
        }, format="json")
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(AuditLog.objects.count(), audits_count_before + 2)

        audits_after = AuditLog.objects.count()

        # Rejected creation (duplicate code) -> generates 0 new audit events
        bad_resp = self.client.post("/api/v1/plans/", {
            "code": "audit_gen_plan",
            "name": "Duplicate Code",
        }, format="json")
        self.assertEqual(bad_resp.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(AuditLog.objects.count(), audits_after)

    # =========================================================================
    # 9. Plan Quota API Contract & Custom Units
    # =========================================================================

    def test_plan_quota_api_custom_units_and_audit_behavior(self):
        self.client.force_login(self.owner)

        # Setup draft plan version
        resp_plan = self.client.post("/api/v1/plans/", {
            "code": "quota_api_plan",
            "name": "Quota API Plan",
        }, format="json")
        self.assertEqual(resp_plan.status_code, status.HTTP_201_CREATED)
        version_id = resp_plan.data["latest_version"]["id"]

        # 1. Create quota with documents -> success 201
        resp_docs = self.client.post(f"/api/v1/plan-versions/{version_id}/quotas/", {
            "scope": "plan",
            "quota_key": "q_docs",
            "name": "Documents Quota",
            "unit": "documents",
            "limit_type": "numeric",
            "limit_value": "1000",
            "reset_period": "monthly",
            "is_hard_limit": True,
        }, format="json")
        self.assertEqual(resp_docs.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp_docs.data["unit"], "documents")
        docs_quota_id = resp_docs.data["id"]

        # 2. Create quota with storage_gb -> success 201
        resp_storage = self.client.post(f"/api/v1/plan-versions/{version_id}/quotas/", {
            "scope": "plan",
            "quota_key": "q_storage",
            "name": "Storage Quota",
            "unit": "storage_gb",
            "limit_type": "numeric",
            "limit_value": "50",
            "reset_period": "never",
            "is_hard_limit": True,
        }, format="json")
        self.assertEqual(resp_storage.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp_storage.data["unit"], "storage_gb")

        # 3. Existing suggested units still work
        resp_suggested = self.client.post(f"/api/v1/plan-versions/{version_id}/quotas/", {
            "scope": "plan",
            "quota_key": "q_api_calls",
            "name": "API Calls Quota",
            "unit": "api_calls",
            "limit_type": "numeric",
            "limit_value": "10000",
            "reset_period": "monthly",
            "is_hard_limit": True,
        }, format="json")
        self.assertEqual(resp_suggested.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp_suggested.data["unit"], "api_calls")

        # 4. PATCH unit to video_minutes -> success 200
        patch_resp = self.client.patch(f"/api/v1/plan-quotas/{docs_quota_id}/", {
            "unit": "video_minutes",
        }, format="json")
        self.assertEqual(patch_resp.status_code, status.HTTP_200_OK)
        self.assertEqual(patch_resp.data["unit"], "video_minutes")

        # 5. Invalid units return HTTP 400 and emit ZERO audit events
        invalid_unit_payloads = [
            {"unit": "video-minutes"},   # hyphen
            {"unit": "GB"},              # uppercase
            {"unit": " gb"},             # leading whitespace
            {"unit": "gb "},             # trailing whitespace
            {"unit": "g b"},             # internal whitespace
            {"unit": "a" * 33},          # > 32 characters
            {"unit": ""},                # empty string
        ]
        for bad_payload in invalid_unit_payloads:
            audits_before = AuditLog.objects.count()
            bad_resp = self.client.patch(f"/api/v1/plan-quotas/{docs_quota_id}/", bad_payload, format="json")
            self.assertEqual(bad_resp.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertEqual(AuditLog.objects.count(), audits_before)

        # 6. Unknown and protected fields remain rejected with HTTP 400 and zero audit
        protected_payloads = [
            {"unknown_field": "val"},
            {"plan_version_id": str(uuid.uuid4())},
            {"scope": "product"},
            {"quota_key": "new_key"},
        ]
        for prot_payload in protected_payloads:
            audits_before = AuditLog.objects.count()
            prot_resp = self.client.patch(f"/api/v1/plan-quotas/{docs_quota_id}/", prot_payload, format="json")
            self.assertEqual(prot_resp.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertEqual(AuditLog.objects.count(), audits_before)

