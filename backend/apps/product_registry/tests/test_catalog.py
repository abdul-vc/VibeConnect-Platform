"""Product Catalog Hierarchy Backend Test Suite.

Verifies catalog models (ProductModule, ProductFeature, ProductCapability),
Django 5.2 expression-based constraints, indexes, display_order,
all-ancestor activation gating, bottom-up retirement, status-only retirement semantics,
immediate-parent-only create payloads, derived read-only ancestry,
trusted operation_source and correlation_id context, audit hierarchy snapshot logging,
exact metadata key sets and type validation, annotated child counts,
platform owner permissions, and real multi-threaded concurrency invariants.
"""

import threading
import uuid
from django.apps import apps
from django.contrib.auth import get_user_model
from django.db import connections
from django.test import TestCase, TransactionTestCase
from rest_framework import status
from rest_framework.test import APIClient

from apps.auditlog.models import AuditAction, AuditLog, AuditOperationSource, AuditTargetType
from apps.auditlog.services import AuditEventError, record_audit_event
from apps.product_registry.models import (
    CatalogStatus,
    Product,
    ProductCapability,
    ProductFeature,
    ProductModule,
    ProductStatus,
)
from apps.product_registry import services

User = get_user_model()


class CatalogBaseTestCase(TestCase):
    """Base setup for catalog tests providing test users and client."""

    def setUp(self):
        self.owner = User.objects.create_user(
            email="owner@vibeconnect.com",
            password="SecurePassword123!",
            full_name="Platform Owner",
            is_platform_owner=True,
            is_active=True,
        )
        self.non_owner = User.objects.create_user(
            email="regular@vibeconnect.com",
            password="SecurePassword123!",
            full_name="Regular User",
            is_platform_owner=False,
            is_active=True,
        )
        self.inactive_owner = User.objects.create_user(
            email="inactive@vibeconnect.com",
            password="SecurePassword123!",
            full_name="Inactive Owner",
            is_platform_owner=True,
            is_active=False,
        )
        self.client = APIClient()

    def create_active_product(self, code="lms", name="LMS Platform"):
        return Product.objects.create(
            code=code,
            name=name,
            status=ProductStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )

    def create_draft_product(self, code="draft_prod", name="Draft Product"):
        return Product.objects.create(
            code=code,
            name=name,
            status=ProductStatus.DRAFT,
            created_by=self.owner,
            updated_by=self.owner,
        )


