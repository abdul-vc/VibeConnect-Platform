"""Role lifecycle domain services (create, update, retire)."""

from collections.abc import Iterable
import re
from typing import Any
import uuid

from django.db import transaction

from apps.access_control.models import (
    AccessPermission,
    ConsoleModule,
    OrganizationConsoleModulePolicy,
    OrganizationPermissionCeiling,
    Role,
    RolePermission,
)
from apps.access_control.services.guards import (
    AccessControlValidationError,
    InsufficientPrivilegesError,
    PermissionNotFoundError,
    PermissionOutsideCeilingError,
    RoleAlreadyExistsError,
    RoleInUseError,
    RoleNotFoundError,
    RoleRetiredError,
    SystemRoleImmutableError,
    calculate_actor_effective_permissions,
    evaluate_structural_last_admin,
    lock_organization_and_tenant_admins,
    require_actor_permission,
    validate_permission_dependencies,
    validate_tenant_admin_actor,
)
from apps.auditlog.models import AuditAction, AuditOperationSource, AuditTargetType
from apps.auditlog.services import record_audit_event
from apps.organizations.models import Organization, OrganizationMembership

ROLE_CODE_REGEX = re.compile(r"^[a-z0-9]+(?:_[a-z0-9]+)*$")


def create_role(
    *,
    actor: Any,
    organization_id: uuid.UUID | str,
    code: str,
    name: str,
    description: str = "",
    permission_keys: Iterable[str],
    correlation_id: uuid.UUID | str | None = None,
) -> Role:
    """Create a new custom organization role with atomic RolePermission assignments and audit recording."""
    # 1. Actor and permission verification
    validate_tenant_admin_actor(actor, organization_id)
    require_actor_permission(actor, organization_id, "roles.manage")

    # 2. Field validation
    if not isinstance(code, str) or not code.strip():
        raise AccessControlValidationError("Role code is required.", code="VALIDATION_ERROR")
    trimmed_code = code.strip()
    if not ROLE_CODE_REGEX.match(trimmed_code) or len(trimmed_code) > 64:
        raise AccessControlValidationError(
            "Role code must be lowercase alphanumeric with single underscores and at most 64 characters.",
            code="VALIDATION_ERROR",
        )

    if not isinstance(name, str) or not name.strip() or len(name.strip()) > 100:
        raise AccessControlValidationError(
            "Role name must be a non-empty string of 100 characters or fewer.",
            code="VALIDATION_ERROR",
        )
    trimmed_name = name.strip()
    desc_val = str(description).strip() if description is not None else ""

    # 3. Permission validation & dependencies
    sorted_keys = validate_permission_dependencies(permission_keys)

    # All requested permissions must exist, be active, and belong to tenant modules
    existing_perms = {
        p.key: p
        for p in AccessPermission.objects.select_related("console_module").filter(key__in=sorted_keys)
    }
    for k in sorted_keys:
        perm = existing_perms.get(k)
        if not perm or not perm.is_active:
            raise PermissionNotFoundError(f"Permission '{k}' not found or inactive.", code="PERMISSION_NOT_FOUND")
        if perm.console_module.target_context != "tenant" or not perm.console_module.is_active:
            raise PermissionNotFoundError(
                f"Permission '{k}' belongs to an inactive or non-tenant module.",
                code="PERMISSION_NOT_FOUND",
            )

    # Organization module policy and permission ceiling must allow each permission
    enabled_policies = set(
        OrganizationConsoleModulePolicy.objects.filter(
            organization_id=organization_id,
            is_enabled=True,
        ).values_list("console_module_id", flat=True)
    )
    allowed_ceilings = set(
        OrganizationPermissionCeiling.objects.filter(
            organization_id=organization_id,
            is_allowed=True,
        ).values_list("permission_id", flat=True)
    )

    for k in sorted_keys:
        perm = existing_perms[k]
        if perm.console_module_id not in enabled_policies:
            raise PermissionOutsideCeilingError(
                f"Console module '{perm.console_module_id}' is disabled for this organization.",
                code="PERMISSION_OUTSIDE_CEILING",
            )
        if k not in allowed_ceilings:
            raise PermissionOutsideCeilingError(
                f"Permission '{k}' is denied by the organization permission ceiling.",
                code="PERMISSION_OUTSIDE_CEILING",
            )

    # Non-escalation: requested permissions must be a subset of actor's effective authority
    actor_effective = calculate_actor_effective_permissions(actor, organization_id)
    if not set(sorted_keys).issubset(actor_effective):
        raise InsufficientPrivilegesError(
            "Actor cannot grant permissions exceeding their own effective permissions in this organization.",
            code="INSUFFICIENT_PRIVILEGES",
        )

    # 4. Atomic persistence
    with transaction.atomic():
        # Lock organization
        org = Organization.objects.select_for_update().filter(id=organization_id).first()
        if not org:
            raise AccessControlValidationError("Organization not found.", code="VALIDATION_ERROR")

        if Role.objects.filter(organization_id=organization_id, code=trimmed_code).exists():
            raise RoleAlreadyExistsError(
                f"A role with code '{trimmed_code}' already exists in this organization.",
                code="ROLE_ALREADY_EXISTS",
            )

        role = Role.objects.create(
            organization=org,
            code=trimmed_code,
            name=trimmed_name,
            description=desc_val,
            is_system_role=False,
            status="active",
            created_by=actor,
            updated_by=actor,
        )

        for k in sorted_keys:
            RolePermission.objects.create(role=role, permission=existing_perms[k])

        record_audit_event(
            action=AuditAction.ROLE_CREATED,
            target_type=AuditTargetType.ROLE,
            target_id=role.id,
            target_repr=f"{role.code}:{role.name}",
            actor=actor,
            organization_id=org.id,
            operation_source=AuditOperationSource.INTERACTIVE,
            correlation_id=correlation_id,
            metadata={
                "organization_id": str(org.id),
                "role_code": role.code,
                "role_name": role.name,
                "permission_keys": sorted_keys,
            },
        )

    return role


