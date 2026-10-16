"""VMS (WarehouseOS) Connector HTTP Client for Warehouse Management Sandbox Integration.

Provides a dedicated, strictly isolated, server-to-server HTTP client for communicating
with the WarehouseOS VMS sandbox API (https://vms.vibecopilot.ai).
Resolves base URL and credentials exclusively from server-side environment/settings.
Never logs or leaks credentials or JWT tokens in errors, logs, or representations.
Enforces read-only operations and strict server-side sanitization.
"""

from __future__ import annotations

import json
import logging
import os
import socket
import time
from typing import Any, Dict, List, Optional
import urllib.error
import urllib.parse
import urllib.request

from django.conf import settings
from django.core.cache import cache

from common.correlation import get_correlation_id

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_SECONDS = 10
CACHE_TOKEN_KEY = "vibeconnect_vms_access_token"
CACHE_REFRESH_KEY = "vibeconnect_vms_refresh_token"
ACCESS_TOKEN_CACHE_TTL = 240  # 4 minutes
REFRESH_TOKEN_CACHE_TTL = 82800  # 23 hours

SENSITIVE_FIELDS = frozenset([
    "password",
    "token",
    "accessToken",
    "access_token",
    "refreshToken",
    "refresh_token",
    "client_secret",
    "secret",
])


class VmsConnectorError(Exception):
    """Base exception for VMS connector communication failures."""

    def __init__(
        self,
        message: str,
        failure_code: str = "VMS_INTEGRATION_ERROR",
        status_code: Optional[int] = None,
        detail: str = "",
        is_retryable: bool = False,
    ):
        super().__init__(message)
        self.message = message
        self.failure_code = failure_code
        self.status_code = status_code
        self.detail = detail
        self.is_retryable = is_retryable

    def __str__(self) -> str:
        code_str = f"[{self.failure_code}]" if self.failure_code else ""
        status_str = f" (HTTP {self.status_code})" if self.status_code else ""
        return f"{code_str}{status_str} {self.message}".strip()


class VmsConnectorConfigurationError(VmsConnectorError):
    """Raised when connector configuration (URL or credentials) is missing or invalid."""

    def __init__(self, message: str, detail: str = ""):
        super().__init__(
            message=message,
            failure_code="CONFIGURATION_ERROR",
            status_code=None,
            detail=detail,
            is_retryable=False,
        )


class VmsConnectorAuthError(VmsConnectorError):
    """Raised when authentication against VMS fails (invalid credentials or token rejection)."""

    def __init__(self, message: str, status_code: Optional[int] = 401, detail: str = ""):
        super().__init__(
            message=message,
            failure_code="AUTHENTICATION_FAILED",
            status_code=status_code,
            detail=detail,
            is_retryable=False,
        )


class VmsConnectorPermanentError(VmsConnectorError):
    """Non-retryable failure (validation, 403, 404, 409)."""

    def __init__(
        self,
        message: str,
        failure_code: str = "PERMANENT_ERROR",
        status_code: Optional[int] = None,
        detail: str = "",
    ):
        super().__init__(
            message=message,
            failure_code=failure_code,
            status_code=status_code,
            detail=detail,
            is_retryable=False,
        )


class VmsConnectorRetryableError(VmsConnectorError):
    """Transient network or server failure (500, 502, 503, 504, connection timeouts)."""

    def __init__(
        self,
        message: str,
        failure_code: str = "TRANSIENT_NETWORK_ERROR",
        status_code: Optional[int] = None,
        detail: str = "",
    ):
        super().__init__(
            message=message,
            failure_code=failure_code,
            status_code=status_code,
            detail=detail,
            is_retryable=True,
        )


def _sanitize_dict(data: Any) -> Any:
    """Recursively strip any sensitive authentication tokens or credentials from returned structures."""
    if isinstance(data, dict):
        return {
            k: _sanitize_dict(v)
            for k, v in data.items()
            if k not in SENSITIVE_FIELDS
        }
    if isinstance(data, list):
        return [_sanitize_dict(item) for item in data]
    return data


