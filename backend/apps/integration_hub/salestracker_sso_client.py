"""Sales Tracker SSO Client (VibeConnect Integration).

Provides a dedicated, strictly isolated, server-to-server HTTP client for communicating
with the Sales Tracker launch-grant endpoint.
Zero hardcoding: base URL, frontend host, and credentials resolve exclusively from Django settings/environment.
Never logs or leaks credentials, launch codes, or callback URLs.
Exclusively handles backend-to-Sales-Tracker launch-grant communication.
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
DEFAULT_SALESTRACKER_FRONTEND_HOST = "localhost:5173"
SALESTRACKER_SSO_CALLBACK_PATH = "/sso/callback"
DEFAULT_TARGET_ROUTE = "/dashboard"


class SalesTrackerSsoError(Exception):
    """Base exception for Sales Tracker SSO communication and validation failures."""

    def __init__(self, message: str, status_code: Optional[int] = None, detail: str = "") -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.detail = detail


class SalesTrackerSsoAuthError(SalesTrackerSsoError):
    """Raised when M2M authentication to Sales Tracker fails (HTTP 401 Unauthorized)."""


class SalesTrackerSsoForbiddenError(SalesTrackerSsoError):
    """Raised when Sales Tracker denies authorization (HTTP 403 Forbidden)."""


class SalesTrackerSsoNotFoundError(SalesTrackerSsoError):
    """Raised when designated Super Administrator account is not found (HTTP 404 Not Found)."""


class SalesTrackerSsoConflictError(SalesTrackerSsoError):
    """Raised when Sales Tracker returns an account or state conflict (HTTP 409 Conflict)."""


class SalesTrackerSsoConnectionError(SalesTrackerSsoError):
    """Raised on network failure, socket timeout, or unreachable Sales Tracker server."""


class SalesTrackerSsoConfigurationError(SalesTrackerSsoError):
    """Raised when required Sales Tracker SSO configuration settings are missing."""


class NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Disallows following HTTP redirects to prevent redirection attacks."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise SalesTrackerSsoError(
            f"Sales Tracker launch-grant endpoint returned unexpected HTTP redirect ({code}).",
            status_code=code,
        )


def is_salestracker_sso_configured() -> bool:
    """Returns True if the dedicated Sales Tracker M2M secret is configured and non-empty."""
    secret = getattr(settings, "SALESTRACKER_SHOWCASE_M2M_SECRET", "")
    return bool(secret and secret.strip())


def get_salestracker_api_base_url() -> str:
    """Resolves the Sales Tracker backend API host from settings."""
    url = getattr(settings, "SALESTRACKER_SHOWCASE_API_BASE_URL", "")
    clean_url = (url or "").strip().rstrip("/")
    if not clean_url:
        raise SalesTrackerSsoConfigurationError(
            "Sales Tracker API base URL is not configured. Please set SALESTRACKER_SHOWCASE_API_BASE_URL."
        )
    return clean_url


def get_salestracker_frontend_url() -> str:
    """Resolves the Sales Tracker frontend base URL from settings."""
    url = getattr(settings, "SALESTRACKER_SHOWCASE_FRONTEND_URL", "")
    return (url or "").strip().rstrip("/")


def get_salestracker_superadmin_employee_id() -> str:
    """Resolves the configured Super Administrator employee ID."""
    emp_id = getattr(settings, "SALESTRACKER_SHOWCASE_SUPERADMIN_EMPLOYEE_ID", "9930663966")
    return (emp_id or "9930663966").strip()


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


def validate_salestracker_callback_url(callback_url: str) -> None:
    """Validates that the returned callback URL matches allowed scheme and configured frontend host.

    Raises:
        SalesTrackerSsoError: if callback URL fails any validation rule.
    """
    if not callback_url or not isinstance(callback_url, str):
        raise SalesTrackerSsoError("Sales Tracker launch grant returned an empty or malformed callback URL.")

    parsed = urllib.parse.urlparse(callback_url)

    if parsed.scheme.lower() not in ("http", "https"):
        raise SalesTrackerSsoError("Sales Tracker launch callback URL must use HTTP or HTTPS scheme.")

    is_local = (
        parsed.hostname in ("localhost", "127.0.0.1")
        or getattr(settings, "DEBUG", False)
        or getattr(settings, "ENVIRONMENT", "") in ("development", "local", "demo", "test")
    )
    if not is_local and parsed.scheme.lower() != "https":
        raise SalesTrackerSsoError("Sales Tracker launch callback URL must use HTTPS in production environments.")

    configured_frontend = get_salestracker_frontend_url()
    expected_host = (
        urllib.parse.urlparse(configured_frontend).netloc.lower()
        if configured_frontend
        else DEFAULT_SALESTRACKER_FRONTEND_HOST
    )

    actual_host = parsed.netloc.lower()
    if actual_host != expected_host and actual_host != DEFAULT_SALESTRACKER_FRONTEND_HOST:
        raise SalesTrackerSsoError(
            f"Sales Tracker callback URL host '{actual_host}' does not match expected host '{expected_host}'."
        )

    path = parsed.path.rstrip("/").lower()
    if not path.endswith(SALESTRACKER_SSO_CALLBACK_PATH) and not path.endswith("/callback"):
        raise SalesTrackerSsoError(
            f"Sales Tracker callback URL path '{parsed.path}' does not match expected callback path '{SALESTRACKER_SSO_CALLBACK_PATH}'."
        )

    if not parsed.query:
        raise SalesTrackerSsoError("Sales Tracker callback URL missing required launch authorization parameters.")

    query_params = urllib.parse.parse_qs(parsed.query)
    code_values = query_params.get("code") or query_params.get("grant")
    if not code_values or not code_values[0].strip():
        raise SalesTrackerSsoError("Sales Tracker callback URL missing required non-empty 'code' parameter.")


def request_salestracker_launch_grant(
    *,
    employee_id: str = "",
    context: str = "showcase",
    target_route: str = DEFAULT_TARGET_ROUTE,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Calls Sales Tracker launch-grant endpoint server-to-server.

    Endpoint: POST /api/v1/sso/launch-grant/
    Headers:
      - X-VibeConnect-Secret: <SALESTRACKER_SHOWCASE_M2M_SECRET>
      - Authorization: Bearer <SALESTRACKER_SHOWCASE_M2M_SECRET>
    """
    if not is_salestracker_sso_configured():
        raise SalesTrackerSsoConfigurationError(
            "Sales Tracker SSO is not configured: missing SALESTRACKER_SHOWCASE_M2M_SECRET."
        )

    secret = getattr(settings, "SALESTRACKER_SHOWCASE_M2M_SECRET", "").strip()
    base_url = get_salestracker_api_base_url()
    endpoint = f"{base_url}/api/v1/sso/launch-grant/"

    clean_employee_id = (employee_id or get_salestracker_superadmin_employee_id()).strip()
    clean_target_route = (target_route or DEFAULT_TARGET_ROUTE).strip()
    if not clean_target_route.startswith("/"):
        clean_target_route = f"/{clean_target_route}"

    payload: dict[str, Any] = {
        "employee_id": clean_employee_id,
        "context": context,
        "target_route": clean_target_route,
        "target_path": clean_target_route,
    }

    body_bytes = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        endpoint,
        data=body_bytes,
        headers={
            "X-VibeConnect-Secret": secret,
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
            logger.warning("Sales Tracker launch-grant unauthorized (HTTP 401).")
            raise SalesTrackerSsoAuthError(
                "Sales Tracker launch-grant M2M authentication failed.",
                status_code=401,
                detail=str(err_detail),
            )

        if status_code == 403:
            logger.warning("Sales Tracker launch-grant forbidden (HTTP 403).")
            raise SalesTrackerSsoForbiddenError(
                f"Sales Tracker launch-grant authorization denied: {err_detail}",
                status_code=403,
                detail=str(err_detail),
            )

        if status_code == 404:
            logger.warning("Sales Tracker Super Administrator account not found (HTTP 404).")
            raise SalesTrackerSsoNotFoundError(
                f"Sales Tracker Super Administrator account not found: {err_detail}",
                status_code=404,
                detail=str(err_detail),
            )

        if status_code == 409:
            logger.warning("Sales Tracker launch-grant conflict (HTTP 409).")
            raise SalesTrackerSsoConflictError(
                f"Sales Tracker launch-grant conflict: {err_detail}",
                status_code=409,
                detail=str(err_detail),
            )

        logger.warning("Sales Tracker launch-grant failed with HTTP %d.", status_code)
        raise SalesTrackerSsoError(
            f"Sales Tracker launch-grant failed with HTTP {status_code}: {err_detail}",
            status_code=status_code,
            detail=str(err_detail),
        )
    except urllib.error.URLError as exc:
        logger.warning("Sales Tracker launch-grant network/connection error.")
        raise SalesTrackerSsoConnectionError(f"Failed to connect to Sales Tracker service: {exc.reason}")
    except json.JSONDecodeError:
        logger.warning("Sales Tracker launch-grant returned non-JSON response.")
        raise SalesTrackerSsoError("Sales Tracker launch-grant returned a malformed non-JSON response.")

    callback_url = data.get("callback_url")
    if not callback_url or not isinstance(callback_url, str):
        raise SalesTrackerSsoError("Sales Tracker launch-grant response did not include a valid 'callback_url'.")

    validate_salestracker_callback_url(callback_url)

    expires_in = data.get("expires_in", 60)
    try:
        expires_in = int(expires_in)
    except (ValueError, TypeError):
        expires_in = 60

    return {
        "callback_url": callback_url,
        "expires_in": expires_in,
        "context": data.get("context", context),
        "employee_id": clean_employee_id,
        "raw_response": data,
    }
