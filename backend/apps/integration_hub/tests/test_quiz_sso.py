"""Focused tests for Quiz SSO integration in Product Launch and Showcase."""

import io
import json
from unittest.mock import MagicMock, patch
import urllib.error

from django.test import TestCase, override_settings
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.assignments.constants import AccessState
from apps.assignments.models import AssignmentStatus, UserProductAssignment
from apps.auditlog.models import AuditLog
from apps.identity.models import PlatformUser
from apps.integration_hub.quiz_sso_client import (
    ALLOWED_QUIZ_FRONTEND_HOST,
    QuizSsoAuthError,
    QuizSsoConflictError,
    QuizSsoConnectionError,
    QuizSsoError,
    is_quiz_sso_configured,
    normalize_and_validate_quiz_callback_url,
    request_quiz_launch_grant,
    validate_quiz_callback_url,
)
from apps.integration_hub.sso_views import SsoLaunchView, SsoPilotStatusView
from apps.organizations.models import Organization, OrganizationMembership
from apps.product_registry.models import Product, ProductStatus
from apps.showcase.models import (
    ProductDemoEnvironment,
    ProductLaunchConfig,
    ProductShowcaseProfile,
    ShowcaseVisibility,
)
from apps.showcase.services import ProductShowcaseService, ShowcaseServiceError

TEST_QUIZ_SECRET = "quiz-test-m2m-secret-xyz"
TEST_QUIZ_API_URL = "https://quizz.digielvestech.in"
VALID_QUIZ_CALLBACK = "https://quiz.digielvestech.in/sso/callback?code=quiz-grant-code-123"


