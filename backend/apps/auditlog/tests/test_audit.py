"""Audit Log Comprehensive Test Suite.

Verifies:
1. Immutability guards on instance, QuerySet, and Manager.
2. Metadata allowlist validation for all 11 action schemas.
3. Secret-exclusion enforcement.
4. Action/target/source compatibility and database constraints.
5. First-class organization_id context validation and constraints.
6. Mutation hooks and transactional rollback consistency across domain apps.
7. Authentication session audit and failure isolation (login/logout).
8. Read-only API endpoint authorization, method restrictions, filtering, ordering, pagination, and constant query counts.
9. Migration zero-backfill and state restoration.
"""

from datetime import timedelta
import importlib
from unittest.mock import patch
import uuid

from django.apps import apps
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import IntegrityError, connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.auditlog.models import (
    AuditAction,
    AuditLog,
    AuditLogImmutableError,
    AuditOperationSource,
    AuditTargetType,
)
from apps.auditlog.services import AuditEventError, record_audit_event
from apps.entitlements.models import EntitlementStatus, OrganizationProductEntitlement
from apps.organizations.models import Organization, OrganizationStatus
from apps.product_registry.models import Product, ProductStatus

User = get_user_model()


class AuditLogModelAndImmutabilityTests(TestCase):
    """Test suite for AuditLog model schema, constraints, and immutability guards."""

    def setUp(self):
        super().setUp()
        self.owner = User.objects.create_user(
            email="audit_owner@vibeconnect.internal",
            password="SecurePassword123!",
            full_name="Audit Owner",
            is_active=True,
            is_platform_owner=True,
        )
        self.target_id = uuid.uuid4()
        self.org_id = uuid.uuid4()

    def test_instance_save_after_creation_raises_immutable_error(self):
        """Calling save() on an existing AuditLog record must raise AuditLogImmutableError."""
        log = record_audit_event(
            action=AuditAction.PRODUCT_CREATED,
            target_type=AuditTargetType.PRODUCT,
            target_id=self.target_id,
            target_repr="Product Alpha",
            actor=self.owner,
            organization_id=None,
            operation_source=AuditOperationSource.INTERACTIVE,
            metadata={"code": "PROD_A", "name": "Product Alpha", "status": "draft"},
        )
        log.target_repr = "Modified Representation"
        with self.assertRaises(AuditLogImmutableError):
            log.save()

    def test_instance_delete_raises_immutable_error(self):
        """Calling delete() on an AuditLog instance must raise AuditLogImmutableError."""
        log = record_audit_event(
            action=AuditAction.PRODUCT_CREATED,
            target_type=AuditTargetType.PRODUCT,
            target_id=self.target_id,
            target_repr="Product Alpha",
            actor=self.owner,
            organization_id=None,
            operation_source=AuditOperationSource.INTERACTIVE,
            metadata={"code": "PROD_A", "name": "Product Alpha", "status": "draft"},
        )
        with self.assertRaises(AuditLogImmutableError):
            log.delete()

    def test_queryset_update_raises_immutable_error(self):
        """Calling update() on an AuditLog QuerySet must raise AuditLogImmutableError."""
        record_audit_event(
            action=AuditAction.PRODUCT_CREATED,
            target_type=AuditTargetType.PRODUCT,
            target_id=self.target_id,
            target_repr="Product Alpha",
            actor=self.owner,
            organization_id=None,
            operation_source=AuditOperationSource.INTERACTIVE,
            metadata={"code": "PROD_A", "name": "Product Alpha", "status": "draft"},
        )
        with self.assertRaises(AuditLogImmutableError):
            AuditLog.objects.filter(target_id=self.target_id).update(target_repr="Hacked")

    def test_queryset_delete_raises_immutable_error(self):
        """Calling delete() on an AuditLog QuerySet must raise AuditLogImmutableError."""
        record_audit_event(
            action=AuditAction.PRODUCT_CREATED,
            target_type=AuditTargetType.PRODUCT,
            target_id=self.target_id,
            target_repr="Product Alpha",
            actor=self.owner,
            organization_id=None,
            operation_source=AuditOperationSource.INTERACTIVE,
            metadata={"code": "PROD_A", "name": "Product Alpha", "status": "draft"},
        )
        with self.assertRaises(AuditLogImmutableError):
            AuditLog.objects.filter(target_id=self.target_id).delete()

    def test_queryset_bulk_update_raises_immutable_error(self):
        """Calling bulk_update() on AuditLog.objects.all() must raise AuditLogImmutableError."""
        log = record_audit_event(
            action=AuditAction.PRODUCT_CREATED,
            target_type=AuditTargetType.PRODUCT,
            target_id=self.target_id,
            target_repr="Product Alpha",
            actor=self.owner,
            organization_id=None,
            operation_source=AuditOperationSource.INTERACTIVE,
            metadata={"code": "PROD_A", "name": "Product Alpha", "status": "draft"},
        )
        with self.assertRaises(AuditLogImmutableError):
            AuditLog.objects.all().bulk_update([log], ["target_repr"])

    def test_manager_bulk_update_raises_immutable_error(self):
        """Calling bulk_update() on AuditLog.objects must raise AuditLogImmutableError."""
        log = record_audit_event(
            action=AuditAction.PRODUCT_CREATED,
            target_type=AuditTargetType.PRODUCT,
            target_id=self.target_id,
            target_repr="Product Alpha",
            actor=self.owner,
            organization_id=None,
            operation_source=AuditOperationSource.INTERACTIVE,
            metadata={"code": "PROD_A", "name": "Product Alpha", "status": "draft"},
        )
        with self.assertRaises(AuditLogImmutableError):
            AuditLog.objects.bulk_update([log], ["target_repr"])

    def test_database_check_constraint_org_id_match(self):
        """Organization events require organization_id equal to target_id at the DB constraint level."""
        mismatched_org_id = uuid.uuid4()
        with self.assertRaises(IntegrityError):
            AuditLog.objects.create(
                action=AuditAction.ORGANIZATION_CREATED,
                target_type=AuditTargetType.ORGANIZATION,
                target_id=self.target_id,
                target_repr="Org Alpha",
                actor=self.owner,
                actor_email=self.owner.email,
                organization_id=mismatched_org_id,
                operation_source=AuditOperationSource.INTERACTIVE,
                metadata={"code": "ORG_A", "name": "Org Alpha", "status": "draft"},
            )

    def test_database_check_constraint_entitlement_org_id_required(self):
        """Entitlement events require non-null organization_id at the DB constraint level."""
        with self.assertRaises(IntegrityError):
            AuditLog.objects.create(
                action=AuditAction.ENTITLEMENT_CREATED,
                target_type=AuditTargetType.ENTITLEMENT,
                target_id=self.target_id,
                target_repr="ORG_A : PROD_A",
                actor=self.owner,
                actor_email=self.owner.email,
                organization_id=None,
                operation_source=AuditOperationSource.INTERACTIVE,
                metadata={},
            )

    def test_database_check_constraint_product_auth_org_id_null(self):
        """Product and Auth events require organization_id to be NULL at the DB constraint level."""
        with self.assertRaises(IntegrityError):
            AuditLog.objects.create(
                action=AuditAction.PRODUCT_CREATED,
                target_type=AuditTargetType.PRODUCT,
                target_id=self.target_id,
                target_repr="Product Alpha",
                actor=self.owner,
                actor_email=self.owner.email,
                organization_id=self.org_id,
                operation_source=AuditOperationSource.INTERACTIVE,
                metadata={},
            )

    def test_database_check_constraint_reserved_source_correlation_required(self):
        """Reserved sources bulk_import and integration require non-null correlation_id."""
        with self.assertRaises(IntegrityError):
            AuditLog.objects.create(
                action=AuditAction.PRODUCT_CREATED,
                target_type=AuditTargetType.PRODUCT,
                target_id=self.target_id,
                target_repr="Product Alpha",
                actor=self.owner,
                actor_email=self.owner.email,
                organization_id=None,
                operation_source=AuditOperationSource.BULK_IMPORT,
                correlation_id=None,
                metadata={},
            )


