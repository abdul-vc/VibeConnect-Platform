"""Tests for User Invitations Domain Services (Phase 3C)."""

from datetime import timedelta
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.access_control.models import Role
from apps.invitations.models import InvitationStatus, UserInvitation, hash_token
from apps.invitations.services import (
    DuplicateInvitationError,
    InvitationAlreadyUsedError,
    InvitationExpiredError,
    InvitationNotFoundError,
    accept_invitation,
    issue_invitation,
    validate_invitation,
)
from apps.organizations.models import MembershipStatus, MembershipType, Organization, OrganizationMembership

PlatformUser = get_user_model()


class InvitationServicesTests(TestCase):
    def setUp(self):
        self.owner = PlatformUser.objects.create_superuser(
            email="owner@vibeconnect.test",
            password="SecurePassword123!",
            full_name="Platform Owner",
        )
        self.org = Organization.objects.create(
            code="acme",
            name="Acme Corp",
            status="active",
            created_by=self.owner,
            updated_by=self.owner,
        )
        self.role = Role.objects.create(
            organization=self.org,
            code="org_admin_role",
            name="Org Admin",
        )

    def test_issue_invitation_success(self):
        invitation, raw_token = issue_invitation(
            organization=self.org,
            email="newuser@acme.test",
            membership_type=MembershipType.MEMBER,
            invited_by=self.owner,
        )
        self.assertEqual(invitation.email, "newuser@acme.test")
        self.assertEqual(invitation.status, InvitationStatus.PENDING)
        self.assertEqual(invitation.token_hash, hash_token(raw_token))
        self.assertNotEqual(raw_token, invitation.token_hash)
        self.assertGreater(invitation.expires_at, timezone.now())

    def test_validate_invitation_success(self):
        invitation, raw_token = issue_invitation(
            organization=self.org,
            email="validate@acme.test",
            membership_type=MembershipType.MEMBER,
            invited_by=self.owner,
        )
        validated = validate_invitation(raw_token)
        self.assertEqual(validated.id, invitation.id)
        self.assertEqual(validated.organization, self.org)

    def test_accept_invitation_atomic_user_and_membership_creation(self):
        invitation, raw_token = issue_invitation(
            organization=self.org,
            email="alice@acme.test",
            membership_type=MembershipType.MEMBER,
            invited_by=self.owner,
        )

        result = accept_invitation(
            raw_token=raw_token,
            password="StrongPassword2026!",
            full_name="Alice Wonderland",
        )

        self.assertEqual(result["email"], "alice@acme.test")
        self.assertEqual(result["organization_code"], "acme")

        # Verify PlatformUser was created and password works
        user = PlatformUser.objects.get(email="alice@acme.test")
        self.assertTrue(user.check_password("StrongPassword2026!"))
        self.assertEqual(user.full_name, "Alice Wonderland")
        self.assertTrue(user.is_active)

        # Verify OrganizationMembership created
        membership = OrganizationMembership.objects.get(organization=self.org, user=user)
        self.assertEqual(membership.status, MembershipStatus.ACTIVE)
        self.assertEqual(membership.membership_type, MembershipType.MEMBER)

        # Verify Invitation marked accepted
        invitation.refresh_from_db()
        self.assertEqual(invitation.status, InvitationStatus.ACCEPTED)
        self.assertIsNotNone(invitation.accepted_at)

    def test_expired_invitation_rejected(self):
        invitation, raw_token = issue_invitation(
            organization=self.org,
            email="expired@acme.test",
            membership_type=MembershipType.MEMBER,
            invited_by=self.owner,
        )
        # Fast-forward expiry
        invitation.expires_at = timezone.now() - timedelta(hours=1)
        invitation.save()

        with self.assertRaises(InvitationExpiredError):
            validate_invitation(raw_token)

        with self.assertRaises(InvitationExpiredError):
            accept_invitation(
                raw_token=raw_token,
                password="StrongPassword2026!",
                full_name="Expired User",
            )

    def test_reused_token_rejected(self):
        _, raw_token = issue_invitation(
            organization=self.org,
            email="bob@acme.test",
            membership_type=MembershipType.MEMBER,
            invited_by=self.owner,
        )
        accept_invitation(
            raw_token=raw_token,
            password="StrongPassword2026!",
            full_name="Bob Builder",
        )

        with self.assertRaises(InvitationAlreadyUsedError):
            validate_invitation(raw_token)

        with self.assertRaises(InvitationAlreadyUsedError):
            accept_invitation(
                raw_token=raw_token,
                password="AnotherPassword2026!",
                full_name="Bob Builder",
            )

    def test_duplicate_invite_conflict(self):
        issue_invitation(
            organization=self.org,
            email="duplicate@acme.test",
            membership_type=MembershipType.MEMBER,
            invited_by=self.owner,
        )
        with self.assertRaises(DuplicateInvitationError):
            issue_invitation(
                organization=self.org,
                email="duplicate@acme.test",
                membership_type=MembershipType.MEMBER,
                invited_by=self.owner,
            )

    def test_existing_user_linking_without_duplicate(self):
        # Create user in org1
        existing_user = PlatformUser.objects.create_user(
            email="crossorg@partner.test",
            password="ExistingPassword2026!",
            full_name="Cross Org User",
        )
        # Org 2 issues invite to the same email
        invitation, raw_token = issue_invitation(
            organization=self.org,
            email="crossorg@partner.test",
            membership_type=MembershipType.MEMBER,
            invited_by=self.owner,
        )

        initial_user_count = PlatformUser.objects.count()

        result = accept_invitation(
            raw_token=raw_token,
            password="ExistingPassword2026!",
            full_name="Cross Org User",
        )

        # No duplicate user created
        self.assertEqual(PlatformUser.objects.count(), initial_user_count)
        self.assertEqual(result["user_id"], str(existing_user.id))

        # Membership in self.org successfully created
        self.assertTrue(
            OrganizationMembership.objects.filter(
                organization=self.org,
                user=existing_user,
                status=MembershipStatus.ACTIVE,
            ).exists()
        )
