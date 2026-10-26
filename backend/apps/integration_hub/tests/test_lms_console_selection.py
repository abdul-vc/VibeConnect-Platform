"""Tests covering LMS Console Selection end-to-end integration across onboarding, assignment, and SSO.

Scenarios tested:
Scenario A: Platform Owner Tenant Onboarding provisions Tenant Admin with LMS Tenant Console (/org-admin).
Scenario B: Tenant Admin Member Onboarding invites Learner/Standard Member with LMS Normal User Console (/dashboard).
Scenario C: RBAC protection: Standard member is rejected from Tenant Console; Tenant Admin is permitted.
"""

from unittest.mock import MagicMock, patch
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.access_control.models import Role
from apps.assignments.constants import AccessState
from apps.assignments.models import (
    AssignmentStatus,
    UserProductAssignment,
)
from apps.assignments.services.exceptions import MembershipIneligibleError
from apps.assignments.services.assignment_services import assign_user_to_product
from apps.entitlements.models import EntitlementStatus, OrganizationProductEntitlement
from apps.identity.models import PlatformUser
from apps.integration_hub.models import (
    ConnectorInstance,
    ExternalTenantMapping,
    ExternalUserMapping,
    ExternalUserMappingStatus,
    InstanceStatus,
    IntegrationConnector,
)
from apps.integration_hub.sso_views import SsoLaunchView
from apps.invitations.models import InvitationStatus, UserInvitation
from apps.invitations.serializers import IssueInvitationSerializer
from apps.invitations.services import accept_invitation, issue_invitation
from apps.onboarding.models import OnboardingCaseStatus, OnboardingStep
from apps.onboarding.services import create_onboarding_case, transition_case_step
from apps.organizations.models import (
    MembershipStatus,
    MembershipType,
    Organization,
    OrganizationMembership,
    OrganizationStatus,
)
from apps.product_registry.models import Product, ProductStatus


TEST_LMS_SECRET = "test-secret-console-1234567890abcdef"
TEST_LMS_BACKEND_URL = "https://lms-api.vibesandbox.live"


