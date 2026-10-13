"""Organization Membership Views (Phase 2D Stage 4).

Implements OrganizationMembershipViewSet providing nested organization membership
listing, creation, role updates, and lifecycle transition endpoints under Platform Owner authority.
Enforces strict organization isolation and delegates all mutations to transactional domain services.
"""

import uuid
from django.db.models import Q
from rest_framework import exceptions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.identity.authentication import EnforcedSessionAuthentication
from apps.identity.permissions import IsPlatformOwnerContext
from apps.organizations.membership_serializers import (
    MembershipLifecycleActionSerializer,
    OrganizationMembershipCreateSerializer,
    OrganizationMembershipDetailSerializer,
    OrganizationMembershipListSerializer,
    OrganizationMembershipUpdateSerializer,
)
from apps.organizations.membership_services import (
    InvalidMembershipTransitionError,
    MembershipAlreadyExistsError,
    MembershipEndedRestoreRequiredError,
    MembershipNotEndedError,
    MembershipNotFoundError,
    MembershipValidationError,
    OrganizationNotActiveError,
    UserInactiveCannotRestoreError,
    UserNotActiveError,
    create_membership,
    end_membership,
    reactivate_membership,
    restore_membership,
    suspend_membership,
    update_membership_type,
)
from apps.organizations.models import (
    MembershipStatus,
    MembershipType,
    Organization,
    OrganizationMembership,
)
from apps.organizations.pagination import OrganizationPagination
from apps.access_control.services.guards import LastAdminProtectionError

MEMBERSHIP_ORDERING_FIELDS_MAP = {
    "created_at": ["created_at", "id"],
    "-created_at": ["-created_at", "-id"],
    "joined_at": ["joined_at", "id"],
    "-joined_at": ["-joined_at", "-id"],
    "membership_type": ["membership_type", "id"],
    "-membership_type": ["-membership_type", "-id"],
    "status": ["status", "id"],
    "-status": ["-status", "-id"],
}


