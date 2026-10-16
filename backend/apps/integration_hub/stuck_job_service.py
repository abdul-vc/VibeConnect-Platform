"""Stuck & Orphaned Provisioning Job Detection and Safe Recovery Service (Phase 5G Stage 4).

Provides:
- Detection of stale/stuck provisioning jobs (STUCK_QUEUED, STUCK_PROCESSING).
- Detection of orphaned/inconsistent job states (ORPHANED).
- Distinction between healthy active states and stuck/orphaned states.
- Explicit, safe, operator-driven recovery actions under row-level database locks.
- Concurrency protection against duplicate executions.
- Zero automatic background loops/daemons; explicit invocation only.
- Strict protection of live audit records.
"""

from datetime import timedelta
import logging
from typing import Any, Optional, Union
import uuid

from django.conf import settings
from django.db import models, transaction
from django.utils import timezone

from apps.integration_hub.models import (
    AttemptOutcome,
    FailureStatus,
    FailureType,
    IntegrationFailure,
    ProvisioningAction,
    ProvisioningJob,
    ProvisioningJobStatus,
)
from apps.integration_hub.provisioning_service import (
    ProvisioningServiceError,
    execute_provisioning_job,
)
from apps.integration_hub.retry_service import (
    record_failure_attempt,
    sanitize_diagnostic_detail,
)

logger = logging.getLogger(__name__)

# Default threshold configuration (overrideable via Django settings or runtime arguments)
DEFAULT_STUCK_QUEUED_THRESHOLD_SECONDS = getattr(
    settings, "INTEGRATION_HUB_STUCK_QUEUED_THRESHOLD_SECONDS", 1800
)  # 30 minutes
DEFAULT_STUCK_PROCESSING_THRESHOLD_SECONDS = getattr(
    settings, "INTEGRATION_HUB_STUCK_PROCESSING_THRESHOLD_SECONDS", 300
)  # 5 minutes


class JobClassification:
    NORMAL_QUEUED = "NORMAL_QUEUED"
    NORMAL_PROCESSING = "NORMAL_PROCESSING"
    NORMAL_RETRY_SCHEDULED = "NORMAL_RETRY_SCHEDULED"
    STUCK_QUEUED = "STUCK_QUEUED"
    STUCK_PROCESSING = "STUCK_PROCESSING"
    ORPHANED = "ORPHANED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


