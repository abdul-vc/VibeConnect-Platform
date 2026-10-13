/**
 * Phase 3D & 3E: Bulk Data Import, Validation & Reconciliation Workspace.
 *
 * Supports drag-and-drop CSV/JSON upload, staged row validation,
 * row-level error reporting, progress polling, atomic/resilient commit,
 * and comprehensive reconciliation reporting with one-click retry of recoverable failures.
 */

import React, { useCallback, useEffect, useRef, useState } from "react";
import { bulkImportApi } from "../../api/bulkImport.ts";
import { organizationsApi } from "../../api/organizations.ts";
import type {
  BulkImportJob,
  BulkImportReconciliationReport,
  BulkImportRow,
  OrganizationListItem,
} from "../../api/types.ts";
import { AppShell } from "../../components/AppShell.tsx";
import {
  AlertCircleIcon,
  CheckCircleIcon,
  PlusIcon,
  RefreshIcon,
  UploadIcon,
} from "../../components/Icons.tsx";
import { useAuth } from "../../context/AuthContext.tsx";

export const BulkImportPage: React.FC = () => {
  const { user } = useAuth();
  const [organizations, setOrganizations] = useState<readonly OrganizationListItem[]>([]);
  const [selectedOrgId, setSelectedOrgId] = useState<string>("");

  const [fileContent, setFileContent] = useState<string>("");
  const [fileName, setFileName] = useState<string>("");
  const [fileFormat, setFileFormat] = useState<"csv" | "json">("csv");
  const [isDragging, setIsDragging] = useState<boolean>(false);

  const [activeJob, setActiveJob] = useState<BulkImportJob | null>(null);
  const [rows, setRows] = useState<readonly BulkImportRow[]>([]);
  const [filterValidationState, setFilterValidationState] = useState<string>("");

  const [reconciliation, setReconciliation] = useState<BulkImportReconciliationReport | null>(null);
  const [activeTab, setActiveTab] = useState<"rows" | "reconciliation">("rows");

  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [isActionLoading, setIsActionLoading] = useState<boolean>(false);
  const [generalError, setGeneralError] = useState<string | null>(null);
  const [successBanner, setSuccessBanner] = useState<string | null>(null);

  const pollTimerRef = useRef<NodeJS.Timeout | null>(null);

  // Load organizations for Platform Owners or set from active tenant context
  useEffect(() => {
    if (user?.active_context?.organization?.id) {
      setSelectedOrgId(user.active_context.organization.id);
    } else if (user?.is_platform_owner) {
      void organizationsApi.list({ page_size: 100 }).then((res) => {
        setOrganizations(res.results);
        if (res.results.length > 0 && !selectedOrgId) {
          setSelectedOrgId(res.results[0].id);
        }
      });
    }
  }, [user]);

  // Load rows for the active job
  const fetchRows = useCallback(async (jobId: string, stateFilter?: string) => {
    try {
      const res = await bulkImportApi.listRows(jobId, {
        validation_state: stateFilter || undefined,
        page_size: 100,
      });
      setRows(res.results);
    } catch {
      // Ignored non-critical failure
    }
  }, []);

  // Load reconciliation report
  const fetchReconciliation = useCallback(async (jobId: string) => {
    try {
      const res = await bulkImportApi.getReconciliation(jobId);
      setReconciliation(res);
    } catch {
      // Non-critical
    }
  }, []);

  // Poll job status if in progress
  useEffect(() => {
    if (!activeJob) return;

    const isPendingOrCommitting =
      activeJob.status === "validating" || activeJob.status === "committing";

    if (isPendingOrCommitting) {
      pollTimerRef.current = setTimeout(async () => {
        try {
          const refreshed = await bulkImportApi.getJob(activeJob.id);
          setActiveJob(refreshed);
          void fetchRows(refreshed.id, filterValidationState);
          if (refreshed.status === "completed" || refreshed.status === "failed") {
            void fetchReconciliation(refreshed.id);
          }
        } catch {
          // Keep previous state on poll error
        }
      }, 2000);
    }

    return () => {
      if (pollTimerRef.current) {
        clearTimeout(pollTimerRef.current);
      }
    };
  }, [activeJob, fetchRows, fetchReconciliation, filterValidationState]);

  const handleFileDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);

    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      const file = e.dataTransfer.files[0];
      handleFileSelected(file);
    }
  };

  const handleFileSelected = (file: File) => {
    setFileName(file.name);
    const format = file.name.endsWith(".json") ? "json" : "csv";
    setFileFormat(format);

    const reader = new FileReader();
    reader.onload = (e) => {
      const content = e.target?.result as string;
      setFileContent(content);
    };
    reader.readAsText(file);
  };

  const handleStageJob = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedOrgId) {
      setGeneralError("Please select a target organization.");
      return;
    }
    if (!fileContent.trim()) {
      setGeneralError("Please select or drop a valid file.");
      return;
    }

    setIsLoading(true);
    setGeneralError(null);
    setSuccessBanner(null);

    try {
      const idempotencyKey = `bulk-import-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
      const job = await bulkImportApi.createJob({
        organization_id: selectedOrgId,
        idempotency_key: idempotencyKey,
        raw_content: fileContent,
        content_type: fileFormat,
      });

      setActiveJob(job);
      void fetchRows(job.id);
      void fetchReconciliation(job.id);
      setActiveTab("rows");
    } catch (err: unknown) {
      const errorObj = err as { data?: { detail?: string } };
      setGeneralError(errorObj?.data?.detail || "Failed to stage import job.");
    } finally {
      setIsLoading(false);
    }
  };

  const handleCommitJob = async () => {
    if (!activeJob) return;
    setIsActionLoading(true);
    setGeneralError(null);

    try {
      const committed = await bulkImportApi.commitJob(activeJob.id);
      setActiveJob(committed);
      void fetchRows(committed.id, filterValidationState);
      void fetchReconciliation(committed.id);
      if (committed.status === "completed") {
        setSuccessBanner(`Successfully committed ${committed.committed_rows} rows.`);
      }
    } catch (err: unknown) {
      const errorObj = err as { data?: { detail?: string } };
      setGeneralError(errorObj?.data?.detail || "Commit execution encountered an error.");
    } finally {
      setIsActionLoading(false);
    }
  };

  const handleRetryJob = async () => {
    if (!activeJob) return;
    setIsActionLoading(true);
    setGeneralError(null);

    try {
      const retried = await bulkImportApi.retryJob(activeJob.id);
      setActiveJob(retried);
      void fetchRows(retried.id, filterValidationState);
      void fetchReconciliation(retried.id);
    } catch (err: unknown) {
      const errorObj = err as { data?: { detail?: string } };
      setGeneralError(errorObj?.data?.detail || "Retry execution encountered an error.");
    } finally {
      setIsActionLoading(false);
    }
  };

  const resetWorkspace = () => {
    setActiveJob(null);
    setRows([]);
    setReconciliation(null);
    setActiveTab("rows");
    setFileContent("");
    setFileName("");
    setGeneralError(null);
    setSuccessBanner(null);
  };

  return (
    <AppShell>
      <div style={{ maxWidth: "1080px", margin: "0 auto", display: "flex", flexDirection: "column", gap: "1.75rem" }}>
        {/* Header */}
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: "1rem" }}>
          <div>
            <h1 className="heading-hero" style={{ margin: 0, fontSize: "1.75rem" }}>
              Bulk User & Membership Import
            </h1>
            <p className="text-body" style={{ marginTop: "0.35rem", maxWidth: "700px" }}>
              Upload and stage batch user accounts with automated schema validation, duplicate detection, and resilient transactional commits.
            </p>
          </div>
          {activeJob && (
            <button
              type="button"
              className="btn btn-secondary"
              onClick={resetWorkspace}
            >
              <PlusIcon size={16} />
              New Import Job
            </button>
          )}
        </div>

        {generalError && (
          <div className="alert-banner alert-banner-error" role="alert" style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
            <AlertCircleIcon size={18} />
            <span>{generalError}</span>
          </div>
        )}

        {successBanner && (
          <div className="alert-banner alert-banner-success" role="status" style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
            <CheckCircleIcon size={18} />
            <span>{successBanner}</span>
          </div>
        )}

        {!activeJob ? (
          /* Step 1: Upload and Configuration */
          <div className="glass-panel" style={{ padding: "2rem", display: "flex", flexDirection: "column", gap: "1.5rem" }}>
            {/* Organization Selector */}
            {user?.is_platform_owner && !user?.active_context?.organization && (
              <div>
                <label htmlFor="targetOrg" className="field-label" style={{ display: "block", marginBottom: "0.35rem" }}>
                  Target Organization <span style={{ color: "var(--status-error)" }}>*</span>
                </label>
                <select
                  id="targetOrg"
                  className="input-field"
                  value={selectedOrgId}
                  onChange={(e) => setSelectedOrgId(e.target.value)}
                  style={{ maxWidth: "400px" }}
                >
                  <option value="">Select Organization...</option>
                  {organizations.map((org) => (
                    <option key={org.id} value={org.id}>
                      {org.name} ({org.code})
                    </option>
                  ))}
                </select>
              </div>
            )}

            {/* Drop Zone */}
            <div
              onDragOver={(e) => {
                e.preventDefault();
                setIsDragging(true);
              }}
              onDragLeave={() => setIsDragging(false)}
              onDrop={handleFileDrop}
              style={{
                border: isDragging
                  ? "2px dashed var(--brand-primary, #6366f1)"
                  : "2px dashed var(--border-color, #334155)",
                borderRadius: "0.75rem",
                padding: "3rem 1.5rem",
                textAlign: "center",
                backgroundColor: isDragging ? "rgba(99, 102, 241, 0.05)" : "rgba(255, 255, 255, 0.01)",
                cursor: "pointer",
                transition: "all 0.2s ease-in-out",
              }}
              onClick={() => document.getElementById("fileInput")?.click()}
            >
              <input
                id="fileInput"
                type="file"
                accept=".csv,.json"
                style={{ display: "none" }}
                onChange={(e) => {
                  if (e.target.files && e.target.files.length > 0) {
                    handleFileSelected(e.target.files[0]);
                  }
                }}
              />
              <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: "0.75rem" }}>
                <div
                  style={{
                    width: "48px",
                    height: "48px",
                    borderRadius: "50%",
                    backgroundColor: "rgba(99, 102, 241, 0.1)",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    color: "var(--brand-primary, #6366f1)",
                  }}
                >
                  <UploadIcon size={24} />
                </div>
                <div>
                  <p style={{ margin: 0, fontWeight: 600, color: "var(--text-primary)" }}>
                    {fileName ? fileName : "Drag and drop your CSV or JSON file here"}
                  </p>
                  <p style={{ margin: "0.25rem 0 0 0", fontSize: "0.8125rem", color: "var(--text-muted)" }}>
                    Supported formats: CSV, JSON (up to 1,000 users per job)
                  </p>
                </div>
              </div>
            </div>

            {/* Template Advice */}
            <div
              style={{
                padding: "1rem",
                backgroundColor: "rgba(255, 255, 255, 0.02)",
                borderRadius: "0.5rem",
                border: "1px solid var(--border-color, #334155)",
                fontSize: "0.8125rem",
                color: "var(--text-secondary)",
              }}
            >
              <strong>Required Schema:</strong> Expected column headers or JSON object keys include <code>email</code> (required), <code>full_name</code> (optional), <code>membership_type</code> (member or tenant_admin), and <code>role_code</code> (optional).
            </div>

            <div style={{ display: "flex", justifyContent: "flex-end" }}>
              <button
                type="button"
                className="btn btn-primary"
                onClick={handleStageJob}
                disabled={isLoading || !fileContent.trim()}
              >
                {isLoading ? "Validating & Staging..." : "Upload & Validate Staged Rows"}
              </button>
            </div>
          </div>
        ) : (
          /* Step 2: Job Monitor, Progress & Reconciliation */
          <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }}>
            {/* Job Summary Banner */}
            <div className="glass-panel" style={{ padding: "1.5rem" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "1rem" }}>
                <div>
                  <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                    <span style={{ fontSize: "0.8125rem", color: "var(--text-muted)" }}>Job ID:</span>
                    <span className="code-pill" style={{ fontFamily: "monospace" }}>{activeJob.id}</span>
                    <span
                      style={{
                        padding: "0.2rem 0.5rem",
                        borderRadius: "0.25rem",
                        fontSize: "0.75rem",
                        fontWeight: 600,
                        textTransform: "uppercase",
                        backgroundColor:
                          activeJob.status === "completed"
                            ? "rgba(16, 185, 129, 0.15)"
                            : activeJob.status === "failed"
                            ? "rgba(239, 68, 68, 0.15)"
                            : "rgba(99, 102, 241, 0.15)",
                        color:
                          activeJob.status === "completed"
                            ? "var(--status-success, #10b981)"
                            : activeJob.status === "failed"
                            ? "var(--status-error, #ef4444)"
                            : "var(--brand-primary, #6366f1)",
                      }}
                    >
                      {activeJob.status}
                    </span>
                  </div>
                  <p style={{ margin: "0.35rem 0 0 0", fontSize: "0.875rem", color: "var(--text-secondary)" }}>
                    Target Organization: <strong>{activeJob.organization_name || activeJob.organization_code || "Target"}</strong>
                  </p>
                </div>

                <div style={{ display: "flex", gap: "0.75rem", alignItems: "center" }}>
                  {activeJob.status === "validated" && activeJob.valid_rows > 0 && (
                    <button
                      type="button"
                      className="btn btn-primary"
                      onClick={handleCommitJob}
                      disabled={isActionLoading}
                    >
                      Commit {activeJob.valid_rows} Valid Rows
                    </button>
                  )}
                  {activeJob.failed_rows > 0 && (
                    <button
                      type="button"
                      className="btn btn-secondary"
                      onClick={handleRetryJob}
                      disabled={Boolean(isActionLoading || (reconciliation && !reconciliation.can_retry))}
                      title={reconciliation && !reconciliation.can_retry ? "No recoverable rows found. Terminal failures cannot be retried." : ""}
                    >
                      <RefreshIcon size={16} />
                      Retry Recoverable Failures
                    </button>
                  )}
                </div>
              </div>

              {/* Progress Counters Grid */}
              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))",
                  gap: "1rem",
                  marginTop: "1.5rem",
                  paddingTop: "1.5rem",
                  borderTop: "1px solid var(--border-color, #334155)",
                }}
              >
                <div>
                  <div style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>Total Rows</div>
                  <div style={{ fontSize: "1.5rem", fontWeight: 700, color: "var(--text-primary)" }}>{activeJob.total_rows}</div>
                </div>
                <div>
                  <div style={{ fontSize: "0.75rem", color: "var(--status-success, #10b981)" }}>Valid (Staged)</div>
                  <div style={{ fontSize: "1.5rem", fontWeight: 700, color: "var(--status-success, #10b981)" }}>{activeJob.valid_rows}</div>
                </div>
                <div>
                  <div style={{ fontSize: "0.75rem", color: "var(--status-error, #ef4444)" }}>Invalid (Rejected)</div>
                  <div style={{ fontSize: "1.5rem", fontWeight: 700, color: "var(--status-error, #ef4444)" }}>{activeJob.invalid_rows}</div>
                </div>
                <div>
                  <div style={{ fontSize: "0.75rem", color: "var(--brand-primary, #6366f1)" }}>Committed</div>
                  <div style={{ fontSize: "1.5rem", fontWeight: 700, color: "var(--brand-primary, #6366f1)" }}>{activeJob.committed_rows}</div>
                </div>
                <div>
                  <div style={{ fontSize: "0.75rem", color: "var(--status-warning, #f59e0b)" }}>Failed on Commit</div>
                  <div style={{ fontSize: "1.5rem", fontWeight: 700, color: "var(--status-warning, #f59e0b)" }}>{activeJob.failed_rows}</div>
                </div>
              </div>
            </div>

            {/* Navigation Tabs: Staged Rows vs Reconciliation Report */}
            <div style={{ display: "flex", gap: "0.5rem", borderBottom: "1px solid var(--border-color, #334155)", paddingBottom: "0.5rem" }}>
              <button
                type="button"
                className={`btn ${activeTab === "rows" ? "btn-primary" : "btn-secondary"}`}
                onClick={() => setActiveTab("rows")}
                style={{ padding: "0.4rem 1rem", fontSize: "0.875rem" }}
              >
                Staged Rows ({rows.length})
              </button>
              <button
                type="button"
                className={`btn ${activeTab === "reconciliation" ? "btn-primary" : "btn-secondary"}`}
                onClick={() => {
                  setActiveTab("reconciliation");
                  void fetchReconciliation(activeJob.id);
                }}
                style={{ padding: "0.4rem 1rem", fontSize: "0.875rem" }}
              >
                Reconciliation & Recovery
              </button>
            </div>

            {activeTab === "rows" ? (
              /* Filter and Rows Table */
              <div className="glass-panel" style={{ padding: "1.5rem" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1rem", flexWrap: "wrap", gap: "0.5rem" }}>
                  <h2 style={{ fontSize: "1rem", margin: 0, fontWeight: 600 }}>Staged Row Details</h2>
                  <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
                    {["", "valid", "invalid", "committed", "failed"].map((st) => (
                      <button
                        key={st}
                        type="button"
                        className={`btn ${filterValidationState === st ? "btn-primary" : "btn-secondary"}`}
                        style={{ fontSize: "0.75rem", padding: "0.25rem 0.65rem" }}
                        onClick={() => {
                          setFilterValidationState(st);
                          void fetchRows(activeJob.id, st);
                        }}
                      >
                        {st === "" ? "All" : st.charAt(0).toUpperCase() + st.slice(1)}
                      </button>
                    ))}
                  </div>
                </div>

                {rows.length === 0 ? (
                  <div style={{ textAlign: "center", padding: "2rem", color: "var(--text-muted)" }}>
                    No rows matching the selected filter.
                  </div>
                ) : (
                  <div style={{ overflowX: "auto" }}>
                    <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.8125rem" }}>
                      <thead>
                        <tr style={{ borderBottom: "1px solid var(--border-color, #334155)", textAlign: "left" }}>
                          <th style={{ padding: "0.75rem 0.5rem" }}>#</th>
                          <th style={{ padding: "0.75rem 0.5rem" }}>Email</th>
                          <th style={{ padding: "0.75rem 0.5rem" }}>Full Name</th>
                          <th style={{ padding: "0.75rem 0.5rem" }}>Role/Membership</th>
                          <th style={{ padding: "0.75rem 0.5rem" }}>State</th>
                          <th style={{ padding: "0.75rem 0.5rem" }}>Diagnostics</th>
                        </tr>
                      </thead>
                      <tbody>
                        {rows.map((row) => (
                          <tr key={row.id} style={{ borderBottom: "1px solid rgba(255, 255, 255, 0.05)" }}>
                            <td style={{ padding: "0.75rem 0.5rem", color: "var(--text-muted)" }}>{row.row_number}</td>
                            <td style={{ padding: "0.75rem 0.5rem", fontWeight: 500 }}>{row.payload_ref.email || "-"}</td>
                            <td style={{ padding: "0.75rem 0.5rem" }}>{row.payload_ref.full_name || "-"}</td>
                            <td style={{ padding: "0.75rem 0.5rem" }}>
                              {row.payload_ref.role_code ? `${row.payload_ref.role_code} (${row.payload_ref.membership_type})` : row.payload_ref.membership_type || "member"}
                            </td>
                            <td style={{ padding: "0.75rem 0.5rem" }}>
                              <span
                                style={{
                                  display: "inline-block",
                                  padding: "0.2rem 0.5rem",
                                  borderRadius: "0.25rem",
                                  fontSize: "0.7rem",
                                  fontWeight: 600,
                                  textTransform: "uppercase",
                                  background:
                                    row.validation_state === "valid"
                                      ? "rgba(16, 185, 129, 0.15)"
                                      : row.validation_state === "committed"
                                      ? "rgba(99, 102, 241, 0.15)"
                                      : "rgba(239, 68, 68, 0.15)",
                                  color:
                                    row.validation_state === "valid"
                                      ? "var(--status-success, #10b981)"
                                      : row.validation_state === "committed"
                                      ? "var(--brand-primary, #6366f1)"
                                      : "var(--status-error, #ef4444)",
                                }}
                              >
                                {row.validation_state}
                              </span>
                            </td>
                            <td style={{ padding: "0.75rem 0.5rem", color: row.error_message ? "var(--status-error)" : "var(--text-muted)" }}>
                              {row.error_message || "-"}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            ) : (
              /* Phase 3E: Reconciliation & Recovery View */
              <div className="glass-panel" style={{ padding: "1.5rem", display: "flex", flexDirection: "column", gap: "1.5rem" }}>
                <div>
                  <h2 style={{ fontSize: "1.125rem", margin: "0 0 0.35rem 0", fontWeight: 700 }}>
                    Reconciliation & Recovery Analysis
                  </h2>
                  <p style={{ margin: 0, fontSize: "0.8125rem", color: "var(--text-muted)" }}>
                    Deep reconciliation cross-references staged rows against live identities, memberships, and pending invitations.
                  </p>
                </div>

                {reconciliation ? (
                  <>
                    {/* Recovery KPI Cards */}
                    <div
                      style={{
                        display: "grid",
                        gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))",
                        gap: "1rem",
                      }}
                    >
                      <div style={{ padding: "1rem", borderRadius: "8px", background: "rgba(16, 185, 129, 0.08)", border: "1px solid rgba(16, 185, 129, 0.2)" }}>
                        <div style={{ fontSize: "0.75rem", color: "rgb(16, 185, 129)", fontWeight: 600 }}>Committed Successfully</div>
                        <div style={{ fontSize: "1.5rem", fontWeight: 700, color: "var(--text-primary)", marginTop: "0.25rem" }}>
                          {reconciliation.committed_rows} / {reconciliation.total_rows}
                        </div>
                      </div>
                      <div style={{ padding: "1rem", borderRadius: "8px", background: "rgba(245, 158, 11, 0.08)", border: "1px solid rgba(245, 158, 11, 0.2)" }}>
                        <div style={{ fontSize: "0.75rem", color: "rgb(245, 158, 11)", fontWeight: 600 }}>Recoverable (Retryable)</div>
                        <div style={{ fontSize: "1.5rem", fontWeight: 700, color: "var(--text-primary)", marginTop: "0.25rem" }}>
                          {reconciliation.recoverable_failures_count}
                        </div>
                      </div>
                      <div style={{ padding: "1rem", borderRadius: "8px", background: "rgba(239, 68, 68, 0.08)", border: "1px solid rgba(239, 68, 68, 0.2)" }}>
                        <div style={{ fontSize: "0.75rem", color: "rgb(239, 68, 68)", fontWeight: 600 }}>Terminal (Non-Retryable)</div>
                        <div style={{ fontSize: "1.5rem", fontWeight: 700, color: "var(--text-primary)", marginTop: "0.25rem" }}>
                          {reconciliation.terminal_failures_count}
                        </div>
                      </div>
                    </div>

                    {/* Taxonomy Breakdown */}
                    {Object.keys(reconciliation.error_code_breakdown).length > 0 && (
                      <div style={{ padding: "1rem", background: "var(--bg-app)", borderRadius: "8px", border: "1px solid var(--border-color, #334155)" }}>
                        <div style={{ fontSize: "0.8125rem", fontWeight: 600, marginBottom: "0.75rem" }}>Error Code Breakdown</div>
                        <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem" }}>
                          {Object.entries(reconciliation.error_code_breakdown).map(([code, count]) => (
                            <span
                              key={code}
                              style={{
                                padding: "0.25rem 0.6rem",
                                borderRadius: "4px",
                                background: "rgba(255, 255, 255, 0.05)",
                                border: "1px solid var(--border-color, #334155)",
                                fontSize: "0.75rem",
                                fontFamily: "monospace",
                              }}
                            >
                              {code}: <strong>{count}</strong>
                            </span>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Reconciliation Table */}
                    <div style={{ overflowX: "auto" }}>
                      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.8125rem" }}>
                        <thead>
                          <tr style={{ borderBottom: "1px solid var(--border-color, #334155)", textAlign: "left" }}>
                            <th style={{ padding: "0.75rem 0.5rem" }}>#</th>
                            <th style={{ padding: "0.75rem 0.5rem" }}>Email</th>
                            <th style={{ padding: "0.75rem 0.5rem" }}>Status</th>
                            <th style={{ padding: "0.75rem 0.5rem" }}>Classification</th>
                            <th style={{ padding: "0.75rem 0.5rem" }}>Error Code & Diagnostic</th>
                          </tr>
                        </thead>
                        <tbody>
                          {reconciliation.rows.map((row) => (
                            <tr key={row.id} style={{ borderBottom: "1px solid rgba(255, 255, 255, 0.05)" }}>
                              <td style={{ padding: "0.75rem 0.5rem", color: "var(--text-muted)" }}>{row.row_number}</td>
                              <td style={{ padding: "0.75rem 0.5rem", fontWeight: 500 }}>{row.email || "-"}</td>
                              <td style={{ padding: "0.75rem 0.5rem" }}>
                                <span
                                  style={{
                                    display: "inline-block",
                                    padding: "0.2rem 0.4rem",
                                    borderRadius: "4px",
                                    fontSize: "0.7rem",
                                    fontWeight: 600,
                                    textTransform: "uppercase",
                                    background:
                                      row.validation_state === "committed"
                                        ? "rgba(16, 185, 129, 0.15)"
                                        : "rgba(239, 68, 68, 0.15)",
                                    color:
                                      row.validation_state === "committed"
                                        ? "var(--status-success, #10b981)"
                                        : "var(--status-error, #ef4444)",
                                  }}
                                >
                                  {row.validation_state}
                                </span>
                              </td>
                              <td style={{ padding: "0.75rem 0.5rem" }}>
                                {row.validation_state === "committed" ? (
                                  <span style={{ color: "var(--status-success, #10b981)", fontWeight: 500 }}>Committed</span>
                                ) : row.is_recoverable ? (
                                  <span
                                    style={{
                                      padding: "0.2rem 0.4rem",
                                      borderRadius: "4px",
                                      background: "rgba(245, 158, 11, 0.15)",
                                      color: "rgb(245, 158, 11)",
                                      fontWeight: 600,
                                      fontSize: "0.7rem",
                                    }}
                                  >
                                    Recoverable (Retryable)
                                  </span>
                                ) : (
                                  <span
                                    style={{
                                      padding: "0.2rem 0.4rem",
                                      borderRadius: "4px",
                                      background: "rgba(239, 68, 68, 0.15)",
                                      color: "rgb(239, 68, 68)",
                                      fontWeight: 600,
                                      fontSize: "0.7rem",
                                    }}
                                  >
                                    Terminal (Fix Source)
                                  </span>
                                )}
                              </td>
                              <td style={{ padding: "0.75rem 0.5rem" }}>
                                {row.error_code && (
                                  <span style={{ fontFamily: "monospace", fontSize: "0.75rem", display: "block" }}>
                                    {row.error_code}
                                  </span>
                                )}
                                <span style={{ color: row.error_message ? "var(--status-error)" : "var(--text-muted)", fontSize: "0.75rem" }}>
                                  {row.error_message || "-"}
                                </span>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </>
                ) : (
                  <div style={{ textAlign: "center", padding: "2rem", color: "var(--text-muted)" }}>
                    Loading reconciliation report...
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </AppShell>
  );
};
