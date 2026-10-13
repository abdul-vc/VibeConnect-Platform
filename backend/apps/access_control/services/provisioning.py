"""Organization default access control provisioning."""

from typing import Any

from apps.access_control.models import (
    AccessPermission,
    ConsoleModule,
    OrganizationConsoleModulePolicy,
    OrganizationPermissionCeiling,
)
from apps.access_control.services.guards import AccessControlValidationError
from apps.organizations.models import Organization

REQUIRED_TENANT_MODULE_KEYS = (
    "tenant_landing",
    "tenant_my_products",
    "tenant_roles",
)
REQUIRED_PERMISSION_KEYS = (
    "roles.view",
    "roles.manage",
    "roles.assign",
    "products.view",
)


def provision_organization_defaults(*, organization: Organization, actor: Any) -> None:
    """Idempotently seed default tenant module policies and permission ceilings for a newly created organization.

    Must be called from an existing surrounding transaction.
    Does not emit separate audit events; ORGANIZATION_CREATED remains the single creation event.
    """
    modules = {
        m.key: m
        for m in ConsoleModule.objects.filter(key__in=REQUIRED_TENANT_MODULE_KEYS, is_active=True)
    }
    for mod_key in REQUIRED_TENANT_MODULE_KEYS:
        if mod_key not in modules:
            raise AccessControlValidationError(
                f"Required console module '{mod_key}' is missing from the registry.",
                code="VALIDATION_ERROR",
            )

    permissions = {
        p.key: p
        for p in AccessPermission.objects.filter(key__in=REQUIRED_PERMISSION_KEYS, is_active=True)
    }
    for perm_key in REQUIRED_PERMISSION_KEYS:
        if perm_key not in permissions:
            raise AccessControlValidationError(
                f"Required access permission '{perm_key}' is missing from the registry.",
                code="VALIDATION_ERROR",
            )

    # 1. Module policies
    for mod_key in REQUIRED_TENANT_MODULE_KEYS:
        OrganizationConsoleModulePolicy.objects.get_or_create(
            organization=organization,
            console_module=modules[mod_key],
            defaults={"is_enabled": True, "updated_by": actor},
        )

    # 2. Permission ceilings
    for perm_key in REQUIRED_PERMISSION_KEYS:
        OrganizationPermissionCeiling.objects.get_or_create(
            organization=organization,
            permission=permissions[perm_key],
            defaults={"is_allowed": True, "updated_by": actor},
        )
