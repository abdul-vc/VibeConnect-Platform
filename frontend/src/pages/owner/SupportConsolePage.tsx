/**
 * Support / Operations Console Page (Phase 6C-3 & 6C-4).
 *
 * Dedicated workspace for Support Operators and Platform Owners to:
 * - Locate customer organizations.
 * - Inspect unified diagnostic health and provisioning state.
 * - View stuck jobs, dead-letter records, and reconciliation issues.
 * - Perform controlled operational remediation (Phase 6C-4).
 *
 * Built strictly with centralized API client. Zero hardcoded URLs.
 */

import React, { useCallback, useEffect, useState } from "react";
import { AppShell } from "../../components/AppShell.tsx";
import { GlassPanel } from "../../components/GlassPanel.tsx";
import { LoadingSpinner } from "../../components/LoadingSpinner.tsx";
import {
  ShieldCheckIcon,
  SearchIcon,
  RefreshIcon,
  AlertCircleIcon,
  CheckCircleIcon,
  UserIcon,
  PlusIcon,
  CloseIcon,
} from "../../components/Icons.tsx";

import {
  supportApi,
  type SupportDiagnosticsResponse,
  type SupportFailure,
  type SupportOrganizationSummary,
  type SupportReconciliationIssue,
  type EligibleTargetUser,
  type SupportOperatorAssignment,
} from "../../api/support.ts";
import { setActiveImpersonationSessionId } from "../../api/client.ts";
import { useAuth } from "../../context/AuthContext.tsx";

export const CANONICAL_SUPPORT_ROLES = [
  {
    code: "support_operator",
    name: "Support Operator",
    description: "Full diagnostic inspection, operational remediation (retry & resolve), and audited user impersonation.",
  },
  {
    code: "support_diagnostics_viewer",
    name: "Support Diagnostics Viewer",
    description: "Read-only access to platform diagnostic health, instances, stuck jobs, and audit logs.",
  },
  {
    code: "support_remediation_operator",
    name: "Support Remediation Operator",
    description: "Operational remediation privileges (retry failed operations and resolve dead-letter issues).",
  },
] as const;

function StatusBadge({ status }: { readonly status: string }) {
  const norm = (status || "").toLowerCase();
  let bg = "var(--glass-surface)";
  let color = "var(--text-muted)";
  let border = "var(--border-subtle)";

  if (norm === "active" || norm === "resolved" || norm === "healthy" || norm === "completed") {
    bg = "var(--status-success-bg, rgba(34, 197, 94, 0.15))";
    color = "var(--status-success, #22c55e)";
    border = "var(--status-success-border, rgba(34, 197, 94, 0.3))";
  } else if (
    norm === "suspended" ||
    norm === "retry_scheduled" ||
    norm === "degraded" ||
    norm === "queued" ||
    norm === "processing"
  ) {
    bg = "var(--status-warning-bg, rgba(245, 158, 11, 0.15))";
    color = "var(--status-warning, #f59e0b)";
    border = "var(--status-warning-border, rgba(245, 158, 11, 0.3))";
  } else if (
    norm === "disconnected" ||
    norm === "retired" ||
    norm === "dead_letter" ||
    norm === "attention_required" ||
    norm === "failed" ||
    norm === "stuck_queued" ||
    norm === "stuck_processing" ||
    norm === "orphaned"
  ) {
    bg = "var(--status-danger-bg, rgba(239, 68, 68, 0.15))";
    color = "var(--status-danger, #ef4444)";
    border = "var(--status-danger-border, rgba(239, 68, 68, 0.3))";
  } else if (norm === "open") {
    bg = "rgba(59, 130, 246, 0.15)";
    color = "#3b82f6";
    border = "rgba(59, 130, 246, 0.3)";
  }

  const label = norm.replace(/_/g, " ");

  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        padding: "0.2rem 0.6rem",
        borderRadius: "9999px",
        fontSize: "0.75rem",
        fontWeight: 600,
        textTransform: "capitalize",
        background: bg,
        color,
        border: `1px solid ${border}`,
      }}
    >
      {label}
    </span>
  );
}

