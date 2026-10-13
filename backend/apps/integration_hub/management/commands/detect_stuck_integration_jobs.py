"""Management command: detect_stuck_integration_jobs.

Scans and detects stuck or orphaned provisioning jobs and failures.
Supports bounded limits and configurable age thresholds.
Does NOT run as a daemon. Explicit invocation only.
"""

from django.core.management.base import BaseCommand

from apps.integration_hub.stuck_job_service import detect_stuck_provisioning_jobs


class Command(BaseCommand):
    help = "Detect stuck and orphaned integration provisioning jobs."

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=50,
            help="Maximum number of candidate jobs to scan (default: 50).",
        )
        parser.add_argument(
            "--once",
            action="store_true",
            default=True,
            help="Execute a single scan run and exit (default behavior).",
        )
        parser.add_argument(
            "--queued-threshold",
            type=int,
            default=None,
            dest="queued_threshold",
            help="Override age threshold in seconds for stuck QUEUED jobs.",
        )
        parser.add_argument(
            "--processing-threshold",
            type=int,
            default=None,
            dest="processing_threshold",
            help="Override age threshold in seconds for stuck PROCESSING jobs.",
        )

    def handle(self, *args, **options):
        limit = options.get("limit", 50)
        queued_thresh = options.get("queued_threshold")
        processing_thresh = options.get("processing_threshold")

        self.stdout.write(f"Scanning for stuck and orphaned provisioning jobs (limit={limit})...")

        results = detect_stuck_provisioning_jobs(
            queued_threshold_seconds=queued_thresh,
            processing_threshold_seconds=processing_thresh,
            limit=limit,
        )

        summary = results["summary"]
        self.stdout.write(
            f"Stuck Job Detection Summary:\n"
            f"  Stuck QUEUED:              {summary['stuck_queued']}\n"
            f"  Stuck PROCESSING:          {summary['stuck_processing']}\n"
            f"  Orphaned:                  {summary['orphaned']}\n"
            f"  Total Stuck or Orphaned:   {summary['total_stuck_or_orphaned']}\n"
            f"  Healthy QUEUED:            {summary['healthy_queued']}\n"
            f"  Healthy PROCESSING:        {summary['healthy_processing']}\n"
            f"  Healthy RETRY_SCHEDULED:   {summary['healthy_retry_scheduled']}"
        )

        stuck_jobs = results.get("stuck_jobs", [])
        if stuck_jobs:
            self.stdout.write("\nStuck / Orphaned Provisioning Jobs:")
            for j in stuck_jobs:
                self.stdout.write(
                    f"  - ID: {j['job_id']} | Category: {j['category']} | "
                    f"Status: {j['current_status']} | Age: {j['age_seconds']}s | "
                    f"Action: {j['recommended_recovery_action']}\n"
                    f"    Reason: {j['reason']}"
                )

        orphaned_failures = results.get("orphaned_failures", [])
        if orphaned_failures:
            self.stdout.write("\nOrphaned Failures:")
            for f in orphaned_failures:
                self.stdout.write(
                    f"  - Failure ID: {f['failure_id']} | Category: {f['category']} | "
                    f"Status: {f['current_status']} | Reason: {f['reason']}"
                )
