"""Audit Log URL Configuration.

Routes /api/v1/audit-logs/ to AuditLogViewSet.
"""

from django.urls import path
from rest_framework.routers import SimpleRouter
from apps.auditlog.views import AuditLogViewSet, TenantAuditLogListView

router = SimpleRouter()
router.register("", AuditLogViewSet, basename="audit-log")

urlpatterns = [
    path("tenant/", TenantAuditLogListView.as_view(), name="tenant-audit-log"),
] + router.urls
