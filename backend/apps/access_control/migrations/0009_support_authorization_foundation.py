# Generated for VibeConnect Phase 6C-1: Support Authorization Foundation
import uuid
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


SUPPORT_MODULE_DATA = {
    "key": "support_console",
    "display_name": "Support Operations Console",
    "description": "Platform-scoped diagnostic inspection and controlled operational remediation workspace.",
    "target_context": "support",
    "is_core": True,
    "is_active": True,
    "sort_order": 90,
    "permissions": [
        {
            "key": "support.diagnostics.view",
            "display_name": "View Support Diagnostics",
            "description": "Inspect organization, connector, provisioning, and reconciliation diagnostic health.",
            "category": "support",
            "sort_order": 10,
        },
        {
            "key": "support.operations.retry",
            "display_name": "Retry Support Operations",
            "description": "Retry eligible failed integration and provisioning operations.",
            "category": "support",
            "sort_order": 20,
        },
        {
            "key": "support.operations.resolve",
            "display_name": "Resolve Support Operations",
            "description": "Resolve eligible dead-letter and reconciliation issues with mandatory reason.",
            "category": "support",
            "sort_order": 30,
        },
    ],
}

SUPPORT_ROLES = [
    {
        "code": "support_diagnostics_viewer",
        "name": "Support Diagnostics Viewer",
        "description": "Read-only access to platform diagnostic health and logs.",
        "permissions": ["support.diagnostics.view"],
    },
    {
        "code": "support_operator",
        "name": "Support Operator",
        "description": "Full support operator with diagnostic view and operational remediation capabilities.",
        "permissions": [
            "support.diagnostics.view",
            "support.operations.retry",
            "support.operations.resolve",
        ],
    },
    {
        "code": "support_remediation_operator",
        "name": "Support Remediation Operator",
        "description": "Operational remediation privileges (retry and resolve).",
        "permissions": [
            "support.operations.retry",
            "support.operations.resolve",
        ],
    },
]


def bootstrap_support_authorization(apps, schema_editor):
    ConsoleModule = apps.get_model("access_control", "ConsoleModule")
    AccessPermission = apps.get_model("access_control", "AccessPermission")
    Role = apps.get_model("access_control", "Role")
    RolePermission = apps.get_model("access_control", "RolePermission")

    module, _ = ConsoleModule.objects.update_or_create(
        key=SUPPORT_MODULE_DATA["key"],
        defaults={
            "display_name": SUPPORT_MODULE_DATA["display_name"],
            "description": SUPPORT_MODULE_DATA["description"],
            "target_context": SUPPORT_MODULE_DATA["target_context"],
            "is_core": SUPPORT_MODULE_DATA["is_core"],
            "is_active": SUPPORT_MODULE_DATA["is_active"],
            "sort_order": SUPPORT_MODULE_DATA["sort_order"],
        },
    )

    created_perms = {}
    for p_info in SUPPORT_MODULE_DATA["permissions"]:
        perm, _ = AccessPermission.objects.update_or_create(
            key=p_info["key"],
            defaults={
                "console_module": module,
                "display_name": p_info["display_name"],
                "description": p_info["description"],
                "category": p_info["category"],
                "sort_order": p_info["sort_order"],
                "is_active": True,
            },
        )
        created_perms[p_info["key"]] = perm

    for r_info in SUPPORT_ROLES:
        role, _ = Role.objects.update_or_create(
            code=r_info["code"],
            is_system_role=True,
            organization=None,
            defaults={
                "name": r_info["name"],
                "description": r_info["description"],
                "status": "active",
            },
        )
        for perm_key in r_info["permissions"]:
            perm_obj = created_perms.get(perm_key)
            if perm_obj:
                RolePermission.objects.get_or_create(
                    role=role,
                    permission=perm_obj,
                )


def reverse_support_authorization(apps, schema_editor):
    ConsoleModule = apps.get_model("access_control", "ConsoleModule")
    AccessPermission = apps.get_model("access_control", "AccessPermission")
    Role = apps.get_model("access_control", "Role")

    for r_info in SUPPORT_ROLES:
        Role.objects.filter(code=r_info["code"], is_system_role=True).delete()

    for p_info in SUPPORT_MODULE_DATA["permissions"]:
        AccessPermission.objects.filter(key=p_info["key"]).delete()

    ConsoleModule.objects.filter(key=SUPPORT_MODULE_DATA["key"]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("access_control", "0008_tenant_modules_reports"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="consolemodule",
            name="console_module_valid_context",
        ),
        migrations.AddConstraint(
            model_name="consolemodule",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    target_context__in=["platform_owner", "tenant", "support"]
                ),
                name="console_module_valid_context",
            ),
        ),
        migrations.CreateModel(
            name="PlatformRoleAssignment",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(auto_now_add=True),
                ),
                (
                    "role",
                    models.ForeignKey(
                        help_text="Platform-level role granted to the user.",
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="platform_assignments",
                        to="access_control.role",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        help_text="Platform user assigned this role.",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="platform_role_assignments",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "db_table": "platform_role_assignments",
                "constraints": [
                    models.UniqueConstraint(
                        fields=("user", "role"),
                        name="unique_platform_user_role",
                    ),
                ],
            },
        ),
        migrations.RunPython(
            bootstrap_support_authorization,
            reverse_support_authorization,
        ),
    ]
