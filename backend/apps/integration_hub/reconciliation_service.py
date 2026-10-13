"""LMS Identity & Mapping Reconciliation Service (Phase 5D — Stage 3).

Provides:
- Read-only deterministic detection of LMS identity and mapping discrepancies.
- Strictly adheres to the Phase 5D Stage 2 frozen contract and user precedence hierarchy.
- Zero outbound mutating LMS calls during ordinary reconciliation scans.
- Deduplication via unique_open_reconciliation_issue invariant.
- Diagnostic payloads sanitized to ensure zero secrets or tokens are stored.
"""

import logging
from typing import Any, Optional, Union
import uuid

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Count, Q
from django.db.models.functions import Lower
from django.utils import timezone

from apps.assignments.models import AssignmentStatus, UserProductAssignment
from apps.entitlements.models import EntitlementStatus, OrganizationProductEntitlement
from apps.identity.models import UserStatus
from apps.integration_hub.models import (
    ConnectorInstance,
    ExternalTenantMapping,
    ExternalUserMapping,
    ExternalUserMappingStatus,
    IntegrationReconciliationIssue,
    IntegrationReconciliationStatus,
    ProvisioningAction,
    ProvisioningJob,
    ProvisioningJobStatus,
)
from apps.organizations.models import Organization, OrganizationMembership, OrganizationStatus
from apps.product_registry.models import Product

logger = logging.getLogger(__name__)

User = get_user_model()


class LmsReconciliationIssueCode:
    # Tenant anomalies
    MISSING_TENANT_MAPPING = "MISSING_TENANT_MAPPING"
    ORGANIZATION_NOT_ACTIVE = "ORGANIZATION_NOT_ACTIVE"
    DUPLICATE_EXTERNAL_TENANT = "DUPLICATE_EXTERNAL_TENANT"

    # User anomalies
    USER_INACTIVE_OR_SUSPENDED = "USER_INACTIVE_OR_SUSPENDED"
    ASSIGNMENT_WITHOUT_ENTITLEMENT = "ASSIGNMENT_WITHOUT_ENTITLEMENT"
    CROSS_TENANT_MAPPING_MISMATCH = "CROSS_TENANT_MAPPING_MISMATCH"
    STALE_USER_MAPPING = "STALE_USER_MAPPING"
    LOCAL_USER_MAPPING_DRIFT = "LOCAL_USER_MAPPING_DRIFT"
    MISSING_USER_MAPPING = "MISSING_USER_MAPPING"
    DUPLICATE_EXTERNAL_USER = "DUPLICATE_EXTERNAL_USER"

    # Integrity & identity anomalies
    INCONSISTENT_MAPPED_IDENTITY = "INCONSISTENT_MAPPED_IDENTITY"
    ORPHAN_MAPPING_LOCAL_ENTITY_MISSING = "ORPHAN_MAPPING_LOCAL_ENTITY_MISSING"
    REMOTE_RECORD_MISSING = "REMOTE_RECORD_MISSING"
    PROFILE_NAME_DRIFT = "PROFILE_NAME_DRIFT"


_DISALLOWED_DETAIL_KEYS = {
    "secret",
    "token",
    "password",
    "authorization",
    "code_hash",
    "client_secret",
    "credential_ref",
}


def _sanitize_details(details: dict[str, Any]) -> dict[str, Any]:
    """Strips any sensitive or secret fields from issue diagnostic details."""
    clean: dict[str, Any] = {}
    for k, v in details.items():
        if any(bad in k.lower() for bad in _DISALLOWED_DETAIL_KEYS):
            continue
        clean[k] = v
    return clean


