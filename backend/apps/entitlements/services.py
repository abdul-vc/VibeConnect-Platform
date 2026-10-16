"""Entitlements Domain Services (Phase 6A Stage 3).

Provides transactional domain services for creating and managing OrganizationProductEntitlement
records, ensuring strict invariants, PostgreSQL row locking, and canonical Integration Hub
lifecycle event dispatch.
"""

import logging
from typing import Any
import uuid

from django.db import transaction
from django.utils import timezone

from apps.auditlog.models import AuditAction, AuditOperationSource, AuditTargetType
from apps.auditlog.services import record_audit_event
from apps.entitlements.models import (
    EntitlementStatus,
    OrganizationProductEntitlement,
)
from apps.integration_hub.lifecycle_service import (
    handle_tenant_lms_entitlement_activated,
    is_lms_product,
)
from apps.organizations.models import Organization, OrganizationStatus
from apps.product_registry.models import Product, ProductStatus

logger = logging.getLogger(__name__)


class EntitlementServiceError(Exception):
    """Base exception for entitlement domain service errors."""

    def __init__(self, message: str, code: str = "ENTITLEMENT_SERVICE_ERROR"):
        super().__init__(message)
        self.message = message
        self.code = code


class EntitlementAlreadyExistsError(EntitlementServiceError):
    def __init__(self, message: str = "An active, draft, or suspended entitlement already exists for this organization and product."):
        super().__init__(message, code="ENTITLEMENT_ALREADY_EXISTS")


class OrganizationNotActiveError(EntitlementServiceError):
    def __init__(self, message: str = "Organization must be in active status to receive product access."):
        super().__init__(message, code="ORGANIZATION_NOT_ACTIVE")


class ProductNotActiveError(EntitlementServiceError):
    def __init__(self, message: str = "Product must be in active status to be entitled to an organization."):
        super().__init__(message, code="PRODUCT_NOT_ACTIVE")


def create_or_activate_entitlement(
    *,
    organization: Organization,
    product: Product,
    actor: Any,
    source: str = "canonical_entitlement_service",
) -> OrganizationProductEntitlement:
    """Canonical domain service to create and immediately activate an OrganizationProductEntitlement.

    Guarantees:
    - Atomicity and select_for_update locking on Organization and Product.
    - Prevents duplicates against org_product_open_entitlement_uniq.
    - Enforces both Organization and Product are ACTIVE.
    - Records append-only audit event.
    - Automatically invokes downstream integration lifecycle hooks (e.g. LMS M2M provisioning)
      without direct caller coupling to Integration Hub internals.
    """
    with transaction.atomic():
        locked_org = Organization.objects.select_for_update().get(pk=organization.pk)
        locked_prod = Product.objects.select_for_update().get(pk=product.pk)

        if locked_org.status != OrganizationStatus.ACTIVE:
            raise OrganizationNotActiveError(
                f"Organization '{locked_org.code}' is not active (status={locked_org.status})."
            )

        if locked_prod.status != ProductStatus.ACTIVE:
            raise ProductNotActiveError(
                f"Product '{locked_prod.code}' is not active (status={locked_prod.status})."
            )

        existing = (
            OrganizationProductEntitlement.objects.select_for_update()
            .filter(organization=locked_org, product=locked_prod)
            .exclude(status=EntitlementStatus.REVOKED)
            .first()
        )
        if existing:
            raise EntitlementAlreadyExistsError(
                f"Organization '{locked_org.code}' already has an open entitlement for '{locked_prod.code}' (status={existing.status})."
            )

        entitlement = OrganizationProductEntitlement.objects.create(
            organization=locked_org,
            product=locked_prod,
            status=EntitlementStatus.DRAFT,
            created_by=actor,
            updated_by=actor,
        )

        record_audit_event(
            action=AuditAction.ENTITLEMENT_CREATED,
            target_type=AuditTargetType.ENTITLEMENT,
            target_id=entitlement.id,
            target_repr=f"{locked_org.code} : {locked_prod.code}",
            actor=actor,
            organization_id=entitlement.organization_id,
            operation_source=AuditOperationSource.INTERACTIVE,
            metadata={
                "organization_code": locked_org.code,
                "product_id": str(locked_prod.id),
                "product_code": locked_prod.code,
                "previous_status": None,
                "resulting_status": "draft",
            },
        )

        # Promote to ACTIVE and record status transition
        entitlement.status = EntitlementStatus.ACTIVE
        entitlement.updated_by = actor
        entitlement.save(update_fields=["status", "updated_by"])

        record_audit_event(
            action=AuditAction.ENTITLEMENT_STATUS_CHANGED,
            target_type=AuditTargetType.ENTITLEMENT,
            target_id=entitlement.id,
            target_repr=f"{locked_org.code} : {locked_prod.code}",
            actor=actor,
            organization_id=entitlement.organization_id,
            operation_source=AuditOperationSource.INTERACTIVE,
            metadata={
                "organization_code": locked_org.code,
                "product_id": str(locked_prod.id),
                "product_code": locked_prod.code,
                "previous_status": "draft",
                "resulting_status": "active",
            },
        )

        # Trigger canonical downstream integration lifecycle hook
        if is_lms_product(locked_prod):
            handle_tenant_lms_entitlement_activated(
                locked_org,
                actor=actor,
                source=source,
            )

        return entitlement

