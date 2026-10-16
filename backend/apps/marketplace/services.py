"""Marketplace Domain Services (Phase 6A Stage 3).

Composes product catalog presentation, commercial plan visibility, tenant entitlement overlays,
deterministic integration readiness resolution, and safe product enablement workflows.
"""

import logging
from typing import Any, Optional
import uuid

from django.db import transaction
from django.utils import timezone

from apps.entitlements.models import EntitlementStatus, OrganizationProductEntitlement
from apps.entitlements.services import (
    EntitlementAlreadyExistsError,
    EntitlementServiceError,
    create_or_activate_entitlement,
)
from apps.identity.models import PlatformUser
from apps.integration_hub.lifecycle_service import is_lms_product
from apps.integration_hub.models import ConnectorStatus, IntegrationConnector
from apps.marketplace.models import TenantProductRequest, TenantProductRequestStatus
from apps.organizations.models import (
    MembershipStatus,
    MembershipType,
    Organization,
    OrganizationMembership,
    OrganizationStatus,
)
from apps.plans.models import PlanPrice, PlanProduct, PlanVersion
from apps.product_registry.models import CatalogStatus, Product, ProductStatus
from apps.showcase.models import ProductShowcaseProfile, ShowcaseVisibility

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Domain Exceptions
# ---------------------------------------------------------------------------

class MarketplaceServiceError(Exception):
    """Base exception for marketplace domain operations."""

    def __init__(self, message: str, code: str = "MARKETPLACE_ERROR"):
        super().__init__(message)
        self.message = message
        self.code = code


class TenantAdminRequiredError(MarketplaceServiceError):
    def __init__(self, message: str = "Action requires an active Tenant Administrator role in the organization."):
        super().__init__(message, code="TENANT_ADMIN_REQUIRED")


class CrossTenantAccessError(MarketplaceServiceError):
    def __init__(self, message: str = "Caller does not belong to the requested organization context."):
        super().__init__(message, code="CROSS_TENANT_ACCESS_DENIED")


class IntegrationPendingError(MarketplaceServiceError):
    def __init__(self, message: str = "Downstream integration for this product is pending and not yet operational."):
        super().__init__(message, code="INTEGRATION_PENDING")


class DuplicateTenantProductRequestError(MarketplaceServiceError):
    def __init__(self, message: str = "A pending product adoption request already exists for this organization and product."):
        super().__init__(message, code="DUPLICATE_PRODUCT_REQUEST")


class ProductNotActiveError(MarketplaceServiceError):
    def __init__(self, message: str = "Product is not in active catalog status."):
        super().__init__(message, code="PRODUCT_NOT_ACTIVE")


class ProductNotFoundError(MarketplaceServiceError):
    def __init__(self, message: str = "Active product not found in the catalog."):
        super().__init__(message, code="PRODUCT_NOT_FOUND")


class OrganizationNotActiveError(MarketplaceServiceError):
    def __init__(self, message: str = "Organization must be active to interact with the Marketplace."):
        super().__init__(message, code="ORGANIZATION_NOT_ACTIVE")


class PlanMismatchError(MarketplaceServiceError):
    def __init__(self, message: str = "The requested plan does not belong to the selected product."):
        super().__init__(message, code="PLAN_PRODUCT_MISMATCH")


# ---------------------------------------------------------------------------
# Integration Readiness Resolver
# ---------------------------------------------------------------------------

def is_product_integration_ready(product: Product) -> bool:
    """Determines deterministically if a catalog Product is integration-ready for automated enablement.

    Authoritative Contract:
    - Product must have an ACTIVE IntegrationConnector in integration_hub.
    - Integration Hub must possess an operational adapter (currently strictly LMS via is_lms_product).
    - Unintegrated products (WMS, VMS, WorkHub, HRMS, CRM) evaluate to False.
    """
    if not product or product.status != ProductStatus.ACTIVE:
        return False

    has_active_connector = IntegrationConnector.objects.filter(
        product=product,
        status=ConnectorStatus.ACTIVE,
    ).exists()

    if not has_active_connector:
        return False

    return is_lms_product(product)


