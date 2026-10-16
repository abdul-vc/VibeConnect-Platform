"""Automatic Lifecycle Provisioning Triggers (Phase 5C-3 Stage 3).

Orchestrates automatic, idempotent M2M LMS provisioning triggered by canonical
VibeConnect business lifecycle events:
- Tenant LMS Entitlement Activation / Subscription Activation
- Tenant Deactivation / Suspension / Retirement
- User LMS Product Assignment Activation
- User LMS Product Assignment Suspension, Reactivation, and Revocation

Transaction & Safety Guarantees:
- Never executes external HTTP calls inside an uncommitted database transaction (uses transaction.on_commit).
- Enforces strict tenant-before-user dependency ordering.
- Idempotent event emission and ProvisioningJob deduplication.
- Preserves full audit context without leaking credentials or secrets.
"""

import logging
from typing import Any, Optional
import uuid

from django.db import transaction
from django.utils import timezone

from apps.integration_hub.models import (
    ConnectorInstance,
    EventStatus,
    ExternalTenantMapping,
    ExternalUserMapping,
    ExternalUserMappingStatus,
    IntegrationEvent,
    ProvisioningAction,
    ProvisioningJob,
    ProvisioningJobStatus,
)
from apps.integration_hub.provisioning_service import (
    execute_provisioning_job,
    get_or_create_lms_connector_instance,
)
from apps.organizations.models import (
    MembershipStatus,
    MembershipType,
    Organization,
    OrganizationMembership,
    OrganizationStatus,
)

logger = logging.getLogger(__name__)

LMS_PRODUCT_CODES = frozenset(["lms", "lms_core", "lms-pilot"])


def is_lms_product(product: Any) -> bool:
    """Returns True if the given product or product code corresponds to LMS."""
    if not product:
        return False
    code = getattr(product, "code", None)
    if not code and isinstance(product, str):
        code = product
    if not code:
        return False
    return str(code).strip().lower() in LMS_PRODUCT_CODES


def dispatch_provisioning_job(job_id: uuid.UUID | str) -> None:
    """Executes the provisioning job after database transaction commit."""
    try:
        execute_provisioning_job(job_id)
    except Exception as exc:
        logger.error(f"Error executing dispatched ProvisioningJob {job_id}: {exc}")


def schedule_job_execution(job: ProvisioningJob) -> None:
    """Enqueues execution of the ProvisioningJob strictly after transaction commit."""
    job_id = job.id
    transaction.on_commit(lambda: dispatch_provisioning_job(job_id))


def handle_tenant_lms_entitlement_activated(
    organization: Organization,
    actor: Optional[Any] = None,
    source: str = "entitlement_activated",
) -> Optional[ProvisioningJob]:
    """Canonical hook invoked when LMS access becomes active for an organization.

    Steps:
    1. Verify organization is active (not retired).
    2. Resolve or idempotently create LMS ConnectorInstance.
    3. Idempotently record IntegrationEvent.
    4. Enqueue ProvisioningJob (action=PROVISION, user=None).
    5. Dispatches execution via transaction.on_commit.
    """
    if not organization or organization.status == OrganizationStatus.RETIRED:
        logger.warning(
            f"Cannot activate LMS entitlement for invalid/retired organization {getattr(organization, 'code', 'unknown')}"
        )
        return None

    try:
        instance = get_or_create_lms_connector_instance(organization)
    except Exception as exc:
        logger.error(f"Failed to get/create LMS connector instance for org {organization.id}: {exc}")
        return None

    # 1. Idempotent Event Recording
    event_key = f"lms.tenant.provision:{organization.id}"
    IntegrationEvent.objects.get_or_create(
        instance=instance,
        event_key=event_key,
        defaults={
            "event_type": "lms.tenant.provision",
            "payload": {
                "organization_id": str(organization.id),
                "organization_code": organization.code,
                "product_code": "lms",
                "source": source,
            },
            "occurred_at": timezone.now(),
            "status": EventStatus.RECEIVED,
        },
    )

    # 2. Check for existing active, completed, or already mapped tenant
    with transaction.atomic():
        if ExternalTenantMapping.objects.filter(instance=instance, organization=organization).exists():
            existing_completed = ProvisioningJob.objects.filter(
                instance=instance,
                organization=organization,
                user=None,
                action=ProvisioningAction.PROVISION,
                status=ProvisioningJobStatus.COMPLETED,
            ).first()
            return existing_completed

        existing_job = ProvisioningJob.objects.select_for_update().filter(
            instance=instance,
            organization=organization,
            user=None,
            action=ProvisioningAction.PROVISION,
            status__in=[
                ProvisioningJobStatus.QUEUED,
                ProvisioningJobStatus.PROCESSING,
            ],
        ).first()

        if existing_job:
            return existing_job

        # 3. Create new queued ProvisioningJob
        job = ProvisioningJob.objects.create(
            instance=instance,
            organization=organization,
            user=None,
            action=ProvisioningAction.PROVISION,
            status=ProvisioningJobStatus.QUEUED,
            context={
                "product_code": "lms",
                "source": source,
                "correlation_key": str(uuid.uuid4()),
            },
        )

    schedule_job_execution(job)
    return job


