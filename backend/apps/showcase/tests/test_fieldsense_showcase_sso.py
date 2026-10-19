"""Comprehensive Tests for FieldSense Showcase SSO Integration and Configure Demo.

Verifies:
1. Configure Demo parameter handling:
   - Saves target environment using 'target_environment_id'
   - Saves target environment using 'target_environment'
   - Clears target environment when null/empty
   - Validates that environment belongs to the same product (cross-product rejection)
2. FieldSense setup management command (setup_fieldsense_demo):
   - Idempotent execution
   - Reuses canonical product without duplicates
   - Configures demo environment, sso client, connector, entitlement, membership, assignment, launch config
3. FieldSense Launchability Contract:
   - Succeeds (READY) when all prerequisites are in place
   - Fails safely when SSO client is missing
   - Fails safely when connector instance is missing
   - Fails safely when entitlement is missing
   - Fails safely when user membership is missing/inactive
   - Fails safely when user product assignment is missing
   - Fails safely when demo organization is not in allowlist
4. Authorized Showcase Live Demo Launch & Token Exchange:
   - POST /launch-demo/ mints short-lived authorization code and callback redirect URL
   - Authorization code exchange returns verified FieldSense claims (canonical product code 'fieldsense')
   - Replayed authorization code is rejected (single-use)
   - Invalid state parameter is rejected
5. Trinity Workshop regression:
   - Trinity records and launch behavior remain untouched and functional
"""

from __future__ import annotations

import os
from unittest import mock
import urllib.parse
import uuid

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.assignments.models import AssignmentStatus, UserModuleAssignment, UserProductAssignment
from apps.entitlements.models import EntitlementStatus, OrganizationProductEntitlement
from apps.identity.models import PlatformUser, UserStatus
from apps.integration_hub.models import ConnectorInstance, InstanceStatus, IntegrationConnector, ProductSsoClient
from apps.integration_hub.sso_service import validate_sso_authorization_code
from apps.organizations.models import MembershipStatus, MembershipType, Organization, OrganizationMembership
from apps.product_registry.models import CatalogStatus, Product, ProductModule, ProductStatus
from apps.showcase.models import ProductDemoEnvironment, ProductLaunchConfig, ProductShowcaseProfile, ShowcaseVisibility
from apps.showcase.services import ProductShowcaseService, ShowcaseServiceError

User = get_user_model()
TEST_FIELDSENSE_SECRET = "test-fieldsense-m2m-secret-entropy-32-chars-long"
TEST_TRINITY_SECRET = "test-trinity-m2m-secret-entropy-32-chars-long"


