"""Integration Hub Backend Tests (Phase 5A + 5B).

Acceptance criteria:
  Phase 5A (3 tests):
    1. Idempotent event ingestion — duplicate event_key returns existing record.
    2. credential_ref never stores a raw secret — assert serializer rejects
       obviously secret-shaped values.
    3. Failure record creation — IntegrationFailure is created with retry_after.

  Phase 5B (3 tests):
    4. ExternalIdentity uniqueness on (provider, provider_tenant, provider_subject).
    5. ExternalTenantMapping uniqueness on (instance, organization).
    6. ExternalUserMapping uniqueness on (instance, external_user_id).
"""

import uuid
from datetime import timedelta

from django.test import TestCase, override_settings
from django.utils import timezone
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

TEST_M2M_SECRET = "sec_pilot_lms_m2m_token_2026"

from apps.integration_hub.models import (
    ConnectorInstance,
    ExternalIdentity,
    ExternalTenantMapping,
    ExternalUserMapping,
    InstanceStatus,
    IntegrationConnector,
    IntegrationEvent,
    IntegrationFailure,
    ProvisioningJob,
)
from apps.integration_hub.serializers import ConnectorInstanceSerializer
from apps.organizations.models import Organization

PlatformUser = get_user_model()


def _owner():
    u = PlatformUser.objects.create_user(
        email=f"owner_{uuid.uuid4().hex[:8]}@test.io",
        password="pass",
    )
    # Mark as platform owner if the field exists on the custom user model
    if hasattr(u, "is_platform_owner"):
        u.is_platform_owner = True
        u.save(update_fields=["is_platform_owner"])
    return u


def _org(suffix: str = "", owner=None, status: str = "active"):
    if owner is None:
        owner = _owner()
    return Organization.objects.create(
        name=f"Test Org {suffix or uuid.uuid4().hex[:6]}",
        code=f"test_{uuid.uuid4().hex[:6]}",
        status=status,
        created_by=owner,
        updated_by=owner,
    )


def _connector() -> IntegrationConnector:
    return IntegrationConnector.objects.create(
        code=f"conn_{uuid.uuid4().hex[:8]}",
        name="Test Connector",
    )


def _instance(connector=None, organization=None) -> ConnectorInstance:
    return ConnectorInstance.objects.create(
        connector=connector or _connector(),
        organization=organization or _org(),
        credential_ref="vault:secret/test/cred",
    )


# ── Phase 5A ──────────────────────────────────────────────────────────────────


class IdempotentEventIngestionTest(TestCase):
    """AC-5A-1: Duplicate event_key returns existing record, creates only one row."""

    def setUp(self):
        self.owner = _owner()
        self.client = APIClient()
        self.client.force_authenticate(user=self.owner)
        self.instance = _instance()

    def test_duplicate_event_key_returns_existing(self):
        event_key = f"lms.enrollment.created:{uuid.uuid4()}"
        payload = {
            "instance": str(self.instance.id),
            "event_type": "lms.enrollment.created",
            "event_key": event_key,
            "occurred_at": timezone.now().isoformat(),
            "payload": {"user_id": "ext-123"},
        }

        # First ingest — creates
        r1 = self.client.post("/api/v1/integration/events/ingest/", payload, format="json")
        self.assertEqual(r1.status_code, 201)
        event_id = r1.data["id"]

        # Second ingest — idempotent
        r2 = self.client.post("/api/v1/integration/events/ingest/", payload, format="json")
        self.assertEqual(r2.status_code, 200, "Second ingest must return 200 (idempotent)")
        self.assertEqual(r2.data["id"], event_id, "Must return the same event record")

        # Only one row in DB
        count = IntegrationEvent.objects.filter(event_key=event_key).count()
        self.assertEqual(count, 1, "Only one event row must exist for a duplicate key")


class CredentialRefSecretRejectionTest(TestCase):
    """AC-5A-2: credential_ref rejects raw-secret-shaped values at the serializer layer."""

    def setUp(self):
        self.connector = _connector()
        self.org = _org()

    def _serializer(self, cred: str):
        return ConnectorInstanceSerializer(data={
            "connector": str(self.connector.id),
            "organization": str(self.org.id),
            "credential_ref": cred,
        })

    def test_raw_secret_sk_prefix_rejected(self):
        s = self._serializer("sk_live_abc123secretkey")
        self.assertFalse(s.is_valid(), "sk_ prefixed value must be rejected")
        self.assertIn("credential_ref", s.errors)

    def test_raw_secret_secret_prefix_rejected(self):
        s = self._serializer("secret_abc123verysensitive")
        self.assertFalse(s.is_valid(), "secret_ prefixed value must be rejected")
        self.assertIn("credential_ref", s.errors)

    def test_bearer_token_rejected(self):
        s = self._serializer("Bearer eyJhbGciOiJIUzI1NiJ9.abc.xyz")
        self.assertFalse(s.is_valid(), "Bearer token must be rejected")
        self.assertIn("credential_ref", s.errors)

    def test_opaque_ref_accepted(self):
        s = self._serializer("vault:secret/org-123/canvas")
        self.assertTrue(s.is_valid(), f"Opaque ref must be accepted: {s.errors}")


class FailureRecordCreationTest(TestCase):
    """AC-5A-3: IntegrationFailure can be created with retry_after populated."""

    def test_failure_record_created_with_retry_after(self):
        inst = _instance()
        job = ProvisioningJob.objects.create(
            instance=inst,
            organization=inst.organization,
            action="provision",
        )
        retry_time = timezone.now() + timedelta(minutes=30)
        failure = IntegrationFailure.objects.create(
            job=job,
            failure_code="UPSTREAM_TIMEOUT",
            failure_detail="External LMS did not respond within 30s.",
            retry_after=retry_time,
        )
        self.assertIsNotNone(failure.id)
        self.assertEqual(failure.failure_code, "UPSTREAM_TIMEOUT")
        self.assertIsNotNone(failure.retry_after)
        # Verify it's persisted
        db_failure = IntegrationFailure.objects.get(pk=failure.pk)
        self.assertEqual(db_failure.retry_after.replace(microsecond=0), retry_time.replace(microsecond=0))


# ── Phase 5B ──────────────────────────────────────────────────────────────────


