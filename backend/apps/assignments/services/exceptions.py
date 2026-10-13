"""Domain exceptions for assignments and seat engine."""


class AssignmentServiceError(Exception):
    """Base exception for assignment service errors."""

    def __init__(self, message: str = "", code: str = "ASSIGNMENT_SERVICE_ERROR"):
        super().__init__(message)
        self.message = message
        self.code = code


class MultipleActiveSubscriptionsError(AssignmentServiceError):
    """Raised when corrupt data or concurrent state exposes multiple temporally eligible subscriptions."""

    def __init__(self, message: str = "Multiple active subscriptions found.", code: str = "MULTIPLE_ACTIVE_SUBSCRIPTIONS"):
        super().__init__(message, code=code)


class SeatQuotaUnconfiguredError(AssignmentServiceError):
    """Raised when no seat quota is configured at either product scope or plan scope."""

    def __init__(self, message: str = "Seat quota is unconfigured.", code: str = "SEAT_QUOTA_UNCONFIGURED"):
        super().__init__(message, code=code)


class InvalidSeatQuotaConfigError(AssignmentServiceError):
    """Raised when seat quota configuration is malformed, ambiguous, fractional, negative, or soft."""

    def __init__(self, message: str = "Invalid seat quota configuration.", code: str = "INVALID_SEAT_QUOTA_CONFIG"):
        super().__init__(message, code=code)


class SeatLimitExceededError(AssignmentServiceError):
    """Raised when an allocation is attempted but no available seats remain in the pool."""

    def __init__(self, message: str = "Seat limit exceeded for the governing pool.", code: str = "SEAT_LIMIT_EXCEEDED"):
        super().__init__(message, code=code)


class ProductNotEntitledError(AssignmentServiceError):
    """Raised when a product is not entitled under the active subscription snapshot."""

    def __init__(self, message: str = "Product is not entitled under the subscription snapshot.", code: str = "PRODUCT_NOT_ENTITLED"):
        super().__init__(message, code=code)


class SubscriptionUnavailableError(AssignmentServiceError):
    """Raised when an organization has no temporally eligible active or trialing subscription."""

    def __init__(self, message: str = "No open, temporally eligible subscription exists.", code: str = "SUBSCRIPTION_UNAVAILABLE"):
        super().__init__(message, code=code)


class AlreadyAssignedError(AssignmentServiceError):
    """Raised when an active or suspended assignment already exists for the user and product."""

    def __init__(self, message: str = "User already holds an active or suspended assignment for this product.", code: str = "ALREADY_ASSIGNED"):
        super().__init__(message, code=code)


class InvalidStateTransitionError(AssignmentServiceError):
    """Raised when an invalid assignment lifecycle transition is requested."""

    def __init__(self, message: str = "Invalid assignment state transition.", code: str = "INVALID_STATE_TRANSITION"):
        super().__init__(message, code=code)


class InvalidReasonError(AssignmentServiceError):
    """Raised when a required lifecycle transition reason is missing, empty, or exceeds 500 characters."""

    def __init__(self, message: str = "Reason must be between 1 and 500 characters.", code: str = "INVALID_REASON"):
        super().__init__(message, code=code)


class UserInactiveError(AssignmentServiceError):
    """Raised when a requested user is not in active status."""

    def __init__(self, message: str = "User is not active.", code: str = "USER_INACTIVE"):
        super().__init__(message, code=code)


class UserDisabledError(AssignmentServiceError):
    """Raised when a requested user account is disabled."""

    def __init__(self, message: str = "User account is disabled.", code: str = "USER_DISABLED"):
        super().__init__(message, code=code)


class MembershipIneligibleError(AssignmentServiceError):
    """Raised when membership does not belong to the organization/user or is not active."""

    def __init__(self, message: str = "Membership is ineligible or not active.", code: str = "MEMBERSHIP_INELIGIBLE"):
        super().__init__(message, code=code)


class ProductInactiveError(AssignmentServiceError):
    """Raised when the target product is not active in the catalog."""

    def __init__(self, message: str = "Product is inactive in the catalog.", code: str = "PRODUCT_INACTIVE"):
        super().__init__(message, code=code)


class InvalidModuleIdsError(AssignmentServiceError):
    """Raised when requested module IDs are invalid, belong to a different product, or are inactive."""

    def __init__(self, message: str = "Invalid module IDs provided.", code: str = "INVALID_MODULE_IDS"):
        super().__init__(message, code=code)


class ModuleNotEntitledError(AssignmentServiceError):
    """Raised when a module is not entitled under the subscription snapshot."""

    def __init__(self, message: str = "Module is not entitled under the subscription snapshot.", code: str = "MODULE_NOT_ENTITLED"):
        super().__init__(message, code=code)


class OrganizationNotActiveError(AssignmentServiceError):
    """Raised when the target organization is not active."""

    def __init__(self, message: str = "Organization is not active.", code: str = "ORGANIZATION_NOT_ACTIVE"):
        super().__init__(message, code=code)


class AssignmentNotFoundError(AssignmentServiceError):
    """Raised when the target assignment record cannot be found."""

    def __init__(self, message: str = "Assignment not found.", code: str = "ASSIGNMENT_NOT_FOUND"):
        super().__init__(message, code=code)

