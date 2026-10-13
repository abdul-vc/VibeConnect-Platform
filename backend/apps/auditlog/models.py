"""Audit Log Domain Models.

Provides an append-only, PostgreSQL-backed central audit trail foundation
for the VibeConnect master control plane with application-enforced immutability.
"""

import uuid
from django.conf import settings
from django.db import models
from django.db.models import F, Q


class AuditLogImmutableError(Exception):
    """Raised when an attempt is made to modify or delete immutable audit records."""
    pass


class AuditAction(models.TextChoices):
    PRODUCT_CREATED = "product_created", "Product Created"
    PRODUCT_UPDATED = "product_updated", "Product Updated"
    PRODUCT_RETIRED = "product_retired", "Product Retired"
    ORGANIZATION_CREATED = "organization_created", "Organization Created"
    ORGANIZATION_UPDATED = "organization_updated", "Organization Updated"
    ORGANIZATION_RETIRED = "organization_retired", "Organization Retired"
    ENTITLEMENT_CREATED = "entitlement_created", "Entitlement Created"
    ENTITLEMENT_STATUS_CHANGED = "entitlement_status_changed", "Entitlement Status Changed"
    ENTITLEMENT_REVOKED = "entitlement_revoked", "Entitlement Revoked"
    LOGIN_SUCCESS = "login_success", "Login Success"
    LOGOUT_SUCCESS = "logout_success", "Logout Success"
    MODULE_CREATED = "module_created", "Module Created"
    MODULE_UPDATED = "module_updated", "Module Updated"
    MODULE_RETIRED = "module_retired", "Module Retired"
    FEATURE_CREATED = "feature_created", "Feature Created"
    FEATURE_UPDATED = "feature_updated", "Feature Updated"
    FEATURE_RETIRED = "feature_retired", "Feature Retired"
    CAPABILITY_CREATED = "capability_created", "Capability Created"
    CAPABILITY_UPDATED = "capability_updated", "Capability Updated"
    CAPABILITY_RETIRED = "capability_retired", "Capability Retired"
    # Phase 2B Plan Domain Actions
    PLAN_CREATED = "plan_created", "Plan Created"
    PLAN_UPDATED = "plan_updated", "Plan Updated"
    PLAN_VERSION_CREATED = "plan_version_created", "Plan Version Created"
    PLAN_VERSION_UPDATED = "plan_version_updated", "Plan Version Updated"
    PLAN_VERSION_CLONED = "plan_version_cloned", "Plan Version Cloned"
    PLAN_VERSION_ACTIVATED = "plan_version_activated", "Plan Version Activated"
    PLAN_VERSION_RETIRED = "plan_version_retired", "Plan Version Retired"
    PLAN_PRICE_CREATED = "plan_price_created", "Plan Price Created"
    PLAN_PRICE_UPDATED = "plan_price_updated", "Plan Price Updated"
    PLAN_PRICE_REMOVED = "plan_price_removed", "Plan Price Removed"
    PLAN_PRODUCT_ADDED = "plan_product_added", "Plan Product Added"
    PLAN_PRODUCT_REMOVED = "plan_product_removed", "Plan Product Removed"
    PLAN_MODULE_ADDED = "plan_module_added", "Plan Module Added"
    PLAN_MODULE_REMOVED = "plan_module_removed", "Plan Module Removed"
    PLAN_CAPABILITY_ADDED = "plan_capability_added", "Plan Capability Added"
    PLAN_CAPABILITY_REMOVED = "plan_capability_removed", "Plan Capability Removed"
    PLAN_QUOTA_CREATED = "plan_quota_created", "Plan Quota Created"
    PLAN_QUOTA_UPDATED = "plan_quota_updated", "Plan Quota Updated"
    PLAN_QUOTA_REMOVED = "plan_quota_removed", "Plan Quota Removed"
    # Phase 2C Subscription Domain Actions
    SUBSCRIPTION_CREATED = "subscription_created", "Subscription Created"
    SUBSCRIPTION_TRIAL_STARTED = "subscription_trial_started", "Subscription Trial Started"
    SUBSCRIPTION_TRIAL_CONVERTED = "subscription_trial_converted", "Subscription Trial Converted"
    SUBSCRIPTION_TRIAL_EXPIRED = "subscription_trial_expired", "Subscription Trial Expired"
    SUBSCRIPTION_PLAN_CHANGED = "subscription_plan_changed", "Subscription Plan Changed"
    SUBSCRIPTION_SUSPENDED = "subscription_suspended", "Subscription Suspended"
    SUBSCRIPTION_REACTIVATED = "subscription_reactivated", "Subscription Reactivated"
    SUBSCRIPTION_CANCELLED = "subscription_cancelled", "Subscription Cancelled"
    SUBSCRIPTION_RECONCILED = "subscription_reconciled", "Subscription Reconciled"
    # Phase 2D User & Membership Domain Actions
    USER_CREATED = "user_created", "User Created"
    USER_UPDATED = "user_updated", "User Updated"
    USER_SUSPENDED = "user_suspended", "User Suspended"
    USER_REACTIVATED = "user_reactivated", "User Reactivated"
    USER_DISABLED = "user_disabled", "User Disabled"
    MEMBERSHIP_CREATED = "membership_created", "Membership Created"
    MEMBERSHIP_UPDATED = "membership_updated", "Membership Updated"
    MEMBERSHIP_SUSPENDED = "membership_suspended", "Membership Suspended"
    MEMBERSHIP_REACTIVATED = "membership_reactivated", "Membership Reactivated"
    MEMBERSHIP_ENDED = "membership_ended", "Membership Ended"
    MEMBERSHIP_RESTORED = "membership_restored", "Membership Restored"
    CONTEXT_SELECTED = "context_selected", "Context Selected"
    # Phase 2E Access Control Actions
    ROLE_CREATED = "role_created", "Role Created"
    ROLE_UPDATED = "role_updated", "Role Updated"
    ROLE_PERMISSIONS_CHANGED = "role_permissions_changed", "Role Permissions Changed"
    ROLE_RETIRED = "role_retired", "Role Retired"
    MEMBERSHIP_ROLE_ASSIGNED = "membership_role_assigned", "Membership Role Assigned"
    CONSOLE_MODULE_POLICY_CHANGED = "console_module_policy_changed", "Console Module Policy Changed"
    PERMISSION_CEILING_CHANGED = "permission_ceiling_changed", "Permission Ceiling Changed"
    # Phase 2F Assignment Domain Actions
    USER_PRODUCT_ASSIGNED = "user_product_assigned", "User Product Assigned"
    USER_PRODUCT_SUSPENDED = "user_product_suspended", "User Product Suspended"
    USER_PRODUCT_REACTIVATED = "user_product_reactivated", "User Product Reactivated"
    USER_PRODUCT_REVOKED = "user_product_revoked", "User Product Revoked"
    USER_MODULE_ASSIGNMENTS_REPLACED = "user_module_assignments_replaced", "User Module Assignments Replaced"
    SEAT_OVER_ALLOCATION_DETECTED = "seat_over_allocation_detected", "Seat Over-Allocation Detected"
    # Phase 3 Onboarding Domain Actions
    ONBOARDING_STEP_TRANSITIONED = "onboarding_step_transitioned", "Onboarding Step Transitioned"
    # Phase 3C & 3D Actions
    INVITATION_ISSUED = "invitation_issued", "Invitation Issued"
    INVITATION_ACCEPTED = "invitation_accepted", "Invitation Accepted"
    INVITATION_REVOKED = "invitation_revoked", "Invitation Revoked"
    BULK_IMPORT_JOB_CREATED = "bulk_import_job_created", "Bulk Import Job Created"
    BULK_IMPORT_JOB_COMMITTED = "bulk_import_job_committed", "Bulk Import Job Committed"
    # Phase 3F Access Requests Actions
    ACCESS_REQUEST_CREATED = "access_request_created", "Access Request Created"
    ACCESS_REQUEST_APPROVED = "access_request_approved", "Access Request Approved"
    ACCESS_REQUEST_DENIED = "access_request_denied", "Access Request Denied"
    ACCESS_REQUEST_CANCELLED = "access_request_cancelled", "Access Request Cancelled"
    # Phase 11 Showcase Domain Actions
    SHOWCASE_PROFILE_PUBLISHED = "showcase_profile_published", "Showcase Profile Published"
    SHOWCASE_PROFILE_UNPUBLISHED = "showcase_profile_unpublished", "Showcase Profile Unpublished"
    SHOWCASE_CONFIG_CHANGED = "showcase_config_changed", "Showcase Config Changed"
    SHOWCASE_DEMO_LAUNCHED = "showcase_demo_launched", "Showcase Demo Launched"
    # Phase 6B Developer Console Actions
    DEVELOPER_APPLICATION_CREATED = "developer_application_created", "Developer Application Created"
    DEVELOPER_APPLICATION_UPDATED = "developer_application_updated", "Developer Application Updated"
    DEVELOPER_APPLICATION_SUSPENDED = "developer_application_suspended", "Developer Application Suspended"
    DEVELOPER_APPLICATION_REACTIVATED = "developer_application_reactivated", "Developer Application Reactivated"
    DEVELOPER_APPLICATION_REVOKED = "developer_application_revoked", "Developer Application Revoked"
    DEVELOPER_KEY_CREATED = "developer_key_created", "Developer Key Created"
    DEVELOPER_KEY_ROTATED = "developer_key_rotated", "Developer Key Rotated"
    DEVELOPER_KEY_REVOKED = "developer_key_revoked", "Developer Key Revoked"
    DEVELOPER_WEBHOOK_CREATED = "developer_webhook_created", "Developer Webhook Created"
    DEVELOPER_WEBHOOK_UPDATED = "developer_webhook_updated", "Developer Webhook Updated"
    DEVELOPER_WEBHOOK_SUSPENDED = "developer_webhook_suspended", "Developer Webhook Suspended"
    DEVELOPER_WEBHOOK_REACTIVATED = "developer_webhook_reactivated", "Developer Webhook Reactivated"
    DEVELOPER_WEBHOOK_REVOKED = "developer_webhook_revoked", "Developer Webhook Revoked"
    DEVELOPER_WEBHOOK_SECRET_ROTATED = "developer_webhook_secret_rotated", "Developer Webhook Secret Rotated"
    DEVELOPER_WEBHOOK_REPLAYED = "developer_webhook_replayed", "Developer Webhook Replayed"
    # Phase 6C Support Remediation Actions
    SUPPORT_FAILURE_RETRY_SCHEDULED = "support_failure_retry_scheduled", "Support Failure Retry Scheduled"
    SUPPORT_DEAD_LETTER_REPLAYED = "support_dead_letter_replayed", "Support Dead-Letter Replayed"
    SUPPORT_FAILURE_RESOLVED = "support_failure_resolved", "Support Failure Resolved"
    SUPPORT_RECONCILIATION_RESOLVED = "support_reconciliation_resolved", "Support Reconciliation Resolved"
    # Phase 6D Support Impersonation Actions
    SUPPORT_IMPERSONATION_STARTED = "support_impersonation_started", "Support Impersonation Started"
    SUPPORT_IMPERSONATION_EXPIRED = "support_impersonation_expired", "Support Impersonation Expired"
    SUPPORT_IMPERSONATION_TERMINATED = "support_impersonation_terminated", "Support Impersonation Terminated"
    SUPPORT_IMPERSONATION_REVOKED = "support_impersonation_revoked", "Support Impersonation Revoked"
    # Phase 6C Support Role Management Actions
    SUPPORT_ROLE_GRANTED = "support_role_granted", "Support Role Granted"
    SUPPORT_ROLE_REVOKED = "support_role_revoked", "Support Role Revoked"
    # Phase 6F User Anonymization Action
    USER_ANONYMIZED = "user_anonymized", "User Anonymized"


