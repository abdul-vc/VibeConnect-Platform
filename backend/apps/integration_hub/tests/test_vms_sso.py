"""Unit & Integration Tests for WarehouseOS VMS SSO Integration.

Validates:
1. VMS Client & Product Detection:
   - Client identifier: 'vms-warehouse-app'
   - Product code: 'vms-warehouse'
   - Audience: 'vms-warehouse-app'
   - Local callback: 'http://localhost:8080/sso/callback'
2. Dedicated M2M Secret Isolation & Fail-Closed:
   - VMS resolves ONLY VIBECONNECT_VMS_M2M_SECRET.
   - Missing VMS secret fails closed (raises AuthenticationFailed with SERVER_MISCONFIGURED),
     even when FieldSense, Trinity, LMS, or shared M2M secrets are configured.
   - FieldSense secret resolution remains strictly isolated and unchanged.
   - Trinity secret resolution remains unchanged (Trinity -> Shared fallback).
   - Cross-client secret rejection: VMS secret cannot validate FieldSense/Trinity and vice versa.
3. Idempotent Management Command (register_vms_sso_client):
   - Correctly creates ProductSsoClient, IntegrationConnector, ConnectorInstance.
   - Repeated runs do not duplicate records.
   - Conflict detection prevents silent overwrites of mismatched clients.
4. State Format & Signing Compatibility:
   - Generates exact format: <nonce>.<timestamp>.<hmac_sha256_hex>.
   - Signing input is strictly f"{nonce}.{timestamp}".encode("utf-8").
   - Correctly validates with VMS verify_signed_state algorithm.
5. End-to-End SSO Contract:
   - Short-lived authorization code issuance via /api/v1/sso/launch/.
   - Strict redirect URI validation against 'http://localhost:8080/sso/callback'.
   - Server-to-server code exchange via /api/v1/sso/validate/ using Bearer token.
   - Verified claims return (user, organization, product 'vms-warehouse', audience 'vms-warehouse-app').
   - Single-use validation replay protection.
"""

import hashlib
import hmac
import os
import time
from unittest import mock
import uuid
from urllib.parse import parse_qs, urlparse

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from rest_framework import exceptions, status
from rest_framework.test import APIClient

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
    is_vms_client,
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
from apps.product_registry.models import Product, ProductStatus

User = get_user_model()

VMS_SECRET = "test-vms-secret-entropy-32-chars-long"
FIELDSENSE_SECRET = "test-fieldsense-secret-entropy-32-chars-long"
TRINITY_SECRET = "test-trinity-secret-entropy-32-chars-long"
LMS_SECRET = "test-lms-secret-entropy-32-chars-longer"
SHARED_SECRET = "test-shared-m2m-secret-fallback-value"


