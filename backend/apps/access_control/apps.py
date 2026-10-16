"""Access Control Application Configuration."""

from django.apps import AppConfig


class AccessControlConfig(AppConfig):
    """Configuration for the Access Control domain application."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.access_control"
    verbose_name = "Access Control"
