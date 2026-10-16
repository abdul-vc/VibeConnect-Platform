import React, { useEffect, useState, useCallback } from "react";
import { AppShell } from "../../components/AppShell.tsx";
import { auditApi, AUDIT_ACTION_LABELS, formatUtcDateTime } from "../../api/audit.ts";
import type { AuditLogListItem } from "../../api/types.ts";
import { LoadingSpinner } from "../../components/LoadingSpinner.tsx";
import { HistoryIcon, RotateCcwIcon, SearchIcon } from "../../components/Icons.tsx";

export const TenantActivityLogPage: React.FC = () => {
  const [logs, setLogs] = useState<readonly AuditLogListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");

  const loadLogs = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await auditApi.listTenant({
        search: search || undefined,
        page_size: 50,
      });
      setLogs(res.results || []);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to load organization audit events.");
    } finally {
      setLoading(false);
    }
  }, [search]);

  useEffect(() => {
    void loadLogs();
  }, [loadLogs]);

  return (
    <AppShell>
      <div style={{ maxWidth: "1080px", margin: "0 auto", padding: "1.75rem 1rem" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "1.75rem" }}>
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <HistoryIcon size={24} color="var(--brand-primary, #6366f1)" />
              <h1 style={{ fontSize: "1.5rem", fontWeight: 800, margin: 0, color: "var(--text-primary)" }}>
                Organization Activity Log
              </h1>
            </div>
            <p style={{ color: "var(--text-muted)", fontSize: "0.88rem", marginTop: 4 }}>
              Immutable, read-only audit log of administrative activities and membership actions scoped exclusively to your organization.
            </p>
          </div>
          <button
            type="button"
            onClick={() => void loadLogs()}
            className="btn-secondary"
            style={{ display: "inline-flex", alignItems: "center", gap: 6, padding: "0.45rem 0.9rem", fontSize: "0.82rem" }}
          >
            <RotateCcwIcon size={14} /> Refresh
          </button>
        </div>

        {error && (
          <div style={{ padding: "0.85rem 1rem", background: "rgba(239, 68, 68, 0.1)", border: "1px solid rgba(239, 68, 68, 0.3)", borderRadius: 8, color: "#f87171", marginBottom: "1.25rem", fontSize: "0.88rem" }}>
            {error}
          </div>
        )}

        {/* Search */}
        <div style={{ marginBottom: "1.25rem" }}>
          <div style={{ position: "relative", maxWidth: "380px" }}>
            <span style={{ position: "absolute", left: 12, top: 10, color: "var(--text-muted)" }}>
              <SearchIcon size={16} />
            </span>
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search audit actions, target, or actor…"
              style={{
                width: "100%",
                padding: "0.55rem 0.75rem 0.55rem 2.25rem",
                borderRadius: 8,
                background: "var(--surface-raised, #0f172a)",
                border: "1px solid var(--border-glass, rgba(255, 255, 255, 0.15))",
                color: "var(--text-primary)",
                fontSize: "0.88rem",
                boxSizing: "border-box",
              }}
            />
          </div>
        </div>

        {loading ? (
          <div style={{ display: "flex", justifyContent: "center", padding: "4rem" }}>
            <LoadingSpinner label="Loading organization audit trail…" />
          </div>
        ) : logs.length === 0 ? (
          <div
            style={{
              padding: "3rem 1.5rem",
              textAlign: "center",
              color: "var(--text-muted)",
              background: "var(--surface-card, #1e293b)",
              borderRadius: 14,
              border: "1px dashed var(--border-glass, rgba(255, 255, 255, 0.1))",
            }}
          >
            No audit records recorded for this organization matching criteria.
          </div>
        ) : (
          <div
            style={{
              background: "var(--surface-card, #1e293b)",
              border: "1px solid var(--border-glass, rgba(255, 255, 255, 0.1))",
              borderRadius: 14,
              overflow: "hidden",
            }}
          >
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.88rem", textAlign: "left" }}>
              <thead>
                <tr style={{ borderBottom: "1px solid var(--border-glass, rgba(255, 255, 255, 0.1))", background: "rgba(0, 0, 0, 0.2)" }}>
                  <th style={{ padding: "0.85rem 1rem", color: "var(--text-muted)", fontWeight: 600 }}>Timestamp (UTC)</th>
                  <th style={{ padding: "0.85rem 1rem", color: "var(--text-muted)", fontWeight: 600 }}>Action</th>
                  <th style={{ padding: "0.85rem 1rem", color: "var(--text-muted)", fontWeight: 600 }}>Target</th>
                  <th style={{ padding: "0.85rem 1rem", color: "var(--text-muted)", fontWeight: 600 }}>Actor</th>
                </tr>
              </thead>
              <tbody>
                {logs.map((log) => (
                  <tr
                    key={log.id}
                    style={{
                      borderBottom: "1px solid var(--border-glass, rgba(255, 255, 255, 0.05))",
                    }}
                  >
                    <td style={{ padding: "0.85rem 1rem", color: "var(--text-muted)", fontSize: "0.8rem", whiteSpace: "nowrap" }}>
                      {formatUtcDateTime(log.timestamp)}
                    </td>
                    <td style={{ padding: "0.85rem 1rem" }}>
                      <span
                        style={{
                          display: "inline-block",
                          padding: "2px 8px",
                          borderRadius: 999,
                          fontSize: "0.72rem",
                          fontWeight: 700,
                          background: "rgba(99, 102, 241, 0.15)",
                          color: "#818cf8",
                        }}
                      >
                        {AUDIT_ACTION_LABELS[log.action] || log.action}
                      </span>
                    </td>
                    <td style={{ padding: "0.85rem 1rem" }}>
                      <div style={{ fontWeight: 600, color: "var(--text-primary)" }}>{log.target_repr}</div>
                      <div style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>{log.target_type}</div>
                    </td>
                    <td style={{ padding: "0.85rem 1rem" }}>
                      <div style={{ color: "var(--text-primary)" }}>{log.actor?.full_name || log.actor?.email || "System"}</div>
                      <div style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>{log.actor?.email || "system@internal"}</div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </AppShell>
  );
};
