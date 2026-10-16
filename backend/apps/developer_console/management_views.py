"""Developer Console Management Views.

Provides:
- Tenant Admin endpoints under /api/v1/tenant/developer/
- Platform Owner oversight endpoints under /api/v1/owner/developer/
"""

import uuid
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import exceptions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.auditlog.models import AuditAction
from apps.developer_console.permissions import (
    IsPlatformOwnerForDeveloperConsole,
    IsTenantAdminForDeveloperConsole,
)
from apps.developer_console.serializers import (
    DeveloperApiKeyCreatedResponseSerializer,
    DeveloperApiKeyCreateSerializer,
    DeveloperApiKeySerializer,
    DeveloperApplicationCreateSerializer,
    DeveloperApplicationSerializer,
    DeveloperApplicationUpdateSerializer,
    DeveloperWebhookDeliverySerializer,
    DeveloperWebhookSubscriptionCreatedResponseSerializer,
    DeveloperWebhookSubscriptionCreateSerializer,
    DeveloperWebhookSubscriptionSerializer,
    DeveloperWebhookSubscriptionUpdateSerializer,
)
from apps.developer_console.services.audit_service import (
    audit_developer_application_event,
    audit_developer_key_event,
    audit_developer_webhook_event,
)
from apps.developer_console.services.key_service import (
    generate_api_key,
    revoke_api_key,
    rotate_api_key,
)
from apps.developer_console.services.webhook_service import (
    create_webhook_subscription,
    deliver_webhook,
    reactivate_webhook_subscription,
    replay_webhook_delivery,
    revoke_webhook_subscription,
    rotate_webhook_secret,
    suspend_webhook_subscription,
    update_webhook_subscription,
)
from apps.developer_console.models import (
    DeveloperApiKey,
    DeveloperApplication,
    DeveloperWebhookDelivery,
    DeveloperWebhookSubscription,
)
from apps.identity.authentication import EnforcedSessionAuthentication


# =========================================================================
# TENANT ADMIN MANAGEMENT VIEWS (/api/v1/tenant/developer/)
# =========================================================================

class TenantDeveloperApplicationListCreateView(APIView):
    authentication_classes = [EnforcedSessionAuthentication]
    permission_classes = [IsTenantAdminForDeveloperConsole]

    def get(self, request):
        queryset = DeveloperApplication.objects.filter(
            organization=request.tenant
        ).select_related("organization", "created_by").prefetch_related("api_keys").order_by("-created_at")

        search = request.query_params.get("search")
        if search:
            queryset = queryset.filter(name__icontains=search.strip())

        serializer = DeveloperApplicationSerializer(queryset, many=True)
        return Response({"results": serializer.data, "count": queryset.count()})

    def post(self, request):
        serializer = DeveloperApplicationCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        with transaction.atomic():
            app = DeveloperApplication.objects.create(
                organization=request.tenant,
                name=data["name"].strip(),
                description=data.get("description", "").strip(),
                status="active",
                created_by=request.user,
            )
            audit_developer_application_event(
                request=request,
                action=AuditAction.DEVELOPER_APPLICATION_CREATED,
                application=app,
                resulting_status="active",
            )

        resp_serializer = DeveloperApplicationSerializer(app)
        return Response(resp_serializer.data, status=status.HTTP_201_CREATED)


