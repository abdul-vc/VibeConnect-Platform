from rest_framework import exceptions, permissions


class HasApiScope(permissions.BasePermission):
    """Verifies that the presented API key has the scope required by the view

    and rejects any cross-tenant mismatch.
    """

    def has_permission(self, request, view):
        api_key = getattr(request, "developer_api_key", None)
        tenant = getattr(request, "tenant", None)

        if not api_key or not tenant:
            raise exceptions.NotAuthenticated(
                {"error": "AUTHENTICATION_REQUIRED", "detail": "Valid Developer API key required."}
            )

        # 1. Tenant Mismatch Check
        client_tenant_id = (
            request.query_params.get("organization_id")
            or request.query_params.get("tenant_id")
            or request.headers.get("X-Tenant-Id")
        )
        if not client_tenant_id and hasattr(request, "data") and isinstance(request.data, dict):
            client_tenant_id = request.data.get("organization_id") or request.data.get("tenant_id")

        if client_tenant_id:
            raw_id = str(client_tenant_id).strip().lower()
            if raw_id != str(tenant.id).lower() and raw_id != str(tenant.code).lower():
                raise exceptions.PermissionDenied(
                    {"error": "TENANT_MISMATCH", "detail": "Cross-tenant access is forbidden."}
                )

        # 2. Scope Verification
        required_scope = getattr(view, "required_scope", None)
        required_scopes = getattr(view, "required_scopes", None)

        scopes_to_check = []
        if required_scope:
            scopes_to_check.append(required_scope)
        if required_scopes:
            scopes_to_check.extend(required_scopes)

        granted_scopes = set(api_key.scopes or [])
        for req in scopes_to_check:
            if req not in granted_scopes:
                raise exceptions.PermissionDenied(
                    {
                        "error": "INSUFFICIENT_SCOPE",
                        "detail": f"This endpoint requires the '{req}' scope.",
                    }
                )

        return True


class IsTenantAdminForDeveloperConsole(permissions.BasePermission):
    """Allows access only to active Tenant Administrators in their active tenant context.

    Rejects regular members with NO_CONSOLE_ACCESS (403).
    Rejects requests without valid tenant context (403).
    """

    message = "Tenant administrator access required."

    def has_permission(self, request, view):
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            raise exceptions.NotAuthenticated({"code": "AUTHENTICATION_REQUIRED", "detail": "Authentication required."})

        if not user.is_active or getattr(user, "status", None) != "active":
            raise exceptions.PermissionDenied({"code": "USER_NOT_ACTIVE", "detail": "User account is not active."})

        from apps.identity.tenant_context import get_active_context
        from apps.organizations.models import MembershipType, Organization

        context = get_active_context(request, user)
        if not context or context.get("type") != "tenant":
            raise exceptions.PermissionDenied({"code": "TENANT_CONTEXT_REQUIRED", "detail": "Active tenant context required."})

        if context.get("membership_type") != MembershipType.TENANT_ADMIN:
            raise exceptions.PermissionDenied({
                "error": "NO_CONSOLE_ACCESS",
                "code": "NO_CONSOLE_ACCESS",
                "detail": "Tenant administrator access required.",
            })

        org_id = context["organization"]["id"]
        org = Organization.objects.filter(pk=org_id, status="active").first()
        if not org:
            raise exceptions.PermissionDenied({"code": "ORGANIZATION_NOT_ACTIVE", "detail": "Organization is not active."})

        request.tenant = org
        return True


class IsPlatformOwnerForDeveloperConsole(permissions.BasePermission):
    """Allows access only to active Platform Owners in platform_owner context."""

    message = "Platform Owner privileges required."

    def has_permission(self, request, view):
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            raise exceptions.NotAuthenticated({"code": "AUTHENTICATION_REQUIRED", "detail": "Authentication required."})

        if not user.is_active or getattr(user, "status", None) != "active":
            raise exceptions.PermissionDenied({"code": "USER_NOT_ACTIVE", "detail": "User account is not active."})

        if not getattr(user, "is_platform_owner", False):
            raise exceptions.PermissionDenied({"code": "INSUFFICIENT_PRIVILEGES", "detail": "Platform Owner privileges required."})

        session = getattr(request, "session", None)
        if session:
            if session.get("tenant_organization_id") is not None or session.get("active_context_type") == "tenant":
                raise exceptions.PermissionDenied({"code": "CONTEXT_MISMATCH", "detail": "Platform Owner context required."})

        return True
