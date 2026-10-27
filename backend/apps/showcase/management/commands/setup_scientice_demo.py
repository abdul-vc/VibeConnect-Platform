"""Safe, idempotent management command to configure Scientice Medical Hub Live Showcase SSO Demo.

Configures:
1. Canonical Product: finds or creates 'scientice' ("Scientice Medical & Scientific Hub").
2. ProductModules: ensures active modules ('scientice_news', 'scientice_conferences', 'scientice_education', 'scientice_cms').
3. ProductShowcaseProfile: ensures published profile is linked to canonical product.
4. ProductDemoEnvironment: registers active 'Scientice Medical & Scientific Hub Local Demo' with base URL.
5. IntegrationConnector & ConnectorInstance: registered for target organization ('demo-org').
6. ProductSsoClient: registers 'scientice-portal' with callback 'http://localhost:5174/sso/callback'.
7. Tenant Access in demo organization:
   - Active OrganizationProductEntitlement for demo organization and product.
   - Verifies active OrganizationMembership for demo user.
   - Active UserProductAssignment and UserModuleAssignments for demo user.
8. ProductLaunchConfig:
   - launch_mode: sso_direct
   - target_environment: demo_env
   - allowed_targets: [demo_env.base_url]
   - policy: {'demo_organization_code': demo_org.code, 'demo_user_email': demo_user.email, 'open_mode': 'embed'}

Safety constraints:
- Strictly scoped to local demo context ('demo-org' and 'admin@gmail.com').
- Refuses conflicting overwrites without --update.
- Leaves other tenants, products, and connectors untouched.
"""

from typing import Any
from django.conf import settings
from django.contrib.auth import get_user_model
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
from apps.integration_hub.models import (
    ConnectorInstance,
    ConnectorStatus,
    InstanceStatus,
    IntegrationConnector,
    ProductSsoClient,
)
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

CANONICAL_PRODUCT_CODE = "scientice"
DEMO_ORG_CODE = "demo-org"
DEMO_USER_EMAIL = "admin@gmail.com"
DEMO_ENV_NAME = "Scientice Medical & Scientific Hub Local Demo"
DEFAULT_DEMO_URL = "http://localhost:5174"
DEFAULT_CALLBACK_URI = "http://localhost:5174/sso/callback"
CLIENT_IDENTIFIER = "scientice-portal"
AUDIENCE = "scientice-portal"
CONNECTOR_CODE = "scientice_connector"
DEFAULT_PUBLIC_KEY_REF = "scientice-m2m-hmac-v1"
DEFAULT_CREDENTIAL_REF = "scientice-m2m-cred-v1"