class TenantDeveloperApplicationDetailView(APIView):
    authentication_classes = [EnforcedSessionAuthentication]
    permission_classes = [IsTenantAdminForDeveloperConsole]

    def get(self, request, pk):
        app = get_object_or_404(
            DeveloperApplication.objects.select_related("organization", "created_by").prefetch_related("api_keys"),
            pk=pk,
            organization=request.tenant,
        )
        serializer = DeveloperApplicationSerializer(app)
        return Response(serializer.data)

    def patch(self, request, pk):
        app = get_object_or_404(
            DeveloperApplication.objects.select_related("organization", "created_by"),
            pk=pk,
            organization=request.tenant,
        )
        if app.status == "revoked":
            raise exceptions.ValidationError({"detail": "Cannot update a revoked application."})

        serializer = DeveloperApplicationUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        update_fields = []
        if "name" in data and data["name"].strip():
            app.name = data["name"].strip()
            update_fields.append("name")
        if "description" in data:
            app.description = data["description"].strip()
            update_fields.append("description")

        if update_fields:
            update_fields.append("updated_at")
            with transaction.atomic():
                app.save(update_fields=update_fields)
                audit_developer_application_event(
                    request=request,
                    action=AuditAction.DEVELOPER_APPLICATION_UPDATED,
                    application=app,
                )

        resp_serializer = DeveloperApplicationSerializer(app)
        return Response(resp_serializer.data)


class TenantDeveloperApplicationSuspendView(APIView):
    authentication_classes = [EnforcedSessionAuthentication]
    permission_classes = [IsTenantAdminForDeveloperConsole]

    def post(self, request, pk):
        app = get_object_or_404(
            DeveloperApplication.objects.select_related("organization", "created_by"),
            pk=pk,
            organization=request.tenant,
        )
        if app.status == "revoked":
            raise exceptions.ValidationError({"detail": "Cannot suspend a revoked application."})
        if app.status == "suspended":
            return Response(DeveloperApplicationSerializer(app).data)

        prev_status = app.status
        with transaction.atomic():
            app.status = "suspended"
            app.save(update_fields=["status", "updated_at"])
            audit_developer_application_event(
                request=request,
                action=AuditAction.DEVELOPER_APPLICATION_SUSPENDED,
                application=app,
                previous_status=prev_status,
                resulting_status="suspended",
                reason=request.data.get("reason"),
            )

        return Response(DeveloperApplicationSerializer(app).data)


class TenantDeveloperApplicationReactivateView(APIView):
    authentication_classes = [EnforcedSessionAuthentication]
    permission_classes = [IsTenantAdminForDeveloperConsole]

    def post(self, request, pk):
        app = get_object_or_404(
            DeveloperApplication.objects.select_related("organization", "created_by"),
            pk=pk,
            organization=request.tenant,
        )
        if app.status == "revoked":
            raise exceptions.ValidationError({"detail": "Cannot reactivate a revoked application."})
        if app.status == "active":
            return Response(DeveloperApplicationSerializer(app).data)

        prev_status = app.status
        with transaction.atomic():
            app.status = "active"
            app.save(update_fields=["status", "updated_at"])
            audit_developer_application_event(
                request=request,
                action=AuditAction.DEVELOPER_APPLICATION_REACTIVATED,
                application=app,
                previous_status=prev_status,
                resulting_status="active",
                reason=request.data.get("reason"),
            )

        return Response(DeveloperApplicationSerializer(app).data)


class TenantDeveloperApplicationRevokeView(APIView):
    authentication_classes = [EnforcedSessionAuthentication]
    permission_classes = [IsTenantAdminForDeveloperConsole]

    def post(self, request, pk):
        app = get_object_or_404(
            DeveloperApplication.objects.select_related("organization", "created_by"),
            pk=pk,
            organization=request.tenant,
        )
        if app.status == "revoked":
            return Response(DeveloperApplicationSerializer(app).data)

        prev_status = app.status
        now = timezone.now()
        with transaction.atomic():
            app.status = "revoked"
            app.save(update_fields=["status", "updated_at"])

            # Revoke all active keys
            active_keys = list(app.api_keys.filter(status="active"))
            for key in active_keys:
                key.status = "revoked"
                key.revoked_at = now
                key.save(update_fields=["status", "revoked_at"])
                audit_developer_key_event(
                    request=request,
                    action=AuditAction.DEVELOPER_KEY_REVOKED,
                    key=key,
                    previous_status="active",
                    resulting_status="revoked",
                    reason="Application revoked",
                )

            audit_developer_application_event(
                request=request,
                action=AuditAction.DEVELOPER_APPLICATION_REVOKED,
                application=app,
                previous_status=prev_status,
                resulting_status="revoked",
                reason=request.data.get("reason"),
            )

        return Response(DeveloperApplicationSerializer(app).data)


