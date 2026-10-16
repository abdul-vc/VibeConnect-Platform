"""Stage 2 Organization Membership Domain Services & Concurrency Test Suite.

Verifies:
- Membership creation (requires active org & active user).
- Conflict handling: MEMBERSHIP_ALREADY_EXISTS vs MEMBERSHIP_ENDED_RESTORE_REQUIRED.
- Membership-type mutation (tenant_admin <-> member).
- Lifecycle transitions: active <-> suspended, active/suspended -> ended.
- Explicit restore of ended memberships (preserving prior timestamps in audit metadata).
- Rejection of restore on active/suspended memberships.
- Concurrency race handling on (organization, user) uniqueness.
- Atomic rollback (no partial state changes or misleading audit events on failure).
"""

import threading
import uuid

from django.contrib.auth import get_user_model
from django.db import close_old_connections, connection, transaction
from django.test import TestCase, TransactionTestCase
from django.utils import timezone

from apps.auditlog.models import AuditAction, AuditLog, AuditTargetType
from apps.identity.models import UserStatus
from apps.organizations.models import (
    MembershipStatus,
    MembershipType,
    Organization,
    OrganizationMembership,
    OrganizationStatus,
)
from apps.organizations.membership_services import (
    InvalidMembershipTransitionError,
    MembershipAlreadyExistsError,
    MembershipEndedRestoreRequiredError,
    MembershipNotEndedError,
    MembershipNotFoundError,
    MembershipValidationError,
    OrganizationNotActiveError,
    UserInactiveCannotRestoreError,
    UserNotActiveError,
    create_membership,
    end_membership,
    reactivate_membership,
    restore_membership,
    suspend_membership,
    update_membership_type,
)

PlatformUser = get_user_model()


def _make_owner(email="owner_ms@example.com"):
    user, _ = PlatformUser.objects.get_or_create(
        email=email,
        defaults={
            "full_name": "Platform Owner",
            "status": UserStatus.ACTIVE,
            "is_active": True,
            "is_platform_owner": True,
        },
    )
    return user


def _make_org(suffix="1", status=OrganizationStatus.ACTIVE):
    owner = _make_owner()
    return Organization.objects.create(
        code=f"org-{suffix}-{uuid.uuid4().hex[:6]}",
        name=f"Org {suffix}",
        status=status,
        created_by=owner,
        updated_by=owner,
    )


def _make_user(suffix="1", status=UserStatus.ACTIVE):
    return PlatformUser.objects.create_user(
        email=f"user_{suffix}_{uuid.uuid4().hex[:6]}@example.com",
        full_name=f"User {suffix}",
        status=status,
    )


def _run_in_threads(tasks: list, timeout: float = 15.0) -> tuple[list, list]:
    n = len(tasks)
    results = [None] * n
    exceptions = [None] * n

    def _worker(idx: int, func):
        close_old_connections()
        try:
            results[idx] = func()
        except Exception as exc:
            exceptions[idx] = exc
        finally:
            close_old_connections()

    threads = [threading.Thread(target=_worker, args=(i, tasks[i])) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=timeout)
        if t.is_alive():
            raise TimeoutError(f"Worker thread {t.name} timed out after {timeout}s")

    return results, exceptions


