"""Showcase URL Patterns – Phase 11."""
from django.urls import path
from apps.showcase import views

urlpatterns = [
    # Profile CRUD
    path("profiles/", views.ShowcaseProfileListView.as_view(), name="showcase-profiles-list"),
    path("profiles/<uuid:profile_id>/", views.ShowcaseProfileDetailView.as_view(), name="showcase-profiles-detail"),
    path("profiles/<uuid:profile_id>/publish/", views.ShowcasePublishView.as_view(), name="showcase-profiles-publish"),
    path("profiles/<uuid:profile_id>/unpublish/", views.ShowcaseUnpublishView.as_view(), name="showcase-profiles-unpublish"),
    path("profiles/<uuid:profile_id>/launchability/", views.ShowcaseLaunchabilityView.as_view(), name="showcase-profiles-launchability"),
    path("profiles/<uuid:profile_id>/launch-demo/", views.ShowcaseDemoLaunchView.as_view(), name="showcase-profiles-launch-demo"),
    path("profiles/<uuid:profile_id>/launch-config/", views.ShowcaseLaunchConfigView.as_view(), name="showcase-profiles-launch-config"),
    path("profiles/<uuid:profile_id>/media/", views.ShowcaseMediaView.as_view(), name="showcase-profiles-media"),
    path("media/<uuid:media_id>/", views.ShowcaseMediaDeleteView.as_view(), name="showcase-media-delete"),
    path("reorder/", views.ShowcaseReorderView.as_view(), name="showcase-profiles-reorder"),
    # Demo environments
    path("products/<uuid:product_id>/demo-environments/", views.DemoEnvironmentListView.as_view(), name="showcase-demo-env-list"),
    path("demo-environments/<uuid:env_id>/", views.DemoEnvironmentDetailView.as_view(), name="showcase-demo-env-detail"),
    # Presentation mode
    path("present/", views.ShowcasePresentationView.as_view(), name="showcase-present"),
]
