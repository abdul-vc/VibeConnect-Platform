"""Unified Analytics and Tenant Health Views for VibeConnect Phase 6E.

Provides:
- OwnerAnalyticsView (Platform-wide aggregates with bounded date ranges).
- TenantAnalyticsView (Tenant-scoped metrics and component-level health indicators).
- Explicit component-level health indicators reusing 6C-2 calculation logic.
- Zero composite numerical scores.
"""

from datetime import datetime, timedelta
import logging
import uuid
from typing import Any

from django.db.models import Avg, Count, F, Q, Sum
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime
from rest_framework import exceptions, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.access_control.constants import CONTEXT_TENANT
from apps.access_control.services.evaluation import evaluate_access
from apps.assignments.models import UserProductAssignment
from apps.auditlog.models import AuditAction, AuditLog
from apps.entitlements.models import EntitlementStatus, OrganizationProductEntitlement
from apps.identity.models import ImpersonationSessionStatus, SupportImpersonationSession
from apps.integration_hub.models import (
    ConnectorInstance,
    FailureStatus,
    InstanceStatus,
    IntegrationFailure,
    IntegrationReconciliationIssue,
    IntegrationReconciliationStatus,
    ProvisioningJob,
    ProvisioningJobStatus,
    SsoAuthorizationCode,
)
from apps.integration_hub.stuck_job_service import detect_stuck_provisioning_jobs
from apps.organizations.models import (
    MembershipStatus,
    MembershipType,
    Organization,
    OrganizationMembership,
    OrganizationStatus,
)
from apps.product_registry.models import Product
from apps.subscriptions.models import OrganizationSubscription, SubscriptionStatus

logger = logging.getLogger(__name__)


def _parse_bounded_date_range(request: Request) -> tuple[datetime, datetime]:
    """Parse start_date and end_date query params, enforcing a hard 90-day window limit.

    Defaults to the past 30 days if not provided.
    """
    now = timezone.now()
    raw_start = request.query_params.get("start_date")
    raw_end = request.query_params.get("end_date")

    end_dt = now
    if raw_end:
        parsed_end = parse_date(raw_end.strip())
        if parsed_end:
            end_dt = timezone.make_aware(datetime.combine(parsed_end, datetime.max.time()))

    start_dt = end_dt - timedelta(days=30)
    if raw_start:
        parsed_start = parse_date(raw_start.strip())
        if parsed_start:
            start_dt = timezone.make_aware(datetime.combine(parsed_start, datetime.min.time()))

    if start_dt > end_dt:
        start_dt, end_dt = end_dt - timedelta(days=30), end_dt

    # Hard bound: Maximum 90-day query window to prevent denial of service
    if (end_dt - start_dt).days > 90:
        start_dt = end_dt - timedelta(days=90)

    return start_dt, end_dt


def compute_component_integration_health(org: Organization) -> dict[str, Any]:
    """Compute component-level integration health indicators reusing 6C-2 logic.

    Directly replicates the deterministic logic from:
    apps/integration_hub/support_views.py:185-195
    apps/integration_hub/views.py:581-593
    Exposes separate transparent component indicators with ZERO composite numerical score.
    """
    instances_qs = ConnectorInstance.objects.filter(organization=org)
    total_instances = instances_qs.count()
    active_instances = instances_qs.filter(status=InstanceStatus.ACTIVE).count()
    suspended_instances = instances_qs.filter(status=InstanceStatus.SUSPENDED).count()
    disconnected_instances = instances_qs.filter(status=InstanceStatus.DISCONNECTED).count()

    failures_qs = IntegrationFailure.objects.filter(
        IntegrationFailure.org_scope_filter(org)
    ).distinct()

    dead_letter_count = failures_qs.filter(status=FailureStatus.DEAD_LETTER).count()
    open_failures_count = failures_qs.filter(status=FailureStatus.OPEN).count()
    retry_scheduled_count = failures_qs.filter(status=FailureStatus.RETRY_SCHEDULED).count()

    stuck_results = detect_stuck_provisioning_jobs(organization_id=org.id, limit=50)
    stuck_summary = stuck_results.get("summary", {})
    stuck_queued = stuck_summary.get("stuck_queued", 0)
    stuck_processing = stuck_summary.get("stuck_processing", 0)
    orphaned_jobs = stuck_summary.get("orphaned", 0)
    total_stuck_jobs = stuck_queued + stuck_processing + orphaned_jobs

    open_reconciliations = IntegrationReconciliationIssue.objects.filter(
        instance__organization=org,
        status=IntegrationReconciliationStatus.OPEN,
    ).count()

    # Reused deterministic status calculation (6C-2 lines 185-195)
    if (
        dead_letter_count > 0
        or total_stuck_jobs > 0
        or disconnected_instances > 0
    ):
        status_label = "unhealthy"
    elif open_failures_count > 0 or suspended_instances > 0 or open_reconciliations > 0:
        status_label = "degraded"
    else:
        status_label = "healthy"

    return {
        "status": status_label,
        "active_connectors": active_instances,
        "suspended_connectors": suspended_instances,
        "disconnected_connectors": disconnected_instances,
        "open_failures": open_failures_count,
        "retry_scheduled_failures": retry_scheduled_count,
        "dead_letter_failures": dead_letter_count,
        "stuck_jobs": total_stuck_jobs,
        "open_reconciliations": open_reconciliations,
    }


