"""Regression and Integration Tests for FieldSense Operations Hub SSO Integration.

Validates:
1. FieldSense Client & Product Detection:
   - Client identifier: 'fieldsense-ops-hub'
   - Product code: 'fieldsense'
   - Audience: 'fieldsense-ops-hub'
   - Local callback: 'http://localhost:8081/sso/callback'
2. Dedicated M2M Secret Isolation & Fail-Closed:
   - FieldSense resolves ONLY VIBECONNECT_FIELDSENSE_M2M_SECRET.
   - Missing FieldSense secret fails closed (raises AuthenticationFailed),
     even when Trinity, LMS, or shared M2M secrets are configured.
   - Trinity secret resolution remains unchanged (Trinity -> Shared fallback).
   - LMS/default secret resolution remains unchanged (LMS -> Shared fallback).
   - Cross-client secret rejection (FieldSense secret cannot validate Trinity/LMS and vice versa).
3. Idempotent Management Command (register_fieldsense_sso_client):
   - Correctly creates Product, IntegrationConnector, ProductSsoClient, ConnectorInstance.
   - Repeated runs do not duplicate records.
   - Conflict detection prevents silent overwrites of mismatched clients.
   - Allows safe updates when --update is passed.
4. End-to-End SSO Contract Preservation:
   - Short-lived authorization code issuance via /api/v1/sso/launch/.
   - Strict redirect URI validation against 'http://localhost:8081/sso/callback'.
   - Server-to-server code exchange via /api/v1/sso/validate/ using Bearer token.
   - Verified claims return (user, organization, product 'fieldsense', audience 'fieldsense-ops-hub').
   - Single-use validation replay protection.
   - State/CSRF verification.
   - Client identifier binding verification.
"""

import os
from unittest import mock
import uuid
from urllib.parse import parse_qs, urlparse

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework import exceptions, status
from rest_framework.test import APIClient

from apps.access_control.models import Role
from apps.assignments.models import AssignmentStatus, UserModuleAssignment, UserProductAssignment
from apps.entitlements.models import EntitlementStatus, OrganizationProductEntitlement
from apps.integration_hub.models import (
    ConnectorInstance,
    ConnectorStatus,
    InstanceStatus,
    IntegrationConnector,
    ProductSsoClient,
    SsoAuthorizationCode,
)
from apps.integration_hub.sso_service import (
    get_m2m_connector_secret,
    is_fieldsense_client,
    is_trinity_client,
    issue_sso_authorization_code,
    validate_sso_authorization_code,
)
from apps.organizations.models import (
    MembershipStatus,
    MembershipType,
    Organization,
    OrganizationMembership,
    OrganizationStatus,
)
from apps.product_registry.models import CatalogStatus, Product, ProductModule, ProductStatus

User = get_user_model()

FIELDSENSE_SECRET = "test-fieldsense-secret-entropy-32-chars-long"
TRINITY_SECRET = "test-trinity-secret-entropy-32-chars-long"
LMS_SECRET = "test-lms-secret-entropy-32-chars-longer"
SHARED_SECRET = "test-shared-m2m-secret-fallback-value"


