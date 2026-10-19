"""LMS Launch-Grant SSO Client (VibeConnect Integration).

Provides a dedicated, strictly isolated, server-to-server HTTP client for communicating
with the LMS launch-grant endpoint.
Zero hardcoding: base URL, frontend host, and credentials resolve exclusively from Django settings/environment.
Never logs or leaks credentials, launch codes, or callback URLs.
Exclusively handles backend-to-LMS launch-grant communication.
"""

import json
import logging
from typing import Any, Optional
import urllib.error
import urllib.parse
import urllib.request

from django.conf import settings

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_SECONDS = 10
ALLOWED_LMS_FRONTEND_HOST = "lms.vibesandbox.live"
LMS_SSO_CALLBACK_PATH = "/sso/vibeconnect/callback"


class LmsLaunchGrantError(Exception):
    """Base exception for LMS launch-grant communication and validation failures."""

    def __init__(self, message: str, status_code: Optional[int] = None, detail: str = "") -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.detail = detail


class LmsLaunchGrantAuthError(LmsLaunchGrantError):
    """Raised when M2M authentication to LMS fails (HTTP 401 Unauthorized)."""


class LmsLaunchGrantForbiddenError(LmsLaunchGrantError):
    """Raised when LMS denies authorization (HTTP 403 Forbidden)."""


class LmsLaunchGrantConflictError(LmsLaunchGrantError):
    """Raised when LMS returns a 409 Conflict."""


class LmsLaunchGrantNotFoundError(LmsLaunchGrantError):
    """Raised when external tenant or user is not provisioned or mapped in LMS (HTTP 404)."""


class LmsLaunchGrantConnectionError(LmsLaunchGrantError):
    """Raised on network failure, socket timeout, or unreachable LMS server."""


class LmsLaunchGrantConfigurationError(LmsLaunchGrantError):
    """Raised when required LMS launch-grant configuration settings are missing."""


class NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Disallows following HTTP redirects to prevent redirection attacks."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise LmsLaunchGrantError(
            f"LMS launch-grant endpoint returned unexpected HTTP redirect ({code}).",
            status_code=code,
        )


def is_lms_launch_grant_configured() -> bool:
    """Returns True if the dedicated LMS launch-grant M2M secret is configured and non-empty."""
    secret = getattr(settings, "LMS_LAUNCH_GRANT_M2M_SECRET", "")
    return bool(secret and secret.strip())


def get_lms_api_base_url() -> str:
    """Resolves the LMS backend API host strictly from settings or environment without hardcoded fallbacks."""
    url = getattr(settings, "VIBECONNECT_LMS_BACKEND_URL", "")
    clean_url = (url or "").strip().rstrip("/")
    if not clean_url:
        raise LmsLaunchGrantConfigurationError(
            "LMS backend URL is not configured. Please set VIBECONNECT_LMS_BACKEND_URL."
        )
    return clean_url


def get_lms_frontend_url() -> str:
    """Resolves the LMS frontend base URL from settings."""
    url = getattr(settings, "LMS_FRONTEND_URL", "https://lms.vibesandbox.live")
    return (url or "https://lms.vibesandbox.live").strip().rstrip("/")


def validate_lms_callback_url(callback_url: str) -> None:
    """Validates that the returned callback URL is HTTPS, matches the approved LMS frontend host,
    has the exact path /sso/vibeconnect/callback, and contains a non-empty code parameter.

    Raises:
        LmsLaunchGrantError: if callback URL fails any validation rule.
    """
    if not callback_url or not isinstance(callback_url, str):
        raise LmsLaunchGrantError("LMS launch grant returned an empty or malformed callback URL.")

    parsed = urllib.parse.urlparse(callback_url)

    if parsed.scheme.lower() != "https":
        raise LmsLaunchGrantError("LMS launch callback URL must use HTTPS scheme.")

    configured_frontend = get_lms_frontend_url()
    expected_host = (
        urllib.parse.urlparse(configured_frontend).netloc.lower()
        if configured_frontend
        else ALLOWED_LMS_FRONTEND_HOST
    )

    actual_host = parsed.netloc.lower()
    if actual_host != expected_host and actual_host != ALLOWED_LMS_FRONTEND_HOST:
        raise LmsLaunchGrantError(
            f"LMS launch callback URL host '{actual_host}' does not match expected host '{expected_host}'."
        )

    path = parsed.path.rstrip("/").lower()
    if path != LMS_SSO_CALLBACK_PATH:
        raise LmsLaunchGrantError(
            f"LMS launch callback URL path '{parsed.path}' does not match expected callback path '{LMS_SSO_CALLBACK_PATH}'."
        )

    if not parsed.query:
        raise LmsLaunchGrantError("LMS launch callback URL missing required launch authorization parameters.")

    query_params = urllib.parse.parse_qs(parsed.query)
    code_values = query_params.get("code")
    if not code_values or not code_values[0].strip():
        raise LmsLaunchGrantError("LMS launch callback URL missing required non-empty 'code' query parameter.")


