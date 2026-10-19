"""Product Showcase Catalog Registration & Marketing Showcase Tests.

Validates:
1. All 20 products registered with valid codes, names, categories, and modules.
2. Idempotent command execution produces zero duplicate products or profiles.
3. LMS existing product record and configuration preservation.
4. FIELDOPS parent-suite structure (sub-products linked and functional modules created).
5. QBR external demo environment configured and launchable via DEMO_ONLY mode.
6. Non-demo products clearly marked as not launchable (no fabricated demo targets).
7. Presentation mode filtering by category and product attributes.
8. Authorization checks: platform owner access granted, tenant access rejected with 403.
"""

from __future__ import annotations

from django.core.management import call_command
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from apps.product_registry.models import Product, ProductModule, ProductStatus
from apps.showcase.models import (
    ProductDemoEnvironment,
    ProductLaunchConfig,
    ProductShowcaseProfile,
    ShowcaseVisibility,
)
from apps.showcase.services import (
    ProductShowcaseService,
    ShowcasePresentationService,
)

User = get_user_model()


def _create_owner(email="owner_catalog@vc.test"):
    user, _ = User.objects.get_or_create(
        email=email,
        defaults={
            "full_name": "Showcase Owner",
            "is_platform_owner": True,
            "is_staff": True,
            "status": "active",
        },
    )
    return user


