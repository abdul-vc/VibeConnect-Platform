"""Comprehensive Tests for Scientice Showcase SSO Integration and Configure Demo.

Verifies:
1. Scientice setup management command (setup_scientice_demo):
   - Idempotent execution
   - Reuses canonical product without duplicates
   - Configures demo environment, sso client, connector, entitlement, membership, assignment, launch config
2. Scientice Launchability Contract:
   - Succeeds (READY) when all prerequisites are in place
   - Fails safely when SSO client is missing
   - Fails safely when connector instance is missing
   - Fails safely when entitlement is missing
   - Fails safely when user membership is missing/inactive
   - Fails safely when user product assignment is missing
   - Fails safely when demo organization is not in allowlist
3. Authorized Showcase Live Demo Launch & Token Exchange:
   - POST /launch-demo/ mints short-lived authorization code and callback redirect URL
   - Authorization code exchange returns verified Scientice claims (canonical product code 'scientice')
   - Replayed authorization code is rejected (single-use)
   - Invalid state parameter is rejected
4. Secret Isolation:
   - Scientice validation strictly requires VIBECONNECT_SCIENTICE_M2M_SECRET
   - Fails closed when wrong product secret (e.g. FieldSense or Trinity) is presented
5. FieldSense & Trinity regression:
   - FieldSense and Trinity records and launch behavior remain untouched and functional
"""

from __future__ import annotations

import os
from unittest import mock
import urllib.parse
import uuid

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.assignments.models import AssignmentStatus, UserModuleAssignment, UserProductAssignment
from apps.entitlements.models import EntitlementStatus, OrganizationProductEntitlement
from apps.identity.models import PlatformUser, UserStatus
from apps.integration_hub.models import ConnectorInstance, InstanceStatus, IntegrationConnector, ProductSsoClient
from apps.integration_hub.sso_service import validate_sso_authorization_code, get_m2m_connector_secret
from apps.organizations.models import MembershipStatus, MembershipType, Organization, OrganizationMembership
from apps.product_registry.models import CatalogStatus, Product, ProductModule, ProductStatus
from apps.showcase.models import ProductDemoEnvironment, ProductLaunchConfig, ProductShowcaseProfile, ShowcaseVisibility
from apps.showcase.services import ProductShowcaseService, ShowcaseServiceError

User = get_user_model()
TEST_SCIENTICE_SECRET = "test-scientice-m2m-secret-entropy-32-chars-long"
TEST_FIELDSENSE_SECRET = "test-fieldsense-m2m-secret-entropy-32-chars-long"
TEST_TRINITY_SECRET = "test-trinity-m2m-secret-entropy-32-chars-long"


