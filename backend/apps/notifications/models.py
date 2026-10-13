"""Notifications Domain Models (Phase 3A).

Implements NotificationTemplate and NotificationDelivery models:
- NotificationTemplate: Versioned, channel-agnostic template definitions with body_ref references (zero plaintext secrets).
- NotificationDelivery: Delivery records with status lifecycle (queued, sent, failed, retrying) and retry tracking.
"""

import uuid
from django.conf import settings
from django.core.validators import RegexValidator
from django.db import models
from django.db.models import Q

CODE_REGEX = r"^[a-z0-9]+(?:[-_][a-z0-9]+)*$"
code_validator = RegexValidator(
    regex=CODE_REGEX,
    message="Code must be lowercase alphanumeric with single hyphens or underscores.",
)


class NotificationChannel(models.TextChoices):
    EMAIL = "email", "Email"
    IN_APP = "in_app", "In-App"
    SMS = "sms", "SMS"
    WEBHOOK = "webhook", "Webhook"


class NotificationTemplateStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    ACTIVE = "active", "Active"
    RETIRED = "retired", "Retired"


class NotificationDeliveryStatus(models.TextChoices):
    QUEUED = "queued", "Queued"
    SENT = "sent", "Sent"
    FAILED = "failed", "Failed"
    RETRYING = "retrying", "Retrying"


class NotificationTemplate(models.Model):
    """Versioned notification template definition.

    Stores a secure template reference (body_ref) rather than raw HTML or secrets.
    Templates referenced by a sent delivery become immutable and must not be mutated in-place.
    """

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    code = models.CharField(
        max_length=64,
        validators=[code_validator],
        db_index=True,
        help_text="Canonical template identifier.",
    )
    name = models.CharField(
        max_length=128,
        help_text="Human-readable name of the template.",
    )
    channel = models.CharField(
        max_length=32,
        choices=NotificationChannel.choices,
        default=NotificationChannel.EMAIL,
        help_text="Delivery communication channel.",
    )
    version = models.PositiveIntegerField(
        default=1,
        help_text="Monotonically increasing version number for the code and channel.",
    )
    subject_template = models.CharField(
        max_length=255,
        help_text="Subject line template string (e.g. Welcome to {{ org_name }}).",
    )
    body_ref = models.CharField(
        max_length=255,
        help_text="Server-side template reference identifier or path (no secrets stored).",
    )
    status = models.CharField(
        max_length=20,
        choices=NotificationTemplateStatus.choices,
        default=NotificationTemplateStatus.ACTIVE,
        db_index=True,
        help_text="Lifecycle state of the template.",
    )
    is_transactional = models.BooleanField(
        default=True,
        help_text="True for transactional notifications (e.g. invites, auth), False for marketing/informational.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "notification_templates"
        ordering = ["code", "-version"]
        constraints = [
            models.UniqueConstraint(
                fields=["code", "channel", "version"],
                name="unique_notification_template_version",
            ),
            models.CheckConstraint(
                condition=Q(status__in=NotificationTemplateStatus.values),
                name="valid_notification_template_status",
            ),
            models.CheckConstraint(
                condition=Q(channel__in=NotificationChannel.values),
                name="valid_notification_channel",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.code} [{self.channel} v{self.version}] ({self.status})"


class NotificationDelivery(models.Model):
    """Notification delivery lifecycle and execution evidence.

    Tracks idempotent dispatch, delivery status, retry attempts, and timing.
    """

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    template = models.ForeignKey(
        NotificationTemplate,
        on_delete=models.PROTECT,
        related_name="deliveries",
        help_text="Template snapshot used for this delivery.",
    )
    recipient_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="notification_deliveries",
        help_text="Recipient platform user if known.",
    )
    recipient_email = models.EmailField(
        max_length=255,
        help_text="Normalized recipient email for delivery.",
    )
    idempotency_key = models.CharField(
        max_length=128,
        unique=True,
        db_index=True,
        help_text="Unique key ensuring idempotent enqueue for the same logical event.",
    )
    status = models.CharField(
        max_length=20,
        choices=NotificationDeliveryStatus.choices,
        default=NotificationDeliveryStatus.QUEUED,
        db_index=True,
        help_text="Current state in the delivery pipeline.",
    )
    retry_count = models.PositiveIntegerField(
        default=0,
        help_text="Number of delivery attempts made.",
    )
    max_retries = models.PositiveIntegerField(
        default=3,
        help_text="Maximum allowed retry attempts before marking terminal failure.",
    )
    failure_reason = models.TextField(
        blank=True,
        default="",
        help_text="Sanitized failure diagnostic message (no sensitive data).",
    )
    payload_context = models.JSONField(
        default=dict,
        blank=True,
        help_text="Sanitized, non-secret parameters passed to the template at render time.",
    )
    queued_at = models.DateTimeField(
        auto_now_add=True,
        help_text="Timestamp when the delivery was queued.",
    )
    sent_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp when the delivery was successfully transmitted.",
    )
    failed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp of final failure.",
    )

    class Meta:
        db_table = "notification_deliveries"
        ordering = ["-queued_at"]
        constraints = [
            models.CheckConstraint(
                condition=Q(status__in=NotificationDeliveryStatus.values),
                name="valid_notification_delivery_status",
            ),
        ]

    def __str__(self) -> str:
        return f"Delivery {self.id} [{self.template.code} -> {self.recipient_email}] ({self.status})"


class BackgroundJobStatus(models.TextChoices):
    QUEUED = "queued", "Queued"
    PROCESSING = "processing", "Processing"
    COMPLETED = "completed", "Completed"
    FAILED = "failed", "Failed"


class BackgroundJob(models.Model):
    """DB-backed asynchronous job queue entity (Phase 3 Async Workers)."""

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    job_type = models.CharField(
        max_length=64,
        db_index=True,
        help_text="Canonical task identifier (e.g. notification_delivery, bulk_import_commit).",
    )
    payload = models.JSONField(
        default=dict,
        help_text="Sanitized execution arguments (no plaintext secrets).",
    )
    status = models.CharField(
        max_length=20,
        choices=BackgroundJobStatus.choices,
        default=BackgroundJobStatus.QUEUED,
        db_index=True,
    )
    attempts = models.PositiveIntegerField(default=0)
    max_attempts = models.PositiveIntegerField(default=3)
    error_message = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "background_jobs"
        ordering = ["created_at"]
        constraints = [
            models.CheckConstraint(
                condition=Q(status__in=BackgroundJobStatus.values),
                name="valid_background_job_status",
            ),
        ]

    def __str__(self) -> str:
        return f"Job {self.id} [{self.job_type}] ({self.status})"


