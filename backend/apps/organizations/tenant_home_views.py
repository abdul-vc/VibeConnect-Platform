"""Tenant Home API Views (Phase 2G Part A).

Provides:
- GET /api/v1/tenant/home/
  Central tenant aggregation endpoint returning:
  - active organization summary
  - current user membership and administrative role
  - entitled products with assigned module/feature/capability trees
  - Tenant Admin console modules permitted by role + ceilings + module policies
  - seat allocation and capacity metrics
"""

from typing import Any
from rest_framework import exceptions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.access_control.constants import CONTEXT_TENANT
from apps.access_control.views import RequireTenantContext, get_tenant_organization_from_request
from apps.assignments.services.effective_access import compute_user_tenant_effective_access
from apps.identity.authentication import EnforcedSessionAuthentication
from apps.organizations.tenant_home_serializers import TenantHomeResponseSerializer


class TenantHomeView(APIView):
    """Authoritative aggregation endpoint for Tenant Admin Console & App Launcher.

    Computes complete effective access chain per user and organization context.
    """

    authentication_classes = [EnforcedSessionAuthentication]
    permission_classes = [RequireTenantContext]

    def get(self, request: Any, *args: Any, **kwargs: Any) -> Response:
        org = get_tenant_organization_from_request(request)

        # Compute full effective-access chain
        data = compute_user_tenant_effective_access(
            user=request.user,
            organization=org,
        )

        serializer = TenantHomeResponseSerializer(data)
        return Response(serializer.data, status=status.HTTP_200_OK)
