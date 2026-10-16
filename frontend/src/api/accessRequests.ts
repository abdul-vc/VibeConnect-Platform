/**
 * Access Requests & Approvals Domain API Client (Phase 3F).
 *
 * Exclusively consumes centralized apiClient and ENDPOINTS.
 */

import { apiClient } from "./client.ts";
import { ENDPOINTS } from "./endpoints.ts";
import type {
  AccessRequestItem,
  AccessRequestListParams,
  AccessRequestListResponse,
  CreateAccessRequestPayload,
  DecideAccessRequestPayload,
} from "./types.ts";

export const accessRequestsApi = {
  /**
   * Submit a new product access request.
   */
  async createRequest(payload: CreateAccessRequestPayload): Promise<AccessRequestItem> {
    return apiClient.post<AccessRequestItem>(ENDPOINTS.ACCESS_REQUESTS.LIST, payload);
  },

  /**
   * List access requests (approver queue or requester history).
   */
  async listRequests(
    params?: AccessRequestListParams,
    signal?: AbortSignal
  ): Promise<AccessRequestListResponse> {
    return apiClient.get<AccessRequestListResponse>(ENDPOINTS.ACCESS_REQUESTS.LIST, {
      params: params as Record<string, unknown>,
      signal,
    });
  },

  /**
   * Retrieve single access request detail.
   */
  async getRequest(id: string, signal?: AbortSignal): Promise<AccessRequestItem> {
    return apiClient.get<AccessRequestItem>(ENDPOINTS.ACCESS_REQUESTS.DETAIL(id), { signal });
  },

  /**
   * Approve a pending access request and allocate product seat.
   */
  async approveRequest(
    id: string,
    payload?: DecideAccessRequestPayload
  ): Promise<AccessRequestItem & { assignment_id?: string }> {
    return apiClient.post<AccessRequestItem & { assignment_id?: string }>(
      ENDPOINTS.ACCESS_REQUESTS.APPROVE(id),
      payload || {}
    );
  },

  /**
   * Deny a pending access request with mandatory reason.
   */
  async denyRequest(
    id: string,
    payload: DecideAccessRequestPayload
  ): Promise<AccessRequestItem> {
    return apiClient.post<AccessRequestItem>(ENDPOINTS.ACCESS_REQUESTS.DENY(id), payload);
  },

  /**
   * Cancel a pending access request.
   */
  async cancelRequest(id: string): Promise<AccessRequestItem> {
    return apiClient.post<AccessRequestItem>(ENDPOINTS.ACCESS_REQUESTS.CANCEL(id), {});
  },
};
