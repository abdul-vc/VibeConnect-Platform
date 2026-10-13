"""VibeConnect Phase 2B Plans Serializers.

Strict serializers and read DTOs enforcing:
- Rejection of unknown fields
- Rejection of protected/read-only client modifications
- Rejection of empty PATCH payloads
- Rejection of non-canonical money or quota strings
- Unified read representations with zero duplication
"""

from decimal import Decimal
import re
from typing import Any
from rest_framework import serializers

from apps.plans.models import (
    BillingInterval,
    Plan,
    PlanCapability,
    PlanCurrency,
    PlanModule,
    PlanPrice,
    PlanProduct,
    PlanQuota,
    PlanVersion,
    QuotaLimitType,
    QuotaResetPeriod,
    QuotaScope,
    unit_validator,
)

PLAN_CODE_REGEX = re.compile(r"^[a-z0-9]+(?:[-_][a-z0-9]+)*$")
MONEY_REGEX = re.compile(r"^(?:0|[1-9][0-9]*)\.[0-9]{2}$")
QUOTA_KEY_REGEX = re.compile(r"^[a-z0-9]+(?:[-_][a-z0-9]+)*$")
QUOTA_UNIT_REGEX = re.compile(r"^[a-z0-9_]+$")
QUOTA_NUMERIC_REGEX = re.compile(r"^(?:0|[1-9][0-9]*)$")


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

        # 3. Reject empty PATCH payload
        if getattr(self, "partial", False):
            present_allowed = self.allowed_fields.intersection(initial_data.keys())
            if not present_allowed:
                raise serializers.ValidationError(
                    {"detail": "No valid editable fields provided for update."}
                )

        return attrs


# ---------------------------------------------------------------------------
# Plan Serializers
# ---------------------------------------------------------------------------