class TenantDeveloperKeyListView(APIView):
    authentication_classes = [EnforcedSessionAuthentication]
    permission_classes = [IsTenantAdminForDeveloperConsole]

    def get(self, request, pk):
        app = get_object_or_404(DeveloperApplication, pk=pk, organization=request.tenant)
        keys = app.api_keys.all().order_by("-created_at")
        serializer = DeveloperApiKeySerializer(keys, many=True)
        return Response({"results": serializer.data, "count": keys.count()})

    def post(self, request, pk):
        return TenantDeveloperKeyCreateView().post(request, pk)


class TenantDeveloperKeyCreateView(APIView):
    authentication_classes = [EnforcedSessionAuthentication]
    permission_classes = [IsTenantAdminForDeveloperConsole]

    def post(self, request, pk):
        app = get_object_or_404(DeveloperApplication, pk=pk, organization=request.tenant)
        if app.status == "revoked":
            raise exceptions.ValidationError({"detail": "Cannot generate keys for a revoked application."})
        if app.status == "suspended":
            raise exceptions.ValidationError({"detail": "Cannot generate keys for a suspended application."})

        serializer = DeveloperApiKeyCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        with transaction.atomic():
            api_key, plaintext_key = generate_api_key(
                name=data["name"].strip(),
                application=app,
                scopes=data["scopes"],
                expires_at=data.get("expires_at"),
            )
            audit_developer_key_event(
                request=request,
                action=AuditAction.DEVELOPER_KEY_CREATED,
                key=api_key,
                resulting_status="active",
            )

        resp_data = DeveloperApiKeySerializer(api_key).data
        resp_data["plaintext_key"] = plaintext_key
        return Response(resp_data, status=status.HTTP_201_CREATED)


class TenantDeveloperKeyRotateView(APIView):
    authentication_classes = [EnforcedSessionAuthentication]
    permission_classes = [IsTenantAdminForDeveloperConsole]

    def post(self, request, pk, key_id):
        app = get_object_or_404(DeveloperApplication, pk=pk, organization=request.tenant)
        if app.status == "revoked":
            raise exceptions.ValidationError({"detail": "Cannot rotate keys for a revoked application."})

        old_key = get_object_or_404(DeveloperApiKey, pk=key_id, application=app)
        if old_key.status == "revoked":
            raise exceptions.ValidationError({"detail": "Cannot rotate an already revoked API key."})

        with transaction.atomic():
            new_key, plaintext_key = rotate_api_key(
                old_key=old_key,
                name=request.data.get("name"),
                expires_at=request.data.get("expires_at"),
            )
            audit_developer_key_event(
                request=request,
                action=AuditAction.DEVELOPER_KEY_ROTATED,
                key=new_key,
                resulting_status="active",
                old_key=old_key,
            )

        resp_data = DeveloperApiKeySerializer(new_key).data
        resp_data["plaintext_key"] = plaintext_key
        return Response(resp_data, status=status.HTTP_200_OK)


class TenantDeveloperKeyRevokeView(APIView):
    authentication_classes = [EnforcedSessionAuthentication]
    permission_classes = [IsTenantAdminForDeveloperConsole]

    def post(self, request, pk, key_id):
        app = get_object_or_404(DeveloperApplication, pk=pk, organization=request.tenant)
        key = get_object_or_404(DeveloperApiKey, pk=key_id, application=app)

        if key.status == "revoked":
            return Response(DeveloperApiKeySerializer(key).data)

        prev_status = key.status
        with transaction.atomic():
            key = revoke_api_key(key)
            audit_developer_key_event(
                request=request,
                action=AuditAction.DEVELOPER_KEY_REVOKED,
                key=key,
                previous_status=prev_status,
                resulting_status="revoked",
                reason=request.data.get("reason"),
            )

        return Response(DeveloperApiKeySerializer(key).data)


