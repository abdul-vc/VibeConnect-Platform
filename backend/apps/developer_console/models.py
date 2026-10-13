import uuid
from django.conf import settings
from django.db import models


class DeveloperApplication(models.Model):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.PROTECT,
        related_name="developer_applications",
    )
    name = models.CharField(max_length=128)
    description = models.TextField(
        blank=True,
        default="",
    )
    status = models.CharField(
        max_length=32,
        choices=[
            ("active", "Active"),
            ("suspended", "Suspended"),
            ("revoked", "Revoked"),
        ],
        default="active",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_developer_applications",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "developer_applications"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.name} ({self.organization.code})"


class DeveloperApiKey(models.Model):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    application = models.ForeignKey(
        DeveloperApplication,
        on_delete=models.CASCADE,
        related_name="api_keys",
    )
    name = models.CharField(max_length=64)
    key_prefix = models.CharField(
        max_length=17,
        unique=True,
        editable=False,
        help_text="Indexed lookup prefix in the format 'vck_live_<8-hex>'",
    )
    hashed_secret = models.CharField(
        max_length=128,
        editable=False,
    )
    scopes = models.JSONField(
        default=list,
    )
    status = models.CharField(
        max_length=32,
        choices=[
            ("active", "Active"),
            ("expired", "Expired"),
            ("revoked", "Revoked"),
        ],
        default="active",
    )
    expires_at = models.DateTimeField(
        null=True,
        blank=True,
    )
    last_used_at = models.DateTimeField(
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
    )
    revoked_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    class Meta:
        db_table = "developer_api_keys"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.name} [{self.key_prefix}] ({self.status})"


class WebhookSubscriptionStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    SUSPENDED = "suspended", "Suspended"
    REVOKED = "revoked", "Revoked"


class WebhookDeliveryStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    DELIVERED = "delivered", "Delivered"
    FAILED = "failed", "Failed"
    DEAD_LETTER = "dead_letter", "Dead Letter"


class DeveloperWebhookSubscription(models.Model):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    application = models.ForeignKey(
        DeveloperApplication,
        on_delete=models.CASCADE,
        related_name="webhook_subscriptions",
    )
    target_url = models.URLField(max_length=512)
    event_topics = models.JSONField(
        default=list,
        help_text="List of subscribed event topics, e.g. ['entitlement.granted']",
    )
    status = models.CharField(
        max_length=32,
        choices=WebhookSubscriptionStatus.choices,
        default=WebhookSubscriptionStatus.ACTIVE,
    )
    signing_secret = models.CharField(
        max_length=128,
        editable=False,
        help_text="HMAC-SHA256 signing secret",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "developer_webhook_subscriptions"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"WebhookSub [{self.id}] -> {self.target_url} ({self.status})"


class DeveloperWebhookDelivery(models.Model):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    subscription = models.ForeignKey(
        DeveloperWebhookSubscription,
        on_delete=models.CASCADE,
        related_name="deliveries",
    )
    event_id = models.UUIDField(
        default=uuid.uuid4,
        editable=False,
    )
    event_type = models.CharField(max_length=64)
    payload = models.JSONField(default=dict)
    status = models.CharField(
        max_length=32,
        choices=WebhookDeliveryStatus.choices,
        default=WebhookDeliveryStatus.PENDING,
    )
    status_code = models.IntegerField(null=True, blank=True)
    attempt_count = models.IntegerField(default=0)
    max_attempts = models.IntegerField(default=5)
    next_retry_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    response_body = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "developer_webhook_deliveries"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"WebhookDelivery [{self.id}] {self.event_type} ({self.status})"
