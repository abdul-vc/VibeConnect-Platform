"""Stage 2 focused domain service tests for access_control."""

import uuid

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.access_control.models import (
    AccessPermission,
    ConsoleModule,
    OrganizationConsoleModulePolicy,
    OrganizationPermissionCeiling,
    Role,
    RolePermission,
)
from apps.access_control.services.assignment_services import assign_membership_role
from apps.access_control.services.ceiling_services import set_permission_ceiling
from apps.access_control.services.guards import (
    AccessControlValidationError,
    InsufficientPrivilegesError,
    LastAdminProtectionError,
    ModuleCannotBeDisabledError,
    ModuleNotFoundError,
    PermissionNotFoundError,
    PermissionOutsideCeilingError,
    RoleInUseError,
    RoleNotAssignableToMemberError,
    RoleNotFoundError,
    RoleRetiredError,
    SystemRoleImmutableError,
)
from apps.access_control.services.policy_services import set_console_module_policy
from apps.access_control.services.provisioning import provision_organization_defaults
from apps.access_control.services.role_services import create_role, retire_role, update_role
from apps.auditlog.models import AuditAction, AuditLog
from apps.organizations.models import (
    MembershipStatus,
    MembershipType,
    Organization,
    OrganizationMembership,
)

PlatformUser = get_user_model()


class BaseAccessControlServiceTestCase(TestCase):
    def setUp(self):
        # Platform Owner
        self.owner = PlatformUser.objects.create(
            email="po_admin@example.com",
            full_name="Platform Owner",
            status="active",
            is_active=True,
            is_platform_owner=True,
        )

        # Organization
        self.org = Organization.objects.create(
            code="ac-test-org",
            name="AC Test Org",
            status="active",
            created_by=self.owner,
            updated_by=self.owner,
        )
        provision_organization_defaults(organization=self.org, actor=self.owner)

        # System role
        self.sys_role = Role.objects.get(code="system_tenant_admin", is_system_role=True)

        # Primary Tenant Admin
        self.admin_user = PlatformUser.objects.create(
            email="primary_admin@example.com",
            full_name="Primary Admin",
            status="active",
            is_active=True,
        )
        self.admin_mem = OrganizationMembership.objects.create(
            organization=self.org,
            user=self.admin_user,
            membership_type=MembershipType.TENANT_ADMIN,
            role=self.sys_role,
            status=MembershipStatus.ACTIVE,
            joined_at=timezone.now(),
        )

        # Secondary Tenant Admin (to test safe last-admin mutations)
        self.admin_user2 = PlatformUser.objects.create(
            email="secondary_admin@example.com",
            full_name="Secondary Admin",
            status="active",
            is_active=True,
        )
        self.admin_mem2 = OrganizationMembership.objects.create(
            organization=self.org,
            user=self.admin_user2,
            membership_type=MembershipType.TENANT_ADMIN,
            role=self.sys_role,
            status=MembershipStatus.ACTIVE,
            joined_at=timezone.now(),
        )

        # Regular Member
        self.regular_user = PlatformUser.objects.create(
            email="regular_user@example.com",
            full_name="Regular User",
            status="active",
            is_active=True,
        )
        self.reg_mem = OrganizationMembership.objects.create(
            organization=self.org,
            user=self.regular_user,
            membership_type=MembershipType.MEMBER,
            role=None,
            status=MembershipStatus.ACTIVE,
            joined_at=timezone.now(),
        )


