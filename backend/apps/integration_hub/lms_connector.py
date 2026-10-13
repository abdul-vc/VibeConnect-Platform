"""LMS Connector HTTP Client (Phase 5C-3 Stage 2).

Provides a dedicated, strictly isolated, server-to-server HTTP client for communicating
with LMS integration endpoints.
Zero hardcoding: base URL and credentials must resolve exclusively from configuration.
Never logs or leaks credentials in errors, logs, or representations.
"""

import json
import logging
import os
import socket
from typing import Any, Optional
import urllib.error
import urllib.parse
import urllib.request

from django.conf import settings

from apps.integration_hub.sso_service import get_m2m_connector_secret
from common.correlation import get_correlation_id

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_SECONDS = 10


class LmsConnectorError(Exception):
    """Base exception for LMS connector communication failures."""

    def __init__(
        self,
        message: str,
        failure_code: str = "INTEGRATION_ERROR",
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


class LmsConnectorConfigurationError(LmsConnectorError):
    """Raised when connector configuration (URL or secret) is missing or invalid."""

    def __init__(self, message: str, detail: str = ""):
        super().__init__(
            message=message,
            failure_code="CONFIGURATION_ERROR",
            status_code=None,
            detail=detail,
            is_retryable=False,
        )


class LmsConnectorPermanentError(LmsConnectorError):
    """Non-retryable failure (validation, 401/403 auth, 409 conflict, 404 not found)."""

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


class LmsConnectorRetryableError(LmsConnectorError):
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


class LmsConnectorClient:
    """HTTP client communicating with external LMS M2M provisioning endpoints."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        secret: Optional[str] = None,
        timeout: int = DEFAULT_TIMEOUT_SECONDS,
    ):
        # 1. Resolve Base URL strictly from arguments, settings, or environment
        resolved_url = (base_url or "").strip()
        if not resolved_url:
            resolved_url = (
                getattr(settings, "VIBECONNECT_LMS_BACKEND_URL", "")
                or os.environ.get("VIBECONNECT_LMS_BACKEND_URL", "")
                or os.environ.get("LMS_BACKEND_URL", "")
            ).strip()

        if not resolved_url:
            raise LmsConnectorConfigurationError(
                "LMS backend URL is not configured. Please set VIBECONNECT_LMS_BACKEND_URL."
            )

        self.base_url = resolved_url.rstrip("/")
        self.timeout = timeout

        # 2. Resolve M2M secret
        resolved_secret = (secret or "").strip()
        if not resolved_secret:
            try:
                resolved_secret = get_m2m_connector_secret("lms")
            except Exception as exc:
                raise LmsConnectorConfigurationError(
                    "LMS M2M connector secret is not configured.",
                    detail=str(exc),
                ) from exc

        self._secret = resolved_secret

    def provision_tenant(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Calls POST /api/v1/integration/tenants/provision/ on LMS."""
        return self._send_request(
            endpoint="/api/v1/integration/tenants/provision/",
            payload=payload,
            operation_label="tenant provisioning",
        )

    def provision_user(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Calls POST /api/v1/integration/users/provision/ on LMS."""
        return self._send_request(
            endpoint="/api/v1/integration/users/provision/",
            payload=payload,
            operation_label="user provisioning",
        )

    def probe_connectivity(self) -> dict[str, Any]:
        """Probes external LMS endpoint connectivity using safe read-only request.

        If external LMS has no read-only health endpoint or returns 404, reports
        status='not_verified' without attempting any business mutations.
        """
        import time

        target_url = f"{self.base_url}/api/v1/integration/health/"
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {self._secret}",
        }
        correlation_id = get_correlation_id()
        if correlation_id:
            headers["X-Request-ID"] = correlation_id
        req = urllib.request.Request(target_url, headers=headers, method="GET")
        start_time = time.time()
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                latency_ms = int((time.time() - start_time) * 1000)
                if resp.status == 200:
                    return {
                        "status": "verified",
                        "http_status": 200,
                        "latency_ms": latency_ms,
                        "detail": "LMS integration endpoint responded successfully to health probe.",
                    }
                return {
                    "status": "not_verified",
                    "http_status": resp.status,
                    "latency_ms": latency_ms,
                    "detail": f"LMS returned HTTP {resp.status} during health probe.",
                }
        except urllib.error.HTTPError as exc:
            latency_ms = int((time.time() - start_time) * 1000)
            if exc.code == 404:
                return {
                    "status": "not_verified",
                    "http_status": 404,
                    "latency_ms": latency_ms,
                    "detail": "External LMS does not expose a supported read-only health endpoint. Status remains not_verified.",
                }
            elif exc.code in (401, 403):
                return {
                    "status": "unreachable",
                    "http_status": exc.code,
                    "latency_ms": latency_ms,
                    "detail": f"M2M authentication failed during health probe (HTTP {exc.code}).",
                }
            else:
                return {
                    "status": "unreachable",
                    "http_status": exc.code,
                    "latency_ms": latency_ms,
                    "detail": f"LMS returned HTTP {exc.code} during health probe.",
                }
        except (socket.timeout, TimeoutError, urllib.error.URLError) as exc:
            reason = getattr(exc, "reason", None) or str(exc)
            return {
                "status": "unreachable",
                "http_status": None,
                "latency_ms": None,
                "detail": f"Network error or timeout reaching LMS: {reason}",
            }
        except Exception as exc:
            return {
                "status": "unreachable",
                "http_status": None,
                "latency_ms": None,
                "detail": f"Unexpected error probing LMS: {exc}",
            }

    def _send_request(
        self,
        endpoint: str,
        payload: dict[str, Any],
        operation_label: str = "request",
    ) -> dict[str, Any]:
        """Executes JSON POST to LMS endpoint with M2M Authorization header."""
        target_url = f"{self.base_url}{endpoint}"

        try:
            body_bytes = json.dumps(payload).encode("utf-8")
        except (TypeError, ValueError) as exc:
            raise LmsConnectorPermanentError(
                message=f"Failed to serialize payload for {operation_label}.",
                failure_code="INVALID_SCHEMA",
                detail=str(exc),
            ) from exc

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": f"Bearer {self._secret}",
        }
        correlation_id = get_correlation_id()
        if correlation_id:
            headers["X-Request-ID"] = correlation_id

        req = urllib.request.Request(target_url, data=body_bytes, headers=headers, method="POST")

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                resp_bytes = resp.read()
                raw_text = resp_bytes.decode("utf-8", errors="ignore")
                try:
                    data = json.loads(raw_text) if raw_text else {}
                except json.JSONDecodeError as exc:
                    raise LmsConnectorPermanentError(
                        message=f"LMS returned non-JSON response for {operation_label}.",
                        failure_code="INVALID_SCHEMA",
                        status_code=resp.status,
                        detail="Failed to parse JSON response.",
                    ) from exc

                return data

        except urllib.error.HTTPError as exc:
            err_bytes = exc.read()
            err_text = err_bytes.decode("utf-8", errors="ignore")
            parsed_err: dict[str, Any] = {}
            if err_text:
                try:
                    parsed_err = json.loads(err_text)
                except Exception:
                    parsed_err = {"detail": err_text[:200]}

            detail_msg = parsed_err.get("detail") or parsed_err.get("error") or str(exc)

            # Classify HTTP Error status codes
            if exc.code in (401, 403):
                raise LmsConnectorPermanentError(
                    message=f"M2M authentication failed for {operation_label}: {detail_msg}",
                    failure_code="AUTHENTICATION_FAILED",
                    status_code=exc.code,
                    detail=detail_msg,
                ) from exc
            elif exc.code == 404:
                raise LmsConnectorPermanentError(
                    message=f"Resource not found in LMS during {operation_label}: {detail_msg}",
                    failure_code="TENANT_NOT_FOUND",
                    status_code=404,
                    detail=detail_msg,
                ) from exc
            elif exc.code == 409:
                raise LmsConnectorPermanentError(
                    message=f"Mapping conflict in LMS during {operation_label}: {detail_msg}",
                    failure_code="MAPPING_CONFLICT",
                    status_code=409,
                    detail=detail_msg,
                ) from exc
            elif exc.code == 400:
                raise LmsConnectorPermanentError(
                    message=f"Validation error in LMS during {operation_label}: {detail_msg}",
                    failure_code="VALIDATION_ERROR",
                    status_code=400,
                    detail=detail_msg,
                ) from exc
            elif 400 <= exc.code < 500:
                raise LmsConnectorPermanentError(
                    message=f"Client error from LMS during {operation_label}: {detail_msg}",
                    failure_code="VALIDATION_ERROR",
                    status_code=exc.code,
                    detail=detail_msg,
                ) from exc
            elif exc.code in (502, 503, 504):
                raise LmsConnectorRetryableError(
                    message=f"LMS service unavailable ({exc.code}) during {operation_label}: {detail_msg}",
                    failure_code="TEMPORARY_UNAVAILABLE",
                    status_code=exc.code,
                    detail=detail_msg,
                ) from exc
            else:
                raise LmsConnectorRetryableError(
                    message=f"LMS internal server error ({exc.code}) during {operation_label}: {detail_msg}",
                    failure_code="SERVICE_UNAVAILABLE",
                    status_code=exc.code,
                    detail=detail_msg,
                ) from exc

        except (socket.timeout, TimeoutError) as exc:
            raise LmsConnectorRetryableError(
                message=f"Timeout communicating with LMS during {operation_label}.",
                failure_code="UPSTREAM_TIMEOUT",
                detail=str(exc),
            ) from exc

        except urllib.error.URLError as exc:
            reason = getattr(exc, "reason", None)
            if isinstance(reason, socket.timeout):
                raise LmsConnectorRetryableError(
                    message=f"Timeout communicating with LMS during {operation_label}.",
                    failure_code="UPSTREAM_TIMEOUT",
                    detail=str(reason),
                ) from exc

            raise LmsConnectorRetryableError(
                message=f"Network error communicating with LMS during {operation_label}.",
                failure_code="NETWORK_ERROR",
                detail=str(reason or exc),
            ) from exc

        except Exception as exc:
            logger.exception("Unexpected error in LMS connector client.")
            raise LmsConnectorRetryableError(
                message=f"Unexpected error communicating with LMS during {operation_label}: {str(exc)}",
                failure_code="SERVICE_UNAVAILABLE",
                detail=str(exc),
            ) from exc
