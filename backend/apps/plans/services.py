"""VibeConnect Phase 2B Plans & Pricing Domain Services.

Provides transactionally isolated, pessimistic-locking domain services for:
- Plan creation and presentation updates
- PlanVersion serialized allocation, draft mutation, cloning, activation readiness,
  supersession activation, and manual retirement
- PlanPrice, PlanProduct, PlanModule, PlanCapability, and PlanQuota draft mutations
- Deterministic cascade-removal auditing
"""

from decimal import Decimal
import re
from typing import Any
import uuid

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.auditlog.models import AuditAction, AuditOperationSource, AuditTargetType
from apps.auditlog.services import record_audit_event
from apps.plans.models import (
    BillingInterval,
    Plan,
    PlanCapability,
    PlanCurrency,
    PlanModule,
    PlanPrice,
    PlanProduct,
    PlanQuota,
    PlanVersion,
    PlanVersionStatus,
)
from apps.product_registry.models import (
    CatalogStatus,
    Product,
    ProductCapability,
    ProductFeature,
    ProductModule,
    ProductStatus,
)


def _validate_actor(actor: Any) -> None:
    if not actor or not getattr(actor, "is_authenticated", False) or not getattr(actor, "is_active", False):
        raise ValidationError("Actor must be an active, authenticated platform user.")
    if not getattr(actor, "is_platform_owner", False):
        raise ValidationError("Actor must possess platform owner privileges.")


def _get_and_lock_draft_version(plan_version_id: uuid.UUID | str) -> PlanVersion:
    """Acquires canonical top-down pessimistic locks (Plan -> PlanVersion) and verifies Draft status."""
    pv_initial = PlanVersion.objects.get(pk=plan_version_id)
    plan = Plan.objects.select_for_update().get(pk=pv_initial.plan_id)
    pv = PlanVersion.objects.select_for_update().get(pk=plan_version_id)
    pv.plan = plan
    if pv.status != PlanVersionStatus.DRAFT:
        raise ValidationError(f"Mutation rejected: PlanVersion '{pv.id}' is in status '{pv.status}', not 'draft'.")
    return pv


def _validate_price_currency(currency: Any) -> str:
    """Validates currency strictly against the model enum single source of truth."""
    if not isinstance(currency, str) or currency not in PlanCurrency.values:
        raise ValidationError(
            f"Currency '{currency}' is invalid. Approved currencies: {list(PlanCurrency.values)}."
        )
    return currency


def _validate_canonical_price_amount(amount: Any) -> tuple[Decimal, str]:
    """Enforces strict canonical price amount contract (string, exact 2-decimals, range)."""
    if not isinstance(amount, str):
        raise ValidationError(f"Price amount must be provided as a string, got {type(amount).__name__}.")
    if not re.match(r"^(?:0|[1-9][0-9]*)\.[0-9]{2}$", amount):
        raise ValidationError(
            f"Price amount '{amount}' has invalid canonical format. "
            "Must be a non-negative string matching '^(?:0|[1-9][0-9]*)\\.[0-9]{2}$' with no leading zeros or signs."
        )
    dec = Decimal(amount)
    if dec < Decimal("0.00") or dec > Decimal("9999999999.99"):
        raise ValidationError("Price amount must be between '0.00' and '9999999999.99'.")
    return dec, amount


# ---------------------------------------------------------------------------
# Plan Family Services
# ---------------------------------------------------------------------------

def create_plan(
    *,
    code: str,
    name: str,
    description: str = "",
    actor: Any,
) -> tuple[Plan, PlanVersion]:
    """Atomically creates a Plan and initial Draft Version 1 with ordered audit events."""
    _validate_actor(actor)
    code = code.strip().lower()
    name = name.strip()
    description = (description or "").strip()

    with transaction.atomic():
        plan = Plan(
            code=code,
            name=name,
            description=description,
            created_by=actor,
            updated_by=actor,
        )
        plan.full_clean()
        plan.save()

        pv = PlanVersion(
            plan=plan,
            version=1,
            status=PlanVersionStatus.DRAFT,
            change_summary="Initial version",
            created_by=actor,
            updated_by=actor,
        )
        pv.full_clean()
        pv.save()

        # Audit events in required order: plan_created, then plan_version_created
        record_audit_event(
            action=AuditAction.PLAN_CREATED,
            target_type=AuditTargetType.PLAN,
            target_id=plan.id,
            target_repr=f"{plan.name} ({plan.code})",
            actor=actor,
            organization_id=None,
            operation_source=AuditOperationSource.INTERACTIVE,
            metadata={"code": plan.code, "name": plan.name, "initial_version": 1},
        )

        record_audit_event(
            action=AuditAction.PLAN_VERSION_CREATED,
            target_type=AuditTargetType.PLAN_VERSION,
            target_id=pv.id,
            target_repr=f"{plan.code} v{pv.version}",
            actor=actor,
            organization_id=None,
            operation_source=AuditOperationSource.INTERACTIVE,
            metadata={
                "plan_id": str(plan.id),
                "plan_code": plan.code,
                "version": pv.version,
                "status": "draft",
            },
        )

        return plan, pv


def update_plan(
    *,
    plan_id: uuid.UUID | str,
    name: str | None = None,
    description: str | None = None,
    code: str | None = None,
    is_public: bool | None = None,
    actor: Any,
) -> Plan:
    """Updates Plan presentation fields. Code is strictly immutable."""
    _validate_actor(actor)

    with transaction.atomic():
        plan = Plan.objects.select_for_update().get(pk=plan_id)

        if code is not None and code.strip().lower() != plan.code:
            raise ValidationError("Plan code is permanently immutable and cannot be updated.")

        prev_name = plan.name
        prev_description = plan.description
        prev_is_public = plan.is_public

        if name is not None:
            plan.name = name.strip()
        if description is not None:
            plan.description = description.strip()

        if is_public is not None and is_public != plan.is_public:
            if is_public:
                active_v = plan.versions.filter(status=PlanVersionStatus.ACTIVE).first()
                if not active_v:
                    raise ValidationError("Cannot make plan public without an active version.")
                readiness = evaluate_activation_readiness(plan_version=active_v)
                if readiness["catalog_health"] != "healthy":
                    raise ValidationError("Cannot make plan public with degraded catalog health.")
            plan.is_public = is_public

        plan.updated_by = actor
        plan.full_clean()
        plan.save()

        name_changed = (prev_name != plan.name)
        description_changed = (prev_description != plan.description)

        metadata = {
            "code": plan.code,
            "name_changed": name_changed,
            "description_changed": description_changed,
            "previous_name": prev_name,
            "resulting_name": plan.name,
            "previous_description": prev_description,
            "resulting_description": plan.description,
        }

        record_audit_event(
            action=AuditAction.PLAN_UPDATED,
            target_type=AuditTargetType.PLAN,
            target_id=plan.id,
            target_repr=f"{plan.name} ({plan.code})",
            actor=actor,
            organization_id=None,
            operation_source=AuditOperationSource.INTERACTIVE,
            metadata=metadata,
        )

        return plan


# ---------------------------------------------------------------------------
# PlanVersion Services
# ---------------------------------------------------------------------------

