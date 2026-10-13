"""Product Showcase Serializers – Phase 11."""
from rest_framework import serializers

from apps.showcase.models import (
    ProductDemoEnvironment,
    ProductLaunchConfig,
    ProductShowcaseMedia,
    ProductShowcaseProfile,
    ShowcaseVisibility,
)


class ShowcaseMediaSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductShowcaseMedia
        fields = ["id", "media_type", "title", "url", "display_order", "created_at"]
        read_only_fields = ["id", "created_at"]


class ProductShowcaseProfileSerializer(serializers.ModelSerializer):
    product_id = serializers.UUIDField(source="product.id", read_only=True)
    product_code = serializers.CharField(source="product.code", read_only=True)
    product_name = serializers.CharField(source="product.name", read_only=True)
    product_status = serializers.CharField(source="product.status", read_only=True)
    media = ShowcaseMediaSerializer(many=True, read_only=True)

    class Meta:
        model = ProductShowcaseProfile
        fields = [
            "id",
            "product_id",
            "product_code",
            "product_name",
            "product_status",
            "tagline",
            "overview",
            "visibility",
            "display_order",
            "media",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class ProductDemoEnvironmentSerializer(serializers.ModelSerializer):
    product_id = serializers.UUIDField(source="product.id", read_only=True)
    product_name = serializers.CharField(source="product.name", read_only=True)

    class Meta:
        model = ProductDemoEnvironment
        fields = [
            "id",
            "product_id",
            "product_name",
            "name",
            "base_url",
            "description",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class ProductLaunchConfigSerializer(serializers.ModelSerializer):
    target_environment_detail = ProductDemoEnvironmentSerializer(source="target_environment", read_only=True)

    class Meta:
        model = ProductLaunchConfig
        fields = [
            "id",
            "product",
            "profile",
            "launch_mode",
            "target_environment",
            "target_environment_detail",
            "allowed_targets",
            "policy",
            "notes",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class ReorderSerializer(serializers.Serializer):
    ordered_ids = serializers.ListField(child=serializers.UUIDField(), min_length=1)
