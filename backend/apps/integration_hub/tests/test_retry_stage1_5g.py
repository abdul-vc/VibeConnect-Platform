"""Phase 5G Stage 1 Tests: Retry Foundation Hardening.

Covers all 5G-1 requirements:
1. IntegrationFailureAttempt model creation & lifecycle
2. Sequential attempt numbering
3. Successful attempt recording & resolution
4. Failed attempt recording & dead-letter transitions
5. Secret sanitization in failure details & attempts
6. Bounded jitter calculation & max delay enforcement
7. Deterministic jitter testing via dependency injection
8. State consistency: ProvisioningJobStatus.RETRY_SCHEDULED vs FAILED vs COMPLETED
9. Unique constraint on (failure, attempt_number)
10. Idempotency preservation on completed jobs
11. Serializer exposure of attempts history
"""

from decimal import Decimal
import unittest.mock as mock
import uuid

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase, TransactionTestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.integration_hub.lms_connector import (
    LmsConnectorPermanentError,
    LmsConnectorRetryableError,
)
from apps.integration_hub.models import (
    AttemptOutcome,
    ConnectorInstance,
    ConnectorStatus,
    ExternalTenantMapping,
    FailureStatus,
    FailureType,
    IntegrationConnector,
    IntegrationFailure,
    IntegrationFailureAttempt,
    ProvisioningAction,
    ProvisioningJob,
    ProvisioningJobStatus,
)
from apps.integration_hub.provisioning_service import execute_provisioning_job
from apps.integration_hub.retry_service import (
    compute_backoff_delay,
    record_failure_attempt,
    sanitize_diagnostic_detail,
    schedule_failure_retry,
)
from apps.organizations.models import MembershipStatus, MembershipType, Organization, OrganizationMembership, OrganizationStatus
from apps.product_registry.models import CatalogStatus, Product

User = get_user_model()


