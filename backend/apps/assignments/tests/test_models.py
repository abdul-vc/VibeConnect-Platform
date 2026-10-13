"""Part A focused model and database constraint tests for UserProductAssignment and UserModuleAssignment.

Validates:
1. Basic assignment creation and field defaults (UUID, status, timestamps, reasons).
2. Status CheckConstraint (active, suspended, revoked).
3. Partial unique constraint for open assignments (preventing active/suspended duplicates).
4. Multiple historical revoked assignments and re-assignment after revocation.
5. Module assignment unique constraint and multiple module links.
6. Foreign key on_delete=PROTECT enforcement on referenced entities.
7. Cascade deletion of module assignments when assignment is deleted.
8. Revoked timestamp synchronization CheckConstraint.
9. Suspended timestamp requirement CheckConstraint.
10. Immutability of identity fields on existing assignments.
11. Cross-entity validation: membership organization must match assignment organization.
12. Cross-entity validation: membership user must match assignment user.
"""

import uuid
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.test import TransactionTestCase
from django.utils import timezone

from apps.assignments.models import (
    AssignmentImmutabilityError,
    AssignmentStatus,
    MembershipValidationError,
    UserModuleAssignment,
    UserProductAssignment,
)
from apps.organizations.models import Organization, OrganizationMembership
from apps.product_registry.models import Product, ProductModule

PlatformUser = get_user_model()


