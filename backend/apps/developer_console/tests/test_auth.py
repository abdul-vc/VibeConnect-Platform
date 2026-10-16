import datetime
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone
from rest_framework.response import Response
from rest_framework.test import APIRequestFactory
from rest_framework.views import APIView

from apps.developer_console.authentication import ApiKeyAuthentication
from apps.developer_console.mixins import DeveloperApiViewMixin
from apps.developer_console.models import DeveloperApiKey, DeveloperApplication
from apps.developer_console.permissions import HasApiScope
from apps.developer_console.services.key_service import generate_api_key, rotate_api_key
from apps.developer_console.throttling import DeveloperKeyRateThrottle
from apps.organizations.models import Organization, OrganizationStatus

User = get_user_model()


class DummyCatalogView(DeveloperApiViewMixin, APIView):
    authentication_classes = [ApiKeyAuthentication]
    permission_classes = [HasApiScope]
    throttle_classes = [DeveloperKeyRateThrottle]
    required_scope = "catalog:read"

    def get(self, request):
        return Response({"status": "ok", "tenant": str(request.tenant.id)})


class ApiKeyAuthTests(TestCase):
    def setUp(self):
        cache.clear()
        self.factory = APIRequestFactory()
        self.user = User.objects.create_user(
            email="owner@tenant.local",
            password="TestPassword123!",
            full_name="Tenant Owner",
        )
        self.org = Organization.objects.create(
            code="tenant_alpha",
            name="Tenant Alpha",
            status=OrganizationStatus.ACTIVE,
            created_by=self.user,
            updated_by=self.user,
        )
        self.app = DeveloperApplication.objects.create(
            organization=self.org,
            name="Alpha Integration",
            created_by=self.user,
            status="active",
        )
        self.api_key_obj, self.raw_key = generate_api_key(
            name="Test Key",
            application=self.app,
            scopes=["catalog:read", "organization:read"],
        )

    def tearDown(self):
        cache.clear()

    def test_valid_api_key_authenticates_and_binds_tenant(self):
        request = self.factory.get("/dummy/", HTTP_AUTHORIZATION=f"Bearer {self.raw_key}")
        view = DummyCatalogView.as_view()
        response = view(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], "ok")
        self.assertEqual(response.data["tenant"], str(self.org.id))
        self.assertIn("X-RateLimit-Limit", response.headers)
        self.assertIn("X-RateLimit-Remaining", response.headers)
        self.assertIn("X-RateLimit-Reset", response.headers)

        # Verify last_used_at was updated
        self.api_key_obj.refresh_from_db()
        self.assertIsNotNone(self.api_key_obj.last_used_at)

    def test_invalid_key_rejected(self):
        request = self.factory.get("/dummy/", HTTP_AUTHORIZATION="Bearer vck_live_deadbeef_invalidsecret1234567890123456789012345")
        view = DummyCatalogView.as_view()
        response = view(request)

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.data.get("error"), "INVALID_API_KEY")

    def test_expired_key_rejected(self):
        # Set expires_at in the past
        self.api_key_obj.expires_at = timezone.now() - datetime.timedelta(hours=1)
        self.api_key_obj.save()

        request = self.factory.get("/dummy/", HTTP_AUTHORIZATION=f"Bearer {self.raw_key}")
        view = DummyCatalogView.as_view()
        response = view(request)

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.data.get("error"), "KEY_EXPIRED")

    def test_revoked_key_rejected(self):
        self.api_key_obj.status = "revoked"
        self.api_key_obj.save()

        request = self.factory.get("/dummy/", HTTP_AUTHORIZATION=f"Bearer {self.raw_key}")
        view = DummyCatalogView.as_view()
        response = view(request)

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.data.get("error"), "KEY_REVOKED")

    def test_suspended_application_rejected(self):
        self.app.status = "suspended"
        self.app.save()

        request = self.factory.get("/dummy/", HTTP_AUTHORIZATION=f"Bearer {self.raw_key}")
        view = DummyCatalogView.as_view()
        response = view(request)

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.data.get("error"), "APPLICATION_SUSPENDED")

    def test_revoked_application_rejected(self):
        self.app.status = "revoked"
        self.app.save()

        request = self.factory.get("/dummy/", HTTP_AUTHORIZATION=f"Bearer {self.raw_key}")
        view = DummyCatalogView.as_view()
        response = view(request)

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.data.get("error"), "APPLICATION_REVOKED")

    def test_inactive_tenant_rejected(self):
        self.org.status = OrganizationStatus.RETIRED
        self.org.save()

        request = self.factory.get("/dummy/", HTTP_AUTHORIZATION=f"Bearer {self.raw_key}")
        view = DummyCatalogView.as_view()
        response = view(request)

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.data.get("error"), "TENANT_INACTIVE")

    def test_scope_allowed(self):
        # catalog:read is in scopes
        request = self.factory.get("/dummy/", HTTP_AUTHORIZATION=f"Bearer {self.raw_key}")
        view = DummyCatalogView.as_view()
        response = view(request)
        self.assertEqual(response.status_code, 200)

    def test_scope_denied(self):
        # Create key without catalog:read
        key_no_scope, raw_key_no_scope = generate_api_key(
            name="Limited Key",
            application=self.app,
            scopes=["organization:read"],
        )
        request = self.factory.get("/dummy/", HTTP_AUTHORIZATION=f"Bearer {raw_key_no_scope}")
        view = DummyCatalogView.as_view()
        response = view(request)

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.data.get("error"), "INSUFFICIENT_SCOPE")

    def test_tenant_mismatch_rejected(self):
        # Passing an explicit foreign tenant_id must be rejected
        other_org_id = "00000000-0000-0000-0000-000000000099"
        request = self.factory.get(f"/dummy/?tenant_id={other_org_id}", HTTP_AUTHORIZATION=f"Bearer {self.raw_key}")
        view = DummyCatalogView.as_view()
        response = view(request)

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.data.get("error"), "TENANT_MISMATCH")

    def test_atomic_key_rotation(self):
        new_key_obj, new_raw_key = rotate_api_key(self.api_key_obj)

        self.api_key_obj.refresh_from_db()
        self.assertEqual(self.api_key_obj.status, "revoked")
        self.assertIsNotNone(self.api_key_obj.revoked_at)

        # Old key fails
        req_old = self.factory.get("/dummy/", HTTP_AUTHORIZATION=f"Bearer {self.raw_key}")
        res_old = DummyCatalogView.as_view()(req_old)
        self.assertEqual(res_old.status_code, 401)
        self.assertEqual(res_old.data.get("error"), "KEY_REVOKED")

        # New key succeeds
        req_new = self.factory.get("/dummy/", HTTP_AUTHORIZATION=f"Bearer {new_raw_key}")
        res_new = DummyCatalogView.as_view()(req_new)
        self.assertEqual(res_new.status_code, 200)

    def test_rate_limit_per_key_429_and_headers(self):
        """Per-key rate limiting: over-threshold returns 429 with Retry-After and rate-limit headers."""
        import unittest.mock as mock

        with mock.patch.object(DeveloperKeyRateThrottle, "get_rate", return_value="3/minute"):
            view = DummyCatalogView.as_view()
            auth_header = f"Bearer {self.raw_key}"

            # Requests 1-3: should all succeed (within limit)
            for i in range(3):
                req = self.factory.get("/dummy/", HTTP_AUTHORIZATION=auth_header)
                resp = view(req)
                self.assertEqual(resp.status_code, 200, f"Request {i+1} should succeed (within limit)")
                self.assertIn("X-RateLimit-Limit", resp.headers)
                self.assertIn("X-RateLimit-Remaining", resp.headers)
                self.assertIn("X-RateLimit-Reset", resp.headers)
                self.assertEqual(resp.headers["X-RateLimit-Limit"], "3")

            # Request 4: must be throttled (429)
            req = self.factory.get("/dummy/", HTTP_AUTHORIZATION=auth_header)
            resp = view(req)
            self.assertEqual(resp.status_code, 429)
            self.assertEqual(resp.data.get("error"), "RATE_LIMIT_EXCEEDED")
            self.assertIn("retry_after", resp.data)
            self.assertIsInstance(resp.data["retry_after"], int)
            self.assertGreater(resp.data["retry_after"], 0)

            # Confirm a different key on the same org is NOT throttled (per-key isolation)
            second_key_obj, second_raw_key = generate_api_key(
                name="Second Key",
                application=self.app,
                scopes=["catalog:read"],
            )
            req_second = self.factory.get("/dummy/", HTTP_AUTHORIZATION=f"Bearer {second_raw_key}")
            resp_second = view(req_second)
            self.assertEqual(
                resp_second.status_code, 200,
                "Different key must not be throttled by first key's exhausted limit",
            )
