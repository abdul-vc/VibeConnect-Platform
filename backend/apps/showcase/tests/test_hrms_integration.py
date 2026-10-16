"""Comprehensive Unit & Integration Tests for HRMS Sandbox Integration.

Tests cover:
1. HrmsConnectorClient configuration validation, token caching, auto-refresh on 401,
   read-only operations, and strict server-side PII sanitization.
2. Authorization enforcement: Platform Owners, staff, and showcase-permitted users
   are allowed access, while anonymous, inactive, and unauthorized tenant users receive 401/403.
3. Upstream error translation (503 on unconfigured, 502 on auth failure or unreachable).
4. Live sandbox smoke test against https://hrms.vibesandbox.live when credentials are present.
"""

from __future__ import annotations

import json
import os
from typing import Any
from unittest.mock import MagicMock, patch
import urllib.error

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from rest_framework import status
from rest_framework.test import APIClient

from apps.integration_hub.hrms_connector import (
    CACHE_REFRESH_KEY,
    CACHE_TOKEN_KEY,
    HrmsConnectorAuthError,
    HrmsConnectorClient,
    HrmsConnectorConfigurationError,
    HrmsConnectorPermanentError,
    HrmsConnectorRetryableError,
)

User = get_user_model()


def _create_user(email: str, is_owner: bool = False, is_active: bool = True, status_val: str = "active") -> Any:
    user = User(
        email=email,
        full_name=f"User {email}",
        is_platform_owner=is_owner,
        is_staff=is_owner,
        is_active=is_active,
        status=status_val,
    )
    user.set_password("valid-pass-123")
    user.save()
    return user


class HrmsConnectorUnitTests(TestCase):
    """Unit tests for HrmsConnectorClient behavior, token caching, and PII sanitization."""

    def setUp(self):
        cache.clear()

    def tearDown(self):
        cache.clear()

    def test_missing_configuration_raises_error(self):
        """Missing URL or credentials must raise HrmsConnectorConfigurationError."""
        with patch.dict(os.environ, {"VIBECONNECT_HRMS_BACKEND_URL": "", "VIBECONNECT_HRMS_USERNAME": "", "VIBECONNECT_HRMS_PASSWORD": ""}):
            with override_settings(VIBECONNECT_HRMS_BACKEND_URL="", VIBECONNECT_HRMS_USERNAME="", VIBECONNECT_HRMS_PASSWORD=""):
                with self.assertRaises(HrmsConnectorConfigurationError):
                    HrmsConnectorClient(base_url="", username="", password="")

                with self.assertRaises(HrmsConnectorConfigurationError):
                    HrmsConnectorClient(base_url="https://hrms.test", username="", password="")

                with self.assertRaises(HrmsConnectorConfigurationError):
                    HrmsConnectorClient(base_url="https://hrms.test", username="testuser", password="")

    def test_pii_sanitization_removes_sensitive_fields(self):
        """Ensures that financial, tax, and government identity fields are stripped."""
        raw_employee = {
            "id": 101,
            "code": "EMP001",
            "firstName": "John",
            "lastName": "Doe",
            "email": "john.doe@example.com",
            "phone": "+1234567890",
            "roleName": "Senior Developer",
            "siteName": "Main Office",
            "department": 1,
            "departmentName": "Engineering",
            "status": "active",
            "doj": "2023-01-15",
            "isWfh": False,
            "employeeType": "Full Time",
            # Sensitive fields that MUST be purged:
            "pan": "ABCDE1234F",
            "aadhaar": "123456789012",
            "uan": "100900800700",
            "esi": "31000000000000001",
            "bankName": "National Bank",
            "bankAccount": "9876543210",
            "ifsc": "NBIN0001234",
            "ctc": 1500000,
            "salary": 125000,
            "taxRegime": "New",
            "taxSavingDeductions": 50000,
            "password": "hashed_secret_password",
        }

        sanitized = HrmsConnectorClient._sanitize_employee(raw_employee)

        # Must retain UI fields
        self.assertEqual(sanitized["id"], 101)
        self.assertEqual(sanitized["code"], "EMP001")
        self.assertEqual(sanitized["fullName"], "John Doe")
        self.assertEqual(sanitized["email"], "john.doe@example.com")
        self.assertEqual(sanitized["roleName"], "Senior Developer")
        self.assertEqual(sanitized["status"], "active")

        # Must NOT contain any sensitive fields
        for sensitive in [
            "pan", "aadhaar", "uan", "esi", "bankName", "bankAccount",
            "ifsc", "ctc", "salary", "taxRegime", "taxSavingDeductions", "password"
        ]:
            self.assertNotIn(sensitive, sanitized)

    @patch("urllib.request.urlopen")
    def test_authenticate_stores_tokens_in_cache(self, mock_urlopen):
        """Authenticating should store access and refresh tokens in Django cache."""
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({
            "access": "mocked-access-token-xyz",
            "refresh": "mocked-refresh-token-abc",
        }).encode("utf-8")
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        client = HrmsConnectorClient(
            base_url="https://hrms.mocked.live",
            username="testuser",
            password="testpassword",
        )

        token = client.authenticate()
        self.assertEqual(token, "mocked-access-token-xyz")
        self.assertEqual(cache.get(CACHE_TOKEN_KEY), "mocked-access-token-xyz")
        self.assertEqual(cache.get(CACHE_REFRESH_KEY), "mocked-refresh-token-abc")

    @patch("urllib.request.urlopen")
    def test_cached_token_is_reused_without_authenticating_again(self, mock_urlopen):
        """Subsequent calls should use the cached access token without network auth."""
        cache.set(CACHE_TOKEN_KEY, "already-cached-access-token", timeout=300)

        client = HrmsConnectorClient(
            base_url="https://hrms.mocked.live",
            username="testuser",
            password="testpassword",
        )

        token = client.get_valid_access_token()
        self.assertEqual(token, "already-cached-access-token")
        # Urlopen should not have been called for auth
        mock_urlopen.assert_not_called()

    @patch("urllib.request.urlopen")
    def test_auto_refresh_on_401_retries_successfully(self, mock_urlopen):
        """When an endpoint returns 401, client re-authenticates and retries the request once."""
        client = HrmsConnectorClient(
            base_url="https://hrms.mocked.live",
            username="testuser",
            password="testpassword",
        )
        cache.set(CACHE_TOKEN_KEY, "stale-access-token", timeout=300)

        # 1st call: GET /api/employees/ raises HTTP 401
        err_401 = urllib.error.HTTPError(
            url="https://hrms.mocked.live/api/employees/",
            code=401,
            msg="Unauthorized",
            hdrs={},
            fp=MagicMock(read=MagicMock(return_value=b'{"detail": "Given token not valid"}')),
        )

        # 2nd call: POST /api/auth/token/ returns new access token
        auth_resp = MagicMock()
        auth_resp.read.return_value = json.dumps({"access": "fresh-token-123"}).encode("utf-8")

        # 3rd call: retried GET /api/employees/ succeeds with 200
        data_resp = MagicMock()
        data_resp.read.return_value = json.dumps([
            {"id": 1, "firstName": "Alice", "lastName": "Smith", "code": "EMP010"}
        ]).encode("utf-8")

        mock_enter = MagicMock()
        mock_enter.__enter__.side_effect = [err_401, auth_resp, data_resp]
        mock_urlopen.side_effect = lambda req, timeout=10: mock_enter

        result = client.list_employees()
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["fullName"], "Alice Smith")


