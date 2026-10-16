"""HRMS Connector HTTP Client for PeoplePulse Sandbox Integration.

Provides a dedicated, strictly isolated, server-to-server HTTP client for communicating
with the PeoplePulse HRMS sandbox API.
Zero hardcoding: base URL and credentials resolve exclusively from server-side configuration.
Never logs or leaks credentials or JWT tokens in errors, logs, or representations.
Enforces read-only operations and strict server-side PII sanitization.
"""

from __future__ import annotations

import json
import logging
import os
import socket
import time
from typing import Any, Optional
import urllib.error
import urllib.parse
import urllib.request

from django.conf import settings
from django.core.cache import cache

from common.correlation import get_correlation_id

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_SECONDS = 10
CACHE_TOKEN_KEY = "vibeconnect_hrms_access_token"
CACHE_REFRESH_KEY = "vibeconnect_hrms_refresh_token"
ACCESS_TOKEN_CACHE_TTL = 240  # 4 minutes (sandbox JWT access lifetime is 5m)
REFRESH_TOKEN_CACHE_TTL = 82800  # 23 hours (sandbox JWT refresh lifetime is 24h)

# Fields that must NEVER be returned or exposed to frontend
SENSITIVE_EMPLOYEE_FIELDS = frozenset([
    "pan",
    "aadhaar",
    "uan",
    "esi",
    "bank_name",
    "bank_account",
    "bank_account_no",
    "ifsc",
    "ifsc_code",
    "ctc",
    "salary",
    "tax_regime",
    "tax_saving_deductions",
    "bankName",
    "bankAccount",
    "bankAccountNo",
    "ifscCode",
    "taxRegime",
    "taxSavingDeductions",
    "password",
])


