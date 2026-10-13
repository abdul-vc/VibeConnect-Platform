"""LMS Tenant & User Provisioning Orchestration Services (Phase 5C-3 Stage 2).

Provides:
- Idempotent tenant provisioning from VibeConnect Organization to LMS Organization.
- Idempotent user provisioning from VibeConnect PlatformUser to LMS User.
- Orchestration around ProvisioningJob lifecycle (QUEUED -> PROCESSING -> COMPLETED/FAILED).
- Integration with IntegrationFailure and retry_service for automated exponential backoff
  and dead-letter classification.
Zero direct DB joins between VibeConnect and LMS; all communication executes via LmsConnectorClient.
"""

import logging
from typing import Any, Optional, Union
import uuid

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.integration_hub.lms_connector import (
    LmsConnectorClient,
    LmsConnectorError,
    LmsConnectorPermanentError,
)
from apps.integration_hub.models import (
    AttemptOutcome,
    ConnectorInstance,
    ExternalTenantMapping,
    ExternalUserMapping,
    ExternalUserMappingStatus,
    FailureStatus,
    FailureType,
    InstanceStatus,
    IntegrationConnector,
    IntegrationFailure,
    IntegrationFailureAttempt,
    ProvisioningAction,
    ProvisioningJob,
    ProvisioningJobStatus,
)
from apps.integration_hub.retry_service import (
    classify_failure,
    mark_failure_dead_letter,
    record_failure_attempt,
    resolve_failure,
    sanitize_diagnostic_detail,
    schedule_failure_retry,
)
from apps.organizations.models import (
    MembershipStatus,
    MembershipType,
    Organization,
    OrganizationMembership,
    OrganizationStatus,
)

logger = logging.getLogger(__name__)

LMS_ROLE_ORGANIZATION_ADMIN = "organization_admin"
LMS_ROLE_MEMBER = "member"


class ProvisioningServiceError(Exception):
    """Base exception for provisioning orchestration errors."""

    def __init__(self, message: str, code: str = "PROVISIONING_ERROR", detail: str = ""):
        super().__init__(message)
        self.message = message
        self.code = code
        self.detail = detail


class TenantProvisioningError(ProvisioningServiceError):
    """Raised when tenant provisioning cannot proceed."""
    pass


class UserProvisioningError(ProvisioningServiceError):
    """Raised when user provisioning cannot proceed."""
    pass


def get_or_create_lms_connector_instance(organization: Organization) -> ConnectorInstance:
    """Retrieves or idempotently creates an active ConnectorInstance for LMS and organization."""
    instance = ConnectorInstance.objects.filter(
        organization=organization,
        connector__code__in=["lms_connector", "lms"],
        status=InstanceStatus.ACTIVE,
    ).first()

    if instance:
        return instance

    connector = IntegrationConnector.objects.filter(
        code__in=["lms_connector", "lms"]
    ).first()
    if not connector:
        connector = IntegrationConnector.objects.filter(product__code="lms").first()
    if not connector:
        raise TenantProvisioningError(
            "LMS IntegrationConnector is not registered.",
            code="CONNECTOR_NOT_FOUND",
        )

    instance, _ = ConnectorInstance.objects.get_or_create(
        connector=connector,
        organization=organization,
        defaults={
            "label": f"lms_connector@{organization.id}",
            "credential_ref": "ref:m2m_connector_secret",
            "status": InstanceStatus.ACTIVE,
            "config": {},
        },
    )
    if instance.status != InstanceStatus.ACTIVE:
        instance.status = InstanceStatus.ACTIVE
        instance.save(update_fields=["status"])

    return instance


