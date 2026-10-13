from decimal import Decimal
import uuid

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.access_control.models import Role
from apps.billing.models import (
    BillingAccount,
    BillingAccountStatus,
    CommercialReconciliation,
    CommercialReconciliationStatus,
    Invoice,
    InvoiceStatus,
)
from apps.billing.reconciliation import (
    ReconciliationIssueCode,
    resolve_commercial_reconciliation,
    run_commercial_reconciliation,
)
from apps.entitlements.models import EntitlementStatus, OrganizationProductEntitlement
from apps.organizations.models import MembershipStatus, MembershipType, Organization, OrganizationMembership
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

PlatformUser = get_user_model()


class CommercialReconciliationTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.owner = PlatformUser.objects.create_superuser(
            email="owner@vibeconnect.io",
            password="Password@12345",
            is_platform_owner=True,
        )

        self.org = Organization.objects.create(
            name="Apex Labs",
            code="apex-labs",
            created_by=self.owner,
            updated_by=self.owner,
        )

        # Setup plan and subscription
        self.product = Product.objects.create(
            code="apex_prod",
            name="Apex Product",
            created_by=self.owner,
            updated_by=self.owner,
        )
        plan = Plan.objects.create(
            code="apex-pro",
            name="Apex Pro",
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
        self.plan_price = PlanPrice.objects.create(
            plan_version=plan_version,
            currency=PlanCurrency.USD,
            billing_interval=BillingInterval.MONTHLY,
            amount=Decimal("150.00"),
            created_by=self.owner,
            updated_by=self.owner,
        )
        self.plan = plan
        self.plan_version = plan_version

    def test_01_active_sub_no_billing_account_flagged(self):
        """Active subscription without an active billing account is flagged."""
        # Create active subscription with no billing account
        sub = OrganizationSubscription.objects.create(
            organization=self.org,
            plan_version=self.plan_version,
            plan_price=self.plan_price,
            plan_code_snapshot=self.plan.code,
            plan_name_snapshot=self.plan.name,
            version_number_snapshot=self.plan_version.version,
            billing_interval=BillingInterval.MONTHLY,
            currency=PlanCurrency.USD,
            amount=self.plan_price.amount,
            status=SubscriptionStatus.ACTIVE,
            current_period_start=timezone.now(),
            current_period_end=timezone.now() + timezone.timedelta(days=30),
            started_as_trial=False,
            created_by=self.owner,
            updated_by=self.owner,
        )

        issues = run_commercial_reconciliation(organization_id=str(self.org.id))
        self.assertTrue(any(i.issue_code == ReconciliationIssueCode.SUB_ACTIVE_NO_BILLING_ACCOUNT for i in issues))

        # Idempotency check: repeated run does not create duplicate open issue
        issues_run2 = run_commercial_reconciliation(organization_id=str(self.org.id))
        self.assertEqual(len(issues_run2), 0)
        self.assertEqual(
            CommercialReconciliation.objects.filter(
                organization=self.org,
                issue_code=ReconciliationIssueCode.SUB_ACTIVE_NO_BILLING_ACCOUNT,
                status=CommercialReconciliationStatus.OPEN,
            ).count(),
            1,
        )

    def test_02_invoice_price_mismatch_flagged(self):
        """Invoice total mismatched against plan price snapshot is flagged."""
        sub = OrganizationSubscription.objects.create(
            organization=self.org,
            plan_version=self.plan_version,
            plan_price=self.plan_price,
            plan_code_snapshot=self.plan.code,
            plan_name_snapshot=self.plan.name,
            version_number_snapshot=self.plan_version.version,
            billing_interval=BillingInterval.MONTHLY,
            currency=PlanCurrency.USD,
            amount=Decimal("150.00"),
            status=SubscriptionStatus.ACTIVE,
            current_period_start=timezone.now(),
            current_period_end=timezone.now() + timezone.timedelta(days=30),
            started_as_trial=False,
            created_by=self.owner,
            updated_by=self.owner,
        )
        BillingAccount.objects.create(
            organization=self.org,
            legal_name="Apex Labs LLC",
            billing_email="billing@apexlabs.com",
            status=BillingAccountStatus.ACTIVE,
        )
        # Create an invoice with mismatched total
        Invoice.objects.create(
            organization=self.org,
            subscription=sub,
            invoice_number="INV-MISMATCH-001",
            currency="USD",
            subtotal=Decimal("999.00"),
            tax_total=Decimal("0.00"),
            total=Decimal("999.00"),  # Mismatches plan price 150.00
            status=InvoiceStatus.ISSUED,
            due_date=timezone.now().date(),
        )

        issues = run_commercial_reconciliation(organization_id=str(self.org.id))
        self.assertTrue(any(i.issue_code == ReconciliationIssueCode.INVOICE_PRICE_MISMATCH for i in issues))

    def test_03_orphaned_entitlement_flagged(self):
        """Active product entitlement with no active/trialing subscription is flagged."""
        # Create active entitlement directly with no subscription
        OrganizationProductEntitlement.objects.create(
            organization=self.org,
            product=self.product,
            status=EntitlementStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )

        issues = run_commercial_reconciliation(organization_id=str(self.org.id))
        self.assertTrue(any(i.issue_code == ReconciliationIssueCode.ORPHANED_ENTITLEMENT for i in issues))

    def test_04_mark_resolved_audit_trail(self):
        """Resolving a reconciliation issue updates status and stores full audit trail."""
        issue = CommercialReconciliation.objects.create(
            organization=self.org,
            issue_code=ReconciliationIssueCode.SUB_ACTIVE_NO_BILLING_ACCOUNT,
            status=CommercialReconciliationStatus.OPEN,
            details={"note": "Test issue"},
        )

        self.client.force_authenticate(user=self.owner)
        url = f"/api/v1/billing/reconciliations/{issue.id}/resolve/"
        payload = {"resolution_reason": "Manually verified enterprise contract and off-platform billing agreement."}

        res = self.client.post(url, payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["status"], CommercialReconciliationStatus.RESOLVED)
        self.assertEqual(res.data["resolution_reason"], payload["resolution_reason"])
        self.assertEqual(res.data["resolved_by_email"], self.owner.email)

        # Verify persisted database record
        issue.refresh_from_db()
        self.assertEqual(issue.status, CommercialReconciliationStatus.RESOLVED)
        self.assertIsNotNone(issue.resolved_at)
        self.assertEqual(issue.resolved_by, self.owner)
        self.assertEqual(issue.resolution_reason, payload["resolution_reason"])
