from django.urls import path

from apps.reports.analytics_views import OwnerAnalyticsView, TenantAnalyticsView
from apps.reports.views import OwnerReportsSummaryView, TenantReportsSummaryView

urlpatterns = [
    path("reports/summary/", OwnerReportsSummaryView.as_view(), name="owner-reports-summary"),
    path("tenant/reports/", TenantReportsSummaryView.as_view(), name="tenant-reports-summary"),
    path("owner/analytics/", OwnerAnalyticsView.as_view(), name="owner-analytics"),
    path("tenant/analytics/", TenantAnalyticsView.as_view(), name="tenant-analytics"),
]
