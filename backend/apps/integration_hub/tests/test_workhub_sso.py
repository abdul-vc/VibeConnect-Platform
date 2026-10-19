"""Focused tests for WorkHub SSO integration in Product Showcase."""

import json
from unittest.mock import MagicMock, patch
import urllib.error

from django.test import TestCase, override_settings

from apps.auditlog.models import AuditLog
from apps.identity.models import PlatformUser
from apps.integration_hub.workhub_sso_client import (
    WorkHubSsoAuthError,
    WorkHubSsoConflictError,
    WorkHubSsoConnectionError,
    WorkHubSsoError,
    WorkHubSsoForbiddenError,
    WorkHubSsoNotFoundError,
    is_workhub_sso_configured,
    request_workhub_launch_grant,
    validate_workhub_callback_url,
)
from apps.product_registry.models import Product, ProductStatus
from apps.showcase.models import (
    ProductDemoEnvironment,
    ProductLaunchConfig,
    ProductShowcaseProfile,
    ShowcaseVisibility,
)
from apps.showcase.services import ProductShowcaseService, ShowcaseServiceError

TEST_SECRET = "workhub-test-m2m-secret-xyz"
TEST_API_URL = "http://localhost:8002"
TEST_FRONTEND_URL = "http://localhost:6395"
VALID_CALLBACK = "http://localhost:6395/sso/callback?code=wh-grant-code-123&target=%2Fadmin"


