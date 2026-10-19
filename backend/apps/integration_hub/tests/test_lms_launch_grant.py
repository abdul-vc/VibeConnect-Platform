"""Focused tests for LMS launch-grant SSO integration in Product Launch and Showcase."""

import io
import json
from unittest.mock import MagicMock, patch
import urllib.error

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.assignments.constants import AccessState
from apps.assignments.models import (
    AssignmentStatus,
    UserModuleAssignment,
    UserProductAssignment,
)
from apps.auditlog.models import AuditLog
from apps.entitlements.models import EntitlementStatus, OrganizationProductEntitlement
from apps.identity.models import PlatformUser
from apps.integration_hub.lms_launch_grant_client import (
    ALLOWED_LMS_FRONTEND_HOST,
    LmsLaunchGrantAuthError,
    LmsLaunchGrantConflictError,
    LmsLaunchGrantConnectionError,
    LmsLaunchGrantConfigurationError,
    LmsLaunchGrantError,
    LmsLaunchGrantForbiddenError,
    LmsLaunchGrantNotFoundError,
    get_lms_api_base_url,
    get_lms_frontend_url,
    is_lms_launch_grant_configured,
    request_lms_launch_grant,
    validate_lms_callback_url,
)
from apps.integration_hub.models import (
    ConnectorInstance,
    ExternalTenantMapping,
    ExternalUserMapping,
    ExternalUserMappingStatus,
    InstanceStatus,
    IntegrationConnector,
    ProductSsoClient,
    ProvisioningAction,
    ProvisioningJob,
    ProvisioningJobStatus,
    SsoAuthorizationCode,
)
from apps.integration_hub.sso_views import SsoLaunchView, SsoPilotStatusView
from apps.organizations.models import (
    MembershipStatus,
    MembershipType,
    Organization,
    OrganizationMembership,
    OrganizationStatus,
)
from apps.product_registry.models import (
    CatalogStatus,
    Product,
    ProductModule,
    ProductStatus,
)
from apps.showcase.models import (
    ProductDemoEnvironment,
    ProductLaunchConfig,
    ProductShowcaseProfile,
    ShowcaseVisibility,
)
from apps.showcase.services import ProductShowcaseService, ShowcaseServiceError

TEST_LMS_SECRET = "lms-test-launch-grant-secret-12345"
TEST_LMS_BACKEND_URL = "https://lms.vibesandbox.live"
VALID_LMS_CALLBACK = "https://lms.vibesandbox.live/sso/vibeconnect/callback?code=lms-code-abc-123"