def classify_provisioning_job(
    job: ProvisioningJob,
    queued_threshold_seconds: Optional[int] = None,
    processing_threshold_seconds: Optional[int] = None,
    now: Optional[timezone.datetime] = None,
) -> dict[str, Any]:
    """Classifies a ProvisioningJob into a health/stuck/orphan category.

    Distinguishes:
    1. NORMAL QUEUED: queued within acceptable threshold
    2. NORMAL PROCESSING: processing within acceptable threshold
    3. NORMAL RETRY_SCHEDULED: has a valid corresponding RETRY_SCHEDULED failure
    4. STUCK QUEUED: queued duration exceeds threshold
    5. STUCK PROCESSING: processing duration without update exceeds threshold
    6. ORPHANED: missing required relationships or impossible state combination
    """
    now = now or timezone.now()
    q_thresh = (
        queued_threshold_seconds
        if queued_threshold_seconds is not None
        else DEFAULT_STUCK_QUEUED_THRESHOLD_SECONDS
    )
    p_thresh = (
        processing_threshold_seconds
        if processing_threshold_seconds is not None
        else DEFAULT_STUCK_PROCESSING_THRESHOLD_SECONDS
    )

    # 1. Structural integrity check (missing required relationships)
    if not job.organization_id or not job.instance_id:
        age_seconds = int((now - (job.updated_at or job.created_at)).total_seconds())
        return {
            "category": JobClassification.ORPHANED,
            "is_stuck_or_orphaned": True,
            "age_seconds": max(0, age_seconds),
            "reason": "Job is missing required organization or connector instance relation.",
            "is_recoverable": True,
            "recommended_recovery_action": "fail",
        }

    # 2. Terminal states
    if job.status == ProvisioningJobStatus.COMPLETED:
        age_seconds = int((now - (job.completed_at or job.updated_at)).total_seconds())
        return {
            "category": JobClassification.COMPLETED,
            "is_stuck_or_orphaned": False,
            "age_seconds": max(0, age_seconds),
            "reason": "Job completed successfully.",
            "is_recoverable": False,
            "recommended_recovery_action": "none",
        }

    if job.status == ProvisioningJobStatus.FAILED:
        age_seconds = int((now - job.updated_at).total_seconds())
        return {
            "category": JobClassification.FAILED,
            "is_stuck_or_orphaned": False,
            "age_seconds": max(0, age_seconds),
            "reason": "Job is in terminal failed state (manageable via dead-letter replay).",
            "is_recoverable": False,
            "recommended_recovery_action": "none",
        }

    if job.status == ProvisioningJobStatus.CANCELLED:
        age_seconds = int((now - job.updated_at).total_seconds())
        return {
            "category": JobClassification.CANCELLED,
            "is_stuck_or_orphaned": False,
            "age_seconds": max(0, age_seconds),
            "reason": "Job was cancelled.",
            "is_recoverable": False,
            "recommended_recovery_action": "none",
        }

    # 3. RETRY_SCHEDULED state integrity check
    if job.status == ProvisioningJobStatus.RETRY_SCHEDULED:
        has_valid_failure = IntegrationFailure.objects.filter(
            job=job,
            status=FailureStatus.RETRY_SCHEDULED,
        ).exists()
        age_seconds = int((now - job.updated_at).total_seconds())
        if not has_valid_failure:
            return {
                "category": JobClassification.ORPHANED,
                "is_stuck_or_orphaned": True,
                "age_seconds": max(0, age_seconds),
                "reason": (
                    "Job status is RETRY_SCHEDULED but no corresponding "
                    "RETRY_SCHEDULED IntegrationFailure record exists."
                ),
                "is_recoverable": True,
                "recommended_recovery_action": "fail",
            }
        return {
            "category": JobClassification.NORMAL_RETRY_SCHEDULED,
            "is_stuck_or_orphaned": False,
            "age_seconds": max(0, age_seconds),
            "reason": "Job is waiting for eligible retry runner execution.",
            "is_recoverable": False,
            "recommended_recovery_action": "none",
        }

    # 4. QUEUED state check
    if job.status == ProvisioningJobStatus.QUEUED:
        age_seconds = int((now - job.created_at).total_seconds())
        if age_seconds > q_thresh:
            return {
                "category": JobClassification.STUCK_QUEUED,
                "is_stuck_or_orphaned": True,
                "age_seconds": max(0, age_seconds),
                "reason": (
                    f"Job has remained in QUEUED state for {age_seconds}s "
                    f"(threshold: {q_thresh}s)."
                ),
                "is_recoverable": True,
                "recommended_recovery_action": "reexecute",
            }
        return {
            "category": JobClassification.NORMAL_QUEUED,
            "is_stuck_or_orphaned": False,
            "age_seconds": max(0, age_seconds),
            "reason": f"Queued normally ({age_seconds}s <= threshold {q_thresh}s).",
            "is_recoverable": False,
            "recommended_recovery_action": "none",
        }

    # 5. PROCESSING state check
    if job.status == ProvisioningJobStatus.PROCESSING:
        age_seconds = int((now - job.updated_at).total_seconds())
        if age_seconds > p_thresh:
            return {
                "category": JobClassification.STUCK_PROCESSING,
                "is_stuck_or_orphaned": True,
                "age_seconds": max(0, age_seconds),
                "reason": (
                    f"Job has remained in PROCESSING state for {age_seconds}s without update "
                    f"(threshold: {p_thresh}s)."
                ),
                "is_recoverable": True,
                "recommended_recovery_action": "fail",
            }
        return {
            "category": JobClassification.NORMAL_PROCESSING,
            "is_stuck_or_orphaned": False,
            "age_seconds": max(0, age_seconds),
            "reason": f"Processing normally ({age_seconds}s <= threshold {p_thresh}s).",
            "is_recoverable": False,
            "recommended_recovery_action": "none",
        }

    # Fallback for unrecognized status
    age_seconds = int((now - job.updated_at).total_seconds())
    return {
        "category": JobClassification.ORPHANED,
        "is_stuck_or_orphaned": True,
        "age_seconds": max(0, age_seconds),
        "reason": f"Unrecognized job status: {job.status}",
        "is_recoverable": True,
        "recommended_recovery_action": "fail",
    }


