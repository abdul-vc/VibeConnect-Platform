/**
 * Centralized API Type Definitions.
 */

export interface TenantOrganizationSummary {
  readonly id: string;
  readonly code: string;
  readonly name: string;
}

export type ConsoleContextType = "platform_owner" | "tenant" | "support";

export interface ConsoleContextSummary {
  readonly type: ConsoleContextType;
  readonly organization: TenantOrganizationSummary | null;
  readonly membership_type?: string;
}

export interface ActiveConsoleContext extends ConsoleContextSummary {
  readonly effective_permissions: readonly string[];
  readonly allowed_modules: readonly string[];
  readonly membership_type?: string;
}

export type ConsoleContext = ActiveConsoleContext;

export interface AuthenticatedUser {
  readonly id: string;
  readonly email: string;
  readonly full_name: string;
  readonly is_platform_owner: boolean;
  readonly active_context: ActiveConsoleContext | null;
  readonly available_contexts: readonly ConsoleContextSummary[];
}

export interface ContextSelectionPayload {
  readonly context_type: ConsoleContextType;
  readonly organization_id?: string;
}

export interface ContextSelectionResponse {
  readonly active_context: ActiveConsoleContext | null;
  readonly available_contexts: readonly ConsoleContextSummary[];
}

export interface LoginPayload {
  readonly email: string;
  readonly password: string;
}

export interface AuthDetailResponse {
  readonly detail: string;
}

export interface HealthResponse {
  readonly status: string;
  readonly service: string;
}

export type HealthCheckResponse = HealthResponse;

export type ProductStatus = "draft" | "active" | "inactive" | "retired";

export interface ProductAuditUser {
  readonly id: string;
  readonly full_name: string;
}

export interface ProductListItem {
  readonly id: string;
  readonly code: string;
  readonly name: string;
  readonly description: string;
  readonly status: ProductStatus;
  readonly created_at: string;
  readonly updated_at: string;
}

export interface ProductDetail extends ProductListItem {
  readonly created_by: ProductAuditUser;
  readonly updated_by: ProductAuditUser;
}

export interface ProductListResponse {
  readonly count: number;
  readonly next: string | null;
  readonly previous: string | null;
  readonly results: readonly ProductListItem[];
}

export interface CreateProductPayload {
  readonly code: string;
  readonly name: string;
  readonly description?: string;
}

export interface UpdateProductPayload {
  readonly name?: string;
  readonly description?: string;
  readonly status?: ProductStatus;
}

export type OrganizationStatus = "draft" | "active" | "suspended" | "retired";

export interface OrganizationAuditUser {
  readonly id: string;
  readonly full_name: string;
}

export interface OrganizationListItem {
  readonly id: string;
  readonly code: string;
  readonly name: string;
  readonly description: string;
  readonly status: OrganizationStatus;
  readonly created_at: string;
  readonly updated_at: string;
}

export interface OrganizationDetail extends OrganizationListItem {
  readonly created_by: OrganizationAuditUser;
  readonly updated_by: OrganizationAuditUser;
}

export interface OrganizationListResponse {
  readonly count: number;
  readonly next: string | null;
  readonly previous: string | null;
  readonly results: readonly OrganizationListItem[];
}

export interface CreateOrganizationPayload {
  readonly code: string;
  readonly name: string;
  readonly description?: string;
}

export interface UpdateOrganizationPayload {
  readonly name?: string;
  readonly description?: string;
  readonly status?: OrganizationStatus;
}

export type EntitlementStatus = "draft" | "active" | "suspended" | "revoked";

export interface EntitlementAuditUser {
  readonly id: string;
  readonly full_name: string;
}

export interface EntitlementOrganizationSummary {
  readonly id: string;
  readonly code: string;
  readonly name: string;
  readonly status: string;
}

export interface EntitlementProductSummary {
  readonly id: string;
  readonly code: string;
  readonly name: string;
  readonly status: string;
}

export interface EntitlementListItem {
  readonly id: string;
  readonly organization: EntitlementOrganizationSummary;
  readonly product: EntitlementProductSummary;
  readonly status: EntitlementStatus;
  readonly created_at: string;
  readonly updated_at: string;
}

export interface EntitlementDetail extends EntitlementListItem {
  readonly created_by: EntitlementAuditUser;
  readonly updated_by: EntitlementAuditUser;
}

export interface EntitlementListResponse {
  readonly count: number;
  readonly next: string | null;
  readonly previous: string | null;
  readonly results: readonly EntitlementListItem[];
}

export interface CreateEntitlementPayload {
  readonly organization_id: string;
  readonly product_id: string;
}

export interface UpdateEntitlementPayload {
  readonly status: EntitlementStatus;
}

export type AuditAction =
  | "product_created"
  | "product_updated"
  | "product_retired"
  | "module_created"
  | "module_updated"
  | "module_retired"
  | "feature_created"
  | "feature_updated"
  | "feature_retired"
  | "capability_created"
  | "capability_updated"
  | "capability_retired"
  | "organization_created"
  | "organization_updated"
  | "organization_retired"
  | "entitlement_created"
  | "entitlement_status_changed"
  | "entitlement_revoked"
  | "login_success"
  | "logout_success"
  // Plan domain
  | "plan_created"
  | "plan_updated"
  | "plan_version_created"
  | "plan_version_updated"
  | "plan_version_cloned"
  | "plan_version_activated"
  | "plan_version_retired"
  | "plan_price_created"
  | "plan_price_updated"
  | "plan_price_removed"
  | "plan_product_added"
  | "plan_product_removed"
  | "plan_module_added"
  | "plan_module_removed"
  | "plan_capability_added"
  | "plan_capability_removed"
  | "plan_quota_created"
  | "plan_quota_updated"
  | "plan_quota_removed"
  // Subscription domain
  | "subscription_created"
  | "subscription_trial_started"
  | "subscription_trial_converted"
  | "subscription_trial_expired"
  | "subscription_plan_changed"
  | "subscription_suspended"
  | "subscription_reactivated"
  | "subscription_cancelled"
  | "subscription_reconciled"
  // User & Membership domain (Phase 2D)
  | "user_created"
  | "user_updated"
  | "user_suspended"
  | "user_reactivated"
  | "user_disabled"
  | "membership_created"
  | "membership_updated"
  | "membership_suspended"
  | "membership_reactivated"
  | "membership_ended"
  | "membership_restored"
  | "context_selected";

