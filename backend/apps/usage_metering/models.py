import uuid

from django.db import models
from django.utils import timezone


class MeterDefinition(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    quota_key = models.CharField(max_length=64, unique=True)
    name = models.CharField(max_length=100)
    scope = models.CharField(max_length=20, default="product")
    unit = models.CharField(max_length=32, default="units")
    reset_period = models.CharField(max_length=20, default="monthly")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "meter_definitions"
        verbose_name = "Meter Definition"
        verbose_name_plural = "Meter Definitions"

    def __str__(self) -> str:
        return f"{self.name} ({self.quota_key})"


class UsageEvent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="usage_events",
    )
    product = models.ForeignKey(
        "product_registry.Product",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="usage_events",
    )
    meter = models.ForeignKey(
        MeterDefinition,
        on_delete=models.PROTECT,
        related_name="events",
    )
    quantity = models.BigIntegerField(default=1)
    event_key = models.CharField(max_length=128)
    occurred_at = models.DateTimeField(default=timezone.now)
    processed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "usage_events"
        verbose_name = "Usage Event"
        verbose_name_plural = "Usage Events"
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "event_key"],
                name="uniq_org_event_key",
            )
        ]
        indexes = [
            models.Index(fields=["organization", "processed"]),
            models.Index(fields=["meter", "processed"]),
        ]

    def __str__(self) -> str:
        return f"Event {self.event_key}: {self.meter.quota_key} (+{self.quantity})"


class UsageBucket(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="usage_buckets",
    )
    meter = models.ForeignKey(
        MeterDefinition,
        on_delete=models.PROTECT,
        related_name="buckets",
    )
    period_start = models.DateTimeField()
    period_end = models.DateTimeField()
    consumed = models.BigIntegerField(default=0)
    limit_value = models.BigIntegerField(null=True, blank=True)
    is_over_limit = models.BooleanField(default=False)
    last_aggregated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "usage_buckets"
        verbose_name = "Usage Bucket"
        verbose_name_plural = "Usage Buckets"
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "meter", "period_start"],
                name="uniq_org_meter_period_start",
            )
        ]
        indexes = [
            models.Index(fields=["organization", "period_start", "period_end"]),
        ]

    def __str__(self) -> str:
        return f"{self.organization.name} - {self.meter.quota_key}: {self.consumed}/{self.limit_value}"
