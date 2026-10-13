"""Platform Owner Permission Ceiling domain service."""

from typing import Any
import uuid

from django.db import transaction

from apps.access_control.models import AccessPermission, OrganizationPermissionCeiling
from apps.access_control.services.guards import (
    AccessControlValidationError,
    OrganizationNotActiveError,
    PermissionNotFoundError,
    validate_platform_owner_actor,
)
from apps.auditlog.models import AuditAction, AuditOperationSource, AuditTargetType
from apps.auditlog.services import record_audit_event
from apps.organizations.models import Organization


def set_permission_ceiling(
    *,
    actor: Any,
    organization_id: uuid.UUID | str,
    permission_key: str,
    is_allowed: bool,
    correlation_id: uuid.UUID | str | None = None,
) -> OrganizationPermissionCeiling:
    """Set an organization permission ceiling for a tenant permission (Platform Owner only)."""
    validate_platform_owner_actor(actor)

    clean_org_id = uuid.UUID(str(organization_id))

    with transaction.atomic():
        org = Organization.objects.select_for_update().filter(id=clean_org_id).first()
        if not org:
            raise OrganizationNotActiveError("Organization not found.", code="ORGANIZATION_NOT_ACTIVE")

        perm = (
            AccessPermission.objects.select_related("console_module")
            .filter(key=permission_key)
            .first()
        )
        if not perm or not perm.is_active:
            raise PermissionNotFoundError(
                f"Permission '{permission_key}' not found or inactive.",
                code="PERMISSION_NOT_FOUND",
            )

        if perm.console_module.target_context != "tenant":
            raise PermissionNotFoundError(
                "Only tenant permissions have organization ceilings.",
                code="PERMISSION_NOT_FOUND",
            )

        # Evaluate coherent ceiling rules across the projected state
        current_ceilings = dict(
            OrganizationPermissionCeiling.objects.filter(organization=org).values_list(
                "permission_id", "is_allowed"
            )
        )
        current_ceilings[permission_key] = is_allowed

        view_allowed = current_ceilings.get("roles.view", True)
        manage_allowed = current_ceilings.get("roles.manage", True)
        assign_allowed = current_ceilings.get("roles.assign", True)

        if manage_allowed and not view_allowed:
            raise AccessControlValidationError(
                "roles.manage cannot be allowed when roles.view is denied in organization ceiling.",
                code="VALIDATION_ERROR",
            )
        if assign_allowed and not view_allowed:
            raise AccessControlValidationError(
                "roles.assign cannot be allowed when roles.view is denied in organization ceiling.",
                code="VALIDATION_ERROR",
            )

        ceiling, created = OrganizationPermissionCeiling.objects.select_for_update().get_or_create(
            organization=org,
            permission=perm,
            defaults={"is_allowed": is_allowed, "updated_by": actor},
        )

        if not created:
            previous_allowed = ceiling.is_allowed
            if previous_allowed == is_allowed:
                return ceiling  # No-op: produce zero audit events

            ceiling.is_allowed = is_allowed
            ceiling.updated_by = actor
            ceiling.save(update_fields=["is_allowed", "updated_by", "updated_at"])
        else:
            previous_allowed = not is_allowed

        record_audit_event(
            action=AuditAction.PERMISSION_CEILING_CHANGED,
            target_type=AuditTargetType.PERMISSION_CEILING,
            target_id=ceiling.id,
            target_repr=f"{org.code}:{perm.key}",
            actor=actor,
            organization_id=clean_org_id,
            operation_source=AuditOperationSource.INTERACTIVE,
            correlation_id=correlation_id,
            metadata={
                "organization_id": str(clean_org_id),
                "permission_key": perm.key,
                "previous_is_allowed": previous_allowed,
                "resulting_is_allowed": is_allowed,
            },
        )

    return ceiling
