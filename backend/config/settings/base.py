"""VibeConnect Base Settings.

Common settings shared across all environments.
"""

import os
import re
from pathlib import Path
import dj_database_url
from django.core.exceptions import ImproperlyConfigured

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent.parent


def get_env_bool(var_name: str) -> bool:
    val = os.environ.get(var_name)
    if val is None or val.strip() == "":
        raise ImproperlyConfigured(f"Environment variable '{var_name}' is mandatory and missing.")
    normalized = val.strip().lower()
    if normalized in ("true", "1"):
        return True
    if normalized in ("false", "0"):
        return False
    raise ImproperlyConfigured(f"Invalid boolean format for '{var_name}': '{val}'. Allowed: True, False, 1, 0.")


def get_env_pos_int(var_name: str) -> int:
    val = os.environ.get(var_name)
    if val is None or val.strip() == "":
        raise ImproperlyConfigured(f"Environment variable '{var_name}' is mandatory and missing.")
    try:
        parsed = int(val.strip())
        if parsed <= 0:
            raise ValueError()
        return parsed
    except ValueError:
        raise ImproperlyConfigured(f"Invalid positive integer for '{var_name}': '{val}'. Must be > 0.")


def get_env_str(var_name: str) -> str:
    val = os.environ.get(var_name)
    if not val or not val.strip():
        raise ImproperlyConfigured(f"Environment variable '{var_name}' is mandatory and missing.")
    return val.strip()


def get_env_samesite(var_name: str) -> str:
    val = get_env_str(var_name)
    if val not in ("Lax", "Strict", "None"):
        raise ImproperlyConfigured(f"Invalid SameSite value for '{var_name}': '{val}'. Allowed: Lax, Strict, None.")
    return val


def get_env_throttle_rate(var_name: str) -> str:
    val = get_env_str(var_name)
    match = re.match(r"^(\d+)/(second|minute|hour|day)$", val)
    if not match or int(match.group(1)) <= 0:
        raise ImproperlyConfigured(f"Invalid throttle rate for '{var_name}': '{val}'. Must be non-zero positive rate (e.g. 5/minute).")
    return val


# Application definition
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third-party apps
    "rest_framework",
    "corsheaders",
    "drf_spectacular",
    # Domain Applications
    "apps.identity.apps.IdentityConfig",
    "apps.organizations.apps.OrganizationsConfig",
    "apps.product_registry.apps.ProductRegistryConfig",
    "apps.entitlements.apps.EntitlementsConfig",
    "apps.branding.apps.BrandingConfig",
    "apps.auditlog.apps.AuditlogConfig",
    "apps.plans.apps.PlansConfig",
    "apps.subscriptions.apps.SubscriptionsConfig",
    "apps.access_control.apps.AccessControlConfig",
    "apps.assignments.apps.AssignmentsConfig",
    "apps.notifications.apps.NotificationsConfig",
    "apps.onboarding.apps.OnboardingConfig",
    "apps.invitations.apps.InvitationsConfig",
    "apps.bulk_import.apps.BulkImportConfig",
    "apps.access_requests.apps.AccessRequestsConfig",
    "apps.showcase.apps.ShowcaseConfig",
    "apps.usage_metering.apps.UsageMeteringConfig",
    "apps.billing.apps.BillingConfig",
    "apps.reports.apps.ReportsConfig",
    "apps.integration_hub.apps.IntegrationHubConfig",
    "apps.marketplace.apps.MarketplaceConfig",
    "apps.developer_console.apps.DeveloperConsoleConfig",

    # Common / Shared
    "common.apps.CommonConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "common.middleware.RequestCorrelationMiddleware",
    "common.middleware.ContentSecurityPolicyMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# Database Configuration
raw_database_url = os.environ.get("DATABASE_URL", "").strip()

