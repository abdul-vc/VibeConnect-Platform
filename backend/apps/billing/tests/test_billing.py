from decimal import Decimal
import uuid

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.access_control.models import Role
from apps.billing.models import (
    BillingAccount,
    DunningAttempt,
    DunningStatus,
    Invoice,
    InvoiceLine,
    InvoiceStatus,
    Payment,
    PaymentStatus,
)
from apps.billing.services import (
    generate_invoice_for_subscription,
    record_payment,
    schedule_dunning_retry,
)
from apps.notifications.models import BackgroundJob
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


class BillingTests(TestCase):
    def setUp(self):
        self.client = APIClient()

        self.owner = PlatformUser.objects.create_user(
            email="po_billing@vibeconnect.internal",
            password="Password@12345",
            is_platform_owner=True,
            is_staff=True,
            is_superuser=True,
        )

        self.org = Organization.objects.create(
            name="Apex Dynamics",
            code="apex",
            created_by=self.owner,
            updated_by=self.owner,
        )

        self.tenant_admin = PlatformUser.objects.create_user(
            email="admin@apex.internal",
            password="Password@12345",
            is_platform_owner=False,
        )

        self.unprivileged_user = PlatformUser.objects.create_user(
            email="guest@apex.internal",
            password="Password@12345",
            is_platform_owner=False,
        )

        # Tenant admin role with billing.view
        role = Role.objects.filter(code="system_tenant_admin").first()
        OrganizationMembership.objects.create(
            user=self.tenant_admin,
            organization=self.org,
            membership_type=MembershipType.TENANT_ADMIN,
            status=MembershipStatus.ACTIVE,
            role=role,
            joined_at=timezone.now(),
        )

        # Unprivileged membership
        OrganizationMembership.objects.create(
            user=self.unprivileged_user,
            organization=self.org,
            membership_type=MembershipType.MEMBER,
            status=MembershipStatus.ACTIVE,
            role=None,
            joined_at=timezone.now(),
        )

        # Product & Subscription
        product = Product.objects.create(
            code="apex_prod",
            name="Apex Product",
            created_by=self.owner,
            updated_by=self.owner,
        )
        plan = Plan.objects.create(
            code="apex-enterprise",
            name="Apex Enterprise",
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
            amount=Decimal("250.00"),
            created_by=self.owner,
            updated_by=self.owner,
        )
        self.subscription = OrganizationSubscription.objects.create(
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

    def test_01_invoice_immutability(self):
        """Issued invoice and its lines cannot be modified or deleted."""
        invoice = generate_invoice_for_subscription(self.subscription)
        self.assertEqual(invoice.status, InvoiceStatus.ISSUED)

        # Attempt to modify total on issued invoice raises ValidationError
        invoice.total = Decimal("9999.00")
        with self.assertRaises(ValidationError):
            invoice.save()

        # Attempt to delete issued invoice raises ValidationError
        with self.assertRaises(ValidationError):
            invoice.delete()

        # Attempt to add line to issued invoice raises ValidationError
        line = InvoiceLine(
            invoice=invoice,
            description="Extra Line",
            quantity=1,
            unit_price=Decimal("50.00"),
            total=Decimal("50.00"),
        )
        with self.assertRaises(ValidationError):
            line.save()

    def test_02_duplicate_payment_idempotency(self):
        """Payment recording with the same idempotency key is an idempotent no-op."""
        invoice = generate_invoice_for_subscription(self.subscription)
        key = "idemp-key-test-001"

        payment1, created1 = record_payment(
            invoice_id=str(invoice.id),
            amount=Decimal("250.00"),
            currency="USD",
            idempotency_key=key,
        )
        self.assertTrue(created1)
        self.assertEqual(payment1.status, PaymentStatus.SUCCEEDED)

        # Duplicate payment with same key
        payment2, created2 = record_payment(
            invoice_id=str(invoice.id),
            amount=Decimal("250.00"),
            currency="USD",
            idempotency_key=key,
        )
        self.assertFalse(created2)
        self.assertEqual(payment1.id, payment2.id)
        self.assertEqual(Payment.objects.filter(idempotency_key=key).count(), 1)

    def test_03_dunning_attempt_scheduled_via_worker(self):
        """Scheduling dunning creates attempt and enqueues background job."""
        invoice = generate_invoice_for_subscription(self.subscription)
        attempt = schedule_dunning_retry(invoice=invoice, attempt_number=1)

        self.assertEqual(attempt.status, DunningStatus.SCHEDULED)
        self.assertEqual(attempt.attempt_number, 1)

        # Verify background job enqueued
        job = BackgroundJob.objects.filter(
            job_type="dunning_retry",
            payload__contains={"invoice_id": str(invoice.id)},
        ).first()
        self.assertIsNotNone(job)
        self.assertEqual(job.status, "queued")

    def test_04_permission_denial_without_billing_view(self):
        """User without billing.view permission is denied access to tenant billing."""
        self.client.force_authenticate(user=self.unprivileged_user)
        res = self.client.get("/api/v1/tenant/billing/invoices/")
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
