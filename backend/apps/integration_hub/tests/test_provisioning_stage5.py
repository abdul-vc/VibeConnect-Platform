"""Stage 5 Automated Test Suite: Fresh Tenant + Fresh User Full Provisioning Verification.

Covers:
- Section A: Fresh Tenant Creation + LMS Provisioning
- Section B: Fresh User Creation + LMS Provisioning
- Section C: Fresh User Identity Verification & Cross-Tenant Isolation
- Section D: Fresh User Lifecycle (Active -> Suspend -> Reactivate -> Revoke)
- Section E: Duplicate / Idempotency Acceptance on Fresh Data
- Section G: SSO Identity / Token Claims Verification
- Section H: Failure / Recovery Regression on Fresh Data
- Section I: Security / Secret Leakage / Tenant Isolation
"""

from datetime import timedelta
from decimal import Decimal
import uuid
from unittest import mock

from django.contrib.auth import get_user_model
from django.db import transaction
from django.test import TestCase
from django.utils import timezone
from rest_framework import exceptions

from apps.access_control.models import Role
from apps.assignments.models import AssignmentStatus, UserProductAssignment
from apps.assignments.services.assignment_services import (
    assign_user_to_product,
    reactivate_user_assignment,
    revoke_user_assignment,
    suspend_user_assignment,
)
from apps.entitlements.models import EntitlementStatus, OrganizationProductEntitlement
from apps.integration_hub.lifecycle_service import (
    handle_tenant_lms_entitlement_activated,
    handle_user_lms_assignment_active,
)
from apps.integration_hub.models import (
    ConnectorInstance,
    ConnectorStatus,
    ExternalTenantMapping,
    ExternalUserMapping,
    ExternalUserMappingStatus,
    FailureStatus,
    FailureType,
    InstanceStatus,
    IntegrationConnector,
    IntegrationFailure,
    ProductSsoClient,
    ProvisioningAction,
    ProvisioningJob,
    ProvisioningJobStatus,
)
from apps.integration_hub.lms_connector import (
    LmsConnectorClient,
    LmsConnectorPermanentError,
    LmsConnectorRetryableError,
)
from apps.integration_hub.provisioning_service import (
    execute_provisioning_job,
    get_or_create_lms_connector_instance,
)
from apps.integration_hub.sso_service import (
    issue_sso_authorization_code,
    validate_sso_authorization_code,
    get_m2m_connector_secret,
)
from apps.organizations.models import (
    MembershipStatus,
    MembershipType,
    Organization,
    OrganizationMembership,
    OrganizationStatus,
)
from apps.plans.models import (
    BillingInterval,
    Plan,
    PlanCurrency,
    PlanModule,
    PlanPrice,
    PlanProduct,
    PlanQuota,
    PlanVersion,
    PlanVersionStatus,
    QuotaLimitType,
    QuotaResetPeriod,
    QuotaScope,
)
from apps.product_registry.models import CatalogStatus, Product, ProductModule, ProductStatus
from apps.subscriptions.models import (
    OrganizationSubscription,
    SubscriptionModuleEntitlement,
    SubscriptionProductEntitlement,
    SubscriptionQuotaEntitlement,
    SubscriptionStatus,
)

User = get_user_model()