def _record_or_reuse_issue(
    instance: ConnectorInstance,
    issue_code: str,
    subject_type: str,
    subject_id: str,
    details: dict[str, Any],
) -> IntegrationReconciliationIssue:
    """Idempotently creates or reuses an existing OPEN reconciliation issue."""
    existing = IntegrationReconciliationIssue.objects.filter(
        instance=instance,
        issue_code=issue_code,
        subject_id=str(subject_id),
        status=IntegrationReconciliationStatus.OPEN,
    ).first()
    if existing:
        return existing

    safe_details = _sanitize_details(details)
    return IntegrationReconciliationIssue.objects.create(
        instance=instance,
        issue_code=issue_code,
        subject_type=subject_type,
        subject_id=str(subject_id),
        details=safe_details,
    )


def run_lms_reconciliation(instance_id: Optional[str] = None) -> list[IntegrationReconciliationIssue]:
    """Read-only deterministic detection scan comparing external mappings against VibeConnect records.

    Produces reviewable IntegrationReconciliationIssue entries.
    Never calls external mutating APIs or mutates identity/mapping data.
    """
    detected_issues: list[IntegrationReconciliationIssue] = []

    instances_qs = ConnectorInstance.objects.select_related("connector", "organization").all()
    if instance_id:
        instances_qs = instances_qs.filter(id=instance_id)

    for instance in instances_qs:
        org = instance.organization
        product = instance.connector.product
        if not product:
            product = Product.objects.filter(code__in=["lms", "lms_connector"]).first()

        # Check if parent organization has an active entitlement for LMS
        has_org_entitlement = False
        if product and org:
            has_org_entitlement = OrganizationProductEntitlement.objects.filter(
                organization=org,
                product=product,
                status=EntitlementStatus.ACTIVE,
            ).exists()

        # =========================================================================
        # 1. TENANT DETECTION
        # =========================================================================
        tenant_mapping = ExternalTenantMapping.objects.filter(
            instance=instance,
            organization=org,
        ).first()

        # A. Tenant Rank 1: ORGANIZATION_NOT_ACTIVE
        if tenant_mapping and org.status != OrganizationStatus.ACTIVE:
            issue = _record_or_reuse_issue(
                instance=instance,
                issue_code=LmsReconciliationIssueCode.ORGANIZATION_NOT_ACTIVE,
                subject_type="organization",
                subject_id=str(org.id),
                details={
                    "organization_id": str(org.id),
                    "organization_code": org.code,
                    "organization_status": org.status,
                    "external_tenant_id": tenant_mapping.external_tenant_id,
                    "reason": "Organization is not active in VibeConnect but has an active external tenant mapping.",
                },
            )
            detected_issues.append(issue)

        # B. Tenant Rank 2: MISSING_TENANT_MAPPING
        elif not tenant_mapping and has_org_entitlement and org.status == OrganizationStatus.ACTIVE:
            issue = _record_or_reuse_issue(
                instance=instance,
                issue_code=LmsReconciliationIssueCode.MISSING_TENANT_MAPPING,
                subject_type="organization",
                subject_id=str(org.id),
                details={
                    "organization_id": str(org.id),
                    "organization_code": org.code,
                    "organization_status": org.status,
                    "reason": "Active organization has an active LMS entitlement but lacks an ExternalTenantMapping.",
                },
            )
            detected_issues.append(issue)

        # C. Instance-wide: DUPLICATE_EXTERNAL_TENANT
        dup_tenant_query = (
            ExternalTenantMapping.objects.filter(instance=instance)
            .annotate(ext_key=Lower("external_tenant_id"))
            .values("ext_key")
            .annotate(cnt=Count("id"))
            .filter(cnt__gt=1)
        )
        for dup in dup_tenant_query:
            ext_id = dup["ext_key"]
            issue = _record_or_reuse_issue(
                instance=instance,
                issue_code=LmsReconciliationIssueCode.DUPLICATE_EXTERNAL_TENANT,
                subject_type="organization",
                subject_id=ext_id,
                details={
                    "external_tenant_id": ext_id,
                    "duplicate_count": dup["cnt"],
                    "reason": f"Multiple organizations ({dup['cnt']}) map to external_tenant_id '{ext_id}' on instance {instance.id}.",
                },
            )
            detected_issues.append(issue)

        # D. Data Integrity: ORPHAN_MAPPING_LOCAL_ENTITY_MISSING (Tenant)
        # Check for tenant mappings referencing non-existent organizations (e.g. legacy/raw SQL delete)
        orphan_tenant_mappings = ExternalTenantMapping.objects.filter(
            instance=instance,
            organization__isnull=True,
        )
        for otm in orphan_tenant_mappings:
            issue = _record_or_reuse_issue(
                instance=instance,
                issue_code=LmsReconciliationIssueCode.ORPHAN_MAPPING_LOCAL_ENTITY_MISSING,
                subject_type="mapping",
                subject_id=str(otm.id),
                details={
                    "mapping_id": str(otm.id),
                    "external_tenant_id": otm.external_tenant_id,
                    "reason": "ExternalTenantMapping exists but referenced organization is missing (data integrity anomaly).",
                },
            )
            detected_issues.append(issue)

        # =========================================================================
        # 2. USER DETECTION (Enforcing Frozen Precedence Ranks 1 to 6)
        # =========================================================================
        # Gather all candidate users related to this instance
        mapped_user_ids = set(
            ExternalUserMapping.objects.filter(instance=instance).values_list("user_id", flat=True)
        )
        assigned_user_ids = set()
        if product and org:
            assigned_user_ids = set(
                UserProductAssignment.objects.filter(
                    organization=org,
                    product=product,
                ).values_list("user_id", flat=True)
            )

        candidate_user_ids = mapped_user_ids | assigned_user_ids

        # Prefetch mappings and assignments for efficiency
        user_mappings_by_uid = {
            m.user_id: m
            for m in ExternalUserMapping.objects.filter(
                instance=instance,
                user_id__in=candidate_user_ids,
            ).select_related("user")
        }

        assignments_by_uid = {}
        if product and org:
            for a in UserProductAssignment.objects.filter(
                organization=org,
                product=product,
                user_id__in=candidate_user_ids,
            ):
                assignments_by_uid[a.user_id] = a

        users_by_uid = {
            u.id: u
            for u in User.objects.filter(id__in=candidate_user_ids)
        }

        # Track users who have had a primary issue logged to enforce strict precedence
        handled_users: set[Any] = set()

        for uid in candidate_user_ids:
            user = users_by_uid.get(uid)
            if not user:
                # User deleted in DB without cascading mapping: legacy orphan anomaly
                m = user_mappings_by_uid.get(uid)
                if m:
                    issue = _record_or_reuse_issue(
                        instance=instance,
                        issue_code=LmsReconciliationIssueCode.ORPHAN_MAPPING_LOCAL_ENTITY_MISSING,
                        subject_type="user",
                        subject_id=str(uid),
                        details={
                            "mapping_id": str(m.id),
                            "external_user_id": m.external_user_id,
                            "reason": "ExternalUserMapping exists but referenced platform user is missing.",
                        },
                    )
                    detected_issues.append(issue)
                continue

            mapping = user_mappings_by_uid.get(uid)
            assignment = assignments_by_uid.get(uid)

            is_user_active = bool(user.is_active and user.status == UserStatus.ACTIVE)
            is_mapping_active = bool(mapping and mapping.status == ExternalUserMappingStatus.ACTIVE)
            is_mapping_suspended = bool(mapping and mapping.status == ExternalUserMappingStatus.SUSPENDED)
            is_assignment_active = bool(assignment and assignment.status == AssignmentStatus.ACTIVE)
            is_assignment_stale = bool(assignment and assignment.status in (AssignmentStatus.SUSPENDED, AssignmentStatus.REVOKED))

            # --- Rank 1: USER_INACTIVE_OR_SUSPENDED ---
            if not is_user_active and is_mapping_active:
                issue = _record_or_reuse_issue(
                    instance=instance,
                    issue_code=LmsReconciliationIssueCode.USER_INACTIVE_OR_SUSPENDED,
                    subject_type="user",
                    subject_id=str(user.id),
                    details={
                        "user_id": str(user.id),
                        "email": user.email,
                        "is_active": user.is_active,
                        "user_status": str(user.status),
                        "external_user_id": mapping.external_user_id if mapping else "",
                        "reason": "User is inactive or suspended in VibeConnect but has an active external mapping.",
                    },
                )
                detected_issues.append(issue)
                handled_users.add(uid)
                continue

            # --- Rank 2: ASSIGNMENT_WITHOUT_ENTITLEMENT ---
            if is_assignment_active and not has_org_entitlement:
                issue = _record_or_reuse_issue(
                    instance=instance,
                    issue_code=LmsReconciliationIssueCode.ASSIGNMENT_WITHOUT_ENTITLEMENT,
                    subject_type="user",
                    subject_id=str(user.id),
                    details={
                        "user_id": str(user.id),
                        "email": user.email,
                        "organization_id": str(org.id),
                        "reason": "User has an active LMS assignment, but parent organization lacks an active LMS entitlement.",
                    },
                )
                detected_issues.append(issue)
                handled_users.add(uid)
                continue

            # --- Rank 3: CROSS_TENANT_MAPPING_MISMATCH ---
            # Contract Rule: NOT INDEPENDENTLY DETECTABLE WITH CURRENT READ-ONLY LMS APIs.
            # Routine scan strictly skips synthesizing this issue without external evidence.

            # --- Rank 4: STALE_USER_MAPPING ---
            # Mapping is ACTIVE, and local LMS assignment is explicitly SUSPENDED or REVOKED
            if is_mapping_active and assignment and is_assignment_stale:
                issue = _record_or_reuse_issue(
                    instance=instance,
                    issue_code=LmsReconciliationIssueCode.STALE_USER_MAPPING,
                    subject_type="user",
                    subject_id=str(user.id),
                    details={
                        "user_id": str(user.id),
                        "email": user.email,
                        "assignment_status": assignment.status,
                        "mapping_status": mapping.status,
                        "external_user_id": mapping.external_user_id,
                        "reason": f"ExternalUserMapping is ACTIVE but user LMS assignment is {assignment.status}.",
                    },
                )
                detected_issues.append(issue)
                handled_users.add(uid)
                continue

            # --- Rank 5: LOCAL_USER_MAPPING_DRIFT ---
            # Local user & assignment are ACTIVE and entitlement ACTIVE, but ExternalUserMapping is SUSPENDED
            if is_user_active and is_assignment_active and has_org_entitlement and is_mapping_suspended:
                issue = _record_or_reuse_issue(
                    instance=instance,
                    issue_code=LmsReconciliationIssueCode.LOCAL_USER_MAPPING_DRIFT,
                    subject_type="user",
                    subject_id=str(user.id),
                    details={
                        "user_id": str(user.id),
                        "email": user.email,
                        "mapping_status": mapping.status,
                        "reason": "User and assignment are active with valid entitlement, but local ExternalUserMapping is SUSPENDED.",
                    },
                )
                detected_issues.append(issue)
                handled_users.add(uid)
                continue

            # --- Rank 6: MISSING_USER_MAPPING ---
            # User & assignment are ACTIVE, entitlement ACTIVE, tenant mapping exists, but no user mapping
            if (
                is_user_active
                and is_assignment_active
                and has_org_entitlement
                and tenant_mapping
                and mapping is None
            ):
                issue = _record_or_reuse_issue(
                    instance=instance,
                    issue_code=LmsReconciliationIssueCode.MISSING_USER_MAPPING,
                    subject_type="user",
                    subject_id=str(user.id),
                    details={
                        "user_id": str(user.id),
                        "email": user.email,
                        "organization_id": str(org.id),
                        "reason": "Active user with active LMS assignment and entitlement has no ExternalUserMapping.",
                    },
                )
                detected_issues.append(issue)
                handled_users.add(uid)
                continue

        # =========================================================================
        # 3. IDENTITY & COLLISION CHECKS
        # =========================================================================
        # A. Instance-wide: DUPLICATE_EXTERNAL_USER
        dup_user_query = (
            ExternalUserMapping.objects.filter(instance=instance)
            .annotate(ext_key=Lower("external_user_id"))
            .values("ext_key")
            .annotate(cnt=Count("id"))
            .filter(cnt__gt=1)
        )
        for dup in dup_user_query:
            ext_id = dup["ext_key"]
            issue = _record_or_reuse_issue(
                instance=instance,
                issue_code=LmsReconciliationIssueCode.DUPLICATE_EXTERNAL_USER,
                subject_type="mapping",
                subject_id=ext_id,
                details={
                    "external_user_id": ext_id,
                    "duplicate_count": dup["cnt"],
                    "reason": f"Multiple user mappings ({dup['cnt']}) share external_user_id '{ext_id}' on instance {instance.id}.",
                },
            )
            detected_issues.append(issue)

        # B. Local Identity Contradiction: INCONSISTENT_MAPPED_IDENTITY
        # Checks locally provable contradictions: e.g. mapping's user has no membership in mapping's org
        for m in user_mappings_by_uid.values():
            if m.user:
                is_member = OrganizationMembership.objects.filter(
                    user=m.user,
                    organization=m.organization,
                ).exists()
                is_owner = getattr(m.user, "is_platform_owner", False)
                if not is_member and not is_owner:
                    issue = _record_or_reuse_issue(
                        instance=instance,
                        issue_code=LmsReconciliationIssueCode.INCONSISTENT_MAPPED_IDENTITY,
                        subject_type="user",
                        subject_id=str(m.user.id),
                        details={
                            "user_id": str(m.user.id),
                            "email": m.user.email,
                            "organization_id": str(m.organization.id),
                            "reason": f"User {m.user.email} is mapped to organization {m.organization.id} but holds no membership in it.",
                        },
                    )
                    detected_issues.append(issue)

    return detected_issues


