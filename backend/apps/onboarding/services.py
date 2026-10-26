"""Tenant Onboarding Domain Services (Phase 3B).

Implements step-driven transitions, resume-from-partial-progress,
conflict validation, and the final transactional provisioning step.
"""

import logging
from typing import Any
import uuid

logger = logging.getLogger(__name__)

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.access_control.models import Role
from apps.access_control.services.provisioning import provision_organization_defaults
from apps.auditlog.models import AuditAction, AuditOperationSource, AuditTargetType
from apps.auditlog.services import record_audit_event
from apps.identity.models import PlatformUser, UserStatus
from apps.notifications.services import send as notification_send
from apps.onboarding.models import (
    OnboardingCaseStatus,
    OnboardingStep,
    TenantOnboardingCase,
    VALID_STEP_TRANSITIONS,
)
from apps.organizations.models import (
    MembershipStatus,
    MembershipType,
    Organization,
    OrganizationMembership,
    OrganizationStatus,
)
from apps.plans.models import PlanPrice, PlanVersion, PlanVersionStatus
from apps.subscriptions.services import create_active_subscription, start_subscription_trial
from apps.entitlements.services import create_or_activate_entitlement
from apps.product_registry.models import Product, ProductStatus
from apps.access_control.models import (
    AccessPermission,
    ConsoleModule,
    OrganizationConsoleModulePolicy,
    OrganizationPermissionCeiling,
)


class OnboardingError(Exception):
    """Base exception for onboarding domain service errors."""
    pass


class InvalidStepTransitionError(OnboardingError):
    """Raised when attempting an unauthorized or invalid step machine transition."""
    pass


class OnboardingValidationError(OnboardingError):
    """Raised when validation of step input parameters fails."""
    pass


class OnboardingCaseConflictError(OnboardingError):
    """Raised when a duplicate organization code conflicts with existing data."""
    pass


@transaction.atomic
def create_onboarding_case(*, actor: Any) -> TenantOnboardingCase:
    """Initialize a new tenant onboarding case in draft status."""
    if not actor or not getattr(actor, "is_platform_owner", False):
        raise OnboardingValidationError("Only Platform Owners can initiate tenant onboarding cases.")

    case = TenantOnboardingCase.objects.create(
        created_by=actor,
        status=OnboardingCaseStatus.IN_PROGRESS,
        current_step=OnboardingStep.ORGANIZATION_PROFILE,
    )
    return case


