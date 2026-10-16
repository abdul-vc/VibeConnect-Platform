"""VibeConnect Phase 2C Subscriptions API Views.

Implements Platform Owner-only REST endpoints for organization subscriptions
with strict authentication, permission enforcement, filter validation, and domain exception handling.
"""

import uuid
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError
from django.db.models import Q
from rest_framework import exceptions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.identity.authentication import EnforcedSessionAuthentication
from apps.identity.permissions import IsPlatformOwner
from apps.subscriptions.models import (
    OrganizationSubscription,
    SubscriptionCapabilityEntitlement,
    SubscriptionModuleEntitlement,
    SubscriptionProductEntitlement,
    SubscriptionQuotaEntitlement,
    SubscriptionStatus,
)
from apps.subscriptions.pagination import SubscriptionDefaultPagination
from apps.subscriptions.serializers import (
    OrganizationSubscriptionSerializer,
    SubscriptionCancelSerializer,
    SubscriptionCapabilityEntitlementSerializer,
    SubscriptionChangePlanSerializer,
    SubscriptionCreateActiveSerializer,
    SubscriptionEmptyActionSerializer,
    SubscriptionModuleEntitlementSerializer,
    SubscriptionProductEntitlementSerializer,
    SubscriptionQuotaEntitlementSerializer,
    SubscriptionStartTrialSerializer,
    SubscriptionSuspendSerializer,
)
from apps.subscriptions.services import (
    SubscriptionNotFoundError,
    SubscriptionValidationError,
    cancel_subscription,
    change_subscription_plan,
    convert_trial_to_active,
    create_active_subscription,
    reactivate_subscription,
    reconcile_subscription_entitlements,
    start_subscription_trial,
    suspend_subscription,
)


def _parse_uuid_or_404(val: str, name: str = "id") -> uuid.UUID:
    try:
        return uuid.UUID(str(val))
    except (ValueError, TypeError, AttributeError):
        raise exceptions.NotFound(f"Resource with {name}='{val}' not found.")


def _validate_singleton_query_params(request, supported_params: set[str]):
    for key in request.GET.keys():
        if key not in supported_params:
            raise exceptions.ValidationError({key: [f"Unexpected query parameter '{key}'."]})
        if len(request.GET.getlist(key)) > 1:
            raise exceptions.ValidationError({key: [f"Duplicate '{key}' parameter is not permitted."]})


