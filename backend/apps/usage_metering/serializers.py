from rest_framework import serializers

from apps.usage_metering.models import MeterDefinition, UsageBucket, UsageEvent


class UsageEventIngestionSerializer(serializers.Serializer):
    organization_id = serializers.UUIDField(required=True)
    meter_key = serializers.CharField(max_length=64, required=True)
    quantity = serializers.IntegerField(default=1, min_value=1)
    event_key = serializers.CharField(max_length=128, required=True)
    product_code = serializers.CharField(max_length=50, required=False, allow_blank=True, default="")


class UsageSummarySerializer(serializers.ModelSerializer):
    meter_key = serializers.CharField(source="meter.quota_key", read_only=True)
    name = serializers.CharField(source="meter.name", read_only=True)
    unit = serializers.CharField(source="meter.unit", read_only=True)
    organization_id = serializers.UUIDField(source="organization.id", read_only=True)
    organization_name = serializers.CharField(source="organization.name", read_only=True)

    class Meta:
        model = UsageBucket
        fields = [
            "id",
            "organization_id",
            "organization_name",
            "meter_key",
            "name",
            "unit",
            "consumed",
            "limit_value",
            "is_over_limit",
            "period_start",
            "period_end",
            "last_aggregated_at",
        ]
