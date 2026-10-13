"""URL routing for Bulk Import (Phase 3D)."""

from django.urls import path

from apps.bulk_import.views import (
    BulkImportJobCommitView,
    BulkImportJobCreateView,
    BulkImportJobDetailView,
    BulkImportJobErrorReportView,
    BulkImportJobReconciliationView,
    BulkImportJobRetryView,
    BulkImportJobRowsView,
)

urlpatterns = [
    path("jobs/", BulkImportJobCreateView.as_view(), name="bulk-import-job-create"),
    path("jobs/<uuid:pk>/", BulkImportJobDetailView.as_view(), name="bulk-import-job-detail"),
    path("jobs/<uuid:pk>/rows/", BulkImportJobRowsView.as_view(), name="bulk-import-job-rows"),
    path("jobs/<uuid:pk>/commit/", BulkImportJobCommitView.as_view(), name="bulk-import-job-commit"),
    path("jobs/<uuid:pk>/retry/", BulkImportJobRetryView.as_view(), name="bulk-import-job-retry"),
    path("jobs/<uuid:pk>/reconciliation/", BulkImportJobReconciliationView.as_view(), name="bulk-import-job-reconciliation"),
    path("jobs/<uuid:pk>/error-report/", BulkImportJobErrorReportView.as_view(), name="bulk-import-job-error-report"),
]