class ExternalIdentityUniquenessTest(TestCase):
    """AC-5B-1: ExternalIdentity is unique on (provider, provider_tenant, provider_subject)."""

    def test_duplicate_external_identity_rejected(self):
        from django.db import IntegrityError
        user1 = _owner()
        user2 = _owner()
        ExternalIdentity.objects.create(
            user=user1,
            provider="canvas",
            provider_tenant="acme.instructure.com",
            provider_subject="ext-user-001",
        )
        with self.assertRaises(IntegrityError):
            ExternalIdentity.objects.create(
                user=user2,
                provider="canvas",
                provider_tenant="acme.instructure.com",
                provider_subject="ext-user-001",
            )


class ExternalTenantMappingUniquenessTest(TestCase):
    """AC-5B-2: ExternalTenantMapping is unique on (instance, organization)."""

    def test_duplicate_tenant_mapping_rejected(self):
        from django.db import IntegrityError
        inst = _instance()
        org = inst.organization
        ExternalTenantMapping.objects.create(
            organization=org,
            instance=inst,
            external_tenant_id="lms-tenant-001",
        )
        with self.assertRaises(IntegrityError):
            ExternalTenantMapping.objects.create(
                organization=org,
                instance=inst,
                external_tenant_id="lms-tenant-002",  # different external ID, same org+instance
            )


class ExternalUserMappingUniquenessTest(TestCase):
    """AC-5B-3: ExternalUserMapping is unique on (instance, external_user_id)."""

    def test_duplicate_user_mapping_rejected(self):
        from django.db import IntegrityError
        inst = _instance()
        org = inst.organization
        user1 = _owner()
        user2 = _owner()
        ExternalUserMapping.objects.create(
            user=user1,
            organization=org,
            instance=inst,
            external_user_id="lms-user-999",
        )
        with self.assertRaises(IntegrityError):
            ExternalUserMapping.objects.create(
                user=user2,
                organization=org,
                instance=inst,
                external_user_id="lms-user-999",  # same external_user_id, same instance
            )


# =============================================================================
# Phase 5C: LMS SSO Pilot Backend Tests
# =============================================================================


def _sso_setup():
    owner = _owner()
    org = _org(owner=owner)
    user = PlatformUser.objects.create_user(
        email=f"user_{uuid.uuid4().hex[:8]}@test.io",
        password="pass",
    )
    from apps.assignments.models import (
        AssignmentStatus,
        UserModuleAssignment,
        UserProductAssignment,
    )
    from apps.entitlements.models import EntitlementStatus, OrganizationProductEntitlement
    from apps.integration_hub.models import ProductSsoClient
    from apps.organizations.models import MembershipStatus, MembershipType, OrganizationMembership
    from apps.product_registry.models import CatalogStatus, Product, ProductModule, ProductStatus

    # Active membership
    membership = OrganizationMembership.objects.create(
        organization=org,
        user=user,
        status=MembershipStatus.ACTIVE,
        membership_type=MembershipType.MEMBER,
        joined_at=timezone.now(),
    )

    # Active product
    product = Product.objects.create(
        code=f"pilot_{uuid.uuid4().hex[:6]}",
        name="Pilot LMS",
        status=ProductStatus.ACTIVE,
        created_by=owner,
        updated_by=owner,
    )

    # Active module
    module = ProductModule.objects.create(
        product=product,
        code="lms_core",
        name="LMS Core Module",
        status=CatalogStatus.ACTIVE,
        created_by=owner,
        updated_by=owner,
    )

    # Active direct grant entitlement
    OrganizationProductEntitlement.objects.create(
        organization=org,
        product=product,
        status=EntitlementStatus.ACTIVE,
        created_by=owner,
        updated_by=owner,
    )

    # User Product Assignment
    assignment = UserProductAssignment.objects.create(
        organization=org,
        user=user,
        membership=membership,
        product=product,
        status=AssignmentStatus.ACTIVE,
        created_by=owner,
        updated_by=owner,
    )

    # User Module Assignment
    UserModuleAssignment.objects.create(
        assignment=assignment,
        module=module,
        is_enabled=True,
    )

    # SSO Client
    sso_client = ProductSsoClient.objects.create(
        product=product,
        client_identifier=f"client_{uuid.uuid4().hex[:8]}",
        audience="pilot-lms-audience",
        callback_uri="https://pilot-lms.example.com/sso/callback",
        public_key_reference="vault://keys/pilot-lms-key",
        is_active=True,
    )

    from apps.integration_hub.models import (
        ConnectorInstance,
        InstanceStatus,
        IntegrationConnector,
    )
    connector = IntegrationConnector.objects.create(
        code=f"conn_{uuid.uuid4().hex[:6]}",
        name="Pilot Connector",
        product=product,
        status="active",
    )
    connector_instance = ConnectorInstance.objects.create(
        connector=connector,
        organization=org,
        label="Pilot LMS Instance",
        credential_ref="vault://pilot-instance",
        status=InstanceStatus.ACTIVE,
    )

    return {
        "owner": owner,
        "org": org,
        "user": user,
        "product": product,
        "assignment": assignment,
        "sso_client": sso_client,
        "connector": connector,
        "connector_instance": connector_instance,
    }


@override_settings(VIBECONNECT_LMS_M2M_SECRET=TEST_M2M_SECRET)
class SsoLaunchAndValidateRoundTripTest(TestCase):
    """AC-5C-1: Successful launch and validate round trip."""

    def test_successful_launch_and_validate_round_trip(self):
        import base64
        import hashlib
        from urllib.parse import parse_qs, urlparse
        from apps.integration_hub.models import SsoAuthorizationCode

        fixture = _sso_setup()
        client = APIClient()
        client.force_authenticate(user=fixture["user"])

        # PKCE preparation
        verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
        digest = hashlib.sha256(verifier.encode("ascii")).digest()
        challenge = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")

        launch_res = client.post(
            "/api/v1/sso/launch/",
            {
                "product_id": str(fixture["product"].id),
                "organization_id": str(fixture["org"].id),
                "state": "state_123",
                "code_challenge": challenge,
                "code_challenge_method": "S256",
            },
            format="json",
        )
        self.assertEqual(launch_res.status_code, 200)
        redirect_url = launch_res.data["redirect_url"]
        self.assertTrue(redirect_url.startswith("https://pilot-lms.example.com/sso/callback"))

        parsed = urlparse(redirect_url)
        params = parse_qs(parsed.query)
        self.assertIn("code", params)
        self.assertEqual(params["state"][0], "state_123")
        raw_code = params["code"][0]

        # Product-side validation with M2M secret
        validate_res = client.post(
            "/api/v1/sso/validate/",
            {
                "code": raw_code,
                "client_identifier": fixture["sso_client"].client_identifier,
                "code_verifier": verifier,
            },
            HTTP_AUTHORIZATION=f"Bearer {TEST_M2M_SECRET}",
            format="json",
        )
        self.assertEqual(validate_res.status_code, 200)
        claims = validate_res.data
        self.assertEqual(claims["user"]["id"], str(fixture["user"].id))
        self.assertEqual(claims["user"]["email"], fixture["user"].email)
        self.assertEqual(claims["organization"]["id"], str(fixture["org"].id))
        self.assertEqual(claims["product"]["id"], str(fixture["product"].id))
        self.assertEqual(claims["assignment_id"], str(fixture["assignment"].id))

        # Assert code is now marked used in DB and plaintext code is never stored
        code_obj = SsoAuthorizationCode.objects.get(
            code_hash=hashlib.sha256(raw_code.encode()).hexdigest()
        )
        self.assertIsNotNone(code_obj.used_at)
        self.assertFalse(hasattr(code_obj, "code"))
        self.assertFalse(hasattr(code_obj, "raw_code"))
        self.assertNotEqual(code_obj.code_hash, raw_code)
        self.assertEqual(code_obj.code_hash, hashlib.sha256(raw_code.encode()).hexdigest())