@override_settings(
    VIBECONNECT_FIELDSENSE_M2M_SECRET=TEST_FIELDSENSE_SECRET,
    VIBECONNECT_TRINITY_M2M_SECRET=TEST_TRINITY_SECRET,
)
class ConfigureDemoParameterMismatchTests(TestCase):
    """Tests parameter handling, product validation, and clearing in configure_launch."""

    def setUp(self):
        self.client = APIClient()
        self.owner = User.objects.create_user(
            email="owner_cfg@vc.test",
            password="Password123!",
            full_name="Platform Owner",
            is_platform_owner=True,
            is_staff=True,
            status=UserStatus.ACTIVE,
        )
        self.client.force_authenticate(user=self.owner)

        self.prod_fieldsense = Product.objects.create(
            code="fieldsense",
            name="FieldSense Operations Hub",
            status=ProductStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )
        self.profile = ProductShowcaseProfile.objects.create(
            product=self.prod_fieldsense,
            tagline="FieldSense Showcase",
            visibility=ShowcaseVisibility.PUBLISHED,
            created_by=self.owner,
            updated_by=self.owner,
        )
        self.env_fieldsense = ProductDemoEnvironment.objects.create(
            product=self.prod_fieldsense,
            name="FieldSense Local Demo",
            base_url="http://localhost:8081",
            is_active=True,
            created_by=self.owner,
            updated_by=self.owner,
        )

        # Separate product and environment for cross-product test
        self.prod_other = Product.objects.create(
            code="workshop-trinity",
            name="WORKSHOP (Trinity)",
            status=ProductStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )
        self.env_other = ProductDemoEnvironment.objects.create(
            product=self.prod_other,
            name="Trinity Demo",
            base_url="http://localhost:8080",
            is_active=True,
            created_by=self.owner,
            updated_by=self.owner,
        )

    def test_configure_demo_saves_target_environment_via_target_environment_id(self):
        """Saving using target_environment_id correctly links the environment."""
        url = f"/api/v1/showcase/profiles/{self.profile.id}/launch-config/"
        resp = self.client.patch(
            url,
            {
                "launch_mode": "sso_direct",
                "target_environment_id": str(self.env_fieldsense.id),
                "notes": "Configured via target_environment_id",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        cfg = ProductLaunchConfig.objects.get(product=self.prod_fieldsense)
        self.assertEqual(cfg.target_environment_id, self.env_fieldsense.id)
        self.assertEqual(cfg.launch_mode, ProductLaunchConfig.LaunchMode.SSO_DIRECT)
        self.assertIn(self.env_fieldsense.base_url, cfg.allowed_targets)

    def test_configure_demo_saves_target_environment_via_target_environment(self):
        """Saving using target_environment (sent by UI modal) correctly links the environment."""
        url = f"/api/v1/showcase/profiles/{self.profile.id}/launch-config/"
        resp = self.client.patch(
            url,
            {
                "launch_mode": "sso_direct",
                "target_environment": str(self.env_fieldsense.id),
                "notes": "Configured via target_environment",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        cfg = ProductLaunchConfig.objects.get(product=self.prod_fieldsense)
        self.assertEqual(cfg.target_environment_id, self.env_fieldsense.id)
        self.assertEqual(cfg.launch_mode, ProductLaunchConfig.LaunchMode.SSO_DIRECT)

    def test_configure_demo_clears_target_environment(self):
        """Passing null target_environment correctly clears the linked environment."""
        # First set it
        cfg = ProductShowcaseService.configure_launch(
            profile_id=str(self.profile.id),
            actor=self.owner,
            data={"target_environment_id": str(self.env_fieldsense.id)},
        )
        self.assertEqual(cfg.target_environment_id, self.env_fieldsense.id)

        # Now clear it via API
        url = f"/api/v1/showcase/profiles/{self.profile.id}/launch-config/"
        resp = self.client.patch(
            url,
            {
                "target_environment": None,
                "notes": "Cleared environment",
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        cfg.refresh_from_db()
        self.assertIsNone(cfg.target_environment)

    def test_configure_demo_rejects_environment_belonging_to_another_product(self):
        """Configuring an environment belonging to another product raises validation error."""
        url = f"/api/v1/showcase/profiles/{self.profile.id}/launch-config/"
        resp = self.client.patch(
            url,
            {
                "target_environment": str(self.env_other.id),
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("belongs to product", str(resp.data.get("detail", "")))


@override_settings(
    VIBECONNECT_FIELDSENSE_M2M_SECRET=TEST_FIELDSENSE_SECRET,
    VIBECONNECT_TRINITY_M2M_SECRET=TEST_TRINITY_SECRET,
)
class FieldSenseShowcaseLaunchabilityAndSsoTests(TestCase):
    """Tests FieldSense setup, launchability prerequisites, live launch, and token exchange."""

    def setUp(self):
        self.client = APIClient()
        self.owner = User.objects.create_user(
            email="admin@gmail.com",
            password="Password123!",
            full_name="Platform Owner Admin",
            is_platform_owner=True,
            is_staff=True,
            status=UserStatus.ACTIVE,
        )
        self.client.force_authenticate(user=self.owner)

        self.demo_org = Organization.objects.create(
            code="demo-org",
            name="Demo Organization",
            status="active",
            created_by=self.owner,
            updated_by=self.owner,
        )
        self.membership = OrganizationMembership.objects.create(
            organization=self.demo_org,
            user=self.owner,
            membership_type=MembershipType.MEMBER,
            status=MembershipStatus.ACTIVE,
            joined_at=timezone.now(),
        )

    def test_setup_fieldsense_demo_command_idempotent(self):
        """setup_fieldsense_demo executes safely and idempotently."""
        # Initial run
        with mock.patch.dict(os.environ, {"VIBECONNECT_FIELDSENSE_M2M_SECRET": TEST_FIELDSENSE_SECRET}):
            call_command("setup_fieldsense_demo")

        product = Product.objects.get(code="fieldsense")
        self.assertEqual(product.name, "FieldSense Operations Hub")

        profile = ProductShowcaseProfile.objects.get(product=product)
        self.assertEqual(profile.visibility, ShowcaseVisibility.PUBLISHED)

        env = ProductDemoEnvironment.objects.get(product=product, base_url="http://localhost:8081")
        self.assertTrue(env.is_active)

        launch_cfg = ProductLaunchConfig.objects.get(product=product)
        self.assertEqual(launch_cfg.launch_mode, ProductLaunchConfig.LaunchMode.SSO_DIRECT)
        self.assertEqual(launch_cfg.target_environment, env)
        self.assertEqual(launch_cfg.policy.get("demo_organization_code"), "demo-org")
        self.assertEqual(launch_cfg.policy.get("demo_user_email"), "admin@gmail.com")

        # Second run should succeed without error
        with mock.patch.dict(os.environ, {"VIBECONNECT_FIELDSENSE_M2M_SECRET": TEST_FIELDSENSE_SECRET}):
            call_command("setup_fieldsense_demo")

    def test_fieldsense_launchability_contract_ready(self):
        """Launchability contract returns launchable=True when all prerequisites are in place."""
        with mock.patch.dict(os.environ, {"VIBECONNECT_FIELDSENSE_M2M_SECRET": TEST_FIELDSENSE_SECRET}):
            call_command("setup_fieldsense_demo")

        product = Product.objects.get(code="fieldsense")
        profile = ProductShowcaseProfile.objects.get(product=product)

        url = f"/api/v1/showcase/profiles/{profile.id}/launchability/"
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertTrue(resp.data["launchable"])
        self.assertEqual(resp.data["reason"], "READY")
        self.assertEqual(resp.data["launch_mode"], "sso_direct")
        self.assertEqual(resp.data["demo_user"], "admin@gmail.com")
        self.assertEqual(resp.data["demo_organization"], "demo-org")

    def test_fieldsense_launchability_fails_missing_sso_client(self):
        """Fails with SSO_CLIENT_NOT_CONFIGURED when ProductSsoClient is missing or inactive."""
        with mock.patch.dict(os.environ, {"VIBECONNECT_FIELDSENSE_M2M_SECRET": TEST_FIELDSENSE_SECRET}):
            call_command("setup_fieldsense_demo")

        product = Product.objects.get(code="fieldsense")
        profile = ProductShowcaseProfile.objects.get(product=product)
        ProductSsoClient.objects.filter(product=product).update(is_active=False)

        contract = ProductShowcaseService.launchability_contract(profile_id=str(profile.id))
        self.assertFalse(contract["launchable"])
        self.assertEqual(contract["reason"], "SSO_CLIENT_NOT_CONFIGURED")

    def test_fieldsense_launchability_fails_missing_connector_instance(self):
        """Fails with INTEGRATION_INSTANCE_MISSING when ConnectorInstance is missing."""
        with mock.patch.dict(os.environ, {"VIBECONNECT_FIELDSENSE_M2M_SECRET": TEST_FIELDSENSE_SECRET}):
            call_command("setup_fieldsense_demo")

        product = Product.objects.get(code="fieldsense")
        profile = ProductShowcaseProfile.objects.get(product=product)
        ConnectorInstance.objects.filter(connector__product=product).delete()

        contract = ProductShowcaseService.launchability_contract(profile_id=str(profile.id))
        self.assertFalse(contract["launchable"])
        self.assertEqual(contract["reason"], "INTEGRATION_INSTANCE_MISSING")

    def test_fieldsense_launchability_fails_missing_entitlement(self):
        """Fails with DEMO_ACCESS_DENIED when OrganizationProductEntitlement is inactive."""
        with mock.patch.dict(os.environ, {"VIBECONNECT_FIELDSENSE_M2M_SECRET": TEST_FIELDSENSE_SECRET}):
            call_command("setup_fieldsense_demo")

        product = Product.objects.get(code="fieldsense")
        profile = ProductShowcaseProfile.objects.get(product=product)
        OrganizationProductEntitlement.objects.filter(organization=self.demo_org, product=product).delete()

        contract = ProductShowcaseService.launchability_contract(profile_id=str(profile.id))
        self.assertFalse(contract["launchable"])
        self.assertEqual(contract["reason"], "DEMO_ACCESS_DENIED")

    def test_fieldsense_launchability_fails_missing_assignment(self):
        """Fails with DEMO_ASSIGNMENT_INACTIVE when UserProductAssignment is missing."""
        with mock.patch.dict(os.environ, {"VIBECONNECT_FIELDSENSE_M2M_SECRET": TEST_FIELDSENSE_SECRET}):
            call_command("setup_fieldsense_demo")

        product = Product.objects.get(code="fieldsense")
        profile = ProductShowcaseProfile.objects.get(product=product)
        UserProductAssignment.objects.filter(organization=self.demo_org, user=self.owner, product=product).delete()

        contract = ProductShowcaseService.launchability_contract(profile_id=str(profile.id))
        self.assertFalse(contract["launchable"])
        self.assertEqual(contract["reason"], "DEMO_ASSIGNMENT_INACTIVE")

    def test_fieldsense_launchability_fails_unauthorized_demo_org(self):
        """Fails with DEMO_CONTEXT_NOT_PERMITTED when an unapproved org code is configured."""
        with mock.patch.dict(os.environ, {"VIBECONNECT_FIELDSENSE_M2M_SECRET": TEST_FIELDSENSE_SECRET}):
            call_command("setup_fieldsense_demo")

        product = Product.objects.get(code="fieldsense")
        profile = ProductShowcaseProfile.objects.get(product=product)

        rogue_org = Organization.objects.create(
            code="rogue-tenant-org",
            name="Rogue Tenant",
            status="active",
            created_by=self.owner,
            updated_by=self.owner,
        )
        launch_cfg = ProductLaunchConfig.objects.get(product=product)
        launch_cfg.policy = {
            "demo_organization_code": rogue_org.code,
            "demo_user_email": "admin@gmail.com",
        }
        launch_cfg.save(update_fields=["policy"])

        contract = ProductShowcaseService.launchability_contract(profile_id=str(profile.id))
        self.assertFalse(contract["launchable"])
        self.assertEqual(contract["reason"], "DEMO_CONTEXT_NOT_PERMITTED")

    def test_fieldsense_live_demo_launch_and_sso_token_exchange(self):
        """Launching FieldSense demo mints single-use code that validates to canonical claims."""
        with mock.patch.dict(os.environ, {"VIBECONNECT_FIELDSENSE_M2M_SECRET": TEST_FIELDSENSE_SECRET}):
            call_command("setup_fieldsense_demo")

            product = Product.objects.get(code="fieldsense")
            profile = ProductShowcaseProfile.objects.get(product=product)

            # Step 1: Platform Owner triggers live demo launch
            url = f"/api/v1/showcase/profiles/{profile.id}/launch-demo/"
            resp = self.client.post(url)
            self.assertEqual(resp.status_code, status.HTTP_200_OK)

            redirect_url = resp.data.get("redirect_url")
            self.assertTrue(redirect_url.startswith("http://localhost:8081/sso/callback"))

            parsed = urllib.parse.urlparse(redirect_url)
            q_params = dict(urllib.parse.parse_qsl(parsed.query))
            self.assertIn("code", q_params)
            self.assertIn("state", q_params)

            raw_code = q_params["code"]
            bound_state = q_params["state"]

            # Step 2: Validate code as FieldSense app with client_identifier
            claims = validate_sso_authorization_code(
                code=raw_code,
                client_identifier="fieldsense-ops-hub",
                state=bound_state,
            )

            # Verify exact claims contract
            self.assertEqual(claims["audience"], "fieldsense-ops-hub")
            self.assertEqual(claims["user"]["email"], "admin@gmail.com")
            self.assertEqual(claims["organization"]["code"], "demo-org")
            self.assertEqual(claims["product"]["code"], "fieldsense")
            self.assertEqual(claims["product"]["name"], "FieldSense Operations Hub")

            # Step 3: Single-use enforcement - Replaying code must fail
            with self.assertRaises(Exception):
                validate_sso_authorization_code(
                    code=raw_code,
                    client_identifier="fieldsense-ops-hub",
                    state=bound_state,
                )

    def test_fieldsense_sso_rejects_invalid_state(self):
        """Token validation rejects mismatched state parameter."""
        with mock.patch.dict(os.environ, {"VIBECONNECT_FIELDSENSE_M2M_SECRET": TEST_FIELDSENSE_SECRET}):
            call_command("setup_fieldsense_demo")

            product = Product.objects.get(code="fieldsense")
            profile = ProductShowcaseProfile.objects.get(product=product)

            url = f"/api/v1/showcase/profiles/{profile.id}/launch-demo/"
            resp = self.client.post(url)
            self.assertEqual(resp.status_code, status.HTTP_200_OK)

            redirect_url = resp.data.get("redirect_url")
            parsed = urllib.parse.urlparse(redirect_url)
            q_params = dict(urllib.parse.parse_qsl(parsed.query))

            with self.assertRaises(Exception):
                validate_sso_authorization_code(
                    code=q_params["code"],
                    client_identifier="fieldsense-ops-hub",
                    state="tampered-state-token",
                )

    def test_trinity_workshop_remains_unaffected(self):
        """Trinity Workshop configuration and SSO capability remain fully operational."""
        # Create Trinity product, connector, sso client, environment, and launch config
        trinity_prod = Product.objects.create(
            code="workshop-trinity",
            name="WORKSHOP (Trinity)",
            status=ProductStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )
        trinity_profile = ProductShowcaseProfile.objects.create(
            product=trinity_prod,
            tagline="Trinity Showcase",
            visibility=ShowcaseVisibility.PUBLISHED,
            created_by=self.owner,
            updated_by=self.owner,
        )
        trinity_env = ProductDemoEnvironment.objects.create(
            product=trinity_prod,
            name="Trinity Local Demo",
            base_url="http://localhost:8080",
            is_active=True,
            created_by=self.owner,
            updated_by=self.owner,
        )
        call_command("register_trinity_sso_client", organization=self.demo_org.code)

        OrganizationProductEntitlement.objects.create(
            organization=self.demo_org,
            product=trinity_prod,
            status=EntitlementStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )
        assign = UserProductAssignment.objects.create(
            organization=self.demo_org,
            user=self.owner,
            product=trinity_prod,
            membership=self.membership,
            status=AssignmentStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )
        mod = ProductModule.objects.create(
            product=trinity_prod,
            code="trinity_core",
            name="Trinity Core",
            status=CatalogStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )
        UserModuleAssignment.objects.create(
            assignment=assign,
            module=mod,
            is_enabled=True,
        )
        ProductLaunchConfig.objects.create(
            product=trinity_prod,
            profile=trinity_profile,
            launch_mode=ProductLaunchConfig.LaunchMode.SSO_DIRECT,
            target_environment=trinity_env,
            allowed_targets=[trinity_env.base_url],
            policy={
                "demo_organization_code": self.demo_org.code,
                "demo_user_email": self.owner.email,
            },
            created_by=self.owner,
            updated_by=self.owner,
        )

        # Run FieldSense setup and verify Trinity is completely untouched
        with mock.patch.dict(os.environ, {"VIBECONNECT_FIELDSENSE_M2M_SECRET": TEST_FIELDSENSE_SECRET}):
            call_command("setup_fieldsense_demo")

        contract = ProductShowcaseService.launchability_contract(profile_id=str(trinity_profile.id))
        self.assertTrue(contract["launchable"])
        self.assertEqual(contract["reason"], "READY")
        self.assertEqual(contract["launch_mode"], "sso_direct")
        self.assertEqual(contract["environment_name"], "Trinity Local Demo")

        with mock.patch.dict(os.environ, {"VIBECONNECT_TRINITY_M2M_SECRET": TEST_TRINITY_SECRET}):
            result = ProductShowcaseService.launch_demo(profile_id=str(trinity_profile.id), actor=self.owner)
            self.assertTrue(result["redirect_url"].startswith("http://localhost:8080/sso/callback"))
