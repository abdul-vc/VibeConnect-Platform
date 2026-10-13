"""Developer Console Audit Service.

Centralized audit logging for developer console management operations using
the append-only AuditLog infrastructure.
"""

from typing import Any
import uuid

from django.http import HttpRequest

from apps.auditlog.models import (
    AuditAction,
    AuditOperationSource,
    AuditTargetType,
)
from apps.auditlog.services import record_audit_event
from apps.developer_console.models import DeveloperApiKey, DeveloperApplication


def _get_request_metadata(request: HttpRequest) -> tuple[uuid.UUID, str]:
    corr_id = getattr(request, "correlation_id", None)
    if not corr_id:
        corr_id = uuid.uuid4()
    elif isinstance(corr_id, str):
        try:
            corr_id = uuid.UUID(corr_id)
        except (ValueError, TypeError):
            corr_id = uuid.uuid4()

    client_ip = request.META.get("HTTP_X_FORWARDED_FOR")
    if client_ip:
        client_ip = client_ip.split(",")[0].strip()
    else:
        client_ip = request.META.get("REMOTE_ADDR", "unknown")
    return corr_id, client_ip


def audit_developer_application_event(
    *,
    request: HttpRequest,
    action: str,
    application: DeveloperApplication,
    previous_status: str | None = None,
    resulting_status: str | None = None,
    reason: str | None = None,
) -> None:
    """Record audit log entry for developer application lifecycle events."""
    corr_id, client_ip = _get_request_metadata(request)
    metadata: dict[str, Any] = {
        "application_id": str(application.id),
        "name": application.name,
        "status": application.status,
        "ip_address": client_ip,
        "request_id": str(corr_id),
    }
    if previous_status:
        metadata["previous_status"] = previous_status
    if resulting_status:
        metadata["resulting_status"] = resulting_status
    if reason:
        metadata["reason"] = reason

    record_audit_event(
        action=action,
        target_type=AuditTargetType.DEVELOPER_APPLICATION,
        target_id=application.id,
        target_repr=f"{application.name} ({application.id})",
        actor=request.user,
        organization_id=application.organization_id,
        operation_source=AuditOperationSource.INTEGRATION,
        correlation_id=corr_id,
        metadata=metadata,
    )


def audit_developer_key_event(
    *,
    request: HttpRequest,
    action: str,
    key: DeveloperApiKey,
    previous_status: str | None = None,
    resulting_status: str | None = None,
    reason: str | None = None,
    is_emergency: bool = False,
    old_key: DeveloperApiKey | None = None,
) -> None:
    """Record audit log entry for developer API key lifecycle events."""
    corr_id, client_ip = _get_request_metadata(request)
    metadata: dict[str, Any] = {
        "application_id": str(key.application_id),
        "key_id": str(key.id),
        "key_prefix": key.key_prefix,
        "name": key.name,
        "status": key.status,
        "scopes": key.scopes,
        "ip_address": client_ip,
        "request_id": str(corr_id),
    }
    if previous_status:
        metadata["previous_status"] = previous_status
    if resulting_status:
        metadata["resulting_status"] = resulting_status
    if reason:
        metadata["reason"] = reason
    if is_emergency:
        metadata["is_emergency"] = True
    if old_key:
        metadata["old_key_id"] = str(old_key.id)
        metadata["old_key_prefix"] = old_key.key_prefix

    record_audit_event(
        action=action,
        target_type=AuditTargetType.DEVELOPER_KEY,
        target_id=key.id,
        target_repr=f"{key.name} [{key.key_prefix}]",
        actor=request.user,
        organization_id=key.application.organization_id,
        operation_source=AuditOperationSource.INTEGRATION,
        correlation_id=corr_id,
        metadata=metadata,
    )


def audit_developer_webhook_event(
    *,
    request: HttpRequest,
    action: str,
    subscription: Any,
    delivery: Any | None = None,
    previous_status: str | None = None,
    resulting_status: str | None = None,
    reason: str | None = None,
) -> None:
    """Record audit log entry for developer webhook lifecycle events."""
    corr_id, client_ip = _get_request_metadata(request)
    metadata: dict[str, Any] = {
        "application_id": str(subscription.application_id),
        "subscription_id": str(subscription.id),
        "target_url": subscription.target_url,
        "event_topics": subscription.event_topics,
        "status": subscription.status,
        "ip_address": client_ip,
        "request_id": str(corr_id),
    }
    if previous_status:
        metadata["previous_status"] = previous_status
    if resulting_status:
        metadata["resulting_status"] = resulting_status
    if reason:
        metadata["reason"] = reason
    if delivery:
        metadata["delivery_id"] = str(delivery.id)
        metadata["event_id"] = str(delivery.event_id)
        metadata["event_type"] = delivery.event_type
        metadata["retry_attempt"] = delivery.attempt_count

    record_audit_event(
        action=action,
        target_type=AuditTargetType.DEVELOPER_WEBHOOK,
        target_id=subscription.id,
        target_repr=f"WebhookSub [{subscription.id}] -> {subscription.target_url}",
        actor=request.user,
        organization_id=subscription.application.organization_id,
        operation_source=AuditOperationSource.INTEGRATION,
        correlation_id=corr_id,
        metadata=metadata,
    )
