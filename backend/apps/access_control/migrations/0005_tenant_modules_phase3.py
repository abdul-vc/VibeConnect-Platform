# Generated for VibeConnect Phase 3 Authorization & Notifications
# Data migration bootstrapping:
# - tenant_notifications (notifications.view)
# - access_requests.decide under tenant_access_requests
# Granting them to system_tenant_admin and backfilling module policies
# and permission ceilings for existing organizations.

from django.db import migrations


MODULES_DATA = [
    {
        "key": "tenant_notifications",
        "display_name": "Notifications & Alerts",
        "description": "View delivered organization notifications, alerts, and communication logs.",
        "target_context": "tenant",
        "is_core": False,
        "is_active": True,
        "sort_order": 45,
        "permissions": [
            {
                "key": "notifications.view",
                "display_name": "View Notifications",
                "description": "View notification delivery logs and alert history.",
                "category": "notifications",
                "sort_order": 10,
            }
        ],
    },
]

EXTRA_PERMISSIONS = [
    {
        "module_key": "tenant_access_requests",
        "key": "access_requests.decide",
        "display_name": "Decide Access Requests",
        "description": "Approve or deny user product access requests.",
        "category": "access_requests",
        "sort_order": 25,
    },
]


def bootstrap_tenant_modules_phase3(apps, schema_editor):
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

    for p_info in EXTRA_PERMISSIONS:
        try:
            parent_mod = ConsoleModule.objects.get(key=p_info["module_key"])
        except ConsoleModule.DoesNotExist:
            continue

        perm, _ = AccessPermission.objects.update_or_create(
            key=p_info["key"],
            defaults={
                "console_module": parent_mod,
                "display_name": p_info["display_name"],
                "description": p_info["description"],
                "category": p_info["category"],
                "is_active": True,
                "sort_order": p_info["sort_order"],
            },
        )
        if system_role:
            RolePermission.objects.get_or_create(role=system_role, permission=perm)

        for org in Organization.objects.all():
            OrganizationPermissionCeiling.objects.get_or_create(
                organization=org,
                permission=perm,
                defaults={"is_allowed": True, "updated_by": None},
            )


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("access_control", "0004_tenant_modules_2g"),
        ("organizations", "0002_organization_membership"),
    ]

    operations = [
        migrations.RunPython(
            bootstrap_tenant_modules_phase3,
            reverse_code=noop_reverse,
        ),
    ]