class TestRoleServices(BaseAccessControlServiceTestCase):
    """Tests for create_role, update_role, and retire_role."""

    def test_valid_custom_role_creation(self):
        role = create_role(
            actor=self.admin_user,
            organization_id=self.org.id,
            code="auditor_lead",
            name="Auditor Lead",
            description="Inspects role configurations",
            permission_keys=["roles.view"],
        )
        self.assertIsNotNone(role.id)
        self.assertEqual(role.code, "auditor_lead")
        self.assertEqual(role.organization, self.org)
        self.assertFalse(role.is_system_role)

        perms = list(RolePermission.objects.filter(role=role).values_list("permission_id", flat=True))
        self.assertEqual(perms, ["roles.view"])

        audit = AuditLog.objects.filter(action=AuditAction.ROLE_CREATED, target_id=role.id).first()
        self.assertIsNotNone(audit)
        self.assertEqual(audit.metadata["permission_keys"], ["roles.view"])

    def test_role_creation_dependency_rejection(self):
        # roles.manage without roles.view
        with self.assertRaises(AccessControlValidationError) as ctx:
            create_role(
                actor=self.admin_user,
                organization_id=self.org.id,
                code="invalid_manage",
                name="Invalid Manage",
                permission_keys=["roles.manage"],
            )
        self.assertEqual(ctx.exception.code, "VALIDATION_ERROR")

        # roles.assign without roles.view
        with self.assertRaises(AccessControlValidationError) as ctx:
            create_role(
                actor=self.admin_user,
                organization_id=self.org.id,
                code="invalid_assign",
                name="Invalid Assign",
                permission_keys=["roles.assign"],
            )
        self.assertEqual(ctx.exception.code, "VALIDATION_ERROR")

    def test_unknown_or_outside_ceiling_permission_rejection(self):
        with self.assertRaises(PermissionNotFoundError):
            create_role(
                actor=self.admin_user,
                organization_id=self.org.id,
                code="unknown_perm",
                name="Unknown Perm",
                permission_keys=["roles.view", "nonexistent.perm"],
            )

        # Deny roles.assign in ceiling
        OrganizationPermissionCeiling.objects.filter(
            organization=self.org, permission_id="roles.assign"
        ).update(is_allowed=False)
        try:
            with self.assertRaises(PermissionOutsideCeilingError):
                create_role(
                    actor=self.admin_user,
                    organization_id=self.org.id,
                    code="ceiling_blocked",
                    name="Ceiling Blocked",
                    permission_keys=["roles.view", "roles.assign"],
                )
        finally:
            OrganizationPermissionCeiling.objects.filter(
                organization=self.org, permission_id="roles.assign"
            ).update(is_allowed=True)

    def test_actor_cannot_create_broader_role_than_own_authority(self):
        # Create an admin with limited role having only roles.view and roles.manage
        limited_role = Role.objects.create(
            organization=self.org,
            code="limited_mgr",
            name="Limited Manager",
            status="active",
        )
        RolePermission.objects.create(role=limited_role, permission_id="roles.view")
        RolePermission.objects.create(role=limited_role, permission_id="roles.manage")

        self.admin_mem.role = limited_role
        self.admin_mem.save(update_fields=["role"])

        # Actor tries to create a role with roles.assign (which actor lacks)
        with self.assertRaises(InsufficientPrivilegesError) as ctx:
            create_role(
                actor=self.admin_user,
                organization_id=self.org.id,
                code="escalated_role",
                name="Escalated Role",
                permission_keys=["roles.view", "roles.assign"],
            )
        self.assertEqual(ctx.exception.code, "INSUFFICIENT_PRIVILEGES")

    def test_equal_permission_sets_allowed_subset_semantics(self):
        """Ordinary subset semantics (<=) must permit creating and assigning a role with the exact same permission set."""
        # Actor holds roles.view, roles.manage, roles.assign
        role = create_role(
            actor=self.admin_user,
            organization_id=self.org.id,
            code="equal_perm_role",
            name="Equal Permission Role",
            permission_keys=["roles.view", "roles.manage", "roles.assign"],
        )
        self.assertIsNotNone(role)
        self.assertEqual(role.role_permissions.count(), 3)

        # Assignment with exact same permission set succeeds
        assigned = assign_membership_role(
            actor=self.admin_user,
            organization_id=self.org.id,
            membership_id=self.admin_mem2.id,
            role_id=role.id,
        )
        self.assertEqual(assigned.role_id, role.id)

    def test_role_update_permits_safe_removal_and_rejects_unauthorized_additions(self):
        """Role update non-escalation only validates newly added permissions."""
        full_role = Role.objects.create(
            organization=self.org,
            code="full_role",
            name="Full Role",
            status="active",
        )
        RolePermission.objects.create(role=full_role, permission_id="roles.view")
        RolePermission.objects.create(role=full_role, permission_id="roles.manage")
        RolePermission.objects.create(role=full_role, permission_id="roles.assign")

        # Admin actor has limited authority (only roles.view, roles.manage)
        limited_role = Role.objects.create(
            organization=self.org,
            code="limited_mgr_2",
            name="Limited Manager 2",
            status="active",
        )
        RolePermission.objects.create(role=limited_role, permission_id="roles.view")
        RolePermission.objects.create(role=limited_role, permission_id="roles.manage")
        self.admin_mem.role = limited_role
        self.admin_mem.save(update_fields=["role"])

        # 1. Removing roles.assign succeeds even though actor lacks roles.assign
        updated = update_role(
            actor=self.admin_user,
            organization_id=self.org.id,
            role_id=full_role.id,
            permission_keys=["roles.view", "roles.manage"],
        )
        self.assertEqual(
            set(updated.role_permissions.values_list("permission_id", flat=True)),
            {"roles.view", "roles.manage"},
        )

        # 2. Adding roles.assign fails because actor lacks roles.assign
        with self.assertRaises(InsufficientPrivilegesError):
            update_role(
                actor=self.admin_user,
                organization_id=self.org.id,
                role_id=full_role.id,
                permission_keys=["roles.view", "roles.manage", "roles.assign"],
            )

    def test_system_role_immutable(self):
        with self.assertRaises(SystemRoleImmutableError):
            update_role(
                actor=self.admin_user,
                organization_id=self.org.id,
                role_id=self.sys_role.id,
                name="New Name",
            )
        with self.assertRaises(SystemRoleImmutableError):
            retire_role(
                actor=self.admin_user,
                organization_id=self.org.id,
                role_id=self.sys_role.id,
            )

    def test_retired_role_update_rejection(self):
        role = Role.objects.create(
            organization=self.org,
            code="retired_role",
            name="Retired Role",
            status="retired",
        )
        with self.assertRaises(RoleRetiredError):
            update_role(
                actor=self.admin_user,
                organization_id=self.org.id,
                role_id=role.id,
                name="Attempt Update",
            )

    def test_role_update_truthful_audit(self):
        role = Role.objects.create(
            organization=self.org,
            code="update_test_role",
            name="Initial Name",
            description="Initial Desc",
            status="active",
        )
        RolePermission.objects.create(role=role, permission_id="roles.view")

        initial_audit_count = AuditLog.objects.count()

        # 1. Update only profile fields
        update_role(
            actor=self.admin_user,
            organization_id=self.org.id,
            role_id=role.id,
            name="Updated Name",
        )
        self.assertEqual(AuditLog.objects.count(), initial_audit_count + 1)
        audit1 = AuditLog.objects.filter(action=AuditAction.ROLE_UPDATED).first()
        self.assertIsNotNone(audit1)
        self.assertTrue(audit1.metadata["name_changed"])
        self.assertFalse(audit1.metadata["description_changed"])

        # 2. Update permissions
        update_role(
            actor=self.admin_user,
            organization_id=self.org.id,
            role_id=role.id,
            permission_keys=["roles.view", "roles.manage"],
        )
        audit2 = AuditLog.objects.filter(action=AuditAction.ROLE_PERMISSIONS_CHANGED).first()
        self.assertIsNotNone(audit2)
        self.assertEqual(audit2.metadata["added_permission_keys"], ["roles.manage"])
        self.assertEqual(audit2.metadata["removed_permission_keys"], [])

        # 3. No-op update emits zero audit events
        count_before_noop = AuditLog.objects.count()
        update_role(
            actor=self.admin_user,
            organization_id=self.org.id,
            role_id=role.id,
            name="Updated Name",
            permission_keys=["roles.view", "roles.manage"],
        )
        self.assertEqual(AuditLog.objects.count(), count_before_noop)

    def test_permission_removal_last_admin_protection(self):
        # Custom full admin role assigned to the only capable admins
        full_custom = Role.objects.create(
            organization=self.org,
            code="full_custom",
            name="Full Custom",
            status="active",
        )
        RolePermission.objects.create(role=full_custom, permission_id="roles.view")
        RolePermission.objects.create(role=full_custom, permission_id="roles.manage")
        RolePermission.objects.create(role=full_custom, permission_id="roles.assign")

        self.admin_mem.role = full_custom
        self.admin_mem.save(update_fields=["role"])
        self.admin_mem2.delete()  # Leave only one admin

        # Attempt to strip roles.manage from full_custom
        with self.assertRaises(LastAdminProtectionError) as ctx:
            update_role(
                actor=self.admin_user,
                organization_id=self.org.id,
                role_id=full_custom.id,
                permission_keys=["roles.view", "roles.assign"],
            )
        self.assertEqual(ctx.exception.code, "LAST_ADMIN_PROTECTION")

    def test_role_retirement_blocked_when_in_use(self):
        custom_role = Role.objects.create(
            organization=self.org,
            code="in_use_role",
            name="In Use Role",
            status="active",
        )
        # Assign to regular member (or admin)
        OrganizationMembership.objects.create(
            organization=self.org,
            user=PlatformUser.objects.create(email="temp_user@example.com", status="active", is_active=True),
            membership_type=MembershipType.TENANT_ADMIN,
            role=custom_role,
            status=MembershipStatus.ACTIVE,
            joined_at=timezone.now(),
        )

        with self.assertRaises(RoleInUseError):
            retire_role(
                actor=self.admin_user,
                organization_id=self.org.id,
                role_id=custom_role.id,
            )

    def test_valid_safe_role_retirement(self):
        unused_role = Role.objects.create(
            organization=self.org,
            code="unused_role",
            name="Unused Role",
            status="active",
        )
        retire_role(
            actor=self.admin_user,
            organization_id=self.org.id,
            role_id=unused_role.id,
        )
        unused_role.refresh_from_db()
        self.assertEqual(unused_role.status, "retired")

        audit = AuditLog.objects.filter(action=AuditAction.ROLE_RETIRED, target_id=unused_role.id).first()
        self.assertIsNotNone(audit)
        self.assertEqual(audit.metadata["role_code"], "unused_role")


