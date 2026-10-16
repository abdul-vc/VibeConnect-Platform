"""Organization Domain Services.

Provides canonical domain services for organization lifecycle transitions.
"""

from typing import Any
import uuid

from django.db import transaction
from django.utils import timezone

from apps.organizations.models import Organization, OrganizationStatus


@transaction.atomic
def retire_organization(
    *,
    organization_id: uuid.UUID | str,
    actor: Any,
    reason: str = "Organization retired",
) -> Organization:
    """Atomically retire an organization, cancelling subscriptions and revoking assignments."""
    clean_id = uuid.UUID(str(organization_id))
    org = Organization.objects.select_for_update().get(id=clean_id)

    if org.status != OrganizationStatus.RETIRED:
        org.status = OrganizationStatus.RETIRED
        if actor:
            org.updated_by = actor
        org.save(update_fields=["status", "updated_by", "updated_at"])

    # 1. Cancel open subscriptions
    from apps.subscriptions.services import cancel_open_subscriptions_for_organization
    cancel_open_subscriptions_for_organization(org=org, actor=actor, reason=reason)

    # 2. Revoke all active and suspended assignments
    from apps.assignments.services import revoke_assignments_for_organization
    revoke_assignments_for_organization(organization_id=org.id, actor=actor, reason=reason)

    # 3. LMS Lifecycle Integration Hook
    from apps.integration_hub.lifecycle_service import handle_tenant_deactivated_or_suspended
    handle_tenant_deactivated_or_suspended(org, status=OrganizationStatus.RETIRED, actor=actor, reason=reason)

    return org


@transaction.atomic
def suspend_organization(
    *,
    organization_id: uuid.UUID | str,
    actor: Any,
    reason: str = "Organization suspended",
) -> Organization:
    """Atomically suspend an organization and synchronize with integrations."""
    clean_id = uuid.UUID(str(organization_id))
    org = Organization.objects.select_for_update().get(id=clean_id)

    if org.status != OrganizationStatus.SUSPENDED:
        org.status = OrganizationStatus.SUSPENDED
        if actor:
            org.updated_by = actor
        org.save(update_fields=["status", "updated_by", "updated_at"])

    # LMS Lifecycle Integration Hook
    from apps.integration_hub.lifecycle_service import handle_tenant_deactivated_or_suspended
    handle_tenant_deactivated_or_suspended(org, status=OrganizationStatus.SUSPENDED, actor=actor, reason=reason)

    return org
