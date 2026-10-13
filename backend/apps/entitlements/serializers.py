"""Entitlements Domain Serializers.

Provides compact list, detailed output, and strictly validated input serializers
for OrganizationProductEntitlement with minimal audit-user exposure and data protection.
"""

from rest_framework import serializers
from apps.organizations.models import Organization
from apps.product_registry.models import Product
from .models import EntitlementStatus, OrganizationProductEntitlement


ALLOWED_CREATE_FIELDS = {"organization_id", "product_id"}
PROTECTED_CREATE_FIELDS = {
    "id",
    "status",
    "created_at",
    "updated_at",
    "created_by",
    "updated_by",
    "organization",
    "product",
}

ALLOWED_UPDATE_FIELDS = {"status"}
IMMUTABLE_UPDATE_FIELDS = {
    "organization_id",
    "product_id",
    "organization",
    "product",
}
PROTECTED_UPDATE_FIELDS = {
    "id",
    "created_at",
    "updated_at",
    "created_by",
    "updated_by",
}


class EntitlementAuditUserSerializer(serializers.Serializer):
    """Minimal audit user representation adhering to DPDP data minimization principles."""

    id = serializers.UUIDField(read_only=True)
    full_name = serializers.CharField(read_only=True)


class EntitlementOrganizationSerializer(serializers.ModelSerializer):
    """Compact summary of the entitled organization."""

    id = serializers.UUIDField(read_only=True)
    code = serializers.CharField(read_only=True)
    name = serializers.CharField(read_only=True)
    status = serializers.CharField(read_only=True)

    class Meta:
        model = Organization
        fields = ["id", "code", "name", "status"]


class EntitlementProductSerializer(serializers.ModelSerializer):
    """Compact summary of the entitled product."""

    id = serializers.UUIDField(read_only=True)
    code = serializers.CharField(read_only=True)
    name = serializers.CharField(read_only=True)
    status = serializers.CharField(read_only=True)

    class Meta:
        model = Product
        fields = ["id", "code", "name", "status"]


class EntitlementListSerializer(serializers.ModelSerializer):
    """Compact summary serializer for entitlement catalog listings."""

    organization = EntitlementOrganizationSerializer(read_only=True)
    product = EntitlementProductSerializer(read_only=True)

    class Meta:
        model = OrganizationProductEntitlement
        fields = [
            "id",
            "organization",
            "product",
            "status",
            "created_at",
            "updated_at",
        ]


class EntitlementDetailSerializer(serializers.ModelSerializer):
    """Comprehensive detail serializer including parent details and audit references."""

    organization = EntitlementOrganizationSerializer(read_only=True)
    product = EntitlementProductSerializer(read_only=True)
    created_by = EntitlementAuditUserSerializer(read_only=True)
    updated_by = EntitlementAuditUserSerializer(read_only=True)

    class Meta:
        model = OrganizationProductEntitlement
        fields = [
            "id",
            "organization",
            "product",
            "status",
            "created_at",
            "updated_at",
            "created_by",
            "updated_by",
        ]


class EntitlementCreateSerializer(serializers.Serializer):
    """Input serializer for registering an entitlement between an organization and product.

    Performs strict syntax and payload structure validation without executing unlocked database queries.
    """

    organization_id = serializers.UUIDField(required=True)
    product_id = serializers.UUIDField(required=True)

    def validate(self, attrs):
        initial_data = getattr(self, "initial_data", {})
        errors = {}

        # 1. Reject protected fields
        for field in PROTECTED_CREATE_FIELDS:
            if field in initial_data:
                errors[field] = [f"Field '{field}' cannot be specified during entitlement creation."]

        # 2. Reject unknown fields
        for field in initial_data:
            if field not in ALLOWED_CREATE_FIELDS and field not in PROTECTED_CREATE_FIELDS:
                errors[field] = [f"Unsupported field '{field}'."]

        if errors:
            raise serializers.ValidationError(errors)

        return attrs


class EntitlementUpdateSerializer(serializers.Serializer):
    """Write serializer for partial updates to entitlement lifecycle status."""

    status = serializers.ChoiceField(choices=EntitlementStatus.choices, required=False)

    def validate(self, attrs):
        initial_data = getattr(self, "initial_data", {})
        errors = {}

        # 1. Reject empty payload
        if not initial_data:
            raise serializers.ValidationError({"detail": "Request body cannot be empty."})

        # 2. Reject immutable parent keys
        for field in IMMUTABLE_UPDATE_FIELDS:
            if field in initial_data:
                errors[field] = [f"Field '{field}' is immutable after entitlement creation."]

        # 3. Reject protected audit/system fields
        for field in PROTECTED_UPDATE_FIELDS:
            if field in initial_data:
                errors[field] = [f"Field '{field}' cannot be modified directly."]

        # 4. Reject unknown fields
        for field in initial_data:
            if (
                field not in ALLOWED_UPDATE_FIELDS
                and field not in IMMUTABLE_UPDATE_FIELDS
                and field not in PROTECTED_UPDATE_FIELDS
            ):
                errors[field] = [f"Unsupported field '{field}'."]

        # 5. Require status if not provided
        if "status" not in initial_data:
            errors["status"] = ["This field is required."]

        if errors:
            raise serializers.ValidationError(errors)

        return attrs
