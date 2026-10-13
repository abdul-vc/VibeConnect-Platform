/**
 * Audit Log Domain API.
 *
 * Exclusively consumes the centralized apiClient to communicate with versioned audit log endpoints.
 */

import { apiClient } from "./client.ts";
import { ENDPOINTS } from "./endpoints.ts";
import type {
  AuditAction,
  AuditLogDetail,
  AuditLogListParams,
  AuditLogListResponse,
  AuditTargetType,
} from "./types.ts";

export const AUDIT_ACTION_LABELS: Record<AuditAction, string> = {
  product_created: "Product Created",
  product_updated: "Product Updated",
  product_retired: "Product Retired",
  module_created: "Module Created",
  module_updated: "Module Updated",
  module_retired: "Module Retired",
  feature_created: "Feature Created",
  feature_updated: "Feature Updated",
  feature_retired: "Feature Retired",
  capability_created: "Capability Created",
  capability_updated: "Capability Updated",
  capability_retired: "Capability Retired",
  organization_created: "Organization Created",
  organization_updated: "Organization Updated",
  organization_retired: "Organization Retired",
  entitlement_created: "Entitlement Created",
  entitlement_status_changed: "Entitlement Status Changed",
  entitlement_revoked: "Entitlement Revoked",
  login_success: "Login Success",
  logout_success: "Logout Success",
  // Plan domain
  plan_created: "Plan Created",
  plan_updated: "Plan Updated",
  plan_version_created: "Version Created",
  plan_version_updated: "Version Updated",
  plan_version_cloned: "Version Cloned",
  plan_version_activated: "Version Activated",
  plan_version_retired: "Version Retired",
  plan_price_created: "Price Added",
  plan_price_updated: "Price Updated",
  plan_price_removed: "Price Removed",
  plan_product_added: "Product Added to Plan",
  plan_product_removed: "Product Removed from Plan",
  plan_module_added: "Module Added to Plan",
  plan_module_removed: "Module Removed from Plan",
  plan_capability_added: "Capability Added to Plan",
  plan_capability_removed: "Capability Removed from Plan",
  plan_quota_created: "Quota Created",
  plan_quota_updated: "Quota Updated",
  plan_quota_removed: "Quota Removed",
  // Subscription domain
  subscription_created: "Subscription Created",
  subscription_trial_started: "Trial Started",
  subscription_trial_converted: "Trial Converted",
  subscription_trial_expired: "Trial Expired",
  subscription_plan_changed: "Plan Changed",
  subscription_suspended: "Subscription Suspended",
  subscription_reactivated: "Subscription Reactivated",
  subscription_cancelled: "Subscription Cancelled",
  subscription_reconciled: "Subscription Reconciled",
  // Phase 2D User & Membership domain
  user_created: "User Created",
  user_updated: "User Updated",
  user_suspended: "User Suspended",
  user_reactivated: "User Reactivated",
  user_disabled: "User Disabled",
  membership_created: "Membership Created",
  membership_updated: "Membership Updated",
  membership_suspended: "Membership Suspended",
  membership_reactivated: "Membership Reactivated",
  membership_ended: "Membership Ended",
  membership_restored: "Membership Restored",
  context_selected: "Context Selected",
};

export const AUDIT_TARGET_TYPE_LABELS: Record<AuditTargetType, string> = {
  product: "Product",
  module: "Module",
  feature: "Feature",
  capability: "Capability",
  organization: "Organization",
  entitlement: "Entitlement",
  auth: "Auth",
  // Plan domain
  plan: "Plan",
  plan_version: "Plan Version",
  plan_price: "Plan Price",
  plan_product: "Plan Product",
  plan_module: "Plan Module",
  plan_capability: "Plan Capability",
  plan_quota: "Plan Quota",
  // Subscription domain
  subscription: "Subscription",
  // Phase 2D Target Types
  user: "User",
  membership: "Membership",
};

