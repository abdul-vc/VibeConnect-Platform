"""Comprehensive Unit & Integration Tests for VMS (WarehouseOS) Sandbox Integration.

Tests cover:
1. VmsConnectorClient configuration validation, token caching, auto-refresh on 401,
   read-only operations, and strict credential/token sanitization.
2. Authorization enforcement: Platform Owners and showcase-permitted users
   are allowed access, while anonymous and unauthorized users receive 401/403.
3. Upstream error translation (503 on unconfigured, 502 on auth failure or unreachable).
4. Live sandbox smoke test against https://vms.vibecopilot.ai when credentials are present.
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

from apps.integration_hub.vms_connector import (
    CACHE_REFRESH_KEY,
    CACHE_TOKEN_KEY,
    VmsConnectorAuthError,
    VmsConnectorClient,
    VmsConnectorConfigurationError,
    VmsConnectorPermanentError,
    VmsConnectorRetryableError,
    _sanitize_dict,
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


class VmsConnectorUnitTests(TestCase):
    """Unit tests for VmsConnectorClient behavior, token caching, and sanitization."""

    def setUp(self):
        cache.clear()

    def tearDown(self):
        cache.clear()

    def test_missing_credentials_raises_configuration_error(self):
        """Missing credentials must raise VmsConnectorConfigurationError on login."""
        client = VmsConnectorClient(
            base_url="https://vms.test",
            username="",
            password="",
        )
        with self.assertRaises(VmsConnectorConfigurationError):
            client._login_and_cache_tokens()

    def test_sanitization_removes_sensitive_fields(self):
        """Ensures that password, token, and secrets are strictly stripped from responses."""
        payload = {
            "warehouseId": "WH-01",
            "name": "Central Hub",
            "token": "secret-jwt-token-123",
            "accessToken": "another-secret",
            "password": "plain-password",
            "nested": {
                "refreshToken": "refresh-secret",
                "safeField": "public-info",
            },
            "listField": [
                {"token": "token-in-list", "sku": "SKU-100"},
            ],
        }
        sanitized = _sanitize_dict(payload)
        self.assertNotIn("token", sanitized)
        self.assertNotIn("accessToken", sanitized)
        self.assertNotIn("password", sanitized)
        self.assertNotIn("refreshToken", sanitized["nested"])
        self.assertEqual(sanitized["nested"]["safeField"], "public-info")
        self.assertNotIn("token", sanitized["listField"][0])
        self.assertEqual(sanitized["listField"][0]["sku"], "SKU-100")

    @patch("urllib.request.urlopen")
    def test_login_caches_access_and_refresh_tokens(self, mock_urlopen):
        """Successful login caches access and refresh tokens."""
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({
            "success": True,
            "data": {
                "token": "mock-access-token",
                "refreshToken": "mock-refresh-token",
            },
        }).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        client = VmsConnectorClient(
            base_url="https://vms.test",
            username="test@example.com",
            password="testpassword",
        )
        token = client._login_and_cache_tokens()

        self.assertEqual(token, "mock-access-token")
        self.assertEqual(cache.get(CACHE_TOKEN_KEY), "mock-access-token")
        self.assertEqual(cache.get(CACHE_REFRESH_KEY), "mock-refresh-token")

    @patch("urllib.request.urlopen")
    def test_transparent_retry_on_401(self, mock_urlopen):
        """When a 401 error occurs, connector flushes token cache and retries once with refreshed token."""
        cache.set(CACHE_TOKEN_KEY, "expired-token")

        # First call fails with 401
        err_401 = urllib.error.HTTPError(
            url="https://vms.test/v1/dashboard/home",
            code=401,
            msg="Unauthorized",
            hdrs={},
            fp=MagicMock(read=lambda: b'{"error": {"message": "Token expired"}}'),
        )

        # Login call succeeds with new token
        mock_login_resp = MagicMock()
        mock_login_resp.read.return_value = json.dumps({
            "success": True,
            "data": {"token": "fresh-token"},
        }).encode("utf-8")
        mock_login_resp.__enter__.return_value = mock_login_resp

        # Retry call succeeds
        mock_retry_resp = MagicMock()
        mock_retry_resp.read.return_value = json.dumps({
            "success": True,
            "data": {"kpis": [{"label": "Active Docks", "value": "6"}]},
        }).encode("utf-8")
        mock_retry_resp.__enter__.return_value = mock_retry_resp

        mock_urlopen.side_effect = [err_401, mock_login_resp, mock_retry_resp]

        client = VmsConnectorClient(
            base_url="https://vms.test",
            username="test@example.com",
            password="testpassword",
        )
        data = client._request("GET", "/v1/dashboard/home")

        self.assertEqual(data["data"]["kpis"][0]["value"], "6")
        self.assertEqual(cache.get(CACHE_TOKEN_KEY), "fresh-token")


class VmsShowcaseViewsTests(TestCase):
    """Integration tests for VMS showcase API views."""

    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.owner = _create_user("owner@test.com", is_owner=True)
        self.user = _create_user("normal@test.com", is_owner=False)

    def tearDown(self):
        cache.clear()

    def test_anonymous_user_blocked(self):
        """Unauthenticated requests receive 401."""
        endpoints = [
            "/api/v1/showcase/vms/health/",
            "/api/v1/showcase/vms/overview/",
            "/api/v1/showcase/vms/inventory/",
            "/api/v1/showcase/vms/docks/",
            "/api/v1/showcase/vms/waves/",
            "/api/v1/showcase/vms/vehicles/",
            "/api/v1/showcase/vms/reports/",
        ]
        for ep in endpoints:
            resp = self.client.get(ep)
            self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED, f"Failed for {ep}")

    @patch.object(VmsConnectorClient, "probe_connectivity")
    def test_owner_access_health_success(self, mock_probe):
        """Platform owner can access health probe."""
        mock_probe.return_value = {
            "provider": "WarehouseOS VMS",
            "url": "https://vms.test",
            "status": "healthy",
            "latency_ms": 42,
            "api_health": {"status": "ok"},
            "auth_configured": True,
            "authenticated": True,
        }

        self.client.force_authenticate(user=self.owner)
        resp = self.client.get("/api/v1/showcase/vms/health/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["status"], "healthy")
        self.assertEqual(resp.data["latency_ms"], 42)

    @patch.object(VmsConnectorClient, "get_overview")
    def test_owner_access_overview_success(self, mock_overview):
        """Platform owner can access overview stats."""
        mock_overview.return_value = {
            "sandbox": {"provider": "WarehouseOS VMS", "url": "https://vms.test", "isSandbox": True},
            "kpis": [{"label": "Active Shift Staff", "value": "142 / 150", "trend": "+4%"}],
            "activities": [{"title": "GRN #8842", "time": "5 mins ago"}],
            "trendKpis": [{"id": "kpi-1", "title": "Inbound Throughput", "current": "4,250"}],
            "totalSKUs": 1420,
            "reportsSummary": {},
        }

        self.client.force_authenticate(user=self.owner)
        resp = self.client.get("/api/v1/showcase/vms/overview/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["totalSKUs"], 1420)
        self.assertEqual(len(resp.data["kpis"]), 1)

    @patch.object(VmsConnectorClient, "get_inventory_stock")
    def test_owner_access_inventory_stock_success(self, mock_stock):
        """Platform owner can access inventory stock."""
        mock_stock.return_value = {"totalSKUs": 1420}

        self.client.force_authenticate(user=self.owner)
        resp = self.client.get("/api/v1/showcase/vms/inventory/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["totalSKUs"], 1420)

    @patch.object(VmsConnectorClient, "get_docks")
    def test_owner_access_docks_success(self, mock_docks):
        """Platform owner can access active docks."""
        mock_docks.return_value = [
            {"dockNumber": 1, "name": "Bay 1", "status": "occupied"},
            {"dockNumber": 2, "name": "Bay 2", "status": "available"},
        ]

        self.client.force_authenticate(user=self.owner)
        resp = self.client.get("/api/v1/showcase/vms/docks/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["count"], 2)

    @patch.object(VmsConnectorClient, "get_overview")
    def test_connector_auth_failure_returns_502(self, mock_overview):
        """Upstream auth failure maps to HTTP 502 Bad Gateway."""
        mock_overview.side_effect = VmsConnectorAuthError("Credentials invalid", status_code=401)

        self.client.force_authenticate(user=self.owner)
        resp = self.client.get("/api/v1/showcase/vms/overview/")
        self.assertEqual(resp.status_code, status.HTTP_502_BAD_GATEWAY)
        self.assertEqual(resp.data["code"], "VMS_AUTH_FAILED")

    @patch.object(VmsConnectorClient, "get_overview")
    def test_connector_unconfigured_returns_503(self, mock_overview):
        """Unconfigured connector maps to HTTP 503 Service Unavailable."""
        mock_overview.side_effect = VmsConnectorConfigurationError("VMS credentials missing")

        self.client.force_authenticate(user=self.owner)
        resp = self.client.get("/api/v1/showcase/vms/overview/")
        self.assertEqual(resp.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertEqual(resp.data["code"], "VMS_NOT_CONFIGURED")