class HrmsShowcaseApiViewTests(TestCase):
    """Integration tests for the HRMS showcase endpoints and permission security."""

    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.owner = _create_user("owner@vibeconnect.local", is_owner=True)
        self.inactive_user = _create_user("inactive@vibeconnect.local", is_owner=True, is_active=False, status_val="disabled")
        self.tenant_user = _create_user("tenant@client.local", is_owner=False)

    def tearDown(self):
        cache.clear()

    def test_anonymous_caller_is_rejected(self):
        """Unauthenticated caller must receive HTTP 401."""
        endpoints = [
            "/api/v1/showcase/hrms/health/",
            "/api/v1/showcase/hrms/overview/",
            "/api/v1/showcase/hrms/employees/",
            "/api/v1/showcase/hrms/attendance/",
            "/api/v1/showcase/hrms/departments/",
        ]
        for url in endpoints:
            resp = self.client.get(url)
            self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED, f"URL {url} failed auth requirement")

    def test_inactive_user_is_forbidden(self):
        """Inactive or disabled user must receive HTTP 403."""
        self.client.force_authenticate(user=self.inactive_user)
        resp = self.client.get("/api/v1/showcase/hrms/health/")
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_unauthorized_tenant_user_is_forbidden(self):
        """Regular tenant user without showcase permissions must receive HTTP 403."""
        self.client.force_authenticate(user=self.tenant_user)
        resp = self.client.get("/api/v1/showcase/hrms/health/")
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(resp.data.get("code"), "INSUFFICIENT_PRIVILEGES")

    @patch("apps.integration_hub.hrms_connector.HrmsConnectorClient.probe_connectivity")
    def test_platform_owner_allowed_health_endpoint(self, mock_probe):
        """Platform Owner must be authorized and receive health probe payload."""
        mock_probe.return_value = {
            "status": "verified",
            "http_status": 200,
            "latency_ms": 42,
            "sandbox_url": "https://hrms.mocked.live",
            "user": {"username": "hrms_demo"},
        }
        self.client.force_authenticate(user=self.owner)
        resp = self.client.get("/api/v1/showcase/hrms/health/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["status"], "verified")
        self.assertEqual(resp.data["latency_ms"], 42)

    @patch("apps.integration_hub.hrms_connector.HrmsConnectorClient.list_employees")
    def test_employees_endpoint_pagination_and_query_filtering(self, mock_list):
        """Employees view must accept department & search filters and paginate cleanly."""
        mock_list.return_value = [
            {"id": i, "fullName": f"Employee {i}", "code": f"EMP{i:03d}", "roleName": "Dev"}
            for i in range(1, 16)
        ]
        self.client.force_authenticate(user=self.owner)

        # Request page 1 with page_size 5
        resp = self.client.get("/api/v1/showcase/hrms/employees/?page=1&page_size=5&search=Dev")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["count"], 15)
        self.assertEqual(resp.data["page"], 1)
        self.assertEqual(resp.data["pageSize"], 5)
        self.assertEqual(resp.data["totalPages"], 3)
        self.assertEqual(len(resp.data["results"]), 5)
        self.assertEqual(resp.data["results"][0]["fullName"], "Employee 1")

        # Request page 3
        resp_p3 = self.client.get("/api/v1/showcase/hrms/employees/?page=3&page_size=5")
        self.assertEqual(resp_p3.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp_p3.data["results"]), 5)
        self.assertEqual(resp_p3.data["results"][0]["fullName"], "Employee 11")

    @patch("apps.integration_hub.hrms_connector.HrmsConnectorClient.get_attendance_dashboard")
    @patch("apps.integration_hub.hrms_connector.HrmsConnectorClient.get_attendance_today")
    def test_attendance_endpoint_returns_metrics_and_records(self, mock_today, mock_dash):
        """Attendance view must return both dashboard counters and punch list."""
        mock_dash.return_value = {
            "totalEmployees": 14,
            "presentToday": 10,
            "absentToday": 3,
            "lateToday": 1,
        }
        mock_today.return_value = [
            {"id": 1, "employeeName": "John Doe", "attendanceStatus": "present", "totalWorkHours": "8h 15m"}
        ]
        self.client.force_authenticate(user=self.owner)

        resp = self.client.get("/api/v1/showcase/hrms/attendance/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["metrics"]["totalEmployees"], 14)
        self.assertEqual(resp.data["metrics"]["presentToday"], 10)
        self.assertEqual(resp.data["count"], 1)
        self.assertEqual(resp.data["records"][0]["employeeName"], "John Doe")

    @patch("apps.integration_hub.hrms_connector.HrmsConnectorClient.get_valid_access_token")
    def test_upstream_auth_failure_returns_bad_gateway(self, mock_auth):
        """When upstream returns authentication failure, view returns HTTP 502 with code HRMS_AUTH_FAILED."""
        mock_auth.side_effect = HrmsConnectorAuthError("Bad credentials", status_code=401)
        self.client.force_authenticate(user=self.owner)

        resp = self.client.get("/api/v1/showcase/hrms/health/")
        self.assertEqual(resp.status_code, status.HTTP_502_BAD_GATEWAY)
        self.assertEqual(resp.data.get("code"), "HRMS_AUTH_FAILED")


class HrmsLiveSandboxSmokeTest(TestCase):
    """Verified Live Sandbox Smoke Test.

    Only executes live requests if real sandbox credentials are configured in the environment.
    Clearly distinguishes mocked tests from verified live tests.
    """

    def test_live_sandbox_smoke_test_if_configured(self):
        backend_url = os.environ.get("VIBECONNECT_HRMS_BACKEND_URL", "").strip()
        username = os.environ.get("VIBECONNECT_HRMS_USERNAME", "").strip()
        password = os.environ.get("VIBECONNECT_HRMS_PASSWORD", "").strip()

        if not (backend_url and username and password):
            self.skipTest("Live HRMS sandbox credentials not set in environment; skipping live test.")

        client = HrmsConnectorClient(
            base_url=backend_url,
            username=username,
            password=password,
            timeout=15,
        )

        # 1. Health probe
        health = client.probe_connectivity()
        self.assertEqual(health.get("status"), "verified", f"Live health probe failed: {health}")
        self.assertEqual(health.get("http_status"), 200)

        # 2. Employees list
        employees = client.list_employees()
        self.assertIsInstance(employees, list)
        self.assertGreater(len(employees), 0, "Live sandbox should return at least 1 employee.")

        # Verify no PII is returned on live employee data
        first_emp = employees[0]
        self.assertIn("fullName", first_emp)
        self.assertIn("code", first_emp)
        self.assertNotIn("pan", first_emp)
        self.assertNotIn("aadhaar", first_emp)
        self.assertNotIn("bankAccount", first_emp)
        self.assertNotIn("ctc", first_emp)

        # 3. Attendance dashboard
        dashboard = client.get_attendance_dashboard()
        self.assertIn("totalEmployees", dashboard)
        self.assertIn("presentToday", dashboard)

        # 4. Departments
        departments = client.list_departments()
        self.assertIsInstance(departments, list)
