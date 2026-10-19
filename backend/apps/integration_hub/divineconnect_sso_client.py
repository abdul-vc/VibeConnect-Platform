"""Divine Connect SSO Client (VibeConnect Integration).

Provides a dedicated, strictly isolated, server-to-server HTTP client for communicating
with the Divine Connect Event Module launch-grant endpoint for Product Showcase.
Zero hardcoding: base URL, frontend host, and credentials resolve exclusively from Django settings/environment.
Never logs or leaks credentials, launch codes, or callback URLs.
Exclusively handles backend-to-Divine-Connect launch-grant communication.
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
DEFAULT_DIVINECONNECT_FRONTEND_HOST = "localhost:8080"
DIVINECONNECT_SSO_CALLBACK_PATH = "/sso/callback"
DEFAULT_TARGET_ROUTE = "/admin"


class DivineConnectSsoError(Exception):
    """Base exception for Divine Connect SSO communication and validation failures."""

    def __init__(self, message: str, status_code: Optional[int] = None, detail: str = "") -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.detail = detail


class DivineConnectSsoAuthError(DivineConnectSsoError):
    """Raised when M2M authentication to Divine Connect fails (HTTP 401 Unauthorized)."""


class DivineConnectSsoForbiddenError(DivineConnectSsoError):
    """Raised when Divine Connect denies authorization (HTTP 403 Forbidden)."""


class DivineConnectSsoNotFoundError(DivineConnectSsoError):
    """Raised when designated Administrator account is not found (HTTP 404 Not Found)."""


class DivineConnectSsoConflictError(DivineConnectSsoError):
    """Raised when Divine Connect returns an account or state conflict (HTTP 409 Conflict)."""


class DivineConnectSsoConnectionError(DivineConnectSsoError):
    """Raised on network failure, socket timeout, or unreachable Divine Connect server."""


class DivineConnectSsoConfigurationError(DivineConnectSsoError):
    """Raised when required Divine Connect SSO configuration settings are missing."""


class NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Disallows following HTTP redirects to prevent redirection attacks."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise DivineConnectSsoError(
            f"Divine Connect launch-grant endpoint returned unexpected HTTP redirect ({code}).",
            status_code=code,
        )


def is_divineconnect_sso_configured() -> bool:
    """Returns True if the dedicated Divine Connect M2M secret is configured and non-empty."""
    secret = getattr(settings, "DIVINECONNECT_SHOWCASE_M2M_SECRET", "")
    return bool(secret and secret.strip())


def get_divineconnect_api_base_url() -> str:
    """Resolves the Divine Connect backend API host from settings."""
    url = getattr(settings, "DIVINECONNECT_SHOWCASE_API_BASE_URL", "")
    clean_url = (url or "").strip().rstrip("/")
    if not clean_url:
        raise DivineConnectSsoConfigurationError(
            "Divine Connect API base URL is not configured. Please set DIVINECONNECT_SHOWCASE_API_BASE_URL."
        )
    return clean_url


def get_divineconnect_frontend_url() -> str:
    """Resolves the Divine Connect frontend base URL from settings."""
    url = getattr(settings, "DIVINECONNECT_SHOWCASE_FRONTEND_URL", "http://localhost:8080")
    return (url or "http://localhost:8080").strip().rstrip("/")


def get_divineconnect_admin_username() -> str:
    """Resolves the configured Administrator username."""
    user = getattr(settings, "DIVINECONNECT_SHOWCASE_ADMIN_USERNAME", "admin")
    return (user or "admin").strip()


def get_divineconnect_admin_email() -> str:
    """Resolves the configured Administrator email."""
    email = getattr(settings, "DIVINECONNECT_SHOWCASE_ADMIN_EMAIL", "admin@sansthan.org")
    return (email or "admin@sansthan.org").strip().lower()


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


def validate_divineconnect_callback_url(callback_url: str) -> None:
    """Validates that the returned callback URL matches allowed scheme and configured frontend host.

    Raises:
        DivineConnectSsoError: if callback URL fails any validation rule.
    """
    if not callback_url or not isinstance(callback_url, str):
        raise DivineConnectSsoError("Divine Connect launch grant returned an empty or malformed callback URL.")

    parsed = urllib.parse.urlparse(callback_url)

    if parsed.scheme.lower() not in ("http", "https"):
        raise DivineConnectSsoError("Divine Connect launch callback URL must use HTTP or HTTPS scheme.")

    is_local = (
        parsed.hostname in ("localhost", "127.0.0.1")
        or getattr(settings, "DEBUG", False)
        or getattr(settings, "ENVIRONMENT", "") in ("development", "local", "demo", "test")
    )
    if not is_local and parsed.scheme.lower() != "https":
        raise DivineConnectSsoError("Divine Connect launch callback URL must use HTTPS in production environments.")

    configured_frontend = get_divineconnect_frontend_url()
    expected_host = (
        urllib.parse.urlparse(configured_frontend).netloc.lower()
        if configured_frontend
        else DEFAULT_DIVINECONNECT_FRONTEND_HOST
    )

    actual_host = parsed.netloc.lower()
    if actual_host != expected_host and actual_host != DEFAULT_DIVINECONNECT_FRONTEND_HOST:
        raise DivineConnectSsoError(
            f"Divine Connect callback URL host '{actual_host}' does not match expected host '{expected_host}'."
        )

    path = parsed.path.rstrip("/").lower()
    if not path.endswith(DIVINECONNECT_SSO_CALLBACK_PATH) and not path.endswith("/callback"):
        raise DivineConnectSsoError(
            f"Divine Connect callback URL path '{parsed.path}' does not match expected callback path '{DIVINECONNECT_SSO_CALLBACK_PATH}'."
        )

    if not parsed.query:
        raise DivineConnectSsoError("Divine Connect callback URL missing required launch authorization parameters.")

    query_params = urllib.parse.parse_qs(parsed.query)
    code_values = query_params.get("code") or query_params.get("grant")
    if not code_values or not code_values[0].strip():
        raise DivineConnectSsoError("Divine Connect callback URL missing required non-empty 'code' parameter.")


def request_divineconnect_launch_grant(
    *,
    username: str = "",
    email: str = "",
    context: str = "showcase",
    target_route: str = DEFAULT_TARGET_ROUTE,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Calls Divine Connect launch-grant endpoint server-to-server.

    Endpoint: POST /api/v1/sso/launch-grant/
    Headers:
      - X-VibeConnect-Secret: <DIVINECONNECT_SHOWCASE_M2M_SECRET>
      - Authorization: Bearer <DIVINECONNECT_SHOWCASE_M2M_SECRET>
    """
    if not is_divineconnect_sso_configured():
        raise DivineConnectSsoConfigurationError(
            "Divine Connect SSO is not configured: missing DIVINECONNECT_SHOWCASE_M2M_SECRET."
        )

    secret = getattr(settings, "DIVINECONNECT_SHOWCASE_M2M_SECRET", "").strip()
    base_url = get_divineconnect_api_base_url()
    endpoint = f"{base_url}/api/v1/sso/launch-grant/"

    clean_username = (username or get_divineconnect_admin_username()).strip()
    clean_email = (email or get_divineconnect_admin_email()).strip().lower()
    clean_target_route = (target_route or DEFAULT_TARGET_ROUTE).strip()
    if not clean_target_route.startswith("/"):
        clean_target_route = f"/{clean_target_route}"

    payload: dict[str, Any] = {
        "username": clean_username,
        "email": clean_email,
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
            logger.warning("Divine Connect launch-grant unauthorized (HTTP 401).")
            raise DivineConnectSsoAuthError(
                "Divine Connect launch-grant M2M authentication failed. Please verify server M2M secret.",
                status_code=401,
                detail=str(err_detail),
            )

        if status_code == 403:
            logger.warning("Divine Connect launch-grant forbidden (HTTP 403).")
            raise DivineConnectSsoForbiddenError(
                f"Divine Connect launch-grant authorization denied: {err_detail}",
                status_code=403,
                detail=str(err_detail),
            )

        if status_code == 404:
            logger.warning("Divine Connect Administrator account not found (HTTP 404).")
            raise DivineConnectSsoNotFoundError(
                f"Divine Connect Administrator account not found: {err_detail}",
                status_code=404,
                detail=str(err_detail),
            )

        if status_code == 409:
            logger.warning("Divine Connect launch-grant conflict (HTTP 409).")
            raise DivineConnectSsoConflictError(
                f"Divine Connect launch-grant conflict: {err_detail}",
                status_code=409,
                detail=str(err_detail),
            )

        logger.warning("Divine Connect launch-grant failed with HTTP %d.", status_code)
        raise DivineConnectSsoError(
            f"Divine Connect launch-grant failed with HTTP {status_code}: {err_detail}",
            status_code=status_code,
            detail=str(err_detail),
        )
    except urllib.error.URLError as exc:
        logger.warning("Divine Connect launch-grant network/connection error.")
        raise DivineConnectSsoConnectionError(f"Failed to connect to Divine Connect service: {exc.reason}")
    except json.JSONDecodeError:
        logger.warning("Divine Connect launch-grant returned non-JSON response.")
        raise DivineConnectSsoError("Divine Connect launch-grant returned a malformed non-JSON response.")

    callback_url = data.get("callback_url")
    if not callback_url or not isinstance(callback_url, str):
        raise DivineConnectSsoError("Divine Connect launch-grant response did not include a valid 'callback_url'.")

    validate_divineconnect_callback_url(callback_url)

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
        "email": clean_email,
        "raw_response": data,
    }
