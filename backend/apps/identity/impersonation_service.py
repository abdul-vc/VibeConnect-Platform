"""Support Impersonation Governance and Context Service for VibeConnect Phase 6D.

Provides authoritative lifecycle management and per-request verification
for time-limited, audited Support Operator impersonation sessions.
"""

import uuid
from typing import Any

from django.core.exceptions import ValidationError
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied

from apps.access_control.constants import (
    CONTEXT_SUPPORT,
    CONTEXT_TENANT,
    PERMISSION_SUPPORT_IMPERSONATION_INITIATE,
)
from apps.access_control.services.evaluation import evaluate_access
from apps.auditlog.models import AuditAction, AuditOperationSource, AuditTargetType
from apps.auditlog.services import record_audit_event
from apps.identity.models import (
    ImpersonationSessionStatus,
    PlatformUser,
    SupportImpersonationSession,
    UserStatus,
)
from apps.organizations.models import (
    MembershipStatus,
    MembershipType,
    Organization,
    OrganizationMembership,
    OrganizationStatus,
)

HEADER_IMPERSONATION_SESSION = "HTTP_X_VIBECONNECT_IMPERSONATION_SESSION"

BLOCKED_IMPERSONATION_DOMAINS = {
    "credentials",
    "password",
    "roles",
    "permissions",
    "ceilings",
    "entitlements",
    "api_keys",
    "billing",
    "subscriptions",
}


def create_impersonation_session(
    *,
    operator: PlatformUser,
    target_user_id: uuid.UUID | str,
    target_organization_id: uuid.UUID | str,
    reason: str,
    ticket_reference: str = "",
    correlation_id: uuid.UUID | str | None = None,
) -> SupportImpersonationSession:
    """Create and activate a new time-limited SupportImpersonationSession."""
    # 1. Operator Permission Verification
    is_platform_owner = getattr(operator, "is_platform_owner", False)
    eval_result = evaluate_access(operator, CONTEXT_SUPPORT, None)
    if not (is_platform_owner or eval_result.has_permission(PERMISSION_SUPPORT_IMPERSONATION_INITIATE)):
        raise PermissionDenied(
            {"code": "INSUFFICIENT_PRIVILEGES", "detail": "Operator lacks 'support.impersonation.initiate' permission."}
        )

    # 2. Reason & Ticket Reference Validation
    clean_reason = (reason or "").strip()
    if not clean_reason:
        raise ValidationError("Reason is required and cannot be empty.", code="REASON_REQUIRED")
    if len(clean_reason) > 500:
        raise ValidationError("Reason cannot exceed 500 characters.", code="REASON_TOO_LONG")

    clean_ticket = (ticket_reference or "").strip()
    if not clean_ticket:
        raise ValidationError("Ticket reference is required and cannot be empty.", code="TICKET_REFERENCE_REQUIRED")
    if len(clean_ticket) > 100:
        raise ValidationError("Ticket reference cannot exceed 100 characters.", code="TICKET_REFERENCE_TOO_LONG")

    # 3. Target User & Organization Resolution
    try:
        t_user_uuid = uuid.UUID(str(target_user_id))
    except (ValueError, TypeError):
        raise ValidationError("Invalid target user ID.", code="INVALID_TARGET_USER")

    try:
        t_org_uuid = uuid.UUID(str(target_organization_id))
    except (ValueError, TypeError):
        raise ValidationError("Invalid target organization ID.", code="INVALID_TARGET_ORG")

    target_user = PlatformUser.objects.filter(pk=t_user_uuid).first()
    if not target_user:
        raise ValidationError("Target user does not exist.", code="TARGET_USER_NOT_FOUND")

    target_org = Organization.objects.filter(pk=t_org_uuid).first()
    if not target_org:
        raise ValidationError("Target organization does not exist.", code="TARGET_ORG_NOT_FOUND")

    corr_uuid = uuid.UUID(str(correlation_id)) if correlation_id else uuid.uuid4()

    # Terminate any existing active session for this operator
    existing_active = SupportImpersonationSession.objects.filter(
        operator=operator,
        status=ImpersonationSessionStatus.ACTIVE,
    )
    for s in existing_active:
        s.status = ImpersonationSessionStatus.TERMINATED
        s.terminated_at = timezone.now()
        s.save(update_fields=["status", "terminated_at"])

    # 4. Instantiate & Validate Session Model (Server computes 30-min cap and enforces target rules)
    now = timezone.now()
    session = SupportImpersonationSession(
        operator=operator,
        target_user=target_user,
        target_organization=target_org,
        reason=clean_reason,
        ticket_reference=clean_ticket,
        correlation_id=corr_uuid,
        expires_at=now + timezone.timedelta(minutes=30),
    )
    session.full_clean()
    session.save()

    # 5. Dual-Actor Audit Logging of Session Initiation
    record_audit_event(
        action=AuditAction.SUPPORT_IMPERSONATION_STARTED,
        target_type=AuditTargetType.SUPPORT_IMPERSONATION,
        target_id=session.id,
        target_repr=f"Session {session.id}: {operator.id} -> {target_user.id}",
        actor=operator,
        organization_id=target_org.id,
        operation_source=AuditOperationSource.INTERACTIVE,
        correlation_id=corr_uuid,
        metadata={
            "session_id": str(session.id),
            "operator_id": str(operator.id),
            "target_user_id": str(target_user.id),
            "target_organization_id": str(target_org.id),
            "reason": session.reason,
            "ticket_reference": session.ticket_reference,
            "correlation_id": str(corr_uuid),
            "status": session.status,
            "lifecycle_event": "started",
        },
    )


    return session


