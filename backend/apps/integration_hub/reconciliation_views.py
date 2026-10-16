"""LMS Reconciliation API Views (Phase 5D).

Endpoints:
- GET  /api/v1/integration/reconciliation/
- POST /api/v1/integration/reconciliation/run/
- POST /api/v1/integration/reconciliation/<uuid:issue_id>/resolve/
"""

from rest_framework import exceptions, status
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.integration_hub.models import (
    IntegrationReconciliationIssue,
    IntegrationReconciliationStatus,
)
from apps.integration_hub.reconciliation_service import (
    resolve_lms_reconciliation,
    run_lms_reconciliation,
)
from apps.integration_hub.serializers import (
    IntegrationReconciliationIssueSerializer,
    ResolveIntegrationIssueSerializer,
)


class StandardReconciliationPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


class LmsReconciliationListView(APIView):
    """GET /api/v1/integration/reconciliation/

    Lists reviewable LMS reconciliation issues for platform owners.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        if not getattr(request.user, "is_platform_owner", False):
            raise exceptions.PermissionDenied("Platform owner privileges required.")

        qs = IntegrationReconciliationIssue.objects.select_related(
            "instance",
            "instance__connector",
            "resolved_by",
        ).order_by("-detected_at")

        status_param = request.query_params.get("status")
        if status_param:
            qs = qs.filter(status=status_param.upper())

        instance_id = request.query_params.get("instance_id")
        if instance_id:
            qs = qs.filter(instance_id=instance_id)

        issue_code = request.query_params.get("issue_code")
        if issue_code:
            qs = qs.filter(issue_code=issue_code)

        paginator = StandardReconciliationPagination()
        page = paginator.paginate_queryset(qs, request)
        if page is not None:
            return paginator.get_paginated_response(
                IntegrationReconciliationIssueSerializer(page, many=True).data
            )

        return Response(IntegrationReconciliationIssueSerializer(qs, many=True).data)


class LmsReconciliationTriggerView(APIView):
    """POST /api/v1/integration/reconciliation/run/

    Triggers read-only LMS reconciliation across connector instances.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        if not getattr(request.user, "is_platform_owner", False):
            raise exceptions.PermissionDenied("Platform owner privileges required.")

        instance_id = request.data.get("instance_id")
        detected = run_lms_reconciliation(instance_id=instance_id)

        open_count = IntegrationReconciliationIssue.objects.filter(
            status=IntegrationReconciliationStatus.OPEN
        ).count()

        return Response(
            {
                "detected_count": len(detected),
                "open_issues_count": open_count,
                "issues": IntegrationReconciliationIssueSerializer(detected, many=True).data,
            },
            status=status.HTTP_200_OK,
        )


class LmsReconciliationResolveView(APIView):
    """POST /api/v1/integration/reconciliation/<uuid:issue_id>/resolve/

    Marks an issue as resolved with required audit notes.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request: Request, issue_id: str) -> Response:
        if not getattr(request.user, "is_platform_owner", False):
            raise exceptions.PermissionDenied("Platform owner privileges required.")

        serializer = ResolveIntegrationIssueSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        notes = serializer.validated_data["resolution_notes"]

        try:
            issue = resolve_lms_reconciliation(
                issue_id=str(issue_id),
                resolved_by_user=request.user,
                resolution_notes=notes,
            )
        except IntegrationReconciliationIssue.DoesNotExist:
            return Response(
                {"detail": "Reconciliation issue not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response(
            IntegrationReconciliationIssueSerializer(issue).data,
            status=status.HTTP_200_OK,
        )
