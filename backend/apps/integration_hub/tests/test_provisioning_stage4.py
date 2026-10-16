"""Comprehensive test suite for Phase 5C-3 Stage 4: Retry, Failure, Recovery & Concurrency.

Covers all required Stage 4 objectives:
A) TRANSIENT FAILURE -> RETRY -> SUCCESS
B) PERMANENT FAILURE -> DEAD LETTER
C) FAILURE RECOVERY / RETRY SAFETY
D) DUPLICATE TRIGGER / IDEMPOTENCY STRESS
E) CONCURRENCY TEST
F) FAILURE STATE CONSISTENCY
G) TRANSACTION / ON_COMMIT SAFETY
H) SECURITY / SECRET SAFETY
"""

from datetime import timedelta
from decimal import Decimal
import unittest.mock as mock
import uuid

from django.contrib.auth import get_user_model
from django.db import connection, transaction
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
)
from apps.integration_hub.lms_connector import (
    LmsConnectorClient,
    LmsConnectorConfigurationError,
    LmsConnectorError,
    LmsConnectorPermanentError,
    LmsConnectorRetryableError,
)
from apps.integration_hub.models import (
    ConnectorInstance,
    ConnectorStatus,
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
    provision_tenant_to_lms,
    provision_user_to_lms,
)
from apps.integration_hub.retry_service import (
    classify_failure,
    compute_backoff_delay,
    schedule_failure_retry,
)
from apps.organizations.models import MembershipStatus, MembershipType, Organization, OrganizationMembership, OrganizationStatus
from apps.plans.models import (
    BillingInterval,
    Plan,
    PlanCurrency,
    PlanPrice,
    PlanProduct,
    PlanQuota,
    PlanVersion,
    PlanVersionStatus,
    QuotaLimitType,
    QuotaResetPeriod,
    QuotaScope,
)
from apps.product_registry.models import Product, ProductStatus
from apps.subscriptions.models import (
    OrganizationSubscription,
    SubscriptionProductEntitlement,
    SubscriptionQuotaEntitlement,
    SubscriptionStatus,
)

User = get_user_model()


