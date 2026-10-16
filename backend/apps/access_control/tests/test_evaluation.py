"""Focused Stage 3 Tests for Centralized Permission Evaluation Engine and Authorization.

Covers:
- Evaluation engine invariants (Tenant Admin vs Platform Owner vs Member).
- Module policy and permission ceiling layering.
- Inactive permission, module, user, org, and membership states.
- Foreign and inactive role safety.
- Request-level memoization boundaries and cross-tenant cache isolation.
- HasConsolePermission and HasConsoleModule authorization classes.
"""

from unittest.mock import Mock
import uuid

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied
from rest_framework.test import APIRequestFactory

from apps.access_control.constants import (
    CONTEXT_PLATFORM_OWNER,
    CONTEXT_TENANT,
    PLATFORM_OWNER_MODULE_KEYS,
)
from apps.access_control.models import (
    AccessPermission,
    ConsoleModule,
    ConsoleModuleContext,
    OrganizationConsoleModulePolicy,
    OrganizationPermissionCeiling,
    Role,
    RolePermission,
    RoleStatus,
)
from apps.access_control.permissions import HasConsoleModule, HasConsolePermission
from apps.access_control.services.evaluation import (
    evaluate_access,
    get_request_evaluation,
)
from apps.organizations.models import (
    MembershipStatus,
    MembershipType,
    Organization,
    OrganizationMembership,
    OrganizationStatus,
)

PlatformUser = get_user_model()


