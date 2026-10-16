"""Audit Log Serializers.

Provides read-only serializers consuming immutable actor snapshots directly
from the AuditLog instance to eliminate N+1 queries.
"""

from typing import Any
from rest_framework import serializers
from apps.auditlog.models import AuditLog


class AuditLogListSerializer(serializers.ModelSerializer):
    """List serializer for audit log entries."""

    actor = serializers.SerializerMethodField()

    class Meta:
        model = AuditLog
        fields = [
            "id",
            "timestamp",
            "action",
            "target_type",
            "target_id",
            "target_repr",
            "organization_id",
            "operation_source",
            "correlation_id",
            "actor",
        ]
        read_only_fields = fields

    def get_actor(self, obj: AuditLog) -> dict[str, Any]:
        return {
            "id": str(obj.actor_id),
            "email": obj.actor_email,
            "full_name": obj.actor_name,
        }


class AuditLogDetailSerializer(AuditLogListSerializer):
    """Detail serializer extending list fields with allowlisted event metadata."""

    class Meta(AuditLogListSerializer.Meta):
        fields = AuditLogListSerializer.Meta.fields + ["metadata"]
        read_only_fields = fields
