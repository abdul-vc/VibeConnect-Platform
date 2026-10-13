"""Serializers for Assignment Domain APIs (Phase 2F Part D).

Implements strict request validation and response formatting for:
- Assignment list (paginated, enabled_module_count)
- Assignment detail (nested user, membership, product, modules)
- Create assignment
- Suspend / revoke lifecycle actions
- Module replacement
- Selector endpoints (products, members, modules)
"""

import uuid
from rest_framework import serializers

from apps.assignments.models import UserModuleAssignment, UserProductAssignment
from apps.organizations.models import OrganizationMembership
from apps.product_registry.models import Product, ProductModule


class UserNestedSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    email = serializers.EmailField()
    full_name = serializers.CharField()


class ProductNestedSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    code = serializers.CharField()
    name = serializers.CharField()


class MembershipNestedSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    role = serializers.SerializerMethodField()
    status = serializers.CharField()

    def get_role(self, obj) -> str:
        if getattr(obj, "role", None) is not None:
            return obj.role.code
        return getattr(obj, "membership_type", "member")


class AssignmentModuleSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    module_id = serializers.UUIDField(source="module.id")
    code = serializers.CharField(source="module.code")
    name = serializers.CharField(source="module.name")
    is_enabled = serializers.BooleanField()


class AssignmentListSerializer(serializers.ModelSerializer):
    user = UserNestedSerializer(read_only=True)
    product = ProductNestedSerializer(read_only=True)
    enabled_module_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = UserProductAssignment
        fields = [
            "id",
            "user",
            "product",
            "status",
            "assigned_at",
            "last_suspended_at",
            "last_reactivated_at",
            "revoked_at",
            "suspension_reason",
            "revocation_reason",
            "enabled_module_count",
            "created_at",
            "updated_at",
        ]


class AssignmentDetailSerializer(serializers.ModelSerializer):
    user = UserNestedSerializer(read_only=True)
    membership = MembershipNestedSerializer(read_only=True)
    product = ProductNestedSerializer(read_only=True)
    modules = serializers.SerializerMethodField()

    class Meta:
        model = UserProductAssignment
        fields = [
            "id",
            "user",
            "membership",
            "product",
            "status",
            "assigned_at",
            "last_suspended_at",
            "last_reactivated_at",
            "revoked_at",
            "suspension_reason",
            "revocation_reason",
            "modules",
            "created_at",
            "updated_at",
        ]

    def get_modules(self, obj) -> list[dict]:
        qs = obj.module_assignments.filter(is_enabled=True).select_related("module").order_by("module__name", "module__code", "module__id")
        return [
            {
                "id": str(ma.id),
                "module_id": str(ma.module.id),
                "code": ma.module.code,
                "name": ma.module.name,
                "is_enabled": ma.is_enabled,
            }
            for ma in qs
        ]


class AssignmentCreateSerializer(serializers.Serializer):
    user_id = serializers.UUIDField()
    product_id = serializers.UUIDField()
    module_ids = serializers.ListField(
        child=serializers.UUIDField(),
        required=False,
        default=list,
        max_length=100,
    )


class AssignmentReasonSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=500, min_length=1, trim_whitespace=True)


class AssignmentModuleReplaceSerializer(serializers.Serializer):
    module_ids = serializers.ListField(
        child=serializers.UUIDField(),
        required=False,
        default=list,
        max_length=100,
    )


class SelectorProductSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    code = serializers.CharField()
    name = serializers.CharField()
    pool_scope = serializers.CharField()
    quota_type = serializers.CharField()
    total_limit = serializers.IntegerField(allow_null=True)
    consumed_seats = serializers.IntegerField()
    available_seats = serializers.IntegerField(allow_null=True)
    is_capacity_available = serializers.BooleanField()


class SelectorMemberSerializer(serializers.Serializer):
    membership_id = serializers.UUIDField()
    user_id = serializers.UUIDField()
    email = serializers.EmailField()
    full_name = serializers.CharField()
    role_code = serializers.CharField()


class SelectorModuleSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    code = serializers.CharField()
    name = serializers.CharField()
    description = serializers.CharField(allow_blank=True)
    is_entitled = serializers.BooleanField()
