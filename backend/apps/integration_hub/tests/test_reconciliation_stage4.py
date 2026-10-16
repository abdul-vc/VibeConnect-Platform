"""Phase 5D — Stage 4 Reconciliation Remediation Orchestration Tests.

Verifies the 24 authoritative remediation scenarios defined in the Stage 2/4 contract:
1. missing tenant → PROVISION job
2. missing user → PROVISION job
3. inactive organization → DEPROVISION job
4. inactive user → DEPROVISION job
5. stale revoked assignment → DEPROVISION job
6. stale suspended assignment → DEPROVISION job
7. local mapping drift → SYNC job
8. assignment without entitlement → safety only, issue OPEN
9. duplicate tenant → no job
10. duplicate user → no job
11. cross-tenant mismatch → no job
12. identity contradiction → no job
13. orphan anomaly → no job
14. exact issue-to-job correlation
15. unrelated issue is never resolved
16. repeated remediation is idempotent
17. queued duplicate remediation is suppressed/reused
18. completed job re-remediation is no-op
19. rollback does not create job
20. successful job resolves only originating issue
21. failed job leaves issue OPEN
22. tenant TENANT_NOT_FOUND remediation path
23. user remote-missing condition is NOT auto-remediated
24. no hidden mutating calls from detection-only scan
"""

import uuid
from unittest import mock

from django.contrib.auth import get_user_model
from django.db import transaction
from django.test import TestCase
from django.utils import timezone

from apps.access_control.models import Role
from apps.assignments.models import AssignmentStatus, UserProductAssignment
from apps.entitlements.models import EntitlementStatus, OrganizationProductEntitlement
from apps.identity.models import UserStatus
from apps.integration_hub.lms_connector import LmsConnectorClient
from apps.integration_hub.models import (
    ConnectorInstance,
    ExternalTenantMapping,
    ExternalUserMapping,
    ExternalUserMappingStatus,
    InstanceStatus,
    IntegrationConnector,
    IntegrationReconciliationIssue,
    IntegrationReconciliationStatus,
    ProvisioningAction,
    ProvisioningJob,
    ProvisioningJobStatus,
)
from apps.integration_hub.provisioning_service import (
    TenantProvisioningError,
    UserProvisioningError,
    execute_provisioning_job,
    provision_tenant_to_lms,
    provision_user_to_lms,
)
from apps.integration_hub.reconciliation_service import (
    LmsReconciliationIssueCode,
    remediate_reconciliation_issue,
    run_lms_reconciliation,
    verify_and_resolve_reconciliation_issue,
)
from apps.organizations.models import (
    MembershipStatus,
    MembershipType,
    Organization,
    OrganizationMembership,
    OrganizationStatus,
)
from apps.product_registry.models import Product, ProductStatus

User = get_user_model()


