"""Focused PostgreSQL Concurrency Tests for Last-Admin Protection (Phase 2E Stage 5).

Verifies:
- Pessimistic locking boundary during concurrent administrative role demotion.
- Two concurrent downgrade transactions cannot eliminate all capable administrators.
- At least one transaction fails with LAST_ADMIN_PROTECTION.
- Database state retains at least one capable administrator without corruption.
"""

import threading

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TransactionTestCase
from django.utils import timezone

from apps.access_control.models import (
    AccessPermission,
    OrganizationConsoleModulePolicy,
    OrganizationPermissionCeiling,
    Role,
    RolePermission,
    RoleStatus,
)
from apps.access_control.services.assignment_services import assign_membership_role
from apps.access_control.services.guards import LastAdminProtectionError
from apps.organizations.models import (
    MembershipStatus,
    MembershipType,
    Organization,
    OrganizationMembership,
    OrganizationStatus,
)

PlatformUser = get_user_model()


class LastAdminConcurrencyTests(TransactionTestCase):
    """PostgreSQL-backed concurrency verification for last-admin protection invariants."""

    def setUp(self):
        super().setUp()
        self.password = "SecureConcurrPass123!"

        # 1. Owner
        self.owner = PlatformUser.objects.create_user(
            email="concurr_owner@vibeconnect.internal",
            password=self.password,
            full_name="Concurrency Owner",
            status="active",
            is_active=True,
            is_platform_owner=True,
        )

        # 2. Organization
        self.org = Organization.objects.create(
            code="concurr-org",
            name="Concurrency Org",
            status=OrganizationStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )

        # 3. Enable tenant_roles module and permission ceilings for org
        OrganizationConsoleModulePolicy.objects.get_or_create(
            organization=self.org,
            console_module_id="tenant_roles",
            defaults={"is_enabled": True, "updated_by": self.owner},
        )
        for perm_key in ["roles.view", "roles.manage", "roles.assign"]:
            OrganizationPermissionCeiling.objects.get_or_create(
                organization=self.org,
                permission_id=perm_key,
                defaults={"is_allowed": True, "updated_by": self.owner},
            )

        # 4. System Tenant Admin role and permissions
        self.system_role = Role.objects.get(code="system_tenant_admin", is_system_role=True)

        # 4. Restricted role (view only - lacks roles.manage and roles.assign)
        self.restricted_role = Role.objects.create(
            organization=self.org,
            code="restricted_viewer",
            name="Restricted Viewer",
            is_system_role=False,
            status=RoleStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )
        perm_view = AccessPermission.objects.get(key="roles.view")
        RolePermission.objects.create(role=self.restricted_role, permission=perm_view)

        # 5. Two capable Tenant Admins assigned system_tenant_admin
        self.admin1_user = PlatformUser.objects.create_user(
            email="admin1@vibeconnect.internal",
            password=self.password,
            full_name="Admin One",
            status="active",
            is_active=True,
            is_platform_owner=False,
        )
        self.admin2_user = PlatformUser.objects.create_user(
            email="admin2@vibeconnect.internal",
            password=self.password,
            full_name="Admin Two",
            status="active",
            is_active=True,
            is_platform_owner=False,
        )

        self.mem1 = OrganizationMembership.objects.create(
            organization=self.org,
            user=self.admin1_user,
            membership_type=MembershipType.TENANT_ADMIN,
            status=MembershipStatus.ACTIVE,
            role=self.system_role,
            joined_at=timezone.now(),
        )
        self.mem2 = OrganizationMembership.objects.create(
            organization=self.org,
            user=self.admin2_user,
            membership_type=MembershipType.TENANT_ADMIN,
            status=MembershipStatus.ACTIVE,
            role=self.system_role,
            joined_at=timezone.now(),
        )

    def test_concurrent_downgrades_prevent_last_admin_elimination(self):
        """Two concurrent operations attempting to downgrade both admins must not both succeed."""
        barrier = threading.Barrier(2)
        results = {}

        def thread_1_downgrade():
            try:
                barrier.wait(timeout=10)
                assign_membership_role(
                    actor=self.admin1_user,
                    organization_id=self.org.id,
                    membership_id=self.mem1.id,
                    role_id=self.restricted_role.id,
                )
                results["t1"] = "SUCCESS"
            except Exception as e:
                results["t1"] = e
            finally:
                connection.close()

        def thread_2_downgrade():
            try:
                barrier.wait(timeout=10)
                assign_membership_role(
                    actor=self.admin2_user,
                    organization_id=self.org.id,
                    membership_id=self.mem2.id,
                    role_id=self.restricted_role.id,
                )
                results["t2"] = "SUCCESS"
            except Exception as e:
                results["t2"] = e
            finally:
                connection.close()

        t1 = threading.Thread(target=thread_1_downgrade)
        t2 = threading.Thread(target=thread_2_downgrade)

        t1.start()
        t2.start()

        t1.join(timeout=15)
        t2.join(timeout=15)

        # Invariant 1: Both threads completed
        self.assertIn("t1", results)
        self.assertIn("t2", results)

        # Invariant 2: Both must not succeed simultaneously
        success_count = sum(1 for res in (results["t1"], results["t2"]) if res == "SUCCESS")
        self.assertEqual(
            success_count,
            1,
            f"Expected exactly 1 downgrade to succeed and 1 to be blocked. Got results: t1={results['t1']}, t2={results['t2']}",
        )

        # Invariant 3: At least one operation was rejected with LAST_ADMIN_PROTECTION
        errors = [res for res in (results["t1"], results["t2"]) if res != "SUCCESS"]
        self.assertEqual(len(errors), 1)
        err = errors[0]
        self.assertIsInstance(err, LastAdminProtectionError)
        self.assertEqual(err.code, "LAST_ADMIN_PROTECTION")

        # Invariant 4: Organization retains at least one capable admin
        self.mem1.refresh_from_db()
        self.mem2.refresh_from_db()

        capable_memberships = [
            m
            for m in (self.mem1, self.mem2)
            if m.role.role_permissions.filter(
                permission_id__in=["roles.manage", "roles.assign"]
            ).count()
            == 2
        ]
        self.assertEqual(len(capable_memberships), 1)

        # Invariant 5: No corruption - one membership has restricted role, one has system role
        roles = {self.mem1.role_id, self.mem2.role_id}
        self.assertEqual(roles, {self.restricted_role.id, self.system_role.id})
