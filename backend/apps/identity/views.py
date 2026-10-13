"""Identity Authentication Views.

Provides CSRF initialization, Platform Owner login, current user verification,
and session logout endpoints.
"""

import uuid

from django.contrib.auth import authenticate, login, logout
from django.middleware.csrf import get_token
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.auditlog.models import AuditAction, AuditOperationSource, AuditTargetType
from apps.auditlog.services import AuditEventError, record_audit_event
from apps.identity.models import LoginAttempt, UserStatus
from apps.identity.tenant_context import (
    get_active_context,
    get_available_contexts,
    get_client_ip,
    get_eligible_tenant_memberships,
    hash_identifier,
    hash_ip,
)
from apps.organizations.models import (
    MembershipStatus,
    MembershipType,
    Organization,
    OrganizationMembership,
    OrganizationStatus,
)
from .authentication import EnforcedSessionAuthentication
from .permissions import HasConsoleAccess, IsActiveAuthenticatedUser
from .serializers import LoginSerializer, PlatformUserProfileSerializer


class CsrfTokenView(APIView):
    """Public endpoint to establish the VibeConnect CSRF token cookie."""

    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request, *args, **kwargs) -> Response:
        get_token(request)
        return Response(
            {"detail": "CSRF cookie set."},
            status=status.HTTP_200_OK,
        )


