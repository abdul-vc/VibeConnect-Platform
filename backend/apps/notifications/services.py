"""Notifications Delivery & Execution Services (Phase 3A).

Provides:
- notifications.send(template_code, recipient_user, context, ...) for downstream consumers.
- Idempotent enqueueing using deterministic idempotency keys.
- Server-side template rendering with sanitized context (no secrets logged).
- Delivery executor with retry handling and edge case validation (user deactivated/retired template).
"""

from datetime import datetime
import hashlib
import logging
from typing import Any
import uuid

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.db import transaction
from django.template import Context, Template
from django.template.loader import TemplateDoesNotExist, get_template
from django.utils import timezone

from apps.notifications.models import (
    NotificationChannel,
    NotificationDelivery,
    NotificationDeliveryStatus,
    NotificationTemplate,
    NotificationTemplateStatus,
)

logger = logging.getLogger(__name__)
PlatformUser = get_user_model()


class NotificationServiceError(Exception):
    """Base exception for notification domain errors."""
    pass


class NotificationTemplateNotFoundError(NotificationServiceError):
    """Raised when an active template cannot be found for code/channel."""
    pass


class RecipientInvalidError(NotificationServiceError):
    """Raised when recipient is invalid or has no deliverable address."""
    pass


DEFAULT_NOTIFICATION_TEMPLATES = {
    "user_invitation": (
        "Hello,\n\n"
        "You have been invited to join {{ org_name }} on VibeConnect as a {{ role_name }}.\n\n"
        "Please click the secure link below to activate your account and set your password:\n"
        "{{ activation_url }}\n\n"
        "This invitation link is single-use and will expire on {{ expires_at }}.\n"
        "You must set your own password to activate your account.\n\n"
        "If you did not expect this invitation, please ignore this email."
    ),
}


def _mask_email(email: str) -> str:
    """Mask email for privacy-preserving logs (e.g. j***@example.com)."""
    if not email or "@" not in email:
        return "***"
    local, domain = email.split("@", 1)
    if len(local) <= 1:
        masked_local = "*"
    else:
        masked_local = local[0] + "***"
    return f"{masked_local}@{domain}"


def render_template_string(template_str: str, context: dict[str, Any]) -> str:
    """Render a Django template string with the provided context dictionary."""
    t = Template(template_str)
    c = Context(context)
    return t.render(c)


def get_active_template(*, code: str, channel: str = NotificationChannel.EMAIL) -> NotificationTemplate:
    """Retrieve the latest active version of a notification template by code and channel."""
    template = (
        NotificationTemplate.objects.filter(
            code=code,
            channel=channel,
            status=NotificationTemplateStatus.ACTIVE,
        )
        .order_by("-version")
        .first()
    )
    if not template:
        raise NotificationTemplateNotFoundError(f"No active notification template found for code \x27{code}\x27 [{channel}].")
    return template


