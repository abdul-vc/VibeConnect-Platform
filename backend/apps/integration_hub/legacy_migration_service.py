"""Legacy LMS Data Migration & Remaining Data Reconciliation Service (Phase 5D Stage 5).

Provides deterministic identity analysis, classification, dry-run planning,
and safe execution of legacy / pre-5C LMS entities into canonical VibeConnect
ExternalTenantMapping and ExternalUserMapping records.

Classification categories:
- SAFE_TO_MIGRATE: Exact tenant/user identity proven, no conflicts, safe to map.
- ALREADY_MAPPED: Correct canonical mapping already established; zero mutation needed.
- INACTIVE_NO_ACTION: Inactive/retired entity or revoked/suspended assignment with no active need.
- AMBIGUOUS_REVIEW: Multiple candidates, contradictory metadata; requires human review.
- CONFLICT_REVIEW: Cross-tenant mismatch, duplicate external IDs, mapping collisions.
- UNSUPPORTED_REMOTE_STATE: Remote state cannot be deterministically validated without read APIs.

Strictly preserves tenant isolation and never makes arbitrary identity guesses.
Reuses canonical provisioning services without introducing duplicate engines.
"""

import logging
from typing import Any, Optional, Union
import uuid

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone

from apps.assignments.models import AssignmentStatus, UserProductAssignment
from apps.entitlements.models import EntitlementStatus, OrganizationProductEntitlement
from apps.integration_hub.models import (
    ConnectorInstance,
    ExternalTenantMapping,
    ExternalUserMapping,
    ExternalUserMappingStatus,
    InstanceStatus,
    IntegrationConnector,
    IntegrationReconciliationIssue,
    IntegrationReconciliationStatus,
    ProvisioningAction,
    ProvisioningJob,
    ProvisioningJobStatus,
)
from apps.integration_hub.provisioning_service import (
    execute_provisioning_job,
    get_or_create_lms_connector_instance,
    provision_tenant_to_lms,
    provision_user_to_lms,
)
from apps.integration_hub.reconciliation_service import (
    LmsReconciliationIssueCode,
    _sanitize_details,
    verify_and_resolve_reconciliation_issue,
)
from apps.organizations.models import (
    MembershipStatus,
    Organization,
    OrganizationMembership,
    OrganizationStatus,
)
from apps.product_registry.models import Product

User = get_user_model()
logger = logging.getLogger(__name__)


class LegacyClassification:
    SAFE_TO_MIGRATE = "SAFE_TO_MIGRATE"
    ALREADY_MAPPED = "ALREADY_MAPPED"
    INACTIVE_NO_ACTION = "INACTIVE_NO_ACTION"
    AMBIGUOUS_REVIEW = "AMBIGUOUS_REVIEW"
    CONFLICT_REVIEW = "CONFLICT_REVIEW"
    UNSUPPORTED_REMOTE_STATE = "UNSUPPORTED_REMOTE_STATE"