export function getAuditActionBadgeClass(action: AuditAction): string {
  switch (action) {
    case "product_created":
    case "module_created":
    case "feature_created":
    case "capability_created":
    case "organization_created":
    case "entitlement_created":
    case "login_success":
    case "plan_created":
    case "plan_version_created":
    case "plan_version_activated":
    case "plan_price_created":
    case "plan_quota_created":
    case "plan_product_added":
    case "plan_module_added":
    case "plan_capability_added":
    case "subscription_created":
    case "subscription_trial_started":
    case "subscription_trial_converted":
    case "subscription_reactivated":
    case "user_created":
    case "user_reactivated":
    case "membership_created":
    case "membership_reactivated":
    case "membership_restored":
      return "badge-success";
    case "product_updated":
    case "module_updated":
    case "feature_updated":
    case "capability_updated":
    case "organization_updated":
    case "entitlement_status_changed":
    case "plan_updated":
    case "plan_version_updated":
    case "plan_version_cloned":
    case "plan_price_updated":
    case "plan_quota_updated":
    case "subscription_plan_changed":
    case "subscription_reconciled":
    case "user_updated":
    case "membership_updated":
    case "context_selected":
      return "badge-primary";
    case "product_retired":
    case "module_retired":
    case "feature_retired":
    case "capability_retired":
    case "organization_retired":
    case "plan_version_retired":
    case "subscription_suspended":
    case "subscription_trial_expired":
    case "user_suspended":
    case "membership_suspended":
    case "membership_ended":
      return "badge-warning";
    case "entitlement_revoked":
    case "plan_price_removed":
    case "plan_product_removed":
    case "plan_module_removed":
    case "plan_capability_removed":
    case "plan_quota_removed":
    case "subscription_cancelled":
    case "user_disabled":
      return "badge-danger";
    case "logout_success":
    default:
      return "badge-neutral";
  }
}

export interface RetentionEvaluationCategory {
  readonly model: string;
  readonly label: string;
  readonly proposed_retention: string;
  readonly candidate_count: number;
}

export interface RetentionEvaluationResponse {
  readonly status: string;
  readonly policy_status: string;
  readonly is_dry_run: boolean;
  readonly destructive_execution_allowed: boolean;
  readonly evaluated_at: string;
  readonly disclaimer: string;
  readonly categories: readonly RetentionEvaluationCategory[];
  readonly total_candidates: number;
}

export const auditApi = {
  /**
   * List audit logs with server-side pagination, search, filtering, and ordering.
   */
  async list(params?: AuditLogListParams, signal?: AbortSignal): Promise<AuditLogListResponse> {
    return apiClient.get<AuditLogListResponse>(ENDPOINTS.AUDIT_LOGS.LIST, {
      params,
      signal,
    });
  },

  /**
   * Retrieve single immutable audit log detail including allowlisted event metadata.
   */
  async get(id: string, signal?: AbortSignal): Promise<AuditLogDetail> {
    return apiClient.get<AuditLogDetail>(ENDPOINTS.AUDIT_LOGS.DETAIL(id), {
      signal,
    });
  },

  /**
   * Evaluate data retention candidates in strict read-only dry-run mode (Phase 6F).
   */
  async getRetentionEvaluation(signal?: AbortSignal): Promise<RetentionEvaluationResponse> {
    return apiClient.get<RetentionEvaluationResponse>(
      ENDPOINTS.AUDIT_LOGS.RETENTION_EVALUATION,
      { signal }
    );
  },

  /**
   * List organization-scoped audit logs for the active tenant admin.
   */
  async listTenant(
    params?: AuditLogListParams,
    signal?: AbortSignal
  ): Promise<AuditLogListResponse> {
    return apiClient.get<AuditLogListResponse>(ENDPOINTS.AUDIT_LOGS.TENANT_LIST, {
      params,
      signal,
    });
  },
};

/**
 * Format an ISO timestamp string into a standardized, deterministic UTC string:
 * 'YYYY-MM-DD HH:mm:ss UTC'
 */
export function formatUtcDateTime(isoString: string): string {
  try {
    const d = new Date(isoString);
    if (isNaN(d.getTime())) return isoString;
    const year = d.getUTCFullYear();
    const month = String(d.getUTCMonth() + 1).padStart(2, "0");
    const day = String(d.getUTCDate()).padStart(2, "0");
    const hours = String(d.getUTCHours()).padStart(2, "0");
    const minutes = String(d.getUTCMinutes()).padStart(2, "0");
    const seconds = String(d.getUTCSeconds()).padStart(2, "0");
    return `${year}-${month}-${day} ${hours}:${minutes}:${seconds} UTC`;
  } catch {
    return isoString;
  }
}
