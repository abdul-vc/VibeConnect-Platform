import re

from django.db.models import Max, Q
from django.template.loader import TemplateDoesNotExist, get_template
from rest_framework import status
from rest_framework.exceptions import PermissionDenied
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.access_control.services.evaluation import evaluate_access
from apps.identity.permissions import IsPlatformOwner
from apps.notifications.models import (
    NotificationChannel,
    NotificationDelivery,
    NotificationDeliveryStatus,
    NotificationTemplate,
    NotificationTemplateStatus,
)
from apps.notifications.serializers import (
    CreateNotificationTemplateSerializer,
    NewTemplateVersionSerializer,
    NotificationDeliverySerializer,
    NotificationTemplateSerializer,
    TemplatePreviewSerializer,
)
from apps.notifications.services import (
    DEFAULT_NOTIFICATION_TEMPLATES,
    execute_delivery,
    render_template_string,
)


class NotificationPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


def _can_view_notifications(user) -> bool:
    """Check if authenticated user can view notifications (platform owner or tenant with notifications.view)."""
    if getattr(user, "is_platform_owner", False):
        return True
    # Check if user has active membership in any org with notifications.view
    for m in user.organization_memberships.filter(status="active"):
        eval_result = evaluate_access(user, "tenant", m.organization_id)
        if eval_result.has_permission("notifications.view"):
            return True
    return False


class NotificationTemplateListCreateView(APIView):
    """List notification templates and create new base templates."""

    permission_classes = [IsAuthenticated]
    pagination_class = NotificationPagination

    def get(self, request):
        if not _can_view_notifications(request.user):
            raise PermissionDenied("You do not have permission to view notification templates.")

        qs = NotificationTemplate.objects.all().order_by("code", "-version")

        # Filters
        channel = request.query_params.get("channel")
        if channel:
            qs = qs.filter(channel=channel)

        tmpl_status = request.query_params.get("status")
        if tmpl_status:
            qs = qs.filter(status=tmpl_status)

        search = request.query_params.get("search")
        if search:
            qs = qs.filter(Q(code__icontains=search) | Q(name__icontains=search))

        # Tenant users only see active templates
        if not getattr(request.user, "is_platform_owner", False):
            qs = qs.filter(status=NotificationTemplateStatus.ACTIVE)

        paginator = self.pagination_class()
        page = paginator.paginate_queryset(qs, request)
        serializer = NotificationTemplateSerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    def post(self, request):
        if not getattr(request.user, "is_platform_owner", False):
            raise PermissionDenied("Only Platform Owners can create notification templates.")

        serializer = CreateNotificationTemplateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        template = NotificationTemplate.objects.create(
            code=data["code"].strip().lower(),
            name=data["name"].strip(),
            channel=data.get("channel", NotificationChannel.EMAIL),
            version=1,
            subject_template=data["subject_template"].strip(),
            body_ref=data["body_ref"].strip(),
            status=NotificationTemplateStatus.ACTIVE,
            is_transactional=data.get("is_transactional", True),
        )

        return Response(NotificationTemplateSerializer(template).data, status=status.HTTP_201_CREATED)


class NotificationTemplateDetailView(APIView):
    """Retrieve details for a specific notification template."""

    permission_classes = [IsAuthenticated]

    def get(self, request, pk: str):
        if not _can_view_notifications(request.user):
            raise PermissionDenied("You do not have permission to view notification templates.")

        try:
            template = NotificationTemplate.objects.get(id=pk)
        except NotificationTemplate.DoesNotExist:
            return Response({"detail": "Template not found."}, status=status.HTTP_404_NOT_FOUND)

        if not getattr(request.user, "is_platform_owner", False) and template.status != NotificationTemplateStatus.ACTIVE:
            raise PermissionDenied("You do not have permission to view this template.")

        return Response(NotificationTemplateSerializer(template).data)


class NotificationTemplateNewVersionView(APIView):
    """Create a new version of an existing template (Platform Owner only)."""

    permission_classes = [IsAuthenticated, IsPlatformOwner]

    def post(self, request, pk: str):
        try:
            current_template = NotificationTemplate.objects.get(id=pk)
        except NotificationTemplate.DoesNotExist:
            return Response({"detail": "Template not found."}, status=status.HTTP_404_NOT_FOUND)

        serializer = NewTemplateVersionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        # Determine next version monotonically
        max_ver = (
            NotificationTemplate.objects.filter(
                code=current_template.code,
                channel=current_template.channel,
            ).aggregate(max_v=Max("version"))["max_v"]
            or current_template.version
        )

        new_version_num = max_ver + 1

        new_template = NotificationTemplate.objects.create(
            code=current_template.code,
            name=data.get("name") or current_template.name,
            channel=current_template.channel,
            version=new_version_num,
            subject_template=data["subject_template"].strip(),
            body_ref=data["body_ref"].strip(),
            status=NotificationTemplateStatus.ACTIVE,
            is_transactional=data.get("is_transactional", current_template.is_transactional),
        )

        return Response(NotificationTemplateSerializer(new_template).data, status=status.HTTP_201_CREATED)


class NotificationTemplateRetireView(APIView):
    """Retire a notification template (Platform Owner only)."""

    permission_classes = [IsAuthenticated, IsPlatformOwner]

    def post(self, request, pk: str):
        try:
            template = NotificationTemplate.objects.get(id=pk)
        except NotificationTemplate.DoesNotExist:
            return Response({"detail": "Template not found."}, status=status.HTTP_404_NOT_FOUND)

        template.status = NotificationTemplateStatus.RETIRED
        template.save(update_fields=["status", "updated_at"])

        return Response(NotificationTemplateSerializer(template).data, status=status.HTTP_200_OK)


