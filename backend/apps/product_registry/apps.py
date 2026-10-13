"""Product Registry application configuration."""

from django.apps import AppConfig


class ProductRegistryConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.product_registry"
    label = "product_registry"
    verbose_name = "Product Registry"
