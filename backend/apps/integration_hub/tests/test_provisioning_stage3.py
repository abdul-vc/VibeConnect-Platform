"""Comprehensive test suite for Automatic Lifecycle Provisioning Triggers (Phase 5C-3 Stage 3).

Covers all 18 mandatory requirements:
- Tenant:
  1. LMS entitlement activation queues provisioning.
  2. Repeated activation does not create duplicate jobs/effects.
  3. Non-LMS entitlement does not trigger LMS provisioning.
  4. Organization deactivation triggers expected LMS synchronization.
  5. Failed provisioning creates expected failure state.
- User:
  6. LMS product assignment queues user provisioning.
  7. Repeated assignment event is idempotent.
  8. Non-LMS assignment does not trigger LMS provisioning.
  9. Assignment suspension propagates correctly.
  10. Assignment reactivation propagates correctly.
  11. Assignment revocation propagates correctly.
- Ordering:
  12. User provisioning depends safely on tenant provisioning.
  13. User job cannot incorrectly provision into an unmapped tenant.
  14. Retry after tenant dependency resolution succeeds.
- Transaction safety:
  15. Rolled-back transaction does not leave a false provisioning job/event.
  16. Successful transaction exposes the provisioning job/event correctly.
- Security:
  17. No credentials/secrets in jobs/events.
  18. Cross-tenant user cannot trigger provisioning into another organization.
"""

from datetime import timedelta
from decimal import Decimal
import unittest.mock as mock
import uuid

from django.contrib.auth import get_user_model
from django.db import transaction
from django.test import TestCase, TransactionTestCase
from django.utils import timezone

from apps.assignments.models import AssignmentStatus, UserProductAssignment
from apps.assignments.services.assignment_services import (
    assign_user_to_product,
    reactivate_user_assignment,
    revoke_user_assignment,
    suspend_user_assignment,
)
from apps.entitlements.models import EntitlementStatus, OrganizationProductEntitlement
from apps.integration_hub.lifecycle_service import (
    handle_tenant_deactivated_or_suspended,
    handle_tenant_lms_entitlement_activated,
    handle_user_lms_assignment_active,
    handle_user_lms_assignment_reactivated,
    handle_user_lms_assignment_revoked,
    handle_user_lms_assignment_suspended,
    is_lms_product,
)
from apps.integration_hub.lms_connector import LmsConnectorError
from apps.integration_hub.models import (
    ConnectorInstance,
    EventStatus,
    ExternalTenantMapping,
    ExternalUserMapping,
    ExternalUserMappingStatus,
    FailureStatus,
    FailureType,
    IntegrationConnector,
    IntegrationEvent,
    IntegrationFailure,
    ProvisioningAction,
    ProvisioningJob,
    ProvisioningJobStatus,
)
from apps.integration_hub.provisioning_service import (
    execute_provisioning_job,
    get_or_create_lms_connector_instance,
)
from apps.organizations.membership_services import (
    LmsRoleDemotionUnsupportedError,
    update_membership_type,
)
from apps.organizations.models import MembershipStatus, MembershipType, Organization, OrganizationMembership, OrganizationStatus
from apps.organizations.services import retire_organization, suspend_organization
from apps.plans.models import BillingInterval, Plan, PlanCurrency, PlanPrice, PlanProduct, PlanQuota, PlanVersion, PlanVersionStatus, QuotaLimitType, QuotaResetPeriod, QuotaScope
from apps.product_registry.models import CatalogStatus, Product, ProductModule, ProductStatus
from apps.subscriptions.models import (
    OrganizationSubscription,
    SubscriptionProductEntitlement,
    SubscriptionQuotaEntitlement,
    SubscriptionStatus,
)

User = get_user_model()


