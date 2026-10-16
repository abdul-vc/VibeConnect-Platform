"""Developer Console Management URL routing.

Provides endpoints for:
- Tenant Admin: /api/v1/tenant/developer/
- Platform Owner: /api/v1/owner/developer/
"""

from django.urls import path

from apps.developer_console.management_views import (
    OwnerDeveloperApplicationDetailView,
    OwnerDeveloperApplicationListView,
    OwnerDeveloperApplicationRevokeView,
    OwnerDeveloperApplicationSuspendView,
    OwnerDeveloperKeyListView,
    OwnerDeveloperKeyRevokeView,
    OwnerDeveloperWebhookDeliveryListView,
    OwnerDeveloperWebhookDetailView,
    OwnerDeveloperWebhookListView,
    OwnerDeveloperWebhookRevokeView,
    OwnerDeveloperWebhookSuspendView,
    TenantDeveloperApplicationDetailView,
    TenantDeveloperApplicationListCreateView,
    TenantDeveloperApplicationReactivateView,
    TenantDeveloperApplicationRevokeView,
    TenantDeveloperApplicationSuspendView,
    TenantDeveloperDeliveryReplayView,
    TenantDeveloperKeyCreateView,
    TenantDeveloperKeyListView,
    TenantDeveloperKeyRevokeView,
    TenantDeveloperKeyRotateView,
    TenantDeveloperWebhookDeliveryListView,
    TenantDeveloperWebhookDetailView,
    TenantDeveloperWebhookListCreateView,
    TenantDeveloperWebhookReactivateView,
    TenantDeveloperWebhookRevokeView,
    TenantDeveloperWebhookRotateSecretView,
    TenantDeveloperWebhookSuspendView,
)

tenant_urlpatterns = [
    path("apps/", TenantDeveloperApplicationListCreateView.as_view(), name="tenant-developer-app-list-create"),
    path("apps/<uuid:pk>/", TenantDeveloperApplicationDetailView.as_view(), name="tenant-developer-app-detail"),
    path("apps/<uuid:pk>/suspend/", TenantDeveloperApplicationSuspendView.as_view(), name="tenant-developer-app-suspend"),
    path("apps/<uuid:pk>/reactivate/", TenantDeveloperApplicationReactivateView.as_view(), name="tenant-developer-app-reactivate"),
    path("apps/<uuid:pk>/revoke/", TenantDeveloperApplicationRevokeView.as_view(), name="tenant-developer-app-revoke"),
    path("apps/<uuid:pk>/keys/", TenantDeveloperKeyListView.as_view(), name="tenant-developer-key-list"),
    path("apps/<uuid:pk>/keys/create/", TenantDeveloperKeyCreateView.as_view(), name="tenant-developer-key-create-alt"),
    path("apps/<uuid:pk>/keys/<uuid:key_id>/rotate/", TenantDeveloperKeyRotateView.as_view(), name="tenant-developer-key-rotate"),
    path("apps/<uuid:pk>/keys/<uuid:key_id>/revoke/", TenantDeveloperKeyRevokeView.as_view(), name="tenant-developer-key-revoke"),
    # Webhooks (Phase 6B-6)
    path("apps/<uuid:app_pk>/webhooks/", TenantDeveloperWebhookListCreateView.as_view(), name="tenant-developer-webhook-list-create"),
    path("webhooks/<uuid:pk>/", TenantDeveloperWebhookDetailView.as_view(), name="tenant-developer-webhook-detail"),
    path("webhooks/<uuid:pk>/suspend/", TenantDeveloperWebhookSuspendView.as_view(), name="tenant-developer-webhook-suspend"),
    path("webhooks/<uuid:pk>/reactivate/", TenantDeveloperWebhookReactivateView.as_view(), name="tenant-developer-webhook-reactivate"),
    path("webhooks/<uuid:pk>/revoke/", TenantDeveloperWebhookRevokeView.as_view(), name="tenant-developer-webhook-revoke"),
    path("webhooks/<uuid:pk>/rotate-secret/", TenantDeveloperWebhookRotateSecretView.as_view(), name="tenant-developer-webhook-rotate-secret"),
    path("webhooks/<uuid:pk>/deliveries/", TenantDeveloperWebhookDeliveryListView.as_view(), name="tenant-developer-webhook-delivery-list"),
    path("deliveries/<uuid:pk>/replay/", TenantDeveloperDeliveryReplayView.as_view(), name="tenant-developer-delivery-replay"),
]

owner_urlpatterns = [
    path("apps/", OwnerDeveloperApplicationListView.as_view(), name="owner-developer-app-list"),
    path("apps/<uuid:pk>/", OwnerDeveloperApplicationDetailView.as_view(), name="owner-developer-app-detail"),
    path("apps/<uuid:pk>/suspend/", OwnerDeveloperApplicationSuspendView.as_view(), name="owner-developer-app-suspend"),
    path("apps/<uuid:pk>/revoke/", OwnerDeveloperApplicationRevokeView.as_view(), name="owner-developer-app-revoke"),
    path("apps/<uuid:pk>/keys/", OwnerDeveloperKeyListView.as_view(), name="owner-developer-key-list"),
    path("apps/<uuid:pk>/keys/<uuid:key_id>/revoke/", OwnerDeveloperKeyRevokeView.as_view(), name="owner-developer-key-revoke"),
    # Webhooks (Phase 6B-6)
    path("webhooks/", OwnerDeveloperWebhookListView.as_view(), name="owner-developer-webhook-list"),
    path("webhooks/<uuid:pk>/", OwnerDeveloperWebhookDetailView.as_view(), name="owner-developer-webhook-detail"),
    path("webhooks/<uuid:pk>/suspend/", OwnerDeveloperWebhookSuspendView.as_view(), name="owner-developer-webhook-suspend"),
    path("webhooks/<uuid:pk>/revoke/", OwnerDeveloperWebhookRevokeView.as_view(), name="owner-developer-webhook-revoke"),
    path("webhooks/<uuid:pk>/deliveries/", OwnerDeveloperWebhookDeliveryListView.as_view(), name="owner-developer-webhook-delivery-list"),
]