@override_settings(VIBECONNECT_LMS_M2M_SECRET=TEST_M2M_SECRET)
class SsoPkceVerificationFailedRejectedTest(TestCase):
    """AC-5C-6: Incorrect PKCE verifier rejected with PKCE_VERIFICATION_FAILED."""

    def test_pkce_incorrect_verifier_rejected(self):
        import base64
        import hashlib
        from urllib.parse import parse_qs, urlparse

        fixture = _sso_setup()
        client = APIClient()
        client.force_authenticate(user=fixture["user"])

        correct_verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
        digest = hashlib.sha256(correct_verifier.encode("ascii")).digest()
        challenge = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")

        launch_res = client.post(
            "/api/v1/sso/launch/",
            {
                "product_id": str(fixture["product"].id),
                "organization_id": str(fixture["org"].id),
                "code_challenge": challenge,
                "code_challenge_method": "S256",
            },
            format="json",
        )
        self.assertEqual(launch_res.status_code, 200)
        parsed = urlparse(launch_res.data["redirect_url"])
        raw_code = parse_qs(parsed.query)["code"][0]

        # Validate with incorrect verifier
        val_res = client.post(
            "/api/v1/sso/validate/",
            {
                "code": raw_code,
                "client_identifier": fixture["sso_client"].client_identifier,
                "code_verifier": "wrong-verifier-12345678901234567890123456789012",
            },
            HTTP_AUTHORIZATION=f"Bearer {TEST_M2M_SECRET}",
            format="json",
        )
        self.assertEqual(val_res.status_code, 400)
        self.assertEqual(val_res.data["error"], "PKCE_VERIFICATION_FAILED")


class SsoUnconfiguredTenantRejectedTest(TestCase):
    """AC-5C-7: Tenant without an active ConnectorInstance is rejected on SSO launch."""

    def test_unconfigured_tenant_rejected_on_sso_launch(self):
        fixture = _sso_setup()
        # Remove active connector instance
        fixture["connector_instance"].delete()

        client = APIClient()
        client.force_authenticate(user=fixture["user"])

        launch_res = client.post(
            "/api/v1/sso/launch/",
            {
                "product_id": str(fixture["product"].id),
                "organization_id": str(fixture["org"].id),
            },
            format="json",
        )
        self.assertEqual(launch_res.status_code, 400)
        self.assertEqual(launch_res.data["error"], "INTEGRATION_NOT_CONFIGURED")


@override_settings(VIBECONNECT_LMS_M2M_SECRET=TEST_M2M_SECRET)
class SsoReusedCodeRejectedTest(TestCase):
    """AC-5C-2: Reused authorization code rejected with error."""

    def test_reused_code_rejected(self):
        from urllib.parse import parse_qs, urlparse

        fixture = _sso_setup()
        client = APIClient()
        client.force_authenticate(user=fixture["user"])

        launch_res = client.post(
            "/api/v1/sso/launch/",
            {
                "product_id": str(fixture["product"].id),
                "organization_id": str(fixture["org"].id),
            },
            format="json",
        )
        self.assertEqual(launch_res.status_code, 200)
        parsed = urlparse(launch_res.data["redirect_url"])
        raw_code = parse_qs(parsed.query)["code"][0]

        # First validate succeeds
        val1 = client.post(
            "/api/v1/sso/validate/",
            {"code": raw_code, "client_identifier": fixture["sso_client"].client_identifier},
            HTTP_AUTHORIZATION=f"Bearer {TEST_M2M_SECRET}",
            format="json",
        )
        self.assertEqual(val1.status_code, 200)

        # Second validate must be rejected
        val2 = client.post(
            "/api/v1/sso/validate/",
            {"code": raw_code, "client_identifier": fixture["sso_client"].client_identifier},
            HTTP_AUTHORIZATION=f"Bearer {TEST_M2M_SECRET}",
            format="json",
        )
        self.assertEqual(val2.status_code, 400)
        self.assertEqual(val2.data["error"], "CODE_ALREADY_USED")


@override_settings(VIBECONNECT_LMS_M2M_SECRET=TEST_M2M_SECRET)
class SsoExpiredCodeRejectedTest(TestCase):
    """AC-5C-3: Expired authorization code rejected."""

    def test_expired_code_rejected(self):
        from urllib.parse import parse_qs, urlparse
        from apps.integration_hub.models import SsoAuthorizationCode

        fixture = _sso_setup()
        client = APIClient()
        client.force_authenticate(user=fixture["user"])

        launch_res = client.post(
            "/api/v1/sso/launch/",
            {
                "product_id": str(fixture["product"].id),
                "organization_id": str(fixture["org"].id),
            },
            format="json",
        )
        self.assertEqual(launch_res.status_code, 200)
        parsed = urlparse(launch_res.data["redirect_url"])
        raw_code = parse_qs(parsed.query)["code"][0]

        # Force expiry in the past
        SsoAuthorizationCode.objects.filter(
            sso_client=fixture["sso_client"]
        ).update(expires_at=timezone.now() - timedelta(minutes=10))

        val = client.post(
            "/api/v1/sso/validate/",
            {"code": raw_code, "client_identifier": fixture["sso_client"].client_identifier},
            HTTP_AUTHORIZATION=f"Bearer {TEST_M2M_SECRET}",
            format="json",
        )
        self.assertEqual(val.status_code, 400)
        self.assertEqual(val.data["error"], "CODE_EXPIRED")


