from rest_framework import exceptions, status
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.access_control.constants import CONTEXT_TENANT
from apps.access_control.services.evaluation import evaluate_access
from apps.billing.models import BillingAccount, Invoice, Payment
from apps.billing.serializers import (
    BillingAccountSerializer,
    InvoiceSerializer,
    PaymentRecordSerializer,
    PaymentSerializer,
)
from apps.billing.services import (
    generate_invoice_for_subscription,
    record_payment,
    schedule_dunning_retry,
)
from apps.organizations.models import MembershipStatus, Organization, OrganizationMembership
from apps.subscriptions.models import OrganizationSubscription


class BillingPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


def _check_billing_view_permission(user, org: Organization) -> None:
    if not user or not user.is_authenticated:
        raise exceptions.NotAuthenticated()
    if getattr(user, "is_platform_owner", False):
        return
    eval_result = evaluate_access(user, CONTEXT_TENANT, org.id)
    if not eval_result.has_permission("billing.view"):
        raise exceptions.PermissionDenied("Actor lacks required permission 'billing.view'.")


class OwnerBillingAccountListView(APIView):
    """GET/POST /api/v1/billing/accounts/
    
    Owner cross-tenant billing account list.
    """
    permission_classes = [IsAuthenticated]
    pagination_class = BillingPagination

    def get(self, request: Request) -> Response:
        if not getattr(request.user, "is_platform_owner", False):
            raise exceptions.PermissionDenied("Platform owner privileges required.")
        accounts = BillingAccount.objects.all().select_related("organization").order_by("organization__name")
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(accounts, request)
        return paginator.get_paginated_response(BillingAccountSerializer(page, many=True).data)


class TenantBillingAccountView(APIView):
    """GET /api/v1/tenant/billing/account/
    
    Tenant billing account detail. Gated by billing.view.
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
            return Response({"detail": "Organization not found."}, status=status.HTTP_404_NOT_FOUND)

        _check_billing_view_permission(user, org)

        account, _ = BillingAccount.objects.get_or_create(
            organization=org,
            defaults={
                "legal_name": org.name,
                "billing_email": f"billing@{org.code}.internal",
            },
        )
        return Response(BillingAccountSerializer(account).data, status=status.HTTP_200_OK)


class OwnerInvoiceListView(APIView):
    """GET /api/v1/billing/invoices/
    
    Platform owner cross-tenant invoice list.
    """
    permission_classes = [IsAuthenticated]
    pagination_class = BillingPagination

    def get(self, request: Request) -> Response:
        if not getattr(request.user, "is_platform_owner", False):
            raise exceptions.PermissionDenied("Platform owner privileges required.")
        invoices = (
            Invoice.objects.all()
            .select_related("organization", "subscription")
            .prefetch_related("lines")
            .order_by("-created_at")
        )
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(invoices, request)
        return paginator.get_paginated_response(InvoiceSerializer(page, many=True).data)


class TenantInvoiceListView(APIView):
    """GET /api/v1/tenant/billing/invoices/
    
    Tenant organization invoice list (read-only). Gated by billing.view.
    """
    permission_classes = [IsAuthenticated]
    pagination_class = BillingPagination

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
            return Response([], status=status.HTTP_200_OK)

        _check_billing_view_permission(user, org)

        invoices = (
            Invoice.objects.filter(organization=org)
            .select_related("organization", "subscription")
            .prefetch_related("lines")
            .order_by("-created_at")
        )
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(invoices, request)
        return paginator.get_paginated_response(InvoiceSerializer(page, many=True).data)


class GenerateInvoiceView(APIView):
    """POST /api/v1/billing/invoices/generate/
    
    Generate an invoice from an active subscription.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        if not getattr(request.user, "is_platform_owner", False):
            raise exceptions.PermissionDenied("Platform owner privileges required.")
        sub_id = request.data.get("subscription_id")
        subscription = OrganizationSubscription.objects.filter(id=sub_id).first()
        if not subscription:
            return Response({"detail": "Subscription not found."}, status=status.HTTP_404_NOT_FOUND)

        try:
            invoice = generate_invoice_for_subscription(subscription, actor=request.user)
            return Response(InvoiceSerializer(invoice).data, status=status.HTTP_201_CREATED)
        except Exception as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class PaymentWebhookView(APIView):
    """POST /api/v1/billing/payments/
    
    Idempotent payment webhook / recording endpoint.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        serializer = PaymentRecordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        payment, created = record_payment(
            invoice_id=str(data["invoice_id"]),
            amount=data["amount"],
            currency=data.get("currency", "USD"),
            idempotency_key=data["idempotency_key"],
            processor_ref=data.get("processor_ref", ""),
        )

        return Response(
            PaymentSerializer(payment).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class DunningTriggerView(APIView):
    """POST /api/v1/billing/invoices/<uuid:invoice_id>/dunning/
    
    Trigger or schedule dunning attempt for an invoice via background worker.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, invoice_id: str) -> Response:
        if not getattr(request.user, "is_platform_owner", False):
            raise exceptions.PermissionDenied("Platform owner privileges required.")
        invoice = Invoice.objects.filter(id=invoice_id).first()
        if not invoice:
            return Response({"detail": "Invoice not found."}, status=status.HTTP_404_NOT_FOUND)

        attempt = schedule_dunning_retry(invoice=invoice)
        return Response(
            {
                "status": "scheduled",
                "attempt_id": str(attempt.id),
                "attempt_number": attempt.attempt_number,
                "invoice_number": invoice.invoice_number,
            },
            status=status.HTTP_202_ACCEPTED,
        )


