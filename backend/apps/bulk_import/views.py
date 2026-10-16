"""REST API Views for Bulk Import (Phase 3D)."""

import csv
import io

from django.http import HttpResponse
from rest_framework import status
from rest_framework.exceptions import PermissionDenied
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.access_control.services.evaluation import evaluate_access
from apps.bulk_import.models import BulkImportJob, BulkImportRow, BulkImportStatus, RowValidationState
from apps.bulk_import.serializers import (
    BulkImportJobSerializer,
    BulkImportRowSerializer,
    CreateBulkImportJobSerializer,
)
from apps.bulk_import.services import (
    RECOVERABLE_ERROR_CODES,
    BulkImportError,
    DuplicateJobError,
    EmptyJobError,
    MaxRowsExceededError,
    commit_import_job,
    get_job_reconciliation_report,
    parse_and_stage_job,
    retry_failed_rows,
)
from apps.notifications.queue import enqueue_background_job


class StandardResultsPagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 200


def _check_import_permission(user, organization, required_permission="bulk_import.manage"):
    """Enforce RBAC via access_control evaluation service."""
    if getattr(user, "is_platform_owner", False):
        return
    if not organization:
        raise PermissionDenied("Organization context is required.")

    eval_result = evaluate_access(user, "tenant", organization.id)
    if not eval_result.has_permission(required_permission):
        raise PermissionDenied("You do not have permission to manage bulk imports for this organization.")


