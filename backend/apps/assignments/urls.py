"""URL routing for Assignment Domain APIs."""

from django.urls import path

from apps.assignments.views import (
    AssignmentDetailView,
    AssignmentListCreateView,
    AssignmentModulesView,
    AssignmentReactivateView,
    AssignmentRevokeView,
    AssignmentSuspendView,
    SelectorMembersView,
    SelectorModulesView,
    SelectorProductsView,
)

app_name = "assignments"

urlpatterns = [
    # Selectors (must come before <uuid:pk>/)
    path(
        "tenant/assignments/selectors/products/",
        SelectorProductsView.as_view(),
        name="selector-products",
    ),
    path(
        "tenant/assignments/selectors/members/",
        SelectorMembersView.as_view(),
        name="selector-members",
    ),
    path(
        "tenant/assignments/selectors/modules/",
        SelectorModulesView.as_view(),
        name="selector-modules",
    ),
    # Core assignment endpoints
    path(
        "tenant/assignments/",
        AssignmentListCreateView.as_view(),
        name="assignment-list-create",
    ),
    path(
        "tenant/assignments/<uuid:pk>/",
        AssignmentDetailView.as_view(),
        name="assignment-detail",
    ),
    path(
        "tenant/assignments/<uuid:pk>/suspend/",
        AssignmentSuspendView.as_view(),
        name="assignment-suspend",
    ),
    path(
        "tenant/assignments/<uuid:pk>/reactivate/",
        AssignmentReactivateView.as_view(),
        name="assignment-reactivate",
    ),
    path(
        "tenant/assignments/<uuid:pk>/revoke/",
        AssignmentRevokeView.as_view(),
        name="assignment-revoke",
    ),
    path(
        "tenant/assignments/<uuid:pk>/modules/",
        AssignmentModulesView.as_view(),
        name="assignment-modules",
    ),
]
