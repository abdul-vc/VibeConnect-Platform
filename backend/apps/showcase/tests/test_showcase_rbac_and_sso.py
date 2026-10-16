"""Comprehensive RBAC and SSO Tests for Product Showcase – VibeConnect.

Validates that:
- Super Admin (platform owner) can access Product Showcase endpoints and initiate demo launches.
- Tenant Admin and normal users are denied (HTTP 403) across all showcase endpoints even on direct API access.
- Tenant-scoped permissions do not grant platform-wide showcase access.
- Authorized Trinity showcase launch generates single-use authorization code and redirect URL.
- Legitimate tenant workflows and entitlements remain operational.
"""

from __future__ import annotations

import uuid
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.assignments.models import AssignmentStatus, UserModuleAssignment, UserProductAssignment
from apps.entitlements.models import EntitlementStatus, OrganizationProductEntitlement
from apps.identity.models import UserStatus
from apps.integration_hub.models import IntegrationConnector, ConnectorInstance, InstanceStatus, ProductSsoClient
from apps.organizations.models import MembershipStatus, MembershipType, Organization, OrganizationMembership
from apps.product_registry.models import CatalogStatus, Product, ProductModule, ProductStatus
from apps.showcase.models import ProductDemoEnvironment, ProductLaunchConfig, ProductShowcaseProfile, ShowcaseVisibility
from apps.showcase.services import ProductShowcaseService

User = get_user_model()