# ---------------------------------------------------------------------------
# Tenant Admin Guard
# ---------------------------------------------------------------------------

def _require_active_tenant_admin(organization: Organization, actor: Any) -> None:
    """Verifies actor is an active Tenant Administrator or Platform Owner for the target organization."""
    if not actor or not getattr(actor, "is_authenticated", False) or not getattr(actor, "is_active", False):
        raise TenantAdminRequiredError("Actor must be an active, authenticated platform user.")

    if getattr(actor, "is_platform_owner", False):
        return

    membership = OrganizationMembership.objects.filter(
        organization=organization,
        user=actor,
        status=MembershipStatus.ACTIVE,
    ).first()

    if not membership:
        raise CrossTenantAccessError("Requester is not a member of the target organization.")

    if membership.membership_type != MembershipType.TENANT_ADMIN:
        raise TenantAdminRequiredError("Requester is not a Tenant Administrator of the target organization.")


# ---------------------------------------------------------------------------
# Request Domain Service
# ---------------------------------------------------------------------------

def create_tenant_product_request(
    *,
    organization: Organization,
    requester: Any,
    product: Product,
    requested_plan: Optional[PlanVersion] = None,
    notes: str = "",
) -> TenantProductRequest:
    """Creates a new TenantProductRequest for organization-level product adoption or enterprise tier review."""
    _require_active_tenant_admin(organization, requester)

    if organization.status != OrganizationStatus.ACTIVE:
        raise OrganizationNotActiveError(f"Organization '{organization.code}' is not active.")

    if product.status != ProductStatus.ACTIVE:
        raise ProductNotActiveError(f"Product '{product.code}' is not active in the catalog.")

    if requested_plan is not None:
        plan_belongs = PlanProduct.objects.filter(
            plan_version=requested_plan,
            product=product,
        ).exists()
        if not plan_belongs:
            raise PlanMismatchError(
                f"PlanVersion '{requested_plan.id}' does not include Product '{product.code}'."
            )

    with transaction.atomic():
        # Check for open duplicate pending request
        has_pending = TenantProductRequest.objects.filter(
            organization=organization,
            product=product,
            status=TenantProductRequestStatus.PENDING,
        ).exists()
        if has_pending:
            raise DuplicateTenantProductRequestError()

        req = TenantProductRequest.objects.create(
            organization=organization,
            product=product,
            requested_plan=requested_plan,
            requester=requester,
            status=TenantProductRequestStatus.PENDING,
            notes=str(notes or "").strip(),
        )

        return req


# ---------------------------------------------------------------------------
# Marketplace Catalog Service
# ---------------------------------------------------------------------------

