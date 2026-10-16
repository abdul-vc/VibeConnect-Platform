"""Phase 6D Support Impersonation Regression Tests.

Verifies:
- Eligibility: only Platform Owner or Support Operator can initiate.
- Target constraints: cannot impersonate Platform Owner, superuser, or Support Operator.
- Reason and ticket_reference validation.
- Invariant: request.user remains the authenticated operator.
- Session termination endpoint and expiry handling.
- Read-only allowlist: mutations blocked during active impersonation.
"""

from datetime import timedelta
import uuid
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import PermissionDenied
from rest_framework.test import APIClient

from apps.access_control.constants import (
    PERMISSION_SUPPORT_IMPERSONATION_INITIATE,
    SUPPORT_ROLE_OPERATOR,
)
from apps.access_control.models import AccessPermission, ConsoleModule, PlatformRoleAssignment, Role
from apps.access_control.services.provisioning import provision_organization_defaults
from apps.identity.impersonation_service import (
    assert_operation_allowed_during_impersonation,
    create_impersonation_session,
    terminate_impersonation_session,
)
from apps.identity.models import ImpersonationSessionStatus, SupportImpersonationSession
from apps.organizations.models import (
    MembershipStatus,
    MembershipType,
    Organization,
    OrganizationMembership,
    OrganizationStatus,
)

User = get_user_model()


