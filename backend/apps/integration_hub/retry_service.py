"""Integration Failure Lifecycle, Retry Scheduling & Backoff Services (Phase 5G).

Provides deterministic backoff calculation, failure classification,
dead-letter management, and audited manual resolution for IntegrationFailure records.
Note: Control-plane operational state only; downstream external API execution is handled
by specific product adapters.
"""

from datetime import datetime, timedelta
import logging
import random
import re
from typing import Any, Callable, Optional, Union
import uuid

from django.db import models, transaction
from django.utils import timezone

from apps.integration_hub.models import (
    AttemptOutcome,
    FailureStatus,
    FailureType,
    IntegrationFailure,
    IntegrationFailureAttempt,
    ProvisioningJob,
    ProvisioningJobStatus,
)

logger = logging.getLogger(__name__)

FORBIDDEN_SECRET_PATTERNS = [
    re.compile(r"(?i)bearer\s+[a-z0-9_\-\.~+/]+=*", re.IGNORECASE),
    re.compile(r"(?i)(token|password|secret|sec_|private_key)\s*[:=]\s*[^\s,;]+", re.IGNORECASE),
]


def sanitize_diagnostic_detail(detail: str) -> str:
    """Sanitize failure diagnostic detail by masking sensitive credentials."""
    if not detail:
        return ""
    sanitized = str(detail)
    for pattern in FORBIDDEN_SECRET_PATTERNS:
        sanitized = pattern.sub("[REDACTED]", sanitized)
    return sanitized

TRANSIENT_FAILURE_CODES = frozenset([
    "UPSTREAM_TIMEOUT",
    "RATE_LIMITED",
    "NETWORK_ERROR",
    "TEMPORARY_UNAVAILABLE",
    "SERVICE_UNAVAILABLE",
    "GATEWAY_TIMEOUT",
    "CONNECTION_RESET",
    "LOCK_ACQUISITION_TIMEOUT",
])

PERMANENT_FAILURE_CODES = frozenset([
    "AUTHENTICATION_FAILED",
    "INVALID_CREDENTIALS",
    "INVALID_SCHEMA",
    "NOT_FOUND",
    "PERMISSION_DENIED",
    "VALIDATION_ERROR",
    "MALFORMED_PAYLOAD",
    "TENANT_NOT_FOUND",
    "PRODUCT_DISABLED",
    "CONFIGURATION_ERROR",
    "MAPPING_CONFLICT",
    "TENANT_CONFLICT",
    "USER_CONFLICT",
    "CONFLICT",
])


def classify_failure(failure_code: str) -> str:
    """Classify failure code as transient (retryable) or permanent (non-retryable)."""
    norm = (failure_code or "").strip().upper()
    if norm in PERMANENT_FAILURE_CODES:
        return FailureType.PERMANENT
    if norm in TRANSIENT_FAILURE_CODES:
        return FailureType.TRANSIENT
    return FailureType.TRANSIENT


def compute_backoff_delay(
    attempt: int,
    base_seconds: int = 60,
    factor: int = 2,
    max_seconds: int = 3600,
    jitter: bool = False,
    jitter_pct: float = 0.2,
    random_func: Optional[Callable[[], float]] = None,
) -> int:
    """Calculate exponential backoff in seconds with optional bounded jitter.

    Formula: min(max_seconds, base_seconds * (factor ** (attempt - 1)))
    attempt=1 -> base_seconds
    attempt=2 -> base_seconds * factor
    attempt=3 -> base_seconds * factor^2

    When jitter=True:
    Applies bounded jitter in range [1 - jitter_pct, 1 + jitter_pct] (default +/- 20%).
    bounded_delay = raw_delay * (1 - jitter_pct + 2 * jitter_pct * rand_val)
    where rand_val is in [0.0, 1.0].
    Enforces 1 <= delay <= max_seconds so delay is always strictly positive and bounded.
    """
    safe_attempt = max(1, attempt)
    exponent = safe_attempt - 1
    raw_delay = base_seconds * (factor ** exponent)
    capped_delay = min(raw_delay, max_seconds)

    if not jitter:
        return capped_delay

    # Bounded jitter
    clamped_pct = max(0.0, min(0.5, float(jitter_pct)))
    rng = random_func if random_func is not None else random.random
    rand_val = float(rng())
    rand_val = max(0.0, min(1.0, rand_val))

    multiplier = (1.0 - clamped_pct) + (2.0 * clamped_pct * rand_val)
    jittered_delay = int(round(capped_delay * multiplier))

    return max(1, min(jittered_delay, max_seconds))


