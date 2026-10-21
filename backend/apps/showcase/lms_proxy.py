"""LMS Showcase Live Demo Gateway & Proxy.

Provides a dedicated, zero-friction demonstration gateway that directly opens
the LMS Super Administrator dashboard without exposing a login prompt to showcase users.

Features:
1. Automated Server-to-Server Superadmin JWT token acquisition from upstream LMS.
2. In-memory caching of JWT tokens with automatic proactive refresh.
3. Upstream HTML injection: sets localStorage credentials ('halyard_access', 'halyard_refresh')
   before bundle hydration to bypass the client-side login redirect.
4. Upstream static asset reverse-proxying (/assets/<path>) with appropriate MIME types and caching.
5. Upstream REST API reverse-proxying (/api/<path>) preserving methods, headers, and request bodies.
6. Permissive frame-ancestors headers enabling embedded iframe execution in the showcase hub.
"""

import io
import json
import logging
import mimetypes
import time
from typing import Any
import urllib.error
import urllib.parse
import urllib.request

from django.conf import settings
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt

logger = logging.getLogger(__name__)

LMS_UPSTREAM_BASE = getattr(settings, "LMS_FRONTEND_URL", "https://lms.vibesandbox.live").strip().rstrip("/")
LMS_SUPERADMIN_USER = getattr(settings, "LMS_SHOWCASE_ADMIN_USERNAME", "superadmin").strip()
LMS_SUPERADMIN_PASS = getattr(settings, "LMS_SHOWCASE_ADMIN_PASSWORD", "superadmin123").strip()

# In-memory JWT token cache
_token_cache: dict[str, Any] = {
    "access": None,
    "refresh": None,
    "expires_at": 0,
}

FRAME_CSP = (
    "frame-ancestors 'self' "
    "http://localhost:6392 http://127.0.0.1:6392 "
    "http://localhost:8000 http://127.0.0.1:8000 "
    "http://localhost:5173 http://127.0.0.1:5173;"
)


