"""URL routing for Tenant Home / App Launcher aggregation endpoints."""

from django.urls import path

from apps.organizations.tenant_home_views import TenantHomeView

urlpatterns = [
    path("tenant/home/", TenantHomeView.as_view(), name="tenant-home"),
]