@override_settings(
    VIBECONNECT_FIELDSENSE_M2M_SECRET=FIELDSENSE_SECRET,
    VIBECONNECT_TRINITY_M2M_SECRET=TRINITY_SECRET,
    VIBECONNECT_LMS_M2M_SECRET=LMS_SECRET,
    VIBECONNECT_M2M_SECRET=SHARED_SECRET,
)
class FieldSenseSecretResolutionTests(TestCase):
    """Tests dedicated secret resolution and fail-closed isolation for FieldSense."""

    def setUp(self):
        super().setUp()
        self.suffix = uuid.uuid4().hex[:6]
        self.admin = User.objects.create_user(
            email=f"admin_{self.suffix}@vc.test",
            password="TestPassword123!",
            full_name="Platform Admin",
            is_platform_owner=True,
        )
        self.fieldsense_product = Product.objects.create(
            code="fieldsense",
            name="FieldSense Operations Hub",
            status=ProductStatus.ACTIVE,
            created_by=self.admin,
            updated_by=self.admin,
        )
        self.sso_client = ProductSsoClient.objects.create(
            product=self.fieldsense_product,
            client_identifier="fieldsense-ops-hub",
            audience="fieldsense-ops-hub",
            callback_uri="http://localhost:8081/sso/callback",
            public_key_reference="vault://keys/fieldsense-ops-hub-m2m",
            is_active=True,
        )

    def test_client_detection_helpers(self):
        """FieldSense and Trinity client detection helpers correctly identify respective clients."""
        # FieldSense detection
        self.assertTrue(is_fieldsense_client(client_identifier="fieldsense-ops-hub"))
        self.assertTrue(is_fieldsense_client(product_code="fieldsense"))
        self.assertTrue(is_fieldsense_client(product_code="fieldsense-ops-hub"))
        self.assertTrue(is_fieldsense_client(client_identifier="fieldsense-ops-hub", product_code="fieldsense"))

        # Lookup via DB client record
        self.assertTrue(is_fieldsense_client(client_identifier="fieldsense-ops-hub"))

        # FieldSense detection does NOT match Trinity, LMS, or other products
        self.assertFalse(is_fieldsense_client(client_identifier="trinity-workshop-app"))
        self.assertFalse(is_fieldsense_client(product_code="workshop-trinity"))
        self.assertFalse(is_fieldsense_client(client_identifier="pilot_lms_client"))
        self.assertFalse(is_fieldsense_client(product_code="lms"))
        self.assertFalse(is_fieldsense_client())

        # Trinity detection does NOT match FieldSense
        self.assertFalse(is_trinity_client(client_identifier="fieldsense-ops-hub"))
        self.assertFalse(is_trinity_client(product_code="fieldsense"))

        # Trinity detection still correctly identifies Trinity
        self.assertTrue(is_trinity_client(client_identifier="trinity-workshop-app"))
        self.assertTrue(is_trinity_client(product_code="workshop-trinity"))

    def test_fieldsense_resolves_only_dedicated_secret(self):
        """FieldSense resolves exclusively VIBECONNECT_FIELDSENSE_M2M_SECRET."""
        with mock.patch.dict(os.environ, {"VIBECONNECT_FIELDSENSE_M2M_SECRET": FIELDSENSE_SECRET}):
            sec_by_client = get_m2m_connector_secret(client_identifier="fieldsense-ops-hub")
            self.assertEqual(sec_by_client, FIELDSENSE_SECRET)

            sec_by_prod = get_m2m_connector_secret(product_code="fieldsense")
            self.assertEqual(sec_by_prod, FIELDSENSE_SECRET)

            sec_by_both = get_m2m_connector_secret(product_code="fieldsense", client_identifier="fieldsense-ops-hub")
            self.assertEqual(sec_by_both, FIELDSENSE_SECRET)

    @override_settings(
        VIBECONNECT_FIELDSENSE_M2M_SECRET="",
        VIBECONNECT_TRINITY_M2M_SECRET=TRINITY_SECRET,
        VIBECONNECT_LMS_M2M_SECRET=LMS_SECRET,
        VIBECONNECT_M2M_SECRET=SHARED_SECRET,
    )
    def test_missing_fieldsense_secret_fails_closed(self):
        """Missing FieldSense secret fails closed with AuthenticationFailed and never falls back."""
        with mock.patch.dict(os.environ, {
            "VIBECONNECT_FIELDSENSE_M2M_SECRET": "",
            "VIBECONNECT_TRINITY_M2M_SECRET": TRINITY_SECRET,
            "VIBECONNECT_LMS_M2M_SECRET": LMS_SECRET,
            "VIBECONNECT_M2M_SECRET": SHARED_SECRET,
        }):
            with self.assertRaises(exceptions.AuthenticationFailed) as ctx:
                get_m2m_connector_secret(client_identifier="fieldsense-ops-hub")
            self.assertIn("FieldSense M2M connector secret is not configured", str(ctx.exception.detail))

            with self.assertRaises(exceptions.AuthenticationFailed) as ctx:
                get_m2m_connector_secret(product_code="fieldsense")
            self.assertIn("FieldSense M2M connector secret is not configured", str(ctx.exception.detail))

    def test_trinity_and_lms_secret_behavior_unchanged(self):
        """Trinity and LMS continue to resolve their dedicated secrets."""
        with mock.patch.dict(os.environ, {
            "VIBECONNECT_TRINITY_M2M_SECRET": TRINITY_SECRET,
            "VIBECONNECT_LMS_M2M_SECRET": LMS_SECRET,
        }):
            trinity_sec = get_m2m_connector_secret(client_identifier="trinity-workshop-app")
            self.assertEqual(trinity_sec, TRINITY_SECRET)

            lms_sec = get_m2m_connector_secret(client_identifier="pilot_lms_client")
            self.assertEqual(lms_sec, LMS_SECRET)

    @override_settings(
        VIBECONNECT_FIELDSENSE_M2M_SECRET=FIELDSENSE_SECRET,
        VIBECONNECT_TRINITY_M2M_SECRET="",
        VIBECONNECT_LMS_M2M_SECRET="",
        VIBECONNECT_M2M_SECRET=SHARED_SECRET,
    )
    def test_trinity_and_lms_fallback_to_shared_secret(self):
        """Trinity and LMS fall back to VIBECONNECT_M2M_SECRET when dedicated is empty."""
        with mock.patch.dict(os.environ, {
            "VIBECONNECT_TRINITY_M2M_SECRET": "",
            "VIBECONNECT_LMS_M2M_SECRET": "",
            "VIBECONNECT_M2M_SECRET": SHARED_SECRET,
        }):
            trinity_sec = get_m2m_connector_secret(client_identifier="trinity-workshop-app")
            self.assertEqual(trinity_sec, SHARED_SECRET)

            lms_sec = get_m2m_connector_secret(client_identifier="pilot_lms_client")
            self.assertEqual(lms_sec, SHARED_SECRET)


