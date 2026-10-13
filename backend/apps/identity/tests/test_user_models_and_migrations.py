"""Stage 1 targeted tests: PlatformUser status/is_active lifecycle,
CheckConstraint enforcement, legacy save() compatibility, and
admin in-transaction last-owner guard.

These tests run against the disposable Django test database only.
No persistent database is touched.
"""

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase, TransactionTestCase
from django.utils import timezone

PlatformUser = get_user_model()


def _make_user(email, status="active", is_platform_owner=False, password=None):
    """Helper: create a PlatformUser in the specified status."""
    user = PlatformUser(
        email=email,
        full_name="Test User",
        status=status,
        is_active=(status == "active"),
        is_platform_owner=is_platform_owner,
    )
    if password:
        user.set_password(password)
    else:
        user.set_unusable_password()
    # Bypass model.save() transition logic for setup — write directly via manager
    PlatformUser.objects.bulk_create([user])
    return PlatformUser.objects.get(email=email)


class TestValidTransitions(TestCase):
    """Prove each valid transition succeeds without a CheckConstraint error."""

    def test_active_to_suspended(self):
        user = _make_user("active_susp@example.com", status="active")
        user.status = "suspended"
        user.is_active = False
        user.save(update_fields=["status", "is_active"])
        user.refresh_from_db()
        self.assertEqual(user.status, "suspended")
        self.assertFalse(user.is_active)

    def test_active_to_disabled(self):
        user = _make_user("active_disabled@example.com", status="active")
        user.status = "disabled"
        user.is_active = False
        user.save(update_fields=["status", "is_active"])
        user.refresh_from_db()
        self.assertEqual(user.status, "disabled")
        self.assertFalse(user.is_active)

    def test_suspended_to_active(self):
        user = _make_user("susp_active@example.com", status="suspended")
        user.status = "active"
        user.is_active = True
        user.save(update_fields=["status", "is_active"])
        user.refresh_from_db()
        self.assertEqual(user.status, "active")
        self.assertTrue(user.is_active)

    def test_suspended_to_disabled(self):
        user = _make_user("susp_disabled@example.com", status="suspended")
        user.status = "disabled"
        user.is_active = False
        user.save(update_fields=["status", "is_active"])
        user.refresh_from_db()
        self.assertEqual(user.status, "disabled")
        self.assertFalse(user.is_active)


class TestTerminalDisabledRejection(TestCase):
    """Prove all transitions out of disabled are rejected."""

    def _disabled_user(self, suffix):
        return _make_user(f"disabled_{suffix}@example.com", status="disabled")

    def test_disabled_full_save_to_active_raises(self):
        user = self._disabled_user("full")
        user.status = "active"
        user.is_active = True
        with self.assertRaises(ValidationError) as ctx:
            user.save()
        self.assertEqual(ctx.exception.code, "USER_DISABLED_TERMINAL")

    def test_disabled_status_only_save_raises(self):
        user = self._disabled_user("status_only")
        user.status = "active"
        with self.assertRaises(ValidationError) as ctx:
            user.save(update_fields=["status"])
        self.assertEqual(ctx.exception.code, "USER_DISABLED_TERMINAL")

    def test_disabled_is_active_legacy_save_raises(self):
        user = self._disabled_user("is_active_legacy")
        user.is_active = True
        with self.assertRaises(ValidationError) as ctx:
            user.save(update_fields=["is_active"])
        self.assertEqual(ctx.exception.code, "USER_DISABLED_TERMINAL")

    def test_disabled_to_suspended_raises(self):
        user = self._disabled_user("to_susp")
        user.status = "suspended"
        user.is_active = False
        with self.assertRaises(ValidationError) as ctx:
            user.save()
        self.assertEqual(ctx.exception.code, "USER_DISABLED_TERMINAL")