class VmsConnectorClient:
    """Server-side client communicating with the WarehouseOS (VMS) sandbox API.

    Handles token lifecycle management, Bearer authorization, request signing,
    and response sanitization. Exposes strictly read-only warehouse operations.
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        timeout: int = DEFAULT_TIMEOUT_SECONDS,
    ):
        if base_url is not None:
            self.base_url = base_url.strip().rstrip("/")
        else:
            self.base_url = (
                getattr(settings, "VIBECONNECT_VMS_BACKEND_URL", "")
                or os.environ.get("VIBECONNECT_VMS_BACKEND_URL", "")
                or "https://vms.vibecopilot.ai"
            ).strip().rstrip("/")

        if username is not None:
            self.username = username.strip()
        else:
            self.username = (
                getattr(settings, "VIBECONNECT_VMS_USERNAME", "")
                or os.environ.get("VIBECONNECT_VMS_USERNAME", "")
            ).strip()

        if password is not None:
            self.password = password.strip()
        else:
            self.password = (
                getattr(settings, "VIBECONNECT_VMS_PASSWORD", "")
                or os.environ.get("VIBECONNECT_VMS_PASSWORD", "")
            ).strip()

        self.timeout = timeout

    # -------------------------------------------------------------------------
    # Authentication & Token Management
    # -------------------------------------------------------------------------

    def _get_access_token(self, force_refresh: bool = False) -> str:
        """Retrieves a valid Bearer access token, acquiring a new one if missing or expired."""
        if not force_refresh:
            cached_token = cache.get(CACHE_TOKEN_KEY)
            if cached_token:
                return cached_token

        # Try refreshing first if we have a refresh token
        refresh_token = cache.get(CACHE_REFRESH_KEY)
        if refresh_token and not force_refresh:
            try:
                return self._rotate_refresh_token(refresh_token)
            except Exception as e:
                logger.info("VMS token rotation unsuccessful, falling back to full login: %s", type(e).__name__)

        # Full login with credentials
        return self._login_and_cache_tokens()

    def _rotate_refresh_token(self, refresh_token: str) -> str:
        """Rotates refresh token via POST /v1/auth/refresh."""
        url = f"{self.base_url}/v1/auth/refresh"
        payload = json.dumps({"refreshToken": refresh_token}).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "VibeConnect-VMS-Connector/1.0",
        }

        req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return self._extract_and_cache_tokens(data)
        except urllib.error.HTTPError as e:
            if e.code in (400, 401, 403):
                cache.delete(CACHE_TOKEN_KEY)
                cache.delete(CACHE_REFRESH_KEY)
                raise VmsConnectorAuthError("VMS refresh token expired or rejected.", status_code=e.code)
            raise self._classify_http_error(e, "Token refresh failed")

    def _login_and_cache_tokens(self) -> str:
        """Performs M2M authentication with VMS credentials via POST /v1/auth/login."""
        if not self.username or not self.password:
            raise VmsConnectorConfigurationError(
                "VMS sandbox credentials (username/password) are not configured.",
                detail="Ensure VIBECONNECT_VMS_USERNAME and VIBECONNECT_VMS_PASSWORD are set.",
            )

        url = f"{self.base_url}/v1/auth/login"
        payload = json.dumps({
            "email": self.username,
            "password": self.password,
        }).encode("utf-8")

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "VibeConnect-VMS-Connector/1.0",
        }

        req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return self._extract_and_cache_tokens(data)
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                logger.warning("VMS upstream rejected credentials for user %s: HTTP %s", self.username, e.code)
                raise VmsConnectorAuthError("Invalid VMS sandbox credentials.", status_code=e.code)
            raise self._classify_http_error(e, "VMS authentication failed")
        except urllib.error.URLError as e:
            raise VmsConnectorRetryableError(f"Network error connecting to VMS: {e.reason}")
        except socket.timeout:
            raise VmsConnectorRetryableError("Connection timed out while authenticating with VMS.")

    def _extract_and_cache_tokens(self, data: Dict[str, Any]) -> str:
        """Parses upstream token response and caches access & refresh tokens safely."""
        resp_data = data.get("data", {}) if isinstance(data.get("data"), dict) else data
        access_token = (
            resp_data.get("token")
            or resp_data.get("accessToken")
            or resp_data.get("access_token")
        )
        refresh_token = (
            resp_data.get("refreshToken")
            or resp_data.get("refresh_token")
        )

        if not access_token:
            raise VmsConnectorAuthError("VMS login succeeded but no access token was returned.")

        cache.set(CACHE_TOKEN_KEY, access_token, timeout=ACCESS_TOKEN_CACHE_TTL)
        if refresh_token:
            cache.set(CACHE_REFRESH_KEY, refresh_token, timeout=REFRESH_TOKEN_CACHE_TTL)

        return access_token

    # -------------------------------------------------------------------------
    # Core Request Dispatcher
    # -------------------------------------------------------------------------

    def _request(
        self,
        method: str,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        requires_auth: bool = True,
        is_retry: bool = False,
    ) -> Any:
        """Dispatches an HTTP request to the VMS upstream API with Bearer token authentication."""
        url = f"{self.base_url}{path}"
        if params:
            clean_params = {k: v for k, v in params.items() if v is not None}
            if clean_params:
                url = f"{url}?{urllib.parse.urlencode(clean_params)}"

        headers = {
            "Accept": "application/json",
            "User-Agent": "VibeConnect-VMS-Connector/1.0",
        }

        cid = get_correlation_id()
        if cid:
            headers["X-Correlation-ID"] = cid

        if requires_auth:
            token = self._get_access_token(force_refresh=is_retry)
            headers["Authorization"] = f"Bearer {token}"

        req = urllib.request.Request(url, headers=headers, method=method)

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw_body = resp.read().decode("utf-8")
                try:
                    payload = json.loads(raw_body)
                    return _sanitize_dict(payload)
                except json.JSONDecodeError:
                    return {"raw": raw_body}
        except urllib.error.HTTPError as e:
            # Handle token expiration (401) with a single transparent retry
            if e.code == 401 and requires_auth and not is_retry:
                logger.info("VMS 401 received; refreshing token and retrying once...")
                cache.delete(CACHE_TOKEN_KEY)
                return self._request(method, path, params, requires_auth=True, is_retry=True)
            raise self._classify_http_error(e, f"VMS request failed: {method} {path}")
        except urllib.error.URLError as e:
            raise VmsConnectorRetryableError(f"Network error contacting VMS: {e.reason}")
        except socket.timeout:
            raise VmsConnectorRetryableError(f"Timed out waiting for VMS API: {method} {path}")

    def _classify_http_error(self, exc: urllib.error.HTTPError, context: str) -> VmsConnectorError:
        """Maps HTTP status codes to typed exceptions."""
        try:
            err_body = exc.read().decode("utf-8")
            err_json = json.loads(err_body)
            msg = err_json.get("error", {}).get("message") or err_json.get("message") or err_body[:200]
        except Exception:
            msg = exc.reason or f"HTTP {exc.code}"

        if exc.code == 401:
            return VmsConnectorAuthError(f"{context}: {msg}", status_code=401)
        if exc.code == 403:
            return VmsConnectorPermanentError(f"{context}: Forbidden. {msg}", failure_code="FORBIDDEN", status_code=403)
        if exc.code == 404:
            return VmsConnectorPermanentError(f"{context}: Resource not found. {msg}", failure_code="NOT_FOUND", status_code=404)
        if exc.code in (500, 502, 503, 504):
            return VmsConnectorRetryableError(f"{context}: Upstream server error {exc.code}. {msg}", status_code=exc.code)
        return VmsConnectorPermanentError(f"{context}: Client error {exc.code}. {msg}", status_code=exc.code)

    # -------------------------------------------------------------------------
    # Public Read-Only Domain Endpoints
    # -------------------------------------------------------------------------

    def probe_connectivity(self) -> Dict[str, Any]:
        """Probes VMS sandbox health and measures network latency."""
        start_time = time.time()
        result = {
            "provider": "WarehouseOS VMS",
            "url": self.base_url,
            "status": "healthy",
            "latency_ms": 0,
            "api_health": None,
            "auth_configured": bool(self.username and self.password),
            "authenticated": False,
        }

        try:
            health_resp = self._request("GET", "/api/health/live", requires_auth=False)
            latency = int((time.time() - start_time) * 1000)
            result["latency_ms"] = latency
            result["api_health"] = health_resp
        except Exception as e:
            result["status"] = "unreachable"
            result["detail"] = str(e)
            result["latency_ms"] = int((time.time() - start_time) * 1000)
            return result

        # Check authentication capability
        if result["auth_configured"]:
            try:
                self._get_access_token()
                result["authenticated"] = True
            except VmsConnectorAuthError as e:
                result["status"] = "auth_failed"
                result["detail"] = f"VMS authentication failed: {e.message}"
            except Exception as e:
                result["status"] = "degraded"
                result["detail"] = f"Auth check encountered transient error: {str(e)}"

        return result

    def get_overview(self) -> Dict[str, Any]:
        """Fetches aggregated operational overview for the VMS demonstration console."""
        # 1. Fetch dashboard KPIs & activities
        dashboard_data = {}
        try:
            home_resp = self._request("GET", "/v1/dashboard/home", requires_auth=True)
            if isinstance(home_resp, dict) and "data" in home_resp:
                dashboard_data = home_resp["data"]
        except Exception as e:
            logger.warning("Could not fetch /v1/dashboard/home: %s", e)

        # 2. Fetch KPI trends
        trend_kpis = []
        try:
            kpis_resp = self._request("GET", "/v1/dashboard/kpis", requires_auth=True)
            if isinstance(kpis_resp, dict) and "data" in kpis_resp:
                trend_kpis = kpis_resp["data"]
        except Exception as e:
            logger.warning("Could not fetch /v1/dashboard/kpis: %s", e)

        # 3. Fetch inventory total SKUs (can be called unauthenticated or authenticated)
        total_skus = 0
        try:
            stock_resp = self._request("GET", "/v1/inventory/stock", requires_auth=False)
            if isinstance(stock_resp, dict):
                total_skus = stock_resp.get("totalSKUs", 0)
        except Exception as e:
            logger.warning("Could not fetch /v1/inventory/stock: %s", e)

        # 4. Fetch reports summary for charts
        reports_summary = {}
        try:
            rep_resp = self._request("GET", "/v1/reports/summary", requires_auth=True)
            if isinstance(rep_resp, dict) and "data" in rep_resp:
                reports_summary = rep_resp["data"]
        except Exception as e:
            logger.warning("Could not fetch /v1/reports/summary: %s", e)

        return {
            "sandbox": {
                "provider": "WarehouseOS VMS",
                "url": self.base_url,
                "isSandbox": True,
            },
            "kpis": dashboard_data.get("kpis", []),
            "activities": dashboard_data.get("activities", []),
            "trendKpis": trend_kpis,
            "totalSKUs": total_skus,
            "reportsSummary": reports_summary,
        }

    def get_inventory_stock(self) -> Dict[str, Any]:
        """Fetches inventory stock statistics."""
        resp = self._request("GET", "/v1/inventory/stock", requires_auth=False)
        return resp if isinstance(resp, dict) else {"totalSKUs": 0}

    def get_docks(self) -> List[Dict[str, Any]]:
        """Fetches active dock bays and assignments."""
        resp = self._request("GET", "/v1/org/docks", requires_auth=False)
        if isinstance(resp, dict) and "data" in resp and isinstance(resp["data"], list):
            return resp["data"]
        return []

    def get_waves(self) -> List[Dict[str, Any]]:
        """Fetches active order fulfillment waves."""
        resp = self._request("GET", "/v1/fulfillment/waves", requires_auth=False)
        if isinstance(resp, dict):
            return resp.get("activeWaves", [])
        return []

    def get_vehicles(self) -> Dict[str, Any]:
        """Fetches gate vehicle movements and yard queue."""
        resp = self._request("GET", "/v1/gate/vehicles", requires_auth=True)
        if isinstance(resp, dict) and "data" in resp:
            return resp["data"]
        return {"activeCount": 0, "totalCount": 0, "vehicles": []}

    def get_reports_summary(self) -> Dict[str, Any]:
        """Fetches QC status distribution and hourly throughput."""
        resp = self._request("GET", "/v1/reports/summary", requires_auth=True)
        if isinstance(resp, dict) and "data" in resp:
            return resp["data"]
        return {}

    def get_warehouses(self) -> List[Dict[str, Any]]:
        """Fetches master warehouses."""
        resp = self._request("GET", "/v1/master/warehouses", requires_auth=True)
        if isinstance(resp, dict) and "data" in resp and isinstance(resp["data"], dict):
            return resp["data"].get("warehouses", [])
        return []
