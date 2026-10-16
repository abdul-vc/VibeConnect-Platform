"""Phase 5G Stage 5 Tests: Integration Health Hardening & Operational Visibility.

Validates the 5G-5 contract:
1. Health response includes new operational metrics (queued, stuck, retry backlog, dead letter, recent failures, failure rate).
2. Health status transitions deterministically (healthy -> degraded -> attention_required) based on evidence.
3. Healthy control plane does not falsely report external connectivity as verified.
4. Explicit LMS probe behaves safely according to the actual available connector contract.
5. Unauthorized health access remains blocked (401 anonymous, 403 non-owner).
"""

from datetime import timedelta
import unittest.mock as mock
import uuid

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.integration_hub.models import (
    ConnectorInstance,
    ConnectorStatus,
    FailureStatus,
    FailureType,
    InstanceStatus,
    IntegrationConnector,
    IntegrationFailure,
    ProvisioningAction,
    ProvisioningJob,
    ProvisioningJobStatus,
)
from apps.organizations.models import (
    MembershipStatus,
    MembershipType,
    Organization,
    OrganizationMembership,
    OrganizationStatus,
)
from apps.product_registry.models import CatalogStatus, Product

User = get_user_model()


class Stage5HealthEndpointTestCase(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(
            email=f"owner_{uuid.uuid4().hex[:6]}@vibeconnect.local",
            password="TestPassword123!",
            full_name="Platform Owner",
            is_active=True,
        )
        if hasattr(self.owner, "is_platform_owner"):
            self.owner.is_platform_owner = True
            self.owner.save(update_fields=["is_platform_owner"])

        self.regular_user = User.objects.create_user(
            email=f"member_{uuid.uuid4().hex[:6]}@vibeconnect.local",
            password="TestPassword123!",
            full_name="Regular Member",
            is_active=True,
        )

        self.org = Organization.objects.create(
            name="Stage 5 Test Org",
            code=f"s5-{uuid.uuid4().hex[:6]}",
            status=OrganizationStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )
        OrganizationMembership.objects.create(
            organization=self.org,
            user=self.owner,
            membership_type=MembershipType.MEMBER,
            status=MembershipStatus.ACTIVE,
            joined_at=timezone.now(),
        )
        self.product = Product.objects.create(
            code=f"lms-{uuid.uuid4().hex[:6]}",
            name="LMS Product",
            status=CatalogStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )
        self.connector = IntegrationConnector.objects.create(
            code=f"lms-conn-{uuid.uuid4().hex[:6]}",
            name="LMS Test Connector",
            product=self.product,
            status=ConnectorStatus.ACTIVE,
        )
        self.instance = ConnectorInstance.objects.create(
            connector=self.connector,
            organization=self.org,
            label="LMS Test Instance",
            credential_ref=f"vault://creds/{uuid.uuid4().hex[:6]}",
            config={"base_url": "https://lms.test.internal"},
            status=InstanceStatus.ACTIVE,
        )

        self.client = APIClient()

    # -------------------------------------------------------------------------
    # 1. Health response includes new operational metrics
    # -------------------------------------------------------------------------

    def test_01_health_response_includes_new_operational_metrics(self):
        """Health endpoint returns queued, stuck, retry backlog, dead-letter, and failure rate metrics."""
        self.client.force_authenticate(user=self.owner)

        # Fresh queued job
        job_queued = ProvisioningJob.objects.create(
            instance=self.instance,
            organization=self.org,
            action=ProvisioningAction.PROVISION,
            status=ProvisioningJobStatus.QUEUED,
        )

        # Stuck queued job (> 1800s)
        job_stuck = ProvisioningJob.objects.create(
            instance=self.instance,
            organization=self.org,
            action=ProvisioningAction.PROVISION,
            status=ProvisioningJobStatus.QUEUED,
        )
        stale_time = timezone.now() - timedelta(hours=2)
        ProvisioningJob.objects.filter(pk=job_stuck.id).update(created_at=stale_time, updated_at=stale_time)

        # Failures: open, retry-scheduled, dead-letter, resolved
        IntegrationFailure.objects.create(
            job=job_queued,
            failure_code="ERR_OPEN",
            status=FailureStatus.OPEN,
        )
        IntegrationFailure.objects.create(
            job=job_queued,
            failure_code="ERR_RETRY",
            status=FailureStatus.RETRY_SCHEDULED,
            retry_count=1,
            max_retries=3,
        )
        IntegrationFailure.objects.create(
            job=job_stuck,
            failure_code="ERR_DEAD",
            status=FailureStatus.DEAD_LETTER,
            failure_type=FailureType.PERMANENT,
        )
        IntegrationFailure.objects.create(
            job=job_queued,
            failure_code="ERR_RESOLVED",
            status=FailureStatus.RESOLVED,
            resolved_at=timezone.now(),
        )

        res = self.client.get("/api/v1/integration/health/")
        self.assertEqual(res.status_code, 200)

        # Operational metrics in summary
        self.assertIn("summary", res.data)
        summary = res.data["summary"]
        self.assertEqual(summary["queued_job_count"], 2)
        self.assertEqual(summary["stuck_queued_job_count"], 1)
        self.assertEqual(summary["stuck_processing_job_count"], 0)
        self.assertEqual(summary["retry_scheduled_count"], 1)
        self.assertEqual(summary["dead_letter_count"], 1)
        self.assertEqual(summary["open_failure_count"], 1)
        self.assertEqual(summary["resolved_failure_count"], 1)
        self.assertEqual(summary["recent_failure_count"], 4)
        self.assertIsInstance(summary["failure_rate"], (int, float))

        # Operational metrics in jobs and failures
        self.assertIn("jobs", res.data)
        self.assertEqual(res.data["jobs"]["queued_job_count"], 2)
        self.assertEqual(res.data["jobs"]["stuck_queued_job_count"], 1)

        self.assertIn("failures", res.data)
        self.assertEqual(res.data["failures"]["open_failure_count"], 1)
        self.assertEqual(res.data["failures"]["retry_scheduled_count"], 1)
        self.assertEqual(res.data["failures"]["dead_letter_count"], 1)

    # -------------------------------------------------------------------------
    # 2. Health status changes correctly based on conditions
    # -------------------------------------------------------------------------

    def test_02_health_status_changes_correctly(self):
        """Status shifts deterministically: healthy -> degraded -> attention_required."""
        self.client.force_authenticate(user=self.owner)

        # Baseline: No failures, no stuck jobs, active connector -> healthy
        res_healthy = self.client.get("/api/v1/integration/health/")
        self.assertEqual(res_healthy.status_code, 200)
        self.assertEqual(res_healthy.data["control_plane"]["status"], "healthy")

        # Transient issue: add a RETRY_SCHEDULED failure -> degraded
        job = ProvisioningJob.objects.create(
            instance=self.instance,
            organization=self.org,
            action=ProvisioningAction.PROVISION,
            status=ProvisioningJobStatus.RETRY_SCHEDULED,
        )
        fail_retry = IntegrationFailure.objects.create(
            job=job,
            failure_code="TRANSIENT_TIMEOUT",
            status=FailureStatus.RETRY_SCHEDULED,
            retry_count=1,
            max_retries=3,
        )
        res_degraded = self.client.get("/api/v1/integration/health/")
        self.assertEqual(res_degraded.data["control_plane"]["status"], "degraded")

        # Critical issue: add a DEAD_LETTER failure -> attention_required
        fail_retry.status = FailureStatus.RESOLVED
        fail_retry.save(update_fields=["status"])
        IntegrationFailure.objects.create(
            job=job,
            failure_code="PERM_FAIL",
            status=FailureStatus.DEAD_LETTER,
            failure_type=FailureType.PERMANENT,
        )
        res_attention = self.client.get("/api/v1/integration/health/")
        self.assertEqual(res_attention.data["control_plane"]["status"], "attention_required")

    # -------------------------------------------------------------------------
    # 3. Healthy state does not falsely report external connectivity as verified
    # -------------------------------------------------------------------------

    def test_03_healthy_control_plane_does_not_falsely_report_external_verified(self):
        """Healthy control-plane never claims downstream SaaS availability without explicit probe."""
        self.client.force_authenticate(user=self.owner)

        res = self.client.get("/api/v1/integration/health/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["control_plane"]["status"], "healthy")

        ext = res.data["external_connectivity"]
        self.assertEqual(ext["status"], "not_verified")
        self.assertEqual(ext["verified_connectors_count"], 0)
        self.assertFalse(ext.get("probed", False))
        self.assertIn("Control-plane layer only", ext["detail"])

    # -------------------------------------------------------------------------
    # 4. Explicit LMS probe behaves safely according to available contract
    # -------------------------------------------------------------------------

    def test_04_explicit_lms_probe_behaves_safely(self):
        """Operator-invoked probe evaluates external readiness safely without business mutations."""
        self.client.force_authenticate(user=self.owner)

        # 4a: Mock client returning verified 200
        with mock.patch("apps.integration_hub.lms_connector.LmsConnectorClient.probe_connectivity") as mock_probe:
            mock_probe.return_value = {
                "status": "verified",
                "http_status": 200,
                "latency_ms": 35,
                "detail": "LMS integration endpoint responded successfully to health probe.",
            }
            res_probe = self.client.get("/api/v1/integration/health/?probe=true")
            self.assertEqual(res_probe.status_code, 200)
            ext = res_probe.data["external_connectivity"]
            self.assertEqual(ext["status"], "verified")
            self.assertEqual(ext["verified_connectors_count"], 1)
            self.assertTrue(ext["probed"])
            self.assertEqual(ext["http_status"], 200)
            self.assertEqual(ext["latency_ms"], 35)

        # 4b: Contract limitation: LMS returns 404 (read-only endpoint not supported) -> not_verified
        with mock.patch("apps.integration_hub.lms_connector.LmsConnectorClient.probe_connectivity") as mock_probe_404:
            mock_probe_404.return_value = {
                "status": "not_verified",
                "http_status": 404,
                "latency_ms": 20,
                "detail": "External LMS does not expose a supported read-only health endpoint. Status remains not_verified.",
            }
            res_404 = self.client.get("/api/v1/integration/health/?probe=true")
            self.assertEqual(res_404.status_code, 200)
            ext_404 = res_404.data["external_connectivity"]
            self.assertEqual(ext_404["status"], "not_verified")
            self.assertEqual(ext_404["verified_connectors_count"], 0)
            self.assertTrue(ext_404["probed"])

        # 4c: Configuration missing or network unreachable
        with mock.patch("apps.integration_hub.lms_connector.LmsConnectorClient.probe_connectivity") as mock_probe_err:
            mock_probe_err.return_value = {
                "status": "unreachable",
                "http_status": None,
                "latency_ms": None,
                "detail": "Network error or timeout reaching LMS: Connection refused",
            }
            res_err = self.client.get("/api/v1/integration/health/?probe=true")
            self.assertEqual(res_err.status_code, 200)
            ext_err = res_err.data["external_connectivity"]
            self.assertEqual(ext_err["status"], "unreachable")
            self.assertEqual(ext_err["verified_connectors_count"], 0)

    # -------------------------------------------------------------------------
    # 5. Unauthorized health access remains blocked
    # -------------------------------------------------------------------------

    def test_05_unauthorized_health_access_blocked(self):
        """Anonymous access is rejected with 401; non-owner is rejected with 403."""
        # Anonymous request
        self.client.logout()
        res_anon = self.client.get("/api/v1/integration/health/")
        self.assertEqual(res_anon.status_code, 401)

        # Non-owner member
        self.client.force_authenticate(user=self.regular_user)
        res_member = self.client.get("/api/v1/integration/health/")
        self.assertEqual(res_member.status_code, 403)
