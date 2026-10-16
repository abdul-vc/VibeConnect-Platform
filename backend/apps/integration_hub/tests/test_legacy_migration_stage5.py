"""Phase 5D — Stage 5 Legacy LMS Migration & Reconciliation Tests.

Verifies the 16 authoritative test scenarios defined for legacy migration:
1. safe legacy tenant migration
2. safe legacy user migration
3. already mapped tenant
4. already mapped user
5. duplicate tenant conflict
6. duplicate user conflict
7. ambiguous tenant
8. ambiguous user
9. cross-tenant conflict
10. suspended/revoked legacy assignment
11. dry-run creates zero mutations
12. repeated migration is idempotent
13. failed migration leaves recoverable state
14. audit trail contains no secrets
15. tenant isolation
16. mapping integrity after migration
"""

import uuid
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.access_control.models import Role
from apps.assignments.models import AssignmentStatus, UserProductAssignment
from apps.entitlements.models import EntitlementStatus, OrganizationProductEntitlement
from apps.integration_hub.legacy_migration_service import (
    LegacyClassification,
    classify_legacy_tenant,
    classify_legacy_user,
    execute_legacy_lms_migration,
    plan_legacy_lms_migration,
)
from apps.integration_hub.lms_connector import LmsConnectorClient
from apps.integration_hub.models import (
    ConnectorInstance,
    ExternalTenantMapping,
    ExternalUserMapping,
    ExternalUserMappingStatus,
    InstanceStatus,
    IntegrationConnector,
    IntegrationReconciliationIssue,
    IntegrationReconciliationStatus,
)
from apps.integration_hub.reconciliation_service import LmsReconciliationIssueCode
from apps.organizations.models import (
    MembershipStatus,
    MembershipType,
    Organization,
    OrganizationMembership,
    OrganizationStatus,
)
from apps.product_registry.models import Product, ProductStatus

User = get_user_model()