export type AuditTargetType =
  | "product"
  | "module"
  | "feature"
  | "capability"
  | "organization"
  | "entitlement"
  | "auth"
  // Plan domain
  | "plan"
  | "plan_version"
  | "plan_price"
  | "plan_product"
  | "plan_module"
  | "plan_capability"
  | "plan_quota"
  // Subscription domain
  | "subscription"
  // Phase 2D Target Types
  | "user"
  | "membership";

export type AuditOperationSource = "interactive" | "authentication" | "bulk_import" | "integration";

export type AuditOrderingField =
  | "-timestamp"
  | "timestamp"
  | "-action"
  | "action"
  | "-target_type"
  | "target_type";

export interface AuditActorSnapshot {
  readonly id: string;
  readonly email: string;
  readonly full_name: string;
}

export interface AuditLogListItem {
  readonly id: string;
  readonly timestamp: string;
  readonly action: AuditAction;
  readonly target_type: AuditTargetType;
  readonly target_id: string;
  readonly target_repr: string;
  readonly organization_id: string | null;
  readonly operation_source: AuditOperationSource;
  readonly correlation_id: string | null;
  readonly actor: AuditActorSnapshot;
}

export interface AuditLogDetail extends AuditLogListItem {
  readonly metadata: Record<string, unknown>;
}

export interface AuditLogListResponse {
  readonly count: number;
  readonly next: string | null;
  readonly previous: string | null;
  readonly results: readonly AuditLogListItem[];
}

export interface AuditLogListParams {
  readonly page?: number;
  readonly page_size?: number;
  readonly search?: string;
  readonly action?: AuditAction;
  readonly target_type?: AuditTargetType;
  readonly actor_id?: string;
  readonly target_id?: string;
  readonly organization_id?: string;
  readonly date_from?: string;
  readonly date_to?: string;
  readonly ordering?: AuditOrderingField;
}

// ============================================================================
// PRODUCT CATALOG HIERARCHY DOMAIN TYPES (MODULE, FEATURE, CAPABILITY)
// ============================================================================

export type CatalogStatus = "draft" | "active" | "retired";

export type CatalogOrderingField =
  | "display_order"
  | "-display_order"
  | "name"
  | "-name"
  | "code"
  | "-code"
  | "created_at"
  | "-created_at";

// --- Product Module DTOs ---

export interface ProductModuleListItem {
  readonly id: string;
  readonly product_id: string;
  readonly product_code: string;
  readonly code: string;
  readonly name: string;
  readonly description: string;
  readonly display_order: number;
  readonly status: CatalogStatus;
  readonly total_features_count: number;
  readonly active_features_count: number;
  readonly created_at: string;
  readonly updated_at: string;
}

export interface ProductModuleDetail extends ProductModuleListItem {
  readonly created_by: ProductAuditUser;
  readonly updated_by: ProductAuditUser;
}

export interface ProductModuleListResponse {
  readonly count: number;
  readonly next: string | null;
  readonly previous: string | null;
  readonly results: readonly ProductModuleListItem[];
}

export interface CreateProductModulePayload {
  readonly product_id: string;
  readonly code: string;
  readonly name: string;
  readonly description?: string;
  readonly display_order?: number;
}

export interface ProductModuleListParams {
  readonly product_id: string;
  readonly page?: number;
  readonly page_size?: number;
  readonly search?: string;
  readonly status?: CatalogStatus;
  readonly ordering?: CatalogOrderingField;
}

// --- Product Feature DTOs ---

export interface ProductFeatureListItem {
  readonly id: string;
  readonly module_id: string;
  readonly module_code: string;
  readonly product_id: string;
  readonly product_code: string;
  readonly code: string;
  readonly name: string;
  readonly description: string;
  readonly display_order: number;
  readonly status: CatalogStatus;
  readonly total_capabilities_count: number;
  readonly active_capabilities_count: number;
  readonly created_at: string;
  readonly updated_at: string;
}

export interface ProductFeatureDetail extends ProductFeatureListItem {
  readonly created_by: ProductAuditUser;
  readonly updated_by: ProductAuditUser;
}

export interface ProductFeatureListResponse {
  readonly count: number;
  readonly next: string | null;
  readonly previous: string | null;
  readonly results: readonly ProductFeatureListItem[];
}

export interface CreateProductFeaturePayload {
  readonly module_id: string;
  readonly code: string;
  readonly name: string;
  readonly description?: string;
  readonly display_order?: number;
}

export interface ProductFeatureListParams {
  readonly module_id: string;
  readonly page?: number;
  readonly page_size?: number;
  readonly search?: string;
  readonly status?: CatalogStatus;
  readonly ordering?: CatalogOrderingField;
}

// --- Product Capability DTOs ---

export interface ProductCapabilityListItem {
  readonly id: string;
  readonly feature_id: string;
  readonly feature_code: string;
  readonly module_id: string;
  readonly module_code: string;
  readonly product_id: string;
  readonly product_code: string;
  readonly code: string;
  readonly name: string;
  readonly description: string;
  readonly display_order: number;
  readonly status: CatalogStatus;
  readonly created_at: string;
  readonly updated_at: string;
}

export interface ProductCapabilityDetail extends ProductCapabilityListItem {
  readonly created_by: ProductAuditUser;
  readonly updated_by: ProductAuditUser;
}

export interface ProductCapabilityListResponse {
  readonly count: number;
  readonly next: string | null;
  readonly previous: string | null;
  readonly results: readonly ProductCapabilityListItem[];
}

export interface CreateProductCapabilityPayload {
  readonly feature_id: string;
  readonly code: string;
  readonly name: string;
  readonly description?: string;
  readonly display_order?: number;
}

export interface ProductCapabilityListParams {
  readonly feature_id: string;
  readonly page?: number;
  readonly page_size?: number;
  readonly search?: string;
  readonly status?: CatalogStatus;
  readonly ordering?: CatalogOrderingField;
}

// --- Strict Discriminated PATCH Payloads ---

export interface CatalogMetadataPatchPayload {
  readonly status?: never;
  readonly name?: string;
  readonly description?: string;
  readonly display_order?: number;
  readonly code?: string;
}

export interface CatalogActivationPatchPayload {
  readonly status: "active";
  readonly name?: string;
  readonly description?: string;
  readonly display_order?: number;
  readonly code?: string;
}

export interface CatalogRetirementPatchPayload {
  readonly status: "retired";
  readonly name?: never;
  readonly description?: never;
  readonly display_order?: never;
  readonly code?: never;
}

export type CatalogPatchPayload =
  | CatalogMetadataPatchPayload
  | CatalogActivationPatchPayload
  | CatalogRetirementPatchPayload;

// ============================================================================
// PHASE 2B PLANS & PRICING TYPES
// ============================================================================

