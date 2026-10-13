"""Tests for Bulk Import Domain Services (Phase 3D & 3E)."""

from datetime import timedelta
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.bulk_import.models import BulkImportJob, BulkImportStatus, RowValidationState
from apps.bulk_import.services import (
    BulkImportError,
    BulkImportErrorCode,
    DuplicateJobError,
    MaxRowsExceededError,
    commit_import_job,
    get_job_reconciliation_report,
    is_error_recoverable,
    parse_and_stage_job,
    retry_failed_rows,
)
from apps.identity.models import UserStatus
from apps.invitations.models import InvitationStatus, UserInvitation
from apps.organizations.models import MembershipStatus, MembershipType, Organization, OrganizationMembership

PlatformUser = get_user_model()


class BulkImportServicesTests(TestCase):
    def setUp(self):
        self.owner = PlatformUser.objects.create_superuser(
            email="owner@vibeconnect.test",
            password="SecurePassword123!",
            full_name="Platform Owner",
        )
        self.org = Organization.objects.create(
            code="acme_corp",
            name="Acme Corporation",
            status="active",
            created_by=self.owner,
            updated_by=self.owner,
        )

    def test_successful_full_job_commit(self):
        csv_data = (
            "email,full_name,membership_type\n"
            "user1@acme.test,User One,member\n"
            "user2@acme.test,User Two,member\n"
        )
        job = parse_and_stage_job(
            actor=self.owner,
            organization=self.org,
            idempotency_key="job-key-001",
            raw_content=csv_data,
            content_type="csv",
        )
        self.assertEqual(job.total_rows, 2)
        self.assertEqual(job.valid_rows, 2)
        self.assertEqual(job.invalid_rows, 0)
        self.assertEqual(job.status, BulkImportStatus.VALIDATED)

        # Commit job
        committed_job = commit_import_job(job.id, self.owner)
        self.assertEqual(committed_job.status, BulkImportStatus.COMPLETED)
        self.assertEqual(committed_job.committed_rows, 2)
        self.assertEqual(committed_job.failed_rows, 0)

        # Verify invitations created
        self.assertEqual(
            UserInvitation.objects.filter(organization=self.org).count(),
            2,
        )

    def test_duplicate_rows_in_file_detected(self):
        csv_data = (
            "email,full_name,membership_type\n"
            "dup@acme.test,Duplicate First,member\n"
            "dup@acme.test,Duplicate Second,member\n"
        )
        job = parse_and_stage_job(
            actor=self.owner,
            organization=self.org,
            idempotency_key="job-key-dup",
            raw_content=csv_data,
            content_type="csv",
        )
        self.assertEqual(job.total_rows, 2)
        self.assertEqual(job.valid_rows, 1)
        self.assertEqual(job.invalid_rows, 1)

        row2 = job.rows.get(row_number=2)
        self.assertEqual(row2.validation_state, RowValidationState.INVALID)
        self.assertEqual(row2.error_code, BulkImportErrorCode.DUPLICATE_ROW_IN_FILE)

    def test_idempotency_key_duplicate_rejection(self):
        csv_data = "email,full_name\nsingle@acme.test,Single User\n"
        parse_and_stage_job(
            actor=self.owner,
            organization=self.org,
            idempotency_key="key-unique-123",
            raw_content=csv_data,
        )
        with self.assertRaises(DuplicateJobError):
            parse_and_stage_job(
                actor=self.owner,
                organization=self.org,
                idempotency_key="key-unique-123",
                raw_content=csv_data,
            )

    def test_max_row_limit_enforcement(self):
        # Generate 1001 rows
        lines = ["email,full_name"]
        for i in range(1001):
            lines.append(f"user{i}@acme.test,User {i}")
        big_csv = "\n".join(lines)

        with self.assertRaises(MaxRowsExceededError):
            parse_and_stage_job(
                actor=self.owner,
                organization=self.org,
                idempotency_key="key-too-big",
                raw_content=big_csv,
            )

    def test_existing_user_and_membership_conflict_detection(self):
        # 1. Existing active member
        existing_active = PlatformUser.objects.create_user(
            email="existing_active@acme.test",
            password="SecurePassword123!",
        )
        OrganizationMembership.objects.create(
            organization=self.org,
            user=existing_active,
            membership_type=MembershipType.MEMBER,
            status=MembershipStatus.ACTIVE,
            joined_at=timezone.now(),
        )

        # 2. Existing suspended member
        existing_suspended = PlatformUser.objects.create_user(
            email="existing_suspended@acme.test",
            password="SecurePassword123!",
        )
        OrganizationMembership.objects.create(
            organization=self.org,
            user=existing_suspended,
            membership_type=MembershipType.MEMBER,
            status=MembershipStatus.SUSPENDED,
            joined_at=timezone.now(),
        )

        # 3. Disabled platform user
        PlatformUser.objects.create_user(
            email="disabled_user@acme.test",
            password="SecurePassword123!",
            status=UserStatus.DISABLED,
        )

        csv_data = (
            "email,full_name\n"
            "existing_active@acme.test,Active Member\n"
            "existing_suspended@acme.test,Suspended Member\n"
            "disabled_user@acme.test,Disabled User\n"
            "clean_new@acme.test,Clean New User\n"
        )
        job = parse_and_stage_job(
            actor=self.owner,
            organization=self.org,
            idempotency_key="key-conflict-test",
            raw_content=csv_data,
        )

        self.assertEqual(job.total_rows, 4)
        self.assertEqual(job.valid_rows, 1)
        self.assertEqual(job.invalid_rows, 3)

        row1 = job.rows.get(row_number=1)
        self.assertEqual(row1.error_code, BulkImportErrorCode.ALREADY_ACTIVE_MEMBER)

        row2 = job.rows.get(row_number=2)
        self.assertEqual(row2.error_code, BulkImportErrorCode.MEMBERSHIP_SUSPENDED)

        row3 = job.rows.get(row_number=3)
        self.assertEqual(row3.error_code, BulkImportErrorCode.USER_DISABLED)

        row4 = job.rows.get(row_number=4)
        self.assertEqual(row4.validation_state, RowValidationState.VALID)

    def test_pending_invitation_conflict_detection(self):
        # Create an active pending invitation
        UserInvitation.objects.create(
            organization=self.org,
            email="invited@acme.test",
            status=InvitationStatus.PENDING,
            token_hash="fake-hash-001",
            expires_at=timezone.now() + timedelta(days=5),
        )

        csv_data = "email,full_name\ninvited@acme.test,Invited User\n"
        job = parse_and_stage_job(
            actor=self.owner,
            organization=self.org,
            idempotency_key="key-pending-invite",
            raw_content=csv_data,
        )

        self.assertEqual(job.invalid_rows, 1)
        row = job.rows.first()
        self.assertEqual(row.error_code, BulkImportErrorCode.PENDING_INVITATION_EXISTS)

    def test_recoverable_vs_terminal_classification(self):
        self.assertTrue(is_error_recoverable(BulkImportErrorCode.COMMIT_FAILED))
        self.assertTrue(is_error_recoverable(BulkImportErrorCode.TRANSIENT_SERVICE_ERROR))
        self.assertFalse(is_error_recoverable(BulkImportErrorCode.INVALID_EMAIL))
        self.assertFalse(is_error_recoverable(BulkImportErrorCode.ALREADY_ACTIVE_MEMBER))
        self.assertFalse(is_error_recoverable(BulkImportErrorCode.DUPLICATE_ROW_IN_FILE))

    def test_retry_recoverable_only_and_rejection_of_terminal(self):
        csv_data = "email,full_name\nuser_retry@acme.test,Retry User\n"
        job = parse_and_stage_job(
            actor=self.owner,
            organization=self.org,
            idempotency_key="key-retry-test",
            raw_content=csv_data,
        )

        row = job.rows.first()
        # Mark row as failed with a terminal error code
        row.validation_state = RowValidationState.FAILED
        row.error_code = BulkImportErrorCode.ALREADY_ACTIVE_MEMBER
        row.error_message = "Already active member"
        row.save()

        job.failed_rows = 1
        job.valid_rows = 0
        job.status = BulkImportStatus.FAILED
        job.save()

        # Retrying terminal error should be rejected
        with self.assertRaises(BulkImportError) as ctx:
            retry_failed_rows(job.id, self.owner)
        self.assertEqual(ctx.exception.code, "NO_RETRYABLE_ROWS")

        # Now mark as recoverable error (transient failure)
        row.error_code = BulkImportErrorCode.COMMIT_FAILED
        row.save()

        # Retrying recoverable error succeeds
        retried_job = retry_failed_rows(job.id, self.owner)
        self.assertEqual(retried_job.status, BulkImportStatus.COMPLETED)
        self.assertEqual(retried_job.committed_rows, 1)
        self.assertEqual(retried_job.failed_rows, 0)

    def test_reconciliation_report(self):
        csv_data = (
            "email,full_name\n"
            "valid1@acme.test,Valid One\n"
            "valid2@acme.test,Valid Two\n"
            "invalid-email,Invalid Email\n"
        )
        job = parse_and_stage_job(
            actor=self.owner,
            organization=self.org,
            idempotency_key="key-reconcile-test",
            raw_content=csv_data,
        )
        commit_import_job(job.id, self.owner)

        report = get_job_reconciliation_report(job.id)
        self.assertEqual(report["job_id"], str(job.id))
        self.assertEqual(report["total_rows"], 3)
        self.assertEqual(report["committed_rows"], 2)
        self.assertEqual(report["invalid_rows"], 1)
        self.assertEqual(len(report["rows"]), 3)
        self.assertIn("error_code_breakdown", report)
        self.assertEqual(report["error_code_breakdown"].get(BulkImportErrorCode.INVALID_EMAIL), 1)
        self.assertFalse(report["can_retry"])

    def test_commit_api_returns_202_and_enqueues_job(self):
        """Item 3: Commit returns 202 Accepted and enqueues BackgroundJob."""
        from rest_framework.test import APIClient
        from rest_framework import status
        from apps.notifications.models import BackgroundJob, BackgroundJobStatus

        client = APIClient()
        client.force_authenticate(user=self.owner)

        csv_data = "email,full_name\nasync1@acme.test,Async One\n"
        job = parse_and_stage_job(
            actor=self.owner,
            organization=self.org,
            idempotency_key="key-async-commit",
            raw_content=csv_data,
        )

        resp = client.post(f"/api/v1/bulk-import/jobs/{job.id}/commit/")
        self.assertEqual(resp.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(resp.data["status"], BulkImportStatus.COMMITTING)

        # Check job enqueued in background_jobs
        bg_job = BackgroundJob.objects.filter(
            job_type="bulk_import_commit",
            status=BackgroundJobStatus.QUEUED,
        ).first()
        self.assertIsNotNone(bg_job)
        self.assertEqual(bg_job.payload.get("job_id"), str(job.id))

    def test_error_report_csv_download(self):
        """Item 3: CSV error-report download endpoint."""
        from rest_framework.test import APIClient
        from rest_framework import status

        client = APIClient()
        client.force_authenticate(user=self.owner)

        csv_data = "email,full_name\ninvalid-email,Invalid Guy\n"
        job = parse_and_stage_job(
            actor=self.owner,
            organization=self.org,
            idempotency_key="key-error-csv",
            raw_content=csv_data,
        )

        resp = client.get(f"/api/v1/bulk-import/jobs/{job.id}/error-report/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp["Content-Type"], "text/csv")
        self.assertIn("invalid-email", resp.content.decode("utf-8"))

    def test_permission_denial_without_bulk_import_manage(self):
        """Item 4: User without bulk_import.manage gets 403."""
        from rest_framework.test import APIClient
        from rest_framework import status

        regular_user = PlatformUser.objects.create_user(
            email="unauth@acme.test",
            password="SecurePassword123!",
            full_name="Unauth User",
        )
        client = APIClient()
        client.force_authenticate(user=regular_user)

        csv_data = "email,full_name\ntest@acme.test,Test\n"
        job = parse_and_stage_job(
            actor=self.owner,
            organization=self.org,
            idempotency_key="key-unauth-test",
            raw_content=csv_data,
        )

        resp = client.post(f"/api/v1/bulk-import/jobs/{job.id}/commit/")
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