class LmsLaunchGrantClientTests(TestCase):
    """Unit tests for lms_launch_grant_client functions."""

    def test_is_lms_launch_grant_configured_truthiness(self):
        with override_settings(LMS_LAUNCH_GRANT_M2M_SECRET=""):
            self.assertFalse(is_lms_launch_grant_configured())
        with override_settings(LMS_LAUNCH_GRANT_M2M_SECRET=TEST_LMS_SECRET):
            self.assertTrue(is_lms_launch_grant_configured())

    def test_get_lms_api_base_url_success(self):
        with override_settings(VIBECONNECT_LMS_BACKEND_URL="https://lms.vibesandbox.live/"):
            self.assertEqual(get_lms_api_base_url(), "https://lms.vibesandbox.live")

    def test_get_lms_api_base_url_missing_raises_configuration_error(self):
        with override_settings(VIBECONNECT_LMS_BACKEND_URL=""):
            with patch.dict("os.environ", {"VIBECONNECT_LMS_BACKEND_URL": ""}):
                with self.assertRaises(LmsLaunchGrantConfigurationError) as ctx:
                    get_lms_api_base_url()
                self.assertIn("LMS backend URL is not configured", str(ctx.exception))

    def test_validate_lms_callback_url_valid(self):
        validate_lms_callback_url(VALID_LMS_CALLBACK)

    def test_validate_lms_callback_url_rejects_non_https(self):
        with self.assertRaises(LmsLaunchGrantError) as ctx:
            validate_lms_callback_url("http://lms.vibesandbox.live/sso/vibeconnect/callback?code=123")
        self.assertIn("HTTPS", str(ctx.exception))

    def test_validate_lms_callback_url_rejects_wrong_host(self):
        with self.assertRaises(LmsLaunchGrantError) as ctx:
            validate_lms_callback_url("https://malicious.org/sso/vibeconnect/callback?code=123")
        self.assertIn("does not match expected host", str(ctx.exception))

    def test_validate_lms_callback_url_rejects_wrong_path(self):
        with self.assertRaises(LmsLaunchGrantError) as ctx:
            validate_lms_callback_url("https://lms.vibesandbox.live/sso/wrong/path?code=123")
        self.assertIn("does not match expected callback path", str(ctx.exception))

    def test_validate_lms_callback_url_rejects_missing_query(self):
        with self.assertRaises(LmsLaunchGrantError) as ctx:
            validate_lms_callback_url("https://lms.vibesandbox.live/sso/vibeconnect/callback")
        self.assertIn("missing required launch authorization parameters", str(ctx.exception))

    def test_validate_lms_callback_url_rejects_missing_code_parameter(self):
        with self.assertRaises(LmsLaunchGrantError) as ctx:
            validate_lms_callback_url("https://lms.vibesandbox.live/sso/vibeconnect/callback?other=value")
        self.assertIn("missing required non-empty 'code'", str(ctx.exception))

    def test_validate_lms_callback_url_rejects_empty_code_parameter(self):
        with self.assertRaises(LmsLaunchGrantError) as ctx:
            validate_lms_callback_url("https://lms.vibesandbox.live/sso/vibeconnect/callback?code=")
        self.assertIn("missing required non-empty 'code'", str(ctx.exception))

    @override_settings(
        LMS_LAUNCH_GRANT_M2M_SECRET=TEST_LMS_SECRET,
        VIBECONNECT_LMS_BACKEND_URL=TEST_LMS_BACKEND_URL,
    )
    def test_request_lms_launch_grant_success(self):
        mock_response_data = {
            "callback_url": VALID_LMS_CALLBACK,
            "expires_in": 60,
            "context": "standard",
        }

        with patch("urllib.request.build_opener") as mock_opener_cls:
            mock_opener = MagicMock()
            mock_opener_cls.return_value = mock_opener

            mock_http_resp = MagicMock()
            mock_http_resp.status = 200
            mock_http_resp.read.return_value = json.dumps(mock_response_data).encode("utf-8")
            mock_opener.open.return_value.__enter__.return_value = mock_http_resp

            result = request_lms_launch_grant(
                external_tenant_id="tenant-uuid-1",
                external_user_id="user-uuid-1",
                context="standard",
            )

            self.assertEqual(result["callback_url"], VALID_LMS_CALLBACK)
            self.assertEqual(result["expires_in"], 60)
            self.assertEqual(result["context"], "standard")

            mock_opener.open.assert_called_once()
            called_req = mock_opener.open.call_args[0][0]
            self.assertEqual(called_req.method, "POST")
            self.assertEqual(
                called_req.full_url,
                "https://lms.vibesandbox.live/api/v1/integration/launch-grant/",
            )
            self.assertEqual(
                called_req.headers.get("Authorization"),
                f"Bearer {TEST_LMS_SECRET}",
            )
            self.assertEqual(
                called_req.headers.get("Content-type"),
                "application/json",
            )

            sent_payload = json.loads(called_req.data.decode("utf-8"))
            self.assertEqual(sent_payload["external_tenant_id"], "tenant-uuid-1")
            self.assertEqual(sent_payload["external_user_id"], "user-uuid-1")
            self.assertEqual(sent_payload["context"], "standard")

    @override_settings(
        LMS_LAUNCH_GRANT_M2M_SECRET=TEST_LMS_SECRET,
        VIBECONNECT_LMS_BACKEND_URL=TEST_LMS_BACKEND_URL,
    )
    def test_request_lms_launch_grant_unauthorized_raises_auth_error(self):
        with patch("urllib.request.build_opener") as mock_opener_cls:
            mock_opener = MagicMock()
            mock_opener_cls.return_value = mock_opener

            err = urllib.error.HTTPError(
                url="https://lms.vibesandbox.live/api/v1/integration/launch-grant/",
                code=401,
                msg="Unauthorized",
                hdrs={},
                fp=io.BytesIO(b'{"detail": "Invalid launch grant secret"}'),
            )
            mock_opener.open.side_effect = err

            with self.assertRaises(LmsLaunchGrantAuthError) as ctx:
                request_lms_launch_grant(
                    external_tenant_id="org-1",
                    external_user_id="user-1",
                )
            self.assertEqual(ctx.exception.status_code, 401)
            self.assertIn("Invalid launch grant secret", ctx.exception.detail)

    @override_settings(
        LMS_LAUNCH_GRANT_M2M_SECRET=TEST_LMS_SECRET,
        VIBECONNECT_LMS_BACKEND_URL=TEST_LMS_BACKEND_URL,
    )
    def test_request_lms_launch_grant_forbidden_raises_forbidden_error(self):
        with patch("urllib.request.build_opener") as mock_opener_cls:
            mock_opener = MagicMock()
            mock_opener_cls.return_value = mock_opener

            err = urllib.error.HTTPError(
                url="https://lms.vibesandbox.live/api/v1/integration/launch-grant/",
                code=403,
                msg="Forbidden",
                hdrs={},
                fp=io.BytesIO(b'{"detail": "Showcase launch requires designated platform super administrator identity."}'),
            )
            mock_opener.open.side_effect = err

            with self.assertRaises(LmsLaunchGrantForbiddenError) as ctx:
                request_lms_launch_grant(
                    external_tenant_id="org-1",
                    external_user_id="user-1",
                )
            self.assertEqual(ctx.exception.status_code, 403)
            self.assertIn("Showcase launch requires designated platform super administrator identity.", ctx.exception.detail)

    @override_settings(
        LMS_LAUNCH_GRANT_M2M_SECRET=TEST_LMS_SECRET,
        VIBECONNECT_LMS_BACKEND_URL=TEST_LMS_BACKEND_URL,
    )
    def test_request_lms_launch_grant_conflict_raises_conflict_error(self):
        with patch("urllib.request.build_opener") as mock_opener_cls:
            mock_opener = MagicMock()
            mock_opener_cls.return_value = mock_opener

            err = urllib.error.HTTPError(
                url="https://lms.vibesandbox.live/api/v1/integration/launch-grant/",
                code=409,
                msg="Conflict",
                hdrs={},
                fp=io.BytesIO(b'{"detail": "User mapping conflict on external tenant"}'),
            )
            mock_opener.open.side_effect = err

            with self.assertRaises(LmsLaunchGrantConflictError) as ctx:
                request_lms_launch_grant(
                    external_tenant_id="org-1",
                    external_user_id="user-1",
                )
            self.assertEqual(ctx.exception.status_code, 409)
            self.assertIn("mapping conflict", ctx.exception.detail)

    @override_settings(
        LMS_LAUNCH_GRANT_M2M_SECRET=TEST_LMS_SECRET,
        VIBECONNECT_LMS_BACKEND_URL=TEST_LMS_BACKEND_URL,
    )
    def test_request_lms_launch_grant_not_found_raises_not_found_error(self):
        with patch("urllib.request.build_opener") as mock_opener_cls:
            mock_opener = MagicMock()
            mock_opener_cls.return_value = mock_opener

            err = urllib.error.HTTPError(
                url="https://lms.vibesandbox.live/api/v1/integration/launch-grant/",
                code=404,
                msg="Not Found",
                hdrs={},
                fp=io.BytesIO(b'{"detail": "User \'usr-1\' is not provisioned in LMS. Provision user first."}'),
            )
            mock_opener.open.side_effect = err

            with self.assertRaises(LmsLaunchGrantNotFoundError) as ctx:
                request_lms_launch_grant(
                    external_tenant_id="org-1",
                    external_user_id="usr-1",
                )
            self.assertEqual(ctx.exception.status_code, 404)
            self.assertIn("not provisioned in LMS", ctx.exception.detail)

    @override_settings(
        LMS_LAUNCH_GRANT_M2M_SECRET=TEST_LMS_SECRET,
        VIBECONNECT_LMS_BACKEND_URL=TEST_LMS_BACKEND_URL,
    )
    def test_request_lms_launch_grant_connection_error(self):
        with patch("urllib.request.build_opener") as mock_opener_cls:
            mock_opener = MagicMock()
            mock_opener_cls.return_value = mock_opener

            mock_opener.open.side_effect = urllib.error.URLError("Connection refused")

            with self.assertRaises(LmsLaunchGrantConnectionError):
                request_lms_launch_grant(
                    external_tenant_id="org-1",
                    external_user_id="user-1",
                )

    @override_settings(
        LMS_LAUNCH_GRANT_M2M_SECRET=TEST_LMS_SECRET,
        VIBECONNECT_LMS_BACKEND_URL=TEST_LMS_BACKEND_URL,
    )
    def test_request_lms_launch_grant_non_json_response(self):
        with patch("urllib.request.build_opener") as mock_opener_cls:
            mock_opener = MagicMock()
            mock_opener_cls.return_value = mock_opener

            mock_http_resp = MagicMock()
            mock_http_resp.status = 200
            mock_http_resp.read.return_value = b"<html>Bad Gateway</html>"
            mock_opener.open.return_value.__enter__.return_value = mock_http_resp

            with self.assertRaises(LmsLaunchGrantError) as ctx:
                request_lms_launch_grant(
                    external_tenant_id="org-1",
                    external_user_id="user-1",
                )
            self.assertIn("malformed non-JSON", str(ctx.exception))


