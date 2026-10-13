"""Retention Evaluation Service for VibeConnect Phase 6F-3.

Executes non-destructive dry-run evaluations of data retention candidates
across forensic audit logs, developer webhook deliveries, provisioning jobs,
integration events, failures, reconciliation issues, and usage events.

Enforces zero destructive mutations pending formal business policy approval.
"""

from datetime import timedelta
import logging
from typing import Any
from django.utils import timezone

from apps.auditlog.models import AuditLog
from apps.developer_console.models import DeveloperWebhookDelivery
from apps.identity.models import PlatformUser, UserStatus
from apps.integration_hub.models import (
    FailureStatus,
    IntegrationEvent,
    IntegrationFailure,
    IntegrationReconciliationIssue,
    ProvisioningJob,
    ProvisioningJobStatus,
)
from apps.usage_metering.models import UsageEvent

logger = logging.getLogger(__name__)


def evaluate_data_retention_dry_run() -> dict[str, Any]:
    """Execute dry-run data retention evaluation without modifying or deleting any record.

    Returns candidate counts across all 8 governed entity categories along with
    authoritative policy disclaimer.
    """
    now = timezone.now()

    # 1. Developer Webhook Deliveries (Proposed: 30 days)
    cutoff_webhooks = now - timedelta(days=30)
    candidates_webhooks = DeveloperWebhookDelivery.objects.filter(created_at__lt=cutoff_webhooks).count()

    # 2. Integration Events (Proposed: 60 days)
    cutoff_integ_events = now - timedelta(days=60)
    candidates_integ_events = IntegrationEvent.objects.filter(received_at__lt=cutoff_integ_events).count()

    # 3. Completed Provisioning Jobs (Proposed: 90 days)
    cutoff_jobs = now - timedelta(days=90)
    candidates_jobs = ProvisioningJob.objects.filter(
        status__in=[ProvisioningJobStatus.COMPLETED, ProvisioningJobStatus.CANCELLED],
        created_at__lt=cutoff_jobs,
    ).count()

    # 4. Resolved Failures (Proposed: 180 days)
    cutoff_failures = now - timedelta(days=180)
    candidates_failures = IntegrationFailure.objects.filter(
        status=FailureStatus.RESOLVED,
        resolved_at__lt=cutoff_failures,
    ).count()

    # 5. Resolved Reconciliation Issues (Proposed: 365 days)
    cutoff_reconcil = now - timedelta(days=365)
    candidates_reconcil = IntegrationReconciliationIssue.objects.filter(
        status="resolved",
        detected_at__lt=cutoff_reconcil,
    ).count()

    # 6. Raw Usage Events (Processed, Proposed: 90 days)
    cutoff_usage = now - timedelta(days=90)
    candidates_usage = UsageEvent.objects.filter(
        processed=True,
        occurred_at__lt=cutoff_usage,
    ).count()

    # 7. Inactive Platform Users Eligible for Anonymization (Disabled > 90 days with non-pseudonymized email)
    cutoff_users = now - timedelta(days=90)
    candidates_users = PlatformUser.objects.filter(
        status=UserStatus.DISABLED,
        updated_at__lt=cutoff_users,
    ).exclude(email__startswith="anonymized-").count()

    # 8. Historical AuditLog Records (Proposed: 7 years = 2555 days)
    cutoff_audit = now - timedelta(days=2555)
    candidates_audit = AuditLog.objects.filter(timestamp__lt=cutoff_audit).count()

    categories = [
        {
            "model": "DeveloperWebhookDelivery",
            "label": "Developer Webhook Deliveries",
            "proposed_retention": "30 Days",
            "candidate_count": candidates_webhooks,
        },
        {
            "model": "IntegrationEvent",
            "label": "Integration Hub Raw Events",
            "proposed_retention": "60 Days",
            "candidate_count": candidates_integ_events,
        },
        {
            "model": "ProvisioningJob",
            "label": "Completed Provisioning Jobs",
            "proposed_retention": "90 Days",
            "candidate_count": candidates_jobs,
        },
        {
            "model": "IntegrationFailure",
            "label": "Resolved Integration Failures",
            "proposed_retention": "180 Days",
            "candidate_count": candidates_failures,
        },
        {
            "model": "IntegrationReconciliationIssue",
            "label": "Resolved Reconciliation Issues",
            "proposed_retention": "365 Days",
            "candidate_count": candidates_reconcil,
        },
        {
            "model": "UsageEvent",
            "label": "Processed Usage Events",
            "proposed_retention": "90 Days",
            "candidate_count": candidates_usage,
        },
        {
            "model": "PlatformUser",
            "label": "Disabled Users Pending Anonymization",
            "proposed_retention": "90 Days post-disable",
            "candidate_count": candidates_users,
        },
        {
            "model": "AuditLog",
            "label": "Immutable Forensic Audit Trail",
            "proposed_retention": "7 Years (2555 Days)",
            "candidate_count": candidates_audit,
        },
    ]

    total_candidates = sum(c["candidate_count"] for c in categories)

    return {
        "status": "dry_run",
        "policy_status": "PROPOSED_NOT_APPROVED",
        "is_dry_run": True,
        "destructive_execution_allowed": False,
        "evaluated_at": now.isoformat(),
        "disclaimer": (
            "CRITICAL POLICY NOTE: Retention periods are PROPOSED and have NOT received formal business authority approval. "
            "This evaluation is strictly read-only and dry-run only. Zero records were modified or deleted. "
            "Execution of real deletion is strictly blocked."
        ),
        "categories": categories,
        "total_candidates": total_candidates,
    }
