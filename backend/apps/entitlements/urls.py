"""Entitlements URL Configuration.

Registers OrganizationProductEntitlementViewSet with SimpleRouter.
"""

from rest_framework.routers import SimpleRouter
from .views import OrganizationProductEntitlementViewSet

app_name = "entitlements"

router = SimpleRouter()
router.register("", OrganizationProductEntitlementViewSet, basename="organization-product-entitlement")

urlpatterns = router.urls
