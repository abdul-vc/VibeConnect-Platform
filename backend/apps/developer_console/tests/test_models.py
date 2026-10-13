import uuid
from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.db.models import ProtectedError
from django.test import TestCase

from apps.developer_console.models import DeveloperApiKey, DeveloperApplication
from apps.organizations.models import Organization

User = get_user_model()


class DeveloperModelTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="admin@tenant1.local",
            password="TestPassword123!",
            full_name="Admin User",
        )
        self.org = Organization.objects.create(
            code="tenant1",
            name="Tenant 1",
            created_by=self.user,
            updated_by=self.user,
        )

    def test_create_application_defaults_and_uuids(self):
        app = DeveloperApplication.objects.create(
            organization=self.org,
            name="HRMS Sync",
            description="Integration application",
            created_by=self.user,
        )
        self.assertIsInstance(app.id, uuid.UUID)
        self.assertEqual(app.status, "active")
        self.assertEqual(str(app), "HRMS Sync (tenant1)")

    def test_protect_on_organization_and_created_by(self):
        app_creator = User.objects.create_user(
            email="developer@tenant1.local",
            password="TestPassword123!",
            full_name="Developer User",
        )
        app = DeveloperApplication.objects.create(
            organization=self.org,
            name="Protected App",
            created_by=app_creator,
        )
        # Attempting to delete organization should raise ProtectedError
        with self.assertRaises(ProtectedError):
            self.org.delete()

        # Attempting to delete created_by user should raise ProtectedError due to DeveloperApplication
        with self.assertRaises(ProtectedError):
            app_creator.delete()

    def test_create_api_key_and_cascade(self):
        app = DeveloperApplication.objects.create(
            organization=self.org,
            name="Keyed App",
            created_by=self.user,
        )
        key = DeveloperApiKey.objects.create(
            application=app,
            name="Primary Live Key",
            key_prefix="vck_live_a1b2c3d4",
            hashed_secret="abc" * 10,
            scopes=["catalog:read", "organization:read"],
        )
        self.assertIsInstance(key.id, uuid.UUID)
        self.assertEqual(key.status, "active")
        self.assertIsNone(key.expires_at)
        self.assertIsNone(key.last_used_at)
        self.assertIsNone(key.revoked_at)
        self.assertIn("vck_live_a1b2c3d4", str(key))

        # Deleting app should cascade delete key
        app_id = app.id
        app.delete()
        self.assertFalse(DeveloperApiKey.objects.filter(application_id=app_id).exists())

    def test_unique_key_prefix_constraint(self):
        app = DeveloperApplication.objects.create(
            organization=self.org,
            name="App With Keys",
            created_by=self.user,
        )
        DeveloperApiKey.objects.create(
            application=app,
            name="Key 1",
            key_prefix="vck_live_11223344",
            hashed_secret="secret1",
        )
        with self.assertRaises(IntegrityError):
            DeveloperApiKey.objects.create(
                application=app,
                name="Key 2",
                key_prefix="vck_live_11223344",
                hashed_secret="secret2",
            )
