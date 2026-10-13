"""Product Registry and Catalog Views.

Implements Platform Owner-only viewsets for Product, ProductModule, ProductFeature,
and ProductCapability with strict session authentication, deterministic ordering,
annotated non-N+1 child counts, immediate-parent scoping, and race-safe service delegation.
"""

import uuid
from django.db import IntegrityError
from django.db.models import Count, Q
from rest_framework import exceptions, status, viewsets
from rest_framework.response import Response

from apps.auditlog.models import AuditOperationSource
from apps.identity.authentication import EnforcedSessionAuthentication
from apps.identity.permissions import IsPlatformOwner
from apps.product_registry.models import (
    CatalogStatus,
    Product,
    ProductCapability,
    ProductFeature,
    ProductModule,
    ProductStatus,
)
from apps.product_registry.pagination import ProductCatalogPagination, ProductPagination
from apps.product_registry.serializers import (
    ProductCapabilityCreateSerializer,
    ProductCapabilityDetailSerializer,
    ProductCapabilityListSerializer,
    ProductCapabilityUpdateSerializer,
    ProductCreateSerializer,
    ProductDetailSerializer,
    ProductFeatureCreateSerializer,
    ProductFeatureDetailSerializer,
    ProductFeatureListSerializer,
    ProductFeatureUpdateSerializer,
    ProductListSerializer,
    ProductModuleCreateSerializer,
    ProductModuleDetailSerializer,
    ProductModuleListSerializer,
    ProductModuleUpdateSerializer,
    ProductUpdateSerializer,
)
from apps.product_registry.services import (
    create_product_capability,
    create_product_feature,
    create_product_module,
    update_product,
    update_product_capability,
    update_product_feature,
    update_product_module,
)

PRODUCT_ORDERING_FIELDS_MAP = {
    "created_at": ["created_at", "id"],
    "-created_at": ["-created_at", "-id"],
    "name": ["name", "id"],
    "-name": ["-name", "-id"],
    "code": ["code", "id"],
    "-code": ["-code", "-id"],
    "status": ["status", "id"],
    "-status": ["-status", "-id"],
}

CATALOG_ORDERING_FIELDS_MAP = {
    "display_order": ["display_order", "created_at", "id"],
    "-display_order": ["-display_order", "-created_at", "-id"],
    "name": ["name", "id"],
    "-name": ["-name", "-id"],
    "code": ["code", "id"],
    "-code": ["-code", "-id"],
    "created_at": ["created_at", "id"],
    "-created_at": ["-created_at", "-id"],
}


def _validate_uuid_param(val: str | None, param_name: str) -> uuid.UUID | None:
    if val is None:
        return None
    try:
        return uuid.UUID(val)
    except (ValueError, TypeError, AttributeError):
        raise exceptions.ValidationError({param_name: ["Invalid UUID format."]})


def _handle_catalog_integrity_error(exc: IntegrityError):
    err_str = str(exc).lower()
    if "code_ci_uniq" in err_str:
        raise exceptions.ValidationError({"code": ["An item with this code already exists under this parent."]})
    if "name_ci_uniq" in err_str:
        raise exceptions.ValidationError({"name": ["An item with this name already exists under this parent."]})
    raise exc


# ==============================================================================
# PRODUCT VIEWSET
# ==============================================================================

