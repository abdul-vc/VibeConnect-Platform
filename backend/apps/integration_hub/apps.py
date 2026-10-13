"""Integration Hub Django Application Config."""

from django.apps import AppConfig


class IntegrationHubConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.integration_hub"
    label = "integration_hub"
    verbose_name = "Integration Hub"

    def ready(self) -> None:
        import apps.integration_hub.signals  # noqa: F401