def get_lms_superadmin_tokens() -> dict[str, str]:
    """Retrieves or refreshes superadmin JWT access and refresh tokens from LMS."""
    now = time.time()
    if _token_cache["access"] and now < _token_cache["expires_at"]:
        return {
            "access": _token_cache["access"],
            "refresh": _token_cache["refresh"],
        }

    login_endpoint = f"{LMS_UPSTREAM_BASE}/api/users/auth/login/"
    payload = json.dumps({
        "username": LMS_SUPERADMIN_USER,
        "password": LMS_SUPERADMIN_PASS,
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
            access = data.get("access", "")
            refresh = data.get("refresh", "")
            _token_cache["access"] = access
            _token_cache["refresh"] = refresh
            # Cache for 45 minutes
            _token_cache["expires_at"] = now + 2700
            return {"access": access, "refresh": refresh}
    except Exception as exc:
        logger.error("Failed to authenticate superadmin against LMS upstream: %s", exc)
        # Return whatever we had cached if any, or empty strings
        return {
            "access": _token_cache.get("access") or "",
            "refresh": _token_cache.get("refresh") or "",
        }


def lms_demo_view(request: HttpRequest, path: str = "") -> HttpResponse:
    """Renders LMS Superadmin Dashboard HTML with pre-injected localStorage credentials."""
    # Determine target path on upstream LMS
    req_path = request.path.strip("/")
    if req_path.startswith("lms-demo"):
        sub = req_path[len("lms-demo"):].strip("/")
        target_path = sub or "super-admin/dashboard"
    elif req_path.startswith("super-admin") or req_path.startswith("org-admin") or req_path.startswith("admin"):
        target_path = req_path
    else:
        target_path = (path or "super-admin/dashboard").lstrip("/")

    if not target_path or target_path in ("login", "login/"):
        target_path = "super-admin/dashboard"

    query_string = request.META.get("QUERY_STRING", "")
    upstream_url = f"{LMS_UPSTREAM_BASE}/{target_path}"
    if query_string:
        upstream_url = f"{upstream_url}?{query_string}"

    tokens = get_lms_superadmin_tokens()
    access_token = tokens.get("access", "")
    refresh_token = tokens.get("refresh", "")

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
        logger.error("Error fetching LMS HTML from upstream: %s", exc)
        return HttpResponse(
            f"<h3>LMS Showcase Gateway: Connection Error</h3><p>{exc}</p>",
            status=502,
        )

    # Inject localStorage initialization script before any module scripts execute
    injection_script = f"""
<script>
(function() {{
  try {{
    var acc = "{access_token}";
    var ref = "{refresh_token}";
    if (acc) {{
      localStorage.setItem("halyard_access", acc);
      sessionStorage.setItem("halyard_access", acc);
    }}
    if (ref) {{
      localStorage.setItem("halyard_refresh", ref);
      sessionStorage.setItem("halyard_refresh", ref);
    }}
    // If opened via /lms-demo/..., rewrite browser URL so TanStack Router matches /super-admin/dashboard
    if (window.location.pathname.startsWith('/lms-demo')) {{
      var realPath = window.location.pathname.replace(/^\\/lms-demo/, '') || '/super-admin/dashboard';
      if (!realPath.startsWith('/')) realPath = '/' + realPath;
      window.history.replaceState(null, '', realPath + window.location.search + window.location.hash);
    }}
  }} catch (e) {{
    console.error("LMS Showcase Session Storage Error:", e);
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


def lms_assets_proxy_view(request: HttpRequest, path: str) -> HttpResponse:
    """Proxies static assets (/assets/<path>) from upstream LMS."""
    clean_path = path.lstrip("/")
    upstream_url = f"{LMS_UPSTREAM_BASE}/assets/{clean_path}" if not clean_path.startswith("..") else f"{LMS_UPSTREAM_BASE}/{clean_path[3:]}"
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
            response["Cache-Control"] = "public, max-age=86400"
            return response
    except urllib.error.HTTPError as err:
        if err.code == 404:
            try:
                from apps.showcase.quiz_proxy import quiz_assets_proxy_view
                return quiz_assets_proxy_view(request, path)
            except Exception:
                pass
        return HttpResponse(err.read(), status=err.code, content_type=err.headers.get("Content-Type", "text/plain"))
    except Exception as exc:
        return HttpResponse(f"Asset proxy error: {exc}", status=502, content_type="text/plain")


@csrf_exempt
def lms_api_proxy_view(request: HttpRequest, path: str) -> HttpResponse:
    """Proxies REST API requests (/api/<path>) directly to upstream LMS."""
    if request.method == "OPTIONS":
        response = HttpResponse(status=204)
        response["Access-Control-Allow-Origin"] = "*"
        response["Access-Control-Allow-Headers"] = "*"
        response["Access-Control-Allow-Methods"] = "GET, POST, PUT, PATCH, DELETE, OPTIONS"
        return response

    query_string = request.META.get("QUERY_STRING", "")
    upstream_url = f"{LMS_UPSTREAM_BASE}/api/{path.lstrip('/')}"
    if query_string:
        upstream_url = f"{upstream_url}?{query_string}"

    headers: dict[str, str] = {
        "User-Agent": request.META.get("HTTP_USER_AGENT", "Mozilla/5.0"),
        "Accept": request.headers.get("Accept", "application/json"),
    }

    if "Content-Type" in request.headers:
        headers["Content-Type"] = request.headers["Content-Type"]

    auth_header = request.headers.get("Authorization")
    if auth_header:
        headers["Authorization"] = auth_header
    else:
        # Fallback to superadmin tokens
        tokens = get_lms_superadmin_tokens()
        if tokens.get("access"):
            headers["Authorization"] = f"Bearer {tokens['access']}"

    body = request.body if request.method in ("POST", "PUT", "PATCH") and request.body else None

    req = urllib.request.Request(
        upstream_url,
        data=body,
        headers=headers,
        method=request.method,
    )

    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            content = resp.read()
            content_type = resp.headers.get("Content-Type", "application/json")
            response = HttpResponse(content, status=resp.status, content_type=content_type)
            response["Access-Control-Allow-Origin"] = "*"
            response["Access-Control-Allow-Headers"] = "*"
            response["Access-Control-Allow-Methods"] = "GET, POST, PUT, PATCH, DELETE, OPTIONS"
            return response
    except urllib.error.HTTPError as err:
        content = err.read()
        content_type = err.headers.get("Content-Type", "application/json")
        response = HttpResponse(content, status=err.code, content_type=content_type)
        response["Access-Control-Allow-Origin"] = "*"
        return response
    except Exception as exc:
        logger.error("LMS API proxy error for %s: %s", upstream_url, exc)
        return JsonResponse({"error": "LMS_PROXY_ERROR", "detail": str(exc)}, status=502)