class ProductViewSet(viewsets.GenericViewSet):
    """Viewset managing the centralized product registry catalog."""

    authentication_classes = [EnforcedSessionAuthentication]
    permission_classes = [IsPlatformOwner]
    pagination_class = ProductPagination
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self):
        queryset = Product.objects.select_related("created_by", "updated_by").all()

        # 1. Filter by status
        status_param = self.request.query_params.get("status")
        if status_param is not None:
            if status_param not in ProductStatus.values:
                allowed_str = ", ".join(ProductStatus.values)
                raise exceptions.ValidationError(
                    {"status": [f"Invalid status '{status_param}'. Allowed: {allowed_str}."]}
                )
            queryset = queryset.filter(status=status_param)

        # 2. Search by name or code
        raw_search = self.request.query_params.get("search")
        if raw_search is not None:
            search = raw_search.strip()
            if len(search) > 100:
                raise exceptions.ValidationError(
                    {"search": ["Search query must be 100 characters or fewer."]}
                )
            if search:
                queryset = queryset.filter(Q(name__icontains=search) | Q(code__icontains=search))

        # 3. Deterministic ordering
        ordering_param = self.request.query_params.get("ordering")
        if ordering_param:
            if ordering_param not in PRODUCT_ORDERING_FIELDS_MAP:
                raise exceptions.ValidationError(
                    {"ordering": [f"Invalid ordering field '{ordering_param}'."]}
                )
            order_by = PRODUCT_ORDERING_FIELDS_MAP[ordering_param]
        else:
            order_by = ["-created_at", "-id"]

        return queryset.order_by(*order_by)

    def get_serializer_class(self):
        if self.action == "list":
            return ProductListSerializer
        if self.action == "create":
            return ProductCreateSerializer
        if self.action == "partial_update":
            return ProductUpdateSerializer
        return ProductDetailSerializer

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = ProductListSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = ProductListSerializer(queryset, many=True)
        return Response(serializer.data)

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = ProductDetailSerializer(instance)
        return Response(serializer.data)

    def create(self, request, *args, **kwargs):
        serializer = ProductCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            from django.db import transaction
            from apps.auditlog.models import AuditAction, AuditTargetType
            from apps.auditlog.services import AuditEventError, record_audit_event

            with transaction.atomic():
                product = serializer.save(
                    status=ProductStatus.DRAFT,
                    created_by=request.user,
                    updated_by=request.user,
                )
                record_audit_event(
                    action=AuditAction.PRODUCT_CREATED,
                    target_type=AuditTargetType.PRODUCT,
                    target_id=product.id,
                    target_repr=product.name,
                    actor=request.user,
                    organization_id=None,
                    operation_source=AuditOperationSource.INTERACTIVE,
                    metadata={
                        "code": product.code,
                        "name": product.name,
                        "status": product.status,
                    },
                )
        except IntegrityError as exc:
            cause = getattr(exc, "__cause__", None)
            diag = getattr(cause, "diag", None)
            constraint_name = getattr(diag, "constraint_name", None)
            if constraint_name == "product_code_ci_uniq" or "product_code_ci_uniq" in str(exc):
                raise exceptions.ValidationError(
                    {"code": ["A product with this code already exists."]}
                )
            raise
        except AuditEventError:
            return Response(
                {"detail": "A server error occurred while recording the audit event."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        response_serializer = ProductDetailSerializer(product)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)

    def partial_update(self, request, *args, **kwargs):
        for forbidden in ("actor", "created_by", "operation_source", "correlation_id"):
            if forbidden in request.data:
                raise exceptions.ValidationError({forbidden: [f"Field '{forbidden}' cannot be specified in HTTP request body."]})
        pk = kwargs.get("pk")
        product = update_product(product_id=pk, data=request.data, actor=request.user)
        response_serializer = ProductDetailSerializer(product)
        return Response(response_serializer.data, status=status.HTTP_200_OK)


# ==============================================================================
# PRODUCT MODULE VIEWSET
# ==============================================================================

class ProductModuleViewSet(viewsets.GenericViewSet):
    """Viewset managing ProductModules under a Product."""

    authentication_classes = [EnforcedSessionAuthentication]
    permission_classes = [IsPlatformOwner]
    pagination_class = ProductCatalogPagination
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self):
        queryset = ProductModule.objects.select_related("product", "created_by", "updated_by").annotate(
            total_features_count=Count("features", distinct=True),
            active_features_count=Count("features", filter=Q(features__status=CatalogStatus.ACTIVE), distinct=True),
        )

        # Scoping by product_id
        product_id_param = self.request.query_params.get("product_id")
        if product_id_param is not None:
            product_uuid = _validate_uuid_param(product_id_param, "product_id")
            queryset = queryset.filter(product_id=product_uuid)
        elif self.action == "list":
            raise exceptions.ValidationError({"product_id": ["Query parameter 'product_id' is required for listing modules."]})

        # Filter by status
        status_param = self.request.query_params.get("status")
        if status_param is not None:
            if status_param not in CatalogStatus.values:
                allowed_str = ", ".join(CatalogStatus.values)
                raise exceptions.ValidationError(
                    {"status": [f"Invalid status '{status_param}'. Allowed: {allowed_str}."]}
                )
            queryset = queryset.filter(status=status_param)

        # Search by name or code
        raw_search = self.request.query_params.get("search")
        if raw_search is not None:
            search = raw_search.strip()
            if len(search) > 100:
                raise exceptions.ValidationError(
                    {"search": ["Search query must be 100 characters or fewer."]}
                )
            if search:
                queryset = queryset.filter(Q(name__icontains=search) | Q(code__icontains=search))

        # Deterministic ordering
        ordering_param = self.request.query_params.get("ordering")
        if ordering_param:
            if ordering_param not in CATALOG_ORDERING_FIELDS_MAP:
                raise exceptions.ValidationError(
                    {"ordering": [f"Invalid ordering field '{ordering_param}'."]}
                )
            order_by = CATALOG_ORDERING_FIELDS_MAP[ordering_param]
        else:
            order_by = ["display_order", "created_at", "id"]

        return queryset.order_by(*order_by)

    def get_serializer_class(self):
        if self.action == "list":
            return ProductModuleListSerializer
        if self.action == "create":
            return ProductModuleCreateSerializer
        if self.action == "partial_update":
            return ProductModuleUpdateSerializer
        return ProductModuleDetailSerializer

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = ProductModuleListSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = ProductModuleListSerializer(queryset, many=True)
        return Response(serializer.data)

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = ProductModuleDetailSerializer(instance)
        return Response(serializer.data)

    def create(self, request, *args, **kwargs):
        for forbidden in ("actor", "created_by", "operation_source", "correlation_id"):
            if forbidden in request.data:
                raise exceptions.ValidationError({forbidden: [f"Field '{forbidden}' cannot be specified in HTTP request body."]})

        product_id = request.data.get("product_id")
        if not product_id:
            raise exceptions.ValidationError({"product_id": ["This field is required."]})
        _validate_uuid_param(str(product_id), "product_id")

        mutable_data = {k: v for k, v in request.data.items() if k != "product_id"}

        try:
            module = create_product_module(
                product_id=product_id,
                data=mutable_data,
                actor=request.user,
                operation_source=AuditOperationSource.INTERACTIVE,
                correlation_id=None,
            )
        except IntegrityError as exc:
            _handle_catalog_integrity_error(exc)

        response_serializer = ProductModuleDetailSerializer(module)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)

    def partial_update(self, request, *args, **kwargs):
        for forbidden in ("actor", "created_by", "operation_source", "correlation_id"):
            if forbidden in request.data:
                raise exceptions.ValidationError({forbidden: [f"Field '{forbidden}' cannot be specified in HTTP request body."]})

        pk = kwargs.get("pk")
        _validate_uuid_param(str(pk), "id")

        try:
            module = update_product_module(
                module_id=pk,
                data=request.data,
                actor=request.user,
                operation_source=AuditOperationSource.INTERACTIVE,
                correlation_id=None,
            )
        except IntegrityError as exc:
            _handle_catalog_integrity_error(exc)

        response_serializer = ProductModuleDetailSerializer(module)
        return Response(response_serializer.data, status=status.HTTP_200_OK)


