from drf_spectacular.utils import extend_schema, OpenApiResponse
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.assignments.models import UserProductAssignment
from apps.developer_console.authentication import ApiKeyAuthentication
from apps.developer_console.mixins import DeveloperApiViewMixin
from apps.developer_console.pagination import DeveloperApiPagination
from apps.developer_console.permissions import HasApiScope
from apps.developer_console.serializers import (
    DeveloperAssignmentSerializer,
    DeveloperCatalogProductSerializer,
    DeveloperEntitlementSerializer,
    DeveloperOrganizationSerializer,
)
from apps.developer_console.throttling import DeveloperKeyRateThrottle
from apps.entitlements.models import OrganizationProductEntitlement
from apps.product_registry.models import Product, ProductStatus


class DeveloperCatalogProductListView(DeveloperApiViewMixin, APIView):
    """GET /api/v1/developer/catalog/products/

    Lists published products, modules, capabilities, and active public plans.
    """

    authentication_classes = [ApiKeyAuthentication]
    permission_classes = [HasApiScope]
    throttle_classes = [DeveloperKeyRateThrottle]
    pagination_class = DeveloperApiPagination
    serializer_class = DeveloperCatalogProductSerializer
    required_scope = "catalog:read"

    @extend_schema(
        summary="List Catalog Products",
        description="Lists active, published products, modules, capabilities, and public plans. Scope required: `catalog:read`.",
        tags=["Catalog"],
        responses={200: DeveloperCatalogProductSerializer(many=True)},
    )

    def get(self, request):
        queryset = (
            Product.objects.filter(status=ProductStatus.ACTIVE)
            .prefetch_related("modules", "modules__features")
            .order_by("name")
        )
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(queryset, request)
        serializer = DeveloperCatalogProductSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)


class DeveloperOrganizationDetailView(DeveloperApiViewMixin, APIView):
    """GET /api/v1/developer/organization/

    Returns the core profile of the bound tenant organization.
    """

    authentication_classes = [ApiKeyAuthentication]
    permission_classes = [HasApiScope]
    throttle_classes = [DeveloperKeyRateThrottle]
    serializer_class = DeveloperOrganizationSerializer
    required_scope = "organization:read"

    @extend_schema(
        summary="Get Tenant Organization Profile",
        description="Returns the organization details bound to the calling API key. Scope required: `organization:read`.",
        tags=["Organization"],
        responses={200: DeveloperOrganizationSerializer},
    )
    def get(self, request):
        serializer = DeveloperOrganizationSerializer(request.tenant)
        return Response(serializer.data)


class DeveloperEntitlementListView(DeveloperApiViewMixin, APIView):
    """GET /api/v1/developer/entitlements/

    Lists active product entitlements granted to the bound tenant organization.
    """

    authentication_classes = [ApiKeyAuthentication]
    permission_classes = [HasApiScope]
    throttle_classes = [DeveloperKeyRateThrottle]
    pagination_class = DeveloperApiPagination
    serializer_class = DeveloperEntitlementSerializer
    required_scope = "entitlements:read"

    @extend_schema(
        summary="List Organization Entitlements",
        description="Lists active product entitlements granted to the bound tenant organization. Scope required: `entitlements:read`.",
        tags=["Entitlements"],
        responses={200: DeveloperEntitlementSerializer(many=True)},
    )
    def get(self, request):
        queryset = (
            OrganizationProductEntitlement.objects.filter(organization=request.tenant)
            .select_related("product")
            .order_by("-created_at")
        )
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(queryset, request)
        serializer = DeveloperEntitlementSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)


class DeveloperAssignmentListView(DeveloperApiViewMixin, APIView):
    """GET /api/v1/developer/assignments/

    Lists user seat allocations and product assignments in the bound tenant.
    """

    authentication_classes = [ApiKeyAuthentication]
    permission_classes = [HasApiScope]
    throttle_classes = [DeveloperKeyRateThrottle]
    pagination_class = DeveloperApiPagination
    serializer_class = DeveloperAssignmentSerializer
    required_scope = "assignments:read"

    @extend_schema(
        summary="List User Product Assignments",
        description="Lists user product assignments and seat allocations in the bound tenant. Scope required: `assignments:read`.",
        tags=["Assignments"],
        responses={200: DeveloperAssignmentSerializer(many=True)},
    )
    def get(self, request):
        queryset = (
            UserProductAssignment.objects.filter(organization=request.tenant)
            .select_related("user", "product")
            .order_by("-assigned_at")
        )
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(queryset, request)
        serializer = DeveloperAssignmentSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)
