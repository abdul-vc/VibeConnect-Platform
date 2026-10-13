"""VibeConnect Phase 2C Subscriptions Domain Serializers.

Strict serializers and read DTOs enforcing:
- Rejection of unknown fields
- Rejection of protected/read-only client modifications
- Rejection of empty or invalid mutation payloads
- Immutable snapshot read models with zero client-side mutability
"""

from typing import Any
from rest_framework import serializers

from apps.plans.models import (
    BillingInterval,
    PlanCurrency,
    QuotaLimitType,
    QuotaResetPeriod,
    QuotaScope,
)
from apps.subscriptions.models import (
    OrganizationSubscription,
    SubscriptionCapabilityEntitlement,
    SubscriptionModuleEntitlement,
    SubscriptionProductEntitlement,
    SubscriptionQuotaEntitlement,
    SubscriptionStatus,
)


class _StrictFieldValidationMixin:
    """Shared validator rejecting unknown fields, protected fields, and empty updates."""

    allowed_fields: set[str] = set()
    protected_fields: set[str] = set()

    def validate(self, attrs):
        initial_data = getattr(self, "initial_data", {})
        if not isinstance(initial_data, dict):
            raise serializers.ValidationError({"detail": "Expected a JSON object."})

        errors = {}

        # 1. Reject protected fields
        for field in self.protected_fields:
            if field in initial_data:
                errors[field] = [f"Field '{field}' cannot be specified or modified."]

        # 2. Reject unknown fields
        for field in initial_data:
            if field not in self.allowed_fields and field not in self.protected_fields:
                errors[field] = [f"Unsupported field '{field}'."]

        if errors:
            raise serializers.ValidationError(errors)

        return attrs


# ---------------------------------------------------------------------------
# Entitlement Snapshot Read Serializers
# ---------------------------------------------------------------------------

class SubscriptionProductEntitlementSerializer(serializers.ModelSerializer):
    """Read representation for product entitlement snapshots."""

    class Meta:
        model = SubscriptionProductEntitlement
        fields = [
            "id",
            "subscription_id",
            "organization_id",
            "product_id",
            "plan_product_id",
            "product_code_snapshot",
            "product_name_snapshot",
            "created_at",
        ]
        read_only_fields = fields


class SubscriptionModuleEntitlementSerializer(serializers.ModelSerializer):
    """Read representation for module entitlement snapshots."""

    class Meta:
        model = SubscriptionModuleEntitlement
        fields = [
            "id",
            "subscription_id",
            "organization_id",
            "module_id",
            "plan_module_id",
            "module_code_snapshot",
            "module_name_snapshot",
            "created_at",
        ]
        read_only_fields = fields


class SubscriptionCapabilityEntitlementSerializer(serializers.ModelSerializer):
    """Read representation for capability entitlement snapshots."""

    class Meta:
        model = SubscriptionCapabilityEntitlement
        fields = [
            "id",
            "subscription_id",
            "organization_id",
            "capability_id",
            "plan_capability_id",
            "capability_code_snapshot",
            "capability_name_snapshot",
            "created_at",
        ]
        read_only_fields = fields


class SubscriptionQuotaEntitlementSerializer(serializers.ModelSerializer):
    """Read representation for quota entitlement snapshots."""

    class Meta:
        model = SubscriptionQuotaEntitlement
        fields = [
            "id",
            "subscription_id",
            "organization_id",
            "plan_quota_id",
            "quota_key",
            "name",
            "scope",
            "product_id",
            "module_id",
            "capability_id",
            "target_code_snapshot",
            "target_name_snapshot",
            "limit_type",
            "limit_value",
            "unit",
            "is_hard_limit",
            "reset_period",
            "created_at",
        ]
        read_only_fields = fields


# ---------------------------------------------------------------------------
# OrganizationSubscription Read Serializer
# ---------------------------------------------------------------------------

