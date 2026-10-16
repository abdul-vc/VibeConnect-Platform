"""Bulk Import Domain Services (Phase 3D & 3E).

Provides staged row validation, cross-referencing against live identity,
membership, and invitation records, recoverable vs terminal error taxonomy,
resilient retry of recoverable rows, idempotency guarantees, and reconciliation reporting.
"""

import csv
import io
import json
import logging
from typing import Any
import uuid

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import validate_email
from django.db import models, transaction
from django.utils import timezone

from apps.access_control.models import Role
from apps.auditlog.models import AuditAction, AuditOperationSource, AuditTargetType
from apps.auditlog.services import record_audit_event
from apps.bulk_import.models import (
    BulkImportJob,
    BulkImportRow,
    BulkImportStatus,
    BulkImportType,
    RowValidationState,
)
from apps.identity.models import UserStatus
from apps.invitations.models import InvitationStatus, UserInvitation
from apps.invitations.services import (
    DuplicateInvitationError,
    InvitationValidationError,
    issue_invitation,
)
from apps.notifications.services import send as notification_send
from apps.organizations.models import (
    MembershipStatus,
    MembershipType,
    Organization,
    OrganizationMembership,
)

logger = logging.getLogger(__name__)
PlatformUser = get_user_model()

MAX_ROWS_PER_JOB = 1000


class BulkImportErrorCode:
    """Documented taxonomy of bulk import error codes (Phase 3E)."""

    # Terminal Data / Conflict Errors (Not retryable)
    MISSING_EMAIL = "MISSING_EMAIL"
    INVALID_EMAIL = "INVALID_EMAIL"
    DUPLICATE_ROW_IN_FILE = "DUPLICATE_ROW_IN_FILE"
    ALREADY_ACTIVE_MEMBER = "ALREADY_ACTIVE_MEMBER"
    PENDING_INVITATION_EXISTS = "PENDING_INVITATION_EXISTS"
    MEMBERSHIP_SUSPENDED = "MEMBERSHIP_SUSPENDED"
    USER_DISABLED = "USER_DISABLED"
    INVALID_MEMBERSHIP_TYPE = "INVALID_MEMBERSHIP_TYPE"
    ROLE_NOT_FOUND = "ROLE_NOT_FOUND"
    MISSING_ADMIN_ROLE = "MISSING_ADMIN_ROLE"
    MEMBER_CANNOT_HAVE_ROLE = "MEMBER_CANNOT_HAVE_ROLE"
    MEMBER_ALREADY_EXISTS = "MEMBER_ALREADY_EXISTS"
    DUPLICATE_INVITATION = "DUPLICATE_INVITATION"

    # Recoverable Transient Errors (Retryable)
    COMMIT_FAILED = "COMMIT_FAILED"
    NOTIFICATION_FAILED = "NOTIFICATION_FAILED"
    TRANSIENT_SERVICE_ERROR = "TRANSIENT_SERVICE_ERROR"
    LOCK_TIMEOUT = "LOCK_TIMEOUT"


TERMINAL_ERROR_CODES = {
    BulkImportErrorCode.MISSING_EMAIL,
    BulkImportErrorCode.INVALID_EMAIL,
    BulkImportErrorCode.DUPLICATE_ROW_IN_FILE,
    BulkImportErrorCode.ALREADY_ACTIVE_MEMBER,
    BulkImportErrorCode.PENDING_INVITATION_EXISTS,
    BulkImportErrorCode.MEMBERSHIP_SUSPENDED,
    BulkImportErrorCode.USER_DISABLED,
    BulkImportErrorCode.INVALID_MEMBERSHIP_TYPE,
    BulkImportErrorCode.ROLE_NOT_FOUND,
    BulkImportErrorCode.MISSING_ADMIN_ROLE,
    BulkImportErrorCode.MEMBER_CANNOT_HAVE_ROLE,
    BulkImportErrorCode.MEMBER_ALREADY_EXISTS,
    BulkImportErrorCode.DUPLICATE_INVITATION,
}

RECOVERABLE_ERROR_CODES = {
    BulkImportErrorCode.COMMIT_FAILED,
    BulkImportErrorCode.NOTIFICATION_FAILED,
    BulkImportErrorCode.TRANSIENT_SERVICE_ERROR,
    BulkImportErrorCode.LOCK_TIMEOUT,
}


