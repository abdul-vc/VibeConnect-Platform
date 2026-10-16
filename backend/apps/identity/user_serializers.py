"""Platform User Management Serializers (Phase 2D Stage 4).

Provides request/response serialization for central user listing, creation,
profile updates, and lifecycle transitions with strict field-level protection.
"""

from django.contrib.auth import get_user_model
from rest_framework import serializers

PlatformUser = get_user_model()


class UserListSerializer(serializers.ModelSerializer):
    """Read-only serializer for central user listing."""

    class Meta:
        model = PlatformUser
        fields = [
            "id",
            "email",
            "full_name",
            "status",
            "is_active",
            "is_platform_owner",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class UserDetailSerializer(serializers.ModelSerializer):
    """Read-only serializer for central user details with zero credential leakage."""

    class Meta:
        model = PlatformUser
        fields = [
            "id",
            "email",
            "full_name",
            "status",
            "is_active",
            "is_platform_owner",
            "auth_provider",
            "email_verified_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class UserCreateSerializer(serializers.Serializer):
    """Input serializer for creating a non-privileged central user."""

    email = serializers.EmailField(max_length=254)
    full_name = serializers.CharField(max_length=150, required=False, allow_blank=True, default="")

    def validate_email(self, value: str) -> str:
        return value.strip().lower()

    def validate_full_name(self, value: str) -> str:
        return value.strip() if value else ""


class UserUpdateSerializer(serializers.Serializer):
    """Input serializer for modifying permitted user profile fields (full_name only)."""

    full_name = serializers.CharField(max_length=150, required=True, allow_blank=True)

    def validate_full_name(self, value: str) -> str:
        return value.strip() if value else ""


class UserLifecycleActionSerializer(serializers.Serializer):
    """Input serializer for lifecycle actions (suspend, disable) accepting an optional reason."""

    reason = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")

    def validate_reason(self, value: str) -> str:
        return value.strip() if value else ""


class UserAnonymizeActionSerializer(serializers.Serializer):
    """Input serializer for user anonymization requiring mandatory reason and explicit confirmation."""

    reason = serializers.CharField(max_length=500, required=True, allow_blank=False)
    confirmation = serializers.BooleanField(required=True)

    def validate_reason(self, value: str) -> str:
        clean = (value or "").strip()
        if len(clean) < 3:
            raise serializers.ValidationError("A descriptive justification of at least 3 characters is mandatory.")
        return clean

    def validate_confirmation(self, value: bool) -> bool:
        if value is not True:
            raise serializers.ValidationError("Explicit confirmation is mandatory to perform irreversible de-identification.")
        return value

