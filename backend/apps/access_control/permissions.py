"""DRF Authorization Classes for VibeConnect Phase 2E Access Control (Stage 3).

Provides:
- HasConsolePermission: Fine-grained permission authorization for views.
- HasConsoleModule: Module-level authorization for views.
"""

from typing import Any
import uuid

from rest_framework.exceptions import NotAuthenticated, PermissionDenied
from rest_framework.permissions import BasePermission

from apps.access_control.constants import (
    CONTEXT_PLATFORM_OWNER,
    CONTEXT_SUPPORT,
    CONTEXT_TENANT,
)
from apps.access_control.services.evaluation import get_request_evaluation
from apps.organizations.models import (
    MembershipStatus,
    MembershipType,
    Organization,
    OrganizationMembership,
    OrganizationStatus,
)


def _validate_session_and_context(request: Any) -> tuple[str, Organization | None]:
    """Validate user and server-side session console context.

    Returns (context_type, organization_instance_or_none).
    Raises standard DRF exceptions matching locked error contracts.
    """
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        raise NotAuthenticated()

    if not user.is_active or getattr(user, "status", None) != "active":
        raise PermissionDenied({"code": "USER_NOT_ACTIVE", "detail": "User account is not active."})

    # Phase 6D: Check for active impersonation context on request
    from apps.identity.impersonation_service import revalidate_request_impersonation
    impersonation_session = revalidate_request_impersonation(request)
    if impersonation_session:
        path = getattr(request, "path", "")
        if not (path and "/impersonation/sessions/" in path and path.rstrip("/").endswith("/terminate")):
            org = impersonation_session.target_organization
            target_user = impersonation_session.target_user
            membership = OrganizationMembership.objects.filter(
                user=target_user,
                organization=org,
                status=MembershipStatus.ACTIVE,
            ).first()
            if not membership:
                raise PermissionDenied({"code": "TENANT_CONTEXT_REQUIRED", "detail": "Target user has no active membership."})
            return CONTEXT_TENANT, org


    session = getattr(request, "session", None)
    if not session:
        raise PermissionDenied({"code": "TENANT_CONTEXT_REQUIRED", "detail": "Active console context required."})

    context_type = session.get("active_context_type")
    if not context_type:
        raise PermissionDenied({"code": "TENANT_CONTEXT_REQUIRED", "detail": "Active console context required."})

    if context_type == CONTEXT_PLATFORM_OWNER:
        if not getattr(user, "is_platform_owner", False):
            raise PermissionDenied(
                {"code": "INSUFFICIENT_PRIVILEGES", "detail": "Platform Owner privileges required."}
            )
        return CONTEXT_PLATFORM_OWNER, None

    if context_type == CONTEXT_SUPPORT:
        return CONTEXT_SUPPORT, None

    if context_type == CONTEXT_TENANT:
        tenant_org_id = session.get("tenant_organization_id")
        if not tenant_org_id:
            raise PermissionDenied({"code": "TENANT_CONTEXT_REQUIRED", "detail": "Tenant context required."})

        try:
            org_uuid = uuid.UUID(str(tenant_org_id))
        except (ValueError, TypeError):
            raise PermissionDenied({"code": "TENANT_CONTEXT_REQUIRED", "detail": "Invalid tenant context."})

        org = Organization.objects.filter(pk=org_uuid).first()
        if not org:
            raise PermissionDenied({"code": "TENANT_CONTEXT_REQUIRED", "detail": "Organization not found."})

        if org.status != OrganizationStatus.ACTIVE:
            raise PermissionDenied({"code": "ORGANIZATION_NOT_ACTIVE", "detail": "Organization is not active."})

        membership = OrganizationMembership.objects.filter(
            user=user,
            organization=org,
        ).first()

        if not membership:
            raise PermissionDenied({"code": "TENANT_CONTEXT_REQUIRED", "detail": "Membership not found."})

        if membership.membership_type != MembershipType.TENANT_ADMIN:
            raise PermissionDenied({"code": "NO_CONSOLE_ACCESS", "detail": "No active console access for regular members."})

        if membership.status != MembershipStatus.ACTIVE:
            raise PermissionDenied({"code": "MEMBERSHIP_NOT_ACTIVE", "detail": "Membership is not active."})

        return CONTEXT_TENANT, org

    raise PermissionDenied({"code": "TENANT_CONTEXT_REQUIRED", "detail": "Valid console context required."})


def _get_required_permission(view: Any) -> str | None:
    if hasattr(view, "get_required_console_permission") and callable(view.get_required_console_permission):
        val = view.get_required_console_permission()
        if isinstance(val, str) and val.strip():
            return val.strip()
    val = getattr(view, "required_console_permission", None)
    if isinstance(val, str) and val.strip():
        return val.strip()
    return None


def _get_required_module(view: Any) -> str | None:
    if hasattr(view, "get_required_console_module") and callable(view.get_required_console_module):
        val = view.get_required_console_module()
        if isinstance(val, str) and val.strip():
            return val.strip()
    val = getattr(view, "required_console_module", None)
    if isinstance(val, str) and val.strip():
        return val.strip()
    return None


ALLOWED_IMPERSONATION_CONSOLE_MODULES = frozenset([
    "tenant_landing",
    "tenant_roles",
    "tenant_branding",
    "tenant_showcase",
    "tenant_notifications",
    "tenant_my_products",
])

ALLOWED_IMPERSONATION_CONSOLE_PERMISSIONS = frozenset([
    "roles.view",
    "branding.view",
    "showcase.view",
    "products.view",
    "notifications.view",
])


