/**
 * Centralized Environment Configuration & Validation.
 *
 * Enforces strict environment variable presence without fallbacks or URL guessing.
 */

export interface AppConfig {
  readonly apiBaseUrl: string;
  readonly csrfCookieName: string;
}

export function getApiBaseUrl(): string {
  const apiBaseUrl = import.meta.env.VITE_API_BASE_URL;

  if (!apiBaseUrl || typeof apiBaseUrl !== "string" || apiBaseUrl.trim() === "") {
    throw new Error(
      "Configuration Error: VITE_API_BASE_URL environment variable is mandatory and missing. " +
        "Please define VITE_API_BASE_URL in your frontend environment configuration."
    );
  }

  return apiBaseUrl.trim();
}

export function getCsrfCookieName(): string {
  const cookieName = import.meta.env.VITE_CSRF_COOKIE_NAME;

  if (!cookieName || typeof cookieName !== "string" || cookieName.trim() === "") {
    throw new Error(
      "Configuration Error: VITE_CSRF_COOKIE_NAME environment variable is mandatory and missing. " +
        "Please define VITE_CSRF_COOKIE_NAME in your frontend environment configuration."
    );
  }

  return cookieName.trim();
}

export const env: AppConfig = {
  get apiBaseUrl(): string {
    return getApiBaseUrl();
  },
  get csrfCookieName(): string {
    return getCsrfCookieName();
  },
};