class RetryStage1TestCase(TestCase):
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
            name="Stage 1 Test Org",
            code=f"s1-{uuid.uuid4().hex[:6]}",
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
            code=f"lms_conn_{uuid.uuid4().hex[:6]}",
            name="LMS Connector",
            product=self.product,
            status=ConnectorStatus.ACTIVE,
        )
        self.instance = ConnectorInstance.objects.create(
            connector=self.connector,
            organization=self.org,
            label="LMS Instance",
            status=ConnectorStatus.ACTIVE,
            config={"base_url": "https://lms.test.internal", "secret": "sec_test123"},
        )
        self.mock_client = mock.MagicMock()

    # -------------------------------------------------------------------------
    # 1. Attempt Record Creation & Lifecycle on Transient Failure
    # -------------------------------------------------------------------------

    def test_01_transient_failure_creates_attempt_record(self):
        """Transient failure transitions job to RETRY_SCHEDULED and creates attempt 1."""
        self.mock_client.provision_tenant.side_effect = LmsConnectorRetryableError(
            message="Temporary network timeout to LMS",
            failure_code="UPSTREAM_TIMEOUT",
            status_code=504,
        )

        job = ProvisioningJob.objects.create(
            instance=self.instance,
            organization=self.org,
            action=ProvisioningAction.PROVISION,
            status=ProvisioningJobStatus.QUEUED,
        )

        with self.assertRaises(LmsConnectorRetryableError):
            execute_provisioning_job(job, client=self.mock_client)

        job.refresh_from_db()
        self.assertEqual(job.status, ProvisioningJobStatus.RETRY_SCHEDULED)

        failure = IntegrationFailure.objects.get(job=job)
        self.assertEqual(failure.status, FailureStatus.RETRY_SCHEDULED)
        self.assertEqual(failure.failure_code, "UPSTREAM_TIMEOUT")
        self.assertEqual(failure.failure_type, FailureType.TRANSIENT)
        self.assertEqual(failure.retry_count, 1)

        attempts = failure.attempts.all()
        self.assertEqual(attempts.count(), 1)
        att = attempts.first()
        self.assertEqual(att.attempt_number, 1)
        self.assertEqual(att.outcome, AttemptOutcome.FAILURE)
        self.assertEqual(att.failure_code, "UPSTREAM_TIMEOUT")
        self.assertEqual(att.http_status, 504)
        self.assertIsNotNone(att.started_at)
        self.assertIsNotNone(att.completed_at)
        self.assertIsNotNone(att.retry_after)
        self.assertGreater(att.retry_after, timezone.now())

    # -------------------------------------------------------------------------
    # 2. Sequential Attempt Numbering
    # -------------------------------------------------------------------------

    def test_02_sequential_attempt_numbering(self):
        """Repeated transient executions number attempts sequentially (1, 2, 3)."""
        self.mock_client.provision_tenant.side_effect = LmsConnectorRetryableError(
            message="Upstream unavailable",
            failure_code="SERVICE_UNAVAILABLE",
            status_code=503,
        )

        job = ProvisioningJob.objects.create(
            instance=self.instance,
            organization=self.org,
            action=ProvisioningAction.PROVISION,
            status=ProvisioningJobStatus.QUEUED,
        )

        # Attempt 1
        with self.assertRaises(LmsConnectorRetryableError):
            execute_provisioning_job(job, client=self.mock_client)

        # Attempt 2
        with self.assertRaises(LmsConnectorRetryableError):
            execute_provisioning_job(job, client=self.mock_client)

        # Attempt 3
        with self.assertRaises(LmsConnectorRetryableError):
            execute_provisioning_job(job, client=self.mock_client)

        failure = IntegrationFailure.objects.get(job=job)
        self.assertEqual(failure.retry_count, 3)
        self.assertEqual(failure.attempts.count(), 3)
        attempt_numbers = list(failure.attempts.values_list("attempt_number", flat=True))
        self.assertEqual(attempt_numbers, [1, 2, 3])

    # -------------------------------------------------------------------------
    # 3. Retry Exhaustion Transitions to FAILED and Records Terminal Attempt
    # -------------------------------------------------------------------------

    def test_03_retry_exhaustion_transitions_to_failed(self):
        """Exhausting max_retries (3) on 4th attempt sets job FAILED, failure DEAD_LETTER."""
        self.mock_client.provision_tenant.side_effect = LmsConnectorRetryableError(
            message="Upstream gateway timeout",
            failure_code="UPSTREAM_TIMEOUT",
            status_code=504,
        )

        job = ProvisioningJob.objects.create(
            instance=self.instance,
            organization=self.org,
            action=ProvisioningAction.PROVISION,
            status=ProvisioningJobStatus.QUEUED,
        )

        # 4 consecutive failures
        for _ in range(4):
            with self.assertRaises(LmsConnectorRetryableError):
                execute_provisioning_job(job, client=self.mock_client)

        job.refresh_from_db()
        self.assertEqual(job.status, ProvisioningJobStatus.FAILED)

        failure = IntegrationFailure.objects.get(job=job)
        self.assertEqual(failure.status, FailureStatus.DEAD_LETTER)
        self.assertEqual(failure.retry_count, 3)
        self.assertEqual(failure.attempts.count(), 4)

        final_attempt = failure.attempts.order_by("attempt_number").last()
        self.assertEqual(final_attempt.attempt_number, 4)
        self.assertEqual(final_attempt.outcome, AttemptOutcome.FAILURE)
        self.assertIsNone(final_attempt.retry_after)

    # -------------------------------------------------------------------------
    # 4. Successful Retry Records Success Attempt and Resolves Failure
    # -------------------------------------------------------------------------

    def test_04_successful_retry_records_success_attempt_and_resolves(self):
        """Failure on attempt 1 followed by success on attempt 2 logs success attempt and resolves."""
        # Attempt 1: Fails
        self.mock_client.provision_tenant.side_effect = LmsConnectorRetryableError(
            message="Connection dropped",
            failure_code="CONNECTION_RESET",
        )

        job = ProvisioningJob.objects.create(
            instance=self.instance,
            organization=self.org,
            action=ProvisioningAction.PROVISION,
            status=ProvisioningJobStatus.QUEUED,
        )

        with self.assertRaises(LmsConnectorRetryableError):
            execute_provisioning_job(job, client=self.mock_client)

        # Attempt 2: Recovers
        self.mock_client.provision_tenant.side_effect = None
        self.mock_client.provision_tenant.return_value = {
            "status": "success",
            "action_taken": "created",
            "lms_organization_id": 777,
        }

        execute_provisioning_job(job, client=self.mock_client)

        job.refresh_from_db()
        self.assertEqual(job.status, ProvisioningJobStatus.COMPLETED)
        self.assertIsNotNone(job.completed_at)

        failure = IntegrationFailure.objects.get(job=job)
        self.assertEqual(failure.status, FailureStatus.RESOLVED)
        self.assertIsNotNone(failure.resolved_at)

        attempts = list(failure.attempts.order_by("attempt_number"))
        self.assertEqual(len(attempts), 2)
        self.assertEqual(attempts[0].attempt_number, 1)
        self.assertEqual(attempts[0].outcome, AttemptOutcome.FAILURE)
        self.assertEqual(attempts[1].attempt_number, 2)
        self.assertEqual(attempts[1].outcome, AttemptOutcome.SUCCESS)
        self.assertEqual(attempts[1].failure_code, "")

    # -------------------------------------------------------------------------
    # 5. Secret Sanitization in Attempt Records
    # -------------------------------------------------------------------------

    def test_05_attempt_sanitizes_secrets_in_detail(self):
        """Sanitizer masks tokens, bearer headers, and passwords from attempt details."""
        sensitive_error = (
            "HTTP 401 Authorization failed: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.xyz "
            "password=SuperSecretPassword123! token: sec_live_998877"
        )
        self.mock_client.provision_tenant.side_effect = LmsConnectorRetryableError(
            message="Auth retryable timeout",
            failure_code="UPSTREAM_TIMEOUT",
            detail=sensitive_error,
        )

        job = ProvisioningJob.objects.create(
            instance=self.instance,
            organization=self.org,
            action=ProvisioningAction.PROVISION,
            status=ProvisioningJobStatus.QUEUED,
        )

        with self.assertRaises(LmsConnectorRetryableError):
            execute_provisioning_job(job, client=self.mock_client)

        failure = IntegrationFailure.objects.get(job=job)
        att = failure.attempts.first()

        forbidden_strings = ["Bearer ", "SuperSecretPassword123!", "sec_live_998877"]
        for forbidden in forbidden_strings:
            self.assertNotIn(forbidden, att.failure_detail)
            self.assertNotIn(forbidden, failure.failure_detail)
        self.assertIn("[REDACTED]", att.failure_detail)

    # -------------------------------------------------------------------------
    # 6. Bounded Jitter Calculation & Deterministic Testing
    # -------------------------------------------------------------------------

    def test_06_bounded_jitter_within_percentage_range(self):
        """Jitter produces deterministic bounded delay using dependency-injected random_func."""
        # Baseline raw delay for attempt 1 (base=60): 60 seconds
        raw_delay = compute_backoff_delay(attempt=1, base_seconds=60, jitter=False)
        self.assertEqual(raw_delay, 60)

        # Min jitter (random_func returning 0.0 with 20% jitter) -> 60 * 0.8 = 48
        min_delay = compute_backoff_delay(
            attempt=1, base_seconds=60, jitter=True, jitter_pct=0.2, random_func=lambda: 0.0
        )
        self.assertEqual(min_delay, 48)

        # Max jitter (random_func returning 1.0 with 20% jitter) -> 60 * 1.2 = 72
        max_delay = compute_backoff_delay(
            attempt=1, base_seconds=60, jitter=True, jitter_pct=0.2, random_func=lambda: 1.0
        )
        self.assertEqual(max_delay, 72)

        # Midpoint jitter (random_func returning 0.5 with 20% jitter) -> 60 * 1.0 = 60
        mid_delay = compute_backoff_delay(
            attempt=1, base_seconds=60, jitter=True, jitter_pct=0.2, random_func=lambda: 0.5
        )
        self.assertEqual(mid_delay, 60)

    def test_07_jitter_preserves_maximum_cap(self):
        """Jitter delay never exceeds max_seconds cap even at high attempt numbers."""
        capped = compute_backoff_delay(
            attempt=10,
            base_seconds=60,
            max_seconds=300,
            jitter=True,
            random_func=lambda: 1.0,
        )
        self.assertLessEqual(capped, 300)
        self.assertEqual(capped, 300)

    # -------------------------------------------------------------------------
    # 8. Unique Attempt Number Constraint
    # -------------------------------------------------------------------------

    def test_08_unique_attempt_number_constraint(self):
        """Database enforces uniqueness on (failure, attempt_number)."""
        job = ProvisioningJob.objects.create(
            instance=self.instance,
            organization=self.org,
            action=ProvisioningAction.PROVISION,
        )
        failure = IntegrationFailure.objects.create(job=job, failure_code="ERR_TEST")

        IntegrationFailureAttempt.objects.create(
            failure=failure,
            attempt_number=1,
            outcome=AttemptOutcome.FAILURE,
        )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                IntegrationFailureAttempt.objects.create(
                    failure=failure,
                    attempt_number=1,
                    outcome=AttemptOutcome.SUCCESS,
                )

    # -------------------------------------------------------------------------
    # 9. Idempotent Re-execution on Completed Job
    # -------------------------------------------------------------------------

    def test_09_idempotent_reexecution_does_not_create_duplicate_attempts(self):
        """Executing an already COMPLETED job is a no-op and creates no new attempts."""
        job = ProvisioningJob.objects.create(
            instance=self.instance,
            organization=self.org,
            action=ProvisioningAction.PROVISION,
            status=ProvisioningJobStatus.COMPLETED,
        )
        failure = IntegrationFailure.objects.create(
            job=job,
            failure_code="PREV_ERR",
            status=FailureStatus.RESOLVED,
        )
        IntegrationFailureAttempt.objects.create(
            failure=failure,
            attempt_number=1,
            outcome=AttemptOutcome.SUCCESS,
        )

        executed = execute_provisioning_job(job, client=self.mock_client)
        self.assertEqual(executed.id, job.id)
        self.assertEqual(self.mock_client.provision_tenant.call_count, 0)
        self.assertEqual(failure.attempts.count(), 1)

    # -------------------------------------------------------------------------
    # 10. Permanent Error Immediately Fails and Records Attempt
    # -------------------------------------------------------------------------

    def test_10_permanent_error_immediately_marks_failed(self):
        """Permanent error (401) sets job FAILED, failure DEAD_LETTER, and records attempt."""
        self.mock_client.provision_tenant.side_effect = LmsConnectorPermanentError(
            message="Invalid M2M credentials",
            failure_code="AUTHENTICATION_FAILED",
            status_code=401,
        )

        job = ProvisioningJob.objects.create(
            instance=self.instance,
            organization=self.org,
            action=ProvisioningAction.PROVISION,
            status=ProvisioningJobStatus.QUEUED,
        )

        with self.assertRaises(LmsConnectorPermanentError):
            execute_provisioning_job(job, client=self.mock_client)

        job.refresh_from_db()
        self.assertEqual(job.status, ProvisioningJobStatus.FAILED)

        failure = IntegrationFailure.objects.get(job=job)
        self.assertEqual(failure.status, FailureStatus.DEAD_LETTER)
        self.assertEqual(failure.failure_type, FailureType.PERMANENT)
        self.assertIsNone(failure.retry_after)

        att = failure.attempts.first()
        self.assertIsNotNone(att)
        self.assertEqual(att.attempt_number, 1)
        self.assertEqual(att.http_status, 401)
        self.assertEqual(att.outcome, AttemptOutcome.FAILURE)
        self.assertIsNone(att.retry_after)

    # -------------------------------------------------------------------------
    # 11. Serializer Exposes Attempts History
    # -------------------------------------------------------------------------

    def test_11_serializer_includes_attempts(self):
        """Failure detail API exposes nested attempts list."""
        client = APIClient()
        client.force_authenticate(user=self.owner)

        job = ProvisioningJob.objects.create(
            instance=self.instance,
            organization=self.org,
            action=ProvisioningAction.PROVISION,
        )
        failure = IntegrationFailure.objects.create(job=job, failure_code="TEST_API_ERR")
        IntegrationFailureAttempt.objects.create(
            failure=failure,
            attempt_number=1,
            outcome=AttemptOutcome.FAILURE,
            failure_code="TEST_API_ERR",
            failure_detail="Diagnostic detail message",
            http_status=503,
        )

        res = client.get(f"/api/v1/integration/failures/{failure.id}/")
        self.assertEqual(res.status_code, 200)
        self.assertIn("attempts", res.data)
        self.assertEqual(len(res.data["attempts"]), 1)
        attempt_data = res.data["attempts"][0]
        self.assertEqual(attempt_data["attempt_number"], 1)
        self.assertEqual(attempt_data["outcome"], "failure")
        self.assertEqual(attempt_data["http_status"], 503)


