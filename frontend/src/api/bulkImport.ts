/**
 * Bulk Import Domain API Client (Phase 3D).
 *
 * Exclusively consumes centralized apiClient and ENDPOINTS.
 */

import { apiClient } from "./client.ts";
import { ENDPOINTS } from "./endpoints.ts";
import type {
  BulkImportJob,
  BulkImportReconciliationReport,
  BulkImportRowListResponse,
  CreateBulkImportJobPayload,
} from "./types.ts";

export const bulkImportApi = {
  /**
   * Upload and stage a new bulk import job.
   */
  async createJob(payload: CreateBulkImportJobPayload): Promise<BulkImportJob> {
    return apiClient.post<BulkImportJob>(ENDPOINTS.BULK_IMPORT.JOBS, payload);
  },

  /**
   * Retrieve job status and counters.
   */
  async getJob(id: string, signal?: AbortSignal): Promise<BulkImportJob> {
    return apiClient.get<BulkImportJob>(ENDPOINTS.BULK_IMPORT.JOB_DETAIL(id), { signal });
  },

  /**
   * List staged rows for a job.
   */
  async listRows(
    id: string,
    params?: { validation_state?: string; page?: number; page_size?: number },
    signal?: AbortSignal
  ): Promise<BulkImportRowListResponse> {
    return apiClient.get<BulkImportRowListResponse>(ENDPOINTS.BULK_IMPORT.JOB_ROWS(id), {
      params,
      signal,
    });
  },

  /**
   * Commit all valid rows in a job.
   */
  async commitJob(id: string): Promise<BulkImportJob> {
    return apiClient.post<BulkImportJob>(ENDPOINTS.BULK_IMPORT.COMMIT(id), {});
  },

  /**
   * Retry failed rows in an import job.
   */
  async retryJob(id: string): Promise<BulkImportJob> {
    return apiClient.post<BulkImportJob>(ENDPOINTS.BULK_IMPORT.RETRY(id), {});
  },

  /**
   * Retrieve idempotent reconciliation report for a job (Phase 3E).
   */
  async getReconciliation(id: string, signal?: AbortSignal): Promise<BulkImportReconciliationReport> {
    return apiClient.get<BulkImportReconciliationReport>(ENDPOINTS.BULK_IMPORT.RECONCILIATION(id), { signal });
  },

  /**
   * Download CSV error report for a job.
   */
  async getErrorReport(id: string): Promise<Blob> {
    return apiClient.get<Blob>(ENDPOINTS.BULK_IMPORT.ERROR_REPORT(id), { responseType: "blob" as any });
  },
};


