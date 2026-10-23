"""REST API Views for User Invitations (Phase 3C)."""

from django.conf import settings
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
                full_name=data.get("full_name", ""),
                role=data.get("role"),
                membership_type=data["membership_type"],
                product=data.get("product_id"),
                product_ids=data.get("product_ids"),
                module_ids=data.get("module_ids"),
                invited_by=actor,
            )

            # If user already exists with active membership, immediately assign products/modules
            from django.contrib.auth import get_user_model
            from apps.organizations.models import OrganizationMembership
            clean_email = data["email"].strip().lower()
            existing_user = get_user_model().objects.filter(email__iexact=clean_email).first()
            if existing_user:
                if data.get("full_name") and not existing_user.full_name:
                    existing_user.full_name = data["full_name"].strip()
                    existing_user.save(update_fields=["full_name"])
                membership = OrganizationMembership.objects.filter(
                    organization=org,
                    user=existing_user,
                    status="active",
                ).first()
                if membership:
                    p_ids = data.get("product_ids") or ([] if not data.get("product_id") else [str(data.get("product_id"))])
                    m_ids = data.get("module_ids") or []
                    if p_ids:
                        from apps.assignments.services.assignment_services import assign_user_to_product
                        from apps.product_registry.models import ProductModule
                        for pid in p_ids:
                            try:
                                prod_mods = list(
                                    ProductModule.objects.filter(
                                        product_id=pid,
                                        id__in=m_ids,
                                        status="active",
                                    ).values_list("id", flat=True)
                                ) if m_ids else None

                                assign_user_to_product(
                                    organization_id=org.id,
                                    user_id=existing_user.id,
                                    product_id=pid,
                                    module_ids=prod_mods,
                                    membership_id=membership.id,
                                    actor=actor,
                                )
                            except Exception:
                                pass
            frontend_base = getattr(settings, "FRONTEND_BASE_URL", "").rstrip("/")
            activation_url = f"{frontend_base}/invitations/accept/{raw_token}"
            return Response(
                {
                    "id": str(invitation.id),
                    "email": invitation.email,
                    "status": invitation.status,
                    "expires_at": invitation.expires_at.isoformat(),
                    "raw_token": raw_token,  # returned for testing/admin copy at issuance
                    "activation_url": activation_url,
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
