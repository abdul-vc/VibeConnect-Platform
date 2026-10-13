/**
 * Platform Owner Developer Oversight Page (Phase 6B Stage 4).
 *
 * Route: /owner/developer-oversight
 * Context Guard: platform_owner
 * Cross-tenant oversight, lifecycle controls, and emergency revocation.
 */

import React, { useState, useEffect, useCallback } from "react";
import { AppShell } from "../../components/AppShell.tsx";
import { GlassPanel } from "../../components/GlassPanel.tsx";
import { LoadingSpinner } from "../../components/LoadingSpinner.tsx";
import { CodeIcon, ShieldCheckIcon } from "../../components/Icons.tsx";
import {
  developerApi,
  type DeveloperApplication,
  type DeveloperApiKey,
} from "../../api/developer.ts";

export const OwnerDeveloperOversightPage: React.FC = () => {
  const [apps, setApps] = useState<DeveloperApplication[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [searchTerm, setSearchTerm] = useState<string>("");
  const [statusFilter, setStatusFilter] = useState<string>("");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  // Key inspection modal
  const [inspectApp, setInspectApp] = useState<DeveloperApplication | null>(null);
  const [appKeys, setAppKeys] = useState<DeveloperApiKey[]>([]);
  const [isLoadingKeys, setIsLoadingKeys] = useState<boolean>(false);

  // Emergency Revocation Modal
  const [emergencyTarget, setEmergencyTarget] = useState<{
    app: DeveloperApplication;
    key: DeveloperApiKey;
  } | null>(null);
  const [emergencyReason, setEmergencyReason] = useState<string>("");
  const [isSubmittingEmergency, setIsSubmittingEmergency] = useState<boolean>(false);

  const fetchApps = useCallback(async () => {
    setIsLoading(true);
    setErrorMessage(null);
    try {
      const res = await developerApi.listOwnerApps({
        search: searchTerm,
        status: statusFilter,
      });
      setApps(res.results || []);
    } catch (err) {
      setErrorMessage("Failed to load developer applications oversight data.");
    } finally {
      setIsLoading(false);
    }
  }, [searchTerm, statusFilter]);

  useEffect(() => {
    void fetchApps();
  }, [fetchApps]);

  const loadKeys = async (app: DeveloperApplication) => {
    setInspectApp(app);
    setIsLoadingKeys(true);
    try {
      const res = await developerApi.listOwnerKeys(app.id);
      setAppKeys(res.results || []);
    } catch (err) {
      setErrorMessage("Failed to load application keys.");
    } finally {
      setIsLoadingKeys(false);
    }
  };

  const handleAdminSuspendApp = async (app: DeveloperApplication) => {
    const reason = window.prompt(`Provide administrative reason for suspending "${app.name}":`, "Security compliance hold");
    if (!reason) return;

    try {
      await developerApi.suspendOwnerApp(app.id, reason);
      setSuccessMessage(`Application "${app.name}" suspended by Platform Owner.`);
      void fetchApps();
      if (inspectApp?.id === app.id) {
        setInspectApp({ ...app, status: "suspended" });
      }
    } catch (err) {
      setErrorMessage("Failed to administratively suspend application.");
    }
  };

  const handleAdminRevokeApp = async (app: DeveloperApplication) => {
    const reason = window.prompt(
      `CRITICAL: Permanently revoke "${app.name}" across tenant ${app.organization.name}? All keys will be immediately revoked.\nEnter rationale:`,
      "Platform emergency revocation"
    );
    if (!reason) return;

    try {
      await developerApi.revokeOwnerApp(app.id, reason);
      setSuccessMessage(`Application "${app.name}" permanently revoked by Platform Owner.`);
      void fetchApps();
      if (inspectApp?.id === app.id) {
        setInspectApp({ ...app, status: "revoked" });
        void loadKeys(app);
      }
    } catch (err) {
      setErrorMessage("Failed to revoke application.");
    }
  };

  const handleEmergencyRevokeKey = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!emergencyTarget || !emergencyReason.trim()) return;

    setIsSubmittingEmergency(true);
    try {
      await developerApi.revokeOwnerKey(
        emergencyTarget.app.id,
        emergencyTarget.key.id,
        emergencyReason.trim()
      );
      setSuccessMessage(`Key "${emergencyTarget.key.name}" revoked under emergency security procedure.`);
      setEmergencyTarget(null);
      setEmergencyReason("");
      void loadKeys(emergencyTarget.app);
    } catch (err) {
      setErrorMessage("Emergency key revocation failed.");
    } finally {
      setIsSubmittingEmergency(false);
    }
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case "active":
        return <span className="badge badge-success">Active</span>;
      case "suspended":
        return <span className="badge badge-warning">Suspended</span>;
      case "revoked":
        return <span className="badge badge-danger">Revoked</span>;
      default:
        return <span className="badge badge-neutral">{status}</span>;
    }
  };

  return (
    <AppShell>
      <div className="container" style={{ padding: "2rem 1.5rem" }}>
        {/* Header */}
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "2rem" }}>
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", marginBottom: "0.5rem" }}>
              <div
                style={{
                  width: "40px",
                  height: "40px",
                  borderRadius: "10px",
                  background: "var(--accent-primary-subtle)",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  color: "var(--accent-primary)",
                }}
              >
                <CodeIcon size={24} />
              </div>
              <h1 style={{ fontSize: "1.75rem", fontWeight: 700, margin: 0 }}>
                Developer Applications Oversight
              </h1>
            </div>
            <p style={{ color: "var(--text-secondary)", margin: 0, fontSize: "0.9375rem" }}>
              Platform Owner global security oversight, compliance audits, and emergency credential controls.
            </p>
          </div>
        </div>

        {/* Alerts */}
        {errorMessage && (
          <div
            style={{
              padding: "1rem",
              background: "var(--status-danger-bg)",
              border: "1px solid var(--status-danger-border)",
              borderRadius: "8px",
              color: "var(--status-danger)",
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
              background: "var(--status-success-bg)",
              border: "1px solid var(--status-success-border)",
              borderRadius: "8px",
              color: "var(--status-success)",
              marginBottom: "1.5rem",
            }}
          >
            {successMessage}
          </div>
        )}

        {/* Cross-tenant Apps Table */}
        <GlassPanel padding="lg">
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1.5rem", gap: "1rem" }}>
            <h2 style={{ fontSize: "1.125rem", fontWeight: 600, margin: 0 }}>Cross-Tenant Applications</h2>
            <div style={{ display: "flex", gap: "0.75rem" }}>
              <select
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value)}
                className="input-select"
                style={{ padding: "0.5rem 0.75rem", fontSize: "0.875rem" }}
              >
                <option value="">All Statuses</option>
                <option value="active">Active</option>
                <option value="suspended">Suspended</option>
                <option value="revoked">Revoked</option>
              </select>
              <input
                type="text"
                placeholder="Search application or tenant..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="input-text"
                style={{ width: "240px", padding: "0.5rem 0.75rem", fontSize: "0.875rem" }}
              />
            </div>
          </div>

          {isLoading ? (
            <LoadingSpinner label="Loading cross-tenant applications..." />
          ) : apps.length === 0 ? (
            <div style={{ textAlign: "center", padding: "3rem 1rem", color: "var(--text-secondary)" }}>
              <p>No developer applications found matching query.</p>
            </div>
          ) : (
            <div className="table-responsive">
              <table className="table" style={{ width: "100%", textAlign: "left" }}>
                <thead>
                  <tr style={{ borderBottom: "1px solid var(--border-glass)" }}>
                    <th style={{ padding: "0.75rem" }}>Organization</th>
                    <th style={{ padding: "0.75rem" }}>Application</th>
                    <th style={{ padding: "0.75rem" }}>Status</th>
                    <th style={{ padding: "0.75rem" }}>Active Keys</th>
                    <th style={{ padding: "0.75rem" }}>Created By</th>
                    <th style={{ padding: "0.75rem" }}>Created</th>
                    <th style={{ padding: "0.75rem", textAlign: "right" }}>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {apps.map((app) => (
                    <tr key={app.id} style={{ borderBottom: "1px solid var(--border-glass-subtle)" }}>
                      <td style={{ padding: "0.75rem" }}>
                        <div style={{ fontWeight: 600 }}>{app.organization.name}</div>
                        <div style={{ fontSize: "0.75rem", color: "var(--text-secondary)" }}>{app.organization.code}</div>
                      </td>
                      <td style={{ padding: "0.75rem" }}>
                        <div style={{ fontWeight: 600 }}>{app.name}</div>
                        {app.description && (
                          <div style={{ fontSize: "0.8125rem", color: "var(--text-secondary)" }}>{app.description}</div>
                        )}
                      </td>
                      <td style={{ padding: "0.75rem" }}>{getStatusBadge(app.status)}</td>
                      <td style={{ padding: "0.75rem" }}>{app.active_keys_count} active</td>
                      <td style={{ padding: "0.75rem", fontSize: "0.8125rem" }}>{app.created_by.email}</td>
                      <td style={{ padding: "0.75rem", fontSize: "0.8125rem", color: "var(--text-secondary)" }}>
                        {new Date(app.created_at).toLocaleDateString()}
                      </td>
                      <td style={{ padding: "0.75rem", textAlign: "right" }}>
                        <div style={{ display: "inline-flex", gap: "0.5rem" }}>
                          <button
                            type="button"
                            className="btn-secondary"
                            onClick={() => void loadKeys(app)}
                            style={{ padding: "0.25rem 0.625rem", fontSize: "0.8125rem" }}
                          >
                            Inspect Keys
                          </button>
                          {app.status === "active" && (
                            <button
                              type="button"
                              className="btn-ghost"
                              onClick={() => void handleAdminSuspendApp(app)}
                              style={{ padding: "0.25rem 0.5rem", fontSize: "0.8125rem", color: "var(--status-warning)" }}
                            >
                              Suspend
                            </button>
                          )}
                          {app.status !== "revoked" && (
                            <button
                              type="button"
                              className="btn-ghost"
                              onClick={() => void handleAdminRevokeApp(app)}
                              style={{ padding: "0.25rem 0.5rem", fontSize: "0.8125rem", color: "var(--status-danger)" }}
                            >
                              Revoke
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

        {/* Modal: Inspect Keys */}
        {inspectApp && (
          <div className="modal-backdrop" style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.6)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 100 }}>
            <GlassPanel padding="xl" style={{ maxWidth: "800px", width: "100%", maxHeight: "85vh", overflowY: "auto", background: "var(--bg-modal, #1e2238)" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "1.25rem" }}>
                <div>
                  <h2 style={{ fontSize: "1.25rem", fontWeight: 700, margin: 0 }}>
                    Keys for {inspectApp.name} ({inspectApp.organization.name})
                  </h2>
                  <p style={{ color: "var(--text-secondary)", fontSize: "0.875rem", margin: "0.25rem 0 0" }}>
                    Metadata oversight inspection. Secrets are strictly hashed and unrecoverable.
                  </p>
                </div>
                <button type="button" className="btn-ghost" onClick={() => setInspectApp(null)}>
                  Close
                </button>
              </div>

              {isLoadingKeys ? (
                <LoadingSpinner label="Inspecting keys..." />
              ) : appKeys.length === 0 ? (
                <p style={{ textAlign: "center", padding: "2rem 0", color: "var(--text-secondary)" }}>
                  No API keys registered for this application.
                </p>
              ) : (
                <div className="table-responsive">
                  <table className="table" style={{ width: "100%", textAlign: "left" }}>
                    <thead>
                      <tr style={{ borderBottom: "1px solid var(--border-glass)" }}>
                        <th style={{ padding: "0.75rem" }}>Key Label</th>
                        <th style={{ padding: "0.75rem" }}>Prefix</th>
                        <th style={{ padding: "0.75rem" }}>Scopes</th>
                        <th style={{ padding: "0.75rem" }}>Status</th>
                        <th style={{ padding: "0.75rem" }}>Last Used</th>
                        <th style={{ padding: "0.75rem" }}>Created</th>
                        <th style={{ padding: "0.75rem", textAlign: "right" }}>Emergency</th>
                      </tr>
                    </thead>
                    <tbody>
                      {appKeys.map((k) => (
                        <tr key={k.id} style={{ borderBottom: "1px solid var(--border-glass-subtle)" }}>
                          <td style={{ padding: "0.75rem", fontWeight: 600 }}>{k.name}</td>
                          <td style={{ padding: "0.75rem" }}>
                            <code>{k.key_prefix}...</code>
                          </td>
                          <td style={{ padding: "0.75rem" }}>
                            <div style={{ display: "flex", flexWrap: "wrap", gap: "0.25rem" }}>
                              {k.scopes.map((s) => (
                                <span key={s} className="badge badge-neutral" style={{ fontSize: "0.75rem" }}>
                                  {s}
                                </span>
                              ))}
                            </div>
                          </td>
                          <td style={{ padding: "0.75rem" }}>{getStatusBadge(k.status)}</td>
                          <td style={{ padding: "0.75rem", fontSize: "0.8125rem", color: "var(--text-secondary)" }}>
                            {k.last_used_at ? new Date(k.last_used_at).toLocaleString() : "Never"}
                          </td>
                          <td style={{ padding: "0.75rem", fontSize: "0.8125rem", color: "var(--text-secondary)" }}>
                            {new Date(k.created_at).toLocaleDateString()}
                          </td>
                          <td style={{ padding: "0.75rem", textAlign: "right" }}>
                            {k.status === "active" && (
                              <button
                                type="button"
                                className="btn-ghost"
                                onClick={() => setEmergencyTarget({ app: inspectApp, key: k })}
                                style={{ padding: "0.25rem 0.5rem", fontSize: "0.75rem", color: "var(--status-danger)" }}
                              >
                                Revoke Key
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
          </div>
        )}

        {/* Modal: Emergency Key Revocation Dialog */}
        {emergencyTarget && (
          <div className="modal-backdrop" style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.75)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 200 }}>
            <GlassPanel padding="xl" style={{ maxWidth: "500px", width: "100%", background: "var(--bg-modal, #1e2238)" }}>
              <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", marginBottom: "1rem" }}>
                <div style={{ color: "var(--status-danger)" }}>
                  <ShieldCheckIcon size={28} />
                </div>
                <h2 style={{ fontSize: "1.25rem", fontWeight: 700, margin: 0 }}>
                  Emergency Key Revocation
                </h2>
              </div>
              <p style={{ color: "var(--text-secondary)", fontSize: "0.875rem", marginBottom: "1.25rem" }}>
                You are about to immediately revoke key <strong>{emergencyTarget.key.name}</strong> ({emergencyTarget.key.key_prefix}...) for tenant <strong>{emergencyTarget.app.organization.name}</strong>.
              </p>
              <form onSubmit={handleEmergencyRevokeKey}>
                <div style={{ marginBottom: "1.5rem" }}>
                  <label style={{ display: "block", fontSize: "0.875rem", fontWeight: 500, marginBottom: "0.375rem" }}>
                    Security Rationale / Audit Justification *
                  </label>
                  <textarea
                    rows={3}
                    required
                    value={emergencyReason}
                    onChange={(e) => setEmergencyReason(e.target.value)}
                    placeholder="Document mandatory reason for emergency revocation..."
                    className="input-text"
                    style={{ width: "100%" }}
                  />
                </div>
                <div style={{ display: "flex", justifyContent: "flex-end", gap: "0.75rem" }}>
                  <button type="button" className="btn-ghost" onClick={() => setEmergencyTarget(null)}>
                    Cancel
                  </button>
                  <button
                    type="submit"
                    className="btn-primary"
                    disabled={isSubmittingEmergency || !emergencyReason.trim()}
                    style={{ background: "var(--status-danger)", borderColor: "var(--status-danger)" }}
                  >
                    {isSubmittingEmergency ? "Revoking..." : "Confirm Emergency Revocation"}
                  </button>
                </div>
              </form>
            </GlassPanel>
          </div>
        )}
      </div>
    </AppShell>
  );
};
