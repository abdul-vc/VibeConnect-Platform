"""Model-level test suite for Phase 2B Plans & Pricing domain schema.

Tests cover:
- Exact table names
- Exact field sets
- Actor ForeignKey metadata (on_delete=PROTECT, null=False, blank=False)
- Exact reverse related names for Plan and PlanVersion
- Child actor FKs use related_name="+"
- PlanVersion.plan uses on_delete=PROTECT
- PlanQuota.unit.max_length == 32
- Numeric validators metadata and constraints
- User deletion protected by referenced rows (ProtectedError)
- Plan deletion protected by PlanVersion (ProtectedError)
- Absence of Plan status/archive fields
- Lowercase Plan code validation
- Case-insensitive Plan code uniqueness and immutability
- Version uniqueness per plan
- Single Active version constraint
- Lifecycle timestamp consistency
- Exact amount field and non-negativity
- Absence of price alias
- Absence of is_included field
- Exact currency choices
- Exact interval choices
- Exact scope choices
- Exact unit choices
- Absence of daily reset period
- Quota scope-target constraint and conditional uniqueness
- Quota limit type and value constraint
- Exact 19 audit actions
- Exact 7 target types
- Absence of rejected audit actions
- Minimal explicit indexes
- Reverse-accessor system check
"""

from decimal import Decimal
import uuid

from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import IntegrityError, models, transaction
from django.test import TestCase
from django.utils import timezone
from django.contrib.auth import get_user_model

from apps.auditlog.models import AuditAction, AuditLog, AuditOperationSource, AuditTargetType
from apps.product_registry.models import (
    Product,
    ProductModule,
    ProductFeature,
    ProductCapability,
    ProductStatus,
    CatalogStatus,
)
from apps.plans.models import (
    Plan,
    PlanVersion,
    PlanVersionStatus,
    PlanPrice,
    PlanCurrency,
    BillingInterval,
    PlanProduct,
    PlanModule,
    PlanCapability,
    PlanQuota,
    QuotaScope,
    QuotaLimitType,
    QuotaResetPeriod,
)

User = get_user_model()


