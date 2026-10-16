"""Phase 5G Stage 3 Tests: Explicit Integration Retry Runner.

Focused tests strictly validating the 5G-3 retry runner contract:
1. Eligible retry is executed (status=RETRY_SCHEDULED, retry_after <= now).
2. Future retry_after is skipped.
3. Retry limit option is respected.
4. Concurrent runners cannot claim the same retry (skip_locked concurrency safety).
5. Successful execution follows canonical completion (job -> COMPLETED, failure -> RESOLVED).
6. Retry failure follows canonical reschedule (transient) / dead-letter (permanent/exhausted) behavior.
"""

import concurrent.futures
from datetime import timedelta
import unittest.mock as mock
import uuid

from django.contrib.auth import get_user_model
from django.db import connection, transaction
from django.test import TestCase, TransactionTestCase
from django.utils import timezone

from apps.integration_hub.lms_connector import (
    LmsConnectorPermanentError,
    LmsConnectorRetryableError,
)
from apps.integration_hub.models import (
    AttemptOutcome,
    ConnectorInstance,
    ConnectorStatus,
    FailureStatus,
    FailureType,
    IntegrationConnector,
    IntegrationFailure,
    ProvisioningAction,
    ProvisioningJob,
    ProvisioningJobStatus,
)
from apps.integration_hub.retry_service import process_scheduled_retries
from apps.organizations.models import (
    MembershipStatus,
    MembershipType,
    Organization,
    OrganizationMembership,
    OrganizationStatus,
)
from apps.product_registry.models import CatalogStatus, Product

User = get_user_model()


