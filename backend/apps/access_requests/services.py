"""Access Requests & Approvals Domain Services (Phase 3F).

Provides atomic workflows for creating, approving, denying, and cancelling
product access requests. Seamlessly delegates seat ceiling checks and entitlement
evaluations to the Phase 2F assignment service upon approval.
"""

import logging
from typing import Any
import uuid

from django.contrib.auth import get_user_model
from django.db import transaction

from apps.access_requests.models import (
    AccessRequest,
    AccessRequestDecision,
    AccessRequestDecisionType,
    AccessRequestStatus,
)
from apps.assignments.models import AssignmentStatus, UserProductAssignment
from apps.assignments.services import (
    AlreadyAssignedError,
    MembershipIneligibleError,
    ProductInactiveError,
    assign_user_to_product,
)
from apps.auditlog.models import AuditAction, AuditOperationSource, AuditTargetType
from apps.auditlog.services import record_audit_event
from apps.notifications.services import send as notification_send
from apps.organizations.models import (
    MembershipStatus,
    MembershipType,
    Organization,
    OrganizationMembership,
)
from apps.product_registry.models import Product, ProductStatus

logger = logging.getLogger(__name__)
PlatformUser = get_user_model()


class AccessRequestError(Exception):
    """Base exception for access request operations."""

    def __init__(self, message: str, code: str = "ACCESS_REQUEST_ERROR"):
        super().__init__(message)
        self.message = message
        self.code = code


class DuplicateAccessRequestError(AccessRequestError):
    def __init__(self, message: str = "A pending access request already exists for this product."):
        super().__init__(message, code="DUPLICATE_ACCESS_REQUEST")


class InvalidRequestStatusError(AccessRequestError):
    def __init__(self, message: str = "Access request is not in pending status."):
        super().__init__(message, code="INVALID_REQUEST_STATUS")


class AccessRequestNotFoundError(AccessRequestError):
    def __init__(self, message: str = "Access request not found."):
        super().__init__(message, code="ACCESS_REQUEST_NOT_FOUND")


class InvalidReasonError(AccessRequestError):
    def __init__(self, message: str = "Denial reason must be between 1 and 500 characters."):
        super().__init__(message, code="INVALID_REASON")


def create_access_request(
    *,
    organization: Organization,
    requester: Any,
    product: Product,
    requested_modules: list[str] | None = None,
    reason: str = "",
) -> AccessRequest:
    """Create a new pending product access request for a tenant member.

    Validates active membership, catalog product status, and checks for existing
    assignments or active duplicate pending requests.
    """
    # 1. Validate active membership
    is_active_member = OrganizationMembership.objects.filter(
        organization=organization,
        user=requester,
        status=MembershipStatus.ACTIVE,
    ).exists()
    if not is_active_member:
        raise MembershipIneligibleError(
            f"User '{requester.email}' is not an active member of organization '{organization.code}'.",
            code="MEMBERSHIP_INELIGIBLE",
        )

    # 2. Validate product status
    if product.status != ProductStatus.ACTIVE:
        raise ProductInactiveError(
            f"Product '{product.code}' is not in active catalog status.",
            code="PRODUCT_INACTIVE",
        )

    # 3. Check for existing active assignment
    has_assignment = UserProductAssignment.objects.filter(
        organization=organization,
        user=requester,
        product=product,
        status__in=[AssignmentStatus.ACTIVE, AssignmentStatus.SUSPENDED],
    ).exists()
    if has_assignment:
        raise AlreadyAssignedError(
            f"User '{requester.email}' already has an active or suspended assignment for product '{product.code}'.",
            code="ALREADY_ASSIGNED",
        )

    # 4. Check for existing pending request
    has_pending = AccessRequest.objects.filter(
        organization=organization,
        requester=requester,
        product=product,
        status=AccessRequestStatus.PENDING,
    ).exists()
    if has_pending:
        raise DuplicateAccessRequestError()

    request = AccessRequest.objects.create(
        organization=organization,
        requester=requester,
        product=product,
        requested_modules=requested_modules or [],
        reason=reason.strip() if reason else "",
        status=AccessRequestStatus.PENDING,
    )

    # Record Audit Event
    record_audit_event(
        action=AuditAction.ACCESS_REQUEST_CREATED,
        target_type=AuditTargetType.ACCESS_REQUEST,
        target_id=request.id,
        target_repr=f"Access Request {request.id} for {product.code} by {requester.email}",
        actor=requester,
        organization_id=organization.id,
        operation_source=AuditOperationSource.INTERACTIVE,
        correlation_id=request.id,
        metadata={
            "request_id": str(request.id),
            "requester_email": requester.email,
            "product_code": product.code,
            "product_name": product.name,
            "status": request.status,
        },
    )

    return request


