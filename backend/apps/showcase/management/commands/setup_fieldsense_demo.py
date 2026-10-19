"""Safe, idempotent management command to configure FieldSense Operations Hub Live Showcase SSO Demo.

Configures:
1. Canonical Product: reuses/migrates existing 'fieldsence' -> 'fieldsense' (or finds/creates 'fieldsense').
2. ProductShowcaseProfile: ensures published profile is linked to canonical product.
3. ProductDemoEnvironment: registers active 'FieldSense Operations Hub Local Demo' with base URL 'http://localhost:8081'.
4. SSO Client & Connector: delegates to register_fieldsense_sso_client for 'fieldsense-ops-hub' bound to 'demo-org'.
5. Tenant Access in 'demo-org':
   - Active OrganizationProductEntitlement for 'demo-org' and product.
   - Verifies active OrganizationMembership for 'admin@gmail.com'.
   - Active UserProductAssignment and UserModuleAssignment for 'admin@gmail.com'.
6. ProductLaunchConfig:
   - launch_mode: sso_direct
   - target_environment: demo_env
   - allowed_targets: ['http://localhost:8081']
   - policy: {'demo_organization_code': 'demo-org', 'demo_user_email': 'admin@gmail.com'}

Safety constraints:
- Strictly scoped to local demo context ('demo-org' and 'admin@gmail.com').
- Refuses conflicting overwrites without --update.
- Leaves Trinity Workshop, LMS, VMS, and other tenants/products untouched.
"""

from typing import Any
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.assignments.models import AssignmentStatus, UserModuleAssignment, UserProductAssignment
from apps.auditlog.models import (
    AuditAction,
    AuditOperationSource,
    AuditTargetType,
)
from apps.auditlog.services import record_audit_event
from apps.entitlements.models import EntitlementStatus, OrganizationProductEntitlement
from apps.integration_hub.models import ConnectorInstance, InstanceStatus, ProductSsoClient
from apps.organizations.models import MembershipStatus, Organization, OrganizationMembership
from apps.product_registry.models import CatalogStatus, Product, ProductModule, ProductStatus
from apps.showcase.models import (
    ProductDemoEnvironment,
    ProductLaunchConfig,
    ProductShowcaseProfile,
    ShowcaseVisibility,
)
from apps.showcase.services import AUTHORIZED_DEMO_ORGANIZATION_CODES

User = get_user_model()

CANONICAL_PRODUCT_CODE = "fieldsense"
LEGACY_PRODUCT_CODE = "fieldsence"
DEMO_ORG_CODE = "demo-org"
DEMO_USER_EMAIL = "admin@gmail.com"
DEMO_ENV_NAME = "FieldSense Operations Hub Local Demo"
DEFAULT_DEMO_URL = "http://localhost:8081"
DEFAULT_CALLBACK_URI = "http://localhost:8081/sso/callback"
CLIENT_IDENTIFIER = "fieldsense-ops-hub"
AUDIENCE = "fieldsense-ops-hub"


