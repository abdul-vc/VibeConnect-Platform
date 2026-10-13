/**
 * Product Registry Domain API.
 *
 * Exclusively consumes the centralized apiClient to communicate with versioned product endpoints.
 */

import { apiClient } from "./client.ts";
import { ENDPOINTS } from "./endpoints.ts";
import type {
  CreateProductPayload,
  ProductDetail,
  ProductListResponse,
  UpdateProductPayload,
} from "./types.ts";

export interface ProductListParams {
  readonly page?: number;
  readonly page_size?: number;
  readonly search?: string;
  readonly status?: string;
  readonly ordering?: string;
}

export const productsApi = {
  /**
   * List products with server-side pagination, search, and filtering.
   */
  async list(params?: ProductListParams, signal?: AbortSignal): Promise<ProductListResponse> {
    return apiClient.get<ProductListResponse>(ENDPOINTS.PRODUCTS.LIST, {
      params,
      signal,
    });
  },

  /**
   * Retrieve single product detail including minimal audit users.
   */
  async get(id: string): Promise<ProductDetail> {
    return apiClient.get<ProductDetail>(ENDPOINTS.PRODUCTS.DETAIL(id));
  },

  /**
   * Create a new product starting in Draft lifecycle status.
   */
  async create(payload: CreateProductPayload): Promise<ProductDetail> {
    return apiClient.post<ProductDetail>(ENDPOINTS.PRODUCTS.LIST, payload);
  },

  /**
   * Partially update editable product fields (name, description, status).
   */
  async update(id: string, payload: UpdateProductPayload): Promise<ProductDetail> {
    return apiClient.patch<ProductDetail>(ENDPOINTS.PRODUCTS.DETAIL(id), payload);
  },
};
