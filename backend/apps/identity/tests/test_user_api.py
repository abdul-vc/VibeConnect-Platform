"""Platform User Management API Tests (Phase 2D Stage 4).

Verifies Platform Owner authority, tenant denial, context isolation,
central user listing, creation, updates, and lifecycle transitions via HTTP endpoints.
"""

import uuid
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.identity.models import UserStatus
from apps.organizations.models import (
    MembershipStatus,
    MembershipType,
    Organization,
    OrganizationMembership,
    OrganizationStatus,
)

PlatformUser = get_user_model()


class UserApiTests(APITestCase):
    """Test suite for central user management endpoints under Platform Owner authority."""

    def setUp(self):
        super().setUp()
        self.password = "SecureTestPass123!"

        # 1. Platform Owner 1
        self.owner = PlatformUser.objects.create_user(
            email="owner1@vibeconnect.internal",
            password=self.password,
            full_name="Platform Owner One",
            status=UserStatus.ACTIVE,
            is_active=True,
            is_platform_owner=True,
        )

        # 2. Platform Owner 2 (allows testing owner deactivation without hitting last-owner check)
        self.owner2 = PlatformUser.objects.create_user(
            email="owner2@vibeconnect.internal",
            password=self.password,
            full_name="Platform Owner Two",
            status=UserStatus.ACTIVE,
            is_active=True,
            is_platform_owner=True,
        )

        # 3. Organization & Tenant Admin (active user with console access, but not platform owner)
        self.org = Organization.objects.create(
            code="test-org",
            name="Test Organization",
            status=OrganizationStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )
        self.tenant_admin = PlatformUser.objects.create_user(
            email="tenant.admin@vibeconnect.internal",
            password=self.password,
            full_name="Tenant Admin",
            status=UserStatus.ACTIVE,
            is_active=True,
            is_platform_owner=False,
        )
        from apps.access_control.models import Role

        system_role, _ = Role.objects.get_or_create(
            organization=None,
            code="system_tenant_admin",
            defaults={
                "name": "Tenant Administrator",
                "description": "System role",
                "is_system_role": True,
                "status": "active",
            },
        )
        OrganizationMembership.objects.create(
            organization=self.org,
            user=self.tenant_admin,
            membership_type=MembershipType.TENANT_ADMIN,
            status=MembershipStatus.ACTIVE,
            role=system_role,
            joined_at=timezone.now(),
        )

        # 4. Regular non-owner user
        self.regular_user = PlatformUser.objects.create_user(
            email="regular@vibeconnect.internal",
            password=self.password,
            full_name="Regular User",
            status=UserStatus.ACTIVE,
            is_active=True,
            is_platform_owner=False,
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
        res = self.client.get("/api/v1/users/")
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_tenant_admin_denied_403(self):
        self._login(self.tenant_admin.email, self.password)
        res = self.client.get("/api/v1/users/")
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(res.json(), {"detail": "Access restricted to active platform owners in platform owner context."})

    def test_platform_owner_in_tenant_context_denied_403(self):
        self._login(self.owner.email, self.password)
        # Simulate active tenant context in session
        session = self.client.session
        session["active_context_type"] = "tenant"
        session["tenant_organization_id"] = str(uuid.uuid4())
        session.save()

        res = self.client.get("/api/v1/users/")
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_platform_owner_success_200(self):
        self._login(self.owner.email, self.password)
        res = self.client.get("/api/v1/users/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertIn("results", res.json())

    # 2. Listing, Filtering & Retrieving
    def test_list_users_filtering_by_status(self):
        self._login(self.owner.email, self.password)
        # Create a suspended user
        PlatformUser.objects.create_user(
            email="suspended@vibeconnect.internal",
            password=self.password,
            full_name="Suspended Guy",
            status=UserStatus.SUSPENDED,
            is_active=False,
            is_platform_owner=False,
        )

        res = self.client.get("/api/v1/users/?status=suspended")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        results = res.json()["results"]
        self.assertTrue(all(u["status"] == "suspended" for u in results))

    def test_list_users_search(self):
        self._login(self.owner.email, self.password)
        res = self.client.get("/api/v1/users/?search=regular@vibeconnect.internal")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        results = res.json()["results"]
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["email"], self.regular_user.email)

    def test_retrieve_user_detail_sanitized(self):
        self._login(self.owner.email, self.password)
        res = self.client.get(f"/api/v1/users/{self.regular_user.id}/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        data = res.json()
        self.assertEqual(data["email"], self.regular_user.email)
        self.assertNotIn("password", data)
        self.assertNotIn("session", data)
        self.assertNotIn("token", data)

    def test_retrieve_nonexistent_user_404(self):
        self._login(self.owner.email, self.password)
        res = self.client.get(f"/api/v1/users/{uuid.uuid4()}/")
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(res.json()["code"], "USER_NOT_FOUND")

    # 3. User Creation & Profile Update
    def test_create_user_success(self):
        self._login(self.owner.email, self.password)
        token = self._get_csrf_token()

        res = self.client.post(
            "/api/v1/users/",
            {"email": "new.hire@vibeconnect.internal", "full_name": "New Hire"},
            format="json",
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        data = res.json()
        self.assertEqual(data["email"], "new.hire@vibeconnect.internal")
        self.assertEqual(data["full_name"], "New Hire")
        self.assertEqual(data["status"], "active")
        self.assertFalse(data["is_platform_owner"])

        # Verify password is unusable
        created = PlatformUser.objects.get(email="new.hire@vibeconnect.internal")
        self.assertFalse(created.has_usable_password())

    def test_create_user_duplicate_email_409(self):
        self._login(self.owner.email, self.password)
        token = self._get_csrf_token()

        res = self.client.post(
            "/api/v1/users/",
            {"email": self.regular_user.email, "full_name": "Duplicate"},
            format="json",
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(res.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(res.json()["code"], "USER_ALREADY_EXISTS")

    def test_update_user_profile_full_name(self):
        self._login(self.owner.email, self.password)
        token = self._get_csrf_token()

        res = self.client.patch(
            f"/api/v1/users/{self.regular_user.id}/",
            {"full_name": "Updated Regular Name"},
            format="json",
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.json()["full_name"], "Updated Regular Name")

    # 4. User Lifecycle Actions
    def test_suspend_and_reactivate_user(self):
        self._login(self.owner.email, self.password)
        token = self._get_csrf_token()

        # Suspend
        sus_res = self.client.post(
            f"/api/v1/users/{self.regular_user.id}/suspend/",
            {"reason": "Security audit hold"},
            format="json",
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(sus_res.status_code, status.HTTP_200_OK)
        self.assertEqual(sus_res.json()["status"], "suspended")
        self.assertFalse(sus_res.json()["is_active"])

        # Reactivate
        react_res = self.client.post(
            f"/api/v1/users/{self.regular_user.id}/reactivate/",
            format="json",
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(react_res.status_code, status.HTTP_200_OK)
        self.assertEqual(react_res.json()["status"], "active")
        self.assertTrue(react_res.json()["is_active"])

    def test_suspend_last_platform_owner_blocked_400(self):
        self._login(self.owner.email, self.password)
        token = self._get_csrf_token()

        # Delete owner2 so owner1 is the sole active platform owner
        self.owner2.delete()

        res = self.client.post(
            f"/api/v1/users/{self.owner.id}/suspend/",
            {"reason": "Attempt to suspend sole owner"},
            format="json",
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(res.json()["code"], "CANNOT_DEACTIVATE_LAST_PLATFORM_OWNER")

    def test_disable_user_terminal_state(self):
        self._login(self.owner.email, self.password)
        token = self._get_csrf_token()

        # Disable regular user
        dis_res = self.client.post(
            f"/api/v1/users/{self.regular_user.id}/disable/",
            {"reason": "Offboarding"},
            format="json",
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(dis_res.status_code, status.HTTP_200_OK)
        self.assertEqual(dis_res.json()["status"], "disabled")
        self.assertFalse(dis_res.json()["is_active"])

        # Attempt to reactivate disabled user is rejected
        react_res = self.client.post(
            f"/api/v1/users/{self.regular_user.id}/reactivate/",
            format="json",
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(react_res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(react_res.json()["code"], "USER_DISABLED_TERMINAL")
