# Generated for VibeConnect Phase 2E — Stage 1
# Adds nullable role FK to OrganizationMembership, backfills all tenant_admin rows
# with system_tenant_admin, and adds membership_type_role_sync constraint.

import django.db.models.deletion
from django.db import migrations, models


def backfill_tenant_admin_roles(apps, schema_editor):
    Role = apps.get_model("access_control", "Role")
    OrganizationMembership = apps.get_model(
        "organizations", "OrganizationMembership"
    )

    system_role = Role.objects.filter(
        code="system_tenant_admin", is_system_role=True
    ).first()
    if not system_role:
        raise RuntimeError(
            "Required system role 'system_tenant_admin' not found for backfill."
        )

    # Backfill every tenant_admin with explicit system_tenant_admin role
    OrganizationMembership.objects.filter(
        membership_type="tenant_admin"
    ).update(role=system_role)

    # Ensure all member rows have role = None
    OrganizationMembership.objects.filter(membership_type="member").update(
        role=None
    )


def reverse_backfill(apps, schema_editor):
    OrganizationMembership = apps.get_model(
        "organizations", "OrganizationMembership"
    )
    OrganizationMembership.objects.update(role=None)


class Migration(migrations.Migration):

    dependencies = [
        ("organizations", "0002_organization_membership"),
        ("access_control", "0002_bootstrap_access_control"),
    ]

    operations = [
        migrations.AddField(
            model_name="organizationmembership",
            name="role",
            field=models.ForeignKey(
                blank=True,
                help_text="Explicitly assigned administrative role. Null for regular members.",
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="memberships",
                to="access_control.role",
            ),
        ),
        migrations.RunPython(
            backfill_tenant_admin_roles,
            reverse_code=reverse_backfill,
        ),
        migrations.AddConstraint(
            model_name="organizationmembership",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(
                        ("membership_type", "tenant_admin"),
                        ("role__isnull", False),
                    ),
                    models.Q(
                        ("membership_type", "member"),
                        ("role__isnull", True),
                    ),
                    _connector="OR",
                ),
                name="membership_type_role_sync",
            ),
        ),
    ]