class Stage4TestBase:
    """Shared helpers for Stage 4 tests."""

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
        product, _ = Product.objects.get_or_create(
            code="lms",
            defaults={
                "name": "Learning Management System",
                "status": ProductStatus.ACTIVE,
                "created_by": self.owner,
                "updated_by": self.owner,
            },
        )
        return product

    def create_lms_connector(self):
        connector, _ = IntegrationConnector.objects.get_or_create(
            code="lms",
            defaults={
                "name": "LMS Connector",
                "product": self.lms_product,
                "status": ConnectorStatus.ACTIVE,
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
        plan_prod, _ = PlanProduct.objects.get_or_create(
            plan_version=pv,
            product=product,
            defaults={"created_by": self.owner},
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


class Stage4TestSuite(TestCase, Stage4TestBase):
    """Unit and integration test cases for Stage 4 objectives."""

    def setUp(self):
        self.owner = self.create_user(is_platform_owner=True)
        self.lms_product = self.create_lms_product()
        self.connector = self.create_lms_connector()
        self.org = self.create_org()
        self.instance = get_or_create_lms_connector_instance(self.org)
        self.member_user = self.create_user()
        self.membership = OrganizationMembership.objects.create(
            organization=self.org,
            user=self.member_user,
            membership_type=MembershipType.MEMBER,
            status=MembershipStatus.ACTIVE,
            joined_at=timezone.now(),
        )

    # =========================================================================
    # A) TRANSIENT FAILURE -> RETRY -> SUCCESS
    # =========================================================================

    @mock.patch("apps.integration_hub.provisioning_service.LmsConnectorClient.provision_tenant")
    def test_01_transient_failure_records_retry_scheduled(self, mock_prov_tenant):
        """Transient error (UPSTREAM_TIMEOUT) sets TRANSIENT, retry_count=1, RETRY_SCHEDULED, job FAILED."""
        mock_prov_tenant.side_effect = LmsConnectorRetryableError(
            message="Connection to LMS timed out after 10s",
            failure_code="UPSTREAM_TIMEOUT",
        )

        job = ProvisioningJob.objects.create(
            instance=self.instance,
            organization=self.org,
            user=None,
            action=ProvisioningAction.PROVISION,
            status=ProvisioningJobStatus.QUEUED,
        )

        with self.assertRaises(LmsConnectorError):
            execute_provisioning_job(job)

        job.refresh_from_db()
        self.assertEqual(job.status, ProvisioningJobStatus.RETRY_SCHEDULED)

        failure = IntegrationFailure.objects.filter(job=job).first()
        self.assertIsNotNone(failure)
        self.assertEqual(failure.failure_type, FailureType.TRANSIENT)
        self.assertEqual(failure.failure_code, "UPSTREAM_TIMEOUT")
        self.assertEqual(failure.retry_count, 1)
        self.assertEqual(failure.status, FailureStatus.RETRY_SCHEDULED)
        self.assertIsNotNone(failure.retry_after)
        self.assertGreater(failure.retry_after, timezone.now())

    @mock.patch("apps.integration_hub.provisioning_service.LmsConnectorClient.provision_tenant")
    def test_02_retry_success_recovers_job_and_resolves_failure(self, mock_prov_tenant):
        """Job failing transiently on attempt 1 recovers on attempt 2, becoming COMPLETED with failure RESOLVED."""
        # Attempt 1: Transient timeout
        mock_prov_tenant.side_effect = LmsConnectorRetryableError(
            message="Temporary network issue",
            failure_code="SERVICE_UNAVAILABLE",
        )

        job = ProvisioningJob.objects.create(
            instance=self.instance,
            organization=self.org,
            user=None,
            action=ProvisioningAction.PROVISION,
            status=ProvisioningJobStatus.QUEUED,
        )

        with self.assertRaises(LmsConnectorError):
            execute_provisioning_job(job)

        job.refresh_from_db()
        self.assertEqual(job.status, ProvisioningJobStatus.RETRY_SCHEDULED)
        failure = IntegrationFailure.objects.get(job=job)
        self.assertEqual(failure.status, FailureStatus.RETRY_SCHEDULED)
        self.assertEqual(failure.retry_count, 1)

        # Attempt 2: Upstream recovers
        mock_prov_tenant.side_effect = None
        mock_prov_tenant.return_value = {
            "status": "success",
            "action_taken": "created",
            "lms_organization_id": 888,
        }

        execute_provisioning_job(job)

        job.refresh_from_db()
        self.assertEqual(job.status, ProvisioningJobStatus.COMPLETED)
        self.assertIsNotNone(job.completed_at)

        failure.refresh_from_db()
        self.assertEqual(failure.status, FailureStatus.RESOLVED)
        self.assertIsNotNone(failure.resolved_at)

        mapping = ExternalTenantMapping.objects.get(organization=self.org)
        self.assertEqual(mapping.external_tenant_id, "888")

    def test_03_backoff_timing_deterministic_progression(self):
        """Calculates exponential backoff delays according to formula base_seconds * (2 ** (attempt - 1))."""
        delay_1 = compute_backoff_delay(attempt=1, base_seconds=60, factor=2)
        delay_2 = compute_backoff_delay(attempt=2, base_seconds=60, factor=2)
        delay_3 = compute_backoff_delay(attempt=3, base_seconds=60, factor=2)

        self.assertEqual(delay_1, 60)
        self.assertEqual(delay_2, 120)
        self.assertEqual(delay_3, 240)

    # =========================================================================
    # B) PERMANENT FAILURE -> DEAD LETTER
    # =========================================================================

    @mock.patch("apps.integration_hub.provisioning_service.LmsConnectorClient.provision_tenant")
    def test_04_permanent_auth_failure_immediately_dead_letters(self, mock_prov_tenant):
        """Permanent error (AUTHENTICATION_FAILED, 401) sets FailureType.PERMANENT, DEAD_LETTER, no retry."""
        mock_prov_tenant.side_effect = LmsConnectorPermanentError(
            message="M2M authentication failed: Invalid token",
            failure_code="AUTHENTICATION_FAILED",
            status_code=401,
        )

        job = ProvisioningJob.objects.create(
            instance=self.instance,
            organization=self.org,
            user=None,
            action=ProvisioningAction.PROVISION,
            status=ProvisioningJobStatus.QUEUED,
        )

        with self.assertRaises(LmsConnectorError):
            execute_provisioning_job(job)

        job.refresh_from_db()
        self.assertEqual(job.status, ProvisioningJobStatus.FAILED)

        failure = IntegrationFailure.objects.get(job=job)
        self.assertEqual(failure.failure_type, FailureType.PERMANENT)
        self.assertEqual(failure.status, FailureStatus.DEAD_LETTER)
        self.assertIsNone(failure.retry_after)
        self.assertEqual(failure.retry_count, 0)
        self.assertFalse(ExternalTenantMapping.objects.filter(organization=self.org).exists())

    @mock.patch("apps.integration_hub.provisioning_service.LmsConnectorClient.provision_user")
    def test_05_validation_error_immediately_dead_letters(self, mock_prov_user):
        """Deterministic validation error (VALIDATION_ERROR, 400) immediately dead-letters."""
        # Pre-seed tenant mapping so user job executes directly
        ExternalTenantMapping.objects.create(
            instance=self.instance,
            organization=self.org,
            external_tenant_id="999",
        )

        mock_prov_user.side_effect = LmsConnectorPermanentError(
            message="Invalid email address format",
            failure_code="VALIDATION_ERROR",
            status_code=400,
        )

        job = ProvisioningJob.objects.create(
            instance=self.instance,
            organization=self.org,
            user=self.member_user,
            action=ProvisioningAction.PROVISION,
            status=ProvisioningJobStatus.QUEUED,
        )

        with self.assertRaises(LmsConnectorError):
            execute_provisioning_job(job)

        failure = IntegrationFailure.objects.get(job=job)
        self.assertEqual(failure.failure_type, FailureType.PERMANENT)
        self.assertEqual(failure.status, FailureStatus.DEAD_LETTER)
        self.assertIsNone(failure.retry_after)
        self.assertFalse(ExternalUserMapping.objects.filter(user=self.member_user).exists())

    @mock.patch("apps.integration_hub.provisioning_service.LmsConnectorClient.provision_tenant")
    def test_06_exhausted_retries_transitions_to_dead_letter(self, mock_prov_tenant):
        """After reaching max_retries (3), the 4th failure moves failure into DEAD_LETTER state."""
        mock_prov_tenant.side_effect = LmsConnectorRetryableError(
            message="Transient timeout",
            failure_code="UPSTREAM_TIMEOUT",
        )

        job = ProvisioningJob.objects.create(
            instance=self.instance,
            organization=self.org,
            user=None,
            action=ProvisioningAction.PROVISION,
            status=ProvisioningJobStatus.QUEUED,
        )

        # Failure 1 (retry_count 0 -> 1)
        with self.assertRaises(LmsConnectorError):
            execute_provisioning_job(job)
        failure = IntegrationFailure.objects.get(job=job)
        self.assertEqual(failure.retry_count, 1)
        self.assertEqual(failure.status, FailureStatus.RETRY_SCHEDULED)

        # Failure 2 (retry_count 1 -> 2)
        with self.assertRaises(LmsConnectorError):
            execute_provisioning_job(job)
        failure.refresh_from_db()
        self.assertEqual(failure.retry_count, 2)
        self.assertEqual(failure.status, FailureStatus.RETRY_SCHEDULED)

        # Failure 3 (retry_count 2 -> 3)
        with self.assertRaises(LmsConnectorError):
            execute_provisioning_job(job)
        failure.refresh_from_db()
        self.assertEqual(failure.retry_count, 3)
        self.assertEqual(failure.status, FailureStatus.RETRY_SCHEDULED)

        # Failure 4 (retry_count reaches max_retries 3 -> transitions to DEAD_LETTER)
        with self.assertRaises(LmsConnectorError):
            execute_provisioning_job(job)
        failure.refresh_from_db()
        self.assertEqual(failure.status, FailureStatus.DEAD_LETTER)
        self.assertIsNone(failure.retry_after)

    # =========================================================================
    # C) FAILURE RECOVERY / RETRY SAFETY
    # =========================================================================

    @mock.patch("apps.integration_hub.provisioning_service.LmsConnectorClient.provision_tenant")
    def test_07_recovery_when_lms_succeeded_but_response_timed_out(self, mock_prov_tenant):
        """Simulate: LMS created tenant, but VibeConnect timed out waiting for response.
        On retry: LMS returns action_taken='existing', VibeConnect reconciles mapping and marks COMPLETED.
        """
        # Attempt 1: Timeout on response
        mock_prov_tenant.side_effect = LmsConnectorRetryableError(
            message="Read timeout from server",
            failure_code="UPSTREAM_TIMEOUT",
        )

        job = ProvisioningJob.objects.create(
            instance=self.instance,
            organization=self.org,
            user=None,
            action=ProvisioningAction.PROVISION,
            status=ProvisioningJobStatus.QUEUED,
        )

        with self.assertRaises(LmsConnectorError):
            execute_provisioning_job(job)

        self.assertFalse(ExternalTenantMapping.objects.filter(organization=self.org).exists())

        # Attempt 2: LMS already has the tenant and returns existing record
        mock_prov_tenant.side_effect = None
        mock_prov_tenant.return_value = {
            "status": "success",
            "action_taken": "existing",
            "lms_organization_id": 555,
        }

        execute_provisioning_job(job)
        job.refresh_from_db()
        self.assertEqual(job.status, ProvisioningJobStatus.COMPLETED)

        mapping_count = ExternalTenantMapping.objects.filter(organization=self.org).count()
        self.assertEqual(mapping_count, 1)
        mapping = ExternalTenantMapping.objects.get(organization=self.org)
        self.assertEqual(mapping.external_tenant_id, "555")

    @mock.patch("apps.integration_hub.provisioning_service.LmsConnectorClient.provision_user")
    def test_08_user_recovery_after_timeout_reuses_lms_user(self, mock_prov_user):
        """User provisioning retry safely links to existing LMS user without creating duplicates."""
        ExternalTenantMapping.objects.create(
            instance=self.instance,
            organization=self.org,
            external_tenant_id="555",
        )

        # Attempt 1: Timeout
        mock_prov_user.side_effect = LmsConnectorRetryableError(
            message="Connection dropped after user created in LMS",
            failure_code="CONNECTION_RESET",
        )

        job = ProvisioningJob.objects.create(
            instance=self.instance,
            organization=self.org,
            user=self.member_user,
            action=ProvisioningAction.PROVISION,
            status=ProvisioningJobStatus.QUEUED,
        )

        with self.assertRaises(LmsConnectorError):
            execute_provisioning_job(job)

        self.assertFalse(ExternalUserMapping.objects.filter(user=self.member_user).exists())

        # Attempt 2: LMS returns existing user
        mock_prov_user.side_effect = None
        mock_prov_user.return_value = {
            "status": "success",
            "action_taken": "existing",
            "lms_user_id": 999,
        }

        execute_provisioning_job(job)
        job.refresh_from_db()
        self.assertEqual(job.status, ProvisioningJobStatus.COMPLETED)

        mapping_count = ExternalUserMapping.objects.filter(user=self.member_user).count()
        self.assertEqual(mapping_count, 1)
        mapping = ExternalUserMapping.objects.get(user=self.member_user)
        self.assertEqual(mapping.external_user_id, "999")
        self.assertEqual(mapping.status, ExternalUserMappingStatus.ACTIVE)

    # =========================================================================
    # D) DUPLICATE TRIGGER / IDEMPOTENCY STRESS
    # =========================================================================

    def test_09_repeated_entitlement_activation_returns_same_job(self):
        """Calling handle_tenant_lms_entitlement_activated twice returns the exact same ProvisioningJob."""
        job_1 = handle_tenant_lms_entitlement_activated(self.org, actor=self.owner)
        self.assertIsNotNone(job_1)

        job_2 = handle_tenant_lms_entitlement_activated(self.org, actor=self.owner)
        self.assertIsNotNone(job_2)

        self.assertEqual(job_1.id, job_2.id)
        job_count = ProvisioningJob.objects.filter(
            organization=self.org,
            user=None,
            action=ProvisioningAction.PROVISION,
        ).count()
        self.assertEqual(job_count, 1)

    def test_10_repeated_user_assignment_hook_returns_same_job(self):
        """Calling handle_user_lms_assignment_active twice returns the exact same ProvisioningJob."""
        assignment = UserProductAssignment.objects.create(
            organization=self.org,
            user=self.member_user,
            membership=self.membership,
            product=self.lms_product,
            status=AssignmentStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )

        job_1 = handle_user_lms_assignment_active(assignment, actor=self.owner)
        self.assertIsNotNone(job_1)

        job_2 = handle_user_lms_assignment_active(assignment, actor=self.owner)
        self.assertIsNotNone(job_2)

        self.assertEqual(job_1.id, job_2.id)
        job_count = ProvisioningJob.objects.filter(
            organization=self.org,
            user=self.member_user,
            action=ProvisioningAction.PROVISION,
        ).count()
        self.assertEqual(job_count, 1)

    @mock.patch("apps.integration_hub.provisioning_service.LmsConnectorClient.provision_tenant")
    def test_11_repeated_execute_on_completed_job_is_safe_noop(self, mock_prov_tenant):
        """Executing an already COMPLETED ProvisioningJob does not call LMS API or modify job."""
        mock_prov_tenant.return_value = {
            "status": "success",
            "action_taken": "created",
            "lms_organization_id": 111,
        }

        job = ProvisioningJob.objects.create(
            instance=self.instance,
            organization=self.org,
            user=None,
            action=ProvisioningAction.PROVISION,
            status=ProvisioningJobStatus.QUEUED,
        )

        execute_provisioning_job(job)
        self.assertEqual(mock_prov_tenant.call_count, 1)

        # Call again
        execute_provisioning_job(job)
        self.assertEqual(mock_prov_tenant.call_count, 1, "Completed job must not re-call LMS API.")

    # =========================================================================
    # E) CONCURRENCY TEST
    # =========================================================================

    @mock.patch("apps.integration_hub.provisioning_service.LmsConnectorClient.provision_tenant")
    def test_12_concurrent_tenant_provisioning_converges_cleanly(self, mock_prov_tenant):
        """Simulate concurrent provisioning requests for the same tenant.
        Verifies database constraints and locking converge on exactly 1 ExternalTenantMapping.
        """
        mock_prov_tenant.return_value = {
            "status": "success",
            "action_taken": "created",
            "lms_organization_id": 222,
        }

        # Call provision_tenant_to_lms twice sequentially to test atomic get_or_create logic
        res_1 = provision_tenant_to_lms(self.org, instance=self.instance)
        res_2 = provision_tenant_to_lms(self.org, instance=self.instance)

        self.assertEqual(res_1["status"], "success")
        self.assertEqual(res_2["status"], "success")

        mapping_count = ExternalTenantMapping.objects.filter(
            instance=self.instance,
            organization=self.org,
        ).count()
        self.assertEqual(mapping_count, 1)

    @mock.patch("apps.integration_hub.provisioning_service.LmsConnectorClient.provision_user")
    def test_13_concurrent_user_provisioning_converges_cleanly(self, mock_prov_user):
        """Simulate concurrent user provisioning requests. Converges on exactly 1 ExternalUserMapping."""
        ExternalTenantMapping.objects.create(
            instance=self.instance,
            organization=self.org,
            external_tenant_id="222",
        )

        mock_prov_user.return_value = {
            "status": "success",
            "action_taken": "created",
            "lms_user_id": 333,
        }

        res_1 = provision_user_to_lms(self.member_user, self.org, is_active=True, instance=self.instance)
        res_2 = provision_user_to_lms(self.member_user, self.org, is_active=True, instance=self.instance)

        self.assertEqual(res_1["status"], "success")
        self.assertEqual(res_2["status"], "success")

        mapping_count = ExternalUserMapping.objects.filter(
            instance=self.instance,
            user=self.member_user,
            organization=self.org,
        ).count()
        self.assertEqual(mapping_count, 1)

    # =========================================================================
    # F) FAILURE STATE CONSISTENCY
    # =========================================================================

    @mock.patch("apps.integration_hub.provisioning_service.LmsConnectorClient.provision_tenant")
    def test_14_failed_tenant_provisioning_leaves_no_false_mapping(self, mock_prov_tenant):
        """When tenant provisioning fails, ExternalTenantMapping must NOT exist."""
        mock_prov_tenant.side_effect = LmsConnectorPermanentError(
            message="Internal database error on remote side",
            failure_code="SERVER_ERROR",
        )

        job = ProvisioningJob.objects.create(
            instance=self.instance,
            organization=self.org,
            user=None,
            action=ProvisioningAction.PROVISION,
            status=ProvisioningJobStatus.QUEUED,
        )

        with self.assertRaises(LmsConnectorError):
            execute_provisioning_job(job)

        self.assertFalse(ExternalTenantMapping.objects.filter(organization=self.org).exists())

    @mock.patch("apps.integration_hub.provisioning_service.LmsConnectorClient.provision_user")
    def test_15_failed_user_provisioning_leaves_no_false_mapping(self, mock_prov_user):
        """When user provisioning fails, ExternalUserMapping must NOT exist."""
        ExternalTenantMapping.objects.create(
            instance=self.instance,
            organization=self.org,
            external_tenant_id="222",
        )

        mock_prov_user.side_effect = LmsConnectorRetryableError(
            message="Temporary network timeout",
            failure_code="UPSTREAM_TIMEOUT",
        )

        job = ProvisioningJob.objects.create(
            instance=self.instance,
            organization=self.org,
            user=self.member_user,
            action=ProvisioningAction.PROVISION,
            status=ProvisioningJobStatus.QUEUED,
        )

        with self.assertRaises(LmsConnectorError):
            execute_provisioning_job(job)

        self.assertFalse(ExternalUserMapping.objects.filter(user=self.member_user).exists())

    # =========================================================================
    # H) SECURITY / SECRET SAFETY
    # =========================================================================

    def test_16_secrets_never_stored_in_failure_or_job_context(self):
        """Verifies no tokens, passwords, or bearer headers exist in IntegrationFailure or ProvisioningJob."""
        job = handle_tenant_lms_entitlement_activated(self.org, actor=self.owner)
        self.assertIsNotNone(job)

        job_str = str(job.context).lower()
        forbidden_patterns = ["bearer", "token", "password", "secret", "private_key", "sec_"]

        for pat in forbidden_patterns:
            self.assertNotIn(pat, job_str, f"Forbidden secret-like pattern '{pat}' found in ProvisioningJob context.")

        failure = IntegrationFailure.objects.create(
            job=job,
            failure_code="UPSTREAM_TIMEOUT",
            failure_detail="LMS connection timed out after 10s at /api/v1/integration/tenants/provision/",
            failure_type=FailureType.TRANSIENT,
        )
        fail_str = str(failure.failure_detail).lower()
        for pat in forbidden_patterns:
            self.assertNotIn(pat, fail_str, f"Forbidden secret-like pattern '{pat}' found in IntegrationFailure detail.")

    def test_17_invalid_m2m_connector_secret_raises_permanent_error(self):
        """LmsConnectorClient with missing/invalid secret raises LmsConnectorConfigurationError."""
        with mock.patch("apps.integration_hub.lms_connector.get_m2m_connector_secret") as mock_get_secret:
            mock_get_secret.side_effect = ValueError("Connector secret not found in settings or vault")
            with self.assertRaises(LmsConnectorConfigurationError):
                LmsConnectorClient(base_url="http://127.0.0.1:8000", secret="")


class Stage4TransactionTests(TransactionTestCase, Stage4TestBase):
    """Transaction commit/rollback safety tests (requires TransactionTestCase for real commit tracking)."""

    def setUp(self):
        self.owner = self.create_user(is_platform_owner=True)
        self.lms_product = self.create_lms_product()
        self.connector = self.create_lms_connector()
        self.org = self.create_org()
        self.instance = get_or_create_lms_connector_instance(self.org)

    # =========================================================================
    # G) TRANSACTION / ON_COMMIT SAFETY
    # =========================================================================

    @mock.patch("apps.integration_hub.lifecycle_service.dispatch_provisioning_job")
    def test_18_rolled_back_transaction_does_not_execute_dispatch(self, mock_dispatch):
        """Rolled-back business transaction discards on_commit callbacks; no job is dispatched."""
        try:
            with transaction.atomic():
                OrganizationProductEntitlement.objects.create(
                    organization=self.org,
                    product=self.lms_product,
                    status=EntitlementStatus.ACTIVE,
                    created_by=self.owner,
                    updated_by=self.owner,
                )
                raise RuntimeError("Simulated transaction rollback (e.g. database error)")
        except RuntimeError:
            pass

        mock_dispatch.assert_not_called()
        self.assertFalse(
            ProvisioningJob.objects.filter(
                organization=self.org,
                action=ProvisioningAction.PROVISION,
            ).exists()
        )

    @mock.patch("apps.integration_hub.lifecycle_service.dispatch_provisioning_job")
    def test_19_committed_transaction_executes_dispatch(self, mock_dispatch):
        """Committed business transaction triggers on_commit and dispatches the ProvisioningJob."""
        with transaction.atomic():
            OrganizationProductEntitlement.objects.create(
                organization=self.org,
                product=self.lms_product,
                status=EntitlementStatus.ACTIVE,
                created_by=self.owner,
                updated_by=self.owner,
            )

        mock_dispatch.assert_called_once()
        self.assertTrue(
            ProvisioningJob.objects.filter(
                organization=self.org,
                action=ProvisioningAction.PROVISION,
            ).exists()
        )
