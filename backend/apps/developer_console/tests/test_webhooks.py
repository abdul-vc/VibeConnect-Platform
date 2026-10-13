"""Focused Tests for Phase 6B-6 Outbound Developer Webhooks.

Validates:
- Webhook subscription creation, updating, secret handling
- Secret rotation with one-time return
- Lifecycle transitions (active, suspended, revoked)
- HMAC-SHA256 signature generation and timestamp-based replay protection
- Delivery execution (HTTP success, failure, retry backoff calculation)
- Dead-letter state when max attempts reached
- Delivery replay with stable delivery/event identity
- Audit logging of management actions (not ordinary automated delivery)
- Tenant isolation (Tenant Admin B cannot access Tenant A webhooks)
- Tenant Member denial (403 NO_CONSOLE_ACCESS)
- Platform Owner oversight
"""

import time
from unittest.mock import MagicMock, patch
import urllib.error
import uuid

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.access_control.models import Role
from apps.auditlog.models import AuditAction, AuditLog, AuditTargetType
from apps.developer_console.models import (
    DeveloperApplication,
    DeveloperWebhookDelivery,
    DeveloperWebhookSubscription,
    WebhookDeliveryStatus,
    WebhookSubscriptionStatus,
)
from apps.developer_console.services.webhook_service import (
    compute_webhook_signature,
    deliver_webhook,
    dispatch_webhook_event,
    verify_webhook_signature,
)
from apps.organizations.models import (
    MembershipStatus,
    MembershipType,
    Organization,
    OrganizationMembership,
    OrganizationStatus,
)

User = get_user_model()


