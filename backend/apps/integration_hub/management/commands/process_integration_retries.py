"""Management command: process_integration_retries.

Processes a bounded batch of eligible scheduled integration retries.
Eligible retries: IntegrationFailure.status == RETRY_SCHEDULED with retry_after <= current time.
Uses database row-level locking (select_for_update with skip_locked=True) for concurrency safety.
Executes canonically through execute_provisioning_job without duplicating provisioning logic.
"""

from django.core.management.base import BaseCommand

from apps.integration_hub.retry_service import process_scheduled_retries


class Command(BaseCommand):
    help = "Process a bounded batch of eligible scheduled integration retries."

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=50,
            help="Maximum number of scheduled retries to claim and execute in this invocation (default: 50).",
        )
        parser.add_argument(
            "--once",
            action="store_true",
            default=True,
            help="Process a single bounded batch and exit (default behavior).",
        )

    def handle(self, *args, **options):
        limit = options.get("limit", 50)
        self.stdout.write(f"Scanning for eligible integration retries (limit={limit})...")

        stats = process_scheduled_retries(limit=limit)

        self.stdout.write(
            f"Retry processing completed:\n"
            f"  Scanned:       {stats['scanned']}\n"
            f"  Claimed:       {stats['claimed']}\n"
            f"  Executed:      {stats['executed']}\n"
            f"  Completed:     {stats['completed']}\n"
            f"  Rescheduled:   {stats['rescheduled']}\n"
            f"  Dead-lettered: {stats['dead_lettered']}\n"
            f"  Skipped:       {stats['skipped']}"
        )