def get_marketplace_catalog(
    *,
    organization: Organization,
    user: Optional[Any] = None,
) -> list[dict[str, Any]]:
    """Composes dynamic Marketplace catalog data for an authenticated organization context.

    Reuses Product, ProductShowcaseProfile, PlanVersion, PlanPrice, OrganizationProductEntitlement,
    and TenantProductRequest without redundant data duplication.
    """
    if organization.status != OrganizationStatus.ACTIVE:
        raise OrganizationNotActiveError(f"Organization '{organization.code}' is not active.")

    products = (
        Product.objects.filter(status=ProductStatus.ACTIVE)
        .prefetch_related("showcase_profile", "showcase_profile__media")
        .order_by("name")
    )

    # Pre-fetch existing open entitlements for this organization
    open_entitlements = {
        ent.product_id: ent.status
        for ent in OrganizationProductEntitlement.objects.filter(
            organization=organization
        ).exclude(status=EntitlementStatus.REVOKED)
    }

    # Pre-fetch pending adoption requests for this organization
    pending_requests = {
        req.product_id: req.id
        for req in TenantProductRequest.objects.filter(
            organization=organization,
            status=TenantProductRequestStatus.PENDING,
        )
    }

    catalog = []
    for prod in products:
        is_ready = is_product_integration_ready(prod)
        integration_status = "operational" if is_ready else "pending"

        ent_status = open_entitlements.get(prod.id)
        has_pending_req = prod.id in pending_requests

        if ent_status == EntitlementStatus.ACTIVE:
            tenant_state = "installed"
            can_enable = False
            can_request = False
        elif ent_status in (EntitlementStatus.DRAFT, EntitlementStatus.SUSPENDED):
            tenant_state = ent_status
            can_enable = False
            can_request = False
        elif has_pending_req:
            tenant_state = "request_pending"
            can_enable = False
            can_request = False
        elif is_ready:
            tenant_state = "available"
            can_enable = True
            can_request = True
        else:
            tenant_state = "integration_pending"
            can_enable = False
            can_request = True

        # Showcase metadata
        showcase = getattr(prod, "showcase_profile", None)
        tagline = showcase.tagline if showcase else ""
        overview = showcase.overview if showcase else prod.description
        media_list = []
        if showcase:
            media_list = [
                {
                    "id": str(m.id),
                    "media_type": m.media_type,
                    "title": m.title,
                    "url": m.url,
                    "display_order": m.display_order,
                }
                for m in showcase.media.all().order_by("display_order")
            ]
        icon_url = media_list[0]["url"] if media_list else None

        # Plan tiers
        plan_links = PlanProduct.objects.filter(
            product=prod,
            plan_version__status="active",
        ).select_related("plan_version", "plan_version__plan")

        plans_data = []
        for pl in plan_links:
            pv = pl.plan_version
            prices = PlanPrice.objects.filter(plan_version=pv)
            plans_data.append({
                "plan_version_id": str(pv.id),
                "plan_name": pv.plan.name,
                "plan_code": pv.plan.code,
                "version": pv.version,
                "is_public": pv.plan.is_public,
                "prices": [
                    {
                        "currency": pr.currency,
                        "amount": str(pr.amount),
                        "billing_interval": pr.billing_interval,
                    }
                    for pr in prices
                ],
            })

        catalog.append({
            "id": str(prod.id),
            "product_id": str(prod.id),
            "code": prod.code,
            "name": prod.name,
            "description": prod.description,
            "tagline": tagline,
            "overview": overview,
            "icon_url": icon_url,
            "media": media_list,
            "integration_status": integration_status,
            "tenant_state": tenant_state,
            "can_enable": can_enable,
            "can_request": can_request,
            "plans_count": len(plans_data),
            "plans": plans_data,
        })

    return catalog


# ---------------------------------------------------------------------------
# Enablement Service
# ---------------------------------------------------------------------------

def enable_marketplace_product(
    *,
    organization: Organization,
    product: Product,
    actor: Any,
) -> OrganizationProductEntitlement:
    """Enables an integration-ready product for an organization in self-service mode.

    Invariants:
    - Actor must be an active Tenant Administrator in the organization.
    - Product must be integration-ready (currently strictly LMS).
    - Blocks unintegrated products (WMS, VMS, WorkHub, HRMS, CRM) with INTEGRATION_PENDING.
    - Delegates entitlement creation to canonical create_or_activate_entitlement.
    - Resolves any pending TenantProductRequest to 'approved'.
    - Relies exclusively on canonical lifecycle hook for downstream provisioning.
    """
    _require_active_tenant_admin(organization, actor)

    if organization.status != OrganizationStatus.ACTIVE:
        raise OrganizationNotActiveError(f"Organization '{organization.code}' is not active.")

    if product.status != ProductStatus.ACTIVE:
        raise ProductNotActiveError(f"Product '{product.code}' is not active.")

    if not is_product_integration_ready(product):
        raise IntegrationPendingError(
            f"Downstream integration for product '{product.code}' is pending. "
            "Self-service enablement is not available until integration is completed."
        )

    with transaction.atomic():
        try:
            entitlement = create_or_activate_entitlement(
                organization=organization,
                product=product,
                actor=actor,
                source="marketplace_self_service_enable",
            )
        except EntitlementAlreadyExistsError:
            # Idempotent: resolve existing open entitlement if already ACTIVE
            entitlement = (
                OrganizationProductEntitlement.objects.select_for_update()
                .filter(organization=organization, product=product)
                .exclude(status=EntitlementStatus.REVOKED)
                .first()
            )
            if not entitlement or entitlement.status != EntitlementStatus.ACTIVE:
                raise

        # Transition any pending adoption request to approved
        TenantProductRequest.objects.filter(
            organization=organization,
            product=product,
            status=TenantProductRequestStatus.PENDING,
        ).update(status=TenantProductRequestStatus.APPROVED, updated_at=timezone.now())

        return entitlement