# =========================================================================
# PLATFORM OWNER OVERSIGHT VIEWS (/api/v1/owner/developer/)
# =========================================================================

class OwnerDeveloperApplicationListView(APIView):
    authentication_classes = [EnforcedSessionAuthentication]
    permission_classes = [IsPlatformOwnerForDeveloperConsole]

    def get(self, request):
        queryset = DeveloperApplication.objects.all().select_related(
            "organization", "created_by"
        ).prefetch_related("api_keys").order_by("-created_at")

        search = request.query_params.get("search")
        if search:
            queryset = queryset.filter(name__icontains=search.strip())

        org_id = request.query_params.get("organization_id")
        if org_id:
            try:
                queryset = queryset.filter(organization_id=uuid.UUID(str(org_id)))
            except (ValueError, TypeError):
                pass

        status_param = request.query_params.get("status")
        if status_param:
            queryset = queryset.filter(status=status_param.strip().lower())

        serializer = DeveloperApplicationSerializer(queryset, many=True)
        return Response({"results": serializer.data, "count": queryset.count()})


class OwnerDeveloperApplicationDetailView(APIView):
    authentication_classes = [EnforcedSessionAuthentication]
    permission_classes = [IsPlatformOwnerForDeveloperConsole]

    def get(self, request, pk):
        app = get_object_or_404(
            DeveloperApplication.objects.select_related("organization", "created_by").prefetch_related("api_keys"),
            pk=pk,
        )
        serializer = DeveloperApplicationSerializer(app)
        return Response(serializer.data)


class OwnerDeveloperApplicationSuspendView(APIView):
    authentication_classes = [EnforcedSessionAuthentication]
    permission_classes = [IsPlatformOwnerForDeveloperConsole]

    def post(self, request, pk):
        app = get_object_or_404(
            DeveloperApplication.objects.select_related("organization", "created_by"),
            pk=pk,
        )
        if app.status == "revoked":
            raise exceptions.ValidationError({"detail": "Cannot suspend a revoked application."})
        if app.status == "suspended":
            return Response(DeveloperApplicationSerializer(app).data)

        prev_status = app.status
        with transaction.atomic():
            app.status = "suspended"
            app.save(update_fields=["status", "updated_at"])
            audit_developer_application_event(
                request=request,
                action=AuditAction.DEVELOPER_APPLICATION_SUSPENDED,
                application=app,
                previous_status=prev_status,
                resulting_status="suspended",
                reason=request.data.get("reason", "Platform Owner Administrative Suspension"),
            )

        return Response(DeveloperApplicationSerializer(app).data)


class OwnerDeveloperApplicationRevokeView(APIView):
    authentication_classes = [EnforcedSessionAuthentication]
    permission_classes = [IsPlatformOwnerForDeveloperConsole]

    def post(self, request, pk):
        app = get_object_or_404(
            DeveloperApplication.objects.select_related("organization", "created_by"),
            pk=pk,
        )
        if app.status == "revoked":
            return Response(DeveloperApplicationSerializer(app).data)

        prev_status = app.status
        now = timezone.now()
        with transaction.atomic():
            app.status = "revoked"
            app.save(update_fields=["status", "updated_at"])

            active_keys = list(app.api_keys.filter(status="active"))
            for key in active_keys:
                key.status = "revoked"
                key.revoked_at = now
                key.save(update_fields=["status", "revoked_at"])
                audit_developer_key_event(
                    request=request,
                    action=AuditAction.DEVELOPER_KEY_REVOKED,
                    key=key,
                    previous_status="active",
                    resulting_status="revoked",
                    reason="Application revoked by Platform Owner",
                    is_emergency=True,
                )

            audit_developer_application_event(
                request=request,
                action=AuditAction.DEVELOPER_APPLICATION_REVOKED,
                application=app,
                previous_status=prev_status,
                resulting_status="revoked",
                reason=request.data.get("reason", "Platform Owner Administrative Revocation"),
            )

        return Response(DeveloperApplicationSerializer(app).data)


