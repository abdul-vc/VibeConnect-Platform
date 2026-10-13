"""Entitlements API Views.

Implements OrganizationProductEntitlementViewSet with EnforcedSessionAuthentication,
IsPlatformOwner authorization, deterministic row locking, safe IntegrityError extraction,
and strict lifecycle transitions.
"""

import uuid
from django.db import IntegrityError, transaction
from django.db.models import Q
from rest_framework import exceptions, status, viewsets
from rest_framework.response import Response

from apps.auditlog.models import AuditAction, AuditOperationSource, AuditTargetType
from apps.auditlog.services import AuditEventError, record_audit_event
from apps.identity.authentication import EnforcedSessionAuthentication
from apps.identity.permissions import IsPlatformOwner
from apps.organizations.models import Organization, OrganizationStatus
from apps.product_registry.models import Product, ProductStatus
from .models import (
    ALLOWED_ENTITLEMENT_TRANSITIONS,
    EntitlementStatus,
    OrganizationProductEntitlement,
)
from .pagination import EntitlementPagination
from .serializers import (
    EntitlementCreateSerializer,
    EntitlementDetailSerializer,
    EntitlementListSerializer,
    EntitlementUpdateSerializer,
)

ORDERING_FIELDS_MAP = {
    "created_at": ["created_at", "id"],
    "-created_at": ["-created_at", "-id"],
    "status": ["status", "id"],
    "-status": ["-status", "-id"],
    "organization": ["organization__code", "id"],
    "-organization": ["-organization__code", "-id"],
    "product": ["product__code", "id"],
    "-product": ["-product__code", "-id"],
}

SUPPORTED_SINGLETON_PARAMS = {
    "search",
    "organization_id",
    "product_id",
    "status",
    "ordering",
    "page",
    "page_size",
}