def classify_legacy_tenant(
    organization: Organization,
    instance: Optional[ConnectorInstance] = None,
) -> dict[str, Any]:
    """Deterministically classifies an organization for legacy LMS tenant migration.

    Rules:
    1. Check for external ID collisions (CONFLICT_REVIEW).
    2. Check if canonical ExternalTenantMapping already exists (ALREADY_MAPPED).
    3. Check organization lifecycle status: if RETIRED or SUSPENDED with no active LMS need (INACTIVE_NO_ACTION).
    4. Check for active LMS entitlement: if missing or inactive (INACTIVE_NO_ACTION).
    5. Check for ambiguous organization code or missing identifier (AMBIGUOUS_REVIEW).
    6. If active, uniquely identified, entitled, and unmapped -> SAFE_TO_MIGRATE.
    """
    if not instance:
        instance = ConnectorInstance.objects.filter(
            organization=organization,
            connector__code="lms",
        ).first()

    # 1. Check existing mapping
    mapping = ExternalTenantMapping.objects.filter(
        organization=organization,
    ).first()

    if mapping:
        # Check for collision where multiple organizations share this external_tenant_id
        collision = ExternalTenantMapping.objects.filter(
            external_tenant_id=mapping.external_tenant_id,
        ).exclude(organization=organization).exists()

        if collision:
            return {
                "subject_type": "organization",
                "subject_id": str(organization.id),
                "organization_code": organization.code,
                "organization_name": organization.name,
                "classification": LegacyClassification.CONFLICT_REVIEW,
                "action_proposed": "MANUAL_REVIEW",
                "reason": f"External tenant ID '{mapping.external_tenant_id}' is shared with another organization.",
                "evidence": {"mapping_id": str(mapping.id), "external_tenant_id": mapping.external_tenant_id},
                "requires_manual_review": True,
                "will_mutate": False,
            }

        return {
            "subject_type": "organization",
            "subject_id": str(organization.id),
            "organization_code": organization.code,
            "organization_name": organization.name,
            "classification": LegacyClassification.ALREADY_MAPPED,
            "action_proposed": "NONE",
            "reason": "Canonical ExternalTenantMapping already established and verified.",
            "evidence": {"mapping_id": str(mapping.id), "external_tenant_id": mapping.external_tenant_id},
            "requires_manual_review": False,
            "will_mutate": False,
        }

    # 2. Lifecycle Status Check
    if organization.status != OrganizationStatus.ACTIVE:
        return {
            "subject_type": "organization",
            "subject_id": str(organization.id),
            "organization_code": organization.code,
            "organization_name": organization.name,
            "classification": LegacyClassification.INACTIVE_NO_ACTION,
            "action_proposed": "NONE",
            "reason": f"Organization is not active (status='{organization.status}'); no mapping to establish.",
            "evidence": {"status": organization.status},
            "requires_manual_review": False,
            "will_mutate": False,
        }

    # 3. Entitlement Check
    has_active_entitlement = OrganizationProductEntitlement.objects.filter(
        organization=organization,
        product__code="lms",
        status=EntitlementStatus.ACTIVE,
    ).exists()

    if not has_active_entitlement:
        return {
            "subject_type": "organization",
            "subject_id": str(organization.id),
            "organization_code": organization.code,
            "organization_name": organization.name,
            "classification": LegacyClassification.INACTIVE_NO_ACTION,
            "action_proposed": "NONE",
            "reason": "Organization has no active LMS entitlement.",
            "evidence": {"has_active_entitlement": False},
            "requires_manual_review": False,
            "will_mutate": False,
        }

    # 4. Ambiguity Check: Ensure unique and valid organization code
    if not organization.code or not organization.code.strip():
        return {
            "subject_type": "organization",
            "subject_id": str(organization.id),
            "organization_code": "",
            "organization_name": organization.name,
            "classification": LegacyClassification.AMBIGUOUS_REVIEW,
            "action_proposed": "MANUAL_REVIEW",
            "reason": "Organization code is empty or missing; cannot establish deterministic remote identity.",
            "evidence": {"code": organization.code},
            "requires_manual_review": True,
            "will_mutate": False,
        }

    code_duplicate = Organization.objects.filter(code=organization.code).exclude(id=organization.id).exists()
    if code_duplicate:
        return {
            "subject_type": "organization",
            "subject_id": str(organization.id),
            "organization_code": organization.code,
            "organization_name": organization.name,
            "classification": LegacyClassification.AMBIGUOUS_REVIEW,
            "action_proposed": "MANUAL_REVIEW",
            "reason": f"Organization code '{organization.code}' is duplicated across organizations.",
            "evidence": {"code": organization.code},
            "requires_manual_review": True,
            "will_mutate": False,
        }

    # 5. Deterministic SAFE_TO_MIGRATE
    return {
        "subject_type": "organization",
        "subject_id": str(organization.id),
        "organization_code": organization.code,
        "organization_name": organization.name,
        "classification": LegacyClassification.SAFE_TO_MIGRATE,
        "action_proposed": "PROVISION",
        "reason": "Deterministic active organization with valid LMS entitlement and unique code.",
        "evidence": {
            "organization_id": str(organization.id),
            "code": organization.code,
            "status": organization.status,
            "has_active_entitlement": True,
        },
        "requires_manual_review": False,
        "will_mutate": True,
    }


