"""VibeConnect Phase 2B Plans URL Routing.

Direct explicit routing mapping the exact approved Phase 2B endpoint inventory
to the 7 compact resource ViewSets.
"""

from django.urls import path
from apps.plans.views import (
    PlanCapabilityViewSet,
    PlanModuleViewSet,
    PlanPriceViewSet,
    PlanProductViewSet,
    PlanQuotaViewSet,
    PlanVersionViewSet,
    PlanViewSet,
    PublicPlanListView,
)

urlpatterns = [
    # Public discovery
    path("public/plans/", PublicPlanListView.as_view(), name="public-plan-list"),

    # 1. Plans
    path("plans/", PlanViewSet.as_view({"get": "list", "post": "create"}), name="plan-list-create"),
    path("plans/<str:pk>/", PlanViewSet.as_view({"get": "retrieve", "patch": "partial_update"}), name="plan-detail"),

    # 2. Plan Versions (nested collection under plan)
    path("plans/<str:plan_id>/versions/", PlanVersionViewSet.as_view({"get": "list", "post": "create"}), name="plan-version-list-create"),

    # Plan Versions (direct detail & actions)
    path("plan-versions/<str:pk>/", PlanVersionViewSet.as_view({"get": "retrieve", "patch": "partial_update"}), name="plan-version-detail"),
    path("plan-versions/<str:pk>/clone/", PlanVersionViewSet.as_view({"post": "clone"}), name="plan-version-clone"),
    path("plan-versions/<str:pk>/readiness/", PlanVersionViewSet.as_view({"get": "readiness"}), name="plan-version-readiness"),
    path("plan-versions/<str:pk>/activate/", PlanVersionViewSet.as_view({"post": "activate"}), name="plan-version-activate"),
    path("plan-versions/<str:pk>/retire/", PlanVersionViewSet.as_view({"post": "retire"}), name="plan-version-retire"),

    # 3. Prices
    path("plan-versions/<str:version_id>/prices/", PlanPriceViewSet.as_view({"get": "list", "post": "create"}), name="plan-price-list-create"),
    path("plan-prices/<str:pk>/", PlanPriceViewSet.as_view({"get": "retrieve", "patch": "partial_update", "delete": "destroy"}), name="plan-price-detail"),

    # 4. Products
    path("plan-versions/<str:version_id>/products/", PlanProductViewSet.as_view({"get": "list", "post": "create"}), name="plan-product-list-create"),
    path("plan-products/<str:pk>/", PlanProductViewSet.as_view({"get": "retrieve", "delete": "destroy"}), name="plan-product-detail"),

    # 5. Modules
    path("plan-versions/<str:version_id>/modules/", PlanModuleViewSet.as_view({"get": "list", "post": "create"}), name="plan-module-list-create"),
    path("plan-modules/<str:pk>/", PlanModuleViewSet.as_view({"get": "retrieve", "delete": "destroy"}), name="plan-module-detail"),

    # 6. Capabilities
    path("plan-versions/<str:version_id>/capabilities/", PlanCapabilityViewSet.as_view({"get": "list", "post": "create"}), name="plan-capability-list-create"),
    path("plan-capabilities/<str:pk>/", PlanCapabilityViewSet.as_view({"get": "retrieve", "delete": "destroy"}), name="plan-capability-detail"),

    # 7. Quotas
    path("plan-versions/<str:version_id>/quotas/", PlanQuotaViewSet.as_view({"get": "list", "post": "create"}), name="plan-quota-list-create"),
    path("plan-quotas/<str:pk>/", PlanQuotaViewSet.as_view({"get": "retrieve", "patch": "partial_update", "delete": "destroy"}), name="plan-quota-detail"),
]