def is_error_recoverable(error_code: str) -> bool:
    """Check if an error code represents a recoverable, transient failure."""
    return error_code in RECOVERABLE_ERROR_CODES


class BulkImportError(Exception):
    """Base exception for bulk import operations."""

    def __init__(self, message: str, code: str = "BULK_IMPORT_ERROR"):
        super().__init__(message)
        self.message = message
        self.code = code


class DuplicateJobError(BulkImportError):
    def __init__(self, message: str = "A job with this idempotency key already exists."):
        super().__init__(message, code="DUPLICATE_JOB")


class MaxRowsExceededError(BulkImportError):
    def __init__(self, message: str = f"File exceeds maximum allowed limit of {MAX_ROWS_PER_JOB} rows."):
        super().__init__(message, code="MAX_ROWS_EXCEEDED")


class EmptyJobError(BulkImportError):
    def __init__(self, message: str = "No data rows were found in the uploaded file."):
        super().__init__(message, code="EMPTY_JOB")


def parse_and_stage_job(
    *,
    actor: Any,
    organization: Organization,
    idempotency_key: str,
    raw_content: str,
    content_type: str = "csv",
) -> BulkImportJob:
    """Parse uploaded content, stage into rows, and run comprehensive Phase 3E validation.

    Cross-references against live platform users, organization memberships,
    and pending user invitations to detect conflicting state prior to commit.
    """
    clean_idempotency_key = idempotency_key.strip()
    if not clean_idempotency_key:
        raise BulkImportError("An idempotency key is required.", code="MISSING_IDEMPOTENCY_KEY")

    if BulkImportJob.objects.filter(idempotency_key=clean_idempotency_key).exists():
        raise DuplicateJobError()

    # Parse raw rows
    rows_data: list[dict[str, Any]] = []
    if content_type == "json":
        try:
            parsed = json.loads(raw_content)
            if not isinstance(parsed, list):
                raise ValueError("JSON root must be an array of objects.")
            rows_data = parsed
        except Exception as exc:
            raise BulkImportError(f"Failed to parse JSON content: {exc}", code="PARSE_ERROR")
    else:
        # CSV parsing
        try:
            reader = csv.DictReader(io.StringIO(raw_content.strip()))
            for row in reader:
                clean_row = {k.strip().lower(): v.strip() for k, v in row.items() if k}
                rows_data.append(clean_row)
        except Exception as exc:
            raise BulkImportError(f"Failed to parse CSV content: {exc}", code="PARSE_ERROR")

    if not rows_data:
        raise EmptyJobError()

    if len(rows_data) > MAX_ROWS_PER_JOB:
        raise MaxRowsExceededError()

    # Create job in validating status
    job = BulkImportJob.objects.create(
        organization=organization,
        import_type=BulkImportType.USERS_AND_MEMBERSHIPS,
        status=BulkImportStatus.VALIDATING,
        idempotency_key=clean_idempotency_key,
        created_by=actor,
        total_rows=len(rows_data),
    )

    seen_emails: set[str] = set()
    valid_count = 0
    invalid_count = 0

    staged_rows: list[BulkImportRow] = []

    for idx, row in enumerate(rows_data, start=1):
        raw_email = row.get("email", "").strip().lower()
        full_name = row.get("full_name") or row.get("name", "")
        membership_type = row.get("membership_type", "member").strip().lower()
        role_code = row.get("role_code", "").strip()

        payload = {
            "email": raw_email,
            "full_name": full_name,
            "membership_type": membership_type,
            "role_code": role_code,
        }

        err_code = ""
        err_msg = ""

        # 1. Validate email presence & syntax
        if not raw_email:
            err_code = BulkImportErrorCode.MISSING_EMAIL
            err_msg = "Email address is required."
        else:
            try:
                validate_email(raw_email)
            except DjangoValidationError:
                err_code = BulkImportErrorCode.INVALID_EMAIL
                err_msg = f"'{raw_email}' is not a valid email address."

        # 2. Check intra-file duplicate
        if not err_code:
            if raw_email in seen_emails:
                err_code = BulkImportErrorCode.DUPLICATE_ROW_IN_FILE
                err_msg = f"Duplicate email '{raw_email}' found in the same file."
            else:
                seen_emails.add(raw_email)

        # 3. Cross-reference: PlatformUser disabled state
        if not err_code:
            existing_user = PlatformUser.objects.filter(email__iexact=raw_email).first()
            if existing_user and getattr(existing_user, "status", None) == UserStatus.DISABLED:
                err_code = BulkImportErrorCode.USER_DISABLED
                err_msg = f"User '{raw_email}' is disabled at the platform level."

        # 4. Cross-reference: OrganizationMembership conflicts
        if not err_code:
            existing_membership = OrganizationMembership.objects.filter(
                organization=organization,
                user__email__iexact=raw_email,
            ).first()
            if existing_membership:
                if existing_membership.status == MembershipStatus.ACTIVE:
                    err_code = BulkImportErrorCode.ALREADY_ACTIVE_MEMBER
                    err_msg = f"User '{raw_email}' is already an active member of this organization."
                elif existing_membership.status == MembershipStatus.SUSPENDED:
                    err_code = BulkImportErrorCode.MEMBERSHIP_SUSPENDED
                    err_msg = f"User '{raw_email}' has a suspended membership in this organization."

        # 5. Cross-reference: Pending UserInvitation conflicts
        if not err_code:
            has_pending_invite = UserInvitation.objects.filter(
                organization=organization,
                email__iexact=raw_email,
                status=InvitationStatus.PENDING,
                expires_at__gt=timezone.now(),
            ).exists()
            if has_pending_invite:
                err_code = BulkImportErrorCode.PENDING_INVITATION_EXISTS
                err_msg = f"An active pending invitation already exists for '{raw_email}' in this organization."

        # 6. Validate membership type
        if not err_code:
            if membership_type not in MembershipType.values:
                err_code = BulkImportErrorCode.INVALID_MEMBERSHIP_TYPE
                err_msg = f"Membership type must be one of: {list(MembershipType.values)}."

        # 7. Validate role assignments
        if not err_code:
            if membership_type == MembershipType.TENANT_ADMIN:
                if role_code:
                    role_exists = (
                        Role.objects.filter(organization=organization, code=role_code).exists()
                        or Role.objects.filter(code=role_code, is_system_role=True).exists()
                    )
                    if not role_exists:
                        err_code = BulkImportErrorCode.ROLE_NOT_FOUND
                        err_msg = f"Role '{role_code}' does not exist for this organization."
            elif membership_type == MembershipType.MEMBER:
                if role_code:
                    err_code = BulkImportErrorCode.MEMBER_CANNOT_HAVE_ROLE
                    err_msg = f"Standard members cannot be assigned an administrative role '{role_code}'."

        if err_code:
            invalid_count += 1
            validation_state = RowValidationState.INVALID
        else:
            valid_count += 1
            validation_state = RowValidationState.VALID

        staged_rows.append(
            BulkImportRow(
                job=job,
                row_number=idx,
                validation_state=validation_state,
                payload_ref=payload,
                error_code=err_code,
                error_message=err_msg,
            )
        )

    BulkImportRow.objects.bulk_create(staged_rows)

    job.valid_rows = valid_count
    job.invalid_rows = invalid_count
    job.status = BulkImportStatus.VALIDATED
    job.save(update_fields=["valid_rows", "invalid_rows", "status", "updated_at"])

    # Record Audit Event
    record_audit_event(
        action=AuditAction.BULK_IMPORT_JOB_CREATED,
        target_type=AuditTargetType.BULK_IMPORT_JOB,
        target_id=job.id,
        target_repr=f"Bulk Import Job {job.id} for {organization.code}",
        actor=actor,
        organization_id=organization.id,
        operation_source=AuditOperationSource.INTERACTIVE,
        correlation_id=job.id,
        metadata={
            "job_id": str(job.id),
            "organization_id": str(organization.id),
            "total_rows": job.total_rows,
            "valid_rows": valid_count,
            "invalid_rows": invalid_count,
        },
    )

    return job


