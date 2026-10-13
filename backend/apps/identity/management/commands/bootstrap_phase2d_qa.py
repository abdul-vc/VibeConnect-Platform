"""Management command to bootstrap Phase 2D QA accounts and memberships.

Restricted exclusively to:
- Persistent manual QA database 'vibeconnect_phase2c_test' during Stage 7 manual QA.
- Disposable test database during automated test runs with --allow-test-database.

Zero password exposure in CLI arguments or stdout.
Preserves auth_provider='local' and durable ownership provenance via external_subject_id.
"""

import getpass
import os
import sys

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from django.utils import timezone

from apps.identity.models import UserStatus
from apps.organizations.models import (
    MembershipStatus,
    MembershipType,
    Organization,
    OrganizationMembership,
    OrganizationStatus,
)

PlatformUser = get_user_model()

TARGET_ACCOUNTS = [
    {
        "email": "phase2d.tenant.admin@vibeconnect.internal",
        "full_name": "Phase 2D Single Tenant Admin",
    },
    {
        "email": "phase2d.multi.admin@vibeconnect.internal",
        "full_name": "Phase 2D Multi Tenant Admin",
    },
    {
        "email": "phase2d.regular.member@vibeconnect.internal",
        "full_name": "Phase 2D Regular Member",
    },
    {
        "email": "phase2e.viewonly.admin@vibeconnect.internal",
        "full_name": "Phase 2E View Only Admin",
    },
]


def _sync_membership(user, org, membership_type: str, now) -> None:
    """Create or update membership to ensure desired status and role."""
    role = None
    if membership_type == MembershipType.TENANT_ADMIN:
        from apps.access_control.models import Role

        role, _ = Role.objects.get_or_create(
            organization=None,
            code="system_tenant_admin",
            defaults={
                "name": "Tenant Administrator",
                "description": "System-defined full tenant administrator role.",
                "is_system_role": True,
                "status": "active",
            },
        )

    membership = OrganizationMembership.objects.filter(user=user, organization=org).first()
    if not membership:
        OrganizationMembership.objects.create(
            user=user,
            organization=org,
            membership_type=membership_type,
            status=MembershipStatus.ACTIVE,
            role=role,
            joined_at=now,
            ended_at=None,
        )
    else:
        membership.membership_type = membership_type
        membership.status = MembershipStatus.ACTIVE
        membership.role = role
        membership.ended_at = None
        membership.save(update_fields=["membership_type", "status", "role", "ended_at", "updated_at"])