class TestLegacyIsActiveSave(TestCase):
    """Prove legacy save(update_fields=['is_active']) persists the correct status."""

    def test_active_user_is_active_false_becomes_disabled(self):
        """Active user set is_active=False → status transitions to disabled."""
        user = _make_user("active_legacy@example.com", status="active")
        user.is_active = False
        user.save(update_fields=["is_active"])
        user.refresh_from_db()
        self.assertEqual(user.status, "disabled")
        self.assertFalse(user.is_active)

    def test_suspended_user_is_active_false_preserves_suspended(self):
        """Suspended user set is_active=False → status stays suspended (not disabled)."""
        user = _make_user("susp_legacy@example.com", status="suspended")
        user.is_active = False
        user.save(update_fields=["is_active"])
        user.refresh_from_db()
        self.assertEqual(user.status, "suspended")
        self.assertFalse(user.is_active)

    def test_suspended_user_is_active_true_becomes_active(self):
        """Suspended user set is_active=True → status transitions to active."""
        user = _make_user("susp_reactivate@example.com", status="suspended")
        user.is_active = True
        user.save(update_fields=["is_active"])
        user.refresh_from_db()
        self.assertEqual(user.status, "active")
        self.assertTrue(user.is_active)


class TestStatusOnlySave(TestCase):
    """Prove status-only save(update_fields=['status']) persists matching is_active."""

    def test_status_suspended_syncs_is_active_false(self):
        user = _make_user("stat_susp@example.com", status="active")
        user.status = "suspended"
        user.save(update_fields=["status"])
        user.refresh_from_db()
        self.assertEqual(user.status, "suspended")
        self.assertFalse(user.is_active)

    def test_status_active_syncs_is_active_true(self):
        user = _make_user("stat_active@example.com", status="suspended")
        user.status = "active"
        user.save(update_fields=["status"])
        user.refresh_from_db()
        self.assertEqual(user.status, "active")
        self.assertTrue(user.is_active)


class TestDatabaseConstraintEnforcement(TransactionTestCase):
    """Prove the DB-level CheckConstraint rejects contradictory rows directly."""

    def test_constraint_rejects_active_status_with_is_active_false(self):
        """Direct DB write violating the sync constraint must fail."""
        user = _make_user("constraint_test@example.com", status="active")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                PlatformUser.objects.filter(pk=user.pk).update(
                    status="active", is_active=False
                )


class TestCreateUserStatusSync(TestCase):
    """Prove create_user correctly syncs status and is_active."""

    def test_create_user_defaults_to_active(self):
        user = PlatformUser.objects.create_user(email="new_active@example.com")
        self.assertEqual(user.status, "active")
        self.assertTrue(user.is_active)

    def test_create_user_is_active_false_sets_disabled(self):
        user = PlatformUser.objects.create_user(
            email="new_inactive@example.com", is_active=False
        )
        self.assertEqual(user.status, "disabled")
        self.assertFalse(user.is_active)

    def test_create_user_status_suspended_syncs_is_active_false(self):
        user = PlatformUser.objects.create_user(
            email="new_suspended@example.com", status="suspended"
        )
        self.assertEqual(user.status, "suspended")
        self.assertFalse(user.is_active)


