/**
 * Platform Owner LMS Integration Reconciliation Page (Phase 5D).
 *
 * Route: /integration/reconciliation
 * Context Guard: platform_owner
 * Pattern: Reuses Prompt 17 flag-and-review reconciliation layout.
 */

import React, { useState, useEffect, useCallback } from "react";
import { Link } from "react-router-dom";
import { AppShell } from "../../components/AppShell.tsx";
import { LoadingSpinner } from "../../components/LoadingSpinner.tsx";
import { RotateCcwIcon } from "../../components/Icons.tsx";
import {
  integrationReconciliationApi,
  type IntegrationReconciliationIssue,
} from "../../api/integrationReconciliation.ts";

export const IntegrationReconciliationPage: React.FC = () => {
  const [issues, setIssues] = useState<IntegrationReconciliationIssue[]>([]);
  const [totalCount, setTotalCount] = useState<number>(0);
  const [statusFilter, setStatusFilter] = useState<string>("OPEN");
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [isTriggering, setIsTriggering] = useState<boolean>(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  // Resolution modal state
  const [resolvingIssue, setResolvingIssue] =
    useState<IntegrationReconciliationIssue | null>(null);
  const [resolutionNotes, setResolutionNotes] = useState<string>("");
  const [isSubmittingResolution, setIsSubmittingResolution] =
    useState<boolean>(false);
  const [modalError, setModalError] = useState<string | null>(null);

  const fetchIssues = useCallback(async () => {
    setIsLoading(true);
    setErrorMessage(null);
    try {
      const res = await integrationReconciliationApi.getIssues({
        status: statusFilter || undefined,
      });
      setIssues(res.results || []);
      setTotalCount(res.count || 0);
    } catch (err: unknown) {
      const msg =
        err && typeof err === "object" && "message" in err
          ? String((err as { message: string }).message)
          : "Failed to load LMS reconciliation issues.";
      setErrorMessage(msg);
    } finally {
      setIsLoading(false);
    }
  }, [statusFilter]);

  useEffect(() => {
    void fetchIssues();
  }, [fetchIssues]);

  const handleTriggerRun = async () => {
    setIsTriggering(true);
    setErrorMessage(null);
    setSuccessMessage(null);
    try {
      const res = await integrationReconciliationApi.triggerReconciliation();
      setSuccessMessage(
        `Reconciliation run completed. Detected ${res.detected_count} new anomaly(s). Total open: ${res.open_issues_count}.`
      );
      void fetchIssues();
    } catch (err: unknown) {
      const msg =
        err && typeof err === "object" && "message" in err
          ? String((err as { message: string }).message)
          : "Failed to run reconciliation job.";
      setErrorMessage(msg);
    } finally {
      setIsTriggering(false);
    }
  };

  const handleOpenResolve = (issue: IntegrationReconciliationIssue) => {
    setResolvingIssue(issue);
    setResolutionNotes("");
    setModalError(null);
  };

  const handleCloseResolve = () => {
    setResolvingIssue(null);
    setResolutionNotes("");
    setModalError(null);
  };

  const handleSubmitResolve = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!resolvingIssue) return;
    if (!resolutionNotes.trim()) {
      setModalError("Resolution notes are required for audit trail.");
      return;
    }

    setIsSubmittingResolution(true);
    setModalError(null);

    try {
      await integrationReconciliationApi.resolveIssue(
        resolvingIssue.id,
        resolutionNotes.trim()
      );
      setSuccessMessage(
        `Issue ${resolvingIssue.issue_code} was successfully marked resolved.`
      );
      handleCloseResolve();
      void fetchIssues();
    } catch (err: unknown) {
      const msg =
        err && typeof err === "object" && "message" in err
          ? String((err as { message: string }).message)
          : "Failed to resolve reconciliation issue.";
      setModalError(msg);
    } finally {
      setIsSubmittingResolution(false);
    }
  };

  return (
    <AppShell>
      <div style={{ maxWidth: "1400px", margin: "0 auto", padding: "2rem" }}>
        {/* Breadcrumb Navigation */}
        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", fontSize: "0.8125rem", color: "var(--text-muted)", marginBottom: "1.25rem", fontWeight: 500 }}>
          <Link to="/" style={{ color: "var(--text-muted)", textDecoration: "none", transition: "color 0.15s" }}>Platform Owner</Link>
          <span>/</span>
          <span>Infrastructure</span>
          <span>/</span>
          <span style={{ color: "var(--brand-primary)", fontWeight: 600 }}>LMS Identity Reconciliation</span>
        </div>

        {/* Header */}
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "flex-start",
            flexWrap: "wrap",
            gap: "1rem",
            marginBottom: "2rem",
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
              <RotateCcwIcon size={24} />
            </div>
            <div>
              <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
                <h1
                  className="heading-hero"
                  style={{
                    fontSize: "1.75rem",
                    fontWeight: 800,
                    letterSpacing: "-0.02em",
                    color: "var(--text-primary)",
                    margin: 0,
                  }}
                >
                  LMS Identity Reconciliation
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
                  {totalCount} Anomaly Records
                </span>
              </div>
              <p
                style={{
                  fontSize: "0.9375rem",
                  color: "var(--text-secondary)",
                  marginTop: "0.25rem",
                  marginBottom: 0,
                }}
              >
                Audit and reconcile external LMS mappings against Envisage identity records.
              </p>
            </div>
          </div>

          <div style={{ display: "flex", gap: "0.75rem", alignItems: "center" }}>
            <button
              id="trigger-lms-reconciliation-btn"
              type="button"
              className="btn btn-gradient"
              onClick={() => void handleTriggerRun()}
              disabled={isTriggering}
            >
              <RotateCcwIcon size={16} />
              {isTriggering ? "Running Audit..." : "Run LMS Reconciliation"}
            </button>
          </div>
        </div>

        {/* Alerts */}
        {errorMessage && (
          <div
            className="alert alert-danger"
            style={{ marginBottom: "1rem", fontSize: "0.875rem" }}
          >
            {errorMessage}
          </div>
        )}
        {successMessage && (
          <div
            className="alert alert-success"
            style={{ marginBottom: "1rem", fontSize: "0.875rem" }}
          >
            {successMessage}
          </div>
        )}

        {/* Filters */}
        <div
          style={{
            display: "flex",
            gap: "1rem",
            alignItems: "center",
            marginBottom: "1rem",
            flexWrap: "wrap",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
            <label
              htmlFor="status-filter"
              style={{
                fontSize: "0.8125rem",
                fontWeight: 600,
                color: "var(--text-secondary)",
              }}
            >
              Status:
            </label>
            <select
              id="status-filter"
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              style={{
                padding: "0.4rem 0.75rem",
                borderRadius: "6px",
                border: "1px solid var(--border-subtle)",
                background: "var(--surface)",
                color: "var(--text-primary)",
                fontSize: "0.8125rem",
              }}
            >
              <option value="">All Statuses</option>
              <option value="OPEN">Open Anomalies</option>
              <option value="RESOLVED">Resolved</option>
            </select>
          </div>
          <span style={{ fontSize: "0.8125rem", color: "var(--text-muted)" }}>
            Found {totalCount} record(s)
          </span>
        </div>

        {/* Content Table */}
        {isLoading ? (
          <LoadingSpinner label="Loading LMS reconciliation records..." />
        ) : issues.length === 0 ? (
          <div
            style={{
              padding: "3rem",
              textAlign: "center",
              background: "var(--glass-surface)",
              borderRadius: "8px",
              border: "1px solid var(--border-subtle)",
              color: "var(--text-muted)",
            }}
          >
            <p style={{ margin: 0, fontSize: "1rem", fontWeight: 500 }}>
              No reconciliation anomalies found.
            </p>
            <p style={{ margin: "0.5rem 0 0 0", fontSize: "0.8125rem" }}>
              Run LMS reconciliation to scan for deactivated users, retired
              tenants, or duplicate mappings.
            </p>
          </div>
        ) : (
          <div
            style={{
              overflowX: "auto",
              background: "var(--surface)",
              borderRadius: "8px",
              border: "1px solid var(--border-subtle)",
            }}
          >
            <table
              id="lms-reconciliation-table"
              style={{
                width: "100%",
                borderCollapse: "collapse",
                fontSize: "0.8125rem",
                textAlign: "left",
              }}
            >
              <thead>
                <tr
                  style={{
                    borderBottom: "1px solid var(--border-subtle)",
                    background: "var(--surface-hover)",
                  }}
                >
                  <th style={{ padding: "0.75rem 1rem" }}>Detected</th>
                  <th style={{ padding: "0.75rem 1rem" }}>Issue Code</th>
                  <th style={{ padding: "0.75rem 1rem" }}>Instance</th>
                  <th style={{ padding: "0.75rem 1rem" }}>Subject</th>
                  <th style={{ padding: "0.75rem 1rem" }}>Reason / Details</th>
                  <th style={{ padding: "0.75rem 1rem" }}>Status</th>
                  <th style={{ padding: "0.75rem 1rem" }}>Action</th>
                </tr>
              </thead>
              <tbody>
                {issues.map((issue) => (
                  <tr
                    key={issue.id}
                    style={{
                      borderBottom: "1px solid var(--border-subtle)",
                    }}
                  >
                    <td
                      style={{
                        padding: "0.75rem 1rem",
                        whiteSpace: "nowrap",
                        color: "var(--text-muted)",
                      }}
                    >
                      {new Date(issue.detected_at).toLocaleString()}
                    </td>
                    <td style={{ padding: "0.75rem 1rem" }}>
                      <span
                        style={{
                          padding: "0.2rem 0.5rem",
                          borderRadius: "4px",
                          fontSize: "0.75rem",
                          fontWeight: 700,
                          background:
                            issue.status === "OPEN"
                              ? "var(--status-danger-bg)"
                              : "var(--glass-surface)",
                          color:
                            issue.status === "OPEN"
                              ? "var(--status-danger)"
                              : "var(--text-muted)",
                          border: `1px solid ${
                            issue.status === "OPEN"
                              ? "var(--status-danger-border)"
                              : "var(--border-subtle)"
                          }`,
                        }}
                      >
                        {issue.issue_code}
                      </span>
                    </td>
                    <td style={{ padding: "0.75rem 1rem" }}>
                      <div>{issue.instance_label || "Instance"}</div>
                      <div style={{ fontSize: "0.6875rem", color: "var(--text-muted)" }}>
                        {issue.connector_code || issue.instance}
                      </div>
                    </td>
                    <td style={{ padding: "0.75rem 1rem" }}>
                      <span style={{ fontWeight: 600 }}>{issue.subject_type}:</span>{" "}
                      <code>{issue.subject_id}</code>
                    </td>
                    <td style={{ padding: "0.75rem 1rem", maxWidth: 320 }}>
                      <div
                        style={{
                          overflow: "hidden",
                          textOverflow: "ellipsis",
                          whiteSpace: "normal",
                          color: "var(--text-secondary)",
                        }}
                      >
                        {String(issue.details?.reason || JSON.stringify(issue.details))}
                      </div>
                    </td>
                    <td style={{ padding: "0.75rem 1rem" }}>
                      <span
                        style={{
                          padding: "0.2rem 0.5rem",
                          borderRadius: "4px",
                          fontSize: "0.75rem",
                          fontWeight: 600,
                          background:
                            issue.status === "OPEN"
                              ? "var(--status-warning-bg)"
                              : "var(--status-success-bg)",
                          color:
                            issue.status === "OPEN"
                              ? "var(--status-warning)"
                              : "var(--status-success)",
                        }}
                      >
                        {issue.status}
                      </span>
                    </td>
                    <td style={{ padding: "0.75rem 1rem" }}>
                      {issue.status === "OPEN" ? (
                        <button
                          type="button"
                          className="btn-secondary"
                          onClick={() => handleOpenResolve(issue)}
                          style={{
                            padding: "0.3rem 0.65rem",
                            fontSize: "0.75rem",
                            fontWeight: 600,
                          }}
                        >
                          Resolve
                        </button>
                      ) : (
                        <span style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
                          Resolved
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {/* Resolution Modal */}
        {resolvingIssue && (
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
          >
            <div
              style={{
                background: "var(--surface)",
                borderRadius: "8px",
                border: "1px solid var(--border-subtle)",
                padding: "1.5rem",
                width: "100%",
                maxWidth: 480,
                boxShadow: "0 8px 32px rgba(0, 0, 0, 0.4)",
              }}
            >
              <h3
                style={{
                  margin: "0 0 0.5rem 0",
                  fontSize: "1.25rem",
                  color: "var(--text-primary)",
                }}
              >
                Resolve Reconciliation Issue
              </h3>
              <p
                style={{
                  fontSize: "0.8125rem",
                  color: "var(--text-secondary)",
                  margin: "0 0 1rem 0",
                }}
              >
                Audited action for <strong>{resolvingIssue.issue_code}</strong> (
                {resolvingIssue.subject_type}: {resolvingIssue.subject_id}).
              </p>

              {modalError && (
                <div
                  className="alert alert-danger"
                  style={{ marginBottom: "1rem", fontSize: "0.8125rem" }}
                >
                  {modalError}
                </div>
              )}

              <form onSubmit={handleSubmitResolve}>
                <div style={{ marginBottom: "1rem" }}>
                  <label
                    htmlFor="resolution-notes-input"
                    style={{
                      display: "block",
                      fontSize: "0.8125rem",
                      fontWeight: 600,
                      marginBottom: "0.35rem",
                      color: "var(--text-primary)",
                    }}
                  >
                    Resolution Notes (Mandatory Audit Evidence):
                  </label>
                  <textarea
                    id="resolution-notes-input"
                    rows={4}
                    required
                    value={resolutionNotes}
                    onChange={(e) => setResolutionNotes(e.target.value)}
                    placeholder="Describe how the mapping or identity mismatch was resolved in LMS or Envisage..."
                    style={{
                      width: "100%",
                      borderRadius: "6px",
                      border: "1px solid var(--border-subtle)",
                      background: "var(--glass-surface)",
                      color: "var(--text-primary)",
                      padding: "0.5rem",
                      fontSize: "0.8125rem",
                    }}
                  />
                </div>

                <div
                  style={{
                    display: "flex",
                    justifyContent: "flex-end",
                    gap: "0.75rem",
                  }}
                >
                  <button
                    type="button"
                    className="btn-secondary"
                    onClick={handleCloseResolve}
                    disabled={isSubmittingResolution}
                    style={{ padding: "0.4rem 0.85rem", fontSize: "0.8125rem" }}
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    className="btn-primary"
                    disabled={isSubmittingResolution}
                    style={{ padding: "0.4rem 0.85rem", fontSize: "0.8125rem" }}
                  >
                    {isSubmittingResolution ? "Submitting..." : "Confirm Resolution"}
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