class TestAssignmentServices(BaseAccessControlServiceTestCase):
    """Tests for assign_membership_role."""

    def test_assignment_to_tenant_admin_succeeds(self):
        custom_role = Role.objects.create(
            organization=self.org,
            code="auditor_role",
            name="Auditor Role",
            status="active",
        )
        RolePermission.objects.create(role=custom_role, permission_id="roles.view")

        # Assign to active admin
        assign_membership_role(
            actor=self.admin_user,
            organization_id=self.org.id,
            membership_id=self.admin_mem2.id,
            role_id=custom_role.id,
        )
        self.admin_mem2.refresh_from_db()
        self.assertEqual(self.admin_mem2.role, custom_role)

        audit = AuditLog.objects.filter(action=AuditAction.MEMBERSHIP_ROLE_ASSIGNED).first()
        self.assertIsNotNone(audit)
        self.assertEqual(audit.metadata["resulting_role_code"], "auditor_role")

    def test_assignment_to_regular_member_rejected(self):
        with self.assertRaises(RoleNotAssignableToMemberError):
            assign_membership_role(
                actor=self.admin_user,
                organization_id=self.org.id,
                membership_id=self.reg_mem.id,
                role_id=self.sys_role.id,
            )

    def test_cross_tenant_assignment_rejected(self):
        other_org = Organization.objects.create(
            code="other-org",
            name="Other Org",
            status="active",
            created_by=self.owner,
            updated_by=self.owner,
        )
        other_admin = PlatformUser.objects.create(
            email="other_admin@example.com",
            full_name="Other Admin",
            status="active",
            is_active=True,
        )
        other_mem = OrganizationMembership.objects.create(
            organization=other_org,
            user=other_admin,
            membership_type=MembershipType.TENANT_ADMIN,
            role=self.sys_role,
            status=MembershipStatus.ACTIVE,
            joined_at=timezone.now(),
        )
        # 1. Target membership belongs to other_org, but actor queries in self.org scope -> rejected
        with self.assertRaises(AccessControlValidationError):
            assign_membership_role(
                actor=self.admin_user,
                organization_id=self.org.id,
                membership_id=other_mem.id,
                role_id=None,
            )
        # 2. Scope is other_org, but actor has no tenant_admin membership in other_org -> rejected
        with self.assertRaises(InsufficientPrivilegesError):
            assign_membership_role(
                actor=self.admin_user,
                organization_id=other_org.id,
                membership_id=other_mem.id,
                role_id=None,
            )

    def test_role_assignment_non_escalation(self):
        # Create a broader role with all 3 permissions
        super_custom = Role.objects.create(
            organization=self.org,
            code="super_custom",
            name="Super Custom",
            status="active",
        )
        for p in ("roles.view", "roles.manage", "roles.assign"):
            RolePermission.objects.create(role=super_custom, permission_id=p)

        # Restrict actor to roles.view and roles.assign only
        restricted_role = Role.objects.create(
            organization=self.org,
            code="restricted_assigner",
            name="Restricted Assigner",
            status="active",
        )
        RolePermission.objects.create(role=restricted_role, permission_id="roles.view")
        RolePermission.objects.create(role=restricted_role, permission_id="roles.assign")

        self.admin_mem.role = restricted_role
        self.admin_mem.save(update_fields=["role"])

        # Actor attempts to assign super_custom (which contains roles.manage that actor lacks)
        with self.assertRaises(InsufficientPrivilegesError):
            assign_membership_role(
                actor=self.admin_user,
                organization_id=self.org.id,
                membership_id=self.admin_mem2.id,
                role_id=super_custom.id,
            )

    def test_last_admin_assignment_rejection(self):
        # admin_mem2 is deleted, admin_mem is the only admin
        self.admin_mem2.delete()

        view_only_role = Role.objects.create(
            organization=self.org,
            code="view_only",
            name="View Only",
            status="active",
        )
        RolePermission.objects.create(role=view_only_role, permission_id="roles.view")

        # Attempt to demote sole admin to view_only
        with self.assertRaises(LastAdminProtectionError) as ctx:
            assign_membership_role(
                actor=self.admin_user,
                organization_id=self.org.id,
                membership_id=self.admin_mem.id,
                role_id=view_only_role.id,
            )
        self.assertEqual(ctx.exception.code, "LAST_ADMIN_PROTECTION")


