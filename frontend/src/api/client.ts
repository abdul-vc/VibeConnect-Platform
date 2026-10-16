/**
 * Centralized API Client.
 *
 * Exclusively responsible for all outgoing HTTP communications in the frontend.
 * Configured with cross-origin credentials, strict CSRF handling, and zero URL fallbacks.
 */

import axios, { type AxiosInstance, type AxiosRequestConfig, type AxiosResponse, AxiosError } from "axios";
import { getApiBaseUrl, getCsrfCookieName } from "../config/env.ts";
import { ENDPOINTS } from "./endpoints.ts";
import type {
  AuthDetailResponse,
  AuthenticatedUser,
  ContextSelectionPayload,
  ContextSelectionResponse,
  HealthResponse,
  LoginPayload,
} from "./types.ts";

export class ApiError extends Error {
  readonly status?: number;
  readonly data?: unknown;

  constructor(message: string, status?: number, data?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.data = data;
  }
}

let axiosInstance: AxiosInstance | null = null;
let activeImpersonationSessionId: string | null = null;
let onImpersonationExpiredHandler: (() => void) | null = null;

export function setActiveImpersonationSessionId(id: string | null) {
  activeImpersonationSessionId = id;
}

export function getActiveImpersonationSessionId(): string | null {
  return activeImpersonationSessionId;
}

export function setOnImpersonationExpired(handler: (() => void) | null) {
  onImpersonationExpiredHandler = handler;
}

function getClient(): AxiosInstance {
  if (!axiosInstance) {
    const baseURL = getApiBaseUrl();
    const csrfCookieName = getCsrfCookieName();

    axiosInstance = axios.create({
      baseURL,
      withCredentials: true,
      xsrfCookieName: csrfCookieName,
      xsrfHeaderName: "X-CSRFToken",
      withXSRFToken: true,
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      timeout: 10000,
    });

    axiosInstance.interceptors.request.use((config) => {
      if (activeImpersonationSessionId) {
        config.headers.set("X-VibeConnect-Impersonation-Session", activeImpersonationSessionId);
      }
      return config;
    });

    axiosInstance.interceptors.response.use(
      (response: AxiosResponse) => response,
      (error: unknown) => {
        if (error instanceof AxiosError) {
          const status = error.response?.status;
          const data = error.response?.data;
          const code = typeof data === "object" && data !== null ? (data as Record<string, unknown>).code : undefined;
          if (
            status === 403 &&
            (code === "IMPERSONATION_SESSION_EXPIRED" ||
              code === "IMPERSONATION_SESSION_NOT_FOUND" ||
              code === "IMPERSONATION_SESSION_INACTIVE" ||
              code === "TARGET_USER_INACTIVE" ||
              code === "TARGET_ORG_INACTIVE" ||
              code === "TARGET_MEMBERSHIP_INACTIVE")
          ) {
            setActiveImpersonationSessionId(null);
            if (onImpersonationExpiredHandler) {
              onImpersonationExpiredHandler();
            }
          }

          const message =
            data?.detail ||
            data?.message ||
            (typeof data === "object" && data !== null ? JSON.stringify(data) : undefined) ||
            error.message ||
            "An unexpected network error occurred.";
          return Promise.reject(new ApiError(message, status, data));
        }
        return Promise.reject(new ApiError("An unexpected network error occurred."));
      }
    );
  }
  return axiosInstance;
}


export const apiClient = {
  /**
   * Generic GET request method.
   */
  async get<T>(url: string, config?: AxiosRequestConfig): Promise<T> {
    const client = getClient();
    const response = await client.get<T>(url, config);
    return response.data;
  },

  /**
   * Generic POST request method.
   */
  async post<T>(url: string, data?: unknown, config?: AxiosRequestConfig): Promise<T> {
    const client = getClient();
    const response = await client.post<T>(url, data, config);
    return response.data;
  },

  /**
   * Generic PATCH request method.
   */
  async patch<T>(url: string, data?: unknown, config?: AxiosRequestConfig): Promise<T> {
    const client = getClient();
    const response = await client.patch<T>(url, data, config);
    return response.data;
  },

  /**
   * Generic DELETE request method.
   */
  async delete<T = void>(url: string, config?: AxiosRequestConfig): Promise<T> {
    const client = getClient();
    const response = await client.delete<T>(url, config);
    return response.data;
  },

  /**
   * Health check API.
   */
  async checkHealth(): Promise<HealthResponse> {
    return this.get<HealthResponse>(ENDPOINTS.HEALTH);
  },

  /**
   * Authentication methods.
   */
  auth: {
    async initCsrf(): Promise<AuthDetailResponse> {
      return apiClient.get<AuthDetailResponse>(ENDPOINTS.AUTH.CSRF);
    },

    async login(payload: LoginPayload): Promise<AuthenticatedUser> {
      return apiClient.post<AuthenticatedUser>(ENDPOINTS.AUTH.LOGIN, payload);
    },

    async getCurrentUser(): Promise<AuthenticatedUser> {
      return apiClient.get<AuthenticatedUser>(ENDPOINTS.AUTH.ME);
    },

    async logout(): Promise<AuthDetailResponse> {
      return apiClient.post<AuthDetailResponse>(ENDPOINTS.AUTH.LOGOUT, {});
    },

    async getContext(): Promise<ContextSelectionResponse> {
      return apiClient.get<ContextSelectionResponse>(ENDPOINTS.AUTH.CONTEXT);
    },

    async selectContext(payload: ContextSelectionPayload): Promise<ContextSelectionResponse> {
      return apiClient.post<ContextSelectionResponse>(ENDPOINTS.AUTH.CONTEXT, payload);
    },
  },
};
