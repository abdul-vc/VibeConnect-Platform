/**
 * Billing & Invoices API Client (Phase 4D).
 * Exclusively consumes centralized apiClient and ENDPOINTS.
 */

import { apiClient } from "./client.ts";
import { ENDPOINTS } from "./endpoints.ts";

export interface BillingAccount {
  id: string;
  organization: string;
  organization_name?: string;
  legal_name: string;
  tax_id: string;
  billing_email: string;
  status: string;
  currency: string;
  address_line1?: string;
  city?: string;
  state?: string;
  postal_code?: string;
  country?: string;
  created_at: string;
  updated_at: string;
}

export interface InvoiceLine {
  id: string;
  description: string;
  quantity: number;
  unit_price: string;
  tax_amount: string;
  total_amount: string;
}

export interface Invoice {
  id: string;
  organization: string;
  organization_name?: string;
  invoice_number: string;
  currency: string;
  subtotal: string;
  tax_total: string;
  total: string;
  status: "draft" | "issued" | "paid" | "overdue" | "cancelled";
  due_date: string;
  issued_at: string | null;
  paid_at: string | null;
  lines: InvoiceLine[];
  created_at: string;
  updated_at: string;
}

export interface Payment {
  id: string;
  invoice: string;
  processor_ref: string;
  amount: string;
  currency: string;
  status: string;
  idempotency_key: string;
  created_at: string;
}

export interface InvoiceListResponse {
  count: number;
  results: Invoice[];
  next?: string | null;
  previous?: string | null;
}

export interface BillingAccountListResponse {
  count: number;
  results: BillingAccount[];
  next?: string | null;
  previous?: string | null;
}

export const billingApi = {
  getOwnerBillingAccounts: async (page = 1, pageSize = 20): Promise<BillingAccountListResponse> => {
    const query = new URLSearchParams({
      page: String(page),
      page_size: String(pageSize),
    }).toString();
    return apiClient.get<BillingAccountListResponse>(`${ENDPOINTS.BILLING.ACCOUNTS}?${query}`);
  },

  getOwnerInvoices: async (page = 1, pageSize = 20): Promise<InvoiceListResponse> => {
    const query = new URLSearchParams({
      page: String(page),
      page_size: String(pageSize),
    }).toString();
    return apiClient.get<InvoiceListResponse>(`${ENDPOINTS.BILLING.INVOICES}?${query}`);
  },

  getTenantInvoices: async (): Promise<InvoiceListResponse> => {
    return apiClient.get<InvoiceListResponse>(ENDPOINTS.BILLING.TENANT_INVOICES);
  },

  getTenantBillingAccount: async (): Promise<BillingAccount> => {
    return apiClient.get<BillingAccount>(ENDPOINTS.BILLING.TENANT_ACCOUNT);
  },

  recordPayment: async (payload: {
    invoice_id: string;
    amount: string;
    currency: string;
    idempotency_key: string;
    processor_ref?: string;
  }): Promise<Payment> => {
    return apiClient.post<Payment>(ENDPOINTS.BILLING.PAYMENTS, payload);
  },
};