def provision_tenant_to_lms(
    organization: Organization,
    instance: Optional[ConnectorInstance] = None,
    client: Optional[LmsConnectorClient] = None,
    status_override: Optional[str] = None,
) -> dict[str, Any]:
    """Idempotently provisions a VibeConnect Organization into an LMS Organization.

    Steps:
    1. Verify organization exists and is not retired (unless status_override is given).
    2. Resolve active LMS ConnectorInstance.
    3. Construct canonical tenant payload.
    4. Call LMS M2M tenant provisioning API.
    5. Persist/update VibeConnect ExternalTenantMapping.
    6. Return structured result.
    """
    if not organization:
        raise TenantProvisioningError("Organization is required.", code="ORGANIZATION_REQUIRED")

    if organization.status == OrganizationStatus.RETIRED and not status_override:
        raise TenantProvisioningError(
            f"Cannot provision retired organization '{organization.code}'.",
            code="ORGANIZATION_RETIRED",
        )

    if not instance:
        instance = get_or_create_lms_connector_instance(organization)

    if not client:
        base_url = instance.config.get("base_url") if isinstance(instance.config, dict) else None
        client = LmsConnectorClient(base_url=base_url)

    if status_override:
        status_val = status_override
    elif organization.status == OrganizationStatus.ACTIVE:
        status_val = "Active"
    elif organization.status == OrganizationStatus.SUSPENDED:
        status_val = "Suspended"
    else:
        status_val = organization.status

    payload = {
        "external_tenant_id": str(organization.id),
        "name": organization.name,
        "code": organization.code,
        "status": status_val,
    }

    # Execute M2M HTTP call
    resp = client.provision_tenant(payload)

    lms_org_id = str(resp.get("lms_organization_id", "")).strip()
    if not lms_org_id:
        raise TenantProvisioningError(
            "LMS response did not contain a valid lms_organization_id.",
            code="INVALID_RESPONSE",
        )

    # Persist or update local ExternalTenantMapping atomically
    with transaction.atomic():
        try:
            mapping, created = ExternalTenantMapping.objects.select_for_update().get_or_create(
                instance=instance,
                organization=organization,
                defaults={"external_tenant_id": lms_org_id},
            )
            if not created and mapping.external_tenant_id != lms_org_id:
                mapping.external_tenant_id = lms_org_id
                mapping.save(update_fields=["external_tenant_id", "updated_at"])
        except IntegrityError:
            mapping = ExternalTenantMapping.objects.select_for_update().get(
                instance=instance,
                organization=organization,
            )
            if mapping.external_tenant_id != lms_org_id:
                mapping.external_tenant_id = lms_org_id
                mapping.save(update_fields=["external_tenant_id", "updated_at"])
            created = False

    return {
        "organization_id": str(organization.id),
        "external_tenant_id": lms_org_id,
        "lms_organization_id": resp.get("lms_organization_id"),
        "action_taken": resp.get("action_taken", "created" if created else "existing"),
        "status": "success",
    }


