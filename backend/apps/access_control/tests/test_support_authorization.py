"""Phase 6C Support Authorization and Operations Regression Tests.

Verifies:
- Platform Owner support-operator grant, list, and revocation endpoints.
- Role boundary: support role does not grant platform_owner or superuser flags.
- Permission enforcement: support diagnostics require support.diagnostics.view.
- Tenant isolation and access denial for unauthenticated/unauthorized users.
"""

import uuid
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from apps.access_control.constants import (
    PERMISSION_SUPPORT_DIAGNOSTICS_VIEW,
    PREDEFINED_SUPPORT_ROLES,
    SUPPORT_ROLE_DIAGNOSTICS_VIEWER,
    SUPPORT_ROLE_OPERATOR,
    SUPPORT_ROLE_REMEDIATION_OPERATOR,
)
from apps.access_control.models import (
    AccessPermission,
    ConsoleModule,
    OrganizationConsoleModulePolicy,
    OrganizationPermissionCeiling,
    PlatformRoleAssignment,
    Role,
)
from apps.auditlog.models import AuditAction, AuditLog
from apps.organizations.models import (
    MembershipStatus,
    MembershipType,
    Organization,
    OrganizationMembership,
    OrganizationStatus,
)

User = get_user_model()


class SupportAuthorizationTests(TestCase):
    def setUp(self):
        super().setUp()
        self.client = APIClient()

        # Platform Owner
        self.owner = User.objects.create_user(
            email="owner@vibeconnect.internal",
            password="SecurePassword123!",
            full_name="Platform Owner",
            is_active=True,
            is_platform_owner=True,
        )

        # Candidate Support User
        self.candidate = User.objects.create_user(
            email="support_candidate@vibeconnect.internal",
            password="SecurePassword123!",
            full_name="Support Candidate",
            is_active=True,
            is_platform_owner=False,
        )

        # Tenant User
        self.tenant_user = User.objects.create_user(
            email="tenant_admin@example.com",
            password="SecurePassword123!",
            full_name="Tenant Admin",
            is_active=True,
            is_platform_owner=False,
        )

        self.org = Organization.objects.create(
            code="testorg",
            name="Test Org",
            status=OrganizationStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )

        from django.utils import timezone
        admin_role = Role.objects.filter(code="system_tenant_admin").first()
        self.membership = OrganizationMembership.objects.create(
            user=self.tenant_user,
            organization=self.org,
            membership_type=MembershipType.TENANT_ADMIN,
            status=MembershipStatus.ACTIVE,
            role=admin_role,
            joined_at=timezone.now(),
        )

        # Seed policies & ceilings for self.org
        tenant_mods = ConsoleModule.objects.filter(target_context="tenant", is_active=True)
        tenant_perms = AccessPermission.objects.filter(console_module__target_context="tenant", is_active=True)
        for mod in tenant_mods:
            OrganizationConsoleModulePolicy.objects.get_or_create(
                organization=self.org,
                console_module=mod,
                defaults={"is_enabled": True, "updated_by": self.owner},
            )
        for p in tenant_perms:
            OrganizationPermissionCeiling.objects.get_or_create(
                organization=self.org,
                permission=p,
                defaults={"is_allowed": True, "updated_by": self.owner},
            )

        # Seed Predefined Support Roles if not present from migrations
        for code, name in [
            (SUPPORT_ROLE_OPERATOR, "Support Operator"),
            (SUPPORT_ROLE_DIAGNOSTICS_VIEWER, "Support Diagnostics Viewer"),
            (SUPPORT_ROLE_REMEDIATION_OPERATOR, "Support Remediation Operator"),
        ]:
            if not Role.objects.filter(code=code, is_system_role=True).exists():
                Role.objects.create(
                    code=code,
                    name=name,
                    is_system_role=True,
                    status="active",
                )
        self.support_role = Role.objects.get(code=SUPPORT_ROLE_OPERATOR, is_system_role=True)

    def _login_tenant(self, user, org):
        self.client.force_login(user)
        session = self.client.session
        session["active_context_type"] = "tenant"
        session["tenant_organization_id"] = str(org.id)
        session.save()

    def test_unauthenticated_requests_are_rejected(self):
        response = self.client.get("/api/v1/owner/support-operators/")
        self.assertIn(response.status_code, [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN])

    def test_tenant_admin_cannot_access_support_operator_management(self):
        self.client.force_authenticate(user=self.tenant_user)
        response = self.client.get("/api/v1/owner/support-operators/")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_owner_can_grant_and_list_support_operator(self):
        self.client.force_authenticate(user=self.owner)
        
        # Grant
        payload = {
            "user_id": str(self.candidate.id),
            "role_code": SUPPORT_ROLE_OPERATOR,
        }
        res = self.client.post("/api/v1/owner/support-operators/", data=payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        assignment_id = res.data.get("id")

        # Verify PlatformRoleAssignment created
        assignment = PlatformRoleAssignment.objects.filter(user=self.candidate, role=self.support_role).first()
        self.assertIsNotNone(assignment)

        # List
        list_res = self.client.get("/api/v1/owner/support-operators/")
        self.assertEqual(list_res.status_code, status.HTTP_200_OK)
        user_ids = [str(item["user_id"]) for item in list_res.data]
        self.assertIn(str(self.candidate.id), user_ids)


        # Revoke via DELETE
        del_res = self.client.delete(f"/api/v1/owner/support-operators/{assignment_id}/")
        self.assertEqual(del_res.status_code, status.HTTP_204_NO_CONTENT)

        # Verify revoked
        self.assertFalse(PlatformRoleAssignment.objects.filter(id=assignment_id).exists())

    def test_duplicate_grant_is_handled_gracefully(self):
        self.client.force_authenticate(user=self.owner)
        payload = {
            "user_id": str(self.candidate.id),
            "role_code": SUPPORT_ROLE_OPERATOR,
        }
        res1 = self.client.post("/api/v1/owner/support-operators/", data=payload, format="json")
        self.assertEqual(res1.status_code, status.HTTP_201_CREATED)

        res2 = self.client.post("/api/v1/owner/support-operators/", data=payload, format="json")
        # Should be deterministic (either 200/201 or 400 with ALREADY_ASSIGNED)
        self.assertIn(res2.status_code, [status.HTTP_200_OK, status.HTTP_201_CREATED, status.HTTP_400_BAD_REQUEST])

    def test_arbitrary_or_tenant_scoped_roles_rejected(self):
        self.client.force_authenticate(user=self.owner)
        
        # Create a tenant-scoped role
        tenant_role = Role.objects.create(
            organization=self.org,
            code="tenant_custom_role",
            name="Custom Role",
            is_system_role=False,
            status="active",
        )

        payload = {
            "user_id": str(self.candidate.id),
            "role_code": tenant_role.code,
        }
        res = self.client.post("/api/v1/owner/support-operators/", data=payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_support_role_does_not_grant_superuser_or_owner_flags(self):
        self.client.force_authenticate(user=self.owner)
        payload = {
            "user_id": str(self.candidate.id),
            "role_code": SUPPORT_ROLE_OPERATOR,
        }
        self.client.post("/api/v1/owner/support-operators/", data=payload, format="json")

        self.candidate.refresh_from_db()
        self.assertFalse(self.candidate.is_platform_owner)
        self.assertFalse(self.candidate.is_superuser)
        self.assertFalse(self.candidate.is_staff)

    def test_support_diagnostics_requires_permission(self):
        # Tenant user without support permission
        self.client.force_authenticate(user=self.tenant_user)
        res = self.client.get(f"/api/v1/support/organizations/{self.org.id}/diagnostics/")
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

        # Platform owner has access
        self.client.force_authenticate(user=self.owner)
        res_owner = self.client.get(f"/api/v1/support/organizations/{self.org.id}/diagnostics/")
        self.assertIn("organization", res_owner.data)
        self.assertIn("health", res_owner.data)
        self.assertIn("control_plane_status", res_owner.data["health"])

    def test_canonical_support_roles_match_seeded_roles(self):
        expected_roles = {
            SUPPORT_ROLE_OPERATOR,
            SUPPORT_ROLE_DIAGNOSTICS_VIEWER,
            SUPPORT_ROLE_REMEDIATION_OPERATOR,
        }
        self.assertEqual(PREDEFINED_SUPPORT_ROLES, expected_roles)
        for role_code in expected_roles:
            role = Role.objects.filter(code=role_code, is_system_role=True, organization__isnull=True).first()
            self.assertIsNotNone(role, f"Seeded role {role_code} must exist.")
            self.assertEqual(role.status, "active")

    def test_owner_can_grant_and_revoke_all_canonical_support_roles_with_audit(self):
        self.client.force_authenticate(user=self.owner)
        for role_code in sorted(PREDEFINED_SUPPORT_ROLES):
            # Grant
            payload = {"user_id": str(self.candidate.id), "role_code": role_code}
            res = self.client.post("/api/v1/owner/support-operators/", data=payload, format="json")
            self.assertEqual(res.status_code, status.HTTP_201_CREATED)
            assignment_id = res.data["id"]

            # Verify audit log for grant
            self.assertTrue(
                AuditLog.objects.filter(
                    action=AuditAction.SUPPORT_ROLE_GRANTED,
                    metadata__role_code=role_code,
                    actor=self.owner,
                ).exists()
            )

            # Revoke
            del_res = self.client.delete(f"/api/v1/owner/support-operators/{assignment_id}/")
            self.assertEqual(del_res.status_code, status.HTTP_204_NO_CONTENT)

            # Verify audit log for revoke
            self.assertTrue(
                AuditLog.objects.filter(
                    action=AuditAction.SUPPORT_ROLE_REVOKED,
                    metadata__role_code=role_code,
                    actor=self.owner,
                ).exists()
            )

    def test_tenant_role_list_excludes_platform_support_roles(self):
        self._login_tenant(self.tenant_user, self.org)
        res = self.client.get("/api/v1/tenant/roles/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        role_codes = {r["code"] for r in res.data["results"]}
        self.assertTrue(role_codes.isdisjoint(PREDEFINED_SUPPORT_ROLES))

    def test_tenant_membership_assignment_rejects_platform_support_roles(self):
        self._login_tenant(self.tenant_user, self.org)
        for role_code in sorted(PREDEFINED_SUPPORT_ROLES):
            role = Role.objects.get(code=role_code, is_system_role=True)
            res = self.client.patch(
                f"/api/v1/tenant/admin-memberships/{self.membership.id}/role/",
                data={"role_id": str(role.id)},
                format="json",
            )
            self.assertIn(res.status_code, [status.HTTP_400_BAD_REQUEST, status.HTTP_404_NOT_FOUND])
            self.membership.refresh_from_db()
            self.assertNotEqual(self.membership.role_id, role.id)

