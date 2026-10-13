from rest_framework import serializers

from apps.assignments.models import UserProductAssignment
from apps.entitlements.models import OrganizationProductEntitlement
from apps.organizations.models import Organization
from apps.plans.models import PlanProduct
from apps.product_registry.models import CatalogStatus, Product, ProductStatus


class DeveloperPlanPriceSerializer(serializers.Serializer):
    currency = serializers.CharField()
    amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    billing_interval = serializers.CharField()


class DeveloperPlanSerializer(serializers.Serializer):
    plan_version_id = serializers.UUIDField()
    plan_name = serializers.CharField()
    plan_code = serializers.CharField()
    version = serializers.IntegerField()
    prices = DeveloperPlanPriceSerializer(many=True)


class DeveloperFeatureSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    code = serializers.CharField()
    name = serializers.CharField()
    description = serializers.CharField()


class DeveloperModuleSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    code = serializers.CharField()
    name = serializers.CharField()
    description = serializers.CharField()
    features = DeveloperFeatureSerializer(many=True)


class DeveloperCatalogProductSerializer(serializers.ModelSerializer):
    modules = serializers.SerializerMethodField()
    plans = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            "id",
            "code",
            "name",
            "description",
            "modules",
            "plans",
        ]

    def get_modules(self, obj):
        modules = obj.modules.filter(status=CatalogStatus.ACTIVE).order_by("display_order", "id")
        result = []
        for mod in modules:
            features = mod.features.filter(status=CatalogStatus.ACTIVE).order_by("display_order", "id")
            result.append({
                "id": mod.id,
                "code": mod.code,
                "name": mod.name,
                "description": mod.description,
                "features": [
                    {
                        "id": feat.id,
                        "code": feat.code,
                        "name": feat.name,
                        "description": feat.description,
                    }
                    for feat in features
                ],
            })
        return result

    def get_plans(self, obj):
        plan_links = (
            PlanProduct.objects.filter(
                product=obj,
                plan_version__status="active",
                plan_version__plan__is_public=True,
            )
            .select_related("plan_version", "plan_version__plan")
            .prefetch_related("plan_version__prices")
        )
        result = []
        for pl in plan_links:
            pv = pl.plan_version
            prices = pv.prices.all().order_by("currency", "billing_interval")
            result.append({
                "plan_version_id": pv.id,
                "plan_name": pv.plan.name,
                "plan_code": pv.plan.code,
                "version": pv.version,
                "prices": [
                    {
                        "currency": pr.currency,
                        "amount": pr.amount,
                        "billing_interval": pr.billing_interval,
                    }
                    for pr in prices
                ],
            })
        return result


class DeveloperOrganizationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Organization
        fields = [
            "id",
            "code",
            "name",
            "status",
            "created_at",
        ]


class DeveloperEntitlementSerializer(serializers.ModelSerializer):
    product_id = serializers.UUIDField(source="product.id")
    product_code = serializers.CharField(source="product.code")
    product_name = serializers.CharField(source="product.name")
    granted_at = serializers.DateTimeField(source="created_at")
    expires_at = serializers.SerializerMethodField()

    class Meta:
        model = OrganizationProductEntitlement
        fields = [
            "id",
            "product_id",
            "product_code",
            "product_name",
            "status",
            "granted_at",
            "expires_at",
        ]

    def get_expires_at(self, obj):
        return None


class DeveloperAssignmentSerializer(serializers.ModelSerializer):
    user_id = serializers.UUIDField(source="user.id")
    user_email = serializers.EmailField(source="user.email")
    user_full_name = serializers.CharField(source="user.full_name")
    product_id = serializers.UUIDField(source="product.id")
    product_code = serializers.CharField(source="product.code")
    product_name = serializers.CharField(source="product.name")
    created_at = serializers.DateTimeField(source="assigned_at")
    updated_at = serializers.SerializerMethodField()

    class Meta:
        model = UserProductAssignment
        fields = [
            "id",
            "user_id",
            "user_email",
            "user_full_name",
            "product_id",
            "product_code",
            "product_name",
            "status",
            "created_at",
            "updated_at",
        ]

    def get_updated_at(self, obj):
        return obj.last_reactivated_at or obj.last_suspended_at or obj.revoked_at or obj.assigned_at


ALLOWED_DEVELOPER_SCOPES = [
    "catalog:read",
    "organization:read",
    "entitlements:read",
    "assignments:read",
]