# ---------------------------------------------------------------------------
# Stage 4 Resolution & Detail Services
# ---------------------------------------------------------------------------

def resolve_active_product(code_or_id: str) -> Product:
    """Resolves an active catalog product by UUID or alphanumeric code."""
    clean = str(code_or_id or "").strip()
    if not clean:
        raise ProductNotFoundError("Product code or ID must be specified.")

    prod = None
    try:
        val_uuid = uuid.UUID(clean)
        prod = (
            Product.objects.filter(id=val_uuid, status=ProductStatus.ACTIVE)
            .prefetch_related("showcase_profile", "showcase_profile__media")
            .first()
        )
    except (ValueError, TypeError):
        pass

    if not prod:
        prod = (
            Product.objects.filter(code__iexact=clean, status=ProductStatus.ACTIVE)
            .prefetch_related("showcase_profile", "showcase_profile__media")
            .first()
        )

    if not prod:
        raise ProductNotFoundError(f"Active product '{code_or_id}' not found in the catalog.")

    return prod


def get_marketplace_product_detail(
    *,
    organization: Organization,
    product: Product,
    user: Optional[Any] = None,
) -> dict[str, Any]:
    """Retrieves full tenant-aware product detail for the marketplace.

    Includes showcase profile, active modules and features, eligible plan versions/prices,
    current tenant entitlement state, and actionability flags.
    """
    if organization.status != OrganizationStatus.ACTIVE:
        raise OrganizationNotActiveError(f"Organization '{organization.code}' is not active.")

    if product.status != ProductStatus.ACTIVE:
        raise ProductNotActiveError(f"Product '{product.code}' is not active.")

    is_ready = is_product_integration_ready(product)
    integration_status = "operational" if is_ready else "pending"

    entitlement = (
        OrganizationProductEntitlement.objects.filter(organization=organization, product=product)
        .exclude(status=EntitlementStatus.REVOKED)
        .first()
    )

    pending_req = TenantProductRequest.objects.filter(
        organization=organization,
        product=product,
        status=TenantProductRequestStatus.PENDING,
    ).first()

    if entitlement and entitlement.status == EntitlementStatus.ACTIVE:
        tenant_state = "installed"
        can_enable = False
        can_request = False
    elif entitlement and entitlement.status in (EntitlementStatus.DRAFT, EntitlementStatus.SUSPENDED):
        tenant_state = entitlement.status
        can_enable = False
        can_request = False
    elif pending_req:
        tenant_state = "request_pending"
        can_enable = False
        can_request = False
    elif is_ready:
        tenant_state = "available"
        can_enable = True
        can_request = True
    else:
        tenant_state = "integration_pending"
        can_enable = False
        can_request = True

    # Showcase metadata
    showcase = getattr(product, "showcase_profile", None)
    tagline = showcase.tagline if showcase else ""
    overview = showcase.overview if showcase else product.description
    media_list = []
    if showcase:
        media_list = [
            {
                "id": str(m.id),
                "media_type": m.media_type,
                "title": m.title,
                "url": m.url,
                "display_order": m.display_order,
            }
            for m in showcase.media.all().order_by("display_order")
        ]
    icon_url = media_list[0]["url"] if media_list else None

    # Published modules and features
    modules_data = []
    for mod in product.modules.filter(status=CatalogStatus.ACTIVE).order_by("display_order", "id"):
        features_data = [
            {
                "id": str(feat.id),
                "code": feat.code,
                "name": feat.name,
                "description": feat.description,
            }
            for feat in mod.features.filter(status=CatalogStatus.ACTIVE).order_by("display_order", "id")
        ]
        modules_data.append({
            "id": str(mod.id),
            "code": mod.code,
            "name": mod.name,
            "description": mod.description,
            "features": features_data,
        })

    # Plan tiers
    plan_links = (
        PlanProduct.objects.filter(product=product, plan_version__status="active")
        .select_related("plan_version", "plan_version__plan")
        .prefetch_related("plan_version__prices")
    )

    plans_data = []
    for pl in plan_links:
        pv = pl.plan_version
        prices = pv.prices.all().order_by("currency", "billing_interval")
        plans_data.append({
            "plan_version_id": str(pv.id),
            "plan_id": str(pv.plan.id),
            "plan_name": pv.plan.name,
            "plan_code": pv.plan.code,
            "version": pv.version,
            "is_public": pv.plan.is_public,
            "prices": [
                {
                    "currency": pr.currency,
                    "amount": str(pr.amount),
                    "billing_interval": pr.billing_interval,
                }
                for pr in prices
            ],
        })

    entitlement_data = None
    if entitlement:
        entitlement_data = {
            "id": str(entitlement.id),
            "status": entitlement.status,
            "created_at": entitlement.created_at.isoformat(),
            "updated_at": entitlement.updated_at.isoformat(),
        }

    pending_request_data = None
    if pending_req:
        pending_request_data = {
            "id": str(pending_req.id),
            "status": pending_req.status,
            "requested_plan_id": str(pending_req.requested_plan_id) if pending_req.requested_plan_id else None,
            "notes": pending_req.notes,
            "created_at": pending_req.created_at.isoformat(),
        }

    return {
        "id": str(product.id),
        "code": product.code,
        "name": product.name,
        "description": product.description,
        "tagline": tagline,
        "overview": overview,
        "icon_url": icon_url,
        "media": media_list,
        "integration_status": integration_status,
        "tenant_state": tenant_state,
        "can_enable": can_enable,
        "can_request": can_request,
        "modules": modules_data,
        "plans_count": len(plans_data),
        "plans": plans_data,
        "entitlement": entitlement_data,
        "pending_request": pending_request_data,
    }


