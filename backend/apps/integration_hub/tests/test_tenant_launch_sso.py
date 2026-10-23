"""Unit tests for Tenant Admin & Member Launch SSO for CRM, Divine Connect, and WorkHub.

Tests:
1. CRM launch with active grant returns 200 and callback URL.
2. Divine Connect launch with active grant returns 200 and callback URL.
3. WorkHub launch with active grant returns 200 and callback URL.
4. Unentitled / unassigned launch is rejected with 403 Forbidden.
5. Downstream connection failure gracefully falls back to demo URL.
"""

from unittest.mock import patch
from django.test import TestCase, override_settings
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.organizations.models import (
    Organization,
    OrganizationMembership,
    OrganizationStatus,
    MembershipType,
    MembershipStatus,
)
from apps.access_control.models import Role
from apps.product_registry.models import Product, ProductStatus
from apps.entitlements.models import OrganizationProductEntitlement, EntitlementStatus
from apps.assignments.models import UserProductAssignment, AssignmentStatus
from apps.integration_hub.sso_views import SsoLaunchView
from apps.integration_hub.salestracker_sso_client import SalesTrackerSsoConnectionError
from apps.integration_hub.divineconnect_sso_client import DivineConnectSsoConnectionError
from apps.integration_hub.workhub_sso_client import WorkHubSsoConnectionError
from django.contrib.auth import get_user_model

User = get_user_model()


class TenantLaunchSsoTests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.view = SsoLaunchView.as_view()

        self.user = User.objects.create_user(
            email="tenant_tester@example.com",
            full_name="Tenant Tester",
            is_active=True,
        )

        self.org = Organization.objects.create(
            code="test-tenant-launch-org",
            name="Test Tenant Launch Org",
            status=OrganizationStatus.ACTIVE,
            created_by=self.user,
            updated_by=self.user,
        )

        self.role = Role.objects.create(
            code="tenant_admin",
            name="Tenant Administrator",
            description="Tenant Admin Role",
            is_system_role=True,
            created_by=self.user,
            updated_by=self.user,
        )

        self.membership = OrganizationMembership.objects.create(
            organization=self.org,
            user=self.user,
            membership_type=MembershipType.TENANT_ADMIN,
            role=self.role,
            status=MembershipStatus.ACTIVE,
            joined_at="2026-01-01T00:00:00Z",
        )

        self.crm_prod = Product.objects.create(
            code="crm",
            name="Sales Tracker CRM",
            status=ProductStatus.ACTIVE,
            created_by=self.user,
            updated_by=self.user,
        )

        self.divine_prod = Product.objects.create(
            code="divineconnect",
            name="Divine Connect",
            status=ProductStatus.ACTIVE,
            created_by=self.user,
            updated_by=self.user,
        )

        self.workhub_prod = Product.objects.create(
            code="workhub",
            name="WorkHub",
            status=ProductStatus.ACTIVE,
            created_by=self.user,
            updated_by=self.user,
        )

    def _grant_entitlement_and_assignment(self, product):
        OrganizationProductEntitlement.objects.create(
            organization=self.org,
            product=product,
            status=EntitlementStatus.ACTIVE,
            created_by=self.user,
            updated_by=self.user,
        )
        return UserProductAssignment.objects.create(
            organization=self.org,
            user=self.user,
            product=product,
            membership=self.membership,
            status=AssignmentStatus.ACTIVE,
            created_by=self.user,
            updated_by=self.user,
        )

    @override_settings(SALESTRACKER_SHOWCASE_M2M_SECRET="test-secret")
    @patch("apps.integration_hub.salestracker_sso_client.request_salestracker_launch_grant")
    def test_crm_tenant_launch_success(self, mock_grant):
        self._grant_entitlement_and_assignment(self.crm_prod)
        mock_grant.return_value = {
            "callback_url": "http://localhost:5173/sso/callback?code=mock-code-123",
            "expires_in": 60,
        }

        req = self.factory.post(
            "/api/v1/sso/launch/",
            {"product_id": str(self.crm_prod.id), "organization_id": str(self.org.id)},
            format="json",
        )
        force_authenticate(req, user=self.user)
        response = self.view(req)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data["direct_launch"])
        self.assertEqual(response.data["redirect_url"], "http://localhost:5173/sso/callback?code=mock-code-123")
        mock_grant.assert_called_once()

    @override_settings(DIVINECONNECT_SHOWCASE_M2M_SECRET="test-secret")
    @patch("apps.integration_hub.divineconnect_sso_client.request_divineconnect_launch_grant")
    def test_divineconnect_tenant_launch_success(self, mock_grant):
        self._grant_entitlement_and_assignment(self.divine_prod)
        mock_grant.return_value = {
            "callback_url": "http://localhost:8080/sso/callback?code=mock-code-456",
            "expires_in": 60,
        }

        req = self.factory.post(
            "/api/v1/sso/launch/",
            {"product_id": str(self.divine_prod.id), "organization_id": str(self.org.id)},
            format="json",
        )
        force_authenticate(req, user=self.user)
        response = self.view(req)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data["direct_launch"])
        self.assertEqual(response.data["redirect_url"], "http://localhost:8080/sso/callback?code=mock-code-456")
        mock_grant.assert_called_once()

    @override_settings(WORKHUB_SHOWCASE_M2M_SECRET="test-secret")
    @patch("apps.integration_hub.workhub_sso_client.request_workhub_launch_grant")
    def test_workhub_tenant_launch_success(self, mock_grant):
        self._grant_entitlement_and_assignment(self.workhub_prod)
        mock_grant.return_value = {
            "callback_url": "http://localhost:6395/sso/callback?code=mock-code-789&target=%2Fadmin",
            "expires_in": 60,
        }

        req = self.factory.post(
            "/api/v1/sso/launch/",
            {"product_id": str(self.workhub_prod.id), "organization_id": str(self.org.id)},
            format="json",
        )
        force_authenticate(req, user=self.user)
        response = self.view(req)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data["direct_launch"])
        self.assertEqual(response.data["redirect_url"], "http://localhost:6395/sso/callback?code=mock-code-789&target=%2Fadmin")
        mock_grant.assert_called_once()

    @override_settings(SALESTRACKER_SHOWCASE_M2M_SECRET="test-secret")
    @patch("apps.integration_hub.salestracker_sso_client.request_salestracker_launch_grant")
    def test_crm_tenant_launch_unreachable_fallback(self, mock_grant):
        self._grant_entitlement_and_assignment(self.crm_prod)
        mock_grant.side_effect = SalesTrackerSsoConnectionError("Connection refused")

        req = self.factory.post(
            "/api/v1/sso/launch/",
            {"product_id": str(self.crm_prod.id), "organization_id": str(self.org.id)},
            format="json",
        )
        force_authenticate(req, user=self.user)
        response = self.view(req)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["direct_launch"])
        self.assertIn("5173", response.data["redirect_url"])

    def test_tenant_launch_unentitled_rejected(self):
        req = self.factory.post(
            "/api/v1/sso/launch/",
            {"product_id": str(self.crm_prod.id), "organization_id": str(self.org.id)},
            format="json",
        )
        force_authenticate(req, user=self.user)
        response = self.view(req)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
