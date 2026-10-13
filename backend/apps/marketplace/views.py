"""Marketplace REST API Views (Phase 6A Stage 4).

Implements the frozen Marketplace REST API contract:
1. GET  /api/v1/marketplace/products/          (Tenant Marketplace Catalog)
2. GET  /api/v1/marketplace/products/<code_or_id>/ (Product Detail)
3. POST /api/v1/marketplace/products/<code_or_id>/enable/ (Enable Product)
4. POST /api/v1/marketplace/products/<code_or_id>/request/ (Request Product)
5. GET  /api/v1/public/marketplace/products/   (Public Catalog)
"""

from typing import Any
from rest_framework import exceptions, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.access_control.views import RequireTenantContext, get_tenant_organization_from_request
from apps.entitlements.serializers import EntitlementListSerializer
from apps.identity.authentication import EnforcedSessionAuthentication
from apps.marketplace.serializers import (
    MarketplaceProductDetailSerializer,
    MarketplaceProductEnableSerializer,
    MarketplaceProductListSerializer,
    PublicMarketplaceProductSerializer,
    TenantProductRequestCreateSerializer,
    TenantProductRequestSerializer,
)
from apps.marketplace.services import (
    CrossTenantAccessError,
    DuplicateTenantProductRequestError,
    IntegrationPendingError,
    MarketplaceServiceError,
    OrganizationNotActiveError,
    PlanMismatchError,
    ProductNotActiveError,
    ProductNotFoundError,
    TenantAdminRequiredError,
    create_tenant_product_request,
    enable_marketplace_product,
    get_marketplace_catalog,
    get_marketplace_product_detail,
    get_public_marketplace_catalog,
    resolve_active_product,
)
from apps.organizations.models import MembershipStatus, MembershipType, Organization, OrganizationMembership
from apps.plans.models import PlanProduct, PlanVersion


def _verify_tenant_admin_membership(organization: Organization, user: Any) -> None:
    """Ensures caller is a Tenant Admin in the target organization, or is the Platform Owner.

    Access contract (Phase 6A Stage 5 correction):
    - Platform Owner: allowed (full catalog visibility)
    - Tenant Admin: allowed (full tenant Marketplace access)
    - Regular Member: REJECTED with TENANT_ADMIN_REQUIRED (members do not access Marketplace console)
    - Mismatched / Non-member: REJECTED with CROSS_TENANT_ACCESS_DENIED
    """
    if getattr(user, "is_platform_owner", False):
        return
    membership = OrganizationMembership.objects.filter(
        organization=organization,
        user=user,
        status=MembershipStatus.ACTIVE,
    ).first()
    if not membership:
        raise exceptions.PermissionDenied(
            {"code": "CROSS_TENANT_ACCESS_DENIED", "detail": "User has no active membership in target organization."}
        )
    if membership.membership_type != MembershipType.TENANT_ADMIN:
        raise exceptions.PermissionDenied(
            {"code": "TENANT_ADMIN_REQUIRED", "detail": "Tenant Admin access required to view the Marketplace console."}
        )