class TestMembershipServicesUnit(TestCase):
    """Unit and transactional tests for membership services."""

    def setUp(self):
        self.actor = _make_owner()
        self.org = _make_org("unit")
        self.user = _make_user("unit")

    def test_create_membership_success(self):
        m = create_membership(
            actor=self.actor,
            organization_id=self.org.id,
            user_id=self.user.id,
            membership_type=MembershipType.TENANT_ADMIN,
        )
        self.assertEqual(m.organization, self.org)
        self.assertEqual(m.user, self.user)
        self.assertEqual(m.membership_type, MembershipType.TENANT_ADMIN)
        self.assertEqual(m.status, MembershipStatus.ACTIVE)
        self.assertIsNotNone(m.joined_at)
        self.assertIsNone(m.ended_at)

        audit = AuditLog.objects.filter(
            action=AuditAction.MEMBERSHIP_CREATED,
            target_id=m.id,
        ).first()
        self.assertIsNotNone(audit)
        self.assertEqual(audit.organization_id, self.org.id)
        self.assertEqual(audit.target_type, AuditTargetType.MEMBERSHIP)
        self.assertEqual(audit.metadata["organization_code"], self.org.code)
        self.assertEqual(audit.metadata["membership_type"], "tenant_admin")

    def test_create_membership_requires_active_organization(self):
        inactive_org = _make_org("draft", status=OrganizationStatus.DRAFT)
        with self.assertRaises(OrganizationNotActiveError) as ctx:
            create_membership(
                actor=self.actor,
                organization_id=inactive_org.id,
                user_id=self.user.id,
            )
        self.assertEqual(ctx.exception.code, "ORGANIZATION_NOT_ACTIVE")

    def test_create_membership_requires_active_user(self):
        inactive_user = _make_user("susp", status=UserStatus.SUSPENDED)
        with self.assertRaises(UserNotActiveError) as ctx:
            create_membership(
                actor=self.actor,
                organization_id=self.org.id,
                user_id=inactive_user.id,
            )
        self.assertEqual(ctx.exception.code, "USER_NOT_ACTIVE")

    def test_create_membership_duplicate_active_raises_conflict(self):
        create_membership(
            actor=self.actor,
            organization_id=self.org.id,
            user_id=self.user.id,
        )
        with self.assertRaises(MembershipAlreadyExistsError) as ctx:
            create_membership(
                actor=self.actor,
                organization_id=self.org.id,
                user_id=self.user.id,
            )
        self.assertEqual(ctx.exception.code, "MEMBERSHIP_ALREADY_EXISTS")

    def test_create_membership_duplicate_ended_raises_restore_required(self):
        m = create_membership(
            actor=self.actor,
            organization_id=self.org.id,
            user_id=self.user.id,
        )
        end_membership(actor=self.actor, membership_id=m.id)

        with self.assertRaises(MembershipEndedRestoreRequiredError) as ctx:
            create_membership(
                actor=self.actor,
                organization_id=self.org.id,
                user_id=self.user.id,
            )
        self.assertEqual(ctx.exception.code, "MEMBERSHIP_ENDED_RESTORE_REQUIRED")

    def test_update_membership_type_success(self):
        m = create_membership(
            actor=self.actor,
            organization_id=self.org.id,
            user_id=self.user.id,
            membership_type=MembershipType.MEMBER,
        )
        updated = update_membership_type(
            actor=self.actor,
            membership_id=m.id,
            new_membership_type=MembershipType.TENANT_ADMIN,
        )
        self.assertEqual(updated.membership_type, MembershipType.TENANT_ADMIN)

        audit = AuditLog.objects.filter(
            action=AuditAction.MEMBERSHIP_UPDATED,
            target_id=m.id,
        ).first()
        self.assertIsNotNone(audit)
        self.assertEqual(audit.metadata["previous_membership_type"], "member")
        self.assertEqual(audit.metadata["resulting_membership_type"], "tenant_admin")

    def test_update_membership_type_ended_raises(self):
        m = create_membership(
            actor=self.actor,
            organization_id=self.org.id,
            user_id=self.user.id,
        )
        end_membership(actor=self.actor, membership_id=m.id)
        with self.assertRaises(InvalidMembershipTransitionError) as ctx:
            update_membership_type(
                actor=self.actor,
                membership_id=m.id,
                new_membership_type=MembershipType.TENANT_ADMIN,
            )
        self.assertEqual(ctx.exception.code, "INVALID_MEMBERSHIP_TRANSITION")

    def test_suspend_and_reactivate_membership_success(self):
        m = create_membership(
            actor=self.actor,
            organization_id=self.org.id,
            user_id=self.user.id,
        )
        suspended = suspend_membership(actor=self.actor, membership_id=m.id, reason="Hold")
        self.assertEqual(suspended.status, MembershipStatus.SUSPENDED)

        reactivated = reactivate_membership(actor=self.actor, membership_id=m.id)
        self.assertEqual(reactivated.status, MembershipStatus.ACTIVE)

    def test_suspend_already_suspended_membership_raises(self):
        m = create_membership(
            actor=self.actor,
            organization_id=self.org.id,
            user_id=self.user.id,
        )
        suspend_membership(actor=self.actor, membership_id=m.id)
        with self.assertRaises(InvalidMembershipTransitionError) as ctx:
            suspend_membership(actor=self.actor, membership_id=m.id)
        self.assertEqual(ctx.exception.code, "INVALID_MEMBERSHIP_TRANSITION")

    def test_reactivate_already_active_membership_raises(self):
        m = create_membership(
            actor=self.actor,
            organization_id=self.org.id,
            user_id=self.user.id,
        )
        with self.assertRaises(InvalidMembershipTransitionError) as ctx:
            reactivate_membership(actor=self.actor, membership_id=m.id)
        self.assertEqual(ctx.exception.code, "INVALID_MEMBERSHIP_TRANSITION")

    def test_end_membership_success(self):
        m = create_membership(
            actor=self.actor,
            organization_id=self.org.id,
            user_id=self.user.id,
        )
        ended = end_membership(actor=self.actor, membership_id=m.id, reason="Offboarded")
        self.assertEqual(ended.status, MembershipStatus.ENDED)
        self.assertIsNotNone(ended.ended_at)

        audit = AuditLog.objects.filter(
            action=AuditAction.MEMBERSHIP_ENDED,
            target_id=m.id,
        ).first()
        self.assertIsNotNone(audit)
        self.assertEqual(audit.metadata["resulting_status"], "ended")
        self.assertEqual(audit.metadata["reason"], "Offboarded")

    def test_end_already_ended_membership_raises(self):
        m = create_membership(
            actor=self.actor,
            organization_id=self.org.id,
            user_id=self.user.id,
        )
        end_membership(actor=self.actor, membership_id=m.id)
        with self.assertRaises(InvalidMembershipTransitionError) as ctx:
            end_membership(actor=self.actor, membership_id=m.id)
        self.assertEqual(ctx.exception.code, "INVALID_MEMBERSHIP_TRANSITION")

    def test_restore_ended_membership_success(self):
        m = create_membership(
            actor=self.actor,
            organization_id=self.org.id,
            user_id=self.user.id,
            membership_type=MembershipType.MEMBER,
        )
        prior_joined = m.joined_at
        end_membership(actor=self.actor, membership_id=m.id)
        m.refresh_from_db()
        prior_ended = m.ended_at

        restored = restore_membership(
            actor=self.actor,
            membership_id=m.id,
        )
        self.assertEqual(restored.status, MembershipStatus.ACTIVE)
        self.assertIsNone(restored.ended_at)
        self.assertNotEqual(restored.joined_at, prior_joined)
        # Restore must preserve existing membership_type
        self.assertEqual(restored.membership_type, MembershipType.MEMBER)

        audit = AuditLog.objects.filter(
            action=AuditAction.MEMBERSHIP_RESTORED,
            target_id=m.id,
        ).first()
        self.assertIsNotNone(audit)
        self.assertEqual(audit.metadata["prior_joined_at"], prior_joined.isoformat())
        self.assertEqual(audit.metadata["prior_ended_at"], prior_ended.isoformat())
        self.assertEqual(audit.metadata["new_joined_at"], restored.joined_at.isoformat())
        self.assertEqual(audit.metadata["membership_type"], "member")

    def test_restore_active_or_suspended_membership_raises(self):
        m = create_membership(
            actor=self.actor,
            organization_id=self.org.id,
            user_id=self.user.id,
        )
        with self.assertRaises(MembershipNotEndedError) as ctx:
            restore_membership(actor=self.actor, membership_id=m.id)
        self.assertEqual(ctx.exception.code, "MEMBERSHIP_NOT_ENDED")

        suspend_membership(actor=self.actor, membership_id=m.id)
        with self.assertRaises(MembershipNotEndedError) as ctx:
            restore_membership(actor=self.actor, membership_id=m.id)
        self.assertEqual(ctx.exception.code, "MEMBERSHIP_NOT_ENDED")

    def test_restore_ended_membership_inactive_user_raises(self):
        m = create_membership(
            actor=self.actor,
            organization_id=self.org.id,
            user_id=self.user.id,
        )
        end_membership(actor=self.actor, membership_id=m.id)
        # Suspend the user to make them inactive
        self.user.status = UserStatus.SUSPENDED
        self.user.is_active = False
        self.user.save(update_fields=["status", "is_active"])

        with self.assertRaises(UserInactiveCannotRestoreError) as ctx:
            restore_membership(actor=self.actor, membership_id=m.id)
        self.assertEqual(ctx.exception.code, "USER_INACTIVE_CANNOT_RESTORE")

    def test_restore_ended_membership_inactive_org_raises(self):
        m = create_membership(
            actor=self.actor,
            organization_id=self.org.id,
            user_id=self.user.id,
        )
        end_membership(actor=self.actor, membership_id=m.id)
        # Suspend organization
        self.org.status = OrganizationStatus.SUSPENDED
        self.org.save(update_fields=["status"])

        with self.assertRaises(OrganizationNotActiveError) as ctx:
            restore_membership(actor=self.actor, membership_id=m.id)
        self.assertEqual(ctx.exception.code, "ORGANIZATION_NOT_ACTIVE")

    def test_atomic_rollback_on_failure(self):
        m = create_membership(
            actor=self.actor,
            organization_id=self.org.id,
            user_id=self.user.id,
        )
        audit_count_before = AuditLog.objects.count()

        # Attempt invalid transition (reactivating active membership)
        with self.assertRaises(InvalidMembershipTransitionError):
            reactivate_membership(actor=self.actor, membership_id=m.id)

        m.refresh_from_db()
        self.assertEqual(m.status, MembershipStatus.ACTIVE)
        self.assertEqual(AuditLog.objects.count(), audit_count_before)


