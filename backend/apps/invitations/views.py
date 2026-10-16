"""REST API Views for User Invitations (Phase 3C)."""

from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.invitations.serializers import (
    AcceptInvitationSerializer,
    InvitationValidationResponseSerializer,
    IssueInvitationSerializer,
)
from apps.invitations.services import (
    DuplicateInvitationError,
    InvitationAlreadyUsedError,
    InvitationError,
    InvitationExpiredError,
    InvitationNotFoundError,
    InvitationRevokedError,
    InvitationValidationError,
    accept_invitation,
    issue_invitation,
    validate_invitation,
)


class IssueInvitationView(APIView):
    """Issue a new user invitation within tenant boundary."""

    permission_classes = [IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "invitation_issue"

    def post(self, request):
        serializer = IssueInvitationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        org = data["organization"]
        actor = request.user

        # RBAC Check: platform owner or tenant admin in the target org
        is_owner = getattr(actor, "is_platform_owner", False)
        is_tenant_admin = actor.organization_memberships.filter(
            organization=org,
            membership_type="tenant_admin",
            status="active",
        ).exists()

        if not (is_owner or is_tenant_admin):
            return Response(
                {"detail": "You do not have permission to invite users to this organization."},
                status=status.HTTP_403_FORBIDDEN,
            )

        try:
            invitation, raw_token = issue_invitation(
                organization=org,
                email=data["email"],
                role=data.get("role"),
                membership_type=data["membership_type"],
                product=data.get("product_id"),
                invited_by=actor,
            )
            return Response(
                {
                    "id": str(invitation.id),
                    "email": invitation.email,
                    "status": invitation.status,
                    "expires_at": invitation.expires_at.isoformat(),
                    "raw_token": raw_token,  # returned for testing/admin copy
                },
                status=status.HTTP_201_CREATED,
            )
        except DuplicateInvitationError as exc:
            return Response({"detail": str(exc), "code": exc.code}, status=status.HTTP_409_CONFLICT)
        except InvitationValidationError as exc:
            return Response({"detail": str(exc), "code": exc.code}, status=status.HTTP_400_BAD_REQUEST)
        except InvitationError as exc:
            return Response({"detail": str(exc), "code": exc.code}, status=status.HTTP_400_BAD_REQUEST)


class ValidateInvitationView(APIView):
    """Validate an invitation token for the public onboarding/accept page."""

    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "invitation_validate"

    def get(self, request, token: str):
        try:
            invitation = validate_invitation(token)
            serializer = InvitationValidationResponseSerializer(invitation)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except InvitationNotFoundError as exc:
            return Response({"detail": str(exc), "code": exc.code}, status=status.HTTP_404_NOT_FOUND)
        except InvitationAlreadyUsedError as exc:
            return Response({"detail": str(exc), "code": exc.code}, status=status.HTTP_409_CONFLICT)
        except InvitationExpiredError as exc:
            return Response({"detail": str(exc), "code": exc.code}, status=status.HTTP_410_GONE)
        except InvitationRevokedError as exc:
            return Response({"detail": str(exc), "code": exc.code}, status=status.HTTP_410_GONE)
        except InvitationError as exc:
            return Response({"detail": str(exc), "code": exc.code}, status=status.HTTP_400_BAD_REQUEST)


class AcceptInvitationView(APIView):
    """Set password and accept the invitation."""

    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "invitation_accept"

    def post(self, request, token: str):
        serializer = AcceptInvitationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            result = accept_invitation(
                raw_token=token,
                password=serializer.validated_data["password"],
                full_name=serializer.validated_data.get("full_name", ""),
            )
            return Response(
                {
                    "success": True,
                    "detail": "Account setup and activation complete.",
                    "data": result,
                },
                status=status.HTTP_200_OK,
            )
        except InvitationNotFoundError as exc:
            return Response({"detail": str(exc), "code": exc.code}, status=status.HTTP_404_NOT_FOUND)
        except InvitationAlreadyUsedError as exc:
            return Response({"detail": str(exc), "code": exc.code}, status=status.HTTP_409_CONFLICT)
        except InvitationExpiredError as exc:
            return Response({"detail": str(exc), "code": exc.code}, status=status.HTTP_410_GONE)
        except InvitationRevokedError as exc:
            return Response({"detail": str(exc), "code": exc.code}, status=status.HTTP_410_GONE)
        except InvitationValidationError as exc:
            return Response({"detail": str(exc), "code": exc.code}, status=status.HTTP_400_BAD_REQUEST)
        except InvitationError as exc:
            return Response({"detail": str(exc), "code": exc.code}, status=status.HTTP_400_BAD_REQUEST)