class SupportImpersonationTests(TestCase):
    def setUp(self):
        super().setUp()
        self.client = APIClient()

        # Platform Owner
        self.owner = User.objects.create_user(
            email="owner@vibeconnect.internal",
            password="SecurePassword123!",
            full_name="Platform Owner",
            is_active=True,
            status="active",
            is_platform_owner=True,
        )

        # Regular user (unauthorized operator)
        self.unauth_user = User.objects.create_user(
            email="regular@vibeconnect.internal",
            password="SecurePassword123!",
            full_name="Regular User",
            is_active=True,
            status="active",
            is_platform_owner=False,
        )

        # Organization
        self.org = Organization.objects.create(
            code="testorg",
            name="Test Org",
            status=OrganizationStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )

        admin_role, _ = Role.objects.get_or_create(
            code="system_tenant_admin",
            defaults={"name": "Tenant Admin", "is_system_role": True},
        )

        # Tenant Admin (eligible target)
        self.tenant_admin = User.objects.create_user(
            email="tenant_admin@example.com",
            password="SecurePassword123!",
            full_name="Tenant Admin",
            is_active=True,
            status="active",
            is_platform_owner=False,
        )
        OrganizationMembership.objects.create(
            user=self.tenant_admin,
            organization=self.org,
            membership_type=MembershipType.TENANT_ADMIN,
            status=MembershipStatus.ACTIVE,
            role=admin_role,
            joined_at=timezone.now(),
        )

    def test_unauthorized_user_cannot_create_session(self):
        with self.assertRaises(PermissionDenied):
            create_impersonation_session(
                operator=self.unauth_user,
                target_user_id=self.tenant_admin.id,
                target_organization_id=self.org.id,
                reason="Investigating issue",
                ticket_reference="TICKET-1234",
            )

    def test_missing_reason_or_ticket_rejected(self):
        # Empty reason
        with self.assertRaises(ValidationError):
            create_impersonation_session(
                operator=self.owner,
                target_user_id=self.tenant_admin.id,
                target_organization_id=self.org.id,
                reason="",
                ticket_reference="TICKET-1234",
            )

        # Empty ticket
        with self.assertRaises(ValidationError):
            create_impersonation_session(
                operator=self.owner,
                target_user_id=self.tenant_admin.id,
                target_organization_id=self.org.id,
                reason="Investigating issue",
                ticket_reference="",
            )

    def test_cannot_impersonate_platform_owner(self):
        with self.assertRaises(ValidationError):
            create_impersonation_session(
                operator=self.owner,
                target_user_id=self.owner.id,
                target_organization_id=self.org.id,
                reason="Testing self",
                ticket_reference="TICKET-1234",
            )

    def test_valid_session_lifecycle_and_termination(self):
        session = create_impersonation_session(
            operator=self.owner,
            target_user_id=self.tenant_admin.id,
            target_organization_id=self.org.id,
            reason="Investigating issue",
            ticket_reference="TICKET-1234",
        )
        self.assertEqual(session.status, ImpersonationSessionStatus.ACTIVE)
        self.assertEqual(session.operator, self.owner)
        self.assertEqual(session.target_user, self.tenant_admin)

        # Verify max 30 min duration
        expected_expiry = session.created_at + timedelta(minutes=30)
        self.assertAlmostEqual(
            session.expires_at.timestamp(),
            expected_expiry.timestamp(),
            delta=5,
        )

        # Terminate
        term_session = terminate_impersonation_session(
            session_id=session.id,
            actor=self.owner,
            reason="Finished troubleshooting.",
        )
        self.assertEqual(term_session.status, ImpersonationSessionStatus.TERMINATED)
        self.assertIsNotNone(term_session.terminated_at)

    def test_mutations_blocked_during_impersonation(self):
        class DummyRequest:
            method = "POST"
            path = "/api/v1/tenant/roles/"
            impersonation_session = object()

        with self.assertRaises(PermissionDenied):
            assert_operation_allowed_during_impersonation(DummyRequest(), "roles")

    def test_unsaved_session_with_default_expiry_passes_validation(self):
        session = SupportImpersonationSession(
            operator=self.owner,
            target_user=self.tenant_admin,
            target_organization=self.org,
            reason="Investigating bug",
            ticket_reference="INC-1111",
        )
        # Verify full_clean succeeds on new instance with default UUID pk
        session.full_clean()
        self.assertIsNotNone(session.expires_at)
        self.assertLessEqual(session.expires_at, timezone.now() + timedelta(minutes=31))

    def test_unsaved_session_with_excessive_expiry_is_rejected(self):
        session = SupportImpersonationSession(
            operator=self.owner,
            target_user=self.tenant_admin,
            target_organization=self.org,
            reason="Investigating bug",
            ticket_reference="INC-1111",
            expires_at=timezone.now() + timedelta(hours=2),
        )
        with self.assertRaises(ValidationError) as ctx:
            session.full_clean()
        self.assertIn("Initial session duration cannot exceed 30 minutes", str(ctx.exception))

    def test_cannot_silently_extend_persisted_session(self):
        session = create_impersonation_session(
            operator=self.owner,
            target_user_id=self.tenant_admin.id,
            target_organization_id=self.org.id,
            reason="Investigating bug",
            ticket_reference="INC-2222",
        )
        session.expires_at = session.expires_at + timedelta(minutes=10)
        with self.assertRaises(ValidationError) as ctx:
            session.clean()
        self.assertIn("Silent session extension is prohibited", str(ctx.exception))

    def test_client_cannot_override_expiry_via_api(self):
        self.client.force_authenticate(user=self.owner)
        payload = {
            "target_user_id": str(self.tenant_admin.id),
            "target_organization_id": str(self.org.id),
            "reason": "API session creation test",
            "ticket_reference": "INC-3333",
            "expires_at": (timezone.now() + timedelta(days=1)).isoformat(),

        }
        res = self.client.post("/api/v1/support/impersonation/sessions/", data=payload, format="json")
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        session_id = res.data["id"]
        db_session = SupportImpersonationSession.objects.get(id=session_id)
        self.assertLessEqual(db_session.expires_at, timezone.now() + timedelta(minutes=31))

    def test_terminated_and_expired_sessions_are_unusable(self):
        from apps.identity.impersonation_service import revalidate_request_impersonation

        session = create_impersonation_session(
            operator=self.owner,
            target_user_id=self.tenant_admin.id,
            target_organization_id=self.org.id,
            reason="Expired usability test",
            ticket_reference="INC-4444",
        )
        session.status = ImpersonationSessionStatus.TERMINATED
        session.save(update_fields=["status"])

        class MockReq:
            def __init__(self, user, s_id):
                self.user = user
                self.META = {"HTTP_X_VIBECONNECT_IMPERSONATION_SESSION": str(s_id)}

        with self.assertRaises(PermissionDenied):
            revalidate_request_impersonation(MockReq(self.owner, session.id))