class Stage4ReconciliationRemediationTests(TestCase):
    """Test suite for Phase 5D Stage 4 Remediation Orchestration."""

    def setUp(self):
        self.suffix = uuid.uuid4().hex[:8]

        # 1. Admin / Platform Owner
        self.admin = User.objects.create_user(
            email=f"admin_{self.suffix}@test.local",
            password="TestPassword123!",
            is_active=True,
        )
        if hasattr(self.admin, "is_platform_owner"):
            self.admin.is_platform_owner = True
            self.admin.save(update_fields=["is_platform_owner"])

        # 2. LMS Product & Connector
        self.product, _ = Product.objects.get_or_create(
            code="lms",
            defaults={
                "name": "Learning Management System",
                "status": ProductStatus.ACTIVE,
                "created_by": self.admin,
                "updated_by": self.admin,
            },
        )
        self.connector, _ = IntegrationConnector.objects.get_or_create(
            code="lms",
            defaults={
                "name": "LMS Connector",
                "product": self.product,
            },
        )

        # 3. Organization & Membership
        self.org = Organization.objects.create(
            name=f"Org {self.suffix}",
            code=f"org_{self.suffix}",
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

        # 4. Connector Instance
        self.instance = ConnectorInstance.objects.create(
            connector=self.connector,
            organization=self.org,
            status=InstanceStatus.ACTIVE,
            credential_ref="vault:secret/stage4",
        )

        # 5. Standard Test User
        self.user = User.objects.create_user(
            email=f"learner_{self.suffix}@test.local",
            password="TestPassword123!",
            is_active=True,
        )
        self.user_membership = OrganizationMembership.objects.create(
            organization=self.org,
            user=self.user,
            membership_type=MembershipType.MEMBER,
            status=MembershipStatus.ACTIVE,
            joined_at=timezone.now(),
        )

        # 6. Mock LMS Client
        self.mock_client = mock.MagicMock(spec=LmsConnectorClient)
        self.mock_client.provision_tenant.return_value = {
            "lms_organization_id": f"lms_org_{self.suffix}",
            "name": self.org.name,
            "status": "Active",
            "action_taken": "created",
        }
        self.mock_client.provision_user.return_value = {
            "lms_user_id": f"lms_usr_{self.suffix}",
            "email": self.user.email,
            "is_active": True,
            "action_taken": "created",
        }

    def _create_entitlement(self, status=EntitlementStatus.ACTIVE):
        return OrganizationProductEntitlement.objects.create(
            organization=self.org,
            product=self.product,
            status=status,
            created_by=self.admin,
            updated_by=self.admin,
        )

    def _create_assignment(self, user=None, status=AssignmentStatus.ACTIVE):
        u = user or self.user
        m = OrganizationMembership.objects.filter(organization=self.org, user=u).first()
        now = timezone.now()
        revoked_at = now if status == AssignmentStatus.REVOKED else None
        last_suspended_at = now if status == AssignmentStatus.SUSPENDED else None
        return UserProductAssignment.objects.create(
            organization=self.org,
            user=u,
            membership=m,
            product=self.product,
            status=status,
            created_by=self.admin,
            updated_by=self.admin,
            revoked_at=revoked_at,
            last_suspended_at=last_suspended_at,
        )

    def _create_tenant_mapping(self, external_id=None):
        return ExternalTenantMapping.objects.create(
            instance=self.instance,
            organization=self.org,
            external_tenant_id=external_id or f"lms_org_{self.suffix}",
        )

    def _create_user_mapping(self, user=None, external_id=None, status=ExternalUserMappingStatus.ACTIVE):
        return ExternalUserMapping.objects.create(
            instance=self.instance,
            organization=self.org,
            user=user or self.user,
            external_user_id=external_id or f"lms_usr_{self.suffix}",
            status=status,
        )

    def test_01_missing_tenant_mapping_creates_provision_job_and_resolves(self):
        """OPEN MISSING_TENANT_MAPPING creates PROVISION job, executes, and auto-resolves issue."""
        issue = IntegrationReconciliationIssue.objects.create(
            instance=self.instance,
            issue_code=LmsReconciliationIssueCode.MISSING_TENANT_MAPPING,
            status=IntegrationReconciliationStatus.OPEN,
            subject_type="organization",
            subject_id=str(self.org.id),
        )

        job = remediate_reconciliation_issue(issue, execute_now=True, client=self.mock_client)
        self.assertIsNotNone(job)
        self.assertEqual(job.action, ProvisioningAction.PROVISION)
        self.assertIsNone(job.user)
        self.assertEqual(job.status, ProvisioningJobStatus.COMPLETED)
        self.assertEqual(job.context.get("reconciliation_issue_id"), str(issue.id))

        # Mapping created
        mapping = ExternalTenantMapping.objects.filter(instance=self.instance, organization=self.org).first()
        self.assertIsNotNone(mapping)

        # Issue resolved
        issue.refresh_from_db()
        self.assertEqual(issue.status, IntegrationReconciliationStatus.RESOLVED)
        self.assertIsNotNone(issue.resolved_at)
        self.assertIn(str(job.id), issue.resolution_notes)

    def test_02_missing_user_mapping_creates_provision_job_and_resolves(self):
        """OPEN MISSING_USER_MAPPING creates PROVISION job and auto-resolves issue."""
        self._create_tenant_mapping()
        self._create_entitlement(status=EntitlementStatus.ACTIVE)
        self._create_assignment(user=self.user, status=AssignmentStatus.ACTIVE)

        issue = IntegrationReconciliationIssue.objects.create(
            instance=self.instance,
            issue_code=LmsReconciliationIssueCode.MISSING_USER_MAPPING,
            status=IntegrationReconciliationStatus.OPEN,
            subject_type="user",
            subject_id=str(self.user.id),
        )

        job = remediate_reconciliation_issue(issue, execute_now=True, client=self.mock_client)
        self.assertIsNotNone(job)
        self.assertEqual(job.action, ProvisioningAction.PROVISION)
        self.assertEqual(job.user, self.user)
        self.assertEqual(job.status, ProvisioningJobStatus.COMPLETED)

        # User mapping created
        mapping = ExternalUserMapping.objects.filter(instance=self.instance, user=self.user).first()
        self.assertIsNotNone(mapping)
        self.assertEqual(mapping.status, ExternalUserMappingStatus.ACTIVE)

        # Issue resolved
        issue.refresh_from_db()
        self.assertEqual(issue.status, IntegrationReconciliationStatus.RESOLVED)

    def test_03_inactive_organization_creates_deprovision_job_and_resolves(self):
        """OPEN ORGANIZATION_NOT_ACTIVE dispatches non-destructive DEPROVISION job and resolves."""
        self._create_tenant_mapping()
        self.org.status = OrganizationStatus.SUSPENDED
        self.org.save(update_fields=["status"])

        self.mock_client.provision_tenant.return_value = {
            "lms_organization_id": f"lms_org_{self.suffix}",
            "status": "Inactive",
            "action_taken": "updated",
        }

        issue = IntegrationReconciliationIssue.objects.create(
            instance=self.instance,
            issue_code=LmsReconciliationIssueCode.ORGANIZATION_NOT_ACTIVE,
            status=IntegrationReconciliationStatus.OPEN,
            subject_type="organization",
            subject_id=str(self.org.id),
        )

        job = remediate_reconciliation_issue(issue, execute_now=True, client=self.mock_client)
        self.assertIsNotNone(job)
        self.assertEqual(job.action, ProvisioningAction.DEPROVISION)
        self.assertEqual(job.status, ProvisioningJobStatus.COMPLETED)

        # LMS called with Inactive override
        self.mock_client.provision_tenant.assert_called_once()
        call_payload = self.mock_client.provision_tenant.call_args[0][0]
        self.assertEqual(call_payload["status"], "Inactive")

        issue.refresh_from_db()
        self.assertEqual(issue.status, IntegrationReconciliationStatus.RESOLVED)

    def test_04_inactive_user_creates_deprovision_job_and_resolves(self):
        """OPEN USER_INACTIVE_OR_SUSPENDED applies immediate safety containment, deprovisions, and resolves."""
        self._create_tenant_mapping()
        user_mapping = self._create_user_mapping(status=ExternalUserMappingStatus.ACTIVE)

        self.user.is_active = False
        self.user.save(update_fields=["is_active"])

        self.mock_client.provision_user.return_value = {
            "lms_user_id": user_mapping.external_user_id,
            "is_active": False,
            "action_taken": "updated",
        }

        issue = IntegrationReconciliationIssue.objects.create(
            instance=self.instance,
            issue_code=LmsReconciliationIssueCode.USER_INACTIVE_OR_SUSPENDED,
            status=IntegrationReconciliationStatus.OPEN,
            subject_type="user",
            subject_id=str(self.user.id),
        )

        job = remediate_reconciliation_issue(issue, execute_now=True, client=self.mock_client)
        self.assertIsNotNone(job)
        self.assertEqual(job.action, ProvisioningAction.DEPROVISION)

        user_mapping.refresh_from_db()
        self.assertEqual(user_mapping.status, ExternalUserMappingStatus.SUSPENDED)

        issue.refresh_from_db()
        self.assertEqual(issue.status, IntegrationReconciliationStatus.RESOLVED)

    def test_05_stale_user_mapping_revoked_creates_deprovision_job_and_resolves(self):
        """OPEN STALE_USER_MAPPING with REVOKED assignment creates DEPROVISION job and resolves."""
        self._create_tenant_mapping()
        self._create_entitlement(status=EntitlementStatus.ACTIVE)
        self._create_assignment(status=AssignmentStatus.REVOKED)
        user_mapping = self._create_user_mapping(status=ExternalUserMappingStatus.ACTIVE)

        self.mock_client.provision_user.return_value = {
            "lms_user_id": user_mapping.external_user_id,
            "is_active": False,
            "action_taken": "updated",
        }

        issue = IntegrationReconciliationIssue.objects.create(
            instance=self.instance,
            issue_code=LmsReconciliationIssueCode.STALE_USER_MAPPING,
            status=IntegrationReconciliationStatus.OPEN,
            subject_type="user",
            subject_id=str(self.user.id),
        )

        job = remediate_reconciliation_issue(issue, execute_now=True, client=self.mock_client)
        self.assertIsNotNone(job)
        self.assertEqual(job.action, ProvisioningAction.DEPROVISION)

        user_mapping.refresh_from_db()
        self.assertEqual(user_mapping.status, ExternalUserMappingStatus.SUSPENDED)

        issue.refresh_from_db()
        self.assertEqual(issue.status, IntegrationReconciliationStatus.RESOLVED)

    def test_06_stale_user_mapping_suspended_creates_deprovision_job_and_resolves(self):
        """OPEN STALE_USER_MAPPING with SUSPENDED assignment creates DEPROVISION job and resolves."""
        self._create_tenant_mapping()
        self._create_entitlement(status=EntitlementStatus.ACTIVE)
        self._create_assignment(status=AssignmentStatus.SUSPENDED)
        user_mapping = self._create_user_mapping(status=ExternalUserMappingStatus.ACTIVE)

        self.mock_client.provision_user.return_value = {
            "lms_user_id": user_mapping.external_user_id,
            "is_active": False,
            "action_taken": "updated",
        }

        issue = IntegrationReconciliationIssue.objects.create(
            instance=self.instance,
            issue_code=LmsReconciliationIssueCode.STALE_USER_MAPPING,
            status=IntegrationReconciliationStatus.OPEN,
            subject_type="user",
            subject_id=str(self.user.id),
        )

        job = remediate_reconciliation_issue(issue, execute_now=True, client=self.mock_client)
        self.assertIsNotNone(job)
        self.assertEqual(job.action, ProvisioningAction.DEPROVISION)

        user_mapping.refresh_from_db()
        self.assertEqual(user_mapping.status, ExternalUserMappingStatus.SUSPENDED)

        issue.refresh_from_db()
        self.assertEqual(issue.status, IntegrationReconciliationStatus.RESOLVED)

    def test_07_local_user_mapping_drift_creates_sync_job_and_resolves(self):
        """OPEN LOCAL_USER_MAPPING_DRIFT creates SYNC job, sets mapping ACTIVE, and resolves."""
        self._create_tenant_mapping()
        self._create_entitlement(status=EntitlementStatus.ACTIVE)
        self._create_assignment(status=AssignmentStatus.ACTIVE)
        user_mapping = self._create_user_mapping(status=ExternalUserMappingStatus.SUSPENDED)

        self.mock_client.provision_user.return_value = {
            "lms_user_id": user_mapping.external_user_id,
            "is_active": True,
            "action_taken": "updated",
        }

        issue = IntegrationReconciliationIssue.objects.create(
            instance=self.instance,
            issue_code=LmsReconciliationIssueCode.LOCAL_USER_MAPPING_DRIFT,
            status=IntegrationReconciliationStatus.OPEN,
            subject_type="user",
            subject_id=str(self.user.id),
        )

        job = remediate_reconciliation_issue(issue, execute_now=True, client=self.mock_client)
        self.assertIsNotNone(job)
        self.assertEqual(job.action, ProvisioningAction.SYNC)

        user_mapping.refresh_from_db()
        self.assertEqual(user_mapping.status, ExternalUserMappingStatus.ACTIVE)

        issue.refresh_from_db()
        self.assertEqual(issue.status, IntegrationReconciliationStatus.RESOLVED)

    def test_08_assignment_without_entitlement_safety_containment_only_issue_open(self):
        """ASSIGNMENT_WITHOUT_ENTITLEMENT applies safety containment, creates no jobs, remains OPEN."""
        self._create_tenant_mapping()
        user_mapping = self._create_user_mapping(status=ExternalUserMappingStatus.ACTIVE)

        issue = IntegrationReconciliationIssue.objects.create(
            instance=self.instance,
            issue_code=LmsReconciliationIssueCode.ASSIGNMENT_WITHOUT_ENTITLEMENT,
            status=IntegrationReconciliationStatus.OPEN,
            subject_type="user",
            subject_id=str(self.user.id),
        )

        job = remediate_reconciliation_issue(issue)
        self.assertIsNone(job)

        # Safety containment applied: mapping suspended
        user_mapping.refresh_from_db()
        self.assertEqual(user_mapping.status, ExternalUserMappingStatus.SUSPENDED)

        # Issue remains OPEN
        issue.refresh_from_db()
        self.assertEqual(issue.status, IntegrationReconciliationStatus.OPEN)

        # Zero provisioning jobs created
        self.assertEqual(ProvisioningJob.objects.count(), 0)

    def test_09_duplicate_tenant_quarantined_no_job(self):
        """DUPLICATE_EXTERNAL_TENANT creates zero jobs and remains OPEN."""
        issue = IntegrationReconciliationIssue.objects.create(
            instance=self.instance,
            issue_code=LmsReconciliationIssueCode.DUPLICATE_EXTERNAL_TENANT,
            status=IntegrationReconciliationStatus.OPEN,
            subject_type="organization",
            subject_id=str(self.org.id),
        )
        job = remediate_reconciliation_issue(issue)
        self.assertIsNone(job)
        issue.refresh_from_db()
        self.assertEqual(issue.status, IntegrationReconciliationStatus.OPEN)
        self.assertEqual(ProvisioningJob.objects.count(), 0)

    def test_10_duplicate_user_quarantined_no_job(self):
        """DUPLICATE_EXTERNAL_USER creates zero jobs and remains OPEN."""
        issue = IntegrationReconciliationIssue.objects.create(
            instance=self.instance,
            issue_code=LmsReconciliationIssueCode.DUPLICATE_EXTERNAL_USER,
            status=IntegrationReconciliationStatus.OPEN,
            subject_type="user",
            subject_id=str(self.user.id),
        )
        job = remediate_reconciliation_issue(issue)
        self.assertIsNone(job)
        issue.refresh_from_db()
        self.assertEqual(issue.status, IntegrationReconciliationStatus.OPEN)
        self.assertEqual(ProvisioningJob.objects.count(), 0)

    def test_11_cross_tenant_mismatch_quarantined_no_job(self):
        """CROSS_TENANT_MAPPING_MISMATCH creates zero jobs and remains OPEN."""
        issue = IntegrationReconciliationIssue.objects.create(
            instance=self.instance,
            issue_code=LmsReconciliationIssueCode.CROSS_TENANT_MAPPING_MISMATCH,
            status=IntegrationReconciliationStatus.OPEN,
            subject_type="user",
            subject_id=str(self.user.id),
        )
        job = remediate_reconciliation_issue(issue)
        self.assertIsNone(job)
        issue.refresh_from_db()
        self.assertEqual(issue.status, IntegrationReconciliationStatus.OPEN)
        self.assertEqual(ProvisioningJob.objects.count(), 0)

    def test_12_identity_contradiction_quarantined_no_job(self):
        """INCONSISTENT_MAPPED_IDENTITY creates zero jobs and remains OPEN."""
        issue = IntegrationReconciliationIssue.objects.create(
            instance=self.instance,
            issue_code=LmsReconciliationIssueCode.INCONSISTENT_MAPPED_IDENTITY,
            status=IntegrationReconciliationStatus.OPEN,
            subject_type="user",
            subject_id=str(self.user.id),
        )
        job = remediate_reconciliation_issue(issue)
        self.assertIsNone(job)
        issue.refresh_from_db()
        self.assertEqual(issue.status, IntegrationReconciliationStatus.OPEN)
        self.assertEqual(ProvisioningJob.objects.count(), 0)

    def test_13_orphan_anomaly_quarantined_no_job(self):
        """ORPHAN_MAPPING_LOCAL_ENTITY_MISSING creates zero jobs and remains OPEN."""
        issue = IntegrationReconciliationIssue.objects.create(
            instance=self.instance,
            issue_code=LmsReconciliationIssueCode.ORPHAN_MAPPING_LOCAL_ENTITY_MISSING,
            status=IntegrationReconciliationStatus.OPEN,
            subject_type="user",
            subject_id=str(uuid.uuid4()),
        )
        job = remediate_reconciliation_issue(issue)
        self.assertIsNone(job)
        issue.refresh_from_db()
        self.assertEqual(issue.status, IntegrationReconciliationStatus.OPEN)
        self.assertEqual(ProvisioningJob.objects.count(), 0)

    def test_14_exact_issue_to_job_correlation(self):
        """ProvisioningJob receives exact reconciliation_issue_id and code in its context."""
        issue = IntegrationReconciliationIssue.objects.create(
            instance=self.instance,
            issue_code=LmsReconciliationIssueCode.MISSING_TENANT_MAPPING,
            status=IntegrationReconciliationStatus.OPEN,
            subject_type="organization",
            subject_id=str(self.org.id),
        )
        job = remediate_reconciliation_issue(issue, execute_now=False)
        self.assertIsNotNone(job)
        self.assertEqual(job.context["reconciliation_issue_id"], str(issue.id))
        self.assertEqual(job.context["reconciliation_issue_code"], issue.issue_code)

    def test_15_unrelated_issue_is_never_resolved(self):
        """Completing a remediation job resolves ONLY its originating issue."""
        issue_a = IntegrationReconciliationIssue.objects.create(
            instance=self.instance,
            issue_code=LmsReconciliationIssueCode.MISSING_TENANT_MAPPING,
            status=IntegrationReconciliationStatus.OPEN,
            subject_type="organization",
            subject_id=str(self.org.id),
        )
        issue_b = IntegrationReconciliationIssue.objects.create(
            instance=self.instance,
            issue_code=LmsReconciliationIssueCode.ORGANIZATION_NOT_ACTIVE,
            status=IntegrationReconciliationStatus.OPEN,
            subject_type="organization",
            subject_id=str(self.org.id),
        )

        job_a = remediate_reconciliation_issue(issue_a, execute_now=True, client=self.mock_client)
        self.assertIsNotNone(job_a)

        issue_a.refresh_from_db()
        issue_b.refresh_from_db()

        self.assertEqual(issue_a.status, IntegrationReconciliationStatus.RESOLVED)
        self.assertEqual(issue_b.status, IntegrationReconciliationStatus.OPEN)

    def test_16_repeated_remediation_is_idempotent(self):
        """Repeated remediation calls for the same issue return the existing job."""
        issue = IntegrationReconciliationIssue.objects.create(
            instance=self.instance,
            issue_code=LmsReconciliationIssueCode.MISSING_TENANT_MAPPING,
            status=IntegrationReconciliationStatus.OPEN,
            subject_type="organization",
            subject_id=str(self.org.id),
        )
        job1 = remediate_reconciliation_issue(issue, execute_now=False)
        job2 = remediate_reconciliation_issue(issue, execute_now=False)

        self.assertEqual(job1.id, job2.id)
        self.assertEqual(ProvisioningJob.objects.count(), 1)

    def test_17_queued_duplicate_remediation_is_suppressed_or_reused(self):
        """Active queued job matching entity and action is correlated and reused."""
        pre_existing_job = ProvisioningJob.objects.create(
            instance=self.instance,
            organization=self.org,
            user=None,
            action=ProvisioningAction.PROVISION,
            status=ProvisioningJobStatus.QUEUED,
            context={"source": "manual"},
        )

        issue = IntegrationReconciliationIssue.objects.create(
            instance=self.instance,
            issue_code=LmsReconciliationIssueCode.MISSING_TENANT_MAPPING,
            status=IntegrationReconciliationStatus.OPEN,
            subject_type="organization",
            subject_id=str(self.org.id),
        )

        job = remediate_reconciliation_issue(issue, execute_now=False)
        self.assertEqual(job.id, pre_existing_job.id)
        self.assertEqual(job.context["reconciliation_issue_id"], str(issue.id))
        self.assertEqual(ProvisioningJob.objects.count(), 1)

    def test_18_completed_job_re_remediation_is_no_op(self):
        """Calling remediation on an issue where job has completed is a safe no-op."""
        issue = IntegrationReconciliationIssue.objects.create(
            instance=self.instance,
            issue_code=LmsReconciliationIssueCode.MISSING_TENANT_MAPPING,
            status=IntegrationReconciliationStatus.OPEN,
            subject_type="organization",
            subject_id=str(self.org.id),
        )
        job = remediate_reconciliation_issue(issue, execute_now=True, client=self.mock_client)
        self.assertEqual(job.status, ProvisioningJobStatus.COMPLETED)

        # Subsequent remediation call does not create new job
        job2 = remediate_reconciliation_issue(issue, execute_now=False)
        self.assertEqual(ProvisioningJob.objects.count(), 1)

    def test_19_rollback_does_not_create_job(self):
        """Atomic rollback leaves zero remediation jobs in the database."""
        issue = IntegrationReconciliationIssue.objects.create(
            instance=self.instance,
            issue_code=LmsReconciliationIssueCode.MISSING_TENANT_MAPPING,
            status=IntegrationReconciliationStatus.OPEN,
            subject_type="organization",
            subject_id=str(self.org.id),
        )

        try:
            with transaction.atomic():
                remediate_reconciliation_issue(issue, execute_now=False)
                raise RuntimeError("Simulated transaction failure")
        except RuntimeError:
            pass

        self.assertEqual(ProvisioningJob.objects.count(), 0)

    def test_20_successful_job_resolves_only_originating_issue(self):
        """Verifies verify_and_resolve_reconciliation_issue sets status, timestamps, and notes."""
        issue = IntegrationReconciliationIssue.objects.create(
            instance=self.instance,
            issue_code=LmsReconciliationIssueCode.MISSING_TENANT_MAPPING,
            status=IntegrationReconciliationStatus.OPEN,
            subject_type="organization",
            subject_id=str(self.org.id),
        )
        job = remediate_reconciliation_issue(issue, execute_now=True, client=self.mock_client)

        issue.refresh_from_db()
        self.assertEqual(issue.status, IntegrationReconciliationStatus.RESOLVED)
        self.assertIsNotNone(issue.resolved_at)
        self.assertIn("Auto-resolved: Tenant mapping created", issue.resolution_notes)

    def test_21_failed_job_leaves_issue_open(self):
        """When remediation job fails remotely, issue remains OPEN."""
        issue = IntegrationReconciliationIssue.objects.create(
            instance=self.instance,
            issue_code=LmsReconciliationIssueCode.MISSING_TENANT_MAPPING,
            status=IntegrationReconciliationStatus.OPEN,
            subject_type="organization",
            subject_id=str(self.org.id),
        )

        self.mock_client.provision_tenant.side_effect = TenantProvisioningError(
            "LMS service 503 unavailable",
            code="SERVICE_UNAVAILABLE",
        )

        try:
            remediate_reconciliation_issue(issue, execute_now=True, client=self.mock_client)
        except TenantProvisioningError:
            pass

        job = ProvisioningJob.objects.first()
        self.assertEqual(job.status, ProvisioningJobStatus.RETRY_SCHEDULED)

        issue.refresh_from_db()
        self.assertEqual(issue.status, IntegrationReconciliationStatus.OPEN)

    def test_22_tenant_not_found_remediation_path(self):
        """REMOTE_RECORD_MISSING for tenant executes PROVISION, updates mapping, and resolves."""
        self._create_tenant_mapping(external_id="lms_stale_ghost_org")

        self.mock_client.provision_tenant.return_value = {
            "lms_organization_id": f"lms_org_recreated_{self.suffix}",
            "status": "Active",
            "action_taken": "created",
        }

        issue = IntegrationReconciliationIssue.objects.create(
            instance=self.instance,
            issue_code=LmsReconciliationIssueCode.REMOTE_RECORD_MISSING,
            status=IntegrationReconciliationStatus.OPEN,
            subject_type="organization",
            subject_id=str(self.org.id),
            details={"error_code": "TENANT_NOT_FOUND"},
        )

        job = remediate_reconciliation_issue(issue, execute_now=True, client=self.mock_client)
        self.assertIsNotNone(job)
        self.assertEqual(job.action, ProvisioningAction.PROVISION)
        self.assertEqual(job.status, ProvisioningJobStatus.COMPLETED)

        # Mapping updated with new remote ID
        mapping = ExternalTenantMapping.objects.get(instance=self.instance, organization=self.org)
        self.assertEqual(mapping.external_tenant_id, f"lms_org_recreated_{self.suffix}")

        issue.refresh_from_db()
        self.assertEqual(issue.status, IntegrationReconciliationStatus.RESOLVED)

    def test_23_user_remote_missing_condition_is_not_auto_remediated(self):
        """User REMOTE_RECORD_MISSING is NOT auto-remediated; issue remains OPEN."""
        issue = IntegrationReconciliationIssue.objects.create(
            instance=self.instance,
            issue_code=LmsReconciliationIssueCode.REMOTE_RECORD_MISSING,
            status=IntegrationReconciliationStatus.OPEN,
            subject_type="user",
            subject_id=str(self.user.id),
        )

        job = remediate_reconciliation_issue(issue)
        self.assertIsNone(job)
        issue.refresh_from_db()
        self.assertEqual(issue.status, IntegrationReconciliationStatus.OPEN)
        self.assertEqual(ProvisioningJob.objects.count(), 0)

    @mock.patch.object(LmsConnectorClient, "provision_tenant")
    @mock.patch.object(LmsConnectorClient, "provision_user")
    def test_24_no_hidden_mutating_calls_from_detection_only_scan(self, mock_user, mock_tenant):
        """Ordinary run_lms_reconciliation detection scan never executes mutating calls."""
        self._create_entitlement(status=EntitlementStatus.ACTIVE)
        # Scan with missing mappings
        issues = run_lms_reconciliation(instance_id=str(self.instance.id))
        self.assertGreater(len(issues), 0)

        mock_tenant.assert_not_called()
        mock_user.assert_not_called()

    def test_25_originating_issue_already_resolved_causes_no_unrelated_resolutions(self):
        """If originating issue was already resolved prior to job completion, verify no other issue is touched."""
        issue_a = IntegrationReconciliationIssue.objects.create(
            instance=self.instance,
            issue_code=LmsReconciliationIssueCode.MISSING_TENANT_MAPPING,
            status=IntegrationReconciliationStatus.RESOLVED,
            subject_type="organization",
            subject_id=str(self.org.id),
            resolution_notes="Previously resolved manually",
        )
        issue_b = IntegrationReconciliationIssue.objects.create(
            instance=self.instance,
            issue_code=LmsReconciliationIssueCode.ORGANIZATION_NOT_ACTIVE,
            status=IntegrationReconciliationStatus.OPEN,
            subject_type="organization",
            subject_id=str(self.org.id),
        )

        job = ProvisioningJob.objects.create(
            instance=self.instance,
            organization=self.org,
            user=None,
            action=ProvisioningAction.PROVISION,
            status=ProvisioningJobStatus.COMPLETED,
            context={
                "reconciliation_issue_id": str(issue_a.id),
                "reconciliation_issue_code": issue_a.issue_code,
                "result": {"status": "success"},
            },
        )

        # Call verification directly
        result_issue = verify_and_resolve_reconciliation_issue(job)
        self.assertEqual(result_issue.id, issue_a.id)

        issue_a.refresh_from_db()
        issue_b.refresh_from_db()

        self.assertEqual(issue_a.status, IntegrationReconciliationStatus.RESOLVED)
        self.assertEqual(issue_a.resolution_notes, "Previously resolved manually")
        self.assertEqual(issue_b.status, IntegrationReconciliationStatus.OPEN)

    def test_26_post_remediation_verification_mismatch_leaves_issue_open(self):
        """If external tenant ID in result does not match created mapping, issue remains OPEN."""
        issue = IntegrationReconciliationIssue.objects.create(
            instance=self.instance,
            issue_code=LmsReconciliationIssueCode.MISSING_TENANT_MAPPING,
            status=IntegrationReconciliationStatus.OPEN,
            subject_type="organization",
            subject_id=str(self.org.id),
        )

        # Existing mapping has different ID
        self._create_tenant_mapping(external_id="actual_local_id")

        job = ProvisioningJob.objects.create(
            instance=self.instance,
            organization=self.org,
            user=None,
            action=ProvisioningAction.PROVISION,
            status=ProvisioningJobStatus.COMPLETED,
            context={
                "reconciliation_issue_id": str(issue.id),
                "reconciliation_issue_code": issue.issue_code,
                "result": {
                    "status": "success",
                    "external_tenant_id": "unexpected_remote_id_mismatch",
                },
            },
        )

        result_issue = verify_and_resolve_reconciliation_issue(job)
        self.assertIsNone(result_issue)

        issue.refresh_from_db()
        self.assertEqual(issue.status, IntegrationReconciliationStatus.OPEN)