class ShowcaseRbacAndSsoTests(TestCase):
    def setUp(self):
        self.client = APIClient()

        # 1. Super Admin (Platform Owner)
        self.super_admin = User.objects.create_user(
            email="superadmin@vc.test",
            password="Password123!",
            full_name="Super Admin",
            is_platform_owner=True,
            is_staff=True,
            status=UserStatus.ACTIVE,
        )

        # 2. Demo Organization
        from apps.organizations.models import OrganizationStatus
        self.org = Organization.objects.create(
            name="Demo Organization",
            code="demo-org",
            status=OrganizationStatus.ACTIVE,
            created_by=self.super_admin,
            updated_by=self.super_admin,
        )

        # 3. Tenant Admin
        self.tenant_admin = User.objects.create_user(
            email="tenant_admin@vc.test",
            password="Password123!",
            full_name="Tenant Admin",
            is_platform_owner=False,
            is_staff=False,
            status=UserStatus.ACTIVE,
        )
        from apps.access_control.models import Role, RoleStatus
        self.admin_role = Role.objects.create(
            organization=self.org,
            name="Admin Role",
            code="admin_role",
            status=RoleStatus.ACTIVE,
            created_by=self.super_admin,
            updated_by=self.super_admin,
        )
        self.tenant_admin_membership = OrganizationMembership.objects.create(
            organization=self.org,
            user=self.tenant_admin,
            membership_type=MembershipType.TENANT_ADMIN,
            role=self.admin_role,
            status=MembershipStatus.ACTIVE,
            joined_at=timezone.now(),
        )

        # 4. Normal Tenant Member
        self.tenant_member = User.objects.create_user(
            email="member@vc.test",
            password="Password123!",
            full_name="Normal Member",
            is_platform_owner=False,
            is_staff=False,
            status=UserStatus.ACTIVE,
        )
        self.tenant_member_membership = OrganizationMembership.objects.create(
            organization=self.org,
            user=self.tenant_member,
            membership_type=MembershipType.MEMBER,
            status=MembershipStatus.ACTIVE,
            joined_at=timezone.now(),
        )

        # 5. Super Admin membership in demo org
        self.super_admin_membership = OrganizationMembership.objects.create(
            organization=self.org,
            user=self.super_admin,
            membership_type=MembershipType.MEMBER,
            status=MembershipStatus.ACTIVE,
            joined_at=timezone.now(),
        )

        # 6. Trinity Product & Module
        self.product = Product.objects.create(
            code="workshop-trinity",
            name="WORKSHOP (Trinity)",
            status=ProductStatus.ACTIVE,
            created_by=self.super_admin,
            updated_by=self.super_admin,
        )
        self.module = ProductModule.objects.create(
            product=self.product,
            code="intake-mgmt",
            name="Intake Management",
            status=CatalogStatus.ACTIVE,
            created_by=self.super_admin,
            updated_by=self.super_admin,
        )

        # 7. Org Entitlement for Trinity
        self.org_entitlement = OrganizationProductEntitlement.objects.create(
            organization=self.org,
            product=self.product,
            status=EntitlementStatus.ACTIVE,
            created_by=self.super_admin,
            updated_by=self.super_admin,
        )

        # 8. User Assignments
        for u, m in [(self.super_admin, self.super_admin_membership), (self.tenant_member, self.tenant_member_membership)]:
            assign = UserProductAssignment.objects.create(
                organization=self.org,
                user=u,
                product=self.product,
                membership=m,
                status=AssignmentStatus.ACTIVE,
                created_by=self.super_admin,
                updated_by=self.super_admin,
            )
            UserModuleAssignment.objects.create(
                assignment=assign,
                module=self.module,
                is_enabled=True,
            )

        # 9. SSO Client & Connector Instance
        self.sso_client = ProductSsoClient.objects.create(
            product=self.product,
            client_identifier="trinity-workshop-app",
            audience="trinity-workshop-app",
            callback_uri="http://localhost:8080/sso/callback",
            is_active=True,
        )
        from apps.integration_hub.models import ConnectorStatus
        self.connector = IntegrationConnector.objects.create(
            product=self.product,
            name="Trinity Connector",
            code="trinity_connector",
            status=ConnectorStatus.ACTIVE,
        )
        self.connector_instance = ConnectorInstance.objects.create(
            connector=self.connector,
            organization=self.org,
            status=InstanceStatus.ACTIVE,
            label="Trinity Connector",
            config={},
        )

        # 10. Showcase Profile, Environment, and Launch Config
        self.profile = ProductShowcaseProfile.objects.create(
            product=self.product,
            tagline="Trinity Workshop Showcase",
            visibility=ShowcaseVisibility.PUBLISHED,
            created_by=self.super_admin,
            updated_by=self.super_admin,
        )
        self.demo_env = ProductDemoEnvironment.objects.create(
            product=self.product,
            name="Trinity Workshop Local Demo",
            base_url="http://localhost:8080",
            is_active=True,
            created_by=self.super_admin,
            updated_by=self.super_admin,
        )
        self.launch_config = ProductLaunchConfig.objects.create(
            product=self.product,
            profile=self.profile,
            launch_mode=ProductLaunchConfig.LaunchMode.SSO_DIRECT,
            target_environment=self.demo_env,
            policy={
                "demo_organization_code": "demo-org",
                "demo_user_email": "superadmin@vc.test",
            },
            created_by=self.super_admin,
            updated_by=self.super_admin,
        )

    def test_super_admin_can_access_showcase_profiles_and_config(self):
        self.client.force_authenticate(user=self.super_admin)

        resp = self.client.get("/api/v1/showcase/profiles/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        resp = self.client.get(f"/api/v1/showcase/profiles/{self.profile.id}/launchability/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertTrue(resp.data["launchable"])

        resp = self.client.get(f"/api/v1/showcase/profiles/{self.profile.id}/launch-config/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        resp = self.client.get("/api/v1/showcase/present/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

    def test_tenant_admin_cannot_access_showcase(self):
        self.client.force_authenticate(user=self.tenant_admin)

        # Direct API calls to showcase endpoints must return 403
        resp = self.client.get("/api/v1/showcase/profiles/")
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

        resp = self.client.get(f"/api/v1/showcase/profiles/{self.profile.id}/")
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

        resp = self.client.get(f"/api/v1/showcase/profiles/{self.profile.id}/launchability/")
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

        resp = self.client.post(f"/api/v1/showcase/profiles/{self.profile.id}/launch-demo/")
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

        resp = self.client.get(f"/api/v1/showcase/profiles/{self.profile.id}/launch-config/")
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

        resp = self.client.get("/api/v1/showcase/present/")
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_normal_user_cannot_access_showcase(self):
        self.client.force_authenticate(user=self.tenant_member)

        resp = self.client.get("/api/v1/showcase/profiles/")
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

        resp = self.client.post(f"/api/v1/showcase/profiles/{self.profile.id}/launch-demo/")
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

        resp = self.client.get("/api/v1/showcase/present/")
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_unauthenticated_user_denied(self):
        self.client.force_authenticate(user=None)

        resp = self.client.get("/api/v1/showcase/profiles/")
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

        resp = self.client.post(f"/api/v1/showcase/profiles/{self.profile.id}/launch-demo/")
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_super_admin_can_initiate_trinity_launch(self):
        self.client.force_authenticate(user=self.super_admin)

        resp = self.client.post(f"/api/v1/showcase/profiles/{self.profile.id}/launch-demo/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn("redirect_url", resp.data)
        self.assertIn("code=", resp.data["redirect_url"])
        self.assertIn("state=", resp.data["redirect_url"])
        self.assertEqual(resp.data["demo_user"], "superadmin@vc.test")
        self.assertEqual(resp.data["demo_organization"], "demo-org")

    def test_tenant_legitimate_launch_workflow_preserved(self):
        self.client.force_authenticate(user=self.tenant_member)

        # Member can initiate launch through standard tenant SSO launcher endpoint
        payload = {
            "product_code": "workshop-trinity",
            "organization_id": str(self.org.id),
        }
        resp = self.client.post("/api/v1/sso/launch/", data=payload, format="json")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn("redirect_url", resp.data)
        self.assertIn("code=", resp.data["redirect_url"])
        self.assertIn("state=", resp.data["redirect_url"])