if not raw_database_url:
    raise ImproperlyConfigured(
        "DATABASE_URL environment variable is mandatory and missing or empty. "
        "VibeConnect requires a valid PostgreSQL connection string. "
        "SQLite and other database backends are strictly forbidden."
    )

parsed_db_config = dj_database_url.parse(
    raw_database_url,
    engine="django.db.backends.postgresql",
    conn_max_age=0,
)

if not parsed_db_config:
    raise ImproperlyConfigured(
        "Failed to parse DATABASE_URL. Please provide a valid PostgreSQL connection URL."
    )

if parsed_db_config.get("ENGINE") != "django.db.backends.postgresql":
    raise ImproperlyConfigured(
        f"Invalid database engine: '{parsed_db_config.get('ENGINE')}'. "
        "Only 'django.db.backends.postgresql' is permitted for VibeConnect."
    )

DATABASES = {
    "default": parsed_db_config,
}

test_database_name = os.environ.get("TEST_DATABASE_NAME", "").strip()
if test_database_name:
    DATABASES["default"]["TEST"] = {"NAME": test_database_name}


# Custom User Model
AUTH_USER_MODEL = "identity.PlatformUser"

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

# Session and Cookie Configuration
SESSION_COOKIE_NAME = get_env_str("DJANGO_SESSION_COOKIE_NAME")
CSRF_COOKIE_NAME = get_env_str("DJANGO_CSRF_COOKIE_NAME")
SESSION_COOKIE_AGE = get_env_pos_int("DJANGO_SESSION_COOKIE_AGE")
SESSION_EXPIRE_AT_BROWSER_CLOSE = get_env_bool("DJANGO_SESSION_EXPIRE_AT_BROWSER_CLOSE")
SESSION_SAVE_EVERY_REQUEST = get_env_bool("DJANGO_SESSION_SAVE_EVERY_REQUEST")
SESSION_COOKIE_SAMESITE = get_env_samesite("DJANGO_SESSION_COOKIE_SAMESITE")
CSRF_COOKIE_SAMESITE = get_env_samesite("DJANGO_CSRF_COOKIE_SAMESITE")

SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = False
SESSION_COOKIE_PATH = "/"
CSRF_COOKIE_PATH = "/"

# Internationalization
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# Default primary key field type
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Django REST Framework configuration
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "apps.identity.authentication.EnforcedSessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "auth_login": get_env_throttle_rate("DJANGO_AUTH_LOGIN_THROTTLE_RATE"),
        "invitation_issue": get_env_throttle_rate("DJANGO_INVITATION_ISSUE_THROTTLE_RATE"),
        "invitation_validate": get_env_throttle_rate("DJANGO_INVITATION_VALIDATE_THROTTLE_RATE"),
        "invitation_accept": get_env_throttle_rate("DJANGO_INVITATION_ACCEPT_THROTTLE_RATE"),
        "developer_api": os.environ.get("DJANGO_DEVELOPER_API_RATE_LIMIT", "120/minute").strip(),
    },
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
    "DEFAULT_PARSER_CLASSES": [
        "rest_framework.parsers.JSONParser",
    ],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
}

