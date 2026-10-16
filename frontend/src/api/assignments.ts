/**
 * Assignment Domain API Client (Phase 2F Part E).
 *
 * Implements typed wrappers for tenant assignment lifecycle endpoints:
 * - List & detail
 * - Create assignment
 * - Suspend, reactivate, revoke lifecycle actions
 * - Module replacement
 * - Selector endpoints (products, members, modules)
 *
 * All operations consume the centralized apiClient.
 */

import { apiClient } from "./client.ts";
import { ENDPOINTS } from "./endpoints.ts";
import type {
  AssignmentDetailItem,
  AssignmentListParams,
  CreateAssignmentPayload,
  PaginatedAssignmentResponse,
  PaginatedSelectorMemberResponse,
  ReplaceModulesPayload,
  RevokeAssignmentPayload,
  SelectorMemberParams,
  SelectorModuleItem,
  SelectorProductItem,
  SuspendAssignmentPayload,
} from "./types.ts";

export const assignmentsApi = {
  /**
   * List paginated assignments with optional search, product, and status filters.
   */
  async listAssignments(params?: AssignmentListParams): Promise<PaginatedAssignmentResponse> {
    const cleanParams: Record<string, string | number> = {};
    if (params?.page) cleanParams.page = params.page;
    if (params?.page_size) cleanParams.page_size = params.page_size;
    if (params?.search && params.search.trim()) cleanParams.search = params.search.trim();
    if (params?.product_id && params.product_id.trim()) cleanParams.product_id = params.product_id.trim();
    if (params?.status && params.status.trim()) cleanParams.status = params.status.trim();

    return apiClient.get<PaginatedAssignmentResponse>(ENDPOINTS.ASSIGNMENTS.LIST, {
      params: cleanParams,
    });
  },

  /**
   * Fetch single assignment details including membership and enabled modules.
   */
  async getAssignment(id: string): Promise<AssignmentDetailItem> {
    return apiClient.get<AssignmentDetailItem>(ENDPOINTS.ASSIGNMENTS.DETAIL(id));
  },

  /**
   * Create a new product assignment for an organization member.
   */
  async createAssignment(payload: CreateAssignmentPayload): Promise<AssignmentDetailItem> {
    return apiClient.post<AssignmentDetailItem>(ENDPOINTS.ASSIGNMENTS.LIST, payload);
  },

  /**
   * Suspend an active assignment with a reason (1-500 characters).
   */
  async suspendAssignment(id: string, payload: SuspendAssignmentPayload): Promise<AssignmentDetailItem> {
    return apiClient.post<AssignmentDetailItem>(ENDPOINTS.ASSIGNMENTS.SUSPEND(id), payload);
  },

  /**
   * Reactivate a suspended assignment.
   */
  async reactivateAssignment(id: string): Promise<AssignmentDetailItem> {
    return apiClient.post<AssignmentDetailItem>(ENDPOINTS.ASSIGNMENTS.REACTIVATE(id), {});
  },

  /**
   * Revoke an assignment with a reason (1-500 characters).
   */
  async revokeAssignment(id: string, payload: RevokeAssignmentPayload): Promise<AssignmentDetailItem> {
    return apiClient.post<AssignmentDetailItem>(ENDPOINTS.ASSIGNMENTS.REVOKE(id), payload);
  },

  /**
   * Replace all assigned modules for an assignment.
   */
  async replaceModules(id: string, payload: ReplaceModulesPayload): Promise<AssignmentDetailItem> {
    return apiClient.patch<AssignmentDetailItem>(ENDPOINTS.ASSIGNMENTS.MODULES(id), payload);
  },

  /**
   * Fetch entitled products with seat allocation quotas for selection.
   */
  async getSelectorProducts(): Promise<SelectorProductItem[]> {
    return apiClient.get<SelectorProductItem[]>(ENDPOINTS.ASSIGNMENTS.SELECTORS.PRODUCTS);
  },

  /**
   * Fetch eligible organization members for the selected product (paginated).
   */
  async getSelectorMembers(params: SelectorMemberParams): Promise<PaginatedSelectorMemberResponse> {
    const cleanParams: Record<string, string | number> = {
      product_id: params.product_id,
    };
    if (params.search && params.search.trim()) cleanParams.search = params.search.trim();
    if (params.page && params.page > 1) cleanParams.page = params.page;
    if (params.page_size) cleanParams.page_size = params.page_size;

    return apiClient.get<PaginatedSelectorMemberResponse>(ENDPOINTS.ASSIGNMENTS.SELECTORS.MEMBERS, {
      params: cleanParams,
    });
  },

  /**
   * Fetch entitled modules for the selected product.
   */
  async getSelectorModules(productId: string): Promise<SelectorModuleItem[]> {
    return apiClient.get<SelectorModuleItem[]>(ENDPOINTS.ASSIGNMENTS.SELECTORS.MODULES, {
      params: { product_id: productId },
    });
  },
};
