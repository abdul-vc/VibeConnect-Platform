/**
 * Developer Console API Client module.
 *
 * Exclusively consumes the centralized apiClient and ENDPOINTS.
 */

import { apiClient } from "./client.ts";
import { ENDPOINTS } from "./endpoints.ts";

export interface DeveloperApplication {
  id: string;
  name: string;
  description: string;
  status: "active" | "suspended" | "revoked";
  organization: {
    id: string;
    code: string;
    name: string;
  };
  created_by: {
    id: string;
    email: string;
    full_name: string;
  };
  active_keys_count: number;
  created_at: string;
  updated_at: string;
}

export interface DeveloperApiKey {
  id: string;
  application_id: string;
  name: string;
  key_prefix: string;
  scopes: string[];
  status: "active" | "expired" | "revoked";
  plaintext_key?: string;
  expires_at: string | null;
  last_used_at: string | null;
  created_at: string;
  revoked_at: string | null;
}

export interface DeveloperAppListResponse {
  results: DeveloperApplication[];
  count: number;
}

export interface DeveloperKeyListResponse {
  results: DeveloperApiKey[];
  count: number;
}

export interface DeveloperWebhookSubscription {
  id: string;
  application_id: string;
  target_url: string;
  event_topics: string[];
  status: "active" | "suspended" | "revoked";
  signing_secret?: string;
  created_at: string;
  updated_at: string;
}

export interface DeveloperWebhookDelivery {
  id: string;
  subscription_id: string;
  event_id: string;
  event_type: string;
  payload: Record<string, unknown>;
  status: "pending" | "delivered" | "failed" | "dead_letter";
  status_code: number | null;
  attempt_count: number;
  max_attempts: number;
  next_retry_at: string | null;
  delivered_at: string | null;
  response_body: string;
  created_at: string;
  updated_at: string;
}

export interface DeveloperWebhookListResponse {
  results: DeveloperWebhookSubscription[];
  count: number;
}

export interface DeveloperDeliveryListResponse {
  results: DeveloperWebhookDelivery[];
  count: number;
}

