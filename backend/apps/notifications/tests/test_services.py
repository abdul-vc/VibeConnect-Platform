"""Unit tests for Phase 3A: Notification Infrastructure & Secure Email Templates."""

from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.identity.models import UserStatus
from apps.notifications.models import (
    NotificationChannel,
    NotificationDelivery,
    NotificationDeliveryStatus,
    NotificationTemplate,
    NotificationTemplateStatus,
)
from apps.notifications.services import (
    NotificationServiceError,
    NotificationTemplateNotFoundError,
    RecipientInvalidError,
    execute_delivery,
    send,
)

PlatformUser = get_user_model()


class NotificationInfrastructureTests(TestCase):
    def setUp(self):
        self.user = PlatformUser.objects.create(
            email="recipient@example.com",
            full_name="Test Recipient",
            status=UserStatus.ACTIVE,
            is_active=True,
        )
        self.template = NotificationTemplate.objects.create(
            code="welcome_invite",
            name="Welcome Invitation",
            channel=NotificationChannel.EMAIL,
            version=1,
            subject_template="Welcome to {{ org_name }}, {{ user_name }}!",
            body_ref="emails/invitations/welcome_invite_v1.html",
            status=NotificationTemplateStatus.ACTIVE,
            is_transactional=True,
        )

    def test_successful_send(self):
        """Test sending a notification to an active recipient."""
        delivery = send(
            template_code="welcome_invite",
            recipient_user=self.user,
            context={"org_name": "Acme Corp", "user_name": "Test User"},
            execute_sync=True,
        )
        self.assertEqual(delivery.status, NotificationDeliveryStatus.SENT)
        self.assertIsNotNone(delivery.sent_at)
        self.assertEqual(delivery.retry_count, 1)
        self.assertEqual(delivery.recipient_email, "recipient@example.com")

    def test_idempotent_enqueue(self):
        """Idempotency key prevents duplicate sends for the same logical event."""
        delivery1 = send(
            template_code="welcome_invite",
            recipient_email="recipient@example.com",
            context={"event": "signup"},
            idempotency_key="unique_event_key_123",
            execute_sync=True,
        )
        delivery2 = send(
            template_code="welcome_invite",
            recipient_email="recipient@example.com",
            context={"event": "signup"},
            idempotency_key="unique_event_key_123",
            execute_sync=True,
        )
        self.assertEqual(delivery1.id, delivery2.id)
        self.assertEqual(NotificationDelivery.objects.filter(idempotency_key="unique_event_key_123").count(), 1)

    def test_retired_template_rejection(self):
        """Cannot send notifications using a retired template."""
        self.template.status = NotificationTemplateStatus.RETIRED
        self.template.save()

        with self.assertRaises(NotificationTemplateNotFoundError):
            send(
                template_code="welcome_invite",
                recipient_user=self.user,
                context={"org_name": "Acme Corp"},
            )

    def test_recipient_deactivated_fails_with_reason(self):
        """Recipient deactivated after enqueue but before delivery is marked failed with reason."""
        delivery = send(
            template_code="welcome_invite",
            recipient_user=self.user,
            context={"org_name": "Acme Corp"},
            execute_sync=False,
        )
        self.assertEqual(delivery.status, NotificationDeliveryStatus.QUEUED)

        # Deactivate recipient before transmission
        self.user.is_active = False
        self.user.status = UserStatus.DISABLED
        self.user.save()

        executed = execute_delivery(delivery.id)
        self.assertEqual(executed.status, NotificationDeliveryStatus.FAILED)
        self.assertIn("deactivated or disabled", executed.failure_reason)

    @patch("apps.notifications.services.send_mail")
    def test_retry_after_failure_and_terminal_exhaustion(self, mock_send_mail):
        """Delivery status transitions to retrying on failure, then failed upon exhausting max retries."""
        mock_send_mail.side_effect = Exception("SMTP timeout error")

        delivery = send(
            template_code="welcome_invite",
            recipient_email="recipient@example.com",
            context={"org_name": "Acme Corp"},
            idempotency_key="retry_test_key",
            max_retries=2,
            execute_sync=True,
        )
        self.assertEqual(delivery.status, NotificationDeliveryStatus.RETRYING)
        self.assertEqual(delivery.retry_count, 1)

        # Second attempt (exceeds max_retries=2)
        final_delivery = execute_delivery(delivery.id)
        self.assertEqual(final_delivery.status, NotificationDeliveryStatus.FAILED)
        self.assertEqual(final_delivery.retry_count, 2)
        self.assertIsNotNone(final_delivery.failed_at)
