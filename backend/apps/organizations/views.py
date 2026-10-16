"""Organizations Views.

Implements OrganizationViewSet providing list, retrieve, create, and partial_update endpoints
with strict session authentication, Platform Owner authorization, transactional state-machine validation,
and safe IntegrityError exception handling.
"""

from django.db import IntegrityError, transaction
from django.db.models import Q
from rest_framework import exceptions, status, viewsets
from rest_framework.response import Response

from apps.access_control.services.guards import AccessControlError
from apps.auditlog.models import AuditAction, AuditOperationSource, AuditTargetType
from apps.auditlog.services import AuditEventError, record_audit_event
from apps.identity.authentication import EnforcedSessionAuthentication
from apps.identity.permissions import IsPlatformOwner
from apps.organizations.models import ALLOWED_STATUS_TRANSITIONS, Organization, OrganizationStatus
from apps.organizations.pagination import OrganizationPagination
from apps.organizations.serializers import (
    OrganizationCreateSerializer,
    OrganizationDetailSerializer,
    OrganizationListSerializer,
    OrganizationUpdateSerializer,
)

ORDERING_FIELDS_MAP = {
    "created_at": ["created_at", "id"],
    "-created_at": ["-created_at", "-id"],
    "name": ["name", "id"],
    "-name": ["-name", "-id"],
    "code": ["code", "id"],
    "-code": ["-code", "-id"],
    "status": ["status", "id"],
    "-status": ["-status", "-id"],
}


class OrganizationViewSet(viewsets.GenericViewSet):
    """Viewset managing the centralized organization registry catalog."""

    authentication_classes = [EnforcedSessionAuthentication]
    permission_classes = [IsPlatformOwner]
    pagination_class = OrganizationPagination
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self):
        queryset = Organization.objects.select_related("created_by", "updated_by").all()

        # 1. Filter by status
        status_param = self.request.query_params.get("status")
        if status_param is not None:
            if status_param not in OrganizationStatus.values:
                allowed_str = ", ".join(OrganizationStatus.values)
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
            return OrganizationListSerializer
        if self.action == "create":
            return OrganizationCreateSerializer
        if self.action == "partial_update":
            return OrganizationUpdateSerializer
        return OrganizationDetailSerializer

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = OrganizationListSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = OrganizationListSerializer(queryset, many=True)
        return Response(serializer.data)

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = OrganizationDetailSerializer(instance)
        return Response(serializer.data)

    def create(self, request, *args, **kwargs):
        serializer = OrganizationCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            with transaction.atomic():
                org = serializer.save(
                    status=OrganizationStatus.DRAFT,
                    created_by=request.user,
                    updated_by=request.user,
                )
                from apps.access_control.services.provisioning import provision_organization_defaults
                provision_organization_defaults(organization=org, actor=request.user)
                record_audit_event(
                    action=AuditAction.ORGANIZATION_CREATED,
                    target_type=AuditTargetType.ORGANIZATION,
                    target_id=org.id,
                    target_repr=org.name,
                    actor=request.user,
                    organization_id=org.id,
                    operation_source=AuditOperationSource.INTERACTIVE,
                    metadata={
                        "code": org.code,
                        "name": org.name,
                        "status": org.status,
                    },
                )
        except IntegrityError as exc:
            cause = getattr(exc, "__cause__", None)
            diag = getattr(cause, "diag", None)
            constraint_name = getattr(diag, "constraint_name", None)
            if constraint_name == "org_code_ci_uniq" or "org_code_ci_uniq" in str(exc):
                raise exceptions.ValidationError(
                    {"code": ["An organization with this code already exists."]}
                )
            raise
        except AuditEventError:
            return Response(
                {"detail": "A server error occurred while recording the audit event."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        except AccessControlError as exc:
            return Response(
                {"detail": "Access control provisioning failed.", "code": getattr(exc, "code", "ACCESS_CONTROL_ERROR")},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        response_serializer = OrganizationDetailSerializer(org)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)

    def partial_update(self, request, *args, **kwargs):
        pk = kwargs.get("pk")
        try:
            with transaction.atomic():
                try:
                    org = Organization.objects.select_for_update().get(pk=pk)
                except (Organization.DoesNotExist, ValueError):
                    raise exceptions.NotFound()

                # Enforce read-only freeze on retired records
                if org.status == OrganizationStatus.RETIRED:
                    raise exceptions.ValidationError(
                        {"status": ["Cannot modify a retired organization."]}
                    )

                prev_status = org.status
                prev_name = org.name
                prev_description = org.description

                serializer = OrganizationUpdateSerializer(instance=org, data=request.data, partial=True)
                serializer.is_valid(raise_exception=True)

                new_status = serializer.validated_data.get("status")
                new_name = serializer.validated_data.get("name")
                new_description = serializer.validated_data.get("description")

                # Validate lifecycle transition against current locked status
                if new_status and new_status != org.status:
                    allowed = ALLOWED_STATUS_TRANSITIONS.get(org.status, set())
                    if new_status not in allowed:
                        raise exceptions.ValidationError(
                            {"status": [f"Cannot transition organization from '{org.status}' to '{new_status}'."]}
                        )

                status_changed = bool(new_status and new_status != org.status)
                name_changed = bool(new_name is not None and new_name != org.name)
                desc_changed = bool(new_description is not None and new_description != org.description)

                if status_changed or name_changed or desc_changed:
                    if status_changed and new_status == OrganizationStatus.RETIRED:
                        if name_changed or desc_changed:
                            if name_changed:
                                org.name = new_name
                            if desc_changed:
                                org.description = new_description
                            org.updated_by = request.user
                            update_fields = ["updated_by", "updated_at"]
                            if name_changed:
                                update_fields.append("name")
                            if desc_changed:
                                update_fields.append("description")
                            org.save(update_fields=update_fields)

                        from apps.organizations.services import retire_organization
                        org = retire_organization(organization_id=org.id, actor=request.user)
                        resulting_status = org.status

                        action = AuditAction.ORGANIZATION_RETIRED
                        metadata = {
                            "name_changed": name_changed,
                            "description_changed": desc_changed,
                            "previous_status": prev_status,
                            "resulting_status": resulting_status,
                        }
                    else:
                        org = serializer.save(updated_by=request.user)
                        resulting_status = org.status

                        if status_changed:
                            from apps.integration_hub.lifecycle_service import (
                                handle_tenant_deactivated_or_suspended,
                                handle_tenant_lms_entitlement_activated,
                            )
                            if new_status == OrganizationStatus.SUSPENDED:
                                handle_tenant_deactivated_or_suspended(org, status=OrganizationStatus.SUSPENDED, actor=request.user)
                            elif new_status == OrganizationStatus.ACTIVE:
                                handle_tenant_lms_entitlement_activated(org, actor=request.user, source="organization_reactivated")

                        action = AuditAction.ORGANIZATION_UPDATED
                        metadata = {
                            "name_changed": name_changed,
                            "description_changed": desc_changed,
                            "status_changed": status_changed,
                            "previous_status": prev_status,
                            "resulting_status": resulting_status,
                        }

                    record_audit_event(
                        action=action,
                        target_type=AuditTargetType.ORGANIZATION,
                        target_id=org.id,
                        target_repr=org.name,
                        actor=request.user,
                        organization_id=org.id,
                        operation_source=AuditOperationSource.INTERACTIVE,
                        metadata=metadata,
                    )
        except AuditEventError:
            return Response(
                {"detail": "A server error occurred while recording the audit event."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        response_serializer = OrganizationDetailSerializer(org)
        return Response(response_serializer.data, status=status.HTTP_200_OK)
