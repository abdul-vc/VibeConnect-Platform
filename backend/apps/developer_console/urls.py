from django.urls import path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework.permissions import AllowAny

from apps.developer_console import views

urlpatterns = [
    # OpenAPI Schema & Developer Documentation (Phase 6B-5)
    path(
        "schema/",
        SpectacularAPIView.as_view(permission_classes=[AllowAny]),
        name="developer-schema",
    ),
    path(
        "docs/",
        SpectacularSwaggerView.as_view(
            url_name="developer-schema",
            permission_classes=[AllowAny],
        ),
        name="developer-docs",
    ),

    # Frozen Read Endpoints
    path("catalog/products/", views.DeveloperCatalogProductListView.as_view(), name="developer-catalog-products"),
    path("organization/", views.DeveloperOrganizationDetailView.as_view(), name="developer-organization-detail"),
    path("entitlements/", views.DeveloperEntitlementListView.as_view(), name="developer-entitlements-list"),
    path("assignments/", views.DeveloperAssignmentListView.as_view(), name="developer-assignments-list"),
]
