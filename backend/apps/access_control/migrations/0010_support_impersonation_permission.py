# Generated for VibeConnect Phase 6D-1: Support Impersonation Permission Foundation
from django.db import migrations


def bootstrap_impersonation_permission(apps, schema_editor):
    ConsoleModule = apps.get_model("access_control", "ConsoleModule")
    AccessPermission = apps.get_model("access_control", "AccessPermission")
    Role = apps.get_model("access_control", "Role")
    RolePermission = apps.get_model("access_control", "RolePermission")

    module = ConsoleModule.objects.filter(key="support_console").first()
    if not module:
        return

    perm, _ = AccessPermission.objects.update_or_create(
        key="support.impersonation.initiate",
        defaults={
            "console_module": module,
            "display_name": "Initiate Support Impersonation",
            "description": "Initiate time-limited, audited impersonation sessions for tenant support.",
            "category": "support",
            "sort_order": 40,
            "is_active": True,
        },
    )

    support_op_role = Role.objects.filter(code="support_operator", is_system_role=True).first()
    if support_op_role:
        RolePermission.objects.get_or_create(role=support_op_role, permission=perm)


def revert_impersonation_permission(apps, schema_editor):
    AccessPermission = apps.get_model("access_control", "AccessPermission")
    RolePermission = apps.get_model("access_control", "RolePermission")

    perm = AccessPermission.objects.filter(key="support.impersonation.initiate").first()
    if perm:
        RolePermission.objects.filter(permission=perm).delete()
        perm.delete()


class Migration(migrations.Migration):

    dependencies = [
        ("access_control", "0009_support_authorization_foundation"),
    ]

    operations = [
        migrations.RunPython(
            bootstrap_impersonation_permission,
            revert_impersonation_permission,
        ),
    ]
