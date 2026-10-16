"""Branding API Views (Phase 4A/4B).

Provides endpoints for:
- Active branding resolution with tenant-to-global fallback
- Profile management (Platform Owner & Tenant Admin)
- Revision history, draft edit, atomic publish, and rollback copies
- Asset upload with type/size validation and SVG security checks
- Live preview token formatting
"""

from __future__ import annotations

import base64
import uuid

from django.core.exceptions import ValidationError
from rest_framework import exceptions, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.branding.models import BrandAsset, BrandingProfile, BrandingRevision
from apps.branding.serializers import (
    BrandAssetSerializer,
    BrandingProfileSerializer,
    BrandingRevisionSerializer,
    SaveDraftRevisionSerializer,
)
from apps.branding.services import (
    BrandingServiceError,
    create_draft_revision,
    get_active_branding,
    get_or_create_profile,
    publish_revision,
    rollback_to_revision,
    update_draft_revision,
    upload_brand_asset,
)
from apps.access_control.constants import CONTEXT_TENANT
from apps.access_control.services.evaluation import evaluate_access
from apps.organizations.models import MembershipStatus, MembershipType, Organization, OrganizationMembership


def _check_branding_view_permission(user, org: Organization) -> None:
    """Ensure caller has authorization to view the target tenant branding profile."""
    if not user or not user.is_authenticated:
        raise exceptions.NotAuthenticated()

    if getattr(user, "is_platform_owner", False):
        return

    eval_result = evaluate_access(user, CONTEXT_TENANT, org.id)
    if not eval_result.has_permission("branding.view"):
        raise exceptions.PermissionDenied("Actor lacks required permission 'branding.view'.")


def _check_branding_manage_permission(user, profile: BrandingProfile) -> None:
    """Ensure caller has authorization to modify or publish the target branding profile."""
    if not user or not user.is_authenticated:
        raise exceptions.NotAuthenticated()

    if getattr(user, "is_platform_owner", False):
        return

    # Global profile can only be modified by platform owners
    if profile.is_global:
        raise exceptions.PermissionDenied("Platform owner privileges required to manage global branding.")

    # For tenant profiles, caller must have active TENANT_ADMIN membership in that org
    org = profile.organization
    if not org:
        raise exceptions.PermissionDenied("Profile is not associated with an organization.")

    eval_result = evaluate_access(user, CONTEXT_TENANT, org.id)
    if not eval_result.has_permission("branding.manage") and not eval_result.has_permission("branding.view"):
        raise exceptions.PermissionDenied("Tenant administrator privileges required to manage branding.")


class ActiveBrandingView(APIView):
    """Resolve active published branding tokens and assets.

    Falls back to global platform default if tenant has no published override.
    """

    def get(self, request: Request) -> Response:
        org_id = request.query_params.get("organization_id")
        if not org_id and request.user.is_authenticated:
            # Check for active context or active tenant membership
            org_id = getattr(request.user, "active_tenant_id", None)
            if not org_id:
                active_mem = OrganizationMembership.objects.filter(
                    user=request.user,
                    status=MembershipStatus.ACTIVE,
                ).first()
                if active_mem:
                    org_id = str(active_mem.organization_id)

        branding_data = get_active_branding(org_id)
        return Response(branding_data, status=status.HTTP_200_OK)


class BrandingProfileListView(APIView):
    """List and create branding profiles.

    - Platform Owners see all profiles and can manage Global branding.
    - Tenant members see their organization profile (auto-initialized if needed).
    """

    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        user = request.user
        if getattr(user, "is_platform_owner", False):
            # Include global profile ensuring it exists
            get_or_create_profile(organization=None, actor=user)
            profiles = BrandingProfile.objects.all().order_by("-is_active", "-created_at")
            return Response(BrandingProfileSerializer(profiles, many=True).data, status=status.HTTP_200_OK)

        # Tenant context: find user's organization
        org_id = request.query_params.get("organization_id")
        if org_id:
            membership = OrganizationMembership.objects.filter(
                user=user,
                organization_id=org_id,
                status=MembershipStatus.ACTIVE,
            ).first()
        else:
            membership = OrganizationMembership.objects.filter(
                user=user,
                status=MembershipStatus.ACTIVE,
            ).first()

        if not membership:
            raise exceptions.PermissionDenied("No active organization membership found.")

        _check_branding_view_permission(user, membership.organization)
        profile = get_or_create_profile(organization=membership.organization, actor=user)
        return Response(BrandingProfileSerializer([profile], many=True).data, status=status.HTTP_200_OK)

    def post(self, request: Request) -> Response:
        user = request.user
        org_id = request.data.get("organization_id")
        name = request.data.get("name")

        if not org_id:
            if not getattr(user, "is_platform_owner", False):
                raise exceptions.PermissionDenied("Platform owner required to create global profile.")
            profile = get_or_create_profile(organization=None, actor=user, name=name)
        else:
            profile = get_or_create_profile(organization_id=org_id, actor=user, name=name)

        _check_branding_manage_permission(user, profile)
        return Response(BrandingProfileSerializer(profile).data, status=status.HTTP_201_CREATED)