export const SupportConsolePage: React.FC = () => {
  const { user } = useAuth();
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<readonly SupportOrganizationSummary[]>([]);
  const [selectedOrgId, setSelectedOrgId] = useState<string | null>(null);
  const [diagnostics, setDiagnostics] = useState<SupportDiagnosticsResponse | null>(null);
  const [searching, setSearching] = useState(false);
  const [loadingDiagnostics, setLoadingDiagnostics] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successNotice, setSuccessNotice] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<
    "overview" | "stuck_jobs" | "failures" | "reconciliation" | "audit"
  >("overview");

  // Remediation Modal States (Phase 6C-4)
  const [remediatingFailure, setRemediatingFailure] = useState<SupportFailure | null>(null);
  const [remediatingIssue, setRemediatingIssue] = useState<SupportReconciliationIssue | null>(null);
  const [resolutionReason, setResolutionReason] = useState("");
  const [remediationActionLoading, setRemediationActionLoading] = useState(false);
  const [remediationError, setRemediationError] = useState<string | null>(null);

  // Permission checks
  const isOwner = Boolean(user?.is_platform_owner);
  const userPermissions = user?.active_context?.effective_permissions ?? [];
  const canRetry = isOwner || userPermissions.includes("support.operations.retry");
  const canResolve = isOwner || userPermissions.includes("support.operations.resolve");
  const canImpersonate = isOwner || userPermissions.includes("support.impersonation.initiate");

  // Impersonation Modal States (Phase 6D)
  const [impersonateModalOpen, setImpersonateModalOpen] = useState(false);
  const [eligibleTargets, setEligibleTargets] = useState<readonly EligibleTargetUser[]>([]);
  const [selectedTargetUserId, setSelectedTargetUserId] = useState<string>("");
  const [impersonationReason, setImpersonationReason] = useState("");
  const [impersonationTicketRef, setImpersonationTicketRef] = useState("");
  const [impersonationLoading, setImpersonationLoading] = useState(false);
  const [impersonationError, setImpersonationError] = useState<string | null>(null);

  // Platform Console Mode Switcher (Phase 6C)
  const [consoleView, setConsoleView] = useState<"diagnostics" | "operators">("diagnostics");

  // Support Operator Administration States (Phase 6C)
  const [operators, setOperators] = useState<readonly SupportOperatorAssignment[]>([]);
  const [loadingOperators, setLoadingOperators] = useState(false);
  const [operatorsError, setOperatorsError] = useState<string | null>(null);
  const [operatorsSuccess, setOperatorsSuccess] = useState<string | null>(null);

  // Grant Modal States
  const [grantModalOpen, setGrantModalOpen] = useState(false);
  const [grantUserId, setGrantUserId] = useState("");
  const [grantRoleCode, setGrantRoleCode] = useState<string>("support_operator");
  const [grantLoading, setGrantLoading] = useState(false);
  const [grantError, setGrantError] = useState<string | null>(null);

  // Revocation State
  const [revokingId, setRevokingId] = useState<string | null>(null);

  const handleOpenImpersonate = async () => {
    if (!selectedOrgId) return;
    setImpersonateModalOpen(true);
    setImpersonationLoading(true);
    setImpersonationError(null);
    setSelectedTargetUserId("");
    setImpersonationReason("");
    setImpersonationTicketRef("");
    try {
      const targets = await supportApi.getEligibleTargets(selectedOrgId);
      setEligibleTargets(targets);
      if (targets.length > 0) {
        setSelectedTargetUserId(targets[0].id);
      }
    } catch (err: unknown) {
      setImpersonationError(err instanceof Error ? err.message : "Failed to load eligible target users.");
    } finally {
      setImpersonationLoading(false);
    }
  };

  const handleStartImpersonationSubmit = async () => {
    if (!selectedOrgId || !selectedTargetUserId) return;
    const trimmedReason = impersonationReason.trim();
    if (trimmedReason.length < 1 || trimmedReason.length > 500) {
      setImpersonationError("Reason must be between 1 and 500 characters.");
      return;
    }
    const trimmedTicket = impersonationTicketRef.trim();
    if (trimmedTicket.length < 1 || trimmedTicket.length > 100) {
      setImpersonationError("Ticket / incident reference is required (1 to 100 characters).");
      return;
    }
    setImpersonationLoading(true);
    setImpersonationError(null);
    try {
      const session = await supportApi.createImpersonationSession({
        target_organization_id: selectedOrgId,
        target_user_id: selectedTargetUserId,
        reason: trimmedReason,
        ticket_reference: trimmedTicket,
      });
      setActiveImpersonationSessionId(session.id);
      setSuccessNotice(`Audited impersonation session started for ${session.target_user_email}.`);
      setImpersonateModalOpen(false);
      window.dispatchEvent(new Event("impersonation-started"));
    } catch (err: unknown) {
      setImpersonationError(err instanceof Error ? err.message : "Failed to start impersonation session.");
    } finally {
      setImpersonationLoading(false);
    }
  };

  // Support Operator Role Administration Handlers (Phase 6C)
  const loadOperators = useCallback(async () => {
    if (!isOwner) return;
    setLoadingOperators(true);
    setOperatorsError(null);
    try {
      const data = await supportApi.listSupportOperators();
      setOperators(data);
    } catch (err: unknown) {
      setOperatorsError(err instanceof Error ? err.message : "Failed to load support operator assignments.");
    } finally {
      setLoadingOperators(false);
    }
  }, [isOwner]);

  useEffect(() => {
    if (isOwner && consoleView === "operators") {
      void loadOperators();
    }
  }, [isOwner, consoleView, loadOperators]);

  const handleOpenGrantModal = () => {
    setGrantUserId("");
    setGrantRoleCode("support_operator");
    setGrantError(null);
    setGrantModalOpen(true);
  };

  const handleGrantSubmit = async () => {
    const cleanUserId = grantUserId.trim();
    if (!cleanUserId) {
      setGrantError("Target User ID (UUID) is required.");
      return;
    }
    setGrantLoading(true);
    setGrantError(null);
    try {
      const assignment = await supportApi.grantSupportRole({
        user_id: cleanUserId,
        role_code: grantRoleCode,
      });
      setOperatorsSuccess(
        `Successfully granted '${assignment.role_name}' to ${assignment.user_email || assignment.user_name || assignment.user_id}.`
      );
      setGrantModalOpen(false);
      await loadOperators();
    } catch (err: unknown) {
      setGrantError(err instanceof Error ? err.message : "Failed to grant support role.");
    } finally {
      setGrantLoading(false);
    }
  };

  const handleRevoke = async (assignment: SupportOperatorAssignment) => {
    if (
      !window.confirm(
        `Are you sure you want to revoke the role '${assignment.role_name}' from ${assignment.user_email || assignment.user_name || assignment.user_id}?`
      )
    ) {
      return;
    }
    setRevokingId(assignment.id);
    setOperatorsError(null);
    try {
      await supportApi.revokeSupportRole(assignment.id);
      setOperatorsSuccess(
        `Revoked support role '${assignment.role_name}' from ${assignment.user_email || assignment.user_name || assignment.user_id}.`
      );
      await loadOperators();
    } catch (err: unknown) {
      setOperatorsError(err instanceof Error ? err.message : "Failed to revoke support role.");
    } finally {
      setRevokingId(null);
    }
  };

  // Initial organization search
  const handleSearch = useCallback(async (query: string = "") => {
    setSearching(true);
    setError(null);
    try {
      const results = await supportApi.searchOrganizations(query);
      setSearchResults(results);
      if (results.length > 0 && !selectedOrgId) {
        setSelectedOrgId(results[0].id);
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to load organizations.");
    } finally {
      setSearching(false);
    }
  }, [selectedOrgId]);

  useEffect(() => {
    void handleSearch("");
  }, [handleSearch]);

  // Load diagnostics when selected organization changes
  const loadDiagnostics = useCallback(async (orgId: string) => {
    setLoadingDiagnostics(true);
    setError(null);
    try {
      const data = await supportApi.getOrganizationDiagnostics(orgId);
      setDiagnostics(data);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to load diagnostic state.");
      setDiagnostics(null);
    } finally {
      setLoadingDiagnostics(false);
    }
  }, []);

  useEffect(() => {
    if (selectedOrgId) {
      void loadDiagnostics(selectedOrgId);
    }
  }, [selectedOrgId, loadDiagnostics]);

  // Remediation Handlers (Phase 6C-4)
  const handleRetryFailure = async (failure: SupportFailure) => {
    if (!selectedOrgId) return;
    setRemediationActionLoading(true);
    setError(null);
    try {
      await supportApi.retryFailure(selectedOrgId, failure.id);
      setSuccessNotice(`Retry successfully scheduled for failure ${failure.id}.`);
      void loadDiagnostics(selectedOrgId);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to trigger retry.");
    } finally {
      setRemediationActionLoading(false);
    }
  };

  const handleReplayFailure = async (failure: SupportFailure) => {
    if (!selectedOrgId) return;
    setRemediationActionLoading(true);
    setError(null);
    try {
      await supportApi.replayFailure(selectedOrgId, failure.id);
      setSuccessNotice(`Dead-letter failure ${failure.id} successfully initiated replay.`);
      void loadDiagnostics(selectedOrgId);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to replay dead-letter record.");
    } finally {
      setRemediationActionLoading(false);
    }
  };

  const handleResolveFailureSubmit = async () => {
    if (!selectedOrgId || !remediatingFailure) return;
    const trimmed = resolutionReason.trim();
    if (trimmed.length < 1 || trimmed.length > 500) {
      setRemediationError("Resolution reason must be between 1 and 500 characters.");
      return;
    }
    setRemediationActionLoading(true);
    setRemediationError(null);
    try {
      await supportApi.resolveFailure(selectedOrgId, remediatingFailure.id, trimmed);
      setSuccessNotice(`Failure ${remediatingFailure.id} marked as resolved.`);
      setRemediatingFailure(null);
      setResolutionReason("");
      void loadDiagnostics(selectedOrgId);
    } catch (err: unknown) {
      setRemediationError(err instanceof Error ? err.message : "Failed to resolve failure.");
    } finally {
      setRemediationActionLoading(false);
    }
  };

  const handleResolveReconciliationSubmit = async () => {
    if (!selectedOrgId || !remediatingIssue) return;
    const trimmed = resolutionReason.trim();
    if (trimmed.length < 1 || trimmed.length > 500) {
      setRemediationError("Resolution notes must be between 1 and 500 characters.");
      return;
    }
    setRemediationActionLoading(true);
    setRemediationError(null);
    try {
      await supportApi.resolveReconciliation(selectedOrgId, remediatingIssue.id, trimmed);
      setSuccessNotice(`Reconciliation issue ${remediatingIssue.id} resolved successfully.`);
      setRemediatingIssue(null);
      setResolutionReason("");
      void loadDiagnostics(selectedOrgId);
    } catch (err: unknown) {
      setRemediationError(err instanceof Error ? err.message : "Failed to resolve reconciliation issue.");
    } finally {
      setRemediationActionLoading(false);
    }
  };

  return (
    <AppShell>
      <div style={{ maxWidth: "1400px", margin: "0 auto", padding: "1.5rem" }}>
        {/* Page Header */}
        <div style={{ marginBottom: "2rem" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", marginBottom: "0.5rem" }}>
            <div
              style={{
                width: "40px",
                height: "40px",
                borderRadius: "10px",
                background: "rgba(59, 130, 246, 0.15)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                color: "#3b82f6",
              }}
            >
              <ShieldCheckIcon size={24} />
            </div>
            <div>
              <h1 style={{ fontSize: "1.75rem", fontWeight: 700, margin: 0, color: "var(--text-primary)" }}>
                Support / Operations Console
              </h1>
              <p style={{ margin: 0, color: "var(--text-secondary)", fontSize: "0.875rem" }}>
                Platform-scoped diagnostic inspection and controlled operational remediation
              </p>
            </div>
          </div>
        </div>

        {/* Platform Owner Console Mode Switcher (Phase 6C) */}
        {isOwner && (
          <div
            style={{
              display: "flex",
              gap: "0.5rem",
              marginBottom: "1.5rem",
              borderBottom: "1px solid var(--border-subtle)",
              paddingBottom: "0.5rem",
            }}
          >
            <button
              type="button"
              onClick={() => setConsoleView("diagnostics")}
              style={{
                padding: "0.5rem 1rem",
                borderRadius: "6px",
                border: "none",
                background: consoleView === "diagnostics" ? "var(--glass-surface-elevated)" : "transparent",
                color: consoleView === "diagnostics" ? "var(--text-primary)" : "var(--text-secondary)",
                fontWeight: consoleView === "diagnostics" ? 600 : 400,
                fontSize: "0.875rem",
                cursor: "pointer",
                display: "flex",
                alignItems: "center",
                gap: "0.5rem",
              }}
            >
              <span>Tenant Diagnostics & Remediation</span>
            </button>
            <button
              type="button"
              onClick={() => setConsoleView("operators")}
              style={{
                padding: "0.5rem 1rem",
                borderRadius: "6px",
                border: "none",
                background: consoleView === "operators" ? "var(--glass-surface-elevated)" : "transparent",
                color: consoleView === "operators" ? "var(--text-primary)" : "var(--text-secondary)",
                fontWeight: consoleView === "operators" ? 600 : 400,
                fontSize: "0.875rem",
                cursor: "pointer",
                display: "flex",
                alignItems: "center",
                gap: "0.5rem",
              }}
            >
              <UserIcon size={16} />
              <span>Support Operator Roles</span>
              <span
                style={{
                  fontSize: "0.6875rem",
                  padding: "0.15rem 0.45rem",
                  borderRadius: "9999px",
                  background: "rgba(59, 130, 246, 0.15)",
                  color: "#3b82f6",
                  fontWeight: 600,
                }}
              >
                Owner
              </span>
            </button>
          </div>
        )}

        {/* Notices */}
        {error && (
          <div
            style={{
              padding: "1rem",
              borderRadius: "8px",
              background: "var(--status-danger-bg)",
              border: "1px solid var(--status-danger-border)",
              color: "var(--status-danger)",
              marginBottom: "1.5rem",
              display: "flex",
              alignItems: "center",
              gap: "0.5rem",
            }}
          >
            <AlertCircleIcon size={18} />

            <span>{error}</span>
          </div>
        )}
        {successNotice && (
          <div
            style={{
              padding: "1rem",
              borderRadius: "8px",
              background: "var(--status-success-bg)",
              border: "1px solid var(--status-success-border)",
              color: "var(--status-success)",
              marginBottom: "1.5rem",
              display: "flex",
              alignItems: "center",
              gap: "0.5rem",
            }}
          >
            <CheckCircleIcon size={18} />
            <span>{successNotice}</span>
          </div>
        )}

        {/* DIAGNOSTICS & REMEDIATION VIEW */}
        {consoleView === "diagnostics" && (
          <div>
            {/* Organization Search & Selector Card */}
            <GlassPanel elevation="default" padding="lg" style={{ marginBottom: "1.5rem" }}>
          <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
              <span style={{ fontWeight: 600, fontSize: "0.9375rem" }}>Tenant Organization Locator</span>
              {selectedOrgId && (
                <button
                  type="button"
                  onClick={() => selectedOrgId && void loadDiagnostics(selectedOrgId)}
                  disabled={loadingDiagnostics}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: "0.4rem",
                    fontSize: "0.8125rem",
                    padding: "0.3rem 0.75rem",
                    borderRadius: "6px",
                    background: "var(--glass-surface)",
                    border: "1px solid var(--border-subtle)",
                    color: "var(--text-secondary)",
                    cursor: "pointer",
                  }}
                >
                  <RefreshIcon size={14} />
                  <span>Refresh Diagnostics</span>
                </button>
              )}
            </div>

            <form
              onSubmit={(e) => {
                e.preventDefault();
                void handleSearch(searchQuery);
              }}
              style={{ display: "flex", gap: "0.5rem" }}
            >
              <div style={{ position: "relative", flex: 1 }}>
                <input
                  type="text"
                  placeholder="Search by organization name, code, or UUID..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  style={{
                    width: "100%",
                    padding: "0.6rem 0.8rem 0.6rem 2.2rem",
                    borderRadius: "8px",
                    background: "var(--input-bg, var(--glass-surface))",
                    border: "1px solid var(--border-subtle)",
                    color: "var(--text-primary)",
                    fontSize: "0.875rem",
                  }}
                />
                <span
                  style={{
                    position: "absolute",
                    left: "0.75rem",
                    top: "50%",
                    transform: "translateY(-50%)",
                    color: "var(--text-muted)",
                    pointerEvents: "none",
                  }}
                >
                  <SearchIcon size={16} />
                </span>
              </div>
              <button
                type="submit"
                disabled={searching}
                className="btn-primary"
                style={{ padding: "0.6rem 1.25rem", fontSize: "0.875rem" }}
              >
                {searching ? "Searching..." : "Search"}
              </button>
            </form>

            {/* Quick Organization Selector Chips */}
            {searchResults.length > 0 && (
              <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem", marginTop: "0.25rem" }}>
                {searchResults.map((org) => {
                  const isSelected = org.id === selectedOrgId;
                  return (
                    <button
                      key={org.id}
                      type="button"
                      onClick={() => setSelectedOrgId(org.id)}
                      style={{
                        padding: "0.35rem 0.75rem",
                        borderRadius: "8px",
                        fontSize: "0.8125rem",
                        fontWeight: isSelected ? 600 : 400,
                        background: isSelected ? "var(--primary-color, #2563eb)" : "var(--glass-surface)",
                        color: isSelected ? "#fff" : "var(--text-primary)",
                        border: isSelected
                          ? "1px solid var(--primary-color, #2563eb)"
                          : "1px solid var(--border-subtle)",
                        cursor: "pointer",
                        display: "flex",
                        alignItems: "center",
                        gap: "0.5rem",
                      }}
                    >
                      <span>{org.name}</span>
                      <span
                        style={{
                          fontSize: "0.6875rem",
                          opacity: isSelected ? 0.9 : 0.6,
                          textTransform: "uppercase",
                        }}
                      >
                        [{org.code}]
                      </span>
                    </button>
                  );
                })}
              </div>
            )}
          </div>
        </GlassPanel>

        {loadingDiagnostics && (
          <div style={{ padding: "3rem", textAlign: "center" }}>
            <LoadingSpinner label="Fetching authoritative diagnostic state..." />
          </div>
        )}

        {/* Diagnostic Detail Workspace */}
        {!loadingDiagnostics && diagnostics && (
          <div>
            {/* Organization Identity & Health Banner */}
            <GlassPanel elevation="elevated" padding="lg" style={{ marginBottom: "1.5rem" }}>
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  flexWrap: "wrap",
                  gap: "1rem",
                  marginBottom: "1.5rem",
                }}
              >
                <div>
                  <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", marginBottom: "0.25rem" }}>
                    <h2 style={{ fontSize: "1.25rem", fontWeight: 700, margin: 0 }}>
                      {diagnostics.organization.name}
                    </h2>
                    <StatusBadge status={diagnostics.organization.status} />
                  </div>
                  <div style={{ fontSize: "0.8125rem", color: "var(--text-secondary)", display: "flex", gap: "1rem" }}>
                    <span>Code: <strong>{diagnostics.organization.code}</strong></span>
                    <span>Org ID: <code style={{ fontSize: "0.75rem" }}>{diagnostics.organization.id}</code></span>
                  </div>
                </div>

                <div style={{ display: "flex", alignItems: "center", gap: "1rem" }}>
                  {canImpersonate && (
                    <button
                      type="button"
                      onClick={() => void handleOpenImpersonate()}
                      className="btn-secondary"
                      style={{
                        display: "flex",
                        alignItems: "center",
                        gap: "0.5rem",
                        padding: "0.45rem 0.9rem",
                        fontSize: "0.8125rem",
                        fontWeight: 600,
                        borderRadius: "8px",
                        background: "rgba(234, 88, 12, 0.12)",
                        color: "#ea580c",
                        border: "1px solid rgba(234, 88, 12, 0.35)",
                        cursor: "pointer",
                      }}
                    >
                      <UserIcon size={15} />
                      <span>Impersonate User</span>
                    </button>
                  )}
                  <div style={{ textAlign: "right" }}>
                    <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", textTransform: "uppercase" }}>
                      Control Plane Health
                    </div>
                    <div style={{ marginTop: "0.25rem" }}>
                      <StatusBadge status={diagnostics.health.control_plane_status} />
                    </div>
                  </div>
                </div>
              </div>

              {/* Aggregated Health Metric Cards */}
              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))",
                  gap: "1rem",
                }}
              >
                <div
                  style={{
                    padding: "0.875rem",
                    borderRadius: "8px",
                    background: "var(--glass-surface)",
                    border: "1px solid var(--border-subtle)",
                  }}
                >
                  <div style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>Connector Instances</div>
                  <div style={{ fontSize: "1.5rem", fontWeight: 700, margin: "0.25rem 0" }}>
                    {diagnostics.health.instances.total}
                  </div>
                  <div style={{ fontSize: "0.75rem", color: "var(--text-secondary)" }}>
                    {diagnostics.health.instances.active} Active &bull; {diagnostics.health.instances.suspended} Suspended
                  </div>
                </div>

                <div
                  style={{
                    padding: "0.875rem",
                    borderRadius: "8px",
                    background: "var(--glass-surface)",
                    border: "1px solid var(--border-subtle)",
                  }}
                >
                  <div style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>Active Failures</div>
                  <div style={{ fontSize: "1.5rem", fontWeight: 700, margin: "0.25rem 0", color: diagnostics.health.failures.open > 0 ? "var(--status-warning)" : "inherit" }}>
                    {diagnostics.health.failures.open}
                  </div>
                  <div style={{ fontSize: "0.75rem", color: "var(--text-secondary)" }}>
                    {diagnostics.health.failures.retry_scheduled} Retry Scheduled &bull; {diagnostics.health.failures.last_24h} in 24h
                  </div>
                </div>

                <div
                  style={{
                    padding: "0.875rem",
                    borderRadius: "8px",
                    background: "var(--glass-surface)",
                    border: "1px solid var(--border-subtle)",
                  }}
                >
                  <div style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>Dead-Letter Records</div>
                  <div style={{ fontSize: "1.5rem", fontWeight: 700, margin: "0.25rem 0", color: diagnostics.health.failures.dead_letter > 0 ? "var(--status-danger)" : "inherit" }}>
                    {diagnostics.health.failures.dead_letter}
                  </div>
                  <div style={{ fontSize: "0.75rem", color: "var(--text-secondary)" }}>
                    Requires operator attention
                  </div>
                </div>

                <div
                  style={{
                    padding: "0.875rem",
                    borderRadius: "8px",
                    background: "var(--glass-surface)",
                    border: "1px solid var(--border-subtle)",
                  }}
                >
                  <div style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>Stuck / Orphaned Jobs</div>
                  <div style={{ fontSize: "1.5rem", fontWeight: 700, margin: "0.25rem 0", color: (diagnostics.health.jobs.stuck_queued + diagnostics.health.jobs.stuck_processing + diagnostics.health.jobs.orphaned) > 0 ? "var(--status-danger)" : "inherit" }}>
                    {diagnostics.health.jobs.stuck_queued + diagnostics.health.jobs.stuck_processing + diagnostics.health.jobs.orphaned}
                  </div>
                  <div style={{ fontSize: "0.75rem", color: "var(--text-secondary)" }}>
                    {diagnostics.health.jobs.stuck_queued} Queued &bull; {diagnostics.health.jobs.stuck_processing} Processing
                  </div>
                </div>

                <div
                  style={{
                    padding: "0.875rem",
                    borderRadius: "8px",
                    background: "var(--glass-surface)",
                    border: "1px solid var(--border-subtle)",
                  }}
                >
                  <div style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>Reconciliation Issues</div>
                  <div style={{ fontSize: "1.5rem", fontWeight: 700, margin: "0.25rem 0", color: diagnostics.health.open_reconciliation_issues_count > 0 ? "var(--status-warning)" : "inherit" }}>
                    {diagnostics.health.open_reconciliation_issues_count}
                  </div>
                  <div style={{ fontSize: "0.75rem", color: "var(--text-secondary)" }}>
                    Open discrepancy reports
                  </div>
                </div>
              </div>
            </GlassPanel>

            {/* Diagnostic Navigation Tabs */}
            <div style={{ display: "flex", gap: "0.5rem", marginBottom: "1.5rem", borderBottom: "1px solid var(--border-subtle)", paddingBottom: "0.5rem" }}>
              {[
                { id: "overview", label: `Connector Instances (${diagnostics.connector_instances.length})` },
                { id: "stuck_jobs", label: `Stuck Jobs (${diagnostics.stuck_jobs.length})` },
                { id: "failures", label: `Failures & Dead-Letter (${diagnostics.dead_letter_failures.length + diagnostics.open_failures.length})` },
                { id: "reconciliation", label: `Reconciliation (${diagnostics.reconciliation_issues.length})` },
                { id: "audit", label: `Recent Audit Logs (${diagnostics.recent_audit_logs.length})` },
              ].map((tab) => (
                <button
                  key={tab.id}
                  type="button"
                  onClick={() => setActiveTab(tab.id as typeof activeTab)}
                  style={{
                    padding: "0.5rem 1rem",
                    borderRadius: "6px",
                    border: "none",
                    background: activeTab === tab.id ? "var(--glass-surface-elevated)" : "transparent",
                    color: activeTab === tab.id ? "var(--text-primary)" : "var(--text-secondary)",
                    fontWeight: activeTab === tab.id ? 600 : 400,
                    fontSize: "0.875rem",
                    cursor: "pointer",
                  }}
                >
                  {tab.label}
                </button>
              ))}
            </div>

            {/* TAB 1: Connector Instances */}
            {activeTab === "overview" && (
              <GlassPanel elevation="default" padding="lg">
                <h3 style={{ fontSize: "1rem", fontWeight: 600, marginBottom: "1rem" }}>
                  Provisioned Connector Instances
                </h3>
                {diagnostics.connector_instances.length === 0 ? (
                  <p style={{ color: "var(--text-muted)", fontSize: "0.875rem" }}>No connector instances found.</p>
                ) : (
                  <div style={{ overflowX: "auto" }}>
                    <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.875rem" }}>
                      <thead>
                        <tr style={{ borderBottom: "1px solid var(--border-subtle)", textAlign: "left", color: "var(--text-muted)" }}>
                          <th style={{ padding: "0.75rem 0.5rem" }}>Connector</th>
                          <th style={{ padding: "0.75rem 0.5rem" }}>Label</th>
                          <th style={{ padding: "0.75rem 0.5rem" }}>Status</th>
                          <th style={{ padding: "0.75rem 0.5rem" }}>Created At</th>
                          <th style={{ padding: "0.75rem 0.5rem" }}>Instance ID</th>
                        </tr>
                      </thead>
                      <tbody>
                        {diagnostics.connector_instances.map((inst) => (
                          <tr key={inst.id} style={{ borderBottom: "1px solid var(--border-subtle)" }}>
                            <td style={{ padding: "0.75rem 0.5rem", fontWeight: 500 }}>
                              {inst.connector_name} ({inst.connector_code})
                            </td>
                            <td style={{ padding: "0.75rem 0.5rem" }}>{inst.label}</td>
                            <td style={{ padding: "0.75rem 0.5rem" }}><StatusBadge status={inst.status} /></td>
                            <td style={{ padding: "0.75rem 0.5rem", color: "var(--text-secondary)" }}>
                              {new Date(inst.created_at).toLocaleString()}
                            </td>
                            <td style={{ padding: "0.75rem 0.5rem" }}>
                              <code style={{ fontSize: "0.75rem" }}>{inst.id}</code>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </GlassPanel>
            )}

            {/* TAB 2: Stuck Provisioning Jobs */}
            {activeTab === "stuck_jobs" && (
              <GlassPanel elevation="default" padding="lg">
                <h3 style={{ fontSize: "1rem", fontWeight: 600, marginBottom: "1rem" }}>
                  Stuck & Orphaned Provisioning Jobs
                </h3>
                {diagnostics.stuck_jobs.length === 0 ? (
                  <div style={{ padding: "2rem", textAlign: "center", color: "var(--text-muted)" }}>
                    <CheckCircleIcon size={32} style={{ color: "var(--status-success)", marginBottom: "0.5rem" }} />
                    <p>No stuck or orphaned provisioning jobs detected.</p>
                  </div>
                ) : (
                  <div style={{ overflowX: "auto" }}>
                    <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.875rem" }}>
                      <thead>
                        <tr style={{ borderBottom: "1px solid var(--border-subtle)", textAlign: "left", color: "var(--text-muted)" }}>
                          <th style={{ padding: "0.75rem 0.5rem" }}>Job ID</th>
                          <th style={{ padding: "0.75rem 0.5rem" }}>Action</th>
                          <th style={{ padding: "0.75rem 0.5rem" }}>Category</th>
                          <th style={{ padding: "0.75rem 0.5rem" }}>Stuck Reason</th>
                          <th style={{ padding: "0.75rem 0.5rem" }}>Age</th>
                        </tr>
                      </thead>
                      <tbody>
                        {diagnostics.stuck_jobs.map((job) => (
                          <tr key={job.id} style={{ borderBottom: "1px solid var(--border-subtle)" }}>
                            <td style={{ padding: "0.75rem 0.5rem" }}>
                              <code style={{ fontSize: "0.75rem" }}>{job.id}</code>
                            </td>
                            <td style={{ padding: "0.75rem 0.5rem", fontWeight: 500 }}>{job.action}</td>
                            <td style={{ padding: "0.75rem 0.5rem" }}>
                              <StatusBadge status={job.classification?.category || job.status} />
                            </td>
                            <td style={{ padding: "0.75rem 0.5rem", color: "var(--text-secondary)" }}>
                              {job.classification?.reason || "N/A"}
                            </td>
                            <td style={{ padding: "0.75rem 0.5rem", color: "var(--text-muted)" }}>
                              {job.classification?.age_seconds ? `${job.classification.age_seconds}s` : "N/A"}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </GlassPanel>
            )}

            {/* TAB 3: Failures & Dead-Letter Records */}
            {activeTab === "failures" && (
              <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }}>
                {/* Dead Letter Records */}
                <GlassPanel elevation="default" padding="lg">
                  <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "1rem" }}>
                    <h3 style={{ fontSize: "1rem", fontWeight: 600, margin: 0, color: "var(--status-danger)" }}>
                      Dead-Letter Failures ({diagnostics.dead_letter_failures.length})
                    </h3>
                  </div>
                  {diagnostics.dead_letter_failures.length === 0 ? (
                    <p style={{ color: "var(--text-muted)", fontSize: "0.875rem" }}>No dead-letter failures.</p>
                  ) : (
                    <div style={{ overflowX: "auto" }}>
                      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.875rem" }}>
                        <thead>
                          <tr style={{ borderBottom: "1px solid var(--border-subtle)", textAlign: "left", color: "var(--text-muted)" }}>
                            <th style={{ padding: "0.75rem 0.5rem" }}>Failure Code</th>
                            <th style={{ padding: "0.75rem 0.5rem" }}>Detail</th>
                            <th style={{ padding: "0.75rem 0.5rem" }}>Attempts</th>
                            <th style={{ padding: "0.75rem 0.5rem" }}>Last Updated</th>
                            <th style={{ padding: "0.75rem 0.5rem", textAlign: "right" }}>Actions</th>
                          </tr>
                        </thead>
                        <tbody>
                          {diagnostics.dead_letter_failures.map((f) => (
                            <tr key={f.id} style={{ borderBottom: "1px solid var(--border-subtle)" }}>
                              <td style={{ padding: "0.75rem 0.5rem" }}>
                                <div style={{ fontWeight: 600 }}>{f.failure_code}</div>
                                <div style={{ fontSize: "0.6875rem", color: "var(--text-muted)" }}>{f.connector_code}</div>
                              </td>
                              <td style={{ padding: "0.75rem 0.5rem", maxWidth: "350px", color: "var(--text-secondary)" }}>
                                <span style={{ fontFamily: "monospace", fontSize: "0.75rem" }}>{f.sanitized_detail}</span>
                              </td>
                              <td style={{ padding: "0.75rem 0.5rem" }}>
                                {f.retry_count} / {f.max_retries}
                              </td>
                              <td style={{ padding: "0.75rem 0.5rem", color: "var(--text-muted)" }}>
                                {new Date(f.updated_at).toLocaleString()}
                              </td>
                              <td style={{ padding: "0.75rem 0.5rem", textAlign: "right" }}>
                                <div style={{ display: "inline-flex", gap: "0.5rem" }}>
                                  {canRetry && (
                                    <button
                                      type="button"
                                      disabled={remediationActionLoading}
                                      onClick={() => void handleReplayFailure(f)}
                                      style={{
                                        padding: "0.3rem 0.6rem",
                                        borderRadius: "6px",
                                        fontSize: "0.75rem",
                                        background: "var(--status-warning-bg)",
                                        border: "1px solid var(--status-warning-border)",
                                        color: "var(--status-warning)",
                                        cursor: "pointer",
                                      }}
                                    >
                                      Replay
                                    </button>
                                  )}
                                  {canResolve && (
                                    <button
                                      type="button"
                                      disabled={remediationActionLoading}
                                      onClick={() => setRemediatingFailure(f)}
                                      style={{
                                        padding: "0.3rem 0.6rem",
                                        borderRadius: "6px",
                                        fontSize: "0.75rem",
                                        background: "var(--status-success-bg)",
                                        border: "1px solid var(--status-success-border)",
                                        color: "var(--status-success)",
                                        cursor: "pointer",
                                      }}
                                    >
                                      Resolve
                                    </button>
                                  )}
                                </div>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </GlassPanel>

                {/* Open & Retry-Scheduled Failures */}
                <GlassPanel elevation="default" padding="lg">
                  <h3 style={{ fontSize: "1rem", fontWeight: 600, marginBottom: "1rem" }}>
                    Open & Retry-Scheduled Failures ({diagnostics.open_failures.length})
                  </h3>
                  {diagnostics.open_failures.length === 0 ? (
                    <p style={{ color: "var(--text-muted)", fontSize: "0.875rem" }}>No open failures.</p>
                  ) : (
                    <div style={{ overflowX: "auto" }}>
                      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.875rem" }}>
                        <thead>
                          <tr style={{ borderBottom: "1px solid var(--border-subtle)", textAlign: "left", color: "var(--text-muted)" }}>
                            <th style={{ padding: "0.75rem 0.5rem" }}>Failure Code</th>
                            <th style={{ padding: "0.75rem 0.5rem" }}>Status</th>
                            <th style={{ padding: "0.75rem 0.5rem" }}>Attempts</th>
                            <th style={{ padding: "0.75rem 0.5rem" }}>Retry After</th>
                            <th style={{ padding: "0.75rem 0.5rem", textAlign: "right" }}>Actions</th>
                          </tr>
                        </thead>
                        <tbody>
                          {diagnostics.open_failures.map((f) => (
                            <tr key={f.id} style={{ borderBottom: "1px solid var(--border-subtle)" }}>
                              <td style={{ padding: "0.75rem 0.5rem" }}>
                                <div style={{ fontWeight: 600 }}>{f.failure_code}</div>
                                <div style={{ fontSize: "0.6875rem", color: "var(--text-muted)" }}>{f.connector_code}</div>
                              </td>
                              <td style={{ padding: "0.75rem 0.5rem" }}><StatusBadge status={f.status} /></td>
                              <td style={{ padding: "0.75rem 0.5rem" }}>{f.retry_count} / {f.max_retries}</td>
                              <td style={{ padding: "0.75rem 0.5rem", color: "var(--text-muted)" }}>
                                {f.retry_after ? new Date(f.retry_after).toLocaleString() : "Immediate / None"}
                              </td>
                              <td style={{ padding: "0.75rem 0.5rem", textAlign: "right" }}>
                                <div style={{ display: "inline-flex", gap: "0.5rem" }}>
                                  {canRetry && (
                                    <button
                                      type="button"
                                      disabled={remediationActionLoading}
                                      onClick={() => void handleRetryFailure(f)}
                                      style={{
                                        padding: "0.3rem 0.6rem",
                                        borderRadius: "6px",
                                        fontSize: "0.75rem",
                                        background: "var(--glass-surface)",
                                        border: "1px solid var(--border-subtle)",
                                        color: "var(--text-primary)",
                                        cursor: "pointer",
                                      }}
                                    >
                                      Retry Now
                                    </button>
                                  )}
                                  {canResolve && (
                                    <button
                                      type="button"
                                      disabled={remediationActionLoading}
                                      onClick={() => setRemediatingFailure(f)}
                                      style={{
                                        padding: "0.3rem 0.6rem",
                                        borderRadius: "6px",
                                        fontSize: "0.75rem",
                                        background: "var(--status-success-bg)",
                                        border: "1px solid var(--status-success-border)",
                                        color: "var(--status-success)",
                                        cursor: "pointer",
                                      }}
                                    >
                                      Resolve
                                    </button>
                                  )}
                                </div>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </GlassPanel>
              </div>
            )}

            {/* TAB 4: Reconciliation Issues */}
            {activeTab === "reconciliation" && (
              <GlassPanel elevation="default" padding="lg">
                <h3 style={{ fontSize: "1rem", fontWeight: 600, marginBottom: "1rem" }}>
                  Open Reconciliation Issues ({diagnostics.reconciliation_issues.length})
                </h3>
                {diagnostics.reconciliation_issues.length === 0 ? (
                  <div style={{ padding: "2rem", textAlign: "center", color: "var(--text-muted)" }}>
                    <CheckCircleIcon size={32} style={{ color: "var(--status-success)", marginBottom: "0.5rem" }} />
                    <p>No open reconciliation issues for this organization.</p>
                  </div>
                ) : (
                  <div style={{ overflowX: "auto" }}>
                    <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.875rem" }}>
                      <thead>
                        <tr style={{ borderBottom: "1px solid var(--border-subtle)", textAlign: "left", color: "var(--text-muted)" }}>
                          <th style={{ padding: "0.75rem 0.5rem" }}>Issue Code</th>
                          <th style={{ padding: "0.75rem 0.5rem" }}>Severity</th>
                          <th style={{ padding: "0.75rem 0.5rem" }}>Description</th>
                          <th style={{ padding: "0.75rem 0.5rem" }}>Detected At</th>
                          <th style={{ padding: "0.75rem 0.5rem", textAlign: "right" }}>Actions</th>
                        </tr>
                      </thead>
                      <tbody>
                        {diagnostics.reconciliation_issues.map((issue) => (
                          <tr key={issue.id} style={{ borderBottom: "1px solid var(--border-subtle)" }}>
                            <td style={{ padding: "0.75rem 0.5rem", fontWeight: 600 }}>{issue.issue_code}</td>
                            <td style={{ padding: "0.75rem 0.5rem" }}><StatusBadge status={issue.severity} /></td>
                            <td style={{ padding: "0.75rem 0.5rem", color: "var(--text-secondary)" }}>
                              {issue.description}
                            </td>
                            <td style={{ padding: "0.75rem 0.5rem", color: "var(--text-muted)" }}>
                              {new Date(issue.detected_at).toLocaleString()}
                            </td>
                            <td style={{ padding: "0.75rem 0.5rem", textAlign: "right" }}>
                              {canResolve && (
                                <button
                                  type="button"
                                  disabled={remediationActionLoading}
                                  onClick={() => setRemediatingIssue(issue)}
                                  style={{
                                    padding: "0.3rem 0.6rem",
                                    borderRadius: "6px",
                                    fontSize: "0.75rem",
                                    background: "var(--status-success-bg)",
                                    border: "1px solid var(--status-success-border)",
                                    color: "var(--status-success)",
                                    cursor: "pointer",
                                  }}
                                >
                                  Resolve
                                </button>
                              )}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </GlassPanel>
            )}

            {/* TAB 5: Audit Log Trail */}
            {activeTab === "audit" && (
              <GlassPanel elevation="default" padding="lg">
                <h3 style={{ fontSize: "1rem", fontWeight: 600, marginBottom: "1rem" }}>
                  Recent Operational Audit Events ({diagnostics.recent_audit_logs.length})
                </h3>
                {diagnostics.recent_audit_logs.length === 0 ? (
                  <p style={{ color: "var(--text-muted)", fontSize: "0.875rem" }}>No audit log entries found.</p>
                ) : (
                  <div style={{ overflowX: "auto" }}>
                    <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.875rem" }}>
                      <thead>
                        <tr style={{ borderBottom: "1px solid var(--border-subtle)", textAlign: "left", color: "var(--text-muted)" }}>
                          <th style={{ padding: "0.75rem 0.5rem" }}>Timestamp</th>
                          <th style={{ padding: "0.75rem 0.5rem" }}>Action</th>
                          <th style={{ padding: "0.75rem 0.5rem" }}>Target</th>
                          <th style={{ padding: "0.75rem 0.5rem" }}>Source</th>
                        </tr>
                      </thead>
                      <tbody>
                        {diagnostics.recent_audit_logs.map((entry) => (
                          <tr key={entry.id} style={{ borderBottom: "1px solid var(--border-subtle)" }}>
                            <td style={{ padding: "0.75rem 0.5rem", color: "var(--text-muted)" }}>
                              {new Date(entry.timestamp).toLocaleString()}
                            </td>
                            <td style={{ padding: "0.75rem 0.5rem", fontWeight: 500 }}>{entry.action}</td>
                            <td style={{ padding: "0.75rem 0.5rem" }}>
                              {entry.target_repr}{" "}
                              <span style={{ fontSize: "0.6875rem", color: "var(--text-muted)" }}>
                                ({entry.target_type})
                              </span>
                            </td>
                            <td style={{ padding: "0.75rem 0.5rem", color: "var(--text-secondary)" }}>
                              {entry.operation_source}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </GlassPanel>
            )}
          </div>
        )}
        </div>
        )}

        {/* SUPPORT OPERATOR ADMINISTRATION VIEW (Phase 6C) */}
        {consoleView === "operators" && (
          <div>
            {/* Notices specific to operators */}
            {operatorsError && (
              <div
                style={{
                  padding: "1rem",
                  borderRadius: "8px",
                  background: "var(--status-danger-bg)",
                  border: "1px solid var(--status-danger-border)",
                  color: "var(--status-danger)",
                  marginBottom: "1.5rem",
                  display: "flex",
                  alignItems: "center",
                  gap: "0.5rem",
                }}
              >
                <AlertCircleIcon size={18} />
                <span>{operatorsError}</span>
              </div>
            )}
            {operatorsSuccess && (
              <div
                style={{
                  padding: "1rem",
                  borderRadius: "8px",
                  background: "var(--status-success-bg)",
                  border: "1px solid var(--status-success-border)",
                  color: "var(--status-success)",
                  marginBottom: "1.5rem",
                  display: "flex",
                  alignItems: "center",
                  gap: "0.5rem",
                }}
              >
                <CheckCircleIcon size={18} />
                <span>{operatorsSuccess}</span>
              </div>
            )}

            {!isOwner ? (
              <GlassPanel elevation="default" padding="lg">
                <div style={{ color: "var(--status-danger)", display: "flex", alignItems: "center", gap: "0.5rem" }}>
                  <AlertCircleIcon size={20} />
                  <span>Platform Owner privileges are required to administer support operator roles.</span>
                </div>
              </GlassPanel>
            ) : (
              <GlassPanel elevation="default" padding="lg">
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    flexWrap: "wrap",
                    gap: "1rem",
                    marginBottom: "1.5rem",
                  }}
                >
                  <div>
                    <h2 style={{ fontSize: "1.25rem", fontWeight: 700, margin: 0, color: "var(--text-primary)" }}>
                      Platform Support Operator Role Assignments
                    </h2>
                    <p style={{ margin: "0.25rem 0 0 0", color: "var(--text-secondary)", fontSize: "0.875rem" }}>
                      Grant and revoke canonical platform support roles. Enforces server authorization, transactional audit logging, duplicate idempotency, and strict tenant isolation.
                    </p>
                  </div>
                  <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
                    <button
                      type="button"
                      onClick={() => void loadOperators()}
                      disabled={loadingOperators}
                      style={{
                        display: "flex",
                        alignItems: "center",
                        gap: "0.4rem",
                        fontSize: "0.8125rem",
                        padding: "0.5rem 0.85rem",
                        borderRadius: "6px",
                        background: "var(--glass-surface)",
                        border: "1px solid var(--border-subtle)",
                        color: "var(--text-secondary)",
                        cursor: "pointer",
                      }}
                    >
                      <RefreshIcon size={14} />
                      <span>{loadingOperators ? "Refreshing..." : "Refresh"}</span>
                    </button>
                    <button
                      type="button"
                      onClick={handleOpenGrantModal}
                      className="btn-primary"
                      style={{
                        display: "flex",
                        alignItems: "center",
                        gap: "0.4rem",
                        fontSize: "0.8125rem",
                        padding: "0.5rem 1rem",
                        borderRadius: "6px",
                        fontWeight: 600,
                      }}
                    >
                      <PlusIcon size={16} />
                      <span>Grant Support Role</span>
                    </button>
                  </div>
                </div>

                {loadingOperators && operators.length === 0 ? (
                  <div style={{ padding: "3rem", textAlign: "center" }}>
                    <LoadingSpinner label="Loading support operator assignments..." />
                  </div>
                ) : operators.length === 0 ? (
                  <div style={{ textAlign: "center", padding: "3rem 1rem", color: "var(--text-muted)" }}>
                    <p style={{ margin: 0, fontSize: "0.9375rem" }}>No support operators currently assigned.</p>
                    <p style={{ margin: "0.5rem 0 0 0", fontSize: "0.8125rem" }}>
                      Click <strong>Grant Support Role</strong> to assign a canonical support role to an active platform user.
                    </p>
                  </div>
                ) : (
                  <div style={{ overflowX: "auto" }}>
                    <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.875rem" }}>
                      <thead>
                        <tr style={{ borderBottom: "1px solid var(--border-subtle)", textAlign: "left", color: "var(--text-muted)" }}>
                          <th style={{ padding: "0.75rem 0.5rem" }}>User</th>
                          <th style={{ padding: "0.75rem 0.5rem" }}>User ID</th>
                          <th style={{ padding: "0.75rem 0.5rem" }}>Assigned Role</th>
                          <th style={{ padding: "0.75rem 0.5rem" }}>Role Code</th>
                          <th style={{ padding: "0.75rem 0.5rem" }}>Granted At</th>
                          <th style={{ padding: "0.75rem 0.5rem", textAlign: "right" }}>Actions</th>
                        </tr>
                      </thead>
                      <tbody>
                        {operators.map((op) => (
                          <tr key={op.id} style={{ borderBottom: "1px solid var(--border-subtle)" }}>
                            <td style={{ padding: "0.75rem 0.5rem", fontWeight: 500 }}>
                              <div>{op.user_name || op.user_email || "User"}</div>
                              {op.user_email && (
                                <div style={{ fontSize: "0.75rem", color: "var(--text-secondary)" }}>
                                  {op.user_email}
                                </div>
                              )}
                            </td>
                            <td style={{ padding: "0.75rem 0.5rem" }}>
                              <code style={{ fontSize: "0.75rem" }}>{op.user_id}</code>
                            </td>
                            <td style={{ padding: "0.75rem 0.5rem", fontWeight: 600 }}>
                              {op.role_name}
                            </td>
                            <td style={{ padding: "0.75rem 0.5rem" }}>
                              <StatusBadge status={op.role_code} />
                            </td>
                            <td style={{ padding: "0.75rem 0.5rem", color: "var(--text-secondary)" }}>
                              {new Date(op.created_at).toLocaleString()}
                            </td>
                            <td style={{ padding: "0.75rem 0.5rem", textAlign: "right" }}>
                              <button
                                type="button"
                                disabled={revokingId === op.id}
                                onClick={() => void handleRevoke(op)}
                                style={{
                                  padding: "0.35rem 0.75rem",
                                  fontSize: "0.75rem",
                                  fontWeight: 600,
                                  borderRadius: "6px",
                                  background: "rgba(239, 68, 68, 0.12)",
                                  color: "#ef4444",
                                  border: "1px solid rgba(239, 68, 68, 0.35)",
                                  cursor: revokingId === op.id ? "not-allowed" : "pointer",
                                  opacity: revokingId === op.id ? 0.6 : 1,
                                }}
                              >
                                {revokingId === op.id ? "Revoking..." : "Revoke"}
                              </button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </GlassPanel>
            )}
          </div>
        )}

        {/* MODAL: Resolve Failure (Phase 6C-4) */}
        {remediatingFailure && (
          <div
            style={{
              position: "fixed",
              inset: 0,
              background: "rgba(0, 0, 0, 0.6)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              zIndex: 1000,
              padding: "1rem",
            }}
          >
            <GlassPanel elevation="elevated" padding="xl" style={{ maxWidth: "500px", width: "100%" }}>
              <h3 style={{ fontSize: "1.125rem", fontWeight: 700, marginBottom: "0.5rem" }}>
                Resolve Integration Failure
              </h3>
              <p style={{ fontSize: "0.875rem", color: "var(--text-secondary)", marginBottom: "1rem" }}>
                Resolving failure <code>{remediatingFailure.id}</code> ({remediatingFailure.failure_code}). An audited reason is mandatory.
              </p>
              {remediationError && (
                <div style={{ color: "var(--status-danger)", fontSize: "0.8125rem", marginBottom: "0.75rem" }}>
                  {remediationError}
                </div>
              )}
              <textarea
                rows={4}
                placeholder="Enter mandatory resolution notes (1-500 chars)..."
                value={resolutionReason}
                onChange={(e) => setResolutionReason(e.target.value)}
                style={{
                  width: "100%",
                  padding: "0.75rem",
                  borderRadius: "8px",
                  background: "var(--input-bg, var(--glass-surface))",
                  border: "1px solid var(--border-subtle)",
                  color: "var(--text-primary)",
                  fontSize: "0.875rem",
                  marginBottom: "1rem",
                  resize: "vertical",
                }}
              />
              <div style={{ display: "flex", justifyContent: "flex-end", gap: "0.75rem" }}>
                <button
                  type="button"
                  disabled={remediationActionLoading}
                  onClick={() => {
                    setRemediatingFailure(null);
                    setResolutionReason("");
                    setRemediationError(null);
                  }}
                  className="btn-secondary"
                  style={{ padding: "0.5rem 1rem" }}
                >
                  Cancel
                </button>
                <button
                  type="button"
                  disabled={remediationActionLoading || resolutionReason.trim().length === 0}
                  onClick={() => void handleResolveFailureSubmit()}
                  className="btn-primary"
                  style={{ padding: "0.5rem 1rem" }}
                >
                  {remediationActionLoading ? "Resolving..." : "Confirm Resolve"}
                </button>
              </div>
            </GlassPanel>
          </div>
        )}

        {/* MODAL: Resolve Reconciliation Issue (Phase 6C-4) */}
        {remediatingIssue && (
          <div
            style={{
              position: "fixed",
              inset: 0,
              background: "rgba(0, 0, 0, 0.6)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              zIndex: 1000,
              padding: "1rem",
            }}
          >
            <GlassPanel elevation="elevated" padding="xl" style={{ maxWidth: "500px", width: "100%" }}>
              <h3 style={{ fontSize: "1.125rem", fontWeight: 700, marginBottom: "0.5rem" }}>
                Resolve Reconciliation Issue
              </h3>
              <p style={{ fontSize: "0.875rem", color: "var(--text-secondary)", marginBottom: "1rem" }}>
                Resolving issue <code>{remediatingIssue.issue_code}</code> on {remediatingIssue.instance_label}. An audited reason is mandatory.
              </p>
              {remediationError && (
                <div style={{ color: "var(--status-danger)", fontSize: "0.8125rem", marginBottom: "0.75rem" }}>
                  {remediationError}
                </div>
              )}
              <textarea
                rows={4}
                placeholder="Enter mandatory resolution notes (1-500 chars)..."
                value={resolutionReason}
                onChange={(e) => setResolutionReason(e.target.value)}
                style={{
                  width: "100%",
                  padding: "0.75rem",
                  borderRadius: "8px",
                  background: "var(--input-bg, var(--glass-surface))",
                  border: "1px solid var(--border-subtle)",
                  color: "var(--text-primary)",
                  fontSize: "0.875rem",
                  marginBottom: "1rem",
                  resize: "vertical",
                }}
              />
              <div style={{ display: "flex", justifyContent: "flex-end", gap: "0.75rem" }}>
                <button
                  type="button"
                  disabled={remediationActionLoading}
                  onClick={() => {
                    setRemediatingIssue(null);
                    setResolutionReason("");
                    setRemediationError(null);
                  }}
                  className="btn-secondary"
                  style={{ padding: "0.5rem 1rem" }}
                >
                  Cancel
                </button>
                <button
                  type="button"
                  disabled={remediationActionLoading || resolutionReason.trim().length === 0}
                  onClick={() => void handleResolveReconciliationSubmit()}
                  className="btn-primary"
                  style={{ padding: "0.5rem 1rem" }}
                >
                  {remediationActionLoading ? "Resolving..." : "Confirm Resolve"}
                </button>
              </div>
            </GlassPanel>
          </div>
        )}

        {/* MODAL: Initiate Impersonation Session (Phase 6D) */}
        {impersonateModalOpen && (
          <div
            style={{
              position: "fixed",
              inset: 0,
              background: "rgba(0, 0, 0, 0.65)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              zIndex: 1000,
              padding: "1rem",
            }}
          >
            <GlassPanel elevation="elevated" padding="xl" style={{ maxWidth: "540px", width: "100%" }}>
              <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.5rem" }}>
                <div style={{ color: "#ea580c" }}>
                  <ShieldCheckIcon size={20} />
                </div>
                <h3 style={{ fontSize: "1.25rem", fontWeight: 700, margin: 0, color: "var(--text-primary)" }}>
                  Initiate Support Impersonation
                </h3>
              </div>
              <p style={{ fontSize: "0.875rem", color: "var(--text-secondary)", marginBottom: "1rem", lineHeight: 1.4 }}>
                Start a time-limited (max 30 minutes), strictly audited session. Platform Owners and other Support Operators are strictly ineligible targets.
              </p>

              {impersonationError && (
                <div
                  style={{
                    color: "var(--status-danger)",
                    fontSize: "0.8125rem",
                    marginBottom: "1rem",
                    padding: "0.5rem 0.75rem",
                    background: "rgba(239, 68, 68, 0.1)",
                    borderRadius: "6px",
                  }}
                >
                  {impersonationError}
                </div>
              )}

              {impersonationLoading && eligibleTargets.length === 0 ? (
                <div style={{ display: "flex", justifyContent: "center", padding: "2rem" }}>
                  <LoadingSpinner fullScreen={false} label="Loading eligible users..." />
                </div>
              ) : (
                <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
                  <div>
                    <label style={{ display: "block", fontSize: "0.8125rem", fontWeight: 600, marginBottom: "0.35rem" }}>
                      Target User (Tenant Admin or Member) *
                    </label>
                    {eligibleTargets.length === 0 ? (
                      <div style={{ fontSize: "0.8125rem", color: "var(--text-muted)" }}>
                        No eligible target users found in this organization.
                      </div>
                    ) : (
                      <select
                        value={selectedTargetUserId}
                        onChange={(e) => setSelectedTargetUserId(e.target.value)}
                        style={{
                          width: "100%",
                          padding: "0.6rem 0.75rem",
                          borderRadius: "8px",
                          background: "var(--input-bg, var(--glass-surface))",
                          border: "1px solid var(--border-subtle)",
                          color: "var(--text-primary)",
                          fontSize: "0.875rem",
                        }}
                      >
                        {eligibleTargets.map((t) => (
                          <option key={t.id} value={t.id}>
                            {t.full_name} ({t.email}) — [{t.membership_type.replace("_", " ").toUpperCase()}]
                          </option>
                        ))}
                      </select>
                    )}
                  </div>

                  <div>
                    <label style={{ display: "block", fontSize: "0.8125rem", fontWeight: 600, marginBottom: "0.35rem" }}>
                      Operational Justification / Reason * (1-500 characters)
                    </label>
                    <textarea
                      rows={3}
                      placeholder="Enter mandatory reason for impersonation (e.g., investigating LMS SSO course sync failure)..."
                      value={impersonationReason}
                      onChange={(e) => setImpersonationReason(e.target.value)}
                      style={{
                        width: "100%",
                        padding: "0.6rem 0.75rem",
                        borderRadius: "8px",
                        background: "var(--input-bg, var(--glass-surface))",
                        border: "1px solid var(--border-subtle)",
                        color: "var(--text-primary)",
                        fontSize: "0.875rem",
                        resize: "vertical",
                      }}
                    />
                    <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginTop: "0.25rem", textAlign: "right" }}>
                      {impersonationReason.trim().length}/500 chars
                    </div>
                  </div>

                  <div>
                    <label style={{ display: "block", fontSize: "0.8125rem", fontWeight: 600, marginBottom: "0.35rem" }}>
                      Ticket / Incident Reference (Required)
                    </label>
                    <input
                      type="text"
                      placeholder="e.g. INC-82914 or JIRA-4029"
                      value={impersonationTicketRef}
                      onChange={(e) => setImpersonationTicketRef(e.target.value)}
                      style={{
                        width: "100%",
                        padding: "0.6rem 0.75rem",
                        borderRadius: "8px",
                        background: "var(--input-bg, var(--glass-surface))",
                        border: "1px solid var(--border-subtle)",
                        color: "var(--text-primary)",
                        fontSize: "0.875rem",
                      }}
                    />
                  </div>
                </div>
              )}

              <div style={{ display: "flex", justifyContent: "flex-end", gap: "0.75rem", marginTop: "1.5rem" }}>
                <button
                  type="button"
                  disabled={impersonationLoading}
                  onClick={() => {
                    setImpersonateModalOpen(false);
                    setImpersonationError(null);
                  }}
                  className="btn-secondary"
                  style={{ padding: "0.5rem 1rem" }}
                >
                  Cancel
                </button>
                <button
                  type="button"
                  disabled={
                    impersonationLoading ||
                    !selectedTargetUserId ||
                    impersonationReason.trim().length === 0 ||
                    impersonationTicketRef.trim().length === 0 ||
                    eligibleTargets.length === 0
                  }
                  onClick={() => void handleStartImpersonationSubmit()}
                  style={{
                    background: "#ea580c",
                    color: "#ffffff",
                    border: "none",
                    borderRadius: "8px",
                    padding: "0.5rem 1.25rem",
                    fontWeight: 600,
                    fontSize: "0.875rem",
                    cursor: "pointer",
                    opacity:
                      impersonationLoading ||
                      !selectedTargetUserId ||
                      impersonationReason.trim().length === 0 ||
                      impersonationTicketRef.trim().length === 0
                        ? 0.5
                        : 1,
                  }}
                >
                  {impersonationLoading ? "Starting Session..." : "Confirm & Impersonate"}
                </button>
              </div>
            </GlassPanel>
          </div>
        )}

        {/* MODAL: Grant Support Operator Role (Phase 6C) */}
        {grantModalOpen && (
          <div
            style={{
              position: "fixed",
              top: 0,
              left: 0,
              right: 0,
              bottom: 0,
              backgroundColor: "rgba(0, 0, 0, 0.6)",
              backdropFilter: "blur(4px)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              zIndex: 1000,
              padding: "1rem",
            }}
          >
            <GlassPanel elevation="elevated" padding="xl" style={{ maxWidth: "560px", width: "100%" }}>
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "0.5rem" }}>
                <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                  <div style={{ color: "#3b82f6" }}>
                    <ShieldCheckIcon size={22} />
                  </div>
                  <h3 style={{ fontSize: "1.25rem", fontWeight: 700, margin: 0, color: "var(--text-primary)" }}>
                    Grant Predefined Support Role
                  </h3>
                </div>
                <button
                  type="button"
                  onClick={() => {
                    setGrantModalOpen(false);
                    setGrantError(null);
                  }}
                  style={{
                    background: "none",
                    border: "none",
                    color: "var(--text-muted)",
                    cursor: "pointer",
                    padding: "0.25rem",
                  }}
                  aria-label="Close"
                >
                  <CloseIcon size={20} />
                </button>
              </div>
              <p style={{ fontSize: "0.875rem", color: "var(--text-secondary)", marginBottom: "1rem", lineHeight: 1.4 }}>
                Assign an authorized platform support role to an active platform user. This grant is transactionally recorded in immutable audit logs.
              </p>

              {grantError && (
                <div
                  style={{
                    color: "var(--status-danger)",
                    fontSize: "0.8125rem",
                    marginBottom: "1rem",
                    padding: "0.5rem 0.75rem",
                    background: "rgba(239, 68, 68, 0.1)",
                    borderRadius: "6px",
                    display: "flex",
                    alignItems: "center",
                    gap: "0.5rem",
                  }}
                >
                  <AlertCircleIcon size={16} />
                  <span>{grantError}</span>
                </div>
              )}

              <div style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>
                <div>
                  <label style={{ display: "block", fontSize: "0.8125rem", fontWeight: 600, marginBottom: "0.35rem" }}>
                    Target User ID (UUID) *
                  </label>
                  <input
                    type="text"
                    placeholder="e.g. 550e8400-e29b-41d4-a716-446655440000"
                    value={grantUserId}
                    onChange={(e) => setGrantUserId(e.target.value)}
                    disabled={grantLoading}
                    style={{
                      width: "100%",
                      padding: "0.6rem 0.75rem",
                      borderRadius: "8px",
                      background: "var(--input-bg, var(--glass-surface))",
                      border: "1px solid var(--border-subtle)",
                      color: "var(--text-primary)",
                      fontSize: "0.875rem",
                      boxSizing: "border-box",
                    }}
                  />
                  <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginTop: "0.25rem" }}>
                    Enter the UUID of the target active platform user.
                  </div>
                </div>

                <div>
                  <label style={{ display: "block", fontSize: "0.8125rem", fontWeight: 600, marginBottom: "0.35rem" }}>
                    Predefined Support Role *
                  </label>
                  <select
                    value={grantRoleCode}
                    onChange={(e) => setGrantRoleCode(e.target.value)}
                    disabled={grantLoading}
                    style={{
                      width: "100%",
                      padding: "0.6rem 0.75rem",
                      borderRadius: "8px",
                      background: "var(--input-bg, var(--glass-surface))",
                      border: "1px solid var(--border-subtle)",
                      color: "var(--text-primary)",
                      fontSize: "0.875rem",
                      boxSizing: "border-box",
                    }}
                  >
                    {CANONICAL_SUPPORT_ROLES.map((role) => (
                      <option key={role.code} value={role.code}>
                        {role.name} ({role.code})
                      </option>
                    ))}
                  </select>
                  <div
                    style={{
                      marginTop: "0.5rem",
                      padding: "0.6rem 0.75rem",
                      borderRadius: "6px",
                      background: "var(--glass-surface)",
                      border: "1px solid var(--border-subtle)",
                      fontSize: "0.8125rem",
                      color: "var(--text-secondary)",
                    }}
                  >
                    {CANONICAL_SUPPORT_ROLES.find((r) => r.code === grantRoleCode)?.description}
                  </div>
                </div>

                <div
                  style={{
                    padding: "0.75rem",
                    borderRadius: "6px",
                    background: "rgba(59, 130, 246, 0.08)",
                    border: "1px solid rgba(59, 130, 246, 0.2)",
                    fontSize: "0.75rem",
                    color: "var(--text-secondary)",
                    lineHeight: 1.4,
                  }}
                >
                  <strong>Security Policy:</strong>
                  <ul style={{ margin: "0.25rem 0 0 0", paddingLeft: "1.25rem" }}>
                    <li>Support roles never grant Platform Owner or superuser privileges.</li>
                    <li>Platform Owners and superusers cannot be assigned support operator roles.</li>
                    <li>Support roles are platform-scoped and strictly excluded from tenant assignment.</li>
                    <li>Target user must be active; disabled/inactive accounts are rejected.</li>
                  </ul>
                </div>
              </div>

              <div style={{ display: "flex", justifyContent: "flex-end", gap: "0.75rem", marginTop: "1.5rem" }}>
                <button
                  type="button"
                  disabled={grantLoading}
                  onClick={() => {
                    setGrantModalOpen(false);
                    setGrantError(null);
                  }}
                  className="btn-secondary"
                  style={{ padding: "0.5rem 1rem" }}
                >
                  Cancel
                </button>
                <button
                  type="button"
                  disabled={grantLoading || !grantUserId.trim()}
                  onClick={() => void handleGrantSubmit()}
                  className="btn-primary"
                  style={{
                    padding: "0.5rem 1.25rem",
                    fontWeight: 600,
                    fontSize: "0.875rem",
                    opacity: grantLoading || !grantUserId.trim() ? 0.6 : 1,
                  }}
                >
                  {grantLoading ? "Granting Role..." : "Grant Role"}
                </button>
              </div>
            </GlassPanel>
          </div>
        )}
      </div>
    </AppShell>
  );
};
