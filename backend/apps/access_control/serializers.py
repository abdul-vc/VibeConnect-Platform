"""Access Control Serializers (Phase 2E Stages 4 & 5).

Provides strict input and read-only presentation serializers for:
- Platform Owner: Console Module Policies and Permission Ceilings
- Tenant Admin: Access Catalog, Role CRUD/retire, and Administrative Memberships
"""

from typing import Any
from rest_framework import serializers

from apps.access_control.constants import PREDEFINED_SUPPORT_ROLES
from apps.access_control.models import AccessPermission, ConsoleModule, PlatformRoleAssignment, Role
from apps.organizations.models import OrganizationMembership


class StrictBooleanField(serializers.BooleanField):
    """Boolean field enforcing real boolean types only.

    Strictly rejects strings ('true', 'false', '1', '0'), integers (1, 0),
    nulls, and other truthy/falsy objects.
    """

    default_error_messages = {
        "invalid": "Must be a valid boolean (true or false).",
        "null": "Field may not be null.",
    }

    def to_internal_value(self, data: Any) -> bool:
        if data is None:
            self.fail("null")
        if type(data) is not bool:
            self.fail("invalid")
        return bool(data)


# =========================================================================
# Stage 4: Platform Owner Serializers
# =========================================================================

class ConsoleModulePolicyItemSerializer(serializers.Serializer):
    """Read-only presentation serializer for tenant console module policies."""

    module_key = serializers.CharField(max_length=100)
    display_name = serializers.CharField(max_length=150)
    description = serializers.CharField(allow_blank=True)
    is_core = serializers.BooleanField()
    is_active = serializers.BooleanField()
    is_enabled = serializers.BooleanField()
    can_disable = serializers.BooleanField()
    updated_at = serializers.DateTimeField(allow_null=True)


class ConsoleModulePolicyUpdateSerializer(serializers.Serializer):
    """Strict input serializer for updating an organization console module policy."""

    is_enabled = StrictBooleanField(required=True, allow_null=False)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(self.initial_data, dict):
            raise serializers.ValidationError("Request payload must be a JSON object.")

        unknown_fields = set(self.initial_data.keys()) - {"is_enabled"}
        if unknown_fields:
            fields_str = ", ".join(sorted(unknown_fields))
            raise serializers.ValidationError(
                f"Unexpected writable fields not permitted: {fields_str}."
            )
        return attrs


class PermissionCeilingItemSerializer(serializers.Serializer):
    """Read-only presentation serializer for organization permission ceilings."""

    permission_key = serializers.CharField(max_length=100)
    display_name = serializers.CharField(max_length=150)
    description = serializers.CharField(allow_blank=True)
    category = serializers.CharField(max_length=50)
    console_module = serializers.CharField(max_length=100)
    is_active = serializers.BooleanField()
    is_allowed = serializers.BooleanField()
    updated_at = serializers.DateTimeField(allow_null=True)


class PermissionCeilingUpdateSerializer(serializers.Serializer):
    """Strict input serializer for updating an organization permission ceiling."""

    is_allowed = StrictBooleanField(required=True, allow_null=False)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(self.initial_data, dict):
            raise serializers.ValidationError("Request payload must be a JSON object.")

        unknown_fields = set(self.initial_data.keys()) - {"is_allowed"}
        if unknown_fields:
            fields_str = ", ".join(sorted(unknown_fields))
            raise serializers.ValidationError(
                f"Unexpected writable fields not permitted: {fields_str}."
            )
        return attrs


# =========================================================================
# Stage 5: Tenant Admin Serializers
# =========================================================================

class AccessCatalogModuleSerializer(serializers.Serializer):
    """Read-only representation of a tenant console module in access catalog."""

    key = serializers.CharField(max_length=100)
    display_name = serializers.CharField(max_length=150)
    description = serializers.CharField(allow_blank=True)


class AccessCatalogPermissionSerializer(serializers.Serializer):
    """Read-only representation of a tenant permission in access catalog."""

    key = serializers.CharField(max_length=100)
    display_name = serializers.CharField(max_length=150)
    category = serializers.CharField(max_length=50)
    console_module = serializers.CharField(max_length=100)


class TenantAccessCatalogResponseSerializer(serializers.Serializer):
    """Full access catalog representation exposing grantable modules and permissions."""

    modules = AccessCatalogModuleSerializer(many=True)
    permissions = AccessCatalogPermissionSerializer(many=True)


class RolePermissionDetailSerializer(serializers.Serializer):
    """Nested permission item on role representations."""

    key = serializers.CharField()
    display_name = serializers.CharField()
    category = serializers.CharField()


