"""Product Registry URL Routing.

Maps product catalog endpoints:
- GET, POST /api/v1/products/
- GET, PATCH /api/v1/products/<uuid:pk>/
"""

from django.urls import path
from apps.product_registry.views import ProductViewSet

product_list = ProductViewSet.as_view({
    "get": "list",
    "post": "create",
})

product_detail = ProductViewSet.as_view({
    "get": "retrieve",
    "patch": "partial_update",
})

urlpatterns = [
    path("", product_list, name="product-list"),
    path("<uuid:pk>/", product_detail, name="product-detail"),
]