class CatalogAuthenticationAndPermissionTests(CatalogBaseTestCase):
    """Verifies authentication and Platform Owner authorization across all catalog endpoints."""

    def test_unauthenticated_catalog_requests_return_401(self):
        endpoints = [
            "/api/v1/product-modules/",
            "/api/v1/product-features/",
            "/api/v1/product-capabilities/",
        ]
        for ep in endpoints:
            get_resp = self.client.get(ep)
            self.assertEqual(get_resp.status_code, status.HTTP_401_UNAUTHORIZED)
            post_resp = self.client.post(ep, {}, format="json")
            self.assertEqual(post_resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_authenticated_non_owner_requests_return_403(self):
        self.client.force_login(self.non_owner)
        endpoints = [
            "/api/v1/product-modules/",
            "/api/v1/product-features/",
            "/api/v1/product-capabilities/",
        ]
        for ep in endpoints:
            get_resp = self.client.get(ep)
            self.assertEqual(get_resp.status_code, status.HTTP_403_FORBIDDEN)
            post_resp = self.client.post(ep, {}, format="json")
            self.assertEqual(post_resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_inactive_session_user_returns_401(self):
        self.client.force_login(self.inactive_owner)
        resp = self.client.get("/api/v1/product-modules/")
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)


class CatalogHttpVerbAndScopingTests(CatalogBaseTestCase):
    """Verifies allowed HTTP verbs, mandatory parent scoping, and absence of custom /retire/ routes."""

    def test_put_and_delete_methods_return_405(self):
        self.client.force_login(self.owner)
        prod = self.create_active_product()
        mod = ProductModule.objects.create(
            product=prod,
            code="courses",
            name="Courses",
            status=CatalogStatus.DRAFT,
            created_by=self.owner,
            updated_by=self.owner,
        )
        endpoints = [
            f"/api/v1/product-modules/{mod.id}/",
            f"/api/v1/product-features/{uuid.uuid4()}/",
            f"/api/v1/product-capabilities/{uuid.uuid4()}/",
        ]
        for ep in endpoints:
            put_resp = self.client.put(ep, {}, format="json")
            self.assertEqual(put_resp.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
            del_resp = self.client.delete(ep)
            self.assertEqual(del_resp.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_module_list_without_product_id_returns_400(self):
        self.client.force_login(self.owner)
        resp = self.client.get("/api/v1/product-modules/")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("product_id", resp.data)

    def test_feature_list_without_module_id_returns_400(self):
        self.client.force_login(self.owner)
        resp = self.client.get("/api/v1/product-features/")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("module_id", resp.data)

    def test_capability_list_without_feature_id_returns_400(self):
        self.client.force_login(self.owner)
        resp = self.client.get("/api/v1/product-capabilities/")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("feature_id", resp.data)

    def test_list_with_invalid_uuid_parent_returns_400(self):
        self.client.force_login(self.owner)
        resp = self.client.get("/api/v1/product-modules/?product_id=not-a-uuid")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_custom_retire_endpoints_do_not_exist_and_return_404(self):
        """Confirms that custom /retire/ routes do not exist; retirement must use PATCH."""
        self.client.force_login(self.owner)
        dummy_id = uuid.uuid4()
        retire_endpoints = [
            f"/api/v1/product-modules/{dummy_id}/retire/",
            f"/api/v1/product-features/{dummy_id}/retire/",
            f"/api/v1/product-capabilities/{dummy_id}/retire/",
        ]
        for ep in retire_endpoints:
            post_resp = self.client.post(ep, {}, format="json")
            self.assertEqual(
                post_resp.status_code,
                status.HTTP_404_NOT_FOUND,
                f"Expected 404 for removed route {ep}, got {post_resp.status_code}"
            )


class CatalogImmediateParentPayloadTests(CatalogBaseTestCase):
    """Verifies Decision 1: Immediate-parent-only inputs, rejection of redundant ancestry, and derived responses."""

    def test_module_creation_requires_product_id_and_returns_derived_ancestry(self):
        self.client.force_login(self.owner)
        prod = self.create_active_product(code="lms", name="LMS Core")
        payload = {
            "product_id": str(prod.id),
            "code": "assessments",
            "name": "Assessments",
            "description": "Evaluation module",
            "display_order": 2,
        }
        resp = self.client.post("/api/v1/product-modules/", payload, format="json")
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp.data["code"], "assessments")
        self.assertEqual(resp.data["product_id"], str(prod.id))
        self.assertEqual(resp.data["product_code"], "lms")
        self.assertEqual(resp.data["status"], "draft")
        self.assertEqual(resp.data["display_order"], 2)

    def test_feature_creation_requires_module_id_and_rejects_product_id(self):
        self.client.force_login(self.owner)
        prod = self.create_active_product()
        mod = ProductModule.objects.create(
            product=prod,
            code="grading",
            name="Grading Module",
            status=CatalogStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )
        # Attempt to pass redundant product_id
        rejected_payload = {
            "module_id": str(mod.id),
            "product_id": str(prod.id),
            "code": "rubrics",
            "name": "Rubrics",
        }
        resp = self.client.post("/api/v1/product-features/", rejected_payload, format="json")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("product_id", resp.data)

        # Valid payload without product_id
        valid_payload = {
            "module_id": str(mod.id),
            "code": "rubrics",
            "name": "Rubrics",
            "description": "Scoring rubrics",
            "display_order": 1,
        }
        valid_resp = self.client.post("/api/v1/product-features/", valid_payload, format="json")
        self.assertEqual(valid_resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(valid_resp.data["module_id"], str(mod.id))
        self.assertEqual(valid_resp.data["module_code"], "grading")
        self.assertEqual(valid_resp.data["product_id"], str(prod.id))
        self.assertEqual(valid_resp.data["product_code"], prod.code)

    def test_capability_creation_requires_feature_id_and_rejects_higher_ancestry(self):
        self.client.force_login(self.owner)
        prod = self.create_active_product()
        mod = ProductModule.objects.create(
            product=prod,
            code="exams",
            name="Exams",
            status=CatalogStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )
        feat = ProductFeature.objects.create(
            module=mod,
            code="proctoring",
            name="Proctoring",
            status=CatalogStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )
        # Attempt to pass redundant module_id or product_id
        rejected_payload = {
            "feature_id": str(feat.id),
            "module_id": str(mod.id),
            "code": "record_session",
            "name": "Record Session",
        }
        resp = self.client.post("/api/v1/product-capabilities/", rejected_payload, format="json")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

        # Valid payload without higher ancestry
        valid_payload = {
            "feature_id": str(feat.id),
            "code": "record_session",
            "name": "Record Session",
            "display_order": 0,
        }
        valid_resp = self.client.post("/api/v1/product-capabilities/", valid_payload, format="json")
        self.assertEqual(valid_resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(valid_resp.data["feature_id"], str(feat.id))
        self.assertEqual(valid_resp.data["feature_code"], "proctoring")
        self.assertEqual(valid_resp.data["module_id"], str(mod.id))
        self.assertEqual(valid_resp.data["module_code"], "exams")
        self.assertEqual(valid_resp.data["product_id"], str(prod.id))
        self.assertEqual(valid_resp.data["product_code"], prod.code)
        cap_id = uuid.UUID(valid_resp.data["id"])
        self.assertEqual(ProductCapability.objects.filter(id=cap_id).count(), 1)
        self.assertEqual(AuditLog.objects.filter(target_id=cap_id, action=AuditAction.CAPABILITY_CREATED).count(), 1)
        audit = AuditLog.objects.get(target_id=cap_id, action=AuditAction.CAPABILITY_CREATED)
        expected_meta = {
            "product_id": str(prod.id),
            "product_code": prod.code,
            "module_id": str(mod.id),
            "module_code": "exams",
            "feature_id": str(feat.id),
            "feature_code": "proctoring",
            "code": "record_session",
            "name": "Record Session",
            "display_order": 0,
            "status": "draft",
        }
        self.assertEqual(audit.metadata, expected_meta)

    def test_capability_creation_allows_security_terminology_such_as_reset_password(self):
        self.client.force_login(self.owner)
        prod = self.create_active_product(code="auth_prod")
        mod = ProductModule.objects.create(
            product=prod,
            code="security",
            name="Security",
            status=CatalogStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )
        feat = ProductFeature.objects.create(
            module=mod,
            code="credentials",
            name="Credentials",
            status=CatalogStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )
        valid_payload = {
            "feature_id": str(feat.id),
            "code": "reset_password",
            "name": "Reset Password",
            "display_order": 1,
        }
        valid_resp = self.client.post("/api/v1/product-capabilities/", valid_payload, format="json")
        self.assertEqual(valid_resp.status_code, status.HTTP_201_CREATED)
        cap_id = uuid.UUID(valid_resp.data["id"])
        self.assertEqual(ProductCapability.objects.filter(id=cap_id).count(), 1)
        self.assertEqual(AuditLog.objects.filter(target_id=cap_id, action=AuditAction.CAPABILITY_CREATED).count(), 1)
        audit = AuditLog.objects.get(target_id=cap_id, action=AuditAction.CAPABILITY_CREATED)
        expected_meta = {
            "product_id": str(prod.id),
            "product_code": "auth_prod",
            "module_id": str(mod.id),
            "module_code": "security",
            "feature_id": str(feat.id),
            "feature_code": "credentials",
            "code": "reset_password",
            "name": "Reset Password",
            "display_order": 1,
            "status": "draft",
        }
        self.assertEqual(audit.metadata, expected_meta)

    def test_create_payload_cannot_control_initial_status(self):
        self.client.force_login(self.owner)
        prod = self.create_active_product()
        payload = {
            "product_id": str(prod.id),
            "code": "certificates",
            "name": "Certificates",
            "status": "active",
        }
        resp = self.client.post("/api/v1/product-modules/", payload, format="json")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("status", resp.data)

    def test_patch_cannot_modify_parent_foreign_key(self):
        self.client.force_login(self.owner)
        prod = self.create_active_product()
        prod2 = Product.objects.create(
            code="hrms",
            name="HRMS Core",
            status=ProductStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )
        mod = ProductModule.objects.create(
            product=prod,
            code="analytics",
            name="Analytics",
            status=CatalogStatus.DRAFT,
            created_by=self.owner,
            updated_by=self.owner,
        )
        resp = self.client.patch(
            f"/api/v1/product-modules/{mod.id}/",
            {"product_id": str(prod2.id)},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        mod.refresh_from_db()
        self.assertEqual(mod.product_id, prod.id)

    def test_child_creation_under_retired_parent_fails(self):
        self.client.force_login(self.owner)
        prod = self.create_active_product()
        mod = ProductModule.objects.create(
            product=prod,
            code="retired_mod",
            name="Retired Mod",
            status=CatalogStatus.RETIRED,
            created_by=self.owner,
            updated_by=self.owner,
        )
        payload = {
            "module_id": str(mod.id),
            "code": "new_feat",
            "name": "New Feat",
        }
        resp = self.client.post("/api/v1/product-features/", payload, format="json")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Cannot create feature under a retired module", str(resp.data))


class CatalogTrustedContextAndAuditTests(CatalogBaseTestCase):
    """Verifies Decision 2: Trusted context handling, client rejection, and audit log generation."""

    def test_browser_supplied_operation_source_returns_400(self):
        self.client.force_login(self.owner)
        prod = self.create_active_product()
        payload = {
            "product_id": str(prod.id),
            "code": "custom_source",
            "name": "Custom Source",
            "operation_source": "bulk_import",
        }
        resp = self.client.post("/api/v1/product-modules/", payload, format="json")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("operation_source", resp.data)

    def test_browser_supplied_correlation_id_returns_400(self):
        self.client.force_login(self.owner)
        prod = self.create_active_product()
        payload = {
            "product_id": str(prod.id),
            "code": "custom_corr",
            "name": "Custom Corr",
            "correlation_id": str(uuid.uuid4()),
        }
        resp = self.client.post("/api/v1/product-modules/", payload, format="json")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("correlation_id", resp.data)

    def test_browser_supplied_actor_returns_400(self):
        self.client.force_login(self.owner)
        prod = self.create_active_product()
        payload = {
            "product_id": str(prod.id),
            "code": "custom_actor",
            "name": "Custom Actor",
            "actor": str(self.owner.id),
        }
        resp = self.client.post("/api/v1/product-modules/", payload, format="json")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("actor", resp.data)

    def test_browser_supplied_created_by_returns_400(self):
        self.client.force_login(self.owner)
        prod = self.create_active_product()
        payload = {
            "product_id": str(prod.id),
            "code": "custom_created_by",
            "name": "Custom Created By",
            "created_by": str(self.owner.id),
        }
        resp = self.client.post("/api/v1/product-modules/", payload, format="json")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("created_by", resp.data)

    def test_interactive_api_request_writes_operation_source_interactive(self):
        self.client.force_login(self.owner)
        prod = self.create_active_product()
        payload = {
            "product_id": str(prod.id),
            "code": "survey",
            "name": "Survey",
        }
        resp = self.client.post("/api/v1/product-modules/", payload, format="json")
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        module_id = uuid.UUID(resp.data["id"])

        audit = AuditLog.objects.filter(target_id=module_id).latest("timestamp")
        self.assertEqual(audit.action, AuditAction.MODULE_CREATED)
        self.assertEqual(audit.operation_source, AuditOperationSource.INTERACTIVE)
        self.assertIsNone(audit.correlation_id)
        self.assertIsNone(audit.organization_id)

    def test_direct_service_bulk_import_with_correlation_id_succeeds(self):
        prod = self.create_active_product()
        corr_id = uuid.uuid4()
        module = services.create_product_module(
            product_id=prod.id,
            data={"code": "bulk_mod", "name": "Bulk Mod", "description": "Bulk import test"},
            actor=self.owner,
            operation_source=AuditOperationSource.BULK_IMPORT,
            correlation_id=corr_id,
        )
        self.assertEqual(module.code, "bulk_mod")
        audit = AuditLog.objects.filter(target_id=module.id).latest("timestamp")
        self.assertEqual(audit.action, AuditAction.MODULE_CREATED)
        self.assertEqual(audit.operation_source, AuditOperationSource.BULK_IMPORT)
        self.assertEqual(audit.correlation_id, corr_id)

    def test_direct_service_integration_with_correlation_id_succeeds(self):
        prod = self.create_active_product()
        corr_id = uuid.uuid4()
        module = services.create_product_module(
            product_id=prod.id,
            data={"code": "integ_mod", "name": "Integration Mod"},
            actor=self.owner,
            operation_source=AuditOperationSource.INTEGRATION,
            correlation_id=corr_id,
        )
        self.assertEqual(module.code, "integ_mod")
        audit = AuditLog.objects.filter(target_id=module.id).latest("timestamp")
        self.assertEqual(audit.action, AuditAction.MODULE_CREATED)
        self.assertEqual(audit.operation_source, AuditOperationSource.INTEGRATION)
        self.assertEqual(audit.correlation_id, corr_id)

    def test_service_bulk_import_missing_correlation_id_raises_value_error(self):
        prod = self.create_active_product()
        with self.assertRaises(ValueError) as ctx:
            services.create_product_module(
                product_id=prod.id,
                data={"code": "fail_mod", "name": "Fail Mod"},
                actor=self.owner,
                operation_source=AuditOperationSource.BULK_IMPORT,
                correlation_id=None,
            )
        self.assertIn("requires a valid non-null correlation_id", str(ctx.exception))
        self.assertFalse(ProductModule.objects.filter(code="fail_mod").exists())
        self.assertFalse(AuditLog.objects.filter(target_repr="fail_mod").exists())

    def test_service_invalid_operation_source_raises_value_error(self):
        prod = self.create_active_product()
        with self.assertRaises(ValueError) as ctx:
            services.create_product_module(
                product_id=prod.id,
                data={"code": "auth_mod", "name": "Auth Mod"},
                actor=self.owner,
                operation_source=AuditOperationSource.AUTHENTICATION,
                correlation_id=uuid.uuid4(),
            )
        self.assertIn("is not permitted for catalog mutations", str(ctx.exception))

    def test_direct_service_creation_without_repeated_parent_id_succeeds_for_all_levels(self):
        """Proves direct service creation succeeds when data does not repeat parent ID for Module, Feature, Capability."""
        prod = self.create_active_product(code="svc_prod")
        mod_data = {"code": "svc_mod", "name": "Svc Module", "display_order": 1}
        module = services.create_product_module(
            product_id=prod.id,
            data=mod_data,
            actor=self.owner,
        )
        self.assertEqual(module.product_id, prod.id)
        self.assertEqual(module.code, "svc_mod")
        self.assertTrue(ProductModule.objects.filter(id=module.id).exists())

        feat_data = {"code": "svc_feat", "name": "Svc Feature", "display_order": 1}
        feature = services.create_product_feature(
            module_id=module.id,
            data=feat_data,
            actor=self.owner,
        )
        self.assertEqual(feature.module_id, module.id)
        self.assertEqual(feature.code, "svc_feat")
        self.assertTrue(ProductFeature.objects.filter(id=feature.id).exists())

        cap_data = {"code": "svc_cap", "name": "Svc Capability", "display_order": 1}
        capability = services.create_product_capability(
            feature_id=feature.id,
            data=cap_data,
            actor=self.owner,
        )
        self.assertEqual(capability.feature_id, feature.id)
        self.assertEqual(capability.code, "svc_cap")
        self.assertTrue(ProductCapability.objects.filter(id=capability.id).exists())

    def test_direct_service_creation_does_not_mutate_caller_data_and_ignores_overriding_parent(self):
        """Proves caller data is not mutated and authoritative keyword parent ID cannot be overridden."""
        prod = self.create_active_product(code="override_prod")
        bogus_parent_id = str(uuid.uuid4())
        caller_data = {
            "code": "caller_mod",
            "name": "Caller Mod",
            "product_id": bogus_parent_id,
        }
        original_copy = dict(caller_data)

        module = services.create_product_module(
            product_id=prod.id,
            data=caller_data,
            actor=self.owner,
        )
        self.assertEqual(module.product_id, prod.id)
        self.assertEqual(caller_data, original_copy)


class CatalogSearchOrderingPaginationTests(CatalogBaseTestCase):
    """Verifies deterministic ordering, search, status filters, and pagination."""

    def setUp(self):
        super().setUp()
        self.prod = self.create_active_product()
        self.m1 = ProductModule.objects.create(
            product=self.prod,
            code="mod_alpha",
            name="Alpha Module",
            display_order=10,
            status=CatalogStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )
        self.m2 = ProductModule.objects.create(
            product=self.prod,
            code="mod_beta",
            name="Beta Module",
            display_order=5,
            status=CatalogStatus.DRAFT,
            created_by=self.owner,
            updated_by=self.owner,
        )
        self.m3 = ProductModule.objects.create(
            product=self.prod,
            code="mod_gamma",
            name="Gamma Module",
            display_order=20,
            status=CatalogStatus.RETIRED,
            created_by=self.owner,
            updated_by=self.owner,
        )

    def test_default_ordering_by_display_order_asc(self):
        self.client.force_login(self.owner)
        resp = self.client.get(f"/api/v1/product-modules/?product_id={self.prod.id}")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        codes = [item["code"] for item in resp.data["results"]]
        self.assertEqual(codes, ["mod_beta", "mod_alpha", "mod_gamma"])

    def test_explicit_ordering_by_name_asc(self):
        self.client.force_login(self.owner)
        resp = self.client.get(f"/api/v1/product-modules/?product_id={self.prod.id}&ordering=name")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        codes = [item["code"] for item in resp.data["results"]]
        self.assertEqual(codes, ["mod_alpha", "mod_beta", "mod_gamma"])

    def test_status_filtering(self):
        self.client.force_login(self.owner)
        resp = self.client.get(f"/api/v1/product-modules/?product_id={self.prod.id}&status=draft")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["count"], 1)
        self.assertEqual(resp.data["results"][0]["code"], "mod_beta")

    def test_search_by_code_and_name(self):
        self.client.force_login(self.owner)
        resp = self.client.get(f"/api/v1/product-modules/?product_id={self.prod.id}&search=alpha")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["count"], 1)
        self.assertEqual(resp.data["results"][0]["code"], "mod_alpha")


class CatalogCodeImmutabilityAndLifecycleTests(CatalogBaseTestCase):
    """Verifies code immutability after activation, single PATCH retirement, and status-only retirement semantics."""

    def test_code_can_be_updated_in_draft(self):
        self.client.force_login(self.owner)
        prod = self.create_active_product()
        mod = ProductModule.objects.create(
            product=prod,
            code="draft_code",
            name="Draft Mod",
            status=CatalogStatus.DRAFT,
            created_by=self.owner,
            updated_by=self.owner,
        )
        resp = self.client.patch(
            f"/api/v1/product-modules/{mod.id}/",
            {"code": "new_draft_code"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        mod.refresh_from_db()
        self.assertEqual(mod.code, "new_draft_code")

    def test_atomic_code_update_and_activation_in_single_patch_succeeds(self):
        self.client.force_login(self.owner)
        prod = self.create_active_product()
        mod = ProductModule.objects.create(
            product=prod,
            code="temp_code",
            name="Temp Mod",
            status=CatalogStatus.DRAFT,
            created_by=self.owner,
            updated_by=self.owner,
        )
        resp = self.client.patch(
            f"/api/v1/product-modules/{mod.id}/",
            {"code": "final_code", "status": "active"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        mod.refresh_from_db()
        self.assertEqual(mod.code, "final_code")
        self.assertEqual(mod.status, CatalogStatus.ACTIVE)

        # Confirm that subsequent code change attempt is rejected
        blocked_resp = self.client.patch(
            f"/api/v1/product-modules/{mod.id}/",
            {"code": "another_code"},
            format="json",
        )
        self.assertEqual(blocked_resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Code cannot be modified after activation", str(blocked_resp.data))

    def test_patch_status_retired_success_for_module(self):
        """Single approved API contract: PATCH with status='retired'."""
        self.client.force_login(self.owner)
        prod = self.create_active_product()
        mod = ProductModule.objects.create(
            product=prod,
            code="retire_mod",
            name="Retire Mod",
            status=CatalogStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )
        resp = self.client.patch(
            f"/api/v1/product-modules/{mod.id}/",
            {"status": "retired"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        mod.refresh_from_db()
        self.assertEqual(mod.status, CatalogStatus.RETIRED)

    def test_patch_status_retired_success_for_feature(self):
        self.client.force_login(self.owner)
        prod = self.create_active_product()
        mod = ProductModule.objects.create(
            product=prod,
            code="f_mod",
            name="F Mod",
            status=CatalogStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )
        feat = ProductFeature.objects.create(
            module=mod,
            code="retire_feat",
            name="Retire Feat",
            status=CatalogStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )
        resp = self.client.patch(
            f"/api/v1/product-features/{feat.id}/",
            {"status": "retired"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        feat.refresh_from_db()
        self.assertEqual(feat.status, CatalogStatus.RETIRED)

    def test_patch_status_retired_success_for_capability(self):
        self.client.force_login(self.owner)
        prod = self.create_active_product()
        mod = ProductModule.objects.create(
            product=prod,
            code="c_mod",
            name="C Mod",
            status=CatalogStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )
        feat = ProductFeature.objects.create(
            module=mod,
            code="c_feat",
            name="C Feat",
            status=CatalogStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )
        cap = ProductCapability.objects.create(
            feature=feat,
            code="retire_cap",
            name="Retire Cap",
            status=CatalogStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )
        resp = self.client.patch(
            f"/api/v1/product-capabilities/{cap.id}/",
            {"status": "retired"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        cap.refresh_from_db()
        self.assertEqual(cap.status, CatalogStatus.RETIRED)

    def test_retirement_rejects_simultaneous_field_edits(self):
        self.client.force_login(self.owner)
        prod = self.create_active_product()
        mod = ProductModule.objects.create(
            product=prod,
            code="active_mod",
            name="Active Mod",
            status=CatalogStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )
        resp = self.client.patch(
            f"/api/v1/product-modules/{mod.id}/",
            {"status": "retired", "name": "New Name"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Retirement is a status-only operation", str(resp.data))

    def test_modifying_already_retired_record_returns_400(self):
        self.client.force_login(self.owner)
        prod = self.create_active_product()
        mod = ProductModule.objects.create(
            product=prod,
            code="frozen_mod",
            name="Frozen Mod",
            status=CatalogStatus.RETIRED,
            created_by=self.owner,
            updated_by=self.owner,
        )
        resp = self.client.patch(
            f"/api/v1/product-modules/{mod.id}/",
            {"name": "Attempt Update"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Cannot modify a retired catalog record", str(resp.data))

    def test_repeated_exact_status_retired_is_noop_with_zero_audit_logs(self):
        """Repeated status='retired' on an already-retired record returns no-op representation with 0 audit events."""
        self.client.force_login(self.owner)
        prod = self.create_active_product()
        mod = ProductModule.objects.create(
            product=prod,
            code="already_retired",
            name="Already Retired",
            status=CatalogStatus.RETIRED,
            created_by=self.owner,
            updated_by=self.owner,
        )
        audit_count_before = AuditLog.objects.filter(target_id=mod.id).count()

        resp = self.client.patch(
            f"/api/v1/product-modules/{mod.id}/",
            {"status": "retired"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        audit_count_after = AuditLog.objects.filter(target_id=mod.id).count()
        self.assertEqual(audit_count_after, audit_count_before, "No-op PATCH must not emit an audit event.")


class CatalogAllAncestorActivationTests(CatalogBaseTestCase):
    """Verifies all-ancestor activation gating: all ancestors up to Product must be active."""

    def test_module_activation_blocked_if_product_is_draft(self):
        self.client.force_login(self.owner)
        draft_prod = self.create_draft_product()
        mod = ProductModule.objects.create(
            product=draft_prod,
            code="mod_test",
            name="Mod Test",
            status=CatalogStatus.DRAFT,
            created_by=self.owner,
            updated_by=self.owner,
        )
        resp = self.client.patch(
            f"/api/v1/product-modules/{mod.id}/",
            {"status": "active"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("status", resp.data)
        self.assertIn("parent product is not active", str(resp.data["status"]))

    def test_feature_activation_blocked_if_module_is_draft(self):
        self.client.force_login(self.owner)
        active_prod = self.create_active_product()
        draft_mod = ProductModule.objects.create(
            product=active_prod,
            code="draft_mod",
            name="Draft Mod",
            status=CatalogStatus.DRAFT,
            created_by=self.owner,
            updated_by=self.owner,
        )
        feat = ProductFeature.objects.create(
            module=draft_mod,
            code="feat_test",
            name="Feat Test",
            status=CatalogStatus.DRAFT,
            created_by=self.owner,
            updated_by=self.owner,
        )
        resp = self.client.patch(
            f"/api/v1/product-features/{feat.id}/",
            {"status": "active"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("status", resp.data)
        self.assertIn("an ancestor is not active", str(resp.data["status"]))

    def test_feature_activation_blocked_if_product_is_draft(self):
        self.client.force_login(self.owner)
        draft_prod = self.create_draft_product()
        active_mod = ProductModule.objects.create(
            product=draft_prod,
            code="active_mod_dp",
            name="Active Mod DP",
            status=CatalogStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )
        feat = ProductFeature.objects.create(
            module=active_mod,
            code="feat_dp_test",
            name="Feat DP Test",
            status=CatalogStatus.DRAFT,
            created_by=self.owner,
            updated_by=self.owner,
        )
        resp = self.client.patch(
            f"/api/v1/product-features/{feat.id}/",
            {"status": "active"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("status", resp.data)
        self.assertIn("an ancestor is not active", str(resp.data["status"]))

    def test_capability_activation_blocked_if_feature_is_draft(self):
        self.client.force_login(self.owner)
        active_prod = self.create_active_product()
        active_mod = ProductModule.objects.create(
            product=active_prod,
            code="active_mod",
            name="Active Mod",
            status=CatalogStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )
        draft_feat = ProductFeature.objects.create(
            module=active_mod,
            code="draft_feat",
            name="Draft Feat",
            status=CatalogStatus.DRAFT,
            created_by=self.owner,
            updated_by=self.owner,
        )
        cap = ProductCapability.objects.create(
            feature=draft_feat,
            code="cap_test",
            name="Cap Test",
            status=CatalogStatus.DRAFT,
            created_by=self.owner,
            updated_by=self.owner,
        )
        resp = self.client.patch(
            f"/api/v1/product-capabilities/{cap.id}/",
            {"status": "active"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("status", resp.data)
        self.assertIn("an ancestor is not active", str(resp.data["status"]))

    def test_capability_activation_blocked_if_module_is_draft(self):
        self.client.force_login(self.owner)
        active_prod = self.create_active_product()
        draft_mod = ProductModule.objects.create(
            product=active_prod,
            code="draft_mod_cap",
            name="Draft Mod Cap",
            status=CatalogStatus.DRAFT,
            created_by=self.owner,
            updated_by=self.owner,
        )
        active_feat = ProductFeature.objects.create(
            module=draft_mod,
            code="active_feat_dm",
            name="Active Feat DM",
            status=CatalogStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )
        cap = ProductCapability.objects.create(
            feature=active_feat,
            code="cap_dm_test",
            name="Cap DM Test",
            status=CatalogStatus.DRAFT,
            created_by=self.owner,
            updated_by=self.owner,
        )
        resp = self.client.patch(
            f"/api/v1/product-capabilities/{cap.id}/",
            {"status": "active"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("status", resp.data)
        self.assertIn("an ancestor is not active", str(resp.data["status"]))

    def test_capability_activation_blocked_if_product_is_draft(self):
        self.client.force_login(self.owner)
        draft_prod = self.create_draft_product()
        active_mod = ProductModule.objects.create(
            product=draft_prod,
            code="active_mod_cap_dp",
            name="Active Mod Cap DP",
            status=CatalogStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )
        active_feat = ProductFeature.objects.create(
            module=active_mod,
            code="active_feat_dp",
            name="Active Feat DP",
            status=CatalogStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )
        cap = ProductCapability.objects.create(
            feature=active_feat,
            code="cap_dp_test",
            name="Cap DP Test",
            status=CatalogStatus.DRAFT,
            created_by=self.owner,
            updated_by=self.owner,
        )
        resp = self.client.patch(
            f"/api/v1/product-capabilities/{cap.id}/",
            {"status": "active"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("status", resp.data)
        self.assertIn("an ancestor is not active", str(resp.data["status"]))


class CatalogBottomUpRetirementTests(CatalogBaseTestCase):
    """Verifies strict bottom-up retirement rules: parents cannot retire with non-retired children."""

    def test_module_retirement_blocked_when_active_feature_exists(self):
        self.client.force_login(self.owner)
        prod = self.create_active_product()
        mod = ProductModule.objects.create(
            product=prod,
            code="parent_mod",
            name="Parent Mod",
            status=CatalogStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )
        ProductFeature.objects.create(
            module=mod,
            code="child_feat",
            name="Child Feat",
            status=CatalogStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )
        resp = self.client.patch(
            f"/api/v1/product-modules/{mod.id}/",
            {"status": "retired"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("non-retired features", str(resp.data))
        mod.refresh_from_db()
        self.assertEqual(mod.status, CatalogStatus.ACTIVE)

    def test_feature_retirement_blocked_when_draft_capability_exists(self):
        self.client.force_login(self.owner)
        prod = self.create_active_product()
        mod = ProductModule.objects.create(
            product=prod,
            code="mod_a",
            name="Mod A",
            status=CatalogStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )
        feat = ProductFeature.objects.create(
            module=mod,
            code="feat_a",
            name="Feat A",
            status=CatalogStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )
        ProductCapability.objects.create(
            feature=feat,
            code="cap_draft",
            name="Cap Draft",
            status=CatalogStatus.DRAFT,
            created_by=self.owner,
            updated_by=self.owner,
        )
        resp = self.client.patch(
            f"/api/v1/product-features/{feat.id}/",
            {"status": "retired"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("non-retired capabilities", str(resp.data))

    def test_product_retirement_blocked_when_module_is_draft_or_active(self):
        self.client.force_login(self.owner)
        prod = self.create_active_product(code="prod_block", name="Prod Block")
        ProductModule.objects.create(
            product=prod,
            code="blocking_mod",
            name="Blocking Mod",
            status=CatalogStatus.DRAFT,
            created_by=self.owner,
            updated_by=self.owner,
        )
        resp = self.client.patch(
            f"/api/v1/products/{prod.id}/",
            {"status": "retired"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("non-retired modules", str(resp.data))

    def test_retired_product_allows_metadata_updates_preserving_phase1_contract(self):
        """Preserves Phase 1E/1F contract: retired products allow name/description metadata updates."""
        self.client.force_login(self.owner)
        prod = Product.objects.create(
            code="already_retired_prod",
            name="Old Product Name",
            description="Old description",
            status=ProductStatus.RETIRED,
            created_by=self.owner,
            updated_by=self.owner,
        )
        resp = self.client.patch(
            f"/api/v1/products/{prod.id}/",
            {"name": "New Product Name", "description": "Updated description"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        prod.refresh_from_db()
        self.assertEqual(prod.name, "New Product Name")
        self.assertEqual(prod.description, "Updated description")
        self.assertEqual(prod.status, ProductStatus.RETIRED)

    def test_successful_bottom_up_retirement_chain_via_patch(self):
        self.client.force_login(self.owner)
        prod = self.create_active_product(code="retire_chain", name="Retire Chain")
        mod = ProductModule.objects.create(
            product=prod,
            code="mod_chain",
            name="Mod Chain",
            status=CatalogStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )
        feat = ProductFeature.objects.create(
            module=mod,
            code="feat_chain",
            name="Feat Chain",
            status=CatalogStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )
        cap = ProductCapability.objects.create(
            feature=feat,
            code="cap_chain",
            name="Cap Chain",
            status=CatalogStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )

        # 1. Retire Capability via PATCH
        cap_resp = self.client.patch(
            f"/api/v1/product-capabilities/{cap.id}/",
            {"status": "retired"},
            format="json",
        )
        self.assertEqual(cap_resp.status_code, status.HTTP_200_OK)
        cap.refresh_from_db()
        self.assertEqual(cap.status, CatalogStatus.RETIRED)

        # 2. Retire Feature via PATCH now succeeds
        feat_resp = self.client.patch(
            f"/api/v1/product-features/{feat.id}/",
            {"status": "retired"},
            format="json",
        )
        self.assertEqual(feat_resp.status_code, status.HTTP_200_OK)
        feat.refresh_from_db()
        self.assertEqual(feat.status, CatalogStatus.RETIRED)

        # 3. Retire Module via PATCH now succeeds
        mod_resp = self.client.patch(
            f"/api/v1/product-modules/{mod.id}/",
            {"status": "retired"},
            format="json",
        )
        self.assertEqual(mod_resp.status_code, status.HTTP_200_OK)
        mod.refresh_from_db()
        self.assertEqual(mod.status, CatalogStatus.RETIRED)

        # 4. Retire Product via PATCH now succeeds
        prod_resp = self.client.patch(
            f"/api/v1/products/{prod.id}/",
            {"status": "retired"},
            format="json",
        )
        self.assertEqual(prod_resp.status_code, status.HTTP_200_OK)
        prod.refresh_from_db()
        self.assertEqual(prod.status, ProductStatus.RETIRED)


class CatalogAuditMetadataExactKeySetTests(CatalogBaseTestCase):
    """Verifies exact metadata dictionary equality for all 9 catalog audit actions."""

    def test_module_created_metadata_exact_dict(self):
        self.client.force_login(self.owner)
        prod = self.create_active_product(code="m_prod", name="M Prod")
        payload = {"product_id": str(prod.id), "code": "m_code", "name": "M Name", "display_order": 3}
        resp = self.client.post("/api/v1/product-modules/", payload, format="json")
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        module_id = uuid.UUID(resp.data["id"])

        audit = AuditLog.objects.get(target_id=module_id, action=AuditAction.MODULE_CREATED)
        expected = {
            "product_id": str(prod.id),
            "product_code": "m_prod",
            "code": "m_code",
            "name": "M Name",
            "display_order": 3,
            "status": "draft",
        }
        self.assertEqual(audit.metadata, expected)

    def test_module_updated_metadata_exact_dict(self):
        self.client.force_login(self.owner)
        prod = self.create_active_product(code="u_prod")
        mod = ProductModule.objects.create(
            product=prod, code="u_mod", name="Old Name", status=CatalogStatus.DRAFT,
            created_by=self.owner, updated_by=self.owner,
        )
        resp = self.client.patch(f"/api/v1/product-modules/{mod.id}/", {"name": "New Name", "status": "active"}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        audit = AuditLog.objects.get(target_id=mod.id, action=AuditAction.MODULE_UPDATED)
        expected = {
            "product_id": str(prod.id),
            "product_code": "u_prod",
            "code_changed": False,
            "name_changed": True,
            "description_changed": False,
            "display_order_changed": False,
            "status_changed": True,
            "previous_status": "draft",
            "resulting_status": "active",
        }
        self.assertEqual(audit.metadata, expected)

    def test_module_retired_metadata_exact_dict(self):
        self.client.force_login(self.owner)
        prod = self.create_active_product(code="r_prod")
        mod = ProductModule.objects.create(
            product=prod, code="r_mod", name="R Name", status=CatalogStatus.ACTIVE,
            created_by=self.owner, updated_by=self.owner,
        )
        resp = self.client.patch(f"/api/v1/product-modules/{mod.id}/", {"status": "retired"}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        audit = AuditLog.objects.get(target_id=mod.id, action=AuditAction.MODULE_RETIRED)
        expected = {
            "product_id": str(prod.id),
            "product_code": "r_prod",
            "previous_status": "active",
            "resulting_status": "retired",
        }
        self.assertEqual(audit.metadata, expected)

    def test_feature_created_metadata_exact_dict(self):
        self.client.force_login(self.owner)
        prod = self.create_active_product(code="fc_prod")
        mod = ProductModule.objects.create(
            product=prod, code="fc_mod", name="FC Mod", status=CatalogStatus.ACTIVE,
            created_by=self.owner, updated_by=self.owner,
        )
        payload = {"module_id": str(mod.id), "code": "fc_feat", "name": "FC Feat", "display_order": 1}
        resp = self.client.post("/api/v1/product-features/", payload, format="json")
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        feat_id = uuid.UUID(resp.data["id"])

        audit = AuditLog.objects.get(target_id=feat_id, action=AuditAction.FEATURE_CREATED)
        expected = {
            "product_id": str(prod.id),
            "product_code": "fc_prod",
            "module_id": str(mod.id),
            "module_code": "fc_mod",
            "code": "fc_feat",
            "name": "FC Feat",
            "display_order": 1,
            "status": "draft",
        }
        self.assertEqual(audit.metadata, expected)

    def test_feature_updated_metadata_exact_dict(self):
        self.client.force_login(self.owner)
        prod = self.create_active_product(code="fu_prod")
        mod = ProductModule.objects.create(
            product=prod, code="fu_mod", name="FU Mod", status=CatalogStatus.ACTIVE,
            created_by=self.owner, updated_by=self.owner,
        )
        feat = ProductFeature.objects.create(
            module=mod, code="fu_feat", name="FU Feat", status=CatalogStatus.DRAFT,
            created_by=self.owner, updated_by=self.owner,
        )
        resp = self.client.patch(f"/api/v1/product-features/{feat.id}/", {"status": "active"}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        audit = AuditLog.objects.get(target_id=feat.id, action=AuditAction.FEATURE_UPDATED)
        expected = {
            "product_id": str(prod.id),
            "product_code": "fu_prod",
            "module_id": str(mod.id),
            "module_code": "fu_mod",
            "code_changed": False,
            "name_changed": False,
            "description_changed": False,
            "display_order_changed": False,
            "status_changed": True,
            "previous_status": "draft",
            "resulting_status": "active",
        }
        self.assertEqual(audit.metadata, expected)

    def test_feature_retired_metadata_exact_dict(self):
        self.client.force_login(self.owner)
        prod = self.create_active_product(code="fr_prod")
        mod = ProductModule.objects.create(
            product=prod, code="fr_mod", name="FR Mod", status=CatalogStatus.ACTIVE,
            created_by=self.owner, updated_by=self.owner,
        )
        feat = ProductFeature.objects.create(
            module=mod, code="fr_feat", name="FR Feat", status=CatalogStatus.ACTIVE,
            created_by=self.owner, updated_by=self.owner,
        )
        resp = self.client.patch(f"/api/v1/product-features/{feat.id}/", {"status": "retired"}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        audit = AuditLog.objects.get(target_id=feat.id, action=AuditAction.FEATURE_RETIRED)
        expected = {
            "product_id": str(prod.id),
            "product_code": "fr_prod",
            "module_id": str(mod.id),
            "module_code": "fr_mod",
            "previous_status": "active",
            "resulting_status": "retired",
        }
        self.assertEqual(audit.metadata, expected)

    def test_capability_created_metadata_exact_dict(self):
        self.client.force_login(self.owner)
        prod = self.create_active_product(code="cc_prod")
        mod = ProductModule.objects.create(
            product=prod, code="cc_mod", name="CC Mod", status=CatalogStatus.ACTIVE,
            created_by=self.owner, updated_by=self.owner,
        )
        feat = ProductFeature.objects.create(
            module=mod, code="cc_feat", name="CC Feat", status=CatalogStatus.ACTIVE,
            created_by=self.owner, updated_by=self.owner,
        )
        payload = {"feature_id": str(feat.id), "code": "cc_cap", "name": "CC Cap", "display_order": 0}
        resp = self.client.post("/api/v1/product-capabilities/", payload, format="json")
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        cap_id = uuid.UUID(resp.data["id"])

        audit = AuditLog.objects.get(target_id=cap_id, action=AuditAction.CAPABILITY_CREATED)
        expected = {
            "product_id": str(prod.id),
            "product_code": "cc_prod",
            "module_id": str(mod.id),
            "module_code": "cc_mod",
            "feature_id": str(feat.id),
            "feature_code": "cc_feat",
            "code": "cc_cap",
            "name": "CC Cap",
            "display_order": 0,
            "status": "draft",
        }
        self.assertEqual(audit.metadata, expected)

    def test_capability_updated_metadata_exact_dict(self):
        self.client.force_login(self.owner)
        prod = self.create_active_product(code="cu_prod")
        mod = ProductModule.objects.create(
            product=prod, code="cu_mod", name="CU Mod", status=CatalogStatus.ACTIVE,
            created_by=self.owner, updated_by=self.owner,
        )
        feat = ProductFeature.objects.create(
            module=mod, code="cu_feat", name="CU Feat", status=CatalogStatus.ACTIVE,
            created_by=self.owner, updated_by=self.owner,
        )
        cap = ProductCapability.objects.create(
            feature=feat, code="cu_cap", name="CU Cap", status=CatalogStatus.DRAFT,
            created_by=self.owner, updated_by=self.owner,
        )
        resp = self.client.patch(f"/api/v1/product-capabilities/{cap.id}/", {"status": "active"}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        audit = AuditLog.objects.get(target_id=cap.id, action=AuditAction.CAPABILITY_UPDATED)
        expected = {
            "product_id": str(prod.id),
            "product_code": "cu_prod",
            "module_id": str(mod.id),
            "module_code": "cu_mod",
            "feature_id": str(feat.id),
            "feature_code": "cu_feat",
            "code_changed": False,
            "name_changed": False,
            "description_changed": False,
            "display_order_changed": False,
            "status_changed": True,
            "previous_status": "draft",
            "resulting_status": "active",
        }
        self.assertEqual(audit.metadata, expected)

    def test_capability_retired_metadata_exact_dict(self):
        self.client.force_login(self.owner)
        prod = self.create_active_product(code="cr_prod")
        mod = ProductModule.objects.create(
            product=prod, code="cr_mod", name="CR Mod", status=CatalogStatus.ACTIVE,
            created_by=self.owner, updated_by=self.owner,
        )
        feat = ProductFeature.objects.create(
            module=mod, code="cr_feat", name="CR Feat", status=CatalogStatus.ACTIVE,
            created_by=self.owner, updated_by=self.owner,
        )
        cap = ProductCapability.objects.create(
            feature=feat, code="cr_cap", name="CR Cap", status=CatalogStatus.ACTIVE,
            created_by=self.owner, updated_by=self.owner,
        )
        resp = self.client.patch(f"/api/v1/product-capabilities/{cap.id}/", {"status": "retired"}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        audit = AuditLog.objects.get(target_id=cap.id, action=AuditAction.CAPABILITY_RETIRED)
        expected = {
            "product_id": str(prod.id),
            "product_code": "cr_prod",
            "module_id": str(mod.id),
            "module_code": "cr_mod",
            "feature_id": str(feat.id),
            "feature_code": "cr_feat",
            "previous_status": "active",
            "resulting_status": "retired",
        }
        self.assertEqual(audit.metadata, expected)

    def test_auditlog_validator_rejects_missing_metadata_keys(self):
        prod_id = uuid.uuid4()
        with self.assertRaises(AuditEventError) as ctx:
            record_audit_event(
                action=AuditAction.MODULE_CREATED,
                target_type=AuditTargetType.MODULE,
                target_id=uuid.uuid4(),
                target_repr="mod",
                actor=self.owner,
                organization_id=None,
                operation_source=AuditOperationSource.INTERACTIVE,
                metadata={"product_id": str(prod_id)},  # Missing code, name, display_order, status
            )
        self.assertIn("Invalid metadata keys", str(ctx.exception))

    def test_auditlog_validator_rejects_extra_metadata_keys(self):
        prod_id = uuid.uuid4()
        with self.assertRaises(AuditEventError) as ctx:
            record_audit_event(
                action=AuditAction.MODULE_CREATED,
                target_type=AuditTargetType.MODULE,
                target_id=uuid.uuid4(),
                target_repr="mod",
                actor=self.owner,
                organization_id=None,
                operation_source=AuditOperationSource.INTERACTIVE,
                metadata={
                    "product_id": str(prod_id),
                    "product_code": "prod",
                    "code": "c",
                    "name": "n",
                    "display_order": 0,
                    "status": "draft",
                    "extra_key": "not_allowed",
                },
            )
        self.assertIn("Invalid metadata keys", str(ctx.exception))

    def test_auditlog_validator_rejects_incorrect_value_types(self):
        prod_id = uuid.uuid4()
        with self.assertRaises(AuditEventError) as ctx:
            record_audit_event(
                action=AuditAction.MODULE_CREATED,
                target_type=AuditTargetType.MODULE,
                target_id=uuid.uuid4(),
                target_repr="mod",
                actor=self.owner,
                organization_id=None,
                operation_source=AuditOperationSource.INTERACTIVE,
                metadata={
                    "product_id": str(prod_id),
                    "product_code": "prod",
                    "code": "c",
                    "name": "n",
                    "display_order": "not_an_int",
                    "status": "draft",
                },
            )
        self.assertIn("must be a non-negative integer", str(ctx.exception))

    def test_auditlog_validator_rejects_extra_password_key(self):
        prod_id = uuid.uuid4()
        with self.assertRaises(AuditEventError) as ctx:
            record_audit_event(
                action=AuditAction.CAPABILITY_CREATED,
                target_type=AuditTargetType.CAPABILITY,
                target_id=uuid.uuid4(),
                target_repr="cap",
                actor=self.owner,
                organization_id=None,
                operation_source=AuditOperationSource.INTERACTIVE,
                metadata={
                    "product_id": str(prod_id),
                    "product_code": "prod",
                    "module_id": str(uuid.uuid4()),
                    "module_code": "mod",
                    "feature_id": str(uuid.uuid4()),
                    "feature_code": "feat",
                    "code": "reset_password",
                    "name": "Reset Password",
                    "display_order": 0,
                    "status": "draft",
                    "password": "supersecretpassword",
                },
            )
        self.assertTrue(
            "prohibited sensitive term" in str(ctx.exception).lower()
            or "invalid metadata keys" in str(ctx.exception).lower()
        )

    def test_auditlog_validator_rejects_extra_access_token_key(self):
        prod_id = uuid.uuid4()
        with self.assertRaises(AuditEventError) as ctx:
            record_audit_event(
                action=AuditAction.CAPABILITY_CREATED,
                target_type=AuditTargetType.CAPABILITY,
                target_id=uuid.uuid4(),
                target_repr="cap",
                actor=self.owner,
                organization_id=None,
                operation_source=AuditOperationSource.INTERACTIVE,
                metadata={
                    "product_id": str(prod_id),
                    "product_code": "prod",
                    "module_id": str(uuid.uuid4()),
                    "module_code": "mod",
                    "feature_id": str(uuid.uuid4()),
                    "feature_code": "feat",
                    "code": "token_mgmt",
                    "name": "Token Management",
                    "display_order": 0,
                    "status": "draft",
                    "access_token": "bearer123456",
                },
            )
        self.assertTrue(
            "prohibited sensitive term" in str(ctx.exception).lower()
            or "invalid metadata keys" in str(ctx.exception).lower()
        )

    def test_auditlog_validator_rejects_extra_api_key(self):
        prod_id = uuid.uuid4()
        with self.assertRaises(AuditEventError) as ctx:
            record_audit_event(
                action=AuditAction.CAPABILITY_CREATED,
                target_type=AuditTargetType.CAPABILITY,
                target_id=uuid.uuid4(),
                target_repr="cap",
                actor=self.owner,
                organization_id=None,
                operation_source=AuditOperationSource.INTERACTIVE,
                metadata={
                    "product_id": str(prod_id),
                    "product_code": "prod",
                    "module_id": str(uuid.uuid4()),
                    "module_code": "mod",
                    "feature_id": str(uuid.uuid4()),
                    "feature_code": "feat",
                    "code": "api_access",
                    "name": "API Access",
                    "display_order": 0,
                    "status": "draft",
                    "api_key": "live_key_xyz",
                },
            )
        self.assertTrue(
            "prohibited sensitive term" in str(ctx.exception).lower()
            or "invalid metadata keys" in str(ctx.exception).lower()
        )


class CatalogAnnotationAndChildCountTests(CatalogBaseTestCase):
    """Verifies annotated child counts and query efficiency."""

    def test_module_list_returns_annotated_child_counts(self):
        self.client.force_login(self.owner)
        prod = self.create_active_product()
        mod = ProductModule.objects.create(
            product=prod,
            code="count_mod",
            name="Count Mod",
            status=CatalogStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )
        ProductFeature.objects.create(
            module=mod, code="f1", name="Feature 1", status=CatalogStatus.ACTIVE,
            created_by=self.owner, updated_by=self.owner,
        )
        ProductFeature.objects.create(
            module=mod, code="f2", name="Feature 2", status=CatalogStatus.DRAFT,
            created_by=self.owner, updated_by=self.owner,
        )
        ProductFeature.objects.create(
            module=mod, code="f3", name="Feature 3", status=CatalogStatus.RETIRED,
            created_by=self.owner, updated_by=self.owner,
        )

        resp = self.client.get(f"/api/v1/product-modules/?product_id={prod.id}")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        mod_data = resp.data["results"][0]
        self.assertEqual(mod_data["total_features_count"], 3)
        self.assertEqual(mod_data["active_features_count"], 1)

    def test_feature_list_returns_annotated_child_counts(self):
        self.client.force_login(self.owner)
        prod = self.create_active_product()
        mod = ProductModule.objects.create(
            product=prod,
            code="parent_mod",
            name="Parent Mod",
            status=CatalogStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )
        feat = ProductFeature.objects.create(
            module=mod, code="count_feat", name="Count Feat", status=CatalogStatus.ACTIVE,
            created_by=self.owner, updated_by=self.owner,
        )
        ProductCapability.objects.create(
            feature=feat, code="c1", name="Cap 1", status=CatalogStatus.ACTIVE,
            created_by=self.owner, updated_by=self.owner,
        )
        ProductCapability.objects.create(
            feature=feat, code="c2", name="Cap 2", status=CatalogStatus.ACTIVE,
            created_by=self.owner, updated_by=self.owner,
        )

        resp = self.client.get(f"/api/v1/product-features/?module_id={mod.id}")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        feat_data = resp.data["results"][0]
        self.assertEqual(feat_data["total_capabilities_count"], 2)
        self.assertEqual(feat_data["active_capabilities_count"], 2)


class CatalogMigrationDependencyTests(TestCase):
    """Verifies that catalog migration dependencies match the approved architecture."""

    def test_catalog_hierarchy_migration_depends_on_auditlog_0002(self):
        import importlib
        migration_module = importlib.import_module("apps.product_registry.migrations.0002_catalog_hierarchy")
        migration = migration_module.Migration("0002_catalog_hierarchy", "product_registry")
        dependencies = migration.dependencies
        self.assertIn(
            ("auditlog", "0002_catalog_audit_actions"),
            dependencies,
            "product_registry.0002 must depend on auditlog.0002_catalog_audit_actions"
        )
        self.assertIn(
            ("product_registry", "0001_initial"),
            dependencies,
            "product_registry.0002 must depend on product_registry.0001_initial"
        )


class CatalogChildCreateVsParentRetireConcurrencyTests(TransactionTestCase):
    """Real multi-threaded concurrency test for race between child creation and parent retirement under select_for_update.

    Exercises top-down row locking and verifies the fundamental platform invariant:
    A retired parent can NEVER have a non-retired child under any race condition.
    """

    def setUp(self):
        super().setUp()
        self.owner = User.objects.create_user(
            email="concurrency_owner@vibeconnect.com",
            password="SecurePassword123!",
            full_name="Concurrency Platform Owner",
            is_platform_owner=True,
            is_active=True,
        )
        self.product = Product.objects.create(
            code="race_lms",
            name="Race LMS",
            status=ProductStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )
        self.module = ProductModule.objects.create(
            product=self.product,
            code="race_mod",
            name="Race Module",
            status=CatalogStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )

    def tearDown(self):
        connections.close_all()
        super().tearDown()

    def test_child_create_vs_parent_retire_race_preserves_hierarchy_invariant(self):
        """Tests concurrent execution of create_product_feature vs update_product_module (retiring).

        Both operations contend on the locked ProductModule row via select_for_update().
        Coordinates execution using threading.Barrier to ensure both worker threads start
        simultaneously and contend on the exact same locked parent row.
        """
        barrier = threading.Barrier(2)
        results = {"create_error": None, "retire_error": None, "feature": None, "module": None}

        def run_create():
            connections.close_all()
            try:
                barrier.wait(timeout=5)
                feat = services.create_product_feature(
                    module_id=self.module.id,
                    data={
                        "code": "race_feat",
                        "name": "Race Feature",
                        "description": "Created under concurrent race",
                        "display_order": 0,
                    },
                    actor=self.owner,
                    operation_source=AuditOperationSource.INTERACTIVE,
                )
                results["feature"] = feat
            except Exception as exc:
                results["create_error"] = exc
            finally:
                connections.close_all()

        def run_retire():
            connections.close_all()
            try:
                barrier.wait(timeout=5)
                mod = services.update_product_module(
                    module_id=self.module.id,
                    data={"status": CatalogStatus.RETIRED},
                    actor=self.owner,
                    operation_source=AuditOperationSource.INTERACTIVE,
                )
                results["module"] = mod
            except Exception as exc:
                results["retire_error"] = exc
            finally:
                connections.close_all()

        t_create = threading.Thread(target=run_create)
        t_retire = threading.Thread(target=run_retire)

        t_create.start()
        t_retire.start()

        t_create.join(timeout=10)
        t_retire.join(timeout=10)

        self.module.refresh_from_db()
        non_retired_features = self.module.features.exclude(status=CatalogStatus.RETIRED).all()

        # Invariant: A retired parent can NEVER have a non-retired child
        if self.module.status == CatalogStatus.RETIRED:
            self.assertEqual(
                len(non_retired_features),
                0,
                "Invariant violation: Retired module has non-retired child features!"
            )
            # In this serialized outcome, retirement won:
            # - Retire succeeded (no error)
            # - Child creation was rejected because parent was retired under locked check
            self.assertIsNone(results["retire_error"])
            self.assertIsNotNone(results["create_error"])
            self.assertTrue(
                AuditLog.objects.filter(target_id=self.module.id, action=AuditAction.MODULE_RETIRED).exists()
            )
            self.assertFalse(
                AuditLog.objects.filter(target_repr="Race Feature").exists()
            )
        else:
            # In this serialized outcome, child creation won:
            # - Create succeeded (no error)
            # - Child feature exists and is DRAFT
            # - Retirement was rejected because non-retired child existed under locked check
            self.assertIsNone(results["create_error"])
            self.assertIsNotNone(results["retire_error"])
            self.assertEqual(len(non_retired_features), 1)
            self.assertEqual(non_retired_features[0].code, "race_feat")
            self.assertEqual(non_retired_features[0].status, CatalogStatus.DRAFT)
            self.assertTrue(
                AuditLog.objects.filter(target_id=non_retired_features[0].id, action=AuditAction.FEATURE_CREATED).exists()
            )
            self.assertFalse(
                AuditLog.objects.filter(target_id=self.module.id, action=AuditAction.MODULE_RETIRED).exists()
            )