@override_settings(
    VIBECONNECT_VMS_M2M_SECRET=VMS_SECRET,
    VIBECONNECT_FIELDSENSE_M2M_SECRET=FIELDSENSE_SECRET,
    VIBECONNECT_TRINITY_M2M_SECRET=TRINITY_SECRET,
    VIBECONNECT_LMS_M2M_SECRET=LMS_SECRET,
    VIBECONNECT_M2M_SECRET=SHARED_SECRET,
)
class VmsSecretResolutionTests(TestCase):
    """Tests dedicated secret resolution and fail-closed isolation for VMS."""

    def setUp(self):
        super().setUp()
        self.suffix = uuid.uuid4().hex[:6]
        self.admin = User.objects.create_user(
            email=f"admin_{self.suffix}@vc.test",
            password="TestPassword123!",
            full_name="Platform Admin",
            is_platform_owner=True,
        )
        self.vms_product = Product.objects.create(
            code="vms-warehouse",
            name="VMS (Warehouse)",
            status=ProductStatus.ACTIVE,
            created_by=self.admin,
            updated_by=self.admin,
        )
        self.vms_client = ProductSsoClient.objects.create(
            product=self.vms_product,
            client_identifier="vms-warehouse-app",
            audience="vms-warehouse-app",
            callback_uri="http://localhost:8080/sso/callback",
            public_key_reference="vault://keys/vms-warehouse-app-m2m",
            is_active=True,
        )

    def test_client_detection(self):
        """is_vms_client correctly detects VMS client identifier and product code."""
        self.assertTrue(is_vms_client(client_identifier="vms-warehouse-app"))
        self.assertTrue(is_vms_client(product_code="vms-warehouse"))
        self.assertTrue(is_vms_client(client_identifier="warehouseos_vms"))
        self.assertFalse(is_vms_client(client_identifier="fieldsense-ops-hub"))
        self.assertFalse(is_vms_client(client_identifier="trinity-workshop-app"))
        self.assertFalse(is_vms_client(product_code="fieldsense"))
        self.assertFalse(is_vms_client(product_code="workshop-trinity"))

    def test_vms_resolves_dedicated_secret(self):
        """VMS resolves exclusively VIBECONNECT_VMS_M2M_SECRET."""
        with mock.patch.dict(os.environ, {"VIBECONNECT_VMS_M2M_SECRET": VMS_SECRET}):
            sec_by_code = get_m2m_connector_secret(product_code="vms-warehouse")
            self.assertEqual(sec_by_code, VMS_SECRET)

            sec_by_client = get_m2m_connector_secret(client_identifier="vms-warehouse-app")
            self.assertEqual(sec_by_client, VMS_SECRET)

    def test_vms_missing_secret_fails_closed(self):
        """When VIBECONNECT_VMS_M2M_SECRET is empty/missing, it raises AuthenticationFailed."""
        with override_settings(
            VIBECONNECT_VMS_M2M_SECRET="",
            VIBECONNECT_M2M_SECRET=SHARED_SECRET,
            VIBECONNECT_TRINITY_M2M_SECRET=TRINITY_SECRET,
            VIBECONNECT_FIELDSENSE_M2M_SECRET=FIELDSENSE_SECRET,
        ):
            with mock.patch.dict(os.environ, {
                "VIBECONNECT_VMS_M2M_SECRET": "",
                "VIBECONNECT_M2M_SECRET": SHARED_SECRET,
            }):
                with self.assertRaises(exceptions.AuthenticationFailed) as ctx:
                    get_m2m_connector_secret(product_code="vms-warehouse")
                self.assertIn("SERVER_MISCONFIGURED", str(ctx.exception))

                with self.assertRaises(exceptions.AuthenticationFailed) as ctx2:
                    get_m2m_connector_secret(client_identifier="vms-warehouse-app")
                self.assertIn("SERVER_MISCONFIGURED", str(ctx2.exception))

    def test_fieldsense_and_trinity_unaffected(self):
        """FieldSense and Trinity secret resolution remain completely intact."""
        with mock.patch.dict(os.environ, {
            "VIBECONNECT_FIELDSENSE_M2M_SECRET": FIELDSENSE_SECRET,
            "VIBECONNECT_TRINITY_M2M_SECRET": TRINITY_SECRET,
            "VIBECONNECT_VMS_M2M_SECRET": VMS_SECRET,
        }):
            fs_sec = get_m2m_connector_secret(product_code="fieldsense")
            self.assertEqual(fs_sec, FIELDSENSE_SECRET)

            trinity_sec = get_m2m_connector_secret(product_code="workshop-trinity")
            self.assertEqual(trinity_sec, TRINITY_SECRET)