class QuizSsoClientTests(TestCase):
    """Unit tests for quiz_sso_client functions."""

    def test_is_quiz_sso_configured_truthiness(self):
        with override_settings(QUIZ_M2M_SECRET=""):
            self.assertFalse(is_quiz_sso_configured())
        with override_settings(QUIZ_M2M_SECRET=TEST_QUIZ_SECRET):
            self.assertTrue(is_quiz_sso_configured())

    def test_validate_quiz_callback_url_valid(self):
        # Should not raise
        validate_quiz_callback_url(VALID_QUIZ_CALLBACK)

    def test_validate_quiz_callback_url_rejects_non_https(self):
        with self.assertRaises(QuizSsoError) as ctx:
            validate_quiz_callback_url("http://quiz.digielvestech.in/sso/callback?code=123")
        self.assertIn("HTTPS", str(ctx.exception))

    def test_validate_quiz_callback_url_rejects_wrong_host(self):
        with self.assertRaises(QuizSsoError) as ctx:
            validate_quiz_callback_url("https://malicious.com/sso/callback?code=123")
        self.assertIn("does not match expected host", str(ctx.exception))

    def test_validate_quiz_callback_url_rejects_wrong_callback_path(self):
        with self.assertRaises(QuizSsoError) as ctx:
            validate_quiz_callback_url("https://quiz.digielvestech.in/dashboard?code=123")
        self.assertIn("does not match expected SSO callback path", str(ctx.exception))

    def test_validate_quiz_callback_url_rejects_legacy_callback_path(self):
        with self.assertRaises(QuizSsoError) as ctx:
            validate_quiz_callback_url("https://quiz.digielvestech.in/auth/sso/vibeconnect/callback?code=123")
        self.assertIn("does not match expected SSO callback path", str(ctx.exception))

    def test_validate_quiz_callback_url_rejects_missing_query(self):
        with self.assertRaises(QuizSsoError) as ctx:
            validate_quiz_callback_url("https://quiz.digielvestech.in/sso/callback")
        self.assertIn("missing required launch authorization parameters", str(ctx.exception))

    def test_normalize_and_validate_quiz_callback_url_normalizes_api_host(self):
        raw_callback = "https://quizz.digielvestech.in/sso/callback?code=quiz-grant-code-456"
        normalized = normalize_and_validate_quiz_callback_url(raw_callback)
        self.assertEqual(normalized, "https://quiz.digielvestech.in/sso/callback?code=quiz-grant-code-456")

    def test_normalize_and_validate_quiz_callback_url_preserves_frontend_host(self):
        raw_callback = "https://quiz.digielvestech.in/sso/callback?code=quiz-grant-code-789"
        normalized = normalize_and_validate_quiz_callback_url(raw_callback)
        self.assertEqual(normalized, raw_callback)

    def test_normalize_and_validate_quiz_callback_url_rejects_untrusted_host(self):
        with self.assertRaises(QuizSsoError) as ctx:
            normalize_and_validate_quiz_callback_url("https://malicious.com/sso/callback?code=evil-123")
        self.assertIn("does not match expected host", str(ctx.exception))

    def test_normalize_and_validate_quiz_callback_url_rejects_missing_code(self):
        with self.assertRaises(QuizSsoError) as ctx:
            normalize_and_validate_quiz_callback_url("https://quizz.digielvestech.in/sso/callback?foo=bar")
        self.assertIn("missing required non-empty 'code' parameter", str(ctx.exception))

    def test_normalize_and_validate_quiz_callback_url_rejects_wrong_path(self):
        with self.assertRaises(QuizSsoError) as ctx:
            normalize_and_validate_quiz_callback_url("https://quizz.digielvestech.in/api/wrong?code=123")
        self.assertIn("does not match expected SSO callback path", str(ctx.exception))

    @override_settings(QUIZ_M2M_SECRET=TEST_QUIZ_SECRET, QUIZ_API_BASE_URL=TEST_QUIZ_API_URL)
    @patch("urllib.request.urlopen")
    def test_request_quiz_launch_grant_normalizes_api_host_callback(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = json.dumps({
            "callback_url": "https://quizz.digielvestech.in/sso/callback?code=grant-from-api-host-999"
        }).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        res = request_quiz_launch_grant(
            user_id="user-123",
            tenant_id="tenant-456",
            email="test@example.com",
            context="showcase",
            target_path="/admin",
        )
        self.assertEqual(res["callback_url"], "https://quiz.digielvestech.in/sso/callback?code=grant-from-api-host-999")

        called_req = mock_urlopen.call_args[0][0]
        payload = json.loads(called_req.data.decode("utf-8"))
        self.assertEqual(payload["target_path"], "/admin")
        self.assertEqual(payload["context"], "showcase")

    @override_settings(QUIZ_M2M_SECRET=TEST_QUIZ_SECRET, QUIZ_API_BASE_URL=TEST_QUIZ_API_URL)
    @patch("urllib.request.urlopen")
    def test_request_quiz_launch_grant_payload_and_headers(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = json.dumps({"callback_url": VALID_QUIZ_CALLBACK}).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        res = request_quiz_launch_grant(
            user_id="user-123",
            tenant_id="tenant-456",
            email="test@example.com",
            first_name="Jane",
            last_name="Doe",
            phone="+1234567890",
            context="standard",
            target_path="/dashboard",
        )

        self.assertEqual(res["callback_url"], VALID_QUIZ_CALLBACK)

        # Inspect request
        called_req = mock_urlopen.call_args[0][0]
        self.assertEqual(called_req.full_url, "https://quizz.digielvestech.in/api/auth/sso/vibeconnect/launch-grant/")
        self.assertEqual(called_req.get_header("X-vibeconnect-secret"), TEST_QUIZ_SECRET)
        self.assertEqual(called_req.get_header("Content-type"), "application/json")

        payload = json.loads(called_req.data.decode("utf-8"))
        self.assertEqual(payload["vibeconnect_user_id"], "user-123")
        self.assertEqual(payload["tenant_id"], "tenant-456")
        self.assertEqual(payload["email"], "test@example.com")
        self.assertEqual(payload["first_name"], "Jane")
        self.assertEqual(payload["last_name"], "Doe")
        self.assertEqual(payload["phone"], "+1234567890")
        self.assertEqual(payload["context"], "standard")
        self.assertEqual(payload["target_path"], "/dashboard")

    @override_settings(QUIZ_M2M_SECRET=TEST_QUIZ_SECRET, QUIZ_API_BASE_URL=TEST_QUIZ_API_URL)
    @patch("urllib.request.urlopen")
    def test_request_quiz_launch_grant_sanitizes_target_path(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = json.dumps({"callback_url": VALID_QUIZ_CALLBACK}).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        # Requesting /admin must be clamped to /dashboard (privilege escalation prevented)
        request_quiz_launch_grant(
            user_id="u1",
            tenant_id="t1",
            target_path="/admin",
        )
        called_req = mock_urlopen.call_args[0][0]
        payload = json.loads(called_req.data.decode("utf-8"))
        self.assertEqual(payload["target_path"], "/dashboard")

        # Requesting arbitrary/invalid path must be sanitized to /dashboard
        request_quiz_launch_grant(
            user_id="u1",
            tenant_id="t1",
            target_path="/unknown/path",
        )
        called_req = mock_urlopen.call_args[0][0]
        payload = json.loads(called_req.data.decode("utf-8"))
        self.assertEqual(payload["target_path"], "/dashboard")

        # Allowed path /quiz is accepted
        request_quiz_launch_grant(
            user_id="u1",
            tenant_id="t1",
            target_path="/quiz",
        )
        called_req = mock_urlopen.call_args[0][0]
        payload = json.loads(called_req.data.decode("utf-8"))
        self.assertEqual(payload["target_path"], "/quiz")

    @override_settings(QUIZ_M2M_SECRET=TEST_QUIZ_SECRET, QUIZ_API_BASE_URL=TEST_QUIZ_API_URL)
    @patch("urllib.request.urlopen")
    def test_request_quiz_launch_grant_handles_401(self, mock_urlopen):
        err = urllib.error.HTTPError(
            url=TEST_QUIZ_API_URL,
            code=401,
            msg="Unauthorized",
            hdrs={},
            fp=io.BytesIO(json.dumps({"detail": "Invalid secret"}).encode("utf-8")),
        )
        mock_urlopen.side_effect = err

        with self.assertRaises(QuizSsoAuthError):
            request_quiz_launch_grant(user_id="u1", tenant_id="t1", context="standard")

    @override_settings(QUIZ_M2M_SECRET=TEST_QUIZ_SECRET, QUIZ_API_BASE_URL=TEST_QUIZ_API_URL)
    @patch("urllib.request.urlopen")
    def test_request_quiz_launch_grant_handles_409_conflict(self, mock_urlopen):
        err = urllib.error.HTTPError(
            url=TEST_QUIZ_API_URL,
            code=409,
            msg="Conflict",
            hdrs={},
            fp=io.BytesIO(json.dumps({"detail": "Email already associated with another account"}).encode("utf-8")),
        )
        mock_urlopen.side_effect = err

        with self.assertRaises(QuizSsoConflictError) as ctx:
            request_quiz_launch_grant(user_id="u1", tenant_id="t1", context="standard")
        self.assertIn("Email already associated", str(ctx.exception))

    @override_settings(QUIZ_M2M_SECRET=TEST_QUIZ_SECRET, QUIZ_API_BASE_URL=TEST_QUIZ_API_URL)
    @patch("urllib.request.urlopen")
    def test_request_quiz_launch_grant_handles_connection_error(self, mock_urlopen):
        mock_urlopen.side_effect = urllib.error.URLError("Connection refused")

        with self.assertRaises(QuizSsoConnectionError):
            request_quiz_launch_grant(user_id="u1", tenant_id="t1", context="standard")


class QuizProductLaunchTests(TestCase):
    """Integration tests for Quiz launch via SsoLaunchView and SsoPilotStatusView."""

    def setUp(self):
        self.factory = APIRequestFactory()
        self.user = PlatformUser.objects.create_user(
            email="quiz.tester@demotenant.test",
            password="test-password-123",
            full_name="Quiz Tester",
        )
        from apps.organizations.models import MembershipStatus, MembershipType, OrganizationStatus

        self.org = Organization.objects.create(
            name="Demo Tenant",
            code="demo-quiz-org",
            status=OrganizationStatus.ACTIVE,
            created_by=self.user,
            updated_by=self.user,
        )
        from django.utils import timezone

        self.membership = OrganizationMembership.objects.create(
            user=self.user,
            organization=self.org,
            status=MembershipStatus.ACTIVE,
            membership_type=MembershipType.MEMBER,
            joined_at=timezone.now(),
        )
        self.product = Product.objects.create(
            name="Quiz",
            code="quiz",
            status=ProductStatus.ACTIVE,
            created_by=self.user,
            updated_by=self.user,
        )
        self.demo_env = ProductDemoEnvironment.objects.create(
            product=self.product,
            name="Quiz Live Platform",
            base_url="https://quiz.digielvestech.in/",
            is_active=True,
            created_by=self.user,
            updated_by=self.user,
        )

    def _grant_active_assignment(self):
        from apps.assignments.models import UserModuleAssignment
        from apps.entitlements.models import EntitlementStatus, OrganizationProductEntitlement
        from apps.product_registry.models import CatalogStatus, ProductModule

        module = ProductModule.objects.create(
            product=self.product,
            name="Quiz Core",
            code="quiz_core",
            status=CatalogStatus.ACTIVE,
            created_by=self.user,
            updated_by=self.user,
        )
        OrganizationProductEntitlement.objects.create(
            organization=self.org,
            product=self.product,
            status=EntitlementStatus.ACTIVE,
            created_by=self.user,
            updated_by=self.user,
        )
        assignment = UserProductAssignment.objects.create(
            user=self.user,
            organization=self.org,
            membership=self.membership,
            product=self.product,
            status=AssignmentStatus.ACTIVE,
            created_by=self.user,
            updated_by=self.user,
        )
        UserModuleAssignment.objects.create(
            assignment=assignment,
            module=module,
            is_enabled=True,
        )

    def test_quiz_launch_blocks_when_unentitled_or_unassigned(self):
        req = self.factory.post(
            "/api/v1/sso/launch/",
            {"product_id": str(self.product.id), "organization_id": str(self.org.id)},
            format="json",
        )
        force_authenticate(req, user=self.user)
        view = SsoLaunchView.as_view()
        response = view(req)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    @override_settings(QUIZ_M2M_SECRET="")
    def test_quiz_launch_direct_fallback_when_sso_not_configured(self):
        self._grant_active_assignment()

        req = self.factory.post(
            "/api/v1/sso/launch/",
            {"product_id": str(self.product.id), "organization_id": str(self.org.id)},
            format="json",
        )
        force_authenticate(req, user=self.user)
        view = SsoLaunchView.as_view()
        response = view(req)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["direct_launch"])
        self.assertEqual(response.data["redirect_url"], "https://quiz.digielvestech.in/")

    @override_settings(QUIZ_M2M_SECRET=TEST_QUIZ_SECRET, QUIZ_API_BASE_URL=TEST_QUIZ_API_URL)
    @patch("apps.integration_hub.quiz_sso_client.request_quiz_launch_grant")
    def test_quiz_launch_sso_grant_when_configured(self, mock_grant):
        self._grant_active_assignment()
        mock_grant.return_value = {"callback_url": VALID_QUIZ_CALLBACK, "raw_response": {}}

        req = self.factory.post(
            "/api/v1/sso/launch/",
            {"product_id": str(self.product.id), "organization_id": str(self.org.id)},
            format="json",
        )
        force_authenticate(req, user=self.user)
        view = SsoLaunchView.as_view()
        response = view(req)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data["direct_launch"])
        self.assertEqual(response.data["redirect_url"], VALID_QUIZ_CALLBACK)

        mock_grant.assert_called_once_with(
            user_id=str(self.user.id),
            tenant_id=str(self.org.id),
            email=self.user.email,
            first_name="Quiz",
            last_name="Tester",
            phone="",
            context="standard",
            target_path="/dashboard",
        )

    @override_settings(QUIZ_M2M_SECRET=TEST_QUIZ_SECRET, QUIZ_API_BASE_URL=TEST_QUIZ_API_URL)
    @patch("apps.integration_hub.quiz_sso_client.request_quiz_launch_grant")
    def test_quiz_launch_sso_returns_409_on_conflict(self, mock_grant):
        self._grant_active_assignment()
        mock_grant.side_effect = QuizSsoConflictError("Quiz account conflict.")

        req = self.factory.post(
            "/api/v1/sso/launch/",
            {"product_id": str(self.product.id), "organization_id": str(self.org.id)},
            format="json",
        )
        force_authenticate(req, user=self.user)
        view = SsoLaunchView.as_view()
        response = view(req)

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(response.data["error"], "QUIZ_ACCOUNT_CONFLICT")

    @override_settings(QUIZ_M2M_SECRET=TEST_QUIZ_SECRET, QUIZ_API_BASE_URL=TEST_QUIZ_API_URL)
    @patch("apps.integration_hub.quiz_sso_client.request_quiz_launch_grant")
    def test_quiz_launch_sso_fails_safely_without_silent_fallback(self, mock_grant):
        self._grant_active_assignment()
        mock_grant.side_effect = QuizSsoError("Quiz launch grant failed.")

        req = self.factory.post(
            "/api/v1/sso/launch/",
            {"product_id": str(self.product.id), "organization_id": str(self.org.id)},
            format="json",
        )
        force_authenticate(req, user=self.user)
        view = SsoLaunchView.as_view()
        response = view(req)

        # Must NOT return 200 with direct_launch login URL!
        self.assertEqual(response.status_code, status.HTTP_502_BAD_GATEWAY)
        self.assertEqual(response.data["error"], "QUIZ_SSO_FAILED")

    @override_settings(QUIZ_M2M_SECRET="")
    def test_quiz_pilot_status_direct_launch_when_unconfigured(self):
        req = self.factory.get(
            f"/api/v1/sso/pilot-status/?product_id={self.product.id}&organization_id={self.org.id}"
        )
        force_authenticate(req, user=self.user)
        view = SsoPilotStatusView.as_view()
        response = view(req)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["sso_enabled"])
        self.assertEqual(response.data["client_identifier"], "quiz_direct_launch")

    @override_settings(QUIZ_M2M_SECRET=TEST_QUIZ_SECRET)
    def test_quiz_pilot_status_quiz_sso_when_configured(self):
        req = self.factory.get(
            f"/api/v1/sso/pilot-status/?product_id={self.product.id}&organization_id={self.org.id}"
        )
        force_authenticate(req, user=self.user)
        view = SsoPilotStatusView.as_view()
        response = view(req)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data["sso_enabled"])
        self.assertEqual(response.data["client_identifier"], "quiz_sso")