class SsoRedirectMismatchRejectedTest(TestCase):
    """AC-5C-4: Redirect URI mismatch strictly rejected."""

    def test_redirect_mismatch_rejected(self):
        fixture = _sso_setup()
        client = APIClient()
        client.force_authenticate(user=fixture["user"])

        launch_res = client.post(
            "/api/v1/sso/launch/",
            {
                "product_id": str(fixture["product"].id),
                "organization_id": str(fixture["org"].id),
                "redirect_uri": "https://attacker.site/callback",
            },
            format="json",
        )
        self.assertEqual(launch_res.status_code, 400)
        self.assertEqual(launch_res.data["error"], "REDIRECT_URI_MISMATCH")


@override_settings(VIBECONNECT_LMS_M2M_SECRET=TEST_M2M_SECRET)
class SsoAssignmentRevokedRejectedTest(TestCase):
    """AC-5C-5: User's assignment revoked between launch and validate rejected."""

    def test_assignment_revoked_before_validate_rejected(self):
        from urllib.parse import parse_qs, urlparse
        from apps.assignments.models import AssignmentStatus

        fixture = _sso_setup()
        client = APIClient()
        client.force_authenticate(user=fixture["user"])

        launch_res = client.post(
            "/api/v1/sso/launch/",
            {
                "product_id": str(fixture["product"].id),
                "organization_id": str(fixture["org"].id),
            },
            format="json",
        )
        self.assertEqual(launch_res.status_code, 200)
        parsed = urlparse(launch_res.data["redirect_url"])
        raw_code = parse_qs(parsed.query)["code"][0]

        # Revoke user's assignment with required revoked_at timestamp
        fixture["assignment"].status = AssignmentStatus.REVOKED
        fixture["assignment"].revoked_at = timezone.now()
        fixture["assignment"].save(update_fields=["status", "revoked_at"])

        val = client.post(
            "/api/v1/sso/validate/",
            {"code": raw_code, "client_identifier": fixture["sso_client"].client_identifier},
            HTTP_AUTHORIZATION=f"Bearer {TEST_M2M_SECRET}",
            format="json",
        )
        self.assertEqual(val.status_code, 403)
        self.assertEqual(val.data["error"], "ASSIGNMENT_REVOKED")


@override_settings(VIBECONNECT_LMS_M2M_SECRET=TEST_M2M_SECRET)
class SsoValidateM2MAuthenticationTest(TestCase):
    """M2M Authentication security tests for /api/v1/sso/validate/."""

    def test_missing_authorization_header_rejected(self):
        fixture = _sso_setup()
        client = APIClient()
        res = client.post(
            "/api/v1/sso/validate/",
            {"code": "dummy-code", "client_identifier": fixture["sso_client"].client_identifier},
            format="json",
        )
        self.assertEqual(res.status_code, 401)
        self.assertEqual(res.data.get("error"), "AUTHENTICATION_REQUIRED")
        self.assertIn("WWW-Authenticate", res.headers)
        self.assertNotIn(TEST_M2M_SECRET, str(res.data))

    def test_malformed_authorization_header_rejected(self):
        fixture = _sso_setup()
        client = APIClient()
        # Non-bearer scheme
        res1 = client.post(
            "/api/v1/sso/validate/",
            {"code": "dummy-code"},
            HTTP_AUTHORIZATION=f"Basic {TEST_M2M_SECRET}",
            format="json",
        )
        self.assertEqual(res1.status_code, 401)
        self.assertEqual(res1.data.get("error"), "INVALID_TOKEN_HEADER")

        # Bearer without token
        res2 = client.post(
            "/api/v1/sso/validate/",
            {"code": "dummy-code"},
            HTTP_AUTHORIZATION="Bearer",
            format="json",
        )
        self.assertEqual(res2.status_code, 401)
        self.assertEqual(res2.data.get("error"), "INVALID_TOKEN_HEADER")

    def test_wrong_bearer_secret_rejected(self):
        fixture = _sso_setup()
        client = APIClient()
        res = client.post(
            "/api/v1/sso/validate/",
            {"code": "dummy-code"},
            HTTP_AUTHORIZATION="Bearer wrong-secret-token-xyz",
            format="json",
        )
        self.assertEqual(res.status_code, 403)
        self.assertEqual(res.data.get("error"), "FORBIDDEN")
        self.assertNotIn(TEST_M2M_SECRET, str(res.data))

    def test_valid_bearer_secret_accepted_and_secret_never_exposed(self):
        from urllib.parse import parse_qs, urlparse
        fixture = _sso_setup()
        client = APIClient()
        client.force_authenticate(user=fixture["user"])

        # Master-initiated launch
        launch_res = client.post(
            "/api/v1/sso/launch/",
            {
                "product_id": str(fixture["product"].id),
                "organization_id": str(fixture["org"].id),
            },
            format="json",
        )
        self.assertEqual(launch_res.status_code, 200)
        raw_code = parse_qs(urlparse(launch_res.data["redirect_url"]).query)["code"][0]

        # S2S M2M validate
        m2m_client = APIClient()
        val_res = m2m_client.post(
            "/api/v1/sso/validate/",
            {
                "code": raw_code,
                "client_identifier": fixture["sso_client"].client_identifier,
            },
            HTTP_AUTHORIZATION=f"Bearer {TEST_M2M_SECRET}",
            format="json",
        )
        self.assertEqual(val_res.status_code, 200)
        self.assertEqual(val_res.data["user"]["id"], str(fixture["user"].id))
        self.assertNotIn(TEST_M2M_SECRET, str(val_res.data))


