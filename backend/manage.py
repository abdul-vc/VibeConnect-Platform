#!/usr/bin/env python
import os
import sys
from pathlib import Path


def main():
    # Load .env.local for local CLI development if present
    base_dir = Path(__file__).resolve().parent
    env_local = base_dir / ".env.local"
    if env_local.exists():
        try:
            from dotenv import load_dotenv

            load_dotenv(env_local, override=True)
        except ImportError:
            pass

    settings_module = os.environ.get("DJANGO_SETTINGS_MODULE")
    if not settings_module:
        sys.stderr.write(
            "Configuration Error: DJANGO_SETTINGS_MODULE environment variable is not set. "
            "Please set DJANGO_SETTINGS_MODULE in your environment or backend/.env.local.\n"
        )
        sys.exit(1)

    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
