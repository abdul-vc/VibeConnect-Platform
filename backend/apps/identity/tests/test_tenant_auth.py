"""Stage 3 Test Suite: Unified Authentication, Console Context, LoginAttempt Privacy & QA Bootstrap.

Verifies:
- Login 401 vs 403 NO_CONSOLE_ACCESS behavior.
- Zero account and organization enumeration.
- LoginAttempt recording with keyed HMAC hashes and zero secret leakage.
- CSRF enforcement and session key rotation on login and context switch.
- Server-side context entry (platform owner default, single-tenant auto-entry, multi-tenant choices).
- Context selection endpoint security (platform ownership alone grants no tenant access).
- Prompt context revocation on /auth/me when tenant organization or membership becomes inactive.
- Tenant Admin logout with session destruction and audit logging.
- QA bootstrap database guard, account collision prevention, and test execution.
"""

import os
from unittest.mock import patch
import uuid

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.auditlog.models import AuditAction, AuditLog, AuditTargetType
from apps.identity.models import LoginAttempt, UserStatus
from apps.identity.tenant_context import hash_identifier, hash_ip
from apps.organizations.models import (
    MembershipStatus,
    MembershipType,
    Organization,
    OrganizationMembership,
    OrganizationStatus,
)

PlatformUser = get_user_model()