class QuizShowcaseLaunchTests(TestCase):
    """Tests for Quiz showcase launch via ProductShowcaseService."""

    def setUp(self):
        self.admin = PlatformUser.objects.create_user(
            email="platform.admin@vibeconnect.internal",
            password="test-password-123",
            full_name="Platform Owner",
            is_platform_owner=True,
            is_staff=True,
        )
        self.product = Product.objects.create(
            name="Quiz",
            code="quiz",
            status=ProductStatus.ACTIVE,
            created_by=self.admin,
            updated_by=self.admin,
        )
        self.profile = ProductShowcaseProfile.objects.create(
            product=self.product,
            tagline="Quiz Showcase",
            overview="Interactive Quiz",
            visibility=ShowcaseVisibility.PUBLISHED,
            created_by=self.admin,
            updated_by=self.admin,
        )
        self.demo_env = ProductDemoEnvironment.objects.create(
            product=self.product,
            name="Quiz Live Platform",
            base_url="https://quiz.digielvestech.in/",
            is_active=True,
            created_by=self.admin,
            updated_by=self.admin,
        )
        self.launch_config = ProductLaunchConfig.objects.create(
            product=self.product,
            profile=self.profile,
            launch_mode=ProductLaunchConfig.LaunchMode.DEMO_ONLY,
            target_environment=self.demo_env,
            created_by=self.admin,
            updated_by=self.admin,
        )

    @override_settings(QUIZ_M2M_SECRET="")
    def test_showcase_direct_launch_when_unconfigured(self):
        res = ProductShowcaseService.launch_demo(
            profile_id=str(self.profile.id),
            actor=self.admin,
        )
        self.assertEqual(res["redirect_url"], "https://quiz.digielvestech.in/")
        self.assertEqual(res["demo_user"], "")

    @override_settings(QUIZ_M2M_SECRET=TEST_QUIZ_SECRET, QUIZ_API_BASE_URL=TEST_QUIZ_API_URL)
    @patch("apps.integration_hub.quiz_sso_client.request_quiz_launch_grant")
    def test_showcase_sso_launch_uses_showcase_context_and_designated_identity(self, mock_grant):
        mock_grant.return_value = {"callback_url": VALID_QUIZ_CALLBACK, "raw_response": {}}

        res = ProductShowcaseService.launch_demo(
            profile_id=str(self.profile.id),
            actor=self.admin,
        )

        self.assertEqual(res["redirect_url"], VALID_QUIZ_CALLBACK)
        self.assertEqual(res["demo_user"], "showcase_student")

        # Verify mock_grant called with showcase context and NOT the platform owner actor identity
        mock_grant.assert_called_once_with(
            user_id="showcase_student",
            tenant_id="showcase",
            email="showcase@vibeconnect.internal",
            first_name="Showcase",
            last_name="Student",
            phone="",
            context="showcase",
            target_path="/dashboard",
        )

        # Verify audit event records platform admin as actor, but context as showcase
        event = AuditLog.objects.filter(target_id=str(self.profile.id)).latest("timestamp")
        self.assertEqual(event.actor, self.admin)
        self.assertEqual(event.metadata.get("context"), "showcase")
        self.assertFalse(event.metadata.get("direct_launch"))

    @override_settings(QUIZ_M2M_SECRET=TEST_QUIZ_SECRET, QUIZ_API_BASE_URL=TEST_QUIZ_API_URL)
    @patch("apps.integration_hub.quiz_sso_client.request_quiz_launch_grant")
    def test_showcase_sso_launch_fails_safely_on_error(self, mock_grant):
        mock_grant.side_effect = QuizSsoError("Quiz service unavailable")

        with self.assertRaises(ShowcaseServiceError) as ctx:
            ProductShowcaseService.launch_demo(
                profile_id=str(self.profile.id),
                actor=self.admin,
            )
        self.assertIn("Quiz showcase SSO launch failed", str(ctx.exception))
