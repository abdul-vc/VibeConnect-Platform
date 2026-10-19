"""Safe, idempotent management command to configure PeoplePulse HRMS Live Showcase SSO Demo.

Configures:
1. Strict runtime database preflight: verifies local database and settings.
2. Canonical Product & Showcase Profile: ensures 'hrms' is active and published.
3. ProductDemoEnvironment: registers active 'PeoplePulse HRMS Local Demo' at 'http://localhost:8081'.
4. IntegrationConnector & ConnectorInstance: binds 'hrms_connector' to 'demo-org'.
5. ProductSsoClient: registers 'hrms-app' with callback 'http://localhost:8081/sso/callback'.
6. OrganizationProductEntitlement: activates HRMS entitlement for 'demo-org'.
7. UserProductAssignment (Optional): conditionally links an existing user; strictly prohibits user creation.
8. ProductLaunchConfig: updates to 'sso_direct' targeting 'http://localhost:8081'.

Safety guarantees:
- Dry-run mode (--dry-run) to preview changes without modifying database.
- Refuses to run against non-local databases or non-local settings.
- Refuses to overwrite conflicting records unless --update is specified.
- Does not create users or superusers.
- Operates inside an atomic transaction.
"""

from typing import Any
from urllib.parse import urlparse

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction

from apps.assignments.models import AssignmentStatus, UserModuleAssignment, UserProductAssignment
from apps.entitlements.models import EntitlementStatus, OrganizationProductEntitlement
from apps.identity.models import PlatformUser
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

DEFAULT_PRODUCT_CODE = "hrms"
DEFAULT_CLIENT_ID = "hrms-app"
DEFAULT_AUDIENCE = "hrms-app"
DEFAULT_CALLBACK_URI = "http://localhost:8080/sso/callback"
DEFAULT_DEMO_URL = "http://localhost:8080"
DEFAULT_DEMO_ENV_NAME = "PeoplePulse HRMS Local Demo"
DEFAULT_CONNECTOR_CODE = "hrms_connector"
DEFAULT_PUBLIC_KEY_REF = "vault://keys/hrms-app-m2m"
DEFAULT_CREDENTIAL_REF = "vault://tenant/demo-org/hrms"
DEMO_ORG_CODE = "demo-org"