def handle_tenant_deactivated_or_suspended(
    organization: Organization,
    status: str,
    actor: Optional[Any] = None,
    reason: str = "",
) -> Optional[ProvisioningJob]:
    """Canonical hook invoked when an organization is deactivated, suspended, or retired."""
    if not organization:
        return None

    # Check if organization has LMS integration
    mapping = ExternalTenantMapping.objects.filter(organization=organization).first()
    instance = mapping.instance if mapping else ConnectorInstance.objects.filter(
        organization=organization,
        connector__code__in=["lms_connector", "lms"],
    ).first()

    if not instance and not mapping:
        return None

    if not instance:
        try:
            instance = get_or_create_lms_connector_instance(organization)
        except Exception:
            return None

    target_status = "Inactive" if status == OrganizationStatus.RETIRED else "Suspended"
    action = (
        ProvisioningAction.DEPROVISION
        if status == OrganizationStatus.RETIRED
        else ProvisioningAction.UPDATE
    )

    event_key = f"lms.tenant.{status}:{organization.id}:{timezone.now().date()}"
    IntegrationEvent.objects.get_or_create(
        instance=instance,
        event_key=event_key,
        defaults={
            "event_type": f"lms.tenant.{status}",
            "payload": {
                "organization_id": str(organization.id),
                "organization_code": organization.code,
                "target_status": target_status,
                "reason": reason,
            },
            "occurred_at": timezone.now(),
            "status": EventStatus.RECEIVED,
        },
    )

    job = ProvisioningJob.objects.create(
        instance=instance,
        organization=organization,
        user=None,
        action=action,
        status=ProvisioningJobStatus.QUEUED,
        context={
            "product_code": "lms",
            "target_status": target_status,
            "reason": reason,
            "correlation_key": str(uuid.uuid4()),
        },
    )

    schedule_job_execution(job)
    return job


def handle_user_lms_assignment_active(
    assignment: Any,
    actor: Optional[Any] = None,
    source: str = "assignment_active",
) -> Optional[ProvisioningJob]:
    """Canonical hook invoked when a user receives an active LMS product assignment."""
    if not assignment or not is_lms_product(assignment.product):
        return None

    organization = assignment.organization
    user = assignment.user

    # Cross-tenant check: user must belong to organization
    is_member = OrganizationMembership.objects.filter(
        user=user,
        organization=organization,
    ).exists()
    if not is_member and not getattr(user, "is_platform_owner", False):
        logger.warning(
            f"Cross-tenant assignment rejected: user {user.id} not in org {organization.id}"
        )
        return None

    try:
        instance = get_or_create_lms_connector_instance(organization)
    except Exception as exc:
        logger.error(f"Failed to get/create LMS connector instance: {exc}")
        return None

    # Idempotent Event Recording
    event_key = f"lms.user.provision:{organization.id}:{user.id}"
    IntegrationEvent.objects.get_or_create(
        instance=instance,
        event_key=event_key,
        defaults={
            "event_type": "lms.user.provision",
            "payload": {
                "organization_id": str(organization.id),
                "user_id": str(user.id),
                "user_email": getattr(user, "email", ""),
                "product_code": "lms",
                "source": source,
            },
            "occurred_at": timezone.now(),
            "status": EventStatus.RECEIVED,
        },
    )

    with transaction.atomic():
        # 1. If active mapping already exists, user is already active in LMS
        existing_mapping = ExternalUserMapping.objects.filter(
            instance=instance,
            user=user,
            organization=organization,
            status=ExternalUserMappingStatus.ACTIVE,
        ).first()
        if existing_mapping:
            completed_job = ProvisioningJob.objects.filter(
                instance=instance,
                organization=organization,
                user=user,
                action=ProvisioningAction.PROVISION,
                status=ProvisioningJobStatus.COMPLETED,
            ).first()
            return completed_job

        # 2. Check if a job is already queued or processing for this user/org
        existing_job = ProvisioningJob.objects.select_for_update().filter(
            instance=instance,
            organization=organization,
            user=user,
            action=ProvisioningAction.PROVISION,
            status__in=[ProvisioningJobStatus.QUEUED, ProvisioningJobStatus.PROCESSING],
        ).first()

        if existing_job:
            return existing_job

        job = ProvisioningJob.objects.create(
            instance=instance,
            organization=organization,
            user=user,
            action=ProvisioningAction.PROVISION,
            status=ProvisioningJobStatus.QUEUED,
            context={
                "assignment_id": str(assignment.id),
                "product_code": "lms",
                "is_active": True,
                "source": source,
                "correlation_key": str(uuid.uuid4()),
            },
        )

    schedule_job_execution(job)
    return job


