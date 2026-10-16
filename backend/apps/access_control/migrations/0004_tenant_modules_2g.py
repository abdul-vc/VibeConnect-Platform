# Generated for VibeConnect Phase 2G
# Data migration bootstrapping tenant console modules and permissions:
# - tenant_my_products (products.view)
# - tenant_bulk_import (bulk_import.view, bulk_import.manage)
# - tenant_access_requests (access_requests.view, access_requests.manage)
# Granting them to system_tenant_admin and backfilling module policies
# and permission ceilings for existing organizations.

from django.db import migrations


MODULES_DATA = [
    {
        "key": "tenant_my_products",
        "display_name": "My Products & Launcher",
        "description": "View entitled products, active modules, and launch authorized applications.",
        "target_context": "tenant",
        "is_core": False,
        "is_active": True,
        "sort_order": 15,
        "permissions": [
            {
                "key": "products.view",
                "display_name": "View My Products",
                "description": "View entitled products, access states, and application launcher.",
                "category": "products",
                "sort_order": 10,
            }
        ],
    },
    {
        "key": "tenant_bulk_import",
        "display_name": "Bulk User Onboarding",
        "description": "Batch import and invite organization users and assign memberships.",
        "target_context": "tenant",
        "is_core": False,
        "is_active": True,
        "sort_order": 25,
        "permissions": [
            {
                "key": "bulk_import.view",
                "display_name": "View Bulk Import Jobs",
                "description": "View bulk onboarding jobs, validation states, and reconciliation reports.",
                "category": "bulk_import",
                "sort_order": 10,
            },
            {
                "key": "bulk_import.manage",
                "display_name": "Manage Bulk Import Jobs",
                "description": "Upload CSV/Excel user lists, trigger validation, commit, and retry jobs.",
                "category": "bulk_import",
                "sort_order": 20,
            },
        ],
    },
    {
        "key": "tenant_access_requests",
        "display_name": "Access Requests & Approvals",
        "description": "Review and decide user product access requests.",
        "target_context": "tenant",
        "is_core": False,
        "is_active": True,
        "sort_order": 35,
        "permissions": [
            {
                "key": "access_requests.view",
                "display_name": "View Access Requests",
                "description": "View pending and historical access requests and decisions.",
                "category": "access_requests",
                "sort_order": 10,
            },
            {
                "key": "access_requests.manage",
                "display_name": "Manage Access Requests",
                "description": "Approve, deny, or escalate user access requests.",
                "category": "access_requests",
                "sort_order": 20,
            },
        ],
    },
]


def bootstrap_tenant_modules_2g(apps, schema_editor):
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

    system_role = Role.objects.filter(code="system_tenant_admin", is_system_role=True).first()

    for mod_info in MODULES_DATA:
        module, _ = ConsoleModule.objects.update_or_create(
            key=mod_info["key"],
            defaults={
                "display_name": mod_info["display_name"],
                "description": mod_info["description"],
                "target_context": mod_info["target_context"],
                "is_core": mod_info["is_core"],
                "is_active": mod_info["is_active"],
                "sort_order": mod_info["sort_order"],
            },
        )

        created_perms = []
        for p_info in mod_info["permissions"]:
            perm, _ = AccessPermission.objects.update_or_create(
                key=p_info["key"],
                defaults={
                    "console_module": module,
                    "display_name": p_info["display_name"],
                    "description": p_info["description"],
                    "category": p_info["category"],
                    "is_active": True,
                    "sort_order": p_info["sort_order"],
                },
            )
            created_perms.append(perm)
            if system_role:
                RolePermission.objects.get_or_create(role=system_role, permission=perm)

        for org in Organization.objects.all():
            OrganizationConsoleModulePolicy.objects.get_or_create(
                organization=org,
                console_module=module,
                defaults={"is_enabled": True, "updated_by": None},
            )
            for perm in created_perms:
                OrganizationPermissionCeiling.objects.get_or_create(
                    organization=org,
                    permission=perm,
                    defaults={"is_allowed": True, "updated_by": None},
                )


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("access_control", "0003_assignments_module_and_permissions"),
        ("organizations", "0002_organization_membership"),
    ]

    operations = [
        migrations.RunPython(
            bootstrap_tenant_modules_2g,
            reverse_code=noop_reverse,
        ),
    ]