class BrandingProfileDetailView(APIView):
    """Retrieve and manage a branding profile."""

    permission_classes = [IsAuthenticated]

    def get(self, request: Request, pk: str) -> Response:
        try:
            profile = BrandingProfile.objects.get(id=pk)
        except BrandingProfile.DoesNotExist:
            return Response({"detail": "Branding profile not found."}, status=status.HTTP_404_NOT_FOUND)

        if profile.organization:
            _check_branding_view_permission(request.user, profile.organization)

        return Response(BrandingProfileSerializer(profile).data, status=status.HTTP_200_OK)

    def patch(self, request: Request, pk: str) -> Response:
        try:
            profile = BrandingProfile.objects.get(id=pk)
        except BrandingProfile.DoesNotExist:
            return Response({"detail": "Branding profile not found."}, status=status.HTTP_404_NOT_FOUND)

        _check_branding_manage_permission(request.user, profile)

        if "name" in request.data:
            profile.name = str(request.data["name"]).strip()
        if "description" in request.data:
            profile.description = str(request.data["description"]).strip()
        if "is_active" in request.data:
            profile.is_active = bool(request.data["is_active"])

        profile.updated_by = request.user
        profile.save()
        return Response(BrandingProfileSerializer(profile).data, status=status.HTTP_200_OK)


class BrandingProfileRevisionsView(APIView):
    """List revision history and create new draft revisions."""

    permission_classes = [IsAuthenticated]

    def get(self, request: Request, profile_id: str) -> Response:
        try:
            profile = BrandingProfile.objects.get(id=profile_id)
        except BrandingProfile.DoesNotExist:
            return Response({"detail": "Branding profile not found."}, status=status.HTTP_404_NOT_FOUND)

        if profile.organization:
            _check_branding_view_permission(request.user, profile.organization)

        revisions = profile.revisions.all().order_by("-revision_number")
        return Response(BrandingRevisionSerializer(revisions, many=True).data, status=status.HTTP_200_OK)

    def post(self, request: Request, profile_id: str) -> Response:
        try:
            profile = BrandingProfile.objects.get(id=profile_id)
        except BrandingProfile.DoesNotExist:
            return Response({"detail": "Branding profile not found."}, status=status.HTTP_404_NOT_FOUND)

        _check_branding_manage_permission(request.user, profile)

        serializer = SaveDraftRevisionSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            rev = create_draft_revision(
                profile_id=profile.id,
                actor=request.user,
                tokens=serializer.validated_data.get("tokens"),
                logo_asset_id=serializer.validated_data.get("logo_asset_id"),
                favicon_asset_id=serializer.validated_data.get("favicon_asset_id"),
            )
        except ValidationError as err:
            return Response({"detail": str(err)}, status=status.HTTP_400_BAD_REQUEST)
        except BrandingServiceError as err:
            return Response({"detail": err.message, "code": err.code}, status=status.HTTP_400_BAD_REQUEST)

        return Response(BrandingRevisionSerializer(rev).data, status=status.HTTP_201_CREATED)


