"""Idempotent seed/setup command for LMS Pilot Integration (Phase 5C).

Configures:
1. IntegrationConnector for the existing LMS product.
2. ConnectorInstance for the designated pilot tenant organization (test-org-shell).
3. ProductSsoClient for LMS SSO launch and validation.
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.integration_hub.models import (
    ConnectorInstance,
    ConnectorStatus,
    InstanceStatus,
    IntegrationConnector,
    ProductSsoClient,
)
from apps.organizations.models import Organization
from apps.product_registry.models import CatalogStatus, Product, ProductModule


class Command(BaseCommand):
    help = "Idempotently configure LMS Pilot Integration Connector, Instance, and SSO Client."

    def handle(self, *args, **options):
        self.stdout.write("Configuring LMS Pilot Integration...")

        with transaction.atomic():
            # 1. Locate existing LMS Product
            product = Product.objects.filter(code="lms").first()
            if not product:
                self.stderr.write(self.style.ERROR("LMS product with code 'lms' not found in database."))
                return

            self.stdout.write(f"Found LMS Product: {product.name} ({product.id})")

            # 2. Ensure canonical LMS Core module exists and is active
            module, m_created = ProductModule.objects.get_or_create(
                product=product,
                code="lms_core",
                defaults={
                    "name": "LMS Core Module",
                    "description": "Core LMS module for courses, assessments, and learner delivery.",
                    "status": CatalogStatus.ACTIVE,
                    "created_by": product.created_by,
                    "updated_by": product.updated_by,
                },
            )
            if not m_created and module.status != CatalogStatus.ACTIVE:
                module.status = CatalogStatus.ACTIVE
                module.save(update_fields=["status"])
            self.stdout.write(f"Product Module {'created' if m_created else 'exists'}: {module.code} ({module.status})")

            # 3. Locate designated pilot organization
            pilot_org = Organization.objects.filter(code="test-org-shell").first()
            if not pilot_org:
                pilot_org = Organization.objects.filter(status="active").first()
            if not pilot_org:
                self.stderr.write(self.style.ERROR("No active organization found to bind pilot."))
                return

            self.stdout.write(f"Designated Pilot Organization: {pilot_org.name} ({pilot_org.code})")

            # 4. Create or update IntegrationConnector
            connector, c_created = IntegrationConnector.objects.get_or_create(
                code="lms_connector",
                defaults={
                    "name": "Learning Management System Connector",
                    "product": product,
                    "version": "1.0.0",
                    "status": ConnectorStatus.ACTIVE,
                },
            )
            if not c_created and (connector.product != product or connector.status != ConnectorStatus.ACTIVE):
                connector.product = product
                connector.status = ConnectorStatus.ACTIVE
                connector.save(update_fields=["product", "status"])
            self.stdout.write(f"Connector {'created' if c_created else 'exists'}: {connector.code}")

            # 4. Create or update ConnectorInstance
            instance, i_created = ConnectorInstance.objects.get_or_create(
                connector=connector,
                organization=pilot_org,
                defaults={
                    "label": "Pilot LMS Instance",
                    "credential_ref": f"vault://tenant/{pilot_org.code}/lms",
                    "status": InstanceStatus.ACTIVE,
                },
            )
            if not i_created and instance.status != InstanceStatus.ACTIVE:
                instance.status = InstanceStatus.ACTIVE
                instance.save(update_fields=["status"])
            self.stdout.write(f"Connector Instance {'created' if i_created else 'exists'}: {instance.label}")

            # 5. Create or update ProductSsoClient
            sso_client, s_created = ProductSsoClient.objects.get_or_create(
                product=product,
                defaults={
                    "client_identifier": "pilot_lms_client",
                    "audience": "vibeconnect-lms",
                    "callback_uri": "http://localhost:8080/sso/callback",
                    "public_key_reference": "vault://keys/pilot-lms-public-key",
                    "is_active": True,
                },
            )
            if not s_created:
                updated_fields = []
                if not sso_client.is_active:
                    sso_client.is_active = True
                    updated_fields.append("is_active")
                if sso_client.callback_uri != "http://localhost:8080/sso/callback":
                    sso_client.callback_uri = "http://localhost:8080/sso/callback"
                    updated_fields.append("callback_uri")
                if updated_fields:
                    sso_client.save(update_fields=updated_fields)
            self.stdout.write(f"Product SSO Client {'created' if s_created else 'exists'}: {sso_client.client_identifier} (callback={sso_client.callback_uri})")

        self.stdout.write(self.style.SUCCESS("LMS Pilot Integration successfully configured!"))
