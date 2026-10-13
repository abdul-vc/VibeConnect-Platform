# Generated for VibeConnect Phase 6D-1: Support Impersonation Session Model
import uuid
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("identity", "0004_system_service_actor"),
        ("organizations", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="SupportImpersonationSession",
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
                    "reason",
                    models.CharField(
                        help_text="Mandatory operational justification (1-500 trimmed characters).",
                        max_length=500,
                        verbose_name="Reason",
                    ),
                ),
                (
                    "ticket_reference",
                    models.CharField(
                        blank=True,
                        default="",
                        help_text="Optional external ticketing or incident reference identifier.",
                        max_length=100,
                        verbose_name="Ticket Reference",
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("active", "Active"),
                            ("expired", "Expired"),
                            ("terminated", "Terminated"),
                            ("revoked", "Revoked"),
                        ],
                        db_index=True,
                        default="active",
                        max_length=20,
                        verbose_name="Session Status",
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(auto_now_add=True, verbose_name="Created At"),
                ),
                (
                    "expires_at",
                    models.DateTimeField(
                        db_index=True,
                        help_text="Server-computed hard cap timestamp (maximum 30 minutes from creation).",
                        verbose_name="Expires At",
                    ),
                ),
                (
                    "terminated_at",
                    models.DateTimeField(
                        blank=True, null=True, verbose_name="Terminated At"
                    ),
                ),
                (
                    "correlation_id",
                    models.UUIDField(
                        db_index=True,
                        default=uuid.uuid4,
                        editable=False,
                        verbose_name="Correlation ID",
                    ),
                ),
                (
                    "operator",
                    models.ForeignKey(
                        help_text="Support operator executing the session.",
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="operated_impersonation_sessions",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Operator",
                    ),
                ),
                (
                    "target_organization",
                    models.ForeignKey(
                        help_text="Organization scope of the impersonation session.",
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="impersonation_sessions",
                        to="organizations.organization",
                        verbose_name="Target Organization",
                    ),
                ),
                (
                    "target_user",
                    models.ForeignKey(
                        help_text="Tenant Admin or Member user being impersonated.",
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="targeted_impersonation_sessions",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Target User",
                    ),
                ),
            ],
            options={
                "verbose_name": "Support Impersonation Session",
                "verbose_name_plural": "Support Impersonation Sessions",
                "db_table": "support_impersonation_sessions",
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="supportimpersonationsession",
            index=models.Index(
                fields=["operator", "status"], name="impers_operator_status_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="supportimpersonationsession",
            index=models.Index(
                fields=["target_organization", "status"], name="impers_org_status_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="supportimpersonationsession",
            index=models.Index(
                fields=["status", "expires_at"], name="impers_status_expiry_idx"
            ),
        ),
    ]