class Stage3TestBase:
    """Helper methods for Stage 3 lifecycle trigger tests."""

    def create_user(self, email=None, is_platform_owner=False):
        unique = uuid.uuid4().hex[:8]
        return User.objects.create_user(
            email=email or f"user_{unique}@test.internal",
            password="TestPassword123!",
            full_name=f"Test User {unique}",
            is_platform_owner=is_platform_owner,
            is_active=True,
        )

    def create_org(self, code=None, status=OrganizationStatus.ACTIVE, creator=None):
        unique = uuid.uuid4().hex[:6]
        c = creator or self.owner
        return Organization.objects.create(
            code=code or f"org_{unique}",
            name=f"Org {unique}",
            status=status,
            created_by=c,
            updated_by=c,
        )

    def create_lms_product(self):
        p, _ = Product.objects.get_or_create(
            code="lms",
            defaults={
                "name": "Learning Management System",
                "status": ProductStatus.ACTIVE,
                "created_by": self.owner,
                "updated_by": self.owner,
            },
        )
        return p

    def create_crm_product(self):
        p, _ = Product.objects.get_or_create(
            code="crm",
            defaults={
                "name": "Customer Relationship Management",
                "status": ProductStatus.ACTIVE,
                "created_by": self.owner,
                "updated_by": self.owner,
            },
        )
        return p

    def setup_lms_connector(self):
        lms_prod = self.create_lms_product()
        connector, _ = IntegrationConnector.objects.get_or_create(
            code="lms_connector",
            defaults={
                "name": "LMS Connector",
                "product": lms_prod,
                "version": "1.0.0",
            },
        )
        return connector

    def setup_subscription_and_seat_pool(self, org, product):
        """Sets up a valid subscription with temporal seat quota for assign_user_to_product."""
        plan, _ = Plan.objects.get_or_create(
            code=f"plan_{product.code}_{uuid.uuid4().hex[:6]}",
            defaults={
                "name": f"Plan for {product.name}",
                "is_public": True,
                "created_by": self.owner,
                "updated_by": self.owner,
            },
        )
        pv, _ = PlanVersion.objects.get_or_create(
            plan=plan,
            version=1,
            defaults={
                "status": PlanVersionStatus.ACTIVE,
                "activated_at": timezone.now(),
                "created_by": self.owner,
                "updated_by": self.owner,
            },
        )
        plan_prod, _ = PlanProduct.objects.get_or_create(
            plan_version=pv,
            product=product,
            defaults={
                "created_by": self.owner,
            },
        )
        price, _ = PlanPrice.objects.get_or_create(
            plan_version=pv,
            currency=PlanCurrency.USD,
            billing_interval=BillingInterval.MONTHLY,
            defaults={
                "amount": Decimal("100.00"),
                "created_by": self.owner,
                "updated_by": self.owner,
            },
        )
        plan_quota, _ = PlanQuota.objects.get_or_create(
            plan_version=pv,
            quota_key="seats",
            defaults={
                "name": "Plan Seats",
                "scope": QuotaScope.PLAN,
                "limit_type": QuotaLimitType.NUMERIC,
                "limit_value": 50,
                "unit": "seats",
                "reset_period": QuotaResetPeriod.MONTHLY,
                "is_hard_limit": True,
                "created_by": self.owner,
                "updated_by": self.owner,
            },
        )
        now = timezone.now()
        sub = OrganizationSubscription.objects.create(
            organization=org,
            plan_version=pv,
            plan_price=price,
            plan_code_snapshot=plan.code,
            plan_name_snapshot=plan.name,
            version_number_snapshot=pv.version,
            billing_interval=price.billing_interval,
            currency=price.currency,
            amount=price.amount,
            started_as_trial=False,
            status=SubscriptionStatus.ACTIVE,
            current_period_start=now - timedelta(days=1),
            current_period_end=now + timedelta(days=30),
            created_by=self.owner,
            updated_by=self.owner,
        )
        SubscriptionProductEntitlement.objects.create(
            subscription=sub,
            organization=org,
            product=product,
            plan_product=plan_prod,
            product_code_snapshot=product.code,
            product_name_snapshot=product.name,
        )
        SubscriptionQuotaEntitlement.objects.create(
            subscription=sub,
            organization=org,
            plan_quota=plan_quota,
            quota_key="seats",
            name="Plan Seats",
            scope=QuotaScope.PLAN,
            limit_type=QuotaLimitType.NUMERIC,
            limit_value=50,
            unit="seats",
            reset_period=QuotaResetPeriod.MONTHLY,
            is_hard_limit=True,
        )
        return sub