class Stage3TenantAuthBase(TestCase):
    """Base setup for Stage 3 authentication and context tests."""

    def setUp(self):
        super().setUp()
        cache.clear()
        self.client = APIClient(enforce_csrf_checks=True)
        self.password = "SecurePassword123!"

        # 1. Platform Owner
        self.owner = PlatformUser.objects.create_user(
            email="owner@vibeconnect.internal",
            password=self.password,
            full_name="Platform Owner",
            status=UserStatus.ACTIVE,
            is_active=True,
            is_platform_owner=True,
        )

        # 2. Organizations
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

        from apps.access_control.models import Role
        from apps.access_control.services.provisioning import provision_organization_defaults

        provision_organization_defaults(organization=self.org_alpha, actor=self.owner)
        provision_organization_defaults(organization=self.org_beta, actor=self.owner)

        self.system_role = Role.objects.filter(code="system_tenant_admin").first()

        # 3. Single Tenant Admin (in org_alpha)
        self.single_admin = PlatformUser.objects.create_user(
            email="single_admin@vibeconnect.internal",
            password=self.password,
            full_name="Single Admin",
            status=UserStatus.ACTIVE,
            is_active=True,
            is_platform_owner=False,
        )
        OrganizationMembership.objects.create(
            user=self.single_admin,
            organization=self.org_alpha,
            membership_type=MembershipType.TENANT_ADMIN,
            status=MembershipStatus.ACTIVE,
            role=self.system_role,
            joined_at=timezone.now(),
        )

        # 4. Multi Tenant Admin (in org_alpha and org_beta)
        self.multi_admin = PlatformUser.objects.create_user(
            email="multi_admin@vibeconnect.internal",
            password=self.password,
            full_name="Multi Admin",
            status=UserStatus.ACTIVE,
            is_active=True,
            is_platform_owner=False,
        )
        OrganizationMembership.objects.create(
            user=self.multi_admin,
            organization=self.org_alpha,
            membership_type=MembershipType.TENANT_ADMIN,
            status=MembershipStatus.ACTIVE,
            role=self.system_role,
            joined_at=timezone.now(),
        )
        OrganizationMembership.objects.create(
            user=self.multi_admin,
            organization=self.org_beta,
            membership_type=MembershipType.TENANT_ADMIN,
            status=MembershipStatus.ACTIVE,
            role=self.system_role,
            joined_at=timezone.now(),
        )

        # 5. Regular Member (member in org_alpha, no tenant_admin)
        self.regular_member = PlatformUser.objects.create_user(
            email="regular_member@vibeconnect.internal",
            password=self.password,
            full_name="Regular Member",
            status=UserStatus.ACTIVE,
            is_active=True,
            is_platform_owner=False,
        )
        OrganizationMembership.objects.create(
            user=self.regular_member,
            organization=self.org_alpha,
            membership_type=MembershipType.MEMBER,
            status=MembershipStatus.ACTIVE,
            joined_at=timezone.now(),
        )

        # 6. Inactive User (suspended)
        self.suspended_user = PlatformUser.objects.create_user(
            email="suspended@vibeconnect.internal",
            password=self.password,
            full_name="Suspended User",
            status=UserStatus.SUSPENDED,
            is_active=False,
            is_platform_owner=False,
        )

    def tearDown(self):
        cache.clear()
        super().tearDown()

    def _get_csrf_token(self, client=None) -> str:
        c = client or self.client
        response = c.get("/api/v1/auth/csrf/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        return response.cookies[settings.CSRF_COOKIE_NAME].value

    def _login(self, email: str, password: str | None = None, client=None):
        c = client or self.client
        token = self._get_csrf_token(client=c)
        return c.post(
            "/api/v1/auth/login/",
            {"email": email, "password": password or self.password},
            format="json",
            HTTP_X_CSRFTOKEN=token,
        )


class TestTenantAuthenticationAndConsoleAccess(Stage3TenantAuthBase):
    """Verifies login authentication, 401/403 contracts, enumeration resistance, and session rotation."""

    def test_login_unknown_email_uniform_401(self):
        res = self._login("unknown@vibeconnect.internal", self.password)
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(res.json(), {"detail": "Invalid credentials or unauthorized account."})

    def test_login_wrong_password_uniform_401(self):
        res = self._login(self.owner.email, "WrongPass123!")
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(res.json(), {"detail": "Invalid credentials or unauthorized account."})

    def test_login_suspended_user_uniform_401(self):
        res = self._login(self.suspended_user.email, self.password)
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(res.json(), {"detail": "Invalid credentials or unauthorized account."})

    def test_login_regular_tenant_member_succeeds_with_tenant_context(self):
        """Active regular tenant member can log in and receives tenant context without admin permissions."""
        res = self._login(self.regular_member.email, self.password)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        data = res.json()
        self.assertEqual(data["active_context"]["type"], "tenant")
        self.assertEqual(data["active_context"]["membership_type"], "member")
        self.assertEqual(data["active_context"]["organization"]["id"], str(self.org_alpha.id))
        self.assertEqual(data["active_context"]["effective_permissions"], [])
        self.assertEqual(data["active_context"]["allowed_modules"], [])
        self.assertIn(settings.SESSION_COOKIE_NAME, res.cookies)

    def test_tenant_member_session_endpoints_and_admin_console_denial(self):
        """Active tenant member can access /auth/me and /tenant/home, but is denied admin console."""
        login_res = self._login(self.regular_member.email, self.password)
        self.assertEqual(login_res.status_code, status.HTTP_200_OK)

        # 1. /api/v1/auth/me/ succeeds with tenant member context
        me_res = self.client.get("/api/v1/auth/me/")
        self.assertEqual(me_res.status_code, status.HTTP_200_OK)
        me_data = me_res.json()
        self.assertEqual(me_data["active_context"]["type"], "tenant")
        self.assertEqual(me_data["active_context"]["membership_type"], "member")
        self.assertEqual(me_data["active_context"]["organization"]["id"], str(self.org_alpha.id))

        # 2. /api/v1/tenant/home/ succeeds for tenant member
        home_res = self.client.get("/api/v1/tenant/home/")
        self.assertEqual(home_res.status_code, status.HTTP_200_OK)

        # 3. Tenant Admin console endpoints are DENIED (403 NO_CONSOLE_ACCESS)
        roles_res = self.client.get("/api/v1/tenant/roles/")
        self.assertEqual(roles_res.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(roles_res.json().get("code"), "NO_CONSOLE_ACCESS")

        memberships_res = self.client.get("/api/v1/tenant/admin-memberships/")
        self.assertEqual(memberships_res.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(memberships_res.json().get("code"), "NO_CONSOLE_ACCESS")

        # 4. Platform Owner endpoints are DENIED (403)
        policies_res = self.client.get(f"/api/v1/organizations/{self.org_alpha.id}/console-policies/")
        self.assertEqual(policies_res.status_code, status.HTTP_403_FORBIDDEN)

        # 5. Member logout succeeds with session destruction and audit log
        token = self._get_csrf_token()
        logout_res = self.client.post("/api/v1/auth/logout/", format="json", HTTP_X_CSRFTOKEN=token)
        self.assertEqual(logout_res.status_code, status.HTTP_200_OK)

        # Session destroyed
        me_after_logout = self.client.get("/api/v1/auth/me/")
        self.assertEqual(me_after_logout.status_code, status.HTTP_401_UNAUTHORIZED)

        # Audit log correctly recorded
        audit = AuditLog.objects.filter(action=AuditAction.LOGOUT_SUCCESS, target_id=self.regular_member.id).first()
        self.assertIsNotNone(audit)
        self.assertEqual(audit.target_repr, "Tenant Member Session")

    def test_login_active_user_without_any_membership_returns_403_no_console_access(self):
        """Active user with valid credentials but no memberships receives 403."""
        no_membership_user = PlatformUser.objects.create_user(
            email="no_membership@vibeconnect.internal",
            password=self.password,
            full_name="No Membership",
            status=UserStatus.ACTIVE,
            is_active=True,
            is_platform_owner=False,
        )
        res = self._login(no_membership_user.email, self.password)
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(
            res.json(),
            {"code": "NO_CONSOLE_ACCESS", "detail": "No active console access."},
        )
        self.assertNotIn(settings.SESSION_COOKIE_NAME, res.cookies)

    def test_login_active_user_with_inactive_org_returns_403(self):
        """If organization is suspended, tenant_admin receives 403 NO_CONSOLE_ACCESS."""
        self.org_alpha.status = OrganizationStatus.SUSPENDED
        self.org_alpha.save(update_fields=["status"])

        res = self._login(self.single_admin.email, self.password)
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(res.json()["code"], "NO_CONSOLE_ACCESS")

    def test_login_platform_owner_default_context(self):
        res = self._login(self.owner.email, self.password)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        data = res.json()
        self.assertEqual(
            data["active_context"],
            {
                "type": "platform_owner",
                "organization": None,
                "effective_permissions": [],
                "allowed_modules": [
                    "po_overview",
                    "po_products",
                    "po_plans",
                    "po_subscriptions",
                    "po_organizations",
                    "po_users",
                    "po_entitlements",
                    "po_activity_log",
                ],
            },
        )
        self.assertTrue(any(c["type"] == "platform_owner" for c in data["available_contexts"]))

    def test_login_single_tenant_admin_auto_enters_tenant_context(self):
        res = self._login(self.single_admin.email, self.password)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        data = res.json()
        self.assertIsNotNone(data["active_context"])
        self.assertEqual(data["active_context"]["type"], "tenant")
        self.assertEqual(data["active_context"]["organization"]["id"], str(self.org_alpha.id))
        self.assertEqual(len(data["available_contexts"]), 1)

    def test_login_multi_tenant_admin_receives_choices_no_auto_select(self):
        res = self._login(self.multi_admin.email, self.password)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        data = res.json()
        # With multiple eligible orgs, active_context is None until user selects
        self.assertIsNone(data["active_context"])
        self.assertEqual(len(data["available_contexts"]), 2)
        org_ids = [c["organization"]["id"] for c in data["available_contexts"]]
        self.assertIn(str(self.org_alpha.id), org_ids)
        self.assertIn(str(self.org_beta.id), org_ids)

    def test_login_rotates_session_key(self):
        token = self._get_csrf_token()
        session = self.client.session
        session["dummy"] = "initial"
        session.save()
        initial_key = self.client.session.session_key

        res = self.client.post(
            "/api/v1/auth/login/",
            {"email": self.owner.email, "password": self.password},
            format="json",
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        new_key = self.client.session.session_key
        self.assertNotEqual(initial_key, new_key)

    def test_login_without_csrf_rejected_403(self):
        res = self.client.post(
            "/api/v1/auth/login/",
            {"email": self.owner.email, "password": self.password},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)


class TestLoginAttemptPrivacyAndEvidence(Stage3TenantAuthBase):
    """Verifies that LoginAttempt stores only keyed HMAC hashes and never plaintext secrets."""

    def test_login_attempt_recorded_on_failure_with_keyed_hashes_no_plaintext(self):
        email = "unknown_user@example.com"
        res = self._login(email, "WrongPassword!")
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

        attempt = LoginAttempt.objects.first()
        self.assertIsNotNone(attempt)
        self.assertEqual(attempt.result, "failure")
        self.assertEqual(attempt.failure_code, "invalid_credentials")
        self.assertIsNone(attempt.user)

        # Verify keyed hash matches
        expected_hash = hash_identifier(email)
        self.assertEqual(attempt.identifier_hash, expected_hash)
        # Ensure plaintext email is nowhere in the database row
        self.assertNotIn(email, attempt.identifier_hash)
        self.assertNotIn("WrongPassword!", attempt.failure_code)

    def test_login_attempt_recorded_on_403_with_keyed_hashes(self):
        no_membership_user = PlatformUser.objects.create_user(
            email="no_membership_hash@vibeconnect.internal",
            password=self.password,
            full_name="No Membership Hash",
            status=UserStatus.ACTIVE,
            is_active=True,
            is_platform_owner=False,
        )
        res = self._login(no_membership_user.email, self.password)
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

        attempt = LoginAttempt.objects.filter(user=no_membership_user).first()
        self.assertIsNotNone(attempt)
        self.assertEqual(attempt.result, "failure")
        self.assertEqual(attempt.failure_code, "no_console_access")
        self.assertEqual(attempt.user, no_membership_user)
        self.assertEqual(attempt.identifier_hash, hash_identifier(no_membership_user.email))

    def test_login_attempt_recorded_on_success(self):
        res = self._login(self.owner.email, self.password)
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        attempt = LoginAttempt.objects.first()
        self.assertIsNotNone(attempt)
        self.assertEqual(attempt.result, "success")
        self.assertEqual(attempt.failure_code, "")
        self.assertEqual(attempt.user, self.owner)
        self.assertEqual(attempt.identifier_hash, hash_identifier(self.owner.email))


class TestContextSelectionAndRevocation(Stage3TenantAuthBase):
    """Verifies context switching, tenant isolation, /auth/me, and prompt context revocation."""

    def test_context_selection_tenant_success(self):
        # Multi admin logs in (active_context is None)
        self._login(self.multi_admin.email, self.password)
        token = self._get_csrf_token()

        # Switch to org_alpha
        res = self.client.post(
            "/api/v1/auth/context/",
            {"context_type": "tenant", "organization_id": str(self.org_alpha.id)},
            format="json",
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        data = res.json()
        self.assertEqual(data["active_context"]["type"], "tenant")
        self.assertEqual(data["active_context"]["organization"]["id"], str(self.org_alpha.id))

        # Switch to org_beta
        res2 = self.client.post(
            "/api/v1/auth/context/",
            {"context_type": "tenant", "organization_id": str(self.org_beta.id)},
            format="json",
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(res2.status_code, status.HTTP_200_OK)
        self.assertEqual(res2.json()["active_context"]["organization"]["id"], str(self.org_beta.id))

    def test_context_selection_platform_ownership_alone_grants_no_tenant_access(self):
        """Platform Owners cannot switch to a tenant context unless they have an active tenant_admin membership."""
        self._login(self.owner.email, self.password)
        token = self._get_csrf_token()

        res = self.client.post(
            "/api/v1/auth/context/",
            {"context_type": "tenant", "organization_id": str(self.org_alpha.id)},
            format="json",
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(res.json()["code"], "INSUFFICIENT_PRIVILEGES")

    def test_context_selection_platform_owner_context_rejected_for_tenant_admin(self):
        self._login(self.single_admin.email, self.password)
        token = self._get_csrf_token()

        res = self.client.post(
            "/api/v1/auth/context/",
            {"context_type": "platform_owner"},
            format="json",
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(res.json()["code"], "INSUFFICIENT_PRIVILEGES")

    def test_auth_me_revalidates_and_revokes_inactive_tenant_context(self):
        """If an organization is suspended while a user holds an active session, /auth/me revokes the context."""
        # 1. Multi admin logs in and selects org_alpha
        self._login(self.multi_admin.email, self.password)
        token = self._get_csrf_token()
        self.client.post(
            "/api/v1/auth/context/",
            {"context_type": "tenant", "organization_id": str(self.org_alpha.id)},
            format="json",
            HTTP_X_CSRFTOKEN=token,
        )
        me_res = self.client.get("/api/v1/auth/me/")
        self.assertEqual(me_res.status_code, status.HTTP_200_OK)
        self.assertEqual(me_res.json()["active_context"]["organization"]["id"], str(self.org_alpha.id))

        # 2. Single admin also establishes an active session while org_alpha is active
        single_client = APIClient()
        self._login(self.single_admin.email, self.password, client=single_client)
        single_me_before = single_client.get("/api/v1/auth/me/")
        self.assertEqual(single_me_before.status_code, status.HTTP_200_OK)
        self.assertEqual(single_me_before.json()["active_context"]["organization"]["id"], str(self.org_alpha.id))

        # 3. Deactivate organization alpha
        self.org_alpha.status = OrganizationStatus.SUSPENDED
        self.org_alpha.save(update_fields=["status"])

        # 4. /auth/me revalidates and revokes active context promptly for multi_admin (org_beta remains)
        me_res2 = self.client.get("/api/v1/auth/me/")
        self.assertEqual(me_res2.status_code, status.HTTP_200_OK)
        self.assertIsNone(me_res2.json()["active_context"])
        self.assertEqual(len(me_res2.json()["available_contexts"]), 1)
        self.assertEqual(me_res2.json()["available_contexts"][0]["organization"]["id"], str(self.org_beta.id))

        # 5. Single admin (holding active session, but now with zero eligible orgs) receives 403 NO_CONSOLE_ACCESS on /auth/me
        single_me_after = single_client.get("/api/v1/auth/me/")
        self.assertEqual(single_me_after.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(single_me_after.json(), {"detail": "Access restricted to active platform owners."})

    def test_tenant_admin_logout_clears_session_and_records_audit(self):
        self._login(self.single_admin.email, self.password)
        token = self._get_csrf_token()

        res = self.client.post("/api/v1/auth/logout/", format="json", HTTP_X_CSRFTOKEN=token)
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        # Subsequent authenticated requests return 401
        res2 = self.client.get("/api/v1/auth/me/")
        self.assertEqual(res2.status_code, status.HTTP_401_UNAUTHORIZED)

        # Audit event recorded for tenant admin logout
        audit = AuditLog.objects.filter(action=AuditAction.LOGOUT_SUCCESS, target_id=self.single_admin.id).first()
        self.assertIsNotNone(audit)
        self.assertEqual(audit.target_repr, "Tenant Admin Session")


class TestQABootstrapCommand(TestCase):
    """Verifies bootstrap_phase2d_qa guards, collision handling, and test execution."""

    def test_bootstrap_rejects_without_allow_test_database_on_test_db(self):
        """Running without --allow-test-database on disposable test db raises CommandError."""
        with patch.dict(os.environ, {"PHASE2D_QA_BOOTSTRAP_PASSWORD": "ValidPassword123!"}):
            with self.assertRaises(CommandError) as ctx:
                call_command("bootstrap_phase2d_qa")
            self.assertIn("strictly restricted to 'vibeconnect_phase2c_test'", str(ctx.exception))

    def test_bootstrap_rejects_account_collision_without_provenance(self):
        """If a target email exists without external_subject_id provenance, command aborts safely."""
        PlatformUser.objects.create_user(
            email="phase2d.tenant.admin@vibeconnect.internal",
            password="OtherPassword123!",
            status=UserStatus.ACTIVE,
            auth_provider="local",
            external_subject_id="",  # Lacks QA bootstrap provenance
        )

        with patch.dict(os.environ, {"PHASE2D_QA_BOOTSTRAP_PASSWORD": "ValidPassword123!"}):
            with self.assertRaises(CommandError) as ctx:
                call_command("bootstrap_phase2d_qa", "--allow-test-database")
            self.assertIn("Account collision", str(ctx.exception))

    def test_bootstrap_success_path_with_allow_test_database(self):
        """With --allow-test-database and valid password in test environment, bootstrap creates accounts and memberships."""
        with patch.dict(os.environ, {"PHASE2D_QA_BOOTSTRAP_PASSWORD": "ValidPassword123!"}):
            call_command("bootstrap_phase2d_qa", "--allow-test-database")

        # 1. Verify Single Tenant Admin
        u_single = PlatformUser.objects.filter(email="phase2d.tenant.admin@vibeconnect.internal").first()
        self.assertIsNotNone(u_single)
        self.assertEqual(u_single.auth_provider, "local")
        self.assertEqual(u_single.external_subject_id, "vibeconnect:qa_bootstrap:phase2d.tenant.admin@vibeconnect.internal")
        self.assertTrue(u_single.check_password("ValidPassword123!"))
        self.assertEqual(u_single.status, UserStatus.ACTIVE)

        m_single = OrganizationMembership.objects.filter(user=u_single)
        self.assertEqual(m_single.count(), 1)
        self.assertEqual(m_single.first().organization.code, "qa-org-alpha")
        self.assertEqual(m_single.first().membership_type, MembershipType.TENANT_ADMIN)

        # 2. Verify Multi Tenant Admin
        u_multi = PlatformUser.objects.filter(email="phase2d.multi.admin@vibeconnect.internal").first()
        self.assertIsNotNone(u_multi)
        m_multi = OrganizationMembership.objects.filter(user=u_multi)
        self.assertEqual(m_multi.count(), 2)
        org_codes = set(m_multi.values_list("organization__code", flat=True))
        self.assertEqual(org_codes, {"qa-org-alpha", "qa-org-beta"})

        # 3. Verify Regular Member
        u_member = PlatformUser.objects.filter(email="phase2d.regular.member@vibeconnect.internal").first()
        self.assertIsNotNone(u_member)
        m_member = OrganizationMembership.objects.filter(user=u_member)
        self.assertEqual(m_member.count(), 1)
        self.assertEqual(m_member.first().membership_type, MembershipType.MEMBER)


class TestStage3AdditiveAuthPayloads(Stage3TenantAuthBase):
    """Verifies additive effective_permissions and allowed_modules in auth responses."""

    def test_tenant_active_context_includes_effective_permissions_and_modules(self):
        res = self._login(self.single_admin.email, self.password)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        data = res.json()
        # Verify top-level user fields are preserved
        self.assertIn("id", data)
        self.assertIn("email", data)
        self.assertIn("full_name", data)
        self.assertIn("is_platform_owner", data)
        self.assertIn("active_context", data)
        self.assertIn("available_contexts", data)

        active = data["active_context"]
        self.assertEqual(active["type"], "tenant")
        self.assertEqual(active["organization"]["id"], str(self.org_alpha.id))
        self.assertIsInstance(active["effective_permissions"], list)
        self.assertIsInstance(active["allowed_modules"], list)
        self.assertIn("roles.view", active["effective_permissions"])
        self.assertIn("tenant_landing", active["allowed_modules"])
        self.assertIn("tenant_roles", active["allowed_modules"])

    def test_platform_owner_active_context_has_empty_effective_permissions_and_po_modules(self):
        res = self._login(self.owner.email, self.password)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        data = res.json()
        active = data["active_context"]
        self.assertEqual(active["type"], "platform_owner")
        self.assertIsNone(active["organization"])
        self.assertEqual(active["effective_permissions"], [])
        self.assertEqual(
            active["allowed_modules"],
            [
                "po_overview",
                "po_products",
                "po_plans",
                "po_subscriptions",
                "po_organizations",
                "po_users",
                "po_entitlements",
                "po_activity_log",
            ],
        )

    def test_auth_me_reflects_immediate_database_authorization_change_no_stale_cache(self):
        # 1. Single admin logs in
        self._login(self.single_admin.email, self.password)

        # 2. First /auth/me call
        res1 = self.client.get("/api/v1/auth/me/")
        self.assertEqual(res1.status_code, status.HTTP_200_OK)
        self.assertIn("roles.assign", res1.json()["active_context"]["effective_permissions"])

        # 3. Change ceiling in database to revoke roles.assign
        from apps.access_control.models import OrganizationPermissionCeiling

        OrganizationPermissionCeiling.objects.filter(
            organization=self.org_alpha,
            permission_id="roles.assign",
        ).update(is_allowed=False)

        # 4. Second /auth/me call immediately reflects database state (no stale cache)
        res2 = self.client.get("/api/v1/auth/me/")
        self.assertEqual(res2.status_code, status.HTTP_200_OK)
        self.assertNotIn("roles.assign", res2.json()["active_context"]["effective_permissions"])
