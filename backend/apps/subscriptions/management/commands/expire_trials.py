"""Management command to expire overdue trial subscriptions."""

from django.core.management.base import BaseCommand

from apps.subscriptions.services import expire_trial_subscriptions


class Command(BaseCommand):
    help = "Expire trial subscriptions whose trial_ends_at is in the past."

    def handle(self, *args, **options):
        expired_count = expire_trial_subscriptions()
        self.stdout.write(
            self.style.SUCCESS(f"Successfully expired {expired_count} trial subscription(s).")
        )
