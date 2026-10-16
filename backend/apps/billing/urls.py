from django.urls import path

from apps.billing.views import (
    DunningTriggerView,
    GenerateInvoiceView,
    OwnerBillingAccountListView,
    OwnerInvoiceListView,
    PaymentWebhookView,
    TenantBillingAccountView,
    TenantInvoiceListView,
    OwnerCommercialReconciliationListView,
    OwnerCommercialReconciliationTriggerView,
    OwnerCommercialReconciliationResolveView,
)

urlpatterns = [
    path("billing/accounts/", OwnerBillingAccountListView.as_view(), name="owner-billing-accounts"),
    path("tenant/billing/account/", TenantBillingAccountView.as_view(), name="tenant-billing-account"),
    path("billing/invoices/", OwnerInvoiceListView.as_view(), name="owner-invoices"),
    path("tenant/billing/invoices/", TenantInvoiceListView.as_view(), name="tenant-invoices"),
    path("billing/invoices/generate/", GenerateInvoiceView.as_view(), name="billing-invoice-generate"),
    path("billing/invoices/<uuid:invoice_id>/dunning/", DunningTriggerView.as_view(), name="billing-invoice-dunning"),
    path("billing/payments/", PaymentWebhookView.as_view(), name="billing-payments"),
    path("billing/reconciliations/", OwnerCommercialReconciliationListView.as_view(), name="billing-reconciliations"),
    path("billing/reconciliations/trigger/", OwnerCommercialReconciliationTriggerView.as_view(), name="billing-reconciliations-trigger"),
    path("billing/reconciliations/<uuid:reconciliation_id>/resolve/", OwnerCommercialReconciliationResolveView.as_view(), name="billing-reconciliations-resolve"),
]
