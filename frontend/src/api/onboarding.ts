/**
 * Tenant Onboarding Domain API Client (Phase 3B).
 *
 * Exclusively consumes the centralized apiClient.
 */

import { apiClient } from "./client.ts";
import { ENDPOINTS } from "./endpoints.ts";
import type {
  OnboardingOptionsResponse,
  TenantOnboardingCase,
  TransitionStepPayload,
} from "./types.ts";

export const onboardingApi = {
  /**
   * Initialize a new onboarding case.
   */
  async createCase(): Promise<TenantOnboardingCase> {
    return apiClient.post<TenantOnboardingCase>(ENDPOINTS.ONBOARDING.CASES, {});
  },

  /**
   * Retrieve existing onboarding case state (resume progress).
   */
  async getCase(id: string, signal?: AbortSignal): Promise<TenantOnboardingCase> {
    return apiClient.get<TenantOnboardingCase>(ENDPOINTS.ONBOARDING.CASE_DETAIL(id), { signal });
  },

  /**
   * Transition to next step with partial payload and validation.
   */
  async transitionStep(id: string, payload: TransitionStepPayload): Promise<TenantOnboardingCase> {
    return apiClient.patch<TenantOnboardingCase>(ENDPOINTS.ONBOARDING.STEP(id), payload);
  },

  /**
   * Fetch available products, modules, features, and tenant console modules for onboarding configuration.
   */
  async getOptions(signal?: AbortSignal): Promise<OnboardingOptionsResponse> {
    return apiClient.get<OnboardingOptionsResponse>(ENDPOINTS.ONBOARDING.OPTIONS, { signal });
  },
};
