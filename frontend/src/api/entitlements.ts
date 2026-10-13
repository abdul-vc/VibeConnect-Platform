/**
 * Organization-Product Entitlements Domain API.
 *
 * Exclusively consumes the centralized apiClient to communicate with versioned entitlement endpoints.
 */

import { apiClient } from "./client.ts";
import { ENDPOINTS } from "./endpoints.ts";
import type {
  CreateEntitlementPayload,
  EntitlementDetail,
  EntitlementListResponse,
  UpdateEntitlementPayload,
} from "./types.ts";

export interface EntitlementListParams {
  readonly page?: number;
  readonly page_size?: number;
  readonly search?: string;
  readonly organization_id?: string;
  readonly product_id?: string;
  readonly status?: string;
  readonly ordering?: string;
}

export const entitlementsApi = {
  /**
   * List entitlements with server-side pagination, search, and filtering.
   */
  async list(params?: EntitlementListParams, signal?: AbortSignal): Promise<EntitlementListResponse> {
    return apiClient.get<EntitlementListResponse>(ENDPOINTS.ORGANIZATION_PRODUCT_ENTITLEMENTS.LIST, {
      params,
      signal,
    });
  },

  /**
   * Retrieve single entitlement detail including parent details and audit references.
   */
  async get(id: string): Promise<EntitlementDetail> {
    return apiClient.get<EntitlementDetail>(ENDPOINTS.ORGANIZATION_PRODUCT_ENTITLEMENTS.DETAIL(id));
  },

  /**
   * Register a new entitlement starting in Draft lifecycle status.
   */
  async create(payload: CreateEntitlementPayload): Promise<EntitlementDetail> {
    return apiClient.post<EntitlementDetail>(ENDPOINTS.ORGANIZATION_PRODUCT_ENTITLEMENTS.LIST, payload);
  },

  /**
   * Partially update editable entitlement status.
   */
  async update(id: string, payload: UpdateEntitlementPayload): Promise<EntitlementDetail> {
    return apiClient.patch<EntitlementDetail>(ENDPOINTS.ORGANIZATION_PRODUCT_ENTITLEMENTS.DETAIL(id), payload);
  },
};