class OwnerAnalyticsView(APIView):
    """GET /api/v1/owner/analytics/

    Platform Owner aggregate reporting covering all 6 metrics in METRICS_CATALOGUE:
    1. Product Adoption (tenants and users)
    2. Seat Utilization across active subscriptions
    3. SSO Launch Activity (codes issued vs codes validated)
    4. Integration Health Trend (healthy/degraded/unhealthy distribution)
    5. Support Activity Volume (retries, replays, resolves)
    6. Impersonation Frequency & Duration
    """

    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        if not getattr(request.user, "is_platform_owner", False):
            raise exceptions.PermissionDenied("Platform owner privileges required.")

        start_dt, end_dt = _parse_bounded_date_range(request)

        # 1. Product Adoption Metric
        products = Product.objects.all().order_by("name")
        product_adoption = []
        for p in products:
            tenant_count = OrganizationProductEntitlement.objects.filter(
                product=p,
                status=EntitlementStatus.ACTIVE,
            ).values("organization_id").distinct().count()

            user_assignment_count = UserProductAssignment.objects.filter(
                product=p,
                status="active",
            ).values("user_id").distinct().count()

            product_adoption.append(
                {
                    "product_id": str(p.id),
                    "product_code": p.code,
                    "product_name": p.name,
                    "entitled_tenants": tenant_count,
                    "assigned_users": user_assignment_count,
                }
            )

        # 2. Global Seat Utilization Metric
        total_seats_assigned = UserProductAssignment.objects.filter(status="active").count()
        total_tenants = Organization.objects.filter(status=OrganizationStatus.ACTIVE).count()

        # 3. SSO Launch Activity Metric (codes issued in window vs codes validated in window)
        sso_issued = SsoAuthorizationCode.objects.filter(
            created_at__gte=start_dt,
            created_at__lte=end_dt,
        ).count()
        sso_validated = SsoAuthorizationCode.objects.filter(
            used_at__gte=start_dt,
            used_at__lte=end_dt,
        ).count()

        # 4. Integration Health Trend Metric (Aggregate distribution across active orgs)

        active_orgs = Organization.objects.filter(status=OrganizationStatus.ACTIVE)[:50]
        health_counts = {"healthy": 0, "degraded": 0, "unhealthy": 0}
        for org in active_orgs:
            comp = compute_component_integration_health(org)
            health_counts[comp["status"]] += 1

        # 5. Support Activity Volume Metric (Audit logs in window)
        support_remediation_count = AuditLog.objects.filter(
            timestamp__gte=start_dt,
            timestamp__lte=end_dt,
            action__in=[
                AuditAction.SUPPORT_FAILURE_RETRY_SCHEDULED,
                AuditAction.SUPPORT_DEAD_LETTER_REPLAYED,
                AuditAction.SUPPORT_FAILURE_RESOLVED,
                AuditAction.SUPPORT_RECONCILIATION_RESOLVED,
            ],
        ).count()
        impersonation_started_count = AuditLog.objects.filter(
            timestamp__gte=start_dt,
            timestamp__lte=end_dt,
            action=AuditAction.SUPPORT_IMPERSONATION_STARTED,
        ).count()

        # 6. Impersonation Frequency & Duration Metric
        sessions_in_window = SupportImpersonationSession.objects.filter(
            created_at__gte=start_dt,
            created_at__lte=end_dt,
        )
        total_sessions = sessions_in_window.count()
        now = timezone.now()
        active_unexpired_count = sessions_in_window.filter(
            status=ImpersonationSessionStatus.ACTIVE,
            expires_at__gt=now,
        ).count()
        expired_count = sessions_in_window.filter(
            Q(status=ImpersonationSessionStatus.EXPIRED)
            | Q(status=ImpersonationSessionStatus.ACTIVE, expires_at__lte=now)
        ).count()
        terminated_count = sessions_in_window.filter(
            status=ImpersonationSessionStatus.TERMINATED
        ).count()
        revoked_count = sessions_in_window.filter(
            status=ImpersonationSessionStatus.REVOKED
        ).count()
        status_breakdown = {
            "active": active_unexpired_count,
            "expired": expired_count,
            "terminated": terminated_count,
            "revoked": revoked_count,
        }

        # Compute average duration
        completed_sessions = sessions_in_window.filter(terminated_at__isnull=False)
        durations = []
        for s in completed_sessions:
            if s.terminated_at and s.created_at:
                sec = int((s.terminated_at - s.created_at).total_seconds())
                durations.append(min(max(sec, 0), 1800))
        avg_duration_seconds = int(sum(durations) / len(durations)) if durations else 0

        return Response(
            {
                "time_window": {
                    "start_date": start_dt.isoformat(),
                    "end_date": end_dt.isoformat(),
                    "days": (end_dt - start_dt).days,
                },
                "product_adoption": product_adoption,
                "seat_utilization": {
                    "total_active_seats": total_seats_assigned,
                    "active_tenants": total_tenants,
                },
                "sso_launch_activity": {
                    "codes_issued": sso_issued,
                    "codes_validated": sso_validated,
                },

                "integration_health_distribution": health_counts,
                "support_activity_volume": {
                    "impersonation_sessions_started": impersonation_started_count,
                    "remediation_operations_executed": support_remediation_count,
                    "total_support_actions": impersonation_started_count + support_remediation_count,
                },
                "impersonation_metrics": {
                    "total_sessions": total_sessions,
                    "average_duration_seconds": avg_duration_seconds,
                    "status_breakdown": status_breakdown,
                },
            },
            status=status.HTTP_200_OK,
        )


