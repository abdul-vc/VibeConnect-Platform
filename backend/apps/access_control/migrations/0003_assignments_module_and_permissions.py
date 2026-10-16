# Generated for VibeConnect Phase 2F Part D
# Data migration bootstrapping tenant_product_assignments console module,
# assignments.view and assignments.manage permissions, granting them to system_tenant_admin,
# and backfilling module policies and permission ceilings for existing organizations.

from django.db import migrations


def bootstrap_assignment_access_control(apps, schema_editor):
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

    # 1. Seed tenant_product_assignments ConsoleModule
    module, _ = ConsoleModule.objects.update_or_create(
        key="tenant_product_assignments",
        defaults={
            "display_name": "User Product Assignments",
            "description": "Manage product seat allocations and module entitlements for organization members.",
            "target_context": "tenant",
            "is_core": False,
            "is_active": True,
            "sort_order": 30,
        },
    )

    # 2. Seed Permissions
    perm_view, _ = AccessPermission.objects.update_or_create(
        key="assignments.view",
        defaults={
            "console_module": module,
            "display_name": "View Product Assignments",
            "description": "View product assignments, module selections and quota metrics.",
            "category": "Tenant Administration",
            "is_active": True,
            "sort_order": 10,
        },
    )

    perm_manage, _ = AccessPermission.objects.update_or_create(
        key="assignments.manage",
        defaults={
            "console_module": module,
            "display_name": "Manage Product Assignments",
            "description": "Create and mutate assignments and module selections.",
            "category": "Tenant Administration",
            "is_active": True,
            "sort_order": 20,
        },
    )

    # 3. Grant both permissions to built-in system_tenant_admin role
    system_role = Role.objects.filter(code="system_tenant_admin", is_system_role=True).first()
    if system_role:
        RolePermission.objects.get_or_create(role=system_role, permission=perm_view)
        RolePermission.objects.get_or_create(role=system_role, permission=perm_manage)

    # 4. Backfill existing organizations idempotently, preserving any existing overrides
    for org in Organization.objects.all():
        OrganizationConsoleModulePolicy.objects.get_or_create(
            organization=org,
            console_module=module,
            defaults={"is_enabled": True, "updated_by": None},
        )
        OrganizationPermissionCeiling.objects.get_or_create(
            organization=org,
            permission=perm_view,
            defaults={"is_allowed": True, "updated_by": None},
        )
        OrganizationPermissionCeiling.objects.get_or_create(
            organization=org,
            permission=perm_manage,
            defaults={"is_allowed": True, "updated_by": None},
        )


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("access_control", "0002_bootstrap_access_control"),
        ("organizations", "0002_organization_membership"),
    ]

    operations = [
        migrations.RunPython(
            bootstrap_assignment_access_control,
            reverse_code=noop_reverse,
        ),
    ]
