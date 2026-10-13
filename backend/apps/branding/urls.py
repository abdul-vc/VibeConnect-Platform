"""Branding URL Routing (Phase 4A/4B)."""

from django.urls import path

from apps.branding.views import (
    ActiveBrandingView,
    BrandAssetUploadView,
    BrandingProfileDetailView,
    BrandingProfileListView,
    BrandingProfileRevisionsView,
    BrandingRevisionDetailView,
    BrandingRevisionPreviewView,
    BrandingRevisionPublishView,
    BrandingRevisionRollbackView,
)

app_name = "branding"

urlpatterns = [
    path("branding/active/", ActiveBrandingView.as_view(), name="active_branding"),
    path("branding/profiles/", BrandingProfileListView.as_view(), name="profile_list"),
    path("branding/profiles/<uuid:pk>/", BrandingProfileDetailView.as_view(), name="profile_detail"),
    path("branding/profiles/<uuid:profile_id>/revisions/", BrandingProfileRevisionsView.as_view(), name="profile_revisions"),
    path("branding/profiles/<uuid:profile_id>/assets/", BrandAssetUploadView.as_view(), name="profile_assets"),
    path("branding/revisions/<uuid:pk>/", BrandingRevisionDetailView.as_view(), name="revision_detail"),
    path("branding/revisions/<uuid:pk>/publish/", BrandingRevisionPublishView.as_view(), name="revision_publish"),
    path("branding/revisions/<uuid:pk>/rollback/", BrandingRevisionRollbackView.as_view(), name="revision_rollback"),
    path("branding/revisions/<uuid:pk>/preview/", BrandingRevisionPreviewView.as_view(), name="revision_preview"),
]
