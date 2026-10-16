"""Support Console Diagnostic Serializers (Phase 6C-2).

Read-only serializers for operator diagnostics.
STRICT PRIVACY & SECURITY RULES:
- Zero credential_ref, token, password, or secret fields exposed.
- Diagnostic failure details sanitized via sanitize_diagnostic_detail.
- PII minimized to operational identifiers.
"""

from rest_framework import serializers

from apps.auditlog.models import AuditLog
from apps.integration_hub.models import (
    ConnectorInstance,
    IntegrationFailure,
    IntegrationReconciliationIssue,
)
from apps.integration_hub.retry_service import sanitize_diagnostic_detail
from apps.organizations.models import Organization


class SupportOrganizationSummarySerializer(serializers.ModelSerializer):
    """Minimal organization representation for search and header display."""

    class Meta:
        model = Organization
        fields = ["id", "code", "name", "status", "created_at", "updated_at"]
        read_only_fields = fields


class SupportConnectorInstanceDiagnosticSerializer(serializers.ModelSerializer):
    """Sanitized connector instance diagnostic view.

    Explicitly excludes credential_ref, config, and sensitive auth data.
    """

    connector_code = serializers.CharField(source="connector.code", read_only=True)
    connector_name = serializers.CharField(source="connector.name", read_only=True)

    class Meta:
        model = ConnectorInstance
        fields = [
            "id",
            "connector_id",
            "connector_code",
            "connector_name",
            "label",
            "status",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class SupportFailureDiagnosticSerializer(serializers.ModelSerializer):
    """Sanitized failure diagnostic summary.

    Failure detail is masked via sanitize_diagnostic_detail.
    """

    sanitized_detail = serializers.SerializerMethodField()
    instance_id = serializers.SerializerMethodField()
    instance_label = serializers.SerializerMethodField()
    connector_code = serializers.SerializerMethodField()

    class Meta:
        model = IntegrationFailure
        fields = [
            "id",
            "instance_id",
            "instance_label",
            "connector_code",
            "failure_type",
            "failure_code",
            "status",
            "retry_count",
            "max_retries",
            "retry_after",
            "sanitized_detail",
            "resolution_notes",
            "resolved_at",
            "created_at",
        ]
        read_only_fields = fields


    def _get_instance(self, obj: IntegrationFailure):
        if obj.job_id and getattr(obj, "job", None):
            return getattr(obj.job, "instance", None)
        if obj.event_id and getattr(obj, "event", None):
            return getattr(obj.event, "instance", None)
        return None

    def get_instance_id(self, obj: IntegrationFailure) -> str | None:
        inst = self._get_instance(obj)
        return str(inst.id) if inst else None

    def get_instance_label(self, obj: IntegrationFailure) -> str:
        inst = self._get_instance(obj)
        return getattr(inst, "label", "") if inst else ""

    def get_connector_code(self, obj: IntegrationFailure) -> str:
        inst = self._get_instance(obj)
        if inst and getattr(inst, "connector", None):
            return inst.connector.code
        return ""

    def get_sanitized_detail(self, obj: IntegrationFailure) -> str:
        return sanitize_diagnostic_detail(obj.failure_detail)


class SupportReconciliationIssueSerializer(serializers.ModelSerializer):
    """Open reconciliation issue view."""

    instance_label = serializers.CharField(source="instance.label", read_only=True)
    connector_code = serializers.CharField(source="instance.connector.code", read_only=True)

    class Meta:
        model = IntegrationReconciliationIssue
        fields = [
            "id",
            "instance_id",
            "instance_label",
            "connector_code",
            "issue_code",
            "description",
            "severity",
            "status",
            "detected_at",
        ]
        read_only_fields = fields


class SupportAuditEntrySerializer(serializers.ModelSerializer):
    """Operationally relevant audit trail records stripped of sensitive metadata."""

    class Meta:
        model = AuditLog
        fields = [
            "id",
            "action",
            "target_type",
            "target_id",
            "target_repr",
            "operation_source",
            "timestamp",
        ]
        read_only_fields = fields
