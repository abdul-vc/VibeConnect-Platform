import math
from django.conf import settings
from rest_framework import exceptions
from rest_framework.throttling import SimpleRateThrottle


class DeveloperApiThrottled(exceptions.Throttled):
    """Custom Throttled exception with frozen error contract format."""

    def __init__(self, wait=None, detail=None, code=None):
        super().__init__(wait=wait, detail=detail, code=code)
        wait_int = math.ceil(wait) if wait else 60
        self.detail = {
            "error": "RATE_LIMIT_EXCEEDED",
            "detail": "API rate limit exceeded.",
            "retry_after": wait_int,
        }


class DeveloperKeyRateThrottle(SimpleRateThrottle):
    """Enforces per-DeveloperApiKey rate limits using Django cache."""

    scope = "developer_api"

    def get_cache_key(self, request, view):
        api_key = getattr(request, "developer_api_key", None)
        if not api_key:
            return None
        return f"throttle_dev_{api_key.key_prefix}"

    def get_rate(self):
        rates = getattr(settings, "REST_FRAMEWORK", {}).get("DEFAULT_THROTTLE_RATES", {})
        rate = rates.get(self.scope)
        if not rate:
            rate = getattr(settings, "DJANGO_DEVELOPER_API_RATE_LIMIT", "120/minute")
        return rate

    def throttle_failure(self):
        """Raises custom throttled exception matching locked error contract."""
        wait = self.wait()
        raise DeveloperApiThrottled(wait=wait)
