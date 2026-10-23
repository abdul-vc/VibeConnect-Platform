"""Unit and API tests for Phase 3B: Tenant Onboarding Wizard."""

from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase

from apps.auditlog.models import AuditAction, AuditLog
from apps.identity.models import UserStatus
from apps.onboarding.models import (
    OnboardingCaseStatus,
    OnboardingStep,
    TenantOnboardingCase,
)
from apps.onboarding.services import (
    InvalidStepTransitionError,
    OnboardingCaseConflictError,
    OnboardingValidationError,
    create_onboarding_case,
    transition_case_step,
)
from apps.organizations.models import Organization, OrganizationMembership, OrganizationStatus
from apps.plans.models import Plan, PlanPrice, PlanVersion, PlanVersionStatus

PlatformUser = get_user_model()


class TenantOnboardingCaseDomainTests(APITestCase):
    def setUp(self):
        self.platform_owner = PlatformUser.objects.create(
            email="po_tester@vibeconnect.internal",
            full_name="Platform Owner Tester",
            is_platform_owner=True,
            status=UserStatus.ACTIVE,
            is_active=True,
        )
        self.regular_user = PlatformUser.objects.create(
            email="regular@example.com",
            full_name="Regular User",
            is_platform_owner=False,
            status=UserStatus.ACTIVE,
            is_active=True,
        )
        # Create an active plan version
        self.plan = Plan.objects.create(
            code="starter_plan",
            name="Starter Plan",
            created_by=self.platform_owner,
            updated_by=self.platform_owner,
        )
        from django.utils import timezone
        self.plan_version = PlanVersion.objects.create(
            plan=self.plan,
            version=1,
            status=PlanVersionStatus.ACTIVE,
            activated_at=timezone.now(),
            created_by=self.platform_owner,
            updated_by=self.platform_owner,
        )
        self.plan_price = PlanPrice.objects.create(
            plan_version=self.plan_version,
            currency="USD",
            billing_interval="monthly",
            amount=49.00,
            created_by=self.platform_owner,
            updated_by=self.platform_owner,
        )

    def test_permission_guard_requires_platform_owner(self):
        """Only platform owners can initiate an onboarding case."""
        with self.assertRaises(OnboardingValidationError):
            create_onboarding_case(actor=self.regular_user)

    def test_full_happy_path_onboarding(self):
        """Test happy path progression from organization profile to completion."""
        case = create_onboarding_case(actor=self.platform_owner)
        self.assertEqual(case.current_step, OnboardingStep.ORGANIZATION_PROFILE)
        self.assertEqual(case.status, OnboardingCaseStatus.IN_PROGRESS)

        # Step 1 -> Step 2
        case = transition_case_step(
            case_id=case.id,
            target_step=OnboardingStep.ADMIN_SETUP,
            step_data={
                "organization_code": "alpha-corp",
                "organization_name": "Alpha Corp",
                "organization_description": "Alpha corporate division",
            },
            actor=self.platform_owner,
        )
        self.assertEqual(case.current_step, OnboardingStep.ADMIN_SETUP)
        self.assertEqual(case.organization_code, "alpha-corp")

        # Step 2 -> Step 3
        case = transition_case_step(
            case_id=case.id,
            target_step=OnboardingStep.PLAN_SELECTION,
            step_data={
                "admin_email": "admin@alphacorp.internal",
                "admin_full_name": "Alice Alpha",
            },
            actor=self.platform_owner,
        )
        self.assertEqual(case.current_step, OnboardingStep.PLAN_SELECTION)

        # Step 3 -> Step 4
        case = transition_case_step(
            case_id=case.id,
            target_step=OnboardingStep.REVIEW_CONFIRM,
            step_data={
                "plan_version_id": str(self.plan_version.id),
                "plan_price_id": str(self.plan_price.id),
                "is_trial": True,
            },
            actor=self.platform_owner,
        )
        self.assertEqual(case.current_step, OnboardingStep.REVIEW_CONFIRM)

        # Step 4 -> Completed
        case = transition_case_step(
            case_id=case.id,
            target_step=OnboardingStep.COMPLETED,
            step_data={},
            actor=self.platform_owner,
        )
        self.assertEqual(case.current_step, OnboardingStep.COMPLETED)
        self.assertEqual(case.status, OnboardingCaseStatus.COMPLETED)
        self.assertIsNotNone(case.created_organization)

        # Verify Organization created and Admin invitation issued (Phase 3C)
        org = Organization.objects.get(code="alpha-corp")
        self.assertEqual(org.status, OrganizationStatus.ACTIVE)
        from apps.invitations.models import UserInvitation
        invitation = UserInvitation.objects.get(organization=org, email="admin@alphacorp.internal")
        self.assertEqual(invitation.membership_type, "tenant_admin")
        self.assertEqual(invitation.status, "pending")

        # Verify Audit Log written
        audit_events = AuditLog.objects.filter(action=AuditAction.ONBOARDING_STEP_TRANSITIONED, target_id=case.id)
        self.assertEqual(audit_events.count(), 4)

    def test_resume_after_interrupt_preserves_state(self):
        """Case can be saved mid-flight and resumed without state loss."""
        case = create_onboarding_case(actor=self.platform_owner)
        transition_case_step(
            case_id=case.id,
            target_step=OnboardingStep.ADMIN_SETUP,
            step_data={
                "organization_code": "resumable-org",
                "organization_name": "Resumable Organization",
            },
            actor=self.platform_owner,
        )

        # Fetch case afresh from DB (simulating page reload)
        fresh_case = TenantOnboardingCase.objects.get(id=case.id)
        self.assertEqual(fresh_case.current_step, OnboardingStep.ADMIN_SETUP)
        self.assertEqual(fresh_case.organization_code, "resumable-org")

        # Resume progression to Plan Selection
        advanced_case = transition_case_step(
            case_id=fresh_case.id,
            target_step=OnboardingStep.PLAN_SELECTION,
            step_data={"admin_email": "admin@resumable.internal"},
            actor=self.platform_owner,
        )
        self.assertEqual(advanced_case.current_step, OnboardingStep.PLAN_SELECTION)

    def test_invalid_step_jump_rejected(self):
        """Reject invalid state machine transitions."""
        case = create_onboarding_case(actor=self.platform_owner)
        with self.assertRaises(InvalidStepTransitionError):
            transition_case_step(
                case_id=case.id,
                target_step=OnboardingStep.COMPLETED,
                step_data={},
                actor=self.platform_owner,
            )

    def test_duplicate_organization_code_conflict(self):
        """Enforces uniqueness of organization code during step transition."""
        Organization.objects.create(
            code="existing-code",
            name="Existing Company",
            status=OrganizationStatus.ACTIVE,
            created_by=self.platform_owner,
            updated_by=self.platform_owner,
        )

        case = create_onboarding_case(actor=self.platform_owner)
        with self.assertRaises(OnboardingCaseConflictError):
            transition_case_step(
                case_id=case.id,
                target_step=OnboardingStep.ADMIN_SETUP,
                step_data={
                    "organization_code": "existing-code",
                    "organization_name": "Conflict Co",
                },
                actor=self.platform_owner,
            )

    def test_provisioning_failure_atomic_rollback_and_resumable_status(self):
        """Failure during provisioning rolls back org and sets PROVISIONING_FAILED status."""
        from unittest.mock import patch
        from apps.onboarding.services import OnboardingValidationError

        case = create_onboarding_case(actor=self.platform_owner)
        transition_case_step(
            case_id=case.id,
            target_step=OnboardingStep.ADMIN_SETUP,
            step_data={"organization_code": "fail-org", "organization_name": "Fail Org"},
            actor=self.platform_owner,
        )
        transition_case_step(
            case_id=case.id,
            target_step=OnboardingStep.PLAN_SELECTION,
            step_data={"admin_email": "admin@fail.internal"},
            actor=self.platform_owner,
        )
        transition_case_step(
            case_id=case.id,
            target_step=OnboardingStep.REVIEW_CONFIRM,
            step_data={"is_trial": True},
            actor=self.platform_owner,
        )

        with patch("apps.invitations.services.issue_invitation", side_effect=RuntimeError("Invitation service down")):
            with self.assertRaises(OnboardingValidationError):
                transition_case_step(
                    case_id=case.id,
                    target_step=OnboardingStep.COMPLETED,
                    step_data={},
                    actor=self.platform_owner,
                )

        # Confirm atomic rollback: organization was NOT created
        self.assertFalse(Organization.objects.filter(code="fail-org").exists())
        # Confirm case is in PROVISIONING_FAILED status and resumable
        case.refresh_from_db()
        self.assertEqual(case.status, OnboardingCaseStatus.PROVISIONING_FAILED)
        self.assertIsNone(case.created_organization)

    def test_provisioning_non_trial_calls_create_active_subscription(self):
        """Non-trial onboarding provisioning creates an active subscription directly."""
        from unittest.mock import patch

        case = create_onboarding_case(actor=self.platform_owner)
        transition_case_step(
            case_id=case.id,
            target_step=OnboardingStep.ADMIN_SETUP,
            step_data={"organization_code": "paid-org", "organization_name": "Paid Org"},
            actor=self.platform_owner,
        )
        transition_case_step(
            case_id=case.id,
            target_step=OnboardingStep.PLAN_SELECTION,
            step_data={"admin_email": "admin@paid.internal"},
            actor=self.platform_owner,
        )
        transition_case_step(
            case_id=case.id,
            target_step=OnboardingStep.REVIEW_CONFIRM,
            step_data={
                "plan_version_id": str(self.plan_version.id),
                "plan_price_id": str(self.plan_price.id),
                "is_trial": False,
            },
            actor=self.platform_owner,
        )

        with patch("apps.onboarding.services.create_active_subscription") as mock_active_sub, \
             patch("apps.onboarding.services.start_subscription_trial") as mock_trial_sub, \
             patch("apps.invitations.services.issue_invitation"):
            completed_case = transition_case_step(
                case_id=case.id,
                target_step=OnboardingStep.COMPLETED,
                step_data={},
                actor=self.platform_owner,
            )

        self.assertEqual(completed_case.status, OnboardingCaseStatus.COMPLETED)
        mock_active_sub.assert_called_once()
        mock_trial_sub.assert_not_called()

    def test_full_6_step_onboarding_with_entitlements_and_ceilings(self):
        """Test complete 6-step tenant onboarding sequence with product entitlements and console feature ceilings."""
        from apps.product_registry.models import Product, ProductStatus
        from apps.entitlements.models import OrganizationProductEntitlement, EntitlementStatus
        from apps.access_control.models import OrganizationConsoleModulePolicy, OrganizationPermissionCeiling

        p1 = Product.objects.create(
            code="test_lms_prod",
            name="Test LMS Product",
            status=ProductStatus.ACTIVE,
            created_by=self.platform_owner,
            updated_by=self.platform_owner,
        )
        p2 = Product.objects.create(
            code="test_crm_prod",
            name="Test CRM Product",
            status=ProductStatus.ACTIVE,
            created_by=self.platform_owner,
            updated_by=self.platform_owner,
        )

        case = create_onboarding_case(actor=self.platform_owner)

        # 1. Organization Profile
        case = transition_case_step(
            case_id=case.id,
            target_step=OnboardingStep.ADMIN_SETUP,
            step_data={
                "organization_code": "six-step-corp",
                "organization_name": "Six Step Corp",
            },
            actor=self.platform_owner,
        )

        # 2. Administrator
        case = transition_case_step(
            case_id=case.id,
            target_step=OnboardingStep.PLAN_SELECTION,
            step_data={
                "admin_email": "admin@sixstep.internal",
                "admin_full_name": "Sam Six",
            },
            actor=self.platform_owner,
        )

        # 3. Plan & Pricing
        case = transition_case_step(
            case_id=case.id,
            target_step=OnboardingStep.PRODUCT_ENTITLEMENTS,
            step_data={
                "plan_version_id": str(self.plan_version.id),
                "plan_price_id": str(self.plan_price.id),
                "is_trial": True,
            },
            actor=self.platform_owner,
        )
        self.assertEqual(case.current_step, OnboardingStep.PRODUCT_ENTITLEMENTS)

        # 4. Product Entitlements
        case = transition_case_step(
            case_id=case.id,
            target_step=OnboardingStep.FEATURE_CEILINGS,
            step_data={
                "selected_product_ids": [str(p1.id), str(p2.id)],
            },
            actor=self.platform_owner,
        )
        self.assertEqual(case.current_step, OnboardingStep.FEATURE_CEILINGS)
        self.assertEqual(len(case.selected_product_ids), 2)

        # 5. Console Feature Ceilings
        case = transition_case_step(
            case_id=case.id,
            target_step=OnboardingStep.REVIEW_CONFIRM,
            step_data={
                "feature_ceilings": {
                    "modules": {"tenant_roles": True, "tenant_branding": False},
                    "permissions": {"roles.manage": False},
                },
            },
            actor=self.platform_owner,
        )
        self.assertEqual(case.current_step, OnboardingStep.REVIEW_CONFIRM)

        # 6. Execute & Complete Provisioning
        case = transition_case_step(
            case_id=case.id,
            target_step=OnboardingStep.COMPLETED,
            step_data={},
            actor=self.platform_owner,
        )
        self.assertEqual(case.status, OnboardingCaseStatus.COMPLETED)
        org = Organization.objects.get(code="six-step-corp")

        # Verify product entitlements were created and activated
        entitlements = OrganizationProductEntitlement.objects.filter(
            organization=org,
            status=EntitlementStatus.ACTIVE,
        )
        self.assertEqual(entitlements.count(), 2)
        entitled_pids = {str(e.product_id) for e in entitlements}
        self.assertIn(str(p1.id), entitled_pids)
        self.assertIn(str(p2.id), entitled_pids)

        # Verify custom feature ceilings were applied
        branding_pol = OrganizationConsoleModulePolicy.objects.filter(
            organization=org,
            console_module__key="tenant_branding",
        ).first()
        self.assertIsNotNone(branding_pol)
        self.assertFalse(branding_pol.is_enabled)

        manage_ceiling = OrganizationPermissionCeiling.objects.filter(
            organization=org,
            permission__key="roles.manage",
        ).first()
        self.assertIsNotNone(manage_ceiling)
        self.assertFalse(manage_ceiling.is_allowed)

        # 7. Idempotency verification: Calling transition on completed case returns case without error
        idempotent_case = transition_case_step(
            case_id=case.id,
            target_step=OnboardingStep.COMPLETED,
            step_data={},
            actor=self.platform_owner,
        )
        self.assertEqual(idempotent_case.id, case.id)
        self.assertEqual(idempotent_case.status, OnboardingCaseStatus.COMPLETED)