export type PlanVersionStatus = "draft" | "active" | "retired";
export type PlanCatalogHealth = "healthy" | "degraded";
export type CatalogHealthStaleItemType = "product" | "module" | "feature" | "capability";

export interface PlanAuditUser {
  readonly id: string;
  readonly email: string;
  readonly full_name: string;
}

export interface PlanVersionSummary {
  readonly id: string;
  readonly version: number;
  readonly status: PlanVersionStatus;
  readonly change_summary: string;
  readonly catalog_health: PlanCatalogHealth;
  readonly activated_at: string | null;
  readonly retired_at: string | null;
  readonly created_at: string;
  readonly updated_at: string;
}

export interface PlanListItem {
  readonly id: string;
  readonly code: string;
  readonly name: string;
  readonly description: string;
  readonly is_public: boolean;
  readonly active_version: PlanVersionSummary | null;
  readonly latest_version: PlanVersionSummary | null;
  readonly total_versions_count: number;
  readonly catalog_health: PlanCatalogHealth;
  readonly created_at: string;
  readonly updated_at: string;
}

export interface PlanDetail extends PlanListItem {
  readonly created_by?: PlanAuditUser;
  readonly updated_by?: PlanAuditUser;
}

export interface PlanListResponse {
  readonly count: number;
  readonly next: string | null;
  readonly previous: string | null;
  readonly results: readonly PlanListItem[];
}

export interface PlanListParams {
  readonly page?: number;
  readonly page_size?: number;
  readonly search?: string;
  readonly has_active_version?: "true" | "false" | "all";
  readonly has_draft_version?: "true" | "false" | "all";
  readonly catalog_health?: "healthy" | "degraded" | "all";
  readonly ordering?: string;
}

export interface CreatePlanPayload {
  readonly code: string;
  readonly name: string;
  readonly description?: string;
  readonly initial_version_change_summary?: string;
}

export interface UpdatePlanPayload {
  readonly name?: string;
  readonly description?: string;
  readonly is_public?: boolean;
}

export interface PlanVersionListItem {
  readonly id: string;
  readonly plan_id: string;
  readonly plan_code: string;
  readonly plan_name: string;
  readonly version: number;
  readonly status: PlanVersionStatus;
  readonly change_summary: string;
  readonly catalog_health: PlanCatalogHealth;
  readonly activated_at: string | null;
  readonly retired_at: string | null;
  readonly created_at: string;
  readonly updated_at: string;
}

export interface PlanVersionDetail extends PlanVersionListItem {
  readonly created_by?: PlanAuditUser;
  readonly updated_by?: PlanAuditUser;
}

export interface PlanVersionListResponse {
  readonly count: number;
  readonly next: string | null;
  readonly previous: string | null;
  readonly results: readonly PlanVersionListItem[];
}

export interface PlanVersionListParams {
  readonly page?: number;
  readonly page_size?: number;
  readonly status?: string;
  readonly ordering?: string;
}

export interface CreatePlanVersionPayload {
  readonly change_summary?: string;
}

export interface UpdatePlanVersionPayload {
  readonly change_summary: string;
}

export interface ClonePlanVersionPayload {
  readonly change_summary?: string;
}

export interface PlanStaleItem {
  readonly type: CatalogHealthStaleItemType;
  readonly id: string;
  readonly code: string;
  readonly name: string;
  readonly status: string;
}

export interface PlanReadinessResponse {
  readonly is_ready: boolean;
  readonly blockers: readonly string[];
  readonly warnings: readonly string[];
  readonly prices_count: number;
  readonly products_count: number;
  readonly catalog_health: PlanCatalogHealth;
  readonly stale_items: readonly PlanStaleItem[];
}

// --- Commercial Pricing Types ---
export type PlanCurrency = "INR" | "USD" | "EUR" | "GBP";
export type PlanBillingInterval = "monthly" | "quarterly" | "annual";

export interface PlanPriceListItem {
  readonly id: string;
  readonly plan_version_id: string;
  readonly currency: PlanCurrency;
  readonly billing_interval: PlanBillingInterval;
  readonly amount: string;
  readonly created_at: string;
  readonly updated_at: string;
}

export interface PlanPriceListResponse {
  readonly count: number;
  readonly next: string | null;
  readonly previous: string | null;
  readonly results: readonly PlanPriceListItem[];
}

export interface PlanPriceListParams {
  readonly page?: number;
  readonly page_size?: number;
  readonly currency?: PlanCurrency;
  readonly billing_interval?: PlanBillingInterval;
  readonly ordering?: "currency" | "billing_interval" | "amount" | "-amount";
}

export interface CreatePlanPricePayload {
  readonly currency: PlanCurrency;
  readonly billing_interval: PlanBillingInterval;
  readonly amount: string;
}

export interface UpdatePlanPricePayload {
  readonly amount: string;
}

// --- Commercial Packaging Types ---
export interface PlanProductListItem {
  readonly id: string;
  readonly plan_version_id: string;
  readonly product_id: string;
  readonly product_code: string;
  readonly product_name: string;
  readonly created_at: string;
}

export interface PlanProductListResponse {
  readonly count: number;
  readonly next: string | null;
  readonly previous: string | null;
  readonly results: readonly PlanProductListItem[];
}

export interface PlanProductListParams {
  readonly page?: number;
  readonly page_size?: number;
  readonly search?: string;
  readonly ordering?: "product__code" | "-product__code" | "created_at";
}

export interface CreatePlanProductPayload {
  readonly product_id: string;
}

export interface PlanModuleListItem {
  readonly id: string;
  readonly plan_version_id: string;
  readonly plan_product_id: string;
  readonly module_id: string;
  readonly module_code: string;
  readonly module_name: string;
  readonly created_at: string;
}

export interface PlanModuleListResponse {
  readonly count: number;
  readonly next: string | null;
  readonly previous: string | null;
  readonly results: readonly PlanModuleListItem[];
}

export interface PlanModuleListParams {
  readonly page?: number;
  readonly page_size?: number;
  readonly search?: string;
  readonly plan_product_id?: string;
  readonly ordering?: "module__code" | "-module__code" | "created_at";
}

export interface CreatePlanModulePayload {
  readonly plan_product_id: string;
  readonly module_id: string;
}

export interface PlanCapabilityListItem {
  readonly id: string;
  readonly plan_version_id: string;
  readonly plan_module_id: string;
  readonly capability_id: string;
  readonly capability_code: string;
  readonly capability_name: string;
  readonly feature_id: string;
  readonly feature_code: string;
  readonly feature_name: string;
  readonly created_at: string;
}

