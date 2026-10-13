"""Audit Log Central Recording Service.

Provides a strictly validated, allowlist-enforced service for writing
immutable audit records. Rejects unvalidated request bodies, raw payloads,
and sensitive tokens.
"""

from decimal import Decimal
import re
from typing import Any
import uuid
from apps.auditlog.models import (
    AuditAction,
    AuditLog,
    AuditOperationSource,
    AuditTargetType,
)

PROHIBITED_SUBSTRINGS = (
    "password",
    "token",
    "secret",
    "cookie",
    "session",
    "csrf",
    "authorization",
    "api_key",
)

CATALOG_ACTIONS = {
    AuditAction.MODULE_CREATED,
    AuditAction.MODULE_UPDATED,
    AuditAction.MODULE_RETIRED,
    AuditAction.FEATURE_CREATED,
    AuditAction.FEATURE_UPDATED,
    AuditAction.FEATURE_RETIRED,
    AuditAction.CAPABILITY_CREATED,
    AuditAction.CAPABILITY_UPDATED,
    AuditAction.CAPABILITY_RETIRED,
}

CATALOG_BUSINESS_IDENTIFIER_FIELDS = {
    "product_code",
    "module_code",
    "feature_code",
    "code",
    "name",
}

PLAN_ACTIONS = {
    AuditAction.PLAN_CREATED,
    AuditAction.PLAN_UPDATED,
    AuditAction.PLAN_VERSION_CREATED,
    AuditAction.PLAN_VERSION_UPDATED,
    AuditAction.PLAN_VERSION_CLONED,
    AuditAction.PLAN_VERSION_ACTIVATED,
    AuditAction.PLAN_VERSION_RETIRED,
    AuditAction.PLAN_PRICE_CREATED,
    AuditAction.PLAN_PRICE_UPDATED,
    AuditAction.PLAN_PRICE_REMOVED,
    AuditAction.PLAN_PRODUCT_ADDED,
    AuditAction.PLAN_PRODUCT_REMOVED,
    AuditAction.PLAN_MODULE_ADDED,
    AuditAction.PLAN_MODULE_REMOVED,
    AuditAction.PLAN_CAPABILITY_ADDED,
    AuditAction.PLAN_CAPABILITY_REMOVED,
    AuditAction.PLAN_QUOTA_CREATED,
    AuditAction.PLAN_QUOTA_UPDATED,
    AuditAction.PLAN_QUOTA_REMOVED,
}

PLAN_BUSINESS_IDENTIFIER_FIELDS = {
    "code",
    "name",
    "plan_code",
    "product_code",
    "module_code",
    "feature_code",
    "capability_code",
    "quota_key",
    "change_summary",
    "previous_name",
    "resulting_name",
    "previous_description",
    "resulting_description",
    "previous_change_summary",
    "resulting_change_summary",
    "previous_unit",
    "resulting_unit",
    "unit",
}

SUBSCRIPTION_ACTIONS = {
    AuditAction.SUBSCRIPTION_CREATED,
    AuditAction.SUBSCRIPTION_TRIAL_STARTED,
    AuditAction.SUBSCRIPTION_TRIAL_CONVERTED,
    AuditAction.SUBSCRIPTION_TRIAL_EXPIRED,
    AuditAction.SUBSCRIPTION_PLAN_CHANGED,
    AuditAction.SUBSCRIPTION_SUSPENDED,
    AuditAction.SUBSCRIPTION_REACTIVATED,
    AuditAction.SUBSCRIPTION_CANCELLED,
    AuditAction.SUBSCRIPTION_RECONCILED,
}

SUBSCRIPTION_BUSINESS_IDENTIFIER_FIELDS = {
    "organization_code",
    "plan_code",
    "previous_plan_code",
    "resulting_plan_code",
    "change_reason",
    "cancellation_reason",
    "suspension_reason",
    "currency",
    "billing_interval",
    "status",
    "previous_status",
    "resulting_status",
    "trial_ends_at",
    "repaired_count",
}

USER_ACTIONS = {
    AuditAction.USER_CREATED,
    AuditAction.USER_UPDATED,
    AuditAction.USER_SUSPENDED,
    AuditAction.USER_REACTIVATED,
    AuditAction.USER_DISABLED,
    AuditAction.USER_ANONYMIZED,
}

SUPPORT_ROLE_ACTIONS = {
    AuditAction.SUPPORT_ROLE_GRANTED,
    AuditAction.SUPPORT_ROLE_REVOKED,
}

USER_BUSINESS_IDENTIFIER_FIELDS = {
    "email",
    "full_name",
    "status",
    "previous_status",
    "resulting_status",
    "reason",
}

MEMBERSHIP_ACTIONS = {
    AuditAction.MEMBERSHIP_CREATED,
    AuditAction.MEMBERSHIP_UPDATED,
    AuditAction.MEMBERSHIP_SUSPENDED,
    AuditAction.MEMBERSHIP_REACTIVATED,
    AuditAction.MEMBERSHIP_ENDED,
    AuditAction.MEMBERSHIP_RESTORED,
    AuditAction.MEMBERSHIP_ROLE_ASSIGNED,
}

MEMBERSHIP_BUSINESS_IDENTIFIER_FIELDS = {
    "organization_code",
    "user_email",
    "membership_type",
    "previous_membership_type",
    "resulting_membership_type",
    "status",
    "previous_status",
    "resulting_status",
    "reason",
    "prior_joined_at",
    "prior_ended_at",
    "new_joined_at",
    "ended_at",
    "membership_id",
    "previous_role_id",
    "previous_role_code",
    "resulting_role_id",
    "resulting_role_code",
    "organization_id",
}

ROLE_ACTIONS = {
    AuditAction.ROLE_CREATED,
    AuditAction.ROLE_UPDATED,
    AuditAction.ROLE_PERMISSIONS_CHANGED,
    AuditAction.ROLE_RETIRED,
}

ROLE_BUSINESS_IDENTIFIER_FIELDS = {
    "role_code",
    "role_name",
    "permission_keys",
    "added_permission_keys",
    "removed_permission_keys",
    "organization_id",
}

CONSOLE_POLICY_ACTIONS = {
    AuditAction.CONSOLE_MODULE_POLICY_CHANGED,
}

CONSOLE_POLICY_BUSINESS_IDENTIFIER_FIELDS = {
    "module_key",
    "organization_id",
}

PERMISSION_CEILING_ACTIONS = {
    AuditAction.PERMISSION_CEILING_CHANGED,
}

PERMISSION_CEILING_BUSINESS_IDENTIFIER_FIELDS = {
    "permission_key",
    "organization_id",
}

TENANT_ADMIN_ELIGIBLE_ACTIONS = {
    AuditAction.ROLE_CREATED,
    AuditAction.ROLE_UPDATED,
    AuditAction.ROLE_PERMISSIONS_CHANGED,
    AuditAction.ROLE_RETIRED,
    AuditAction.MEMBERSHIP_ROLE_ASSIGNED,
}

PLATFORM_OWNER_PHASE2E_ACTIONS = {
    AuditAction.CONSOLE_MODULE_POLICY_CHANGED,
    AuditAction.PERMISSION_CEILING_CHANGED,
}

ASSIGNMENT_ACTIONS = {
    AuditAction.USER_PRODUCT_ASSIGNED,
    AuditAction.USER_PRODUCT_SUSPENDED,
    AuditAction.USER_PRODUCT_REACTIVATED,
    AuditAction.USER_PRODUCT_REVOKED,
    AuditAction.USER_MODULE_ASSIGNMENTS_REPLACED,
    AuditAction.SEAT_OVER_ALLOCATION_DETECTED,
}

ASSIGNMENT_BUSINESS_IDENTIFIER_FIELDS = {
    "organization_code",
    "user_email",
    "product_code",
    "pool_scope",
    "pool_key",
    "quota_key",
    "suspension_reason",
    "reason",
    "detection_context",
    "previous_status",
    "resulting_status",
}

ONBOARDING_ACTIONS = {
    AuditAction.ONBOARDING_STEP_TRANSITIONED,
}

INVITATION_ACTIONS = {
    AuditAction.INVITATION_ISSUED,
    AuditAction.INVITATION_ACCEPTED,
    AuditAction.INVITATION_REVOKED,
}

BULK_IMPORT_ACTIONS = {
    AuditAction.BULK_IMPORT_JOB_CREATED,
    AuditAction.BULK_IMPORT_JOB_COMMITTED,
}

ACCESS_REQUEST_ACTIONS = {
    AuditAction.ACCESS_REQUEST_CREATED,
    AuditAction.ACCESS_REQUEST_APPROVED,
    AuditAction.ACCESS_REQUEST_DENIED,
    AuditAction.ACCESS_REQUEST_CANCELLED,
}

ACCESS_REQUEST_BUSINESS_IDENTIFIER_FIELDS = {
    "request_id",
    "product_code",
    "product_name",
    "requester_email",
    "approver_email",
    "decision",
    "reason",
    "status",
}

SHOWCASE_ACTIONS = {
    AuditAction.SHOWCASE_PROFILE_PUBLISHED,
    AuditAction.SHOWCASE_PROFILE_UNPUBLISHED,
    AuditAction.SHOWCASE_CONFIG_CHANGED,
}

SHOWCASE_BUSINESS_IDENTIFIER_FIELDS = {
    "product_code",
    "product_name",
    "visibility",
    "previous_visibility",
    "resulting_visibility",
    "profile_id",
}

ONBOARDING_BUSINESS_IDENTIFIER_FIELDS = {
    "case_id",
    "organization_code",
    "organization_name",
    "from_step",
    "to_step",
    "case_status",
    "admin_email",
    "plan_version_id",
}

DEVELOPER_APP_ACTIONS = {
    AuditAction.DEVELOPER_APPLICATION_CREATED,
    AuditAction.DEVELOPER_APPLICATION_UPDATED,
    AuditAction.DEVELOPER_APPLICATION_SUSPENDED,
    AuditAction.DEVELOPER_APPLICATION_REACTIVATED,
    AuditAction.DEVELOPER_APPLICATION_REVOKED,
}

DEVELOPER_KEY_ACTIONS = {
    AuditAction.DEVELOPER_KEY_CREATED,
    AuditAction.DEVELOPER_KEY_ROTATED,
    AuditAction.DEVELOPER_KEY_REVOKED,
}

DEVELOPER_WEBHOOK_ACTIONS = {
    AuditAction.DEVELOPER_WEBHOOK_CREATED,
    AuditAction.DEVELOPER_WEBHOOK_UPDATED,
    AuditAction.DEVELOPER_WEBHOOK_SUSPENDED,
    AuditAction.DEVELOPER_WEBHOOK_REACTIVATED,
    AuditAction.DEVELOPER_WEBHOOK_REVOKED,
    AuditAction.DEVELOPER_WEBHOOK_SECRET_ROTATED,
    AuditAction.DEVELOPER_WEBHOOK_REPLAYED,
}

DEVELOPER_ACTIONS = DEVELOPER_APP_ACTIONS | DEVELOPER_KEY_ACTIONS | DEVELOPER_WEBHOOK_ACTIONS

DEVELOPER_BUSINESS_IDENTIFIER_FIELDS = {
    "application_id",
    "application_name",
    "key_prefix",
    "key_id",
    "key_name",
    "scopes",
    "reason",
    "status",
    "previous_status",
    "resulting_status",
    "request_id",
    "ip_address",
    "is_emergency",
    "old_key_id",
    "old_key_prefix",
    "action",
    "subscription_id",
    "target_url",
    "event_topics",
    "delivery_id",
    "event_id",
    "event_type",
    "retry_attempt",
}

SUPPORT_IMPERSONATION_ACTIONS = {
    AuditAction.SUPPORT_IMPERSONATION_STARTED,
    AuditAction.SUPPORT_IMPERSONATION_EXPIRED,
    AuditAction.SUPPORT_IMPERSONATION_TERMINATED,
    AuditAction.SUPPORT_IMPERSONATION_REVOKED,
}

SUPPORT_IMPERSONATION_BUSINESS_IDENTIFIER_FIELDS = {
    "session_id",
    "operator_id",
    "operator_email",
    "target_user_id",
    "target_user_email",
    "target_organization_id",
    "reason",
    "ticket_reference",
    "correlation_id",
    "status",
    "lifecycle_event",
}


class AuditEventError(Exception):
    """Base exception raised when an audit event fails validation or recording."""
    pass


def _validate_uuid(val: Any, field_name: str) -> uuid.UUID:
    if isinstance(val, uuid.UUID):
        return val
    try:
        return uuid.UUID(str(val))
    except (ValueError, TypeError, AttributeError):
        raise AuditEventError(f"Field '{field_name}' must be a valid UUID.")


def _assert_no_prohibited_terms(data: dict[str, Any], action: str | None = None) -> None:
    for key, value in data.items():
        key_lower = str(key).lower()
        if key in ("impersonation", "session_id") or (action in SUPPORT_IMPERSONATION_ACTIONS and key in SUPPORT_IMPERSONATION_BUSINESS_IDENTIFIER_FIELDS):
            if key == "impersonation" and isinstance(value, dict):
                _assert_no_prohibited_terms(value, action)
            continue
        if any(term in key_lower for term in PROHIBITED_SUBSTRINGS):
            raise AuditEventError(f"Prohibited sensitive term detected in metadata key '{key}'.")
        if isinstance(value, str):
            # The approved metadata schema for authentication events requires auth_method="session".
            # This specific key-value pair describes the authentication mechanism and is not a credential.
            if key == "auth_method" and value == "session":
                continue
            if action in CATALOG_ACTIONS and key in CATALOG_BUSINESS_IDENTIFIER_FIELDS:
                continue
            if action in PLAN_ACTIONS and key in PLAN_BUSINESS_IDENTIFIER_FIELDS:
                continue
            if action in SUBSCRIPTION_ACTIONS and key in SUBSCRIPTION_BUSINESS_IDENTIFIER_FIELDS:
                continue
            if action in USER_ACTIONS and key in USER_BUSINESS_IDENTIFIER_FIELDS:
                continue
            if action in MEMBERSHIP_ACTIONS and key in MEMBERSHIP_BUSINESS_IDENTIFIER_FIELDS:
                continue
            if action in ROLE_ACTIONS and key in ROLE_BUSINESS_IDENTIFIER_FIELDS:
                continue
            if action in CONSOLE_POLICY_ACTIONS and key in CONSOLE_POLICY_BUSINESS_IDENTIFIER_FIELDS:
                continue
            if action in PERMISSION_CEILING_ACTIONS and key in PERMISSION_CEILING_BUSINESS_IDENTIFIER_FIELDS:
                continue
            if action in ASSIGNMENT_ACTIONS and key in ASSIGNMENT_BUSINESS_IDENTIFIER_FIELDS:
                continue
            if action in ONBOARDING_ACTIONS and key in ONBOARDING_BUSINESS_IDENTIFIER_FIELDS:
                continue
            if action in ACCESS_REQUEST_ACTIONS and key in ACCESS_REQUEST_BUSINESS_IDENTIFIER_FIELDS:
                continue
            if action in SHOWCASE_ACTIONS and key in SHOWCASE_BUSINESS_IDENTIFIER_FIELDS:
                continue
            if action in DEVELOPER_ACTIONS and key in DEVELOPER_BUSINESS_IDENTIFIER_FIELDS:
                continue
            if action in SUPPORT_IMPERSONATION_ACTIONS and key in SUPPORT_IMPERSONATION_BUSINESS_IDENTIFIER_FIELDS:
                continue
            val_lower = value.lower()
            if any(term in val_lower for term in PROHIBITED_SUBSTRINGS):
                raise AuditEventError(f"Prohibited sensitive term detected in metadata value for '{key}'.")


def _validate_uuid_string(val: Any, field_name: str) -> str:
    if not isinstance(val, str):
        raise AuditEventError(f"Field '{field_name}' must be a string UUID.")
    try:
        u = uuid.UUID(val)
        if str(u) != val.lower():
            raise AuditEventError(f"Field '{field_name}' must be a canonical lowercase UUID string.")
        return val
    except (ValueError, TypeError, AttributeError):
        raise AuditEventError(f"Field '{field_name}' must be a valid UUID string.")


def _validate_optional_uuid_string(val: Any, field_name: str) -> str | None:
    if val is None:
        return None
    return _validate_uuid_string(val, field_name)


def _validate_canonical_money(val: Any, field_name: str) -> None:
    if not isinstance(val, str):
        raise AuditEventError(f"Field '{field_name}' must be a canonical money string.")
    if not re.match(r"^(?:0|[1-9][0-9]*)\.[0-9]{2}$", val):
        raise AuditEventError(f"Field '{field_name}' must be a canonical fixed two-decimal string, got '{val}'.")
    try:
        dec = Decimal(val)
        if dec < Decimal("0.00") or dec > Decimal("9999999999.99"):
            raise AuditEventError(f"Field '{field_name}' out of canonical money range [0.00, 9999999999.99].")
    except Exception:
        raise AuditEventError(f"Field '{field_name}' is not a valid decimal.")


def _validate_canonical_quota_limit(limit_type: str, limit_value: Any, field_name: str = "limit_value") -> None:
    if limit_type == "unlimited":
        if limit_value is not None:
            raise AuditEventError(f"Field '{field_name}' must be None when limit_type is 'unlimited'.")
    elif limit_type == "numeric":
        if limit_value is None:
            raise AuditEventError(f"Field '{field_name}' must not be None when limit_type is 'numeric'.")
        if not isinstance(limit_value, str):
            raise AuditEventError(f"Field '{field_name}' must be a canonical decimal string, got {type(limit_value).__name__}.")
        if limit_value != "0" and not re.match(r"^[1-9][0-9]*$", limit_value):
            raise AuditEventError(f"Field '{field_name}' has invalid canonical format or leading zeros: '{limit_value}'.")
        try:
            int_val = int(limit_value)
            if int_val < 0 or int_val > 9223372036854775807:
                raise AuditEventError(f"Field '{field_name}' out of 64-bit integer range: {int_val}.")
        except ValueError:
            raise AuditEventError(f"Field '{field_name}' is not a valid integer string.")
    else:
        raise AuditEventError(f"Invalid limit_type '{limit_type}'.")


