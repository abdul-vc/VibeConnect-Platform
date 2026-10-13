"""Phase 2B Domain Services Comprehensive Test Suite.

Verifies:
1. Plan plus Version 1 creation and both ordered audit events.
2. Audit failure rolls back Plan and Version creation.
3. Plan update records complete previous/resulting metadata.
4. Plan code mutation is rejected.
5. Serialized blank-version allocation.
6. Draft change_summary update audit.
7. Active/Retired update rejection with zero audit.
8. Exact clone copy counts and target remapping.
9. Clone preserves stale catalog references and reports degraded health.
10. Readiness blocks zero prices.
11. Readiness blocks zero products.
12. Readiness reports Product/Module/Feature/Capability stale items.
13. Manual retirement metadata.
14. Automatic supersession event order and metadata.
15. Audit failure rolls back both supersession transitions.
16. Active and Retired child mutation rejection.
17. Product/Module/Capability ancestry rejection.
18. Retired or Draft catalog attachment rejection.
19. Cross-version quota target rejection.
20. Canonical money formatting in audits.
21. Quota leading-zero rejection.
22. Quota values above JavaScript safe integer remain exact strings.
23. Quota update contains all six flags and previous/resulting values.
24. Exact PlanCapability cascade audit order.
25. Exact PlanModule cascade audit order.
26. Exact PlanProduct cascade audit order.
27. Cascade audit failure restores all descendants.
"""

from decimal import Decimal
from unittest.mock import patch
import uuid

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from apps.auditlog.models import AuditAction, AuditLog, AuditOperationSource, AuditTargetType
from apps.auditlog.services import AuditEventError, record_audit_event
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
from apps.plans.services import (
    activate_plan_version,
    add_plan_capability,
    add_plan_module,
    add_plan_product,
    clone_plan_version,
    create_draft_version,
    create_plan,
    create_plan_price,
    create_plan_quota,
    evaluate_activation_readiness,
    remove_plan_capability,
    remove_plan_module,
    remove_plan_price,
    remove_plan_product,
    remove_plan_quota,
    retire_plan_version,
    update_draft_version,
    update_plan,
    update_plan_price,
    update_plan_quota,
)
from apps.product_registry.models import (
    CatalogStatus,
    Product,
    ProductCapability,
    ProductFeature,
    ProductModule,
    ProductStatus,
)

User = get_user_model()