export interface PlanCapabilityListResponse {
  readonly count: number;
  readonly next: string | null;
  readonly previous: string | null;
  readonly results: readonly PlanCapabilityListItem[];
}

export interface PlanCapabilityListParams {
  readonly page?: number;
  readonly page_size?: number;
  readonly search?: string;
  readonly plan_module_id?: string;
  readonly ordering?: "capability__code" | "-capability__code";
}

export interface CreatePlanCapabilityPayload {
  readonly plan_module_id: string;
  readonly capability_id: string;
}

// ============================================================================
// PLAN QUOTAS (STAGE 1C-2B)
// ============================================================================

export type PlanQuotaScope = "plan" | "product" | "module" | "capability";
export type PlanQuotaLimitType = "numeric" | "unlimited";
export type PlanQuotaResetPeriod = "never" | "monthly" | "annual";

export type PlanQuotaUnit = string;

export interface PlanQuotaListItem {
  readonly id: string;
  readonly plan_version_id: string;
  readonly scope: PlanQuotaScope;
  readonly quota_key: string;
  readonly name: string;
  readonly unit: string;
  readonly limit_type: PlanQuotaLimitType;
  readonly limit_value: string | null;
  readonly is_hard_limit: boolean;
  readonly reset_period: PlanQuotaResetPeriod;
  readonly target_id: string | null;
  readonly created_at: string;
  readonly updated_at: string;
}

export interface PlanQuotaListResponse {
  readonly count: number;
  readonly next: string | null;
  readonly previous: string | null;
  readonly results: readonly PlanQuotaListItem[];
}

export interface PlanQuotaListParams {
  readonly page?: number;
  readonly page_size?: number;
  readonly search?: string;
  readonly scope?: PlanQuotaScope;
  readonly ordering?: "scope" | "quota_key" | "name";
}

export interface CreatePlanQuotaPayload {
  readonly scope: PlanQuotaScope;
  readonly quota_key: string;
  readonly name: string;
  readonly unit: string;
  readonly limit_type: PlanQuotaLimitType;
  readonly limit_value?: string | null;
  readonly is_hard_limit?: boolean;
  readonly reset_period?: PlanQuotaResetPeriod;
  readonly plan_product_id?: string | null;
  readonly plan_module_id?: string | null;
  readonly plan_capability_id?: string | null;
}

export interface UpdatePlanQuotaPayload {
  readonly name?: string;
  readonly unit?: string;
  readonly limit_type?: PlanQuotaLimitType;
  readonly limit_value?: string | null;
  readonly is_hard_limit?: boolean;
  readonly reset_period?: PlanQuotaResetPeriod;
}

// ============================================================================
// PHASE 2C SUBSCRIPTION MANAGEMENT DOMAIN TYPES
// ============================================================================

export type SubscriptionStatus =
  | "trialing"
  | "active"
  | "suspended"
  | "cancelled"
  | "expired";

export interface SubscriptionListItem {
  readonly id: string;
  readonly organization_id: string;
  readonly organization_name: string;
  readonly organization_code: string;
  readonly plan_version_id: string;
  readonly plan_price_id: string;
  readonly previous_subscription_id: string | null;
  readonly plan_code_snapshot: string;
  readonly plan_name_snapshot: string;
  readonly version_number_snapshot: number;
  readonly billing_interval: PlanBillingInterval;
  readonly currency: PlanCurrency;
  readonly amount: string;
  readonly started_as_trial: boolean;
  readonly trial_started_at: string | null;
  readonly trial_ends_at: string | null;
  readonly status: SubscriptionStatus;
  readonly current_period_start: string | null;
  readonly current_period_end: string | null;
  readonly cancelled_at: string | null;
  readonly ended_at: string | null;
  readonly change_reason: string;
  readonly cancellation_reason: string;
  readonly suspension_reason: string;
  readonly created_at: string;
  readonly updated_at: string;
  readonly created_by_email: string;
  readonly updated_by_email: string;
}

export type SubscriptionDetail = SubscriptionListItem;

export interface SubscriptionListResponse {
  readonly count: number;
  readonly next: string | null;
  readonly previous: string | null;
  readonly results: readonly SubscriptionListItem[];
}

export interface SubscriptionListParams {
  readonly page?: number;
  readonly page_size?: number;
  readonly organization_id?: string;
  readonly plan_id?: string;
  readonly status?: SubscriptionStatus;
  readonly search?: string;
  readonly ordering?: string;
}

export interface SubscriptionProductEntitlement {
  readonly id: string;
  readonly subscription_id: string;
  readonly organization_id: string;
  readonly product_id: string;
  readonly plan_product_id: string;
  readonly product_code_snapshot: string;
  readonly product_name_snapshot: string;
  readonly created_at: string;
}

export interface SubscriptionModuleEntitlement {
  readonly id: string;
  readonly subscription_id: string;
  readonly organization_id: string;
  readonly module_id: string;
  readonly plan_module_id: string;
  readonly module_code_snapshot: string;
  readonly module_name_snapshot: string;
  readonly created_at: string;
}

export interface SubscriptionCapabilityEntitlement {
  readonly id: string;
  readonly subscription_id: string;
  readonly organization_id: string;
  readonly capability_id: string;
  readonly plan_capability_id: string;
  readonly capability_code_snapshot: string;
  readonly capability_name_snapshot: string;
  readonly created_at: string;
}

export interface SubscriptionQuotaEntitlement {
  readonly id: string;
  readonly subscription_id: string;
  readonly organization_id: string;
  readonly plan_quota_id: string;
  readonly quota_key: string;
  readonly name: string;
  readonly scope: PlanQuotaScope;
  readonly product_id: string | null;
  readonly module_id: string | null;
  readonly capability_id: string | null;
  readonly target_code_snapshot: string;
  readonly target_name_snapshot: string;
  readonly limit_type: PlanQuotaLimitType;
  readonly limit_value: string | null;
  readonly unit: string;
  readonly is_hard_limit: boolean;
  readonly reset_period: PlanQuotaResetPeriod;
  readonly created_at: string;
}

export interface SubscriptionEntitlementsResponse {
  readonly subscription_id: string;
  readonly organization_id: string;
  readonly products: readonly SubscriptionProductEntitlement[];
  readonly modules: readonly SubscriptionModuleEntitlement[];
  readonly capabilities: readonly SubscriptionCapabilityEntitlement[];
  readonly quotas: readonly SubscriptionQuotaEntitlement[];
}

// --- Action Payloads ---