def create_draft_version(
    *,
    plan_id: uuid.UUID | str,
    change_summary: str = "",
    actor: Any,
) -> PlanVersion:
    """Creates a new blank Draft version using serialized version allocation."""
    _validate_actor(actor)

    with transaction.atomic():
        plan = Plan.objects.select_for_update().get(pk=plan_id)
        existing_versions = list(
            PlanVersion.objects.select_for_update().filter(plan=plan).order_by("version", "id")
        )
        max_v = max((v.version for v in existing_versions), default=0)
        new_version = max_v + 1

        pv = PlanVersion(
            plan=plan,
            version=new_version,
            status=PlanVersionStatus.DRAFT,
            change_summary=(change_summary or "").strip(),
            created_by=actor,
            updated_by=actor,
        )
        pv.full_clean()
        pv.save()

        record_audit_event(
            action=AuditAction.PLAN_VERSION_CREATED,
            target_type=AuditTargetType.PLAN_VERSION,
            target_id=pv.id,
            target_repr=f"{plan.code} v{pv.version}",
            actor=actor,
            organization_id=None,
            operation_source=AuditOperationSource.INTERACTIVE,
            metadata={
                "plan_id": str(plan.id),
                "plan_code": plan.code,
                "version": pv.version,
                "status": "draft",
            },
        )

        return pv


def update_draft_version(
    *,
    plan_version_id: uuid.UUID | str,
    change_summary: str,
    actor: Any,
) -> PlanVersion:
    """Updates Draft change_summary. Rejects Active or Retired versions with zero audit."""
    _validate_actor(actor)

    with transaction.atomic():
        pv_initial = PlanVersion.objects.get(pk=plan_version_id)
        plan = Plan.objects.select_for_update().get(pk=pv_initial.plan_id)
        pv = PlanVersion.objects.select_for_update().select_related("plan").get(pk=plan_version_id)

        if pv.status != PlanVersionStatus.DRAFT:
            raise ValidationError(
                f"Cannot update version '{pv.id}' in status '{pv.status}'. Only draft versions can be modified."
            )

        prev_change_summary = pv.change_summary
        pv.change_summary = (change_summary or "").strip()
        pv.updated_by = actor
        pv.full_clean()
        pv.save()

        change_summary_changed = (prev_change_summary != pv.change_summary)

        record_audit_event(
            action=AuditAction.PLAN_VERSION_UPDATED,
            target_type=AuditTargetType.PLAN_VERSION,
            target_id=pv.id,
            target_repr=f"{plan.code} v{pv.version}",
            actor=actor,
            organization_id=None,
            operation_source=AuditOperationSource.INTERACTIVE,
            metadata={
                "plan_id": str(plan.id),
                "plan_code": plan.code,
                "plan_version_id": str(pv.id),
                "version": pv.version,
                "change_summary_changed": change_summary_changed,
                "previous_change_summary": prev_change_summary,
                "resulting_change_summary": pv.change_summary,
            },
        )

        return pv


def evaluate_activation_readiness(
    *,
    plan_version: PlanVersion | uuid.UUID | str,
) -> dict[str, Any]:
    """Calculates activation readiness and derived catalog health dynamically."""
    if not isinstance(plan_version, PlanVersion):
        pv = PlanVersion.objects.select_related("plan").get(pk=plan_version)
    else:
        pv = plan_version

    prices = list(PlanPrice.objects.filter(plan_version=pv))
    packaged_products = list(PlanProduct.objects.filter(plan_version=pv).select_related("product"))
    packaged_modules = list(
        PlanModule.objects.filter(plan_version=pv).select_related("module", "plan_product__product")
    )
    packaged_capabilities = list(
        PlanCapability.objects.filter(plan_version=pv).select_related(
            "capability__feature__module__product",
            "plan_module__module",
            "plan_module__plan_product__product",
        )
    )
    quotas = list(
        PlanQuota.objects.filter(plan_version=pv).select_related(
            "plan_product", "plan_module", "plan_capability"
        )
    )

    blockers: list[str] = []
    stale_items_map: dict[tuple[str, str], dict[str, str]] = {}

    if len(prices) == 0:
        blockers.append("Plan version requires at least one price before activation.")

    if len(packaged_products) == 0:
        blockers.append("Plan version requires at least one packaged product before activation.")

    # Product checks
    for pp in packaged_products:
        prod = pp.product
        if prod.status != ProductStatus.ACTIVE:
            stale_items_map[("product", str(prod.id))] = {
                "type": "product",
                "id": str(prod.id),
                "code": prod.code,
                "name": prod.name,
                "status": prod.status,
            }
            blockers.append(f"Packaged product '{prod.code}' is not active (status: '{prod.status}').")

    # Module checks
    for pm in packaged_modules:
        mod = pm.module
        if mod.status != CatalogStatus.ACTIVE:
            stale_items_map[("module", str(mod.id))] = {
                "type": "module",
                "id": str(mod.id),
                "code": mod.code,
                "name": mod.name,
                "status": mod.status,
            }
            blockers.append(f"Packaged module '{mod.code}' is not active (status: '{mod.status}').")
        if mod.product_id != pm.plan_product.product_id:
            blockers.append(f"Module '{mod.code}' parent product does not match packaged product.")

    # Capability checks
    for pc in packaged_capabilities:
        cap = pc.capability
        if cap.status != CatalogStatus.ACTIVE:
            stale_items_map[("capability", str(cap.id))] = {
                "type": "capability",
                "id": str(cap.id),
                "code": cap.code,
                "name": cap.name,
                "status": cap.status,
            }
            blockers.append(f"Packaged capability '{cap.code}' is not active (status: '{cap.status}').")

        feat = getattr(cap, "feature", None)
        if feat:
            if feat.status != CatalogStatus.ACTIVE:
                stale_items_map[("feature", str(feat.id))] = {
                    "type": "feature",
                    "id": str(feat.id),
                    "code": feat.code,
                    "name": feat.name,
                    "status": feat.status,
                }
                blockers.append(
                    f"Feature ancestor '{feat.code}' for capability '{cap.code}' is not active (status: '{feat.status}')."
                )
            if feat.module_id != pc.plan_module.module_id:
                blockers.append(
                    f"Capability '{cap.code}' feature module does not match packaged module."
                )

    # Quota target checks
    for q in quotas:
        if q.plan_product and q.plan_product.plan_version_id != pv.id:
            blockers.append(f"Quota '{q.quota_key}' references product target from a different version.")
        if q.plan_module and q.plan_module.plan_version_id != pv.id:
            blockers.append(f"Quota '{q.quota_key}' references module target from a different version.")
        if q.plan_capability and q.plan_capability.plan_version_id != pv.id:
            blockers.append(f"Quota '{q.quota_key}' references capability target from a different version.")

    stale_items = list(stale_items_map.values())
    catalog_health = "degraded" if len(stale_items) > 0 else "healthy"
    is_ready = (len(blockers) == 0)

    return {
        "is_ready": is_ready,
        "blockers": blockers,
        "warnings": [],
        "prices_count": len(prices),
        "products_count": len(packaged_products),
        "catalog_health": catalog_health,
        "stale_items": stale_items,
    }


