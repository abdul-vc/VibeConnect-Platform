"""Developer Console Webhook Service (Phase 6B-6).

Provides webhook subscription management, secure HMAC-SHA256 signing,
HTTP delivery with 5-second timeout, deterministic retry with 5G backoff,
dead-letter management, and audited replay capabilities.
"""

from datetime import timedelta
import hashlib
import hmac
import json
import logging
import secrets
import time
from typing import Any
import urllib.error
import urllib.request
import uuid

from django.core.exceptions import ValidationError
from django.core.validators import URLValidator
from django.db import transaction
from django.utils import timezone

from apps.auditlog.models import AuditAction
from apps.developer_console.models import (
    DeveloperApplication,
    DeveloperWebhookDelivery,
    DeveloperWebhookSubscription,
    WebhookDeliveryStatus,
    WebhookSubscriptionStatus,
)
from apps.developer_console.services.audit_service import audit_developer_webhook_event
from apps.integration_hub.retry_service import compute_backoff_delay

logger = logging.getLogger(__name__)

SUPPORTED_WEBHOOK_TOPICS = frozenset([
    "entitlement.granted",
    "entitlement.revoked",
    "assignment.created",
    "assignment.revoked",
    "product.activated",
])

DEFAULT_MAX_ATTEMPTS = 5
DEFAULT_DELIVERY_TIMEOUT_SECONDS = 5


def generate_webhook_secret() -> str:
    """Generate a cryptographically secure random signing secret."""
    return f"whsec_{secrets.token_hex(24)}"


def compute_webhook_signature(secret: str, timestamp: int, payload_str: str) -> str:
    """Compute deterministic HMAC-SHA256 hex signature over 'timestamp.payload'."""
    signed_content = f"{timestamp}.{payload_str}".encode("utf-8")
    return hmac.new(
        secret.encode("utf-8"),
        signed_content,
        hashlib.sha256,
    ).hexdigest()


def verify_webhook_signature(
    secret: str,
    signature_header: str,
    payload_str: str,
    tolerance_seconds: int = 300,
) -> bool:
    """Verify an incoming X-VibeConnect-Signature header against the secret and payload.

    Expected format: 't=<timestamp>,v1=<signature_hex>'
    Replay protection: rejects timestamps older than tolerance_seconds.
    """
    if not signature_header or not secret:
        return False

    parts = dict(
        item.split("=", 1)
        for item in signature_header.split(",")
        if "=" in item
    )
    timestamp_str = parts.get("t")
    signature_v1 = parts.get("v1")

    if not timestamp_str or not signature_v1:
        return False

    try:
        timestamp = int(timestamp_str)
    except ValueError:
        return False

    now = int(time.time())
    if abs(now - timestamp) > tolerance_seconds:
        return False

    expected_signature = compute_webhook_signature(secret, timestamp, payload_str)
    return hmac.compare_digest(expected_signature, signature_v1)


def validate_webhook_subscription_data(target_url: str, event_topics: list[str]) -> None:
    """Validate target URL and event subscription topics."""
    if not target_url or not isinstance(target_url, str):
        raise ValidationError("Target URL is required.")

    url_validator = URLValidator(schemes=["http", "https"])
    try:
        url_validator(target_url)
    except ValidationError:
        raise ValidationError(f"Invalid webhook URL: '{target_url}'. Must be a valid HTTP/HTTPS URL.")

    if not event_topics or not isinstance(event_topics, list):
        raise ValidationError("At least one event topic must be selected.")

    for topic in event_topics:
        if topic not in SUPPORTED_WEBHOOK_TOPICS:
            raise ValidationError(
                f"Unsupported event topic '{topic}'. Supported: {sorted(SUPPORTED_WEBHOOK_TOPICS)}"
            )


@transaction.atomic
def create_webhook_subscription(
    *,
    application: DeveloperApplication,
    target_url: str,
    event_topics: list[str],
    user: Any,
    request: Any,
) -> tuple[DeveloperWebhookSubscription, str]:
    """Create a new webhook subscription, generate its secret, and record audit log."""
    validate_webhook_subscription_data(target_url, event_topics)

    raw_secret = generate_webhook_secret()
    subscription = DeveloperWebhookSubscription.objects.create(
        application=application,
        target_url=target_url.strip(),
        event_topics=sorted(list(set(event_topics))),
        signing_secret=raw_secret,
        status=WebhookSubscriptionStatus.ACTIVE,
    )

    audit_developer_webhook_event(
        request=request,
        action=AuditAction.DEVELOPER_WEBHOOK_CREATED,
        subscription=subscription,
        resulting_status=subscription.status,
    )

    return subscription, raw_secret