def detect_stuck_provisioning_jobs(
    queued_threshold_seconds: Optional[int] = None,
    processing_threshold_seconds: Optional[int] = None,
    limit: int = 100,
    organization_id: Optional[Union[str, uuid.UUID]] = None,
) -> dict[str, Any]:
    """Scans and reports provisioning jobs and failures that are stuck or orphaned.

    Returns structured summary and item lists without exposing secrets or sensitive data.
    """
    now = timezone.now()
    safe_limit = max(1, min(limit, 500))

    query = ProvisioningJob.objects.filter(
        status__in=[
            ProvisioningJobStatus.QUEUED,
            ProvisioningJobStatus.PROCESSING,
            ProvisioningJobStatus.RETRY_SCHEDULED,
        ]
    )
    if organization_id:
        query = query.filter(organization_id=organization_id)

    candidate_jobs = list(query.order_by("created_at")[:safe_limit])

    summary = {
        "stuck_queued": 0,
        "stuck_processing": 0,
        "orphaned": 0,
        "total_stuck_or_orphaned": 0,
        "healthy_queued": 0,
        "healthy_processing": 0,
        "healthy_retry_scheduled": 0,
    }

    stuck_jobs_list = []

    for job in candidate_jobs:
        classification = classify_provisioning_job(
            job,
            queued_threshold_seconds=queued_threshold_seconds,
            processing_threshold_seconds=processing_threshold_seconds,
            now=now,
        )

        cat = classification["category"]
        if cat == JobClassification.STUCK_QUEUED:
            summary["stuck_queued"] += 1
            summary["total_stuck_or_orphaned"] += 1
            stuck_jobs_list.append({
                "job_id": str(job.id),
                "category": cat,
                "current_status": job.status,
                "age_seconds": classification["age_seconds"],
                "reason": classification["reason"],
                "action": job.action,
                "organization_id": str(job.organization_id) if job.organization_id else None,
                "instance_id": str(job.instance_id) if job.instance_id else None,
                "is_recoverable": classification["is_recoverable"],
                "recommended_recovery_action": classification["recommended_recovery_action"],
            })
        elif cat == JobClassification.STUCK_PROCESSING:
            summary["stuck_processing"] += 1
            summary["total_stuck_or_orphaned"] += 1
            stuck_jobs_list.append({
                "job_id": str(job.id),
                "category": cat,
                "current_status": job.status,
                "age_seconds": classification["age_seconds"],
                "reason": classification["reason"],
                "action": job.action,
                "organization_id": str(job.organization_id) if job.organization_id else None,
                "instance_id": str(job.instance_id) if job.instance_id else None,
                "is_recoverable": classification["is_recoverable"],
                "recommended_recovery_action": classification["recommended_recovery_action"],
            })
        elif cat == JobClassification.ORPHANED:
            summary["orphaned"] += 1
            summary["total_stuck_or_orphaned"] += 1
            stuck_jobs_list.append({
                "job_id": str(job.id),
                "category": cat,
                "current_status": job.status,
                "age_seconds": classification["age_seconds"],
                "reason": classification["reason"],
                "action": job.action,
                "organization_id": str(job.organization_id) if job.organization_id else None,
                "instance_id": str(job.instance_id) if job.instance_id else None,
                "is_recoverable": classification["is_recoverable"],
                "recommended_recovery_action": classification["recommended_recovery_action"],
            })
        elif cat == JobClassification.NORMAL_QUEUED:
            summary["healthy_queued"] += 1
        elif cat == JobClassification.NORMAL_PROCESSING:
            summary["healthy_processing"] += 1
        elif cat == JobClassification.NORMAL_RETRY_SCHEDULED:
            summary["healthy_retry_scheduled"] += 1

    # Also detect orphaned IntegrationFailure records marked RETRY_SCHEDULED without an active job
    orphaned_failures_query = IntegrationFailure.objects.filter(
        status=FailureStatus.RETRY_SCHEDULED,
        job__isnull=True,
    )
    if organization_id:
        orphaned_failures_query = orphaned_failures_query.filter(
            event__instance__organization_id=organization_id
        )

    orphaned_failures_list = []
    for fail in orphaned_failures_query[:safe_limit]:
        summary["orphaned"] += 1
        summary["total_stuck_or_orphaned"] += 1
        orphaned_failures_list.append({
            "failure_id": str(fail.id),
            "category": JobClassification.ORPHANED,
            "current_status": fail.status,
            "reason": "IntegrationFailure is RETRY_SCHEDULED but has no associated job.",
        })

    return {
        "summary": summary,
        "stuck_jobs": stuck_jobs_list,
        "orphaned_failures": orphaned_failures_list,
    }


