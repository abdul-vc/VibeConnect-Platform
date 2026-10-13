"""
Phase 2D — OrganizationMembership model.

Depends on:
  - organizations.0001_initial  (Organization table)
  - identity.0002_user_status_and_verification  (PlatformUser status constraint applied)
"""

import django.db.models.deletion
import django.utils.timezone
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("organizations", "0001_initial"),
        ("identity", "0002_user_status_and_verification"),
    ]

    operations = [
        migrations.CreateModel(
            name="OrganizationMembership",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        help_text="Globally unique identifier for the membership record.",
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "organization",
                    models.ForeignKey(
                        help_text="The organization this membership belongs to.",
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="memberships",
                        to="organizations.organization",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        help_text="The platform user who holds this membership.",
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="organization_memberships",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "membership_type",
                    models.CharField(
                        choices=[
                            ("tenant_admin", "Tenant Admin"),
                            ("member", "Member"),
                        ],
                        default="member",
                        help_text="Functional role this membership grants within the organization.",
                        max_length=20,
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("active", "Active"),
                            ("suspended", "Suspended"),
                            ("ended", "Ended"),
                        ],
                        db_index=True,
                        default="active",
                        help_text="Current lifecycle state of the membership.",
                        max_length=20,
                    ),
                ),
                (
                    "joined_at",
                    models.DateTimeField(
                        help_text="Timestamp when the membership was originally created or last restored.",
                    ),
                ),
                (
                    "ended_at",
                    models.DateTimeField(
                        blank=True,
                        help_text="Timestamp when the membership was ended (terminal unless restored).",
                        null=True,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Organization Membership",
                "verbose_name_plural": "Organization Memberships",
                "db_table": "organization_memberships",
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddConstraint(
            model_name="organizationmembership",
            constraint=models.UniqueConstraint(
                fields=["organization", "user"],
                name="org_membership_user_uniq",
            ),
        ),
        migrations.AddConstraint(
            model_name="organizationmembership",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    status__in=["active", "suspended", "ended"]
                ),
                name="org_membership_status_valid",
            ),
        ),
        migrations.AddConstraint(
            model_name="organizationmembership",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    membership_type__in=["tenant_admin", "member"]
                ),
                name="org_membership_type_valid",
            ),
        ),
        migrations.AddConstraint(
            model_name="organizationmembership",
            constraint=models.CheckConstraint(
                condition=(
                    (
                        models.Q(status="ended")
                        & models.Q(ended_at__isnull=False)
                    )
                    | (
                        models.Q(status__in=["active", "suspended"])
                        & models.Q(ended_at__isnull=True)
                    )
                ),
                name="org_membership_ended_at_sync",
            ),
        ),
    ]
