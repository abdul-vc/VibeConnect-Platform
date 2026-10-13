"""Tenant and Console Context Utilities for VibeConnect Phase 2D (Stage 3).

Provides helper functions for:
- Keyed HMAC-SHA256 hashing of identifiers and IP addresses for LoginAttempt privacy.
- Extraction of eligible tenant admin memberships.
- Construction of available and active console contexts.
- Revalidation and prompt revocation of invalid session contexts.
"""

import hashlib
import hmac
from typing import Any
import uuid

from django.conf import settings

from apps.identity.models import UserStatus
from apps.organizations.models import (
    MembershipStatus,
    MembershipType,
    Organization,
    OrganizationMembership,
    OrganizationStatus,
)


def hash_identifier(identifier: str) -> str:
    """Compute HMAC-SHA256 of normalized identifier using SECRET_KEY."""
    key = settings.SECRET_KEY.encode("utf-8")
    normalized = identifier.strip().lower().encode("utf-8")
    return hmac.new(key, normalized, hashlib.sha256).hexdigest()


def hash_ip(ip: str) -> str:
    """Compute HMAC-SHA256 of cleaned IP address using SECRET_KEY."""
    key = settings.SECRET_KEY.encode("utf-8")
    cleaned = ip.strip().encode("utf-8")
    return hmac.new(key, cleaned, hashlib.sha256).hexdigest()


def get_client_ip(request) -> str:
    """Extract client IP from X-Forwarded-For or REMOTE_ADDR."""
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        return x_forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "").strip()


def get_eligible_tenant_memberships(user: Any):
    """Return active tenant memberships (both admin and member) in active organizations for user."""
    if not user or not getattr(user, "is_active", False) or getattr(user, "status", None) != UserStatus.ACTIVE:
        return OrganizationMembership.objects.none()

    return (
        OrganizationMembership.objects.select_related("organization")
        .filter(
            user=user,
            status=MembershipStatus.ACTIVE,
            organization__status=OrganizationStatus.ACTIVE,
        )
        .order_by("organization__name", "organization__code")
    )


def get_eligible_tenant_admin_memberships(user: Any):
    """Return active tenant_admin memberships in active organizations for user."""
    return get_eligible_tenant_memberships(user).filter(
        membership_type=MembershipType.TENANT_ADMIN
    )


def get_available_contexts(user: Any) -> list[dict]:
    """Return list of available contexts for user.

    Platform owners receive 'platform_owner' context plus any eligible tenant contexts.
    Tenant admins and members receive their eligible tenant contexts.
    """
    contexts: list[dict] = []
    if not user or not getattr(user, "is_active", False) or getattr(user, "status", None) != UserStatus.ACTIVE:
        return contexts

    if getattr(user, "is_platform_owner", False):
        contexts.append({"type": "platform_owner", "organization": None})

    from apps.access_control.models import PlatformRoleAssignment, RoleStatus
    has_support_role = PlatformRoleAssignment.objects.filter(
        user=user,
        role__status=RoleStatus.ACTIVE,
        role__is_system_role=True,
        role__organization__isnull=True,
        role__role_permissions__permission__is_active=True,
        role__role_permissions__permission__console_module__target_context="support",
    ).exists()
    if getattr(user, "is_platform_owner", False) or has_support_role:
        contexts.append({"type": "support", "organization": None})


    eligible_memberships = get_eligible_tenant_memberships(user)
    for m in eligible_memberships:
        contexts.append(
            {
                "type": "tenant",
                "organization": {
                    "id": str(m.organization.id),
                    "code": m.organization.code,
                    "name": m.organization.name,
                },
                "membership_type": m.membership_type,
            }
        )

    return contexts


def get_active_context(request, user: Any) -> dict | None:
    """Resolve and revalidate active console context from session.

    If context has become invalid (e.g. organization deactivated, membership ended,
    or user deactivated), revokes it promptly from session and returns None.
    """
    if not user or not getattr(user, "is_active", False) or getattr(user, "status", None) != UserStatus.ACTIVE:
        _clear_session_context(request)
        return None

    context_type = request.session.get("active_context_type")
    tenant_org_id = request.session.get("tenant_organization_id")

    if context_type == "platform_owner":
        if getattr(user, "is_platform_owner", False):
            from apps.access_control.services.evaluation import get_request_evaluation

            eval_result = get_request_evaluation(request, user, "platform_owner", None)
            return {
                "type": "platform_owner",
                "organization": None,
                "effective_permissions": eval_result.effective_permissions,
                "allowed_modules": eval_result.allowed_modules,
            }
        _clear_session_context(request)
        return None

    if context_type == "support":
        from apps.access_control.services.evaluation import get_request_evaluation

        eval_result = get_request_evaluation(request, user, "support", None)
        if eval_result.allowed_modules or eval_result.effective_permissions:
            return {
                "type": "support",
                "organization": None,
                "effective_permissions": eval_result.effective_permissions,
                "allowed_modules": eval_result.allowed_modules,
            }
        _clear_session_context(request)
        return None

    if context_type == "tenant" and tenant_org_id:
        try:
            org_uuid = uuid.UUID(str(tenant_org_id))
        except (ValueError, TypeError):
            _clear_session_context(request)
            return None

        org = Organization.objects.filter(pk=org_uuid, status=OrganizationStatus.ACTIVE).first()
        if not org:
            _clear_session_context(request)
            return None

        membership = OrganizationMembership.objects.filter(
            user=user,
            organization=org,
            status=MembershipStatus.ACTIVE,
        ).first()

        if not membership:
            _clear_session_context(request)
            return None

        from apps.access_control.services.evaluation import get_request_evaluation

        eval_result = get_request_evaluation(request, user, "tenant", org.id)
        return {
            "type": "tenant",
            "organization": {
                "id": str(org.id),
                "code": org.code,
                "name": org.name,
            },
            "membership_type": membership.membership_type,
            "effective_permissions": eval_result.effective_permissions,
            "allowed_modules": eval_result.allowed_modules,
        }

    return None


def _clear_session_context(request) -> None:
    """Revoke active console context keys from session."""
    if hasattr(request, "session"):
        request.session["active_context_type"] = None
        request.session["tenant_organization_id"] = None
        request.session.modified = True
