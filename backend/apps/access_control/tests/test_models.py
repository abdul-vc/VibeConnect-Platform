"""Stage 1 focused database tests for access_control models, constraints, bootstrap, and backfill."""

from django.apps import apps
from django.contrib.auth import get_user_model
from django.db import IntegrityError, connection, transaction
from django.db.models import ProtectedError
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase
from django.utils import timezone

from apps.access_control.models import (
    AccessPermission,
    ConsoleModule,
    OrganizationConsoleModulePolicy,
    OrganizationPermissionCeiling,
    Role,
    RolePermission,
)
from apps.organizations.models import (
    MembershipStatus,
    MembershipType,
    Organization,
    OrganizationMembership,
)

PlatformUser = get_user_model()


def _create_user(email="test_user@example.com", is_owner=False):
    u, _ = PlatformUser.objects.get_or_create(
        email=email,
        defaults={
            "full_name": "Test User",
            "status": "active",
            "is_active": True,
            "is_platform_owner": is_owner,
        },
    )
    return u


def _create_org(code="test-org-1", owner=None):
    if owner is None:
        owner = _create_user("owner_for_org@example.com", is_owner=True)
    return Organization.objects.create(
        code=code,
        name=f"Test Org {code}",
        status="active",
        created_by=owner,
        updated_by=owner,
    )


class TestBootstrapRegistry(TestCase):
    """Verifies that 0002_bootstrap_access_control seeded the frozen platform registry."""

    def test_platform_owner_modules_seeded(self):
        expected_po_keys = {
            "po_overview",
            "po_products",
            "po_plans",
            "po_subscriptions",
            "po_organizations",
            "po_users",
            "po_entitlements",
            "po_activity_log",
        }
        po_modules = ConsoleModule.objects.filter(target_context="platform_owner")
        self.assertEqual(set(po_modules.values_list("key", flat=True)), expected_po_keys)
        for m in po_modules:
            self.assertTrue(m.is_core)
            self.assertTrue(m.is_active)

    def test_tenant_modules_seeded(self):
        landing = ConsoleModule.objects.get(key="tenant_landing")
        self.assertEqual(landing.target_context, "tenant")
        self.assertTrue(landing.is_core)
        self.assertTrue(landing.is_active)

        roles_mod = ConsoleModule.objects.get(key="tenant_roles")
        self.assertEqual(roles_mod.target_context, "tenant")
        self.assertFalse(roles_mod.is_core)
        self.assertTrue(roles_mod.is_active)

    def test_access_permissions_seeded(self):
        expected_perms = {
            "roles.view",
            "roles.manage",
            "roles.assign",
            "assignments.view",
            "assignments.manage",
            "products.view",
            "bulk_import.view",
            "bulk_import.manage",
            "access_requests.view",
            "access_requests.manage",
            "access_requests.decide",
            "notifications.view",
            "reports.view",
            "billing.manage",
            "billing.view",
            "branding.manage",
            "branding.view",
            "usage.manage",
            "usage.view",
            "support.diagnostics.view",
            "support.operations.retry",
            "support.operations.resolve",
            "support.impersonation.initiate",
        }
        perms = AccessPermission.objects.all()
        self.assertEqual(set(perms.values_list("key", flat=True)), expected_perms)
        roles_perms = perms.filter(key__startswith="roles.")
        for p in roles_perms:
            self.assertEqual(p.console_module_id, "tenant_roles")
            self.assertEqual(p.category, "roles")
            self.assertTrue(p.is_active)
        asgn_perms = perms.filter(key__startswith="assignments.")
        for p in asgn_perms:
            self.assertEqual(p.console_module_id, "tenant_product_assignments")
            self.assertEqual(p.category, "Tenant Administration")
            self.assertTrue(p.is_active)

    def test_system_role_seeded(self):
        sys_role = Role.objects.get(code="system_tenant_admin")
        self.assertTrue(sys_role.is_system_role)
        self.assertIsNone(sys_role.organization)
        self.assertEqual(sys_role.status, "active")

        granted_perms = set(
            RolePermission.objects.filter(role=sys_role).values_list("permission_id", flat=True)
        )
        expected_perms = {
            "roles.view",
            "roles.manage",
            "roles.assign",
            "assignments.view",
            "assignments.manage",
            "products.view",
            "bulk_import.view",
            "bulk_import.manage",
            "access_requests.view",
            "access_requests.manage",
            "access_requests.decide",
            "notifications.view",
            "reports.view",
            "billing.manage",
            "billing.view",
            "branding.manage",
            "branding.view",
            "usage.manage",
            "usage.view",
        }
        self.assertEqual(granted_perms, expected_perms)


