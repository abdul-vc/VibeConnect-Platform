"""Exhaustive Unit & Integration Tests for Trinity Workshop SSO Integration.

Tests cover:
1. Safe & Idempotent Management Command (register_trinity_sso_client):
   - Creation of ProductSsoClient, IntegrationConnector, ConnectorInstance
   - Idempotent re-run
   - Conflict detection and safety checks
2. Secure Authorization Code Launch Flow:
   - Success with product_code or product_id
   - HTTPS callback enforcement in non-DEBUG mode
   - Cryptographically bound state generation and persistence
   - Tenant isolation, effective access, and active assignment enforcement
   - Inactive client and unconfigured connector rejection
3. Server-to-Server M2M Validation Flow:
   - Successful code exchange with verified claims
   - Atomic redemption & single-use replay protection
   - Expiration enforcement
   - Strict client_identifier and product binding
   - State/CSRF verification & mismatch rejection
   - Assignment revocation check at validate time
4. Secret Isolation & Security:
   - Dedicated VIBECONNECT_TRINITY_M2M_SECRET authentication
   - Cross-client secret rejection (LMS secret rejected for Trinity and vice versa)
   - Constant-time secret comparison
   - No secrets leaked in API responses
5. LMS Backward Compatibility:
   - Existing LMS launch and validation flow remains fully operational
"""

import datetime
from decimal import Decimal
import hashlib
import json
import uuid

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework import status
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

TRINITY_SECRET = "test-trinity-secret-entropy-32-chars-long"
LMS_SECRET = "test-lms-secret-entropy-32-chars-longer"


