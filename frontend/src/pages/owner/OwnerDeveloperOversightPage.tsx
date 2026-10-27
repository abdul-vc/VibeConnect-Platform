/**
 * Platform Owner Developer Oversight Page (Phase 6B Stage 4).
 *
 * Route: /owner/developer-oversight
 * Context Guard: platform_owner
 * Cross-tenant oversight, lifecycle controls, and emergency revocation.
 */

import React, { useState, useEffect, useCallback } from "react";
import { Link } from "react-router-dom";
import { AppShell } from "../../components/AppShell.tsx";
import { LoadingSpinner } from "../../components/LoadingSpinner.tsx";
import {
  CodeIcon,
  ShieldCheckIcon,
  BuildingIcon,
  KeyIcon,
  UserIcon,
  CalendarIcon,
  SearchIcon,
  CloseIcon,
  AlertCircleIcon,
  CheckCircleIcon,
} from "../../components/Icons.tsx";
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
    } catch {
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
    } catch {
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
    } catch {
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
    } catch {
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
    } catch {
      setErrorMessage("Emergency key revocation failed.");
    } finally {
      setIsSubmittingEmergency(false);
    }
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case "active":
        return (
          <span className="badge badge-success">
            <span className="badge-dot" />
            Active
          </span>
        );
      case "suspended":
        return (
          <span className="badge badge-warning">
            <span className="badge-dot" />
            Suspended
          </span>
        );
      case "revoked":
        return (
          <span className="badge badge-danger">
            <span className="badge-dot" />
            Revoked
          </span>
        );
      default:
        return (
          <span className="badge badge-neutral">
            <span className="badge-dot" />
            {status}
          </span>
        );
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
          <span style={{ color: "var(--brand-primary)", fontWeight: 600 }}>Developer Applications Oversight</span>
        </div>

        {/* Header */}
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "2rem", flexWrap: "wrap", gap: "1rem" }}>
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
              <CodeIcon size={24} />
            </div>
            <div>
              <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
                <h1 className="heading-hero" style={{ fontSize: "1.75rem", fontWeight: 800, margin: 0, letterSpacing: "-0.02em", color: "var(--text-primary)" }}>
                  Developer Applications Oversight
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
                  {apps.length} Apps
                </span>
              </div>
              <p style={{ color: "var(--text-secondary)", margin: "0.25rem 0 0 0", fontSize: "0.9375rem" }}>
                Platform Owner global security oversight, compliance audits, and emergency credential controls.
              </p>
            </div>
          </div>
        </div>

        {/* Alerts */}
        {errorMessage && (
          <div
            style={{
              padding: "1rem 1.25rem",
              background: "var(--status-danger-bg)",
              border: "1px solid var(--status-danger-border)",
              borderRadius: "8px",
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
              borderRadius: "8px",
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

        {/* Cross-tenant Apps Table Card */}
        <div className="table-card-container">
          <div
            style={{
              padding: "1.25rem 1.5rem",
              borderBottom: "1px solid var(--border-subtle)",
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              flexWrap: "wrap",
              gap: "1rem",
              background: "var(--glass-surface)",
            }}
          >
            <div>
              <h2 style={{ fontSize: "1.125rem", fontWeight: 700, margin: 0, color: "var(--text-primary)" }}>
                Cross-Tenant Applications
              </h2>
              <p style={{ margin: "0.2rem 0 0", fontSize: "0.8125rem", color: "var(--text-secondary)" }}>
                Global inventory of registered third-party and custom tenant integrations.
              </p>
            </div>

            <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", flexWrap: "wrap" }}>
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
                {(["", "active", "suspended", "revoked"] as const).map((s) => {
                  const isActive = statusFilter === s;
                  const label =
                    s === ""
                      ? "All Statuses"
                      : s === "active"
                      ? "Active"
                      : s === "suspended"
                      ? "Suspended"
                      : "Revoked";
                  return (
                    <button
                      key={s}
                      type="button"
                      onClick={() => setStatusFilter(s)}
                      style={{
                        padding: "0.35rem 0.75rem",
                        borderRadius: "6px",
                        fontSize: "0.75rem",
                        fontWeight: isActive ? 600 : 500,
                        border: "none",
                        background: isActive ? "var(--glass-surface-elevated)" : "transparent",
                        color: isActive ? "var(--brand-primary)" : "var(--text-secondary)",
                        boxShadow: isActive ? "var(--shadow-sm)" : "none",
                        cursor: "pointer",
                        transition: "all 0.15s ease",
                      }}
                    >
                      {label}
                    </button>
                  );
                })}
              </div>

              <div style={{ position: "relative", display: "flex", alignItems: "center" }}>
                <SearchIcon
                  size={15}
                  style={{
                    position: "absolute",
                    left: "0.75rem",
                    color: "var(--text-muted)",
                    pointerEvents: "none",
                  }}
                />
                <input
                  type="text"
                  placeholder="Search application or tenant..."
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                  style={{
                    padding: "0.45rem 0.75rem 0.45rem 2.25rem",
                    borderRadius: "6px",
                    fontSize: "0.8125rem",
                    background: "var(--input-bg)",
                    border: "1px solid var(--border-subtle)",
                    color: "var(--text-primary)",
                    width: "220px",
                    outline: "none",
                    boxSizing: "border-box",
                  }}
                />
              </div>
            </div>
          </div>

          {isLoading ? (
            <div style={{ display: "flex", justifyContent: "center", padding: "4rem" }}>
              <LoadingSpinner label="Loading cross-tenant applications..." />
            </div>
          ) : apps.length === 0 ? (
            <div style={{ textAlign: "center", padding: "3.5rem 1.5rem", color: "var(--text-secondary)" }}>
              <p style={{ margin: 0, fontSize: "1rem", color: "var(--text-primary)", fontWeight: 600 }}>
                No developer applications found
              </p>
              <p style={{ margin: "0.35rem 0 0", fontSize: "0.875rem" }}>
                No cross-tenant application matches your current search or status filters.
              </p>
            </div>
          ) : (
            <div className="table-card-scroll">
              <table style={{ width: "100%", borderCollapse: "collapse", textAlign: "left" }}>
                <thead>
                  <tr
                    style={{
                      borderBottom: "1px solid var(--border-subtle)",
                      background: "var(--glass-surface-sunken)",
                    }}
                  >
                    <th scope="col" style={{ padding: "0.875rem 1.25rem", fontSize: "0.75rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.05em", color: "var(--text-secondary)" }}>
                      ORGANIZATION
                    </th>
                    <th scope="col" style={{ padding: "0.875rem 1.25rem", fontSize: "0.75rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.05em", color: "var(--text-secondary)" }}>
                      APPLICATION
                    </th>
                    <th scope="col" style={{ padding: "0.875rem 1.25rem", fontSize: "0.75rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.05em", color: "var(--text-secondary)" }}>
                      STATUS
                    </th>
                    <th scope="col" style={{ padding: "0.875rem 1.25rem", fontSize: "0.75rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.05em", color: "var(--text-secondary)" }}>
                      ACTIVE KEYS
                    </th>
                    <th scope="col" style={{ padding: "0.875rem 1.25rem", fontSize: "0.75rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.05em", color: "var(--text-secondary)" }}>
                      CREATED BY
                    </th>
                    <th scope="col" style={{ padding: "0.875rem 1.25rem", fontSize: "0.75rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.05em", color: "var(--text-secondary)" }}>
                      CREATED
                    </th>
                    <th scope="col" style={{ padding: "0.875rem 1.25rem", fontSize: "0.75rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.05em", color: "var(--text-secondary)", textAlign: "right" }}>
                      ACTIONS
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {apps.map((app) => (
                    <tr
                      key={app.id}
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
                              {app.organization.name}
                            </div>
                            <span
                              style={{
                                display: "inline-block",
                                fontSize: "0.75rem",
                                fontFamily: "var(--font-code)",
                                color: "var(--text-muted)",
                                background: "var(--glass-surface-sunken)",
                                padding: "0.1rem 0.4rem",
                                borderRadius: 4,
                                border: "1px solid var(--border-subtle)",
                                marginTop: "0.2rem",
                              }}
                            >
                              {app.organization.code}
                            </span>
                          </div>
                        </div>
                      </td>
                      <td style={{ padding: "1rem 1.25rem", verticalAlign: "middle", maxWidth: "280px" }}>
                        <div style={{ fontWeight: 600, color: "var(--text-primary)", fontSize: "0.9375rem" }}>
                          {app.name}
                        </div>
                        {app.description && (
                          <div style={{ fontSize: "0.8125rem", color: "var(--text-secondary)", marginTop: "0.25rem", lineHeight: 1.4 }}>
                            {app.description}
                          </div>
                        )}
                      </td>
                      <td style={{ padding: "1rem 1.25rem", verticalAlign: "middle" }}>
                        {getStatusBadge(app.status)}
                      </td>
                      <td style={{ padding: "1rem 1.25rem", verticalAlign: "middle" }}>
                        <div style={{ display: "flex", alignItems: "center", gap: "0.35rem", fontSize: "0.8125rem", color: "var(--text-primary)" }}>
                          <KeyIcon size={14} style={{ color: "var(--brand-primary)" }} />
                          <span style={{ fontWeight: 600 }}>{app.active_keys_count}</span>
                          <span style={{ color: "var(--text-muted)" }}>active</span>
                        </div>
                      </td>
                      <td style={{ padding: "1rem 1.25rem", verticalAlign: "middle" }}>
                        <div style={{ display: "flex", alignItems: "center", gap: "0.4rem", fontSize: "0.8125rem", color: "var(--text-secondary)" }}>
                          <UserIcon size={14} style={{ color: "var(--text-muted)", flexShrink: 0 }} />
                          <span title={app.created_by.email} style={{ overflowWrap: "anywhere" }}>
                            {app.created_by.email}
                          </span>
                        </div>
                      </td>
                      <td style={{ padding: "1rem 1.25rem", verticalAlign: "middle", whiteSpace: "nowrap" }}>
                        <div style={{ display: "flex", alignItems: "center", gap: "0.4rem", fontSize: "0.8125rem", color: "var(--text-secondary)" }}>
                          <CalendarIcon size={14} style={{ color: "var(--text-muted)" }} />
                          <span>{new Date(app.created_at).toLocaleDateString()}</span>
                        </div>
                      </td>
                      <td style={{ padding: "1rem 1.25rem", textAlign: "right", verticalAlign: "middle" }}>
                        <div style={{ display: "inline-flex", alignItems: "center", gap: "0.5rem" }}>
                          <button
                            type="button"
                            className="btn-secondary"
                            onClick={() => void loadKeys(app)}
                            style={{
                              padding: "0.35rem 0.75rem",
                              fontSize: "0.8125rem",
                              fontWeight: 500,
                              minHeight: "32px",
                            }}
                          >
                            <KeyIcon size={14} />
                            Inspect Keys
                          </button>
                          {app.status === "active" && (
                            <button
                              type="button"
                              onClick={() => void handleAdminSuspendApp(app)}
                              style={{
                                display: "inline-flex",
                                alignItems: "center",
                                gap: "0.25rem",
                                padding: "0.35rem 0.65rem",
                                fontSize: "0.75rem",
                                fontWeight: 600,
                                borderRadius: "6px",
                                border: "1px solid var(--status-warning-border)",
                                background: "var(--status-warning-bg)",
                                color: "var(--status-warning)",
                                cursor: "pointer",
                                minHeight: "32px",
                                transition: "all 0.15s ease",
                              }}
                            >
                              Suspend
                            </button>
                          )}
                          {app.status !== "revoked" && (
                            <button
                              type="button"
                              onClick={() => void handleAdminRevokeApp(app)}
                              style={{
                                display: "inline-flex",
                                alignItems: "center",
                                gap: "0.25rem",
                                padding: "0.35rem 0.65rem",
                                fontSize: "0.75rem",
                                fontWeight: 600,
                                borderRadius: "6px",
                                border: "1px solid var(--status-danger-border)",
                                background: "var(--status-danger-bg)",
                                color: "var(--status-danger)",
                                cursor: "pointer",
                                minHeight: "32px",
                                transition: "all 0.15s ease",
                              }}
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
        </div>

        {/* Modal: Inspect Keys */}
        {inspectApp && (
          <div
            style={{
              position: "fixed",
              inset: 0,
              background: "rgba(10, 14, 26, 0.65)",
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
                maxWidth: "860px",
                width: "100%",
                maxHeight: "88vh",
                overflowY: "auto",
                background: "var(--glass-surface-elevated)",
                border: "1px solid var(--border-glass)",
                borderRadius: "0.75rem",
                boxShadow: "var(--shadow-lg)",
                padding: "2rem",
              }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "1.25rem" }}>
                <div>
                  <h2 style={{ fontSize: "1.25rem", fontWeight: 700, margin: 0, color: "var(--text-primary)" }}>
                    Keys for {inspectApp.name} ({inspectApp.organization.name})
                  </h2>
                  <p style={{ color: "var(--text-secondary)", fontSize: "0.875rem", margin: "0.25rem 0 0" }}>
                    Metadata oversight inspection. Secrets are strictly hashed and unrecoverable.
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => setInspectApp(null)}
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
                  <CloseIcon size={20} />
                </button>
              </div>

              {isLoadingKeys ? (
                <div style={{ padding: "3rem", display: "flex", justifyContent: "center" }}>
                  <LoadingSpinner label="Inspecting keys..." />
                </div>
              ) : appKeys.length === 0 ? (
                <div style={{ textAlign: "center", padding: "3rem 1rem", color: "var(--text-secondary)" }}>
                  <p style={{ margin: 0, fontSize: "0.9375rem" }}>No API keys registered for this application.</p>
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
                          <th scope="col" style={{ padding: "0.75rem 1rem", fontSize: "0.75rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.05em", color: "var(--text-secondary)" }}>
                            Key Label
                          </th>
                          <th scope="col" style={{ padding: "0.75rem 1rem", fontSize: "0.75rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.05em", color: "var(--text-secondary)" }}>
                            Prefix
                          </th>
                          <th scope="col" style={{ padding: "0.75rem 1rem", fontSize: "0.75rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.05em", color: "var(--text-secondary)" }}>
                            Scopes
                          </th>
                          <th scope="col" style={{ padding: "0.75rem 1rem", fontSize: "0.75rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.05em", color: "var(--text-secondary)" }}>
                            Status
                          </th>
                          <th scope="col" style={{ padding: "0.75rem 1rem", fontSize: "0.75rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.05em", color: "var(--text-secondary)" }}>
                            Last Used
                          </th>
                          <th scope="col" style={{ padding: "0.75rem 1rem", fontSize: "0.75rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.05em", color: "var(--text-secondary)" }}>
                            Created
                          </th>
                          <th scope="col" style={{ padding: "0.75rem 1rem", fontSize: "0.75rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.05em", color: "var(--text-secondary)", textAlign: "right" }}>
                            Emergency
                          </th>
                        </tr>
                      </thead>
                      <tbody>
                        {appKeys.map((k) => (
                          <tr
                            key={k.id}
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
                            <td style={{ padding: "0.75rem 1rem", fontWeight: 600, color: "var(--text-primary)" }}>
                              {k.name}
                            </td>
                            <td style={{ padding: "0.75rem 1rem" }}>
                              <code
                                style={{
                                  fontSize: "0.75rem",
                                  fontFamily: "var(--font-code)",
                                  background: "var(--glass-surface-sunken)",
                                  padding: "0.15rem 0.4rem",
                                  borderRadius: 4,
                                  border: "1px solid var(--border-subtle)",
                                }}
                              >
                                {k.key_prefix}...
                              </code>
                            </td>
                            <td style={{ padding: "0.75rem 1rem" }}>
                              <div style={{ display: "flex", flexWrap: "wrap", gap: "0.25rem" }}>
                                {k.scopes.map((s) => (
                                  <span key={s} className="badge badge-neutral" style={{ fontSize: "0.6875rem" }}>
                                    {s}
                                  </span>
                                ))}
                              </div>
                            </td>
                            <td style={{ padding: "0.75rem 1rem" }}>{getStatusBadge(k.status)}</td>
                            <td style={{ padding: "0.75rem 1rem", fontSize: "0.8125rem", color: "var(--text-secondary)" }}>
                              {k.last_used_at ? new Date(k.last_used_at).toLocaleString() : "Never"}
                            </td>
                            <td style={{ padding: "0.75rem 1rem", fontSize: "0.8125rem", color: "var(--text-secondary)" }}>
                              {new Date(k.created_at).toLocaleDateString()}
                            </td>
                            <td style={{ padding: "0.75rem 1rem", textAlign: "right" }}>
                              {k.status === "active" && (
                                <button
                                  type="button"
                                  onClick={() => setEmergencyTarget({ app: inspectApp, key: k })}
                                  style={{
                                    display: "inline-flex",
                                    alignItems: "center",
                                    padding: "0.3rem 0.6rem",
                                    fontSize: "0.75rem",
                                    fontWeight: 600,
                                    borderRadius: "4px",
                                    border: "1px solid var(--status-danger-border)",
                                    background: "var(--status-danger-bg)",
                                    color: "var(--status-danger)",
                                    cursor: "pointer",
                                  }}
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
                </div>
              )}
            </div>
          </div>
        )}

        {/* Modal: Emergency Key Revocation Dialog */}
        {emergencyTarget && (
          <div
            style={{
              position: "fixed",
              inset: 0,
              background: "rgba(10, 14, 26, 0.75)",
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
                maxWidth: "520px",
                width: "100%",
                background: "var(--glass-surface-elevated)",
                border: "1px solid var(--border-glass)",
                borderRadius: "0.75rem",
                boxShadow: "var(--shadow-lg)",
                padding: "2rem",
              }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", marginBottom: "1rem" }}>
                <div style={{ color: "var(--status-danger)" }}>
                  <ShieldCheckIcon size={28} />
                </div>
                <h2 style={{ fontSize: "1.25rem", fontWeight: 700, margin: 0, color: "var(--text-primary)" }}>
                  Emergency Key Revocation
                </h2>
              </div>
              <p style={{ color: "var(--text-secondary)", fontSize: "0.875rem", marginBottom: "1.25rem", lineHeight: 1.5 }}>
                You are about to immediately revoke key <strong>{emergencyTarget.key.name}</strong> (<code>{emergencyTarget.key.key_prefix}...</code>) for tenant <strong>{emergencyTarget.app.organization.name}</strong>.
              </p>
              <form onSubmit={handleEmergencyRevokeKey}>
                <div style={{ marginBottom: "1.5rem" }}>
                  <label style={{ display: "block", fontSize: "0.875rem", fontWeight: 600, marginBottom: "0.5rem", color: "var(--text-primary)" }}>
                    Security Rationale / Audit Justification <span style={{ color: "var(--status-danger)" }}>*</span>
                  </label>
                  <textarea
                    rows={3}
                    required
                    value={emergencyReason}
                    onChange={(e) => setEmergencyReason(e.target.value)}
                    placeholder="Document mandatory reason for emergency revocation..."
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
                  />
                </div>
                <div style={{ display: "flex", justifyContent: "flex-end", gap: "0.75rem" }}>
                  <button
                    type="button"
                    className="btn-secondary"
                    onClick={() => setEmergencyTarget(null)}
                    style={{ padding: "0.5rem 1rem", fontSize: "0.875rem" }}
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={isSubmittingEmergency || !emergencyReason.trim()}
                    style={{
                      display: "inline-flex",
                      alignItems: "center",
                      gap: "0.35rem",
                      padding: "0.5rem 1.25rem",
                      fontSize: "0.875rem",
                      fontWeight: 600,
                      borderRadius: "6px",
                      border: "1px solid var(--status-danger)",
                      background: "var(--status-danger)",
                      color: "#ffffff",
                      cursor: isSubmittingEmergency || !emergencyReason.trim() ? "not-allowed" : "pointer",
                      opacity: isSubmittingEmergency || !emergencyReason.trim() ? 0.6 : 1,
                    }}
                  >
                    {isSubmittingEmergency ? "Revoking..." : "Confirm Emergency Revocation"}
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

