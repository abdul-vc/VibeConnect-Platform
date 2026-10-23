"""Idempotent setup command for Digielves demonstration tenant and Sales Team member.

Configures:
1. Digielves organization: code='digielves', name='Digielves', status=ACTIVE
2. Entitlements: active OrganizationProductEntitlement for all registered active products
   (quiz, crm, divineconnect, workhub, lms)
3. Tenant Admin membership and active product assignments
4. Sales Team member (display name 'Sales Team', role=Member) with active product assignments
   and enabled module assignments for all supported demonstration products.
5. Also idempotently ensures boss-demo-org has matching full entitlements and assignments.
"""

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from django.contrib.auth import get_user_model

from apps.organizations.models import (
    Organization,
    OrganizationMembership,
    OrganizationStatus,
    MembershipType,
    MembershipStatus,
)
from apps.access_control.models import Role
from apps.entitlements.models import (
    OrganizationProductEntitlement,
    EntitlementStatus,
)
from apps.assignments.models import (
    UserProductAssignment,
    UserModuleAssignment,
    AssignmentStatus,
)
from apps.product_registry.models import (
    Product,
    ProductStatus,
    CatalogStatus,
)

User = get_user_model()


class Command(BaseCommand):
    help = "Idempotently configure Digielves demonstration tenant, Sales Team member, and product access."

    def handle(self, *args, **options):
        self.stdout.write("Configuring Digielves tenant and Sales Team demonstration setup...")

        system_user = (
            User.objects.filter(is_superuser=True).first()
            or User.objects.filter(is_staff=True).first()
            or User.objects.first()
        )

        admin_role = (
            Role.objects.filter(name="Tenant Administrator").first()
            or Role.objects.first()
        )

        with transaction.atomic():
            # 1. Ensure Digielves organization
            org, org_created = Organization.objects.get_or_create(
                code="digielves",
                defaults={
                    "name": "Digielves",
                    "description": "Internal demonstration and sales tenant for Digielves.",
                    "status": OrganizationStatus.ACTIVE,
                    "created_by": system_user,
                    "updated_by": system_user,
                },
            )
            if not org_created and org.status != OrganizationStatus.ACTIVE:
                org.status = OrganizationStatus.ACTIVE
                org.save(update_fields=["status"])

            self.stdout.write(f"Organization Digielves: {org.id} (code={org.code}, active={org.status})")

            # 2. Candidate demonstration products
            target_product_codes = ["quiz", "crm", "divineconnect", "workhub", "lms"]
            products = list(
                Product.objects.filter(
                    code__in=target_product_codes,
                    status=ProductStatus.ACTIVE,
                ).prefetch_related("modules")
            )
            self.stdout.write(f"Found {len(products)} active products to entitle: {[p.code for p in products]}")

            # Also include boss-demo-org to ensure complete compatibility
            demo_orgs = [org]
            boss_demo = Organization.objects.filter(code="boss-demo-org").first()
            if boss_demo:
                demo_orgs.append(boss_demo)

            for target_org in demo_orgs:
                # 3. Entitlements for all products
                for product in products:
                    ent, ent_created = OrganizationProductEntitlement.objects.get_or_create(
                        organization=target_org,
                        product=product,
                        defaults={
                            "status": EntitlementStatus.ACTIVE,
                            "created_by": system_user,
                            "updated_by": system_user,
                        },
                    )
                    if not ent_created and ent.status != EntitlementStatus.ACTIVE:
                        ent.status = EntitlementStatus.ACTIVE
                        ent.save(update_fields=["status"])

            # 4. Ensure Tenant Admin user
            admin_user = (
                User.objects.filter(email="demo.tenant.admin@demotenant.test").first()
                or User.objects.filter(email="admin@digielves.test").first()
            )
            if not admin_user:
                admin_user = User.objects.create_user(
                    email="demo.tenant.admin@demotenant.test",
                    full_name="Demo Tenant Administrator",
                    is_active=True,
                )

            # 5. Ensure Sales Team member user
            sales_user = (
                User.objects.filter(email="demo.member@demotenant.test").first()
                or User.objects.filter(email="sales.team@digielves.test").first()
            )
            if not sales_user:
                sales_user = User.objects.create_user(
                    email="demo.member@demotenant.test",
                    full_name="Sales Team",
                    is_active=True,
                )
            else:
                sales_user.full_name = "Sales Team"
                sales_user.save(update_fields=["full_name"])

            # Also create dedicated sales.team@digielves.test if not present
            dedicated_sales = User.objects.filter(email="sales.team@digielves.test").first()
            if not dedicated_sales:
                dedicated_sales = User.objects.create_user(
                    email="sales.team@digielves.test",
                    full_name="Sales Team",
                    is_active=True,
                )

            target_users_and_roles = [
                (admin_user, MembershipType.TENANT_ADMIN),
                (sales_user, MembershipType.MEMBER),
                (dedicated_sales, MembershipType.MEMBER),
            ]

            now = timezone.now()
            for target_org in demo_orgs:
                for target_user, role_type in target_users_and_roles:
                    # Role must be set if TENANT_ADMIN, None if MEMBER
                    assigned_role = admin_role if role_type == MembershipType.TENANT_ADMIN else None

                    # Organization Membership
                    mship, m_created = OrganizationMembership.objects.get_or_create(
                        organization=target_org,
                        user=target_user,
                        defaults={
                            "membership_type": role_type,
                            "role": assigned_role,
                            "status": MembershipStatus.ACTIVE,
                            "joined_at": now,
                        },
                    )
                    if not m_created:
                        fields_to_update = []
                        if mship.membership_type != role_type:
                            mship.membership_type = role_type
                            fields_to_update.append("membership_type")
                        if mship.role != assigned_role:
                            mship.role = assigned_role
                            fields_to_update.append("role")
                        if mship.status != MembershipStatus.ACTIVE:
                            mship.status = MembershipStatus.ACTIVE
                            fields_to_update.append("status")
                        if fields_to_update:
                            mship.save(update_fields=fields_to_update)

                    # Product and Module Assignments
                    for product in products:
                        assign, a_created = UserProductAssignment.objects.get_or_create(
                            organization=target_org,
                            user=target_user,
                            product=product,
                            defaults={
                                "membership": mship,
                                "status": AssignmentStatus.ACTIVE,
                                "created_by": system_user,
                                "updated_by": system_user,
                            },
                        )
                        if not a_created:
                            fields_to_update = []
                            if assign.membership != mship:
                                assign.membership = mship
                                fields_to_update.append("membership")
                            if assign.status != AssignmentStatus.ACTIVE:
                                assign.status = AssignmentStatus.ACTIVE
                                fields_to_update.append("status")
                            if fields_to_update:
                                assign.save(update_fields=fields_to_update)

                        # Enable all active modules for this assignment
                        for mod in product.modules.filter(status=CatalogStatus.ACTIVE):
                            uma, u_created = UserModuleAssignment.objects.get_or_create(
                                assignment=assign,
                                module=mod,
                                defaults={
                                    "is_enabled": True,
                                },
                            )
                            if not u_created and not uma.is_enabled:
                                uma.is_enabled = True
                                uma.save(update_fields=["is_enabled"])

            self.stdout.write(self.style.SUCCESS("Digielves and Sales Team setup completed successfully."))
