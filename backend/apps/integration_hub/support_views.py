"""Support Console Diagnostic Views (Phase 6C-2).

Authoritative read-only diagnostic workspace endpoints for Support Operators.
Gated strictly with Phase 6C-1 support permissions.
Reuses existing Integration Hub, 5G failure, and reconciliation calculation services.
Zero new source-of-truth tables. Zero secret exposure.
"""

from datetime import timedelta
import logging
import uuid

from django.db.models import Q
from django.utils import timezone
from rest_framework import exceptions, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.access_control.constants import (
    PERMISSION_SUPPORT_DIAGNOSTICS_VIEW,
    PERMISSION_SUPPORT_OPERATIONS_RESOLVE,
    PERMISSION_SUPPORT_OPERATIONS_RETRY,
)
from apps.access_control.permissions import HasSupportPermission
from apps.auditlog.models import (
    AuditLog,
    AuditOperationSource,
    AuditTargetType,
)
from apps.integration_hub.models import (
    ConnectorInstance,
    FailureStatus,
    InstanceStatus,
    IntegrationFailure,
    IntegrationReconciliationIssue,
    IntegrationReconciliationStatus,
    ProvisioningJob,
    ProvisioningJobStatus,
)
from apps.integration_hub.reconciliation_service import resolve_lms_reconciliation
from apps.integration_hub.retry_service import (
    replay_dead_letter_failure,
    resolve_failure,
    schedule_failure_retry,
)
from apps.integration_hub.stuck_job_service import detect_stuck_provisioning_jobs
from apps.integration_hub.support_serializers import (
    SupportAuditEntrySerializer,
    SupportConnectorInstanceDiagnosticSerializer,
    SupportFailureDiagnosticSerializer,
    SupportOrganizationSummarySerializer,
    SupportReconciliationIssueSerializer,
)

from apps.organizations.models import Organization

logger = logging.getLogger(__name__)


class SupportOrganizationLookupView(APIView):
    """GET /api/v1/support/organizations/

    Allows authorized Support Operators to look up organizations by query string
    to inspect their diagnostic state. Bounded to 20 results.
    Gated strictly with support.diagnostics.view.
    """

    permission_classes = [IsAuthenticated, HasSupportPermission]
    required_console_permission = PERMISSION_SUPPORT_DIAGNOSTICS_VIEW

    def get(self, request: Request) -> Response:
        search_query = (
            request.query_params.get("q")
            or request.query_params.get("search")
            or ""
        ).strip()

        qs = Organization.objects.all().order_by("name")

        if search_query:
            # Check if query is a UUID
            is_uuid = False
            try:
                uuid.UUID(search_query)
                is_uuid = True
            except ValueError:
                pass

            if is_uuid:
                qs = qs.filter(id=search_query)
            else:
                qs = qs.filter(
                    Q(name__icontains=search_query)
                    | Q(code__icontains=search_query)
                )

        limited_orgs = list(qs[:20])
        return Response(
            SupportOrganizationSummarySerializer(limited_orgs, many=True).data,
            status=status.HTTP_200_OK,
        )


