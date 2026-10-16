/**
 * Product Catalog Hierarchy Domain API.
 *
 * Exclusively consumes the centralized apiClient to communicate with versioned
 * catalog endpoints for ProductModules, ProductFeatures, and ProductCapabilities.
 * Enforces strict runtime payload allowlisting and prohibited-field stripping.
 */

import { apiClient } from "./client.ts";
import { ENDPOINTS } from "./endpoints.ts";
import type {
  CatalogPatchPayload,
  CreateProductCapabilityPayload,
  CreateProductFeaturePayload,
  CreateProductModulePayload,
  ProductCapabilityDetail,
  ProductCapabilityListParams,
  ProductCapabilityListResponse,
  ProductFeatureDetail,
  ProductFeatureListParams,
  ProductFeatureListResponse,
  ProductModuleDetail,
  ProductModuleListParams,
  ProductModuleListResponse,
} from "./types.ts";

/**
 * Runtime sanitization for Catalog PATCH payloads.
 * Strictly guarantees that retirement payloads contain only `{ status: "retired" }`,
 * and that metadata/activation payloads never contain parent IDs, server-owned audit fields,
 * or invalid `status: "draft"`.
 */
function sanitizePatchPayload(payload: CatalogPatchPayload): Record<string, unknown> {
  if (payload.status === "retired") {
    // Retirement must be status-only: no other keys are permitted
    return { status: "retired" };
  }

  const clean: Record<string, unknown> = {};

  if (payload.status === "active") {
    clean.status = "active";
  }

  if (typeof payload.name === "string") {
    clean.name = payload.name.trim();
  }

  if (typeof payload.description === "string") {
    clean.description = payload.description.trim();
  }

  if (typeof payload.display_order === "number" && !isNaN(payload.display_order)) {
    clean.display_order = Math.max(0, Math.floor(payload.display_order));
  }

  if (typeof payload.code === "string" && payload.code.trim()) {
    clean.code = payload.code.trim().toLowerCase();
  }

  return clean;
}

/**
 * Runtime sanitization for Create ProductModule payloads.
 */
function sanitizeCreateModulePayload(payload: CreateProductModulePayload): Record<string, unknown> {
  const clean: Record<string, unknown> = {
    product_id: payload.product_id,
    code: payload.code.trim().toLowerCase(),
    name: payload.name.trim(),
  };

  if (payload.description !== undefined) {
    clean.description = payload.description.trim();
  }

  if (payload.display_order !== undefined && !isNaN(payload.display_order)) {
    clean.display_order = Math.max(0, Math.floor(payload.display_order));
  }

  return clean;
}

/**
 * Runtime sanitization for Create ProductFeature payloads.
 */
function sanitizeCreateFeaturePayload(payload: CreateProductFeaturePayload): Record<string, unknown> {
  const clean: Record<string, unknown> = {
    module_id: payload.module_id,
    code: payload.code.trim().toLowerCase(),
    name: payload.name.trim(),
  };

  if (payload.description !== undefined) {
    clean.description = payload.description.trim();
  }

  if (payload.display_order !== undefined && !isNaN(payload.display_order)) {
    clean.display_order = Math.max(0, Math.floor(payload.display_order));
  }

  return clean;
}

/**
 * Runtime sanitization for Create ProductCapability payloads.
 */
function sanitizeCreateCapabilityPayload(payload: CreateProductCapabilityPayload): Record<string, unknown> {
  const clean: Record<string, unknown> = {
    feature_id: payload.feature_id,
    code: payload.code.trim().toLowerCase(),
    name: payload.name.trim(),
  };

  if (payload.description !== undefined) {
    clean.description = payload.description.trim();
  }

  if (payload.display_order !== undefined && !isNaN(payload.display_order)) {
    clean.display_order = Math.max(0, Math.floor(payload.display_order));
  }

  return clean;
}

