"""Management command to evaluate data retention candidates (Phase 6F-3).

Enforces non-destructive dry-run reporting only.
Execution of destructive deletion is strictly blocked pending formal business approval
of the proposed retention periods documented in DATA_INVENTORY_AND_RETENTION.md.
"""

from datetime import timedelta
import logging

from django.core.management.base import BaseCommand, CommandError
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


class Command(BaseCommand):
    help = "Evaluate data retention candidate records in dry-run mode (Phase 6F-3)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            default=True,
            help="Perform evaluation in dry-run mode without modifying records (default & mandatory).",
        )
        parser.add_argument(
            "--execute",
            action="store_true",
            default=False,
            help="Attempt execution of real deletion (strictly prohibited for unapproved policies).",
        )

    def handle(self, *args, **options):
        execute = options.get("execute", False)
        if execute:
            raise CommandError(
                "CRITICAL POLICY BLOCK: Execution of retention purges is prohibited. "
                "Retention periods from Phase 6F-1 are currently PROPOSED, NOT APPROVED by business authority. "
                "Only dry-run candidate reporting is permitted."
            )

        now = timezone.now()
        self.stdout.write(self.style.WARNING("=" * 80))
        self.stdout.write(self.style.WARNING("VIBECONNECT DATA RETENTION EVALUATION (PHASE 6F-3 DRY-RUN ONLY)"))
        self.stdout.write(self.style.WARNING("Policy Status: PROPOSED, NOT APPROVED (Zero destructive modifications)"))
        self.stdout.write(self.style.WARNING(f"Evaluation Timestamp: {now.isoformat()}"))
        self.stdout.write(self.style.WARNING("=" * 80))

        from apps.auditlog.retention_service import evaluate_data_retention_dry_run
        data = evaluate_data_retention_dry_run()

        self.stdout.write(f"\n{'MODEL / CATEGORY':<35} | {'PROPOSED WINDOW':<22} | {'CANDIDATES IDENTIFIED':<20}")
        self.stdout.write("-" * 83)
        for cat in data["categories"]:
            self.stdout.write(f"{cat['model']:<35} | {cat['proposed_retention']:<22} | {cat['candidate_count']:<20}")

        self.stdout.write("-" * 83)
        self.stdout.write(self.style.SUCCESS("\nEVALUATION SUMMARY:"))
        self.stdout.write("  - Mode: DRY-RUN ONLY (Non-destructive)")
        self.stdout.write("  - Actual records deleted or mutated: 0")
        self.stdout.write(f"  - Total Candidates Identified: {data['total_candidates']}")
        self.stdout.write("  - Destructive execution path: DISABLED pending formal stakeholder policy approval.")
        self.stdout.write(self.style.SUCCESS("=" * 80 + "\n"))
