"""Serializers for Tenant Home / App Launcher API (Phase 2G).

Provides schema definitions for:
GET /api/v1/tenant/home/
"""

from rest_framework import serializers


class CapabilityItemSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    code = serializers.CharField()
    name = serializers.CharField()
    description = serializers.CharField(allow_blank=True)
    status = serializers.CharField()


class FeatureItemSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    code = serializers.CharField()
    name = serializers.CharField()
    description = serializers.CharField(allow_blank=True)
    status = serializers.CharField()
    capabilities = CapabilityItemSerializer(many=True)


class ModuleItemSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    code = serializers.CharField()
    name = serializers.CharField()
    description = serializers.CharField(allow_blank=True)
    status = serializers.CharField()
    module_state = serializers.CharField(default="available")
    features = FeatureItemSerializer(many=True, required=False)


class EntitledProductItemSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    code = serializers.CharField()
    name = serializers.CharField()
    description = serializers.CharField(allow_blank=True)
    status = serializers.CharField()
    assignment_id = serializers.UUIDField(allow_null=True, required=False)
    assigned_at = serializers.DateTimeField(allow_null=True, required=False)
    access_state = serializers.CharField(default="available")
    denial_code = serializers.CharField(allow_null=True, required=False)
    eligible_modules = ModuleItemSerializer(many=True, required=False)
    modules = ModuleItemSerializer(many=True)


class ConsoleModuleItemSerializer(serializers.Serializer):
    key = serializers.CharField()
    display_name = serializers.CharField()
    description = serializers.CharField(allow_blank=True)
    is_core = serializers.BooleanField()


class ProductSeatMetricSerializer(serializers.Serializer):
    product_id = serializers.UUIDField()
    product_code = serializers.CharField()
    product_name = serializers.CharField()
    pool_scope = serializers.CharField()
    quota_type = serializers.CharField()
    total_limit = serializers.IntegerField(allow_null=True)
    consumed_seats = serializers.IntegerField()
    available_seats = serializers.IntegerField(allow_null=True)
    is_capacity_available = serializers.BooleanField()


class SeatSummarySerializer(serializers.Serializer):
    total_assigned_seats = serializers.IntegerField()
    products = ProductSeatMetricSerializer(many=True)


class RoleSummarySerializer(serializers.Serializer):
    id = serializers.UUIDField()
    code = serializers.CharField()
    name = serializers.CharField()
    is_system_role = serializers.BooleanField()


class MembershipSummarySerializer(serializers.Serializer):
    id = serializers.UUIDField()
    membership_type = serializers.CharField()
    status = serializers.CharField()
    joined_at = serializers.DateTimeField(allow_null=True)
    role = RoleSummarySerializer(allow_null=True)


class OrganizationSummarySerializer(serializers.Serializer):
    id = serializers.UUIDField()
    code = serializers.CharField()
    name = serializers.CharField()
    description = serializers.CharField(allow_blank=True)
    status = serializers.CharField()


class TenantHomeResponseSerializer(serializers.Serializer):
    schema_version = serializers.CharField()
    organization = OrganizationSummarySerializer()
    membership = MembershipSummarySerializer()
    entitled_products = EntitledProductItemSerializer(many=True)
    products = EntitledProductItemSerializer(many=True, required=False)
    console_modules = ConsoleModuleItemSerializer(many=True)
    seat_summary = SeatSummarySerializer()
