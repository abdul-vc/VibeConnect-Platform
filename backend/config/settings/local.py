"""VibeConnect Local Development Settings.

Explicitly configured via environment variables. No fallback values or hardcoded secrets.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

backend_dir = Path(__file__).resolve().parent.parent.parent
env_file = backend_dir / ".env"
if env_file.exists():
    load_dotenv(env_file, override=True)

env_local_file = backend_dir / ".env.local"
if env_local_file.exists():
    load_dotenv(env_local_file, override=True)
from django.core.exceptions import ImproperlyConfigured
from .base import *

secret_key = os.environ.get("DJANGO_SECRET_KEY")
if not secret_key:
    raise ImproperlyConfigured(
        "DJANGO_SECRET_KEY environment variable is mandatory and missing."
    )
SECRET_KEY = secret_key

raw_debug = os.environ.get("DJANGO_DEBUG")
if raw_debug is None or raw_debug.strip() == "":
    raise ImproperlyConfigured(
        "DJANGO_DEBUG environment variable is mandatory and missing."
    )
DEBUG = raw_debug.strip().lower() in ("true", "1")

raw_allowed_hosts = os.environ.get("DJANGO_ALLOWED_HOSTS")
if raw_allowed_hosts is None or raw_allowed_hosts.strip() == "":
    raise ImproperlyConfigured(
        "DJANGO_ALLOWED_HOSTS environment variable is mandatory and missing."
    )
ALLOWED_HOSTS = [host.strip() for host in raw_allowed_hosts.split(",") if host.strip()]

# Cookie Security Flags (Environment-driven)
SESSION_COOKIE_SECURE = get_env_bool("DJANGO_SESSION_COOKIE_SECURE")
CSRF_COOKIE_SECURE = get_env_bool("DJANGO_CSRF_COOKIE_SECURE")

if SESSION_COOKIE_SAMESITE == "None" and not SESSION_COOKIE_SECURE:
    raise ImproperlyConfigured("SESSION_COOKIE_SAMESITE='None' requires DJANGO_SESSION_COOKIE_SECURE=True.")
if CSRF_COOKIE_SAMESITE == "None" and not CSRF_COOKIE_SECURE:
    raise ImproperlyConfigured("CSRF_COOKIE_SAMESITE='None' requires DJANGO_CSRF_COOKIE_SECURE=True.")

# CORS & CSRF Configuration from environment only - no wildcards
raw_cors = os.environ.get("CORS_ALLOWED_ORIGINS", "").strip()
if raw_cors:
    CORS_ALLOWED_ORIGINS = [origin.strip() for origin in raw_cors.split(",") if origin.strip()]
else:
    CORS_ALLOWED_ORIGINS = []

CORS_ALLOW_ALL_ORIGINS = False
CORS_ALLOW_CREDENTIALS = True

raw_csrf = os.environ.get("CSRF_TRUSTED_ORIGINS", "").strip()
if raw_csrf:
    CSRF_TRUSTED_ORIGINS = [origin.strip() for origin in raw_csrf.split(",") if origin.strip()]
else:
    CSRF_TRUSTED_ORIGINS = []
# Phase 3A: Email & Frontend Configuration for Local Development
if not FRONTEND_BASE_URL:
    FRONTEND_BASE_URL = os.environ.get("FRONTEND_BASE_URL", "http://localhost:6392").rstrip("/")
