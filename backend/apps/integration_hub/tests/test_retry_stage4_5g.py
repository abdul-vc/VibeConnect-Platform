"""Phase 5G Stage 4 Tests: Stuck & Orphaned Provisioning Job Detection / Safe Recovery.

Strictly validates the 5G-4 contract:
1. Healthy queued job is not classified as stuck.
2. Old queued job is classified as stuck.
3. Old processing job is classified as stuck.
4. Valid retry-scheduled job is not falsely classified as stuck.
5. Orphan / inconsistent state is detected.
6. Explicit recovery behaves safely for the supported recoverable case (reexecute vs fail, protected live job guard).
7. Recovery cannot trigger duplicate concurrent execution.
"""

import concurrent.futures
from datetime import timedelta
import unittest.mock as mock
import uuid

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import connection, transaction
from django.test import TestCase, TransactionTestCase
from django.utils import timezone

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
from apps.integration_hub.provisioning_service import ProvisioningServiceError
from apps.integration_hub.stuck_job_service import (
    JobClassification,
    classify_provisioning_job,
    detect_stuck_provisioning_jobs,
    recover_stuck_provisioning_job,
)
from apps.organizations.models import (
    MembershipStatus,
    MembershipType,
    Organization,
    OrganizationMembership,
    OrganizationStatus,
)
from apps.product_registry.models import CatalogStatus, Product

User = get_user_model()