def approve_access_request(
    *,
    request_id: uuid.UUID | str,
    approver: Any,
    reason: str = "",
) -> tuple[AccessRequest, UserProductAssignment]:
    """Approve a pending access request, granting access via Phase 2F assignment service.

    Re-evaluates membership eligibility and seat ceiling at decision time.
    If seat capacity is exceeded, the request remains pending and raises SeatLimitExceededError.
    If requester membership ended, the request is auto-cancelled.
    """
    try:
        req = AccessRequest.objects.get(id=request_id)
    except AccessRequest.DoesNotExist:
        raise AccessRequestNotFoundError()

    if req.status != AccessRequestStatus.PENDING:
        raise InvalidRequestStatusError(
            f"Cannot approve request with status '{req.status}'. Must be 'pending'."
        )

    # Re-validate requester membership
    membership = OrganizationMembership.objects.filter(
        organization=req.organization,
        user=req.requester,
    ).first()

    if not membership or membership.status != MembershipStatus.ACTIVE:
        req.status = AccessRequestStatus.CANCELLED
        req.save(update_fields=["status", "updated_at"])
        record_audit_event(
            action=AuditAction.ACCESS_REQUEST_CANCELLED,
            target_type=AuditTargetType.ACCESS_REQUEST,
            target_id=req.id,
            target_repr=f"Access Request {req.id} auto-cancelled due to inactive membership",
            actor=approver,
            organization_id=req.organization_id,
            operation_source=AuditOperationSource.INTERACTIVE,
            correlation_id=req.id,
            metadata={
                "request_id": str(req.id),
                "requester_email": req.requester.email,
                "reason": "Requester membership inactive at approval time",
            },
        )
        raise MembershipIneligibleError(
            f"Requester '{req.requester.email}' membership is no longer active. Request auto-cancelled.",
            code="MEMBERSHIP_INELIGIBLE",
        )

    with transaction.atomic():
        req = AccessRequest.objects.select_for_update().get(id=request_id)
        if req.status != AccessRequestStatus.PENDING:
            raise InvalidRequestStatusError(
                f"Cannot approve request with status '{req.status}'. Must be 'pending'."
            )

        # Execute assignment via Phase 2F assignment engine (re-validates ceiling and entitlements)
        assignment = assign_user_to_product(
            organization_id=req.organization_id,
            user_id=req.requester_id,
            product_id=req.product_id,
            module_ids=req.requested_modules or None,
            actor=approver,
            correlation_id=req.id,
        )

        # Record immutable decision
        AccessRequestDecision.objects.create(
            request=req,
            approver=approver,
            decision=AccessRequestDecisionType.APPROVED,
            reason=reason.strip() if reason else "",
        )

        req.status = AccessRequestStatus.APPROVED
        req.save(update_fields=["status", "updated_at"])

        # Record Audit Event
        record_audit_event(
            action=AuditAction.ACCESS_REQUEST_APPROVED,
            target_type=AuditTargetType.ACCESS_REQUEST,
            target_id=req.id,
            target_repr=f"Access Request {req.id} approved by {approver.email}",
            actor=approver,
            organization_id=req.organization_id,
            operation_source=AuditOperationSource.INTERACTIVE,
            correlation_id=req.id,
            metadata={
                "request_id": str(req.id),
                "requester_email": req.requester.email,
                "approver_email": approver.email,
                "product_code": req.product.code if req.product else "",
                "product_name": req.product.name if req.product else "",
                "decision": AccessRequestDecisionType.APPROVED,
                "status": req.status,
            },
        )

        # Notify requester
        try:
            notification_send(
                template_code="access_request_approved",
                recipient_email=req.requester.email,
                recipient_user=req.requester,
                context={
                    "product_name": req.product.name if req.product else "Product",
                    "org_name": req.organization.name,
                    "approver_email": approver.email,
                },
                execute_sync=True,
            )
        except Exception as exc:
            logger.warning("Access request approval notification delivery skipped: %s", exc)

        return req, assignment


