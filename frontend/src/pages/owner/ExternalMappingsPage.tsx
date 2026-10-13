/**
 * External Identity Mappings Owner Page (Phase 5B).
 *
 * Platform Owner console to view and create ExternalTenantMapping,
 * ExternalUserMapping, and ExternalIdentity records for a selected connector instance.
 * Manual entry only (bulk import deferred).
 */

import React, { useEffect, useState, useCallback } from "react";
import { AppShell } from "../../components/AppShell.tsx";
import {
  integrationApi,
  ConnectorInstance,
  ExternalTenantMapping,
  ExternalUserMapping,
  ExternalIdentity,
} from "../../api/integration.ts";

export const ExternalMappingsPage: React.FC = () => {
  const [instances, setInstances] = useState<ConnectorInstance[]>([]);
  const [selectedInstance, setSelectedInstance] = useState<string>("");
  const [activeTab, setActiveTab] = useState<"tenant" | "user" | "identities">("tenant");

  const [tenantMappings, setTenantMappings] = useState<ExternalTenantMapping[]>([]);
  const [userMappings, setUserMappings] = useState<ExternalUserMapping[]>([]);
  const [externalIdentities, setExternalIdentities] = useState<ExternalIdentity[]>([]);

  const [loading, setLoading] = useState(false);
  const [instancesLoading, setInstancesLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  // Modal State for Creating Mapping
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [modalType, setModalType] = useState<"tenant" | "user">("tenant");
  const [formOrgId, setFormOrgId] = useState("");
  const [formUserId, setFormUserId] = useState("");
  const [formExternalId, setFormExternalId] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [modalError, setModalError] = useState<string | null>(null);

  // Load instances on mount
  useEffect(() => {
    let cancelled = false;
    setInstancesLoading(true);
    integrationApi
      .listInstances()
      .then((r) => {
        if (!cancelled) {
          setInstances(r.results || []);
          if (r.results && r.results.length > 0) {
            setSelectedInstance(r.results[0].id);
          }
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to load connector instances.");
        }
      })
      .finally(() => {
        if (!cancelled) setInstancesLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // Fetch mappings for the selected instance
  const fetchMappings = useCallback(async (instId: string) => {
    if (!instId) {
      setTenantMappings([]);
      setUserMappings([]);
      setExternalIdentities([]);
      return;
    }

    setLoading(true);
    setError(null);
    try {
      const [tmRes, umRes, idRes] = await Promise.all([
        integrationApi.listTenantMappings(instId).then((r) => r.results),
        integrationApi.listUserMappings(instId).then((r) => r.results),
        integrationApi.listExternalIdentities().then((r) => r.results),
      ]);
      setTenantMappings(tmRes || []);
      setUserMappings(umRes || []);
      setExternalIdentities(idRes || []);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to load external mappings.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (selectedInstance) {
      void fetchMappings(selectedInstance);
    }
  }, [selectedInstance, fetchMappings]);

  // Handle Create Mapping
  const handleOpenCreateModal = (type: "tenant" | "user") => {
    setModalType(type);
    setModalError(null);
    setFormExternalId("");
    // Pre-populate organization from current selected instance if available
    const currentInst = instances.find((i) => i.id === selectedInstance);
    setFormOrgId(currentInst?.organization || "");
    setFormUserId("");
    setIsModalOpen(true);
  };

  const handleSubmitMapping = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedInstance) {
      setModalError("Please select a connector instance first.");
      return;
    }
    if (!formOrgId.trim()) {
      setModalError("Organization is required.");
      return;
    }
    if (!formExternalId.trim()) {
      setModalError("External ID is required.");
      return;
    }
    if (modalType === "user" && !formUserId.trim()) {
      setModalError("User ID is required for user mappings.");
      return;
    }

    setIsSubmitting(true);
    setModalError(null);
    try {
      if (modalType === "tenant") {
        await integrationApi.createTenantMapping({
          instance: selectedInstance,
          organization: formOrgId.trim(),
          external_tenant_id: formExternalId.trim(),
        });
        setSuccessMessage("Tenant mapping created successfully.");
      } else {
        await integrationApi.createUserMapping({
          instance: selectedInstance,
          organization: formOrgId.trim(),
          user: formUserId.trim(),
          external_user_id: formExternalId.trim(),
          status: "active",
        });
        setSuccessMessage("User mapping created successfully.");
      }
      setIsModalOpen(false);
      void fetchMappings(selectedInstance);
      setTimeout(() => setSuccessMessage(null), 4000);
    } catch (err: unknown) {
      setModalError(err instanceof Error ? err.message : "Failed to create mapping.");
    } finally {
      setIsSubmitting(false);
    }
  };

  const selectedInstanceObj = instances.find((i) => i.id === selectedInstance);

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
                Control Plane • Identity Federation
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
              External Identity Mappings
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
              Map VibeConnect tenant organizations and users to external LMS identities. Enforces strict identity isolation without assuming UUID equality.
            </p>
          </div>

          <div style={{ display: "flex", gap: "0.75rem", flexWrap: "wrap" }}>
            <button
              type="button"
              onClick={() => handleOpenCreateModal("tenant")}
              disabled={!selectedInstance}
              className="btn-secondary"
              style={{
                padding: "0.5rem 1rem",
                borderRadius: "8px",
                fontSize: "0.875rem",
                cursor: selectedInstance ? "pointer" : "not-allowed",
              }}
            >
              + Add Tenant Mapping
            </button>
            <button
              type="button"
              onClick={() => handleOpenCreateModal("user")}
              disabled={!selectedInstance}
              className="btn-primary"
              style={{
                padding: "0.5rem 1rem",
                borderRadius: "8px",
                fontSize: "0.875rem",
                cursor: selectedInstance ? "pointer" : "not-allowed",
              }}
            >
              + Add User Mapping
            </button>
          </div>
        </div>

        {/* Notifications */}
        {successMessage && (
          <div
            role="status"
            style={{
              padding: "1rem 1.25rem",
              background: "var(--status-success-bg, rgba(34, 197, 94, 0.15))",
              border: "1px solid var(--status-success-border, rgba(34, 197, 94, 0.3))",
              borderRadius: "10px",
              color: "var(--status-success, #22c55e)",
              fontSize: "0.875rem",
            }}
          >
            {successMessage}
          </div>
        )}

        {error && (
          <div
            role="alert"
            style={{
              padding: "1rem 1.25rem",
              background: "var(--status-danger-bg, rgba(239, 68, 68, 0.15))",
              border: "1px solid var(--status-danger-border, rgba(239, 68, 68, 0.3))",
              borderRadius: "10px",
              color: "var(--status-danger, #ef4444)",
              fontSize: "0.875rem",
            }}
          >
            {error}
          </div>
        )}

        {/* Connector Instance Selector Bar */}
        <div
          style={{
            background: "var(--glass-surface)",
            border: "1px solid var(--border-glass)",
            borderRadius: "12px",
            padding: "1.25rem",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            flexWrap: "wrap",
            gap: "1rem",
          }}
        >
          <div style={{ display: "flex", flexDirection: "column", gap: "0.35rem", minWidth: 280 }}>
            <label
              htmlFor="instance-select"
              style={{ fontSize: "0.8125rem", fontWeight: 600, color: "var(--text-secondary)" }}
            >
              Connector Instance
            </label>
            <select
              id="instance-select"
              value={selectedInstance}
              onChange={(e) => setSelectedInstance(e.target.value)}
              disabled={instancesLoading || instances.length === 0}
              style={{
                padding: "0.6rem 0.85rem",
                borderRadius: "8px",
                border: "1px solid var(--border-subtle)",
                background: "var(--glass-surface-elevated)",
                color: "var(--text-primary)",
                fontSize: "0.875rem",
                minWidth: "320px",
              }}
            >
              {instancesLoading ? (
                <option value="">Loading instances…</option>
              ) : instances.length === 0 ? (
                <option value="">No connector instances registered</option>
              ) : (
                instances.map((inst) => (
                  <option key={inst.id} value={inst.id}>
                    {inst.label || inst.connector_code} • {inst.organization_name} ({inst.status})
                  </option>
                ))
              )}
            </select>
          </div>

          {selectedInstanceObj && (
            <div style={{ display: "flex", gap: "1.5rem", alignItems: "center" }}>
              <div>
                <div style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>Target Organization</div>
                <div style={{ fontSize: "0.875rem", fontWeight: 600, color: "var(--text-primary)" }}>
                  {selectedInstanceObj.organization_name}
                </div>
              </div>
              <div>
                <div style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>Credential Reference</div>
                <code style={{ fontSize: "0.75rem", color: "var(--text-secondary)" }}>
                  {selectedInstanceObj.credential_ref || "—"}
                </code>
              </div>
              <div>
                <div style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>Status</div>
                <div style={{ fontSize: "0.875rem", fontWeight: 600, color: "var(--status-success)" }}>
                  {selectedInstanceObj.status.toUpperCase()}
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Tab Controls */}
        <div style={{ display: "flex", borderBottom: "1px solid var(--border-subtle)", gap: "0.5rem" }}>
          <button
            type="button"
            onClick={() => setActiveTab("tenant")}
            style={{
              padding: "0.65rem 1.25rem",
              background: "transparent",
              border: "none",
              borderBottom: activeTab === "tenant" ? "2px solid var(--brand-primary, #6366f1)" : "2px solid transparent",
              color: activeTab === "tenant" ? "var(--text-primary)" : "var(--text-muted)",
              fontWeight: activeTab === "tenant" ? 600 : 400,
              fontSize: "0.875rem",
              cursor: "pointer",
            }}
          >
            Tenant Mappings ({tenantMappings.length})
          </button>
          <button
            type="button"
            onClick={() => setActiveTab("user")}
            style={{
              padding: "0.65rem 1.25rem",
              background: "transparent",
              border: "none",
              borderBottom: activeTab === "user" ? "2px solid var(--brand-primary, #6366f1)" : "2px solid transparent",
              color: activeTab === "user" ? "var(--text-primary)" : "var(--text-muted)",
              fontWeight: activeTab === "user" ? 600 : 400,
              fontSize: "0.875rem",
              cursor: "pointer",
            }}
          >
            User Mappings ({userMappings.length})
          </button>
          <button
            type="button"
            onClick={() => setActiveTab("identities")}
            style={{
              padding: "0.65rem 1.25rem",
              background: "transparent",
              border: "none",
              borderBottom: activeTab === "identities" ? "2px solid var(--brand-primary, #6366f1)" : "2px solid transparent",
              color: activeTab === "identities" ? "var(--text-primary)" : "var(--text-muted)",
              fontWeight: activeTab === "identities" ? 600 : 400,
              fontSize: "0.875rem",
              cursor: "pointer",
            }}
          >
            External Identities ({externalIdentities.length})
          </button>
        </div>

        {/* Tab Contents */}
        {loading ? (
          <div
            aria-live="polite"
            style={{
              padding: "2rem",
              textAlign: "center",
              color: "var(--text-muted)",
              background: "var(--glass-surface)",
              borderRadius: "10px",
              border: "1px solid var(--border-subtle)",
            }}
          >
            Loading mappings…
          </div>
        ) : !selectedInstance ? (
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
            Select a connector instance above to view and manage external identity mappings.
          </div>
        ) : (
          <div
            style={{
              background: "var(--glass-surface-elevated)",
              border: "1px solid var(--border-glass)",
              borderRadius: "14px",
              padding: "1.5rem",
            }}
          >
            {/* Tab 1: Tenant Mappings */}
            {activeTab === "tenant" && (
              <div>
                {tenantMappings.length === 0 ? (
                  <div
                    style={{
                      padding: "2.5rem 1rem",
                      textAlign: "center",
                      color: "var(--text-muted)",
                    }}
                  >
                    <div style={{ fontSize: "1rem", fontWeight: 600, color: "var(--text-primary)", marginBottom: "0.35rem" }}>
                      No mappings configured
                    </div>
                    <div style={{ fontSize: "0.875rem" }}>
                      No external tenant ID mappings exist for this connector instance yet. Click "+ Add Tenant Mapping" to create one.
                    </div>
                  </div>
                ) : (
                  <div style={{ overflowX: "auto" }}>
                    <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.875rem" }}>
                      <thead>
                        <tr style={{ borderBottom: "1px solid var(--border-subtle)", textAlign: "left" }}>
                          <th style={{ padding: "0.75rem", color: "var(--text-secondary)", fontWeight: 600 }}>VibeConnect Organization</th>
                          <th style={{ padding: "0.75rem", color: "var(--text-secondary)", fontWeight: 600 }}>External Tenant ID</th>
                          <th style={{ padding: "0.75rem", color: "var(--text-secondary)", fontWeight: 600 }}>Instance</th>
                          <th style={{ padding: "0.75rem", color: "var(--text-secondary)", fontWeight: 600 }}>Configured</th>
                        </tr>
                      </thead>
                      <tbody>
                        {tenantMappings.map((m) => (
                          <tr key={m.id} style={{ borderBottom: "1px solid var(--border-glass)" }}>
                            <td style={{ padding: "0.75rem", fontWeight: 600, color: "var(--text-primary)" }}>
                              {m.organization}
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
                                {m.external_tenant_id}
                              </code>
                            </td>
                            <td style={{ padding: "0.75rem", color: "var(--text-secondary)" }}>
                              {selectedInstanceObj?.label || m.instance}
                            </td>
                            <td style={{ padding: "0.75rem", color: "var(--text-muted)", fontSize: "0.75rem" }}>
                              {m.created_at ? new Date(m.created_at).toLocaleDateString() : "—"}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            )}

            {/* Tab 2: User Mappings */}
            {activeTab === "user" && (
              <div>
                {userMappings.length === 0 ? (
                  <div
                    style={{
                      padding: "2.5rem 1rem",
                      textAlign: "center",
                      color: "var(--text-muted)",
                    }}
                  >
                    <div style={{ fontSize: "1rem", fontWeight: 600, color: "var(--text-primary)", marginBottom: "0.35rem" }}>
                      No mappings configured
                    </div>
                    <div style={{ fontSize: "0.875rem" }}>
                      No external user mappings exist for this connector instance yet. Click "+ Add User Mapping" to configure one.
                    </div>
                  </div>
                ) : (
                  <div style={{ overflowX: "auto" }}>
                    <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.875rem" }}>
                      <thead>
                        <tr style={{ borderBottom: "1px solid var(--border-subtle)", textAlign: "left" }}>
                          <th style={{ padding: "0.75rem", color: "var(--text-secondary)", fontWeight: 600 }}>VibeConnect User</th>
                          <th style={{ padding: "0.75rem", color: "var(--text-secondary)", fontWeight: 600 }}>Organization</th>
                          <th style={{ padding: "0.75rem", color: "var(--text-secondary)", fontWeight: 600 }}>External User ID</th>
                          <th style={{ padding: "0.75rem", color: "var(--text-secondary)", fontWeight: 600 }}>Status</th>
                          <th style={{ padding: "0.75rem", color: "var(--text-secondary)", fontWeight: 600 }}>Created</th>
                        </tr>
                      </thead>
                      <tbody>
                        {userMappings.map((m) => (
                          <tr key={m.id} style={{ borderBottom: "1px solid var(--border-glass)" }}>
                            <td style={{ padding: "0.75rem", fontWeight: 600, color: "var(--text-primary)" }}>
                              {m.user}
                            </td>
                            <td style={{ padding: "0.75rem", color: "var(--text-secondary)" }}>
                              {m.organization}
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
                                {m.external_user_id}
                              </code>
                            </td>
                            <td style={{ padding: "0.75rem" }}>
                              <span
                                style={{
                                  display: "inline-block",
                                  padding: "0.15rem 0.5rem",
                                  borderRadius: "9999px",
                                  fontSize: "0.75rem",
                                  fontWeight: 600,
                                  background:
                                    m.status === "active"
                                      ? "var(--status-success-bg, rgba(34, 197, 94, 0.15))"
                                      : "var(--status-danger-bg, rgba(239, 68, 68, 0.15))",
                                  color:
                                    m.status === "active"
                                      ? "var(--status-success, #22c55e)"
                                      : "var(--status-danger, #ef4444)",
                                }}
                              >
                                {m.status}
                              </span>
                            </td>
                            <td style={{ padding: "0.75rem", color: "var(--text-muted)", fontSize: "0.75rem" }}>
                              {m.created_at ? new Date(m.created_at).toLocaleDateString() : "—"}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            )}

            {/* Tab 3: External Identities */}
            {activeTab === "identities" && (
              <div>
                {externalIdentities.length === 0 ? (
                  <div
                    style={{
                      padding: "2.5rem 1rem",
                      textAlign: "center",
                      color: "var(--text-muted)",
                    }}
                  >
                    <div style={{ fontSize: "1rem", fontWeight: 600, color: "var(--text-primary)", marginBottom: "0.35rem" }}>
                      No external identities registered
                    </div>
                    <div style={{ fontSize: "0.875rem" }}>
                      Federated provider subject bindings created via SSO and identity sync will appear here.
                    </div>
                  </div>
                ) : (
                  <div style={{ overflowX: "auto" }}>
                    <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.875rem" }}>
                      <thead>
                        <tr style={{ borderBottom: "1px solid var(--border-subtle)", textAlign: "left" }}>
                          <th style={{ padding: "0.75rem", color: "var(--text-secondary)", fontWeight: 600 }}>User</th>
                          <th style={{ padding: "0.75rem", color: "var(--text-secondary)", fontWeight: 600 }}>Provider</th>
                          <th style={{ padding: "0.75rem", color: "var(--text-secondary)", fontWeight: 600 }}>Provider Tenant</th>
                          <th style={{ padding: "0.75rem", color: "var(--text-secondary)", fontWeight: 600 }}>Provider Subject</th>
                          <th style={{ padding: "0.75rem", color: "var(--text-secondary)", fontWeight: 600 }}>Status</th>
                        </tr>
                      </thead>
                      <tbody>
                        {externalIdentities.map((id) => (
                          <tr key={id.id} style={{ borderBottom: "1px solid var(--border-glass)" }}>
                            <td style={{ padding: "0.75rem", fontWeight: 600, color: "var(--text-primary)" }}>
                              {id.user}
                            </td>
                            <td style={{ padding: "0.75rem", color: "var(--text-secondary)" }}>
                              {id.provider}
                            </td>
                            <td style={{ padding: "0.75rem", color: "var(--text-secondary)" }}>
                              {id.provider_tenant}
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
                                {id.provider_subject}
                              </code>
                            </td>
                            <td style={{ padding: "0.75rem" }}>
                              <span
                                style={{
                                  display: "inline-block",
                                  padding: "0.15rem 0.5rem",
                                  borderRadius: "9999px",
                                  fontSize: "0.75rem",
                                  fontWeight: 600,
                                  background:
                                    id.status === "active"
                                      ? "var(--status-success-bg, rgba(34, 197, 94, 0.15))"
                                      : "var(--status-danger-bg, rgba(239, 68, 68, 0.15))",
                                  color:
                                    id.status === "active"
                                      ? "var(--status-success, #22c55e)"
                                      : "var(--status-danger, #ef4444)",
                                }}
                              >
                                {id.status}
                              </span>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        {/* Create Mapping Modal */}
        {isModalOpen && (
          <div
            style={{
              position: "fixed",
              top: 0,
              left: 0,
              right: 0,
              bottom: 0,
              backgroundColor: "rgba(0, 0, 0, 0.65)",
              display: "flex",
              justifyContent: "center",
              alignItems: "center",
              zIndex: 1000,
              padding: "1rem",
            }}
          >
            <div
              style={{
                background: "var(--glass-surface-elevated, #1e1e2e)",
                border: "1px solid var(--border-glass)",
                borderRadius: "14px",
                width: "100%",
                maxWidth: "500px",
                padding: "1.75rem",
                boxShadow: "0 20px 40px rgba(0,0,0,0.5)",
              }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1.25rem" }}>
                <h3 style={{ margin: 0, fontSize: "1.25rem", color: "var(--text-primary)" }}>
                  Create {modalType === "tenant" ? "Tenant" : "User"} Mapping
                </h3>
                <button
                  type="button"
                  onClick={() => setIsModalOpen(false)}
                  style={{
                    background: "none",
                    border: "none",
                    color: "var(--text-muted)",
                    fontSize: "1.25rem",
                    cursor: "pointer",
                  }}
                >
                  ✕
                </button>
              </div>

              {modalError && (
                <div
                  role="alert"
                  style={{
                    padding: "0.75rem 1rem",
                    background: "var(--status-danger-bg, rgba(239, 68, 68, 0.15))",
                    border: "1px solid var(--status-danger-border, rgba(239, 68, 68, 0.3))",
                    borderRadius: "8px",
                    color: "var(--status-danger, #ef4444)",
                    fontSize: "0.8125rem",
                    marginBottom: "1rem",
                  }}
                >
                  {modalError}
                </div>
              )}

              <form onSubmit={handleSubmitMapping} style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
                <div>
                  <label style={{ display: "block", fontSize: "0.8125rem", fontWeight: 600, marginBottom: "0.35rem" }}>
                    Connector Instance
                  </label>
                  <input
                    type="text"
                    readOnly
                    value={`${selectedInstanceObj?.label || selectedInstanceObj?.connector_code || selectedInstance}`}
                    style={{
                      width: "100%",
                      padding: "0.6rem 0.8rem",
                      borderRadius: "6px",
                      border: "1px solid var(--border-subtle)",
                      background: "var(--glass-surface)",
                      color: "var(--text-muted)",
                      fontSize: "0.875rem",
                      cursor: "not-allowed",
                    }}
                  />
                </div>

                <div>
                  <label style={{ display: "block", fontSize: "0.8125rem", fontWeight: 600, marginBottom: "0.35rem" }}>
                    VibeConnect Organization ID *
                  </label>
                  <input
                    type="text"
                    required
                    value={formOrgId}
                    onChange={(e) => setFormOrgId(e.target.value)}
                    placeholder="Organization UUID"
                    style={{
                      width: "100%",
                      padding: "0.6rem 0.8rem",
                      borderRadius: "6px",
                      border: "1px solid var(--border-subtle)",
                      background: "var(--glass-surface)",
                      color: "var(--text-primary)",
                      fontSize: "0.875rem",
                    }}
                  />
                </div>

                {modalType === "user" && (
                  <div>
                    <label style={{ display: "block", fontSize: "0.8125rem", fontWeight: 600, marginBottom: "0.35rem" }}>
                      VibeConnect User ID *
                    </label>
                    <input
                      type="text"
                      required
                      value={formUserId}
                      onChange={(e) => setFormUserId(e.target.value)}
                      placeholder="User UUID"
                      style={{
                        width: "100%",
                        padding: "0.6rem 0.8rem",
                        borderRadius: "6px",
                        border: "1px solid var(--border-subtle)",
                        background: "var(--glass-surface)",
                        color: "var(--text-primary)",
                        fontSize: "0.875rem",
                      }}
                    />
                  </div>
                )}

                <div>
                  <label style={{ display: "block", fontSize: "0.8125rem", fontWeight: 600, marginBottom: "0.35rem" }}>
                    External {modalType === "tenant" ? "Tenant" : "User"} ID *
                  </label>
                  <input
                    type="text"
                    required
                    value={formExternalId}
                    onChange={(e) => setFormExternalId(e.target.value)}
                    placeholder={modalType === "tenant" ? "e.g. lms_tenant_441" : "e.g. lms_user_992"}
                    style={{
                      width: "100%",
                      padding: "0.6rem 0.8rem",
                      borderRadius: "6px",
                      border: "1px solid var(--border-subtle)",
                      background: "var(--glass-surface)",
                      color: "var(--text-primary)",
                      fontSize: "0.875rem",
                    }}
                  />
                </div>

                <div style={{ display: "flex", justifyContent: "flex-end", gap: "0.75rem", marginTop: "0.5rem" }}>
                  <button
                    type="button"
                    onClick={() => setIsModalOpen(false)}
                    className="btn-secondary"
                    style={{ padding: "0.5rem 1rem", borderRadius: "6px", fontSize: "0.875rem" }}
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={isSubmitting}
                    className="btn-primary"
                    style={{ padding: "0.5rem 1rem", borderRadius: "6px", fontSize: "0.875rem" }}
                  >
                    {isSubmitting ? "Creating..." : "Create Mapping"}
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
