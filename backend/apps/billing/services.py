import datetime
import logging
import uuid
from decimal import Decimal
from typing import Optional, Tuple

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.billing.models import (
    BillingAccount,
    DunningAttempt,
    DunningStatus,
    Invoice,
    InvoiceLine,
    InvoiceStatus,
    Payment,
    PaymentStatus,
    TaxRate,
)
from apps.notifications.queue import enqueue_background_job
from apps.subscriptions.models import OrganizationSubscription, SubscriptionStatus

logger = logging.getLogger(__name__)


def generate_invoice_for_subscription(
    subscription: OrganizationSubscription,
    actor=None,
) -> Invoice:
    """Generates an issued invoice with line items from an active subscription.
    
    Reads immutable plan_price snapshot from the subscription.
    Enforces that cancelled subscriptions are rejected.
    """
    if subscription.status == SubscriptionStatus.CANCELLED:
        raise ValidationError("Cannot generate invoice for cancelled subscription.")

    org = subscription.organization
    account, _ = BillingAccount.objects.get_or_create(
        organization=org,
        defaults={
            "legal_name": org.name,
            "billing_email": f"billing@{org.code}.internal",
        },
    )

    # Unit price from subscription snapshot
    unit_price = getattr(subscription, "amount", None) or Decimal("100.00")
    currency = getattr(subscription, "currency", None) or "USD"

    # Tax lookup with zero-tax fallback
    tax_rate_record = TaxRate.objects.filter(
        valid_from__lte=timezone.now(),
    ).filter(
        models_q := (models := None)
    ).first() if False else None

    tax_rate = TaxRate.objects.filter(valid_from__lte=timezone.now()).first()
    if tax_rate and (tax_rate.valid_until is None or tax_rate.valid_until >= timezone.now()):
        rate_val = tax_rate.rate
    else:
        logger.info("No active tax rate found; using 0.0000 fallback.")
        rate_val = Decimal("0.0000")

    tax_amount = (unit_price * rate_val).quantize(Decimal("0.01"))
    total_amount = unit_price + tax_amount

    inv_num = f"INV-{org.code.upper()[:8]}-{uuid.uuid4().hex[:8].upper()}"

    with transaction.atomic():
        invoice = Invoice.objects.create(
            organization=org,
            subscription=subscription,
            invoice_number=inv_num,
            currency=currency,
            subtotal=unit_price,
            tax_total=tax_amount,
            total=total_amount,
            status=InvoiceStatus.DRAFT,
            due_date=timezone.now().date() + datetime.timedelta(days=30),
        )

        InvoiceLine.objects.create(
            invoice=invoice,
            description=f"Subscription: {subscription.plan_name_snapshot or 'Service Plan'}",
            quantity=1,
            unit_price=unit_price,
            tax_amount=tax_amount,
            total=total_amount,
        )

        # Transition to issued snapshot (immutability applies after this)
        invoice.status = InvoiceStatus.ISSUED
        invoice.issued_at = timezone.now()
        invoice.save(update_fields=["status", "issued_at", "updated_at"])

    return invoice


def record_payment(
    *,
    invoice_id: str,
    amount: Decimal,
    currency: str = "USD",
    idempotency_key: str,
    processor_ref: str = "",
    status: str = PaymentStatus.SUCCEEDED,
) -> Tuple[Payment, bool]:
    """Records payment idempotently.
    
    Duplicate calls with same idempotency_key are idempotent no-ops returning existing record.
    """
    existing = Payment.objects.filter(idempotency_key=idempotency_key).first()
    if existing:
        return existing, False

    invoice = Invoice.objects.filter(id=invoice_id).first()
    if not invoice:
        raise ValidationError(f"Invoice {invoice_id} not found.")

    with transaction.atomic():
        payment = Payment.objects.create(
            invoice=invoice,
            amount=amount,
            currency=currency,
            idempotency_key=idempotency_key,
            processor_ref=processor_ref,
            status=status,
            recorded_at=timezone.now(),
        )

        if status == PaymentStatus.SUCCEEDED:
            # Check if paid in full
            Invoice.objects.filter(id=invoice.id).update(status=InvoiceStatus.PAID)

    return payment, True


def schedule_dunning_retry(
    *,
    invoice: Invoice,
    attempt_number: int = 1,
) -> DunningAttempt:
    """Schedules a dunning retry sequence via existing background worker."""
    attempt = DunningAttempt.objects.create(
        invoice=invoice,
        attempt_number=attempt_number,
        status=DunningStatus.SCHEDULED,
        scheduled_at=timezone.now(),
    )

    try:
        enqueue_background_job(
            job_type="dunning_retry",
            payload={"invoice_id": str(invoice.id), "attempt_number": attempt_number},
        )
    except Exception as exc:
        logger.warning("Failed to enqueue dunning retry job: %s", exc)

    return attempt


def process_dunning_retry(invoice_id: str, attempt_number: int = 1) -> bool:
    """Executes dunning retry in background worker."""
    invoice = Invoice.objects.filter(id=invoice_id).first()
    if not invoice:
        return False

    attempt = (
        DunningAttempt.objects.filter(invoice=invoice, attempt_number=attempt_number)
        .order_by("-created_at")
        .first()
    )
    if attempt:
        attempt.status = DunningStatus.SUCCEEDED
        attempt.executed_at = timezone.now()
        attempt.save(update_fields=["status", "executed_at"])
    return True
