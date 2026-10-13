/**
 * Usage & Metering API Client (Phase 4C).
 * Exclusively consumes centralized apiClient and ENDPOINTS.
 */

import { apiClient } from "./client.ts";
import { ENDPOINTS } from "./endpoints.ts";

export interface UsageBucketItem {
  meter_key: string;
  meter_name: string;
  scope: string;
  unit: string;
  consumed: number;
  limit: number | null;
  is_over_limit: boolean;
  period_start: string;
  period_end: string;
}

export interface TenantUsageSummary {
  buckets: UsageBucketItem[];
  as_of: string;
}

export interface OwnerUsageBucket {
  id: string;
  organization_id: string;
  organization_name: string;
  meter_key: string;
  meter_name: string;
  unit: string;
  period_start: string;
  period_end: string;
  consumed: number;
  is_over_limit: boolean;
  updated_at: string;
}

export interface OwnerUsageListResponse {
  count: number;
  results: OwnerUsageBucket[];
  next?: string | null;
  previous?: string | null;
}

export const usageApi = {
  getTenantUsageSummary: async (): Promise<TenantUsageSummary> => {
    return apiClient.get<TenantUsageSummary>(ENDPOINTS.USAGE.TENANT_SUMMARY);
  },

  getOwnerUsage: async (page = 1, pageSize = 20): Promise<OwnerUsageListResponse> => {
    const query = new URLSearchParams({
      page: String(page),
      page_size: String(pageSize),
    }).toString();
    return apiClient.get<OwnerUsageListResponse>(`${ENDPOINTS.USAGE.OWNER_LIST}?${query}`);
  },

  ingestEvent: async (payload: {
    organization_id: string;
    meter_key: string;
    quantity: number;
    event_key: string;
    product_id?: string;
  }): Promise<{ status: string; event_id: string }> => {
    return apiClient.post<{ status: string; event_id: string }>(
      ENDPOINTS.USAGE.EVENTS,
      payload
    );
  },
};