class TestMembershipServicesConcurrency(TransactionTestCase):
    """Concurrency tests for organization membership operations."""

    def test_concurrent_membership_creation_race(self):
        """Two concurrent threads creating membership for same (org, user) pair:
        exactly one succeeds and one receives MembershipAlreadyExistsError.
        """
        actor = _make_owner("conc_owner@example.com")
        org = _make_org("conc")
        user = _make_user("conc")

        def _task1():
            return create_membership(
                actor=actor,
                organization_id=org.id,
                user_id=user.id,
            )

        def _task2():
            return create_membership(
                actor=actor,
                organization_id=org.id,
                user_id=user.id,
            )

        results, exceptions = _run_in_threads([_task1, _task2])

        successes = [r for r in results if r is not None]
        failures = [e for e in exceptions if e is not None]

        self.assertEqual(len(successes), 1, f"Expected 1 success, got {len(successes)}")
        self.assertEqual(len(failures), 1, f"Expected 1 failure, got {len(failures)}")
        self.assertIsInstance(failures[0], MembershipAlreadyExistsError)
        self.assertEqual(failures[0].code, "MEMBERSHIP_ALREADY_EXISTS")

        # Exactly 1 membership row in DB
        self.assertEqual(OrganizationMembership.objects.filter(organization=org, user=user).count(), 1)