class Stage5LegacyMigrationTests(TestCase):
    """Test suite for Phase 5D Stage 5 Legacy LMS Migration & Reconciliation."""

    def setUp(self):
        self.suffix = uuid.uuid4().hex[:8]

        # 1. Admin / Platform Owner
        self.admin = User.objects.create_user(
            email=f"admin_{self.suffix}@test.local",
            password="TestPassword123!",
            is_active=True,
        )
        if hasattr(self.admin, "is_platform_owner"):
            self.admin.is_platform_owner = True
            self.admin.save(update_fields=["is_platform_owner"])

        # 2. LMS Product & Connector
        self.product, _ = Product.objects.get_or_create(
            code="lms",
            defaults={
                "name": "Learning Management System",
                "status": ProductStatus.ACTIVE,
                "created_by": self.admin,
                "updated_by": self.admin,
            },
        )
        self.connector, _ = IntegrationConnector.objects.get_or_create(
            code="lms",
            defaults={
                "name": "LMS Connector",
                "product": self.product,
            },
        )

        # 3. Organization & Membership
        self.org = Organization.objects.create(
            name=f"Org {self.suffix}",
            code=f"org_{self.suffix}",
            status=OrganizationStatus.ACTIVE,
            created_by=self.admin,
            updated_by=self.admin,
        )
        self.tenant_admin_role, _ = Role.objects.get_or_create(
            code="system_tenant_admin",
            defaults={"name": "Tenant Administrator", "is_system_role": True},
        )
        self.admin_membership = OrganizationMembership.objects.create(
            organization=self.org,
            user=self.admin,
            membership_type=MembershipType.TENANT_ADMIN,
            role=self.tenant_admin_role,
            status=MembershipStatus.ACTIVE,
            joined_at=timezone.now(),
        )

        # 4. Connector Instance
        self.instance = ConnectorInstance.objects.create(
            connector=self.connector,
            organization=self.org,
            status=InstanceStatus.ACTIVE,
            credential_ref="vault:secret/stage5",
        )

        # 5. Standard Test User
        self.user = User.objects.create_user(
            email=f"learner_{self.suffix}@test.local",
            password="TestPassword123!",
            is_active=True,
        )
        self.user_membership = OrganizationMembership.objects.create(
            organization=self.org,
            user=self.user,
            membership_type=MembershipType.MEMBER,
            status=MembershipStatus.ACTIVE,
            joined_at=timezone.now(),
        )

        # 6. Mock LMS Client
        self.mock_client = mock.MagicMock(spec=LmsConnectorClient)
        self.mock_client.provision_tenant.return_value = {
            "lms_organization_id": f"lms_org_{self.suffix}",
            "name": self.org.name,
            "status": "Active",
            "action_taken": "created",
        }
        self.mock_client.provision_user.return_value = {
            "lms_user_id": f"lms_usr_{self.suffix}",
            "email": self.user.email,
            "is_active": True,
            "action_taken": "created",
        }

    def _create_entitlement(self, status=EntitlementStatus.ACTIVE, org=None):
        target_org = org or self.org
        return OrganizationProductEntitlement.objects.create(
            organization=target_org,
            product=self.product,
            status=status,
            created_by=self.admin,
            updated_by=self.admin,
        )

    def _create_assignment(self, user=None, org=None, status=AssignmentStatus.ACTIVE):
        target_user = user or self.user
        target_org = org or self.org
        m = OrganizationMembership.objects.filter(organization=target_org, user=target_user).first()
        now = timezone.now()
        revoked_at = now if status == AssignmentStatus.REVOKED else None
        last_suspended_at = now if status == AssignmentStatus.SUSPENDED else None
        return UserProductAssignment.objects.create(
            organization=target_org,
            user=target_user,
            membership=m,
            product=self.product,
            status=status,
            created_by=self.admin,
            updated_by=self.admin,
            revoked_at=revoked_at,
            last_suspended_at=last_suspended_at,
        )

    # -------------------------------------------------------------------------
    # 1. safe legacy tenant migration
    # -------------------------------------------------------------------------
    def test_01_safe_legacy_tenant_migration(self):
        """Active entitled organization without mapping classifies SAFE_TO_MIGRATE and migrates."""
        self._create_entitlement(EntitlementStatus.ACTIVE)

        # Check classification
        rec = classify_legacy_tenant(self.org, self.instance)
        self.assertEqual(rec["classification"], LegacyClassification.SAFE_TO_MIGRATE)
        self.assertTrue(rec["will_mutate"])

        # Execute migration
        plan = plan_legacy_lms_migration(organization=self.org, instance=self.instance)
        result = execute_legacy_lms_migration(
            plan=plan,
            organization=self.org,
            instance=self.instance,
            client=self.mock_client,
        )

        self.assertEqual(result["migrated_count"], 1)
        self.assertEqual(result["failed_count"], 0)
        mapping = ExternalTenantMapping.objects.get(organization=self.org)
        self.assertEqual(mapping.external_tenant_id, f"lms_org_{self.suffix}")

    # -------------------------------------------------------------------------
    # 2. safe legacy user migration
    # -------------------------------------------------------------------------
    def test_02_safe_legacy_user_migration(self):
        """Active assigned user in mapped tenant classifies SAFE_TO_MIGRATE and migrates."""
        self._create_entitlement(EntitlementStatus.ACTIVE)
        ExternalTenantMapping.objects.create(
            organization=self.org,
            instance=self.instance,
            external_tenant_id=f"lms_org_{self.suffix}",
        )
        self._create_assignment(status=AssignmentStatus.ACTIVE)

        rec = classify_legacy_user(self.user, self.org, self.instance)
        self.assertEqual(rec["classification"], LegacyClassification.SAFE_TO_MIGRATE)
        self.assertTrue(rec["will_mutate"])

        plan = plan_legacy_lms_migration(organization=self.org, instance=self.instance)
        result = execute_legacy_lms_migration(
            plan=plan,
            organization=self.org,
            instance=self.instance,
            client=self.mock_client,
        )

        self.assertEqual(result["migrated_count"], 1)
        user_mapping = ExternalUserMapping.objects.get(organization=self.org, user=self.user)
        self.assertEqual(user_mapping.external_user_id, f"lms_usr_{self.suffix}")
        self.assertEqual(user_mapping.status, ExternalUserMappingStatus.ACTIVE)

    # -------------------------------------------------------------------------
    # 3. already mapped tenant
    # -------------------------------------------------------------------------
    def test_03_already_mapped_tenant(self):
        """Organization with existing ExternalTenantMapping classifies ALREADY_MAPPED with 0 mutations."""
        self._create_entitlement(EntitlementStatus.ACTIVE)
        ExternalTenantMapping.objects.create(
            organization=self.org,
            instance=self.instance,
            external_tenant_id=f"lms_org_{self.suffix}",
        )

        rec = classify_legacy_tenant(self.org, self.instance)
        self.assertEqual(rec["classification"], LegacyClassification.ALREADY_MAPPED)
        self.assertFalse(rec["will_mutate"])
        self.assertFalse(rec["requires_manual_review"])

        plan = plan_legacy_lms_migration(organization=self.org, instance=self.instance)
        result = execute_legacy_lms_migration(
            plan=plan,
            organization=self.org,
            instance=self.instance,
            client=self.mock_client,
        )
        self.assertEqual(result["migrated_count"], 0)
        self.mock_client.provision_tenant.assert_not_called()

    # -------------------------------------------------------------------------
    # 4. already mapped user
    # -------------------------------------------------------------------------
    def test_04_already_mapped_user(self):
        """User with existing active ExternalUserMapping classifies ALREADY_MAPPED with 0 mutations."""
        self._create_entitlement(EntitlementStatus.ACTIVE)
        ExternalTenantMapping.objects.create(
            organization=self.org,
            instance=self.instance,
            external_tenant_id=f"lms_org_{self.suffix}",
        )
        self._create_assignment(status=AssignmentStatus.ACTIVE)
        ExternalUserMapping.objects.create(
            organization=self.org,
            instance=self.instance,
            user=self.user,
            external_user_id=f"lms_usr_{self.suffix}",
            status=ExternalUserMappingStatus.ACTIVE,
        )

        rec = classify_legacy_user(self.user, self.org, self.instance)
        self.assertEqual(rec["classification"], LegacyClassification.ALREADY_MAPPED)
        self.assertFalse(rec["will_mutate"])

        plan = plan_legacy_lms_migration(organization=self.org, instance=self.instance)
        result = execute_legacy_lms_migration(
            plan=plan,
            organization=self.org,
            instance=self.instance,
            client=self.mock_client,
        )
        self.assertEqual(result["migrated_count"], 0)
        self.mock_client.provision_user.assert_not_called()

    # -------------------------------------------------------------------------
    # 5. duplicate tenant conflict
    # -------------------------------------------------------------------------
    def test_05_duplicate_tenant_conflict(self):
        """Collision on external_tenant_id across organizations triggers CONFLICT_REVIEW."""
        self._create_entitlement(EntitlementStatus.ACTIVE)
        org2 = Organization.objects.create(
            name=f"Org 2 {self.suffix}",
            code=f"org2_{self.suffix}",
            status=OrganizationStatus.ACTIVE,
            created_by=self.admin,
            updated_by=self.admin,
        )
        shared_ext_id = f"shared_lms_org_{self.suffix}"
        ExternalTenantMapping.objects.create(
            organization=self.org,
            instance=self.instance,
            external_tenant_id=shared_ext_id,
        )
        inst2 = ConnectorInstance.objects.create(
            connector=self.connector,
            organization=org2,
            status=InstanceStatus.ACTIVE,
        )
        ExternalTenantMapping.objects.create(
            organization=org2,
            instance=inst2,
            external_tenant_id=shared_ext_id,
        )

        rec = classify_legacy_tenant(self.org, self.instance)
        self.assertEqual(rec["classification"], LegacyClassification.CONFLICT_REVIEW)
        self.assertTrue(rec["requires_manual_review"])
        self.assertFalse(rec["will_mutate"])

    # -------------------------------------------------------------------------
    # 6. duplicate user conflict
    # -------------------------------------------------------------------------
    def test_06_duplicate_user_conflict(self):
        """Duplicate external_user_id within same connector instance triggers CONFLICT_REVIEW."""
        self._create_entitlement(EntitlementStatus.ACTIVE)
        ExternalTenantMapping.objects.create(
            organization=self.org,
            instance=self.instance,
            external_tenant_id=f"lms_org_{self.suffix}",
        )
        org2 = Organization.objects.create(
            name=f"Org 2 {self.suffix}",
            code=f"org2_{self.suffix}",
            status=OrganizationStatus.ACTIVE,
            created_by=self.admin,
            updated_by=self.admin,
        )
        inst2 = ConnectorInstance.objects.create(
            connector=self.connector,
            organization=org2,
            status=InstanceStatus.ACTIVE,
        )
        u2 = User.objects.create_user(
            email=f"other_{self.suffix}@test.local",
            password="TestPassword123!",
            is_active=True,
        )
        OrganizationMembership.objects.create(
            organization=org2,
            user=u2,
            membership_type=MembershipType.MEMBER,
            status=MembershipStatus.ACTIVE,
            joined_at=timezone.now(),
        )
        shared_ext_id = f"shared_usr_{self.suffix}"
        ExternalUserMapping.objects.create(
            organization=self.org,
            instance=self.instance,
            user=self.user,
            external_user_id=shared_ext_id,
            status=ExternalUserMappingStatus.ACTIVE,
        )
        ExternalUserMapping.objects.create(
            organization=org2,
            instance=inst2,
            user=u2,
            external_user_id=shared_ext_id,
            status=ExternalUserMappingStatus.ACTIVE,
        )

        rec = classify_legacy_user(self.user, self.org, self.instance)
        self.assertEqual(rec["classification"], LegacyClassification.CONFLICT_REVIEW)
        self.assertTrue(rec["requires_manual_review"])
        self.assertFalse(rec["will_mutate"])

    # -------------------------------------------------------------------------
    # 7. ambiguous tenant
    # -------------------------------------------------------------------------
    def test_07_ambiguous_tenant(self):
        """Organization with blank or duplicate code triggers AMBIGUOUS_REVIEW."""
        self._create_entitlement(EntitlementStatus.ACTIVE)
        self.org.code = ""

        rec = classify_legacy_tenant(self.org, self.instance)
        self.assertEqual(rec["classification"], LegacyClassification.AMBIGUOUS_REVIEW)
        self.assertTrue(rec["requires_manual_review"])
        self.assertFalse(rec["will_mutate"])

    # -------------------------------------------------------------------------
    # 8. ambiguous user
    # -------------------------------------------------------------------------
    def test_08_ambiguous_user(self):
        """User with missing or malformed email triggers AMBIGUOUS_REVIEW."""
        self._create_entitlement(EntitlementStatus.ACTIVE)
        ExternalTenantMapping.objects.create(
            organization=self.org,
            instance=self.instance,
            external_tenant_id=f"lms_org_{self.suffix}",
        )
        self._create_assignment(status=AssignmentStatus.ACTIVE)
        self.user.email = "invalid-email"
        self.user.save(update_fields=["email"])

        rec = classify_legacy_user(self.user, self.org, self.instance)
        self.assertEqual(rec["classification"], LegacyClassification.AMBIGUOUS_REVIEW)
        self.assertTrue(rec["requires_manual_review"])
        self.assertFalse(rec["will_mutate"])

    # -------------------------------------------------------------------------
    # 9. cross-tenant conflict
    # -------------------------------------------------------------------------
    def test_09_cross_tenant_conflict(self):
        """User having no membership in target organization triggers CONFLICT_REVIEW."""
        self._create_entitlement(EntitlementStatus.ACTIVE)
        ExternalTenantMapping.objects.create(
            organization=self.org,
            instance=self.instance,
            external_tenant_id=f"lms_org_{self.suffix}",
        )
        foreign_user = User.objects.create_user(
            email=f"foreign_{self.suffix}@test.local",
            password="TestPassword123!",
            is_active=True,
        )

        rec = classify_legacy_user(foreign_user, self.org, self.instance)
        self.assertEqual(rec["classification"], LegacyClassification.CONFLICT_REVIEW)
        self.assertTrue(rec["requires_manual_review"])
        self.assertFalse(rec["will_mutate"])

    # -------------------------------------------------------------------------
    # 10. suspended/revoked legacy assignment
    # -------------------------------------------------------------------------
    def test_10_suspended_revoked_legacy_assignment(self):
        """Suspended or revoked assignment classifies INACTIVE_NO_ACTION and does NOT mutate."""
        self._create_entitlement(EntitlementStatus.ACTIVE)
        ExternalTenantMapping.objects.create(
            organization=self.org,
            instance=self.instance,
            external_tenant_id=f"lms_org_{self.suffix}",
        )
        self._create_assignment(status=AssignmentStatus.REVOKED)

        rec = classify_legacy_user(self.user, self.org, self.instance)
        self.assertEqual(rec["classification"], LegacyClassification.INACTIVE_NO_ACTION)
        self.assertFalse(rec["will_mutate"])
        self.assertFalse(rec["requires_manual_review"])

        plan = plan_legacy_lms_migration(organization=self.org, instance=self.instance)
        result = execute_legacy_lms_migration(
            plan=plan,
            organization=self.org,
            instance=self.instance,
            client=self.mock_client,
        )
        self.assertEqual(result["migrated_count"], 0)
        self.assertFalse(ExternalUserMapping.objects.filter(user=self.user).exists())

    # -------------------------------------------------------------------------
    # 11. dry-run creates zero mutations
    # -------------------------------------------------------------------------
    def test_11_dry_run_creates_zero_mutations(self):
        """Dry-run plan generation audits all entities with zero DB mutations."""
        self._create_entitlement(EntitlementStatus.ACTIVE)
        self._create_assignment(status=AssignmentStatus.ACTIVE)

        plan = plan_legacy_lms_migration(organization=self.org, instance=self.instance)
        self.assertTrue(plan["dry_run"])
        self.assertGreaterEqual(plan["counts"]["total"], 1)

        # Zero mappings should have been created
        self.assertEqual(ExternalTenantMapping.objects.filter(organization=self.org).count(), 0)
        self.assertEqual(ExternalUserMapping.objects.filter(organization=self.org).count(), 0)

    # -------------------------------------------------------------------------
    # 12. repeated migration is idempotent
    # -------------------------------------------------------------------------
    def test_12_repeated_migration_is_idempotent(self):
        """Executing migration twice results in second run migrating 0 items."""
        self._create_entitlement(EntitlementStatus.ACTIVE)

        # First run
        result1 = execute_legacy_lms_migration(
            organization=self.org,
            instance=self.instance,
            client=self.mock_client,
        )
        self.assertEqual(result1["migrated_count"], 1)

        # Second run
        result2 = execute_legacy_lms_migration(
            organization=self.org,
            instance=self.instance,
            client=self.mock_client,
        )
        self.assertEqual(result2["migrated_count"], 0)
        self.assertEqual(result2["failed_count"], 0)

    # -------------------------------------------------------------------------
    # 13. failed migration leaves recoverable state
    # -------------------------------------------------------------------------
    def test_13_failed_migration_leaves_recoverable_state(self):
        """When client fails, audit records FAILED without crashing the process."""
        self._create_entitlement(EntitlementStatus.ACTIVE)
        self.mock_client.provision_tenant.side_effect = RuntimeError("LMS Connection Timeout")

        result = execute_legacy_lms_migration(
            organization=self.org,
            instance=self.instance,
            client=self.mock_client,
        )
        self.assertEqual(result["migrated_count"], 0)
        self.assertEqual(result["failed_count"], 1)
        self.assertEqual(result["audit_trail"][0]["result"], "FAILED")
        self.assertIn("LMS Connection Timeout", result["audit_trail"][0]["error"])

    # -------------------------------------------------------------------------
    # 14. audit trail contains no secrets
    # -------------------------------------------------------------------------
    def test_14_audit_trail_contains_no_secrets(self):
        """Audit trail records must not contain passwords, tokens, or credential references."""
        self._create_entitlement(EntitlementStatus.ACTIVE)

        result = execute_legacy_lms_migration(
            organization=self.org,
            instance=self.instance,
            client=self.mock_client,
        )
        for entry in result["audit_trail"]:
            entry_str = str(entry).lower()
            self.assertNotIn("password", entry_str)
            self.assertNotIn("vault:secret", entry_str)
            self.assertNotIn("access_token", entry_str)
            self.assertNotIn("bearer", entry_str)

    # -------------------------------------------------------------------------
    # 15. tenant isolation
    # -------------------------------------------------------------------------
    def test_15_tenant_isolation(self):
        """User from Org A cannot be migrated into Org B even if assigned there erroneously."""
        org_b = Organization.objects.create(
            name=f"Org B {self.suffix}",
            code=f"org_b_{self.suffix}",
            status=OrganizationStatus.ACTIVE,
            created_by=self.admin,
            updated_by=self.admin,
        )
        inst_b = ConnectorInstance.objects.create(
            connector=self.connector,
            organization=org_b,
            status=InstanceStatus.ACTIVE,
        )
        ExternalTenantMapping.objects.create(
            organization=org_b,
            instance=inst_b,
            external_tenant_id=f"lms_org_b_{self.suffix}",
        )
        self._create_entitlement(org=org_b)

        # self.user belongs to self.org, NOT org_b
        rec = classify_legacy_user(self.user, org_b, inst_b)
        self.assertEqual(rec["classification"], LegacyClassification.CONFLICT_REVIEW)
        self.assertTrue(rec["requires_manual_review"])
        self.assertFalse(rec["will_mutate"])

    # -------------------------------------------------------------------------
    # 16. mapping integrity after migration
    # -------------------------------------------------------------------------
    def test_16_mapping_integrity_after_migration(self):
        """External mappings accurately match LMS returned IDs and auto-resolve reconciliation issues."""
        self._create_entitlement(EntitlementStatus.ACTIVE)

        # Seed an OPEN MISSING_TENANT_MAPPING reconciliation issue
        issue = IntegrationReconciliationIssue.objects.create(
            instance=self.instance,
            issue_code=LmsReconciliationIssueCode.MISSING_TENANT_MAPPING,
            subject_id=str(self.org.id),
            subject_type="organization",
            status=IntegrationReconciliationStatus.OPEN,
        )

        result = execute_legacy_lms_migration(
            organization=self.org,
            instance=self.instance,
            client=self.mock_client,
        )
        self.assertEqual(result["migrated_count"], 1)

        # Verify mapping matches LMS returned ID
        mapping = ExternalTenantMapping.objects.get(organization=self.org)
        self.assertEqual(mapping.external_tenant_id, f"lms_org_{self.suffix}")

        # Verify issue is resolved
        issue.refresh_from_db()
        self.assertEqual(issue.status, IntegrationReconciliationStatus.RESOLVED)
        self.assertIn("Auto-resolved by legacy migration", issue.resolution_notes)
