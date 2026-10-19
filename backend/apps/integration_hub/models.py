"""Integration Hub Models (Phase 5A).

Five models:
  - IntegrationConnector   : connector registry entry
  - ConnectorInstance      : per-org connector configuration (credential_ref only — never plaintext)
  - IntegrationEvent       : idempotent inbound/outbound event record
  - ProvisioningJob        : async provisioning action tracking
  - IntegrationFailure     : dead-letter / failure record with retry_after

Credential storage convention (matching existing codebase pattern from
notifications body_ref and billing processor_ref):
  credential_ref stores an opaque reference string (e.g. vault path, secret-manager key,
  external secret-store ID).  Raw secret values must never be written to this column.
  A CheckConstraint rejects values that look like typical secret patterns (begin with
  "sk_", "secret_", "Bearer ", or contain a raw PEM header).
"""

import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone


CODE_REGEX = r"^[a-z0-9]+(?:[-_][a-z0-9]+)*$"
code_validator = RegexValidator(
    regex=CODE_REGEX,
    message="Code must be lowercase alphanumeric with single hyphens or underscores.",
)

# Regex that rejects obviously secret-shaped values in credential_ref.
# Matches strings that start with known secret prefixes or contain PEM block headers.
_SECRET_PATTERN = r"^(sk_|secret_|Bearer |-----BEGIN)"


class ConnectorStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    DEPRECATED = "deprecated", "Deprecated"
    RETIRED = "retired", "Retired"


class InstanceStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    SUSPENDED = "suspended", "Suspended"
    DISCONNECTED = "disconnected", "Disconnected"


class EventStatus(models.TextChoices):
    RECEIVED = "received", "Received"
    PROCESSING = "processing", "Processing"
    PROCESSED = "processed", "Processed"
    FAILED = "failed", "Failed"
    IGNORED = "ignored", "Ignored"


class ProvisioningAction(models.TextChoices):
    PROVISION = "provision", "Provision"
    DEPROVISION = "deprovision", "Deprovision"
    UPDATE = "update", "Update"
    SYNC = "sync", "Sync"


class ProvisioningJobStatus(models.TextChoices):
    QUEUED = "queued", "Queued"
    PROCESSING = "processing", "Processing"
    COMPLETED = "completed", "Completed"
    FAILED = "failed", "Failed"
    CANCELLED = "cancelled", "Cancelled"
    RETRY_SCHEDULED = "retry_scheduled", "Retry Scheduled"


class AttemptOutcome(models.TextChoices):
    SUCCESS = "success", "Success"
    FAILURE = "failure", "Failure"


class FailureStatus(models.TextChoices):
    OPEN = "open", "Open"
    RETRY_SCHEDULED = "retry_scheduled", "Retry Scheduled"
    DEAD_LETTER = "dead_letter", "Dead Letter"
    RESOLVED = "resolved", "Resolved"


class FailureType(models.TextChoices):
    TRANSIENT = "transient", "Transient"
    PERMANENT = "permanent", "Permanent"


