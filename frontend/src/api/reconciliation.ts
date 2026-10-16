/**
 * Commercial Reconciliation API Client (Phase 4E).
 * Exclusively consumes centralized apiClient and ENDPOINTS.
 */

import { apiClient } from "./client.ts";
import { ENDPOINTS } from "./endpoints.ts";

export interface CommercialReconciliation {
  id: string;
  organization: string;
  organization_name?: string;
  organization_code?: string;
  subscription: string | null;
  subscription_plan_code?: string;
  issue_code:
    | "SUB_ACTIVE_NO_BILLING_ACCOUNT"
    | "INVOICE_PRICE_MISMATCH"
    | "ORPHANED_ENTITLEMENT"
    | string;
  status: "open" | "resolved";
  details: Record<string, unknown>;
  detected_at: string;
  resolved_at: string | null;
  resolved_by: string | null;
  resolved_by_email?: string | null;
  resolution_reason: string;
  created_at: string;
  updated_at: string;
}

export interface ReconciliationListResponse {
  count: number;
  results: CommercialReconciliation[];
  next?: string | null;
  previous?: string | null;
}

export const reconciliationApi = {
  getReconciliations: async (params?: {
    status?: string;
    organization?: string;
    page?: number;
    page_size?: number;
  }): Promise<ReconciliationListResponse> => {
    const searchParams = new URLSearchParams();
    if (params?.status) searchParams.append("status", params.status);
    if (params?.organization) searchParams.append("organization", params.organization);
    if (params?.page) searchParams.append("page", String(params.page));
    if (params?.page_size) searchParams.append("page_size", String(params.page_size));

    const queryString = searchParams.toString();
    const url = queryString
      ? `${ENDPOINTS.BILLING.RECONCILIATIONS}?${queryString}`
      : ENDPOINTS.BILLING.RECONCILIATIONS;

    return apiClient.get<ReconciliationListResponse>(url);
  },

  resolveReconciliation: async (
    id: string,
    resolution_reason: string
  ): Promise<CommercialReconciliation> => {
    return apiClient.post<CommercialReconciliation>(
      ENDPOINTS.BILLING.RECONCILIATION_RESOLVE(id),
      { resolution_reason }
    );
  },

  triggerReconciliation: async (payload?: {
    organization_id?: string;
  }): Promise<{ message: string; task_id?: string }> => {
    return apiClient.post<{ message: string; task_id?: string }>(
      ENDPOINTS.BILLING.RECONCILIATION_TRIGGER,
      payload || {}
    );
  },
};
