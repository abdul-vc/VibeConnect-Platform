"""Common API Views.

Provides health and readiness probes for the VibeConnect master control plane (Phase 7D):
- HealthCheckView: Minimal, safe process liveness probe.
- ReadinessCheckView: Safe, non-destructive dependency readiness probe (PostgreSQL).
"""

import logging
from django.db import connection
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

logger = logging.getLogger(__name__)


class HealthCheckView(APIView):
    """Minimal, safe process liveness probe.

    Verifies the VibeConnect backend process is running and responding.
    Does not query PostgreSQL, does not call external services,
    and exposes no sensitive credentials or environment details.
    """

    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request, *args, **kwargs) -> Response:
        return Response(
            {
                "status": "healthy",
                "service": "vibeconnect_backend",
            },
            status=status.HTTP_200_OK,
        )


class ReadinessCheckView(APIView):
    """Safe, non-destructive dependency readiness probe.

    Verifies that critical dependencies (PostgreSQL database) are accessible
    and ready to accept traffic.
    Returns HTTP 200 with status "ready" when healthy.
    Returns HTTP 503 with status "unhealthy" when database connectivity fails.
    Never exposes credentials, database connection strings, or internal tracebacks.
    """

    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request, *args, **kwargs) -> Response:
        db_ready = False
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1;")
                row = cursor.fetchone()
                if row and row[0] == 1:
                    db_ready = True
        except Exception as exc:
            logger.error("Readiness check database probe failed: %s", exc)
            db_ready = False

        if db_ready:
            return Response(
                {
                    "status": "ready",
                    "services": {
                        "database": "connected",
                    },
                },
                status=status.HTTP_200_OK,
            )

        return Response(
            {
                "status": "unhealthy",
                "services": {
                    "database": "unavailable",
                },
            },
            status=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