def clone_plan_version(
    *,
    source_plan_version_id: uuid.UUID | str,
    actor: Any,
    change_summary: str = "",
) -> PlanVersion:
    """Clones a source version into a new Draft version with deep copies and target remapping."""
    _validate_actor(actor)

    with transaction.atomic():
        source_pv_init = PlanVersion.objects.get(pk=source_plan_version_id)
        plan = Plan.objects.select_for_update().get(pk=source_pv_init.plan_id)
        existing_versions = list(
            PlanVersion.objects.select_for_update().filter(plan=plan).order_by("version", "id")
        )
        source_pv = PlanVersion.objects.select_for_update().get(pk=source_plan_version_id)

        new_version = max((v.version for v in existing_versions), default=0) + 1
        new_pv = PlanVersion(
            plan=plan,
            version=new_version,
            status=PlanVersionStatus.DRAFT,
            change_summary=(change_summary or f"Cloned from v{source_pv.version}").strip(),
            created_by=actor,
            updated_by=actor,
        )
        new_pv.full_clean()
        new_pv.save()

        # 1. Copy prices
        source_prices = list(
            PlanPrice.objects.select_for_update()
            .filter(plan_version=source_pv)
            .order_by("currency", "billing_interval", "id")
        )
        for sp in source_prices:
            new_price = PlanPrice(
                plan_version=new_pv,
                currency=sp.currency,
                billing_interval=sp.billing_interval,
                amount=sp.amount,
                created_by=actor,
                updated_by=actor,
            )
            new_price.full_clean()
            new_price.save()

        # 2. Copy PlanProducts
        source_products = list(
            PlanProduct.objects.select_for_update()
            .filter(plan_version=source_pv)
            .order_by("product__code", "id")
        )
        product_map: dict[uuid.UUID, PlanProduct] = {}
        for spp in source_products:
            new_pp = PlanProduct(
                plan_version=new_pv,
                product=spp.product,
                created_by=actor,
            )
            new_pp.full_clean()
            new_pp.save()
            product_map[spp.id] = new_pp

        # 3. Copy PlanModules
        source_modules = list(
            PlanModule.objects.select_for_update()
            .filter(plan_version=source_pv)
            .order_by("module__code", "id")
        )
        module_map: dict[uuid.UUID, PlanModule] = {}
        for spm in source_modules:
            new_pm = PlanModule(
                plan_version=new_pv,
                plan_product=product_map[spm.plan_product_id],
                module=spm.module,
                created_by=actor,
            )
            new_pm.full_clean()
            new_pm.save()
            module_map[spm.id] = new_pm

        # 4. Copy PlanCapabilities
        source_capabilities = list(
            PlanCapability.objects.select_for_update()
            .filter(plan_version=source_pv)
            .order_by("capability__code", "id")
        )
        capability_map: dict[uuid.UUID, PlanCapability] = {}
        for spc in source_capabilities:
            new_pc = PlanCapability(
                plan_version=new_pv,
                plan_module=module_map[spc.plan_module_id],
                capability=spc.capability,
                created_by=actor,
            )
            new_pc.full_clean()
            new_pc.save()
            capability_map[spc.id] = new_pc

        # 5. Copy PlanQuotas
        source_quotas = list(
            PlanQuota.objects.select_for_update()
            .filter(plan_version=source_pv)
            .order_by("scope", "quota_key", "id")
        )
        for sq in source_quotas:
            mapped_product = product_map.get(sq.plan_product_id) if sq.plan_product_id else None
            mapped_module = module_map.get(sq.plan_module_id) if sq.plan_module_id else None
            mapped_capability = capability_map.get(sq.plan_capability_id) if sq.plan_capability_id else None

            new_quota = PlanQuota(
                plan_version=new_pv,
                scope=sq.scope,
                quota_key=sq.quota_key,
                name=sq.name,
                unit=sq.unit,
                limit_type=sq.limit_type,
                limit_value=sq.limit_value,
                is_hard_limit=sq.is_hard_limit,
                reset_period=sq.reset_period,
                plan_product=mapped_product,
                plan_module=mapped_module,
                plan_capability=mapped_capability,
                created_by=actor,
                updated_by=actor,
            )
            new_quota.full_clean()
            new_quota.save()

        health_eval = evaluate_activation_readiness(plan_version=new_pv)
        resulting_health = health_eval["catalog_health"]

        # Aggregate clone audit only — zero individual child-added events
        record_audit_event(
            action=AuditAction.PLAN_VERSION_CLONED,
            target_type=AuditTargetType.PLAN_VERSION,
            target_id=new_pv.id,
            target_repr=f"{plan.code} v{new_pv.version}",
            actor=actor,
            organization_id=None,
            operation_source=AuditOperationSource.INTERACTIVE,
            metadata={
                "source_plan_version_id": str(source_pv.id),
                "source_version": source_pv.version,
                "resulting_plan_version_id": str(new_pv.id),
                "resulting_version": new_pv.version,
                "copied_prices_count": len(source_prices),
                "copied_products_count": len(source_products),
                "copied_modules_count": len(source_modules),
                "copied_capabilities_count": len(source_capabilities),
                "copied_quotas_count": len(source_quotas),
                "resulting_catalog_health": resulting_health,
            },
        )

        return new_pv


