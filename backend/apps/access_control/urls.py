"""Access Control URL Routing Configuration (Phase 2E Stages 4 & 5).

Registers:
- Platform Owner endpoints:
  - GET   organizations/<uuid:organization_id>/console-policies/
  - PATCH organizations/<uuid:organization_id>/console-policies/<str:module_key>/
  - GET   organizations/<uuid:organization_id>/permission-ceilings/
  - PATCH organizations/<uuid:organization_id>/permission-ceilings/<str:permission_key>/
- Tenant Admin endpoints:
  - GET   tenant/access-catalog/
  - GET   tenant/roles/
  - POST  tenant/roles/
  - GET   tenant/roles/<uuid:role_id>/
  - PATCH tenant/roles/<uuid:role_id>/
  - POST  tenant/roles/<uuid:role_id>/retire/
  - GET   tenant/admin-memberships/
  - PATCH tenant/admin-memberships/<uuid:membership_id>/role/
"""

from django.urls import path

from apps.access_control.views import (
    OrganizationConsolePolicyDetailView,
    OrganizationConsolePolicyListView,
    OrganizationPermissionCeilingDetailView,
    OrganizationPermissionCeilingListView,
    PlatformSupportOperatorDetailView,
    PlatformSupportOperatorListView,
    TenantAccessCatalogView,
    TenantAdminMembershipListView,
    TenantAdminMembershipRoleView,
    TenantRoleDetailView,
    TenantRoleListView,
    TenantRoleRetireView,
)

urlpatterns = [
    # Platform Owner Endpoints (Stage 4 & Support Governance)
    path(
        "owner/support-operators/",
        PlatformSupportOperatorListView.as_view(),
        name="platform-support-operator-list",
    ),
    path(
        "owner/support-operators/<uuid:pk>/",
        PlatformSupportOperatorDetailView.as_view(),
        name="platform-support-operator-detail",
    ),
    path(
        "owner/support-operators/<uuid:user_id>/<str:role_code>/",
        PlatformSupportOperatorDetailView.as_view(),
        name="platform-support-operator-role-detail",
    ),
    path(
        "organizations/<uuid:organization_id>/console-policies/",
        OrganizationConsolePolicyListView.as_view(),
        name="organization-console-policy-list",
    ),

    path(
        "organizations/<uuid:organization_id>/console-policies/<str:module_key>/",
        OrganizationConsolePolicyDetailView.as_view(),
        name="organization-console-policy-detail",
    ),
    path(
        "organizations/<uuid:organization_id>/permission-ceilings/",
        OrganizationPermissionCeilingListView.as_view(),
        name="organization-permission-ceiling-list",
    ),
    path(
        "organizations/<uuid:organization_id>/permission-ceilings/<str:permission_key>/",
        OrganizationPermissionCeilingDetailView.as_view(),
        name="organization-permission-ceiling-detail",
    ),
    # Tenant Admin Endpoints (Stage 5)
    path(
        "tenant/access-catalog/",
        TenantAccessCatalogView.as_view(),
        name="tenant-access-catalog",
    ),
    path(
        "tenant/roles/",
        TenantRoleListView.as_view(),
        name="tenant-role-list",
    ),
    path(
        "tenant/roles/<uuid:role_id>/",
        TenantRoleDetailView.as_view(),
        name="tenant-role-detail",
    ),
    path(
        "tenant/roles/<uuid:role_id>/retire/",
        TenantRoleRetireView.as_view(),
        name="tenant-role-retire",
    ),
    path(
        "tenant/admin-memberships/",
        TenantAdminMembershipListView.as_view(),
        name="tenant-admin-membership-list",
    ),
    path(
        "tenant/admin-memberships/<uuid:membership_id>/role/",
        TenantAdminMembershipRoleView.as_view(),
        name="tenant-admin-membership-role",
    ),
]
