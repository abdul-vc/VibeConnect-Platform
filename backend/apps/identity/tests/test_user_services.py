"""Stage 2 User Domain Services & Concurrency Test Suite.

Verifies:
- User creation (unusable password, non-privileged, audit logging).
- Safe profile updates (full_name only).
- Lifecycle transitions: active→suspended/disabled, suspended→active/disabled.
- Terminal disabled enforcement (rejection of all transitions out of disabled).
- In-transaction row-locked protection of the final active Platform Owner.
- Concurrent last-owner race protection with separate database connections.
- Atomic rollback (no partial state changes or misleading audit events on failure).
"""

import threading
import uuid

from django.contrib.auth import get_user_model
from django.db import close_old_connections, connection, transaction
from django.test import TestCase, TransactionTestCase

from apps.auditlog.models import AuditAction, AuditLog, AuditTargetType
from apps.identity.models import UserStatus
from apps.identity.services import (
    InvalidUserTransitionError,
    LastPlatformOwnerError,
    UserAlreadyActiveError,
    UserAlreadyExistsError,
    UserDisabledTerminalError,
    UserNotFoundError,
    UserValidationError,
    create_user,
    disable_user,
    reactivate_user,
    suspend_user,
    update_user_profile,
)

PlatformUser = get_user_model()


def _make_owner(email="owner@example.com"):
    """Helper: create an active platform owner."""
    user, _ = PlatformUser.objects.get_or_create(
        email=email,
        defaults={
            "full_name": "Platform Owner",
            "status": UserStatus.ACTIVE,
            "is_active": True,
            "is_platform_owner": True,
        },
    )
    if not user.is_platform_owner or user.status != UserStatus.ACTIVE:
        PlatformUser.objects.filter(pk=user.pk).update(
            status=UserStatus.ACTIVE, is_active=True, is_platform_owner=True
        )
        user.refresh_from_db()
    return user


def _run_in_threads(tasks: list, timeout: float = 15.0) -> tuple[list, list]:
    """Execute callables in separate worker threads with isolated DB connections."""
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