def activate_plan_version(
    *,
    plan_version_id: uuid.UUID | str,
    actor: Any,
) -> PlanVersion:
    """Activates a Draft version and supersedes any currently Active version on the same Plan."""
    _validate_actor(actor)

    with transaction.atomic():
        # 1. Lock parent Plan
        pv_initial = PlanVersion.objects.get(pk=plan_version_id)
        plan = Plan.objects.select_for_update().get(pk=pv_initial.plan_id)

        # 2. Lock all relevant PlanVersions deterministically
        all_versions = list(
            PlanVersion.objects.select_for_update().filter(plan=plan).order_by("version", "id")
        )
        target_version = next(v for v in all_versions if v.id == pv_initial.id)

        # 3. Lock complete commercial graph in canonical order
        list(
            PlanPrice.objects.select_for_update()
            .filter(plan_version=target_version)
            .order_by("currency", "billing_interval", "id")
        )
        plan_products = list(
            PlanProduct.objects.select_for_update()
            .filter(plan_version=target_version)
            .order_by("product__code", "id")
        )
        plan_modules = list(
            PlanModule.objects.select_for_update()
            .filter(plan_version=target_version)
            .order_by("module__code", "id")
        )
        plan_capabilities = list(
            PlanCapability.objects.select_for_update()
            .filter(plan_version=target_version)
            .order_by("capability__code", "id")
        )
        list(
            PlanQuota.objects.select_for_update()
            .filter(plan_version=target_version)
            .order_by("scope", "quota_key", "id")
        )

        # 4. Lock referenced catalog entities in canonical order (id ASC)
        prod_ids = sorted(list({pp.product_id for pp in plan_products}))
        list(Product.objects.select_for_update().filter(id__in=prod_ids).order_by("id"))
        mod_ids = sorted(list({pm.module_id for pm in plan_modules}))
        list(ProductModule.objects.select_for_update().filter(id__in=mod_ids).order_by("id"))
        cap_ids = sorted(list({pc.capability_id for pc in plan_capabilities}))
        caps_unlocked = list(ProductCapability.objects.filter(id__in=cap_ids))
        feat_ids = sorted(list({c.feature_id for c in caps_unlocked}))
        list(ProductFeature.objects.select_for_update().filter(id__in=feat_ids).order_by("id"))
        list(ProductCapability.objects.select_for_update().filter(id__in=cap_ids).order_by("id"))

        # 5. Re-check status of target version
        if target_version.status != PlanVersionStatus.DRAFT:
            raise ValidationError(
                f"Cannot activate version '{target_version.id}' in status '{target_version.status}'. Only draft versions can be activated."
            )

        # 6. Re-evaluate readiness after locks
        readiness = evaluate_activation_readiness(plan_version=target_version)
        if not readiness["is_ready"]:
            raise ValidationError(
                f"Plan version activation blocked: {'; '.join(readiness['blockers'])}"
            )

        # 7. Find existing active version on same plan
        old_active = next(
            (v for v in all_versions if v.status == PlanVersionStatus.ACTIVE and v.id != target_version.id),
            None,
        )

        # 8. Supersede existing active version if present
        now = timezone.now()
        if old_active:
            old_active.status = PlanVersionStatus.RETIRED
            old_active.retired_at = now
            old_active.updated_by = actor
            old_active.full_clean()
            old_active.save()

            record_audit_event(
                action=AuditAction.PLAN_VERSION_RETIRED,
                target_type=AuditTargetType.PLAN_VERSION,
                target_id=old_active.id,
                target_repr=f"{plan.code} v{old_active.version}",
                actor=actor,
                organization_id=None,
                operation_source=AuditOperationSource.INTERACTIVE,
                metadata={
                    "plan_id": str(plan.id),
                    "plan_code": plan.code,
                    "version": old_active.version,
                    "previous_status": "active",
                    "resulting_status": "retired",
                    "retirement_reason": "superseded",
                    "superseded_by_plan_version_id": str(target_version.id),
                    "superseded_by_version": target_version.version,
                },
            )

        # 9. Activate selected draft
        target_version.status = PlanVersionStatus.ACTIVE
        target_version.activated_at = now
        target_version.updated_by = actor
        target_version.full_clean()
        target_version.save()

        record_audit_event(
            action=AuditAction.PLAN_VERSION_ACTIVATED,
            target_type=AuditTargetType.PLAN_VERSION,
            target_id=target_version.id,
            target_repr=f"{plan.code} v{target_version.version}",
            actor=actor,
            organization_id=None,
            operation_source=AuditOperationSource.INTERACTIVE,
            metadata={
                "plan_id": str(plan.id),
                "plan_code": plan.code,
                "version": target_version.version,
                "previous_status": "draft",
                "resulting_status": "active",
                "superseded_version_id": str(old_active.id) if old_active else None,
                "superseded_version": old_active.version if old_active else None,
            },
        )

        return target_version


def retire_plan_version(
    *,
    plan_version_id: uuid.UUID | str,
    actor: Any,
) -> PlanVersion:
    """Manually retires a Draft or Active version. Retiring an already retired version is rejected with zero audit."""
    _validate_actor(actor)

    with transaction.atomic():
        pv_initial = PlanVersion.objects.get(pk=plan_version_id)
        plan = Plan.objects.select_for_update().get(pk=pv_initial.plan_id)
        pv = PlanVersion.objects.select_for_update().get(pk=plan_version_id)
        pv.plan = plan

        if pv.status == PlanVersionStatus.RETIRED:
            raise ValidationError("Plan version is already retired.")

        prev_status = pv.status
        now = timezone.now()
        pv.status = PlanVersionStatus.RETIRED
        pv.retired_at = now

        if prev_status == PlanVersionStatus.DRAFT:
            pv.activated_at = None

        pv.updated_by = actor
        pv.full_clean()
        pv.save()

        record_audit_event(
            action=AuditAction.PLAN_VERSION_RETIRED,
            target_type=AuditTargetType.PLAN_VERSION,
            target_id=pv.id,
            target_repr=f"{plan.code} v{pv.version}",
            actor=actor,
            organization_id=None,
            operation_source=AuditOperationSource.INTERACTIVE,
            metadata={
                "plan_id": str(plan.id),
                "plan_code": plan.code,
                "version": pv.version,
                "previous_status": prev_status,
                "resulting_status": "retired",
                "retirement_reason": "manual",
                "superseded_by_plan_version_id": None,
                "superseded_by_version": None,
            },
        )

        return pv


# ---------------------------------------------------------------------------
# PlanPrice Services
# ---------------------------------------------------------------------------

def create_plan_price(
    *,
    plan_version_id: uuid.UUID | str,
    currency: str,
    billing_interval: str,
    amount: str,
    actor: Any,
) -> PlanPrice:
    """Creates a price on a Draft version."""
    _validate_actor(actor)

    with transaction.atomic():
        pv = _get_and_lock_draft_version(plan_version_id)

        curr = _validate_price_currency(currency)
        if billing_interval not in BillingInterval.values:
            raise ValidationError(f"Invalid billing_interval '{billing_interval}'.")

        amt_dec, amt_str = _validate_canonical_price_amount(amount)
        price = PlanPrice(
            plan_version=pv,
            currency=curr,
            billing_interval=billing_interval,
            amount=amt_dec,
            created_by=actor,
            updated_by=actor,
        )
        price.full_clean()
        price.save()

        record_audit_event(
            action=AuditAction.PLAN_PRICE_CREATED,
            target_type=AuditTargetType.PLAN_PRICE,
            target_id=price.id,
            target_repr=f"{price.currency} {amt_str}/{price.billing_interval}",
            actor=actor,
            organization_id=None,
            operation_source=AuditOperationSource.INTERACTIVE,
            metadata={
                "plan_id": str(pv.plan_id),
                "plan_version_id": str(pv.id),
                "currency": price.currency,
                "billing_interval": price.billing_interval,
                "amount": amt_str,
            },
        )

        return price


def update_plan_price(
    *,
    plan_price_id: uuid.UUID | str,
    amount: str,
    actor: Any,
) -> PlanPrice:
    """Updates only the amount on a Draft version's price."""
    _validate_actor(actor)

    with transaction.atomic():
        price_init = PlanPrice.objects.get(pk=plan_price_id)
        pv = _get_and_lock_draft_version(price_init.plan_version_id)
        price = PlanPrice.objects.select_for_update().select_related("plan_version__plan").get(pk=plan_price_id)

        res_amt_dec, res_amt_str = _validate_canonical_price_amount(amount)
        prev_amt_str = f"{price.amount:.2f}"

        price.amount = res_amt_dec
        price.updated_by = actor
        price.full_clean()
        price.save()

        record_audit_event(
            action=AuditAction.PLAN_PRICE_UPDATED,
            target_type=AuditTargetType.PLAN_PRICE,
            target_id=price.id,
            target_repr=f"{price.currency} {res_amt_str}/{price.billing_interval}",
            actor=actor,
            organization_id=None,
            operation_source=AuditOperationSource.INTERACTIVE,
            metadata={
                "plan_id": str(price.plan_version.plan_id),
                "plan_version_id": str(price.plan_version_id),
                "currency": price.currency,
                "billing_interval": price.billing_interval,
                "previous_amount": prev_amt_str,
                "resulting_amount": res_amt_str,
            },
        )

        return price


