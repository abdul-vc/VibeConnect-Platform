/**
 * Platform Owner Commercial Reconciliation Page (Phase 4E).
 *
 * Route: /reconciliation
 * Context Guard: platform_owner
 */

import React, { useState, useEffect, useCallback, useMemo } from "react";
import { Link } from "react-router-dom";
import { AppShell } from "../../components/AppShell.tsx";
import { LoadingSpinner } from "../../components/LoadingSpinner.tsx";
import {
  ShieldCheckIcon,
  RotateCcwIcon,
  BuildingIcon,
  AlertCircleIcon,
  CheckCircleIcon,
  CalendarIcon,
  SearchIcon,
  CloseIcon,
} from "../../components/Icons.tsx";
import {
  reconciliationApi,
  type CommercialReconciliation,
} from "../../api/reconciliation.ts";

export const ReconciliationPage: React.FC = () => {
  const [reconciliations, setReconciliations] = useState<CommercialReconciliation[]>([]);
  const [totalCount, setTotalCount] = useState<number>(0);
  const [statusFilter, setStatusFilter] = useState<string>("open");
  const [searchTerm, setSearchTerm] = useState<string>("");
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

  const filteredReconciliations = useMemo(() => {
    if (!searchTerm.trim()) return reconciliations;
    const term = searchTerm.toLowerCase().trim();
    return reconciliations.filter((rec) => {
      const orgName = (rec.organization_name || "").toLowerCase();
      const orgCode = (rec.organization_code || "").toLowerCase();
      const orgId = (rec.organization || "").toLowerCase();
      const issue = (rec.issue_code || "").toLowerCase();
      const label = (getIssueLabel(rec.issue_code) || "").toLowerCase();
      const plan = (rec.subscription_plan_code || "").toLowerCase();
      return (
        orgName.includes(term) ||
        orgCode.includes(term) ||
        orgId.includes(term) ||
        issue.includes(term) ||
        label.includes(term) ||
        plan.includes(term)
      );
    });
  }, [reconciliations, searchTerm]);

  return (
    <AppShell>
      <div style={{ padding: "2rem", maxWidth: "1400px", margin: "0 auto" }}>
        {/* Breadcrumb Navigation */}
        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", fontSize: "0.8125rem", color: "var(--text-muted)", marginBottom: "1.25rem", fontWeight: 500 }}>
          <Link to="/" style={{ color: "var(--text-muted)", textDecoration: "none", transition: "color 0.15s" }}>Platform Owner</Link>
          <span>/</span>
          <span>Platform</span>
          <span>/</span>
          <span style={{ color: "var(--brand-primary)", fontWeight: 600 }}>Commercial Reconciliation</span>
        </div>

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
          <div style={{ display: "flex", alignItems: "center", gap: "1rem" }}>
            <div
              style={{
                width: 48,
                height: 48,
                borderRadius: 14,
                background: "linear-gradient(135deg, rgba(56, 103, 245, 0.15) 0%, rgba(139, 92, 246, 0.15) 100%)",
                border: "1px solid rgba(56, 103, 245, 0.25)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                color: "var(--brand-primary)",
                boxShadow: "0 4px 12px rgba(56, 103, 245, 0.1)",
                flexShrink: 0,
              }}
            >
              <ShieldCheckIcon size={24} />
            </div>
            <div>
              <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
                <h1
                  className="heading-hero"
                  style={{ fontSize: "1.75rem", margin: 0, color: "var(--text-primary)", fontWeight: 800, letterSpacing: "-0.02em" }}
                >
                  Commercial Reconciliation
                </h1>
                <span
                  style={{
                    background: "rgba(56, 103, 245, 0.1)",
                    color: "var(--brand-primary)",
                    padding: "0.2rem 0.65rem",
                    borderRadius: 999,
                    fontSize: "0.75rem",
                    fontWeight: 700,
                    border: "1px solid rgba(56, 103, 245, 0.2)",
                  }}
                >
                  {totalCount} Discrepancies
                </span>
              </div>
              <p style={{ margin: "0.25rem 0 0 0", color: "var(--text-secondary)", fontSize: "0.9375rem" }}>
                Automated read-only integrity inspection comparing billing, subscriptions, entitlements, and usage.
              </p>
            </div>
          </div>
          <div>
            <button
              onClick={handleTriggerRun}
              disabled={isTriggering}
              className="btn btn-gradient"
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: "0.5rem",
              }}
            >
              <RotateCcwIcon size={16} className={isTriggering ? "spinner-icon" : ""} />
              {isTriggering ? "Running..." : "Trigger Reconciliation Job"}
            </button>
          </div>
        </div>

        {/* Alerts */}
        {errorMessage && (
          <div
            style={{
              padding: "1rem 1.25rem",
              background: "var(--status-danger-bg)",
              border: "1px solid var(--status-danger-border)",
              borderRadius: "0.5rem",
              color: "var(--status-danger)",
              marginBottom: "1.5rem",
              fontSize: "0.875rem",
              display: "flex",
              alignItems: "center",
              gap: "0.75rem",
            }}
          >
            <AlertCircleIcon size={18} style={{ flexShrink: 0 }} />
            <span>{errorMessage}</span>
          </div>
        )}

        {successMessage && (
          <div
            style={{
              padding: "1rem 1.25rem",
              background: "var(--status-success-bg)",
              border: "1px solid var(--status-success-border)",
              borderRadius: "0.5rem",
              color: "var(--status-success)",
              marginBottom: "1.5rem",
              fontSize: "0.875rem",
              display: "flex",
              alignItems: "center",
              gap: "0.75rem",
            }}
          >
            <CheckCircleIcon size={18} style={{ flexShrink: 0 }} />
            <span>{successMessage}</span>
          </div>
        )}

        {/* Filter Toolbar */}
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            flexWrap: "wrap",
            gap: "1rem",
            marginBottom: "1.5rem",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", flexWrap: "wrap" }}>
            <span style={{ fontSize: "0.875rem", fontWeight: 600, color: "var(--text-secondary)" }}>
              Filter Status:
            </span>
            <div
              style={{
                display: "inline-flex",
                background: "var(--glass-surface-sunken)",
                padding: "3px",
                borderRadius: "8px",
                border: "1px solid var(--border-subtle)",
                gap: "2px",
              }}
            >
              {(["open", "resolved", ""] as const).map((s) => {
                const isActive = statusFilter === s;
                return (
                  <button
                    key={s || "all"}
                    type="button"
                    onClick={() => setStatusFilter(s)}
                    style={{
                      padding: "0.4rem 0.85rem",
                      borderRadius: "6px",
                      fontSize: "0.8125rem",
                      fontWeight: isActive ? 600 : 500,
                      border: "none",
                      background: isActive ? "var(--glass-surface-elevated)" : "transparent",
                      color: isActive ? "var(--brand-primary)" : "var(--text-secondary)",
                      boxShadow: isActive ? "var(--shadow-sm)" : "none",
                      cursor: "pointer",
                      transition: "all 0.15s ease",
                    }}
                  >
                    {s === "open" ? "Open Issues" : s === "resolved" ? "Resolved" : "All Records"}
                  </button>
                );
              })}
            </div>
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: "1rem", flexWrap: "wrap" }}>
            <div
              style={{
                position: "relative",
                display: "flex",
                alignItems: "center",
              }}
            >
              <SearchIcon
                size={16}
                style={{
                  position: "absolute",
                  left: "0.75rem",
                  color: "var(--text-muted)",
                  pointerEvents: "none",
                }}
              />
              <input
                type="text"
                placeholder="Search organization or issue..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                style={{
                  padding: "0.45rem 0.75rem 0.45rem 2.25rem",
                  borderRadius: "6px",
                  fontSize: "0.8125rem",
                  background: "var(--input-bg)",
                  border: "1px solid var(--border-subtle)",
                  color: "var(--text-primary)",
                  width: "240px",
                  outline: "none",
                  boxSizing: "border-box",
                }}
              />
            </div>
            <span style={{ fontSize: "0.875rem", color: "var(--text-secondary)" }}>
              Found: <strong style={{ color: "var(--text-primary)" }}>{filteredReconciliations.length}</strong>
            </span>
          </div>
        </div>

        {/* Main Content */}
        {isLoading ? (
          <div style={{ display: "flex", justifyContent: "center", padding: "4rem" }}>
            <LoadingSpinner fullScreen={false} label="Loading reconciliations..." />
          </div>
        ) : filteredReconciliations.length === 0 ? (
          <div
            className="table-card-container"
            style={{
              padding: "3.5rem 2rem",
              textAlign: "center",
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              justifyContent: "center",
            }}
          >
            <div
              style={{
                width: 52,
                height: 52,
                borderRadius: "50%",
                background: "var(--status-success-bg)",
                border: "1px solid var(--status-success-border)",
                color: "var(--status-success)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                marginBottom: "1rem",
              }}
            >
              <CheckCircleIcon size={26} />
            </div>
            <h3 style={{ margin: 0, fontSize: "1.125rem", color: "var(--text-primary)", fontWeight: 700 }}>
              No reconciliation issues found
            </h3>
            <p style={{ margin: "0.5rem 0 0 0", fontSize: "0.875rem", color: "var(--text-secondary)", maxWidth: "480px" }}>
              {searchTerm
                ? "No records match your search filter."
                : "All cross-domain billing, subscription, and entitlement records are aligned."}
            </p>
          </div>
        ) : (
          <div className="table-card-container">
            <div className="table-card-scroll">
              <table style={{ width: "100%", borderCollapse: "collapse", textAlign: "left" }}>
                <thead>
                  <tr
                    style={{
                      borderBottom: "1px solid var(--border-subtle)",
                      background: "var(--glass-surface-sunken)",
                    }}
                  >
                    <th
                      scope="col"
                      style={{
                        padding: "0.875rem 1.25rem",
                        fontSize: "0.75rem",
                        fontWeight: 700,
                        textTransform: "uppercase",
                        letterSpacing: "0.05em",
                        color: "var(--text-secondary)",
                      }}
                    >
                      ORGANIZATION
                    </th>
                    <th
                      scope="col"
                      style={{
                        padding: "0.875rem 1.25rem",
                        fontSize: "0.75rem",
                        fontWeight: 700,
                        textTransform: "uppercase",
                        letterSpacing: "0.05em",
                        color: "var(--text-secondary)",
                      }}
                    >
                      DISCREPANCY
                    </th>
                    <th
                      scope="col"
                      style={{
                        padding: "0.875rem 1.25rem",
                        fontSize: "0.75rem",
                        fontWeight: 700,
                        textTransform: "uppercase",
                        letterSpacing: "0.05em",
                        color: "var(--text-secondary)",
                      }}
                    >
                      STATUS
                    </th>
                    <th
                      scope="col"
                      style={{
                        padding: "0.875rem 1.25rem",
                        fontSize: "0.75rem",
                        fontWeight: 700,
                        textTransform: "uppercase",
                        letterSpacing: "0.05em",
                        color: "var(--text-secondary)",
                      }}
                    >
                      DETECTED AT
                    </th>
                    <th
                      scope="col"
                      style={{
                        padding: "0.875rem 1.25rem",
                        fontSize: "0.75rem",
                        fontWeight: 700,
                        textTransform: "uppercase",
                        letterSpacing: "0.05em",
                        color: "var(--text-secondary)",
                        textAlign: "right",
                      }}
                    >
                      ACTIONS
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {filteredReconciliations.map((rec) => {
                    const isOpen = rec.status === "open";
                    return (
                      <tr
                        key={rec.id}
                        style={{
                          borderBottom: "1px solid var(--border-subtle)",
                          transition: "background-color 0.15s ease",
                        }}
                        onMouseEnter={(e) => {
                          e.currentTarget.style.backgroundColor = "var(--glass-surface-hover)";
                        }}
                        onMouseLeave={(e) => {
                          e.currentTarget.style.backgroundColor = "transparent";
                        }}
                      >
                        <td style={{ padding: "1rem 1.25rem", verticalAlign: "middle" }}>
                          <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
                            <div
                              style={{
                                width: 36,
                                height: 36,
                                borderRadius: 8,
                                background: "var(--surface-soft-blue)",
                                border: "1px solid rgba(56, 103, 245, 0.2)",
                                display: "flex",
                                alignItems: "center",
                                justifyContent: "center",
                                color: "var(--brand-primary)",
                                flexShrink: 0,
                              }}
                            >
                              <BuildingIcon size={18} />
                            </div>
                            <div>
                              <div style={{ fontWeight: 600, color: "var(--text-primary)", fontSize: "0.9375rem" }}>
                                {rec.organization_name || rec.organization_code || rec.organization}
                              </div>
                              <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginTop: "0.25rem", flexWrap: "wrap" }}>
                                {rec.organization_code && (
                                  <span
                                    style={{
                                      fontSize: "0.75rem",
                                      fontFamily: "var(--font-code)",
                                      color: "var(--text-muted)",
                                      background: "var(--glass-surface-sunken)",
                                      padding: "0.1rem 0.4rem",
                                      borderRadius: 4,
                                      border: "1px solid var(--border-subtle)",
                                    }}
                                  >
                                    {rec.organization_code}
                                  </span>
                                )}
                                {rec.subscription_plan_code && (
                                  <span style={{ fontSize: "0.75rem", color: "var(--brand-primary)", fontWeight: 500 }}>
                                    Plan: {rec.subscription_plan_code}
                                  </span>
                                )}
                              </div>
                            </div>
                          </div>
                        </td>
                        <td style={{ padding: "1rem 1.25rem", verticalAlign: "middle" }}>
                          <div style={{ marginBottom: "0.35rem" }}>
                            <span
                              style={{
                                display: "inline-flex",
                                alignItems: "center",
                                gap: "0.35rem",
                                padding: "0.2rem 0.55rem",
                                borderRadius: "4px",
                                fontSize: "0.75rem",
                                fontFamily: "var(--font-code)",
                                fontWeight: 600,
                                background: "var(--status-danger-bg)",
                                color: "var(--status-danger)",
                                border: "1px solid var(--status-danger-border)",
                              }}
                            >
                              <AlertCircleIcon size={12} />
                              {rec.issue_code}
                            </span>
                          </div>
                          <div style={{ fontSize: "0.8125rem", color: "var(--text-secondary)", fontWeight: 500, lineHeight: 1.4 }}>
                            {getIssueLabel(rec.issue_code)}
                          </div>
                        </td>
                        <td style={{ padding: "1rem 1.25rem", verticalAlign: "middle" }}>
                          <div>
                            <span className={`badge ${isOpen ? "badge-warning" : "badge-success"}`}>
                              <span className="badge-dot" />
                              {isOpen ? "Open" : "Resolved"}
                            </span>
                            {!isOpen && rec.resolved_by_email && (
                              <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginTop: "0.35rem" }}>
                                by {rec.resolved_by_email}
                              </div>
                            )}
                          </div>
                        </td>
                        <td style={{ padding: "1rem 1.25rem", verticalAlign: "middle" }}>
                          <div
                            style={{
                              display: "flex",
                              alignItems: "center",
                              gap: "0.4rem",
                              color: "var(--text-secondary)",
                              fontSize: "0.8125rem",
                              whiteSpace: "nowrap",
                            }}
                          >
                            <CalendarIcon size={14} style={{ color: "var(--text-muted)" }} />
                            <span>{new Date(rec.detected_at).toLocaleString()}</span>
                          </div>
                        </td>
                        <td style={{ padding: "1rem 1.25rem", textAlign: "right", verticalAlign: "middle" }}>
                          {isOpen ? (
                            <button
                              type="button"
                              onClick={() => handleOpenResolveModal(rec)}
                              className="btn btn-secondary"
                              style={{
                                fontSize: "0.8125rem",
                                padding: "0.4rem 0.85rem",
                                fontWeight: 600,
                                cursor: "pointer",
                              }}
                            >
                              Mark Resolved
                            </button>
                          ) : (
                            <span style={{ fontSize: "0.8125rem", color: "var(--text-muted)", fontStyle: "italic" }}>
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
              backgroundColor: "rgba(10, 14, 26, 0.65)",
              backdropFilter: "blur(4px)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              zIndex: 1000,
              padding: "1rem",
            }}
          >
            <div
              style={{
                background: "var(--glass-surface-elevated)",
                padding: "2rem",
                borderRadius: "0.75rem",
                width: "100%",
                maxWidth: "520px",
                border: "1px solid var(--border-glass)",
                boxShadow: "var(--shadow-lg)",
              }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1rem" }}>
                <h2 style={{ margin: 0, fontSize: "1.25rem", color: "var(--text-primary)", fontWeight: 700 }}>
                  Mark Discrepancy Resolved
                </h2>
                <button
                  type="button"
                  onClick={handleCloseResolveModal}
                  style={{
                    background: "transparent",
                    border: "none",
                    color: "var(--text-muted)",
                    cursor: "pointer",
                    padding: "0.25rem",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    borderRadius: "4px",
                  }}
                  aria-label="Close dialog"
                >
                  <CloseIcon size={18} />
                </button>
              </div>

              <p style={{ margin: "0 0 1.25rem 0", fontSize: "0.875rem", color: "var(--text-secondary)", lineHeight: 1.5 }}>
                This will mark issue{" "}
                <code
                  style={{
                    background: "var(--status-danger-bg)",
                    color: "var(--status-danger)",
                    border: "1px solid var(--status-danger-border)",
                    padding: "0.15rem 0.4rem",
                    borderRadius: "4px",
                    fontSize: "0.8125rem",
                    fontFamily: "var(--font-code)",
                  }}
                >
                  {resolvingItem.issue_code}
                </code>{" "}
                as resolved with an immutable audit log.
              </p>

              {modalError && (
                <div
                  style={{
                    padding: "0.75rem 1rem",
                    background: "var(--status-danger-bg)",
                    border: "1px solid var(--status-danger-border)",
                    borderRadius: "0.5rem",
                    color: "var(--status-danger)",
                    marginBottom: "1.25rem",
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
                      fontWeight: 600,
                      marginBottom: "0.5rem",
                      color: "var(--text-primary)",
                    }}
                  >
                    Resolution Reason <span style={{ color: "var(--status-danger)" }}>*</span>
                  </label>
                  <textarea
                    rows={4}
                    value={resolutionReason}
                    onChange={(e) => setResolutionReason(e.target.value)}
                    placeholder="Describe how this issue was verified or resolved (e.g. customer billing account restored)."
                    style={{
                      width: "100%",
                      padding: "0.75rem",
                      borderRadius: "0.5rem",
                      border: "1px solid var(--border-subtle)",
                      background: "var(--input-bg)",
                      color: "var(--text-primary)",
                      fontSize: "0.875rem",
                      boxSizing: "border-box",
                      resize: "vertical",
                      outline: "none",
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
                    style={{ padding: "0.5rem 1.25rem", fontSize: "0.875rem" }}
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

