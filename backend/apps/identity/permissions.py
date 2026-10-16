"""Identity Custom Permission Classes."""

from rest_framework.permissions import BasePermission


class IsPlatformOwner(BasePermission):
    """Allows access only to active, authenticated Platform Owners.

    Returns HTTP 403 Forbidden if user is authenticated but not a platform owner.
    """

    message = "Access restricted to active platform owners."

    def has_permission(self, request, view) -> bool:
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.is_active
            and getattr(request.user, "is_platform_owner", False)
        )


class IsActiveAuthenticatedUser(BasePermission):
    """Allows access to any active, authenticated user."""

    message = "Access restricted to active authenticated users."

    def has_permission(self, request, view) -> bool:
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.is_active
            and getattr(request.user, "status", None) == "active"
        )


class HasConsoleAccess(BasePermission):
    """Allows access to active Platform Owners, Tenant Admins, and Tenant Members.

    Rejects unauthenticated requests (handled by EnforcedSessionAuthentication -> 401)
    and authenticated users without console access (403).
    """

    message = "Access restricted to active platform owners."

    def has_permission(self, request, view) -> bool:
        user = request.user
        if not user or not user.is_authenticated or not user.is_active or getattr(user, "status", None) != "active":
            return False

        if getattr(user, "is_platform_owner", False):
            return True

        from apps.identity.tenant_context import get_eligible_tenant_memberships
        return get_eligible_tenant_memberships(user).exists()


class IsPlatformOwnerContext(BasePermission):
    """Allows access only to active Platform Owners in platform_owner context.

    Rejects requests if:
    - User is unauthenticated (handled by EnforcedSessionAuthentication -> 401)
    - User is not active or status != 'active' (403)
    - User is not a platform owner (403)
    - Session has active tenant context (active_context_type == 'tenant' or tenant_organization_id is not None) (403)
    """

    message = "Access restricted to active platform owners in platform owner context."

    def has_permission(self, request, view) -> bool:
        user = request.user
        if not (
            user
            and user.is_authenticated
            and user.is_active
            and getattr(user, "is_platform_owner", False)
            and getattr(user, "status", None) == "active"
        ):
            return False

        session = getattr(request, "session", None)
        if session:
            if session.get("tenant_organization_id") is not None:
                return False
            if session.get("active_context_type") == "tenant":
                return False

        return True
