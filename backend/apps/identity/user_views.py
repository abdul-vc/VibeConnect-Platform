"""Platform User Management Views (Phase 2D Stage 4).

Implements UserViewSet providing central user listing, creation, profile update,
and lifecycle transition endpoints under strict Platform Owner authorization.
Delegates all mutations to transactional domain services.
"""

import uuid
from django.contrib.auth import get_user_model
from django.db.models import Q
from rest_framework import exceptions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.identity.authentication import EnforcedSessionAuthentication
from apps.identity.models import UserStatus
from apps.identity.pagination import UserPagination
from apps.identity.permissions import IsPlatformOwnerContext
from apps.identity.services import (
    InvalidUserTransitionError,
    LastPlatformOwnerError,
    UserAlreadyActiveError,
    UserAlreadyExistsError,
    UserDisabledTerminalError,
    UserNotFoundError,
    UserValidationError,
    anonymize_user,
    create_user,
    disable_user,
    reactivate_user,
    suspend_user,
    update_user_profile,
)
from apps.identity.user_serializers import (
    UserAnonymizeActionSerializer,
    UserCreateSerializer,
    UserDetailSerializer,
    UserLifecycleActionSerializer,
    UserListSerializer,
    UserUpdateSerializer,
)
from apps.access_control.services.guards import LastAdminProtectionError

PlatformUser = get_user_model()

USER_ORDERING_FIELDS_MAP = {
    "created_at": ["created_at", "id"],
    "-created_at": ["-created_at", "-id"],
    "email": ["email", "id"],
    "-email": ["-email", "-id"],
    "full_name": ["full_name", "id"],
    "-full_name": ["-full_name", "-id"],
    "status": ["status", "id"],
    "-status": ["-status", "-id"],
}