class IntegrationConnector(models.Model):
    """Registry of available integration connectors.

    Each connector represents a supported external system type
    (e.g. moodle, canvas, saml_idp).  product is nullable so
    connector types can exist before a product mapping is defined.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(
        max_length=64,
        unique=True,
        validators=[code_validator],
        help_text="Canonical connector identifier (e.g. moodle, canvas_lms).",
    )
    name = models.CharField(max_length=128)
    description = models.TextField(blank=True, default="")
    product = models.ForeignKey(
        "product_registry.Product",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="integration_connectors",
        help_text="Optional product association. Null until a product mapping is configured.",
    )
    version = models.CharField(
        max_length=32,
        default="1.0",
        help_text="Connector protocol/schema version.",
    )
    status = models.CharField(
        max_length=20,
        choices=ConnectorStatus.choices,
        default=ConnectorStatus.ACTIVE,
        db_index=True,
    )
    capabilities = models.JSONField(
        default=list,
        blank=True,
        help_text="List of capability identifiers this connector supports (no secrets).",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "integration_connectors"
        ordering = ["code"]
        constraints = [
            models.CheckConstraint(
                condition=Q(status__in=ConnectorStatus.values),
                name="valid_integration_connector_status",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.code} v{self.version} ({self.status})"


class ConnectorInstance(models.Model):
    """Per-organization connector configuration.

    credential_ref holds an opaque external reference (vault path, AWS Secrets
    Manager ARN, etc.).  The actual secret value is never stored in this table.
    A DB-level check constraint prevents obviously secret-shaped values from
    being written (defense in depth alongside application-layer validation).
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    connector = models.ForeignKey(
        IntegrationConnector,
        on_delete=models.PROTECT,
        related_name="instances",
        help_text="Connector definition this instance implements.",
    )
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="connector_instances",
    )
    label = models.CharField(
        max_length=128,
        blank=True,
        default="",
        help_text="Optional human-readable label for this instance.",
    )
    credential_ref = models.CharField(
        max_length=512,
        blank=True,
        default="",
        help_text=(
            "Opaque reference to the credential stored in an external secret store "
            "(e.g. 'vault:secret/org-123/canvas', 'asm:arn:aws:secretsmanager:...'). "
            "NEVER store raw secret values here."
        ),
    )
    config = models.JSONField(
        default=dict,
        blank=True,
        help_text="Non-sensitive configuration parameters (base URL, tenant ID, etc.).",
    )
    status = models.CharField(
        max_length=20,
        choices=InstanceStatus.choices,
        default=InstanceStatus.ACTIVE,
        db_index=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "connector_instances"
        ordering = ["organization__name", "connector__code"]
        constraints = [
            models.CheckConstraint(
                condition=Q(status__in=InstanceStatus.values),
                name="valid_connector_instance_status",
            ),
            # Defense-in-depth: reject common raw-secret prefixes at the DB level.
            # This is not exhaustive; application-layer validation is the primary gate.
            models.CheckConstraint(
                condition=~Q(credential_ref__regex=_SECRET_PATTERN),
                name="connector_instance_no_raw_secret_in_credential_ref",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.connector.code}@{self.organization_id} ({self.status})"


class IntegrationEvent(models.Model):
    """Idempotent inbound or outbound integration event record.

    event_key enforces idempotency: re-ingesting an event with a key that already
    exists returns the existing record rather than creating a duplicate.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    instance = models.ForeignKey(
        ConnectorInstance,
        on_delete=models.PROTECT,
        related_name="events",
        help_text="Connector instance that produced or will consume this event.",
    )
    event_type = models.CharField(
        max_length=128,
        db_index=True,
        help_text="Namespaced event type (e.g. 'lms.enrollment.created').",
    )
    event_key = models.CharField(
        max_length=255,
        unique=True,
        db_index=True,
        help_text="Globally unique idempotency key for this event.",
    )
    payload = models.JSONField(
        default=dict,
        blank=True,
        help_text="Sanitized event payload (no secrets).",
    )
    status = models.CharField(
        max_length=20,
        choices=EventStatus.choices,
        default=EventStatus.RECEIVED,
        db_index=True,
    )
    occurred_at = models.DateTimeField(
        help_text="When the event occurred in the source system.",
    )
    received_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "integration_events"
        ordering = ["-occurred_at"]
        constraints = [
            models.CheckConstraint(
                condition=Q(status__in=EventStatus.values),
                name="valid_integration_event_status",
            ),
        ]

    def __str__(self) -> str:
        return f"Event {self.event_key} [{self.event_type}] ({self.status})"


class ProvisioningJob(models.Model):
    """Tracks an async provisioning action for a connector instance.

    Linked to an organization and optionally a user (for user-level provisioning).
    Full retry/backoff workflow is deferred to Prompt 24/5G; this model only
    records state and is referenced by IntegrationFailure for dead-letter tracking.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    instance = models.ForeignKey(
        ConnectorInstance,
        on_delete=models.PROTECT,
        related_name="provisioning_jobs",
    )
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.PROTECT,
        related_name="provisioning_jobs",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="provisioning_jobs",
        help_text="Target user for user-level provisioning; null for org-level actions.",
    )
    action = models.CharField(
        max_length=20,
        choices=ProvisioningAction.choices,
        default=ProvisioningAction.PROVISION,
        db_index=True,
    )
    status = models.CharField(
        max_length=20,
        choices=ProvisioningJobStatus.choices,
        default=ProvisioningJobStatus.QUEUED,
        db_index=True,
    )
    context = models.JSONField(
        default=dict,
        blank=True,
        help_text="Non-sensitive execution context (no secrets).",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "provisioning_jobs"
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=Q(action__in=ProvisioningAction.values),
                name="valid_provisioning_action",
            ),
            models.CheckConstraint(
                condition=Q(status__in=ProvisioningJobStatus.values),
                name="valid_provisioning_job_status",
            ),
        ]

    def __str__(self) -> str:
        return f"ProvisioningJob {self.id} [{self.action}] ({self.status})"