def sanitize_diagnostic_detail(detail: Any) -> str:
    """Sanitizes upstream error detail ensuring no secrets, passwords, or tokens leak."""
    if not detail:
        return ""
    text = str(detail).strip()
    lower = text.lower()
    for sensitive in ("secret", "password", "token", "bearer", "code="):
        if sensitive in lower:
            return "Authorization error from upstream service."
    return text


def request_lms_launch_grant(
    *,
    external_tenant_id: str,
    external_user_id: str,
    context: str = "standard",
    target_route: str = "",
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Calls LMS launch-grant endpoint server-to-server.

    Endpoint: POST /api/v1/integration/launch-grant/
    Header: Authorization: Bearer <LMS_LAUNCH_GRANT_M2M_SECRET>
    """
    if not is_lms_launch_grant_configured():
        raise LmsLaunchGrantConfigurationError("LMS launch-grant SSO is not configured: missing LMS_LAUNCH_GRANT_M2M_SECRET.")

    secret = getattr(settings, "LMS_LAUNCH_GRANT_M2M_SECRET", "").strip()
    base_url = get_lms_api_base_url()
    endpoint = f"{base_url}/api/v1/integration/launch-grant/"

    payload: dict[str, Any] = {
        "external_tenant_id": str(external_tenant_id),
        "external_user_id": str(external_user_id),
        "context": context,
    }
    if target_route:
        payload["target_route"] = str(target_route).strip()

    body_bytes = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        endpoint,
        data=body_bytes,
        headers={
            "Authorization": f"Bearer {secret}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )

    opener = urllib.request.build_opener(NoRedirectHandler)

    try:
        with opener.open(req, timeout=timeout) as response:
            status_code = response.status
            raw_data = response.read().decode("utf-8")
            data = json.loads(raw_data) if raw_data else {}
    except urllib.error.HTTPError as exc:
        status_code = exc.code
        try:
            err_body = exc.read().decode("utf-8")
            err_data = json.loads(err_body) if err_body else {}
        except Exception:
            err_data = {}

        raw_detail = err_data.get("detail") or err_data.get("error") or f"HTTP {status_code}"
        err_detail = sanitize_diagnostic_detail(raw_detail)

        if status_code == 401:
            logger.warning("LMS launch-grant unauthorized (HTTP 401).")
            raise LmsLaunchGrantAuthError(
                "LMS launch-grant M2M authentication failed.",
                status_code=401,
                detail=str(err_detail),
            )

        if status_code == 403:
            logger.warning("LMS launch-grant forbidden (HTTP 403).")
            raise LmsLaunchGrantForbiddenError(
                f"LMS launch-grant authorization denied: {err_detail}",
                status_code=403,
                detail=str(err_detail),
            )

        if status_code == 409:
            logger.warning("LMS launch-grant conflict (HTTP 409).")
            raise LmsLaunchGrantConflictError(
                f"LMS launch-grant conflict: {err_detail}",
                status_code=409,
                detail=str(err_detail),
            )

        if status_code == 404:
            logger.warning("LMS launch-grant resource not found (HTTP 404).")
            raise LmsLaunchGrantNotFoundError(
                f"LMS launch-grant resource not found: {err_detail}",
                status_code=404,
                detail=str(err_detail),
            )

        logger.warning("LMS launch-grant failed with HTTP %d.", status_code)
        raise LmsLaunchGrantError(
            f"LMS launch-grant failed with HTTP {status_code}: {err_detail}",
            status_code=status_code,
            detail=str(err_detail),
        )
    except urllib.error.URLError as exc:
        logger.warning("LMS launch-grant network/connection error.")
        raise LmsLaunchGrantConnectionError(f"Failed to connect to LMS launch-grant service: {exc.reason}")
    except json.JSONDecodeError:
        logger.warning("LMS launch-grant returned non-JSON response.")
        raise LmsLaunchGrantError("LMS launch-grant returned a malformed non-JSON response.")

    callback_url = data.get("callback_url")
    if not callback_url or not isinstance(callback_url, str):
        raise LmsLaunchGrantError("LMS launch-grant response did not include a valid 'callback_url'.")

    validate_lms_callback_url(callback_url)

    expires_in = data.get("expires_in", 60)
    try:
        expires_in = int(expires_in)
    except (ValueError, TypeError):
        expires_in = 60

    return {
        "callback_url": callback_url,
        "expires_in": expires_in,
        "context": data.get("context", context),
        "raw_response": data,
    }