def remove_plan_price(
    *,
    plan_price_id: uuid.UUID | str,
    actor: Any,
) -> None:
    """Removes a price from a Draft version."""
    _validate_actor(actor)

    with transaction.atomic():
        price_init = PlanPrice.objects.get(pk=plan_price_id)
        pv = _get_and_lock_draft_version(price_init.plan_version_id)
        price = PlanPrice.objects.select_for_update().select_related("plan_version__plan").get(pk=plan_price_id)

        amt_str = f"{price.amount:.2f}"
        record_audit_event(
            action=AuditAction.PLAN_PRICE_REMOVED,
            target_type=AuditTargetType.PLAN_PRICE,
            target_id=price.id,
            target_repr=f"{price.currency} {amt_str}/{price.billing_interval}",
            actor=actor,
            organization_id=None,
            operation_source=AuditOperationSource.INTERACTIVE,
            metadata={
                "plan_id": str(price.plan_version.plan_id),
                "plan_version_id": str(price.plan_version_id),
                "currency": price.currency,
                "billing_interval": price.billing_interval,
                "amount": amt_str,
            },
        )

        price.delete()


# ---------------------------------------------------------------------------
# Packaging Services (PlanProduct, PlanModule, PlanCapability)
# ---------------------------------------------------------------------------

def add_plan_product(
    *,
    plan_version_id: uuid.UUID | str,
    product_id: uuid.UUID | str,
    actor: Any,
) -> PlanProduct:
    """Adds an active Product to a Draft version."""
    _validate_actor(actor)

    with transaction.atomic():
        pv = _get_and_lock_draft_version(plan_version_id)
        product = Product.objects.select_for_update().get(pk=product_id)

        if product.status != ProductStatus.ACTIVE:
            raise ValidationError(
                f"Cannot attach non-active Product '{product.code}' (status: '{product.status}')."
            )

        pp = PlanProduct(
            plan_version=pv,
            product=product,
            created_by=actor,
        )
        pp.full_clean()
        pp.save()

        record_audit_event(
            action=AuditAction.PLAN_PRODUCT_ADDED,
            target_type=AuditTargetType.PLAN_PRODUCT,
            target_id=pp.id,
            target_repr=f"{product.name} ({product.code})",
            actor=actor,
            organization_id=None,
            operation_source=AuditOperationSource.INTERACTIVE,
            metadata={
                "plan_id": str(pv.plan_id),
                "plan_version_id": str(pv.id),
                "product_id": str(product.id),
                "product_code": product.code,
            },
        )

        return pp


def remove_plan_product(
    *,
    plan_product_id: uuid.UUID | str,
    actor: Any,
) -> None:
    """Removes a PlanProduct with deterministic descendant auditing."""
    _validate_actor(actor)

    with transaction.atomic():
        pp_init = PlanProduct.objects.get(pk=plan_product_id)
        pv = _get_and_lock_draft_version(pp_init.plan_version_id)
        pp = (
            PlanProduct.objects.select_for_update()
            .select_related("product")
            .get(pk=plan_product_id)
        )
        pp.plan_version = pv

        modules = list(
            PlanModule.objects.select_for_update()
            .filter(plan_product=pp)
            .select_related("module")
            .order_by("module__code", "id")
        )
        caps = list(
            PlanCapability.objects.select_for_update()
            .filter(plan_module__in=modules)
            .select_related("capability__feature", "plan_module__module")
            .order_by("capability__code", "id")
        )

        # Lock and fetch all descendant quotas in canonical order: scope ASC, quota_key ASC, id ASC
        all_quotas = list(
            PlanQuota.objects.select_for_update()
            .filter(
                Q(plan_product=pp)
                | Q(plan_module__in=modules)
                | Q(plan_capability__in=caps),
                plan_version=pp.plan_version,
            )
            .order_by("scope", "quota_key", "id")
        )

        # 1. Emit quota-removal events
        for q in all_quotas:
            target_id_str = str(q.plan_product_id or q.plan_module_id or q.plan_capability_id or "") or None
            record_audit_event(
                action=AuditAction.PLAN_QUOTA_REMOVED,
                target_type=AuditTargetType.PLAN_QUOTA,
                target_id=q.id,
                target_repr=f"{q.quota_key}: {q.limit_type}",
                actor=actor,
                organization_id=None,
                operation_source=AuditOperationSource.INTERACTIVE,
                metadata={
                    "plan_id": str(pp.plan_version.plan_id),
                    "plan_version_id": str(pp.plan_version_id),
                    "scope": q.scope,
                    "target_id": target_id_str,
                    "quota_key": q.quota_key,
                    "limit_type": q.limit_type,
                    "limit_value": str(q.limit_value) if q.limit_value is not None else None,
                },
            )

        # 2. Emit capability-removal events
        for pc in caps:
            cap_quotas_count = sum(1 for q in all_quotas if q.plan_capability_id == pc.id)
            record_audit_event(
                action=AuditAction.PLAN_CAPABILITY_REMOVED,
                target_type=AuditTargetType.PLAN_CAPABILITY,
                target_id=pc.id,
                target_repr=f"{pc.capability.name} ({pc.capability.code})",
                actor=actor,
                organization_id=None,
                operation_source=AuditOperationSource.INTERACTIVE,
                metadata={
                    "plan_id": str(pp.plan_version.plan_id),
                    "plan_version_id": str(pp.plan_version_id),
                    "product_id": str(pp.product_id),
                    "module_id": str(pc.plan_module.module_id),
                    "feature_id": str(pc.capability.feature_id),
                    "capability_id": str(pc.capability_id),
                    "capability_code": pc.capability.code,
                    "cascaded_quotas_count": cap_quotas_count,
                },
            )

        # 3. Emit module-removal events
        for pm in modules:
            mod_caps_count = sum(1 for c in caps if c.plan_module_id == pm.id)
            mod_quotas_count = sum(
                1 for q in all_quotas if q.plan_module_id == pm.id or (q.plan_capability and q.plan_capability.plan_module_id == pm.id)
            )
            record_audit_event(
                action=AuditAction.PLAN_MODULE_REMOVED,
                target_type=AuditTargetType.PLAN_MODULE,
                target_id=pm.id,
                target_repr=f"{pm.module.name} ({pm.module.code})",
                actor=actor,
                organization_id=None,
                operation_source=AuditOperationSource.INTERACTIVE,
                metadata={
                    "plan_id": str(pp.plan_version.plan_id),
                    "plan_version_id": str(pp.plan_version_id),
                    "product_id": str(pp.product_id),
                    "product_code": pp.product.code,
                    "module_id": str(pm.module_id),
                    "module_code": pm.module.code,
                    "cascaded_capabilities_count": mod_caps_count,
                    "cascaded_quotas_count": mod_quotas_count,
                },
            )

        # 4. Emit plan_product_removed
        record_audit_event(
            action=AuditAction.PLAN_PRODUCT_REMOVED,
            target_type=AuditTargetType.PLAN_PRODUCT,
            target_id=pp.id,
            target_repr=f"{pp.product.name} ({pp.product.code})",
            actor=actor,
            organization_id=None,
            operation_source=AuditOperationSource.INTERACTIVE,
            metadata={
                "plan_id": str(pp.plan_version.plan_id),
                "plan_version_id": str(pp.plan_version_id),
                "product_id": str(pp.product_id),
                "product_code": pp.product.code,
                "cascaded_modules_count": len(modules),
                "cascaded_capabilities_count": len(caps),
                "cascaded_quotas_count": len(all_quotas),
            },
        )

        pp.delete()