class FieldSenseManagementCommandTests(TestCase):
    """Tests idempotent execution and safety constraints of register_fieldsense_sso_client."""

    def setUp(self):
        super().setUp()
        self.suffix = uuid.uuid4().hex[:6]
        self.admin = User.objects.create_user(
            email=f"admin_{self.suffix}@vc.test",
            password="TestPassword123!",
            full_name="Platform Admin",
            is_platform_owner=True,
        )
        self.org = Organization.objects.create(
            name=f"FieldForce Operations {self.suffix}",
            code=f"ff-{self.suffix}",
            status=OrganizationStatus.ACTIVE,
            created_by=self.admin,
            updated_by=self.admin,
        )

    def test_command_creates_client_and_connector_records(self):
        """Command creates Product, IntegrationConnector, ProductSsoClient, and ConnectorInstance."""
        call_command("register_fieldsense_sso_client", organization=self.org.code)

        product = Product.objects.get(code="fieldsense")
        self.assertEqual(product.name, "FieldSense Operations Hub")
        self.assertEqual(product.status, ProductStatus.ACTIVE)

        client = ProductSsoClient.objects.get(client_identifier="fieldsense-ops-hub")
        self.assertEqual(client.product, product)
        self.assertEqual(client.audience, "fieldsense-ops-hub")
        self.assertEqual(client.callback_uri, "http://localhost:8081/sso/callback")
        self.assertTrue(client.is_active)

        connector = IntegrationConnector.objects.get(code="fieldsense_ops_hub_connector")
        self.assertEqual(connector.product, product)
        self.assertEqual(connector.status, ConnectorStatus.ACTIVE)

        instance = ConnectorInstance.objects.get(connector=connector, organization=self.org)
        self.assertEqual(instance.status, InstanceStatus.ACTIVE)

    def test_command_is_strictly_idempotent(self):
        """Repeated executions do not create duplicate records."""
        call_command("register_fieldsense_sso_client", organization=self.org.code)

        client_count_1 = ProductSsoClient.objects.filter(client_identifier="fieldsense-ops-hub").count()
        connector_count_1 = IntegrationConnector.objects.filter(code="fieldsense_ops_hub_connector").count()
        instance_count_1 = ConnectorInstance.objects.filter(organization=self.org).count()
        product_count_1 = Product.objects.filter(code="fieldsense").count()

        self.assertEqual(client_count_1, 1)
        self.assertEqual(connector_count_1, 1)
        self.assertEqual(instance_count_1, 1)
        self.assertEqual(product_count_1, 1)

        # Run command second and third time
        call_command("register_fieldsense_sso_client", organization=self.org.code)
        call_command("register_fieldsense_sso_client", organization=self.org.code)

        self.assertEqual(ProductSsoClient.objects.filter(client_identifier="fieldsense-ops-hub").count(), 1)
        self.assertEqual(IntegrationConnector.objects.filter(code="fieldsense_ops_hub_connector").count(), 1)
        self.assertEqual(ConnectorInstance.objects.filter(organization=self.org).count(), 1)
        self.assertEqual(Product.objects.filter(code="fieldsense").count(), 1)

    def test_command_rejects_conflicting_client_identifier(self):
        """Command refuses to bind client_identifier if already used by another product."""
        other_product = Product.objects.create(
            code="other-prod",
            name="Other Product",
            status=ProductStatus.ACTIVE,
            created_by=self.admin,
            updated_by=self.admin,
        )
        ProductSsoClient.objects.create(
            product=other_product,
            client_identifier="fieldsense-ops-hub",
            audience="other-audience",
            callback_uri="http://localhost:9999/sso/callback",
            public_key_reference="vault://keys/other",
            is_active=True,
        )

        with self.assertRaises(CommandError) as ctx:
            call_command("register_fieldsense_sso_client", organization=self.org.code)
        self.assertIn("Conflict: client_identifier 'fieldsense-ops-hub' is already bound", str(ctx.exception))

    def test_command_detects_configuration_drift_and_requires_update_flag(self):
        """Differing configuration requires --update to prevent accidental overwrites."""
        call_command("register_fieldsense_sso_client", organization=self.org.code)

        # Attempt to change audience without --update
        with self.assertRaises(CommandError) as ctx:
            call_command(
                "register_fieldsense_sso_client",
                audience="new-audience-hub",
                organization=self.org.code,
            )
        self.assertIn("Pass --update to explicitly apply these changes", str(ctx.exception))

        # With --update flag, modification succeeds
        call_command(
            "register_fieldsense_sso_client",
            audience="new-audience-hub",
            organization=self.org.code,
            update=True,
        )
        client = ProductSsoClient.objects.get(client_identifier="fieldsense-ops-hub")
        self.assertEqual(client.audience, "new-audience-hub")