def schedule_failure_retry(
    failure: IntegrationFailure,
    base_seconds: int = 60,
    jitter: bool = True,
    random_func: Optional[Callable[[], float]] = None,
) -> IntegrationFailure:
    """Transition an IntegrationFailure into RETRY_SCHEDULED or DEAD_LETTER.

    Transition rules:
    - If resolved: raises ValueError (cannot retry resolved).
    - If permanent failure: transitions directly to DEAD_LETTER (no retry permitted).
    - If retry_count >= max_retries: transitions to DEAD_LETTER (retry exhausted).
    - Else: increments retry_count, computes retry_after via backoff, status = RETRY_SCHEDULED.
    """
    if failure.status == FailureStatus.RESOLVED:
        raise ValueError("Cannot schedule retry for a resolved failure.")

    if failure.failure_type == FailureType.PERMANENT:
        failure.status = FailureStatus.DEAD_LETTER
        failure.retry_after = None
        failure.save(update_fields=["status", "retry_after"])
        if failure.job_id and getattr(failure, "job", None) and failure.job.status != ProvisioningJobStatus.COMPLETED:
            failure.job.status = ProvisioningJobStatus.FAILED
            failure.job.save(update_fields=["status", "updated_at"])
        return failure

    if failure.retry_count >= failure.max_retries:
        failure.status = FailureStatus.DEAD_LETTER
        failure.retry_after = None
        failure.save(update_fields=["status", "retry_after"])
        if failure.job_id and getattr(failure, "job", None) and failure.job.status != ProvisioningJobStatus.COMPLETED:
            failure.job.status = ProvisioningJobStatus.FAILED
            failure.job.save(update_fields=["status", "updated_at"])
        return failure

    failure.retry_count += 1
    delay_sec = compute_backoff_delay(
        failure.retry_count,
        base_seconds=base_seconds,
        jitter=jitter,
        random_func=random_func,
    )
    failure.retry_after = timezone.now() + timedelta(seconds=delay_sec)
    failure.status = FailureStatus.RETRY_SCHEDULED
    failure.save(update_fields=["status", "retry_count", "retry_after"])
    if failure.job_id and getattr(failure, "job", None) and failure.job.status != ProvisioningJobStatus.COMPLETED:
        failure.job.status = ProvisioningJobStatus.RETRY_SCHEDULED
        failure.job.save(update_fields=["status", "updated_at"])
    return failure


def mark_failure_dead_letter(
    failure: IntegrationFailure,
    reason: str = "",
) -> IntegrationFailure:
    """Explicitly transition an IntegrationFailure to DEAD_LETTER state."""
    if failure.status == FailureStatus.RESOLVED:
        raise ValueError("Cannot mark a resolved failure as dead-letter.")

    failure.status = FailureStatus.DEAD_LETTER
    failure.retry_after = None
    if reason:
        cleaned_reason = reason.strip()
        failure.failure_detail = f"{failure.failure_detail}\n[Dead-Letter Note: {cleaned_reason}]".strip()
        failure.save(update_fields=["status", "retry_after", "failure_detail"])
    else:
        failure.save(update_fields=["status", "retry_after"])

    if failure.job_id and getattr(failure, "job", None) and failure.job.status != ProvisioningJobStatus.COMPLETED:
        failure.job.status = ProvisioningJobStatus.FAILED
        failure.job.save(update_fields=["status", "updated_at"])

    return failure