@override_settings(VIBECONNECT_LMS_M2M_SECRET=TEST_M2M_SECRET)
class SsoMasterInitiatedNoPkceLaunchTest(TestCase):
    """Verifies the master-initiated pilot flow operates without browser PKCE."""

    def test_master_initiated_no_pkce_round_trip(self):
        from urllib.parse import parse_qs, urlparse
        from apps.integration_hub.models import SsoAuthorizationCode

        fixture = _sso_setup()
        client = APIClient()
        client.force_authenticate(user=fixture["user"])

        # 1. Master-initiated launch with NO code_challenge
        launch_res = client.post(
            "/api/v1/sso/launch/",
            {
                "product_id": str(fixture["product"].id),
                "organization_id": str(fixture["org"].id),
                "state": "state_master_flow",
            },
            format="json",
        )
        self.assertEqual(launch_res.status_code, 200)
        redirect_url = launch_res.data["redirect_url"]
        parsed = urlparse(redirect_url)
        params = parse_qs(parsed.query)
        self.assertIn("code", params)
        self.assertEqual(params["state"][0], "state_master_flow")
        raw_code = params["code"][0]

        # Verify SsoAuthorizationCode has null code_challenge
        auth_code_obj = SsoAuthorizationCode.objects.get(
            sso_client=fixture["sso_client"],
            user=fixture["user"],
        )
        self.assertIsNone(auth_code_obj.code_challenge)

        # 2. Server-to-server validate with NO code_verifier (or None)
        m2m_client = APIClient()
        val_res = m2m_client.post(
            "/api/v1/sso/validate/",
            {
                "code": raw_code,
                "client_identifier": fixture["sso_client"].client_identifier,
                "code_verifier": None,
                "expected_org_id": str(fixture["org"].id),
                "expected_product_id": str(fixture["product"].id),
            },
            HTTP_AUTHORIZATION=f"Bearer {TEST_M2M_SECRET}",
            format="json",
        )
        self.assertEqual(val_res.status_code, 200)
        claims = val_res.data
        self.assertEqual(claims["user"]["id"], str(fixture["user"].id))
        self.assertEqual(claims["user"]["email"], fixture["user"].email)
        self.assertEqual(claims["organization"]["id"], str(fixture["org"].id))
        self.assertEqual(claims["organization"]["code"], fixture["org"].code)
        self.assertEqual(claims["product"]["id"], str(fixture["product"].id))
        self.assertEqual(claims["product"]["code"], fixture["product"].code)
        self.assertEqual(claims["assignment_id"], str(fixture["assignment"].id))
        self.assertEqual(claims["audience"], fixture["sso_client"].audience)


@override_settings(VIBECONNECT_LMS_M2M_SECRET=TEST_M2M_SECRET)
class SsoSecurityValidationBoundariesTest(TestCase):
    """Tests security validation boundaries in code exchange."""

    def _get_raw_code(self, fixture, with_pkce=False, challenge=None):
        from urllib.parse import parse_qs, urlparse
        client = APIClient()
        client.force_authenticate(user=fixture["user"])
        payload = {
            "product_id": str(fixture["product"].id),
            "organization_id": str(fixture["org"].id),
        }
        if with_pkce and challenge:
            payload["code_challenge"] = challenge
            payload["code_challenge_method"] = "S256"
        res = client.post("/api/v1/sso/launch/", payload, format="json")
        self.assertEqual(res.status_code, 200)
        return parse_qs(urlparse(res.data["redirect_url"]).query)["code"][0]

    def test_client_mismatch_rejected(self):
        fixture = _sso_setup()
        raw_code = self._get_raw_code(fixture)

        m2m_client = APIClient()
        res = m2m_client.post(
            "/api/v1/sso/validate/",
            {
                "code": raw_code,
                "client_identifier": "foreign_client_id",
            },
            HTTP_AUTHORIZATION=f"Bearer {TEST_M2M_SECRET}",
            format="json",
        )
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.data.get("error"), "CLIENT_MISMATCH")

    def test_tenant_mismatch_rejected(self):
        fixture = _sso_setup()
        raw_code = self._get_raw_code(fixture)

        m2m_client = APIClient()
        res = m2m_client.post(
            "/api/v1/sso/validate/",
            {
                "code": raw_code,
                "client_identifier": fixture["sso_client"].client_identifier,
                "expected_org_id": str(uuid.uuid4()),
            },
            HTTP_AUTHORIZATION=f"Bearer {TEST_M2M_SECRET}",
            format="json",
        )
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.data.get("error"), "TENANT_MISMATCH")

    def test_product_mismatch_rejected(self):
        fixture = _sso_setup()
        raw_code = self._get_raw_code(fixture)

        m2m_client = APIClient()
        res = m2m_client.post(
            "/api/v1/sso/validate/",
            {
                "code": raw_code,
                "client_identifier": fixture["sso_client"].client_identifier,
                "expected_product_id": str(uuid.uuid4()),
            },
            HTTP_AUTHORIZATION=f"Bearer {TEST_M2M_SECRET}",
            format="json",
        )
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.data.get("error"), "PRODUCT_MISMATCH")

    def test_pkce_enforced_when_challenge_present(self):
        import base64
        import hashlib
        fixture = _sso_setup()
        verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
        digest = hashlib.sha256(verifier.encode("ascii")).digest()
        challenge = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
        raw_code = self._get_raw_code(fixture, with_pkce=True, challenge=challenge)

        m2m_client = APIClient()
        # Missing verifier when challenge exists
        res = m2m_client.post(
            "/api/v1/sso/validate/",
            {
                "code": raw_code,
                "client_identifier": fixture["sso_client"].client_identifier,
            },
            HTTP_AUTHORIZATION=f"Bearer {TEST_M2M_SECRET}",
            format="json",
        )
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.data.get("error"), "PKCE_VERIFIER_REQUIRED")


class SsoLaunchAccessControlTest(TestCase):
    """Tests launch-time access control, entitlements, and tenant checks."""

    def test_unassigned_user_cannot_launch(self):
        fixture = _sso_setup()
        unassigned_user = PlatformUser.objects.create_user(
            email=f"unassigned_{uuid.uuid4().hex[:8]}@test.io",
            password="pass",
        )
        client = APIClient()
        client.force_authenticate(user=unassigned_user)

        res = client.post(
            "/api/v1/sso/launch/",
            {
                "product_id": str(fixture["product"].id),
                "organization_id": str(fixture["org"].id),
            },
            format="json",
        )
        self.assertEqual(res.status_code, 403)

    def test_cross_tenant_launch_rejected(self):
        fixture = _sso_setup()
        other_owner = _owner()
        other_org = _org(owner=other_owner)
        ConnectorInstance.objects.create(
            connector=fixture["connector"],
            organization=other_org,
            label="Other Org LMS Instance",
            credential_ref="vault://other-instance",
            status=InstanceStatus.ACTIVE,
        )

        client = APIClient()
        client.force_authenticate(user=fixture["user"])

        res = client.post(
            "/api/v1/sso/launch/",
            {
                "product_id": str(fixture["product"].id),
                "organization_id": str(other_org.id),
            },
            format="json",
        )
        self.assertEqual(res.status_code, 403)

    def test_inactive_sso_client_rejected(self):
        fixture = _sso_setup()
        fixture["sso_client"].is_active = False
        fixture["sso_client"].save(update_fields=["is_active"])

        client = APIClient()
        client.force_authenticate(user=fixture["user"])

        res = client.post(
            "/api/v1/sso/launch/",
            {
                "product_id": str(fixture["product"].id),
                "organization_id": str(fixture["org"].id),
            },
            format="json",
        )
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.data.get("error"), "SSO_NOT_CONFIGURED")


