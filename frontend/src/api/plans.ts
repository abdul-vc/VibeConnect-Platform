/**
 * Plans & Pricing Domain API.
 *
 * Exclusively consumes the centralized apiClient to communicate with versioned plan endpoints.
 */

import { apiClient } from "./client.ts";
import { ENDPOINTS } from "./endpoints.ts";
import type {
  ClonePlanVersionPayload,
  CreatePlanCapabilityPayload,
  CreatePlanModulePayload,
  CreatePlanPayload,
  CreatePlanPricePayload,
  CreatePlanProductPayload,
  CreatePlanQuotaPayload,
  CreatePlanVersionPayload,
  PlanCapabilityListItem,
  PlanCapabilityListParams,
  PlanCapabilityListResponse,
  PlanDetail,
  PlanListParams,
  PlanListResponse,
  PlanModuleListItem,
  PlanModuleListParams,
  PlanModuleListResponse,
  PlanPriceListItem,
  PlanPriceListParams,
  PlanPriceListResponse,
  PlanProductListItem,
  PlanProductListParams,
  PlanProductListResponse,
  PlanQuotaListItem,
  PlanQuotaListParams,
  PlanQuotaListResponse,
  PlanReadinessResponse,
  PlanVersionDetail,
  PlanVersionListParams,
  PlanVersionListResponse,
  UpdatePlanPayload,
  UpdatePlanPricePayload,
  UpdatePlanQuotaPayload,
  UpdatePlanVersionPayload,
} from "./types.ts";