def classify_legacy_user(
    user: Any,
    organization: Organization,
    instance: Optional[ConnectorInstance] = None,
) -> dict[str, Any]:
    """Deterministically classifies a user within an organization for legacy LMS migration.

    Rules:
    1. Tenant scoping: Parent organization must be mapped first (UNSUPPORTED_REMOTE_STATE).
    2. Tenant boundary: User must be an associated member of this organization (CONFLICT_REVIEW).
    3. Existing mapping check: If mapping already exists and active (ALREADY_MAPPED).
    4. Duplicate external user ID check on existing mapping (CONFLICT_REVIEW).
    5. Assignment lifecycle check:
       - If assignment revoked/suspended: (INACTIVE_NO_ACTION) - preserve historical state.
       - If no assignment or entitlement: (INACTIVE_NO_ACTION).
    6. User lifecycle check: If user is inactive without mapping: (INACTIVE_NO_ACTION).
    7. Ambiguity check: Blank email or unresolvable identity: (AMBIGUOUS_REVIEW).
    8. Deterministic active user in mapped tenant with active assignment -> SAFE_TO_MIGRATE.
    """
    if not instance:
        instance = ConnectorInstance.objects.filter(
            organization=organization,
            connector__code="lms",
        ).first()

    # 1. Tenant Dependency Check: Parent tenant must have a valid ExternalTenantMapping
    parent_mapping = ExternalTenantMapping.objects.filter(
        organization=organization,
    ).first()

    if not parent_mapping:
        return {
            "subject_type": "user",
            "subject_id": str(user.id),
            "user_email": getattr(user, "email", ""),
            "organization_id": str(organization.id),
            "organization_code": organization.code,
            "classification": LegacyClassification.UNSUPPORTED_REMOTE_STATE,
            "action_proposed": "MANUAL_REVIEW",
            "reason": f"Parent organization '{organization.code}' has no ExternalTenantMapping; cannot provision users before tenant is mapped.",
            "evidence": {"organization_id": str(organization.id)},
            "requires_manual_review": True,
            "will_mutate": False,
        }

    # 2. Tenant Boundary Check: User must belong to organization
    is_member = OrganizationMembership.objects.filter(
        user=user,
        organization=organization,
    ).exists()
    is_platform_owner = getattr(user, "is_platform_owner", False)

    if not is_member and not is_platform_owner:
        return {
            "subject_type": "user",
            "subject_id": str(user.id),
            "user_email": getattr(user, "email", ""),
            "organization_id": str(organization.id),
            "organization_code": organization.code,
            "classification": LegacyClassification.CONFLICT_REVIEW,
            "action_proposed": "MANUAL_REVIEW",
            "reason": f"User '{getattr(user, 'email', '')}' has no membership in organization '{organization.code}'. Cross-tenant migration rejected.",
            "evidence": {"user_id": str(user.id), "organization_id": str(organization.id)},
            "requires_manual_review": True,
            "will_mutate": False,
        }

    # 3. Check Existing User Mapping
    mapping = ExternalUserMapping.objects.filter(
        organization=organization,
    ).first()

    if mapping:
        # Check for external ID collisions (duplicate external_user_id across users)
        collision = ExternalUserMapping.objects.filter(
            external_user_id=mapping.external_user_id,
        ).exclude(user=user).exists()
        if collision:
            return {
                "subject_type": "user",
                "subject_id": str(user.id),
                "user_email": getattr(user, "email", ""),
                "organization_id": str(organization.id),
                "organization_code": organization.code,
                "classification": LegacyClassification.CONFLICT_REVIEW,
                "action_proposed": "MANUAL_REVIEW",
                "reason": f"External user ID '{mapping.external_user_id}' is shared with another user.",
                "evidence": {"mapping_id": str(mapping.id), "external_user_id": mapping.external_user_id},
                "requires_manual_review": True,
                "will_mutate": False,
            }

        if mapping.status == ExternalUserMappingStatus.ACTIVE:
            return {
                "subject_type": "user",
                "subject_id": str(user.id),
                "user_email": getattr(user, "email", ""),
                "organization_id": str(organization.id),
                "organization_code": organization.code,
                "classification": LegacyClassification.ALREADY_MAPPED,
                "action_proposed": "NONE",
                "reason": "Canonical active ExternalUserMapping already established.",
                "evidence": {"mapping_id": str(mapping.id), "external_user_id": mapping.external_user_id},
                "requires_manual_review": False,
                "will_mutate": False,
            }
        else:
            return {
                "subject_type": "user",
                "subject_id": str(user.id),
                "user_email": getattr(user, "email", ""),
                "organization_id": str(organization.id),
                "organization_code": organization.code,
                "classification": LegacyClassification.INACTIVE_NO_ACTION,
                "action_proposed": "NONE",
                "reason": f"Existing mapping is in status '{mapping.status}'; preserving historical state.",
                "evidence": {"mapping_id": str(mapping.id), "status": mapping.status},
                "requires_manual_review": False,
                "will_mutate": False,
            }

    # 4. Check Assignment & Entitlement
    assignment = UserProductAssignment.objects.filter(
        organization=organization,
        user=user,
        product__code="lms",
    ).first()

    if not assignment:
        return {
            "subject_type": "user",
            "subject_id": str(user.id),
            "user_email": getattr(user, "email", ""),
            "organization_id": str(organization.id),
            "organization_code": organization.code,
            "classification": LegacyClassification.INACTIVE_NO_ACTION,
            "action_proposed": "NONE",
            "reason": "User has no LMS product assignment in this organization.",
            "evidence": {"has_assignment": False},
            "requires_manual_review": False,
            "will_mutate": False,
        }

    if assignment.status in (AssignmentStatus.REVOKED, AssignmentStatus.SUSPENDED):
        return {
            "subject_type": "user",
            "subject_id": str(user.id),
            "user_email": getattr(user, "email", ""),
            "organization_id": str(organization.id),
            "organization_code": organization.code,
            "classification": LegacyClassification.INACTIVE_NO_ACTION,
            "action_proposed": "NONE",
            "reason": f"LMS product assignment is {assignment.status}; no new mapping will be created for suspended/revoked assignments.",
            "evidence": {"assignment_status": assignment.status},
            "requires_manual_review": False,
            "will_mutate": False,
        }

    has_active_entitlement = OrganizationProductEntitlement.objects.filter(
        organization=organization,
        product__code="lms",
        status=EntitlementStatus.ACTIVE,
    ).exists()

    if not has_active_entitlement:
        return {
            "subject_type": "user",
            "subject_id": str(user.id),
            "user_email": getattr(user, "email", ""),
            "organization_id": str(organization.id),
            "organization_code": organization.code,
            "classification": LegacyClassification.INACTIVE_NO_ACTION,
            "action_proposed": "NONE",
            "reason": "Parent organization has no active LMS entitlement.",
            "evidence": {"has_active_entitlement": False},
            "requires_manual_review": False,
            "will_mutate": False,
        }

    # 5. User Lifecycle Check
    if not getattr(user, "is_active", True):
        return {
            "subject_type": "user",
            "subject_id": str(user.id),
            "user_email": getattr(user, "email", ""),
            "organization_id": str(organization.id),
            "organization_code": organization.code,
            "classification": LegacyClassification.INACTIVE_NO_ACTION,
            "action_proposed": "NONE",
            "reason": "Platform user is deactivated/inactive.",
            "evidence": {"is_active": False},
            "requires_manual_review": False,
            "will_mutate": False,
        }

    # 6. Ambiguity Check: Normalized Email
    email = getattr(user, "email", "")
    if not email or not email.strip() or "@" not in email:
        return {
            "subject_type": "user",
            "subject_id": str(user.id),
            "user_email": email,
            "organization_id": str(organization.id),
            "organization_code": organization.code,
            "classification": LegacyClassification.AMBIGUOUS_REVIEW,
            "action_proposed": "MANUAL_REVIEW",
            "reason": "User email is invalid or missing.",
            "evidence": {"email": email},
            "requires_manual_review": True,
            "will_mutate": False,
        }

    # 7. Safe to Migrate
    return {
        "subject_type": "user",
        "subject_id": str(user.id),
        "user_email": email,
        "organization_id": str(organization.id),
        "organization_code": organization.code,
        "classification": LegacyClassification.SAFE_TO_MIGRATE,
        "action_proposed": "PROVISION",
        "reason": "Active user in mapped tenant with verified membership and active assignment.",
        "evidence": {
            "user_id": str(user.id),
            "email": email,
            "organization_id": str(organization.id),
            "assignment_id": str(assignment.id),
        },
        "requires_manual_review": False,
        "will_mutate": True,
    }