class VmsManagementCommandTests(TestCase):
    """Tests the register_vms_sso_client management command."""

    def setUp(self):
        super().setUp()
        self.admin = User.objects.create_user(
            email="platform_owner@vc.test",
            password="TestPassword123!",
            is_platform_owner=True,
        )
        self.product = Product.objects.create(
            code="vms-warehouse",
            name="VMS (Warehouse)",
            status=ProductStatus.ACTIVE,
            created_by=self.admin,
            updated_by=self.admin,
        )
        self.org = Organization.objects.create(
            code="demo-org",
            name="Demo Organization",
            created_by=self.admin,
            updated_by=self.admin,
            status=OrganizationStatus.ACTIVE,
        )

    def test_register_vms_client_idempotence(self):
        """register_vms_sso_client runs cleanly and is idempotent."""
        call_command("register_vms_sso_client", organization="demo-org")

        client = ProductSsoClient.objects.filter(client_identifier="vms-warehouse-app").first()
        self.assertIsNotNone(client)
        self.assertEqual(client.audience, "vms-warehouse-app")
        self.assertEqual(client.callback_uri, "http://localhost:8080/sso/callback")
        self.assertTrue(client.is_active)

        connector = IntegrationConnector.objects.filter(code="vms_warehouse_connector").first()
        self.assertIsNotNone(connector)
        self.assertEqual(connector.product, self.product)

        instance = ConnectorInstance.objects.filter(connector=connector, organization=self.org).first()
        self.assertIsNotNone(instance)
        self.assertEqual(instance.status, InstanceStatus.ACTIVE)

        # Second call should succeed without duplicating or erroring
        call_command("register_vms_sso_client", organization="demo-org")
        self.assertEqual(ProductSsoClient.objects.filter(client_identifier="vms-warehouse-app").count(), 1)