class BulkImportJobCreateView(APIView):
    """Upload and parse content to create a staged bulk import job."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = CreateBulkImportJobSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        org = data["organization_id"]
        _check_import_permission(request.user, org, "bulk_import.manage")

        try:
            job = parse_and_stage_job(
                actor=request.user,
                organization=org,
                idempotency_key=data["idempotency_key"],
                raw_content=data["raw_content"],
                content_type=data.get("content_type", "csv"),
            )
            return Response(BulkImportJobSerializer(job).data, status=status.HTTP_201_CREATED)
        except DuplicateJobError as exc:
            return Response({"detail": str(exc), "code": exc.code}, status=status.HTTP_409_CONFLICT)
        except MaxRowsExceededError as exc:
            return Response({"detail": str(exc), "code": exc.code}, status=status.HTTP_400_BAD_REQUEST)
        except EmptyJobError as exc:
            return Response({"detail": str(exc), "code": exc.code}, status=status.HTTP_400_BAD_REQUEST)
        except BulkImportError as exc:
            return Response({"detail": str(exc), "code": exc.code}, status=status.HTTP_400_BAD_REQUEST)


class BulkImportJobDetailView(APIView):
    """Retrieve bulk import job status and progress summary."""

    permission_classes = [IsAuthenticated]

    def get(self, request, pk: str):
        try:
            job = BulkImportJob.objects.select_related("organization").get(id=pk)
        except BulkImportJob.DoesNotExist:
            return Response({"detail": "Job not found."}, status=status.HTTP_404_NOT_FOUND)

        _check_import_permission(request.user, job.organization, "bulk_import.view")
        return Response(BulkImportJobSerializer(job).data)


class BulkImportJobRowsView(APIView):
    """List staged rows within a bulk import job with optional state filter."""

    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsPagination

    def get(self, request, pk: str):
        try:
            job = BulkImportJob.objects.get(id=pk)
        except BulkImportJob.DoesNotExist:
            return Response({"detail": "Job not found."}, status=status.HTTP_404_NOT_FOUND)

        _check_import_permission(request.user, job.organization, "bulk_import.view")

        qs = job.rows.all().order_by("row_number")
        validation_state = request.query_params.get("validation_state")
        if validation_state:
            qs = qs.filter(validation_state=validation_state)

        paginator = self.pagination_class()
        page = paginator.paginate_queryset(qs, request)
        serializer = BulkImportRowSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)


class BulkImportJobCommitView(APIView):
    """Commit all valid rows within a staged job asynchronously."""

    permission_classes = [IsAuthenticated]

    def post(self, request, pk: str):
        try:
            job = BulkImportJob.objects.get(id=pk)
        except BulkImportJob.DoesNotExist:
            return Response({"detail": "Job not found."}, status=status.HTTP_404_NOT_FOUND)

        _check_import_permission(request.user, job.organization, "bulk_import.manage")

        if job.status not in (BulkImportStatus.VALIDATED, BulkImportStatus.FAILED):
            return Response(
                {
                    "detail": f"Cannot commit job in '{job.status}' status. Job must be 'validated' or 'failed'.",
                    "code": "INVALID_JOB_STATUS",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        job.status = BulkImportStatus.COMMITTING
        job.save(update_fields=["status", "updated_at"])

        enqueue_background_job(
            job_type="bulk_import_commit",
            payload={"job_id": str(job.id), "actor_id": str(request.user.id)},
        )

        return Response(BulkImportJobSerializer(job).data, status=status.HTTP_202_ACCEPTED)


class BulkImportJobRetryView(APIView):
    """Retry failed rows within an import job asynchronously."""

    permission_classes = [IsAuthenticated]

    def post(self, request, pk: str):
        try:
            job = BulkImportJob.objects.get(id=pk)
        except BulkImportJob.DoesNotExist:
            return Response({"detail": "Job not found."}, status=status.HTTP_404_NOT_FOUND)

        _check_import_permission(request.user, job.organization, "bulk_import.manage")

        failed_rows = job.rows.filter(
            validation_state=RowValidationState.FAILED,
            error_code__in=RECOVERABLE_ERROR_CODES,
        )
        if failed_rows.count() == 0:
            return Response(
                {
                    "detail": "No recoverable failed rows available to retry. Terminal errors cannot be retried.",
                    "code": "NO_RETRYABLE_ROWS",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        job.status = BulkImportStatus.COMMITTING
        job.save(update_fields=["status", "updated_at"])

        enqueue_background_job(
            job_type="bulk_import_retry",
            payload={"job_id": str(job.id), "actor_id": str(request.user.id)},
        )

        return Response(BulkImportJobSerializer(job).data, status=status.HTTP_202_ACCEPTED)


class BulkImportJobReconciliationView(APIView):
    """Retrieve idempotent, reproducible reconciliation report for a bulk import job."""

    permission_classes = [IsAuthenticated]

    def get(self, request, pk: str):
        try:
            job = BulkImportJob.objects.select_related("organization").get(id=pk)
        except BulkImportJob.DoesNotExist:
            return Response({"detail": "Job not found."}, status=status.HTTP_404_NOT_FOUND)

        _check_import_permission(request.user, job.organization, "bulk_import.view")

        report = get_job_reconciliation_report(job.id)
        return Response(report, status=status.HTTP_200_OK)


class BulkImportJobErrorReportView(APIView):
    """Export invalid and failed rows for an import job as CSV download."""

    permission_classes = [IsAuthenticated]

    def get(self, request, pk: str):
        try:
            job = BulkImportJob.objects.select_related("organization").get(id=pk)
        except BulkImportJob.DoesNotExist:
            return Response({"detail": "Job not found."}, status=status.HTTP_404_NOT_FOUND)

        _check_import_permission(request.user, job.organization, "bulk_import.view")

        error_rows = job.rows.filter(
            validation_state__in=[RowValidationState.INVALID, RowValidationState.FAILED]
        ).order_by("row_number")

        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow([
            "row_number",
            "email",
            "full_name",
            "role_code",
            "membership_type",
            "validation_state",
            "error_code",
            "error_message",
        ])

        for row in error_rows:
            p = row.payload_ref
            writer.writerow([
                row.row_number,
                p.get("email", ""),
                p.get("full_name", ""),
                p.get("role_code", ""),
                p.get("membership_type", ""),
                row.validation_state,
                row.error_code,
                row.error_message,
            ])

        response = HttpResponse(buffer.getvalue(), content_type="text/csv")
        response["Content-Disposition"] = f'attachment; filename="bulk_import_{job.id}_errors.csv"'
        return response
