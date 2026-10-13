/**
 * Marketplace API Client (Phase 6A).
 *
 * Exclusively consumes centralized apiClient and ENDPOINTS.MARKETPLACE.
 * Zero localhost references, zero direct fetch, zero inline axios creation.
 */

import { apiClient } from "./client.ts";
import { ENDPOINTS } from "./endpoints.ts";

export type MarketplaceIntegrationStatus = "operational" | "pending";

export type MarketplaceTenantState =
  | "installed"
  | "available"
  | "request_pending"
  | "integration_pending";

export interface MarketplacePrice {
  readonly currency: string;
  readonly amount: string;
  readonly billing_interval: string;
}

export interface MarketplacePlan {
  readonly plan_version_id: string;
  readonly plan_id?: string;
  readonly plan_name: string;
  readonly plan_code: string;
  readonly version?: string;
  readonly is_public?: boolean;
  readonly prices: readonly MarketplacePrice[];
}

export interface MarketplaceMedia {
  readonly id: string;
  readonly media_type: string;
  readonly title: string;
  readonly url: string;
  readonly display_order: number;
}

export interface MarketplaceFeature {
  readonly id: string;
  readonly code: string;
  readonly name: string;
  readonly description: string;
}

export interface MarketplaceModule {
  readonly id: string;
  readonly code: string;
  readonly name: string;
  readonly description: string;
  readonly features: readonly MarketplaceFeature[];
}

export interface MarketplaceProductListItem {
  readonly id: string;
  readonly code: string;
  readonly name: string;
  readonly tagline: string;
  readonly description: string;
  readonly icon_url: string | null;
  readonly media?: readonly MarketplaceMedia[];
  readonly integration_status: MarketplaceIntegrationStatus;
  readonly tenant_state: MarketplaceTenantState;
  readonly can_enable: boolean;
  readonly can_request: boolean;
  readonly plans_count: number;
}

export interface MarketplaceProductDetail extends MarketplaceProductListItem {
  readonly overview: string;
  readonly media: readonly MarketplaceMedia[];
  readonly modules: readonly MarketplaceModule[];
  readonly plans: readonly MarketplacePlan[];
  readonly entitlement: Record<string, unknown> | null;
  readonly pending_request: Record<string, unknown> | null;
}

export interface MarketplaceEnablePayload {
  readonly plan_version_id?: string | null;
}

export interface MarketplaceRequestPayload {
  readonly requested_plan_id?: string | null;
  readonly notes?: string;
}

export interface TenantProductRequestResponse {
  readonly id: string;
  readonly organization_id: string;
  readonly organization_code: string;
  readonly product_id: string;
  readonly product_code: string;
  readonly product_name: string;
  readonly requested_plan_id: string | null;
  readonly status: string;
  readonly notes: string;
  readonly created_at: string;
  readonly updated_at: string;
}

export const marketplaceApi = {
  /**
   * List available products in the tenant marketplace with tenant overlay.
   */
  listProducts: async (): Promise<MarketplaceProductListItem[]> => {
    return apiClient.get<MarketplaceProductListItem[]>(ENDPOINTS.MARKETPLACE.PRODUCTS);
  },

  /**
   * Fetch detailed product specifications, modules, showcase media, and packaged plans.
   */
  getProductDetail: async (codeOrId: string): Promise<MarketplaceProductDetail> => {
    return apiClient.get<MarketplaceProductDetail>(ENDPOINTS.MARKETPLACE.PRODUCT_DETAIL(codeOrId));
  },

  /**
   * Enable an integration-ready product for the tenant organization.
   */
  enableProduct: async (
    codeOrId: string,
    payload: MarketplaceEnablePayload = {}
  ): Promise<unknown> => {
    return apiClient.post<unknown>(ENDPOINTS.MARKETPLACE.ENABLE(codeOrId), payload);
  },

  /**
   * Submit a product adoption request for an integration-pending product.
   */
  requestProduct: async (
    codeOrId: string,
    payload: MarketplaceRequestPayload = {}
  ): Promise<TenantProductRequestResponse> => {
    return apiClient.post<TenantProductRequestResponse>(ENDPOINTS.MARKETPLACE.REQUEST(codeOrId), payload);
  },
};
