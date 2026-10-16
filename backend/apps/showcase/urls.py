"""Showcase URL Patterns – Phase 11."""
from django.urls import path
from apps.showcase import hrms_views, views, vms_views

urlpatterns = [
    # Profile CRUD
    path("profiles/", views.ShowcaseProfileListView.as_view(), name="showcase-profiles-list"),
    path("profiles/<uuid:profile_id>/", views.ShowcaseProfileDetailView.as_view(), name="showcase-profiles-detail"),
    path("profiles/<uuid:profile_id>/publish/", views.ShowcasePublishView.as_view(), name="showcase-profiles-publish"),
    path("profiles/<uuid:profile_id>/unpublish/", views.ShowcaseUnpublishView.as_view(), name="showcase-profiles-unpublish"),
    path("profiles/<uuid:profile_id>/launchability/", views.ShowcaseLaunchabilityView.as_view(), name="showcase-profiles-launchability"),
    path("profiles/<uuid:profile_id>/launch-demo/", views.ShowcaseDemoLaunchView.as_view(), name="showcase-profiles-launch-demo"),
    path("profiles/<uuid:profile_id>/launch-config/", views.ShowcaseLaunchConfigView.as_view(), name="showcase-profiles-launch-config"),
    path("profiles/<uuid:profile_id>/media/", views.ShowcaseMediaView.as_view(), name="showcase-profiles-media"),
    path("media/<uuid:media_id>/", views.ShowcaseMediaDeleteView.as_view(), name="showcase-media-delete"),
    path("reorder/", views.ShowcaseReorderView.as_view(), name="showcase-profiles-reorder"),
    # Demo environments
    path("products/<uuid:product_id>/demo-environments/", views.DemoEnvironmentListView.as_view(), name="showcase-demo-env-list"),
    path("demo-environments/<uuid:env_id>/", views.DemoEnvironmentDetailView.as_view(), name="showcase-demo-env-detail"),
    # Presentation mode
    path("present/", views.ShowcasePresentationView.as_view(), name="showcase-present"),
    # HRMS Sandbox Integration Endpoints
    path("hrms/health/", hrms_views.HrmsHealthView.as_view(), name="showcase-hrms-health"),
    path("hrms/overview/", hrms_views.HrmsOverviewView.as_view(), name="showcase-hrms-overview"),
    path("hrms/employees/", hrms_views.HrmsEmployeesView.as_view(), name="showcase-hrms-employees"),
    path("hrms/attendance/", hrms_views.HrmsAttendanceView.as_view(), name="showcase-hrms-attendance"),
    path("hrms/attendance/history/", hrms_views.HrmsAttendanceHistoryView.as_view(), name="showcase-hrms-attendance-history"),
    path("hrms/departments/", hrms_views.HrmsDepartmentsView.as_view(), name="showcase-hrms-departments"),
    path("hrms/organization-structure/", hrms_views.HrmsOrganizationStructureView.as_view(), name="showcase-hrms-organization-structure"),
    path("hrms/leaves-summary/", hrms_views.HrmsLeavesSummaryView.as_view(), name="showcase-hrms-leaves-summary"),
    # VMS (WarehouseOS) Sandbox Integration Endpoints
    path("vms/health/", vms_views.VmsHealthView.as_view(), name="showcase-vms-health"),
    path("vms/overview/", vms_views.VmsOverviewView.as_view(), name="showcase-vms-overview"),
    path("vms/inventory/", vms_views.VmsInventoryView.as_view(), name="showcase-vms-inventory"),
    path("vms/docks/", vms_views.VmsDocksView.as_view(), name="showcase-vms-docks"),
    path("vms/waves/", vms_views.VmsWavesView.as_view(), name="showcase-vms-waves"),
    path("vms/vehicles/", vms_views.VmsVehiclesView.as_view(), name="showcase-vms-vehicles"),
    path("vms/reports/", vms_views.VmsReportsView.as_view(), name="showcase-vms-reports"),
]