class AuditLogServiceAndAllowlistTests(TestCase):
    """Test suite for record_audit_event service validation, allowlists, and secret exclusion."""

    def setUp(self):
        super().setUp()
        self.owner = User.objects.create_user(
            email="service_owner@vibeconnect.internal",
            password="SecurePassword123!",
            full_name="Service Owner",
            is_active=True,
            is_platform_owner=True,
        )
        self.target_id = uuid.uuid4()
        self.org_id = uuid.uuid4()
        self.prod_id = uuid.uuid4()

    def test_all_11_action_metadata_schemas_valid(self):
        """All 11 approved actions succeed with valid allowlisted metadata."""
        schemas = [
            (
                AuditAction.PRODUCT_CREATED,
                AuditTargetType.PRODUCT,
                self.target_id,
                "Product 1",
                None,
                AuditOperationSource.INTERACTIVE,
                {"code": "PROD_1", "name": "Product 1", "status": "draft"},
            ),
            (
                AuditAction.PRODUCT_UPDATED,
                AuditTargetType.PRODUCT,
                self.target_id,
                "Product 1",
                None,
                AuditOperationSource.INTERACTIVE,
                {
                    "name_changed": True,
                    "description_changed": False,
                    "status_changed": False,
                    "previous_status": "draft",
                    "resulting_status": "draft",
                },
            ),
            (
                AuditAction.PRODUCT_RETIRED,
                AuditTargetType.PRODUCT,
                self.target_id,
                "Product 1",
                None,
                AuditOperationSource.INTERACTIVE,
                {
                    "name_changed": False,
                    "description_changed": False,
                    "previous_status": "active",
                    "resulting_status": "retired",
                },
            ),
            (
                AuditAction.ORGANIZATION_CREATED,
                AuditTargetType.ORGANIZATION,
                self.org_id,
                "Org 1",
                self.org_id,
                AuditOperationSource.INTERACTIVE,
                {"code": "ORG_1", "name": "Org 1", "status": "draft"},
            ),
            (
                AuditAction.ORGANIZATION_UPDATED,
                AuditTargetType.ORGANIZATION,
                self.org_id,
                "Org 1",
                self.org_id,
                AuditOperationSource.INTERACTIVE,
                {
                    "name_changed": False,
                    "description_changed": True,
                    "status_changed": False,
                    "previous_status": "draft",
                    "resulting_status": "draft",
                },
            ),
            (
                AuditAction.ORGANIZATION_RETIRED,
                AuditTargetType.ORGANIZATION,
                self.org_id,
                "Org 1",
                self.org_id,
                AuditOperationSource.INTERACTIVE,
                {
                    "name_changed": False,
                    "description_changed": False,
                    "previous_status": "active",
                    "resulting_status": "retired",
                },
            ),
            (
                AuditAction.ENTITLEMENT_CREATED,
                AuditTargetType.ENTITLEMENT,
                self.target_id,
                "ORG_1 : PROD_1",
                self.org_id,
                AuditOperationSource.INTERACTIVE,
                {
                    "organization_code": "ORG_1",
                    "product_id": str(self.prod_id),
                    "product_code": "PROD_1",
                    "previous_status": None,
                    "resulting_status": "draft",
                },
            ),
            (
                AuditAction.ENTITLEMENT_STATUS_CHANGED,
                AuditTargetType.ENTITLEMENT,
                self.target_id,
                "ORG_1 : PROD_1",
                self.org_id,
                AuditOperationSource.INTERACTIVE,
                {
                    "organization_code": "ORG_1",
                    "product_id": str(self.prod_id),
                    "product_code": "PROD_1",
                    "previous_status": "draft",
                    "resulting_status": "active",
                },
            ),
            (
                AuditAction.ENTITLEMENT_REVOKED,
                AuditTargetType.ENTITLEMENT,
                self.target_id,
                "ORG_1 : PROD_1",
                self.org_id,
                AuditOperationSource.INTERACTIVE,
                {
                    "organization_code": "ORG_1",
                    "product_id": str(self.prod_id),
                    "product_code": "PROD_1",
                    "previous_status": "active",
                    "resulting_status": "revoked",
                },
            ),
            (
                AuditAction.LOGIN_SUCCESS,
                AuditTargetType.AUTH,
                self.owner.id,
                "Platform Owner Session",
                None,
                AuditOperationSource.AUTHENTICATION,
                {"auth_method": "session"},
            ),
            (
                AuditAction.LOGOUT_SUCCESS,
                AuditTargetType.AUTH,
                self.owner.id,
                "Platform Owner Session",
                None,
                AuditOperationSource.AUTHENTICATION,
                {"auth_method": "session"},
            ),
        ]

        for action, target_type, target_id, target_repr, org_id, source, metadata in schemas:
            with self.subTest(action=action):
                log = record_audit_event(
                    action=action,
                    target_type=target_type,
                    target_id=target_id,
                    target_repr=target_repr,
                    actor=self.owner,
                    organization_id=org_id,
                    operation_source=source,
                    metadata=metadata,
                )
                self.assertEqual(log.action, action)
                self.assertEqual(log.target_type, target_type)
                self.assertEqual(log.actor, self.owner)
                self.assertEqual(log.organization_id, org_id)

    def test_missing_and_unknown_metadata_keys_rejected(self):
        """Missing or extraneous keys in metadata must raise AuditEventError."""
        # Missing key 'status'
        with self.assertRaises(AuditEventError):
            record_audit_event(
                action=AuditAction.PRODUCT_CREATED,
                target_type=AuditTargetType.PRODUCT,
                target_id=self.target_id,
                target_repr="Product",
                actor=self.owner,
                organization_id=None,
                operation_source=AuditOperationSource.INTERACTIVE,
                metadata={"code": "PROD", "name": "Name"},
            )

        # Extra unexpected key 'extra_field'
        with self.assertRaises(AuditEventError):
            record_audit_event(
                action=AuditAction.PRODUCT_CREATED,
                target_type=AuditTargetType.PRODUCT,
                target_id=self.target_id,
                target_repr="Product",
                actor=self.owner,
                organization_id=None,
                operation_source=AuditOperationSource.INTERACTIVE,
                metadata={"code": "PROD", "name": "Name", "status": "draft", "extra_field": "val"},
            )

    def test_secret_terms_in_metadata_rejected(self):
        """Metadata containing secret terms in keys or values must be rejected, while allowing safe auth_method='session'."""
        # 1. Accepted: safe approved pair auth_method="session" for login_success and logout_success
        log_login = record_audit_event(
            action=AuditAction.LOGIN_SUCCESS,
            target_type=AuditTargetType.AUTH,
            target_id=self.owner.id,
            target_repr=self.owner.email,
            actor=self.owner,
            organization_id=None,
            operation_source=AuditOperationSource.AUTHENTICATION,
            metadata={"auth_method": "session"},
        )
        self.assertEqual(log_login.metadata["auth_method"], "session")

        log_logout = record_audit_event(
            action=AuditAction.LOGOUT_SUCCESS,
            target_type=AuditTargetType.AUTH,
            target_id=self.owner.id,
            target_repr=self.owner.email,
            actor=self.owner,
            organization_id=None,
            operation_source=AuditOperationSource.AUTHENTICATION,
            metadata={"auth_method": "session"},
        )
        self.assertEqual(log_logout.metadata["auth_method"], "session")

        # 2. Rejected: session credentials/keys in metadata keys or values
        for bad_meta in [
            {"auth_method": "session", "session_key": "active_key_123"},
            {"auth_method": "session", "session_id": "sid_999"},
            {"auth_method": "session_token"},
            {"auth_method": "session_id"},
        ]:
            with self.assertRaises(AuditEventError):
                record_audit_event(
                    action=AuditAction.LOGIN_SUCCESS,
                    target_type=AuditTargetType.AUTH,
                    target_id=self.owner.id,
                    target_repr=self.owner.email,
                    actor=self.owner,
                    organization_id=None,
                    operation_source=AuditOperationSource.AUTHENTICATION,
                    metadata=bad_meta,
                )

        # 3. Rejected: prohibited terms in keys or values (password, token, secret, cookie, csrf, authorization)
        prohibited_samples = [
            {"code": "prod", "name": "Name", "status": "draft", "password": "123"},
            {"code": "prod", "name": "Name", "status": "draft", "token": "xyz"},
            {"code": "prod", "name": "Name", "status": "draft", "secret": "abc"},
            {"code": "prod", "name": "Name", "status": "draft", "cookie": "val"},
            {"code": "prod", "name": "Name", "status": "draft", "csrf": "token"},
            {"code": "prod", "name": "Name", "status": "draft", "authorization": "bearer"},
            {"code": "prod", "name": "Name", "status": "draft", "api_token_key": "val"},
        ]
        for meta in prohibited_samples:
            with self.assertRaises(AuditEventError):
                record_audit_event(
                    action=AuditAction.PRODUCT_CREATED,
                    target_type=AuditTargetType.PRODUCT,
                    target_id=self.target_id,
                    target_repr="Product",
                    actor=self.owner,
                    organization_id=None,
                    operation_source=AuditOperationSource.INTERACTIVE,
                    metadata=meta,
                )

        # 4. Rejected: unsupported auth_method values
        for unsupported_auth in ["oauth", "bearer", "cookie", "jwt", "token"]:
            with self.assertRaises(AuditEventError):
                record_audit_event(
                    action=AuditAction.LOGIN_SUCCESS,
                    target_type=AuditTargetType.AUTH,
                    target_id=self.owner.id,
                    target_repr=self.owner.email,
                    actor=self.owner,
                    organization_id=None,
                    operation_source=AuditOperationSource.AUTHENTICATION,
                    metadata={"auth_method": unsupported_auth},
                )

    def test_reserved_source_rejected_for_current_producers(self):
        """Current Phase 1F producers cannot use bulk_import or integration sources."""
        with self.assertRaises(AuditEventError):
            record_audit_event(
                action=AuditAction.PRODUCT_CREATED,
                target_type=AuditTargetType.PRODUCT,
                target_id=self.target_id,
                target_repr="Product",
                actor=self.owner,
                organization_id=None,
                operation_source=AuditOperationSource.BULK_IMPORT,
                metadata={"code": "PROD", "name": "Name", "status": "draft"},
            )

    def test_organization_context_validation_in_service(self):
        """Service enforces exact organization_id rules for orgs, entitlements, and products."""
        # Organization event with mismatched organization_id
        with self.assertRaises(AuditEventError):
            record_audit_event(
                action=AuditAction.ORGANIZATION_CREATED,
                target_type=AuditTargetType.ORGANIZATION,
                target_id=self.org_id,
                target_repr="Org",
                actor=self.owner,
                organization_id=uuid.uuid4(),
                operation_source=AuditOperationSource.INTERACTIVE,
                metadata={"code": "ORG", "name": "Name", "status": "draft"},
            )

        # Entitlement event with null organization_id
        with self.assertRaises(AuditEventError):
            record_audit_event(
                action=AuditAction.ENTITLEMENT_CREATED,
                target_type=AuditTargetType.ENTITLEMENT,
                target_id=self.target_id,
                target_repr="Ent",
                actor=self.owner,
                organization_id=None,
                operation_source=AuditOperationSource.INTERACTIVE,
                metadata={
                    "organization_code": "ORG",
                    "product_id": str(self.prod_id),
                    "product_code": "PROD",
                    "previous_status": None,
                    "resulting_status": "draft",
                },
            )

        # Product event with non-null organization_id
        with self.assertRaises(AuditEventError):
            record_audit_event(
                action=AuditAction.PRODUCT_CREATED,
                target_type=AuditTargetType.PRODUCT,
                target_id=self.target_id,
                target_repr="Prod",
                actor=self.owner,
                organization_id=self.org_id,
                operation_source=AuditOperationSource.INTERACTIVE,
                metadata={"code": "PROD", "name": "Name", "status": "draft"},
            )

    def test_retired_state_audit_service_validation(self):
        """Service enforces exact conditional retired-status rules for product and org updates."""
        # 1. Product: valid retired -> retired with status_changed=False
        log_prod = record_audit_event(
            action=AuditAction.PRODUCT_UPDATED,
            target_type=AuditTargetType.PRODUCT,
            target_id=self.target_id,
            target_repr="Retired Prod",
            actor=self.owner,
            organization_id=None,
            operation_source=AuditOperationSource.INTERACTIVE,
            metadata={
                "name_changed": True,
                "description_changed": False,
                "status_changed": False,
                "previous_status": "retired",
                "resulting_status": "retired",
            },
        )
        self.assertEqual(log_prod.metadata["previous_status"], "retired")
        self.assertEqual(log_prod.metadata["resulting_status"], "retired")
        self.assertFalse(log_prod.metadata["status_changed"])

        # 2. Product: invalid retired -> retired with status_changed=True
        with self.assertRaises(AuditEventError):
            record_audit_event(
                action=AuditAction.PRODUCT_UPDATED,
                target_type=AuditTargetType.PRODUCT,
                target_id=self.target_id,
                target_repr="Retired Prod",
                actor=self.owner,
                organization_id=None,
                operation_source=AuditOperationSource.INTERACTIVE,
                metadata={
                    "name_changed": True,
                    "description_changed": False,
                    "status_changed": True,
                    "previous_status": "retired",
                    "resulting_status": "retired",
                },
            )

        # 3. Product: transition into retired under product_updated rejected (must use product_retired)
        with self.assertRaises(AuditEventError):
            record_audit_event(
                action=AuditAction.PRODUCT_UPDATED,
                target_type=AuditTargetType.PRODUCT,
                target_id=self.target_id,
                target_repr="Retired Prod",
                actor=self.owner,
                organization_id=None,
                operation_source=AuditOperationSource.INTERACTIVE,
                metadata={
                    "name_changed": False,
                    "description_changed": False,
                    "status_changed": True,
                    "previous_status": "active",
                    "resulting_status": "retired",
                },
            )

        # 4. Product: transition out of retired under product_updated rejected
        for bad_result in ["active", "inactive", "draft"]:
            with self.assertRaises(AuditEventError):
                record_audit_event(
                    action=AuditAction.PRODUCT_UPDATED,
                    target_type=AuditTargetType.PRODUCT,
                    target_id=self.target_id,
                    target_repr="Retired Prod",
                    actor=self.owner,
                    organization_id=None,
                    operation_source=AuditOperationSource.INTERACTIVE,
                    metadata={
                        "name_changed": False,
                        "description_changed": False,
                        "status_changed": True,
                        "previous_status": "retired",
                        "resulting_status": bad_result,
                    },
                )

        # 5. Product: product_retired rejected when previous_status is already retired
        with self.assertRaises(AuditEventError):
            record_audit_event(
                action=AuditAction.PRODUCT_RETIRED,
                target_type=AuditTargetType.PRODUCT,
                target_id=self.target_id,
                target_repr="Retired Prod",
                actor=self.owner,
                organization_id=None,
                operation_source=AuditOperationSource.INTERACTIVE,
                metadata={
                    "name_changed": False,
                    "description_changed": False,
                    "previous_status": "retired",
                    "resulting_status": "retired",
                },
            )

        # 6. Organization: retired -> retired rejected under organization_updated
        for status_changed_val in [False, True]:
            with self.assertRaises(AuditEventError):
                record_audit_event(
                    action=AuditAction.ORGANIZATION_UPDATED,
                    target_type=AuditTargetType.ORGANIZATION,
                    target_id=self.org_id,
                    target_repr="Retired Org",
                    actor=self.owner,
                    organization_id=self.org_id,
                    operation_source=AuditOperationSource.INTERACTIVE,
                    metadata={
                        "name_changed": False,
                        "description_changed": True,
                        "status_changed": status_changed_val,
                        "previous_status": "retired",
                        "resulting_status": "retired",
                    },
                )

        # 7. Organization: transitions into retired under organization_updated rejected
        for prev_status in ["draft", "active", "suspended"]:
            with self.assertRaises(AuditEventError):
                record_audit_event(
                    action=AuditAction.ORGANIZATION_UPDATED,
                    target_type=AuditTargetType.ORGANIZATION,
                    target_id=self.org_id,
                    target_repr="Retired Org",
                    actor=self.owner,
                    organization_id=self.org_id,
                    operation_source=AuditOperationSource.INTERACTIVE,
                    metadata={
                        "name_changed": False,
                        "description_changed": False,
                        "status_changed": True,
                        "previous_status": prev_status,
                        "resulting_status": "retired",
                    },
                )

        # 8. Organization: transitions out of retired under organization_updated rejected
        for bad_org_result in ["active", "suspended", "draft"]:
            with self.assertRaises(AuditEventError):
                record_audit_event(
                    action=AuditAction.ORGANIZATION_UPDATED,
                    target_type=AuditTargetType.ORGANIZATION,
                    target_id=self.org_id,
                    target_repr="Retired Org",
                    actor=self.owner,
                    organization_id=self.org_id,
                    operation_source=AuditOperationSource.INTERACTIVE,
                    metadata={
                        "name_changed": False,
                        "description_changed": False,
                        "status_changed": True,
                        "previous_status": "retired",
                        "resulting_status": bad_org_result,
                    },
                )

        # 9. Organization: organization_retired rejected when previous_status is already retired
        with self.assertRaises(AuditEventError):
            record_audit_event(
                action=AuditAction.ORGANIZATION_RETIRED,
                target_type=AuditTargetType.ORGANIZATION,
                target_id=self.org_id,
                target_repr="Retired Org",
                actor=self.owner,
                organization_id=self.org_id,
                operation_source=AuditOperationSource.INTERACTIVE,
                metadata={
                    "name_changed": False,
                    "description_changed": False,
                    "previous_status": "retired",
                    "resulting_status": "retired",
                },
            )

    def test_entitlement_revocation_service_real_transition_required(self):
        """Entitlement revocation service enforces real transition into revoked state."""
        # 1. Valid revocation from active
        log_rev = record_audit_event(
            action=AuditAction.ENTITLEMENT_REVOKED,
            target_type=AuditTargetType.ENTITLEMENT,
            target_id=self.target_id,
            target_repr="ORG : PROD",
            actor=self.owner,
            organization_id=self.org_id,
            operation_source=AuditOperationSource.INTERACTIVE,
            metadata={
                "organization_code": "ORG",
                "product_id": str(self.prod_id),
                "product_code": "PROD",
                "previous_status": "active",
                "resulting_status": "revoked",
            },
        )
        self.assertEqual(log_rev.metadata["resulting_status"], "revoked")

        # 2. Invalid revocation when already revoked
        with self.assertRaises(AuditEventError):
            record_audit_event(
                action=AuditAction.ENTITLEMENT_REVOKED,
                target_type=AuditTargetType.ENTITLEMENT,
                target_id=self.target_id,
                target_repr="ORG : PROD",
                actor=self.owner,
                organization_id=self.org_id,
                operation_source=AuditOperationSource.INTERACTIVE,
                metadata={
                    "organization_code": "ORG",
                    "product_id": str(self.prod_id),
                    "product_code": "PROD",
                    "previous_status": "revoked",
                    "resulting_status": "revoked",
                },
            )


