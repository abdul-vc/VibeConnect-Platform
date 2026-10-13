/**
 * Subscription Management Domain API.
 *
 * Exclusively consumes the centralized apiClient to communicate with versioned subscription endpoints.
 */

import { apiClient } from "./client.ts";
import { ENDPOINTS } from "./endpoints.ts";
import type {
  CancelSubscriptionPayload,
  ChangePlanPayload,
  ConvertTrialPayload,
  CreateSubscriptionPayload,
  ReactivateSubscriptionPayload,
  ReconcileSubscriptionPayload,
  ReconcileSubscriptionResponse,
  StartTrialPayload,
  SubscriptionDetail,
  SubscriptionEntitlementsResponse,
  SubscriptionListParams,
  SubscriptionListResponse,
  SuspendSubscriptionPayload,
} from "./types.ts";

export const subscriptionsApi = {
  /**
   * List subscriptions with server-side pagination, search, status, and ordering.
   */
  async list(
    params?: SubscriptionListParams,
    signal?: AbortSignal
  ): Promise<SubscriptionListResponse> {
    return apiClient.get<SubscriptionListResponse>(ENDPOINTS.SUBSCRIPTIONS.LIST, {
      params,
      signal,
    });
  },

  /**
   * Retrieve a single subscription by ID.
   */
  async get(id: string, signal?: AbortSignal): Promise<SubscriptionDetail> {
    return apiClient.get<SubscriptionDetail>(ENDPOINTS.SUBSCRIPTIONS.DETAIL(id), {
      signal,
    });
  },

  /**
   * Create a direct active subscription for an organization.
   */
  async create(payload: CreateSubscriptionPayload): Promise<SubscriptionDetail> {
    return apiClient.post<SubscriptionDetail>(ENDPOINTS.SUBSCRIPTIONS.LIST, payload);
  },

  /**
   * Start a trial subscription for an organization.
   */
  async startTrial(payload: StartTrialPayload): Promise<SubscriptionDetail> {
    return apiClient.post<SubscriptionDetail>(ENDPOINTS.SUBSCRIPTIONS.TRIAL, payload);
  },

  /**
   * Convert an active trial subscription into a standard paid active subscription.
   */
  async convertTrial(
    id: string,
    payload?: ConvertTrialPayload
  ): Promise<SubscriptionDetail> {
    return apiClient.post<SubscriptionDetail>(
      ENDPOINTS.SUBSCRIPTIONS.CONVERT_TRIAL(id),
      payload ?? {}
    );
  },

  /**
   * Change plan for an active/trialing/suspended subscription with immediate successor cutover.
   */
  async changePlan(
    id: string,
    payload: ChangePlanPayload
  ): Promise<SubscriptionDetail> {
    return apiClient.post<SubscriptionDetail>(
      ENDPOINTS.SUBSCRIPTIONS.CHANGE_PLAN(id),
      payload
    );
  },

  /**
   * Suspend an active subscription.
   */
  async suspend(
    id: string,
    payload?: SuspendSubscriptionPayload
  ): Promise<SubscriptionDetail> {
    return apiClient.post<SubscriptionDetail>(
      ENDPOINTS.SUBSCRIPTIONS.SUSPEND(id),
      payload ?? {}
    );
  },

  /**
   * Reactivate a suspended subscription.
   */
  async reactivate(
    id: string,
    payload?: ReactivateSubscriptionPayload
  ): Promise<SubscriptionDetail> {
    return apiClient.post<SubscriptionDetail>(
      ENDPOINTS.SUBSCRIPTIONS.REACTIVATE(id),
      payload ?? {}
    );
  },

  /**
   * Cancel an active, trialing, or suspended subscription.
   */
  async cancel(
    id: string,
    payload?: CancelSubscriptionPayload
  ): Promise<SubscriptionDetail> {
    return apiClient.post<SubscriptionDetail>(
      ENDPOINTS.SUBSCRIPTIONS.CANCEL(id),
      payload ?? {}
    );
  },

  /**
   * Reconcile subscription entitlement snapshots idempotently against PlanVersion blueprint.
   */
  async reconcile(
    id: string,
    payload?: ReconcileSubscriptionPayload
  ): Promise<ReconcileSubscriptionResponse> {
    return apiClient.post<ReconcileSubscriptionResponse>(
      ENDPOINTS.SUBSCRIPTIONS.RECONCILE(id),
      payload ?? {}
    );
  },

  /**
   * Retrieve entitlement snapshot hierarchy for a subscription.
   */
  async getEntitlements(
    id: string,
    signal?: AbortSignal
  ): Promise<SubscriptionEntitlementsResponse> {
    return apiClient.get<SubscriptionEntitlementsResponse>(
      ENDPOINTS.SUBSCRIPTIONS.ENTITLEMENTS(id),
      { signal }
    );
  },
};
