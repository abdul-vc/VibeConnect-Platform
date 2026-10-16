"""Effective Access Computation Service (Phase 2G).

Provides a single authoritative service function to compute the complete effective
access chain for a user within an active tenant organization:
(active user + active organization + active membership + eligible subscription/direct grant
+ plan/module packaging + permission ceiling + user assignment + role/capability).

Reusable by:
- Tenant Admin Console Shell & App Launcher (/api/v1/tenant/home/)
- Future SSO token and launcher endpoints
- Permission and license authorization checks
"""

from typing import Any
import uuid

from django.db.models import Prefetch, Q
from django.utils import timezone
from rest_framework import exceptions

from apps.access_control.constants import CONTEXT_TENANT
from apps.access_control.models import (
    AccessPermission,
    ConsoleModule,
    OrganizationConsoleModulePolicy,
    OrganizationPermissionCeiling,
    RolePermission,
    RoleStatus,
)
from apps.access_control.services.evaluation import evaluate_access
from apps.assignments.constants import AccessState, DenialCode, ModuleState
from apps.assignments.models import AssignmentStatus, UserModuleAssignment, UserProductAssignment
from apps.assignments.services.seat_engine import (
    get_temporally_eligible_subscription,
    resolve_seat_pool,
)
from apps.entitlements.models import EntitlementStatus, OrganizationProductEntitlement
from apps.identity.models import PlatformUser, UserStatus
from apps.organizations.models import (
    MembershipStatus,
    MembershipType,
    Organization,
    OrganizationMembership,
    OrganizationStatus,
)
from apps.product_registry.models import (
    CatalogStatus,
    Product,
    ProductCapability,
    ProductFeature,
    ProductModule,
    ProductStatus,
)
from apps.subscriptions.models import (
    OrganizationSubscription,
    SubscriptionProductEntitlement,
    SubscriptionStatus,
)


