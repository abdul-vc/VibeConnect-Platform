"""Idempotent setup command for WorkHub Product Showcase integration.

Registers and ensures the required Showcase metadata for WorkHub:
1. Reuses existing Product: code='workhub', name='WorkHub'
2. Reuses existing Showcase Profile: published status
3. Demo Environment: pointing to configured WORKHUB_SHOWCASE_FRONTEND_URL (http://localhost:6395)
4. Launch Configuration: bound to DEMO_ONLY mode targeting /admin

CRITICAL SCOPE RULE:
- Does NOT touch LMS, Quiz, Sales Tracker, or Divine Connect products, showcase profiles, connectors, or instances.
- Never hardcodes secrets or passwords.
"""

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.product_registry.models import Product, ProductStatus
from apps.showcase.models import (
    ProductDemoEnvironment,
    ProductLaunchConfig,
    ProductShowcaseProfile,
    ShowcaseVisibility,
)

User = get_user_model()


class Command(BaseCommand):
    help = "Idempotently configure WorkHub for Product Showcase."

    def handle(self, *args, **options):
        self.stdout.write("Configuring WorkHub for Product Showcase...")

        system_user = (
            User.objects.filter(is_superuser=True).first()
            or User.objects.filter(is_staff=True).first()
            or User.objects.first()
        )
        if not system_user:
            self.stderr.write(self.style.ERROR("No user found in database to attribute showcase configuration."))
            return

        frontend_url = getattr(settings, "WORKHUB_SHOWCASE_FRONTEND_URL", "http://localhost:6395") or "http://localhost:6395"

        with transaction.atomic():
            # 1. Product Registry
            product, p_created = Product.objects.get_or_create(
                code="workhub",
                defaults={
                    "name": "WorkHub",
                    "description": "Enterprise productivity, collaboration, and task hub.",
                    "status": ProductStatus.ACTIVE,
                    "created_by": system_user,
                    "updated_by": system_user,
                },
            )
            if not p_created and product.status != ProductStatus.ACTIVE:
                product.status = ProductStatus.ACTIVE
                product.save(update_fields=["status"])

            self.stdout.write(
                f"Product {'created' if p_created else 'verified'}: {product.name} [{product.code}] ({product.id})"
            )

            # 2. Product Showcase Profile
            profile, pr_created = ProductShowcaseProfile.objects.get_or_create(
                product=product,
                defaults={
                    "tagline": "Enterprise productivity, collaboration, and task management with Admin console",
                    "overview": "Unified enterprise workspace for team collaboration, task routing, workflow tracking, and departmental productivity.",
                    "visibility": ShowcaseVisibility.PUBLISHED,
                    "display_order": 4,
                    "created_by": system_user,
                    "updated_by": system_user,
                },
            )
            if not pr_created and profile.visibility != ShowcaseVisibility.PUBLISHED:
                profile.visibility = ShowcaseVisibility.PUBLISHED
                profile.save(update_fields=["visibility"])

            self.stdout.write(
                f"Showcase Profile {'created' if pr_created else 'verified'}: {profile.id} ({profile.visibility})"
            )

            # 3. Product Demo Environment
            demo_env, env_created = ProductDemoEnvironment.objects.get_or_create(
                product=product,
                name="WorkHub Live",
                defaults={
                    "base_url": frontend_url,
                    "description": "WorkHub Administrator Interactive Showcase Environment",
                    "is_active": True,
                    "created_by": system_user,
                    "updated_by": system_user,
                },
            )
            if not env_created and (demo_env.base_url != frontend_url or not demo_env.is_active):
                demo_env.base_url = frontend_url
                demo_env.is_active = True
                demo_env.save(update_fields=["base_url", "is_active"])

            self.stdout.write(
                f"Demo Environment {'created' if env_created else 'verified'}: {demo_env.name} ({demo_env.base_url})"
            )

            # 4. Product Launch Configuration
            launch_config, lc_created = ProductLaunchConfig.objects.get_or_create(
                profile=profile,
                defaults={
                    "product": product,
                    "launch_mode": ProductLaunchConfig.LaunchMode.DEMO_ONLY,
                    "allowed_targets": ["/admin"],
                    "target_environment": demo_env,
                    "created_by": system_user,
                    "updated_by": system_user,
                },
            )
            if not lc_created and (
                launch_config.target_environment != demo_env
                or launch_config.launch_mode != ProductLaunchConfig.LaunchMode.DEMO_ONLY
            ):
                launch_config.target_environment = demo_env
                launch_config.launch_mode = ProductLaunchConfig.LaunchMode.DEMO_ONLY
                launch_config.save(update_fields=["target_environment", "launch_mode"])

            self.stdout.write(
                f"Launch Config {'created' if lc_created else 'verified'}: {launch_config.id} [{launch_config.launch_mode}]"
            )

        self.stdout.write(self.style.SUCCESS("WorkHub Product Showcase setup completed successfully."))