def deny_access_request(
    *,
    request_id: uuid.UUID | str,
    approver: Any,
    reason: str,
) -> AccessRequest:
    """Deny a pending access request with mandatory explanation reason."""
    if not isinstance(reason, str) or not (1 <= len(reason.strip()) <= 500):
        raise InvalidReasonError()

    clean_reason = reason.strip()

    with transaction.atomic():
        try:
            req = AccessRequest.objects.select_for_update().get(id=request_id)
        except AccessRequest.DoesNotExist:
            raise AccessRequestNotFoundError()

        if req.status != AccessRequestStatus.PENDING:
            raise InvalidRequestStatusError(
                f"Cannot deny request with status '{req.status}'. Must be 'pending'."
            )

        AccessRequestDecision.objects.create(
            request=req,
            approver=approver,
            decision=AccessRequestDecisionType.DENIED,
            reason=clean_reason,
        )

        req.status = AccessRequestStatus.DENIED
        req.save(update_fields=["status", "updated_at"])

        # Record Audit Event
        record_audit_event(
            action=AuditAction.ACCESS_REQUEST_DENIED,
            target_type=AuditTargetType.ACCESS_REQUEST,
            target_id=req.id,
            target_repr=f"Access Request {req.id} denied by {approver.email}",
            actor=approver,
            organization_id=req.organization_id,
            operation_source=AuditOperationSource.INTERACTIVE,
            correlation_id=req.id,
            metadata={
                "request_id": str(req.id),
                "requester_email": req.requester.email,
                "approver_email": approver.email,
                "product_code": req.product.code if req.product else "",
                "product_name": req.product.name if req.product else "",
                "decision": AccessRequestDecisionType.DENIED,
                "reason": clean_reason,
                "status": req.status,
            },
        )

        # Notify requester
        try:
            notification_send(
                template_code="access_request_denied",
                recipient_email=req.requester.email,
                recipient_user=req.requester,
                context={
                    "product_name": req.product.name if req.product else "Product",
                    "org_name": req.organization.name,
                    "reason": clean_reason,
                },
                execute_sync=True,
            )
        except Exception as exc:
            logger.warning("Access request denial notification delivery skipped: %s", exc)

        return req


def cancel_access_request(
    *,
    request_id: uuid.UUID | str,
    actor: Any,
) -> AccessRequest:
    """Cancel a pending access request by requester or authorized administrator."""
    with transaction.atomic():
        try:
            req = AccessRequest.objects.select_for_update().get(id=request_id)
        except AccessRequest.DoesNotExist:
            raise AccessRequestNotFoundError()

        if req.status != AccessRequestStatus.PENDING:
            raise InvalidRequestStatusError(
                f"Cannot cancel request with status '{req.status}'. Must be 'pending'."
            )

        is_owner = getattr(actor, "is_platform_owner", False)
        is_requester = actor.id == req.requester_id
        is_admin = OrganizationMembership.objects.filter(
            organization=req.organization,
            user=actor,
            membership_type=MembershipType.TENANT_ADMIN,
            status=MembershipStatus.ACTIVE,
        ).exists()

        if not (is_owner or is_requester or is_admin):
            raise AccessRequestError(
                "You do not have permission to cancel this access request.",
                code="PERMISSION_DENIED",
            )

        req.status = AccessRequestStatus.CANCELLED
        req.save(update_fields=["status", "updated_at"])

        # Record Audit Event
        record_audit_event(
            action=AuditAction.ACCESS_REQUEST_CANCELLED,
            target_type=AuditTargetType.ACCESS_REQUEST,
            target_id=req.id,
            target_repr=f"Access Request {req.id} cancelled by {actor.email}",
            actor=actor,
            organization_id=req.organization_id,
            operation_source=AuditOperationSource.INTERACTIVE,
            correlation_id=req.id,
            metadata={
                "request_id": str(req.id),
                "requester_email": req.requester.email,
                "product_code": req.product.code if req.product else "",
                "product_name": req.product.name if req.product else "",
                "status": req.status,
            },
        )

        return req
