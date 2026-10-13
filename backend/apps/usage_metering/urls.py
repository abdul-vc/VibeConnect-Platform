from django.urls import path

from apps.usage_metering.views import (
    OwnerUsageListView,
    TenantUsageSummaryView,
    UsageEventIngestionView,
)

urlpatterns = [
    path("usage/events/", UsageEventIngestionView.as_view(), name="usage-event-ingest"),
    path("tenant/usage/", TenantUsageSummaryView.as_view(), name="tenant-usage-summary"),
    path("usage/", OwnerUsageListView.as_view(), name="owner-usage-list"),
]