class OrganizationDiagnosticsView(APIView):
    """GET /api/v1/support/organizations/<uuid:organization_id>/diagnostics/

    Unified diagnostic inspection for a single organization.
    Aggregates:
    - Organization lifecycle status
    - Connector instances & their status
    - Integration health summary (reused deterministic status calculation)
    - Stuck and orphaned provisioning jobs (via detect_stuck_provisioning_jobs)
    - Active failures & dead-letter records
    - Open reconciliation issues
    - Recent operational audit log entries

    Gated strictly with support.diagnostics.view.
    """

    permission_classes = [IsAuthenticated, HasSupportPermission]
    required_console_permission = PERMISSION_SUPPORT_DIAGNOSTICS_VIEW

    def get(self, request: Request, organization_id: uuid.UUID) -> Response:
        try:
            org = Organization.objects.get(id=organization_id)
        except Organization.DoesNotExist:
            return Response(
                {"detail": f"Organization '{organization_id}' not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # 1. Organization Summary
        org_data = SupportOrganizationSummarySerializer(org).data

        # 2. Connector Instances (credential_ref & config stripped)
        instances_qs = ConnectorInstance.objects.filter(
            organization=org
        ).select_related("connector").order_by("created_at")
        instances_data = SupportConnectorInstanceDiagnosticSerializer(
            instances_qs, many=True
        ).data

        total_instances = instances_qs.count()
        active_instances = instances_qs.filter(status=InstanceStatus.ACTIVE).count()
        suspended_instances = instances_qs.filter(status=InstanceStatus.SUSPENDED).count()
        disconnected_instances = instances_qs.filter(status=InstanceStatus.DISCONNECTED).count()

        # 3. Failures breakdown
        failures_qs = (
            IntegrationFailure.objects.filter(
                IntegrationFailure.org_scope_filter(org)
            )
            .distinct()
            .select_related(
                "job",
                "job__instance",
                "job__instance__connector",
                "event",
                "event__instance",
                "event__instance__connector",
            )
        )

        dead_letter_failures = failures_qs.filter(status=FailureStatus.DEAD_LETTER).order_by("-created_at")
        open_failures = failures_qs.filter(status=FailureStatus.OPEN).order_by("-created_at")
        retry_scheduled_failures = failures_qs.filter(status=FailureStatus.RETRY_SCHEDULED).order_by("-created_at")
        resolved_failures = failures_qs.filter(status=FailureStatus.RESOLVED).order_by("-resolved_at")

        total_dead_letter = dead_letter_failures.count()
        total_open = open_failures.count()
        total_retry_scheduled = retry_scheduled_failures.count()
        total_resolved = resolved_failures.count()

        since_24h = timezone.now() - timedelta(hours=24)
        recent_24h_failures = failures_qs.filter(created_at__gte=since_24h).count()

        # 4. Jobs & Stuck Detection (Reused stuck_job_service)
        jobs_qs = ProvisioningJob.objects.filter(organization=org)
        total_queued_jobs = jobs_qs.filter(status=ProvisioningJobStatus.QUEUED).count()
        total_processing_jobs = jobs_qs.filter(status=ProvisioningJobStatus.PROCESSING).count()
        total_failed_jobs = jobs_qs.filter(status=ProvisioningJobStatus.FAILED).count()
        total_completed_jobs = jobs_qs.filter(status=ProvisioningJobStatus.COMPLETED).count()

        stuck_results = detect_stuck_provisioning_jobs(
            organization_id=org.id,
            limit=50,
        )
        stuck_summary = stuck_results.get("summary", {})
        stuck_queued_count = stuck_summary.get("stuck_queued", 0)
        stuck_processing_count = stuck_summary.get("stuck_processing", 0)
        orphaned_job_count = stuck_summary.get("orphaned", 0)

        # 5. Deterministic Control Plane Status (Identical logic to IntegrationHealthSummaryView lines 581-593)
        if (
            total_dead_letter > 0
            or stuck_queued_count > 0
            or stuck_processing_count > 0
            or orphaned_job_count > 0
            or disconnected_instances > 0
        ):
            control_plane_status = "attention_required"
        elif total_open > 0 or suspended_instances > 0 or total_retry_scheduled > 0:
            control_plane_status = "degraded"
        else:
            control_plane_status = "healthy"

        # 6. Open Reconciliation Issues
        reconciliation_qs = IntegrationReconciliationIssue.objects.filter(
            instance__organization=org,
            status=IntegrationReconciliationStatus.OPEN,
        ).select_related("instance", "instance__connector").order_by("-detected_at")
        reconciliation_data = SupportReconciliationIssueSerializer(
            reconciliation_qs[:50], many=True
        ).data

        # 7. Recent Audit Log Entries (PII-minimized)
        audit_qs = AuditLog.objects.filter(
            organization_id=org.id
        ).order_by("-timestamp")[:25]
        audit_data = SupportAuditEntrySerializer(audit_qs, many=True).data

        # 8. Assemble response
        return Response(
            {
                "organization": org_data,
                "health": {
                    "control_plane_status": control_plane_status,
                    "instances": {
                        "total": total_instances,
                        "active": active_instances,
                        "suspended": suspended_instances,
                        "disconnected": disconnected_instances,
                    },
                    "failures": {
                        "open": total_open,
                        "retry_scheduled": total_retry_scheduled,
                        "dead_letter": total_dead_letter,
                        "resolved": total_resolved,
                        "last_24h": recent_24h_failures,
                    },
                    "jobs": {
                        "queued": total_queued_jobs,
                        "processing": total_processing_jobs,
                        "failed": total_failed_jobs,
                        "completed": total_completed_jobs,
                        "stuck_queued": stuck_queued_count,
                        "stuck_processing": stuck_processing_count,
                        "orphaned": orphaned_job_count,
                    },
                    "open_reconciliation_issues_count": reconciliation_qs.count(),
                },
                "connector_instances": instances_data,
                "stuck_jobs": stuck_results.get("stuck_jobs", []),
                "dead_letter_failures": SupportFailureDiagnosticSerializer(
                    dead_letter_failures[:50], many=True
                ).data,
                "open_failures": SupportFailureDiagnosticSerializer(
                    (open_failures | retry_scheduled_failures).order_by("-created_at")[:50],
                    many=True,
                ).data,
                "recent_resolved_failures": SupportFailureDiagnosticSerializer(
                    resolved_failures[:20], many=True
                ).data,
                "reconciliation_issues": reconciliation_data,
                "recent_audit_logs": audit_data,
            },
            status=status.HTTP_200_OK,
        )


# ── 6C-4: Controlled Operational Remediation Endpoints ──────────────────────


class SupportFailureRetryView(APIView):
    """POST /api/v1/support/organizations/<uuid:organization_id>/failures/<uuid:failure_id>/retry/

    Gated strictly with support.operations.retry.
    Reuses schedule_failure_retry from 5G retry service.
    Enforces server-side transition validation, tenant boundary scoping, and validated reason.
    """

    permission_classes = [IsAuthenticated, HasSupportPermission]
    required_console_permission = PERMISSION_SUPPORT_OPERATIONS_RETRY

    def post(
        self, request: Request, organization_id: uuid.UUID, failure_id: uuid.UUID
    ) -> Response:
        raw_reason = request.data.get("reason") or request.data.get("resolution_notes") or ""
        reason = str(raw_reason).strip()
        if not (1 <= len(reason) <= 500):
            return Response(
                {"detail": "Operational reason must be between 1 and 500 characters."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        failure = (
            IntegrationFailure.objects.filter(
                IntegrationFailure.org_scope_filter(organization_id),
                pk=failure_id,
            )
            .select_related(
                "job",
                "job__instance",
                "job__instance__connector",
                "event",
                "event__instance",
                "event__instance__connector",
            )
            .first()
        )
        if not failure:
            return Response(
                {"detail": f"Integration failure '{failure_id}' not found for organization."},
                status=status.HTTP_404_NOT_FOUND,
            )

        if failure.status == FailureStatus.DEAD_LETTER:
            return Response(
                {"detail": "Cannot directly retry DEAD_LETTER failure; use replay endpoint."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if failure.status == FailureStatus.RESOLVED:
            return Response(
                {"detail": "Cannot retry a RESOLVED failure."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if failure.retry_count >= failure.max_retries:
            return Response(
                {"detail": "Maximum retry limit reached for this failure."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            updated = schedule_failure_retry(failure)
        except ValueError as err:
            return Response({"detail": str(err)}, status=status.HTTP_400_BAD_REQUEST)

        # Audit remediation action with real operator identity
        AuditLog.objects.create(
            action="support_failure_retry_scheduled",
            target_type=AuditTargetType.MODULE,
            target_id=failure.id,
            target_repr=f"Failure {failure.failure_code}",
            organization_id=organization_id,
            actor=request.user,
            actor_email=getattr(request.user, "email", ""),
            actor_name=getattr(request.user, "full_name", "") or getattr(request.user, "email", ""),
            operation_source=AuditOperationSource.INTERACTIVE,
            metadata={
                "operator_email": getattr(request.user, "email", ""),
                "reason": reason,
                "retry_count": updated.retry_count,
                "status": updated.status,
            },
        )

        return Response(
            SupportFailureDiagnosticSerializer(updated).data,
            status=status.HTTP_200_OK,
        )


class SupportFailureReplayView(APIView):
    """POST /api/v1/support/organizations/<uuid:organization_id>/failures/<uuid:failure_id>/replay/

    Gated strictly with support.operations.retry.
    Reuses replay_dead_letter_failure from 5G retry service.
    Enforces server-side transition validation, tenant boundary scoping, and validated reason.
    """

    permission_classes = [IsAuthenticated, HasSupportPermission]
    required_console_permission = PERMISSION_SUPPORT_OPERATIONS_RETRY

    def post(
        self, request: Request, organization_id: uuid.UUID, failure_id: uuid.UUID
    ) -> Response:
        raw_reason = request.data.get("reason") or request.data.get("resolution_notes") or ""
        reason = str(raw_reason).strip()
        if not (1 <= len(reason) <= 500):
            return Response(
                {"detail": "Operational reason must be between 1 and 500 characters."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        failure = (
            IntegrationFailure.objects.filter(
                IntegrationFailure.org_scope_filter(organization_id),
                pk=failure_id,
            )
            .select_related(
                "job",
                "job__instance",
                "job__instance__connector",
                "event",
                "event__instance",
                "event__instance__connector",
            )
            .first()
        )
        if not failure:
            return Response(
                {"detail": f"Integration failure '{failure_id}' not found for organization."},
                status=status.HTTP_404_NOT_FOUND,
            )

        if failure.status != FailureStatus.DEAD_LETTER:
            return Response(
                {"detail": f"Only DEAD_LETTER failures can be replayed (current status: '{failure.status}')."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not failure.job_id:
            return Response(
                {"detail": "Only failures associated with a provisioning job can be replayed."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Explicitly grant operator context for replay invocation
        setattr(request.user, "_is_support_operator", True)
        try:
            updated = replay_dead_letter_failure(failure_id=failure.id, actor=request.user)
        except (ValueError, PermissionError) as err:
            return Response({"detail": str(err)}, status=status.HTTP_400_BAD_REQUEST)

        AuditLog.objects.create(
            action="support_dead_letter_replayed",
            target_type=AuditTargetType.MODULE,
            target_id=failure.id,
            target_repr=f"Dead-Letter Failure {failure.failure_code}",
            organization_id=organization_id,
            actor=request.user,
            actor_email=getattr(request.user, "email", ""),
            actor_name=getattr(request.user, "full_name", "") or getattr(request.user, "email", ""),
            operation_source=AuditOperationSource.INTERACTIVE,
            metadata={
                "operator_email": getattr(request.user, "email", ""),
                "reason": reason,
                "status": updated.status,
            },
        )

        return Response(
            SupportFailureDiagnosticSerializer(updated).data,
            status=status.HTTP_200_OK,
        )


class SupportFailureResolveView(APIView):
    """POST /api/v1/support/organizations/<uuid:organization_id>/failures/<uuid:failure_id>/resolve/

    Gated strictly with support.operations.resolve.
    Reuses resolve_failure from 5G retry service.
    Requires mandatory 1–500 char trimmed resolution reason.
    """

    permission_classes = [IsAuthenticated, HasSupportPermission]
    required_console_permission = PERMISSION_SUPPORT_OPERATIONS_RESOLVE

    def post(
        self, request: Request, organization_id: uuid.UUID, failure_id: uuid.UUID
    ) -> Response:
        raw_reason = request.data.get("resolution_notes") or request.data.get("reason") or ""
        reason = str(raw_reason).strip()
        if not (1 <= len(reason) <= 500):
            return Response(
                {"detail": "Resolution reason must be between 1 and 500 characters."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        failure = (
            IntegrationFailure.objects.filter(
                IntegrationFailure.org_scope_filter(organization_id),
                pk=failure_id,
            )
            .select_related(
                "job",
                "job__instance",
                "job__instance__connector",
                "event",
                "event__instance",
                "event__instance__connector",
            )
            .first()
        )
        if not failure:
            return Response(
                {"detail": f"Integration failure '{failure_id}' not found for organization."},
                status=status.HTTP_404_NOT_FOUND,
            )

        if failure.status == FailureStatus.RESOLVED:
            return Response(
                {"detail": "Failure is already in RESOLVED status."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            updated = resolve_failure(failure, user=request.user, notes=reason)
        except ValueError as err:
            return Response({"detail": str(err)}, status=status.HTTP_400_BAD_REQUEST)

        AuditLog.objects.create(
            action="support_failure_resolved",
            target_type=AuditTargetType.MODULE,
            target_id=failure.id,
            target_repr=f"Failure {failure.failure_code}",
            organization_id=organization_id,
            actor=request.user,
            actor_email=getattr(request.user, "email", ""),
            actor_name=getattr(request.user, "full_name", "") or getattr(request.user, "email", ""),
            operation_source=AuditOperationSource.INTERACTIVE,
            metadata={
                "operator_email": getattr(request.user, "email", ""),
                "resolution_notes": reason,
                "status": updated.status,
            },
        )

        return Response(
            SupportFailureDiagnosticSerializer(updated).data,
            status=status.HTTP_200_OK,
        )


class SupportReconciliationResolveView(APIView):
    """POST /api/v1/support/organizations/<uuid:organization_id>/reconciliation/<uuid:issue_id>/resolve/

    Gated strictly with support.operations.resolve.
    Reuses resolve_lms_reconciliation from reconciliation service.
    Requires mandatory 1–500 char trimmed resolution reason.
    """

    permission_classes = [IsAuthenticated, HasSupportPermission]
    required_console_permission = PERMISSION_SUPPORT_OPERATIONS_RESOLVE

    def post(
        self, request: Request, organization_id: uuid.UUID, issue_id: uuid.UUID
    ) -> Response:
        raw_reason = request.data.get("resolution_notes") or request.data.get("reason") or ""
        reason = str(raw_reason).strip()
        if not (1 <= len(reason) <= 500):
            return Response(
                {"detail": "Resolution notes must be between 1 and 500 characters."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        issue = (
            IntegrationReconciliationIssue.objects.select_related("instance")
            .filter(pk=issue_id, instance__organization_id=organization_id)
            .first()
        )
        if not issue:
            return Response(
                {"detail": f"Reconciliation issue '{issue_id}' not found for organization."},
                status=status.HTTP_404_NOT_FOUND,
            )

        if issue.status == IntegrationReconciliationStatus.RESOLVED:
            return Response(
                {"detail": "Reconciliation issue is already resolved."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            updated = resolve_lms_reconciliation(
                issue_id=str(issue.id),
                resolved_by_user=request.user,
                resolution_notes=reason,
            )
        except Exception as err:
            return Response({"detail": str(err)}, status=status.HTTP_400_BAD_REQUEST)

        AuditLog.objects.create(
            action="support_reconciliation_resolved",
            target_type=AuditTargetType.MODULE,
            target_id=issue.id,
            target_repr=f"Reconciliation Issue {issue.issue_code}",
            organization_id=organization_id,
            actor=request.user,
            actor_email=getattr(request.user, "email", ""),
            actor_name=getattr(request.user, "full_name", "") or getattr(request.user, "email", ""),
            operation_source=AuditOperationSource.INTERACTIVE,
            metadata={
                "operator_email": getattr(request.user, "email", ""),
                "resolution_notes": reason,
                "status": updated.status,
            },
        )

        return Response(
            SupportReconciliationIssueSerializer(updated).data,
            status=status.HTTP_200_OK,
        )

