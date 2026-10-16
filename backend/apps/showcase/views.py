"""Product Showcase Views – Phase 11.

All views require platform_owner context. Tenant users get 403.
Presentation endpoints are owner-read; they return only published profiles,
but are still gated to platform owners (no anonymous access).
"""
from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import models
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.identity.permissions import IsPlatformOwner

from apps.showcase.serializers import (
    ProductDemoEnvironmentSerializer,
    ProductLaunchConfigSerializer,
    ProductShowcaseProfileSerializer,
    ReorderSerializer,
    ShowcaseMediaSerializer,
)
from apps.showcase.services import (
    DemoEnvironmentService,
    ProductShowcaseService,
    ShowcaseServiceError,
    ShowcasePresentationService,
)


def _require_owner(request: Request) -> Response | None:
    """Return a 403 Response if the caller is not a platform owner, else None."""
    user = request.user
    if not getattr(user, "is_platform_owner", False):
        return Response(
            {"detail": "Platform owner access required."},
            status=status.HTTP_403_FORBIDDEN,
        )
    return None


class ShowcaseProfileListView(APIView):
    """GET list, POST create."""

    permission_classes = [IsAuthenticated, IsPlatformOwner]

    def get(self, request: Request) -> Response:
        guard = _require_owner(request)
        if guard:
            return guard
        visibility = request.query_params.get("visibility")
        search = request.query_params.get("search")
        try:
            page = int(request.query_params.get("page", 1))
            page_size = int(request.query_params.get("page_size", 20))
        except (TypeError, ValueError):
            page, page_size = 1, 20
        result = ProductShowcaseService.list_profiles(
            search=search, visibility=visibility, page=page, page_size=page_size
        )
        serializer = ProductShowcaseProfileSerializer(result["results"], many=True)
        return Response({"count": result["count"], "results": serializer.data})

    def post(self, request: Request) -> Response:
        guard = _require_owner(request)
        if guard:
            return guard
        product_id = request.data.get("product_id")
        if not product_id:
            return Response({"detail": "product_id is required."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            profile = ProductShowcaseService.create_profile(
                product_id=str(product_id), actor=request.user, data=request.data
            )
        except ShowcaseServiceError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        serializer = ProductShowcaseProfileSerializer(profile)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class ShowcaseProfileDetailView(APIView):
    """GET detail, PATCH update."""

    permission_classes = [IsAuthenticated, IsPlatformOwner]

    def get(self, request: Request, profile_id: str) -> Response:
        guard = _require_owner(request)
        if guard:
            return guard
        from apps.showcase.models import ProductShowcaseProfile
        try:
            profile = ProductShowcaseProfile.objects.select_related("product").prefetch_related("media").get(pk=profile_id)
        except ProductShowcaseProfile.DoesNotExist:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(ProductShowcaseProfileSerializer(profile).data)

    def patch(self, request: Request, profile_id: str) -> Response:
        guard = _require_owner(request)
        if guard:
            return guard
        try:
            profile = ProductShowcaseService.update_profile(
                profile_id=profile_id, actor=request.user, data=request.data
            )
        except ShowcaseServiceError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(ProductShowcaseProfileSerializer(profile).data)


class ShowcasePublishView(APIView):
    """POST publish a profile."""

    permission_classes = [IsAuthenticated, IsPlatformOwner]

    def post(self, request: Request, profile_id: str) -> Response:
        guard = _require_owner(request)
        if guard:
            return guard
        try:
            profile = ProductShowcaseService.publish_profile(profile_id=profile_id, actor=request.user)
        except ShowcaseServiceError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(ProductShowcaseProfileSerializer(profile).data)


class ShowcaseUnpublishView(APIView):
    """POST unpublish a profile."""

    permission_classes = [IsAuthenticated, IsPlatformOwner]

    def post(self, request: Request, profile_id: str) -> Response:
        guard = _require_owner(request)
        if guard:
            return guard
        try:
            profile = ProductShowcaseService.unpublish_profile(profile_id=profile_id, actor=request.user)
        except ShowcaseServiceError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(ProductShowcaseProfileSerializer(profile).data)


class ShowcaseReorderView(APIView):
    """POST reorder profiles."""

    permission_classes = [IsAuthenticated, IsPlatformOwner]

    def post(self, request: Request) -> Response:
        guard = _require_owner(request)
        if guard:
            return guard
        serializer = ReorderSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        ordered_ids = [str(uid) for uid in serializer.validated_data["ordered_ids"]]
        try:
            ProductShowcaseService.reorder_profiles(ordered_ids=ordered_ids, actor=request.user)
        except ShowcaseServiceError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"detail": "Reordered."})


class ShowcaseLaunchabilityView(APIView):
    """GET launchability contract for a profile."""

    permission_classes = [IsAuthenticated, IsPlatformOwner]

    def get(self, request: Request, profile_id: str) -> Response:
        guard = _require_owner(request)
        if guard:
            return guard
        try:
            contract = ProductShowcaseService.launchability_contract(profile_id=profile_id)
        except ShowcaseServiceError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)
        return Response(contract)