class WorkHubSsoClientTests(TestCase):
    """Unit tests for workhub_sso_client functions."""

    def test_is_workhub_sso_configured(self):
        with override_settings(WORKHUB_SHOWCASE_M2M_SECRET=""):
            self.assertFalse(is_workhub_sso_configured())
        with override_settings(WORKHUB_SHOWCASE_M2M_SECRET=TEST_SECRET):
            self.assertTrue(is_workhub_sso_configured())

    def test_validate_workhub_callback_url_valid(self):
        with override_settings(WORKHUB_SHOWCASE_FRONTEND_URL=TEST_FRONTEND_URL):
            # Should not raise
            validate_workhub_callback_url(VALID_CALLBACK)

    def test_validate_workhub_callback_url_rejects_dangerous_scheme(self):
        with self.assertRaises(WorkHubSsoError) as ctx:
            validate_workhub_callback_url("javascript:alert(1)")
        self.assertIn("HTTP or HTTPS", str(ctx.exception))

    def test_validate_workhub_callback_url_rejects_wrong_host(self):
        with override_settings(WORKHUB_SHOWCASE_FRONTEND_URL="http://localhost:6395"):
            with self.assertRaises(WorkHubSsoError) as ctx:
                validate_workhub_callback_url("https://malicious.com:6395/sso/callback?code=123")
            self.assertIn("does not match expected host", str(ctx.exception))

    def test_validate_workhub_callback_url_rejects_wrong_path(self):
        with override_settings(WORKHUB_SHOWCASE_FRONTEND_URL=TEST_FRONTEND_URL):
            with self.assertRaises(WorkHubSsoError) as ctx:
                validate_workhub_callback_url("http://localhost:6395/admin?code=123")
            self.assertIn("does not match expected callback path", str(ctx.exception))

    def test_validate_workhub_callback_url_rejects_missing_query(self):
        with override_settings(WORKHUB_SHOWCASE_FRONTEND_URL=TEST_FRONTEND_URL):
            with self.assertRaises(WorkHubSsoError) as ctx:
                validate_workhub_callback_url("http://localhost:6395/sso/callback")
            self.assertIn("missing required launch authorization parameters", str(ctx.exception))

    @override_settings(
        WORKHUB_SHOWCASE_M2M_SECRET=TEST_SECRET,
        WORKHUB_SHOWCASE_API_BASE_URL=TEST_API_URL,
        WORKHUB_SHOWCASE_FRONTEND_URL=TEST_FRONTEND_URL,
        WORKHUB_SHOWCASE_ADMIN_USERNAME="admin",
    )
    @patch("urllib.request.build_opener")
    def test_request_workhub_launch_grant_payload_and_headers(self, mock_build_opener):
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = json.dumps({
            "callback_url": VALID_CALLBACK,
            "expires_in": 60,
        }).encode("utf-8")

        mock_opener = MagicMock()
        mock_opener.open.return_value.__enter__.return_value = mock_resp
        mock_build_opener.return_value = mock_opener

        res = request_workhub_launch_grant(
            username="admin",
            context="showcase",
            target_route="/admin",
        )

        self.assertEqual(res["callback_url"], VALID_CALLBACK)
        self.assertEqual(res["expires_in"], 60)
        self.assertEqual(res["username"], "admin")

        # Verify request headers and payload
        called_req = mock_opener.open.call_args[0][0]
        self.assertEqual(called_req.get_header("X-vibeconnect-secret"), TEST_SECRET)
        self.assertEqual(called_req.get_header("Authorization"), f"Bearer {TEST_SECRET}")
        body = json.loads(called_req.data.decode("utf-8"))
        self.assertEqual(body["username"], "admin")
        self.assertEqual(body["context"], "showcase")
        self.assertEqual(body["target_route"], "/admin")

    @override_settings(
        WORKHUB_SHOWCASE_M2M_SECRET=TEST_SECRET,
        WORKHUB_SHOWCASE_API_BASE_URL=TEST_API_URL,
    )
    @patch("urllib.request.build_opener")
    def test_request_workhub_launch_grant_auth_error(self, mock_build_opener):
        mock_opener = MagicMock()
        http_error = urllib.error.HTTPError(
            url=f"{TEST_API_URL}/api/v1/sso/launch-grant/",
            code=401,
            msg="Unauthorized",
            hdrs={},
            fp=MagicMock(read=lambda: b'{"detail": "Invalid M2M secret"}'),
        )
        mock_opener.open.side_effect = http_error
        mock_build_opener.return_value = mock_opener

        with self.assertRaises(WorkHubSsoAuthError):
            request_workhub_launch_grant(username="admin")

    @override_settings(
        WORKHUB_SHOWCASE_M2M_SECRET=TEST_SECRET,
        WORKHUB_SHOWCASE_API_BASE_URL=TEST_API_URL,
    )
    @patch("urllib.request.build_opener")
    def test_request_workhub_launch_grant_not_found(self, mock_build_opener):
        mock_opener = MagicMock()
        http_error = urllib.error.HTTPError(
            url=f"{TEST_API_URL}/api/v1/sso/launch-grant/",
            code=404,
            msg="Not Found",
            hdrs={},
            fp=MagicMock(read=lambda: b'{"detail": "Admin account not found"}'),
        )
        mock_opener.open.side_effect = http_error
        mock_build_opener.return_value = mock_opener

        with self.assertRaises(WorkHubSsoNotFoundError) as ctx:
            request_workhub_launch_grant(username="admin")
        self.assertIn("Admin account not found", ctx.exception.detail)


