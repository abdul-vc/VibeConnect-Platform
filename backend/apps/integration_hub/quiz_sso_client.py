"""Quiz SSO Client (VibeConnect Integration).

Provides a dedicated, strictly isolated, server-to-server HTTP client for communicating
with the Quiz SSO launch-grant endpoint.
Zero hardcoding: base URL and credentials resolve exclusively from Django settings/environment.
Never logs or leaks credentials, launch codes, or callback URLs.
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
ALLOWED_QUIZ_FRONTEND_HOST = "quiz.digielvestech.in"
QUIZ_SSO_CALLBACK_PATH = "/sso/callback"
ALLOWED_TARGET_PATHS = frozenset({"/dashboard", "/quiz", "/admin"})
DEFAULT_TARGET_PATH = "/dashboard"


class QuizSsoError(Exception):
    """Base exception for Quiz SSO communication and validation failures."""

    def __init__(self, message: str, status_code: Optional[int] = None, detail: str = "") -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.detail = detail


class QuizSsoAuthError(QuizSsoError):
    """Raised when M2M authentication to Quiz fails (401 Unauthorized)."""


class QuizSsoConflictError(QuizSsoError):
    """Raised when Quiz returns a 409 Conflict (e.g. account linking conflict)."""


class QuizSsoConnectionError(QuizSsoError):
    """Raised on network failure, socket timeout, or unreachable Quiz server."""


def is_quiz_sso_configured() -> bool:
    """Returns True if the dedicated Quiz M2M secret is configured and non-empty."""
    secret = getattr(settings, "QUIZ_M2M_SECRET", "")
    return bool(secret and secret.strip())


def get_quiz_api_base_url() -> str:
    """Resolves the Quiz backend API host from settings."""
    url = getattr(settings, "QUIZ_API_BASE_URL", "https://quizz.digielvestech.in")
    return (url or "https://quizz.digielvestech.in").strip().rstrip("/")


def get_quiz_frontend_url() -> str:
    """Resolves the Quiz frontend base URL from settings."""
    url = getattr(settings, "QUIZ_FRONTEND_URL", "https://quiz.digielvestech.in")
    return (url or "https://quiz.digielvestech.in").strip().rstrip("/")


def validate_quiz_callback_url(callback_url: str) -> None:
    """Validates that the returned callback URL is HTTPS and points to the allowed Quiz frontend host.

    Raises:
        QuizSsoError: if callback URL fails validation.
    """
    if not callback_url or not isinstance(callback_url, str):
        raise QuizSsoError("Quiz launch grant returned an empty or malformed callback URL.")

    parsed = urllib.parse.urlparse(callback_url)

    if parsed.scheme.lower() != "https":
        raise QuizSsoError("Quiz launch callback URL must use HTTPS scheme.")

    configured_frontend = get_quiz_frontend_url()
    expected_host = (
        urllib.parse.urlparse(configured_frontend).netloc.lower()
        if configured_frontend
        else ALLOWED_QUIZ_FRONTEND_HOST
    )

    actual_host = parsed.netloc.lower()
    if actual_host != expected_host and actual_host != ALLOWED_QUIZ_FRONTEND_HOST:
        raise QuizSsoError(
            f"Quiz launch callback URL host '{actual_host}' does not match expected host '{expected_host}'."
        )

    path = parsed.path.rstrip("/").lower()
    if path != QUIZ_SSO_CALLBACK_PATH and not path.endswith(QUIZ_SSO_CALLBACK_PATH):
        raise QuizSsoError(
            f"Quiz launch callback URL path '{parsed.path}' does not match expected SSO callback path '{QUIZ_SSO_CALLBACK_PATH}'."
        )

    if not parsed.query:
        raise QuizSsoError("Quiz launch callback URL missing required launch authorization parameters.")


def normalize_and_validate_quiz_callback_url(raw_callback_url: str) -> str:
    """Validates the raw callback URL returned by Quiz launch-grant and resolves
    the authoritative HTTPS frontend callback URL, preserving the one-time launch grant.

    Security rules enforced:
    1. Scheme must be HTTPS.
    2. Path must strictly match the allowed Quiz frontend SSO callback path (/sso/callback).
    3. Host must be either the configured frontend host or the configured API host.
       Arbitrary hosts are strictly rejected.
    4. Query parameters must be non-empty and include the one-time code parameter.
    5. The final callback URL uses the authoritative configured Quiz frontend origin.
    """
    if not raw_callback_url or not isinstance(raw_callback_url, str):
        raise QuizSsoError("Quiz launch grant returned an empty or malformed callback URL.")

    parsed = urllib.parse.urlparse(raw_callback_url)

    if parsed.scheme.lower() != "https":
        raise QuizSsoError("Quiz launch callback URL must use HTTPS scheme.")

    path = parsed.path.rstrip("/").lower()
    if path != QUIZ_SSO_CALLBACK_PATH and not path.endswith(QUIZ_SSO_CALLBACK_PATH):
        raise QuizSsoError(
            f"Quiz launch callback URL path '{parsed.path}' does not match expected SSO callback path '{QUIZ_SSO_CALLBACK_PATH}'."
        )

    if not parsed.query:
        raise QuizSsoError("Quiz launch callback URL missing required launch authorization parameters.")

    query_params = urllib.parse.parse_qs(parsed.query)
    code_val = query_params.get("code") or query_params.get("grant")
    if not code_val or not code_val[0].strip():
        raise QuizSsoError("Quiz launch callback URL missing required non-empty 'code' parameter.")

    configured_frontend = get_quiz_frontend_url()
    expected_frontend_host = (
        urllib.parse.urlparse(configured_frontend).netloc.lower()
        if configured_frontend
        else ALLOWED_QUIZ_FRONTEND_HOST
    )
    api_base = get_quiz_api_base_url()
    expected_api_host = urllib.parse.urlparse(api_base).netloc.lower() if api_base else ""

    actual_host = parsed.netloc.lower()
    allowed_hosts = {expected_frontend_host, ALLOWED_QUIZ_FRONTEND_HOST}
    if expected_api_host:
        allowed_hosts.add(expected_api_host)

    if actual_host not in allowed_hosts:
        raise QuizSsoError(
            f"Quiz launch callback URL host '{actual_host}' does not match expected host '{expected_frontend_host}'."
        )

    # When the callback is intended for the Quiz frontend, map to the authoritative
    # configured Quiz frontend origin while preserving the returned one-time grant securely.
    frontend_origin = configured_frontend or f"https://{ALLOWED_QUIZ_FRONTEND_HOST}"
    frontend_parsed = urllib.parse.urlparse(frontend_origin)
    canonical_url = urllib.parse.urlunparse((
        frontend_parsed.scheme or "https",
        frontend_parsed.netloc or expected_frontend_host,
        parsed.path,
        parsed.params,
        parsed.query,
        parsed.fragment,
    ))

    validate_quiz_callback_url(canonical_url)
    return canonical_url


def request_quiz_launch_grant(
    *,
    user_id: str,
    tenant_id: str,
    email: str = "",
    first_name: str = "",
    last_name: str = "",
    phone: str = "",
    context: str = "standard",
    target_path: str = DEFAULT_TARGET_PATH,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Calls Quiz launch-grant endpoint server-to-server.

    Endpoint: POST /api/auth/sso/vibeconnect/launch-grant/
    Header: X-VibeConnect-Secret: <QUIZ_M2M_SECRET>
    """
    if not is_quiz_sso_configured():
        raise QuizSsoError("Quiz SSO is not configured: missing QUIZ_M2M_SECRET.")

    secret = getattr(settings, "QUIZ_M2M_SECRET", "").strip()
    base_url = get_quiz_api_base_url()
    endpoint = f"{base_url}/api/auth/sso/vibeconnect/launch-grant/"

    # Sanitize target path: enforce allowed paths and prevent privilege elevation to /admin in standard tenant context
    clean_target_path = (target_path or DEFAULT_TARGET_PATH).strip()
    if clean_target_path not in ALLOWED_TARGET_PATHS:
        clean_target_path = DEFAULT_TARGET_PATH
    if clean_target_path == "/admin" and context != "showcase":
        clean_target_path = DEFAULT_TARGET_PATH

    payload: dict[str, Any] = {
        "vibeconnect_user_id": str(user_id),
        "tenant_id": str(tenant_id),
        "context": context,
        "target_path": clean_target_path,
    }
    if email:
        payload["email"] = email
    if first_name:
        payload["first_name"] = first_name
    if last_name:
        payload["last_name"] = last_name
    if phone:
        payload["phone"] = phone

    body_bytes = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        endpoint,
        data=body_bytes,
        headers={
            "X-VibeConnect-Secret": secret,
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
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

        err_detail = err_data.get("detail") or err_data.get("error") or f"HTTP {status_code}"

        if status_code == 401:
            logger.warning("Quiz SSO launch-grant unauthorized (401).")
            raise QuizSsoAuthError("Quiz SSO M2M authentication failed.", status_code=401, detail=str(err_detail))

        if status_code == 409:
            logger.warning("Quiz SSO launch-grant account conflict (409).")
            raise QuizSsoConflictError(
                f"Quiz account linking conflict: {err_detail}", status_code=409, detail=str(err_detail)
            )

        logger.warning("Quiz SSO launch-grant failed with HTTP %d.", status_code)
        raise QuizSsoError(
            f"Quiz SSO launch grant failed with HTTP {status_code}: {err_detail}",
            status_code=status_code,
            detail=str(err_detail),
        )
    except urllib.error.URLError as exc:
        logger.warning("Quiz SSO launch-grant network/connection error.")
        raise QuizSsoConnectionError(f"Failed to connect to Quiz SSO service: {exc.reason}")
    except json.JSONDecodeError as exc:
        logger.warning("Quiz SSO launch-grant returned non-JSON response.")
        raise QuizSsoError("Quiz SSO launch-grant returned a malformed non-JSON response.")

    raw_callback_url = data.get("callback_url")
    if not raw_callback_url:
        raise QuizSsoError("Quiz launch grant response did not include a 'callback_url'.")

    callback_url = normalize_and_validate_quiz_callback_url(raw_callback_url)

    return {
        "callback_url": callback_url,
        "raw_response": data,
    }