class AssignmentModelTests(TransactionTestCase):
    """Part A focused model tests for assignments application."""

    def setUp(self):
        super().setUp()
        self.actor = PlatformUser.objects.create(
            email=f"admin_{uuid.uuid4().hex[:6]}@example.com",
            full_name="Admin Actor",
            status="active",
            is_active=True,
            is_platform_owner=True,
        )
        self.org_a = Organization.objects.create(
            code=f"org-a-{uuid.uuid4().hex[:6]}",
            name="Organization A",
            status="active",
            created_by=self.actor,
            updated_by=self.actor,
        )
        self.org_b = Organization.objects.create(
            code=f"org-b-{uuid.uuid4().hex[:6]}",
            name="Organization B",
            status="active",
            created_by=self.actor,
            updated_by=self.actor,
        )
        self.user_1 = PlatformUser.objects.create(
            email=f"user1_{uuid.uuid4().hex[:6]}@example.com",
            full_name="User One",
            status="active",
            is_active=True,
        )
        self.user_2 = PlatformUser.objects.create(
            email=f"user2_{uuid.uuid4().hex[:6]}@example.com",
            full_name="User Two",
            status="active",
            is_active=True,
        )
        self.membership_1a = OrganizationMembership.objects.create(
            organization=self.org_a,
            user=self.user_1,
            membership_type="member",
            status="active",
            joined_at=timezone.now(),
        )
        self.membership_2a = OrganizationMembership.objects.create(
            organization=self.org_a,
            user=self.user_2,
            membership_type="member",
            status="active",
            joined_at=timezone.now(),
        )
        self.membership_1b = OrganizationMembership.objects.create(
            organization=self.org_b,
            user=self.user_1,
            membership_type="member",
            status="active",
            joined_at=timezone.now(),
        )
        self.product_lms = Product.objects.create(
            code=f"lms_{uuid.uuid4().hex[:6]}",
            name="Learning Management System",
            status="active",
            created_by=self.actor,
            updated_by=self.actor,
        )
        self.product_crm = Product.objects.create(
            code=f"crm_{uuid.uuid4().hex[:6]}",
            name="Customer Relationship Manager",
            status="active",
            created_by=self.actor,
            updated_by=self.actor,
        )
        self.module_grading = ProductModule.objects.create(
            product=self.product_lms,
            code="grading",
            name="Grading Module",
            status="active",
            created_by=self.actor,
            updated_by=self.actor,
        )
        self.module_forums = ProductModule.objects.create(
            product=self.product_lms,
            code="forums",
            name="Discussion Forums",
            status="active",
            created_by=self.actor,
            updated_by=self.actor,
        )

    # -------------------------------------------------------------------------
    # Test 01: Assignment creation valid
    # -------------------------------------------------------------------------
    def test_01_assignment_creation_valid(self):
        """Valid creation of UserProductAssignment and UserModuleAssignment with defaults."""
        now = timezone.now()
        assignment = UserProductAssignment.objects.create(
            organization=self.org_a,
            user=self.user_1,
            membership=self.membership_1a,
            product=self.product_lms,
            created_by=self.actor,
            updated_by=self.actor,
        )

        self.assertIsNotNone(assignment.id)
        self.assertIsInstance(assignment.id, uuid.UUID)
        self.assertEqual(assignment.status, AssignmentStatus.ACTIVE)
        self.assertAlmostEqual(assignment.assigned_at.timestamp(), now.timestamp(), delta=2.0)
        self.assertIsNotNone(assignment.created_at)
        self.assertIsNotNone(assignment.updated_at)
        self.assertIsNone(assignment.last_suspended_at)
        self.assertIsNone(assignment.last_reactivated_at)
        self.assertIsNone(assignment.revoked_at)
        self.assertEqual(assignment.suspension_reason, "")
        self.assertEqual(assignment.revocation_reason, "")

        # Create module assignment
        mod_assign = UserModuleAssignment.objects.create(
            assignment=assignment,
            module=self.module_grading,
        )
        self.assertIsNotNone(mod_assign.id)
        self.assertIsInstance(mod_assign.id, uuid.UUID)
        self.assertTrue(mod_assign.is_enabled)
        self.assertIsNotNone(mod_assign.created_at)
        self.assertIsNotNone(mod_assign.updated_at)

        # Assert UserProductAssignment metadata: exactly five authoritative explicit indexes
        product_assign_index_names = {idx.name for idx in UserProductAssignment._meta.indexes}
        expected_indexes = {
            "assign_org_prod_stat_idx",
            "assign_org_user_stat_idx",
            "assign_user_stat_idx",
            "assign_membership_stat_idx",
            "assign_time_id_idx",
        }
        self.assertEqual(product_assign_index_names, expected_indexes)

        # Assert UserProductAssignment metadata: four authoritative constraint names
        product_assign_constraint_names = {c.name for c in UserProductAssignment._meta.constraints}
        expected_product_constraints = {
            "assign_status_valid",
            "assign_revoked_at_sync",
            "assign_suspended_at_sync",
            "unique_open_user_product_assignment",
        }
        self.assertEqual(product_assign_constraint_names, expected_product_constraints)

        # Assert UserModuleAssignment metadata: one authoritative constraint name
        module_assign_constraint_names = {c.name for c in UserModuleAssignment._meta.constraints}
        expected_module_constraints = {
            "unique_assignment_module",
        }
        self.assertEqual(module_assign_constraint_names, expected_module_constraints)

    # -------------------------------------------------------------------------
    # Test 02: Status choices constraint
    # -------------------------------------------------------------------------
    def test_02_status_choices_constraint(self):
        """Invalid status fails at database constraint boundary."""
        with transaction.atomic():
            with self.assertRaises(IntegrityError):
                UserProductAssignment.objects.create(
                    organization=self.org_a,
                    user=self.user_1,
                    membership=self.membership_1a,
                    product=self.product_lms,
                    status="invalid_status",
                    created_by=self.actor,
                    updated_by=self.actor,
                )

    # -------------------------------------------------------------------------
    # Test 03: Partial unique constraint for open assignments
    # -------------------------------------------------------------------------
    def test_03_partial_unique_active_assignment(self):
        """Enforces unique open assignment per (organization, user, product)."""
        # First active assignment succeeds
        UserProductAssignment.objects.create(
            organization=self.org_a,
            user=self.user_1,
            membership=self.membership_1a,
            product=self.product_lms,
            status=AssignmentStatus.ACTIVE,
            created_by=self.actor,
            updated_by=self.actor,
        )

        # 1. Second active assignment for same (org, user, product) fails
        with transaction.atomic():
            with self.assertRaises(IntegrityError):
                UserProductAssignment.objects.create(
                    organization=self.org_a,
                    user=self.user_1,
                    membership=self.membership_1a,
                    product=self.product_lms,
                    status=AssignmentStatus.ACTIVE,
                    created_by=self.actor,
                    updated_by=self.actor,
                )

        # 2. Active + suspended duplicate fails
        with transaction.atomic():
            with self.assertRaises(IntegrityError):
                UserProductAssignment.objects.create(
                    organization=self.org_a,
                    user=self.user_1,
                    membership=self.membership_1a,
                    product=self.product_lms,
                    status=AssignmentStatus.SUSPENDED,
                    last_suspended_at=timezone.now(),
                    created_by=self.actor,
                    updated_by=self.actor,
                )

        # 3. Two suspended duplicates for user_2 fail
        UserProductAssignment.objects.create(
            organization=self.org_a,
            user=self.user_2,
            membership=self.membership_2a,
            product=self.product_lms,
            status=AssignmentStatus.SUSPENDED,
            last_suspended_at=timezone.now(),
            created_by=self.actor,
            updated_by=self.actor,
        )
        with transaction.atomic():
            with self.assertRaises(IntegrityError):
                UserProductAssignment.objects.create(
                    organization=self.org_a,
                    user=self.user_2,
                    membership=self.membership_2a,
                    product=self.product_lms,
                    status=AssignmentStatus.SUSPENDED,
                    last_suspended_at=timezone.now(),
                    created_by=self.actor,
                    updated_by=self.actor,
                )

    # -------------------------------------------------------------------------
    # Test 04: Reassign after revocation allowed
    # -------------------------------------------------------------------------
    def test_04_reassign_after_revocation_allowed(self):
        """Allows multiple historical revoked rows and creating a new active row."""
        now = timezone.now()

        # Revoked assignment 1
        revoked_1 = UserProductAssignment.objects.create(
            organization=self.org_a,
            user=self.user_1,
            membership=self.membership_1a,
            product=self.product_lms,
            status=AssignmentStatus.REVOKED,
            revoked_at=now,
            revocation_reason="Initial end",
            created_by=self.actor,
            updated_by=self.actor,
        )

        # Revoked assignment 2 (historical record allowed)
        revoked_2 = UserProductAssignment.objects.create(
            organization=self.org_a,
            user=self.user_1,
            membership=self.membership_1a,
            product=self.product_lms,
            status=AssignmentStatus.REVOKED,
            revoked_at=now,
            revocation_reason="Second end",
            created_by=self.actor,
            updated_by=self.actor,
        )
        self.assertNotEqual(revoked_1.id, revoked_2.id)

        # New active row is permitted after revocation
        active_new = UserProductAssignment.objects.create(
            organization=self.org_a,
            user=self.user_1,
            membership=self.membership_1a,
            product=self.product_lms,
            status=AssignmentStatus.ACTIVE,
            created_by=self.actor,
            updated_by=self.actor,
        )
        self.assertIsNotNone(active_new.id)

        # Same user can have assignment to different product in same org
        diff_prod = UserProductAssignment.objects.create(
            organization=self.org_a,
            user=self.user_1,
            membership=self.membership_1a,
            product=self.product_crm,
            status=AssignmentStatus.ACTIVE,
            created_by=self.actor,
            updated_by=self.actor,
        )
        self.assertIsNotNone(diff_prod.id)

        # Same user/product can be assigned in a different organization
        diff_org = UserProductAssignment.objects.create(
            organization=self.org_b,
            user=self.user_1,
            membership=self.membership_1b,
            product=self.product_lms,
            status=AssignmentStatus.ACTIVE,
            created_by=self.actor,
            updated_by=self.actor,
        )
        self.assertIsNotNone(diff_org.id)

    # -------------------------------------------------------------------------
    # Test 05: Module assignment unique constraint
    # -------------------------------------------------------------------------
    def test_05_module_assignment_unique_together(self):
        """Enforces uniqueness on (assignment, module)."""
        assignment = UserProductAssignment.objects.create(
            organization=self.org_a,
            user=self.user_1,
            membership=self.membership_1a,
            product=self.product_lms,
            created_by=self.actor,
            updated_by=self.actor,
        )

        # First module link succeeds
        UserModuleAssignment.objects.create(
            assignment=assignment,
            module=self.module_grading,
            is_enabled=True,
        )

        # Duplicate link for same module fails
        with transaction.atomic():
            with self.assertRaises(IntegrityError):
                UserModuleAssignment.objects.create(
                    assignment=assignment,
                    module=self.module_grading,
                    is_enabled=False,
                )

        # Multiple different modules for the same product assignment are allowed
        mod_2 = UserModuleAssignment.objects.create(
            assignment=assignment,
            module=self.module_forums,
            is_enabled=True,
        )
        self.assertIsNotNone(mod_2.id)

    # -------------------------------------------------------------------------
    # Test 06: Foreign key protect behavior
    # -------------------------------------------------------------------------
    def test_06_fk_protect_behavior(self):
        """Deleting referenced entities is protected by on_delete=PROTECT."""
        assignment = UserProductAssignment.objects.create(
            organization=self.org_a,
            user=self.user_1,
            membership=self.membership_1a,
            product=self.product_lms,
            created_by=self.actor,
            updated_by=self.actor,
        )
        UserModuleAssignment.objects.create(
            assignment=assignment,
            module=self.module_grading,
        )

        with self.assertRaises(ProtectedError):
            self.org_a.delete()

        with self.assertRaises(ProtectedError):
            self.user_1.delete()

        with self.assertRaises(ProtectedError):
            self.membership_1a.delete()

        with self.assertRaises(ProtectedError):
            self.product_lms.delete()

        with self.assertRaises(ProtectedError):
            self.module_grading.delete()

        with self.assertRaises(ProtectedError):
            self.actor.delete()

    # -------------------------------------------------------------------------
    # Test 07: Module assignment cascade behavior
    # -------------------------------------------------------------------------
    def test_07_module_assignment_cascade(self):
        """Deleting UserProductAssignment cascades to its UserModuleAssignment rows."""
        assignment = UserProductAssignment.objects.create(
            organization=self.org_a,
            user=self.user_1,
            membership=self.membership_1a,
            product=self.product_lms,
            created_by=self.actor,
            updated_by=self.actor,
        )
        mod_1 = UserModuleAssignment.objects.create(
            assignment=assignment,
            module=self.module_grading,
        )
        mod_2 = UserModuleAssignment.objects.create(
            assignment=assignment,
            module=self.module_forums,
        )

        assignment_id = assignment.id
        mod_1_id = mod_1.id
        mod_2_id = mod_2.id

        # Delete the assignment
        assignment.delete()

        self.assertFalse(UserProductAssignment.objects.filter(id=assignment_id).exists())
        self.assertFalse(UserModuleAssignment.objects.filter(id=mod_1_id).exists())
        self.assertFalse(UserModuleAssignment.objects.filter(id=mod_2_id).exists())

    # -------------------------------------------------------------------------
    # Test 08: Revoked timestamp synchronization constraint
    # -------------------------------------------------------------------------
    def test_08_revoked_at_check_constraint(self):
        """Enforces assign_revoked_at_sync check constraint."""
        now = timezone.now()

        # 1. status=revoked without revoked_at fails
        with transaction.atomic():
            with self.assertRaises(IntegrityError):
                UserProductAssignment.objects.create(
                    organization=self.org_a,
                    user=self.user_1,
                    membership=self.membership_1a,
                    product=self.product_lms,
                    status=AssignmentStatus.REVOKED,
                    revoked_at=None,
                    created_by=self.actor,
                    updated_by=self.actor,
                )

        # 2. status=revoked with revoked_at succeeds
        revoked_ok = UserProductAssignment.objects.create(
            organization=self.org_a,
            user=self.user_1,
            membership=self.membership_1a,
            product=self.product_lms,
            status=AssignmentStatus.REVOKED,
            revoked_at=now,
            created_by=self.actor,
            updated_by=self.actor,
        )
        self.assertIsNotNone(revoked_ok.id)

        # 3. status=active with revoked_at fails
        with transaction.atomic():
            with self.assertRaises(IntegrityError):
                UserProductAssignment.objects.create(
                    organization=self.org_a,
                    user=self.user_2,
                    membership=self.membership_2a,
                    product=self.product_lms,
                    status=AssignmentStatus.ACTIVE,
                    revoked_at=now,
                    created_by=self.actor,
                    updated_by=self.actor,
                )

        # 4. status=suspended with revoked_at fails
        with transaction.atomic():
            with self.assertRaises(IntegrityError):
                UserProductAssignment.objects.create(
                    organization=self.org_a,
                    user=self.user_2,
                    membership=self.membership_2a,
                    product=self.product_lms,
                    status=AssignmentStatus.SUSPENDED,
                    last_suspended_at=now,
                    revoked_at=now,
                    created_by=self.actor,
                    updated_by=self.actor,
                )

    # -------------------------------------------------------------------------
    # Test 09: Suspended timestamp constraint
    # -------------------------------------------------------------------------
    def test_09_suspended_at_check_constraint(self):
        """Enforces assign_suspended_at_sync check constraint."""
        now = timezone.now()

        # 1. status=suspended without last_suspended_at fails
        with transaction.atomic():
            with self.assertRaises(IntegrityError):
                UserProductAssignment.objects.create(
                    organization=self.org_a,
                    user=self.user_1,
                    membership=self.membership_1a,
                    product=self.product_lms,
                    status=AssignmentStatus.SUSPENDED,
                    last_suspended_at=None,
                    created_by=self.actor,
                    updated_by=self.actor,
                )

        # 2. status=suspended with last_suspended_at succeeds
        suspended_ok = UserProductAssignment.objects.create(
            organization=self.org_a,
            user=self.user_1,
            membership=self.membership_1a,
            product=self.product_lms,
            status=AssignmentStatus.SUSPENDED,
            last_suspended_at=now,
            created_by=self.actor,
            updated_by=self.actor,
        )
        self.assertIsNotNone(suspended_ok.id)

        # 3. active assignment retaining historical last_suspended_at succeeds
        active_with_historical = UserProductAssignment.objects.create(
            organization=self.org_a,
            user=self.user_2,
            membership=self.membership_2a,
            product=self.product_lms,
            status=AssignmentStatus.ACTIVE,
            last_suspended_at=now,
            last_reactivated_at=now,
            created_by=self.actor,
            updated_by=self.actor,
        )
        self.assertIsNotNone(active_with_historical.id)

    # -------------------------------------------------------------------------
    # Test 10: Immutability of identity fields on existing assignments
    # -------------------------------------------------------------------------
    def test_10_immutable_assignment_identity_fields(self):
        """Mutating identity fields raises AssignmentImmutabilityError."""
        assignment = UserProductAssignment.objects.create(
            organization=self.org_a,
            user=self.user_1,
            membership=self.membership_1a,
            product=self.product_lms,
            created_by=self.actor,
            updated_by=self.actor,
        )

        # 1. Mutating product_id
        assignment.product = self.product_crm
        with self.assertRaises(AssignmentImmutabilityError):
            assignment.save()
        assignment.refresh_from_db()

        # 2. Mutating user_id
        assignment.user = self.user_2
        with self.assertRaises(AssignmentImmutabilityError):
            assignment.save()
        assignment.refresh_from_db()

        # 3. Mutating organization_id
        assignment.organization = self.org_b
        with self.assertRaises(AssignmentImmutabilityError):
            assignment.save()
        assignment.refresh_from_db()

        # 4. Mutating membership_id
        assignment.membership = self.membership_2a
        with self.assertRaises(AssignmentImmutabilityError):
            assignment.save()
        assignment.refresh_from_db()

        # 5. Mutating via update_fields containing immutable field
        with self.assertRaises(AssignmentImmutabilityError):
            assignment.save(update_fields=["product_id", "status"])

        # 6. Mutable field (status, updated_by, last_suspended_at) updates successfully
        now = timezone.now()
        assignment.status = AssignmentStatus.SUSPENDED
        assignment.last_suspended_at = now
        assignment.suspension_reason = "Valid update"
        assignment.save(update_fields=["status", "last_suspended_at", "suspension_reason", "updated_at"])
        assignment.refresh_from_db()
        self.assertEqual(assignment.status, AssignmentStatus.SUSPENDED)
        self.assertEqual(assignment.suspension_reason, "Valid update")

    # -------------------------------------------------------------------------
    # Test 11: Membership organization mismatch rejected
    # -------------------------------------------------------------------------
    def test_11_membership_organization_mismatch_rejected(self):
        """Assigning with membership from different organization raises MembershipValidationError."""
        # membership_1b belongs to org_b, but assignment specifies org_a
        assignment = UserProductAssignment(
            organization=self.org_a,
            user=self.user_1,
            membership=self.membership_1b,
            product=self.product_lms,
            created_by=self.actor,
            updated_by=self.actor,
        )
        with self.assertRaises(MembershipValidationError) as ctx:
            assignment.save()
        self.assertIn("organization does not match", str(ctx.exception))

    # -------------------------------------------------------------------------
    # Test 12: Membership user mismatch rejected
    # -------------------------------------------------------------------------
    def test_12_membership_user_mismatch_rejected(self):
        """Assigning with membership belonging to different user raises MembershipValidationError."""
        # membership_2a belongs to user_2, but assignment specifies user_1
        assignment = UserProductAssignment(
            organization=self.org_a,
            user=self.user_1,
            membership=self.membership_2a,
            product=self.product_lms,
            created_by=self.actor,
            updated_by=self.actor,
        )
        with self.assertRaises(MembershipValidationError) as ctx:
            assignment.save()
        self.assertIn("user does not match", str(ctx.exception))
