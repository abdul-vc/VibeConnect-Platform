/**
 * Tenant Developer Console Page (Phase 6B Stage 4).
 *
 * Route: /tenant/developer
 * Context Guard: tenant (adminOnly=true)
 * Strict tenant-isolated programmatic integration management.
 */

import React, { useState, useEffect, useCallback, useMemo } from "react";
import { Link } from "react-router-dom";
import { AppShell } from "../../components/AppShell.tsx";
import { LoadingSpinner } from "../../components/LoadingSpinner.tsx";
import {
  CodeIcon,
  ShieldCheckIcon,
  KeyIcon,
  RotateCcwIcon,
  AlertCircleIcon,
  CheckCircleIcon,
  SearchIcon,
  PlusIcon,
  CalendarIcon,
  GlobeIcon,
  CopyIcon,
  CloseIcon,
} from "../../components/Icons.tsx";
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
  const [statusFilter, setStatusFilter] = useState<string>("");
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

  const filteredApps = useMemo(() => {
    return apps.filter((app) => {
      if (statusFilter && app.status !== statusFilter) return false;
      return true;
    });
  }, [apps, statusFilter]);

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
            {status}
          </span>
        );
    }
  };

  return (
    <AppShell>
      <div style={{ maxWidth: "1400px", margin: "0 auto", padding: "2rem" }}>
        {/* Breadcrumb Navigation */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: "0.5rem",
            fontSize: "0.8125rem",
            color: "var(--text-muted)",
            marginBottom: "1.25rem",
            fontWeight: 500,
          }}
        >
          <Link
            to="/tenant"
            style={{ color: "var(--text-muted)", textDecoration: "none", transition: "color 0.15s" }}
          >
            Dashboard
          </Link>
          <span>/</span>
          <span>Infrastructure</span>
          <span>/</span>
          <span style={{ color: "var(--brand-primary)", fontWeight: 600 }}>Developer Console</span>
        </div>

        {/* Hero Header */}
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
              <CodeIcon size={24} />
            </div>
            <div>
              <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
                <h1
                  className="heading-hero"
                  style={{
                    fontSize: "1.75rem",
                    fontWeight: 800,
                    margin: 0,
                    letterSpacing: "-0.02em",
                    color: "var(--text-primary)",
                  }}
                >
                  Developer Console
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
                  {apps.length} {apps.length === 1 ? "App" : "Apps"}
                </span>
              </div>
              <p style={{ color: "var(--text-secondary)", margin: "0.25rem 0 0 0", fontSize: "0.9375rem" }}>
                Manage tenant-scoped API applications, scoped credentials, and integration keys.
              </p>
            </div>
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", flexWrap: "wrap" }}>
            <button
              type="button"
              onClick={() => void fetchApps()}
              disabled={isLoading}
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: "0.5rem",
                padding: "0.5rem 0.875rem",
                background: "var(--glass-surface-elevated)",
                border: "1px solid var(--border-subtle)",
                borderRadius: "8px",
                color: "var(--text-primary)",
                fontSize: "0.8125rem",
                fontWeight: 600,
                cursor: isLoading ? "not-allowed" : "pointer",
                boxShadow: "var(--shadow-sm)",
                transition: "all 0.15s ease",
              }}
            >
              <RotateCcwIcon size={14} className={isLoading ? "spin-pulse" : ""} />
              Refresh
            </button>
            <button
              type="button"
              className="btn-primary"
              onClick={() => setShowCreateAppModal(true)}
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: "0.5rem",
                padding: "0.5rem 1rem",
                fontSize: "0.875rem",
                fontWeight: 600,
              }}
            >
              <PlusIcon size={16} />
              <span>Register Application</span>
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

        {/* Applications List Table Card */}
        <div className="table-card-container" style={{ marginBottom: "2rem" }}>
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
                Registered Applications
              </h2>
              <p style={{ margin: "0.2rem 0 0", fontSize: "0.8125rem", color: "var(--text-secondary)" }}>
                Tenant-scoped client credentials and outbound webhook integrations.
              </p>
            </div>

            <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", flexWrap: "wrap" }}>
              {/* Status Segmented Control */}
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

              {/* Search Bar */}
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
                  placeholder="Search applications..."
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
              <LoadingSpinner label="Loading applications..." />
            </div>
          ) : filteredApps.length === 0 ? (
            <div style={{ textAlign: "center", padding: "3.5rem 1.5rem", color: "var(--text-secondary)" }}>
              <div
                style={{
                  width: 52,
                  height: 52,
                  borderRadius: 14,
                  background: "var(--surface-soft-blue)",
                  display: "inline-flex",
                  alignItems: "center",
                  justifyContent: "center",
                  color: "var(--brand-primary)",
                  marginBottom: "1rem",
                }}
              >
                <CodeIcon size={26} />
              </div>
              <p style={{ margin: 0, fontSize: "1rem", color: "var(--text-primary)", fontWeight: 600 }}>
                No developer applications registered yet
              </p>
              <p style={{ margin: "0.35rem 0 1.25rem", fontSize: "0.875rem" }}>
                {searchTerm || statusFilter
                  ? "No applications match your current search or status filter."
                  : "Click \"Register Application\" to generate your first integration client."}
              </p>
              {!searchTerm && !statusFilter && (
                <button
                  type="button"
                  className="btn-primary"
                  onClick={() => setShowCreateAppModal(true)}
                  style={{ display: "inline-flex", alignItems: "center", gap: "0.5rem", fontSize: "0.8125rem" }}
                >
                  <PlusIcon size={14} />
                  Register First Application
                </button>
              )}
            </div>
          ) : (
            <div className="table-card-scroll">
              <table style={{ width: "100%", borderCollapse: "collapse", textAlign: "left" }}>
                <thead>
                  <tr style={{ borderBottom: "1px solid var(--border-subtle)", background: "var(--glass-surface-sunken)" }}>
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
                      APPLICATION
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
                      ACTIVE KEYS
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
                      CREATED
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
                  {filteredApps.map((app) => (
                    <tr
                      key={app.id}
                      style={{
                        borderBottom: "1px solid var(--border-subtle)",
                        transition: "background-color 0.15s ease",
                        background: selectedApp?.id === app.id ? "var(--glass-surface-hover)" : "transparent",
                      }}
                      onMouseEnter={(e) => {
                        if (selectedApp?.id !== app.id) {
                          e.currentTarget.style.backgroundColor = "var(--glass-surface-hover)";
                        }
                      }}
                      onMouseLeave={(e) => {
                        if (selectedApp?.id !== app.id) {
                          e.currentTarget.style.backgroundColor = "transparent";
                        }
                      }}
                    >
                      <td style={{ padding: "1rem 1.25rem", verticalAlign: "middle" }}>
                        <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
                          <div
                            style={{
                              width: 38,
                              height: 38,
                              borderRadius: 10,
                              background: "var(--surface-soft-blue)",
                              border: "1px solid rgba(56, 103, 245, 0.2)",
                              display: "flex",
                              alignItems: "center",
                              justifyContent: "center",
                              color: "var(--brand-primary)",
                              flexShrink: 0,
                            }}
                          >
                            <CodeIcon size={18} />
                          </div>
                          <div>
                            <div style={{ fontWeight: 600, color: "var(--text-primary)", fontSize: "0.9375rem" }}>
                              {app.name}
                            </div>
                            {app.description && (
                              <div
                                style={{
                                  fontSize: "0.8125rem",
                                  color: "var(--text-secondary)",
                                  marginTop: "0.2rem",
                                  lineHeight: 1.4,
                                }}
                              >
                                {app.description}
                              </div>
                            )}
                          </div>
                        </div>
                      </td>
                      <td style={{ padding: "1rem 1.25rem", verticalAlign: "middle" }}>
                        {getStatusBadge(app.status)}
                      </td>
                      <td style={{ padding: "1rem 1.25rem", verticalAlign: "middle" }}>
                        <span
                          style={{
                            display: "inline-flex",
                            alignItems: "center",
                            gap: "0.35rem",
                            fontSize: "0.8125rem",
                            padding: "0.2rem 0.65rem",
                            borderRadius: "999px",
                            background: "var(--surface-soft-blue)",
                            border: "1px solid rgba(56, 103, 245, 0.2)",
                            color: "var(--brand-primary)",
                            fontWeight: 600,
                          }}
                        >
                          <KeyIcon size={13} />
                          {app.active_keys_count} active
                        </span>
                      </td>
                      <td
                        style={{
                          padding: "1rem 1.25rem",
                          verticalAlign: "middle",
                          fontSize: "0.8125rem",
                          color: "var(--text-secondary)",
                        }}
                      >
                        <div style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
                          <CalendarIcon size={13} style={{ opacity: 0.6 }} />
                          {new Date(app.created_at).toLocaleDateString()}
                        </div>
                      </td>
                      <td style={{ padding: "1rem 1.25rem", verticalAlign: "middle", textAlign: "right" }}>
                        <div
                          style={{
                            display: "inline-flex",
                            gap: "0.5rem",
                            alignItems: "center",
                            justifyContent: "flex-end",
                          }}
                        >
                          <button
                            type="button"
                            className={selectedApp?.id === app.id ? "btn-primary" : "btn-secondary"}
                            onClick={() => void loadAppData(app)}
                            style={{ padding: "0.35rem 0.75rem", fontSize: "0.8125rem", fontWeight: 600 }}
                          >
                            Manage App
                          </button>
                          {app.status === "active" && (
                            <button
                              type="button"
                              onClick={() => void handleSuspendApp(app)}
                              style={{
                                padding: "0.35rem 0.65rem",
                                fontSize: "0.8125rem",
                                fontWeight: 500,
                                borderRadius: "6px",
                                border: "1px solid var(--border-subtle)",
                                background: "var(--glass-surface-sunken)",
                                color: "var(--status-warning)",
                                cursor: "pointer",
                                transition: "all 0.15s ease",
                              }}
                            >
                              Suspend
                            </button>
                          )}
                          {app.status === "suspended" && (
                            <button
                              type="button"
                              onClick={() => void handleReactivateApp(app)}
                              style={{
                                padding: "0.35rem 0.65rem",
                                fontSize: "0.8125rem",
                                fontWeight: 500,
                                borderRadius: "6px",
                                border: "1px solid rgba(16, 185, 129, 0.3)",
                                background: "rgba(16, 185, 129, 0.1)",
                                color: "var(--status-success)",
                                cursor: "pointer",
                                transition: "all 0.15s ease",
                              }}
                            >
                              Reactivate
                            </button>
                          )}
                          {app.status !== "revoked" && (
                            <button
                              type="button"
                              onClick={() => void handleRevokeApp(app)}
                              style={{
                                padding: "0.35rem 0.65rem",
                                fontSize: "0.8125rem",
                                fontWeight: 500,
                                borderRadius: "6px",
                                border: "1px solid rgba(239, 68, 68, 0.3)",
                                background: "rgba(239, 68, 68, 0.08)",
                                color: "var(--status-danger)",
                                cursor: "pointer",
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

        {/* Selected App Resources Section */}
        {selectedApp && (
          <div className="table-card-container" style={{ marginTop: "2rem" }}>
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
                <div style={{ display: "flex", alignItems: "center", gap: "0.6rem" }}>
                  <div
                    style={{
                      width: 32,
                      height: 32,
                      borderRadius: 8,
                      background: "var(--surface-soft-blue)",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      color: "var(--brand-primary)",
                    }}
                  >
                    <CodeIcon size={16} />
                  </div>
                  <h2 style={{ fontSize: "1.25rem", fontWeight: 700, margin: 0, color: "var(--text-primary)" }}>
                    {selectedApp.name}
                  </h2>
                  {getStatusBadge(selectedApp.status)}
                </div>
                <p style={{ color: "var(--text-secondary)", fontSize: "0.8125rem", margin: "0.25rem 0 0" }}>
                  Manage scoped API keys and outbound webhook subscriptions for this application.
                </p>
              </div>

              <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                {selectedApp.status === "active" && appTab === "keys" && (
                  <button
                    type="button"
                    className="btn-primary"
                    onClick={() => setShowCreateKeyModal(true)}
                    style={{
                      display: "inline-flex",
                      alignItems: "center",
                      gap: "0.4rem",
                      padding: "0.45rem 0.85rem",
                      fontSize: "0.8125rem",
                    }}
                  >
                    <PlusIcon size={14} />
                    Generate New Key
                  </button>
                )}
                {selectedApp.status === "active" && appTab === "webhooks" && (
                  <button
                    type="button"
                    className="btn-primary"
                    onClick={() => setShowCreateWebhookModal(true)}
                    style={{
                      display: "inline-flex",
                      alignItems: "center",
                      gap: "0.4rem",
                      padding: "0.45rem 0.85rem",
                      fontSize: "0.8125rem",
                    }}
                  >
                    <PlusIcon size={14} />
                    Add Webhook
                  </button>
                )}
                <button
                  type="button"
                  onClick={() => setSelectedApp(null)}
                  style={{
                    padding: "0.45rem 0.75rem",
                    background: "var(--glass-surface-sunken)",
                    border: "1px solid var(--border-subtle)",
                    borderRadius: "6px",
                    color: "var(--text-secondary)",
                    fontSize: "0.8125rem",
                    cursor: "pointer",
                  }}
                >
                  Close Inspector
                </button>
              </div>
            </div>

            {/* Segmented Tab Controls */}
            <div
              style={{
                display: "flex",
                gap: "0.5rem",
                padding: "0.75rem 1.5rem",
                background: "var(--glass-surface-sunken)",
                borderBottom: "1px solid var(--border-subtle)",
              }}
            >
              <button
                type="button"
                onClick={() => setAppTab("keys")}
                style={{
                  padding: "0.4rem 0.85rem",
                  borderRadius: "6px",
                  fontSize: "0.8125rem",
                  fontWeight: appTab === "keys" ? 600 : 500,
                  border: "none",
                  background: appTab === "keys" ? "var(--glass-surface-elevated)" : "transparent",
                  color: appTab === "keys" ? "var(--brand-primary)" : "var(--text-secondary)",
                  boxShadow: appTab === "keys" ? "var(--shadow-sm)" : "none",
                  cursor: "pointer",
                  display: "inline-flex",
                  alignItems: "center",
                  gap: "0.4rem",
                  transition: "all 0.15s ease",
                }}
              >
                <KeyIcon size={14} />
                API Keys ({keys.length})
              </button>
              <button
                type="button"
                onClick={() => setAppTab("webhooks")}
                style={{
                  padding: "0.4rem 0.85rem",
                  borderRadius: "6px",
                  fontSize: "0.8125rem",
                  fontWeight: appTab === "webhooks" ? 600 : 500,
                  border: "none",
                  background: appTab === "webhooks" ? "var(--glass-surface-elevated)" : "transparent",
                  color: appTab === "webhooks" ? "var(--brand-primary)" : "var(--text-secondary)",
                  boxShadow: appTab === "webhooks" ? "var(--shadow-sm)" : "none",
                  cursor: "pointer",
                  display: "inline-flex",
                  alignItems: "center",
                  gap: "0.4rem",
                  transition: "all 0.15s ease",
                }}
              >
                <GlobeIcon size={14} />
                Webhooks ({webhooks.length})
              </button>
            </div>

            {/* Keys Tab Content */}
            {appTab === "keys" && (
              <>
                {isLoadingKeys ? (
                  <div style={{ display: "flex", justifyContent: "center", padding: "3rem" }}>
                    <LoadingSpinner label="Loading keys..." />
                  </div>
                ) : keys.length === 0 ? (
                  <div style={{ textAlign: "center", padding: "3rem 1.5rem", color: "var(--text-secondary)" }}>
                    <KeyIcon size={32} style={{ opacity: 0.4, marginBottom: "0.5rem" }} />
                    <p style={{ margin: 0, fontWeight: 600, color: "var(--text-primary)" }}>
                      No API keys generated for this application yet.
                    </p>
                    <p style={{ margin: "0.25rem 0 0", fontSize: "0.8125rem" }}>
                      Generate a scoped API key to enable secure programmatic integrations.
                    </p>
                  </div>
                ) : (
                  <div className="table-card-scroll">
                    <table style={{ width: "100%", borderCollapse: "collapse", textAlign: "left" }}>
                      <thead>
                        <tr style={{ borderBottom: "1px solid var(--border-subtle)", background: "var(--glass-surface-sunken)" }}>
                          <th
                            scope="col"
                            style={{
                              padding: "0.75rem 1rem",
                              fontSize: "0.75rem",
                              fontWeight: 700,
                              textTransform: "uppercase",
                              letterSpacing: "0.05em",
                              color: "var(--text-secondary)",
                            }}
                          >
                            KEY NAME
                          </th>
                          <th
                            scope="col"
                            style={{
                              padding: "0.75rem 1rem",
                              fontSize: "0.75rem",
                              fontWeight: 700,
                              textTransform: "uppercase",
                              letterSpacing: "0.05em",
                              color: "var(--text-secondary)",
                            }}
                          >
                            KEY PREFIX
                          </th>
                          <th
                            scope="col"
                            style={{
                              padding: "0.75rem 1rem",
                              fontSize: "0.75rem",
                              fontWeight: 700,
                              textTransform: "uppercase",
                              letterSpacing: "0.05em",
                              color: "var(--text-secondary)",
                            }}
                          >
                            GRANTED SCOPES
                          </th>
                          <th
                            scope="col"
                            style={{
                              padding: "0.75rem 1rem",
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
                              padding: "0.75rem 1rem",
                              fontSize: "0.75rem",
                              fontWeight: 700,
                              textTransform: "uppercase",
                              letterSpacing: "0.05em",
                              color: "var(--text-secondary)",
                            }}
                          >
                            LAST USED
                          </th>
                          <th
                            scope="col"
                            style={{
                              padding: "0.75rem 1rem",
                              fontSize: "0.75rem",
                              fontWeight: 700,
                              textTransform: "uppercase",
                              letterSpacing: "0.05em",
                              color: "var(--text-secondary)",
                            }}
                          >
                            CREATED
                          </th>
                          <th
                            scope="col"
                            style={{
                              padding: "0.75rem 1rem",
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
                        {keys.map((k) => (
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
                            <td
                              style={{
                                padding: "0.875rem 1rem",
                                fontWeight: 600,
                                color: "var(--text-primary)",
                                fontSize: "0.875rem",
                              }}
                            >
                              {k.name}
                            </td>
                            <td style={{ padding: "0.875rem 1rem" }}>
                              <code
                                style={{
                                  fontSize: "0.8125rem",
                                  background: "var(--glass-surface-sunken)",
                                  border: "1px solid var(--border-subtle)",
                                  padding: "0.2rem 0.45rem",
                                  borderRadius: "4px",
                                  color: "var(--text-primary)",
                                  fontFamily: "var(--font-code)",
                                }}
                              >
                                {k.key_prefix}...
                              </code>
                            </td>
                            <td style={{ padding: "0.875rem 1rem" }}>
                              <div style={{ display: "flex", flexWrap: "wrap", gap: "0.25rem" }}>
                                {k.scopes.map((s) => (
                                  <span
                                    key={s}
                                    className="badge badge-neutral"
                                    style={{ fontSize: "0.72rem", fontFamily: "var(--font-code)" }}
                                  >
                                    {s}
                                  </span>
                                ))}
                              </div>
                            </td>
                            <td style={{ padding: "0.875rem 1rem" }}>{getStatusBadge(k.status)}</td>
                            <td
                              style={{
                                padding: "0.875rem 1rem",
                                fontSize: "0.8125rem",
                                color: "var(--text-secondary)",
                              }}
                            >
                              {k.last_used_at ? new Date(k.last_used_at).toLocaleString() : "Never"}
                            </td>
                            <td
                              style={{
                                padding: "0.875rem 1rem",
                                fontSize: "0.8125rem",
                                color: "var(--text-secondary)",
                              }}
                            >
                              {new Date(k.created_at).toLocaleDateString()}
                            </td>
                            <td style={{ padding: "0.875rem 1rem", textAlign: "right" }}>
                              {k.status === "active" && selectedApp.status === "active" && (
                                <div style={{ display: "inline-flex", gap: "0.4rem" }}>
                                  <button
                                    type="button"
                                    className="btn-secondary"
                                    onClick={() => void handleRotateKey(k)}
                                    style={{ padding: "0.25rem 0.55rem", fontSize: "0.75rem", fontWeight: 600 }}
                                  >
                                    Rotate
                                  </button>
                                  <button
                                    type="button"
                                    onClick={() => void handleRevokeKey(k)}
                                    style={{
                                      padding: "0.25rem 0.55rem",
                                      fontSize: "0.75rem",
                                      fontWeight: 500,
                                      borderRadius: "6px",
                                      border: "1px solid rgba(239, 68, 68, 0.3)",
                                      background: "rgba(239, 68, 68, 0.08)",
                                      color: "var(--status-danger)",
                                      cursor: "pointer",
                                    }}
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
                  <div style={{ display: "flex", justifyContent: "center", padding: "3rem" }}>
                    <LoadingSpinner label="Loading webhooks..." />
                  </div>
                ) : webhooks.length === 0 ? (
                  <div style={{ textAlign: "center", padding: "3rem 1.5rem", color: "var(--text-secondary)" }}>
                    <GlobeIcon size={32} style={{ opacity: 0.4, marginBottom: "0.5rem" }} />
                    <p style={{ margin: 0, fontWeight: 600, color: "var(--text-primary)" }}>
                      No webhook subscriptions configured for this application yet.
                    </p>
                    <p style={{ margin: "0.25rem 0 0", fontSize: "0.8125rem" }}>
                      Configure an HTTP payload endpoint to receive real-time signed webhook events.
                    </p>
                  </div>
                ) : (
                  <div className="table-card-scroll">
                    <table style={{ width: "100%", borderCollapse: "collapse", textAlign: "left" }}>
                      <thead>
                        <tr style={{ borderBottom: "1px solid var(--border-subtle)", background: "var(--glass-surface-sunken)" }}>
                          <th
                            scope="col"
                            style={{
                              padding: "0.75rem 1rem",
                              fontSize: "0.75rem",
                              fontWeight: 700,
                              textTransform: "uppercase",
                              letterSpacing: "0.05em",
                              color: "var(--text-secondary)",
                            }}
                          >
                            TARGET URL
                          </th>
                          <th
                            scope="col"
                            style={{
                              padding: "0.75rem 1rem",
                              fontSize: "0.75rem",
                              fontWeight: 700,
                              textTransform: "uppercase",
                              letterSpacing: "0.05em",
                              color: "var(--text-secondary)",
                            }}
                          >
                            EVENT TOPICS
                          </th>
                          <th
                            scope="col"
                            style={{
                              padding: "0.75rem 1rem",
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
                              padding: "0.75rem 1rem",
                              fontSize: "0.75rem",
                              fontWeight: 700,
                              textTransform: "uppercase",
                              letterSpacing: "0.05em",
                              color: "var(--text-secondary)",
                            }}
                          >
                            CREATED
                          </th>
                          <th
                            scope="col"
                            style={{
                              padding: "0.75rem 1rem",
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
                        {webhooks.map((w) => (
                          <tr
                            key={w.id}
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
                            <td style={{ padding: "0.875rem 1rem", fontWeight: 500 }}>
                              <code
                                style={{
                                  fontSize: "0.8125rem",
                                  background: "var(--glass-surface-sunken)",
                                  border: "1px solid var(--border-subtle)",
                                  padding: "0.2rem 0.45rem",
                                  borderRadius: "4px",
                                  color: "var(--text-primary)",
                                  fontFamily: "var(--font-code)",
                                }}
                              >
                                {w.target_url}
                              </code>
                            </td>
                            <td style={{ padding: "0.875rem 1rem" }}>
                              <div style={{ display: "flex", flexWrap: "wrap", gap: "0.25rem" }}>
                                {w.event_topics.map((t) => (
                                  <span
                                    key={t}
                                    className="badge badge-neutral"
                                    style={{ fontSize: "0.72rem", fontFamily: "var(--font-code)" }}
                                  >
                                    {t}
                                  </span>
                                ))}
                              </div>
                            </td>
                            <td style={{ padding: "0.875rem 1rem" }}>{getStatusBadge(w.status)}</td>
                            <td
                              style={{
                                padding: "0.875rem 1rem",
                                fontSize: "0.8125rem",
                                color: "var(--text-secondary)",
                              }}
                            >
                              {new Date(w.created_at).toLocaleDateString()}
                            </td>
                            <td style={{ padding: "0.875rem 1rem", textAlign: "right" }}>
                              <div
                                style={{
                                  display: "inline-flex",
                                  gap: "0.4rem",
                                  alignItems: "center",
                                  justifyContent: "flex-end",
                                }}
                              >
                                <button
                                  type="button"
                                  className="btn-secondary"
                                  onClick={() => void handleViewDeliveries(w)}
                                  style={{ padding: "0.25rem 0.55rem", fontSize: "0.75rem", fontWeight: 600 }}
                                >
                                  Deliveries
                                </button>
                                {w.status === "active" && selectedApp.status === "active" && (
                                  <>
                                    <button
                                      type="button"
                                      className="btn-secondary"
                                      onClick={() => void handleRotateWebhookSecret(w)}
                                      style={{ padding: "0.25rem 0.55rem", fontSize: "0.75rem", fontWeight: 600 }}
                                    >
                                      Rotate Secret
                                    </button>
                                    <button
                                      type="button"
                                      onClick={() => void handleSuspendWebhook(w)}
                                      style={{
                                        padding: "0.25rem 0.55rem",
                                        fontSize: "0.75rem",
                                        fontWeight: 500,
                                        borderRadius: "6px",
                                        border: "1px solid var(--border-subtle)",
                                        background: "var(--glass-surface-sunken)",
                                        color: "var(--status-warning)",
                                        cursor: "pointer",
                                      }}
                                    >
                                      Suspend
                                    </button>
                                  </>
                                )}
                                {w.status === "suspended" && selectedApp.status === "active" && (
                                  <button
                                    type="button"
                                    onClick={() => void handleReactivateWebhook(w)}
                                    style={{
                                      padding: "0.25rem 0.55rem",
                                      fontSize: "0.75rem",
                                      fontWeight: 500,
                                      borderRadius: "6px",
                                      border: "1px solid rgba(16, 185, 129, 0.3)",
                                      background: "rgba(16, 185, 129, 0.1)",
                                      color: "var(--status-success)",
                                      cursor: "pointer",
                                    }}
                                  >
                                    Reactivate
                                  </button>
                                )}
                                {w.status !== "revoked" && (
                                  <button
                                    type="button"
                                    onClick={() => void handleRevokeWebhook(w)}
                                    style={{
                                      padding: "0.25rem 0.55rem",
                                      fontSize: "0.75rem",
                                      fontWeight: 500,
                                      borderRadius: "6px",
                                      border: "1px solid rgba(239, 68, 68, 0.3)",
                                      background: "rgba(239, 68, 68, 0.08)",
                                      color: "var(--status-danger)",
                                      cursor: "pointer",
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
              </>
            )}
          </div>
        )}

        {/* Modal: Register Application */}
        {showCreateAppModal && (
          <div
            className="modal-backdrop"
            style={{
              position: "fixed",
              inset: 0,
              background: "rgba(0, 0, 0, 0.65)",
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
                maxWidth: "500px",
                width: "100%",
                background: "var(--glass-surface-elevated)",
                border: "1px solid var(--border-glass)",
                borderRadius: "14px",
                boxShadow: "var(--shadow-xl)",
                padding: "1.75rem",
              }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1.25rem" }}>
                <h2 style={{ fontSize: "1.25rem", fontWeight: 700, margin: 0, color: "var(--text-primary)" }}>
                  Register Developer Application
                </h2>
                <button
                  type="button"
                  onClick={() => setShowCreateAppModal(false)}
                  style={{
                    background: "transparent",
                    border: "none",
                    color: "var(--text-secondary)",
                    cursor: "pointer",
                    padding: "0.25rem",
                  }}
                >
                  <CloseIcon size={18} />
                </button>
              </div>
              <form onSubmit={handleCreateApp}>
                <div style={{ marginBottom: "1rem" }}>
                  <label
                    style={{
                      display: "block",
                      fontSize: "0.8125rem",
                      fontWeight: 600,
                      marginBottom: "0.375rem",
                      color: "var(--text-primary)",
                    }}
                  >
                    Application Name *
                  </label>
                  <input
                    type="text"
                    required
                    value={newAppName}
                    onChange={(e) => setNewAppName(e.target.value)}
                    placeholder="e.g. ERP Integration Service"
                    className="input-text"
                    style={{
                      width: "100%",
                      boxSizing: "border-box",
                      padding: "0.625rem 0.75rem",
                      borderRadius: "6px",
                      background: "var(--input-bg)",
                      border: "1px solid var(--border-subtle)",
                      color: "var(--text-primary)",
                    }}
                  />
                </div>
                <div style={{ marginBottom: "1.5rem" }}>
                  <label
                    style={{
                      display: "block",
                      fontSize: "0.8125rem",
                      fontWeight: 600,
                      marginBottom: "0.375rem",
                      color: "var(--text-primary)",
                    }}
                  >
                    Description
                  </label>
                  <textarea
                    rows={3}
                    value={newAppDesc}
                    onChange={(e) => setNewAppDesc(e.target.value)}
                    placeholder="Purpose of this application integration..."
                    className="input-text"
                    style={{
                      width: "100%",
                      boxSizing: "border-box",
                      padding: "0.625rem 0.75rem",
                      borderRadius: "6px",
                      background: "var(--input-bg)",
                      border: "1px solid var(--border-subtle)",
                      color: "var(--text-primary)",
                      fontFamily: "inherit",
                    }}
                  />
                </div>
                <div style={{ display: "flex", justifyContent: "flex-end", gap: "0.75rem" }}>
                  <button
                    type="button"
                    className="btn-secondary"
                    onClick={() => setShowCreateAppModal(false)}
                    style={{ padding: "0.5rem 1rem", fontSize: "0.875rem" }}
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    className="btn-primary"
                    disabled={isSubmittingApp || !newAppName.trim()}
                    style={{ padding: "0.5rem 1.25rem", fontSize: "0.875rem" }}
                  >
                    {isSubmittingApp ? "Registering..." : "Register Application"}
                  </button>
                </div>
              </form>
            </div>
          </div>
        )}

        {/* Modal: Generate New Key */}
        {showCreateKeyModal && selectedApp && (
          <div
            className="modal-backdrop"
            style={{
              position: "fixed",
              inset: 0,
              background: "rgba(0, 0, 0, 0.65)",
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
                borderRadius: "14px",
                boxShadow: "var(--shadow-xl)",
                padding: "1.75rem",
              }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.5rem" }}>
                <h2 style={{ fontSize: "1.25rem", fontWeight: 700, margin: 0, color: "var(--text-primary)" }}>
                  Generate Key for {selectedApp.name}
                </h2>
                <button
                  type="button"
                  onClick={() => setShowCreateKeyModal(false)}
                  style={{
                    background: "transparent",
                    border: "none",
                    color: "var(--text-secondary)",
                    cursor: "pointer",
                    padding: "0.25rem",
                  }}
                >
                  <CloseIcon size={18} />
                </button>
              </div>
              <p style={{ color: "var(--text-secondary)", fontSize: "0.8125rem", margin: "0 0 1.25rem" }}>
                Select allowed scopes. Scopes cannot be expanded after generation.
              </p>
              <form onSubmit={handleCreateKey}>
                <div style={{ marginBottom: "1rem" }}>
                  <label
                    style={{
                      display: "block",
                      fontSize: "0.8125rem",
                      fontWeight: 600,
                      marginBottom: "0.375rem",
                      color: "var(--text-primary)",
                    }}
                  >
                    Key Label *
                  </label>
                  <input
                    type="text"
                    required
                    value={newKeyName}
                    onChange={(e) => setNewKeyName(e.target.value)}
                    placeholder="e.g. Production Catalog Sync"
                    className="input-text"
                    style={{
                      width: "100%",
                      boxSizing: "border-box",
                      padding: "0.625rem 0.75rem",
                      borderRadius: "6px",
                      background: "var(--input-bg)",
                      border: "1px solid var(--border-subtle)",
                      color: "var(--text-primary)",
                    }}
                  />
                </div>

                <div style={{ marginBottom: "1.25rem" }}>
                  <label
                    style={{
                      display: "block",
                      fontSize: "0.8125rem",
                      fontWeight: 600,
                      marginBottom: "0.5rem",
                      color: "var(--text-primary)",
                    }}
                  >
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
                          padding: "0.6rem 0.75rem",
                          borderRadius: "8px",
                          background: "var(--glass-surface-sunken)",
                          border: "1px solid var(--border-subtle)",
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
                          <div style={{ fontWeight: 600, fontSize: "0.8125rem", color: "var(--text-primary)" }}>
                            {scope.label}{" "}
                            <code style={{ fontSize: "0.75rem", color: "var(--brand-primary)" }}>({scope.id})</code>
                          </div>
                          <div style={{ fontSize: "0.75rem", color: "var(--text-secondary)", marginTop: "0.15rem" }}>
                            {scope.desc}
                          </div>
                        </div>
                      </label>
                    ))}
                  </div>
                </div>

                <div style={{ display: "flex", justifyContent: "flex-end", gap: "0.75rem" }}>
                  <button
                    type="button"
                    className="btn-secondary"
                    onClick={() => setShowCreateKeyModal(false)}
                    style={{ padding: "0.5rem 1rem", fontSize: "0.875rem" }}
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    className="btn-primary"
                    disabled={isSubmittingKey || !newKeyName.trim() || selectedScopes.length === 0}
                    style={{ padding: "0.5rem 1.25rem", fontSize: "0.875rem" }}
                  >
                    {isSubmittingKey ? "Generating..." : "Generate Key"}
                  </button>
                </div>
              </form>
            </div>
          </div>
        )}

        {/* Modal: ONE-TIME Plaintext Secret Display */}
        {oneTimeKey && (
          <div
            className="modal-backdrop"
            style={{
              position: "fixed",
              inset: 0,
              background: "rgba(0, 0, 0, 0.75)",
              backdropFilter: "blur(6px)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              zIndex: 2000,
              padding: "1rem",
            }}
          >
            <div
              style={{
                maxWidth: "560px",
                width: "100%",
                background: "var(--glass-surface-elevated)",
                border: "1px solid var(--border-glass)",
                borderRadius: "14px",
                boxShadow: "var(--shadow-xl)",
                padding: "1.75rem",
              }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", marginBottom: "1rem" }}>
                <div style={{ color: "var(--status-warning)" }}>
                  <ShieldCheckIcon size={28} />
                </div>
                <h2 style={{ fontSize: "1.25rem", fontWeight: 700, margin: 0, color: "var(--text-primary)" }}>
                  API Key Generated Successfully
                </h2>
              </div>

              <div
                style={{
                  padding: "0.875rem 1rem",
                  background: "var(--status-warning-bg)",
                  border: "1px solid var(--status-warning-border)",
                  borderRadius: "8px",
                  color: "var(--status-warning)",
                  fontSize: "0.875rem",
                  lineHeight: 1.5,
                  marginBottom: "1.25rem",
                }}
              >
                <strong>Important:</strong> This secret will <strong>never</strong> be displayed again. If you lose this key, you will need to rotate or generate a replacement.
              </div>

              <div style={{ marginBottom: "1.5rem" }}>
                <label
                  style={{
                    display: "block",
                    fontSize: "0.8125rem",
                    fontWeight: 600,
                    color: "var(--text-secondary)",
                    marginBottom: "0.375rem",
                  }}
                >
                  Full API Key ({oneTimeKey.name})
                </label>
                <div style={{ display: "flex", gap: "0.5rem" }}>
                  <input
                    type="text"
                    readOnly
                    value={oneTimeKey.key}
                    style={{
                      fontFamily: "var(--font-code)",
                      fontSize: "0.875rem",
                      width: "100%",
                      padding: "0.625rem 0.75rem",
                      background: "var(--glass-surface-sunken)",
                      border: "1px solid var(--border-glass)",
                      borderRadius: "6px",
                      color: "var(--text-primary)",
                      boxSizing: "border-box",
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
                    style={{
                      display: "inline-flex",
                      alignItems: "center",
                      gap: "0.35rem",
                      whiteSpace: "nowrap",
                      padding: "0.5rem 0.85rem",
                    }}
                  >
                    <CopyIcon size={14} />
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
                  style={{ padding: "0.5rem 1.25rem" }}
                >
                  I Have Saved My Key
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Modal: Create Webhook Subscription */}
        {showCreateWebhookModal && selectedApp && (
          <div
            className="modal-backdrop"
            style={{
              position: "fixed",
              inset: 0,
              background: "rgba(0, 0, 0, 0.65)",
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
                borderRadius: "14px",
                boxShadow: "var(--shadow-xl)",
                padding: "1.75rem",
              }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.5rem" }}>
                <h2 style={{ fontSize: "1.25rem", fontWeight: 700, margin: 0, color: "var(--text-primary)" }}>
                  Add Webhook Subscription
                </h2>
                <button
                  type="button"
                  onClick={() => setShowCreateWebhookModal(false)}
                  style={{
                    background: "transparent",
                    border: "none",
                    color: "var(--text-secondary)",
                    cursor: "pointer",
                    padding: "0.25rem",
                  }}
                >
                  <CloseIcon size={18} />
                </button>
              </div>
              <p style={{ color: "var(--text-secondary)", fontSize: "0.8125rem", margin: "0 0 1.25rem" }}>
                Configure HTTP endpoint to receive real-time signed event notifications.
              </p>
              <form onSubmit={handleCreateWebhook}>
                <div style={{ marginBottom: "1rem" }}>
                  <label
                    style={{
                      display: "block",
                      fontSize: "0.8125rem",
                      fontWeight: 600,
                      marginBottom: "0.375rem",
                      color: "var(--text-primary)",
                    }}
                  >
                    Payload URL (HTTP/HTTPS) *
                  </label>
                  <input
                    type="url"
                    required
                    value={newWebhookUrl}
                    onChange={(e) => setNewWebhookUrl(e.target.value)}
                    placeholder="https://api.yourdomain.com/webhooks/envisage"
                    className="input-text"
                    style={{
                      width: "100%",
                      boxSizing: "border-box",
                      padding: "0.625rem 0.75rem",
                      borderRadius: "6px",
                      background: "var(--input-bg)",
                      border: "1px solid var(--border-subtle)",
                      color: "var(--text-primary)",
                    }}
                  />
                </div>

                <div style={{ marginBottom: "1.25rem" }}>
                  <label
                    style={{
                      display: "block",
                      fontSize: "0.8125rem",
                      fontWeight: 600,
                      marginBottom: "0.5rem",
                      color: "var(--text-primary)",
                    }}
                  >
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
                          padding: "0.6rem 0.75rem",
                          borderRadius: "8px",
                          background: "var(--glass-surface-sunken)",
                          border: "1px solid var(--border-subtle)",
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
                          style={{ marginTop: "0.2rem" }}
                        />
                        <div>
                          <div style={{ fontSize: "0.8125rem", fontWeight: 600, color: "var(--text-primary)" }}>
                            {topic.label}
                          </div>
                          <div style={{ fontSize: "0.75rem", color: "var(--text-secondary)", marginTop: "0.15rem" }}>
                            {topic.desc}
                          </div>
                        </div>
                      </label>
                    ))}
                  </div>
                </div>

                <div style={{ display: "flex", justifyContent: "flex-end", gap: "0.75rem" }}>
                  <button
                    type="button"
                    className="btn-secondary"
                    onClick={() => setShowCreateWebhookModal(false)}
                    style={{ padding: "0.5rem 1rem", fontSize: "0.875rem" }}
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    className="btn-primary"
                    disabled={isSubmittingWebhook || !newWebhookUrl.trim() || newWebhookTopics.length === 0}
                    style={{ padding: "0.5rem 1.25rem", fontSize: "0.875rem" }}
                  >
                    {isSubmittingWebhook ? "Creating..." : "Create Subscription"}
                  </button>
                </div>
              </form>
            </div>
          </div>
        )}

        {/* Modal: One-time Webhook Secret Display */}
        {oneTimeSecret && (
          <div
            className="modal-backdrop"
            style={{
              position: "fixed",
              inset: 0,
              background: "rgba(0, 0, 0, 0.75)",
              backdropFilter: "blur(6px)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              zIndex: 2000,
              padding: "1rem",
            }}
          >
            <div
              style={{
                maxWidth: "560px",
                width: "100%",
                background: "var(--glass-surface-elevated)",
                border: "1px solid var(--border-glass)",
                borderRadius: "14px",
                boxShadow: "var(--shadow-xl)",
                padding: "1.75rem",
              }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.75rem" }}>
                <ShieldCheckIcon size={24} style={{ color: "var(--status-warning)" }} />
                <h2 style={{ fontSize: "1.25rem", fontWeight: 700, margin: 0, color: "var(--text-primary)" }}>
                  Save Your Webhook Signing Secret
                </h2>
              </div>
              <p
                style={{
                  color: "var(--status-warning)",
                  fontSize: "0.875rem",
                  marginBottom: "1rem",
                  lineHeight: 1.5,
                  padding: "0.75rem 1rem",
                  background: "var(--status-warning-bg)",
                  border: "1px solid var(--status-warning-border)",
                  borderRadius: "8px",
                }}
              >
                This signing secret will <strong>never be shown again</strong>. Store it safely to verify the HMAC-SHA256 signature in incoming requests.
              </p>

              <div style={{ marginBottom: "1.25rem" }}>
                <label
                  style={{
                    display: "block",
                    fontSize: "0.8125rem",
                    fontWeight: 600,
                    color: "var(--text-secondary)",
                    marginBottom: "0.25rem",
                  }}
                >
                  Target Endpoint
                </label>
                <div
                  style={{
                    fontSize: "0.875rem",
                    fontFamily: "var(--font-code)",
                    color: "var(--text-primary)",
                    marginBottom: "0.75rem",
                    wordBreak: "break-all",
                  }}
                >
                  {oneTimeSecret.url}
                </div>

                <label
                  style={{
                    display: "block",
                    fontSize: "0.8125rem",
                    fontWeight: 600,
                    color: "var(--text-secondary)",
                    marginBottom: "0.25rem",
                  }}
                >
                  Signing Secret
                </label>
                <div style={{ display: "flex", gap: "0.5rem" }}>
                  <input
                    type="text"
                    readOnly
                    value={oneTimeSecret.secret}
                    style={{
                      flex: 1,
                      fontFamily: "var(--font-code)",
                      fontSize: "0.8125rem",
                      padding: "0.5rem 0.75rem",
                      background: "var(--glass-surface-sunken)",
                      border: "1px solid var(--border-glass)",
                      borderRadius: "6px",
                      color: "var(--text-primary)",
                      boxSizing: "border-box",
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
                    style={{
                      display: "inline-flex",
                      alignItems: "center",
                      gap: "0.35rem",
                      whiteSpace: "nowrap",
                      padding: "0.5rem 0.85rem",
                    }}
                  >
                    <CopyIcon size={14} />
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
                  style={{ padding: "0.5rem 1.25rem" }}
                >
                  I Have Saved My Secret
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Modal: Deliveries History & Replay */}
        {deliveriesWebhook && (
          <div
            className="modal-backdrop"
            style={{
              position: "fixed",
              inset: 0,
              background: "rgba(0, 0, 0, 0.65)",
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
                maxWidth: "780px",
                width: "100%",
                maxHeight: "85vh",
                overflowY: "auto",
                background: "var(--glass-surface-elevated)",
                border: "1px solid var(--border-glass)",
                borderRadius: "14px",
                boxShadow: "var(--shadow-xl)",
                padding: "1.75rem",
              }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1.25rem" }}>
                <div>
                  <h2 style={{ fontSize: "1.25rem", fontWeight: 700, margin: 0, color: "var(--text-primary)" }}>
                    Webhook Delivery History
                  </h2>
                  <p
                    style={{
                      color: "var(--text-secondary)",
                      fontSize: "0.8125rem",
                      margin: "0.25rem 0 0",
                      wordBreak: "break-all",
                    }}
                  >
                    {deliveriesWebhook.target_url}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => setDeliveriesWebhook(null)}
                  style={{
                    background: "transparent",
                    border: "none",
                    color: "var(--text-secondary)",
                    cursor: "pointer",
                    padding: "0.25rem",
                  }}
                >
                  <CloseIcon size={20} />
                </button>
              </div>

              {isLoadingDeliveries ? (
                <div style={{ display: "flex", justifyContent: "center", padding: "3rem" }}>
                  <LoadingSpinner label="Loading delivery traces..." />
                </div>
              ) : deliveries.length === 0 ? (
                <div style={{ textAlign: "center", padding: "3rem 1.5rem", color: "var(--text-secondary)" }}>
                  <p style={{ margin: 0, fontWeight: 600, color: "var(--text-primary)" }}>
                    No delivery attempts recorded yet
                  </p>
                  <p style={{ margin: "0.25rem 0 0", fontSize: "0.8125rem" }}>
                    Events dispatched to this endpoint will be logged here for observability and debugging.
                  </p>
                </div>
              ) : (
                <div className="table-card-scroll">
                  <table style={{ width: "100%", borderCollapse: "collapse", textAlign: "left", fontSize: "0.8125rem" }}>
                    <thead>
                      <tr style={{ borderBottom: "1px solid var(--border-subtle)", background: "var(--glass-surface-sunken)" }}>
                        <th scope="col" style={{ padding: "0.75rem 1rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.05em", color: "var(--text-secondary)" }}>EVENT TYPE</th>
                        <th scope="col" style={{ padding: "0.75rem 1rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.05em", color: "var(--text-secondary)" }}>STATUS</th>
                        <th scope="col" style={{ padding: "0.75rem 1rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.05em", color: "var(--text-secondary)" }}>HTTP CODE</th>
                        <th scope="col" style={{ padding: "0.75rem 1rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.05em", color: "var(--text-secondary)" }}>ATTEMPT</th>
                        <th scope="col" style={{ padding: "0.75rem 1rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.05em", color: "var(--text-secondary)" }}>TIMESTAMP</th>
                        <th scope="col" style={{ padding: "0.75rem 1rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.05em", color: "var(--text-secondary)", textAlign: "right" }}>ACTIONS</th>
                      </tr>
                    </thead>
                    <tbody>
                      {deliveries.map((d) => (
                        <tr
                          key={d.id}
                          style={{ borderBottom: "1px solid var(--border-subtle)", transition: "background-color 0.15s ease" }}
                          onMouseEnter={(e) => {
                            e.currentTarget.style.backgroundColor = "var(--glass-surface-hover)";
                          }}
                          onMouseLeave={(e) => {
                            e.currentTarget.style.backgroundColor = "transparent";
                          }}
                        >
                          <td style={{ padding: "0.75rem 1rem", fontFamily: "var(--font-code)", color: "var(--text-primary)" }}>
                            {d.event_type}
                          </td>
                          <td style={{ padding: "0.75rem 1rem" }}>{getStatusBadge(d.status)}</td>
                          <td style={{ padding: "0.75rem 1rem" }}>
                            <span
                              style={{
                                fontFamily: "var(--font-code)",
                                fontWeight: 600,
                                color:
                                  d.status_code && d.status_code >= 200 && d.status_code < 300
                                    ? "var(--status-success)"
                                    : "var(--status-danger)",
                              }}
                            >
                              {d.status_code ?? "—"}
                            </span>
                          </td>
                          <td style={{ padding: "0.75rem 1rem", color: "var(--text-secondary)" }}>
                            {d.attempt_count} / {d.max_attempts}
                          </td>
                          <td style={{ padding: "0.75rem 1rem", color: "var(--text-secondary)" }}>
                            {new Date(d.created_at).toLocaleTimeString()}
                          </td>
                          <td style={{ padding: "0.75rem 1rem", textAlign: "right" }}>
                            {d.status !== "delivered" && (
                              <button
                                type="button"
                                className="btn-secondary"
                                onClick={() => void handleReplayDelivery(d.id)}
                                style={{ padding: "0.25rem 0.55rem", fontSize: "0.75rem", fontWeight: 600 }}
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
            </div>
          </div>
        )}
      </div>
    </AppShell>
  );
};