class HasConsolePermission(BasePermission):
    """Enforces fine-grained permission authorization on a view."""

    def has_permission(self, request, view) -> bool:
        required_perm = _get_required_permission(view)
        if not required_perm:
            raise PermissionDenied(
                {"code": "INSUFFICIENT_PRIVILEGES", "detail": "Required permission declaration missing or invalid."}
            )

        context_type, org = _validate_session_and_context(request)

        # Support Console context evaluation (Phase 6C)
        if context_type == CONTEXT_SUPPORT or (context_type == CONTEXT_PLATFORM_OWNER and required_perm.startswith("support.")):
            eval_result = get_request_evaluation(request, request.user, CONTEXT_SUPPORT, None)
            if eval_result.has_permission(required_perm):
                return True
            raise PermissionDenied(
                {"code": "INSUFFICIENT_PRIVILEGES", "detail": f"Actor lacks required permission '{required_perm}'."}
            )

        # Fine-grained console permissions apply to Tenant Admin context
        if context_type != CONTEXT_TENANT or not org:
            raise PermissionDenied({"code": "TENANT_CONTEXT_REQUIRED", "detail": "Tenant context required."})

        eval_user = request.user
        impersonation_session = getattr(request, "impersonation_session", None)
        if impersonation_session:
            eval_user = impersonation_session.target_user
            path = getattr(request, "path", "")
            is_termination_op = bool(path and "/impersonation/sessions/" in path and path.rstrip("/").endswith("/terminate"))
            # Strict fail-closed allowlist during impersonation:
            # 1. Non-safe mutating HTTP methods are unconditionally rejected (except dedicated session termination)
            if not is_termination_op and request.method not in ("GET", "HEAD", "OPTIONS"):
                raise PermissionDenied(
                    {"code": "OPERATION_BLOCKED_DURING_IMPERSONATION", "detail": "Mutations are strictly prohibited during an active impersonation session."}
                )
            # 2. Hard-block sensitive management actions during impersonation
            if required_perm.startswith(("roles.", "permissions.", "ceilings.", "developer.", "billing.", "entitlements.")):
                if required_perm != "roles.view":
                    raise PermissionDenied(
                        {"code": "OPERATION_BLOCKED_DURING_IMPERSONATION", "detail": "This operation is prohibited during an active impersonation session."}
                    )
            # 3. Explicit permission allowlist check (no wildcard .view fallback permitted)
            if required_perm not in ALLOWED_IMPERSONATION_CONSOLE_PERMISSIONS:
                raise PermissionDenied(
                    {"code": "OPERATION_BLOCKED_DURING_IMPERSONATION", "detail": f"Permission '{required_perm}' is not permitted during an active impersonation session."}
                )

        eval_result = get_request_evaluation(request, eval_user, CONTEXT_TENANT, org.id)
        if eval_result.has_permission(required_perm):
            return True

        raise PermissionDenied(
            {"code": "INSUFFICIENT_PRIVILEGES", "detail": f"Actor lacks required permission '{required_perm}'."}
        )


class HasConsoleModule(BasePermission):
    """Enforces module-level authorization on a view."""

    def has_permission(self, request, view) -> bool:
        required_mod = _get_required_module(view)
        if not required_mod:
            raise PermissionDenied(
                {"code": "MODULE_DISABLED", "detail": "Required module declaration missing or invalid."}
            )

        context_type, org = _validate_session_and_context(request)

        eval_user = request.user
        impersonation_session = getattr(request, "impersonation_session", None)
        if impersonation_session:
            eval_user = impersonation_session.target_user
            path = getattr(request, "path", "")
            is_termination_op = bool(path and "/impersonation/sessions/" in path and path.rstrip("/").endswith("/terminate"))
            # Strict fail-closed allowlist during impersonation:
            # 1. Non-safe mutating HTTP methods are unconditionally rejected (except dedicated session termination)
            if not is_termination_op and request.method not in ("GET", "HEAD", "OPTIONS"):
                raise PermissionDenied(
                    {"code": "OPERATION_BLOCKED_DURING_IMPERSONATION", "detail": "Mutations are strictly prohibited during an active impersonation session."}
                )
            # 2. Module must be in the explicit impersonation allowlist
            if required_mod not in ALLOWED_IMPERSONATION_CONSOLE_MODULES:
                raise PermissionDenied(
                    {"code": "OPERATION_BLOCKED_DURING_IMPERSONATION", "detail": f"Console module '{required_mod}' is not permitted during an active impersonation session."}
                )


        org_id = org.id if org else None
        eval_result = get_request_evaluation(request, eval_user, context_type, org_id)

        if eval_result.has_module(required_mod):
            return True

        raise PermissionDenied(
            {"code": "MODULE_DISABLED", "detail": f"Console module '{required_mod}' is disabled or not available."}
        )



class HasSupportPermission(BasePermission):
    """DRF permission class for Support Console endpoints (Phase 6C).

    Evaluates permissions against CONTEXT_SUPPORT via the centralized
    evaluation engine.
    - Platform Owners automatically possess all support permissions.
    - Support Operators possess permissions explicitly granted by their
      assigned platform-level roles (via PlatformRoleAssignment).
    """

    def has_permission(self, request, view) -> bool:
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            raise NotAuthenticated()

        if not user.is_active or getattr(user, "status", None) != "active":
            raise PermissionDenied({"code": "USER_NOT_ACTIVE", "detail": "User account is not active."})

        required_perm = _get_required_permission(view)
        if not required_perm:
            raise PermissionDenied(
                {"code": "INSUFFICIENT_PRIVILEGES", "detail": "Required support permission declaration missing or invalid."}
            )

        eval_result = get_request_evaluation(request, user, CONTEXT_SUPPORT, None)
        if eval_result.has_permission(required_perm):
            return True

        raise PermissionDenied(
            {"code": "INSUFFICIENT_PRIVILEGES", "detail": f"Actor lacks required permission '{required_perm}'."}
        )