class DeveloperWebhookTests(TestCase):
    def setUp(self):
        self.client = APIClient()

        # Users
        self.owner = User.objects.create_user(
            email="owner@example.com",
            password="Password123!",
            is_platform_owner=True,
            status="active",
        )
        self.tenant_admin_a = User.objects.create_user(
            email="admin_a@tenant.com",
            password="Password123!",
            status="active",
        )
        self.tenant_admin_b = User.objects.create_user(
            email="admin_b@tenant.com",
            password="Password123!",
            status="active",
        )
        self.tenant_member_a = User.objects.create_user(
            email="member_a@tenant.com",
            password="Password123!",
            status="active",
        )

        # Organizations
        self.org_a = Organization.objects.create(
            name="Org Alpha",
            code="org-alpha",
            status=OrganizationStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )
        self.org_b = Organization.objects.create(
            name="Org Beta",
            code="org-beta",
            status=OrganizationStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )

        # Roles
        self.admin_role_a = Role.objects.create(
            organization=self.org_a,
            code="admin_role_a",
            name="Tenant Admin Role A",
            created_by=self.owner,
            updated_by=self.owner,
        )
        self.admin_role_b = Role.objects.create(
            organization=self.org_b,
            code="admin_role_b",
            name="Tenant Admin Role B",
            created_by=self.owner,
            updated_by=self.owner,
        )

        # Memberships
        OrganizationMembership.objects.create(
            user=self.tenant_admin_a,
            organization=self.org_a,
            membership_type=MembershipType.TENANT_ADMIN,
            status=MembershipStatus.ACTIVE,
            role=self.admin_role_a,
            joined_at=timezone.now(),
        )
        OrganizationMembership.objects.create(
            user=self.tenant_admin_b,
            organization=self.org_b,
            membership_type=MembershipType.TENANT_ADMIN,
            status=MembershipStatus.ACTIVE,
            role=self.admin_role_b,
            joined_at=timezone.now(),
        )
        OrganizationMembership.objects.create(
            user=self.tenant_member_a,
            organization=self.org_a,
            membership_type=MembershipType.MEMBER,
            status=MembershipStatus.ACTIVE,
            role=None,
            joined_at=timezone.now(),
        )

        # Developer Application for Org A
        self.app_a = DeveloperApplication.objects.create(
            organization=self.org_a,
            name="Test App Alpha",
            status="active",
            created_by=self.tenant_admin_a,
        )

    def _login_as(self, user, context_type="tenant", organization=None):
        self.client.force_authenticate(user=user)
        session = self.client.session
        session["active_context_type"] = context_type
        session["tenant_organization_id"] = str(organization.id) if organization else None
        session.save()

    def test_tenant_admin_create_webhook_subscription_and_audit(self):
        """Tenant Admin can create webhook subscription and receives signing secret once."""
        self._login_as(self.tenant_admin_a, organization=self.org_a)

        payload = {
            "target_url": "https://api.example.com/webhooks/alpha",
            "event_topics": ["entitlement.granted", "assignment.created"],
        }
        res = self.client.post(
            f"/api/v1/tenant/developer/apps/{self.app_a.id}/webhooks/",
            data=payload,
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertIn("signing_secret", res.data)
        self.assertTrue(res.data["signing_secret"].startswith("whsec_"))
        self.assertEqual(res.data["status"], "active")

        sub_id = res.data["id"]

        # Detail endpoint must NOT return signing_secret
        detail_res = self.client.get(f"/api/v1/tenant/developer/webhooks/{sub_id}/")
        self.assertEqual(detail_res.status_code, status.HTTP_200_OK)
        self.assertNotIn("signing_secret", detail_res.data)

        # AuditLog entry must exist
        audit = AuditLog.objects.filter(
            action=AuditAction.DEVELOPER_WEBHOOK_CREATED,
            target_id=sub_id,
        ).first()
        self.assertIsNotNone(audit)
        self.assertEqual(audit.organization_id, self.org_a.id)

    def test_webhook_secret_rotation_returns_new_secret_once(self):
        """Secret rotation generates replacement secret, updates model, and records audit."""
        self._login_as(self.tenant_admin_a, organization=self.org_a)

        sub = DeveloperWebhookSubscription.objects.create(
            application=self.app_a,
            target_url="https://api.example.com/wh",
            event_topics=["entitlement.granted"],
            signing_secret="whsec_original12345",
            status="active",
        )

        res = self.client.post(f"/api/v1/tenant/developer/webhooks/{sub.id}/rotate-secret/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        new_secret = res.data["signing_secret"]
        self.assertNotEqual(new_secret, "whsec_original12345")
        self.assertTrue(new_secret.startswith("whsec_"))

        sub.refresh_from_db()
        self.assertEqual(sub.signing_secret, new_secret)

        audit = AuditLog.objects.filter(
            action=AuditAction.DEVELOPER_WEBHOOK_SECRET_ROTATED,
            target_id=sub.id,
        ).first()
        self.assertIsNotNone(audit)

    def test_webhook_lifecycle_transitions(self):
        """Tenant Admin can suspend, reactivate, and revoke webhook subscriptions."""
        self._login_as(self.tenant_admin_a, organization=self.org_a)

        sub = DeveloperWebhookSubscription.objects.create(
            application=self.app_a,
            target_url="https://api.example.com/wh",
            event_topics=["entitlement.granted"],
            signing_secret="whsec_secret123",
            status="active",
        )

        # Suspend
        res = self.client.post(
            f"/api/v1/tenant/developer/webhooks/{sub.id}/suspend/",
            data={"reason": "Temporarily down"},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["status"], "suspended")

        # Reactivate
        res = self.client.post(f"/api/v1/tenant/developer/webhooks/{sub.id}/reactivate/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["status"], "active")

        # Revoke
        res = self.client.post(
            f"/api/v1/tenant/developer/webhooks/{sub.id}/revoke/",
            data={"reason": "Decommissioned"},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["status"], "revoked")

    def test_hmac_sha256_signature_and_replay_protection(self):
        """Signature computes deterministic HMAC and rejects expired timestamps."""
        secret = "whsec_supersecretkey"
        now_ts = int(time.time())
        payload = '{"event":"entitlement.granted","id":"123"}'

        # Valid signature
        sig = compute_webhook_signature(secret, now_ts, payload)
        header = f"t={now_ts},v1={sig}"
        self.assertTrue(verify_webhook_signature(secret, header, payload, tolerance_seconds=300))

        # Tampered payload fails
        self.assertFalse(verify_webhook_signature(secret, header, '{"event":"tampered"}', tolerance_seconds=300))

        # Expired timestamp (older than tolerance) fails
        expired_ts = now_ts - 500
        expired_sig = compute_webhook_signature(secret, expired_ts, payload)
        expired_header = f"t={expired_ts},v1={expired_sig}"
        self.assertFalse(verify_webhook_signature(secret, expired_header, payload, tolerance_seconds=300))

    @patch("urllib.request.urlopen")
    def test_webhook_delivery_success(self, mock_urlopen):
        """Successful HTTP POST transitions delivery to DELIVERED."""
        mock_resp = MagicMock()
        mock_resp.getcode.return_value = 200
        mock_resp.read.return_value = b'{"received": true}'
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        sub = DeveloperWebhookSubscription.objects.create(
            application=self.app_a,
            target_url="https://api.example.com/endpoint",
            event_topics=["entitlement.granted"],
            signing_secret="whsec_testsecret",
            status="active",
        )

        delivery = DeveloperWebhookDelivery.objects.create(
            subscription=sub,
            event_type="entitlement.granted",
            payload={"product_code": "PROD_1"},
            status=WebhookDeliveryStatus.PENDING,
        )

        delivered = deliver_webhook(delivery)
        self.assertEqual(delivered.status, WebhookDeliveryStatus.DELIVERED)
        self.assertEqual(delivered.status_code, 200)
        self.assertEqual(delivered.attempt_count, 1)
        self.assertIsNotNone(delivered.delivered_at)
        self.assertIsNone(delivered.next_retry_at)

    @patch("urllib.request.urlopen")
    def test_webhook_delivery_failure_and_retry_backoff(self, mock_urlopen):
        """Failed HTTP POST increments attempt_count and schedules retry using 5G backoff."""
        mock_urlopen.side_effect = urllib.error.HTTPError(
            url="https://api.example.com/endpoint",
            code=503,
            msg="Service Unavailable",
            hdrs={},
            fp=None,
        )

        sub = DeveloperWebhookSubscription.objects.create(
            application=self.app_a,
            target_url="https://api.example.com/endpoint",
            event_topics=["entitlement.granted"],
            signing_secret="whsec_testsecret",
            status="active",
        )

        delivery = DeveloperWebhookDelivery.objects.create(
            subscription=sub,
            event_type="entitlement.granted",
            payload={"product_code": "PROD_1"},
            status=WebhookDeliveryStatus.PENDING,
        )

        delivered = deliver_webhook(delivery)
        self.assertEqual(delivered.status, WebhookDeliveryStatus.FAILED)
        self.assertEqual(delivered.status_code, 503)
        self.assertEqual(delivered.attempt_count, 1)
        self.assertIsNotNone(delivered.next_retry_at)

    @patch("urllib.request.urlopen")
    def test_webhook_delivery_dead_letter_on_exhaustion(self, mock_urlopen):
        """When attempt count reaches max_attempts, status transitions to DEAD_LETTER."""
        mock_urlopen.side_effect = TimeoutError("Connection timed out")

        sub = DeveloperWebhookSubscription.objects.create(
            application=self.app_a,
            target_url="https://api.example.com/endpoint",
            event_topics=["entitlement.granted"],
            signing_secret="whsec_testsecret",
            status="active",
        )

        delivery = DeveloperWebhookDelivery.objects.create(
            subscription=sub,
            event_type="entitlement.granted",
            payload={"product_code": "PROD_1"},
            attempt_count=4,
            max_attempts=5,
            status=WebhookDeliveryStatus.FAILED,
        )

        delivered = deliver_webhook(delivery)
        self.assertEqual(delivered.status, WebhookDeliveryStatus.DEAD_LETTER)
        self.assertEqual(delivered.attempt_count, 5)
        self.assertIsNone(delivered.next_retry_at)

    @patch("urllib.request.urlopen")
    def test_webhook_delivery_replay_preserves_identity_and_audits(self, mock_urlopen):
        """Delivery replay preserves delivery_id and event_id and records audit entry."""
        mock_resp = MagicMock()
        mock_resp.getcode.return_value = 200
        mock_resp.read.return_value = b'{"ok": true}'
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        self._login_as(self.tenant_admin_a, organization=self.org_a)

        sub = DeveloperWebhookSubscription.objects.create(
            application=self.app_a,
            target_url="https://api.example.com/wh",
            event_topics=["entitlement.granted"],
            signing_secret="whsec_secret",
            status="active",
        )
        delivery = DeveloperWebhookDelivery.objects.create(
            subscription=sub,
            event_type="entitlement.granted",
            payload={"test": 1},
            status=WebhookDeliveryStatus.DEAD_LETTER,
            attempt_count=5,
        )

        res = self.client.post(f"/api/v1/tenant/developer/deliveries/{delivery.id}/replay/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["id"], str(delivery.id))
        self.assertEqual(res.data["event_id"], str(delivery.event_id))
        self.assertEqual(res.data["status"], "delivered")

        audit = AuditLog.objects.filter(
            action=AuditAction.DEVELOPER_WEBHOOK_REPLAYED,
            target_id=sub.id,
        ).first()
        self.assertIsNotNone(audit)

    def test_tenant_isolation_cross_tenant_denial(self):
        """Tenant Admin B cannot view, modify, or replay Tenant A's webhooks."""
        self._login_as(self.tenant_admin_b, organization=self.org_b)

        sub_a = DeveloperWebhookSubscription.objects.create(
            application=self.app_a,
            target_url="https://api.example.com/wh",
            event_topics=["entitlement.granted"],
            signing_secret="whsec_secret",
            status="active",
        )

        # Cross-tenant detail access returns 404
        res = self.client.get(f"/api/v1/tenant/developer/webhooks/{sub_a.id}/")
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

        # Cross-tenant secret rotation returns 404
        rotate_res = self.client.post(f"/api/v1/tenant/developer/webhooks/{sub_a.id}/rotate-secret/")
        self.assertEqual(rotate_res.status_code, status.HTTP_404_NOT_FOUND)

    def test_tenant_member_denial(self):
        """Regular Tenant Member receives 403 NO_CONSOLE_ACCESS on developer webhook endpoints."""
        self._login_as(self.tenant_member_a, organization=self.org_a)

        res = self.client.get(f"/api/v1/tenant/developer/apps/{self.app_a.id}/webhooks/")
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(res.data.get("error"), "NO_CONSOLE_ACCESS")

    def test_platform_owner_oversight_and_emergency_controls(self):
        """Platform Owner can inspect webhooks across all tenants and suspend/revoke."""
        self._login_as(self.owner, context_type="platform_owner")

        sub_a = DeveloperWebhookSubscription.objects.create(
            application=self.app_a,
            target_url="https://api.example.com/wh",
            event_topics=["entitlement.granted"],
            signing_secret="whsec_secret",
            status="active",
        )

        # List across all tenants
        list_res = self.client.get("/api/v1/owner/developer/webhooks/")
        self.assertEqual(list_res.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(list_res.data["count"], 1)

        # Emergency suspend
        suspend_res = self.client.post(
            f"/api/v1/owner/developer/webhooks/{sub_a.id}/suspend/",
            data={"reason": "Security compliance violation"},
            format="json",
        )
        self.assertEqual(suspend_res.status_code, status.HTTP_200_OK)
        self.assertEqual(suspend_res.data["status"], "suspended")
