"""Phase 6F Anonymization Regression Tests.

Verifies:
- Authorization: only Platform Owner can invoke anonymize_user.
- Protection: final active Platform Owner cannot be anonymized.
- Data redaction: pseudonymous email and full_name, inactive and disabled state.
- Referential integrity: UUID primary key is preserved.
- Audit recording: append-only audit event created.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.auditlog.models import AuditAction, AuditLog
from apps.identity.models import UserStatus
from apps.identity.services import (
    LastPlatformOwnerError,
    UserValidationError,
    anonymize_user,
)

User = get_user_model()


class AnonymizationTests(TestCase):
    def setUp(self):
        super().setUp()

        # Primary Owner
        self.owner1 = User.objects.create_user(
            email="owner1@vibeconnect.internal",
            password="SecurePassword123!",
            full_name="Primary Owner",
            is_active=True,
            is_platform_owner=True,
        )

        # Secondary Owner
        self.owner2 = User.objects.create_user(
            email="owner2@vibeconnect.internal",
            password="SecurePassword123!",
            full_name="Secondary Owner",
            is_active=True,
            is_platform_owner=True,
        )

        # Target regular user
        self.target_user = User.objects.create_user(
            email="target_user@example.com",
            password="SecurePassword123!",
            full_name="Target User",
            is_active=True,
            is_platform_owner=False,
        )

    def test_unauthorized_actor_cannot_anonymize(self):
        with self.assertRaises(UserValidationError):
            anonymize_user(
                user_id=self.target_user.id,
                actor=self.target_user,
                reason="GDPR Erasure request",
            )

    def test_last_active_owner_cannot_be_anonymized(self):
        # Deactivate owner2 so owner1 is the last active owner
        self.owner2.is_active = False
        self.owner2.status = UserStatus.DISABLED
        self.owner2.save(update_fields=["is_active", "status"])

        with self.assertRaises(LastPlatformOwnerError):
            anonymize_user(
                user_id=self.owner1.id,
                actor=self.owner1,
                reason="Account termination",
            )

    def test_anonymize_regular_user_success(self):
        orig_id = self.target_user.id
        anonymized = anonymize_user(
            user_id=self.target_user.id,
            actor=self.owner1,
            reason="Right to be forgotten",
        )

        self.assertEqual(anonymized.id, orig_id)
        self.assertEqual(anonymized.email, f"anonymized-{orig_id}@redacted.vibeconnect.local")
        self.assertEqual(anonymized.full_name, "Redacted User")
        self.assertEqual(anonymized.status, UserStatus.DISABLED)
        self.assertFalse(anonymized.is_active)
        self.assertFalse(anonymized.has_usable_password())

        # Verify audit log
        log = AuditLog.objects.filter(
            action=AuditAction.USER_ANONYMIZED,
            target_id=orig_id,
        ).first()
        self.assertIsNotNone(log)
        self.assertEqual(log.actor, self.owner1)
        self.assertIn("Right to be forgotten", log.metadata.get("reason", ""))

