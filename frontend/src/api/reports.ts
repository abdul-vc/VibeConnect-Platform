/**
 * Reports & Analytics API Client (Phase 4F).
 * Exclusively consumes centralized apiClient and ENDPOINTS.
 */

import { apiClient } from "./client.ts";
import { ENDPOINTS } from "./endpoints.ts";

export interface OwnerReportsSummary {
  organizations: {
    total: number;
    active: number;
    inactive: number;
  };
  product_adoption: Array<{
    product_id: string;
    product_code: string;
    product_name: string;
    adopted_tenants_count: number;
  }>;
  usage: {
    total_events: number;
    total_buckets: number;
    over_limit_buckets: number;
  };
  commercial: {
    active_subscriptions: number;
    total_invoices: number;
    paid_invoices: number;
    open_reconciliations: number;
  };
}

export interface TenantReportsSummary {
  seat_utilization: {
    total_assigned: number;
  };
  usage_buckets: Array<{
    meter_key: string;
    meter_name: string;
    unit: string;
    consumed: number;
    is_over_limit: boolean;
    period_start: string;
    period_end: string;
  }>;
  subscription: {
    id: string;
    plan_code: string;
    plan_name: string;
    currency: string;
    amount: string;
    billing_interval: string;
    status: string;
  } | null;
  invoices: {
    total: number;
    paid: number;
  };
}

export interface OwnerAnalyticsResponse {
  time_window: {
    start_date: string;
    end_date: string;
    days: number;
  };
  product_adoption: Array<{
    product_id: string;
    product_code: string;
    product_name: string;
    entitled_tenants: number;
    assigned_users: number;
  }>;
  seat_utilization: {
    total_active_seats: number;
    active_tenants: number;
  };
  sso_launch_activity: {
    codes_issued: number;
    codes_validated: number;
  };

  integration_health_distribution: {
    healthy: number;
    degraded: number;
    unhealthy: number;
  };
  support_activity_volume: {
    impersonation_sessions_started: number;
  };
  impersonation_metrics: {
    total_sessions: number;
    average_duration_seconds: number;
    status_breakdown: Record<string, number>;
  };
}

export interface TenantAnalyticsResponse {
  organization: {
    id: string;
    code: string;
    name: string;
  };
  time_window: {
    start_date: string;
    end_date: string;
    days: number;
  };
  product_adoption: Array<{
    product_id: string;
    product_code: string;
    product_name: string;
    assigned_users_count: number;
  }>;
  seat_utilization: {
    assigned_seats: number;
    has_active_subscription: boolean;
  };
  sso_launch_activity: {
    codes_issued: number;
    codes_validated: number;
  };

  component_health_indicators: {
    status: "healthy" | "degraded" | "unhealthy";
    active_connectors: number;
    suspended_connectors: number;
    disconnected_connectors: number;
    open_failures: number;
    retry_scheduled_failures: number;
    dead_letter_failures: number;
    stuck_jobs: number;
    open_reconciliations: number;
  };
  support_activity: {
    impersonation_sessions_in_window: number;
  };
}

export const reportsApi = {
  getOwnerSummary: async (): Promise<OwnerReportsSummary> => {
    return apiClient.get<OwnerReportsSummary>(ENDPOINTS.REPORTS.OWNER_SUMMARY);
  },

  getTenantSummary: async (): Promise<TenantReportsSummary> => {
    return apiClient.get<TenantReportsSummary>(ENDPOINTS.REPORTS.TENANT_SUMMARY);
  },

  getOwnerAnalytics: async (startDate?: string, endDate?: string): Promise<OwnerAnalyticsResponse> => {
    const params = new URLSearchParams();
    if (startDate) params.set("start_date", startDate);
    if (endDate) params.set("end_date", endDate);
    const queryString = params.toString() ? `?${params.toString()}` : "";
    return apiClient.get<OwnerAnalyticsResponse>(`${ENDPOINTS.REPORTS.OWNER_ANALYTICS}${queryString}`);
  },

  getTenantAnalytics: async (startDate?: string, endDate?: string): Promise<TenantAnalyticsResponse> => {
    const params = new URLSearchParams();
    if (startDate) params.set("start_date", startDate);
    if (endDate) params.set("end_date", endDate);
    const queryString = params.toString() ? `?${params.toString()}` : "";
    return apiClient.get<TenantAnalyticsResponse>(`${ENDPOINTS.REPORTS.TENANT_ANALYTICS}${queryString}`);
  },
};