@transaction.atomic
def rotate_webhook_secret(
    *,
    subscription: DeveloperWebhookSubscription,
    user: Any,
    request: Any,
) -> tuple[DeveloperWebhookSubscription, str]:
    """Rotate the signing secret for an existing subscription and record audit log."""
    new_raw_secret = generate_webhook_secret()
    subscription.signing_secret = new_raw_secret
    subscription.save(update_fields=["signing_secret", "updated_at"])

    audit_developer_webhook_event(
        request=request,
        action=AuditAction.DEVELOPER_WEBHOOK_SECRET_ROTATED,
        subscription=subscription,
        resulting_status=subscription.status,
    )

    return subscription, new_raw_secret


@transaction.atomic
def update_webhook_subscription(
    *,
    subscription: DeveloperWebhookSubscription,
    target_url: str | None = None,
    event_topics: list[str] | None = None,
    user: Any,
    request: Any,
) -> DeveloperWebhookSubscription:
    """Update URL or topics for an existing subscription."""
    new_url = target_url.strip() if target_url else subscription.target_url
    new_topics = event_topics if event_topics is not None else subscription.event_topics
    validate_webhook_subscription_data(new_url, new_topics)

    subscription.target_url = new_url
    subscription.event_topics = sorted(list(set(new_topics)))
    subscription.save(update_fields=["target_url", "event_topics", "updated_at"])

    audit_developer_webhook_event(
        request=request,
        action=AuditAction.DEVELOPER_WEBHOOK_UPDATED,
        subscription=subscription,
        resulting_status=subscription.status,
    )

    return subscription


@transaction.atomic
def suspend_webhook_subscription(
    *,
    subscription: DeveloperWebhookSubscription,
    reason: str,
    user: Any,
    request: Any,
) -> DeveloperWebhookSubscription:
    """Suspend a webhook subscription."""
    if subscription.status == WebhookSubscriptionStatus.REVOKED:
        raise ValidationError("Cannot suspend a revoked webhook subscription.")

    prev = subscription.status
    subscription.status = WebhookSubscriptionStatus.SUSPENDED
    subscription.save(update_fields=["status", "updated_at"])

    audit_developer_webhook_event(
        request=request,
        action=AuditAction.DEVELOPER_WEBHOOK_SUSPENDED,
        subscription=subscription,
        previous_status=prev,
        resulting_status=subscription.status,
        reason=reason,
    )

    return subscription


@transaction.atomic
def reactivate_webhook_subscription(
    *,
    subscription: DeveloperWebhookSubscription,
    user: Any,
    request: Any,
) -> DeveloperWebhookSubscription:
    """Reactivate a suspended webhook subscription."""
    if subscription.status == WebhookSubscriptionStatus.REVOKED:
        raise ValidationError("Cannot reactivate a revoked webhook subscription.")

    prev = subscription.status
    subscription.status = WebhookSubscriptionStatus.ACTIVE
    subscription.save(update_fields=["status", "updated_at"])

    audit_developer_webhook_event(
        request=request,
        action=AuditAction.DEVELOPER_WEBHOOK_REACTIVATED,
        subscription=subscription,
        previous_status=prev,
        resulting_status=subscription.status,
    )

    return subscription


@transaction.atomic
def revoke_webhook_subscription(
    *,
    subscription: DeveloperWebhookSubscription,
    reason: str,
    user: Any,
    request: Any,
) -> DeveloperWebhookSubscription:
    """Permanently revoke a webhook subscription."""
    prev = subscription.status
    subscription.status = WebhookSubscriptionStatus.REVOKED
    subscription.save(update_fields=["status", "updated_at"])

    audit_developer_webhook_event(
        request=request,
        action=AuditAction.DEVELOPER_WEBHOOK_REVOKED,
        subscription=subscription,
        previous_status=prev,
        resulting_status=subscription.status,
        reason=reason,
    )

    return subscription


