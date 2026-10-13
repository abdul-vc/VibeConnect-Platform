"""Serializers for Bulk Import (Phase 3D)."""

from rest_framework import serializers

from apps.bulk_import.models import BulkImportJob, BulkImportRow
from apps.organizations.models import Organization


class CreateBulkImportJobSerializer(serializers.Serializer):
    """Payload for uploading and initiating a bulk import job."""

    organization_id = serializers.UUIDField(required=True)
    idempotency_key = serializers.CharField(max_length=128, required=True)
    raw_content = serializers.CharField(required=True)
    content_type = serializers.ChoiceField(choices=["csv", "json"], default="csv")

    def validate_organization_id(self, value):
        try:
            return Organization.objects.get(id=value)
        except Organization.DoesNotExist:
            raise serializers.ValidationError("Organization not found.")


class BulkImportRowSerializer(serializers.ModelSerializer):
    """Serializer for inspection of staged rows."""

    class Meta:
        model = BulkImportRow
        fields = [
            "id",
            "row_number",
            "validation_state",
            "payload_ref",
            "error_code",
            "error_message",
            "created_at",
            "updated_at",
        ]


class BulkImportJobSerializer(serializers.ModelSerializer):
    """Detailed view of a bulk import job status and counters."""

    organization_code = serializers.CharField(source="organization.code", read_only=True, default=None)
    organization_name = serializers.CharField(source="organization.name", read_only=True, default=None)

    class Meta:
        model = BulkImportJob
        fields = [
            "id",
            "organization_id",
            "organization_code",
            "organization_name",
            "import_type",
            "status",
            "idempotency_key",
            "total_rows",
            "valid_rows",
            "invalid_rows",
            "committed_rows",
            "failed_rows",
            "error_summary",
            "created_at",
            "updated_at",
            "completed_at",
        ]
