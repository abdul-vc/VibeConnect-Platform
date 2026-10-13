"""Product Catalog URL Configuration for root router.

Registers endpoints for:
- /api/v1/product-modules/
- /api/v1/product-modules/{id}/
- /api/v1/product-features/
- /api/v1/product-features/{id}/
- /api/v1/product-capabilities/
- /api/v1/product-capabilities/{id}/
"""

from rest_framework.routers import SimpleRouter
from apps.product_registry.views import (
    ProductModuleViewSet,
    ProductFeatureViewSet,
    ProductCapabilityViewSet,
)

router = SimpleRouter()
router.register(r"product-modules", ProductModuleViewSet, basename="product-module")
router.register(r"product-features", ProductFeatureViewSet, basename="product-feature")
router.register(r"product-capabilities", ProductCapabilityViewSet, basename="product-capability")

urlpatterns = router.urls
