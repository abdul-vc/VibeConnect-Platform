"""Audit Log API Views.

Implements AuditLogViewSet providing list and retrieve endpoints with strict
Platform Owner authorization, deterministic ordering, comprehensive parameter
validation, and snapshot-based serialization.
"""

import uuid
from django.db.models import Q
from django.utils.dateparse import parse_datetime
from django.utils.timezone import is_naive, make_aware
from rest_framework import exceptions, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.auditlog.models import AuditAction, AuditLog, AuditTargetType
from apps.auditlog.pagination import AuditLogPagination
from apps.auditlog.retention_service import evaluate_data_retention_dry_run
from apps.auditlog.serializers import AuditLogDetailSerializer, AuditLogListSerializer
from apps.identity.authentication import EnforcedSessionAuthentication
from apps.identity.permissions import IsPlatformOwner

ORDERING_FIELDS_MAP = {
    "timestamp": ["timestamp", "id"],
    "-timestamp": ["-timestamp", "-id"],
    "action": ["action", "-timestamp", "-id"],
    "-action": ["-action", "-timestamp", "-id"],
    "target_type": ["target_type", "-timestamp", "-id"],
    "-target_type": ["-target_type", "-timestamp", "-id"],
}

SUPPORTED_SINGLETON_PARAMS = {
    "action",
    "target_type",
    "actor_id",
    "target_id",
    "organization_id",
    "date_from",
    "date_to",
    "search",
    "ordering",
    "page",
    "page_size",
}


class AuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    """Read-only viewset providing list and detail access to the central audit trail."""

    authentication_classes = [EnforcedSessionAuthentication]
    permission_classes = [IsPlatformOwner]
    pagination_class = AuditLogPagination
    http_method_names = ["get", "head", "options"]

    def _validate_query_params(self):
        """Enforces strict query parameter validation, rejecting unknown and duplicate parameters."""
        # 1. Reject unknown parameters
        for key in self.request.GET.keys():
            if key not in SUPPORTED_SINGLETON_PARAMS:
                raise exceptions.ValidationError(
                    {key: [f"Unexpected query parameter '{key}'."]}
                )

        # 2. Reject duplicate singleton parameters
        for param in SUPPORTED_SINGLETON_PARAMS:
            if len(self.request.GET.getlist(param)) > 1:
                raise exceptions.ValidationError(
                    {param: [f"Duplicate '{param}' parameter is not permitted."]}
                )

    def get_queryset(self):
        self._validate_query_params()

        queryset = AuditLog.objects.all()

        # 1. Filter by action
        action_param = self.request.query_params.get("action")
        if action_param is not None:
            if action_param not in AuditAction.values:
                allowed = ", ".join(AuditAction.values)
                raise exceptions.ValidationError(
                    {"action": [f"Invalid action '{action_param}'. Allowed: {allowed}."]}
                )
            queryset = queryset.filter(action=action_param)

        # 2. Filter by target_type
        target_type_param = self.request.query_params.get("target_type")
        if target_type_param is not None:
            if target_type_param not in AuditTargetType.values:
                allowed = ", ".join(AuditTargetType.values)
                raise exceptions.ValidationError(
                    {"target_type": [f"Invalid target_type '{target_type_param}'. Allowed: {allowed}."]}
                )
            queryset = queryset.filter(target_type=target_type_param)

        # 3. Filter by actor_id
        actor_id_param = self.request.query_params.get("actor_id")
        if actor_id_param is not None:
            try:
                actor_uuid = uuid.UUID(actor_id_param)
            except (ValueError, TypeError):
                raise exceptions.ValidationError(
                    {"actor_id": ["Invalid UUID format for actor_id."]}
                )
            queryset = queryset.filter(actor_id=actor_uuid)

        # 4. Filter by target_id
        target_id_param = self.request.query_params.get("target_id")
        if target_id_param is not None:
            try:
                target_uuid = uuid.UUID(target_id_param)
            except (ValueError, TypeError):
                raise exceptions.ValidationError(
                    {"target_id": ["Invalid UUID format for target_id."]}
                )
            queryset = queryset.filter(target_id=target_uuid)

        # 5. Filter by organization_id
        org_id_param = self.request.query_params.get("organization_id")
        if org_id_param is not None:
            try:
                org_uuid = uuid.UUID(org_id_param)
            except (ValueError, TypeError):
                raise exceptions.ValidationError(
                    {"organization_id": ["Invalid UUID format for organization_id."]}
                )
            queryset = queryset.filter(organization_id=org_uuid)

        # 6. Filter by date_from and date_to
        date_from_param = self.request.query_params.get("date_from")
        date_to_param = self.request.query_params.get("date_to")
        dt_from = None
        dt_to = None

        if date_from_param is not None:
            dt_from = parse_datetime(date_from_param)
            if dt_from is None:
                raise exceptions.ValidationError(
                    {"date_from": ["Invalid ISO 8601 datetime format for date_from."]}
                )
            if is_naive(dt_from):
                dt_from = make_aware(dt_from)
            queryset = queryset.filter(timestamp__gte=dt_from)

        if date_to_param is not None:
            dt_to = parse_datetime(date_to_param)
            if dt_to is None:
                raise exceptions.ValidationError(
                    {"date_to": ["Invalid ISO 8601 datetime format for date_to."]}
                )
            if is_naive(dt_to):
                dt_to = make_aware(dt_to)
            queryset = queryset.filter(timestamp__lte=dt_to)

        if dt_from and dt_to and dt_from > dt_to:
            raise exceptions.ValidationError(
                {"date_from": ["'date_from' cannot be after 'date_to'."]}
            )

        # 7. Search query across snapshot fields
        raw_search = self.request.query_params.get("search")
        if raw_search is not None:
            search = raw_search.strip()
            if len(search) > 100:
                raise exceptions.ValidationError(
                    {"search": ["Search query must be 100 characters or fewer."]}
                )
            if search:
                queryset = queryset.filter(
                    Q(target_repr__icontains=search)
                    | Q(actor_email__icontains=search)
                    | Q(actor_name__icontains=search)
                )

        # 8. Deterministic ordering
        ordering_param = self.request.query_params.get("ordering")
        if ordering_param:
            if ordering_param not in ORDERING_FIELDS_MAP:
                raise exceptions.ValidationError(
                    {"ordering": [f"Invalid ordering field '{ordering_param}'."]}
                )
            order_by = ORDERING_FIELDS_MAP[ordering_param]
        else:
            order_by = ["-timestamp", "-id"]

        return queryset.order_by(*order_by)

    def get_serializer_class(self):
        if self.action == "list":
            return AuditLogListSerializer
        return AuditLogDetailSerializer

    def retrieve(self, request, *args, **kwargs):
        pk = kwargs.get("pk")
        try:
            uuid.UUID(str(pk))
            instance = self.get_object()
        except (ValueError, TypeError, exceptions.NotFound):
            raise exceptions.NotFound()
        serializer = self.get_serializer(instance)
        return Response(serializer.data)

    @action(detail=False, methods=["get"], url_path="retention-evaluation")
    def retention_evaluation(self, request, *args, **kwargs):
        if (
            getattr(request, "impersonation_session", None)
            or getattr(request, "_is_impersonated", False)
            or request.META.get("HTTP_X_VIBECONNECT_IMPERSONATION_SESSION")
        ):
            raise exceptions.PermissionDenied(
                {"code": "OPERATION_BLOCKED_DURING_IMPERSONATION", "detail": "Retention evaluation is not permitted during an active impersonation session."}
            )
        data = evaluate_data_retention_dry_run()
        return Response(data)


from rest_framework.views import APIView
from apps.access_control.views import RequireTenantContext, get_tenant_organization_from_request


class TenantAuditLogListView(APIView):
    """Organization-scoped, read-only audit activity log for tenant administrators."""

    authentication_classes = [EnforcedSessionAuthentication]
    permission_classes = [RequireTenantContext]
    pagination_class = AuditLogPagination

    def get(self, request, *args, **kwargs) -> Response:
        org = get_tenant_organization_from_request(request)
        queryset = AuditLog.objects.filter(organization_id=org.id).order_by("-timestamp", "-id")

        search = request.query_params.get("search")
        if search:
            queryset = queryset.filter(
                Q(target_repr__icontains=search)
                | Q(actor_email__icontains=search)
                | Q(actor_name__icontains=search)
            )

        action_param = request.query_params.get("action")
        if action_param:
            queryset = queryset.filter(action=action_param)

        paginator = self.pagination_class()
        page = paginator.paginate_queryset(queryset, request, view=self)
        serializer = AuditLogListSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)


