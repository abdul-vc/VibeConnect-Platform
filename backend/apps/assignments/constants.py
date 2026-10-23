"""Access-State and Denial Code Constants (Phase 2G).

Authoritative definitions for product and module access states, denial codes,
and module evaluation states.
"""

from django.db import models


class AccessState(models.TextChoices):
    """Authoritative product access state enum (Phase 2G).

    Covers exactly the 10 defined states:
    1. available: All access checks passed, user can launch/access product.
    2. not_assigned: Entitled to organization, but user is not assigned.
    3. subscription_inactive: Subscription expired/suspended/cancelled, no active direct grant.
    4. entitlement_unavailable: Organization has no entitlement (subscription or direct grant).
    5. assignment_suspended: User product assignment is suspended.
    6. assignment_revoked: User product assignment is revoked.
    7. module_unavailable: Assigned but no entitled/active modules available to user.
    8. membership_inactive: User membership in organization is not active.
    9. product_unavailable: Product is disabled or retired in catalog.
    10. access_expired: Assignment or entitlement has expired.
    """

    AVAILABLE = "available", "Available"
    NOT_ASSIGNED = "not_assigned", "Not Assigned"
    SUBSCRIPTION_INACTIVE = "subscription_inactive", "Subscription Inactive"
    ENTITLEMENT_UNAVAILABLE = "entitlement_unavailable", "Entitlement Unavailable"
    ASSIGNMENT_SUSPENDED = "assignment_suspended", "Assignment Suspended"
    ASSIGNMENT_REVOKED = "assignment_revoked", "Assignment Revoked"
    MODULE_UNAVAILABLE = "module_unavailable", "Module Unavailable"
    MEMBERSHIP_INACTIVE = "membership_inactive", "Membership Inactive"
    PRODUCT_UNAVAILABLE = "product_unavailable", "Product Unavailable"
    ACCESS_EXPIRED = "access_expired", "Access Expired"
    INTEGRATION_PENDING = "integration_pending", "Integration Pending"


class DenialCode(models.TextChoices):
    """Denial code indicating the specific reason product access is unavailable."""

    NOT_ASSIGNED = "not_assigned", "User is not assigned to this product"
    SUBSCRIPTION_INACTIVE = "subscription_inactive", "Organization subscription is inactive"
    ENTITLEMENT_UNAVAILABLE = "entitlement_unavailable", "Organization has no active entitlement"
    ASSIGNMENT_SUSPENDED = "assignment_suspended", "User assignment is suspended"
    ASSIGNMENT_REVOKED = "assignment_revoked", "User assignment has been revoked"
    MODULE_UNAVAILABLE = "module_unavailable", "No assigned modules are entitled or active"
    MEMBERSHIP_INACTIVE = "membership_inactive", "User organization membership is inactive"
    PRODUCT_UNAVAILABLE = "product_unavailable", "Product is not active in the catalog"
    ACCESS_EXPIRED = "access_expired", "Access period has expired"
    INTEGRATION_PENDING = "integration_pending", "Product integration or SSO client is not configured"


class ModuleState(models.TextChoices):
    """Per-module entitlement and packaging state."""

    AVAILABLE = "available", "Available"
    UNAVAILABLE = "unavailable", "Unavailable"
    EXCLUDED = "excluded", "Excluded"