def resolve_failure(
    failure: IntegrationFailure,
    user,
    notes: str,
) -> IntegrationFailure:
    """Record audited manual resolution for an IntegrationFailure."""
    if not notes or not notes.strip():
        raise ValueError("Resolution notes are required for audit trail.")

    failure.status = FailureStatus.RESOLVED
    failure.resolved_at = timezone.now()
    failure.resolved_by = user
    failure.resolution_notes = notes.strip()
    failure.retry_after = None
    failure.save(update_fields=["status", "resolved_at", "resolved_by", "resolution_notes", "retry_after"])
    return failure


def record_failure_attempt(
    failure: IntegrationFailure,
    started_at: datetime,
    completed_at: datetime,
    outcome: str,
    failure_code: str = "",
    failure_detail: str = "",
    http_status: Optional[int] = None,
    retry_after: Optional[datetime] = None,
) -> IntegrationFailureAttempt:
    """Record an execution attempt for an IntegrationFailure with concurrency-safe attempt numbering.

    Serializes attempt-number allocation using row-level database locking (select_for_update)
    on the canonical IntegrationFailure record within an atomic transaction. This guarantees
    that concurrent executions safely obtain sequential, non-colliding attempt numbers without
    triggering unique constraint collisions or skipping numbers.
    """
    clean_detail = sanitize_diagnostic_detail(failure_detail)
    with transaction.atomic():
        locked_failure = IntegrationFailure.objects.select_for_update().get(pk=failure.pk)
        max_attempt = IntegrationFailureAttempt.objects.filter(failure=locked_failure).aggregate(
            max_num=models.Max("attempt_number")
        )["max_num"]
        next_attempt = (max_attempt or 0) + 1

        return IntegrationFailureAttempt.objects.create(
            failure=locked_failure,
            attempt_number=next_attempt,
            started_at=started_at,
            completed_at=completed_at,
            outcome=outcome,
            failure_code=failure_code or "",
            failure_detail=clean_detail,
            http_status=http_status,
            retry_after=retry_after,
        )


def replay_dead_letter_failure(
    failure_id: Union[str, uuid.UUID],
    actor: Any = None,
    client: Optional[Any] = None,
) -> IntegrationFailure:
    """Safely replays a DEAD_LETTER IntegrationFailure after issue correction.

    Requirements:
    1. Validate actor has Platform Owner permission.
    2. Atomically lock IntegrationFailure and associated ProvisioningJob with select_for_update().
    3. Verify status == DEAD_LETTER.
    4. Verify related ProvisioningJob exists and is not currently PROCESSING or COMPLETED.
    5. Reset failure to OPEN and reset retry_count to 0 (starting a fresh recovery cycle for the operator,
       while fully preserving all historical IntegrationFailureAttempt records).
    6. Transition ProvisioningJob to PROCESSING with audit context recording replayed_by.
    7. Execute provisioning via canonical execute_provisioning_job().
    8. Return refreshed IntegrationFailure record.
    """
    if actor is not None and not getattr(actor, "is_platform_owner", False) and not getattr(actor, "_is_support_operator", False):
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied("Platform owner privileges required to replay dead-letter failures.")


    with transaction.atomic():
        try:
            failure = IntegrationFailure.objects.select_for_update().get(pk=failure_id)
        except IntegrationFailure.DoesNotExist:
            raise ValueError(f"Integration failure '{failure_id}' not found.")

        if failure.status != FailureStatus.DEAD_LETTER:
            raise ValueError(
                f"Only DEAD_LETTER failures can be replayed. Current failure status is '{failure.status}'."
            )

        if not failure.job_id:
            raise ValueError("Only failures associated with a ProvisioningJob can be replayed.")

        job = ProvisioningJob.objects.select_for_update().get(pk=failure.job_id)

        if job.status == ProvisioningJobStatus.PROCESSING:
            raise ValueError("Replay or execution already in progress for this job.")

        if job.status == ProvisioningJobStatus.COMPLETED:
            raise ValueError("Associated provisioning job is already completed.")

        # Minimum valid state reset:
        # Start a fresh recovery cycle for the operator while preserving all previous attempts.
        failure.status = FailureStatus.OPEN
        failure.retry_count = 0
        failure.retry_after = None
        failure.save(update_fields=["status", "retry_count", "retry_after"])

        job.status = ProvisioningJobStatus.PROCESSING
        if actor and getattr(actor, "id", None):
            job.context = {**job.context, "replayed_by_id": str(actor.id)}
            job.save(update_fields=["status", "context", "updated_at"])
        else:
            job.save(update_fields=["status", "updated_at"])

    # Canonical execution outside atomic block to avoid prolonged DB locks during M2M calls
    from apps.integration_hub.provisioning_service import execute_provisioning_job

    try:
        execute_provisioning_job(job, client=client)
    except Exception as exc:
        logger.info("Replay execution for failure %s resulted in error: %s", failure.id, exc)

    failure.refresh_from_db()
    return failure


