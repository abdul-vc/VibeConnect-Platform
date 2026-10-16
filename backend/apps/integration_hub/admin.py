"""Django Admin configuration for Integration Hub models."""

from django.contrib import admin

from apps.integration_hub.models import (
    ConnectorInstance,
    IntegrationConnector,
    ProductSsoClient,
    SsoAuthorizationCode,
)


@admin.register(ProductSsoClient)
class ProductSsoClientAdmin(admin.ModelAdmin):
    list_display = (
        "client_identifier",
        "product",
        "audience",
        "callback_uri",
        "is_active",
        "created_at",
    )
    list_filter = ("is_active", "product")
    search_fields = ("client_identifier", "audience", "callback_uri")
    readonly_fields = ("id", "created_at", "updated_at")


@admin.register(IntegrationConnector)
class IntegrationConnectorAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "product", "version", "status", "created_at")
    list_filter = ("status", "product")
    search_fields = ("code", "name")
    readonly_fields = ("id", "created_at", "updated_at")


@admin.register(ConnectorInstance)
class ConnectorInstanceAdmin(admin.ModelAdmin):
    list_display = ("label", "connector", "organization", "status", "created_at")
    list_filter = ("status", "connector")
    search_fields = ("label", "organization__name", "organization__code")
    readonly_fields = ("id", "created_at", "updated_at")


@admin.register(SsoAuthorizationCode)
class SsoAuthorizationCodeAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "organization",
        "product",
        "sso_client",
        "expires_at",
        "used_at",
        "created_at",
    )
    list_filter = ("product", "organization", "used_at")
    search_fields = ("user__email", "code_hash")
    readonly_fields = (
        "id",
        "user",
        "organization",
        "product",
        "assignment",
        "sso_client",
        "code_hash",
        "code_challenge",
        "code_challenge_method",
        "state",
        "expires_at",
        "used_at",
        "created_at",
    )
