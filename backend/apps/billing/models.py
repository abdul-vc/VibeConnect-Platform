import uuid
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class BillingAccountStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    DELINQUENT = "delinquent", "Delinquent"
    SUSPENDED = "suspended", "Suspended"


class InvoiceStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    ISSUED = "issued", "Issued"
    PAID = "paid", "Paid"
    VOID = "void", "Void"
    UNCOLLECTIBLE = "uncollectible", "Uncollectible"


class PaymentStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    SUCCEEDED = "succeeded", "Succeeded"
    FAILED = "failed", "Failed"


class DunningStatus(models.TextChoices):
    SCHEDULED = "scheduled", "Scheduled"
    PROCESSING = "processing", "Processing"
    SUCCEEDED = "succeeded", "Succeeded"
    FAILED = "failed", "Failed"
    ABANDONED = "abandoned", "Abandoned"


class BillingAccount(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.OneToOneField(
        "organizations.Organization",
        on_delete=models.PROTECT,
        related_name="billing_account",
    )
    legal_name = models.CharField(max_length=255)
    tax_id = models.CharField(max_length=64, blank=True, default="")
    billing_email = models.EmailField()
    status = models.CharField(
        max_length=20,
        choices=BillingAccountStatus.choices,
        default=BillingAccountStatus.ACTIVE,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "billing_accounts"
        verbose_name = "Billing Account"
        verbose_name_plural = "Billing Accounts"

    def __str__(self) -> str:
        return f"{self.legal_name} ({self.organization.name})"


class TaxRate(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    jurisdiction = models.CharField(max_length=50)
    tax_code = models.CharField(max_length=50)
    rate = models.DecimalField(max_digits=5, decimal_places=4)
    valid_from = models.DateTimeField(default=timezone.now)
    valid_until = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "tax_rates"
        verbose_name = "Tax Rate"
        verbose_name_plural = "Tax Rates"

    def __str__(self) -> str:
        return f"{self.jurisdiction} - {self.tax_code} ({self.rate * 100}%)"


class Invoice(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.PROTECT,
        related_name="invoices",
    )
    subscription = models.ForeignKey(
        "subscriptions.OrganizationSubscription",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="invoices",
    )
    invoice_number = models.CharField(max_length=64, unique=True)
    currency = models.CharField(max_length=10, default="USD")
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    tax_total = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    total = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    status = models.CharField(
        max_length=20,
        choices=InvoiceStatus.choices,
        default=InvoiceStatus.DRAFT,
    )
    due_date = models.DateField(null=True, blank=True)
    issued_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "invoices"
        verbose_name = "Invoice"
        verbose_name_plural = "Invoices"
        indexes = [
            models.Index(fields=["organization", "status"]),
        ]

    def clean(self):
        super().clean()
        if self.pk:
            old = Invoice.objects.filter(pk=self.pk).first()
            if old and old.status != InvoiceStatus.DRAFT:
                immutable_fields = ["invoice_number", "organization_id", "subscription_id", "currency", "subtotal", "tax_total", "total"]
                for f in immutable_fields:
                    if getattr(self, f) != getattr(old, f):
                        raise ValidationError(f"Issued invoice financial field '{f}' is immutable.")

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self.status != InvoiceStatus.DRAFT:
            raise ValidationError("Issued invoices cannot be deleted; they are immutable records.")
        super().delete(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.invoice_number} ({self.organization.name}) - {self.status}"


class InvoiceLine(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    invoice = models.ForeignKey(
        Invoice,
        on_delete=models.CASCADE,
        related_name="lines",
    )
    description = models.CharField(max_length=255)
    quantity = models.IntegerField(default=1)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    tax_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    total = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "invoice_lines"
        verbose_name = "Invoice Line"
        verbose_name_plural = "Invoice Lines"

    def clean(self):
        super().clean()
        if self.invoice and self.invoice.status != InvoiceStatus.DRAFT:
            raise ValidationError("Cannot add or modify lines on an issued invoice.")

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self.invoice and self.invoice.status != InvoiceStatus.DRAFT:
            raise ValidationError("Cannot delete lines on an issued invoice.")
        super().delete(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.description} ({self.quantity} x {self.unit_price})"


class Payment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    invoice = models.ForeignKey(
        Invoice,
        on_delete=models.PROTECT,
        related_name="payments",
    )
    processor_ref = models.CharField(max_length=128, blank=True, default="")
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=10, default="USD")
    status = models.CharField(
        max_length=20,
        choices=PaymentStatus.choices,
        default=PaymentStatus.SUCCEEDED,
    )
    idempotency_key = models.CharField(max_length=128, unique=True)
    recorded_at = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "payments"
        verbose_name = "Payment"
        verbose_name_plural = "Payments"

    def __str__(self) -> str:
        return f"Payment {self.idempotency_key}: {self.amount} {self.currency} ({self.status})"


class DunningAttempt(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    invoice = models.ForeignKey(
        Invoice,
        on_delete=models.CASCADE,
        related_name="dunning_attempts",
    )
    attempt_number = models.PositiveSmallIntegerField(default=1)
    status = models.CharField(
        max_length=20,
        choices=DunningStatus.choices,
        default=DunningStatus.SCHEDULED,
    )
    scheduled_at = models.DateTimeField(default=timezone.now)
    executed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "dunning_attempts"
        verbose_name = "Dunning Attempt"
        verbose_name_plural = "Dunning Attempts"

    def __str__(self) -> str:
        return f"Dunning #{self.attempt_number} for {self.invoice.invoice_number} ({self.status})"


class CommercialReconciliationStatus(models.TextChoices):
    OPEN = "open", "Open"
    RESOLVED = "resolved", "Resolved"


class CommercialReconciliation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="commercial_reconciliations",
    )
    subscription = models.ForeignKey(
        "subscriptions.OrganizationSubscription",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="commercial_reconciliations",
    )
    issue_code = models.CharField(max_length=64)
    status = models.CharField(
        max_length=20,
        choices=CommercialReconciliationStatus.choices,
        default=CommercialReconciliationStatus.OPEN,
    )
    details = models.JSONField(default=dict, blank=True)
    detected_at = models.DateTimeField(default=timezone.now)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    resolution_reason = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "commercial_reconciliations"
        verbose_name = "Commercial Reconciliation"
        verbose_name_plural = "Commercial Reconciliations"
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "issue_code"],
                condition=models.Q(status="open"),
                name="unique_open_commercial_reconciliation_per_org_issue",
            ),
        ]

    def __str__(self) -> str:
        return f"Reconciliation {self.issue_code} for {self.organization_id} ({self.status})"

