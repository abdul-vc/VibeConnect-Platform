/**
 * Centralized API Endpoint Definitions.
 *
 * Versioned endpoint paths for VibeConnect master control plane.
 */

export const ENDPOINTS = {
  HEALTH: "/api/v1/health/",
  AUTH: {
    CSRF: "/api/v1/auth/csrf/",
    LOGIN: "/api/v1/auth/login/",
    ME: "/api/v1/auth/me/",
    LOGOUT: "/api/v1/auth/logout/",
    CONTEXT: "/api/v1/auth/context/",
  },
  PRODUCTS: {
    LIST: "/api/v1/products/",
    DETAIL: (id: string) => `/api/v1/products/${id}/`,
  },
  ORGANIZATIONS: {
    LIST: "/api/v1/organizations/",
    DETAIL: (id: string) => `/api/v1/organizations/${id}/`,
  },
  ORGANIZATION_PRODUCT_ENTITLEMENTS: {
    LIST: "/api/v1/organization-product-entitlements/",
    DETAIL: (id: string) => `/api/v1/organization-product-entitlements/${id}/`,
  },
  AUDIT_LOGS: {
    LIST: "/api/v1/audit-logs/",
    DETAIL: (id: string) => `/api/v1/audit-logs/${id}/`,
    RETENTION_EVALUATION: "/api/v1/audit-logs/retention-evaluation/",
    TENANT_LIST: "/api/v1/audit-logs/tenant/",
  },
  PRODUCT_MODULES: {
    LIST: "/api/v1/product-modules/",
    DETAIL: (id: string) => `/api/v1/product-modules/${id}/`,
  },
  PRODUCT_FEATURES: {
    LIST: "/api/v1/product-features/",
    DETAIL: (id: string) => `/api/v1/product-features/${id}/`,
  },
  PRODUCT_CAPABILITIES: {
    LIST: "/api/v1/product-capabilities/",
    DETAIL: (id: string) => `/api/v1/product-capabilities/${id}/`,
  },
  PLANS: {
    LIST: "/api/v1/plans/",
    DETAIL: (id: string) => `/api/v1/plans/${id}/`,
    VERSIONS: (id: string) => `/api/v1/plans/${id}/versions/`,
  },
  PLAN_VERSIONS: {
    DETAIL: (id: string) => `/api/v1/plan-versions/${id}/`,
    CLONE: (id: string) => `/api/v1/plan-versions/${id}/clone/`,
    READINESS: (id: string) => `/api/v1/plan-versions/${id}/readiness/`,
    ACTIVATE: (id: string) => `/api/v1/plan-versions/${id}/activate/`,
    RETIRE: (id: string) => `/api/v1/plan-versions/${id}/retire/`,
    PRICES: (id: string) => `/api/v1/plan-versions/${id}/prices/`,
    PRODUCTS: (id: string) => `/api/v1/plan-versions/${id}/products/`,
    MODULES: (id: string) => `/api/v1/plan-versions/${id}/modules/`,
    CAPABILITIES: (id: string) => `/api/v1/plan-versions/${id}/capabilities/`,
    QUOTAS: (id: string) => `/api/v1/plan-versions/${id}/quotas/`,
  },
  PLAN_QUOTAS: {
    DETAIL: (id: string) => `/api/v1/plan-quotas/${id}/`,
  },
  PLAN_PRICES: {
    DETAIL: (id: string) => `/api/v1/plan-prices/${id}/`,
  },
  PLAN_PRODUCTS: {
    DETAIL: (id: string) => `/api/v1/plan-products/${id}/`,
  },
  PLAN_MODULES: {
    DETAIL: (id: string) => `/api/v1/plan-modules/${id}/`,
  },
  PLAN_CAPABILITIES: {
    DETAIL: (id: string) => `/api/v1/plan-capabilities/${id}/`,
  },
  SUBSCRIPTIONS: {
    LIST: "/api/v1/subscriptions/",
    TRIAL: "/api/v1/subscriptions/trial/",
    DETAIL: (id: string) => `/api/v1/subscriptions/${id}/`,
    CONVERT_TRIAL: (id: string) => `/api/v1/subscriptions/${id}/convert-trial/`,
    CHANGE_PLAN: (id: string) => `/api/v1/subscriptions/${id}/change-plan/`,
    SUSPEND: (id: string) => `/api/v1/subscriptions/${id}/suspend/`,
    REACTIVATE: (id: string) => `/api/v1/subscriptions/${id}/reactivate/`,
    CANCEL: (id: string) => `/api/v1/subscriptions/${id}/cancel/`,
    RECONCILE: (id: string) => `/api/v1/subscriptions/${id}/reconcile/`,
    ENTITLEMENTS: (id: string) => `/api/v1/subscriptions/${id}/entitlements/`,
  },
  PUBLIC_PLANS: "/api/v1/public/plans/",
  USERS: {
    LIST: "/api/v1/users/",
    DETAIL: (id: string) => `/api/v1/users/${id}/`,
    SUSPEND: (id: string) => `/api/v1/users/${id}/suspend/`,
    REACTIVATE: (id: string) => `/api/v1/users/${id}/reactivate/`,
    DISABLE: (id: string) => `/api/v1/users/${id}/disable/`,
    ANONYMIZE: (id: string) => `/api/v1/users/${id}/anonymize/`,
  },
  MEMBERSHIPS: {
    LIST: (orgId: string) => `/api/v1/organizations/${orgId}/memberships/`,
    DETAIL: (orgId: string, id: string) => `/api/v1/organizations/${orgId}/memberships/${id}/`,
    SUSPEND: (orgId: string, id: string) => `/api/v1/organizations/${orgId}/memberships/${id}/suspend/`,
    REACTIVATE: (orgId: string, id: string) => `/api/v1/organizations/${orgId}/memberships/${id}/reactivate/`,
    END: (orgId: string, id: string) => `/api/v1/organizations/${orgId}/memberships/${id}/end/`,
    RESTORE: (orgId: string, id: string) => `/api/v1/organizations/${orgId}/memberships/${id}/restore/`,
  },
  TENANT_ROLES: {
    ACCESS_CATALOG: "/api/v1/tenant/access-catalog/",
    LIST: "/api/v1/tenant/roles/",
    DETAIL: (roleId: string) => `/api/v1/tenant/roles/${encodeURIComponent(roleId)}/`,
    RETIRE: (roleId: string) => `/api/v1/tenant/roles/${encodeURIComponent(roleId)}/retire/`,
    ADMIN_MEMBERSHIPS: "/api/v1/tenant/admin-memberships/",
    ASSIGN_ROLE: (membershipId: string) =>
      `/api/v1/tenant/admin-memberships/${encodeURIComponent(membershipId)}/role/`,
  },
  ASSIGNMENTS: {
    LIST: "/api/v1/tenant/assignments/",
    DETAIL: (id: string) => `/api/v1/tenant/assignments/${encodeURIComponent(id)}/`,
    SUSPEND: (id: string) => `/api/v1/tenant/assignments/${encodeURIComponent(id)}/suspend/`,
    REACTIVATE: (id: string) => `/api/v1/tenant/assignments/${encodeURIComponent(id)}/reactivate/`,
    REVOKE: (id: string) => `/api/v1/tenant/assignments/${encodeURIComponent(id)}/revoke/`,
    MODULES: (id: string) => `/api/v1/tenant/assignments/${encodeURIComponent(id)}/modules/`,
    SELECTORS: {
      PRODUCTS: "/api/v1/tenant/assignments/selectors/products/",
      MEMBERS: "/api/v1/tenant/assignments/selectors/members/",
      MODULES: "/api/v1/tenant/assignments/selectors/modules/",
    },
  },
  CONSOLE_POLICIES: {
    LIST: (orgId: string) => `/api/v1/organizations/${encodeURIComponent(orgId)}/console-policies/`,
    DETAIL: (orgId: string, moduleKey: string) =>
      `/api/v1/organizations/${encodeURIComponent(orgId)}/console-policies/${encodeURIComponent(moduleKey)}/`,
  },
  PERMISSION_CEILINGS: {
    LIST: (orgId: string) => `/api/v1/organizations/${encodeURIComponent(orgId)}/permission-ceilings/`,
    DETAIL: (orgId: string, permissionKey: string) =>
      `/api/v1/organizations/${encodeURIComponent(orgId)}/permission-ceilings/${encodeURIComponent(permissionKey)}/`,
  },
  TENANT_HOME: "/api/v1/tenant/home/",
  ONBOARDING: {
    CASES: "/api/v1/onboarding/cases/",
    CASE_DETAIL: (id: string) => `/api/v1/onboarding/cases/${encodeURIComponent(id)}/`,
    STEP: (id: string) => `/api/v1/onboarding/cases/${encodeURIComponent(id)}/step/`,
  },
  INVITATIONS: {
    ISSUE: "/api/v1/invitations/",
    VALIDATE: (token: string) => `/api/v1/invitations/${encodeURIComponent(token)}/`,
    ACCEPT: (token: string) => `/api/v1/invitations/${encodeURIComponent(token)}/accept/`,
  },
  BULK_IMPORT: {
    JOBS: "/api/v1/bulk-import/jobs/",
    JOB_DETAIL: (id: string) => `/api/v1/bulk-import/jobs/${encodeURIComponent(id)}/`,
    JOB_ROWS: (id: string) => `/api/v1/bulk-import/jobs/${encodeURIComponent(id)}/rows/`,
    COMMIT: (id: string) => `/api/v1/bulk-import/jobs/${encodeURIComponent(id)}/commit/`,
    RETRY: (id: string) => `/api/v1/bulk-import/jobs/${encodeURIComponent(id)}/retry/`,
    RECONCILIATION: (id: string) => `/api/v1/bulk-import/jobs/${encodeURIComponent(id)}/reconciliation/`,
    ERROR_REPORT: (id: string) => `/api/v1/bulk-import/jobs/${encodeURIComponent(id)}/error-report/`,
  },
  ACCESS_REQUESTS: {
    LIST: "/api/v1/access-requests/",
    DETAIL: (id: string) => `/api/v1/access-requests/${encodeURIComponent(id)}/`,
    APPROVE: (id: string) => `/api/v1/access-requests/${encodeURIComponent(id)}/approve/`,
    DENY: (id: string) => `/api/v1/access-requests/${encodeURIComponent(id)}/deny/`,
    CANCEL: (id: string) => `/api/v1/access-requests/${encodeURIComponent(id)}/cancel/`,
  },
  NOTIFICATIONS: {
    TEMPLATES: "/api/v1/notifications/templates/",
    TEMPLATE_DETAIL: (id: string) => `/api/v1/notifications/templates/${encodeURIComponent(id)}/`,
    NEW_VERSION: (id: string) => `/api/v1/notifications/templates/${encodeURIComponent(id)}/new-version/`,
    RETIRE: (id: string) => `/api/v1/notifications/templates/${encodeURIComponent(id)}/retire/`,
    PREVIEW: (id: string) => `/api/v1/notifications/templates/${encodeURIComponent(id)}/preview/`,
    DELIVERIES: "/api/v1/notifications/deliveries/",
  },
  SHOWCASE: {
    PROFILES: "/api/v1/showcase/profiles/",
    PROFILE_DETAIL: (id: string) => `/api/v1/showcase/profiles/${encodeURIComponent(id)}/`,
    PUBLISH: (id: string) => `/api/v1/showcase/profiles/${encodeURIComponent(id)}/publish/`,
    UNPUBLISH: (id: string) => `/api/v1/showcase/profiles/${encodeURIComponent(id)}/unpublish/`,
    LAUNCHABILITY: (id: string) => `/api/v1/showcase/profiles/${encodeURIComponent(id)}/launchability/`,
    MEDIA: (id: string) => `/api/v1/showcase/profiles/${encodeURIComponent(id)}/media/`,
    MEDIA_DELETE: (mediaId: string) => `/api/v1/showcase/media/${encodeURIComponent(mediaId)}/`,
    REORDER: "/api/v1/showcase/reorder/",
    DEMO_ENVS: (productId: string) => `/api/v1/showcase/products/${encodeURIComponent(productId)}/demo-environments/`,
    DEMO_ENV_DETAIL: (envId: string) => `/api/v1/showcase/demo-environments/${encodeURIComponent(envId)}/`,
    LAUNCH_CONFIG: (id: string) => `/api/v1/showcase/profiles/${encodeURIComponent(id)}/launch-config/`,
    LAUNCH_DEMO: (id: string) => `/api/v1/showcase/profiles/${encodeURIComponent(id)}/launch-demo/`,
    PRESENT: "/api/v1/showcase/present/",
    VMS_HEALTH: "/api/v1/showcase/vms/health/",
    VMS_OVERVIEW: "/api/v1/showcase/vms/overview/",
    VMS_INVENTORY: "/api/v1/showcase/vms/inventory/",
    VMS_DOCKS: "/api/v1/showcase/vms/docks/",
    VMS_WAVES: "/api/v1/showcase/vms/waves/",
    VMS_VEHICLES: "/api/v1/showcase/vms/vehicles/",
    VMS_REPORTS: "/api/v1/showcase/vms/reports/",
  },
  BRANDING: {
    ACTIVE: "/api/v1/branding/active/",
    PROFILES: "/api/v1/branding/profiles/",
    PROFILE_DETAIL: (id: string) => `/api/v1/branding/profiles/${encodeURIComponent(id)}/`,
    REVISIONS: (profileId: string) => `/api/v1/branding/profiles/${encodeURIComponent(profileId)}/revisions/`,
    REVISION_DETAIL: (id: string) => `/api/v1/branding/revisions/${encodeURIComponent(id)}/`,
    PUBLISH: (id: string) => `/api/v1/branding/revisions/${encodeURIComponent(id)}/publish/`,
    ROLLBACK: (id: string) => `/api/v1/branding/revisions/${encodeURIComponent(id)}/rollback/`,
    PREVIEW: (id: string) => `/api/v1/branding/revisions/${encodeURIComponent(id)}/preview/`,
    ASSETS: (profileId: string) => `/api/v1/branding/profiles/${encodeURIComponent(profileId)}/assets/`,
  },
  USAGE: {
    EVENTS: "/api/v1/usage/events/",
    TENANT_SUMMARY: "/api/v1/tenant/usage/",
    OWNER_LIST: "/api/v1/usage/",
  },
  BILLING: {
    ACCOUNTS: "/api/v1/billing/accounts/",
    ACCOUNT_DETAIL: (id: string) => `/api/v1/billing/accounts/${encodeURIComponent(id)}/`,
    INVOICES: "/api/v1/billing/invoices/",
    INVOICE_DETAIL: (id: string) => `/api/v1/billing/invoices/${encodeURIComponent(id)}/`,
    TENANT_INVOICES: "/api/v1/tenant/billing/invoices/",
    TENANT_ACCOUNT: "/api/v1/tenant/billing/account/",
    PAYMENTS: "/api/v1/billing/payments/",
    DUNNING_TRIGGER: "/api/v1/billing/dunning/trigger/",
    RECONCILIATIONS: "/api/v1/billing/reconciliations/",
    RECONCILIATION_RESOLVE: (id: string) => `/api/v1/billing/reconciliations/${encodeURIComponent(id)}/resolve/`,
    RECONCILIATION_TRIGGER: "/api/v1/billing/reconciliations/trigger/",
  },
  REPORTS: {
    OWNER_SUMMARY: "/api/v1/reports/summary/",
    TENANT_SUMMARY: "/api/v1/tenant/reports/",
    OWNER_ANALYTICS: "/api/v1/owner/analytics/",
    TENANT_ANALYTICS: "/api/v1/tenant/analytics/",
  },
  INTEGRATION: {
    CONNECTORS: "/api/v1/integration/connectors/",
    CONNECTOR_DETAIL: (id: string) => `/api/v1/integration/connectors/${encodeURIComponent(id)}/`,
    INSTANCES: "/api/v1/integration/instances/",
    INSTANCE_DETAIL: (id: string) => `/api/v1/integration/instances/${encodeURIComponent(id)}/`,
    EVENTS: "/api/v1/integration/events/",
    EVENT_INGEST: "/api/v1/integration/events/ingest/",
    PROVISIONING_JOBS: "/api/v1/integration/provisioning-jobs/",
    PROVISIONING_JOB_DETAIL: (id: string) => `/api/v1/integration/provisioning-jobs/${encodeURIComponent(id)}/`,
    EXTERNAL_IDENTITIES: "/api/v1/integration/external-identities/",
    TENANT_MAPPINGS: "/api/v1/integration/tenant-mappings/",
    USER_MAPPINGS: "/api/v1/integration/user-mappings/",
    RECONCILIATION: {
      LIST: "/api/v1/integration/reconciliation/",
      RUN: "/api/v1/integration/reconciliation/run/",
      RESOLVE: (id: string) => `/api/v1/integration/reconciliation/${encodeURIComponent(id)}/resolve/`,
    },
    HEALTH: "/api/v1/integration/health/",
    FAILURES: "/api/v1/integration/failures/",
    FAILURE_DETAIL: (id: string) => `/api/v1/integration/failures/${encodeURIComponent(id)}/`,
    FAILURE_RESOLVE: (id: string) => `/api/v1/integration/failures/${encodeURIComponent(id)}/resolve/`,
    FAILURE_MARK_DEAD_LETTER: (id: string) => `/api/v1/integration/failures/${encodeURIComponent(id)}/mark-dead-letter/`,
    FAILURE_SCHEDULE_RETRY: (id: string) => `/api/v1/integration/failures/${encodeURIComponent(id)}/schedule-retry/`,
    FAILURE_REPLAY: (id: string) => `/api/v1/integration/failures/${encodeURIComponent(id)}/replay/`,
  },
  SSO: {
    LAUNCH: "/api/v1/sso/launch/",
    VALIDATE: "/api/v1/sso/validate/",
    PILOT_STATUS: "/api/v1/sso/pilot-status/",
  },
  MARKETPLACE: {
    PRODUCTS: "/api/v1/marketplace/products/",
    PRODUCT_DETAIL: (codeOrId: string) => `/api/v1/marketplace/products/${encodeURIComponent(codeOrId)}/`,
    ENABLE: (codeOrId: string) => `/api/v1/marketplace/products/${encodeURIComponent(codeOrId)}/enable/`,
    REQUEST: (codeOrId: string) => `/api/v1/marketplace/products/${encodeURIComponent(codeOrId)}/request/`,
  },
  DEVELOPER: {
    TENANT: {
      APPS: "/api/v1/tenant/developer/apps/",
      APP_DETAIL: (id: string) => `/api/v1/tenant/developer/apps/${encodeURIComponent(id)}/`,
      APP_SUSPEND: (id: string) => `/api/v1/tenant/developer/apps/${encodeURIComponent(id)}/suspend/`,
      APP_REACTIVATE: (id: string) => `/api/v1/tenant/developer/apps/${encodeURIComponent(id)}/reactivate/`,
      APP_REVOKE: (id: string) => `/api/v1/tenant/developer/apps/${encodeURIComponent(id)}/revoke/`,
      KEYS: (appId: string) => `/api/v1/tenant/developer/apps/${encodeURIComponent(appId)}/keys/`,
      KEY_ROTATE: (appId: string, keyId: string) =>
        `/api/v1/tenant/developer/apps/${encodeURIComponent(appId)}/keys/${encodeURIComponent(keyId)}/rotate/`,
      KEY_REVOKE: (appId: string, keyId: string) =>
        `/api/v1/tenant/developer/apps/${encodeURIComponent(appId)}/keys/${encodeURIComponent(keyId)}/revoke/`,
      WEBHOOKS: (appId: string) => `/api/v1/tenant/developer/apps/${encodeURIComponent(appId)}/webhooks/`,
      WEBHOOK_DETAIL: (id: string) => `/api/v1/tenant/developer/webhooks/${encodeURIComponent(id)}/`,
      WEBHOOK_SUSPEND: (id: string) => `/api/v1/tenant/developer/webhooks/${encodeURIComponent(id)}/suspend/`,
      WEBHOOK_REACTIVATE: (id: string) => `/api/v1/tenant/developer/webhooks/${encodeURIComponent(id)}/reactivate/`,
      WEBHOOK_REVOKE: (id: string) => `/api/v1/tenant/developer/webhooks/${encodeURIComponent(id)}/revoke/`,
      WEBHOOK_ROTATE_SECRET: (id: string) => `/api/v1/tenant/developer/webhooks/${encodeURIComponent(id)}/rotate-secret/`,
      WEBHOOK_DELIVERIES: (id: string) => `/api/v1/tenant/developer/webhooks/${encodeURIComponent(id)}/deliveries/`,
      DELIVERY_REPLAY: (id: string) => `/api/v1/tenant/developer/deliveries/${encodeURIComponent(id)}/replay/`,
    },
    OWNER: {
      APPS: "/api/v1/owner/developer/apps/",
      APP_DETAIL: (id: string) => `/api/v1/owner/developer/apps/${encodeURIComponent(id)}/`,
      APP_SUSPEND: (id: string) => `/api/v1/owner/developer/apps/${encodeURIComponent(id)}/suspend/`,
      APP_REVOKE: (id: string) => `/api/v1/owner/developer/apps/${encodeURIComponent(id)}/revoke/`,
      KEYS: (appId: string) => `/api/v1/owner/developer/apps/${encodeURIComponent(appId)}/keys/`,
      KEY_REVOKE: (appId: string, keyId: string) =>
        `/api/v1/owner/developer/apps/${encodeURIComponent(appId)}/keys/${encodeURIComponent(keyId)}/revoke/`,
      WEBHOOKS: "/api/v1/owner/developer/webhooks/",
      WEBHOOK_DETAIL: (id: string) => `/api/v1/owner/developer/webhooks/${encodeURIComponent(id)}/`,
      WEBHOOK_SUSPEND: (id: string) => `/api/v1/owner/developer/webhooks/${encodeURIComponent(id)}/suspend/`,
      WEBHOOK_REVOKE: (id: string) => `/api/v1/owner/developer/webhooks/${encodeURIComponent(id)}/revoke/`,
      WEBHOOK_DELIVERIES: (id: string) => `/api/v1/owner/developer/webhooks/${encodeURIComponent(id)}/deliveries/`,
    },
  },
  SUPPORT: {
    ORGANIZATIONS: "/api/v1/support/organizations/",
    DIAGNOSTICS: (orgId: string) => `/api/v1/support/organizations/${encodeURIComponent(orgId)}/diagnostics/`,
    RETRY_FAILURE: (orgId: string, failureId: string) =>
      `/api/v1/support/organizations/${encodeURIComponent(orgId)}/failures/${encodeURIComponent(failureId)}/retry/`,
    REPLAY_FAILURE: (orgId: string, failureId: string) =>
      `/api/v1/support/organizations/${encodeURIComponent(orgId)}/failures/${encodeURIComponent(failureId)}/replay/`,
    RESOLVE_FAILURE: (orgId: string, failureId: string) =>
      `/api/v1/support/organizations/${encodeURIComponent(orgId)}/failures/${encodeURIComponent(failureId)}/resolve/`,
    RESOLVE_RECONCILIATION: (orgId: string, issueId: string) =>
      `/api/v1/support/organizations/${encodeURIComponent(orgId)}/reconciliation/${encodeURIComponent(issueId)}/resolve/`,
    IMPERSONATION_TARGETS: (orgId: string) =>
      `/api/v1/support/impersonation/eligible-targets/?organization_id=${encodeURIComponent(orgId)}`,
    IMPERSONATION_SESSIONS: "/api/v1/support/impersonation/sessions/",
    IMPERSONATION_ACTIVE_SESSION: "/api/v1/support/impersonation/sessions/active/",
    IMPERSONATION_TERMINATE: (sessionId: string) =>
      `/api/v1/support/impersonation/sessions/${encodeURIComponent(sessionId)}/terminate/`,
    OPERATORS: "/api/v1/owner/support-operators/",
    OPERATOR_DETAIL: (id: string) => `/api/v1/owner/support-operators/${encodeURIComponent(id)}/`,
  },
} as const;


export type EndpointKey = keyof typeof ENDPOINTS;

