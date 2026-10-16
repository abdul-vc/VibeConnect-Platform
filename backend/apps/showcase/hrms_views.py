"""HRMS Showcase Demonstration Views.

Provides read-only API endpoints for live presentation of the PeoplePulse HRMS sandbox:
- Health & connectivity probe
- Employee directory with search & department filtering
- Today's attendance punches and attendance dashboard metrics
- Department list for dynamic UI filters
- High-level overview stats

All endpoints require showcase authorization and return strictly sanitized data.
No mutating operations (POST, PUT, PATCH, DELETE) are exposed.
"""

from __future__ import annotations

import logging
import math
from typing import Any

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.integration_hub.hrms_connector import (
    HrmsConnectorAuthError,
    HrmsConnectorClient,
    HrmsConnectorConfigurationError,
    HrmsConnectorPermanentError,
    HrmsConnectorRetryableError,
)
from apps.showcase.permissions import HasShowcaseAccess

logger = logging.getLogger(__name__)


def _get_hrms_client() -> HrmsConnectorClient:
    """Instantiates HrmsConnectorClient resolving server-side configuration."""
    return HrmsConnectorClient()


def _handle_connector_error(exc: Exception) -> Response:
    """Standardized error responder for HRMS upstream failures."""
    if isinstance(exc, HrmsConnectorConfigurationError):
        logger.warning("HRMS configuration error: %s", exc)
        return Response(
            {
                "code": "HRMS_NOT_CONFIGURED",
                "detail": "HRMS sandbox is not configured on this server.",
            },
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    if isinstance(exc, HrmsConnectorAuthError):
        logger.warning("HRMS upstream authentication error: %s", exc)
        return Response(
            {
                "code": "HRMS_AUTH_FAILED",
                "detail": "Authentication with the upstream HRMS sandbox failed.",
            },
            status=status.HTTP_502_BAD_GATEWAY,
        )
    if isinstance(exc, HrmsConnectorRetryableError):
        logger.warning("HRMS transient upstream error: %s", exc)
        return Response(
            {
                "code": "HRMS_UNREACHABLE",
                "detail": f"Upstream HRMS service is temporarily unreachable: {exc.message}",
            },
            status=status.HTTP_504_GATEWAY_TIMEOUT if exc.status_code == 504 else status.HTTP_502_BAD_GATEWAY,
        )
    if isinstance(exc, HrmsConnectorPermanentError):
        logger.warning("HRMS upstream permanent error: %s", exc)
        return Response(
            {
                "code": "HRMS_UPSTREAM_ERROR",
                "detail": f"Upstream HRMS service rejected request: {exc.message}",
            },
            status=status.HTTP_502_BAD_GATEWAY,
        )
    logger.exception("Unexpected error in HRMS showcase view: %s", exc)
    return Response(
        {
            "code": "HRMS_INTERNAL_ERROR",
            "detail": "An unexpected error occurred while communicating with HRMS.",
        },
        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )


class HrmsHealthView(APIView):
    """GET /api/v1/showcase/hrms/health/ - Safe probe of sandbox connectivity."""

    permission_classes = [IsAuthenticated, HasShowcaseAccess]

    def get(self, request: Request) -> Response:
        try:
            client = _get_hrms_client()
            health = client.probe_connectivity()
            if health.get("status") == "auth_failed":
                return Response(
                    {
                        "code": "HRMS_AUTH_FAILED",
                        "status": "auth_failed",
                        "detail": health.get("detail", "HRMS authentication failed."),
                        "latency_ms": health.get("latency_ms"),
                    },
                    status=status.HTTP_502_BAD_GATEWAY,
                )
            if health.get("status") == "unreachable":
                return Response(
                    {
                        "code": "HRMS_UNREACHABLE",
                        "status": "unreachable",
                        "detail": health.get("detail", "HRMS sandbox is unreachable."),
                        "latency_ms": health.get("latency_ms"),
                    },
                    status=status.HTTP_502_BAD_GATEWAY,
                )
            return Response(health)
        except Exception as exc:
            return _handle_connector_error(exc)


class HrmsOverviewView(APIView):
    """GET /api/v1/showcase/hrms/overview/ - Aggregated stats for presentation overview."""

    permission_classes = [IsAuthenticated, HasShowcaseAccess]

    def get(self, request: Request) -> Response:
        try:
            client = _get_hrms_client()
            dashboard = client.get_attendance_dashboard()
            stats = client.get_overview_stats()
            today_records = client.get_attendance_today()

            return Response({
                "sandbox": {
                    "provider": "PeoplePulse HRMS",
                    "url": client.base_url,
                    "isSandbox": True,
                },
                "attendance": dashboard,
                "stats": stats,
                "todayPunchCount": len(today_records),
            })
        except Exception as exc:
            return _handle_connector_error(exc)


class HrmsEmployeesView(APIView):
    """GET /api/v1/showcase/hrms/employees/ - Sanitized paginated employee directory."""

    permission_classes = [IsAuthenticated, HasShowcaseAccess]

    def get(self, request: Request) -> Response:
        department = request.query_params.get("department")
        search = request.query_params.get("search")

        try:
            page = max(1, int(request.query_params.get("page", 1)))
            page_size = min(100, max(1, int(request.query_params.get("page_size", 10))))
        except (ValueError, TypeError):
            page, page_size = 1, 10

        try:
            client = _get_hrms_client()
            employees = client.list_employees(department=department, search=search)

            # Paginate results cleanly
            total_count = len(employees)
            total_pages = max(1, math.ceil(total_count / page_size)) if total_count > 0 else 1

            start_idx = (page - 1) * page_size
            end_idx = start_idx + page_size
            page_results = employees[start_idx:end_idx]

            return Response({
                "count": total_count,
                "page": page,
                "pageSize": page_size,
                "totalPages": total_pages,
                "results": page_results,
            })
        except Exception as exc:
            return _handle_connector_error(exc)


class HrmsAttendanceView(APIView):
    """GET /api/v1/showcase/hrms/attendance/ - Today's punch records and dashboard metrics."""

    permission_classes = [IsAuthenticated, HasShowcaseAccess]

    def get(self, request: Request) -> Response:
        try:
            client = _get_hrms_client()
            metrics = client.get_attendance_dashboard()
            records = client.get_attendance_today()

            return Response({
                "metrics": metrics,
                "count": len(records),
                "records": records,
            })
        except Exception as exc:
            return _handle_connector_error(exc)


class HrmsDepartmentsView(APIView):
    """GET /api/v1/showcase/hrms/departments/ - Department filter options."""

    permission_classes = [IsAuthenticated, HasShowcaseAccess]

    def get(self, request: Request) -> Response:
        try:
            client = _get_hrms_client()
            departments = client.list_departments()
            return Response({
                "count": len(departments),
                "results": departments,
            })
        except Exception as exc:
            return _handle_connector_error(exc)


class HrmsAttendanceHistoryView(APIView):
    """GET /api/v1/showcase/hrms/attendance/history/ - Historical attendance punch telemetry."""

    permission_classes = [IsAuthenticated, HasShowcaseAccess]

    def get(self, request: Request) -> Response:
        search = request.query_params.get("search")
        try:
            limit = min(200, max(1, int(request.query_params.get("limit", 50))))
        except (ValueError, TypeError):
            limit = 50

        try:
            client = _get_hrms_client()
            records = client.list_attendance_history(limit=limit, search=search)
            return Response({
                "count": len(records),
                "limit": limit,
                "results": records,
            })
        except Exception as exc:
            return _handle_connector_error(exc)


class HrmsOrganizationStructureView(APIView):
    """GET /api/v1/showcase/hrms/organization-structure/ - Departments, designations, and sites."""

    permission_classes = [IsAuthenticated, HasShowcaseAccess]

    def get(self, request: Request) -> Response:
        try:
            client = _get_hrms_client()
            departments = client.list_departments()
            designations = client.list_designations()
            sites = client.list_sites()

            return Response({
                "departments": departments,
                "designations": designations,
                "sites": sites,
            })
        except Exception as exc:
            return _handle_connector_error(exc)


class HrmsLeavesSummaryView(APIView):
    """GET /api/v1/showcase/hrms/leaves-summary/ - Aggregated leave metrics."""

    permission_classes = [IsAuthenticated, HasShowcaseAccess]

    def get(self, request: Request) -> Response:
        try:
            client = _get_hrms_client()
            summary = client.get_leaves_summary()
            return Response(summary)
        except Exception as exc:
            return _handle_connector_error(exc)

