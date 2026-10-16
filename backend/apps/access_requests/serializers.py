"""Serializers for Access Requests & Approvals (Phase 3F)."""

from rest_framework import serializers

from apps.access_requests.models import (
    AccessRequest,
    AccessRequestDecision,
    AccessRequestStatus,
)
from apps.organizations.models import Organization
from apps.product_registry.models import Product


class AccessRequestDecisionSerializer(serializers.ModelSerializer):
    approver_id = serializers.UUIDField(source="approver.id", read_only=True)
    approver_email = serializers.EmailField(source="approver.email", read_only=True)
    approver_name = serializers.CharField(source="approver.full_name", read_only=True)

    class Meta:
        model = AccessRequestDecision
        fields = [
            "id",
            "approver_id",
            "approver_email",
            "approver_name",
            "decision",
            "reason",
            "decided_at",
        ]


class AccessRequestSerializer(serializers.ModelSerializer):
    organization_id = serializers.UUIDField(source="organization.id", read_only=True)
    organization_code = serializers.CharField(source="organization.code", read_only=True)
    organization_name = serializers.CharField(source="organization.name", read_only=True)
    requester_id = serializers.UUIDField(source="requester.id", read_only=True)
    requester_email = serializers.EmailField(source="requester.email", read_only=True)
    requester_name = serializers.CharField(source="requester.full_name", read_only=True)
    product_id = serializers.UUIDField(source="product.id", read_only=True)
    product_code = serializers.CharField(source="product.code", read_only=True)
    product_name = serializers.CharField(source="product.name", read_only=True)
    decisions = AccessRequestDecisionSerializer(many=True, read_only=True)

    class Meta:
        model = AccessRequest
        fields = [
            "id",
            "organization_id",
            "organization_code",
            "organization_name",
            "requester_id",
            "requester_email",
            "requester_name",
            "product_id",
            "product_code",
            "product_name",
            "status",
            "requested_modules",
            "reason",
            "requested_at",
            "updated_at",
            "decisions",
        ]


class CreateAccessRequestSerializer(serializers.Serializer):
    organization_id = serializers.UUIDField()
    product_id = serializers.UUIDField()
    requested_modules = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        default=list,
    )
    reason = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
        max_length=500,
    )

    def validate_organization_id(self, value):
        try:
            return Organization.objects.get(id=value)
        except Organization.DoesNotExist:
            raise serializers.ValidationError("Organization not found.")

    def validate_product_id(self, value):
        try:
            return Product.objects.get(id=value)
        except Product.DoesNotExist:
            raise serializers.ValidationError("Product not found.")


class DecideAccessRequestSerializer(serializers.Serializer):
    reason = serializers.CharField(
        required=False,
        allow_blank=True,
        default="",
        max_length=500,
    )
