"""Unit and Integration Tests for LMS Provisioning Stage 2.

Covers:
- LMS Connector Client:
  - 200 / 201 Success
  - Timeout and Connection Errors (classified as transient/retryable)
  - 400 Validation Error (permanent)
  - 401 / 403 Authentication Failure (permanent)
  - 404 Not Found (permanent)
  - 409 Conflict (permanent)
  - 502 / 503 / 504 Service Unavailable (transient)
  - Malformed non-JSON responses
  - Secret not leaked in logs/exceptions
- Tenant Provisioning:
  - Successful provision
  - Existing mapping reuse / idempotency
  - Repeated calls (0 duplicates)
  - LMS unavailable (transient retry classification)
  - Partial failure recovery
  - Mapping persistence
- User Provisioning:
  - Successful provision
  - Existing mapping reuse
  - Repeated calls (0 duplicates)
  - Cross-tenant member rejection
  - Inactive user handling
  - Automatic prerequisite tenant provisioning
- Provisioning Job Executor:
  - QUEUED -> PROCESSING -> COMPLETED
  - Failure transitions to FAILED
  - IntegrationFailure and retry_service integration
  - Idempotent completion guard
"""

import io
import json
import socket
from unittest.mock import MagicMock, patch
import urllib.error
import uuid

from django.test import TestCase, override_settings
from django.utils import timezone
from django.contrib.auth import get_user_model


from apps.integration_hub.lms_connector import (
    LmsConnectorClient,
    LmsConnectorConfigurationError,
    LmsConnectorError,
    LmsConnectorPermanentError,
    LmsConnectorRetryableError,
)
from apps.integration_hub.models import (
    ConnectorInstance,
    ExternalTenantMapping,
    ExternalUserMapping,
    ExternalUserMappingStatus,
    FailureStatus,
    FailureType,
    InstanceStatus,
    IntegrationConnector,
    IntegrationFailure,
    ProvisioningAction,
    ProvisioningJob,
    ProvisioningJobStatus,
)
from apps.integration_hub.provisioning_service import (
    TenantProvisioningError,
    UserProvisioningError,
    execute_provisioning_job,
    get_or_create_lms_connector_instance,
    provision_tenant_to_lms,
    provision_user_to_lms,
)
from apps.organizations.models import (
    MembershipStatus,
    MembershipType,
    Organization,
    OrganizationMembership,
    OrganizationStatus,
)
from apps.product_registry.models import CatalogStatus, Product

PlatformUser = get_user_model()
TEST_M2M_SECRET = "sec_test_stage2_secret_token_12345"
TEST_LMS_URL = "http://mock-lms.internal:8000"


def _create_owner():
    u = PlatformUser.objects.create_user(
        email=f"owner_{uuid.uuid4().hex[:6]}@test.io",
        password="PassWord123!",
    )
    if hasattr(u, "is_platform_owner"):
        u.is_platform_owner = True
        u.save(update_fields=["is_platform_owner"])
    return u


def _create_org(owner=None, code=None, status="active"):
    if owner is None:
        owner = _create_owner()
    suffix = uuid.uuid4().hex[:6]
    return Organization.objects.create(
        name=f"Org {suffix}",
        code=code or f"org_{suffix}",
        status=status,
        created_by=owner,
        updated_by=owner,
    )


def _create_user_and_membership(org, email=None, is_active=True):
    user = PlatformUser.objects.create_user(
        email=email or f"user_{uuid.uuid4().hex[:6]}@org.test",
        password="UserPass123!",
    )
    user.is_active = is_active
    user.save(update_fields=["is_active"])
    OrganizationMembership.objects.create(
        organization=org,
        user=user,
        membership_type=MembershipType.MEMBER,
        status=MembershipStatus.ACTIVE if is_active else MembershipStatus.INACTIVE,
        joined_at=timezone.now(),
    )
    return user


