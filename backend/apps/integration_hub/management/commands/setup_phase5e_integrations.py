"""Idempotent setup command for Phase 5E: WMS, VMS, and WorkHub Integrations.

Registers:
1. Catalog products in Product Registry:
   - wms (Warehouse Management System)
   - vms (Visitor Management System)
   - workhub (WorkHub)
2. Generic IntegrationConnector records in Integration Hub:
   - wms_connector
   - vms_connector
   - workhub_connector

CRITICAL RULE:
- Does NOT create any ConnectorInstance records for WMS, VMS, or WorkHub.
- Existing LMS integration and LMS ConnectorInstance remain completely untouched.
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
    help = "Idempotently register WMS, VMS, and WorkHub products and connectors (Phase 5E)."

    def handle(self, *args, **options):
        self.stdout.write("Starting Phase 5E Catalog & Connector Registration...")

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
                "code": "wms",
                "name": "Warehouse Management System",
                "description": "Warehouse and inventory logistics platform.",
                "connector_code": "wms_connector",
                "connector_name": "Warehouse Management System Connector",
            },
            {
                "code": "vms",
                "name": "Visitor Management System",
                "description": "Visitor, site check-in, and badge security platform.",
                "connector_code": "vms_connector",
                "connector_name": "Visitor Management System Connector",
            },
            {
                "code": "workhub",
                "name": "WorkHub",
                "description": "Enterprise productivity, collaboration, and task hub.",
                "connector_code": "workhub_connector",
                "connector_name": "WorkHub Connector",
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
                "Phase 5E setup complete: WMS, VMS, and WorkHub registered. Zero ConnectorInstances created."
            )
        )
