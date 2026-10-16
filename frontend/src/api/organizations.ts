/**
 * Organization Registry Domain API.
 *
 * Exclusively consumes the centralized apiClient to communicate with versioned organization endpoints.
 */

import { apiClient } from "./client.ts";
import { ENDPOINTS } from "./endpoints.ts";
import type {
  CreateOrganizationPayload,
  OrganizationDetail,
  OrganizationListResponse,
  UpdateOrganizationPayload,
} from "./types.ts";

export interface OrganizationListParams {
  readonly page?: number;
  readonly page_size?: number;
  readonly search?: string;
  readonly status?: string;
  readonly ordering?: string;
}

export const organizationsApi = {
  /**
   * List organizations with server-side pagination, search, and filtering.
   */
  async list(params?: OrganizationListParams, signal?: AbortSignal): Promise<OrganizationListResponse> {
    return apiClient.get<OrganizationListResponse>(ENDPOINTS.ORGANIZATIONS.LIST, {
      params,
      signal,
    });
  },

  /**
   * Retrieve single organization detail including minimal audit users.
   */
  async get(id: string): Promise<OrganizationDetail> {
    return apiClient.get<OrganizationDetail>(ENDPOINTS.ORGANIZATIONS.DETAIL(id));
  },

  /**
   * Create a new organization starting in Draft lifecycle status.
   */
  async create(payload: CreateOrganizationPayload): Promise<OrganizationDetail> {
    return apiClient.post<OrganizationDetail>(ENDPOINTS.ORGANIZATIONS.LIST, payload);
  },

  /**
   * Partially update editable organization fields (name, description, status).
   */
  async update(id: string, payload: UpdateOrganizationPayload): Promise<OrganizationDetail> {
    return apiClient.patch<OrganizationDetail>(ENDPOINTS.ORGANIZATIONS.DETAIL(id), payload);
  },
};