def update_role(
    *,
    actor: Any,
    organization_id: uuid.UUID | str,
    role_id: uuid.UUID | str,
    name: str | None = None,
    description: str | None = None,
    permission_keys: Iterable[str] | None = None,
    correlation_id: uuid.UUID | str | None = None,
) -> Role:
    """Update profile fields and/or permissions of an existing custom role."""
    validate_tenant_admin_actor(actor, organization_id)
    require_actor_permission(actor, organization_id, "roles.manage")

    clean_org_id = uuid.UUID(str(organization_id))

    with transaction.atomic():
        # Global deterministic locking order
        org, tenant_admins = lock_organization_and_tenant_admins(clean_org_id)

        role = (
            Role.objects.select_for_update()
            .filter(id=role_id)
            .first()
        )
        if not role:
            raise RoleNotFoundError("Role not found in this organization.", code="ROLE_NOT_FOUND")

        if role.is_system_role:
            raise SystemRoleImmutableError("System roles cannot be modified.", code="SYSTEM_ROLE_IMMUTABLE")

        if role.organization_id != clean_org_id:
            raise RoleNotFoundError("Role not found in this organization.", code="ROLE_NOT_FOUND")

        if role.status == "retired":
            raise RoleRetiredError("Retired roles cannot be modified.", code="ROLE_RETIRED")

        # Track modifications
        name_changed = False
        desc_changed = False
        new_name = role.name
        new_desc = role.description

        if name is not None:
            trimmed_name = str(name).strip()
            if not trimmed_name or len(trimmed_name) > 100:
                raise AccessControlValidationError(
                    "Role name must be a non-empty string of 100 characters or fewer.",
                    code="VALIDATION_ERROR",
                )
            if trimmed_name != role.name:
                name_changed = True
                new_name = trimmed_name

        if description is not None:
            desc_val = str(description).strip()
            if desc_val != role.description:
                desc_changed = True
                new_desc = desc_val

        # Permission changes
        permissions_changed = False
        added_keys: list[str] = []
        removed_keys: list[str] = []

        if permission_keys is not None:
            sorted_keys = validate_permission_dependencies(permission_keys)
            existing_role_perms = set(
                RolePermission.objects.filter(role=role).values_list("permission_id", flat=True)
            )
            requested_perms_set = set(sorted_keys)

            if requested_perms_set != existing_role_perms:
                permissions_changed = True
                added_keys = sorted(requested_perms_set - existing_role_perms)
                removed_keys = sorted(existing_role_perms - requested_perms_set)

                # Validate any new permissions exist, active, tenant context
                existing_perm_objs = {
                    p.key: p
                    for p in AccessPermission.objects.select_related("console_module").filter(key__in=sorted_keys)
                }
                for k in sorted_keys:
                    perm = existing_perm_objs.get(k)
                    if not perm or not perm.is_active:
                        raise PermissionNotFoundError(
                            f"Permission '{k}' not found or inactive.", code="PERMISSION_NOT_FOUND"
                        )
                    if perm.console_module.target_context != "tenant" or not perm.console_module.is_active:
                        raise PermissionNotFoundError(
                            f"Permission '{k}' belongs to an inactive or non-tenant module.",
                            code="PERMISSION_NOT_FOUND",
                        )

                # Must be allowed by module policies and ceilings
                enabled_policies = set(
                    OrganizationConsoleModulePolicy.objects.filter(
                        organization_id=clean_org_id,
                        is_enabled=True,
                    ).values_list("console_module_id", flat=True)
                )
                allowed_ceilings = set(
                    OrganizationPermissionCeiling.objects.filter(
                        organization_id=clean_org_id,
                        is_allowed=True,
                    ).values_list("permission_id", flat=True)
                )
                for k in sorted_keys:
                    perm = existing_perm_objs[k]
                    if perm.console_module_id not in enabled_policies:
                        raise PermissionOutsideCeilingError(
                            f"Console module '{perm.console_module_id}' is disabled.",
                            code="PERMISSION_OUTSIDE_CEILING",
                        )
                    if k not in allowed_ceilings:
                        raise PermissionOutsideCeilingError(
                            f"Permission '{k}' is denied by the ceiling.",
                            code="PERMISSION_OUTSIDE_CEILING",
                        )

                # Non-escalation check: only permissions newly added by the update must be within actor's effective permissions
                actor_effective = calculate_actor_effective_permissions(actor, clean_org_id)
                if not set(added_keys).issubset(actor_effective):
                    raise InsufficientPrivilegesError(
                        "Actor cannot add permissions exceeding their own effective permissions.",
                        code="INSUFFICIENT_PRIVILEGES",
                    )

                # Evaluate structural last-admin invariant if permissions are being modified
                evaluate_structural_last_admin(
                    organization_id=clean_org_id,
                    modified_role_id=role.id,
                    new_permission_keys=sorted_keys,
                    locked_tenant_admins=tenant_admins,
                )

                # Apply permission mutations
                RolePermission.objects.filter(role=role).delete()
                for k in sorted_keys:
                    RolePermission.objects.create(role=role, permission=existing_perm_objs[k])

        # Apply profile field mutations
        if name_changed or desc_changed or permissions_changed:
            role.name = new_name
            role.description = new_desc
            role.updated_by = actor
            role.save(update_fields=["name", "description", "updated_by", "updated_at"])

        # Record truthful audit events
        if name_changed or desc_changed:
            record_audit_event(
                action=AuditAction.ROLE_UPDATED,
                target_type=AuditTargetType.ROLE,
                target_id=role.id,
                target_repr=f"{role.code}:{role.name}",
                actor=actor,
                organization_id=clean_org_id,
                operation_source=AuditOperationSource.INTERACTIVE,
                correlation_id=correlation_id,
                metadata={
                    "organization_id": str(clean_org_id),
                    "role_code": role.code,
                    "name_changed": name_changed,
                    "description_changed": desc_changed,
                },
            )

        if permissions_changed:
            record_audit_event(
                action=AuditAction.ROLE_PERMISSIONS_CHANGED,
                target_type=AuditTargetType.ROLE,
                target_id=role.id,
                target_repr=f"{role.code}:{role.name}",
                actor=actor,
                organization_id=clean_org_id,
                operation_source=AuditOperationSource.INTERACTIVE,
                correlation_id=correlation_id,
                metadata={
                    "organization_id": str(clean_org_id),
                    "role_code": role.code,
                    "added_permission_keys": added_keys,
                    "removed_permission_keys": removed_keys,
                },
            )

    return role