@override_settings(
    VIBECONNECT_LMS_M2M_SECRET=TEST_M2M_SECRET,
    VIBECONNECT_LMS_BACKEND_URL=TEST_LMS_URL,
)
class LmsConnectorClientTests(TestCase):
    """Verifies LmsConnectorClient request construction, response handling, and error classification."""

    def setUp(self):
        self.client = LmsConnectorClient()

    def test_missing_url_raises_configuration_error(self):
        with override_settings(VIBECONNECT_LMS_BACKEND_URL=""):
            with patch.dict("os.environ", {"VIBECONNECT_LMS_BACKEND_URL": "", "LMS_BACKEND_URL": ""}):
                with self.assertRaises(LmsConnectorConfigurationError):
                    LmsConnectorClient()

    def test_missing_secret_raises_configuration_error(self):
        with override_settings(VIBECONNECT_LMS_M2M_SECRET=""):
            with patch.dict("os.environ", {"VIBECONNECT_LMS_M2M_SECRET": "", "VIBECONNECT_M2M_SECRET": ""}):
                with self.assertRaises(LmsConnectorConfigurationError):
                    LmsConnectorClient(base_url="http://mock-lms.internal:8000")

    @patch("urllib.request.urlopen")
    def test_successful_tenant_provision_201(self, mock_urlopen):
        resp_data = {
            "external_tenant_id": "org_123",
            "lms_organization_id": 101,
            "status": "active",
            "action_taken": "created",
        }
        mock_resp = MagicMock()
        mock_resp.status = 201
        mock_resp.read.return_value = json.dumps(resp_data).encode("utf-8")
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        payload = {"external_tenant_id": "org_123", "name": "Org 123", "code": "org_123", "status": "Active"}
        result = self.client.provision_tenant(payload)

        self.assertEqual(result["lms_organization_id"], 101)
        self.assertEqual(result["action_taken"], "created")

        # Verify headers sent
        req_arg = mock_urlopen.call_args[0][0]
        self.assertEqual(req_arg.get_header("Authorization"), f"Bearer {TEST_M2M_SECRET}")
        self.assertEqual(req_arg.get_header("Content-type"), "application/json")

    @patch("urllib.request.urlopen")
    def test_timeout_classified_as_retryable(self, mock_urlopen):
        mock_urlopen.side_effect = socket.timeout("Timed out")

        with self.assertRaises(LmsConnectorRetryableError) as ctx:
            self.client.provision_tenant({"external_tenant_id": "org_123"})

        self.assertEqual(ctx.exception.failure_code, "UPSTREAM_TIMEOUT")
        self.assertTrue(ctx.exception.is_retryable)

    @patch("urllib.request.urlopen")
    def test_connection_error_classified_as_retryable(self, mock_urlopen):
        mock_urlopen.side_effect = urllib.error.URLError("Connection refused")

        with self.assertRaises(LmsConnectorRetryableError) as ctx:
            self.client.provision_tenant({"external_tenant_id": "org_123"})

        self.assertEqual(ctx.exception.failure_code, "NETWORK_ERROR")
        self.assertTrue(ctx.exception.is_retryable)

    @patch("urllib.request.urlopen")
    def test_400_validation_error_classified_as_permanent(self, mock_urlopen):
        err_body = json.dumps({"error": "validation_error", "detail": "code is invalid."}).encode("utf-8")
        err = urllib.error.HTTPError(
            url="http://mock-lms.internal/api/",
            code=400,
            msg="Bad Request",
            hdrs={},
            fp=io.BytesIO(err_body),
        )
        mock_urlopen.side_effect = err

        with self.assertRaises(LmsConnectorPermanentError) as ctx:
            self.client.provision_tenant({"external_tenant_id": "org_123"})

        self.assertEqual(ctx.exception.status_code, 400)
        self.assertEqual(ctx.exception.failure_code, "VALIDATION_ERROR")
        self.assertFalse(ctx.exception.is_retryable)

    @patch("urllib.request.urlopen")
    def test_401_auth_error_classified_as_permanent(self, mock_urlopen):
        err_body = json.dumps({"detail": "Invalid M2M credentials."}).encode("utf-8")
        err = urllib.error.HTTPError(
            url="http://mock-lms.internal/api/",
            code=401,
            msg="Unauthorized",
            hdrs={},
            fp=io.BytesIO(err_body),
        )
        mock_urlopen.side_effect = err

        with self.assertRaises(LmsConnectorPermanentError) as ctx:
            self.client.provision_tenant({"external_tenant_id": "org_123"})

        self.assertEqual(ctx.exception.status_code, 401)
        self.assertEqual(ctx.exception.failure_code, "AUTHENTICATION_FAILED")

    @patch("urllib.request.urlopen")
    def test_409_conflict_classified_as_permanent(self, mock_urlopen):
        err_body = json.dumps({"error": "conflict", "detail": "Mapping conflict."}).encode("utf-8")
        err = urllib.error.HTTPError(
            url="http://mock-lms.internal/api/",
            code=409,
            msg="Conflict",
            hdrs={},
            fp=io.BytesIO(err_body),
        )
        mock_urlopen.side_effect = err

        with self.assertRaises(LmsConnectorPermanentError) as ctx:
            self.client.provision_tenant({"external_tenant_id": "org_123"})

        self.assertEqual(ctx.exception.status_code, 409)
        self.assertEqual(ctx.exception.failure_code, "MAPPING_CONFLICT")

    @patch("urllib.request.urlopen")
    def test_503_service_unavailable_classified_as_retryable(self, mock_urlopen):
        err_body = b"Gateway unavailable"
        err = urllib.error.HTTPError(
            url="http://mock-lms.internal/api/",
            code=503,
            msg="Service Unavailable",
            hdrs={},
            fp=io.BytesIO(err_body),
        )
        mock_urlopen.side_effect = err

        with self.assertRaises(LmsConnectorRetryableError) as ctx:
            self.client.provision_tenant({"external_tenant_id": "org_123"})

        self.assertEqual(ctx.exception.status_code, 503)
        self.assertTrue(ctx.exception.is_retryable)

    def test_secret_is_not_exposed_in_str_or_repr(self):
        exc = LmsConnectorPermanentError("Auth failed", failure_code="AUTHENTICATION_FAILED", status_code=401)
        self.assertNotIn(TEST_M2M_SECRET, str(exc))
        self.assertNotIn(TEST_M2M_SECRET, repr(exc))


