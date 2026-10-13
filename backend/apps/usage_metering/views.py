from rest_framework import exceptions, status
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.access_control.constants import CONTEXT_TENANT
from apps.access_control.services.evaluation import evaluate_access
from apps.organizations.models import MembershipStatus, Organization, OrganizationMembership
from apps.product_registry.models import Product
from apps.usage_metering.models import UsageBucket
from apps.usage_metering.serializers import UsageEventIngestionSerializer, UsageSummarySerializer
from apps.usage_metering.services import ingest_usage_event


class UsagePagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


def _check_usage_view_permission(user, org: Organization) -> None:
    if not user or not user.is_authenticated:
        raise exceptions.NotAuthenticated()
    if getattr(user, "is_platform_owner", False):
        return
    eval_result = evaluate_access(user, CONTEXT_TENANT, org.id)
    if not eval_result.has_permission("usage.view"):
        raise exceptions.PermissionDenied("Actor lacks required permission 'usage.view'.")


class UsageEventIngestionView(APIView):
    """POST /api/v1/usage/events/
    
    Idempotent usage ingestion endpoint.
    Org-scoped, authenticated service / client only.
    Duplicate event_key is a no-op 200 response, not an error.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        serializer = UsageEventIngestionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        org = Organization.objects.filter(id=data["organization_id"]).first()
        if not org:
            return Response({"detail": "Organization not found."}, status=status.HTTP_404_NOT_FOUND)

        product = None
        if data.get("product_code"):
            product = Product.objects.filter(code=data["product_code"]).first()

        event, created = ingest_usage_event(
            organization=org,
            meter_key=data["meter_key"],
            quantity=data["quantity"],
            event_key=data["event_key"],
            product=product,
        )

        if not created:
            return Response(
                {
                    "status": "duplicate",
                    "detail": "Event already recorded.",
                    "event_id": str(event.id),
                    "event_key": event.event_key,
                },
                status=status.HTTP_200_OK,
            )

        return Response(
            {
                "status": "recorded",
                "event_id": str(event.id),
                "event_key": event.event_key,
            },
            status=status.HTTP_201_CREATED,
        )


class TenantUsageSummaryView(APIView):
    """GET /api/v1/tenant/usage/
    
    Org-scoped summary for the tenant dashboard usage card.
    Gated by usage.view.
    Empty state returns [] without error.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        user = request.user
        org_id = request.query_params.get("organization_id")
        if org_id:
            membership = OrganizationMembership.objects.filter(
                user=user,
                organization_id=org_id,
                status=MembershipStatus.ACTIVE,
            ).first()
            if not membership and not getattr(user, "is_platform_owner", False):
                raise exceptions.PermissionDenied("Not an active member of specified organization.")
            org = Organization.objects.filter(id=org_id).first()
        else:
            membership = OrganizationMembership.objects.filter(
                user=user,
                status=MembershipStatus.ACTIVE,
            ).first()
            if not membership and not getattr(user, "is_platform_owner", False):
                raise exceptions.PermissionDenied("No active organization membership found.")
            org = membership.organization if membership else Organization.objects.first()

        if not org:
            return Response([], status=status.HTTP_200_OK)

        _check_usage_view_permission(user, org)

        buckets = (
            UsageBucket.objects.filter(organization=org)
            .select_related("meter", "organization")
            .order_by("-period_start", "meter__quota_key")
        )

        # Return latest bucket per meter
        seen_meters = set()
        latest_buckets = []
        for b in buckets:
            if b.meter_id not in seen_meters:
                seen_meters.add(b.meter_id)
                latest_buckets.append(b)

        return Response(UsageSummarySerializer(latest_buckets, many=True).data, status=status.HTTP_200_OK)


class OwnerUsageListView(APIView):
    """GET /api/v1/usage/
    
    Platform owner cross-tenant paginated list of usage buckets.
    """
    permission_classes = [IsAuthenticated]
    pagination_class = UsagePagination

    def get(self, request: Request) -> Response:
        if not getattr(request.user, "is_platform_owner", False):
            raise exceptions.PermissionDenied("Platform owner privileges required.")

        buckets = (
            UsageBucket.objects.all()
            .select_related("meter", "organization")
            .order_by("-period_start", "organization__name")
        )
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(buckets, request)
        serializer = UsageSummarySerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)
