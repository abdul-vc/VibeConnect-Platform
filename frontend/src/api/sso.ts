/**
 * SSO API Client (Phase 5C).
 *
 * Provides typed methods for launching SSO, validating codes,
 * and checking pilot status. Routes exclusively through apiClient.
 */

import { apiClient } from "./client.ts";
import { ENDPOINTS } from "./endpoints.ts";

export interface SsoLaunchPayload {
  product_id: string;
  organization_id?: string;
  redirect_uri?: string;
  code_challenge?: string;
  code_challenge_method?: "S256" | "plain";
  state?: string;
}

export interface SsoLaunchResponse {
  redirect_url: string;
  expires_at: string;
}

export interface SsoValidatePayload {
  code: string;
  client_identifier?: string;
  code_verifier?: string;
  expected_org_id?: string;
  expected_product_id?: string;
}

export interface SsoValidateResponse {
  user: {
    id: string;
    email: string;
    full_name: string;
  };
  organization: {
    id: string;
    code: string;
    name: string;
  };
  product: {
    id: string;
    code: string;
    name: string;
  };
  assignment_id: string;
  audience: string;
}

export interface SsoPilotStatusResponse {
  sso_enabled: boolean;
  client_identifier: string | null;
}

export const ssoApi = {
  launch: async (payload: SsoLaunchPayload): Promise<SsoLaunchResponse> => {
    return apiClient.post<SsoLaunchResponse>(ENDPOINTS.SSO.LAUNCH, payload);
  },

  validate: async (payload: SsoValidatePayload): Promise<SsoValidateResponse> => {
    return apiClient.post<SsoValidateResponse>(ENDPOINTS.SSO.VALIDATE, payload);
  },

  getPilotStatus: async (productId: string, organizationId?: string): Promise<SsoPilotStatusResponse> => {
    return apiClient.get<SsoPilotStatusResponse>(ENDPOINTS.SSO.PILOT_STATUS, {
      params: {
        product_id: productId,
        ...(organizationId ? { organization_id: organizationId } : {}),
      },
    });
  },
};