class OwnerDeveloperKeyListView(APIView):
    authentication_classes = [EnforcedSessionAuthentication]
    permission_classes = [IsPlatformOwnerForDeveloperConsole]

    def get(self, request, pk):
        app = get_object_or_404(DeveloperApplication, pk=pk)
        keys = app.api_keys.all().order_by("-created_at")
        serializer = DeveloperApiKeySerializer(keys, many=True)
        return Response({"results": serializer.data, "count": keys.count()})


class OwnerDeveloperKeyRevokeView(APIView):
    authentication_classes = [EnforcedSessionAuthentication]
    permission_classes = [IsPlatformOwnerForDeveloperConsole]

    def post(self, request, pk, key_id):
        app = get_object_or_404(DeveloperApplication, pk=pk)
        key = get_object_or_404(DeveloperApiKey, pk=key_id, application=app)

        if key.status == "revoked":
            return Response(DeveloperApiKeySerializer(key).data)

        prev_status = key.status
        reason = request.data.get("reason", "Platform Owner Emergency Revocation")
        with transaction.atomic():
            key = revoke_api_key(key)
            audit_developer_key_event(
                request=request,
                action=AuditAction.DEVELOPER_KEY_REVOKED,
                key=key,
                previous_status=prev_status,
                resulting_status="revoked",
                reason=reason,
                is_emergency=True,
            )

        return Response(DeveloperApiKeySerializer(key).data)


# =========================================================================
# TENANT ADMIN WEBHOOK VIEWS (/api/v1/tenant/developer/)
# =========================================================================

class TenantDeveloperWebhookListCreateView(APIView):
    authentication_classes = [EnforcedSessionAuthentication]
    permission_classes = [IsTenantAdminForDeveloperConsole]

    def get(self, request, app_pk):
        app = get_object_or_404(DeveloperApplication, pk=app_pk, organization=request.tenant)
        webhooks = app.webhook_subscriptions.all().order_by("-created_at")
        serializer = DeveloperWebhookSubscriptionSerializer(webhooks, many=True)
        return Response({"results": serializer.data, "count": webhooks.count()})

    def post(self, request, app_pk):
        app = get_object_or_404(DeveloperApplication, pk=app_pk, organization=request.tenant)
        if app.status != "active":
            raise exceptions.ValidationError(
                {"error": "APPLICATION_NOT_ACTIVE", "detail": "Cannot create webhooks for a non-active application."}
            )

        serializer = DeveloperWebhookSubscriptionCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            subscription, raw_secret = create_webhook_subscription(
                application=app,
                target_url=serializer.validated_data["target_url"],
                event_topics=serializer.validated_data["event_topics"],
                user=request.user,
                request=request,
            )
        except Exception as e:
            raise exceptions.ValidationError({"error": "VALIDATION_ERROR", "detail": str(e)})

        response_serializer = DeveloperWebhookSubscriptionCreatedResponseSerializer(
            subscription,
            context={"signing_secret": raw_secret},
        )
        data = response_serializer.data
        data["signing_secret"] = raw_secret
        return Response(data, status=status.HTTP_201_CREATED)


