"""Focused Stage 4 API Tests for Platform Owner Policy and Ceiling Endpoints.

Verifies:
- Authorization boundaries (unauthenticated, tenant admin, member, wrong context, valid PO).
- Console-policy GET listing (filtering, ordering, deny-by-default, zero audit).
- Console-policy PATCH (mutations, core protection, module lookup, strict booleans, audit, isolation).
- Permission-ceiling GET listing (filtering, ordering, deny-by-default, zero audit).
- Permission-ceiling PATCH (mutations, dependency validation, lookup, strict booleans, audit, isolation).
- Immediate reflection of ceiling updates in Stage 3 centralized evaluation.
"""

import uuid
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.access_control.constants import CONTEXT_TENANT
from apps.access_control.models import (
    AccessPermission,
    ConsoleModule,
    ConsoleModuleContext,
    OrganizationConsoleModulePolicy,
    OrganizationPermissionCeiling,
    Role,
    RolePermission,
    RoleStatus,
)
from apps.access_control.services.evaluation import evaluate_access
from apps.auditlog.models import AuditAction, AuditLog, AuditTargetType
from apps.organizations.models import (
    MembershipStatus,
    MembershipType,
    Organization,
    OrganizationMembership,
    OrganizationStatus,
)

PlatformUser = get_user_model()


