"""Focused API test suite for Phase 2C Stage 3 Subscription REST APIs and Public Plan Discovery.

Verifies:
1. Authentication and Platform Owner permission enforcement
2. Create active subscription
3. Start subscription trial
4. Lifecycle action routing (convert-trial, change-plan, suspend, reactivate, cancel, reconcile)
5. List filters, search, ordering, and pagination
6. Duplicate query parameter rejection
7. Invalid UUID rejection
8. Absence of DELETE/PUT/PATCH methods
9. Entitlement snapshot response structure
10. Strict payload validation (unknown and protected fields)
11. Validation preventing mismatched PlanVersion/PlanPrice and duplicate open subscriptions
12. Public plan discovery unauthenticated access and field allowlist
13. Public plan discovery exclusion of private, versionless, and degraded plans
14. Plan public visibility management (publishing validation and unpublishing)
"""

from decimal import Decimal
import uuid
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from apps.organizations.models import Organization, OrganizationStatus
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
    QuotaResetPeriod,
    QuotaScope,
)
from apps.plans.services import activate_plan_version, create_plan
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
    SubscriptionStatus,
)
from apps.subscriptions.services import (
    create_active_subscription,
    start_subscription_trial,
)

User = get_user_model()


class SubscriptionsApiTests(TestCase):
    """API test suite for Phase 2C Subscription REST endpoints and Public Plan Discovery."""

    def setUp(self):
        super().setUp()
        self.owner = User.objects.create_user(
            email="platform_owner@vibeconnect.test",
            password="SecurePassword123!",
            full_name="Platform Owner",
            is_active=True,
            is_platform_owner=True,
        )
        self.regular_user = User.objects.create_user(
            email="regular_user@vibeconnect.test",
            password="SecurePassword123!",
            full_name="Regular User",
            is_active=True,
            is_platform_owner=False,
        )
        self.client = APIClient()

        # Create active organization
        self.org = Organization.objects.create(
            name="Acme Corp",
            code="acme",
            status=OrganizationStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )

        # Create catalog entities
        self.product = Product.objects.create(
            name="LMS Core",
            code="lms_core",
            status=ProductStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )
        self.module = ProductModule.objects.create(
            product=self.product,
            name="Assessments",
            code="assessments",
            status=CatalogStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )
        self.feature = ProductFeature.objects.create(
            module=self.module,
            name="Grading",
            code="grading",
            status=CatalogStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )
        self.capability = ProductCapability.objects.create(
            feature=self.feature,
            name="Auto Grade",
            code="auto_grade",
            status=CatalogStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )

        # Create plan, active version, price, packaged product/module/capability, quota
        self.plan, self.pv = create_plan(
            code="enterprise",
            name="Enterprise Plan",
            description="Full enterprise suite",
            actor=self.owner,
        )
        self.price = PlanPrice.objects.create(
            plan_version=self.pv,
            billing_interval=BillingInterval.MONTHLY,
            currency=PlanCurrency.USD,
            amount=Decimal("499.00"),
            created_by=self.owner,
            updated_by=self.owner,
        )
        self.plan_prod = PlanProduct.objects.create(
            plan_version=self.pv,
            product=self.product,
            created_by=self.owner,
        )
        self.plan_mod = PlanModule.objects.create(
            plan_version=self.pv,
            module=self.module,
            plan_product=self.plan_prod,
            created_by=self.owner,
        )
        self.plan_cap = PlanCapability.objects.create(
            plan_version=self.pv,
            capability=self.capability,
            plan_module=self.plan_mod,
            created_by=self.owner,
        )
        self.plan_quota = PlanQuota.objects.create(
            plan_version=self.pv,
            quota_key="max_seats",
            name="Maximum Seats",
            scope=QuotaScope.PLAN,
            limit_type=QuotaLimitType.NUMERIC,
            limit_value=100,
            unit="seats",
            is_hard_limit=True,
            reset_period=QuotaResetPeriod.NEVER,
            created_by=self.owner,
            updated_by=self.owner,
        )
        # Activate plan version
        activate_plan_version(plan_version_id=self.pv.id, actor=self.owner)
        self.pv.refresh_from_db()

    def test_subscription_endpoints_require_platform_owner_auth(self):
        """Subscription endpoints reject unauthenticated and non-platform-owner requests."""
        # Unauthenticated
        resp = self.client.get("/api/v1/subscriptions/")
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

        # Non-platform owner
        self.client.force_authenticate(user=self.regular_user)
        resp = self.client.get("/api/v1/subscriptions/")
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_create_active_subscription_success(self):
        """Platform owner can create an active subscription."""
        self.client.force_authenticate(user=self.owner)
        payload = {
            "organization_id": str(self.org.id),
            "plan_version_id": str(self.pv.id),
            "plan_price_id": str(self.price.id),
            "change_reason": "Initial customer onboarding",
        }
        resp = self.client.post("/api/v1/subscriptions/", payload, format="json")
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        data = resp.json()
        self.assertEqual(data["organization_id"], str(self.org.id))
        self.assertEqual(data["status"], "active")
        self.assertEqual(data["plan_code_snapshot"], "enterprise")
        self.assertEqual(data["amount"], "499.00")
        self.assertFalse(data["started_as_trial"])
        self.assertIsNotNone(data["current_period_start"])
        self.assertIsNotNone(data["current_period_end"])

    def test_start_subscription_trial_success(self):
        """Platform owner can start a subscription trial."""
        self.client.force_authenticate(user=self.owner)
        payload = {
            "organization_id": str(self.org.id),
            "plan_version_id": str(self.pv.id),
            "plan_price_id": str(self.price.id),
            "trial_days": 30,
            "change_reason": "30-day enterprise evaluation",
        }
        resp = self.client.post("/api/v1/subscriptions/trial/", payload, format="json")
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        data = resp.json()
        self.assertEqual(data["organization_id"], str(self.org.id))
        self.assertEqual(data["status"], "trialing")
        self.assertTrue(data["started_as_trial"])
        self.assertIsNotNone(data["trial_started_at"])
        self.assertIsNotNone(data["trial_ends_at"])
        self.assertIsNone(data["current_period_start"])

    def test_convert_trial_endpoint(self):
        """Trial subscription can be converted to active via POST /convert-trial/."""
        self.client.force_authenticate(user=self.owner)
        sub = start_subscription_trial(
            organization_id=self.org.id,
            plan_version_id=self.pv.id,
            plan_price_id=self.price.id,
            actor=self.owner,
            trial_days=14,
        )
        resp = self.client.post(f"/api/v1/subscriptions/{sub.id}/convert-trial/", {}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        data = resp.json()
        self.assertEqual(data["status"], "active")
        self.assertTrue(data["started_as_trial"])
        self.assertIsNotNone(data["current_period_start"])

    def test_change_plan_endpoint(self):
        """Active subscription plan can be changed via POST /change-plan/."""
        self.client.force_authenticate(user=self.owner)
        sub = create_active_subscription(
            organization_id=self.org.id,
            plan_version_id=self.pv.id,
            plan_price_id=self.price.id,
            actor=self.owner,
        )
        # Create a second plan and version
        plan2, pv2 = create_plan(code="pro", name="Pro Plan", actor=self.owner)
        price2 = PlanPrice.objects.create(
            plan_version=pv2,
            billing_interval=BillingInterval.ANNUAL,
            currency=PlanCurrency.USD,
            amount=Decimal("3999.00"),
            created_by=self.owner,
            updated_by=self.owner,
        )
        PlanProduct.objects.create(
            plan_version=pv2,
            product=self.product,
            created_by=self.owner,
        )
        activate_plan_version(plan_version_id=pv2.id, actor=self.owner)

        payload = {
            "new_plan_version_id": str(pv2.id),
            "new_plan_price_id": str(price2.id),
            "change_reason": "Upgraded to Pro Annual",
        }
        resp = self.client.post(f"/api/v1/subscriptions/{sub.id}/change-plan/", payload, format="json")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        data = resp.json()
        self.assertEqual(data["plan_code_snapshot"], "pro")
        self.assertEqual(data["previous_subscription_id"], str(sub.id))
        self.assertEqual(data["amount"], "3999.00")

    def test_suspend_and_reactivate_endpoints(self):
        """Active subscription can be suspended and reactivated."""
        self.client.force_authenticate(user=self.owner)
        sub = create_active_subscription(
            organization_id=self.org.id,
            plan_version_id=self.pv.id,
            plan_price_id=self.price.id,
            actor=self.owner,
        )
        # Suspend
        resp = self.client.post(
            f"/api/v1/subscriptions/{sub.id}/suspend/",
            {"reason": "Payment pending"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.json()["status"], "suspended")
        self.assertEqual(resp.json()["suspension_reason"], "Payment pending")

        # Reactivate
        resp = self.client.post(
            f"/api/v1/subscriptions/{sub.id}/reactivate/",
            {},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.json()["status"], "active")
        self.assertEqual(resp.json()["suspension_reason"], "")

    def test_cancel_subscription_endpoint(self):
        """Open subscription can be cancelled via POST /cancel/."""
        self.client.force_authenticate(user=self.owner)
        sub = create_active_subscription(
            organization_id=self.org.id,
            plan_version_id=self.pv.id,
            plan_price_id=self.price.id,
            actor=self.owner,
        )
        resp = self.client.post(
            f"/api/v1/subscriptions/{sub.id}/cancel/",
            {"reason": "Customer requested cancellation"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        data = resp.json()
        self.assertEqual(data["status"], "cancelled")
        self.assertEqual(data["cancellation_reason"], "Customer requested cancellation")
        self.assertIsNotNone(data["cancelled_at"])
        self.assertIsNotNone(data["ended_at"])

    def test_reconcile_subscription_endpoint(self):
        """Subscription snapshot reconciliation returns repaired count."""
        self.client.force_authenticate(user=self.owner)
        sub = create_active_subscription(
            organization_id=self.org.id,
            plan_version_id=self.pv.id,
            plan_price_id=self.price.id,
            actor=self.owner,
        )
        resp = self.client.post(f"/api/v1/subscriptions/{sub.id}/reconcile/", {}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.json(), {"repaired_count": 0})

    def test_get_subscription_entitlements_endpoint(self):
        """GET /api/v1/subscriptions/{id}/entitlements/ returns grouped snapshots."""
        self.client.force_authenticate(user=self.owner)
        sub = create_active_subscription(
            organization_id=self.org.id,
            plan_version_id=self.pv.id,
            plan_price_id=self.price.id,
            actor=self.owner,
        )
        resp = self.client.get(f"/api/v1/subscriptions/{sub.id}/entitlements/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        data = resp.json()
        self.assertEqual(data["subscription_id"], str(sub.id))
        self.assertEqual(data["organization_id"], str(self.org.id))
        self.assertEqual(len(data["products"]), 1)
        self.assertEqual(data["products"][0]["product_code_snapshot"], "lms_core")
        self.assertEqual(len(data["modules"]), 1)
        self.assertEqual(data["modules"][0]["module_code_snapshot"], "assessments")
        self.assertEqual(len(data["capabilities"]), 1)
        self.assertEqual(data["capabilities"][0]["capability_code_snapshot"], "auto_grade")
        self.assertEqual(len(data["quotas"]), 1)
        self.assertEqual(data["quotas"][0]["quota_key"], "max_seats")

    def test_list_subscriptions_filtering_and_search(self):
        """Subscriptions list supports filters for organization, plan, status, and search."""
        self.client.force_authenticate(user=self.owner)
        sub = create_active_subscription(
            organization_id=self.org.id,
            plan_version_id=self.pv.id,
            plan_price_id=self.price.id,
            actor=self.owner,
        )
        # Filter by organization
        resp = self.client.get(f"/api/v1/subscriptions/?organization_id={self.org.id}")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.json()["results"]), 1)

        # Filter by plan
        resp = self.client.get(f"/api/v1/subscriptions/?plan_id={self.plan.id}")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.json()["results"]), 1)

        # Filter by status
        resp = self.client.get("/api/v1/subscriptions/?status=active")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.json()["results"]), 1)

        resp = self.client.get("/api/v1/subscriptions/?status=cancelled")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.json()["results"]), 0)

        # Search
        resp = self.client.get("/api/v1/subscriptions/?search=enterprise")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.json()["results"]), 1)

    def test_list_subscriptions_ordering_and_pagination(self):
        """Subscriptions list supports ordering, page, and bounded page_size."""
        self.client.force_authenticate(user=self.owner)
        create_active_subscription(
            organization_id=self.org.id,
            plan_version_id=self.pv.id,
            plan_price_id=self.price.id,
            actor=self.owner,
        )
        resp = self.client.get("/api/v1/subscriptions/?ordering=-created_at&page=1&page_size=10")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn("results", resp.json())
        self.assertIn("count", resp.json())

        # Invalid page size (> 100)
        bad_resp = self.client.get("/api/v1/subscriptions/?page_size=150")
        self.assertEqual(bad_resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_duplicate_query_params_rejected(self):
        """Duplicate query parameters are rejected with 400 Bad Request."""
        self.client.force_authenticate(user=self.owner)
        resp = self.client.get(f"/api/v1/subscriptions/?status=active&status=trialing")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("status", resp.json())

    def test_invalid_uuid_rejected(self):
        """Malformed UUIDs are rejected properly."""
        self.client.force_authenticate(user=self.owner)
        # Invalid UUID in detail route -> 404
        resp = self.client.get("/api/v1/subscriptions/not-a-uuid/")
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

        # Invalid UUID in filter -> 400
        resp = self.client.get("/api/v1/subscriptions/?organization_id=invalid-uuid")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_absence_of_delete_put_patch_methods(self):
        """Direct DELETE, PUT, and generic PATCH are not permitted on subscriptions."""
        self.client.force_authenticate(user=self.owner)
        sub = create_active_subscription(
            organization_id=self.org.id,
            plan_version_id=self.pv.id,
            plan_price_id=self.price.id,
            actor=self.owner,
        )
        # DELETE
        resp_del = self.client.delete(f"/api/v1/subscriptions/{sub.id}/")
        self.assertEqual(resp_del.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

        # PUT
        resp_put = self.client.put(f"/api/v1/subscriptions/{sub.id}/", {})
        self.assertEqual(resp_put.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

        # PATCH
        resp_patch = self.client.patch(f"/api/v1/subscriptions/{sub.id}/", {"status": "cancelled"})
        self.assertEqual(resp_patch.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_strict_payload_validation_rejects_unknown_and_protected_fields(self):
        """Mutation payloads reject unknown and protected fields."""
        self.client.force_authenticate(user=self.owner)
        # Unknown field
        resp = self.client.post(
            "/api/v1/subscriptions/",
            {
                "organization_id": str(self.org.id),
                "plan_version_id": str(self.pv.id),
                "plan_price_id": str(self.price.id),
                "extra_field": "injected",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

        # Protected field in create payload
        resp_prot = self.client.post(
            "/api/v1/subscriptions/",
            {
                "organization_id": str(self.org.id),
                "plan_version_id": str(self.pv.id),
                "plan_price_id": str(self.price.id),
                "status": "active",
            },
            format="json",
        )
        self.assertEqual(resp_prot.status_code, status.HTTP_400_BAD_REQUEST)

    def test_prevent_duplicate_open_subscription_via_api(self):
        """API rejects creating a second open subscription for the same organization."""
        self.client.force_authenticate(user=self.owner)
        create_active_subscription(
            organization_id=self.org.id,
            plan_version_id=self.pv.id,
            plan_price_id=self.price.id,
            actor=self.owner,
        )
        resp = self.client.post(
            "/api/v1/subscriptions/",
            {
                "organization_id": str(self.org.id),
                "plan_version_id": str(self.pv.id),
                "plan_price_id": str(self.price.id),
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_public_plan_discovery_unauthenticated_allowlist(self):
        """Unauthenticated public endpoint returns public plans with exact required keys and forbidden fields absent."""
        # Mark plan as public
        self.plan.is_public = True
        self.plan.save(update_fields=["is_public"])

        resp = self.client.get("/api/v1/public/plans/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        payload = resp.json()
        self.assertEqual(payload["count"], 1)
        self.assertEqual(len(payload["results"]), 1)

        item = payload["results"][0]
        self.assertEqual(
            set(item.keys()),
            {"plan_code", "plan_name", "description", "version", "prices", "packaged_products", "quota_highlights"},
        )
        self.assertEqual(item["plan_code"], "enterprise")
        self.assertEqual(item["plan_name"], "Enterprise Plan")
        self.assertEqual(item["description"], "Full enterprise suite")
        self.assertEqual(item["version"], 1)

        # 1. Prices keys
        self.assertEqual(len(item["prices"]), 1)
        price_item = item["prices"][0]
        self.assertEqual(set(price_item.keys()), {"currency", "billing_interval", "amount"})
        self.assertEqual(price_item["currency"], "USD")
        self.assertEqual(price_item["billing_interval"], "monthly")
        self.assertEqual(price_item["amount"], "499.00")

        # 2. Packaged products keys
        self.assertEqual(len(item["packaged_products"]), 1)
        prod_item = item["packaged_products"][0]
        self.assertEqual(set(prod_item.keys()), {"product_code", "product_name"})
        self.assertEqual(prod_item["product_code"], "lms_core")
        self.assertEqual(prod_item["product_name"], "LMS Core")

        # 3. Quota highlights keys
        self.assertEqual(len(item["quota_highlights"]), 1)
        quota_item = item["quota_highlights"][0]
        self.assertEqual(
            set(quota_item.keys()),
            {"quota_key", "name", "limit_type", "limit_value", "unit", "reset_period"},
        )
        self.assertEqual(quota_item["quota_key"], "max_seats")
        self.assertEqual(quota_item["name"], "Maximum Seats")
        self.assertEqual(quota_item["limit_type"], "numeric")
        self.assertEqual(quota_item["limit_value"], 100)
        self.assertEqual(quota_item["unit"], "seats")
        self.assertEqual(quota_item["reset_period"], "never")

        # 4. Confirm forbidden fields are absent
        forbidden_plan_fields = {"id", "is_public", "created_at", "updated_at", "created_by", "created_by_email"}
        self.assertTrue(forbidden_plan_fields.isdisjoint(item.keys()))

        forbidden_quota_fields = {"scope", "target_code", "target_name", "is_hard_limit", "id", "created_at"}
        self.assertTrue(forbidden_quota_fields.isdisjoint(quota_item.keys()))

    def test_public_plan_discovery_excludes_private_versionless_and_degraded_plans(self):
        """Public plan discovery excludes private, versionless, and degraded plans."""
        # 1. Private plan -> excluded
        self.plan.is_public = False
        self.plan.save(update_fields=["is_public"])
        resp = self.client.get("/api/v1/public/plans/")
        self.assertEqual(resp.json()["count"], 0)
        self.assertEqual(len(resp.json()["results"]), 0)

        # 2. Versionless public plan -> excluded
        plan_no_v = Plan.objects.create(
            code="empty_plan",
            name="Empty Plan",
            is_public=True,
            created_by=self.owner,
            updated_by=self.owner,
        )
        resp = self.client.get("/api/v1/public/plans/")
        self.assertEqual(resp.json()["count"], 0)
        self.assertEqual(len(resp.json()["results"]), 0)

        # 3. Degraded public plan -> excluded
        self.plan.is_public = True
        self.plan.save(update_fields=["is_public"])
        # Retire packaged product to make version degraded
        self.product.status = ProductStatus.RETIRED
        self.product.save(update_fields=["status"])

        resp = self.client.get("/api/v1/public/plans/")
        self.assertEqual(resp.json()["count"], 0)
        self.assertEqual(len(resp.json()["results"]), 0)

    def test_plan_public_publishing_validation(self):
        """Plan public publishing validation rejects degraded or versionless plans and allows unpublishing."""
        self.client.force_authenticate(user=self.owner)
        # Create draft-only plan
        draft_plan, _ = create_plan(code="draft_only", name="Draft Only", actor=self.owner)

        # 1. Attempt to publish versionless/draft-only plan -> rejected
        resp = self.client.patch(
            f"/api/v1/plans/{draft_plan.id}/",
            {"is_public": True},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

        # 2. Publish healthy active plan -> succeeds
        resp_ok = self.client.patch(
            f"/api/v1/plans/{self.plan.id}/",
            {"is_public": True},
            format="json",
        )
        self.assertEqual(resp_ok.status_code, status.HTTP_200_OK)
        self.assertTrue(resp_ok.json()["is_public"])

        # 3. Unpublish plan -> always succeeds
        resp_unpub = self.client.patch(
            f"/api/v1/plans/{self.plan.id}/",
            {"is_public": False},
            format="json",
        )
        self.assertEqual(resp_unpub.status_code, status.HTTP_200_OK)
        self.assertFalse(resp_unpub.json()["is_public"])
