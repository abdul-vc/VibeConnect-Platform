"""VibeConnect Phase 2B Plans API Views.

Implements compact ViewSets for Plan, PlanVersion, PlanPrice, PlanProduct,
PlanModule, PlanCapability, and PlanQuota with EnforcedSessionAuthentication,
IsPlatformOwner authorization, strict query parameter validation, deterministic
ordering, non-N+1 annotations, and centralized domain-to-HTTP exception mapping.
"""

import uuid
from django.core.exceptions import ObjectDoesNotExist, ValidationError as DjangoValidationError
from django.db import IntegrityError
from django.db.models import Case, Exists, OuterRef, Prefetch, Q, Subquery, Value, When
from rest_framework import exceptions, status, viewsets
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.identity.authentication import EnforcedSessionAuthentication
from apps.identity.permissions import IsPlatformOwner
from apps.plans.models import (
    BillingInterval,
    Plan,
    PlanCapability,
    PlanCurrency,
    PlanModule,
    PlanPrice,
    PlanProduct,
    PlanQuota,
    PlanVersion,
    PlanVersionStatus,
    QuotaScope,
)
from apps.plans.pagination import PlanDefaultPagination, PlanLargePagination
from apps.plans.serializers import (
    PlanCapabilityCreateSerializer,
    PlanCapabilitySerializer,
    PlanCreateSerializer,
    PlanModuleCreateSerializer,
    PlanModuleSerializer,
    PlanPriceCreateSerializer,
    PlanPriceSerializer,
    PlanPriceUpdateSerializer,
    PlanProductCreateSerializer,
    PlanProductSerializer,
    PlanQuotaCreateSerializer,
    PlanQuotaSerializer,
    PlanQuotaUpdateSerializer,
    PlanSerializer,
    PlanUpdateSerializer,
    PlanVersionCloneSerializer,
    PlanVersionCreateSerializer,
    PlanVersionEmptyActionSerializer,
    PlanVersionSerializer,
    PlanVersionUpdateSerializer,
)
from apps.plans.services import (
    activate_plan_version,
    add_plan_capability,
    add_plan_module,
    add_plan_product,
    clone_plan_version,
    create_draft_version,
    create_plan,
    create_plan_price,
    create_plan_quota,
    evaluate_activation_readiness,
    remove_plan_capability,
    remove_plan_module,
    remove_plan_price,
    remove_plan_product,
    remove_plan_quota,
    retire_plan_version,
    update_draft_version,
    update_plan,
    update_plan_price,
    update_plan_quota,
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


CONSTRAINT_MESSAGES = {
    "plan_code_ci_unq": "A plan with this code already exists.",
    "plan_price_ver_curr_int_unq": "A price with this currency and interval already exists for this version.",
    "plan_product_ver_prod_unq": "This product is already packaged in this plan version.",
    "plan_module_ver_mod_unq": "This module is already packaged in this plan version.",
    "plan_capability_ver_cap_unq": "This capability is already packaged in this plan version.",
    "quota_plan_scope_key_unq": "A quota with this scope and key already exists for this plan version.",
    "quota_product_scope_key_unq": "A quota with this scope and key already exists for this plan version.",
    "quota_module_scope_key_unq": "A quota with this scope and key already exists for this plan version.",
    "quota_capability_scope_key_unq": "A quota with this scope and key already exists for this plan version.",
}


class _PlanBaseViewSet(viewsets.GenericViewSet):
    authentication_classes = [EnforcedSessionAuthentication]
    permission_classes = [IsPlatformOwner]

    def handle_exception(self, exc):
        if isinstance(exc, (exceptions.NotFound, ObjectDoesNotExist)):
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        if isinstance(exc, IntegrityError):
            cause = getattr(exc, "__cause__", None)
            diag = getattr(cause, "diag", None)
            constraint = getattr(diag, "constraint_name", "") or ""
            if not constraint:
                err_str = " ".join(str(a) for a in exc.args).lower()
                for c in CONSTRAINT_MESSAGES:
                    if c in err_str:
                        constraint = c
                        break

            if constraint in CONSTRAINT_MESSAGES:
                return Response({"detail": CONSTRAINT_MESSAGES[constraint]}, status=status.HTTP_409_CONFLICT)
            return Response({"detail": "Conflict on database constraint."}, status=status.HTTP_409_CONFLICT)

        if isinstance(exc, DjangoValidationError):
            msg = str(exc)
            msg_lower = msg.lower()
            if any(term in msg for term in ["draft versions can be modified", "Mutation rejected: PlanVersion", " in status ", "immutable"]):
                return Response({"detail": "PlanVersion is immutable in active or retired status."}, status=status.HTTP_409_CONFLICT)

            if "plan_code_ci_unq" in msg or ("plan with this code" in msg_lower and "already exists" in msg_lower):
                return Response({"detail": CONSTRAINT_MESSAGES["plan_code_ci_unq"]}, status=status.HTTP_409_CONFLICT)
            if "plan_price_ver_curr_int_unq" in msg or ("currency" in msg_lower and "billing interval already exists" in msg_lower):
                return Response({"detail": CONSTRAINT_MESSAGES["plan_price_ver_curr_int_unq"]}, status=status.HTTP_409_CONFLICT)
            if "plan_product_ver_prod_unq" in msg or ("plan product with this" in msg_lower and "already exists" in msg_lower):
                return Response({"detail": CONSTRAINT_MESSAGES["plan_product_ver_prod_unq"]}, status=status.HTTP_409_CONFLICT)
            if "plan_module_ver_mod_unq" in msg or ("plan module with this" in msg_lower and "already exists" in msg_lower):
                return Response({"detail": CONSTRAINT_MESSAGES["plan_module_ver_mod_unq"]}, status=status.HTTP_409_CONFLICT)
            if "plan_capability_ver_cap_unq" in msg or ("plan capability with this" in msg_lower and "already exists" in msg_lower):
                return Response({"detail": CONSTRAINT_MESSAGES["plan_capability_ver_cap_unq"]}, status=status.HTTP_409_CONFLICT)
            for qk in ("quota_plan_scope_key_unq", "quota_product_scope_key_unq", "quota_module_scope_key_unq", "quota_capability_scope_key_unq"):
                if qk in msg:
                    return Response({"detail": CONSTRAINT_MESSAGES[qk]}, status=status.HTTP_409_CONFLICT)

            if hasattr(exc, "message_dict"):
                return Response(exc.message_dict, status=status.HTTP_400_BAD_REQUEST)
            if hasattr(exc, "messages"):
                return Response({"detail": exc.messages}, status=status.HTTP_400_BAD_REQUEST)
            return Response({"detail": [msg]}, status=status.HTTP_400_BAD_REQUEST)

        return super().handle_exception(exc)


# ---------------------------------------------------------------------------
# 1. Plan ViewSet
# ---------------------------------------------------------------------------

class PlanViewSet(_PlanBaseViewSet):
    """ViewSet managing Plan packaging families."""

    pagination_class = PlanDefaultPagination
    serializer_class = PlanSerializer
    http_method_names = ["get", "post", "patch", "head", "options"]

    SUPPORTED_PARAMS = {
        "search", "has_active_version", "has_draft_version", "catalog_health",
        "is_public", "ordering", "page", "page_size",
    }
    ORDERING_MAP = {
        "created_at": ["created_at", "id"],
        "-created_at": ["-created_at", "-id"],
        "code": ["code", "id"],
        "-code": ["-code", "-id"],
        "name": ["name", "id"],
        "-name": ["-name", "-id"],
    }

    def _attach_computed_plan_attributes(self, plans):
        for plan in plans:
            versions = list(plan.versions.all())
            plan.total_versions_count = len(versions)
            plan.active_version = next((v for v in versions if v.status == PlanVersionStatus.ACTIVE), None)
            plan.latest_version = versions[0] if versions else None

            # Dynamic catalog health
            target_v = plan.active_version if plan.active_version else plan.latest_version
            if target_v:
                is_degraded = (
                    any(p.product.status != "active" for p in target_v.packaged_products.all())
                    or any(m.module.status != "active" for m in target_v.packaged_modules.all())
                    or any(
                        c.capability.status != "active" or (c.capability.feature and c.capability.feature.status != "active")
                        for c in target_v.packaged_capabilities.all()
                    )
                )
                plan.catalog_health = "degraded" if is_degraded else "healthy"
            else:
                plan.catalog_health = "healthy"

    def get_queryset(self):
        _validate_singleton_query_params(self.request, self.SUPPORTED_PARAMS)

        target_v_subquery = Subquery(
            PlanVersion.objects.filter(plan=OuterRef("pk"))
            .order_by(Case(When(status=PlanVersionStatus.ACTIVE, then=Value(0)), default=Value(1)), "-version")
            .values("id")[:1]
        )
        is_degraded_expr = (
            Exists(PlanProduct.objects.filter(plan_version_id=target_v_subquery).exclude(product__status="active"))
            | Exists(PlanModule.objects.filter(plan_version_id=target_v_subquery).exclude(module__status="active"))
            | Exists(
                PlanCapability.objects.filter(plan_version_id=target_v_subquery).filter(
                    ~Q(capability__status="active") | (Q(capability__feature__isnull=False) & ~Q(capability__feature__status="active"))
                )
            )
        )

        qs = Plan.objects.select_related("created_by", "updated_by").prefetch_related(
            Prefetch("versions", queryset=PlanVersion.objects.order_by("-version").prefetch_related(
                "packaged_products__product",
                "packaged_modules__module",
                "packaged_capabilities__capability__feature",
            ))
        )

        # Filters
        search = self.request.query_params.get("search")
        if search is not None:
            s = search.strip()
            if s:
                qs = qs.filter(Q(name__icontains=s) | Q(code__icontains=s))

        has_active = self.request.query_params.get("has_active_version")
        if has_active is not None:
            if has_active == "true":
                qs = qs.filter(Exists(PlanVersion.objects.filter(plan=OuterRef("pk"), status=PlanVersionStatus.ACTIVE)))
            elif has_active == "false":
                qs = qs.filter(~Exists(PlanVersion.objects.filter(plan=OuterRef("pk"), status=PlanVersionStatus.ACTIVE)))
            elif has_active != "all":
                raise exceptions.ValidationError({"has_active_version": ["Allowed values: true, false, all."]})

        has_draft = self.request.query_params.get("has_draft_version")
        if has_draft is not None:
            if has_draft == "true":
                qs = qs.filter(Exists(PlanVersion.objects.filter(plan=OuterRef("pk"), status=PlanVersionStatus.DRAFT)))
            elif has_draft == "false":
                qs = qs.filter(~Exists(PlanVersion.objects.filter(plan=OuterRef("pk"), status=PlanVersionStatus.DRAFT)))
            elif has_draft != "all":
                raise exceptions.ValidationError({"has_draft_version": ["Allowed values: true, false, all."]})

        health = self.request.query_params.get("catalog_health")
        if health is not None:
            if health == "healthy":
                qs = qs.filter(~is_degraded_expr)
            elif health == "degraded":
                qs = qs.filter(is_degraded_expr)
            elif health != "all":
                raise exceptions.ValidationError({"catalog_health": ["Allowed values: healthy, degraded, all."]})

        is_pub = self.request.query_params.get("is_public")
        if is_pub is not None:
            if is_pub == "true":
                qs = qs.filter(is_public=True)
            elif is_pub == "false":
                qs = qs.filter(is_public=False)
            elif is_pub != "all":
                raise exceptions.ValidationError({"is_public": ["Allowed values: true, false, all."]})

        # Ordering
        ordering = self.request.query_params.get("ordering", "-created_at")
        if ordering not in self.ORDERING_MAP:
            raise exceptions.ValidationError({"ordering": [f"Invalid ordering field '{ordering}'."]})
        qs = qs.order_by(*self.ORDERING_MAP[ordering])

        return qs

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            self._attach_computed_plan_attributes(page)
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        self._attach_computed_plan_attributes(queryset)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    def create(self, request, *args, **kwargs):
        serializer = PlanCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        plan, v1 = create_plan(
            code=data["code"],
            name=data["name"],
            description=data.get("description", ""),
            actor=request.user,
        )
        if data.get("change_summary") and data["change_summary"] != "Initial version":
            update_draft_version(
                plan_version_id=v1.id,
                change_summary=data["change_summary"],
                actor=request.user,
            )

        plan_instance = self.get_queryset().get(pk=plan.id)
        self._attach_computed_plan_attributes([plan_instance])
        return Response(PlanSerializer(plan_instance).data, status=status.HTTP_201_CREATED)

    def retrieve(self, request, *args, **kwargs):
        plan_id = _parse_uuid_or_404(kwargs.get("pk"), "plan_id")
        plan = self.get_queryset().get(pk=plan_id)
        self._attach_computed_plan_attributes([plan])
        return Response(PlanSerializer(plan).data)

    def partial_update(self, request, *args, **kwargs):
        plan_id = _parse_uuid_or_404(kwargs.get("pk"), "plan_id")
        serializer = PlanUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        update_plan(
            plan_id=plan_id,
            name=data.get("name"),
            description=data.get("description"),
            is_public=data.get("is_public"),
            actor=request.user,
        )
        plan = self.get_queryset().get(pk=plan_id)
        self._attach_computed_plan_attributes([plan])
        return Response(PlanSerializer(plan).data)


# ---------------------------------------------------------------------------
# 2. PlanVersion ViewSet
# ---------------------------------------------------------------------------

class PlanVersionViewSet(_PlanBaseViewSet):
    """ViewSet managing PlanVersions, lifecycle operations, and activation readiness."""

    pagination_class = PlanDefaultPagination
    serializer_class = PlanVersionSerializer
    http_method_names = ["get", "post", "patch", "head", "options"]

    SUPPORTED_PARAMS = {"status", "catalog_health", "ordering", "page", "page_size"}
    ORDERING_MAP = {
        "version": ["version", "id"],
        "-version": ["-version", "-id"],
        "created_at": ["created_at", "id"],
        "-created_at": ["-created_at", "-id"],
    }

    def _attach_computed_version_attributes(self, versions):
        for v in versions:
            is_degraded = (
                any(p.product.status != "active" for p in v.packaged_products.all())
                or any(m.module.status != "active" for m in v.packaged_modules.all())
                or any(
                    c.capability.status != "active" or (c.capability.feature and c.capability.feature.status != "active")
                    for c in v.packaged_capabilities.all()
                )
            )
            v.catalog_health = "degraded" if is_degraded else "healthy"

    def get_queryset(self):
        qs = PlanVersion.objects.select_related("created_by", "updated_by").prefetch_related(
            "packaged_products__product",
            "packaged_modules__module",
            "packaged_capabilities__capability__feature",
        )

        plan_id = self.kwargs.get("plan_id")
        if plan_id is not None:
            plan_uuid = _parse_uuid_or_404(plan_id, "plan_id")
            if not Plan.objects.filter(pk=plan_uuid).exists():
                raise exceptions.NotFound("Plan not found.")
            qs = qs.filter(plan_id=plan_uuid)

        _validate_singleton_query_params(self.request, self.SUPPORTED_PARAMS)

        status_param = self.request.query_params.get("status")
        if status_param is not None:
            if status_param not in PlanVersionStatus.values and status_param != "all":
                raise exceptions.ValidationError({"status": [f"Allowed status: {list(PlanVersionStatus.values)} or 'all'."]})
            if status_param != "all":
                qs = qs.filter(status=status_param)

        health = self.request.query_params.get("catalog_health")
        if health is not None:
            is_degraded_expr = (
                Exists(PlanProduct.objects.filter(plan_version=OuterRef("pk")).exclude(product__status="active"))
                | Exists(PlanModule.objects.filter(plan_version=OuterRef("pk")).exclude(module__status="active"))
                | Exists(
                    PlanCapability.objects.filter(plan_version=OuterRef("pk")).filter(
                        ~Q(capability__status="active") | (Q(capability__feature__isnull=False) & ~Q(capability__feature__status="active"))
                    )
                )
            )
            if health == "healthy":
                qs = qs.filter(~is_degraded_expr)
            elif health == "degraded":
                qs = qs.filter(is_degraded_expr)
            elif health != "all":
                raise exceptions.ValidationError({"catalog_health": ["Allowed values: healthy, degraded, all."]})

        ordering = self.request.query_params.get("ordering", "-version")
        if ordering not in self.ORDERING_MAP:
            raise exceptions.ValidationError({"ordering": [f"Invalid ordering field '{ordering}'."]})
        qs = qs.order_by(*self.ORDERING_MAP[ordering])

        return qs

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            self._attach_computed_version_attributes(page)
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        self._attach_computed_version_attributes(queryset)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    def create(self, request, *args, **kwargs):
        plan_id = _parse_uuid_or_404(kwargs.get("plan_id"), "plan_id")
        serializer = PlanVersionCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        pv = create_draft_version(
            plan_id=plan_id,
            change_summary=serializer.validated_data.get("change_summary", ""),
            actor=request.user,
        )
        pv_instance = self.get_queryset().get(pk=pv.id)
        self._attach_computed_version_attributes([pv_instance])
        return Response(PlanVersionSerializer(pv_instance).data, status=status.HTTP_201_CREATED)

    def retrieve(self, request, *args, **kwargs):
        version_id = _parse_uuid_or_404(kwargs.get("pk"), "version_id")
        pv = self.get_queryset().get(pk=version_id)
        self._attach_computed_version_attributes([pv])
        return Response(PlanVersionSerializer(pv).data)

    def partial_update(self, request, *args, **kwargs):
        version_id = _parse_uuid_or_404(kwargs.get("pk"), "version_id")
        serializer = PlanVersionUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        pv = update_draft_version(
            plan_version_id=version_id,
            change_summary=serializer.validated_data["change_summary"],
            actor=request.user,
        )
        pv_instance = self.get_queryset().get(pk=pv.id)
        self._attach_computed_version_attributes([pv_instance])
        return Response(PlanVersionSerializer(pv_instance).data)

    def clone(self, request, *args, **kwargs):
        version_id = _parse_uuid_or_404(kwargs.get("pk"), "version_id")
        serializer = PlanVersionCloneSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        new_v = clone_plan_version(
            source_plan_version_id=version_id,
            actor=request.user,
            change_summary=serializer.validated_data.get("change_summary", ""),
        )
        new_instance = self.get_queryset().get(pk=new_v.id)
        self._attach_computed_version_attributes([new_instance])
        return Response(PlanVersionSerializer(new_instance).data, status=status.HTTP_201_CREATED)

    def readiness(self, request, *args, **kwargs):
        version_id = _parse_uuid_or_404(kwargs.get("pk"), "version_id")
        if not PlanVersion.objects.filter(pk=version_id).exists():
            raise exceptions.NotFound("PlanVersion not found.")
        data = evaluate_activation_readiness(plan_version=version_id)
        return Response(data)

    def activate(self, request, *args, **kwargs):
        version_id = _parse_uuid_or_404(kwargs.get("pk"), "version_id")
        serializer = PlanVersionEmptyActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        pv = activate_plan_version(plan_version_id=version_id, actor=request.user)
        pv_instance = self.get_queryset().get(pk=pv.id)
        self._attach_computed_version_attributes([pv_instance])
        return Response(PlanVersionSerializer(pv_instance).data)

    def retire(self, request, *args, **kwargs):
        version_id = _parse_uuid_or_404(kwargs.get("pk"), "version_id")
        serializer = PlanVersionEmptyActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        pv = retire_plan_version(plan_version_id=version_id, actor=request.user)
        pv_instance = self.get_queryset().get(pk=pv.id)
        self._attach_computed_version_attributes([pv_instance])
        return Response(PlanVersionSerializer(pv_instance).data)


# ---------------------------------------------------------------------------
# 3. PlanPrice ViewSet
# ---------------------------------------------------------------------------

class PlanPriceViewSet(_PlanBaseViewSet):
    """ViewSet managing PlanPrices under PlanVersions."""

    pagination_class = PlanLargePagination
    serializer_class = PlanPriceSerializer
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    SUPPORTED_PARAMS = {"currency", "billing_interval", "ordering", "page", "page_size"}
    ORDERING_MAP = {
        "currency": ["currency", "billing_interval", "id"],
        "billing_interval": ["billing_interval", "currency", "id"],
        "amount": ["amount", "currency", "id"],
        "-amount": ["-amount", "currency", "id"],
    }

    def get_queryset(self):
        qs = PlanPrice.objects.all()

        version_id = self.kwargs.get("version_id")
        if version_id is not None:
            v_uuid = _parse_uuid_or_404(version_id, "version_id")
            if not PlanVersion.objects.filter(pk=v_uuid).exists():
                raise exceptions.NotFound("PlanVersion not found.")
            qs = qs.filter(plan_version_id=v_uuid)

        _validate_singleton_query_params(self.request, self.SUPPORTED_PARAMS)

        curr = self.request.query_params.get("currency")
        if curr is not None:
            if curr not in PlanCurrency.values:
                raise exceptions.ValidationError({"currency": [f"Allowed currencies: {list(PlanCurrency.values)}."]})
            qs = qs.filter(currency=curr)

        interval = self.request.query_params.get("billing_interval")
        if interval is not None:
            if interval not in BillingInterval.values:
                raise exceptions.ValidationError({"billing_interval": [f"Allowed intervals: {list(BillingInterval.values)}."]})
            qs = qs.filter(billing_interval=interval)

        ordering = self.request.query_params.get("ordering", "currency")
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

    def create(self, request, *args, **kwargs):
        version_id = _parse_uuid_or_404(kwargs.get("version_id"), "version_id")
        serializer = PlanPriceCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        price = create_plan_price(
            plan_version_id=version_id,
            currency=serializer.validated_data["currency"],
            billing_interval=serializer.validated_data["billing_interval"],
            amount=serializer.validated_data["amount"],
            actor=request.user,
        )
        return Response(PlanPriceSerializer(price).data, status=status.HTTP_201_CREATED)

    def retrieve(self, request, *args, **kwargs):
        price_id = _parse_uuid_or_404(kwargs.get("pk"), "price_id")
        price = self.get_queryset().get(pk=price_id)
        return Response(PlanPriceSerializer(price).data)

    def partial_update(self, request, *args, **kwargs):
        price_id = _parse_uuid_or_404(kwargs.get("pk"), "price_id")
        serializer = PlanPriceUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        price = update_plan_price(
            plan_price_id=price_id,
            amount=serializer.validated_data["amount"],
            actor=request.user,
        )
        return Response(PlanPriceSerializer(price).data)

    def destroy(self, request, *args, **kwargs):
        price_id = _parse_uuid_or_404(kwargs.get("pk"), "price_id")
        remove_plan_price(plan_price_id=price_id, actor=request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# 4. PlanProduct ViewSet
# ---------------------------------------------------------------------------

class PlanProductViewSet(_PlanBaseViewSet):
    """ViewSet managing PlanProducts under PlanVersions."""

    pagination_class = PlanDefaultPagination
    serializer_class = PlanProductSerializer
    http_method_names = ["get", "post", "delete", "head", "options"]

    SUPPORTED_PARAMS = {"search", "ordering", "page", "page_size"}
    ORDERING_MAP = {
        "product__code": ["product__code", "id"],
        "-product__code": ["-product__code", "-id"],
        "created_at": ["created_at", "id"],
    }

    def get_queryset(self):
        qs = PlanProduct.objects.select_related("product").all()

        version_id = self.kwargs.get("version_id")
        if version_id is not None:
            v_uuid = _parse_uuid_or_404(version_id, "version_id")
            if not PlanVersion.objects.filter(pk=v_uuid).exists():
                raise exceptions.NotFound("PlanVersion not found.")
            qs = qs.filter(plan_version_id=v_uuid)

        _validate_singleton_query_params(self.request, self.SUPPORTED_PARAMS)

        search = self.request.query_params.get("search")
        if search is not None:
            s = search.strip()
            if s:
                qs = qs.filter(Q(product__name__icontains=s) | Q(product__code__icontains=s))

        ordering = self.request.query_params.get("ordering", "product__code")
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

    def create(self, request, *args, **kwargs):
        version_id = _parse_uuid_or_404(kwargs.get("version_id"), "version_id")
        serializer = PlanProductCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        pp = add_plan_product(
            plan_version_id=version_id,
            product_id=serializer.validated_data["product_id"],
            actor=request.user,
        )
        return Response(PlanProductSerializer(pp).data, status=status.HTTP_201_CREATED)

    def retrieve(self, request, *args, **kwargs):
        pp_id = _parse_uuid_or_404(kwargs.get("pk"), "plan_product_id")
        pp = self.get_queryset().get(pk=pp_id)
        return Response(PlanProductSerializer(pp).data)

    def destroy(self, request, *args, **kwargs):
        pp_id = _parse_uuid_or_404(kwargs.get("pk"), "plan_product_id")
        remove_plan_product(plan_product_id=pp_id, actor=request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# 5. PlanModule ViewSet
# ---------------------------------------------------------------------------

class PlanModuleViewSet(_PlanBaseViewSet):
    """ViewSet managing PlanModules under PlanVersions."""

    pagination_class = PlanDefaultPagination
    serializer_class = PlanModuleSerializer
    http_method_names = ["get", "post", "delete", "head", "options"]

    SUPPORTED_PARAMS = {"search", "plan_product_id", "ordering", "page", "page_size"}
    ORDERING_MAP = {
        "module__code": ["module__code", "id"],
        "-module__code": ["-module__code", "-id"],
        "created_at": ["created_at", "id"],
    }

    def get_queryset(self):
        qs = PlanModule.objects.select_related("module").all()

        version_id = self.kwargs.get("version_id")
        if version_id is not None:
            v_uuid = _parse_uuid_or_404(version_id, "version_id")
            if not PlanVersion.objects.filter(pk=v_uuid).exists():
                raise exceptions.NotFound("PlanVersion not found.")
            qs = qs.filter(plan_version_id=v_uuid)

        _validate_singleton_query_params(self.request, self.SUPPORTED_PARAMS)

        search = self.request.query_params.get("search")
        if search is not None:
            s = search.strip()
            if s:
                qs = qs.filter(Q(module__name__icontains=s) | Q(module__code__icontains=s))

        pp_id = self.request.query_params.get("plan_product_id")
        if pp_id is not None:
            pp_uuid = _parse_uuid_or_404(pp_id, "plan_product_id")
            qs = qs.filter(plan_product_id=pp_uuid)

        ordering = self.request.query_params.get("ordering", "module__code")
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

    def create(self, request, *args, **kwargs):
        _parse_uuid_or_404(kwargs.get("version_id"), "version_id")
        serializer = PlanModuleCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        pm = add_plan_module(
            plan_product_id=serializer.validated_data["plan_product_id"],
            module_id=serializer.validated_data["module_id"],
            actor=request.user,
        )
        return Response(PlanModuleSerializer(pm).data, status=status.HTTP_201_CREATED)

    def retrieve(self, request, *args, **kwargs):
        pm_id = _parse_uuid_or_404(kwargs.get("pk"), "plan_module_id")
        pm = self.get_queryset().get(pk=pm_id)
        return Response(PlanModuleSerializer(pm).data)

    def destroy(self, request, *args, **kwargs):
        pm_id = _parse_uuid_or_404(kwargs.get("pk"), "plan_module_id")
        remove_plan_module(plan_module_id=pm_id, actor=request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# 6. PlanCapability ViewSet
# ---------------------------------------------------------------------------

class PlanCapabilityViewSet(_PlanBaseViewSet):
    """ViewSet managing PlanCapabilities under PlanVersions."""

    pagination_class = PlanLargePagination
    serializer_class = PlanCapabilitySerializer
    http_method_names = ["get", "post", "delete", "head", "options"]

    SUPPORTED_PARAMS = {"search", "plan_module_id", "ordering", "page", "page_size"}
    ORDERING_MAP = {
        "capability__code": ["capability__code", "id"],
        "-capability__code": ["-capability__code", "-id"],
    }

    def get_queryset(self):
        qs = PlanCapability.objects.select_related("capability__feature").all()

        version_id = self.kwargs.get("version_id")
        if version_id is not None:
            v_uuid = _parse_uuid_or_404(version_id, "version_id")
            if not PlanVersion.objects.filter(pk=v_uuid).exists():
                raise exceptions.NotFound("PlanVersion not found.")
            qs = qs.filter(plan_version_id=v_uuid)

        _validate_singleton_query_params(self.request, self.SUPPORTED_PARAMS)

        search = self.request.query_params.get("search")
        if search is not None:
            s = search.strip()
            if s:
                qs = qs.filter(Q(capability__name__icontains=s) | Q(capability__code__icontains=s))

        pm_id = self.request.query_params.get("plan_module_id")
        if pm_id is not None:
            pm_uuid = _parse_uuid_or_404(pm_id, "plan_module_id")
            qs = qs.filter(plan_module_id=pm_uuid)

        ordering = self.request.query_params.get("ordering", "capability__code")
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

    def create(self, request, *args, **kwargs):
        _parse_uuid_or_404(kwargs.get("version_id"), "version_id")
        serializer = PlanCapabilityCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        pc = add_plan_capability(
            plan_module_id=serializer.validated_data["plan_module_id"],
            capability_id=serializer.validated_data["capability_id"],
            actor=request.user,
        )
        return Response(PlanCapabilitySerializer(pc).data, status=status.HTTP_201_CREATED)

    def retrieve(self, request, *args, **kwargs):
        pc_id = _parse_uuid_or_404(kwargs.get("pk"), "plan_capability_id")
        pc = self.get_queryset().get(pk=pc_id)
        return Response(PlanCapabilitySerializer(pc).data)

    def destroy(self, request, *args, **kwargs):
        pc_id = _parse_uuid_or_404(kwargs.get("pk"), "plan_capability_id")
        remove_plan_capability(plan_capability_id=pc_id, actor=request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# 7. PlanQuota ViewSet
# ---------------------------------------------------------------------------

class PlanQuotaViewSet(_PlanBaseViewSet):
    """ViewSet managing PlanQuotas under PlanVersions."""

    pagination_class = PlanDefaultPagination
    serializer_class = PlanQuotaSerializer
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    SUPPORTED_PARAMS = {"search", "scope", "ordering", "page", "page_size"}
    ORDERING_MAP = {
        "scope": ["scope", "quota_key", "id"],
        "quota_key": ["quota_key", "id"],
        "name": ["name", "id"],
    }

    def get_queryset(self):
        qs = PlanQuota.objects.all()

        version_id = self.kwargs.get("version_id")
        if version_id is not None:
            v_uuid = _parse_uuid_or_404(version_id, "version_id")
            if not PlanVersion.objects.filter(pk=v_uuid).exists():
                raise exceptions.NotFound("PlanVersion not found.")
            qs = qs.filter(plan_version_id=v_uuid)

        _validate_singleton_query_params(self.request, self.SUPPORTED_PARAMS)

        search = self.request.query_params.get("search")
        if search is not None:
            s = search.strip()
            if s:
                qs = qs.filter(Q(quota_key__icontains=s) | Q(name__icontains=s))

        scope = self.request.query_params.get("scope")
        if scope is not None:
            if scope not in QuotaScope.values:
                raise exceptions.ValidationError({"scope": [f"Allowed scopes: {list(QuotaScope.values)}."]})
            qs = qs.filter(scope=scope)

        ordering = self.request.query_params.get("ordering", "scope")
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

    def create(self, request, *args, **kwargs):
        version_id = _parse_uuid_or_404(kwargs.get("version_id"), "version_id")
        serializer = PlanQuotaCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        target_id = None
        if data["scope"] == QuotaScope.PRODUCT:
            target_id = data.get("plan_product_id")
        elif data["scope"] == QuotaScope.MODULE:
            target_id = data.get("plan_module_id")
        elif data["scope"] == QuotaScope.CAPABILITY:
            target_id = data.get("plan_capability_id")

        quota = create_plan_quota(
            plan_version_id=version_id,
            scope=data["scope"],
            quota_key=data["quota_key"],
            name=data["name"],
            unit=data["unit"],
            limit_type=data["limit_type"],
            limit_value=data.get("limit_value"),
            is_hard_limit=data.get("is_hard_limit", True),
            reset_period=data.get("reset_period", "never"),
            target_id=target_id,
            actor=request.user,
        )
        return Response(PlanQuotaSerializer(quota).data, status=status.HTTP_201_CREATED)

    def retrieve(self, request, *args, **kwargs):
        quota_id = _parse_uuid_or_404(kwargs.get("pk"), "quota_id")
        quota = self.get_queryset().get(pk=quota_id)
        return Response(PlanQuotaSerializer(quota).data)

    def partial_update(self, request, *args, **kwargs):
        quota_id = _parse_uuid_or_404(kwargs.get("pk"), "quota_id")
        serializer = PlanQuotaUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        kwargs_update = {}
        for field in ("name", "unit", "limit_type", "is_hard_limit", "reset_period"):
            if field in data:
                kwargs_update[field] = data[field]
        if "limit_value" in data:
            kwargs_update["limit_value"] = data["limit_value"]

        quota = update_plan_quota(
            plan_quota_id=quota_id,
            actor=request.user,
            **kwargs_update,
        )
        return Response(PlanQuotaSerializer(quota).data)

    def destroy(self, request, *args, **kwargs):
        quota_id = _parse_uuid_or_404(kwargs.get("pk"), "quota_id")
        remove_plan_quota(plan_quota_id=quota_id, actor=request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Public Plan Discovery View
# ---------------------------------------------------------------------------

class PublicPlanListView(APIView):
    """Public read-only plan discovery endpoint.

    Unauthenticated. Returns only public plans with active healthy versions.
    """

    authentication_classes = []
    permission_classes = [AllowAny]
    http_method_names = ["get", "head", "options"]

    def get(self, request, *args, **kwargs):
        plans = (
            Plan.objects.filter(is_public=True)
            .prefetch_related(
                Prefetch(
                    "versions",
                    queryset=PlanVersion.objects.filter(status=PlanVersionStatus.ACTIVE).prefetch_related(
                        "prices",
                        "packaged_products__product",
                        "packaged_modules__module",
                        "packaged_capabilities__capability__feature",
                        "quotas__plan_product__product",
                        "quotas__plan_module__module",
                        "quotas__plan_capability__capability",
                    ),
                    to_attr="active_versions",
                )
            )
            .order_by("code")
        )

        results = []
        for plan in plans:
            active_versions = getattr(plan, "active_versions", [])
            if not active_versions:
                continue
            active_v = active_versions[0]

            is_degraded = (
                any(p.product.status != "active" for p in active_v.packaged_products.all())
                or any(m.module.status != "active" for m in active_v.packaged_modules.all())
                or any(
                    c.capability.status != "active" or (c.capability.feature and c.capability.feature.status != "active")
                    for c in active_v.packaged_capabilities.all()
                )
            )
            if is_degraded:
                continue

            prices_data = [
                {
                    "currency": p.currency,
                    "billing_interval": p.billing_interval,
                    "amount": f"{p.amount:.2f}",
                }
                for p in active_v.prices.all().order_by("currency", "billing_interval")
            ]

            packaged_products_data = [
                {
                    "product_code": pp.product.code,
                    "product_name": pp.product.name,
                }
                for pp in active_v.packaged_products.all().order_by("product__code")
            ]

            quota_highlights_data = []
            for q in active_v.quotas.all().order_by("quota_key"):
                quota_highlights_data.append({
                    "quota_key": q.quota_key,
                    "name": q.name,
                    "limit_type": q.limit_type,
                    "limit_value": q.limit_value,
                    "unit": q.unit,
                    "reset_period": q.reset_period,
                })

            results.append({
                "plan_code": plan.code,
                "plan_name": plan.name,
                "description": plan.description,
                "version": active_v.version,
                "prices": prices_data,
                "packaged_products": packaged_products_data,
                "quota_highlights": quota_highlights_data,
            })

        return Response({"count": len(results), "results": results}, status=status.HTTP_200_OK)