class ShowcaseCatalogRegistrationTest(TestCase):
    """Test full catalog registration, idempotency, LMS preservation, and FIELDOPS suite."""

    def setUp(self):
        self.owner = _create_owner()
        self.client = APIClient()
        self.client.force_authenticate(user=self.owner)

    def test_catalog_registration_registers_all_twenty_products(self):
        call_command("register_showcase_catalog")

        expected_codes = {
            "lms",
            "hrms",
            "vms-warehouse",
            "leasing",
            "fieldsense",
            "inventory",
            "crm-logicon",
            "mom",
            "qbr",
            "audit-smart",
            "vendor-invoice-management",
            "quiz",
            "workshop-trinity",
            "fieldops",
            "workhub",
            "ai-dashboard",
            "event-module",
            "video-content-generation",
            "ats",
            "sales-tracker",
        }

        registered_codes = set(Product.objects.filter(status=ProductStatus.ACTIVE).values_list("code", flat=True))
        self.assertTrue(expected_codes.issubset(registered_codes), f"Missing: {expected_codes - registered_codes}")

        # Check showcase profiles exist for all 20
        all_profile_codes = set(
            ProductShowcaseProfile.objects.values_list("product__code", flat=True)
        )
        self.assertTrue(expected_codes.issubset(all_profile_codes))

        # 19 published, QBR explicitly hidden
        published_codes = set(
            ProductShowcaseProfile.objects.filter(visibility=ShowcaseVisibility.PUBLISHED).values_list(
                "product__code", flat=True
            )
        )
        self.assertNotIn("qbr", published_codes)
        self.assertEqual(len(published_codes), 19)
        self.assertEqual(
            ProductShowcaseProfile.objects.get(product__code="qbr").visibility,
            ShowcaseVisibility.HIDDEN,
        )

    def test_registration_idempotency_prevents_duplicates(self):
        # Run twice
        call_command("register_showcase_catalog")
        initial_product_count = Product.objects.count()
        initial_profile_count = ProductShowcaseProfile.objects.count()
        initial_modules_count = ProductModule.objects.count()

        call_command("register_showcase_catalog")

        self.assertEqual(Product.objects.count(), initial_product_count)
        self.assertEqual(ProductShowcaseProfile.objects.count(), initial_profile_count)
        self.assertEqual(ProductModule.objects.count(), initial_modules_count)

    def test_existing_lms_preservation(self):
        # Pre-create an LMS product with custom attributes before registration
        lms_product = Product.objects.create(
            code="lms",
            name="Existing LMS Custom",
            description="Pre-existing corporate LMS installation.",
            status=ProductStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )
        lms_profile = ProductShowcaseProfile.objects.create(
            product=lms_product,
            tagline="Custom Enterprise LMS Tagline",
            overview="Custom pre-existing LMS overview.",
            visibility=ShowcaseVisibility.PUBLISHED,
            display_order=99,
            created_by=self.owner,
            updated_by=self.owner,
        )

        call_command("register_showcase_catalog")

        # Must not duplicate or overwrite existing LMS product or profile
        self.assertEqual(Product.objects.filter(code="lms").count(), 1)
        refreshed_lms = Product.objects.get(code="lms")
        self.assertEqual(refreshed_lms.id, lms_product.id)
        self.assertEqual(refreshed_lms.name, "Existing LMS Custom")
        self.assertEqual(refreshed_lms.description, "Pre-existing corporate LMS installation.")

        refreshed_profile = ProductShowcaseProfile.objects.get(product=refreshed_lms)
        self.assertEqual(refreshed_profile.id, lms_profile.id)
        self.assertEqual(refreshed_profile.tagline, "Custom Enterprise LMS Tagline")
        self.assertEqual(refreshed_profile.overview, "Custom pre-existing LMS overview.")

    def test_fieldops_suite_structure(self):
        call_command("register_showcase_catalog")

        fieldops = Product.objects.get(code="fieldops")
        self.assertIsNotNone(fieldops)

        # Check sub-products
        sub_codes = set(fieldops.sub_products.values_list("code", flat=True))
        self.assertIn("crm-logicon", sub_codes)
        self.assertTrue("fieldsense" in sub_codes or "fieldsence" in sub_codes)
        self.assertIn("sales-tracker", sub_codes)

        # Check modules on FIELDOPS
        mod_codes = set(fieldops.modules.values_list("code", flat=True))
        self.assertIn("fieldops_crm", mod_codes)
        self.assertIn("fieldops_sales", mod_codes)
        self.assertTrue("fieldops_fieldsense" in mod_codes or "fieldops_fieldsence" in mod_codes)

    def test_qbr_demo_launchability_and_execution(self):
        call_command("register_showcase_catalog")

        qbr_prod = Product.objects.get(code="qbr")
        qbr_profile = ProductShowcaseProfile.objects.get(product=qbr_prod)

        contract = ProductShowcaseService.launchability_contract(profile_id=str(qbr_profile.id))
        self.assertTrue(contract["launchable"])
        self.assertEqual(contract["reason"], "READY")
        self.assertEqual(contract["launch_mode"], "demo_only")
        self.assertIn("https://excelreports.vibecopilot.ai/", contract["allowed_targets"])
        self.assertEqual(contract["target_environment"]["base_url"], "https://excelreports.vibecopilot.ai/")

        # Test launch demo execution returns verified redirect URL
        result = ProductShowcaseService.launch_demo(profile_id=str(qbr_profile.id), actor=self.owner)
        self.assertEqual(result["redirect_url"], "https://excelreports.vibecopilot.ai/")
        self.assertEqual(result["target_name"], "QBR Live Web Demo")

    def test_hrms_demo_environment_configured(self):
        call_command("register_showcase_catalog")

        hrms_prod = Product.objects.get(code="hrms")
        hrms_profile = ProductShowcaseProfile.objects.get(product=hrms_prod)
        contract = ProductShowcaseService.launchability_contract(profile_id=str(hrms_profile.id))

        self.assertTrue(contract["launchable"])
        self.assertEqual(contract["launch_mode"], "demo_only")
        self.assertEqual(contract.get("open_mode"), "embed")
        self.assertIn("https://hrms.vibesandbox.live", contract["allowed_targets"])
        self.assertEqual(contract["target_environment"]["base_url"], "https://hrms.vibesandbox.live")

        result = ProductShowcaseService.launch_demo(profile_id=str(hrms_profile.id), actor=self.owner)
        self.assertEqual(result["redirect_url"], "https://hrms.vibesandbox.live")
        self.assertEqual(result["target_name"], "PeoplePulse HRMS Sandbox")
        self.assertEqual(result.get("open_mode"), "embed")

    def test_non_demo_products_distinguished_from_demo_readiness(self):
        call_command("register_showcase_catalog")

        # Products without demo environments should be catalog available but demo disabled
        for code in ("leasing", "inventory", "ats"):
            prod = Product.objects.get(code=code)
            profile = ProductShowcaseProfile.objects.get(product=prod)
            contract = ProductShowcaseService.launchability_contract(profile_id=str(profile.id))

            self.assertFalse(contract["launchable"], f"Product {code} should not be launchable without demo env")
            self.assertEqual(contract["launch_mode"], "disabled")
            self.assertEqual(contract["allowed_targets"], [])

            # Attempting to launch demo must raise error
            with self.assertRaises(Exception):
                ProductShowcaseService.launch_demo(profile_id=str(profile.id), actor=self.owner)

    def test_presentation_portfolio_category_filtering_and_hidden_qbr(self):
        call_command("register_showcase_catalog")

        # Filter by "Supply Chain"
        supply_chain_profiles = ShowcasePresentationService.presentation_portfolio(category_filter="Supply Chain")
        sc_codes = {p.product.code for p in supply_chain_profiles}
        self.assertIn("vms-warehouse", sc_codes)
        self.assertIn("inventory", sc_codes)
        self.assertNotIn("hrms", sc_codes)

        # QBR is hidden, so presentation portfolio must NOT include it
        all_presentation = ShowcasePresentationService.presentation_portfolio()
        pres_codes = {p.product.code for p in all_presentation}
        self.assertNotIn("qbr", pres_codes)

        # Profile itself has HIDDEN visibility
        qbr_prof = ProductShowcaseProfile.objects.get(product__code="qbr")
        self.assertEqual(qbr_prof.visibility, ShowcaseVisibility.HIDDEN)

    def test_api_permissions_owner_vs_tenant(self):
        call_command("register_showcase_catalog")

        # Platform owner can list presentation profiles (19 published products, QBR hidden)
        res = self.client.get("/api/v1/showcase/present/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.data), 19)
        present_codes = [p["product_code"] for p in res.data]
        self.assertNotIn("qbr", present_codes)
        self.assertIn("lms", present_codes)

        # Tenant user gets 403
        tenant_user = User.objects.create_user(
            email="tenant_showcase@vc.test",
            password="pw",
            full_name="Tenant User",
            is_platform_owner=False,
            status="active",
        )
        tenant_client = APIClient()
        tenant_client.force_authenticate(user=tenant_user)

        res_tenant = tenant_client.get("/api/v1/showcase/present/")
        self.assertEqual(res_tenant.status_code, 403)