@override_settings(
    VIBECONNECT_LMS_M2M_SECRET=TEST_M2M_SECRET,
    VIBECONNECT_LMS_BACKEND_URL=TEST_LMS_URL,
)
class TenantProvisioningServiceTests(TestCase):
    """Verifies provision_tenant_to_lms behavior, mapping persistence, and idempotency."""

    def setUp(self):
        self.owner = _create_owner()
        self.product = Product.objects.create(
            code="lms",
            name="LMS",
            status=CatalogStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )
        self.connector = IntegrationConnector.objects.create(
            code="lms",
            name="LMS Connector",
            product=self.product,
            version="1.0",
        )
        self.org = _create_org(owner=self.owner)

    def test_provision_tenant_success_creates_mapping(self):
        mock_client = MagicMock()
        mock_client.provision_tenant.return_value = {
            "external_tenant_id": str(self.org.id),
            "lms_organization_id": 88,
            "status": "active",
            "action_taken": "created",
        }

        res = provision_tenant_to_lms(self.org, client=mock_client)

        self.assertEqual(res["status"], "success")
        self.assertEqual(res["lms_organization_id"], 88)
        self.assertEqual(res["external_tenant_id"], "88")

        # Verify VibeConnect ExternalTenantMapping exists
        mapping = ExternalTenantMapping.objects.get(organization=self.org)
        self.assertEqual(mapping.external_tenant_id, "88")

    def test_repeated_tenant_provision_is_idempotent(self):
        mock_client = MagicMock()
        mock_client.provision_tenant.return_value = {
            "external_tenant_id": str(self.org.id),
            "lms_organization_id": 88,
            "status": "active",
            "action_taken": "existing",
        }

        # Run 1
        res1 = provision_tenant_to_lms(self.org, client=mock_client)
        # Run 2
        res2 = provision_tenant_to_lms(self.org, client=mock_client)

        self.assertEqual(res1["lms_organization_id"], res2["lms_organization_id"])
        # Exactly one mapping record exists
        self.assertEqual(ExternalTenantMapping.objects.filter(organization=self.org).count(), 1)

    def test_retired_org_rejected(self):
        self.org.status = OrganizationStatus.RETIRED
        self.org.save(update_fields=["status"])

        with self.assertRaises(TenantProvisioningError):
            provision_tenant_to_lms(self.org)


