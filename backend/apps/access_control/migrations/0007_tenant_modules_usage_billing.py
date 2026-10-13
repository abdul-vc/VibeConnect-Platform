# Generated for VibeConnect Phase 4C/4D Usage Metering & Billing
# Data migration bootstrapping:
# - tenant_usage (usage.view, usage.manage)
# - tenant_billing (billing.view, billing.manage)
# Granting them to system_tenant_admin and backfilling module policies
# and permission ceilings for existing organizations.

from django.db import migrations


MODULES_DATA = [
    {
        "key": "tenant_usage",
        "display_name": "Usage & Metering",
        "description": "View and monitor consumed quotas and resource metering metrics.",
        "target_context": "tenant",
        "is_core": False,
        "is_active": True,
        "sort_order": 55,
        "permissions": [
            {
                "key": "usage.view",
                "display_name": "View Usage & Quotas",
                "description": "View consumed resource metering and quota limits.",
                "category": "usage",
                "sort_order": 10,
            },
            {
                "key": "usage.manage",
                "display_name": "Manage Usage & Ingestion",
                "description": "Ingest usage events and trigger bucket aggregation.",
                "category": "usage",
                "sort_order": 20,
            },
        ],
    },
    {
        "key": "tenant_billing",
        "display_name": "Billing & Invoices",
        "description": "View invoices, tax details, and payment histories.",
        "target_context": "tenant",
        "is_core": False,
        "is_active": True,
        "sort_order": 60,
        "permissions": [
            {
                "key": "billing.view",
                "display_name": "View Billing & Invoices",
                "description": "View organization invoices, payment receipts, and tax info.",
                "category": "billing",
                "sort_order": 10,
            },
            {
                "key": "billing.manage",
                "display_name": "Manage Billing & Payments",
                "description": "Manage billing details and record payments.",
                "category": "billing",
                "sort_order": 20,
            },
        ],
    },
]


def bootstrap_tenant_modules_usage_billing(apps, schema_editor):
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
        ("access_control", "0006_tenant_modules_branding"),
        ("organizations", "0002_organization_membership"),
    ]

    operations = [
        migrations.RunPython(
            bootstrap_tenant_modules_usage_billing,
            reverse_code=noop_reverse,
        ),
    ]
