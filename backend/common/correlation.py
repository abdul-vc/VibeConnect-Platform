"""Request Correlation ID management for VibeConnect (Phase 7D).

Provides context-local tracking of request correlation IDs across the HTTP request lifecycle
and outbound service-to-service calls using Python's standard-library contextvars.
"""

import re
import uuid
from contextvars import ContextVar
from typing import Optional

# Strict policy: 1 to 64 alphanumeric characters, hyphens, or underscores.
CORRELATION_ID_REGEX = re.compile(r"^[A-Za-z0-9_-]{1,64}$")

_correlation_id_ctx: ContextVar[Optional[str]] = ContextVar("correlation_id", default=None)


def is_valid_correlation_id(value: Optional[str]) -> bool:
    """Validates whether a correlation ID meets length and character safety policies."""
    if not value or not isinstance(value, str):
        return False
    return bool(CORRELATION_ID_REGEX.match(value.strip()))


def generate_correlation_id() -> str:
    """Generates a cryptographically random, collision-resistant correlation ID."""
    return uuid.uuid4().hex


def get_correlation_id() -> Optional[str]:
    """Retrieves the active correlation ID from the current execution context."""
    return _correlation_id_ctx.get()


def set_correlation_id(correlation_id: str):
    """Binds a correlation ID to the current context. Returns token for reset."""
    return _correlation_id_ctx.set(correlation_id)


def reset_correlation_id(token) -> None:
    """Resets the contextvar using the token to prevent context leakage across requests/workers."""
    try:
        _correlation_id_ctx.reset(token)
    except Exception:
        _correlation_id_ctx.set(None)