class TenantMarketplaceCatalogView(APIView):
    """Authenticated tenant-context marketplace catalog.

    Composes product, showcase, plans, entitlement state, and actionability flags.
    """

    authentication_classes = [EnforcedSessionAuthentication]
    permission_classes = [RequireTenantContext]

    def get(self, request: Any, *args: Any, **kwargs: Any) -> Response:
        org = get_tenant_organization_from_request(request)
        _verify_tenant_admin_membership(org, request.user)

        try:
            catalog = get_marketplace_catalog(organization=org, user=request.user)
        except OrganizationNotActiveError as exc:
            return Response({"code": exc.code, "detail": exc.message}, status=status.HTTP_400_BAD_REQUEST)
        except MarketplaceServiceError as exc:
            return Response({"code": exc.code, "detail": exc.message}, status=status.HTTP_400_BAD_REQUEST)

        serializer = MarketplaceProductListSerializer(catalog, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class MarketplaceProductDetailView(APIView):
    """Tenant-aware detailed product presentation in the marketplace."""

    authentication_classes = [EnforcedSessionAuthentication]
    permission_classes = [RequireTenantContext]

    def get(self, request: Any, code_or_id: str, *args: Any, **kwargs: Any) -> Response:
        org = get_tenant_organization_from_request(request)
        _verify_tenant_admin_membership(org, request.user)

        try:
            prod = resolve_active_product(code_or_id)
            detail = get_marketplace_product_detail(organization=org, product=prod, user=request.user)
        except ProductNotFoundError as exc:
            return Response({"code": exc.code, "detail": exc.message}, status=status.HTTP_404_NOT_FOUND)
        except (OrganizationNotActiveError, ProductNotActiveError, MarketplaceServiceError) as exc:
            return Response({"code": exc.code, "detail": exc.message}, status=status.HTTP_400_BAD_REQUEST)

        serializer = MarketplaceProductDetailSerializer(detail)
        return Response(serializer.data, status=status.HTTP_200_OK)


class MarketplaceProductEnableView(APIView):
    """Enables an integration-ready product for the tenant organization.

    Restricted strictly to active Tenant Administrators.
    Integration-pending products (WMS, VMS, etc.) are rejected with zero mutation.
    """

    authentication_classes = [EnforcedSessionAuthentication]
    permission_classes = [RequireTenantContext]

    def post(self, request: Any, code_or_id: str, *args: Any, **kwargs: Any) -> Response:
        org = get_tenant_organization_from_request(request)
        _verify_tenant_admin_membership(org, request.user)

        serializer = MarketplaceProductEnableSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            prod = resolve_active_product(code_or_id)

            plan_version_id = serializer.validated_data.get("plan_version_id")
            if plan_version_id:
                pv = PlanVersion.objects.filter(id=plan_version_id, status="active").first()
                if not pv:
                    return Response(
                        {"code": "PLAN_NOT_FOUND", "detail": f"Active plan version '{plan_version_id}' not found."},
                        status=status.HTTP_404_NOT_FOUND,
                    )
                if not PlanProduct.objects.filter(plan_version=pv, product=prod).exists():
                    return Response(
                        {"code": "PLAN_PRODUCT_MISMATCH", "detail": f"Plan version '{plan_version_id}' does not belong to product '{prod.code}'."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

            entitlement = enable_marketplace_product(
                organization=org,
                product=prod,
                actor=request.user,
            )
        except ProductNotFoundError as exc:
            return Response({"code": exc.code, "detail": exc.message}, status=status.HTTP_404_NOT_FOUND)
        except (TenantAdminRequiredError, CrossTenantAccessError) as exc:
            return Response({"code": exc.code, "detail": exc.message}, status=status.HTTP_403_FORBIDDEN)
        except IntegrationPendingError as exc:
            return Response({"code": exc.code, "detail": exc.message}, status=status.HTTP_422_UNPROCESSABLE_ENTITY)
        except PlanMismatchError as exc:
            return Response({"code": exc.code, "detail": exc.message}, status=status.HTTP_400_BAD_REQUEST)
        except (OrganizationNotActiveError, ProductNotActiveError, MarketplaceServiceError) as exc:
            return Response({"code": exc.code, "detail": exc.message}, status=status.HTTP_400_BAD_REQUEST)

        return Response(EntitlementListSerializer(entitlement).data, status=status.HTTP_200_OK)


class MarketplaceProductRequestView(APIView):
    """Submits a tenant product adoption request for an organization.

    Restricted strictly to active Tenant Administrators.
    """

    authentication_classes = [EnforcedSessionAuthentication]
    permission_classes = [RequireTenantContext]

    def post(self, request: Any, code_or_id: str, *args: Any, **kwargs: Any) -> Response:
        org = get_tenant_organization_from_request(request)
        _verify_tenant_admin_membership(org, request.user)

        serializer = TenantProductRequestCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            prod = resolve_active_product(code_or_id)

            requested_plan = None
            requested_plan_id = serializer.validated_data.get("requested_plan_id")
            if requested_plan_id:
                requested_plan = PlanVersion.objects.filter(id=requested_plan_id).first()
                if not requested_plan:
                    return Response(
                        {"code": "PLAN_NOT_FOUND", "detail": f"Plan version '{requested_plan_id}' not found."},
                        status=status.HTTP_404_NOT_FOUND,
                    )
                if not PlanProduct.objects.filter(plan_version=requested_plan, product=prod).exists():
                    return Response(
                        {"code": "PLAN_PRODUCT_MISMATCH", "detail": f"Plan version '{requested_plan_id}' does not belong to product '{prod.code}'."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

            req = create_tenant_product_request(
                organization=org,
                requester=request.user,
                product=prod,
                requested_plan=requested_plan,
                notes=serializer.validated_data.get("notes", ""),
            )
        except ProductNotFoundError as exc:
            return Response({"code": exc.code, "detail": exc.message}, status=status.HTTP_404_NOT_FOUND)
        except (TenantAdminRequiredError, CrossTenantAccessError) as exc:
            return Response({"code": exc.code, "detail": exc.message}, status=status.HTTP_403_FORBIDDEN)
        except DuplicateTenantProductRequestError as exc:
            return Response({"code": exc.code, "detail": exc.message}, status=status.HTTP_409_CONFLICT)
        except PlanMismatchError as exc:
            return Response({"code": exc.code, "detail": exc.message}, status=status.HTTP_400_BAD_REQUEST)
        except (OrganizationNotActiveError, ProductNotActiveError, MarketplaceServiceError) as exc:
            return Response({"code": exc.code, "detail": exc.message}, status=status.HTTP_400_BAD_REQUEST)

        return Response(TenantProductRequestSerializer(req).data, status=status.HTTP_201_CREATED)


class PublicMarketplaceCatalogView(APIView):
    """Unauthenticated public marketplace product discovery."""

    authentication_classes = []
    permission_classes = [AllowAny]
    http_method_names = ["get", "head", "options"]

    def get(self, request: Any, *args: Any, **kwargs: Any) -> Response:
        catalog = get_public_marketplace_catalog()
        serializer = PublicMarketplaceProductSerializer(catalog, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