class LmsConsoleSelectionTests(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.owner = PlatformUser.objects.create_superuser(
            email="owner@vibeconnect.internal",
            password="SecurePassword123!",
            full_name="Platform Owner",
        )
        self.org = Organization.objects.create(
            code="acme-lms",
            name="Acme LMS Tenant",
            status=OrganizationStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )
        self.admin_role = Role.objects.create(
            organization=self.org,
            code="tenant_admin",
            name="Tenant Administrator",
        )
        self.member_role = Role.objects.create(
            organization=self.org,
            code="learner",
            name="Learner",
        )
        self.lms_product = Product.objects.create(
            code="lms",
            name="Learning Management System",
            status=ProductStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )
        self.connector = IntegrationConnector.objects.create(
            code="lms",
            name="LMS Connector",
            product=self.lms_product,
        )
        self.instance = ConnectorInstance.objects.create(
            connector=self.connector,
            organization=self.org,
            status=InstanceStatus.ACTIVE,
        )
        self.sys_admin_role, _ = Role.objects.get_or_create(
            code="system_tenant_admin",
            is_system_role=True,
            defaults={"name": "System Tenant Admin"},
        )
        self.entitlement = OrganizationProductEntitlement.objects.create(
            organization=self.org,
            product=self.lms_product,
            status=EntitlementStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )
        self.tenant_mapping = ExternalTenantMapping.objects.create(
            instance=self.instance,
            organization=self.org,
            external_tenant_id=str(self.org.id),
        )

    def _mock_effective_access(self):
        return {
            "entitled_products": [
                {
                    "id": str(self.lms_product.id),
                    "code": "lms",
                    "access_state": AccessState.AVAILABLE,
                    "is_entitled": True,
                }
            ],
            "products": [],
        }

    # -------------------------------------------------------------------------
    # Scenario A: Platform Owner Tenant Onboarding -> Tenant Admin (Tenant Console)
    # -------------------------------------------------------------------------
    @override_settings(
        LMS_LAUNCH_GRANT_M2M_SECRET=TEST_LMS_SECRET,
        VIBECONNECT_LMS_BACKEND_URL=TEST_LMS_BACKEND_URL,
    )
    def test_scenario_a_tenant_onboarding_provisions_tenant_console(self):
        """Tenant onboarding automatically configures Tenant Admin for Tenant Console (/org-admin)."""
        # Step 1: Execute onboarding step machine
        case = create_onboarding_case(actor=self.owner)
        transition_case_step(
            case_id=case.id,
            target_step=OnboardingStep.ADMIN_SETUP,
            step_data={
                "organization_code": "beta-corp",
                "organization_name": "Beta Corp",
            },
            actor=self.owner,
        )
        transition_case_step(
            case_id=case.id,
            target_step=OnboardingStep.PLAN_SELECTION,
            step_data={
                "admin_email": "beta.admin@betacorp.internal",
                "admin_full_name": "Beta Admin",
            },
            actor=self.owner,
        )
        transition_case_step(
            case_id=case.id,
            target_step=OnboardingStep.PRODUCT_ENTITLEMENTS,
            step_data={
                "selected_product_ids": [str(self.lms_product.id)],
            },
            actor=self.owner,
        )
        transition_case_step(
            case_id=case.id,
            target_step=OnboardingStep.FEATURE_CEILINGS,
            step_data={},
            actor=self.owner,
        )
        transition_case_step(
            case_id=case.id,
            target_step=OnboardingStep.REVIEW_CONFIRM,
            step_data={},
            actor=self.owner,
        )
        case = transition_case_step(
            case_id=case.id,
            target_step=OnboardingStep.COMPLETED,
            step_data={},
            actor=self.owner,
        )

        beta_org = Organization.objects.get(code="beta-corp")
        invitation = UserInvitation.objects.get(organization=beta_org, email="beta.admin@betacorp.internal")
        
        # Verify invitation persisted lms_console="tenant_console"
        self.assertEqual(invitation.lms_console, "tenant_console")
        self.assertEqual(invitation.membership_type, MembershipType.TENANT_ADMIN)

        # Step 2: Accept invitation
        self.assertTrue(bool(case.initial_admin_activation_token))
        accept_result = accept_invitation(
            raw_token=case.initial_admin_activation_token,
            password="StrongPassword2026!",
            full_name="Beta Admin",
        )
        beta_admin_user = PlatformUser.objects.get(email="beta.admin@betacorp.internal")
        
        # Verify assignment was created with launch_console="tenant_console"
        assignment = UserProductAssignment.objects.get(
            organization=beta_org,
            user=beta_admin_user,
            product=self.lms_product,
        )
        self.assertEqual(assignment.launch_console, "tenant_console")

        # Step 3: Launch SSO and verify target_route is /org-admin
        beta_instance = ConnectorInstance.objects.create(
            connector=self.connector,
            organization=beta_org,
            status=InstanceStatus.ACTIVE,
        )
        ExternalTenantMapping.objects.create(
            instance=beta_instance,
            organization=beta_org,
            external_tenant_id=str(beta_org.id),
        )
        ExternalUserMapping.objects.create(
            instance=beta_instance,
            organization=beta_org,
            user=beta_admin_user,
            external_user_id=str(beta_admin_user.id),
            status=ExternalUserMappingStatus.ACTIVE,
        )

        from apps.integration_hub.models import ProvisioningJob, ProvisioningJobStatus
        ProvisioningJob.objects.filter(organization=beta_org).update(status=ProvisioningJobStatus.COMPLETED)

        with patch("apps.assignments.services.effective_access.compute_user_tenant_effective_access") as mock_eff, \
             patch("apps.integration_hub.sso_views.request_lms_launch_grant") as mock_grant, \
             patch("apps.integration_hub.provisioning_service.provision_user_to_lms") as mock_prov_u:

            mock_eff.return_value = {
                "entitled_products": [
                    {
                        "id": str(self.lms_product.id),
                        "code": "lms",
                        "access_state": AccessState.AVAILABLE,
                        "is_entitled": True,
                    }
                ],
                "products": [],
            }
            mock_grant.return_value = {
                "callback_url": "https://lms.vibesandbox.live/sso/vibeconnect/callback?code=beta-admin-code",
                "expires_in": 60,
                "context": "standard",
            }

            request = self.factory.post(
                "/api/v1/sso/launch/",
                {"product_id": str(self.lms_product.id), "organization_id": str(beta_org.id)},
                format="json",
            )
            force_authenticate(request, user=beta_admin_user)
            response = SsoLaunchView.as_view()(request)

            self.assertEqual(response.status_code, status.HTTP_200_OK)
            mock_grant.assert_called_once_with(
                external_tenant_id=str(beta_org.id),
                external_user_id=str(beta_admin_user.id),
                context="standard",
                target_route="/org-admin",
            )

    # -------------------------------------------------------------------------
    # Scenario B: Tenant Admin Member Onboarding -> Learner (Normal User Console)
    # -------------------------------------------------------------------------
    @override_settings(
        LMS_LAUNCH_GRANT_M2M_SECRET=TEST_LMS_SECRET,
        VIBECONNECT_LMS_BACKEND_URL=TEST_LMS_BACKEND_URL,
    )
    def test_scenario_b_member_onboarding_provisions_normal_user_console(self):
        """Member onboarding with normal_user_console launches into /dashboard with member role."""
        # Tenant admin issues invitation for standard member with normal_user_console
        admin_user = PlatformUser.objects.create(
            email="tenant.admin@acme.com",
            full_name="Acme Admin",
            is_active=True,
        )
        OrganizationMembership.objects.create(
            organization=self.org,
            user=admin_user,
            membership_type=MembershipType.TENANT_ADMIN,
            role=self.admin_role,
            status=MembershipStatus.ACTIVE,
            joined_at=timezone.now(),
        )

        invitation, raw_token = issue_invitation(
            organization=self.org,
            email="learner@acme.com",
            membership_type=MembershipType.MEMBER,
            role=None,
            product_ids=[str(self.lms_product.id)],
            lms_console="normal_user_console",
            invited_by=admin_user,
        )
        self.assertEqual(invitation.lms_console, "normal_user_console")

        # Learner accepts invitation
        accept_invitation(
            raw_token=raw_token,
            password="StrongPassword2026!",
            full_name="Acme Learner",
        )
        learner_user = PlatformUser.objects.get(email="learner@acme.com")

        # Verify assignment launch_console
        assignment = UserProductAssignment.objects.get(
            organization=self.org,
            user=learner_user,
            product=self.lms_product,
        )
        self.assertEqual(assignment.launch_console, "normal_user_console")

        ExternalUserMapping.objects.create(
            instance=self.instance,
            organization=self.org,
            user=learner_user,
            external_user_id=str(learner_user.id),
            status=ExternalUserMappingStatus.ACTIVE,
        )

        from apps.integration_hub.models import ProvisioningJob, ProvisioningJobStatus
        ProvisioningJob.objects.filter(organization=self.org).update(status=ProvisioningJobStatus.COMPLETED)

        # Launch SSO as learner
        with patch("apps.assignments.services.effective_access.compute_user_tenant_effective_access") as mock_eff, \
             patch("apps.integration_hub.sso_views.request_lms_launch_grant") as mock_grant, \
             patch("apps.integration_hub.provisioning_service.provision_user_to_lms") as mock_prov_u:

            mock_eff.return_value = self._mock_effective_access()
            mock_grant.return_value = {
                "callback_url": "https://lms.vibesandbox.live/sso/vibeconnect/callback?code=learner-code",
                "expires_in": 60,
                "context": "standard",
            }

            request = self.factory.post(
                "/api/v1/sso/launch/",
                {"product_id": str(self.lms_product.id), "organization_id": str(self.org.id)},
                format="json",
            )
            force_authenticate(request, user=learner_user)
            response = SsoLaunchView.as_view()(request)

            self.assertEqual(response.status_code, status.HTTP_200_OK)
            mock_grant.assert_called_once_with(
                external_tenant_id=str(self.org.id),
                external_user_id=str(learner_user.id),
                context="standard",
                target_route="/dashboard",
            )

    # -------------------------------------------------------------------------
    # Scenario C: RBAC protection: Standard member rejected from Tenant Console
    # -------------------------------------------------------------------------
    def test_scenario_c_serializer_rejects_tenant_console_for_standard_member(self):
        """IssueInvitationSerializer validates that standard members cannot request tenant_console."""
        serializer = IssueInvitationSerializer(data={
            "organization_id": str(self.org.id),
            "email": "hacker@acme.com",
            "membership_type": "member",
            "product_ids": [str(self.lms_product.id)],
            "lms_console": "tenant_console",
        })
        self.assertFalse(serializer.is_valid())
        self.assertIn("lms_console", serializer.errors)
        self.assertIn("Tenant Console requires", str(serializer.errors["lms_console"]))

    def test_scenario_c_serializer_permits_tenant_console_for_admin_role(self):
        """IssueInvitationSerializer permits tenant_console when role has administrative privileges."""
        serializer = IssueInvitationSerializer(data={
            "organization_id": str(self.org.id),
            "email": "subadmin@acme.com",
            "membership_type": "tenant_admin",
            "role_id": str(self.admin_role.id),
            "product_ids": [str(self.lms_product.id)],
            "lms_console": "tenant_console",
        })
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data.get("lms_console"), "tenant_console")

    def test_scenario_c_service_layer_blocks_unauthorized_tenant_console(self):
        """assign_user_to_product raises MembershipIneligibleError if non-admin requests tenant_console."""
        standard_user = PlatformUser.objects.create(
            email="standard@acme.com",
            full_name="Standard User",
            is_active=True,
        )
        membership = OrganizationMembership.objects.create(
            organization=self.org,
            user=standard_user,
            membership_type=MembershipType.MEMBER,
            role=None,
            status=MembershipStatus.ACTIVE,
            joined_at=timezone.now(),
        )

        with self.assertRaises(MembershipIneligibleError) as ctx:
            assign_user_to_product(
                user_id=standard_user.id,
                product_id=self.lms_product.id,
                organization_id=self.org.id,
                membership_id=membership.id,
                actor=self.owner,
                launch_console="tenant_console",
            )
        self.assertIn("Tenant Console requires administrative privileges", str(ctx.exception))

    @override_settings(
        LMS_LAUNCH_GRANT_M2M_SECRET=TEST_LMS_SECRET,
        VIBECONNECT_LMS_BACKEND_URL=TEST_LMS_BACKEND_URL,
    )
    def test_scenario_c_sso_launch_blocks_unauthorized_tenant_console_for_standard_member(self):
        """If a standard member's assignment has launch_console='tenant_console', SSO launch blocks access with 403."""
        user = PlatformUser.objects.create(
            email="forged@acme.com",
            full_name="Forged Access User",
            is_active=True,
        )
        membership = OrganizationMembership.objects.create(
            organization=self.org,
            user=user,
            membership_type=MembershipType.MEMBER,
            role=None,
            status=MembershipStatus.ACTIVE,
            joined_at=timezone.now(),
        )
        # Directly create assignment with launch_console='tenant_console'
        UserProductAssignment.objects.create(
            user=user,
            organization=self.org,
            membership=membership,
            product=self.lms_product,
            status=AssignmentStatus.ACTIVE,
            launch_console="tenant_console",
            created_by=self.owner,
            updated_by=self.owner,
        )

        with patch("apps.assignments.services.effective_access.compute_user_tenant_effective_access") as mock_eff:
            mock_eff.return_value = self._mock_effective_access()

            request = self.factory.post(
                "/api/v1/sso/launch/",
                {"product_id": str(self.lms_product.id), "organization_id": str(self.org.id)},
                format="json",
            )
            force_authenticate(request, user=user)
            response = SsoLaunchView.as_view()(request)
            self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
            self.assertEqual(response.data.get("error"), "FORBIDDEN_CONSOLE")

    @override_settings(
        LMS_LAUNCH_GRANT_M2M_SECRET=TEST_LMS_SECRET,
        VIBECONNECT_LMS_BACKEND_URL=TEST_LMS_BACKEND_URL,
    )
    def test_scenario_c_sso_launch_permits_tenant_console_for_tenant_admin(self):
        """When an authorized tenant admin launches LMS with tenant_console, SSO succeeds with /org-admin."""
        admin_user = PlatformUser.objects.create(
            email="authorized.admin@acme.com",
            full_name="Authorized Admin",
            is_active=True,
        )
        membership = OrganizationMembership.objects.create(
            organization=self.org,
            user=admin_user,
            membership_type=MembershipType.TENANT_ADMIN,
            role=self.admin_role,
            status=MembershipStatus.ACTIVE,
            joined_at=timezone.now(),
        )
        UserProductAssignment.objects.create(
            user=admin_user,
            organization=self.org,
            membership=membership,
            product=self.lms_product,
            status=AssignmentStatus.ACTIVE,
            launch_console="tenant_console",
            created_by=self.owner,
            updated_by=self.owner,
        )
        ExternalUserMapping.objects.create(
            instance=self.instance,
            organization=self.org,
            user=admin_user,
            external_user_id=str(admin_user.id),
            status=ExternalUserMappingStatus.ACTIVE,
        )

        with patch("apps.assignments.services.effective_access.compute_user_tenant_effective_access") as mock_eff, \
             patch("apps.integration_hub.sso_views.request_lms_launch_grant") as mock_grant, \
             patch("apps.integration_hub.provisioning_service.provision_user_to_lms") as mock_prov_u:

            mock_eff.return_value = self._mock_effective_access()
            mock_grant.return_value = {
                "callback_url": "https://lms.vibesandbox.live/sso/vibeconnect/callback?code=admin-code",
                "expires_in": 60,
                "context": "standard",
            }

            request = self.factory.post(
                "/api/v1/sso/launch/",
                {"product_id": str(self.lms_product.id), "organization_id": str(self.org.id)},
                format="json",
            )
            force_authenticate(request, user=admin_user)
            response = SsoLaunchView.as_view()(request)

            self.assertEqual(response.status_code, status.HTTP_200_OK)
            mock_grant.assert_called_once_with(
                external_tenant_id=str(self.org.id),
                external_user_id=str(admin_user.id),
                context="standard",
                target_route="/org-admin",
            )