class LmsSsoLaunchViewTests(TestCase):
    """Integration tests for SsoLaunchView and SsoPilotStatusView with LMS product."""

    def setUp(self):
        self.factory = APIRequestFactory()
        self.user = PlatformUser.objects.create(
            email="learner@alphacorp.com",
            full_name="Learner Alpha",
            is_active=True,
        )
        self.org = Organization.objects.create(
            name="Alpha Corp",
            code="alpha-corp",
            status=OrganizationStatus.ACTIVE,
            created_by=self.user,
            updated_by=self.user,
        )
        self.membership = OrganizationMembership.objects.create(
            organization=self.org,
            user=self.user,
            membership_type=MembershipType.MEMBER,
            status=MembershipStatus.ACTIVE,
            joined_at=timezone.now(),
        )
        self.lms_product = Product.objects.create(
            code="lms",
            name="Learning Management System",
            status=ProductStatus.ACTIVE,
            created_by=self.user,
            updated_by=self.user,
        )
        self.connector = IntegrationConnector.objects.create(
            code="lms",
            name="LMS Connector",
            product=self.lms_product,
        )
        self.instance = ConnectorInstance.objects.create(
            connector=self.connector,
            organization=self.org,
            status=InstanceStatus.ACTIVE,
        )
        self.sso_client = ProductSsoClient.objects.create(
            product=self.lms_product,
            client_identifier="lms_legacy_client",
            callback_uri="https://lms.vibesandbox.live/sso/callback",
            is_active=True,
        )
        self.assignment = UserProductAssignment.objects.create(
            user=self.user,
            organization=self.org,
            membership=self.membership,
            product=self.lms_product,
            status=AssignmentStatus.ACTIVE,
            created_by=self.user,
            updated_by=self.user,
        )
        self.module = ProductModule.objects.create(
            product=self.lms_product,
            code="lms_core",
            name="LMS Core Module",
            status=CatalogStatus.ACTIVE,
            created_by=self.user,
            updated_by=self.user,
        )
        self.entitlement = OrganizationProductEntitlement.objects.create(
            organization=self.org,
            product=self.lms_product,
            status=EntitlementStatus.ACTIVE,
            created_by=self.user,
            updated_by=self.user,
        )
        self.module_assignment = UserModuleAssignment.objects.create(
            assignment=self.assignment,
            module=self.module,
            is_enabled=True,
        )

        self.tenant_mapping = ExternalTenantMapping.objects.create(
            instance=self.instance,
            organization=self.org,
            external_tenant_id="lms-ext-tenant-1",
        )
        self.user_mapping = ExternalUserMapping.objects.create(
            instance=self.instance,
            organization=self.org,
            user=self.user,
            external_user_id="lms-ext-user-1",
            status=ExternalUserMappingStatus.ACTIVE,
        )

    def _mock_effective_access(self, entitled=True):
        return {
            "entitled_products": [
                {
                    "id": str(self.lms_product.id),
                    "code": "lms",
                    "access_state": AccessState.AVAILABLE if entitled else AccessState.SUSPENDED,
                    "is_entitled": entitled,
                }
            ],
            "products": [
                {
                    "id": str(self.lms_product.id),
                    "code": "lms",
                    "is_entitled": entitled,
                    "denial_code": None if entitled else "PAYMENT_PAST_DUE",
                }
            ],
        }

    @override_settings(
        LMS_LAUNCH_GRANT_M2M_SECRET="",
        VIBECONNECT_LMS_BACKEND_URL=TEST_LMS_BACKEND_URL,
    )
    def test_launch_when_unconfigured_preserves_legacy_flow(self):
        """When LMS_LAUNCH_GRANT_M2M_SECRET is empty, legacy issue_sso_authorization_code runs."""
        with patch("apps.assignments.services.effective_access.compute_user_tenant_effective_access") as mock_eff:
            mock_eff.return_value = self._mock_effective_access(entitled=True)

            request = self.factory.post(
                "/api/v1/sso/launch/",
                {"product_id": str(self.lms_product.id), "organization_id": str(self.org.id)},
                format="json",
            )
            force_authenticate(request, user=self.user)
            response = SsoLaunchView.as_view()(request)

            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertIn("redirect_url", response.data)
            self.assertIn("expires_at", response.data)
            # Legacy code was created in database
            self.assertTrue(SsoAuthorizationCode.objects.filter(user=self.user, product=self.lms_product).exists())

    @override_settings(
        LMS_LAUNCH_GRANT_M2M_SECRET=TEST_LMS_SECRET,
        VIBECONNECT_LMS_BACKEND_URL=TEST_LMS_BACKEND_URL,
    )
    def test_launch_when_configured_success(self):
        """When configured, requests grant and returns validated callback_url without creating auth code."""
        with patch("apps.assignments.services.effective_access.compute_user_tenant_effective_access") as mock_eff:
            mock_eff.return_value = self._mock_effective_access(entitled=True)

            with patch("apps.integration_hub.sso_views.request_lms_launch_grant") as mock_grant:
                mock_grant.return_value = {
                    "callback_url": VALID_LMS_CALLBACK,
                    "expires_in": 60,
                    "context": "standard",
                }

                request = self.factory.post(
                    "/api/v1/sso/launch/",
                    {"product_id": str(self.lms_product.id), "organization_id": str(self.org.id)},
                    format="json",
                )
                force_authenticate(request, user=self.user)
                response = SsoLaunchView.as_view()(request)

                self.assertEqual(response.status_code, status.HTTP_200_OK)
                self.assertEqual(response.data["redirect_url"], VALID_LMS_CALLBACK)
                self.assertFalse(response.data["direct_launch"])

                # Identity passed must come from trusted server records
                mock_grant.assert_called_once_with(
                    external_tenant_id=str(self.org.id),
                    external_user_id=str(self.user.id),
                    context="standard",
                    target_route="/dashboard",
                )

                # No VibeConnect-side authorization code created
                self.assertFalse(
                    SsoAuthorizationCode.objects.filter(user=self.user, product=self.lms_product).exists()
                )

    @override_settings(
        LMS_LAUNCH_GRANT_M2M_SECRET=TEST_LMS_SECRET,
        VIBECONNECT_LMS_BACKEND_URL=TEST_LMS_BACKEND_URL,
    )
    def test_launch_when_provisioning_pending_returns_409(self):
        """When a provisioning job is queued or processing, launch fails with 409 PROVISIONING_PENDING."""
        with patch("apps.assignments.services.effective_access.compute_user_tenant_effective_access") as mock_eff:
            mock_eff.return_value = self._mock_effective_access(entitled=True)

            ProvisioningJob.objects.create(
                instance=self.instance,
                organization=self.org,
                user=self.user,
                action=ProvisioningAction.PROVISION,
                status=ProvisioningJobStatus.PROCESSING,
            )

            request = self.factory.post(
                "/api/v1/sso/launch/",
                {"product_id": str(self.lms_product.id), "organization_id": str(self.org.id)},
                format="json",
            )
            force_authenticate(request, user=self.user)
            response = SsoLaunchView.as_view()(request)

            self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
            self.assertEqual(response.data["error"], "PROVISIONING_PENDING")

    @override_settings(
        LMS_LAUNCH_GRANT_M2M_SECRET=TEST_LMS_SECRET,
        VIBECONNECT_LMS_BACKEND_URL=TEST_LMS_BACKEND_URL,
    )
    def test_launch_when_provisioning_failed_returns_409(self):
        """When a provisioning job failed without resolved mappings, returns 409 PROVISIONING_FAILED."""
        self.tenant_mapping.delete()
        self.user_mapping.delete()
        with patch("apps.assignments.services.effective_access.compute_user_tenant_effective_access") as mock_eff:
            mock_eff.return_value = self._mock_effective_access(entitled=True)

            ProvisioningJob.objects.create(
                instance=self.instance,
                organization=self.org,
                user=self.user,
                action=ProvisioningAction.PROVISION,
                status=ProvisioningJobStatus.FAILED,
            )

            request = self.factory.post(
                "/api/v1/sso/launch/",
                {"product_id": str(self.lms_product.id), "organization_id": str(self.org.id)},
                format="json",
            )
            force_authenticate(request, user=self.user)
            response = SsoLaunchView.as_view()(request)

            self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
            self.assertEqual(response.data["error"], "PROVISIONING_FAILED")

    @override_settings(
        LMS_LAUNCH_GRANT_M2M_SECRET=TEST_LMS_SECRET,
        VIBECONNECT_LMS_BACKEND_URL=TEST_LMS_BACKEND_URL,
    )
    def test_launch_when_remote_auth_fails_returns_502(self):
        """When remote LMS returns 401, SsoLaunchView returns 502 LMS_SSO_UNAUTHORIZED."""
        with patch("apps.assignments.services.effective_access.compute_user_tenant_effective_access") as mock_eff:
            mock_eff.return_value = self._mock_effective_access(entitled=True)

            with patch("apps.integration_hub.sso_views.request_lms_launch_grant") as mock_grant:
                mock_grant.side_effect = LmsLaunchGrantAuthError("M2M authentication failed.", status_code=401)

                request = self.factory.post(
                    "/api/v1/sso/launch/",
                    {"product_id": str(self.lms_product.id), "organization_id": str(self.org.id)},
                    format="json",
                )
                force_authenticate(request, user=self.user)
                response = SsoLaunchView.as_view()(request)

                self.assertEqual(response.status_code, status.HTTP_502_BAD_GATEWAY)
                self.assertEqual(response.data["error"], "LMS_SSO_UNAUTHORIZED")

    @override_settings(
        LMS_LAUNCH_GRANT_M2M_SECRET=TEST_LMS_SECRET,
        VIBECONNECT_LMS_BACKEND_URL=TEST_LMS_BACKEND_URL,
    )
    def test_pilot_status_when_configured(self):
        request = self.factory.get(
            f"/api/v1/sso/pilot-status/?product_id={self.lms_product.id}&organization_id={self.org.id}"
        )
        force_authenticate(request, user=self.user)
        response = SsoPilotStatusView.as_view()(request)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["sso_enabled"])
        self.assertEqual(response.data["client_identifier"], "lms_launch_grant")

    @override_settings(
        LMS_LAUNCH_GRANT_M2M_SECRET="",
        VIBECONNECT_LMS_BACKEND_URL=TEST_LMS_BACKEND_URL,
    )
    def test_pilot_status_when_unconfigured(self):
        request = self.factory.get(
            f"/api/v1/sso/pilot-status/?product_id={self.lms_product.id}&organization_id={self.org.id}"
        )
        force_authenticate(request, user=self.user)
        response = SsoPilotStatusView.as_view()(request)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["sso_enabled"])
    @override_settings(
        LMS_LAUNCH_GRANT_M2M_SECRET=TEST_LMS_SECRET,
        VIBECONNECT_LMS_BACKEND_URL=TEST_LMS_BACKEND_URL,
    )
    def test_launch_missing_upstream_mapping_triggers_idempotent_provisioning_and_succeeds(self):
        """When upstream returns 404, launch view calls idempotent provisioning and retries."""
        with patch("apps.assignments.services.effective_access.compute_user_tenant_effective_access") as mock_eff:
            mock_eff.return_value = self._mock_effective_access(entitled=True)

            with patch("apps.integration_hub.sso_views.request_lms_launch_grant") as mock_grant, \
                 patch("apps.integration_hub.sso_views.provision_tenant_to_lms") as mock_prov_tenant, \
                 patch("apps.integration_hub.sso_views.provision_user_to_lms") as mock_prov_user:

                # First call fails with 404 (user not provisioned upstream), second call succeeds
                mock_grant.side_effect = [
                    LmsLaunchGrantNotFoundError("User not provisioned in LMS", status_code=404),
                    {
                        "callback_url": "https://lms.vibesandbox.live/sso/vibeconnect/callback?code=recovered-code-123",
                        "expires_in": 60,
                        "context": "standard",
                    },
                ]

                request = self.factory.post(
                    "/api/v1/sso/launch/",
                    {"product_id": str(self.lms_product.id), "organization_id": str(self.org.id)},
                    format="json",
                )
                force_authenticate(request, user=self.user)
                response = SsoLaunchView.as_view()(request)

                self.assertEqual(response.status_code, status.HTTP_200_OK)
                self.assertIn("recovered-code-123", response.data["redirect_url"])
                mock_prov_tenant.assert_called_once_with(self.org)
                mock_prov_user.assert_called_once_with(self.user, self.org)
                self.assertEqual(mock_grant.call_count, 2)

    @override_settings(
        LMS_LAUNCH_GRANT_M2M_SECRET=TEST_LMS_SECRET,
        VIBECONNECT_LMS_BACKEND_URL=TEST_LMS_BACKEND_URL,
    )
    def test_launch_tenant_admin_sets_org_admin_target_route(self):
        """When an authenticated tenant admin launches LMS, target_route is /org-admin."""
        # Update membership to TENANT_ADMIN with role
        from apps.access_control.models import Role
        admin_role = Role.objects.create(
            organization=self.org,
            code="test_tenant_admin_role",
            name="Test Tenant Admin",
        )
        self.membership.role = admin_role
        self.membership.membership_type = MembershipType.TENANT_ADMIN
        self.membership.save()

        with patch("apps.assignments.services.effective_access.compute_user_tenant_effective_access") as mock_eff:
            mock_eff.return_value = self._mock_effective_access(entitled=True)

            with patch("apps.integration_hub.sso_views.request_lms_launch_grant") as mock_grant:
                mock_grant.return_value = {
                    "callback_url": "https://lms.vibesandbox.live/sso/vibeconnect/callback?code=admin-code-123",
                    "expires_in": 60,
                    "context": "standard",
                }

                request = self.factory.post(
                    "/api/v1/sso/launch/",
                    {"product_id": str(self.lms_product.id), "organization_id": str(self.org.id)},
                    format="json",
                )
                force_authenticate(request, user=self.user)
                response = SsoLaunchView.as_view()(request)

                self.assertEqual(response.status_code, status.HTTP_200_OK)
                mock_grant.assert_called_once_with(
                    external_tenant_id=str(self.org.id),
                    external_user_id=str(self.user.id),
                    context="standard",
                    target_route="/org-admin",
                )

    @override_settings(
        LMS_LAUNCH_GRANT_M2M_SECRET=TEST_LMS_SECRET,
        VIBECONNECT_LMS_BACKEND_URL=TEST_LMS_BACKEND_URL,
    )
    def test_launch_member_sets_dashboard_target_route(self):
        """When a standard member launches LMS, target_route is /dashboard."""
        self.membership.membership_type = MembershipType.MEMBER
        self.membership.save()

        with patch("apps.assignments.services.effective_access.compute_user_tenant_effective_access") as mock_eff:
            mock_eff.return_value = self._mock_effective_access(entitled=True)

            with patch("apps.integration_hub.sso_views.request_lms_launch_grant") as mock_grant:
                mock_grant.return_value = {
                    "callback_url": "https://lms.vibesandbox.live/sso/vibeconnect/callback?code=member-code-123",
                    "expires_in": 60,
                    "context": "standard",
                }

                request = self.factory.post(
                    "/api/v1/sso/launch/",
                    {"product_id": str(self.lms_product.id), "organization_id": str(self.org.id)},
                    format="json",
                )
                force_authenticate(request, user=self.user)
                response = SsoLaunchView.as_view()(request)

                self.assertEqual(response.status_code, status.HTTP_200_OK)
                mock_grant.assert_called_once_with(
                    external_tenant_id=str(self.org.id),
                    external_user_id=str(self.user.id),
                    context="standard",
                    target_route="/dashboard",
                )

    @override_settings(
        LMS_LAUNCH_GRANT_M2M_SECRET=TEST_LMS_SECRET,
        VIBECONNECT_LMS_BACKEND_URL=TEST_LMS_BACKEND_URL,
    )
    def test_repeated_launches_reuse_existing_mappings_without_duplicates(self):
        """Repeated launches work safely without duplicating organization or user mappings."""
        with patch("apps.assignments.services.effective_access.compute_user_tenant_effective_access") as mock_eff:
            mock_eff.return_value = self._mock_effective_access(entitled=True)

            with patch("apps.integration_hub.sso_views.request_lms_launch_grant") as mock_grant:
                mock_grant.return_value = {
                    "callback_url": "https://lms.vibesandbox.live/sso/vibeconnect/callback?code=reuse-code-123",
                    "expires_in": 60,
                    "context": "standard",
                }

                # Launch 1
                req1 = self.factory.post(
                    "/api/v1/sso/launch/",
                    {"product_id": str(self.lms_product.id), "organization_id": str(self.org.id)},
                    format="json",
                )
                force_authenticate(req1, user=self.user)
                res1 = SsoLaunchView.as_view()(req1)
                self.assertEqual(res1.status_code, status.HTTP_200_OK)

                # Launch 2
                req2 = self.factory.post(
                    "/api/v1/sso/launch/",
                    {"product_id": str(self.lms_product.id), "organization_id": str(self.org.id)},
                    format="json",
                )
                force_authenticate(req2, user=self.user)
                res2 = SsoLaunchView.as_view()(req2)
                self.assertEqual(res2.status_code, status.HTTP_200_OK)

                # Verify mapping counts remain 1
                self.assertEqual(ExternalTenantMapping.objects.filter(organization=self.org).count(), 1)
                self.assertEqual(
                    ExternalUserMapping.objects.filter(organization=self.org, user=self.user).count(),
                    1,
                )