class Stage3RetryRunnerTestCase(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            email=f"owner_{uuid.uuid4().hex[:6]}@vibeconnect.local",
            password="TestPassword123!",
            full_name="Platform Owner",
            is_active=True,
        )
        if hasattr(self.owner, "is_platform_owner"):
            self.owner.is_platform_owner = True
            self.owner.save(update_fields=["is_platform_owner"])

        self.org = Organization.objects.create(
            name="Stage 3 Test Org",
            code=f"s3-{uuid.uuid4().hex[:6]}",
            status=OrganizationStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )
        OrganizationMembership.objects.create(
            organization=self.org,
            user=self.owner,
            membership_type=MembershipType.MEMBER,
            status=MembershipStatus.ACTIVE,
            joined_at=timezone.now(),
        )
        self.product = Product.objects.create(
            code=f"lms-{uuid.uuid4().hex[:6]}",
            name="LMS Product",
            status=CatalogStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )
        self.connector = IntegrationConnector.objects.create(
            code=f"lms-conn-{uuid.uuid4().hex[:6]}",
            name="LMS Test Connector",
            product=self.product,
            status=ConnectorStatus.ACTIVE,
        )
        self.instance = ConnectorInstance.objects.create(
            connector=self.connector,
            organization=self.org,
            label="LMS Test Instance",
            credential_ref=f"vault://creds/{uuid.uuid4().hex[:6]}",
            config={"base_url": "https://lms.test.internal"},
        )

        self.mock_client = mock.MagicMock()
        self.mock_client.provision_tenant.return_value = {
            "lms_organization_id": f"lms_org_{uuid.uuid4().hex[:8]}",
            "action_taken": "created",
        }

    # -------------------------------------------------------------------------
    # 1. Eligible Retry Is Executed
    # -------------------------------------------------------------------------

    def test_01_eligible_retry_is_executed(self):
        """Eligible scheduled retry (due now) is claimed and processed by runner."""
        job = ProvisioningJob.objects.create(
            instance=self.instance,
            organization=self.org,
            action=ProvisioningAction.PROVISION,
            status=ProvisioningJobStatus.RETRY_SCHEDULED,
        )
        failure = IntegrationFailure.objects.create(
            job=job,
            failure_code="SERVICE_UNAVAILABLE",
            failure_type=FailureType.TRANSIENT,
            status=FailureStatus.RETRY_SCHEDULED,
            retry_count=1,
            max_retries=3,
            retry_after=timezone.now() - timedelta(seconds=30),  # In the past
        )

        stats = process_scheduled_retries(limit=10, client=self.mock_client)

        self.assertEqual(stats["scanned"], 1)
        self.assertEqual(stats["claimed"], 1)
        self.assertEqual(stats["executed"], 1)
        self.assertEqual(stats["completed"], 1)

        job.refresh_from_db()
        failure.refresh_from_db()

        self.assertEqual(job.status, ProvisioningJobStatus.COMPLETED)
        self.assertEqual(failure.status, FailureStatus.RESOLVED)

    # -------------------------------------------------------------------------
    # 2. Future Retry After Is Skipped
    # -------------------------------------------------------------------------

    def test_02_future_retry_after_is_skipped(self):
        """Failures with retry_after in the future are not claimed or executed."""
        job = ProvisioningJob.objects.create(
            instance=self.instance,
            organization=self.org,
            action=ProvisioningAction.PROVISION,
            status=ProvisioningJobStatus.RETRY_SCHEDULED,
        )
        failure = IntegrationFailure.objects.create(
            job=job,
            failure_code="UPSTREAM_TIMEOUT",
            status=FailureStatus.RETRY_SCHEDULED,
            retry_count=1,
            max_retries=3,
            retry_after=timezone.now() + timedelta(hours=1),  # In the future
        )

        stats = process_scheduled_retries(limit=10, client=self.mock_client)

        self.assertEqual(stats["scanned"], 0)
        self.assertEqual(stats["claimed"], 0)
        self.assertEqual(stats["executed"], 0)

        job.refresh_from_db()
        failure.refresh_from_db()

        self.assertEqual(job.status, ProvisioningJobStatus.RETRY_SCHEDULED)
        self.assertEqual(failure.status, FailureStatus.RETRY_SCHEDULED)

    # -------------------------------------------------------------------------
    # 3. Retry Limit Is Respected
    # -------------------------------------------------------------------------

    def test_03_retry_limit_is_respected(self):
        """Runner processes at most the requested --limit of eligible retries."""
        now = timezone.now()
        for i in range(5):
            job = ProvisioningJob.objects.create(
                instance=self.instance,
                organization=self.org,
                action=ProvisioningAction.PROVISION,
                status=ProvisioningJobStatus.RETRY_SCHEDULED,
            )
            IntegrationFailure.objects.create(
                job=job,
                failure_code=f"ERR_{i}",
                status=FailureStatus.RETRY_SCHEDULED,
                retry_count=1,
                max_retries=3,
                retry_after=now - timedelta(minutes=10 - i),
            )

        # Process with limit=2
        stats = process_scheduled_retries(limit=2, client=self.mock_client)

        self.assertEqual(stats["scanned"], 2)
        self.assertEqual(stats["claimed"], 2)
        self.assertEqual(stats["executed"], 2)
        self.assertEqual(stats["completed"], 2)

        # Exactly 3 remain in RETRY_SCHEDULED
        remaining_count = IntegrationFailure.objects.filter(
            status=FailureStatus.RETRY_SCHEDULED
        ).count()
        self.assertEqual(remaining_count, 3)

    # -------------------------------------------------------------------------
    # 5. Successful Execution Follows Canonical Completion
    # -------------------------------------------------------------------------

    def test_05_successful_execution_records_attempt_and_completes(self):
        """Runner execution records an auditable SUCCESS attempt and resolves the failure."""
        job = ProvisioningJob.objects.create(
            instance=self.instance,
            organization=self.org,
            action=ProvisioningAction.PROVISION,
            status=ProvisioningJobStatus.RETRY_SCHEDULED,
        )
        failure = IntegrationFailure.objects.create(
            job=job,
            failure_code="TEMPORARY_ERROR",
            status=FailureStatus.RETRY_SCHEDULED,
            retry_count=1,
            max_retries=3,
            retry_after=timezone.now() - timedelta(seconds=10),
        )

        stats = process_scheduled_retries(limit=10, client=self.mock_client)
        self.assertEqual(stats["completed"], 1)

        failure.refresh_from_db()
        self.assertEqual(failure.status, FailureStatus.RESOLVED)
        attempts = list(failure.attempts.order_by("attempt_number"))
        self.assertEqual(len(attempts), 1)
        self.assertEqual(attempts[0].outcome, AttemptOutcome.SUCCESS)

    # -------------------------------------------------------------------------
    # 6. Retry Failure Follows Canonical Reschedule / Dead-Letter
    # -------------------------------------------------------------------------

    def test_06_retry_failure_follows_canonical_reschedule_and_dead_letter(self):
        """Runner follows canonical retry rules: transient -> rescheduled, permanent -> dead_letter."""
        # 6a: Transient failure is rescheduled with incremented retry_count
        job_transient = ProvisioningJob.objects.create(
            instance=self.instance,
            organization=self.org,
            action=ProvisioningAction.PROVISION,
            status=ProvisioningJobStatus.RETRY_SCHEDULED,
        )
        fail_transient = IntegrationFailure.objects.create(
            job=job_transient,
            failure_code="UPSTREAM_TIMEOUT",
            failure_type=FailureType.TRANSIENT,
            status=FailureStatus.RETRY_SCHEDULED,
            retry_count=1,
            max_retries=3,
            retry_after=timezone.now() - timedelta(seconds=10),
        )

        mock_transient_client = mock.MagicMock()
        mock_transient_client.provision_tenant.side_effect = LmsConnectorRetryableError(
            "Gateway timeout",
            failure_code="GATEWAY_TIMEOUT",
        )

        stats_a = process_scheduled_retries(limit=10, client=mock_transient_client)
        self.assertEqual(stats_a["rescheduled"], 1)

        fail_transient.refresh_from_db()
        self.assertEqual(fail_transient.status, FailureStatus.RETRY_SCHEDULED)
        self.assertEqual(fail_transient.retry_count, 2)
        self.assertGreater(fail_transient.retry_after, timezone.now())

        # 6b: Permanent failure (or exhausted retries) moves to DEAD_LETTER
        job_perm = ProvisioningJob.objects.create(
            instance=self.instance,
            organization=self.org,
            action=ProvisioningAction.PROVISION,
            status=ProvisioningJobStatus.RETRY_SCHEDULED,
        )
        fail_perm = IntegrationFailure.objects.create(
            job=job_perm,
            failure_code="INVALID_CREDENTIALS",
            failure_type=FailureType.PERMANENT,
            status=FailureStatus.RETRY_SCHEDULED,
            retry_count=1,
            max_retries=3,
            retry_after=timezone.now() - timedelta(seconds=10),
        )

        mock_perm_client = mock.MagicMock()
        mock_perm_client.provision_tenant.side_effect = LmsConnectorPermanentError(
            "Invalid credentials",
            failure_code="INVALID_CREDENTIALS",
            status_code=401,
        )

        stats_b = process_scheduled_retries(limit=10, client=mock_perm_client)
        self.assertEqual(stats_b["dead_lettered"], 1)

        fail_perm.refresh_from_db()
        job_perm.refresh_from_db()
        self.assertEqual(fail_perm.status, FailureStatus.DEAD_LETTER)
        self.assertEqual(job_perm.status, ProvisioningJobStatus.FAILED)

    def test_07_management_command_invokes_runner_cleanly(self):
        """Management command process_integration_retries executes bounded batch cleanly."""
        from io import StringIO
        from django.core.management import call_command

        out = StringIO()
        call_command("process_integration_retries", limit=10, once=True, stdout=out)
        output_str = out.getvalue()
        self.assertIn("Retry processing completed:", output_str)
        self.assertIn("Scanned:", output_str)
        self.assertIn("Completed:", output_str)



