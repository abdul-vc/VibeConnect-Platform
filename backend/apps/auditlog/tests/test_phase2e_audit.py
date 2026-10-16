"""Phase 2E audit writer and schema validation tests."""

import uuid

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.access_control.models import Role
from apps.auditlog.models import AuditAction, AuditLog, AuditOperationSource, AuditTargetType
from apps.auditlog.services import AuditEventError, record_audit_event
from apps.organizations.models import (
    MembershipStatus,
    MembershipType,
    Organization,
    OrganizationMembership,
)

PlatformUser = get_user_model()


class TestPhase2EAuditWriter(TestCase):
    def setUp(self):
        self.owner = PlatformUser.objects.create(
            email="audit_owner@example.com",
            full_name="Audit Owner",
            status="active",
            is_active=True,
            is_platform_owner=True,
        )

        self.org = Organization.objects.create(
            code="audit-org",
            name="Audit Org",
            status="active",
            created_by=self.owner,
            updated_by=self.owner,
        )

        self.sys_role = Role.objects.get(code="system_tenant_admin", is_system_role=True)

        self.admin = PlatformUser.objects.create(
            email="audit_admin@example.com",
            full_name="Audit Admin",
            status="active",
            is_active=True,
        )
        self.membership = OrganizationMembership.objects.create(
            organization=self.org,
            user=self.admin,
            membership_type=MembershipType.TENANT_ADMIN,
            role=self.sys_role,
            status=MembershipStatus.ACTIVE,
            joined_at=timezone.now(),
        )

        self.other_org = Organization.objects.create(
            code="other-audit-org",
            name="Other Audit Org",
            status="active",
            created_by=self.owner,
            updated_by=self.owner,
        )

    def test_valid_phase2e_action_schemas(self):
        org_id_str = str(self.org.id)
        role_id = uuid.uuid4()
        mem_id = uuid.uuid4()

        cases = [
            (
                AuditAction.ROLE_CREATED,
                AuditTargetType.ROLE,
                role_id,
                "auditor:Auditor",
                self.admin,
                self.org.id,
                {
                    "organization_id": org_id_str,
                    "role_code": "auditor",
                    "role_name": "Auditor",
                    "permission_keys": ["roles.view"],
                },
            ),
            (
                AuditAction.ROLE_UPDATED,
                AuditTargetType.ROLE,
                role_id,
                "auditor:Auditor",
                self.admin,
                self.org.id,
                {
                    "organization_id": org_id_str,
                    "role_code": "auditor",
                    "name_changed": True,
                    "description_changed": False,
                },
            ),
            (
                AuditAction.ROLE_PERMISSIONS_CHANGED,
                AuditTargetType.ROLE,
                role_id,
                "auditor:Auditor",
                self.admin,
                self.org.id,
                {
                    "organization_id": org_id_str,
                    "role_code": "auditor",
                    "added_permission_keys": ["roles.manage"],
                    "removed_permission_keys": [],
                },
            ),
            (
                AuditAction.ROLE_RETIRED,
                AuditTargetType.ROLE,
                role_id,
                "auditor:Auditor",
                self.admin,
                self.org.id,
                {
                    "organization_id": org_id_str,
                    "role_code": "auditor",
                },
            ),
            (
                AuditAction.MEMBERSHIP_ROLE_ASSIGNED,
                AuditTargetType.MEMBERSHIP,
                mem_id,
                "audit-org:test@example.com",
                self.admin,
                self.org.id,
                {
                    "organization_id": org_id_str,
                    "membership_id": str(mem_id),
                    "previous_role_id": str(self.sys_role.id),
                    "previous_role_code": self.sys_role.code,
                    "resulting_role_id": str(role_id),
                    "resulting_role_code": "auditor",
                },
            ),
            (
                AuditAction.CONSOLE_MODULE_POLICY_CHANGED,
                AuditTargetType.CONSOLE_POLICY,
                uuid.uuid4(),
                "audit-org:tenant_roles",
                self.owner,
                self.org.id,
                {
                    "organization_id": org_id_str,
                    "module_key": "tenant_roles",
                    "previous_is_enabled": True,
                    "resulting_is_enabled": False,
                },
            ),
            (
                AuditAction.PERMISSION_CEILING_CHANGED,
                AuditTargetType.PERMISSION_CEILING,
                uuid.uuid4(),
                "audit-org:roles.manage",
                self.owner,
                self.org.id,
                {
                    "organization_id": org_id_str,
                    "permission_key": "roles.manage",
                    "previous_is_allowed": True,
                    "resulting_is_allowed": False,
                },
            ),
        ]

        for action, target_type, target_id, target_repr, actor, org_id, metadata in cases:
            with self.subTest(action=action):
                entry = record_audit_event(
                    action=action,
                    target_type=target_type,
                    target_id=target_id,
                    target_repr=target_repr,
                    actor=actor,
                    organization_id=org_id,
                    operation_source=AuditOperationSource.INTERACTIVE,
                    metadata=metadata,
                )
                self.assertIsNotNone(entry.id)
                self.assertEqual(entry.action, action)

    def test_missing_and_extra_metadata_rejected(self):
        org_id_str = str(self.org.id)

        # Missing permission_keys in ROLE_CREATED
        with self.assertRaises(AuditEventError):
            record_audit_event(
                action=AuditAction.ROLE_CREATED,
                target_type=AuditTargetType.ROLE,
                target_id=uuid.uuid4(),
                target_repr="code:name",
                actor=self.admin,
                organization_id=self.org.id,
                operation_source=AuditOperationSource.INTERACTIVE,
                metadata={
                    "organization_id": org_id_str,
                    "role_code": "test_code",
                    "role_name": "Test Role",
                },
            )

        # Extra key in ROLE_RETIRED
        with self.assertRaises(AuditEventError):
            record_audit_event(
                action=AuditAction.ROLE_RETIRED,
                target_type=AuditTargetType.ROLE,
                target_id=uuid.uuid4(),
                target_repr="code:name",
                actor=self.admin,
                organization_id=self.org.id,
                operation_source=AuditOperationSource.INTERACTIVE,
                metadata={
                    "organization_id": org_id_str,
                    "role_code": "test_code",
                    "extra_key": "prohibited",
                },
            )

    def test_unsorted_permission_keys_rejected(self):
        with self.assertRaises(AuditEventError):
            record_audit_event(
                action=AuditAction.ROLE_CREATED,
                target_type=AuditTargetType.ROLE,
                target_id=uuid.uuid4(),
                target_repr="code:name",
                actor=self.admin,
                organization_id=self.org.id,
                operation_source=AuditOperationSource.INTERACTIVE,
                metadata={
                    "organization_id": str(self.org.id),
                    "role_code": "test_code",
                    "role_name": "Test Role",
                    "permission_keys": ["roles.view", "roles.assign"],  # unsorted
                },
            )

    def test_action_target_mismatch_rejected(self):
        with self.assertRaises(AuditEventError):
            record_audit_event(
                action=AuditAction.ROLE_CREATED,
                target_type=AuditTargetType.MEMBERSHIP,  # Mismatch
                target_id=uuid.uuid4(),
                target_repr="code:name",
                actor=self.admin,
                organization_id=self.org.id,
                operation_source=AuditOperationSource.INTERACTIVE,
                metadata={
                    "organization_id": str(self.org.id),
                    "role_code": "test_code",
                    "role_name": "Test Role",
                    "permission_keys": ["roles.view"],
                },
            )

    def test_non_interactive_source_rejected(self):
        with self.assertRaises(AuditEventError):
            record_audit_event(
                action=AuditAction.ROLE_CREATED,
                target_type=AuditTargetType.ROLE,
                target_id=uuid.uuid4(),
                target_repr="code:name",
                actor=self.admin,
                organization_id=self.org.id,
                operation_source=AuditOperationSource.AUTHENTICATION,  # Invalid
                metadata={
                    "organization_id": str(self.org.id),
                    "role_code": "test_code",
                    "role_name": "Test Role",
                    "permission_keys": ["roles.view"],
                },
            )

    def test_tenant_admin_cross_org_audit_rejected(self):
        # Admin in self.org tries to emit audit for other_org
        with self.assertRaises(AuditEventError):
            record_audit_event(
                action=AuditAction.ROLE_CREATED,
                target_type=AuditTargetType.ROLE,
                target_id=uuid.uuid4(),
                target_repr="code:name",
                actor=self.admin,
                organization_id=self.other_org.id,
                operation_source=AuditOperationSource.INTERACTIVE,
                metadata={
                    "organization_id": str(self.other_org.id),
                    "role_code": "test_code",
                    "role_name": "Test Role",
                    "permission_keys": ["roles.view"],
                },
            )

    def test_tenant_admin_cannot_emit_po_actions(self):
        with self.assertRaises(AuditEventError):
            record_audit_event(
                action=AuditAction.CONSOLE_MODULE_POLICY_CHANGED,
                target_type=AuditTargetType.CONSOLE_POLICY,
                target_id=uuid.uuid4(),
                target_repr="code:name",
                actor=self.admin,
                organization_id=self.org.id,
                operation_source=AuditOperationSource.INTERACTIVE,
                metadata={
                    "organization_id": str(self.org.id),
                    "module_key": "tenant_roles",
                    "previous_is_enabled": True,
                    "resulting_is_enabled": False,
                },
            )

    def test_existing_audit_actions_unaffected(self):
        # Existing user action
        user = PlatformUser.objects.create(email="new_test@example.com", status="active", is_active=True)
        entry = record_audit_event(
            action=AuditAction.USER_CREATED,
            target_type=AuditTargetType.USER,
            target_id=user.id,
            target_repr=user.email,
            actor=self.owner,
            organization_id=None,
            operation_source=AuditOperationSource.INTERACTIVE,
            metadata={
                "email": user.email,
                "full_name": user.full_name,
                "status": "active",
            },
        )
        self.assertEqual(entry.action, AuditAction.USER_CREATED)