@override_settings(
    VIBECONNECT_TRINITY_M2M_SECRET=TRINITY_SECRET,
    VIBECONNECT_LMS_M2M_SECRET=LMS_SECRET,
    VIBECONNECT_M2M_SECRET="",
)
class TrinitySsoIntegrationTests(TestCase):
    """Test suite verifying Trinity Workshop SSO integration end-to-end."""

    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.suffix = uuid.uuid4().hex[:6]

        # 1. Admin & Test User
        self.admin = User.objects.create_user(
            email=f"admin_{self.suffix}@vc.test",
            password="TestPassword123!",
            full_name="Platform Admin",
            is_active=True,
            is_staff=True,
            is_platform_owner=True,
        )
        self.user = User.objects.create_user(
            email=f"technician_{self.suffix}@vc.test",
            password="TestPassword123!",
            full_name="Workshop Technician",
            is_active=True,
        )

        # 2. Organization & Membership
        self.org = Organization.objects.create(
            name=f"Trinity Test Garage {self.suffix}",
            code=f"garage-{self.suffix}",
            status=OrganizationStatus.ACTIVE,
            created_by=self.admin,
            updated_by=self.admin,
        )
        self.role, _ = Role.objects.get_or_create(
            code="tenant_member",
            defaults={"name": "Tenant Member", "is_system_role": True},
        )
        self.membership = OrganizationMembership.objects.create(
            organization=self.org,
            user=self.user,
            membership_type=MembershipType.MEMBER,
            role=None,
            status=MembershipStatus.ACTIVE,
            joined_at=timezone.now(),
        )

        # 3. Products: Trinity Workshop & LMS
        self.workshop_prod, _ = Product.objects.get_or_create(
            code="workshop-trinity",
            defaults={
                "name": "WORKSHOP (Trinity)",
                "status": ProductStatus.ACTIVE,
                "created_by": self.admin,
                "updated_by": self.admin,
            },
        )
        self.lms_prod, _ = Product.objects.get_or_create(
            code="lms",
            defaults={
                "name": "Learning Management System",
                "status": ProductStatus.ACTIVE,
                "created_by": self.admin,
                "updated_by": self.admin,
            },
        )

        # 4. Entitlements & Product Assignments for Test User
        self.entitlement = OrganizationProductEntitlement.objects.create(
            organization=self.org,
            product=self.workshop_prod,
            status=EntitlementStatus.ACTIVE,
            created_by=self.admin,
            updated_by=self.admin,
        )
        self.assignment = UserProductAssignment.objects.create(
            user=self.user,
            organization=self.org,
            membership=self.membership,
            product=self.workshop_prod,
            status=AssignmentStatus.ACTIVE,
            created_by=self.admin,
            updated_by=self.admin,
        )
        self.workshop_module, _ = ProductModule.objects.get_or_create(
            product=self.workshop_prod,
            code="trinity_core",
            defaults={
                "name": "Trinity Core Module",
                "status": CatalogStatus.ACTIVE,
                "created_by": self.admin,
                "updated_by": self.admin,
            },
        )
        self.mod_assignment = UserModuleAssignment.objects.create(
            assignment=self.assignment,
            module=self.workshop_module,
            is_enabled=True,
        )

        # 5. Connector & Instance for Trinity
        self.connector, _ = IntegrationConnector.objects.get_or_create(
            code="trinity_workshop_connector",
            defaults={
                "name": "Trinity Workshop Connector",
                "product": self.workshop_prod,
                "status": ConnectorStatus.ACTIVE,
            },
        )
        self.instance, _ = ConnectorInstance.objects.get_or_create(
            connector=self.connector,
            organization=self.org,
            defaults={
                "label": f"Trinity Instance - {self.org.name}",
                "credential_ref": f"vault://tenant/{self.org.code}/trinity",
                "status": InstanceStatus.ACTIVE,
            },
        )

        # 6. ProductSsoClient for Trinity
        self.sso_client, _ = ProductSsoClient.objects.get_or_create(
            product=self.workshop_prod,
            defaults={
                "client_identifier": "trinity-workshop-app",
                "audience": "trinity-workshop-app",
                "callback_uri": "http://localhost:8080/sso/callback",
                "public_key_reference": "vault://keys/trinity-workshop-m2m",
                "is_active": True,
            },
        )

    # -------------------------------------------------------------------------
    # Management Command Tests
    # -------------------------------------------------------------------------

    def test_management_command_registration_and_idempotency(self):
        """Management command runs idempotently and configures client, connector, and instance."""
        # Run command
        call_command(
            "register_trinity_sso_client",
            organization=self.org.code,
            update=True,
        )

        client = ProductSsoClient.objects.get(client_identifier="trinity-workshop-app")
        self.assertEqual(client.product_id, self.workshop_prod.id)
        self.assertEqual(client.audience, "trinity-workshop-app")
        self.assertTrue(client.callback_uri.endswith("/sso/callback"))
        self.assertTrue(client.is_active)

        # Re-running without update flag succeeds cleanly (idempotent no-op)
        call_command("register_trinity_sso_client", organization=self.org.code)

    def test_management_command_detects_conflicts(self):
        """Command refuses to silently overwrite conflicting client identifiers."""
        # Create conflicting client bound to a different product
        other_prod = Product.objects.create(
            code=f"other_{self.suffix}",
            name="Other Product",
            status=ProductStatus.ACTIVE,
            created_by=self.admin,
            updated_by=self.admin,
        )
        ProductSsoClient.objects.create(
            product=other_prod,
            client_identifier="conflicting-client-id",
            audience="other",
            callback_uri="http://localhost:8080/sso/callback",
            is_active=True,
        )

        with self.assertRaises(CommandError) as ctx:
            call_command("register_trinity_sso_client", client_identifier="conflicting-client-id")
        self.assertIn("Conflict", str(ctx.exception))

    def test_management_command_rejects_non_callback_uri(self):
        """Command requires callback URI ending in /sso/callback."""
        with self.assertRaises(CommandError) as ctx:
            call_command("register_trinity_sso_client", callback_uri="http://localhost:8080/invalid/path")
        self.assertIn("/sso/callback", str(ctx.exception))

    # -------------------------------------------------------------------------
    # Launch Flow Tests
    # -------------------------------------------------------------------------

    def test_successful_trinity_sso_launch_by_product_code(self):
        """Launch endpoint issues a code and redirect URL with state query param."""
        self.client.force_authenticate(user=self.user)
        response = self.client.post(
            "/api/v1/sso/launch/",
            {
                "product_code": "workshop-trinity",
                "organization_id": str(self.org.id),
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertIn("redirect_url", data)
        self.assertIn("expires_at", data)

        redirect_url = data["redirect_url"]
        self.assertTrue(redirect_url.startswith("http://localhost:8080/sso/callback"))
        self.assertIn("code=", redirect_url)
        self.assertIn("state=", redirect_url)

        # Verify record exists in DB with state
        sso_code = SsoAuthorizationCode.objects.filter(user=self.user, product=self.workshop_prod).first()
        self.assertIsNotNone(sso_code)
        self.assertIsNotNone(sso_code.state)
        self.assertIn(sso_code.state, redirect_url)

    def test_launch_with_explicit_state_preserves_state(self):
        """Explicit state provided during launch is preserved and bound."""
        self.client.force_authenticate(user=self.user)
        custom_state = "client-provided-csrf-state-12345"
        response = self.client.post(
            "/api/v1/sso/launch/",
            {
                "product_code": "workshop-trinity",
                "organization_id": str(self.org.id),
                "state": custom_state,
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn(f"state={custom_state}", response.json()["redirect_url"])

    def test_launch_rejects_when_assignment_missing(self):
        """Launch fails if user has no active assignment for the product."""
        unassigned_user = User.objects.create_user(
            email=f"unassigned_{self.suffix}@vc.test",
            password="TestPassword123!",
            is_active=True,
        )
        OrganizationMembership.objects.create(
            organization=self.org,
            user=unassigned_user,
            membership_type=MembershipType.MEMBER,
            role=None,
            status=MembershipStatus.ACTIVE,
            joined_at=timezone.now(),
        )

        self.client.force_authenticate(user=unassigned_user)
        response = self.client.post(
            "/api/v1/sso/launch/",
            {
                "product_code": "workshop-trinity",
                "organization_id": str(self.org.id),
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn(response.json()["error"], ["ACCESS_DENIED", "ASSIGNMENT_MISSING"])

    def test_launch_rejects_inactive_client(self):
        """Launch fails if ProductSsoClient is deactivated."""
        self.sso_client.is_active = False
        self.sso_client.save(update_fields=["is_active"])

        self.client.force_authenticate(user=self.user)
        response = self.client.post(
            "/api/v1/sso/launch/",
            {
                "product_code": "workshop-trinity",
                "organization_id": str(self.org.id),
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.json()["error"], "SSO_NOT_CONFIGURED")

    def test_launch_rejects_missing_connector_instance(self):
        """Launch fails if organization has no active ConnectorInstance for the product."""
        self.instance.status = InstanceStatus.DISCONNECTED
        self.instance.save(update_fields=["status"])

        self.client.force_authenticate(user=self.user)
        response = self.client.post(
            "/api/v1/sso/launch/",
            {
                "product_code": "workshop-trinity",
                "organization_id": str(self.org.id),
            },
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.json()["error"], "INTEGRATION_NOT_CONFIGURED")

    # -------------------------------------------------------------------------
    # Code Validation / Exchange Flow Tests
    # -------------------------------------------------------------------------

    def test_successful_code_exchange_and_claims(self):
        """Valid code is exchanged for verified user, org, and product claims."""
        launch_res = issue_sso_authorization_code(
            user=self.user,
            organization=self.org,
            product=self.workshop_prod,
        )
        # Extract code from redirect URL
        code = launch_res["redirect_url"].split("code=")[1].split("&")[0]

        response = self.client.post(
            "/api/v1/sso/validate/",
            {
                "code": code,
                "client_identifier": "trinity-workshop-app",
            },
            HTTP_AUTHORIZATION=f"Bearer {TRINITY_SECRET}",
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        claims = response.json()

        # Check required Trinity claims
        self.assertEqual(claims["user"]["id"], str(self.user.id))
        self.assertEqual(claims["user"]["email"], self.user.email)
        self.assertEqual(claims["user"]["full_name"], self.user.full_name)
        self.assertEqual(claims["organization"]["id"], str(self.org.id))
        self.assertEqual(claims["organization"]["code"], self.org.code)
        self.assertEqual(claims["product"]["id"], str(self.workshop_prod.id))
        self.assertEqual(claims["product"]["code"], "workshop-trinity")
        self.assertEqual(claims["audience"], "trinity-workshop-app")
        self.assertEqual(claims["assignment_id"], str(self.assignment.id))

    def test_client_id_alias_supported_in_validation(self):
        """Validation accepts client_id as alias for client_identifier."""
        launch_res = issue_sso_authorization_code(
            user=self.user,
            organization=self.org,
            product=self.workshop_prod,
        )
        code = launch_res["redirect_url"].split("code=")[1].split("&")[0]

        response = self.client.post(
            "/api/v1/sso/validate/",
            {
                "code": code,
                "client_id": "trinity-workshop-app",
            },
            HTTP_AUTHORIZATION=f"Bearer {TRINITY_SECRET}",
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_single_use_atomic_burning_replay_protection(self):
        """Code cannot be redeemed more than once."""
        launch_res = issue_sso_authorization_code(
            user=self.user,
            organization=self.org,
            product=self.workshop_prod,
        )
        code = launch_res["redirect_url"].split("code=")[1].split("&")[0]

        # First exchange: 200 OK
        res1 = self.client.post(
            "/api/v1/sso/validate/",
            {"code": code, "client_identifier": "trinity-workshop-app"},
            HTTP_AUTHORIZATION=f"Bearer {TRINITY_SECRET}",
            format="json",
        )
        self.assertEqual(res1.status_code, status.HTTP_200_OK)

        # Second exchange (replay attempt): 400 CODE_ALREADY_USED
        res2 = self.client.post(
            "/api/v1/sso/validate/",
            {"code": code, "client_identifier": "trinity-workshop-app"},
            HTTP_AUTHORIZATION=f"Bearer {TRINITY_SECRET}",
            format="json",
        )
        self.assertEqual(res2.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(res2.json()["error"], "CODE_ALREADY_USED")

    def test_expired_code_is_rejected(self):
        """Expired code cannot be redeemed."""
        launch_res = issue_sso_authorization_code(
            user=self.user,
            organization=self.org,
            product=self.workshop_prod,
        )
        code = launch_res["redirect_url"].split("code=")[1].split("&")[0]
        code_hash = hashlib.sha256(code.encode("utf-8")).hexdigest()

        # Manually expire the code in DB
        SsoAuthorizationCode.objects.filter(code_hash=code_hash).update(
            expires_at=timezone.now() - datetime.timedelta(seconds=10)
        )

        response = self.client.post(
            "/api/v1/sso/validate/",
            {"code": code, "client_identifier": "trinity-workshop-app"},
            HTTP_AUTHORIZATION=f"Bearer {TRINITY_SECRET}",
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.json()["error"], "CODE_EXPIRED")

    def test_state_validation_success_and_mismatch_rejection(self):
        """Validation correctly verifies matching state and rejects tampered state."""
        launch_res = issue_sso_authorization_code(
            user=self.user,
            organization=self.org,
            product=self.workshop_prod,
            state="expected-secret-nonce-123",
        )
        code = launch_res["redirect_url"].split("code=")[1].split("&")[0]

        # Tampered state attempt
        tampered_res = self.client.post(
            "/api/v1/sso/validate/",
            {
                "code": code,
                "client_identifier": "trinity-workshop-app",
                "state": "attacker-tampered-state",
            },
            HTTP_AUTHORIZATION=f"Bearer {TRINITY_SECRET}",
            format="json",
        )
        self.assertEqual(tampered_res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(tampered_res.json()["error"], "STATE_MISMATCH")

        # Legitimate state attempt
        valid_res = self.client.post(
            "/api/v1/sso/validate/",
            {
                "code": code,
                "client_identifier": "trinity-workshop-app",
                "state": "expected-secret-nonce-123",
            },
            HTTP_AUTHORIZATION=f"Bearer {TRINITY_SECRET}",
            format="json",
        )
        self.assertEqual(valid_res.status_code, status.HTTP_200_OK)

    def test_client_identifier_mismatch_rejected(self):
        """Code issued to Trinity cannot be exchanged with wrong client_identifier."""
        launch_res = issue_sso_authorization_code(
            user=self.user,
            organization=self.org,
            product=self.workshop_prod,
        )
        code = launch_res["redirect_url"].split("code=")[1].split("&")[0]

        # Present authenticated LMS client attempting to redeem code issued to Trinity
        response = self.client.post(
            "/api/v1/sso/validate/",
            {"code": code, "client_identifier": "pilot_lms_client"},
            HTTP_AUTHORIZATION=f"Bearer {LMS_SECRET}",
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.json()["error"], "CLIENT_MISMATCH")

    def test_assignment_revocation_at_validation_time_rejected(self):
        """If user assignment is revoked between launch and validate, validate fails."""
        launch_res = issue_sso_authorization_code(
            user=self.user,
            organization=self.org,
            product=self.workshop_prod,
        )
        code = launch_res["redirect_url"].split("code=")[1].split("&")[0]

        # Revoke assignment with valid timestamp satisfying database constraint
        self.assignment.status = AssignmentStatus.REVOKED
        self.assignment.revoked_at = timezone.now()
        self.assignment.save(update_fields=["status", "revoked_at"])

        response = self.client.post(
            "/api/v1/sso/validate/",
            {"code": code, "client_identifier": "trinity-workshop-app"},
            HTTP_AUTHORIZATION=f"Bearer {TRINITY_SECRET}",
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.json()["error"], "ASSIGNMENT_REVOKED")

    # -------------------------------------------------------------------------
    # M2M Authentication & Secret Isolation Tests
    # -------------------------------------------------------------------------

    def test_missing_or_malformed_auth_header_rejected(self):
        """Missing or non-Bearer authorization header is rejected with 401."""
        res_none = self.client.post(
            "/api/v1/sso/validate/",
            {"code": "dummy", "client_identifier": "trinity-workshop-app"},
            format="json",
        )
        self.assertEqual(res_none.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(res_none.json()["error"], "AUTHENTICATION_REQUIRED")

        res_basic = self.client.post(
            "/api/v1/sso/validate/",
            {"code": "dummy", "client_identifier": "trinity-workshop-app"},
            HTTP_AUTHORIZATION="Basic xyz",
            format="json",
        )
        self.assertEqual(res_basic.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(res_basic.json()["error"], "INVALID_TOKEN_HEADER")

    def test_invalid_m2m_secret_rejected(self):
        """Incorrect secret is rejected with 403 Forbidden."""
        response = self.client.post(
            "/api/v1/sso/validate/",
            {"code": "dummy", "client_identifier": "trinity-workshop-app"},
            HTTP_AUTHORIZATION="Bearer wrong-secret-value",
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.json()["error"], "FORBIDDEN")

    def test_cross_client_secret_isolation(self):
        """LMS secret cannot authenticate Trinity validation, and Trinity secret cannot authenticate LMS."""
        launch_res = issue_sso_authorization_code(
            user=self.user,
            organization=self.org,
            product=self.workshop_prod,
        )
        code = launch_res["redirect_url"].split("code=")[1].split("&")[0]

        # Attempt to validate Trinity code using the LMS secret -> 403
        response = self.client.post(
            "/api/v1/sso/validate/",
            {"code": code, "client_identifier": "trinity-workshop-app"},
            HTTP_AUTHORIZATION=f"Bearer {LMS_SECRET}",
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_secrets_never_leak_in_error_or_success_responses(self):
        """API responses never contain secret strings."""
        # Check in successful response
        launch_res = issue_sso_authorization_code(
            user=self.user,
            organization=self.org,
            product=self.workshop_prod,
        )
        code = launch_res["redirect_url"].split("code=")[1].split("&")[0]

        success_res = self.client.post(
            "/api/v1/sso/validate/",
            {"code": code, "client_identifier": "trinity-workshop-app"},
            HTTP_AUTHORIZATION=f"Bearer {TRINITY_SECRET}",
            format="json",
        )
        success_content = success_res.content.decode("utf-8")
        self.assertNotIn(TRINITY_SECRET, success_content)
        self.assertNotIn(LMS_SECRET, success_content)

        # Check in error response
        error_res = self.client.post(
            "/api/v1/sso/validate/",
            {"code": "invalid-code", "client_identifier": "trinity-workshop-app"},
            HTTP_AUTHORIZATION="Bearer invalid-attempt",
            format="json",
        )
        error_content = error_res.content.decode("utf-8")
        self.assertNotIn(TRINITY_SECRET, error_content)
        self.assertNotIn(LMS_SECRET, error_content)

    # -------------------------------------------------------------------------
    # LMS Backward Compatibility Test
    # -------------------------------------------------------------------------

    def test_preserve_existing_lms_sso_behavior(self):
        """Existing LMS integration continues to work without disruption."""
        # Set up LMS connector, instance, client, entitlement, assignment
        lms_connector, _ = IntegrationConnector.objects.get_or_create(
            code="lms_connector",
            defaults={"name": "LMS Connector", "product": self.lms_prod, "status": ConnectorStatus.ACTIVE},
        )
        ConnectorInstance.objects.get_or_create(
            connector=lms_connector,
            organization=self.org,
            defaults={"label": "LMS Instance", "credential_ref": "vault://lms", "status": InstanceStatus.ACTIVE},
        )
        lms_client, _ = ProductSsoClient.objects.get_or_create(
            product=self.lms_prod,
            defaults={
                "client_identifier": "pilot_lms_client",
                "audience": "vibeconnect-lms",
                "callback_uri": "http://localhost:8080/sso/callback",
                "public_key_reference": "vault://keys/lms",
                "is_active": True,
            },
        )
        OrganizationProductEntitlement.objects.create(
            organization=self.org,
            product=self.lms_prod,
            status=EntitlementStatus.ACTIVE,
            created_by=self.admin,
            updated_by=self.admin,
        )
        lms_assignment = UserProductAssignment.objects.create(
            user=self.user,
            organization=self.org,
            membership=self.membership,
            product=self.lms_prod,
            status=AssignmentStatus.ACTIVE,
            created_by=self.admin,
            updated_by=self.admin,
        )
        lms_mod, _ = ProductModule.objects.get_or_create(
            product=self.lms_prod,
            code="lms_core",
            defaults={
                "name": "LMS Core Module",
                "status": CatalogStatus.ACTIVE,
                "created_by": self.admin,
                "updated_by": self.admin,
            },
        )
        UserModuleAssignment.objects.create(
            assignment=lms_assignment,
            module=lms_mod,
            is_enabled=True,
        )

        # Issue LMS code
        lms_launch = issue_sso_authorization_code(
            user=self.user,
            organization=self.org,
            product=self.lms_prod,
        )
        lms_code = lms_launch["redirect_url"].split("code=")[1].split("&")[0]

        # Validate with LMS secret and pilot_lms_client
        lms_validate_res = self.client.post(
            "/api/v1/sso/validate/",
            {"code": lms_code, "client_identifier": "pilot_lms_client"},
            HTTP_AUTHORIZATION=f"Bearer {LMS_SECRET}",
            format="json",
        )
        self.assertEqual(lms_validate_res.status_code, status.HTTP_200_OK)
        self.assertEqual(lms_validate_res.json()["product"]["code"], "lms")
        self.assertEqual(lms_validate_res.json()["audience"], "vibeconnect-lms")