class TestUserServicesUnit(TestCase):
    """Unit tests for user lifecycle services."""

    def setUp(self):
        self.actor = _make_owner()

    def test_create_user_success(self):
        user = create_user(
            actor=self.actor,
            email="newuser@example.com",
            full_name="New User",
        )
        self.assertEqual(user.email, "newuser@example.com")
        self.assertEqual(user.full_name, "New User")
        self.assertEqual(user.status, UserStatus.ACTIVE)
        self.assertTrue(user.is_active)
        self.assertFalse(user.is_platform_owner)
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertFalse(user.has_usable_password())

        audit = AuditLog.objects.filter(
            action=AuditAction.USER_CREATED,
            target_id=user.id,
        ).first()
        self.assertIsNotNone(audit)
        self.assertEqual(audit.actor, self.actor)
        self.assertEqual(audit.target_type, AuditTargetType.USER)
        self.assertIsNone(audit.organization_id)
        self.assertEqual(audit.metadata["email"], "newuser@example.com")

    def test_create_user_duplicate_email_raises_conflict(self):
        create_user(actor=self.actor, email="dup@example.com", full_name="User 1")
        with self.assertRaises(UserAlreadyExistsError) as ctx:
            create_user(actor=self.actor, email="DUP@example.com", full_name="User 2")
        self.assertEqual(ctx.exception.code, "USER_ALREADY_EXISTS")

    def test_create_user_non_owner_actor_rejected(self):
        regular_user = create_user(actor=self.actor, email="regular@example.com")
        with self.assertRaises(UserValidationError) as ctx:
            create_user(actor=regular_user, email="other@example.com")
        self.assertEqual(ctx.exception.code, "INSUFFICIENT_PRIVILEGES")

    def test_update_user_profile_success(self):
        user = create_user(actor=self.actor, email="profile@example.com", full_name="Initial")
        updated = update_user_profile(actor=self.actor, user_id=user.id, full_name="Updated Name")
        self.assertEqual(updated.full_name, "Updated Name")

        audit = AuditLog.objects.filter(
            action=AuditAction.USER_UPDATED,
            target_id=user.id,
        ).first()
        self.assertIsNotNone(audit)
        self.assertEqual(audit.metadata["full_name"], "Updated Name")

    def test_suspend_active_user_success(self):
        user = create_user(actor=self.actor, email="suspend_me@example.com")
        suspended = suspend_user(actor=self.actor, user_id=user.id, reason="Policy violation")
        self.assertEqual(suspended.status, UserStatus.SUSPENDED)
        self.assertFalse(suspended.is_active)

        audit = AuditLog.objects.filter(
            action=AuditAction.USER_SUSPENDED,
            target_id=user.id,
        ).first()
        self.assertIsNotNone(audit)
        self.assertEqual(audit.metadata["previous_status"], "active")
        self.assertEqual(audit.metadata["resulting_status"], "suspended")
        self.assertEqual(audit.metadata["reason"], "Policy violation")

    def test_suspend_already_suspended_user_raises(self):
        user = create_user(actor=self.actor, email="already_susp@example.com")
        suspend_user(actor=self.actor, user_id=user.id)
        with self.assertRaises(InvalidUserTransitionError) as ctx:
            suspend_user(actor=self.actor, user_id=user.id)
        self.assertEqual(ctx.exception.code, "INVALID_USER_TRANSITION")

    def test_suspend_disabled_user_raises_terminal_error(self):
        user = create_user(actor=self.actor, email="disabled_user@example.com")
        disable_user(actor=self.actor, user_id=user.id)
        with self.assertRaises(UserDisabledTerminalError) as ctx:
            suspend_user(actor=self.actor, user_id=user.id)
        self.assertEqual(ctx.exception.code, "USER_DISABLED_TERMINAL")

    def test_reactivate_suspended_user_success(self):
        user = create_user(actor=self.actor, email="reactivate_me@example.com")
        suspend_user(actor=self.actor, user_id=user.id)
        reactivated = reactivate_user(actor=self.actor, user_id=user.id)
        self.assertEqual(reactivated.status, UserStatus.ACTIVE)
        self.assertTrue(reactivated.is_active)

        audit = AuditLog.objects.filter(
            action=AuditAction.USER_REACTIVATED,
            target_id=user.id,
        ).first()
        self.assertIsNotNone(audit)
        self.assertEqual(audit.metadata["previous_status"], "suspended")
        self.assertEqual(audit.metadata["resulting_status"], "active")

    def test_reactivate_active_user_raises(self):
        user = create_user(actor=self.actor, email="already_active@example.com")
        with self.assertRaises(UserAlreadyActiveError) as ctx:
            reactivate_user(actor=self.actor, user_id=user.id)
        self.assertEqual(ctx.exception.code, "USER_ALREADY_ACTIVE")

    def test_reactivate_disabled_user_raises_terminal_error(self):
        user = create_user(actor=self.actor, email="terminal_user@example.com")
        disable_user(actor=self.actor, user_id=user.id)
        with self.assertRaises(UserDisabledTerminalError) as ctx:
            reactivate_user(actor=self.actor, user_id=user.id)
        self.assertEqual(ctx.exception.code, "USER_DISABLED_TERMINAL")

    def test_disable_active_and_suspended_user_success(self):
        user1 = create_user(actor=self.actor, email="dis1@example.com")
        disable_user(actor=self.actor, user_id=user1.id, reason="Terminated")
        self.assertEqual(user1.refresh_from_db() or user1.status, UserStatus.DISABLED)
        self.assertFalse(user1.is_active)

        user2 = create_user(actor=self.actor, email="dis2@example.com")
        suspend_user(actor=self.actor, user_id=user2.id)
        disable_user(actor=self.actor, user_id=user2.id)
        self.assertEqual(user2.refresh_from_db() or user2.status, UserStatus.DISABLED)
        self.assertFalse(user2.is_active)

    def test_disable_already_disabled_user_raises_terminal_error(self):
        user = create_user(actor=self.actor, email="already_dis@example.com")
        disable_user(actor=self.actor, user_id=user.id)
        with self.assertRaises(UserDisabledTerminalError) as ctx:
            disable_user(actor=self.actor, user_id=user.id)
        self.assertEqual(ctx.exception.code, "USER_DISABLED_TERMINAL")

    def test_last_active_platform_owner_protection_sequential(self):
        """Cannot suspend or disable the final active platform owner."""
        # Ensure only self.actor is active owner
        PlatformUser.objects.filter(is_platform_owner=True).exclude(pk=self.actor.pk).delete()

        with self.assertRaises(LastPlatformOwnerError) as ctx:
            suspend_user(actor=self.actor, user_id=self.actor.id)
        self.assertEqual(ctx.exception.code, "CANNOT_DEACTIVATE_LAST_PLATFORM_OWNER")

        with self.assertRaises(LastPlatformOwnerError) as ctx:
            disable_user(actor=self.actor, user_id=self.actor.id)
        self.assertEqual(ctx.exception.code, "CANNOT_DEACTIVATE_LAST_PLATFORM_OWNER")

    def test_atomic_rollback_on_service_failure(self):
        """A failed transition produces no partial state change and no audit event."""
        user = create_user(actor=self.actor, email="rollback_test@example.com")
        audit_count_before = AuditLog.objects.count()

        # Attempt invalid transition (reactivating already-active user)
        with self.assertRaises(UserAlreadyActiveError):
            reactivate_user(actor=self.actor, user_id=user.id)

        user.refresh_from_db()
        self.assertEqual(user.status, UserStatus.ACTIVE)
        self.assertEqual(AuditLog.objects.count(), audit_count_before)


