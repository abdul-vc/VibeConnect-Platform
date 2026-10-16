from drf_spectacular.extensions import OpenApiAuthenticationExtension


class ApiKeyAuthenticationScheme(OpenApiAuthenticationExtension):
    target_class = "apps.developer_console.authentication.ApiKeyAuthentication"
    name = "DeveloperApiKeyAuth"

    def get_security_definition(self, auto_schema):
        return {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "vck_live_<prefix>_<secret>",
            "description": "Provide your full API key as a Bearer token: Authorization: Bearer vck_live_<prefix>_<secret>",
        }


def developer_endpoints_filter(endpoints):
    """
    Ensure the OpenAPI schema contains ONLY the frozen /api/v1/developer/ endpoints.
    Explicitly excludes /auth/, /tenant/, /owner/, /marketplace/, /integration/,
    billing, audit, access-control, and the documentation/schema endpoints themselves.
    """
    allowed_developer_paths = {
        "/api/v1/developer/catalog/products/",
        "/api/v1/developer/organization/",
        "/api/v1/developer/entitlements/",
        "/api/v1/developer/assignments/",
    }
    filtered = []
    for path, path_regex, method, callback in endpoints:
        if path in allowed_developer_paths:
            filtered.append((path, path_regex, method, callback))
    return filtered