class ShowcaseDemoLaunchView(APIView):
    """POST initiate authorized showcase live demo launch."""

    permission_classes = [IsAuthenticated, IsPlatformOwner]

    def post(self, request: Request, profile_id: str) -> Response:
        guard = _require_owner(request)
        if guard:
            return guard
        try:
            result = ProductShowcaseService.launch_demo(
                profile_id=profile_id, actor=request.user
            )
        except ShowcaseServiceError as exc:
            return Response({"error": "LAUNCH_FAILED", "detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(result, status=status.HTTP_200_OK)


class ShowcaseLaunchConfigView(APIView):
    """GET, PATCH/POST configure launch for a profile."""

    permission_classes = [IsAuthenticated, IsPlatformOwner]

    def get(self, request: Request, profile_id: str) -> Response:
        guard = _require_owner(request)
        if guard:
            return guard
        from apps.showcase.models import ProductLaunchConfig, ProductShowcaseProfile
        try:
            profile = ProductShowcaseProfile.objects.select_related("product").get(pk=profile_id)
        except ProductShowcaseProfile.DoesNotExist:
            return Response({"detail": "Profile not found."}, status=status.HTTP_404_NOT_FOUND)
        config = ProductLaunchConfig.objects.filter(
            models.Q(profile=profile) | models.Q(product=profile.product)
        ).select_related("target_environment").first()
        from apps.showcase.models import ProductDemoEnvironment
        envs = ProductDemoEnvironment.objects.filter(product=profile.product, is_active=True)
        if not config:
            return Response({
                "id": None,
                "product": str(profile.product.id),
                "product_name": profile.product.name,
                "launch_mode": "demo_only",
                "target_environment": None,
                "allowed_targets": [],
                "policy": {},
                "notes": "",
                "available_environments": ProductDemoEnvironmentSerializer(envs, many=True).data,
            })
        data = ProductLaunchConfigSerializer(config).data
        data["available_environments"] = ProductDemoEnvironmentSerializer(envs, many=True).data
        return Response(data)

    def patch(self, request: Request, profile_id: str) -> Response:
        guard = _require_owner(request)
        if guard:
            return guard
        try:
            config = ProductShowcaseService.configure_launch(
                profile_id=profile_id, actor=request.user, data=request.data
            )
        except ShowcaseServiceError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(ProductLaunchConfigSerializer(config).data)

    def post(self, request: Request, profile_id: str) -> Response:
        return self.patch(request, profile_id)



class ShowcaseMediaView(APIView):
    """POST add media to a profile."""

    permission_classes = [IsAuthenticated, IsPlatformOwner]

    def post(self, request: Request, profile_id: str) -> Response:
        guard = _require_owner(request)
        if guard:
            return guard
        try:
            media = ProductShowcaseService.add_media(
                profile_id=profile_id, actor=request.user, data=request.data
            )
        except (ShowcaseServiceError, ValidationError) as exc:
            detail = exc.message_dict if isinstance(exc, ValidationError) else str(exc)
            return Response({"detail": detail}, status=status.HTTP_400_BAD_REQUEST)
        return Response(ShowcaseMediaSerializer(media).data, status=status.HTTP_201_CREATED)


class ShowcaseMediaDeleteView(APIView):
    """DELETE a media item."""

    permission_classes = [IsAuthenticated, IsPlatformOwner]

    def delete(self, request: Request, media_id: str) -> Response:
        guard = _require_owner(request)
        if guard:
            return guard
        try:
            ProductShowcaseService.delete_media(media_id=media_id)
        except ShowcaseServiceError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)
        return Response(status=status.HTTP_204_NO_CONTENT)


# ------------------------------------------------------------------
# Demo Environment Views
# ------------------------------------------------------------------

class DemoEnvironmentListView(APIView):
    """GET list, POST create demo environments for a product."""

    permission_classes = [IsAuthenticated, IsPlatformOwner]

    def get(self, request: Request, product_id: str) -> Response:
        guard = _require_owner(request)
        if guard:
            return guard
        envs = DemoEnvironmentService.list_environments(product_id=product_id)
        return Response(ProductDemoEnvironmentSerializer(envs, many=True).data)

    def post(self, request: Request, product_id: str) -> Response:
        guard = _require_owner(request)
        if guard:
            return guard
        try:
            env = DemoEnvironmentService.create_environment(
                product_id=product_id, actor=request.user, data=request.data
            )
        except (ShowcaseServiceError, ValidationError) as exc:
            detail = exc.message_dict if isinstance(exc, ValidationError) else str(exc)
            return Response({"detail": detail}, status=status.HTTP_400_BAD_REQUEST)
        return Response(ProductDemoEnvironmentSerializer(env).data, status=status.HTTP_201_CREATED)


class DemoEnvironmentDetailView(APIView):
    """PATCH update, DELETE demo environment."""

    permission_classes = [IsAuthenticated, IsPlatformOwner]

    def patch(self, request: Request, env_id: str) -> Response:
        guard = _require_owner(request)
        if guard:
            return guard
        try:
            env = DemoEnvironmentService.update_environment(
                env_id=env_id, actor=request.user, data=request.data
            )
        except (ShowcaseServiceError, ValidationError) as exc:
            detail = exc.message_dict if isinstance(exc, ValidationError) else str(exc)
            return Response({"detail": detail}, status=status.HTTP_400_BAD_REQUEST)
        return Response(ProductDemoEnvironmentSerializer(env).data)

    def delete(self, request: Request, env_id: str) -> Response:
        guard = _require_owner(request)
        if guard:
            return guard
        try:
            DemoEnvironmentService.delete_environment(env_id=env_id)
        except ShowcaseServiceError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)
        return Response(status=status.HTTP_204_NO_CONTENT)


# ------------------------------------------------------------------
# Presentation Mode Views (owner-only read)
# ------------------------------------------------------------------

class ShowcasePresentationView(APIView):
    """GET published profiles for presentation mode – no owner controls."""

    permission_classes = [IsAuthenticated, IsPlatformOwner]

    def get(self, request: Request) -> Response:
        guard = _require_owner(request)
        if guard:
            return guard
        category = request.query_params.get("category")
        profiles = ShowcasePresentationService.presentation_portfolio(category_filter=category)
        return Response(ProductShowcaseProfileSerializer(profiles, many=True).data)