class UserViewSet(viewsets.GenericViewSet):
    """ViewSet managing central platform users under Platform Owner authority."""

    authentication_classes = [EnforcedSessionAuthentication]
    permission_classes = [IsPlatformOwnerContext]
    pagination_class = UserPagination
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self):
        queryset = PlatformUser.objects.all()

        # 1. Filter by status
        status_param = self.request.query_params.get("status")
        if status_param is not None:
            if status_param not in UserStatus.values:
                allowed_str = ", ".join(UserStatus.values)
                raise exceptions.ValidationError(
                    {"status": [f"Invalid status '{status_param}'. Allowed: {allowed_str}."]}
                )
            queryset = queryset.filter(status=status_param)

        # 2. Search by email or full_name
        raw_search = self.request.query_params.get("search")
        if raw_search is not None:
            search = raw_search.strip()
            if len(search) > 100:
                raise exceptions.ValidationError(
                    {"search": ["Search query must be 100 characters or fewer."]}
                )
            if search:
                queryset = queryset.filter(Q(email__icontains=search) | Q(full_name__icontains=search))

        # 3. Deterministic ordering
        ordering_param = self.request.query_params.get("ordering")
        if ordering_param:
            if ordering_param not in USER_ORDERING_FIELDS_MAP:
                raise exceptions.ValidationError(
                    {"ordering": [f"Invalid ordering field '{ordering_param}'."]}
                )
            order_by = USER_ORDERING_FIELDS_MAP[ordering_param]
        else:
            order_by = ["-created_at", "-id"]

        return queryset.order_by(*order_by)

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = UserListSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = UserListSerializer(queryset, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def retrieve(self, request, pk=None, *args, **kwargs):
        try:
            uuid.UUID(str(pk))
        except (ValueError, TypeError):
            return Response(
                {"code": "USER_NOT_FOUND", "detail": f"User '{pk}' not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        user = PlatformUser.objects.filter(pk=pk).first()
        if not user:
            return Response(
                {"code": "USER_NOT_FOUND", "detail": f"User '{pk}' not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        serializer = UserDetailSerializer(user)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def create(self, request, *args, **kwargs):
        serializer = UserCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            user = create_user(
                actor=request.user,
                email=serializer.validated_data["email"],
                full_name=serializer.validated_data.get("full_name", ""),
            )
        except UserAlreadyExistsError as e:
            return Response({"code": e.code, "detail": e.message}, status=status.HTTP_409_CONFLICT)
        except UserValidationError as e:
            return Response({"code": e.code, "detail": e.message}, status=status.HTTP_400_BAD_REQUEST)

        return Response(UserDetailSerializer(user).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request, pk=None, *args, **kwargs):
        try:
            uuid.UUID(str(pk))
        except (ValueError, TypeError):
            return Response(
                {"code": "USER_NOT_FOUND", "detail": f"User '{pk}' not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = UserUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            user = update_user_profile(
                actor=request.user,
                user_id=pk,
                full_name=serializer.validated_data["full_name"],
            )
        except UserNotFoundError as e:
            return Response({"code": e.code, "detail": e.message}, status=status.HTTP_404_NOT_FOUND)
        except UserValidationError as e:
            return Response({"code": e.code, "detail": e.message}, status=status.HTTP_400_BAD_REQUEST)

        return Response(UserDetailSerializer(user).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"])
    def suspend(self, request, pk=None, *args, **kwargs):
        try:
            uuid.UUID(str(pk))
        except (ValueError, TypeError):
            return Response(
                {"code": "USER_NOT_FOUND", "detail": f"User '{pk}' not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = UserLifecycleActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            user = suspend_user(
                actor=request.user,
                user_id=pk,
                reason=serializer.validated_data.get("reason"),
            )
        except UserNotFoundError as e:
            return Response({"code": e.code, "detail": e.message}, status=status.HTTP_404_NOT_FOUND)
        except (LastPlatformOwnerError, UserDisabledTerminalError, InvalidUserTransitionError, UserValidationError, LastAdminProtectionError) as e:
            return Response({"code": e.code, "detail": e.message}, status=status.HTTP_400_BAD_REQUEST)

        return Response(UserDetailSerializer(user).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"])
    def reactivate(self, request, pk=None, *args, **kwargs):
        try:
            uuid.UUID(str(pk))
        except (ValueError, TypeError):
            return Response(
                {"code": "USER_NOT_FOUND", "detail": f"User '{pk}' not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        try:
            user = reactivate_user(
                actor=request.user,
                user_id=pk,
            )
        except UserNotFoundError as e:
            return Response({"code": e.code, "detail": e.message}, status=status.HTTP_404_NOT_FOUND)
        except (UserDisabledTerminalError, UserAlreadyActiveError, InvalidUserTransitionError, UserValidationError) as e:
            return Response({"code": e.code, "detail": e.message}, status=status.HTTP_400_BAD_REQUEST)

        return Response(UserDetailSerializer(user).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"])
    def disable(self, request, pk=None, *args, **kwargs):
        try:
            uuid.UUID(str(pk))
        except (ValueError, TypeError):
            return Response(
                {"code": "USER_NOT_FOUND", "detail": f"User '{pk}' not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = UserLifecycleActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            user = disable_user(
                actor=request.user,
                user_id=pk,
                reason=serializer.validated_data.get("reason"),
            )
        except UserNotFoundError as e:
            return Response({"code": e.code, "detail": e.message}, status=status.HTTP_404_NOT_FOUND)
        except (LastPlatformOwnerError, UserDisabledTerminalError, InvalidUserTransitionError, UserValidationError, LastAdminProtectionError) as e:
            return Response({"code": e.code, "detail": e.message}, status=status.HTTP_400_BAD_REQUEST)

        return Response(UserDetailSerializer(user).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"])
    def anonymize(self, request, pk=None, *args, **kwargs):
        if (
            getattr(request, "impersonation_session", None)
            or getattr(request, "_is_impersonated", False)
            or request.META.get("HTTP_X_VIBECONNECT_IMPERSONATION_SESSION")
        ):
            raise exceptions.PermissionDenied(
                {"code": "OPERATION_BLOCKED_DURING_IMPERSONATION", "detail": "Anonymization cannot be performed during an active impersonation session."}
            )

        try:
            uuid.UUID(str(pk))
        except (ValueError, TypeError):
            return Response(
                {"code": "USER_NOT_FOUND", "detail": f"User '{pk}' not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = UserAnonymizeActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            user = anonymize_user(
                user_id=pk,
                actor=request.user,
                reason=serializer.validated_data["reason"],
            )
        except UserNotFoundError as e:
            return Response({"code": e.code, "detail": e.message}, status=status.HTTP_404_NOT_FOUND)
        except (LastPlatformOwnerError, UserValidationError) as e:
            return Response({"code": e.code, "detail": e.message}, status=status.HTTP_400_BAD_REQUEST)

        data = UserDetailSerializer(user).data
        data["retention_notice"] = (
            "Platform user profile has been successfully anonymized and permanently deactivated. "
            "Direct personal identifiers were replaced with pseudonymous values. Historical audit log "
            "entries remain immutable and unmutated as legal/forensic fact."
        )
        return Response(data, status=status.HTTP_200_OK)

