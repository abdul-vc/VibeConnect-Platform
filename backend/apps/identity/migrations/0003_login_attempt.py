"""
Phase 2D — LoginAttempt model for immutable authentication evidence store.
"""

import django.db.models.deletion
import django.utils.timezone
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("identity", "0002_user_status_and_verification"),
    ]

    operations = [
        migrations.CreateModel(
            name="LoginAttempt",
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
                    "user",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="login_attempts",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "identifier_hash",
                    models.CharField(db_index=True, max_length=128),
                ),
                (
                    "result",
                    models.CharField(
                        choices=[("success", "Success"), ("failure", "Failure")],
                        max_length=20,
                    ),
                ),
                (
                    "failure_code",
                    models.CharField(blank=True, default="", max_length=40),
                ),
                (
                    "ip_hash",
                    models.CharField(max_length=128),
                ),
                (
                    "occurred_at",
                    models.DateTimeField(
                        db_index=True, default=django.utils.timezone.now
                    ),
                ),
            ],
            options={
                "verbose_name": "Login Attempt",
                "verbose_name_plural": "Login Attempts",
                "db_table": "login_attempts",
                "ordering": ["-occurred_at"],
                "indexes": [
                    models.Index(
                        fields=["identifier_hash", "-occurred_at"],
                        name="login_attempt_ident_idx",
                    ),
                    models.Index(
                        fields=["ip_hash", "-occurred_at"],
                        name="login_attempt_ip_idx",
                    ),
                ],
            },
        ),
    ]
