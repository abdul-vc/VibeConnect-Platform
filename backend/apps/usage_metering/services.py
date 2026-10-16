import datetime
import logging
from typing import Any, Optional, Tuple

from django.db import transaction
from django.db.models import F, Sum
from django.utils import timezone

from apps.notifications.queue import enqueue_background_job
from apps.organizations.models import Organization
from apps.subscriptions.models import SubscriptionQuotaEntitlement
from apps.usage_metering.models import MeterDefinition, UsageBucket, UsageEvent

logger = logging.getLogger(__name__)


def _get_monthly_period_bounds(dt: datetime.datetime) -> Tuple[datetime.datetime, datetime.datetime]:
    """Returns UTC (period_start, period_end) for the month containing dt."""
    start = dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    # Next month start
    if start.month == 12:
        next_month = start.replace(year=start.year + 1, month=1)
    else:
        next_month = start.replace(month=start.month + 1)
    return start, next_month


def ingest_usage_event(
    *,
    organization: Organization,
    meter_key: str,
    quantity: int = 1,
    event_key: str,
    product=None,
    occurred_at: Optional[datetime.datetime] = None,
) -> Tuple[UsageEvent, bool]:
    """Idempotently ingest a usage event.
    
    Returns (event, is_created). If event_key already exists for the organization,
    returns existing event and False without modifying bucket or erroring.
    """
    if not occurred_at:
        occurred_at = timezone.now()

    # Fast check for duplicate
    existing = UsageEvent.objects.filter(organization=organization, event_key=event_key).first()
    if existing:
        return existing, False

    meter, _ = MeterDefinition.objects.get_or_create(
        quota_key=meter_key,
        defaults={"name": meter_key.replace("_", " ").title()},
    )

    try:
        with transaction.atomic():
            event = UsageEvent.objects.create(
                organization=organization,
                product=product,
                meter=meter,
                quantity=quantity,
                event_key=event_key,
                occurred_at=occurred_at,
                processed=False,
            )
    except Exception:
        # Check if race condition inserted the duplicate
        existing = UsageEvent.objects.filter(organization=organization, event_key=event_key).first()
        if existing:
            return existing, False
        raise

    # Trigger background aggregation
    try:
        enqueue_background_job(
            job_type="usage_bucket_aggregation",
            payload={"organization_id": str(organization.id), "event_key": event_key},
        )
    except Exception as exc:
        logger.warning("Failed to enqueue usage aggregation job: %s", exc)

    return event, True


def aggregate_usage_buckets(organization_id: Optional[str] = None) -> int:
    """Aggregates unprocessed usage events into UsageBucket atomically.
    
    Evaluates against active SubscriptionQuotaEntitlement limits.
    Returns count of processed events.
    """
    qs = UsageEvent.objects.filter(processed=False).select_related("organization", "meter")
    if organization_id:
        qs = qs.filter(organization_id=organization_id)

    events = list(qs.order_by("occurred_at")[:500])
    if not events:
        return 0

    processed_ids = []

    # Group events by (organization, meter, period_start, period_end)
    grouped: dict[tuple, int] = {}
    event_map: dict[tuple, list[UsageEvent]] = {}

    for evt in events:
        p_start, p_end = _get_monthly_period_bounds(evt.occurred_at)
        key = (evt.organization, evt.meter, p_start, p_end)
        grouped[key] = grouped.get(key, 0) + evt.quantity
        event_map.setdefault(key, []).append(evt)

    for (org, meter, p_start, p_end), total_qty in grouped.items():
        with transaction.atomic():
            bucket, _ = UsageBucket.objects.get_or_create(
                organization=org,
                meter=meter,
                period_start=p_start,
                defaults={
                    "period_end": p_end,
                    "consumed": 0,
                    "is_over_limit": False,
                },
            )

            # Atomic increment
            UsageBucket.objects.filter(id=bucket.id).update(consumed=F("consumed") + total_qty)
            bucket.refresh_from_db()

            # Quota limit evaluation against active subscription snapshot
            entitlement = (
                SubscriptionQuotaEntitlement.objects.filter(
                    organization=org,
                    quota_key=meter.quota_key,
                    subscription__status="active",
                )
                .order_by("-created_at")
                .first()
            )

            if entitlement:
                bucket.limit_value = entitlement.limit_value
                if entitlement.limit_value is not None and bucket.consumed > entitlement.limit_value:
                    bucket.is_over_limit = True
                else:
                    bucket.is_over_limit = False
            else:
                # Event for a meter with no matching quota: log, don't crash
                logger.info("Meter %s has no matching active quota entitlement for org %s", meter.quota_key, org.id)
                bucket.limit_value = None
                bucket.is_over_limit = False

            bucket.save(update_fields=["limit_value", "is_over_limit", "last_aggregated_at"])

            evts_in_group = event_map.get((org, meter, p_start, p_end), [])
            for e in evts_in_group:
                processed_ids.append(e.id)

    if processed_ids:
        UsageEvent.objects.filter(id__in=processed_ids).update(processed=True)

    return len(processed_ids)