def commit_import_job(job_id: uuid.UUID | str, actor: Any) -> BulkImportJob:
    """Commit validated rows by issuing invitations and creating memberships.

    Resilient to partial failures: committed rows remain saved, failed rows are marked
    with clear terminal vs recoverable error codes. Handles race conditions gracefully.
    """
    job = (
        BulkImportJob.objects.select_related("organization")
        .prefetch_related("rows")
        .get(id=job_id)
    )

    if job.status not in (BulkImportStatus.VALIDATED, BulkImportStatus.FAILED):
        raise BulkImportError(
            f"Cannot commit job in '{job.status}' status. Job must be 'validated' or 'failed'.",
            code="INVALID_JOB_STATUS",
        )

    job.status = BulkImportStatus.COMMITTING
    job.save(update_fields=["status", "updated_at"])

    valid_rows = job.rows.filter(validation_state=RowValidationState.VALID).order_by("row_number")
    committed_delta = 0
    failed_delta = 0

    for row in valid_rows:
        payload = row.payload_ref
        email = payload.get("email")
        membership_type = payload.get("membership_type", "member")
        role_code = payload.get("role_code")

        role = None
        if role_code:
            role = (
                Role.objects.filter(organization=job.organization, code=role_code).first()
                or Role.objects.filter(code=role_code, is_system_role=True).first()
            )

        if not role and membership_type == MembershipType.TENANT_ADMIN:
            role = Role.objects.filter(code="system_tenant_admin", is_system_role=True).first()

        try:
            with transaction.atomic():
                issue_invitation(
                    organization=job.organization,
                    email=email,
                    role=role,
                    membership_type=membership_type,
                    invited_by=actor,
                )
            row.validation_state = RowValidationState.COMMITTED
            row.error_code = ""
            row.error_message = ""
            row.save(update_fields=["validation_state", "error_code", "error_message", "updated_at"])
            committed_delta += 1
        except DuplicateInvitationError as exc:
            # Race condition: invitation was issued between validation and commit
            row.validation_state = RowValidationState.FAILED
            row.error_code = BulkImportErrorCode.PENDING_INVITATION_EXISTS
            row.error_message = str(exc)
            row.save(update_fields=["validation_state", "error_code", "error_message", "updated_at"])
            failed_delta += 1
        except InvitationValidationError as exc:
            # Terminal data error
            row.validation_state = RowValidationState.FAILED
            row.error_code = exc.code or BulkImportErrorCode.INVALID_EMAIL
            row.error_message = str(exc)
            row.save(update_fields=["validation_state", "error_code", "error_message", "updated_at"])
            failed_delta += 1
        except Exception as exc:
            # Check if exception denotes a known error code or transient commit failure
            row.validation_state = RowValidationState.FAILED
            row.error_code = getattr(exc, "code", BulkImportErrorCode.COMMIT_FAILED)
            row.error_message = str(exc)
            row.save(update_fields=["validation_state", "error_code", "error_message", "updated_at"])
            failed_delta += 1

    job.committed_rows += committed_delta
    job.failed_rows += failed_delta
    job.valid_rows = job.rows.filter(validation_state=RowValidationState.VALID).count()

    if job.failed_rows > 0:
        job.status = BulkImportStatus.FAILED
    else:
        job.status = BulkImportStatus.COMPLETED
        job.completed_at = timezone.now()

    job.save(
        update_fields=[
            "committed_rows",
            "failed_rows",
            "valid_rows",
            "status",
            "completed_at",
            "updated_at",
        ]
    )

    # Dispatch completion notification
    try:
        notification_send(
            template_code="bulk_import_completed",
            recipient_email=job.created_by.email,
            recipient_user=job.created_by,
            context={
                "job_id": str(job.id),
                "org_code": job.organization.code if job.organization else "global",
                "total_rows": str(job.total_rows),
                "committed_rows": str(job.committed_rows),
                "failed_rows": str(job.failed_rows),
            },
            execute_sync=True,
        )
    except Exception as exc:
        logger.warning("Bulk import notification delivery skipped: %s", exc)

    # Record Audit Event
    record_audit_event(
        action=AuditAction.BULK_IMPORT_JOB_COMMITTED,
        target_type=AuditTargetType.BULK_IMPORT_JOB,
        target_id=job.id,
        target_repr=f"Bulk Import Job {job.id} committed ({job.committed_rows}/{job.total_rows})",
        actor=actor,
        organization_id=job.organization.id if job.organization else None,
        operation_source=AuditOperationSource.BULK_IMPORT,
        correlation_id=job.id,
        metadata={
            "job_id": str(job.id),
            "total_rows": job.total_rows,
            "committed_rows": job.committed_rows,
            "failed_rows": job.failed_rows,
        },
    )

    return job