# =============================================================================
# Phase 5D: LMS Identity Reconciliation Backend Tests
# =============================================================================


class LmsReconciliationDeactivatedUserTest(TestCase):
    """AC-5D-1: Detects user deactivated or suspended after mapping created."""

    def test_reconciliation_detects_deactivated_user(self):
        from apps.identity.models import UserStatus
        from apps.integration_hub.reconciliation_service import run_lms_reconciliation

        inst = _instance()
        user = _owner()
        ExternalUserMapping.objects.create(
            user=user,
            organization=inst.organization,
            instance=inst,
            external_user_id="ext_user_deact_1",
        )

        user.is_active = False
        user.status = UserStatus.SUSPENDED
        user.save(update_fields=["is_active", "status"])

        issues = run_lms_reconciliation(instance_id=str(inst.id))
        self.assertTrue(
            any(
                i.issue_code == "USER_INACTIVE_OR_SUSPENDED" and i.subject_id == str(user.id)
                for i in issues
            ),
            "Expected USER_INACTIVE_OR_SUSPENDED issue for deactivated user",
        )


class LmsReconciliationRetiredOrganizationTest(TestCase):
    """AC-5D-2: Detects organization retired after mapping created."""

    def test_reconciliation_detects_retired_organization(self):
        from apps.organizations.models import OrganizationStatus
        from apps.integration_hub.reconciliation_service import run_lms_reconciliation

        inst = _instance()
        ExternalTenantMapping.objects.create(
            organization=inst.organization,
            instance=inst,
            external_tenant_id="ext_tenant_ret_1",
        )

        inst.organization.status = OrganizationStatus.RETIRED
        inst.organization.save(update_fields=["status"])

        issues = run_lms_reconciliation(instance_id=str(inst.id))
        self.assertTrue(
            any(
                i.issue_code == "ORGANIZATION_NOT_ACTIVE" and i.subject_id == str(inst.organization.id)
                for i in issues
            ),
            "Expected ORGANIZATION_NOT_ACTIVE issue for retired organization",
        )


class LmsReconciliationDuplicateExternalUserIdTest(TestCase):
    """AC-5D-3: Detects duplicate external_user_id on the same instance."""

    def test_reconciliation_detects_duplicate_external_user_id(self):
        from apps.integration_hub.reconciliation_service import run_lms_reconciliation

        inst = _instance()
        user1 = _owner()
        user2 = _owner()

        ExternalUserMapping.objects.create(
            user=user1,
            organization=inst.organization,
            instance=inst,
            external_user_id="pilot_dup_user",
        )
        # Case variation satisfies DB unique constraint but represents duplicate external user
        ExternalUserMapping.objects.create(
            user=user2,
            organization=inst.organization,
            instance=inst,
            external_user_id="PILOT_DUP_USER",
        )

        issues = run_lms_reconciliation(instance_id=str(inst.id))
        self.assertTrue(
            any(
                i.issue_code == "DUPLICATE_EXTERNAL_USER" and i.subject_id == "pilot_dup_user"
                for i in issues
            ),
            "Expected DUPLICATE_EXTERNAL_USER issue detected",
        )


class LmsReconciliationMarkResolvedAuditTest(TestCase):
    """AC-5D-4: Mark-resolved action records audit details."""

    def test_reconciliation_mark_resolved_audit(self):
        from apps.integration_hub.models import (
            IntegrationReconciliationIssue,
            IntegrationReconciliationStatus,
        )

        inst = _instance()
        issue = IntegrationReconciliationIssue.objects.create(
            instance=inst,
            issue_code="TEST_ANOMALY",
            subject_type="mapping",
            subject_id="sub_test_001",
            status=IntegrationReconciliationStatus.OPEN,
        )

        owner = _owner()
        client = APIClient()
        client.force_authenticate(user=owner)

        res = client.post(
            f"/api/v1/integration/reconciliation/{issue.id}/resolve/",
            {"resolution_notes": "Reviewed in LMS and resolved mapping manually."},
            format="json",
        )
        self.assertEqual(res.status_code, 200)

        issue.refresh_from_db()
        self.assertEqual(issue.status, IntegrationReconciliationStatus.RESOLVED)
        self.assertEqual(issue.resolved_by, owner)
        self.assertIsNotNone(issue.resolved_at)
        self.assertEqual(issue.resolution_notes, "Reviewed in LMS and resolved mapping manually.")


# =============================================================================
# Phase 5E & 5F: Multi-Product Generic Integration Coexistence Tests
# =============================================================================


class MultiProductIntegrationCoexistenceTest(TestCase):
    """AC-5E/5F: Generic Integration Hub supports LMS, WMS, VMS, WorkHub, HRMS, and CRM without collisions."""

    def test_multi_product_connectors_and_instances_coexist(self):
        owner = _owner()
        org = _org(owner=owner)

        from apps.product_registry.models import Product, ProductStatus
        from apps.integration_hub.models import (
            IntegrationConnector,
            ConnectorInstance,
            InstanceStatus,
            ExternalTenantMapping,
        )

        products_spec = [
            ("lms", "Learning Management System", "lms_connector"),
            ("wms", "Warehouse Management System", "wms_connector"),
            ("vms", "Visitor Management System", "vms_connector"),
            ("workhub", "WorkHub", "workhub_connector"),
            ("hrms", "Human Resources Management System", "hrms_connector"),
            ("crm", "Customer Relationship Management", "crm_connector"),
        ]

        connectors = {}
        instances = {}

        for code, name, conn_code in products_spec:
            prod, _ = Product.objects.get_or_create(
                code=code,
                defaults={"name": name, "status": ProductStatus.ACTIVE, "created_by": owner, "updated_by": owner},
            )
            conn, _ = IntegrationConnector.objects.get_or_create(
                code=conn_code,
                defaults={"name": f"{name} Connector", "product": prod, "status": "active"},
            )
            connectors[code] = conn
            # Ensure connector points to exact product
            self.assertEqual(conn.product_id, prod.id)

            # Create an instance for this product on the same organization
            inst = ConnectorInstance.objects.create(
                connector=conn,
                organization=org,
                label=f"{name} Instance",
                credential_ref=f"vault://tenant/{org.code}/{code}",
                status=InstanceStatus.ACTIVE,
            )
            instances[code] = inst

        # Assert all 6 instances coexist on the same organization without collision
        self.assertEqual(ConnectorInstance.objects.filter(organization=org).count(), 6)

        # Assert mappings remain instance-scoped across disparate products
        tm_lms = ExternalTenantMapping.objects.create(
            organization=org,
            instance=instances["lms"],
            external_tenant_id="ext_tenant_shared_id",
        )
        tm_crm = ExternalTenantMapping.objects.create(
            organization=org,
            instance=instances["crm"],
            external_tenant_id="ext_tenant_shared_id",
        )
        self.assertNotEqual(tm_lms.instance_id, tm_crm.instance_id)
        self.assertEqual(tm_lms.external_tenant_id, tm_crm.external_tenant_id)


