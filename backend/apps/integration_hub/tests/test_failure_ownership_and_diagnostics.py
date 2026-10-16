"""Regression tests for IntegrationFailure serialization and cross-tenant ownership consistency."""

import uuid
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.access_control.constants import PREDEFINED_SUPPORT_ROLES
from apps.access_control.models import PlatformRoleAssignment, Role
from apps.integration_hub.models import (
    ConnectorInstance,
    ConnectorStatus,
    FailureStatus,
    FailureType,
    InstanceStatus,
    IntegrationConnector,
    IntegrationEvent,
    IntegrationFailure,
    ProvisioningAction,
    ProvisioningJob,
    ProvisioningJobStatus,
)
from apps.integration_hub.support_serializers import SupportFailureDiagnosticSerializer
from apps.organizations.models import Organization, OrganizationStatus
from apps.product_registry.models import ProductStatus, Product
from apps.reports.analytics_views import compute_component_integration_health

User = get_user_model()


class FailureOwnershipAndDiagnosticsTests(TestCase):
    def setUp(self):
        super().setUp()
        self.client = APIClient()

        # Platform Owner
        self.owner = User.objects.create_user(
            email=f"owner_{uuid.uuid4().hex[:6]}@vibeconnect.local",
            password="TestPassword123!",
            full_name="Platform Owner",
            is_active=True,
            is_platform_owner=True,
        )

        # Support Operator
        self.operator = User.objects.create_user(
            email=f"operator_{uuid.uuid4().hex[:6]}@vibeconnect.local",
            password="TestPassword123!",
            full_name="Support Operator",
            is_active=True,
            is_platform_owner=False,
        )
        support_role = Role.objects.filter(code="support_operator").first()
        if support_role:
            PlatformRoleAssignment.objects.create(user=self.operator, role=support_role)

        # Product & Connector
        self.product = Product.objects.create(
            name="Test Product",
            code=f"prod_{uuid.uuid4().hex[:6]}",
            status=ProductStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )


        self.connector = IntegrationConnector.objects.create(
            code=f"conn_{uuid.uuid4().hex[:6]}",
            name="Test Connector",
            product=self.product,
            status=ConnectorStatus.ACTIVE,
        )


        # Organizations
        self.org_a = Organization.objects.create(
            code="tenant_a",
            name="Tenant A",
            status=OrganizationStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )
        self.org_b = Organization.objects.create(
            code="tenant_b",
            name="Tenant B",
            status=OrganizationStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )

        # Instances
        self.inst_a = ConnectorInstance.objects.create(
            connector=self.connector,
            organization=self.org_a,
            status=InstanceStatus.ACTIVE,
            credential_ref="vault://cred-a",
        )
        self.inst_b = ConnectorInstance.objects.create(
            connector=self.connector,
            organization=self.org_b,
            status=InstanceStatus.ACTIVE,
            credential_ref="vault://cred-b",
        )

        # Jobs
        self.job_a = ProvisioningJob.objects.create(
            instance=self.inst_a,
            organization=self.org_a,
            action=ProvisioningAction.PROVISION,
            status=ProvisioningJobStatus.FAILED,
        )
        self.job_b = ProvisioningJob.objects.create(
            instance=self.inst_b,
            organization=self.org_b,
            action=ProvisioningAction.PROVISION,
            status=ProvisioningJobStatus.FAILED,
        )

        # Events
        self.event_a = IntegrationEvent.objects.create(
            instance=self.inst_a,
            event_type="test.event",
            event_key=f"evt_{uuid.uuid4().hex}",
            occurred_at=timezone.now(),
        )
        self.event_b = IntegrationEvent.objects.create(
            instance=self.inst_b,
            event_type="test.event",
            event_key=f"evt_{uuid.uuid4().hex}",
            occurred_at=timezone.now(),
        )

    def test_serializer_and_diagnostics_view_success(self):
        failure = IntegrationFailure.objects.create(
            job=self.job_a,
            failure_code="PROV_ERR",
            failure_detail="Detailed error message",
            status=FailureStatus.OPEN,
        )
        # 1. Serializer does not raise ImproperlyConfigured
        serializer = SupportFailureDiagnosticSerializer(failure)
        data = serializer.data
        self.assertEqual(data["id"], str(failure.id))
        self.assertNotIn("updated_at", data)
        self.assertIn("created_at", data)
        self.assertIn("instance_id", data)

        # 2. Support diagnostic detail view returns 200 without crashing
        self.client.force_authenticate(user=self.owner)
        res = self.client.get(f"/api/v1/support/organizations/{self.org_a.id}/diagnostics/")
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        open_fails = res.data.get("open_failures", [])
        self.assertTrue(any(f["id"] == str(failure.id) for f in open_fails))

    def test_tenant_isolation_and_deduplication(self):
        # Failure 1: Tenant A via Job
        fail_a1 = IntegrationFailure.objects.create(
            job=self.job_a,
            failure_code="ERR_JOB_A",
        )
        # Failure 2: Tenant A via Event
        fail_a2 = IntegrationFailure.objects.create(
            event=self.event_a,
            failure_code="ERR_EVT_A",
        )
        # Failure 3: Tenant A via BOTH Job and Event
        fail_a3 = IntegrationFailure.objects.create(
            job=self.job_a,
            event=self.event_a,
            failure_code="ERR_BOTH_A",
        )
        # Failure 4: Tenant B via Job
        fail_b = IntegrationFailure.objects.create(
            job=self.job_b,
            failure_code="ERR_JOB_B",
        )

        # Query Tenant A
        qs_a = IntegrationFailure.objects.filter(
            IntegrationFailure.org_scope_filter(self.org_a)
        ).distinct()
        ids_a = set(qs_a.values_list("id", flat=True))

        self.assertIn(fail_a1.id, ids_a)
        self.assertIn(fail_a2.id, ids_a)
        self.assertIn(fail_a3.id, ids_a)
        self.assertNotIn(fail_b.id, ids_a)
        self.assertEqual(qs_a.count(), 3)

        # Query Tenant B
        qs_b = IntegrationFailure.objects.filter(
            IntegrationFailure.org_scope_filter(self.org_b)
        ).distinct()
        ids_b = set(qs_b.values_list("id", flat=True))

        self.assertIn(fail_b.id, ids_b)
        self.assertNotIn(fail_a1.id, ids_b)
        self.assertNotIn(fail_a2.id, ids_b)
        self.assertNotIn(fail_a3.id, ids_b)
        self.assertEqual(qs_b.count(), 1)

    def test_cross_tenant_mismatch_rejected_at_write_boundary(self):
        # Attempt to create failure linking Job in Tenant A and Event in Tenant B
        mismatched_failure = IntegrationFailure(
            job=self.job_a,
            event=self.event_b,
            failure_code="MISMATCH_ERR",
        )
        with self.assertRaises(ValidationError) as ctx:
            mismatched_failure.clean()
        self.assertIn("Cross-tenant association conflict", str(ctx.exception))

        with self.assertRaises(ValidationError):
            mismatched_failure.save()

    def test_corrupted_mismatched_record_fails_closed_in_queries_and_actions(self):
        # Force-create a mismatched record bypassing save() to simulate legacy corrupt data
        corrupt_id = uuid.uuid4()
        IntegrationFailure.objects.bulk_create([
            IntegrationFailure(
                id=corrupt_id,
                job=self.job_a,
                event=self.event_b,
                failure_code="CORRUPT_LEGACY",
                status=FailureStatus.OPEN,
            )
        ])

        # Excluded from Tenant A queries
        qs_a = IntegrationFailure.objects.filter(
            IntegrationFailure.org_scope_filter(self.org_a)
        )
        self.assertFalse(qs_a.filter(id=corrupt_id).exists())

        # Excluded from Tenant B queries
        qs_b = IntegrationFailure.objects.filter(
            IntegrationFailure.org_scope_filter(self.org_b)
        )
        self.assertFalse(qs_b.filter(id=corrupt_id).exists())

        # Excluded from diagnostics endpoint for both tenants
        self.client.force_authenticate(user=self.owner)
        res_a = self.client.get(f"/api/v1/support/organizations/{self.org_a.id}/diagnostics/")
        self.assertFalse(any(f["id"] == str(corrupt_id) for f in res_a.data.get("open_failures", [])))

        res_b = self.client.get(f"/api/v1/support/organizations/{self.org_b.id}/diagnostics/")
        self.assertFalse(any(f["id"] == str(corrupt_id) for f in res_b.data.get("open_failures", [])))

        # Mutation endpoints fail closed (404 Not Found) for both tenants
        retry_res_a = self.client.post(
            f"/api/v1/support/organizations/{self.org_a.id}/failures/{corrupt_id}/retry/",
            data={"reason": "Attempting retry on corrupt record"},
            format="json",
        )
        self.assertEqual(retry_res_a.status_code, status.HTTP_404_NOT_FOUND)

        retry_res_b = self.client.post(
            f"/api/v1/support/organizations/{self.org_b.id}/failures/{corrupt_id}/retry/",
            data={"reason": "Attempting retry on corrupt record"},
            format="json",
        )
        self.assertEqual(retry_res_b.status_code, status.HTTP_404_NOT_FOUND)

        # Analytics health computation ignores corrupt record
        health_a = compute_component_integration_health(self.org_a)
        self.assertEqual(health_a["open_failures"], 0)
        health_b = compute_component_integration_health(self.org_b)
        self.assertEqual(health_b["open_failures"], 0)


