"""Tests for Phase 6B-4 Developer Console Management APIs.

Validates:
- Tenant Admin application management & strict tenant isolation
- Key creation, rotation, one-time secret display, and revocation
- Tenant Member denial (NO_CONSOLE_ACCESS)
- Platform Owner oversight and emergency revocation
- AuditLog records for management actions
"""

import uuid
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.access_control.models import Role
from apps.auditlog.models import AuditAction, AuditLog, AuditTargetType
from apps.developer_console.models import DeveloperApiKey, DeveloperApplication
from apps.organizations.models import (
    MembershipStatus,
    MembershipType,
    Organization,
    OrganizationMembership,
    OrganizationStatus,
)

User = get_user_model()


class DeveloperConsoleManagementTests(TestCase):
    def setUp(self):
        self.client = APIClient()

        # Users
        self.owner = User.objects.create_user(
            email="owner@example.com",
            password="Password123!",
            is_platform_owner=True,
            status="active",
        )
        self.tenant_admin_a = User.objects.create_user(
            email="admin_a@tenant.com",
            password="Password123!",
            status="active",
        )
        self.tenant_admin_b = User.objects.create_user(
            email="admin_b@tenant.com",
            password="Password123!",
            status="active",
        )
        self.tenant_member_a = User.objects.create_user(
            email="member_a@tenant.com",
            password="Password123!",
            status="active",
        )

        # Organizations
        self.org_a = Organization.objects.create(
            name="Org Alpha",
            code="org-alpha",
            status=OrganizationStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )
        self.org_b = Organization.objects.create(
            name="Org Beta",
            code="org-beta",
            status=OrganizationStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )

        # Roles for Tenant Admins
        self.admin_role_a = Role.objects.create(
            organization=self.org_a,
            code="admin_role_a",
            name="Tenant Admin Role A",
            created_by=self.owner,
            updated_by=self.owner,
        )
        self.admin_role_b = Role.objects.create(
            organization=self.org_b,
            code="admin_role_b",
            name="Tenant Admin Role B",
            created_by=self.owner,
            updated_by=self.owner,
        )

        # Memberships
        OrganizationMembership.objects.create(
            user=self.tenant_admin_a,
            organization=self.org_a,
            membership_type=MembershipType.TENANT_ADMIN,
            status=MembershipStatus.ACTIVE,
            role=self.admin_role_a,
            joined_at=timezone.now(),
        )
        OrganizationMembership.objects.create(
            user=self.tenant_admin_b,
            organization=self.org_b,
            membership_type=MembershipType.TENANT_ADMIN,
            status=MembershipStatus.ACTIVE,
            role=self.admin_role_b,
            joined_at=timezone.now(),
        )
        OrganizationMembership.objects.create(
            user=self.tenant_member_a,
            organization=self.org_a,
            membership_type=MembershipType.MEMBER,
            status=MembershipStatus.ACTIVE,
            role=None,
            joined_at=timezone.now(),
        )

    def _login_as(self, user, context_type="tenant", organization=None):
        self.client.force_authenticate(user=user)
        session = self.client.session
        session["active_context_type"] = context_type
        session["tenant_organization_id"] = str(organization.id) if organization else None
        session.save()

    def test_tenant_admin_create_and_list_application(self):
        self._login_as(self.tenant_admin_a, organization=self.org_a)

        # Create app
        resp = self.client.post(
            "/api/v1/tenant/developer/apps/",
            {"name": "Alpha Integration App", "description": "Used for internal sync"},
            format="json",
        )
        self.assertEqual(resp.status_code, 201)
        app_id = resp.data["id"]
        self.assertEqual(resp.data["name"], "Alpha Integration App")
        self.assertEqual(resp.data["status"], "active")
        self.assertEqual(resp.data["organization"]["id"], str(self.org_a.id))

        # Verify audit log
        audit = AuditLog.objects.filter(
            action=AuditAction.DEVELOPER_APPLICATION_CREATED,
            target_id=app_id,
        ).first()
        self.assertIsNotNone(audit)
        self.assertEqual(audit.organization_id, self.org_a.id)

        # List apps
        list_resp = self.client.get("/api/v1/tenant/developer/apps/")
        self.assertEqual(list_resp.status_code, 200)
        self.assertEqual(list_resp.data["count"], 1)
        self.assertEqual(list_resp.data["results"][0]["id"], app_id)

    def test_tenant_admin_cross_tenant_isolation(self):
        # Admin A creates app
        self._login_as(self.tenant_admin_a, organization=self.org_a)
        resp_a = self.client.post(
            "/api/v1/tenant/developer/apps/",
            {"name": "Alpha App"},
            format="json",
        )
        app_a_id = resp_a.data["id"]

        # Admin B should not see App A
        self._login_as(self.tenant_admin_b, organization=self.org_b)
        list_resp = self.client.get("/api/v1/tenant/developer/apps/")
        self.assertEqual(list_resp.status_code, 200)
        self.assertEqual(list_resp.data["count"], 0)

        # Admin B directly accessing App A receives 404
        detail_resp = self.client.get(f"/api/v1/tenant/developer/apps/{app_a_id}/")
        self.assertEqual(detail_resp.status_code, 404)

    def test_tenant_member_denial(self):
        self._login_as(self.tenant_member_a, organization=self.org_a)

        # Member cannot access tenant developer management
        resp = self.client.get("/api/v1/tenant/developer/apps/")
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.data.get("code"), "NO_CONSOLE_ACCESS")

        post_resp = self.client.post(
            "/api/v1/tenant/developer/apps/",
            {"name": "Unauthorized App"},
            format="json",
        )
        self.assertEqual(post_resp.status_code, 403)
        self.assertEqual(post_resp.data.get("code"), "NO_CONSOLE_ACCESS")

    def test_application_lifecycle(self):
        self._login_as(self.tenant_admin_a, organization=self.org_a)
        create_resp = self.client.post(
            "/api/v1/tenant/developer/apps/",
            {"name": "Lifecycle App"},
            format="json",
        )
        app_id = create_resp.data["id"]

        # Suspend
        suspend_resp = self.client.post(f"/api/v1/tenant/developer/apps/{app_id}/suspend/", format="json")
        self.assertEqual(suspend_resp.status_code, 200)
        self.assertEqual(suspend_resp.data["status"], "suspended")

        # Reactivate
        reactivate_resp = self.client.post(f"/api/v1/tenant/developer/apps/{app_id}/reactivate/", format="json")
        self.assertEqual(reactivate_resp.status_code, 200)
        self.assertEqual(reactivate_resp.data["status"], "active")

        # Revoke
        revoke_resp = self.client.post(f"/api/v1/tenant/developer/apps/{app_id}/revoke/", format="json")
        self.assertEqual(revoke_resp.status_code, 200)
        self.assertEqual(revoke_resp.data["status"], "revoked")

        # Cannot reactivate revoked app
        fail_reactivate = self.client.post(f"/api/v1/tenant/developer/apps/{app_id}/reactivate/", format="json")
        self.assertEqual(fail_reactivate.status_code, 400)

    def test_key_creation_rotation_and_revocation(self):
        self._login_as(self.tenant_admin_a, organization=self.org_a)
        app_resp = self.client.post(
            "/api/v1/tenant/developer/apps/",
            {"name": "Key Test App"},
            format="json",
        )
        app_id = app_resp.data["id"]

        # 1. Create Key
        key_resp = self.client.post(
            f"/api/v1/tenant/developer/apps/{app_id}/keys/",
            {"name": "Sync Key", "scopes": ["catalog:read", "organization:read"]},
            format="json",
        )
        self.assertEqual(key_resp.status_code, 201)
        self.assertIn("plaintext_key", key_resp.data)
        full_key = key_resp.data["plaintext_key"]
        self.assertTrue(full_key.startswith("vck_live_"))
        key_id = key_resp.data["id"]

        # Verify key listed does NOT include plaintext_key
        list_keys = self.client.get(f"/api/v1/tenant/developer/apps/{app_id}/keys/")
        self.assertEqual(list_keys.status_code, 200)
        self.assertEqual(list_keys.data["count"], 1)
        self.assertNotIn("plaintext_key", list_keys.data["results"][0])

        # 2. Rotate Key
        rotate_resp = self.client.post(
            f"/api/v1/tenant/developer/apps/{app_id}/keys/{key_id}/rotate/",
            format="json",
        )
        self.assertEqual(rotate_resp.status_code, 200)
        self.assertIn("plaintext_key", rotate_resp.data)
        new_key_id = rotate_resp.data["id"]
        self.assertNotEqual(key_id, new_key_id)

        # Old key is now revoked
        old_key = DeveloperApiKey.objects.get(pk=key_id)
        self.assertEqual(old_key.status, "revoked")
        self.assertIsNotNone(old_key.revoked_at)

        # 3. Revoke New Key
        revoke_resp = self.client.post(
            f"/api/v1/tenant/developer/apps/{app_id}/keys/{new_key_id}/revoke/",
            format="json",
        )
        self.assertEqual(revoke_resp.status_code, 200)
        self.assertEqual(revoke_resp.data["status"], "revoked")

    def test_platform_owner_oversight_and_emergency_action(self):
        # Admin A creates app and key
        self._login_as(self.tenant_admin_a, organization=self.org_a)
        app_resp = self.client.post(
            "/api/v1/tenant/developer/apps/",
            {"name": "Owner Oversight Target"},
            format="json",
        )
        app_id = app_resp.data["id"]
        key_resp = self.client.post(
            f"/api/v1/tenant/developer/apps/{app_id}/keys/",
            {"name": "Vulnerable Key", "scopes": ["catalog:read"]},
            format="json",
        )
        key_id = key_resp.data["id"]

        # Platform Owner views apps across tenants
        self._login_as(self.owner, context_type="platform_owner", organization=None)
        owner_list = self.client.get("/api/v1/owner/developer/apps/")
        self.assertEqual(owner_list.status_code, 200)
        self.assertTrue(any(app["id"] == app_id for app in owner_list.data["results"]))

        # Platform Owner emergency key revocation
        emergency_revoke = self.client.post(
            f"/api/v1/owner/developer/apps/{app_id}/keys/{key_id}/revoke/",
            {"reason": "Credential leaked publicly"},
            format="json",
        )
        self.assertEqual(emergency_revoke.status_code, 200)
        self.assertEqual(emergency_revoke.data["status"], "revoked")

        # Verify audit log recorded emergency revocation
        audit = AuditLog.objects.filter(
            action=AuditAction.DEVELOPER_KEY_REVOKED,
            target_id=key_id,
        ).order_by("-timestamp").first()
        self.assertIsNotNone(audit)
        self.assertTrue(audit.metadata.get("is_emergency"))
