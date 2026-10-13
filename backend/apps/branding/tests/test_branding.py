"""Minimal Authoritative Test Suite for Branding (Phase 4A/4B).

Covers the 4 required minimal tests:
1. Immutability: Published revisions cannot be altered.
2. Rollback creates new revision: Rolling back generates an incremental revision copy.
3. Fallback to global: Tenant without override inherits global branding profile tokens.
4. Permission denial: Unauthorized tenant users or non-owners are denied modification access.
"""

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.branding.models import BrandingProfile, BrandingRevision
from apps.branding.services import (
    create_draft_revision,
    get_active_branding,
    get_or_create_profile,
    publish_revision,
    rollback_to_revision,
)
from apps.access_control.models import (
    AccessPermission,
    ConsoleModule,
    OrganizationConsoleModulePolicy,
    OrganizationPermissionCeiling,
    Role,
)
from apps.organizations.models import (
    MembershipStatus,
    MembershipType,
    Organization,
    OrganizationMembership,
    OrganizationStatus,
)

PlatformUser = get_user_model()


class BrandingMinimalTests(TestCase):
    """Verifies the four required Phase 4A/4B criteria."""

    def setUp(self):
        self.client = APIClient()

        # Platform owner
        self.owner = PlatformUser.objects.create_user(
            email="branding_owner@example.com",
            password="testpassword123",
            is_platform_owner=True,
        )

        # Tenant Org & Users
        self.org = Organization.objects.create(
            name="Alpha Corp",
            code="alpha-corp",
            status=OrganizationStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )
        self.tenant_admin = PlatformUser.objects.create_user(
            email="tenant_admin@alpha.com",
            password="testpassword123",
            is_platform_owner=False,
        )
        sys_role = Role.objects.get(code="system_tenant_admin")
        OrganizationMembership.objects.create(
            organization=self.org,
            user=self.tenant_admin,
            membership_type=MembershipType.TENANT_ADMIN,
            status=MembershipStatus.ACTIVE,
            role=sys_role,
            joined_at=timezone.now(),
        )

        self.regular_member = PlatformUser.objects.create_user(
            email="regular_member@alpha.com",
            password="testpassword123",
            is_platform_owner=False,
        )
        OrganizationMembership.objects.create(
            organization=self.org,
            user=self.regular_member,
            membership_type=MembershipType.MEMBER,
            status=MembershipStatus.ACTIVE,
            joined_at=timezone.now(),
        )

        # Configure organization module policy and ceilings for tenant_branding
        mod_branding = ConsoleModule.objects.filter(key="tenant_branding").first()
        if mod_branding:
            OrganizationConsoleModulePolicy.objects.get_or_create(
                organization=self.org,
                console_module=mod_branding,
                defaults={"is_enabled": True},
            )
            for perm in AccessPermission.objects.filter(console_module=mod_branding):
                OrganizationPermissionCeiling.objects.get_or_create(
                    organization=self.org,
                    permission=perm,
                    defaults={"is_allowed": True},
                )

    def test_01_published_revision_immutability(self):
        """1. Immutability: Attempting to modify a published revision fails."""
        profile = get_or_create_profile(organization=self.org, actor=self.tenant_admin)
        rev = profile.revisions.first()
        # Publish revision
        published = publish_revision(revision_id=rev.id, actor=self.tenant_admin)
        self.assertEqual(published.status, "published")

        # Direct model save modification should raise ValidationError
        published.tokens = {"brand_primary": "#ff0000"}
        with self.assertRaises(ValidationError) as ctx:
            published.save()
        self.assertIn("Published revisions are immutable", str(ctx.exception))

        # API PATCH attempt should return 400 Bad Request
        self.client.force_authenticate(user=self.tenant_admin)
        res = self.client.patch(
            f"/api/v1/branding/revisions/{published.id}/",
            {"tokens": {"brand_primary": "#00ff00"}},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("immutable", str(res.data.get("detail", "")).lower())

    def test_02_rollback_creates_new_revision(self):
        """2. Rollback creates new revision: Rolling back creates an incremental revision copy."""
        profile = get_or_create_profile(organization=self.org, actor=self.tenant_admin)
        rev1 = profile.revisions.first()
        rev1.tokens = {"brand_primary": "#111111"}
        rev1.save()
        publish_revision(revision_id=rev1.id, actor=self.tenant_admin)

        # Create revision 2 and publish it
        rev2 = create_draft_revision(
            profile_id=profile.id,
            actor=self.tenant_admin,
            tokens={"brand_primary": "#222222"},
        )
        publish_revision(revision_id=rev2.id, actor=self.tenant_admin)
        self.assertEqual(rev2.revision_number, 2)

        # Roll back to revision 1
        rev3 = rollback_to_revision(target_revision_id=rev1.id, actor=self.tenant_admin)

        # Must generate new revision copy with incremented revision number
        self.assertEqual(rev3.revision_number, 3)
        self.assertEqual(rev3.status, "published")
        self.assertEqual(rev3.tokens.get("brand_primary"), "#111111")

        # Prior revision 2 must now be archived
        rev2.refresh_from_db()
        self.assertEqual(rev2.status, "archived")

    def test_03_fallback_to_global_when_no_tenant_override(self):
        """3. Fallback-to-global: Tenant with no override inherits global profile tokens."""
        # Setup Global Profile with custom brand primary
        global_profile = get_or_create_profile(organization=None, actor=self.owner)
        global_rev = global_profile.revisions.filter(status="published").first()
        global_rev.tokens = {"brand_primary": "#7c3aed", "bg_app": "#0a0a0a"}
        # Save via direct QuerySet update or recreate to simulate initial seed
        BrandingRevision.objects.filter(id=global_rev.id).update(tokens={"brand_primary": "#7c3aed", "bg_app": "#0a0a0a"})

        # New tenant organization with zero branding profile
        fresh_org = Organization.objects.create(
            name="Beta Corp",
            code="beta-corp",
            status=OrganizationStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )

        # Resolve active branding
        active = get_active_branding(organization_id=fresh_org.id)
        self.assertTrue(active["is_global_fallback"])
        self.assertFalse(active["is_override"])
        self.assertEqual(active["tokens"]["brand_primary"], "#7c3aed")
        self.assertEqual(active["tokens"]["bg_app"], "#0a0a0a")

        # API resolution via GET /api/v1/branding/active/?organization_id=...
        self.client.force_authenticate(user=self.tenant_admin)
        res = self.client.get(f"/api/v1/branding/active/?organization_id={fresh_org.id}")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertTrue(res.data["is_global_fallback"])
        self.assertEqual(res.data["tokens"]["brand_primary"], "#7c3aed")

    def test_04_permission_denial_for_unauthorized_user(self):
        """4. Permission denial: Non-admin tenant user cannot publish or edit branding."""
        profile = get_or_create_profile(organization=self.org, actor=self.tenant_admin)
        rev = profile.revisions.first()

        # Regular member attempts to publish revision
        self.client.force_authenticate(user=self.regular_member)
        res_publish = self.client.post(f"/api/v1/branding/revisions/{rev.id}/publish/")
        self.assertEqual(res_publish.status_code, status.HTTP_403_FORBIDDEN)

        # Regular member attempts to update draft
        res_patch = self.client.patch(
            f"/api/v1/branding/revisions/{rev.id}/",
            {"tokens": {"brand_primary": "#ff00ff"}},
            format="json",
        )
        self.assertEqual(res_patch.status_code, status.HTTP_403_FORBIDDEN)

        # Tenant admin cannot manage global branding profile
        global_profile = get_or_create_profile(organization=None, actor=self.owner)
        self.client.force_authenticate(user=self.tenant_admin)
        res_global = self.client.post(
            f"/api/v1/branding/profiles/{global_profile.id}/revisions/",
            {"tokens": {"brand_primary": "#ff00ff"}},
            format="json",
        )
        self.assertEqual(res_global.status_code, status.HTTP_403_FORBIDDEN)

    def test_05_permission_denial_without_branding_view(self):
        """5. Permission denial: Tenant user lacking branding.view cannot access branding profiles."""
        self.client.force_authenticate(user=self.regular_member)
        res = self.client.get(f"/api/v1/branding/profiles/?organization_id={self.org.id}")
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn("branding.view", str(res.data.get("detail", "")))