class IntegrationFailure(models.Model):
    """Dead-letter record for failed provisioning jobs or events.

    retry_after is set by the failure handler; full dead-letter recovery UI
    and backoff scheduling are deferred to Prompt 24/5G.  This table only
    records the failure and the earliest time a retry is permissible.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    job = models.ForeignKey(
        ProvisioningJob,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="failures",
        help_text="Associated provisioning job, if failure originates from a job.",
    )
    event = models.ForeignKey(
        IntegrationEvent,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="failures",
        help_text="Associated integration event, if failure originates from event processing.",
    )
    failure_code = models.CharField(
        max_length=64,
        db_index=True,
        help_text="Machine-readable failure reason code.",
    )
    failure_detail = models.TextField(
        blank=True,
        default="",
        help_text="Sanitized diagnostic detail (no sensitive data).",
    )
    retry_after = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Earliest datetime a retry is permitted (null = no scheduled retry).",
    )
    status = models.CharField(
        max_length=20,
        choices=FailureStatus.choices,
        default=FailureStatus.OPEN,
        db_index=True,
        help_text="Current state in the failure/recovery lifecycle.",
    )
    failure_type = models.CharField(
        max_length=20,
        choices=FailureType.choices,
        default=FailureType.TRANSIENT,
        db_index=True,
        help_text="Classification: transient (retryable) vs permanent (non-retryable).",
    )
    retry_count = models.PositiveIntegerField(
        default=0,
        help_text="Number of retry attempts scheduled or executed.",
    )
    max_retries = models.PositiveIntegerField(
        default=3,
        help_text="Maximum allowed retry attempts before marking dead-letter.",
    )
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="resolved_integration_failures",
        help_text="User who manually marked this failure resolved.",
    )
    resolution_notes = models.TextField(
        blank=True,
        default="",
        help_text="Mandatory audit explanation when manually resolving.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "integration_failures"
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=Q(job__isnull=False) | Q(event__isnull=False),
                name="integration_failure_requires_job_or_event",
            ),
            models.CheckConstraint(
                condition=Q(status__in=FailureStatus.values),
                name="valid_integration_failure_status",
            ),
            models.CheckConstraint(
                condition=Q(failure_type__in=FailureType.values),
                name="valid_integration_failure_type",
            ),
        ]

    @classmethod
    def org_scope_filter(cls, org_or_id):
        """Return a Q filter strictly scoping failures to an organization.

        Enforces canonical ownership and fail-closed security:
        - Failures linked only to a job in the target org are included.
        - Failures linked only to an event in the target org are included.
        - Failures linked to both job and event where BOTH belong to the target org are included.
        - Inconsistent cross-tenant linkages (job in Org A, event in Org B) or orphaned records
          are strictly excluded and fail closed for both organizations.
        """
        org_id = getattr(org_or_id, "id", org_or_id)
        return (
            Q(job__organization_id=org_id)
            & (Q(event__isnull=True) | Q(event__instance__organization_id=org_id))
        ) | (
            Q(event__instance__organization_id=org_id)
            & Q(job__isnull=True)
        )

    def clean(self):
        super().clean()
        if self.job_id and self.event_id:
            job_org_id = None
            if getattr(self, "job", None):
                job_org_id = self.job.organization_id
            else:
                job_org_id = ProvisioningJob.objects.filter(pk=self.job_id).values_list("organization_id", flat=True).first()

            event_org_id = None
            if getattr(self, "event", None) and getattr(self.event, "instance", None):
                event_org_id = self.event.instance.organization_id
            else:
                event_org_id = IntegrationEvent.objects.filter(pk=self.event_id).values_list("instance__organization_id", flat=True).first()

            if job_org_id and event_org_id and str(job_org_id) != str(event_org_id):
                raise ValidationError(
                    "Cross-tenant association conflict: ProvisioningJob and IntegrationEvent belong to different organizations.",
                    code="CROSS_TENANT_ORGANIZATION_MISMATCH",
                )

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    @property
    def is_dead_letter(self) -> bool:
        return self.status == FailureStatus.DEAD_LETTER

    def __str__(self) -> str:
        ref = f"job={self.job_id}" if self.job_id else f"event={self.event_id}"
        return f"Failure [{self.failure_code}] {ref} ({self.status})"



class IntegrationFailureAttempt(models.Model):
    """Audited execution attempt history for an IntegrationFailure record.

    Captures deterministic attempt sequence, timing, outcome, and sanitized
    error diagnostics without storing passwords, tokens, or bearer secrets.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    failure = models.ForeignKey(
        IntegrationFailure,
        on_delete=models.CASCADE,
        related_name="attempts",
        db_index=True,
        help_text="Associated IntegrationFailure record.",
    )
    attempt_number = models.PositiveIntegerField(
        help_text="1-based sequence number for this execution attempt.",
    )
    started_at = models.DateTimeField(
        default=timezone.now,
        help_text="Timestamp when this attempt execution began.",
    )
    completed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp when this attempt execution concluded.",
    )
    outcome = models.CharField(
        max_length=20,
        choices=AttemptOutcome.choices,
        default=AttemptOutcome.FAILURE,
        db_index=True,
        help_text="Final outcome of this attempt: success or failure.",
    )
    failure_code = models.CharField(
        max_length=64,
        blank=True,
        default="",
        help_text="Machine-readable error code if this attempt failed.",
    )
    failure_detail = models.TextField(
        blank=True,
        default="",
        help_text="Sanitized failure diagnostic detail (no secrets).",
    )
    http_status = models.IntegerField(
        null=True,
        blank=True,
        help_text="HTTP status code from remote service if available.",
    )
    retry_after = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Earliest retry timestamp scheduled after this attempt, if any.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "integration_failure_attempts"
        ordering = ["attempt_number"]
        constraints = [
            models.UniqueConstraint(
                fields=["failure", "attempt_number"],
                name="unique_failure_attempt_number",
            ),
            models.CheckConstraint(
                condition=Q(outcome__in=AttemptOutcome.values),
                name="valid_failure_attempt_outcome",
            ),
        ]

    def __str__(self) -> str:
        return f"Attempt #{self.attempt_number} for Failure {self.failure_id} [{self.outcome}]"