def compute_user_tenant_effective_access(
    user: PlatformUser,
    organization: Organization,
) -> dict[str, Any]:
    """Compute and return authoritative effective access for a user in a tenant organization.

    Enforces the entire chain:
    1. Active user verification (authenticated, active status).
    2. Active organization verification.
    3. Membership verification (403 if missing).
    4. Organization entitlement resolution (eligible subscription OR active direct grant).
    5. User product assignment resolution (scoped strictly to organization).
    6. Module, feature, and capability packaging & assignment resolution.
    7. Evaluation of exact 10 access states and denial codes per product.
    8. Tenant Admin console module visibility governed by role, module policy, and permission ceiling.
    9. Seat and usage summary metrics.
    """
    now = timezone.now()

    # 1. Active User Validation
    if not user or not user.is_authenticated or not getattr(user, "is_active", False):
        raise exceptions.NotAuthenticated()

    if getattr(user, "status", None) != UserStatus.ACTIVE:
        raise exceptions.PermissionDenied(
            {"code": "USER_INACTIVE", "detail": "User account is suspended or disabled."}
        )

    # 2. Active Organization Validation
    if organization.status != OrganizationStatus.ACTIVE:
        raise exceptions.PermissionDenied(
            {"code": "ORGANIZATION_NOT_ACTIVE", "detail": "Organization is not active."}
        )

    # 3. Membership Validation (Strict Tenant Scoping)
    membership = (
        OrganizationMembership.objects.filter(
            organization=organization,
            user=user,
        )
        .select_related("role")
        .first()
    )
    if not membership:
        raise exceptions.PermissionDenied(
            {"code": "MEMBERSHIP_INELIGIBLE", "detail": "User has no membership in this organization."}
        )

    is_membership_active = (membership.status == MembershipStatus.ACTIVE)

    # 4. Organization Entitlements Resolution (Subscription + Direct Grants)
    eligible_sub = get_temporally_eligible_subscription(organization.id)

    sub_entitled_prod_ids: set[uuid.UUID] = set()
    sub_entitled_mod_ids: set[uuid.UUID] = set()
    sub_entitled_cap_ids: set[uuid.UUID] = set()

    if eligible_sub:
        sub_entitled_prod_ids = set(
            eligible_sub.product_entitlements.values_list("product_id", flat=True)
        )
        sub_entitled_mod_ids = set(
            eligible_sub.module_entitlements.values_list("module_id", flat=True)
        )
        sub_entitled_cap_ids = set(
            eligible_sub.capability_entitlements.values_list("capability_id", flat=True)
        )

    # Expired subscriptions of the organization (current_period_end < now or status=expired)
    expired_sub_qs = OrganizationSubscription.objects.filter(
        organization=organization
    ).filter(
        Q(status=SubscriptionStatus.EXPIRED) | Q(current_period_end__lt=now)
    )
    if eligible_sub:
        expired_sub_qs = expired_sub_qs.exclude(id=eligible_sub.id)

    expired_sub_prod_ids = set(
        SubscriptionProductEntitlement.objects.filter(
            subscription__in=expired_sub_qs
        ).values_list("product_id", flat=True)
    )

    # Inactive/suspended subscriptions of the organization (excluding expired)
    inactive_sub_qs = OrganizationSubscription.objects.filter(
        organization=organization
    ).exclude(
        id__in=expired_sub_qs.values_list("id", flat=True)
    )
    if eligible_sub:
        inactive_sub_qs = inactive_sub_qs.exclude(id=eligible_sub.id)

    inactive_sub_prod_ids = set(
        SubscriptionProductEntitlement.objects.filter(
            subscription__in=inactive_sub_qs
        ).values_list("product_id", flat=True)
    )

    # Direct Grants (Roadmap rule: active direct grants count even if subscription is suspended or absent)
    direct_grants = OrganizationProductEntitlement.objects.filter(
        organization=organization,
        status=EntitlementStatus.ACTIVE,
    )
    direct_grant_prod_ids = set(direct_grants.values_list("product_id", flat=True))

    all_entitled_prod_ids = sub_entitled_prod_ids | direct_grant_prod_ids

    # 5. User Product Assignments Map (any status for this user & org)
    all_user_assignments = {
        ua.product_id: ua
        for ua in UserProductAssignment.objects.filter(
            organization=organization,
            user=user,
        )
        .select_related("product")
        .prefetch_related(
            Prefetch(
                "module_assignments",
                queryset=UserModuleAssignment.objects.select_related("module"),
            )
        )
    }

    # Candidate products to evaluate across the 10 states:
    candidate_prod_ids = (
        all_entitled_prod_ids
        | inactive_sub_prod_ids
        | expired_sub_prod_ids
        | set(all_user_assignments.keys())
        | set(Product.objects.filter(status=ProductStatus.ACTIVE).values_list("id", flat=True))
    )

    candidate_products = (
        Product.objects.filter(id__in=candidate_prod_ids)
        .prefetch_related(
            Prefetch(
                "modules",
                queryset=ProductModule.objects.prefetch_related(
                    Prefetch(
                        "features",
                        queryset=ProductFeature.objects.filter(status=CatalogStatus.ACTIVE).prefetch_related(
                            Prefetch(
                                "capabilities",
                                queryset=ProductCapability.objects.filter(status=CatalogStatus.ACTIVE),
                            )
                        ),
                    )
                ),
            )
        )
        .order_by("name", "code")
    )

    all_products_data = []
    entitled_products_data = []

    for product in candidate_products:
        assignment = all_user_assignments.get(product.id)

        # Evaluate 10-state access contract
        if not is_membership_active:
            access_state = AccessState.MEMBERSHIP_INACTIVE
            denial_code = DenialCode.MEMBERSHIP_INACTIVE
        elif product.status != ProductStatus.ACTIVE:
            access_state = AccessState.PRODUCT_UNAVAILABLE
            denial_code = DenialCode.PRODUCT_UNAVAILABLE
        elif product.id not in all_entitled_prod_ids:
            if product.id in expired_sub_prod_ids:
                access_state = AccessState.ACCESS_EXPIRED
                denial_code = DenialCode.ACCESS_EXPIRED
            elif product.id in inactive_sub_prod_ids:
                access_state = AccessState.SUBSCRIPTION_INACTIVE
                denial_code = DenialCode.SUBSCRIPTION_INACTIVE
            else:
                access_state = AccessState.ENTITLEMENT_UNAVAILABLE
                denial_code = DenialCode.ENTITLEMENT_UNAVAILABLE
        elif not assignment:
            access_state = AccessState.NOT_ASSIGNED
            denial_code = DenialCode.NOT_ASSIGNED
        elif assignment.status == AssignmentStatus.SUSPENDED:
            access_state = AccessState.ASSIGNMENT_SUSPENDED
            denial_code = DenialCode.ASSIGNMENT_SUSPENDED
        elif assignment.status == AssignmentStatus.REVOKED:
            access_state = AccessState.ASSIGNMENT_REVOKED
            denial_code = DenialCode.ASSIGNMENT_REVOKED
        elif (
            getattr(assignment, "status", None) == "expired"
            or (getattr(assignment, "expires_at", None) and assignment.expires_at < now)
        ):
            access_state = AccessState.ACCESS_EXPIRED
            denial_code = DenialCode.ACCESS_EXPIRED
        elif assignment.status != AssignmentStatus.ACTIVE:
            access_state = AccessState.ASSIGNMENT_SUSPENDED
            denial_code = DenialCode.ASSIGNMENT_SUSPENDED
        else:
            # Check module eligibility
            assigned_enabled_mod_ids = {
                uma.module_id for uma in assignment.module_assignments.all() if uma.is_enabled
            }

            if product.id in direct_grant_prod_ids:
                allowed_mod_ids = assigned_enabled_mod_ids
            else:
                allowed_mod_ids = assigned_enabled_mod_ids & sub_entitled_mod_ids

            product_active_mods = [m for m in product.modules.all() if m.status == CatalogStatus.ACTIVE]
            eligible_mod_ids = {m.id for m in product_active_mods if m.id in allowed_mod_ids}

            if not eligible_mod_ids:
                access_state = AccessState.MODULE_UNAVAILABLE
                denial_code = DenialCode.MODULE_UNAVAILABLE
            else:
                access_state = AccessState.AVAILABLE
                denial_code = None

        # Build module tree & per-module module_state
        assigned_enabled_mod_ids = (
            {uma.module_id for uma in assignment.module_assignments.all() if uma.is_enabled}
            if assignment
            else set()
        )

        if product.id in direct_grant_prod_ids:
            allowed_mod_ids = assigned_enabled_mod_ids
        else:
            allowed_mod_ids = assigned_enabled_mod_ids & sub_entitled_mod_ids

        modules_data = []
        eligible_modules_data = []

        for mod in product.modules.all():
            if mod.status != CatalogStatus.ACTIVE:
                mod_state = ModuleState.UNAVAILABLE
            elif mod.id in allowed_mod_ids:
                mod_state = ModuleState.AVAILABLE
            elif mod.id in assigned_enabled_mod_ids:
                mod_state = ModuleState.UNAVAILABLE
            else:
                mod_state = ModuleState.EXCLUDED

            features_data = []
            for feat in mod.features.all():
                caps_data = []
                for cap in feat.capabilities.all():
                    if product.id not in direct_grant_prod_ids and sub_entitled_cap_ids:
                        if cap.id not in sub_entitled_cap_ids:
                            continue
                    caps_data.append(
                        {
                            "id": str(cap.id),
                            "code": cap.code,
                            "name": cap.name,
                            "description": cap.description,
                            "status": cap.status,
                        }
                    )
                features_data.append(
                    {
                        "id": str(feat.id),
                        "code": feat.code,
                        "name": feat.name,
                        "description": feat.description,
                        "status": feat.status,
                        "capabilities": caps_data,
                    }
                )

            mod_item = {
                "id": str(mod.id),
                "code": mod.code,
                "name": mod.name,
                "description": mod.description,
                "status": mod.status,
                "module_state": mod_state.value if hasattr(mod_state, "value") else str(mod_state),
                "features": features_data,
            }
            modules_data.append(mod_item)
            if mod_state == ModuleState.AVAILABLE:
                eligible_modules_data.append(mod_item)

        prod_item = {
            "id": str(product.id),
            "code": product.code,
            "name": product.name,
            "description": product.description,
            "status": product.status,
            "assignment_id": str(assignment.id) if assignment else None,
            "assigned_at": assignment.assigned_at.isoformat() if assignment and assignment.assigned_at else None,
            "access_state": access_state.value if hasattr(access_state, "value") else str(access_state),
            "denial_code": denial_code.value if (denial_code and hasattr(denial_code, "value")) else denial_code,
            "eligible_modules": eligible_modules_data,
            "modules": modules_data,
        }

        all_products_data.append(prod_item)
        if access_state == AccessState.AVAILABLE:
            entitled_products_data.append(prod_item)

    # 6. Tenant Admin Console Modules Resolution
    # Governed by Role, Organization Console Module Policy, and Permission Ceilings
    console_modules_data = []
    if membership.membership_type == MembershipType.TENANT_ADMIN and membership.role:
        eval_result = evaluate_access(user, CONTEXT_TENANT, organization.id)
        effective_perm_set = set(eval_result.effective_permissions)

        candidate_modules = (
            ConsoleModule.objects.filter(
                target_context="tenant",
                is_active=True,
                key__in=eval_result.allowed_modules,
            )
            .prefetch_related("permissions")
            .order_by("sort_order", "key")
        )

        for mod in candidate_modules:
            mod_perms = [p for p in mod.permissions.all() if p.is_active]
            if mod_perms:
                has_permission = any(p.key in effective_perm_set for p in mod_perms)
                if not has_permission:
                    continue

            console_modules_data.append(
                {
                    "key": mod.key,
                    "display_name": mod.display_name,
                    "description": mod.description,
                    "is_core": mod.is_core,
                }
            )

    # 7. Seat & Usage Summary Metrics
    total_assigned_seats = UserProductAssignment.objects.filter(
        organization=organization,
        status__in=[AssignmentStatus.ACTIVE, AssignmentStatus.SUSPENDED],
    ).count()

    product_seat_metrics = []
    for prod_id in all_entitled_prod_ids:
        p_obj = Product.objects.filter(id=prod_id, status=ProductStatus.ACTIVE).first()
        if not p_obj:
            continue

        if eligible_sub and prod_id in sub_entitled_prod_ids:
            try:
                pool_res = resolve_seat_pool(organization.id, p_obj.id, eligible_sub)
                product_seat_metrics.append(
                    {
                        "product_id": str(p_obj.id),
                        "product_code": p_obj.code,
                        "product_name": p_obj.name,
                        "pool_scope": pool_res.pool_scope,
                        "quota_type": pool_res.limit_type,
                        "total_limit": pool_res.total_limit,
                        "consumed_seats": pool_res.consumed_seats,
                        "available_seats": pool_res.available_seats,
                        "is_capacity_available": pool_res.is_capacity_available,
                    }
                )
                continue
            except Exception:
                pass

        # Direct grant or unconfigured fallback
        consumed = UserProductAssignment.objects.filter(
            organization=organization,
            product=p_obj,
            status__in=[AssignmentStatus.ACTIVE, AssignmentStatus.SUSPENDED],
        ).count()
        product_seat_metrics.append(
            {
                "product_id": str(p_obj.id),
                "product_code": p_obj.code,
                "product_name": p_obj.name,
                "pool_scope": "direct_grant" if prod_id in direct_grant_prod_ids else "unconfigured",
                "quota_type": "unlimited" if prod_id in direct_grant_prod_ids else "unconfigured",
                "total_limit": None,
                "consumed_seats": consumed,
                "available_seats": None,
                "is_capacity_available": True,
            }
        )

    # 8. Assemble Definitive Response Payload
    return {
        "schema_version": "1.0",
        "organization": {
            "id": str(organization.id),
            "code": organization.code,
            "name": organization.name,
            "description": organization.description,
            "status": organization.status,
        },
        "membership": {
            "id": str(membership.id),
            "membership_type": membership.membership_type,
            "status": membership.status,
            "joined_at": membership.joined_at.isoformat() if membership.joined_at else None,
            "role": (
                {
                    "id": str(membership.role.id),
                    "code": membership.role.code,
                    "name": membership.role.name,
                    "is_system_role": membership.role.is_system_role,
                }
                if membership.role
                else None
            ),
        },
        "entitled_products": entitled_products_data,
        "products": all_products_data,
        "console_modules": console_modules_data,
        "seat_summary": {
            "total_assigned_seats": total_assigned_seats,
            "products": product_seat_metrics,
        },
    }