class Command(BaseCommand):
    help = "Bootstrap Phase 2D QA test accounts and organization memberships."

    def add_arguments(self, parser):
        parser.add_argument(
            "--allow-test-database",
            action="store_true",
            default=False,
            help="Allow execution in an active disposable test database during automated test runs.",
        )

    def handle(self, *args, **options):
        # 1. Database Guard Validation
        with connection.cursor() as cursor:
            cursor.execute("SELECT current_database();")
            current_db = cursor.fetchone()[0]

        allow_test_db = options.get("allow_test_database", False)
        if allow_test_db:
            is_testing = getattr(settings, "IS_TESTING", False) or hasattr(connection.creation, "_get_test_db_name")
            if not is_testing:
                raise CommandError("Flag --allow-test-database is only permitted during active automated test runs.")
            try:
                test_override = connection.settings_dict.get("TEST", {}).get("NAME")
                expected_test_db = test_override or connection.settings_dict.get("NAME")
            except Exception as exc:
                raise CommandError(f"Unable to determine expected test database name: {exc}")
            if not (current_db == expected_test_db and (current_db.startswith("test_") or bool(test_override))):
                raise CommandError(
                    f"Database guard violation: test database '{current_db}' does not match expected '{expected_test_db}'."
                )
        else:
            if current_db != "vibeconnect_phase2c_test":
                raise CommandError(
                    f"Database guard violation: refusing to execute on database '{current_db}'. "
                    "QA bootstrap is strictly restricted to 'vibeconnect_phase2c_test'."
                )

        # 2. Secure Password Resolution (Never from CLI arguments)
        raw_password = os.environ.get("PHASE2D_QA_BOOTSTRAP_PASSWORD", "").strip()
        if not raw_password:
            if sys.stdin.isatty():
                raw_password = getpass.getpass("Enter password for Phase 2D QA accounts: ")
            else:
                raise CommandError(
                    "Password must be provided via interactive prompt or PHASE2D_QA_BOOTSTRAP_PASSWORD environment variable."
                )
        if not raw_password or len(raw_password.strip()) < 8:
            raise CommandError("Password must be at least 8 characters.")
        password = raw_password.strip()

        # 3. Durable Provenance Check & Account/Membership Setup
        with transaction.atomic():
            owner = PlatformUser.objects.filter(is_platform_owner=True, status=UserStatus.ACTIVE).first()
            if not owner:
                owner = PlatformUser.objects.filter(is_platform_owner=True).first()
            if not owner:
                owner = PlatformUser.objects.create(
                    email="system.owner@vibeconnect.internal",
                    full_name="System Owner",
                    status=UserStatus.ACTIVE,
                    is_active=True,
                    is_platform_owner=True,
                    auth_provider="local",
                    external_subject_id="vibeconnect:system:owner",
                )
                owner.set_unusable_password()
                owner.save()

            org_alpha, _ = Organization.objects.get_or_create(
                code="qa-org-alpha",
                defaults={
                    "name": "QA Organization Alpha",
                    "status": OrganizationStatus.ACTIVE,
                    "created_by": owner,
                    "updated_by": owner,
                },
            )
            if org_alpha.status != OrganizationStatus.ACTIVE:
                org_alpha.status = OrganizationStatus.ACTIVE
                org_alpha.save(update_fields=["status"])

            org_beta, _ = Organization.objects.get_or_create(
                code="qa-org-beta",
                defaults={
                    "name": "QA Organization Beta",
                    "status": OrganizationStatus.ACTIVE,
                    "created_by": owner,
                    "updated_by": owner,
                },
            )
            if org_beta.status != OrganizationStatus.ACTIVE:
                org_beta.status = OrganizationStatus.ACTIVE
                org_beta.save(update_fields=["status"])

            users = {}
            for account in TARGET_ACCOUNTS:
                email = account["email"]
                expected_subject_id = f"vibeconnect:qa_bootstrap:{email}"
                existing = PlatformUser.objects.filter(email__iexact=email).first()
                if existing:
                    if (
                        existing.external_subject_id != expected_subject_id
                        or existing.auth_provider != "local"
                    ):
                        raise CommandError(
                            f"Account collision: user '{email}' exists but lacks valid QA bootstrap provenance. "
                            "Refusing to alter account."
                        )
                    existing.status = UserStatus.ACTIVE
                    existing.is_active = True
                    existing.set_password(password)
                    existing.save()
                    users[email] = existing
                else:
                    user = PlatformUser(
                        email=email,
                        full_name=account["full_name"],
                        status=UserStatus.ACTIVE,
                        is_active=True,
                        auth_provider="local",
                        external_subject_id=expected_subject_id,
                        is_platform_owner=False,
                        is_staff=False,
                        is_superuser=False,
                    )
                    user.set_password(password)
                    user.save()
                    users[email] = user

            now = timezone.now()

            # 1. Single Tenant Admin -> tenant_admin in org_alpha only
            u_single = users["phase2d.tenant.admin@vibeconnect.internal"]
            _sync_membership(u_single, org_alpha, MembershipType.TENANT_ADMIN, now)
            OrganizationMembership.objects.filter(user=u_single, organization=org_beta).delete()

            # 2. Multi Tenant Admin -> tenant_admin in org_alpha and org_beta
            u_multi = users["phase2d.multi.admin@vibeconnect.internal"]
            _sync_membership(u_multi, org_alpha, MembershipType.TENANT_ADMIN, now)
            _sync_membership(u_multi, org_beta, MembershipType.TENANT_ADMIN, now)

            # 3. Regular Member -> member in org_alpha, no tenant_admin
            u_member = users["phase2d.regular.member@vibeconnect.internal"]
            _sync_membership(u_member, org_alpha, MembershipType.MEMBER, now)
            OrganizationMembership.objects.filter(user=u_member, organization=org_beta).delete()

            # 4. View-Only Tenant Admin -> tenant_admin in org_alpha with view_only_admin role
            from apps.access_control.models import (
                AccessPermission,
                ConsoleModule,
                OrganizationConsoleModulePolicy,
                OrganizationPermissionCeiling,
                Role,
                RolePermission,
            )

            view_role, _ = Role.objects.get_or_create(
                organization=org_alpha,
                code="view_only_admin",
                defaults={
                    "name": "View Only Administrator",
                    "description": "Tenant administrator with read-only access to roles and permissions.",
                    "is_system_role": False,
                    "status": "active",
                    "created_by": owner,
                    "updated_by": owner,
                },
            )
            p_view = AccessPermission.objects.filter(key="roles.view").first()
            if p_view:
                RolePermission.objects.get_or_create(role=view_role, permission=p_view)

            u_view = users["phase2e.viewonly.admin@vibeconnect.internal"]
            mem_view = OrganizationMembership.objects.filter(user=u_view, organization=org_alpha).first()
            if not mem_view:
                OrganizationMembership.objects.create(
                    user=u_view,
                    organization=org_alpha,
                    membership_type=MembershipType.TENANT_ADMIN,
                    status=MembershipStatus.ACTIVE,
                    role=view_role,
                    joined_at=now,
                    ended_at=None,
                )
            else:
                mem_view.membership_type = MembershipType.TENANT_ADMIN
                mem_view.status = MembershipStatus.ACTIVE
                mem_view.role = view_role
                mem_view.ended_at = None
                mem_view.save(update_fields=["membership_type", "status", "role", "ended_at", "updated_at"])
            OrganizationMembership.objects.filter(user=u_view, organization=org_beta).delete()

            # 5. Ensure module policies and permission ceilings exist for QA orgs
            for org in (org_alpha, org_beta):
                for mod_key in ("tenant_landing", "tenant_roles"):
                    mod = ConsoleModule.objects.filter(key=mod_key).first()
                    if mod:
                        OrganizationConsoleModulePolicy.objects.get_or_create(
                            organization=org,
                            console_module=mod,
                            defaults={"is_enabled": True},
                        )
                for perm in AccessPermission.objects.all():
                    OrganizationPermissionCeiling.objects.get_or_create(
                        organization=org,
                        permission=perm,
                        defaults={"is_allowed": True},
                    )

        self.stdout.write(self.style.SUCCESS("Successfully bootstrapped Phase 2D/2E QA accounts, roles, and memberships."))
