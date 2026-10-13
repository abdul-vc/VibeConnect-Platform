"""Identity Custom Authentication Classes.

Provides EnforcedSessionAuthentication to guarantee HTTP 401 for unauthenticated
requests while strictly preserving CSRF validation.
"""

from rest_framework.authentication import SessionAuthentication


class EnforcedSessionAuthentication(SessionAuthentication):
    """SessionAuthentication that returns an authentication header.

    When an unauthenticated request attempts to access an endpoint protected by
    permissions such as IsAuthenticated or IsPlatformOwner, DRF raises
    AuthenticationFailed (resulting in HTTP 401 Unauthorized) rather than
    PermissionDenied (HTTP 403 Forbidden).
    Strictly preserves full CSRF validation for mutating requests.
    """

    def authenticate_header(self, request) -> str:
        return "Session"
