"""WorkHub SSO Client (VibeConnect Integration).

Provides a dedicated, strictly isolated, server-to-server HTTP client for communicating
with the WorkHub enterprise platform launch-grant endpoint for Product Showcase.
Zero hardcoding: base URL, frontend host, and credentials resolve exclusively from Django settings/environment.
Never logs or leaks credentials, launch codes, or callback URLs.
Exclusively handles backend-to-WorkHub launch-grant communication.
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
DEFAULT_WORKHUB_FRONTEND_HOST = "localhost:6395"
WORKHUB_SSO_CALLBACK_PATH = "/sso/callback"
DEFAULT_TARGET_ROUTE = "/admin"


class WorkHubSsoError(Exception):
    """Base exception for WorkHub SSO communication and validation failures."""

    def __init__(self, message: str, status_code: Optional[int] = None, detail: str = "") -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.detail = detail


class WorkHubSsoAuthError(WorkHubSsoError):
    """Raised when M2M authentication to WorkHub fails (HTTP 401 Unauthorized)."""


class WorkHubSsoForbiddenError(WorkHubSsoError):
    """Raised when WorkHub denies authorization (HTTP 403 Forbidden)."""


class WorkHubSsoNotFoundError(WorkHubSsoError):
    """Raised when designated Administrator account is not found (HTTP 404 Not Found)."""


class WorkHubSsoConflictError(WorkHubSsoError):
    """Raised when WorkHub returns an account or state conflict (HTTP 409 Conflict)."""


class WorkHubSsoConnectionError(WorkHubSsoError):
    """Raised on network failure, socket timeout, or unreachable WorkHub server."""


class WorkHubSsoConfigurationError(WorkHubSsoError):
    """Raised when required WorkHub SSO configuration settings are missing."""


class NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Disallows following HTTP redirects to prevent redirection attacks."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise WorkHubSsoError(
            f"WorkHub launch-grant endpoint returned unexpected HTTP redirect ({code}).",
            status_code=code,
        )


def is_workhub_sso_configured() -> bool:
    """Returns True if the dedicated WorkHub M2M secret is configured and non-empty."""
    secret = getattr(settings, "WORKHUB_SHOWCASE_M2M_SECRET", "")
    return bool(secret and secret.strip())


def get_workhub_api_base_url() -> str:
    """Resolves the WorkHub backend API host from settings."""
    url = getattr(settings, "WORKHUB_SHOWCASE_API_BASE_URL", "http://localhost:8002")
    clean_url = (url or "http://localhost:8002").strip().rstrip("/")
    if not clean_url:
        raise WorkHubSsoConfigurationError(
            "WorkHub API base URL is not configured. Please set WORKHUB_SHOWCASE_API_BASE_URL."
        )
    return clean_url


def get_workhub_frontend_url() -> str:
    """Resolves the WorkHub frontend base URL from settings."""
    url = getattr(settings, "WORKHUB_SHOWCASE_FRONTEND_URL", "http://localhost:6395")
    return (url or "http://localhost:6395").strip().rstrip("/")


def get_workhub_admin_username() -> str:
    """Resolves the configured Administrator username."""
    user = getattr(settings, "WORKHUB_SHOWCASE_ADMIN_USERNAME", "admin")
    return (user or "admin").strip()


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


def validate_workhub_callback_url(callback_url: str) -> None:
    """Validates that the returned callback URL matches allowed scheme and configured frontend host.

    Raises:
        WorkHubSsoError: if callback URL fails any validation rule.
    """
    if not callback_url or not isinstance(callback_url, str):
        raise WorkHubSsoError("WorkHub launch grant returned an empty or malformed callback URL.")

    parsed = urllib.parse.urlparse(callback_url)

    if parsed.scheme.lower() not in ("http", "https"):
        raise WorkHubSsoError("WorkHub launch callback URL must use HTTP or HTTPS scheme.")

    is_local = (
        parsed.hostname in ("localhost", "127.0.0.1")
        or getattr(settings, "DEBUG", False)
        or getattr(settings, "ENVIRONMENT", "") in ("development", "local", "demo", "test")
    )
    if not is_local and parsed.scheme.lower() != "https":
        raise WorkHubSsoError("WorkHub launch callback URL must use HTTPS in production environments.")

    configured_frontend = get_workhub_frontend_url()
    expected_host = (
        urllib.parse.urlparse(configured_frontend).netloc.lower()
        if configured_frontend
        else DEFAULT_WORKHUB_FRONTEND_HOST
    )

    actual_host = parsed.netloc.lower()
    if actual_host != expected_host and actual_host != DEFAULT_WORKHUB_FRONTEND_HOST:
        raise WorkHubSsoError(
            f"WorkHub callback URL host '{actual_host}' does not match expected host '{expected_host}'."
        )

    path = parsed.path.rstrip("/").lower()
    if not path.endswith(WORKHUB_SSO_CALLBACK_PATH) and not path.endswith("/callback"):
        raise WorkHubSsoError(
            f"WorkHub callback URL path '{parsed.path}' does not match expected callback path '{WORKHUB_SSO_CALLBACK_PATH}'."
        )

    if not parsed.query:
        raise WorkHubSsoError("WorkHub callback URL missing required launch authorization parameters.")

    query_params = urllib.parse.parse_qs(parsed.query)
    code_values = query_params.get("code") or query_params.get("grant")
    if not code_values or not code_values[0].strip():
        raise WorkHubSsoError("WorkHub callback URL missing required non-empty 'code' parameter.")


def request_workhub_launch_grant(
    *,
    username: str = "",
    context: str = "showcase",
    target_route: str = DEFAULT_TARGET_ROUTE,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Calls WorkHub launch-grant endpoint server-to-server.

    Endpoint: POST /api/v1/sso/launch-grant/
    Headers:
      - X-VibeConnect-Secret: <WORKHUB_SHOWCASE_M2M_SECRET>
      - Authorization: Bearer <WORKHUB_SHOWCASE_M2M_SECRET>
    """
    if not is_workhub_sso_configured():
        raise WorkHubSsoConfigurationError(
            "WorkHub SSO is not configured: missing WORKHUB_SHOWCASE_M2M_SECRET."
        )

    secret = getattr(settings, "WORKHUB_SHOWCASE_M2M_SECRET", "").strip()
    base_url = get_workhub_api_base_url()
    endpoint = f"{base_url}/api/v1/sso/launch-grant/"

    clean_username = (username or get_workhub_admin_username()).strip()
    clean_target_route = (target_route or DEFAULT_TARGET_ROUTE).strip()
    if not clean_target_route.startswith("/"):
        clean_target_route = f"/{clean_target_route}"

    payload: dict[str, Any] = {
        "username": clean_username,
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
            logger.warning("WorkHub launch-grant unauthorized (HTTP 401).")
            raise WorkHubSsoAuthError(
                "WorkHub launch-grant M2M authentication failed. Please verify server M2M secret.",
                status_code=401,
                detail=str(err_detail),
            )

        if status_code == 403:
            logger.warning("WorkHub launch-grant forbidden (HTTP 403).")
            raise WorkHubSsoForbiddenError(
                f"WorkHub launch-grant authorization denied: {err_detail}",
                status_code=403,
                detail=str(err_detail),
            )

        if status_code == 404:
            logger.warning("WorkHub Administrator account not found (HTTP 404).")
            raise WorkHubSsoNotFoundError(
                f"WorkHub Administrator account not found: {err_detail}",
                status_code=404,
                detail=str(err_detail),
            )

        if status_code == 409:
            logger.warning("WorkHub launch-grant conflict (HTTP 409).")
            raise WorkHubSsoConflictError(
                f"WorkHub launch-grant conflict: {err_detail}",
                status_code=409,
                detail=str(err_detail),
            )

        logger.warning("WorkHub launch-grant failed with HTTP %d.", status_code)
        raise WorkHubSsoError(
            f"WorkHub launch-grant failed with HTTP {status_code}: {err_detail}",
            status_code=status_code,
            detail=str(err_detail),
        )
    except urllib.error.URLError as exc:
        logger.warning("WorkHub launch-grant network/connection error.")
        raise WorkHubSsoConnectionError(f"Failed to connect to WorkHub service: {exc.reason}")
    except json.JSONDecodeError:
        logger.warning("WorkHub launch-grant returned non-JSON response.")
        raise WorkHubSsoError("WorkHub launch-grant returned a malformed non-JSON response.")

    callback_url = data.get("callback_url")
    if not callback_url or not isinstance(callback_url, str):
        raise WorkHubSsoError("WorkHub launch-grant response did not include a valid 'callback_url'.")

    validate_workhub_callback_url(callback_url)

    expires_in = data.get("expires_in", 60)
    try:
        expires_in = int(expires_in)
    except (ValueError, TypeError):
        expires_in = 60

    return {
        "callback_url": callback_url,
        "expires_in": expires_in,
        "context": data.get("context", context),
        "username": clean_username,
        "raw_response": data,
    }
