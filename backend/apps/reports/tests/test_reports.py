from decimal import Decimal
import uuid

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.access_control.models import (
    AccessPermission,
    ConsoleModule,
    OrganizationConsoleModulePolicy,
    OrganizationPermissionCeiling,
    Role,
)
from apps.assignments.models import UserProductAssignment
from apps.billing.models import (
    BillingAccount,
    BillingAccountStatus,
    CommercialReconciliation,
    CommercialReconciliationStatus,
    Invoice,
    InvoiceStatus,
)
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
    PlanCurrency,
    PlanPrice,
    PlanVersion,
    PlanVersionStatus,
)
from apps.product_registry.models import Product
from apps.subscriptions.models import OrganizationSubscription, SubscriptionStatus
from apps.usage_metering.models import MeterDefinition, UsageBucket, UsageEvent

PlatformUser = get_user_model()


class ReportsTests(TestCase):
    def setUp(self):
        self.client = APIClient()

        # Platform owner
        self.owner = PlatformUser.objects.create_user(
            email="owner_reports@vibeconnect.internal",
            password="Password@12345",
            is_platform_owner=True,
            is_staff=True,
            is_superuser=True,
        )

        # Organization
        self.org = Organization.objects.create(
            name="Alpha Corp",
            code="alpha-corp",
            created_by=self.owner,
            updated_by=self.owner,
            status=OrganizationStatus.ACTIVE,
        )

        # Tenant Admin with system_tenant_admin role (has reports.view)
        self.tenant_admin = PlatformUser.objects.create_user(
            email="admin@alpha.internal",
            password="Password@12345",
            is_platform_owner=False,
            status="active",
        )
        admin_role = Role.objects.filter(code="system_tenant_admin").first()
        self.tenant_admin_membership = OrganizationMembership.objects.create(
            user=self.tenant_admin,
            organization=self.org,
            membership_type=MembershipType.TENANT_ADMIN,
            status=MembershipStatus.ACTIVE,
            role=admin_role,
            joined_at=timezone.now(),
        )

        # Enable reports module and permission ceiling for Org Alpha
        mod_reports = ConsoleModule.objects.get(key="tenant_reports")
        perm_reports = AccessPermission.objects.get(key="reports.view")
        OrganizationConsoleModulePolicy.objects.get_or_create(
            organization=self.org,
            console_module=mod_reports,
            defaults={"is_enabled": True, "updated_by": self.owner},
        )
        OrganizationPermissionCeiling.objects.get_or_create(
            organization=self.org,
            permission=perm_reports,
            defaults={"is_allowed": True, "updated_by": self.owner},
        )

        # Unprivileged tenant user without reports.view
        self.unprivileged_user = PlatformUser.objects.create_user(
            email="user@alpha.internal",
            password="Password@12345",
            is_platform_owner=False,
        )
        OrganizationMembership.objects.create(
            user=self.unprivileged_user,
            organization=self.org,
            membership_type=MembershipType.MEMBER,
            status=MembershipStatus.ACTIVE,
            role=None,
            joined_at=timezone.now(),
        )

        # Product & Entitlement
        self.product = Product.objects.create(
            code="alpha_lms",
            name="Alpha LMS",
            created_by=self.owner,
            updated_by=self.owner,
        )
        self.entitlement = OrganizationProductEntitlement.objects.create(
            organization=self.org,
            product=self.product,
            status=EntitlementStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )

        # Seat Assignment
        UserProductAssignment.objects.create(
            organization=self.org,
            user=self.tenant_admin,
            membership=self.tenant_admin_membership,
            product=self.product,
            status="active",
            created_by=self.owner,
            updated_by=self.owner,
        )

        # Plan & Subscription
        self.plan = Plan.objects.create(
            code="plan_pro",
            name="Pro Plan",
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
            currency=PlanCurrency.USD,
            billing_interval=BillingInterval.MONTHLY,
            amount=Decimal("199.00"),
            created_by=self.owner,
            updated_by=self.owner,
        )
        self.subscription = OrganizationSubscription.objects.create(
            organization=self.org,
            plan_version=self.plan_version,
            plan_price=self.plan_price,
            status=SubscriptionStatus.ACTIVE,
            billing_interval=BillingInterval.MONTHLY,
            currency=PlanCurrency.USD,
            amount=Decimal("199.00"),
            plan_code_snapshot="plan_pro",
            plan_name_snapshot="Pro Plan",
            version_number_snapshot=self.plan_version.version,
            current_period_start=timezone.now(),
            current_period_end=timezone.now() + timezone.timedelta(days=30),
            started_as_trial=False,
            created_by=self.owner,
            updated_by=self.owner,
        )

        # Meter & Bucket
        self.meter = MeterDefinition.objects.create(
            quota_key="api_calls",
            name="API Calls",
            unit="calls",
        )
        self.bucket = UsageBucket.objects.create(
            organization=self.org,
            meter=self.meter,
            period_start=timezone.now() - timezone.timedelta(days=1),
            period_end=timezone.now() + timezone.timedelta(days=29),
            consumed=50,
            is_over_limit=False,
        )
        UsageEvent.objects.create(
            organization=self.org,
            meter=self.meter,
            event_key="evt_001",
            quantity=50,
            occurred_at=timezone.now(),
        )

        # Billing Account & Invoice
        self.billing_account = BillingAccount.objects.create(
            organization=self.org,
            legal_name="Alpha Legal Corp",
            billing_email="billing@alpha.internal",
            status=BillingAccountStatus.ACTIVE,
        )
        self.invoice = Invoice.objects.create(
            organization=self.org,
            invoice_number="INV-2026-0001",
            subscription=self.subscription,
            status=InvoiceStatus.PAID,
            subtotal=Decimal("199.00"),
            tax_total=Decimal("0.00"),
            total=Decimal("199.00"),
            currency="USD",
            issued_at=timezone.now(),
            due_date=timezone.now().date(),
        )

    def test_01_owner_aggregate_correctness(self):
        """Owner summary endpoint correctly aggregates cross-tenant counts, adoption, usage, and commercial metrics."""
        self.client.force_authenticate(user=self.owner)
        res = self.client.get("/api/v1/reports/summary/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        # Check organizations
        self.assertEqual(res.data["organizations"]["total"], 1)
        self.assertEqual(res.data["organizations"]["active"], 1)
        self.assertEqual(res.data["organizations"]["inactive"], 0)

        # Check product adoption
        self.assertEqual(len(res.data["product_adoption"]), 1)
        self.assertEqual(res.data["product_adoption"][0]["product_code"], "alpha_lms")
        self.assertEqual(res.data["product_adoption"][0]["adopted_tenants_count"], 1)

        # Check usage totals
        self.assertEqual(res.data["usage"]["total_events"], 1)
        self.assertEqual(res.data["usage"]["total_buckets"], 1)
        self.assertEqual(res.data["usage"]["over_limit_buckets"], 0)

        # Check commercial totals
        self.assertEqual(res.data["commercial"]["active_subscriptions"], 1)
        self.assertEqual(res.data["commercial"]["total_invoices"], 1)
        self.assertEqual(res.data["commercial"]["paid_invoices"], 1)
        self.assertEqual(res.data["commercial"]["open_reconciliations"], 0)

    def test_02_tenant_scoped_aggregate_correctness(self):
        """Tenant-scoped summary returns only tenant's own seat utilization, usage buckets, subscription, and invoices."""
        self.client.force_authenticate(user=self.tenant_admin)
        res = self.client.get("/api/v1/tenant/reports/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        # Seat utilization
        self.assertEqual(res.data["seat_utilization"]["total_assigned"], 1)

        # Usage buckets
        self.assertEqual(len(res.data["usage_buckets"]), 1)
        self.assertEqual(res.data["usage_buckets"][0]["meter_key"], "api_calls")
        self.assertEqual(res.data["usage_buckets"][0]["consumed"], 50)
        self.assertFalse(res.data["usage_buckets"][0]["is_over_limit"])

        # Subscription
        self.assertIsNotNone(res.data["subscription"])
        self.assertEqual(res.data["subscription"]["plan_code"], "plan_pro")
        self.assertEqual(res.data["subscription"]["status"], SubscriptionStatus.ACTIVE)

        # Invoices
        self.assertEqual(res.data["invoices"]["total"], 1)
        self.assertEqual(res.data["invoices"]["paid"], 1)

    def test_03_permission_denial_without_reports_view(self):
        """Users without reports.view are denied tenant reports; non-owners are denied owner reports."""
        # Unprivileged tenant user without reports.view
        self.client.force_authenticate(user=self.unprivileged_user)
        res = self.client.get("/api/v1/tenant/reports/")
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

        # Tenant admin cannot access owner reports
        self.client.force_authenticate(user=self.tenant_admin)
        res_owner = self.client.get("/api/v1/reports/summary/")
        self.assertEqual(res_owner.status_code, status.HTTP_403_FORBIDDEN)