class TenantDeveloperWebhookDetailView(APIView):
    authentication_classes = [EnforcedSessionAuthentication]
    permission_classes = [IsTenantAdminForDeveloperConsole]

    def get(self, request, pk):
        sub = get_object_or_404(
            DeveloperWebhookSubscription,
            pk=pk,
            application__organization=request.tenant,
        )
        return Response(DeveloperWebhookSubscriptionSerializer(sub).data)

    def patch(self, request, pk):
        sub = get_object_or_404(
            DeveloperWebhookSubscription,
            pk=pk,
            application__organization=request.tenant,
        )
        if sub.status == "revoked":
            raise exceptions.ValidationError(
                {"error": "SUBSCRIPTION_REVOKED", "detail": "Cannot update a revoked webhook subscription."}
            )

        serializer = DeveloperWebhookSubscriptionUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            sub = update_webhook_subscription(
                subscription=sub,
                target_url=serializer.validated_data.get("target_url"),
                event_topics=serializer.validated_data.get("event_topics"),
                user=request.user,
                request=request,
            )
        except Exception as e:
            raise exceptions.ValidationError({"error": "VALIDATION_ERROR", "detail": str(e)})

        return Response(DeveloperWebhookSubscriptionSerializer(sub).data)


class TenantDeveloperWebhookSuspendView(APIView):
    authentication_classes = [EnforcedSessionAuthentication]
    permission_classes = [IsTenantAdminForDeveloperConsole]

    def post(self, request, pk):
        sub = get_object_or_404(
            DeveloperWebhookSubscription,
            pk=pk,
            application__organization=request.tenant,
        )
        reason = request.data.get("reason", "Suspended by Tenant Admin")
        try:
            sub = suspend_webhook_subscription(
                subscription=sub,
                reason=reason,
                user=request.user,
                request=request,
            )
        except Exception as e:
            raise exceptions.ValidationError({"error": "INVALID_STATE", "detail": str(e)})

        return Response(DeveloperWebhookSubscriptionSerializer(sub).data)


class TenantDeveloperWebhookReactivateView(APIView):
    authentication_classes = [EnforcedSessionAuthentication]
    permission_classes = [IsTenantAdminForDeveloperConsole]

    def post(self, request, pk):
        sub = get_object_or_404(
            DeveloperWebhookSubscription,
            pk=pk,
            application__organization=request.tenant,
        )
        try:
            sub = reactivate_webhook_subscription(
                subscription=sub,
                user=request.user,
                request=request,
            )
        except Exception as e:
            raise exceptions.ValidationError({"error": "INVALID_STATE", "detail": str(e)})

        return Response(DeveloperWebhookSubscriptionSerializer(sub).data)


class TenantDeveloperWebhookRevokeView(APIView):
    authentication_classes = [EnforcedSessionAuthentication]
    permission_classes = [IsTenantAdminForDeveloperConsole]

    def post(self, request, pk):
        sub = get_object_or_404(
            DeveloperWebhookSubscription,
            pk=pk,
            application__organization=request.tenant,
        )
        reason = request.data.get("reason", "Revoked by Tenant Admin")
        try:
            sub = revoke_webhook_subscription(
                subscription=sub,
                reason=reason,
                user=request.user,
                request=request,
            )
        except Exception as e:
            raise exceptions.ValidationError({"error": "INVALID_STATE", "detail": str(e)})

        return Response(DeveloperWebhookSubscriptionSerializer(sub).data)


class TenantDeveloperWebhookRotateSecretView(APIView):
    authentication_classes = [EnforcedSessionAuthentication]
    permission_classes = [IsTenantAdminForDeveloperConsole]

    def post(self, request, pk):
        sub = get_object_or_404(
            DeveloperWebhookSubscription,
            pk=pk,
            application__organization=request.tenant,
        )
        if sub.status != "active":
            raise exceptions.ValidationError(
                {"error": "SUBSCRIPTION_NOT_ACTIVE", "detail": "Can only rotate secrets for active subscriptions."}
            )

        try:
            sub, new_secret = rotate_webhook_secret(
                subscription=sub,
                user=request.user,
                request=request,
            )
        except Exception as e:
            raise exceptions.ValidationError({"error": "ROTATION_FAILED", "detail": str(e)})

        data = DeveloperWebhookSubscriptionSerializer(sub).data
        data["signing_secret"] = new_secret
        return Response(data)