class TestMigrationBackfill(TestCase):
    """Verify migration 0002 backfill logic: active → active, inactive → disabled (never activated)."""

    def test_migration_0002_defines_backfill_sql(self):
        import importlib
        migration_module = importlib.import_module(
            "apps.identity.migrations.0002_user_status_and_verification"
        )
        migration_class = getattr(migration_module, "Migration")
        run_sql_ops = [
            op for op in migration_class.operations
            if op.__class__.__name__ == "RunSQL"
        ]
        self.assertTrue(len(run_sql_ops) >= 1)
        sql_text = run_sql_ops[0].sql
        self.assertIn("UPDATE platform_users", sql_text)
        self.assertIn("WHEN is_active = TRUE THEN 'active'", sql_text)
        self.assertIn("ELSE 'disabled'", sql_text)

    def test_backfill_sql_execution_sets_correct_status(self):
        """Executing the backfill SQL sets active users to 'active' and inactive users to 'disabled'."""
        from django.db import connection
        active_user = _make_user("legacy_active@example.com", status="active")
        inactive_user = _make_user("legacy_inactive@example.com", status="suspended")

        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE platform_users
                SET status = CASE
                    WHEN is_active = TRUE THEN 'active'
                    ELSE 'disabled'
                END
                WHERE id IN (%s, %s);
                """,
                [str(active_user.id), str(inactive_user.id)],
            )

        active_user.refresh_from_db()
        inactive_user.refresh_from_db()
        self.assertEqual(active_user.status, "active")
        self.assertEqual(inactive_user.status, "disabled")


class TestAdminLastOwnerProtection(TestCase):
    """Verify admin last-active-owner guard and in-transaction concurrent protection."""

    def setUp(self):
        from django.contrib.admin.sites import AdminSite
        from django.test import RequestFactory
        from apps.identity.admin import PlatformUserAdmin

        self.site = AdminSite()
        self.admin = PlatformUserAdmin(PlatformUser, self.site)
        self.rf = RequestFactory()

    def _create_request(self):
        from django.contrib.messages.storage.fallback import FallbackStorage

        request = self.rf.post("/admin/identity/platformuser/")
        request.session = "session"
        request._messages = FallbackStorage(request)
        return request

    def test_admin_form_rejects_deactivating_sole_active_owner(self):
        from apps.identity.admin import PlatformUserAdminForm

        owner = _make_user(
            "sole_owner@example.com", status="active", is_platform_owner=True
        )
        form = PlatformUserAdminForm(
            instance=owner,
            data={
                "email": owner.email,
                "full_name": owner.full_name,
                "status": "suspended",
                "is_active": False,
                "is_platform_owner": True,
            },
        )
        self.assertFalse(form.is_valid())
        self.assertIn(
            "Cannot deactivate or revoke privileges from the final active Platform Owner.",
            form.errors.get("__all__", []),
        )

    def test_admin_form_rejects_revoking_ownership_from_sole_active_owner(self):
        from apps.identity.admin import PlatformUserAdminForm

        owner = _make_user(
            "sole_owner2@example.com", status="active", is_platform_owner=True
        )
        form = PlatformUserAdminForm(
            instance=owner,
            data={
                "email": owner.email,
                "full_name": owner.full_name,
                "status": "active",
                "is_active": True,
                "is_platform_owner": False,
            },
        )
        self.assertFalse(form.is_valid())
        self.assertIn(
            "Cannot deactivate or revoke privileges from the final active Platform Owner.",
            form.errors.get("__all__", []),
        )

    def test_admin_form_allows_deactivating_owner_when_multiple_active_owners_exist(self):
        from apps.identity.admin import PlatformUserAdminForm

        owner1 = _make_user(
            "multi_owner1@example.com", status="active", is_platform_owner=True
        )
        _make_user(
            "multi_owner2@example.com", status="active", is_platform_owner=True
        )
        form = PlatformUserAdminForm(
            instance=owner1,
            data={
                "email": owner1.email,
                "full_name": owner1.full_name,
                "password": owner1.password,
                "status": "suspended",
                "is_active": False,
                "is_platform_owner": True,
            },
        )
        self.assertTrue(form.is_valid(), form.errors)

    def test_admin_save_model_concurrent_protection_aborts_last_owner_deactivation(self):
        """Even if form passed validation, save_model inside locked transaction
        prevents deactivating the final active owner under concurrent race condition."""
        from django.contrib.messages import get_messages

        owner = _make_user(
            "race_owner@example.com", status="active", is_platform_owner=True
        )
        request = self._create_request()

        # Simulate object being modified to suspended
        owner.status = "suspended"
        owner.is_active = False

        self.admin.save_model(request, owner, form=None, change=True)

        # Confirm error message was recorded
        messages_list = [m.message for m in get_messages(request)]
        self.assertTrue(
            any(
                "Cannot deactivate the final active Platform Owner under concurrent edit."
                in msg
                for msg in messages_list
            ),
            f"Expected error message not found in: {messages_list}",
        )

        # Confirm the user in DB was NOT modified to suspended
        owner.refresh_from_db()
        self.assertEqual(owner.status, "active")
        self.assertTrue(owner.is_active)

