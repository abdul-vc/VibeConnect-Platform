from rest_framework import serializers

from apps.billing.models import (
    BillingAccount,
    Invoice,
    InvoiceLine,
    Payment,
    TaxRate,
)


class BillingAccountSerializer(serializers.ModelSerializer):
    organization_name = serializers.CharField(source="organization.name", read_only=True)
    organization_code = serializers.CharField(source="organization.code", read_only=True)

    class Meta:
        model = BillingAccount
        fields = [
            "id",
            "organization",
            "organization_name",
            "organization_code",
            "legal_name",
            "tax_id",
            "billing_email",
            "status",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class InvoiceLineSerializer(serializers.ModelSerializer):
    class Meta:
        model = InvoiceLine
        fields = [
            "id",
            "description",
            "quantity",
            "unit_price",
            "tax_amount",
            "total",
            "created_at",
        ]


class InvoiceSerializer(serializers.ModelSerializer):
    lines = InvoiceLineSerializer(many=True, read_only=True)
    organization_name = serializers.CharField(source="organization.name", read_only=True)
    organization_code = serializers.CharField(source="organization.code", read_only=True)

    class Meta:
        model = Invoice
        fields = [
            "id",
            "organization",
            "organization_name",
            "organization_code",
            "subscription",
            "invoice_number",
            "currency",
            "subtotal",
            "tax_total",
            "total",
            "status",
            "due_date",
            "issued_at",
            "lines",
            "created_at",
            "updated_at",
        ]


class PaymentRecordSerializer(serializers.Serializer):
    invoice_id = serializers.UUIDField(required=True)
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, required=True)
    currency = serializers.CharField(max_length=10, default="USD")
    idempotency_key = serializers.CharField(max_length=128, required=True)
    processor_ref = serializers.CharField(max_length=128, required=False, allow_blank=True, default="")


class PaymentSerializer(serializers.ModelSerializer):
    invoice_number = serializers.CharField(source="invoice.invoice_number", read_only=True)

    class Meta:
        model = Payment
        fields = [
            "id",
            "invoice",
            "invoice_number",
            "processor_ref",
            "amount",
            "currency",
            "status",
            "idempotency_key",
            "recorded_at",
            "created_at",
        ]


class CommercialReconciliationSerializer(serializers.ModelSerializer):
    organization_name = serializers.CharField(source="organization.name", read_only=True)
    organization_code = serializers.CharField(source="organization.code", read_only=True)
    resolved_by_email = serializers.CharField(source="resolved_by.email", read_only=True)

    class Meta:
        from apps.billing.models import CommercialReconciliation
        model = CommercialReconciliation
        fields = [
            "id",
            "organization",
            "organization_name",
            "organization_code",
            "subscription",
            "issue_code",
            "status",
            "details",
            "detected_at",
            "resolved_at",
            "resolved_by",
            "resolved_by_email",
            "resolution_reason",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class ResolveReconciliationSerializer(serializers.Serializer):
    resolution_reason = serializers.CharField(max_length=1000, required=True)