class TestRoleDatabaseConstraints(TestCase):
    """Verifies Role model PostgreSQL constraints."""

    def setUp(self):
        self.owner = _create_user("role_owner@example.com", is_owner=True)
        self.org = _create_org(code="role-test-org", owner=self.owner)

    def test_valid_custom_role_succeeds(self):
        role = Role.objects.create(
            code="custom_auditor",
            name="Custom Auditor",
            organization=self.org,
            is_system_role=False,
            status="active",
        )
        self.assertIsNotNone(role.id)
        self.assertEqual(role.code, "custom_auditor")
        self.assertEqual(role.organization, self.org)

    def test_invalid_role_code_format_fails(self):
        invalid_codes = [
            "ROLE_UPPER",
            "role-hyphen",
            "_leading_underscore",
            "trailing_underscore_",
            "double__underscore",
            "role with spaces",
            "role.dotted",
        ]
        for invalid_code in invalid_codes:
            with self.subTest(code=invalid_code):
                with self.assertRaises(IntegrityError):
                    with transaction.atomic():
                        Role.objects.create(
                            code=invalid_code,
                            name="Invalid Role",
                            organization=self.org,
                            is_system_role=False,
                            status="active",
                        )

    def test_invalid_role_status_fails(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Role.objects.create(
                    code="status_invalid",
                    name="Invalid Status",
                    organization=self.org,
                    is_system_role=False,
                    status="pending",
                )

    def test_system_role_with_organization_fails(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Role.objects.create(
                    code="sys_with_org",
                    name="Invalid System Role",
                    organization=self.org,
                    is_system_role=True,
                    status="active",
                )

    def test_custom_role_without_organization_fails(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Role.objects.create(
                    code="custom_without_org",
                    name="Invalid Custom Role",
                    organization=None,
                    is_system_role=False,
                    status="active",
                )

    def test_duplicate_custom_role_code_in_same_org_fails(self):
        Role.objects.create(
            code="duplicate_code",
            name="Original Role",
            organization=self.org,
            is_system_role=False,
            status="active",
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Role.objects.create(
                    code="duplicate_code",
                    name="Duplicate Role",
                    organization=self.org,
                    is_system_role=False,
                    status="active",
                )

    def test_same_custom_role_code_in_different_orgs_succeeds(self):
        org2 = _create_org(code="role-test-org-2", owner=self.owner)
        r1 = Role.objects.create(
            code="shared_role",
            name="Org 1 Role",
            organization=self.org,
            is_system_role=False,
            status="active",
        )
        r2 = Role.objects.create(
            code="shared_role",
            name="Org 2 Role",
            organization=org2,
            is_system_role=False,
            status="active",
        )
        self.assertNotEqual(r1.id, r2.id)

    def test_duplicate_system_role_code_fails(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Role.objects.create(
                    code="system_tenant_admin",
                    name="Duplicate System Admin",
                    organization=None,
                    is_system_role=True,
                    status="active",
                )


class TestRelationshipConstraints(TestCase):
    """Verifies uniqueness constraints on relationship models."""

    def setUp(self):
        self.owner = _create_user("rel_owner@example.com", is_owner=True)
        self.org = _create_org(code="rel-test-org", owner=self.owner)

    def test_duplicate_role_permission_fails(self):
        sys_role = Role.objects.get(code="system_tenant_admin")
        perm = AccessPermission.objects.get(key="roles.view")
        # sys_role already has roles.view from 0002 bootstrap
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                RolePermission.objects.create(role=sys_role, permission=perm)

    def test_duplicate_org_console_module_policy_fails(self):
        mod = ConsoleModule.objects.get(key="tenant_roles")
        OrganizationConsoleModulePolicy.objects.create(
            organization=self.org,
            console_module=mod,
            is_enabled=True,
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                OrganizationConsoleModulePolicy.objects.create(
                    organization=self.org,
                    console_module=mod,
                    is_enabled=False,
                )

    def test_duplicate_org_permission_ceiling_fails(self):
        perm = AccessPermission.objects.get(key="roles.view")
        OrganizationPermissionCeiling.objects.create(
            organization=self.org,
            permission=perm,
            is_allowed=True,
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                OrganizationPermissionCeiling.objects.create(
                    organization=self.org,
                    permission=perm,
                    is_allowed=False,
                )


class TestOrganizationMembershipRoleSync(TestCase):
    """Verifies membership_type_role_sync CheckConstraint on OrganizationMembership."""

    def setUp(self):
        self.owner = _create_user("mem_owner@example.com", is_owner=True)
        self.org = _create_org(code="mem-test-org", owner=self.owner)
        self.user = _create_user("target_user@example.com")
        self.sys_role = Role.objects.get(code="system_tenant_admin")

    def test_tenant_admin_with_role_succeeds(self):
        mem = OrganizationMembership.objects.create(
            organization=self.org,
            user=self.user,
            membership_type=MembershipType.TENANT_ADMIN,
            role=self.sys_role,
            status=MembershipStatus.ACTIVE,
            joined_at=timezone.now(),
        )
        self.assertEqual(mem.role, self.sys_role)
        self.assertEqual(mem.membership_type, MembershipType.TENANT_ADMIN)

    def test_tenant_admin_without_role_fails(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                OrganizationMembership.objects.create(
                    organization=self.org,
                    user=self.user,
                    membership_type=MembershipType.TENANT_ADMIN,
                    role=None,
                    status=MembershipStatus.ACTIVE,
                    joined_at=timezone.now(),
                )

    def test_member_without_role_succeeds(self):
        mem = OrganizationMembership.objects.create(
            organization=self.org,
            user=self.user,
            membership_type=MembershipType.MEMBER,
            role=None,
            status=MembershipStatus.ACTIVE,
            joined_at=timezone.now(),
        )
        self.assertIsNone(mem.role)
        self.assertEqual(mem.membership_type, MembershipType.MEMBER)

    def test_member_with_role_fails(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                OrganizationMembership.objects.create(
                    organization=self.org,
                    user=self.user,
                    membership_type=MembershipType.MEMBER,
                    role=self.sys_role,
                    status=MembershipStatus.ACTIVE,
                    joined_at=timezone.now(),
                )

    def test_assigned_role_deletion_is_protected(self):
        custom_role = Role.objects.create(
            code="protected_role",
            name="Protected Role",
            organization=self.org,
            is_system_role=False,
            status="active",
        )
        OrganizationMembership.objects.create(
            organization=self.org,
            user=self.user,
            membership_type=MembershipType.TENANT_ADMIN,
            role=custom_role,
            status=MembershipStatus.ACTIVE,
            joined_at=timezone.now(),
        )
        with self.assertRaises(ProtectedError):
            custom_role.delete()


class TestMembershipMigrationBackfill(TransactionTestCase):
    """Verifies pre-migration tenant_admin backfill and existing-org bootstrap."""

    def test_bootstrap_and_membership_backfill_migration(self):
        executor = MigrationExecutor(connection)
        try:
            # 1. Migrate back to before access_control.0002 and organizations.0003
            targets_pre = [
                ("access_control", "0001_initial"),
                ("organizations", "0002_organization_membership"),
            ]
            executor.migrate(targets_pre)
            executor.loader.build_graph()
            old_state = executor.loader.project_state(targets_pre)

            OrgModel = old_state.apps.get_model("organizations", "Organization")
            MemModel = old_state.apps.get_model("organizations", "OrganizationMembership")
            UserModel = old_state.apps.get_model("identity", "PlatformUser")

            owner = UserModel.objects.create(
                email="backfill_owner@example.com",
                full_name="Backfill Owner",
                status="active",
                is_active=True,
                is_platform_owner=True,
            )
            org = OrgModel.objects.create(
                code="backfill-org",
                name="Backfill Test Org",
                status="active",
                created_by=owner,
                updated_by=owner,
            )
            admin_user = UserModel.objects.create(
                email="backfill_admin@example.com",
                full_name="Backfill Admin",
                status="active",
                is_active=True,
            )
            member_user = UserModel.objects.create(
                email="backfill_member@example.com",
                full_name="Backfill Member",
                status="active",
                is_active=True,
            )

            # In organizations.0002 schema, role column does not exist
            admin_mem = MemModel.objects.create(
                organization=org,
                user=admin_user,
                membership_type="tenant_admin",
                status="active",
                joined_at=timezone.now(),
            )
            reg_mem = MemModel.objects.create(
                organization=org,
                user=member_user,
                membership_type="member",
                status="active",
                joined_at=timezone.now(),
            )

            # 2. Migrate forward through access_control.0002 (bootstrap)
            executor.loader.build_graph()
            executor.migrate([("access_control", "0002_bootstrap_access_control")])
            executor.loader.build_graph()
            mid_state = executor.loader.project_state([("access_control", "0002_bootstrap_access_control")])

            # Verify existing organization received policies and ceilings
            PolicyModel = mid_state.apps.get_model("access_control", "OrganizationConsoleModulePolicy")
            CeilingModel = mid_state.apps.get_model("access_control", "OrganizationPermissionCeiling")

            policies = PolicyModel.objects.filter(organization_id=org.id)
            self.assertEqual(
                set(policies.values_list("console_module_id", flat=True)),
                {"tenant_landing", "tenant_roles"},
            )
            for pol in policies:
                self.assertTrue(pol.is_enabled)

            ceilings = CeilingModel.objects.filter(organization_id=org.id)
            self.assertEqual(
                set(ceilings.values_list("permission_id", flat=True)),
                {"roles.view", "roles.manage", "roles.assign"},
            )
            for ceil in ceilings:
                self.assertTrue(ceil.is_allowed)

            # 3. Migrate forward through organizations.0003 (backfill + constraint)
            executor.loader.build_graph()
            targets_post = [("organizations", "0003_organizationmembership_role")]
            executor.migrate(targets_post)
            executor.loader.build_graph()
            post_state = executor.loader.project_state(targets_post)

            RoleModel = post_state.apps.get_model("access_control", "Role")
            PostMemModel = post_state.apps.get_model("organizations", "OrganizationMembership")
            sys_role = RoleModel.objects.get(code="system_tenant_admin", is_system_role=True)

            refreshed_admin_mem = PostMemModel.objects.get(id=admin_mem.id)
            refreshed_reg_mem = PostMemModel.objects.get(id=reg_mem.id)

            # tenant_admin received system_tenant_admin role
            self.assertEqual(refreshed_admin_mem.role_id, sys_role.id)
            # member retained role = None
            self.assertIsNone(refreshed_reg_mem.role_id)

        finally:
            # Always restore latest migration state for test database tear-down
            executor.loader.build_graph()
            executor.migrate(executor.loader.graph.leaf_nodes())
