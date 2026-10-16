/**
 * Tenant Billing & Invoices Page (Phase 4D).
 *
 * Route: /tenant/billing
 * Context Guard: tenant (requires tenant_billing / billing.view)
 * Read-only interface for tenant administrators.
 */

import React, { useState, useEffect, useCallback } from "react";
import { AppShell } from "../../components/AppShell.tsx";
import {
  billingApi,
  type Invoice,
  type BillingAccount,
} from "../../api/billing.ts";
import { LoadingSpinner } from "../../components/LoadingSpinner.tsx";

export const TenantBillingPage: React.FC = () => {
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [billingAccount, setBillingAccount] = useState<BillingAccount | null>(null);
  const [selectedInvoice, setSelectedInvoice] = useState<Invoice | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const fetchTenantBillingData = useCallback(async () => {
    setIsLoading(true);
    setErrorMessage(null);
    try {
      const [invRes, accRes] = await Promise.allSettled([
        billingApi.getTenantInvoices(),
        billingApi.getTenantBillingAccount(),
      ]);

      if (invRes.status === "fulfilled") {
        setInvoices(invRes.value.results || []);
      }
      if (accRes.status === "fulfilled") {
        setBillingAccount(accRes.value);
      }
    } catch (err: unknown) {
      const msg = err && typeof err === "object" && "message" in err
        ? String((err as { message: string }).message)
        : "Failed to load billing details.";
      setErrorMessage(msg);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    void fetchTenantBillingData();
  }, [fetchTenantBillingData]);

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
      <div style={{ padding: "2rem", maxWidth: "1200px", margin: "0 auto" }}>
        {/* Header */}
        <div style={{ marginBottom: "2rem" }}>
          <h1
            className="heading-hero"
            style={{ fontSize: "1.75rem", margin: "0 0 0.5rem 0", color: "var(--text-primary)" }}
          >
            Billing & Invoices
          </h1>
          <p style={{ margin: 0, color: "var(--text-secondary)", fontSize: "0.9375rem" }}>
            View your organization's invoices, payment receipts, and billing profile.
          </p>
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

        {/* Billing Profile Card (if exists) */}
        {billingAccount && (
          <div
            style={{
              background: "var(--glass-surface-elevated)",
              border: "1px solid var(--border-glass)",
              borderRadius: "12px",
              padding: "1.5rem",
              marginBottom: "2rem",
            }}
          >
            <h2 style={{ fontSize: "1.125rem", margin: "0 0 1rem 0", color: "var(--text-primary)" }}>
              Billing Profile
            </h2>
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
                gap: "1rem",
                fontSize: "0.875rem",
              }}
            >
              <div>
                <span style={{ color: "var(--text-secondary)", display: "block", fontSize: "0.75rem", marginBottom: "0.25rem" }}>
                  Legal Business Name
                </span>
                <strong style={{ color: "var(--text-primary)" }}>{billingAccount.legal_name}</strong>
              </div>
              <div>
                <span style={{ color: "var(--text-secondary)", display: "block", fontSize: "0.75rem", marginBottom: "0.25rem" }}>
                  Tax ID / GSTIN
                </span>
                <span style={{ color: "var(--text-primary)", fontFamily: "monospace" }}>
                  {billingAccount.tax_id || "Not registered"}
                </span>
              </div>
              <div>
                <span style={{ color: "var(--text-secondary)", display: "block", fontSize: "0.75rem", marginBottom: "0.25rem" }}>
                  Billing Email
                </span>
                <span style={{ color: "var(--text-primary)" }}>{billingAccount.billing_email}</span>
              </div>
              <div>
                <span style={{ color: "var(--text-secondary)", display: "block", fontSize: "0.75rem", marginBottom: "0.25rem" }}>
                  Currency
                </span>
                <span style={{ color: "var(--text-primary)", fontWeight: 600 }}>{billingAccount.currency}</span>
              </div>
            </div>
          </div>
        )}

        {/* Invoices List */}
        <div
          style={{
            background: "var(--glass-surface-elevated)",
            border: "1px solid var(--border-glass)",
            borderRadius: "12px",
            overflow: "hidden",
            boxShadow: "var(--shadow-sm)",
          }}
        >
          <div style={{ padding: "1.25rem 1.5rem", borderBottom: "1px solid var(--border-glass)" }}>
            <h2 style={{ fontSize: "1.125rem", margin: 0, color: "var(--text-primary)" }}>
              Invoices History
            </h2>
          </div>

          {isLoading ? (
            <div style={{ padding: "3rem", display: "flex", justifyContent: "center" }}>
              <LoadingSpinner label="Loading invoices..." />
            </div>
          ) : invoices.length === 0 ? (
            <div style={{ padding: "3rem", textAlign: "center", color: "var(--text-muted)" }}>
              No invoices have been issued for this organization.
            </div>
          ) : (
            <div style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse", textAlign: "left", fontSize: "0.875rem" }}>
                <thead>
                  <tr style={{ borderBottom: "1px solid var(--border-glass)", background: "rgba(255, 255, 255, 0.02)" }}>
                    <th style={{ padding: "0.875rem 1.25rem", color: "var(--text-secondary)", fontWeight: 600 }}>Invoice #</th>
                    <th style={{ padding: "0.875rem 1.25rem", color: "var(--text-secondary)", fontWeight: 600 }}>Date</th>
                    <th style={{ padding: "0.875rem 1.25rem", color: "var(--text-secondary)", fontWeight: 600 }}>Total Amount</th>
                    <th style={{ padding: "0.875rem 1.25rem", color: "var(--text-secondary)", fontWeight: 600 }}>Tax</th>
                    <th style={{ padding: "0.875rem 1.25rem", color: "var(--text-secondary)", fontWeight: 600 }}>Due Date</th>
                    <th style={{ padding: "0.875rem 1.25rem", color: "var(--text-secondary)", fontWeight: 600 }}>Status</th>
                    <th style={{ padding: "0.875rem 1.25rem", color: "var(--text-secondary)", fontWeight: 600, textAlign: "right" }}>Action</th>
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
                        <td style={{ padding: "1rem 1.25rem", color: "var(--text-secondary)" }}>
                          {inv.issued_at ? new Date(inv.issued_at).toLocaleDateString() : new Date(inv.created_at).toLocaleDateString()}
                        </td>
                        <td style={{ padding: "1rem 1.25rem", fontWeight: 600, color: "var(--text-primary)" }}>
                          {inv.currency} {Number(inv.total).toFixed(2)}
                        </td>
                        <td style={{ padding: "1rem 1.25rem", color: "var(--text-secondary)" }}>
                          {inv.currency} {Number(inv.tax_total).toFixed(2)}
                        </td>
                        <td style={{ padding: "1rem 1.25rem", color: "var(--text-secondary)" }}>
                          {inv.due_date ? new Date(inv.due_date).toLocaleDateString() : "—"}
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
                        <td style={{ padding: "1rem 1.25rem", textAlign: "right" }}>
                          <button
                            type="button"
                            className="btn btn-secondary btn-sm"
                            onClick={() => setSelectedInvoice(inv)}
                          >
                            View Details
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* Invoice Detail Modal (Read-Only) */}
        {selectedInvoice && (
          <div
            style={{
              position: "fixed",
              top: 0,
              left: 0,
              right: 0,
              bottom: 0,
              background: "rgba(0, 0, 0, 0.6)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              zIndex: 1000,
              padding: "1rem",
            }}
            onClick={() => setSelectedInvoice(null)}
          >
            <div
              style={{
                background: "var(--bg-card, #1e1e24)",
                border: "1px solid var(--border-glass)",
                borderRadius: "12px",
                width: "100%",
                maxWidth: "600px",
                padding: "2rem",
                boxShadow: "var(--shadow-lg)",
              }}
              onClick={(e) => e.stopPropagation()}
            >
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1.5rem" }}>
                <div>
                  <h3 style={{ margin: 0, fontSize: "1.25rem", color: "var(--text-primary)" }}>
                    Invoice {selectedInvoice.invoice_number}
                  </h3>
                  <span style={{ fontSize: "0.8125rem", color: "var(--text-secondary)" }}>
                    Status: <strong style={{ textTransform: "capitalize" }}>{selectedInvoice.status}</strong>
                  </span>
                </div>
                <button
                  type="button"
                  className="btn btn-secondary btn-sm"
                  onClick={() => setSelectedInvoice(null)}
                >
                  Close
                </button>
              </div>

              {/* Line items table */}
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.875rem", marginBottom: "1.5rem" }}>
                <thead>
                  <tr style={{ borderBottom: "1px solid var(--border-glass)" }}>
                    <th style={{ padding: "0.5rem 0", textAlign: "left", color: "var(--text-secondary)" }}>Description</th>
                    <th style={{ padding: "0.5rem 0", textAlign: "center", color: "var(--text-secondary)" }}>Qty</th>
                    <th style={{ padding: "0.5rem 0", textAlign: "right", color: "var(--text-secondary)" }}>Price</th>
                    <th style={{ padding: "0.5rem 0", textAlign: "right", color: "var(--text-secondary)" }}>Total</th>
                  </tr>
                </thead>
                <tbody>
                  {selectedInvoice.lines.map((l) => (
                    <tr key={l.id} style={{ borderBottom: "1px solid var(--border-glass)" }}>
                      <td style={{ padding: "0.75rem 0", color: "var(--text-primary)" }}>{l.description}</td>
                      <td style={{ padding: "0.75rem 0", textAlign: "center", color: "var(--text-secondary)" }}>{l.quantity}</td>
                      <td style={{ padding: "0.75rem 0", textAlign: "right", color: "var(--text-secondary)" }}>
                        {selectedInvoice.currency} {Number(l.unit_price).toFixed(2)}
                      </td>
                      <td style={{ padding: "0.75rem 0", textAlign: "right", fontWeight: 600, color: "var(--text-primary)" }}>
                        {selectedInvoice.currency} {Number(l.total_amount).toFixed(2)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>

              {/* Totals */}
              <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem", alignItems: "flex-end", fontSize: "0.875rem" }}>
                <div>
                  <span style={{ color: "var(--text-secondary)", marginRight: "1rem" }}>Subtotal:</span>
                  <span style={{ color: "var(--text-primary)" }}>{selectedInvoice.currency} {Number(selectedInvoice.subtotal).toFixed(2)}</span>
                </div>
                <div>
                  <span style={{ color: "var(--text-secondary)", marginRight: "1rem" }}>Tax:</span>
                  <span style={{ color: "var(--text-primary)" }}>{selectedInvoice.currency} {Number(selectedInvoice.tax_total).toFixed(2)}</span>
                </div>
                <div style={{ fontSize: "1.125rem", fontWeight: 700, borderTop: "1px solid var(--border-glass)", paddingTop: "0.5rem" }}>
                  <span style={{ color: "var(--text-primary)", marginRight: "1rem" }}>Total:</span>
                  <span style={{ color: "var(--brand-primary)" }}>{selectedInvoice.currency} {Number(selectedInvoice.total).toFixed(2)}</span>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </AppShell>
  );
};