class OrganizationProductEntitlementViewSet(viewsets.GenericViewSet):
    """ViewSet for managing Organization-Product entitlements."""

    authentication_classes = [EnforcedSessionAuthentication]
    permission_classes = [IsPlatformOwner]
    pagination_class = EntitlementPagination
    http_method_names = ["get", "post", "patch", "head", "options"]

    def _validate_singleton_params(self):
        """Rejects repeated occurrences of any supported singleton query parameter."""
        for param in SUPPORTED_SINGLETON_PARAMS:
            if len(self.request.GET.getlist(param)) > 1:
                raise exceptions.ValidationError(
                    {param: [f"Duplicate '{param}' parameter is not permitted."]}
                )

    def get_queryset(self):
        self._validate_singleton_params()

        queryset = OrganizationProductEntitlement.objects.select_related(
            "organization",
            "product",
            "created_by",
            "updated_by",
        ).all()

        # 1. Filter by organization_id (UUID format check)
        org_id_param = self.request.query_params.get("organization_id")
        if org_id_param is not None:
            try:
                org_uuid = uuid.UUID(org_id_param)
            except (ValueError, TypeError, AttributeError):
                raise exceptions.ValidationError(
                    {"organization_id": ["Invalid UUID format for organization_id."]}
                )
            queryset = queryset.filter(organization_id=org_uuid)

        # 2. Filter by product_id (UUID format check)
        prod_id_param = self.request.query_params.get("product_id")
        if prod_id_param is not None:
            try:
                prod_uuid = uuid.UUID(prod_id_param)
            except (ValueError, TypeError, AttributeError):
                raise exceptions.ValidationError(
                    {"product_id": ["Invalid UUID format for product_id."]}
                )
            queryset = queryset.filter(product_id=prod_uuid)

        # 3. Filter by status
        status_param = self.request.query_params.get("status")
        if status_param is not None:
            if status_param not in EntitlementStatus.values:
                allowed_str = ", ".join(EntitlementStatus.values)
                raise exceptions.ValidationError(
                    {"status": [f"Invalid status '{status_param}'. Allowed: {allowed_str}."]}
                )
            queryset = queryset.filter(status=status_param)

        # 4. Search across organization name/code and product name/code
        raw_search = self.request.query_params.get("search")
        if raw_search is not None:
            search = raw_search.strip()
            if len(search) > 100:
                raise exceptions.ValidationError(
                    {"search": ["Search query must be 100 characters or fewer."]}
                )
            if search:
                queryset = queryset.filter(
                    Q(organization__name__icontains=search)
                    | Q(organization__code__icontains=search)
                    | Q(product__name__icontains=search)
                    | Q(product__code__icontains=search)
                )

        # 5. Deterministic ordering
        ordering_param = self.request.query_params.get("ordering")
        if ordering_param:
            if ordering_param not in ORDERING_FIELDS_MAP:
                raise exceptions.ValidationError(
                    {"ordering": [f"Invalid ordering field '{ordering_param}'."]}
                )
            order_by = ORDERING_FIELDS_MAP[ordering_param]
        else:
            order_by = ["-created_at", "-id"]

        return queryset.order_by(*order_by)

    def get_serializer_class(self):
        if self.action == "list":
            return EntitlementListSerializer
        if self.action == "create":
            return EntitlementCreateSerializer
        if self.action == "partial_update":
            return EntitlementUpdateSerializer
        return EntitlementDetailSerializer

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = EntitlementListSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = EntitlementListSerializer(queryset, many=True)
        return Response(serializer.data)

    def retrieve(self, request, *args, **kwargs):
        pk = kwargs.get("pk")
        try:
            uuid.UUID(str(pk))
            instance = self.get_object()
        except (ValueError, exceptions.NotFound):
            raise exceptions.NotFound()
        serializer = EntitlementDetailSerializer(instance)
        return Response(serializer.data)

    def create(self, request, *args, **kwargs):
        serializer = EntitlementCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        org_id = serializer.validated_data["organization_id"]
        prod_id = serializer.validated_data["product_id"]

        try:
            with transaction.atomic():
                # 1. Deterministic lock: Organization before Product
                try:
                    org = Organization.objects.select_for_update().get(pk=org_id)
                except (Organization.DoesNotExist, ValueError):
                    raise exceptions.ValidationError(
                        {"organization_id": ["Organization does not exist."]}
                    )

                try:
                    prod = Product.objects.select_for_update().get(pk=prod_id)
                except (Product.DoesNotExist, ValueError):
                    raise exceptions.ValidationError(
                        {"product_id": ["Product does not exist."]}
                    )

                # 2. Verify both parent entities are Active
                if org.status != OrganizationStatus.ACTIVE:
                    raise exceptions.ValidationError(
                        {"organization_id": ["Organization must be in Active status to receive product access."]}
                    )

                if prod.status != ProductStatus.ACTIVE:
                    raise exceptions.ValidationError(
                        {"product_id": ["Product must be in Active status to be assigned to an organization."]}
                    )

                # 3. Early duplicate check for non-revoked open entitlement
                if (
                    OrganizationProductEntitlement.objects.filter(
                        organization=org, product=prod
                    )
                    .exclude(status=EntitlementStatus.REVOKED)
                    .exists()
                ):
                    raise exceptions.ValidationError(
                        {
                            "non_field_errors": [
                                "An active, draft, or suspended access record already exists for this organization and product."
                            ]
                        }
                    )

                # 4. Create new draft entitlement record
                entitlement = OrganizationProductEntitlement.objects.create(
                    organization=org,
                    product=prod,
                    status=EntitlementStatus.DRAFT,
                    created_by=request.user,
                    updated_by=request.user,
                )
                record_audit_event(
                    action=AuditAction.ENTITLEMENT_CREATED,
                    target_type=AuditTargetType.ENTITLEMENT,
                    target_id=entitlement.id,
                    target_repr=f"{org.code} : {prod.code}",
                    actor=request.user,
                    organization_id=entitlement.organization_id,
                    operation_source=AuditOperationSource.INTERACTIVE,
                    metadata={
                        "organization_code": org.code,
                        "product_id": str(prod.id),
                        "product_code": prod.code,
                        "previous_status": None,
                        "resulting_status": entitlement.status,
                    },
                )
        except IntegrityError as exc:
            cause = getattr(exc, "__cause__", None)
            diag = getattr(cause, "diag", None)
            constraint_name = getattr(diag, "constraint_name", None)
            if constraint_name == "org_product_open_entitlement_uniq":
                raise exceptions.ValidationError(
                    {
                        "non_field_errors": [
                            "An active, draft, or suspended access record already exists for this organization and product."
                        ]
                    }
                )
            raise
        except AuditEventError:
            return Response(
                {"detail": "A server error occurred while recording the audit event."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        response_serializer = EntitlementDetailSerializer(entitlement)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)

    def partial_update(self, request, *args, **kwargs):
        pk = kwargs.get("pk")
        try:
            with transaction.atomic():
                try:
                    uuid.UUID(str(pk))
                    entitlement = (
                        OrganizationProductEntitlement.objects.select_for_update()
                        .select_related("organization", "product")
                        .get(pk=pk)
                    )
                except (OrganizationProductEntitlement.DoesNotExist, ValueError):
                    raise exceptions.NotFound()

                # Enforce read-only freeze on revoked historical records
                if entitlement.status == EntitlementStatus.REVOKED:
                    raise exceptions.ValidationError(
                        {"status": ["Cannot modify a revoked access record. This entitlement is permanently closed."]}
                    )

                prev_status = entitlement.status

                serializer = EntitlementUpdateSerializer(data=request.data)
                serializer.is_valid(raise_exception=True)

                target_status = serializer.validated_data["status"]

                # Same-status no-op check (preserves updated_at and updated_by without saving)
                if target_status == entitlement.status:
                    response_serializer = EntitlementDetailSerializer(entitlement)
                    return Response(response_serializer.data, status=status.HTTP_200_OK)

                # Validate lifecycle transition against current locked status
                allowed = ALLOWED_ENTITLEMENT_TRANSITIONS.get(entitlement.status, set())
                if target_status not in allowed:
                    raise exceptions.ValidationError(
                        {
                            "status": [
                                f"Cannot transition entitlement from '{entitlement.status}' to '{target_status}'."
                            ]
                        }
                    )

                # On transition to Active, lock and verify both parent entities remain Active
                if target_status == EntitlementStatus.ACTIVE:
                    org = Organization.objects.select_for_update().get(pk=entitlement.organization_id)
                    prod = Product.objects.select_for_update().get(pk=entitlement.product_id)
                    if org.status != OrganizationStatus.ACTIVE or prod.status != ProductStatus.ACTIVE:
                        raise exceptions.ValidationError(
                            {
                                "status": [
                                    "Cannot activate product access because the organization or product is no longer in Active status."
                                ]
                            }
                        )

                # Persist real status update
                entitlement.status = target_status
                entitlement.updated_by = request.user
                entitlement.save(update_fields=["status", "updated_by", "updated_at"])

                # LMS Lifecycle Integration Hook
                if entitlement.product.code in ("lms", "lms_core", "lms-pilot"):
                    from apps.integration_hub.lifecycle_service import (
                        handle_tenant_deactivated_or_suspended,
                        handle_tenant_lms_entitlement_activated,
                    )
                    if target_status == EntitlementStatus.ACTIVE:
                        handle_tenant_lms_entitlement_activated(entitlement.organization, actor=request.user, source="entitlement_activated")
                    elif target_status in (EntitlementStatus.SUSPENDED, EntitlementStatus.REVOKED):
                        handle_tenant_deactivated_or_suspended(entitlement.organization, status=target_status, actor=request.user)

                action = (
                    AuditAction.ENTITLEMENT_REVOKED
                    if target_status == EntitlementStatus.REVOKED
                    else AuditAction.ENTITLEMENT_STATUS_CHANGED
                )

                record_audit_event(
                    action=action,
                    target_type=AuditTargetType.ENTITLEMENT,
                    target_id=entitlement.id,
                    target_repr=f"{entitlement.organization.code} : {entitlement.product.code}",
                    actor=request.user,
                    organization_id=entitlement.organization_id,
                    operation_source=AuditOperationSource.INTERACTIVE,
                    metadata={
                        "organization_code": entitlement.organization.code,
                        "product_id": str(entitlement.product_id),
                        "product_code": entitlement.product.code,
                        "previous_status": prev_status,
                        "resulting_status": entitlement.status,
                    },
                )
        except AuditEventError:
            return Response(
                {"detail": "A server error occurred while recording the audit event."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        response_serializer = EntitlementDetailSerializer(entitlement)
        return Response(response_serializer.data, status=status.HTTP_200_OK)