class BrandingRevisionDetailView(APIView):
    """Retrieve or update a draft revision."""

    permission_classes = [IsAuthenticated]

    def get(self, request: Request, pk: str) -> Response:
        try:
            rev = BrandingRevision.objects.get(id=pk)
        except BrandingRevision.DoesNotExist:
            return Response({"detail": "Revision not found."}, status=status.HTTP_404_NOT_FOUND)

        return Response(BrandingRevisionSerializer(rev).data, status=status.HTTP_200_OK)

    def patch(self, request: Request, pk: str) -> Response:
        try:
            rev = BrandingRevision.objects.get(id=pk)
        except BrandingRevision.DoesNotExist:
            return Response({"detail": "Revision not found."}, status=status.HTTP_404_NOT_FOUND)

        _check_branding_manage_permission(request.user, rev.profile)

        # Immutability check: cannot update a published revision
        if rev.status == "published":
            return Response(
                {"detail": "Published revisions are immutable.", "code": "REVISION_IMMUTABLE"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = SaveDraftRevisionSerializer(data=request.data, partial=True)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            updated = update_draft_revision(
                revision_id=rev.id,
                actor=request.user,
                tokens=serializer.validated_data.get("tokens"),
                logo_asset_id=serializer.validated_data.get("logo_asset_id"),
                favicon_asset_id=serializer.validated_data.get("favicon_asset_id"),
            )
        except (ValidationError, BrandingServiceError) as err:
            msg = getattr(err, "message", str(err))
            return Response({"detail": msg}, status=status.HTTP_400_BAD_REQUEST)

        return Response(BrandingRevisionSerializer(updated).data, status=status.HTTP_200_OK)


class BrandingRevisionPublishView(APIView):
    """Atomically publish a revision."""

    permission_classes = [IsAuthenticated]

    def post(self, request: Request, pk: str) -> Response:
        try:
            rev = BrandingRevision.objects.get(id=pk)
        except BrandingRevision.DoesNotExist:
            return Response({"detail": "Revision not found."}, status=status.HTTP_404_NOT_FOUND)

        _check_branding_manage_permission(request.user, rev.profile)

        try:
            published = publish_revision(revision_id=rev.id, actor=request.user)
        except (ValidationError, BrandingServiceError) as err:
            msg = getattr(err, "message", str(err))
            return Response({"detail": msg}, status=status.HTTP_400_BAD_REQUEST)

        return Response(BrandingRevisionSerializer(published).data, status=status.HTTP_200_OK)


class BrandingRevisionRollbackView(APIView):
    """Roll back to a target revision by creating a new revision copy."""

    permission_classes = [IsAuthenticated]

    def post(self, request: Request, pk: str) -> Response:
        try:
            rev = BrandingRevision.objects.get(id=pk)
        except BrandingRevision.DoesNotExist:
            return Response({"detail": "Revision not found."}, status=status.HTTP_404_NOT_FOUND)

        _check_branding_manage_permission(request.user, rev.profile)

        try:
            rolled_back = rollback_to_revision(target_revision_id=rev.id, actor=request.user)
        except (ValidationError, BrandingServiceError) as err:
            msg = getattr(err, "message", str(err))
            return Response({"detail": msg}, status=status.HTTP_400_BAD_REQUEST)

        return Response(BrandingRevisionSerializer(rolled_back).data, status=status.HTTP_201_CREATED)


class BrandAssetUploadView(APIView):
    """Upload and validate a brand asset (logo/favicon/banner)."""

    permission_classes = [IsAuthenticated]

    def post(self, request: Request, profile_id: str) -> Response:
        try:
            profile = BrandingProfile.objects.get(id=profile_id)
        except BrandingProfile.DoesNotExist:
            return Response({"detail": "Branding profile not found."}, status=status.HTTP_404_NOT_FOUND)

        _check_branding_manage_permission(request.user, profile)

        # Support both multipart form file upload and JSON data payload
        uploaded_file = request.FILES.get("file")
        if uploaded_file:
            asset_type = request.data.get("asset_type", "logo")
            file_name = uploaded_file.name
            content_type = uploaded_file.content_type or "image/png"
            file_bytes = uploaded_file.read()
        else:
            asset_type = request.data.get("asset_type", "logo")
            file_name = request.data.get("file_name", "asset.png")
            content_type = request.data.get("content_type", "image/png")
            raw_b64 = request.data.get("file_data", "")
            if "," in raw_b64:
                raw_b64 = raw_b64.split(",", 1)[1]
            try:
                file_bytes = base64.b64decode(raw_b64)
            except Exception:
                return Response({"detail": "Invalid base64 asset payload."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            asset = upload_brand_asset(
                profile_id=profile.id,
                actor=request.user,
                asset_type=asset_type,
                file_name=file_name,
                content_type=content_type,
                file_bytes=file_bytes,
            )
        except (ValidationError, BrandingServiceError) as err:
            msg = getattr(err, "message", str(err))
            return Response({"detail": msg}, status=status.HTTP_400_BAD_REQUEST)

        return Response(BrandAssetSerializer(asset).data, status=status.HTTP_201_CREATED)


class BrandingRevisionPreviewView(APIView):
    """Retrieve CSS variable preview map for a revision."""

    permission_classes = [IsAuthenticated]

    def get(self, request: Request, pk: str) -> Response:
        try:
            rev = BrandingRevision.objects.get(id=pk)
        except BrandingRevision.DoesNotExist:
            return Response({"detail": "Revision not found."}, status=status.HTTP_404_NOT_FOUND)

        # Transform token keys into standard CSS custom properties
        css_vars = {
            f"--{k.replace('_', '-')}": v
            for k, v in (rev.tokens or {}).items()
        }
        return Response(
            {
                "revision_id": str(rev.id),
                "revision_number": rev.revision_number,
                "status": rev.status,
                "css_variables": css_vars,
                "logo_url": rev.logo_asset.file_data if rev.logo_asset else None,
                "favicon_url": rev.favicon_asset.file_data if rev.favicon_asset else None,
            },
            status=status.HTTP_200_OK,
        )
