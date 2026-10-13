/**
 * Support Console API Client Module (Phase 6C).
 *
 * Exclusively consumes centralized apiClient with zero hardcoded URLs.
 */

import { apiClient } from "./client.ts";
import { ENDPOINTS } from "./endpoints.ts";

export interface SupportOrganizationSummary {
  readonly id: string;
  readonly code: string;
  readonly name: string;
  readonly status: string;
  readonly created_at: string;
  readonly updated_at: string;
}

export interface SupportConnectorInstance {
  readonly id: string;
  readonly connector_id: string;
  readonly connector_code: string;
  readonly connector_name: string;
  readonly label: string;
  readonly status: string;
  readonly created_at: string;
  readonly updated_at: string;
}

export interface SupportFailure {
  readonly id: string;
  readonly instance_id: string;
  readonly instance_label?: string;
  readonly connector_code?: string;
  readonly failure_type: string;
  readonly failure_code: string;
  readonly status: string;
  readonly retry_count: number;
  readonly max_retries: number;
  readonly retry_after: string | null;
  readonly sanitized_detail: string;
  readonly resolution_notes: string;
  readonly resolved_at: string | null;
  readonly created_at: string;
  readonly updated_at: string;
}

export interface SupportReconciliationIssue {
  readonly id: string;
  readonly instance_id: string;
  readonly instance_label?: string;
  readonly connector_code?: string;
  readonly issue_code: string;
  readonly description: string;
  readonly severity: string;
  readonly status: string;
  readonly detected_at: string;
}

export interface SupportAuditEntry {
  readonly id: string;
  readonly action: string;
  readonly target_type: string;
  readonly target_id: string;
  readonly target_repr: string;
  readonly operation_source: string;
  readonly timestamp: string;
}

export interface SupportDiagnosticsHealth {
  readonly control_plane_status: "healthy" | "degraded" | "attention_required";
  readonly instances: {
    readonly total: number;
    readonly active: number;
    readonly suspended: number;
    readonly disconnected: number;
  };
  readonly failures: {
    readonly open: number;
    readonly retry_scheduled: number;
    readonly dead_letter: number;
    readonly resolved: number;
    readonly last_24h: number;
  };
  readonly jobs: {
    readonly queued: number;
    readonly processing: number;
    readonly failed: number;
    readonly completed: number;
    readonly stuck_queued: number;
    readonly stuck_processing: number;
    readonly orphaned: number;
  };
  readonly open_reconciliation_issues_count: number;
}

export interface SupportStuckJob {
  readonly id: string;
  readonly action: string;
  readonly status: string;
  readonly created_at: string;
  readonly updated_at: string;
  readonly classification?: {
    readonly category: string;
    readonly reason: string;
    readonly age_seconds: number;
    readonly is_recoverable: boolean;
    readonly recommended_recovery_action: string;
  };
}

export interface SupportDiagnosticsResponse {
  readonly organization: SupportOrganizationSummary;
  readonly health: SupportDiagnosticsHealth;
  readonly connector_instances: readonly SupportConnectorInstance[];
  readonly stuck_jobs: readonly SupportStuckJob[];
  readonly dead_letter_failures: readonly SupportFailure[];
  readonly open_failures: readonly SupportFailure[];
  readonly recent_resolved_failures: readonly SupportFailure[];
  readonly reconciliation_issues: readonly SupportReconciliationIssue[];
  readonly recent_audit_logs: readonly SupportAuditEntry[];
}