# ── Phase 5B mapping models ────────────────────────────────────────────────────

class ExternalIdentityStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    SUSPENDED = "suspended", "Suspended"


class ExternalIdentity(models.Model):
    """Maps a VibeConnect user to an external provider identity.

    Unique on (provider, provider_tenant, provider_subject) so that the same
    external identity can never be linked to two different platform users.
    VibeConnect UUID is never assumed to equal provider_subject.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="external_identities",
    )
    provider = models.CharField(
        max_length=64,
        help_text="Provider code (e.g. 'canvas', 'moodle', 'saml_acme').",
    )
    provider_subject = models.CharField(
        max_length=255,
        help_text="Opaque external user identifier as issued by the provider.",
    )
    provider_tenant = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Provider-side tenant/domain qualifier (empty string for global providers).",
    )
    status = models.CharField(
        max_length=20,
        choices=ExternalIdentityStatus.choices,
        default=ExternalIdentityStatus.ACTIVE,
        db_index=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "external_identities"
        ordering = ["provider", "provider_tenant", "provider_subject"]
        constraints = [
            models.UniqueConstraint(
                fields=["provider", "provider_tenant", "provider_subject"],
                name="unique_external_identity_per_provider_tenant_subject",
            ),
            models.CheckConstraint(
                condition=Q(status__in=ExternalIdentityStatus.values),
                name="valid_external_identity_status",
            ),
        ]

    def __str__(self) -> str:
        return f"ExternalIdentity [{self.provider}:{self.provider_tenant}:{self.provider_subject}] -> user={self.user_id}"


class ExternalUserMappingStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    SUSPENDED = "suspended", "Suspended"
    ORPHANED = "orphaned", "Orphaned"


class ExternalTenantMapping(models.Model):
    """Maps a VibeConnect organization to an external tenant ID within a connector instance.

    Unique per instance: one organization cannot have two different external_tenant_ids
    in the same connector instance.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="external_tenant_mappings",
    )
    instance = models.ForeignKey(
        ConnectorInstance,
        on_delete=models.CASCADE,
        related_name="tenant_mappings",
    )
    external_tenant_id = models.CharField(
        max_length=255,
        help_text="Opaque tenant identifier as used by the external system.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "external_tenant_mappings"
        ordering = ["instance__connector__code", "external_tenant_id"]
        constraints = [
            models.UniqueConstraint(
                fields=["instance", "organization"],
                name="unique_external_tenant_mapping_per_instance_org",
            ),
        ]

    def __str__(self) -> str:
        return f"TenantMapping [{self.external_tenant_id}] org={self.organization_id} instance={self.instance_id}"


class ExternalUserMapping(models.Model):
    """Maps a VibeConnect user (within an organization) to an external user ID in a connector instance.

    Unique per (instance, external_user_id): the same external user can only map to
    one VibeConnect user per connector instance.
    Deletion of the organization cascades to this mapping (soft-status orphaning
    is not used here because FK CASCADE is already established by ConnectorInstance ->
    Organization CASCADE, making the mapping unreachable).
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="external_user_mappings",
    )
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="external_user_mappings",
    )
    instance = models.ForeignKey(
        ConnectorInstance,
        on_delete=models.CASCADE,
        related_name="user_mappings",
    )
    external_user_id = models.CharField(
        max_length=255,
        help_text="Opaque user identifier as used by the external system.",
    )
    status = models.CharField(
        max_length=20,
        choices=ExternalUserMappingStatus.choices,
        default=ExternalUserMappingStatus.ACTIVE,
        db_index=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "external_user_mappings"
        ordering = ["instance__connector__code", "external_user_id"]
        constraints = [
            models.UniqueConstraint(
                fields=["instance", "external_user_id"],
                name="unique_external_user_mapping_per_instance",
            ),
            models.CheckConstraint(
                condition=Q(status__in=ExternalUserMappingStatus.values),
                name="valid_external_user_mapping_status",
            ),
        ]

    def __str__(self) -> str:
        return f"UserMapping [{self.external_user_id}] user={self.user_id} org={self.organization_id} instance={self.instance_id}"


# =============================================================================
# Phase 5C: LMS SSO Pilot Models
# =============================================================================


class ProductSsoClient(models.Model):
    """Registered SSO client configuration for a product.

    Defines the exact callback URL and credentials reference for SSO direct launches.
    Redirect URIs must match callback_uri exactly (no wildcards allowed).
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    product = models.ForeignKey(
        "product_registry.Product",
        on_delete=models.CASCADE,
        related_name="sso_clients",
    )
    client_identifier = models.CharField(
        max_length=120,
        unique=True,
        db_index=True,
        help_text="Opaque client ID recognized by the external LMS.",
    )
    audience = models.CharField(
        max_length=255,
        help_text="Expected token audience for external client.",
    )
    callback_uri = models.URLField(
        max_length=500,
        help_text="Exact callback URL for redirect after authorization.",
    )
    public_key_reference = models.CharField(
        max_length=255,
        help_text="Opaque reference to the client public key/verification credential.",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "product_sso_clients"
        ordering = ["client_identifier"]

    def __str__(self) -> str:
        return f"ProductSsoClient [{self.client_identifier}] product={self.product_id}"


class SsoAuthorizationCode(models.Model):
    """Short-lived, single-use authorization code for LMS SSO handoff.

    Stored exclusively as a SHA-256 hash. Never stores raw plaintext codes.
    Enforces tenant/product/user/assignment binding.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="sso_codes",
    )
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="sso_codes",
    )
    product = models.ForeignKey(
        "product_registry.Product",
        on_delete=models.CASCADE,
        related_name="sso_codes",
    )
    assignment = models.ForeignKey(
        "assignments.UserProductAssignment",
        on_delete=models.CASCADE,
        related_name="sso_codes",
    )
    sso_client = models.ForeignKey(
        ProductSsoClient,
        on_delete=models.CASCADE,
        related_name="codes",
    )
    code_hash = models.CharField(
        max_length=64,
        unique=True,
        db_index=True,
        help_text="SHA-256 hex digest of the one-time authorization code.",
    )
    code_challenge = models.CharField(
        max_length=128,
        null=True,
        blank=True,
        help_text="PKCE code challenge (RFC 7636).",
    )
    code_challenge_method = models.CharField(
        max_length=10,
        default="S256",
        help_text="PKCE code challenge method (S256 or plain).",
    )
    state = models.CharField(
        max_length=512,
        null=True,
        blank=True,
        help_text="Opaque client state or signed CSRF nonce bound to launch.",
    )
    expires_at = models.DateTimeField(db_index=True)
    used_at = models.DateTimeField(null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "sso_authorization_codes"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"SsoAuthCode user={self.user_id} org={self.organization_id} used={bool(self.used_at)}"


# =============================================================================
# Phase 5D: LMS Identity Reconciliation Models
# =============================================================================


class IntegrationReconciliationStatus(models.TextChoices):
    OPEN = "OPEN", "Open"
    RESOLVED = "RESOLVED", "Resolved"


class IntegrationReconciliationIssue(models.Model):
    """Reviewable issue detected during LMS identity/mapping reconciliation.

    Read-only detection output. Does not mutate identity or mapping records.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    instance = models.ForeignKey(
        ConnectorInstance,
        on_delete=models.CASCADE,
        related_name="reconciliation_issues",
    )
    issue_code = models.CharField(
        max_length=64,
        db_index=True,
        help_text="Categorical code for the anomaly (e.g. USER_INACTIVE_OR_SUSPENDED).",
    )
    subject_type = models.CharField(
        max_length=64,
        help_text="Type of subject (user, organization, mapping).",
    )
    subject_id = models.CharField(
        max_length=120,
        help_text="Identifier of the subject.",
    )
    details = models.JSONField(default=dict, blank=True)
    status = models.CharField(
        max_length=20,
        choices=IntegrationReconciliationStatus.choices,
        default=IntegrationReconciliationStatus.OPEN,
        db_index=True,
    )
    detected_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="resolved_integration_issues",
    )
    resolution_notes = models.TextField(blank=True)

    class Meta:
        db_table = "integration_reconciliation_issues"
        ordering = ["-detected_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["instance", "issue_code", "subject_id"],
                condition=Q(status="OPEN"),
                name="unique_open_reconciliation_issue",
            ),
        ]

    def __str__(self) -> str:
        return f"ReconciliationIssue [{self.issue_code}] {self.subject_type}:{self.subject_id} status={self.status}"
