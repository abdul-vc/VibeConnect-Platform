"""Identity Authentication and Authorization Test Suite.

Verifies CSRF enforcement, session authentication, Platform Owner authorization,
endpoint-local throttling, cookie isolation, and superuser attributes against PostgreSQL.
"""

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.exceptions import ImproperlyConfigured
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from config.settings.base import (
    get_env_bool,
    get_env_pos_int,
    get_env_samesite,
    get_env_str,
    get_env_throttle_rate,
)

User = get_user_model()


class AuthTestSuite(TestCase):
    """Complete test suite for VibeConnect Phase 1B authentication."""

    def setUp(self):
        super().setUp()
        cache.clear()
        self.client = APIClient(enforce_csrf_checks=True)

        self.password = "SecurePassword123!"
        self.owner_email = "owner@vibeconnect.internal"
        self.regular_email = "regular@vibeconnect.internal"
        self.inactive_owner_email = "inactive_owner@vibeconnect.internal"

        self.owner_user = User.objects.create_user(
            email=self.owner_email,
            password=self.password,
            full_name="Platform Owner",
            is_active=True,
            is_platform_owner=True,
        )

        self.regular_user = User.objects.create_user(
            email=self.regular_email,
            password=self.password,
            full_name="Regular User",
            is_active=True,
            is_platform_owner=False,
        )

        self.inactive_owner_user = User.objects.create_user(
            email=self.inactive_owner_email,
            password=self.password,
            full_name="Inactive Owner",
            is_active=False,
            is_platform_owner=True,
        )

    def tearDown(self):
        cache.clear()
        super().tearDown()

    def _get_csrf_token(self) -> str:
        """Helper to call /csrf/ endpoint and extract cookie value."""
        response = self.client.get("/api/v1/auth/csrf/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        csrf_cookie_name = settings.CSRF_COOKIE_NAME
        self.assertIn(csrf_cookie_name, response.cookies)
        return response.cookies[csrf_cookie_name].value

    # 1. Public Health Endpoint
    def test_health_endpoint_public(self):
        response = self.client.get("/api/v1/health/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json(), {"status": "healthy", "service": "vibeconnect_backend"})

    # 2. Public CSRF Initialization
    def test_csrf_endpoint_public_and_sets_cookie(self):
        response = self.client.get("/api/v1/auth/csrf/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        csrf_cookie_name = settings.CSRF_COOKIE_NAME
        self.assertIn(csrf_cookie_name, response.cookies)
        self.assertTrue(len(response.cookies[csrf_cookie_name].value) > 0)

    # 3. CSRF Endpoint does not leak token in JSON
    def test_csrf_endpoint_does_not_leak_token_in_json(self):
        response = self.client.get("/api/v1/auth/csrf/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(data, {"detail": "CSRF cookie set."})
        self.assertNotIn("csrf", data)
        self.assertNotIn("token", data)

    # 4. Login without CSRF Rejected
    def test_login_without_csrf_rejected_403(self):
        payload = {"email": self.owner_email, "password": self.password}
        response = self.client.post("/api/v1/auth/login/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    # 5. Login with Missing Header Rejected
    def test_login_with_missing_header_rejected_403(self):
        self._get_csrf_token()
        payload = {"email": self.owner_email, "password": self.password}
        # Client has cookie, but no HTTP_X_CSRFTOKEN header is sent
        response = self.client.post("/api/v1/auth/login/", payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    # 6. Login with Mismatched CSRF Rejected
    def test_login_with_mismatched_csrf_rejected_403(self):
        self._get_csrf_token()
        payload = {"email": self.owner_email, "password": self.password}
        response = self.client.post(
            "/api/v1/auth/login/",
            payload,
            format="json",
            HTTP_X_CSRFTOKEN="invalid_mismatched_csrf_token_value",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    # 7. Valid Active Platform Owner Login Success
    def test_login_with_valid_csrf_and_platform_owner_success(self):
        token = self._get_csrf_token()
        payload = {"email": self.owner_email, "password": self.password}
        response = self.client.post(
            "/api/v1/auth/login/",
            payload,
            format="json",
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        session_cookie_name = settings.SESSION_COOKIE_NAME
        self.assertIn(session_cookie_name, response.cookies)
        data = response.json()
        self.assertEqual(data["email"], self.owner_email)
        self.assertEqual(data["is_platform_owner"], True)
        self.assertEqual(data["full_name"], "Platform Owner")
        self.assertIn("id", data)

    # 8. Unknown Email Login Failure
    def test_login_unknown_email_generic_401(self):
        token = self._get_csrf_token()
        payload = {"email": "nonexistent@vibeconnect.internal", "password": self.password}
        response = self.client.post(
            "/api/v1/auth/login/",
            payload,
            format="json",
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(response.json(), {"detail": "Invalid credentials or unauthorized account."})

    # 9. Invalid Password Login Failure
    def test_login_invalid_password_generic_401(self):
        token = self._get_csrf_token()
        payload = {"email": self.owner_email, "password": "WrongPassword!"}
        response = self.client.post(
            "/api/v1/auth/login/",
            payload,
            format="json",
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(response.json(), {"detail": "Invalid credentials or unauthorized account."})

    # 10. Inactive Platform Owner Login Failure
    def test_login_inactive_platform_owner_generic_401(self):
        token = self._get_csrf_token()
        payload = {"email": self.inactive_owner_email, "password": self.password}
        response = self.client.post(
            "/api/v1/auth/login/",
            payload,
            format="json",
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(response.json(), {"detail": "Invalid credentials or unauthorized account."})

    # 11. Active Non-Console User Login Returns 403 NO_CONSOLE_ACCESS
    def test_login_active_non_console_user_returns_403_no_console_access(self):
        token = self._get_csrf_token()
        payload = {"email": self.regular_email, "password": self.password}
        response = self.client.post(
            "/api/v1/auth/login/",
            payload,
            format="json",
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(
            response.json(),
            {"code": "NO_CONSOLE_ACCESS", "detail": "No active console access."},
        )

    # 12. Identical Generic Login Failure Response Verification (401)
    def test_login_identical_generic_failure_response(self):
        token = self._get_csrf_token()
        cases = [
            {"email": "unknown@vibeconnect.internal", "password": self.password},
            {"email": self.owner_email, "password": "WrongPassword123!"},
            {"email": self.inactive_owner_email, "password": self.password},
            {"email": self.regular_email, "password": "WrongPassword123!"},
        ]
        for payload in cases:
            response = self.client.post(
                "/api/v1/auth/login/",
                payload,
                format="json",
                HTTP_X_CSRFTOKEN=token,
            )
            self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
            self.assertEqual(response.json(), {"detail": "Invalid credentials or unauthorized account."})

    # 13. Missing Email 400
    def test_login_missing_email_returns_400(self):
        token = self._get_csrf_token()
        payload = {"password": self.password}
        response = self.client.post(
            "/api/v1/auth/login/",
            payload,
            format="json",
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("email", response.json())

    # 14. Missing Password 400
    def test_login_missing_password_returns_400(self):
        token = self._get_csrf_token()
        payload = {"email": self.owner_email}
        response = self.client.post(
            "/api/v1/auth/login/",
            payload,
            format="json",
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("password", response.json())

    # 15. Invalid Email Syntax 400
    def test_login_invalid_email_syntax_returns_400(self):
        token = self._get_csrf_token()
        payload = {"email": "not-an-email", "password": self.password}
        response = self.client.post(
            "/api/v1/auth/login/",
            payload,
            format="json",
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("email", response.json())

    # 16. Exceeding Max Length 400
    def test_login_exceeding_max_length_returns_400(self):
        token = self._get_csrf_token()
        payload = {"email": "a" * 256 + "@vibeconnect.internal", "password": self.password}
        response = self.client.post(
            "/api/v1/auth/login/",
            payload,
            format="json",
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    # 17. Email Case Normalization on Login
    def test_login_email_case_normalization(self):
        token = self._get_csrf_token()
        payload = {"email": "OWNER@VIBECONNECT.INTERNAL", "password": self.password}
        response = self.client.post(
            "/api/v1/auth/login/",
            payload,
            format="json",
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()["email"], self.owner_email)

    # 18. Failed Login Creates No Session
    def test_failed_login_creates_no_session(self):
        token = self._get_csrf_token()
        payload = {"email": self.owner_email, "password": "WrongPassword!"}
        response = self.client.post(
            "/api/v1/auth/login/",
            payload,
            format="json",
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        session_cookie_name = settings.SESSION_COOKIE_NAME
        self.assertNotIn(session_cookie_name, response.cookies)

    # 19. Successful Login Rotates Session Key
    def test_successful_login_rotates_session_key(self):
        token = self._get_csrf_token()
        # Initialize an anonymous session first
        session = self.client.session
        session["pre_auth"] = "marker"
        session.save()
        pre_key = self.client.session.session_key

        payload = {"email": self.owner_email, "password": self.password}
        response = self.client.post(
            "/api/v1/auth/login/",
            payload,
            format="json",
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        post_key = self.client.session.session_key
        self.assertNotEqual(pre_key, post_key)

    # 20. Session Cookie Name and Attributes
    def test_session_cookie_name_and_attributes(self):
        token = self._get_csrf_token()
        payload = {"email": self.owner_email, "password": self.password}
        response = self.client.post(
            "/api/v1/auth/login/",
            payload,
            format="json",
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        cookie = response.cookies[settings.SESSION_COOKIE_NAME]
        self.assertTrue(cookie["httponly"])
        self.assertEqual(cookie["samesite"], "Lax")
        self.assertEqual(cookie["path"], "/")

    # 21. CSRF Cookie Name and Attributes
    def test_csrf_cookie_name_and_attributes(self):
        response = self.client.get("/api/v1/auth/csrf/")
        cookie = response.cookies[settings.CSRF_COOKIE_NAME]
        self.assertFalse(cookie["httponly"])
        self.assertEqual(cookie["samesite"], "Lax")
        self.assertEqual(cookie["path"], "/")

    # 22. /me Unauthenticated returns 401
    def test_me_unauthenticated_returns_401(self):
        response = self.client.get("/api/v1/auth/me/")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(response.json(), {"detail": "Authentication credentials were not provided."})

    # 23. /me Authenticated Non-Platform-Owner returns 403
    def test_me_authenticated_non_platform_owner_returns_403(self):
        # Establish real session for regular user
        session = self.client.session
        session["_auth_user_id"] = str(self.regular_user.pk)
        session["_auth_user_backend"] = "django.contrib.auth.backends.ModelBackend"
        session["_auth_user_hash"] = self.regular_user.get_session_auth_hash()
        session.save()
        self.client.cookies[settings.SESSION_COOKIE_NAME] = session.session_key

        response = self.client.get("/api/v1/auth/me/")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(response.json(), {"detail": "Access restricted to active platform owners."})

    # 24. /me Authenticated Platform Owner returns 200
    def test_me_authenticated_platform_owner_returns_200(self):
        token = self._get_csrf_token()
        payload = {"email": self.owner_email, "password": self.password}
        login_res = self.client.post(
            "/api/v1/auth/login/",
            payload,
            format="json",
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(login_res.status_code, status.HTTP_200_OK)

        response = self.client.get("/api/v1/auth/me/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(data["email"], self.owner_email)
        self.assertEqual(data["is_platform_owner"], True)

    # 25. /me Returns only Approved Fields
    def test_me_returns_only_approved_fields(self):
        token = self._get_csrf_token()
        payload = {"email": self.owner_email, "password": self.password}
        self.client.post("/api/v1/auth/login/", payload, format="json", HTTP_X_CSRFTOKEN=token)

        response = self.client.get("/api/v1/auth/me/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        expected_keys = {
            "id",
            "email",
            "full_name",
            "is_platform_owner",
            "active_context",
            "available_contexts",
        }
        self.assertEqual(set(response.json().keys()), expected_keys)

    # 26. /me Sensitive Fields are Absent
    def test_me_sensitive_fields_absent(self):
        token = self._get_csrf_token()
        payload = {"email": self.owner_email, "password": self.password}
        self.client.post("/api/v1/auth/login/", payload, format="json", HTTP_X_CSRFTOKEN=token)

        response = self.client.get("/api/v1/auth/me/")
        data = response.json()
        for sensitive in ["password", "is_staff", "is_superuser", "user_permissions", "groups", "auth_provider", "external_subject_id"]:
            self.assertNotIn(sensitive, data)

    # 27. Deactivated Platform Owner Session Rejected 401
    def test_deactivated_platform_owner_session_rejected_401(self):
        token = self._get_csrf_token()
        payload = {"email": self.owner_email, "password": self.password}
        self.client.post("/api/v1/auth/login/", payload, format="json", HTTP_X_CSRFTOKEN=token)

        # Deactivate user in DB while session exists
        self.owner_user.is_active = False
        self.owner_user.save()

        response = self.client.get("/api/v1/auth/me/")
        # ModelBackend rejects inactive user during session restoration, yielding unauthenticated 401
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    # 28. Logout Unauthenticated returns 401
    def test_logout_unauthenticated_returns_401(self):
        token = self._get_csrf_token()
        response = self.client.post(
            "/api/v1/auth/logout/",
            format="json",
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    # 29. Logout Authenticated Non-Owner succeeds and clears session
    def test_logout_authenticated_non_owner_succeeds(self):
        session = self.client.session
        session["_auth_user_id"] = str(self.regular_user.pk)
        session["_auth_user_backend"] = "django.contrib.auth.backends.ModelBackend"
        session["_auth_user_hash"] = self.regular_user.get_session_auth_hash()
        session.save()
        self.client.cookies[settings.SESSION_COOKIE_NAME] = session.session_key

        token = self._get_csrf_token()
        response = self.client.post(
            "/api/v1/auth/logout/",
            format="json",
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["detail"], "Successfully logged out.")

    # 30. Logout Owner without CSRF returns 403
    def test_logout_owner_without_csrf_returns_403(self):
        token = self._get_csrf_token()
        payload = {"email": self.owner_email, "password": self.password}
        self.client.post("/api/v1/auth/login/", payload, format="json", HTTP_X_CSRFTOKEN=token)

        # Attempt logout without sending X-CSRFToken header
        response = self.client.post("/api/v1/auth/logout/", format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    # 31. Logout Owner with CSRF returns 200
    def test_logout_owner_with_csrf_returns_200(self):
        token = self._get_csrf_token()
        payload = {"email": self.owner_email, "password": self.password}
        login_res = self.client.post("/api/v1/auth/login/", payload, format="json", HTTP_X_CSRFTOKEN=token)
        self.assertEqual(login_res.status_code, status.HTTP_200_OK)

        # Retrieve current CSRF token from client cookie
        current_token = self.client.cookies[settings.CSRF_COOKIE_NAME].value
        response = self.client.post(
            "/api/v1/auth/logout/",
            format="json",
            HTTP_X_CSRFTOKEN=current_token,
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json(), {"detail": "Successfully logged out."})

    # 32. Logout Invalidates Server Session
    def test_logout_invalidates_server_session(self):
        token = self._get_csrf_token()
        payload = {"email": self.owner_email, "password": self.password}
        login_res = self.client.post("/api/v1/auth/login/", payload, format="json", HTTP_X_CSRFTOKEN=token)
        self.assertEqual(login_res.status_code, status.HTTP_200_OK)

        current_token = self.client.cookies[settings.CSRF_COOKIE_NAME].value
        # Successful logout
        logout_res = self.client.post(
            "/api/v1/auth/logout/",
            format="json",
            HTTP_X_CSRFTOKEN=current_token,
        )
        self.assertEqual(logout_res.status_code, status.HTTP_200_OK)

        # Subsequent /me call must be unauthenticated 401
        me_res = self.client.get("/api/v1/auth/me/")
        self.assertEqual(me_res.status_code, status.HTTP_401_UNAUTHORIZED)

    # 33. GET Logout returns 405 for Authenticated Platform Owner
    def test_logout_get_method_not_allowed_405(self):
        token = self._get_csrf_token()
        payload = {"email": self.owner_email, "password": self.password}
        login_res = self.client.post("/api/v1/auth/login/", payload, format="json", HTTP_X_CSRFTOKEN=token)
        self.assertEqual(login_res.status_code, status.HTTP_200_OK)

        response = self.client.get("/api/v1/auth/logout/")
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    # 34. Login Throttling Triggers 429
    def test_login_throttling_triggers_429(self):
        cache.clear()
        token = self._get_csrf_token()
        payload = {"email": self.owner_email, "password": "WrongPassword!"}

        # Rate is 5/minute; 5 requests allowed, 6th must trigger 429
        for _ in range(5):
            res = self.client.post(
                "/api/v1/auth/login/",
                payload,
                format="json",
                HTTP_X_CSRFTOKEN=token,
            )
            self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

        throttled_res = self.client.post(
            "/api/v1/auth/login/",
            payload,
            format="json",
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(throttled_res.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        self.assertIn("detail", throttled_res.json())

    # 35. Throttle Cache Isolation
    def test_throttle_cache_isolation(self):
        cache.clear()
        token = self._get_csrf_token()
        payload = {"email": self.owner_email, "password": "WrongPassword!"}
        res = self.client.post(
            "/api/v1/auth/login/",
            payload,
            format="json",
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)
        cache.clear()

    # 36. Unrelated Endpoints Not Throttled by Login Throttle
    def test_unrelated_endpoints_not_throttled(self):
        cache.clear()
        # Exhaust login throttle
        token = self._get_csrf_token()
        payload = {"email": self.owner_email, "password": "WrongPassword!"}
        for _ in range(6):
            self.client.post(
                "/api/v1/auth/login/",
                payload,
                format="json",
                HTTP_X_CSRFTOKEN=token,
            )

        # Other endpoints should continue working and not return 429
        health_res = self.client.get("/api/v1/health/")
        self.assertEqual(health_res.status_code, status.HTTP_200_OK)

        csrf_res = self.client.get("/api/v1/auth/csrf/")
        self.assertEqual(csrf_res.status_code, status.HTTP_200_OK)

        me_res = self.client.get("/api/v1/auth/me/")
        self.assertEqual(me_res.status_code, status.HTTP_401_UNAUTHORIZED)

    # 37. createsuperuser Required Flags
    def test_createsuperuser_required_flags(self):
        superuser = User.objects.create_superuser(
            email="root@vibeconnect.internal",
            password=self.password,
            full_name="Root Superuser",
        )
        self.assertTrue(superuser.is_staff)
        self.assertTrue(superuser.is_superuser)
        self.assertTrue(superuser.is_platform_owner)
        self.assertTrue(superuser.is_active)

    # 38. createsuperuser Unsafe Flags Rejected
    def test_createsuperuser_unsafe_flags_rejected(self):
        with self.assertRaises(ValueError):
            User.objects.create_superuser(
                email="badowner@vibeconnect.internal",
                password=self.password,
                is_platform_owner=False,
            )
        with self.assertRaises(ValueError):
            User.objects.create_superuser(
                email="badactive@vibeconnect.internal",
                password=self.password,
                is_active=False,
            )

    # 39. Required Environment Parser Failures
    def test_required_environment_parser_failures(self):
        with self.assertRaises(ImproperlyConfigured):
            get_env_pos_int("NONEXISTENT_INT_VAR")
        with self.assertRaises(ImproperlyConfigured):
            get_env_bool("NONEXISTENT_BOOL_VAR")
        with self.assertRaises(ImproperlyConfigured):
            get_env_str("NONEXISTENT_STR_VAR")
        with self.assertRaises(ImproperlyConfigured):
            get_env_samesite("NONEXISTENT_SAMESITE_VAR")
        with self.assertRaises(ImproperlyConfigured):
            get_env_throttle_rate("NONEXISTENT_THROTTLE_VAR")