def retire_role(
    *,
    actor: Any,
    organization_id: uuid.UUID | str,
    role_id: uuid.UUID | str,
    correlation_id: uuid.UUID | str | None = None,
) -> Role:
    """Retire an unused custom organization role."""
    validate_tenant_admin_actor(actor, organization_id)
    require_actor_permission(actor, organization_id, "roles.manage")

    clean_org_id = uuid.UUID(str(organization_id))

    with transaction.atomic():
        # Global deterministic locking order
        org, tenant_admins = lock_organization_and_tenant_admins(clean_org_id)

        role = Role.objects.select_for_update().filter(id=role_id).first()
        if not role:
            raise RoleNotFoundError("Role not found in this organization.", code="ROLE_NOT_FOUND")

        if role.is_system_role:
            raise SystemRoleImmutableError("System roles cannot be retired.", code="SYSTEM_ROLE_IMMUTABLE")

        if role.organization_id != clean_org_id:
            raise RoleNotFoundError("Role not found in this organization.", code="ROLE_NOT_FOUND")

        if role.status == "retired":
            raise RoleRetiredError("Role is already retired.", code="ROLE_RETIRED")

        # Reject if referenced by any active, suspended, or ended membership
        if OrganizationMembership.objects.filter(role=role).exists():
            raise RoleInUseError(
                "Role is assigned to one or more memberships and cannot be retired.",
                code="ROLE_IN_USE",
            )

        # Structural last-admin evaluation
        evaluate_structural_last_admin(
            organization_id=clean_org_id,
            retired_role_id=role.id,
            locked_tenant_admins=tenant_admins,
        )

        role.status = "retired"
        role.updated_by = actor
        role.save(update_fields=["status", "updated_by", "updated_at"])

        record_audit_event(
            action=AuditAction.ROLE_RETIRED,
            target_type=AuditTargetType.ROLE,
            target_id=role.id,
            target_repr=f"{role.code}:{role.name}",
            actor=actor,
            organization_id=clean_org_id,
            operation_source=AuditOperationSource.INTERACTIVE,
            correlation_id=correlation_id,
            metadata={
                "organization_id": str(clean_org_id),
                "role_code": role.code,
            },
        )

    return role