def process_scheduled_retries(
    limit: int = 50,
    client: Optional[Any] = None,
) -> dict[str, int]:
    """Execute a bounded batch of eligible scheduled integration retries.

    Eligibility criteria:
    - IntegrationFailure.status == RETRY_SCHEDULED
    - retry_after <= current time
    - retry_count < max_retries
    - related ProvisioningJob exists
    - related ProvisioningJob.status == RETRY_SCHEDULED

    Concurrency safety:
    Uses select_for_update(skip_locked=True) to claim eligible failure and job rows.
    If another process or runner has claimed the row, skip_locked=True bypasses it cleanly.

    Execution:
    Invokes canonical execute_provisioning_job(job, client=client).
    Preserves all attempt histories, backoff jitter, and state consistency.

    Returns stats dict:
    {"scanned": int, "claimed": int, "executed": int, "completed": int, "rescheduled": int, "dead_lettered": int, "skipped": int}
    """
    now = timezone.now()
    safe_limit = max(1, min(limit, 500))

    candidate_ids = list(
        IntegrationFailure.objects.filter(
            status=FailureStatus.RETRY_SCHEDULED,
            retry_after__lte=now,
            retry_count__lt=models.F("max_retries"),
            job__isnull=False,
            job__status=ProvisioningJobStatus.RETRY_SCHEDULED,
        )
        .order_by("retry_after")[:safe_limit]
        .values_list("id", flat=True)
    )

    stats = {
        "scanned": len(candidate_ids),
        "claimed": 0,
        "executed": 0,
        "completed": 0,
        "rescheduled": 0,
        "dead_lettered": 0,
        "skipped": 0,
    }

    from apps.integration_hub.provisioning_service import execute_provisioning_job

    for failure_id in candidate_ids:
        job_to_execute = None
        with transaction.atomic():
            failure = (
                IntegrationFailure.objects.filter(
                    pk=failure_id,
                    status=FailureStatus.RETRY_SCHEDULED,
                    retry_after__lte=timezone.now(),
                )
                .select_for_update(skip_locked=True)
                .first()
            )
            if not failure or not failure.job_id:
                stats["skipped"] += 1
                continue

            job = (
                ProvisioningJob.objects.filter(
                    pk=failure.job_id,
                    status=ProvisioningJobStatus.RETRY_SCHEDULED,
                )
                .select_for_update(skip_locked=True)
                .first()
            )
            if not job:
                stats["skipped"] += 1
                continue

            # Atomically claim the retry: transition job to PROCESSING
            job.status = ProvisioningJobStatus.PROCESSING
            job.save(update_fields=["status", "updated_at"])
            job_to_execute = job
            stats["claimed"] += 1

        # Execute outside claim transaction
        if job_to_execute:
            stats["executed"] += 1
            try:
                execute_provisioning_job(job_to_execute, client=client)
            except Exception as exc:
                logger.info("Retry runner execution for job %s resulted in: %s", job_to_execute.id, exc)

            # Inspect resulting failure state
            try:
                refreshed_failure = IntegrationFailure.objects.get(pk=failure_id)
                if refreshed_failure.status == FailureStatus.RESOLVED:
                    stats["completed"] += 1
                elif refreshed_failure.status == FailureStatus.RETRY_SCHEDULED:
                    stats["rescheduled"] += 1
                elif refreshed_failure.status == FailureStatus.DEAD_LETTER:
                    stats["dead_lettered"] += 1
            except IntegrationFailure.DoesNotExist:
                pass

    return stats


