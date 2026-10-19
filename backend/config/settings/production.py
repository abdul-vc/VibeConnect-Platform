"""VibeConnect Production Settings.

Enforces production-grade security, HTTPS, strict cookie protection, and strict environment validation.
"""

import os
from django.core.exceptions import ImproperlyConfigured
from .base import *

secret_key = os.environ.get("DJANGO_SECRET_KEY")
if not secret_key:
    raise ImproperlyConfigured(
        "DJANGO_SECRET_KEY environment variable is mandatory in production."
    )
SECRET_KEY = secret_key

# Debug is strictly disabled in production
DEBUG = False

raw_allowed_hosts = os.environ.get("DJANGO_ALLOWED_HOSTS")
if not raw_allowed_hosts or not raw_allowed_hosts.strip():
    raise ImproperlyConfigured(
        "DJANGO_ALLOWED_HOSTS environment variable is mandatory in production."
    )
ALLOWED_HOSTS = [host.strip() for host in raw_allowed_hosts.split(",") if host.strip()]

# Cookie Security Flags (Environment-driven, must be True in production)
SESSION_COOKIE_SECURE = get_env_bool("DJANGO_SESSION_COOKIE_SECURE")
CSRF_COOKIE_SECURE = get_env_bool("DJANGO_CSRF_COOKIE_SECURE")

if not SESSION_COOKIE_SECURE or not CSRF_COOKIE_SECURE:
    raise ImproperlyConfigured(
        "Production settings require DJANGO_SESSION_COOKIE_SECURE=True and DJANGO_CSRF_COOKIE_SECURE=True."
    )

# CORS Configuration from environment only - no wildcards
raw_cors = os.environ.get("CORS_ALLOWED_ORIGINS", "").strip()
if raw_cors:
    CORS_ALLOWED_ORIGINS = [origin.strip() for origin in raw_cors.split(",") if origin.strip()]
else:
    CORS_ALLOWED_ORIGINS = []

CORS_ALLOW_ALL_ORIGINS = False
CORS_ALLOW_CREDENTIALS = True

# CSRF Trusted Origins from environment only
raw_csrf = os.environ.get("CSRF_TRUSTED_ORIGINS", "").strip()
if raw_csrf:
    CSRF_TRUSTED_ORIGINS = [origin.strip() for origin in raw_csrf.split(",") if origin.strip()]
else:
    CSRF_TRUSTED_ORIGINS = []

# Production Security Headers & Cookie Policies
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
SECURE_REFERRER_POLICY = "same-origin"
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# Phase 3A: Email & Frontend Configuration for Production
if not FRONTEND_BASE_URL:
    raise ImproperlyConfigured("FRONTEND_BASE_URL environment variable is mandatory in production.")

if not FRONTEND_BASE_URL.startswith("https://"):
    raise ImproperlyConfigured("FRONTEND_BASE_URL must use HTTPS in production.")

if not os.environ.get("DJANGO_EMAIL_BACKEND"):
    raise ImproperlyConfigured("DJANGO_EMAIL_BACKEND environment variable is mandatory in production.")

if EMAIL_BACKEND == "django.core.mail.backends.console.EmailBackend":
    raise ImproperlyConfigured("DJANGO_EMAIL_BACKEND cannot be console backend in production.")

if EMAIL_BACKEND == "django.core.mail.backends.smtp.EmailBackend":
    if not EMAIL_HOST:
        raise ImproperlyConfigured("DJANGO_EMAIL_HOST environment variable is mandatory when using SMTP in production.")
    if not EMAIL_PORT:
        raise ImproperlyConfigured("DJANGO_EMAIL_PORT environment variable is mandatory when using SMTP in production.")