def handle_user_lms_assignment_suspended(
    assignment: Any,
    actor: Optional[Any] = None,
    reason: str = "",
) -> Optional[ProvisioningJob]:
    """Canonical hook when user LMS assignment is suspended."""
    if not assignment or not is_lms_product(assignment.product):
        return None

    organization = assignment.organization
    user = assignment.user

    try:
        instance = get_or_create_lms_connector_instance(organization)
    except Exception:
        return None

    job = ProvisioningJob.objects.create(
        instance=instance,
        organization=organization,
        user=user,
        action=ProvisioningAction.UPDATE,
        status=ProvisioningJobStatus.QUEUED,
        context={
            "assignment_id": str(assignment.id),
            "product_code": "lms",
            "is_active": False,
            "reason": reason,
            "action_type": "suspend",
            "correlation_key": str(uuid.uuid4()),
        },
    )

    schedule_job_execution(job)
    return job


def handle_user_lms_assignment_reactivated(
    assignment: Any,
    actor: Optional[Any] = None,
) -> Optional[ProvisioningJob]:
    """Canonical hook when user LMS assignment is reactivated."""
    if not assignment or not is_lms_product(assignment.product):
        return None

    organization = assignment.organization
    user = assignment.user

    try:
        instance = get_or_create_lms_connector_instance(organization)
    except Exception:
        return None

    job = ProvisioningJob.objects.create(
        instance=instance,
        organization=organization,
        user=user,
        action=ProvisioningAction.UPDATE,
        status=ProvisioningJobStatus.QUEUED,
        context={
            "assignment_id": str(assignment.id),
            "product_code": "lms",
            "is_active": True,
            "action_type": "reactivate",
            "correlation_key": str(uuid.uuid4()),
        },
    )

    schedule_job_execution(job)
    return job


def handle_user_lms_assignment_revoked(
    assignment: Any,
    actor: Optional[Any] = None,
    reason: str = "",
) -> Optional[ProvisioningJob]:
    """Canonical hook when user LMS assignment is revoked."""
    if not assignment or not is_lms_product(assignment.product):
        return None

    organization = assignment.organization
    user = assignment.user

    try:
        instance = get_or_create_lms_connector_instance(organization)
    except Exception:
        return None

    job = ProvisioningJob.objects.create(
        instance=instance,
        organization=organization,
        user=user,
        action=ProvisioningAction.DEPROVISION,
        status=ProvisioningJobStatus.QUEUED,
        context={
            "assignment_id": str(assignment.id),
            "product_code": "lms",
            "is_active": False,
            "reason": reason,
            "action_type": "revoke",
            "correlation_key": str(uuid.uuid4()),
        },
    )

    schedule_job_execution(job)
    return job


def handle_user_membership_promoted_to_admin(
    membership: OrganizationMembership,
    actor: Optional[Any] = None,
    source: str = "membership_promoted_to_admin",
) -> Optional[ProvisioningJob]:
    """Canonical hook invoked when a member is promoted to TENANT_ADMIN in an organization.

    If the user holds an active LMS product assignment in this organization,
    enqueues an idempotent ProvisioningJob to synchronize the user's updated role to LMS.
    """
    if not membership or membership.membership_type != MembershipType.TENANT_ADMIN:
        return None

    organization = membership.organization
    user = membership.user

    # Find active LMS product assignment for this user in this organization
    from apps.assignments.models import AssignmentStatus, UserProductAssignment

    assignment = UserProductAssignment.objects.filter(
        organization=organization,
        user=user,
        status=AssignmentStatus.ACTIVE,
        product__code__in=LMS_PRODUCT_CODES,
    ).select_related("product").first()

    if not assignment:
        # User has no active LMS assignment: do not trigger LMS provisioning
        return None

    try:
        instance = get_or_create_lms_connector_instance(organization)
    except Exception as exc:
        logger.error(f"Failed to get/create LMS connector instance: {exc}")
        return None

    # Idempotent Event Recording
    event_key = f"lms.user.role_sync:{organization.id}:{user.id}:admin:{timezone.now().date()}"
    IntegrationEvent.objects.get_or_create(
        instance=instance,
        event_key=event_key,
        defaults={
            "event_type": "lms.user.role_sync",
            "payload": {
                "organization_id": str(organization.id),
                "user_id": str(user.id),
                "user_email": getattr(user, "email", ""),
                "target_role": "organization_admin",
                "source": source,
            },
            "occurred_at": timezone.now(),
            "status": EventStatus.RECEIVED,
        },
    )

    with transaction.atomic():
        # Check if an in-flight job is already queued or processing for this user/org
        existing_job = ProvisioningJob.objects.select_for_update().filter(
            instance=instance,
            organization=organization,
            user=user,
            action=ProvisioningAction.PROVISION,
            status__in=[ProvisioningJobStatus.QUEUED, ProvisioningJobStatus.PROCESSING],
        ).first()

        if existing_job:
            return existing_job

        job = ProvisioningJob.objects.create(
            instance=instance,
            organization=organization,
            user=user,
            action=ProvisioningAction.PROVISION,
            status=ProvisioningJobStatus.QUEUED,
            context={
                "assignment_id": str(assignment.id),
                "product_code": "lms",
                "is_active": True,
                "target_role": "organization_admin",
                "source": source,
                "correlation_key": str(uuid.uuid4()),
            },
        )

    schedule_job_execution(job)
    return job