class Stage4DetectionAndRecoveryTestCase(TestCase):
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
            name="Stage 4 Test Org",
            code=f"s4-{uuid.uuid4().hex[:6]}",
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
    # 1. Healthy QUEUED job is not classified as stuck
    # -------------------------------------------------------------------------

    def test_01_healthy_queued_job_not_classified_as_stuck(self):
        """A freshly queued job is classified as NORMAL_QUEUED and not stuck."""
        job = ProvisioningJob.objects.create(
            instance=self.instance,
            organization=self.org,
            action=ProvisioningAction.PROVISION,
            status=ProvisioningJobStatus.QUEUED,
        )

        classification = classify_provisioning_job(job)
        self.assertEqual(classification["category"], JobClassification.NORMAL_QUEUED)
        self.assertFalse(classification["is_stuck_or_orphaned"])

        scan_result = detect_stuck_provisioning_jobs(organization_id=self.org.id)
        self.assertEqual(scan_result["summary"]["healthy_queued"], 1)
        self.assertEqual(scan_result["summary"]["stuck_queued"], 0)
        self.assertEqual(len(scan_result["stuck_jobs"]), 0)

    # -------------------------------------------------------------------------
    # 2. Old QUEUED job is classified as stuck
    # -------------------------------------------------------------------------

    def test_02_old_queued_job_classified_as_stuck(self):
        """A job queued beyond the queued age threshold is classified as STUCK_QUEUED."""
        job = ProvisioningJob.objects.create(
            instance=self.instance,
            organization=self.org,
            action=ProvisioningAction.PROVISION,
            status=ProvisioningJobStatus.QUEUED,
        )
        # Simulate age: 2 hours ago
        stale_time = timezone.now() - timedelta(hours=2)
        ProvisioningJob.objects.filter(pk=job.id).update(created_at=stale_time, updated_at=stale_time)
        job.refresh_from_db()

        classification = classify_provisioning_job(job, queued_threshold_seconds=1800)
        self.assertEqual(classification["category"], JobClassification.STUCK_QUEUED)
        self.assertTrue(classification["is_stuck_or_orphaned"])
        self.assertTrue(classification["is_recoverable"])
        self.assertEqual(classification["recommended_recovery_action"], "reexecute")

        scan_result = detect_stuck_provisioning_jobs(organization_id=self.org.id)
        self.assertEqual(scan_result["summary"]["stuck_queued"], 1)
        self.assertEqual(scan_result["summary"]["total_stuck_or_orphaned"], 1)
        self.assertEqual(scan_result["stuck_jobs"][0]["job_id"], str(job.id))

    # -------------------------------------------------------------------------
    # 3. Old PROCESSING job is classified as stuck
    # -------------------------------------------------------------------------

    def test_03_old_processing_job_classified_as_stuck(self):
        """A job in PROCESSING state beyond the processing threshold is classified as STUCK_PROCESSING."""
        job = ProvisioningJob.objects.create(
            instance=self.instance,
            organization=self.org,
            action=ProvisioningAction.PROVISION,
            status=ProvisioningJobStatus.PROCESSING,
        )
        # Simulate stuck processing: 10 minutes ago
        stale_time = timezone.now() - timedelta(minutes=10)
        ProvisioningJob.objects.filter(pk=job.id).update(created_at=stale_time, updated_at=stale_time)
        job.refresh_from_db()

        classification = classify_provisioning_job(job, processing_threshold_seconds=300)
        self.assertEqual(classification["category"], JobClassification.STUCK_PROCESSING)
        self.assertTrue(classification["is_stuck_or_orphaned"])
        self.assertTrue(classification["is_recoverable"])
        # Safe default recovery: do not blindly reexecute; require safe fail/review
        self.assertEqual(classification["recommended_recovery_action"], "fail")

        scan_result = detect_stuck_provisioning_jobs(organization_id=self.org.id)
        self.assertEqual(scan_result["summary"]["stuck_processing"], 1)
        self.assertEqual(scan_result["summary"]["total_stuck_or_orphaned"], 1)
        self.assertEqual(scan_result["stuck_jobs"][0]["job_id"], str(job.id))

    # -------------------------------------------------------------------------
    # 4. Valid RETRY_SCHEDULED job is not falsely classified as stuck
    # -------------------------------------------------------------------------

    def test_04_valid_retry_scheduled_job_not_falsely_classified_as_stuck(self):
        """A RETRY_SCHEDULED job with a valid corresponding failure is healthy, not stuck."""
        job = ProvisioningJob.objects.create(
            instance=self.instance,
            organization=self.org,
            action=ProvisioningAction.PROVISION,
            status=ProvisioningJobStatus.RETRY_SCHEDULED,
        )
        IntegrationFailure.objects.create(
            job=job,
            failure_code="TEMPORARY_NETWORK_ERROR",
            status=FailureStatus.RETRY_SCHEDULED,
            retry_count=1,
            max_retries=3,
            retry_after=timezone.now() + timedelta(minutes=5),
        )

        classification = classify_provisioning_job(job)
        self.assertEqual(classification["category"], JobClassification.NORMAL_RETRY_SCHEDULED)
        self.assertFalse(classification["is_stuck_or_orphaned"])

        scan_result = detect_stuck_provisioning_jobs(organization_id=self.org.id)
        self.assertEqual(scan_result["summary"]["healthy_retry_scheduled"], 1)
        self.assertEqual(scan_result["summary"]["total_stuck_or_orphaned"], 0)

    # -------------------------------------------------------------------------
    # 5. Orphan / Inconsistent state is detected
    # -------------------------------------------------------------------------

    def test_05_orphan_inconsistent_state_detected(self):
        """Jobs with impossible combinations or missing relations are classified as ORPHANED."""
        # 5a. Job marked RETRY_SCHEDULED but NO failure record exists
        job_no_failure = ProvisioningJob.objects.create(
            instance=self.instance,
            organization=self.org,
            action=ProvisioningAction.PROVISION,
            status=ProvisioningJobStatus.RETRY_SCHEDULED,
        )
        cls_a = classify_provisioning_job(job_no_failure)
        self.assertEqual(cls_a["category"], JobClassification.ORPHANED)
        self.assertTrue(cls_a["is_stuck_or_orphaned"])
        self.assertIn("no corresponding RETRY_SCHEDULED IntegrationFailure", cls_a["reason"])

        # 5b. Job marked RETRY_SCHEDULED but failure is in DEAD_LETTER (inconsistent state)
        job_dead_failure = ProvisioningJob.objects.create(
            instance=self.instance,
            organization=self.org,
            action=ProvisioningAction.PROVISION,
            status=ProvisioningJobStatus.RETRY_SCHEDULED,
        )
        IntegrationFailure.objects.create(
            job=job_dead_failure,
            failure_code="PERM_ERR",
            status=FailureStatus.DEAD_LETTER,
            failure_type=FailureType.PERMANENT,
        )
        cls_b = classify_provisioning_job(job_dead_failure)
        self.assertEqual(cls_b["category"], JobClassification.ORPHANED)
        self.assertTrue(cls_b["is_stuck_or_orphaned"])

        # 5c. IntegrationFailure marked RETRY_SCHEDULED with an event but NO job
        from apps.integration_hub.models import IntegrationEvent
        event = IntegrationEvent.objects.create(
            instance=self.instance,
            event_type="test.orphan.event",
            event_key=f"orphan-{uuid.uuid4().hex[:8]}",
            occurred_at=timezone.now(),
        )
        orphan_failure = IntegrationFailure.objects.create(
            event=event,
            job=None,
            failure_code="ORPHAN_FAILURE_NO_JOB",
            status=FailureStatus.RETRY_SCHEDULED,
            failure_type=FailureType.TRANSIENT,
            retry_after=timezone.now() + timedelta(minutes=5),
        )
        scan = detect_stuck_provisioning_jobs()
        orphan_ids = [f["failure_id"] for f in scan.get("orphaned_failures", [])]
        self.assertIn(str(orphan_failure.id), orphan_ids)

    # -------------------------------------------------------------------------
    # 6. Explicit recovery behaves safely
    # -------------------------------------------------------------------------

    def test_06_explicit_recovery_behaves_safely(self):
        """Explicit recovery safely executes or fails jobs and protects live audit records."""
        # 6a: STUCK_QUEUED re-execution
        stuck_queued_job = ProvisioningJob.objects.create(
            instance=self.instance,
            organization=self.org,
            action=ProvisioningAction.PROVISION,
            status=ProvisioningJobStatus.QUEUED,
        )
        stale_time = timezone.now() - timedelta(hours=1)
        ProvisioningJob.objects.filter(pk=stuck_queued_job.id).update(created_at=stale_time)

        rec_result = recover_stuck_provisioning_job(
            stuck_queued_job.id,
            action="reexecute",
            actor=self.owner,
            client=self.mock_client,
        )
        self.assertTrue(rec_result["success"])
        self.assertEqual(rec_result["action_taken"], "reexecuted")
        stuck_queued_job.refresh_from_db()
        self.assertEqual(stuck_queued_job.status, ProvisioningJobStatus.COMPLETED)
        self.mock_client.provision_tenant.assert_called_once()

        # 6b: STUCK_PROCESSING safe fail transition
        stuck_proc_job = ProvisioningJob.objects.create(
            instance=self.instance,
            organization=self.org,
            action=ProvisioningAction.PROVISION,
            status=ProvisioningJobStatus.PROCESSING,
        )
        ProvisioningJob.objects.filter(pk=stuck_proc_job.id).update(
            created_at=stale_time, updated_at=stale_time
        )

        fail_result = recover_stuck_provisioning_job(
            stuck_proc_job.id,
            action="fail",
            actor=self.owner,
        )
        self.assertTrue(fail_result["success"])
        self.assertEqual(fail_result["action_taken"], "marked_failed")
        stuck_proc_job.refresh_from_db()
        self.assertEqual(stuck_proc_job.status, ProvisioningJobStatus.FAILED)

        # Failure record was created and dead-lettered
        failure = IntegrationFailure.objects.filter(job=stuck_proc_job).first()
        self.assertIsNotNone(failure)
        self.assertEqual(failure.failure_code, "STUCK_PROCESSING_TIMEOUT")
        self.assertEqual(failure.status, FailureStatus.DEAD_LETTER)
        self.assertEqual(failure.failure_type, FailureType.PERMANENT)
        self.assertEqual(failure.attempts.count(), 1)
        self.assertEqual(failure.attempts.first().outcome, AttemptOutcome.FAILURE)

        # 6c: Generic state-based eligibility guard rejects recovery of healthy jobs
        healthy_job = ProvisioningJob.objects.create(
            instance=self.instance,
            organization=self.org,
            action=ProvisioningAction.PROVISION,
            status=ProvisioningJobStatus.QUEUED,
        )
        with self.assertRaises(ProvisioningServiceError) as ctx:
            recover_stuck_provisioning_job(healthy_job.id, action="reexecute")
        self.assertEqual(ctx.exception.code, "JOB_NOT_STUCK")
        healthy_job.refresh_from_db()
        self.assertEqual(healthy_job.status, ProvisioningJobStatus.QUEUED)

    # -------------------------------------------------------------------------
    # 8. Management command execution check
    # -------------------------------------------------------------------------

    def test_08_management_command_detects_stuck_jobs(self):
        """Management command detect_stuck_integration_jobs executes cleanly."""
        from io import StringIO

        out = StringIO()
        call_command(
            "detect_stuck_integration_jobs",
            limit=10,
            once=True,
            stdout=out,
        )
        output_str = out.getvalue()
        self.assertIn("Scanning for stuck and orphaned provisioning jobs", output_str)
        self.assertIn("Stuck Job Detection Summary:", output_str)
        self.assertIn("Stuck QUEUED:", output_str)
        self.assertIn("Stuck PROCESSING:", output_str)