def add_plan_module(
    *,
    plan_product_id: uuid.UUID | str,
    module_id: uuid.UUID | str,
    actor: Any,
) -> PlanModule:
    """Adds an active ProductModule beneath the correct PlanProduct."""
    _validate_actor(actor)

    with transaction.atomic():
        pp_init = PlanProduct.objects.get(pk=plan_product_id)
        pv = _get_and_lock_draft_version(pp_init.plan_version_id)
        pp = (
            PlanProduct.objects.select_for_update()
            .select_related("plan_version__plan", "product")
            .get(pk=plan_product_id)
        )

        # Lock catalog rows
        Product.objects.select_for_update().get(pk=pp.product_id)
        mod = ProductModule.objects.select_for_update().get(pk=module_id)

        if mod.status != CatalogStatus.ACTIVE:
            raise ValidationError(
                f"Cannot attach non-active ProductModule '{mod.code}' (status: '{mod.status}')."
            )
        if mod.product_id != pp.product_id:
            raise ValidationError(
                f"ProductModule '{mod.code}' does not belong to selected PlanProduct '{pp.product.code}'."
            )

        pm = PlanModule(
            plan_version=pp.plan_version,
            plan_product=pp,
            module=mod,
            created_by=actor,
        )
        pm.full_clean()
        pm.save()

        record_audit_event(
            action=AuditAction.PLAN_MODULE_ADDED,
            target_type=AuditTargetType.PLAN_MODULE,
            target_id=pm.id,
            target_repr=f"{mod.name} ({mod.code})",
            actor=actor,
            organization_id=None,
            operation_source=AuditOperationSource.INTERACTIVE,
            metadata={
                "plan_id": str(pp.plan_version.plan_id),
                "plan_version_id": str(pp.plan_version_id),
                "product_id": str(pp.product_id),
                "product_code": pp.product.code,
                "module_id": str(mod.id),
                "module_code": mod.code,
            },
        )

        return pm


def remove_plan_module(
    *,
    plan_module_id: uuid.UUID | str,
    actor: Any,
) -> None:
    """Removes a PlanModule with deterministic descendant auditing."""
    _validate_actor(actor)

    with transaction.atomic():
        pm_init = PlanModule.objects.get(pk=plan_module_id)
        pv = _get_and_lock_draft_version(pm_init.plan_version_id)
        pm = (
            PlanModule.objects.select_for_update()
            .select_related("plan_product__product", "module")
            .get(pk=plan_module_id)
        )
        pm.plan_version = pv

        caps = list(
            PlanCapability.objects.select_for_update()
            .filter(plan_module=pm)
            .select_related("capability__feature")
            .order_by("capability__code", "id")
        )

        descendant_quotas = list(
            PlanQuota.objects.select_for_update()
            .filter(
                Q(plan_module=pm) | Q(plan_capability__in=caps),
                plan_version=pm.plan_version,
            )
            .order_by("scope", "quota_key", "id")
        )

        # 1. Emit quota-removal events
        for q in descendant_quotas:
            target_id_str = str(q.plan_module_id or q.plan_capability_id or "") or None
            record_audit_event(
                action=AuditAction.PLAN_QUOTA_REMOVED,
                target_type=AuditTargetType.PLAN_QUOTA,
                target_id=q.id,
                target_repr=f"{q.quota_key}: {q.limit_type}",
                actor=actor,
                organization_id=None,
                operation_source=AuditOperationSource.INTERACTIVE,
                metadata={
                    "plan_id": str(pm.plan_version.plan_id),
                    "plan_version_id": str(pm.plan_version_id),
                    "scope": q.scope,
                    "target_id": target_id_str,
                    "quota_key": q.quota_key,
                    "limit_type": q.limit_type,
                    "limit_value": str(q.limit_value) if q.limit_value is not None else None,
                },
            )

        # 2. Emit capability-removal events
        for pc in caps:
            cap_quotas_count = sum(1 for q in descendant_quotas if q.plan_capability_id == pc.id)
            record_audit_event(
                action=AuditAction.PLAN_CAPABILITY_REMOVED,
                target_type=AuditTargetType.PLAN_CAPABILITY,
                target_id=pc.id,
                target_repr=f"{pc.capability.name} ({pc.capability.code})",
                actor=actor,
                organization_id=None,
                operation_source=AuditOperationSource.INTERACTIVE,
                metadata={
                    "plan_id": str(pm.plan_version.plan_id),
                    "plan_version_id": str(pm.plan_version_id),
                    "product_id": str(pm.plan_product.product_id),
                    "module_id": str(pm.module_id),
                    "feature_id": str(pc.capability.feature_id),
                    "capability_id": str(pc.capability_id),
                    "capability_code": pc.capability.code,
                    "cascaded_quotas_count": cap_quotas_count,
                },
            )

        # 3. Emit module-removal event
        record_audit_event(
            action=AuditAction.PLAN_MODULE_REMOVED,
            target_type=AuditTargetType.PLAN_MODULE,
            target_id=pm.id,
            target_repr=f"{pm.module.name} ({pm.module.code})",
            actor=actor,
            organization_id=None,
            operation_source=AuditOperationSource.INTERACTIVE,
            metadata={
                "plan_id": str(pm.plan_version.plan_id),
                "plan_version_id": str(pm.plan_version_id),
                "product_id": str(pm.plan_product.product_id),
                "product_code": pm.plan_product.product.code,
                "module_id": str(pm.module_id),
                "module_code": pm.module.code,
                "cascaded_capabilities_count": len(caps),
                "cascaded_quotas_count": len(descendant_quotas),
            },
        )

        pm.delete()


def add_plan_capability(
    *,
    plan_module_id: uuid.UUID | str,
    capability_id: uuid.UUID | str,
    actor: Any,
) -> PlanCapability:
    """Adds an active ProductCapability beneath the correct PlanModule."""
    _validate_actor(actor)

    with transaction.atomic():
        pm_init = PlanModule.objects.get(pk=plan_module_id)
        pv = _get_and_lock_draft_version(pm_init.plan_version_id)
        pm = (
            PlanModule.objects.select_for_update()
            .select_related("plan_version__plan", "plan_product__product", "module")
            .get(pk=plan_module_id)
        )

        # Unlocked read of catalog ancestry
        cap_init = (
            ProductCapability.objects.select_related("feature__module__product")
            .get(pk=capability_id)
        )
        # Lock catalog rows in canonical order: Product (8) -> ProductModule (9) -> ProductFeature (10) -> ProductCapability (11)
        prod = Product.objects.select_for_update().get(pk=cap_init.feature.module.product_id)
        mod = ProductModule.objects.select_for_update().get(pk=cap_init.feature.module_id)
        feat = ProductFeature.objects.select_for_update().get(pk=cap_init.feature_id)
        cap = ProductCapability.objects.select_for_update().get(pk=capability_id)

        if cap.status != CatalogStatus.ACTIVE:
            raise ValidationError(
                f"Cannot attach non-active ProductCapability '{cap.code}' (status: '{cap.status}')."
            )
        if feat.status != CatalogStatus.ACTIVE:
            raise ValidationError(
                f"Feature ancestor '{feat.code}' for capability '{cap.code}' is not active (status: '{feat.status}')."
            )
        if feat.module_id != pm.module_id:
            raise ValidationError(
                f"ProductCapability '{cap.code}' feature does not belong to selected PlanModule '{pm.module.code}'."
            )
        if mod.product_id != pm.plan_product.product_id:
            raise ValidationError(
                f"Module ancestor '{mod.code}' does not match PlanProduct '{pm.plan_product.product.code}'."
            )

        pc = PlanCapability(
            plan_version=pm.plan_version,
            plan_module=pm,
            capability=cap,
            created_by=actor,
        )
        pc.full_clean()
        pc.save()

        record_audit_event(
            action=AuditAction.PLAN_CAPABILITY_ADDED,
            target_type=AuditTargetType.PLAN_CAPABILITY,
            target_id=pc.id,
            target_repr=f"{cap.name} ({cap.code})",
            actor=actor,
            organization_id=None,
            operation_source=AuditOperationSource.INTERACTIVE,
            metadata={
                "plan_id": str(pm.plan_version.plan_id),
                "plan_version_id": str(pm.plan_version_id),
                "product_id": str(prod.id),
                "module_id": str(mod.id),
                "feature_id": str(feat.id),
                "capability_id": str(cap.id),
                "capability_code": cap.code,
            },
        )

        return pc