class RoleSerializer(serializers.ModelSerializer):
    """Consistent presentation serializer for administrative roles."""

    permission_keys = serializers.SerializerMethodField()
    permissions = serializers.SerializerMethodField()
    assigned_members_count = serializers.SerializerMethodField()

    class Meta:
        model = Role
        fields = [
            "id",
            "code",
            "name",
            "description",
            "is_system_role",
            "status",
            "permission_keys",
            "permissions",
            "assigned_members_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_permission_keys(self, obj: Role) -> list[str]:
        perms = [rp.permission for rp in obj.role_permissions.all()]
        return sorted([p.key for p in perms])

    def get_permissions(self, obj: Role) -> list[dict[str, str]]:
        perms = sorted(
            [rp.permission for rp in obj.role_permissions.all()],
            key=lambda p: (p.sort_order, p.key),
        )
        return [
            {
                "key": p.key,
                "display_name": p.display_name,
                "category": p.category,
            }
            for p in perms
        ]

    def get_assigned_members_count(self, obj: Role) -> int:
        if hasattr(obj, "assigned_members_count"):
            return getattr(obj, "assigned_members_count")
        return obj.memberships.count()


class RoleCreateSerializer(serializers.Serializer):
    """Strict input serializer for creating custom organization roles."""

    name = serializers.CharField(max_length=100, required=True, allow_blank=False)
    code = serializers.CharField(max_length=64, required=True, allow_blank=False)
    description = serializers.CharField(required=False, allow_blank=True, default="")
    permission_keys = serializers.ListField(
        child=serializers.CharField(max_length=100),
        required=True,
        allow_empty=True,
    )

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(self.initial_data, dict):
            raise serializers.ValidationError("Request payload must be a JSON object.")

        unknown_fields = set(self.initial_data.keys()) - {"name", "code", "description", "permission_keys"}
        if unknown_fields:
            fields_str = ", ".join(sorted(unknown_fields))
            raise serializers.ValidationError(
                f"Unexpected writable fields not permitted: {fields_str}."
            )
        return attrs


class RoleUpdateSerializer(serializers.Serializer):
    """Strict input serializer for updating custom organization roles."""

    name = serializers.CharField(max_length=100, required=False)
    description = serializers.CharField(required=False, allow_blank=True)
    permission_keys = serializers.ListField(
        child=serializers.CharField(max_length=100),
        required=False,
        allow_empty=True,
    )

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(self.initial_data, dict):
            raise serializers.ValidationError("Request payload must be a JSON object.")

        if "code" in self.initial_data:
            raise serializers.ValidationError("Role code is immutable and cannot be updated.")

        unknown_fields = set(self.initial_data.keys()) - {"name", "description", "permission_keys"}
        if unknown_fields:
            fields_str = ", ".join(sorted(unknown_fields))
            raise serializers.ValidationError(
                f"Unexpected writable fields not permitted: {fields_str}."
            )
        return attrs


class MembershipUserSerializer(serializers.Serializer):
    """Nested user representation on administrative memberships."""

    id = serializers.UUIDField(read_only=True)
    email = serializers.EmailField(read_only=True)
    full_name = serializers.CharField(read_only=True)
    status = serializers.CharField(read_only=True)


class MembershipRoleSummarySerializer(serializers.Serializer):
    """Nested role representation on administrative memberships."""

    id = serializers.UUIDField(read_only=True)
    code = serializers.CharField(read_only=True)
    name = serializers.CharField(read_only=True)
    is_system_role = serializers.BooleanField(read_only=True)


class AdministrativeMembershipSerializer(serializers.ModelSerializer):
    """Presentation serializer for tenant administrator memberships."""

    user = MembershipUserSerializer(read_only=True)
    role = MembershipRoleSummarySerializer(read_only=True)

    class Meta:
        model = OrganizationMembership
        fields = [
            "id",
            "user",
            "membership_type",
            "status",
            "role",
            "joined_at",
        ]
        read_only_fields = fields


class MembershipRoleAssignSerializer(serializers.Serializer):
    """Strict input serializer for assigning or resetting a membership role."""

    role_id = serializers.UUIDField(required=True, allow_null=True)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(self.initial_data, dict):
            raise serializers.ValidationError("Request payload must be a JSON object.")

        if "role_id" not in self.initial_data:
            raise serializers.ValidationError({"role_id": ["This field is required."]})

        unknown_fields = set(self.initial_data.keys()) - {"role_id"}
        if unknown_fields:
            fields_str = ", ".join(sorted(unknown_fields))
            raise serializers.ValidationError(
                f"Unexpected writable fields not permitted: {fields_str}."
            )
        return attrs


class PlatformSupportOperatorAssignSerializer(serializers.Serializer):
    """Strict input serializer for granting a support role to a platform user."""

    user_id = serializers.UUIDField(required=True)
    role_code = serializers.CharField(max_length=100, required=True)

    def validate_role_code(self, value: str) -> str:
        clean_code = (value or "").strip()
        if clean_code not in PREDEFINED_SUPPORT_ROLES:
            raise serializers.ValidationError(
                f"Role '{clean_code}' is not an approved predefined support role."
            )
        return clean_code

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(self.initial_data, dict):
            raise serializers.ValidationError("Request payload must be a JSON object.")

        unknown_fields = set(self.initial_data.keys()) - {"user_id", "role_code"}
        if unknown_fields:
            fields_str = ", ".join(sorted(unknown_fields))
            raise serializers.ValidationError(
                f"Unexpected writable fields not permitted: {fields_str}."
            )
        return attrs


class PlatformSupportOperatorSerializer(serializers.ModelSerializer):
    """Read-only presentation serializer for PlatformRoleAssignment records."""

    user_id = serializers.UUIDField(source="user.id", read_only=True)
    user_email = serializers.EmailField(source="user.email", read_only=True)
    user_name = serializers.CharField(source="user.get_full_name", read_only=True)
    role_code = serializers.CharField(source="role.code", read_only=True)
    role_name = serializers.CharField(source="role.name", read_only=True)

    class Meta:
        model = PlatformRoleAssignment
        fields = [
            "id",
            "user_id",
            "user_email",
            "user_name",
            "role_code",
            "role_name",
            "created_at",
        ]
        read_only_fields = fields

