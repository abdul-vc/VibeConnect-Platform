"""Role assignment domain service for tenant administrator memberships."""

from typing import Any
import uuid

from django.db import transaction

from apps.access_control.constants import PREDEFINED_SUPPORT_ROLES
from apps.access_control.models import Role, RolePermission
from apps.access_control.services.guards import (
    AccessControlValidationError,
    InsufficientPrivilegesError,
    RoleNotAssignableToMemberError,
    RoleNotFoundError,
    RoleRetiredError,
    calculate_actor_effective_permissions,
    evaluate_structural_last_admin,
    lock_organization_and_tenant_admins,
    require_actor_permission,
    validate_tenant_admin_actor,
)
from apps.auditlog.models import AuditAction, AuditOperationSource, AuditTargetType
from apps.auditlog.services import record_audit_event
from apps.organizations.models import MembershipType, OrganizationMembership


def assign_membership_role(
    *,
    actor: Any,
    organization_id: uuid.UUID | str,
    membership_id: uuid.UUID | str,
    role_id: uuid.UUID | str | None,
    correlation_id: uuid.UUID | str | None = None,
) -> OrganizationMembership:
    """Assign an active role to a tenant administrator membership under pessimistic locking and non-escalation."""
    validate_tenant_admin_actor(actor, organization_id)
    require_actor_permission(actor, organization_id, "roles.assign")

    clean_org_id = uuid.UUID(str(organization_id))
    clean_mem_id = uuid.UUID(str(membership_id))

    # Non-locking pre-lookup for tenant boundary check
    pre_mem = (
        OrganizationMembership.objects.filter(id=clean_mem_id)
        .values("organization_id", "membership_type")
        .first()
    )
    if not pre_mem or pre_mem["organization_id"] != clean_org_id:
        raise AccessControlValidationError(
            "Membership not found in this organization.",
            code="MEMBERSHIP_NOT_FOUND",
        )

    if pre_mem["membership_type"] != MembershipType.TENANT_ADMIN:
        raise RoleNotAssignableToMemberError(
            "Roles can only be assigned to tenant administrators.",
            code="ROLE_NOT_ASSIGNABLE_TO_MEMBER",
        )

    with transaction.atomic():
        # Global deterministic locking order
        org, tenant_admins = lock_organization_and_tenant_admins(clean_org_id)

        target_mem = next((m for m in tenant_admins if m.id == clean_mem_id), None)
        if not target_mem:
            raise AccessControlValidationError(
                "Target membership not found in locked set.",
                code="MEMBERSHIP_NOT_FOUND",
            )

        # Resolve target role
        if role_id is None:
            target_role = Role.objects.filter(code="system_tenant_admin", is_system_role=True).first()
            if not target_role:
                raise RoleNotFoundError(
                    "System tenant admin role is missing.",
                    code="ROLE_NOT_FOUND",
                )
        else:
            clean_role_id = uuid.UUID(str(role_id))
            target_role = Role.objects.select_for_update().filter(id=clean_role_id).first()
            if not target_role:
                raise RoleNotFoundError("Target role not found.", code="ROLE_NOT_FOUND")
            if target_role.is_system_role and target_role.code in PREDEFINED_SUPPORT_ROLES:
                raise RoleNotFoundError("Support roles cannot be assigned to tenant memberships.", code="ROLE_NOT_FOUND")
            if not target_role.is_system_role and target_role.organization_id != clean_org_id:
                raise RoleNotFoundError(
                    "Target role does not belong to this organization.",
                    code="ROLE_NOT_FOUND",
                )

        if target_role.status != "active":
            raise RoleRetiredError("Cannot assign a retired role.", code="ROLE_RETIRED")

        # Non-escalation: target role's complete active registered permissions must be subset of actor's effective permissions
        target_role_perms = set(
            RolePermission.objects.filter(role=target_role)
            .select_related("permission")
            .filter(permission__is_active=True)
            .values_list("permission_id", flat=True)
        )
        actor_effective = calculate_actor_effective_permissions(actor, clean_org_id)
        if not target_role_perms.issubset(actor_effective):
            raise InsufficientPrivilegesError(
                "Actor cannot assign a role with permissions exceeding their own effective permissions.",
                code="INSUFFICIENT_PRIVILEGES",
            )

        # No-op check: if role unchanged, emit zero audit events
        if target_mem.role_id == target_role.id:
            return target_mem

        # Structural last-admin evaluation
        evaluate_structural_last_admin(
            organization_id=clean_org_id,
            reassigned_membership_id=target_mem.id,
            new_role=target_role,
            locked_tenant_admins=tenant_admins,
        )

        previous_role_id = target_mem.role_id
        previous_role_code = target_mem.role.code if target_mem.role else ""

        target_mem.role = target_role
        target_mem.save(update_fields=["role", "updated_at"])

        record_audit_event(
            action=AuditAction.MEMBERSHIP_ROLE_ASSIGNED,
            target_type=AuditTargetType.MEMBERSHIP,
            target_id=target_mem.id,
            target_repr=f"{org.code}:{target_mem.user.email}",
            actor=actor,
            organization_id=clean_org_id,
            operation_source=AuditOperationSource.INTERACTIVE,
            correlation_id=correlation_id,
            metadata={
                "organization_id": str(clean_org_id),
                "membership_id": str(target_mem.id),
                "previous_role_id": str(previous_role_id),
                "previous_role_code": previous_role_code,
                "resulting_role_id": str(target_role.id),
                "resulting_role_code": target_role.code,
            },
        )

    return target_mem