def _validate_metadata(action: str, metadata: dict[str, Any]) -> None:
    if not isinstance(metadata, dict):
        raise AuditEventError("Metadata must be a dictionary.")

    _assert_no_prohibited_terms(metadata, action=action)

    if action == AuditAction.PRODUCT_CREATED:
        expected_keys = {"code", "name", "status"}
        if set(metadata.keys()) != expected_keys:
            raise AuditEventError(f"Invalid metadata keys for '{action}'. Expected: {expected_keys}")
        if not isinstance(metadata["code"], str) or len(metadata["code"]) > 50 or not metadata["code"].strip():
            raise AuditEventError("Product 'code' must be a non-empty string up to 50 characters.")
        if not isinstance(metadata["name"], str) or len(metadata["name"]) > 100 or not metadata["name"].strip():
            raise AuditEventError("Product 'name' must be a non-empty string up to 100 characters.")
        if metadata["status"] != "draft":
            raise AuditEventError("Product creation status must be 'draft'.")

    elif action == AuditAction.PRODUCT_UPDATED:
        expected_keys = {"name_changed", "description_changed", "status_changed", "previous_status", "resulting_status"}
        if set(metadata.keys()) != expected_keys:
            raise AuditEventError(f"Invalid metadata keys for '{action}'. Expected: {expected_keys}")
        for flag in ("name_changed", "description_changed", "status_changed"):
            if type(metadata[flag]) is not bool:
                raise AuditEventError(f"Field '{flag}' must be a boolean.")

        prev = metadata["previous_status"]
        resulting = metadata["resulting_status"]
        status_changed = metadata["status_changed"]

        allowed_all = {"draft", "active", "inactive", "retired"}
        if prev not in allowed_all:
            raise AuditEventError(f"Invalid 'previous_status' for '{action}': '{prev}'.")
        if resulting not in allowed_all:
            raise AuditEventError(f"Invalid 'resulting_status' for '{action}': '{resulting}'.")

        if status_changed != (prev != resulting):
            raise AuditEventError(
                f"Field 'status_changed' ({status_changed}) does not match whether previous_status ('{prev}') and resulting_status ('{resulting}') differ."
            )

        if resulting == "retired" and prev != "retired":
            raise AuditEventError("Transition into 'retired' must be recorded using 'product_retired', not 'product_updated'.")

        if prev == "retired":
            if resulting != "retired":
                raise AuditEventError(f"Cannot transition product out of 'retired' to '{resulting}'.")
            # prev == "retired" and resulting == "retired": allowed only with status_changed=False (enforced above)

        if status_changed:
            allowed_transitions = {
                "draft": {"active", "inactive"},
                "active": {"inactive"},
                "inactive": {"active"},
            }
            if resulting not in allowed_transitions.get(prev, set()):
                raise AuditEventError(f"Invalid status transition from '{prev}' to '{resulting}'.")

    elif action == AuditAction.PRODUCT_RETIRED:
        expected_keys = {"name_changed", "description_changed", "previous_status", "resulting_status"}
        if set(metadata.keys()) != expected_keys:
            raise AuditEventError(f"Invalid metadata keys for '{action}'. Expected: {expected_keys}")
        for flag in ("name_changed", "description_changed"):
            if type(metadata[flag]) is not bool:
                raise AuditEventError(f"Field '{flag}' must be a boolean.")
        allowed_prev = {"draft", "active", "inactive"}
        if metadata["previous_status"] not in allowed_prev:
            raise AuditEventError(f"Invalid 'previous_status' for '{action}': '{metadata['previous_status']}'.")
        if metadata["resulting_status"] != "retired":
            raise AuditEventError("Product retirement 'resulting_status' must be 'retired'.")

    elif action == AuditAction.ORGANIZATION_CREATED:
        expected_keys = {"code", "name", "status"}
        if set(metadata.keys()) != expected_keys:
            raise AuditEventError(f"Invalid metadata keys for '{action}'. Expected: {expected_keys}")
        if not isinstance(metadata["code"], str) or len(metadata["code"]) > 50 or not metadata["code"].strip():
            raise AuditEventError("Organization 'code' must be a non-empty string up to 50 characters.")
        if not isinstance(metadata["name"], str) or len(metadata["name"]) > 150 or not metadata["name"].strip():
            raise AuditEventError("Organization 'name' must be a non-empty string up to 150 characters.")
        if metadata["status"] != "draft":
            raise AuditEventError("Organization creation status must be 'draft'.")

    elif action == AuditAction.ORGANIZATION_UPDATED:
        expected_keys = {"name_changed", "description_changed", "status_changed", "previous_status", "resulting_status"}
        if set(metadata.keys()) != expected_keys:
            raise AuditEventError(f"Invalid metadata keys for '{action}'. Expected: {expected_keys}")
        for flag in ("name_changed", "description_changed", "status_changed"):
            if type(metadata[flag]) is not bool:
                raise AuditEventError(f"Field '{flag}' must be a boolean.")

        prev = metadata["previous_status"]
        resulting = metadata["resulting_status"]
        status_changed = metadata["status_changed"]

        if prev == "retired" or resulting == "retired":
            if resulting == "retired" and prev != "retired":
                raise AuditEventError("Transition into 'retired' must be recorded using 'organization_retired', not 'organization_updated'.")
            raise AuditEventError(f"Retired status is not permitted under '{action}'.")

        allowed_statuses = {"draft", "active", "suspended"}
        if prev not in allowed_statuses:
            raise AuditEventError(f"Invalid 'previous_status' for '{action}': '{prev}'.")
        if resulting not in allowed_statuses:
            raise AuditEventError(f"Invalid 'resulting_status' for '{action}': '{resulting}'.")

        if status_changed != (prev != resulting):
            raise AuditEventError(
                f"Field 'status_changed' ({status_changed}) does not match whether previous_status ('{prev}') and resulting_status ('{resulting}') differ."
            )

        if status_changed:
            allowed_transitions = {
                "draft": {"active"},
                "active": {"suspended"},
                "suspended": {"active"},
            }
            if resulting not in allowed_transitions.get(prev, set()):
                raise AuditEventError(f"Invalid status transition from '{prev}' to '{resulting}'.")

    elif action == AuditAction.ORGANIZATION_RETIRED:
        expected_keys = {"name_changed", "description_changed", "previous_status", "resulting_status"}
        if set(metadata.keys()) != expected_keys:
            raise AuditEventError(f"Invalid metadata keys for '{action}'. Expected: {expected_keys}")
        for flag in ("name_changed", "description_changed"):
            if type(metadata[flag]) is not bool:
                raise AuditEventError(f"Field '{flag}' must be a boolean.")
        allowed_prev = {"draft", "active", "suspended"}
        if metadata["previous_status"] not in allowed_prev:
            raise AuditEventError(f"Invalid 'previous_status' for '{action}': '{metadata['previous_status']}'.")
        if metadata["resulting_status"] != "retired":
            raise AuditEventError("Organization retirement 'resulting_status' must be 'retired'.")

    elif action == AuditAction.ENTITLEMENT_CREATED:
        expected_keys = {"organization_code", "product_id", "product_code", "previous_status", "resulting_status"}
        if set(metadata.keys()) != expected_keys:
            raise AuditEventError(f"Invalid metadata keys for '{action}'. Expected: {expected_keys}")
        if not isinstance(metadata["organization_code"], str) or len(metadata["organization_code"]) > 50:
            raise AuditEventError("Entitlement 'organization_code' must be a string up to 50 characters.")
        _validate_uuid(metadata["product_id"], "product_id in metadata")
        if not isinstance(metadata["product_code"], str) or len(metadata["product_code"]) > 50:
            raise AuditEventError("Entitlement 'product_code' must be a string up to 50 characters.")
        if metadata["previous_status"] is not None:
            raise AuditEventError("Entitlement creation 'previous_status' must be None.")
        if metadata["resulting_status"] != "draft":
            raise AuditEventError("Entitlement creation 'resulting_status' must be 'draft'.")

    elif action == AuditAction.ENTITLEMENT_STATUS_CHANGED:
        expected_keys = {"organization_code", "product_id", "product_code", "previous_status", "resulting_status"}
        if set(metadata.keys()) != expected_keys:
            raise AuditEventError(f"Invalid metadata keys for '{action}'. Expected: {expected_keys}")
        if not isinstance(metadata["organization_code"], str) or len(metadata["organization_code"]) > 50:
            raise AuditEventError("Entitlement 'organization_code' must be a string up to 50 characters.")
        _validate_uuid(metadata["product_id"], "product_id in metadata")
        if not isinstance(metadata["product_code"], str) or len(metadata["product_code"]) > 50:
            raise AuditEventError("Entitlement 'product_code' must be a string up to 50 characters.")
        allowed_prev = {"draft", "active", "suspended"}
        allowed_result = {"active", "suspended"}
        if metadata["previous_status"] not in allowed_prev:
            raise AuditEventError(f"Invalid 'previous_status' for '{action}': '{metadata['previous_status']}'.")
        if metadata["resulting_status"] not in allowed_result:
            raise AuditEventError(f"Invalid 'resulting_status' for '{action}': '{metadata['resulting_status']}'.")

    elif action == AuditAction.ENTITLEMENT_REVOKED:
        expected_keys = {"organization_code", "product_id", "product_code", "previous_status", "resulting_status"}
        if set(metadata.keys()) != expected_keys:
            raise AuditEventError(f"Invalid metadata keys for '{action}'. Expected: {expected_keys}")
        if not isinstance(metadata["organization_code"], str) or len(metadata["organization_code"]) > 50:
            raise AuditEventError("Entitlement 'organization_code' must be a string up to 50 characters.")
        _validate_uuid(metadata["product_id"], "product_id in metadata")
        if not isinstance(metadata["product_code"], str) or len(metadata["product_code"]) > 50:
            raise AuditEventError("Entitlement 'product_code' must be a string up to 50 characters.")
        allowed_prev = {"draft", "active", "suspended"}
        if metadata["previous_status"] not in allowed_prev:
            raise AuditEventError(f"Invalid 'previous_status' for '{action}': '{metadata['previous_status']}'.")
        if metadata["resulting_status"] != "revoked":
            raise AuditEventError("Entitlement revocation 'resulting_status' must be 'revoked'.")

    elif action in (AuditAction.LOGIN_SUCCESS, AuditAction.LOGOUT_SUCCESS):
        expected_keys = {"auth_method"}
        if set(metadata.keys()) != expected_keys:
            raise AuditEventError(f"Invalid metadata keys for '{action}'. Expected: {expected_keys}")
        if metadata["auth_method"] != "session":
            raise AuditEventError(f"Invalid 'auth_method' for '{action}'. Must be 'session'.")

    elif action == AuditAction.MODULE_CREATED:
        expected_keys = {"product_id", "product_code", "code", "name", "display_order", "status"}
        if set(metadata.keys()) != expected_keys:
            raise AuditEventError(f"Invalid metadata keys for '{action}'. Expected: {expected_keys}")
        _validate_uuid(metadata["product_id"], "product_id in metadata")
        if not isinstance(metadata["product_code"], str) or len(metadata["product_code"]) > 50 or not metadata["product_code"].strip():
            raise AuditEventError("Metadata 'product_code' must be a non-empty string up to 50 characters.")
        if not isinstance(metadata["code"], str) or len(metadata["code"]) > 50 or not metadata["code"].strip():
            raise AuditEventError("Module 'code' must be a non-empty string up to 50 characters.")
        if not isinstance(metadata["name"], str) or len(metadata["name"]) > 100 or not metadata["name"].strip():
            raise AuditEventError("Module 'name' must be a non-empty string up to 100 characters.")
        if type(metadata["display_order"]) is not int or metadata["display_order"] < 0:
            raise AuditEventError("Module 'display_order' must be a non-negative integer.")
        if metadata["status"] != "draft":
            raise AuditEventError("Module creation status must be 'draft'.")

    elif action == AuditAction.MODULE_UPDATED:
        expected_keys = {
            "product_id",
            "product_code",
            "code_changed",
            "name_changed",
            "description_changed",
            "display_order_changed",
            "status_changed",
            "previous_status",
            "resulting_status",
        }
        if set(metadata.keys()) != expected_keys:
            raise AuditEventError(f"Invalid metadata keys for '{action}'. Expected: {expected_keys}")
        _validate_uuid(metadata["product_id"], "product_id in metadata")
        if not isinstance(metadata["product_code"], str) or len(metadata["product_code"]) > 50 or not metadata["product_code"].strip():
            raise AuditEventError("Metadata 'product_code' must be a non-empty string up to 50 characters.")
        for flag in ("code_changed", "name_changed", "description_changed", "display_order_changed", "status_changed"):
            if type(metadata[flag]) is not bool:
                raise AuditEventError(f"Field '{flag}' must be a boolean.")

        prev = metadata["previous_status"]
        resulting = metadata["resulting_status"]
        status_changed = metadata["status_changed"]
        allowed_all = {"draft", "active", "retired"}

        if prev not in allowed_all:
            raise AuditEventError(f"Invalid 'previous_status' for '{action}': '{prev}'.")
        if resulting not in allowed_all:
            raise AuditEventError(f"Invalid 'resulting_status' for '{action}': '{resulting}'.")
        if status_changed != (prev != resulting):
            raise AuditEventError(
                f"Field 'status_changed' ({status_changed}) does not match whether previous_status ('{prev}') and resulting_status ('{resulting}') differ."
            )
        if resulting == "retired" and prev != "retired":
            raise AuditEventError("Transition into 'retired' must be recorded using 'module_retired', not 'module_updated'.")
        if prev == "retired":
            raise AuditEventError("Cannot modify or transition a retired module.")
        if status_changed:
            if prev == "draft" and resulting != "active":
                raise AuditEventError(f"Invalid status transition from '{prev}' to '{resulting}'.")
            if prev == "active":
                raise AuditEventError(f"Cannot transition active module directly to '{resulting}' via module_updated.")

    elif action == AuditAction.MODULE_RETIRED:
        expected_keys = {"product_id", "product_code", "previous_status", "resulting_status"}
        if set(metadata.keys()) != expected_keys:
            raise AuditEventError(f"Invalid metadata keys for '{action}'. Expected: {expected_keys}")
        _validate_uuid(metadata["product_id"], "product_id in metadata")
        if not isinstance(metadata["product_code"], str) or len(metadata["product_code"]) > 50 or not metadata["product_code"].strip():
            raise AuditEventError("Metadata 'product_code' must be a non-empty string up to 50 characters.")
        allowed_prev = {"draft", "active"}
        if metadata["previous_status"] not in allowed_prev:
            raise AuditEventError(f"Invalid 'previous_status' for '{action}': '{metadata['previous_status']}'.")
        if metadata["resulting_status"] != "retired":
            raise AuditEventError("Module retirement 'resulting_status' must be 'retired'.")

    elif action == AuditAction.FEATURE_CREATED:
        expected_keys = {"product_id", "product_code", "module_id", "module_code", "code", "name", "display_order", "status"}
        if set(metadata.keys()) != expected_keys:
            raise AuditEventError(f"Invalid metadata keys for '{action}'. Expected: {expected_keys}")
        _validate_uuid(metadata["product_id"], "product_id in metadata")
        _validate_uuid(metadata["module_id"], "module_id in metadata")
        if not isinstance(metadata["product_code"], str) or len(metadata["product_code"]) > 50 or not metadata["product_code"].strip():
            raise AuditEventError("Metadata 'product_code' must be a non-empty string up to 50 characters.")
        if not isinstance(metadata["module_code"], str) or len(metadata["module_code"]) > 50 or not metadata["module_code"].strip():
            raise AuditEventError("Metadata 'module_code' must be a non-empty string up to 50 characters.")
        if not isinstance(metadata["code"], str) or len(metadata["code"]) > 50 or not metadata["code"].strip():
            raise AuditEventError("Feature 'code' must be a non-empty string up to 50 characters.")
        if not isinstance(metadata["name"], str) or len(metadata["name"]) > 100 or not metadata["name"].strip():
            raise AuditEventError("Feature 'name' must be a non-empty string up to 100 characters.")
        if type(metadata["display_order"]) is not int or metadata["display_order"] < 0:
            raise AuditEventError("Feature 'display_order' must be a non-negative integer.")
        if metadata["status"] != "draft":
            raise AuditEventError("Feature creation status must be 'draft'.")

    elif action == AuditAction.FEATURE_UPDATED:
        expected_keys = {
            "product_id",
            "product_code",
            "module_id",
            "module_code",
            "code_changed",
            "name_changed",
            "description_changed",
            "display_order_changed",
            "status_changed",
            "previous_status",
            "resulting_status",
        }
        if set(metadata.keys()) != expected_keys:
            raise AuditEventError(f"Invalid metadata keys for '{action}'. Expected: {expected_keys}")
        _validate_uuid(metadata["product_id"], "product_id in metadata")
        _validate_uuid(metadata["module_id"], "module_id in metadata")
        if not isinstance(metadata["product_code"], str) or len(metadata["product_code"]) > 50 or not metadata["product_code"].strip():
            raise AuditEventError("Metadata 'product_code' must be a non-empty string up to 50 characters.")
        if not isinstance(metadata["module_code"], str) or len(metadata["module_code"]) > 50 or not metadata["module_code"].strip():
            raise AuditEventError("Metadata 'module_code' must be a non-empty string up to 50 characters.")
        for flag in ("code_changed", "name_changed", "description_changed", "display_order_changed", "status_changed"):
            if type(metadata[flag]) is not bool:
                raise AuditEventError(f"Field '{flag}' must be a boolean.")

        prev = metadata["previous_status"]
        resulting = metadata["resulting_status"]
        status_changed = metadata["status_changed"]
        allowed_all = {"draft", "active", "retired"}

        if prev not in allowed_all:
            raise AuditEventError(f"Invalid 'previous_status' for '{action}': '{prev}'.")
        if resulting not in allowed_all:
            raise AuditEventError(f"Invalid 'resulting_status' for '{action}': '{resulting}'.")
        if status_changed != (prev != resulting):
            raise AuditEventError(
                f"Field 'status_changed' ({status_changed}) does not match whether previous_status ('{prev}') and resulting_status ('{resulting}') differ."
            )
        if resulting == "retired" and prev != "retired":
            raise AuditEventError("Transition into 'retired' must be recorded using 'feature_retired', not 'feature_updated'.")
        if prev == "retired":
            raise AuditEventError("Cannot modify or transition a retired feature.")
        if status_changed:
            if prev == "draft" and resulting != "active":
                raise AuditEventError(f"Invalid status transition from '{prev}' to '{resulting}'.")
            if prev == "active":
                raise AuditEventError(f"Cannot transition active feature directly to '{resulting}' via feature_updated.")

    elif action == AuditAction.FEATURE_RETIRED:
        expected_keys = {"product_id", "product_code", "module_id", "module_code", "previous_status", "resulting_status"}
        if set(metadata.keys()) != expected_keys:
            raise AuditEventError(f"Invalid metadata keys for '{action}'. Expected: {expected_keys}")
        _validate_uuid(metadata["product_id"], "product_id in metadata")
        _validate_uuid(metadata["module_id"], "module_id in metadata")
        if not isinstance(metadata["product_code"], str) or len(metadata["product_code"]) > 50 or not metadata["product_code"].strip():
            raise AuditEventError("Metadata 'product_code' must be a non-empty string up to 50 characters.")
        if not isinstance(metadata["module_code"], str) or len(metadata["module_code"]) > 50 or not metadata["module_code"].strip():
            raise AuditEventError("Metadata 'module_code' must be a non-empty string up to 50 characters.")
        allowed_prev = {"draft", "active"}
        if metadata["previous_status"] not in allowed_prev:
            raise AuditEventError(f"Invalid 'previous_status' for '{action}': '{metadata['previous_status']}'.")
        if metadata["resulting_status"] != "retired":
            raise AuditEventError("Feature retirement 'resulting_status' must be 'retired'.")

    elif action == AuditAction.CAPABILITY_CREATED:
        expected_keys = {
            "product_id",
            "product_code",
            "module_id",
            "module_code",
            "feature_id",
            "feature_code",
            "code",
            "name",
            "display_order",
            "status",
        }
        if set(metadata.keys()) != expected_keys:
            raise AuditEventError(f"Invalid metadata keys for '{action}'. Expected: {expected_keys}")
        _validate_uuid(metadata["product_id"], "product_id in metadata")
        _validate_uuid(metadata["module_id"], "module_id in metadata")
        _validate_uuid(metadata["feature_id"], "feature_id in metadata")
        for key in ("product_code", "module_code", "feature_code", "code"):
            if not isinstance(metadata[key], str) or len(metadata[key]) > 50 or not metadata[key].strip():
                raise AuditEventError(f"Metadata '{key}' must be a non-empty string up to 50 characters.")
        if not isinstance(metadata["name"], str) or len(metadata["name"]) > 100 or not metadata["name"].strip():
            raise AuditEventError("Capability 'name' must be a non-empty string up to 100 characters.")
        if type(metadata["display_order"]) is not int or metadata["display_order"] < 0:
            raise AuditEventError("Capability 'display_order' must be a non-negative integer.")
        if metadata["status"] != "draft":
            raise AuditEventError("Capability creation status must be 'draft'.")

    elif action == AuditAction.CAPABILITY_UPDATED:
        expected_keys = {
            "product_id",
            "product_code",
            "module_id",
            "module_code",
            "feature_id",
            "feature_code",
            "code_changed",
            "name_changed",
            "description_changed",
            "display_order_changed",
            "status_changed",
            "previous_status",
            "resulting_status",
        }
        if set(metadata.keys()) != expected_keys:
            raise AuditEventError(f"Invalid metadata keys for '{action}'. Expected: {expected_keys}")
        _validate_uuid(metadata["product_id"], "product_id in metadata")
        _validate_uuid(metadata["module_id"], "module_id in metadata")
        _validate_uuid(metadata["feature_id"], "feature_id in metadata")
        for key in ("product_code", "module_code", "feature_code"):
            if not isinstance(metadata[key], str) or len(metadata[key]) > 50 or not metadata[key].strip():
                raise AuditEventError(f"Metadata '{key}' must be a non-empty string up to 50 characters.")
        for flag in ("code_changed", "name_changed", "description_changed", "display_order_changed", "status_changed"):
            if type(metadata[flag]) is not bool:
                raise AuditEventError(f"Field '{flag}' must be a boolean.")

        prev = metadata["previous_status"]
        resulting = metadata["resulting_status"]
        status_changed = metadata["status_changed"]
        allowed_all = {"draft", "active", "retired"}

        if prev not in allowed_all:
            raise AuditEventError(f"Invalid 'previous_status' for '{action}': '{prev}'.")
        if resulting not in allowed_all:
            raise AuditEventError(f"Invalid 'resulting_status' for '{action}': '{resulting}'.")
        if status_changed != (prev != resulting):
            raise AuditEventError(
                f"Field 'status_changed' ({status_changed}) does not match whether previous_status ('{prev}') and resulting_status ('{resulting}') differ."
            )
        if resulting == "retired" and prev != "retired":
            raise AuditEventError("Transition into 'retired' must be recorded using 'capability_retired', not 'capability_updated'.")
        if prev == "retired":
            raise AuditEventError("Cannot modify or transition a retired capability.")
        if status_changed:
            if prev == "draft" and resulting != "active":
                raise AuditEventError(f"Invalid status transition from '{prev}' to '{resulting}'.")
            if prev == "active":
                raise AuditEventError(f"Cannot transition active capability directly to '{resulting}' via capability_updated.")

    elif action == AuditAction.CAPABILITY_RETIRED:
        expected_keys = {
            "product_id",
            "product_code",
            "module_id",
            "module_code",
            "feature_id",
            "feature_code",
            "previous_status",
            "resulting_status",
        }
        if set(metadata.keys()) != expected_keys:
            raise AuditEventError(f"Invalid metadata keys for '{action}'. Expected: {expected_keys}")
        _validate_uuid(metadata["product_id"], "product_id in metadata")
        _validate_uuid(metadata["module_id"], "module_id in metadata")
        _validate_uuid(metadata["feature_id"], "feature_id in metadata")
        for key in ("product_code", "module_code", "feature_code"):
            if not isinstance(metadata[key], str) or len(metadata[key]) > 50 or not metadata[key].strip():
                raise AuditEventError(f"Metadata '{key}' must be a non-empty string up to 50 characters.")
        allowed_prev = {"draft", "active"}
        if metadata["previous_status"] not in allowed_prev:
            raise AuditEventError(f"Invalid 'previous_status' for '{action}': '{metadata['previous_status']}'.")
        if metadata["resulting_status"] != "retired":
            raise AuditEventError("Capability retirement 'resulting_status' must be 'retired'.")

    elif action == AuditAction.PLAN_CREATED:
        expected_keys = {"code", "name", "initial_version"}
        if set(metadata.keys()) != expected_keys:
            raise AuditEventError(f"Invalid metadata keys for '{action}'. Expected: {expected_keys}")
        code = metadata["code"]
        if not isinstance(code, str) or len(code) > 50 or not re.match(r"^[a-z0-9]+(?:[-_][a-z0-9]+)*$", code):
            raise AuditEventError("Plan 'code' must be lowercase alphanumeric with separators up to 50 chars.")
        name = metadata["name"]
        if not isinstance(name, str) or len(name) > 100 or not name.strip():
            raise AuditEventError("Plan 'name' must be a non-empty string up to 100 characters.")
        if type(metadata["initial_version"]) is not int or metadata["initial_version"] != 1:
            raise AuditEventError("Plan 'initial_version' must be integer 1.")

    elif action == AuditAction.PLAN_UPDATED:
        expected_keys = {
            "code",
            "name_changed",
            "description_changed",
            "previous_name",
            "resulting_name",
            "previous_description",
            "resulting_description",
        }
        if set(metadata.keys()) != expected_keys:
            raise AuditEventError(f"Invalid metadata keys for '{action}'. Expected: {expected_keys}")
        code = metadata["code"]
        if not isinstance(code, str) or len(code) > 50 or not code.strip():
            raise AuditEventError("Plan 'code' must be a non-empty string up to 50 characters.")
        for flag in ("name_changed", "description_changed"):
            if type(metadata[flag]) is not bool:
                raise AuditEventError(f"Field '{flag}' must be a boolean.")
        for field in ("previous_name", "resulting_name", "previous_description", "resulting_description"):
            if not isinstance(metadata[field], str):
                raise AuditEventError(f"Field '{field}' must be a string.")
        if metadata["name_changed"] != (metadata["previous_name"] != metadata["resulting_name"]):
            raise AuditEventError("Field 'name_changed' does not match whether name changed.")
        if metadata["description_changed"] != (metadata["previous_description"] != metadata["resulting_description"]):
            raise AuditEventError("Field 'description_changed' does not match whether description changed.")

    elif action == AuditAction.PLAN_VERSION_CREATED:
        expected_keys = {"plan_id", "plan_code", "version", "status"}
        if set(metadata.keys()) != expected_keys:
            raise AuditEventError(f"Invalid metadata keys for '{action}'. Expected: {expected_keys}")
        _validate_uuid_string(metadata["plan_id"], "plan_id")
        if not isinstance(metadata["plan_code"], str) or not metadata["plan_code"].strip():
            raise AuditEventError("Plan version 'plan_code' must be a non-empty string.")
        if type(metadata["version"]) is not int or metadata["version"] <= 0:
            raise AuditEventError("Plan version 'version' must be a positive integer.")
        if metadata["status"] != "draft":
            raise AuditEventError("Plan version creation 'status' must be 'draft'.")

    elif action == AuditAction.PLAN_VERSION_UPDATED:
        expected_keys = {
            "plan_id",
            "plan_code",
            "plan_version_id",
            "version",
            "change_summary_changed",
            "previous_change_summary",
            "resulting_change_summary",
        }
        if set(metadata.keys()) != expected_keys:
            raise AuditEventError(f"Invalid metadata keys for '{action}'. Expected: {expected_keys}")
        _validate_uuid_string(metadata["plan_id"], "plan_id")
        _validate_uuid_string(metadata["plan_version_id"], "plan_version_id")
        if not isinstance(metadata["plan_code"], str) or not metadata["plan_code"].strip():
            raise AuditEventError("Plan version 'plan_code' must be a non-empty string.")
        if type(metadata["version"]) is not int or metadata["version"] <= 0:
            raise AuditEventError("Plan version 'version' must be a positive integer.")
        if type(metadata["change_summary_changed"]) is not bool:
            raise AuditEventError("Field 'change_summary_changed' must be a boolean.")
        for field in ("previous_change_summary", "resulting_change_summary"):
            if not isinstance(metadata[field], str):
                raise AuditEventError(f"Field '{field}' must be a string.")
        if metadata["change_summary_changed"] != (metadata["previous_change_summary"] != metadata["resulting_change_summary"]):
            raise AuditEventError("Field 'change_summary_changed' does not match whether change_summary changed.")

    elif action == AuditAction.PLAN_VERSION_CLONED:
        expected_keys = {
            "source_plan_version_id",
            "source_version",
            "resulting_plan_version_id",
            "resulting_version",
            "copied_prices_count",
            "copied_products_count",
            "copied_modules_count",
            "copied_capabilities_count",
            "copied_quotas_count",
            "resulting_catalog_health",
        }
        if set(metadata.keys()) != expected_keys:
            raise AuditEventError(f"Invalid metadata keys for '{action}'. Expected: {expected_keys}")
        _validate_uuid_string(metadata["source_plan_version_id"], "source_plan_version_id")
        _validate_uuid_string(metadata["resulting_plan_version_id"], "resulting_plan_version_id")
        for vkey in ("source_version", "resulting_version"):
            if type(metadata[vkey]) is not int or metadata[vkey] <= 0:
                raise AuditEventError(f"Field '{vkey}' must be a positive integer.")
        for count_key in (
            "copied_prices_count",
            "copied_products_count",
            "copied_modules_count",
            "copied_capabilities_count",
            "copied_quotas_count",
        ):
            if type(metadata[count_key]) is not int or metadata[count_key] < 0:
                raise AuditEventError(f"Field '{count_key}' must be a non-negative integer.")
        if metadata["resulting_catalog_health"] not in ("healthy", "degraded"):
            raise AuditEventError(
                f"Field 'resulting_catalog_health' must be 'healthy' or 'degraded', got '{metadata['resulting_catalog_health']}'."
            )

    elif action == AuditAction.PLAN_VERSION_ACTIVATED:
        expected_keys = {
            "plan_id",
            "plan_code",
            "version",
            "previous_status",
            "resulting_status",
            "superseded_version_id",
            "superseded_version",
        }
        if set(metadata.keys()) != expected_keys:
            raise AuditEventError(f"Invalid metadata keys for '{action}'. Expected: {expected_keys}")
        _validate_uuid_string(metadata["plan_id"], "plan_id")
        if not isinstance(metadata["plan_code"], str) or not metadata["plan_code"].strip():
            raise AuditEventError("Field 'plan_code' must be a non-empty string.")
        if type(metadata["version"]) is not int or metadata["version"] <= 0:
            raise AuditEventError("Field 'version' must be a positive integer.")
        if metadata["previous_status"] != "draft":
            raise AuditEventError("Field 'previous_status' for plan activation must be 'draft'.")
        if metadata["resulting_status"] != "active":
            raise AuditEventError("Field 'resulting_status' for plan activation must be 'active'.")
        sup_id = metadata["superseded_version_id"]
        sup_ver = metadata["superseded_version"]
        if sup_id is not None:
            _validate_uuid_string(sup_id, "superseded_version_id")
            if type(sup_ver) is not int or sup_ver <= 0:
                raise AuditEventError("Field 'superseded_version' must be a positive integer when superseded_version_id is set.")
        else:
            if sup_ver is not None:
                raise AuditEventError("Field 'superseded_version' must be None when superseded_version_id is None.")

    elif action == AuditAction.PLAN_VERSION_RETIRED:
        expected_keys = {
            "plan_id",
            "plan_code",
            "version",
            "previous_status",
            "resulting_status",
            "retirement_reason",
            "superseded_by_plan_version_id",
            "superseded_by_version",
        }
        if set(metadata.keys()) != expected_keys:
            raise AuditEventError(f"Invalid metadata keys for '{action}'. Expected: {expected_keys}")
        _validate_uuid_string(metadata["plan_id"], "plan_id")
        if not isinstance(metadata["plan_code"], str) or not metadata["plan_code"].strip():
            raise AuditEventError("Field 'plan_code' must be a non-empty string.")
        if type(metadata["version"]) is not int or metadata["version"] <= 0:
            raise AuditEventError("Field 'version' must be a positive integer.")
        if metadata["previous_status"] not in ("draft", "active"):
            raise AuditEventError(f"Invalid 'previous_status' for plan version retirement: '{metadata['previous_status']}'.")
        if metadata["resulting_status"] != "retired":
            raise AuditEventError("Field 'resulting_status' for plan version retirement must be 'retired'.")
        reason = metadata["retirement_reason"]
        if reason not in ("superseded", "manual"):
            raise AuditEventError(f"Field 'retirement_reason' must be 'superseded' or 'manual', got '{reason}'.")
        sup_by_id = metadata["superseded_by_plan_version_id"]
        sup_by_ver = metadata["superseded_by_version"]
        if reason == "superseded":
            _validate_uuid_string(sup_by_id, "superseded_by_plan_version_id")
            if type(sup_by_ver) is not int or sup_by_ver <= 0:
                raise AuditEventError("Field 'superseded_by_version' must be a positive integer when superseded.")
        else:
            if sup_by_id is not None or sup_by_ver is not None:
                raise AuditEventError(
                    "Fields 'superseded_by_plan_version_id' and 'superseded_by_version' must be None for manual retirement."
                )

    elif action == AuditAction.PLAN_PRICE_CREATED:
        expected_keys = {"plan_id", "plan_version_id", "currency", "billing_interval", "amount"}
        if set(metadata.keys()) != expected_keys:
            raise AuditEventError(f"Invalid metadata keys for '{action}'. Expected: {expected_keys}")
        _validate_uuid_string(metadata["plan_id"], "plan_id")
        _validate_uuid_string(metadata["plan_version_id"], "plan_version_id")
        if metadata["currency"] not in ("INR", "USD", "EUR", "GBP"):
            raise AuditEventError(f"Invalid currency '{metadata['currency']}'.")
        if metadata["billing_interval"] not in ("monthly", "quarterly", "annual"):
            raise AuditEventError(f"Invalid billing_interval '{metadata['billing_interval']}'.")
        _validate_canonical_money(metadata["amount"], "amount")

    elif action == AuditAction.PLAN_PRICE_UPDATED:
        expected_keys = {"plan_id", "plan_version_id", "currency", "billing_interval", "previous_amount", "resulting_amount"}
        if set(metadata.keys()) != expected_keys:
            raise AuditEventError(f"Invalid metadata keys for '{action}'. Expected: {expected_keys}")
        _validate_uuid_string(metadata["plan_id"], "plan_id")
        _validate_uuid_string(metadata["plan_version_id"], "plan_version_id")
        if metadata["currency"] not in ("INR", "USD", "EUR", "GBP"):
            raise AuditEventError(f"Invalid currency '{metadata['currency']}'.")
        if metadata["billing_interval"] not in ("monthly", "quarterly", "annual"):
            raise AuditEventError(f"Invalid billing_interval '{metadata['billing_interval']}'.")
        _validate_canonical_money(metadata["previous_amount"], "previous_amount")
        _validate_canonical_money(metadata["resulting_amount"], "resulting_amount")

    elif action == AuditAction.PLAN_PRICE_REMOVED:
        expected_keys = {"plan_id", "plan_version_id", "currency", "billing_interval", "amount"}
        if set(metadata.keys()) != expected_keys:
            raise AuditEventError(f"Invalid metadata keys for '{action}'. Expected: {expected_keys}")
        _validate_uuid_string(metadata["plan_id"], "plan_id")
        _validate_uuid_string(metadata["plan_version_id"], "plan_version_id")
        if metadata["currency"] not in ("INR", "USD", "EUR", "GBP"):
            raise AuditEventError(f"Invalid currency '{metadata['currency']}'.")
        if metadata["billing_interval"] not in ("monthly", "quarterly", "annual"):
            raise AuditEventError(f"Invalid billing_interval '{metadata['billing_interval']}'.")
        _validate_canonical_money(metadata["amount"], "amount")

    elif action == AuditAction.PLAN_PRODUCT_ADDED:
        expected_keys = {"plan_id", "plan_version_id", "product_id", "product_code"}
        if set(metadata.keys()) != expected_keys:
            raise AuditEventError(f"Invalid metadata keys for '{action}'. Expected: {expected_keys}")
        _validate_uuid_string(metadata["plan_id"], "plan_id")
        _validate_uuid_string(metadata["plan_version_id"], "plan_version_id")
        _validate_uuid_string(metadata["product_id"], "product_id")
        if not isinstance(metadata["product_code"], str) or not metadata["product_code"].strip():
            raise AuditEventError("Field 'product_code' must be a non-empty string.")

    elif action == AuditAction.PLAN_PRODUCT_REMOVED:
        expected_keys = {
            "plan_id",
            "plan_version_id",
            "product_id",
            "product_code",
            "cascaded_modules_count",
            "cascaded_capabilities_count",
            "cascaded_quotas_count",
        }
        if set(metadata.keys()) != expected_keys:
            raise AuditEventError(f"Invalid metadata keys for '{action}'. Expected: {expected_keys}")
        _validate_uuid_string(metadata["plan_id"], "plan_id")
        _validate_uuid_string(metadata["plan_version_id"], "plan_version_id")
        _validate_uuid_string(metadata["product_id"], "product_id")
        if not isinstance(metadata["product_code"], str) or not metadata["product_code"].strip():
            raise AuditEventError("Field 'product_code' must be a non-empty string.")
        for count_key in ("cascaded_modules_count", "cascaded_capabilities_count", "cascaded_quotas_count"):
            if type(metadata[count_key]) is not int or metadata[count_key] < 0:
                raise AuditEventError(f"Field '{count_key}' must be a non-negative integer.")

    elif action == AuditAction.PLAN_MODULE_ADDED:
        expected_keys = {"plan_id", "plan_version_id", "product_id", "product_code", "module_id", "module_code"}
        if set(metadata.keys()) != expected_keys:
            raise AuditEventError(f"Invalid metadata keys for '{action}'. Expected: {expected_keys}")
        _validate_uuid_string(metadata["plan_id"], "plan_id")
        _validate_uuid_string(metadata["plan_version_id"], "plan_version_id")
        _validate_uuid_string(metadata["product_id"], "product_id")
        _validate_uuid_string(metadata["module_id"], "module_id")
        for code_key in ("product_code", "module_code"):
            if not isinstance(metadata[code_key], str) or not metadata[code_key].strip():
                raise AuditEventError(f"Field '{code_key}' must be a non-empty string.")

    elif action == AuditAction.PLAN_MODULE_REMOVED:
        expected_keys = {
            "plan_id",
            "plan_version_id",
            "product_id",
            "product_code",
            "module_id",
            "module_code",
            "cascaded_capabilities_count",
            "cascaded_quotas_count",
        }
        if set(metadata.keys()) != expected_keys:
            raise AuditEventError(f"Invalid metadata keys for '{action}'. Expected: {expected_keys}")
        _validate_uuid_string(metadata["plan_id"], "plan_id")
        _validate_uuid_string(metadata["plan_version_id"], "plan_version_id")
        _validate_uuid_string(metadata["product_id"], "product_id")
        _validate_uuid_string(metadata["module_id"], "module_id")
        for code_key in ("product_code", "module_code"):
            if not isinstance(metadata[code_key], str) or not metadata[code_key].strip():
                raise AuditEventError(f"Field '{code_key}' must be a non-empty string.")
        for count_key in ("cascaded_capabilities_count", "cascaded_quotas_count"):
            if type(metadata[count_key]) is not int or metadata[count_key] < 0:
                raise AuditEventError(f"Field '{count_key}' must be a non-negative integer.")

    elif action == AuditAction.PLAN_CAPABILITY_ADDED:
        expected_keys = {"plan_id", "plan_version_id", "product_id", "module_id", "feature_id", "capability_id", "capability_code"}
        if set(metadata.keys()) != expected_keys:
            raise AuditEventError(f"Invalid metadata keys for '{action}'. Expected: {expected_keys}")
        for uid_key in ("plan_id", "plan_version_id", "product_id", "module_id", "feature_id", "capability_id"):
            _validate_uuid_string(metadata[uid_key], uid_key)
        if not isinstance(metadata["capability_code"], str) or not metadata["capability_code"].strip():
            raise AuditEventError("Field 'capability_code' must be a non-empty string.")

    elif action == AuditAction.PLAN_CAPABILITY_REMOVED:
        expected_keys = {
            "plan_id",
            "plan_version_id",
            "product_id",
            "module_id",
            "feature_id",
            "capability_id",
            "capability_code",
            "cascaded_quotas_count",
        }
        if set(metadata.keys()) != expected_keys:
            raise AuditEventError(f"Invalid metadata keys for '{action}'. Expected: {expected_keys}")
        for uid_key in ("plan_id", "plan_version_id", "product_id", "module_id", "feature_id", "capability_id"):
            _validate_uuid_string(metadata[uid_key], uid_key)
        if not isinstance(metadata["capability_code"], str) or not metadata["capability_code"].strip():
            raise AuditEventError("Field 'capability_code' must be a non-empty string.")
        if type(metadata["cascaded_quotas_count"]) is not int or metadata["cascaded_quotas_count"] < 0:
            raise AuditEventError("Field 'cascaded_quotas_count' must be a non-negative integer.")

    elif action == AuditAction.PLAN_QUOTA_CREATED:
        expected_keys = {
            "plan_id",
            "plan_version_id",
            "scope",
            "target_id",
            "quota_key",
            "limit_type",
            "limit_value",
            "unit",
            "reset_period",
            "is_hard_limit",
        }
        if set(metadata.keys()) != expected_keys:
            raise AuditEventError(f"Invalid metadata keys for '{action}'. Expected: {expected_keys}")
        _validate_uuid_string(metadata["plan_id"], "plan_id")
        _validate_uuid_string(metadata["plan_version_id"], "plan_version_id")
        scope = metadata["scope"]
        if scope not in ("plan", "product", "module", "capability"):
            raise AuditEventError(f"Invalid scope '{scope}'.")
        target_id = metadata["target_id"]
        if scope == "plan":
            if target_id is not None:
                raise AuditEventError("Field 'target_id' must be None when scope is 'plan'.")
        else:
            _validate_uuid_string(target_id, "target_id")
        quota_key = metadata["quota_key"]
        if not isinstance(quota_key, str) or not re.match(r"^[a-z0-9]+(?:[-_][a-z0-9]+)*$", quota_key):
            raise AuditEventError("Field 'quota_key' has invalid format.")
        unit = metadata["unit"]
        if not isinstance(unit, str) or not re.match(r"^[a-z0-9_]+$", unit):
            raise AuditEventError("Field 'unit' has invalid format.")
        limit_type = metadata["limit_type"]
        _validate_canonical_quota_limit(limit_type, metadata["limit_value"])
        if metadata["reset_period"] not in ("never", "monthly", "annual"):
            raise AuditEventError(f"Invalid reset_period '{metadata['reset_period']}'.")
        if type(metadata["is_hard_limit"]) is not bool:
            raise AuditEventError("Field 'is_hard_limit' must be a boolean.")

    elif action == AuditAction.PLAN_QUOTA_UPDATED:
        expected_keys = {
            "plan_id",
            "plan_version_id",
            "scope",
            "target_id",
            "quota_key",
            "name_changed",
            "unit_changed",
            "limit_type_changed",
            "limit_value_changed",
            "is_hard_limit_changed",
            "reset_period_changed",
            "previous_name",
            "resulting_name",
            "previous_unit",
            "resulting_unit",
            "previous_limit_type",
            "resulting_limit_type",
            "previous_limit_value",
            "resulting_limit_value",
            "previous_is_hard_limit",
            "resulting_is_hard_limit",
            "previous_reset_period",
            "resulting_reset_period",
        }
        if set(metadata.keys()) != expected_keys:
            raise AuditEventError(f"Invalid metadata keys for '{action}'. Expected: {expected_keys}")
        _validate_uuid_string(metadata["plan_id"], "plan_id")
        _validate_uuid_string(metadata["plan_version_id"], "plan_version_id")
        scope = metadata["scope"]
        if scope not in ("plan", "product", "module", "capability"):
            raise AuditEventError(f"Invalid scope '{scope}'.")
        target_id = metadata["target_id"]
        if scope == "plan":
            if target_id is not None:
                raise AuditEventError("Field 'target_id' must be None when scope is 'plan'.")
        else:
            _validate_uuid_string(target_id, "target_id")
        if not isinstance(metadata["quota_key"], str) or not metadata["quota_key"].strip():
            raise AuditEventError("Field 'quota_key' must be a non-empty string.")
        for flag in (
            "name_changed",
            "unit_changed",
            "limit_type_changed",
            "limit_value_changed",
            "is_hard_limit_changed",
            "reset_period_changed",
        ):
            if type(metadata[flag]) is not bool:
                raise AuditEventError(f"Field '{flag}' must be a boolean.")
        for str_field in ("previous_name", "resulting_name", "previous_unit", "resulting_unit"):
            if not isinstance(metadata[str_field], str):
                raise AuditEventError(f"Field '{str_field}' must be a string.")
        for hl_field in ("previous_is_hard_limit", "resulting_is_hard_limit"):
            if type(metadata[hl_field]) is not bool:
                raise AuditEventError(f"Field '{hl_field}' must be a boolean.")
        for rp_field in ("previous_reset_period", "resulting_reset_period"):
            if metadata[rp_field] not in ("never", "monthly", "annual"):
                raise AuditEventError(f"Field '{rp_field}' must be in ('never', 'monthly', 'annual').")
        _validate_canonical_quota_limit(metadata["previous_limit_type"], metadata["previous_limit_value"], "previous_limit_value")
        _validate_canonical_quota_limit(metadata["resulting_limit_type"], metadata["resulting_limit_value"], "resulting_limit_value")
        if metadata["name_changed"] != (metadata["previous_name"] != metadata["resulting_name"]):
            raise AuditEventError("Field 'name_changed' does not match whether name changed.")
        if metadata["unit_changed"] != (metadata["previous_unit"] != metadata["resulting_unit"]):
            raise AuditEventError("Field 'unit_changed' does not match whether unit changed.")
        if metadata["limit_type_changed"] != (metadata["previous_limit_type"] != metadata["resulting_limit_type"]):
            raise AuditEventError("Field 'limit_type_changed' does not match whether limit_type changed.")
        if metadata["limit_value_changed"] != (metadata["previous_limit_value"] != metadata["resulting_limit_value"]):
            raise AuditEventError("Field 'limit_value_changed' does not match whether limit_value changed.")
        if metadata["is_hard_limit_changed"] != (metadata["previous_is_hard_limit"] != metadata["resulting_is_hard_limit"]):
            raise AuditEventError("Field 'is_hard_limit_changed' does not match whether is_hard_limit changed.")
        if metadata["reset_period_changed"] != (metadata["previous_reset_period"] != metadata["resulting_reset_period"]):
            raise AuditEventError("Field 'reset_period_changed' does not match whether reset_period changed.")

    elif action == AuditAction.PLAN_QUOTA_REMOVED:
        expected_keys = {"plan_id", "plan_version_id", "scope", "target_id", "quota_key", "limit_type", "limit_value"}
        if set(metadata.keys()) != expected_keys:
            raise AuditEventError(f"Invalid metadata keys for '{action}'. Expected: {expected_keys}")
        _validate_uuid_string(metadata["plan_id"], "plan_id")
        _validate_uuid_string(metadata["plan_version_id"], "plan_version_id")
        scope = metadata["scope"]
        if scope not in ("plan", "product", "module", "capability"):
            raise AuditEventError(f"Invalid scope '{scope}'.")
        target_id = metadata["target_id"]
        if scope == "plan":
            if target_id is not None:
                raise AuditEventError("Field 'target_id' must be None when scope is 'plan'.")
        else:
            _validate_uuid_string(target_id, "target_id")
        if not isinstance(metadata["quota_key"], str) or not metadata["quota_key"].strip():
            raise AuditEventError("Field 'quota_key' must be a non-empty string.")
        _validate_canonical_quota_limit(metadata["limit_type"], metadata["limit_value"])

    elif action == AuditAction.SUBSCRIPTION_CREATED:
        expected_keys = {"organization_code", "plan_code", "plan_version", "billing_interval", "currency", "amount", "status"}
        if set(metadata.keys()) != expected_keys:
            raise AuditEventError(f"Invalid metadata keys for '{action}'. Expected: {expected_keys}")
        if not isinstance(metadata["organization_code"], str) or not metadata["organization_code"].strip():
            raise AuditEventError("Field 'organization_code' must be a non-empty string.")
        if not isinstance(metadata["plan_code"], str) or not metadata["plan_code"].strip():
            raise AuditEventError("Field 'plan_code' must be a non-empty string.")
        if type(metadata["plan_version"]) is not int or metadata["plan_version"] <= 0:
            raise AuditEventError("Field 'plan_version' must be a positive integer.")
        if metadata["billing_interval"] not in ("monthly", "quarterly", "annual"):
            raise AuditEventError(f"Invalid billing_interval '{metadata['billing_interval']}'.")
        if metadata["currency"] not in ("INR", "USD", "EUR", "GBP"):
            raise AuditEventError(f"Invalid currency '{metadata['currency']}'.")
        _validate_canonical_money(metadata["amount"], "amount")
        if metadata["status"] != "active":
            raise AuditEventError("Field 'status' for direct subscription creation must be 'active'.")

    elif action == AuditAction.SUBSCRIPTION_TRIAL_STARTED:
        expected_keys = {"organization_code", "plan_code", "plan_version", "trial_days", "trial_ends_at", "status"}
        if set(metadata.keys()) != expected_keys:
            raise AuditEventError(f"Invalid metadata keys for '{action}'. Expected: {expected_keys}")
        if not isinstance(metadata["organization_code"], str) or not metadata["organization_code"].strip():
            raise AuditEventError("Field 'organization_code' must be a non-empty string.")
        if not isinstance(metadata["plan_code"], str) or not metadata["plan_code"].strip():
            raise AuditEventError("Field 'plan_code' must be a non-empty string.")
        if type(metadata["plan_version"]) is not int or metadata["plan_version"] <= 0:
            raise AuditEventError("Field 'plan_version' must be a positive integer.")
        if type(metadata["trial_days"]) is not int or metadata["trial_days"] <= 0:
            raise AuditEventError("Field 'trial_days' must be a positive integer.")
        if not isinstance(metadata["trial_ends_at"], str) or not metadata["trial_ends_at"].strip():
            raise AuditEventError("Field 'trial_ends_at' must be a non-empty string.")
        if metadata["status"] != "trialing":
            raise AuditEventError("Field 'status' for trial start must be 'trialing'.")

    elif action == AuditAction.SUBSCRIPTION_TRIAL_CONVERTED:
        expected_keys = {"organization_code", "plan_code", "plan_version", "billing_interval", "currency", "amount", "previous_status", "resulting_status"}
        if set(metadata.keys()) != expected_keys:
            raise AuditEventError(f"Invalid metadata keys for '{action}'. Expected: {expected_keys}")
        if not isinstance(metadata["organization_code"], str) or not metadata["organization_code"].strip():
            raise AuditEventError("Field 'organization_code' must be a non-empty string.")
        if not isinstance(metadata["plan_code"], str) or not metadata["plan_code"].strip():
            raise AuditEventError("Field 'plan_code' must be a non-empty string.")
        if type(metadata["plan_version"]) is not int or metadata["plan_version"] <= 0:
            raise AuditEventError("Field 'plan_version' must be a positive integer.")
        if metadata["billing_interval"] not in ("monthly", "quarterly", "annual"):
            raise AuditEventError(f"Invalid billing_interval '{metadata['billing_interval']}'.")
        if metadata["currency"] not in ("INR", "USD", "EUR", "GBP"):
            raise AuditEventError(f"Invalid currency '{metadata['currency']}'.")
        _validate_canonical_money(metadata["amount"], "amount")
        if metadata["previous_status"] != "trialing":
            raise AuditEventError("Field 'previous_status' for trial conversion must be 'trialing'.")
        if metadata["resulting_status"] != "active":
            raise AuditEventError("Field 'resulting_status' for trial conversion must be 'active'.")

    elif action == AuditAction.SUBSCRIPTION_TRIAL_EXPIRED:
        expected_keys = {"organization_code", "plan_code", "plan_version", "previous_status", "resulting_status"}
        if set(metadata.keys()) != expected_keys:
            raise AuditEventError(f"Invalid metadata keys for '{action}'. Expected: {expected_keys}")
        if not isinstance(metadata["organization_code"], str) or not metadata["organization_code"].strip():
            raise AuditEventError("Field 'organization_code' must be a non-empty string.")
        if not isinstance(metadata["plan_code"], str) or not metadata["plan_code"].strip():
            raise AuditEventError("Field 'plan_code' must be a non-empty string.")
        if type(metadata["plan_version"]) is not int or metadata["plan_version"] <= 0:
            raise AuditEventError("Field 'plan_version' must be a positive integer.")
        if metadata["previous_status"] != "trialing":
            raise AuditEventError("Field 'previous_status' for trial expiration must be 'trialing'.")
        if metadata["resulting_status"] != "expired":
            raise AuditEventError("Field 'resulting_status' for trial expiration must be 'expired'.")

    elif action == AuditAction.SUBSCRIPTION_PLAN_CHANGED:
        expected_keys = {"organization_code", "previous_plan_code", "previous_plan_version", "resulting_plan_code", "resulting_plan_version", "change_reason"}
        if set(metadata.keys()) != expected_keys:
            raise AuditEventError(f"Invalid metadata keys for '{action}'. Expected: {expected_keys}")
        if not isinstance(metadata["organization_code"], str) or not metadata["organization_code"].strip():
            raise AuditEventError("Field 'organization_code' must be a non-empty string.")
        if not isinstance(metadata["previous_plan_code"], str) or not metadata["previous_plan_code"].strip():
            raise AuditEventError("Field 'previous_plan_code' must be a non-empty string.")
        if not isinstance(metadata["resulting_plan_code"], str) or not metadata["resulting_plan_code"].strip():
            raise AuditEventError("Field 'resulting_plan_code' must be a non-empty string.")
        if type(metadata["previous_plan_version"]) is not int or metadata["previous_plan_version"] <= 0:
            raise AuditEventError("Field 'previous_plan_version' must be a positive integer.")
        if type(metadata["resulting_plan_version"]) is not int or metadata["resulting_plan_version"] <= 0:
            raise AuditEventError("Field 'resulting_plan_version' must be a positive integer.")
        if not isinstance(metadata["change_reason"], str):
            raise AuditEventError("Field 'change_reason' must be a string.")

    elif action == AuditAction.SUBSCRIPTION_SUSPENDED:
        expected_keys = {"organization_code", "plan_code", "plan_version", "suspension_reason", "previous_status", "resulting_status"}
        if set(metadata.keys()) != expected_keys:
            raise AuditEventError(f"Invalid metadata keys for '{action}'. Expected: {expected_keys}")
        if not isinstance(metadata["organization_code"], str) or not metadata["organization_code"].strip():
            raise AuditEventError("Field 'organization_code' must be a non-empty string.")
        if not isinstance(metadata["plan_code"], str) or not metadata["plan_code"].strip():
            raise AuditEventError("Field 'plan_code' must be a non-empty string.")
        if type(metadata["plan_version"]) is not int or metadata["plan_version"] <= 0:
            raise AuditEventError("Field 'plan_version' must be a positive integer.")
        if not isinstance(metadata["suspension_reason"], str):
            raise AuditEventError("Field 'suspension_reason' must be a string.")
        if metadata["previous_status"] != "active":
            raise AuditEventError("Field 'previous_status' for subscription suspension must be 'active'.")
        if metadata["resulting_status"] != "suspended":
            raise AuditEventError("Field 'resulting_status' for subscription suspension must be 'suspended'.")

    elif action == AuditAction.SUBSCRIPTION_REACTIVATED:
        expected_keys = {"organization_code", "plan_code", "plan_version", "previous_status", "resulting_status"}
        if set(metadata.keys()) != expected_keys:
            raise AuditEventError(f"Invalid metadata keys for '{action}'. Expected: {expected_keys}")
        if not isinstance(metadata["organization_code"], str) or not metadata["organization_code"].strip():
            raise AuditEventError("Field 'organization_code' must be a non-empty string.")
        if not isinstance(metadata["plan_code"], str) or not metadata["plan_code"].strip():
            raise AuditEventError("Field 'plan_code' must be a non-empty string.")
        if type(metadata["plan_version"]) is not int or metadata["plan_version"] <= 0:
            raise AuditEventError("Field 'plan_version' must be a positive integer.")
        if metadata["previous_status"] != "suspended":
            raise AuditEventError("Field 'previous_status' for subscription reactivation must be 'suspended'.")
        if metadata["resulting_status"] != "active":
            raise AuditEventError("Field 'resulting_status' for subscription reactivation must be 'active'.")

    elif action == AuditAction.SUBSCRIPTION_CANCELLED:
        expected_keys = {"organization_code", "plan_code", "plan_version", "cancellation_reason", "previous_status", "resulting_status"}
        if set(metadata.keys()) != expected_keys:
            raise AuditEventError(f"Invalid metadata keys for '{action}'. Expected: {expected_keys}")
        if not isinstance(metadata["organization_code"], str) or not metadata["organization_code"].strip():
            raise AuditEventError("Field 'organization_code' must be a non-empty string.")
        if not isinstance(metadata["plan_code"], str) or not metadata["plan_code"].strip():
            raise AuditEventError("Field 'plan_code' must be a non-empty string.")
        if type(metadata["plan_version"]) is not int or metadata["plan_version"] <= 0:
            raise AuditEventError("Field 'plan_version' must be a positive integer.")
        if not isinstance(metadata["cancellation_reason"], str):
            raise AuditEventError("Field 'cancellation_reason' must be a string.")
        if metadata["previous_status"] not in ("trialing", "active", "suspended"):
            raise AuditEventError(f"Invalid 'previous_status' for cancellation: '{metadata['previous_status']}'.")
        if metadata["resulting_status"] != "cancelled":
            raise AuditEventError("Field 'resulting_status' for subscription cancellation must be 'cancelled'.")

    elif action == AuditAction.SUBSCRIPTION_RECONCILED:
        expected_keys = {"organization_code", "repaired_count"}
        if set(metadata.keys()) != expected_keys:
            raise AuditEventError(f"Invalid metadata keys for '{action}'. Expected: {expected_keys}")
        if not isinstance(metadata["organization_code"], str) or not metadata["organization_code"].strip():
            raise AuditEventError("Field 'organization_code' must be a non-empty string.")
        if type(metadata["repaired_count"]) is not int or metadata["repaired_count"] <= 0:
            raise AuditEventError("Field 'repaired_count' must be a positive integer.")

    # Phase 2D User Actions
    elif action == AuditAction.USER_CREATED:
        expected_keys = {"email", "full_name", "status"}
        if set(metadata.keys()) != expected_keys:
            raise AuditEventError(f"Invalid metadata keys for '{action}'. Expected: {expected_keys}")
        if not isinstance(metadata["email"], str) or not metadata["email"].strip():
            raise AuditEventError("Field 'email' must be a non-empty string.")
        if not isinstance(metadata["full_name"], str):
            raise AuditEventError("Field 'full_name' must be a string.")
        if metadata["status"] != "active":
            raise AuditEventError("Field 'status' must be 'active'.")

    elif action == AuditAction.USER_UPDATED:
        expected_keys = {"email", "full_name"}
        if set(metadata.keys()) != expected_keys:
            raise AuditEventError(f"Invalid metadata keys for '{action}'. Expected: {expected_keys}")
        if not isinstance(metadata["email"], str) or not metadata["email"].strip():
            raise AuditEventError("Field 'email' must be a non-empty string.")
        if not isinstance(metadata["full_name"], str):
            raise AuditEventError("Field 'full_name' must be a string.")

    elif action == AuditAction.USER_SUSPENDED:
        if not {"email", "previous_status", "resulting_status"}.issubset(set(metadata.keys())):
            raise AuditEventError(f"Missing required metadata keys for '{action}'.")
        if set(metadata.keys()) - {"email", "previous_status", "resulting_status", "reason"}:
            raise AuditEventError(f"Invalid metadata keys for '{action}'.")
        if not isinstance(metadata["email"], str) or not metadata["email"].strip():
            raise AuditEventError("Field 'email' must be a non-empty string.")
        if metadata["previous_status"] != "active":
            raise AuditEventError("Field 'previous_status' must be 'active'.")
        if metadata["resulting_status"] != "suspended":
            raise AuditEventError("Field 'resulting_status' must be 'suspended'.")
        if "reason" in metadata and not isinstance(metadata["reason"], str):
            raise AuditEventError("Field 'reason' must be a string.")

    elif action == AuditAction.USER_REACTIVATED:
        expected_keys = {"email", "previous_status", "resulting_status"}
        if set(metadata.keys()) != expected_keys:
            raise AuditEventError(f"Invalid metadata keys for '{action}'. Expected: {expected_keys}")
        if not isinstance(metadata["email"], str) or not metadata["email"].strip():
            raise AuditEventError("Field 'email' must be a non-empty string.")
        if metadata["previous_status"] != "suspended":
            raise AuditEventError("Field 'previous_status' must be 'suspended'.")
        if metadata["resulting_status"] != "active":
            raise AuditEventError("Field 'resulting_status' must be 'active'.")

    elif action == AuditAction.USER_DISABLED:
        if not {"email", "previous_status", "resulting_status"}.issubset(set(metadata.keys())):
            raise AuditEventError(f"Missing required metadata keys for '{action}'.")
        if set(metadata.keys()) - {"email", "previous_status", "resulting_status", "reason"}:
            raise AuditEventError(f"Invalid metadata keys for '{action}'.")
        if not isinstance(metadata["email"], str) or not metadata["email"].strip():
            raise AuditEventError("Field 'email' must be a non-empty string.")
        if metadata["previous_status"] not in ("active", "suspended"):
            raise AuditEventError(f"Invalid 'previous_status' for '{action}': '{metadata['previous_status']}'.")
        if metadata["resulting_status"] != "disabled":
            raise AuditEventError("Field 'resulting_status' must be 'disabled'.")
        if "reason" in metadata and not isinstance(metadata["reason"], str):
            raise AuditEventError("Field 'reason' must be a string.")

    # Phase 2D Membership Actions
    elif action == AuditAction.MEMBERSHIP_CREATED:
        expected_keys = {"organization_code", "user_email", "membership_type", "status"}
        if set(metadata.keys()) != expected_keys:
            raise AuditEventError(f"Invalid metadata keys for '{action}'. Expected: {expected_keys}")
        if not isinstance(metadata["organization_code"], str) or not metadata["organization_code"].strip():
            raise AuditEventError("Field 'organization_code' must be a non-empty string.")
        if not isinstance(metadata["user_email"], str) or not metadata["user_email"].strip():
            raise AuditEventError("Field 'user_email' must be a non-empty string.")
        if metadata["membership_type"] not in ("tenant_admin", "member"):
            raise AuditEventError(f"Invalid 'membership_type': '{metadata['membership_type']}'.")
        if metadata["status"] != "active":
            raise AuditEventError("Field 'status' must be 'active'.")

    elif action == AuditAction.MEMBERSHIP_UPDATED:
        expected_keys = {"organization_code", "user_email", "previous_membership_type", "resulting_membership_type"}
        if set(metadata.keys()) != expected_keys:
            raise AuditEventError(f"Invalid metadata keys for '{action}'. Expected: {expected_keys}")
        if not isinstance(metadata["organization_code"], str) or not metadata["organization_code"].strip():
            raise AuditEventError("Field 'organization_code' must be a non-empty string.")
        if not isinstance(metadata["user_email"], str) or not metadata["user_email"].strip():
            raise AuditEventError("Field 'user_email' must be a non-empty string.")
        if metadata["previous_membership_type"] not in ("tenant_admin", "member"):
            raise AuditEventError(f"Invalid 'previous_membership_type': '{metadata['previous_membership_type']}'.")
        if metadata["resulting_membership_type"] not in ("tenant_admin", "member"):
            raise AuditEventError(f"Invalid 'resulting_membership_type': '{metadata['resulting_membership_type']}'.")

    elif action == AuditAction.MEMBERSHIP_SUSPENDED:
        if not {"organization_code", "user_email", "previous_status", "resulting_status"}.issubset(set(metadata.keys())):
            raise AuditEventError(f"Missing required metadata keys for '{action}'.")
        if set(metadata.keys()) - {"organization_code", "user_email", "previous_status", "resulting_status", "reason"}:
            raise AuditEventError(f"Invalid metadata keys for '{action}'.")
        if not isinstance(metadata["organization_code"], str) or not metadata["organization_code"].strip():
            raise AuditEventError("Field 'organization_code' must be a non-empty string.")
        if not isinstance(metadata["user_email"], str) or not metadata["user_email"].strip():
            raise AuditEventError("Field 'user_email' must be a non-empty string.")
        if metadata["previous_status"] != "active":
            raise AuditEventError("Field 'previous_status' must be 'active'.")
        if metadata["resulting_status"] != "suspended":
            raise AuditEventError("Field 'resulting_status' must be 'suspended'.")
        if "reason" in metadata and not isinstance(metadata["reason"], str):
            raise AuditEventError("Field 'reason' must be a string.")

    elif action == AuditAction.MEMBERSHIP_REACTIVATED:
        expected_keys = {"organization_code", "user_email", "previous_status", "resulting_status"}
        if set(metadata.keys()) != expected_keys:
            raise AuditEventError(f"Invalid metadata keys for '{action}'. Expected: {expected_keys}")
        if not isinstance(metadata["organization_code"], str) or not metadata["organization_code"].strip():
            raise AuditEventError("Field 'organization_code' must be a non-empty string.")
        if not isinstance(metadata["user_email"], str) or not metadata["user_email"].strip():
            raise AuditEventError("Field 'user_email' must be a non-empty string.")
        if metadata["previous_status"] != "suspended":
            raise AuditEventError("Field 'previous_status' must be 'suspended'.")
        if metadata["resulting_status"] != "active":
            raise AuditEventError("Field 'resulting_status' must be 'active'.")

    elif action == AuditAction.MEMBERSHIP_ENDED:
        if not {"organization_code", "user_email", "previous_status", "resulting_status", "ended_at"}.issubset(set(metadata.keys())):
            raise AuditEventError(f"Missing required metadata keys for '{action}'.")
        if set(metadata.keys()) - {"organization_code", "user_email", "previous_status", "resulting_status", "ended_at", "reason"}:
            raise AuditEventError(f"Invalid metadata keys for '{action}'.")
        if not isinstance(metadata["organization_code"], str) or not metadata["organization_code"].strip():
            raise AuditEventError("Field 'organization_code' must be a non-empty string.")
        if not isinstance(metadata["user_email"], str) or not metadata["user_email"].strip():
            raise AuditEventError("Field 'user_email' must be a non-empty string.")
        if metadata["previous_status"] not in ("active", "suspended"):
            raise AuditEventError(f"Invalid 'previous_status': '{metadata['previous_status']}'.")
        if metadata["resulting_status"] != "ended":
            raise AuditEventError("Field 'resulting_status' must be 'ended'.")
        if not isinstance(metadata["ended_at"], str) or not metadata["ended_at"].strip():
            raise AuditEventError("Field 'ended_at' must be a non-empty string.")
        if "reason" in metadata and not isinstance(metadata["reason"], str):
            raise AuditEventError("Field 'reason' must be a string.")

    elif action == AuditAction.MEMBERSHIP_RESTORED:
        expected_keys = {"organization_code", "user_email", "prior_joined_at", "prior_ended_at", "new_joined_at", "membership_type"}
        if set(metadata.keys()) != expected_keys:
            raise AuditEventError(f"Invalid metadata keys for '{action}'. Expected: {expected_keys}")
        if not isinstance(metadata["organization_code"], str) or not metadata["organization_code"].strip():
            raise AuditEventError("Field 'organization_code' must be a non-empty string.")
        if not isinstance(metadata["user_email"], str) or not metadata["user_email"].strip():
            raise AuditEventError("Field 'user_email' must be a non-empty string.")
        if not isinstance(metadata["prior_joined_at"], str) or not metadata["prior_joined_at"].strip():
            raise AuditEventError("Field 'prior_joined_at' must be a non-empty string.")
        if not isinstance(metadata["prior_ended_at"], str) or not metadata["prior_ended_at"].strip():
            raise AuditEventError("Field 'prior_ended_at' must be a non-empty string.")
        if not isinstance(metadata["new_joined_at"], str) or not metadata["new_joined_at"].strip():
            raise AuditEventError("Field 'new_joined_at' must be a non-empty string.")
        if metadata["membership_type"] not in ("tenant_admin", "member"):
            raise AuditEventError(f"Invalid 'membership_type': '{metadata['membership_type']}'.")

    # Phase 2E Access Control Actions
    elif action == AuditAction.ROLE_CREATED:
        expected_keys = {"organization_id", "role_code", "role_name", "permission_keys"}
        if set(metadata.keys()) != expected_keys:
            raise AuditEventError(f"Invalid metadata keys for '{action}'. Expected: {expected_keys}")
        _validate_uuid_string(metadata["organization_id"], "organization_id")
        if not isinstance(metadata["role_code"], str) or not metadata["role_code"].strip():
            raise AuditEventError("Field 'role_code' must be a non-empty string.")
        if not isinstance(metadata["role_name"], str) or not metadata["role_name"].strip():
            raise AuditEventError("Field 'role_name' must be a non-empty string.")
        if not isinstance(metadata["permission_keys"], list):
            raise AuditEventError("Field 'permission_keys' must be a list of strings.")
        for pk in metadata["permission_keys"]:
            if not isinstance(pk, str) or not pk.strip():
                raise AuditEventError("Items in 'permission_keys' must be non-empty strings.")
        if metadata["permission_keys"] != sorted(metadata["permission_keys"]):
            raise AuditEventError("Field 'permission_keys' must be deterministically sorted.")

    elif action == AuditAction.ROLE_UPDATED:
        expected_keys = {"organization_id", "role_code", "name_changed", "description_changed"}
        if set(metadata.keys()) != expected_keys:
            raise AuditEventError(f"Invalid metadata keys for '{action}'. Expected: {expected_keys}")
        _validate_uuid_string(metadata["organization_id"], "organization_id")
        if not isinstance(metadata["role_code"], str) or not metadata["role_code"].strip():
            raise AuditEventError("Field 'role_code' must be a non-empty string.")
        if not isinstance(metadata["name_changed"], bool):
            raise AuditEventError("Field 'name_changed' must be a boolean.")
        if not isinstance(metadata["description_changed"], bool):
            raise AuditEventError("Field 'description_changed' must be a boolean.")

    elif action == AuditAction.ROLE_PERMISSIONS_CHANGED:
        expected_keys = {"organization_id", "role_code", "added_permission_keys", "removed_permission_keys"}
        if set(metadata.keys()) != expected_keys:
            raise AuditEventError(f"Invalid metadata keys for '{action}'. Expected: {expected_keys}")
        _validate_uuid_string(metadata["organization_id"], "organization_id")
        if not isinstance(metadata["role_code"], str) or not metadata["role_code"].strip():
            raise AuditEventError("Field 'role_code' must be a non-empty string.")
        for field_name in ("added_permission_keys", "removed_permission_keys"):
            if not isinstance(metadata[field_name], list):
                raise AuditEventError(f"Field '{field_name}' must be a list of strings.")
            for pk in metadata[field_name]:
                if not isinstance(pk, str) or not pk.strip():
                    raise AuditEventError(f"Items in '{field_name}' must be non-empty strings.")
            if metadata[field_name] != sorted(metadata[field_name]):
                raise AuditEventError(f"Field '{field_name}' must be deterministically sorted.")

    elif action == AuditAction.ROLE_RETIRED:
        expected_keys = {"organization_id", "role_code"}
        if set(metadata.keys()) != expected_keys:
            raise AuditEventError(f"Invalid metadata keys for '{action}'. Expected: {expected_keys}")
        _validate_uuid_string(metadata["organization_id"], "organization_id")
        if not isinstance(metadata["role_code"], str) or not metadata["role_code"].strip():
            raise AuditEventError("Field 'role_code' must be a non-empty string.")

    elif action == AuditAction.MEMBERSHIP_ROLE_ASSIGNED:
        expected_keys = {
            "organization_id",
            "membership_id",
            "previous_role_id",
            "previous_role_code",
            "resulting_role_id",
            "resulting_role_code",
        }
        if set(metadata.keys()) != expected_keys:
            raise AuditEventError(f"Invalid metadata keys for '{action}'. Expected: {expected_keys}")
        _validate_uuid_string(metadata["organization_id"], "organization_id")
        _validate_uuid_string(metadata["membership_id"], "membership_id")
        _validate_uuid_string(metadata["previous_role_id"], "previous_role_id")
        if not isinstance(metadata["previous_role_code"], str) or not metadata["previous_role_code"].strip():
            raise AuditEventError("Field 'previous_role_code' must be a non-empty string.")
        _validate_uuid_string(metadata["resulting_role_id"], "resulting_role_id")
        if not isinstance(metadata["resulting_role_code"], str) or not metadata["resulting_role_code"].strip():
            raise AuditEventError("Field 'resulting_role_code' must be a non-empty string.")

    elif action == AuditAction.CONSOLE_MODULE_POLICY_CHANGED:
        expected_keys = {"organization_id", "module_key", "previous_is_enabled", "resulting_is_enabled"}
        if set(metadata.keys()) != expected_keys:
            raise AuditEventError(f"Invalid metadata keys for '{action}'. Expected: {expected_keys}")
        _validate_uuid_string(metadata["organization_id"], "organization_id")
        if not isinstance(metadata["module_key"], str) or not metadata["module_key"].strip():
            raise AuditEventError("Field 'module_key' must be a non-empty string.")
        if not isinstance(metadata["previous_is_enabled"], bool):
            raise AuditEventError("Field 'previous_is_enabled' must be a boolean.")
        if not isinstance(metadata["resulting_is_enabled"], bool):
            raise AuditEventError("Field 'resulting_is_enabled' must be a boolean.")

    elif action == AuditAction.PERMISSION_CEILING_CHANGED:
        expected_keys = {"organization_id", "permission_key", "previous_is_allowed", "resulting_is_allowed"}
        if set(metadata.keys()) != expected_keys:
            raise AuditEventError(f"Invalid metadata keys for '{action}'. Expected: {expected_keys}")
        _validate_uuid_string(metadata["organization_id"], "organization_id")
        if not isinstance(metadata["permission_key"], str) or not metadata["permission_key"].strip():
            raise AuditEventError("Field 'permission_key' must be a non-empty string.")
        if not isinstance(metadata["previous_is_allowed"], bool):
            raise AuditEventError("Field 'previous_is_allowed' must be a boolean.")
        if not isinstance(metadata["resulting_is_allowed"], bool):
            raise AuditEventError("Field 'resulting_is_allowed' must be a boolean.")

    # Phase 2F Assignment Domain Actions
    elif action == AuditAction.USER_PRODUCT_ASSIGNED:
        expected_keys = {
            "organization_code",
            "user_id",
            "user_email",
            "product_id",
            "product_code",
            "subscription_id",
            "pool_scope",
            "pool_key",
            "governed_product_ids",
            "quota_entitlement_id",
            "quota_key",
            "total_limit",
            "consumed_seats_after",
            "available_seats_after",
            "assigned_module_ids",
            "assigned_module_codes",
        }
        if set(metadata.keys()) != expected_keys:
            raise AuditEventError(f"Invalid metadata keys for '{action}'. Expected: {expected_keys}")
        if not isinstance(metadata["organization_code"], str) or not metadata["organization_code"].strip():
            raise AuditEventError("Field 'organization_code' must be a non-empty string.")
        _validate_uuid_string(metadata["user_id"], "user_id")
        if not isinstance(metadata["user_email"], str) or not metadata["user_email"].strip():
            raise AuditEventError("Field 'user_email' must be a non-empty string.")
        _validate_uuid_string(metadata["product_id"], "product_id")
        if not isinstance(metadata["product_code"], str) or not metadata["product_code"].strip():
            raise AuditEventError("Field 'product_code' must be a non-empty string.")
        _validate_uuid_string(metadata["subscription_id"], "subscription_id")
        if metadata["pool_scope"] not in ("product", "plan"):
            raise AuditEventError("Field 'pool_scope' must be 'product' or 'plan'.")
        if not isinstance(metadata["pool_key"], str) or not metadata["pool_key"].strip():
            raise AuditEventError("Field 'pool_key' must be a non-empty string.")
        if not isinstance(metadata["governed_product_ids"], list):
            raise AuditEventError("Field 'governed_product_ids' must be a list.")
        for pid in metadata["governed_product_ids"]:
            _validate_uuid_string(pid, "governed_product_ids item")
        if metadata["governed_product_ids"] != sorted(metadata["governed_product_ids"]):
            raise AuditEventError("Field 'governed_product_ids' must be deterministically sorted.")
        _validate_uuid_string(metadata["quota_entitlement_id"], "quota_entitlement_id")
        if metadata["quota_key"] not in ("seats", "max_seats"):
            raise AuditEventError("Field 'quota_key' must be 'seats' or 'max_seats'.")
        if metadata["total_limit"] is not None and (not isinstance(metadata["total_limit"], int) or metadata["total_limit"] < 0):
            raise AuditEventError("Field 'total_limit' must be a non-negative integer or None.")
        if not isinstance(metadata["consumed_seats_after"], int) or metadata["consumed_seats_after"] < 0:
            raise AuditEventError("Field 'consumed_seats_after' must be a non-negative integer.")
        if metadata["available_seats_after"] is not None and (not isinstance(metadata["available_seats_after"], int) or metadata["available_seats_after"] < 0):
            raise AuditEventError("Field 'available_seats_after' must be a non-negative integer or None.")
        if not isinstance(metadata["assigned_module_ids"], list):
            raise AuditEventError("Field 'assigned_module_ids' must be a list.")
        for mid in metadata["assigned_module_ids"]:
            _validate_uuid_string(mid, "assigned_module_ids item")
        if metadata["assigned_module_ids"] != sorted(metadata["assigned_module_ids"]):
            raise AuditEventError("Field 'assigned_module_ids' must be deterministically sorted.")
        if not isinstance(metadata["assigned_module_codes"], list):
            raise AuditEventError("Field 'assigned_module_codes' must be a list.")
        for mc in metadata["assigned_module_codes"]:
            if not isinstance(mc, str) or not mc.strip():
                raise AuditEventError("Items in 'assigned_module_codes' must be non-empty strings.")
        if metadata["assigned_module_codes"] != sorted(metadata["assigned_module_codes"]):
            raise AuditEventError("Field 'assigned_module_codes' must be deterministically sorted.")

    elif action == AuditAction.USER_PRODUCT_SUSPENDED:
        expected_keys = {
            "organization_code",
            "user_id",
            "user_email",
            "product_id",
            "product_code",
            "previous_status",
            "resulting_status",
            "suspension_reason",
        }
        if set(metadata.keys()) != expected_keys:
            raise AuditEventError(f"Invalid metadata keys for '{action}'. Expected: {expected_keys}")
        if not isinstance(metadata["organization_code"], str) or not metadata["organization_code"].strip():
            raise AuditEventError("Field 'organization_code' must be a non-empty string.")
        _validate_uuid_string(metadata["user_id"], "user_id")
        if not isinstance(metadata["user_email"], str) or not metadata["user_email"].strip():
            raise AuditEventError("Field 'user_email' must be a non-empty string.")
        _validate_uuid_string(metadata["product_id"], "product_id")
        if not isinstance(metadata["product_code"], str) or not metadata["product_code"].strip():
            raise AuditEventError("Field 'product_code' must be a non-empty string.")
        if metadata["previous_status"] != "active":
            raise AuditEventError("Field 'previous_status' must be 'active'.")
        if metadata["resulting_status"] != "suspended":
            raise AuditEventError("Field 'resulting_status' must be 'suspended'.")
        if not isinstance(metadata["suspension_reason"], str) or not metadata["suspension_reason"].strip():
            raise AuditEventError("Field 'suspension_reason' must be a non-empty string.")

    elif action == AuditAction.USER_PRODUCT_REACTIVATED:
        expected_keys = {
            "organization_code",
            "user_id",
            "user_email",
            "product_id",
            "product_code",
            "previous_status",
            "resulting_status",
        }
        if set(metadata.keys()) != expected_keys:
            raise AuditEventError(f"Invalid metadata keys for '{action}'. Expected: {expected_keys}")
        if not isinstance(metadata["organization_code"], str) or not metadata["organization_code"].strip():
            raise AuditEventError("Field 'organization_code' must be a non-empty string.")
        _validate_uuid_string(metadata["user_id"], "user_id")
        if not isinstance(metadata["user_email"], str) or not metadata["user_email"].strip():
            raise AuditEventError("Field 'user_email' must be a non-empty string.")
        _validate_uuid_string(metadata["product_id"], "product_id")
        if not isinstance(metadata["product_code"], str) or not metadata["product_code"].strip():
            raise AuditEventError("Field 'product_code' must be a non-empty string.")
        if metadata["previous_status"] != "suspended":
            raise AuditEventError("Field 'previous_status' must be 'suspended'.")
        if metadata["resulting_status"] != "active":
            raise AuditEventError("Field 'resulting_status' must be 'active'.")

    elif action == AuditAction.USER_PRODUCT_REVOKED:
        expected_keys = {
            "organization_code",
            "user_id",
            "user_email",
            "product_id",
            "product_code",
            "previous_status",
            "resulting_status",
            "reason",
            "seat_reservation_released",
            "was_counted_in_current_pool",
            "current_pool_consumed_delta",
        }
        if set(metadata.keys()) != expected_keys:
            raise AuditEventError(f"Invalid metadata keys for '{action}'. Expected: {expected_keys}")
        if not isinstance(metadata["organization_code"], str) or not metadata["organization_code"].strip():
            raise AuditEventError("Field 'organization_code' must be a non-empty string.")
        _validate_uuid_string(metadata["user_id"], "user_id")
        if not isinstance(metadata["user_email"], str) or not metadata["user_email"].strip():
            raise AuditEventError("Field 'user_email' must be a non-empty string.")
        _validate_uuid_string(metadata["product_id"], "product_id")
        if not isinstance(metadata["product_code"], str) or not metadata["product_code"].strip():
            raise AuditEventError("Field 'product_code' must be a non-empty string.")
        if metadata["previous_status"] not in ("active", "suspended"):
            raise AuditEventError("Field 'previous_status' must be 'active' or 'suspended'.")
        if metadata["resulting_status"] != "revoked":
            raise AuditEventError("Field 'resulting_status' must be 'revoked'.")
        if not isinstance(metadata["reason"], str) or not metadata["reason"].strip():
            raise AuditEventError("Field 'reason' must be a non-empty string.")
        if metadata["seat_reservation_released"] is not True:
            raise AuditEventError("Field 'seat_reservation_released' must be True.")
        if not isinstance(metadata["was_counted_in_current_pool"], bool):
            raise AuditEventError("Field 'was_counted_in_current_pool' must be a boolean.")
        if metadata["current_pool_consumed_delta"] not in (0, -1):
            raise AuditEventError("Field 'current_pool_consumed_delta' must be 0 or -1.")

    elif action == AuditAction.USER_MODULE_ASSIGNMENTS_REPLACED:
        expected_keys = {
            "organization_code",
            "user_id",
            "product_id",
            "product_code",
            "previous_enabled_module_ids",
            "previous_enabled_module_codes",
            "resulting_enabled_module_ids",
            "resulting_enabled_module_codes",
        }
        if set(metadata.keys()) != expected_keys:
            raise AuditEventError(f"Invalid metadata keys for '{action}'. Expected: {expected_keys}")
        if not isinstance(metadata["organization_code"], str) or not metadata["organization_code"].strip():
            raise AuditEventError("Field 'organization_code' must be a non-empty string.")
        _validate_uuid_string(metadata["user_id"], "user_id")
        _validate_uuid_string(metadata["product_id"], "product_id")
        if not isinstance(metadata["product_code"], str) or not metadata["product_code"].strip():
            raise AuditEventError("Field 'product_code' must be a non-empty string.")
        for id_field in ("previous_enabled_module_ids", "resulting_enabled_module_ids"):
            if not isinstance(metadata[id_field], list):
                raise AuditEventError(f"Field '{id_field}' must be a list.")
            for mid in metadata[id_field]:
                _validate_uuid_string(mid, f"{id_field} item")
            if metadata[id_field] != sorted(metadata[id_field]):
                raise AuditEventError(f"Field '{id_field}' must be deterministically sorted.")
        for code_field in ("previous_enabled_module_codes", "resulting_enabled_module_codes"):
            if not isinstance(metadata[code_field], list):
                raise AuditEventError(f"Field '{code_field}' must be a list.")
            for mc in metadata[code_field]:
                if not isinstance(mc, str) or not mc.strip():
                    raise AuditEventError(f"Items in '{code_field}' must be non-empty strings.")
            if metadata[code_field] != sorted(metadata[code_field]):
                raise AuditEventError(f"Field '{code_field}' must be deterministically sorted.")

    elif action == AuditAction.SEAT_OVER_ALLOCATION_DETECTED:
        expected_keys = {
            "organization_code",
            "pool_scope",
            "pool_key",
            "governed_product_ids",
            "total_limit",
            "consumed_seats",
            "over_allocated_amount",
            "detection_context",
        }
        if set(metadata.keys()) != expected_keys:
            raise AuditEventError(f"Invalid metadata keys for '{action}'. Expected: {expected_keys}")
        if not isinstance(metadata["organization_code"], str) or not metadata["organization_code"].strip():
            raise AuditEventError("Field 'organization_code' must be a non-empty string.")
        if metadata["pool_scope"] not in ("product", "plan"):
            raise AuditEventError("Field 'pool_scope' must be 'product' or 'plan'.")
        if not isinstance(metadata["pool_key"], str) or not metadata["pool_key"].strip():
            raise AuditEventError("Field 'pool_key' must be a non-empty string.")
        if not isinstance(metadata["governed_product_ids"], list):
            raise AuditEventError("Field 'governed_product_ids' must be a list.")
        for pid in metadata["governed_product_ids"]:
            _validate_uuid_string(pid, "governed_product_ids item")
        if metadata["governed_product_ids"] != sorted(metadata["governed_product_ids"]):
            raise AuditEventError("Field 'governed_product_ids' must be deterministically sorted.")
        if metadata["total_limit"] is not None and (not isinstance(metadata["total_limit"], int) or metadata["total_limit"] < 0):
            raise AuditEventError("Field 'total_limit' must be a non-negative integer or None.")
        if not isinstance(metadata["consumed_seats"], int) or metadata["consumed_seats"] < 0:
            raise AuditEventError("Field 'consumed_seats' must be a non-negative integer.")
        if not isinstance(metadata["over_allocated_amount"], int) or metadata["over_allocated_amount"] < 0:
            raise AuditEventError("Field 'over_allocated_amount' must be a non-negative integer.")
        if metadata["detection_context"] not in ("plan_downgrade", "reconciliation"):
            raise AuditEventError("Field 'detection_context' must be 'plan_downgrade' or 'reconciliation'.")

    elif action == AuditAction.ONBOARDING_STEP_TRANSITIONED:
        expected_keys = {
            "case_id",
            "from_step",
            "to_step",
            "case_status",
            "organization_code",
            "organization_name",
        }
        if not expected_keys.issubset(set(metadata.keys())):
            raise AuditEventError(f"Missing required metadata keys for '{action}'. Required: {expected_keys}")
        if not isinstance(metadata["case_id"], str) or not metadata["case_id"].strip():
            raise AuditEventError("Field 'case_id' must be a non-empty string.")
        if not isinstance(metadata["from_step"], str) or not metadata["from_step"].strip():
            raise AuditEventError("Field 'from_step' must be a non-empty string.")
        if not isinstance(metadata["to_step"], str) or not metadata["to_step"].strip():
            raise AuditEventError("Field 'to_step' must be a non-empty string.")
        if not isinstance(metadata["case_status"], str) or not metadata["case_status"].strip():
            raise AuditEventError("Field 'case_status' must be a non-empty string.")
        if not isinstance(metadata["organization_code"], str) or not metadata["organization_code"].strip():
            raise AuditEventError("Field 'organization_code' must be a non-empty string.")
        if not isinstance(metadata["organization_name"], str) or not metadata["organization_name"].strip():
            raise AuditEventError("Field 'organization_name' must be a non-empty string.")

    elif action in INVITATION_ACTIONS:
        expected_keys = {"invitation_id", "email", "organization_id", "organization_code"}
        if not expected_keys.issubset(set(metadata.keys())):
            raise AuditEventError(f"Missing required metadata keys for '{action}'. Required: {expected_keys}")
        if not isinstance(metadata["invitation_id"], str) or not metadata["invitation_id"].strip():
            raise AuditEventError("Field 'invitation_id' must be a non-empty string.")
        if not isinstance(metadata["email"], str) or not metadata["email"].strip():
            raise AuditEventError("Field 'email' must be a non-empty string.")
        if not isinstance(metadata["organization_id"], str) or not metadata["organization_id"].strip():
            raise AuditEventError("Field 'organization_id' must be a non-empty string.")
        if not isinstance(metadata["organization_code"], str) or not metadata["organization_code"].strip():
            raise AuditEventError("Field 'organization_code' must be a non-empty string.")

    elif action in BULK_IMPORT_ACTIONS:
        expected_keys = {"job_id", "total_rows"}
        if not expected_keys.issubset(set(metadata.keys())):
            raise AuditEventError(f"Missing required metadata keys for '{action}'. Required: {expected_keys}")
        if not isinstance(metadata["job_id"], str) or not metadata["job_id"].strip():
            raise AuditEventError("Field 'job_id' must be a non-empty string.")
        if not isinstance(metadata["total_rows"], int) or metadata["total_rows"] < 0:
            raise AuditEventError("Field 'total_rows' must be a non-negative integer.")

    elif action in ACCESS_REQUEST_ACTIONS:
        expected_keys = {"request_id", "requester_email"}
        if not expected_keys.issubset(set(metadata.keys())):
            raise AuditEventError(f"Missing required metadata keys for '{action}'. Required: {expected_keys}")
        if not isinstance(metadata["request_id"], str) or not metadata["request_id"].strip():
            raise AuditEventError("Field 'request_id' must be a non-empty string.")
        if not isinstance(metadata["requester_email"], str) or not metadata["requester_email"].strip():
            raise AuditEventError("Field 'requester_email' must be a non-empty string.")

    elif action in SHOWCASE_ACTIONS:
        required = {"product_code", "product_name", "profile_id"}
        if not required.issubset(set(metadata.keys())):
            raise AuditEventError(f"Missing required metadata keys for '{action}'. Required: {required}")
        if not isinstance(metadata["product_code"], str) or not metadata["product_code"].strip():
            raise AuditEventError("Field 'product_code' must be a non-empty string.")
        if not isinstance(metadata["product_name"], str) or not metadata["product_name"].strip():
            raise AuditEventError("Field 'product_name' must be a non-empty string.")
        if not isinstance(metadata["profile_id"], str) or not metadata["profile_id"].strip():
            raise AuditEventError("Field 'profile_id' must be a non-empty string.")

    elif action in DEVELOPER_APP_ACTIONS:
        required = {"application_id", "name", "status"}
        if not required.issubset(set(metadata.keys())):
            raise AuditEventError(f"Missing required metadata keys for '{action}'. Required: {required}")
        if not isinstance(metadata["application_id"], str) or not metadata["application_id"].strip():
            raise AuditEventError("Field 'application_id' must be a non-empty string.")
        if not isinstance(metadata["name"], str) or not metadata["name"].strip():
            raise AuditEventError("Field 'name' must be a non-empty string.")
        if metadata["status"] not in ("active", "suspended", "revoked"):
            raise AuditEventError(f"Invalid status '{metadata['status']}' for developer application.")

    elif action in DEVELOPER_KEY_ACTIONS:
        required = {"application_id", "key_id", "key_prefix", "name", "status"}
        if not required.issubset(set(metadata.keys())):
            raise AuditEventError(f"Missing required metadata keys for '{action}'. Required: {required}")
        if not isinstance(metadata["application_id"], str) or not metadata["application_id"].strip():
            raise AuditEventError("Field 'application_id' must be a non-empty string.")
        if not isinstance(metadata["key_id"], str) or not metadata["key_id"].strip():
            raise AuditEventError("Field 'key_id' must be a non-empty string.")
        if not isinstance(metadata["key_prefix"], str) or not metadata["key_prefix"].strip():
            raise AuditEventError("Field 'key_prefix' must be a non-empty string.")
        if not isinstance(metadata["name"], str) or not metadata["name"].strip():
            raise AuditEventError("Field 'name' must be a non-empty string.")
        if metadata["status"] not in ("active", "expired", "revoked"):
            raise AuditEventError(f"Invalid status '{metadata['status']}' for developer key.")

    elif action in DEVELOPER_WEBHOOK_ACTIONS:
        required = {"application_id", "subscription_id", "target_url", "event_topics", "status"}
        if not required.issubset(set(metadata.keys())):
            raise AuditEventError(f"Missing required metadata keys for '{action}'. Required: {required}")
        if not isinstance(metadata["application_id"], str) or not metadata["application_id"].strip():
            raise AuditEventError("Field 'application_id' must be a non-empty string.")
        if not isinstance(metadata["subscription_id"], str) or not metadata["subscription_id"].strip():
            raise AuditEventError("Field 'subscription_id' must be a non-empty string.")
        if not isinstance(metadata["target_url"], str) or not metadata["target_url"].strip():
            raise AuditEventError("Field 'target_url' must be a non-empty string.")
        if not isinstance(metadata["event_topics"], list):
            raise AuditEventError("Field 'event_topics' must be a list.")
        if metadata["status"] not in ("active", "suspended", "revoked"):
            raise AuditEventError(f"Invalid status '{metadata['status']}' for developer webhook.")

    elif action in SUPPORT_IMPERSONATION_ACTIONS:
        required = {"session_id", "target_user_id", "target_organization_id", "reason"}
        if not required.issubset(set(metadata.keys())):
            raise AuditEventError(f"Missing required metadata keys for '{action}'. Required: {required}")
        _validate_uuid_string(metadata["session_id"], "session_id")
        _validate_uuid_string(metadata["target_user_id"], "target_user_id")
        _validate_uuid_string(metadata["target_organization_id"], "target_organization_id")
        if "target_user_email" in metadata:
            if not isinstance(metadata["target_user_email"], str) or not metadata["target_user_email"].strip():
                raise AuditEventError("Field 'target_user_email' must be a non-empty string.")
        if "operator_email" in metadata:
            if not isinstance(metadata["operator_email"], str) or not metadata["operator_email"].strip():
                raise AuditEventError("Field 'operator_email' must be a non-empty string.")
        if not isinstance(metadata["reason"], str) or not metadata["reason"].strip():
            raise AuditEventError("Field 'reason' must be a non-empty string.")


    elif action in SUPPORT_ROLE_ACTIONS:
        expected_keys = {"target_user_id", "role_code", "role_id", "assignment_id"}
        if set(metadata.keys()) != expected_keys:
            raise AuditEventError(f"Invalid metadata keys for '{action}'. Expected: {expected_keys}")
        _validate_uuid_string(metadata["target_user_id"], "target_user_id")
        if not isinstance(metadata["role_code"], str) or not metadata["role_code"].strip():
            raise AuditEventError("Field 'role_code' must be a non-empty string.")
        _validate_uuid_string(metadata["role_id"], "role_id")
        _validate_uuid_string(metadata["assignment_id"], "assignment_id")

    elif action == AuditAction.USER_ANONYMIZED:
        if not {"pseudonymized_identity", "audit_immutability_note"}.issubset(set(metadata.keys())):
            raise AuditEventError(f"Missing required metadata keys for '{action}'.")
        if set(metadata.keys()) - {"pseudonymized_identity", "audit_immutability_note", "reason"}:
            raise AuditEventError(f"Invalid metadata keys for '{action}'.")
        if not isinstance(metadata["pseudonymized_identity"], str) or not metadata["pseudonymized_identity"].strip():
            raise AuditEventError("Field 'pseudonymized_identity' must be a non-empty string.")
        if not isinstance(metadata["audit_immutability_note"], str) or not metadata["audit_immutability_note"].strip():
            raise AuditEventError("Field 'audit_immutability_note' must be a non-empty string.")
        if "reason" in metadata and (not isinstance(metadata["reason"], str) or not metadata["reason"].strip()):
            raise AuditEventError("Field 'reason' must be a non-empty string.")

    elif action in (
        AuditAction.SHOWCASE_PROFILE_PUBLISHED,
        AuditAction.SHOWCASE_PROFILE_UNPUBLISHED,
        AuditAction.SHOWCASE_CONFIG_CHANGED,
        AuditAction.SHOWCASE_DEMO_LAUNCHED,
    ):
        pass

    else:
        raise AuditEventError(f"Unknown audit action '{action}'.")