class TenantAnalyticsView(APIView):
    """GET /api/v1/tenant/analytics/

    Tenant-scoped operational analytics and transparent component-level health indicators.
    - Strictly rejects Tenant Members (Tenant Admin privileges required).
    - Scoped strictly to the authenticated tenant organization.
    - Bounded date range parsing.
    - ZERO composite numerical health score.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        user = request.user
        membership = (
            OrganizationMembership.objects.filter(
                user=user,
                status=MembershipStatus.ACTIVE,
            )
            .select_related("organization")
            .first()
        )

        is_owner = getattr(user, "is_platform_owner", False)
        if not membership and not is_owner:
            raise exceptions.PermissionDenied("Active organization membership required.")

        org = None
        if is_owner:
            req_org_id = request.query_params.get("organization_id")
            if req_org_id:
                try:
                    org = Organization.objects.filter(pk=uuid.UUID(str(req_org_id)), status=OrganizationStatus.ACTIVE).first()
                    if not org:
                        raise exceptions.NotFound("Organization not found.")
                except (ValueError, TypeError):
                    raise exceptions.ValidationError({"organization_id": "Invalid organization UUID format."})
            elif membership:
                org = membership.organization
            else:
                org = Organization.objects.filter(status=OrganizationStatus.ACTIVE).first()
        else:
            org = membership.organization

        if not org:
            raise exceptions.NotFound("Organization not found.")

        # Rejection: Tenant Members must not get administrative analytics access
        if not is_owner:
            if membership.membership_type != MembershipType.TENANT_ADMIN:
                raise exceptions.PermissionDenied(
                    {"code": "INSUFFICIENT_PRIVILEGES", "detail": "Tenant Administrator access required for analytics."}
                )
            eval_result = evaluate_access(user, CONTEXT_TENANT, org.id)
            if not eval_result.has_permission("reports.view"):
                raise exceptions.PermissionDenied("Actor lacks required permission 'reports.view'.")

        start_dt, end_dt = _parse_bounded_date_range(request)

        # 1. Tenant Product Adoption
        entitlements = OrganizationProductEntitlement.objects.filter(
            organization=org,
            status=EntitlementStatus.ACTIVE,
        ).select_related("product")

        product_items = []
        for ent in entitlements:
            assigned_count = UserProductAssignment.objects.filter(
                organization=org,
                product=ent.product,
                status="active",
            ).count()
            product_items.append(
                {
                    "product_id": str(ent.product.id),
                    "product_code": ent.product.code,
                    "product_name": ent.product.name,
                    "assigned_users_count": assigned_count,
                }
            )

        # 2. Tenant Seat Utilization
        assigned_seats = UserProductAssignment.objects.filter(
            organization=org,
            status="active",
        ).count()

        active_sub = OrganizationSubscription.objects.filter(
            organization=org,
            status=SubscriptionStatus.ACTIVE,
        ).first()

        # 3. Tenant SSO Launch Activity in Window (codes issued in window vs codes validated in window)
        sso_issued = SsoAuthorizationCode.objects.filter(
            organization=org,
            created_at__gte=start_dt,
            created_at__lte=end_dt,
        ).count()
        sso_validated = SsoAuthorizationCode.objects.filter(
            organization=org,
            used_at__gte=start_dt,
            used_at__lte=end_dt,
        ).count()

        # 4. Transparent Component-Level Health Indicators (Reused from 6C-2)
        component_health = compute_component_integration_health(org)

        # 5. Tenant Impersonation & Support Activity
        impersonation_sessions_count = SupportImpersonationSession.objects.filter(
            target_organization=org,
            created_at__gte=start_dt,
            created_at__lte=end_dt,
        ).count()

        return Response(
            {
                "organization": {
                    "id": str(org.id),
                    "code": org.code,
                    "name": org.name,
                },
                "time_window": {
                    "start_date": start_dt.isoformat(),
                    "end_date": end_dt.isoformat(),
                    "days": (end_dt - start_dt).days,
                },
                "product_adoption": product_items,
                "seat_utilization": {
                    "assigned_seats": assigned_seats,
                    "has_active_subscription": bool(active_sub),
                },
                "sso_launch_activity": {
                    "codes_issued": sso_issued,
                    "codes_validated": sso_validated,
                },
                "component_health_indicators": component_health,

                "support_activity": {
                    "impersonation_sessions_in_window": impersonation_sessions_count,
                },
            },
            status=status.HTTP_200_OK,
        )
