"""VibeConnect Root URL Configuration.

Versioned API foundation under /api/v1/.
"""

from django.contrib import admin
from django.urls import include, path

from apps.developer_console.management_urls import owner_urlpatterns, tenant_urlpatterns

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/", include("common.urls")),
    path("api/v1/auth/", include("apps.identity.urls")),
    path("api/v1/products/", include("apps.product_registry.urls")),
    path("api/v1/", include("apps.product_registry.catalog_urls")),
    path("api/v1/", include("apps.access_control.urls")),
    path("api/v1/organizations/", include("apps.organizations.urls")),
    path("api/v1/organization-product-entitlements/", include("apps.entitlements.urls")),
    path("api/v1/audit-logs/", include("apps.auditlog.urls")),
    path("api/v1/", include("apps.plans.urls")),
    path("api/v1/users/", include("apps.identity.user_urls")),
    path("api/v1/subscriptions/", include("apps.subscriptions.urls")),
    path("api/v1/", include("apps.assignments.urls")),
    path("api/v1/", include("apps.organizations.tenant_urls")),
    path("api/v1/onboarding/", include("apps.onboarding.urls")),
    path("api/v1/invitations/", include("apps.invitations.urls")),
    path("api/v1/bulk-import/", include("apps.bulk_import.urls")),
    path("api/v1/access-requests/", include("apps.access_requests.urls")),
    path("api/v1/notifications/", include("apps.notifications.urls")),
    path("api/v1/showcase/", include("apps.showcase.urls")),
    path("api/v1/", include("apps.branding.urls")),
    path("api/v1/", include("apps.usage_metering.urls")),
    path("api/v1/", include("apps.billing.urls")),
    path("api/v1/", include("apps.reports.urls")),
    path("api/v1/integration/", include("apps.integration_hub.urls")),
    path("api/v1/sso/", include("apps.integration_hub.sso_urls")),
    path("api/v1/", include("apps.marketplace.urls")),
    path("api/v1/developer/", include("apps.developer_console.urls")),
    path("api/v1/tenant/developer/", include((tenant_urlpatterns, "tenant_developer"))),
    path("api/v1/owner/developer/", include((owner_urlpatterns, "owner_developer"))),
    path("api/v1/support/", include("apps.integration_hub.support_urls")),
]