@transaction.atomic
def resolve_lms_reconciliation(
    issue_id: str,
    resolved_by_user: Any,
    resolution_notes: str,
) -> IntegrationReconciliationIssue:
    """Marks an integration reconciliation issue as resolved with audit details."""
    issue = IntegrationReconciliationIssue.objects.select_for_update().get(id=issue_id)
    issue.status = IntegrationReconciliationStatus.RESOLVED
    issue.resolved_at = timezone.now()
    issue.resolved_by = resolved_by_user
    issue.resolution_notes = resolution_notes
    issue.save(update_fields=["status", "resolved_at", "resolved_by", "resolution_notes"])
    return issue


def remediate_reconciliation_issue(
    issue_or_id: Union[IntegrationReconciliationIssue, str, uuid.UUID],
    execute_now: bool = False,
    client: Optional[Any] = None,
) -> Optional[ProvisioningJob]:
    """Orchestrates safe canonical remediation for an auto-remediable reconciliation issue.

    - Validates issue eligibility according to frozen Stage 2 contract.
    - Idempotently creates or reuses a ProvisioningJob with exact reconciliation_issue_id.
    - Applies immediate safety containment for suspended/stale accounts.
    - Quarantines manual-review issues (returns None; issue remains OPEN).
    - If execute_now=True, synchronously executes the job via canonical provisioning executor.
    """
    job = None

    with transaction.atomic():
        if isinstance(issue_or_id, (str, uuid.UUID)):
            try:
                issue = IntegrationReconciliationIssue.objects.select_for_update().get(id=issue_or_id)
            except IntegrationReconciliationIssue.DoesNotExist:
                logger.warning(f"Reconciliation issue {issue_or_id} does not exist.")
                return None
        else:
            issue = IntegrationReconciliationIssue.objects.select_for_update().get(id=issue_or_id.id)

        # 1. State check
        if issue.status != IntegrationReconciliationStatus.OPEN:
            logger.info(f"Reconciliation issue {issue.id} is already {issue.status}. Skipping remediation.")
            return None

        # 2. Manual Review Quarantines
        MANUAL_REVIEW_CODES = {
            LmsReconciliationIssueCode.DUPLICATE_EXTERNAL_TENANT,
            LmsReconciliationIssueCode.DUPLICATE_EXTERNAL_USER,
            LmsReconciliationIssueCode.CROSS_TENANT_MAPPING_MISMATCH,
            LmsReconciliationIssueCode.INCONSISTENT_MAPPED_IDENTITY,
            LmsReconciliationIssueCode.ORPHAN_MAPPING_LOCAL_ENTITY_MISSING,
        }
        if issue.issue_code in MANUAL_REVIEW_CODES:
            logger.info(
                f"Issue {issue.id} ({issue.issue_code}) requires manual review. Zero automated remediation dispatched."
            )
            return None

        # 3. Special Case: ASSIGNMENT_WITHOUT_ENTITLEMENT
        if issue.issue_code == LmsReconciliationIssueCode.ASSIGNMENT_WITHOUT_ENTITLEMENT:
            # Safety containment: suspend user mapping if present, block access
            ExternalUserMapping.objects.filter(
                instance=issue.instance,
                user_id=issue.subject_id,
                status=ExternalUserMappingStatus.ACTIVE,
            ).update(status=ExternalUserMappingStatus.SUSPENDED)
            # Issue remains OPEN; zero retry/remediation job created
            logger.info(f"Safety containment applied for {issue.id}: User mapping suspended. Issue remains OPEN.")
            return None

        # 4. Special Case: REMOTE_RECORD_MISSING (Tenant only)
        if issue.issue_code == LmsReconciliationIssueCode.REMOTE_RECORD_MISSING:
            if issue.subject_type != "organization":
                logger.info("User REMOTE_RECORD_MISSING is not independently auto-remediable. Issue remains OPEN.")
                return None

        # 5. Special Case: PROFILE_NAME_DRIFT
        if issue.issue_code == LmsReconciliationIssueCode.PROFILE_NAME_DRIFT:
            if not issue.details.get("remote_profile_evidence"):
                logger.info("PROFILE_NAME_DRIFT lacks verified remote evidence. Issue remains OPEN.")
                return None

        # 6. Action & Entity Mapping
        org = issue.instance.organization
        user = None
        action = None
        job_context: dict[str, Any] = {}

        if issue.issue_code == LmsReconciliationIssueCode.MISSING_TENANT_MAPPING:
            action = ProvisioningAction.PROVISION
            user = None

        elif issue.issue_code == LmsReconciliationIssueCode.MISSING_USER_MAPPING:
            action = ProvisioningAction.PROVISION
            user = User.objects.filter(id=issue.subject_id).first()
            if not user:
                logger.warning(f"User {issue.subject_id} not found for issue {issue.id}.")
                return None
            job_context["is_active"] = True

        elif issue.issue_code == LmsReconciliationIssueCode.ORGANIZATION_NOT_ACTIVE:
            action = ProvisioningAction.DEPROVISION
            user = None
            job_context["target_status"] = "Inactive"

        elif issue.issue_code == LmsReconciliationIssueCode.USER_INACTIVE_OR_SUSPENDED:
            action = ProvisioningAction.DEPROVISION
            user = User.objects.filter(id=issue.subject_id).first()
            if not user:
                return None
            job_context["is_active"] = False
            # Immediate safety containment
            ExternalUserMapping.objects.filter(
                instance=issue.instance,
                user=user,
            ).update(status=ExternalUserMappingStatus.SUSPENDED)

        elif issue.issue_code == LmsReconciliationIssueCode.STALE_USER_MAPPING:
            action = ProvisioningAction.DEPROVISION
            user = User.objects.filter(id=issue.subject_id).first()
            if not user:
                return None
            job_context["is_active"] = False
            # Immediate safety containment
            ExternalUserMapping.objects.filter(
                instance=issue.instance,
                user=user,
            ).update(status=ExternalUserMappingStatus.SUSPENDED)

        elif issue.issue_code == LmsReconciliationIssueCode.LOCAL_USER_MAPPING_DRIFT:
            action = ProvisioningAction.SYNC
            user = User.objects.filter(id=issue.subject_id).first()
            if not user:
                return None
            job_context["is_active"] = True

        elif issue.issue_code == LmsReconciliationIssueCode.REMOTE_RECORD_MISSING:
            # Organization missing in LMS
            action = ProvisioningAction.PROVISION
            user = None
            job_context["force_reprovision"] = True

        elif issue.issue_code == LmsReconciliationIssueCode.PROFILE_NAME_DRIFT:
            action = ProvisioningAction.UPDATE
            user = User.objects.filter(id=issue.subject_id).first()
            if not user:
                return None

        if not action:
            logger.warning(f"No provisioning action mapped for issue {issue.issue_code}.")
            return None

        # 7. Check for existing correlated job
        existing_job = ProvisioningJob.objects.filter(
            instance=issue.instance,
            organization=org,
            user=user,
            action=action,
            context__reconciliation_issue_id=str(issue.id),
        ).order_by("-created_at").first()

        if existing_job:
            if existing_job.status in (ProvisioningJobStatus.QUEUED, ProvisioningJobStatus.PROCESSING):
                logger.info(f"Reusing active correlated ProvisioningJob {existing_job.id} for issue {issue.id}.")
                job = existing_job
            elif existing_job.status == ProvisioningJobStatus.COMPLETED:
                logger.info(f"ProvisioningJob {existing_job.id} already completed for issue {issue.id}.")
                return existing_job
            else:
                job = existing_job

        if not job:
            # 8. Check for existing active job matching entity and action
            active_job = ProvisioningJob.objects.filter(
                instance=issue.instance,
                organization=org,
                user=user,
                action=action,
                status__in=[ProvisioningJobStatus.QUEUED, ProvisioningJobStatus.PROCESSING],
            ).first()

            if active_job:
                active_job.context["reconciliation_issue_id"] = str(issue.id)
                active_job.context["reconciliation_issue_code"] = issue.issue_code
                active_job.save(update_fields=["context", "updated_at"])
                logger.info(f"Correlated active ProvisioningJob {active_job.id} to issue {issue.id}.")
                job = active_job

        if not job:
            # 9. Create new ProvisioningJob
            payload_context = {
                **job_context,
                "reconciliation_issue_id": str(issue.id),
                "reconciliation_issue_code": issue.issue_code,
            }
            job = ProvisioningJob.objects.create(
                instance=issue.instance,
                organization=org,
                user=user,
                action=action,
                status=ProvisioningJobStatus.QUEUED,
                context=payload_context,
            )
            logger.info(f"Created ProvisioningJob {job.id} ({action}) for reconciliation issue {issue.id}.")

    # Execute outside creation transaction boundary so operational failures are persisted
    if execute_now and job and job.status == ProvisioningJobStatus.QUEUED:
        from apps.integration_hub.provisioning_service import execute_provisioning_job
        job = execute_provisioning_job(job, client=client)

    return job


