"""Idempotent setup command for Phase 5F: HRMS and CRM Integrations.

Registers catalog products and generic connectors:
1. HRMS:
   - Product: code='hrms', name='Human Resources Management System'
   - Connector: code='hrms_connector', name='Human Resources Management System Connector'
2. CRM:
   - Product: code='crm', name='Customer Relationship Management'
   - Connector: code='crm_connector', name='Customer Relationship Management Connector'

CRITICAL RULE:
- Does NOT create any ConnectorInstance records for HRMS or CRM.
- Existing LMS, WMS, VMS, and WorkHub products, connectors, and instances remain untouched.
"""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.integration_hub.models import (
    ConnectorStatus,
    IntegrationConnector,
)
from apps.product_registry.models import Product, ProductStatus

User = get_user_model()


class Command(BaseCommand):
    help = "Idempotently register HRMS and CRM products and connectors (Phase 5F)."

    def handle(self, *args, **options):
        self.stdout.write("Starting Phase 5F Catalog & Connector Registration...")

        system_user = (
            User.objects.filter(is_superuser=True).first()
            or User.objects.filter(is_staff=True).first()
            or User.objects.first()
        )
        if not system_user:
            self.stderr.write(self.style.ERROR("No user found in database to attribute product creation."))
            return

        products_spec = [
            {
                "code": "hrms",
                "name": "Human Resources Management System",
                "description": "Human resources, workforce identity, and personnel management platform.",
                "connector_code": "hrms_connector",
                "connector_name": "Human Resources Management System Connector",
            },
            {
                "code": "crm",
                "name": "Customer Relationship Management",
                "description": "Customer relationship, client engagement, and sales pipeline platform.",
                "connector_code": "crm_connector",
                "connector_name": "Customer Relationship Management Connector",
            },
        ]

        with transaction.atomic():
            for spec in products_spec:
                # 1. Product Registry
                product, p_created = Product.objects.get_or_create(
                    code=spec["code"],
                    defaults={
                        "name": spec["name"],
                        "description": spec["description"],
                        "status": ProductStatus.ACTIVE,
                        "created_by": system_user,
                        "updated_by": system_user,
                    },
                )
                if not p_created and product.status != ProductStatus.ACTIVE:
                    product.status = ProductStatus.ACTIVE
                    product.save(update_fields=["status"])

                self.stdout.write(
                    f"Product {'created' if p_created else 'exists'}: {product.name} [{product.code}] ({product.id})"
                )

                # 2. Integration Connector Registry
                connector, c_created = IntegrationConnector.objects.get_or_create(
                    code=spec["connector_code"],
                    defaults={
                        "name": spec["connector_name"],
                        "description": spec["description"],
                        "product": product,
                        "version": "1.0.0",
                        "status": ConnectorStatus.ACTIVE,
                    },
                )
                if not c_created:
                    updated_fields = []
                    if connector.product != product:
                        connector.product = product
                        updated_fields.append("product")
                    if connector.status != ConnectorStatus.ACTIVE:
                        connector.status = ConnectorStatus.ACTIVE
                        updated_fields.append("status")
                    if updated_fields:
                        connector.save(update_fields=updated_fields)

                self.stdout.write(
                    f"Connector {'created' if c_created else 'exists'}: {connector.name} [{connector.code}]"
                )

        self.stdout.write(
            self.style.SUCCESS(
                "Phase 5F setup complete: HRMS and CRM registered. Zero ConnectorInstances created."
            )
        )
