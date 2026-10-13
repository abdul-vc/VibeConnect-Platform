import logging
from typing import Optional

from django.db import transaction
from django.utils import timezone

from apps.billing.models import (
    BillingAccount,
    BillingAccountStatus,
    CommercialReconciliation,
    CommercialReconciliationStatus,
    Invoice,
)
from apps.entitlements.models import EntitlementStatus, OrganizationProductEntitlement
from apps.organizations.models import Organization
from apps.subscriptions.models import OrganizationSubscription, SubscriptionStatus

logger = logging.getLogger(__name__)


class ReconciliationIssueCode:
    SUB_ACTIVE_NO_BILLING_ACCOUNT = "SUB_ACTIVE_NO_BILLING_ACCOUNT"
    INVOICE_PRICE_MISMATCH = "INVOICE_PRICE_MISMATCH"
    ORPHANED_ENTITLEMENT = "ORPHANED_ENTITLEMENT"


def run_commercial_reconciliation(organization_id: Optional[str] = None) -> list[CommercialReconciliation]:
    """Read-only commercial reconciliation job.

    Compares billing vs subscriptions vs entitlements and flags anomalies.
    Never auto-mutates financial or entitlement records.
    Idempotent: at most one open record per (organization, issue_code).
    """
    detected_issues: list[CommercialReconciliation] = []

    orgs_qs = Organization.objects.all()
    if organization_id:
        orgs_qs = orgs_qs.filter(id=organization_id)

    for org in orgs_qs:
        # Check 1: Active subscription but no active billing account
        active_sub = OrganizationSubscription.objects.filter(
            organization=org,
            status=SubscriptionStatus.ACTIVE,
        ).first()

        if active_sub:
            has_active_billing = BillingAccount.objects.filter(
                organization=org,
                status=BillingAccountStatus.ACTIVE,
            ).exists()

            if not has_active_billing:
                existing_open = CommercialReconciliation.objects.filter(
                    organization=org,
                    issue_code=ReconciliationIssueCode.SUB_ACTIVE_NO_BILLING_ACCOUNT,
                    status=CommercialReconciliationStatus.OPEN,
                ).first()

                if not existing_open:
                    issue = CommercialReconciliation.objects.create(
                        organization=org,
                        subscription=active_sub,
                        issue_code=ReconciliationIssueCode.SUB_ACTIVE_NO_BILLING_ACCOUNT,
                        status=CommercialReconciliationStatus.OPEN,
                        details={
                            "subscription_id": str(active_sub.id),
                            "subscription_status": active_sub.status,
                            "reason": "Organization has an active subscription but no active billing account.",
                        },
                    )
                    detected_issues.append(issue)

        # Check 2: Invoice total mismatched against plan price snapshot
        invoices = Invoice.objects.filter(
            organization=org,
            subscription__isnull=False,
        ).select_related("subscription")

        for inv in invoices:
            sub = inv.subscription
            if sub and inv.total != sub.amount:
                existing_open = CommercialReconciliation.objects.filter(
                    organization=org,
                    issue_code=ReconciliationIssueCode.INVOICE_PRICE_MISMATCH,
                    status=CommercialReconciliationStatus.OPEN,
                ).first()

                if not existing_open:
                    issue = CommercialReconciliation.objects.create(
                        organization=org,
                        subscription=sub,
                        issue_code=ReconciliationIssueCode.INVOICE_PRICE_MISMATCH,
                        status=CommercialReconciliationStatus.OPEN,
                        details={
                            "invoice_id": str(inv.id),
                            "invoice_number": inv.invoice_number,
                            "invoice_total": str(inv.total),
                            "subscription_amount": str(sub.amount),
                            "reason": f"Invoice {inv.invoice_number} total ({inv.total}) does not match subscription plan price snapshot ({sub.amount}).",
                        },
                    )
                    detected_issues.append(issue)

        # Check 3: Active entitlement with no matching active/trialing subscription
        has_active_or_trial_sub = OrganizationSubscription.objects.filter(
            organization=org,
            status__in=[SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIALING],
        ).exists()

        if not has_active_or_trial_sub:
            active_entitlements = OrganizationProductEntitlement.objects.filter(
                organization=org,
                status=EntitlementStatus.ACTIVE,
            )

            if active_entitlements.exists():
                existing_open = CommercialReconciliation.objects.filter(
                    organization=org,
                    issue_code=ReconciliationIssueCode.ORPHANED_ENTITLEMENT,
                    status=CommercialReconciliationStatus.OPEN,
                ).first()

                if not existing_open:
                    entitlement_ids = [str(e.id) for e in active_entitlements]
                    issue = CommercialReconciliation.objects.create(
                        organization=org,
                        subscription=None,
                        issue_code=ReconciliationIssueCode.ORPHANED_ENTITLEMENT,
                        status=CommercialReconciliationStatus.OPEN,
                        details={
                            "active_entitlement_ids": entitlement_ids,
                            "reason": "Organization has active product entitlements with no active or trialing subscription.",
                        },
                    )
                    detected_issues.append(issue)

    return detected_issues


@transaction.atomic
def resolve_commercial_reconciliation(
    reconciliation_id: str,
    resolved_by_user,
    resolution_reason: str,
) -> CommercialReconciliation:
    """Marks a commercial reconciliation record as resolved with mandatory audit details."""
    reconciliation = CommercialReconciliation.objects.select_for_update().get(id=reconciliation_id)
    reconciliation.status = CommercialReconciliationStatus.RESOLVED
    reconciliation.resolved_at = timezone.now()
    reconciliation.resolved_by = resolved_by_user
    reconciliation.resolution_reason = resolution_reason
    reconciliation.save(update_fields=["status", "resolved_at", "resolved_by", "resolution_reason", "updated_at"])
    return reconciliation