def execute_delivery(delivery_id: uuid.UUID | str) -> NotificationDelivery:
    """Synchronously execute a single delivery attempt with retry and status tracking.

    Can be invoked directly or queued via async worker/threading.
    """
    clean_id = uuid.UUID(str(delivery_id))
    with transaction.atomic():
        try:
            delivery = (
                NotificationDelivery.objects.select_for_update(of=("self",))
                .select_related("template", "recipient_user")
                .get(id=clean_id)
            )
        except NotificationDelivery.DoesNotExist:
            raise NotificationServiceError(f"Delivery {clean_id} not found.")

        if delivery.status == NotificationDeliveryStatus.SENT:
            return delivery

        # Edge case: check recipient user active status
        if delivery.recipient_user and (
            not delivery.recipient_user.is_active or getattr(delivery.recipient_user, "status", None) == "disabled"
        ):
            delivery.status = NotificationDeliveryStatus.FAILED
            delivery.failure_reason = "Recipient user was deactivated or disabled prior to transmission."
            delivery.failed_at = timezone.now()
            delivery.save(update_fields=["status", "failure_reason", "failed_at"])
            logger.warning(
                "Delivery %s marked failed: recipient user deactivated.",
                delivery.id,
            )
            return delivery

        delivery.retry_count += 1

        try:
            # 1. Render subject and body
            subject = render_template_string(delivery.template.subject_template, delivery.payload_context)
            # Body rendering: reference server-side template or body_ref string
            body = None
            if not delivery.payload_context.get("body_template") and delivery.template.body_ref:
                try:
                    loaded = get_template(delivery.template.body_ref)
                    body = loaded.render(delivery.payload_context)
                except (TemplateDoesNotExist, Exception):
                    body = None

            if not body:
                body_template = (
                    delivery.payload_context.get("body_template")
                    or DEFAULT_NOTIFICATION_TEMPLATES.get(delivery.template.code)
                    or f"Notification: {subject}\n\nReference: {delivery.template.body_ref}"
                )
                body = render_template_string(body_template, delivery.payload_context)

            # 2. Transmit via channel
            if delivery.template.channel == NotificationChannel.EMAIL:
                from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "notifications@vibeconnect.internal")
                try:
                    send_mail(
                        subject=subject,
                        message=body,
                        from_email=from_email,
                        recipient_list=[delivery.recipient_email],
                        fail_silently=False,
                    )
                except Exception as mail_exc:
                    # In test environments or when mock/console backend is used
                    raise mail_exc

            delivery.status = NotificationDeliveryStatus.SENT
            delivery.sent_at = timezone.now()
            delivery.failure_reason = ""
            delivery.save(update_fields=["status", "sent_at", "failure_reason", "retry_count"])
            logger.info(
                "Notification delivery %s successfully sent to %s via %s.",
                delivery.id,
                _mask_email(delivery.recipient_email),
                delivery.template.channel,
            )
            return delivery

        except Exception as exc:
            err_msg = str(exc)
            if delivery.retry_count < delivery.max_retries:
                delivery.status = NotificationDeliveryStatus.RETRYING
                delivery.failure_reason = f"Attempt {delivery.retry_count} failed: {err_msg[:200]}"
                delivery.save(update_fields=["status", "failure_reason", "retry_count"])
                logger.warning(
                    "Delivery %s failed attempt %d/%d; will retry. Error: %s",
                    delivery.id,
                    delivery.retry_count,
                    delivery.max_retries,
                    err_msg[:100],
                )
            else:
                delivery.status = NotificationDeliveryStatus.FAILED
                delivery.failed_at = timezone.now()
                delivery.failure_reason = f"Final failure after {delivery.retry_count} attempts: {err_msg[:200]}"
                delivery.save(update_fields=["status", "failure_reason", "failed_at", "retry_count"])
                logger.error(
                    "Delivery %s permanently failed after max retries.",
                    delivery.id,
                )
            return delivery


def send(
    *,
    template_code: str,
    recipient_email: str | None = None,
    recipient_user: Any = None,
    context: dict[str, Any] | None = None,
    channel: str = NotificationChannel.EMAIL,
    idempotency_key: str | None = None,
    max_retries: int = 3,
    execute_sync: bool = True,
) -> NotificationDelivery:
    """Central service API to enqueue and deliver notifications.

    Parameters:
    - template_code: Canonical template code (e.g. \x27tenant_invitation\x27, \x27onboarding_welcome\x27).
    - recipient_email: Email string (optional if recipient_user provided).
    - recipient_user: Optional PlatformUser instance.
    - context: Sanitized context dictionary for rendering.
    - channel: Communication channel (default: email).
    - idempotency_key: Client or caller provided key. If omitted, deterministically hashed from event.
    - max_retries: Maximum delivery retries on transmission failure.
    - execute_sync: If True, executes delivery attempt immediately. If False, remains in QUEUED status.
    """
    clean_context = dict(context or {})

    # Resolve recipient email
    target_email = ""
    if recipient_email:
        target_email = recipient_email.strip().lower()
    elif recipient_user and getattr(recipient_user, "email", None):
        target_email = recipient_user.email.strip().lower()

    if not target_email or "@" not in target_email:
        raise RecipientInvalidError("A valid recipient email address or active user is required.")

    # Validate active template (immutable snapshot binding)
    template = get_active_template(code=template_code, channel=channel)

    # Resolve idempotency key
    if not idempotency_key:
        payload_hash = hashlib.sha256(f"{template.code}:{target_email}:{sorted(clean_context.items())}".encode("utf-8")).hexdigest()
        idempotency_key = f"{template.code}:{target_email}:{payload_hash[:32]}"

    # Idempotent enqueue
    with transaction.atomic():
        existing = NotificationDelivery.objects.filter(idempotency_key=idempotency_key).first()
        if existing:
            # Idempotent return without duplicate send
            return existing

        delivery = NotificationDelivery.objects.create(
            template=template,
            recipient_user=recipient_user if getattr(recipient_user, "is_authenticated", False) else None,
            recipient_email=target_email,
            idempotency_key=idempotency_key,
            status=NotificationDeliveryStatus.QUEUED,
            max_retries=max_retries,
            payload_context=clean_context,
        )

    if execute_sync:
        return execute_delivery(delivery.id)
    else:
        from apps.notifications.queue import enqueue_background_job
        enqueue_background_job(
            job_type="notification_delivery",
            payload={"delivery_id": str(delivery.id)},
        )

    return delivery