export interface CreateSubscriptionPayload {
  readonly organization_id: string;
  readonly plan_version_id: string;
  readonly plan_price_id: string;
  readonly current_period_start?: string | null;
  readonly change_reason?: string;
}

export interface StartTrialPayload {
  readonly organization_id: string;
  readonly plan_version_id: string;
  readonly plan_price_id: string;
  readonly trial_days?: number;
  readonly change_reason?: string;
}

export type ConvertTrialPayload = Record<string, never>;

export interface ChangePlanPayload {
  readonly new_plan_version_id: string;
  readonly new_plan_price_id: string;
  readonly change_reason?: string;
}

export interface SuspendSubscriptionPayload {
  readonly reason?: string;
}

export type ReactivateSubscriptionPayload = Record<string, never>;

export interface CancelSubscriptionPayload {
  readonly reason?: string;
}

export type ReconcileSubscriptionPayload = Record<string, never>;

export interface ReconcileSubscriptionResponse {
  readonly repaired_count: number;
}

// ---------------------------------------------------------------------------
// Central User Management Types (Phase 2D Stage 4/5)
// ---------------------------------------------------------------------------

export type UserStatus = "active" | "suspended" | "disabled";

export interface UserListItem {
  readonly id: string;
  readonly email: string;
  readonly full_name: string;
  readonly status: UserStatus;
  readonly is_active: boolean;
  readonly is_platform_owner: boolean;
  readonly created_at: string;
  readonly updated_at: string;
}

export interface UserDetail extends UserListItem {
  readonly auth_provider?: string;
  readonly email_verified_at?: string | null;
}

export interface UserListResponse {
  readonly count: number;
  readonly next: string | null;
  readonly previous: string | null;
  readonly results: readonly UserListItem[];
}

export interface UserListParams {
  readonly page?: number;
  readonly page_size?: number;
  readonly status?: UserStatus;
  readonly search?: string;
  readonly ordering?: string;
}

export interface CreateUserPayload {
  readonly email: string;
  readonly full_name?: string;
}

export interface UpdateUserPayload {
  readonly full_name: string;
}

export interface UserLifecycleActionPayload {
  readonly reason?: string;
}

// ---------------------------------------------------------------------------
// Organization Membership Management Types (Phase 2D Stage 4/5)
// ---------------------------------------------------------------------------

export type MembershipType = "member" | "tenant_admin";
export type MembershipStatus = "active" | "suspended" | "ended";

export interface MembershipUserSummary {
  readonly id: string;
  readonly email: string;
  readonly full_name: string;
  readonly status: UserStatus;
}

export interface OrganizationMembershipItem {
  readonly id: string;
  readonly organization_id: string;
  readonly user: MembershipUserSummary;
  readonly membership_type: MembershipType;
  readonly status: MembershipStatus;
  readonly role: RoleSummary | null;
  readonly joined_at: string | null;
  readonly ended_at: string | null;
  readonly created_at: string;
  readonly updated_at: string;
}

export interface OrganizationMembershipListResponse {
  readonly count: number;
  readonly next: string | null;
  readonly previous: string | null;
  readonly results: readonly OrganizationMembershipItem[];
}

export interface OrganizationMembershipListParams {
  readonly page?: number;
  readonly page_size?: number;
  readonly status?: MembershipStatus;
  readonly membership_type?: MembershipType;
  readonly search?: string;
  readonly ordering?: string;
}

export interface CreateMembershipPayload {
  readonly user_id: string;
  readonly membership_type?: MembershipType;
}

export interface UpdateMembershipTypePayload {
  readonly membership_type: MembershipType;
}

export interface MembershipLifecycleActionPayload {
  readonly reason?: string;
}

// =========================================================================
// Phase 2E Access Control & Roles Types (Stage 6)
// =========================================================================

export type ConsolePermissionKey =
  | "roles.view"
  | "roles.manage"
  | "roles.assign";

export type TenantConsoleModuleKey =
  | "tenant_landing"
  | "tenant_roles";

export type PlatformConsoleModuleKey =
  | "po_overview"
  | "po_products"
  | "po_plans"
  | "po_subscriptions"
  | "po_organizations"
  | "po_users"
  | "po_entitlements"
  | "po_activity_log";

export interface ConsoleModuleItem {
  readonly key: string;
  readonly display_name: string;
  readonly description: string;
}

export interface AccessPermissionItem {
  readonly key: string;
  readonly display_name: string;
  readonly category: string;
  readonly console_module?: string;
}

export interface AccessCatalogResponse {
  readonly modules: readonly ConsoleModuleItem[];
  readonly permissions: readonly AccessPermissionItem[];
}

export type RoleStatus = "active" | "retired";

export interface RolePermissionDetail {
  readonly key: string;
  readonly display_name: string;
  readonly category: string;
}

export interface RoleSummary {
  readonly id: string;
  readonly code: string;
  readonly name: string;
  readonly is_system_role: boolean;
}

export interface RoleItem {
  readonly id: string;
  readonly code: string;
  readonly name: string;
  readonly description: string;
  readonly is_system_role: boolean;
  readonly status: RoleStatus;
  readonly permission_keys: readonly string[];
  readonly permissions: readonly RolePermissionDetail[];
  readonly assigned_members_count: number;
  readonly created_at: string;
  readonly updated_at: string;
}

export interface PaginatedRoleResponse {
  readonly count: number;
  readonly next: string | null;
  readonly previous: string | null;
  readonly results: readonly RoleItem[];
}

export interface CreateRolePayload {
  readonly name: string;
  readonly code: string;
  readonly description?: string;
  readonly permission_keys: readonly string[];
}

export interface UpdateRolePayload {
  readonly name?: string;
  readonly description?: string;
  readonly permission_keys?: readonly string[];
}

export interface AdministrativeMembershipItem {
  readonly id: string;
  readonly user: {
    readonly id: string;
    readonly email: string;
    readonly full_name: string;
    readonly status: UserStatus;
  };
  readonly membership_type: "tenant_admin";
  readonly status: MembershipStatus;
  readonly role: RoleSummary;
  readonly joined_at: string;
}

export interface PaginatedAdministrativeMembershipResponse {
  readonly count: number;
  readonly next: string | null;
  readonly previous: string | null;
  readonly results: readonly AdministrativeMembershipItem[];
}

export interface AssignMembershipRolePayload {
  readonly role_id: string | null;
}

export interface ConsoleModulePolicyItem {
  readonly module_key: string;
  readonly display_name: string;
  readonly description: string;
  readonly is_core: boolean;
  readonly is_active: boolean;
  readonly is_enabled: boolean;
  readonly updated_at: string | null;
}