class Stage3ConcurrencyTestCase(TransactionTestCase):
    """Concurrency test ensuring multiple runners cannot claim the same retry."""

    def setUp(self):
        self.owner = User.objects.create_user(
            email=f"conc_{uuid.uuid4().hex[:6]}@vibeconnect.local",
            password="TestPassword123!",
            full_name="Platform Owner",
            is_active=True,
        )
        if hasattr(self.owner, "is_platform_owner"):
            self.owner.is_platform_owner = True
            self.owner.save(update_fields=["is_platform_owner"])

        self.org = Organization.objects.create(
            name="Stage 3 Conc Org",
            code=f"s3c-{uuid.uuid4().hex[:6]}",
            status=OrganizationStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )
        OrganizationMembership.objects.create(
            organization=self.org,
            user=self.owner,
            membership_type=MembershipType.MEMBER,
            status=MembershipStatus.ACTIVE,
            joined_at=timezone.now(),
        )
        self.product = Product.objects.create(
            code=f"lms-{uuid.uuid4().hex[:6]}",
            name="LMS Product",
            status=CatalogStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )
        self.connector = IntegrationConnector.objects.create(
            code=f"lms-conc-{uuid.uuid4().hex[:6]}",
            name="LMS Conc Connector",
            product=self.product,
            status=ConnectorStatus.ACTIVE,
        )
        self.instance = ConnectorInstance.objects.create(
            connector=self.connector,
            organization=self.org,
            label="LMS Conc Instance",
            credential_ref=f"vault://creds/{uuid.uuid4().hex[:6]}",
            config={"base_url": "https://lms.test.internal"},
        )

    # -------------------------------------------------------------------------
    # 4. Concurrent Runners Cannot Claim Same Retry
    # -------------------------------------------------------------------------

    def test_04_concurrent_runners_cannot_claim_same_retry(self):
        """Simultaneous runner invocations safely serialize via skip_locked."""
        job = ProvisioningJob.objects.create(
            instance=self.instance,
            organization=self.org,
            action=ProvisioningAction.PROVISION,
            status=ProvisioningJobStatus.RETRY_SCHEDULED,
        )
        failure = IntegrationFailure.objects.create(
            job=job,
            failure_code="CONC_RETRY_ERR",
            status=FailureStatus.RETRY_SCHEDULED,
            retry_count=1,
            max_retries=3,
            retry_after=timezone.now() - timedelta(seconds=10),
        )

        mock_client = mock.MagicMock()
        mock_client.provision_tenant.return_value = {
            "lms_organization_id": f"lms_org_{uuid.uuid4().hex[:8]}",
            "action_taken": "created",
        }

        all_stats = []

        def _runner_worker():
            try:
                stats = process_scheduled_retries(limit=10, client=mock_client)
                all_stats.append(stats)
            finally:
                connection.close()

        threads = [
            concurrent.futures.ThreadPoolExecutor(max_workers=2).submit(_runner_worker),
            concurrent.futures.ThreadPoolExecutor(max_workers=2).submit(_runner_worker),
        ]
        concurrent.futures.wait(threads)

        total_claimed = sum(s["claimed"] for s in all_stats)
        total_completed = sum(s["completed"] for s in all_stats)

        # Exactly 1 worker claimed and executed the retry; the other skipped it
        self.assertEqual(total_claimed, 1)
        self.assertEqual(total_completed, 1)

        failure.refresh_from_db()
        self.assertEqual(failure.status, FailureStatus.RESOLVED)

        # Exactly 1 attempt created across both workers (no duplicate side effects)
        self.assertEqual(failure.attempts.count(), 1)