export const developerApi = {
  // Tenant Admin methods
  async listTenantApps(search?: string): Promise<DeveloperAppListResponse> {
    const url = search
      ? `${ENDPOINTS.DEVELOPER.TENANT.APPS}?search=${encodeURIComponent(search)}`
      : ENDPOINTS.DEVELOPER.TENANT.APPS;
    return apiClient.get<DeveloperAppListResponse>(url);
  },

  async createTenantApp(data: { name: string; description?: string }): Promise<DeveloperApplication> {
    return apiClient.post<DeveloperApplication>(ENDPOINTS.DEVELOPER.TENANT.APPS, data);
  },

  async getTenantApp(id: string): Promise<DeveloperApplication> {
    return apiClient.get<DeveloperApplication>(ENDPOINTS.DEVELOPER.TENANT.APP_DETAIL(id));
  },

  async updateTenantApp(id: string, data: { name?: string; description?: string }): Promise<DeveloperApplication> {
    return apiClient.patch<DeveloperApplication>(ENDPOINTS.DEVELOPER.TENANT.APP_DETAIL(id), data);
  },

  async suspendTenantApp(id: string, reason?: string): Promise<DeveloperApplication> {
    return apiClient.post<DeveloperApplication>(ENDPOINTS.DEVELOPER.TENANT.APP_SUSPEND(id), { reason });
  },

  async reactivateTenantApp(id: string, reason?: string): Promise<DeveloperApplication> {
    return apiClient.post<DeveloperApplication>(ENDPOINTS.DEVELOPER.TENANT.APP_REACTIVATE(id), { reason });
  },

  async revokeTenantApp(id: string, reason?: string): Promise<DeveloperApplication> {
    return apiClient.post<DeveloperApplication>(ENDPOINTS.DEVELOPER.TENANT.APP_REVOKE(id), { reason });
  },

  async listTenantKeys(appId: string): Promise<DeveloperKeyListResponse> {
    return apiClient.get<DeveloperKeyListResponse>(ENDPOINTS.DEVELOPER.TENANT.KEYS(appId));
  },

  async createTenantKey(
    appId: string,
    data: { name: string; scopes: string[]; expires_at?: string | null }
  ): Promise<DeveloperApiKey> {
    return apiClient.post<DeveloperApiKey>(ENDPOINTS.DEVELOPER.TENANT.KEYS(appId), data);
  },

  async rotateTenantKey(
    appId: string,
    keyId: string,
    data?: { name?: string; expires_at?: string | null }
  ): Promise<DeveloperApiKey> {
    return apiClient.post<DeveloperApiKey>(ENDPOINTS.DEVELOPER.TENANT.KEY_ROTATE(appId, keyId), data || {});
  },

  async revokeTenantKey(appId: string, keyId: string, reason?: string): Promise<DeveloperApiKey> {
    return apiClient.post<DeveloperApiKey>(ENDPOINTS.DEVELOPER.TENANT.KEY_REVOKE(appId, keyId), { reason });
  },

  // Tenant Webhooks
  async listTenantWebhooks(appId: string): Promise<DeveloperWebhookListResponse> {
    return apiClient.get<DeveloperWebhookListResponse>(ENDPOINTS.DEVELOPER.TENANT.WEBHOOKS(appId));
  },

  async createTenantWebhook(
    appId: string,
    data: { target_url: string; event_topics: string[] }
  ): Promise<DeveloperWebhookSubscription> {
    return apiClient.post<DeveloperWebhookSubscription>(ENDPOINTS.DEVELOPER.TENANT.WEBHOOKS(appId), data);
  },

  async updateTenantWebhook(
    id: string,
    data: { target_url?: string; event_topics?: string[] }
  ): Promise<DeveloperWebhookSubscription> {
    return apiClient.patch<DeveloperWebhookSubscription>(ENDPOINTS.DEVELOPER.TENANT.WEBHOOK_DETAIL(id), data);
  },

  async suspendTenantWebhook(id: string, reason?: string): Promise<DeveloperWebhookSubscription> {
    return apiClient.post<DeveloperWebhookSubscription>(ENDPOINTS.DEVELOPER.TENANT.WEBHOOK_SUSPEND(id), { reason });
  },

  async reactivateTenantWebhook(id: string): Promise<DeveloperWebhookSubscription> {
    return apiClient.post<DeveloperWebhookSubscription>(ENDPOINTS.DEVELOPER.TENANT.WEBHOOK_REACTIVATE(id), {});
  },

  async revokeTenantWebhook(id: string, reason?: string): Promise<DeveloperWebhookSubscription> {
    return apiClient.post<DeveloperWebhookSubscription>(ENDPOINTS.DEVELOPER.TENANT.WEBHOOK_REVOKE(id), { reason });
  },

  async rotateTenantWebhookSecret(id: string): Promise<DeveloperWebhookSubscription> {
    return apiClient.post<DeveloperWebhookSubscription>(ENDPOINTS.DEVELOPER.TENANT.WEBHOOK_ROTATE_SECRET(id), {});
  },

  async listTenantDeliveries(id: string): Promise<DeveloperDeliveryListResponse> {
    return apiClient.get<DeveloperDeliveryListResponse>(ENDPOINTS.DEVELOPER.TENANT.WEBHOOK_DELIVERIES(id));
  },

  async replayTenantDelivery(deliveryId: string): Promise<DeveloperWebhookDelivery> {
    return apiClient.post<DeveloperWebhookDelivery>(ENDPOINTS.DEVELOPER.TENANT.DELIVERY_REPLAY(deliveryId), {});
  },

  // Platform Owner methods
  async listOwnerApps(params?: {
    search?: string;
    organization_id?: string;
    status?: string;
  }): Promise<DeveloperAppListResponse> {
    const query = new URLSearchParams();
    if (params?.search) query.set("search", params.search);
    if (params?.organization_id) query.set("organization_id", params.organization_id);
    if (params?.status) query.set("status", params.status);
    const qs = query.toString();
    const url = qs ? `${ENDPOINTS.DEVELOPER.OWNER.APPS}?${qs}` : ENDPOINTS.DEVELOPER.OWNER.APPS;
    return apiClient.get<DeveloperAppListResponse>(url);
  },

  async getOwnerApp(id: string): Promise<DeveloperApplication> {
    return apiClient.get<DeveloperApplication>(ENDPOINTS.DEVELOPER.OWNER.APP_DETAIL(id));
  },

  async suspendOwnerApp(id: string, reason?: string): Promise<DeveloperApplication> {
    return apiClient.post<DeveloperApplication>(ENDPOINTS.DEVELOPER.OWNER.APP_SUSPEND(id), { reason });
  },

  async revokeOwnerApp(id: string, reason?: string): Promise<DeveloperApplication> {
    return apiClient.post<DeveloperApplication>(ENDPOINTS.DEVELOPER.OWNER.APP_REVOKE(id), { reason });
  },

  async listOwnerKeys(appId: string): Promise<DeveloperKeyListResponse> {
    return apiClient.get<DeveloperKeyListResponse>(ENDPOINTS.DEVELOPER.OWNER.KEYS(appId));
  },

  async revokeOwnerKey(appId: string, keyId: string, reason?: string): Promise<DeveloperApiKey> {
    return apiClient.post<DeveloperApiKey>(ENDPOINTS.DEVELOPER.OWNER.KEY_REVOKE(appId, keyId), { reason });
  },

  // Platform Owner Webhooks
  async listOwnerWebhooks(appId?: string): Promise<DeveloperWebhookListResponse> {
    const url = appId
      ? `${ENDPOINTS.DEVELOPER.OWNER.WEBHOOKS}?application_id=${encodeURIComponent(appId)}`
      : ENDPOINTS.DEVELOPER.OWNER.WEBHOOKS;
    return apiClient.get<DeveloperWebhookListResponse>(url);
  },

  async suspendOwnerWebhook(id: string, reason?: string): Promise<DeveloperWebhookSubscription> {
    return apiClient.post<DeveloperWebhookSubscription>(ENDPOINTS.DEVELOPER.OWNER.WEBHOOK_SUSPEND(id), { reason });
  },

  async revokeOwnerWebhook(id: string, reason?: string): Promise<DeveloperWebhookSubscription> {
    return apiClient.post<DeveloperWebhookSubscription>(ENDPOINTS.DEVELOPER.OWNER.WEBHOOK_REVOKE(id), { reason });
  },

  async listOwnerDeliveries(id: string): Promise<DeveloperDeliveryListResponse> {
    return apiClient.get<DeveloperDeliveryListResponse>(ENDPOINTS.DEVELOPER.OWNER.WEBHOOK_DELIVERIES(id));
  },
};