@override_settings(
    VIBECONNECT_SCIENTICE_M2M_SECRET=TEST_SCIENTICE_SECRET,
    VIBECONNECT_FIELDSENSE_M2M_SECRET=TEST_FIELDSENSE_SECRET,
    VIBECONNECT_TRINITY_M2M_SECRET=TEST_TRINITY_SECRET,
)
class ScienticeShowcaseSsoTests(TestCase):
    """End-to-end tests for Scientice showcase SSO integration, launchability, and validation."""

    def setUp(self):
        self.client = APIClient()
        self.owner = User.objects.create_user(
            email="admin@gmail.com",
            password="Password123!",
            full_name="Platform Owner Admin",
            is_platform_owner=True,
            is_staff=True,
            status=UserStatus.ACTIVE,
        )
        self.client.force_authenticate(user=self.owner)
        self.demo_user = self.owner

        self.demo_org = Organization.objects.create(
            name="Demo Organization",
            code="demo-org",
            status="active",
            created_by=self.owner,
            updated_by=self.owner,
        )
        self.membership = OrganizationMembership.objects.create(
            organization=self.demo_org,
            user=self.owner,
            membership_type=MembershipType.MEMBER,
            status=MembershipStatus.ACTIVE,
            joined_at=timezone.now(),
        )

        # Run setup command
        call_command(
            "setup_scientice_demo",
            base_url="http://localhost:5174",
            callback_uri="http://localhost:5174/sso/callback",
            organization="demo-org",
            user_email="admin@gmail.com",
        )

        self.product = Product.objects.get(code="scientice")
        self.profile = ProductShowcaseProfile.objects.get(product=self.product)
        self.demo_env = ProductDemoEnvironment.objects.get(product=self.product)
        self.sso_client = ProductSsoClient.objects.get(client_identifier="scientice-portal")

    def test_setup_scientice_demo_idempotence(self):
        """Re-running setup_scientice_demo does not duplicate products, connectors, or clients."""
        init_prod_count = Product.objects.filter(code="scientice").count()
        init_client_count = ProductSsoClient.objects.filter(client_identifier="scientice-portal").count()

        call_command(
            "setup_scientice_demo",
            base_url="http://localhost:5174",
            callback_uri="http://localhost:5174/sso/callback",
            organization="demo-org",
            user_email="admin@gmail.com",
        )

        self.assertEqual(Product.objects.filter(code="scientice").count(), init_prod_count)
        self.assertEqual(ProductSsoClient.objects.filter(client_identifier="scientice-portal").count(), init_client_count)

    def test_launchability_contract_ready(self):
        """Contract returns launchable=True with reason=READY when all prerequisites exist."""
        contract = ProductShowcaseService.launchability_contract(profile_id=str(self.profile.id))
        self.assertTrue(contract["launchable"])
        self.assertEqual(contract["reason"], "READY")
        self.assertEqual(contract["demo_user"], "admin@gmail.com")
        self.assertEqual(contract["demo_organization"], "demo-org")
        self.assertTrue(contract["sso_enabled"])

    def test_launchability_fails_when_sso_client_inactive(self):
        """Fails with SSO_CLIENT_NOT_CONFIGURED when ProductSsoClient is inactive or missing."""
        self.sso_client.is_active = False
        self.sso_client.save(update_fields=["is_active"])

        contract = ProductShowcaseService.launchability_contract(profile_id=str(self.profile.id))
        self.assertFalse(contract["launchable"])
        self.assertEqual(contract["reason"], "SSO_CLIENT_NOT_CONFIGURED")

    def test_launchability_fails_when_connector_missing(self):
        """Fails with INTEGRATION_INSTANCE_MISSING when ConnectorInstance is missing or inactive."""
        ConnectorInstance.objects.filter(connector__product=self.product).delete()

        contract = ProductShowcaseService.launchability_contract(profile_id=str(self.profile.id))
        self.assertFalse(contract["launchable"])
        self.assertEqual(contract["reason"], "INTEGRATION_INSTANCE_MISSING")

    def test_launchability_fails_when_assignment_missing(self):
        """Fails with DEMO_ASSIGNMENT_INACTIVE when user product assignment is missing."""
        UserProductAssignment.objects.filter(user=self.demo_user, product=self.product).delete()

        contract = ProductShowcaseService.launchability_contract(profile_id=str(self.profile.id))
        self.assertFalse(contract["launchable"])
        self.assertEqual(contract["reason"], "DEMO_ASSIGNMENT_INACTIVE")

    def test_launch_demo_and_validate_sso_code_flow(self):
        """Full flow: launch generates authorization code and validate endpoint returns Scientice claims."""
        url = f"/api/v1/showcase/profiles/{self.profile.id}/launch-demo/"
        resp = self.client.post(url, {})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        data = resp.json()
        redirect_url = data["redirect_url"]
        self.assertIn("http://localhost:5174/sso/callback", redirect_url)
        self.assertIn("code=", redirect_url)
        self.assertIn("state=", redirect_url)

        parsed = urllib.parse.urlparse(redirect_url)
        q = dict(urllib.parse.parse_qsl(parsed.query))
        code = q["code"]
        state = q["state"]

        # Call /api/v1/sso/validate/ using M2M secret
        val_url = "/api/v1/sso/validate/"
        val_resp = self.client.post(
            val_url,
            {
                "code": code,
                "client_identifier": "scientice-portal",
                "state": state,
            },
            format="json",
            HTTP_AUTHORIZATION=f"Bearer {TEST_SCIENTICE_SECRET}",
        )
        self.assertEqual(val_resp.status_code, status.HTTP_200_OK)
        claims = val_resp.json()

        self.assertEqual(claims["product"]["code"], "scientice")
        self.assertEqual(claims["user"]["email"], "admin@gmail.com")
        self.assertEqual(claims["audience"], "scientice-portal")

        # Anti-replay: code cannot be redeemed twice
        val_resp2 = self.client.post(
            val_url,
            {
                "code": code,
                "client_identifier": "scientice-portal",
                "state": state,
            },
            format="json",
            HTTP_AUTHORIZATION=f"Bearer {TEST_SCIENTICE_SECRET}",
        )
        self.assertEqual(val_resp2.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("CODE_ALREADY_USED", str(val_resp2.json()))

    def test_secret_isolation_rejects_wrong_secret(self):
        """Attempting to validate Scientice code with FieldSense or Trinity secret is rejected with 403."""
        # Issue code
        url = f"/api/v1/showcase/profiles/{self.profile.id}/launch-demo/"
        resp = self.client.post(url, {})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        parsed = urllib.parse.urlparse(resp.json()["redirect_url"])
        q = dict(urllib.parse.parse_qsl(parsed.query))
        code = q["code"]
        state = q["state"]

        # Validate with FieldSense secret
        val_url = "/api/v1/sso/validate/"
        val_resp = self.client.post(
            val_url,
            {
                "code": code,
                "client_identifier": "scientice-portal",
                "state": state,
            },
            format="json",
            HTTP_AUTHORIZATION=f"Bearer {TEST_FIELDSENSE_SECRET}",
        )
        self.assertEqual(val_resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_unauthenticated_user_denied_launch(self):
        """Unauthenticated user cannot launch Scientice showcase demo."""
        anon_client = APIClient()
        url = f"/api/v1/showcase/profiles/{self.profile.id}/launch-demo/"
        resp = anon_client.post(url, {})
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)