export interface PermissionCeilingItem {
  readonly permission_key: string;
  readonly display_name: string;
  readonly description: string;
  readonly category: string;
  readonly console_module: string;
  readonly is_active: boolean;
  readonly is_allowed: boolean;
  readonly updated_at: string | null;
}

export interface UpdateConsoleModulePolicyPayload {
  readonly is_enabled: boolean;
}

export interface UpdatePermissionCeilingPayload {
  readonly is_allowed: boolean;
}

// ---------------------------------------------------------------------------
// Assignment Domain Types (Phase 2F Part E)
// ---------------------------------------------------------------------------

export type AssignmentStatus = "active" | "suspended" | "revoked";

export interface AssignmentUser {
  readonly id: string;
  readonly email: string;
  readonly full_name: string;
}

export interface AssignmentProduct {
  readonly id: string;
  readonly code: string;
  readonly name: string;
}

export interface AssignmentMembership {
  readonly id: string;
  readonly role: string;
  readonly status: string;
}

export interface AssignmentModule {
  readonly id: string;
  readonly module_id: string;
  readonly code: string;
  readonly name: string;
  readonly is_enabled: boolean;
}

export interface UserProductAssignmentItem {
  readonly id: string;
  readonly user: AssignmentUser;
  readonly product: AssignmentProduct;
  readonly status: AssignmentStatus;
  readonly assigned_at: string;
  readonly last_suspended_at: string | null;
  readonly last_reactivated_at: string | null;
  readonly revoked_at: string | null;
  readonly suspension_reason: string | null;
  readonly revocation_reason: string | null;
  readonly enabled_module_count: number;
  readonly created_at: string;
  readonly updated_at: string;
}

export interface AssignmentDetailItem extends UserProductAssignmentItem {
  readonly membership: AssignmentMembership;
  readonly modules: readonly AssignmentModule[];
}

export interface PaginatedAssignmentResponse {
  readonly count: number;
  readonly next: string | null;
  readonly previous: string | null;
  readonly results: readonly UserProductAssignmentItem[];
}

export interface AssignmentListParams {
  readonly page?: number;
  readonly page_size?: number;
  readonly search?: string;
  readonly product_id?: string;
  readonly status?: string;
}

export interface CreateAssignmentPayload {
  readonly user_id: string;
  readonly product_id: string;
  readonly module_ids?: readonly string[];
}

export interface SuspendAssignmentPayload {
  readonly reason: string;
}

export interface RevokeAssignmentPayload {
  readonly reason: string;
}

export interface ReplaceModulesPayload {
  readonly module_ids: readonly string[];
}

export type PoolScope = "product" | "plan";
export type QuotaType = "numeric" | "unlimited";

export interface SelectorProductItem {
  readonly id: string;
  readonly code: string;
  readonly name: string;
  readonly pool_scope: PoolScope;
  readonly quota_type: QuotaType;
  readonly total_limit: number | null;
  readonly consumed_seats: number;
  readonly available_seats: number | null;
  readonly is_capacity_available: boolean;
}

export interface SelectorMemberItem {
  readonly membership_id: string;
  readonly user_id: string;
  readonly email: string;
  readonly full_name: string;
  readonly role_code: string;
}

export interface PaginatedSelectorMemberResponse {
  readonly count: number;
  readonly next: string | null;
  readonly previous: string | null;
  readonly results: readonly SelectorMemberItem[];
}

export interface SelectorMemberParams {
  readonly product_id: string;
  readonly search?: string;
  readonly page?: number;
  readonly page_size?: number;
}

export interface SelectorModuleItem {
  readonly id: string;
  readonly code: string;
  readonly name: string;
  readonly description: string;
  readonly is_entitled: boolean;
}

// ============================================================================
// PHASE 2G — TENANT HOME / APP LAUNCHER TYPES
// ============================================================================

export interface TenantHomeCapabilityItem {
  readonly id: string;
  readonly code: string;
  readonly name: string;
  readonly description: string;
  readonly status: string;
}

export interface TenantHomeFeatureItem {
  readonly id: string;
  readonly code: string;
  readonly name: string;
  readonly description: string;
  readonly status: string;
  readonly capabilities: readonly TenantHomeCapabilityItem[];
}

export type AccessState =
  | "available"
  | "not_assigned"
  | "subscription_inactive"
  | "entitlement_unavailable"
  | "assignment_suspended"
  | "assignment_revoked"
  | "module_unavailable"
  | "membership_inactive"
  | "product_unavailable"
  | "access_expired"
  | "integration_pending";

export type DenialCode =
  | "not_assigned"
  | "subscription_inactive"
  | "entitlement_unavailable"
  | "assignment_suspended"
  | "assignment_revoked"
  | "module_unavailable"
  | "membership_inactive"
  | "product_unavailable"
  | "access_expired"
  | "integration_pending";

export type ModuleState = "available" | "unavailable" | "excluded";

export interface TenantHomeModuleItem {
  readonly id: string;
  readonly code: string;
  readonly name: string;
  readonly description: string;
  readonly status: string;
  readonly module_state?: ModuleState;
  readonly features: readonly TenantHomeFeatureItem[];
}

export interface TenantHomeEntitledProduct {
  readonly id: string;
  readonly code: string;
  readonly name: string;
  readonly description: string;
  readonly status: string;
  readonly assignment_id: string | null;
  readonly assigned_at: string | null;
  readonly access_state?: AccessState;
  readonly denial_code?: DenialCode | null;
  readonly launchable?: boolean;
  readonly eligible_modules?: readonly TenantHomeModuleItem[];
  readonly modules: readonly TenantHomeModuleItem[];
}

export interface TenantHomeConsoleModule {
  readonly key: string;
  readonly display_name: string;
  readonly description: string;
  readonly is_core: boolean;
}

export interface TenantHomeProductSeatMetric {
  readonly product_id: string;
  readonly product_code: string;
  readonly product_name: string;
  readonly pool_scope: string;
  readonly quota_type: string;
  readonly total_limit: number | null;
  readonly consumed_seats: number;
  readonly available_seats: number | null;
  readonly is_capacity_available: boolean;
}

export interface TenantHomeSeatSummary {
  readonly total_assigned_seats: number;
  readonly products: readonly TenantHomeProductSeatMetric[];
}

export interface TenantHomeRoleSummary {
  readonly id: string;
  readonly code: string;
  readonly name: string;
  readonly is_system_role: boolean;
}

export interface TenantHomeMembershipSummary {
  readonly id: string;
  readonly membership_type: string;
  readonly status: string;
  readonly joined_at: string | null;
  readonly role: TenantHomeRoleSummary | null;
}

