"""Quiz Showcase Live Demo Gateway & Proxy.

Provides a dedicated, zero-friction demonstration gateway that directly opens
the Quiz Administrator portal without exposing a login prompt to showcase users.

Features:
1. Automated Server-to-Server Admin authentication against Quiz backend (quizz.digielvestech.in).
2. In-memory caching of JWT token and user profile with proactive refresh.
3. Upstream HTML injection: sets localStorage credentials ('auth_token', 'user')
   before bundle hydration to bypass the client-side login redirect.
4. Upstream static asset reverse-proxying (/assets/<path>, /images/<path>) with MIME detection.
5. Permissive frame-ancestors headers enabling embedded iframe execution in the showcase hub.
"""

import json
import logging
import mimetypes
import time
from typing import Any
import urllib.error
import urllib.parse
import urllib.request

from django.conf import settings
from django.http import HttpRequest, HttpResponse

logger = logging.getLogger(__name__)

QUIZ_FRONTEND_BASE = getattr(settings, "QUIZ_FRONTEND_URL", "https://quiz.digielvestech.in").strip().rstrip("/")
QUIZ_API_BASE = getattr(settings, "QUIZ_API_BASE_URL", "https://quizz.digielvestech.in").strip().rstrip("/")
QUIZ_ADMIN_USER = getattr(settings, "QUIZ_SHOWCASE_ADMIN_USERNAME", "superadmin").strip()
QUIZ_ADMIN_PASS = getattr(settings, "QUIZ_SHOWCASE_ADMIN_PASSWORD", "Admin@1234").strip()

# In-memory JWT token cache
_quiz_token_cache: dict[str, Any] = {
    "token": None,
    "user": None,
    "expires_at": 0,
}

FRAME_CSP = (
    "frame-ancestors 'self' "
    "http://localhost:6392 http://127.0.0.1:6392 "
    "http://localhost:8000 http://127.0.0.1:8000 "
    "http://localhost:5173 http://127.0.0.1:5173;"
)