class PlansDomainModelTests(TestCase):
    """Comprehensive model-level validation of Phase 2B domain schema."""

    def setUp(self):
        self.user = User.objects.create_user(
            email="plan_admin@vibeconnect.test",
            password="SecurePassword123!",
            full_name="Plan Admin",
            is_platform_owner=True,
        )
        self.product = Product.objects.create(
            code="prod-lms",
            name="LMS Product",
            status=ProductStatus.ACTIVE,
            created_by=self.user,
            updated_by=self.user,
        )
        self.module = ProductModule.objects.create(
            product=self.product,
            code="mod-core",
            name="Core Module",
            status=CatalogStatus.ACTIVE,
            created_by=self.user,
            updated_by=self.user,
        )
        self.feature = ProductFeature.objects.create(
            module=self.module,
            code="feat-analytics",
            name="Analytics Feature",
            status=CatalogStatus.ACTIVE,
            created_by=self.user,
            updated_by=self.user,
        )
        self.capability = ProductCapability.objects.create(
            feature=self.feature,
            code="cap-reports",
            name="Reports Capability",
            status=CatalogStatus.ACTIVE,
            created_by=self.user,
            updated_by=self.user,
        )

    # 1. Exact Table Names
    def test_exact_table_names(self):
        self.assertEqual(Plan._meta.db_table, "plans")
        self.assertEqual(PlanVersion._meta.db_table, "plan_versions")
        self.assertEqual(PlanPrice._meta.db_table, "plan_prices")
        self.assertEqual(PlanProduct._meta.db_table, "plan_products")
        self.assertEqual(PlanModule._meta.db_table, "plan_modules")
        self.assertEqual(PlanCapability._meta.db_table, "plan_capabilities")
        self.assertEqual(PlanQuota._meta.db_table, "plan_quotas")

    # 2. Exact Field Sets
    def test_exact_field_sets(self):
        def get_model_fields(model):
            return {f.name for f in model._meta.fields}

        self.assertEqual(
            get_model_fields(Plan),
            {"id", "code", "name", "description", "is_public", "created_at", "updated_at", "created_by", "updated_by"},
        )
        self.assertEqual(
            get_model_fields(PlanVersion),
            {
                "id",
                "plan",
                "version",
                "status",
                "change_summary",
                "activated_at",
                "retired_at",
                "created_at",
                "updated_at",
                "created_by",
                "updated_by",
            },
        )
        self.assertEqual(
            get_model_fields(PlanPrice),
            {
                "id",
                "plan_version",
                "currency",
                "billing_interval",
                "amount",
                "created_at",
                "updated_at",
                "created_by",
                "updated_by",
            },
        )
        self.assertEqual(
            get_model_fields(PlanProduct),
            {"id", "plan_version", "product", "created_at", "created_by"},
        )
        self.assertEqual(
            get_model_fields(PlanModule),
            {"id", "plan_version", "plan_product", "module", "created_at", "created_by"},
        )
        self.assertEqual(
            get_model_fields(PlanCapability),
            {"id", "plan_version", "plan_module", "capability", "created_at", "created_by"},
        )
        self.assertEqual(
            get_model_fields(PlanQuota),
            {
                "id",
                "plan_version",
                "scope",
                "plan_product",
                "plan_module",
                "plan_capability",
                "quota_key",
                "name",
                "unit",
                "limit_type",
                "limit_value",
                "is_hard_limit",
                "reset_period",
                "created_at",
                "updated_at",
                "created_by",
                "updated_by",
            },
        )

    # 3. Actor ForeignKey Metadata
    def test_actor_foreign_key_metadata(self):
        actor_fks = [
            (Plan, "created_by", "created_plans"),
            (Plan, "updated_by", "updated_plans"),
            (PlanVersion, "created_by", "created_plan_versions"),
            (PlanVersion, "updated_by", "updated_plan_versions"),
            (PlanPrice, "created_by", "+"),
            (PlanPrice, "updated_by", "+"),
            (PlanProduct, "created_by", "+"),
            (PlanModule, "created_by", "+"),
            (PlanCapability, "created_by", "+"),
            (PlanQuota, "created_by", "+"),
            (PlanQuota, "updated_by", "+"),
        ]

        for model, field_name, expected_rel_name in actor_fks:
            field = model._meta.get_field(field_name)
            self.assertIs(field.remote_field.on_delete, models.PROTECT, f"{model.__name__}.{field_name} must use PROTECT")
            self.assertFalse(field.null, f"{model.__name__}.{field_name} must have null=False")
            self.assertFalse(field.blank, f"{model.__name__}.{field_name} must have blank=False")
            self.assertEqual(
                field.remote_field.related_name,
                expected_rel_name,
                f"{model.__name__}.{field_name} must have related_name='{expected_rel_name}'",
            )

        # PlanVersion.plan must use PROTECT
        pv_plan_field = PlanVersion._meta.get_field("plan")
        self.assertIs(pv_plan_field.remote_field.on_delete, models.PROTECT)
        self.assertEqual(pv_plan_field.remote_field.related_name, "versions")

    # 4. PlanQuota.unit metadata
    def test_plan_quota_unit_metadata(self):
        unit_field = PlanQuota._meta.get_field("unit")
        self.assertEqual(unit_field.max_length, 32)
        self.assertIsNone(unit_field.choices)

    # 5. Numeric Validators Metadata
    def test_numeric_validators_metadata(self):
        amount_field = PlanPrice._meta.get_field("amount")
        self.assertEqual(amount_field.max_digits, 12)
        self.assertEqual(amount_field.decimal_places, 2)
        validator_types = [type(v) for v in amount_field.validators]
        self.assertIn(MinValueValidator, validator_types)
        self.assertIn(MaxValueValidator, validator_types)

        limit_value_field = PlanQuota._meta.get_field("limit_value")
        self.assertTrue(limit_value_field.null)
        self.assertTrue(limit_value_field.blank)
        lv_validator_types = [type(v) for v in limit_value_field.validators]
        self.assertIn(MinValueValidator, lv_validator_types)
        self.assertIn(MaxValueValidator, lv_validator_types)

    # 6. User and Plan Deletion Protection (PROTECT on delete)
    def test_user_deletion_protected(self):
        plan = Plan.objects.create(
            code="protect-user",
            name="Protect User",
            created_by=self.user,
            updated_by=self.user,
        )
        with self.assertRaises(models.ProtectedError):
            self.user.delete()

    def test_plan_deletion_protected_by_version(self):
        plan = Plan.objects.create(
            code="protect-plan",
            name="Protect Plan",
            created_by=self.user,
            updated_by=self.user,
        )
        PlanVersion.objects.create(
            plan=plan,
            version=1,
            status=PlanVersionStatus.DRAFT,
            created_by=self.user,
            updated_by=self.user,
        )
        with self.assertRaises(models.ProtectedError):
            plan.delete()

    # 7. Absence of Plan Status / Active / Archive Fields
    def test_absence_of_plan_status_and_archive_fields(self):
        plan_fields = {f.name for f in Plan._meta.fields}
        prohibited = {"status", "active", "is_active", "archived", "is_archived", "deleted", "is_deleted"}
        self.assertTrue(prohibited.isdisjoint(plan_fields))
        plan = Plan(code="starter", name="Starter Plan", created_by=self.user, updated_by=self.user)
        for field_name in prohibited:
            self.assertFalse(hasattr(plan, field_name))

    # 8. Lowercase Plan Code and Format Regex
    def test_plan_code_lowercase_and_regex(self):
        plan = Plan(code="starter-pro_v1", name="Starter Plan", created_by=self.user, updated_by=self.user)
        plan.full_clean()
        plan.save()
        self.assertEqual(plan.code, "starter-pro_v1")

        # Uppercase auto-lowercases or validates
        plan_upper = Plan(code="STARTER_TIER", name="Upper Plan", created_by=self.user, updated_by=self.user)
        plan_upper.save()
        self.assertEqual(plan_upper.code, "starter_tier")

        # Invalid regex patterns
        invalid_codes = ["-invalid", "invalid-", "inv__code", "inv--code", "inv@code", "inv code"]
        for invalid_code in invalid_codes:
            with self.assertRaises(ValidationError):
                bad_plan = Plan(code=invalid_code, name="Invalid Plan", created_by=self.user, updated_by=self.user)
                bad_plan.full_clean()

    # 9. Case-Insensitive Plan Code Uniqueness and Immutability
    def test_plan_code_case_insensitive_uniqueness(self):
        Plan.objects.create(code="enterprise", name="Enterprise Plan", created_by=self.user, updated_by=self.user)
        with self.assertRaises((IntegrityError, ValidationError)):
            with transaction.atomic():
                Plan.objects.create(
                    code="ENTERPRISE",
                    name="Enterprise Duplicate",
                    created_by=self.user,
                    updated_by=self.user,
                )

    def test_plan_code_immutability(self):
        plan = Plan.objects.create(code="growth", name="Growth Plan", created_by=self.user, updated_by=self.user)
        plan.code = "growth-revised"
        with self.assertRaises(ValidationError) as ctx:
            plan.save()
        self.assertIn("Plan code is immutable", str(ctx.exception))

    # 10. Version Uniqueness
    def test_plan_version_uniqueness(self):
        plan = Plan.objects.create(code="team", name="Team Plan", created_by=self.user, updated_by=self.user)
        PlanVersion.objects.create(
            plan=plan,
            version=1,
            status=PlanVersionStatus.DRAFT,
            created_by=self.user,
            updated_by=self.user,
        )
        with self.assertRaises((ValidationError, IntegrityError)):
            with transaction.atomic():
                PlanVersion.objects.create(
                    plan=plan,
                    version=1,
                    status=PlanVersionStatus.DRAFT,
                    created_by=self.user,
                    updated_by=self.user,
                )

    def test_plan_version_gt_zero(self):
        plan = Plan.objects.create(code="team-v0", name="Team Plan", created_by=self.user, updated_by=self.user)
        with self.assertRaises((IntegrityError, ValidationError)):
            with transaction.atomic():
                pv = PlanVersion(
                    plan=plan,
                    version=0,
                    status=PlanVersionStatus.DRAFT,
                    created_by=self.user,
                    updated_by=self.user,
                )
                pv.full_clean()
                pv.save()

    # 11. One Active Version per Plan
    def test_one_active_version_per_plan(self):
        plan = Plan.objects.create(code="business", name="Business Plan", created_by=self.user, updated_by=self.user)
        now = timezone.now()
        PlanVersion.objects.create(
            plan=plan,
            version=1,
            status=PlanVersionStatus.ACTIVE,
            activated_at=now,
            created_by=self.user,
            updated_by=self.user,
        )

        with self.assertRaises((ValidationError, IntegrityError)):
            with transaction.atomic():
                PlanVersion.objects.create(
                    plan=plan,
                    version=2,
                    status=PlanVersionStatus.ACTIVE,
                    activated_at=now,
                    created_by=self.user,
                    updated_by=self.user,
                )

        # But multiple retired/draft versions are allowed
        PlanVersion.objects.create(
            plan=plan,
            version=2,
            status=PlanVersionStatus.DRAFT,
            created_by=self.user,
            updated_by=self.user,
        )
        PlanVersion.objects.create(
            plan=plan,
            version=3,
            status=PlanVersionStatus.RETIRED,
            activated_at=now,
            retired_at=now,
            created_by=self.user,
            updated_by=self.user,
        )

    # 12. Lifecycle Timestamp Consistency
    def test_lifecycle_timestamp_consistency(self):
        plan = Plan.objects.create(code="lifecycle", name="Lifecycle Plan", created_by=self.user, updated_by=self.user)
        now = timezone.now()

        # 5. Draft with either lifecycle timestamp set is rejected
        with self.assertRaises((ValidationError, IntegrityError)):
            with transaction.atomic():
                pv = PlanVersion(
                    plan=plan,
                    version=1,
                    status=PlanVersionStatus.DRAFT,
                    activated_at=now,
                    created_by=self.user,
                    updated_by=self.user,
                )
                pv.full_clean()
                pv.save()

        with self.assertRaises((ValidationError, IntegrityError)):
            with transaction.atomic():
                pv = PlanVersion(
                    plan=plan,
                    version=1,
                    status=PlanVersionStatus.DRAFT,
                    retired_at=now,
                    created_by=self.user,
                    updated_by=self.user,
                )
                pv.full_clean()
                pv.save()

        # 6. Active without activated_at is rejected
        with self.assertRaises((ValidationError, IntegrityError)):
            with transaction.atomic():
                pv = PlanVersion(
                    plan=plan,
                    version=1,
                    status=PlanVersionStatus.ACTIVE,
                    activated_at=None,
                    created_by=self.user,
                    updated_by=self.user,
                )
                pv.full_clean()
                pv.save()

        # Active with retired_at must fail
        with self.assertRaises((ValidationError, IntegrityError)):
            with transaction.atomic():
                pv = PlanVersion(
                    plan=plan,
                    version=1,
                    status=PlanVersionStatus.ACTIVE,
                    activated_at=now,
                    retired_at=now,
                    created_by=self.user,
                    updated_by=self.user,
                )
                pv.full_clean()
                pv.save()

        # 3. Retired with retired_at=None is rejected (both with activated_at=None and with activated_at set)
        with self.assertRaises((ValidationError, IntegrityError)):
            with transaction.atomic():
                pv = PlanVersion(
                    plan=plan,
                    version=1,
                    status=PlanVersionStatus.RETIRED,
                    activated_at=None,
                    retired_at=None,
                    created_by=self.user,
                    updated_by=self.user,
                )
                pv.full_clean()
                pv.save()

        with self.assertRaises((ValidationError, IntegrityError)):
            with transaction.atomic():
                pv = PlanVersion(
                    plan=plan,
                    version=1,
                    status=PlanVersionStatus.RETIRED,
                    activated_at=now,
                    retired_at=None,
                    created_by=self.user,
                    updated_by=self.user,
                )
                pv.full_clean()
                pv.save()

        # 4. Retired with retired_at < activated_at is rejected
        with self.assertRaises((ValidationError, IntegrityError)):
            with transaction.atomic():
                pv = PlanVersion(
                    plan=plan,
                    version=1,
                    status=PlanVersionStatus.RETIRED,
                    activated_at=now,
                    retired_at=now - timezone.timedelta(days=1),
                    created_by=self.user,
                    updated_by=self.user,
                )
                pv.full_clean()
                pv.save()

        # 1. Draft -> Retired with activated_at=None and non-null retired_at succeeds
        pv_draft_retired = PlanVersion(
            plan=plan,
            version=1,
            status=PlanVersionStatus.RETIRED,
            activated_at=None,
            retired_at=now,
            created_by=self.user,
            updated_by=self.user,
        )
        pv_draft_retired.full_clean()
        pv_draft_retired.save()
        self.assertIsNone(pv_draft_retired.activated_at)
        self.assertIsNotNone(pv_draft_retired.retired_at)

        # 2. Active -> Retired preserves non-null activated_at
        pv_active_retired = PlanVersion(
            plan=plan,
            version=2,
            status=PlanVersionStatus.RETIRED,
            activated_at=now,
            retired_at=now + timezone.timedelta(days=1),
            created_by=self.user,
            updated_by=self.user,
        )
        pv_active_retired.full_clean()
        pv_active_retired.save()
        self.assertEqual(pv_active_retired.activated_at, now)
        self.assertEqual(pv_active_retired.retired_at, now + timezone.timedelta(days=1))

    # 13. Exact Amount Field and Non-Negativity
    def test_exact_amount_field_and_non_negativity(self):
        plan = Plan.objects.create(code="pricing", name="Pricing Plan", created_by=self.user, updated_by=self.user)
        pv = PlanVersion.objects.create(
            plan=plan,
            version=1,
            status=PlanVersionStatus.DRAFT,
            created_by=self.user,
            updated_by=self.user,
        )
        price = PlanPrice.objects.create(
            plan_version=pv,
            currency=PlanCurrency.USD,
            billing_interval=BillingInterval.MONTHLY,
            amount=Decimal("49.99"),
            created_by=self.user,
            updated_by=self.user,
        )
        self.assertEqual(price.amount, Decimal("49.99"))

        # Negative amount must fail
        with self.assertRaises((ValidationError, IntegrityError)):
            with transaction.atomic():
                bad_price = PlanPrice(
                    plan_version=pv,
                    currency=PlanCurrency.INR,
                    billing_interval=BillingInterval.MONTHLY,
                    amount=Decimal("-10.00"),
                    created_by=self.user,
                    updated_by=self.user,
                )
                bad_price.full_clean()
                bad_price.save()

        # Unique plan_version + currency + billing_interval
        with self.assertRaises((ValidationError, IntegrityError)):
            with transaction.atomic():
                PlanPrice.objects.create(
                    plan_version=pv,
                    currency=PlanCurrency.USD,
                    billing_interval=BillingInterval.MONTHLY,
                    amount=Decimal("59.99"),
                    created_by=self.user,
                    updated_by=self.user,
                )

    # 14. Absence of Price Alias
    def test_absence_of_price_alias(self):
        plan = Plan.objects.create(code="alias-check", name="Alias Check Plan", created_by=self.user, updated_by=self.user)
        pv = PlanVersion.objects.create(
            plan=plan,
            version=1,
            status=PlanVersionStatus.DRAFT,
            created_by=self.user,
            updated_by=self.user,
        )
        price_fields = {f.name for f in PlanPrice._meta.fields}
        self.assertIn("amount", price_fields)
        self.assertNotIn("price", price_fields)
        price_obj = PlanPrice(
            plan_version=pv,
            currency=PlanCurrency.USD,
            billing_interval=BillingInterval.MONTHLY,
            amount=Decimal("10.00"),
            created_by=self.user,
            updated_by=self.user,
        )
        self.assertFalse(hasattr(price_obj, "price"))

    # 15. Absence of is_included
    def test_absence_of_is_included_field(self):
        for model in (PlanProduct, PlanModule, PlanCapability):
            fields = {f.name for f in model._meta.fields}
            self.assertNotIn("is_included", fields)

    # 16. Exact Currency Choices
    def test_exact_currency_choices(self):
        self.assertEqual(set(PlanCurrency.values), {"INR", "USD", "EUR", "GBP"})

    # 17. Exact Billing Interval Choices
    def test_exact_billing_interval_choices(self):
        self.assertEqual(set(BillingInterval.values), {"monthly", "quarterly", "annual"})

    # 18. Exact Scope Choices
    def test_exact_scope_choices(self):
        self.assertEqual(set(QuotaScope.values), {"plan", "product", "module", "capability"})

    # 19. Extensible Unit Model Validation and Database Constraint
    def test_plan_quota_unit_model_validation(self):
        plan = Plan.objects.create(code="quota-unit-val", name="Unit Val Plan", created_by=self.user, updated_by=self.user)
        pv = PlanVersion.objects.create(
            plan=plan,
            version=1,
            status=PlanVersionStatus.DRAFT,
            created_by=self.user,
            updated_by=self.user,
        )

        valid_units = [
            "gb",
            "api_calls",
            "documents",
            "storage_gb",
            "video_minutes",
            "a" * 32,
        ]
        for i, u in enumerate(valid_units):
            q = PlanQuota(
                plan_version=pv,
                scope=QuotaScope.PLAN,
                quota_key=f"valid_key_{i}",
                name=f"Valid Quota {i}",
                unit=u,
                limit_type=QuotaLimitType.NUMERIC,
                limit_value=100,
                reset_period=QuotaResetPeriod.NEVER,
                created_by=self.user,
                updated_by=self.user,
            )
            q.full_clean()
            q.save()
            self.assertEqual(q.unit, u)

        invalid_units = [
            "",               # empty string
            "GB",             # uppercase
            " gb",            # leading whitespace
            "gb ",            # trailing whitespace
            "g b",            # internal whitespace
            "video-minutes",  # hyphen
            "doc.uments",     # punctuation
            "a" * 33,         # 33-character value
        ]
        for i, bad_u in enumerate(invalid_units):
            q_bad = PlanQuota(
                plan_version=pv,
                scope=QuotaScope.PLAN,
                quota_key=f"invalid_key_{i}",
                name=f"Invalid Quota {i}",
                unit=bad_u,
                limit_type=QuotaLimitType.NUMERIC,
                limit_value=100,
                reset_period=QuotaResetPeriod.NEVER,
                created_by=self.user,
                updated_by=self.user,
            )
            with self.assertRaises(ValidationError):
                q_bad.full_clean()

    def test_plan_quota_unit_database_constraint(self):
        plan = Plan.objects.create(code="quota-db-check", name="DB Check Plan", created_by=self.user, updated_by=self.user)
        pv = PlanVersion.objects.create(
            plan=plan,
            version=1,
            status=PlanVersionStatus.DRAFT,
            created_by=self.user,
            updated_by=self.user,
        )

        # Bypass normal model clean validation using bulk_create to test PostgreSQL constraint
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                PlanQuota.objects.bulk_create([
                    PlanQuota(
                        plan_version=pv,
                        scope=QuotaScope.PLAN,
                        quota_key="direct-db-invalid",
                        name="Direct DB Invalid",
                        unit="INVALID_UPPERCASE",
                        limit_type=QuotaLimitType.NUMERIC,
                        limit_value=10,
                        reset_period=QuotaResetPeriod.NEVER,
                        created_by=self.user,
                        updated_by=self.user,
                    )
                ])

        # Valid custom unit succeeds at database level
        PlanQuota.objects.bulk_create([
            PlanQuota(
                plan_version=pv,
                scope=QuotaScope.PLAN,
                quota_key="direct-db-valid",
                name="Direct DB Valid",
                unit="custom_events",
                limit_type=QuotaLimitType.NUMERIC,
                limit_value=10,
                reset_period=QuotaResetPeriod.NEVER,
                created_by=self.user,
                updated_by=self.user,
            )
        ])
        self.assertTrue(PlanQuota.objects.filter(quota_key="direct-db-valid", unit="custom_events").exists())

    # 20. Absence of Daily Reset Period
    def test_absence_of_daily_reset_period(self):
        self.assertEqual(set(QuotaResetPeriod.values), {"never", "monthly", "annual"})
        self.assertNotIn("daily", QuotaResetPeriod.values)

    # 21. Quota Scope-Target Constraints and Conditional Uniqueness
    def test_quota_scope_target_constraints(self):
        plan = Plan.objects.create(code="quota-scope", name="Quota Scope Plan", created_by=self.user, updated_by=self.user)
        pv = PlanVersion.objects.create(
            plan=plan,
            version=1,
            status=PlanVersionStatus.DRAFT,
            created_by=self.user,
            updated_by=self.user,
        )
        plan_prod = PlanProduct.objects.create(plan_version=pv, product=self.product, created_by=self.user)
        plan_mod = PlanModule.objects.create(
            plan_version=pv,
            plan_product=plan_prod,
            module=self.module,
            created_by=self.user,
        )
        plan_cap = PlanCapability.objects.create(
            plan_version=pv,
            plan_module=plan_mod,
            capability=self.capability,
            created_by=self.user,
        )

        # Valid plan-scoped quota
        q_plan = PlanQuota.objects.create(
            plan_version=pv,
            scope=QuotaScope.PLAN,
            quota_key="max-users",
            name="Max Users",
            unit="users",
            limit_type=QuotaLimitType.NUMERIC,
            limit_value=50,
            reset_period=QuotaResetPeriod.MONTHLY,
            created_by=self.user,
            updated_by=self.user,
        )
        self.assertIsNotNone(q_plan.id)

        # Plan-scoped quota with plan_product set must fail
        with self.assertRaises((ValidationError, IntegrityError)):
            with transaction.atomic():
                bad_q = PlanQuota(
                    plan_version=pv,
                    scope=QuotaScope.PLAN,
                    plan_product=plan_prod,
                    quota_key="invalid-plan-q",
                    name="Invalid",
                    unit="count",
                    limit_type=QuotaLimitType.NUMERIC,
                    limit_value=10,
                    reset_period=QuotaResetPeriod.NEVER,
                    created_by=self.user,
                    updated_by=self.user,
                )
                bad_q.full_clean()
                bad_q.save()

        # Product-scoped quota requires plan_product and rejects others
        q_prod = PlanQuota.objects.create(
            plan_version=pv,
            scope=QuotaScope.PRODUCT,
            plan_product=plan_prod,
            quota_key="api-calls",
            name="API Calls",
            unit="api_calls",
            limit_type=QuotaLimitType.UNLIMITED,
            limit_value=None,
            reset_period=QuotaResetPeriod.MONTHLY,
            created_by=self.user,
            updated_by=self.user,
        )
        self.assertIsNotNone(q_prod.id)

        # Conditional Uniqueness per Scope
        with self.assertRaises((ValidationError, IntegrityError)):
            with transaction.atomic():
                PlanQuota.objects.create(
                    plan_version=pv,
                    scope=QuotaScope.PLAN,
                    quota_key="max-users",
                    name="Duplicate Max Users",
                    unit="users",
                    limit_type=QuotaLimitType.NUMERIC,
                    limit_value=100,
                    reset_period=QuotaResetPeriod.MONTHLY,
                    created_by=self.user,
                    updated_by=self.user,
                )

    # 22. Quota Limit Type and Value Constraint
    def test_quota_limit_type_and_value_constraint(self):
        plan = Plan.objects.create(code="quota-limit", name="Quota Limit Plan", created_by=self.user, updated_by=self.user)
        pv = PlanVersion.objects.create(
            plan=plan,
            version=1,
            status=PlanVersionStatus.DRAFT,
            created_by=self.user,
            updated_by=self.user,
        )

        # Numeric with null limit_value must fail
        with self.assertRaises((ValidationError, IntegrityError)):
            with transaction.atomic():
                bad_q = PlanQuota(
                    plan_version=pv,
                    scope=QuotaScope.PLAN,
                    quota_key="bad-numeric",
                    name="Bad Numeric",
                    unit="count",
                    limit_type=QuotaLimitType.NUMERIC,
                    limit_value=None,
                    reset_period=QuotaResetPeriod.NEVER,
                    created_by=self.user,
                    updated_by=self.user,
                )
                bad_q.full_clean()
                bad_q.save()

        # Unlimited with non-null limit_value must fail
        with self.assertRaises((ValidationError, IntegrityError)):
            with transaction.atomic():
                bad_q2 = PlanQuota(
                    plan_version=pv,
                    scope=QuotaScope.PLAN,
                    quota_key="bad-unlimited",
                    name="Bad Unlimited",
                    unit="count",
                    limit_type=QuotaLimitType.UNLIMITED,
                    limit_value=500,
                    reset_period=QuotaResetPeriod.NEVER,
                    created_by=self.user,
                    updated_by=self.user,
                )
                bad_q2.full_clean()
                bad_q2.save()

        # BigInteger range test: up to 9223372036854775807
        max_q = PlanQuota.objects.create(
            plan_version=pv,
            scope=QuotaScope.PLAN,
            quota_key="max-bigint",
            name="Max BigInt",
            unit="gb",
            limit_type=QuotaLimitType.NUMERIC,
            limit_value=9223372036854775807,
            reset_period=QuotaResetPeriod.ANNUAL,
            created_by=self.user,
            updated_by=self.user,
        )
        self.assertEqual(max_q.limit_value, 9223372036854775807)

    # 23. Exact 19 Audit Actions
    def test_exact_19_audit_actions(self):
        expected_plan_actions = {
            "plan_created",
            "plan_updated",
            "plan_version_created",
            "plan_version_updated",
            "plan_version_cloned",
            "plan_version_activated",
            "plan_version_retired",
            "plan_price_created",
            "plan_price_updated",
            "plan_price_removed",
            "plan_product_added",
            "plan_product_removed",
            "plan_module_added",
            "plan_module_removed",
            "plan_capability_added",
            "plan_capability_removed",
            "plan_quota_created",
            "plan_quota_updated",
            "plan_quota_removed",
        }
        actual_actions = set(AuditAction.values)
        self.assertTrue(expected_plan_actions.issubset(actual_actions))
        self.assertEqual(len(expected_plan_actions), 19)

    # 24. Exact 7 Target Types
    def test_exact_7_audit_target_types(self):
        expected_target_types = {
            "plan",
            "plan_version",
            "plan_price",
            "plan_product",
            "plan_module",
            "plan_capability",
            "plan_quota",
        }
        actual_targets = set(AuditTargetType.values)
        self.assertTrue(expected_target_types.issubset(actual_targets))
        self.assertEqual(len(expected_target_types), 7)

    # 25. Absence of Rejected Audit Actions
    def test_absence_of_rejected_audit_actions(self):
        rejected_actions = {
            "plan_archived",
            "plan_price_deleted",
            "plan_quota_deleted",
        }
        self.assertTrue(rejected_actions.isdisjoint(set(AuditAction.values)))

    # 26. Minimal Explicit Indexes
    def test_minimal_explicit_indexes(self):
        plan_index_names = {idx.name for idx in Plan._meta.indexes}
        self.assertEqual(plan_index_names, {"plan_created_idx"})

        pv_index_names = {idx.name for idx in PlanVersion._meta.indexes}
        self.assertEqual(pv_index_names, {"plan_ver_plan_stat_idx"})

        pq_index_names = {idx.name for idx in PlanQuota._meta.indexes}
        self.assertEqual(pq_index_names, {"quota_ver_scope_idx"})

        for model in (PlanPrice, PlanProduct, PlanModule, PlanCapability):
            self.assertEqual(len(model._meta.indexes), 0)

    # 27. Reverse-Accessor System Check
    def test_reverse_accessor_system_check(self):
        call_command("check")
        self.assertEqual(Plan._meta.get_field("created_by").remote_field.related_name, "created_plans")
        self.assertEqual(Plan._meta.get_field("updated_by").remote_field.related_name, "updated_plans")
        self.assertEqual(PlanVersion._meta.get_field("created_by").remote_field.related_name, "created_plan_versions")
        self.assertEqual(PlanVersion._meta.get_field("updated_by").remote_field.related_name, "updated_plan_versions")
        self.assertEqual(PlanPrice._meta.get_field("created_by").remote_field.related_name, "+")
        self.assertEqual(PlanProduct._meta.get_field("created_by").remote_field.related_name, "+")
        self.assertEqual(PlanModule._meta.get_field("created_by").remote_field.related_name, "+")
        self.assertEqual(PlanCapability._meta.get_field("created_by").remote_field.related_name, "+")
        self.assertEqual(PlanQuota._meta.get_field("created_by").remote_field.related_name, "+")
        self.assertEqual(PlanQuota._meta.get_field("updated_by").remote_field.related_name, "+")

    # 28. AuditLog Phase 2B Model and Constraint Tests
    def test_auditlog_phase2b_constraints(self):
        # 1. Successful audit creation with organization_id=None for all 7 target types
        target_action_pairs = [
            (AuditTargetType.PLAN, AuditAction.PLAN_CREATED),
            (AuditTargetType.PLAN_VERSION, AuditAction.PLAN_VERSION_CREATED),
            (AuditTargetType.PLAN_PRICE, AuditAction.PLAN_PRICE_CREATED),
            (AuditTargetType.PLAN_PRODUCT, AuditAction.PLAN_PRODUCT_ADDED),
            (AuditTargetType.PLAN_MODULE, AuditAction.PLAN_MODULE_ADDED),
            (AuditTargetType.PLAN_CAPABILITY, AuditAction.PLAN_CAPABILITY_ADDED),
            (AuditTargetType.PLAN_QUOTA, AuditAction.PLAN_QUOTA_CREATED),
        ]
        for target_type, action in target_action_pairs:
            log = AuditLog.objects.create(
                action=action,
                target_type=target_type,
                target_id=uuid.uuid4(),
                actor=self.user,
                operation_source=AuditOperationSource.INTERACTIVE,
                organization_id=None,
            )
            self.assertIsNotNone(log.id)

        # 2. Setting organization_id on plan target types must fail audit_catalog_auth_org_id_null
        for target_type, action in target_action_pairs:
            with self.assertRaises(IntegrityError):
                with transaction.atomic():
                    AuditLog.objects.create(
                        action=action,
                        target_type=target_type,
                        target_id=uuid.uuid4(),
                        actor=self.user,
                        operation_source=AuditOperationSource.INTERACTIVE,
                        organization_id=uuid.uuid4(),
                    )

        # 3. Action / TargetType mismatch constraints
        mismatch_cases = [
            (AuditAction.PLAN_CREATED, AuditTargetType.PRODUCT),
            (AuditAction.PLAN_VERSION_CREATED, AuditTargetType.PLAN),
            (AuditAction.PLAN_PRICE_CREATED, AuditTargetType.PLAN_VERSION),
            (AuditAction.PLAN_PRODUCT_ADDED, AuditTargetType.MODULE),
            (AuditAction.PLAN_MODULE_ADDED, AuditTargetType.FEATURE),
            (AuditAction.PLAN_CAPABILITY_ADDED, AuditTargetType.CAPABILITY),
            (AuditAction.PLAN_QUOTA_CREATED, AuditTargetType.PLAN),
        ]
        for action, wrong_target_type in mismatch_cases:
            with self.assertRaises(IntegrityError):
                with transaction.atomic():
                    AuditLog.objects.create(
                        action=action,
                        target_type=wrong_target_type,
                        target_id=uuid.uuid4(),
                        actor=self.user,
                        operation_source=AuditOperationSource.INTERACTIVE,
                        organization_id=None,
                    )

    # 26. PlanCurrency values, Model Validation, and Database Constraint
    def test_currency_allowlist_and_db_constraint(self):
        # 1. Exact PlanCurrency values
        self.assertEqual(set(PlanCurrency.values), {"INR", "USD", "EUR", "GBP"})
        self.assertEqual(len(PlanCurrency.values), 4)

        plan = Plan.objects.create(code="curr-test", name="Currency Test Plan", created_by=self.user, updated_by=self.user)
        pv = PlanVersion.objects.create(
            plan=plan,
            version=1,
            status=PlanVersionStatus.DRAFT,
            created_by=self.user,
            updated_by=self.user,
        )

        # 2. full_clean() accepts all 4 approved currencies
        for curr in ["INR", "USD", "EUR", "GBP"]:
            p = PlanPrice(
                plan_version=pv,
                currency=curr,
                billing_interval=BillingInterval.MONTHLY,
                amount=Decimal("10.00"),
                created_by=self.user,
                updated_by=self.user,
            )
            p.full_clean()

        # 3. full_clean() rejects unsupported currencies
        for bad_curr in ["AUD", "CAD", "JPY", "XYZ", ""]:
            p = PlanPrice(
                plan_version=pv,
                currency=bad_curr,
                billing_interval=BillingInterval.MONTHLY,
                amount=Decimal("10.00"),
                created_by=self.user,
                updated_by=self.user,
            )
            with self.assertRaises(ValidationError):
                p.full_clean()

        # 4. PostgreSQL CheckConstraint plan_price_currency_allowed rejects direct insertion
        for bad_curr in ["AUD", "CAD", "JPY", "XYZ"]:
            with self.assertRaises(IntegrityError):
                with transaction.atomic():
                    PlanPrice.objects.bulk_create([
                        PlanPrice(
                            plan_version=pv,
                            currency=bad_curr,
                            billing_interval=BillingInterval.MONTHLY,
                            amount=Decimal("10.00"),
                            created_by=self.user,
                            updated_by=self.user,
                        )
                    ])

        # 5. CheckConstraint exists in metadata
        constraint_names = [c.name for c in PlanPrice._meta.constraints]
        self.assertIn("plan_price_currency_allowed", constraint_names)