class TenantDeveloperWebhookDeliveryListView(APIView):
    authentication_classes = [EnforcedSessionAuthentication]
    permission_classes = [IsTenantAdminForDeveloperConsole]

    def get(self, request, pk):
        sub = get_object_or_404(
            DeveloperWebhookSubscription,
            pk=pk,
            application__organization=request.tenant,
        )
        deliveries = sub.deliveries.all().order_by("-created_at")[:100]
        serializer = DeveloperWebhookDeliverySerializer(deliveries, many=True)
        return Response({"results": serializer.data, "count": deliveries.count()})


class TenantDeveloperDeliveryReplayView(APIView):
    authentication_classes = [EnforcedSessionAuthentication]
    permission_classes = [IsTenantAdminForDeveloperConsole]

    def post(self, request, pk):
        delivery = get_object_or_404(
            DeveloperWebhookDelivery,
            pk=pk,
            subscription__application__organization=request.tenant,
        )
        replayed = replay_webhook_delivery(
            delivery=delivery,
            user=request.user,
            request=request,
        )
        return Response(DeveloperWebhookDeliverySerializer(replayed).data)


# =========================================================================
# PLATFORM OWNER WEBHOOK VIEWS (/api/v1/owner/developer/)
# =========================================================================

class OwnerDeveloperWebhookListView(APIView):
    authentication_classes = [EnforcedSessionAuthentication]
    permission_classes = [IsPlatformOwnerForDeveloperConsole]

    def get(self, request):
        queryset = DeveloperWebhookSubscription.objects.select_related(
            "application", "application__organization"
        ).order_by("-created_at")

        app_id = request.query_params.get("application_id")
        if app_id:
            queryset = queryset.filter(application_id=app_id)

        serializer = DeveloperWebhookSubscriptionSerializer(queryset, many=True)
        return Response({"results": serializer.data, "count": queryset.count()})


class OwnerDeveloperWebhookDetailView(APIView):
    authentication_classes = [EnforcedSessionAuthentication]
    permission_classes = [IsPlatformOwnerForDeveloperConsole]

    def get(self, request, pk):
        sub = get_object_or_404(DeveloperWebhookSubscription, pk=pk)
        return Response(DeveloperWebhookSubscriptionSerializer(sub).data)


class OwnerDeveloperWebhookSuspendView(APIView):
    authentication_classes = [EnforcedSessionAuthentication]
    permission_classes = [IsPlatformOwnerForDeveloperConsole]

    def post(self, request, pk):
        sub = get_object_or_404(DeveloperWebhookSubscription, pk=pk)
        reason = request.data.get("reason", "Platform Owner Administrative Suspension")
        sub = suspend_webhook_subscription(
            subscription=sub,
            reason=reason,
            user=request.user,
            request=request,
        )
        return Response(DeveloperWebhookSubscriptionSerializer(sub).data)


class OwnerDeveloperWebhookRevokeView(APIView):
    authentication_classes = [EnforcedSessionAuthentication]
    permission_classes = [IsPlatformOwnerForDeveloperConsole]

    def post(self, request, pk):
        sub = get_object_or_404(DeveloperWebhookSubscription, pk=pk)
        reason = request.data.get("reason", "Platform Owner Administrative Revocation")
        sub = revoke_webhook_subscription(
            subscription=sub,
            reason=reason,
            user=request.user,
            request=request,
        )
        return Response(DeveloperWebhookSubscriptionSerializer(sub).data)


class OwnerDeveloperWebhookDeliveryListView(APIView):
    authentication_classes = [EnforcedSessionAuthentication]
    permission_classes = [IsPlatformOwnerForDeveloperConsole]

    def get(self, request, pk):
        sub = get_object_or_404(DeveloperWebhookSubscription, pk=pk)
        deliveries = sub.deliveries.all().order_by("-created_at")[:100]
        serializer = DeveloperWebhookDeliverySerializer(deliveries, many=True)
        return Response({"results": serializer.data, "count": deliveries.count()})