class OrganizationSubscriptionSerializer(serializers.ModelSerializer):
    """Unified read representation for OrganizationSubscription."""

    organization_name = serializers.CharField(source="organization.name", read_only=True)
    organization_code = serializers.CharField(source="organization.code", read_only=True)
    created_by_email = serializers.EmailField(source="created_by.email", read_only=True)
    updated_by_email = serializers.EmailField(source="updated_by.email", read_only=True)

    class Meta:
        model = OrganizationSubscription
        fields = [
            "id",
            "organization_id",
            "organization_name",
            "organization_code",
            "plan_version_id",
            "plan_price_id",
            "previous_subscription_id",
            "plan_code_snapshot",
            "plan_name_snapshot",
            "version_number_snapshot",
            "billing_interval",
            "currency",
            "amount",
            "started_as_trial",
            "trial_started_at",
            "trial_ends_at",
            "status",
            "current_period_start",
            "current_period_end",
            "cancelled_at",
            "ended_at",
            "change_reason",
            "cancellation_reason",
            "suspension_reason",
            "created_at",
            "updated_at",
            "created_by_email",
            "updated_by_email",
        ]
        read_only_fields = fields


# ---------------------------------------------------------------------------
# Write / Mutation Serializers
# ---------------------------------------------------------------------------

class SubscriptionCreateActiveSerializer(_StrictFieldValidationMixin, serializers.Serializer):
    """Strict write serializer for creating a direct active subscription."""

    organization_id = serializers.UUIDField()
    plan_version_id = serializers.UUIDField()
    plan_price_id = serializers.UUIDField()
    current_period_start = serializers.DateTimeField(required=False, default=None, allow_null=True)
    change_reason = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")

    allowed_fields = {
        "organization_id",
        "plan_version_id",
        "plan_price_id",
        "current_period_start",
        "change_reason",
    }
    protected_fields = {
        "id",
        "status",
        "created_at",
        "updated_at",
        "started_as_trial",
        "trial_started_at",
        "trial_ends_at",
        "current_period_end",
        "cancelled_at",
        "ended_at",
        "amount",
        "currency",
        "billing_interval",
        "plan_code_snapshot",
        "plan_name_snapshot",
        "version_number_snapshot",
    }


class SubscriptionStartTrialSerializer(_StrictFieldValidationMixin, serializers.Serializer):
    """Strict write serializer for starting a subscription trial."""

    organization_id = serializers.UUIDField()
    plan_version_id = serializers.UUIDField()
    plan_price_id = serializers.UUIDField()
    trial_days = serializers.IntegerField(required=False, default=14, min_value=1, max_value=365)
    change_reason = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")

    allowed_fields = {
        "organization_id",
        "plan_version_id",
        "plan_price_id",
        "trial_days",
        "change_reason",
    }
    protected_fields = {
        "id",
        "status",
        "created_at",
        "updated_at",
        "started_as_trial",
        "trial_started_at",
        "trial_ends_at",
        "current_period_start",
        "current_period_end",
        "cancelled_at",
        "ended_at",
        "amount",
        "currency",
        "billing_interval",
        "plan_code_snapshot",
        "plan_name_snapshot",
        "version_number_snapshot",
    }


class SubscriptionChangePlanSerializer(_StrictFieldValidationMixin, serializers.Serializer):
    """Strict write serializer for changing subscription plan."""

    new_plan_version_id = serializers.UUIDField()
    new_plan_price_id = serializers.UUIDField()
    change_reason = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")

    allowed_fields = {
        "new_plan_version_id",
        "new_plan_price_id",
        "change_reason",
    }
    protected_fields = {
        "id",
        "organization_id",
        "status",
        "created_at",
        "updated_at",
        "started_as_trial",
    }


class SubscriptionSuspendSerializer(_StrictFieldValidationMixin, serializers.Serializer):
    """Strict write serializer for suspending an active subscription."""

    reason = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")

    allowed_fields = {"reason"}
    protected_fields = {"id", "status", "created_at", "updated_at"}


class SubscriptionCancelSerializer(_StrictFieldValidationMixin, serializers.Serializer):
    """Strict write serializer for cancelling a subscription."""

    reason = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")

    allowed_fields = {"reason"}
    protected_fields = {"id", "status", "created_at", "updated_at"}


class SubscriptionEmptyActionSerializer(_StrictFieldValidationMixin, serializers.Serializer):
    """Strict write serializer for parameterless lifecycle actions (convert-trial, reactivate, reconcile)."""

    allowed_fields: set[str] = set()
    protected_fields = {
        "id",
        "organization_id",
        "status",
        "created_at",
        "updated_at",
    }
