"""Integration Hub Serializers (Phase 5A + 5B)."""

from django.utils import timezone
from rest_framework import serializers

from apps.integration_hub.models import (
    ConnectorInstance,
    ExternalIdentity,
    ExternalTenantMapping,
    ExternalUserMapping,
    IntegrationConnector,
    IntegrationEvent,
    IntegrationFailure,
    IntegrationFailureAttempt,
    ProvisioningJob,
)

# ── 5A ────────────────────────────────────────────────────────────────────────


class IntegrationConnectorSerializer(serializers.ModelSerializer):
    class Meta:
        model = IntegrationConnector
        fields = [
            "id", "code", "name", "description", "product",
            "version", "status", "capabilities", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class ConnectorInstanceSerializer(serializers.ModelSerializer):
    connector_code = serializers.CharField(source="connector.code", read_only=True)
    organization_name = serializers.CharField(source="organization.name", read_only=True)

    class Meta:
        model = ConnectorInstance
        fields = [
            "id", "connector", "connector_code", "organization", "organization_name",
            "label", "credential_ref", "config", "status", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate_credential_ref(self, value: str) -> str:
        """Application-layer guard: reject obviously secret-shaped values."""
        import re
        secret_prefixes = ("sk_", "secret_", "Bearer ", "-----BEGIN")
        if any(value.startswith(p) for p in secret_prefixes):
            raise serializers.ValidationError(
                "credential_ref must be an opaque reference, not a raw secret value. "
                "Store the secret in your secret manager and provide its reference path here."
            )
        return value


class IntegrationEventIngestSerializer(serializers.ModelSerializer):
    """Used only for the idempotent ingest endpoint."""

    class Meta:
        model = IntegrationEvent
        fields = [
            "id", "instance", "event_type", "event_key",
            "payload", "status", "occurred_at", "received_at",
        ]
        read_only_fields = ["id", "status", "received_at"]


class IntegrationEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = IntegrationEvent
        fields = [
            "id", "instance", "event_type", "event_key",
            "payload", "status", "occurred_at", "received_at", "processed_at",
        ]
        read_only_fields = ["id", "received_at"]


class ProvisioningJobSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProvisioningJob
        fields = [
            "id", "instance", "organization", "user", "action",
            "status", "context", "created_at", "updated_at", "completed_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class IntegrationFailureAttemptSerializer(serializers.ModelSerializer):
    class Meta:
        model = IntegrationFailureAttempt
        fields = [
            "id",
            "attempt_number",
            "started_at",
            "completed_at",
            "outcome",
            "failure_code",
            "failure_detail",
            "http_status",
            "retry_after",
            "created_at",
        ]
        read_only_fields = fields


class IntegrationFailureSerializer(serializers.ModelSerializer):
    instance_id = serializers.SerializerMethodField()
    instance_label = serializers.SerializerMethodField()
    organization_id = serializers.SerializerMethodField()
    organization_name = serializers.SerializerMethodField()
    connector_code = serializers.SerializerMethodField()
    product_code = serializers.SerializerMethodField()
    resolved_by_email = serializers.SerializerMethodField()
    is_dead_letter = serializers.BooleanField(read_only=True)
    attempts = IntegrationFailureAttemptSerializer(many=True, read_only=True)

    class Meta:
        model = IntegrationFailure
        fields = [
            "id", "job", "event", "failure_code", "failure_detail",
            "failure_type", "status", "retry_count", "max_retries",
            "retry_after", "is_dead_letter", "created_at",
            "resolved_at", "resolved_by", "resolved_by_email", "resolution_notes",
            "instance_id", "instance_label", "organization_id",
            "organization_name", "connector_code", "product_code",
            "attempts",
        ]
        read_only_fields = [
            "id", "created_at", "resolved_at", "resolved_by",
            "resolved_by_email", "is_dead_letter", "instance_id",
            "instance_label", "organization_id", "organization_name",
            "connector_code", "product_code", "attempts",
        ]

    def _get_instance(self, obj):
        if obj.job_id and getattr(obj, "job", None):
            return obj.job.instance
        if obj.event_id and getattr(obj, "event", None):
            return obj.event.instance
        return None

    def get_instance_id(self, obj):
        inst = self._get_instance(obj)
        return str(inst.id) if inst else None

    def get_instance_label(self, obj):
        inst = self._get_instance(obj)
        return inst.label if inst else ""

    def get_organization_id(self, obj):
        if obj.job_id and getattr(obj, "job", None) and obj.job.organization_id:
            return str(obj.job.organization_id)
        inst = self._get_instance(obj)
        return str(inst.organization_id) if inst and inst.organization_id else None

    def get_organization_name(self, obj):
        if obj.job_id and getattr(obj, "job", None) and getattr(obj.job, "organization", None):
            return obj.job.organization.name
        inst = self._get_instance(obj)
        return inst.organization.name if inst and getattr(inst, "organization", None) else ""

    def get_connector_code(self, obj):
        inst = self._get_instance(obj)
        return inst.connector.code if inst and getattr(inst, "connector", None) else ""

    def get_product_code(self, obj):
        inst = self._get_instance(obj)
        if inst and getattr(inst, "connector", None) and getattr(inst.connector, "product", None):
            return inst.connector.product.code
        return ""

    def get_resolved_by_email(self, obj):
        return obj.resolved_by.email if getattr(obj, "resolved_by", None) else None


class FailureResolveRequestSerializer(serializers.Serializer):
    resolution_notes = serializers.CharField(required=True, min_length=1, max_length=2000)


class FailureDeadLetterRequestSerializer(serializers.Serializer):
    reason = serializers.CharField(required=False, allow_blank=True, max_length=500)


# ── 5B ────────────────────────────────────────────────────────────────────────


class ExternalIdentitySerializer(serializers.ModelSerializer):
    class Meta:
        model = ExternalIdentity
        fields = [
            "id", "user", "provider", "provider_subject",
            "provider_tenant", "status", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class ExternalTenantMappingSerializer(serializers.ModelSerializer):
    class Meta:
        model = ExternalTenantMapping
        fields = [
            "id", "organization", "instance", "external_tenant_id",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class ExternalUserMappingSerializer(serializers.ModelSerializer):
    class Meta:
        model = ExternalUserMapping
        fields = [
            "id", "user", "organization", "instance", "external_user_id",
            "status", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


# ── 5C ────────────────────────────────────────────────────────────────────────


class ProductSsoClientSerializer(serializers.ModelSerializer):
    product_code = serializers.CharField(source="product.code", read_only=True)
    product_name = serializers.CharField(source="product.name", read_only=True)

    class Meta:
        from apps.integration_hub.models import ProductSsoClient
        model = ProductSsoClient
        fields = [
            "id", "product", "product_code", "product_name",
            "client_identifier", "audience", "callback_uri",
            "public_key_reference", "is_active", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class SsoLaunchRequestSerializer(serializers.Serializer):
    product_id = serializers.UUIDField(required=False)
    product_code = serializers.CharField(required=False, allow_blank=True)
    organization_id = serializers.UUIDField(required=False)
    redirect_uri = serializers.CharField(required=False, allow_blank=True)
    code_challenge = serializers.CharField(required=False, allow_blank=True, max_length=128)
    code_challenge_method = serializers.ChoiceField(
        choices=["S256", "plain"],
        default="S256",
        required=False,
    )
    state = serializers.CharField(required=False, allow_blank=True, max_length=512)

    def validate(self, attrs):
        if not attrs.get("product_id") and not attrs.get("product_code"):
            raise serializers.ValidationError("Either 'product_id' or 'product_code' is required.")
        return attrs


class SsoValidateRequestSerializer(serializers.Serializer):
    code = serializers.CharField(required=True)
    client_identifier = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    client_id = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    code_verifier = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    expected_org_id = serializers.UUIDField(required=False, allow_null=True)
    expected_product_id = serializers.UUIDField(required=False, allow_null=True)
    state = serializers.CharField(required=False, allow_blank=True, allow_null=True, max_length=512)

    def validate(self, attrs):
        if not attrs.get("client_identifier") and attrs.get("client_id"):
            attrs["client_identifier"] = attrs["client_id"]
        return attrs


# ── 5D ────────────────────────────────────────────────────────────────────────


class IntegrationReconciliationIssueSerializer(serializers.ModelSerializer):
    instance_label = serializers.CharField(source="instance.label", read_only=True)
    connector_code = serializers.CharField(source="instance.connector.code", read_only=True)
    resolved_by_email = serializers.CharField(source="resolved_by.email", read_only=True, default=None)

    class Meta:
        from apps.integration_hub.models import IntegrationReconciliationIssue
        model = IntegrationReconciliationIssue
        fields = [
            "id", "instance", "instance_label", "connector_code",
            "issue_code", "subject_type", "subject_id", "details",
            "status", "detected_at", "resolved_at", "resolved_by",
            "resolved_by_email", "resolution_notes",
        ]
        read_only_fields = [
            "id", "instance", "instance_label", "connector_code",
            "issue_code", "subject_type", "subject_id", "details",
            "status", "detected_at", "resolved_at", "resolved_by",
            "resolved_by_email", "resolution_notes",
        ]


class ResolveIntegrationIssueSerializer(serializers.Serializer):
    resolution_notes = serializers.CharField(required=True, min_length=3, max_length=1000)