class Command(BaseCommand):
    help = "Idempotently configure FieldSense Operations Hub Live Showcase SSO Demo."

    def add_arguments(self, parser):
        parser.add_argument(
            "--base-url",
            default=DEFAULT_DEMO_URL,
            help=f"Base URL for FieldSense Local Demo (default: {DEFAULT_DEMO_URL}).",
        )
        parser.add_argument(
            "--callback-uri",
            default=DEFAULT_CALLBACK_URI,
            help=f"Callback URI for FieldSense SSO client (default: {DEFAULT_CALLBACK_URI}).",
        )
        parser.add_argument(
            "--organization",
            default=DEMO_ORG_CODE,
            help=f"Target allowlisted demo organization code (default: {DEMO_ORG_CODE}).",
        )
        parser.add_argument(
            "--user-email",
            default=DEMO_USER_EMAIL,
            help=f"Target demo user email in demo organization (default: {DEMO_USER_EMAIL}).",
        )
        parser.add_argument(
            "--update",
            action="store_true",
            help="Explicitly permit updating existing configuration fields if differing.",
        )

    def handle(self, *args: Any, **options: Any):
        base_url = options["base_url"].rstrip("/")
        callback_uri = options["callback_uri"].strip()
        org_code = options["organization"].strip()
        user_email = options["user_email"].strip()
        allow_update = options["update"]

        if org_code not in AUTHORIZED_DEMO_ORGANIZATION_CODES:
            raise CommandError(
                f"Organization '{org_code}' is not an authorized demo organization context. "
                f"Permitted contexts: {sorted(AUTHORIZED_DEMO_ORGANIZATION_CODES)}"
            )

        with transaction.atomic():
            # 1. Resolve Admin / Actor
            actor = (
                User.objects.filter(is_platform_owner=True).order_by("created_at").first()
                or User.objects.filter(is_superuser=True).first()
                or User.objects.first()
            )
            if not actor:
                raise CommandError("No platform owner or administrator found to perform configuration.")

            # 2. Resolve Canonical FieldSense Product
            product = Product.objects.filter(code=CANONICAL_PRODUCT_CODE).first()
            if not product:
                legacy_prod = Product.objects.filter(code=LEGACY_PRODUCT_CODE).first()
                if legacy_prod:
                    self.stdout.write(
                        self.style.WARNING(
                            f"Migrating existing product {legacy_prod.id} from '{LEGACY_PRODUCT_CODE}' to canonical '{CANONICAL_PRODUCT_CODE}'."
                        )
                    )
                    legacy_prod.code = CANONICAL_PRODUCT_CODE
                    if legacy_prod.name == "FIELDSENCE":
                        legacy_prod.name = "FieldSense Operations Hub"
                    legacy_prod.updated_by = actor
                    legacy_prod.save(update_fields=["code", "name", "updated_by"])
                    product = legacy_prod
                else:
                    product = Product.objects.create(
                        code=CANONICAL_PRODUCT_CODE,
                        name="FieldSense Operations Hub",
                        description="Real-time field force automation, route optimization, and activity logging.",
                        status=ProductStatus.ACTIVE,
                        created_by=actor,
                        updated_by=actor,
                    )
                    self.stdout.write(self.style.SUCCESS(f"Created canonical product: {product.name} ({product.code})"))
            else:
                self.stdout.write(f"Canonical product found: {product.name} ({product.code})")

            # Ensure product status is active
            if product.status != ProductStatus.ACTIVE:
                product.status = ProductStatus.ACTIVE
                product.save(update_fields=["status"])

            # 3. Ensure Default Product Modules Exist for FieldSense
            default_modules = [
                ("fieldsense_tracking", "Location & Beat Planning", "Live GPS tracking, route deviation alerts, and daily travel logs."),
                ("fieldsense_tasks", "Field Task Allocation", "Dynamic dispatching of service tasks and delivery assignments."),
                ("fieldsense_reporting", "Visit & Activity Reports", "Client meeting checklists, signature capture, and photographic proof."),
            ]
            for idx, (m_code, m_name, m_desc) in enumerate(default_modules):
                legacy_mod_code = m_code.replace("fieldsense", "fieldsence")
                mod = ProductModule.objects.filter(product=product, code__in=[m_code, legacy_mod_code]).first()
                if not mod:
                    ProductModule.objects.create(
                        product=product,
                        code=m_code,
                        name=m_name,
                        description=m_desc,
                        display_order=idx,
                        status=CatalogStatus.ACTIVE,
                        created_by=actor,
                        updated_by=actor,
                    )
                elif mod.code != m_code:
                    mod.code = m_code
                    mod.name = m_name
                    mod.status = CatalogStatus.ACTIVE
                    mod.save(update_fields=["code", "name", "status"])

            # 4. Resolve Showcase Profile
            profile = ProductShowcaseProfile.objects.filter(product=product).first()
            if not profile:
                profile = ProductShowcaseProfile.objects.create(
                    product=product,
                    tagline="Intelligent field force tracking, route optimization, and activity logging",
                    overview=(
                        "Real-time field force automation and tracking platform. Empowers field representatives "
                        "and managers with GPS-enabled task allocation, automated geo-fenced attendance, "
                        "route optimization, dynamic beat planning, and structured client visit logging."
                    ),
                    category="Field Operations & Workforce",
                    visibility=ShowcaseVisibility.PUBLISHED,
                    display_order=5,
                    created_by=actor,
                    updated_by=actor,
                )
                self.stdout.write(self.style.SUCCESS(f"Created ProductShowcaseProfile for {product.name}."))
            else:
                if profile.visibility != ShowcaseVisibility.PUBLISHED:
                    profile.visibility = ShowcaseVisibility.PUBLISHED
                    profile.save(update_fields=["visibility"])
                self.stdout.write(f"ProductShowcaseProfile found: {profile.id} (visibility: {profile.visibility})")

            # 5. Register or Idempotently Update ProductDemoEnvironment
            demo_env = ProductDemoEnvironment.objects.filter(product=product, base_url=base_url).first()
            if not demo_env:
                # Check by name
                demo_env_by_name = ProductDemoEnvironment.objects.filter(product=product, name=DEMO_ENV_NAME).first()
                if demo_env_by_name:
                    if demo_env_by_name.base_url != base_url:
                        if not allow_update:
                            raise CommandError(
                                f"Demo environment '{DEMO_ENV_NAME}' already exists with URL '{demo_env_by_name.base_url}'. "
                                "Pass --update to rebind base_url."
                            )
                        demo_env_by_name.base_url = base_url
                        demo_env_by_name.is_active = True
                        demo_env_by_name.updated_by = actor
                        demo_env_by_name.save(update_fields=["base_url", "is_active", "updated_by"])
                        demo_env = demo_env_by_name
                        self.stdout.write(self.style.SUCCESS(f"Updated DemoEnvironment: {demo_env.name} -> {base_url}"))
                    else:
                        demo_env = demo_env_by_name
                else:
                    demo_env = ProductDemoEnvironment.objects.create(
                        product=product,
                        name=DEMO_ENV_NAME,
                        base_url=base_url,
                        description="Local live demonstration environment for FieldSense Operations Hub.",
                        is_active=True,
                        created_by=actor,
                        updated_by=actor,
                    )
                    self.stdout.write(self.style.SUCCESS(f"Created DemoEnvironment: {demo_env.name} ({demo_env.base_url})"))
            else:
                if not demo_env.is_active:
                    demo_env.is_active = True
                    demo_env.save(update_fields=["is_active"])
                self.stdout.write(f"DemoEnvironment exists: {demo_env.name} ({demo_env.base_url})")

            # 6. Delegate SSO Client & Connector Registration to register_fieldsense_sso_client
            self.stdout.write("Running register_fieldsense_sso_client...")
            call_command(
                "register_fieldsense_sso_client",
                product_code=product.code,
                client_identifier=CLIENT_IDENTIFIER,
                audience=AUDIENCE,
                callback_uri=callback_uri,
                organization=org_code,
                update=allow_update,
            )

            # Verify active SSO client & connector instance
            sso_client = ProductSsoClient.objects.filter(product=product, client_identifier=CLIENT_IDENTIFIER, is_active=True).first()
            if not sso_client:
                raise CommandError("Failed to verify active ProductSsoClient after registration.")

            demo_org = Organization.objects.filter(code=org_code, status="active").first()
            if not demo_org:
                raise CommandError(f"Target organization '{org_code}' is not active or does not exist.")

            conn_instance = ConnectorInstance.objects.filter(
                connector__product=product,
                organization=demo_org,
                status=InstanceStatus.ACTIVE,
            ).first()
            if not conn_instance:
                raise CommandError(f"Failed to verify active ConnectorInstance for org '{org_code}'.")

            # 7. Ensure Organization Entitlement in demo-org
            entitlement, ent_created = OrganizationProductEntitlement.objects.get_or_create(
                organization=demo_org,
                product=product,
                defaults={
                    "status": EntitlementStatus.ACTIVE,
                    "created_by": actor,
                    "updated_by": actor,
                },
            )
            if not ent_created and entitlement.status != EntitlementStatus.ACTIVE:
                entitlement.status = EntitlementStatus.ACTIVE
                entitlement.save(update_fields=["status"])
            self.stdout.write(f"OrganizationProductEntitlement: {entitlement.status} ({'created' if ent_created else 'active'})")

            # 8. Verify Demo User & Membership
            demo_user = User.objects.filter(email=user_email).first()
            if not demo_user:
                raise CommandError(f"Demo user '{user_email}' not found. Please create user first.")

            membership = OrganizationMembership.objects.filter(
                organization=demo_org,
                user=demo_user,
                status=MembershipStatus.ACTIVE,
            ).first()
            if not membership:
                raise CommandError(
                    f"User '{user_email}' does not have an active membership in organization '{org_code}'."
                )
            self.stdout.write(f"Verified active membership for {demo_user.email} in {demo_org.code}.")

            # 9. Ensure UserProductAssignment & Module Assignments
            assignment, assign_created = UserProductAssignment.objects.get_or_create(
                organization=demo_org,
                user=demo_user,
                product=product,
                defaults={
                    "membership": membership,
                    "status": AssignmentStatus.ACTIVE,
                    "created_by": actor,
                    "updated_by": actor,
                },
            )
            if not assign_created and assignment.status != AssignmentStatus.ACTIVE:
                assignment.status = AssignmentStatus.ACTIVE
                assignment.save(update_fields=["status"])
            self.stdout.write(f"UserProductAssignment: {assignment.status} ({'created' if assign_created else 'active'})")

            # Enable modules on assignment for effective access
            active_modules = ProductModule.objects.filter(product=product, status=CatalogStatus.ACTIVE)
            for mod in active_modules:
                uma, uma_created = UserModuleAssignment.objects.get_or_create(
                    assignment=assignment,
                    module=mod,
                    defaults={"is_enabled": True},
                )
                if not uma_created and not uma.is_enabled:
                    uma.is_enabled = True
                    uma.save(update_fields=["is_enabled"])

            # 10. Configure ProductLaunchConfig for SSO Direct Demo Launch
            launch_cfg = ProductLaunchConfig.objects.filter(
                product=product
            ).first() or ProductLaunchConfig.objects.filter(
                profile=profile
            ).first()

            if not launch_cfg:
                launch_cfg = ProductLaunchConfig.objects.create(
                    product=product,
                    profile=profile,
                    launch_mode=ProductLaunchConfig.LaunchMode.SSO_DIRECT,
                    target_environment=demo_env,
                    allowed_targets=[demo_env.base_url],
                    policy={
                        "demo_organization_code": demo_org.code,
                        "demo_user_email": demo_user.email,
                        "open_mode": "embed",
                    },
                    notes="Configured FieldSense Operations Hub Live Showcase SSO demo.",
                    created_by=actor,
                    updated_by=actor,
                )
                self.stdout.write(self.style.SUCCESS("Created FieldSense ProductLaunchConfig in SSO_DIRECT mode."))
            else:
                launch_cfg.product = product
                launch_cfg.profile = profile
                launch_cfg.launch_mode = ProductLaunchConfig.LaunchMode.SSO_DIRECT
                launch_cfg.target_environment = demo_env
                if demo_env.base_url not in (launch_cfg.allowed_targets or []):
                    launch_cfg.allowed_targets = [demo_env.base_url]
                launch_cfg.policy = {
                    "demo_organization_code": demo_org.code,
                    "demo_user_email": demo_user.email,
                    "open_mode": "embed",
                }
                launch_cfg.updated_by = actor
                launch_cfg.save(
                    update_fields=[
                        "product",
                        "profile",
                        "launch_mode",
                        "target_environment",
                        "allowed_targets",
                        "policy",
                        "updated_by",
                    ]
                )
                self.stdout.write(self.style.SUCCESS("Updated FieldSense ProductLaunchConfig to SSO_DIRECT mode."))

            record_audit_event(
                action=AuditAction.SHOWCASE_CONFIG_CHANGED,
                target_type=AuditTargetType.SHOWCASE_PROFILE,
                target_id=str(profile.id),
                target_repr=f"ShowcaseProfile({product.name})",
                actor=actor,
                organization_id=demo_org.id,
                operation_source=AuditOperationSource.INTERACTIVE,
                correlation_id=None,
                metadata={
                    "operation": "setup_fieldsense_demo",
                    "product_code": product.code,
                    "product_name": product.name,
                    "profile_id": str(profile.id),
                    "launch_mode": "sso_direct",
                    "demo_environment_id": str(demo_env.id),
                    "demo_organization": demo_org.code,
                    "demo_user": demo_user.email,
                },
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"\nFieldSense Live Demo Configuration Complete!\n"
                f"  Product: {product.name} ({product.code})\n"
                f"  Showcase Profile: {profile.id}\n"
                f"  Target Environment: {demo_env.name} ({demo_env.base_url})\n"
                f"  Launch Mode: {launch_cfg.launch_mode}\n"
                f"  Demo Org: {demo_org.code}\n"
                f"  Demo User: {demo_user.email}\n"
                f"  SSO Client: {sso_client.client_identifier} (callback: {sso_client.callback_uri})\n"
            )
        )
