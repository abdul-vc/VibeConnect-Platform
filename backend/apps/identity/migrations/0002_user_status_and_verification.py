"""
Phase 2D — PlatformUser status field, email_verified_at, and
status/is_active synchronization constraint.

Depends on auditlog.0005 so Phase 2D audit actions are present
before any service code emits them.

Backfill:
  - Existing is_active=True  → status='active'
  - Existing is_active=False → status='disabled'  (terminal; never activated)
"""

import django.db.models.functions.text
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("identity", "0001_initial"),
        ("auditlog", "0005_phase2d_audit_actions"),
    ]

    operations = [
        # 1. Add status field (nullable initially so backfill can run first)
        migrations.AddField(
            model_name="platformuser",
            name="status",
            field=models.CharField(
                blank=True,
                choices=[
                    ("active", "Active"),
                    ("suspended", "Suspended"),
                    ("disabled", "Disabled"),
                ],
                db_index=True,
                default="",
                help_text="Lifecycle state of the platform user account.",
                max_length=20,
                verbose_name="Lifecycle Status",
            ),
            preserve_default=False,
        ),
        # 2. Backfill: active users → 'active', inactive users → 'disabled'
        migrations.RunSQL(
            sql="""
                UPDATE platform_users
                SET status = CASE
                    WHEN is_active = TRUE THEN 'active'
                    ELSE 'disabled'
                END;
            """,
            reverse_sql=migrations.RunSQL.noop,
        ),
        # 3. Now apply NOT NULL + valid-values constraint
        migrations.AlterField(
            model_name="platformuser",
            name="status",
            field=models.CharField(
                choices=[
                    ("active", "Active"),
                    ("suspended", "Suspended"),
                    ("disabled", "Disabled"),
                ],
                db_index=True,
                default="active",
                help_text="Lifecycle state of the platform user account.",
                max_length=20,
                verbose_name="Lifecycle Status",
            ),
        ),
        # 4. Add email_verified_at
        migrations.AddField(
            model_name="platformuser",
            name="email_verified_at",
            field=models.DateTimeField(
                blank=True,
                help_text="Timestamp when the user email identity was verified.",
                null=True,
                verbose_name="Email Verified At",
            ),
        ),
        # 5. Add valid-status check constraint
        migrations.AddConstraint(
            model_name="platformuser",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    status__in=["active", "suspended", "disabled"]
                ),
                name="platform_user_status_valid",
            ),
        ),
        # 6. Add status/is_active synchronization constraint
        migrations.AddConstraint(
            model_name="platformuser",
            constraint=models.CheckConstraint(
                condition=(
                    (models.Q(status="active") & models.Q(is_active=True))
                    | (
                        models.Q(status__in=["suspended", "disabled"])
                        & models.Q(is_active=False)
                    )
                ),
                name="platform_user_status_is_active_sync",
            ),
        ),
    ]
