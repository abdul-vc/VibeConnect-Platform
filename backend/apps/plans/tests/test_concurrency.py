"""Phase 2B PostgreSQL Concurrency, Locking, Atomic Rollback, and Failure-Injection Test Suite.

Verifies:
1. Canonical top-down locking order and deadlock-free operation under concurrency.
2. Concurrent Plan-Version allocation contiguousness and serialization.
3. Concurrent activation single-Active guarantee and automatic supersession.
4. Concurrent active-version mutation protection.
5. Concurrent duplicate commercial rows uniqueness and clean error handling.
6. Packaging ancestry race conditions and orphan prevention.
7. Clone consistency under concurrent source mutation.
8. Cascade removal determinism, descendant-first auditing, and atomic rollback.
9. Failure-injection and atomic rollback across all 14 transaction categories.
10. Database isolation and connection cleanup.
"""

from decimal import Decimal
import os
import threading
import time
from unittest.mock import patch
import uuid

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, close_old_connections, connection, transaction
from django.test import TransactionTestCase
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


def _run_in_threads(tasks: list, timeout: float = 15.0) -> tuple[list, list]:
    """Executes callables in separate worker threads with isolated DB connections."""
    n = len(tasks)
    results = [None] * n
    exceptions = [None] * n

    def _worker(idx: int, func):
        close_old_connections()
        try:
            results[idx] = func()
        except Exception as exc:
            exceptions[idx] = exc
        finally:
            close_old_connections()

    threads = [threading.Thread(target=_worker, args=(i, tasks[i])) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=timeout)
        if t.is_alive():
            raise TimeoutError(f"Worker thread {t.name} timed out after {timeout}s (possible deadlock)")

    return results, exceptions