def dispatch_webhook_event(
    *,
    event_type: str,
    organization: Any,
    payload: dict[str, Any],
) -> list[DeveloperWebhookDelivery]:
    """Find active subscriptions for the organization and dispatch webhook deliveries."""
    subscriptions = DeveloperWebhookSubscription.objects.filter(
        application__organization=organization,
        application__status="active",
        status=WebhookSubscriptionStatus.ACTIVE,
    )

    deliveries = []
    for sub in subscriptions:
        if event_type in sub.event_topics:
            delivery = DeveloperWebhookDelivery.objects.create(
                subscription=sub,
                event_type=event_type,
                payload=payload,
                status=WebhookDeliveryStatus.PENDING,
            )
            deliver_webhook(delivery)
            deliveries.append(delivery)

    return deliveries


def deliver_webhook(
    delivery: DeveloperWebhookDelivery,
    timeout: int = DEFAULT_DELIVERY_TIMEOUT_SECONDS,
) -> DeveloperWebhookDelivery:
    """Attempt HTTP POST delivery of a webhook event with signing and retry backoff."""
    subscription = delivery.subscription

    if subscription.status != WebhookSubscriptionStatus.ACTIVE:
        delivery.status = WebhookDeliveryStatus.FAILED
        delivery.response_body = f"Subscription is {subscription.status}; delivery skipped."
        delivery.save(update_fields=["status", "response_body", "updated_at"])
        return delivery

    now_ts = int(time.time())
    envelope = {
        "delivery_id": str(delivery.id),
        "event_id": str(delivery.event_id),
        "event_type": delivery.event_type,
        "timestamp": timezone.now().isoformat(),
        "payload": delivery.payload,
    }
    raw_json = json.dumps(envelope, separators=(",", ":"), sort_keys=True)
    signature = compute_webhook_signature(subscription.signing_secret, now_ts, raw_json)
    signature_header = f"t={now_ts},v1={signature}"

    delivery.attempt_count += 1
    req = urllib.request.Request(
        subscription.target_url,
        data=raw_json.encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "User-Agent": "VibeConnect-Webhooks/1.0",
            "X-VibeConnect-Signature": signature_header,
            "X-VibeConnect-Delivery-Id": str(delivery.id),
            "X-VibeConnect-Event-Id": str(delivery.event_id),
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status_code = resp.getcode()
            body_snippet = resp.read(512).decode("utf-8", errors="replace")
            delivery.status_code = status_code
            if 200 <= status_code < 300:
                delivery.status = WebhookDeliveryStatus.DELIVERED
                delivery.delivered_at = timezone.now()
                delivery.next_retry_at = None
                delivery.response_body = body_snippet[:256]
            else:
                _handle_delivery_failure(delivery, status_code, body_snippet)
    except urllib.error.HTTPError as e:
        body_snippet = e.read(512).decode("utf-8", errors="replace") if hasattr(e, "read") else ""
        _handle_delivery_failure(delivery, e.code, body_snippet)
    except (urllib.error.URLError, TimeoutError, Exception) as e:
        error_msg = f"{type(e).__name__}: {str(e)[:200]}"
        _handle_delivery_failure(delivery, None, error_msg)

    delivery.save()
    return delivery


def _handle_delivery_failure(
    delivery: DeveloperWebhookDelivery,
    status_code: int | None,
    detail: str,
) -> None:
    """Classify failure and apply 5G exponential backoff or dead-letter state."""
    delivery.status_code = status_code
    delivery.response_body = detail[:256]

    if delivery.attempt_count >= delivery.max_attempts:
        delivery.status = WebhookDeliveryStatus.DEAD_LETTER
        delivery.next_retry_at = None
    else:
        delivery.status = WebhookDeliveryStatus.FAILED
        backoff_seconds = compute_backoff_delay(
            attempt=delivery.attempt_count,
            base_seconds=60,
            factor=2,
            max_seconds=3600,
        )
        delivery.next_retry_at = timezone.now() + timedelta(seconds=backoff_seconds)


@transaction.atomic
def replay_webhook_delivery(
    *,
    delivery: DeveloperWebhookDelivery,
    user: Any,
    request: Any,
) -> DeveloperWebhookDelivery:
    """Manually replay a delivery (audited) while retaining delivery_id and event_id."""
    audit_developer_webhook_event(
        request=request,
        action=AuditAction.DEVELOPER_WEBHOOK_REPLAYED,
        subscription=delivery.subscription,
        delivery=delivery,
        reason="Manual delivery replay requested",
    )
    return deliver_webhook(delivery)