class AuditTargetType(models.TextChoices):
    PRODUCT = "product", "Product"
    ORGANIZATION = "organization", "Organization"
    ENTITLEMENT = "entitlement", "Entitlement"
    AUTH = "auth", "Authentication"
    MODULE = "module", "Module"
    FEATURE = "feature", "Feature"
    CAPABILITY = "capability", "Capability"
    # Phase 2B Plan Domain Target Types
    PLAN = "plan", "Plan"
    PLAN_VERSION = "plan_version", "Plan Version"
    PLAN_PRICE = "plan_price", "Plan Price"
    PLAN_PRODUCT = "plan_product", "Plan Product"
    PLAN_MODULE = "plan_module", "Plan Module"
    PLAN_CAPABILITY = "plan_capability", "Plan Capability"
    PLAN_QUOTA = "plan_quota", "Plan Quota"
    # Phase 2C Subscription Domain Target Type
    SUBSCRIPTION = "subscription", "Subscription"
    # Phase 2D Target Types
    USER = "user", "User"
    MEMBERSHIP = "membership", "Membership"
    # Phase 2E Target Types
    ROLE = "role", "Role"
    CONSOLE_POLICY = "console_policy", "Console Module Policy"
    PERMISSION_CEILING = "permission_ceiling", "Permission Ceiling"
    # Phase 2F Target Types
    USER_PRODUCT_ASSIGNMENT = "user_product_assignment", "User Product Assignment"
    # Phase 3 Target Types
    ONBOARDING_CASE = "onboarding_case", "Onboarding Case"
    INVITATION = "invitation", "Invitation"
    BULK_IMPORT_JOB = "bulk_import_job", "Bulk Import Job"
    ACCESS_REQUEST = "access_request", "Access Request"
    # Phase 11 Showcase Target Type
    SHOWCASE_PROFILE = "showcase_profile", "Showcase Profile"
    # Phase 6B Target Types
    DEVELOPER_APPLICATION = "developer_application", "Developer Application"
    DEVELOPER_KEY = "developer_key", "Developer Key"
    DEVELOPER_WEBHOOK = "developer_webhook", "Developer Webhook"
    # Phase 6D Target Types
    SUPPORT_IMPERSONATION = "support_impersonation", "Support Impersonation Session"