def provision_user_to_lms(
    user: Any,
    organization: Organization,
    is_active: bool = True,
    instance: Optional[ConnectorInstance] = None,
    client: Optional[LmsConnectorClient] = None,
) -> dict[str, Any]:
    """Idempotently provisions a VibeConnect user into an LMS User for an organization.

    Steps:
    1. Verify user belongs to the target organization.
    2. Ensure tenant is provisioned in LMS and local ExternalTenantMapping exists.
    3. Construct canonical user payload.
    4. Call LMS M2M user provisioning API.
    5. Persist/update VibeConnect ExternalUserMapping.
    6. Return structured result.
    """
    if not user or not getattr(user, "id", None):
        raise UserProvisioningError("Valid User instance is required.", code="USER_REQUIRED")
    if not organization or not getattr(organization, "id", None):
        raise UserProvisioningError("Valid Organization instance is required.", code="ORGANIZATION_REQUIRED")

    # 1. Tenant Membership Verification & Authoritative Role Resolution
    membership = (
        OrganizationMembership.objects.filter(
            user=user,
            organization=organization,
        )
        .select_related("role")
        .first()
    )

    if is_active:
        is_member = bool(membership and membership.status == MembershipStatus.ACTIVE)

        if not is_member and not getattr(user, "is_platform_owner", False):
            raise UserProvisioningError(
                f"User {user.email} is not an active member of organization {organization.code}.",
                code="NOT_AN_ORGANIZATION_MEMBER",
            )
    else:
        is_associated = (
            bool(membership)
            or ExternalUserMapping.objects.filter(user=user, organization=organization).exists()
            or getattr(user, "is_platform_owner", False)
        )
        if not is_associated:
            raise UserProvisioningError(
                f"User {user.email} is not associated with organization {organization.code}.",
                code="NOT_AN_ORGANIZATION_MEMBER",
            )

    # 2. Derive authoritative LMS role strictly from target tenant membership
    # tenant_admin -> organization_admin
    # member -> member
    # missing, unsupported, or inconsistent -> defaults safely to member (never defaults to administrative role)
    lms_role = LMS_ROLE_MEMBER
    if (
        membership
        and membership.membership_type == MembershipType.TENANT_ADMIN
        and membership.role_id is not None
    ):
        lms_role = LMS_ROLE_ORGANIZATION_ADMIN

    if not instance:
        instance = get_or_create_lms_connector_instance(organization)

    if not client:
        base_url = instance.config.get("base_url") if isinstance(instance.config, dict) else None
        client = LmsConnectorClient(base_url=base_url)

    # 3. Ensure Tenant is provisioned before user provisioning
    tenant_mapping = ExternalTenantMapping.objects.filter(
        instance=instance,
        organization=organization,
    ).first()

    if not tenant_mapping:
        logger.info(f"Provisioning tenant {organization.code} before provisioning user {user.email}")
        provision_tenant_to_lms(organization, instance=instance, client=client)

    # 4. Assemble user names
    first_name = getattr(user, "first_name", "")
    last_name = getattr(user, "last_name", "")
    if not first_name and getattr(user, "full_name", None):
        parts = user.full_name.strip().split(" ", 1)
        first_name = parts[0]
        last_name = parts[1] if len(parts) > 1 else ""

    payload = {
        "external_tenant_id": str(organization.id),
        "external_user_id": str(user.id),
        "email": user.email,
        "first_name": first_name or "",
        "last_name": last_name or "",
        "role": lms_role,
        "is_active": bool(is_active),
    }

    # 4. Call LMS M2M user provisioning endpoint
    resp = client.provision_user(payload)

    lms_user_id = str(resp.get("lms_user_id", "")).strip()
    if not lms_user_id:
        raise UserProvisioningError(
            "LMS response did not contain a valid lms_user_id.",
            code="INVALID_RESPONSE",
        )

    # 5. Persist or update local ExternalUserMapping
    target_status = (
        ExternalUserMappingStatus.ACTIVE if is_active else ExternalUserMappingStatus.SUSPENDED
    )

    with transaction.atomic():
        try:
            mapping = ExternalUserMapping.objects.select_for_update().filter(
                instance=instance,
                external_user_id=lms_user_id,
            ).first()

            if not mapping:
                # Check if user already had another mapping in this instance
                mapping = ExternalUserMapping.objects.select_for_update().filter(
                    instance=instance,
                    user=user,
                    organization=organization,
                ).first()

            if mapping:
                updated_fields = []
                if mapping.external_user_id != lms_user_id:
                    mapping.external_user_id = lms_user_id
                    updated_fields.append("external_user_id")
                if mapping.status != target_status:
                    mapping.status = target_status
                    updated_fields.append("status")
                if mapping.user_id != user.id:
                    mapping.user = user
                    updated_fields.append("user")
                if mapping.organization_id != organization.id:
                    mapping.organization = organization
                    updated_fields.append("organization")
                if updated_fields:
                    updated_fields.append("updated_at")
                    mapping.save(update_fields=updated_fields)
                created = False
            else:
                mapping = ExternalUserMapping.objects.create(
                    instance=instance,
                    user=user,
                    organization=organization,
                    external_user_id=lms_user_id,
                    status=target_status,
                )
                created = True
        except IntegrityError:
            mapping = ExternalUserMapping.objects.select_for_update().filter(
                instance=instance,
                external_user_id=lms_user_id,
            ).first()
            if not mapping:
                mapping = ExternalUserMapping.objects.select_for_update().filter(
                    instance=instance,
                    user=user,
                    organization=organization,
                ).first()
            if mapping:
                if mapping.status != target_status or mapping.user_id != user.id or mapping.organization_id != organization.id:
                    mapping.status = target_status
                    mapping.user = user
                    mapping.organization = organization
                    mapping.save(update_fields=["status", "user", "organization", "updated_at"])
            created = False

    return {
        "user_id": str(user.id),
        "organization_id": str(organization.id),
        "external_user_id": lms_user_id,
        "lms_user_id": resp.get("lms_user_id"),
        "role": lms_role,
        "action_taken": resp.get("action_taken", "created" if created else "existing"),
        "is_active": is_active,
        "status": "success",
    }