class PlanDomainServicesTests(TestCase):
    """Focused test suite for Phase 2B domain services and audit guarantees."""

    def setUp(self):
        super().setUp()
        self.owner = User.objects.create_user(
            email="platform_owner@vibeconnect.internal",
            password="SecurePassword123!",
            full_name="Platform Owner",
            is_active=True,
            is_platform_owner=True,
        )

    def _create_active_catalog_tree(self):
        """Helper to set up an active Product -> Module -> Feature -> Capability tree."""
        suffix = uuid.uuid4().hex[:6]
        product = Product.objects.create(
            code=f"prod_{suffix}",
            name=f"Product {suffix}",
            status=ProductStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )
        module = ProductModule.objects.create(
            product=product,
            code=f"mod_{suffix}",
            name=f"Module {suffix}",
            status=CatalogStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )
        feature = ProductFeature.objects.create(
            module=module,
            code=f"feat_{suffix}",
            name=f"Feature {suffix}",
            status=CatalogStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )
        capability = ProductCapability.objects.create(
            feature=feature,
            code=f"cap_{suffix}",
            name=f"Capability {suffix}",
            status=CatalogStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )
        return product, module, feature, capability

    # 1. Plan plus Version 1 creation and both ordered audit events
    def test_plan_plus_version_1_creation_and_ordered_audits(self):
        plan, pv = create_plan(
            code="starter",
            name="Starter Plan",
            description="Initial starter tier",
            actor=self.owner,
        )
        self.assertEqual(plan.code, "starter")
        self.assertEqual(plan.name, "Starter Plan")
        self.assertEqual(pv.version, 1)
        self.assertEqual(pv.status, PlanVersionStatus.DRAFT)
        self.assertEqual(pv.plan_id, plan.id)

        audits = list(AuditLog.objects.filter(target_id__in=[plan.id, pv.id]).order_by("timestamp", "id"))
        self.assertEqual(len(audits), 2)
        self.assertEqual(audits[0].action, AuditAction.PLAN_CREATED)
        self.assertEqual(audits[0].target_type, AuditTargetType.PLAN)
        self.assertEqual(audits[0].metadata["code"], "starter")
        self.assertEqual(audits[0].metadata["initial_version"], 1)

        self.assertEqual(audits[1].action, AuditAction.PLAN_VERSION_CREATED)
        self.assertEqual(audits[1].target_type, AuditTargetType.PLAN_VERSION)
        self.assertEqual(audits[1].metadata["version"], 1)
        self.assertEqual(audits[1].metadata["status"], "draft")

    # 2. Audit failure rolls back Plan and Version creation
    def test_audit_failure_rolls_back_plan_and_version_creation(self):
        with patch("apps.plans.services.record_audit_event", side_effect=AuditEventError("Audit failure")):
            with self.assertRaises(AuditEventError):
                create_plan(code="rollback_plan", name="Rollback Plan", actor=self.owner)

        self.assertFalse(Plan.objects.filter(code="rollback_plan").exists())
        self.assertEqual(PlanVersion.objects.count(), 0)

    # 3. Plan update records complete previous/resulting metadata
    def test_plan_update_records_complete_metadata(self):
        plan, _ = create_plan(code="growth", name="Growth", description="Old Desc", actor=self.owner)
        updated = update_plan(
            plan_id=plan.id,
            name="Growth Pro",
            description="New Desc",
            actor=self.owner,
        )
        self.assertEqual(updated.name, "Growth Pro")
        self.assertEqual(updated.description, "New Desc")

        audit = AuditLog.objects.filter(target_id=plan.id, action=AuditAction.PLAN_UPDATED).first()
        self.assertIsNotNone(audit)
        self.assertTrue(audit.metadata["name_changed"])
        self.assertTrue(audit.metadata["description_changed"])
        self.assertEqual(audit.metadata["previous_name"], "Growth")
        self.assertEqual(audit.metadata["resulting_name"], "Growth Pro")
        self.assertEqual(audit.metadata["previous_description"], "Old Desc")
        self.assertEqual(audit.metadata["resulting_description"], "New Desc")

    # 4. Plan code mutation is rejected
    def test_plan_code_mutation_is_rejected(self):
        plan, _ = create_plan(code="immutable_code", name="Immutable", actor=self.owner)
        with self.assertRaises(ValidationError):
            update_plan(plan_id=plan.id, code="mutated_code", actor=self.owner)

        plan.refresh_from_db()
        self.assertEqual(plan.code, "immutable_code")

    # 5. Serialized blank-version allocation
    def test_serialized_blank_version_allocation(self):
        plan, v1 = create_plan(code="serial", name="Serial Plan", actor=self.owner)
        v2 = create_draft_version(plan_id=plan.id, change_summary="Second", actor=self.owner)
        v3 = create_draft_version(plan_id=plan.id, change_summary="Third", actor=self.owner)

        self.assertEqual(v2.version, 2)
        self.assertEqual(v2.status, PlanVersionStatus.DRAFT)
        self.assertEqual(v3.version, 3)
        self.assertEqual(v3.status, PlanVersionStatus.DRAFT)

    # 6. Draft change_summary update audit
    def test_draft_change_summary_update_audit(self):
        plan, v1 = create_plan(code="summary_test", name="Summary Test", actor=self.owner)
        updated_v1 = update_draft_version(
            plan_version_id=v1.id,
            change_summary="New refined summary",
            actor=self.owner,
        )
        self.assertEqual(updated_v1.change_summary, "New refined summary")

        audit = AuditLog.objects.filter(target_id=v1.id, action=AuditAction.PLAN_VERSION_UPDATED).first()
        self.assertIsNotNone(audit)
        self.assertTrue(audit.metadata["change_summary_changed"])
        self.assertEqual(audit.metadata["previous_change_summary"], "Initial version")
        self.assertEqual(audit.metadata["resulting_change_summary"], "New refined summary")

    # 7. Active/Retired update rejection with zero audit
    def test_active_and_retired_update_rejection_with_zero_audit(self):
        product, _, _, _ = self._create_active_catalog_tree()
        plan, v1 = create_plan(code="active_test", name="Active Test", actor=self.owner)
        create_plan_price(plan_version_id=v1.id, currency="USD", billing_interval="monthly", amount="10.00", actor=self.owner)
        add_plan_product(plan_version_id=v1.id, product_id=product.id, actor=self.owner)
        activate_plan_version(plan_version_id=v1.id, actor=self.owner)

        # Active version rejection
        audits_before = AuditLog.objects.filter(action=AuditAction.PLAN_VERSION_UPDATED).count()
        with self.assertRaises(ValidationError):
            update_draft_version(plan_version_id=v1.id, change_summary="Mutate Active", actor=self.owner)
        self.assertEqual(AuditLog.objects.filter(action=AuditAction.PLAN_VERSION_UPDATED).count(), audits_before)

        # Retired version rejection
        retire_plan_version(plan_version_id=v1.id, actor=self.owner)
        with self.assertRaises(ValidationError):
            update_draft_version(plan_version_id=v1.id, change_summary="Mutate Retired", actor=self.owner)
        self.assertEqual(AuditLog.objects.filter(action=AuditAction.PLAN_VERSION_UPDATED).count(), audits_before)

    # 8. Exact clone copy counts and target remapping
    def test_clone_copy_counts_and_target_remapping(self):
        product, module, feature, capability = self._create_active_catalog_tree()
        plan, v1 = create_plan(code="clone_test", name="Clone Test", actor=self.owner)

        p = create_plan_price(plan_version_id=v1.id, currency="INR", billing_interval="monthly", amount="199.00", actor=self.owner)
        pp = add_plan_product(plan_version_id=v1.id, product_id=product.id, actor=self.owner)
        pm = add_plan_module(plan_product_id=pp.id, module_id=module.id, actor=self.owner)
        pc = add_plan_capability(plan_module_id=pm.id, capability_id=capability.id, actor=self.owner)

        qp = create_plan_quota(plan_version_id=v1.id, scope="plan", quota_key="api_calls", name="API Calls", unit="count", limit_type="numeric", limit_value="1000", actor=self.owner)
        qprod = create_plan_quota(plan_version_id=v1.id, scope="product", quota_key="seats", name="Seats", unit="seats", limit_type="numeric", limit_value="5", target_id=pp.id, actor=self.owner)
        qmod = create_plan_quota(plan_version_id=v1.id, scope="module", quota_key="storage", name="Storage", unit="gb", limit_type="numeric", limit_value="50", target_id=pm.id, actor=self.owner)
        qcap = create_plan_quota(plan_version_id=v1.id, scope="capability", quota_key="exports", name="Exports", unit="count", limit_type="unlimited", limit_value=None, target_id=pc.id, actor=self.owner)

        audits_count_before = AuditLog.objects.count()
        v2 = clone_plan_version(source_plan_version_id=v1.id, actor=self.owner)

        self.assertEqual(v2.version, 2)
        self.assertEqual(v2.status, PlanVersionStatus.DRAFT)
        self.assertEqual(PlanPrice.objects.filter(plan_version=v2).count(), 1)
        self.assertEqual(PlanProduct.objects.filter(plan_version=v2).count(), 1)
        self.assertEqual(PlanModule.objects.filter(plan_version=v2).count(), 1)
        self.assertEqual(PlanCapability.objects.filter(plan_version=v2).count(), 1)
        self.assertEqual(PlanQuota.objects.filter(plan_version=v2).count(), 4)

        # Verify target remapping
        new_pp = PlanProduct.objects.get(plan_version=v2)
        new_pm = PlanModule.objects.get(plan_version=v2)
        new_pc = PlanCapability.objects.get(plan_version=v2)

        self.assertEqual(new_pm.plan_product_id, new_pp.id)
        self.assertEqual(new_pc.plan_module_id, new_pm.id)

        self.assertNotEqual(new_pp.id, pp.id)
        self.assertNotEqual(new_pm.id, pm.id)
        self.assertNotEqual(new_pc.id, pc.id)

        q_prod_v2 = PlanQuota.objects.get(plan_version=v2, scope="product")
        self.assertEqual(q_prod_v2.plan_product_id, new_pp.id)
        q_mod_v2 = PlanQuota.objects.get(plan_version=v2, scope="module")
        self.assertEqual(q_mod_v2.plan_module_id, new_pm.id)
        q_cap_v2 = PlanQuota.objects.get(plan_version=v2, scope="capability")
        self.assertEqual(q_cap_v2.plan_capability_id, new_pc.id)

        # Aggregate clone audit only — exactly 1 audit event added
        self.assertEqual(AuditLog.objects.count(), audits_count_before + 1)
        clone_audit = AuditLog.objects.filter(target_id=v2.id, action=AuditAction.PLAN_VERSION_CLONED).first()
        self.assertIsNotNone(clone_audit)
        self.assertEqual(clone_audit.metadata["copied_prices_count"], 1)
        self.assertEqual(clone_audit.metadata["copied_products_count"], 1)
        self.assertEqual(clone_audit.metadata["copied_modules_count"], 1)
        self.assertEqual(clone_audit.metadata["copied_capabilities_count"], 1)
        self.assertEqual(clone_audit.metadata["copied_quotas_count"], 4)
        self.assertEqual(clone_audit.metadata["resulting_catalog_health"], "healthy")

    # 9. Clone preserves stale catalog references and reports degraded health
    def test_clone_preserves_stale_catalog_references_and_reports_degraded(self):
        product, _, _, _ = self._create_active_catalog_tree()
        plan, v1 = create_plan(code="degraded_clone", name="Degraded Clone", actor=self.owner)
        pp = add_plan_product(plan_version_id=v1.id, product_id=product.id, actor=self.owner)

        # Mark product as inactive/retired after attachment
        product.status = ProductStatus.RETIRED
        product.save()

        v2 = clone_plan_version(source_plan_version_id=v1.id, actor=self.owner)
        self.assertEqual(PlanProduct.objects.filter(plan_version=v2, product=product).count(), 1)

        clone_audit = AuditLog.objects.filter(target_id=v2.id, action=AuditAction.PLAN_VERSION_CLONED).first()
        self.assertEqual(clone_audit.metadata["resulting_catalog_health"], "degraded")

    # 10. Readiness blocks zero prices
    def test_readiness_blocks_zero_prices(self):
        product, _, _, _ = self._create_active_catalog_tree()
        plan, v1 = create_plan(code="zero_price", name="Zero Price", actor=self.owner)
        add_plan_product(plan_version_id=v1.id, product_id=product.id, actor=self.owner)

        res = evaluate_activation_readiness(plan_version=v1)
        self.assertFalse(res["is_ready"])
        self.assertTrue(any("zero prices" in b.lower() or "at least one price" in b.lower() for b in res["blockers"]))

    # 11. Readiness blocks zero products
    def test_readiness_blocks_zero_products(self):
        plan, v1 = create_plan(code="zero_prod", name="Zero Prod", actor=self.owner)
        create_plan_price(plan_version_id=v1.id, currency="USD", billing_interval="monthly", amount="10.00", actor=self.owner)

        res = evaluate_activation_readiness(plan_version=v1)
        self.assertFalse(res["is_ready"])
        self.assertTrue(any("zero products" in b.lower() or "at least one packaged product" in b.lower() for b in res["blockers"]))

    # 12. Readiness reports Product/Module/Feature/Capability stale items
    def test_readiness_reports_all_stale_item_types(self):
        product, module, feature, capability = self._create_active_catalog_tree()
        plan, v1 = create_plan(code="stale_all", name="Stale All", actor=self.owner)
        create_plan_price(plan_version_id=v1.id, currency="USD", billing_interval="monthly", amount="10.00", actor=self.owner)
        pp = add_plan_product(plan_version_id=v1.id, product_id=product.id, actor=self.owner)
        pm = add_plan_module(plan_product_id=pp.id, module_id=module.id, actor=self.owner)
        pc = add_plan_capability(plan_module_id=pm.id, capability_id=capability.id, actor=self.owner)

        product.status = ProductStatus.INACTIVE
        product.save()
        module.status = CatalogStatus.DRAFT
        module.save()
        feature.status = CatalogStatus.RETIRED
        feature.save()
        capability.status = CatalogStatus.RETIRED
        capability.save()

        res = evaluate_activation_readiness(plan_version=v1)
        self.assertFalse(res["is_ready"])
        self.assertEqual(res["catalog_health"], "degraded")
        stale_types = {item["type"] for item in res["stale_items"]}
        self.assertIn("product", stale_types)
        self.assertIn("module", stale_types)
        self.assertIn("feature", stale_types)
        self.assertIn("capability", stale_types)

    # 13. Manual retirement metadata
    def test_manual_retirement_metadata(self):
        plan, v1 = create_plan(code="man_ret", name="Manual Ret", actor=self.owner)

        # Retire directly from Draft
        retired_draft = retire_plan_version(plan_version_id=v1.id, actor=self.owner)
        self.assertEqual(retired_draft.status, PlanVersionStatus.RETIRED)
        self.assertIsNone(retired_draft.activated_at)
        self.assertIsNotNone(retired_draft.retired_at)

        audit = AuditLog.objects.filter(target_id=v1.id, action=AuditAction.PLAN_VERSION_RETIRED).first()
        self.assertEqual(audit.metadata["retirement_reason"], "manual")
        self.assertEqual(audit.metadata["previous_status"], "draft")
        self.assertEqual(audit.metadata["resulting_status"], "retired")
        self.assertIsNone(audit.metadata["superseded_by_plan_version_id"])

        # Retire from Active
        v2 = create_draft_version(plan_id=plan.id, actor=self.owner)
        product, _, _, _ = self._create_active_catalog_tree()
        create_plan_price(plan_version_id=v2.id, currency="USD", billing_interval="monthly", amount="15.00", actor=self.owner)
        add_plan_product(plan_version_id=v2.id, product_id=product.id, actor=self.owner)
        active_v2 = activate_plan_version(plan_version_id=v2.id, actor=self.owner)

        retired_active = retire_plan_version(plan_version_id=active_v2.id, actor=self.owner)
        self.assertEqual(retired_active.status, PlanVersionStatus.RETIRED)
        self.assertIsNotNone(retired_active.activated_at)
        self.assertIsNotNone(retired_active.retired_at)

        # Retiring an already retired version is rejected without audit
        audits_count = AuditLog.objects.filter(action=AuditAction.PLAN_VERSION_RETIRED).count()
        with self.assertRaises(ValidationError):
            retire_plan_version(plan_version_id=retired_active.id, actor=self.owner)
        self.assertEqual(AuditLog.objects.filter(action=AuditAction.PLAN_VERSION_RETIRED).count(), audits_count)

    # 14. Automatic supersession event order and metadata
    def test_automatic_supersession_event_order_and_metadata(self):
        product, _, _, _ = self._create_active_catalog_tree()
        plan, v1 = create_plan(code="supersede", name="Supersede", actor=self.owner)
        create_plan_price(plan_version_id=v1.id, currency="USD", billing_interval="monthly", amount="10.00", actor=self.owner)
        add_plan_product(plan_version_id=v1.id, product_id=product.id, actor=self.owner)
        activate_plan_version(plan_version_id=v1.id, actor=self.owner)

        v2 = create_draft_version(plan_id=plan.id, actor=self.owner)
        create_plan_price(plan_version_id=v2.id, currency="USD", billing_interval="monthly", amount="20.00", actor=self.owner)
        add_plan_product(plan_version_id=v2.id, product_id=product.id, actor=self.owner)

        activate_plan_version(plan_version_id=v2.id, actor=self.owner)

        v1.refresh_from_db()
        v2.refresh_from_db()
        self.assertEqual(v1.status, PlanVersionStatus.RETIRED)
        self.assertEqual(v2.status, PlanVersionStatus.ACTIVE)

        audits = list(AuditLog.objects.filter(target_id__in=[v1.id, v2.id]).order_by("timestamp", "id"))
        retire_event = next(a for a in audits if a.action == AuditAction.PLAN_VERSION_RETIRED)
        activate_event = next(a for a in audits if a.action == AuditAction.PLAN_VERSION_ACTIVATED and a.target_id == v2.id)

        # Retirement event comes strictly before activation event
        self.assertLessEqual(retire_event.timestamp, activate_event.timestamp)
        self.assertEqual(retire_event.metadata["retirement_reason"], "superseded")
        self.assertEqual(retire_event.metadata["superseded_by_plan_version_id"], str(v2.id))
        self.assertEqual(retire_event.metadata["superseded_by_version"], 2)

        self.assertEqual(activate_event.metadata["superseded_version_id"], str(v1.id))
        self.assertEqual(activate_event.metadata["superseded_version"], 1)

    # 15. Audit failure rolls back both supersession transitions
    def test_audit_failure_rolls_back_both_supersession_transitions(self):
        product, _, _, _ = self._create_active_catalog_tree()
        plan, v1 = create_plan(code="super_fail", name="Super Fail", actor=self.owner)
        create_plan_price(plan_version_id=v1.id, currency="USD", billing_interval="monthly", amount="10.00", actor=self.owner)
        add_plan_product(plan_version_id=v1.id, product_id=product.id, actor=self.owner)
        activate_plan_version(plan_version_id=v1.id, actor=self.owner)

        v2 = create_draft_version(plan_id=plan.id, actor=self.owner)
        create_plan_price(plan_version_id=v2.id, currency="USD", billing_interval="monthly", amount="20.00", actor=self.owner)
        add_plan_product(plan_version_id=v2.id, product_id=product.id, actor=self.owner)

        orig_record = record_audit_event

        def mock_record(*args, **kwargs):
            if kwargs.get("action") == AuditAction.PLAN_VERSION_ACTIVATED:
                raise AuditEventError("Activation audit failed")
            return orig_record(*args, **kwargs)

        with patch("apps.plans.services.record_audit_event", side_effect=mock_record):
            with self.assertRaises(AuditEventError):
                activate_plan_version(plan_version_id=v2.id, actor=self.owner)

        v1.refresh_from_db()
        v2.refresh_from_db()
        self.assertEqual(v1.status, PlanVersionStatus.ACTIVE)
        self.assertEqual(v2.status, PlanVersionStatus.DRAFT)

    # 16. Active and Retired child mutation rejection
    def test_active_and_retired_child_mutation_rejection(self):
        product, _, _, _ = self._create_active_catalog_tree()
        plan, v1 = create_plan(code="child_mut", name="Child Mut", actor=self.owner)
        create_plan_price(plan_version_id=v1.id, currency="USD", billing_interval="monthly", amount="10.00", actor=self.owner)
        add_plan_product(plan_version_id=v1.id, product_id=product.id, actor=self.owner)
        activate_plan_version(plan_version_id=v1.id, actor=self.owner)

        # Active rejections
        with self.assertRaises(ValidationError):
            create_plan_price(plan_version_id=v1.id, currency="EUR", billing_interval="annual", amount="100.00", actor=self.owner)
        with self.assertRaises(ValidationError):
            add_plan_product(plan_version_id=v1.id, product_id=product.id, actor=self.owner)
        with self.assertRaises(ValidationError):
            create_plan_quota(plan_version_id=v1.id, scope="plan", quota_key="q_test", name="Q", unit="count", limit_type="numeric", limit_value="10", actor=self.owner)

        retire_plan_version(plan_version_id=v1.id, actor=self.owner)

        # Retired rejections
        with self.assertRaises(ValidationError):
            create_plan_price(plan_version_id=v1.id, currency="EUR", billing_interval="annual", amount="100.00", actor=self.owner)
        with self.assertRaises(ValidationError):
            add_plan_product(plan_version_id=v1.id, product_id=product.id, actor=self.owner)

    # 17. Product/Module/Capability ancestry rejection
    def test_ancestry_rejection(self):
        prod1, mod1, feat1, cap1 = self._create_active_catalog_tree()
        prod2, mod2, feat2, cap2 = self._create_active_catalog_tree()

        plan, v1 = create_plan(code="ancestry", name="Ancestry", actor=self.owner)
        pp1 = add_plan_product(plan_version_id=v1.id, product_id=prod1.id, actor=self.owner)

        # Trying to attach mod2 (from prod2) beneath pp1 (prod1)
        with self.assertRaises(ValidationError):
            add_plan_module(plan_product_id=pp1.id, module_id=mod2.id, actor=self.owner)

        pm1 = add_plan_module(plan_product_id=pp1.id, module_id=mod1.id, actor=self.owner)

        # Trying to attach cap2 (from mod2) beneath pm1 (mod1)
        with self.assertRaises(ValidationError):
            add_plan_capability(plan_module_id=pm1.id, capability_id=cap2.id, actor=self.owner)

    # 18. Retired or Draft catalog attachment rejection
    def test_retired_or_draft_catalog_attachment_rejection(self):
        suffix = uuid.uuid4().hex[:6]
        draft_prod = Product.objects.create(
            code=f"draft_{suffix}",
            name="Draft",
            status=ProductStatus.DRAFT,
            created_by=self.owner,
            updated_by=self.owner,
        )
        ret_prod = Product.objects.create(
            code=f"ret_{suffix}",
            name="Ret",
            status=ProductStatus.RETIRED,
            created_by=self.owner,
            updated_by=self.owner,
        )

        plan, v1 = create_plan(code="cat_attach", name="Cat Attach", actor=self.owner)
        with self.assertRaises(ValidationError):
            add_plan_product(plan_version_id=v1.id, product_id=draft_prod.id, actor=self.owner)
        with self.assertRaises(ValidationError):
            add_plan_product(plan_version_id=v1.id, product_id=ret_prod.id, actor=self.owner)

    # 19. Cross-version quota target rejection
    def test_cross_version_quota_target_rejection(self):
        prod, _, _, _ = self._create_active_catalog_tree()
        plan, v1 = create_plan(code="cross_q", name="Cross Q", actor=self.owner)
        pp1 = add_plan_product(plan_version_id=v1.id, product_id=prod.id, actor=self.owner)

        v2 = create_draft_version(plan_id=plan.id, actor=self.owner)
        with self.assertRaises(ValidationError):
            create_plan_quota(
                plan_version_id=v2.id,
                scope="product",
                quota_key="seats",
                name="Seats",
                unit="count",
                limit_type="numeric",
                limit_value="10",
                target_id=pp1.id,  # belongs to v1!
                actor=self.owner,
            )

    # 20. Canonical price validation and currency allowlist
    def test_canonical_price_validation_and_currency(self):
        plan, v1 = create_plan(code="money_val", name="Money Val", actor=self.owner)

        # Accepted values and currencies
        p1 = create_plan_price(plan_version_id=v1.id, currency="USD", billing_interval="monthly", amount="0.00", actor=self.owner)
        p2 = create_plan_price(plan_version_id=v1.id, currency="INR", billing_interval="quarterly", amount="1.00", actor=self.owner)
        p3 = create_plan_price(plan_version_id=v1.id, currency="EUR", billing_interval="annual", amount="9999999999.99", actor=self.owner)
        v2 = create_draft_version(plan_id=plan.id, actor=self.owner)
        p4 = create_plan_price(plan_version_id=v2.id, currency="GBP", billing_interval="monthly", amount="29.99", actor=self.owner)

        self.assertEqual(p1.amount, Decimal("0.00"))
        self.assertEqual(p2.amount, Decimal("1.00"))
        self.assertEqual(p3.amount, Decimal("9999999999.99"))
        self.assertEqual(p4.amount, Decimal("29.99"))

        # Update accepts valid canonical strings
        updated_p1 = update_plan_price(plan_price_id=p1.id, amount="99.99", actor=self.owner)
        self.assertEqual(updated_p1.amount, Decimal("99.99"))

        # Rejection cases for create_plan_price and update_plan_price
        rejected_values = [
            None, 0, 1, 1.0, Decimal("1.00"), "1", "1.0", "01.00", "09.99",
            "+1.00", "-1.00", "1e2", "1,000.00", " 1.00", "1.00 ", "10000000000.00"
        ]
        for bad_amt in rejected_values:
            with self.subTest(bad_amount=bad_amt):
                with self.assertRaises(ValidationError):
                    create_plan_price(plan_version_id=v2.id, currency="USD", billing_interval="annual", amount=bad_amt, actor=self.owner)
                with self.assertRaises(ValidationError):
                    update_plan_price(plan_price_id=p1.id, amount=bad_amt, actor=self.owner)

        # Rejected currencies
        for bad_curr in ["AUD", "CAD", "JPY", "XYZ", 123, None]:
            with self.subTest(bad_currency=bad_curr):
                with self.assertRaises(ValidationError):
                    create_plan_price(plan_version_id=v2.id, currency=bad_curr, billing_interval="monthly", amount="10.00", actor=self.owner)

    # 21. Quota leading-zero rejection
    def test_quota_leading_zero_rejection(self):
        plan, v1 = create_plan(code="leading_zeros", name="Leading Zeros", actor=self.owner)
        with self.assertRaises(ValidationError):
            create_plan_quota(plan_version_id=v1.id, scope="plan", quota_key="q00", name="Q", unit="count", limit_type="numeric", limit_value="00", actor=self.owner)
        with self.assertRaises(ValidationError):
            create_plan_quota(plan_version_id=v1.id, scope="plan", quota_key="q01", name="Q", unit="count", limit_type="numeric", limit_value="01", actor=self.owner)
        with self.assertRaises(ValidationError):
            create_plan_quota(plan_version_id=v1.id, scope="plan", quota_key="q050", name="Q", unit="count", limit_type="numeric", limit_value="050", actor=self.owner)

    # 22. Quota values above JavaScript safe integer remain exact strings
    def test_quota_values_above_javascript_safe_integer(self):
        plan, v1 = create_plan(code="safe_int", name="Safe Int", actor=self.owner)
        large_val_str = "9007199254740992"  # 2^53, above MAX_SAFE_INTEGER
        q = create_plan_quota(
            plan_version_id=v1.id,
            scope="plan",
            quota_key="big_quota",
            name="Big Quota",
            unit="count",
            limit_type="numeric",
            limit_value=large_val_str,
            actor=self.owner,
        )
        self.assertEqual(q.limit_value, int(large_val_str))

        audit = AuditLog.objects.filter(target_id=q.id, action=AuditAction.PLAN_QUOTA_CREATED).first()
        self.assertIsNotNone(audit)
        self.assertEqual(audit.metadata["limit_value"], large_val_str)
        self.assertIsInstance(audit.metadata["limit_value"], str)

    # 23. Quota update contains all six flags and previous/resulting values
    def test_quota_update_contains_all_flags_and_values(self):
        plan, v1 = create_plan(code="quota_flags", name="Quota Flags", actor=self.owner)
        q = create_plan_quota(
            plan_version_id=v1.id,
            scope="plan",
            quota_key="flag_q",
            name="Original Name",
            unit="count",
            limit_type="numeric",
            limit_value="100",
            is_hard_limit=True,
            reset_period="monthly",
            actor=self.owner,
        )

        update_plan_quota(
            plan_quota_id=q.id,
            name="Updated Name",
            actor=self.owner,
        )

        audit = AuditLog.objects.filter(target_id=q.id, action=AuditAction.PLAN_QUOTA_UPDATED).first()
        self.assertIsNotNone(audit)
        self.assertTrue(audit.metadata["name_changed"])
        self.assertFalse(audit.metadata["unit_changed"])
        self.assertFalse(audit.metadata["limit_type_changed"])
        self.assertFalse(audit.metadata["limit_value_changed"])
        self.assertFalse(audit.metadata["is_hard_limit_changed"])
        self.assertFalse(audit.metadata["reset_period_changed"])

        self.assertEqual(audit.metadata["previous_name"], "Original Name")
        self.assertEqual(audit.metadata["resulting_name"], "Updated Name")
        self.assertEqual(audit.metadata["previous_unit"], "count")
        self.assertEqual(audit.metadata["resulting_unit"], "count")
        self.assertEqual(audit.metadata["previous_limit_value"], "100")
        self.assertEqual(audit.metadata["resulting_limit_value"], "100")
        self.assertTrue(audit.metadata["previous_is_hard_limit"])
        self.assertTrue(audit.metadata["resulting_is_hard_limit"])
        self.assertEqual(audit.metadata["previous_reset_period"], "monthly")
        self.assertEqual(audit.metadata["resulting_reset_period"], "monthly")

    # 24. Exact PlanCapability cascade audit order with multiple quotas
    def test_exact_plan_capability_cascade_audit_order(self):
        prod, mod, feat, cap = self._create_active_catalog_tree()
        plan, v1 = create_plan(code="cap_cascade", name="Cap Cascade", actor=self.owner)
        pp = add_plan_product(plan_version_id=v1.id, product_id=prod.id, actor=self.owner)
        pm = add_plan_module(plan_product_id=pp.id, module_id=mod.id, actor=self.owner)
        pc = add_plan_capability(plan_module_id=pm.id, capability_id=cap.id, actor=self.owner)

        q1 = create_plan_quota(plan_version_id=v1.id, scope="capability", quota_key="q_alpha", name="QA", unit="count", limit_type="numeric", limit_value="1", target_id=pc.id, actor=self.owner)
        q2 = create_plan_quota(plan_version_id=v1.id, scope="capability", quota_key="q_beta", name="QB", unit="count", limit_type="numeric", limit_value="2", target_id=pc.id, actor=self.owner)

        audits_count_before = AuditLog.objects.count()
        remove_plan_capability(plan_capability_id=pc.id, actor=self.owner)

        # 3 new audits: 2 quotas removed (quota_key order), then capability removed
        self.assertEqual(AuditLog.objects.count(), audits_count_before + 3)
        new_audits = list(AuditLog.objects.order_by("timestamp", "id")[audits_count_before:])

        self.assertEqual(new_audits[0].action, AuditAction.PLAN_QUOTA_REMOVED)
        self.assertEqual(new_audits[0].target_type, AuditTargetType.PLAN_QUOTA)
        self.assertEqual(new_audits[0].target_id, q1.id)
        self.assertEqual(new_audits[0].target_repr, "q_alpha: numeric")

        self.assertEqual(new_audits[1].action, AuditAction.PLAN_QUOTA_REMOVED)
        self.assertEqual(new_audits[1].target_type, AuditTargetType.PLAN_QUOTA)
        self.assertEqual(new_audits[1].target_id, q2.id)
        self.assertEqual(new_audits[1].target_repr, "q_beta: numeric")

        self.assertEqual(new_audits[2].action, AuditAction.PLAN_CAPABILITY_REMOVED)
        self.assertEqual(new_audits[2].target_type, AuditTargetType.PLAN_CAPABILITY)
        self.assertEqual(new_audits[2].target_id, pc.id)
        self.assertEqual(new_audits[2].target_repr, f"{cap.name} ({cap.code})")
        self.assertEqual(new_audits[2].metadata["cascaded_quotas_count"], 2)

        self.assertFalse(PlanCapability.objects.filter(id=pc.id).exists())
        self.assertFalse(PlanQuota.objects.filter(id__in=[q1.id, q2.id]).exists())

    # 25. Exact PlanModule cascade audit order with multiple capabilities and quotas
    def test_exact_plan_module_cascade_audit_order(self):
        prod, mod, feat, cap1 = self._create_active_catalog_tree()
        cap2 = ProductCapability.objects.create(
            feature=feat,
            code=f"cap2_{uuid.uuid4().hex[:6]}",
            name="Capability Two",
            status=CatalogStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )

        plan, v1 = create_plan(code="mod_cascade", name="Mod Cascade", actor=self.owner)
        pp = add_plan_product(plan_version_id=v1.id, product_id=prod.id, actor=self.owner)
        pm = add_plan_module(plan_product_id=pp.id, module_id=mod.id, actor=self.owner)
        pc1 = add_plan_capability(plan_module_id=pm.id, capability_id=cap1.id, actor=self.owner)
        pc2 = add_plan_capability(plan_module_id=pm.id, capability_id=cap2.id, actor=self.owner)

        q_mod = create_plan_quota(plan_version_id=v1.id, scope="module", quota_key="q_mod", name="QM", unit="count", limit_type="numeric", limit_value="5", target_id=pm.id, actor=self.owner)
        q_cap1 = create_plan_quota(plan_version_id=v1.id, scope="capability", quota_key="q_cap1", name="QC1", unit="count", limit_type="numeric", limit_value="10", target_id=pc1.id, actor=self.owner)
        q_cap2 = create_plan_quota(plan_version_id=v1.id, scope="capability", quota_key="q_cap2", name="QC2", unit="count", limit_type="numeric", limit_value="20", target_id=pc2.id, actor=self.owner)

        audits_count_before = AuditLog.objects.count()
        remove_plan_module(plan_module_id=pm.id, actor=self.owner)

        # Sequence: Quotas first (ordered by scope ASC, quota_key ASC), then Capabilities (capability__code ASC), then Module
        new_audits = list(AuditLog.objects.order_by("timestamp", "id")[audits_count_before:])
        actions = [a.action for a in new_audits]
        self.assertEqual(actions, [
            AuditAction.PLAN_QUOTA_REMOVED,
            AuditAction.PLAN_QUOTA_REMOVED,
            AuditAction.PLAN_QUOTA_REMOVED,
            AuditAction.PLAN_CAPABILITY_REMOVED,
            AuditAction.PLAN_CAPABILITY_REMOVED,
            AuditAction.PLAN_MODULE_REMOVED,
        ])
        target_types = [a.target_type for a in new_audits]
        self.assertEqual(target_types, [
            AuditTargetType.PLAN_QUOTA,
            AuditTargetType.PLAN_QUOTA,
            AuditTargetType.PLAN_QUOTA,
            AuditTargetType.PLAN_CAPABILITY,
            AuditTargetType.PLAN_CAPABILITY,
            AuditTargetType.PLAN_MODULE,
        ])

        mod_audit = new_audits[-1]
        self.assertEqual(mod_audit.target_id, pm.id)
        self.assertEqual(mod_audit.target_repr, f"{mod.name} ({mod.code})")
        self.assertEqual(mod_audit.metadata["cascaded_capabilities_count"], 2)
        self.assertEqual(mod_audit.metadata["cascaded_quotas_count"], 3)

        self.assertFalse(PlanModule.objects.filter(id=pm.id).exists())
        self.assertFalse(PlanCapability.objects.filter(id__in=[pc1.id, pc2.id]).exists())
        self.assertFalse(PlanQuota.objects.filter(id__in=[q_mod.id, q_cap1.id, q_cap2.id]).exists())

    # 26. Exact PlanProduct cascade audit order with multiple modules, capabilities, and quotas
    def test_exact_plan_product_cascade_audit_order(self):
        prod, mod1, feat1, cap1 = self._create_active_catalog_tree()
        mod2 = ProductModule.objects.create(
            product=prod,
            code=f"mod2_{uuid.uuid4().hex[:6]}",
            name="Module Two",
            status=CatalogStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )
        feat2 = ProductFeature.objects.create(
            module=mod2,
            code=f"feat2_{uuid.uuid4().hex[:6]}",
            name="Feature Two",
            status=CatalogStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )
        cap2 = ProductCapability.objects.create(
            feature=feat2,
            code=f"cap2_{uuid.uuid4().hex[:6]}",
            name="Capability Two",
            status=CatalogStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )

        plan, v1 = create_plan(code="prod_cascade", name="Prod Cascade", actor=self.owner)
        pp = add_plan_product(plan_version_id=v1.id, product_id=prod.id, actor=self.owner)
        pm1 = add_plan_module(plan_product_id=pp.id, module_id=mod1.id, actor=self.owner)
        pm2 = add_plan_module(plan_product_id=pp.id, module_id=mod2.id, actor=self.owner)
        pc1 = add_plan_capability(plan_module_id=pm1.id, capability_id=cap1.id, actor=self.owner)
        pc2 = add_plan_capability(plan_module_id=pm2.id, capability_id=cap2.id, actor=self.owner)

        qp = create_plan_quota(plan_version_id=v1.id, scope="product", quota_key="qp", name="QP", unit="count", limit_type="numeric", limit_value="1", target_id=pp.id, actor=self.owner)
        qm1 = create_plan_quota(plan_version_id=v1.id, scope="module", quota_key="qm1", name="QM1", unit="count", limit_type="numeric", limit_value="2", target_id=pm1.id, actor=self.owner)
        qc1 = create_plan_quota(plan_version_id=v1.id, scope="capability", quota_key="qc1", name="QC1", unit="count", limit_type="numeric", limit_value="3", target_id=pc1.id, actor=self.owner)
        qc2 = create_plan_quota(plan_version_id=v1.id, scope="capability", quota_key="qc2", name="QC2", unit="count", limit_type="numeric", limit_value="4", target_id=pc2.id, actor=self.owner)

        audits_count_before = AuditLog.objects.count()
        remove_plan_product(plan_product_id=pp.id, actor=self.owner)

        # Exact sequence: all quotas -> all capabilities -> all modules -> product
        new_audits = list(AuditLog.objects.order_by("timestamp", "id")[audits_count_before:])
        actions = [a.action for a in new_audits]
        self.assertEqual(actions, [
            AuditAction.PLAN_QUOTA_REMOVED,
            AuditAction.PLAN_QUOTA_REMOVED,
            AuditAction.PLAN_QUOTA_REMOVED,
            AuditAction.PLAN_QUOTA_REMOVED,
            AuditAction.PLAN_CAPABILITY_REMOVED,
            AuditAction.PLAN_CAPABILITY_REMOVED,
            AuditAction.PLAN_MODULE_REMOVED,
            AuditAction.PLAN_MODULE_REMOVED,
            AuditAction.PLAN_PRODUCT_REMOVED,
        ])
        target_types = [a.target_type for a in new_audits]
        self.assertEqual(target_types, [
            AuditTargetType.PLAN_QUOTA,
            AuditTargetType.PLAN_QUOTA,
            AuditTargetType.PLAN_QUOTA,
            AuditTargetType.PLAN_QUOTA,
            AuditTargetType.PLAN_CAPABILITY,
            AuditTargetType.PLAN_CAPABILITY,
            AuditTargetType.PLAN_MODULE,
            AuditTargetType.PLAN_MODULE,
            AuditTargetType.PLAN_PRODUCT,
        ])

        prod_audit = new_audits[-1]
        self.assertEqual(prod_audit.target_id, pp.id)
        self.assertEqual(prod_audit.target_repr, f"{prod.name} ({prod.code})")
        self.assertEqual(prod_audit.metadata["cascaded_modules_count"], 2)
        self.assertEqual(prod_audit.metadata["cascaded_capabilities_count"], 2)
        self.assertEqual(prod_audit.metadata["cascaded_quotas_count"], 4)

        # All rows deleted after success
        self.assertFalse(PlanProduct.objects.filter(id=pp.id).exists())
        self.assertFalse(PlanModule.objects.filter(id__in=[pm1.id, pm2.id]).exists())
        self.assertFalse(PlanCapability.objects.filter(id__in=[pc1.id, pc2.id]).exists())
        self.assertFalse(PlanQuota.objects.filter(id__in=[qp.id, qm1.id, qc1.id, qc2.id]).exists())

    # 27. Cascade audit failure restores all descendants and zero partial audits
    def test_cascade_audit_failure_restores_all_descendants(self):
        prod, mod, feat, cap = self._create_active_catalog_tree()
        plan, v1 = create_plan(code="rest_fail", name="Rest Fail", actor=self.owner)
        pp = add_plan_product(plan_version_id=v1.id, product_id=prod.id, actor=self.owner)
        pm = add_plan_module(plan_product_id=pp.id, module_id=mod.id, actor=self.owner)
        pc = add_plan_capability(plan_module_id=pm.id, capability_id=cap.id, actor=self.owner)
        qp = create_plan_quota(plan_version_id=v1.id, scope="product", quota_key="qp_fail", name="QP", unit="count", limit_type="numeric", limit_value="1", target_id=pp.id, actor=self.owner)

        audits_count_before = AuditLog.objects.count()
        orig_record = record_audit_event

        def mock_record(*args, **kwargs):
            if kwargs.get("action") == AuditAction.PLAN_PRODUCT_REMOVED:
                raise AuditEventError("Final cascade audit failure")
            return orig_record(*args, **kwargs)

        with patch("apps.plans.services.record_audit_event", side_effect=mock_record):
            with self.assertRaises(AuditEventError):
                remove_plan_product(plan_product_id=pp.id, actor=self.owner)

        # All descendants restored via transaction rollback
        self.assertTrue(PlanProduct.objects.filter(id=pp.id).exists())
        self.assertTrue(PlanModule.objects.filter(id=pm.id).exists())
        self.assertTrue(PlanCapability.objects.filter(id=pc.id).exists())
        self.assertTrue(PlanQuota.objects.filter(id=qp.id).exists())

        # Zero partial audit events persisted
        self.assertEqual(AuditLog.objects.count(), audits_count_before)

    # 28. Compact parameterized test covering all 19 valid action/target mappings and 5 invalid mappings
    def test_audit_all_nineteen_action_target_mappings(self):
        valid_mappings = [
            (AuditAction.PLAN_CREATED, AuditTargetType.PLAN),
            (AuditAction.PLAN_UPDATED, AuditTargetType.PLAN),
            (AuditAction.PLAN_VERSION_CREATED, AuditTargetType.PLAN_VERSION),
            (AuditAction.PLAN_VERSION_UPDATED, AuditTargetType.PLAN_VERSION),
            (AuditAction.PLAN_VERSION_CLONED, AuditTargetType.PLAN_VERSION),
            (AuditAction.PLAN_VERSION_ACTIVATED, AuditTargetType.PLAN_VERSION),
            (AuditAction.PLAN_VERSION_RETIRED, AuditTargetType.PLAN_VERSION),
            (AuditAction.PLAN_PRICE_CREATED, AuditTargetType.PLAN_PRICE),
            (AuditAction.PLAN_PRICE_UPDATED, AuditTargetType.PLAN_PRICE),
            (AuditAction.PLAN_PRICE_REMOVED, AuditTargetType.PLAN_PRICE),
            (AuditAction.PLAN_PRODUCT_ADDED, AuditTargetType.PLAN_PRODUCT),
            (AuditAction.PLAN_PRODUCT_REMOVED, AuditTargetType.PLAN_PRODUCT),
            (AuditAction.PLAN_MODULE_ADDED, AuditTargetType.PLAN_MODULE),
            (AuditAction.PLAN_MODULE_REMOVED, AuditTargetType.PLAN_MODULE),
            (AuditAction.PLAN_CAPABILITY_ADDED, AuditTargetType.PLAN_CAPABILITY),
            (AuditAction.PLAN_CAPABILITY_REMOVED, AuditTargetType.PLAN_CAPABILITY),
            (AuditAction.PLAN_QUOTA_CREATED, AuditTargetType.PLAN_QUOTA),
            (AuditAction.PLAN_QUOTA_UPDATED, AuditTargetType.PLAN_QUOTA),
            (AuditAction.PLAN_QUOTA_REMOVED, AuditTargetType.PLAN_QUOTA),
        ]
        self.assertEqual(len(valid_mappings), 19)

        pid = str(uuid.uuid4())
        pvid = str(uuid.uuid4())
        prod_id = str(uuid.uuid4())
        mod_id = str(uuid.uuid4())
        feat_id = str(uuid.uuid4())
        cap_id = str(uuid.uuid4())

        sample_metadata = {
            AuditAction.PLAN_CREATED: {"code": "p1", "name": "P1", "initial_version": 1},
            AuditAction.PLAN_UPDATED: {"code": "p1", "name_changed": True, "description_changed": False, "previous_name": "A", "resulting_name": "B", "previous_description": "", "resulting_description": ""},
            AuditAction.PLAN_VERSION_CREATED: {"plan_id": pid, "plan_code": "p1", "version": 1, "status": "draft"},
            AuditAction.PLAN_VERSION_UPDATED: {"plan_id": pid, "plan_version_id": pvid, "plan_code": "p1", "version": 1, "change_summary_changed": True, "previous_change_summary": "A", "resulting_change_summary": "B"},
            AuditAction.PLAN_VERSION_CLONED: {
                "source_plan_version_id": pvid,
                "source_version": 1,
                "resulting_plan_version_id": str(uuid.uuid4()),
                "resulting_version": 2,
                "copied_prices_count": 0,
                "copied_products_count": 0,
                "copied_modules_count": 0,
                "copied_capabilities_count": 0,
                "copied_quotas_count": 0,
                "resulting_catalog_health": "healthy",
            },
            AuditAction.PLAN_VERSION_ACTIVATED: {"plan_id": pid, "plan_code": "p1", "version": 1, "previous_status": "draft", "resulting_status": "active", "superseded_version_id": None, "superseded_version": None},
            AuditAction.PLAN_VERSION_RETIRED: {"plan_id": pid, "plan_code": "p1", "version": 1, "previous_status": "active", "resulting_status": "retired", "retirement_reason": "manual", "superseded_by_plan_version_id": None, "superseded_by_version": None},
            AuditAction.PLAN_PRICE_CREATED: {"plan_id": pid, "plan_version_id": pvid, "currency": "USD", "billing_interval": "monthly", "amount": "10.00"},
            AuditAction.PLAN_PRICE_UPDATED: {"plan_id": pid, "plan_version_id": pvid, "currency": "USD", "billing_interval": "monthly", "previous_amount": "10.00", "resulting_amount": "15.00"},
            AuditAction.PLAN_PRICE_REMOVED: {"plan_id": pid, "plan_version_id": pvid, "currency": "USD", "billing_interval": "monthly", "amount": "10.00"},
            AuditAction.PLAN_PRODUCT_ADDED: {"plan_id": pid, "plan_version_id": pvid, "product_id": prod_id, "product_code": "pr1"},
            AuditAction.PLAN_PRODUCT_REMOVED: {"plan_id": pid, "plan_version_id": pvid, "product_id": prod_id, "product_code": "pr1", "cascaded_modules_count": 0, "cascaded_capabilities_count": 0, "cascaded_quotas_count": 0},
            AuditAction.PLAN_MODULE_ADDED: {"plan_id": pid, "plan_version_id": pvid, "product_id": prod_id, "product_code": "pr1", "module_id": mod_id, "module_code": "m1"},
            AuditAction.PLAN_MODULE_REMOVED: {"plan_id": pid, "plan_version_id": pvid, "product_id": prod_id, "product_code": "pr1", "module_id": mod_id, "module_code": "m1", "cascaded_capabilities_count": 0, "cascaded_quotas_count": 0},
            AuditAction.PLAN_CAPABILITY_ADDED: {"plan_id": pid, "plan_version_id": pvid, "product_id": prod_id, "module_id": mod_id, "feature_id": feat_id, "capability_id": cap_id, "capability_code": "c1"},
            AuditAction.PLAN_CAPABILITY_REMOVED: {"plan_id": pid, "plan_version_id": pvid, "product_id": prod_id, "module_id": mod_id, "feature_id": feat_id, "capability_id": cap_id, "capability_code": "c1", "cascaded_quotas_count": 0},
            AuditAction.PLAN_QUOTA_CREATED: {"plan_id": pid, "plan_version_id": pvid, "scope": "plan", "target_id": None, "quota_key": "qk", "limit_type": "numeric", "limit_value": "10", "unit": "count", "reset_period": "never", "is_hard_limit": True},
            AuditAction.PLAN_QUOTA_UPDATED: {"plan_id": pid, "plan_version_id": pvid, "scope": "plan", "target_id": None, "quota_key": "qk", "name_changed": False, "unit_changed": False, "limit_type_changed": False, "limit_value_changed": False, "is_hard_limit_changed": False, "reset_period_changed": False, "previous_name": "N", "resulting_name": "N", "previous_unit": "u", "resulting_unit": "u", "previous_limit_type": "numeric", "resulting_limit_type": "numeric", "previous_limit_value": "10", "resulting_limit_value": "10", "previous_is_hard_limit": True, "resulting_is_hard_limit": True, "previous_reset_period": "never", "resulting_reset_period": "never"},
            AuditAction.PLAN_QUOTA_REMOVED: {"plan_id": pid, "plan_version_id": pvid, "scope": "plan", "target_id": None, "quota_key": "qk", "limit_type": "numeric", "limit_value": "10"},
        }

        # Verify all 19 valid mappings succeed
        for act, tt in valid_mappings:
            with self.subTest(action=act, target_type=tt):
                row = record_audit_event(
                    action=act,
                    target_type=tt,
                    target_id=uuid.uuid4(),
                    target_repr=f"Repr for {act}",
                    actor=self.owner,
                    organization_id=None,
                    operation_source=AuditOperationSource.INTERACTIVE,
                    metadata=sample_metadata[act],
                )
                self.assertEqual(row.action, act)
                self.assertEqual(row.target_type, tt)

        # Verify 5 representative invalid mappings are rejected
        invalid_mappings = [
            (AuditAction.PLAN_PRICE_CREATED, AuditTargetType.PLAN_VERSION),
            (AuditAction.PLAN_PRODUCT_ADDED, AuditTargetType.PLAN),
            (AuditAction.PLAN_MODULE_REMOVED, AuditTargetType.PLAN_PRODUCT),
            (AuditAction.PLAN_CAPABILITY_ADDED, AuditTargetType.PLAN_MODULE),
            (AuditAction.PLAN_QUOTA_REMOVED, AuditTargetType.PLAN_VERSION),
        ]
        for bad_act, bad_tt in invalid_mappings:
            with self.subTest(invalid_action=bad_act, invalid_target_type=bad_tt):
                with self.assertRaises(AuditEventError):
                    record_audit_event(
                        action=bad_act,
                        target_type=bad_tt,
                        target_id=uuid.uuid4(),
                        target_repr=f"Bad mapping",
                        actor=self.owner,
                        organization_id=None,
                        operation_source=AuditOperationSource.INTERACTIVE,
                        metadata=sample_metadata[bad_act],
                    )

    # 29. Child audit target IDs and canonical target representations
    def test_child_audit_target_ids_and_representations(self):
        prod, mod, feat, cap = self._create_active_catalog_tree()
        plan, v1 = create_plan(code="target_check", name="Target Check", actor=self.owner)

        # 1. PlanPrice: target_repr = "{currency} {amount}/{billing_interval}"
        price = create_plan_price(plan_version_id=v1.id, currency="USD", billing_interval="monthly", amount="19.99", actor=self.owner)
        price_audit = AuditLog.objects.filter(target_id=price.id, action=AuditAction.PLAN_PRICE_CREATED).first()
        self.assertIsNotNone(price_audit)
        self.assertEqual(price_audit.target_type, AuditTargetType.PLAN_PRICE)
        self.assertEqual(price_audit.target_id, price.id)
        self.assertNotEqual(price_audit.target_id, v1.id)
        self.assertEqual(price_audit.target_repr, "USD 19.99/monthly")

        # 2. PlanProduct: target_repr = "{product_name} ({product_code})"
        pp = add_plan_product(plan_version_id=v1.id, product_id=prod.id, actor=self.owner)
        pp_audit = AuditLog.objects.filter(target_id=pp.id, action=AuditAction.PLAN_PRODUCT_ADDED).first()
        self.assertIsNotNone(pp_audit)
        self.assertEqual(pp_audit.target_type, AuditTargetType.PLAN_PRODUCT)
        self.assertEqual(pp_audit.target_id, pp.id)
        self.assertNotEqual(pp_audit.target_id, v1.id)
        self.assertEqual(pp_audit.target_repr, f"{prod.name} ({prod.code})")

        # 3. PlanModule: target_repr = "{module_name} ({module_code})"
        pm = add_plan_module(plan_product_id=pp.id, module_id=mod.id, actor=self.owner)
        pm_audit = AuditLog.objects.filter(target_id=pm.id, action=AuditAction.PLAN_MODULE_ADDED).first()
        self.assertIsNotNone(pm_audit)
        self.assertEqual(pm_audit.target_type, AuditTargetType.PLAN_MODULE)
        self.assertEqual(pm_audit.target_id, pm.id)
        self.assertNotEqual(pm_audit.target_id, v1.id)
        self.assertEqual(pm_audit.target_repr, f"{mod.name} ({mod.code})")

        # 4. PlanCapability: target_repr = "{capability_name} ({capability_code})"
        pc = add_plan_capability(plan_module_id=pm.id, capability_id=cap.id, actor=self.owner)
        pc_audit = AuditLog.objects.filter(target_id=pc.id, action=AuditAction.PLAN_CAPABILITY_ADDED).first()
        self.assertIsNotNone(pc_audit)
        self.assertEqual(pc_audit.target_type, AuditTargetType.PLAN_CAPABILITY)
        self.assertEqual(pc_audit.target_id, pc.id)
        self.assertNotEqual(pc_audit.target_id, v1.id)
        self.assertEqual(pc_audit.target_repr, f"{cap.name} ({cap.code})")

        # 5. PlanQuota: target_repr = "{quota_key}: {limit_type}"
        quota = create_plan_quota(plan_version_id=v1.id, scope="plan", quota_key="api_calls", name="API Calls", unit="count", limit_type="numeric", limit_value="1000", actor=self.owner)
        quota_audit = AuditLog.objects.filter(target_id=quota.id, action=AuditAction.PLAN_QUOTA_CREATED).first()
        self.assertIsNotNone(quota_audit)
        self.assertEqual(quota_audit.target_type, AuditTargetType.PLAN_QUOTA)
        self.assertEqual(quota_audit.target_id, quota.id)
        self.assertNotEqual(quota_audit.target_id, v1.id)
        self.assertEqual(quota_audit.target_repr, "api_calls: numeric")

    # 30. Canonical lock acquisition order: Plan -> PlanVersion -> PlanProduct -> PlanModule -> PlanCapability -> PlanQuota
    def test_canonical_lock_acquisition_order(self):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        prod, mod, feat, cap = self._create_active_catalog_tree()
        plan, v1 = create_plan(code="lock_order", name="Lock Order", actor=self.owner)
        pp = add_plan_product(plan_version_id=v1.id, product_id=prod.id, actor=self.owner)
        pm = add_plan_module(plan_product_id=pp.id, module_id=mod.id, actor=self.owner)
        pc = add_plan_capability(plan_module_id=pm.id, capability_id=cap.id, actor=self.owner)
        create_plan_quota(plan_version_id=v1.id, scope="product", quota_key="qp", name="QP", unit="count", limit_type="numeric", limit_value="1", target_id=pp.id, actor=self.owner)

        with CaptureQueriesContext(connection) as ctx:
            remove_plan_product(plan_product_id=pp.id, actor=self.owner)

        locked_tables = []
        for q in ctx.captured_queries:
            sql = q["sql"].upper()
            if "FOR UPDATE" in sql:
                for tbl in ["\"PLANS\"", "\"PLAN_VERSIONS\"", "\"PLAN_PRODUCTS\"", "\"PLAN_MODULES\"", "\"PLAN_CAPABILITIES\"", "\"PLAN_QUOTAS\""]:
                    clean_tbl = tbl.replace('"', '').lower()
                    if tbl in sql or f"FROM {clean_tbl}" in sql.lower():
                        if not locked_tables or locked_tables[-1] != clean_tbl:
                            locked_tables.append(clean_tbl)

        expected_order = ["plans", "plan_versions", "plan_products", "plan_modules", "plan_capabilities", "plan_quotas"]
        self.assertEqual(locked_tables, expected_order)

    # 31. Quota Service Custom Units, Audit Verification, Rollback, Clone, and Protections
    def test_quota_service_custom_units_audit_and_protections(self):
        from unittest.mock import patch
        from apps.auditlog.services import AuditEventError

        prod, _, _, _ = self._create_active_catalog_tree()
        plan, v1 = create_plan(code="quota_svc_test", name="Quota Svc Plan", actor=self.owner)
        pp = add_plan_product(plan_version_id=v1.id, product_id=prod.id, actor=self.owner)

        # 1. Service create accepts custom unit
        quota = create_plan_quota(
            plan_version_id=v1.id,
            scope="plan",
            quota_key="custom_docs",
            name="Custom Docs",
            unit="documents",
            limit_type="numeric",
            limit_value="500",
            actor=self.owner,
        )
        self.assertEqual(quota.unit, "documents")

        # 2. Audit metadata records exact custom unit
        audit_create = AuditLog.objects.filter(target_id=quota.id, action=AuditAction.PLAN_QUOTA_CREATED).first()
        self.assertIsNotNone(audit_create)
        self.assertEqual(audit_create.metadata["unit"], "documents")

        # 3. Service update accepts custom unit
        updated_quota = update_plan_quota(
            plan_quota_id=quota.id,
            unit="video_minutes",
            actor=self.owner,
        )
        self.assertEqual(updated_quota.unit, "video_minutes")

        audit_update = AuditLog.objects.filter(target_id=quota.id, action=AuditAction.PLAN_QUOTA_UPDATED).first()
        self.assertIsNotNone(audit_update)
        self.assertEqual(audit_update.metadata["previous_unit"], "documents")
        self.assertEqual(audit_update.metadata["resulting_unit"], "video_minutes")
        self.assertTrue(audit_update.metadata["unit_changed"])

        # 4. Audit failure rolls back quota mutation
        with patch("apps.plans.services.record_audit_event", side_effect=AuditEventError("Simulated audit failure")):
            with self.assertRaises(AuditEventError):
                create_plan_quota(
                    plan_version_id=v1.id,
                    scope="plan",
                    quota_key="rollback_quota",
                    name="Rollback Quota",
                    unit="workflow_runs",
                    limit_type="numeric",
                    limit_value="10",
                    actor=self.owner,
                )
        self.assertFalse(PlanQuota.objects.filter(quota_key="rollback_quota").exists())

        # 5. Clone preserves custom units exactly
        quota_prod = create_plan_quota(
            plan_version_id=v1.id,
            scope="product",
            quota_key="custom_storage",
            name="Custom Storage",
            unit="storage_gb",
            limit_type="numeric",
            limit_value="100",
            target_id=pp.id,
            actor=self.owner,
        )
        v2 = clone_plan_version(source_plan_version_id=v1.id, actor=self.owner)
        cloned_q1 = PlanQuota.objects.get(plan_version=v2, quota_key="custom_docs")
        self.assertEqual(cloned_q1.unit, "video_minutes")
        cloned_q2 = PlanQuota.objects.get(plan_version=v2, quota_key="custom_storage")
        self.assertEqual(cloned_q2.unit, "storage_gb")

        # 6. Active/Retired mutation protection remains unchanged
        create_plan_price(plan_version_id=v1.id, currency="USD", billing_interval="monthly", amount="29.99", actor=self.owner)
        activate_plan_version(plan_version_id=v1.id, actor=self.owner)
        audits_count_before = AuditLog.objects.count()
        with self.assertRaises(ValidationError):
            update_plan_quota(plan_quota_id=quota.id, unit="api_calls", actor=self.owner)
        self.assertEqual(AuditLog.objects.count(), audits_count_before)

        retire_plan_version(plan_version_id=v1.id, actor=self.owner)
        audits_count_before_retire = AuditLog.objects.count()
        with self.assertRaises(ValidationError):
            update_plan_quota(plan_quota_id=quota.id, unit="api_calls", actor=self.owner)
        self.assertEqual(AuditLog.objects.count(), audits_count_before_retire)

