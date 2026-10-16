"""Branding Serializers (Phase 4A/4B)."""

from rest_framework import serializers

from apps.branding.models import BrandAsset, BrandingProfile, BrandingRevision, validate_tokens_dict


class BrandAssetSerializer(serializers.ModelSerializer):
    class Meta:
        model = BrandAsset
        fields = [
            "id",
            "profile",
            "asset_type",
            "file_name",
            "content_type",
            "file_size",
            "file_data",
            "created_at",
        ]
        read_only_fields = ["id", "file_size", "created_at"]


class BrandingRevisionSerializer(serializers.ModelSerializer):
    logo_asset = BrandAssetSerializer(read_only=True)
    favicon_asset = BrandAssetSerializer(read_only=True)

    class Meta:
        model = BrandingRevision
        fields = [
            "id",
            "profile",
            "revision_number",
            "status",
            "tokens",
            "logo_asset",
            "favicon_asset",
            "published_at",
            "published_by",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "profile",
            "revision_number",
            "status",
            "published_at",
            "published_by",
            "created_at",
            "updated_at",
        ]

    def validate_tokens(self, value):
        if value:
            return validate_tokens_dict(value)
        return value


class SaveDraftRevisionSerializer(serializers.Serializer):
    tokens = serializers.DictField(required=False, default=dict)
    logo_asset_id = serializers.UUIDField(required=False, allow_null=True)
    favicon_asset_id = serializers.UUIDField(required=False, allow_null=True)

    def validate_tokens(self, value):
        if value:
            return validate_tokens_dict(value)
        return value


class BrandingProfileSerializer(serializers.ModelSerializer):
    active_revision = serializers.SerializerMethodField()
    latest_revision = serializers.SerializerMethodField()
    organization_name = serializers.CharField(source="organization.name", read_only=True, default=None)

    class Meta:
        model = BrandingProfile
        fields = [
            "id",
            "organization",
            "organization_name",
            "name",
            "description",
            "is_active",
            "is_global",
            "created_at",
            "updated_at",
            "active_revision",
            "latest_revision",
        ]
        read_only_fields = ["id", "is_global", "created_at", "updated_at"]

    def get_active_revision(self, obj):
        rev = obj.revisions.filter(status="published").first()
        return BrandingRevisionSerializer(rev).data if rev else None

    def get_latest_revision(self, obj):
        rev = obj.revisions.order_by("-revision_number").first()
        return BrandingRevisionSerializer(rev).data if rev else None