def execute_provisioning_job(
    job_or_id: Union[ProvisioningJob, str, uuid.UUID],
    client: Optional[LmsConnectorClient] = None,
) -> ProvisioningJob:
    """Executes a queued or retry-scheduled ProvisioningJob synchronously.

    Manages state transitions:
    - QUEUED -> PROCESSING -> COMPLETED (on success)
    - PROCESSING -> FAILED (on error)
    Integrates with IntegrationFailure and retry_service for automated retry scheduling.
    """
    job_id = job_or_id.id if isinstance(job_or_id, ProvisioningJob) else job_or_id
    with transaction.atomic():
        try:
            job = (
                ProvisioningJob.objects.select_for_update()
                .select_related("instance", "organization")
                .get(pk=job_id)
            )
        except ProvisioningJob.DoesNotExist:
            raise ProvisioningServiceError(f"ProvisioningJob '{job_id}' does not exist.", code="JOB_NOT_FOUND")

        # Idempotent guard: if already completed, do not re-execute
        if job.status == ProvisioningJobStatus.COMPLETED:
            return job

        # Transition to PROCESSING
        job.status = ProvisioningJobStatus.PROCESSING
        job.save(update_fields=["status", "updated_at"])

    started_at = timezone.now()
    try:
        if job.user is None:
            # Org-level action
            if job.action in (ProvisioningAction.PROVISION, ProvisioningAction.UPDATE, ProvisioningAction.SYNC):
                result = provision_tenant_to_lms(
                    organization=job.organization,
                    instance=job.instance,
                    client=client,
                    status_override=job.context.get("target_status"),
                )
            elif job.action == ProvisioningAction.DEPROVISION:
                # Deprovision: marks tenant inactive in LMS
                result = provision_tenant_to_lms(
                    organization=job.organization,
                    instance=job.instance,
                    client=client,
                    status_override="Inactive",
                )
            else:
                raise ProvisioningServiceError(f"Unsupported tenant action: {job.action}", code="UNSUPPORTED_ACTION")
        else:
            # User-level action: enforce tenant provisioning dependency first
            if not ExternalTenantMapping.objects.filter(instance=job.instance, organization=job.organization).exists():
                tenant_job = ProvisioningJob.objects.filter(
                    instance=job.instance,
                    organization=job.organization,
                    user=None,
                    status__in=[ProvisioningJobStatus.QUEUED, ProvisioningJobStatus.PROCESSING],
                ).first()
                if tenant_job and tenant_job.id != job.id:
                    execute_provisioning_job(tenant_job, client=client)
                else:
                    provision_tenant_to_lms(job.organization, instance=job.instance, client=client)

            is_active = (
                job.context.get("is_active", True)
                if job.action != ProvisioningAction.DEPROVISION
                else False
            )
            result = provision_user_to_lms(
                user=job.user,
                organization=job.organization,
                is_active=is_active,
                instance=job.instance,
                client=client,
            )

        # Mark COMPLETED
        job.status = ProvisioningJobStatus.COMPLETED
        job.completed_at = timezone.now()
        job.context = {**job.context, "result": result}
        job.save(update_fields=["status", "completed_at", "context", "updated_at"])

        # Auto-resolve reconciliation issue if this job originated from one
        if job.context.get("reconciliation_issue_id"):
            from apps.integration_hub.reconciliation_service import verify_and_resolve_reconciliation_issue
            try:
                verify_and_resolve_reconciliation_issue(job)
            except Exception as rec_err:
                logger.warning(f"Could not auto-resolve reconciliation issue for job {job.id}: {rec_err}")

        # Resolve open failure if one was previously recorded
        with transaction.atomic():
            locked_job = ProvisioningJob.objects.select_for_update().get(pk=job.id)
            failure = IntegrationFailure.objects.select_for_update().filter(
                job=locked_job,
                status__in=[FailureStatus.OPEN, FailureStatus.RETRY_SCHEDULED],
            ).first()
            if failure:
                try:
                    completed_at = timezone.now()
                    record_failure_attempt(
                        failure=failure,
                        started_at=started_at,
                        completed_at=completed_at,
                        outcome=AttemptOutcome.SUCCESS,
                        failure_code="",
                        failure_detail="Resolved automatically on successful job execution.",
                        http_status=None,
                        retry_after=None,
                    )
                    replay_actor_id = locked_job.context.get("replayed_by_id")
                    actor_user = None
                    if replay_actor_id:
                        from django.contrib.auth import get_user_model
                        actor_user = get_user_model().objects.filter(pk=replay_actor_id).first()
                    notes = f"Resolved automatically after replay by {actor_user.email}." if actor_user else "Resolved automatically on successful job execution."
                    resolve_failure(failure, user=actor_user, notes=notes)
                except Exception as res_err:
                    logger.warning(f"Could not mark failure resolved for job {job.id}: {res_err}")

        return job

    except Exception as exc:
        completed_at = timezone.now()
        failure_code = getattr(exc, "failure_code", None) or getattr(exc, "code", "SERVICE_UNAVAILABLE")
        failure_detail = getattr(exc, "detail", str(exc))
        http_status = getattr(exc, "status_code", None)
        clean_detail = sanitize_diagnostic_detail(failure_detail)

        if getattr(exc, "is_retryable", None) is False:
            failure_type = FailureType.PERMANENT
        else:
            failure_type = classify_failure(failure_code)

        # Find or create failure record with row-level serialization
        with transaction.atomic():
            locked_job = ProvisioningJob.objects.select_for_update().get(pk=job.id)
            failure = IntegrationFailure.objects.select_for_update().filter(job=locked_job).first()
            if not failure:
                failure = IntegrationFailure.objects.create(
                    job=locked_job,
                    failure_code=failure_code,
                    failure_detail=clean_detail,
                    failure_type=failure_type,
                )
            else:
                failure.failure_code = failure_code
                failure.failure_detail = clean_detail
                failure.failure_type = failure_type
                failure.status = FailureStatus.OPEN
                failure.save(update_fields=["failure_code", "failure_detail", "failure_type", "status"])

            if failure_type == FailureType.TRANSIENT and failure.retry_count < failure.max_retries:
                schedule_failure_retry(failure)
                locked_job.status = ProvisioningJobStatus.RETRY_SCHEDULED
            else:
                mark_failure_dead_letter(
                    failure,
                    reason=f"Exhausted retries or permanent error: {failure_code}",
                )
                locked_job.status = ProvisioningJobStatus.FAILED

            locked_job.save(update_fields=["status", "updated_at"])

            record_failure_attempt(
                failure=failure,
                started_at=started_at,
                completed_at=completed_at,
                outcome=AttemptOutcome.FAILURE,
                failure_code=failure_code,
                failure_detail=clean_detail,
                http_status=http_status,
                retry_after=failure.retry_after,
            )

        logger.error(f"ProvisioningJob {job.id} failed: [{failure_code}] {clean_detail}")
        raise