@method_decorator(csrf_protect, name="dispatch")
class LoginView(APIView):
    """Unified VibeConnect Login Endpoint (Phase 2D Stage 3).

    Protected by Django CSRF validation and scoped rate throttling.
    Verifies credentials and console access, sets server-side context,
    rotates session keys, and records privacy-preserving LoginAttempt evidence.
    """

    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth_login"

    def post(self, request, *args, **kwargs) -> Response:
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data["email"]
        password = serializer.validated_data["password"]

        client_ip = get_client_ip(request)
        ident_hash = hash_identifier(email)
        ip_hash_val = hash_ip(client_ip)

        user = authenticate(request, email=email, password=password)

        if not user:
            request.session.flush()
            LoginAttempt.objects.create(
                user=None,
                identifier_hash=ident_hash,
                ip_hash=ip_hash_val,
                result="failure",
                failure_code="invalid_credentials",
            )
            return Response(
                {"detail": "Invalid credentials or unauthorized account."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        if not user.is_active or getattr(user, "status", None) != UserStatus.ACTIVE:
            request.session.flush()
            LoginAttempt.objects.create(
                user=None,
                identifier_hash=ident_hash,
                ip_hash=ip_hash_val,
                result="failure",
                failure_code="invalid_credentials",
            )
            return Response(
                {"detail": "Invalid credentials or unauthorized account."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        is_owner = bool(getattr(user, "is_platform_owner", False))
        eligible_memberships = list(get_eligible_tenant_memberships(user))
        has_platform_roles = user.platform_role_assignments.filter(role__status="active").exists()

        if not is_owner and len(eligible_memberships) == 0 and not has_platform_roles:
            request.session.flush()
            LoginAttempt.objects.create(
                user=user,
                identifier_hash=ident_hash,
                ip_hash=ip_hash_val,
                result="failure",
                failure_code="no_console_access",
            )
            return Response(
                {
                    "code": "NO_CONSOLE_ACCESS",
                    "detail": "No active console access.",
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        login(request, user)
        request.session.cycle_key()

        if is_owner:
            request.session["active_context_type"] = "platform_owner"
            request.session["tenant_organization_id"] = None
        elif has_platform_roles and len(eligible_memberships) == 0:
            request.session["active_context_type"] = "support"
            request.session["tenant_organization_id"] = None
        elif len(eligible_memberships) == 1:
            single_org = eligible_memberships[0].organization
            request.session["active_context_type"] = "tenant"
            request.session["tenant_organization_id"] = str(single_org.id)
        else:
            request.session["active_context_type"] = None
            request.session["tenant_organization_id"] = None

        request.session.modified = True
        active_context = get_active_context(request, user)

        LoginAttempt.objects.create(
            user=user,
            identifier_hash=ident_hash,
            ip_hash=ip_hash_val,
            result="success",
            failure_code="",
        )

        try:
            is_admin = False
            if not is_owner:
                from apps.identity.tenant_context import get_eligible_tenant_admin_memberships
                is_admin = get_eligible_tenant_admin_memberships(user).exists()
            target_repr = "Platform Owner Session" if is_owner else ("Tenant Admin Session" if is_admin else "Tenant Member Session")
            record_audit_event(
                action=AuditAction.LOGIN_SUCCESS,
                target_type=AuditTargetType.AUTH,
                target_id=user.id,
                target_repr=target_repr,
                actor=user,
                organization_id=None,
                operation_source=AuditOperationSource.AUTHENTICATION,
                metadata={"auth_method": "session"},
            )
        except AuditEventError:
            logout(request)
            return Response(
                {"detail": "A server error occurred during authentication."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        data = PlatformUserProfileSerializer(user).data
        data["active_context"] = active_context
        data["available_contexts"] = get_available_contexts(user)
        return Response(data, status=status.HTTP_200_OK)


class CurrentUserView(APIView):
    """Current User Profile Endpoint.

    Verifies active session, revalidates selected context, and returns sanitized profile.
    """

    authentication_classes = [EnforcedSessionAuthentication]
    permission_classes = [HasConsoleAccess]

    def get(self, request, *args, **kwargs) -> Response:
        user = request.user
        active_context = get_active_context(request, user)
        available_contexts = get_available_contexts(user)

        data = PlatformUserProfileSerializer(user).data
        data["active_context"] = active_context
        data["available_contexts"] = available_contexts
        return Response(data, status=status.HTTP_200_OK)


class LogoutView(APIView):
    """Logout Endpoint.

    POST-only, CSRF-enforced endpoint that destroys the active database session
    for authenticated Platform Owners, Tenant Admins, and Tenant Members.
    """

    authentication_classes = [EnforcedSessionAuthentication]
    permission_classes = [IsActiveAuthenticatedUser]

    def post(self, request, *args, **kwargs) -> Response:
        actor = request.user
        is_owner = getattr(actor, "is_platform_owner", False)
        is_admin = False
        if not is_owner:
            from apps.identity.tenant_context import get_eligible_tenant_admin_memberships
            is_admin = get_eligible_tenant_admin_memberships(actor).exists()
        target_repr = "Platform Owner Session" if is_owner else ("Tenant Admin Session" if is_admin else "Tenant Member Session")

        logout(request)
        try:
            record_audit_event(
                action=AuditAction.LOGOUT_SUCCESS,
                target_type=AuditTargetType.AUTH,
                target_id=actor.id,
                target_repr=target_repr,
                actor=actor,
                organization_id=None,
                operation_source=AuditOperationSource.AUTHENTICATION,
                metadata={"auth_method": "session"},
            )
        except AuditEventError:
            return Response(
                {"detail": "A server error occurred during logout."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        return Response(
            {"detail": "Successfully logged out."},
            status=status.HTTP_200_OK,
        )


@method_decorator(csrf_protect, name="dispatch")
class ContextSelectionView(APIView):
    """Authenticated endpoint to switch between platform owner and tenant console contexts."""

    authentication_classes = [EnforcedSessionAuthentication]
    permission_classes = [IsActiveAuthenticatedUser]

    def post(self, request, *args, **kwargs) -> Response:
        context_type = request.data.get("context_type")
        organization_id = request.data.get("organization_id")

        if context_type not in ("platform_owner", "tenant", "support"):
            return Response(
                {
                    "code": "INVALID_CONTEXT_TYPE",
                    "detail": "context_type must be 'platform_owner', 'tenant', or 'support'.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if context_type == "support":
            from apps.access_control.models import PlatformRoleAssignment, RoleStatus
            has_support_role = PlatformRoleAssignment.objects.filter(
                user=request.user,
                role__status=RoleStatus.ACTIVE,
                role__is_system_role=True,
                role__organization__isnull=True,
                role__role_permissions__permission__is_active=True,
                role__role_permissions__permission__console_module__target_context="support",
            ).exists()
            if not getattr(request.user, "is_platform_owner", False) and not has_support_role:

                return Response(
                    {
                        "code": "INSUFFICIENT_PRIVILEGES",
                        "detail": "Support Operator privileges required for this context.",
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )
            request.session["active_context_type"] = "support"
            request.session["tenant_organization_id"] = None
            request.session.cycle_key()
            request.session.modified = True

            active_context = get_active_context(request, request.user)
            available_contexts = get_available_contexts(request.user)
            return Response(
                {
                    "active_context": active_context,
                    "available_contexts": available_contexts,
                },
                status=status.HTTP_200_OK,
            )

        if context_type == "platform_owner":
            if not getattr(request.user, "is_platform_owner", False):
                return Response(
                    {
                        "code": "INSUFFICIENT_PRIVILEGES",
                        "detail": "Platform Owner privileges required for this context.",
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )
            request.session["active_context_type"] = "platform_owner"
            request.session["tenant_organization_id"] = None
            request.session.cycle_key()
            request.session.modified = True

            active_context = get_active_context(request, request.user)
            available_contexts = get_available_contexts(request.user)
            return Response(
                {
                    "active_context": active_context,
                    "available_contexts": available_contexts,
                },
                status=status.HTTP_200_OK,
            )

        # context_type == "tenant"
        if not organization_id:
            return Response(
                {
                    "code": "INVALID_CONTEXT_DATA",
                    "detail": "organization_id is required for tenant context.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            org_uuid = uuid.UUID(str(organization_id))
        except (ValueError, TypeError):
            return Response(
                {
                    "code": "INVALID_CONTEXT_DATA",
                    "detail": "Invalid organization_id format.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        org = Organization.objects.filter(pk=org_uuid).first()
        if not org:
            return Response(
                {
                    "code": "ORGANIZATION_NOT_FOUND",
                    "detail": "Organization not found.",
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        if org.status != OrganizationStatus.ACTIVE:
            return Response(
                {
                    "code": "ORGANIZATION_NOT_ACTIVE",
                    "detail": "Organization is not active.",
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        membership = OrganizationMembership.objects.filter(
            user=request.user,
            organization=org,
            status=MembershipStatus.ACTIVE,
        ).first()

        if not membership:
            return Response(
                {
                    "code": "INSUFFICIENT_PRIVILEGES",
                    "detail": "User lacks active membership for this organization.",
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        request.session["active_context_type"] = "tenant"
        request.session["tenant_organization_id"] = str(org.id)
        request.session.cycle_key()
        request.session.modified = True

        active_context = get_active_context(request, request.user)
        available_contexts = get_available_contexts(request.user)
        return Response(
            {
                "active_context": active_context,
                "available_contexts": available_contexts,
            },
            status=status.HTTP_200_OK,
        )

    def get(self, request, *args, **kwargs) -> Response:
        active_context = get_active_context(request, request.user)
        available_contexts = get_available_contexts(request.user)
        return Response(
            {
                "active_context": active_context,
                "available_contexts": available_contexts,
            },
            status=status.HTTP_200_OK,
        )

