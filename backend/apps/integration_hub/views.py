"""Integration Hub Views (Phase 5A + 5B).

Owner-only endpoints. No tenant-facing UI in this phase.
"""

from datetime import timedelta
import logging

from django.db import IntegrityError
from django.db.models import Q
from django.utils import timezone
from rest_framework import exceptions, status
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.integration_hub.models import (
    ConnectorInstance,
    ExternalIdentity,
    ExternalTenantMapping,
    ExternalUserMapping,
    FailureStatus,
    FailureType,
    InstanceStatus,
    IntegrationConnector,
    IntegrationEvent,
    IntegrationFailure,
    ProvisioningJob,
)
from apps.integration_hub.retry_service import (
    mark_failure_dead_letter,
    replay_dead_letter_failure,
    resolve_failure,
    schedule_failure_retry,
)
from apps.integration_hub.serializers import (
    ConnectorInstanceSerializer,
    ExternalIdentitySerializer,
    ExternalTenantMappingSerializer,
    ExternalUserMappingSerializer,
    FailureDeadLetterRequestSerializer,
    FailureResolveRequestSerializer,
    IntegrationConnectorSerializer,
    IntegrationEventIngestSerializer,
    IntegrationEventSerializer,
    IntegrationFailureSerializer,
    ProvisioningJobSerializer,
)

logger = logging.getLogger(__name__)


def _require_owner(user) -> None:
    if not user or not user.is_authenticated:
        raise exceptions.NotAuthenticated()
    if not getattr(user, "is_platform_owner", False):
        raise exceptions.PermissionDenied("Platform owner privileges required.")


class HubPagination(PageNumberPagination):
    page_size = 25
    page_size_query_param = "page_size"
    max_page_size = 100


# ── 5A: Connector Registry ────────────────────────────────────────────────────


