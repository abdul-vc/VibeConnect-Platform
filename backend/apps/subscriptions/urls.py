"""VibeConnect Phase 2C Subscriptions URL Routing.

Direct explicit routing for subscription collection, trial initiation, detail, and lifecycle actions.
"""

from django.urls import path
from apps.subscriptions.views import SubscriptionViewSet

urlpatterns = [
    # 1. Collection & Creation
    path("", SubscriptionViewSet.as_view({"get": "list", "post": "create"}), name="subscription-list-create"),
    path("trial/", SubscriptionViewSet.as_view({"post": "start_trial"}), name="subscription-start-trial"),

    # 2. Detail & Lifecycle Mutations
    path("<str:pk>/", SubscriptionViewSet.as_view({"get": "retrieve"}), name="subscription-detail"),
    path("<str:pk>/convert-trial/", SubscriptionViewSet.as_view({"post": "convert_trial"}), name="subscription-convert-trial"),
    path("<str:pk>/change-plan/", SubscriptionViewSet.as_view({"post": "change_plan"}), name="subscription-change-plan"),
    path("<str:pk>/suspend/", SubscriptionViewSet.as_view({"post": "suspend"}), name="subscription-suspend"),
    path("<str:pk>/reactivate/", SubscriptionViewSet.as_view({"post": "reactivate"}), name="subscription-reactivate"),
    path("<str:pk>/cancel/", SubscriptionViewSet.as_view({"post": "cancel"}), name="subscription-cancel"),
    path("<str:pk>/reconcile/", SubscriptionViewSet.as_view({"post": "reconcile"}), name="subscription-reconcile"),
    path("<str:pk>/entitlements/", SubscriptionViewSet.as_view({"get": "entitlements"}), name="subscription-entitlements"),
]