class WorkHubShowcaseServiceTests(TestCase):
    """Showcase integration tests for WorkHub."""

    def setUp(self):
        self.admin = PlatformUser.objects.create_user(
            email="platformowner@vibeconnect.internal",
            password="test-password-123",
            full_name="Platform Owner",
            is_platform_owner=True,
            is_staff=True,
        )
        self.product, _ = Product.objects.get_or_create(
            code="workhub",
            defaults={
                "name": "WorkHub",
                "status": ProductStatus.ACTIVE,
                "created_by": self.admin,
                "updated_by": self.admin,
            },
        )
        self.profile, _ = ProductShowcaseProfile.objects.get_or_create(
            product=self.product,
            defaults={
                "tagline": "WorkHub Platform",
                "visibility": ShowcaseVisibility.PUBLISHED,
                "created_by": self.admin,
                "updated_by": self.admin,
            },
        )
        self.demo_env, _ = ProductDemoEnvironment.objects.get_or_create(
            product=self.product,
            name="WorkHub Live",
            defaults={
                "base_url": "http://localhost:6395",
                "is_active": True,
                "created_by": self.admin,
                "updated_by": self.admin,
            },
        )
        self.launch_config, _ = ProductLaunchConfig.objects.get_or_create(
            product=self.product,
            defaults={
                "profile": self.profile,
                "launch_mode": ProductLaunchConfig.LaunchMode.DEMO_ONLY,
                "target_environment": self.demo_env,
                "allowed_targets": ["/admin"],
                "created_by": self.admin,
                "updated_by": self.admin,
            },
        )

    @override_settings(
        WORKHUB_SHOWCASE_M2M_SECRET=TEST_SECRET,
        WORKHUB_SHOWCASE_API_BASE_URL=TEST_API_URL,
        WORKHUB_SHOWCASE_FRONTEND_URL=TEST_FRONTEND_URL,
        WORKHUB_SHOWCASE_ADMIN_USERNAME="admin",
    )
    def test_launchability_contract_when_configured(self):
        contract = ProductShowcaseService.launchability_contract(profile_id=str(self.profile.id))
        self.assertTrue(contract["launchable"])
        self.assertEqual(contract["reason"], "READY")
        self.assertTrue(contract["sso_enabled"])
        self.assertEqual(contract["demo_user"], "admin")
        self.assertEqual(contract["allowed_targets"], ["/admin"])

    @override_settings(
        WORKHUB_SHOWCASE_M2M_SECRET="",
        WORKHUB_SHOWCASE_FRONTEND_URL=TEST_FRONTEND_URL,
    )
    def test_launchability_contract_when_unconfigured(self):
        contract = ProductShowcaseService.launchability_contract(profile_id=str(self.profile.id))
        self.assertTrue(contract["launchable"])
        self.assertFalse(contract["sso_enabled"])

    @override_settings(
        WORKHUB_SHOWCASE_M2M_SECRET=TEST_SECRET,
        WORKHUB_SHOWCASE_API_BASE_URL=TEST_API_URL,
        WORKHUB_SHOWCASE_FRONTEND_URL=TEST_FRONTEND_URL,
        WORKHUB_SHOWCASE_ADMIN_USERNAME="admin",
    )
    @patch("apps.integration_hub.workhub_sso_client.request_workhub_launch_grant")
    def test_launch_demo_success(self, mock_grant):
        mock_grant.return_value = {
            "callback_url": VALID_CALLBACK,
            "expires_in": 60,
        }

        res = ProductShowcaseService.launch_demo(
            profile_id=str(self.profile.id),
            actor=self.admin,
        )

        self.assertEqual(res["redirect_url"], VALID_CALLBACK)
        self.assertEqual(res["demo_user"], "admin")
        self.assertEqual(res["product_name"], "WorkHub")

        # Verify audit log was recorded
        audit = AuditLog.objects.filter(
            action="showcase_demo_launched",
            target_id=str(self.profile.id),
        ).first()
        self.assertIsNotNone(audit)
        self.assertEqual(audit.metadata.get("product_code"), "workhub")
        self.assertEqual(audit.metadata.get("designated_admin_username"), "admin")

    @override_settings(
        WORKHUB_SHOWCASE_M2M_SECRET=TEST_SECRET,
        WORKHUB_SHOWCASE_API_BASE_URL=TEST_API_URL,
        WORKHUB_SHOWCASE_FRONTEND_URL=TEST_FRONTEND_URL,
        WORKHUB_SHOWCASE_ADMIN_USERNAME="admin",
    )
    @patch("apps.integration_hub.workhub_sso_client.request_workhub_launch_grant")
    def test_launch_demo_reload_requests_fresh_grant(self, mock_grant):
        callback_1 = "http://localhost:6395/sso/callback?code=grant-1"
        callback_2 = "http://localhost:6395/sso/callback?code=grant-2"
        mock_grant.side_effect = [
            {"callback_url": callback_1, "expires_in": 60},
            {"callback_url": callback_2, "expires_in": 60},
        ]

        # Initial launch
        res1 = ProductShowcaseService.launch_demo(profile_id=str(self.profile.id), actor=self.admin)
        self.assertEqual(res1["redirect_url"], callback_1)

        # Reload launch
        res2 = ProductShowcaseService.launch_demo(profile_id=str(self.profile.id), actor=self.admin)
        self.assertEqual(res2["redirect_url"], callback_2)
        self.assertEqual(mock_grant.call_count, 2)
