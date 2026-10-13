"""Support Impersonation Views for VibeConnect Phase 6D.

Provides endpoints for:
- Listing eligible target users within an organization.
- Creating a time-limited, audited SupportImpersonationSession.
- Fetching the active session with server-calculated remaining time.
- Terminating an active session.
"""

import uuid
from typing import Any

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Q
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.access_control.constants import (
    PERMISSION_SUPPORT_IMPERSONATION_INITIATE,
)
from apps.access_control.models import PlatformRoleAssignment
from apps.access_control.permissions import HasSupportPermission
from apps.identity.impersonation_service import (
    create_impersonation_session,
    terminate_impersonation_session,
)
from apps.identity.models import (
    ImpersonationSessionStatus,
    PlatformUser,
    SupportImpersonationSession,
    UserStatus,
)
from apps.organizations.models import (
    MembershipStatus,
    MembershipType,
    Organization,
    OrganizationMembership,
    OrganizationStatus,
)


class SupportImpersonationSessionSerializer(serializers.ModelSerializer):
    operator_email = serializers.CharField(source="operator.email", read_only=True)
    target_user_email = serializers.CharField(source="target_user.email", read_only=True)
    target_user_name = serializers.CharField(source="target_user.full_name", read_only=True)
    target_organization_code = serializers.CharField(source="target_organization.code", read_only=True)
    target_organization_name = serializers.CharField(source="target_organization.name", read_only=True)
    remaining_seconds = serializers.SerializerMethodField()

    class Meta:
        model = SupportImpersonationSession
        fields = [
            "id",
            "operator_email",
            "target_user",
            "target_user_email",
            "target_user_name",
            "target_organization",
            "target_organization_code",
            "target_organization_name",
            "reason",
            "ticket_reference",
            "status",
            "created_at",
            "expires_at",
            "terminated_at",
            "correlation_id",
            "remaining_seconds",
        ]

    def get_remaining_seconds(self, obj) -> int:
        if obj.status != ImpersonationSessionStatus.ACTIVE:
            return 0
        now = timezone.now()
        if now >= obj.expires_at:
            return 0
        return int((obj.expires_at - now).total_seconds())


class EligibleTargetUserSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    email = serializers.CharField()
    full_name = serializers.CharField()
    membership_type = serializers.CharField()


class EligibleTargetsView(APIView):
    """List eligible impersonation target users in an organization.

    Locked Policy:
    - Target must be an active Tenant Admin or Member in the organization.
    - Platform Owners and Support Operators are strictly excluded.
    """

    permission_classes = [IsAuthenticated, HasSupportPermission]
    required_console_permission = PERMISSION_SUPPORT_IMPERSONATION_INITIATE

    def get(self, request):
        org_id_str = request.query_params.get("organization_id")
        if not org_id_str:
            raise ValidationError({"organization_id": "Organization ID is required."})

        try:
            org_uuid = uuid.UUID(org_id_str.strip())
        except (ValueError, TypeError):
            raise ValidationError({"organization_id": "Invalid organization UUID."})

        org = Organization.objects.filter(pk=org_uuid, status=OrganizationStatus.ACTIVE).first()
        if not org:
            raise ValidationError({"organization_id": "Active organization not found."})

        # Excluded users: platform owners, superusers, and users with platform role assignments
        support_operator_ids = set(PlatformRoleAssignment.objects.values_list("user_id", flat=True))

        memberships = (
            OrganizationMembership.objects.filter(
                organization=org,
                status=MembershipStatus.ACTIVE,
                membership_type__in=[MembershipType.TENANT_ADMIN, MembershipType.MEMBER],
                user__status=UserStatus.ACTIVE,
                user__is_active=True,
                user__is_platform_owner=False,
                user__is_superuser=False,
            )
            .exclude(user_id__in=support_operator_ids)
            .exclude(user_id=request.user.id)
            .select_related("user")
            .order_by("user__email")
        )

        results = []
        for m in memberships[:50]:
            results.append(
                {
                    "id": m.user.id,
                    "email": m.user.email,
                    "full_name": m.user.full_name or m.user.email,
                    "membership_type": m.membership_type,
                }
            )

        return Response({"targets": results})


class ImpersonationSessionCreateView(APIView):
    """Initiate a time-limited, audited SupportImpersonationSession."""

    permission_classes = [IsAuthenticated, HasSupportPermission]
    required_console_permission = PERMISSION_SUPPORT_IMPERSONATION_INITIATE

    def post(self, request):
        target_user_id = request.data.get("target_user_id")
        target_organization_id = request.data.get("target_organization_id")
        reason = request.data.get("reason")
        ticket_reference = request.data.get("ticket_reference", "")

        if not target_user_id or not target_organization_id:
            raise ValidationError("target_user_id and target_organization_id are required.")

        clean_reason = (reason or "").strip()
        if not clean_reason:
            raise ValidationError({"reason": "Reason is required and cannot be empty."})
        if len(clean_reason) > 500:
            raise ValidationError({"reason": "Reason cannot exceed 500 characters."})

        clean_ticket = (ticket_reference or "").strip()
        if not clean_ticket:
            raise ValidationError({"ticket_reference": "Ticket/incident reference is required and cannot be empty."})
        if len(clean_ticket) > 100:
            raise ValidationError({"ticket_reference": "Ticket reference cannot exceed 100 characters."})

        try:
            session = create_impersonation_session(
                operator=request.user,
                target_user_id=target_user_id,
                target_organization_id=target_organization_id,
                reason=clean_reason,
                ticket_reference=ticket_reference,
            )
        except (DjangoValidationError, ValidationError) as e:
            raise ValidationError({"detail": str(e)})

        serializer = SupportImpersonationSessionSerializer(session)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class ActiveImpersonationSessionView(APIView):
    """Retrieve the currently active session for the authenticated operator or target user.

    Preserves strict tenant isolation and security:
    - Queries active session where request.user is either operator or target_user.
    - If neither, returns {"active_session": null} with HTTP 200 OK without 403 errors.
    - Never exposes any third-party or unrelated sessions.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        now = timezone.now()
        session = (
            SupportImpersonationSession.objects.filter(
                Q(operator=request.user) | Q(target_user=request.user),
                status=ImpersonationSessionStatus.ACTIVE,
            )
            .select_related("operator", "target_user", "target_organization")
            .first()
        )

        if not session:
            return Response({"active_session": None})

        # Server-authority expiry check
        if now >= session.expires_at:
            session.status = ImpersonationSessionStatus.EXPIRED
            session.terminated_at = session.expires_at
            session.save(update_fields=["status", "terminated_at"])
            return Response({"active_session": None})

        serializer = SupportImpersonationSessionSerializer(session)
        return Response({"active_session": serializer.data})


class ImpersonationSessionTerminateView(APIView):
    """Terminate an active impersonation session."""

    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        reason = request.data.get("reason", "Session terminated.")
        try:
            session = terminate_impersonation_session(
                session_id=pk,
                actor=request.user,
                reason=reason,
            )
        except (DjangoValidationError, ValidationError) as e:
            raise ValidationError({"detail": str(e)})

        serializer = SupportImpersonationSessionSerializer(session)
        return Response(serializer.data)
