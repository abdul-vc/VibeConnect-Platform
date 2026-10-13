/**
 * Central Users Domain API (Phase 2D Stage 4/5).
 *
 * Exclusively consumes the centralized apiClient to communicate with versioned user endpoints.
 */

import { apiClient } from "./client.ts";
import { ENDPOINTS } from "./endpoints.ts";
import type {
  CreateUserPayload,
  UpdateUserPayload,
  UserDetail,
  UserLifecycleActionPayload,
  UserListParams,
  UserListResponse,
} from "./types.ts";

export const usersApi = {
  /**
   * List central users with server-side pagination, search, and status filtering.
   */
  async list(params?: UserListParams, signal?: AbortSignal): Promise<UserListResponse> {
    return apiClient.get<UserListResponse>(ENDPOINTS.USERS.LIST, {
      params,
      signal,
    });
  },

  /**
   * Retrieve single user details with zero sensitive credentials.
   */
  async get(id: string): Promise<UserDetail> {
    return apiClient.get<UserDetail>(ENDPOINTS.USERS.DETAIL(id));
  },

  /**
   * Create an unprivileged central user with unusable password.
   */
  async create(payload: CreateUserPayload): Promise<UserDetail> {
    return apiClient.post<UserDetail>(ENDPOINTS.USERS.LIST, payload);
  },

  /**
   * Update permitted profile fields (full_name only).
   */
  async update(id: string, payload: UpdateUserPayload): Promise<UserDetail> {
    return apiClient.patch<UserDetail>(ENDPOINTS.USERS.DETAIL(id), payload);
  },

  /**
   * Suspend an active user account.
   */
  async suspend(id: string, payload?: UserLifecycleActionPayload): Promise<UserDetail> {
    return apiClient.post<UserDetail>(ENDPOINTS.USERS.SUSPEND(id), payload || {});
  },

  /**
   * Reactivate a suspended user account.
   */
  async reactivate(id: string): Promise<UserDetail> {
    return apiClient.post<UserDetail>(ENDPOINTS.USERS.REACTIVATE(id), {});
  },

  /**
   * Disable a user account into the terminal disabled state.
   */
  async disable(id: string, payload?: UserLifecycleActionPayload): Promise<UserDetail> {
    return apiClient.post<UserDetail>(ENDPOINTS.USERS.DISABLE(id), payload || {});
  },

  /**
   * Anonymize a user account (Phase 6F Privacy / Irreversible de-identification).
   */
  async anonymize(
    id: string,
    payload: { reason: string; confirmation: boolean }
  ): Promise<UserDetail & { retention_notice?: string }> {
    return apiClient.post<UserDetail & { retention_notice?: string }>(
      ENDPOINTS.USERS.ANONYMIZE(id),
      payload
    );
  },
};

