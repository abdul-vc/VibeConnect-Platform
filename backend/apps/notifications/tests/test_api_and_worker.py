"""API and Async Worker Tests for Notifications (Phase 3A & Async Workers)."""

from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from apps.notifications.models import (
    BackgroundJob,
    BackgroundJobStatus,
    NotificationChannel,
    NotificationDelivery,
    NotificationDeliveryStatus,
    NotificationTemplate,
    NotificationTemplateStatus,
)
from apps.notifications.queue import enqueue_background_job, process_next_queued_job

PlatformUser = get_user_model()


class NotificationsApiAndWorkerTests(APITestCase):
    def setUp(self):
        self.owner = PlatformUser.objects.create_user(
            email="notif_owner@vibeconnect.internal",
            password="SecurePassword123!",
            full_name="Notif Owner",
            status="active",
            is_active=True,
            is_platform_owner=True,
        )
        self.regular_user = PlatformUser.objects.create_user(
            email="regular_user@example.com",
            password="SecurePassword123!",
            full_name="Regular User",
            status="active",
            is_active=True,
            is_platform_owner=False,
        )
        self.template = NotificationTemplate.objects.create(
            code="test_alert",
            name="Test Alert",
            channel=NotificationChannel.EMAIL,
            version=1,
            subject_template="Alert for {{ user_name }}",
            body_ref="templates/alerts/test_alert.html",
            status=NotificationTemplateStatus.ACTIVE,
        )

    def test_owner_can_create_new_template_version_and_retire(self):
        """Item 1: Template new version creation and retirement."""
        self.client.force_authenticate(user=self.owner)

        # 1. New version
        resp_v2 = self.client.post(
            f"/api/v1/notifications/templates/{self.template.id}/new-version/",
            {
                "subject_template": "Updated Alert for {{ user_name }}",
                "body_ref": "templates/alerts/test_alert_v2.html",
            },
            format="json",
        )
        self.assertEqual(resp_v2.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp_v2.data["version"], 2)

        # 2. Preview
        resp_prev = self.client.post(
            f"/api/v1/notifications/templates/{self.template.id}/preview/",
            {"context": {"user_name": "Alice"}},
            format="json",
        )
        self.assertEqual(resp_prev.status_code, status.HTTP_200_OK)
        self.assertEqual(resp_prev.data["rendered_subject"], "Alert for Alice")

        # 3. Retire
        resp_retire = self.client.post(
            f"/api/v1/notifications/templates/{self.template.id}/retire/",
            format="json",
        )
        self.assertEqual(resp_retire.status_code, status.HTTP_200_OK)
        self.assertEqual(resp_retire.data["status"], NotificationTemplateStatus.RETIRED)

    def test_regular_user_cannot_create_or_retire_templates(self):
        """Item 1: Authorization denial for non-owners on template mutation."""
        self.client.force_authenticate(user=self.regular_user)
        resp = self.client.post(
            f"/api/v1/notifications/templates/{self.template.id}/retire/",
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_async_job_queue_and_worker_execution(self):
        """Item 2: DB-backed async job enqueue and worker execution."""
        delivery = NotificationDelivery.objects.create(
            template=self.template,
            recipient_email="worker_test@example.com",
            idempotency_key="worker_test_key_1",
            status=NotificationDeliveryStatus.QUEUED,
            payload_context={"user_name": "Bob"},
        )

        job = enqueue_background_job(
            job_type="notification_delivery",
            payload={"delivery_id": str(delivery.id)},
        )
        self.assertEqual(job.status, BackgroundJobStatus.QUEUED)

        # Duplicate enqueue returns existing active job
        dup_job = enqueue_background_job(
            job_type="notification_delivery",
            payload={"delivery_id": str(delivery.id)},
        )
        self.assertEqual(dup_job.id, job.id)

        # Execute worker
        executed = process_next_queued_job()
        self.assertTrue(executed)

        job.refresh_from_db()
        self.assertEqual(job.status, BackgroundJobStatus.COMPLETED)
        delivery.refresh_from_db()
        self.assertEqual(delivery.status, NotificationDeliveryStatus.SENT)

    def test_owner_can_preview_template_with_sample_context_and_rendered_body(self):
        """Preview correctly renders sample variables and body."""
        self.client.force_authenticate(user=self.owner)
        resp = self.client.post(
            f"/api/v1/notifications/templates/{self.template.id}/preview/",
            {"context": {"user_name": "Carol"}},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["rendered_subject"], "Alert for Carol")
        self.assertIn("rendered_body", resp.data)
        self.assertIn("user_name", resp.data["supported_variables"])
        self.assertEqual(resp.data["unresolved_variables"], [])

    def test_owner_can_retry_delivery(self):
        """Platform Owner can manually retry failed or queued delivery."""
        self.client.force_authenticate(user=self.owner)
        delivery = NotificationDelivery.objects.create(
            template=self.template,
            recipient_email="retry_test@example.com",
            idempotency_key="retry_test_key_1",
            status=NotificationDeliveryStatus.FAILED,
            retry_count=3,
            max_retries=3,
            failure_reason="Simulated connection error",
            payload_context={"user_name": "Dave"},
        )
        resp = self.client.post(
            f"/api/v1/notifications/deliveries/{delivery.id}/retry/",
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        delivery.refresh_from_db()
        self.assertEqual(delivery.status, NotificationDeliveryStatus.SENT)
        self.assertEqual(delivery.retry_count, 4)

    def test_retry_already_sent_delivery_rejected(self):
        """Retrying already sent delivery returns 400 Bad Request."""
        self.client.force_authenticate(user=self.owner)
        delivery = NotificationDelivery.objects.create(
            template=self.template,
            recipient_email="already_sent@example.com",
            idempotency_key="already_sent_key_1",
            status=NotificationDeliveryStatus.SENT,
            payload_context={"user_name": "Eve"},
        )
        resp = self.client.post(
            f"/api/v1/notifications/deliveries/{delivery.id}/retry/",
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_regular_user_cannot_retry_delivery(self):
        """Non-platform owner cannot trigger delivery retry."""
        self.client.force_authenticate(user=self.regular_user)
        delivery = NotificationDelivery.objects.create(
            template=self.template,
            recipient_email="unauth_retry@example.com",
            idempotency_key="unauth_retry_key_1",
            status=NotificationDeliveryStatus.FAILED,
        )
        resp = self.client.post(
            f"/api/v1/notifications/deliveries/{delivery.id}/retry/",
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