class HrmsConnectorError(Exception):
    """Base exception for HRMS connector communication failures."""

    def __init__(
        self,
        message: str,
        failure_code: str = "HRMS_INTEGRATION_ERROR",
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


class HrmsConnectorConfigurationError(HrmsConnectorError):
    """Raised when connector configuration (URL or credentials) is missing or invalid."""

    def __init__(self, message: str, detail: str = ""):
        super().__init__(
            message=message,
            failure_code="CONFIGURATION_ERROR",
            status_code=None,
            detail=detail,
            is_retryable=False,
        )


class HrmsConnectorAuthError(HrmsConnectorError):
    """Raised when authentication against HRMS fails (invalid credentials or token rejection)."""

    def __init__(self, message: str, status_code: Optional[int] = 401, detail: str = ""):
        super().__init__(
            message=message,
            failure_code="AUTHENTICATION_FAILED",
            status_code=status_code,
            detail=detail,
            is_retryable=False,
        )


class HrmsConnectorPermanentError(HrmsConnectorError):
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


class HrmsConnectorRetryableError(HrmsConnectorError):
    """Transient failure suitable for retry (timeout, network error, 5xx upstream)."""

    def __init__(
        self,
        message: str,
        failure_code: str = "TRANSIENT_ERROR",
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


class HrmsConnectorClient:
    """HTTP client communicating with external PeoplePulse HRMS sandbox endpoints."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        timeout: int = DEFAULT_TIMEOUT_SECONDS,
    ):
        # 1. Resolve Base URL
        resolved_url = (base_url or "").strip()
        if not resolved_url:
            resolved_url = (
                getattr(settings, "VIBECONNECT_HRMS_BACKEND_URL", "")
                or os.environ.get("VIBECONNECT_HRMS_BACKEND_URL", "")
                or os.environ.get("HRMS_BACKEND_URL", "")
            ).strip()

        if not resolved_url:
            raise HrmsConnectorConfigurationError(
                "HRMS backend URL is not configured. Please set VIBECONNECT_HRMS_BACKEND_URL."
            )

        self.base_url = resolved_url.rstrip("/")
        self.timeout = timeout

        # 2. Resolve credentials
        resolved_user = (username or "").strip()
        if not resolved_user:
            resolved_user = (
                getattr(settings, "VIBECONNECT_HRMS_USERNAME", "")
                or os.environ.get("VIBECONNECT_HRMS_USERNAME", "")
                or os.environ.get("HRMS_USERNAME", "")
            ).strip()

        resolved_pwd = (password or "").strip()
        if not resolved_pwd:
            resolved_pwd = (
                getattr(settings, "VIBECONNECT_HRMS_PASSWORD", "")
                or os.environ.get("VIBECONNECT_HRMS_PASSWORD", "")
                or os.environ.get("HRMS_PASSWORD", "")
            ).strip()

        if not resolved_user or not resolved_pwd:
            raise HrmsConnectorConfigurationError(
                "HRMS credentials are not configured. Please set VIBECONNECT_HRMS_USERNAME and VIBECONNECT_HRMS_PASSWORD."
            )

        self._username = resolved_user
        self._password = resolved_pwd

    # ----------------------------------------------------------------------
    # Authentication & Token Management
    # ----------------------------------------------------------------------

    def _get_cached_access_token(self) -> Optional[str]:
        try:
            return cache.get(CACHE_TOKEN_KEY)
        except Exception:
            return None

    def _get_cached_refresh_token(self) -> Optional[str]:
        try:
            return cache.get(CACHE_REFRESH_KEY)
        except Exception:
            return None

    def _set_cached_tokens(self, access_token: str, refresh_token: Optional[str] = None) -> None:
        try:
            if access_token:
                cache.set(CACHE_TOKEN_KEY, access_token, timeout=ACCESS_TOKEN_CACHE_TTL)
            if refresh_token:
                cache.set(CACHE_REFRESH_KEY, refresh_token, timeout=REFRESH_TOKEN_CACHE_TTL)
        except Exception as exc:
            logger.warning("Failed to store HRMS tokens in cache: %s", exc)

    def _clear_cached_tokens(self) -> None:
        try:
            cache.delete(CACHE_TOKEN_KEY)
            cache.delete(CACHE_REFRESH_KEY)
        except Exception:
            pass

    def authenticate(self) -> str:
        """Authenticates with username/password via POST /api/auth/token/ and caches tokens."""
        url = f"{self.base_url}/api/auth/token/"
        payload = {"username": self._username, "password": self._password}
        data = json.dumps(payload).encode("utf-8")

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        correlation_id = get_correlation_id()
        if correlation_id:
            headers["X-Request-ID"] = correlation_id

        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                body = json.loads(resp.read().decode("utf-8"))
                access = body.get("access")
                refresh = body.get("refresh")
                if not access:
                    raise HrmsConnectorAuthError("HRMS auth response missing access token.")
                self._set_cached_tokens(access, refresh)
                return access
        except urllib.error.HTTPError as exc:
            self._clear_cached_tokens()
            detail = ""
            try:
                detail = exc.read().decode("utf-8")
            except Exception:
                pass
            if exc.code in (400, 401, 403):
                raise HrmsConnectorAuthError(
                    f"HRMS authentication failed (HTTP {exc.code}). Check credentials.",
                    status_code=exc.code,
                    detail=detail,
                ) from exc
            raise HrmsConnectorRetryableError(
                f"HRMS auth endpoint returned HTTP {exc.code}.",
                status_code=exc.code,
                detail=detail,
            ) from exc
        except (socket.timeout, TimeoutError, urllib.error.URLError) as exc:
            raise HrmsConnectorRetryableError(
                f"Network error or timeout reaching HRMS auth: {exc}",
                detail=str(exc),
            ) from exc
        except Exception as exc:
            raise HrmsConnectorPermanentError(f"Unexpected error authenticating with HRMS: {exc}") from exc

    def refresh_access_token(self) -> str:
        """Attempts to obtain a new access token using cached refresh token."""
        refresh_token = self._get_cached_refresh_token()
        if not refresh_token:
            return self.authenticate()

        url = f"{self.base_url}/api/auth/token/refresh/"
        payload = {"refresh": refresh_token}
        data = json.dumps(payload).encode("utf-8")

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        correlation_id = get_correlation_id()
        if correlation_id:
            headers["X-Request-ID"] = correlation_id

        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                body = json.loads(resp.read().decode("utf-8"))
                access = body.get("access")
                if not access:
                    return self.authenticate()
                self._set_cached_tokens(access, refresh_token)
                return access
        except urllib.error.HTTPError as exc:
            # Refresh token may be expired or blacklisted; fall back to full authentication
            logger.info("HRMS token refresh failed (HTTP %s); re-authenticating.", exc.code)
            return self.authenticate()
        except Exception as exc:
            logger.warning("HRMS token refresh encountered %s; re-authenticating.", exc)
            return self.authenticate()

    def get_valid_access_token(self) -> str:
        """Returns a valid access token from cache or authenticates."""
        token = self._get_cached_access_token()
        if token:
            return token
        return self.authenticate()

    # ----------------------------------------------------------------------
    # Core HTTP Request Handler
    # ----------------------------------------------------------------------

    def _send_request(
        self,
        endpoint: str,
        method: str = "GET",
        params: Optional[dict[str, Any]] = None,
        retries_on_auth: bool = True,
    ) -> Any:
        """Executes HTTP request to HRMS endpoint with Bearer auth and auto-refresh."""
        token = self.get_valid_access_token()

        url = f"{self.base_url}{endpoint}"
        if params:
            query_str = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
            if query_str:
                url = f"{url}?{query_str}"

        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
        }
        correlation_id = get_correlation_id()
        if correlation_id:
            headers["X-Request-ID"] = correlation_id

        req = urllib.request.Request(url, headers=headers, method=method)

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw_bytes = resp.read()
                if not raw_bytes:
                    return {}
                return json.loads(raw_bytes.decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body_text = ""
            try:
                body_text = exc.read().decode("utf-8")
            except Exception:
                pass

            # Handle token expiry / 401 with one-time retry
            if exc.code == 401 and retries_on_auth:
                logger.info("Received HTTP 401 from HRMS endpoint %s; refreshing token and retrying.", endpoint)
                self._clear_cached_tokens()
                self.authenticate()
                return self._send_request(
                    endpoint=endpoint,
                    method=method,
                    params=params,
                    retries_on_auth=False,
                )

            if exc.code in (401, 403):
                raise HrmsConnectorAuthError(
                    f"HRMS permission or authorization denied (HTTP {exc.code}) on {endpoint}.",
                    status_code=exc.code,
                    detail=body_text,
                ) from exc
            if exc.code == 404:
                raise HrmsConnectorPermanentError(
                    f"HRMS resource not found (HTTP 404) at {endpoint}.",
                    status_code=404,
                    detail=body_text,
                ) from exc
            if 400 <= exc.code < 500:
                raise HrmsConnectorPermanentError(
                    f"HRMS request rejected (HTTP {exc.code}) on {endpoint}.",
                    status_code=exc.code,
                    detail=body_text,
                ) from exc

            raise HrmsConnectorRetryableError(
                f"HRMS upstream service returned HTTP {exc.code} on {endpoint}.",
                status_code=exc.code,
                detail=body_text,
            ) from exc
        except (socket.timeout, TimeoutError, urllib.error.URLError) as exc:
            reason = getattr(exc, "reason", None) or str(exc)
            raise HrmsConnectorRetryableError(
                f"Network error or timeout reaching HRMS: {reason}",
                detail=str(exc),
            ) from exc
        except json.JSONDecodeError as exc:
            raise HrmsConnectorPermanentError(
                f"Failed to parse JSON response from HRMS: {exc}",
                detail=str(exc),
            ) from exc
        except Exception as exc:
            raise HrmsConnectorPermanentError(f"Unexpected error communicating with HRMS: {exc}") from exc

    # ----------------------------------------------------------------------
    # PII Sanitization
    # ----------------------------------------------------------------------

    @staticmethod
    def _sanitize_employee(raw_emp: dict[str, Any]) -> dict[str, Any]:
        """Strips all sensitive financial, tax, and government identity fields.

        Returns only UI display fields adhering to strict data minimization.
        """
        first_name = str(raw_emp.get("firstName") or raw_emp.get("first_name") or "").strip()
        last_name = str(raw_emp.get("lastName") or raw_emp.get("last_name") or "").strip()
        full_name = f"{first_name} {last_name}".strip()
        if not full_name:
            full_name = str(raw_emp.get("fullName") or raw_emp.get("name") or "Employee")

        sanitized = {
            "id": raw_emp.get("id"),
            "code": raw_emp.get("code") or raw_emp.get("employeeCode") or raw_emp.get("employee_code") or "",
            "firstName": first_name,
            "lastName": last_name,
            "fullName": full_name,
            "email": raw_emp.get("email") or "",
            "phone": raw_emp.get("phone") or "",
            "roleName": raw_emp.get("roleName") or raw_emp.get("role_name") or raw_emp.get("designation") or "",
            "siteName": raw_emp.get("siteName") or raw_emp.get("site_name") or raw_emp.get("location") or "",
            "department": raw_emp.get("department"),
            "departmentName": raw_emp.get("departmentName") or raw_emp.get("department_name") or "",
            "status": raw_emp.get("status") or "active",
            "doj": raw_emp.get("doj") or raw_emp.get("joiningDate") or "",
            "photo": raw_emp.get("photo"),
            "isWfh": bool(raw_emp.get("isWfh") or raw_emp.get("is_wfh", False)),
            "employeeType": raw_emp.get("employeeType") or raw_emp.get("employee_type") or "Full Time",
        }

        return sanitized

    # ----------------------------------------------------------------------
    # Public Domain API Operations (Read-Only)
    # ----------------------------------------------------------------------

    def probe_connectivity(self) -> dict[str, Any]:
        """Probes HRMS endpoint connectivity using safe read-only GET /api/auth/me/.

        Returns connection health status, latency, and basic verified identity.
        """
        start_time = time.time()
        try:
            token = self.get_valid_access_token()
            url = f"{self.base_url}/api/auth/me/"
            headers = {
                "Accept": "application/json",
                "Authorization": f"Bearer {token}",
            }
            correlation_id = get_correlation_id()
            if correlation_id:
                headers["X-Request-ID"] = correlation_id

            req = urllib.request.Request(url, headers=headers, method="GET")
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                latency_ms = int((time.time() - start_time) * 1000)
                raw_bytes = resp.read()
                data = json.loads(raw_bytes.decode("utf-8")) if raw_bytes else {}
                return {
                    "status": "verified",
                    "http_status": resp.status,
                    "latency_ms": latency_ms,
                    "sandbox_url": self.base_url,
                    "user": {
                        "username": data.get("username", self._username),
                        "email": data.get("email", ""),
                    },
                    "detail": "HRMS sandbox responded successfully to health probe.",
                }
        except HrmsConnectorAuthError as exc:
            latency_ms = int((time.time() - start_time) * 1000)
            return {
                "status": "auth_failed",
                "http_status": exc.status_code or 401,
                "latency_ms": latency_ms,
                "sandbox_url": self.base_url,
                "detail": f"HRMS authentication failed: {exc.message}",
            }
        except urllib.error.HTTPError as exc:
            latency_ms = int((time.time() - start_time) * 1000)
            status_label = "auth_failed" if exc.code in (401, 403) else "unreachable"
            return {
                "status": status_label,
                "http_status": exc.code,
                "latency_ms": latency_ms,
                "sandbox_url": self.base_url,
                "detail": f"HRMS returned HTTP {exc.code} during probe.",
            }
        except (socket.timeout, TimeoutError, urllib.error.URLError) as exc:
            reason = getattr(exc, "reason", None) or str(exc)
            return {
                "status": "unreachable",
                "http_status": None,
                "latency_ms": None,
                "sandbox_url": self.base_url,
                "detail": f"Network error or timeout reaching HRMS: {reason}",
            }
        except Exception as exc:
            return {
                "status": "unreachable",
                "http_status": None,
                "latency_ms": None,
                "sandbox_url": self.base_url,
                "detail": f"Unexpected error probing HRMS: {exc}",
            }

    def list_employees(
        self,
        department: Optional[str] = None,
        search: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """Fetches employee list from GET /api/employees/ and applies PII sanitization."""
        params: dict[str, Any] = {}
        if department:
            params["department"] = department
        if search:
            params["search"] = search

        raw_data = self._send_request("/api/employees/", method="GET", params=params)

        if isinstance(raw_data, dict) and "results" in raw_data:
            items = raw_data["results"]
        elif isinstance(raw_data, list):
            items = raw_data
        else:
            items = []

        return [self._sanitize_employee(item) for item in items]

    def list_departments(self) -> list[dict[str, Any]]:
        """Fetches departments list from GET /api/organisation/departments/."""
        raw_data = self._send_request("/api/organisation/departments/", method="GET")

        if isinstance(raw_data, dict) and "results" in raw_data:
            items = raw_data["results"]
        elif isinstance(raw_data, list):
            items = raw_data
        else:
            items = []

        clean_deps = []
        for dep in items:
            clean_deps.append({
                "id": dep.get("id"),
                "name": dep.get("name") or dep.get("department_name") or "",
                "code": dep.get("code") or "",
                "head": dep.get("head"),
            })
        return clean_deps

    def get_attendance_dashboard(self) -> dict[str, Any]:
        """Fetches attendance dashboard summary metrics from GET /api/attendance/dashboard/."""
        raw_data = self._send_request("/api/attendance/dashboard/", method="GET")
        if not isinstance(raw_data, dict):
            return {
                "totalEmployees": 0,
                "presentToday": 0,
                "absentToday": 0,
                "lateToday": 0,
            }

        return {
            "totalEmployees": int(raw_data.get("totalEmployees") or raw_data.get("total_employees", 0)),
            "presentToday": int(raw_data.get("presentToday") or raw_data.get("present_today", 0)),
            "absentToday": int(raw_data.get("absentToday") or raw_data.get("absent_today", 0)),
            "lateToday": int(raw_data.get("lateToday") or raw_data.get("late_today", 0)),
        }

    def get_attendance_today(self) -> list[dict[str, Any]]:
        """Fetches today's attendance punch records from GET /api/attendance/today/."""
        raw_data = self._send_request("/api/attendance/today/", method="GET")

        if isinstance(raw_data, dict) and "results" in raw_data:
            items = raw_data["results"]
        elif isinstance(raw_data, list):
            items = raw_data
        else:
            items = []

        clean_records = []
        for rec in items:
            clean_records.append({
                "id": rec.get("id"),
                "employeeName": rec.get("employeeName") or rec.get("fullName") or "Employee",
                "employeeCode": rec.get("employeeCode") or "",
                "shiftName": rec.get("shiftName") or "General Shift",
                "shiftStart": rec.get("shiftStart") or "",
                "shiftEnd": rec.get("shiftEnd") or "",
                "attendanceDate": rec.get("attendanceDate") or "",
                "firstCheckIn": rec.get("firstCheckIn") or "",
                "lastCheckOut": rec.get("lastCheckOut") or "",
                "totalWorkHours": rec.get("totalWorkHours") or "0h 0m",
                "attendanceStatus": rec.get("attendanceStatus") or "present",
            })
        return clean_records

    def get_overview_stats(self) -> dict[str, Any]:
        """Fetches stats summary from GET /api/dashboard/stats/ or synthesizes from attendance."""
        try:
            raw_data = self._send_request("/api/dashboard/stats/", method="GET")
            if isinstance(raw_data, dict):
                return raw_data
        except Exception as exc:
            logger.info("Direct dashboard stats endpoint unavailable (%s); using attendance dashboard.", exc)

        dashboard = self.get_attendance_dashboard()
        return {
            "totalEmployees": dashboard["totalEmployees"],
            "presentCount": dashboard["presentToday"],
            "absentCount": dashboard["absentToday"],
            "lateCount": dashboard["lateToday"],
        }

    def list_designations(self) -> list[dict[str, Any]]:
        """Fetches designations list from GET /api/organisation/designations/."""
        raw_data = self._send_request("/api/organisation/designations/", method="GET")
        items = raw_data if isinstance(raw_data, list) else (raw_data.get("results", []) if isinstance(raw_data, dict) else [])
        clean_items = []
        for d in items:
            clean_items.append({
                "id": d.get("id"),
                "title": d.get("title") or "",
                "grade": d.get("grade") or "",
                "department": d.get("department"),
                "createdAt": d.get("createdAt") or "",
            })
        return clean_items

    def list_sites(self) -> list[dict[str, Any]]:
        """Fetches sites list from GET /api/organisation/sites/."""
        raw_data = self._send_request("/api/organisation/sites/", method="GET")
        items = raw_data if isinstance(raw_data, list) else (raw_data.get("results", []) if isinstance(raw_data, dict) else [])
        clean_sites = []
        for s in items:
            clean_sites.append({
                "id": s.get("id"),
                "name": s.get("name") or "",
                "siteCode": s.get("siteCode") or "",
                "status": s.get("status") or "Active",
                "address": s.get("address") or "",
                "latitude": s.get("latitude"),
                "longitude": s.get("longitude"),
                "radius": s.get("radius") or 150,
                "brandingText": s.get("brandingText") or "PeoplePulse HRMS",
                "usersCount": s.get("usersCount") or 0,
            })
        return clean_sites

    def get_leaves_summary(self) -> dict[str, Any]:
        """Fetches leave status counts from GET /api/leaves/dashboard/."""
        raw_data = self._send_request("/api/leaves/dashboard/", method="GET")
        if isinstance(raw_data, dict):
            return {
                "pending": int(raw_data.get("pending", 0)),
                "approved": int(raw_data.get("approved", 0)),
                "rejected": int(raw_data.get("rejected", 0)),
            }
        return {"pending": 0, "approved": 0, "rejected": 0}

    def list_attendance_history(self, limit: int = 50, search: Optional[str] = None) -> list[dict[str, Any]]:
        """Fetches historical attendance records from GET /api/attendance/history/ with PII sanitization."""
        params: dict[str, Any] = {}
        if search:
            params["search"] = search

        raw_data = self._send_request("/api/attendance/history/", method="GET", params=params)
        items = raw_data if isinstance(raw_data, list) else (raw_data.get("results", []) if isinstance(raw_data, dict) else [])

        clean_history = []
        for item in items[:limit]:
            clean_history.append({
                "id": item.get("id"),
                "employeeName": item.get("fullName") or item.get("employeeName") or "Employee",
                "employeeCode": item.get("employeeCode") or "",
                "designation": item.get("designation") or "",
                "attendanceDate": item.get("attendanceDate") or "",
                "shiftName": item.get("shiftName") or "General Shift",
                "firstCheckIn": item.get("firstCheckIn") or "",
                "lastCheckOut": item.get("lastCheckOut") or "",
                "totalWorkHours": item.get("totalWorkHours") or "0.00",
                "attendanceStatus": item.get("attendanceStatus") or "Present",
                "statusText": item.get("statusText") or "",
            })
        return clean_history
