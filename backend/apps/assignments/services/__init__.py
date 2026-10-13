"""Assignments services package.

Exports canonical domain services, seat engine resolvers, access evaluators,
and domain exceptions.
"""

from apps.assignments.services.assignment_services import (
    assign_user_to_product,
    reactivate_user_assignment,
    replace_user_module_assignments,
    revoke_assignments_for_membership,
    revoke_assignments_for_organization,
    revoke_user_assignment,
    suspend_user_assignment,
)
from apps.assignments.services.eligibility import (
    UserProductAccessResult,
    evaluate_user_product_access,
)
from apps.assignments.services.exceptions import (
    AlreadyAssignedError,
    AssignmentNotFoundError,
    AssignmentServiceError,
    InvalidModuleIdsError,
    InvalidReasonError,
    InvalidSeatQuotaConfigError,
    InvalidStateTransitionError,
    MembershipIneligibleError,
    ModuleNotEntitledError,
    MultipleActiveSubscriptionsError,
    OrganizationNotActiveError,
    ProductInactiveError,
    ProductNotEntitledError,
    SeatLimitExceededError,
    SeatQuotaUnconfiguredError,
    SubscriptionUnavailableError,
    UserDisabledError,
    UserInactiveError,
)
from apps.assignments.services.seat_engine import (
    SeatQuotaResolution,
    get_temporally_eligible_subscription,
    normalize_seat_limit,
    resolve_governing_seat_pool,
    resolve_seat_pool,
)

__all__ = [
    # Domain Mutation Services
    "assign_user_to_product",
    "suspend_user_assignment",
    "reactivate_user_assignment",
    "revoke_user_assignment",
    "replace_user_module_assignments",
    "revoke_assignments_for_membership",
    "revoke_assignments_for_organization",
    # Access Evaluation
    "evaluate_user_product_access",
    "UserProductAccessResult",
    # Seat Engine
    "get_temporally_eligible_subscription",
    "resolve_governing_seat_pool",
    "normalize_seat_limit",
    "SeatQuotaResolution",
    # Domain Exceptions
    "AssignmentServiceError",
    "MultipleActiveSubscriptionsError",
    "SeatQuotaUnconfiguredError",
    "InvalidSeatQuotaConfigError",
    "SeatLimitExceededError",
    "ProductNotEntitledError",
    "SubscriptionUnavailableError",
    "AlreadyAssignedError",
    "InvalidStateTransitionError",
    "InvalidReasonError",
    "UserInactiveError",
    "UserDisabledError",
    "MembershipIneligibleError",
    "ProductInactiveError",
    "InvalidModuleIdsError",
    "ModuleNotEntitledError",
    "OrganizationNotActiveError",
    "AssignmentNotFoundError",
]