class Stage3LifecycleTriggerTests(TestCase, Stage3TestBase):
    """Automated tests for Stage 3 automatic lifecycle triggers."""

    def setUp(self):
        self.owner = self.create_user(is_platform_owner=True)
        self.lms_product = self.create_lms_product()
        self.crm_product = self.create_crm_product()
        self.connector = self.setup_lms_connector()
        self.org = self.create_org()
        self.member_user = self.create_user()
        self.membership = OrganizationMembership.objects.create(
            organization=self.org,
            user=self.member_user,
            membership_type=MembershipType.MEMBER,
            status=MembershipStatus.ACTIVE,
            joined_at=timezone.now(),
        )

    # -------------------------------------------------------------------------
    # 1. LMS entitlement activation queues provisioning
    # -------------------------------------------------------------------------
    @mock.patch("apps.integration_hub.provisioning_service.LmsConnectorClient.provision_tenant")
    def test_01_lms_entitlement_activation_queues_provisioning(self, mock_prov_tenant):
        mock_prov_tenant.return_value = {
            "status": "success",
            "lms_organization_id": 101,
            "action_taken": "created",
        }
        with self.captureOnCommitCallbacks(execute=True):
            entitlement = OrganizationProductEntitlement.objects.create(
                organization=self.org,
                product=self.lms_product,
                status=EntitlementStatus.ACTIVE,
                created_by=self.owner,
                updated_by=self.owner,
            )

        job = ProvisioningJob.objects.filter(
            organization=self.org,
            user=None,
            action=ProvisioningAction.PROVISION,
        ).first()
        self.assertIsNotNone(job, "A tenant ProvisioningJob must be enqueued.")
        self.assertEqual(job.status, ProvisioningJobStatus.COMPLETED)
        self.assertTrue(
            ExternalTenantMapping.objects.filter(organization=self.org, external_tenant_id="101").exists()
        )

    # -------------------------------------------------------------------------
    # 2. Repeated activation does not create duplicate jobs/effects
    # -------------------------------------------------------------------------
    def test_02_repeated_activation_does_not_create_duplicate_jobs(self):
        job1 = handle_tenant_lms_entitlement_activated(self.org, actor=self.owner)
        self.assertIsNotNone(job1)

        job2 = handle_tenant_lms_entitlement_activated(self.org, actor=self.owner)
        self.assertEqual(job1.id, job2.id, "Second call must return the existing queued job.")

        job_count = ProvisioningJob.objects.filter(
            organization=self.org,
            user=None,
            action=ProvisioningAction.PROVISION,
        ).count()
        self.assertEqual(job_count, 1, "Exactly one job must exist for repeated activations.")

    # -------------------------------------------------------------------------
    # 3. Non-LMS entitlement does not trigger LMS provisioning
    # -------------------------------------------------------------------------
    def test_03_non_lms_entitlement_does_not_trigger_lms_provisioning(self):
        entitlement = OrganizationProductEntitlement.objects.create(
            organization=self.org,
            product=self.crm_product,
            status=EntitlementStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )
        self.assertFalse(is_lms_product(entitlement.product))
        jobs = ProvisioningJob.objects.filter(organization=self.org)
        self.assertEqual(jobs.count(), 0, "Non-LMS entitlement must NOT create any ProvisioningJob.")

    # -------------------------------------------------------------------------
    # 4. Organization deactivation triggers expected LMS synchronization
    # -------------------------------------------------------------------------
    @mock.patch("apps.integration_hub.provisioning_service.LmsConnectorClient.provision_tenant")
    def test_04_organization_deactivation_triggers_lms_synchronization(self, mock_prov_tenant):
        mock_prov_tenant.return_value = {
            "status": "success",
            "lms_organization_id": 101,
            "action_taken": "updated",
        }
        # First map the tenant
        instance = get_or_create_lms_connector_instance(self.org)
        ExternalTenantMapping.objects.create(
            instance=instance,
            organization=self.org,
            external_tenant_id="101",
        )

        with self.captureOnCommitCallbacks(execute=True):
            suspend_organization(
                organization_id=self.org.id,
                actor=self.owner,
                reason="Temporary compliance review",
            )

        job = ProvisioningJob.objects.filter(
            organization=self.org,
            user=None,
            action=ProvisioningAction.UPDATE,
        ).first()
        self.assertIsNotNone(job)
        self.assertEqual(job.context.get("target_status"), "Suspended")
        self.assertEqual(job.status, ProvisioningJobStatus.COMPLETED)

    # -------------------------------------------------------------------------
    # 5. Failed provisioning creates expected failure state
    # -------------------------------------------------------------------------
    @mock.patch("apps.integration_hub.provisioning_service.LmsConnectorClient.provision_tenant")
    def test_05_failed_provisioning_creates_expected_failure_state(self, mock_prov_tenant):
        mock_prov_tenant.side_effect = LmsConnectorError(
            message="Upstream gateway timeout",
            failure_code="UPSTREAM_TIMEOUT",
            status_code=504,
            is_retryable=True,
        )
        job = handle_tenant_lms_entitlement_activated(self.org, actor=self.owner)
        with self.assertRaises(LmsConnectorError):
            execute_provisioning_job(job)

        job.refresh_from_db()
        self.assertEqual(job.status, ProvisioningJobStatus.RETRY_SCHEDULED)
        failure = IntegrationFailure.objects.filter(job=job).first()
        self.assertIsNotNone(failure)
        self.assertEqual(failure.failure_code, "UPSTREAM_TIMEOUT")
        self.assertEqual(failure.failure_type, FailureType.TRANSIENT)
        self.assertEqual(failure.status, FailureStatus.RETRY_SCHEDULED)

    # -------------------------------------------------------------------------
    # 6. LMS product assignment queues user provisioning
    # -------------------------------------------------------------------------
    @mock.patch("apps.integration_hub.provisioning_service.LmsConnectorClient.provision_user")
    @mock.patch("apps.integration_hub.provisioning_service.LmsConnectorClient.provision_tenant")
    def test_06_lms_product_assignment_queues_user_provisioning(self, mock_prov_tenant, mock_prov_user):
        mock_prov_tenant.return_value = {"status": "success", "lms_organization_id": 201}
        mock_prov_user.return_value = {"status": "success", "lms_user_id": 501, "action_taken": "created"}

        self.setup_subscription_and_seat_pool(self.org, self.lms_product)

        with self.captureOnCommitCallbacks(execute=True):
            assignment = assign_user_to_product(
                organization_id=self.org.id,
                user_id=self.member_user.id,
                product_id=self.lms_product.id,
                actor=self.owner,
            )

        job = ProvisioningJob.objects.filter(
            organization=self.org,
            user=self.member_user,
            action=ProvisioningAction.PROVISION,
        ).first()
        self.assertIsNotNone(job, "A user ProvisioningJob must be enqueued.")
        self.assertEqual(job.status, ProvisioningJobStatus.COMPLETED)
        self.assertTrue(
            ExternalUserMapping.objects.filter(user=self.member_user, external_user_id="501").exists()
        )

    # -------------------------------------------------------------------------
    # 7. Repeated assignment event is idempotent
    # -------------------------------------------------------------------------
    def test_07_repeated_assignment_event_is_idempotent(self):
        assignment = mock.MagicMock(
            id=uuid.uuid4(),
            organization=self.org,
            organization_id=self.org.id,
            user=self.member_user,
            user_id=self.member_user.id,
            product=self.lms_product,
            status=AssignmentStatus.ACTIVE,
        )
        job1 = handle_user_lms_assignment_active(assignment, actor=self.owner)
        self.assertIsNotNone(job1)

        job2 = handle_user_lms_assignment_active(assignment, actor=self.owner)
        self.assertEqual(job1.id, job2.id, "Repeated event must reuse the same active job.")

        job_count = ProvisioningJob.objects.filter(
            organization=self.org,
            user=self.member_user,
            action=ProvisioningAction.PROVISION,
        ).count()
        self.assertEqual(job_count, 1)

    # -------------------------------------------------------------------------
    # 8. Non-LMS assignment does not trigger LMS provisioning
    # -------------------------------------------------------------------------
    def test_08_non_lms_assignment_does_not_trigger_lms_provisioning(self):
        self.setup_subscription_and_seat_pool(self.org, self.crm_product)
        assignment = assign_user_to_product(
            organization_id=self.org.id,
            user_id=self.member_user.id,
            product_id=self.crm_product.id,
            actor=self.owner,
        )
        jobs = ProvisioningJob.objects.filter(organization=self.org, user=self.member_user)
        self.assertEqual(jobs.count(), 0, "CRM assignment must not queue any LMS provisioning job.")

    # -------------------------------------------------------------------------
    # 9. Assignment suspension propagates correctly
    # -------------------------------------------------------------------------
    @mock.patch("apps.integration_hub.provisioning_service.LmsConnectorClient.provision_user")
    @mock.patch("apps.integration_hub.provisioning_service.LmsConnectorClient.provision_tenant")
    def test_09_assignment_suspension_propagates_correctly(self, mock_prov_tenant, mock_prov_user):
        mock_prov_tenant.return_value = {"status": "success", "lms_organization_id": 201}
        mock_prov_user.return_value = {"status": "success", "lms_user_id": 501, "action_taken": "updated"}

        self.setup_subscription_and_seat_pool(self.org, self.lms_product)
        assignment = assign_user_to_product(
            organization_id=self.org.id,
            user_id=self.member_user.id,
            product_id=self.lms_product.id,
            actor=self.owner,
        )

        with self.captureOnCommitCallbacks(execute=True):
            suspend_user_assignment(
                assignment_id=assignment.id,
                reason="Temporary suspension for audit",
                actor=self.owner,
            )

        suspend_job = ProvisioningJob.objects.filter(
            organization=self.org,
            user=self.member_user,
            action=ProvisioningAction.UPDATE,
            context__action_type="suspend",
        ).first()
        self.assertIsNotNone(suspend_job)
        self.assertFalse(suspend_job.context.get("is_active"))
        self.assertEqual(suspend_job.status, ProvisioningJobStatus.COMPLETED)

        # Check mapping status in VC
        mapping = ExternalUserMapping.objects.filter(user=self.member_user).first()
        self.assertEqual(mapping.status, ExternalUserMappingStatus.SUSPENDED)

    # -------------------------------------------------------------------------
    # 10. Assignment reactivation propagates correctly
    # -------------------------------------------------------------------------
    @mock.patch("apps.integration_hub.provisioning_service.LmsConnectorClient.provision_user")
    @mock.patch("apps.integration_hub.provisioning_service.LmsConnectorClient.provision_tenant")
    def test_10_assignment_reactivation_propagates_correctly(self, mock_prov_tenant, mock_prov_user):
        mock_prov_tenant.return_value = {"status": "success", "lms_organization_id": 201}
        mock_prov_user.return_value = {"status": "success", "lms_user_id": 501, "action_taken": "updated"}

        self.setup_subscription_and_seat_pool(self.org, self.lms_product)
        assignment = assign_user_to_product(
            organization_id=self.org.id,
            user_id=self.member_user.id,
            product_id=self.lms_product.id,
            actor=self.owner,
        )
        suspend_user_assignment(
            assignment_id=assignment.id,
            reason="Suspended for review",
            actor=self.owner,
        )

        with self.captureOnCommitCallbacks(execute=True):
            reactivate_user_assignment(
                assignment_id=assignment.id,
                actor=self.owner,
            )

        reactivate_job = ProvisioningJob.objects.filter(
            organization=self.org,
            user=self.member_user,
            action=ProvisioningAction.UPDATE,
            context__action_type="reactivate",
        ).first()
        self.assertIsNotNone(reactivate_job)
        self.assertTrue(reactivate_job.context.get("is_active"))
        self.assertEqual(reactivate_job.status, ProvisioningJobStatus.COMPLETED)

        mapping = ExternalUserMapping.objects.filter(user=self.member_user).first()
        self.assertEqual(mapping.status, ExternalUserMappingStatus.ACTIVE)

    # -------------------------------------------------------------------------
    # 11. Assignment revocation propagates correctly
    # -------------------------------------------------------------------------
    @mock.patch("apps.integration_hub.provisioning_service.LmsConnectorClient.provision_user")
    @mock.patch("apps.integration_hub.provisioning_service.LmsConnectorClient.provision_tenant")
    def test_11_assignment_revocation_propagates_correctly(self, mock_prov_tenant, mock_prov_user):
        mock_prov_tenant.return_value = {"status": "success", "lms_organization_id": 201}
        mock_prov_user.return_value = {"status": "success", "lms_user_id": 501, "action_taken": "deprovisioned"}

        self.setup_subscription_and_seat_pool(self.org, self.lms_product)
        assignment = assign_user_to_product(
            organization_id=self.org.id,
            user_id=self.member_user.id,
            product_id=self.lms_product.id,
            actor=self.owner,
        )

        with self.captureOnCommitCallbacks(execute=True):
            revoke_user_assignment(
                assignment_id=assignment.id,
                reason="Employee role changed",
                actor=self.owner,
            )

        revoke_job = ProvisioningJob.objects.filter(
            organization=self.org,
            user=self.member_user,
            action=ProvisioningAction.DEPROVISION,
        ).first()
        self.assertIsNotNone(revoke_job)
        self.assertFalse(revoke_job.context.get("is_active"))
        self.assertEqual(revoke_job.status, ProvisioningJobStatus.COMPLETED)

    # -------------------------------------------------------------------------
    # 12. User provisioning depends safely on tenant provisioning
    # -------------------------------------------------------------------------
    @mock.patch("apps.integration_hub.provisioning_service.LmsConnectorClient.provision_user")
    @mock.patch("apps.integration_hub.provisioning_service.LmsConnectorClient.provision_tenant")
    def test_12_user_provisioning_depends_safely_on_tenant_provisioning(self, mock_prov_tenant, mock_prov_user):
        call_order = []

        def fake_tenant(payload):
            call_order.append("tenant")
            return {"status": "success", "lms_organization_id": 301}

        def fake_user(payload):
            call_order.append("user")
            return {"status": "success", "lms_user_id": 601}

        mock_prov_tenant.side_effect = fake_tenant
        mock_prov_user.side_effect = fake_user

        instance = get_or_create_lms_connector_instance(self.org)
        user_job = ProvisioningJob.objects.create(
            instance=instance,
            organization=self.org,
            user=self.member_user,
            action=ProvisioningAction.PROVISION,
            status=ProvisioningJobStatus.QUEUED,
        )
        execute_provisioning_job(user_job)

        self.assertEqual(call_order, ["tenant", "user"], "Tenant must be provisioned before user.")
        self.assertTrue(ExternalTenantMapping.objects.filter(organization=self.org).exists())
        self.assertTrue(ExternalUserMapping.objects.filter(user=self.member_user).exists())

    # -------------------------------------------------------------------------
    # 13. User job cannot incorrectly provision into an unmapped tenant
    # -------------------------------------------------------------------------
    @mock.patch("apps.integration_hub.provisioning_service.LmsConnectorClient.provision_tenant")
    def test_13_user_job_cannot_provision_into_unmapped_tenant(self, mock_prov_tenant):
        mock_prov_tenant.side_effect = LmsConnectorError(
            message="Tenant creation failed",
            failure_code="TENANT_CREATION_FAILED",
            status_code=500,
            is_retryable=True,
        )
        instance = get_or_create_lms_connector_instance(self.org)
        user_job = ProvisioningJob.objects.create(
            instance=instance,
            organization=self.org,
            user=self.member_user,
            action=ProvisioningAction.PROVISION,
            status=ProvisioningJobStatus.QUEUED,
        )
        with self.assertRaises(LmsConnectorError):
            execute_provisioning_job(user_job)

        user_job.refresh_from_db()
        self.assertEqual(user_job.status, ProvisioningJobStatus.RETRY_SCHEDULED)
        self.assertFalse(ExternalUserMapping.objects.filter(user=self.member_user).exists())

    # -------------------------------------------------------------------------
    # 14. Retry after tenant dependency resolution succeeds
    # -------------------------------------------------------------------------
    @mock.patch("apps.integration_hub.provisioning_service.LmsConnectorClient.provision_user")
    @mock.patch("apps.integration_hub.provisioning_service.LmsConnectorClient.provision_tenant")
    def test_14_retry_after_tenant_dependency_resolution_succeeds(self, mock_prov_tenant, mock_prov_user):
        mock_prov_tenant.return_value = {"status": "success", "lms_organization_id": 401}
        mock_prov_user.return_value = {"status": "success", "lms_user_id": 701}

        instance = get_or_create_lms_connector_instance(self.org)
        user_job = ProvisioningJob.objects.create(
            instance=instance,
            organization=self.org,
            user=self.member_user,
            action=ProvisioningAction.PROVISION,
            status=ProvisioningJobStatus.QUEUED,
        )
        # Execute retry
        execute_provisioning_job(user_job)
        user_job.refresh_from_db()
        self.assertEqual(user_job.status, ProvisioningJobStatus.COMPLETED)
        self.assertTrue(ExternalTenantMapping.objects.filter(organization=self.org).exists())
        self.assertTrue(ExternalUserMapping.objects.filter(user=self.member_user).exists())

    # -------------------------------------------------------------------------
    # 17. No credentials/secrets in jobs/events
    # -------------------------------------------------------------------------
    def test_17_no_credentials_secrets_in_jobs_events(self):
        job = handle_tenant_lms_entitlement_activated(self.org, actor=self.owner)
        self.assertIsNotNone(job)

        event = IntegrationEvent.objects.filter(instance=job.instance).first()
        self.assertIsNotNone(event)

        job_context_str = str(job.context).lower()
        event_payload_str = str(event.payload).lower()

        forbidden = ["bearer", "secret", "password", "token", "auth_token", "private_key"]
        for f in forbidden:
            self.assertNotIn(f, job_context_str, f"Secret pattern '{f}' found in ProvisioningJob context.")
            self.assertNotIn(f, event_payload_str, f"Secret pattern '{f}' found in IntegrationEvent payload.")

    # -------------------------------------------------------------------------
    # 18. Cross-tenant user cannot trigger provisioning into another organization
    # -------------------------------------------------------------------------
    def test_18_cross_tenant_user_cannot_trigger_provisioning(self):
        other_org = self.create_org(code="other_org")
        alien_user = self.create_user(email="alien@external.com")
        # Alien user has no membership in other_org

        assignment = mock.MagicMock(
            id=uuid.uuid4(),
            organization=other_org,
            organization_id=other_org.id,
            user=alien_user,
            user_id=alien_user.id,
            product=self.lms_product,
            status=AssignmentStatus.ACTIVE,
        )

        job = handle_user_lms_assignment_active(assignment, actor=self.owner)
        self.assertIsNone(job, "Cross-tenant user must be rejected and create no job.")
        self.assertEqual(
            ProvisioningJob.objects.filter(organization=other_org, user=alien_user).count(),
            0,
        )

    # -------------------------------------------------------------------------
    # 19. Member promotion to TENANT_ADMIN enqueues LMS provisioning job
    # -------------------------------------------------------------------------
    def test_19_member_promotion_with_active_lms_assignment_enqueues_job(self):
        # Ensure active LMS product assignment exists
        assignment = UserProductAssignment.objects.create(
            organization=self.org,
            user=self.member_user,
            membership=self.membership,
            product=self.lms_product,
            status=AssignmentStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )

        promoted = update_membership_type(
            actor=self.owner,
            membership_id=self.membership.id,
            new_membership_type=MembershipType.TENANT_ADMIN,
        )
        self.assertEqual(promoted.membership_type, MembershipType.TENANT_ADMIN)

        # ProvisioningJob must be enqueued
        job = ProvisioningJob.objects.filter(
            organization=self.org,
            user=self.member_user,
            action=ProvisioningAction.PROVISION,
        ).first()
        self.assertIsNotNone(job)
        self.assertEqual(job.context.get("target_role"), "organization_admin")
        self.assertEqual(job.status, ProvisioningJobStatus.QUEUED)

        # Repeated calls when job is in-flight must not duplicate job
        from apps.integration_hub.lifecycle_service import handle_user_membership_promoted_to_admin

        second_job = handle_user_membership_promoted_to_admin(promoted, actor=self.owner)
        self.assertEqual(second_job.id, job.id)
        self.assertEqual(
            ProvisioningJob.objects.filter(
                organization=self.org,
                user=self.member_user,
                action=ProvisioningAction.PROVISION,
            ).count(),
            1,
        )

    # -------------------------------------------------------------------------
    # 20. Member promotion without active LMS assignment does not enqueue job
    # -------------------------------------------------------------------------
    def test_20_member_promotion_without_lms_assignment_does_not_enqueue_job(self):
        # User has no active LMS assignment (e.g. only CRM or none)
        UserProductAssignment.objects.create(
            organization=self.org,
            user=self.member_user,
            membership=self.membership,
            product=self.crm_product,
            status=AssignmentStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )

        promoted = update_membership_type(
            actor=self.owner,
            membership_id=self.membership.id,
            new_membership_type=MembershipType.TENANT_ADMIN,
        )
        self.assertEqual(promoted.membership_type, MembershipType.TENANT_ADMIN)

        # No ProvisioningJob should be created
        job_count = ProvisioningJob.objects.filter(
            organization=self.org,
            user=self.member_user,
        ).count()
        self.assertEqual(job_count, 0)

    # -------------------------------------------------------------------------
    # 21. Downgrade from TENANT_ADMIN with active LMS assignment fails closed
    # -------------------------------------------------------------------------
    def test_21_tenant_admin_downgrade_with_active_lms_assignment_fails_closed(self):
        # Promote to tenant admin first
        promoted = update_membership_type(
            actor=self.owner,
            membership_id=self.membership.id,
            new_membership_type=MembershipType.TENANT_ADMIN,
        )
        # Create a second admin to satisfy structural last admin guard
        admin2 = self.create_user()
        OrganizationMembership.objects.create(
            organization=self.org,
            user=admin2,
            membership_type=MembershipType.TENANT_ADMIN,
            role=promoted.role,
            status=MembershipStatus.ACTIVE,
            joined_at=timezone.now(),
        )

        # Attach active LMS assignment
        UserProductAssignment.objects.create(
            organization=self.org,
            user=self.member_user,
            membership=promoted,
            product=self.lms_product,
            status=AssignmentStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )

        # Attempt downgrade to MEMBER
        with self.assertRaises(LmsRoleDemotionUnsupportedError) as ctx:
            update_membership_type(
                actor=self.owner,
                membership_id=promoted.id,
                new_membership_type=MembershipType.MEMBER,
            )

        self.assertEqual(ctx.exception.code, "LMS_ROLE_DEMOTION_UNSUPPORTED")

        # Verify membership remains TENANT_ADMIN in DB (fail-closed)
        promoted.refresh_from_db()
        self.assertEqual(promoted.membership_type, MembershipType.TENANT_ADMIN)
        self.assertIsNotNone(promoted.role)

    # -------------------------------------------------------------------------
    # 22. Downgrade from TENANT_ADMIN without active LMS assignment succeeds
    # -------------------------------------------------------------------------
    def test_22_tenant_admin_downgrade_without_lms_assignment_succeeds(self):
        # Promote to tenant admin first
        promoted = update_membership_type(
            actor=self.owner,
            membership_id=self.membership.id,
            new_membership_type=MembershipType.TENANT_ADMIN,
        )
        # Create second admin for last-admin invariant
        admin2 = self.create_user()
        OrganizationMembership.objects.create(
            organization=self.org,
            user=admin2,
            membership_type=MembershipType.TENANT_ADMIN,
            role=promoted.role,
            status=MembershipStatus.ACTIVE,
            joined_at=timezone.now(),
        )

        # Downgrade to MEMBER succeeds because user has no active LMS assignment
        downgraded = update_membership_type(
            actor=self.owner,
            membership_id=promoted.id,
            new_membership_type=MembershipType.MEMBER,
        )
        self.assertEqual(downgraded.membership_type, MembershipType.MEMBER)
        self.assertIsNone(downgraded.role)