class DeveloperApplicationSerializer(serializers.ModelSerializer):
    organization = serializers.SerializerMethodField()
    created_by = serializers.SerializerMethodField()
    active_keys_count = serializers.SerializerMethodField()

    class Meta:
        from apps.developer_console.models import DeveloperApplication
        model = DeveloperApplication
        fields = [
            "id",
            "name",
            "description",
            "status",
            "organization",
            "created_by",
            "active_keys_count",
            "created_at",
            "updated_at",
        ]

    def get_organization(self, obj):
        return {
            "id": str(obj.organization.id),
            "code": obj.organization.code,
            "name": obj.organization.name,
        }

    def get_created_by(self, obj):
        return {
            "id": str(obj.created_by.id),
            "email": obj.created_by.email,
            "full_name": getattr(obj.created_by, "full_name", ""),
        }

    def get_active_keys_count(self, obj):
        return obj.api_keys.filter(status="active").count()


class DeveloperApplicationCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=128)
    description = serializers.CharField(required=False, allow_blank=True, default="")


class DeveloperApplicationUpdateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=128, required=False)
    description = serializers.CharField(required=False, allow_blank=True)


class DeveloperApiKeySerializer(serializers.ModelSerializer):
    application_id = serializers.UUIDField(source="application.id")

    class Meta:
        from apps.developer_console.models import DeveloperApiKey
        model = DeveloperApiKey
        fields = [
            "id",
            "application_id",
            "name",
            "key_prefix",
            "scopes",
            "status",
            "expires_at",
            "last_used_at",
            "created_at",
            "revoked_at",
        ]


class DeveloperApiKeyCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=64)
    scopes = serializers.ListField(
        child=serializers.ChoiceField(choices=ALLOWED_DEVELOPER_SCOPES),
        allow_empty=False,
    )
    expires_at = serializers.DateTimeField(required=False, allow_null=True, default=None)

    def validate_scopes(self, value):
        if not value:
            raise serializers.ValidationError("At least one scope must be selected.")
        invalid = set(value) - set(ALLOWED_DEVELOPER_SCOPES)
        if invalid:
            raise serializers.ValidationError(f"Invalid scopes: {sorted(list(invalid))}")
        return list(dict.fromkeys(value))  # preserve order, unique


class DeveloperApiKeyCreatedResponseSerializer(serializers.ModelSerializer):
    application_id = serializers.UUIDField(source="application.id")
    plaintext_key = serializers.CharField()

    class Meta:
        from apps.developer_console.models import DeveloperApiKey
        model = DeveloperApiKey
        fields = [
            "id",
            "application_id",
            "name",
            "key_prefix",
            "scopes",
            "status",
            "plaintext_key",
            "expires_at",
            "last_used_at",
            "created_at",
            "revoked_at",
        ]


class DeveloperWebhookSubscriptionSerializer(serializers.ModelSerializer):
    application_id = serializers.UUIDField(source="application.id")

    class Meta:
        from apps.developer_console.models import DeveloperWebhookSubscription
        model = DeveloperWebhookSubscription
        fields = [
            "id",
            "application_id",
            "target_url",
            "event_topics",
            "status",
            "created_at",
            "updated_at",
        ]


class DeveloperWebhookSubscriptionCreateSerializer(serializers.Serializer):
    target_url = serializers.URLField(max_length=512)
    event_topics = serializers.ListField(
        child=serializers.CharField(max_length=64),
        allow_empty=False,
    )


class DeveloperWebhookSubscriptionCreatedResponseSerializer(serializers.ModelSerializer):
    application_id = serializers.UUIDField(source="application.id")
    signing_secret = serializers.CharField()

    class Meta:
        from apps.developer_console.models import DeveloperWebhookSubscription
        model = DeveloperWebhookSubscription
        fields = [
            "id",
            "application_id",
            "target_url",
            "event_topics",
            "status",
            "signing_secret",
            "created_at",
            "updated_at",
        ]


class DeveloperWebhookSubscriptionUpdateSerializer(serializers.Serializer):
    target_url = serializers.URLField(max_length=512, required=False)
    event_topics = serializers.ListField(
        child=serializers.CharField(max_length=64),
        required=False,
    )


class DeveloperWebhookDeliverySerializer(serializers.ModelSerializer):
    subscription_id = serializers.UUIDField(source="subscription.id")

    class Meta:
        from apps.developer_console.models import DeveloperWebhookDelivery
        model = DeveloperWebhookDelivery
        fields = [
            "id",
            "subscription_id",
            "event_id",
            "event_type",
            "payload",
            "status",
            "status_code",
            "attempt_count",
            "max_attempts",
            "next_retry_at",
            "delivered_at",
            "response_body",
            "created_at",
            "updated_at",
        ]
