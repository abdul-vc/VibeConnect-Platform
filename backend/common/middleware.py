"""Security and Observability middleware for VibeConnect.

Includes:
- RequestCorrelationMiddleware: Inbound/outbound X-Request-ID management and contextvar binding (Phase 7D).
- ContentSecurityPolicyMiddleware: Compatible Content-Security-Policy headers (Phase 6F-4).
"""

import os
from django.http import HttpRequest, HttpResponse

from common.correlation import (
    generate_correlation_id,
    is_valid_correlation_id,
    reset_correlation_id,
    set_correlation_id,
)


class RequestCorrelationMiddleware:
    """Manages request correlation IDs across the HTTP request lifecycle.

    1. Validates incoming X-Request-ID header against strict policy (alphanumeric, hyphens, underscores, 1-64 chars).
    2. Generates a new unique UUID hex if missing or invalid.
    3. Sets request.correlation_id and binds it to contextvars for structured logging and outbound HTTP client propagation.
    4. Attaches X-Request-ID to the outgoing response.
    5. Cleans up contextvar in a finally block to prevent leakage across requests or worker threads.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        incoming_id = request.headers.get("X-Request-ID") or request.META.get("HTTP_X_REQUEST_ID")
        if incoming_id and is_valid_correlation_id(incoming_id):
            correlation_id = incoming_id.strip()
        else:
            correlation_id = generate_correlation_id()

        request.correlation_id = correlation_id
        token = set_correlation_id(correlation_id)
        try:
            response = self.get_response(request)
            response["X-Request-ID"] = correlation_id
            return response
        finally:
            reset_correlation_id(token)


class ContentSecurityPolicyMiddleware:
    """Attaches a minimal, compatible Content-Security-Policy header to HTTP responses.

    Supports existing frontend asset conventions (Google Fonts, inline SVGs, self-hosted bundles).
    Can be customized via DJANGO_CSP_HEADER environment variable if provided.
    """

    def __init__(self, get_response):
        self.get_response = get_response
        custom_csp = os.environ.get("DJANGO_CSP_HEADER", "").strip()
        if custom_csp:
            self.csp_header = custom_csp
        else:
            self.csp_header = (
                "default-src 'self'; "
                "script-src 'self'; "
                "style-src 'self' 'unsafe-inline'; "
                "font-src 'self' data:; "
                "img-src 'self' data: https:; "
                "connect-src 'self'; "
                "frame-src 'self' http://localhost:8000 http://127.0.0.1:8000 http://localhost:8080 http://127.0.0.1:8080 http://localhost:8081 http://127.0.0.1:8081 http://localhost:5173 http://127.0.0.1:5173 http://localhost:6395 http://127.0.0.1:6395 https://hrms.vibesandbox.live https://*.vibesandbox.live https://excelreports.vibecopilot.ai https://quiz.digielvestech.in https://*.digielvestech.in; "
                "frame-ancestors 'none'; "
                "object-src 'none'; "
                "base-uri 'self';"
            )

    def __call__(self, request: HttpRequest) -> HttpResponse:
        response = self.get_response(request)
        if "Content-Security-Policy" not in response:
            response["Content-Security-Policy"] = self.csp_header
        if "Permissions-Policy" not in response:
            response["Permissions-Policy"] = (
                "accelerometer=(), camera=(), geolocation=(), gyroscope=(), "
                "magnetometer=(), microphone=(), payment=(), usb=()"
            )
        return response