export interface TenantHomeOrganizationSummary {
  readonly id: string;
  readonly code: string;
  readonly name: string;
  readonly description: string;
  readonly status: string;
}

export interface TenantHomeResponse {
  readonly schema_version: string;
  readonly organization: TenantHomeOrganizationSummary;
  readonly membership: TenantHomeMembershipSummary;
  readonly entitled_products: readonly TenantHomeEntitledProduct[];
  readonly products?: readonly TenantHomeEntitledProduct[];
  readonly console_modules: readonly TenantHomeConsoleModule[];
  readonly seat_summary: TenantHomeSeatSummary;
}

export type TenantProductAccessItem = TenantHomeEntitledProduct;
export type TenantModuleItem = TenantHomeModuleItem;
export type TenantConsoleModuleItem = TenantHomeConsoleModule;
export type TenantSeatSummary = TenantHomeSeatSummary;
export type TenantRoleSummary = TenantHomeRoleSummary;
export type TenantMembershipSummary = TenantHomeMembershipSummary;


// ============================================================================
// PHASE 3B TENANT ONBOARDING TYPES
// ============================================================================

export type OnboardingStepName =
  | "organization_profile"
  | "admin_setup"
  | "plan_selection"
  | "product_entitlements"
  | "feature_ceilings"
  | "review_confirm"
  | "completed";

export type OnboardingCaseStatus = "in_progress" | "completed" | "abandoned" | "provisioning_failed";

export interface TenantOnboardingCase {
  readonly id: string;
  readonly status: OnboardingCaseStatus;
  readonly current_step: OnboardingStepName;
  readonly organization_code: string;
  readonly organization_name: string;
  readonly organization_description: string;
  readonly admin_email: string;
  readonly admin_full_name: string;
  readonly plan_version: string | null;
  readonly plan_version_number: number | null;
  readonly plan_name: string | null;
  readonly plan_price: string | null;
  readonly is_trial: boolean;
  readonly selected_product_ids?: readonly string[];
  readonly feature_ceilings?: Record<string, unknown>;
  readonly created_organization_id: string | null;
  readonly initial_admin_activation_url?: string | null;
  readonly started_at: string;
  readonly completed_at: string | null;
  readonly updated_at: string;
}

export interface TransitionStepPayload {
  readonly target_step: OnboardingStepName;
  readonly step_data?: Record<string, unknown>;
}

export interface OnboardingProductFeatureOption {
  readonly id: string;
  readonly code: string;
  readonly name: string;
  readonly description: string;
  readonly display_order: number;
}

export interface OnboardingProductModuleOption {
  readonly id: string;
  readonly code: string;
  readonly name: string;
  readonly description: string;
  readonly display_order: number;
  readonly features: readonly OnboardingProductFeatureOption[];
}

export interface OnboardingProductOption {
  readonly id: string;
  readonly code: string;
  readonly name: string;
  readonly description: string;
  readonly modules: readonly OnboardingProductModuleOption[];
}

export interface OnboardingConsolePermissionOption {
  readonly key: string;
  readonly display_name: string;
  readonly description: string;
}

export interface OnboardingConsoleModuleOption {
  readonly key: string;
  readonly display_name: string;
  readonly description: string;
  readonly is_core: boolean;
  readonly permissions: readonly OnboardingConsolePermissionOption[];
}

export interface OnboardingOptionsResponse {
  readonly products: readonly OnboardingProductOption[];
  readonly console_modules: readonly OnboardingConsoleModuleOption[];
}

// ============================================================================
// PHASE 3C USER INVITATIONS TYPES
// ============================================================================

export type InvitationStatus = "pending" | "accepted" | "expired" | "revoked";

export interface InvitationValidateResponse {
  readonly id: string;
  readonly email: string;
  readonly organization_name: string;
  readonly organization_code: string;
  readonly membership_type: string;
  readonly status: InvitationStatus;
  readonly expires_at: string;
}

export interface AcceptInvitationPayload {
  readonly password: string;
  readonly full_name?: string;
}

export interface AcceptInvitationResponse {
  readonly success: boolean;
  readonly detail: string;
  readonly data: {
    readonly user_id: string;
    readonly email: string;
    readonly full_name: string;
    readonly organization_id: string;
    readonly organization_code: string;
    readonly organization_name: string;
  };
}

export interface IssueInvitationPayload {
  readonly organization_id: string;
  readonly email: string;
  readonly full_name?: string;
  readonly membership_type?: string;
  readonly role_id?: string | null;
  readonly product_id?: string | null;
  readonly product_ids?: readonly string[];
  readonly module_ids?: readonly string[];
}

export interface IssueInvitationResponse {
  readonly id: string;
  readonly email: string;
  readonly status: InvitationStatus;
  readonly expires_at: string;
  readonly raw_token?: string;
  readonly activation_url?: string;
}

// ============================================================================
// PHASE 3D BULK IMPORT TYPES
// ============================================================================

export type BulkImportJobStatus =
  | "pending"
  | "validating"
  | "validated"
  | "committing"
  | "completed"
  | "failed";

export type BulkImportRowValidationState =
  | "pending"
  | "valid"
  | "invalid"
  | "committed"
  | "failed";

export interface BulkImportJob {
  readonly id: string;
  readonly organization_id: string | null;
  readonly organization_code?: string | null;
  readonly organization_name?: string | null;
  readonly import_type: string;
  readonly status: BulkImportJobStatus;
  readonly idempotency_key: string;
  readonly total_rows: number;
  readonly valid_rows: number;
  readonly invalid_rows: number;
  readonly committed_rows: number;
  readonly failed_rows: number;
  readonly error_summary: Record<string, unknown>;
  readonly created_at: string;
  readonly updated_at: string;
  readonly completed_at: string | null;
}

export interface BulkImportRow {
  readonly id: string;
  readonly row_number: number;
  readonly validation_state: BulkImportRowValidationState;
  readonly payload_ref: {
    readonly email?: string;
    readonly full_name?: string;
    readonly membership_type?: string;
    readonly role_code?: string;
  };
  readonly error_code: string;
  readonly error_message: string;
  readonly created_at: string;
  readonly updated_at: string;
}

export interface BulkImportRowListResponse {
  readonly count: number;
  readonly next: string | null;
  readonly previous: string | null;
  readonly results: readonly BulkImportRow[];
}

export interface CreateBulkImportJobPayload {
  readonly organization_id: string;
  readonly idempotency_key: string;
  readonly raw_content: string;
  readonly content_type?: "csv" | "json";
}