class Command(BaseCommand):
    help = "Idempotently configure PeoplePulse HRMS Live Showcase SSO Demo in local development."

    def add_arguments(self, parser):
        parser.add_argument(
            "--client-identifier",
            default=DEFAULT_CLIENT_ID,
            help=f"Client identifier for HRMS SSO client (default: {DEFAULT_CLIENT_ID}).",
        )
        parser.add_argument(
            "--audience",
            default=DEFAULT_AUDIENCE,
            help=f"Expected token audience (default: {DEFAULT_AUDIENCE}).",
        )
        parser.add_argument(
            "--callback-uri",
            default=DEFAULT_CALLBACK_URI,
            help=f"Callback URI for HRMS SSO client (default: {DEFAULT_CALLBACK_URI}).",
        )
        parser.add_argument(
            "--base-url",
            default=DEFAULT_DEMO_URL,
            help=f"Base URL for HRMS Local Demo (default: {DEFAULT_DEMO_URL}).",
        )
        parser.add_argument(
            "--organization",
            default=DEMO_ORG_CODE,
            help=f"Target allowlisted demo organization code (default: {DEMO_ORG_CODE}).",
        )
        parser.add_argument(
            "--user-email",
            default=None,
            help="Target existing demo user email in demo organization (optional; does NOT create users).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Simulate execution and preview all changes without writing to database.",
        )
        parser.add_argument(
            "--update",
            action="store_true",
            help="Explicitly permit updating existing configuration fields if differing.",
        )

    def handle(self, *args: Any, **options: Any):
        client_identifier = options["client_identifier"].strip()
        audience = options["audience"].strip()
        callback_uri = options["callback_uri"].strip()
        base_url = options["base_url"].rstrip("/")
        org_code = options["organization"].strip()
        user_email = options.get("user_email")
        if user_email:
            user_email = user_email.strip()
        is_dry_run = options["dry_run"]
        allow_update = options["update"]

        prefix = "[DRY-RUN] " if is_dry_run else ""

        # =====================================================================
        # 1. STRICT RUNTIME DATABASE PREFLIGHT
        # =====================================================================
        self.stdout.write(self.style.MIGRATE_HEADING("=== 1. Runtime Safety & Database Preflight ==="))

        # Check 1.1: Active settings module
        active_settings = getattr(settings, "SETTINGS_MODULE", None) or os.environ.get("DJANGO_SETTINGS_MODULE", "")
        if "local" not in active_settings.lower():
            raise CommandError(
                f"ABORT: Disallowed DJANGO_SETTINGS_MODULE '{active_settings}'. Must be a local settings module."
            )
        self.stdout.write(f"  [PASS] Settings module is '{active_settings}'.")

        # Check 1.2: Database identity
        with connection.cursor() as cur:
            cur.execute("SELECT current_database(), current_user, inet_server_addr(), inet_server_port();")
            db_name, db_user, srv_addr, srv_port = cur.fetchone()

        if db_name != "vibeconnect_local":
            raise CommandError(f"ABORT: Connected to unexpected database '{db_name}'. Must be 'vibeconnect_local'.")
        if srv_addr not in ("::1", "127.0.0.1", None):
            raise CommandError(f"ABORT: Connected to non-local database host '{srv_addr}'. Refusing to proceed.")
        self.stdout.write(
            f"  [PASS] Database is '{db_name}' on localhost ({srv_addr or 'localhost'}:{srv_port}) as user '{db_user}'."
        )

        # Check 1.3: Authorized demo organization check
        if org_code not in AUTHORIZED_DEMO_ORGANIZATION_CODES:
            raise CommandError(
                f"Organization '{org_code}' is not an authorized demo organization context. "
                f"Permitted contexts: {sorted(AUTHORIZED_DEMO_ORGANIZATION_CODES)}"
            )

        # Check 1.4: Callback URI validation
        parsed_cb = urlparse(callback_uri)
        if not parsed_cb.scheme or not parsed_cb.netloc:
            raise CommandError(f"Invalid callback URI format: '{callback_uri}'")
        if not parsed_cb.path.endswith("/sso/callback"):
            raise CommandError(f"Callback URI must end in '/sso/callback', got: '{parsed_cb.path}'")

        # =====================================================================
        # 2. ATOMIC CONFIGURATION EXECUTION
        # =====================================================================
        self.stdout.write(self.style.MIGRATE_HEADING(f"\n=== 2. {prefix}Executing HRMS SSO Configuration ==="))

        with transaction.atomic():
            # 2.1 Actor resolution (system user or platform owner)
            actor = (
                PlatformUser.objects.filter(email="system@vibeconnect.internal").first()
                or PlatformUser.objects.filter(is_platform_owner=True).order_by("created_at").first()
                or PlatformUser.objects.filter(is_superuser=True).first()
            )
            if not actor:
                raise CommandError("No system user or platform owner found to execute configuration.")
            self.stdout.write(f"  Actor: {actor.email} (ID: {actor.id})")

            # 2.2 Product verification
            product = Product.objects.filter(code=DEFAULT_PRODUCT_CODE).first()
            if not product:
                raise CommandError(f"Product '{DEFAULT_PRODUCT_CODE}' not found in product registry.")
            if product.status != ProductStatus.ACTIVE:
                if not allow_update:
                    raise CommandError(f"Product '{product.code}' is currently '{product.status}'. Pass --update to activate.")
                product.status = ProductStatus.ACTIVE
                product.updated_by = actor
                product.save(update_fields=["status", "updated_by"])
                self.stdout.write(self.style.SUCCESS(f"  {prefix}[UPDATED] Product '{product.code}' set to active."))
            else:
                self.stdout.write(f"  [EXISTING] Product: {product.name} ({product.code}) is active.")

            # 2.3 Showcase Profile verification
            profile = ProductShowcaseProfile.objects.filter(product=product).first()
            if not profile:
                profile = ProductShowcaseProfile.objects.create(
                    product=product,
                    tagline="Enterprise human capital management and payroll platform",
                    overview="Modern workforce management, biometric attendance tracking, automated payroll, and leave management.",
                    category="Human Resources & Workforce",
                    visibility=ShowcaseVisibility.PUBLISHED,
                    display_order=4,
                    created_by=actor,
                    updated_by=actor,
                )
                self.stdout.write(self.style.SUCCESS(f"  {prefix}[CREATED] Showcase Profile for {product.name}."))
            else:
                if profile.visibility != ShowcaseVisibility.PUBLISHED:
                    if not allow_update:
                        raise CommandError(f"Showcase profile visibility is '{profile.visibility}'. Pass --update to publish.")
                    profile.visibility = ShowcaseVisibility.PUBLISHED
                    profile.updated_by = actor
                    profile.save(update_fields=["visibility", "updated_by"])
                    self.stdout.write(self.style.SUCCESS(f"  {prefix}[UPDATED] Showcase Profile set to published."))
                else:
                    self.stdout.write(f"  [EXISTING] Showcase Profile is published.")

            # 2.4 ProductDemoEnvironment
            demo_env = ProductDemoEnvironment.objects.filter(product=product, base_url=base_url).first()
            if not demo_env:
                demo_env_by_name = ProductDemoEnvironment.objects.filter(product=product, name=DEFAULT_DEMO_ENV_NAME).first()
                if demo_env_by_name:
                    if demo_env_by_name.base_url != base_url:
                        if not allow_update:
                            raise CommandError(
                                f"DemoEnvironment '{DEFAULT_DEMO_ENV_NAME}' exists with URL '{demo_env_by_name.base_url}'. "
                                "Pass --update to rebind base_url."
                            )
                        demo_env_by_name.base_url = base_url
                        demo_env_by_name.is_active = True
                        demo_env_by_name.updated_by = actor
                        demo_env_by_name.save(update_fields=["base_url", "is_active", "updated_by"])
                        demo_env = demo_env_by_name
                        self.stdout.write(self.style.SUCCESS(f"  {prefix}[UPDATED] DemoEnvironment '{demo_env.name}' -> {base_url}"))
                    else:
                        demo_env = demo_env_by_name
                        self.stdout.write(f"  [EXISTING] DemoEnvironment '{demo_env.name}' matches {base_url}.")
                else:
                    demo_env = ProductDemoEnvironment.objects.create(
                        product=product,
                        name=DEFAULT_DEMO_ENV_NAME,
                        base_url=base_url,
                        description="Local live demonstration environment for PeoplePulse HRMS.",
                        is_active=True,
                        created_by=actor,
                        updated_by=actor,
                    )
                    self.stdout.write(self.style.SUCCESS(f"  {prefix}[CREATED] DemoEnvironment '{demo_env.name}' (ID: {demo_env.id}) -> {base_url}"))
            else:
                if not demo_env.is_active:
                    demo_env.is_active = True
                    demo_env.updated_by = actor
                    demo_env.save(update_fields=["is_active", "updated_by"])
                    self.stdout.write(self.style.SUCCESS(f"  {prefix}[UPDATED] DemoEnvironment '{demo_env.name}' set to active."))
                else:
                    self.stdout.write(f"  [EXISTING] DemoEnvironment '{demo_env.name}' is active.")

            # 2.5 IntegrationConnector
            connector, conn_created = IntegrationConnector.objects.get_or_create(
                code=DEFAULT_CONNECTOR_CODE,
                defaults={
                    "name": "PeoplePulse HRMS Connector",
                    "description": "Integration connector for PeoplePulse HRMS employee lifecycle, payroll, and attendance.",
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
                self.stdout.write(self.style.SUCCESS(f"  {prefix}[UPDATED] IntegrationConnector '{connector.code}' updated."))
            else:
                self.stdout.write(f"  [{'CREATED' if conn_created else 'EXISTING'}] IntegrationConnector '{connector.code}'.")

            # 2.6 Target Demo Organization
            demo_org = Organization.objects.filter(code=org_code, status="active").first()
            if not demo_org:
                raise CommandError(f"Target organization '{org_code}' not found or is not active.")

            # 2.7 ConnectorInstance
            conn_instance, inst_created = ConnectorInstance.objects.get_or_create(
                connector=connector,
                organization=demo_org,
                defaults={
                    "label": f"PeoplePulse HRMS - {demo_org.name}",
                    "credential_ref": DEFAULT_CREDENTIAL_REF,
                    "config": {"base_url": base_url, "api_url": "http://127.0.0.1:8003"},
                    "status": InstanceStatus.ACTIVE,
                },
            )
            if not inst_created and conn_instance.status != InstanceStatus.ACTIVE:
                conn_instance.status = InstanceStatus.ACTIVE
                conn_instance.save(update_fields=["status"])
                self.stdout.write(self.style.SUCCESS(f"  {prefix}[UPDATED] ConnectorInstance for '{demo_org.code}' activated."))
            else:
                self.stdout.write(f"  [{'CREATED' if inst_created else 'EXISTING'}] ConnectorInstance '{conn_instance.label}'.")

            # 2.8 ProductSsoClient
            existing_client_by_id = ProductSsoClient.objects.filter(client_identifier=client_identifier).first()
            existing_client_by_prod = ProductSsoClient.objects.filter(product=product).first()

            if existing_client_by_id and existing_client_by_id.product_id != product.id:
                raise CommandError(
                    f"Conflict: client_identifier '{client_identifier}' is already bound to product "
                    f"'{existing_client_by_id.product.code}' (ID: {existing_client_by_id.product_id}). "
                    "Refusing to overwrite conflicting client."
                )

            if existing_client_by_prod and existing_client_by_prod.client_identifier != client_identifier:
                if not allow_update:
                    raise CommandError(
                        f"Conflict: Product '{product.code}' already has client '{existing_client_by_prod.client_identifier}'. "
                        "Pass --update to explicitly rebind."
                    )
                existing_client_by_prod.client_identifier = client_identifier
                existing_client_by_prod.save(update_fields=["client_identifier"])
                sso_client = existing_client_by_prod
            elif existing_client_by_id:
                sso_client = existing_client_by_id
            else:
                sso_client = None

            if sso_client:
                changes = []
                if sso_client.audience != audience:
                    changes.append(("audience", sso_client.audience, audience))
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
                            f"ProductSsoClient '{client_identifier}' exists with differing fields: {diffs}. Pass --update to apply."
                        )
                    sso_client.audience = audience
                    sso_client.callback_uri = callback_uri
                    sso_client.public_key_reference = DEFAULT_PUBLIC_KEY_REF
                    sso_client.is_active = True
                    sso_client.save(update_fields=["audience", "callback_uri", "public_key_reference", "is_active"])
                    self.stdout.write(self.style.SUCCESS(f"  {prefix}[UPDATED] ProductSsoClient [{client_identifier}]."))
                else:
                    self.stdout.write(f"  [EXISTING] ProductSsoClient [{client_identifier}] is up to date.")
            else:
                sso_client = ProductSsoClient.objects.create(
                    product=product,
                    client_identifier=client_identifier,
                    audience=audience,
                    callback_uri=callback_uri,
                    public_key_reference=DEFAULT_PUBLIC_KEY_REF,
                    is_active=True,
                )
                self.stdout.write(self.style.SUCCESS(f"  {prefix}[CREATED] ProductSsoClient [{client_identifier}] (ID: {sso_client.id})."))

            # 2.9 OrganizationProductEntitlement
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
                entitlement.updated_by = actor
                entitlement.save(update_fields=["status", "updated_by"])
                self.stdout.write(self.style.SUCCESS(f"  {prefix}[UPDATED] OrganizationProductEntitlement activated."))
            else:
                self.stdout.write(f"  [{'CREATED' if ent_created else 'EXISTING'}] OrganizationProductEntitlement for '{demo_org.code}'.")

            # 2.10 UserProductAssignment (strictly conditional on existing user; NO user creation)
            assigned_user_email = None
            if user_email:
                demo_user = PlatformUser.objects.filter(email=user_email).first()
                if not demo_user:
                    raise CommandError(
                        f"Specified user '{user_email}' does not exist in PlatformUser. "
                        "User creation is strictly prohibited in this command."
                    )
                membership = OrganizationMembership.objects.filter(
                    organization=demo_org,
                    user=demo_user,
                    status=MembershipStatus.ACTIVE,
                ).first()
                if not membership:
                    raise CommandError(f"User '{user_email}' has no active membership in organization '{org_code}'.")

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
                    assignment.updated_by = actor
                    assignment.save(update_fields=["status", "updated_by"])
                self.stdout.write(
                    f"  [{'CREATED' if assign_created else 'EXISTING'}] UserProductAssignment for {demo_user.email}."
                )

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
                    self.stdout.write(f"    ModuleAssignment: {mod.code} ({'created' if uma_created else 'enabled'})")

                assigned_user_email = demo_user.email
            else:
                self.stdout.write(
                    "  [SKIPPED] No target user specified (--user-email omitted). "
                    "Zero users or assignments created (strictly adhering to safety policy)."
                )

            # 2.11 ProductLaunchConfig
            launch_cfg = ProductLaunchConfig.objects.filter(product=product).first()
            if not launch_cfg:
                launch_cfg = ProductLaunchConfig.objects.create(
                    product=product,
                    profile=profile,
                    launch_mode=ProductLaunchConfig.LaunchMode.SSO_DIRECT,
                    target_environment=demo_env,
                    allowed_targets=[base_url],
                    policy={
                        "open_mode": "embed",
                        "in_window_demo": True,
                        "allow_iframe": True,
                        "demo_organization_code": demo_org.code,
                    },
                    notes="Configured PeoplePulse HRMS Local Live Showcase SSO demo.",
                    created_by=actor,
                    updated_by=actor,
                )
                self.stdout.write(self.style.SUCCESS(f"  {prefix}[CREATED] ProductLaunchConfig (ID: {launch_cfg.id})."))
            else:
                policy = {
                    "open_mode": "embed",
                    "in_window_demo": True,
                    "allow_iframe": True,
                    "demo_organization_code": demo_org.code,
                }
                if assigned_user_email:
                    policy["demo_user_email"] = assigned_user_email

                launch_cfg.launch_mode = ProductLaunchConfig.LaunchMode.SSO_DIRECT
                launch_cfg.target_environment = demo_env
                launch_cfg.allowed_targets = [base_url]
                launch_cfg.policy = policy
                launch_cfg.notes = "Configured PeoplePulse HRMS Local Live Showcase SSO demo."
                launch_cfg.updated_by = actor
                launch_cfg.save(
                    update_fields=[
                        "launch_mode",
                        "target_environment",
                        "allowed_targets",
                        "policy",
                        "notes",
                        "updated_by",
                        "updated_at",
                    ]
                )
                self.stdout.write(self.style.SUCCESS(f"  {prefix}[UPDATED] ProductLaunchConfig -> sso_direct targeting {base_url}."))

            # If dry-run, roll back changes
            if is_dry_run:
                transaction.set_rollback(True)
                self.stdout.write(
                    self.style.WARNING(
                        "\n[DRY-RUN COMPLETE] All preflight validations passed. Transaction rolled back successfully; no changes were saved."
                    )
                )
            else:
                self.stdout.write(
                    self.style.SUCCESS(
                        "\n[SUCCESS] PeoplePulse HRMS SSO configuration applied successfully."
                    )
                )