class TestPhase2EMembershipRoleLifecycle(TestCase):
    """Verifies Phase 2E membership-role synchronization and last-admin invariant enforcement."""

    def setUp(self):
        self.actor = _make_owner("po_role_life@example.com")
        self.org = _make_org("role_life")
        from apps.access_control.services.provisioning import provision_organization_defaults

        provision_organization_defaults(organization=self.org, actor=self.actor)

        from apps.access_control.models import Role

        self.sys_role = Role.objects.get(code="system_tenant_admin", is_system_role=True)
        self.user1 = _make_user("user1_rl")
        self.user2 = _make_user("user2_rl")

    def test_tenant_admin_promotion_assigns_explicit_system_role(self):
        m = create_membership(
            actor=self.actor,
            organization_id=self.org.id,
            user_id=self.user1.id,
            membership_type=MembershipType.MEMBER,
        )
        self.assertIsNone(m.role)

        promoted = update_membership_type(
            actor=self.actor,
            membership_id=m.id,
            new_membership_type=MembershipType.TENANT_ADMIN,
        )
        self.assertEqual(promoted.membership_type, MembershipType.TENANT_ADMIN)
        self.assertEqual(promoted.role, self.sys_role)

    def test_downgrade_clears_role(self):
        # Create two admins
        m1 = create_membership(
            actor=self.actor,
            organization_id=self.org.id,
            user_id=self.user1.id,
            membership_type=MembershipType.TENANT_ADMIN,
        )
        create_membership(
            actor=self.actor,
            organization_id=self.org.id,
            user_id=self.user2.id,
            membership_type=MembershipType.TENANT_ADMIN,
        )

        downgraded = update_membership_type(
            actor=self.actor,
            membership_id=m1.id,
            new_membership_type=MembershipType.MEMBER,
        )
        self.assertEqual(downgraded.membership_type, MembershipType.MEMBER)
        self.assertIsNone(downgraded.role)

    def test_suspending_or_ending_last_capable_admin_rejected(self):
        from apps.access_control.services.guards import LastAdminProtectionError

        sole_admin = create_membership(
            actor=self.actor,
            organization_id=self.org.id,
            user_id=self.user1.id,
            membership_type=MembershipType.TENANT_ADMIN,
        )

        with self.assertRaises(LastAdminProtectionError) as ctx:
            suspend_membership(actor=self.actor, membership_id=sole_admin.id)
        self.assertEqual(ctx.exception.code, "LAST_ADMIN_PROTECTION")

        with self.assertRaises(LastAdminProtectionError) as ctx:
            end_membership(actor=self.actor, membership_id=sole_admin.id)
        self.assertEqual(ctx.exception.code, "LAST_ADMIN_PROTECTION")

    def test_operation_succeeds_when_another_capable_admin_remains(self):
        admin1 = create_membership(
            actor=self.actor,
            organization_id=self.org.id,
            user_id=self.user1.id,
            membership_type=MembershipType.TENANT_ADMIN,
        )
        create_membership(
            actor=self.actor,
            organization_id=self.org.id,
            user_id=self.user2.id,
            membership_type=MembershipType.TENANT_ADMIN,
        )

        suspended = suspend_membership(actor=self.actor, membership_id=admin1.id)
        self.assertEqual(suspended.status, MembershipStatus.SUSPENDED)

    def test_ended_membership_retains_role(self):
        admin1 = create_membership(
            actor=self.actor,
            organization_id=self.org.id,
            user_id=self.user1.id,
            membership_type=MembershipType.TENANT_ADMIN,
        )
        create_membership(
            actor=self.actor,
            organization_id=self.org.id,
            user_id=self.user2.id,
            membership_type=MembershipType.TENANT_ADMIN,
        )

        ended = end_membership(actor=self.actor, membership_id=admin1.id)
        self.assertEqual(ended.status, MembershipStatus.ENDED)
        self.assertEqual(ended.role, self.sys_role)

    def test_restore_preserves_assigned_role(self):
        admin1 = create_membership(
            actor=self.actor,
            organization_id=self.org.id,
            user_id=self.user1.id,
            membership_type=MembershipType.TENANT_ADMIN,
        )
        create_membership(
            actor=self.actor,
            organization_id=self.org.id,
            user_id=self.user2.id,
            membership_type=MembershipType.TENANT_ADMIN,
        )

        ended = end_membership(actor=self.actor, membership_id=admin1.id)
        restored = restore_membership(actor=self.actor, membership_id=ended.id)
        self.assertEqual(restored.status, MembershipStatus.ACTIVE)
        self.assertEqual(restored.role, self.sys_role)