class PlanVersionSummarySerializer(serializers.ModelSerializer):
    """Compact version representation embedded in plan details."""

    class Meta:
        model = PlanVersion
        fields = [
            "id",
            "version",
            "status",
            "change_summary",
            "activated_at",
            "retired_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class PlanSerializer(serializers.ModelSerializer):
    """Unified read representation for both Plan list and detail."""

    active_version = PlanVersionSummarySerializer(read_only=True)
    latest_version = PlanVersionSummarySerializer(read_only=True)
    total_versions_count = serializers.IntegerField(read_only=True)
    catalog_health = serializers.CharField(read_only=True)
    created_by_email = serializers.EmailField(source="created_by.email", read_only=True)
    updated_by_email = serializers.EmailField(source="updated_by.email", read_only=True)

    class Meta:
        model = Plan
        fields = [
            "id",
            "code",
            "name",
            "description",
            "is_public",
            "active_version",
            "latest_version",
            "total_versions_count",
            "catalog_health",
            "created_at",
            "updated_at",
            "created_by_email",
            "updated_by_email",
        ]
        read_only_fields = fields


class PlanCreateSerializer(_StrictFieldValidationMixin, serializers.Serializer):
    """Strict write serializer for creating a new Plan."""

    code = serializers.CharField(max_length=50)
    name = serializers.CharField(max_length=100)
    description = serializers.CharField(max_length=1000, required=False, allow_blank=True, default="")
    change_summary = serializers.CharField(max_length=1000, required=False, allow_blank=True, default="")

    allowed_fields = {"code", "name", "description", "change_summary"}
    protected_fields = {
        "id", "is_public", "created_at", "updated_at", "created_by", "updated_by",
        "active_version", "latest_version", "total_versions_count", "catalog_health",
    }

    def validate_code(self, value: str) -> str:
        code = value.strip().lower()
        if not PLAN_CODE_REGEX.match(code):
            raise serializers.ValidationError(
                "Plan code must be lowercase alphanumeric with single hyphens or underscores."
            )
        return code

    def validate_name(self, value: str) -> str:
        name = value.strip()
        if not name:
            raise serializers.ValidationError("Plan name cannot be blank.")
        return name


class PlanUpdateSerializer(_StrictFieldValidationMixin, serializers.Serializer):
    """Strict write serializer for updating plan presentation."""

    name = serializers.CharField(max_length=100, required=False)
    description = serializers.CharField(max_length=1000, required=False, allow_blank=True)
    is_public = serializers.BooleanField(required=False)

    allowed_fields = {"name", "description", "is_public"}
    protected_fields = {
        "id", "code", "created_at", "updated_at", "created_by", "updated_by",
        "active_version", "latest_version", "total_versions_count", "catalog_health",
    }

    def validate_name(self, value: str) -> str:
        name = value.strip()
        if not name:
            raise serializers.ValidationError("Plan name cannot be blank.")
        return name


# ---------------------------------------------------------------------------
# PlanVersion Serializers
# ---------------------------------------------------------------------------

class PlanVersionSerializer(serializers.ModelSerializer):
    """Unified read representation for PlanVersion list and detail."""

    catalog_health = serializers.CharField(read_only=True)
    created_by_email = serializers.EmailField(source="created_by.email", read_only=True)
    updated_by_email = serializers.EmailField(source="updated_by.email", read_only=True)

    class Meta:
        model = PlanVersion
        fields = [
            "id",
            "plan_id",
            "version",
            "status",
            "change_summary",
            "catalog_health",
            "activated_at",
            "retired_at",
            "created_at",
            "updated_at",
            "created_by_email",
            "updated_by_email",
        ]
        read_only_fields = fields


class PlanVersionCreateSerializer(_StrictFieldValidationMixin, serializers.Serializer):
    """Strict serializer for creating a blank Draft version."""

    change_summary = serializers.CharField(max_length=1000, required=False, allow_blank=True, default="")

    allowed_fields = {"change_summary"}
    protected_fields = {
        "id", "version", "status", "plan_id", "created_at", "updated_at",
        "created_by", "updated_by", "activated_at", "retired_at", "catalog_health",
    }


class PlanVersionUpdateSerializer(_StrictFieldValidationMixin, serializers.Serializer):
    """Strict serializer for updating a Draft version change summary."""

    change_summary = serializers.CharField(max_length=1000)

    allowed_fields = {"change_summary"}
    protected_fields = {
        "id", "version", "status", "plan_id", "created_at", "updated_at",
        "created_by", "updated_by", "activated_at", "retired_at", "catalog_health",
    }


class PlanVersionCloneSerializer(_StrictFieldValidationMixin, serializers.Serializer):
    """Strict serializer for cloning an existing version into a new Draft."""

    change_summary = serializers.CharField(max_length=1000, required=False, allow_blank=True, default="")

    allowed_fields = {"change_summary"}
    protected_fields = {
        "id", "version", "status", "plan_id", "source_plan_version_id",
        "created_at", "updated_at", "created_by", "updated_by", "catalog_health",
    }


class PlanVersionEmptyActionSerializer(_StrictFieldValidationMixin, serializers.Serializer):
    """Strict serializer for activate and retire actions, requiring empty payload."""

    allowed_fields = set()
    protected_fields = {
        "id", "version", "status", "plan_id", "activated_at", "retired_at",
        "created_at", "updated_at", "created_by", "updated_by",
    }


# ---------------------------------------------------------------------------
# PlanPrice Serializers
# ---------------------------------------------------------------------------

class PlanPriceSerializer(serializers.ModelSerializer):
    """Unified read representation for PlanPrice."""

    amount = serializers.SerializerMethodField()

    class Meta:
        model = PlanPrice
        fields = [
            "id",
            "plan_version_id",
            "currency",
            "billing_interval",
            "amount",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_amount(self, obj: PlanPrice) -> str:
        return f"{obj.amount:.2f}"


class PlanPriceCreateSerializer(_StrictFieldValidationMixin, serializers.Serializer):
    """Strict write serializer for creating a PlanPrice."""

    currency = serializers.ChoiceField(choices=PlanCurrency.choices)
    billing_interval = serializers.ChoiceField(choices=BillingInterval.choices)
    amount = serializers.CharField()

    allowed_fields = {"currency", "billing_interval", "amount"}
    protected_fields = {
        "id", "plan_version_id", "created_at", "updated_at", "created_by", "updated_by",
    }

    def validate_amount(self, value: Any) -> str:
        raw = getattr(self, "initial_data", {}).get("amount")
        if not isinstance(raw, str):
            raise serializers.ValidationError(
                f"Price amount must be provided as a string, got {type(raw).__name__}."
            )
        if not MONEY_REGEX.match(raw):
            raise serializers.ValidationError(
                f"Price amount '{raw}' has invalid format. Must match '^(?:0|[1-9][0-9]*)\\.[0-9]{{2}}$'."
            )
        dec = Decimal(raw)
        if dec < Decimal("0.00") or dec > Decimal("9999999999.99"):
            raise serializers.ValidationError("Price amount must be between '0.00' and '9999999999.99'.")
        return raw


class PlanPriceUpdateSerializer(_StrictFieldValidationMixin, serializers.Serializer):
    """Strict write serializer for updating a PlanPrice amount."""

    amount = serializers.CharField()

    allowed_fields = {"amount"}
    protected_fields = {
        "id", "plan_version_id", "currency", "billing_interval",
        "created_at", "updated_at", "created_by", "updated_by",
    }

    def validate_amount(self, value: Any) -> str:
        raw = getattr(self, "initial_data", {}).get("amount")
        if not isinstance(raw, str):
            raise serializers.ValidationError(
                f"Price amount must be provided as a string, got {type(raw).__name__}."
            )
        if not MONEY_REGEX.match(raw):
            raise serializers.ValidationError(
                f"Price amount '{raw}' has invalid format. Must match '^(?:0|[1-9][0-9]*)\\.[0-9]{{2}}$'."
            )
        dec = Decimal(raw)
        if dec < Decimal("0.00") or dec > Decimal("9999999999.99"):
            raise serializers.ValidationError("Price amount must be between '0.00' and '9999999999.99'.")
        return raw


# ---------------------------------------------------------------------------
# Packaging Serializers (Product, Module, Capability)
# ---------------------------------------------------------------------------

class PlanProductSerializer(serializers.ModelSerializer):
    """Unified read representation for PlanProduct."""

    product_code = serializers.CharField(source="product.code", read_only=True)
    product_name = serializers.CharField(source="product.name", read_only=True)

    class Meta:
        model = PlanProduct
        fields = [
            "id",
            "plan_version_id",
            "product_id",
            "product_code",
            "product_name",
            "created_at",
        ]
        read_only_fields = fields


class PlanProductCreateSerializer(_StrictFieldValidationMixin, serializers.Serializer):
    product_id = serializers.UUIDField()

    allowed_fields = {"product_id"}
    protected_fields = {
        "id", "plan_version_id", "created_at", "created_by",
    }


class PlanModuleSerializer(serializers.ModelSerializer):
    """Unified read representation for PlanModule."""

    module_code = serializers.CharField(source="module.code", read_only=True)
    module_name = serializers.CharField(source="module.name", read_only=True)

    class Meta:
        model = PlanModule
        fields = [
            "id",
            "plan_version_id",
            "plan_product_id",
            "module_id",
            "module_code",
            "module_name",
            "created_at",
        ]
        read_only_fields = fields


class PlanModuleCreateSerializer(_StrictFieldValidationMixin, serializers.Serializer):
    plan_product_id = serializers.UUIDField()
    module_id = serializers.UUIDField()

    allowed_fields = {"plan_product_id", "module_id"}
    protected_fields = {
        "id", "plan_version_id", "created_at", "created_by",
    }


class PlanCapabilitySerializer(serializers.ModelSerializer):
    """Unified read representation for PlanCapability."""

    capability_code = serializers.CharField(source="capability.code", read_only=True)
    capability_name = serializers.CharField(source="capability.name", read_only=True)
    feature_id = serializers.UUIDField(source="capability.feature_id", read_only=True)
    feature_code = serializers.CharField(source="capability.feature.code", read_only=True)
    feature_name = serializers.CharField(source="capability.feature.name", read_only=True)

    class Meta:
        model = PlanCapability
        fields = [
            "id",
            "plan_version_id",
            "plan_module_id",
            "capability_id",
            "capability_code",
            "capability_name",
            "feature_id",
            "feature_code",
            "feature_name",
            "created_at",
        ]
        read_only_fields = fields


class PlanCapabilityCreateSerializer(_StrictFieldValidationMixin, serializers.Serializer):
    plan_module_id = serializers.UUIDField()
    capability_id = serializers.UUIDField()

    allowed_fields = {"plan_module_id", "capability_id"}
    protected_fields = {
        "id", "plan_version_id", "created_at", "created_by",
    }




# ---------------------------------------------------------------------------
# PlanQuota Serializers
# ---------------------------------------------------------------------------

class PlanQuotaSerializer(serializers.ModelSerializer):
    """Unified read representation for PlanQuota."""

    limit_value = serializers.SerializerMethodField()
    target_id = serializers.SerializerMethodField()

    class Meta:
        model = PlanQuota
        fields = [
            "id",
            "plan_version_id",
            "scope",
            "quota_key",
            "name",
            "unit",
            "limit_type",
            "limit_value",
            "is_hard_limit",
            "reset_period",
            "target_id",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_limit_value(self, obj: PlanQuota) -> str | None:
        return str(obj.limit_value) if obj.limit_value is not None else None

    def get_target_id(self, obj: PlanQuota) -> str | None:
        tid = obj.plan_product_id or obj.plan_module_id or obj.plan_capability_id
        return str(tid) if tid else None


class PlanQuotaCreateSerializer(_StrictFieldValidationMixin, serializers.Serializer):
    """Strict write serializer for creating a PlanQuota."""

    scope = serializers.ChoiceField(choices=QuotaScope.choices)
    quota_key = serializers.CharField(max_length=64, trim_whitespace=False)
    name = serializers.CharField(max_length=100)
    unit = serializers.CharField(max_length=32, trim_whitespace=False, validators=[unit_validator])
    limit_type = serializers.ChoiceField(choices=QuotaLimitType.choices)
    limit_value = serializers.CharField(required=False, allow_null=True, default=None)
    is_hard_limit = serializers.BooleanField(required=False, default=True)
    reset_period = serializers.ChoiceField(choices=QuotaResetPeriod.choices, required=False, default="never")
    plan_product_id = serializers.UUIDField(required=False, allow_null=True, default=None)
    plan_module_id = serializers.UUIDField(required=False, allow_null=True, default=None)
    plan_capability_id = serializers.UUIDField(required=False, allow_null=True, default=None)

    allowed_fields = {
        "scope", "quota_key", "name", "unit", "limit_type", "limit_value",
        "is_hard_limit", "reset_period", "plan_product_id", "plan_module_id", "plan_capability_id",
    }
    protected_fields = {
        "id", "plan_version_id", "created_at", "updated_at", "created_by", "updated_by", "target_id",
    }

    def validate_quota_key(self, value: str) -> str:
        if value != value.strip() or any(c.isspace() for c in value):
            raise serializers.ValidationError("quota_key cannot contain whitespace.")
        if value != value.lower():
            raise serializers.ValidationError("quota_key must be lowercase.")
        if not QUOTA_KEY_REGEX.match(value):
            raise serializers.ValidationError(
                "quota_key must be lowercase alphanumeric and may contain single hyphens or underscores."
            )
        return value

    def validate_unit(self, value: str) -> str:
        if value != value.strip() or any(c.isspace() for c in value):
            raise serializers.ValidationError("unit cannot contain whitespace.")
        if value != value.lower():
            raise serializers.ValidationError("unit must be lowercase.")
        if not QUOTA_UNIT_REGEX.match(value):
            raise serializers.ValidationError("unit must be lowercase alphanumeric with underscores.")
        return value

    def validate(self, attrs):
        attrs = super().validate(attrs)
        scope = attrs.get("scope")
        limit_type = attrs.get("limit_type")
        limit_value = attrs.get("limit_value")

        # Limit value format and range
        if limit_type == QuotaLimitType.UNLIMITED:
            if limit_value is not None:
                raise serializers.ValidationError(
                    {"limit_value": ["limit_value must be null when limit_type is 'unlimited'."]}
                )
        elif limit_type == QuotaLimitType.NUMERIC:
            if limit_value is None:
                raise serializers.ValidationError(
                    {"limit_value": ["limit_value is required when limit_type is 'numeric'."]}
                )
            if not isinstance(limit_value, str):
                raise serializers.ValidationError(
                    {"limit_value": ["limit_value must be provided as a string."]}
                )
            if not QUOTA_NUMERIC_REGEX.match(limit_value):
                raise serializers.ValidationError(
                    {"limit_value": [f"Invalid canonical quota format or leading zeros: '{limit_value}'."]}
                )
            int_val = int(limit_value)
            if int_val < 0 or int_val > 9223372036854775807:
                raise serializers.ValidationError(
                    {"limit_value": ["limit_value out of 64-bit integer range."]}
                )

        # Scope and target ID consistency
        target_fields = ["plan_product_id", "plan_module_id", "plan_capability_id"]
        provided_targets = [f for f in target_fields if attrs.get(f) is not None]

        if scope == QuotaScope.PLAN:
            if provided_targets:
                raise serializers.ValidationError(
                    {"detail": "Packaging target ID cannot be provided when scope is 'plan'."}
                )
        elif scope == QuotaScope.PRODUCT:
            if attrs.get("plan_product_id") is None or len(provided_targets) != 1:
                raise serializers.ValidationError(
                    {"plan_product_id": ["Exactly plan_product_id must be provided when scope is 'product'."]}
                )
        elif scope == QuotaScope.MODULE:
            if attrs.get("plan_module_id") is None or len(provided_targets) != 1:
                raise serializers.ValidationError(
                    {"plan_module_id": ["Exactly plan_module_id must be provided when scope is 'module'."]}
                )
        elif scope == QuotaScope.CAPABILITY:
            if attrs.get("plan_capability_id") is None or len(provided_targets) != 1:
                raise serializers.ValidationError(
                    {"plan_capability_id": ["Exactly plan_capability_id must be provided when scope is 'capability'."]}
                )

        return attrs


class PlanQuotaUpdateSerializer(_StrictFieldValidationMixin, serializers.Serializer):
    """Strict write serializer for updating approved PlanQuota fields."""

    name = serializers.CharField(max_length=100, required=False)
    unit = serializers.CharField(max_length=32, required=False, trim_whitespace=False, validators=[unit_validator])
    limit_type = serializers.ChoiceField(choices=QuotaLimitType.choices, required=False)
    limit_value = serializers.CharField(required=False, allow_null=True)
    is_hard_limit = serializers.BooleanField(required=False)
    reset_period = serializers.ChoiceField(choices=QuotaResetPeriod.choices, required=False)

    allowed_fields = {"name", "unit", "limit_type", "limit_value", "is_hard_limit", "reset_period"}
    protected_fields = {
        "id", "plan_version_id", "scope", "quota_key", "target_id",
        "plan_product_id", "plan_module_id", "plan_capability_id",
        "created_at", "updated_at", "created_by", "updated_by",
    }

    def validate_unit(self, value: str) -> str:
        if value != value.strip() or any(c.isspace() for c in value):
            raise serializers.ValidationError("unit cannot contain whitespace.")
        if value != value.lower():
            raise serializers.ValidationError("unit must be lowercase.")
        if not QUOTA_UNIT_REGEX.match(value):
            raise serializers.ValidationError("unit must be lowercase alphanumeric with underscores.")
        return value

    def validate(self, attrs):
        attrs = super().validate(attrs)
        limit_type = attrs.get("limit_type")
        limit_value = attrs.get("limit_value")

        if limit_type is not None:
            if limit_type == QuotaLimitType.UNLIMITED and limit_value is not None:
                raise serializers.ValidationError(
                    {"limit_value": ["limit_value must be null when limit_type is 'unlimited'."]}
                )
        if limit_value is not None:
            if not isinstance(limit_value, str):
                raise serializers.ValidationError(
                    {"limit_value": ["limit_value must be provided as a string."]}
                )
            if not QUOTA_NUMERIC_REGEX.match(limit_value):
                raise serializers.ValidationError(
                    {"limit_value": [f"Invalid canonical quota format or leading zeros: '{limit_value}'."]}
                )
            int_val = int(limit_value)
            if int_val < 0 or int_val > 9223372036854775807:
                raise serializers.ValidationError(
                    {"limit_value": ["limit_value out of 64-bit integer range."]}
                )

        return attrs


# ---------------------------------------------------------------------------
# Public Plan Discovery Serializers
# ---------------------------------------------------------------------------

class PublicPlanPriceSerializer(serializers.Serializer):
    """Public read representation for plan prices."""

    currency = serializers.CharField()
    billing_interval = serializers.CharField()
    amount = serializers.CharField()


class PublicPlanProductSerializer(serializers.Serializer):
    """Public read representation for packaged products."""

    product_code = serializers.CharField()
    product_name = serializers.CharField()


class PublicPlanQuotaHighlightSerializer(serializers.Serializer):
    """Public read representation for quota highlights."""

    quota_key = serializers.CharField()
    name = serializers.CharField()
    limit_type = serializers.CharField()
    limit_value = serializers.IntegerField(allow_null=True)
    unit = serializers.CharField()
    reset_period = serializers.CharField()


class PublicPlanSerializer(serializers.Serializer):
    """Public unauthenticated representation for healthy, public plans."""

    plan_code = serializers.CharField()
    plan_name = serializers.CharField()
    description = serializers.CharField()
    version = serializers.IntegerField()
    prices = PublicPlanPriceSerializer(many=True)
    packaged_products = PublicPlanProductSerializer(many=True)
    quota_highlights = PublicPlanQuotaHighlightSerializer(many=True)

