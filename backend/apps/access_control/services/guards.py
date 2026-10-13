"""Shared actor, locking, dependency, and structural last-admin guards for Access Control."""

from collections.abc import Iterable
from typing import Any
import uuid

from django.contrib.auth import get_user_model

from apps.access_control.models import (
    AccessPermission,
    ConsoleModule,
    OrganizationConsoleModulePolicy,
    OrganizationPermissionCeiling,
    Role,
    RolePermission,
)
from apps.organizations.models import (
    MembershipStatus,
    MembershipType,
    Organization,
    OrganizationMembership,
    OrganizationStatus,
)

PlatformUser = get_user_model()


class AccessControlError(Exception):
    """Base domain exception for access control services."""

    def __init__(self, message: str, code: str = "ACCESS_CONTROL_ERROR"):
        super().__init__(message)
        self.message = message
        self.code = code


class InsufficientPrivilegesError(AccessControlError):
    def __init__(self, message: str = "Actor lacks required privileges.", code: str = "INSUFFICIENT_PRIVILEGES"):
        super().__init__(message, code=code)


class OrganizationNotActiveError(AccessControlError):
    def __init__(self, message: str = "Target organization is not active.", code: str = "ORGANIZATION_NOT_ACTIVE"):
        super().__init__(message, code=code)


class MembershipNotActiveError(AccessControlError):
    def __init__(self, message: str = "Actor membership is not active.", code: str = "MEMBERSHIP_NOT_ACTIVE"):
        super().__init__(message, code=code)


class RoleNotFoundError(AccessControlError):
    def __init__(self, message: str = "Role not found.", code: str = "ROLE_NOT_FOUND"):
        super().__init__(message, code=code)


class RoleAlreadyExistsError(AccessControlError):
    def __init__(self, message: str = "A role with this code already exists in the organization.", code: str = "ROLE_ALREADY_EXISTS"):
        super().__init__(message, code=code)


class SystemRoleImmutableError(AccessControlError):
    def __init__(self, message: str = "System roles are immutable and cannot be modified or retired.", code: str = "SYSTEM_ROLE_IMMUTABLE"):
        super().__init__(message, code=code)


class RoleRetiredError(AccessControlError):
    def __init__(self, message: str = "Retired roles cannot be modified or assigned.", code: str = "ROLE_RETIRED"):
        super().__init__(message, code=code)


class RoleInUseError(AccessControlError):
    def __init__(self, message: str = "Role is currently assigned to one or more memberships and cannot be retired.", code: str = "ROLE_IN_USE"):
        super().__init__(message, code=code)


class RoleNotAssignableToMemberError(AccessControlError):
    def __init__(self, message: str = "Roles can only be assigned to tenant administrators.", code: str = "ROLE_NOT_ASSIGNABLE_TO_MEMBER"):
        super().__init__(message, code=code)


class PermissionNotFoundError(AccessControlError):
    def __init__(self, message: str = "Permission not found or inactive.", code: str = "PERMISSION_NOT_FOUND"):
        super().__init__(message, code=code)


class PermissionOutsideCeilingError(AccessControlError):
    def __init__(self, message: str = "Requested permission is outside the organization ceiling.", code: str = "PERMISSION_OUTSIDE_CEILING"):
        super().__init__(message, code=code)


class ModuleNotFoundError(AccessControlError):
    def __init__(self, message: str = "Console module not found or inactive.", code: str = "MODULE_NOT_FOUND"):
        super().__init__(message, code=code)


class ModuleCannotBeDisabledError(AccessControlError):
    def __init__(self, message: str = "Core modules cannot be disabled.", code: str = "MODULE_CANNOT_BE_DISABLED"):
        super().__init__(message, code=code)


class ModuleDisabledError(AccessControlError):
    def __init__(self, message: str = "Console module is disabled for this organization.", code: str = "MODULE_DISABLED"):
        super().__init__(message, code=code)


class LastAdminProtectionError(AccessControlError):
    def __init__(
        self,
        message: str = "Operation rejected: organization must have at least one capable active tenant administrator.",
        code: str = "LAST_ADMIN_PROTECTION",
    ):
        super().__init__(message, code=code)


class AccessControlValidationError(AccessControlError):
    def __init__(self, message: str, code: str = "VALIDATION_ERROR"):
        super().__init__(message, code=code)


def validate_platform_owner_actor(actor: Any) -> None:
    """Validate that actor is an authenticated, active Platform Owner."""
    if not actor or not getattr(actor, "is_authenticated", False) or not getattr(actor, "is_active", False):
        raise InsufficientPrivilegesError("Actor must be an active, authenticated platform user.")
    if getattr(actor, "status", None) != "active":
        raise InsufficientPrivilegesError("Actor status must be active.")
    if not getattr(actor, "is_platform_owner", False):
        raise InsufficientPrivilegesError("Actor must possess Platform Owner privileges.")