# ==============================================================================
# PRODUCT FEATURE VIEWSET
# ==============================================================================

class ProductFeatureViewSet(viewsets.GenericViewSet):
    """Viewset managing ProductFeatures under a ProductModule."""

    authentication_classes = [EnforcedSessionAuthentication]
    permission_classes = [IsPlatformOwner]
    pagination_class = ProductCatalogPagination
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self):
        queryset = ProductFeature.objects.select_related("module__product", "created_by", "updated_by").annotate(
            total_capabilities_count=Count("capabilities", distinct=True),
            active_capabilities_count=Count("capabilities", filter=Q(capabilities__status=CatalogStatus.ACTIVE), distinct=True),
        )

        # Scoping by module_id
        module_id_param = self.request.query_params.get("module_id")
        if module_id_param is not None:
            module_uuid = _validate_uuid_param(module_id_param, "module_id")
            queryset = queryset.filter(module_id=module_uuid)
        elif self.action == "list":
            raise exceptions.ValidationError({"module_id": ["Query parameter 'module_id' is required for listing features."]})

        # Filter by status
        status_param = self.request.query_params.get("status")
        if status_param is not None:
            if status_param not in CatalogStatus.values:
                allowed_str = ", ".join(CatalogStatus.values)
                raise exceptions.ValidationError(
                    {"status": [f"Invalid status '{status_param}'. Allowed: {allowed_str}."]}
                )
            queryset = queryset.filter(status=status_param)

        # Search by name or code
        raw_search = self.request.query_params.get("search")
        if raw_search is not None:
            search = raw_search.strip()
            if len(search) > 100:
                raise exceptions.ValidationError(
                    {"search": ["Search query must be 100 characters or fewer."]}
                )
            if search:
                queryset = queryset.filter(Q(name__icontains=search) | Q(code__icontains=search))

        # Deterministic ordering
        ordering_param = self.request.query_params.get("ordering")
        if ordering_param:
            if ordering_param not in CATALOG_ORDERING_FIELDS_MAP:
                raise exceptions.ValidationError(
                    {"ordering": [f"Invalid ordering field '{ordering_param}'."]}
                )
            order_by = CATALOG_ORDERING_FIELDS_MAP[ordering_param]
        else:
            order_by = ["display_order", "created_at", "id"]

        return queryset.order_by(*order_by)

    def get_serializer_class(self):
        if self.action == "list":
            return ProductFeatureListSerializer
        if self.action == "create":
            return ProductFeatureCreateSerializer
        if self.action == "partial_update":
            return ProductFeatureUpdateSerializer
        return ProductFeatureDetailSerializer

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = ProductFeatureListSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = ProductFeatureListSerializer(queryset, many=True)
        return Response(serializer.data)

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = ProductFeatureDetailSerializer(instance)
        return Response(serializer.data)

    def create(self, request, *args, **kwargs):
        for forbidden in ("actor", "created_by", "operation_source", "correlation_id"):
            if forbidden in request.data:
                raise exceptions.ValidationError({forbidden: [f"Field '{forbidden}' cannot be specified in HTTP request body."]})

        module_id = request.data.get("module_id")
        if not module_id:
            raise exceptions.ValidationError({"module_id": ["This field is required."]})
        _validate_uuid_param(str(module_id), "module_id")

        mutable_data = {k: v for k, v in request.data.items() if k != "module_id"}

        try:
            feature = create_product_feature(
                module_id=module_id,
                data=mutable_data,
                actor=request.user,
                operation_source=AuditOperationSource.INTERACTIVE,
                correlation_id=None,
            )
        except IntegrityError as exc:
            _handle_catalog_integrity_error(exc)

        response_serializer = ProductFeatureDetailSerializer(feature)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)

    def partial_update(self, request, *args, **kwargs):
        for forbidden in ("actor", "created_by", "operation_source", "correlation_id"):
            if forbidden in request.data:
                raise exceptions.ValidationError({forbidden: [f"Field '{forbidden}' cannot be specified in HTTP request body."]})

        pk = kwargs.get("pk")
        _validate_uuid_param(str(pk), "id")

        try:
            feature = update_product_feature(
                feature_id=pk,
                data=request.data,
                actor=request.user,
                operation_source=AuditOperationSource.INTERACTIVE,
                correlation_id=None,
            )
        except IntegrityError as exc:
            _handle_catalog_integrity_error(exc)

        response_serializer = ProductFeatureDetailSerializer(feature)
        return Response(response_serializer.data, status=status.HTTP_200_OK)