class Command(BaseCommand):
    help = "Idempotently configure Scientice Medical Hub Live Showcase SSO Demo."

    def add_arguments(self, parser):
        parser.add_argument(
            "--base-url",
            default=DEFAULT_DEMO_URL,
            help=f"Base URL for Scientice Local Demo (default: {DEFAULT_DEMO_URL}).",
        )
        parser.add_argument(
            "--callback-uri",
            default=DEFAULT_CALLBACK_URI,
            help=f"Callback URI for Scientice SSO client (default: {DEFAULT_CALLBACK_URI}).",
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

            # 2. Resolve Canonical Scientice Product
            product = Product.objects.filter(code=CANONICAL_PRODUCT_CODE).first()
            if not product:
                product = Product.objects.create(
                    code=CANONICAL_PRODUCT_CODE,
                    name="Scientice Medical & Scientific Hub",
                    description="Medical and scientific knowledge portal, conference coverage, clinical guidelines, and educational bulletins.",
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

            # 3. Ensure Default Product Modules Exist for Scientice
            default_modules = [
                ("scientice_news", "Medical News & Highlights", "Daily verified medical and scientific news, clinical trial updates, and therapy highlights."),
                ("scientice_conferences", "Conferences & Society Guidelines", "Global medical conferences, society consensus papers, and accredited event registration."),
                ("scientice_education", "Clinical Education & Bulletins", "Specialty CME modules, patient education guides, and video bulletin masterclasses."),
                ("scientice_cms", "Scientice CMS Studio", "Content management, guideline approval workflow, and editorial publication studio."),
            ]
            for idx, (m_code, m_name, m_desc) in enumerate(default_modules):
                mod = ProductModule.objects.filter(product=product, code=m_code).first()
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
                elif mod.status != CatalogStatus.ACTIVE:
                    mod.status = CatalogStatus.ACTIVE
                    mod.save(update_fields=["status"])

            # 4. Resolve Showcase Profile
            profile = ProductShowcaseProfile.objects.filter(product=product).first()
            if not profile:
                profile = ProductShowcaseProfile.objects.create(
                    product=product,
                    tagline="Medical & scientific knowledge portal, clinical guidelines, and conference hub",
                    overview=(
                        "Authoritative healthcare platform delivering peer-reviewed medical guidelines, "
                        "international conference coverage, multidisciplinary clinical educational resources, "
                        "and dedicated editorial CMS studio."
                    ),
                    category="Healthcare & Life Sciences",
                    visibility=ShowcaseVisibility.PUBLISHED,
                    display_order=6,
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
                        description="Local live demonstration environment for Scientice Medical Hub.",
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

            # 6. IntegrationConnector & ConnectorInstance
            demo_org = Organization.objects.filter(code=org_code, status="active").first()
            if not demo_org:
                raise CommandError(f"Target organization '{org_code}' is not active or does not exist.")

            connector, conn_created = IntegrationConnector.objects.get_or_create(
                code=CONNECTOR_CODE,
                defaults={
                    "name": "Scientice Medical Hub Connector",
                    "description": "Integration connector for Scientice Medical Hub SSO.",
                    "product": product,
                    "version": "1.0.0",
                    "status": ConnectorStatus.ACTIVE,
                    "capabilities": ["sso_launch", "user_mapping", "identity_sync"],
                },
            )
            if not conn_created and (connector.product_id != product.id or connector.status != ConnectorStatus.ACTIVE):
                connector.product = product
                connector.status = ConnectorStatus.ACTIVE
                connector.save(update_fields=["product", "status"])

            conn_instance, inst_created = ConnectorInstance.objects.get_or_create(
                connector=connector,
                organization=demo_org,
                defaults={
                    "label": f"Scientice Medical Hub - {demo_org.name}",
                    "credential_ref": DEFAULT_CREDENTIAL_REF,
                    "config": {"base_url": base_url, "callback_uri": callback_uri},
                    "status": InstanceStatus.ACTIVE,
                },
            )
            if not inst_created and conn_instance.status != InstanceStatus.ACTIVE:
                conn_instance.status = InstanceStatus.ACTIVE
                conn_instance.save(update_fields=["status"])

            # 7. ProductSsoClient
            existing_client_by_id = ProductSsoClient.objects.filter(client_identifier=CLIENT_IDENTIFIER).first()
            existing_client_by_prod = ProductSsoClient.objects.filter(product=product).first()

            if existing_client_by_id and existing_client_by_id.product_id != product.id:
                raise CommandError(
                    f"Conflict: client_identifier '{CLIENT_IDENTIFIER}' is already bound to product "
                    f"'{existing_client_by_id.product.code}' (ID: {existing_client_by_id.product_id}). "
                    "Refusing to overwrite conflicting client."
                )

            if existing_client_by_prod and existing_client_by_prod.client_identifier != CLIENT_IDENTIFIER:
                if not allow_update:
                    raise CommandError(
                        f"Conflict: Product '{product.code}' already has client '{existing_client_by_prod.client_identifier}'. "
                        "Pass --update to explicitly rebind."
                    )
                existing_client_by_prod.client_identifier = CLIENT_IDENTIFIER
                existing_client_by_prod.save(update_fields=["client_identifier"])
                sso_client = existing_client_by_prod
            elif existing_client_by_id:
                sso_client = existing_client_by_id
            else:
                sso_client = None

            if sso_client:
                changes = []
                if sso_client.audience != AUDIENCE:
                    changes.append(("audience", sso_client.audience, AUDIENCE))
                if sso_client.callback_uri != callback_uri:
                    changes.append(("callback_uri", sso_client.callback_uri, callback_uri))
                if sso_client.public_key_reference != DEFAULT_PUBLIC_KEY_REF:
                    changes.append(("public_key_reference", sso_client.public_key_reference, DEFAULT_PUBLIC_KEY_REF))
                if not sso_client.is_active:
                    changes.append(("is_active", False, True))

                if changes:
                    if not allow_update:
                        diffs = "; ".join(f"{f}: '{o}' -> '{n}'" for f, o, n in changes)
                        raise CommandError(
                            f"ProductSsoClient '{CLIENT_IDENTIFIER}' exists with differing fields: {diffs}. Pass --update to apply."
                        )
                    sso_client.audience = AUDIENCE
                    sso_client.callback_uri = callback_uri
                    sso_client.public_key_reference = DEFAULT_PUBLIC_KEY_REF
                    sso_client.is_active = True
                    sso_client.save(update_fields=["audience", "callback_uri", "public_key_reference", "is_active"])
                    self.stdout.write(self.style.SUCCESS(f"Updated ProductSsoClient [{CLIENT_IDENTIFIER}]."))
                else:
                    self.stdout.write(f"ProductSsoClient [{CLIENT_IDENTIFIER}] is up to date.")
            else:
                sso_client = ProductSsoClient.objects.create(
                    product=product,
                    client_identifier=CLIENT_IDENTIFIER,
                    audience=AUDIENCE,
                    callback_uri=callback_uri,
                    public_key_reference=DEFAULT_PUBLIC_KEY_REF,
                    is_active=True,
                )
                self.stdout.write(self.style.SUCCESS(f"Created ProductSsoClient [{CLIENT_IDENTIFIER}] (ID: {sso_client.id})."))

            # 8. Ensure Organization Entitlement in demo-org
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

            # 9. Verify Demo User & Membership
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

            # 10. Ensure UserProductAssignment & Module Assignments
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

            # 11. Configure ProductLaunchConfig for SSO Direct Demo Launch
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
                    notes="Configured Scientice Medical & Scientific Hub Live Showcase SSO demo.",
                    created_by=actor,
                    updated_by=actor,
                )
                self.stdout.write(self.style.SUCCESS("Created Scientice ProductLaunchConfig in SSO_DIRECT mode."))
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
                self.stdout.write(self.style.SUCCESS("Updated Scientice ProductLaunchConfig to SSO_DIRECT mode."))

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
                    "operation": "setup_scientice_demo",
                    "product_code": product.code,
                    "product_name": product.name,
                    "profile_id": str(profile.id),
                    "client_identifier": CLIENT_IDENTIFIER,
                    "demo_org": org_code,
                    "demo_user": user_email,
                    "base_url": base_url,
                    "callback_uri": callback_uri,
                },
            )

            self.stdout.write(self.style.SUCCESS("\nScientice Live Demo Configuration Complete!"))
            self.stdout.write(f"  Product: {product.name} ({product.code})")
            self.stdout.write(f"  Showcase Profile: {profile.id}")
            self.stdout.write(f"  Target Environment: {demo_env.name} ({demo_env.base_url})")
            self.stdout.write("  Launch Mode: sso_direct")
            self.stdout.write(f"  Demo Org: {demo_org.code}")
            self.stdout.write(f"  Demo User: {demo_user.email}")
            self.stdout.write(f"  SSO Client: {sso_client.client_identifier} (callback: {sso_client.callback_uri})")
