"""URL Routing for Access Requests & Approvals (Phase 3F)."""

from django.urls import path

from apps.access_requests.views import (
    AccessRequestApproveView,
    AccessRequestCancelView,
    AccessRequestDenyView,
    AccessRequestDetailView,
    AccessRequestListCreateView,
)

urlpatterns = [
    path("", AccessRequestListCreateView.as_view(), name="access-request-list-create"),
    path("<uuid:pk>/", AccessRequestDetailView.as_view(), name="access-request-detail"),
    path("<uuid:pk>/approve/", AccessRequestApproveView.as_view(), name="access-request-approve"),
    path("<uuid:pk>/deny/", AccessRequestDenyView.as_view(), name="access-request-deny"),
    path("<uuid:pk>/cancel/", AccessRequestCancelView.as_view(), name="access-request-cancel"),
]