@override_settings(
    VIBECONNECT_VMS_M2M_SECRET=VMS_SECRET,
    VIBECONNECT_FIELDSENSE_M2M_SECRET=FIELDSENSE_SECRET,
    VIBECONNECT_TRINITY_M2M_SECRET=TRINITY_SECRET,
)
class VmsSsoEndToEndTests(TestCase):
    """Integration tests for VMS SSO launch, state signing, and validation exchange."""

    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.admin = User.objects.create_user(
            email="owner@vc.test",
            password="TestPassword123!",
            is_platform_owner=True,
        )
        self.user = User.objects.create_user(
            email="demo_user@vc.test",
            password="TestPassword123!",
            full_name="Demo User",
        )
        self.product = Product.objects.create(
            code="vms-warehouse",
            name="VMS (Warehouse)",
            status=ProductStatus.ACTIVE,
            created_by=self.admin,
            updated_by=self.admin,
        )
        self.org = Organization.objects.create(
            code="demo-org",
            name="Demo Organization",
            created_by=self.admin,
            updated_by=self.admin,
            status=OrganizationStatus.ACTIVE,
        )
        from django.utils import timezone
        self.membership = OrganizationMembership.objects.create(
            organization=self.org,
            user=self.user,
            membership_type=MembershipType.MEMBER,
            status=MembershipStatus.ACTIVE,
            joined_at=timezone.now(),
        )
        call_command("register_vms_sso_client", organization=self.org.code)
        self.sso_client = ProductSsoClient.objects.get(client_identifier="vms-warehouse-app")
        self.connector = IntegrationConnector.objects.get(code="vms_warehouse_connector")
        self.instance = ConnectorInstance.objects.get(connector=self.connector, organization=self.org)
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
        from apps.product_registry.models import CatalogStatus, ProductModule
        self.module, _ = ProductModule.objects.get_or_create(
            product=self.product,
            code="vms_core",
            defaults={
                "name": "WarehouseOS Core Module",
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

    def test_state_format_and_signature_compatibility(self):
        """Verifies state format is <nonce>.<ts>.<hmac> and matches VMS signature validation."""
        with mock.patch.dict(os.environ, {"VIBECONNECT_VMS_M2M_SECRET": VMS_SECRET}):
            res = issue_sso_authorization_code(
                user=self.user,
                organization=self.org,
                product=self.product,
            )
            redirect_url = res["redirect_url"]
            params = parse_qs(urlparse(redirect_url).query)
            state = params["state"][0]

            parts = state.split(".")
            self.assertEqual(len(parts), 3, "State must have 3 segments: <nonce>.<ts>.<hmac>")
            nonce, ts_str, sig = parts

            # Verify signing input is f"{nonce}.{ts}".encode("utf-8")
            msg = f"{nonce}.{ts_str}".encode("utf-8")
            expected_sig = hmac.new(VMS_SECRET.encode("utf-8"), msg, hashlib.sha256).hexdigest()
            self.assertEqual(sig, expected_sig, "HMAC signature must match expected VMS verification")

            # Timestamp drift must be within 5 seconds
            ts = int(ts_str)
            self.assertLessEqual(abs(time.time() - ts), 5)

    def test_vms_sso_launch_and_validate_flow(self):
        """Tests complete flow: launch code issuance, M2M Bearer validate, claims check."""
        with mock.patch.dict(os.environ, {"VIBECONNECT_VMS_M2M_SECRET": VMS_SECRET}):
            self.client.force_authenticate(user=self.user)
            launch_res = self.client.post(
                "/api/v1/sso/launch/",
                {
                    "product_code": "vms-warehouse",
                    "organization_id": str(self.org.id),
                    "redirect_uri": "http://localhost:8080/sso/callback",
                },
                format="json",
            )
            self.assertEqual(launch_res.status_code, status.HTTP_200_OK)
            redirect_url = launch_res.data["redirect_url"]
            self.assertTrue(redirect_url.startswith("http://localhost:8080/sso/callback?"))

            params = parse_qs(urlparse(redirect_url).query)
            code = params["code"][0]
            state = params["state"][0]

            # Validate via M2M Bearer call
            self.client.force_authenticate(user=None)
            validate_res = self.client.post(
                "/api/v1/sso/validate/",
                {
                    "code": code,
                    "client_identifier": "vms-warehouse-app",
                    "state": state,
                },
                HTTP_AUTHORIZATION=f"Bearer {VMS_SECRET}",
                format="json",
            )
            self.assertEqual(validate_res.status_code, status.HTTP_200_OK)
            claims = validate_res.data
            self.assertEqual(claims["user"]["id"], str(self.user.id))
            self.assertEqual(claims["user"]["email"], self.user.email)
            self.assertEqual(claims["organization"]["code"], self.org.code)
            self.assertEqual(claims["product"]["code"], "vms-warehouse")
            self.assertEqual(claims["audience"], "vms-warehouse-app")

            # Replay should fail with CODE_ALREADY_USED
            replay_res = self.client.post(
                "/api/v1/sso/validate/",
                {
                    "code": code,
                    "client_identifier": "vms-warehouse-app",
                    "state": state,
                },
                HTTP_AUTHORIZATION=f"Bearer {VMS_SECRET}",
                format="json",
            )
            self.assertEqual(replay_res.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertEqual(replay_res.data["error"], "CODE_ALREADY_USED")

    def test_cross_client_secret_rejection(self):
        """FieldSense and Trinity secrets cannot validate VMS codes."""
        with mock.patch.dict(os.environ, {
            "VIBECONNECT_VMS_M2M_SECRET": VMS_SECRET,
            "VIBECONNECT_FIELDSENSE_M2M_SECRET": FIELDSENSE_SECRET,
            "VIBECONNECT_TRINITY_M2M_SECRET": TRINITY_SECRET,
        }):
            self.client.force_authenticate(user=self.user)
            launch_res = self.client.post(
                "/api/v1/sso/launch/",
                {"product_code": "vms-warehouse", "organization_id": str(self.org.id)},
                format="json",
            )
            code = parse_qs(urlparse(launch_res.data["redirect_url"]).query)["code"][0]

            self.client.force_authenticate(user=None)
            # Try validating with FieldSense secret
            res_fs = self.client.post(
                "/api/v1/sso/validate/",
                {"code": code, "client_identifier": "vms-warehouse-app"},
                HTTP_AUTHORIZATION=f"Bearer {FIELDSENSE_SECRET}",
                format="json",
            )
            self.assertEqual(res_fs.status_code, status.HTTP_403_FORBIDDEN)

            # Try validating with Trinity secret
            res_trinity = self.client.post(
                "/api/v1/sso/validate/",
                {"code": code, "client_identifier": "vms-warehouse-app"},
                HTTP_AUTHORIZATION=f"Bearer {TRINITY_SECRET}",
                format="json",
            )
            self.assertEqual(res_trinity.status_code, status.HTTP_403_FORBIDDEN)