def get_quiz_admin_credentials() -> dict[str, Any]:
    """Retrieves or refreshes admin JWT token and user profile from Quiz API."""
    now = time.time()
    if _quiz_token_cache["token"] and now < _quiz_token_cache["expires_at"]:
        return {
            "token": _quiz_token_cache["token"],
            "user": _quiz_token_cache["user"],
        }

    login_endpoint = f"{QUIZ_API_BASE}/api/auth/login/"
    payload = json.dumps({
        "identifier": QUIZ_ADMIN_USER,
        "password": QUIZ_ADMIN_PASS,
    }).encode("utf-8")

    req = urllib.request.Request(
        login_endpoint,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "VibeConnect-Showcase-Proxy/1.0",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            token = data.get("access") or data.get("token") or data.get("jwt") or ""
            user = data.get("user") or {
                "id": 1,
                "username": QUIZ_ADMIN_USER,
                "role": "ADMIN",
                "is_staff": True,
                "is_superuser": True,
                "is_admin": True,
            }
            _quiz_token_cache["token"] = token
            _quiz_token_cache["user"] = user
            _quiz_token_cache["expires_at"] = now + 2700  # 45 minutes
            return {"token": token, "user": user}
    except Exception as exc:
        logger.error("Failed to authenticate admin against Quiz upstream: %s", exc)
        return {
            "token": _quiz_token_cache.get("token") or "",
            "user": _quiz_token_cache.get("user") or {"role": "ADMIN", "is_admin": True},
        }


def quiz_demo_view(request: HttpRequest, path: str = "") -> HttpResponse:
    """Renders Quiz Admin Dashboard HTML with pre-injected localStorage credentials."""
    req_path = request.path.strip("/")
    if req_path.startswith("quiz-demo"):
        sub = req_path[len("quiz-demo"):].strip("/")
        target_path = sub or "admin"
    elif req_path.startswith("admin"):
        target_path = req_path
    else:
        target_path = (path or "admin").lstrip("/")

    if not target_path or target_path in ("login", "login/"):
        target_path = "admin"

    query_string = request.META.get("QUERY_STRING", "")
    upstream_url = f"{QUIZ_FRONTEND_BASE}/{target_path}"
    if query_string:
        upstream_url = f"{upstream_url}?{query_string}"

    creds = get_quiz_admin_credentials()
    auth_token = creds.get("token", "")
    user_data = creds.get("user", {"role": "ADMIN", "is_admin": True})

    req = urllib.request.Request(
        upstream_url,
        headers={
            "User-Agent": request.META.get("HTTP_USER_AGENT", "Mozilla/5.0"),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            raw_content = resp.read()
            html = raw_content.decode("utf-8", errors="replace")
    except urllib.error.HTTPError as err:
        html = err.read().decode("utf-8", errors="replace")
    except Exception as exc:
        logger.error("Error fetching Quiz HTML from upstream: %s", exc)
        return HttpResponse(
            f"<h3>Quiz Showcase Gateway: Connection Error</h3><p>{exc}</p>",
            status=502,
        )

    # Injected script initializes localStorage before any module scripts execute
    user_json = json.dumps(user_data)
    injection_script = f"""
<script>
(function() {{
  try {{
    var token = "{auth_token}";
    var userObj = {user_json};
    if (token) {{
      localStorage.setItem("auth_token", token);
      sessionStorage.setItem("auth_token", token);
    }}
    if (userObj) {{
      localStorage.setItem("user", JSON.stringify(userObj));
      sessionStorage.setItem("user", JSON.stringify(userObj));
    }}
    // If opened via /quiz-demo/..., rewrite browser URL so React Router matches /admin
    if (window.location.pathname.startsWith('/quiz-demo')) {{
      var realPath = window.location.pathname.replace(/^\\/quiz-demo/, '') || '/admin';
      if (!realPath.startsWith('/')) realPath = '/' + realPath;
      window.history.replaceState(null, '', realPath + window.location.search + window.location.hash);
    }}
  }} catch (e) {{
    console.error("Quiz Showcase Session Storage Error:", e);
  }}
}})();
</script>
"""

    if "<head>" in html:
        modified_html = html.replace("<head>", f"<head>{injection_script}", 1)
    elif "<body" in html:
        modified_html = html.replace("<body", f"{injection_script}<body", 1)
    else:
        modified_html = f"{injection_script}{html}"

    response = HttpResponse(modified_html, content_type="text/html; charset=utf-8")
    response["Content-Security-Policy"] = FRAME_CSP
    response["X-Frame-Options"] = "ALLOWALL"
    return response


def quiz_assets_proxy_view(request: HttpRequest, path: str) -> HttpResponse:
    """Proxies static assets (/assets/<path> or /images/<path>) from upstream Quiz frontend."""
    clean_path = path.lstrip("/")
    # Determine upstream asset URL
    if request.path.startswith("/images/"):
        upstream_url = f"{QUIZ_FRONTEND_BASE}/images/{clean_path}"
    else:
        upstream_url = f"{QUIZ_FRONTEND_BASE}/assets/{clean_path}"

    req = urllib.request.Request(
        upstream_url,
        headers={"User-Agent": request.META.get("HTTP_USER_AGENT", "Mozilla/5.0")},
    )

    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            content = resp.read()
            content_type = resp.headers.get("Content-Type")
            if not content_type:
                guessed, _ = mimetypes.guess_type(path)
                content_type = guessed or "application/octet-stream"

            response = HttpResponse(content, content_type=content_type, status=resp.status)
            response["Content-Security-Policy"] = FRAME_CSP
            response["X-Frame-Options"] = "ALLOWALL"
            response["Access-Control-Allow-Origin"] = "*"
            response["Cache-Control"] = "public, max-age=86400"
            return response
    except urllib.error.HTTPError as err:
        return HttpResponse(err.read(), status=err.code, content_type=err.headers.get("Content-Type", "text/plain"))
    except Exception as exc:
        return HttpResponse(f"Quiz asset proxy error: {exc}", status=502, content_type="text/plain")
