/**
 * Organization Memberships Domain API (Phase 2D Stage 4/5).
 *
 * Exclusively consumes the centralized apiClient to communicate with versioned membership endpoints.
 */

import { apiClient } from "./client.ts";
import { ENDPOINTS } from "./endpoints.ts";
import type {
  CreateMembershipPayload,
  MembershipLifecycleActionPayload,
  OrganizationMembershipItem,
  OrganizationMembershipListParams,
  OrganizationMembershipListResponse,
  UpdateMembershipTypePayload,
} from "./types.ts";

export const membershipsApi = {
  /**
   * List memberships for a specific organization with filtering and pagination.
   */
  async list(
    orgId: string,
    params?: OrganizationMembershipListParams,
    signal?: AbortSignal
  ): Promise<OrganizationMembershipListResponse> {
    return apiClient.get<OrganizationMembershipListResponse>(ENDPOINTS.MEMBERSHIPS.LIST(orgId), {
      params,
      signal,
    });
  },

  /**
   * Retrieve a single membership detail for an organization.
   */
  async get(orgId: string, id: string): Promise<OrganizationMembershipItem> {
    return apiClient.get<OrganizationMembershipItem>(ENDPOINTS.MEMBERSHIPS.DETAIL(orgId, id));
  },

  /**
   * Grant membership in an organization to an active user.
   */
  async create(orgId: string, payload: CreateMembershipPayload): Promise<OrganizationMembershipItem> {
    return apiClient.post<OrganizationMembershipItem>(ENDPOINTS.MEMBERSHIPS.LIST(orgId), payload);
  },

  /**
   * Update membership type (member <-> tenant_admin).
   */
  async updateType(
    orgId: string,
    id: string,
    payload: UpdateMembershipTypePayload
  ): Promise<OrganizationMembershipItem> {
    return apiClient.patch<OrganizationMembershipItem>(ENDPOINTS.MEMBERSHIPS.DETAIL(orgId, id), payload);
  },

  /**
   * Suspend an active membership.
   */
  async suspend(
    orgId: string,
    id: string,
    payload?: MembershipLifecycleActionPayload
  ): Promise<OrganizationMembershipItem> {
    return apiClient.post<OrganizationMembershipItem>(ENDPOINTS.MEMBERSHIPS.SUSPEND(orgId, id), payload || {});
  },

  /**
   * Reactivate a suspended membership.
   */
  async reactivate(orgId: string, id: string): Promise<OrganizationMembershipItem> {
    return apiClient.post<OrganizationMembershipItem>(ENDPOINTS.MEMBERSHIPS.REACTIVATE(orgId, id), {});
  },

  /**
   * End an active or suspended membership.
   */
  async end(
    orgId: string,
    id: string,
    payload?: MembershipLifecycleActionPayload
  ): Promise<OrganizationMembershipItem> {
    return apiClient.post<OrganizationMembershipItem>(ENDPOINTS.MEMBERSHIPS.END(orgId, id), payload || {});
  },

  /**
   * Explicitly restore an ended membership.
   */
  async restore(orgId: string, id: string): Promise<OrganizationMembershipItem> {
    return apiClient.post<OrganizationMembershipItem>(ENDPOINTS.MEMBERSHIPS.RESTORE(orgId, id), {});
  },
};