# OpenAPI / Developer API Documentation (Phase 6B-5)
SPECTACULAR_SETTINGS = {
    "TITLE": "VibeConnect Developer API",
    "DESCRIPTION": (
        "Official programmatic integration layer for VibeConnect.\n\n"
        "### Authentication\n"
        "Authenticate all requests using a Bearer API key in the Authorization header:\n\n"
        "`Authorization: Bearer vck_live_<prefix>_<secret>`\n\n"
        "### Scopes\n"
        "- `catalog:read`: Read-only access to published products, modules, capabilities, and active public plans.\n"
        "- `organization:read`: Read-only access to organization profile.\n"
        "- `entitlements:read`: Read-only access to granted product entitlements.\n"
        "- `assignments:read`: Read-only access to user product assignments.\n\n"
        "### Rate Limiting\n"
        "Developer API requests are throttled per API key (default: 120 requests/minute).\n"
        "The following headers are returned on all responses:\n"
        "- `X-RateLimit-Limit`: Maximum requests allowed per window.\n"
        "- `X-RateLimit-Remaining`: Remaining requests in current window.\n"
        "- `X-RateLimit-Reset`: Seconds until quota window resets.\n"
        "- `Retry-After`: Returned on HTTP 429 when rate limit is exceeded.\n\n"
        "### Tenant Isolation\n"
        "All requests are bound strictly to the organization associated with the API key.\n"
        "Cross-tenant access is forbidden (HTTP 403 TENANT_MISMATCH)."
    ),
    "VERSION": "v1",
    "SERVE_INCLUDE_SCHEMA": False,
    "PREPROCESSING_HOOKS": [
        "apps.developer_console.openapi.developer_endpoints_filter",
    ],
    "APPEND_COMPONENTS": {
        "securitySchemes": {
            "DeveloperApiKeyAuth": {
                "type": "http",
                "scheme": "bearer",
                "bearerFormat": "vck_live_<prefix>_<secret>",
                "description": "Provide your full API key as a Bearer token: Authorization: Bearer vck_live_<prefix>_<secret>",
            }
        }
    },
    "SECURITY": [
        {"DeveloperApiKeyAuth": []}
    ],
}

# M2M Service-to-Service Configuration for Integration (Phase 5C, Trinity Workshop, FieldSense)
VIBECONNECT_LMS_M2M_SECRET = os.environ.get("VIBECONNECT_LMS_M2M_SECRET", "").strip()
VIBECONNECT_LMS_BACKEND_URL = os.environ.get("VIBECONNECT_LMS_BACKEND_URL", "").strip()
VIBECONNECT_TRINITY_M2M_SECRET = os.environ.get("VIBECONNECT_TRINITY_M2M_SECRET", "").strip()
VIBECONNECT_TRINITY_CALLBACK_URI = os.environ.get("VIBECONNECT_TRINITY_CALLBACK_URI", "").strip()
VIBECONNECT_FIELDSENSE_M2M_SECRET = os.environ.get("VIBECONNECT_FIELDSENSE_M2M_SECRET", "").strip()
VIBECONNECT_FIELDSENSE_CALLBACK_URI = os.environ.get("VIBECONNECT_FIELDSENSE_CALLBACK_URI", "").strip()
VIBECONNECT_M2M_SECRET = os.environ.get("VIBECONNECT_M2M_SECRET", "").strip()

# HRMS Sandbox Integration (Phase 3)
VIBECONNECT_HRMS_BACKEND_URL = os.environ.get("VIBECONNECT_HRMS_BACKEND_URL", "").strip()
VIBECONNECT_HRMS_USERNAME = os.environ.get("VIBECONNECT_HRMS_USERNAME", "").strip()
VIBECONNECT_HRMS_PASSWORD = os.environ.get("VIBECONNECT_HRMS_PASSWORD", "").strip()

# Observability & Structured Application Logging (Phase 7D)
DJANGO_LOG_LEVEL = os.environ.get("DJANGO_LOG_LEVEL", "INFO").strip().upper()
DJANGO_LOG_FORMAT = os.environ.get("DJANGO_LOG_FORMAT", "json").strip().lower()

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {
            "()": "common.logging.StructuredJsonFormatter",
        },
        "console": {
            "format": "%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "json" if DJANGO_LOG_FORMAT == "json" else "console",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": DJANGO_LOG_LEVEL,
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "django.request": {
            "handlers": ["console"],
            "level": "ERROR",
            "propagate": False,
        },
        "apps": {
            "handlers": ["console"],
            "level": DJANGO_LOG_LEVEL,
            "propagate": False,
        },
        "common": {
            "handlers": ["console"],
            "level": DJANGO_LOG_LEVEL,
            "propagate": False,
        },
    },
}