export const supportApi = {
  /**
   * Search organizations by code or name for Support Operator diagnosis.
   */
  async searchOrganizations(query: string = ""): Promise<readonly SupportOrganizationSummary[]> {
    const url = query.trim()
      ? `${ENDPOINTS.SUPPORT.ORGANIZATIONS}?q=${encodeURIComponent(query.trim())}`
      : ENDPOINTS.SUPPORT.ORGANIZATIONS;
    return apiClient.get<SupportOrganizationSummary[]>(url);
  },

  /**
   * Retrieve aggregated diagnostic state for a specific organization.
   */
  async getOrganizationDiagnostics(organizationId: string): Promise<SupportDiagnosticsResponse> {
    return apiClient.get<SupportDiagnosticsResponse>(
      ENDPOINTS.SUPPORT.DIAGNOSTICS(organizationId)
    );
  },

  /**
   * Retry an eligible failed operation.
   */
  async retryFailure(organizationId: string, failureId: string): Promise<SupportFailure> {
    return apiClient.post<SupportFailure>(
      ENDPOINTS.SUPPORT.RETRY_FAILURE(organizationId, failureId),
      {}
    );
  },

  /**
   * Replay an eligible dead-letter failure.
   */
  async replayFailure(organizationId: string, failureId: string): Promise<SupportFailure> {
    return apiClient.post<SupportFailure>(
      ENDPOINTS.SUPPORT.REPLAY_FAILURE(organizationId, failureId),
      {}
    );
  },

  /**
   * Mark a failure as resolved with mandatory operator resolution notes.
   */
  async resolveFailure(
    organizationId: string,
    failureId: string,
    resolutionNotes: string
  ): Promise<SupportFailure> {
    return apiClient.post<SupportFailure>(
      ENDPOINTS.SUPPORT.RESOLVE_FAILURE(organizationId, failureId),
      { resolution_notes: resolutionNotes }
    );
  },

  /**
   * Mark a reconciliation issue as resolved with mandatory operator notes.
   */
  async resolveReconciliation(
    organizationId: string,
    issueId: string,
    resolutionNotes: string
  ): Promise<SupportReconciliationIssue> {
    return apiClient.post<SupportReconciliationIssue>(
      ENDPOINTS.SUPPORT.RESOLVE_RECONCILIATION(organizationId, issueId),
      { resolution_notes: resolutionNotes }
    );
  },

  /**
   * Phase 6D: List eligible target users in an organization for impersonation.
   */
  async getEligibleTargets(organizationId: string): Promise<readonly EligibleTargetUser[]> {
    const res = await apiClient.get<{ targets: readonly EligibleTargetUser[] }>(
      ENDPOINTS.SUPPORT.IMPERSONATION_TARGETS(organizationId)
    );
    return res.targets;
  },

  /**
   * Phase 6D: Initiate an audited, time-limited impersonation session.
   */
  async createImpersonationSession(payload: {
    target_user_id: string;
    target_organization_id: string;
    reason: string;
    ticket_reference?: string;
  }): Promise<SupportImpersonationSessionData> {
    return apiClient.post<SupportImpersonationSessionData>(
      ENDPOINTS.SUPPORT.IMPERSONATION_SESSIONS,
      payload
    );
  },

  /**
   * Phase 6D: Fetch the current operator's active impersonation session with server-derived expiry.
   */
  async getActiveImpersonationSession(): Promise<SupportImpersonationSessionData | null> {
    const res = await apiClient.get<{ active_session: SupportImpersonationSessionData | null }>(
      ENDPOINTS.SUPPORT.IMPERSONATION_ACTIVE_SESSION
    );
    return res.active_session;
  },

  /**
   * Phase 6D: Terminate an active impersonation session.
   */
  async terminateImpersonationSession(
    sessionId: string,
    reason?: string
  ): Promise<SupportImpersonationSessionData> {
    return apiClient.post<SupportImpersonationSessionData>(
      ENDPOINTS.SUPPORT.IMPERSONATION_TERMINATE(sessionId),
      { reason: reason || "Operator ended impersonation session." }
    );
  },

  /**
   * Phase 6C: List active support operator role assignments (Platform Owner only).
   */
  async listSupportOperators(): Promise<readonly SupportOperatorAssignment[]> {
    return apiClient.get<readonly SupportOperatorAssignment[]>(
      ENDPOINTS.SUPPORT.OPERATORS
    );
  },

  /**
   * Phase 6C: Grant a predefined support role to an active platform user (Platform Owner only).
   */
  async grantSupportRole(payload: {
    user_id: string;
    role_code: string;
  }): Promise<SupportOperatorAssignment> {
    return apiClient.post<SupportOperatorAssignment>(
      ENDPOINTS.SUPPORT.OPERATORS,
      payload
    );
  },

  /**
   * Phase 6C: Revoke a support operator role assignment (Platform Owner only).
   */
  async revokeSupportRole(assignmentId: string): Promise<void> {
    await apiClient.delete<void>(
      ENDPOINTS.SUPPORT.OPERATOR_DETAIL(assignmentId)
    );
  },
};

export interface SupportOperatorAssignment {
  readonly id: string;
  readonly user_id: string;
  readonly user_email: string;
  readonly user_name: string;
  readonly role_code: string;
  readonly role_name: string;
  readonly created_at: string;
}

export interface EligibleTargetUser {
  readonly id: string;
  readonly email: string;
  readonly full_name: string;
  readonly membership_type: string;
}

export interface SupportImpersonationSessionData {
  readonly id: string;
  readonly operator_email: string;
  readonly target_user: string;
  readonly target_user_email: string;
  readonly target_user_name: string;
  readonly target_organization: string;
  readonly target_organization_code: string;
  readonly target_organization_name: string;
  readonly reason: string;
  readonly ticket_reference: string;
  readonly status: string;
  readonly created_at: string;
  readonly expires_at: string;
  readonly terminated_at: string | null;
  readonly correlation_id: string;
  readonly remaining_seconds: number;
}

