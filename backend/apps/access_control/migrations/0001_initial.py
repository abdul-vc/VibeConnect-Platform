# Generated for VibeConnect Phase 2E — Stage 1

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models
import uuid


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("identity", "0003_login_attempt"),
        ("organizations", "0002_organization_membership"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ConsoleModule",
            fields=[
                (
                    "key",
                    models.CharField(
                        help_text="Canonical unique identifier for the console module.",
                        max_length=100,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "display_name",
                    models.CharField(
                        help_text="Human-readable title of the console module.",
                        max_length=150,
                    ),
                ),
                (
                    "description",
                    models.TextField(
                        blank=True,
                        help_text="Functional description of the module.",
                    ),
                ),
                (
                    "target_context",
                    models.CharField(
                        choices=[
                            ("platform_owner", "Platform Owner"),
                            ("tenant", "Tenant"),
                        ],
                        help_text="Target console context (platform_owner or tenant).",
                        max_length=50,
                    ),
                ),
                (
                    "is_core",
                    models.BooleanField(
                        default=False,
                        help_text="True if this module is essential and cannot be disabled.",
                    ),
                ),
                (
                    "is_active",
                    models.BooleanField(
                        default=True,
                        help_text="Global administrative lifecycle status of the module.",
                    ),
                ),
                (
                    "sort_order",
                    models.PositiveIntegerField(
                        default=0,
                        help_text="Display ordering for navigation.",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "db_table": "console_modules",
                "ordering": ["sort_order", "key"],
                "constraints": [
                    models.CheckConstraint(
                        condition=models.Q(
                            target_context__in=["platform_owner", "tenant"]
                        ),
                        name="console_module_valid_context",
                    ),
                    models.CheckConstraint(
                        condition=~models.Q(is_core=True, is_active=False),
                        name="core_module_cannot_be_inactive",
                    ),
                ],
            },
        ),
        migrations.CreateModel(
            name="AccessPermission",
            fields=[
                (
                    "key",
                    models.CharField(
                        help_text="Dot-separated permission key (e.g. roles.view).",
                        max_length=100,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "display_name",
                    models.CharField(
                        help_text="Human-readable display name.",
                        max_length=150,
                    ),
                ),
                (
                    "description",
                    models.TextField(
                        blank=True,
                        help_text="Functional description of capability granted.",
                    ),
                ),
                (
                    "category",
                    models.CharField(
                        db_index=True,
                        help_text="Logical grouping category (e.g. roles).",
                        max_length=50,
                    ),
                ),
                (
                    "is_active",
                    models.BooleanField(
                        default=True,
                        help_text="System-wide active status.",
                    ),
                ),
                (
                    "sort_order",
                    models.PositiveIntegerField(
                        default=0,
                        help_text="Display ordering.",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "console_module",
                    models.ForeignKey(
                        help_text="Console module governing this permission.",
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="permissions",
                        to="access_control.consolemodule",
                    ),
                ),
            ],
            options={
                "db_table": "access_permissions",
                "ordering": ["sort_order", "key"],
            },
        ),
        migrations.CreateModel(
            name="Role",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        help_text="Globally unique identifier for the role.",
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "code",
                    models.CharField(
                        db_index=True,
                        help_text="Immutable lowercase alphanumeric code with single underscores.",
                        max_length=64,
                    ),
                ),
                (
                    "name",
                    models.CharField(
                        help_text="Editable display name for the role.",
                        max_length=100,
                    ),
                ),
                (
                    "description",
                    models.TextField(
                        blank=True,
                        help_text="Functional summary of role duties.",
                    ),
                ),
                (
                    "is_system_role",
                    models.BooleanField(
                        default=False,
                        help_text="True if this is an immutable platform-defined system role.",
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[("active", "Active"), ("retired", "Retired")],
                        default="active",
                        help_text="Lifecycle state (active or retired).",
                        max_length=20,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        help_text="Platform user who created this custom role.",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "organization",
                    models.ForeignKey(
                        blank=True,
                        help_text="Owning organization for custom roles. Null for system roles.",
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="roles",
                        to="organizations.organization",
                    ),
                ),
                (
                    "updated_by",
                    models.ForeignKey(
                        blank=True,
                        help_text="Platform user who last updated this custom role.",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "db_table": "organization_roles",
                "ordering": ["-created_at"],
                "constraints": [
                    models.CheckConstraint(
                        condition=models.Q(
                            code__regex="^[a-z0-9]+(?:_[a-z0-9]+)*$"
                        ),
                        name="role_code_format",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(status__in=["active", "retired"]),
                        name="role_valid_status",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(
                            models.Q(
                                ("is_system_role", True),
                                ("organization__isnull", True),
                            ),
                            models.Q(
                                ("is_system_role", False),
                                ("organization__isnull", False),
                            ),
                            _connector="OR",
                        ),
                        name="role_system_or_custom_org_scope",
                    ),
                    models.UniqueConstraint(
                        fields=("organization", "code"),
                        name="unique_custom_role_code_per_org",
                    ),
                    models.UniqueConstraint(
                        condition=models.Q(("is_system_role", True)),
                        fields=("code",),
                        name="unique_system_role_code",
                    ),
                ],
            },
        ),
        migrations.CreateModel(
            name="RolePermission",
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
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "permission",
                    models.ForeignKey(
                        help_text="Permission granted to the role.",
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="role_permissions",
                        to="access_control.accesspermission",
                    ),
                ),
                (
                    "role",
                    models.ForeignKey(
                        help_text="Role receiving the permission.",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="role_permissions",
                        to="access_control.role",
                    ),
                ),
            ],
            options={
                "db_table": "role_permissions",
                "constraints": [
                    models.UniqueConstraint(
                        fields=("role", "permission"),
                        name="unique_role_permission",
                    )
                ],
            },
        ),
        migrations.CreateModel(
            name="OrganizationConsoleModulePolicy",
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
                    "is_enabled",
                    models.BooleanField(
                        default=False,
                        help_text="True if module is enabled for this organization.",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "console_module",
                    models.ForeignKey(
                        help_text="Target console module.",
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="organization_policies",
                        to="access_control.consolemodule",
                    ),
                ),
                (
                    "organization",
                    models.ForeignKey(
                        help_text="Organization subject to this module policy.",
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="console_module_policies",
                        to="organizations.organization",
                    ),
                ),
                (
                    "updated_by",
                    models.ForeignKey(
                        blank=True,
                        help_text="Platform Owner who last modified this ceiling.",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "db_table": "organization_console_module_policies",
                "constraints": [
                    models.UniqueConstraint(
                        fields=("organization", "console_module"),
                        name="unique_org_console_module_policy",
                    )
                ],
            },
        ),
        migrations.CreateModel(
            name="OrganizationPermissionCeiling",
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
                    "is_allowed",
                    models.BooleanField(
                        default=False,
                        help_text="True if permission is permitted for this organization.",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "organization",
                    models.ForeignKey(
                        help_text="Organization subject to this permission ceiling.",
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="permission_ceilings",
                        to="organizations.organization",
                    ),
                ),
                (
                    "permission",
                    models.ForeignKey(
                        help_text="Target control-plane permission.",
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="organization_ceilings",
                        to="access_control.accesspermission",
                    ),
                ),
                (
                    "updated_by",
                    models.ForeignKey(
                        blank=True,
                        help_text="Platform Owner who last modified this ceiling.",
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "db_table": "organization_permission_ceilings",
                "constraints": [
                    models.UniqueConstraint(
                        fields=("organization", "permission"),
                        name="unique_org_permission_ceiling",
                    )
                ],
            },
        ),
    ]