DEFAULT_SAMPLE_CONTEXT = {
    "org_name": "Acme Global",
    "role_name": "Administrator",
    "activation_url": "https://vibeconnect.internal/auth/activate?token=sample_token_xyz",
    "expires_at": "in 48 hours",
    "user_name": "Alex Mercer",
    "recipient_name": "Alex Mercer",
    "actor_name": "Platform Admin",
    "platform_name": "VibeConnect",
    "code": "VC-8921",
    "link": "https://vibeconnect.internal/dashboard",
}


class NotificationTemplatePreviewView(APIView):
    """Preview rendered subject and body for a notification template."""

    permission_classes = [IsAuthenticated]

    def post(self, request, pk: str):
        if not _can_view_notifications(request.user):
            raise PermissionDenied("You do not have permission to preview notification templates.")

        try:
            template = NotificationTemplate.objects.get(id=pk)
        except NotificationTemplate.DoesNotExist:
            return Response({"detail": "Template not found."}, status=status.HTTP_404_NOT_FOUND)

        serializer = TemplatePreviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user_context = serializer.validated_data.get("context", {})

        # Merge user context over standard sample context so variables are resolved cleanly
        resolved_context = {**DEFAULT_SAMPLE_CONTEXT, **user_context}

        try:
            rendered_subject = render_template_string(template.subject_template, resolved_context)
        except Exception as exc:
            return Response(
                {"detail": f"Failed to render subject template: {exc}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Render body using template file or default string template
        body = None
        if not resolved_context.get("body_template") and template.body_ref:
            try:
                loaded = get_template(template.body_ref)
                body = loaded.render(resolved_context)
            except (TemplateDoesNotExist, Exception):
                body = None

        raw_body_template = (
            resolved_context.get("body_template")
            or DEFAULT_NOTIFICATION_TEMPLATES.get(template.code)
            or f"Notification: {template.name}\n\nReference: {template.body_ref}"
        )
        if not body:
            try:
                body = render_template_string(raw_body_template, resolved_context)
            except Exception:
                body = raw_body_template

        # Detect template variables in subject & body
        combined_text = f"{template.subject_template} {raw_body_template}"
        found_vars = sorted(list(set(re.findall(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}", combined_text))))
        unresolved_vars = [v for v in found_vars if v not in resolved_context or resolved_context[v] == ""]

        return Response(
            {
                "template_id": str(template.id),
                "code": template.code,
                "name": template.name,
                "version": template.version,
                "channel": template.channel,
                "rendered_subject": rendered_subject,
                "rendered_body": body,
                "body_ref": template.body_ref,
                "context": resolved_context,
                "supported_variables": found_vars,
                "unresolved_variables": unresolved_vars,
            },
            status=status.HTTP_200_OK,
        )


class NotificationDeliveryRetryView(APIView):
    """Manually trigger a retry for a queued, failed, or retrying delivery (Platform Owner only)."""

    permission_classes = [IsAuthenticated, IsPlatformOwner]

    def post(self, request, pk: str):
        try:
            delivery = NotificationDelivery.objects.select_related("template", "recipient_user").get(id=pk)
        except NotificationDelivery.DoesNotExist:
            return Response({"detail": "Delivery not found."}, status=status.HTTP_404_NOT_FOUND)

        if delivery.status == NotificationDeliveryStatus.SENT:
            return Response(
                {"detail": "Delivery has already been successfully sent."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Allow manual retry even if maximum automated retries were reached
        if delivery.retry_count >= delivery.max_retries:
            delivery.max_retries = delivery.retry_count + 1
            delivery.save(update_fields=["max_retries"])

        try:
            updated_delivery = execute_delivery(delivery.id)
            return Response(
                NotificationDeliverySerializer(updated_delivery).data,
                status=status.HTTP_200_OK,
            )
        except Exception as exc:
            return Response(
                {"detail": f"Retry execution failed: {str(exc)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class NotificationDeliveryListView(APIView):
    """List notification deliveries with status and channel filters."""

    permission_classes = [IsAuthenticated]
    pagination_class = NotificationPagination

    def get(self, request):
        user = request.user
        is_owner = getattr(user, "is_platform_owner", False)

        qs = NotificationDelivery.objects.select_related("template").all().order_by("-queued_at")

        # Scoping:
        if is_owner:
            pass  # Owner sees all deliveries
        else:
            # Check user's tenant permissions
            active_memberships = list(user.organization_memberships.filter(status="active"))
            has_tenant_view = False
            for m in active_memberships:
                eval_res = evaluate_access(user, "tenant", m.organization_id)
                if eval_res.has_permission("notifications.view"):
                    has_tenant_view = True
                    break

            if has_tenant_view:
                # Can view deliveries addressed to themselves or their organization's members
                qs = qs.filter(Q(recipient_user=user) | Q(recipient_email=user.email))
            else:
                qs = qs.filter(recipient_user=user)

        # Filters
        delivery_status = request.query_params.get("status")
        if delivery_status:
            qs = qs.filter(status=delivery_status)

        channel = request.query_params.get("channel")
        if channel:
            qs = qs.filter(template__channel=channel)

        search = request.query_params.get("search")
        if search:
            qs = qs.filter(
                Q(recipient_email__icontains=search)
                | Q(template__code__icontains=search)
                | Q(template__name__icontains=search)
            )

        paginator = self.pagination_class()
        page = paginator.paginate_queryset(qs, request)
        serializer = NotificationDeliverySerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)