class RetryStage1ConcurrencyTestCase(TransactionTestCase):
    """Real concurrency tests validating that simultaneous executions safely obtain next attempt numbers."""

    def setUp(self):
        self.owner = User.objects.create_user(
            email=f"conc_owner_{uuid.uuid4().hex[:6]}@vibeconnect.local",
            password="TestPassword123!",
            full_name="Platform Owner",
            is_active=True,
        )
        if hasattr(self.owner, "is_platform_owner"):
            self.owner.is_platform_owner = True
            self.owner.save(update_fields=["is_platform_owner"])
        self.org = Organization.objects.create(
            name="Concurrency Test Org",
            code=f"conc-{uuid.uuid4().hex[:6]}",
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

    def test_12_concurrent_attempt_allocations_safely_obtain_sequential_numbers(self):
        """Concurrent calls to record_failure_attempt safely obtain next sequential attempt numbers."""
        import concurrent.futures
        from django.db import connection

        job = ProvisioningJob.objects.create(
            instance=self.instance,
            organization=self.org,
            action=ProvisioningAction.PROVISION,
        )
        failure = IntegrationFailure.objects.create(
            job=job,
            failure_code="CONC_ERR",
            failure_detail="Concurrent execution test",
        )

        num_threads = 5
        now = timezone.now()

        def _record_worker(idx):
            try:
                att = record_failure_attempt(
                    failure=failure,
                    started_at=now,
                    completed_at=now,
                    outcome=AttemptOutcome.FAILURE,
                    failure_code="CONC_ERR",
                    failure_detail=f"Worker {idx} attempt token=secret_{idx}",
                    http_status=503,
                )
                return att.attempt_number
            finally:
                connection.close()

        with concurrent.futures.ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [executor.submit(_record_worker, i) for i in range(num_threads)]
            results = [f.result() for f in futures]

        # 1. All threads must have successfully obtained a unique attempt number
        self.assertEqual(len(results), num_threads)
        self.assertEqual(sorted(results), list(range(1, num_threads + 1)))

        # 2. In database, persisted attempts are exactly 1..num_threads with no duplicates and no gaps
        persisted = list(
            IntegrationFailureAttempt.objects.filter(failure=failure)
            .order_by("attempt_number")
            .values_list("attempt_number", flat=True)
        )
        self.assertEqual(persisted, list(range(1, num_threads + 1)))

        # 3. Verify secrets sanitized even under concurrent execution
        for attempt in IntegrationFailureAttempt.objects.filter(failure=failure):
            self.assertNotIn("secret_", attempt.failure_detail)
            self.assertIn("[REDACTED]", attempt.failure_detail)