def recover_stuck_provisioning_job(
    job_or_id: Union[ProvisioningJob, str, uuid.UUID],
    action: str = "fail",
    actor: Optional[Any] = None,
    client: Optional[Any] = None,
    queued_threshold_seconds: Optional[int] = None,
    processing_threshold_seconds: Optional[int] = None,
) -> dict[str, Any]:
    """Performs an explicit, safe recovery on a stuck or orphaned ProvisioningJob.

    Concurrency protected via row-level database locking (select_for_update).
    Requires explicit invocation. Does NOT run automatic loops.
    Strictly safeguards protected audit records from mutation.

    Parameters:
    - job_or_id: ProvisioningJob instance or primary key
    - action: "fail" (safe terminal failure for manual review) or "reexecute" (re-run canonical provisioning)
    - actor: Optional user who initiated the recovery action
    - client: Optional LmsConnectorClient instance (for testing/mocking)

    Returns:
    dict with operation result, job status, and action taken.
    """
    job_id = job_or_id.id if isinstance(job_or_id, ProvisioningJob) else job_or_id
    str_job_id = str(job_id)

    normalized_action = (action or "fail").strip().lower()
    if normalized_action not in ("fail", "reexecute"):
        raise ProvisioningServiceError(
            f"Invalid recovery action '{action}'. Allowed actions: 'fail', 'reexecute'.",
            code="INVALID_RECOVERY_ACTION",
        )

    with transaction.atomic():
        # Acquire row-level lock on the job row (no nullable outer joins in select_for_update)
        job = (
            ProvisioningJob.objects.select_for_update()
            .filter(pk=job_id)
            .first()
        )
        if not job:
            raise ProvisioningServiceError(
                f"ProvisioningJob '{job_id}' does not exist.",
                code="JOB_NOT_FOUND",
            )

        # Idempotency guard: If job has already completed or failed, safely return no-op
        if job.status == ProvisioningJobStatus.COMPLETED:
            return {
                "success": True,
                "action_taken": "noop",
                "job_id": str(job.id),
                "status": job.status,
                "message": "Job has already completed successfully.",
            }
        if job.status == ProvisioningJobStatus.FAILED:
            return {
                "success": True,
                "action_taken": "noop",
                "job_id": str(job.id),
                "status": job.status,
                "message": "Job is already marked as failed.",
            }
        if job.status == ProvisioningJobStatus.CANCELLED:
            return {
                "success": True,
                "action_taken": "noop",
                "job_id": str(job.id),
                "status": job.status,
                "message": "Job was cancelled.",
            }

        # If job is actively being processed by another worker within the processing threshold
        if job.status == ProvisioningJobStatus.PROCESSING:
            p_thresh = (
                processing_threshold_seconds
                if processing_threshold_seconds is not None
                else DEFAULT_STUCK_PROCESSING_THRESHOLD_SECONDS
            )
            proc_age = int((timezone.now() - (job.updated_at or job.created_at)).total_seconds())
            if proc_age <= p_thresh:
                return {
                    "success": True,
                    "action_taken": "noop",
                    "job_id": str(job.id),
                    "status": job.status,
                    "message": "Job is currently being processed by another worker.",
                }

        classification = classify_provisioning_job(
            job,
            queued_threshold_seconds=queued_threshold_seconds,
            processing_threshold_seconds=processing_threshold_seconds,
        )

        # Generic state-based eligibility rule:
        # A healthy job within threshold or active retry schedule is not eligible for stuck-job recovery
        if not classification["is_stuck_or_orphaned"]:
            raise ProvisioningServiceError(
                f"Job '{job_id}' is currently healthy ({classification['category']}) "
                f"and not eligible for stuck job recovery.",
                code="JOB_NOT_STUCK",
            )

        category = classification["category"]

        # Action: "reexecute"
        if normalized_action == "reexecute":
            # For STUCK_QUEUED: safe to re-execute since it never completed
            # For other categories: reexecute is only permitted if relationships are intact
            if category == JobClassification.ORPHANED and (not job.organization_id or not job.instance_id):
                raise ProvisioningServiceError(
                    "Cannot re-execute orphaned job with missing organization or instance.",
                    code="ORPHAN_CANNOT_REEXECUTE",
                )

            # Atomically claim the execution under the lock
            job.status = ProvisioningJobStatus.PROCESSING
            job.context = {
                **job.context,
                "recovered_at": timezone.now().isoformat(),
                "recovered_by_id": str(actor.id) if actor and hasattr(actor, "id") else None,
                "recovery_reason": classification["reason"],
            }
            job.save(update_fields=["status", "context", "updated_at"])

    # Outside the initial locking transaction, run execute_provisioning_job canonically
    if normalized_action == "reexecute":
        executed_job = execute_provisioning_job(job_id, client=client)
        return {
            "success": True,
            "action_taken": "reexecuted",
            "job_id": str(executed_job.id),
            "status": executed_job.status,
            "message": f"Job re-executed. New status: {executed_job.status}",
        }

    # Action: "fail" (safe terminal failure recording dead-letter failure)
    with transaction.atomic():
        locked_job = (
            ProvisioningJob.objects.select_for_update()
            .filter(pk=job_id)
            .first()
        )
        if not locked_job or locked_job.status in (
            ProvisioningJobStatus.COMPLETED,
            ProvisioningJobStatus.FAILED,
        ):
            return {
                "success": True,
                "action_taken": "noop",
                "job_id": str_job_id,
                "status": locked_job.status if locked_job else "unknown",
                "message": "Job state changed before failure action could be applied.",
            }

        started_at = locked_job.updated_at or timezone.now()
        completed_at = timezone.now()

        if category == JobClassification.STUCK_QUEUED:
            failure_code = "STUCK_QUEUED_TIMEOUT"
        elif category == JobClassification.STUCK_PROCESSING:
            failure_code = "STUCK_PROCESSING_TIMEOUT"
        else:
            failure_code = "ORPHANED_JOB_INVALID_STATE"

        failure_detail = sanitize_diagnostic_detail(classification["reason"])

        # Mark job failed
        locked_job.status = ProvisioningJobStatus.FAILED
        locked_job.context = {
            **locked_job.context,
            "recovered_at": completed_at.isoformat(),
            "recovered_by_id": str(actor.id) if actor and hasattr(actor, "id") else None,
            "recovery_action": "fail",
            "recovery_reason": failure_detail,
        }
        locked_job.save(update_fields=["status", "context", "updated_at"])

        # Find or create dead-letter failure record
        failure = (
            IntegrationFailure.objects.select_for_update()
            .filter(job=locked_job)
            .first()
        )
        if not failure:
            failure = IntegrationFailure.objects.create(
                job=locked_job,
                failure_code=failure_code,
                failure_detail=failure_detail,
                failure_type=FailureType.PERMANENT,
                status=FailureStatus.DEAD_LETTER,
            )
        else:
            failure.failure_code = failure_code
            failure.failure_detail = failure_detail
            failure.failure_type = FailureType.PERMANENT
            failure.status = FailureStatus.DEAD_LETTER
            failure.save(update_fields=["failure_code", "failure_detail", "failure_type", "status"])

        # Record audited attempt
        record_failure_attempt(
            failure=failure,
            started_at=started_at,
            completed_at=completed_at,
            outcome=AttemptOutcome.FAILURE,
            failure_code=failure_code,
            failure_detail=failure_detail,
            http_status=None,
            retry_after=None,
        )

        logger.info(
            "Stuck provisioning job %s safely recovered with action 'fail' (%s)",
            locked_job.id,
            failure_code,
        )

        return {
            "success": True,
            "action_taken": "marked_failed",
            "job_id": str(locked_job.id),
            "status": locked_job.status,
            "failure_id": str(failure.id),
            "failure_code": failure_code,
            "message": f"Job marked FAILED with dead-letter failure ({failure_code}).",
        }
