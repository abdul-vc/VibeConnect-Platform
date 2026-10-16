"""Support Console URL Configuration (Phase 6C)."""

from django.urls import path

from apps.identity import support_impersonation_views
from apps.integration_hub import support_views


urlpatterns = [
    path("organizations/", support_views.SupportOrganizationLookupView.as_view(), name="support-organization-lookup"),
    path("organizations/<uuid:organization_id>/diagnostics/", support_views.OrganizationDiagnosticsView.as_view(), name="support-organization-diagnostics"),
    path("organizations/<uuid:organization_id>/failures/<uuid:failure_id>/retry/", support_views.SupportFailureRetryView.as_view(), name="support-failure-retry"),
    path("organizations/<uuid:organization_id>/failures/<uuid:failure_id>/replay/", support_views.SupportFailureReplayView.as_view(), name="support-failure-replay"),
    path("organizations/<uuid:organization_id>/failures/<uuid:failure_id>/resolve/", support_views.SupportFailureResolveView.as_view(), name="support-failure-resolve"),
    path("organizations/<uuid:organization_id>/reconciliation/<uuid:issue_id>/resolve/", support_views.SupportReconciliationResolveView.as_view(), name="support-reconciliation-resolve"),
    # Phase 6D: Audited Support Impersonation Endpoints
    path("impersonation/eligible-targets/", support_impersonation_views.EligibleTargetsView.as_view(), name="support-impersonation-targets"),
    path("impersonation/sessions/", support_impersonation_views.ImpersonationSessionCreateView.as_view(), name="support-impersonation-create"),
    path("impersonation/sessions/active/", support_impersonation_views.ActiveImpersonationSessionView.as_view(), name="support-impersonation-active"),
    path("impersonation/sessions/<uuid:pk>/terminate/", support_impersonation_views.ImpersonationSessionTerminateView.as_view(), name="support-impersonation-terminate"),
]


