"""Safe, idempotent management command to register the FieldSense Operations Hub SSO client.

Configures:
1. Locates or creates FieldSense product (code: 'fieldsense').
2. Ensures IntegrationConnector exists for the fieldsense product.
3. Registers or idempotently updates ProductSsoClient for 'fieldsense-ops-hub'.
4. Optionally binds active ConnectorInstance for one or more tenant organizations.
5. Performs safety checks: refuses silent overwrites of conflicting records.
"""

from urllib.parse import urlparse

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.integration_hub.models import (
    ConnectorInstance,
    ConnectorStatus,
    InstanceStatus,
    IntegrationConnector,
    ProductSsoClient,
)
from apps.organizations.models import Organization
from apps.product_registry.models import Product, ProductStatus

User = get_user_model()

DEFAULT_CLIENT_ID = "fieldsense-ops-hub"
DEFAULT_PRODUCT_CODE = "fieldsense"
DEFAULT_AUDIENCE = "fieldsense-ops-hub"
DEFAULT_CALLBACK_URI = "http://localhost:8081/sso/callback"
DEFAULT_PUBLIC_KEY_REF = "vault://keys/fieldsense-ops-hub-m2m"
CONNECTOR_CODE = "fieldsense_ops_hub_connector"


class Command(BaseCommand):
    help = "Idempotently register or update the FieldSense Operations Hub SSO client and connector."

    def add_arguments(self, parser):
        parser.add_argument(
            "--client-identifier",
            default=DEFAULT_CLIENT_ID,
            help=f"Client identifier for FieldSense Operations Hub (default: {DEFAULT_CLIENT_ID}).",
        )
        parser.add_argument(
            "--product-code",
            default=DEFAULT_PRODUCT_CODE,
            help=f"Product code for FieldSense (default: {DEFAULT_PRODUCT_CODE}).",
        )
        parser.add_argument(
            "--audience",
            default=DEFAULT_AUDIENCE,
            help=f"Expected token audience (default: {DEFAULT_AUDIENCE}).",
        )
        parser.add_argument(
            "--callback-uri",
            default=None,
            help=f"Exact callback URL ending in /sso/callback (default: from settings/env or {DEFAULT_CALLBACK_URI}).",
        )
        parser.add_argument(
            "--public-key-ref",
            default=DEFAULT_PUBLIC_KEY_REF,
            help="Opaque reference to verification key.",
        )
        parser.add_argument(
            "--organization",
            default=None,
            help="Organization code or UUID to bind an active ConnectorInstance for SSO.",
        )
        parser.add_argument(
            "--bind-all-active-orgs",
            action="store_true",
            help="Bind active ConnectorInstances for all active organizations in database.",
        )
        parser.add_argument(
            "--inactive",
            action="store_true",
            help="Register the client as inactive initially.",
        )
        parser.add_argument(
            "--update",
            action="store_true",
            help="Explicitly permit updating existing client fields if configuration has changed.",
        )

    def handle(self, *args, **options):
        client_identifier = options["client_identifier"].strip()
        product_code = options["product_code"].strip()
        audience = options["audience"].strip()
        public_key_ref = options["public_key_ref"].strip()
        is_active = not options["inactive"]
        allow_update = options["update"]

        # Resolve callback URI
        callback_uri = options.get("callback_uri")
        if not callback_uri:
            callback_uri = getattr(settings, "VIBECONNECT_FIELDSENSE_CALLBACK_URI", None)
        if not callback_uri:
            callback_uri = DEFAULT_CALLBACK_URI
        callback_uri = callback_uri.strip()

        # Validate callback URI structure
        parsed = urlparse(callback_uri)
        if not parsed.scheme or not parsed.netloc:
            raise CommandError(f"Invalid callback URI format: '{callback_uri}'")
        if not parsed.path.endswith("/sso/callback"):
            raise CommandError(f"Callback URI must end in '/sso/callback', got: '{parsed.path}'")

        is_local = parsed.hostname in ("localhost", "127.0.0.1", "::1")
        if not getattr(settings, "DEBUG", False) and parsed.scheme != "https" and not is_local:
            raise CommandError("Production callback URI must use HTTPS for non-local endpoints.")

        with transaction.atomic():
            # 1. Locate or create FieldSense Product
            product = Product.objects.filter(code=product_code).first()
            if not product:
                owner = (
                    User.objects.filter(is_platform_owner=True).order_by("created_at").first()
                    or User.objects.filter(is_superuser=True).first()
                    or User.objects.first()
                )
                if not owner:
                    raise CommandError(
                        f"Product with code '{product_code}' not found and no user available to create it. "
                        "Please ensure a platform user or administrator exists."
                    )
                product = Product.objects.create(
                    code=product_code,
                    name="FieldSense Operations Hub",
                    description="FieldSense Operations Hub - Intelligent field force tracking, route optimization, and activity logging.",
                    status=ProductStatus.ACTIVE,
                    created_by=owner,
                    updated_by=owner,
                )
                self.stdout.write(self.style.SUCCESS(f"Created Product: {product.name} ({product.code}, ID: {product.id})"))
            else:
                self.stdout.write(f"Target Product: {product.name} ({product.code}, ID: {product.id})")

            # 2. Conflict & Existing Client Verification
            existing_by_identifier = ProductSsoClient.objects.filter(client_identifier=client_identifier).first()
            existing_by_product = ProductSsoClient.objects.filter(product=product).first()

            if existing_by_identifier and existing_by_identifier.product_id != product.id:
                raise CommandError(
                    f"Conflict: client_identifier '{client_identifier}' is already bound to another product "
                    f"'{existing_by_identifier.product.code}' (ID: {existing_by_identifier.product_id}). "
                    "Refusing to overwrite conflicting client."
                )

            if existing_by_product and existing_by_product.client_identifier != client_identifier:
                if not allow_update:
                    raise CommandError(
                        f"Conflict: Product '{product.code}' already has an active client '{existing_by_product.client_identifier}'. "
                        "Pass --update to explicitly rebind to a new client identifier."
                    )
                self.stdout.write(
                    self.style.WARNING(
                        f"Rebinding product '{product.code}' from '{existing_by_product.client_identifier}' to '{client_identifier}'."
                    )
                )
                existing_by_product.client_identifier = client_identifier
                existing_by_product.save(update_fields=["client_identifier"])
                sso_client = existing_by_product
            elif existing_by_identifier:
                sso_client = existing_by_identifier
            else:
                sso_client = None

            # 3. Create or update ProductSsoClient
            if sso_client:
                changes = []
                if sso_client.audience != audience:
                    changes.append(("audience", sso_client.audience, audience))
                if sso_client.callback_uri != callback_uri:
                    changes.append(("callback_uri", sso_client.callback_uri, callback_uri))
                if sso_client.public_key_reference != public_key_ref:
                    changes.append(("public_key_reference", sso_client.public_key_reference, public_key_ref))
                if sso_client.is_active != is_active:
                    changes.append(("is_active", sso_client.is_active, is_active))

                if changes:
                    if not allow_update:
                        change_summary = "; ".join(f"{field}: '{old}' -> '{new}'" for field, old, new in changes)
                        raise CommandError(
                            f"Client '{client_identifier}' already exists with differing configuration: {change_summary}. "
                            "Pass --update to explicitly apply these changes."
                        )
                    sso_client.audience = audience
                    sso_client.callback_uri = callback_uri
                    sso_client.public_key_reference = public_key_ref
                    sso_client.is_active = is_active
                    sso_client.save(update_fields=["audience", "callback_uri", "public_key_reference", "is_active"])
                    self.stdout.write(self.style.SUCCESS(f"Updated ProductSsoClient [{client_identifier}]."))
                else:
                    self.stdout.write(self.style.SUCCESS(f"ProductSsoClient [{client_identifier}] is up to date (no changes required)."))
            else:
                sso_client = ProductSsoClient.objects.create(
                    product=product,
                    client_identifier=client_identifier,
                    audience=audience,
                    callback_uri=callback_uri,
                    public_key_reference=public_key_ref,
                    is_active=is_active,
                )
                self.stdout.write(self.style.SUCCESS(f"Created ProductSsoClient [{client_identifier}] (ID: {sso_client.id})."))

            # 4. Ensure IntegrationConnector exists for FieldSense
            connector, conn_created = IntegrationConnector.objects.get_or_create(
                code=CONNECTOR_CODE,
                defaults={
                    "name": "FieldSense Operations Hub Connector",
                    "description": "Integration connector for FieldSense Operations Hub field force tracking and mobile workforce activities.",
                    "product": product,
                    "version": "1.0.0",
                    "status": ConnectorStatus.ACTIVE,
                    "capabilities": ["sso_launch", "user_mapping"],
                },
            )
            if not conn_created and (connector.product_id != product.id or connector.status != ConnectorStatus.ACTIVE):
                connector.product = product
                connector.status = ConnectorStatus.ACTIVE
                connector.save(update_fields=["product", "status"])
            self.stdout.write(f"Integration Connector: {connector.code} ({'created' if conn_created else 'exists'})")

            # 5. Bind ConnectorInstance for specified organization or all active orgs
            target_orgs = []
            if options.get("organization"):
                org_val = options["organization"].strip()
                org = Organization.objects.filter(code=org_val).first() or Organization.objects.filter(id=org_val).first()
                if not org:
                    raise CommandError(f"Organization '{org_val}' not found.")
                target_orgs.append(org)
            elif options.get("bind_all_active_orgs"):
                target_orgs = list(Organization.objects.filter(status="active"))
            else:
                default_org = Organization.objects.filter(status="active").first()
                if default_org:
                    target_orgs.append(default_org)

            for org in target_orgs:
                instance, inst_created = ConnectorInstance.objects.get_or_create(
                    connector=connector,
                    organization=org,
                    defaults={
                        "label": f"FieldSense Operations Hub - {org.name}",
                        "credential_ref": f"vault://tenant/{org.code}/fieldsense",
                        "status": InstanceStatus.ACTIVE,
                    },
                )
                if not inst_created and instance.status != InstanceStatus.ACTIVE:
                    instance.status = InstanceStatus.ACTIVE
                    instance.save(update_fields=["status"])
                self.stdout.write(f"Connector Instance: {instance.label} for org '{org.code}' ({'created' if inst_created else 'active'})")

        self.stdout.write(
            self.style.SUCCESS(
                f"\nFieldSense Operations Hub SSO client registration complete!\n"
                f"  Product: {product.name} ({product.code})\n"
                f"  Client Identifier: {sso_client.client_identifier}\n"
                f"  Audience: {sso_client.audience}\n"
                f"  Callback URI: {sso_client.callback_uri}\n"
                f"  Active: {sso_client.is_active}\n"
            )
        )
