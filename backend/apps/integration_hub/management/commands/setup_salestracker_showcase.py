"""Idempotent setup command for Sales Tracker Product Showcase integration.

Registers and ensures the required Showcase metadata for Sales Tracker CRM:
1. Product: code='crm', name='Customer Relationship Management'
2. Showcase Profile: published status with proper tagline and overview
3. Demo Environment: pointing to configured SALESTRACKER_SHOWCASE_FRONTEND_URL
4. Launch Configuration: bound to DEMO_ONLY mode targeting /dashboard

CRITICAL SCOPE RULE:
- Does NOT touch LMS or Quiz products, showcase profiles, connectors, or instances.
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
    help = "Idempotently configure Sales Tracker CRM for Product Showcase."

    def handle(self, *args, **options):
        self.stdout.write("Configuring Sales Tracker CRM for Product Showcase...")

        system_user = (
            User.objects.filter(is_superuser=True).first()
            or User.objects.filter(is_staff=True).first()
            or User.objects.first()
        )
        if not system_user:
            self.stderr.write(self.style.ERROR("No user found in database to attribute showcase configuration."))
            return

        frontend_url = getattr(settings, "SALESTRACKER_SHOWCASE_FRONTEND_URL", "http://localhost:5173") or "http://localhost:5173"

        with transaction.atomic():
            # 1. Product Registry
            product, p_created = Product.objects.get_or_create(
                code="crm",
                defaults={
                    "name": "Customer Relationship Management",
                    "description": "Envisage Lead & Sales Tracker CRM platform.",
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
                    "tagline": "Real-time Lead & Sales Tracking CRM with Super Administrator controls",
                    "overview": "Comprehensive CRM platform for tracking enterprise sales pipelines, deals, customer engagement, and performance metrics.",
                    "visibility": ShowcaseVisibility.PUBLISHED,
                    "display_order": 2,
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
                name="Sales Tracker CRM Live",
                defaults={
                    "base_url": frontend_url,
                    "description": "Sales Tracker CRM Super Administrator Interactive Showcase Environment",
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
            launch_cfg, cfg_created = ProductLaunchConfig.objects.get_or_create(
                product=product,
                defaults={
                    "profile": profile,
                    "launch_mode": ProductLaunchConfig.LaunchMode.DEMO_ONLY,
                    "target_environment": demo_env,
                    "allowed_targets": ["/dashboard"],
                    "policy": {
                        "demo_user_employee_id": getattr(settings, "SALESTRACKER_SHOWCASE_SUPERADMIN_EMPLOYEE_ID", "9930663966"),
                    },
                    "notes": "Dedicated Sales Tracker Superadmin Product Showcase SSO",
                    "created_by": system_user,
                    "updated_by": system_user,
                },
            )
            if not cfg_created:
                fields_to_update = []
                if launch_cfg.profile != profile:
                    launch_cfg.profile = profile
                    fields_to_update.append("profile")
                if launch_cfg.target_environment != demo_env:
                    launch_cfg.target_environment = demo_env
                    fields_to_update.append("target_environment")
                if launch_cfg.launch_mode != ProductLaunchConfig.LaunchMode.DEMO_ONLY:
                    launch_cfg.launch_mode = ProductLaunchConfig.LaunchMode.DEMO_ONLY
                    fields_to_update.append("launch_mode")
                if fields_to_update:
                    launch_cfg.save(update_fields=fields_to_update)

            self.stdout.write(
                f"Launch Config {'created' if cfg_created else 'verified'}: mode={launch_cfg.launch_mode}, target={demo_env.name}"
            )

        self.stdout.write(
            self.style.SUCCESS("Sales Tracker CRM Showcase setup completed successfully.")
        )
