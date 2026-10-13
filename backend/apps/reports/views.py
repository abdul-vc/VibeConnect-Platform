from decimal import Decimal
import logging

from django.db.models import Count, Sum
from rest_framework import exceptions, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.access_control.constants import CONTEXT_TENANT
from apps.access_control.services.evaluation import evaluate_access
from apps.assignments.models import UserProductAssignment
from apps.billing.models import CommercialReconciliation, Invoice, InvoiceStatus
from apps.entitlements.models import EntitlementStatus, OrganizationProductEntitlement
from apps.organizations.models import MembershipStatus, Organization, OrganizationMembership, OrganizationStatus
from apps.product_registry.models import Product
from apps.subscriptions.models import OrganizationSubscription, SubscriptionStatus
from apps.usage_metering.models import UsageBucket, UsageEvent

logger = logging.getLogger(__name__)


def _check_reports_view_permission(user, org: Organization) -> None:
    if not user or not user.is_authenticated:
        raise exceptions.NotAuthenticated()
    if getattr(user, "is_platform_owner", False):
        return
    eval_result = evaluate_access(user, CONTEXT_TENANT, org.id)
    if not eval_result.has_permission("reports.view"):
        raise exceptions.PermissionDenied("Actor lacks required permission 'reports.view'.")


class OwnerReportsSummaryView(APIView):
    """GET /api/v1/reports/summary/

    Platform Owner aggregate reporting across organizations, product adoptions,
    aggregate usage volume, and commercial status.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        if not getattr(request.user, "is_platform_owner", False):
            raise exceptions.PermissionDenied("Platform owner privileges required.")

        # Organization metrics
        total_orgs = Organization.objects.count()
        active_orgs = Organization.objects.filter(status=OrganizationStatus.ACTIVE).count()
        inactive_orgs = total_orgs - active_orgs

        # Product adoption
        products = Product.objects.all()
        product_adoption = []
        for prod in products:
            count = OrganizationProductEntitlement.objects.filter(
                product=prod,
                status=EntitlementStatus.ACTIVE,
            ).values("organization").distinct().count()
            product_adoption.append({
                "product_id": str(prod.id),
                "product_code": prod.code,
                "product_name": prod.name,
                "adopted_tenants_count": count,
            })

        # Aggregate usage
        total_events = UsageEvent.objects.count()
        total_buckets = UsageBucket.objects.count()
        over_limit_buckets = UsageBucket.objects.filter(is_over_limit=True).count()

        # Commercial & subscriptions
        active_subscriptions = OrganizationSubscription.objects.filter(
            status=SubscriptionStatus.ACTIVE,
        ).count()
        total_invoices = Invoice.objects.count()
        paid_invoices = Invoice.objects.filter(status=InvoiceStatus.PAID).count()
        open_reconciliations = CommercialReconciliation.objects.filter(status="open").count()

        return Response(
            {
                "organizations": {
                    "total": total_orgs,
                    "active": active_orgs,
                    "inactive": inactive_orgs,
                },
                "product_adoption": product_adoption,
                "usage": {
                    "total_events": total_events,
                    "total_buckets": total_buckets,
                    "over_limit_buckets": over_limit_buckets,
                },
                "commercial": {
                    "active_subscriptions": active_subscriptions,
                    "total_invoices": total_invoices,
                    "paid_invoices": paid_invoices,
                    "open_reconciliations": open_reconciliations,
                },
            },
            status=status.HTTP_200_OK,
        )


class TenantReportsSummaryView(APIView):
    """GET /api/v1/tenant/reports/

    Tenant-scoped operational reports: seat utilization, product usage,
    active subscription status, and billing invoice summary.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        user = request.user
        membership = OrganizationMembership.objects.filter(
            user=user,
            status=MembershipStatus.ACTIVE,
        ).first()

        if not membership and not getattr(user, "is_platform_owner", False):
            raise exceptions.PermissionDenied("No active organization membership found.")

        org = membership.organization if membership else Organization.objects.first()
        if not org:
            return Response(
                {
                    "seat_utilization": {"total_assigned": 0},
                    "usage_buckets": [],
                    "subscription": None,
                    "invoices": {"total": 0, "paid": 0},
                },
                status=status.HTTP_200_OK,
            )

        _check_reports_view_permission(user, org)

        # 1. Seat utilization
        total_seats_assigned = UserProductAssignment.objects.filter(
            organization=org,
            status="active",
        ).count()

        # 2. Product usage buckets
        buckets = UsageBucket.objects.filter(organization=org).select_related("meter")
        bucket_data = [
            {
                "meter_key": b.meter.quota_key,
                "meter_name": b.meter.name,
                "unit": b.meter.unit,
                "consumed": b.consumed,
                "is_over_limit": b.is_over_limit,
                "period_start": b.period_start.isoformat(),
                "period_end": b.period_end.isoformat(),
            }
            for b in buckets
        ]

        # 3. Active Subscription
        active_sub = OrganizationSubscription.objects.filter(
            organization=org,
            status=SubscriptionStatus.ACTIVE,
        ).first()
        sub_data = None
        if active_sub:
            sub_data = {
                "id": str(active_sub.id),
                "plan_code": active_sub.plan_code_snapshot,
                "plan_name": active_sub.plan_name_snapshot,
                "currency": active_sub.currency,
                "amount": str(active_sub.amount),
                "billing_interval": active_sub.billing_interval,
                "status": active_sub.status,
            }

        # 4. Invoices
        invoices = Invoice.objects.filter(organization=org)
        total_inv_count = invoices.count()
        paid_inv_count = invoices.filter(status=InvoiceStatus.PAID).count()

        return Response(
            {
                "seat_utilization": {
                    "total_assigned": total_seats_assigned,
                },
                "usage_buckets": bucket_data,
                "subscription": sub_data,
                "invoices": {
                    "total": total_inv_count,
                    "paid": paid_inv_count,
                },
            },
            status=status.HTTP_200_OK,
        )