class Stage3EvaluationEngineTests(TestCase):
    """Verifies centralized permission evaluation, DRF authorization, and request memoization."""

    def setUp(self):
        super().setUp()
        self.factory = APIRequestFactory()

        # 1. Platform Owner
        self.owner = PlatformUser.objects.create_user(
            email="eval_owner@vibeconnect.internal",
            password="SecurePassword123!",
            full_name="Platform Owner",
            status="active",
            is_active=True,
            is_platform_owner=True,
        )

        # 2. Organizations
        self.org_alpha = Organization.objects.create(
            code="eval-org-alpha",
            name="Evaluation Org Alpha",
            status=OrganizationStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )
        self.org_beta = Organization.objects.create(
            code="eval-org-beta",
            name="Evaluation Org Beta",
            status=OrganizationStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )

        # 3. Ensure Console Modules exist
        self.mod_landing, _ = ConsoleModule.objects.get_or_create(
            key="tenant_landing",
            defaults={
                "display_name": "Tenant Console",
                "target_context": ConsoleModuleContext.TENANT,
                "is_core": True,
                "is_active": True,
                "sort_order": 10,
            },
        )
        self.mod_roles, _ = ConsoleModule.objects.get_or_create(
            key="tenant_roles",
            defaults={
                "display_name": "Roles & Permissions",
                "target_context": ConsoleModuleContext.TENANT,
                "is_core": False,
                "is_active": True,
                "sort_order": 20,
            },
        )

        # Ensure PO modules exist
        for idx, key in enumerate(PLATFORM_OWNER_MODULE_KEYS):
            ConsoleModule.objects.get_or_create(
                key=key,
                defaults={
                    "display_name": key.replace("_", " ").title(),
                    "target_context": ConsoleModuleContext.PLATFORM_OWNER,
                    "is_core": True,
                    "is_active": True,
                    "sort_order": (idx + 1) * 10,
                },
            )

        # 4. Ensure Permissions exist
        self.perm_view, _ = AccessPermission.objects.get_or_create(
            key="roles.view",
            defaults={
                "console_module": self.mod_roles,
                "display_name": "View Roles",
                "category": "roles",
                "is_active": True,
                "sort_order": 10,
            },
        )
        self.perm_manage, _ = AccessPermission.objects.get_or_create(
            key="roles.manage",
            defaults={
                "console_module": self.mod_roles,
                "display_name": "Manage Roles",
                "category": "roles",
                "is_active": True,
                "sort_order": 20,
            },
        )
        self.perm_assign, _ = AccessPermission.objects.get_or_create(
            key="roles.assign",
            defaults={
                "console_module": self.mod_roles,
                "display_name": "Assign Roles",
                "category": "roles",
                "is_active": True,
                "sort_order": 30,
            },
        )

        # 5. System Role
        self.system_role, _ = Role.objects.get_or_create(
            code="system_tenant_admin",
            defaults={
                "name": "System Tenant Administrator",
                "is_system_role": True,
                "status": RoleStatus.ACTIVE,
                "organization": None,
            },
        )
        for perm in [self.perm_view, self.perm_manage, self.perm_assign]:
            RolePermission.objects.get_or_create(role=self.system_role, permission=perm)

        # 6. Policies & Ceilings for org_alpha
        OrganizationConsoleModulePolicy.objects.get_or_create(
            organization=self.org_alpha,
            console_module=self.mod_roles,
            defaults={"is_enabled": True},
        )
        for perm in [self.perm_view, self.perm_manage, self.perm_assign]:
            OrganizationPermissionCeiling.objects.get_or_create(
                organization=self.org_alpha,
                permission=perm,
                defaults={"is_allowed": True},
            )

        # 7. Tenant Admin User & Membership
        self.admin_user = PlatformUser.objects.create_user(
            email="eval_admin@vibeconnect.internal",
            password="SecurePassword123!",
            full_name="Tenant Administrator",
            status="active",
            is_active=True,
            is_platform_owner=False,
        )
        self.admin_membership = OrganizationMembership.objects.create(
            organization=self.org_alpha,
            user=self.admin_user,
            membership_type=MembershipType.TENANT_ADMIN,
            status=MembershipStatus.ACTIVE,
            role=self.system_role,
            joined_at=timezone.now(),
        )

    # 1. Full active system_tenant_admin receives expected permissions and modules
    def test_system_tenant_admin_full_permissions_and_modules(self):
        result = evaluate_access(self.admin_user, CONTEXT_TENANT, self.org_alpha.id)
        self.assertEqual(
            result.effective_permissions,
            ["roles.assign", "roles.manage", "roles.view"],
        )
        self.assertEqual(
            result.allowed_modules,
            ["tenant_landing", "tenant_roles"],
        )

    # 2. Restricted custom role receives only its effective assigned permission subset
    def test_restricted_custom_role_receives_assigned_subset(self):
        custom_role = Role.objects.create(
            organization=self.org_alpha,
            code="restricted_viewer",
            name="Restricted Viewer",
            is_system_role=False,
            status=RoleStatus.ACTIVE,
        )
        RolePermission.objects.create(role=custom_role, permission=self.perm_view)

        self.admin_membership.role = custom_role
        self.admin_membership.save(update_fields=["role"])

        result = evaluate_access(self.admin_user, CONTEXT_TENANT, self.org_alpha.id)
        self.assertEqual(result.effective_permissions, ["roles.view"])
        self.assertEqual(result.allowed_modules, ["tenant_landing", "tenant_roles"])

    # 3. Missing permission-ceiling row denies that permission
    def test_missing_permission_ceiling_row_denies_permission(self):
        OrganizationPermissionCeiling.objects.filter(
            organization=self.org_alpha,
            permission=self.perm_assign,
        ).delete()

        result = evaluate_access(self.admin_user, CONTEXT_TENANT, self.org_alpha.id)
        self.assertNotIn("roles.assign", result.effective_permissions)
        self.assertEqual(result.effective_permissions, ["roles.manage", "roles.view"])

    # 4. Ceiling set to denied removes that permission
    def test_ceiling_denied_removes_permission(self):
        OrganizationPermissionCeiling.objects.filter(
            organization=self.org_alpha,
            permission=self.perm_manage,
        ).update(is_allowed=False)

        result = evaluate_access(self.admin_user, CONTEXT_TENANT, self.org_alpha.id)
        self.assertNotIn("roles.manage", result.effective_permissions)
        self.assertIn("roles.view", result.effective_permissions)
        self.assertIn("roles.assign", result.effective_permissions)

    # 5. Missing optional module-policy row disables tenant_roles
    def test_missing_module_policy_disables_optional_module(self):
        OrganizationConsoleModulePolicy.objects.filter(
            organization=self.org_alpha,
            console_module=self.mod_roles,
        ).delete()

        result = evaluate_access(self.admin_user, CONTEXT_TENANT, self.org_alpha.id)
        self.assertNotIn("tenant_roles", result.allowed_modules)
        self.assertEqual(result.allowed_modules, ["tenant_landing"])

    # 6. Disabled tenant_roles removes the module and its linked permissions
    def test_disabled_module_removes_module_and_linked_permissions(self):
        OrganizationConsoleModulePolicy.objects.filter(
            organization=self.org_alpha,
            console_module=self.mod_roles,
        ).update(is_enabled=False)

        result = evaluate_access(self.admin_user, CONTEXT_TENANT, self.org_alpha.id)
        self.assertNotIn("tenant_roles", result.allowed_modules)
        self.assertEqual(result.allowed_modules, ["tenant_landing"])
        self.assertEqual(result.effective_permissions, [])

    # 7. Inactive permission is denied
    def test_inactive_permission_is_denied(self):
        self.perm_view.is_active = False
        self.perm_view.save(update_fields=["is_active"])

        result = evaluate_access(self.admin_user, CONTEXT_TENANT, self.org_alpha.id)
        self.assertNotIn("roles.view", result.effective_permissions)

    # 8. Inactive console module is denied
    def test_inactive_console_module_is_denied(self):
        self.mod_roles.is_active = False
        self.mod_roles.save(update_fields=["is_active"])

        result = evaluate_access(self.admin_user, CONTEXT_TENANT, self.org_alpha.id)
        self.assertNotIn("tenant_roles", result.allowed_modules)
        self.assertEqual(result.effective_permissions, [])

    # 9. Regular member receives no Tenant Admin console access
    def test_regular_member_receives_no_console_access(self):
        member_user = PlatformUser.objects.create_user(
            email="eval_member@vibeconnect.internal",
            password="SecurePassword123!",
            full_name="Regular Member",
            status="active",
            is_active=True,
            is_platform_owner=False,
        )
        OrganizationMembership.objects.create(
            organization=self.org_alpha,
            user=member_user,
            membership_type=MembershipType.MEMBER,
            status=MembershipStatus.ACTIVE,
            role=None,
            joined_at=timezone.now(),
        )

        result = evaluate_access(member_user, CONTEXT_TENANT, self.org_alpha.id)
        self.assertEqual(result.effective_permissions, [])
        self.assertEqual(result.allowed_modules, [])

    # 10. Suspended or ended membership is denied
    def test_suspended_or_ended_membership_is_denied(self):
        self.admin_membership.status = MembershipStatus.SUSPENDED
        self.admin_membership.save(update_fields=["status"])

        res_suspended = evaluate_access(self.admin_user, CONTEXT_TENANT, self.org_alpha.id)
        self.assertEqual(res_suspended.effective_permissions, [])
        self.assertEqual(res_suspended.allowed_modules, [])

        self.admin_membership.status = MembershipStatus.ENDED
        self.admin_membership.ended_at = timezone.now()
        self.admin_membership.save(update_fields=["status", "ended_at"])

        res_ended = evaluate_access(self.admin_user, CONTEXT_TENANT, self.org_alpha.id)
        self.assertEqual(res_ended.effective_permissions, [])
        self.assertEqual(res_ended.allowed_modules, [])

    # 11. Inactive user is denied
    def test_inactive_user_is_denied(self):
        self.admin_user.status = "suspended"
        self.admin_user.save(update_fields=["status"])

        res_status = evaluate_access(self.admin_user, CONTEXT_TENANT, self.org_alpha.id)
        self.assertEqual(res_status.effective_permissions, [])
        self.assertEqual(res_status.allowed_modules, [])

        self.admin_user.status = "disabled"
        self.admin_user.save(update_fields=["status"])

        res_disabled = evaluate_access(self.admin_user, CONTEXT_TENANT, self.org_alpha.id)
        self.assertEqual(res_disabled.effective_permissions, [])
        self.assertEqual(res_disabled.allowed_modules, [])

        mock_user = Mock(is_authenticated=True, is_active=False, status="active")
        res_mock = evaluate_access(mock_user, CONTEXT_TENANT, self.org_alpha.id)
        self.assertEqual(res_mock.effective_permissions, [])
        self.assertEqual(res_mock.allowed_modules, [])

    # 12. Inactive organization is denied
    def test_inactive_organization_is_denied(self):
        self.org_alpha.status = OrganizationStatus.SUSPENDED
        self.org_alpha.save(update_fields=["status"])

        result = evaluate_access(self.admin_user, CONTEXT_TENANT, self.org_alpha.id)
        self.assertEqual(result.effective_permissions, [])
        self.assertEqual(result.allowed_modules, [])

    # 13. Missing, null, inactive, or foreign role is denied safely
    def test_inactive_or_foreign_role_denied_safely(self):
        # Inactive role
        retired_role = Role.objects.create(
            organization=self.org_alpha,
            code="retired_role",
            name="Retired Role",
            status=RoleStatus.RETIRED,
        )
        self.admin_membership.role = retired_role
        self.admin_membership.save(update_fields=["role"])

        res_retired = evaluate_access(self.admin_user, CONTEXT_TENANT, self.org_alpha.id)
        self.assertEqual(res_retired.effective_permissions, [])
        self.assertEqual(res_retired.allowed_modules, [])

        # Foreign role (role belongs to org_beta but assigned to org_alpha membership)
        foreign_role = Role.objects.create(
            organization=self.org_beta,
            code="beta_role",
            name="Beta Role",
            status=RoleStatus.ACTIVE,
        )
        self.admin_membership.role = foreign_role
        self.admin_membership.save(update_fields=["role"])

        res_foreign = evaluate_access(self.admin_user, CONTEXT_TENANT, self.org_alpha.id)
        self.assertEqual(res_foreign.effective_permissions, [])
        self.assertEqual(res_foreign.allowed_modules, [])

    # 14. Unknown permission/module keys are denied
    def test_unknown_permission_and_module_keys_denied(self):
        result = evaluate_access(self.admin_user, CONTEXT_TENANT, self.org_alpha.id)
        self.assertFalse(result.has_permission("nonexistent.permission"))
        self.assertFalse(result.has_module("nonexistent_module"))

    # 15. Platform Owner context returns empty effective permissions and only po_* modules
    def test_platform_owner_context_returns_po_modules_and_no_wildcards(self):
        result = evaluate_access(self.owner, CONTEXT_PLATFORM_OWNER, None)
        self.assertEqual(result.effective_permissions, [])
        self.assertNotIn("*", result.effective_permissions)
        self.assertNotIn("roles.view", result.effective_permissions)
        self.assertEqual(
            result.allowed_modules,
            list(PLATFORM_OWNER_MODULE_KEYS),
        )

    # 16. HasConsolePermission allows present effective permission and denies absent
    def test_has_console_permission_class(self):
        perm_checker = HasConsolePermission()

        class ViewRoles:
            required_console_permission = "roles.view"

        class ViewDelete:
            required_console_permission = "roles.delete"

        request = self.factory.get("/dummy/")
        request.user = self.admin_user
        request.session = {
            "active_context_type": CONTEXT_TENANT,
            "tenant_organization_id": str(self.org_alpha.id),
        }

        # roles.view is allowed
        self.assertTrue(perm_checker.has_permission(request, ViewRoles()))

        # roles.delete is denied with INSUFFICIENT_PRIVILEGES
        with self.assertRaises(PermissionDenied) as ctx:
            perm_checker.has_permission(request, ViewDelete())
        self.assertEqual(ctx.exception.detail.get("code"), "INSUFFICIENT_PRIVILEGES")

    # 17. HasConsoleModule allows enabled module and denies disabled
    def test_has_console_module_class(self):
        module_checker = HasConsoleModule()

        class ViewRolesMod:
            required_console_module = "tenant_roles"

        class ViewUnknownMod:
            required_console_module = "unknown_module"

        request = self.factory.get("/dummy/")
        request.user = self.admin_user
        request.session = {
            "active_context_type": CONTEXT_TENANT,
            "tenant_organization_id": str(self.org_alpha.id),
        }

        # tenant_roles is enabled
        self.assertTrue(module_checker.has_permission(request, ViewRolesMod()))

        # unknown_module is denied with MODULE_DISABLED
        with self.assertRaises(PermissionDenied) as ctx:
            module_checker.has_permission(request, ViewUnknownMod())
        self.assertEqual(ctx.exception.detail.get("code"), "MODULE_DISABLED")

        # Disable tenant_roles
        OrganizationConsoleModulePolicy.objects.filter(
            organization=self.org_alpha,
            console_module=self.mod_roles,
        ).update(is_enabled=False)

        # Clear request memoization to test new evaluation
        request_new = self.factory.get("/dummy/")
        request_new.user = self.admin_user
        request_new.session = {
            "active_context_type": CONTEXT_TENANT,
            "tenant_organization_id": str(self.org_alpha.id),
        }

        with self.assertRaises(PermissionDenied) as ctx:
            module_checker.has_permission(request_new, ViewRolesMod())
        self.assertEqual(ctx.exception.detail.get("code"), "MODULE_DISABLED")

    # 18. Request-level memoization reuses evaluation within one request but not across separate requests
    def test_request_level_memoization_lifecycle(self):
        req1 = self.factory.get("/dummy/")
        req1.user = self.admin_user

        res1 = get_request_evaluation(req1, self.admin_user, CONTEXT_TENANT, self.org_alpha.id)
        self.assertIn("roles.assign", res1.effective_permissions)

        # Modify database state behind the scenes
        OrganizationPermissionCeiling.objects.filter(
            organization=self.org_alpha,
            permission=self.perm_assign,
        ).update(is_allowed=False)

        # Calling again with req1 should reuse cached evaluation
        res2 = get_request_evaluation(req1, self.admin_user, CONTEXT_TENANT, self.org_alpha.id)
        self.assertIn("roles.assign", res2.effective_permissions)
        self.assertIs(res1, res2)

        # Calling with a fresh request must evaluate fresh database state
        req2 = self.factory.get("/dummy/")
        req2.user = self.admin_user

        res3 = get_request_evaluation(req2, self.admin_user, CONTEXT_TENANT, self.org_alpha.id)
        self.assertNotIn("roles.assign", res3.effective_permissions)

    # 19. Cross-organization context cannot reuse another organization's cached evaluation
    def test_cross_organization_context_cannot_reuse_cache(self):
        req = self.factory.get("/dummy/")
        req.user = self.admin_user

        res_alpha = get_request_evaluation(req, self.admin_user, CONTEXT_TENANT, self.org_alpha.id)
        self.assertEqual(res_alpha.organization_id, str(self.org_alpha.id))
        self.assertIn("roles.view", res_alpha.effective_permissions)

        # User is not a member of org_beta
        res_beta = get_request_evaluation(req, self.admin_user, CONTEXT_TENANT, self.org_beta.id)
        self.assertEqual(res_beta.organization_id, str(self.org_beta.id))
        self.assertEqual(res_beta.effective_permissions, [])
        self.assertEqual(res_beta.allowed_modules, [])