def plan_legacy_lms_migration(
    organization: Optional[Organization] = None,
    instance: Optional[ConnectorInstance] = None,
) -> dict[str, Any]:
    """Generates a complete, deterministic, zero-mutation legacy migration plan.

    Audits all relevant organizations and user assignments, classifies each subject,
    and returns categorized records and a dedicated manual-review dataset.
    """
    records: list[dict[str, Any]] = []

    org_qs = Organization.objects.all()
    if organization:
        org_qs = org_qs.filter(id=organization.id)

    # 1. Audit Organizations
    for org in org_qs:
        inst = instance if (instance and instance.organization_id == org.id) else None
        rec = classify_legacy_tenant(org, instance=inst)
        records.append(rec)

    # 2. Audit Users with LMS assignments or memberships in target orgs
    assignments = UserProductAssignment.objects.filter(
        product__code="lms",
        organization__in=org_qs,
    ).select_related("user", "organization")

    processed_pairs: set[tuple[uuid.UUID, uuid.UUID]] = set()

    for a in assignments:
        pair = (a.user_id, a.organization_id)
        if pair in processed_pairs:
            continue
        processed_pairs.add(pair)

        inst = instance if (instance and instance.organization_id == a.organization_id) else None
        u_rec = classify_legacy_user(a.user, a.organization, instance=inst)
        records.append(u_rec)

    # Also check unassigned users who have existing ExternalUserMapping (to verify integrity)
    existing_mappings = ExternalUserMapping.objects.filter(
        organization__in=org_qs,
    ).select_related("user", "organization")

    for um in existing_mappings:
        pair = (um.user_id, um.organization_id)
        if pair in processed_pairs:
            continue
        processed_pairs.add(pair)

        inst = instance if (instance and instance.organization_id == um.organization_id) else None
        u_rec = classify_legacy_user(um.user, um.organization, instance=inst)
        records.append(u_rec)

    # Calculate counts by classification category
    counts: dict[str, int] = {
        LegacyClassification.SAFE_TO_MIGRATE: 0,
        LegacyClassification.ALREADY_MAPPED: 0,
        LegacyClassification.INACTIVE_NO_ACTION: 0,
        LegacyClassification.AMBIGUOUS_REVIEW: 0,
        LegacyClassification.CONFLICT_REVIEW: 0,
        LegacyClassification.UNSUPPORTED_REMOTE_STATE: 0,
        "total": len(records),
    }

    manual_review_dataset: list[dict[str, Any]] = []

    for r in records:
        c = r["classification"]
        counts[c] = counts.get(c, 0) + 1
        if r.get("requires_manual_review"):
            manual_review_dataset.append(r)

    return {
        "dry_run": True,
        "timestamp": timezone.now().isoformat(),
        "counts": counts,
        "records": records,
        "manual_review_dataset": manual_review_dataset,
    }


