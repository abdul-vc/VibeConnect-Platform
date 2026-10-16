"""Showcase Authorization and Permission Policies.

Defines access control rules for product showcase presentation and live product demos.
Ensures platform owners, staff, and users with active showcase demonstration
permissions are allowed access, while denying inactive or unauthorized callers.
"""

from __future__ import annotations

import logging
from typing import Any

from rest_framework import permissions
from rest_framework.exceptions import NotAuthenticated, PermissionDenied
from rest_framework.request import Request

logger = logging.getLogger(__name__)


def check_user_showcase_access(user: Any) -> tuple[bool, str]:
    """Evaluates whether the user is authorized to access showcase demonstration features.

    Returns (is_authorized, reason_if_denied).
    """
    if not user or not getattr(user, "is_authenticated", False):
        return False, "Authentication required."

    if not getattr(user, "is_active", True) or getattr(user, "status", "active") != "active":
        return False, "User account is not active."

    # 1. Platform owners always have showcase presentation access
    if getattr(user, "is_platform_owner", False):
        return True, ""

    # 2. Staff and superusers have administrative presentation access
    if getattr(user, "is_staff", False) or getattr(user, "is_superuser", False):
        return True, ""

    # 3. Direct Django permission check
    if hasattr(user, "has_perm") and user.has_perm("showcase.view"):
        return True, ""

    # Platform owners and administrative staff/superusers only
    return False, "Platform owner access required for Product Showcase."


class HasShowcaseAccess(permissions.BasePermission):
    """DRF permission allowing authorized showcase users (platform owners, staff, and showcase users)."""

    def has_permission(self, request: Request, view: Any) -> bool:
        user = getattr(request, "user", None)
        authorized, message = check_user_showcase_access(user)
        if not authorized:
            if not user or not getattr(user, "is_authenticated", False):
                raise NotAuthenticated(message)
            raise PermissionDenied({"code": "INSUFFICIENT_PRIVILEGES", "detail": message})
        return True