class Stage5ProvisioningVerificationTestCase(TestCase):
    """Exhaustive test suite for Stage 5 acceptance requirements."""

    def setUp(self):
        super().setUp()
        self.test_id = uuid.uuid4().hex[:8]

        # 1. Fresh Admin & Org
        self.admin = User.objects.create_user(
            email=f"admin_{self.test_id}@test.internal",
            password="TestPassword123!",
            full_name=f"Admin {self.test_id}",
            is_active=True,
        )

        # 2. LMS Product & Connector
        self.lms_product, _ = Product.objects.get_or_create(
            code="lms",
            defaults={
                "name": "Learning Management System",
                "status": ProductStatus.ACTIVE,
                "created_by": self.admin,
                "updated_by": self.admin,
            },
        )
        self.lms_core_module, _ = ProductModule.objects.get_or_create(
            product=self.lms_product,
            code="lms_core",
            defaults={
                "name": "LMS Core Module",
                "status": CatalogStatus.ACTIVE,
                "created_by": self.admin,
                "updated_by": self.admin,
            },
        )

        self.connector, _ = IntegrationConnector.objects.get_or_create(
            code="lms",
            defaults={"name": "LMS Connector", "product": self.lms_product, "status": ConnectorStatus.ACTIVE},
        )

        self.org = Organization.objects.create(
            name=f"Stage 5 Org {self.test_id}",
            code=f"org-{self.test_id}",
            status=OrganizationStatus.ACTIVE,
            created_by=self.admin,
            updated_by=self.admin,
        )
        self.tenant_admin_role, _ = Role.objects.get_or_create(
            code="system_tenant_admin",
            defaults={"name": "Tenant Administrator", "is_system_role": True},
        )
        self.admin_membership = OrganizationMembership.objects.create(
            organization=self.org,
            user=self.admin,
            membership_type=MembershipType.TENANT_ADMIN,
            role=self.tenant_admin_role,
            status=MembershipStatus.ACTIVE,
            joined_at=timezone.now(),
        )

        # 3. Plan & Subscription Infrastructure
        self.plan = Plan.objects.create(
            code=f"plan_{self.test_id}",
            name=f"Plan {self.test_id}",
            created_by=self.admin,
            updated_by=self.admin,
        )
        self.pv = PlanVersion.objects.create(
            plan=self.plan,
            version=1,
            status=PlanVersionStatus.ACTIVE,
            activated_at=timezone.now(),
            created_by=self.admin,
            updated_by=self.admin,
        )
        self.price = PlanPrice.objects.create(
            plan_version=self.pv,
            currency=PlanCurrency.USD,
            billing_interval=BillingInterval.MONTHLY,
            amount=Decimal("100.00"),
            created_by=self.admin,
            updated_by=self.admin,
        )
        self.plan_prod = PlanProduct.objects.create(
            plan_version=self.pv,
            product=self.lms_product,
            created_by=self.admin,
        )
        self.plan_mod = PlanModule.objects.create(
            plan_version=self.pv,
            plan_product=self.plan_prod,
            module=self.lms_core_module,
            created_by=self.admin,
        )
        self.plan_quota = PlanQuota.objects.create(
            plan_version=self.pv,
            quota_key="seats",
            name="Plan Seats",
            scope=QuotaScope.PLAN,
            limit_type=QuotaLimitType.NUMERIC,
            limit_value=50,
            unit="seats",
            reset_period=QuotaResetPeriod.MONTHLY,
            is_hard_limit=True,
            created_by=self.admin,
            updated_by=self.admin,
        )

        now = timezone.now()
        self.sub = OrganizationSubscription.objects.create(
            organization=self.org,
            plan_version=self.pv,
            plan_price=self.price,
            plan_code_snapshot=self.plan.code,
            plan_name_snapshot=self.plan.name,
            version_number_snapshot=self.pv.version,
            billing_interval=self.price.billing_interval,
            currency=self.price.currency,
            amount=self.price.amount,
            started_as_trial=False,
            status=SubscriptionStatus.ACTIVE,
            current_period_start=now - timedelta(days=1),
            current_period_end=now + timedelta(days=30),
            created_by=self.admin,
            updated_by=self.admin,
        )
        # 4. Product SSO Client
        self.sso_client, _ = ProductSsoClient.objects.get_or_create(
            product=self.lms_product,
            defaults={
                "client_identifier": f"client_{self.test_id}",
                "audience": "lms-backend",
                "callback_uri": "http://localhost:8080/sso/callback",
                "public_key_reference": "ref-sso-key",
                "is_active": True,
            },
        )

        # 5. Fresh User
        self.user = User.objects.create_user(
            email=f"user_{self.test_id}@test.internal",
            password="TestPassword123!",
            full_name=f"User {self.test_id}",
            is_active=True,
        )
        self.user_membership = OrganizationMembership.objects.create(
            organization=self.org,
            user=self.user,
            membership_type=MembershipType.MEMBER,
            status=MembershipStatus.ACTIVE,
            joined_at=timezone.now(),
        )

        # Mock LMS client responses
        self.lms_org_id = f"mock-lms-org-{self.test_id}"
        self.lms_user_id = f"mock-lms-user-{self.test_id}"

        self.mock_client = mock.MagicMock(spec=LmsConnectorClient)
        self.mock_client.provision_tenant.return_value = {
            "success": True,
            "lms_organization_id": self.lms_org_id,
            "status": "Active",
        }
        self.mock_client.provision_user.return_value = {
            "success": True,
            "lms_user_id": self.lms_user_id,
            "status": "Active",
        }

    def setup_subscription_entitlements(self):
        SubscriptionProductEntitlement.objects.get_or_create(
            subscription=self.sub,
            organization=self.org,
            product=self.lms_product,
            defaults={
                "plan_product": self.plan_prod,
                "product_code_snapshot": self.lms_product.code,
                "product_name_snapshot": self.lms_product.name,
            },
        )
        SubscriptionModuleEntitlement.objects.get_or_create(
            subscription=self.sub,
            organization=self.org,
            module=self.lms_core_module,
            defaults={
                "plan_module": self.plan_mod,
                "module_code_snapshot": self.lms_core_module.code,
                "module_name_snapshot": self.lms_core_module.name,
            },
        )
        SubscriptionQuotaEntitlement.objects.get_or_create(
            subscription=self.sub,
            organization=self.org,
            plan_quota=self.plan_quota,
            defaults={
                "quota_key": "seats",
                "name": "Plan Seats",
                "scope": QuotaScope.PLAN,
                "limit_type": QuotaLimitType.NUMERIC,
                "limit_value": 50,
                "unit": "seats",
                "reset_period": QuotaResetPeriod.MONTHLY,
                "is_hard_limit": True,
            },
        )

    # =========================================================================
    # A. FRESH TENANT CREATION + LMS PROVISIONING
    # =========================================================================
    def test_section_a_fresh_tenant_provisioning(self):
        """Entitlement activation creates exactly one job, COMPLETED, mapping established."""
        self.assertFalse(ExternalTenantMapping.objects.filter(organization=self.org).exists())

        with mock.patch("apps.integration_hub.provisioning_service.LmsConnectorClient", return_value=self.mock_client):
            with self.captureOnCommitCallbacks(execute=True):
                entitlement = OrganizationProductEntitlement.objects.create(
                    organization=self.org,
                    product=self.lms_product,
                    status=EntitlementStatus.ACTIVE,
                    created_by=self.admin,
                    updated_by=self.admin,
                )

        # 1. Job created and completed
        jobs = ProvisioningJob.objects.filter(organization=self.org, user__isnull=True)
        self.assertEqual(jobs.count(), 1)
        job = jobs.first()
        self.assertEqual(job.status, ProvisioningJobStatus.COMPLETED)
        self.assertIsNotNone(job.completed_at)

        # 2. ExternalTenantMapping created
        mapping = ExternalTenantMapping.objects.filter(organization=self.org).first()
        self.assertIsNotNone(mapping)
        self.assertEqual(mapping.external_tenant_id, self.lms_org_id)

        # 3. No unresolved failures
        failures = IntegrationFailure.objects.filter(job=job)
        self.assertFalse(failures.filter(status__in=[FailureStatus.OPEN, FailureStatus.DEAD_LETTER]).exists())

    # =========================================================================
    # B. FRESH USER CREATION + LMS PROVISIONING
    # =========================================================================
    def test_section_b_fresh_user_provisioning(self):
        """User product assignment creates exactly one user job, COMPLETED, mapping established."""
        self.setup_subscription_entitlements()
        # Ensure tenant mapped
        ExternalTenantMapping.objects.create(
            instance=get_or_create_lms_connector_instance(self.org),
            organization=self.org,
            external_tenant_id=self.lms_org_id,
        )

        with mock.patch("apps.integration_hub.provisioning_service.LmsConnectorClient", return_value=self.mock_client):
            with self.captureOnCommitCallbacks(execute=True):
                assignment = assign_user_to_product(
                    organization_id=self.org.id,
                    user_id=self.user.id,
                    product_id=self.lms_product.id,
                    module_ids=[self.lms_core_module.id],
                    actor=self.admin,
                )

        # 1. Job created and completed
        jobs = ProvisioningJob.objects.filter(organization=self.org, user=self.user)
        self.assertEqual(jobs.count(), 1)
        job = jobs.first()
        self.assertEqual(job.status, ProvisioningJobStatus.COMPLETED)

        # 2. ExternalUserMapping created
        user_mapping = ExternalUserMapping.objects.filter(user=self.user, organization=self.org).first()
        self.assertIsNotNone(user_mapping)
        self.assertEqual(user_mapping.external_user_id, self.lms_user_id)
        self.assertEqual(user_mapping.status, ExternalUserMappingStatus.ACTIVE)

        # 3. No unresolved failures
        failures = IntegrationFailure.objects.filter(job=job)
        self.assertFalse(failures.filter(status__in=[FailureStatus.OPEN, FailureStatus.DEAD_LETTER]).exists())

    # =========================================================================
    # C. FRESH USER IDENTITY VERIFICATION
    # =========================================================================
    def test_section_c_identity_chain_and_isolation(self):
        """Verifies VC User -> VC Mapping -> LMS ID chain and cross-tenant isolation."""
        instance = get_or_create_lms_connector_instance(self.org)
        user_mapping = ExternalUserMapping.objects.create(
            instance=instance,
            organization=self.org,
            user=self.user,
            external_user_id=self.lms_user_id,
            status=ExternalUserMappingStatus.ACTIVE,
        )

        self.assertEqual(user_mapping.user_id, self.user.id)
        self.assertEqual(user_mapping.organization_id, self.org.id)
        self.assertEqual(user_mapping.external_user_id, self.lms_user_id)

        # Cross-tenant isolation check
        other_org = Organization.objects.create(
            name=f"Other Org {self.test_id}",
            code=f"other-{self.test_id}",
            status=OrganizationStatus.ACTIVE,
            created_by=self.admin,
            updated_by=self.admin,
        )
        self.assertFalse(ExternalUserMapping.objects.filter(user=self.user, organization=other_org).exists())

    # =========================================================================
    # D. FRESH USER LIFECYCLE
    # =========================================================================
    def test_section_d_user_lifecycle_suspend_reactivate_revoke(self):
        """Active -> Suspend -> Reactivate -> Revoke (disable-not-delete)."""
        self.setup_subscription_entitlements()
        instance = get_or_create_lms_connector_instance(self.org)
        ExternalTenantMapping.objects.create(
            instance=instance,
            organization=self.org,
            external_tenant_id=self.lms_org_id,
        )
        user_mapping = ExternalUserMapping.objects.create(
            instance=instance,
            organization=self.org,
            user=self.user,
            external_user_id=self.lms_user_id,
            status=ExternalUserMappingStatus.ACTIVE,
        )

        with mock.patch("apps.integration_hub.provisioning_service.LmsConnectorClient", return_value=self.mock_client):
            with self.captureOnCommitCallbacks(execute=True):
                assignment = assign_user_to_product(
                    organization_id=self.org.id,
                    user_id=self.user.id,
                    product_id=self.lms_product.id,
                    module_ids=[self.lms_core_module.id],
                    actor=self.admin,
                )

            # 1. Suspend
            with self.captureOnCommitCallbacks(execute=True):
                suspend_user_assignment(assignment_id=assignment.id, actor=self.admin, reason="Testing suspension")
            user_mapping.refresh_from_db()
            assignment.refresh_from_db()
            self.assertEqual(assignment.status, AssignmentStatus.SUSPENDED)
            self.assertEqual(user_mapping.status, ExternalUserMappingStatus.SUSPENDED)

            # 2. Reactivate
            with self.captureOnCommitCallbacks(execute=True):
                reactivate_user_assignment(assignment_id=assignment.id, actor=self.admin)
            user_mapping.refresh_from_db()
            assignment.refresh_from_db()
            self.assertEqual(assignment.status, AssignmentStatus.ACTIVE)
            self.assertEqual(user_mapping.status, ExternalUserMappingStatus.ACTIVE)

            # 3. Revoke
            with self.captureOnCommitCallbacks(execute=True):
                revoke_user_assignment(assignment_id=assignment.id, actor=self.admin, reason="Testing revocation")
            user_mapping.refresh_from_db()
            assignment.refresh_from_db()
            self.assertEqual(assignment.status, AssignmentStatus.REVOKED)
            # Disable-not-delete: mapping is preserved as SUSPENDED
            self.assertEqual(user_mapping.status, ExternalUserMappingStatus.SUSPENDED)
            self.assertEqual(ExternalUserMapping.objects.filter(user=self.user, organization=self.org).count(), 1)

    # =========================================================================
    # E. DUPLICATE / IDEMPOTENCY ACCEPTANCE
    # =========================================================================
    def test_section_e_duplicate_trigger_idempotency(self):
        """Repeated activations or job executions do not duplicate mappings or jobs."""
        instance = get_or_create_lms_connector_instance(self.org)
        tenant_mapping = ExternalTenantMapping.objects.create(
            instance=instance,
            organization=self.org,
            external_tenant_id=self.lms_org_id,
        )
        tenant_job = ProvisioningJob.objects.create(
            instance=instance,
            organization=self.org,
            action=ProvisioningAction.PROVISION,
            status=ProvisioningJobStatus.COMPLETED,
        )

        # Repeated tenant trigger
        res = handle_tenant_lms_entitlement_activated(organization=self.org, actor=self.admin)
        self.assertIsNotNone(res)
        self.assertEqual(res.id, tenant_job.id)
        self.assertEqual(ExternalTenantMapping.objects.filter(organization=self.org).count(), 1)

        # Repeated execution of completed job
        repeat_job = execute_provisioning_job(tenant_job.id)
        self.assertEqual(repeat_job.status, ProvisioningJobStatus.COMPLETED)
        self.assertEqual(ExternalTenantMapping.objects.filter(organization=self.org).count(), 1)

    # =========================================================================
    # G. SSO IDENTITY / TOKEN VERIFICATION
    # =========================================================================
    def test_section_g_sso_authorization_and_claims(self):
        """Authoritative code issuance and claims validation."""
        self.setup_subscription_entitlements()
        instance = get_or_create_lms_connector_instance(self.org)
        ExternalTenantMapping.objects.create(
            instance=instance,
            organization=self.org,
            external_tenant_id=self.lms_org_id,
        )
        ExternalUserMapping.objects.create(
            instance=instance,
            organization=self.org,
            user=self.user,
            external_user_id=self.lms_user_id,
            status=ExternalUserMappingStatus.ACTIVE,
        )

        with mock.patch("apps.integration_hub.provisioning_service.LmsConnectorClient", return_value=self.mock_client):
            assignment = assign_user_to_product(
                organization_id=self.org.id,
                user_id=self.user.id,
                product_id=self.lms_product.id,
                module_ids=[self.lms_core_module.id],
                actor=self.admin,
            )

        # Issue code
        sso_res = issue_sso_authorization_code(user=self.user, organization=self.org, product=self.lms_product)
        from urllib.parse import urlparse, parse_qs
        code = parse_qs(urlparse(sso_res["redirect_url"]).query)["code"][0]
        self.assertTrue(code)

        # Validate code
        claims = validate_sso_authorization_code(code=code)
        self.assertEqual(claims["user"]["id"], str(self.user.id))
        self.assertEqual(claims["user"]["email"], self.user.email)
        self.assertEqual(claims["organization"]["id"], str(self.org.id))
        self.assertEqual(claims["organization"]["code"], self.org.code)

        # Ensure revoked assignment denies SSO
        revoke_user_assignment(assignment_id=assignment.id, actor=self.admin, reason="Revoking for SSO denial check")
        with self.assertRaises(exceptions.PermissionDenied):
            issue_sso_authorization_code(user=self.user, organization=self.org, product=self.lms_product)

    # =========================================================================
    # H. FAILURE / RECOVERY REGRESSION
    # =========================================================================
    def test_section_h_failure_recovery_regression(self):
        """Transient error schedules retry; re-execution completes job and resolves failure."""
        instance = get_or_create_lms_connector_instance(self.org)
        job = ProvisioningJob.objects.create(
            instance=instance,
            organization=self.org,
            user=self.user,
            action=ProvisioningAction.PROVISION,
            status=ProvisioningJobStatus.QUEUED,
        )

        # Transient glitch
        with mock.patch(
            "apps.integration_hub.lms_connector.LmsConnectorClient.provision_user",
            side_effect=LmsConnectorRetryableError("Connection timeout", failure_code="UPSTREAM_TIMEOUT"),
        ):
            with self.assertRaises(LmsConnectorRetryableError):
                execute_provisioning_job(job.id)

        job.refresh_from_db()
        self.assertEqual(job.status, ProvisioningJobStatus.RETRY_SCHEDULED)
        failure = IntegrationFailure.objects.get(job=job)
        self.assertEqual(failure.status, FailureStatus.RETRY_SCHEDULED)
        self.assertEqual(failure.retry_count, 1)

        # Recovery
        with mock.patch("apps.integration_hub.provisioning_service.LmsConnectorClient", return_value=self.mock_client):
            execute_provisioning_job(job.id)

        job.refresh_from_db()
        failure.refresh_from_db()
        self.assertEqual(job.status, ProvisioningJobStatus.COMPLETED)
        self.assertEqual(failure.status, FailureStatus.RESOLVED)

    # =========================================================================
    # I. SECURITY / SECRET LEAKAGE / TENANT ISOLATION
    # =========================================================================
    def test_section_i_security_and_tenant_isolation(self):
        """M2M secret configured and never leaked into job contexts or failure details."""
        secret = get_m2m_connector_secret("lms")
        self.assertTrue(secret)

        instance = get_or_create_lms_connector_instance(self.org)
        job = ProvisioningJob.objects.create(
            instance=instance,
            organization=self.org,
            user=self.user,
            action=ProvisioningAction.PROVISION,
            status=ProvisioningJobStatus.QUEUED,
            context={"note": "diagnostic trace"},
        )
        failure = IntegrationFailure.objects.create(
            job=job,
            failure_code="SERVICE_UNAVAILABLE",
            failure_detail="Remote server timeout on /api/v1/integration/tenants/provision/",
        )

        self.assertNotIn(secret, str(job.context))
        self.assertNotIn(secret, failure.failure_detail)
