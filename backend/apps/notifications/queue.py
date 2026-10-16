"""DB-backed Asynchronous Job Queue & Worker Services (Phase 3 Async Workers).

Handles idempotent enqueueing and transactional execution for:
- Notification deliveries (notification_delivery)
- Bulk import commit operations (bulk_import_commit)
- Bulk import retry operations (bulk_import_retry)
"""

import logging
from typing import Any
import uuid

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone

from apps.notifications.models import BackgroundJob, BackgroundJobStatus

logger = logging.getLogger(__name__)
PlatformUser = get_user_model()


def enqueue_background_job(*, job_type: str, payload: dict[str, Any], max_attempts: int = 3) -> BackgroundJob:
    """Idempotently enqueue a background task.

    If an identical active job (queued or processing) already exists for the given
    job_type and payload key, the existing job is returned to prevent duplicate processing.
    """
    clean_payload = dict(payload)

    # Check for existing active job with same job_type and key payload identifier
    key_id = clean_payload.get("job_id") or clean_payload.get("delivery_id")
    if key_id:
        existing = (
            BackgroundJob.objects.filter(
                job_type=job_type,
                status__in=[BackgroundJobStatus.QUEUED, BackgroundJobStatus.PROCESSING],
            )
            .filter(payload__contains={clean_payload.get("job_id") and "job_id" or "delivery_id": str(key_id)})
            .first()
        )
        if existing:
            return existing

    return BackgroundJob.objects.create(
        job_type=job_type,
        payload=clean_payload,
        status=BackgroundJobStatus.QUEUED,
        max_attempts=max_attempts,
    )


def process_background_job(job: BackgroundJob) -> bool:
    """Execute a single background job safely and update its status."""
    from apps.bulk_import.services import commit_import_job, retry_failed_rows
    from apps.notifications.services import execute_delivery

    job.status = BackgroundJobStatus.PROCESSING
    job.attempts += 1
    job.save(update_fields=["status", "attempts", "updated_at"])

    try:
        if job.job_type == "notification_delivery":
            delivery_id = job.payload.get("delivery_id")
            execute_delivery(delivery_id)
        elif job.job_type == "bulk_import_commit":
            job_id = job.payload.get("job_id")
            actor_id = job.payload.get("actor_id")
            actor = PlatformUser.objects.filter(id=actor_id).first()
            commit_import_job(job_id=job_id, actor=actor)
        elif job.job_type == "bulk_import_retry":
            job_id = job.payload.get("job_id")
            actor_id = job.payload.get("actor_id")
            actor = PlatformUser.objects.filter(id=actor_id).first()
            retry_failed_rows(job_id=job_id, actor=actor)
        elif job.job_type == "usage_bucket_aggregation":
            from apps.usage_metering.services import aggregate_usage_buckets
            aggregate_usage_buckets(organization_id=job.payload.get("organization_id"))
        elif job.job_type == "dunning_retry":
            from apps.billing.services import process_dunning_retry
            process_dunning_retry(
                invoice_id=job.payload.get("invoice_id"),
                attempt_number=job.payload.get("attempt_number", 1),
            )
        elif job.job_type == "commercial_reconciliation":
            from apps.billing.reconciliation import run_commercial_reconciliation
            run_commercial_reconciliation(organization_id=job.payload.get("organization_id"))
        else:
            raise ValueError(f"Unknown background job type: {job.job_type}")

        job.status = BackgroundJobStatus.COMPLETED
        job.error_message = ""
        job.completed_at = timezone.now()
        job.save(update_fields=["status", "error_message", "completed_at", "updated_at"])
        return True

    except Exception as exc:
        logger.error("Background job %s (%s) failed attempt %d: %s", job.id, job.job_type, job.attempts, exc)
        job.error_message = str(exc)[:1000]
        if job.attempts >= job.max_attempts:
            job.status = BackgroundJobStatus.FAILED
        else:
            job.status = BackgroundJobStatus.QUEUED
        job.save(update_fields=["status", "error_message", "updated_at"])
        return False


def process_next_queued_job() -> bool:
    """Atomically fetch and execute the next queued job.

    Returns True if a job was found and executed, False if the queue was empty.
    Uses select_for_update(skip_locked=True) to avoid worker contention.
    """
    with transaction.atomic():
        job = (
            BackgroundJob.objects.select_for_update(skip_locked=True)
            .filter(status=BackgroundJobStatus.QUEUED)
            .order_by("created_at")
            .first()
        )
        if not job:
            return False

        # Mark as processing inside atomic transaction
        job.status = BackgroundJobStatus.PROCESSING
        job.attempts += 1
        job.save(update_fields=["status", "attempts", "updated_at"])

    # Execute outside the lock transaction so long-running operations don't hold table locks
    process_background_job(job)
    return True
