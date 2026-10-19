"""Focused tests for Sales Tracker SSO integration in Product Showcase."""

import json
from unittest.mock import MagicMock, patch
import urllib.error

from django.test import TestCase, override_settings

from apps.auditlog.models import AuditLog
from apps.identity.models import PlatformUser
from apps.integration_hub.salestracker_sso_client import (
    SalesTrackerSsoAuthError,
    SalesTrackerSsoConflictError,
    SalesTrackerSsoConnectionError,
    SalesTrackerSsoError,
    SalesTrackerSsoForbiddenError,
    SalesTrackerSsoNotFoundError,
    is_salestracker_sso_configured,
    request_salestracker_launch_grant,
    validate_salestracker_callback_url,
)
from apps.product_registry.models import Product, ProductStatus
from apps.showcase.models import (
    ProductDemoEnvironment,
    ProductLaunchConfig,
    ProductShowcaseProfile,
    ShowcaseVisibility,
)
from apps.showcase.services import ProductShowcaseService, ShowcaseServiceError

TEST_SECRET = "salestracker-test-m2m-secret-xyz"
TEST_API_URL = "http://localhost:8000"
TEST_FRONTEND_URL = "http://localhost:5173"
VALID_CALLBACK = "http://localhost:5173/sso/callback?code=st-grant-code-123&target=%2Fdashboard"


class SalesTrackerSsoClientTests(TestCase):
    """Unit tests for salestracker_sso_client functions."""

    def test_is_salestracker_sso_configured(self):
        with override_settings(SALESTRACKER_SHOWCASE_M2M_SECRET=""):
            self.assertFalse(is_salestracker_sso_configured())
        with override_settings(SALESTRACKER_SHOWCASE_M2M_SECRET=TEST_SECRET):
            self.assertTrue(is_salestracker_sso_configured())

    def test_validate_salestracker_callback_url_valid(self):
        with override_settings(SALESTRACKER_SHOWCASE_FRONTEND_URL=TEST_FRONTEND_URL):
            # Should not raise
            validate_salestracker_callback_url(VALID_CALLBACK)

    def test_validate_salestracker_callback_url_rejects_dangerous_scheme(self):
        with self.assertRaises(SalesTrackerSsoError) as ctx:
            validate_salestracker_callback_url("javascript:alert(1)")
        self.assertIn("HTTP or HTTPS", str(ctx.exception))

    def test_validate_salestracker_callback_url_rejects_wrong_host(self):
        with override_settings(SALESTRACKER_SHOWCASE_FRONTEND_URL="http://localhost:5173"):
            with self.assertRaises(SalesTrackerSsoError) as ctx:
                validate_salestracker_callback_url("https://malicious.com:5173/sso/callback?code=123")
            self.assertIn("does not match expected host", str(ctx.exception))

    def test_validate_salestracker_callback_url_rejects_wrong_path(self):
        with override_settings(SALESTRACKER_SHOWCASE_FRONTEND_URL=TEST_FRONTEND_URL):
            with self.assertRaises(SalesTrackerSsoError) as ctx:
                validate_salestracker_callback_url("http://localhost:5173/dashboard?code=123")
            self.assertIn("does not match expected callback path", str(ctx.exception))

    def test_validate_salestracker_callback_url_rejects_missing_query(self):
        with override_settings(SALESTRACKER_SHOWCASE_FRONTEND_URL=TEST_FRONTEND_URL):
            with self.assertRaises(SalesTrackerSsoError) as ctx:
                validate_salestracker_callback_url("http://localhost:5173/sso/callback")
            self.assertIn("missing required launch authorization parameters", str(ctx.exception))

    @override_settings(
        SALESTRACKER_SHOWCASE_M2M_SECRET=TEST_SECRET,
        SALESTRACKER_SHOWCASE_API_BASE_URL=TEST_API_URL,
        SALESTRACKER_SHOWCASE_FRONTEND_URL=TEST_FRONTEND_URL,
        SALESTRACKER_SHOWCASE_SUPERADMIN_EMPLOYEE_ID="9930663966",
    )
    @patch("urllib.request.build_opener")
    def test_request_salestracker_launch_grant_payload_and_headers(self, mock_build_opener):
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = json.dumps({
            "callback_url": VALID_CALLBACK,
            "expires_in": 60,
        }).encode("utf-8")

        mock_opener = MagicMock()
        mock_opener.open.return_value.__enter__.return_value = mock_resp
        mock_build_opener.return_value = mock_opener

        res = request_salestracker_launch_grant(
            employee_id="9930663966",
            context="showcase",
            target_route="/dashboard",
        )

        self.assertEqual(res["callback_url"], VALID_CALLBACK)
        self.assertEqual(res["expires_in"], 60)
        self.assertEqual(res["employee_id"], "9930663966")

        # Verify request headers and payload
        called_req = mock_opener.open.call_args[0][0]
        self.assertEqual(called_req.get_header("X-vibeconnect-secret"), TEST_SECRET)
        self.assertEqual(called_req.get_header("Authorization"), f"Bearer {TEST_SECRET}")
        body = json.loads(called_req.data.decode("utf-8"))
        self.assertEqual(body["employee_id"], "9930663966")
        self.assertEqual(body["context"], "showcase")
        self.assertEqual(body["target_route"], "/dashboard")

    @override_settings(
        SALESTRACKER_SHOWCASE_M2M_SECRET=TEST_SECRET,
        SALESTRACKER_SHOWCASE_API_BASE_URL=TEST_API_URL,
    )
    @patch("urllib.request.build_opener")
    def test_request_salestracker_launch_grant_auth_error(self, mock_build_opener):
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

        with self.assertRaises(SalesTrackerSsoAuthError):
            request_salestracker_launch_grant(employee_id="9930663966")

    @override_settings(
        SALESTRACKER_SHOWCASE_M2M_SECRET=TEST_SECRET,
        SALESTRACKER_SHOWCASE_API_BASE_URL=TEST_API_URL,
    )
    @patch("urllib.request.build_opener")
    def test_request_salestracker_launch_grant_not_found(self, mock_build_opener):
        mock_opener = MagicMock()
        http_error = urllib.error.HTTPError(
            url=f"{TEST_API_URL}/api/v1/sso/launch-grant/",
            code=404,
            msg="Not Found",
            hdrs={},
            fp=MagicMock(read=lambda: b'{"detail": "Employee 9930663966 not found"}'),
        )
        mock_opener.open.side_effect = http_error
        mock_build_opener.return_value = mock_opener

        with self.assertRaises(SalesTrackerSsoNotFoundError) as ctx:
            request_salestracker_launch_grant(employee_id="9930663966")
        self.assertIn("Employee 9930663966 not found", ctx.exception.detail)