# =============================================================================
# Phase 5G: Integration Health, Retry, Dead-Letter & Recovery Tests
# =============================================================================


class FailureLifecycleAndRetryBackoffTest(TestCase):
    """AC-5G-1: Deterministic backoff, classification, retry scheduling, and dead-letter transitions."""

    def test_deterministic_backoff_calculation(self):
        from apps.integration_hub.retry_service import compute_backoff_delay
        self.assertEqual(compute_backoff_delay(1, base_seconds=60, factor=2), 60)
        self.assertEqual(compute_backoff_delay(2, base_seconds=60, factor=2), 120)
        self.assertEqual(compute_backoff_delay(3, base_seconds=60, factor=2), 240)
        # Caps at max_seconds
        self.assertEqual(compute_backoff_delay(10, base_seconds=60, factor=2, max_seconds=3600), 3600)

    def test_failure_classification(self):
        from apps.integration_hub.models import FailureType
        from apps.integration_hub.retry_service import classify_failure
        self.assertEqual(classify_failure("UPSTREAM_TIMEOUT"), FailureType.TRANSIENT)
        self.assertEqual(classify_failure("RATE_LIMITED"), FailureType.TRANSIENT)
        self.assertEqual(classify_failure("AUTHENTICATION_FAILED"), FailureType.PERMANENT)
        self.assertEqual(classify_failure("INVALID_SCHEMA"), FailureType.PERMANENT)

    def test_transient_failure_retry_lifecycle_and_exhaustion(self):
        from apps.integration_hub.models import FailureStatus, FailureType
        from apps.integration_hub.retry_service import schedule_failure_retry

        inst = _instance()
        job = ProvisioningJob.objects.create(
            instance=inst,
            organization=inst.organization,
            action="provision",
        )
        failure = IntegrationFailure.objects.create(
            job=job,
            failure_code="UPSTREAM_TIMEOUT",
            failure_type=FailureType.TRANSIENT,
            max_retries=2,
        )
        self.assertEqual(failure.status, FailureStatus.OPEN)
        self.assertEqual(failure.retry_count, 0)

        # Retry 1
        f1 = schedule_failure_retry(failure, base_seconds=30)
        self.assertEqual(f1.status, FailureStatus.RETRY_SCHEDULED)
        self.assertEqual(f1.retry_count, 1)
        self.assertIsNotNone(f1.retry_after)

        # Retry 2
        f2 = schedule_failure_retry(f1, base_seconds=30)
        self.assertEqual(f2.status, FailureStatus.RETRY_SCHEDULED)
        self.assertEqual(f2.retry_count, 2)

        # Retry 3 exceeds max_retries=2 -> transitions to DEAD_LETTER
        f3 = schedule_failure_retry(f2, base_seconds=30)
        self.assertEqual(f3.status, FailureStatus.DEAD_LETTER)
        self.assertIsNone(f3.retry_after)
        self.assertTrue(f3.is_dead_letter)

    def test_permanent_failure_transitions_directly_to_dead_letter(self):
        from apps.integration_hub.models import FailureStatus, FailureType
        from apps.integration_hub.retry_service import schedule_failure_retry

        inst = _instance()
        job = ProvisioningJob.objects.create(
            instance=inst,
            organization=inst.organization,
            action="provision",
        )
        failure = IntegrationFailure.objects.create(
            job=job,
            failure_code="AUTHENTICATION_FAILED",
            failure_type=FailureType.PERMANENT,
            max_retries=3,
        )
        # Attempting to schedule retry on permanent failure transitions straight to dead letter
        updated = schedule_failure_retry(failure)
        self.assertEqual(updated.status, FailureStatus.DEAD_LETTER)
        self.assertIsNone(updated.retry_after)


class FailureManualResolutionAuditTest(TestCase):
    """AC-5G-2: Platform Owner manual resolution with required audit notes."""

    def setUp(self):
        self.owner = _owner()
        self.client = APIClient()
        self.client.force_authenticate(user=self.owner)
        self.inst = _instance()
        self.job = ProvisioningJob.objects.create(
            instance=self.inst,
            organization=self.inst.organization,
            action="provision",
        )
        self.failure = IntegrationFailure.objects.create(
            job=self.job,
            failure_code="UPSTREAM_TIMEOUT",
            failure_detail="Connection timeout to upstream provider.",
        )

    def test_resolve_failure_success_with_audit_trail(self):
        from apps.integration_hub.models import FailureStatus

        res = self.client.post(
            f"/api/v1/integration/failures/{self.failure.id}/resolve/",
            {"resolution_notes": "Upstream service was rebooted and connection confirmed."},
            format="json",
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["status"], FailureStatus.RESOLVED)
        self.assertEqual(res.data["resolution_notes"], "Upstream service was rebooted and connection confirmed.")
        self.assertEqual(res.data["resolved_by_email"], self.owner.email)

        self.failure.refresh_from_db()
        self.assertEqual(self.failure.status, FailureStatus.RESOLVED)
        self.assertEqual(self.failure.resolved_by, self.owner)
        self.assertIsNotNone(self.failure.resolved_at)

    def test_resolve_failure_requires_non_blank_notes(self):
        res = self.client.post(
            f"/api/v1/integration/failures/{self.failure.id}/resolve/",
            {"resolution_notes": ""},
            format="json",
        )
        self.assertEqual(res.status_code, 400)


