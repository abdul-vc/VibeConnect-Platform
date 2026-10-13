"""Structured Application Logging for VibeConnect (Phase 7D).

Provides standard-library JSON formatting, request correlation ID inclusion,
and sensitive credential redaction without requiring third-party telemetry dependencies.
"""

from datetime import datetime, timezone
import json
import logging
import re
from typing import Any, Mapping

from common.correlation import get_correlation_id, is_valid_correlation_id

SENSITIVE_KEY_SUBSTRINGS = (
    "password",
    "secret",
    "token",
    "authorization",
    "cookie",
    "session",
    "credential",
    "m2m",
    "private_key",
    "api_key",
)

# Targeted regex patterns for sanitizing sensitive data embedded in messages, URLs, headers, and exceptions
REDACTION_PATTERNS = [
    # Authorization / Bearer tokens: Bearer <token>
    (re.compile(r"(?i)(bearer\s+)[A-Za-z0-9\-._~+/]+=*"), r"\1[REDACTED]"),
    # Basic Auth: Basic <base64>
    (re.compile(r"(?i)(basic\s+)[A-Za-z0-9+/=]+"), r"\1[REDACTED]"),
    # URL query parameters containing sensitive keys (code, token, access_token, refresh_token, client_secret, etc.)
    (
        re.compile(
            r"([?&](?:password|secret|client_secret|m2m_secret|token|access_token|refresh_token|api_key|credential|code|sessionid|csrftoken)=)[^&\s'\"]+",
            re.IGNORECASE,
        ),
        r"\1[REDACTED]",
    ),
    # Key-value / assignment pairs: access_token=..., client_secret=..., etc.
    (
        re.compile(
            r"(?i)\b(password|secret|client_secret|m2m_secret|token|access_token|refresh_token|api_key|credential|sessionid|csrftoken|auth_code)\b\s*([:=])\s*['\"]?([^,\s'\";}\]]+)['\"]?"
        ),
        r"\1\2[REDACTED]",
    ),
    # Cookie headers / strings: sessionid=..., csrftoken=...
    (
        re.compile(r"(?i)\b(sessionid|csrftoken|jwt)\s*=\s*[^;\s]+"),
        r"\1=[REDACTED]",
    ),
]


def sanitize_log_text(text: str) -> str:
    """Sanitizes rendered log messages, exception tracebacks, and URLs against secret leakage."""
    if not text or not isinstance(text, str):
        return text

    sanitized = text
    for pattern, replacement in REDACTION_PATTERNS:
        sanitized = pattern.sub(replacement, sanitized)
    return sanitized


def redact_sensitive_value(key: str, value: Any) -> Any:
    """Recursively redacts sensitive values if the key or string value matches known patterns."""
    key_lower = str(key).lower()
    if any(sub in key_lower for sub in SENSITIVE_KEY_SUBSTRINGS):
        return "[REDACTED]"

    if isinstance(value, Mapping):
        return {k: redact_sensitive_value(k, v) for k, v in value.items()}
    elif isinstance(value, (list, tuple, set)):
        return [redact_sensitive_value(key, item) for item in value]
    elif isinstance(value, str):
        return sanitize_log_text(value)
    return value


class StructuredJsonFormatter(logging.Formatter):
    """Formats LogRecords as structured JSON objects for modern observability platforms."""

    def format(self, record: logging.LogRecord) -> str:
        # 1. Base log fields (message sanitized against sensitive string patterns)
        rendered_message = sanitize_log_text(record.getMessage())

        # Resolve correlation_id with fallback hierarchy:
        # a. Explicitly passed in LogRecord (e.g. record.correlation_id)
        # b. Active ContextVar from current execution thread/task
        # c. Validated correlation_id from record.request (e.g. from django.request log_response)
        req = getattr(record, "request", None)
        req_correlation_id = getattr(req, "correlation_id", None) if req else None

        resolved_correlation_id = (
            getattr(record, "correlation_id", None)
            or get_correlation_id()
            or (req_correlation_id if is_valid_correlation_id(req_correlation_id) else None)
        )

        log_data: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": rendered_message,
            "correlation_id": resolved_correlation_id,
            "module": record.module,
            "funcName": record.funcName,
            "lineno": record.lineno,
        }

        # 2. Format exception if present (traceback sanitized to protect embedded secrets)
        if record.exc_info:
            raw_exc = self.formatException(record.exc_info)
            log_data["exception"] = sanitize_log_text(raw_exc)

        # 3. Include any extra structured fields attached to the LogRecord
        reserved_attrs = {
            "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
            "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
            "created", "msecs", "relativeCreated", "thread", "threadName",
            "processName", "process", "message", "correlation_id", "request", "response",
        }

        extra_fields = {}
        for attr, value in record.__dict__.items():
            if attr not in reserved_attrs and not attr.startswith("_"):
                extra_fields[attr] = redact_sensitive_value(attr, value)

        if extra_fields:
            log_data["extra"] = extra_fields

        try:
            return json.dumps(log_data, default=str)
        except Exception:
            # Fallback safe serialization if an un-serializable object is encountered
            log_data["message"] = str(log_data.get("message", ""))
            return json.dumps(
                {
                    "timestamp": log_data["timestamp"],
                    "level": log_data["level"],
                    "logger": log_data["logger"],
                    "message": log_data["message"],
                    "correlation_id": log_data["correlation_id"],
                }
            )
