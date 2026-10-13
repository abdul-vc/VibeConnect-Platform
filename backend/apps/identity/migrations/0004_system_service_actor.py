# Generated for VibeConnect Phase 2F Part D
# Data migration creating the locked system service actor.

from django.contrib.auth.hashers import make_password
from django.db import migrations


def seed_system_service_actor(apps, schema_editor):
    PlatformUser = apps.get_model("identity", "PlatformUser")
    email = "system@vibeconnect.internal"

    user, created = PlatformUser.objects.get_or_create(
        email=email,
        defaults={
            "full_name": "VibeConnect System Engine",
            "status": "active",
            "is_active": True,
            "is_staff": True,
            "is_platform_owner": True,
            "is_superuser": False,
            "password": make_password(None),
        },
    )
    if not created:
        user.full_name = "VibeConnect System Engine"
        user.status = "active"
        user.is_active = True
        user.is_staff = True
        user.is_platform_owner = True
        user.is_superuser = False
        user.password = make_password(None)
        user.save(
            update_fields=[
                "full_name",
                "status",
                "is_active",
                "is_staff",
                "is_platform_owner",
                "is_superuser",
                "password",
            ]
        )
    else:
        user.password = make_password(None)
        user.save(update_fields=["password"])


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("identity", "0003_login_attempt"),
    ]

    operations = [
        migrations.RunPython(
            seed_system_service_actor,
            reverse_code=noop_reverse,
        ),
    ]