def execute_legacy_lms_migration(
    plan: Optional[dict[str, Any]] = None,
    organization: Optional[Organization] = None,
    instance: Optional[ConnectorInstance] = None,
    client: Optional[Any] = None,
) -> dict[str, Any]:
    """Executes migration for records classified SAFE_TO_MIGRATE.

    - Uses canonical provisioning services without duplicate engines.
    - Resolves correlated reconciliation issues upon verified mapping creation.
    - Emits a sanitized, secret-free audit trail.
    - Idempotent and restart-safe.
    """
    if plan is None:
        plan = plan_legacy_lms_migration(organization=organization, instance=instance)

    audit_trail: list[dict[str, Any]] = []
    migrated_count = 0
    failed_count = 0

    safe_records = [r for r in plan["records"] if r["classification"] == LegacyClassification.SAFE_TO_MIGRATE]

    # Process Tenants first (to ensure user dependency)
    tenant_records = [r for r in safe_records if r["subject_type"] == "organization"]
    user_records = [r for r in safe_records if r["subject_type"] == "user"]

    for rec in tenant_records + user_records:
        start_time = timezone.now()
        subject_id = rec["subject_id"]
        subject_type = rec["subject_type"]

        try:
            if subject_type == "organization":
                org = Organization.objects.get(id=subject_id)
                inst = instance or get_or_create_lms_connector_instance(org)
                
                # Execute canonical tenant provisioning
                result = provision_tenant_to_lms(
                    organization=org,
                    instance=inst,
                    client=client,
                )

                mapping = ExternalTenantMapping.objects.get(
                    instance=inst,
                    organization=org,
                )

                # Check if an OPEN reconciliation issue exists for this tenant
                rec_issue = IntegrationReconciliationIssue.objects.filter(
                    instance=inst,
                    issue_code=LmsReconciliationIssueCode.MISSING_TENANT_MAPPING,
                    subject_id=str(org.id),
                    status=IntegrationReconciliationStatus.OPEN,
                ).first()

                if rec_issue:
                    rec_issue.status = IntegrationReconciliationStatus.RESOLVED
                    rec_issue.resolved_at = timezone.now()
                    rec_issue.resolution_notes = f"Auto-resolved by legacy migration: ExternalTenantMapping established (external_tenant_id={mapping.external_tenant_id})."
                    rec_issue.save(update_fields=["status", "resolved_at", "resolution_notes"])

                audit_entry = {
                    "classification": LegacyClassification.SAFE_TO_MIGRATE,
                    "subject_type": "organization",
                    "subject_id": str(org.id),
                    "organization_code": org.code,
                    "external_tenant_id": str(mapping.external_tenant_id),
                    "action_taken": "PROVISION_TENANT",
                    "result": "SUCCESS",
                    "timestamp": start_time.isoformat(),
                    "reason": rec["reason"],
                    "sanitized_evidence": _sanitize_details(rec.get("evidence", {})),
                }
                audit_trail.append(audit_entry)
                migrated_count += 1

            elif subject_type == "user":
                target_user = User.objects.get(id=subject_id)
                target_org = Organization.objects.get(id=rec["organization_id"])
                inst = instance or get_or_create_lms_connector_instance(target_org)

                # Execute canonical user provisioning
                result = provision_user_to_lms(
                    user=target_user,
                    organization=target_org,
                    is_active=True,
                    instance=inst,
                    client=client,
                )

                mapping = ExternalUserMapping.objects.get(
                    instance=inst,
                    user=target_user,
                    organization=target_org,
                )

                # Check if an OPEN reconciliation issue exists for this user
                rec_issue = IntegrationReconciliationIssue.objects.filter(
                    instance=inst,
                    issue_code=LmsReconciliationIssueCode.MISSING_USER_MAPPING,
                    subject_id=str(target_user.id),
                    status=IntegrationReconciliationStatus.OPEN,
                ).first()

                if rec_issue:
                    rec_issue.status = IntegrationReconciliationStatus.RESOLVED
                    rec_issue.resolved_at = timezone.now()
                    rec_issue.resolution_notes = f"Auto-resolved by legacy migration: ExternalUserMapping established (external_user_id={mapping.external_user_id})."
                    rec_issue.save(update_fields=["status", "resolved_at", "resolution_notes"])

                audit_entry = {
                    "classification": LegacyClassification.SAFE_TO_MIGRATE,
                    "subject_type": "user",
                    "subject_id": str(target_user.id),
                    "user_email": getattr(target_user, "email", ""),
                    "organization_id": str(target_org.id),
                    "organization_code": target_org.code,
                    "external_user_id": str(mapping.external_user_id),
                    "action_taken": "PROVISION_USER",
                    "result": "SUCCESS",
                    "timestamp": start_time.isoformat(),
                    "reason": rec["reason"],
                    "sanitized_evidence": _sanitize_details(rec.get("evidence", {})),
                }
                audit_trail.append(audit_entry)
                migrated_count += 1

        except Exception as exc:
            logger.error(f"Legacy migration failed for {subject_type} {subject_id}: {exc}")
            audit_entry = {
                "classification": LegacyClassification.SAFE_TO_MIGRATE,
                "subject_type": subject_type,
                "subject_id": str(subject_id),
                "action_taken": f"PROVISION_{subject_type.upper()}",
                "result": "FAILED",
                "error": str(exc),
                "timestamp": start_time.isoformat(),
                "reason": rec["reason"],
            }
            audit_trail.append(audit_entry)
            failed_count += 1

    return {
        "dry_run": False,
        "timestamp": timezone.now().isoformat(),
        "migrated_count": migrated_count,
        "failed_count": failed_count,
        "audit_trail": audit_trail,
        "manual_review_dataset": plan["manual_review_dataset"],
    }
