"""Stage 1 targeted tests: OrganizationMembership model constraints.

Verifies:
- Status choices are enforced by the CheckConstraint.
- membership_type choices are enforced by the CheckConstraint.
- ended_at synchronization constraint (ended → ended_at required; active/suspended → ended_at null).
- Unique-per-(organization, user) pair constraint.
- Basic lifecycle field values.
"""

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TransactionTestCase
from django.utils import timezone

from apps.organizations.models import (
    MembershipStatus,
    MembershipType,
    Organization,
    OrganizationMembership,
)

PlatformUser = get_user_model()


def _owner():
    """Create or reuse a platform owner for organization FK fields."""
    email = "org_owner@example.com"
    u, _ = PlatformUser.objects.get_or_create(
        email=email,
        defaults={
            "full_name": "Org Owner",
            "status": "active",
            "is_active": True,
            "is_platform_owner": True,
        },
    )
    if not u.has_usable_password():
        u.set_unusable_password()
        PlatformUser.objects.filter(pk=u.pk).update(
            password=u.password
        )
    return u


def _org(suffix="a"):
    owner = _owner()
    return Organization.objects.create(
        code=f"test-org-{suffix}",
        name=f"Test Org {suffix}",
        status="active",
        created_by=owner,
        updated_by=owner,
    )


def _user(suffix):
    email = f"member_{suffix}@example.com"
    u, _ = PlatformUser.objects.get_or_create(
        email=email,
        defaults={"full_name": "Member", "status": "active", "is_active": True},
    )
    return u


def _active_membership(org, user, membership_type=MembershipType.MEMBER):
    role = None
    if membership_type == MembershipType.TENANT_ADMIN:
        from apps.access_control.models import Role

        role, _ = Role.objects.get_or_create(
            organization=None,
            code="system_tenant_admin",
            defaults={
                "name": "Tenant Administrator",
                "description": "System role",
                "is_system_role": True,
                "status": "active",
            },
        )
    return OrganizationMembership.objects.create(
        organization=org,
        user=user,
        membership_type=membership_type,
        status=MembershipStatus.ACTIVE,
        role=role,
        joined_at=timezone.now(),
        ended_at=None,
    )


class TestMembershipCreation(TransactionTestCase):
    """Basic creation and constraint satisfaction."""

    def test_create_active_membership_succeeds(self):
        org = _org("create1")
        user = _user("create1")
        m = _active_membership(org, user)
        self.assertEqual(m.status, MembershipStatus.ACTIVE)
        self.assertIsNone(m.ended_at)

    def test_create_suspended_membership_succeeds(self):
        org = _org("create2")
        user = _user("create2")
        m = OrganizationMembership.objects.create(
            organization=org,
            user=user,
            status=MembershipStatus.SUSPENDED,
            joined_at=timezone.now(),
            ended_at=None,
        )
        self.assertEqual(m.status, MembershipStatus.SUSPENDED)

    def test_create_ended_membership_with_ended_at_succeeds(self):
        org = _org("create3")
        user = _user("create3")
        m = OrganizationMembership.objects.create(
            organization=org,
            user=user,
            status=MembershipStatus.ENDED,
            joined_at=timezone.now(),
            ended_at=timezone.now(),
        )
        self.assertEqual(m.status, MembershipStatus.ENDED)
        self.assertIsNotNone(m.ended_at)


class TestMembershipUniqueConstraint(TransactionTestCase):
    """(organization, user) pair must be unique."""

    def test_duplicate_membership_raises_integrity_error(self):
        org = _org("unique1")
        user = _user("unique1")
        _active_membership(org, user)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                _active_membership(org, user)


class TestEndedAtSyncConstraint(TransactionTestCase):
    """ended_at must be null for active/suspended; must be set for ended."""

    def test_active_membership_with_ended_at_raises(self):
        org = _org("ended_sync1")
        user = _user("ended_sync1")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                OrganizationMembership.objects.create(
                    organization=org,
                    user=user,
                    status=MembershipStatus.ACTIVE,
                    joined_at=timezone.now(),
                    ended_at=timezone.now(),  # violation
                )

    def test_ended_membership_without_ended_at_raises(self):
        org = _org("ended_sync2")
        user = _user("ended_sync2")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                OrganizationMembership.objects.create(
                    organization=org,
                    user=user,
                    status=MembershipStatus.ENDED,
                    joined_at=timezone.now(),
                    ended_at=None,  # violation
                )

    def test_suspended_membership_with_ended_at_raises(self):
        org = _org("ended_sync3")
        user = _user("ended_sync3")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                OrganizationMembership.objects.create(
                    organization=org,
                    user=user,
                    status=MembershipStatus.SUSPENDED,
                    joined_at=timezone.now(),
                    ended_at=timezone.now(),  # violation
                )


class TestMembershipTypeChoices(TransactionTestCase):
    """membership_type must be one of the valid choices."""

    def test_tenant_admin_type_succeeds(self):
        org = _org("type1")
        user = _user("type1")
        m = _active_membership(org, user, membership_type=MembershipType.TENANT_ADMIN)
        self.assertEqual(m.membership_type, MembershipType.TENANT_ADMIN)

    def test_invalid_membership_type_raises(self):
        org = _org("type2")
        user = _user("type2")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                OrganizationMembership.objects.create(
                    organization=org,
                    user=user,
                    membership_type="super_admin",  # invalid
                    status=MembershipStatus.ACTIVE,
                    joined_at=timezone.now(),
                    ended_at=None,
                )