def retry_failed_rows(job_id: uuid.UUID | str, actor: Any) -> BulkImportJob:
    """Reset recoverable failed rows to valid and re-execute the commit pipeline.

    Terminal failures (permanent data errors) are strictly excluded from retry.
    """
    job = BulkImportJob.objects.get(id=job_id)

    # Filter ONLY failed rows with recoverable error codes
    failed_rows = job.rows.filter(
        validation_state=RowValidationState.FAILED,
        error_code__in=RECOVERABLE_ERROR_CODES,
    )
    recoverable_count = failed_rows.count()

    if recoverable_count == 0:
        raise BulkImportError(
            "No recoverable failed rows available to retry. Terminal errors cannot be retried.",
            code="NO_RETRYABLE_ROWS",
        )

    failed_rows.update(
        validation_state=RowValidationState.VALID,
        error_code="",
        error_message="",
    )

    job.failed_rows = max(0, job.failed_rows - recoverable_count)
    job.valid_rows = job.rows.filter(validation_state=RowValidationState.VALID).count()
    job.status = BulkImportStatus.VALIDATED
    job.save(update_fields=["failed_rows", "valid_rows", "status", "updated_at"])

    return commit_import_job(job.id, actor)


def get_job_reconciliation_report(job_id: uuid.UUID | str) -> dict[str, Any]:
    """Generate a reproducible, idempotent reconciliation report for a bulk import job.

    Uses aggregation to evaluate outcomes efficiently without N+1 query overhead.
    """
    job = (
        BulkImportJob.objects.select_related("organization", "created_by")
        .prefetch_related("rows")
        .get(id=job_id)
    )

    # Aggregate state counts
    state_breakdown = dict(
        job.rows.values("validation_state")
        .annotate(count=models.Count("id"))
        .values_list("validation_state", "count")
    )

    # Aggregate error code breakdown for non-empty error_code
    error_code_breakdown = dict(
        job.rows.exclude(error_code="")
        .values("error_code")
        .annotate(count=models.Count("id"))
        .values_list("error_code", "count")
    )

    # Count recoverable vs terminal among failed rows
    recoverable_failed_count = job.rows.filter(
        validation_state=RowValidationState.FAILED,
        error_code__in=RECOVERABLE_ERROR_CODES,
    ).count()

    terminal_failed_count = (
        job.rows.filter(validation_state=RowValidationState.FAILED)
        .exclude(error_code__in=RECOVERABLE_ERROR_CODES)
        .count()
    )

    total_terminal_count = terminal_failed_count + state_breakdown.get(RowValidationState.INVALID, 0)

    rows_detail = []
    for r in job.rows.all().order_by("row_number"):
        is_rec = is_error_recoverable(r.error_code) if r.error_code else False
        rows_detail.append(
            {
                "id": str(r.id),
                "row_number": r.row_number,
                "email": r.payload_ref.get("email", ""),
                "full_name": r.payload_ref.get("full_name", ""),
                "membership_type": r.payload_ref.get("membership_type", "member"),
                "role_code": r.payload_ref.get("role_code", ""),
                "validation_state": r.validation_state,
                "error_code": r.error_code,
                "error_message": r.error_message,
                "is_recoverable": is_rec,
            }
        )

    return {
        "job_id": str(job.id),
        "organization_id": str(job.organization.id) if job.organization else None,
        "organization_code": job.organization.code if job.organization else None,
        "organization_name": job.organization.name if job.organization else None,
        "status": job.status,
        "total_rows": job.total_rows,
        "committed_rows": job.committed_rows,
        "failed_rows": job.failed_rows,
        "invalid_rows": job.invalid_rows,
        "valid_rows": job.valid_rows,
        "recoverable_failures_count": recoverable_failed_count,
        "terminal_failures_count": total_terminal_count,
        "can_retry": recoverable_failed_count > 0,
        "state_breakdown": state_breakdown,
        "error_code_breakdown": error_code_breakdown,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        "created_at": job.created_at.isoformat(),
        "rows": rows_detail,
    }
