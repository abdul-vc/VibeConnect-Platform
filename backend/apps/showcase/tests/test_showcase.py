"""Showcase Minimal Acceptance Tests – Phase 11.

One test per acceptance criterion:
1. CRUD works (create + update profile)
2. Publish/unpublish works
3. Tenant user gets 403
4. Invalid URL scheme rejected
5. Audit event recorded on publish
"""
from __future__ import annotations

from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.showcase.models import ProductShowcaseProfile, ShowcaseVisibility
from apps.showcase.services import ProductShowcaseService, ShowcaseServiceError
from apps.auditlog.models import AuditLog, AuditAction

User = get_user_model()


def _make_owner(**kwargs):
    defaults = dict(
        email="owner@vc.test",
        full_name="Owner",
        is_platform_owner=True,
        is_staff=True,
        status="active",
    )
    defaults.update(kwargs)
    user = User(**defaults)
    user.set_password("pw")
    user.save()
    return user


def _make_product(owner):
    from apps.product_registry.models import Product, ProductStatus
    return Product.objects.create(
        code="test-showcase",
        name="Test Showcase Product",
        status=ProductStatus.ACTIVE,
        created_by=owner,
        updated_by=owner,
    )


class ShowcaseCRUDTest(TestCase):
    """AC-1: CRUD works."""

    def setUp(self):
        self.owner = _make_owner()
        self.product = _make_product(self.owner)

    def test_create_and_update_profile(self):
        profile = ProductShowcaseService.create_profile(
            product_id=str(self.product.pk),
            actor=self.owner,
            data={"tagline": "Hello", "display_order": 0},
        )
        self.assertEqual(profile.product_id, self.product.pk)
        self.assertEqual(profile.tagline, "Hello")

        updated = ProductShowcaseService.update_profile(
            profile_id=str(profile.pk),
            actor=self.owner,
            data={"tagline": "Updated"},
        )
        self.assertEqual(updated.tagline, "Updated")

    def test_duplicate_profile_raises(self):
        ProductShowcaseService.create_profile(
            product_id=str(self.product.pk),
            actor=self.owner,
            data={},
        )
        with self.assertRaises(ShowcaseServiceError):
            ProductShowcaseService.create_profile(
                product_id=str(self.product.pk),
                actor=self.owner,
                data={},
            )


class ShowcasePublishUnpublishTest(TestCase):
    """AC-2: Publish/unpublish works."""

    def setUp(self):
        self.owner = _make_owner(email="owner2@vc.test")
        self.product = _make_product(self.owner)
        self.profile = ProductShowcaseService.create_profile(
            product_id=str(self.product.pk),
            actor=self.owner,
            data={},
        )

    def test_publish_sets_published_visibility(self):
        profile = ProductShowcaseService.publish_profile(
            profile_id=str(self.profile.pk), actor=self.owner
        )
        self.assertEqual(profile.visibility, ShowcaseVisibility.PUBLISHED)

    def test_unpublish_sets_hidden_visibility(self):
        ProductShowcaseService.publish_profile(
            profile_id=str(self.profile.pk), actor=self.owner
        )
        profile = ProductShowcaseService.unpublish_profile(
            profile_id=str(self.profile.pk), actor=self.owner
        )
        self.assertEqual(profile.visibility, ShowcaseVisibility.HIDDEN)


class ShowcaseTenantForbiddenTest(TestCase):
    """AC-3: Tenant user gets 403."""

    def setUp(self):
        self.tenant_user = User.objects.create_user(
            email="tenant@vc.test",
            password="pw",
            full_name="Tenant",
            is_platform_owner=False,
            status="active",
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.tenant_user)

    def test_tenant_gets_403_on_profiles_list(self):
        response = self.client.get("/api/v1/showcase/profiles/")
        self.assertEqual(response.status_code, 403)


class ShowcaseInvalidUrlSchemeTest(TestCase):
    """AC-4: Invalid URL scheme rejected."""

    def setUp(self):
        self.owner = _make_owner(email="owner4@vc.test")
        self.product = _make_product(self.owner)
        self.profile = ProductShowcaseService.create_profile(
            product_id=str(self.product.pk),
            actor=self.owner,
            data={},
        )

    def test_javascript_scheme_rejected(self):
        with self.assertRaises(Exception):
            ProductShowcaseService.add_media(
                profile_id=str(self.profile.pk),
                actor=self.owner,
                data={
                    "media_type": "screenshot",
                    "title": "bad",
                    "url": "javascript:alert(1)",
                },
            )

    def test_http_scheme_rejected(self):
        with self.assertRaises(Exception):
            ProductShowcaseService.add_media(
                profile_id=str(self.profile.pk),
                actor=self.owner,
                data={
                    "media_type": "screenshot",
                    "title": "bad",
                    "url": "http://example.com/screenshot.png",
                },
            )

    def test_data_scheme_rejected(self):
        with self.assertRaises(Exception):
            ProductShowcaseService.add_media(
                profile_id=str(self.profile.pk),
                actor=self.owner,
                data={
                    "media_type": "screenshot",
                    "title": "bad",
                    "url": "data:text/html,<script>alert(1)</script>",
                },
            )


class ShowcaseLaunchabilityContractTest(TestCase):
    """Test launchability contract behavior with absent/present ProductLaunchConfig."""

    def setUp(self):
        self.owner = _make_owner(email="owner_launch@vc.test")
        self.product = _make_product(self.owner)
        self.profile = ProductShowcaseService.create_profile(
            product_id=str(self.product.pk),
            actor=self.owner,
            data={},
        )

    def test_contract_reflects_absent_launch_config(self):
        # No ProductLaunchConfig row exists for profile or product
        contract = ProductShowcaseService.launchability_contract(
            profile_id=str(self.profile.pk)
        )
        self.assertFalse(contract["launchable"])
        self.assertEqual(contract["reason"], "LAUNCH_CONFIG_NOT_FOUND")
        self.assertIsNone(contract["launch_mode"])
        self.assertEqual(contract["allowed_targets"], [])


class ShowcaseAuditEventTest(TestCase):
    """AC-5: Audit event recorded on publish."""

    def setUp(self):
        self.owner = _make_owner(email="owner5@vc.test")
        self.product = _make_product(self.owner)
        self.profile = ProductShowcaseService.create_profile(
            product_id=str(self.product.pk),
            actor=self.owner,
            data={},
        )

    def test_publish_records_audit_event(self):
        before_count = AuditLog.objects.filter(
            action=AuditAction.SHOWCASE_PROFILE_PUBLISHED
        ).count()
        ProductShowcaseService.publish_profile(
            profile_id=str(self.profile.pk), actor=self.owner
        )
        after_count = AuditLog.objects.filter(
            action=AuditAction.SHOWCASE_PROFILE_PUBLISHED
        ).count()
        self.assertEqual(after_count, before_count + 1)