class AuditOperationSource(models.TextChoices):
    INTERACTIVE = "interactive", "Interactive"
    AUTHENTICATION = "authentication", "Authentication"
    BULK_IMPORT = "bulk_import", "Bulk Import"
    INTEGRATION = "integration", "Integration"


class AuditLogQuerySet(models.QuerySet):
    """QuerySet that enforces append-only immutability at the query level."""

    def update(self, **kwargs):
        raise AuditLogImmutableError("Audit records are immutable and cannot be updated.")

    def delete(self):
        raise AuditLogImmutableError("Audit records are append-only and cannot be deleted.")

    def bulk_update(self, objs, fields, batch_size=None):
        raise AuditLogImmutableError("Audit records are immutable and cannot be bulk updated.")


class AuditLogManager(models.Manager):
    """Manager providing custom immutable QuerySet and preventing bulk updates."""

    def get_queryset(self):
        return AuditLogQuerySet(self.model, using=self._db)

    def bulk_update(self, objs, fields, batch_size=None):
        raise AuditLogImmutableError("Audit records are immutable and cannot be bulk updated.")


class AuditLog(models.Model):
    """Central append-only audit trail event.

    Notes on Immutability Boundary:
    Application-enforced immutability prevents modifications from Django ORM,
    managers, and public APIs. Privileged PostgreSQL users, raw SQL queries,
    database migrations, and table owners are outside this application boundary.
    """

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    timestamp = models.DateTimeField(
        auto_now_add=True,
        editable=False,
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=False,
        blank=False,
        db_index=False,
        related_name="audit_logs",
    )
    actor_email = models.CharField(
        max_length=255,
        null=False,
        blank=False,
        editable=False,
    )
    actor_name = models.CharField(
        max_length=255,
        blank=True,
        default="",
        editable=False,
    )
    action = models.CharField(
        max_length=64,
        choices=AuditAction.choices,
        editable=False,
    )
    target_type = models.CharField(
        max_length=64,
        choices=AuditTargetType.choices,
        editable=False,
    )
    target_id = models.UUIDField(
        null=False,
        blank=False,
        editable=False,
    )
    target_repr = models.CharField(
        max_length=255,
        null=False,
        blank=False,
        editable=False,
    )
    organization_id = models.UUIDField(
        null=True,
        blank=True,
        editable=False,
    )
    operation_source = models.CharField(
        max_length=32,
        choices=AuditOperationSource.choices,
        null=False,
        blank=False,
        editable=False,
    )
    correlation_id = models.UUIDField(
        null=True,
        blank=True,
        editable=False,
    )
    metadata = models.JSONField(
        default=dict,
        blank=True,
        editable=False,
    )

    objects = AuditLogManager()

    class Meta:
        db_table = "audit_logs"
        verbose_name = "Audit Log"
        verbose_name_plural = "Audit Logs"
        ordering = ["-timestamp", "-id"]
        indexes = [
            models.Index(fields=["-timestamp", "-id"], name="audit_time_id_idx"),
            models.Index(fields=["action", "-timestamp"], name="audit_action_time_idx"),
            models.Index(fields=["target_type", "target_id", "-timestamp"], name="audit_target_time_idx"),
            models.Index(fields=["actor", "-timestamp"], name="audit_actor_time_idx"),
            models.Index(
                fields=["correlation_id", "-timestamp"],
                name="audit_correlation_time_idx",
                condition=Q(correlation_id__isnull=False),
            ),
            models.Index(
                fields=["organization_id", "-timestamp", "-id"],
                name="audit_org_time_id_idx",
                condition=Q(organization_id__isnull=False),
            ),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(action__in=AuditAction.values),
                name="audit_action_valid",
            ),
            models.CheckConstraint(
                condition=Q(target_type__in=AuditTargetType.values),
                name="audit_target_type_valid",
            ),
            models.CheckConstraint(
                condition=Q(operation_source__in=AuditOperationSource.values),
                name="audit_operation_source_valid",
            ),
            models.CheckConstraint(
                condition=(
                    ~Q(action__in=[
                        AuditAction.PRODUCT_CREATED,
                        AuditAction.PRODUCT_UPDATED,
                        AuditAction.PRODUCT_RETIRED,
                    ])
                    | Q(target_type=AuditTargetType.PRODUCT)
                ),
                name="audit_product_target_match",
            ),
            models.CheckConstraint(
                condition=(
                    ~Q(action__in=[
                        AuditAction.ORGANIZATION_CREATED,
                        AuditAction.ORGANIZATION_UPDATED,
                        AuditAction.ORGANIZATION_RETIRED,
                    ])
                    | Q(target_type=AuditTargetType.ORGANIZATION)
                ),
                name="audit_org_target_match",
            ),
            models.CheckConstraint(
                condition=(
                    ~Q(action__in=[
                        AuditAction.ENTITLEMENT_CREATED,
                        AuditAction.ENTITLEMENT_STATUS_CHANGED,
                        AuditAction.ENTITLEMENT_REVOKED,
                    ])
                    | Q(target_type=AuditTargetType.ENTITLEMENT)
                ),
                name="audit_entitlement_target_match",
            ),
            models.CheckConstraint(
                condition=(
                    ~Q(action__in=[
                        AuditAction.LOGIN_SUCCESS,
                        AuditAction.LOGOUT_SUCCESS,
                    ])
                    | Q(target_type=AuditTargetType.AUTH)
                ),
                name="audit_auth_target_match",
            ),
            models.CheckConstraint(
                condition=(
                    ~Q(action__in=[
                        AuditAction.LOGIN_SUCCESS,
                        AuditAction.LOGOUT_SUCCESS,
                    ])
                    | Q(operation_source=AuditOperationSource.AUTHENTICATION)
                ),
                name="audit_auth_source_match",
            ),
            models.CheckConstraint(
                condition=(
                    Q(action__in=[
                        AuditAction.LOGIN_SUCCESS,
                        AuditAction.LOGOUT_SUCCESS,
                    ])
                    | ~Q(operation_source=AuditOperationSource.AUTHENTICATION)
                ),
                name="audit_non_auth_source_match",
            ),
            models.CheckConstraint(
                condition=(
                    ~Q(operation_source__in=[
                        AuditOperationSource.BULK_IMPORT,
                        AuditOperationSource.INTEGRATION,
                    ])
                    | Q(correlation_id__isnull=False)
                ),
                name="audit_reserved_source_correlation",
            ),
            models.CheckConstraint(
                condition=(
                    ~Q(target_type=AuditTargetType.ORGANIZATION)
                    | (Q(organization_id__isnull=False) & Q(organization_id=F("target_id")))
                ),
                name="audit_org_id_match",
            ),
            models.CheckConstraint(
                condition=(
                    ~Q(target_type=AuditTargetType.ENTITLEMENT)
                    | Q(organization_id__isnull=False)
                ),
                name="audit_entitlement_org_id_req",
            ),
            models.CheckConstraint(
                condition=(
                    ~Q(action__in=[
                        AuditAction.MODULE_CREATED,
                        AuditAction.MODULE_UPDATED,
                        AuditAction.MODULE_RETIRED,
                    ])
                    | Q(target_type=AuditTargetType.MODULE)
                ),
                name="audit_module_target_match",
            ),
            models.CheckConstraint(
                condition=(
                    ~Q(action__in=[
                        AuditAction.FEATURE_CREATED,
                        AuditAction.FEATURE_UPDATED,
                        AuditAction.FEATURE_RETIRED,
                    ])
                    | Q(target_type=AuditTargetType.FEATURE)
                ),
                name="audit_feature_target_match",
            ),
            models.CheckConstraint(
                condition=(
                    ~Q(action__in=[
                        AuditAction.CAPABILITY_CREATED,
                        AuditAction.CAPABILITY_UPDATED,
                        AuditAction.CAPABILITY_RETIRED,
                    ])
                    | Q(target_type=AuditTargetType.CAPABILITY)
                ),
                name="audit_capability_target_match",
            ),
            models.CheckConstraint(
                condition=(
                    ~Q(action__in=[
                        AuditAction.PLAN_CREATED,
                        AuditAction.PLAN_UPDATED,
                    ])
                    | Q(target_type=AuditTargetType.PLAN)
                ),
                name="audit_plan_target_match",
            ),
            models.CheckConstraint(
                condition=(
                    ~Q(action__in=[
                        AuditAction.PLAN_VERSION_CREATED,
                        AuditAction.PLAN_VERSION_UPDATED,
                        AuditAction.PLAN_VERSION_CLONED,
                        AuditAction.PLAN_VERSION_ACTIVATED,
                        AuditAction.PLAN_VERSION_RETIRED,
                    ])
                    | Q(target_type=AuditTargetType.PLAN_VERSION)
                ),
                name="audit_plan_ver_target_match",
            ),
            models.CheckConstraint(
                condition=(
                    ~Q(action__in=[
                        AuditAction.PLAN_PRICE_CREATED,
                        AuditAction.PLAN_PRICE_UPDATED,
                        AuditAction.PLAN_PRICE_REMOVED,
                    ])
                    | Q(target_type=AuditTargetType.PLAN_PRICE)
                ),
                name="audit_plan_price_target_match",
            ),
            models.CheckConstraint(
                condition=(
                    ~Q(action__in=[
                        AuditAction.PLAN_PRODUCT_ADDED,
                        AuditAction.PLAN_PRODUCT_REMOVED,
                    ])
                    | Q(target_type=AuditTargetType.PLAN_PRODUCT)
                ),
                name="audit_plan_prod_target_match",
            ),
            models.CheckConstraint(
                condition=(
                    ~Q(action__in=[
                        AuditAction.PLAN_MODULE_ADDED,
                        AuditAction.PLAN_MODULE_REMOVED,
                    ])
                    | Q(target_type=AuditTargetType.PLAN_MODULE)
                ),
                name="audit_plan_mod_target_match",
            ),
            models.CheckConstraint(
                condition=(
                    ~Q(action__in=[
                        AuditAction.PLAN_CAPABILITY_ADDED,
                        AuditAction.PLAN_CAPABILITY_REMOVED,
                    ])
                    | Q(target_type=AuditTargetType.PLAN_CAPABILITY)
                ),
                name="audit_plan_cap_target_match",
            ),
            models.CheckConstraint(
                condition=(
                    ~Q(action__in=[
                        AuditAction.PLAN_QUOTA_CREATED,
                        AuditAction.PLAN_QUOTA_UPDATED,
                        AuditAction.PLAN_QUOTA_REMOVED,
                    ])
                    | Q(target_type=AuditTargetType.PLAN_QUOTA)
                ),
                name="audit_plan_quota_target_match",
            ),
            models.CheckConstraint(
                condition=(
                    ~Q(action__in=[
                        AuditAction.SUBSCRIPTION_CREATED,
                        AuditAction.SUBSCRIPTION_TRIAL_STARTED,
                        AuditAction.SUBSCRIPTION_TRIAL_CONVERTED,
                        AuditAction.SUBSCRIPTION_TRIAL_EXPIRED,
                        AuditAction.SUBSCRIPTION_PLAN_CHANGED,
                        AuditAction.SUBSCRIPTION_SUSPENDED,
                        AuditAction.SUBSCRIPTION_REACTIVATED,
                        AuditAction.SUBSCRIPTION_CANCELLED,
                        AuditAction.SUBSCRIPTION_RECONCILED,
                        AuditAction.SEAT_OVER_ALLOCATION_DETECTED,
                    ])
                    | Q(target_type=AuditTargetType.SUBSCRIPTION)
                ),
                name="audit_subscription_target_match",
            ),
            models.CheckConstraint(
                condition=(
                    ~Q(target_type=AuditTargetType.SUBSCRIPTION)
                    | Q(organization_id__isnull=False)
                ),
                name="audit_subscription_org_id_req",
            ),
            models.CheckConstraint(
                condition=(
                    ~Q(action__in=[
                        AuditAction.USER_CREATED,
                        AuditAction.USER_UPDATED,
                        AuditAction.USER_SUSPENDED,
                        AuditAction.USER_REACTIVATED,
                        AuditAction.USER_DISABLED,
                        AuditAction.SUPPORT_ROLE_GRANTED,
                        AuditAction.SUPPORT_ROLE_REVOKED,
                        AuditAction.USER_ANONYMIZED,
                    ])
                    | Q(target_type=AuditTargetType.USER)
                ),
                name="audit_user_target_match",
            ),
            models.CheckConstraint(
                condition=(
                    ~Q(action__in=[
                        AuditAction.MEMBERSHIP_CREATED,
                        AuditAction.MEMBERSHIP_UPDATED,
                        AuditAction.MEMBERSHIP_SUSPENDED,
                        AuditAction.MEMBERSHIP_REACTIVATED,
                        AuditAction.MEMBERSHIP_ENDED,
                        AuditAction.MEMBERSHIP_RESTORED,
                        AuditAction.MEMBERSHIP_ROLE_ASSIGNED,
                    ])
                    | Q(target_type=AuditTargetType.MEMBERSHIP)
                ),
                name="audit_membership_target_match",
            ),
            models.CheckConstraint(
                condition=(
                    ~Q(target_type=AuditTargetType.MEMBERSHIP)
                    | Q(organization_id__isnull=False)
                ),
                name="audit_membership_org_id_req",
            ),
            models.CheckConstraint(
                condition=(
                    ~Q(action__in=[
                        AuditAction.ROLE_CREATED,
                        AuditAction.ROLE_UPDATED,
                        AuditAction.ROLE_PERMISSIONS_CHANGED,
                        AuditAction.ROLE_RETIRED,
                    ])
                    | Q(target_type=AuditTargetType.ROLE)
                ),
                name="audit_role_target_match",
            ),
            models.CheckConstraint(
                condition=(
                    ~Q(action=AuditAction.CONSOLE_MODULE_POLICY_CHANGED)
                    | Q(target_type=AuditTargetType.CONSOLE_POLICY)
                ),
                name="audit_console_policy_target_match",
            ),
            models.CheckConstraint(
                condition=(
                    ~Q(action=AuditAction.PERMISSION_CEILING_CHANGED)
                    | Q(target_type=AuditTargetType.PERMISSION_CEILING)
                ),
                name="audit_permission_ceiling_target_match",
            ),
            models.CheckConstraint(
                condition=(
                    ~Q(target_type=AuditTargetType.ROLE)
                    | Q(organization_id__isnull=False)
                ),
                name="audit_role_org_id_req",
            ),
            models.CheckConstraint(
                condition=(
                    ~Q(target_type=AuditTargetType.CONSOLE_POLICY)
                    | Q(organization_id__isnull=False)
                ),
                name="audit_console_policy_org_id_req",
            ),
            models.CheckConstraint(
                condition=(
                    ~Q(target_type=AuditTargetType.PERMISSION_CEILING)
                    | Q(organization_id__isnull=False)
                ),
                name="audit_permission_ceiling_org_id_req",
            ),
            models.CheckConstraint(
                condition=(
                    ~Q(action__in=[
                        AuditAction.USER_PRODUCT_ASSIGNED,
                        AuditAction.USER_PRODUCT_SUSPENDED,
                        AuditAction.USER_PRODUCT_REACTIVATED,
                        AuditAction.USER_PRODUCT_REVOKED,
                        AuditAction.USER_MODULE_ASSIGNMENTS_REPLACED,
                    ])
                    | Q(target_type=AuditTargetType.USER_PRODUCT_ASSIGNMENT)
                ),
                name="audit_assignment_target_match",
            ),
            models.CheckConstraint(
                condition=(
                    ~Q(target_type=AuditTargetType.USER_PRODUCT_ASSIGNMENT)
                    | Q(organization_id__isnull=False)
                ),
                name="audit_assignment_org_id_req",
            ),
            models.CheckConstraint(
                condition=(
                    ~Q(action=AuditAction.ONBOARDING_STEP_TRANSITIONED)
                    | Q(target_type=AuditTargetType.ONBOARDING_CASE)
                ),
                name="audit_onboarding_target_match",
            ),
            models.CheckConstraint(
                condition=(
                    ~Q(action__in=[
                        AuditAction.INVITATION_ISSUED,
                        AuditAction.INVITATION_ACCEPTED,
                        AuditAction.INVITATION_REVOKED,
                    ])
                    | Q(target_type=AuditTargetType.INVITATION)
                ),
                name="audit_invitation_target_match",
            ),
            models.CheckConstraint(
                condition=(
                    ~Q(target_type=AuditTargetType.INVITATION)
                    | Q(organization_id__isnull=False)
                ),
                name="audit_invitation_org_id_req",
            ),
            models.CheckConstraint(
                condition=(
                    ~Q(action__in=[
                        AuditAction.BULK_IMPORT_JOB_CREATED,
                        AuditAction.BULK_IMPORT_JOB_COMMITTED,
                    ])
                    | Q(target_type=AuditTargetType.BULK_IMPORT_JOB)
                ),
                name="audit_bulk_import_target_match",
            ),
            models.CheckConstraint(
                condition=(
                    ~Q(action__in=[
                        AuditAction.ACCESS_REQUEST_CREATED,
                        AuditAction.ACCESS_REQUEST_APPROVED,
                        AuditAction.ACCESS_REQUEST_DENIED,
                        AuditAction.ACCESS_REQUEST_CANCELLED,
                    ])
                    | Q(target_type=AuditTargetType.ACCESS_REQUEST)
                ),
                name="audit_access_request_target_match",
            ),
            models.CheckConstraint(
                condition=(
                    ~Q(target_type=AuditTargetType.ACCESS_REQUEST)
                    | Q(organization_id__isnull=False)
                ),
                name="audit_access_request_org_id_req",
            ),
            models.CheckConstraint(
                condition=(
                    ~Q(target_type__in=[
                        AuditTargetType.PRODUCT,
                        AuditTargetType.AUTH,
                        AuditTargetType.MODULE,
                        AuditTargetType.FEATURE,
                        AuditTargetType.CAPABILITY,
                        AuditTargetType.PLAN,
                        AuditTargetType.PLAN_VERSION,
                        AuditTargetType.PLAN_PRICE,
                        AuditTargetType.PLAN_PRODUCT,
                        AuditTargetType.PLAN_MODULE,
                        AuditTargetType.PLAN_CAPABILITY,
                        AuditTargetType.PLAN_QUOTA,
                        AuditTargetType.USER,
                    ])
                    | Q(organization_id__isnull=True)
                ),
                name="audit_catalog_auth_org_id_null",
            ),
            models.CheckConstraint(
                condition=(
                    ~Q(action__in=[
                        AuditAction.DEVELOPER_APPLICATION_CREATED,
                        AuditAction.DEVELOPER_APPLICATION_UPDATED,
                        AuditAction.DEVELOPER_APPLICATION_SUSPENDED,
                        AuditAction.DEVELOPER_APPLICATION_REACTIVATED,
                        AuditAction.DEVELOPER_APPLICATION_REVOKED,
                    ])
                    | Q(target_type=AuditTargetType.DEVELOPER_APPLICATION)
                ),
                name="audit_dev_app_target_match",
            ),
            models.CheckConstraint(
                condition=(
                    ~Q(action__in=[
                        AuditAction.DEVELOPER_KEY_CREATED,
                        AuditAction.DEVELOPER_KEY_ROTATED,
                        AuditAction.DEVELOPER_KEY_REVOKED,
                    ])
                    | Q(target_type=AuditTargetType.DEVELOPER_KEY)
                ),
                name="audit_dev_key_target_match",
            ),
            models.CheckConstraint(
                condition=(
                    ~Q(action__in=[
                        AuditAction.DEVELOPER_WEBHOOK_CREATED,
                        AuditAction.DEVELOPER_WEBHOOK_UPDATED,
                        AuditAction.DEVELOPER_WEBHOOK_SUSPENDED,
                        AuditAction.DEVELOPER_WEBHOOK_REACTIVATED,
                        AuditAction.DEVELOPER_WEBHOOK_REVOKED,
                        AuditAction.DEVELOPER_WEBHOOK_SECRET_ROTATED,
                        AuditAction.DEVELOPER_WEBHOOK_REPLAYED,
                    ])
                    | Q(target_type=AuditTargetType.DEVELOPER_WEBHOOK)
                ),
                name="audit_dev_webhook_target_match",
            ),
            models.CheckConstraint(
                condition=(
                    ~Q(target_type__in=[
                        AuditTargetType.DEVELOPER_APPLICATION,
                        AuditTargetType.DEVELOPER_KEY,
                        AuditTargetType.DEVELOPER_WEBHOOK,
                    ])
                    | Q(organization_id__isnull=False)
                ),
                name="audit_dev_org_id_req",
            ),
            models.CheckConstraint(
                condition=(
                    ~Q(action__in=[
                        AuditAction.SUPPORT_IMPERSONATION_STARTED,
                        AuditAction.SUPPORT_IMPERSONATION_EXPIRED,
                        AuditAction.SUPPORT_IMPERSONATION_TERMINATED,
                        AuditAction.SUPPORT_IMPERSONATION_REVOKED,
                    ])
                    | Q(target_type=AuditTargetType.SUPPORT_IMPERSONATION)
                ),
                name="audit_support_impersonation_target_match",
            ),
        ]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise AuditLogImmutableError("Audit records are immutable and cannot be updated.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise AuditLogImmutableError("Audit records are append-only and cannot be deleted.")