def get_public_marketplace_catalog() -> list[dict[str, Any]]:
    """Composes globally public marketplace catalog for unauthenticated discovery.

    Zero tenant state, zero entitlement info, zero actionability flags.
    """
    products = (
        Product.objects.filter(status=ProductStatus.ACTIVE)
        .prefetch_related("showcase_profile", "showcase_profile__media")
        .order_by("name")
    )

    catalog = []
    for prod in products:
        showcase = getattr(prod, "showcase_profile", None)
        if showcase and showcase.visibility == ShowcaseVisibility.PUBLISHED:
            tagline = showcase.tagline
            overview = showcase.overview if showcase.overview else prod.description
            media_list = [
                {
                    "id": str(m.id),
                    "media_type": m.media_type,
                    "title": m.title,
                    "url": m.url,
                    "display_order": m.display_order,
                }
                for m in showcase.media.all().order_by("display_order")
            ]
        else:
            tagline = ""
            overview = prod.description
            media_list = []
        icon_url = media_list[0]["url"] if media_list else None

        plan_links = (
            PlanProduct.objects.filter(
                product=prod,
                plan_version__status="active",
                plan_version__plan__is_public=True,
            )
            .select_related("plan_version", "plan_version__plan")
            .prefetch_related("plan_version__prices")
        )

        plans_data = []
        for pl in plan_links:
            pv = pl.plan_version
            prices = pv.prices.all().order_by("currency", "billing_interval")
            plans_data.append({
                "plan_version_id": str(pv.id),
                "plan_name": pv.plan.name,
                "plan_code": pv.plan.code,
                "version": pv.version,
                "prices": [
                    {
                        "currency": pr.currency,
                        "amount": str(pr.amount),
                        "billing_interval": pr.billing_interval,
                    }
                    for pr in prices
                ],
            })

        catalog.append({
            "id": str(prod.id),
            "code": prod.code,
            "name": prod.name,
            "description": prod.description,
            "tagline": tagline,
            "overview": overview,
            "icon_url": icon_url,
            "media": media_list,
            "plans_count": len(plans_data),
            "plans": plans_data,
        })

    return catalog