class SalesTrackerShowcaseServiceTests(TestCase):
    """Showcase integration tests for Sales Tracker CRM."""

    def setUp(self):
        self.admin = PlatformUser.objects.create_user(
            email="platformowner@vibeconnect.internal",
            password="test-password-123",
            full_name="Platform Owner",
            is_platform_owner=True,
            is_staff=True,
        )
        self.product, _ = Product.objects.get_or_create(
            code="crm",
            defaults={
                "name": "Customer Relationship Management",
                "status": ProductStatus.ACTIVE,
                "created_by": self.admin,
                "updated_by": self.admin,
            },
        )
        self.profile, _ = ProductShowcaseProfile.objects.get_or_create(
            product=self.product,
            defaults={
                "tagline": "Sales Tracker CRM",
                "visibility": ShowcaseVisibility.PUBLISHED,
                "created_by": self.admin,
                "updated_by": self.admin,
            },
        )
        self.demo_env, _ = ProductDemoEnvironment.objects.get_or_create(
            product=self.product,
            name="Sales Tracker CRM Live",
            defaults={
                "base_url": "http://localhost:5173",
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
                "allowed_targets": ["/dashboard"],
                "created_by": self.admin,
                "updated_by": self.admin,
            },
        )

    def test_showcase_launchability_contract(self):
        contract = ProductShowcaseService.launchability_contract(profile_id=str(self.profile.id))
        self.assertTrue(contract["launchable"])
        self.assertEqual(contract["reason"], "READY")
        self.assertEqual(contract["environment_name"], "Sales Tracker CRM Live")

    @override_settings(
        SALESTRACKER_SHOWCASE_M2M_SECRET=TEST_SECRET,
        SALESTRACKER_SHOWCASE_API_BASE_URL=TEST_API_URL,
        SALESTRACKER_SHOWCASE_FRONTEND_URL=TEST_FRONTEND_URL,
        SALESTRACKER_SHOWCASE_SUPERADMIN_EMPLOYEE_ID="9930663966",
    )
    @patch("apps.integration_hub.salestracker_sso_client.request_salestracker_launch_grant")
    def test_showcase_sso_launch_success(self, mock_grant):
        mock_grant.return_value = {
            "callback_url": VALID_CALLBACK,
            "expires_in": 60,
            "context": "showcase",
            "employee_id": "9930663966",
            "raw_response": {},
        }

        res = ProductShowcaseService.launch_demo(
            profile_id=str(self.profile.id),
            actor=self.admin,
        )

        self.assertEqual(res["redirect_url"], VALID_CALLBACK)
        self.assertEqual(res["demo_user"], "employee:9930663966")

        mock_grant.assert_called_once_with(
            employee_id="9930663966",
            context="showcase",
            target_route="/dashboard",
        )

        event = AuditLog.objects.filter(target_id=str(self.profile.id)).latest("timestamp")
        self.assertEqual(event.actor, self.admin)
        self.assertEqual(event.metadata.get("context"), "showcase")
        self.assertEqual(event.metadata.get("designated_employee_id"), "9930663966")
        self.assertFalse(event.metadata.get("direct_launch"))

    @override_settings(
        SALESTRACKER_SHOWCASE_M2M_SECRET=TEST_SECRET,
        SALESTRACKER_SHOWCASE_API_BASE_URL=TEST_API_URL,
    )
    @patch("apps.integration_hub.salestracker_sso_client.request_salestracker_launch_grant")
    def test_showcase_sso_launch_auth_failure_sanitized(self, mock_grant):
        mock_grant.side_effect = SalesTrackerSsoAuthError("401 Unauthorized")

        with self.assertRaises(ShowcaseServiceError) as ctx:
            ProductShowcaseService.launch_demo(
                profile_id=str(self.profile.id),
                actor=self.admin,
            )
        self.assertIn("authentication failed. Please verify server M2M secret", str(ctx.exception))

    @override_settings(
        SALESTRACKER_SHOWCASE_M2M_SECRET=TEST_SECRET,
        SALESTRACKER_SHOWCASE_API_BASE_URL=TEST_API_URL,
    )
    @patch("apps.integration_hub.salestracker_sso_client.request_salestracker_launch_grant")
    def test_showcase_sso_launch_not_found_sanitized(self, mock_grant):
        mock_grant.side_effect = SalesTrackerSsoNotFoundError("Employee 9930663966 not found", detail="Employee 9930663966 not found")

        with self.assertRaises(ShowcaseServiceError) as ctx:
            ProductShowcaseService.launch_demo(
                profile_id=str(self.profile.id),
                actor=self.admin,
            )
        self.assertIn("Sales Tracker showcase account not found: Employee 9930663966 not found", str(ctx.exception))