class TestUserServicesConcurrency(TransactionTestCase):
    """PostgreSQL multi-threaded concurrency tests for Platform Owner protection."""

    def test_concurrent_deactivation_of_last_platform_owners(self):
        """When exactly two active owners exist, concurrent deactivations serialize;
        exactly one succeeds and the second fails with LastPlatformOwnerError.
        """
        owner1 = _make_owner("owner1_conc@example.com")
        owner2 = _make_owner("owner2_conc@example.com")

        # Ensure no other active owners exist
        PlatformUser.objects.filter(is_platform_owner=True).exclude(
            pk__in=[owner1.pk, owner2.pk]
        ).delete()

        def _task_suspend_owner1():
            return suspend_user(actor=owner1, user_id=owner1.id)

        def _task_suspend_owner2():
            return suspend_user(actor=owner2, user_id=owner2.id)

        results, exceptions = _run_in_threads([_task_suspend_owner1, _task_suspend_owner2])

        # Exactly one thread must succeed and one must raise LastPlatformOwnerError
        successes = [r for r in results if r is not None]
        failures = [e for e in exceptions if e is not None]

        self.assertEqual(len(successes), 1, f"Expected 1 success, got {len(successes)}")
        self.assertEqual(len(failures), 1, f"Expected 1 failure, got {len(failures)}")
        self.assertIsInstance(failures[0], LastPlatformOwnerError)
        self.assertEqual(failures[0].code, "CANNOT_DEACTIVATE_LAST_PLATFORM_OWNER")

        # Exactly 1 active platform owner must remain in DB
        active_owners_remaining = PlatformUser.objects.filter(
            is_platform_owner=True, status=UserStatus.ACTIVE
        ).count()
        self.assertEqual(active_owners_remaining, 1)


