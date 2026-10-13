"""WSGI config for VibeConnect platform.

Consumes real operating system environment variables in production.
"""

import os
from django.core.wsgi import get_wsgi_application

settings_module = os.environ.get("DJANGO_SETTINGS_MODULE")
if not settings_module:
    raise RuntimeError(
        "DJANGO_SETTINGS_MODULE environment variable must be set in the system environment."
    )

os.environ.setdefault("DJANGO_SETTINGS_MODULE", settings_module)

application = get_wsgi_application()
