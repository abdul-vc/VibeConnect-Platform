# Generated for VibeConnect Phase 6C: Synchronize ConsoleModule.target_context choices
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("access_control", "0010_support_impersonation_permission"),
    ]

    operations = [
        migrations.AlterField(
            model_name="consolemodule",
            name="target_context",
            field=models.CharField(
                choices=[
                    ("platform_owner", "Platform Owner"),
                    ("tenant", "Tenant"),
                    ("support", "Support"),
                ],
                help_text="Target console context (platform_owner or tenant).",
                max_length=50,
            ),
        ),
    ]