class AuditMutationHookAndRollbackTests(TestCase):
    """Test suite for mutation hook instrumentation, atomic rollback, and no-op handling."""

    def setUp(self):
        super().setUp()
        self.client = APIClient(enforce_csrf_checks=True)
        self.owner = User.objects.create_user(
            email="hooks_owner@vibeconnect.internal",
            password="SecurePassword123!",
            full_name="Hooks Owner",
            is_active=True,
            is_platform_owner=True,
        )
        self.client.force_authenticate(user=self.owner)

    def test_product_lifecycle_mutations_create_exact_audit_events(self):
        """Product create, update, and retire create exactly one audit event each."""
        # 1. Create Product
        resp = self.client.post(
            "/api/v1/products/",
            {"code": "HOOK_PROD", "name": "Hook Product", "description": "Desc"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        prod_id = resp.data["id"]

        create_log = AuditLog.objects.get(action=AuditAction.PRODUCT_CREATED, target_id=prod_id)
        self.assertIsNone(create_log.organization_id)
        self.assertEqual(create_log.metadata["code"], "hook_prod")

        # 2. Update Product name
        resp = self.client.patch(
            f"/api/v1/products/{prod_id}/",
            {"name": "Updated Hook Product"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        update_log = AuditLog.objects.get(action=AuditAction.PRODUCT_UPDATED, target_id=prod_id)
        self.assertTrue(update_log.metadata["name_changed"])
        self.assertFalse(update_log.metadata["status_changed"])

        # 3. No-op Product update creates zero audit events
        initial_count = AuditLog.objects.count()
        resp = self.client.patch(
            f"/api/v1/products/{prod_id}/",
            {"name": "Updated Hook Product"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(AuditLog.objects.count(), initial_count)

        # 4. Retire Product
        resp = self.client.patch(
            f"/api/v1/products/{prod_id}/",
            {"status": "retired"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        retire_log = AuditLog.objects.get(action=AuditAction.PRODUCT_RETIRED, target_id=prod_id)
        self.assertEqual(retire_log.metadata["resulting_status"], "retired")
        self.assertEqual(retire_log.metadata["previous_status"], "draft")

        # 5. Metadata-only update on an already-retired Product emits exactly one product_updated
        resp = self.client.patch(
            f"/api/v1/products/{prod_id}/",
            {"name": "Archived Hook Product"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["name"], "Archived Hook Product")
        self.assertEqual(resp.data["status"], "retired")

        retired_update_log = AuditLog.objects.filter(
            action=AuditAction.PRODUCT_UPDATED, target_id=prod_id
        ).latest("timestamp")
        self.assertEqual(retired_update_log.metadata["previous_status"], "retired")
        self.assertEqual(retired_update_log.metadata["resulting_status"], "retired")
        self.assertFalse(retired_update_log.metadata["status_changed"])
        self.assertTrue(retired_update_log.metadata["name_changed"])
        self.assertFalse(retired_update_log.metadata["description_changed"])

        # 6. No-op PATCH on an already-retired Product emits zero audit records
        count_before_noop = AuditLog.objects.count()
        resp = self.client.patch(
            f"/api/v1/products/{prod_id}/",
            {"name": "Archived Hook Product", "status": "retired"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(AuditLog.objects.count(), count_before_noop)

    def test_organization_lifecycle_mutations_create_exact_audit_events(self):
        """Organization create, update, and retire create audit events with matching organization_id."""
        # 1. Create Organization
        resp = self.client.post(
            "/api/v1/organizations/",
            {"code": "HOOK_ORG", "name": "Hook Org", "description": "Desc"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        org_id = uuid.UUID(resp.data["id"])

        create_log = AuditLog.objects.get(action=AuditAction.ORGANIZATION_CREATED, target_id=org_id)
        self.assertEqual(create_log.organization_id, org_id)

        # 2. Update Organization
        resp = self.client.patch(
            f"/api/v1/organizations/{org_id}/",
            {"description": "New Org Desc"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        update_log = AuditLog.objects.get(action=AuditAction.ORGANIZATION_UPDATED, target_id=org_id)
        self.assertTrue(update_log.metadata["description_changed"])

        # 3. No-op Org update produces zero audit events
        count_before = AuditLog.objects.count()
        resp = self.client.patch(
            f"/api/v1/organizations/{org_id}/",
            {"description": "New Org Desc"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(AuditLog.objects.count(), count_before)

        # 4. Retire Organization
        resp = self.client.patch(
            f"/api/v1/organizations/{org_id}/",
            {"status": "retired"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        retire_log = AuditLog.objects.get(action=AuditAction.ORGANIZATION_RETIRED, target_id=org_id)
        self.assertEqual(retire_log.organization_id, org_id)

        # 5. Modification on retired Organization is rejected by domain freeze (Phase 1E) with 0 audit records
        count_before_org_freeze = AuditLog.objects.count()
        resp = self.client.patch(
            f"/api/v1/organizations/{org_id}/",
            {"name": "New Name After Retirement"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("status", resp.data)
        self.assertEqual(AuditLog.objects.count(), count_before_org_freeze)

    def test_entitlement_lifecycle_mutations_create_exact_audit_events(self):
        """Entitlement creation, status change, and revocation derive organization_id."""
        org = Organization.objects.create(
            code="ent_org",
            name="Ent Org",
            status=OrganizationStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )
        prod = Product.objects.create(
            code="ent_prod",
            name="Ent Prod",
            status=ProductStatus.ACTIVE,
            created_by=self.owner,
            updated_by=self.owner,
        )

        # 1. Create Entitlement
        resp = self.client.post(
            "/api/v1/organization-product-entitlements/",
            {"organization_id": str(org.id), "product_id": str(prod.id)},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        ent_id = uuid.UUID(resp.data["id"])

        create_log = AuditLog.objects.get(action=AuditAction.ENTITLEMENT_CREATED, target_id=ent_id)
        self.assertEqual(create_log.organization_id, org.id)
        self.assertIsNone(create_log.metadata["previous_status"])
        self.assertEqual(create_log.metadata["resulting_status"], "draft")

        # 2. Transition to Active
        resp = self.client.patch(
            f"/api/v1/organization-product-entitlements/{ent_id}/",
            {"status": "active"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        status_log = AuditLog.objects.get(action=AuditAction.ENTITLEMENT_STATUS_CHANGED, target_id=ent_id)
        self.assertEqual(status_log.organization_id, org.id)
        self.assertEqual(status_log.metadata["previous_status"], "draft")
        self.assertEqual(status_log.metadata["resulting_status"], "active")

        # 3. Same-status no-op emits zero audit records
        count_before = AuditLog.objects.count()
        resp = self.client.patch(
            f"/api/v1/organization-product-entitlements/{ent_id}/",
            {"status": "active"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(AuditLog.objects.count(), count_before)

        # 4. Revoke Entitlement
        resp = self.client.patch(
            f"/api/v1/organization-product-entitlements/{ent_id}/",
            {"status": "revoked"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        revoke_log = AuditLog.objects.get(action=AuditAction.ENTITLEMENT_REVOKED, target_id=ent_id)
        self.assertEqual(revoke_log.organization_id, org.id)
        self.assertEqual(revoke_log.metadata["resulting_status"], "revoked")

        # 5. Modification on revoked Entitlement is rejected by domain freeze (Phase 1E) with 0 audit records
        count_before_rev_freeze = AuditLog.objects.count()
        resp = self.client.patch(
            f"/api/v1/organization-product-entitlements/{ent_id}/",
            {"status": "active"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("status", resp.data)
        self.assertEqual(AuditLog.objects.count(), count_before_rev_freeze)

    def test_audit_failure_rolls_back_domain_mutation(self):
        """When audit recording raises AuditEventError, the domain mutation must roll back completely."""
        with patch("apps.auditlog.services.record_audit_event", side_effect=AuditEventError("Simulated Failure")):
            resp = self.client.post(
                "/api/v1/products/",
                {"code": "ROLLBACK_PROD", "name": "Rollback Prod"},
                format="json",
            )
            self.assertEqual(resp.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)
            self.assertEqual(resp.data["detail"], "A server error occurred while recording the audit event.")
            self.assertFalse(Product.objects.filter(code="rollback_prod").exists())
            self.assertFalse(AuditLog.objects.filter(target_repr="Rollback Prod").exists())

    def test_failed_business_mutation_creates_no_audit_event(self):
        """A failed business mutation (e.g. unique constraint violation) creates zero audit records."""
        Product.objects.create(
            code="unique_prod",
            name="Existing Prod",
            created_by=self.owner,
            updated_by=self.owner,
        )
        count_before = AuditLog.objects.count()

        resp = self.client.post(
            "/api/v1/products/",
            {"code": "unique_prod", "name": "Duplicate Code"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(AuditLog.objects.count(), count_before)


class AuditAuthenticationTests(TestCase):
    """Test suite for authentication audit events and session failure isolation."""

    def setUp(self):
        super().setUp()
        cache.clear()
        self.addCleanup(cache.clear)
        self.client = APIClient(enforce_csrf_checks=True)
        self.owner = User.objects.create_user(
            email="auth_test_owner@vibeconnect.internal",
            password="SecurePassword123!",
            full_name="Auth Owner",
            is_active=True,
            is_platform_owner=True,
        )

    def test_login_audit_success(self):
        """Successful login creates login_success audit event."""
        csrf_resp = self.client.get("/api/v1/auth/csrf/")
        csrf_token = csrf_resp.cookies[settings.CSRF_COOKIE_NAME].value

        resp = self.client.post(
            "/api/v1/auth/login/",
            {"email": "auth_test_owner@vibeconnect.internal", "password": "SecurePassword123!"},
            format="json",
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        log = AuditLog.objects.get(action=AuditAction.LOGIN_SUCCESS, target_id=self.owner.id)
        self.assertEqual(log.operation_source, AuditOperationSource.AUTHENTICATION)
        self.assertIsNone(log.organization_id)
        self.assertEqual(log.metadata["auth_method"], "session")

    def test_failed_login_creates_no_audit_event(self):
        """Failed login attempts do not create audit records in Phase 1F."""
        csrf_resp = self.client.get("/api/v1/auth/csrf/")
        csrf_token = csrf_resp.cookies[settings.CSRF_COOKIE_NAME].value

        resp = self.client.post(
            "/api/v1/auth/login/",
            {"email": "auth_test_owner@vibeconnect.internal", "password": "WrongPassword!"},
            format="json",
            HTTP_X_CSRFTOKEN=csrf_token,
        )
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertFalse(AuditLog.objects.filter(action=AuditAction.LOGIN_SUCCESS).exists())

    def test_login_audit_failure_leaves_no_session(self):
        """If login audit creation fails, session is flushed and client is left unauthenticated."""
        csrf_resp = self.client.get("/api/v1/auth/csrf/")
        csrf_token = csrf_resp.cookies[settings.CSRF_COOKIE_NAME].value

        with patch("apps.identity.views.record_audit_event", side_effect=AuditEventError("Audit DB down")):
            resp = self.client.post(
                "/api/v1/auth/login/",
                {"email": "auth_test_owner@vibeconnect.internal", "password": "SecurePassword123!"},
                format="json",
                HTTP_X_CSRFTOKEN=csrf_token,
            )
            self.assertEqual(resp.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)

        # Verify client is not authenticated
        me_resp = self.client.get("/api/v1/auth/me/")
        self.assertEqual(me_resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_logout_audit_success(self):
        """Successful logout creates logout_success audit event."""
        csrf_resp = self.client.get("/api/v1/auth/csrf/")
        initial_token = csrf_resp.cookies[settings.CSRF_COOKIE_NAME].value

        login_resp = self.client.post(
            "/api/v1/auth/login/",
            {"email": "auth_test_owner@vibeconnect.internal", "password": "SecurePassword123!"},
            format="json",
            HTTP_X_CSRFTOKEN=initial_token,
        )
        self.assertEqual(login_resp.status_code, status.HTTP_200_OK)

        rotated_token = self.client.cookies[settings.CSRF_COOKIE_NAME].value

        logout_resp = self.client.post(
            "/api/v1/auth/logout/",
            {},
            format="json",
            HTTP_X_CSRFTOKEN=rotated_token,
        )
        self.assertEqual(logout_resp.status_code, status.HTTP_200_OK)

        log = AuditLog.objects.get(action=AuditAction.LOGOUT_SUCCESS, target_id=self.owner.id)
        self.assertEqual(log.operation_source, AuditOperationSource.AUTHENTICATION)
        self.assertIsNone(log.organization_id)

    def test_logout_audit_failure_leaves_user_logged_out(self):
        """If logout audit creation fails, user session remains terminated."""
        csrf_resp = self.client.get("/api/v1/auth/csrf/")
        initial_token = csrf_resp.cookies[settings.CSRF_COOKIE_NAME].value

        login_resp = self.client.post(
            "/api/v1/auth/login/",
            {"email": "auth_test_owner@vibeconnect.internal", "password": "SecurePassword123!"},
            format="json",
            HTTP_X_CSRFTOKEN=initial_token,
        )
        self.assertEqual(login_resp.status_code, status.HTTP_200_OK)

        rotated_token = self.client.cookies[settings.CSRF_COOKIE_NAME].value

        with patch("apps.identity.views.record_audit_event", side_effect=AuditEventError("Audit DB down")):
            logout_resp = self.client.post(
                "/api/v1/auth/logout/",
                {},
                format="json",
                HTTP_X_CSRFTOKEN=rotated_token,
            )
            self.assertEqual(logout_resp.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)

        # Verify user is logged out despite the 500 error
        me_resp = self.client.get("/api/v1/auth/me/")
        self.assertEqual(me_resp.status_code, status.HTTP_401_UNAUTHORIZED)


class AuditLogApiReadOnlyTests(TestCase):
    """Test suite for /api/v1/audit-logs/ permissions, method restrictions, filters, and query bounds."""

    def setUp(self):
        super().setUp()
        cache.clear()
        self.addCleanup(cache.clear)
        self.client = APIClient(enforce_csrf_checks=True)
        self.owner = User.objects.create_user(
            email="api_owner@vibeconnect.internal",
            password="SecurePassword123!",
            full_name="API Owner",
            is_active=True,
            is_platform_owner=True,
        )
        self.regular_user = User.objects.create_user(
            email="regular@vibeconnect.internal",
            password="SecurePassword123!",
            full_name="Regular User",
            is_active=True,
            is_platform_owner=False,
        )

        # Seed sample audit log
        self.sample_log = record_audit_event(
            action=AuditAction.PRODUCT_CREATED,
            target_type=AuditTargetType.PRODUCT,
            target_id=uuid.uuid4(),
            target_repr="Sample Product",
            actor=self.owner,
            organization_id=None,
            operation_source=AuditOperationSource.INTERACTIVE,
            metadata={"code": "SAMPLE", "name": "Sample Product", "status": "draft"},
        )

    def test_unauthenticated_access_rejected(self):
        """Unauthenticated requests to list and detail return HTTP 401."""
        resp_list = self.client.get("/api/v1/audit-logs/")
        self.assertEqual(resp_list.status_code, status.HTTP_401_UNAUTHORIZED)

        resp_detail = self.client.get(f"/api/v1/audit-logs/{self.sample_log.id}/")
        self.assertEqual(resp_detail.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_non_platform_owner_access_forbidden(self):
        """Authenticated non-platform owners receive HTTP 403 Forbidden."""
        self.client.force_authenticate(user=self.regular_user)

        resp_list = self.client.get("/api/v1/audit-logs/")
        self.assertEqual(resp_list.status_code, status.HTTP_403_FORBIDDEN)

        resp_detail = self.client.get(f"/api/v1/audit-logs/{self.sample_log.id}/")
        self.assertEqual(resp_detail.status_code, status.HTTP_403_FORBIDDEN)

    def test_platform_owner_list_and_detail_success(self):
        """Platform Owner receives HTTP 200 with sanitized actor snapshot and metadata."""
        self.client.force_authenticate(user=self.owner)

        resp_list = self.client.get("/api/v1/audit-logs/")
        self.assertEqual(resp_list.status_code, status.HTTP_200_OK)
        self.assertEqual(resp_list.data["count"], 1)
        self.assertEqual(resp_list.data["results"][0]["actor"]["email"], self.owner.email)
        self.assertNotIn("metadata", resp_list.data["results"][0])

        resp_detail = self.client.get(f"/api/v1/audit-logs/{self.sample_log.id}/")
        self.assertEqual(resp_detail.status_code, status.HTTP_200_OK)
        self.assertEqual(resp_detail.data["metadata"]["code"], "SAMPLE")
        self.assertEqual(resp_detail.data["actor"]["full_name"], "API Owner")

    def test_http_method_restrictions_with_valid_csrf(self):
        """POST, PUT, PATCH, DELETE with valid CSRF return HTTP 405 Method Not Allowed."""
        csrf_resp = self.client.get("/api/v1/auth/csrf/")
        initial_token = csrf_resp.cookies[settings.CSRF_COOKIE_NAME].value

        login_resp = self.client.post(
            "/api/v1/auth/login/",
            {"email": "api_owner@vibeconnect.internal", "password": "SecurePassword123!"},
            format="json",
            HTTP_X_CSRFTOKEN=initial_token,
        )
        self.assertEqual(login_resp.status_code, status.HTTP_200_OK)

        rotated_token = self.client.cookies[settings.CSRF_COOKIE_NAME].value
        headers = {"HTTP_X_CSRFTOKEN": rotated_token}

        # List endpoint mutating methods
        self.assertEqual(
            self.client.post("/api/v1/audit-logs/", {}, format="json", **headers).status_code,
            status.HTTP_405_METHOD_NOT_ALLOWED,
        )
        self.assertEqual(
            self.client.put("/api/v1/audit-logs/", {}, format="json", **headers).status_code,
            status.HTTP_405_METHOD_NOT_ALLOWED,
        )
        self.assertEqual(
            self.client.patch("/api/v1/audit-logs/", {}, format="json", **headers).status_code,
            status.HTTP_405_METHOD_NOT_ALLOWED,
        )
        self.assertEqual(
            self.client.delete("/api/v1/audit-logs/", **headers).status_code,
            status.HTTP_405_METHOD_NOT_ALLOWED,
        )

        # Detail endpoint mutating methods
        detail_url = f"/api/v1/audit-logs/{self.sample_log.id}/"
        self.assertEqual(
            self.client.post(detail_url, {}, format="json", **headers).status_code,
            status.HTTP_405_METHOD_NOT_ALLOWED,
        )
        self.assertEqual(
            self.client.put(detail_url, {}, format="json", **headers).status_code,
            status.HTTP_405_METHOD_NOT_ALLOWED,
        )
        self.assertEqual(
            self.client.patch(detail_url, {}, format="json", **headers).status_code,
            status.HTTP_405_METHOD_NOT_ALLOWED,
        )
        self.assertEqual(
            self.client.delete(detail_url, **headers).status_code,
            status.HTTP_405_METHOD_NOT_ALLOWED,
        )

    def test_malformed_and_nonexistent_detail_uuid_returns_404(self):
        """Malformed or non-existent UUID path returns safe HTTP 404."""
        self.client.force_authenticate(user=self.owner)

        resp_malformed = self.client.get("/api/v1/audit-logs/not-a-valid-uuid/")
        self.assertEqual(resp_malformed.status_code, status.HTTP_404_NOT_FOUND)

        resp_nonexistent = self.client.get(f"/api/v1/audit-logs/{uuid.uuid4()}/")
        self.assertEqual(resp_nonexistent.status_code, status.HTTP_404_NOT_FOUND)

    def test_query_filtering_and_validation(self):
        """Tests strict filtering by action, target_type, target_id, actor_id, organization_id, and dates."""
        self.client.force_authenticate(user=self.owner)

        # Filter by action
        resp = self.client.get("/api/v1/audit-logs/?action=product_created")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["count"], 1)

        # Invalid action returns 400
        resp = self.client.get("/api/v1/audit-logs/?action=invalid_action")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

        # Invalid UUID filter returns 400
        resp = self.client.get("/api/v1/audit-logs/?organization_id=not-a-uuid")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

        # Duplicate organization_id parameter returns 400
        uuid1 = uuid.uuid4()
        uuid2 = uuid.uuid4()
        resp = self.client.get(f"/api/v1/audit-logs/?organization_id={uuid1}&organization_id={uuid2}")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

        # Reversed date range returns 400
        now = timezone.now()
        yesterday = now - timedelta(days=1)
        resp = self.client.get(
            f"/api/v1/audit-logs/?date_from={now.isoformat()}&date_to={yesterday.isoformat()}"
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

        # Duplicate query param returns 400
        resp = self.client.get("/api/v1/audit-logs/?action=product_created&action=product_updated")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

        # Unknown query param returns 400
        resp = self.client.get("/api/v1/audit-logs/?unknown_param=val")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_default_ordering_and_all_six_supported_ordering_values(self):
        """Tests default ordering and all six supported client ordering values with deterministic tie-breakers."""
        self.client.force_authenticate(user=self.owner)

        org_id = uuid.uuid4()
        log_org = record_audit_event(
            action=AuditAction.ORGANIZATION_CREATED,
            target_type=AuditTargetType.ORGANIZATION,
            target_id=org_id,
            target_repr="Org Beta",
            actor=self.owner,
            organization_id=org_id,
            operation_source=AuditOperationSource.INTERACTIVE,
            metadata={"code": "ORG_B", "name": "Org Beta", "status": "draft"},
        )
        ent_id = uuid.uuid4()
        prod_id = uuid.uuid4()
        log_ent = record_audit_event(
            action=AuditAction.ENTITLEMENT_CREATED,
            target_type=AuditTargetType.ENTITLEMENT,
            target_id=ent_id,
            target_repr="ORG_B - PROD_B",
            actor=self.owner,
            organization_id=org_id,
            operation_source=AuditOperationSource.INTERACTIVE,
            metadata={
                "organization_code": "ORG_B",
                "product_id": str(prod_id),
                "product_code": "PROD_B",
                "previous_status": None,
                "resulting_status": "draft",
            },
        )
        # Create a second product log with the same action and target_type as sample_log to test tie-breaker
        log_prod2 = record_audit_event(
            action=AuditAction.PRODUCT_CREATED,
            target_type=AuditTargetType.PRODUCT,
            target_id=uuid.uuid4(),
            target_repr="Product Gamma",
            actor=self.owner,
            organization_id=None,
            operation_source=AuditOperationSource.INTERACTIVE,
            metadata={"code": "PROD_G", "name": "Product Gamma", "status": "draft"},
        )

        # 1. Default ordering: [-timestamp, -id]
        resp_def = self.client.get("/api/v1/audit-logs/")
        self.assertEqual(resp_def.status_code, status.HTTP_200_OK)
        ids_def = [item["id"] for item in resp_def.data["results"]]
        expected_def_ids = [
            str(log.id)
            for log in AuditLog.objects.order_by("-timestamp", "-id")
        ]
        self.assertEqual(ids_def, expected_def_ids)

        # 2. ordering=timestamp -> [timestamp, id]
        resp_ts = self.client.get("/api/v1/audit-logs/?ordering=timestamp")
        self.assertEqual(resp_ts.status_code, status.HTTP_200_OK)
        self.assertEqual(
            [item["id"] for item in resp_ts.data["results"]],
            [str(l.id) for l in AuditLog.objects.order_by("timestamp", "id")],
        )

        # 3. ordering=-timestamp -> [-timestamp, -id]
        resp_mts = self.client.get("/api/v1/audit-logs/?ordering=-timestamp")
        self.assertEqual(resp_mts.status_code, status.HTTP_200_OK)
        self.assertEqual(
            [item["id"] for item in resp_mts.data["results"]],
            [str(l.id) for l in AuditLog.objects.order_by("-timestamp", "-id")],
        )

        # 4. ordering=action -> [action, -timestamp, -id]
        resp_act = self.client.get("/api/v1/audit-logs/?ordering=action")
        self.assertEqual(resp_act.status_code, status.HTTP_200_OK)
        self.assertEqual(
            [item["id"] for item in resp_act.data["results"]],
            [str(l.id) for l in AuditLog.objects.order_by("action", "-timestamp", "-id")],
        )

        # 5. ordering=-action -> [-action, -timestamp, -id]
        resp_mact = self.client.get("/api/v1/audit-logs/?ordering=-action")
        self.assertEqual(resp_mact.status_code, status.HTTP_200_OK)
        self.assertEqual(
            [item["id"] for item in resp_mact.data["results"]],
            [str(l.id) for l in AuditLog.objects.order_by("-action", "-timestamp", "-id")],
        )

        # 6. ordering=target_type -> [target_type, -timestamp, -id]
        resp_tt = self.client.get("/api/v1/audit-logs/?ordering=target_type")
        self.assertEqual(resp_tt.status_code, status.HTTP_200_OK)
        self.assertEqual(
            [item["id"] for item in resp_tt.data["results"]],
            [str(l.id) for l in AuditLog.objects.order_by("target_type", "-timestamp", "-id")],
        )

        # 7. ordering=-target_type -> [-target_type, -timestamp, -id]
        resp_mtt = self.client.get("/api/v1/audit-logs/?ordering=-target_type")
        self.assertEqual(resp_mtt.status_code, status.HTTP_200_OK)
        self.assertEqual(
            [item["id"] for item in resp_mtt.data["results"]],
            [str(l.id) for l in AuditLog.objects.order_by("-target_type", "-timestamp", "-id")],
        )

        # Stable tie-breaker verification when primary fields are equal:
        # Both self.sample_log and log_prod2 share action='product_created'.
        # With ordering=action, the tie-breaker [-timestamp, -id] places the newer log_prod2 before sample_log.
        prod_results = [
            item["id"] for item in resp_act.data["results"]
            if item["action"] == "product_created"
        ]
        self.assertEqual(prod_results, [str(log_prod2.id), str(self.sample_log.id)])

    def test_ordering_validation_rejections(self):
        """Tests that unsupported ordering fields and duplicate ordering parameters return HTTP 400."""
        self.client.force_authenticate(user=self.owner)

        # Unsupported client ordering fields (including id and comma-separated multiple fields)
        for unsupported in ["id", "-id", "actor", "target_repr", "invalid_field", "timestamp,id", "action,-timestamp"]:
            resp = self.client.get(f"/api/v1/audit-logs/?ordering={unsupported}")
            self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertIn("ordering", resp.data)

        # Duplicate ordering parameters return 400
        resp_dup = self.client.get("/api/v1/audit-logs/?ordering=timestamp&ordering=-timestamp")
        self.assertEqual(resp_dup.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("ordering", resp_dup.data)

    def test_pagination_defaults_and_custom_page_size(self):
        """Tests default page size of 20, valid custom page size, and maximum page size 100."""
        self.client.force_authenticate(user=self.owner)

        # Seed 24 additional logs so total count is 25 (exceeding default page_size 20)
        for i in range(24):
            record_audit_event(
                action=AuditAction.PRODUCT_CREATED,
                target_type=AuditTargetType.PRODUCT,
                target_id=uuid.uuid4(),
                target_repr=f"Paginated Prod {i}",
                actor=self.owner,
                organization_id=None,
                operation_source=AuditOperationSource.INTERACTIVE,
                metadata={"code": f"PP{i}", "name": f"Paginated Prod {i}", "status": "draft"},
            )

        # Default page size 20
        resp_default = self.client.get("/api/v1/audit-logs/")
        self.assertEqual(resp_default.status_code, status.HTTP_200_OK)
        self.assertEqual(resp_default.data["count"], 25)
        self.assertEqual(len(resp_default.data["results"]), 20)
        self.assertIsNotNone(resp_default.data["next"])
        self.assertIsNone(resp_default.data["previous"])

        # Page 2 with default page size returns remaining 5 items
        resp_page2 = self.client.get("/api/v1/audit-logs/?page=2")
        self.assertEqual(resp_page2.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp_page2.data["results"]), 5)
        self.assertIsNone(resp_page2.data["next"])
        self.assertIsNotNone(resp_page2.data["previous"])

        # Custom valid page size (e.g. 5)
        resp_custom = self.client.get("/api/v1/audit-logs/?page_size=5")
        self.assertEqual(resp_custom.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp_custom.data["results"]), 5)

        # Maximum page size 100
        resp_max = self.client.get("/api/v1/audit-logs/?page_size=100")
        self.assertEqual(resp_max.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp_max.data["results"]), 25)

    def test_pagination_invalid_and_out_of_range_rejections(self):
        """Tests that invalid page/page_size parameters return 400 and out-of-range page returns 404."""
        self.client.force_authenticate(user=self.owner)

        # Page size greater than 100 returns 400
        resp_gt100 = self.client.get("/api/v1/audit-logs/?page_size=101")
        self.assertEqual(resp_gt100.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("page_size", resp_gt100.data)

        # Zero, negative, and non-integer page-size values return 400
        for invalid_size in ["0", "-1", "-20", "xyz", "1.5"]:
            resp = self.client.get(f"/api/v1/audit-logs/?page_size={invalid_size}")
            self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertIn("page_size", resp.data)

        # Zero, negative, and non-integer page values return 400
        for invalid_page in ["0", "-1", "-5", "abc", "2.5"]:
            resp = self.client.get(f"/api/v1/audit-logs/?page={invalid_page}")
            self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertIn("page", resp.data)

        # Duplicate page and page_size parameters return 400
        resp_dup_page = self.client.get("/api/v1/audit-logs/?page=1&page=2")
        self.assertEqual(resp_dup_page.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("page", resp_dup_page.data)

        resp_dup_size = self.client.get("/api/v1/audit-logs/?page_size=10&page_size=20")
        self.assertEqual(resp_dup_size.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("page_size", resp_dup_size.data)

        # Out-of-range page returns 404
        resp_out_of_range = self.client.get("/api/v1/audit-logs/?page=999")
        self.assertEqual(resp_out_of_range.status_code, status.HTTP_404_NOT_FOUND)

    def test_actor_snapshot_preservation_after_user_update(self):
        """Updating user profile full_name does not change the snapshot stored on AuditLog."""
        self.owner.full_name = "New Name"
        self.owner.save()

        self.client.force_authenticate(user=self.owner)
        resp = self.client.get(f"/api/v1/audit-logs/{self.sample_log.id}/")
        self.assertEqual(resp.data["actor"]["full_name"], "API Owner")

    def test_constant_query_counts_for_list_and_detail(self):
        """Serializing audit list and detail views executes constant queries without N+1."""
        self.client.force_authenticate(user=self.owner)

        # Pre-seed additional logs
        for i in range(5):
            record_audit_event(
                action=AuditAction.PRODUCT_CREATED,
                target_type=AuditTargetType.PRODUCT,
                target_id=uuid.uuid4(),
                target_repr=f"Product {i}",
                actor=self.owner,
                organization_id=None,
                operation_source=AuditOperationSource.INTERACTIVE,
                metadata={"code": f"P{i}", "name": f"Product {i}", "status": "draft"},
            )

        # List query count: 1 count query + 1 data query = 2 queries total
        with self.assertNumQueries(2):
            self.client.get("/api/v1/audit-logs/")

        # Detail query count: 1 query
        with self.assertNumQueries(1):
            self.client.get(f"/api/v1/audit-logs/{self.sample_log.id}/")


class AuditMigrationZeroBackfillTests(TransactionTestCase):
    """Test suite ensuring migration 0001_initial creates schema only without data backfill."""

    def test_migration_0001_initial_contains_no_data_operations(self):
        """Inspects auditlog 0001_initial operations to verify zero RunPython or RunSQL operations exist."""
        app_config = apps.get_app_config("auditlog")
        migration_module = importlib.import_module("apps.auditlog.migrations.0001_initial")
        migration_class = getattr(migration_module, "Migration")

        for op in migration_class.operations:
            op_name = op.__class__.__name__
            self.assertNotIn(
                op_name,
                ("RunPython", "RunSQL"),
                f"Prohibited data operation '{op_name}' detected in initial migration.",
            )

    def test_migration_executor_zero_backfill_and_cleanup(self):
        """Verifies forward migration to 0001_initial results in 0 backfilled records, restoring state in finally."""
        executor = MigrationExecutor(connection)
        target = ("auditlog", "0001_initial")
        source = ("auditlog", None)

        try:
            # Migrate back to None
            executor.migrate([source])
            # Re-read state and migrate forward to target
            executor.loader.build_graph()
            executor.migrate([target])

            # Verify audit table is empty
            AuditLogModel = apps.get_model("auditlog", "AuditLog")
            self.assertEqual(AuditLogModel.objects.count(), 0)
        finally:
            # Restore to latest migration state
            executor.loader.build_graph()
            executor.migrate(executor.loader.graph.leaf_nodes())