def transition_case_step(
    *,
    case_id: uuid.UUID | str,
    target_step: str,
    step_data: dict[str, Any],
    actor: Any,
) -> TenantOnboardingCase:
    """Transition onboarding case to the next step, validating and saving partial progress.

    Emits an audit event for every valid step transition.
    """
    clean_id = uuid.UUID(str(case_id))
    case = TenantOnboardingCase.objects.get(id=clean_id)

    # If case has already completed and caller is requesting completion or review,
    # return the completed case directly to guarantee idempotency.
    if case.status == OnboardingCaseStatus.COMPLETED:
        if target_step in (OnboardingStep.COMPLETED, OnboardingStep.REVIEW_CONFIRM):
            return case
        raise OnboardingValidationError(f"Cannot transition case in status '{case.status}'.")

    if case.status not in (OnboardingCaseStatus.IN_PROGRESS, OnboardingCaseStatus.PROVISIONING_FAILED):
        raise OnboardingValidationError(f"Cannot transition case in status '{case.status}'.")

    current_step = case.current_step
    allowed_next = VALID_STEP_TRANSITIONS.get(current_step, set())
    if target_step not in allowed_next:
        raise InvalidStepTransitionError(
            f"Invalid step jump from \x27{current_step}\x27 to \x27{target_step}\x27."
        )

    # Validate and apply step data
    if current_step == OnboardingStep.ORGANIZATION_PROFILE or target_step == OnboardingStep.ADMIN_SETUP:
        if "organization_code" in step_data:
            code = step_data["organization_code"].strip().lower()
            if not code:
                raise OnboardingValidationError("Organization code is required.")
            # Verify code is not already taken by an existing organization
            if Organization.objects.filter(code=code).exists():
                raise OnboardingCaseConflictError(f"Organization code \x27{code}\x27 is already taken.")
            case.organization_code = code

        if "organization_name" in step_data:
            name = step_data["organization_name"].strip()
            if not name:
                raise OnboardingValidationError("Organization name is required.")
            case.organization_name = name

        if "organization_description" in step_data:
            case.organization_description = step_data["organization_description"].strip()

    if current_step == OnboardingStep.ADMIN_SETUP or target_step == OnboardingStep.PLAN_SELECTION:
        if "admin_email" in step_data:
            email = step_data["admin_email"].strip().lower()
            if not email or "@" not in email:
                raise OnboardingValidationError("A valid admin email is required.")
            case.admin_email = email

        if "admin_full_name" in step_data:
            case.admin_full_name = step_data["admin_full_name"].strip()

    if current_step == OnboardingStep.PLAN_SELECTION or target_step in (
        OnboardingStep.PRODUCT_ENTITLEMENTS,
        OnboardingStep.FEATURE_CEILINGS,
        OnboardingStep.REVIEW_CONFIRM,
    ):
        if "plan_version_id" in step_data:
            p_ver_id = step_data["plan_version_id"]
            if p_ver_id:
                try:
                    ver_obj = PlanVersion.objects.get(id=p_ver_id, status=PlanVersionStatus.ACTIVE)
                    case.plan_version = ver_obj
                except PlanVersion.DoesNotExist:
                    raise OnboardingValidationError("Selected plan version does not exist or is not active.")
            else:
                case.plan_version = None

        if "plan_price_id" in step_data:
            p_price_id = step_data["plan_price_id"]
            if p_price_id:
                try:
                    price_obj = PlanPrice.objects.get(id=p_price_id)
                    case.plan_price = price_obj
                except PlanPrice.DoesNotExist:
                    raise OnboardingValidationError("Selected plan price does not exist.")
            else:
                case.plan_price = None

        if "is_trial" in step_data:
            case.is_trial = bool(step_data["is_trial"])

    # Product Entitlements step data
    if "selected_product_ids" in step_data:
        raw_prod_ids = step_data["selected_product_ids"]
        if not isinstance(raw_prod_ids, (list, tuple)):
            raise OnboardingValidationError("selected_product_ids must be a list of product IDs.")
        cleaned_ids = []
        for pid in raw_prod_ids:
            try:
                cleaned_ids.append(str(uuid.UUID(str(pid))))
            except (ValueError, TypeError):
                raise OnboardingValidationError(f"Invalid product UUID: {pid}")
        case.selected_product_ids = cleaned_ids

    # Feature Ceilings step data
    if "feature_ceilings" in step_data:
        raw_ceilings = step_data["feature_ceilings"]
        if not isinstance(raw_ceilings, dict):
            raise OnboardingValidationError("feature_ceilings must be an object/dict.")
        case.feature_ceilings = raw_ceilings

    # Final Step: Execution and Provisioning
    if target_step == OnboardingStep.COMPLETED:
        # Validate minimum requirements
        if not case.organization_code or not case.organization_name:
            raise OnboardingValidationError("Organization details must be completed before provisioning.")
        if not case.admin_email:
            raise OnboardingValidationError("Admin email must be specified before provisioning.")

        # Check for duplicate organization code conflict
        if Organization.objects.filter(code=case.organization_code).exists():
            raise OnboardingCaseConflictError(f"Organization code '{case.organization_code}' is already in use.")

        try:
            with transaction.atomic():
                # 1. Create Organization record in active status
                org = Organization.objects.create(
                    code=case.organization_code,
                    name=case.organization_name,
                    description=case.organization_description,
                    status=OrganizationStatus.ACTIVE,
                    created_by=actor,
                    updated_by=actor,
                )
                case.created_organization = org

                # 2. Provision default access control policies & ceilings
                provision_organization_defaults(organization=org, actor=actor)

                # 2a. Provision Direct Product Entitlements if selected
                if case.selected_product_ids:
                    products = Product.objects.filter(
                        id__in=case.selected_product_ids,
                        status=ProductStatus.ACTIVE,
                    )
                    for prod in products:
                        try:
                            create_or_activate_entitlement(
                                organization=org,
                                product=prod,
                                actor=actor,
                                source="tenant_onboarding_provision",
                            )
                        except Exception as ent_err:
                            logger.warning(
                                "Failed to activate entitlement for org %s product %s: %s",
                                org.code,
                                prod.code,
                                ent_err,
                            )

                # 2b. Apply custom Console Module Policies and Permission Ceilings if provided
                if case.feature_ceilings:
                    # module_policies: { [module_key: string]: boolean }
                    module_policies = case.feature_ceilings.get("modules") or case.feature_ceilings.get("module_policies")
                    if isinstance(module_policies, dict):
                        for mod_key, is_enabled in module_policies.items():
                            mod = ConsoleModule.objects.filter(key=mod_key, is_active=True).first()
                            if mod and not mod.is_core:
                                OrganizationConsoleModulePolicy.objects.update_or_create(
                                    organization=org,
                                    console_module=mod,
                                    defaults={
                                        "is_enabled": bool(is_enabled),
                                        "updated_by": actor,
                                    },
                                )

                    # permission_ceilings: { [permission_key: string]: boolean }
                    perm_ceilings = case.feature_ceilings.get("permissions") or case.feature_ceilings.get("permission_ceilings")
                    if isinstance(perm_ceilings, dict):
                        for perm_key, is_allowed in perm_ceilings.items():
                            perm = AccessPermission.objects.filter(key=perm_key, is_active=True).first()
                            if perm:
                                OrganizationPermissionCeiling.objects.update_or_create(
                                    organization=org,
                                    permission=perm,
                                    defaults={
                                        "is_allowed": bool(is_allowed),
                                        "updated_by": actor,
                                    },
                                )

                # 3. Issue initial Tenant Admin Invitation (Phase 3C)
                admin_role = Role.objects.filter(code="system_tenant_admin", is_system_role=True).first()
                from apps.invitations.services import issue_invitation
                invitation_res = issue_invitation(
                    organization=org,
                    email=case.admin_email,
                    role=admin_role,
                    membership_type=MembershipType.TENANT_ADMIN,
                    product_ids=case.selected_product_ids,
                    lms_console="tenant_console",
                    invited_by=actor,
                )
                if isinstance(invitation_res, (list, tuple)) and len(invitation_res) >= 2:
                    case.initial_admin_activation_token = invitation_res[1]

                # 4. Provision initial Plan / Subscription if selected
                if case.plan_version and case.plan_price:
                    if case.is_trial:
                        start_subscription_trial(
                            organization_id=org.id,
                            plan_version_id=case.plan_version.id,
                            plan_price_id=case.plan_price.id,
                            actor=actor,
                            trial_days=14,
                            change_reason="Tenant onboarding provision",
                        )
                    else:
                        create_active_subscription(
                            organization_id=org.id,
                            plan_version_id=case.plan_version.id,
                            plan_price_id=case.plan_price.id,
                            actor=actor,
                            change_reason="Tenant onboarding provision",
                        )

                case.status = OnboardingCaseStatus.COMPLETED
                case.completed_at = timezone.now()
                case.current_step = target_step
                case.save()
        except Exception as exc:
            case.status = OnboardingCaseStatus.PROVISIONING_FAILED
            case.created_organization = None
            case.save(update_fields=["status", "created_organization", "updated_at"])
            logger.error("Onboarding provisioning failed for case %s: %s", case.id, exc)
            raise OnboardingValidationError(f"Provisioning failed: {exc}") from exc
    else:
        case.current_step = target_step
        case.save()

    # Record Audit Event
    record_audit_event(
        action=AuditAction.ONBOARDING_STEP_TRANSITIONED,
        target_type=AuditTargetType.ONBOARDING_CASE,
        target_id=case.id,
        target_repr=f"Onboarding Case {case.id} [{case.organization_code or 'draft'}]",
        actor=actor,
        organization_id=case.created_organization.id if case.created_organization else None,
        operation_source=AuditOperationSource.INTERACTIVE,
        metadata={
            "case_id": str(case.id),
            "from_step": current_step,
            "to_step": target_step,
            "case_status": case.status,
            "organization_code": case.organization_code or "draft",
            "organization_name": case.organization_name or "draft",
            "admin_email": case.admin_email,
            "plan_version_id": str(case.plan_version.id) if case.plan_version else None,
        },
    )

    return case