class PlanPostgresConcurrencyTests(TransactionTestCase):
    """Real PostgreSQL multi-threaded concurrency and transaction rollback test suite."""

    reset_sequences = True

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        current_db = settings.DATABASES["default"]["NAME"]
        expected_db = os.environ.get("TEST_DATABASE_NAME", "").strip() or current_db
        assert expected_db, "TEST_DATABASE_NAME could not be determined."
        assert expected_db != "vibeconnect_local", (
            "Concurrency tests must not run against the development database ('vibeconnect_local')."
        )
        assert current_db != "vibeconnect_local", (
            "Safety assertion failed: running against development database ('vibeconnect_local')."
        )
        assert current_db == expected_db, (
            f"DB Name mismatch: expected '{expected_db}', got '{current_db}'"
        )
        test_cfg_db = settings.DATABASES["default"].get("TEST", {}).get("NAME")
        if test_cfg_db:
            assert test_cfg_db != "vibeconnect_local", (
                "Safety assertion failed: TEST DB configured as 'vibeconnect_local'."
            )

    def setUp(self):
        super().setUp()
        close_old_connections()
        self.owner = User.objects.create_user(
            email=f"owner_{uuid.uuid4().hex[:8]}@vibeconnect.internal",
            password="SecurePassword123!",
            full_name="Platform Owner",
            is_active=True,
            is_platform_owner=True,
        )

        p_code = f"prod_{uuid.uuid4().hex[:6]}"
        self.catalog_product = Product.objects.create(
            code=p_code,
            name="Core Product",
            status=ProductStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )
        self.catalog_module = ProductModule.objects.create(
            product=self.catalog_product,
            code=f"mod_{uuid.uuid4().hex[:6]}",
            name="Core Module",
            status=CatalogStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )
        self.catalog_feature = ProductFeature.objects.create(
            module=self.catalog_module,
            code=f"feat_{uuid.uuid4().hex[:6]}",
            name="Core Feature",
            status=CatalogStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )
        self.catalog_capability = ProductCapability.objects.create(
            feature=self.catalog_feature,
            code=f"cap_{uuid.uuid4().hex[:6]}",
            name="Core Capability",
            status=CatalogStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )

    def tearDown(self):
        close_old_connections()
        super().tearDown()

    def _setup_ready_version(self, plan: Plan, version: PlanVersion) -> None:
        """Configures price and product on a draft version so it passes activation readiness."""
        create_plan_price(
            plan_version_id=version.id,
            currency="USD",
            billing_interval="monthly",
            amount="29.99",
            actor=self.owner,
        )
        add_plan_product(
            plan_version_id=version.id,
            product_id=self.catalog_product.id,
            actor=self.owner,
        )

    # -----------------------------------------------------------------------
    # 6. Concurrent Plan-Version Allocation
    # -----------------------------------------------------------------------
    def test_concurrent_plan_version_allocation(self):
        """5 concurrent workers creating versions under one Plan get contiguous unique integers."""
        plan, v1 = create_plan(
            code=f"p_{uuid.uuid4().hex[:6]}",
            name="Plan For Allocation",
            actor=self.owner,
        )

        num_workers = 5
        barrier = threading.Barrier(num_workers)

        def _alloc_task():
            barrier.wait(timeout=5.0)
            return create_draft_version(
                plan_id=plan.id,
                change_summary="Concurrent version",
                actor=self.owner,
            )

        results, exceptions = _run_in_threads([_alloc_task for _ in range(num_workers)])

        # Assert no exceptions
        for exc in exceptions:
            self.assertIsNone(exc, f"Version allocation worker raised exception: {exc}")

        # Assert contiguous versions allocated from 2 to 6
        allocated_versions = sorted([pv.version for pv in results])
        self.assertEqual(allocated_versions, [2, 3, 4, 5, 6])

        # Assert persisted rows in DB
        db_versions = list(
            PlanVersion.objects.filter(plan=plan).order_by("version").values_list("version", flat=True)
        )
        self.assertEqual(db_versions, [1, 2, 3, 4, 5, 6])

        # Assert audit logs: exactly 1 per created version
        for pv in results:
            audit = AuditLog.objects.get(
                action=AuditAction.PLAN_VERSION_CREATED,
                target_id=pv.id,
            )
            self.assertEqual(audit.metadata["version"], pv.version)
            self.assertEqual(audit.metadata["plan_id"], str(plan.id))

    def test_concurrent_version_allocation_two_different_plans(self):
        """Concurrent version creation on two distinct Plans does not serialize or block each other."""
        plan_a, _ = create_plan(code=f"pa_{uuid.uuid4().hex[:6]}", name="Plan A", actor=self.owner)
        plan_b, _ = create_plan(code=f"pb_{uuid.uuid4().hex[:6]}", name="Plan B", actor=self.owner)

        barrier = threading.Barrier(4)

        def _task_a():
            barrier.wait(timeout=5.0)
            return create_draft_version(plan_id=plan_a.id, actor=self.owner)

        def _task_b():
            barrier.wait(timeout=5.0)
            return create_draft_version(plan_id=plan_b.id, actor=self.owner)

        results, exceptions = _run_in_threads([_task_a, _task_a, _task_b, _task_b])
        for exc in exceptions:
            self.assertIsNone(exc)

        versions_a = list(PlanVersion.objects.filter(plan=plan_a).order_by("version").values_list("version", flat=True))
        versions_b = list(PlanVersion.objects.filter(plan=plan_b).order_by("version").values_list("version", flat=True))
        self.assertEqual(versions_a, [1, 2, 3])
        self.assertEqual(versions_b, [1, 2, 3])

    # -----------------------------------------------------------------------
    # 7. Concurrent Activation and Single-Active Guarantee
    # -----------------------------------------------------------------------
    def test_concurrent_activation_two_drafts_of_same_plan(self):
        """Simultaneous activation of two Draft versions of the same Plan maintains single-Active guarantee."""
        plan, v1 = create_plan(code=f"p_{uuid.uuid4().hex[:6]}", name="Activation Plan", actor=self.owner)
        self._setup_ready_version(plan, v1)
        v1 = activate_plan_version(plan_version_id=v1.id, actor=self.owner)
        self.assertEqual(v1.status, PlanVersionStatus.ACTIVE)

        v2 = create_draft_version(plan_id=plan.id, change_summary="Draft 2", actor=self.owner)
        self._setup_ready_version(plan, v2)

        v3 = create_draft_version(plan_id=plan.id, change_summary="Draft 3", actor=self.owner)
        self._setup_ready_version(plan, v3)

        barrier = threading.Barrier(2)

        def _activate_v2():
            barrier.wait(timeout=5.0)
            return activate_plan_version(plan_version_id=v2.id, actor=self.owner)

        def _activate_v3():
            barrier.wait(timeout=5.0)
            return activate_plan_version(plan_version_id=v3.id, actor=self.owner)

        results, exceptions = _run_in_threads([_activate_v2, _activate_v3])

        # Assert no unexpected crashes
        for exc in exceptions:
            self.assertIsNone(exc, f"Activation worker failed: {exc}")

        # Assert single-Active guarantee: exactly ONE version is Active
        active_versions = list(PlanVersion.objects.filter(plan=plan, status=PlanVersionStatus.ACTIVE))
        self.assertEqual(len(active_versions), 1, "Exactly one version must remain Active")

        # The other two versions must be retired
        retired_versions = list(PlanVersion.objects.filter(plan=plan, status=PlanVersionStatus.RETIRED))
        self.assertEqual(len(retired_versions), 2)

        # Check audit events order and supersession metadata
        supersession_audits = list(
            AuditLog.objects.filter(
                action__in=[AuditAction.PLAN_VERSION_RETIRED, AuditAction.PLAN_VERSION_ACTIVATED],
                metadata__plan_id=str(plan.id),
            ).order_by("timestamp", "id")
        )
        # Each supersession activation emits RETIRED then ACTIVATED
        retire_indices = [i for i, a in enumerate(supersession_audits) if a.action == AuditAction.PLAN_VERSION_RETIRED]
        activate_indices = [i for i, a in enumerate(supersession_audits) if a.action == AuditAction.PLAN_VERSION_ACTIVATED]
        for r_idx in retire_indices:
            # Each retirement must be followed by an activation
            self.assertTrue(any(act_idx > r_idx for act_idx in activate_indices))

    def test_concurrent_activation_same_draft_version(self):
        """Simultaneous activation of the exact same Draft version allows only one activation; loser rejected cleanly."""
        plan, v1 = create_plan(code=f"p_{uuid.uuid4().hex[:6]}", name="Same Draft Plan", actor=self.owner)
        self._setup_ready_version(plan, v1)

        barrier = threading.Barrier(2)

        def _activate_task():
            barrier.wait(timeout=5.0)
            return activate_plan_version(plan_version_id=v1.id, actor=self.owner)

        results, exceptions = _run_in_threads([_activate_task, _activate_task])

        # One must succeed, one must fail with ValidationError (version is already active, not draft)
        successes = [r for r in results if r is not None]
        failures = [e for e in exceptions if e is not None]

        self.assertEqual(len(successes), 1)
        self.assertEqual(len(failures), 1)
        self.assertIsInstance(failures[0], ValidationError)
        self.assertIn("Only draft versions can be activated", str(failures[0]))

        # DB has exactly 1 active version
        v1_reloaded = PlanVersion.objects.get(pk=v1.id)
        self.assertEqual(v1_reloaded.status, PlanVersionStatus.ACTIVE)

        # Exactly 1 PLAN_VERSION_ACTIVATED audit log
        act_audits = AuditLog.objects.filter(
            action=AuditAction.PLAN_VERSION_ACTIVATED,
            target_id=v1.id,
        )
        self.assertEqual(act_audits.count(), 1)

    # -----------------------------------------------------------------------
    # 8. Concurrent Active-Version Mutation Protection
    # -----------------------------------------------------------------------
    def test_concurrent_activation_vs_commercial_mutation(self):
        """Race between activation and price creation: either price is included, or rejected post-activation."""
        plan, v1 = create_plan(code=f"p_{uuid.uuid4().hex[:6]}", name="Race Mutation Plan", actor=self.owner)
        self._setup_ready_version(plan, v1)

        barrier = threading.Barrier(2)

        def _activate_task():
            barrier.wait(timeout=5.0)
            return activate_plan_version(plan_version_id=v1.id, actor=self.owner)

        def _mutate_task():
            barrier.wait(timeout=5.0)
            return create_plan_price(
                plan_version_id=v1.id,
                currency="EUR",
                billing_interval="monthly",
                amount="19.99",
                actor=self.owner,
            )

        results, exceptions = _run_in_threads([_activate_task, _mutate_task])

        act_res, act_exc = results[0], exceptions[0]
        mut_res, mut_exc = results[1], exceptions[1]

        # Activation should always succeed
        self.assertIsNone(act_exc)
        self.assertIsNotNone(act_res)

        if mut_exc is not None:
            # Mutation serialized after activation: must fail with ValidationError
            self.assertIsInstance(mut_exc, ValidationError)
            self.assertIn("not 'draft'", str(mut_exc))
            # Must NOT have created EUR price in DB
            self.assertFalse(PlanPrice.objects.filter(plan_version=v1, currency="EUR").exists())
            # Must NOT have emitted audit event for EUR price
            self.assertFalse(
                AuditLog.objects.filter(
                    action=AuditAction.PLAN_PRICE_CREATED,
                    metadata__currency="EUR",
                ).exists()
            )
        else:
            # Mutation serialized before activation: price exists and is committed
            self.assertIsNotNone(mut_res)
            self.assertTrue(PlanPrice.objects.filter(plan_version=v1, currency="EUR").exists())

    # -----------------------------------------------------------------------
    # 9. Concurrent Duplicate Commercial Rows
    # -----------------------------------------------------------------------
    def test_concurrent_duplicate_price_creation(self):
        """Two workers simultaneously creating the exact same price result in exactly 1 row; loser rejected."""
        plan, v1 = create_plan(code=f"p_{uuid.uuid4().hex[:6]}", name="Dup Price Plan", actor=self.owner)

        barrier = threading.Barrier(2)

        def _task():
            barrier.wait(timeout=5.0)
            return create_plan_price(
                plan_version_id=v1.id,
                currency="USD",
                billing_interval="monthly",
                amount="15.00",
                actor=self.owner,
            )

        results, exceptions = _run_in_threads([_task, _task])
        successes = [r for r in results if r is not None]
        failures = [e for e in exceptions if e is not None]

        self.assertEqual(len(successes), 1)
        self.assertEqual(len(failures), 1)
        self.assertTrue(isinstance(failures[0], (ValidationError, IntegrityError)))

        # Exactly 1 price in DB
        prices = PlanPrice.objects.filter(plan_version=v1, currency="USD", billing_interval="monthly")
        self.assertEqual(prices.count(), 1)

        # Exactly 1 audit event
        self.assertEqual(
            AuditLog.objects.filter(action=AuditAction.PLAN_PRICE_CREATED, target_id=prices[0].id).count(),
            1,
        )

    def test_concurrent_duplicate_product_packaging(self):
        """Two workers simultaneously adding the same Product result in exactly 1 PlanProduct; loser rejected."""
        plan, v1 = create_plan(code=f"p_{uuid.uuid4().hex[:6]}", name="Dup Prod Plan", actor=self.owner)

        barrier = threading.Barrier(2)

        def _task():
            barrier.wait(timeout=5.0)
            return add_plan_product(
                plan_version_id=v1.id,
                product_id=self.catalog_product.id,
                actor=self.owner,
            )

        results, exceptions = _run_in_threads([_task, _task])
        successes = [r for r in results if r is not None]
        failures = [e for e in exceptions if e is not None]

        self.assertEqual(len(successes), 1)
        self.assertEqual(len(failures), 1)
        self.assertTrue(isinstance(failures[0], (ValidationError, IntegrityError)))
        self.assertEqual(PlanProduct.objects.filter(plan_version=v1).count(), 1)

    def test_concurrent_duplicate_quota_creation(self):
        """Two workers simultaneously creating the same plan-scoped quota result in 1 row; loser rejected."""
        plan, v1 = create_plan(code=f"p_{uuid.uuid4().hex[:6]}", name="Dup Quota Plan", actor=self.owner)

        barrier = threading.Barrier(2)

        def _task():
            barrier.wait(timeout=5.0)
            return create_plan_quota(
                plan_version_id=v1.id,
                scope="plan",
                quota_key="api_calls",
                name="API Calls",
                unit="requests",
                limit_type="numeric",
                limit_value="1000",
                actor=self.owner,
            )

        results, exceptions = _run_in_threads([_task, _task])
        successes = [r for r in results if r is not None]
        failures = [e for e in exceptions if e is not None]

        self.assertEqual(len(successes), 1)
        self.assertEqual(len(failures), 1)
        self.assertTrue(isinstance(failures[0], (ValidationError, IntegrityError)))
        self.assertEqual(PlanQuota.objects.filter(plan_version=v1, quota_key="api_calls").count(), 1)

    # -----------------------------------------------------------------------
    # 10. Packaging Ancestry Race Tests
    # -----------------------------------------------------------------------
    def test_packaging_ancestry_race_product_removal_vs_module_add(self):
        """Race: removing PlanProduct while adding PlanModule beneath it leaves no orphaned modules."""
        plan, v1 = create_plan(code=f"p_{uuid.uuid4().hex[:6]}", name="Ancestry Plan", actor=self.owner)
        pp = add_plan_product(plan_version_id=v1.id, product_id=self.catalog_product.id, actor=self.owner)

        barrier = threading.Barrier(2)

        def _remove_prod():
            barrier.wait(timeout=5.0)
            return remove_plan_product(plan_product_id=pp.id, actor=self.owner)

        def _add_mod():
            barrier.wait(timeout=5.0)
            return add_plan_module(
                plan_product_id=pp.id,
                module_id=self.catalog_module.id,
                actor=self.owner,
            )

        results, exceptions = _run_in_threads([_remove_prod, _add_mod])

        # Assert no orphaned PlanModule exists without its parent PlanProduct
        orphaned_mods = PlanModule.objects.filter(plan_version=v1, plan_product__isnull=True).count()
        self.assertEqual(orphaned_mods, 0)

        # PlanProduct must either be deleted (if remove ran) and zero modules remain
        if not PlanProduct.objects.filter(id=pp.id).exists():
            self.assertEqual(PlanModule.objects.filter(plan_version=v1).count(), 0)

    def test_packaging_ancestry_race_module_removal_vs_capability_add(self):
        """Race: removing PlanModule while adding PlanCapability beneath it leaves no orphaned capabilities."""
        plan, v1 = create_plan(code=f"p_{uuid.uuid4().hex[:6]}", name="Mod Ancestry Plan", actor=self.owner)
        pp = add_plan_product(plan_version_id=v1.id, product_id=self.catalog_product.id, actor=self.owner)
        pm = add_plan_module(plan_product_id=pp.id, module_id=self.catalog_module.id, actor=self.owner)

        barrier = threading.Barrier(2)

        def _remove_mod():
            barrier.wait(timeout=5.0)
            return remove_plan_module(plan_module_id=pm.id, actor=self.owner)

        def _add_cap():
            barrier.wait(timeout=5.0)
            return add_plan_capability(
                plan_module_id=pm.id,
                capability_id=self.catalog_capability.id,
                actor=self.owner,
            )

        results, exceptions = _run_in_threads([_remove_mod, _add_cap])

        orphaned_caps = PlanCapability.objects.filter(plan_version=v1, plan_module__isnull=True).count()
        self.assertEqual(orphaned_caps, 0)

        if not PlanModule.objects.filter(id=pm.id).exists():
            self.assertEqual(PlanCapability.objects.filter(plan_version=v1).count(), 0)

    # -----------------------------------------------------------------------
    # 11. Clone Consistency Under Concurrency
    # -----------------------------------------------------------------------
    def test_clone_consistency_under_concurrent_mutation(self):
        """Cloning a version during concurrent price addition produces a clean, consistent snapshot."""
        plan, v1 = create_plan(code=f"p_{uuid.uuid4().hex[:6]}", name="Clone Race Plan", actor=self.owner)
        add_plan_product(plan_version_id=v1.id, product_id=self.catalog_product.id, actor=self.owner)
        create_plan_price(
            plan_version_id=v1.id,
            currency="USD",
            billing_interval="monthly",
            amount="10.00",
            actor=self.owner,
        )

        barrier = threading.Barrier(2)

        def _clone_task():
            barrier.wait(timeout=5.0)
            return clone_plan_version(source_plan_version_id=v1.id, actor=self.owner)

        def _price_task():
            barrier.wait(timeout=5.0)
            return create_plan_price(
                plan_version_id=v1.id,
                currency="EUR",
                billing_interval="monthly",
                amount="20.00",
                actor=self.owner,
            )

        results, exceptions = _run_in_threads([_clone_task, _price_task])
        for exc in exceptions:
            self.assertIsNone(exc)

        cloned_version = results[0]
        self.assertIsNotNone(cloned_version)

        # Cloned version prices count in audit must equal persisted cloned prices
        clone_audit = AuditLog.objects.get(
            action=AuditAction.PLAN_VERSION_CLONED,
            target_id=cloned_version.id,
        )
        cloned_prices = list(PlanPrice.objects.filter(plan_version=cloned_version))
        self.assertEqual(clone_audit.metadata["copied_prices_count"], len(cloned_prices))

        # Remapped ancestry references must point to the new version, never source version
        for pp in PlanProduct.objects.filter(plan_version=cloned_version):
            self.assertEqual(pp.plan_version_id, cloned_version.id)

    # -----------------------------------------------------------------------
    # 12. Cascade Removal Determinism and Rollback
    # -----------------------------------------------------------------------
    def test_cascade_removal_determinism_and_rollback(self):
        """Cascade removal audits descendants before parent; audit failure rolls back all deletes."""
        plan, v1 = create_plan(code=f"p_{uuid.uuid4().hex[:6]}", name="Cascade Plan", actor=self.owner)
        pp = add_plan_product(plan_version_id=v1.id, product_id=self.catalog_product.id, actor=self.owner)
        pm = add_plan_module(plan_product_id=pp.id, module_id=self.catalog_module.id, actor=self.owner)
        pc = add_plan_capability(plan_module_id=pm.id, capability_id=self.catalog_capability.id, actor=self.owner)
        q = create_plan_quota(
            plan_version_id=v1.id,
            scope="capability",
            target_id=pc.id,
            quota_key="cap_q",
            name="Cap Quota",
            unit="count",
            limit_type="numeric",
            limit_value="50",
            actor=self.owner,
        )

        # Test failure rollback: patch record_audit_event to fail on PLAN_PRODUCT_REMOVED
        original_record = record_audit_event

        def _fail_on_product_removed(**kwargs):
            if kwargs.get("action") == AuditAction.PLAN_PRODUCT_REMOVED:
                raise AuditEventError("Injected audit failure during product cascade")
            return original_record(**kwargs)

        with patch("apps.plans.services.record_audit_event", side_effect=_fail_on_product_removed):
            with self.assertRaises(AuditEventError):
                remove_plan_product(plan_product_id=pp.id, actor=self.owner)

        # Assert full rollback: all rows restored
        self.assertTrue(PlanProduct.objects.filter(id=pp.id).exists())
        self.assertTrue(PlanModule.objects.filter(id=pm.id).exists())
        self.assertTrue(PlanCapability.objects.filter(id=pc.id).exists())
        self.assertTrue(PlanQuota.objects.filter(id=q.id).exists())

        # No removal audit events persisted
        self.assertFalse(
            AuditLog.objects.filter(
                target_id__in=[pp.id, pm.id, pc.id, q.id],
                action__in=[
                    AuditAction.PLAN_QUOTA_REMOVED,
                    AuditAction.PLAN_CAPABILITY_REMOVED,
                    AuditAction.PLAN_MODULE_REMOVED,
                    AuditAction.PLAN_PRODUCT_REMOVED,
                ],
            ).exists()
        )

        # Successful removal: verify exact descendant-first ordering
        remove_plan_product(plan_product_id=pp.id, actor=self.owner)
        removal_audits = list(
            AuditLog.objects.filter(
                action__in=[
                    AuditAction.PLAN_QUOTA_REMOVED,
                    AuditAction.PLAN_CAPABILITY_REMOVED,
                    AuditAction.PLAN_MODULE_REMOVED,
                    AuditAction.PLAN_PRODUCT_REMOVED,
                ]
            ).order_by("timestamp", "id")
        )
        actions = [a.action for a in removal_audits]
        self.assertEqual(
            actions,
            [
                AuditAction.PLAN_QUOTA_REMOVED,
                AuditAction.PLAN_CAPABILITY_REMOVED,
                AuditAction.PLAN_MODULE_REMOVED,
                AuditAction.PLAN_PRODUCT_REMOVED,
            ],
        )

    # -----------------------------------------------------------------------
    # 13. Failure-Injection and Atomic Rollback Matrix
    # -----------------------------------------------------------------------
    def test_failure_injection_atomic_rollback_matrix(self):
        """Simulated audit failure across all 14 transaction categories completely rolls back changes."""
        # 1. Plan creation
        with patch("apps.plans.services.record_audit_event", side_effect=AuditEventError("Audit failure")):
            with self.assertRaises(AuditEventError):
                create_plan(code=f"p_{uuid.uuid4().hex[:6]}", name="Fail Plan", actor=self.owner)
        self.assertFalse(Plan.objects.filter(name="Fail Plan").exists())

        # Setup baseline plan for remaining categories
        plan, v1 = create_plan(code=f"p_{uuid.uuid4().hex[:6]}", name="Base Plan", actor=self.owner)

        # 2. Plan update
        with patch("apps.plans.services.record_audit_event", side_effect=AuditEventError("Audit failure")):
            with self.assertRaises(AuditEventError):
                update_plan(plan_id=plan.id, name="Renamed Plan", actor=self.owner)
        plan.refresh_from_db()
        self.assertEqual(plan.name, "Base Plan")

        # 3. PlanVersion creation
        with patch("apps.plans.services.record_audit_event", side_effect=AuditEventError("Audit failure")):
            with self.assertRaises(AuditEventError):
                create_draft_version(plan_id=plan.id, change_summary="Fail v2", actor=self.owner)
        self.assertEqual(PlanVersion.objects.filter(plan=plan).count(), 1)

        # 4. Draft change_summary update
        with patch("apps.plans.services.record_audit_event", side_effect=AuditEventError("Audit failure")):
            with self.assertRaises(AuditEventError):
                update_draft_version(plan_version_id=v1.id, change_summary="New Summary", actor=self.owner)
        v1.refresh_from_db()
        self.assertEqual(v1.change_summary, "Initial version")

        # 5. Clone
        with patch("apps.plans.services.record_audit_event", side_effect=AuditEventError("Audit failure")):
            with self.assertRaises(AuditEventError):
                clone_plan_version(source_plan_version_id=v1.id, actor=self.owner)
        self.assertEqual(PlanVersion.objects.filter(plan=plan).count(), 1)

        # Setup ready version for activation tests
        self._setup_ready_version(plan, v1)

        # 6. Activation without supersession
        with patch("apps.plans.services.record_audit_event", side_effect=AuditEventError("Audit failure")):
            with self.assertRaises(AuditEventError):
                activate_plan_version(plan_version_id=v1.id, actor=self.owner)
        v1.refresh_from_db()
        self.assertEqual(v1.status, PlanVersionStatus.DRAFT)
        self.assertIsNone(v1.activated_at)

        # Activate v1 cleanly
        v1 = activate_plan_version(plan_version_id=v1.id, actor=self.owner)
        self.assertEqual(v1.status, PlanVersionStatus.ACTIVE)

        # 7. Activation with automatic supersession (failure during retirement event vs activation event)
        v2 = create_draft_version(plan_id=plan.id, actor=self.owner)
        self._setup_ready_version(plan, v2)

        # 7a. Failure during retirement event
        original_record = record_audit_event

        def _fail_on_retire(**kwargs):
            if kwargs.get("action") == AuditAction.PLAN_VERSION_RETIRED:
                raise AuditEventError("Fail retire audit")
            return original_record(**kwargs)

        with patch("apps.plans.services.record_audit_event", side_effect=_fail_on_retire):
            with self.assertRaises(AuditEventError):
                activate_plan_version(plan_version_id=v2.id, actor=self.owner)
        v1.refresh_from_db()
        v2.refresh_from_db()
        self.assertEqual(v1.status, PlanVersionStatus.ACTIVE)
        self.assertEqual(v2.status, PlanVersionStatus.DRAFT)

        # 7b. Failure during activation event
        def _fail_on_activate(**kwargs):
            if kwargs.get("action") == AuditAction.PLAN_VERSION_ACTIVATED:
                raise AuditEventError("Fail activate audit")
            return original_record(**kwargs)

        with patch("apps.plans.services.record_audit_event", side_effect=_fail_on_activate):
            with self.assertRaises(AuditEventError):
                activate_plan_version(plan_version_id=v2.id, actor=self.owner)
        v1.refresh_from_db()
        v2.refresh_from_db()
        self.assertEqual(v1.status, PlanVersionStatus.ACTIVE)
        self.assertEqual(v2.status, PlanVersionStatus.DRAFT)

        # 8. Manual retirement
        with patch("apps.plans.services.record_audit_event", side_effect=AuditEventError("Audit failure")):
            with self.assertRaises(AuditEventError):
                retire_plan_version(plan_version_id=v2.id, actor=self.owner)
        v2.refresh_from_db()
        self.assertEqual(v2.status, PlanVersionStatus.DRAFT)

        # 9. Price create or update
        with patch("apps.plans.services.record_audit_event", side_effect=AuditEventError("Audit failure")):
            with self.assertRaises(AuditEventError):
                create_plan_price(
                    plan_version_id=v2.id,
                    currency="GBP",
                    billing_interval="annual",
                    amount="199.99",
                    actor=self.owner,
                )
        self.assertFalse(PlanPrice.objects.filter(plan_version=v2, currency="GBP").exists())

        price = PlanPrice.objects.filter(plan_version=v2).first()
        with patch("apps.plans.services.record_audit_event", side_effect=AuditEventError("Audit failure")):
            with self.assertRaises(AuditEventError):
                update_plan_price(plan_price_id=price.id, amount="999.99", actor=self.owner)
        price.refresh_from_db()
        self.assertNotEqual(price.amount, Decimal("999.99"))

        # 10. PlanProduct removal
        pp = PlanProduct.objects.filter(plan_version=v2).first()
        with patch("apps.plans.services.record_audit_event", side_effect=AuditEventError("Audit failure")):
            with self.assertRaises(AuditEventError):
                remove_plan_product(plan_product_id=pp.id, actor=self.owner)
        self.assertTrue(PlanProduct.objects.filter(id=pp.id).exists())

        # 11. PlanModule removal
        pm = add_plan_module(plan_product_id=pp.id, module_id=self.catalog_module.id, actor=self.owner)
        with patch("apps.plans.services.record_audit_event", side_effect=AuditEventError("Audit failure")):
            with self.assertRaises(AuditEventError):
                remove_plan_module(plan_module_id=pm.id, actor=self.owner)
        self.assertTrue(PlanModule.objects.filter(id=pm.id).exists())

        # 12. Capability removal
        pc = add_plan_capability(plan_module_id=pm.id, capability_id=self.catalog_capability.id, actor=self.owner)
        with patch("apps.plans.services.record_audit_event", side_effect=AuditEventError("Audit failure")):
            with self.assertRaises(AuditEventError):
                remove_plan_capability(plan_capability_id=pc.id, actor=self.owner)
        self.assertTrue(PlanCapability.objects.filter(id=pc.id).exists())

        # 13. Quota create or update
        with patch("apps.plans.services.record_audit_event", side_effect=AuditEventError("Audit failure")):
            with self.assertRaises(AuditEventError):
                create_plan_quota(
                    plan_version_id=v2.id,
                    scope="plan",
                    quota_key="rollback_q",
                    name="Rollback Q",
                    unit="count",
                    limit_type="numeric",
                    limit_value="10",
                    actor=self.owner,
                )
        self.assertFalse(PlanQuota.objects.filter(plan_version=v2, quota_key="rollback_q").exists())

        q = create_plan_quota(
            plan_version_id=v2.id,
            scope="plan",
            quota_key="rollback_q",
            name="Rollback Q",
            unit="count",
            limit_type="numeric",
            limit_value="10",
            actor=self.owner,
        )
        with patch("apps.plans.services.record_audit_event", side_effect=AuditEventError("Audit failure")):
            with self.assertRaises(AuditEventError):
                update_plan_quota(plan_quota_id=q.id, name="Changed Q", actor=self.owner)
        q.refresh_from_db()
        self.assertEqual(q.name, "Rollback Q")

        # 14. Quota removal
        with patch("apps.plans.services.record_audit_event", side_effect=AuditEventError("Audit failure")):
            with self.assertRaises(AuditEventError):
                remove_plan_quota(plan_quota_id=q.id, actor=self.owner)
        self.assertTrue(PlanQuota.objects.filter(id=q.id).exists())

    # -----------------------------------------------------------------------
    # 14. Deadlock and Lock-Order Verification
    # -----------------------------------------------------------------------
    def test_deadlock_freedom_under_conflicting_concurrent_operations(self):
        """Repeated conflicting operations complete without PostgreSQL deadlocks or lock timeouts."""
        plan, v1 = create_plan(code=f"p_{uuid.uuid4().hex[:6]}", name="Deadlock Test Plan", actor=self.owner)
        self._setup_ready_version(plan, v1)
        v2 = create_draft_version(plan_id=plan.id, actor=self.owner)
        self._setup_ready_version(plan, v2)

        for iteration in range(3):
            barrier = threading.Barrier(2)

            def _op_a():
                barrier.wait(timeout=5.0)
                try:
                    activate_plan_version(plan_version_id=v1.id, actor=self.owner)
                except ValidationError:
                    pass

            def _op_b():
                barrier.wait(timeout=5.0)
                try:
                    create_plan_price(
                        plan_version_id=v2.id,
                        currency="INR",
                        billing_interval="monthly",
                        amount="500.00",
                        actor=self.owner,
                    )
                except ValidationError:
                    pass

            results, exceptions = _run_in_threads([_op_a, _op_b], timeout=10.0)
            for exc in exceptions:
                if exc is not None:
                    self.assertNotIn("deadlock detected", str(exc).lower())
                    self.assertNotIn("lock timeout", str(exc).lower())