def remove_plan_capability(
    *,
    plan_capability_id: uuid.UUID | str,
    actor: Any,
) -> None:
    """Removes a PlanCapability with deterministic descendant quota auditing."""
    _validate_actor(actor)

    with transaction.atomic():
        pc_init = PlanCapability.objects.get(pk=plan_capability_id)
        pv = _get_and_lock_draft_version(pc_init.plan_version_id)
        pc = (
            PlanCapability.objects.select_for_update()
            .select_related(
                "plan_module__module",
                "plan_module__plan_product__product",
                "capability__feature",
            )
            .get(pk=plan_capability_id)
        )
        pc.plan_version = pv

        quotas = list(
            PlanQuota.objects.select_for_update()
            .filter(plan_capability=pc)
            .order_by("scope", "quota_key", "id")
        )

        # 1. Emit quota-removal events
        for q in quotas:
            record_audit_event(
                action=AuditAction.PLAN_QUOTA_REMOVED,
                target_type=AuditTargetType.PLAN_QUOTA,
                target_id=q.id,
                target_repr=f"{q.quota_key}: {q.limit_type}",
                actor=actor,
                organization_id=None,
                operation_source=AuditOperationSource.INTERACTIVE,
                metadata={
                    "plan_id": str(pc.plan_version.plan_id),
                    "plan_version_id": str(pc.plan_version_id),
                    "scope": q.scope,
                    "target_id": str(pc.id),
                    "quota_key": q.quota_key,
                    "limit_type": q.limit_type,
                    "limit_value": str(q.limit_value) if q.limit_value is not None else None,
                },
            )

        # 2. Emit capability-removal event
        record_audit_event(
            action=AuditAction.PLAN_CAPABILITY_REMOVED,
            target_type=AuditTargetType.PLAN_CAPABILITY,
            target_id=pc.id,
            target_repr=f"{pc.capability.name} ({pc.capability.code})",
            actor=actor,
            organization_id=None,
            operation_source=AuditOperationSource.INTERACTIVE,
            metadata={
                "plan_id": str(pc.plan_version.plan_id),
                "plan_version_id": str(pc.plan_version_id),
                "product_id": str(pc.plan_module.plan_product.product_id),
                "module_id": str(pc.plan_module.module_id),
                "feature_id": str(pc.capability.feature_id),
                "capability_id": str(pc.capability_id),
                "capability_code": pc.capability.code,
                "cascaded_quotas_count": len(quotas),
            },
        )

        pc.delete()


# ---------------------------------------------------------------------------
# PlanQuota Services
# ---------------------------------------------------------------------------

def _canonical_quota_limit(limit_type: str, limit_value: Any) -> tuple[int | None, str | None]:
    if limit_type == "unlimited":
        if limit_value is not None:
            raise ValidationError("limit_value must be None when limit_type is 'unlimited'.")
        return None, None
    elif limit_type == "numeric":
        if limit_value is None:
            raise ValidationError("limit_value cannot be None when limit_type is 'numeric'.")
        val_str = str(limit_value)
        if val_str != "0" and not re.match(r"^[1-9][0-9]*$", val_str):
            raise ValidationError(f"Invalid canonical quota format or leading zeros: '{val_str}'.")
        try:
            int_val = int(val_str)
            if int_val < 0 or int_val > 9223372036854775807:
                raise ValidationError("limit_value out of 64-bit integer range.")
            return int_val, str(int_val)
        except ValueError:
            raise ValidationError("limit_value must be a valid integer string.")
    else:
        raise ValidationError(f"Invalid limit_type '{limit_type}'.")


def create_plan_quota(
    *,
    plan_version_id: uuid.UUID | str,
    scope: str,
    quota_key: str,
    name: str,
    unit: str,
    limit_type: str,
    limit_value: int | str | None,
    is_hard_limit: bool = True,
    reset_period: str = "never",
    target_id: uuid.UUID | str | None = None,
    actor: Any,
) -> PlanQuota:
    """Creates a quota on a Draft version."""
    _validate_actor(actor)

    with transaction.atomic():
        pv = _get_and_lock_draft_version(plan_version_id)

        plan_prod = None
        plan_mod = None
        plan_cap = None

        if scope == "plan":
            if target_id is not None:
                raise ValidationError("target_id must be None when scope is 'plan'.")
        elif scope == "product":
            if not target_id:
                raise ValidationError("target_id is required when scope is 'product'.")
            plan_prod = PlanProduct.objects.select_for_update().get(pk=target_id)
            if plan_prod.plan_version_id != pv.id:
                raise ValidationError("Cross-version quota target: PlanProduct belongs to different PlanVersion.")
        elif scope == "module":
            if not target_id:
                raise ValidationError("target_id is required when scope is 'module'.")
            plan_mod = PlanModule.objects.select_for_update().get(pk=target_id)
            if plan_mod.plan_version_id != pv.id:
                raise ValidationError("Cross-version quota target: PlanModule belongs to different PlanVersion.")
        elif scope == "capability":
            if not target_id:
                raise ValidationError("target_id is required when scope is 'capability'.")
            plan_cap = PlanCapability.objects.select_for_update().get(pk=target_id)
            if plan_cap.plan_version_id != pv.id:
                raise ValidationError("Cross-version quota target: PlanCapability belongs to different PlanVersion.")
        else:
            raise ValidationError(f"Invalid quota scope '{scope}'.")

        quota_key = quota_key.strip()
        if not re.match(r"^[a-z0-9]+(?:[-_][a-z0-9]+)*$", quota_key):
            raise ValidationError("quota_key must be lowercase alphanumeric with single hyphens or underscores.")

        if not isinstance(unit, str) or unit != unit.strip() or any(c.isspace() for c in unit):
            raise ValidationError("unit cannot contain whitespace.")
        if unit != unit.lower():
            raise ValidationError("unit must be lowercase.")
        if not re.match(r"^[a-z0-9_]+$", unit):
            raise ValidationError("unit must be lowercase alphanumeric with underscores.")

        db_limit, canonical_limit_str = _canonical_quota_limit(limit_type, limit_value)

        quota = PlanQuota(
            plan_version=pv,
            scope=scope,
            quota_key=quota_key,
            name=name.strip(),
            unit=unit,
            limit_type=limit_type,
            limit_value=db_limit,
            is_hard_limit=is_hard_limit,
            reset_period=reset_period,
            plan_product=plan_prod,
            plan_module=plan_mod,
            plan_capability=plan_cap,
            created_by=actor,
            updated_by=actor,
        )
        quota.full_clean()
        quota.save()

        target_id_str = str(target_id) if target_id else None
        record_audit_event(
            action=AuditAction.PLAN_QUOTA_CREATED,
            target_type=AuditTargetType.PLAN_QUOTA,
            target_id=quota.id,
            target_repr=f"{quota.quota_key}: {quota.limit_type}",
            actor=actor,
            organization_id=None,
            operation_source=AuditOperationSource.INTERACTIVE,
            metadata={
                "plan_id": str(pv.plan_id),
                "plan_version_id": str(pv.id),
                "scope": scope,
                "target_id": target_id_str,
                "quota_key": quota.quota_key,
                "limit_type": quota.limit_type,
                "limit_value": canonical_limit_str,
                "unit": quota.unit,
                "reset_period": quota.reset_period,
                "is_hard_limit": quota.is_hard_limit,
            },
        )

        return quota