@transaction.atomic
def verify_and_resolve_reconciliation_issue(job: ProvisioningJob) -> Optional[IntegrationReconciliationIssue]:
    """Validates post-remediation condition and resolves the exact originating reconciliation issue."""
    issue_id = job.context.get("reconciliation_issue_id")
    if not issue_id:
        return None

    try:
        issue = IntegrationReconciliationIssue.objects.select_for_update().get(id=issue_id)
    except IntegrationReconciliationIssue.DoesNotExist:
        logger.warning(f"Reconciliation issue {issue_id} not found for job {job.id}.")
        return None

    if issue.status != IntegrationReconciliationStatus.OPEN:
        logger.info(f"Reconciliation issue {issue_id} is already {issue.status}. Skipping resolution.")
        return issue

    verified = False
    notes = ""

    if issue.issue_code == LmsReconciliationIssueCode.MISSING_TENANT_MAPPING:
        mapping = ExternalTenantMapping.objects.filter(
            instance=job.instance,
            organization=job.organization,
        ).first()
        res = job.context.get("result", {})
        expected_ext_id = str(res.get("external_tenant_id") or res.get("lms_organization_id") or "").strip()
        if mapping and mapping.external_tenant_id and (not expected_ext_id or mapping.external_tenant_id == expected_ext_id):
            verified = True
            notes = f"Auto-resolved: Tenant mapping created and verified by job {job.id}."

    elif issue.issue_code == LmsReconciliationIssueCode.MISSING_USER_MAPPING:
        mapping = ExternalUserMapping.objects.filter(
            instance=job.instance,
            user=job.user,
            organization=job.organization,
        ).first()
        res = job.context.get("result", {})
        expected_ext_id = str(res.get("external_user_id") or res.get("lms_user_id") or "").strip()
        if (
            mapping
            and mapping.status == ExternalUserMappingStatus.ACTIVE
            and (not expected_ext_id or mapping.external_user_id == expected_ext_id)
        ):
            verified = True
            notes = f"Auto-resolved: User mapping created and verified by job {job.id}."

    elif issue.issue_code == LmsReconciliationIssueCode.ORGANIZATION_NOT_ACTIVE:
        res = job.context.get("result", {})
        if res.get("status") == "success":
            verified = True
            notes = f"Auto-resolved: Remote tenant deactivated by job {job.id}."

    elif issue.issue_code in (
        LmsReconciliationIssueCode.USER_INACTIVE_OR_SUSPENDED,
        LmsReconciliationIssueCode.STALE_USER_MAPPING,
    ):
        mapping = ExternalUserMapping.objects.filter(
            instance=job.instance,
            user=job.user,
            organization=job.organization,
        ).first()
        res = job.context.get("result", {})
        if mapping and mapping.status == ExternalUserMappingStatus.SUSPENDED and res.get("status") == "success":
            verified = True
            notes = f"Auto-resolved: User mapping suspended and remote deactivated by job {job.id}."

    elif issue.issue_code == LmsReconciliationIssueCode.LOCAL_USER_MAPPING_DRIFT:
        mapping = ExternalUserMapping.objects.filter(
            instance=job.instance,
            user=job.user,
            organization=job.organization,
        ).first()
        if mapping and mapping.status == ExternalUserMappingStatus.ACTIVE:
            verified = True
            notes = f"Auto-resolved: User mapping synchronized to ACTIVE by job {job.id}."

    elif issue.issue_code == LmsReconciliationIssueCode.REMOTE_RECORD_MISSING:
        mapping = ExternalTenantMapping.objects.filter(
            instance=job.instance,
            organization=job.organization,
        ).first()
        if mapping and mapping.external_tenant_id:
            collision = ExternalTenantMapping.objects.filter(
                instance=job.instance,
                external_tenant_id=mapping.external_tenant_id,
            ).exclude(organization=job.organization).exists()
            if not collision:
                verified = True
                notes = f"Auto-resolved: Missing remote tenant reprovisioned and verified by job {job.id}."

    elif issue.issue_code == LmsReconciliationIssueCode.PROFILE_NAME_DRIFT:
        res = job.context.get("result", {})
        if res.get("status") == "success":
            verified = True
            notes = f"Auto-resolved: User profile updated by job {job.id}."

    if verified:
        issue.status = IntegrationReconciliationStatus.RESOLVED
        issue.resolved_at = timezone.now()
        issue.resolution_notes = notes
        issue.save(update_fields=["status", "resolved_at", "resolution_notes"])
        logger.info(f"Reconciliation issue {issue_id} successfully auto-resolved via job {job.id}.")
        return issue
    else:
        logger.warning(
            f"Post-remediation verification failed for issue {issue_id} ({issue.issue_code}). Keeping OPEN."
        )
        return None
