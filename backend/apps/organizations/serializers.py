"""Organizations Serializers.

Implements strict whitelist serialization, input normalization, format regex validation,
protected-field rejection, data minimization, and audit-user encapsulation.
"""

import re
from rest_framework import serializers
from apps.organizations.models import Organization, OrganizationStatus

CODE_REGEX = re.compile(r"^[a-z0-9]+(?:[-_][a-z0-9]+)*$")
ALLOWED_CREATE_FIELDS = {"code", "name", "description"}
ALLOWED_UPDATE_FIELDS = {"name", "description", "status"}
PROTECTED_CREATE_FIELDS = {"id", "status", "created_at", "updated_at", "created_by", "updated_by"}
PROTECTED_UPDATE_FIELDS = {"id", "code", "created_at", "updated_at", "created_by", "updated_by"}


class OrganizationAuditUserSerializer(serializers.Serializer):
    """Minimal audit user representation preserving data privacy."""

    id = serializers.UUIDField(read_only=True)
    full_name = serializers.CharField(read_only=True)


class OrganizationListSerializer(serializers.ModelSerializer):
    """Compact list representation for organization catalog views."""

    class Meta:
        model = Organization
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


class OrganizationDetailSerializer(serializers.ModelSerializer):
    """Full detail representation including minimal audit metadata."""

    created_by = OrganizationAuditUserSerializer(read_only=True)
    updated_by = OrganizationAuditUserSerializer(read_only=True)

    class Meta:
        model = Organization
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


class OrganizationCreateSerializer(serializers.ModelSerializer):
    """Write serializer for creating new organizations starting in Draft state."""

    code = serializers.CharField(max_length=50)
    name = serializers.CharField(max_length=150)
    description = serializers.CharField(max_length=1000, required=False, allow_blank=True, default="")

    class Meta:
        model = Organization
        fields = ["code", "name", "description"]

    def validate(self, attrs):
        initial_data = getattr(self, "initial_data", {})
        errors = {}

        # 1. Reject protected server-owned fields
        for field in PROTECTED_CREATE_FIELDS:
            if field in initial_data:
                errors[field] = [f"Field '{field}' cannot be specified during organization creation."]

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
            raise serializers.ValidationError("Organization code cannot be empty.")
        if len(normalized) > 50:
            raise serializers.ValidationError("Organization code must be 50 characters or fewer.")
        if not CODE_REGEX.match(normalized):
            raise serializers.ValidationError(
                "Organization code must contain only lowercase alphanumeric characters, with optional single hyphens or underscores between characters."
            )
        if Organization.objects.filter(code__iexact=normalized).exists():
            raise serializers.ValidationError("An organization with this code already exists.")
        return normalized

    def validate_name(self, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise serializers.ValidationError("Organization name cannot be empty or whitespace only.")
        if len(stripped) > 150:
            raise serializers.ValidationError("Organization name must be 150 characters or fewer.")
        return stripped

    def validate_description(self, value: str) -> str:
        stripped = value.strip() if value else ""
        if len(stripped) > 1000:
            raise serializers.ValidationError("Organization description must be 1000 characters or fewer.")
        return stripped


class OrganizationUpdateSerializer(serializers.ModelSerializer):
    """Write serializer for partial updates to organization name, description, and status."""

    name = serializers.CharField(max_length=150, required=False)
    description = serializers.CharField(max_length=1000, required=False, allow_blank=True)
    status = serializers.ChoiceField(choices=OrganizationStatus.choices, required=False)

    class Meta:
        model = Organization
        fields = ["name", "description", "status"]

    def validate(self, attrs):
        initial_data = getattr(self, "initial_data", {})
        errors = {}

        # 1. Reject immutable code and protected fields
        if "code" in initial_data:
            errors["code"] = ["Organization code is immutable after creation."]

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
            raise serializers.ValidationError("Organization name cannot be empty or whitespace only.")
        if len(stripped) > 150:
            raise serializers.ValidationError("Organization name must be 150 characters or fewer.")
        return stripped

    def validate_description(self, value: str) -> str:
        stripped = value.strip() if value else ""
        if len(stripped) > 1000:
            raise serializers.ValidationError("Organization description must be 1000 characters or fewer.")
        return stripped
