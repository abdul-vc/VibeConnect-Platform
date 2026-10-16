"""Audit Log application configuration."""

from django.apps import AppConfig


class AuditlogConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.auditlog"
    label = "auditlog"
    verbose_name = "Audit Log"
