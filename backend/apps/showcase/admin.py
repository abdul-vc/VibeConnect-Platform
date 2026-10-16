"""Showcase Admin – minimal registration."""
from django.contrib import admin
from apps.showcase.models import (
    ProductShowcaseProfile,
    ProductShowcaseMedia,
    ProductDemoEnvironment,
    ProductLaunchConfig,
)

admin.site.register(ProductShowcaseProfile)
admin.site.register(ProductShowcaseMedia)
admin.site.register(ProductDemoEnvironment)
admin.site.register(ProductLaunchConfig)