export const catalogApi = {
  /**
   * Product Module API Methods.
   */
  modules: {
    async list(params: ProductModuleListParams, signal?: AbortSignal): Promise<ProductModuleListResponse> {
      return apiClient.get<ProductModuleListResponse>(ENDPOINTS.PRODUCT_MODULES.LIST, {
        params,
        signal,
      });
    },

    async get(id: string, signal?: AbortSignal): Promise<ProductModuleDetail> {
      return apiClient.get<ProductModuleDetail>(ENDPOINTS.PRODUCT_MODULES.DETAIL(id), {
        signal,
      });
    },

    async create(payload: CreateProductModulePayload): Promise<ProductModuleDetail> {
      const sanitized = sanitizeCreateModulePayload(payload);
      return apiClient.post<ProductModuleDetail>(ENDPOINTS.PRODUCT_MODULES.LIST, sanitized);
    },

    async patch(id: string, payload: CatalogPatchPayload): Promise<ProductModuleDetail> {
      const sanitized = sanitizePatchPayload(payload);
      return apiClient.patch<ProductModuleDetail>(ENDPOINTS.PRODUCT_MODULES.DETAIL(id), sanitized);
    },
  },

  /**
   * Product Feature API Methods.
   */
  features: {
    async list(params: ProductFeatureListParams, signal?: AbortSignal): Promise<ProductFeatureListResponse> {
      return apiClient.get<ProductFeatureListResponse>(ENDPOINTS.PRODUCT_FEATURES.LIST, {
        params,
        signal,
      });
    },

    async get(id: string, signal?: AbortSignal): Promise<ProductFeatureDetail> {
      return apiClient.get<ProductFeatureDetail>(ENDPOINTS.PRODUCT_FEATURES.DETAIL(id), {
        signal,
      });
    },

    async create(payload: CreateProductFeaturePayload): Promise<ProductFeatureDetail> {
      const sanitized = sanitizeCreateFeaturePayload(payload);
      return apiClient.post<ProductFeatureDetail>(ENDPOINTS.PRODUCT_FEATURES.LIST, sanitized);
    },

    async patch(id: string, payload: CatalogPatchPayload): Promise<ProductFeatureDetail> {
      const sanitized = sanitizePatchPayload(payload);
      return apiClient.patch<ProductFeatureDetail>(ENDPOINTS.PRODUCT_FEATURES.DETAIL(id), sanitized);
    },
  },

  /**
   * Product Capability API Methods.
   */
  capabilities: {
    async list(params: ProductCapabilityListParams, signal?: AbortSignal): Promise<ProductCapabilityListResponse> {
      return apiClient.get<ProductCapabilityListResponse>(ENDPOINTS.PRODUCT_CAPABILITIES.LIST, {
        params,
        signal,
      });
    },

    async get(id: string, signal?: AbortSignal): Promise<ProductCapabilityDetail> {
      return apiClient.get<ProductCapabilityDetail>(ENDPOINTS.PRODUCT_CAPABILITIES.DETAIL(id), {
        signal,
      });
    },

    async create(payload: CreateProductCapabilityPayload): Promise<ProductCapabilityDetail> {
      const sanitized = sanitizeCreateCapabilityPayload(payload);
      return apiClient.post<ProductCapabilityDetail>(ENDPOINTS.PRODUCT_CAPABILITIES.LIST, sanitized);
    },

    async patch(id: string, payload: CatalogPatchPayload): Promise<ProductCapabilityDetail> {
      const sanitized = sanitizePatchPayload(payload);
      return apiClient.patch<ProductCapabilityDetail>(ENDPOINTS.PRODUCT_CAPABILITIES.DETAIL(id), sanitized);
    },
  },
};

/**
 * Robust, user-friendly error message extractor for catalog operations.
 * Handles DRF status arrays, non_field_errors, detail, message, and nested objects.
 * Strictly guarantees [object Object] is never returned.
 */
export function extractCatalogErrorMessage(err: unknown, fallback: string): string {
  if (!err || typeof err !== "object") return fallback;
  const apiErr = err as { status?: number; data?: Record<string, unknown>; message?: string };
  if (apiErr.data && typeof apiErr.data === "object") {
    if (Array.isArray(apiErr.data.status)) {
      return apiErr.data.status.join(" ");
    }
    if (Array.isArray(apiErr.data.non_field_errors)) {
      return apiErr.data.non_field_errors.join(" ");
    }
    if (typeof apiErr.data.detail === "string") {
      return apiErr.data.detail;
    }
    if (typeof apiErr.data.message === "string") {
      return apiErr.data.message;
    }
    try {
      return JSON.stringify(apiErr.data);
    } catch {
      return fallback;
    }
  }
  if (apiErr.message && typeof apiErr.message === "string") {
    return apiErr.message;
  }
  return fallback;
}
