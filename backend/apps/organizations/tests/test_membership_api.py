"""Organization Membership API Tests (Phase 2D Stage 4).

Verifies Platform Owner authority, tenant denial, organization isolation,
membership listing, creation, role mutation, and lifecycle transitions via HTTP endpoints.
"""

import uuid
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.access_control.models import Role
from apps.identity.models import UserStatus
from apps.organizations.models import (
    MembershipStatus,
    MembershipType,
    Organization,
    OrganizationMembership,
    OrganizationStatus,
)

PlatformUser = get_user_model()


class MembershipApiTests(APITestCase):
    """Test suite for organization membership management endpoints under Platform Owner authority."""

    def setUp(self):
        super().setUp()
        self.password = "SecureTestPass123!"

        # System role for Tenant Admin memberships
        self.system_tenant_admin_role = Role.objects.get(
            code="system_tenant_admin", is_system_role=True
        )

        # 1. Platform Owner
        self.owner = PlatformUser.objects.create_user(
            email="owner@vibeconnect.internal",
            password=self.password,
            full_name="Platform Owner",
            status=UserStatus.ACTIVE,
            is_active=True,
            is_platform_owner=True,
        )

        # 2. Regular User / Tenant Admin candidate
        self.member_user = PlatformUser.objects.create_user(
            email="member@vibeconnect.internal",
            password=self.password,
            full_name="Member User",
            status=UserStatus.ACTIVE,
            is_active=True,
            is_platform_owner=False,
        )

        # 3. Organizations (Org Alpha & Org Beta for cross-tenant isolation testing)
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

        # 4. Membership in Org Alpha
        self.membership_alpha = OrganizationMembership.objects.create(
            organization=self.org_alpha,
            user=self.member_user,
            membership_type=MembershipType.MEMBER,
            status=MembershipStatus.ACTIVE,
            joined_at=timezone.now(),
        )

        # 5. User & Membership in Org Beta
        self.beta_user = PlatformUser.objects.create_user(
            email="beta.user@vibeconnect.internal",
            password=self.password,
            full_name="Beta User",
            status=UserStatus.ACTIVE,
            is_active=True,
            is_platform_owner=False,
        )
        self.membership_beta = OrganizationMembership.objects.create(
            organization=self.org_beta,
            user=self.beta_user,
            membership_type=MembershipType.TENANT_ADMIN,
            role=self.system_tenant_admin_role,
            status=MembershipStatus.ACTIVE,
            joined_at=timezone.now(),
        )

    def tearDown(self):
        cache.clear()
        super().tearDown()

    def _get_csrf_token(self) -> str:
        response = self.client.get("/api/v1/auth/csrf/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        return response.cookies[settings.CSRF_COOKIE_NAME].value

    def _login(self, email: str, password: str | None = None):
        token = self._get_csrf_token()
        return self.client.post(
            "/api/v1/auth/login/",
            {"email": email, "password": password or self.password},
            format="json",
            HTTP_X_CSRFTOKEN=token,
        )

    # 1. Security & Authorization
    def test_unauthenticated_requests_rejected_401(self):
        res = self.client.get(f"/api/v1/organizations/{self.org_alpha.id}/memberships/")
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_tenant_admin_denied_403(self):
        self._login(self.beta_user.email, self.password)
        res = self.client.get(f"/api/v1/organizations/{self.org_alpha.id}/memberships/")
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(res.json(), {"detail": "Access restricted to active platform owners in platform owner context."})

    def test_platform_owner_in_tenant_context_denied_403(self):
        self._login(self.owner.email, self.password)
        # Switch session to tenant context
        session = self.client.session
        session["active_context_type"] = "tenant"
        session["tenant_organization_id"] = str(self.org_alpha.id)
        session.save()

        res = self.client.get(f"/api/v1/organizations/{self.org_alpha.id}/memberships/")
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    # 2. Organization Isolation
    def test_organization_isolation_listing(self):
        """Listing memberships for org_alpha returns only org_alpha memberships."""
        self._login(self.owner.email, self.password)
        res = self.client.get(f"/api/v1/organizations/{self.org_alpha.id}/memberships/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        results = res.json()["results"]
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["id"], str(self.membership_alpha.id))
        self.assertEqual(results[0]["organization_id"], str(self.org_alpha.id))

    def test_organization_isolation_cross_tenant_retrieve_404(self):
        """Requesting membership_beta under org_alpha path returns 404 Not Found."""
        self._login(self.owner.email, self.password)
        res = self.client.get(f"/api/v1/organizations/{self.org_alpha.id}/memberships/{self.membership_beta.id}/")
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(res.json()["code"], "MEMBERSHIP_NOT_FOUND")

    def test_nonexistent_organization_404(self):
        self._login(self.owner.email, self.password)
        res = self.client.get(f"/api/v1/organizations/{uuid.uuid4()}/memberships/")
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(res.json()["code"], "ORGANIZATION_NOT_FOUND")

    # 3. Membership Creation & Conflict Handling
    def test_create_membership_success(self):
        self._login(self.owner.email, self.password)
        token = self._get_csrf_token()

        new_user = PlatformUser.objects.create_user(
            email="candidate@vibeconnect.internal",
            password=self.password,
            full_name="Candidate",
            status=UserStatus.ACTIVE,
            is_active=True,
            is_platform_owner=False,
        )

        res = self.client.post(
            f"/api/v1/organizations/{self.org_alpha.id}/memberships/",
            {"user_id": str(new_user.id), "membership_type": "tenant_admin"},
            format="json",
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        data = res.json()
        self.assertEqual(data["membership_type"], "tenant_admin")
        self.assertEqual(data["status"], "active")
        self.assertEqual(data["user"]["id"], str(new_user.id))

    def test_create_membership_already_exists_409(self):
        self._login(self.owner.email, self.password)
        token = self._get_csrf_token()

        res = self.client.post(
            f"/api/v1/organizations/{self.org_alpha.id}/memberships/",
            {"user_id": str(self.member_user.id), "membership_type": "member"},
            format="json",
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(res.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(res.json()["code"], "MEMBERSHIP_ALREADY_EXISTS")

    def test_create_membership_ended_restore_required_409(self):
        self._login(self.owner.email, self.password)
        token = self._get_csrf_token()

        # End the membership first
        self.membership_alpha.status = MembershipStatus.ENDED
        self.membership_alpha.ended_at = timezone.now()
        self.membership_alpha.save(update_fields=["status", "ended_at"])

        res = self.client.post(
            f"/api/v1/organizations/{self.org_alpha.id}/memberships/",
            {"user_id": str(self.member_user.id), "membership_type": "member"},
            format="json",
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(res.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(res.json()["code"], "MEMBERSHIP_ENDED_RESTORE_REQUIRED")

    # 4. Membership Type Update
    def test_update_membership_type(self):
        self._login(self.owner.email, self.password)
        token = self._get_csrf_token()

        res = self.client.patch(
            f"/api/v1/organizations/{self.org_alpha.id}/memberships/{self.membership_alpha.id}/",
            {"membership_type": "tenant_admin"},
            format="json",
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.json()["membership_type"], "tenant_admin")

    # 5. Membership Lifecycle Actions: Suspend, Reactivate, End, Restore
    def test_membership_lifecycle_full_flow(self):
        self._login(self.owner.email, self.password)
        token = self._get_csrf_token()

        # 1. Suspend
        sus_res = self.client.post(
            f"/api/v1/organizations/{self.org_alpha.id}/memberships/{self.membership_alpha.id}/suspend/",
            {"reason": "Leave of absence"},
            format="json",
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(sus_res.status_code, status.HTTP_200_OK)
        self.assertEqual(sus_res.json()["status"], "suspended")

        # 2. Reactivate
        react_res = self.client.post(
            f"/api/v1/organizations/{self.org_alpha.id}/memberships/{self.membership_alpha.id}/reactivate/",
            format="json",
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(react_res.status_code, status.HTTP_200_OK)
        self.assertEqual(react_res.json()["status"], "active")

        # 3. End
        end_res = self.client.post(
            f"/api/v1/organizations/{self.org_alpha.id}/memberships/{self.membership_alpha.id}/end/",
            {"reason": "Contract finished"},
            format="json",
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(end_res.status_code, status.HTTP_200_OK)
        self.assertEqual(end_res.json()["status"], "ended")
        self.assertIsNotNone(end_res.json()["ended_at"])

        # 4. Restore
        rest_res = self.client.post(
            f"/api/v1/organizations/{self.org_alpha.id}/memberships/{self.membership_alpha.id}/restore/",
            format="json",
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(rest_res.status_code, status.HTTP_200_OK)
        self.assertEqual(rest_res.json()["status"], "active")
        self.assertIsNone(rest_res.json()["ended_at"])

    # 6. Assigned Role Serialization (Phase 2E Stage 6 Integration)
    def test_tenant_admin_membership_list_contains_role_summary(self):
        """Tenant Admin membership in list endpoint contains exact role summary."""
        self._login(self.owner.email, self.password)
        res = self.client.get(f"/api/v1/organizations/{self.org_beta.id}/memberships/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        results = res.json()["results"]
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["id"], str(self.membership_beta.id))
        self.assertIsNotNone(results[0]["role"])
        self.assertEqual(
            results[0]["role"],
            {
                "id": str(self.system_tenant_admin_role.id),
                "code": "system_tenant_admin",
                "name": "Tenant Administrator",
                "is_system_role": True,
            },
        )

    def test_tenant_admin_membership_detail_contains_role_summary(self):
        """Tenant Admin membership in retrieve endpoint contains exact role summary."""
        self._login(self.owner.email, self.password)
        res = self.client.get(f"/api/v1/organizations/{self.org_beta.id}/memberships/{self.membership_beta.id}/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        data = res.json()
        self.assertIsNotNone(data["role"])
        self.assertEqual(
            data["role"],
            {
                "id": str(self.system_tenant_admin_role.id),
                "code": "system_tenant_admin",
                "name": "Tenant Administrator",
                "is_system_role": True,
            },
        )

    def test_regular_member_response_contains_role_null(self):
        """Regular member list and detail responses contain role: null."""
        self._login(self.owner.email, self.password)
        # List
        res_list = self.client.get(f"/api/v1/organizations/{self.org_alpha.id}/memberships/")
        self.assertEqual(res_list.status_code, status.HTTP_200_OK)
        self.assertIsNone(res_list.json()["results"][0]["role"])

        # Detail
        res_detail = self.client.get(f"/api/v1/organizations/{self.org_alpha.id}/memberships/{self.membership_alpha.id}/")
        self.assertEqual(res_detail.status_code, status.HTTP_200_OK)
        self.assertIsNone(res_detail.json()["role"])

    def test_membership_write_payload_cannot_mutate_role(self):
        """Sending role in PATCH payload does not alter the assigned role."""
        self._login(self.owner.email, self.password)
        token = self._get_csrf_token()

        fake_role_id = str(uuid.uuid4())
        res = self.client.patch(
            f"/api/v1/organizations/{self.org_beta.id}/memberships/{self.membership_beta.id}/",
            {"membership_type": "tenant_admin", "role": fake_role_id, "role_id": fake_role_id},
            format="json",
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        data = res.json()
        self.assertEqual(data["role"]["id"], str(self.system_tenant_admin_role.id))
        self.assertEqual(data["role"]["code"], "system_tenant_admin")
        self.membership_beta.refresh_from_db()
        self.assertEqual(self.membership_beta.role_id, self.system_tenant_admin_role.id)

    # 6. Last Qualifying Administrator API Protection
    def test_suspend_sole_qualifying_admin_rejected_via_api(self):
        """Platform Owner suspending sole qualifying admin returns HTTP 400 LAST_ADMIN_PROTECTION."""
        self._login(self.owner.email, self.password)
        token = self._get_csrf_token()

        res = self.client.post(
            f"/api/v1/organizations/{self.org_beta.id}/memberships/{self.membership_beta.id}/suspend/",
            {"reason": "Attempted suspension"},
            format="json",
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        data = res.json()
        self.assertEqual(data.get("code"), "LAST_ADMIN_PROTECTION")
        self.assertIn("at least one capable active tenant administrator", data.get("detail", ""))

        # Target membership remains unchanged
        self.membership_beta.refresh_from_db()
        self.assertEqual(self.membership_beta.status, MembershipStatus.ACTIVE)

    def test_end_sole_qualifying_admin_rejected_via_api(self):
        """Platform Owner ending sole qualifying admin returns HTTP 400 LAST_ADMIN_PROTECTION."""
        self._login(self.owner.email, self.password)
        token = self._get_csrf_token()

        res = self.client.post(
            f"/api/v1/organizations/{self.org_beta.id}/memberships/{self.membership_beta.id}/end/",
            {"reason": "Attempted termination"},
            format="json",
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        data = res.json()
        self.assertEqual(data.get("code"), "LAST_ADMIN_PROTECTION")
        self.assertIn("at least one capable active tenant administrator", data.get("detail", ""))

        # Target membership remains unchanged
        self.membership_beta.refresh_from_db()
        self.assertEqual(self.membership_beta.status, MembershipStatus.ACTIVE)
        self.assertIsNone(self.membership_beta.ended_at)

    def test_suspend_succeeds_when_another_qualifying_admin_exists_via_api(self):
        """Platform Owner suspending a qualifying admin succeeds when another qualifying admin exists."""
        self._login(self.owner.email, self.password)
        token = self._get_csrf_token()

        # Add second active qualifying tenant admin to Org Beta
        second_admin_user = PlatformUser.objects.create_user(
            email="beta.second.admin@vibeconnect.internal",
            password=self.password,
            full_name="Second Beta Admin",
            status=UserStatus.ACTIVE,
            is_active=True,
            is_platform_owner=False,
        )
        OrganizationMembership.objects.create(
            organization=self.org_beta,
            user=second_admin_user,
            membership_type=MembershipType.TENANT_ADMIN,
            role=self.system_tenant_admin_role,
            status=MembershipStatus.ACTIVE,
            joined_at=timezone.now(),
        )

        res = self.client.post(
            f"/api/v1/organizations/{self.org_beta.id}/memberships/{self.membership_beta.id}/suspend/",
            {"reason": "Temporary leave"},
            format="json",
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.membership_beta.refresh_from_db()
        self.assertEqual(self.membership_beta.status, MembershipStatus.SUSPENDED)

    def test_end_admin_allowed_when_second_qualifying_admin_exists(self):
        """Ending a qualifying admin succeeds when another qualifying admin exists."""
        self._login(self.owner.email, self.password)
        token = self._get_csrf_token()

        # Add second active qualifying tenant admin to Org Beta
        second_admin_user = PlatformUser.objects.create_user(
            email="beta.second.admin.end@vibeconnect.internal",
            password=self.password,
            full_name="Second Beta Admin End",
            status=UserStatus.ACTIVE,
            is_active=True,
            is_platform_owner=False,
        )
        second_membership = OrganizationMembership.objects.create(
            organization=self.org_beta,
            user=second_admin_user,
            membership_type=MembershipType.TENANT_ADMIN,
            role=self.system_tenant_admin_role,
            status=MembershipStatus.ACTIVE,
            joined_at=timezone.now(),
        )

        res = self.client.post(
            f"/api/v1/organizations/{self.org_beta.id}/memberships/{self.membership_beta.id}/end/",
            {"reason": "Departed organization"},
            format="json",
            HTTP_X_CSRFTOKEN=token,
        )
        # Verify the request succeeds
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        data = res.json()

        # Verify LAST_ADMIN_PROTECTION is not returned
        self.assertNotEqual(data.get("code"), "LAST_ADMIN_PROTECTION")

        # Verify the target membership receives the expected ended status
        self.membership_beta.refresh_from_db()
        self.assertEqual(self.membership_beta.status, MembershipStatus.ENDED)
        self.assertEqual(data.get("status"), "ended")

        # Verify ended_at is populated according to the existing API contract
        self.assertIsNotNone(self.membership_beta.ended_at)
        self.assertIsNotNone(data.get("ended_at"))

        # Verify the remaining qualifying administrator stays active
        second_membership.refresh_from_db()
        self.assertEqual(second_membership.status, MembershipStatus.ACTIVE)
        self.assertIsNone(second_membership.ended_at)
        second_admin_user.refresh_from_db()
        self.assertEqual(second_admin_user.status, UserStatus.ACTIVE)
        self.assertTrue(second_admin_user.is_active)