class TestPolicyAndCeilingServices(BaseAccessControlServiceTestCase):
    """Tests for set_console_module_policy and set_permission_ceiling."""

    def test_module_policy_core_protection(self):
        with self.assertRaises(ModuleCannotBeDisabledError):
            set_console_module_policy(
                actor=self.owner,
                organization_id=self.org.id,
                module_key="tenant_landing",
                is_enabled=False,
            )

    def test_po_module_policy_rejection(self):
        with self.assertRaises(ModuleNotFoundError):
            set_console_module_policy(
                actor=self.owner,
                organization_id=self.org.id,
                module_key="po_overview",
                is_enabled=True,
            )

    def test_coherent_and_incoherent_ceiling_changes(self):
        # Denying roles.view while roles.manage is allowed is incoherent
        with self.assertRaises(AccessControlValidationError) as ctx:
            set_permission_ceiling(
                actor=self.owner,
                organization_id=self.org.id,
                permission_key="roles.view",
                is_allowed=False,
            )
        self.assertEqual(ctx.exception.code, "VALIDATION_ERROR")

        # Coherent change: disable roles.manage
        ceiling = set_permission_ceiling(
            actor=self.owner,
            organization_id=self.org.id,
            permission_key="roles.manage",
            is_allowed=False,
        )
        self.assertFalse(ceiling.is_allowed)

        audit = AuditLog.objects.filter(action=AuditAction.PERMISSION_CEILING_CHANGED).first()
        self.assertIsNotNone(audit)
        self.assertEqual(audit.metadata["permission_key"], "roles.manage")
        self.assertFalse(audit.metadata["resulting_is_allowed"])

    def test_no_op_policy_and_ceiling_emit_zero_audit(self):
        audit_count = AuditLog.objects.count()

        # No-op policy (already enabled)
        set_console_module_policy(
            actor=self.owner,
            organization_id=self.org.id,
            module_key="tenant_roles",
            is_enabled=True,
        )
        # No-op ceiling (already allowed)
        set_permission_ceiling(
            actor=self.owner,
            organization_id=self.org.id,
            permission_key="roles.view",
            is_allowed=True,
        )
        self.assertEqual(AuditLog.objects.count(), audit_count)

    def test_organization_provisioning_creates_exact_defaults(self):
        new_org = Organization.objects.create(
            code="prov-test-org",
            name="Prov Test Org",
            status="active",
            created_by=self.owner,
            updated_by=self.owner,
        )
        provision_organization_defaults(organization=new_org, actor=self.owner)

        policies = dict(
            OrganizationConsoleModulePolicy.objects.filter(organization=new_org).values_list(
                "console_module_id", "is_enabled"
            )
        )
        self.assertTrue(policies.get("tenant_landing"))
        self.assertTrue(policies.get("tenant_roles"))
        self.assertTrue(policies.get("tenant_my_products"))

        ceilings = dict(
            OrganizationPermissionCeiling.objects.filter(organization=new_org).values_list(
                "permission_id", "is_allowed"
            )
        )
        self.assertTrue(ceilings.get("roles.view"))
        self.assertTrue(ceilings.get("roles.manage"))
        self.assertTrue(ceilings.get("roles.assign"))
        self.assertTrue(ceilings.get("products.view"))

    def test_organization_provisioning_is_idempotent(self):
        new_org = Organization.objects.create(
            code="prov-idempotent-org",
            name="Prov Idempotent Org",
            status="active",
            created_by=self.owner,
            updated_by=self.owner,
        )
        # Run provisioning twice
        provision_organization_defaults(organization=new_org, actor=self.owner)
        provision_organization_defaults(organization=new_org, actor=self.owner)

        module_count = OrganizationConsoleModulePolicy.objects.filter(organization=new_org).count()
        ceiling_count = OrganizationPermissionCeiling.objects.filter(organization=new_org).count()
        self.assertEqual(module_count, 3)
        self.assertEqual(ceiling_count, 4)

    def test_provisioned_organization_grants_tenant_admin_my_products_and_products_view(self):
        new_org = Organization.objects.create(
            code="prov-eff-org",
            name="Prov Effective Org",
            status="active",
            created_by=self.owner,
            updated_by=self.owner,
        )
        provision_organization_defaults(organization=new_org, actor=self.owner)

        from django.utils import timezone
        from apps.organizations.models import OrganizationMembership, MembershipType
        from apps.access_control.services.evaluation import evaluate_access
        OrganizationMembership.objects.create(
            organization=new_org,
            user=self.admin_user,
            membership_type=MembershipType.TENANT_ADMIN,
            role=self.sys_role,
            status="active",
            joined_at=timezone.now(),
        )

        res = evaluate_access(self.admin_user, "tenant", new_org.id)
        self.assertIn("tenant_my_products", res.allowed_modules)
        self.assertIn("products.view", res.effective_permissions)