def terminate_impersonation_session(
    *,
    session_id: uuid.UUID | str,
    actor: PlatformUser,
    reason: str = "Operator terminated session.",
) -> SupportImpersonationSession:
    """Terminate an active impersonation session."""
    try:
        s_uuid = uuid.UUID(str(session_id))
    except (ValueError, TypeError):
        raise ValidationError("Invalid session ID.", code="INVALID_SESSION_ID")

    session = SupportImpersonationSession.objects.filter(pk=s_uuid).select_related(
        "operator", "target_user", "target_organization"
    ).first()
    if not session:
        raise ValidationError("Session not found.", code="SESSION_NOT_FOUND")

    is_platform_owner = getattr(actor, "is_platform_owner", False)
    if not (is_platform_owner or session.operator_id == actor.id or session.target_user_id == actor.id):
        raise PermissionDenied(
            {"code": "INSUFFICIENT_PRIVILEGES", "detail": "Only the initiating operator, target user, or Platform Owner can terminate."}
        )

    if session.status == ImpersonationSessionStatus.ACTIVE:
        session.status = ImpersonationSessionStatus.TERMINATED
        session.terminated_at = timezone.now()
        session.save(update_fields=["status", "terminated_at"])

        record_audit_event(
            action=AuditAction.SUPPORT_IMPERSONATION_TERMINATED,
            target_type=AuditTargetType.SUPPORT_IMPERSONATION,
            target_id=session.id,
            target_repr=f"Terminated Session {session.id}",
            actor=actor,
            organization_id=session.target_organization.id,
            operation_source=AuditOperationSource.INTERACTIVE,
            correlation_id=session.correlation_id,
            metadata={
                "session_id": str(session.id),
                "operator_id": str(session.operator.id),
                "target_user_id": str(session.target_user.id),
                "target_organization_id": str(session.target_organization.id),
                "reason": (reason or "Operator terminated session.").strip()[:500],
                "ticket_reference": session.ticket_reference,
                "correlation_id": str(session.correlation_id),
                "status": session.status,
                "lifecycle_event": "terminated",
            },

        )

    return session