# ==============================================================================
# PRODUCT CAPABILITY VIEWSET
# ==============================================================================

class ProductCapabilityViewSet(viewsets.GenericViewSet):
    """Viewset managing ProductCapabilities under a ProductFeature."""

    authentication_classes = [EnforcedSessionAuthentication]
    permission_classes = [IsPlatformOwner]
    pagination_class = ProductCatalogPagination
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self):
        queryset = ProductCapability.objects.select_related(
            "feature__module__product", "created_by", "updated_by"
        ).all()

        # Scoping by feature_id
        feature_id_param = self.request.query_params.get("feature_id")
        if feature_id_param is not None:
            feature_uuid = _validate_uuid_param(feature_id_param, "feature_id")
            queryset = queryset.filter(feature_id=feature_uuid)
        elif self.action == "list":
            raise exceptions.ValidationError({"feature_id": ["Query parameter 'feature_id' is required for listing capabilities."]})

        # Filter by status
        status_param = self.request.query_params.get("status")
        if status_param is not None:
            if status_param not in CatalogStatus.values:
                allowed_str = ", ".join(CatalogStatus.values)
                raise exceptions.ValidationError(
                    {"status": [f"Invalid status '{status_param}'. Allowed: {allowed_str}."]}
                )
            queryset = queryset.filter(status=status_param)

        # Search by name or code
        raw_search = self.request.query_params.get("search")
        if raw_search is not None:
            search = raw_search.strip()
            if len(search) > 100:
                raise exceptions.ValidationError(
                    {"search": ["Search query must be 100 characters or fewer."]}
                )
            if search:
                queryset = queryset.filter(Q(name__icontains=search) | Q(code__icontains=search))

        # Deterministic ordering
        ordering_param = self.request.query_params.get("ordering")
        if ordering_param:
            if ordering_param not in CATALOG_ORDERING_FIELDS_MAP:
                raise exceptions.ValidationError(
                    {"ordering": [f"Invalid ordering field '{ordering_param}'."]}
                )
            order_by = CATALOG_ORDERING_FIELDS_MAP[ordering_param]
        else:
            order_by = ["display_order", "created_at", "id"]

        return queryset.order_by(*order_by)

    def get_serializer_class(self):
        if self.action == "list":
            return ProductCapabilityListSerializer
        if self.action == "create":
            return ProductCapabilityCreateSerializer
        if self.action == "partial_update":
            return ProductCapabilityUpdateSerializer
        return ProductCapabilityDetailSerializer

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = ProductCapabilityListSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = ProductCapabilityListSerializer(queryset, many=True)
        return Response(serializer.data)

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = ProductCapabilityDetailSerializer(instance)
        return Response(serializer.data)

    def create(self, request, *args, **kwargs):
        for forbidden in ("actor", "created_by", "operation_source", "correlation_id"):
            if forbidden in request.data:
                raise exceptions.ValidationError({forbidden: [f"Field '{forbidden}' cannot be specified in HTTP request body."]})

        feature_id = request.data.get("feature_id")
        if not feature_id:
            raise exceptions.ValidationError({"feature_id": ["This field is required."]})
        _validate_uuid_param(str(feature_id), "feature_id")

        mutable_data = {k: v for k, v in request.data.items() if k != "feature_id"}

        try:
            capability = create_product_capability(
                feature_id=feature_id,
                data=mutable_data,
                actor=request.user,
                operation_source=AuditOperationSource.INTERACTIVE,
                correlation_id=None,
            )
        except IntegrityError as exc:
            _handle_catalog_integrity_error(exc)

        response_serializer = ProductCapabilityDetailSerializer(capability)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)

    def partial_update(self, request, *args, **kwargs):
        for forbidden in ("actor", "created_by", "operation_source", "correlation_id"):
            if forbidden in request.data:
                raise exceptions.ValidationError({forbidden: [f"Field '{forbidden}' cannot be specified in HTTP request body."]})

        pk = kwargs.get("pk")
        _validate_uuid_param(str(pk), "id")

        try:
            capability = update_product_capability(
                capability_id=pk,
                data=request.data,
                actor=request.user,
                operation_source=AuditOperationSource.INTERACTIVE,
                correlation_id=None,
            )
        except IntegrityError as exc:
            _handle_catalog_integrity_error(exc)

        response_serializer = ProductCapabilityDetailSerializer(capability)
        return Response(response_serializer.data, status=status.HTTP_200_OK)
