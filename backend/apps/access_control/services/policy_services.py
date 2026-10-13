"""Platform Owner Console Module Policy domain service."""

from typing import Any
import uuid

from django.db import transaction

from apps.access_control.models import ConsoleModule, OrganizationConsoleModulePolicy
from apps.access_control.services.guards import (
    ModuleCannotBeDisabledError,
    ModuleNotFoundError,
    OrganizationNotActiveError,
    validate_platform_owner_actor,
)
from apps.auditlog.models import AuditAction, AuditOperationSource, AuditTargetType
from apps.auditlog.services import record_audit_event
from apps.organizations.models import Organization


def set_console_module_policy(
    *,
    actor: Any,
    organization_id: uuid.UUID | str,
    module_key: str,
    is_enabled: bool,
    correlation_id: uuid.UUID | str | None = None,
) -> OrganizationConsoleModulePolicy:
    """Enable or disable a tenant console module for an organization (Platform Owner only)."""
    validate_platform_owner_actor(actor)

    clean_org_id = uuid.UUID(str(organization_id))

    with transaction.atomic():
        org = Organization.objects.select_for_update().filter(id=clean_org_id).first()
        if not org:
            raise OrganizationNotActiveError("Organization not found.", code="ORGANIZATION_NOT_ACTIVE")

        mod = ConsoleModule.objects.filter(key=module_key).first()
        if not mod or not mod.is_active:
            raise ModuleNotFoundError(f"Module '{module_key}' not found or inactive.", code="MODULE_NOT_FOUND")

        if mod.target_context != "tenant":
            raise ModuleNotFoundError(
                "Platform Owner modules cannot receive organization policies.",
                code="MODULE_NOT_FOUND",
            )

        if mod.is_core:
            raise ModuleCannotBeDisabledError(
                f"Core module '{mod.key}' cannot be modified or disabled.",
                code="MODULE_CANNOT_BE_DISABLED",
            )

        policy, created = OrganizationConsoleModulePolicy.objects.select_for_update().get_or_create(
            organization=org,
            console_module=mod,
            defaults={"is_enabled": is_enabled, "updated_by": actor},
        )

        if not created:
            previous_enabled = policy.is_enabled
            if previous_enabled == is_enabled:
                return policy  # No-op: produce zero audit events

            policy.is_enabled = is_enabled
            policy.updated_by = actor
            policy.save(update_fields=["is_enabled", "updated_by", "updated_at"])
        else:
            previous_enabled = not is_enabled

        record_audit_event(
            action=AuditAction.CONSOLE_MODULE_POLICY_CHANGED,
            target_type=AuditTargetType.CONSOLE_POLICY,
            target_id=policy.id,
            target_repr=f"{org.code}:{mod.key}",
            actor=actor,
            organization_id=clean_org_id,
            operation_source=AuditOperationSource.INTERACTIVE,
            correlation_id=correlation_id,
            metadata={
                "organization_id": str(clean_org_id),
                "module_key": mod.key,
                "previous_is_enabled": previous_enabled,
                "resulting_is_enabled": is_enabled,
            },
        )

    return policy
