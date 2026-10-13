/**
 * Tenant Developer Console Page (Phase 6B Stage 4).
 *
 * Route: /tenant/developer
 * Context Guard: tenant (adminOnly=true)
 * Strict tenant-isolated programmatic integration management.
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
  type DeveloperWebhookSubscription,
  type DeveloperWebhookDelivery,
} from "../../api/developer.ts";

const ALLOWED_SCOPES = [
  { id: "catalog:read", label: "Catalog Read", desc: "Access active published catalog products & plans" },
  { id: "organization:read", label: "Organization Read", desc: "Read-only tenant profile metadata" },
  { id: "entitlements:read", label: "Entitlements Read", desc: "List tenant product entitlements" },
  { id: "assignments:read", label: "Assignments Read", desc: "List user product assignments" },
];

const SUPPORTED_TOPICS = [
  { id: "entitlement.granted", label: "Entitlement Granted", desc: "Fired when a product entitlement is granted" },
  { id: "entitlement.revoked", label: "Entitlement Revoked", desc: "Fired when a product entitlement is revoked" },
  { id: "assignment.created", label: "Assignment Created", desc: "Fired when user product assignment is created" },
  { id: "assignment.revoked", label: "Assignment Revoked", desc: "Fired when user product assignment is revoked" },
  { id: "product.activated", label: "Product Activated", desc: "Fired when product catalog status is active" },
];

export const TenantDeveloperConsolePage: React.FC = () => {
  const [apps, setApps] = useState<DeveloperApplication[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [searchTerm, setSearchTerm] = useState<string>("");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  // App Selection / Detail Modal
  const [selectedApp, setSelectedApp] = useState<DeveloperApplication | null>(null);
  const [keys, setKeys] = useState<DeveloperApiKey[]>([]);
  const [isLoadingKeys, setIsLoadingKeys] = useState<boolean>(false);

  // Create App Modal
  const [showCreateAppModal, setShowCreateAppModal] = useState<boolean>(false);
  const [newAppName, setNewAppName] = useState<string>("");
  const [newAppDesc, setNewAppDesc] = useState<string>("");
  const [isSubmittingApp, setIsSubmittingApp] = useState<boolean>(false);

  // Create Key Modal
  const [showCreateKeyModal, setShowCreateKeyModal] = useState<boolean>(false);
  const [newKeyName, setNewKeyName] = useState<string>("");
  const [selectedScopes, setSelectedScopes] = useState<string[]>(["catalog:read"]);
  const [keyExpiresAt, setKeyExpiresAt] = useState<string>("");
  const [isSubmittingKey, setIsSubmittingKey] = useState<boolean>(false);

  // One-time Plaintext Key Display Modal
  const [oneTimeKey, setOneTimeKey] = useState<{ name: string; key: string } | null>(null);
  const [copiedKey, setCopiedKey] = useState<boolean>(false);

  // Webhook Tab & State (Phase 6B-6)
  const [appTab, setAppTab] = useState<"keys" | "webhooks">("keys");
  const [webhooks, setWebhooks] = useState<DeveloperWebhookSubscription[]>([]);
  const [isLoadingWebhooks, setIsLoadingWebhooks] = useState<boolean>(false);
  const [showCreateWebhookModal, setShowCreateWebhookModal] = useState<boolean>(false);
  const [newWebhookUrl, setNewWebhookUrl] = useState<string>("");
  const [newWebhookTopics, setNewWebhookTopics] = useState<string[]>(["entitlement.granted"]);
  const [isSubmittingWebhook, setIsSubmittingWebhook] = useState<boolean>(false);
  const [oneTimeSecret, setOneTimeSecret] = useState<{ url: string; secret: string } | null>(null);
  const [copiedSecret, setCopiedSecret] = useState<boolean>(false);
  const [deliveriesWebhook, setDeliveriesWebhook] = useState<DeveloperWebhookSubscription | null>(null);
  const [deliveries, setDeliveries] = useState<DeveloperWebhookDelivery[]>([]);
  const [isLoadingDeliveries, setIsLoadingDeliveries] = useState<boolean>(false);

  const fetchApps = useCallback(async () => {
    setIsLoading(true);
    setErrorMessage(null);
    try {
      const res = await developerApi.listTenantApps(searchTerm);
      setApps(res.results || []);
    } catch (err: unknown) {
      setErrorMessage("Failed to load developer applications.");
    } finally {
      setIsLoading(false);
    }
  }, [searchTerm]);

  useEffect(() => {
    void fetchApps();
  }, [fetchApps]);

  const loadAppData = async (app: DeveloperApplication) => {
    setSelectedApp(app);
    setIsLoadingKeys(true);
    setIsLoadingWebhooks(true);
    try {
      const [keyRes, whRes] = await Promise.all([
        developerApi.listTenantKeys(app.id),
        developerApi.listTenantWebhooks(app.id),
      ]);
      setKeys(keyRes.results || []);
      setWebhooks(whRes.results || []);
    } catch (err) {
      setErrorMessage("Failed to load application resources.");
    } finally {
      setIsLoadingKeys(false);
      setIsLoadingWebhooks(false);
    }
  };

  const loadAppKeys = async (app: DeveloperApplication) => {
    setIsLoadingKeys(true);
    try {
      const res = await developerApi.listTenantKeys(app.id);
      setKeys(res.results || []);
    } catch (err) {
      setErrorMessage("Failed to load API keys.");
    } finally {
      setIsLoadingKeys(false);
    }
  };

  const loadAppWebhooks = async (app: DeveloperApplication) => {
    setIsLoadingWebhooks(true);
    try {
      const res = await developerApi.listTenantWebhooks(app.id);
      setWebhooks(res.results || []);
    } catch (err) {
      setErrorMessage("Failed to load webhooks.");
    } finally {
      setIsLoadingWebhooks(false);
    }
  };

  const handleCreateApp = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newAppName.trim()) return;

    setIsSubmittingApp(true);
    try {
      const created = await developerApi.createTenantApp({
        name: newAppName.trim(),
        description: newAppDesc.trim(),
      });
      setShowCreateAppModal(false);
      setNewAppName("");
      setNewAppDesc("");
      setSuccessMessage(`Application "${created.name}" created successfully.`);
      void fetchApps();
    } catch (err: unknown) {
      setErrorMessage("Failed to create application.");
    } finally {
      setIsSubmittingApp(false);
    }
  };

  const handleSuspendApp = async (app: DeveloperApplication) => {
    if (!window.confirm(`Suspend application "${app.name}"? All active API keys will be immediately blocked.`)) {
      return;
    }
    try {
      await developerApi.suspendTenantApp(app.id, "Suspended via Developer Console");
      setSuccessMessage(`Application "${app.name}" suspended.`);
      void fetchApps();
      if (selectedApp?.id === app.id) {
        setSelectedApp({ ...app, status: "suspended" });
      }
    } catch (err) {
      setErrorMessage("Failed to suspend application.");
    }
  };

  const handleReactivateApp = async (app: DeveloperApplication) => {
    try {
      await developerApi.reactivateTenantApp(app.id, "Reactivated via Developer Console");
      setSuccessMessage(`Application "${app.name}" reactivated.`);
      void fetchApps();
      if (selectedApp?.id === app.id) {
        setSelectedApp({ ...app, status: "active" });
      }
    } catch (err) {
      setErrorMessage("Failed to reactivate application.");
    }
  };

  const handleRevokeApp = async (app: DeveloperApplication) => {
    if (
      !window.confirm(
        `Permanently revoke "${app.name}"? This action cannot be undone and will permanently disable all associated API keys.`
      )
    ) {
      return;
    }
    try {
      await developerApi.revokeTenantApp(app.id, "Revoked via Developer Console");
      setSuccessMessage(`Application "${app.name}" permanently revoked.`);
      void fetchApps();
      if (selectedApp?.id === app.id) {
        setSelectedApp({ ...app, status: "revoked" });
        void loadAppKeys(app);
      }
    } catch (err) {
      setErrorMessage("Failed to revoke application.");
    }
  };

  const handleCreateKey = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedApp || !newKeyName.trim() || selectedScopes.length === 0) return;

    setIsSubmittingKey(true);
    try {
      const res = await developerApi.createTenantKey(selectedApp.id, {
        name: newKeyName.trim(),
        scopes: selectedScopes,
        expires_at: keyExpiresAt ? new Date(keyExpiresAt).toISOString() : null,
      });

      setShowCreateKeyModal(false);
      setNewKeyName("");
      setSelectedScopes(["catalog:read"]);
      setKeyExpiresAt("");

      // Set one-time key display
      if (res.plaintext_key) {
        setOneTimeKey({ name: res.name, key: res.plaintext_key });
      }

      void loadAppKeys(selectedApp);
      void fetchApps();
    } catch (err) {
      setErrorMessage("Failed to generate API key.");
    } finally {
      setIsSubmittingKey(false);
    }
  };

  const handleRotateKey = async (key: DeveloperApiKey) => {
    if (!selectedApp) return;
    if (
      !window.confirm(
        `Rotate key "${key.name}"? The existing key will be immediately revoked and replaced with a new key with identical scopes.`
      )
    ) {
      return;
    }

    try {
      const res = await developerApi.rotateTenantKey(selectedApp.id, key.id);
      if (res.plaintext_key) {
        setOneTimeKey({ name: res.name, key: res.plaintext_key });
      }
      setSuccessMessage(`API key rotated successfully.`);
      void loadAppKeys(selectedApp);
    } catch (err) {
      setErrorMessage("Failed to rotate API key.");
    }
  };

  const handleRevokeKey = async (key: DeveloperApiKey) => {
    if (!selectedApp) return;
    if (!window.confirm(`Permanently revoke key "${key.name}"? It will no longer be able to authenticate.`)) {
      return;
    }

    try {
      await developerApi.revokeTenantKey(selectedApp.id, key.id, "Revoked via Developer Console");
      setSuccessMessage(`API key "${key.name}" revoked.`);
      void loadAppKeys(selectedApp);
    } catch (err) {
      setErrorMessage("Failed to revoke API key.");
    }
  };

  const handleCreateWebhook = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedApp || !newWebhookUrl.trim() || newWebhookTopics.length === 0) return;

    setIsSubmittingWebhook(true);
    try {
      const res = await developerApi.createTenantWebhook(selectedApp.id, {
        target_url: newWebhookUrl.trim(),
        event_topics: newWebhookTopics,
      });

      setShowCreateWebhookModal(false);
      setNewWebhookUrl("");
      setNewWebhookTopics(["entitlement.granted"]);

      if (res.signing_secret) {
        setOneTimeSecret({ url: res.target_url, secret: res.signing_secret });
      }

      setSuccessMessage("Webhook subscription created successfully.");
      void loadAppWebhooks(selectedApp);
    } catch (err) {
      setErrorMessage("Failed to create webhook subscription.");
    } finally {
      setIsSubmittingWebhook(false);
    }
  };

  const handleRotateWebhookSecret = async (sub: DeveloperWebhookSubscription) => {
    if (!selectedApp) return;
    if (
      !window.confirm(
        `Rotate signing secret for "${sub.target_url}"? The existing secret will be replaced immediately.`
      )
    ) {
      return;
    }

    try {
      const res = await developerApi.rotateTenantWebhookSecret(sub.id);
      if (res.signing_secret) {
        setOneTimeSecret({ url: res.target_url, secret: res.signing_secret });
      }
      setSuccessMessage("Webhook secret rotated successfully.");
      void loadAppWebhooks(selectedApp);
    } catch (err) {
      setErrorMessage("Failed to rotate webhook secret.");
    }
  };

  const handleSuspendWebhook = async (sub: DeveloperWebhookSubscription) => {
    if (!selectedApp) return;
    try {
      await developerApi.suspendTenantWebhook(sub.id, "Suspended via Developer Console");
      setSuccessMessage("Webhook subscription suspended.");
      void loadAppWebhooks(selectedApp);
    } catch (err) {
      setErrorMessage("Failed to suspend webhook.");
    }
  };

  const handleReactivateWebhook = async (sub: DeveloperWebhookSubscription) => {
    if (!selectedApp) return;
    try {
      await developerApi.reactivateTenantWebhook(sub.id);
      setSuccessMessage("Webhook subscription reactivated.");
      void loadAppWebhooks(selectedApp);
    } catch (err) {
      setErrorMessage("Failed to reactivate webhook.");
    }
  };

  const handleRevokeWebhook = async (sub: DeveloperWebhookSubscription) => {
    if (!selectedApp) return;
    if (
      !window.confirm(
        `Permanently revoke webhook for "${sub.target_url}"? It will no longer receive any events.`
      )
    ) {
      return;
    }

    try {
      await developerApi.revokeTenantWebhook(sub.id, "Revoked via Developer Console");
      setSuccessMessage("Webhook subscription revoked.");
      void loadAppWebhooks(selectedApp);
    } catch (err) {
      setErrorMessage("Failed to revoke webhook.");
    }
  };

  const handleViewDeliveries = async (sub: DeveloperWebhookSubscription) => {
    setDeliveriesWebhook(sub);
    setIsLoadingDeliveries(true);
    try {
      const res = await developerApi.listTenantDeliveries(sub.id);
      setDeliveries(res.results || []);
    } catch (err) {
      setErrorMessage("Failed to load webhook deliveries.");
    } finally {
      setIsLoadingDeliveries(false);
    }
  };

  const handleReplayDelivery = async (deliveryId: string) => {
    try {
      await developerApi.replayTenantDelivery(deliveryId);
      setSuccessMessage("Webhook delivery replayed.");
      if (deliveriesWebhook) {
        void handleViewDeliveries(deliveriesWebhook);
      }
    } catch (err) {
      setErrorMessage("Failed to replay delivery.");
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
              <h1 style={{ fontSize: "1.75rem", fontWeight: 700, margin: 0 }}>Developer Console</h1>
            </div>
            <p style={{ color: "var(--text-secondary)", margin: 0, fontSize: "0.9375rem" }}>
              Manage tenant-scoped API applications, scoped credentials, and integration keys.
            </p>
          </div>
          <button
            type="button"
            className="btn-primary"
            onClick={() => setShowCreateAppModal(true)}
            style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}
          >
            <span>+ Register Application</span>
          </button>
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

        {/* Applications List */}
        <GlassPanel padding="lg" style={{ marginBottom: "2rem" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1.5rem" }}>
            <h2 style={{ fontSize: "1.125rem", fontWeight: 600, margin: 0 }}>Registered Applications</h2>
            <input
              type="text"
              placeholder="Search applications..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="input-text"
              style={{ width: "240px", padding: "0.5rem 0.75rem", fontSize: "0.875rem" }}
            />
          </div>

          {isLoading ? (
            <LoadingSpinner label="Loading applications..." />
          ) : apps.length === 0 ? (
            <div style={{ textAlign: "center", padding: "3rem 1rem", color: "var(--text-secondary)" }}>
              <CodeIcon size={48} style={{ opacity: 0.4, marginBottom: "1rem" }} />
              <p style={{ fontSize: "1rem", fontWeight: 500 }}>No developer applications registered yet.</p>
              <p style={{ fontSize: "0.875rem" }}>Click "Register Application" above to generate your first integration client.</p>
            </div>
          ) : (
            <div className="table-responsive">
              <table className="table" style={{ width: "100%", textAlign: "left" }}>
                <thead>
                  <tr style={{ borderBottom: "1px solid var(--border-glass)" }}>
                    <th style={{ padding: "0.75rem" }}>Application</th>
                    <th style={{ padding: "0.75rem" }}>Status</th>
                    <th style={{ padding: "0.75rem" }}>Active Keys</th>
                    <th style={{ padding: "0.75rem" }}>Created</th>
                    <th style={{ padding: "0.75rem", textAlign: "right" }}>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {apps.map((app) => (
                    <tr key={app.id} style={{ borderBottom: "1px solid var(--border-glass-subtle)" }}>
                      <td style={{ padding: "0.75rem" }}>
                        <div style={{ fontWeight: 600 }}>{app.name}</div>
                        {app.description && (
                          <div style={{ fontSize: "0.8125rem", color: "var(--text-secondary)" }}>{app.description}</div>
                        )}
                      </td>
                      <td style={{ padding: "0.75rem" }}>{getStatusBadge(app.status)}</td>
                      <td style={{ padding: "0.75rem" }}>{app.active_keys_count} active</td>
                      <td style={{ padding: "0.75rem", fontSize: "0.875rem", color: "var(--text-secondary)" }}>
                        {new Date(app.created_at).toLocaleDateString()}
                      </td>
                      <td style={{ padding: "0.75rem", textAlign: "right" }}>
                        <div style={{ display: "inline-flex", gap: "0.5rem" }}>
                          <button
                            type="button"
                            className="btn-secondary"
                            onClick={() => void loadAppData(app)}
                            style={{ padding: "0.375rem 0.75rem", fontSize: "0.8125rem" }}
                          >
                            Manage App
                          </button>
                          {app.status === "active" && (
                            <button
                              type="button"
                              className="btn-ghost"
                              onClick={() => void handleSuspendApp(app)}
                              style={{ padding: "0.375rem 0.5rem", fontSize: "0.8125rem" }}
                            >
                              Suspend
                            </button>
                          )}
                          {app.status === "suspended" && (
                            <button
                              type="button"
                              className="btn-ghost"
                              onClick={() => void handleReactivateApp(app)}
                              style={{ padding: "0.375rem 0.5rem", fontSize: "0.8125rem", color: "var(--status-success)" }}
                            >
                              Reactivate
                            </button>
                          )}
                          {app.status !== "revoked" && (
                            <button
                              type="button"
                              className="btn-ghost"
                              onClick={() => void handleRevokeApp(app)}
                              style={{ padding: "0.375rem 0.5rem", fontSize: "0.8125rem", color: "var(--status-danger)" }}
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

        {/* Selected App Resources Section */}
        {selectedApp && (
          <GlassPanel padding="lg" style={{ marginTop: "2rem" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1.25rem" }}>
              <div>
                <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                  <CodeIcon size={20} />
                  <h2 style={{ fontSize: "1.25rem", fontWeight: 600, margin: 0 }}>
                    {selectedApp.name}
                  </h2>
                  {getStatusBadge(selectedApp.status)}
                </div>
                <p style={{ color: "var(--text-secondary)", fontSize: "0.875rem", margin: "0.25rem 0 0" }}>
                  Manage scoped API keys and outbound webhook subscriptions for this application.
                </p>
              </div>
              <div style={{ display: "flex", gap: "0.5rem" }}>
                {selectedApp.status === "active" && appTab === "keys" && (
                  <button
                    type="button"
                    className="btn-primary"
                    onClick={() => setShowCreateKeyModal(true)}
                    style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}
                  >
                    <span>+ Generate New Key</span>
                  </button>
                )}
                {selectedApp.status === "active" && appTab === "webhooks" && (
                  <button
                    type="button"
                    className="btn-primary"
                    onClick={() => setShowCreateWebhookModal(true)}
                    style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}
                  >
                    <span>+ Add Webhook</span>
                  </button>
                )}
              </div>
            </div>

            {/* Tabs */}
            <div style={{ display: "flex", gap: "1rem", borderBottom: "1px solid var(--border-glass)", marginBottom: "1.5rem" }}>
              <button
                type="button"
                className="btn-ghost"
                style={{
                  padding: "0.5rem 1rem",
                  borderBottom: appTab === "keys" ? "2px solid var(--accent-primary)" : "2px solid transparent",
                  fontWeight: appTab === "keys" ? 600 : 400,
                  color: appTab === "keys" ? "var(--text-primary)" : "var(--text-secondary)",
                  borderRadius: 0,
                }}
                onClick={() => setAppTab("keys")}
              >
                API Keys ({keys.length})
              </button>
              <button
                type="button"
                className="btn-ghost"
                style={{
                  padding: "0.5rem 1rem",
                  borderBottom: appTab === "webhooks" ? "2px solid var(--accent-primary)" : "2px solid transparent",
                  fontWeight: appTab === "webhooks" ? 600 : 400,
                  color: appTab === "webhooks" ? "var(--text-primary)" : "var(--text-secondary)",
                  borderRadius: 0,
                }}
                onClick={() => setAppTab("webhooks")}
              >
                Webhooks ({webhooks.length})
              </button>
            </div>

            {/* Keys Tab Content */}
            {appTab === "keys" && (
              <>
                {isLoadingKeys ? (
                  <LoadingSpinner label="Loading keys..." />
                ) : keys.length === 0 ? (
                  <div style={{ textAlign: "center", padding: "2rem 1rem", color: "var(--text-secondary)" }}>
                    <p>No API keys generated for this application yet.</p>
                  </div>
                ) : (
                  <div className="table-responsive">
                    <table className="table" style={{ width: "100%", textAlign: "left" }}>
                      <thead>
                        <tr style={{ borderBottom: "1px solid var(--border-glass)" }}>
                          <th style={{ padding: "0.75rem" }}>Key Name</th>
                          <th style={{ padding: "0.75rem" }}>Key Prefix</th>
                          <th style={{ padding: "0.75rem" }}>Granted Scopes</th>
                          <th style={{ padding: "0.75rem" }}>Status</th>
                          <th style={{ padding: "0.75rem" }}>Last Used</th>
                          <th style={{ padding: "0.75rem" }}>Created</th>
                          <th style={{ padding: "0.75rem", textAlign: "right" }}>Actions</th>
                        </tr>
                      </thead>
                      <tbody>
                        {keys.map((k) => (
                          <tr key={k.id} style={{ borderBottom: "1px solid var(--border-glass-subtle)" }}>
                            <td style={{ padding: "0.75rem", fontWeight: 600 }}>{k.name}</td>
                            <td style={{ padding: "0.75rem" }}>
                              <code style={{ fontSize: "0.8125rem", background: "var(--bg-card)", padding: "0.2rem 0.4rem", borderRadius: "4px" }}>
                                {k.key_prefix}...
                              </code>
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
                              {k.status === "active" && selectedApp.status === "active" && (
                                <div style={{ display: "inline-flex", gap: "0.5rem" }}>
                                  <button
                                    type="button"
                                    className="btn-secondary"
                                    onClick={() => void handleRotateKey(k)}
                                    style={{ padding: "0.25rem 0.5rem", fontSize: "0.75rem" }}
                                  >
                                    Rotate
                                  </button>
                                  <button
                                    type="button"
                                    className="btn-ghost"
                                    onClick={() => void handleRevokeKey(k)}
                                    style={{ padding: "0.25rem 0.5rem", fontSize: "0.75rem", color: "var(--status-danger)" }}
                                  >
                                    Revoke
                                  </button>
                                </div>
                              )}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </>
            )}

            {/* Webhooks Tab Content */}
            {appTab === "webhooks" && (
              <>
                {isLoadingWebhooks ? (
                  <LoadingSpinner label="Loading webhooks..." />
                ) : webhooks.length === 0 ? (
                  <div style={{ textAlign: "center", padding: "2rem 1rem", color: "var(--text-secondary)" }}>
                    <p>No webhook subscriptions configured for this application yet.</p>
                  </div>
                ) : (
                  <div className="table-responsive">
                    <table className="table" style={{ width: "100%", textAlign: "left" }}>
                      <thead>
                        <tr style={{ borderBottom: "1px solid var(--border-glass)" }}>
                          <th style={{ padding: "0.75rem" }}>Target URL</th>
                          <th style={{ padding: "0.75rem" }}>Event Topics</th>
                          <th style={{ padding: "0.75rem" }}>Status</th>
                          <th style={{ padding: "0.75rem" }}>Created</th>
                          <th style={{ padding: "0.75rem", textAlign: "right" }}>Actions</th>
                        </tr>
                      </thead>
                      <tbody>
                        {webhooks.map((w) => (
                          <tr key={w.id} style={{ borderBottom: "1px solid var(--border-glass-subtle)" }}>
                            <td style={{ padding: "0.75rem", fontWeight: 500 }}>
                              <code style={{ fontSize: "0.8125rem", background: "var(--bg-card)", padding: "0.2rem 0.4rem", borderRadius: "4px" }}>
                                {w.target_url}
                              </code>
                            </td>
                            <td style={{ padding: "0.75rem" }}>
                              <div style={{ display: "flex", flexWrap: "wrap", gap: "0.25rem" }}>
                                {w.event_topics.map((t) => (
                                  <span key={t} className="badge badge-neutral" style={{ fontSize: "0.75rem" }}>
                                    {t}
                                  </span>
                                ))}
                              </div>
                            </td>
                            <td style={{ padding: "0.75rem" }}>{getStatusBadge(w.status)}</td>
                            <td style={{ padding: "0.75rem", fontSize: "0.8125rem", color: "var(--text-secondary)" }}>
                              {new Date(w.created_at).toLocaleDateString()}
                            </td>
                            <td style={{ padding: "0.75rem", textAlign: "right" }}>
                              <div style={{ display: "inline-flex", gap: "0.5rem" }}>
                                <button
                                  type="button"
                                  className="btn-secondary"
                                  onClick={() => void handleViewDeliveries(w)}
                                  style={{ padding: "0.25rem 0.5rem", fontSize: "0.75rem" }}
                                >
                                  Deliveries
                                </button>
                                {w.status === "active" && selectedApp.status === "active" && (
                                  <>
                                    <button
                                      type="button"
                                      className="btn-secondary"
                                      onClick={() => void handleRotateWebhookSecret(w)}
                                      style={{ padding: "0.25rem 0.5rem", fontSize: "0.75rem" }}
                                    >
                                      Rotate Secret
                                    </button>
                                    <button
                                      type="button"
                                      className="btn-ghost"
                                      onClick={() => void handleSuspendWebhook(w)}
                                      style={{ padding: "0.25rem 0.5rem", fontSize: "0.75rem" }}
                                    >
                                      Suspend
                                    </button>
                                  </>
                                )}
                                {w.status === "suspended" && selectedApp.status === "active" && (
                                  <button
                                    type="button"
                                    className="btn-ghost"
                                    onClick={() => void handleReactivateWebhook(w)}
                                    style={{ padding: "0.25rem 0.5rem", fontSize: "0.75rem", color: "var(--status-success)" }}
                                  >
                                    Reactivate
                                  </button>
                                )}
                                {w.status !== "revoked" && (
                                  <button
                                    type="button"
                                    className="btn-ghost"
                                    onClick={() => void handleRevokeWebhook(w)}
                                    style={{ padding: "0.25rem 0.5rem", fontSize: "0.75rem", color: "var(--status-danger)" }}
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
              </>
            )}
          </GlassPanel>
        )}

        {/* Modal: Register Application */}
        {showCreateAppModal && (
          <div className="modal-backdrop" style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.6)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 100 }}>
            <GlassPanel padding="xl" style={{ maxWidth: "480px", width: "100%", background: "var(--bg-modal, #1e2238)" }}>
              <h2 style={{ fontSize: "1.25rem", fontWeight: 700, marginBottom: "1rem" }}>Register Developer Application</h2>
              <form onSubmit={handleCreateApp}>
                <div style={{ marginBottom: "1rem" }}>
                  <label style={{ display: "block", fontSize: "0.875rem", fontWeight: 500, marginBottom: "0.375rem" }}>
                    Application Name *
                  </label>
                  <input
                    type="text"
                    required
                    value={newAppName}
                    onChange={(e) => setNewAppName(e.target.value)}
                    placeholder="e.g. ERP Integration Service"
                    className="input-text"
                    style={{ width: "100%" }}
                  />
                </div>
                <div style={{ marginBottom: "1.5rem" }}>
                  <label style={{ display: "block", fontSize: "0.875rem", fontWeight: 500, marginBottom: "0.375rem" }}>
                    Description
                  </label>
                  <textarea
                    rows={3}
                    value={newAppDesc}
                    onChange={(e) => setNewAppDesc(e.target.value)}
                    placeholder="Purpose of this application integration..."
                    className="input-text"
                    style={{ width: "100%" }}
                  />
                </div>
                <div style={{ display: "flex", justifyContent: "flex-end", gap: "0.75rem" }}>
                  <button type="button" className="btn-ghost" onClick={() => setShowCreateAppModal(false)}>
                    Cancel
                  </button>
                  <button type="submit" className="btn-primary" disabled={isSubmittingApp || !newAppName.trim()}>
                    {isSubmittingApp ? "Registering..." : "Register Application"}
                  </button>
                </div>
              </form>
            </GlassPanel>
          </div>
        )}

        {/* Modal: Generate New Key */}
        {showCreateKeyModal && selectedApp && (
          <div className="modal-backdrop" style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.6)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 100 }}>
            <GlassPanel padding="xl" style={{ maxWidth: "520px", width: "100%", background: "var(--bg-modal, #1e2238)" }}>
              <h2 style={{ fontSize: "1.25rem", fontWeight: 700, marginBottom: "0.5rem" }}>
                Generate Key for {selectedApp.name}
              </h2>
              <p style={{ color: "var(--text-secondary)", fontSize: "0.875rem", marginBottom: "1.25rem" }}>
                Select allowed scopes. Scopes cannot be expanded after generation.
              </p>
              <form onSubmit={handleCreateKey}>
                <div style={{ marginBottom: "1rem" }}>
                  <label style={{ display: "block", fontSize: "0.875rem", fontWeight: 500, marginBottom: "0.375rem" }}>
                    Key Label *
                  </label>
                  <input
                    type="text"
                    required
                    value={newKeyName}
                    onChange={(e) => setNewKeyName(e.target.value)}
                    placeholder="e.g. Production Catalog Sync"
                    className="input-text"
                    style={{ width: "100%" }}
                  />
                </div>

                <div style={{ marginBottom: "1.25rem" }}>
                  <label style={{ display: "block", fontSize: "0.875rem", fontWeight: 500, marginBottom: "0.5rem" }}>
                    Allowed Scopes (Read-Only) *
                  </label>
                  <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
                    {ALLOWED_SCOPES.map((scope) => (
                      <label
                        key={scope.id}
                        style={{
                          display: "flex",
                          alignItems: "flex-start",
                          gap: "0.75rem",
                          padding: "0.5rem 0.75rem",
                          borderRadius: "6px",
                          background: "var(--bg-card)",
                          cursor: "pointer",
                        }}
                      >
                        <input
                          type="checkbox"
                          checked={selectedScopes.includes(scope.id)}
                          onChange={(e) => {
                            if (e.target.checked) {
                              setSelectedScopes([...selectedScopes, scope.id]);
                            } else {
                              setSelectedScopes(selectedScopes.filter((s) => s !== scope.id));
                            }
                          }}
                          style={{ marginTop: "0.2rem" }}
                        />
                        <div>
                          <div style={{ fontWeight: 600, fontSize: "0.875rem" }}>{scope.label} (<code>{scope.id}</code>)</div>
                          <div style={{ fontSize: "0.75rem", color: "var(--text-secondary)" }}>{scope.desc}</div>
                        </div>
                      </label>
                    ))}
                  </div>
                </div>

                <div style={{ display: "flex", justifyContent: "flex-end", gap: "0.75rem" }}>
                  <button type="button" className="btn-ghost" onClick={() => setShowCreateKeyModal(false)}>
                    Cancel
                  </button>
                  <button
                    type="submit"
                    className="btn-primary"
                    disabled={isSubmittingKey || !newKeyName.trim() || selectedScopes.length === 0}
                  >
                    {isSubmittingKey ? "Generating..." : "Generate Key"}
                  </button>
                </div>
              </form>
            </GlassPanel>
          </div>
        )}

        {/* Modal: ONE-TIME Plaintext Secret Display */}
        {oneTimeKey && (
          <div className="modal-backdrop" style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.75)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 200 }}>
            <GlassPanel padding="xl" style={{ maxWidth: "560px", width: "100%", background: "var(--bg-modal, #1e2238)" }}>
              <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", marginBottom: "1rem" }}>
                <div style={{ color: "var(--status-warning)" }}>
                  <ShieldCheckIcon size={28} />
                </div>
                <h2 style={{ fontSize: "1.25rem", fontWeight: 700, margin: 0 }}>API Key Generated Successfully</h2>
              </div>

              <div
                style={{
                  padding: "0.875rem 1rem",
                  background: "var(--status-warning-bg, rgba(234, 179, 8, 0.1))",
                  border: "1px solid var(--status-warning-border, rgba(234, 179, 8, 0.3))",
                  borderRadius: "8px",
                  color: "var(--status-warning, #eab308)",
                  fontSize: "0.875rem",
                  lineHeight: 1.5,
                  marginBottom: "1.25rem",
                }}
              >
                <strong>Important:</strong> This secret will <strong>never</strong> be displayed again. If you lose this key, you will need to rotate or generate a replacement.
              </div>

              <div style={{ marginBottom: "1.5rem" }}>
                <label style={{ display: "block", fontSize: "0.8125rem", color: "var(--text-secondary)", marginBottom: "0.375rem" }}>
                  Full API Key ({oneTimeKey.name})
                </label>
                <div style={{ display: "flex", gap: "0.5rem" }}>
                  <input
                    type="text"
                    readOnly
                    value={oneTimeKey.key}
                    style={{
                      fontFamily: "monospace",
                      fontSize: "0.875rem",
                      width: "100%",
                      padding: "0.625rem 0.75rem",
                      background: "var(--bg-card, #0f1225)",
                      border: "1px solid var(--border-glass)",
                      borderRadius: "6px",
                      color: "var(--text-primary)",
                    }}
                  />
                  <button
                    type="button"
                    className="btn-secondary"
                    onClick={() => {
                      void navigator.clipboard.writeText(oneTimeKey.key);
                      setCopiedKey(true);
                      setTimeout(() => setCopiedKey(false), 2000);
                    }}
                    style={{ whiteSpace: "nowrap" }}
                  >
                    {copiedKey ? "Copied!" : "Copy Key"}
                  </button>
                </div>
              </div>

              <div style={{ display: "flex", justifyContent: "flex-end" }}>
                <button
                  type="button"
                  className="btn-primary"
                  onClick={() => {
                    setOneTimeKey(null);
                    setCopiedKey(false);
                  }}
                >
                  I Have Saved My Key
                </button>
              </div>
            </GlassPanel>
          </div>
        )}

        {/* Modal: Create Webhook Subscription */}
        {showCreateWebhookModal && selectedApp && (
          <div className="modal-backdrop" style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.6)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 100 }}>
            <GlassPanel padding="xl" style={{ maxWidth: "520px", width: "100%", background: "var(--bg-modal, #1e2238)" }}>
              <h2 style={{ fontSize: "1.25rem", fontWeight: 700, marginBottom: "0.5rem" }}>
                Add Webhook Subscription
              </h2>
              <p style={{ color: "var(--text-secondary)", fontSize: "0.875rem", marginBottom: "1.25rem" }}>
                Configure HTTP endpoint to receive real-time signed event notifications.
              </p>
              <form onSubmit={handleCreateWebhook}>
                <div style={{ marginBottom: "1rem" }}>
                  <label style={{ display: "block", fontSize: "0.875rem", fontWeight: 500, marginBottom: "0.375rem" }}>
                    Payload URL (HTTP/HTTPS) *
                  </label>
                  <input
                    type="url"
                    required
                    value={newWebhookUrl}
                    onChange={(e) => setNewWebhookUrl(e.target.value)}
                    placeholder="https://api.yourdomain.com/webhooks/vibeconnect"
                    className="input-text"
                    style={{ width: "100%" }}
                  />
                </div>

                <div style={{ marginBottom: "1.25rem" }}>
                  <label style={{ display: "block", fontSize: "0.875rem", fontWeight: 500, marginBottom: "0.5rem" }}>
                    Subscribed Event Topics *
                  </label>
                  <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
                    {SUPPORTED_TOPICS.map((topic) => (
                      <label
                        key={topic.id}
                        style={{
                          display: "flex",
                          alignItems: "flex-start",
                          gap: "0.75rem",
                          padding: "0.5rem 0.75rem",
                          borderRadius: "6px",
                          background: "var(--bg-card)",
                          cursor: "pointer",
                        }}
                      >
                        <input
                          type="checkbox"
                          checked={newWebhookTopics.includes(topic.id)}
                          onChange={(e) => {
                            if (e.target.checked) {
                              setNewWebhookTopics([...newWebhookTopics, topic.id]);
                            } else {
                              setNewWebhookTopics(newWebhookTopics.filter((t) => t !== topic.id));
                            }
                          }}
                        />
                        <div>
                          <div style={{ fontSize: "0.875rem", fontWeight: 600 }}>{topic.label}</div>
                          <div style={{ fontSize: "0.75rem", color: "var(--text-secondary)" }}>{topic.desc}</div>
                        </div>
                      </label>
                    ))}
                  </div>
                </div>

                <div style={{ display: "flex", justifyContent: "flex-end", gap: "0.75rem" }}>
                  <button type="button" className="btn-ghost" onClick={() => setShowCreateWebhookModal(false)}>
                    Cancel
                  </button>
                  <button
                    type="submit"
                    className="btn-primary"
                    disabled={isSubmittingWebhook || !newWebhookUrl.trim() || newWebhookTopics.length === 0}
                  >
                    {isSubmittingWebhook ? "Creating..." : "Create Subscription"}
                  </button>
                </div>
              </form>
            </GlassPanel>
          </div>
        )}

        {/* Modal: One-time Webhook Secret Display */}
        {oneTimeSecret && (
          <div className="modal-backdrop" style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.6)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 100 }}>
            <GlassPanel padding="xl" style={{ maxWidth: "560px", width: "100%", background: "var(--bg-modal, #1e2238)" }}>
              <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.75rem" }}>
                <ShieldCheckIcon size={24} color="var(--status-warning)" />
                <h2 style={{ fontSize: "1.25rem", fontWeight: 700, margin: 0 }}>
                  Save Your Webhook Signing Secret
                </h2>
              </div>
              <p style={{ color: "var(--status-warning)", fontSize: "0.875rem", marginBottom: "1rem", lineHeight: 1.5 }}>
                This signing secret will <strong>never be shown again</strong>. Store it safely to verify the HMAC-SHA256 signature in incoming requests.
              </p>

              <div style={{ marginBottom: "1.25rem" }}>
                <label style={{ display: "block", fontSize: "0.8125rem", fontWeight: 500, color: "var(--text-secondary)", marginBottom: "0.25rem" }}>
                  Target Endpoint
                </label>
                <div style={{ fontSize: "0.875rem", fontFamily: "monospace", color: "var(--text-primary)", marginBottom: "0.75rem" }}>
                  {oneTimeSecret.url}
                </div>

                <label style={{ display: "block", fontSize: "0.8125rem", fontWeight: 500, color: "var(--text-secondary)", marginBottom: "0.25rem" }}>
                  Signing Secret
                </label>
                <div style={{ display: "flex", gap: "0.5rem" }}>
                  <input
                    type="text"
                    readOnly
                    value={oneTimeSecret.secret}
                    style={{
                      flex: 1,
                      fontFamily: "monospace",
                      fontSize: "0.8125rem",
                      padding: "0.5rem 0.75rem",
                      background: "var(--bg-card)",
                      border: "1px solid var(--border-glass)",
                      borderRadius: "6px",
                      color: "var(--text-primary)",
                    }}
                  />
                  <button
                    type="button"
                    className="btn-secondary"
                    onClick={() => {
                      void navigator.clipboard.writeText(oneTimeSecret.secret);
                      setCopiedSecret(true);
                      setTimeout(() => setCopiedSecret(false), 2000);
                    }}
                    style={{ whiteSpace: "nowrap" }}
                  >
                    {copiedSecret ? "Copied!" : "Copy Secret"}
                  </button>
                </div>
              </div>

              <div style={{ display: "flex", justifyContent: "flex-end" }}>
                <button
                  type="button"
                  className="btn-primary"
                  onClick={() => {
                    setOneTimeSecret(null);
                    setCopiedSecret(false);
                  }}
                >
                  I Have Saved My Secret
                </button>
              </div>
            </GlassPanel>
          </div>
        )}

        {/* Modal: Deliveries History & Replay */}
        {deliveriesWebhook && (
          <div className="modal-backdrop" style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.6)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 100 }}>
            <GlassPanel padding="xl" style={{ maxWidth: "760px", width: "100%", maxHeight: "85vh", overflowY: "auto", background: "var(--bg-modal, #1e2238)" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1rem" }}>
                <div>
                  <h2 style={{ fontSize: "1.25rem", fontWeight: 700, margin: 0 }}>
                    Webhook Delivery History
                  </h2>
                  <p style={{ color: "var(--text-secondary)", fontSize: "0.8125rem", margin: "0.25rem 0 0" }}>
                    {deliveriesWebhook.target_url}
                  </p>
                </div>
                <button
                  type="button"
                  className="btn-ghost"
                  onClick={() => setDeliveriesWebhook(null)}
                >
                  ✕
                </button>
              </div>

              {isLoadingDeliveries ? (
                <LoadingSpinner label="Loading delivery traces..." />
              ) : deliveries.length === 0 ? (
                <div style={{ textAlign: "center", padding: "2rem", color: "var(--text-secondary)" }}>
                  <p>No delivery attempts recorded for this webhook subscription yet.</p>
                </div>
              ) : (
                <div className="table-responsive">
                  <table className="table" style={{ width: "100%", textAlign: "left", fontSize: "0.8125rem" }}>
                    <thead>
                      <tr style={{ borderBottom: "1px solid var(--border-glass)" }}>
                        <th style={{ padding: "0.5rem" }}>Event Type</th>
                        <th style={{ padding: "0.5rem" }}>Status</th>
                        <th style={{ padding: "0.5rem" }}>HTTP Code</th>
                        <th style={{ padding: "0.5rem" }}>Attempt</th>
                        <th style={{ padding: "0.5rem" }}>Timestamp</th>
                        <th style={{ padding: "0.5rem", textAlign: "right" }}>Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {deliveries.map((d) => (
                        <tr key={d.id} style={{ borderBottom: "1px solid var(--border-glass-subtle)" }}>
                          <td style={{ padding: "0.5rem", fontFamily: "monospace" }}>{d.event_type}</td>
                          <td style={{ padding: "0.5rem" }}>{getStatusBadge(d.status)}</td>
                          <td style={{ padding: "0.5rem" }}>{d.status_code ?? "—"}</td>
                          <td style={{ padding: "0.5rem" }}>{d.attempt_count} / {d.max_attempts}</td>
                          <td style={{ padding: "0.5rem", color: "var(--text-secondary)" }}>
                            {new Date(d.created_at).toLocaleTimeString()}
                          </td>
                          <td style={{ padding: "0.5rem", textAlign: "right" }}>
                            {d.status !== "delivered" && (
                              <button
                                type="button"
                                className="btn-secondary"
                                onClick={() => void handleReplayDelivery(d.id)}
                                style={{ padding: "0.2rem 0.4rem", fontSize: "0.75rem" }}
                              >
                                Replay
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
      </div>
    </AppShell>
  );
};
