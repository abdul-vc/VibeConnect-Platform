/**
 * Tenant Home & Access-State API Service (Phase 2G).
 *
 * Exclusively consumes the centralized apiClient to communicate with:
 * - GET /api/v1/tenant/home/
 */

import { apiClient } from "./client.ts";
import { ENDPOINTS } from "./endpoints.ts";
import type { TenantHomeResponse } from "./types.ts";

export const tenantHomeApi = {
  /**
   * Fetch complete authoritative tenant home access summary, seat metrics,
   * entitled products, and console modules for the active tenant session.
   */
  async getTenantHome(signal?: AbortSignal): Promise<TenantHomeResponse> {
    return apiClient.get<TenantHomeResponse>(ENDPOINTS.TENANT_HOME, { signal });
  },
};