def update_plan_quota(
    *,
    plan_quota_id: uuid.UUID | str,
    name: str | None = None,
    unit: str | None = None,
    limit_type: str | None = None,
    limit_value: Any = ...,
    is_hard_limit: bool | None = None,
    reset_period: str | None = None,
    actor: Any,
) -> PlanQuota:
    """Updates only the six approved fields on a Draft version's quota."""
    _validate_actor(actor)

    with transaction.atomic():
        quota_init = PlanQuota.objects.get(pk=plan_quota_id)
        pv = _get_and_lock_draft_version(quota_init.plan_version_id)
        quota = (
            PlanQuota.objects.select_for_update()
            .select_related("plan_version__plan")
            .get(pk=plan_quota_id)
        )

        prev_name = quota.name
        prev_unit = quota.unit
        prev_limit_type = quota.limit_type
        prev_limit_value = str(quota.limit_value) if quota.limit_value is not None else None
        prev_is_hard_limit = quota.is_hard_limit
        prev_reset_period = quota.reset_period

        if name is not None:
            quota.name = name.strip()
        if unit is not None:
            if not isinstance(unit, str) or unit != unit.strip() or any(c.isspace() for c in unit):
                raise ValidationError("unit cannot contain whitespace.")
            if unit != unit.lower():
                raise ValidationError("unit must be lowercase.")
            if not re.match(r"^[a-z0-9_]+$", unit):
                raise ValidationError("unit must be lowercase alphanumeric with underscores.")
            quota.unit = unit
        if limit_type is not None:
            quota.limit_type = limit_type

        if limit_value is not ...:
            db_lim, _ = _canonical_quota_limit(quota.limit_type, limit_value)
            quota.limit_value = db_lim
        elif limit_type is not None and limit_type != prev_limit_type:
            # If limit_type changed and limit_value wasn't explicitly supplied, validate compatibility
            if quota.limit_type == "unlimited":
                quota.limit_value = None

        if is_hard_limit is not None:
            quota.is_hard_limit = is_hard_limit
        if reset_period is not None:
            quota.reset_period = reset_period

        quota.updated_by = actor
        quota.full_clean()
        quota.save()

        res_name = quota.name
        res_unit = quota.unit
        res_limit_type = quota.limit_type
        res_limit_value = str(quota.limit_value) if quota.limit_value is not None else None
        res_is_hard_limit = quota.is_hard_limit
        res_reset_period = quota.reset_period

        name_changed = (prev_name != res_name)
        unit_changed = (prev_unit != res_unit)
        limit_type_changed = (prev_limit_type != res_limit_type)
        limit_value_changed = (prev_limit_value != res_limit_value)
        is_hard_limit_changed = (prev_is_hard_limit != res_is_hard_limit)
        reset_period_changed = (prev_reset_period != res_reset_period)

        if quota.scope == "product":
            target_id_str = str(quota.plan_product_id)
        elif quota.scope == "module":
            target_id_str = str(quota.plan_module_id)
        elif quota.scope == "capability":
            target_id_str = str(quota.plan_capability_id)
        else:
            target_id_str = None

        record_audit_event(
            action=AuditAction.PLAN_QUOTA_UPDATED,
            target_type=AuditTargetType.PLAN_QUOTA,
            target_id=quota.id,
            target_repr=f"{quota.quota_key}: {res_limit_type}",
            actor=actor,
            organization_id=None,
            operation_source=AuditOperationSource.INTERACTIVE,
            metadata={
                "plan_id": str(quota.plan_version.plan_id),
                "plan_version_id": str(quota.plan_version_id),
                "scope": quota.scope,
                "target_id": target_id_str,
                "quota_key": quota.quota_key,
                "name_changed": name_changed,
                "unit_changed": unit_changed,
                "limit_type_changed": limit_type_changed,
                "limit_value_changed": limit_value_changed,
                "is_hard_limit_changed": is_hard_limit_changed,
                "reset_period_changed": reset_period_changed,
                "previous_name": prev_name,
                "resulting_name": res_name,
                "previous_unit": prev_unit,
                "resulting_unit": res_unit,
                "previous_limit_type": prev_limit_type,
                "resulting_limit_type": res_limit_type,
                "previous_limit_value": prev_limit_value,
                "resulting_limit_value": res_limit_value,
                "previous_is_hard_limit": prev_is_hard_limit,
                "resulting_is_hard_limit": res_is_hard_limit,
                "previous_reset_period": prev_reset_period,
                "resulting_reset_period": res_reset_period,
            },
        )

        return quota


def remove_plan_quota(
    *,
    plan_quota_id: uuid.UUID | str,
    actor: Any,
) -> None:
    """Removes a quota from a Draft version."""
    _validate_actor(actor)

    with transaction.atomic():
        quota_init = PlanQuota.objects.get(pk=plan_quota_id)
        pv = _get_and_lock_draft_version(quota_init.plan_version_id)
        quota = (
            PlanQuota.objects.select_for_update()
            .select_related("plan_version__plan")
            .get(pk=plan_quota_id)
        )

        if quota.scope == "product":
            target_id_str = str(quota.plan_product_id)
        elif quota.scope == "module":
            target_id_str = str(quota.plan_module_id)
        elif quota.scope == "capability":
            target_id_str = str(quota.plan_capability_id)
        else:
            target_id_str = None

        record_audit_event(
            action=AuditAction.PLAN_QUOTA_REMOVED,
            target_type=AuditTargetType.PLAN_QUOTA,
            target_id=quota.id,
            target_repr=f"{quota.quota_key}: {quota.limit_type}",
            actor=actor,
            organization_id=None,
            operation_source=AuditOperationSource.INTERACTIVE,
            metadata={
                "plan_id": str(quota.plan_version.plan_id),
                "plan_version_id": str(quota.plan_version_id),
                "scope": quota.scope,
                "target_id": target_id_str,
                "quota_key": quota.quota_key,
                "limit_type": quota.limit_type,
                "limit_value": str(quota.limit_value) if quota.limit_value is not None else None,
            },
        )

        quota.delete()


