"""Integration Hub URL Configuration (Phase 5A + 5B)."""

from django.urls import path

from apps.integration_hub import reconciliation_views, views

urlpatterns = [
    # 5A: Connector registry
    path("connectors/", views.ConnectorListView.as_view(), name="integration-connector-list"),
    path("connectors/<str:pk>/", views.ConnectorDetailView.as_view(), name="integration-connector-detail"),
    # 5A: Connector instances
    path("instances/", views.InstanceListView.as_view(), name="integration-instance-list"),
    path("instances/<str:pk>/", views.InstanceDetailView.as_view(), name="integration-instance-detail"),
    # 5A: Event ingestion (idempotent)
    path("events/ingest/", views.EventIngestView.as_view(), name="integration-event-ingest"),
    path("events/", views.EventListView.as_view(), name="integration-event-list"),
    # 5A: Provisioning jobs
    path("provisioning-jobs/", views.ProvisioningJobListView.as_view(), name="integration-provisioning-job-list"),
    path("provisioning-jobs/<str:pk>/", views.ProvisioningJobDetailView.as_view(), name="integration-provisioning-job-detail"),
    # 5B: External identity mappings
    path("external-identities/", views.ExternalIdentityListView.as_view(), name="integration-external-identity-list"),
    path("tenant-mappings/", views.ExternalTenantMappingListView.as_view(), name="integration-tenant-mapping-list"),
    path("user-mappings/", views.ExternalUserMappingListView.as_view(), name="integration-user-mapping-list"),
    # 5D: LMS Reconciliation
    path("reconciliation/", reconciliation_views.LmsReconciliationListView.as_view(), name="integration-reconciliation-list"),
    path("reconciliation/run/", reconciliation_views.LmsReconciliationTriggerView.as_view(), name="integration-reconciliation-run"),
    path("reconciliation/<uuid:issue_id>/resolve/", reconciliation_views.LmsReconciliationResolveView.as_view(), name="integration-reconciliation-resolve"),
    # 5G: Health & Failure Management
    path("health/", views.IntegrationHealthSummaryView.as_view(), name="integration-health-summary"),
    path("failures/", views.FailureListView.as_view(), name="integration-failure-list"),
    path("failures/<uuid:pk>/", views.FailureDetailView.as_view(), name="integration-failure-detail"),
    path("failures/<uuid:pk>/resolve/", views.FailureResolveView.as_view(), name="integration-failure-resolve"),
    path("failures/<uuid:pk>/mark-dead-letter/", views.FailureDeadLetterView.as_view(), name="integration-failure-mark-dead-letter"),
    path("failures/<uuid:pk>/schedule-retry/", views.FailureScheduleRetryView.as_view(), name="integration-failure-schedule-retry"),
    path("failures/<uuid:pk>/replay/", views.FailureReplayView.as_view(), name="integration-failure-replay"),
]