class TestTenantAdminProtectionInUserServices(TestCase):
    """Verifies that suspend_user and disable_user enforce the structural last-capable Tenant Admin invariant."""

    def setUp(self):
        from django.utils import timezone
        from apps.access_control.models import Role
        from apps.access_control.services.provisioning import provision_organization_defaults
        from apps.organizations.models import (
            MembershipStatus,
            MembershipType,
            Organization,
            OrganizationMembership,
        )

        self.owner = _make_owner("po_user_test@example.com")

        self.org1 = Organization.objects.create(
            code="user-svc-org-1",
            name="User Svc Org 1",
            status="active",
            created_by=self.owner,
            updated_by=self.owner,
        )
        provision_organization_defaults(organization=self.org1, actor=self.owner)

        self.sys_role = Role.objects.get(code="system_tenant_admin", is_system_role=True)

        self.admin1 = PlatformUser.objects.create(
            email="admin_target_1@example.com",
            full_name="Admin Target 1",
            status=UserStatus.ACTIVE,
            is_active=True,
        )
        self.mem1 = OrganizationMembership.objects.create(
            organization=self.org1,
            user=self.admin1,
            membership_type=MembershipType.TENANT_ADMIN,
            role=self.sys_role,
            status=MembershipStatus.ACTIVE,
            joined_at=timezone.now(),
        )

    def test_suspend_last_capable_tenant_admin_user_rejected(self):
        from apps.access_control.services.guards import LastAdminProtectionError

        with self.assertRaises(LastAdminProtectionError) as ctx:
            suspend_user(actor=self.owner, user_id=self.admin1.id)
        self.assertEqual(ctx.exception.code, "LAST_ADMIN_PROTECTION")

    def test_disable_last_capable_tenant_admin_user_rejected(self):
        from apps.access_control.services.guards import LastAdminProtectionError

        with self.assertRaises(LastAdminProtectionError) as ctx:
            disable_user(actor=self.owner, user_id=self.admin1.id)
        self.assertEqual(ctx.exception.code, "LAST_ADMIN_PROTECTION")

    def test_suspension_succeeds_when_another_capable_active_admin_remains(self):
        from django.utils import timezone
        from apps.organizations.models import MembershipStatus, MembershipType, OrganizationMembership

        admin2 = PlatformUser.objects.create(
            email="admin_co_2@example.com",
            full_name="Admin Co 2",
            status=UserStatus.ACTIVE,
            is_active=True,
        )
        OrganizationMembership.objects.create(
            organization=self.org1,
            user=admin2,
            membership_type=MembershipType.TENANT_ADMIN,
            role=self.sys_role,
            status=MembershipStatus.ACTIVE,
            joined_at=timezone.now(),
        )

        suspended = suspend_user(actor=self.owner, user_id=self.admin1.id)
        self.assertEqual(suspended.status, UserStatus.SUSPENDED)
        self.assertFalse(suspended.is_active)

    def test_disabled_or_suspended_alternative_admin_does_not_satisfy_invariant(self):
        from django.utils import timezone
        from apps.access_control.services.guards import LastAdminProtectionError
        from apps.organizations.models import MembershipStatus, MembershipType, OrganizationMembership

        admin2 = PlatformUser.objects.create(
            email="admin_suspended_co@example.com",
            full_name="Admin Suspended Co",
            status=UserStatus.SUSPENDED,
            is_active=False,
        )
        OrganizationMembership.objects.create(
            organization=self.org1,
            user=admin2,
            membership_type=MembershipType.TENANT_ADMIN,
            role=self.sys_role,
            status=MembershipStatus.ACTIVE,
            joined_at=timezone.now(),
        )

        with self.assertRaises(LastAdminProtectionError):
            suspend_user(actor=self.owner, user_id=self.admin1.id)

    def test_multi_organization_target_cannot_leave_any_organization_without_admin(self):
        from django.utils import timezone
        from apps.access_control.services.guards import LastAdminProtectionError
        from apps.access_control.services.provisioning import provision_organization_defaults
        from apps.organizations.models import MembershipStatus, MembershipType, Organization, OrganizationMembership

        org2 = Organization.objects.create(
            code="user-svc-org-2",
            name="User Svc Org 2",
            status="active",
            created_by=self.owner,
            updated_by=self.owner,
        )
        provision_organization_defaults(organization=org2, actor=self.owner)

        # admin1 is in org2 as well
        OrganizationMembership.objects.create(
            organization=org2,
            user=self.admin1,
            membership_type=MembershipType.TENANT_ADMIN,
            role=self.sys_role,
            status=MembershipStatus.ACTIVE,
            joined_at=timezone.now(),
        )
        # org2 has another active admin
        admin2 = PlatformUser.objects.create(
            email="admin_org2_other@example.com",
            full_name="Admin Org2 Other",
            status=UserStatus.ACTIVE,
            is_active=True,
        )
        OrganizationMembership.objects.create(
            organization=org2,
            user=admin2,
            membership_type=MembershipType.TENANT_ADMIN,
            role=self.sys_role,
            status=MembershipStatus.ACTIVE,
            joined_at=timezone.now(),
        )

        # But org1 still has ONLY admin1. Suspending admin1 must fail because org1 would have no capable admins!
        with self.assertRaises(LastAdminProtectionError):
            suspend_user(actor=self.owner, user_id=self.admin1.id)