class OwnerCommercialReconciliationListView(APIView):
    """GET /api/v1/billing/reconciliations/
    
    List commercial reconciliation issues.
    """
    permission_classes = [IsAuthenticated]
    pagination_class = BillingPagination

    def get(self, request: Request) -> Response:
        if not getattr(request.user, "is_platform_owner", False):
            raise exceptions.PermissionDenied("Platform owner privileges required.")

        from apps.billing.models import CommercialReconciliation
        from apps.billing.serializers import CommercialReconciliationSerializer

        qs = CommercialReconciliation.objects.select_related("organization", "subscription", "resolved_by").order_by("-detected_at")
        status_filter = request.query_params.get("status")
        if status_filter:
            qs = qs.filter(status=status_filter)

        paginator = self.pagination_class()
        page = paginator.paginate_queryset(qs, request)
        return paginator.get_paginated_response(CommercialReconciliationSerializer(page, many=True).data)


class OwnerCommercialReconciliationTriggerView(APIView):
    """POST /api/v1/billing/reconciliations/trigger/
    
    Trigger a commercial reconciliation job run.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        if not getattr(request.user, "is_platform_owner", False):
            raise exceptions.PermissionDenied("Platform owner privileges required.")
        from apps.billing.reconciliation import run_commercial_reconciliation
        org_id = request.data.get("organization_id")
        issues = run_commercial_reconciliation(organization_id=org_id)
        return Response(
            {
                "status": "completed",
                "detected_count": len(issues),
                "detected_issue_ids": [str(i.id) for i in issues],
            },
            status=status.HTTP_200_OK,
        )


class OwnerCommercialReconciliationResolveView(APIView):
    """POST /api/v1/billing/reconciliations/<uuid:reconciliation_id>/resolve/
    
    Manually resolve a reconciliation issue with mandatory audit reason.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, reconciliation_id: str) -> Response:
        if not getattr(request.user, "is_platform_owner", False):
            raise exceptions.PermissionDenied("Platform owner privileges required.")
        from apps.billing.models import CommercialReconciliation
        from apps.billing.serializers import (
            CommercialReconciliationSerializer,
            ResolveReconciliationSerializer,
        )

        serializer = ResolveReconciliationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        reason = serializer.validated_data["resolution_reason"]

        from apps.billing.reconciliation import resolve_commercial_reconciliation
        try:
            issue = resolve_commercial_reconciliation(
                reconciliation_id=str(reconciliation_id),
                resolved_by_user=request.user,
                resolution_reason=reason,
            )
        except CommercialReconciliation.DoesNotExist:
            return Response({"detail": "Reconciliation record not found."}, status=status.HTTP_404_NOT_FOUND)

        return Response(CommercialReconciliationSerializer(issue).data, status=status.HTTP_200_OK)

