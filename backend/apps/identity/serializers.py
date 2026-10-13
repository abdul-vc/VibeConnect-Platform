"""Identity Domain Serializers.

Safe serializers for platform authentication and profile representation.
"""

from rest_framework import serializers
from .models import PlatformUser, PlatformUserManager


class LoginSerializer(serializers.Serializer):
    """Validates structural login credentials.

    Enforces email normalization, bounded lengths, and write-only passwords
    without stripping significant whitespace.
    """

    email = serializers.EmailField(max_length=255, required=True)
    password = serializers.CharField(
        max_length=128,
        required=True,
        write_only=True,
        trim_whitespace=False,
    )

    def validate_email(self, value: str) -> str:
        return PlatformUserManager.normalize_email(value)


class PlatformUserProfileSerializer(serializers.ModelSerializer):
    """Sanitized user profile serializer.

    Restricted strictly to minimal fields required for platform UI shell.
    """

    class Meta:
        model = PlatformUser
        fields = [
            "id",
            "email",
            "full_name",
            "is_platform_owner",
        ]
        read_only_fields = [
            "id",
            "email",
            "full_name",
            "is_platform_owner",
        ]
