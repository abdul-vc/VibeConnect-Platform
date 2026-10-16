/**
 * Platform Owner Billing & Invoices Page (Phase 4D).
 *
 * Route: /billing
 * Context Guard: platform_owner
 */

import React, { useState, useEffect, useCallback } from "react";
import { AppShell } from "../../components/AppShell.tsx";
import {
  billingApi,
  type Invoice,
  type BillingAccount,
} from "../../api/billing.ts";
import { LoadingSpinner } from "../../components/LoadingSpinner.tsx";

export const BillingPage: React.FC = () => {
  const [activeTab, setActiveTab] = useState<"invoices" | "accounts">("invoices");

  // Invoices state
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [invoiceCount, setInvoiceCount] = useState<number>(0);
  const [invoicePage, setInvoicePage] = useState<number>(1);

  // Accounts state
  const [accounts, setAccounts] = useState<BillingAccount[]>([]);
  const [accountCount, setAccountCount] = useState<number>(0);
  const [accountPage, setAccountPage] = useState<number>(1);

  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const pageSize = 15;

  const fetchInvoices = useCallback(async (page: number) => {
    setIsLoading(true);
    setErrorMessage(null);
    try {
      const res = await billingApi.getOwnerInvoices(page, pageSize);
      setInvoices(res.results || []);
      setInvoiceCount(res.count || 0);
    } catch (err: unknown) {
      const msg = err && typeof err === "object" && "message" in err
        ? String((err as { message: string }).message)
        : "Failed to load invoices.";
      setErrorMessage(msg);
    } finally {
      setIsLoading(false);
    }
  }, [pageSize]);

  const fetchAccounts = useCallback(async (page: number) => {
    setIsLoading(true);
    setErrorMessage(null);
    try {
      const res = await billingApi.getOwnerBillingAccounts(page, pageSize);
      setAccounts(res.results || []);
      setAccountCount(res.count || 0);
    } catch (err: unknown) {
      const msg = err && typeof err === "object" && "message" in err
        ? String((err as { message: string }).message)
        : "Failed to load billing accounts.";
      setErrorMessage(msg);
    } finally {
      setIsLoading(false);
    }
  }, [pageSize]);

  useEffect(() => {
    if (activeTab === "invoices") {
      void fetchInvoices(invoicePage);
    } else {
      void fetchAccounts(accountPage);
    }
  }, [activeTab, invoicePage, accountPage, fetchInvoices, fetchAccounts]);

  const getStatusBadgeStyle = (status: string) => {
    switch (status) {
      case "paid":
        return {
          bg: "var(--status-success-bg)",
          color: "var(--status-success)",
          border: "var(--status-success-border)",
        };
      case "issued":
        return {
          bg: "rgba(99, 102, 241, 0.1)",
          color: "rgb(99, 102, 241)",
          border: "rgba(99, 102, 241, 0.3)",
        };
      case "overdue":
        return {
          bg: "var(--status-error-bg)",
          color: "var(--status-error)",
          border: "var(--status-error-border)",
        };
      case "draft":
        return {
          bg: "rgba(156, 163, 175, 0.1)",
          color: "rgb(156, 163, 175)",
          border: "rgba(156, 163, 175, 0.3)",
        };
      default:
        return {
          bg: "var(--glass-surface-elevated)",
          color: "var(--text-secondary)",
          border: "var(--border-glass)",
        };
    }
  };

  return (
    <AppShell>
      <div style={{ padding: "2rem", maxWidth: "1400px", margin: "0 auto" }}>
        {/* Header */}
        <div style={{ marginBottom: "2rem" }}>
          <h1
            className="heading-hero"
            style={{ fontSize: "1.75rem", margin: "0 0 0.5rem 0", color: "var(--text-primary)" }}
          >
            Billing & Invoices
          </h1>
          <p style={{ margin: 0, color: "var(--text-secondary)", fontSize: "0.9375rem" }}>
            Cross-tenant billing accounts, issued invoices, and payment lifecycle tracking.
          </p>
        </div>

        {/* Tab Controls */}
        <div
          style={{
            display: "flex",
            gap: "0.5rem",
            marginBottom: "1.5rem",
            borderBottom: "1px solid var(--border-glass)",
            paddingBottom: "0.75rem",
          }}
        >
          <button
            type="button"
            className={`btn btn-sm ${activeTab === "invoices" ? "btn-primary" : "btn-secondary"}`}
            onClick={() => setActiveTab("invoices")}
          >
            Invoices ({invoiceCount})
          </button>
          <button
            type="button"
            className={`btn btn-sm ${activeTab === "accounts" ? "btn-primary" : "btn-secondary"}`}
            onClick={() => setActiveTab("accounts")}
          >
            Billing Accounts ({accountCount})
          </button>
        </div>

        {/* Error State */}
        {errorMessage && (
          <div
            style={{
              padding: "1rem",
              borderRadius: "8px",
              background: "var(--status-error-bg)",
              color: "var(--status-error)",
              border: "1px solid var(--status-error-border)",
              marginBottom: "1.5rem",
              fontSize: "0.875rem",
            }}
          >
            {errorMessage}
          </div>
        )}

        {/* Table Container Card */}
        <div
          style={{
            background: "var(--glass-surface-elevated)",
            border: "1px solid var(--border-glass)",
            borderRadius: "12px",
            overflow: "hidden",
            boxShadow: "var(--shadow-sm)",
          }}
        >
          {isLoading ? (
            <div style={{ padding: "3rem", display: "flex", justifyContent: "center" }}>
              <LoadingSpinner label={`Loading ${activeTab}...`} />
            </div>
          ) : activeTab === "invoices" ? (
            invoices.length === 0 ? (
              <div style={{ padding: "3rem", textAlign: "center", color: "var(--text-muted)" }}>
                No invoices found.
              </div>
            ) : (
              <div style={{ overflowX: "auto" }}>
                <table style={{ width: "100%", borderCollapse: "collapse", textAlign: "left", fontSize: "0.875rem" }}>
                  <thead>
                    <tr style={{ borderBottom: "1px solid var(--border-glass)", background: "rgba(255, 255, 255, 0.02)" }}>
                      <th style={{ padding: "0.875rem 1.25rem", color: "var(--text-secondary)", fontWeight: 600 }}>Invoice #</th>
                      <th style={{ padding: "0.875rem 1.25rem", color: "var(--text-secondary)", fontWeight: 600 }}>Tenant</th>
                      <th style={{ padding: "0.875rem 1.25rem", color: "var(--text-secondary)", fontWeight: 600 }}>Amount</th>
                      <th style={{ padding: "0.875rem 1.25rem", color: "var(--text-secondary)", fontWeight: 600 }}>Tax</th>
                      <th style={{ padding: "0.875rem 1.25rem", color: "var(--text-secondary)", fontWeight: 600 }}>Status</th>
                      <th style={{ padding: "0.875rem 1.25rem", color: "var(--text-secondary)", fontWeight: 600 }}>Due Date</th>
                      <th style={{ padding: "0.875rem 1.25rem", color: "var(--text-secondary)", fontWeight: 600 }}>Issued At</th>
                    </tr>
                  </thead>
                  <tbody>
                    {invoices.map((inv) => {
                      const badge = getStatusBadgeStyle(inv.status);
                      return (
                        <tr key={inv.id} style={{ borderBottom: "1px solid var(--border-glass)" }}>
                          <td style={{ padding: "1rem 1.25rem", fontWeight: 700, color: "var(--text-primary)" }}>
                            {inv.invoice_number}
                          </td>
                          <td style={{ padding: "1rem 1.25rem", color: "var(--text-primary)", fontWeight: 500 }}>
                            {inv.organization_name || inv.organization}
                          </td>
                          <td style={{ padding: "1rem 1.25rem", fontWeight: 600, color: "var(--text-primary)" }}>
                            {inv.currency} {Number(inv.total).toFixed(2)}
                          </td>
                          <td style={{ padding: "1rem 1.25rem", color: "var(--text-secondary)" }}>
                            {inv.currency} {Number(inv.tax_total).toFixed(2)}
                          </td>
                          <td style={{ padding: "1rem 1.25rem" }}>
                            <span
                              style={{
                                display: "inline-flex",
                                alignItems: "center",
                                padding: "0.2rem 0.5rem",
                                borderRadius: "4px",
                                fontSize: "0.75rem",
                                fontWeight: 600,
                                textTransform: "uppercase",
                                background: badge.bg,
                                color: badge.color,
                                border: `1px solid ${badge.border}`,
                              }}
                            >
                              {inv.status}
                            </span>
                          </td>
                          <td style={{ padding: "1rem 1.25rem", color: "var(--text-secondary)", fontSize: "0.8125rem" }}>
                            {inv.due_date ? new Date(inv.due_date).toLocaleDateString() : "—"}
                          </td>
                          <td style={{ padding: "1rem 1.25rem", color: "var(--text-muted)", fontSize: "0.8125rem" }}>
                            {inv.issued_at ? new Date(inv.issued_at).toLocaleDateString() : "—"}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )
          ) : accounts.length === 0 ? (
            <div style={{ padding: "3rem", textAlign: "center", color: "var(--text-muted)" }}>
              No billing accounts found.
            </div>
          ) : (
            <div style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse", textAlign: "left", fontSize: "0.875rem" }}>
                <thead>
                  <tr style={{ borderBottom: "1px solid var(--border-glass)", background: "rgba(255, 255, 255, 0.02)" }}>
                    <th style={{ padding: "0.875rem 1.25rem", color: "var(--text-secondary)", fontWeight: 600 }}>Tenant</th>
                    <th style={{ padding: "0.875rem 1.25rem", color: "var(--text-secondary)", fontWeight: 600 }}>Legal Name</th>
                    <th style={{ padding: "0.875rem 1.25rem", color: "var(--text-secondary)", fontWeight: 600 }}>Tax ID</th>
                    <th style={{ padding: "0.875rem 1.25rem", color: "var(--text-secondary)", fontWeight: 600 }}>Billing Email</th>
                    <th style={{ padding: "0.875rem 1.25rem", color: "var(--text-secondary)", fontWeight: 600 }}>Currency</th>
                    <th style={{ padding: "0.875rem 1.25rem", color: "var(--text-secondary)", fontWeight: 600 }}>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {accounts.map((acc) => (
                    <tr key={acc.id} style={{ borderBottom: "1px solid var(--border-glass)" }}>
                      <td style={{ padding: "1rem 1.25rem", fontWeight: 600, color: "var(--text-primary)" }}>
                        {acc.organization_name || acc.organization}
                      </td>
                      <td style={{ padding: "1rem 1.25rem", color: "var(--text-primary)" }}>
                        {acc.legal_name}
                      </td>
                      <td style={{ padding: "1rem 1.25rem", color: "var(--text-secondary)", fontFamily: "monospace" }}>
                        {acc.tax_id || "—"}
                      </td>
                      <td style={{ padding: "1rem 1.25rem", color: "var(--text-secondary)" }}>
                        {acc.billing_email}
                      </td>
                      <td style={{ padding: "1rem 1.25rem", fontWeight: 600, color: "var(--text-primary)" }}>
                        {acc.currency}
                      </td>
                      <td style={{ padding: "1rem 1.25rem" }}>
                        <span
                          style={{
                            display: "inline-flex",
                            alignItems: "center",
                            padding: "0.2rem 0.5rem",
                            borderRadius: "4px",
                            fontSize: "0.75rem",
                            fontWeight: 600,
                            textTransform: "uppercase",
                            background: acc.status === "active" ? "var(--status-success-bg)" : "var(--status-warning-bg)",
                            color: acc.status === "active" ? "var(--status-success)" : "var(--status-warning)",
                            border: `1px solid ${acc.status === "active" ? "var(--status-success-border)" : "var(--status-warning-border)"}`,
                          }}
                        >
                          {acc.status}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* Pagination */}
          {!isLoading && (
            <div
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                padding: "1rem 1.25rem",
                borderTop: "1px solid var(--border-glass)",
                fontSize: "0.875rem",
                color: "var(--text-secondary)",
              }}
            >
              {activeTab === "invoices" ? (
                <>
                  <div>
                    Showing {invoiceCount === 0 ? 0 : (invoicePage - 1) * pageSize + 1} to{" "}
                    {Math.min(invoicePage * pageSize, invoiceCount)} of {invoiceCount} invoices
                  </div>
                  <div style={{ display: "flex", gap: "0.5rem" }}>
                    <button
                      type="button"
                      className="btn btn-secondary btn-sm"
                      disabled={invoicePage <= 1}
                      onClick={() => setInvoicePage((p) => Math.max(p - 1, 1))}
                    >
                      Previous
                    </button>
                    <span style={{ padding: "0.4rem 0.75rem", fontWeight: 600, color: "var(--text-primary)" }}>
                      {invoicePage} / {Math.ceil(invoiceCount / pageSize) || 1}
                    </span>
                    <button
                      type="button"
                      className="btn btn-secondary btn-sm"
                      disabled={invoicePage >= (Math.ceil(invoiceCount / pageSize) || 1)}
                      onClick={() => setInvoicePage((p) => p + 1)}
                    >
                      Next
                    </button>
                  </div>
                </>
              ) : (
                <>
                  <div>
                    Showing {accountCount === 0 ? 0 : (accountPage - 1) * pageSize + 1} to{" "}
                    {Math.min(accountPage * pageSize, accountCount)} of {accountCount} accounts
                  </div>
                  <div style={{ display: "flex", gap: "0.5rem" }}>
                    <button
                      type="button"
                      className="btn btn-secondary btn-sm"
                      disabled={accountPage <= 1}
                      onClick={() => setAccountPage((p) => Math.max(p - 1, 1))}
                    >
                      Previous
                    </button>
                    <span style={{ padding: "0.4rem 0.75rem", fontWeight: 600, color: "var(--text-primary)" }}>
                      {accountPage} / {Math.ceil(accountCount / pageSize) || 1}
                    </span>
                    <button
                      type="button"
                      className="btn btn-secondary btn-sm"
                      disabled={accountPage >= (Math.ceil(accountCount / pageSize) || 1)}
                      onClick={() => setAccountPage((p) => p + 1)}
                    >
                      Next
                    </button>
                  </div>
                </>
              )}
            </div>
          )}
        </div>
      </div>
    </AppShell>
  );
};