export type BulkImportErrorCode =
  | "MISSING_EMAIL"
  | "INVALID_EMAIL"
  | "DUPLICATE_ROW_IN_FILE"
  | "ALREADY_ACTIVE_MEMBER"
  | "PENDING_INVITATION_EXISTS"
  | "MEMBERSHIP_SUSPENDED"
  | "USER_DISABLED"
  | "INVALID_MEMBERSHIP_TYPE"
  | "ROLE_NOT_FOUND"
  | "MISSING_ADMIN_ROLE"
  | "MEMBER_CANNOT_HAVE_ROLE"
  | "MEMBER_ALREADY_EXISTS"
  | "DUPLICATE_INVITATION"
  | "COMMIT_FAILED"
  | "NOTIFICATION_FAILED"
  | "TRANSIENT_SERVICE_ERROR"
  | "LOCK_TIMEOUT";

export interface BulkImportReconciliationRow {
  readonly id: string;
  readonly row_number: number;
  readonly email: string;
  readonly full_name: string;
  readonly membership_type: string;
  readonly role_code: string;
  readonly validation_state: BulkImportRowValidationState;
  readonly error_code: string;
  readonly error_message: string;
  readonly is_recoverable: boolean;
}

export interface BulkImportReconciliationReport {
  readonly job_id: string;
  readonly organization_id: string | null;
  readonly organization_code: string | null;
  readonly organization_name: string | null;
  readonly status: BulkImportJobStatus;
  readonly total_rows: number;
  readonly committed_rows: number;
  readonly failed_rows: number;
  readonly invalid_rows: number;
  readonly valid_rows: number;
  readonly recoverable_failures_count: number;
  readonly terminal_failures_count: number;
  readonly can_retry: boolean;
  readonly state_breakdown: Record<string, number>;
  readonly error_code_breakdown: Record<string, number>;
  readonly completed_at: string | null;
  readonly created_at: string;
  readonly rows: readonly BulkImportReconciliationRow[];
}

// ============================================================================
// PHASE 3F ACCESS REQUESTS & APPROVALS TYPES
// ============================================================================

export type AccessRequestStatus = "pending" | "approved" | "denied" | "cancelled";
export type AccessRequestDecisionType = "approved" | "denied";

export interface AccessRequestDecisionItem {
  readonly id: string;
  readonly approver_id: string;
  readonly approver_email?: string;
  readonly approver_name?: string;
  readonly decision: AccessRequestDecisionType;
  readonly reason: string;
  readonly decided_at: string;
}

export interface AccessRequestItem {
  readonly id: string;
  readonly organization_id: string;
  readonly organization_code?: string;
  readonly organization_name?: string;
  readonly requester_id: string;
  readonly requester_email: string;
  readonly requester_name: string;
  readonly product_id: string | null;
  readonly product_code?: string | null;
  readonly product_name?: string | null;
  readonly status: AccessRequestStatus;
  readonly requested_modules: readonly string[];
  readonly reason: string;
  readonly requested_at: string;
  readonly updated_at: string;
  readonly decisions?: readonly AccessRequestDecisionItem[];
}

export interface AccessRequestListResponse {
  readonly count: number;
  readonly next: string | null;
  readonly previous: string | null;
  readonly results: readonly AccessRequestItem[];
}

export interface AccessRequestListParams {
  readonly organization_id?: string;
  readonly status?: AccessRequestStatus;
  readonly product_id?: string;
  readonly search?: string;
  readonly page?: number;
  readonly page_size?: number;
}

export interface CreateAccessRequestPayload {
  readonly organization_id: string;
  readonly product_id: string;
  readonly requested_modules?: readonly string[];
  readonly reason?: string;
}export interface DecideAccessRequestPayload {
  readonly reason?: string;
}



// --- Phase 11: Product Showcase ---

export type ShowcaseVisibility = 'draft' | 'published' | 'hidden';
export type ShowcaseMediaType = 'screenshot' | 'video' | 'document';

export interface ShowcaseMedia {
  readonly id: string;
  readonly media_type: ShowcaseMediaType;
  readonly title: string;
  readonly url: string;
  readonly display_order: number;
  readonly created_at: string;
}

export interface ShowcaseProfile {
  readonly id: string;
  readonly product_id: string;
  readonly product_code: string;
  readonly product_name: string;
  readonly product_status: string;
  readonly tagline: string;
  readonly overview: string;
  readonly visibility: ShowcaseVisibility;
  readonly display_order: number;
  readonly media: readonly ShowcaseMedia[];
  readonly created_at: string;
  readonly updated_at: string;
}

export interface ShowcaseProfileListResponse {
  readonly count: number;
  readonly results: readonly ShowcaseProfile[];
}

export interface CreateShowcaseProfilePayload {
  readonly product_id: string;
  readonly tagline?: string;
  readonly overview?: string;
  readonly visibility?: ShowcaseVisibility;
  readonly display_order?: number;
}

export interface UpdateShowcaseProfilePayload {
  readonly tagline?: string;
  readonly overview?: string;
  readonly visibility?: ShowcaseVisibility;
  readonly display_order?: number;
}

export interface DemoEnvironment {
  readonly id: string;
  readonly product_id: string;
  readonly product_name: string;
  readonly name: string;
  readonly base_url: string;
  readonly description: string;
  readonly is_active: boolean;
  readonly created_at: string;
  readonly updated_at: string;
}

export interface LaunchabilityContract {
  readonly launchable: boolean;
  readonly reason: string;
  readonly environment_name?: string;
  readonly launch_mode?: string;
  readonly demo_user?: string;
  readonly demo_organization?: string;
  readonly allowed_targets?: readonly string[];
  readonly target_environment?: {
    readonly id?: string;
    readonly name?: string;
    readonly base_url?: string;
  };
}

export interface ShowcaseDemoLaunchResponse {
  readonly redirect_url: string;
  readonly expires_at: string;
  readonly demo_user: string;
  readonly demo_organization: string;
  readonly product_name: string;
  readonly target_name: string;
  readonly open_mode?: string;
}

export interface ShowcaseLaunchConfig {
  readonly id: string | null;
  readonly product: string;
  readonly product_name: string;
  readonly launch_mode: string;
  readonly target_environment: string | null;
  readonly target_environment_id?: string | null;
  readonly target_environment_name?: string;
  readonly allowed_targets: readonly string[];
  readonly policy: Record<string, unknown>;
  readonly notes: string;
  readonly available_environments?: readonly DemoEnvironment[];
}

export interface ReorderPayload {
  readonly ordered_ids: readonly string[];
}