class Stage3TransactionSafetyTests(TransactionTestCase, Stage3TestBase):
    """Tests requiring real transaction rollback semantics to verify on_commit safety."""

    def setUp(self):
        self.owner = self.create_user(is_platform_owner=True)
        self.lms_product = self.create_lms_product()
        self.connector = self.setup_lms_connector()
        self.org = self.create_org()

    # -------------------------------------------------------------------------
    # 15. Rolled-back transaction does not leave a false provisioning job/event
    # -------------------------------------------------------------------------
    def test_15_rolled_back_transaction_leaves_no_orphans(self):
        initial_job_count = ProvisioningJob.objects.count()
        initial_event_count = IntegrationEvent.objects.count()

        try:
            with transaction.atomic():
                job = handle_tenant_lms_entitlement_activated(self.org, actor=self.owner)
                self.assertIsNotNone(job)
                # Force rollback
                raise RuntimeError("Simulated transaction rollback")
        except RuntimeError:
            pass

        final_job_count = ProvisioningJob.objects.count()
        final_event_count = IntegrationEvent.objects.count()
        self.assertEqual(final_job_count, initial_job_count, "Rolled-back transaction must leave no ProvisioningJob.")
        self.assertEqual(final_event_count, initial_event_count, "Rolled-back transaction must leave no IntegrationEvent.")

    # -------------------------------------------------------------------------
    # 16. Successful transaction exposes the provisioning job/event correctly
    # -------------------------------------------------------------------------
    def test_16_successful_transaction_persists_job_and_event(self):
        with transaction.atomic():
            job = handle_tenant_lms_entitlement_activated(self.org, actor=self.owner)
            self.assertIsNotNone(job)

        self.assertTrue(ProvisioningJob.objects.filter(id=job.id).exists())
        self.assertTrue(IntegrationEvent.objects.filter(instance=job.instance).exists())