class SubscriptionViewSet(viewsets.GenericViewSet):
    """ViewSet managing Organization Subscriptions."""

    authentication_classes = [EnforcedSessionAuthentication]
    permission_classes = [IsPlatformOwner]
    pagination_class = SubscriptionDefaultPagination
    serializer_class = OrganizationSubscriptionSerializer
    http_method_names = ["get", "post", "head", "options"]

    SUPPORTED_PARAMS = {
        "organization_id",
        "plan_id",
        "status",
        "search",
        "ordering",
        "page",
        "page_size",
    }
    ORDERING_MAP = {
        "created_at": ["created_at", "id"],
        "-created_at": ["-created_at", "-id"],
        "status": ["status", "-created_at", "id"],
        "-status": ["-status", "-created_at", "-id"],
        "current_period_end": ["current_period_end", "id"],
        "-current_period_end": ["-current_period_end", "-id"],
    }

    def handle_exception(self, exc):
        if isinstance(exc, SubscriptionNotFoundError):
            return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)

        if isinstance(exc, SubscriptionValidationError):
            return Response({"detail": [str(exc)]}, status=status.HTTP_400_BAD_REQUEST)

        if isinstance(exc, DjangoValidationError):
            if hasattr(exc, "message_dict"):
                return Response(exc.message_dict, status=status.HTTP_400_BAD_REQUEST)
            if hasattr(exc, "messages"):
                return Response({"detail": exc.messages}, status=status.HTTP_400_BAD_REQUEST)
            return Response({"detail": [str(exc)]}, status=status.HTTP_400_BAD_REQUEST)

        if isinstance(exc, IntegrityError):
            return Response(
                {"detail": ["Database integrity constraint violation."]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return super().handle_exception(exc)

    def get_queryset(self):
        _validate_singleton_query_params(self.request, self.SUPPORTED_PARAMS)

        qs = OrganizationSubscription.objects.select_related(
            "organization",
            "plan_version__plan",
            "plan_price",
            "created_by",
            "updated_by",
        ).all()

        # Filters
        org_id = self.request.query_params.get("organization_id")
        if org_id is not None:
            try:
                org_uuid = uuid.UUID(org_id)
            except ValueError:
                raise exceptions.ValidationError({"organization_id": ["Must be a valid UUID."]})
            qs = qs.filter(organization_id=org_uuid)

        plan_id = self.request.query_params.get("plan_id")
        if plan_id is not None:
            try:
                plan_uuid = uuid.UUID(plan_id)
            except ValueError:
                raise exceptions.ValidationError({"plan_id": ["Must be a valid UUID."]})
            qs = qs.filter(plan_version__plan_id=plan_uuid)

        status_param = self.request.query_params.get("status")
        if status_param is not None:
            if status_param not in SubscriptionStatus.values:
                raise exceptions.ValidationError(
                    {"status": [f"Invalid status '{status_param}'. Allowed: {list(SubscriptionStatus.values)}."]}
                )
            qs = qs.filter(status=status_param)

        search = self.request.query_params.get("search")
        if search is not None:
            s = search.strip()
            if s:
                qs = qs.filter(
                    Q(plan_code_snapshot__icontains=s)
                    | Q(plan_name_snapshot__icontains=s)
                    | Q(organization__code__icontains=s)
                    | Q(organization__name__icontains=s)
                )

        ordering = self.request.query_params.get("ordering", "-created_at")
        if ordering not in self.ORDERING_MAP:
            raise exceptions.ValidationError({"ordering": [f"Invalid ordering field '{ordering}'."]})
        qs = qs.order_by(*self.ORDERING_MAP[ordering])

        return qs

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    def retrieve(self, request, *args, **kwargs):
        sub_id = _parse_uuid_or_404(kwargs.get("pk"), "subscription_id")
        try:
            sub = self.get_queryset().get(pk=sub_id)
        except OrganizationSubscription.DoesNotExist:
            raise exceptions.NotFound(f"Resource with subscription_id='{sub_id}' not found.")
        serializer = self.get_serializer(sub)
        return Response(serializer.data)

    def create(self, request, *args, **kwargs):
        serializer = SubscriptionCreateActiveSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        sub = create_active_subscription(
            organization_id=data["organization_id"],
            plan_version_id=data["plan_version_id"],
            plan_price_id=data["plan_price_id"],
            actor=request.user,
            current_period_start=data.get("current_period_start"),
            change_reason=data.get("change_reason", ""),
        )

        sub_instance = self.get_queryset().get(pk=sub.id)
        return Response(self.get_serializer(sub_instance).data, status=status.HTTP_201_CREATED)

    def start_trial(self, request, *args, **kwargs):
        serializer = SubscriptionStartTrialSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        sub = start_subscription_trial(
            organization_id=data["organization_id"],
            plan_version_id=data["plan_version_id"],
            plan_price_id=data["plan_price_id"],
            actor=request.user,
            trial_days=data.get("trial_days", 14),
            change_reason=data.get("change_reason", ""),
        )

        sub_instance = self.get_queryset().get(pk=sub.id)
        return Response(self.get_serializer(sub_instance).data, status=status.HTTP_201_CREATED)

    def convert_trial(self, request, *args, **kwargs):
        sub_id = _parse_uuid_or_404(kwargs.get("pk"), "subscription_id")
        serializer = SubscriptionEmptyActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        sub = convert_trial_to_active(
            subscription_id=sub_id,
            actor=request.user,
        )

        sub_instance = self.get_queryset().get(pk=sub.id)
        return Response(self.get_serializer(sub_instance).data, status=status.HTTP_200_OK)

    def change_plan(self, request, *args, **kwargs):
        sub_id = _parse_uuid_or_404(kwargs.get("pk"), "subscription_id")
        serializer = SubscriptionChangePlanSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        successor = change_subscription_plan(
            subscription_id=sub_id,
            new_plan_version_id=data["new_plan_version_id"],
            new_plan_price_id=data["new_plan_price_id"],
            actor=request.user,
            change_reason=data.get("change_reason", ""),
        )

        sub_instance = self.get_queryset().get(pk=successor.id)
        return Response(self.get_serializer(sub_instance).data, status=status.HTTP_200_OK)

    def suspend(self, request, *args, **kwargs):
        sub_id = _parse_uuid_or_404(kwargs.get("pk"), "subscription_id")
        serializer = SubscriptionSuspendSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        sub = suspend_subscription(
            subscription_id=sub_id,
            actor=request.user,
            reason=data.get("reason", ""),
        )

        sub_instance = self.get_queryset().get(pk=sub.id)
        return Response(self.get_serializer(sub_instance).data, status=status.HTTP_200_OK)

    def reactivate(self, request, *args, **kwargs):
        sub_id = _parse_uuid_or_404(kwargs.get("pk"), "subscription_id")
        serializer = SubscriptionEmptyActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        sub = reactivate_subscription(
            subscription_id=sub_id,
            actor=request.user,
        )

        sub_instance = self.get_queryset().get(pk=sub.id)
        return Response(self.get_serializer(sub_instance).data, status=status.HTTP_200_OK)

    def cancel(self, request, *args, **kwargs):
        sub_id = _parse_uuid_or_404(kwargs.get("pk"), "subscription_id")
        serializer = SubscriptionCancelSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        sub = cancel_subscription(
            subscription_id=sub_id,
            actor=request.user,
            reason=data.get("reason", ""),
        )

        sub_instance = self.get_queryset().get(pk=sub.id)
        return Response(self.get_serializer(sub_instance).data, status=status.HTTP_200_OK)

    def reconcile(self, request, *args, **kwargs):
        sub_id = _parse_uuid_or_404(kwargs.get("pk"), "subscription_id")
        serializer = SubscriptionEmptyActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        repaired_count = reconcile_subscription_entitlements(
            subscription_id=sub_id,
            actor=request.user,
        )

        return Response({"repaired_count": repaired_count}, status=status.HTTP_200_OK)

    def entitlements(self, request, *args, **kwargs):
        sub_id = _parse_uuid_or_404(kwargs.get("pk"), "subscription_id")
        try:
            sub = OrganizationSubscription.objects.get(pk=sub_id)
        except OrganizationSubscription.DoesNotExist:
            raise exceptions.NotFound(f"Resource with subscription_id='{sub_id}' not found.")

        products = SubscriptionProductEntitlement.objects.filter(subscription=sub).order_by("created_at")
        modules = SubscriptionModuleEntitlement.objects.filter(subscription=sub).order_by("created_at")
        capabilities = SubscriptionCapabilityEntitlement.objects.filter(subscription=sub).order_by("created_at")
        quotas = SubscriptionQuotaEntitlement.objects.filter(subscription=sub).order_by("created_at")

        return Response(
            {
                "subscription_id": str(sub.id),
                "organization_id": str(sub.organization_id),
                "products": SubscriptionProductEntitlementSerializer(products, many=True).data,
                "modules": SubscriptionModuleEntitlementSerializer(modules, many=True).data,
                "capabilities": SubscriptionCapabilityEntitlementSerializer(capabilities, many=True).data,
                "quotas": SubscriptionQuotaEntitlementSerializer(quotas, many=True).data,
            },
            status=status.HTTP_200_OK,
        )