class LmsShowcaseLaunchTests(TestCase):
    """Tests for LMS Product Showcase launchability contract and launch_demo."""

    def setUp(self):
        self.owner = PlatformUser.objects.create(
            email="owner@vibeconnect.internal",
            full_name="Platform Owner",
            is_platform_owner=True,
            is_active=True,
        )
        self.demo_user = PlatformUser.objects.create(
            email="superadmin@gmail.com",
            full_name="Platform Superadmin",
            is_active=True,
        )
        self.demo_org = Organization.objects.create(
            name="Boss Demo Org",
            code="boss-demo-org",
            status=OrganizationStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )
        self.membership = OrganizationMembership.objects.create(
            organization=self.demo_org,
            user=self.demo_user,
            membership_type=MembershipType.MEMBER,
            status=MembershipStatus.ACTIVE,
            joined_at=timezone.now(),
        )
        self.lms_product = Product.objects.create(
            code="lms",
            name="Learning Management System",
            status=ProductStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )
        self.connector = IntegrationConnector.objects.create(
            code="lms",
            name="LMS Connector",
            product=self.lms_product,
        )
        self.instance = ConnectorInstance.objects.create(
            connector=self.connector,
            organization=self.demo_org,
            status=InstanceStatus.ACTIVE,
        )
        self.assignment = UserProductAssignment.objects.create(
            user=self.demo_user,
            organization=self.demo_org,
            membership=self.membership,
            product=self.lms_product,
            status=AssignmentStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )
        self.profile = ProductShowcaseProfile.objects.create(
            product=self.lms_product,
            tagline="Enterprise Learning Experience",
            overview="Empower your workforce with modern LMS",
            visibility=ShowcaseVisibility.PUBLISHED,
            created_by=self.owner,
            updated_by=self.owner,
        )
        self.target_env = ProductDemoEnvironment.objects.create(
            product=self.lms_product,
            name="LMS Sandbox",
            base_url="https://lms.vibesandbox.live/",
            is_active=True,
            created_by=self.owner,
            updated_by=self.owner,
        )
        self.launch_config = ProductLaunchConfig.objects.create(
            profile=self.profile,
            product=self.lms_product,
            target_environment=self.target_env,
            launch_mode=ProductLaunchConfig.LaunchMode.DEMO_ONLY,
            policy={
                "demo_organization_code": "boss-demo-org",
                "demo_user_email": "superadmin@gmail.com",
            },
            created_by=self.owner,
            updated_by=self.owner,
        )

    def _mock_effective_access(self):
        return {
            "entitled_products": [
                {
                    "id": str(self.lms_product.id),
                    "code": "lms",
                    "access_state": AccessState.AVAILABLE,
                    "is_entitled": True,
                }
            ],
            "products": [],
        }

    @override_settings(
        LMS_LAUNCH_GRANT_M2M_SECRET=TEST_LMS_SECRET,
        VIBECONNECT_LMS_BACKEND_URL=TEST_LMS_BACKEND_URL,
    )
    def test_showcase_contract_reports_missing_tenant_mapping(self):
        with patch("apps.assignments.services.effective_access.compute_user_tenant_effective_access") as mock_eff:
            mock_eff.return_value = self._mock_effective_access()

            contract = ProductShowcaseService.launchability_contract(profile_id=str(self.profile.id))
            self.assertFalse(contract["launchable"])
            self.assertEqual(contract["reason"], "DEMO_TENANT_MAPPING_MISSING")

    @override_settings(
        LMS_LAUNCH_GRANT_M2M_SECRET=TEST_LMS_SECRET,
        VIBECONNECT_LMS_BACKEND_URL=TEST_LMS_BACKEND_URL,
    )
    def test_showcase_contract_reports_missing_user_mapping(self):
        with patch("apps.assignments.services.effective_access.compute_user_tenant_effective_access") as mock_eff:
            mock_eff.return_value = self._mock_effective_access()

            ExternalTenantMapping.objects.create(
                instance=self.instance,
                organization=self.demo_org,
                external_tenant_id="lms-demo-tenant-99",
            )

            contract = ProductShowcaseService.launchability_contract(profile_id=str(self.profile.id))
            self.assertFalse(contract["launchable"])
            self.assertEqual(contract["reason"], "DEMO_USER_MAPPING_MISSING")

    @override_settings(
        LMS_LAUNCH_GRANT_M2M_SECRET=TEST_LMS_SECRET,
        VIBECONNECT_LMS_BACKEND_URL=TEST_LMS_BACKEND_URL,
    )
    def test_showcase_launch_success_with_demo_identity(self):
        """Showcase launch passes demo user ID and demo tenant ID, and sets Platform Owner as audit actor."""
        with patch("apps.assignments.services.effective_access.compute_user_tenant_effective_access") as mock_eff:
            mock_eff.return_value = self._mock_effective_access()

            ExternalTenantMapping.objects.create(
                instance=self.instance,
                organization=self.demo_org,
                external_tenant_id="lms-demo-tenant-99",
            )
            ExternalUserMapping.objects.create(
                instance=self.instance,
                organization=self.demo_org,
                user=self.demo_user,
                external_user_id="lms-demo-user-88",
                status=ExternalUserMappingStatus.ACTIVE,
            )

            with patch("apps.showcase.services.request_lms_launch_grant") as mock_grant:
                mock_grant.return_value = {
                    "callback_url": VALID_LMS_CALLBACK,
                    "expires_in": 60,
                    "context": "showcase",
                }

                result = ProductShowcaseService.launch_demo(
                    profile_id=str(self.profile.id),
                    actor=self.owner,
                )

                self.assertEqual(result["redirect_url"], VALID_LMS_CALLBACK)
                self.assertEqual(result["demo_user"], self.demo_user.email)
                self.assertEqual(result["demo_organization"], "boss-demo-org")

                # Verify grant parameters: must be demo identity, context="showcase"
                mock_grant.assert_called_once_with(
                    external_tenant_id=str(self.demo_org.id),
                    external_user_id=str(self.demo_user.id),
                    context="showcase",
                    target_route="/super-admin/dashboard",
                )

                # Verify audit event: actor is the Platform Owner
                audit_entry = AuditLog.objects.filter(
                    target_id=str(self.profile.id),
                    actor=self.owner,
                ).last()
                self.assertIsNotNone(audit_entry)
                self.assertEqual(audit_entry.metadata.get("context"), "showcase")
                self.assertEqual(audit_entry.metadata.get("demo_user"), self.demo_user.email)

    @override_settings(
        LMS_LAUNCH_GRANT_M2M_SECRET=TEST_LMS_SECRET,
        VIBECONNECT_LMS_BACKEND_URL=TEST_LMS_BACKEND_URL,
    )
    def test_showcase_launch_demo_self_heals_on_404(self):
        """When showcase launch grant returns 404, showcase service provisions tenant and user, then retries."""
        with patch("apps.assignments.services.effective_access.compute_user_tenant_effective_access") as mock_eff:
            mock_eff.return_value = self._mock_effective_access()

            ExternalTenantMapping.objects.create(
                instance=self.instance,
                organization=self.demo_org,
                external_tenant_id="lms-demo-tenant-99",
            )
            ExternalUserMapping.objects.create(
                instance=self.instance,
                organization=self.demo_org,
                user=self.demo_user,
                external_user_id="lms-demo-user-88",
                status=ExternalUserMappingStatus.ACTIVE,
            )

            with patch("apps.showcase.services.request_lms_launch_grant") as mock_grant, \
                 patch("apps.integration_hub.provisioning_service.provision_tenant_to_lms") as mock_prov_t, \
                 patch("apps.integration_hub.provisioning_service.provision_user_to_lms") as mock_prov_u:

                mock_grant.side_effect = [
                    LmsLaunchGrantNotFoundError("Demo user not provisioned in LMS", status_code=404),
                    {
                        "callback_url": VALID_LMS_CALLBACK,
                        "expires_in": 60,
                        "context": "showcase",
                    },
                ]

                result = ProductShowcaseService.launch_demo(
                    profile_id=str(self.profile.id),
                    actor=self.owner,
                )

                self.assertEqual(result["redirect_url"], VALID_LMS_CALLBACK)
                self.assertEqual(mock_grant.call_count, 2)
                mock_prov_t.assert_called_once_with(self.demo_org, instance=self.instance)
                mock_prov_u.assert_called_once_with(self.demo_user, self.demo_org, instance=self.instance)

    @override_settings(
        LMS_LAUNCH_GRANT_M2M_SECRET=TEST_LMS_SECRET,
        VIBECONNECT_LMS_BACKEND_URL=TEST_LMS_BACKEND_URL,
    )
    def test_showcase_launch_demo_distinguishes_403_forbidden(self):
        """Showcase launch cleanly differentiates 403 authorization denied with diagnostic detail."""
        with patch("apps.assignments.services.effective_access.compute_user_tenant_effective_access") as mock_eff:
            mock_eff.return_value = self._mock_effective_access()

            ExternalTenantMapping.objects.create(
                instance=self.instance,
                organization=self.demo_org,
                external_tenant_id="lms-demo-tenant-99",
            )
            ExternalUserMapping.objects.create(
                instance=self.instance,
                organization=self.demo_org,
                user=self.demo_user,
                external_user_id="lms-demo-user-88",
                status=ExternalUserMappingStatus.ACTIVE,
            )

            with patch("apps.showcase.services.request_lms_launch_grant") as mock_grant:
                mock_grant.side_effect = LmsLaunchGrantForbiddenError(
                    "LMS launch-grant authorization denied: Showcase launch requires designated platform super administrator identity.",
                    status_code=403,
                    detail="Showcase launch requires designated platform super administrator identity.",
                )

                with self.assertRaises(ShowcaseServiceError) as ctx:
                    ProductShowcaseService.launch_demo(
                        profile_id=str(self.profile.id),
                        actor=self.owner,
                    )

                self.assertIn("LMS showcase access denied", str(ctx.exception))
                self.assertIn("Showcase launch requires designated platform super administrator identity.", str(ctx.exception))
