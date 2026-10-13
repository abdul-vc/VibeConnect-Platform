"""Marketplace URL Configuration (Phase 6A Stage 4).

Exposes:
- GET  /api/v1/public/marketplace/products/
- GET  /api/v1/marketplace/products/
- GET  /api/v1/marketplace/products/<code_or_id>/
- POST /api/v1/marketplace/products/<code_or_id>/enable/
- POST /api/v1/marketplace/products/<code_or_id>/request/
"""

from django.urls import path

from apps.marketplace.views import (
    MarketplaceProductDetailView,
    MarketplaceProductEnableView,
    MarketplaceProductRequestView,
    PublicMarketplaceCatalogView,
    TenantMarketplaceCatalogView,
)

urlpatterns = [
    # Public catalog discovery (unauthenticated)
    path(
        "public/marketplace/products/",
        PublicMarketplaceCatalogView.as_view(),
        name="public-marketplace-products",
    ),
    # Authenticated tenant catalog & actions
    path(
        "marketplace/products/",
        TenantMarketplaceCatalogView.as_view(),
        name="marketplace-product-list",
    ),
    path(
        "marketplace/products/<str:code_or_id>/",
        MarketplaceProductDetailView.as_view(),
        name="marketplace-product-detail",
    ),
    path(
        "marketplace/products/<str:code_or_id>/enable/",
        MarketplaceProductEnableView.as_view(),
        name="marketplace-product-enable",
    ),
    path(
        "marketplace/products/<str:code_or_id>/request/",
        MarketplaceProductRequestView.as_view(),
        name="marketplace-product-request",
    ),
]
