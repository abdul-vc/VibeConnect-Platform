"""Phase 5G Stage 2 Tests: Dead-Letter Replay & Recovery.

Focused tests strictly validating the 5G-2 dead-letter replay contract:
1. DEAD_LETTER replay succeeds: canonical provisioning execution transitions job to COMPLETED, failure to RESOLVED.
2. Successful replay resolves the failure and attributes resolved_by to the Platform Owner actor.
3. Failed replay follows existing retry/permanent classification (transient -> RETRY_SCHEDULED, permanent -> DEAD_LETTER).
4. Replay preserves previous attempt history and creates sequential next attempt.
5. Unauthorized actor (non-platform-owner / unauthenticated) is rejected.
6. Concurrent duplicate replay is safely prevented via row-level locking.
"""

import concurrent.futures
from decimal import Decimal
import unittest.mock as mock
import uuid

from django.contrib.auth import get_user_model
from django.db import connection, transaction
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
from apps.integration_hub.retry_service import replay_dead_letter_failure
from apps.organizations.models import (
    MembershipStatus,
    MembershipType,
    Organization,
    OrganizationMembership,
    OrganizationStatus,
)
from apps.product_registry.models import CatalogStatus, Product

User = get_user_model()


class Stage2DeadLetterReplayTestCase(TestCase):
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

        self.regular_user = User.objects.create_user(
            email=f"member_{uuid.uuid4().hex[:6]}@vibeconnect.local",
            password="TestPassword123!",
            full_name="Regular Member",
            is_active=True,
        )

        self.org = Organization.objects.create(
            name="Stage 2 Test Org",
            code=f"s2-{uuid.uuid4().hex[:6]}",
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
    # 1. DEAD_LETTER Replay Succeeds
    # -------------------------------------------------------------------------

    def test_01_dead_letter_replay_succeeds(self):
        """Replaying a DEAD_LETTER failure executes canonical provisioning and completes."""
        job = ProvisioningJob.objects.create(
            instance=self.instance,
            organization=self.org,
            action=ProvisioningAction.PROVISION,
            status=ProvisioningJobStatus.FAILED,
        )
        failure = IntegrationFailure.objects.create(
            job=job,
            failure_code="SERVICE_UNAVAILABLE",
            failure_type=FailureType.TRANSIENT,
            status=FailureStatus.DEAD_LETTER,
            retry_count=3,
            max_retries=3,
        )

        replayed = replay_dead_letter_failure(failure.id, actor=self.owner, client=self.mock_client)

        self.assertEqual(replayed.status, FailureStatus.RESOLVED)
        self.assertIsNotNone(replayed.resolved_at)
        self.assertEqual(replayed.resolved_by, self.owner)

        job.refresh_from_db()
        self.assertEqual(job.status, ProvisioningJobStatus.COMPLETED)
        self.assertIsNotNone(job.completed_at)

        # Successful attempt recorded
        attempts = list(replayed.attempts.order_by("attempt_number"))
        self.assertEqual(len(attempts), 1)
        self.assertEqual(attempts[0].outcome, AttemptOutcome.SUCCESS)
        self.assertEqual(attempts[0].attempt_number, 1)

    # -------------------------------------------------------------------------
    # 2. Replay of Non-DEAD_LETTER Fails Validation
    # -------------------------------------------------------------------------

    def test_02_replay_rejects_non_dead_letter_failures(self):
        """Replaying OPEN, RETRY_SCHEDULED, or RESOLVED failures raises ValueError."""
        job = ProvisioningJob.objects.create(
            instance=self.instance,
            organization=self.org,
            action=ProvisioningAction.PROVISION,
            status=ProvisioningJobStatus.FAILED,
        )

        for invalid_status in (FailureStatus.OPEN, FailureStatus.RETRY_SCHEDULED, FailureStatus.RESOLVED):
            failure = IntegrationFailure.objects.create(
                job=job,
                failure_code="ERR_TEST",
                status=invalid_status,
            )
            with self.assertRaises(ValueError) as ctx:
                replay_dead_letter_failure(failure.id, actor=self.owner, client=self.mock_client)
            self.assertIn("Only DEAD_LETTER failures can be replayed", str(ctx.exception))

    # -------------------------------------------------------------------------
    # 3. Failed Replay Follows Retry / Permanent Classification
    # -------------------------------------------------------------------------

    def test_03_failed_replay_handles_transient_and_permanent_failures(self):
        """Failed replay schedules retry if transient, or returns to DEAD_LETTER if permanent."""
        # 3a. Transient error: starts fresh retry cycle (attempt 1), schedules retry
        job_a = ProvisioningJob.objects.create(
            instance=self.instance,
            organization=self.org,
            action=ProvisioningAction.PROVISION,
            status=ProvisioningJobStatus.FAILED,
        )
        fail_a = IntegrationFailure.objects.create(
            job=job_a,
            failure_code="UPSTREAM_TIMEOUT",
            failure_type=FailureType.TRANSIENT,
            status=FailureStatus.DEAD_LETTER,
            retry_count=3,
        )

        mock_fail_client = mock.MagicMock()
        mock_fail_client.provision_tenant.side_effect = LmsConnectorRetryableError(
            "Service unavailable",
            failure_code="SERVICE_UNAVAILABLE",
        )

        res_a = replay_dead_letter_failure(fail_a.id, actor=self.owner, client=mock_fail_client)
        self.assertEqual(res_a.status, FailureStatus.RETRY_SCHEDULED)
        self.assertEqual(res_a.retry_count, 1)  # 1st retry of new recovery cycle
        self.assertIsNotNone(res_a.retry_after)

        job_a.refresh_from_db()
        self.assertEqual(job_a.status, ProvisioningJobStatus.RETRY_SCHEDULED)

        # 3b. Permanent error: immediately returns to DEAD_LETTER
        job_b = ProvisioningJob.objects.create(
            instance=self.instance,
            organization=self.org,
            action=ProvisioningAction.PROVISION,
            status=ProvisioningJobStatus.FAILED,
        )
        fail_b = IntegrationFailure.objects.create(
            job=job_b,
            failure_code="AUTHENTICATION_FAILED",
            failure_type=FailureType.PERMANENT,
            status=FailureStatus.DEAD_LETTER,
        )

        mock_perm_client = mock.MagicMock()
        mock_perm_client.provision_tenant.side_effect = LmsConnectorPermanentError(
            "Invalid credentials",
            failure_code="AUTHENTICATION_FAILED",
            status_code=401,
        )

        res_b = replay_dead_letter_failure(fail_b.id, actor=self.owner, client=mock_perm_client)
        self.assertEqual(res_b.status, FailureStatus.DEAD_LETTER)
        job_b.refresh_from_db()
        self.assertEqual(job_b.status, ProvisioningJobStatus.FAILED)

    # -------------------------------------------------------------------------
    # 4. Replay Preserves Previous Attempt History
    # -------------------------------------------------------------------------

    def test_04_replay_preserves_previous_attempts(self):
        """Replay adds sequential attempt records without erasing historical attempts."""
        job = ProvisioningJob.objects.create(
            instance=self.instance,
            organization=self.org,
            action=ProvisioningAction.PROVISION,
            status=ProvisioningJobStatus.FAILED,
        )
        failure = IntegrationFailure.objects.create(
            job=job,
            failure_code="SERVICE_UNAVAILABLE",
            status=FailureStatus.DEAD_LETTER,
            retry_count=3,
        )
        # Pre-existing historical attempts
        IntegrationFailureAttempt.objects.create(
            failure=failure,
            attempt_number=1,
            outcome=AttemptOutcome.FAILURE,
            failure_code="SERVICE_UNAVAILABLE",
            failure_detail="Initial timeout",
        )
        IntegrationFailureAttempt.objects.create(
            failure=failure,
            attempt_number=2,
            outcome=AttemptOutcome.FAILURE,
            failure_code="SERVICE_UNAVAILABLE",
            failure_detail="Second timeout",
        )

        replayed = replay_dead_letter_failure(failure.id, actor=self.owner, client=self.mock_client)
        self.assertEqual(replayed.status, FailureStatus.RESOLVED)

        attempts = list(replayed.attempts.order_by("attempt_number"))
        self.assertEqual(len(attempts), 3)
        self.assertEqual(attempts[0].attempt_number, 1)
        self.assertEqual(attempts[0].outcome, AttemptOutcome.FAILURE)
        self.assertEqual(attempts[1].attempt_number, 2)
        self.assertEqual(attempts[1].outcome, AttemptOutcome.FAILURE)
        self.assertEqual(attempts[2].attempt_number, 3)
        self.assertEqual(attempts[2].outcome, AttemptOutcome.SUCCESS)

    # -------------------------------------------------------------------------
    # 5. Authorization: API Rejects Non-Owner and Unauthenticated
    # -------------------------------------------------------------------------

    def test_05_api_replay_authorization(self):
        """API endpoint POST /api/v1/integration/failures/<id>/replay/ enforces Platform Owner permission."""
        job = ProvisioningJob.objects.create(
            instance=self.instance,
            organization=self.org,
            action=ProvisioningAction.PROVISION,
            status=ProvisioningJobStatus.FAILED,
        )
        failure = IntegrationFailure.objects.create(
            job=job,
            failure_code="ERR_AUTH",
            status=FailureStatus.DEAD_LETTER,
        )

        client = APIClient()

        # Unauthenticated -> 401
        res1 = client.post(f"/api/v1/integration/failures/{failure.id}/replay/")
        self.assertEqual(res1.status_code, 401)

        # Authenticated non-owner -> 403
        client.force_authenticate(user=self.regular_user)
        res2 = client.post(f"/api/v1/integration/failures/{failure.id}/replay/")
        self.assertEqual(res2.status_code, 403)

        # Authenticated Platform Owner -> 200
        client.force_authenticate(user=self.owner)
        with mock.patch("apps.integration_hub.provisioning_service.LmsConnectorClient") as mock_cls:
            mock_inst = mock_cls.return_value
            mock_inst.provision_tenant.return_value = {
                "lms_organization_id": "lms-org-99",
                "action_taken": "created",
            }
            res3 = client.post(f"/api/v1/integration/failures/{failure.id}/replay/")
            self.assertEqual(res3.status_code, 200)
            self.assertEqual(res3.data["status"], "resolved")


class Stage2ConcurrencyTestCase(TransactionTestCase):
    """Concurrency test for duplicate simultaneous replay requests."""

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
            name="Stage 2 Conc Org",
            code=f"s2c-{uuid.uuid4().hex[:6]}",
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
            name="LMS Test Connector",
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
    # 6. Concurrent Duplicate Replay Safely Prevented
    # -------------------------------------------------------------------------

    def test_06_concurrent_duplicate_replay_safely_prevented(self):
        """Simultaneous replay requests on the same DEAD_LETTER failure are safely serialized."""
        job = ProvisioningJob.objects.create(
            instance=self.instance,
            organization=self.org,
            action=ProvisioningAction.PROVISION,
            status=ProvisioningJobStatus.FAILED,
        )
        failure = IntegrationFailure.objects.create(
            job=job,
            failure_code="DEAD_LETTER_ERR",
            status=FailureStatus.DEAD_LETTER,
        )

        mock_client = mock.MagicMock()
        mock_client.provision_tenant.return_value = {
            "lms_organization_id": f"lms_org_{uuid.uuid4().hex[:8]}",
            "action_taken": "created",
        }

        results = []
        errors = []

        def _replay_worker():
            try:
                res = replay_dead_letter_failure(failure.id, actor=self.owner, client=mock_client)
                results.append(res)
            except ValueError as ve:
                errors.append(str(ve))
            finally:
                connection.close()

        threads = [
            concurrent.futures.ThreadPoolExecutor(max_workers=2).submit(_replay_worker),
            concurrent.futures.ThreadPoolExecutor(max_workers=2).submit(_replay_worker),
        ]
        concurrent.futures.wait(threads)

        # Exactly one worker succeeds in performing the replay; the other is rejected as not DEAD_LETTER
        self.assertEqual(len(results), 1)
        self.assertEqual(len(errors), 1)
        self.assertIn("Only DEAD_LETTER failures can be replayed", errors[0])

        failure.refresh_from_db()
        self.assertEqual(failure.status, FailureStatus.RESOLVED)

        # Exactly 1 attempt created across both workers (no duplicate side effects)
        self.assertEqual(failure.attempts.count(), 1)