def validate_tenant_admin_actor(
    actor: Any, organization_id: uuid.UUID | str
) -> OrganizationMembership:
    """Validate that actor is an active Tenant Administrator in target organization."""
    if not actor or not getattr(actor, "is_authenticated", False) or not getattr(actor, "is_active", False):
        raise InsufficientPrivilegesError("Actor must be an active, authenticated platform user.")
    if getattr(actor, "status", None) != "active":
        raise InsufficientPrivilegesError("Actor status must be active.")

    org = Organization.objects.filter(id=organization_id).first()
    if not org or org.status != OrganizationStatus.ACTIVE:
        raise OrganizationNotActiveError("Target organization does not exist or is not active.")

    membership = (
        OrganizationMembership.objects.filter(
            organization_id=organization_id,
            user=actor,
            membership_type=MembershipType.TENANT_ADMIN,
            status=MembershipStatus.ACTIVE,
        )
        .select_related("role")
        .first()
    )
    if not membership:
        raise InsufficientPrivilegesError(
            "Actor must hold an active tenant administrator membership in the target organization."
        )

    if not membership.role or membership.role.status != "active":
        raise InsufficientPrivilegesError(
            "Actor's administrative role is not active."
        )

    return membership


def calculate_actor_effective_permissions(
    actor: Any, organization_id: uuid.UUID | str
) -> set[str]:
    """Calculate the actor's current transactional effective permissions in an organization."""
    validate_tenant_admin_actor(actor, organization_id)
    from apps.access_control.services.evaluation import evaluate_access

    result = evaluate_access(actor, "tenant", organization_id)
    return set(result.effective_permissions)


def require_actor_permission(
    actor: Any, organization_id: uuid.UUID | str, required_permission: str
) -> None:
    """Verify actor currently holds the required effective permission."""
    effective = calculate_actor_effective_permissions(actor, organization_id)
    if required_permission not in effective:
        raise InsufficientPrivilegesError(
            f"Actor lacks required effective permission '{required_permission}' in target organization."
        )


def validate_permission_dependencies(permission_keys: Iterable[str]) -> list[str]:
    """Validate locked Phase 2E permission dependencies and return deterministically sorted keys."""
    keys_set = set(permission_keys)
    if "roles.manage" in keys_set and "roles.view" not in keys_set:
        raise AccessControlValidationError(
            "roles.manage requires roles.view to be granted.",
            code="VALIDATION_ERROR",
        )
    if "roles.assign" in keys_set and "roles.view" not in keys_set:
        raise AccessControlValidationError(
            "roles.assign requires roles.view to be granted.",
            code="VALIDATION_ERROR",
        )
    return sorted(keys_set)


def lock_organization_and_tenant_admins(
    organization_id: uuid.UUID | str,
) -> tuple[Organization, list[OrganizationMembership]]:
    """Pessimistically lock Organization and all its tenant_admin memberships in global order.

    Lock order:
    1. Organization rows ordered by ID.
    2. All tenant_admin membership rows for affected organizations ordered by ID.
    3. Relevant Role rows ordered by ID.
    4. Relevant RolePermission rows ordered by ID.
    5. PlatformUser rows where required by identity lifecycle operations.
    """
    clean_org_id = uuid.UUID(str(organization_id)) if not isinstance(organization_id, uuid.UUID) else organization_id
    org = Organization.objects.select_for_update().filter(id=clean_org_id).first()
    if not org:
        raise OrganizationNotActiveError("Organization not found.", code="ORGANIZATION_NOT_ACTIVE")

    # 2. Lock all tenant_admin memberships (active, suspended, ended) in deterministic ID order
    tenant_admins = list(
        OrganizationMembership.objects.select_for_update()
        .filter(organization_id=clean_org_id, membership_type=MembershipType.TENANT_ADMIN)
        .order_by("id")
    )

    # 3. Relevant Role rows ordered by ID
    role_ids = {m.role_id for m in tenant_admins if m.role_id}
    roles = list(Role.objects.select_for_update().filter(id__in=role_ids).order_by("id"))
    roles_by_id = {r.id: r for r in roles}

    # 4. Relevant RolePermission rows ordered by ID
    if role_ids:
        list(RolePermission.objects.select_for_update().filter(role_id__in=role_ids).order_by("id"))

    # 5. PlatformUser rows where required
    user_ids = {m.user_id for m in tenant_admins}
    users = list(PlatformUser.objects.select_for_update().filter(id__in=user_ids).order_by("id"))
    users_by_id = {u.id: u for u in users}

    # Attach loaded models in memory to avoid extra queries or outer-join FOR UPDATE
    for m in tenant_admins:
        m.organization = org
        if m.role_id:
            m.role = roles_by_id.get(m.role_id)
        m.user = users_by_id.get(m.user_id)

    return org, tenant_admins