export const plansApi = {
  /**
   * List Plans with server-side pagination, search, and filtering.
   */
  async list(params?: PlanListParams, signal?: AbortSignal): Promise<PlanListResponse> {
    return apiClient.get<PlanListResponse>(ENDPOINTS.PLANS.LIST, {
      params,
      signal,
    });
  },

  /**
   * Retrieve single Plan detail by ID.
   */
  async get(id: string, signal?: AbortSignal): Promise<PlanDetail> {
    return apiClient.get<PlanDetail>(ENDPOINTS.PLANS.DETAIL(id), { signal });
  },

  /**
   * Create a new Plan family (automatically initializes Version 1 Draft).
   */
  async create(payload: CreatePlanPayload): Promise<PlanDetail> {
    return apiClient.post<PlanDetail>(ENDPOINTS.PLANS.LIST, payload);
  },

  /**
   * Partially update editable Plan presentation fields (name, description).
   */
  async update(id: string, payload: UpdatePlanPayload): Promise<PlanDetail> {
    return apiClient.patch<PlanDetail>(ENDPOINTS.PLANS.DETAIL(id), payload);
  },

  /**
   * List paginated versions for a specific Plan.
   */
  async listVersions(
    planId: string,
    params?: PlanVersionListParams,
    signal?: AbortSignal
  ): Promise<PlanVersionListResponse> {
    return apiClient.get<PlanVersionListResponse>(ENDPOINTS.PLANS.VERSIONS(planId), {
      params,
      signal,
    });
  },

  /**
   * Retrieve single PlanVersion detail by version ID.
   */
  async getVersion(versionId: string, signal?: AbortSignal): Promise<PlanVersionDetail> {
    return apiClient.get<PlanVersionDetail>(ENDPOINTS.PLAN_VERSIONS.DETAIL(versionId), { signal });
  },

  /**
   * Create a new Draft version under a Plan.
   */
  async createVersion(planId: string, payload?: CreatePlanVersionPayload): Promise<PlanVersionDetail> {
    return apiClient.post<PlanVersionDetail>(ENDPOINTS.PLANS.VERSIONS(planId), payload ?? {});
  },

  /**
   * Partially update Draft version change summary.
   */
  async updateVersion(
    versionId: string,
    payload: UpdatePlanVersionPayload
  ): Promise<PlanVersionDetail> {
    return apiClient.patch<PlanVersionDetail>(ENDPOINTS.PLAN_VERSIONS.DETAIL(versionId), payload);
  },

  /**
   * Clone a version to create a new Draft with deep-copied configurations.
   */
  async cloneVersion(
    versionId: string,
    payload?: ClonePlanVersionPayload
  ): Promise<PlanVersionDetail> {
    return apiClient.post<PlanVersionDetail>(
      ENDPOINTS.PLAN_VERSIONS.CLONE(versionId),
      payload ?? {}
    );
  },

  /**
   * Evaluate activation readiness and catalog health for a version.
   */
  async getReadiness(versionId: string, signal?: AbortSignal): Promise<PlanReadinessResponse> {
    return apiClient.get<PlanReadinessResponse>(ENDPOINTS.PLAN_VERSIONS.READINESS(versionId), {
      signal,
    });
  },

  /**
   * Activate a Draft version (supersedes any existing Active version atomically).
   */
  async activateVersion(versionId: string): Promise<PlanVersionDetail> {
    return apiClient.post<PlanVersionDetail>(ENDPOINTS.PLAN_VERSIONS.ACTIVATE(versionId), {});
  },

  /**
   * Manually retire a Draft or Active version.
   */
  async retireVersion(versionId: string): Promise<PlanVersionDetail> {
    return apiClient.post<PlanVersionDetail>(ENDPOINTS.PLAN_VERSIONS.RETIRE(versionId), {});
  },

  // ---------------------------------------------------------------------------
  // Pricing Endpoints
  // ---------------------------------------------------------------------------

  /**
   * List paginated prices for a specific PlanVersion.
   */
  async listPrices(
    versionId: string,
    params?: PlanPriceListParams,
    signal?: AbortSignal
  ): Promise<PlanPriceListResponse> {
    return apiClient.get<PlanPriceListResponse>(ENDPOINTS.PLAN_VERSIONS.PRICES(versionId), {
      params,
      signal,
    });
  },

  /**
   * Create a price entry under a Draft PlanVersion.
   */
  async createPrice(
    versionId: string,
    payload: CreatePlanPricePayload
  ): Promise<PlanPriceListItem> {
    return apiClient.post<PlanPriceListItem>(ENDPOINTS.PLAN_VERSIONS.PRICES(versionId), payload);
  },

  /**
   * Update an existing price amount under a Draft PlanVersion.
   */
  async updatePrice(
    priceId: string,
    payload: UpdatePlanPricePayload
  ): Promise<PlanPriceListItem> {
    return apiClient.patch<PlanPriceListItem>(ENDPOINTS.PLAN_PRICES.DETAIL(priceId), payload);
  },

  /**
   * Remove a price entry from a Draft PlanVersion.
   */
  async deletePrice(priceId: string): Promise<void> {
    return apiClient.delete<void>(ENDPOINTS.PLAN_PRICES.DETAIL(priceId));
  },

  // ---------------------------------------------------------------------------
  // Packaging Endpoints (Products, Modules, Capabilities)
  // ---------------------------------------------------------------------------

  /**
   * List paginated PlanProducts for a specific PlanVersion.
   */
  async listProducts(
    versionId: string,
    params?: PlanProductListParams,
    signal?: AbortSignal
  ): Promise<PlanProductListResponse> {
    return apiClient.get<PlanProductListResponse>(ENDPOINTS.PLAN_VERSIONS.PRODUCTS(versionId), {
      params,
      signal,
    });
  },

  /**
   * Add a Product to a Draft PlanVersion.
   */
  async addProduct(
    versionId: string,
    payload: CreatePlanProductPayload
  ): Promise<PlanProductListItem> {
    return apiClient.post<PlanProductListItem>(ENDPOINTS.PLAN_VERSIONS.PRODUCTS(versionId), payload);
  },

  /**
   * Remove a PlanProduct (atomic cascade to child modules and capabilities).
   */
  async deleteProduct(planProductId: string): Promise<void> {
    return apiClient.delete<void>(ENDPOINTS.PLAN_PRODUCTS.DETAIL(planProductId));
  },

  /**
   * List paginated PlanModules for a specific PlanVersion.
   */
  async listModules(
    versionId: string,
    params?: PlanModuleListParams,
    signal?: AbortSignal
  ): Promise<PlanModuleListResponse> {
    return apiClient.get<PlanModuleListResponse>(ENDPOINTS.PLAN_VERSIONS.MODULES(versionId), {
      params,
      signal,
    });
  },

  /**
   * Add a Module to a PlanProduct under a Draft PlanVersion.
   */
  async addModule(
    versionId: string,
    payload: CreatePlanModulePayload
  ): Promise<PlanModuleListItem> {
    return apiClient.post<PlanModuleListItem>(ENDPOINTS.PLAN_VERSIONS.MODULES(versionId), payload);
  },

  /**
   * Remove a PlanModule (atomic cascade to child capabilities).
   */
  async deleteModule(planModuleId: string): Promise<void> {
    return apiClient.delete<void>(ENDPOINTS.PLAN_MODULES.DETAIL(planModuleId));
  },

  /**
   * List paginated PlanCapabilities for a specific PlanVersion.
   */
  async listCapabilities(
    versionId: string,
    params?: PlanCapabilityListParams,
    signal?: AbortSignal
  ): Promise<PlanCapabilityListResponse> {
    return apiClient.get<PlanCapabilityListResponse>(ENDPOINTS.PLAN_VERSIONS.CAPABILITIES(versionId), {
      params,
      signal,
    });
  },

  /**
   * Add a Capability to a PlanModule under a Draft PlanVersion.
   */
  async addCapability(
    versionId: string,
    payload: CreatePlanCapabilityPayload
  ): Promise<PlanCapabilityListItem> {
    return apiClient.post<PlanCapabilityListItem>(ENDPOINTS.PLAN_VERSIONS.CAPABILITIES(versionId), payload);
  },

  /**
   * Remove a PlanCapability from a Draft PlanVersion.
   */
  async deleteCapability(planCapabilityId: string): Promise<void> {
    return apiClient.delete<void>(ENDPOINTS.PLAN_CAPABILITIES.DETAIL(planCapabilityId));
  },

  // ---------------------------------------------------------------------------
  // Quota Endpoints (Stage 1C-2B)
  // ---------------------------------------------------------------------------

  /**
   * List paginated PlanQuotas for a specific PlanVersion.
   */
  async listQuotas(
    versionId: string,
    params?: PlanQuotaListParams,
    signal?: AbortSignal
  ): Promise<PlanQuotaListResponse> {
    return apiClient.get<PlanQuotaListResponse>(ENDPOINTS.PLAN_VERSIONS.QUOTAS(versionId), {
      params,
      signal,
    });
  },

  /**
   * Create a PlanQuota under a Draft PlanVersion.
   */
  async createQuota(
    versionId: string,
    payload: CreatePlanQuotaPayload
  ): Promise<PlanQuotaListItem> {
    return apiClient.post<PlanQuotaListItem>(ENDPOINTS.PLAN_VERSIONS.QUOTAS(versionId), payload);
  },

  /**
   * Update mutable fields of a PlanQuota.
   */
  async updateQuota(
    quotaId: string,
    payload: UpdatePlanQuotaPayload
  ): Promise<PlanQuotaListItem> {
    return apiClient.patch<PlanQuotaListItem>(ENDPOINTS.PLAN_QUOTAS.DETAIL(quotaId), payload);
  },

  /**
   * Delete a PlanQuota from a Draft PlanVersion.
   */
  async deleteQuota(quotaId: string): Promise<void> {
    return apiClient.delete<void>(ENDPOINTS.PLAN_QUOTAS.DETAIL(quotaId));
  },
};

/**
 * Canonical Currency Display Formatter.
 *
 * Formats decimal string amounts for human presentation using Intl.NumberFormat:
 * - INR "55000.00" -> "₹55,000.00"
 * - USD "1200.00"  -> "$1,200.00"
 * - EUR "99.00"    -> "€99.00"
 * - GBP "45.00"    -> "£45.00"
 * Presentation only: does not mutate canonical decimal strings or API payloads.
 */
export function formatCurrencyDisplay(amount: string | number, currency: string): string {
  if (!amount && amount !== 0) return "";
  const num = typeof amount === "number" ? amount : Number(amount);
  if (Number.isNaN(num)) {
    return `${currency} ${amount}`;
  }
  try {
    const locale = currency === "INR" ? "en-IN" : "en-US";
    return new Intl.NumberFormat(locale, {
      style: "currency",
      currency,
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(num);
  } catch {
    return `${currency} ${amount}`;
  }
}

