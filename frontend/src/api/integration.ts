/**
 * Integration Hub API Client (Phase 5A + 5B).
 *
 * Provides typed fetch wrappers for connector registry, instances,
 * event ingestion, provisioning jobs, and identity/tenant/user mappings.
 * All requests route through the centralized apiClient.
 */

import { apiClient } from "./client.ts";
import { ENDPOINTS } from "./endpoints.ts";

// ── Types ─────────────────────────────────────────────────────────────────────

export interface IntegrationConnector {
  id: string;
  code: string;
  name: string;
  description: string;
  product: string | null;
  version: string;
  status: "active" | "deprecated" | "retired";
  capabilities: string[];
  created_at: string;
  updated_at: string;
}

export interface ConnectorInstance {
  id: string;
  connector: string;
  connector_code: string;
  organization: string;
  organization_name: string;
  label: string;
  /** Opaque reference only — never a raw secret value. */
  credential_ref: string;
  config: Record<string, unknown>;
  status: "active" | "suspended" | "disconnected";
  created_at: string;
  updated_at: string;
}

export interface IntegrationEvent {
  id: string;
  instance: string;
  event_type: string;
  event_key: string;
  payload: Record<string, unknown>;
  status: "received" | "processing" | "processed" | "failed" | "ignored";
  occurred_at: string;
  received_at: string;
  processed_at: string | null;
}

export interface ProvisioningJob {
  id: string;
  instance: string;
  organization: string;
  user: string | null;
  action: "provision" | "deprovision" | "update" | "sync";
  status: "queued" | "processing" | "completed" | "failed" | "cancelled" | "retry_scheduled";
  context: Record<string, unknown>;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
}

export interface IntegrationFailureAttempt {
  id: string;
  attempt_number: number;
  started_at: string;
  completed_at: string;
  outcome: "success" | "failure";
  failure_code: string;
  failure_detail: string;
  http_status: number | null;
  retry_after: string | null;
  created_at: string;
}

export interface ExternalIdentity {
  id: string;
  user: string;
  provider: string;
  provider_subject: string;
  provider_tenant: string;
  status: "active" | "suspended";
  created_at: string;
  updated_at: string;
}

export interface ExternalTenantMapping {
  id: string;
  organization: string;
  instance: string;
  external_tenant_id: string;
  created_at: string;
  updated_at: string;
}

export interface ExternalUserMapping {
  id: string;
  user: string;
  organization: string;
  instance: string;
  external_user_id: string;
  status: "active" | "suspended" | "orphaned";
  created_at: string;
  updated_at: string;
}

export interface IntegrationFailure {
  id: string;
  job: string | null;
  event: string | null;
  failure_code: string;
  failure_detail: string;
  failure_type: "transient" | "permanent";
  status: "open" | "retry_scheduled" | "dead_letter" | "resolved";
  retry_count: number;
  max_retries: number;
  retry_after: string | null;
  is_dead_letter: boolean;
  created_at: string;
  resolved_at: string | null;
  resolved_by: string | null;
  resolved_by_email: string | null;
  resolution_notes: string;
  instance_id: string | null;
  instance_label: string;
  organization_id: string | null;
  organization_name: string;
  connector_code: string;
  product_code: string;
  attempts?: IntegrationFailureAttempt[];
}

export interface IntegrationHealthSummary {
  control_plane: {
    status: "healthy" | "degraded" | "attention_required";
    total_connectors: number;
    total_instances: number;
    active_instances: number;
    suspended_instances: number;
    disconnected_instances: number;
  };
  summary?: {
    queued_job_count: number;
    stuck_queued_job_count: number;
    stuck_processing_job_count: number;
    orphaned_job_count: number;
    retry_scheduled_count: number;
    dead_letter_count: number;
    open_failure_count: number;
    resolved_failure_count: number;
    recent_failure_count: number;
    failure_rate: number;
  };
  jobs?: {
    queued_job_count: number;
    stuck_queued_job_count: number;
    stuck_processing_job_count: number;
    orphaned_job_count: number;
    recent_24h_completed_count: number;
    recent_24h_failed_count: number;
    total_active_jobs: number;
  };
  failures: {
    total_open: number;
    total_retry_scheduled: number;
    total_dead_letter: number;
    total_resolved: number;
    recent_24h_count: number;
    open_failure_count?: number;
    retry_scheduled_count?: number;
    dead_letter_count?: number;
    resolved_failure_count?: number;
    recent_failure_count?: number;
    failure_rate_pct?: number | null;
  };
  instance_health: Array<{
    id: string;
    label: string;
    connector_code: string;
    organization_name: string;
    status: string;
    open_failures: number;
    dead_letter_failures: number;
    latest_failure_at: string | null;
  }>;
  external_connectivity: {
    status: string;
    verified_connectors_count: number;
    unverified_connectors_count: number;
    detail: string;
    probed?: boolean;
    last_probed_at?: string | null;
    http_status?: number | null;
    latency_ms?: number | null;
  };
}

export interface PaginatedResponse<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

// ── API Calls ──────────────────────────────────────────────────────────────────

export const integrationApi = {
  // 5A: Connectors
  listConnectors: (): Promise<IntegrationConnector[]> =>
    apiClient.get<IntegrationConnector[]>(ENDPOINTS.INTEGRATION.CONNECTORS),

  createConnector: (data: Partial<IntegrationConnector>): Promise<IntegrationConnector> =>
    apiClient.post<IntegrationConnector>(ENDPOINTS.INTEGRATION.CONNECTORS, data),

  // 5A: Instances
  listInstances: (page = 1): Promise<PaginatedResponse<ConnectorInstance>> =>
    apiClient.get<PaginatedResponse<ConnectorInstance>>(`${ENDPOINTS.INTEGRATION.INSTANCES}?page=${page}`),

  createInstance: (data: Partial<ConnectorInstance>): Promise<ConnectorInstance> =>
    apiClient.post<ConnectorInstance>(ENDPOINTS.INTEGRATION.INSTANCES, data),

  // 5A: Events
  listEvents: (page = 1): Promise<PaginatedResponse<IntegrationEvent>> =>
    apiClient.get<PaginatedResponse<IntegrationEvent>>(`${ENDPOINTS.INTEGRATION.EVENTS}?page=${page}`),

  // 5A: Provisioning jobs
  listProvisioningJobs: (page = 1): Promise<PaginatedResponse<ProvisioningJob>> =>
    apiClient.get<PaginatedResponse<ProvisioningJob>>(`${ENDPOINTS.INTEGRATION.PROVISIONING_JOBS}?page=${page}`),

  getProvisioningJob: (id: string): Promise<ProvisioningJob> =>
    apiClient.get<ProvisioningJob>(ENDPOINTS.INTEGRATION.PROVISIONING_JOB_DETAIL(id)),

  // 5B: Mappings
  listExternalIdentities: (page = 1): Promise<PaginatedResponse<ExternalIdentity>> =>
    apiClient.get<PaginatedResponse<ExternalIdentity>>(`${ENDPOINTS.INTEGRATION.EXTERNAL_IDENTITIES}?page=${page}`),

  createExternalIdentity: (data: Partial<ExternalIdentity>): Promise<ExternalIdentity> =>
    apiClient.post<ExternalIdentity>(ENDPOINTS.INTEGRATION.EXTERNAL_IDENTITIES, data),

  listTenantMappings: (instanceId?: string, page = 1): Promise<PaginatedResponse<ExternalTenantMapping>> => {
    const qs = instanceId ? `?instance=${encodeURIComponent(instanceId)}&page=${page}` : `?page=${page}`;
    return apiClient.get<PaginatedResponse<ExternalTenantMapping>>(`${ENDPOINTS.INTEGRATION.TENANT_MAPPINGS}${qs}`);
  },

  createTenantMapping: (data: Partial<ExternalTenantMapping>): Promise<ExternalTenantMapping> =>
    apiClient.post<ExternalTenantMapping>(ENDPOINTS.INTEGRATION.TENANT_MAPPINGS, data),

  listUserMappings: (instanceId?: string, page = 1): Promise<PaginatedResponse<ExternalUserMapping>> => {
    const qs = instanceId ? `?instance=${encodeURIComponent(instanceId)}&page=${page}` : `?page=${page}`;
    return apiClient.get<PaginatedResponse<ExternalUserMapping>>(`${ENDPOINTS.INTEGRATION.USER_MAPPINGS}${qs}`);
  },

  createUserMapping: (data: Partial<ExternalUserMapping>): Promise<ExternalUserMapping> =>
    apiClient.post<ExternalUserMapping>(ENDPOINTS.INTEGRATION.USER_MAPPINGS, data),

  // 5G: Health Summary
  getHealth: (probe = false): Promise<IntegrationHealthSummary> => {
    const qs = probe ? "?probe=true" : "";
    return apiClient.get<IntegrationHealthSummary>(`${ENDPOINTS.INTEGRATION.HEALTH}${qs}`);
  },

  // 5G: Failures, Dead-Letter & Recovery
  listFailures: (params?: {
    instance?: string;
    organization?: string;
    status?: string;
    failure_type?: string;
    failure_code?: string;
    is_dead_letter?: boolean;
    page?: number;
  }): Promise<PaginatedResponse<IntegrationFailure>> => {
    const searchParams = new URLSearchParams();
    if (params?.instance) searchParams.set("instance", params.instance);
    if (params?.organization) searchParams.set("organization", params.organization);
    if (params?.status) searchParams.set("status", params.status);
    if (params?.failure_type) searchParams.set("failure_type", params.failure_type);
    if (params?.failure_code) searchParams.set("failure_code", params.failure_code);
    if (params?.is_dead_letter !== undefined) searchParams.set("is_dead_letter", String(params.is_dead_letter));
    if (params?.page) searchParams.set("page", String(params.page));
    const qs = searchParams.toString() ? `?${searchParams.toString()}` : "";
    return apiClient.get<PaginatedResponse<IntegrationFailure>>(`${ENDPOINTS.INTEGRATION.FAILURES}${qs}`);
  },

  getFailure: (id: string): Promise<IntegrationFailure> =>
    apiClient.get<IntegrationFailure>(ENDPOINTS.INTEGRATION.FAILURE_DETAIL(id)),

  resolveFailure: (id: string, notes: string): Promise<IntegrationFailure> =>
    apiClient.post<IntegrationFailure>(ENDPOINTS.INTEGRATION.FAILURE_RESOLVE(id), {
      resolution_notes: notes,
    }),

  markFailureDeadLetter: (id: string, reason?: string): Promise<IntegrationFailure> =>
    apiClient.post<IntegrationFailure>(ENDPOINTS.INTEGRATION.FAILURE_MARK_DEAD_LETTER(id), {
      reason: reason || "",
    }),

  scheduleFailureRetry: (id: string): Promise<IntegrationFailure> =>
    apiClient.post<IntegrationFailure>(ENDPOINTS.INTEGRATION.FAILURE_SCHEDULE_RETRY(id), {}),

  replayFailure: (id: string): Promise<IntegrationFailure> =>
    apiClient.post<IntegrationFailure>(ENDPOINTS.INTEGRATION.FAILURE_REPLAY(id), {}),
};

