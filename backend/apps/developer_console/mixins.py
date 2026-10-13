import time
from rest_framework.response import Response


class DeveloperApiViewMixin:
    """Base mixin for developer endpoints injecting standard rate-limit headers."""

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        if isinstance(response, Response):
            throttles = getattr(self, "get_throttles", None)
            if throttles:
                for throttle in self.get_throttles():
                    num_requests = getattr(throttle, "num_requests", None)
                    if num_requests:
                        history = getattr(throttle, "history", [])
                        remaining = max(0, num_requests - len(history))
                        duration = getattr(throttle, "duration", 60) or 60
                        response["X-RateLimit-Limit"] = str(num_requests)
                        response["X-RateLimit-Remaining"] = str(remaining)
                        response["X-RateLimit-Reset"] = str(int(time.time() + duration))
                        break
        return response
