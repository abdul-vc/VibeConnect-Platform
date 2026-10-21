"""URL routing for Notifications (Phase 3A)."""

from django.urls import path

from apps.notifications.views import (
    NotificationDeliveryListView,
    NotificationDeliveryRetryView,
    NotificationTemplateDetailView,
    NotificationTemplateListCreateView,
    NotificationTemplateNewVersionView,
    NotificationTemplatePreviewView,
    NotificationTemplateRetireView,
)

urlpatterns = [
    path("templates/", NotificationTemplateListCreateView.as_view(), name="notification-template-list-create"),
    path("templates/<uuid:pk>/", NotificationTemplateDetailView.as_view(), name="notification-template-detail"),
    path("templates/<uuid:pk>/new-version/", NotificationTemplateNewVersionView.as_view(), name="notification-template-new-version"),
    path("templates/<uuid:pk>/retire/", NotificationTemplateRetireView.as_view(), name="notification-template-retire"),
    path("templates/<uuid:pk>/preview/", NotificationTemplatePreviewView.as_view(), name="notification-template-preview"),
    path("deliveries/", NotificationDeliveryListView.as_view(), name="notification-delivery-list"),
    path("deliveries/<uuid:pk>/retry/", NotificationDeliveryRetryView.as_view(), name="notification-delivery-retry"),
]
