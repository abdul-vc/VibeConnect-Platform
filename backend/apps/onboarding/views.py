"""Tenant Onboarding API Views & Serializers (Phase 3B).

Provides:
- POST /api/v1/onboarding/cases/ (Initialize new case)
- GET /api/v1/onboarding/cases/<id>/ (Retrieve current state / resume)
- PATCH /api/v1/onboarding/cases/<id>/step/ (Advance step with validation)
"""

from django.conf import settings
from rest_framework import exceptions, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.identity.authentication import EnforcedSessionAuthentication
from apps.identity.permissions import IsPlatformOwner
from apps.onboarding.models import OnboardingCaseStatus, OnboardingStep, TenantOnboardingCase
from apps.onboarding.services import (
    InvalidStepTransitionError,
    OnboardingCaseConflictError,
    OnboardingValidationError,
    create_onboarding_case,
    transition_case_step,
)


class TenantOnboardingCaseSerializer(serializers.ModelSerializer):
    created_organization_id = serializers.UUIDField(source="created_organization.id", read_only=True)
    plan_name = serializers.CharField(source="plan_version.plan.name", read_only=True)
    plan_version_number = serializers.IntegerField(source="plan_version.version", read_only=True)
    initial_admin_activation_url = serializers.SerializerMethodField()

    def get_initial_admin_activation_url(self, obj):
        raw_token = getattr(obj, "initial_admin_activation_token", None)
        if not raw_token:
            return None
        frontend_base = getattr(settings, "FRONTEND_BASE_URL", "").rstrip("/")
        return f"{frontend_base}/invitations/accept/{raw_token}"

    class Meta:
        model = TenantOnboardingCase
        fields = [
            "id",
            "status",
            "current_step",
            "organization_code",
            "organization_name",
            "organization_description",
            "admin_email",
            "admin_full_name",
            "plan_version",
            "plan_version_number",
            "plan_name",
            "plan_price",
            "is_trial",
            "selected_product_ids",
            "feature_ceilings",
            "created_organization_id",
            "initial_admin_activation_url",
            "started_at",
            "completed_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "status",
            "started_at",
            "completed_at",
            "updated_at",
            "created_organization_id",
            "initial_admin_activation_url",
            "plan_name",
            "plan_version_number",
        ]



class StepTransitionPayloadSerializer(serializers.Serializer):
    target_step = serializers.ChoiceField(choices=OnboardingStep.choices)
    step_data = serializers.DictField(required=False, default=dict)


class TenantOnboardingCaseViewSet(viewsets.GenericViewSet):
    """Platform Owner API for managing Tenant Onboarding Cases."""

    authentication_classes = [EnforcedSessionAuthentication]
    permission_classes = [IsPlatformOwner]
    serializer_class = TenantOnboardingCaseSerializer
    queryset = TenantOnboardingCase.objects.select_related("plan_version__plan", "plan_price", "created_organization").all()

    def create(self, request, *args, **kwargs):
        case = create_onboarding_case(actor=request.user)
        serializer = self.get_serializer(case)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def retrieve(self, request, pk=None, *args, **kwargs):
        case = self.get_object()
        serializer = self.get_serializer(case)
        return Response(serializer.data)

    @action(detail=True, methods=["patch"], url_path="step")
    def transition_step(self, request, pk=None):
        case = self.get_object()
        payload_serializer = StepTransitionPayloadSerializer(data=request.data)
        payload_serializer.is_valid(raise_exception=True)

        target_step = payload_serializer.validated_data["target_step"]
        step_data = payload_serializer.validated_data.get("step_data", {})

        try:
            updated_case = transition_case_step(
                case_id=case.id,
                target_step=target_step,
                step_data=step_data,
                actor=request.user,
            )
        except OnboardingCaseConflictError as exc:
            raise exceptions.ValidationError({"organization_code": [str(exc)]})
        except (InvalidStepTransitionError, OnboardingValidationError) as exc:
            raise exceptions.ValidationError({"detail": str(exc)})

        return Response(self.get_serializer(updated_case).data, status=status.HTTP_200_OK)

    @action(detail=False, methods=["get"], url_path="options")
    def options(self, request, *args, **kwargs):
        """Return available active products with catalog modules/features and tenant console modules/permissions."""
        from apps.access_control.models import AccessPermission, ConsoleModule
        from apps.product_registry.models import Product

        products = []
        for p in Product.objects.filter(status="active").order_by("name"):
            modules = []
            for m in p.modules.filter(status="active").order_by("display_order", "name"):
                features = [
                    {
                        "id": str(f.id),
                        "code": f.code,
                        "name": f.name,
                        "description": f.description,
                        "display_order": f.display_order,
                    }
                    for f in m.features.filter(status="active").order_by("display_order", "name")
                ]
                modules.append({
                    "id": str(m.id),
                    "code": m.code,
                    "name": m.name,
                    "description": m.description,
                    "display_order": m.display_order,
                    "features": features,
                })
            products.append({
                "id": str(p.id),
                "code": p.code,
                "name": p.name,
                "description": p.description,
                "modules": modules,
            })

        console_modules = []
        for cm in ConsoleModule.objects.filter(target_context="tenant", is_active=True).order_by("sort_order", "key"):
            permissions = [
                {
                    "key": perm.key,
                    "display_name": perm.display_name,
                    "description": perm.description,
                }
                for perm in cm.permissions.filter(is_active=True).order_by("key")
            ]
            console_modules.append({
                "key": cm.key,
                "display_name": cm.display_name,
                "description": cm.description,
                "is_core": cm.is_core,
                "permissions": permissions,
            })

        return Response({
            "products": products,
            "console_modules": console_modules,
        })