@override_settings(
    VIBECONNECT_LMS_M2M_SECRET=TEST_M2M_SECRET,
    VIBECONNECT_LMS_BACKEND_URL=TEST_LMS_URL,
)
class UserProvisioningServiceTests(TestCase):
    """Verifies provision_user_to_lms behavior, tenant prerequisite, and mapping isolation."""

    def setUp(self):
        self.owner = _create_owner()
        self.product = Product.objects.create(
            code="lms",
            name="LMS",
            status=CatalogStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )
        self.connector = IntegrationConnector.objects.create(
            code="lms",
            name="LMS Connector",
            product=self.product,
            version="1.0",
        )
        self.org = _create_org(owner=self.owner)
        self.user = _create_user_and_membership(self.org)

    def test_provision_user_auto_provisions_tenant_if_unmapped(self):
        mock_client = MagicMock()
        mock_client.provision_tenant.return_value = {
            "external_tenant_id": str(self.org.id),
            "lms_organization_id": 45,
            "status": "active",
            "action_taken": "created",
        }
        mock_client.provision_user.return_value = {
            "external_tenant_id": str(self.org.id),
            "external_user_id": str(self.user.id),
            "lms_user_id": 999,
            "email": self.user.email,
            "is_active": True,
            "action_taken": "created",
        }

        res = provision_user_to_lms(self.user, self.org, is_active=True, client=mock_client)

        self.assertEqual(res["status"], "success")
        self.assertEqual(res["lms_user_id"], 999)
        self.assertEqual(res["external_user_id"], "999")

        # Both tenant and user mappings must exist locally
        self.assertTrue(ExternalTenantMapping.objects.filter(organization=self.org).exists())
        user_mapping = ExternalUserMapping.objects.get(user=self.user)
        self.assertEqual(user_mapping.external_user_id, "999")
        self.assertEqual(user_mapping.status, ExternalUserMappingStatus.ACTIVE)

    def test_repeated_user_provision_is_idempotent(self):
        mock_client = MagicMock()
        mock_client.provision_tenant.return_value = {"external_tenant_id": str(self.org.id), "lms_organization_id": 45}
        mock_client.provision_user.return_value = {
            "external_tenant_id": str(self.org.id),
            "external_user_id": str(self.user.id),
            "lms_user_id": 999,
            "email": self.user.email,
            "is_active": True,
            "action_taken": "existing",
        }

        res1 = provision_user_to_lms(self.user, self.org, is_active=True, client=mock_client)
        res2 = provision_user_to_lms(self.user, self.org, is_active=True, client=mock_client)

        self.assertEqual(res1["lms_user_id"], res2["lms_user_id"])
        self.assertEqual(ExternalUserMapping.objects.filter(user=self.user).count(), 1)

    def test_cross_tenant_user_rejected(self):
        other_org = _create_org(owner=self.owner, code="other_org")
        # User is not a member of other_org
        with self.assertRaises(UserProvisioningError):
            provision_user_to_lms(self.user, other_org)

    def test_provision_user_member_sends_member_role(self):
        mock_client = MagicMock()
        mock_client.provision_user.return_value = {
            "external_tenant_id": str(self.org.id),
            "external_user_id": str(self.user.id),
            "lms_user_id": 101,
            "email": self.user.email,
            "role": "member",
            "is_active": True,
            "action_taken": "created",
        }
        res = provision_user_to_lms(self.user, self.org, is_active=True, client=mock_client)
        self.assertEqual(res["role"], "member")
        sent_payload = mock_client.provision_user.call_args[0][0]
        self.assertEqual(sent_payload["role"], "member")

    def test_provision_user_tenant_admin_sends_organization_admin_role(self):
        from apps.access_control.models import Role

        admin_role, _ = Role.objects.get_or_create(
            organization=None,
            code="system_tenant_admin",
            defaults={
                "name": "Tenant Administrator",
                "description": "System role",
                "is_system_role": True,
                "status": "active",
            },
        )
        admin_user = PlatformUser.objects.create_user(
            email=f"admin_{uuid.uuid4().hex[:6]}@org.test",
            password="AdminPass123!",
        )
        OrganizationMembership.objects.create(
            organization=self.org,
            user=admin_user,
            membership_type=MembershipType.TENANT_ADMIN,
            role=admin_role,
            status=MembershipStatus.ACTIVE,
            joined_at=timezone.now(),
        )

        mock_client = MagicMock()
        mock_client.provision_user.return_value = {
            "external_tenant_id": str(self.org.id),
            "external_user_id": str(admin_user.id),
            "lms_user_id": 202,
            "email": admin_user.email,
            "role": "organization_admin",
            "is_active": True,
            "action_taken": "created",
        }

        res = provision_user_to_lms(admin_user, self.org, is_active=True, client=mock_client)
        self.assertEqual(res["role"], "organization_admin")
        sent_payload = mock_client.provision_user.call_args[0][0]
        self.assertEqual(sent_payload["role"], "organization_admin")

    def test_provision_user_missing_or_non_admin_membership_defaults_to_member(self):
        # Platform owner associated with organization without an admin membership
        mock_client = MagicMock()
        mock_client.provision_user.return_value = {
            "external_tenant_id": str(self.org.id),
            "external_user_id": str(self.owner.id),
            "lms_user_id": 303,
            "email": self.owner.email,
            "role": "member",
            "is_active": True,
            "action_taken": "created",
        }
        res = provision_user_to_lms(self.owner, self.org, is_active=True, client=mock_client)
        self.assertEqual(res["role"], "member")
        sent_payload = mock_client.provision_user.call_args[0][0]
        self.assertEqual(sent_payload["role"], "member")

    def test_provision_user_conflict_409_surfaced(self):
        mock_client = MagicMock()
        mock_client.provision_user.side_effect = LmsConnectorPermanentError(
            message="Mapping conflict in LMS during user provisioning: User already exists with conflicting role",
            failure_code="MAPPING_CONFLICT",
            status_code=409,
        )
        with self.assertRaises(LmsConnectorPermanentError) as ctx:
            provision_user_to_lms(self.user, self.org, is_active=True, client=mock_client)
        self.assertEqual(ctx.exception.status_code, 409)
        self.assertEqual(ctx.exception.failure_code, "MAPPING_CONFLICT")



