"""Management command to run the DB-backed async background worker (Phase 3 Async Workers).

Usage:
  python manage.py run_worker             # Continuous loop
  python manage.py run_worker --once      # Process currently queued jobs and exit
"""

import time
from django.core.management.base import BaseCommand
from apps.notifications.queue import process_next_queued_job


class Command(BaseCommand):
    help = "Run the VibeConnect background job queue worker for notifications and bulk import."

    def add_arguments(self, parser):
        parser.add_argument(
            "--once",
            action="store_true",
            help="Process all currently queued jobs and exit.",
        )
        parser.add_argument(
            "--poll-interval",
            type=float,
            default=2.0,
            help="Polling interval in seconds when the queue is idle (default: 2.0s).",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Optional maximum number of jobs to process before exiting.",
        )

    def handle(self, *args, **options):
        once = options["once"]
        poll_interval = options["poll_interval"]
        limit = options["limit"]

        self.stdout.write(self.style.SUCCESS("Starting VibeConnect Background Worker..."))

        processed_count = 0
        try:
            while True:
                found_job = process_next_queued_job()
                if found_job:
                    processed_count += 1
                    self.stdout.write(f"Processed background job #{processed_count}")
                    if limit and processed_count >= limit:
                        self.stdout.write(self.style.SUCCESS(f"Reached job limit ({limit}). Exiting."))
                        break
                else:
                    if once:
                        self.stdout.write(self.style.SUCCESS(f"Queue idle. Completed {processed_count} jobs. Exiting (--once)."))
                        break
                    time.sleep(poll_interval)
        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING(f"\nWorker stopped by user. Total processed: {processed_count}"))