class OrganizationMembershipViewSet(viewsets.GenericViewSet):
    """ViewSet managing memberships within a specific organization under Platform Owner authority."""

    authentication_classes = [EnforcedSessionAuthentication]
    permission_classes = [IsPlatformOwnerContext]
    pagination_class = OrganizationPagination
    http_method_names = ["get", "post", "patch", "head", "options"]

    def _get_organization(self) -> Organization:
        """Validate and resolve organization_id from URL path."""
        org_id = self.kwargs.get("organization_id")
        try:
            uuid.UUID(str(org_id))
        except (ValueError, TypeError):
            raise exceptions.NotFound(
                {"code": "ORGANIZATION_NOT_FOUND", "detail": f"Organization '{org_id}' not found."}
            )

        org = Organization.objects.filter(pk=org_id).first()
        if not org:
            raise exceptions.NotFound(
                {"code": "ORGANIZATION_NOT_FOUND", "detail": f"Organization '{org_id}' not found."}
            )
        return org

    def get_queryset(self):
        org = self._get_organization()
        queryset = OrganizationMembership.objects.filter(organization=org).select_related("user", "organization", "role")

        # 1. Filter by status
        status_param = self.request.query_params.get("status")
        if status_param is not None:
            if status_param not in MembershipStatus.values:
                allowed_str = ", ".join(MembershipStatus.values)
                raise exceptions.ValidationError(
                    {"status": [f"Invalid status '{status_param}'. Allowed: {allowed_str}."]}
                )
            queryset = queryset.filter(status=status_param)

        # 2. Filter by membership_type
        type_param = self.request.query_params.get("membership_type")
        if type_param is not None:
            if type_param not in MembershipType.values:
                allowed_str = ", ".join(MembershipType.values)
                raise exceptions.ValidationError(
                    {"membership_type": [f"Invalid membership_type '{type_param}'. Allowed: {allowed_str}."]}
                )
            queryset = queryset.filter(membership_type=type_param)

        # 3. Search by user email or full_name
        raw_search = self.request.query_params.get("search")
        if raw_search is not None:
            search = raw_search.strip()
            if len(search) > 100:
                raise exceptions.ValidationError(
                    {"search": ["Search query must be 100 characters or fewer."]}
                )
            if search:
                queryset = queryset.filter(
                    Q(user__email__icontains=search) | Q(user__full_name__icontains=search)
                )

        # 4. Deterministic ordering
        ordering_param = self.request.query_params.get("ordering")
        if ordering_param:
            if ordering_param not in MEMBERSHIP_ORDERING_FIELDS_MAP:
                raise exceptions.ValidationError(
                    {"ordering": [f"Invalid ordering field '{ordering_param}'."]}
                )
            order_by = MEMBERSHIP_ORDERING_FIELDS_MAP[ordering_param]
        else:
            order_by = ["-created_at", "-id"]

        return queryset.order_by(*order_by)

    def get_object(self) -> OrganizationMembership:
        org = self._get_organization()
        pk = self.kwargs.get("pk")
        try:
            uuid.UUID(str(pk))
        except (ValueError, TypeError):
            raise exceptions.NotFound(
                {"code": "MEMBERSHIP_NOT_FOUND", "detail": f"Membership '{pk}' not found."}
            )

        membership = (
            OrganizationMembership.objects.filter(organization=org, pk=pk)
            .select_related("user", "organization", "role")
            .first()
        )
        if not membership:
            raise exceptions.NotFound(
                {"code": "MEMBERSHIP_NOT_FOUND", "detail": f"Membership '{pk}' not found in organization '{org.id}'."}
            )
        return membership

    def list(self, request, organization_id=None, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = OrganizationMembershipListSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = OrganizationMembershipListSerializer(queryset, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def retrieve(self, request, organization_id=None, pk=None, *args, **kwargs):
        membership = self.get_object()
        serializer = OrganizationMembershipDetailSerializer(membership)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def create(self, request, organization_id=None, *args, **kwargs):
        org = self._get_organization()
        serializer = OrganizationMembershipCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            membership = create_membership(
                actor=request.user,
                organization_id=org.id,
                user_id=serializer.validated_data["user_id"],
                membership_type=serializer.validated_data["membership_type"],
            )
        except (MembershipAlreadyExistsError, MembershipEndedRestoreRequiredError) as e:
            return Response({"code": e.code, "detail": e.message}, status=status.HTTP_409_CONFLICT)
        except (OrganizationNotActiveError, UserNotActiveError, MembershipValidationError) as e:
            return Response({"code": e.code, "detail": e.message}, status=status.HTTP_400_BAD_REQUEST)
        except MembershipNotFoundError as e:
            return Response({"code": e.code, "detail": e.message}, status=status.HTTP_404_NOT_FOUND)

        return Response(OrganizationMembershipDetailSerializer(membership).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request, organization_id=None, pk=None, *args, **kwargs):
        membership = self.get_object()
        serializer = OrganizationMembershipUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            updated = update_membership_type(
                actor=request.user,
                membership_id=membership.id,
                new_membership_type=serializer.validated_data["membership_type"],
            )
        except (InvalidMembershipTransitionError, MembershipValidationError, LastAdminProtectionError) as e:
            return Response({"code": e.code, "detail": e.message}, status=status.HTTP_400_BAD_REQUEST)
        except MembershipNotFoundError as e:
            return Response({"code": e.code, "detail": e.message}, status=status.HTTP_404_NOT_FOUND)

        return Response(OrganizationMembershipDetailSerializer(updated).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"])
    def suspend(self, request, organization_id=None, pk=None, *args, **kwargs):
        membership = self.get_object()
        serializer = MembershipLifecycleActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            updated = suspend_membership(
                actor=request.user,
                membership_id=membership.id,
                reason=serializer.validated_data.get("reason"),
            )
        except (InvalidMembershipTransitionError, MembershipValidationError, LastAdminProtectionError) as e:
            return Response({"code": e.code, "detail": e.message}, status=status.HTTP_400_BAD_REQUEST)
        except MembershipNotFoundError as e:
            return Response({"code": e.code, "detail": e.message}, status=status.HTTP_404_NOT_FOUND)

        return Response(OrganizationMembershipDetailSerializer(updated).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"])
    def reactivate(self, request, organization_id=None, pk=None, *args, **kwargs):
        membership = self.get_object()

        try:
            updated = reactivate_membership(
                actor=request.user,
                membership_id=membership.id,
            )
        except (OrganizationNotActiveError, UserNotActiveError, InvalidMembershipTransitionError, MembershipValidationError) as e:
            return Response({"code": e.code, "detail": e.message}, status=status.HTTP_400_BAD_REQUEST)
        except MembershipNotFoundError as e:
            return Response({"code": e.code, "detail": e.message}, status=status.HTTP_404_NOT_FOUND)

        return Response(OrganizationMembershipDetailSerializer(updated).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"])
    def end(self, request, organization_id=None, pk=None, *args, **kwargs):
        membership = self.get_object()
        serializer = MembershipLifecycleActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            updated = end_membership(
                actor=request.user,
                membership_id=membership.id,
                reason=serializer.validated_data.get("reason"),
            )
        except (InvalidMembershipTransitionError, MembershipValidationError, LastAdminProtectionError) as e:
            return Response({"code": e.code, "detail": e.message}, status=status.HTTP_400_BAD_REQUEST)
        except MembershipNotFoundError as e:
            return Response({"code": e.code, "detail": e.message}, status=status.HTTP_404_NOT_FOUND)

        return Response(OrganizationMembershipDetailSerializer(updated).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"])
    def restore(self, request, organization_id=None, pk=None, *args, **kwargs):
        membership = self.get_object()

        try:
            updated = restore_membership(
                actor=request.user,
                membership_id=membership.id,
            )
        except (OrganizationNotActiveError, UserInactiveCannotRestoreError, MembershipNotEndedError, MembershipValidationError) as e:
            return Response({"code": e.code, "detail": e.message}, status=status.HTTP_400_BAD_REQUEST)
        except MembershipNotFoundError as e:
            return Response({"code": e.code, "detail": e.message}, status=status.HTTP_404_NOT_FOUND)

        return Response(OrganizationMembershipDetailSerializer(updated).data, status=status.HTTP_200_OK)
