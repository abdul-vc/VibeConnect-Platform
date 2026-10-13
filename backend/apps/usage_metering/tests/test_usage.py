from decimal import Decimal
import uuid

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.access_control.models import AccessPermission, Role, RolePermission
from apps.organizations.models import MembershipStatus, MembershipType, Organization, OrganizationMembership
from apps.plans.models import (
    BillingInterval,
    Plan,
    PlanCurrency,
    PlanPrice,
    PlanQuota,
    PlanVersion,
    PlanVersionStatus,
    QuotaLimitType,
    QuotaResetPeriod,
    QuotaScope,
)
from apps.product_registry.models import Product
from apps.subscriptions.models import OrganizationSubscription, SubscriptionQuotaEntitlement, SubscriptionStatus
from apps.usage_metering.models import MeterDefinition, UsageBucket, UsageEvent
from apps.usage_metering.services import aggregate_usage_buckets, ingest_usage_event

PlatformUser = get_user_model()


class UsageMeteringTests(TestCase):
    def setUp(self):
        self.client = APIClient()

        self.owner = PlatformUser.objects.create_user(
            email="po_usage@vibeconnect.internal",
            password="Password@12345",
            is_platform_owner=True,
            is_staff=True,
            is_superuser=True,
        )

        self.org = Organization.objects.create(
            name="Acme Corp",
            code="acme",
            created_by=self.owner,
            updated_by=self.owner,
        )

        self.tenant_admin = PlatformUser.objects.create_user(
            email="admin@acme.internal",
            password="Password@12345",
            is_platform_owner=False,
        )

        self.unprivileged_user = PlatformUser.objects.create_user(
            email="guest@acme.internal",
            password="Password@12345",
            is_platform_owner=False,
        )

        # Tenant Admin membership with usage.view role
        role = Role.objects.filter(code="system_tenant_admin").first()
        OrganizationMembership.objects.create(
            user=self.tenant_admin,
            organization=self.org,
            membership_type=MembershipType.TENANT_ADMIN,
            status=MembershipStatus.ACTIVE,
            role=role,
            joined_at=timezone.now(),
        )

        # Unprivileged membership without usage.view
        OrganizationMembership.objects.create(
            user=self.unprivileged_user,
            organization=self.org,
            membership_type=MembershipType.MEMBER,
            status=MembershipStatus.ACTIVE,
            role=None,
            joined_at=timezone.now(),
        )

    def test_01_idempotent_ingestion(self):
        """Duplicate event_key ingestion is a no-op that returns existing event without re-incrementing."""
        self.client.force_authenticate(user=self.owner)

        payload = {
            "organization_id": str(self.org.id),
            "meter_key": "api_calls",
            "quantity": 10,
            "event_key": "evt-idempotent-001",
        }

        # First call -> 201 Created
        res1 = self.client.post("/api/v1/usage/events/", payload, format="json")
        self.assertEqual(res1.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res1.data["status"], "recorded")
        self.assertEqual(UsageEvent.objects.filter(event_key="evt-idempotent-001").count(), 1)

        # Duplicate call -> 200 OK (no duplicate record)
        res2 = self.client.post("/api/v1/usage/events/", payload, format="json")
        self.assertEqual(res2.status_code, status.HTTP_200_OK)
        self.assertEqual(res2.data["status"], "duplicate")
        self.assertEqual(UsageEvent.objects.filter(event_key="evt-idempotent-001").count(), 1)

    def test_02_bucket_aggregation_correctness(self):
        """Unprocessed events are aggregated atomically into UsageBucket."""
        ingest_usage_event(
            organization=self.org,
            meter_key="compute_hours",
            quantity=5,
            event_key="evt-agg-1",
        )
        ingest_usage_event(
            organization=self.org,
            meter_key="compute_hours",
            quantity=7,
            event_key="evt-agg-2",
        )

        processed_count = aggregate_usage_buckets(organization_id=str(self.org.id))
        self.assertEqual(processed_count, 2)

        bucket = UsageBucket.objects.filter(
            organization=self.org,
            meter__quota_key="compute_hours",
        ).first()
        self.assertIsNotNone(bucket)
        self.assertEqual(bucket.consumed, 12)

    def test_03_quota_exceeded_flagging(self):
        """Consumption exceeding subscription quota entitlement sets is_over_limit=True."""
        # Create plan, subscription, and quota entitlement
        product = Product.objects.create(
            code="core_prod",
            name="Core Product",
            created_by=self.owner,
            updated_by=self.owner,
        )
        plan = Plan.objects.create(
            code="plan-pro",
            name="Pro Plan",
            created_by=self.owner,
            updated_by=self.owner,
        )
        plan_version = PlanVersion.objects.create(
            plan=plan,
            version=1,
            status=PlanVersionStatus.ACTIVE,
            activated_at=timezone.now(),
            created_by=self.owner,
            updated_by=self.owner,
        )
        plan_price = PlanPrice.objects.create(
            plan_version=plan_version,
            currency=PlanCurrency.USD,
            billing_interval=BillingInterval.MONTHLY,
            amount=Decimal("99.00"),
            created_by=self.owner,
            updated_by=self.owner,
        )
        sub = OrganizationSubscription.objects.create(
            organization=self.org,
            plan_version=plan_version,
            plan_price=plan_price,
            plan_code_snapshot=plan.code,
            plan_name_snapshot=plan.name,
            version_number_snapshot=plan_version.version,
            billing_interval=BillingInterval.MONTHLY,
            currency=PlanCurrency.USD,
            amount=plan_price.amount,
            status=SubscriptionStatus.ACTIVE,
            current_period_start=timezone.now(),
            current_period_end=timezone.now() + timezone.timedelta(days=30),
            started_as_trial=False,
            created_by=self.owner,
            updated_by=self.owner,
        )
        plan_quota = PlanQuota.objects.create(
            plan_version=plan_version,
            quota_key="storage_gb",
            name="Storage",
            scope=QuotaScope.PLAN,
            limit_type=QuotaLimitType.NUMERIC,
            limit_value=100,
            unit="gb",
            reset_period=QuotaResetPeriod.MONTHLY,
            created_by=self.owner,
            updated_by=self.owner,
        )
        SubscriptionQuotaEntitlement.objects.create(
            subscription=sub,
            organization=self.org,
            plan_quota=plan_quota,
            quota_key="storage_gb",
            name="Storage",
            scope=QuotaScope.PLAN,
            limit_type=QuotaLimitType.NUMERIC,
            limit_value=100,
            unit="gb",
            reset_period=QuotaResetPeriod.MONTHLY,
        )

        # Ingest 150 GB (exceeding limit of 100)
        ingest_usage_event(
            organization=self.org,
            meter_key="storage_gb",
            quantity=150,
            event_key="evt-quota-exceed",
        )
        aggregate_usage_buckets(organization_id=str(self.org.id))

        bucket = UsageBucket.objects.filter(
            organization=self.org,
            meter__quota_key="storage_gb",
        ).first()
        self.assertIsNotNone(bucket)
        self.assertEqual(bucket.consumed, 150)
        self.assertEqual(bucket.limit_value, 100)
        self.assertTrue(bucket.is_over_limit)

    def test_04_permission_denial_without_usage_view(self):
        """User without usage.view permission is denied access to tenant usage summary."""
        self.client.force_authenticate(user=self.unprivileged_user)
        res = self.client.get(f"/api/v1/tenant/usage/?organization_id={self.org.id}")
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