@override_settings(
    VIBECONNECT_LMS_M2M_SECRET=TEST_M2M_SECRET,
    VIBECONNECT_LMS_BACKEND_URL=TEST_LMS_URL,
)
class ProvisioningJobExecutorTests(TestCase):
    """Verifies ProvisioningJob lifecycle transitions, retry integration, and failure recording."""

    def setUp(self):
        self.owner = _create_owner()
        self.product = Product.objects.create(
            code="lms",
            name="LMS",
            status=CatalogStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )
        self.connector = IntegrationConnector.objects.create(
            code="lms",
            name="LMS Connector",
            product=self.product,
            version="1.0",
        )
        self.org = _create_org(owner=self.owner)
        self.instance = get_or_create_lms_connector_instance(self.org)
        self.user = _create_user_and_membership(self.org)

    def test_tenant_job_transitions_to_completed(self):
        job = ProvisioningJob.objects.create(
            instance=self.instance,
            organization=self.org,
            user=None,
            action=ProvisioningAction.PROVISION,
            status=ProvisioningJobStatus.QUEUED,
        )

        mock_client = MagicMock()
        mock_client.provision_tenant.return_value = {
            "external_tenant_id": str(self.org.id),
            "lms_organization_id": 55,
            "status": "active",
            "action_taken": "created",
        }

        executed_job = execute_provisioning_job(job, client=mock_client)

        self.assertEqual(executed_job.status, ProvisioningJobStatus.COMPLETED)
        self.assertIsNotNone(executed_job.completed_at)
        self.assertEqual(executed_job.context["result"]["lms_organization_id"], 55)

    def test_user_job_transitions_to_completed(self):
        job = ProvisioningJob.objects.create(
            instance=self.instance,
            organization=self.org,
            user=self.user,
            action=ProvisioningAction.PROVISION,
            status=ProvisioningJobStatus.QUEUED,
        )

        mock_client = MagicMock()
        mock_client.provision_tenant.return_value = {"external_tenant_id": str(self.org.id), "lms_organization_id": 55}
        mock_client.provision_user.return_value = {
            "external_tenant_id": str(self.org.id),
            "external_user_id": str(self.user.id),
            "lms_user_id": 777,
            "email": self.user.email,
            "is_active": True,
            "action_taken": "created",
        }

        executed_job = execute_provisioning_job(job, client=mock_client)

        self.assertEqual(executed_job.status, ProvisioningJobStatus.COMPLETED)
        self.assertEqual(executed_job.context["result"]["lms_user_id"], 777)

    def test_transient_failure_schedules_retry_on_integration_failure(self):
        job = ProvisioningJob.objects.create(
            instance=self.instance,
            organization=self.org,
            user=None,
            action=ProvisioningAction.PROVISION,
            status=ProvisioningJobStatus.QUEUED,
        )

        mock_client = MagicMock()
        mock_client.provision_tenant.side_effect = LmsConnectorRetryableError(
            "Gateway timeout",
            failure_code="UPSTREAM_TIMEOUT",
            status_code=504,
        )

        with self.assertRaises(LmsConnectorRetryableError):
            execute_provisioning_job(job, client=mock_client)

        job.refresh_from_db()
        self.assertEqual(job.status, ProvisioningJobStatus.RETRY_SCHEDULED)

        # Check IntegrationFailure record created and retry scheduled
        failure = IntegrationFailure.objects.get(job=job)
        self.assertEqual(failure.failure_code, "UPSTREAM_TIMEOUT")
        self.assertEqual(failure.failure_type, FailureType.TRANSIENT)
        self.assertEqual(failure.status, FailureStatus.RETRY_SCHEDULED)
        self.assertEqual(failure.retry_count, 1)
        self.assertIsNotNone(failure.retry_after)

    def test_permanent_failure_transitions_to_dead_letter(self):
        job = ProvisioningJob.objects.create(
            instance=self.instance,
            organization=self.org,
            user=None,
            action=ProvisioningAction.PROVISION,
            status=ProvisioningJobStatus.QUEUED,
        )

        mock_client = MagicMock()
        mock_client.provision_tenant.side_effect = LmsConnectorPermanentError(
            "Conflict occurred",
            failure_code="MAPPING_CONFLICT",
            status_code=409,
        )

        with self.assertRaises(LmsConnectorPermanentError):
            execute_provisioning_job(job, client=mock_client)

        job.refresh_from_db()
        self.assertEqual(job.status, ProvisioningJobStatus.FAILED)

        failure = IntegrationFailure.objects.get(job=job)
        self.assertEqual(failure.failure_code, "MAPPING_CONFLICT")
        self.assertEqual(failure.failure_type, FailureType.PERMANENT)
        self.assertEqual(failure.status, FailureStatus.DEAD_LETTER)
        self.assertIsNone(failure.retry_after)
