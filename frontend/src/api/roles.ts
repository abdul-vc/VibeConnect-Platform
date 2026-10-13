/**
 * Roles & Permissions API Service (Phase 2E Stage 6).
 *
 * Exclusively consumes the centralized apiClient to communicate with:
 * - Tenant Admin Access Catalog & Role CRUD endpoints
 * - Tenant Administrative Membership & Role Assignment endpoints
 * - Platform Owner Console Policy & Permission Ceiling endpoints
 */

import { apiClient } from "./client.ts";
import { ENDPOINTS } from "./endpoints.ts";
import type {
  AccessCatalogResponse,
  AdministrativeMembershipItem,
  AssignMembershipRolePayload,
  ConsoleModulePolicyItem,
  CreateRolePayload,
  PaginatedAdministrativeMembershipResponse,
  PaginatedRoleResponse,
  PermissionCeilingItem,
  RoleItem,
  UpdateConsoleModulePolicyPayload,
  UpdatePermissionCeilingPayload,
  UpdateRolePayload,
} from "./types.ts";

export const rolesApi = {
  /**
   * Fetch modules and permissions grantable by the current Tenant Admin.
   */
  async getAccessCatalog(signal?: AbortSignal): Promise<AccessCatalogResponse> {
    return apiClient.get<AccessCatalogResponse>(ENDPOINTS.TENANT_ROLES.ACCESS_CATALOG, { signal });
  },

  /**
   * List administrative roles for the active tenant organization (paginated).
   */
  async listRoles(
    params?: { page?: number; page_size?: number },
    signal?: AbortSignal
  ): Promise<PaginatedRoleResponse> {
    return apiClient.get<PaginatedRoleResponse>(ENDPOINTS.TENANT_ROLES.LIST, { params, signal });
  },

  /**
   * Retrieve a single role detail by ID.
   */
  async getRole(roleId: string, signal?: AbortSignal): Promise<RoleItem> {
    return apiClient.get<RoleItem>(ENDPOINTS.TENANT_ROLES.DETAIL(roleId), { signal });
  },

  /**
   * Create a new custom organization role.
   */
  async createRole(payload: CreateRolePayload): Promise<RoleItem> {
    return apiClient.post<RoleItem>(ENDPOINTS.TENANT_ROLES.LIST, payload);
  },

  /**
   * Update an existing custom organization role.
   */
  async updateRole(roleId: string, payload: UpdateRolePayload): Promise<RoleItem> {
    return apiClient.patch<RoleItem>(ENDPOINTS.TENANT_ROLES.DETAIL(roleId), payload);
  },

  /**
   * Retire an unused custom organization role.
   */
  async retireRole(roleId: string): Promise<RoleItem> {
    return apiClient.post<RoleItem>(ENDPOINTS.TENANT_ROLES.RETIRE(roleId), {});
  },

  /**
   * List tenant administrator memberships for the active organization with optional status filtering.
   */
  async listAdminMemberships(
    params?: { page?: number; page_size?: number; status?: string },
    signal?: AbortSignal
  ): Promise<PaginatedAdministrativeMembershipResponse> {
    return apiClient.get<PaginatedAdministrativeMembershipResponse>(
      ENDPOINTS.TENANT_ROLES.ADMIN_MEMBERSHIPS,
      { params, signal }
    );
  },

  /**
   * Assign or reset an administrative role on a tenant admin membership.
   */
  async assignMembershipRole(
    membershipId: string,
    payload: AssignMembershipRolePayload
  ): Promise<AdministrativeMembershipItem> {
    return apiClient.patch<AdministrativeMembershipItem>(
      ENDPOINTS.TENANT_ROLES.ASSIGN_ROLE(membershipId),
      payload
    );
  },

  /**
   * List console module policies for an organization (Platform Owner only).
   */
  async listConsolePolicies(
    orgId: string,
    signal?: AbortSignal
  ): Promise<readonly ConsoleModulePolicyItem[]> {
    return apiClient.get<readonly ConsoleModulePolicyItem[]>(
      ENDPOINTS.CONSOLE_POLICIES.LIST(orgId),
      { signal }
    );
  },

  /**
   * Update console module policy for an organization (Platform Owner only).
   */
  async updateConsolePolicy(
    orgId: string,
    moduleKey: string,
    payload: UpdateConsoleModulePolicyPayload
  ): Promise<ConsoleModulePolicyItem> {
    return apiClient.patch<ConsoleModulePolicyItem>(
      ENDPOINTS.CONSOLE_POLICIES.DETAIL(orgId, moduleKey),
      payload
    );
  },

  /**
   * List permission ceilings for an organization (Platform Owner only).
   */
  async listPermissionCeilings(
    orgId: string,
    signal?: AbortSignal
  ): Promise<readonly PermissionCeilingItem[]> {
    return apiClient.get<readonly PermissionCeilingItem[]>(
      ENDPOINTS.PERMISSION_CEILINGS.LIST(orgId),
      { signal }
    );
  },

  /**
   * Update permission ceiling for an organization (Platform Owner only).
   */
  async updatePermissionCeiling(
    orgId: string,
    permissionKey: string,
    payload: UpdatePermissionCeilingPayload
  ): Promise<PermissionCeilingItem> {
    return apiClient.patch<PermissionCeilingItem>(
      ENDPOINTS.PERMISSION_CEILINGS.DETAIL(orgId, permissionKey),
      payload
    );
  },
};