def revalidate_request_impersonation(request: Any) -> SupportImpersonationSession | None:
    """Re-validate impersonation context on every request opting into it.

    Checks:
    - Opt-in header `X-VibeConnect-Impersonation-Session`
    - Operator matches authenticated user (`request.user`)
    - Session active status
    - Server-side expiry re-checked per-request (auto-expires with audit record if expired)
    - Target user and organization active status re-validated
    - NEVER mutates or reassigns `request.user`!
    """
    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return None

    raw_session_id = request.META.get(HEADER_IMPERSONATION_SESSION)
    if not raw_session_id and hasattr(request, "session"):
        raw_session_id = request.session.get("impersonation_session_id")

    if not raw_session_id:
        return None

    try:
        session_uuid = uuid.UUID(str(raw_session_id).strip())
    except (ValueError, TypeError):
        raise PermissionDenied({"code": "INVALID_IMPERSONATION_SESSION", "detail": "Invalid impersonation session header."})

    session = (
        SupportImpersonationSession.objects.filter(pk=session_uuid)
        .select_related("operator", "target_user", "target_organization")
        .first()
    )
    if not session:
        raise PermissionDenied({"code": "IMPERSONATION_SESSION_NOT_FOUND", "detail": "Impersonation session not found."})

    # Validate operator matches authenticated principal
    if session.operator_id != user.id:
        raise PermissionDenied(
            {"code": "IMPERSONATION_OPERATOR_MISMATCH", "detail": "Authenticated user is not the session operator."}
        )

    now = timezone.now()

    # Re-validate session status and per-request expiry
    if session.status != ImpersonationSessionStatus.ACTIVE or now >= session.expires_at:
        if session.status == ImpersonationSessionStatus.ACTIVE:
            session.status = ImpersonationSessionStatus.EXPIRED
            session.terminated_at = session.expires_at
            session.save(update_fields=["status", "terminated_at"])

            # System-triggered audit of session expiry
            record_audit_event(
                action=AuditAction.SUPPORT_IMPERSONATION_EXPIRED,
                target_type=AuditTargetType.SUPPORT_IMPERSONATION,
                target_id=session.id,
                target_repr=f"Expired Session {session.id}",
                actor=user,
                organization_id=session.target_organization.id,
                operation_source=AuditOperationSource.INTEGRATION,
                correlation_id=session.correlation_id,
                metadata={
                    "session_id": str(session.id),
                    "operator_id": str(session.operator.id),
                    "target_user_id": str(session.target_user.id),
                    "target_organization_id": str(session.target_organization.id),
                    "reason": "Session reached 30-minute expiry cap.",
                    "ticket_reference": session.ticket_reference,
                    "correlation_id": str(session.correlation_id),
                    "status": session.status,
                    "lifecycle_event": "expired",
                },

            )

        raise PermissionDenied({"code": "IMPERSONATION_SESSION_EXPIRED", "detail": "Impersonation session has expired."})

    # Re-validate target user active state
    if getattr(session.target_user, "status", None) != UserStatus.ACTIVE or not session.target_user.is_active:
        session.status = ImpersonationSessionStatus.REVOKED
        session.terminated_at = now
        session.save(update_fields=["status", "terminated_at"])
        raise PermissionDenied({"code": "TARGET_USER_INACTIVE", "detail": "Target user is no longer active."})

    # Re-validate target organization active state
    if session.target_organization.status != OrganizationStatus.ACTIVE:
        session.status = ImpersonationSessionStatus.REVOKED
        session.terminated_at = now
        session.save(update_fields=["status", "terminated_at"])
        raise PermissionDenied({"code": "TARGET_ORG_INACTIVE", "detail": "Target organization is no longer active."})

    # Re-validate active membership in target organization
    has_membership = OrganizationMembership.objects.filter(
        user=session.target_user,
        organization=session.target_organization,
        status=MembershipStatus.ACTIVE,
        membership_type__in=[MembershipType.TENANT_ADMIN, MembershipType.MEMBER],
    ).exists()
    if not has_membership:
        session.status = ImpersonationSessionStatus.REVOKED
        session.terminated_at = now
        session.save(update_fields=["status", "terminated_at"])
        raise PermissionDenied({"code": "TARGET_MEMBERSHIP_INACTIVE", "detail": "Target user membership is no longer active."})

    # Attach impersonation context to request (without replacing request.user!)
    request.impersonation_session = session
    return session


ALLOWED_IMPERSONATION_DOMAINS = frozenset([
    "landing",
    "roles",
    "branding",
    "showcase",
    "catalog",
    "products",
    "notifications",
    "diagnostics",
    "overview",
])


def assert_operation_allowed_during_impersonation(request: Any, domain: str) -> None:
    """Enforce explicit allowlist of operations during an impersonation session."""
    impersonation_session = getattr(request, "impersonation_session", None)
    if not impersonation_session:
        return

    # Dedicated session termination operation exception:
    # Authenticated operator must be able to terminate the active session via POST.
    path = getattr(request, "path", "")
    if path and "/impersonation/sessions/" in path and path.rstrip("/").endswith("/terminate"):
        return

    method = getattr(request, "method", "GET")
    if method not in ("GET", "HEAD", "OPTIONS"):
        raise PermissionDenied(
            {
                "code": "OPERATION_BLOCKED_DURING_IMPERSONATION",
                "detail": "Mutations are strictly prohibited during an active impersonation session.",
            }
        )


    clean_domain = str(domain).lower().strip()
    if clean_domain not in ALLOWED_IMPERSONATION_DOMAINS:
        raise PermissionDenied(
            {
                "code": "OPERATION_BLOCKED_DURING_IMPERSONATION",
                "detail": f"Domain '{domain}' is not permitted during an active impersonation session.",
            }
        )
