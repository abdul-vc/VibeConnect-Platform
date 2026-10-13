# Generated for VibeConnect Phase 2E — Stage 1
# Frozen data migration bootstrapping core console modules, permissions, system role,
# and initial module policies & permission ceilings for existing organizations.

from django.db import migrations


FROZEN_PO_MODULES = [
    {
        "key": "po_overview",
        "display_name": "Overview",
        "description": "Master platform overview and health metrics.",
        "target_context": "platform_owner",
        "is_core": True,
        "is_active": True,
        "sort_order": 10,
    },
    {
        "key": "po_products",
        "display_name": "Product Registry",
        "description": "Product catalog and hierarchy management.",
        "target_context": "platform_owner",
        "is_core": True,
        "is_active": True,
        "sort_order": 20,
    },
    {
        "key": "po_plans",
        "display_name": "Plans & Pricing",
        "description": "Commercial plans, versions, pricing, and packaging.",
        "target_context": "platform_owner",
        "is_core": True,
        "is_active": True,
        "sort_order": 30,
    },
    {
        "key": "po_subscriptions",
        "display_name": "Subscriptions",
        "description": "Customer organization subscriptions and billing states.",
        "target_context": "platform_owner",
        "is_core": True,
        "is_active": True,
        "sort_order": 40,
    },
    {
        "key": "po_organizations",
        "display_name": "Organization Registry",
        "description": "Tenant organization directory and lifecycle management.",
        "target_context": "platform_owner",
        "is_core": True,
        "is_active": True,
        "sort_order": 50,
    },
    {
        "key": "po_users",
        "display_name": "Central Users",
        "description": "Platform user directory and credential lifecycles.",
        "target_context": "platform_owner",
        "is_core": True,
        "is_active": True,
        "sort_order": 60,
    },
    {
        "key": "po_entitlements",
        "display_name": "Product Access",
        "description": "Organization commercial product entitlements.",
        "target_context": "platform_owner",
        "is_core": True,
        "is_active": True,
        "sort_order": 70,
    },
    {
        "key": "po_activity_log",
        "display_name": "Activity Log",
        "description": "Master immutable platform audit trail.",
        "target_context": "platform_owner",
        "is_core": True,
        "is_active": True,
        "sort_order": 80,
    },
]

FROZEN_TENANT_MODULES = [
    {
        "key": "tenant_landing",
        "display_name": "Tenant Console",
        "description": "Core tenant administration overview workspace.",
        "target_context": "tenant",
        "is_core": True,
        "is_active": True,
        "sort_order": 10,
    },
    {
        "key": "tenant_roles",
        "display_name": "Roles & Permissions",
        "description": "Organization roles, assignments, and access policies workspace.",
        "target_context": "tenant",
        "is_core": False,
        "is_active": True,
        "sort_order": 20,
    },
]

FROZEN_PERMISSIONS = [
    {
        "key": "roles.view",
        "console_module_key": "tenant_roles",
        "display_name": "View Roles & Permissions",
        "description": "View system and custom administrative roles and admin assignments.",
        "category": "roles",
        "is_active": True,
        "sort_order": 10,
    },
    {
        "key": "roles.manage",
        "console_module_key": "tenant_roles",
        "display_name": "Manage Roles",
        "description": "Create, update, and retire custom organization roles.",
        "category": "roles",
        "is_active": True,
        "sort_order": 20,
    },
    {
        "key": "roles.assign",
        "console_module_key": "tenant_roles",
        "display_name": "Assign Roles",
        "description": "Assign administrative roles to Tenant Admins.",
        "category": "roles",
        "is_active": True,
        "sort_order": 30,
    },
]


def bootstrap_access_control(apps, schema_editor):
    ConsoleModule = apps.get_model("access_control", "ConsoleModule")
    AccessPermission = apps.get_model("access_control", "AccessPermission")
    Role = apps.get_model("access_control", "Role")
    RolePermission = apps.get_model("access_control", "RolePermission")
    Organization = apps.get_model("organizations", "Organization")
    OrganizationConsoleModulePolicy = apps.get_model(
        "access_control", "OrganizationConsoleModulePolicy"
    )
    OrganizationPermissionCeiling = apps.get_model(
        "access_control", "OrganizationPermissionCeiling"
    )

    # 1. Seed Platform Owner modules
    for mod_data in FROZEN_PO_MODULES:
        ConsoleModule.objects.update_or_create(
            key=mod_data["key"],
            defaults={
                "display_name": mod_data["display_name"],
                "description": mod_data["description"],
                "target_context": mod_data["target_context"],
                "is_core": mod_data["is_core"],
                "is_active": mod_data["is_active"],
                "sort_order": mod_data["sort_order"],
            },
        )

    # 2. Seed Tenant modules
    tenant_modules = {}
    for mod_data in FROZEN_TENANT_MODULES:
        mod, _ = ConsoleModule.objects.update_or_create(
            key=mod_data["key"],
            defaults={
                "display_name": mod_data["display_name"],
                "description": mod_data["description"],
                "target_context": mod_data["target_context"],
                "is_core": mod_data["is_core"],
                "is_active": mod_data["is_active"],
                "sort_order": mod_data["sort_order"],
            },
        )
        tenant_modules[mod.key] = mod

    # 3. Seed Permissions
    permissions = {}
    for perm_data in FROZEN_PERMISSIONS:
        perm, _ = AccessPermission.objects.update_or_create(
            key=perm_data["key"],
            defaults={
                "console_module": tenant_modules[perm_data["console_module_key"]],
                "display_name": perm_data["display_name"],
                "description": perm_data["description"],
                "category": perm_data["category"],
                "is_active": perm_data["is_active"],
                "sort_order": perm_data["sort_order"],
            },
        )
        permissions[perm.key] = perm

    # 4. Seed system_tenant_admin role
    system_role, _ = Role.objects.update_or_create(
        code="system_tenant_admin",
        defaults={
            "name": "Tenant Administrator",
            "description": "System-defined full tenant administrator role.",
            "is_system_role": True,
            "organization": None,
            "status": "active",
            "created_by": None,
            "updated_by": None,
        },
    )

    # 5. Grant permissions to system_tenant_admin
    for perm in permissions.values():
        RolePermission.objects.get_or_create(
            role=system_role,
            permission=perm,
        )

    # 6. Seed policies and permission ceilings for all existing organizations
    for org in Organization.objects.all():
        # Module policies
        OrganizationConsoleModulePolicy.objects.update_or_create(
            organization=org,
            console_module=tenant_modules["tenant_landing"],
            defaults={"is_enabled": True, "updated_by": None},
        )
        OrganizationConsoleModulePolicy.objects.update_or_create(
            organization=org,
            console_module=tenant_modules["tenant_roles"],
            defaults={"is_enabled": True, "updated_by": None},
        )

        # Permission ceilings
        for perm in permissions.values():
            OrganizationPermissionCeiling.objects.update_or_create(
                organization=org,
                permission=perm,
                defaults={"is_allowed": True, "updated_by": None},
            )


def noop_reverse(apps, schema_editor):
    # Safe no-op on reverse to preserve database integrity across migration states
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("access_control", "0001_initial"),
        ("organizations", "0002_organization_membership"),
    ]

    operations = [
        migrations.RunPython(
            bootstrap_access_control,
            reverse_code=noop_reverse,
        ),
    ]