class ConnectorListView(APIView):
    """GET /api/v1/integration/connectors/   — list
    POST /api/v1/integration/connectors/   — create
    """
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        _require_owner(request.user)
        qs = IntegrationConnector.objects.all().select_related("product")
        serializer = IntegrationConnectorSerializer(qs, many=True)
        return Response(serializer.data)

    def post(self, request: Request) -> Response:
        _require_owner(request.user)
        serializer = IntegrationConnectorSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class ConnectorDetailView(APIView):
    """GET/PATCH/DELETE /api/v1/integration/connectors/<pk>/"""
    permission_classes = [IsAuthenticated]

    def _get_obj(self, pk: str) -> IntegrationConnector:
        try:
            return IntegrationConnector.objects.get(pk=pk)
        except IntegrationConnector.DoesNotExist:
            raise exceptions.NotFound("Connector not found.")

    def get(self, request: Request, pk: str) -> Response:
        _require_owner(request.user)
        return Response(IntegrationConnectorSerializer(self._get_obj(pk)).data)

    def patch(self, request: Request, pk: str) -> Response:
        _require_owner(request.user)
        obj = self._get_obj(pk)
        serializer = IntegrationConnectorSerializer(obj, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    def delete(self, request: Request, pk: str) -> Response:
        _require_owner(request.user)
        obj = self._get_obj(pk)
        obj.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


# ── 5A: Connector Instances ───────────────────────────────────────────────────


class InstanceListView(APIView):
    """GET/POST /api/v1/integration/instances/"""
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        _require_owner(request.user)
        qs = ConnectorInstance.objects.all().select_related("connector", "organization")
        paginator = HubPagination()
        page = paginator.paginate_queryset(qs, request)
        return paginator.get_paginated_response(ConnectorInstanceSerializer(page, many=True).data)

    def post(self, request: Request) -> Response:
        _require_owner(request.user)
        serializer = ConnectorInstanceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class InstanceDetailView(APIView):
    """GET/PATCH/DELETE /api/v1/integration/instances/<pk>/"""
    permission_classes = [IsAuthenticated]

    def _get_obj(self, pk: str) -> ConnectorInstance:
        try:
            return ConnectorInstance.objects.select_related("connector", "organization").get(pk=pk)
        except ConnectorInstance.DoesNotExist:
            raise exceptions.NotFound("Connector instance not found.")

    def get(self, request: Request, pk: str) -> Response:
        _require_owner(request.user)
        return Response(ConnectorInstanceSerializer(self._get_obj(pk)).data)

    def patch(self, request: Request, pk: str) -> Response:
        _require_owner(request.user)
        obj = self._get_obj(pk)
        serializer = ConnectorInstanceSerializer(obj, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    def delete(self, request: Request, pk: str) -> Response:
        _require_owner(request.user)
        obj = self._get_obj(pk)
        obj.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


# ── 5A: Event Ingestion (idempotent) ─────────────────────────────────────────


class EventIngestView(APIView):
    """POST /api/v1/integration/events/ingest/

    Idempotent: if event_key already exists, returns the existing record (200).
    Rejects events referencing an unknown instance (404).
    """
    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        _require_owner(request.user)
        event_key = request.data.get("event_key")
        if not event_key:
            raise exceptions.ValidationError({"event_key": "This field is required."})

        # Idempotency check
        existing = IntegrationEvent.objects.filter(event_key=event_key).first()
        if existing:
            return Response(IntegrationEventSerializer(existing).data, status=status.HTTP_200_OK)

        # Validate instance exists
        instance_id = request.data.get("instance")
        if not instance_id:
            raise exceptions.ValidationError({"instance": "This field is required."})
        try:
            ConnectorInstance.objects.get(pk=instance_id)
        except ConnectorInstance.DoesNotExist:
            logger.warning("EventIngest: unknown instance %s for event_key=%s", instance_id, event_key)
            raise exceptions.NotFound("Connector instance not found; event rejected.")

        serializer = IntegrationEventIngestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        event = serializer.save()
        return Response(IntegrationEventSerializer(event).data, status=status.HTTP_201_CREATED)


class EventListView(APIView):
    """GET /api/v1/integration/events/"""
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        _require_owner(request.user)
        qs = IntegrationEvent.objects.select_related("instance").order_by("-occurred_at")
        paginator = HubPagination()
        page = paginator.paginate_queryset(qs, request)
        return paginator.get_paginated_response(IntegrationEventSerializer(page, many=True).data)


# ── 5A: Provisioning Jobs ─────────────────────────────────────────────────────


class ProvisioningJobListView(APIView):
    """GET /api/v1/integration/provisioning-jobs/"""
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        _require_owner(request.user)
        qs = ProvisioningJob.objects.select_related("instance", "organization", "user").order_by("-created_at")
        paginator = HubPagination()
        page = paginator.paginate_queryset(qs, request)
        return paginator.get_paginated_response(ProvisioningJobSerializer(page, many=True).data)


class ProvisioningJobDetailView(APIView):
    """GET /api/v1/integration/provisioning-jobs/<pk>/"""
    permission_classes = [IsAuthenticated]

    def get(self, request: Request, pk: str) -> Response:
        _require_owner(request.user)
        try:
            job = ProvisioningJob.objects.select_related("instance", "organization", "user").get(pk=pk)
        except ProvisioningJob.DoesNotExist:
            raise exceptions.NotFound("Provisioning job not found.")
        return Response(ProvisioningJobSerializer(job).data)


# ── 5B: External Identity Mappings ────────────────────────────────────────────


class ExternalIdentityListView(APIView):
    """GET/POST /api/v1/integration/external-identities/"""
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        _require_owner(request.user)
        qs = ExternalIdentity.objects.select_related("user").order_by("provider", "provider_tenant")
        paginator = HubPagination()
        page = paginator.paginate_queryset(qs, request)
        return paginator.get_paginated_response(ExternalIdentitySerializer(page, many=True).data)

    def post(self, request: Request) -> Response:
        _require_owner(request.user)
        serializer = ExternalIdentitySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            obj = serializer.save()
        except IntegrityError:
            raise exceptions.ValidationError(
                {"non_field_errors": ["An external identity with this provider/tenant/subject already exists."]}
            )
        return Response(ExternalIdentitySerializer(obj).data, status=status.HTTP_201_CREATED)


class ExternalTenantMappingListView(APIView):
    """GET/POST /api/v1/integration/tenant-mappings/"""
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        _require_owner(request.user)
        instance_id = request.query_params.get("instance")
        qs = ExternalTenantMapping.objects.select_related("organization", "instance")
        if instance_id:
            qs = qs.filter(instance_id=instance_id)
        paginator = HubPagination()
        page = paginator.paginate_queryset(qs, request)
        return paginator.get_paginated_response(ExternalTenantMappingSerializer(page, many=True).data)

    def post(self, request: Request) -> Response:
        _require_owner(request.user)
        serializer = ExternalTenantMappingSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            obj = serializer.save()
        except IntegrityError:
            raise exceptions.ValidationError(
                {"non_field_errors": ["A tenant mapping for this instance/organization already exists."]}
            )
        return Response(ExternalTenantMappingSerializer(obj).data, status=status.HTTP_201_CREATED)


class ExternalUserMappingListView(APIView):
    """GET/POST /api/v1/integration/user-mappings/"""
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        _require_owner(request.user)
        instance_id = request.query_params.get("instance")
        qs = ExternalUserMapping.objects.select_related("user", "organization", "instance")
        if instance_id:
            qs = qs.filter(instance_id=instance_id)
        paginator = HubPagination()
        page = paginator.paginate_queryset(qs, request)
        return paginator.get_paginated_response(ExternalUserMappingSerializer(page, many=True).data)

    def post(self, request: Request) -> Response:
        _require_owner(request.user)
        serializer = ExternalUserMappingSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            obj = serializer.save()
        except IntegrityError:
            raise exceptions.ValidationError(
                {"non_field_errors": ["A user mapping with this instance/external_user_id already exists."]}
            )
        return Response(ExternalUserMappingSerializer(obj).data, status=status.HTTP_201_CREATED)


# ── 5G: Integration Failures, Dead-Letter & Recovery ─────────────────────────


class FailureListView(APIView):
    """GET /api/v1/integration/failures/

    Paginated list of integration failures with filtering by instance, organization,
    status, failure_type, failure_code, and dead-letter state. Platform Owner only.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        _require_owner(request.user)
        qs = IntegrationFailure.objects.select_related(
            "job__instance__connector__product",
            "job__organization",
            "event__instance__connector__product",
            "event__instance__organization",
            "resolved_by",
        ).prefetch_related("attempts").order_by("-created_at")

        # Filters
        instance_id = request.query_params.get("instance")
        if instance_id:
            qs = qs.filter(Q(job__instance_id=instance_id) | Q(event__instance_id=instance_id))

        org_id = request.query_params.get("organization")
        if org_id:
            qs = qs.filter(IntegrationFailure.org_scope_filter(org_id))


        status_param = request.query_params.get("status")
        if status_param:
            qs = qs.filter(status=status_param.lower())

        ftype_param = request.query_params.get("failure_type")
        if ftype_param:
            qs = qs.filter(failure_type=ftype_param.lower())

        fcode_param = request.query_params.get("failure_code")
        if fcode_param:
            qs = qs.filter(failure_code__icontains=fcode_param.strip())

        is_dead_letter = request.query_params.get("is_dead_letter")
        if is_dead_letter is not None:
            if is_dead_letter.lower() in ("true", "1"):
                qs = qs.filter(status=FailureStatus.DEAD_LETTER)
            elif is_dead_letter.lower() in ("false", "0"):
                qs = qs.exclude(status=FailureStatus.DEAD_LETTER)

        paginator = HubPagination()
        page = paginator.paginate_queryset(qs, request)
        return paginator.get_paginated_response(IntegrationFailureSerializer(page, many=True).data)


class FailureDetailView(APIView):
    """GET /api/v1/integration/failures/<pk>/

    Detailed diagnostic breakdown for an IntegrationFailure record. Platform Owner only.
    """
    permission_classes = [IsAuthenticated]

    def _get_obj(self, pk: str) -> IntegrationFailure:
        try:
            return IntegrationFailure.objects.select_related(
                "job__instance__connector__product",
                "job__organization",
                "event__instance__connector__product",
                "event__instance__organization",
                "resolved_by",
            ).prefetch_related("attempts").get(pk=pk)
        except IntegrationFailure.DoesNotExist:
            raise exceptions.NotFound("Integration failure not found.")

    def get(self, request: Request, pk: str) -> Response:
        _require_owner(request.user)
        failure = self._get_obj(pk)
        return Response(IntegrationFailureSerializer(failure).data)


class FailureResolveView(APIView):
    """POST /api/v1/integration/failures/<pk>/resolve/

    Audited manual resolution for an IntegrationFailure. Platform Owner only.
    """
    permission_classes = [IsAuthenticated]

    def _get_obj(self, pk: str) -> IntegrationFailure:
        try:
            return IntegrationFailure.objects.get(pk=pk)
        except IntegrationFailure.DoesNotExist:
            raise exceptions.NotFound("Integration failure not found.")

    def post(self, request: Request, pk: str) -> Response:
        _require_owner(request.user)
        failure = self._get_obj(pk)
        serializer = FailureResolveRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            updated = resolve_failure(
                failure,
                user=request.user,
                notes=serializer.validated_data["resolution_notes"],
            )
        except ValueError as err:
            raise exceptions.ValidationError({"detail": str(err)})

        return Response(IntegrationFailureSerializer(updated).data, status=status.HTTP_200_OK)


class FailureDeadLetterView(APIView):
    """POST /api/v1/integration/failures/<pk>/mark-dead-letter/

    Explicit transition of an IntegrationFailure to DEAD_LETTER state. Platform Owner only.
    """
    permission_classes = [IsAuthenticated]

    def _get_obj(self, pk: str) -> IntegrationFailure:
        try:
            return IntegrationFailure.objects.get(pk=pk)
        except IntegrationFailure.DoesNotExist:
            raise exceptions.NotFound("Integration failure not found.")

    def post(self, request: Request, pk: str) -> Response:
        _require_owner(request.user)
        failure = self._get_obj(pk)
        serializer = FailureDeadLetterRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            updated = mark_failure_dead_letter(
                failure,
                reason=serializer.validated_data.get("reason", ""),
            )
        except ValueError as err:
            raise exceptions.ValidationError({"detail": str(err)})

        return Response(IntegrationFailureSerializer(updated).data, status=status.HTTP_200_OK)


class FailureScheduleRetryView(APIView):
    """POST /api/v1/integration/failures/<pk>/schedule-retry/

    Deterministic retry scheduling: increments retry_count, computes backoff,
    and transitions to RETRY_SCHEDULED (or DEAD_LETTER if max_retries reached).
    Platform Owner only.
    """
    permission_classes = [IsAuthenticated]

    def _get_obj(self, pk: str) -> IntegrationFailure:
        try:
            return IntegrationFailure.objects.get(pk=pk)
        except IntegrationFailure.DoesNotExist:
            raise exceptions.NotFound("Integration failure not found.")

    def post(self, request: Request, pk: str) -> Response:
        _require_owner(request.user)
        failure = self._get_obj(pk)
        try:
            updated = schedule_failure_retry(failure)
        except ValueError as err:
            raise exceptions.ValidationError({"detail": str(err)})

        return Response(IntegrationFailureSerializer(updated).data, status=status.HTTP_200_OK)


class FailureReplayView(APIView):
    """POST /api/v1/integration/failures/<pk>/replay/

    Replays a DEAD_LETTER failure after issue correction. Platform Owner only.
    """
    permission_classes = [IsAuthenticated]

    def _get_obj(self, pk: str) -> IntegrationFailure:
        try:
            return IntegrationFailure.objects.get(pk=pk)
        except IntegrationFailure.DoesNotExist:
            raise exceptions.NotFound("Integration failure not found.")

    def post(self, request: Request, pk: str) -> Response:
        _require_owner(request.user)
        self._get_obj(pk)
        try:
            updated = replay_dead_letter_failure(failure_id=pk, actor=request.user)
        except ValueError as err:
            raise exceptions.ValidationError({"detail": str(err)})

        return Response(IntegrationFailureSerializer(updated).data, status=status.HTTP_200_OK)



# ── 5G: Aggregated Integration Health Endpoint ───────────────────────────────


class IntegrationHealthSummaryView(APIView):
    """GET /api/v1/integration/health/

    Aggregated control-plane operational health summary.
    Accurately distinguishes Control Plane state from external connectivity status.
    Platform Owner only.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        _require_owner(request.user)

        total_connectors = IntegrationConnector.objects.count()
        instances_qs = ConnectorInstance.objects.select_related("connector", "organization")
        total_instances = instances_qs.count()
        active_instances = instances_qs.filter(status=InstanceStatus.ACTIVE).count()
        suspended_instances = instances_qs.filter(status=InstanceStatus.SUSPENDED).count()
        disconnected_instances = instances_qs.filter(status=InstanceStatus.DISCONNECTED).count()

        # Failures breakdown
        failures_qs = IntegrationFailure.objects.all()
        total_open = failures_qs.filter(status=FailureStatus.OPEN).count()
        total_retry_scheduled = failures_qs.filter(status=FailureStatus.RETRY_SCHEDULED).count()
        total_dead_letter = failures_qs.filter(status=FailureStatus.DEAD_LETTER).count()
        total_resolved = failures_qs.filter(status=FailureStatus.RESOLVED).count()

        since_24h = timezone.now() - timedelta(hours=24)
        recent_24h_count = failures_qs.filter(created_at__gte=since_24h).count()

        # Jobs & Stuck / Orphaned breakdown
        from apps.integration_hub.models import ProvisioningJob, ProvisioningJobStatus
        from apps.integration_hub.stuck_job_service import detect_stuck_provisioning_jobs

        queued_job_count = ProvisioningJob.objects.filter(status=ProvisioningJobStatus.QUEUED).count()
        total_active_jobs = ProvisioningJob.objects.filter(
            status__in=[
                ProvisioningJobStatus.QUEUED,
                ProvisioningJobStatus.PROCESSING,
                ProvisioningJobStatus.RETRY_SCHEDULED,
            ]
        ).count()

        jobs_24h_qs = ProvisioningJob.objects.filter(created_at__gte=since_24h)
        jobs_24h_total = jobs_24h_qs.count()
        jobs_24h_completed = jobs_24h_qs.filter(status=ProvisioningJobStatus.COMPLETED).count()
        jobs_24h_failed = jobs_24h_qs.filter(status=ProvisioningJobStatus.FAILED).count()

        stuck_results = detect_stuck_provisioning_jobs(limit=200)
        stuck_summary = stuck_results.get("summary", {})
        stuck_queued_count = stuck_summary.get("stuck_queued", 0)
        stuck_processing_count = stuck_summary.get("stuck_processing", 0)
        orphaned_job_count = stuck_summary.get("orphaned", 0)

        # Calculable failure rate in last 24h
        if jobs_24h_total > 0:
            failure_rate = round((recent_24h_count / max(jobs_24h_total, 1)) * 100, 1)
        else:
            failure_rate = 0.0

        # Overall control plane status determination (deterministic state-based rules)
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

        # Explicit LMS Connectivity Probe (only invoked on explicit operator request)
        should_probe = request.query_params.get("probe", "").lower() in ("true", "1")
        if should_probe:
            from apps.integration_hub.lms_connector import (
                LmsConnectorClient,
                LmsConnectorConfigurationError,
            )

            try:
                lms_client = LmsConnectorClient()
                probe_res = lms_client.probe_connectivity()
                is_verified = probe_res.get("status") == "verified"
                external_connectivity = {
                    "status": probe_res.get("status", "not_verified"),
                    "verified_connectors_count": 1 if is_verified else 0,
                    "unverified_connectors_count": total_connectors - (1 if is_verified else 0),
                    "probed": True,
                    "last_probed_at": timezone.now().isoformat(),
                    "detail": probe_res.get("detail", ""),
                    "http_status": probe_res.get("http_status"),
                    "latency_ms": probe_res.get("latency_ms"),
                }
            except LmsConnectorConfigurationError as cfg_err:
                external_connectivity = {
                    "status": "not_verified",
                    "verified_connectors_count": 0,
                    "unverified_connectors_count": total_connectors,
                    "probed": True,
                    "last_probed_at": timezone.now().isoformat(),
                    "detail": f"Configuration unverified: {cfg_err.message}",
                }
            except Exception as exc:
                external_connectivity = {
                    "status": "unreachable",
                    "verified_connectors_count": 0,
                    "unverified_connectors_count": total_connectors,
                    "probed": True,
                    "last_probed_at": timezone.now().isoformat(),
                    "detail": "Failed to probe external connectivity.",
                }
        else:
            external_connectivity = {
                "status": "not_verified",
                "verified_connectors_count": 0,
                "unverified_connectors_count": total_connectors,
                "probed": False,
                "last_probed_at": None,
                "detail": "Control-plane layer only. No external SaaS health probes or active network calls configured.",
            }

        # Per-instance breakdown
        instance_health_list = []
        for inst in instances_qs:
            inst_failures = failures_qs.filter(
                Q(job__instance_id=inst.id) | Q(event__instance_id=inst.id)
            )
            open_count = inst_failures.filter(status__in=[FailureStatus.OPEN, FailureStatus.RETRY_SCHEDULED]).count()
            dl_count = inst_failures.filter(status=FailureStatus.DEAD_LETTER).count()
            latest = inst_failures.order_by("-created_at").first()
            instance_health_list.append({
                "id": str(inst.id),
                "label": inst.label,
                "connector_code": inst.connector.code if inst.connector else "",
                "organization_name": inst.organization.name if inst.organization else "",
                "status": inst.status,
                "open_failures": open_count,
                "dead_letter_failures": dl_count,
                "latest_failure_at": latest.created_at.isoformat() if latest else None,
            })

        return Response({
            "control_plane": {
                "status": control_plane_status,
                "total_connectors": total_connectors,
                "total_instances": total_instances,
                "active_instances": active_instances,
                "suspended_instances": suspended_instances,
                "disconnected_instances": disconnected_instances,
            },
            "summary": {
                "queued_job_count": queued_job_count,
                "stuck_queued_job_count": stuck_queued_count,
                "stuck_processing_job_count": stuck_processing_count,
                "orphaned_job_count": orphaned_job_count,
                "retry_scheduled_count": total_retry_scheduled,
                "dead_letter_count": total_dead_letter,
                "open_failure_count": total_open,
                "resolved_failure_count": total_resolved,
                "recent_failure_count": recent_24h_count,
                "failure_rate": failure_rate,
            },
            "jobs": {
                "queued_job_count": queued_job_count,
                "stuck_queued_job_count": stuck_queued_count,
                "stuck_processing_job_count": stuck_processing_count,
                "orphaned_job_count": orphaned_job_count,
                "recent_24h_completed_count": jobs_24h_completed,
                "recent_24h_failed_count": jobs_24h_failed,
                "total_active_jobs": total_active_jobs,
            },
            "failures": {
                "total_open": total_open,
                "total_retry_scheduled": total_retry_scheduled,
                "total_dead_letter": total_dead_letter,
                "total_resolved": total_resolved,
                "recent_24h_count": recent_24h_count,
                "open_failure_count": total_open,
                "retry_scheduled_count": total_retry_scheduled,
                "dead_letter_count": total_dead_letter,
                "resolved_failure_count": total_resolved,
                "recent_failure_count": recent_24h_count,
                "failure_rate_pct": failure_rate,
            },
            "instance_health": instance_health_list,
            "external_connectivity": external_connectivity,
        }, status=status.HTTP_200_OK)
