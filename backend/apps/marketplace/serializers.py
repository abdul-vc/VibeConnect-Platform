"""Marketplace Domain Serializers (Phase 6A Stage 4).

Provides input validation and response serialization for tenant catalog,
product detail, product enablement, tenant product requests, and public catalog.
"""

from rest_framework import serializers

from apps.marketplace.models import TenantProductRequest


# ---------------------------------------------------------------------------
# Catalog & Detail Output Serializers
# ---------------------------------------------------------------------------

class MarketplacePriceSerializer(serializers.Serializer):
    currency = serializers.CharField()
    amount = serializers.CharField()
    billing_interval = serializers.CharField()


class MarketplacePlanSerializer(serializers.Serializer):
    plan_version_id = serializers.UUIDField()
    plan_id = serializers.UUIDField(required=False)
    plan_name = serializers.CharField()
    plan_code = serializers.CharField()
    version = serializers.CharField(required=False)
    is_public = serializers.BooleanField(required=False)
    prices = MarketplacePriceSerializer(many=True, default=list)


class MarketplaceMediaSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    media_type = serializers.CharField()
    title = serializers.CharField()
    url = serializers.URLField()
    display_order = serializers.IntegerField()


class MarketplaceFeatureSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    code = serializers.CharField()
    name = serializers.CharField()
    description = serializers.CharField(allow_blank=True)


class MarketplaceModuleSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    code = serializers.CharField()
    name = serializers.CharField()
    description = serializers.CharField(allow_blank=True)
    features = MarketplaceFeatureSerializer(many=True, default=list)


class MarketplaceProductListSerializer(serializers.Serializer):
    """Exposes only the frozen fields defined for Stage 2 tenant catalog."""

    id = serializers.UUIDField()
    code = serializers.CharField()
    name = serializers.CharField()
    tagline = serializers.CharField(allow_blank=True)
    description = serializers.CharField(allow_blank=True)
    icon_url = serializers.URLField(allow_null=True, required=False)
    media = MarketplaceMediaSerializer(many=True, required=False)
    integration_status = serializers.CharField()
    tenant_state = serializers.CharField()
    can_enable = serializers.BooleanField()
    can_request = serializers.BooleanField()
    plans_count = serializers.IntegerField()


class MarketplaceProductDetailSerializer(serializers.Serializer):
    """Complete tenant-aware product detail for the marketplace view."""

    id = serializers.UUIDField()
    code = serializers.CharField()
    name = serializers.CharField()
    description = serializers.CharField(allow_blank=True)
    tagline = serializers.CharField(allow_blank=True)
    overview = serializers.CharField(allow_blank=True)
    icon_url = serializers.URLField(allow_null=True, required=False)
    media = MarketplaceMediaSerializer(many=True, default=list)
    integration_status = serializers.CharField()
    tenant_state = serializers.CharField()
    can_enable = serializers.BooleanField()
    can_request = serializers.BooleanField()
    modules = MarketplaceModuleSerializer(many=True, default=list)
    plans_count = serializers.IntegerField()
    plans = MarketplacePlanSerializer(many=True, default=list)
    entitlement = serializers.DictField(allow_null=True, required=False)
    pending_request = serializers.DictField(allow_null=True, required=False)


class PublicMarketplaceProductSerializer(serializers.Serializer):
    """Globally public catalog item with zero tenant state and only public plans."""

    id = serializers.UUIDField()
    code = serializers.CharField()
    name = serializers.CharField()
    description = serializers.CharField(allow_blank=True)
    tagline = serializers.CharField(allow_blank=True)
    overview = serializers.CharField(allow_blank=True)
    icon_url = serializers.URLField(allow_null=True, required=False)
    media = MarketplaceMediaSerializer(many=True, default=list)
    plans_count = serializers.IntegerField()
    plans = MarketplacePlanSerializer(many=True, default=list)


# ---------------------------------------------------------------------------
# Action Input Serializers
# ---------------------------------------------------------------------------

class MarketplaceProductEnableSerializer(serializers.Serializer):
    """Input payload for self-service product enablement."""

    plan_version_id = serializers.UUIDField(required=False, allow_null=True)


class TenantProductRequestCreateSerializer(serializers.Serializer):
    """Input payload for Tenant Admin product adoption requests."""

    requested_plan_id = serializers.UUIDField(required=False, allow_null=True)
    notes = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
        max_length=2000,
    )


# ---------------------------------------------------------------------------
# Request Model Output Serializer
# ---------------------------------------------------------------------------

class TenantProductRequestSerializer(serializers.ModelSerializer):
    organization_code = serializers.CharField(source="organization.code", read_only=True)
    product_code = serializers.CharField(source="product.code", read_only=True)
    product_name = serializers.CharField(source="product.name", read_only=True)

    class Meta:
        model = TenantProductRequest
        fields = [
            "id",
            "organization_id",
            "organization_code",
            "product_id",
            "product_code",
            "product_name",
            "requested_plan_id",
            "status",
            "notes",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields
