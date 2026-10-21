/**
 * Notifications Domain API Client (Phase 3A).
 *
 * Exclusively consumes centralized apiClient and ENDPOINTS.
 */

import { apiClient } from "./client.ts";
import { ENDPOINTS } from "./endpoints.ts";

export interface NotificationTemplate {
  id: string;
  code: string;
  name: string;
  channel: string;
  version: number;
  subject_template: string;
  body_ref: string;
  status: "draft" | "active" | "retired";
  is_transactional: boolean;
  created_at: string;
  updated_at: string;
}

export interface NotificationDelivery {
  id: string;
  template: string;
  template_code: string;
  template_name: string;
  channel: string;
  recipient_email: string;
  recipient_user: string | null;
  status: "queued" | "sent" | "failed" | "retrying";
  retry_count: number;
  max_retries: number;
  failure_reason: string;
  payload_context: Record<string, unknown>;
  queued_at: string;
  sent_at: string | null;
  failed_at: string | null;
}

export interface NotificationTemplateListResponse {
  count: number;
  next: string | null;
  previous: string | null;
  results: NotificationTemplate[];
}

export interface NotificationDeliveryListResponse {
  count: number;
  next: string | null;
  previous: string | null;
  results: NotificationDelivery[];
}

export interface TemplatePreviewResponse {
  template_id: string;
  code: string;
  name?: string;
  version: number;
  channel: string;
  rendered_subject: string;
  rendered_body?: string;
  body_ref: string;
  context: Record<string, unknown>;
  supported_variables?: string[];
  unresolved_variables?: string[];
}

export const notificationsApi = {
  async listTemplates(
    params?: { channel?: string; status?: string; search?: string; page?: number },
    signal?: AbortSignal
  ): Promise<NotificationTemplateListResponse> {
    return apiClient.get<NotificationTemplateListResponse>(ENDPOINTS.NOTIFICATIONS.TEMPLATES, {
      params,
      signal,
    });
  },

  async getTemplate(id: string, signal?: AbortSignal): Promise<NotificationTemplate> {
    return apiClient.get<NotificationTemplate>(ENDPOINTS.NOTIFICATIONS.TEMPLATE_DETAIL(id), { signal });
  },

  async createNewVersion(
    id: string,
    payload: { subject_template: string; body_ref: string; name?: string; is_transactional?: boolean }
  ): Promise<NotificationTemplate> {
    return apiClient.post<NotificationTemplate>(ENDPOINTS.NOTIFICATIONS.NEW_VERSION(id), payload);
  },

  async retireTemplate(id: string): Promise<NotificationTemplate> {
    return apiClient.post<NotificationTemplate>(ENDPOINTS.NOTIFICATIONS.RETIRE(id), {});
  },

  async previewTemplate(
    id: string,
    context?: Record<string, unknown>
  ): Promise<TemplatePreviewResponse> {
    return apiClient.post<TemplatePreviewResponse>(ENDPOINTS.NOTIFICATIONS.PREVIEW(id), { context: context || {} });
  },

  async listDeliveries(
    params?: { status?: string; channel?: string; search?: string; page?: number },
    signal?: AbortSignal
  ): Promise<NotificationDeliveryListResponse> {
    return apiClient.get<NotificationDeliveryListResponse>(ENDPOINTS.NOTIFICATIONS.DELIVERIES, {
      params,
      signal,
    });
  },

  async retryDelivery(id: string): Promise<NotificationDelivery> {
    return apiClient.post<NotificationDelivery>(ENDPOINTS.NOTIFICATIONS.RETRY(id), {});
  },
};