class Stage4PlatformOwnerApiTests(APITestCase):
    """Test suite covering the 4 locked Platform Owner policy & ceiling endpoints."""

    def setUp(self):
        super().setUp()
        cache.clear()
        self.password = "SecureTestPass123!"

        # 1. Platform Owner
        self.owner = PlatformUser.objects.create_user(
            email="owner@vibeconnect.internal",
            password=self.password,
            full_name="Platform Owner",
            status="active",
            is_active=True,
            is_platform_owner=True,
        )

        # 2. Regular User & Tenant Admin candidate
        self.admin_user = PlatformUser.objects.create_user(
            email="tenant_admin@vibeconnect.internal",
            password=self.password,
            full_name="Tenant Admin",
            status="active",
            is_active=True,
            is_platform_owner=False,
        )
        self.regular_user = PlatformUser.objects.create_user(
            email="member@vibeconnect.internal",
            password=self.password,
            full_name="Regular Member",
            status="active",
            is_active=True,
            is_platform_owner=False,
        )

        # 3. Organizations Alpha & Beta
        self.org_alpha = Organization.objects.create(
            code="org-alpha",
            name="Organization Alpha",
            status=OrganizationStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )
        self.org_beta = Organization.objects.create(
            code="org-beta",
            name="Organization Beta",
            status=OrganizationStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )

        # 4. Ensure System Role and permissions exist
        self.system_role, _ = Role.objects.get_or_create(
            code="system_tenant_admin",
            defaults={
                "name": "System Tenant Administrator",
                "is_system_role": True,
                "status": RoleStatus.ACTIVE,
                "organization": None,
            },
        )
        for perm in AccessPermission.objects.filter(console_module__target_context="tenant"):
            RolePermission.objects.get_or_create(role=self.system_role, permission=perm)

        # 5. Memberships
        self.membership_admin = OrganizationMembership.objects.create(
            organization=self.org_alpha,
            user=self.admin_user,
            membership_type=MembershipType.TENANT_ADMIN,
            status=MembershipStatus.ACTIVE,
            role=self.system_role,
            joined_at=timezone.now(),
        )
        self.membership_member = OrganizationMembership.objects.create(
            organization=self.org_alpha,
            user=self.regular_user,
            membership_type=MembershipType.MEMBER,
            status=MembershipStatus.ACTIVE,
            joined_at=timezone.now(),
        )

        # 6. Seed baseline policies & ceilings for Org Alpha & Beta
        mod_landing = ConsoleModule.objects.get(key="tenant_landing")
        mod_roles = ConsoleModule.objects.get(key="tenant_roles")

        for org in [self.org_alpha, self.org_beta]:
            OrganizationConsoleModulePolicy.objects.get_or_create(
                organization=org,
                console_module=mod_landing,
                defaults={"is_enabled": True, "updated_by": self.owner},
            )
            OrganizationConsoleModulePolicy.objects.get_or_create(
                organization=org,
                console_module=mod_roles,
                defaults={"is_enabled": True, "updated_by": self.owner},
            )
            for perm in AccessPermission.objects.filter(console_module__target_context="tenant"):
                OrganizationPermissionCeiling.objects.get_or_create(
                    organization=org,
                    permission=perm,
                    defaults={"is_allowed": True, "updated_by": self.owner},
                )

    def tearDown(self):
        cache.clear()
        super().tearDown()

    def _get_csrf_token(self) -> str:
        res = self.client.get("/api/v1/auth/csrf/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        return res.cookies[settings.CSRF_COOKIE_NAME].value

    def _login(self, email: str, password: str | None = None):
        token = self._get_csrf_token()
        return self.client.post(
            "/api/v1/auth/login/",
            {"email": email, "password": password or self.password},
            format="json",
            HTTP_X_CSRFTOKEN=token,
        )

    # ==========================================
    # 1. Authorization Tests (1 - 5)
    # ==========================================

    def test_01_unauthenticated_request_returns_401(self):
        """Unauthenticated requests to policy and ceiling endpoints return 401."""
        url_policy = f"/api/v1/organizations/{self.org_alpha.id}/console-policies/"
        res = self.client.get(url_policy)
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

        url_patch = f"/api/v1/organizations/{self.org_alpha.id}/console-policies/tenant_roles/"
        res = self.client.patch(url_patch, {"is_enabled": False}, format="json")
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

        url_ceilings = f"/api/v1/organizations/{self.org_alpha.id}/permission-ceilings/"
        res = self.client.get(url_ceilings)
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_02_tenant_admin_cannot_access_platform_owner_endpoints(self):
        """Tenant Admin receives 403 on all Platform Owner endpoints."""
        self._login(self.admin_user.email)
        token = self._get_csrf_token()

        res = self.client.get(f"/api/v1/organizations/{self.org_alpha.id}/console-policies/")
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

        res = self.client.patch(
            f"/api/v1/organizations/{self.org_alpha.id}/console-policies/tenant_roles/",
            {"is_enabled": False},
            format="json",
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

        res = self.client.get(f"/api/v1/organizations/{self.org_alpha.id}/permission-ceilings/")
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

        res = self.client.patch(
            f"/api/v1/organizations/{self.org_alpha.id}/permission-ceilings/roles.manage/",
            {"is_allowed": False},
            format="json",
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_03_regular_member_cannot_access_platform_owner_endpoints(self):
        """Regular member receives 403 on Platform Owner endpoints."""
        self.client.force_login(self.regular_user)
        res = self.client.get(f"/api/v1/organizations/{self.org_alpha.id}/console-policies/")
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_04_platform_owner_in_tenant_context_cannot_access(self):
        """Platform Owner operating in tenant context receives 403 until switched back."""
        self._login(self.owner.email)
        session = self.client.session
        session["active_context_type"] = "tenant"
        session["tenant_organization_id"] = str(self.org_alpha.id)
        session.save()

        res = self.client.get(f"/api/v1/organizations/{self.org_alpha.id}/console-policies/")
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_05_active_platform_owner_in_platform_owner_context_can_access(self):
        """Active Platform Owner in platform_owner context can access all 4 endpoints."""
        self._login(self.owner.email)
        res_policies = self.client.get(f"/api/v1/organizations/{self.org_alpha.id}/console-policies/")
        self.assertEqual(res_policies.status_code, status.HTTP_200_OK)

        res_ceilings = self.client.get(f"/api/v1/organizations/{self.org_alpha.id}/permission-ceilings/")
        self.assertEqual(res_ceilings.status_code, status.HTTP_200_OK)

    # ==========================================
    # 2. Console-Policy GET Tests (6 - 10)
    # ==========================================

    def test_06_console_policy_get_returns_only_tenant_modules(self):
        """GET console-policies returns only tenant modules."""
        self._login(self.owner.email)
        res = self.client.get(f"/api/v1/organizations/{self.org_alpha.id}/console-policies/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        keys = [item["module_key"] for item in res.data]
        self.assertEqual(
            keys,
            [
                "tenant_landing",
                "tenant_my_products",
                "tenant_roles",
                "tenant_bulk_import",
                "tenant_product_assignments",
                "tenant_access_requests",
                "tenant_notifications",
                "tenant_branding",
                "tenant_usage",
                "tenant_billing",
                "tenant_reports",
            ],
        )

        landing = next(i for i in res.data if i["module_key"] == "tenant_landing")
        self.assertTrue(landing["is_core"])
        self.assertFalse(landing["can_disable"])
        self.assertTrue(landing["is_enabled"])

        roles = next(i for i in res.data if i["module_key"] == "tenant_roles")
        self.assertFalse(roles["is_core"])
        self.assertTrue(roles["can_disable"])
        self.assertTrue(roles["is_enabled"])

    def test_07_console_policy_get_excludes_all_po_modules(self):
        """GET console-policies excludes all platform owner (po_*) modules."""
        self._login(self.owner.email)
        res = self.client.get(f"/api/v1/organizations/{self.org_alpha.id}/console-policies/")
        for item in res.data:
            self.assertFalse(item["module_key"].startswith("po_"))

    def test_08_console_policy_get_deterministic_ordering(self):
        """GET console-policies sorts deterministically by sort_order, then key."""
        self._login(self.owner.email)
        res = self.client.get(f"/api/v1/organizations/{self.org_alpha.id}/console-policies/")
        keys = [item["module_key"] for item in res.data]
        self.assertEqual(
            keys,
            [
                "tenant_landing",
                "tenant_my_products",
                "tenant_roles",
                "tenant_bulk_import",
                "tenant_product_assignments",
                "tenant_access_requests",
                "tenant_notifications",
                "tenant_branding",
                "tenant_usage",
                "tenant_billing",
                "tenant_reports",
            ],
        )

    def test_09_console_policy_get_missing_policy_represented_as_disabled_without_creating_row(self):
        """Missing optional policy state is represented as disabled; GET never creates rows."""
        org_fresh = Organization.objects.create(
            code="org-fresh",
            name="Fresh Org",
            status=OrganizationStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )
        # Ensure zero policies exist for fresh org
        OrganizationConsoleModulePolicy.objects.filter(organization=org_fresh).delete()

        self._login(self.owner.email)
        res = self.client.get(f"/api/v1/organizations/{org_fresh.id}/console-policies/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        landing = next(i for i in res.data if i["module_key"] == "tenant_landing")
        self.assertTrue(landing["is_enabled"])
        self.assertFalse(landing["can_disable"])

        roles = next(i for i in res.data if i["module_key"] == "tenant_roles")
        self.assertFalse(roles["is_enabled"])  # Deny-by-default
        self.assertTrue(roles["can_disable"])
        self.assertIsNone(roles["updated_at"])

        # Verification: No rows were created
        self.assertEqual(
            OrganizationConsoleModulePolicy.objects.filter(organization=org_fresh).count(),
            0,
        )

    def test_10_console_policy_get_emits_no_audit_event(self):
        """GET console-policies is read-only and emits zero audit events."""
        self._login(self.owner.email)
        count_before = AuditLog.objects.count()

        res = self.client.get(f"/api/v1/organizations/{self.org_alpha.id}/console-policies/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(AuditLog.objects.count(), count_before)

    # ==========================================
    # 3. Console-Policy PATCH Tests (11 - 17)
    # ==========================================

    def test_11_console_policy_patch_tenant_roles_can_be_enabled_and_disabled(self):
        """tenant_roles can be successfully disabled and re-enabled."""
        self._login(self.owner.email)
        token = self._get_csrf_token()
        url = f"/api/v1/organizations/{self.org_alpha.id}/console-policies/tenant_roles/"

        # Disable
        res = self.client.patch(url, {"is_enabled": False}, format="json", HTTP_X_CSRFTOKEN=token)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertFalse(res.data["is_enabled"])
        self.assertEqual(res.data["module_key"], "tenant_roles")

        # Re-enable
        token = self._get_csrf_token()
        res = self.client.patch(url, {"is_enabled": True}, format="json", HTTP_X_CSRFTOKEN=token)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertTrue(res.data["is_enabled"])

    def test_12_console_policy_patch_disabling_tenant_landing_returns_module_cannot_be_disabled(self):
        """Attempting to disable core module tenant_landing returns 400 MODULE_CANNOT_BE_DISABLED."""
        self._login(self.owner.email)
        token = self._get_csrf_token()
        url = f"/api/v1/organizations/{self.org_alpha.id}/console-policies/tenant_landing/"

        res = self.client.patch(url, {"is_enabled": False}, format="json", HTTP_X_CSRFTOKEN=token)
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(res.data["code"], "MODULE_CANNOT_BE_DISABLED")

    def test_13_console_policy_patch_unknown_or_po_module_returns_module_not_found(self):
        """Unknown or Platform Owner module keys return 404 MODULE_NOT_FOUND."""
        self._login(self.owner.email)
        token = self._get_csrf_token()

        res_unknown = self.client.patch(
            f"/api/v1/organizations/{self.org_alpha.id}/console-policies/nonexistent_mod/",
            {"is_enabled": True},
            format="json",
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(res_unknown.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(res_unknown.data["code"], "MODULE_NOT_FOUND")

        token = self._get_csrf_token()
        res_po = self.client.patch(
            f"/api/v1/organizations/{self.org_alpha.id}/console-policies/po_overview/",
            {"is_enabled": True},
            format="json",
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(res_po.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(res_po.data["code"], "MODULE_NOT_FOUND")

    def test_14_console_policy_patch_strict_boolean_validation_rejects_invalid_input(self):
        """Rejects missing, string, integer, null, or unrelated fields with 400 VALIDATION_ERROR."""
        self._login(self.owner.email)
        url = f"/api/v1/organizations/{self.org_alpha.id}/console-policies/tenant_roles/"

        invalid_payloads = [
            {},
            {"is_enabled": "true"},
            {"is_enabled": "false"},
            {"is_enabled": 1},
            {"is_enabled": 0},
            {"is_enabled": None},
            {"is_enabled": True, "extra_field": 123},
        ]

        for payload in invalid_payloads:
            token = self._get_csrf_token()
            res = self.client.patch(url, payload, format="json", HTTP_X_CSRFTOKEN=token)
            self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertEqual(res.data["code"], "VALIDATION_ERROR")

    def test_15_console_policy_patch_successful_change_emits_exactly_one_audit_event(self):
        """A state change emits exactly one CONSOLE_MODULE_POLICY_CHANGED audit event."""
        self._login(self.owner.email)
        token = self._get_csrf_token()
        url = f"/api/v1/organizations/{self.org_alpha.id}/console-policies/tenant_roles/"

        count_before = AuditLog.objects.count()
        res = self.client.patch(url, {"is_enabled": False}, format="json", HTTP_X_CSRFTOKEN=token)
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        self.assertEqual(AuditLog.objects.count(), count_before + 1)
        latest_audit = AuditLog.objects.latest("timestamp")
        self.assertEqual(latest_audit.action, AuditAction.CONSOLE_MODULE_POLICY_CHANGED)
        self.assertEqual(latest_audit.target_type, AuditTargetType.CONSOLE_POLICY)
        self.assertEqual(latest_audit.actor, self.owner)
        self.assertEqual(latest_audit.organization_id, self.org_alpha.id)

    def test_16_console_policy_patch_noop_update_emits_zero_new_audit_events(self):
        """A no-op update emits zero new audit events."""
        self._login(self.owner.email)
        token = self._get_csrf_token()
        url = f"/api/v1/organizations/{self.org_alpha.id}/console-policies/tenant_roles/"

        # First ensure enabled
        self.client.patch(url, {"is_enabled": True}, format="json", HTTP_X_CSRFTOKEN=token)

        # No-op re-send enabled
        token = self._get_csrf_token()
        count_before = AuditLog.objects.count()
        res = self.client.patch(url, {"is_enabled": True}, format="json", HTTP_X_CSRFTOKEN=token)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(AuditLog.objects.count(), count_before)

    def test_17_console_policy_patch_updating_org_a_does_not_alter_org_b(self):
        """Updating module policy in Organization Alpha does not modify Organization Beta."""
        self._login(self.owner.email)
        token = self._get_csrf_token()

        # Disable tenant_roles in org_alpha
        res = self.client.patch(
            f"/api/v1/organizations/{self.org_alpha.id}/console-policies/tenant_roles/",
            {"is_enabled": False},
            format="json",
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        # Check org_beta remains enabled
        res_beta = self.client.get(f"/api/v1/organizations/{self.org_beta.id}/console-policies/")
        beta_roles = next(i for i in res_beta.data if i["module_key"] == "tenant_roles")
        self.assertTrue(beta_roles["is_enabled"])

    # ==========================================
    # 4. Permission-Ceiling GET Tests (18 - 21)
    # ==========================================

    def test_18_permission_ceiling_get_returns_only_tenant_permissions(self):
        """GET permission-ceilings returns only tenant permissions."""
        self._login(self.owner.email)
        res = self.client.get(f"/api/v1/organizations/{self.org_alpha.id}/permission-ceilings/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        keys = [item["permission_key"] for item in res.data]
        expected_keys = [
            "access_requests.view",
            "assignments.view",
            "billing.view",
            "branding.view",
            "bulk_import.view",
            "notifications.view",
            "products.view",
            "reports.view",
            "roles.view",
            "usage.view",
            "access_requests.manage",
            "assignments.manage",
            "billing.manage",
            "branding.manage",
            "bulk_import.manage",
            "roles.manage",
            "usage.manage",
            "access_requests.decide",
            "roles.assign",
        ]
        self.assertEqual(keys, expected_keys)

        manage = next(i for i in res.data if i["permission_key"] == "roles.manage")
        self.assertEqual(manage["console_module"], "tenant_roles")
        self.assertEqual(manage["category"], "roles")
        self.assertTrue(manage["is_allowed"])

    def test_19_permission_ceiling_get_deterministic_ordering(self):
        """GET permission-ceilings sorts deterministically by sort_order, then key."""
        self._login(self.owner.email)
        res = self.client.get(f"/api/v1/organizations/{self.org_alpha.id}/permission-ceilings/")
        keys = [item["permission_key"] for item in res.data]
        expected_keys = [
            "access_requests.view",
            "assignments.view",
            "billing.view",
            "branding.view",
            "bulk_import.view",
            "notifications.view",
            "products.view",
            "reports.view",
            "roles.view",
            "usage.view",
            "access_requests.manage",
            "assignments.manage",
            "billing.manage",
            "branding.manage",
            "bulk_import.manage",
            "roles.manage",
            "usage.manage",
            "access_requests.decide",
            "roles.assign",
        ]
        self.assertEqual(keys, expected_keys)

    def test_20_permission_ceiling_get_missing_ceiling_represented_as_denied_without_creating_row(self):
        """Missing ceiling row is represented as is_allowed=False; GET never creates rows."""
        org_fresh = Organization.objects.create(
            code="org-fresh-ceil",
            name="Fresh Org Ceilings",
            status=OrganizationStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )
        OrganizationPermissionCeiling.objects.filter(organization=org_fresh).delete()

        self._login(self.owner.email)
        res = self.client.get(f"/api/v1/organizations/{org_fresh.id}/permission-ceilings/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        for item in res.data:
            self.assertFalse(item["is_allowed"])  # Deny-by-default
            self.assertIsNone(item["updated_at"])

        self.assertEqual(
            OrganizationPermissionCeiling.objects.filter(organization=org_fresh).count(),
            0,
        )

    def test_21_permission_ceiling_get_emits_no_audit_event(self):
        """GET permission-ceilings emits zero audit events."""
        self._login(self.owner.email)
        count_before = AuditLog.objects.count()

        res = self.client.get(f"/api/v1/organizations/{self.org_alpha.id}/permission-ceilings/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(AuditLog.objects.count(), count_before)

    # ==========================================
    # 5. Permission-Ceiling PATCH Tests (22 - 30)
    # ==========================================

    def test_22_permission_ceiling_patch_valid_ceiling_change_succeeds(self):
        """Valid ceiling change succeeds and returns updated representation."""
        self._login(self.owner.email)
        token = self._get_csrf_token()
        url = f"/api/v1/organizations/{self.org_alpha.id}/permission-ceilings/roles.manage/"

        res = self.client.patch(url, {"is_allowed": False}, format="json", HTTP_X_CSRFTOKEN=token)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertFalse(res.data["is_allowed"])
        self.assertEqual(res.data["permission_key"], "roles.manage")

    def test_23_permission_ceiling_patch_enabling_manage_assign_while_view_denied_returns_validation_error(self):
        """Enabling roles.manage or roles.assign while roles.view is denied returns 400 VALIDATION_ERROR."""
        self._login(self.owner.email)
        token = self._get_csrf_token()

        # First disable manage and assign so view can be safely disabled
        self.client.patch(
            f"/api/v1/organizations/{self.org_alpha.id}/permission-ceilings/roles.manage/",
            {"is_allowed": False},
            format="json",
            HTTP_X_CSRFTOKEN=token,
        )
        token = self._get_csrf_token()
        self.client.patch(
            f"/api/v1/organizations/{self.org_alpha.id}/permission-ceilings/roles.assign/",
            {"is_allowed": False},
            format="json",
            HTTP_X_CSRFTOKEN=token,
        )
        token = self._get_csrf_token()
        self.client.patch(
            f"/api/v1/organizations/{self.org_alpha.id}/permission-ceilings/roles.view/",
            {"is_allowed": False},
            format="json",
            HTTP_X_CSRFTOKEN=token,
        )

        # Now attempting to allow roles.manage must fail
        token = self._get_csrf_token()
        res = self.client.patch(
            f"/api/v1/organizations/{self.org_alpha.id}/permission-ceilings/roles.manage/",
            {"is_allowed": True},
            format="json",
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(res.data["code"], "VALIDATION_ERROR")

        # Attempting to allow roles.assign must also fail
        token = self._get_csrf_token()
        res_assign = self.client.patch(
            f"/api/v1/organizations/{self.org_alpha.id}/permission-ceilings/roles.assign/",
            {"is_allowed": True},
            format="json",
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(res_assign.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(res_assign.data["code"], "VALIDATION_ERROR")

    def test_24_permission_ceiling_patch_disabling_view_while_manage_assign_allowed_returns_validation_error(self):
        """Disabling roles.view while roles.manage or roles.assign is allowed returns 400 VALIDATION_ERROR."""
        self._login(self.owner.email)
        token = self._get_csrf_token()

        res = self.client.patch(
            f"/api/v1/organizations/{self.org_alpha.id}/permission-ceilings/roles.view/",
            {"is_allowed": False},
            format="json",
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(res.data["code"], "VALIDATION_ERROR")

    def test_25_permission_ceiling_patch_unknown_permission_returns_permission_not_found(self):
        """Unknown permission key returns 400 PERMISSION_NOT_FOUND."""
        self._login(self.owner.email)
        token = self._get_csrf_token()

        res = self.client.patch(
            f"/api/v1/organizations/{self.org_alpha.id}/permission-ceilings/unknown.permission/",
            {"is_allowed": True},
            format="json",
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(res.data["code"], "PERMISSION_NOT_FOUND")

    def test_26_permission_ceiling_patch_strict_boolean_validation_rejects_invalid_input(self):
        """Rejects missing, string, integer, null, or unrelated fields with 400 VALIDATION_ERROR."""
        self._login(self.owner.email)
        url = f"/api/v1/organizations/{self.org_alpha.id}/permission-ceilings/roles.manage/"

        invalid_payloads = [
            {},
            {"is_allowed": "true"},
            {"is_allowed": "false"},
            {"is_allowed": 1},
            {"is_allowed": 0},
            {"is_allowed": None},
            {"is_allowed": False, "extra_payload": 999},
        ]

        for payload in invalid_payloads:
            token = self._get_csrf_token()
            res = self.client.patch(url, payload, format="json", HTTP_X_CSRFTOKEN=token)
            self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertEqual(res.data["code"], "VALIDATION_ERROR")

    def test_27_permission_ceiling_patch_successful_change_emits_exactly_one_audit_event(self):
        """A state change emits exactly one PERMISSION_CEILING_CHANGED audit event."""
        self._login(self.owner.email)
        token = self._get_csrf_token()
        url = f"/api/v1/organizations/{self.org_alpha.id}/permission-ceilings/roles.manage/"

        count_before = AuditLog.objects.count()
        res = self.client.patch(url, {"is_allowed": False}, format="json", HTTP_X_CSRFTOKEN=token)
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        self.assertEqual(AuditLog.objects.count(), count_before + 1)
        latest_audit = AuditLog.objects.latest("timestamp")
        self.assertEqual(latest_audit.action, AuditAction.PERMISSION_CEILING_CHANGED)
        self.assertEqual(latest_audit.target_type, AuditTargetType.PERMISSION_CEILING)
        self.assertEqual(latest_audit.actor, self.owner)
        self.assertEqual(latest_audit.organization_id, self.org_alpha.id)

    def test_28_permission_ceiling_patch_noop_update_emits_zero_new_audit_events(self):
        """A no-op update emits zero new audit events."""
        self._login(self.owner.email)
        token = self._get_csrf_token()
        url = f"/api/v1/organizations/{self.org_alpha.id}/permission-ceilings/roles.manage/"

        # Ensure allowed
        self.client.patch(url, {"is_allowed": True}, format="json", HTTP_X_CSRFTOKEN=token)

        # Re-send identical state
        token = self._get_csrf_token()
        count_before = AuditLog.objects.count()
        res = self.client.patch(url, {"is_allowed": True}, format="json", HTTP_X_CSRFTOKEN=token)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(AuditLog.objects.count(), count_before)

    def test_29_permission_ceiling_patch_updating_org_a_does_not_alter_org_b(self):
        """Updating permission ceiling in Organization Alpha does not modify Organization Beta."""
        self._login(self.owner.email)
        token = self._get_csrf_token()

        res = self.client.patch(
            f"/api/v1/organizations/{self.org_alpha.id}/permission-ceilings/roles.manage/",
            {"is_allowed": False},
            format="json",
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        # Check org_beta ceiling remains allowed
        res_beta = self.client.get(f"/api/v1/organizations/{self.org_beta.id}/permission-ceilings/")
        beta_manage = next(i for i in res_beta.data if i["permission_key"] == "roles.manage")
        self.assertTrue(beta_manage["is_allowed"])

    def test_30_ceiling_change_reflected_by_stage3_evaluation_engine_on_new_request(self):
        """A successful ceiling change is immediately visible to Stage 3 centralized evaluation on a new request."""
        # 1. Baseline: Tenant admin in org_alpha has roles.manage granted via system role and ceiling
        eval_before = evaluate_access(self.admin_user, CONTEXT_TENANT, self.org_alpha.id)
        self.assertIn("roles.manage", eval_before.effective_permissions)

        # 2. Platform Owner disables roles.manage ceiling via PATCH
        self._login(self.owner.email)
        token = self._get_csrf_token()
        url = f"/api/v1/organizations/{self.org_alpha.id}/permission-ceilings/roles.manage/"

        res = self.client.patch(url, {"is_allowed": False}, format="json", HTTP_X_CSRFTOKEN=token)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertFalse(res.data["is_allowed"])

        # 3. New evaluation: roles.manage is now denied by the updated ceiling
        eval_after = evaluate_access(self.admin_user, CONTEXT_TENANT, self.org_alpha.id)
        self.assertNotIn("roles.manage", eval_after.effective_permissions)
        self.assertIn("roles.view", eval_after.effective_permissions)
        self.assertIn("roles.assign", eval_after.effective_permissions)

    def test_organization_not_found_returns_404(self):
        """Unknown organization UUID returns 404 with ORGANIZATION_NOT_FOUND."""
        self._login(self.owner.email)
        non_existent_org_id = uuid.uuid4()

        res_get_ceil = self.client.get(f"/api/v1/organizations/{non_existent_org_id}/permission-ceilings/")
        self.assertEqual(res_get_ceil.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(res_get_ceil.data["code"], "ORGANIZATION_NOT_FOUND")


class Stage5TenantAdminApiTests(APITestCase):
    """Test suite covering the 6 Stage 5 Tenant Admin API endpoints (53 test cases)."""

    def setUp(self):
        super().setUp()
        cache.clear()
        self.password = "SecureTenantPass123!"

        # 1. Platform Owner
        self.owner = PlatformUser.objects.create_user(
            email="po_owner@vibeconnect.internal",
            password=self.password,
            full_name="Platform Owner",
            status="active",
            is_active=True,
            is_platform_owner=True,
        )

        # 2. Organizations
        self.org_alpha = Organization.objects.create(
            code="tenant-org-alpha",
            name="Tenant Org Alpha",
            status=OrganizationStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )
        self.org_beta = Organization.objects.create(
            code="tenant-org-beta",
            name="Tenant Org Beta",
            status=OrganizationStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )

        # 3. System Role & Tenant Permissions
        self.system_role = Role.objects.get(code="system_tenant_admin", is_system_role=True)
        self.perm_view = AccessPermission.objects.get(key="roles.view")
        self.perm_manage = AccessPermission.objects.get(key="roles.manage")
        self.perm_assign = AccessPermission.objects.get(key="roles.assign")

        # 4. Seed policies & ceilings for Org Alpha and Beta
        tenant_mods = ConsoleModule.objects.filter(target_context="tenant", is_active=True)
        tenant_perms = AccessPermission.objects.filter(console_module__target_context="tenant", is_active=True)

        for org in [self.org_alpha, self.org_beta]:
            for mod in tenant_mods:
                OrganizationConsoleModulePolicy.objects.get_or_create(
                    organization=org,
                    console_module=mod,
                    defaults={"is_enabled": True, "updated_by": self.owner},
                )
            for p in tenant_perms:
                OrganizationPermissionCeiling.objects.get_or_create(
                    organization=org,
                    permission=p,
                    defaults={"is_allowed": True, "updated_by": self.owner},
                )

        # 5. Users in Org Alpha
        self.admin_alpha_1 = PlatformUser.objects.create_user(
            email="admin_a1@vibeconnect.internal",
            password=self.password,
            full_name="Alpha Admin One",
            status="active",
            is_active=True,
            is_platform_owner=False,
        )
        self.admin_alpha_2 = PlatformUser.objects.create_user(
            email="admin_a2@vibeconnect.internal",
            password=self.password,
            full_name="Alpha Admin Two",
            status="active",
            is_active=True,
            is_platform_owner=False,
        )
        self.member_alpha = PlatformUser.objects.create_user(
            email="member_a@vibeconnect.internal",
            password=self.password,
            full_name="Alpha Member",
            status="active",
            is_active=True,
            is_platform_owner=False,
        )
        self.admin_suspended = PlatformUser.objects.create_user(
            email="admin_susp@vibeconnect.internal",
            password=self.password,
            full_name="Suspended Admin",
            status="active",
            is_active=True,
            is_platform_owner=False,
        )
        self.admin_ended = PlatformUser.objects.create_user(
            email="admin_ended@vibeconnect.internal",
            password=self.password,
            full_name="Ended Admin",
            status="active",
            is_active=True,
            is_platform_owner=False,
        )

        # 6. Users in Org Beta
        self.admin_beta = PlatformUser.objects.create_user(
            email="admin_b@vibeconnect.internal",
            password=self.password,
            full_name="Beta Admin",
            status="active",
            is_active=True,
            is_platform_owner=False,
        )

        # 7. Memberships in Org Alpha
        self.mem_admin1 = OrganizationMembership.objects.create(
            organization=self.org_alpha,
            user=self.admin_alpha_1,
            membership_type=MembershipType.TENANT_ADMIN,
            status=MembershipStatus.ACTIVE,
            role=self.system_role,
            joined_at=timezone.now(),
        )
        self.mem_admin2 = OrganizationMembership.objects.create(
            organization=self.org_alpha,
            user=self.admin_alpha_2,
            membership_type=MembershipType.TENANT_ADMIN,
            status=MembershipStatus.ACTIVE,
            role=self.system_role,
            joined_at=timezone.now(),
        )
        self.mem_regular = OrganizationMembership.objects.create(
            organization=self.org_alpha,
            user=self.member_alpha,
            membership_type=MembershipType.MEMBER,
            status=MembershipStatus.ACTIVE,
            role=None,
            joined_at=timezone.now(),
        )
        self.mem_suspended = OrganizationMembership.objects.create(
            organization=self.org_alpha,
            user=self.admin_suspended,
            membership_type=MembershipType.TENANT_ADMIN,
            status=MembershipStatus.SUSPENDED,
            role=self.system_role,
            joined_at=timezone.now(),
        )
        self.mem_ended = OrganizationMembership.objects.create(
            organization=self.org_alpha,
            user=self.admin_ended,
            membership_type=MembershipType.TENANT_ADMIN,
            status=MembershipStatus.ENDED,
            role=self.system_role,
            joined_at=timezone.now(),
            ended_at=timezone.now(),
        )

        # 8. Memberships in Org Beta
        self.mem_beta = OrganizationMembership.objects.create(
            organization=self.org_beta,
            user=self.admin_beta,
            membership_type=MembershipType.TENANT_ADMIN,
            status=MembershipStatus.ACTIVE,
            role=self.system_role,
            joined_at=timezone.now(),
        )

        # 9. Custom roles
        self.custom_role_alpha = Role.objects.create(
            organization=self.org_alpha,
            code="custom_role_alpha",
            name="Custom Role Alpha",
            description="Alpha custom role.",
            is_system_role=False,
            status=RoleStatus.ACTIVE,
            created_by=self.admin_alpha_1,
            updated_by=self.admin_alpha_1,
        )
        RolePermission.objects.create(role=self.custom_role_alpha, permission=self.perm_view)
        RolePermission.objects.create(role=self.custom_role_alpha, permission=self.perm_manage)

        self.role_beta = Role.objects.create(
            organization=self.org_beta,
            code="role_beta",
            name="Role Beta",
            description="Beta role.",
            is_system_role=False,
            status=RoleStatus.ACTIVE,
            created_by=self.admin_beta,
            updated_by=self.admin_beta,
        )
        RolePermission.objects.create(role=self.role_beta, permission=self.perm_view)

    def tearDown(self):
        cache.clear()
        super().tearDown()

    def _login_tenant(self, user, org):
        """Establish session in tenant context for given user and org."""
        self.client.force_login(user)
        session = self.client.session
        session["active_context_type"] = "tenant"
        session["tenant_organization_id"] = str(org.id)
        session.save()

    def _login_owner(self):
        """Establish session in platform_owner context."""
        self.client.force_login(self.owner)
        session = self.client.session
        session["active_context_type"] = "platform_owner"
        session["tenant_organization_id"] = None
        session.save()

    # ==========================================
    # 1. Tenant Access Boundary (Tests 1 - 7)
    # ==========================================

    def test_t01_unauthenticated_request_returns_401(self):
        """Unauthenticated requests to tenant endpoints return 401."""
        res = self.client.get("/api/v1/tenant/access-catalog/")
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

        res_roles = self.client.get("/api/v1/tenant/roles/")
        self.assertEqual(res_roles.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_t02_regular_member_denied(self):
        """Regular member receives 403 NO_CONSOLE_ACCESS on tenant endpoints."""
        self._login_tenant(self.member_alpha, self.org_alpha)
        res = self.client.get("/api/v1/tenant/access-catalog/")
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(res.data["code"], "NO_CONSOLE_ACCESS")

    def test_t03_suspended_membership_denied(self):
        """Tenant Admin with suspended membership receives 403 MEMBERSHIP_NOT_ACTIVE."""
        self._login_tenant(self.admin_suspended, self.org_alpha)
        res = self.client.get("/api/v1/tenant/access-catalog/")
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(res.data["code"], "MEMBERSHIP_NOT_ACTIVE")

    def test_t04_tenant_admin_wrong_tenant_context_cannot_access_other_org(self):
        """Tenant Admin in Org Alpha context cannot access Org Beta custom role (returns 404)."""
        self._login_tenant(self.admin_alpha_1, self.org_alpha)
        res = self.client.get(f"/api/v1/tenant/roles/{self.role_beta.id}/")
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(res.data["code"], "ROLE_NOT_FOUND")

    def test_t05_platform_owner_context_does_not_bypass_tenant_api(self):
        """Platform Owner context without tenant selection receives 403 TENANT_CONTEXT_REQUIRED."""
        self._login_owner()
        res = self.client.get("/api/v1/tenant/roles/")
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(res.data["code"], "TENANT_CONTEXT_REQUIRED")

    def test_t06_disabled_tenant_roles_module_returns_module_disabled(self):
        """When tenant_roles module is disabled for an org, tenant receives 403 MODULE_DISABLED."""
        policy = OrganizationConsoleModulePolicy.objects.get(
            organization=self.org_alpha,
            console_module_id="tenant_roles",
        )
        policy.is_enabled = False
        policy.save(update_fields=["is_enabled"])

        self._login_tenant(self.admin_alpha_1, self.org_alpha)
        res = self.client.get("/api/v1/tenant/roles/")
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(res.data["code"], "MODULE_DISABLED")

    def test_t07_missing_required_permission_returns_insufficient_privileges(self):
        """Tenant Admin lacking roles.manage receives 403 INSUFFICIENT_PRIVILEGES on mutating endpoints."""
        view_only_role = Role.objects.create(
            organization=self.org_alpha,
            code="view_only_tester",
            name="View Only Tester",
            is_system_role=False,
            status=RoleStatus.ACTIVE,
            created_by=self.admin_alpha_1,
            updated_by=self.admin_alpha_1,
        )
        RolePermission.objects.create(role=view_only_role, permission=self.perm_view)
        self.mem_admin1.role = view_only_role
        self.mem_admin1.save(update_fields=["role"])

        self._login_tenant(self.admin_alpha_1, self.org_alpha)
        res = self.client.post(
            "/api/v1/tenant/roles/",
            {
                "code": "new_unauth_role",
                "name": "New Unauth Role",
                "permission_keys": ["roles.view"],
            },
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(res.data["code"], "INSUFFICIENT_PRIVILEGES")

    # ==========================================
    # 2. Access Catalog (Tests 8 - 12)
    # ==========================================

    def test_t08_access_catalog_returns_only_actor_grantable_active_permissions(self):
        """Access catalog returns only permissions granted to the actor and allowed by ceiling/policy."""
        restricted_role = Role.objects.create(
            organization=self.org_alpha,
            code="restricted_catalog_tester",
            name="Restricted Catalog Tester",
            is_system_role=False,
            status=RoleStatus.ACTIVE,
            created_by=self.admin_alpha_1,
            updated_by=self.admin_alpha_1,
        )
        RolePermission.objects.create(role=restricted_role, permission=self.perm_view)
        RolePermission.objects.create(role=restricted_role, permission=self.perm_manage)
        self.mem_admin1.role = restricted_role
        self.mem_admin1.save(update_fields=["role"])

        self._login_tenant(self.admin_alpha_1, self.org_alpha)
        res = self.client.get("/api/v1/tenant/access-catalog/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        perm_keys = [p["key"] for p in res.data["permissions"]]
        self.assertEqual(set(perm_keys), {"roles.view", "roles.manage"})
        self.assertNotIn("roles.assign", perm_keys)

    def test_t09_access_catalog_excludes_ceiling_denied_permissions(self):
        """Ceiling-denied permissions are excluded from access catalog even if actor role possesses them."""
        ceiling = OrganizationPermissionCeiling.objects.get(
            organization=self.org_alpha,
            permission=self.perm_assign,
        )
        ceiling.is_allowed = False
        ceiling.save(update_fields=["is_allowed"])

        self._login_tenant(self.admin_alpha_1, self.org_alpha)
        res = self.client.get("/api/v1/tenant/access-catalog/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        perm_keys = [p["key"] for p in res.data["permissions"]]
        self.assertNotIn("roles.assign", perm_keys)

    def test_t10_access_catalog_excludes_module_disabled_permissions(self):
        """Permissions belonging to a disabled module are excluded from access catalog."""
        policy = OrganizationConsoleModulePolicy.objects.get(
            organization=self.org_alpha,
            console_module_id="tenant_roles",
        )
        policy.is_enabled = False
        policy.save(update_fields=["is_enabled"])

        self._login_tenant(self.admin_alpha_1, self.org_alpha)
        res = self.client.get("/api/v1/tenant/access-catalog/")
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(res.data["code"], "MODULE_DISABLED")

    def test_t11_access_catalog_uses_deterministic_ordering(self):
        """Access catalog permissions and modules sort deterministically by sort_order, key."""
        self._login_tenant(self.admin_alpha_1, self.org_alpha)
        res = self.client.get("/api/v1/tenant/access-catalog/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        perm_keys = [p["key"] for p in res.data["permissions"]]
        expected_keys = [
            "access_requests.view",
            "assignments.view",
            "billing.view",
            "branding.view",
            "bulk_import.view",
            "notifications.view",
            "products.view",
            "reports.view",
            "roles.view",
            "usage.view",
            "access_requests.manage",
            "assignments.manage",
            "billing.manage",
            "branding.manage",
            "bulk_import.manage",
            "roles.manage",
            "usage.manage",
            "access_requests.decide",
            "roles.assign",
        ]
        self.assertEqual(perm_keys, expected_keys)

    def test_t12_access_catalog_get_emits_no_audit_event(self):
        """GET access catalog emits zero audit events."""
        self._login_tenant(self.admin_alpha_1, self.org_alpha)
        count_before = AuditLog.objects.count()

        res = self.client.get("/api/v1/tenant/access-catalog/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(AuditLog.objects.count(), count_before)

    # ==========================================
    # 3. Role List & Detail (Tests 13 - 17)
    # ==========================================

    def test_t13_role_list_returns_system_role_plus_current_org_custom_roles(self):
        """Role list returns global system_tenant_admin first, followed by org custom roles."""
        self._login_tenant(self.admin_alpha_1, self.org_alpha)
        res = self.client.get("/api/v1/tenant/roles/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        results = res.data["results"]
        codes = [r["code"] for r in results]
        self.assertEqual(codes[0], "system_tenant_admin")
        self.assertIn("custom_role_alpha", codes)
        self.assertNotIn("support_operator", codes)
        self.assertNotIn("support_diagnostics_viewer", codes)
        self.assertNotIn("support_remediation_operator", codes)

    def test_t14_role_list_excludes_another_org_custom_roles(self):
        """Role list never exposes custom roles belonging to another organization."""
        self._login_tenant(self.admin_alpha_1, self.org_alpha)
        res = self.client.get("/api/v1/tenant/roles/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        codes = [r["code"] for r in res.data["results"]]
        self.assertNotIn("role_beta", codes)

    def test_t15_role_list_uses_pagination(self):
        """Role list response contains count, next, previous, results."""
        self._login_tenant(self.admin_alpha_1, self.org_alpha)
        res = self.client.get("/api/v1/tenant/roles/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        for expected_key in ("count", "next", "previous", "results"):
            self.assertIn(expected_key, res.data)

    def test_t16_role_detail_returns_expected_data(self):
        """Role detail returns full representation including permissions and assigned_members_count."""
        self._login_tenant(self.admin_alpha_1, self.org_alpha)
        res = self.client.get(f"/api/v1/tenant/roles/{self.custom_role_alpha.id}/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        self.assertEqual(res.data["code"], "custom_role_alpha")
        self.assertEqual(res.data["name"], "Custom Role Alpha")
        self.assertFalse(res.data["is_system_role"])
        self.assertEqual(res.data["status"], "active")
        self.assertEqual(set(res.data["permission_keys"]), {"roles.view", "roles.manage"})
        self.assertEqual(len(res.data["permissions"]), 2)
        self.assertEqual(res.data["assigned_members_count"], 0)

    def test_t17_unknown_or_cross_tenant_role_returns_role_not_found(self):
        """Unknown or cross-tenant role ID returns 404 with ROLE_NOT_FOUND."""
        self._login_tenant(self.admin_alpha_1, self.org_alpha)

        # Cross-tenant
        res_cross = self.client.get(f"/api/v1/tenant/roles/{self.role_beta.id}/")
        self.assertEqual(res_cross.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(res_cross.data["code"], "ROLE_NOT_FOUND")

        # Non-existent UUID
        res_none = self.client.get(f"/api/v1/tenant/roles/{uuid.uuid4()}/")
        self.assertEqual(res_none.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(res_none.data["code"], "ROLE_NOT_FOUND")

    # ==========================================
    # 4. Role Creation (Tests 18 - 23)
    # ==========================================

    def test_t18_valid_role_creation_succeeds(self):
        """Valid role creation succeeds with 201 and returns complete representation."""
        self._login_tenant(self.admin_alpha_1, self.org_alpha)
        payload = {
            "name": "Audit Manager",
            "code": "audit_manager",
            "description": "Role management without assignment rights.",
            "permission_keys": ["roles.view", "roles.manage"],
        }
        res = self.client.post("/api/v1/tenant/roles/", payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)

        self.assertEqual(res.data["code"], "audit_manager")
        self.assertEqual(res.data["name"], "Audit Manager")
        self.assertFalse(res.data["is_system_role"])
        self.assertEqual(set(res.data["permission_keys"]), {"roles.view", "roles.manage"})

    def test_t19_exact_equality_permission_set_allowed(self):
        """Creating a role whose permissions match the actor's effective set exactly is allowed."""
        self._login_tenant(self.admin_alpha_1, self.org_alpha)
        payload = {
            "name": "Full Equal Role",
            "code": "full_equal_role",
            "permission_keys": ["roles.view", "roles.manage", "roles.assign"],
        }
        res = self.client.post("/api/v1/tenant/roles/", payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(len(res.data["permission_keys"]), 3)

    def test_t20_unauthorized_permission_addition_denied(self):
        """Attempting to grant a permission outside the actor's effective set returns 403."""
        # Restrict admin 1 to roles.view and roles.manage
        self.mem_admin1.role = self.custom_role_alpha
        self.mem_admin1.save(update_fields=["role"])

        self._login_tenant(self.admin_alpha_1, self.org_alpha)
        payload = {
            "name": "Escalated Role",
            "code": "escalated_role",
            "permission_keys": ["roles.view", "roles.manage", "roles.assign"],
        }
        res = self.client.post("/api/v1/tenant/roles/", payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(res.data["code"], "INSUFFICIENT_PRIVILEGES")

    def test_t21_invalid_dependency_set_rejected(self):
        """Requesting roles.manage without roles.view returns 400 VALIDATION_ERROR."""
        self._login_tenant(self.admin_alpha_1, self.org_alpha)
        payload = {
            "name": "Invalid Deps Role",
            "code": "invalid_deps_role",
            "permission_keys": ["roles.manage"],
        }
        res = self.client.post("/api/v1/tenant/roles/", payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(res.data["code"], "VALIDATION_ERROR")

    def test_t22_duplicate_role_code_returns_role_already_exists(self):
        """Duplicate role code within the organization returns 409 ROLE_ALREADY_EXISTS."""
        self._login_tenant(self.admin_alpha_1, self.org_alpha)
        payload = {
            "name": "Duplicate Code",
            "code": "custom_role_alpha",
            "permission_keys": ["roles.view"],
        }
        res = self.client.post("/api/v1/tenant/roles/", payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(res.data["code"], "ROLE_ALREADY_EXISTS")

    def test_t23_role_creation_audit_behavior(self):
        """Successful role creation produces exactly one ROLE_CREATED audit event."""
        self._login_tenant(self.admin_alpha_1, self.org_alpha)
        count_before = AuditLog.objects.count()

        payload = {
            "name": "Audited Role",
            "code": "audited_role",
            "permission_keys": ["roles.view"],
        }
        res = self.client.post("/api/v1/tenant/roles/", payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)

        self.assertEqual(AuditLog.objects.count(), count_before + 1)
        latest = AuditLog.objects.latest("timestamp")
        self.assertEqual(latest.action, AuditAction.ROLE_CREATED)
        self.assertEqual(latest.actor, self.admin_alpha_1)
        self.assertEqual(latest.organization_id, self.org_alpha.id)

    # ==========================================
    # 5. Role Update (Tests 24 - 31)
    # ==========================================

    def test_t24_role_update_metadata_only_succeeds(self):
        """Updating role name/description succeeds and leaves permissions unchanged."""
        self._login_tenant(self.admin_alpha_1, self.org_alpha)
        url = f"/api/v1/tenant/roles/{self.custom_role_alpha.id}/"
        payload = {"name": "New Alpha Name", "description": "New description."}

        res = self.client.patch(url, payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["name"], "New Alpha Name")
        self.assertEqual(res.data["description"], "New description.")
        self.assertEqual(set(res.data["permission_keys"]), {"roles.view", "roles.manage"})

    def test_t25_safe_permission_removal_succeeds(self):
        """Safe permission removal succeeds."""
        self._login_tenant(self.admin_alpha_1, self.org_alpha)
        url = f"/api/v1/tenant/roles/{self.custom_role_alpha.id}/"
        payload = {"permission_keys": ["roles.view"]}

        res = self.client.patch(url, payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["permission_keys"], ["roles.view"])

    def test_t26_unauthorized_newly_added_permission_rejected(self):
        """Actor attempting to add an unauthorized permission to an existing role receives 403."""
        # Restrict admin 1 to roles.view and roles.manage
        self.mem_admin1.role = self.custom_role_alpha
        self.mem_admin1.save(update_fields=["role"])

        self._login_tenant(self.admin_alpha_1, self.org_alpha)
        url = f"/api/v1/tenant/roles/{self.custom_role_alpha.id}/"
        payload = {"permission_keys": ["roles.view", "roles.manage", "roles.assign"]}

        res = self.client.patch(url, payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(res.data["code"], "INSUFFICIENT_PRIVILEGES")

    def test_t27_role_code_mutation_rejected(self):
        """Attempting to mutate role code returns 400 VALIDATION_ERROR."""
        self._login_tenant(self.admin_alpha_1, self.org_alpha)
        url = f"/api/v1/tenant/roles/{self.custom_role_alpha.id}/"
        payload = {"code": "new_code_attempt"}

        res = self.client.patch(url, payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(res.data["code"], "VALIDATION_ERROR")

    def test_t28_system_role_update_rejected(self):
        """Attempting to update the system role returns 400 SYSTEM_ROLE_IMMUTABLE."""
        self._login_tenant(self.admin_alpha_1, self.org_alpha)
        url = f"/api/v1/tenant/roles/{self.system_role.id}/"
        payload = {"name": "Mutated System Role"}

        res = self.client.patch(url, payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(res.data["code"], "SYSTEM_ROLE_IMMUTABLE")

    def test_t29_retired_role_update_rejected(self):
        """Attempting to update a retired role returns 400 ROLE_RETIRED."""
        self.custom_role_alpha.status = RoleStatus.RETIRED
        self.custom_role_alpha.save(update_fields=["status"])

        self._login_tenant(self.admin_alpha_1, self.org_alpha)
        url = f"/api/v1/tenant/roles/{self.custom_role_alpha.id}/"
        payload = {"name": "New Name on Retired"}

        res = self.client.patch(url, payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(res.data["code"], "ROLE_RETIRED")

    def test_t30_role_update_noop_emits_zero_audit_events(self):
        """A no-op update emits zero new audit events."""
        self._login_tenant(self.admin_alpha_1, self.org_alpha)
        url = f"/api/v1/tenant/roles/{self.custom_role_alpha.id}/"
        payload = {
            "name": self.custom_role_alpha.name,
            "description": self.custom_role_alpha.description,
            "permission_keys": ["roles.view", "roles.manage"],
        }

        count_before = AuditLog.objects.count()
        res = self.client.patch(url, payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(AuditLog.objects.count(), count_before)

    def test_t31_removing_final_capable_admin_permissions_returns_last_admin_protection(self):
        """Removing manage/assign from the role of the only capable admin returns 400 LAST_ADMIN_PROTECTION."""
        # Admin 1 holds custom_role_alpha (has roles.manage and roles.view, but not roles.assign).
        # Admin 2 holds view_only_role (no manage, no assign).
        view_only = Role.objects.create(
            organization=self.org_alpha,
            code="view_only_adm2",
            name="View Only",
            is_system_role=False,
            status=RoleStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )
        RolePermission.objects.create(role=view_only, permission=self.perm_view)
        self.mem_admin2.role = view_only
        self.mem_admin2.save(update_fields=["role"])

        self.mem_admin1.role = self.custom_role_alpha
        self.mem_admin1.save(update_fields=["role"])

        # Admin 1 is the ONLY capable admin. Removing roles.manage from custom_role_alpha will eliminate all manage capability.
        self._login_tenant(self.admin_alpha_1, self.org_alpha)
        url = f"/api/v1/tenant/roles/{self.custom_role_alpha.id}/"
        res = self.client.patch(url, {"permission_keys": ["roles.view"]}, format="json")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(res.data["code"], "LAST_ADMIN_PROTECTION")

    # ==========================================
    # 6. Role Retirement (Tests 32 - 36)
    # ==========================================

    def test_t32_unused_custom_role_retires_successfully(self):
        """An unused custom role retires successfully and transitions to status retired."""
        unused_role = Role.objects.create(
            organization=self.org_alpha,
            code="unused_role",
            name="Unused Role",
            is_system_role=False,
            status=RoleStatus.ACTIVE,
            created_by=self.admin_alpha_1,
            updated_by=self.admin_alpha_1,
        )
        self._login_tenant(self.admin_alpha_1, self.org_alpha)
        url = f"/api/v1/tenant/roles/{unused_role.id}/retire/"

        count_before = AuditLog.objects.count()
        res = self.client.post(url, format="json")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["status"], "retired")

        self.assertEqual(AuditLog.objects.count(), count_before + 1)
        latest = AuditLog.objects.latest("timestamp")
        self.assertEqual(latest.action, AuditAction.ROLE_RETIRED)

    def test_t33_system_role_retirement_rejected(self):
        """Attempting to retire the system role returns 400 SYSTEM_ROLE_IMMUTABLE."""
        self._login_tenant(self.admin_alpha_1, self.org_alpha)
        url = f"/api/v1/tenant/roles/{self.system_role.id}/retire/"

        res = self.client.post(url, format="json")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(res.data["code"], "SYSTEM_ROLE_IMMUTABLE")

    def test_t34_referenced_role_retirement_rejected_for_active_membership(self):
        """Retiring a role referenced by an active membership returns 400 ROLE_IN_USE."""
        self.mem_admin2.role = self.custom_role_alpha
        self.mem_admin2.save(update_fields=["role"])

        self._login_tenant(self.admin_alpha_1, self.org_alpha)
        url = f"/api/v1/tenant/roles/{self.custom_role_alpha.id}/retire/"

        res = self.client.post(url, format="json")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(res.data["code"], "ROLE_IN_USE")

    def test_t35_referenced_role_retirement_rejected_for_suspended_membership(self):
        """Retiring a role referenced by a suspended membership returns 400 ROLE_IN_USE."""
        self.mem_suspended.role = self.custom_role_alpha
        self.mem_suspended.save(update_fields=["role"])

        self._login_tenant(self.admin_alpha_1, self.org_alpha)
        url = f"/api/v1/tenant/roles/{self.custom_role_alpha.id}/retire/"

        res = self.client.post(url, format="json")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(res.data["code"], "ROLE_IN_USE")

    def test_t36_referenced_role_retirement_rejected_for_ended_membership(self):
        """Retiring a role referenced by an ended membership returns 400 ROLE_IN_USE."""
        self.mem_ended.role = self.custom_role_alpha
        self.mem_ended.save(update_fields=["role"])

        self._login_tenant(self.admin_alpha_1, self.org_alpha)
        url = f"/api/v1/tenant/roles/{self.custom_role_alpha.id}/retire/"

        res = self.client.post(url, format="json")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(res.data["code"], "ROLE_IN_USE")

    # ==========================================
    # 7. Administrative Memberships (Tests 37 - 41)
    # ==========================================

    def test_t37_admin_memberships_returns_only_tenant_admins_for_selected_org(self):
        """Returns only tenant_admin memberships for current org, excluding regular members and other orgs."""
        self._login_tenant(self.admin_alpha_1, self.org_alpha)
        res = self.client.get("/api/v1/tenant/admin-memberships/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        user_emails = [m["user"]["email"] for m in res.data["results"]]
        self.assertIn(self.admin_alpha_1.email, user_emails)
        self.assertIn(self.admin_alpha_2.email, user_emails)
        self.assertNotIn(self.member_alpha.email, user_emails)
        self.assertNotIn(self.admin_beta.email, user_emails)

    def test_t38_admin_memberships_includes_active_suspended_ended(self):
        """Default listing includes active, suspended, and ended tenant admin memberships."""
        self._login_tenant(self.admin_alpha_1, self.org_alpha)
        res = self.client.get("/api/v1/tenant/admin-memberships/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        statuses = {m["status"] for m in res.data["results"]}
        self.assertIn("active", statuses)
        self.assertIn("suspended", statuses)
        self.assertIn("ended", statuses)

    def test_t39_admin_memberships_status_filter(self):
        """Filtering by status correctly narrows the returned results."""
        self._login_tenant(self.admin_alpha_1, self.org_alpha)

        res_active = self.client.get("/api/v1/tenant/admin-memberships/?status=active")
        self.assertEqual(res_active.status_code, status.HTTP_200_OK)
        for m in res_active.data["results"]:
            self.assertEqual(m["status"], "active")

        res_susp = self.client.get("/api/v1/tenant/admin-memberships/?status=suspended")
        self.assertEqual(res_susp.status_code, status.HTTP_200_OK)
        for m in res_susp.data["results"]:
            self.assertEqual(m["status"], "suspended")

    def test_t40_admin_memberships_invalid_status_filter_rejected(self):
        """Invalid status filter returns 400 VALIDATION_ERROR."""
        self._login_tenant(self.admin_alpha_1, self.org_alpha)
        res = self.client.get("/api/v1/tenant/admin-memberships/?status=invalid_status")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(res.data["code"], "VALIDATION_ERROR")

    def test_t41_admin_memberships_uses_real_full_name_and_assigned_role(self):
        """Exposes user.full_name and non-null role representation."""
        self._login_tenant(self.admin_alpha_1, self.org_alpha)
        res = self.client.get("/api/v1/tenant/admin-memberships/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        first_mem = res.data["results"][0]
        self.assertIn("full_name", first_mem["user"])
        self.assertIsNotNone(first_mem["role"])
        self.assertIn("code", first_mem["role"])

    # ==========================================
    # 8. Role Assignment (Tests 42 - 53)
    # ==========================================

    def test_t42_valid_role_assignment_succeeds(self):
        """Valid same-org role assignment updates membership.role."""
        self._login_tenant(self.admin_alpha_1, self.org_alpha)
        url = f"/api/v1/tenant/admin-memberships/{self.mem_admin2.id}/role/"
        payload = {"role_id": str(self.custom_role_alpha.id)}

        res = self.client.patch(url, payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["role"]["id"], str(self.custom_role_alpha.id))

    def test_t43_null_role_resets_to_system_tenant_admin(self):
        """Passing role_id=None resets membership role to system_tenant_admin."""
        # First assign custom role
        self.mem_admin2.role = self.custom_role_alpha
        self.mem_admin2.save(update_fields=["role"])

        self._login_tenant(self.admin_alpha_1, self.org_alpha)
        url = f"/api/v1/tenant/admin-memberships/{self.mem_admin2.id}/role/"
        payload = {"role_id": None}

        res = self.client.patch(url, payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["role"]["code"], "system_tenant_admin")

        self.mem_admin2.refresh_from_db()
        self.assertEqual(self.mem_admin2.role.code, "system_tenant_admin")

    def test_t44_suspended_admin_reassigned_without_status_change(self):
        """Suspended admin can have role reassigned without changing status."""
        self._login_tenant(self.admin_alpha_1, self.org_alpha)
        url = f"/api/v1/tenant/admin-memberships/{self.mem_suspended.id}/role/"
        payload = {"role_id": str(self.custom_role_alpha.id)}

        res = self.client.patch(url, payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["status"], "suspended")
        self.assertEqual(res.data["role"]["id"], str(self.custom_role_alpha.id))

    def test_t45_ended_admin_reassigned_without_status_change(self):
        """Ended admin can have role reassigned without changing status."""
        self._login_tenant(self.admin_alpha_1, self.org_alpha)
        url = f"/api/v1/tenant/admin-memberships/{self.mem_ended.id}/role/"
        payload = {"role_id": str(self.custom_role_alpha.id)}

        res = self.client.patch(url, payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["status"], "ended")
        self.assertEqual(res.data["role"]["id"], str(self.custom_role_alpha.id))

    def test_t46_cross_tenant_membership_or_role_rejected(self):
        """Cross-tenant membership or role returns 404 without data leakage."""
        self._login_tenant(self.admin_alpha_1, self.org_alpha)

        # Cross-tenant membership
        res_mem = self.client.patch(
            f"/api/v1/tenant/admin-memberships/{self.mem_beta.id}/role/",
            {"role_id": str(self.custom_role_alpha.id)},
            format="json",
        )
        self.assertEqual(res_mem.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(res_mem.data["code"], "MEMBERSHIP_NOT_FOUND")

        # Cross-tenant role
        res_role = self.client.patch(
            f"/api/v1/tenant/admin-memberships/{self.mem_admin2.id}/role/",
            {"role_id": str(self.role_beta.id)},
            format="json",
        )
        self.assertEqual(res_role.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(res_role.data["code"], "ROLE_NOT_FOUND")

    def test_t47_regular_member_role_assignment_rejected(self):
        """Attempting to assign a role to a regular member returns 400 or 404."""
        self._login_tenant(self.admin_alpha_1, self.org_alpha)
        url = f"/api/v1/tenant/admin-memberships/{self.mem_regular.id}/role/"
        payload = {"role_id": str(self.custom_role_alpha.id)}

        res = self.client.patch(url, payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(res.data["code"], "ROLE_NOT_ASSIGNABLE_TO_MEMBER")

    def test_t48_retired_role_assignment_rejected(self):
        """Attempting to assign a retired role returns 400 ROLE_RETIRED."""
        self.custom_role_alpha.status = RoleStatus.RETIRED
        self.custom_role_alpha.save(update_fields=["status"])

        self._login_tenant(self.admin_alpha_1, self.org_alpha)
        url = f"/api/v1/tenant/admin-memberships/{self.mem_admin2.id}/role/"
        payload = {"role_id": str(self.custom_role_alpha.id)}

        res = self.client.patch(url, payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(res.data["code"], "ROLE_RETIRED")

    def test_t49_exact_equality_permission_assignment_allowed(self):
        """Assigning a role whose permissions match the actor's effective set succeeds."""
        self._login_tenant(self.admin_alpha_1, self.org_alpha)
        url = f"/api/v1/tenant/admin-memberships/{self.mem_admin2.id}/role/"
        payload = {"role_id": str(self.system_role.id)}

        res = self.client.patch(url, payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_200_OK)

    def test_t50_broader_than_actor_role_assignment_denied(self):
        """Actor cannot assign a role with permissions exceeding their own effective permissions."""
        # Restrict admin 1 to custom_role_alpha (lacks roles.assign).
        # We also need admin 1 to have roles.assign to invoke the endpoint, but let's give admin 1 a role
        # that has roles.assign and roles.view, but lacks roles.manage.
        assigner_role = Role.objects.create(
            organization=self.org_alpha,
            code="assigner_role",
            name="Assigner Role",
            is_system_role=False,
            status=RoleStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )
        RolePermission.objects.create(role=assigner_role, permission=self.perm_view)
        RolePermission.objects.create(role=assigner_role, permission=self.perm_assign)
        self.mem_admin1.role = assigner_role
        self.mem_admin1.save(update_fields=["role"])

        # Admin 1 now has roles.view and roles.assign, but NOT roles.manage.
        # Target role (system_role) has roles.manage.
        self._login_tenant(self.admin_alpha_1, self.org_alpha)
        url = f"/api/v1/tenant/admin-memberships/{self.mem_admin2.id}/role/"
        payload = {"role_id": str(self.system_role.id)}

        res = self.client.patch(url, payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(res.data["code"], "INSUFFICIENT_PRIVILEGES")

    def test_t51_role_assignment_noop_emits_zero_audit_events(self):
        """Assigning the same role already held emits zero new audit events."""
        self._login_tenant(self.admin_alpha_1, self.org_alpha)
        url = f"/api/v1/tenant/admin-memberships/{self.mem_admin2.id}/role/"
        payload = {"role_id": str(self.system_role.id)}

        count_before = AuditLog.objects.count()
        res = self.client.patch(url, payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(AuditLog.objects.count(), count_before)

    def test_t52_final_capable_admin_downgrade_returns_last_admin_protection(self):
        """Downgrading the final capable admin to a restricted role returns 400 LAST_ADMIN_PROTECTION."""
        # Admin 2 is already downgraded to custom_role_alpha (or view only)
        view_only = Role.objects.create(
            organization=self.org_alpha,
            code="view_only_adm2_assign",
            name="View Only",
            is_system_role=False,
            status=RoleStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )
        RolePermission.objects.create(role=view_only, permission=self.perm_view)
        self.mem_admin2.role = view_only
        self.mem_admin2.save(update_fields=["role"])

        # Admin 1 is the ONLY capable admin.
        self._login_tenant(self.admin_alpha_1, self.org_alpha)
        url = f"/api/v1/tenant/admin-memberships/{self.mem_admin1.id}/role/"
        payload = {"role_id": str(view_only.id)}

        res = self.client.patch(url, payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(res.data["code"], "LAST_ADMIN_PROTECTION")

    def test_t53_successful_assignment_emits_audit_event(self):
        """A successful role change emits exactly one MEMBERSHIP_ROLE_ASSIGNED audit event."""
        self._login_tenant(self.admin_alpha_1, self.org_alpha)
        url = f"/api/v1/tenant/admin-memberships/{self.mem_admin2.id}/role/"
        payload = {"role_id": str(self.custom_role_alpha.id)}

        count_before = AuditLog.objects.count()
        res = self.client.patch(url, payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        self.assertEqual(AuditLog.objects.count(), count_before + 1)
        latest = AuditLog.objects.latest("timestamp")
        self.assertEqual(latest.action, AuditAction.MEMBERSHIP_ROLE_ASSIGNED)
        self.assertEqual(latest.actor, self.admin_alpha_1)
        self.assertEqual(latest.organization_id, self.org_alpha.id)

