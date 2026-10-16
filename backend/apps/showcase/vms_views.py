"""VMS (WarehouseOS) Showcase Demonstration Views.

Provides read-only API endpoints for live presentation of the WarehouseOS VMS sandbox:
- Health & connectivity probe
- Operational overview with KPIs and real-time activities
- Inventory stock statistics
- Active dock bays and vehicle queue
- Order fulfillment waves
- Yard gate vehicle movements
- Operational reports (QC status distribution, hourly throughput)

All endpoints require showcase authorization and return strictly sanitized data.
No mutating operations are exposed.
"""

from __future__ import annotations

import logging
from typing import Any

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.integration_hub.vms_connector import (
    VmsConnectorAuthError,
    VmsConnectorClient,
    VmsConnectorConfigurationError,
    VmsConnectorPermanentError,
    VmsConnectorRetryableError,
)
from apps.showcase.permissions import HasShowcaseAccess

logger = logging.getLogger(__name__)


def _get_vms_client() -> VmsConnectorClient:
    """Instantiates VmsConnectorClient resolving server-side configuration."""
    return VmsConnectorClient()


def _handle_connector_error(exc: Exception) -> Response:
    """Standardized error responder for VMS upstream failures."""
    if isinstance(exc, VmsConnectorConfigurationError):
        logger.warning("VMS configuration error: %s", exc)
        return Response(
            {
                "code": "VMS_NOT_CONFIGURED",
                "detail": "VMS sandbox is not configured on this server.",
            },
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    if isinstance(exc, VmsConnectorAuthError):
        logger.warning("VMS upstream authentication error: %s", exc)
        return Response(
            {
                "code": "VMS_AUTH_FAILED",
                "detail": "Authentication with the upstream VMS sandbox failed.",
            },
            status=status.HTTP_502_BAD_GATEWAY,
        )
    if isinstance(exc, VmsConnectorRetryableError):
        logger.warning("VMS transient upstream error: %s", exc)
        return Response(
            {
                "code": "VMS_UNREACHABLE",
                "detail": f"Upstream VMS service is temporarily unreachable: {exc.message}",
            },
            status=status.HTTP_504_GATEWAY_TIMEOUT if exc.status_code == 504 else status.HTTP_502_BAD_GATEWAY,
        )
    if isinstance(exc, VmsConnectorPermanentError):
        logger.warning("VMS upstream permanent error: %s", exc)
        return Response(
            {
                "code": "VMS_UPSTREAM_ERROR",
                "detail": f"Upstream VMS service rejected request: {exc.message}",
            },
            status=status.HTTP_502_BAD_GATEWAY,
        )
    logger.exception("Unexpected error in VMS showcase view: %s", exc)
    return Response(
        {
            "code": "VMS_INTERNAL_ERROR",
            "detail": "An unexpected error occurred while communicating with VMS.",
        },
        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )


class VmsHealthView(APIView):
    """GET /api/v1/showcase/vms/health/ - Safe probe of VMS sandbox connectivity."""

    permission_classes = [IsAuthenticated, HasShowcaseAccess]

    def get(self, request: Request) -> Response:
        try:
            client = _get_vms_client()
            health = client.probe_connectivity()
            if health.get("status") == "auth_failed":
                return Response(
                    {
                        "code": "VMS_AUTH_FAILED",
                        "status": "auth_failed",
                        "detail": health.get("detail", "VMS authentication failed."),
                        "latency_ms": health.get("latency_ms"),
                    },
                    status=status.HTTP_502_BAD_GATEWAY,
                )
            if health.get("status") == "unreachable":
                return Response(
                    {
                        "code": "VMS_UNREACHABLE",
                        "status": "unreachable",
                        "detail": health.get("detail", "VMS sandbox is unreachable."),
                        "latency_ms": health.get("latency_ms"),
                    },
                    status=status.HTTP_502_BAD_GATEWAY,
                )
            return Response(health)
        except Exception as exc:
            return _handle_connector_error(exc)


class VmsOverviewView(APIView):
    """GET /api/v1/showcase/vms/overview/ - Aggregated stats for presentation overview."""

    permission_classes = [IsAuthenticated, HasShowcaseAccess]

    def get(self, request: Request) -> Response:
        try:
            client = _get_vms_client()
            overview = client.get_overview()
            return Response(overview)
        except Exception as exc:
            return _handle_connector_error(exc)


class VmsInventoryView(APIView):
    """GET /api/v1/showcase/vms/inventory/ - Real-time stock statistics."""

    permission_classes = [IsAuthenticated, HasShowcaseAccess]

    def get(self, request: Request) -> Response:
        try:
            client = _get_vms_client()
            stock = client.get_inventory_stock()
            return Response(stock)
        except Exception as exc:
            return _handle_connector_error(exc)


class VmsDocksView(APIView):
    """GET /api/v1/showcase/vms/docks/ - Active dock bays and allocations."""

    permission_classes = [IsAuthenticated, HasShowcaseAccess]

    def get(self, request: Request) -> Response:
        try:
            client = _get_vms_client()
            docks = client.get_docks()
            return Response({
                "count": len(docks),
                "docks": docks,
            })
        except Exception as exc:
            return _handle_connector_error(exc)


class VmsWavesView(APIView):
    """GET /api/v1/showcase/vms/waves/ - Active order fulfillment waves."""

    permission_classes = [IsAuthenticated, HasShowcaseAccess]

    def get(self, request: Request) -> Response:
        try:
            client = _get_vms_client()
            waves = client.get_waves()
            return Response({
                "count": len(waves),
                "waves": waves,
            })
        except Exception as exc:
            return _handle_connector_error(exc)


class VmsVehiclesView(APIView):
    """GET /api/v1/showcase/vms/vehicles/ - Active gate vehicles and yard queue."""

    permission_classes = [IsAuthenticated, HasShowcaseAccess]

    def get(self, request: Request) -> Response:
        try:
            client = _get_vms_client()
            vehicles = client.get_vehicles()
            return Response(vehicles)
        except Exception as exc:
            return _handle_connector_error(exc)


class VmsReportsView(APIView):
    """GET /api/v1/showcase/vms/reports/ - Aggregated operational reports."""

    permission_classes = [IsAuthenticated, HasShowcaseAccess]

    def get(self, request: Request) -> Response:
        try:
            client = _get_vms_client()
            reports = client.get_reports_summary()
            return Response(reports)
        except Exception as exc:
            return _handle_connector_error(exc)
