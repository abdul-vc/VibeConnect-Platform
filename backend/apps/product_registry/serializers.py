"""Product Registry Serializers.

Implements strict whitelist serialization, input normalization, format regex validation,
protected-field rejection, data minimization, and audit-user encapsulation.
"""

import re
from rest_framework import serializers
from apps.product_registry.models import (
    CatalogStatus,
    Product,
    ProductCapability,
    ProductFeature,
    ProductModule,
    ProductStatus,
)

CODE_REGEX = re.compile(r"^[a-z0-9]+(?:[-_][a-z0-9]+)*$")
ALLOWED_CREATE_FIELDS = {"code", "name", "description"}
ALLOWED_UPDATE_FIELDS = {"name", "description", "status"}
PROTECTED_CREATE_FIELDS = {"id", "status", "created_at", "updated_at", "actor", "created_by", "updated_by", "operation_source", "correlation_id"}
PROTECTED_UPDATE_FIELDS = {"id", "code", "created_at", "updated_at", "actor", "created_by", "updated_by", "operation_source", "correlation_id"}


class ProductAuditUserSerializer(serializers.Serializer):
    """Minimal audit user representation preserving data privacy."""

    id = serializers.UUIDField(read_only=True)
    full_name = serializers.CharField(read_only=True)


class ProductListSerializer(serializers.ModelSerializer):
    """Compact list representation for product catalog views."""

    class Meta:
        model = Product
        fields = [
            "id",
            "code",
            "name",
            "description",
            "status",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class ProductDetailSerializer(serializers.ModelSerializer):
    """Full detail representation including minimal audit metadata."""

    created_by = ProductAuditUserSerializer(read_only=True)
    updated_by = ProductAuditUserSerializer(read_only=True)

    class Meta:
        model = Product
        fields = [
            "id",
            "code",
            "name",
            "description",
            "status",
            "created_at",
            "updated_at",
            "created_by",
            "updated_by",
        ]
        read_only_fields = fields


class ProductCreateSerializer(serializers.ModelSerializer):
    """Write serializer for creating new products starting in Draft state."""

    code = serializers.CharField(max_length=50)
    name = serializers.CharField(max_length=100)
    description = serializers.CharField(max_length=1000, required=False, allow_blank=True, default="")

    class Meta:
        model = Product
        fields = ["code", "name", "description"]

    def validate(self, attrs):
        initial_data = getattr(self, "initial_data", {})
        errors = {}

        # 1. Reject protected server-owned fields
        for field in PROTECTED_CREATE_FIELDS:
            if field in initial_data:
                errors[field] = [f"Field '{field}' cannot be specified during product creation."]

        # 2. Reject unknown fields
        for field in initial_data:
            if field not in ALLOWED_CREATE_FIELDS and field not in PROTECTED_CREATE_FIELDS:
                errors[field] = [f"Unsupported field '{field}'."]

        if errors:
            raise serializers.ValidationError(errors)

        return attrs

    def validate_code(self, value: str) -> str:
        normalized = value.strip().lower()
        if not normalized:
            raise serializers.ValidationError("Product code cannot be empty.")
        if len(normalized) > 50:
            raise serializers.ValidationError("Product code must be 50 characters or fewer.")
        if not CODE_REGEX.match(normalized):
            raise serializers.ValidationError(
                "Product code must contain only lowercase alphanumeric characters, with optional single hyphens or underscores between characters."
            )
        if Product.objects.filter(code__iexact=normalized).exists():
            raise serializers.ValidationError("A product with this code already exists.")
        return normalized

    def validate_name(self, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise serializers.ValidationError("Product name cannot be empty or whitespace only.")
        if len(stripped) > 100:
            raise serializers.ValidationError("Product name must be 100 characters or fewer.")
        return stripped

    def validate_description(self, value: str) -> str:
        stripped = value.strip() if value else ""
        if len(stripped) > 1000:
            raise serializers.ValidationError("Product description must be 1000 characters or fewer.")
        return stripped


class ProductUpdateSerializer(serializers.ModelSerializer):
    """Write serializer for partial updates to product name, description, and status."""

    name = serializers.CharField(max_length=100, required=False)
    description = serializers.CharField(max_length=1000, required=False, allow_blank=True)
    status = serializers.ChoiceField(choices=ProductStatus.choices, required=False)

    class Meta:
        model = Product
        fields = ["name", "description", "status"]

    def validate(self, attrs):
        initial_data = getattr(self, "initial_data", {})
        errors = {}

        # 1. Reject immutable code and protected fields
        if "code" in initial_data:
            errors["code"] = ["Product code is immutable after creation."]

        for field in {"id", "created_at", "updated_at", "created_by", "updated_by"}:
            if field in initial_data:
                errors[field] = [f"Field '{field}' cannot be modified."]

        # 2. Reject unknown fields
        for field in initial_data:
            if field not in ALLOWED_UPDATE_FIELDS and field not in PROTECTED_UPDATE_FIELDS:
                errors[field] = [f"Unsupported field '{field}'."]

        if errors:
            raise serializers.ValidationError(errors)

        # 3. Reject completely empty payload or payload with zero allowed fields
        present_allowed = ALLOWED_UPDATE_FIELDS.intersection(initial_data.keys())
        if not present_allowed:
            raise serializers.ValidationError({"detail": "No valid editable fields provided for update."})

        return attrs

    def validate_name(self, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise serializers.ValidationError("Product name cannot be empty or whitespace only.")
        if len(stripped) > 100:
            raise serializers.ValidationError("Product name must be 100 characters or fewer.")
        return stripped

    def validate_description(self, value: str) -> str:
        stripped = value.strip() if value else ""
        if len(stripped) > 1000:
            raise serializers.ValidationError("Product description must be 1000 characters or fewer.")
        return stripped


# ==============================================================================
# PRODUCT MODULE SERIALIZERS
# ==============================================================================

ALLOWED_MODULE_CREATE_FIELDS = {"product_id", "code", "name", "description", "display_order"}
PROTECTED_MODULE_CREATE_FIELDS = {
    "id", "module_id", "feature_id", "status", "created_at", "updated_at",
    "actor", "created_by", "updated_by", "operation_source", "correlation_id",
}
ALLOWED_MODULE_UPDATE_FIELDS = {"name", "description", "display_order", "status", "code"}
PROTECTED_MODULE_UPDATE_FIELDS = {
    "id", "product_id", "module_id", "feature_id", "created_at", "updated_at",
    "actor", "created_by", "updated_by", "operation_source", "correlation_id",
}


class ProductModuleListSerializer(serializers.ModelSerializer):
    """Compact list representation for product modules with derived ancestry and counts."""

    product_id = serializers.UUIDField(source="product.id", read_only=True)
    product_code = serializers.CharField(source="product.code", read_only=True)
    total_features_count = serializers.IntegerField(read_only=True, default=0)
    active_features_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = ProductModule
        fields = [
            "id",
            "product_id",
            "product_code",
            "code",
            "name",
            "description",
            "display_order",
            "status",
            "total_features_count",
            "active_features_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class ProductModuleDetailSerializer(serializers.ModelSerializer):
    """Full detail representation for a ProductModule."""

    product_id = serializers.UUIDField(source="product.id", read_only=True)
    product_code = serializers.CharField(source="product.code", read_only=True)
    total_features_count = serializers.IntegerField(read_only=True, default=0)
    active_features_count = serializers.IntegerField(read_only=True, default=0)
    created_by = ProductAuditUserSerializer(read_only=True)
    updated_by = ProductAuditUserSerializer(read_only=True)

    class Meta:
        model = ProductModule
        fields = [
            "id",
            "product_id",
            "product_code",
            "code",
            "name",
            "description",
            "display_order",
            "status",
            "total_features_count",
            "active_features_count",
            "created_at",
            "updated_at",
            "created_by",
            "updated_by",
        ]
        read_only_fields = fields


class ProductModuleCreateSerializer(serializers.Serializer):
    """Immediate-parent-only write serializer for creating a ProductModule."""

    product_id = serializers.UUIDField(required=True)
    code = serializers.CharField(max_length=50, required=True)
    name = serializers.CharField(max_length=100, required=True)
    description = serializers.CharField(max_length=1000, required=False, allow_blank=True, default="")
    display_order = serializers.IntegerField(min_value=0, required=False, default=0)

    def validate(self, attrs):
        initial_data = getattr(self, "initial_data", {})
        errors = {}

        for field in PROTECTED_MODULE_CREATE_FIELDS:
            if field in initial_data:
                errors[field] = [f"Field '{field}' cannot be specified during module creation."]

        for field in initial_data:
            if field not in ALLOWED_MODULE_CREATE_FIELDS and field not in PROTECTED_MODULE_CREATE_FIELDS:
                errors[field] = [f"Unsupported field '{field}'."]

        if errors:
            raise serializers.ValidationError(errors)

        return attrs

    def validate_code(self, value: str) -> str:
        normalized = value.strip().lower()
        if not normalized:
            raise serializers.ValidationError("Module code cannot be empty.")
        if len(normalized) > 50:
            raise serializers.ValidationError("Module code must be 50 characters or fewer.")
        if not CODE_REGEX.match(normalized):
            raise serializers.ValidationError(
                "Module code must contain only lowercase alphanumeric characters, with optional single hyphens or underscores between characters."
            )
        return normalized

    def validate_name(self, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise serializers.ValidationError("Module name cannot be empty or whitespace only.")
        if len(stripped) > 100:
            raise serializers.ValidationError("Module name must be 100 characters or fewer.")
        return stripped

    def validate_description(self, value: str) -> str:
        stripped = value.strip() if value else ""
        if len(stripped) > 1000:
            raise serializers.ValidationError("Module description must be 1000 characters or fewer.")
        return stripped

    def create(self, validated_data):
        clean_data = dict(validated_data)
        clean_data.pop("product_id", None)
        return ProductModule.objects.create(**clean_data)


class ProductModuleUpdateSerializer(serializers.ModelSerializer):
    """Write serializer for updating a ProductModule."""

    name = serializers.CharField(max_length=100, required=False)
    description = serializers.CharField(max_length=1000, required=False, allow_blank=True)
    display_order = serializers.IntegerField(min_value=0, required=False)
    status = serializers.ChoiceField(choices=CatalogStatus.choices, required=False)
    code = serializers.CharField(max_length=50, required=False)

    class Meta:
        model = ProductModule
        fields = ["name", "description", "display_order", "status", "code"]

    def validate(self, attrs):
        initial_data = getattr(self, "initial_data", {})
        errors = {}

        for field in PROTECTED_MODULE_UPDATE_FIELDS:
            if field in initial_data:
                errors[field] = [f"Field '{field}' cannot be modified."]

        for field in initial_data:
            if field not in ALLOWED_MODULE_UPDATE_FIELDS and field not in PROTECTED_MODULE_UPDATE_FIELDS:
                errors[field] = [f"Unsupported field '{field}'."]

        if errors:
            raise serializers.ValidationError(errors)

        present_allowed = ALLOWED_MODULE_UPDATE_FIELDS.intersection(initial_data.keys())
        if not present_allowed:
            raise serializers.ValidationError({"detail": "No valid editable fields provided for update."})

        return attrs

    def validate_code(self, value: str) -> str:
        normalized = value.strip().lower()
        if not normalized:
            raise serializers.ValidationError("Module code cannot be empty.")
        if len(normalized) > 50:
            raise serializers.ValidationError("Module code must be 50 characters or fewer.")
        if not CODE_REGEX.match(normalized):
            raise serializers.ValidationError(
                "Module code must contain only lowercase alphanumeric characters, with optional single hyphens or underscores between characters."
            )
        return normalized

    def validate_name(self, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise serializers.ValidationError("Module name cannot be empty or whitespace only.")
        if len(stripped) > 100:
            raise serializers.ValidationError("Module name must be 100 characters or fewer.")
        return stripped

    def validate_description(self, value: str) -> str:
        stripped = value.strip() if value else ""
        if len(stripped) > 1000:
            raise serializers.ValidationError("Module description must be 1000 characters or fewer.")
        return stripped


# ==============================================================================
# PRODUCT FEATURE SERIALIZERS
# ==============================================================================

ALLOWED_FEATURE_CREATE_FIELDS = {"module_id", "code", "name", "description", "display_order"}
PROTECTED_FEATURE_CREATE_FIELDS = {
    "id", "product_id", "feature_id", "status", "created_at", "updated_at",
    "actor", "created_by", "updated_by", "operation_source", "correlation_id",
}
ALLOWED_FEATURE_UPDATE_FIELDS = {"name", "description", "display_order", "status", "code"}
PROTECTED_FEATURE_UPDATE_FIELDS = {
    "id", "product_id", "module_id", "feature_id", "created_at", "updated_at",
    "actor", "created_by", "updated_by", "operation_source", "correlation_id",
}


class ProductFeatureListSerializer(serializers.ModelSerializer):
    """Compact list representation for product features with derived ancestry and counts."""

    module_id = serializers.UUIDField(source="module.id", read_only=True)
    module_code = serializers.CharField(source="module.code", read_only=True)
    product_id = serializers.UUIDField(source="module.product.id", read_only=True)
    product_code = serializers.CharField(source="module.product.code", read_only=True)
    total_capabilities_count = serializers.IntegerField(read_only=True, default=0)
    active_capabilities_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = ProductFeature
        fields = [
            "id",
            "module_id",
            "module_code",
            "product_id",
            "product_code",
            "code",
            "name",
            "description",
            "display_order",
            "status",
            "total_capabilities_count",
            "active_capabilities_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class ProductFeatureDetailSerializer(serializers.ModelSerializer):
    """Full detail representation for a ProductFeature."""

    module_id = serializers.UUIDField(source="module.id", read_only=True)
    module_code = serializers.CharField(source="module.code", read_only=True)
    product_id = serializers.UUIDField(source="module.product.id", read_only=True)
    product_code = serializers.CharField(source="module.product.code", read_only=True)
    total_capabilities_count = serializers.IntegerField(read_only=True, default=0)
    active_capabilities_count = serializers.IntegerField(read_only=True, default=0)
    created_by = ProductAuditUserSerializer(read_only=True)
    updated_by = ProductAuditUserSerializer(read_only=True)

    class Meta:
        model = ProductFeature
        fields = [
            "id",
            "module_id",
            "module_code",
            "product_id",
            "product_code",
            "code",
            "name",
            "description",
            "display_order",
            "status",
            "total_capabilities_count",
            "active_capabilities_count",
            "created_at",
            "updated_at",
            "created_by",
            "updated_by",
        ]
        read_only_fields = fields


class ProductFeatureCreateSerializer(serializers.Serializer):
    """Immediate-parent-only write serializer for creating a ProductFeature."""

    module_id = serializers.UUIDField(required=True)
    code = serializers.CharField(max_length=50, required=True)
    name = serializers.CharField(max_length=100, required=True)
    description = serializers.CharField(max_length=1000, required=False, allow_blank=True, default="")
    display_order = serializers.IntegerField(min_value=0, required=False, default=0)

    def validate(self, attrs):
        initial_data = getattr(self, "initial_data", {})
        errors = {}

        for field in PROTECTED_FEATURE_CREATE_FIELDS:
            if field in initial_data:
                errors[field] = [f"Field '{field}' cannot be specified during feature creation."]

        for field in initial_data:
            if field not in ALLOWED_FEATURE_CREATE_FIELDS and field not in PROTECTED_FEATURE_CREATE_FIELDS:
                errors[field] = [f"Unsupported field '{field}'."]

        if errors:
            raise serializers.ValidationError(errors)

        return attrs

    def validate_code(self, value: str) -> str:
        normalized = value.strip().lower()
        if not normalized:
            raise serializers.ValidationError("Feature code cannot be empty.")
        if len(normalized) > 50:
            raise serializers.ValidationError("Feature code must be 50 characters or fewer.")
        if not CODE_REGEX.match(normalized):
            raise serializers.ValidationError(
                "Feature code must contain only lowercase alphanumeric characters, with optional single hyphens or underscores between characters."
            )
        return normalized

    def validate_name(self, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise serializers.ValidationError("Feature name cannot be empty or whitespace only.")
        if len(stripped) > 100:
            raise serializers.ValidationError("Feature name must be 100 characters or fewer.")
        return stripped

    def validate_description(self, value: str) -> str:
        stripped = value.strip() if value else ""
        if len(stripped) > 1000:
            raise serializers.ValidationError("Feature description must be 1000 characters or fewer.")
        return stripped

    def create(self, validated_data):
        clean_data = dict(validated_data)
        clean_data.pop("module_id", None)
        return ProductFeature.objects.create(**clean_data)


class ProductFeatureUpdateSerializer(serializers.ModelSerializer):
    """Write serializer for updating a ProductFeature."""

    name = serializers.CharField(max_length=100, required=False)
    description = serializers.CharField(max_length=1000, required=False, allow_blank=True)
    display_order = serializers.IntegerField(min_value=0, required=False)
    status = serializers.ChoiceField(choices=CatalogStatus.choices, required=False)
    code = serializers.CharField(max_length=50, required=False)

    class Meta:
        model = ProductFeature
        fields = ["name", "description", "display_order", "status", "code"]

    def validate(self, attrs):
        initial_data = getattr(self, "initial_data", {})
        errors = {}

        for field in PROTECTED_FEATURE_UPDATE_FIELDS:
            if field in initial_data:
                errors[field] = [f"Field '{field}' cannot be modified."]

        for field in initial_data:
            if field not in ALLOWED_FEATURE_UPDATE_FIELDS and field not in PROTECTED_FEATURE_UPDATE_FIELDS:
                errors[field] = [f"Unsupported field '{field}'."]

        if errors:
            raise serializers.ValidationError(errors)

        present_allowed = ALLOWED_FEATURE_UPDATE_FIELDS.intersection(initial_data.keys())
        if not present_allowed:
            raise serializers.ValidationError({"detail": "No valid editable fields provided for update."})

        return attrs

    def validate_code(self, value: str) -> str:
        normalized = value.strip().lower()
        if not normalized:
            raise serializers.ValidationError("Feature code cannot be empty.")
        if len(normalized) > 50:
            raise serializers.ValidationError("Feature code must be 50 characters or fewer.")
        if not CODE_REGEX.match(normalized):
            raise serializers.ValidationError(
                "Feature code must contain only lowercase alphanumeric characters, with optional single hyphens or underscores between characters."
            )
        return normalized

    def validate_name(self, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise serializers.ValidationError("Feature name cannot be empty or whitespace only.")
        if len(stripped) > 100:
            raise serializers.ValidationError("Feature name must be 100 characters or fewer.")
        return stripped

    def validate_description(self, value: str) -> str:
        stripped = value.strip() if value else ""
        if len(stripped) > 1000:
            raise serializers.ValidationError("Feature description must be 1000 characters or fewer.")
        return stripped


# ==============================================================================
# PRODUCT CAPABILITY SERIALIZERS
# ==============================================================================

ALLOWED_CAPABILITY_CREATE_FIELDS = {"feature_id", "code", "name", "description", "display_order"}
PROTECTED_CAPABILITY_CREATE_FIELDS = {
    "id", "product_id", "module_id", "capability_id", "status", "created_at", "updated_at",
    "actor", "created_by", "updated_by", "operation_source", "correlation_id",
}
ALLOWED_CAPABILITY_UPDATE_FIELDS = {"name", "description", "display_order", "status", "code"}
PROTECTED_CAPABILITY_UPDATE_FIELDS = {
    "id", "product_id", "module_id", "feature_id", "capability_id", "created_at", "updated_at",
    "actor", "created_by", "updated_by", "operation_source", "correlation_id",
}


class ProductCapabilityListSerializer(serializers.ModelSerializer):
    """Compact list representation for product capabilities with derived ancestry."""

    feature_id = serializers.UUIDField(source="feature.id", read_only=True)
    feature_code = serializers.CharField(source="feature.code", read_only=True)
    module_id = serializers.UUIDField(source="feature.module.id", read_only=True)
    module_code = serializers.CharField(source="feature.module.code", read_only=True)
    product_id = serializers.UUIDField(source="feature.module.product.id", read_only=True)
    product_code = serializers.CharField(source="feature.module.product.code", read_only=True)

    class Meta:
        model = ProductCapability
        fields = [
            "id",
            "feature_id",
            "feature_code",
            "module_id",
            "module_code",
            "product_id",
            "product_code",
            "code",
            "name",
            "description",
            "display_order",
            "status",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class ProductCapabilityDetailSerializer(serializers.ModelSerializer):
    """Full detail representation for a ProductCapability."""

    feature_id = serializers.UUIDField(source="feature.id", read_only=True)
    feature_code = serializers.CharField(source="feature.code", read_only=True)
    module_id = serializers.UUIDField(source="feature.module.id", read_only=True)
    module_code = serializers.CharField(source="feature.module.code", read_only=True)
    product_id = serializers.UUIDField(source="feature.module.product.id", read_only=True)
    product_code = serializers.CharField(source="feature.module.product.code", read_only=True)
    created_by = ProductAuditUserSerializer(read_only=True)
    updated_by = ProductAuditUserSerializer(read_only=True)

    class Meta:
        model = ProductCapability
        fields = [
            "id",
            "feature_id",
            "feature_code",
            "module_id",
            "module_code",
            "product_id",
            "product_code",
            "code",
            "name",
            "description",
            "display_order",
            "status",
            "created_at",
            "updated_at",
            "created_by",
            "updated_by",
        ]
        read_only_fields = fields


class ProductCapabilityCreateSerializer(serializers.Serializer):
    """Immediate-parent-only write serializer for creating a ProductCapability."""

    feature_id = serializers.UUIDField(required=True)
    code = serializers.CharField(max_length=50, required=True)
    name = serializers.CharField(max_length=100, required=True)
    description = serializers.CharField(max_length=1000, required=False, allow_blank=True, default="")
    display_order = serializers.IntegerField(min_value=0, required=False, default=0)

    def validate(self, attrs):
        initial_data = getattr(self, "initial_data", {})
        errors = {}

        for field in PROTECTED_CAPABILITY_CREATE_FIELDS:
            if field in initial_data:
                errors[field] = [f"Field '{field}' cannot be specified during capability creation."]

        for field in initial_data:
            if field not in ALLOWED_CAPABILITY_CREATE_FIELDS and field not in PROTECTED_CAPABILITY_CREATE_FIELDS:
                errors[field] = [f"Unsupported field '{field}'."]

        if errors:
            raise serializers.ValidationError(errors)

        return attrs

    def validate_code(self, value: str) -> str:
        normalized = value.strip().lower()
        if not normalized:
            raise serializers.ValidationError("Capability code cannot be empty.")
        if len(normalized) > 50:
            raise serializers.ValidationError("Capability code must be 50 characters or fewer.")
        if not CODE_REGEX.match(normalized):
            raise serializers.ValidationError(
                "Capability code must contain only lowercase alphanumeric characters, with optional single hyphens or underscores between characters."
            )
        return normalized

    def validate_name(self, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise serializers.ValidationError("Capability name cannot be empty or whitespace only.")
        if len(stripped) > 100:
            raise serializers.ValidationError("Capability name must be 100 characters or fewer.")
        return stripped

    def validate_description(self, value: str) -> str:
        stripped = value.strip() if value else ""
        if len(stripped) > 1000:
            raise serializers.ValidationError("Capability description must be 1000 characters or fewer.")
        return stripped

    def create(self, validated_data):
        clean_data = dict(validated_data)
        clean_data.pop("feature_id", None)
        return ProductCapability.objects.create(**clean_data)


class ProductCapabilityUpdateSerializer(serializers.ModelSerializer):
    """Write serializer for updating a ProductCapability."""

    name = serializers.CharField(max_length=100, required=False)
    description = serializers.CharField(max_length=1000, required=False, allow_blank=True)
    display_order = serializers.IntegerField(min_value=0, required=False)
    status = serializers.ChoiceField(choices=CatalogStatus.choices, required=False)
    code = serializers.CharField(max_length=50, required=False)

    class Meta:
        model = ProductCapability
        fields = ["name", "description", "display_order", "status", "code"]

    def validate(self, attrs):
        initial_data = getattr(self, "initial_data", {})
        errors = {}

        for field in PROTECTED_CAPABILITY_UPDATE_FIELDS:
            if field in initial_data:
                errors[field] = [f"Field '{field}' cannot be modified."]

        for field in initial_data:
            if field not in ALLOWED_CAPABILITY_UPDATE_FIELDS and field not in PROTECTED_CAPABILITY_UPDATE_FIELDS:
                errors[field] = [f"Unsupported field '{field}'."]

        if errors:
            raise serializers.ValidationError(errors)

        present_allowed = ALLOWED_CAPABILITY_UPDATE_FIELDS.intersection(initial_data.keys())
        if not present_allowed:
            raise serializers.ValidationError({"detail": "No valid editable fields provided for update."})

        return attrs

    def validate_code(self, value: str) -> str:
        normalized = value.strip().lower()
        if not normalized:
            raise serializers.ValidationError("Capability code cannot be empty.")
        if len(normalized) > 50:
            raise serializers.ValidationError("Capability code must be 50 characters or fewer.")
        if not CODE_REGEX.match(normalized):
            raise serializers.ValidationError(
                "Capability code must contain only lowercase alphanumeric characters, with optional single hyphens or underscores between characters."
            )
        return normalized

    def validate_name(self, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise serializers.ValidationError("Capability name cannot be empty or whitespace only.")
        if len(stripped) > 100:
            raise serializers.ValidationError("Capability name must be 100 characters or fewer.")
        return stripped

    def validate_description(self, value: str) -> str:
        stripped = value.strip() if value else ""
        if len(stripped) > 1000:
            raise serializers.ValidationError("Capability description must be 1000 characters or fewer.")
        return stripped

