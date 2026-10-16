"""Organizations URL Configuration.

Registers the versioned OrganizationViewSet endpoints under /api/v1/organizations/
and nested OrganizationMembershipViewSet endpoints under /api/v1/organizations/<organization_id>/memberships/.
"""

from django.urls import path
from rest_framework.routers import SimpleRouter
from apps.organizations.views import OrganizationViewSet
from apps.organizations.membership_views import OrganizationMembershipViewSet

router = SimpleRouter()
router.register(r"", OrganizationViewSet, basename="organization")

membership_list = OrganizationMembershipViewSet.as_view({
    "get": "list",
    "post": "create",
})
membership_detail = OrganizationMembershipViewSet.as_view({
    "get": "retrieve",
    "patch": "partial_update",
})
membership_suspend = OrganizationMembershipViewSet.as_view({"post": "suspend"})
membership_reactivate = OrganizationMembershipViewSet.as_view({"post": "reactivate"})
membership_end = OrganizationMembershipViewSet.as_view({"post": "end"})
membership_restore = OrganizationMembershipViewSet.as_view({"post": "restore"})

urlpatterns = [
    path("<uuid:organization_id>/memberships/", membership_list, name="organization-membership-list"),
    path("<uuid:organization_id>/memberships/<uuid:pk>/", membership_detail, name="organization-membership-detail"),
    path("<uuid:organization_id>/memberships/<uuid:pk>/suspend/", membership_suspend, name="organization-membership-suspend"),
    path("<uuid:organization_id>/memberships/<uuid:pk>/reactivate/", membership_reactivate, name="organization-membership-reactivate"),
    path("<uuid:organization_id>/memberships/<uuid:pk>/end/", membership_end, name="organization-membership-end"),
    path("<uuid:organization_id>/memberships/<uuid:pk>/restore/", membership_restore, name="organization-membership-restore"),
] + router.urls
