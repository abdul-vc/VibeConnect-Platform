"""Stable identifiers and constants for VibeConnect Phase 2E Access Control.

Defines console context types, canonical module keys, and permission keys.
"""

# Console Context Types
CONTEXT_PLATFORM_OWNER = "platform_owner"
CONTEXT_TENANT = "tenant"

# Platform Owner Console Module Keys
PO_MODULE_OVERVIEW = "po_overview"
PO_MODULE_PRODUCTS = "po_products"
PO_MODULE_PLANS = "po_plans"
PO_MODULE_SUBSCRIPTIONS = "po_subscriptions"
PO_MODULE_ORGANIZATIONS = "po_organizations"
PO_MODULE_USERS = "po_users"
PO_MODULE_ENTITLEMENTS = "po_entitlements"
PO_MODULE_ACTIVITY_LOG = "po_activity_log"

PLATFORM_OWNER_MODULE_KEYS = (
    PO_MODULE_OVERVIEW,
    PO_MODULE_PRODUCTS,
    PO_MODULE_PLANS,
    PO_MODULE_SUBSCRIPTIONS,
    PO_MODULE_ORGANIZATIONS,
    PO_MODULE_USERS,
    PO_MODULE_ENTITLEMENTS,
    PO_MODULE_ACTIVITY_LOG,
)

# Tenant Console Module Keys
TENANT_MODULE_LANDING = "tenant_landing"
TENANT_MODULE_ROLES = "tenant_roles"

# Tenant Permission Keys
PERMISSION_ROLES_VIEW = "roles.view"
PERMISSION_ROLES_MANAGE = "roles.manage"
PERMISSION_ROLES_ASSIGN = "roles.assign"

# Support Console Context & Module Key
CONTEXT_SUPPORT = "support"
SUPPORT_MODULE_CONSOLE = "support_console"

# Support Permission Keys (Phase 6C & 6D)
PERMISSION_SUPPORT_DIAGNOSTICS_VIEW = "support.diagnostics.view"
PERMISSION_SUPPORT_OPERATIONS_RETRY = "support.operations.retry"
PERMISSION_SUPPORT_OPERATIONS_RESOLVE = "support.operations.resolve"
PERMISSION_SUPPORT_IMPERSONATION_INITIATE = "support.impersonation.initiate"

SUPPORT_PERMISSION_KEYS = (
    PERMISSION_SUPPORT_DIAGNOSTICS_VIEW,
    PERMISSION_SUPPORT_OPERATIONS_RETRY,
    PERMISSION_SUPPORT_OPERATIONS_RESOLVE,
    PERMISSION_SUPPORT_IMPERSONATION_INITIATE,
)

# Predefined Support System Role Codes
SUPPORT_ROLE_DIAGNOSTICS_VIEWER = "support_diagnostics_viewer"
SUPPORT_ROLE_OPERATOR = "support_operator"
SUPPORT_ROLE_REMEDIATION_OPERATOR = "support_remediation_operator"

PREDEFINED_SUPPORT_ROLES = frozenset([
    SUPPORT_ROLE_DIAGNOSTICS_VIEWER,
    SUPPORT_ROLE_OPERATOR,
    SUPPORT_ROLE_REMEDIATION_OPERATOR,
])



