"""Serializers for User Invitations (Phase 3C)."""

from rest_framework import serializers

from apps.access_control.models import Role
from apps.invitations.models import UserInvitation
from apps.organizations.models import MembershipType, Organization


class IssueInvitationSerializer(serializers.Serializer):
    """Serializer for issuing an invitation."""

    organization_id = serializers.UUIDField(required=True)
    email = serializers.EmailField(required=True)
    full_name = serializers.CharField(max_length=150, required=False, allow_blank=True, default="")
    membership_type = serializers.ChoiceField(
        choices=MembershipType.choices,
        default=MembershipType.MEMBER,
    )
    role_id = serializers.UUIDField(required=False, allow_null=True, default=None)
    product_id = serializers.UUIDField(required=False, allow_null=True, default=None)
    product_ids = serializers.ListField(child=serializers.UUIDField(), required=False, default=list)
    module_ids = serializers.ListField(child=serializers.UUIDField(), required=False, default=list)
    lms_console = serializers.CharField(max_length=50, required=False, allow_blank=True, default="")

    def validate(self, attrs):
        org_id = attrs["organization_id"]
        try:
            attrs["organization"] = Organization.objects.get(id=org_id)
        except Organization.DoesNotExist:
            raise serializers.ValidationError({"organization_id": "Organization does not exist."})

        role_id = attrs.get("role_id")
        if role_id:
            try:
                attrs["role"] = Role.objects.get(id=role_id)
            except Role.DoesNotExist:
                raise serializers.ValidationError({"role_id": "Role does not exist."})
        else:
            attrs["role"] = None

        # RBAC validation: Tenant Console requires administrative role/privileges
        lms_console = (attrs.get("lms_console") or "").strip()
        if lms_console == "tenant_console":
            role = attrs.get("role")
            is_admin = (
                attrs.get("membership_type") == MembershipType.TENANT_ADMIN
                or (role and getattr(role, "is_admin_role", False))
                or (role and getattr(role, "code", "") in ("system_tenant_admin", "tenant_admin"))
                or (role and getattr(role, "name", "") == "Tenant Administrator")
            )
            if not is_admin:
                raise serializers.ValidationError(
                    {"lms_console": "Tenant Console requires Tenant Administrator privileges."}
                )
        attrs["lms_console"] = lms_console

        # Normalize product_ids and module_ids as strings
        p_ids = [str(pid) for pid in attrs.get("product_ids", [])]
        single_pid = attrs.get("product_id")
        if single_pid and str(single_pid) not in p_ids:
            p_ids.append(str(single_pid))
        attrs["product_ids"] = p_ids
        attrs["module_ids"] = [str(mid) for mid in attrs.get("module_ids", [])]

        return attrs


class InvitationValidationResponseSerializer(serializers.ModelSerializer):
    """Public details returned for a valid invitation token."""

    organization_name = serializers.CharField(source="organization.name", read_only=True)
    organization_code = serializers.CharField(source="organization.code", read_only=True)

    class Meta:
        model = UserInvitation
        fields = [
            "id",
            "email",
            "organization_name",
            "organization_code",
            "membership_type",
            "status",
            "expires_at",
        ]


class AcceptInvitationSerializer(serializers.Serializer):
    """Serializer for setting password and accepting invitation."""

    password = serializers.CharField(
        required=True,
        write_only=True,
        min_length=8,
        trim_whitespace=False,
    )
    full_name = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=150,
        default="",
    )
