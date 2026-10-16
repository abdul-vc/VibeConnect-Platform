"""Organization Membership Serializers (Phase 2D Stage 4).

Provides request/response serialization for organization membership listing,
creation, role updates, and lifecycle transitions with strict field-level protection.
"""

from django.contrib.auth import get_user_model
from rest_framework import serializers

from apps.organizations.models import (
    MembershipType,
    OrganizationMembership,
)

PlatformUser = get_user_model()


class MembershipUserSummarySerializer(serializers.ModelSerializer):
    """Sanitized user summary embedded inside membership responses."""

    class Meta:
        model = PlatformUser
        fields = ["id", "email", "full_name", "status"]
        read_only_fields = fields


class MembershipRoleSummarySerializer(serializers.Serializer):
    """Sanitized role summary embedded inside membership responses."""

    id = serializers.UUIDField(read_only=True)
    code = serializers.CharField(read_only=True)
    name = serializers.CharField(read_only=True)
    is_system_role = serializers.BooleanField(read_only=True)


class OrganizationMembershipListSerializer(serializers.ModelSerializer):
    """Read-only serializer for organization memberships listing."""

    user = MembershipUserSummarySerializer(read_only=True)
    organization_id = serializers.UUIDField(source="organization.id", read_only=True)
    role = MembershipRoleSummarySerializer(read_only=True, allow_null=True)

    class Meta:
        model = OrganizationMembership
        fields = [
            "id",
            "organization_id",
            "user",
            "membership_type",
            "status",
            "role",
            "joined_at",
            "ended_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class OrganizationMembershipDetailSerializer(serializers.ModelSerializer):
    """Read-only serializer for organization membership detail."""

    user = MembershipUserSummarySerializer(read_only=True)
    organization_id = serializers.UUIDField(source="organization.id", read_only=True)
    role = MembershipRoleSummarySerializer(read_only=True, allow_null=True)

    class Meta:
        model = OrganizationMembership
        fields = [
            "id",
            "organization_id",
            "user",
            "membership_type",
            "status",
            "role",
            "joined_at",
            "ended_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class OrganizationMembershipCreateSerializer(serializers.Serializer):
    """Input serializer for granting membership in an organization."""

    user_id = serializers.UUIDField()
    membership_type = serializers.ChoiceField(
        choices=MembershipType.values,
        default=MembershipType.MEMBER,
    )


class OrganizationMembershipUpdateSerializer(serializers.Serializer):
    """Input serializer for modifying membership_type (member <-> tenant_admin)."""

    membership_type = serializers.ChoiceField(choices=MembershipType.values)


class MembershipLifecycleActionSerializer(serializers.Serializer):
    """Input serializer for lifecycle actions (suspend, end) accepting an optional reason."""

    reason = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")

    def validate_reason(self, value: str) -> str:
        return value.strip() if value else ""
