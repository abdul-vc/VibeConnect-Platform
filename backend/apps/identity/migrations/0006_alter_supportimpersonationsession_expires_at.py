# Generated for VibeConnect Phase 6D: Add callable default for SupportImpersonationSession.expires_at
import apps.identity.models
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("identity", "0005_support_impersonation_session"),
    ]

    operations = [
        migrations.AlterField(
            model_name="supportimpersonationsession",
            name="expires_at",
            field=models.DateTimeField(
                db_index=True,
                default=apps.identity.models.compute_default_impersonation_expiry,
                help_text="Server-computed hard cap timestamp (maximum 30 minutes from creation).",
                verbose_name="Expires At",
            ),
        ),
    ]