class Stage4ConcurrencyTestCase(TransactionTestCase):
    """Concurrency test ensuring multiple recoveries cannot execute duplicate operations."""

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
            name="Stage 4 Conc Org",
            code=f"s4c-{uuid.uuid4().hex[:6]}",
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
    # 7. Recovery cannot trigger duplicate concurrent execution
    # -------------------------------------------------------------------------

    def test_07_recovery_cannot_trigger_duplicate_concurrent_execution(self):
        """Simultaneous recovery invocations safely serialize via select_for_update."""
        stuck_job = ProvisioningJob.objects.create(
            instance=self.instance,
            organization=self.org,
            action=ProvisioningAction.PROVISION,
            status=ProvisioningJobStatus.QUEUED,
        )
        stale_time = timezone.now() - timedelta(hours=2)
        ProvisioningJob.objects.filter(pk=stuck_job.id).update(created_at=stale_time)

        mock_client = mock.MagicMock()
        mock_client.provision_tenant.return_value = {
            "lms_organization_id": f"lms_org_{uuid.uuid4().hex[:8]}",
            "action_taken": "created",
        }

        results = []

        def _recovery_worker():
            try:
                res = recover_stuck_provisioning_job(
                    stuck_job.id,
                    action="reexecute",
                    client=mock_client,
                )
                results.append(res)
            finally:
                connection.close()

        threads = [
            concurrent.futures.ThreadPoolExecutor(max_workers=2).submit(_recovery_worker),
            concurrent.futures.ThreadPoolExecutor(max_workers=2).submit(_recovery_worker),
        ]
        concurrent.futures.wait(threads)

        actions_taken = [r["action_taken"] for r in results]

        # One worker re-executed the job; the other received a noop due to completed status
        self.assertIn("reexecuted", actions_taken)
        self.assertIn("noop", actions_taken)

        stuck_job.refresh_from_db()
        self.assertEqual(stuck_job.status, ProvisioningJobStatus.COMPLETED)

        # Downstream client must only be called once across both concurrent requests
        self.assertEqual(mock_client.provision_tenant.call_count, 1)
