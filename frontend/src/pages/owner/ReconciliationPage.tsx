/**
 * Platform Owner Commercial Reconciliation Page (Phase 4E).
 *
 * Route: /reconciliation
 * Context Guard: platform_owner
 */

import React, { useState, useEffect, useCallback } from "react";
import { AppShell } from "../../components/AppShell.tsx";
import { LoadingSpinner } from "../../components/LoadingSpinner.tsx";
import {
  reconciliationApi,
  type CommercialReconciliation,
} from "../../api/reconciliation.ts";

export const ReconciliationPage: React.FC = () => {
  const [reconciliations, setReconciliations] = useState<CommercialReconciliation[]>([]);
  const [totalCount, setTotalCount] = useState<number>(0);
  const [statusFilter, setStatusFilter] = useState<string>("open");
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [isTriggering, setIsTriggering] = useState<boolean>(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  // Resolution modal state
  const [resolvingItem, setResolvingItem] = useState<CommercialReconciliation | null>(null);
  const [resolutionReason, setResolutionReason] = useState<string>("");
  const [isSubmittingResolution, setIsSubmittingResolution] = useState<boolean>(false);
  const [modalError, setModalError] = useState<string | null>(null);

  const fetchReconciliations = useCallback(async () => {
    setIsLoading(true);
    setErrorMessage(null);
    try {
      const res = await reconciliationApi.getReconciliations({
        status: statusFilter || undefined,
      });
      setReconciliations(res.results || []);
      setTotalCount(res.count || 0);
    } catch (err: unknown) {
      const msg =
        err && typeof err === "object" && "message" in err
          ? String((err as { message: string }).message)
          : "Failed to load commercial reconciliation records.";
      setErrorMessage(msg);
    } finally {
      setIsLoading(false);
    }
  }, [statusFilter]);

  useEffect(() => {
    void fetchReconciliations();
  }, [fetchReconciliations]);

  const handleTriggerRun = async () => {
    setIsTriggering(true);
    setErrorMessage(null);
    setSuccessMessage(null);
    try {
      const res = await reconciliationApi.triggerReconciliation();
      setSuccessMessage(res.message || "Reconciliation job enqueued successfully.");
      await fetchReconciliations();
    } catch (err: unknown) {
      const msg =
        err && typeof err === "object" && "message" in err
          ? String((err as { message: string }).message)
          : "Failed to trigger reconciliation job.";
      setErrorMessage(msg);
    } finally {
      setIsTriggering(false);
    }
  };

  const handleOpenResolveModal = (item: CommercialReconciliation) => {
    setResolvingItem(item);
    setResolutionReason("");
    setModalError(null);
  };

  const handleCloseResolveModal = () => {
    setResolvingItem(null);
    setResolutionReason("");
    setModalError(null);
  };

  const handleSubmitResolution = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!resolvingItem) return;
    if (!resolutionReason.trim()) {
      setModalError("Please provide a reason for resolving this discrepancy.");
      return;
    }

    setIsSubmittingResolution(true);
    setModalError(null);
    try {
      await reconciliationApi.resolveReconciliation(resolvingItem.id, resolutionReason.trim());
      handleCloseResolveModal();
      setSuccessMessage("Discrepancy resolved successfully.");
      await fetchReconciliations();
    } catch (err: unknown) {
      const msg =
        err && typeof err === "object" && "message" in err
          ? String((err as { message: string }).message)
          : "Failed to resolve discrepancy.";
      setModalError(msg);
    } finally {
      setIsSubmittingResolution(false);
    }
  };

  const getIssueLabel = (code: string) => {
    switch (code) {
      case "SUB_ACTIVE_NO_BILLING_ACCOUNT":
        return "Active Subscription Missing Billing Account";
      case "INVOICE_PRICE_MISMATCH":
        return "Invoice Price Differs From Subscription Plan Snapshot";
      case "ORPHANED_ENTITLEMENT":
        return "Orphaned Active Product Entitlement Without Active Subscription";
      default:
        return code;
    }
  };

  return (
    <AppShell>
      <div style={{ padding: "2rem", maxWidth: "1400px", margin: "0 auto" }}>
        {/* Header */}
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "flex-start",
            marginBottom: "2rem",
            flexWrap: "wrap",
            gap: "1rem",
          }}
        >
          <div>
            <h1
              className="heading-hero"
              style={{ fontSize: "1.75rem", margin: "0 0 0.5rem 0", color: "var(--text-primary)" }}
            >
              Commercial Reconciliation
            </h1>
            <p style={{ margin: 0, color: "var(--text-secondary)", fontSize: "0.9375rem" }}>
              Automated read-only integrity inspection comparing billing, subscriptions, entitlements, and usage.
            </p>
          </div>
          <div>
            <button
              onClick={handleTriggerRun}
              disabled={isTriggering}
              className="btn btn-primary"
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: "0.5rem",
                padding: "0.625rem 1.25rem",
                cursor: isTriggering ? "not-allowed" : "pointer",
              }}
            >
              {isTriggering ? "Running..." : "Trigger Reconciliation Job"}
            </button>
          </div>
        </div>

        {/* Alerts */}
        {errorMessage && (
          <div
            style={{
              padding: "1rem",
              background: "rgba(239, 68, 68, 0.1)",
              border: "1px solid rgba(239, 68, 68, 0.3)",
              borderRadius: "0.5rem",
              color: "#f87171",
              marginBottom: "1.5rem",
            }}
          >
            {errorMessage}
          </div>
        )}

        {successMessage && (
          <div
            style={{
              padding: "1rem",
              background: "rgba(16, 185, 129, 0.1)",
              border: "1px solid rgba(16, 185, 129, 0.3)",
              borderRadius: "0.5rem",
              color: "#34d399",
              marginBottom: "1.5rem",
            }}
          >
            {successMessage}
          </div>
        )}

        {/* Filter Toolbar */}
        <div
          style={{
            display: "flex",
            gap: "1rem",
            alignItems: "center",
            marginBottom: "1.5rem",
          }}
        >
          <span style={{ fontSize: "0.875rem", color: "var(--text-secondary)" }}>Filter Status:</span>
          {(["open", "resolved", ""] as const).map((s) => (
            <button
              key={s || "all"}
              onClick={() => setStatusFilter(s)}
              style={{
                padding: "0.375rem 0.875rem",
                borderRadius: "0.375rem",
                fontSize: "0.875rem",
                border: "1px solid var(--border-color)",
                background: statusFilter === s ? "var(--brand-primary, #3b82f6)" : "transparent",
                color: statusFilter === s ? "#fff" : "var(--text-primary)",
                cursor: "pointer",
              }}
            >
              {s === "open" ? "Open Issues" : s === "resolved" ? "Resolved" : "All Records"}
            </button>
          ))}
          <span style={{ marginLeft: "auto", fontSize: "0.875rem", color: "var(--text-secondary)" }}>
            Found: <strong>{totalCount}</strong>
          </span>
        </div>

        {/* Main Content */}
        {isLoading ? (
          <div style={{ display: "flex", justifyContent: "center", padding: "4rem" }}>
            <LoadingSpinner fullScreen={false} label="Loading reconciliations..." />
          </div>
        ) : reconciliations.length === 0 ? (
          <div
            style={{
              padding: "3rem",
              textAlign: "center",
              background: "var(--bg-surface)",
              borderRadius: "0.75rem",
              border: "1px solid var(--border-color)",
              color: "var(--text-secondary)",
            }}
          >
            <p style={{ margin: 0, fontSize: "1.125rem", color: "var(--text-primary)" }}>
              No reconciliation issues found.
            </p>
            <p style={{ margin: "0.5rem 0 0 0", fontSize: "0.875rem" }}>
              All cross-domain billing, subscription, and entitlement records are aligned.
            </p>
          </div>
        ) : (
          <div
            style={{
              background: "var(--bg-surface)",
              borderRadius: "0.75rem",
              border: "1px solid var(--border-color)",
              overflow: "hidden",
            }}
          >
            <table style={{ width: "100%", borderCollapse: "collapse", textAlign: "left" }}>
              <thead>
                <tr style={{ borderBottom: "1px solid var(--border-color)", background: "rgba(255,255,255,0.02)" }}>
                  <th style={{ padding: "0.875rem 1rem", fontSize: "0.8125rem", color: "var(--text-secondary)" }}>
                    ORGANIZATION
                  </th>
                  <th style={{ padding: "0.875rem 1rem", fontSize: "0.8125rem", color: "var(--text-secondary)" }}>
                    DISCREPANCY
                  </th>
                  <th style={{ padding: "0.875rem 1rem", fontSize: "0.8125rem", color: "var(--text-secondary)" }}>
                    STATUS
                  </th>
                  <th style={{ padding: "0.875rem 1rem", fontSize: "0.8125rem", color: "var(--text-secondary)" }}>
                    DETECTED AT
                  </th>
                  <th style={{ padding: "0.875rem 1rem", fontSize: "0.8125rem", color: "var(--text-secondary)", textAlign: "right" }}>
                    ACTIONS
                  </th>
                </tr>
              </thead>
              <tbody>
                {reconciliations.map((rec) => {
                  const isOpen = rec.status === "open";
                  return (
                    <tr
                      key={rec.id}
                      style={{
                        borderBottom: "1px solid var(--border-color)",
                      }}
                    >
                      <td style={{ padding: "1rem" }}>
                        <div style={{ fontWeight: 600, color: "var(--text-primary)" }}>
                          {rec.organization_name || rec.organization_code || rec.organization}
                        </div>
                        {rec.subscription_plan_code && (
                          <div style={{ fontSize: "0.75rem", color: "var(--text-secondary)", marginTop: "0.25rem" }}>
                            Plan: {rec.subscription_plan_code}
                          </div>
                        )}
                      </td>
                      <td style={{ padding: "1rem" }}>
                        <span
                          style={{
                            display: "inline-block",
                            padding: "0.25rem 0.5rem",
                            borderRadius: "0.25rem",
                            fontSize: "0.75rem",
                            fontFamily: "monospace",
                            background: "rgba(239, 68, 68, 0.15)",
                            color: "#f87171",
                            marginBottom: "0.25rem",
                          }}
                        >
                          {rec.issue_code}
                        </span>
                        <div style={{ fontSize: "0.8125rem", color: "var(--text-secondary)" }}>
                          {getIssueLabel(rec.issue_code)}
                        </div>
                      </td>
                      <td style={{ padding: "1rem" }}>
                        <span
                          style={{
                            display: "inline-block",
                            padding: "0.25rem 0.625rem",
                            borderRadius: "9999px",
                            fontSize: "0.75rem",
                            fontWeight: 600,
                            background: isOpen ? "rgba(245, 158, 11, 0.15)" : "rgba(16, 185, 129, 0.15)",
                            color: isOpen ? "#fbbf24" : "#34d399",
                          }}
                        >
                          {isOpen ? "Open" : "Resolved"}
                        </span>
                        {!isOpen && rec.resolved_by_email && (
                          <div style={{ fontSize: "0.75rem", color: "var(--text-secondary)", marginTop: "0.25rem" }}>
                            by {rec.resolved_by_email}
                          </div>
                        )}
                      </td>
                      <td style={{ padding: "1rem", fontSize: "0.8125rem", color: "var(--text-secondary)" }}>
                        {new Date(rec.detected_at).toLocaleString()}
                      </td>
                      <td style={{ padding: "1rem", textAlign: "right" }}>
                        {isOpen ? (
                          <button
                            onClick={() => handleOpenResolveModal(rec)}
                            className="btn btn-secondary"
                            style={{
                              fontSize: "0.8125rem",
                              padding: "0.375rem 0.75rem",
                              cursor: "pointer",
                            }}
                          >
                            Mark Resolved
                          </button>
                        ) : (
                          <span style={{ fontSize: "0.8125rem", color: "var(--text-secondary)" }}>
                            {rec.resolution_reason || "Resolved"}
                          </span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}

        {/* Resolve Modal */}
        {resolvingItem && (
          <div
            style={{
              position: "fixed",
              top: 0,
              left: 0,
              right: 0,
              bottom: 0,
              backgroundColor: "rgba(0, 0, 0, 0.7)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              zIndex: 1000,
            }}
          >
            <div
              style={{
                background: "var(--bg-surface)",
                padding: "2rem",
                borderRadius: "0.75rem",
                width: "100%",
                maxWidth: "500px",
                border: "1px solid var(--border-color)",
                boxShadow: "0 20px 25px -5px rgba(0, 0, 0, 0.5)",
              }}
            >
              <h2 style={{ margin: "0 0 1rem 0", fontSize: "1.25rem", color: "var(--text-primary)" }}>
                Mark Discrepancy Resolved
              </h2>

              <p style={{ margin: "0 0 1rem 0", fontSize: "0.875rem", color: "var(--text-secondary)" }}>
                This will mark issue <code>{resolvingItem.issue_code}</code> as resolved with an immutable audit log.
              </p>

              {modalError && (
                <div
                  style={{
                    padding: "0.75rem",
                    background: "rgba(239, 68, 68, 0.1)",
                    border: "1px solid rgba(239, 68, 68, 0.3)",
                    borderRadius: "0.375rem",
                    color: "#f87171",
                    marginBottom: "1rem",
                    fontSize: "0.875rem",
                  }}
                >
                  {modalError}
                </div>
              )}

              <form onSubmit={handleSubmitResolution}>
                <div style={{ marginBottom: "1.5rem" }}>
                  <label
                    style={{
                      display: "block",
                      fontSize: "0.875rem",
                      fontWeight: 500,
                      marginBottom: "0.5rem",
                      color: "var(--text-primary)",
                    }}
                  >
                    Resolution Reason *
                  </label>
                  <textarea
                    rows={4}
                    value={resolutionReason}
                    onChange={(e) => setResolutionReason(e.target.value)}
                    placeholder="Describe how this issue was verified or resolved (e.g. customer billing account restored)."
                    style={{
                      width: "100%",
                      padding: "0.75rem",
                      borderRadius: "0.375rem",
                      border: "1px solid var(--border-color)",
                      background: "rgba(0, 0, 0, 0.2)",
                      color: "var(--text-primary)",
                      fontSize: "0.875rem",
                      boxSizing: "border-box",
                      resize: "vertical",
                    }}
                    required
                  />
                </div>

                <div style={{ display: "flex", justifyContent: "flex-end", gap: "0.75rem" }}>
                  <button
                    type="button"
                    onClick={handleCloseResolveModal}
                    className="btn btn-secondary"
                    style={{ padding: "0.5rem 1rem", fontSize: "0.875rem" }}
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={isSubmittingResolution}
                    className="btn btn-primary"
                    style={{ padding: "0.5rem 1rem", fontSize: "0.875rem" }}
                  >
                    {isSubmittingResolution ? "Saving..." : "Confirm Resolution"}
                  </button>
                </div>
              </form>
            </div>
          </div>
        )}
      </div>
    </AppShell>
  );
};
