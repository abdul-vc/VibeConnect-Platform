/**
 * LMS Integration Reconciliation API Client (Phase 5D).
 *
 * Provides typed methods for querying, triggering, and resolving
 * LMS identity and mapping reconciliation issues.
 * Routes exclusively through centralized apiClient.
 */

import { apiClient } from "./client.ts";
import { ENDPOINTS } from "./endpoints.ts";

export interface IntegrationReconciliationIssue {
  id: string;
  instance: string;
  instance_label?: string;
  connector_code?: string;
  issue_code: string;
  subject_type: string;
  subject_id: string;
  details: Record<string, unknown>;
  status: "OPEN" | "RESOLVED";
  detected_at: string;
  resolved_at: string | null;
  resolved_by: string | null;
  resolved_by_email: string | null;
  resolution_notes: string;
}

export interface PaginatedIntegrationReconciliationIssues {
  count: number;
  next: string | null;
  previous: string | null;
  results: IntegrationReconciliationIssue[];
}

export interface TriggerLmsReconciliationResponse {
  detected_count: number;
  open_issues_count: number;
  issues: IntegrationReconciliationIssue[];
}

export const integrationReconciliationApi = {
  getIssues: async (params?: {
    status?: string;
    instance_id?: string;
    issue_code?: string;
    page?: number;
  }): Promise<PaginatedIntegrationReconciliationIssues> => {
    return apiClient.get<PaginatedIntegrationReconciliationIssues>(
      ENDPOINTS.INTEGRATION.RECONCILIATION.LIST,
      { params }
    );
  },

  triggerReconciliation: async (
    instance_id?: string
  ): Promise<TriggerLmsReconciliationResponse> => {
    return apiClient.post<TriggerLmsReconciliationResponse>(
      ENDPOINTS.INTEGRATION.RECONCILIATION.RUN,
      { instance_id }
    );
  },

  resolveIssue: async (
    issueId: string,
    resolution_notes: string
  ): Promise<IntegrationReconciliationIssue> => {
    return apiClient.post<IntegrationReconciliationIssue>(
      ENDPOINTS.INTEGRATION.RECONCILIATION.RESOLVE(issueId),
      { resolution_notes }
    );
  },
};