@override_settings(
    VIBECONNECT_FIELDSENSE_M2M_SECRET=FIELDSENSE_SECRET,
    VIBECONNECT_TRINITY_M2M_SECRET=TRINITY_SECRET,
    VIBECONNECT_LMS_M2M_SECRET=LMS_SECRET,
    VIBECONNECT_M2M_SECRET="",
)
class FieldSenseSsoEndToEndTests(TestCase):
    """End-to-end tests for FieldSense launch, token exchange, and claims validation."""

    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.suffix = uuid.uuid4().hex[:6]

        # 1. Admin & Test User
        self.admin = User.objects.create_user(
            email=f"admin_{self.suffix}@vc.test",
            password="TestPassword123!",
            full_name="Platform Admin",
            is_platform_owner=True,
            is_staff=True,
        )
        self.user = User.objects.create_user(
            email=f"fieldagent_{self.suffix}@vc.test",
            password="TestPassword123!",
            full_name="Field Operations Agent",
            is_active=True,
        )

        # 2. Organization & Membership
        self.org = Organization.objects.create(
            name=f"FieldSense Dispatch Org {self.suffix}",
            code=f"dispatch-{self.suffix}",
            status=OrganizationStatus.ACTIVE,
            created_by=self.admin,
            updated_by=self.admin,
        )
        self.membership = OrganizationMembership.objects.create(
            organization=self.org,
            user=self.user,
            membership_type=MembershipType.MEMBER,
            status=MembershipStatus.ACTIVE,
            joined_at=timezone.now(),
        )

        # 3. Product, Connector, SSO Client, ConnectorInstance via command
        call_command("register_fieldsense_sso_client", organization=self.org.code)
        self.product = Product.objects.get(code="fieldsense")
        self.sso_client = ProductSsoClient.objects.get(client_identifier="fieldsense-ops-hub")

        # 4. Entitlements & User Product Assignment
        self.entitlement = OrganizationProductEntitlement.objects.create(
            organization=self.org,
            product=self.product,
            status=EntitlementStatus.ACTIVE,
            created_by=self.admin,
            updated_by=self.admin,
        )
        self.assignment = UserProductAssignment.objects.create(
            user=self.user,
            organization=self.org,
            membership=self.membership,
            product=self.product,
            status=AssignmentStatus.ACTIVE,
            created_by=self.admin,
            updated_by=self.admin,
        )
        self.module, _ = ProductModule.objects.get_or_create(
            product=self.product,
            code="fieldsense_core",
            defaults={
                "name": "FieldSense Core Module",
                "status": CatalogStatus.ACTIVE,
                "created_by": self.admin,
                "updated_by": self.admin,
            },
        )
        self.mod_assignment = UserModuleAssignment.objects.create(
            assignment=self.assignment,
            module=self.module,
            is_enabled=True,
        )

    def test_fieldsense_launch_and_validation_happy_path(self):
        """Full SSO launch and code validation returns verified FieldSense claims."""
        with mock.patch.dict(os.environ, {"VIBECONNECT_FIELDSENSE_M2M_SECRET": FIELDSENSE_SECRET}):
            # Step 1: Launch SSO code as authenticated user
            self.client.force_authenticate(user=self.user)
            launch_res = self.client.post(
                "/api/v1/sso/launch/",
                {
                    "product_code": "fieldsense",
                    "organization_id": str(self.org.id),
                    "redirect_uri": "http://localhost:8081/sso/callback",
                },
                format="json",
            )
            self.assertEqual(launch_res.status_code, status.HTTP_200_OK)
            redirect_url = launch_res.data["redirect_url"]
            self.assertTrue(redirect_url.startswith("http://localhost:8081/sso/callback?"))

            # Extract code and state from redirect URL
            parsed = urlparse(redirect_url)
            params = parse_qs(parsed.query)
            code = params["code"][0]
            state = params.get("state", [None])[0]
            self.assertTrue(code)

            # Step 2: Validate code as FieldSense backend via M2M Bearer authentication
            self.client.force_authenticate(user=None)
            validate_res = self.client.post(
                "/api/v1/sso/validate/",
                {
                    "code": code,
                    "client_identifier": "fieldsense-ops-hub",
                    "state": state,
                },
                HTTP_AUTHORIZATION=f"Bearer {FIELDSENSE_SECRET}",
                format="json",
            )
            self.assertEqual(validate_res.status_code, status.HTTP_200_OK)
            claims = validate_res.data
            self.assertEqual(claims["user"]["id"], str(self.user.id))
            self.assertEqual(claims["user"]["email"], self.user.email)
            self.assertEqual(claims["organization"]["id"], str(self.org.id))
            self.assertEqual(claims["organization"]["code"], self.org.code)
            self.assertEqual(claims["product"]["code"], "fieldsense")
            self.assertEqual(claims["audience"], "fieldsense-ops-hub")

    def test_validate_rejects_wrong_secret(self):
        """Validation with wrong M2M secret returns 403 Forbidden."""
        with mock.patch.dict(os.environ, {"VIBECONNECT_FIELDSENSE_M2M_SECRET": FIELDSENSE_SECRET}):
            self.client.force_authenticate(user=self.user)
            launch_res = self.client.post(
                "/api/v1/sso/launch/",
                {"product_code": "fieldsense", "organization_id": str(self.org.id)},
                format="json",
            )
            code = parse_qs(urlparse(launch_res.data["redirect_url"]).query)["code"][0]

            self.client.force_authenticate(user=None)
            res = self.client.post(
                "/api/v1/sso/validate/",
                {"code": code, "client_identifier": "fieldsense-ops-hub"},
                HTTP_AUTHORIZATION="Bearer totally-wrong-secret",
                format="json",
            )
            self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
            self.assertEqual(res.data["error"], "FORBIDDEN")

    def test_cross_client_secret_rejection(self):
        """Trinity and LMS secrets are rejected when validating FieldSense authorization codes."""
        with mock.patch.dict(os.environ, {
            "VIBECONNECT_FIELDSENSE_M2M_SECRET": FIELDSENSE_SECRET,
            "VIBECONNECT_TRINITY_M2M_SECRET": TRINITY_SECRET,
            "VIBECONNECT_LMS_M2M_SECRET": LMS_SECRET,
        }):
            self.client.force_authenticate(user=self.user)
            launch_res = self.client.post(
                "/api/v1/sso/launch/",
                {"product_code": "fieldsense", "organization_id": str(self.org.id)},
                format="json",
            )
            code = parse_qs(urlparse(launch_res.data["redirect_url"]).query)["code"][0]

            self.client.force_authenticate(user=None)
            # Attempt validation using Trinity secret
            res_trinity = self.client.post(
                "/api/v1/sso/validate/",
                {"code": code, "client_identifier": "fieldsense-ops-hub"},
                HTTP_AUTHORIZATION=f"Bearer {TRINITY_SECRET}",
                format="json",
            )
            self.assertEqual(res_trinity.status_code, status.HTTP_403_FORBIDDEN)

            # Attempt validation using LMS secret
            res_lms = self.client.post(
                "/api/v1/sso/validate/",
                {"code": code, "client_identifier": "fieldsense-ops-hub"},
                HTTP_AUTHORIZATION=f"Bearer {LMS_SECRET}",
                format="json",
            )
            self.assertEqual(res_lms.status_code, status.HTTP_403_FORBIDDEN)

    def test_single_use_validation_enforced(self):
        """Authorization codes are strictly single-use and cannot be replayed."""
        with mock.patch.dict(os.environ, {"VIBECONNECT_FIELDSENSE_M2M_SECRET": FIELDSENSE_SECRET}):
            self.client.force_authenticate(user=self.user)
            launch_res = self.client.post(
                "/api/v1/sso/launch/",
                {"product_code": "fieldsense", "organization_id": str(self.org.id)},
                format="json",
            )
            code = parse_qs(urlparse(launch_res.data["redirect_url"]).query)["code"][0]

            self.client.force_authenticate(user=None)
            # First exchange succeeds
            res1 = self.client.post(
                "/api/v1/sso/validate/",
                {"code": code, "client_identifier": "fieldsense-ops-hub"},
                HTTP_AUTHORIZATION=f"Bearer {FIELDSENSE_SECRET}",
                format="json",
            )
            self.assertEqual(res1.status_code, status.HTTP_200_OK)

            # Second exchange fails with CODE_ALREADY_USED
            res2 = self.client.post(
                "/api/v1/sso/validate/",
                {"code": code, "client_identifier": "fieldsense-ops-hub"},
                HTTP_AUTHORIZATION=f"Bearer {FIELDSENSE_SECRET}",
                format="json",
            )
            self.assertEqual(res2.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertEqual(res2.data["error"], "CODE_ALREADY_USED")

    def test_state_mismatch_rejected(self):
        """Code validation rejects mismatched state parameter."""
        with mock.patch.dict(os.environ, {"VIBECONNECT_FIELDSENSE_M2M_SECRET": FIELDSENSE_SECRET}):
            self.client.force_authenticate(user=self.user)
            launch_res = self.client.post(
                "/api/v1/sso/launch/",
                {
                    "product_code": "fieldsense",
                    "organization_id": str(self.org.id),
                    "state": "client-csrf-state-nonce-123",
                },
                format="json",
            )
            code = parse_qs(urlparse(launch_res.data["redirect_url"]).query)["code"][0]

            self.client.force_authenticate(user=None)
            res = self.client.post(
                "/api/v1/sso/validate/",
                {
                    "code": code,
                    "client_identifier": "fieldsense-ops-hub",
                    "state": "attacker-tampered-state",
                },
                HTTP_AUTHORIZATION=f"Bearer {FIELDSENSE_SECRET}",
                format="json",
            )
            self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertEqual(res.data["error"], "STATE_MISMATCH")

    def test_client_identifier_mismatch_rejected(self):
        """Code issued to FieldSense cannot be validated with another client_identifier."""
        with mock.patch.dict(os.environ, {
            "VIBECONNECT_FIELDSENSE_M2M_SECRET": FIELDSENSE_SECRET,
            "VIBECONNECT_TRINITY_M2M_SECRET": TRINITY_SECRET,
        }):
            self.client.force_authenticate(user=self.user)
            launch_res = self.client.post(
                "/api/v1/sso/launch/",
                {"product_code": "fieldsense", "organization_id": str(self.org.id)},
                format="json",
            )
            code = parse_qs(urlparse(launch_res.data["redirect_url"]).query)["code"][0]

            self.client.force_authenticate(user=None)
            # Present Trinity client_identifier and Trinity secret for a FieldSense code
            res = self.client.post(
                "/api/v1/sso/validate/",
                {"code": code, "client_identifier": "trinity-workshop-app"},
                HTTP_AUTHORIZATION=f"Bearer {TRINITY_SECRET}",
                format="json",
            )
            self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertEqual(res.data["error"], "CLIENT_MISMATCH")

    @override_settings(
        VIBECONNECT_FIELDSENSE_M2M_SECRET="",
        VIBECONNECT_TRINITY_M2M_SECRET=TRINITY_SECRET,
        VIBECONNECT_M2M_SECRET=SHARED_SECRET,
    )
    def test_validate_when_fieldsense_secret_unconfigured_returns_500(self):
        """When VIBECONNECT_FIELDSENSE_M2M_SECRET is unconfigured, validate returns 500 SERVER_MISCONFIGURED."""
        with mock.patch.dict(os.environ, {
            "VIBECONNECT_FIELDSENSE_M2M_SECRET": "",
            "VIBECONNECT_TRINITY_M2M_SECRET": TRINITY_SECRET,
            "VIBECONNECT_M2M_SECRET": SHARED_SECRET,
        }):
            self.client.force_authenticate(user=self.user)
            launch_res = self.client.post(
                "/api/v1/sso/launch/",
                {"product_code": "fieldsense", "organization_id": str(self.org.id)},
                format="json",
            )
            code = parse_qs(urlparse(launch_res.data["redirect_url"]).query)["code"][0]

            self.client.force_authenticate(user=None)
            res = self.client.post(
                "/api/v1/sso/validate/",
                {"code": code, "client_identifier": "fieldsense-ops-hub"},
                HTTP_AUTHORIZATION="Bearer some-token",
                format="json",
            )
            self.assertEqual(res.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)
            self.assertEqual(res.data["error"], "SERVER_MISCONFIGURED")