class FailureDeadLetterManualTransitionTest(TestCase):
    """AC-5G-3: Platform Owner can explicitly mark a failure as dead-letter."""

    def test_manual_dead_letter_transition(self):
        from apps.integration_hub.models import FailureStatus

        owner = _owner()
        client = APIClient()
        client.force_authenticate(user=owner)
        inst = _instance()
        job = ProvisioningJob.objects.create(
            instance=inst,
            organization=inst.organization,
            action="provision",
        )
        failure = IntegrationFailure.objects.create(
            job=job,
            failure_code="UNKNOWN_ERROR",
            failure_detail="Unexpected non-retryable response.",
        )

        res = client.post(
            f"/api/v1/integration/failures/{failure.id}/mark-dead-letter/",
            {"reason": "Triage determined unrecoverable corrupted data."},
            format="json",
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["status"], FailureStatus.DEAD_LETTER)
        self.assertTrue(res.data["is_dead_letter"])

        failure.refresh_from_db()
        self.assertEqual(failure.status, FailureStatus.DEAD_LETTER)
        self.assertIn("Triage determined unrecoverable corrupted data.", failure.failure_detail)


class FailureEndpointsAuthorizationAndTenantIsolationTest(TestCase):
    """AC-5G-4: RBAC enforcement and tenant/instance scoping."""

    def test_unauthenticated_and_non_owner_rejected(self):
        client = APIClient()
        inst = _instance()
        job = ProvisioningJob.objects.create(
            instance=inst,
            organization=inst.organization,
            action="provision",
        )
        failure = IntegrationFailure.objects.create(job=job, failure_code="ERR_1")

        # Unauthenticated
        r1 = client.get("/api/v1/integration/failures/")
        self.assertEqual(r1.status_code, 401)

        # Authenticated non-owner
        regular_user = PlatformUser.objects.create_user(email="member@test.io", password="pass")
        client.force_authenticate(user=regular_user)
        r2 = client.get("/api/v1/integration/failures/")
        self.assertEqual(r2.status_code, 403)

        r3 = client.get(f"/api/v1/integration/failures/{failure.id}/")
        self.assertEqual(r3.status_code, 403)

    def test_instance_and_organization_filtering(self):
        owner = _owner()
        client = APIClient()
        client.force_authenticate(user=owner)

        org_a = _org("Alpha", owner=owner)
        org_b = _org("Beta", owner=owner)
        inst_a = _instance(organization=org_a)
        inst_b = _instance(organization=org_b)

        job_a = ProvisioningJob.objects.create(instance=inst_a, organization=org_a, action="provision")
        job_b = ProvisioningJob.objects.create(instance=inst_b, organization=org_b, action="provision")

        fail_a = IntegrationFailure.objects.create(job=job_a, failure_code="FAIL_ALPHA")
        fail_b = IntegrationFailure.objects.create(job=job_b, failure_code="FAIL_BETA")

        # Filter by inst_a
        res_a = client.get(f"/api/v1/integration/failures/?instance={inst_a.id}")
        self.assertEqual(res_a.status_code, 200)
        returned_ids_a = [f["id"] for f in res_a.data["results"]]
        self.assertIn(str(fail_a.id), returned_ids_a)
        self.assertNotIn(str(fail_b.id), returned_ids_a)

        # Filter by org_b
        res_b = client.get(f"/api/v1/integration/failures/?organization={org_b.id}")
        self.assertEqual(res_b.status_code, 200)
        returned_ids_b = [f["id"] for f in res_b.data["results"]]
        self.assertIn(str(fail_b.id), returned_ids_b)
        self.assertNotIn(str(fail_a.id), returned_ids_b)


class IntegrationHealthSummaryEndpointTest(TestCase):
    """AC-5G-5: Aggregated operational control-plane health summary."""

    def test_health_summary_returns_control_plane_and_unverified_connectivity(self):
        owner = _owner()
        client = APIClient()
        client.force_authenticate(user=owner)

        inst = _instance()
        job = ProvisioningJob.objects.create(instance=inst, organization=inst.organization, action="provision")
        IntegrationFailure.objects.create(job=job, failure_code="HEALTH_ERR_1", status="open")
        IntegrationFailure.objects.create(job=job, failure_code="HEALTH_ERR_2", status="dead_letter")

        res = client.get("/api/v1/integration/health/")
        self.assertEqual(res.status_code, 200)

        # Control plane metrics
        self.assertIn("control_plane", res.data)
        cp = res.data["control_plane"]
        self.assertIn(cp["status"], ["healthy", "degraded", "attention_required"])
        self.assertGreaterEqual(cp["total_connectors"], 1)
        self.assertGreaterEqual(cp["total_instances"], 1)

        # Failures breakdown
        self.assertIn("failures", res.data)
        self.assertGreaterEqual(res.data["failures"]["total_open"], 1)
        self.assertGreaterEqual(res.data["failures"]["total_dead_letter"], 1)

        # Instance breakdown
        self.assertIn("instance_health", res.data)
        self.assertTrue(any(ih["id"] == str(inst.id) for ih in res.data["instance_health"]))

        # Explicit transparency: external connectivity is NOT claimed healthy
        self.assertIn("external_connectivity", res.data)
        ext = res.data["external_connectivity"]
        self.assertEqual(ext["status"], "not_verified")
        self.assertEqual(ext["verified_connectors_count"], 0)
        self.assertIn("Control-plane layer only", ext["detail"])


class SetupLmsPilotTest(TestCase):
    """Regression test: setup_lms_pilot establishes lms_core module baseline idempotently."""

    def test_setup_lms_pilot_establishes_lms_core_module_baseline(self):
        from django.core.management import call_command
        from apps.product_registry.models import Product, ProductModule, CatalogStatus

        owner = _owner()
        lms = Product.objects.create(
            code="lms",
            name="Learning Management System",
            status=CatalogStatus.ACTIVE,
            created_by=owner,
            updated_by=owner,
        )

        call_command("setup_lms_pilot")

        core_mod = ProductModule.objects.get(product=lms, code="lms_core")
        self.assertEqual(core_mod.status, CatalogStatus.ACTIVE)
        self.assertEqual(core_mod.name, "LMS Core Module")

        # Running again is idempotent and does not create duplicate
        call_command("setup_lms_pilot")
        self.assertEqual(ProductModule.objects.filter(product=lms, code="lms_core").count(), 1)

