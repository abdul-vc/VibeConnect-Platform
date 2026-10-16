import secrets
from django.contrib.auth.models import AnonymousUser
from django.utils import timezone
from rest_framework import authentication, exceptions

from apps.developer_console.models import DeveloperApiKey
from apps.developer_console.services.key_service import hash_key, parse_key_prefix
from apps.organizations.models import OrganizationStatus


class ApiKeyAuthentication(authentication.BaseAuthentication):
    """Authenticates machine requests via Bearer API keys (vck_live_<8-hex>_<43-url-safe-secret>)."""

    keyword = "Bearer"

    def authenticate_header(self, request):
        return f'{self.keyword} realm="developer_api"'

    def authenticate(self, request):
        auth_header = authentication.get_authorization_header(request).decode("utf-8")
        if not auth_header:
            return None

        parts = auth_header.split()
        if len(parts) != 2 or parts[0].lower() != self.keyword.lower():
            return None

        raw_key = parts[1].strip()
        if not raw_key.startswith("vck_live_"):
            return None

        prefix = parse_key_prefix(raw_key)
        if not prefix:
            raise exceptions.AuthenticationFailed(
                {"error": "INVALID_API_KEY", "detail": "API key format is invalid."}
            )

        api_key = (
            DeveloperApiKey.objects.select_related("application", "application__organization")
            .filter(key_prefix=prefix)
            .first()
        )
        if not api_key:
            raise exceptions.AuthenticationFailed(
                {"error": "INVALID_API_KEY", "detail": "Invalid API key."}
            )

        # Constant-time comparison of hashed secret
        provided_hash = hash_key(raw_key)
        if not secrets.compare_digest(provided_hash, api_key.hashed_secret):
            raise exceptions.AuthenticationFailed(
                {"error": "INVALID_API_KEY", "detail": "Invalid API key."}
            )

        now = timezone.now()

        # Validate Key Status & Expiration
        if api_key.status == "revoked":
            raise exceptions.AuthenticationFailed(
                {"error": "KEY_REVOKED", "detail": "API key has been revoked."}
            )

        if api_key.status == "expired" or (api_key.expires_at and api_key.expires_at < now):
            if api_key.status != "expired":
                DeveloperApiKey.objects.filter(pk=api_key.pk).update(status="expired")
            raise exceptions.AuthenticationFailed(
                {"error": "KEY_EXPIRED", "detail": "API key has expired."}
            )

        if api_key.status != "active":
            raise exceptions.AuthenticationFailed(
                {"error": "INVALID_API_KEY", "detail": "API key is not active."}
            )

        # Validate Application Lifecycle
        app = api_key.application
        if app.status == "suspended":
            raise exceptions.AuthenticationFailed(
                {"error": "APPLICATION_SUSPENDED", "detail": "Developer application is suspended."}
            )
        if app.status == "revoked":
            raise exceptions.AuthenticationFailed(
                {"error": "APPLICATION_REVOKED", "detail": "Developer application has been revoked."}
            )
        if app.status != "active":
            raise exceptions.AuthenticationFailed(
                {"error": "APPLICATION_INACTIVE", "detail": "Developer application is not active."}
            )

        # Validate Tenant Organization Lifecycle
        org = app.organization
        if org.status != OrganizationStatus.ACTIVE:
            raise exceptions.AuthenticationFailed(
                {"error": "TENANT_INACTIVE", "detail": "Tenant organization is not active."}
            )

        # Server-enforced trusted tenant binding
        request.tenant = org
        request.developer_application = app
        request.developer_api_key = api_key

        # Throttled update of last_used_at (maximum once per 60 seconds)
        if not api_key.last_used_at or (now - api_key.last_used_at).total_seconds() >= 60:
            DeveloperApiKey.objects.filter(pk=api_key.pk).update(last_used_at=now)

        return (AnonymousUser(), api_key)
