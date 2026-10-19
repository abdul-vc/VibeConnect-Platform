# Generated data migration for Phase 3A: Seed user_invitation template.

from django.db import migrations


def seed_user_invitation_template(apps, schema_editor):
    NotificationTemplate = apps.get_model("notifications", "NotificationTemplate")
    # Idempotent check: do not recreate if it exists; do not overwrite customized content
    if not NotificationTemplate.objects.filter(code="user_invitation", channel="email").exists():
        NotificationTemplate.objects.create(
            code="user_invitation",
            name="User Invitation & Password Activation",
            channel="email",
            version=1,
            subject_template="You've been invited to join {{ org_name }} on VibeConnect",
            body_ref="templates/emails/user_invitation.txt",
            status="active",
            is_transactional=True,
        )


def unseed_user_invitation_template(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("notifications", "0002_backgroundjob"),
    ]

    operations = [
        migrations.RunPython(seed_user_invitation_template, unseed_user_invitation_template),
    ]