def record_audit_event(
    *,
    action: str,
    target_type: str,
    target_id: uuid.UUID | str,
    target_repr: str,
    actor: Any,
    organization_id: uuid.UUID | str | None = None,
    operation_source: str,
    metadata: dict[str, Any],
    correlation_id: uuid.UUID | str | None = None,
) -> AuditLog:
    """Record a verified, immutable audit log entry."""
    # 1. Actor validation
    if not actor or not getattr(actor, "is_authenticated", False) or not getattr(actor, "is_active", False):
        raise AuditEventError("Actor must be an active, authenticated platform user.")
    if getattr(actor, "status", None) != "active":
        raise AuditEventError("Actor status must be active.")

    org_uuid = None
    if organization_id is not None:
        org_uuid = _validate_uuid(organization_id, "organization_id")

    if action in (AuditAction.LOGIN_SUCCESS, AuditAction.LOGOUT_SUCCESS):
        pass
    elif action in TENANT_ADMIN_ELIGIBLE_ACTIONS:
        if org_uuid is None:
            raise AuditEventError(f"Action '{action}' requires a non-null organization_id.")
        if "organization_id" in metadata and metadata["organization_id"] != str(org_uuid):
            raise AuditEventError("Metadata organization_id does not match event organization_id.")
        from apps.organizations.models import MembershipStatus, MembershipType, OrganizationMembership

        is_tenant_admin = OrganizationMembership.objects.filter(
            organization_id=org_uuid,
            user=actor,
            membership_type=MembershipType.TENANT_ADMIN,
            status=MembershipStatus.ACTIVE,
        ).exists()
        if not is_tenant_admin:
            raise AuditEventError("Actor must hold an active tenant administrator membership in the target organization.")
    elif action in PLATFORM_OWNER_PHASE2E_ACTIONS:
        if not getattr(actor, "is_platform_owner", False):
            raise AuditEventError("Actor must possess Platform Owner privileges.")
        if org_uuid is None:
            raise AuditEventError(f"Action '{action}' requires a non-null organization_id.")
        if "organization_id" in metadata and metadata["organization_id"] != str(org_uuid):
            raise AuditEventError("Metadata organization_id does not match event organization_id.")
    elif action in ASSIGNMENT_ACTIONS:
        if org_uuid is None:
            raise AuditEventError(f"Action '{action}' requires a non-null organization_id.")
        if "organization_id" in metadata and metadata["organization_id"] != str(org_uuid):
            raise AuditEventError("Metadata organization_id does not match event organization_id.")
        from apps.organizations.models import MembershipStatus, OrganizationMembership
        from apps.identity.services import get_system_service_actor

        is_system_actor = False
        try:
            sys_actor = get_system_service_actor()
            if actor.id == sys_actor.id:
                is_system_actor = True
        except Exception:
            pass

        is_platform_owner = getattr(actor, "is_platform_owner", False)
        is_member = OrganizationMembership.objects.filter(
            organization_id=org_uuid,
            user=actor,
            status=MembershipStatus.ACTIVE,
        ).exists()

        if not (is_system_actor or is_platform_owner or is_member):
            raise AuditEventError("Actor must be an active organization member, platform owner, or system service actor.")
    elif action in INVITATION_ACTIONS:
        if org_uuid is None:
            raise AuditEventError(f"Action '{action}' requires a non-null organization_id.")
    elif action in BULK_IMPORT_ACTIONS:
        if org_uuid is not None:
            from apps.organizations.models import MembershipStatus, MembershipType, OrganizationMembership
            is_platform_owner = getattr(actor, "is_platform_owner", False)
            is_tenant_admin = OrganizationMembership.objects.filter(
                organization_id=org_uuid,
                user=actor,
                membership_type=MembershipType.TENANT_ADMIN,
                status=MembershipStatus.ACTIVE,
            ).exists()
            if not (is_platform_owner or is_tenant_admin):
                raise AuditEventError("Actor must be a Platform Owner or Tenant Administrator.")
    elif action in ACCESS_REQUEST_ACTIONS:
        if org_uuid is None:
            raise AuditEventError(f"Action '{action}' requires a non-null organization_id.")
        from apps.organizations.models import MembershipStatus, OrganizationMembership
        is_platform_owner = getattr(actor, "is_platform_owner", False)
        is_member = OrganizationMembership.objects.filter(
            organization_id=org_uuid,
            user=actor,
            status=MembershipStatus.ACTIVE,
        ).exists()
        if not (is_platform_owner or is_member):
            raise AuditEventError("Actor must be an active member of the target organization or a platform owner.")
    elif action in (AuditAction.ENTITLEMENT_CREATED, AuditAction.ENTITLEMENT_STATUS_CHANGED):
        if org_uuid is not None:
            from apps.organizations.models import MembershipStatus, MembershipType, OrganizationMembership
            is_platform_owner = getattr(actor, "is_platform_owner", False)
            is_tenant_admin = OrganizationMembership.objects.filter(
                organization_id=org_uuid,
                user=actor,
                membership_type=MembershipType.TENANT_ADMIN,
                status=MembershipStatus.ACTIVE,
            ).exists()
            if not (is_platform_owner or is_tenant_admin):
                raise AuditEventError("Actor must be a Platform Owner or Tenant Administrator.")
        else:
            if not getattr(actor, "is_platform_owner", False):
                raise AuditEventError("Actor must possess platform owner privileges.")
    elif action in DEVELOPER_ACTIONS:
        if org_uuid is None:
            raise AuditEventError(f"Action '{action}' requires a non-null organization_id.")
        from apps.organizations.models import MembershipStatus, MembershipType, OrganizationMembership
        is_platform_owner = getattr(actor, "is_platform_owner", False)
        is_tenant_admin = OrganizationMembership.objects.filter(
            organization_id=org_uuid,
            user=actor,
            membership_type=MembershipType.TENANT_ADMIN,
            status=MembershipStatus.ACTIVE,
        ).exists()
        if not (is_platform_owner or is_tenant_admin):
            raise AuditEventError("Actor must be a Platform Owner or Tenant Administrator in the target organization.")
    elif action in SUPPORT_IMPERSONATION_ACTIONS:
        if org_uuid is None:
            raise AuditEventError(f"Action '{action}' requires a non-null organization_id.")
        is_platform_owner = getattr(actor, "is_platform_owner", False)
        from apps.access_control.services.evaluation import evaluate_access
        from apps.access_control.constants import CONTEXT_SUPPORT, PERMISSION_SUPPORT_IMPERSONATION_INITIATE
        eval_result = evaluate_access(actor, CONTEXT_SUPPORT, None)
        has_perm = eval_result.has_permission(PERMISSION_SUPPORT_IMPERSONATION_INITIATE)
        if not (is_platform_owner or has_perm):
            raise AuditEventError("Actor must hold support.impersonation.initiate permission or be a Platform Owner.")
    elif action in SUPPORT_ROLE_ACTIONS:
        if not getattr(actor, "is_platform_owner", False):
            raise AuditEventError("Actor must possess Platform Owner privileges.")
    else:
        if not getattr(actor, "is_platform_owner", False):
            raise AuditEventError("Actor must possess platform owner privileges.")

    actor_email = getattr(actor, "email", "")
    if not actor_email or not isinstance(actor_email, str):
        raise AuditEventError("Actor must have a valid email.")
    actor_email = actor_email.strip().lower()
    actor_name = getattr(actor, "full_name", "") or ""

    # 2. Choice enumerations validation
    if action not in AuditAction.values:
        raise AuditEventError(f"Invalid action '{action}'.")
    if target_type not in AuditTargetType.values:
        raise AuditEventError(f"Invalid target_type '{target_type}'.")
    if operation_source not in AuditOperationSource.values:
        raise AuditEventError(f"Invalid operation_source '{operation_source}'.")

    # 3. Operation sources compatibility
    if action in (AuditAction.LOGIN_SUCCESS, AuditAction.LOGOUT_SUCCESS):
        if operation_source != AuditOperationSource.AUTHENTICATION:
            raise AuditEventError("Operation source 'authentication' is required for auth events.")
    elif operation_source == AuditOperationSource.AUTHENTICATION:
        raise AuditEventError("Operation source 'authentication' is not permitted for non-auth events.")
    elif operation_source in (AuditOperationSource.BULK_IMPORT, AuditOperationSource.INTEGRATION):
        if (
            action not in CATALOG_ACTIONS
            and action not in SUBSCRIPTION_ACTIONS
            and action not in ASSIGNMENT_ACTIONS
            and action not in BULK_IMPORT_ACTIONS
            and action not in DEVELOPER_ACTIONS
        ):
            raise AuditEventError(
                f"Operation source '{operation_source}' is reserved and not permitted for action '{action}'."
            )
        if correlation_id is None:
            raise AuditEventError(
                f"Operation source '{operation_source}' requires a valid non-null correlation_id."
            )

    # 4. Target representations & UUIDs
    target_uuid = _validate_uuid(target_id, "target_id")
    if not isinstance(target_repr, str) or not target_repr.strip() or len(target_repr) > 255:
        raise AuditEventError("target_repr must be a non-empty string of 255 characters or fewer.")

    corr_uuid = None
    if correlation_id is not None:
        corr_uuid = _validate_uuid(correlation_id, "correlation_id")

    # 5. Action / Target / Source / Organization compatibility checks
    if action in (AuditAction.LOGIN_SUCCESS, AuditAction.LOGOUT_SUCCESS):
        if target_type != AuditTargetType.AUTH:
            raise AuditEventError(f"Action '{action}' requires target_type 'auth'.")
        if operation_source != AuditOperationSource.AUTHENTICATION:
            raise AuditEventError(f"Action '{action}' requires operation_source 'authentication'.")
        if org_uuid is not None:
            raise AuditEventError(f"Action '{action}' must have organization_id=None.")

    elif action in (AuditAction.PRODUCT_CREATED, AuditAction.PRODUCT_UPDATED, AuditAction.PRODUCT_RETIRED):
        if target_type != AuditTargetType.PRODUCT:
            raise AuditEventError(f"Action '{action}' requires target_type 'product'.")
        if operation_source != AuditOperationSource.INTERACTIVE:
            raise AuditEventError(f"Action '{action}' requires operation_source 'interactive'.")
        if org_uuid is not None:
            raise AuditEventError(f"Action '{action}' must have organization_id=None.")

    elif action in (AuditAction.ORGANIZATION_CREATED, AuditAction.ORGANIZATION_UPDATED, AuditAction.ORGANIZATION_RETIRED):
        if target_type != AuditTargetType.ORGANIZATION:
            raise AuditEventError(f"Action '{action}' requires target_type 'organization'.")
        if operation_source != AuditOperationSource.INTERACTIVE:
            raise AuditEventError(f"Action '{action}' requires operation_source 'interactive'.")
        if org_uuid is None or org_uuid != target_uuid:
            raise AuditEventError(f"Action '{action}' requires organization_id equal to target_id.")

    elif action in (AuditAction.ENTITLEMENT_CREATED, AuditAction.ENTITLEMENT_STATUS_CHANGED, AuditAction.ENTITLEMENT_REVOKED):
        if target_type != AuditTargetType.ENTITLEMENT:
            raise AuditEventError(f"Action '{action}' requires target_type 'entitlement'.")
        if operation_source != AuditOperationSource.INTERACTIVE:
            raise AuditEventError(f"Action '{action}' requires operation_source 'interactive'.")
        if org_uuid is None:
            raise AuditEventError(f"Action '{action}' requires a non-null organization_id.")

    elif action in (AuditAction.MODULE_CREATED, AuditAction.MODULE_UPDATED, AuditAction.MODULE_RETIRED):
        if target_type != AuditTargetType.MODULE:
            raise AuditEventError(f"Action '{action}' requires target_type 'module'.")
        if operation_source not in (AuditOperationSource.INTERACTIVE, AuditOperationSource.BULK_IMPORT, AuditOperationSource.INTEGRATION):
            raise AuditEventError(f"Action '{action}' does not permit operation_source '{operation_source}'.")
        if org_uuid is not None:
            raise AuditEventError(f"Action '{action}' must have organization_id=None.")

    elif action in (AuditAction.FEATURE_CREATED, AuditAction.FEATURE_UPDATED, AuditAction.FEATURE_RETIRED):
        if target_type != AuditTargetType.FEATURE:
            raise AuditEventError(f"Action '{action}' requires target_type 'feature'.")
        if operation_source not in (AuditOperationSource.INTERACTIVE, AuditOperationSource.BULK_IMPORT, AuditOperationSource.INTEGRATION):
            raise AuditEventError(f"Action '{action}' does not permit operation_source '{operation_source}'.")
        if org_uuid is not None:
            raise AuditEventError(f"Action '{action}' must have organization_id=None.")

    elif action in (AuditAction.CAPABILITY_CREATED, AuditAction.CAPABILITY_UPDATED, AuditAction.CAPABILITY_RETIRED):
        if target_type != AuditTargetType.CAPABILITY:
            raise AuditEventError(f"Action '{action}' requires target_type 'capability'.")
        if operation_source not in (AuditOperationSource.INTERACTIVE, AuditOperationSource.BULK_IMPORT, AuditOperationSource.INTEGRATION):
            raise AuditEventError(f"Action '{action}' does not permit operation_source '{operation_source}'.")
        if org_uuid is not None:
            raise AuditEventError(f"Action '{action}' must have organization_id=None.")

    elif action in (AuditAction.PLAN_CREATED, AuditAction.PLAN_UPDATED):
        if target_type != AuditTargetType.PLAN:
            raise AuditEventError(f"Action '{action}' requires target_type 'plan'.")
        if operation_source != AuditOperationSource.INTERACTIVE:
            raise AuditEventError(f"Action '{action}' requires operation_source 'interactive'.")
        if org_uuid is not None:
            raise AuditEventError(f"Action '{action}' must have organization_id=None.")

    elif action in (
        AuditAction.PLAN_VERSION_CREATED,
        AuditAction.PLAN_VERSION_UPDATED,
        AuditAction.PLAN_VERSION_CLONED,
        AuditAction.PLAN_VERSION_ACTIVATED,
        AuditAction.PLAN_VERSION_RETIRED,
    ):
        if target_type != AuditTargetType.PLAN_VERSION:
            raise AuditEventError(f"Action '{action}' requires target_type 'plan_version'.")
        if operation_source != AuditOperationSource.INTERACTIVE:
            raise AuditEventError(f"Action '{action}' requires operation_source 'interactive'.")
        if org_uuid is not None:
            raise AuditEventError(f"Action '{action}' must have organization_id=None.")

    elif action in (
        AuditAction.PLAN_PRICE_CREATED,
        AuditAction.PLAN_PRICE_UPDATED,
        AuditAction.PLAN_PRICE_REMOVED,
    ):
        if target_type != AuditTargetType.PLAN_PRICE:
            raise AuditEventError(f"Action '{action}' requires target_type 'plan_price'.")
        if operation_source != AuditOperationSource.INTERACTIVE:
            raise AuditEventError(f"Action '{action}' requires operation_source 'interactive'.")
        if org_uuid is not None:
            raise AuditEventError(f"Action '{action}' must have organization_id=None.")

    elif action in (AuditAction.PLAN_PRODUCT_ADDED, AuditAction.PLAN_PRODUCT_REMOVED):
        if target_type != AuditTargetType.PLAN_PRODUCT:
            raise AuditEventError(f"Action '{action}' requires target_type 'plan_product'.")
        if operation_source != AuditOperationSource.INTERACTIVE:
            raise AuditEventError(f"Action '{action}' requires operation_source 'interactive'.")
        if org_uuid is not None:
            raise AuditEventError(f"Action '{action}' must have organization_id=None.")

    elif action in (AuditAction.PLAN_MODULE_ADDED, AuditAction.PLAN_MODULE_REMOVED):
        if target_type != AuditTargetType.PLAN_MODULE:
            raise AuditEventError(f"Action '{action}' requires target_type 'plan_module'.")
        if operation_source != AuditOperationSource.INTERACTIVE:
            raise AuditEventError(f"Action '{action}' requires operation_source 'interactive'.")
        if org_uuid is not None:
            raise AuditEventError(f"Action '{action}' must have organization_id=None.")

    elif action in (AuditAction.PLAN_CAPABILITY_ADDED, AuditAction.PLAN_CAPABILITY_REMOVED):
        if target_type != AuditTargetType.PLAN_CAPABILITY:
            raise AuditEventError(f"Action '{action}' requires target_type 'plan_capability'.")
        if operation_source != AuditOperationSource.INTERACTIVE:
            raise AuditEventError(f"Action '{action}' requires operation_source 'interactive'.")
        if org_uuid is not None:
            raise AuditEventError(f"Action '{action}' must have organization_id=None.")

    elif action in (
        AuditAction.PLAN_QUOTA_CREATED,
        AuditAction.PLAN_QUOTA_UPDATED,
        AuditAction.PLAN_QUOTA_REMOVED,
    ):
        if target_type != AuditTargetType.PLAN_QUOTA:
            raise AuditEventError(f"Action '{action}' requires target_type 'plan_quota'.")
        if operation_source != AuditOperationSource.INTERACTIVE:
            raise AuditEventError(f"Action '{action}' requires operation_source 'interactive'.")
        if org_uuid is not None:
            raise AuditEventError(f"Action '{action}' must have organization_id=None.")

    elif action in SUBSCRIPTION_ACTIONS:
        if target_type != AuditTargetType.SUBSCRIPTION:
            raise AuditEventError(f"Action '{action}' requires target_type 'subscription'.")
        if operation_source not in (AuditOperationSource.INTERACTIVE, AuditOperationSource.INTEGRATION, AuditOperationSource.BULK_IMPORT):
            raise AuditEventError(f"Action '{action}' does not permit operation_source '{operation_source}'.")
        if org_uuid is None:
            raise AuditEventError(f"Action '{action}' requires a non-null organization_id.")

    elif action in USER_ACTIONS:
        if target_type != AuditTargetType.USER:
            raise AuditEventError(f"Action '{action}' requires target_type 'user'.")
        if operation_source != AuditOperationSource.INTERACTIVE:
            raise AuditEventError(f"Action '{action}' requires operation_source 'interactive'.")
        if org_uuid is not None:
            raise AuditEventError(f"Action '{action}' must have organization_id=None.")

    elif action in SUPPORT_ROLE_ACTIONS:
        if target_type != AuditTargetType.USER:
            raise AuditEventError(f"Action '{action}' requires target_type 'user'.")
        if operation_source != AuditOperationSource.INTERACTIVE:
            raise AuditEventError(f"Action '{action}' requires operation_source 'interactive'.")
        if org_uuid is not None:
            raise AuditEventError(f"Action '{action}' must have organization_id=None.")

    elif action in MEMBERSHIP_ACTIONS:
        if target_type != AuditTargetType.MEMBERSHIP:
            raise AuditEventError(f"Action '{action}' requires target_type 'membership'.")
        if operation_source != AuditOperationSource.INTERACTIVE:
            raise AuditEventError(f"Action '{action}' requires operation_source 'interactive'.")
        if org_uuid is None:
            raise AuditEventError(f"Action '{action}' requires a non-null organization_id.")

    elif action in ROLE_ACTIONS:
        if target_type != AuditTargetType.ROLE:
            raise AuditEventError(f"Action '{action}' requires target_type 'role'.")
        if operation_source != AuditOperationSource.INTERACTIVE:
            raise AuditEventError(f"Action '{action}' requires operation_source 'interactive'.")
        if org_uuid is None:
            raise AuditEventError(f"Action '{action}' requires a non-null organization_id.")

    elif action == AuditAction.CONSOLE_MODULE_POLICY_CHANGED:
        if target_type != AuditTargetType.CONSOLE_POLICY:
            raise AuditEventError(f"Action '{action}' requires target_type 'console_policy'.")
        if operation_source != AuditOperationSource.INTERACTIVE:
            raise AuditEventError(f"Action '{action}' requires operation_source 'interactive'.")
        if org_uuid is None:
            raise AuditEventError(f"Action '{action}' requires a non-null organization_id.")

    elif action == AuditAction.PERMISSION_CEILING_CHANGED:
        if target_type != AuditTargetType.PERMISSION_CEILING:
            raise AuditEventError(f"Action '{action}' requires target_type 'permission_ceiling'.")
        if operation_source != AuditOperationSource.INTERACTIVE:
            raise AuditEventError(f"Action '{action}' requires operation_source 'interactive'.")
        if org_uuid is None:
            raise AuditEventError(f"Action '{action}' requires a non-null organization_id.")

    elif action in (
        AuditAction.USER_PRODUCT_ASSIGNED,
        AuditAction.USER_PRODUCT_SUSPENDED,
        AuditAction.USER_PRODUCT_REACTIVATED,
        AuditAction.USER_PRODUCT_REVOKED,
        AuditAction.USER_MODULE_ASSIGNMENTS_REPLACED,
    ):
        if target_type != AuditTargetType.USER_PRODUCT_ASSIGNMENT:
            raise AuditEventError(f"Action '{action}' requires target_type 'user_product_assignment'.")
        if operation_source not in (AuditOperationSource.INTERACTIVE, AuditOperationSource.INTEGRATION):
            raise AuditEventError(f"Action '{action}' does not permit operation_source '{operation_source}'.")
        if org_uuid is None:
            raise AuditEventError(f"Action '{action}' requires a non-null organization_id.")
        # Actor validation: active tenant admin in org, or platform owner, or system service actor
        is_sys_actor = getattr(actor, "email", "") == "system@vibeconnect.internal"
        is_po = getattr(actor, "is_platform_owner", False)
        if not is_sys_actor and not is_po:
            from apps.organizations.models import MembershipStatus, MembershipType, OrganizationMembership
            is_ta = OrganizationMembership.objects.filter(
                organization_id=org_uuid,
                user=actor,
                membership_type=MembershipType.TENANT_ADMIN,
                status=MembershipStatus.ACTIVE,
            ).exists()
            if not is_ta:
                raise AuditEventError("Actor must hold an active tenant administrator membership in the target organization, or possess Platform Owner privileges, or be the system service actor.")

    elif action == AuditAction.SEAT_OVER_ALLOCATION_DETECTED:
        if target_type != AuditTargetType.SUBSCRIPTION:
            raise AuditEventError(f"Action '{action}' requires target_type 'subscription'.")
        if operation_source not in (AuditOperationSource.INTERACTIVE, AuditOperationSource.INTEGRATION):
            raise AuditEventError(f"Action '{action}' does not permit operation_source '{operation_source}'.")
        if org_uuid is None:
            raise AuditEventError(f"Action '{action}' requires a non-null organization_id.")

    elif action == AuditAction.ONBOARDING_STEP_TRANSITIONED:
        if target_type != AuditTargetType.ONBOARDING_CASE:
            raise AuditEventError(f"Action '{action}' requires target_type 'onboarding_case'.")
        if operation_source != AuditOperationSource.INTERACTIVE:
            raise AuditEventError(f"Action '{action}' requires operation_source 'interactive'.")
    elif action in SHOWCASE_ACTIONS:
        if target_type != AuditTargetType.SHOWCASE_PROFILE:
            raise AuditEventError(f"Action '{action}' requires target_type 'showcase_profile'.")
        if operation_source != AuditOperationSource.INTERACTIVE:
            raise AuditEventError(f"Action '{action}' requires operation_source 'interactive'.")
    elif action in DEVELOPER_APP_ACTIONS:
        if target_type != AuditTargetType.DEVELOPER_APPLICATION:
            raise AuditEventError(f"Action '{action}' requires target_type 'developer_application'.")
        if operation_source not in (AuditOperationSource.INTERACTIVE, AuditOperationSource.INTEGRATION):
            raise AuditEventError(f"Action '{action}' does not permit operation_source '{operation_source}'.")
        if org_uuid is None:
            raise AuditEventError(f"Action '{action}' requires a non-null organization_id.")
    elif action in DEVELOPER_KEY_ACTIONS:
        if target_type != AuditTargetType.DEVELOPER_KEY:
            raise AuditEventError(f"Action '{action}' requires target_type 'developer_key'.")
        if operation_source not in (AuditOperationSource.INTERACTIVE, AuditOperationSource.INTEGRATION):
            raise AuditEventError(f"Action '{action}' does not permit operation_source '{operation_source}'.")
        if org_uuid is None:
            raise AuditEventError(f"Action '{action}' requires a non-null organization_id.")
    elif action in DEVELOPER_WEBHOOK_ACTIONS:
        if target_type != AuditTargetType.DEVELOPER_WEBHOOK:
            raise AuditEventError(f"Action '{action}' requires target_type 'developer_webhook'.")
        if operation_source not in (AuditOperationSource.INTERACTIVE, AuditOperationSource.INTEGRATION):
            raise AuditEventError(f"Action '{action}' does not permit operation_source '{operation_source}'.")
        if org_uuid is None:
            raise AuditEventError(f"Action '{action}' requires a non-null organization_id.")
    elif action in SUPPORT_IMPERSONATION_ACTIONS:
        if target_type != AuditTargetType.SUPPORT_IMPERSONATION:
            raise AuditEventError(f"Action '{action}' requires target_type 'support_impersonation'.")
        if operation_source not in (AuditOperationSource.INTERACTIVE, AuditOperationSource.INTEGRATION):
            raise AuditEventError(f"Action '{action}' does not permit operation_source '{operation_source}'.")
        if org_uuid is None:
            raise AuditEventError(f"Action '{action}' requires a non-null organization_id.")

    # 6. Metadata schema validation
    _validate_metadata(action, metadata)

    # 7. Persistence
    return AuditLog.objects.create(
        action=action,
        target_type=target_type,
        target_id=target_uuid,
        target_repr=target_repr.strip(),
        actor=actor,
        actor_email=actor_email,
        actor_name=actor_name,
        organization_id=org_uuid,
        operation_source=operation_source,
        correlation_id=corr_uuid,
        metadata=metadata,
    )
