/**
 * Integration Hub Owner Page (Phase 5A–5G).
 *
 * Operational console for Platform Owners to inspect:
 * - Connector Registry
 * - Deployed Connector Instances
 * - Control Plane Health & Aggregated Operational Metrics
 * - Failures, Retry Scheduling & Dead-Letter Recovery (Phase 5G)
 *
 * Centralized API client used exclusively.
 */

import React, { useEffect, useState, useCallback } from "react";
import { AppShell } from "../../components/AppShell.tsx";
import {
  integrationApi,
  IntegrationConnector,
  ConnectorInstance,
  IntegrationFailure,
  IntegrationHealthSummary,
} from "../../api/integration.ts";

function StatusBadge({ status }: { status: string }) {
  const norm = (status || "").toLowerCase();
  let bg = "var(--glass-surface)";
  let color = "var(--text-muted)";
  let border = "var(--border-subtle)";

  if (norm === "active" || norm === "resolved" || norm === "healthy") {
    bg = "var(--status-success-bg, rgba(34, 197, 94, 0.15))";
    color = "var(--status-success, #22c55e)";
    border = "var(--status-success-border, rgba(34, 197, 94, 0.3))";
  } else if (norm === "suspended" || norm === "deprecated" || norm === "retry_scheduled" || norm === "degraded") {
    bg = "var(--status-warning-bg, rgba(245, 158, 11, 0.15))";
    color = "var(--status-warning, #f59e0b)";
    border = "var(--status-warning-border, rgba(245, 158, 11, 0.3))";
  } else if (norm === "disconnected" || norm === "retired" || norm === "dead_letter" || norm === "attention_required") {
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

export const IntegrationHubPage: React.FC = () => {
  const [connectors, setConnectors] = useState<IntegrationConnector[]>([]);
  const [instances, setInstances] = useState<ConnectorInstance[]>([]);
  const [health, setHealth] = useState<IntegrationHealthSummary | null>(null);
  const [failures, setFailures] = useState<IntegrationFailure[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [successNotice, setSuccessNotice] = useState<string | null>(null);

  // Failure filters & modal state
  const [statusFilter, setStatusFilter] = useState<string>("");
  const [resolvingFailure, setResolvingFailure] = useState<IntegrationFailure | null>(null);
  const [resolutionNotes, setResolutionNotes] = useState<string>("");
  const [detailFailure, setDetailFailure] = useState<IntegrationFailure | null>(null);
  const [actionLoading, setActionLoading] = useState<boolean>(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [probing, setProbing] = useState<boolean>(false);

  const handleProbeConnectivity = async () => {
    setProbing(true);
    setError(null);
    try {
      const h = await integrationApi.getHealth(true);
      setHealth(h);
      if (h.external_connectivity.status === "verified") {
        setSuccessNotice("External LMS connectivity probe verified successfully.");
      } else {
        setSuccessNotice(`External connectivity probe completed: status is ${h.external_connectivity.status}.`);
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to probe external connectivity.");
    } finally {
      setProbing(false);
    }
  };

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [connList, instRes, healthRes, failRes] = await Promise.all([
        integrationApi.listConnectors(),
        integrationApi.listInstances().then((r) => r.results),
        integrationApi.getHealth().catch(() => null),
        integrationApi
          .listFailures({ status: statusFilter || undefined })
          .then((r) => r.results)
          .catch(() => []),
      ]);
      setConnectors(connList || []);
      setInstances(instRes || []);
      setHealth(healthRes);
      setFailures(failRes || []);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to load integration hub data.");
    } finally {
      setLoading(false);
    }
  }, [statusFilter]);

  useEffect(() => {
    void fetchData();
  }, [fetchData]);

  // Recovery actions
  const handleOpenResolve = (f: IntegrationFailure) => {
    setResolvingFailure(f);
    setResolutionNotes("");
    setActionError(null);
  };

  const handleCloseResolve = () => {
    setResolvingFailure(null);
    setResolutionNotes("");
    setActionError(null);
  };

  const handleSubmitResolve = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!resolvingFailure) return;
    if (!resolutionNotes.trim()) {
      setActionError("Resolution notes are required for audit trail.");
      return;
    }

    setActionLoading(true);
    setActionError(null);
    try {
      await integrationApi.resolveFailure(resolvingFailure.id, resolutionNotes.trim());
      setSuccessNotice(`Failure [${resolvingFailure.failure_code}] resolved successfully.`);
      handleCloseResolve();
      void fetchData();
    } catch (err: unknown) {
      setActionError(err instanceof Error ? err.message : "Failed to resolve failure.");
    } finally {
      setActionLoading(false);
    }
  };

  const handleMarkDeadLetter = async (f: IntegrationFailure) => {
    if (!window.confirm(`Mark failure [${f.failure_code}] as dead-letter? This is a terminal state.`)) {
      return;
    }
    setActionLoading(true);
    try {
      await integrationApi.markFailureDeadLetter(f.id, "Manually marked as dead-letter by Platform Owner.");
      setSuccessNotice(`Failure [${f.failure_code}] transitioned to dead-letter.`);
      void fetchData();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to mark as dead-letter.");
    } finally {
      setActionLoading(false);
    }
  };

  const handleScheduleRetry = async (f: IntegrationFailure) => {
    setActionLoading(true);
    try {
      const res = await integrationApi.scheduleFailureRetry(f.id);
      setSuccessNotice(
        `Retry scheduled for failure [${f.failure_code}]. State: ${res.status.replace(/_/g, " ")}. Scheduled execution pending.`
      );
      void fetchData();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to schedule retry.");
    } finally {
      setActionLoading(false);
    }
  };

  const handleReplay = async (f: IntegrationFailure) => {
    if (
      !window.confirm(
        `Replay dead-letter failure [${f.failure_code}]? This will immediately re-execute provisioning through the canonical integration pipeline.`
      )
    ) {
      return;
    }
    setActionLoading(true);
    try {
      const res = await integrationApi.replayFailure(f.id);
      const norm = (res.status || "").toLowerCase();
      if (norm === "resolved") {
        setSuccessNotice(`Failure [${f.failure_code}] replayed and successfully resolved.`);
      } else if (norm === "retry_scheduled") {
        setSuccessNotice(`Failure [${f.failure_code}] replayed: transient error encountered, retry scheduled.`);
      } else {
        setSuccessNotice(`Failure [${f.failure_code}] replayed: resulting state is ${res.status.replace(/_/g, " ")}.`);
      }
      void fetchData();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to replay dead-letter failure.");
    } finally {
      setActionLoading(false);
    }
  };


  const activeInstancesCount = instances.filter((i) => (i.status || "").toLowerCase() === "active").length;
  const attentionInstancesCount = instances.filter((i) => (i.status || "").toLowerCase() !== "active").length;

  return (
    <AppShell>
      <div style={{ display: "flex", flexDirection: "column", gap: "1.75rem", minWidth: 0 }}>
        {/* Header */}
        <div
          style={{
            background: "var(--glass-surface-elevated)",
            border: "1px solid var(--border-glass)",
            borderRadius: "14px",
            padding: "1.75rem",
            display: "flex",
            justifyContent: "space-between",
            alignItems: "flex-start",
            flexWrap: "wrap",
            gap: "1rem",
          }}
        >
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: "0.6rem", marginBottom: "0.35rem" }}>
              <span
                style={{
                  display: "inline-block",
                  width: "10px",
                  height: "10px",
                  borderRadius: "50%",
                  backgroundColor: "var(--brand-primary, #6366f1)",
                  boxShadow: "0 0 10px var(--brand-primary, #6366f1)",
                }}
              />
              <span
                style={{
                  fontSize: "0.75rem",
                  fontWeight: 600,
                  textTransform: "uppercase",
                  letterSpacing: "0.08em",
                  color: "var(--brand-primary, #6366f1)",
                }}
              >
                Control Plane • Platform Owner
              </span>
            </div>
            <h1
              style={{
                fontSize: "1.75rem",
                fontWeight: 700,
                color: "var(--text-primary)",
                margin: "0 0 0.4rem 0",
              }}
            >
              Integration Hub & Operational Health
            </h1>
            <p
              style={{
                fontSize: "0.9375rem",
                color: "var(--text-secondary)",
                margin: 0,
                maxWidth: "680px",
                lineHeight: 1.5,
              }}
            >
              Control plane operational health, connector registry, tenant deployments, and failure recovery.
            </p>
          </div>

          <button
            type="button"
            onClick={() => void fetchData()}
            disabled={loading}
            className="btn-secondary"
            style={{
              padding: "0.5rem 1rem",
              borderRadius: "8px",
              cursor: loading ? "not-allowed" : "pointer",
              fontSize: "0.875rem",
              display: "inline-flex",
              alignItems: "center",
              gap: "0.4rem",
            }}
          >
            {loading ? "Refreshing..." : "Refresh Status"}
          </button>
        </div>

        {/* High-Level Control Plane & Operational Metrics Summary */}
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))",
            gap: "1rem",
          }}
        >
          <div
            style={{
              background: "var(--glass-surface)",
              border: "1px solid var(--border-subtle)",
              borderRadius: "12px",
              padding: "1.25rem",
            }}
          >
            <div style={{ fontSize: "0.8125rem", color: "var(--text-muted)", marginBottom: "0.35rem" }}>
              Control Plane Status
            </div>
            <div style={{ fontSize: "1.25rem", fontWeight: 700, marginTop: "0.25rem" }}>
              {health ? <StatusBadge status={health.control_plane.status} /> : "—"}
            </div>
          </div>

          <div
            style={{
              background: "var(--glass-surface)",
              border: "1px solid var(--border-subtle)",
              borderRadius: "12px",
              padding: "1.25rem",
            }}
          >
            <div style={{ fontSize: "0.8125rem", color: "var(--text-muted)", marginBottom: "0.35rem" }}>
              Active Instances
            </div>
            <div style={{ fontSize: "1.75rem", fontWeight: 700, color: "var(--status-success, #22c55e)" }}>
              {loading ? "—" : activeInstancesCount}
            </div>
          </div>

          <div
            style={{
              background: "var(--glass-surface)",
              border: "1px solid var(--border-subtle)",
              borderRadius: "12px",
              padding: "1.25rem",
            }}
          >
            <div
              style={{
                fontSize: "0.8125rem",
                color: attentionInstancesCount > 0 ? "var(--status-warning, #f59e0b)" : "var(--text-muted)",
                marginBottom: "0.35rem",
              }}
            >
              Attention Required
            </div>
            <div
              style={{
                fontSize: "1.75rem",
                fontWeight: 700,
                color: attentionInstancesCount > 0 ? "var(--status-warning, #f59e0b)" : "var(--text-primary)",
              }}
            >
              {loading ? "—" : attentionInstancesCount}
            </div>
          </div>

          <div
            style={{
              background: "var(--glass-surface)",
              border: "1px solid var(--border-subtle)",
              borderRadius: "12px",
              padding: "1.25rem",
            }}
          >
            <div style={{ fontSize: "0.8125rem", color: "var(--text-muted)", marginBottom: "0.35rem" }}>
              Queued Jobs
            </div>
            <div
              style={{
                fontSize: "1.75rem",
                fontWeight: 700,
                color: "var(--text-primary)",
              }}
            >
              {health && health.summary ? health.summary.queued_job_count : "—"}
            </div>
          </div>

          <div
            style={{
              background: "var(--glass-surface)",
              border: "1px solid var(--border-subtle)",
              borderRadius: "12px",
              padding: "1.25rem",
            }}
          >
            <div
              style={{
                fontSize: "0.8125rem",
                color:
                  health &&
                  health.summary &&
                  health.summary.stuck_queued_job_count + health.summary.stuck_processing_job_count > 0
                    ? "var(--status-danger, #ef4444)"
                    : "var(--text-muted)",
                marginBottom: "0.35rem",
              }}
            >
              Stuck Jobs
            </div>
            <div
              style={{
                fontSize: "1.75rem",
                fontWeight: 700,
                color:
                  health &&
                  health.summary &&
                  health.summary.stuck_queued_job_count + health.summary.stuck_processing_job_count > 0
                    ? "var(--status-danger, #ef4444)"
                    : "var(--text-primary)",
              }}
            >
              {health && health.summary
                ? health.summary.stuck_queued_job_count + health.summary.stuck_processing_job_count
                : "—"}
            </div>
          </div>

          <div
            style={{
              background: "var(--glass-surface)",
              border: "1px solid var(--border-subtle)",
              borderRadius: "12px",
              padding: "1.25rem",
            }}
          >
            <div style={{ fontSize: "0.8125rem", color: "var(--text-muted)", marginBottom: "0.35rem" }}>
              Scheduled Retries
            </div>
            <div
              style={{
                fontSize: "1.75rem",
                fontWeight: 700,
                color:
                  health && health.failures.total_retry_scheduled > 0
                    ? "var(--status-warning, #f59e0b)"
                    : "var(--text-primary)",
              }}
            >
              {health ? health.failures.total_retry_scheduled : "—"}
            </div>
          </div>

          <div
            style={{
              background: "var(--glass-surface)",
              border: "1px solid var(--border-subtle)",
              borderRadius: "12px",
              padding: "1.25rem",
            }}
          >
            <div style={{ fontSize: "0.8125rem", color: "var(--text-muted)", marginBottom: "0.35rem" }}>
              Dead-Letter (Terminal)
            </div>
            <div
              style={{
                fontSize: "1.75rem",
                fontWeight: 700,
                color:
                  health && health.failures.total_dead_letter > 0
                    ? "var(--status-danger, #ef4444)"
                    : "var(--text-primary)",
              }}
            >
              {health ? health.failures.total_dead_letter : "—"}
            </div>
          </div>

          <div
            style={{
              background: "var(--glass-surface)",
              border: "1px solid var(--border-subtle)",
              borderRadius: "12px",
              padding: "1.25rem",
            }}
          >
            <div style={{ fontSize: "0.8125rem", color: "var(--text-muted)", marginBottom: "0.35rem" }}>
              Recent Failures (24h)
            </div>
            <div
              style={{
                fontSize: "1.75rem",
                fontWeight: 700,
                color:
                  health && health.failures.recent_24h_count > 0
                    ? "var(--status-warning, #f59e0b)"
                    : "var(--text-primary)",
              }}
            >
              {health ? health.failures.recent_24h_count : "—"}
            </div>
            {health && health.summary && (
              <div style={{ fontSize: "0.75rem", color: "var(--text-secondary)", marginTop: "0.2rem" }}>
                Failure Rate: {health.summary.failure_rate}%
              </div>
            )}
          </div>
        </div>

        {/* External Connectivity Transparency & Probe Card */}
        <div
          style={{
            background:
              health?.external_connectivity?.status === "verified"
                ? "rgba(34, 197, 94, 0.05)"
                : health?.external_connectivity?.status === "unreachable"
                ? "rgba(239, 68, 68, 0.05)"
                : "rgba(59, 130, 246, 0.05)",
            border: `1px solid ${
              health?.external_connectivity?.status === "verified"
                ? "rgba(34, 197, 94, 0.2)"
                : health?.external_connectivity?.status === "unreachable"
                ? "rgba(239, 68, 68, 0.2)"
                : "rgba(59, 130, 246, 0.2)"
            }`,
            borderRadius: "12px",
            padding: "1rem 1.25rem",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            flexWrap: "wrap",
            gap: "0.75rem",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", flex: 1, minWidth: "260px" }}>
            <span
              style={{
                display: "inline-block",
                width: "8px",
                height: "8px",
                borderRadius: "50%",
                backgroundColor:
                  health?.external_connectivity?.status === "verified"
                    ? "#22c55e"
                    : health?.external_connectivity?.status === "unreachable"
                    ? "#ef4444"
                    : "#3b82f6",
              }}
            />
            <div style={{ fontSize: "0.875rem", color: "var(--text-secondary)" }}>
              <strong style={{ color: "var(--text-primary)" }}>External Connectivity:</strong>{" "}
              {health?.external_connectivity?.detail ||
                "Control-plane state verified. Real-time downstream SaaS network health probes are pending product adapter configurations."}
              {health?.external_connectivity?.latency_ms != null && (
                <span style={{ marginLeft: "0.5rem", color: "var(--text-muted)", fontSize: "0.75rem" }}>
                  ({health.external_connectivity.latency_ms}ms)
                </span>
              )}
            </div>
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
            <span
              style={{
                fontSize: "0.75rem",
                padding: "0.2rem 0.5rem",
                borderRadius: "4px",
                background:
                  health?.external_connectivity?.status === "verified"
                    ? "rgba(34, 197, 94, 0.15)"
                    : health?.external_connectivity?.status === "unreachable"
                    ? "rgba(239, 68, 68, 0.15)"
                    : "rgba(59, 130, 246, 0.15)",
                color:
                  health?.external_connectivity?.status === "verified"
                    ? "#22c55e"
                    : health?.external_connectivity?.status === "unreachable"
                    ? "#ef4444"
                    : "#3b82f6",
                fontWeight: 600,
              }}
            >
              {health?.external_connectivity?.status === "verified"
                ? "Connectivity Verified"
                : health?.external_connectivity?.status === "unreachable"
                ? "Downstream Unreachable"
                : "Control-Plane Only (Not Verified)"}
            </span>

            <button
              type="button"
              onClick={() => void handleProbeConnectivity()}
              disabled={probing}
              className="btn-secondary"
              style={{
                fontSize: "0.75rem",
                padding: "0.25rem 0.6rem",
                borderRadius: "6px",
                cursor: probing ? "not-allowed" : "pointer",
              }}
            >
              {probing ? "Probing LMS..." : "Probe External LMS"}
            </button>
          </div>
        </div>

        {/* Loading and Notifications */}
        {loading && (
          <div
            aria-live="polite"
            style={{
              padding: "1.5rem",
              textAlign: "center",
              color: "var(--text-muted)",
              background: "var(--glass-surface)",
              borderRadius: "10px",
              border: "1px solid var(--border-subtle)",
            }}
          >
            Loading integration hub…
          </div>
        )}

        {error && (
          <div
            role="alert"
            style={{
              padding: "1.25rem",
              background: "var(--status-danger-bg, rgba(239, 68, 68, 0.15))",
              border: "1px solid var(--status-danger-border, rgba(239, 68, 68, 0.3))",
              borderRadius: "10px",
              color: "var(--status-danger, #ef4444)",
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
            }}
          >
            <span>{error}</span>
            <button
              type="button"
              onClick={() => void fetchData()}
              className="btn-secondary"
              style={{ fontSize: "0.8125rem", padding: "0.3rem 0.75rem" }}
            >
              Retry
            </button>
          </div>
        )}

        {successNotice && (
          <div
            role="status"
            style={{
              padding: "1rem 1.25rem",
              background: "var(--status-success-bg, rgba(34, 197, 94, 0.15))",
              border: "1px solid var(--status-success-border, rgba(34, 197, 94, 0.3))",
              borderRadius: "10px",
              color: "var(--status-success, #22c55e)",
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
            }}
          >
            <span>{successNotice}</span>
            <button
              type="button"
              onClick={() => setSuccessNotice(null)}
              style={{ background: "transparent", border: "none", color: "inherit", cursor: "pointer", fontWeight: 700 }}
            >
              ✕
            </button>
          </div>
        )}

        {/* ── Phase 5G: Failures & Dead-Letter Recovery Section ──────────────── */}
        <div
          style={{
            background: "var(--glass-surface-elevated)",
            border: "1px solid var(--border-glass)",
            borderRadius: "14px",
            padding: "1.5rem",
          }}
        >
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              flexWrap: "wrap",
              gap: "1rem",
              marginBottom: "1rem",
            }}
          >
            <div>
              <h2 style={{ fontSize: "1.15rem", fontWeight: 600, color: "var(--text-primary)", margin: "0 0 0.2rem 0" }}>
                Integration Failures & Dead-Letter Recovery
              </h2>
              <p style={{ fontSize: "0.8125rem", color: "var(--text-muted)", margin: 0 }}>
                Operational failures, backoff schedule, dead-letter quarantine, and manual resolution audit trail.
              </p>
            </div>

            {/* Filter Pills */}
            <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
              {[
                { label: "All", value: "" },
                { label: "Open", value: "open" },
                { label: "Retry Scheduled", value: "retry_scheduled" },
                { label: "Dead Letter", value: "dead_letter" },
                { label: "Resolved", value: "resolved" },
              ].map((pill) => (
                <button
                  key={pill.value}
                  type="button"
                  onClick={() => setStatusFilter(pill.value)}
                  style={{
                    padding: "0.35rem 0.75rem",
                    borderRadius: "6px",
                    fontSize: "0.8125rem",
                    fontWeight: statusFilter === pill.value ? 600 : 400,
                    background: statusFilter === pill.value ? "var(--brand-primary, #6366f1)" : "var(--glass-surface)",
                    color: statusFilter === pill.value ? "#ffffff" : "var(--text-secondary)",
                    border: "1px solid var(--border-subtle)",
                    cursor: "pointer",
                  }}
                >
                  {pill.label}
                </button>
              ))}
            </div>
          </div>

          {failures.length === 0 ? (
            <div
              style={{
                padding: "2.5rem 1rem",
                textAlign: "center",
                background: "var(--glass-surface)",
                borderRadius: "10px",
                border: "1px dashed var(--border-subtle)",
                color: "var(--text-muted)",
              }}
            >
              <div style={{ fontSize: "1rem", fontWeight: 600, color: "var(--text-primary)", marginBottom: "0.35rem" }}>
                No integration failures recorded.
              </div>
              <div style={{ fontSize: "0.875rem" }}>
                All integration operations and events are running without active errors or dead-letter records.
              </div>
            </div>
          ) : (
            <div style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.875rem" }}>
                <thead>
                  <tr style={{ borderBottom: "1px solid var(--border-subtle)", textAlign: "left" }}>
                    <th style={{ padding: "0.75rem", color: "var(--text-secondary)", fontWeight: 600 }}>Failure Code</th>
                    <th style={{ padding: "0.75rem", color: "var(--text-secondary)", fontWeight: 600 }}>Type</th>
                    <th style={{ padding: "0.75rem", color: "var(--text-secondary)", fontWeight: 600 }}>Instance / Org</th>
                    <th style={{ padding: "0.75rem", color: "var(--text-secondary)", fontWeight: 600 }}>Retries</th>
                    <th style={{ padding: "0.75rem", color: "var(--text-secondary)", fontWeight: 600 }}>Status</th>
                    <th style={{ padding: "0.75rem", color: "var(--text-secondary)", fontWeight: 600 }}>Occurred</th>
                    <th style={{ padding: "0.75rem", color: "var(--text-secondary)", fontWeight: 600, textAlign: "right" }}>
                      Recovery Actions
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {failures.map((f) => (
                    <tr
                      key={f.id}
                      style={{
                        borderBottom: "1px solid var(--border-glass)",
                        transition: "background-color 0.15s ease",
                      }}
                    >
                      <td style={{ padding: "0.75rem" }}>
                        <code
                          style={{
                            fontSize: "0.75rem",
                            background: "var(--glass-surface)",
                            padding: "0.2rem 0.5rem",
                            borderRadius: "4px",
                            border: "1px solid var(--border-subtle)",
                            color: "var(--text-primary)",
                            fontWeight: 600,
                          }}
                        >
                          {f.failure_code}
                        </code>
                      </td>
                      <td style={{ padding: "0.75rem", textTransform: "capitalize", color: "var(--text-secondary)" }}>
                        {f.failure_type}
                      </td>
                      <td style={{ padding: "0.75rem" }}>
                        <div style={{ fontWeight: 600, color: "var(--text-primary)" }}>
                          {f.instance_label || "Global / Unassigned"}
                        </div>
                        <div style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
                          {f.organization_name || f.connector_code || "—"}
                        </div>
                      </td>
                      <td style={{ padding: "0.75rem", color: "var(--text-secondary)" }}>
                        {f.retry_count} / {f.max_retries}
                        {f.retry_after && (
                          <div style={{ fontSize: "0.75rem", color: "var(--status-warning, #f59e0b)" }}>
                            Next: {new Date(f.retry_after).toLocaleTimeString()}
                          </div>
                        )}
                      </td>
                      <td style={{ padding: "0.75rem" }}>
                        <StatusBadge status={f.status} />
                      </td>
                      <td style={{ padding: "0.75rem", color: "var(--text-muted)", fontSize: "0.75rem" }}>
                        {f.created_at ? new Date(f.created_at).toLocaleString() : "—"}
                      </td>
                      <td style={{ padding: "0.75rem", textAlign: "right" }}>
                        <div style={{ display: "inline-flex", gap: "0.4rem", justifyContent: "flex-end" }}>
                          <button
                            type="button"
                            onClick={() => setDetailFailure(f)}
                            className="btn-secondary"
                            style={{ padding: "0.25rem 0.6rem", fontSize: "0.75rem", borderRadius: "6px" }}
                          >
                            Details
                          </button>

                          {f.status !== "resolved" && (
                            <>
                              {f.status !== "dead_letter" && (
                                <>
                                  <button
                                    type="button"
                                    onClick={() => void handleScheduleRetry(f)}
                                    disabled={actionLoading}
                                    className="btn-secondary"
                                    style={{
                                      padding: "0.25rem 0.6rem",
                                      fontSize: "0.75rem",
                                      borderRadius: "6px",
                                      color: "var(--status-warning, #f59e0b)",
                                    }}
                                    title="Calculates backoff and schedules retry in control plane"
                                  >
                                    Schedule Retry
                                  </button>
                                  <button
                                    type="button"
                                    onClick={() => void handleMarkDeadLetter(f)}
                                    disabled={actionLoading}
                                    className="btn-secondary"
                                    style={{
                                      padding: "0.25rem 0.6rem",
                                      fontSize: "0.75rem",
                                      borderRadius: "6px",
                                      color: "var(--status-danger, #ef4444)",
                                    }}
                                  >
                                    Dead-Letter
                                  </button>
                                </>
                              )}
                              {f.status === "dead_letter" && (
                                <button
                                  type="button"
                                  onClick={() => void handleReplay(f)}
                                  disabled={actionLoading}
                                  className="btn-secondary"
                                  style={{
                                    padding: "0.25rem 0.6rem",
                                    fontSize: "0.75rem",
                                    borderRadius: "6px",
                                    color: "var(--brand-primary, #6366f1)",
                                    fontWeight: 600,
                                  }}
                                  title="Re-execute provisioning for this dead-letter failure"
                                >
                                  Replay
                                </button>
                              )}
                              <button
                                type="button"
                                onClick={() => handleOpenResolve(f)}
                                disabled={actionLoading}
                                style={{
                                  padding: "0.25rem 0.6rem",
                                  fontSize: "0.75rem",
                                  borderRadius: "6px",
                                  background: "var(--status-success-bg, rgba(34, 197, 94, 0.15))",
                                  color: "var(--status-success, #22c55e)",
                                  border: "1px solid var(--status-success-border, rgba(34, 197, 94, 0.3))",
                                  cursor: "pointer",
                                  fontWeight: 600,
                                }}
                              >
                                Resolve
                              </button>
                            </>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* ── Connector Registry Section ────────────────────────────────────── */}
        {!loading && (
          <div
            style={{
              background: "var(--glass-surface-elevated)",
              border: "1px solid var(--border-glass)",
              borderRadius: "14px",
              padding: "1.5rem",
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1rem" }}>
              <div>
                <h2 style={{ fontSize: "1.15rem", fontWeight: 600, color: "var(--text-primary)", margin: "0 0 0.2rem 0" }}>
                  Connector Registry
                </h2>
                <p style={{ fontSize: "0.8125rem", color: "var(--text-muted)", margin: 0 }}>
                  Master catalog of integration connectors supported across products.
                </p>
              </div>
            </div>

            {connectors.length === 0 ? (
              <div
                style={{
                  padding: "2.5rem 1rem",
                  textAlign: "center",
                  background: "var(--glass-surface)",
                  borderRadius: "10px",
                  border: "1px dashed var(--border-subtle)",
                  color: "var(--text-muted)",
                }}
              >
                <div style={{ fontSize: "1rem", fontWeight: 600, color: "var(--text-primary)", marginBottom: "0.35rem" }}>
                  No connectors registered yet.
                </div>
              </div>
            ) : (
              <div style={{ overflowX: "auto" }}>
                <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.875rem" }}>
                  <thead>
                    <tr style={{ borderBottom: "1px solid var(--border-subtle)", textAlign: "left" }}>
                      <th style={{ padding: "0.75rem", color: "var(--text-secondary)", fontWeight: 600 }}>Connector</th>
                      <th style={{ padding: "0.75rem", color: "var(--text-secondary)", fontWeight: 600 }}>Code</th>
                      <th style={{ padding: "0.75rem", color: "var(--text-secondary)", fontWeight: 600 }}>Version</th>
                      <th style={{ padding: "0.75rem", color: "var(--text-secondary)", fontWeight: 600 }}>Status</th>
                      <th style={{ padding: "0.75rem", color: "var(--text-secondary)", fontWeight: 600 }}>Instances</th>
                      <th style={{ padding: "0.75rem", color: "var(--text-secondary)", fontWeight: 600 }}>Registered</th>
                    </tr>
                  </thead>
                  <tbody>
                    {connectors.map((c) => {
                      const count = instances.filter((i) => i.connector === c.id).length;
                      return (
                        <tr
                          key={c.id}
                          style={{
                            borderBottom: "1px solid var(--border-glass)",
                            transition: "background-color 0.15s ease",
                          }}
                        >
                          <td style={{ padding: "0.75rem", fontWeight: 600, color: "var(--text-primary)" }}>
                            {c.name}
                            {c.description && (
                              <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", fontWeight: 400, marginTop: "0.15rem" }}>
                                {c.description}
                              </div>
                            )}
                          </td>
                          <td style={{ padding: "0.75rem" }}>
                            <code
                              style={{
                                fontSize: "0.75rem",
                                background: "var(--glass-surface)",
                                padding: "0.2rem 0.5rem",
                                borderRadius: "4px",
                                border: "1px solid var(--border-subtle)",
                                color: "var(--text-primary)",
                              }}
                            >
                              {c.code}
                            </code>
                          </td>
                          <td style={{ padding: "0.75rem", color: "var(--text-secondary)" }}>v{c.version}</td>
                          <td style={{ padding: "0.75rem" }}>
                            <StatusBadge status={c.status} />
                          </td>
                          <td style={{ padding: "0.75rem", color: "var(--text-primary)", fontWeight: 600 }}>
                            {count}
                          </td>
                          <td style={{ padding: "0.75rem", color: "var(--text-muted)", fontSize: "0.75rem" }}>
                            {c.created_at ? new Date(c.created_at).toLocaleDateString() : "—"}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}

        {/* ── Connector Instances Section ───────────────────────────────────── */}
        {!loading && (
          <div
            style={{
              background: "var(--glass-surface-elevated)",
              border: "1px solid var(--border-glass)",
              borderRadius: "14px",
              padding: "1.5rem",
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1rem" }}>
              <div>
                <h2 style={{ fontSize: "1.15rem", fontWeight: 600, color: "var(--text-primary)", margin: "0 0 0.2rem 0" }}>
                  Connector Instances
                </h2>
                <p style={{ fontSize: "0.8125rem", color: "var(--text-muted)", margin: 0 }}>
                  Tenant organization deployments with opaque credential pointers. Plaintext secrets are never stored.
                </p>
              </div>
            </div>

            {instances.length === 0 ? (
              <div
                style={{
                  padding: "2.5rem 1rem",
                  textAlign: "center",
                  background: "var(--glass-surface)",
                  borderRadius: "10px",
                  border: "1px dashed var(--border-subtle)",
                  color: "var(--text-muted)",
                }}
              >
                <div style={{ fontSize: "1rem", fontWeight: 600, color: "var(--text-primary)", marginBottom: "0.35rem" }}>
                  No connector instances configured.
                </div>
              </div>
            ) : (
              <div style={{ overflowX: "auto" }}>
                <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.875rem" }}>
                  <thead>
                    <tr style={{ borderBottom: "1px solid var(--border-subtle)", textAlign: "left" }}>
                      <th style={{ padding: "0.75rem", color: "var(--text-secondary)", fontWeight: 600 }}>Instance</th>
                      <th style={{ padding: "0.75rem", color: "var(--text-secondary)", fontWeight: 600 }}>Connector</th>
                      <th style={{ padding: "0.75rem", color: "var(--text-secondary)", fontWeight: 600 }}>Tenant Organization</th>
                      <th style={{ padding: "0.75rem", color: "var(--text-secondary)", fontWeight: 600 }}>Credential Reference</th>
                      <th style={{ padding: "0.75rem", color: "var(--text-secondary)", fontWeight: 600 }}>Status</th>
                      <th style={{ padding: "0.75rem", color: "var(--text-secondary)", fontWeight: 600 }}>Updated</th>
                    </tr>
                  </thead>
                  <tbody>
                    {instances.map((inst) => (
                      <tr
                        key={inst.id}
                        style={{
                          borderBottom: "1px solid var(--border-glass)",
                          transition: "background-color 0.15s ease",
                        }}
                      >
                        <td style={{ padding: "0.75rem", fontWeight: 600, color: "var(--text-primary)" }}>
                          {inst.label || "Untitled Instance"}
                        </td>
                        <td style={{ padding: "0.75rem" }}>
                          <code
                            style={{
                              fontSize: "0.75rem",
                              background: "var(--glass-surface)",
                              padding: "0.2rem 0.5rem",
                              borderRadius: "4px",
                              border: "1px solid var(--border-subtle)",
                              color: "var(--text-primary)",
                            }}
                          >
                            {inst.connector_code || inst.connector}
                          </code>
                        </td>
                        <td style={{ padding: "0.75rem", color: "var(--text-primary)" }}>
                          {inst.organization_name || inst.organization}
                        </td>
                        <td style={{ padding: "0.75rem" }}>
                          <code
                            style={{
                              fontSize: "0.75rem",
                              background: "var(--glass-surface)",
                              padding: "0.2rem 0.5rem",
                              borderRadius: "4px",
                              border: "1px solid var(--border-subtle)",
                              color: "var(--text-muted)",
                            }}
                            title="Opaque pointer reference, never contains plaintext secrets"
                          >
                            {inst.credential_ref || "—"}
                          </code>
                        </td>
                        <td style={{ padding: "0.75rem" }}>
                          <StatusBadge status={inst.status} />
                        </td>
                        <td style={{ padding: "0.75rem", color: "var(--text-muted)", fontSize: "0.75rem" }}>
                          {inst.updated_at ? new Date(inst.updated_at).toLocaleDateString() : "—"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}

        {/* ── Resolve Failure Modal ─────────────────────────────────────────── */}
        {resolvingFailure && (
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
              padding: "1rem",
            }}
          >
            <div
              style={{
                background: "var(--glass-surface-elevated, #18181b)",
                border: "1px solid var(--border-glass, rgba(255, 255, 255, 0.1))",
                borderRadius: "14px",
                width: "100%",
                maxWidth: "520px",
                padding: "1.75rem",
              }}
            >
              <h3 style={{ fontSize: "1.2rem", fontWeight: 700, margin: "0 0 0.5rem 0", color: "var(--text-primary)" }}>
                Resolve Integration Failure
              </h3>
              <p style={{ fontSize: "0.875rem", color: "var(--text-secondary)", margin: "0 0 1.25rem 0" }}>
                Provide an audit explanation of how this integration failure was investigated and resolved.
              </p>

              <div style={{ marginBottom: "1rem", fontSize: "0.8125rem", color: "var(--text-muted)" }}>
                <div><strong>Code:</strong> {resolvingFailure.failure_code}</div>
                <div><strong>Target:</strong> {resolvingFailure.instance_label || "Global"} ({resolvingFailure.organization_name})</div>
              </div>

              {actionError && (
                <div
                  style={{
                    padding: "0.75rem",
                    marginBottom: "1rem",
                    background: "var(--status-danger-bg, rgba(239, 68, 68, 0.15))",
                    border: "1px solid var(--status-danger-border, rgba(239, 68, 68, 0.3))",
                    borderRadius: "8px",
                    color: "var(--status-danger, #ef4444)",
                    fontSize: "0.8125rem",
                  }}
                >
                  {actionError}
                </div>
              )}

              <form onSubmit={(e) => void handleSubmitResolve(e)}>
                <label
                  style={{
                    display: "block",
                    fontSize: "0.8125rem",
                    fontWeight: 600,
                    marginBottom: "0.35rem",
                    color: "var(--text-primary)",
                  }}
                >
                  Resolution Notes <span style={{ color: "var(--status-danger, #ef4444)" }}>*</span>
                </label>
                <textarea
                  rows={4}
                  value={resolutionNotes}
                  onChange={(e) => setResolutionNotes(e.target.value)}
                  placeholder="e.g. Verified external provider configuration, reconciled mapping, and confirmed health."
                  required
                  style={{
                    width: "100%",
                    padding: "0.75rem",
                    borderRadius: "8px",
                    background: "var(--glass-surface)",
                    border: "1px solid var(--border-subtle)",
                    color: "var(--text-primary)",
                    fontSize: "0.875rem",
                    resize: "vertical",
                    boxSizing: "border-box",
                    marginBottom: "1.25rem",
                  }}
                />

                <div style={{ display: "flex", justifyContent: "flex-end", gap: "0.75rem" }}>
                  <button
                    type="button"
                    onClick={handleCloseResolve}
                    disabled={actionLoading}
                    className="btn-secondary"
                    style={{ padding: "0.5rem 1rem", borderRadius: "8px", fontSize: "0.875rem" }}
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={actionLoading}
                    style={{
                      padding: "0.5rem 1.25rem",
                      borderRadius: "8px",
                      background: "var(--brand-primary, #6366f1)",
                      color: "#ffffff",
                      border: "none",
                      fontSize: "0.875rem",
                      fontWeight: 600,
                      cursor: actionLoading ? "not-allowed" : "pointer",
                    }}
                  >
                    {actionLoading ? "Resolving..." : "Confirm Resolution"}
                  </button>
                </div>
              </form>
            </div>
          </div>
        )}

        {/* ── Diagnostic Detail Modal ───────────────────────────────────────── */}
        {detailFailure && (
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
              padding: "1rem",
            }}
          >
            <div
              style={{
                background: "var(--glass-surface-elevated, #18181b)",
                border: "1px solid var(--border-glass, rgba(255, 255, 255, 0.1))",
                borderRadius: "14px",
                width: "100%",
                maxWidth: "600px",
                padding: "1.75rem",
              }}
            >
              <h3 style={{ fontSize: "1.2rem", fontWeight: 700, margin: "0 0 0.75rem 0", color: "var(--text-primary)" }}>
                Failure Diagnostic Detail
              </h3>

              <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem", fontSize: "0.875rem" }}>
                <div>
                  <span style={{ color: "var(--text-muted)" }}>Failure Code: </span>
                  <strong style={{ color: "var(--text-primary)" }}>{detailFailure.failure_code}</strong>
                </div>
                <div>
                  <span style={{ color: "var(--text-muted)" }}>Status: </span>
                  <StatusBadge status={detailFailure.status} />
                </div>
                <div>
                  <span style={{ color: "var(--text-muted)" }}>Classification: </span>
                  <span style={{ textTransform: "capitalize", color: "var(--text-primary)" }}>{detailFailure.failure_type}</span>
                </div>
                <div>
                  <span style={{ color: "var(--text-muted)" }}>Retries: </span>
                  <span style={{ color: "var(--text-primary)" }}>{detailFailure.retry_count} of {detailFailure.max_retries} max</span>
                </div>
                <div>
                  <span style={{ color: "var(--text-muted)" }}>Target Instance: </span>
                  <span style={{ color: "var(--text-primary)" }}>{detailFailure.instance_label || "None"}</span>
                </div>
                <div>
                  <span style={{ color: "var(--text-muted)" }}>Organization: </span>
                  <span style={{ color: "var(--text-primary)" }}>{detailFailure.organization_name || "None"}</span>
                </div>

                <div>
                  <div style={{ color: "var(--text-muted)", marginBottom: "0.25rem" }}>Diagnostic Detail:</div>
                  <pre
                    style={{
                      background: "var(--glass-surface)",
                      border: "1px solid var(--border-subtle)",
                      borderRadius: "8px",
                      padding: "0.75rem",
                      fontSize: "0.8125rem",
                      color: "var(--text-secondary)",
                      whiteSpace: "pre-wrap",
                      wordBreak: "break-word",
                      maxHeight: "160px",
                      overflowY: "auto",
                      margin: 0,
                    }}
                  >
                    {detailFailure.failure_detail || "No additional detail recorded."}
                  </pre>
                </div>

                {detailFailure.resolution_notes && (
                  <div>
                    <div style={{ color: "var(--status-success, #22c55e)", fontWeight: 600, marginBottom: "0.25rem" }}>
                      Resolution Notes (Audited):
                    </div>
                    <div
                      style={{
                        background: "var(--glass-surface)",
                        border: "1px solid var(--border-subtle)",
                        borderRadius: "8px",
                        padding: "0.75rem",
                        fontSize: "0.8125rem",
                        color: "var(--text-primary)",
                      }}
                    >
                      {detailFailure.resolution_notes}
                      <div style={{ marginTop: "0.35rem", fontSize: "0.75rem", color: "var(--text-muted)" }}>
                        Resolved by: {detailFailure.resolved_by_email || "Platform Owner"} on{" "}
                        {detailFailure.resolved_at ? new Date(detailFailure.resolved_at).toLocaleString() : "—"}
                      </div>
                    </div>
                  </div>
                )}
              </div>

              <div style={{ display: "flex", justifyContent: "flex-end", marginTop: "1.5rem" }}>
                <button
                  type="button"
                  onClick={() => setDetailFailure(null)}
                  className="btn-secondary"
                  style={{ padding: "0.5rem 1.25rem", borderRadius: "8px", fontSize: "0.875rem" }}
                >
                  Close
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </AppShell>
  );
};