def evaluate_structural_last_admin(
    *,
    organization_id: uuid.UUID | str,
    suspended_membership_id: uuid.UUID | str | None = None,
    ended_membership_id: uuid.UUID | str | None = None,
    downgraded_membership_id: uuid.UUID | str | None = None,
    reassigned_membership_id: uuid.UUID | str | None = None,
    new_role: Role | None = None,
    modified_role_id: uuid.UUID | str | None = None,
    new_permission_keys: Iterable[str] | None = None,
    retired_role_id: uuid.UUID | str | None = None,
    suspended_user_id: uuid.UUID | str | None = None,
    disabled_user_id: uuid.UUID | str | None = None,
    locked_tenant_admins: list[OrganizationMembership] | None = None,
) -> None:
    """Evaluate structural last-admin invariant under projected mutation state.

    A capable administrator requires all of:
    - PlatformUser.status == "active"
    - PlatformUser.is_active == True
    - OrganizationMembership.status == "active"
    - OrganizationMembership.membership_type == "tenant_admin"
    - assigned Role is non-null
    - assigned Role.status == "active"
    - assigned role contains both roles.manage and roles.assign
    """
    clean_org_id = uuid.UUID(str(organization_id)) if not isinstance(organization_id, uuid.UUID) else organization_id
    if locked_tenant_admins is not None:
        memberships = locked_tenant_admins
    else:
        memberships = list(
            OrganizationMembership.objects.select_for_update()
            .filter(organization_id=clean_org_id, membership_type=MembershipType.TENANT_ADMIN)
            .order_by("id")
        )
        role_ids = {m.role_id for m in memberships if m.role_id}
        if new_role and new_role.id:
            role_ids.add(new_role.id)
        roles = list(Role.objects.select_for_update().filter(id__in=role_ids).order_by("id"))
        roles_by_id = {r.id: r for r in roles}
        if role_ids:
            list(RolePermission.objects.select_for_update().filter(role_id__in=role_ids).order_by("id"))
        user_ids = {m.user_id for m in memberships}
        users = list(PlatformUser.objects.select_for_update().filter(id__in=user_ids).order_by("id"))
        users_by_id = {u.id: u for u in users}
        for m in memberships:
            if m.role_id:
                m.role = roles_by_id.get(m.role_id)
            m.user = users_by_id.get(m.user_id)

    # Gather all roles involved
    role_ids = {m.role_id for m in memberships if m.role_id}
    if new_role and new_role.id:
        role_ids.add(new_role.id)

    # Map role_id to active granted permission keys
    role_perms_map: dict[uuid.UUID, set[str]] = {}
    if role_ids:
        for rp in (
            RolePermission.objects.filter(role_id__in=role_ids)
            .select_related("permission")
            .filter(permission__is_active=True)
        ):
            role_perms_map.setdefault(rp.role_id, set()).add(rp.permission_id)

    str_suspended_mem = str(suspended_membership_id) if suspended_membership_id else None
    str_ended_mem = str(ended_membership_id) if ended_membership_id else None
    str_downgraded_mem = str(downgraded_membership_id) if downgraded_membership_id else None
    str_reassigned_mem = str(reassigned_membership_id) if reassigned_membership_id else None
    str_modified_role = str(modified_role_id) if modified_role_id else None
    str_retired_role = str(retired_role_id) if retired_role_id else None
    str_suspended_user = str(suspended_user_id) if suspended_user_id else None
    str_disabled_user = str(disabled_user_id) if disabled_user_id else None
    projected_new_perms = set(new_permission_keys) if new_permission_keys is not None else None

    capable_count = 0

    for mem in memberships:
        mid_str = str(mem.id)

        # Projected status / type
        if mid_str == str_suspended_mem:
            continue
        if mid_str == str_ended_mem:
            continue
        if mid_str == str_downgraded_mem:
            continue
        if mem.status != MembershipStatus.ACTIVE:
            continue

        # User status
        uid_str = str(mem.user_id)
        if uid_str == str_suspended_user or uid_str == str_disabled_user:
            continue
        if mem.user.status != "active" or not mem.user.is_active:
            continue

        # Assigned role
        if mid_str == str_reassigned_mem:
            role = new_role
        else:
            role = mem.role

        if not role:
            continue
        if str(role.id) == str_retired_role:
            continue
        if role.status != "active":
            continue

        # Assigned role permissions
        if str(role.id) == str_modified_role and projected_new_perms is not None:
            perms = projected_new_perms
        else:
            perms = role_perms_map.get(role.id, set())

        if "roles.manage" in perms and "roles.assign" in perms:
            capable_count += 1

    if capable_count == 0:
        raise LastAdminProtectionError(
            "Operation rejected: organization must have at least one capable active tenant administrator.",
            code="LAST_ADMIN_PROTECTION",
        )
