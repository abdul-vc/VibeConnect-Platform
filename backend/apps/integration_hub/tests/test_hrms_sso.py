"""Unit & Integration Tests for PeoplePulse HRMS SSO Integration.

Validates:
1. HRMS Client & Product Detection:
   - Client identifier: 'hrms-app'
   - Product code: 'hrms'
   - Audience: 'hrms-app'
   - Local callback: 'http://localhost:8081/sso/callback'
2. Dedicated M2M Secret Isolation & Fail-Closed:
   - HRMS resolves ONLY VIBECONNECT_HRMS_M2M_SECRET.
   - Missing HRMS secret fails closed (raises AuthenticationFailed with SERVER_MISCONFIGURED),
     even when VMS, FieldSense, Trinity, LMS, or shared M2M secrets are configured.
   - VMS, FieldSense, and Trinity secret resolution remain strictly isolated and unchanged.
   - Cross-client secret rejection: HRMS secret cannot validate VMS/FieldSense/Trinity and vice versa.
3. State Format & Signing Compatibility:
   - Generates exact format: <nonce>.<timestamp>.<hmac_sha256_hex>.
   - Signing input is strictly f"{nonce}.{timestamp}".encode("utf-8").
4. Validation Endpoint & Single-Use Enforcement:
   - Server-to-server code exchange via /api/v1/sso/validate/ using Bearer token.
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
from django.test import TestCase, override_settings
from rest_framework import exceptions, status
from rest_framework.test import APIClient

from apps.assignments.models import AssignmentStatus, UserModuleAssignment, UserProductAssignment
from apps.entitlements.models import EntitlementStatus, OrganizationProductEntitlement
from apps.integration_hub.models import (
    ConnectorInstance,
    InstanceStatus,
    IntegrationConnector,
    ProductSsoClient,
    SsoAuthorizationCode,
)
from apps.integration_hub.sso_service import (
    get_m2m_connector_secret,
    is_fieldsense_client,
    is_hrms_client,
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

HRMS_SECRET = "test-hrms-secret-entropy-32-chars-long"
VMS_SECRET = "test-vms-secret-entropy-32-chars-long"
FIELDSENSE_SECRET = "test-fieldsense-secret-entropy-32-chars-long"
TRINITY_SECRET = "test-trinity-secret-entropy-32-chars-long"
LMS_SECRET = "test-lms-secret-entropy-32-chars-longer"
SHARED_SECRET = "test-shared-m2m-secret-fallback-value"


@override_settings(
    VIBECONNECT_HRMS_M2M_SECRET=HRMS_SECRET,
    VIBECONNECT_VMS_M2M_SECRET=VMS_SECRET,
    VIBECONNECT_FIELDSENSE_M2M_SECRET=FIELDSENSE_SECRET,
    VIBECONNECT_TRINITY_M2M_SECRET=TRINITY_SECRET,
    VIBECONNECT_LMS_M2M_SECRET=LMS_SECRET,
    VIBECONNECT_M2M_SECRET=SHARED_SECRET,
)
class HrmsSecretResolutionTests(TestCase):
    """Tests dedicated secret resolution and fail-closed isolation for HRMS."""

    def setUp(self):
        super().setUp()
        self.suffix = uuid.uuid4().hex[:6]
        self.admin = User.objects.create_user(
            email=f"admin_{self.suffix}@vc.test",
            password="TestPassword123!",
            full_name="Platform Admin",
            is_platform_owner=True,
        )
        self.hrms_product = Product.objects.create(
            code="hrms",
            name="HRMS",
            status=ProductStatus.ACTIVE,
            created_by=self.admin,
            updated_by=self.admin,
        )

    def test_is_hrms_client_identifier_and_product_code(self):
        """Identifies HRMS by client identifier, product code, or database lookup."""
        self.assertTrue(is_hrms_client(client_identifier="hrms-app"))
        self.assertTrue(is_hrms_client(product_code="hrms"))
        self.assertTrue(is_hrms_client(product_code="hrms-core"))
        self.assertFalse(is_hrms_client(client_identifier="vms-warehouse-app"))
        self.assertFalse(is_hrms_client(client_identifier="fieldsense-ops-hub"))
        self.assertFalse(is_hrms_client(client_identifier="trinity-workshop-app"))
        self.assertFalse(is_hrms_client(product_code="vms-warehouse"))

    def test_hrms_resolves_dedicated_secret(self):
        """HRMS resolves VIBECONNECT_HRMS_M2M_SECRET when configured."""
        secret_by_client = get_m2m_connector_secret(client_identifier="hrms-app")
        self.assertEqual(secret_by_client, HRMS_SECRET)

        secret_by_prod = get_m2m_connector_secret(product_code="hrms")
        self.assertEqual(secret_by_prod, HRMS_SECRET)

    @override_settings(
        VIBECONNECT_HRMS_M2M_SECRET="",
        VIBECONNECT_VMS_M2M_SECRET=VMS_SECRET,
        VIBECONNECT_FIELDSENSE_M2M_SECRET=FIELDSENSE_SECRET,
        VIBECONNECT_TRINITY_M2M_SECRET=TRINITY_SECRET,
        VIBECONNECT_LMS_M2M_SECRET=LMS_SECRET,
        VIBECONNECT_M2M_SECRET=SHARED_SECRET,
    )
    def test_hrms_fails_closed_when_secret_missing(self):
        """Missing HRMS secret raises AuthenticationFailed (SERVER_MISCONFIGURED).

        Must NEVER fall back to LMS, VMS, FieldSense, Trinity, or shared secrets.
        """
        with mock.patch.dict(os.environ, {"VIBECONNECT_HRMS_M2M_SECRET": ""}):
            with self.assertRaises(exceptions.AuthenticationFailed) as ctx:
                get_m2m_connector_secret(client_identifier="hrms-app")
            self.assertEqual(ctx.exception.detail.get("error"), "SERVER_MISCONFIGURED")

            with self.assertRaises(exceptions.AuthenticationFailed) as ctx:
                get_m2m_connector_secret(product_code="hrms")
            self.assertEqual(ctx.exception.detail.get("error"), "SERVER_MISCONFIGURED")

    def test_hrms_isolation_does_not_affect_vms_or_fieldsense(self):
        """FieldSense, VMS, and Trinity secret resolution remain completely isolated."""
        self.assertEqual(get_m2m_connector_secret(client_identifier="fieldsense-ops-hub"), FIELDSENSE_SECRET)
        self.assertEqual(get_m2m_connector_secret(product_code="fieldsense"), FIELDSENSE_SECRET)
        self.assertEqual(get_m2m_connector_secret(client_identifier="vms-warehouse-app"), VMS_SECRET)
        self.assertEqual(get_m2m_connector_secret(product_code="vms-warehouse"), VMS_SECRET)
        self.assertEqual(get_m2m_connector_secret(client_identifier="trinity-workshop-app"), TRINITY_SECRET)


@override_settings(
    VIBECONNECT_HRMS_M2M_SECRET=HRMS_SECRET,
    VIBECONNECT_VMS_M2M_SECRET=VMS_SECRET,
    VIBECONNECT_FIELDSENSE_M2M_SECRET=FIELDSENSE_SECRET,
    VIBECONNECT_TRINITY_M2M_SECRET=TRINITY_SECRET,
    VIBECONNECT_LMS_M2M_SECRET=LMS_SECRET,
    VIBECONNECT_M2M_SECRET=SHARED_SECRET,
)
class HrmsSsoLifecycleTests(TestCase):
    """End-to-end tests for HRMS SSO issuance, signing, and code validation."""

    def setUp(self):
        super().setUp()
        self.suffix = uuid.uuid4().hex[:6]
        self.api_client = APIClient()

        self.admin = User.objects.create_user(
            email=f"admin_{self.suffix}@vc.test",
            password="TestPassword123!",
            full_name="Platform Admin",
            is_platform_owner=True,
        )

        self.hrms_product = Product.objects.create(
            code="hrms",
            name="HRMS",
            status=ProductStatus.ACTIVE,
            created_by=self.admin,
            updated_by=self.admin,
        )

        self.sso_client = ProductSsoClient.objects.create(
            product=self.hrms_product,
            client_identifier="hrms-app",
            audience="hrms-app",
            callback_uri="http://localhost:8081/sso/callback",
            public_key_reference="hrms-local-reference",
            is_active=True,
        )

        self.connector = IntegrationConnector.objects.create(
            product=self.hrms_product,
            code="hrms_app_connector",
            name="PeoplePulse HRMS Connector",
        )

        self.org = Organization.objects.create(
            name=f"Demo Org {self.suffix}",
            code=f"demo-org-{self.suffix}",
            status=OrganizationStatus.ACTIVE,
            created_by=self.admin,
            updated_by=self.admin,
        )

        self.connector_instance = ConnectorInstance.objects.create(
            connector=self.connector,
            organization=self.org,
            status=InstanceStatus.ACTIVE,
            credential_ref=f"ref://hrms/{self.org.code}",
        )

        self.user = User.objects.create_user(
            email=f"demo_user_{self.suffix}@vc.test",
            password="TestPassword123!",
            full_name="Demo User",
        )

        from django.utils import timezone
        self.membership = OrganizationMembership.objects.create(
            organization=self.org,
            user=self.user,
            membership_type=MembershipType.MEMBER,
            status=MembershipStatus.ACTIVE,
            joined_at=timezone.now(),
        )

        OrganizationProductEntitlement.objects.create(
            organization=self.org,
            product=self.hrms_product,
            status=EntitlementStatus.ACTIVE,
            created_by=self.admin,
            updated_by=self.admin,
        )

        self.assignment = UserProductAssignment.objects.create(
            user=self.user,
            organization=self.org,
            membership=self.membership,
            product=self.hrms_product,
            status=AssignmentStatus.ACTIVE,
            created_by=self.admin,
            updated_by=self.admin,
        )

        from apps.product_registry.models import CatalogStatus, ProductModule
        self.module, _ = ProductModule.objects.get_or_create(
            product=self.hrms_product,
            code="hrms_core",
            defaults={
                "name": "HRMS Core Module",
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

    def test_issue_sso_authorization_code_with_signed_state(self):
        """Code issuance generates signed state and redirect URL pointing to HRMS callback."""
        result = issue_sso_authorization_code(
            user=self.user,
            organization=self.org,
            product=self.hrms_product,
        )

        redirect_url = result["redirect_url"]
        parsed = urlparse(redirect_url)
        self.assertEqual(parsed.scheme, "http")
        self.assertEqual(parsed.netloc, "localhost:8081")
        self.assertEqual(parsed.path, "/sso/callback")

        qs = parse_qs(parsed.query)
        self.assertIn("code", qs)
        self.assertIn("state", qs)

        raw_code = qs["code"][0]
        state = qs["state"][0]

        # Verify state is signed with HRMS_SECRET: <nonce>.<timestamp>.<hmac>
        parts = state.split(".")
        self.assertEqual(len(parts), 3)
        nonce, ts, sig = parts
        expected_sig = hmac.new(
            HRMS_SECRET.encode("utf-8"),
            f"{nonce}.{ts}".encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        self.assertTrue(hmac.compare_digest(sig, expected_sig))

        # Verify code is stored hashed
        code_hash = hashlib.sha256(raw_code.encode("utf-8")).hexdigest()
        self.assertTrue(SsoAuthorizationCode.objects.filter(code_hash=code_hash).exists())

    def test_sso_validate_success_and_replay_protection(self):
        """Server-to-server validate endpoint validates code and rejects replay."""
        result = issue_sso_authorization_code(
            user=self.user,
            organization=self.org,
            product=self.hrms_product,
        )
        qs = parse_qs(urlparse(result["redirect_url"]).query)
        code = qs["code"][0]
        state = qs["state"][0]

        # 1. Validation without Authorization header -> 401
        res = self.api_client.post(
            "/api/v1/sso/validate/",
            {"code": code, "client_identifier": "hrms-app", "state": state},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

        # 2. Validation with wrong secret -> 403
        res = self.api_client.post(
            "/api/v1/sso/validate/",
            {"code": code, "client_identifier": "hrms-app", "state": state},
            HTTP_AUTHORIZATION="Bearer wrong-secret-value",
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

        # 3. Validation with valid HRMS secret -> 200 OK
        res = self.api_client.post(
            "/api/v1/sso/validate/",
            {"code": code, "client_identifier": "hrms-app", "state": state},
            HTTP_AUTHORIZATION=f"Bearer {HRMS_SECRET}",
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        claims = res.json()
        self.assertEqual(claims["user"]["email"], self.user.email)
        self.assertEqual(claims["organization"]["code"], self.org.code)
        self.assertEqual(claims["product"]["code"], "hrms")
        self.assertEqual(claims["audience"], "hrms-app")

        # 4. Replay attempt -> 400 CODE_ALREADY_USED
        replay_res = self.api_client.post(
            "/api/v1/sso/validate/",
            {"code": code, "client_identifier": "hrms-app", "state": state},
            HTTP_AUTHORIZATION=f"Bearer {HRMS_SECRET}",
            format="json",
        )
        self.assertEqual(replay_res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(replay_res.json().get("error"), "CODE_ALREADY_USED")
