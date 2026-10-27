import React, { FC, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import {
  NotificationDelivery,
  NotificationTemplate,
  TemplatePreviewResponse,
  notificationsApi,
} from "../../api/notifications.ts";
import { AppShell } from "../../components/AppShell.tsx";
import {
  AlertCircleIcon,
  CheckCircleIcon,
  CloseIcon,
  EyeIcon,
  RefreshIcon,
  MailIcon,
} from "../../components/Icons.tsx";
import { LoadingSpinner } from "../../components/LoadingSpinner.tsx";

// Helper to render subject line with dynamic variable chips instead of raw braces
function formatSubjectWithChips(subjectTemplate: string): React.ReactNode {
  const parts = subjectTemplate.split(/(\{\{\s*[\w.]+\s*\}\})/g);
  return (
    <span className="notif-subject-preview">
      {parts.map((part, idx) => {
        const match = part.match(/^\{\{\s*([\w.]+)\s*\}\}$/);
        if (match) {
          return (
            <span
              key={idx}
              className="notif-variable-chip"
              title={`Dynamic variable: ${match[1]}`}
            >
              {match[1]}
            </span>
          );
        }
        return <span key={idx}>{part}</span>;
      })}
    </span>
  );
}

export const OwnerNotificationsPage: FC = () => {
  const [activeTab, setActiveTab] = useState<"templates" | "deliveries">("templates");
  const [templates, setTemplates] = useState<NotificationTemplate[]>([]);
  const [deliveries, setDeliveries] = useState<NotificationDelivery[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [refreshing, setRefreshing] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [successToast, setSuccessToast] = useState<string | null>(null);

  // Filters for Templates tab
  const [templateSearch, setTemplateSearch] = useState<string>("");
  const [templateChannelFilter, setTemplateChannelFilter] = useState<string>("");
  const [templateStatusFilter, setTemplateStatusFilter] = useState<string>("");

  // Filters for Delivery Queue tab
  const [deliverySearch, setDeliverySearch] = useState<string>("");
  const [deliveryStatusFilter, setDeliveryStatusFilter] = useState<string>("");
  const [deliveryChannelFilter, setDeliveryChannelFilter] = useState<string>("");

  // Modals state
  // 1. Preview Modal
  const [previewTemplate, setPreviewTemplate] = useState<NotificationTemplate | null>(null);
  const [previewResult, setPreviewResult] = useState<TemplatePreviewResponse | null>(null);
  const [previewContextJson, setPreviewContextJson] = useState<string>("");
  const [previewLoading, setPreviewLoading] = useState<boolean>(false);
  const [previewError, setPreviewError] = useState<string | null>(null);

  // 2. New Version Modal
  const [versioningTemplate, setVersioningTemplate] = useState<NotificationTemplate | null>(null);
  const [newSubject, setNewSubject] = useState<string>("");
  const [newBodyRef, setNewBodyRef] = useState<string>("");
  const [newIsTransactional, setNewIsTransactional] = useState<boolean>(true);
  const [versionSubmitting, setVersionSubmitting] = useState<boolean>(false);
  const [versionError, setVersionError] = useState<string | null>(null);

  // 3. Retire Confirmation Modal
  const [retiringTemplate, setRetiringTemplate] = useState<NotificationTemplate | null>(null);
  const [retireSubmitting, setRetireSubmitting] = useState<boolean>(false);
  const [retireError, setRetireError] = useState<string | null>(null);

  // 4. Retry action tracking
  const [retryingDeliveryId, setRetryingDeliveryId] = useState<string | null>(null);

  // 5. Diagnostics Modal
  const [viewingDelivery, setViewingDelivery] = useState<NotificationDelivery | null>(null);

  // Toast auto-clear timer
  const toastTimeoutRef = useRef<number | null>(null);
  const showToast = useCallback((message: string) => {
    setSuccessToast(message);
    if (toastTimeoutRef.current) clearTimeout(toastTimeoutRef.current);
    toastTimeoutRef.current = window.setTimeout(() => {
      setSuccessToast(null);
    }, 4000);
  }, []);

  useEffect(() => {
    return () => {
      if (toastTimeoutRef.current) clearTimeout(toastTimeoutRef.current);
    };
  }, []);

  // Fetch Templates
  const loadTemplates = useCallback(async () => {
    try {
      const res = await notificationsApi.listTemplates();
      setTemplates(res.results || []);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load notification templates.");
    }
  }, []);

  // Fetch Deliveries
  const loadDeliveries = useCallback(async () => {
    try {
      const params: Record<string, string> = {};
      if (deliveryStatusFilter) params.status = deliveryStatusFilter;
      if (deliveryChannelFilter) params.channel = deliveryChannelFilter;
      if (deliverySearch.trim()) params.search = deliverySearch.trim();
      const res = await notificationsApi.listDeliveries(params);
      setDeliveries(res.results || []);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load notification deliveries.");
    }
  }, [deliveryStatusFilter, deliveryChannelFilter, deliverySearch]);

  // Initial load
  const loadAllData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      await Promise.all([loadTemplates(), loadDeliveries()]);
    } finally {
      setLoading(false);
    }
  }, [loadTemplates, loadDeliveries]);

  useEffect(() => {
    loadAllData();
  }, [loadAllData]);

  // Manual Refresh Handler
  const handleRefresh = async () => {
    setRefreshing(true);
    setError(null);
    try {
      await Promise.all([loadTemplates(), loadDeliveries()]);
      showToast("Notification and delivery records refreshed successfully.");
    } finally {
      setRefreshing(false);
    }
  };

  // KPI Metrics (Calculated exclusively from actual API responses)
  const overviewMetrics = useMemo(() => {
    const totalTemplates = templates.length;
    const activeTemplates = templates.filter((t) => t.status === "active").length;
    const queuedDeliveries = deliveries.filter(
      (d) => d.status === "queued" || d.status === "retrying"
    ).length;
    const failedDeliveries = deliveries.filter((d) => d.status === "failed").length;
    return {
      totalTemplates,
      activeTemplates,
      queuedDeliveries,
      failedDeliveries,
    };
  }, [templates, deliveries]);

  // Filtered Templates
  const filteredTemplates = useMemo(() => {
    return templates.filter((t) => {
      if (templateChannelFilter && t.channel !== templateChannelFilter) return false;
      if (templateStatusFilter && t.status !== templateStatusFilter) return false;
      if (templateSearch.trim()) {
        const q = templateSearch.toLowerCase();
        const matchesCode = t.code.toLowerCase().includes(q);
        const matchesName = t.name.toLowerCase().includes(q);
        const matchesSubject = t.subject_template.toLowerCase().includes(q);
        if (!matchesCode && !matchesName && !matchesSubject) return false;
      }
      return true;
    });
  }, [templates, templateChannelFilter, templateStatusFilter, templateSearch]);

  // Action: Open Preview Modal
  const handleOpenPreview = async (template: NotificationTemplate) => {
    setPreviewTemplate(template);
    setPreviewResult(null);
    setPreviewError(null);
    setPreviewLoading(true);

    try {
      const res = await notificationsApi.previewTemplate(template.id, {});
      setPreviewResult(res);
      setPreviewContextJson(JSON.stringify(res.context || {}, null, 2));
    } catch (err) {
      setPreviewError(err instanceof Error ? err.message : "Failed to load template preview.");
    } finally {
      setPreviewLoading(false);
    }
  };

  // Action: Re-render Preview with custom context JSON
  const handleExecutePreview = async () => {
    if (!previewTemplate) return;
    setPreviewLoading(true);
    setPreviewError(null);

    let parsedContext: Record<string, unknown> = {};
    if (previewContextJson.trim()) {
      try {
        parsedContext = JSON.parse(previewContextJson);
      } catch {
        setPreviewError("Context must be a valid JSON object.");
        setPreviewLoading(false);
        return;
      }
    }

    try {
      const res = await notificationsApi.previewTemplate(previewTemplate.id, parsedContext);
      setPreviewResult(res);
    } catch (err) {
      setPreviewError(err instanceof Error ? err.message : "Failed to re-render preview.");
    } finally {
      setPreviewLoading(false);
    }
  };

  // Action: Open New Version Modal
  const handleOpenNewVersion = (template: NotificationTemplate) => {
    setVersioningTemplate(template);
    setNewSubject(template.subject_template);
    setNewBodyRef(template.body_ref);
    setNewIsTransactional(template.is_transactional);
    setVersionError(null);
  };

  // Action: Submit New Version
  const handleCreateNewVersion = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!versioningTemplate) return;

    if (!newSubject.trim()) {
      setVersionError("Subject line template is required.");
      return;
    }
    if (!newBodyRef.trim()) {
      setVersionError("Body reference or template identifier is required.");
      return;
    }

    setVersionSubmitting(true);
    setVersionError(null);

    try {
      const created = await notificationsApi.createNewVersion(versioningTemplate.id, {
        subject_template: newSubject.trim(),
        body_ref: newBodyRef.trim(),
        is_transactional: newIsTransactional,
      });
      setVersioningTemplate(null);
      await loadTemplates();
      showToast(
        `Version v${created.version} published successfully for '${created.name}'.`
      );
    } catch (err) {
      setVersionError(
        err instanceof Error ? err.message : "Failed to create new template version."
      );
    } finally {
      setVersionSubmitting(false);
    }
  };

  // Action: Open Retire Modal
  const handleOpenRetire = (template: NotificationTemplate) => {
    setRetiringTemplate(template);
    setRetireError(null);
  };

  // Action: Confirm Retire
  const handleConfirmRetire = async () => {
    if (!retiringTemplate) return;
    setRetireSubmitting(true);
    setRetireError(null);

    try {
      const retired = await notificationsApi.retireTemplate(retiringTemplate.id);
      setRetiringTemplate(null);
      await loadTemplates();
      showToast(`Template '${retired.name}' (v${retired.version}) has been retired.`);
    } catch (err) {
      setRetireError(err instanceof Error ? err.message : "Failed to retire template.");
    } finally {
      setRetireSubmitting(false);
    }
  };

  // Action: Manual Retry Delivery
  const handleRetryDelivery = async (deliveryId: string) => {
    setRetryingDeliveryId(deliveryId);
    setError(null);

    try {
      const updated = await notificationsApi.retryDelivery(deliveryId);
      setDeliveries((prev) => prev.map((d) => (d.id === updated.id ? updated : d)));
      showToast(
        `Delivery attempt completed. New status: ${updated.status.toUpperCase()}`
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Manual retry failed.");
    } finally {
      setRetryingDeliveryId(null);
    }
  };

  return (
    <AppShell>
      <div className="notif-page-container">
        {/* Breadcrumb Navigation */}
        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", fontSize: "0.8125rem", color: "var(--text-muted)", marginBottom: "1.25rem", fontWeight: 500 }}>
          <Link to="/" style={{ color: "var(--text-muted)", textDecoration: "none", transition: "color 0.15s" }}>Platform Owner</Link>
          <span>/</span>
          <span>Platform</span>
          <span>/</span>
          <span style={{ color: "var(--brand-primary)", fontWeight: 600 }}>Notifications & Communications</span>
        </div>

        {/* Page Header */}
        <div className="notif-page-header">
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
              <MailIcon size={24} />
            </div>

            <div>
              <div className="notif-title-row" style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
                <h1 className="heading-hero" style={{ fontSize: "1.75rem", margin: 0, fontWeight: 800, letterSpacing: "-0.02em" }}>Notifications & Communications</h1>
                <span className="notif-badge-pill">Control Plane</span>
              </div>
              <p className="text-body" style={{ marginTop: "0.25rem", color: "var(--text-secondary)", fontSize: "0.9375rem" }}>
                Manage versioned notification templates, inspect transactional delivery queues, and trigger operational retries.
              </p>
            </div>
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
            <button
              type="button"
              onClick={handleRefresh}
              disabled={refreshing || loading}
              className="btn btn-secondary btn-sm"
              title="Refresh all notification and delivery records"
            >
              <RefreshIcon
                size={14}
                className={refreshing ? "animate-spin" : ""}
              />
              <span>{refreshing ? "Refreshing..." : "Refresh"}</span>
            </button>
          </div>
        </div>

        {/* Global Notifications / Error Banners */}
        {error && (
          <div className="notif-alert-banner notif-alert-error">
            <AlertCircleIcon size={18} style={{ flexShrink: 0 }} />
            <div style={{ flex: 1 }}>
              <strong style={{ display: "block" }}>Operation Notice</strong>
              <span>{error}</span>
            </div>
            <button
              type="button"
              onClick={() => setError(null)}
              className="notif-alert-dismiss"
              aria-label="Dismiss error"
            >
              <CloseIcon size={16} />
            </button>
          </div>
        )}

        {successToast && (
          <div className="notif-alert-banner notif-alert-success">
            <CheckCircleIcon size={18} style={{ flexShrink: 0 }} />
            <div style={{ flex: 1 }}>
              <span>{successToast}</span>
            </div>
            <button
              type="button"
              onClick={() => setSuccessToast(null)}
              className="notif-alert-dismiss"
              aria-label="Dismiss toast"
            >
              <CloseIcon size={16} />
            </button>
          </div>
        )}

        {/* KPI Metrics Indicator Cards */}
        <div className="notif-kpi-grid">
          <div className="notif-kpi-card">
            <div className="notif-kpi-header">
              <span>Total Templates</span>
              <span className="notif-kpi-dot notif-dot-brand"></span>
            </div>
            <div className="notif-kpi-value">{loading ? "…" : overviewMetrics.totalTemplates}</div>
            <div className="notif-kpi-caption">Configured notification definitions</div>
          </div>

          <div className="notif-kpi-card">
            <div className="notif-kpi-header">
              <span>Active Templates</span>
              <span className="notif-kpi-dot notif-dot-success"></span>
            </div>
            <div className="notif-kpi-value notif-text-success">
              {loading ? "…" : overviewMetrics.activeTemplates}
            </div>
            <div className="notif-kpi-caption">Available for live system dispatch</div>
          </div>

          <div className="notif-kpi-card">
            <div className="notif-kpi-header">
              <span>Queued / In Flight</span>
              <span className="notif-kpi-dot notif-dot-warning"></span>
            </div>
            <div className="notif-kpi-value notif-text-warning">
              {loading ? "…" : overviewMetrics.queuedDeliveries}
            </div>
            <div className="notif-kpi-caption">Awaiting delivery or retry worker</div>
          </div>

          <div className="notif-kpi-card">
            <div className="notif-kpi-header">
              <span>Failed Deliveries</span>
              <span className="notif-kpi-dot notif-dot-danger"></span>
            </div>
            <div className="notif-kpi-value notif-text-danger">
              {loading ? "…" : overviewMetrics.failedDeliveries}
            </div>
            <div className="notif-kpi-caption">Require operator review or retry</div>
          </div>
        </div>

        {/* Tab Selection */}
        <div className="notif-tabs-bar">
          <button
            type="button"
            onClick={() => setActiveTab("templates")}
            className={`notif-tab-btn ${activeTab === "templates" ? "notif-tab-active" : ""}`}
          >
            <span>Notification Templates</span>
            <span className="notif-tab-count">{templates.length}</span>
          </button>
          <button
            type="button"
            onClick={() => setActiveTab("deliveries")}
            className={`notif-tab-btn ${activeTab === "deliveries" ? "notif-tab-active" : ""}`}
          >
            <span>Delivery Queue & Logs</span>
            <span className="notif-tab-count">{deliveries.length}</span>
          </button>
        </div>

        {/* Content Area */}
        {loading ? (
          <div className="notif-loading-panel">
            <LoadingSpinner label="Loading notification system data…" />
          </div>
        ) : activeTab === "templates" ? (
          /* TEMPLATES VIEW */
          <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
            {/* Toolbar */}
            <div className="notif-toolbar">
              <input
                type="text"
                placeholder="Search by template name, code, or subject..."
                value={templateSearch}
                onChange={(e) => setTemplateSearch(e.target.value)}
                className="notif-search-input"
              />

              <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", flexWrap: "wrap" }}>
                <select
                  aria-label="Filter templates by channel"
                  value={templateChannelFilter}
                  onChange={(e) => setTemplateChannelFilter(e.target.value)}
                  className="notif-select"
                >
                  <option value="">All Channels</option>
                  <option value="email">Email</option>
                  <option value="in_app">In-App</option>
                  <option value="sms">SMS</option>
                  <option value="webhook">Webhook</option>
                </select>

                <select
                  aria-label="Filter templates by status"
                  value={templateStatusFilter}
                  onChange={(e) => setTemplateStatusFilter(e.target.value)}
                  className="notif-select"
                >
                  <option value="">All Statuses</option>
                  <option value="active">Active</option>
                  <option value="draft">Draft</option>
                  <option value="retired">Retired</option>
                </select>
              </div>
            </div>

            {/* Templates Table */}
            <div className="product-table-container">
              <div className="table-responsive">
                <table className="enterprise-table" aria-label="Notification Templates">
                  <thead>
                    <tr>
                      <th scope="col" style={{ width: "26%" }}>Template Code & Name</th>
                      <th scope="col" style={{ width: "12%" }}>Channel</th>
                      <th scope="col" style={{ width: "10%" }}>Version</th>
                      <th scope="col" style={{ width: "32%" }}>Subject / Content Preview</th>
                      <th scope="col" style={{ width: "10%" }}>Status</th>
                      <th scope="col" style={{ width: "10%", textAlign: "right" }}>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredTemplates.length === 0 ? (
                      <tr>
                        <td colSpan={6} style={{ padding: "3rem", textAlign: "center" }}>
                          <p style={{ fontWeight: 600, color: "var(--text-primary)" }}>
                            No matching templates found
                          </p>
                          <p className="text-caption" style={{ marginTop: "0.25rem" }}>
                            Try adjusting your search criteria or channel filters.
                          </p>
                        </td>
                      </tr>
                    ) : (
                      filteredTemplates.map((tmpl) => (
                        <tr key={tmpl.id} className="table-row">
                          {/* Name & Code */}
                          <td>
                            <div style={{ fontWeight: 600, color: "var(--text-primary)" }}>
                              {tmpl.name}
                            </div>
                            <div className="notif-code-pill">{tmpl.code}</div>
                          </td>

                          {/* Channel */}
                          <td>
                            <span className="notif-channel-tag">{tmpl.channel}</span>
                          </td>

                          {/* Version */}
                          <td>
                            <span className="notif-version-pill">v{tmpl.version}</span>
                          </td>

                          {/* Subject Preview with dynamic variable chips */}
                          <td>
                            <div style={{ maxWidth: "340px", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={tmpl.subject_template}>
                              {formatSubjectWithChips(tmpl.subject_template)}
                            </div>
                          </td>

                          {/* Status */}
                          <td>
                            <span
                              className={`notif-status-badge ${
                                tmpl.status === "active"
                                  ? "notif-status-active"
                                  : tmpl.status === "retired"
                                  ? "notif-status-retired"
                                  : "notif-status-draft"
                              }`}
                            >
                              &bull; {tmpl.status}
                            </span>
                          </td>

                          {/* Actions */}
                          <td style={{ textAlign: "right" }}>
                            <div style={{ display: "inline-flex", alignItems: "center", gap: "0.4rem", justifyContent: "flex-end" }}>
                              <button
                                type="button"
                                onClick={() => handleOpenPreview(tmpl)}
                                className="btn btn-secondary btn-sm"
                                title="Open template preview"
                              >
                                <EyeIcon size={14} />
                                <span>Preview</span>
                              </button>

                              {tmpl.status === "active" && (
                                <>
                                  <button
                                    type="button"
                                    onClick={() => handleOpenNewVersion(tmpl)}
                                    className="btn btn-secondary btn-sm"
                                    title="Create next monotonic version"
                                  >
                                    New Version
                                  </button>
                                  <button
                                    type="button"
                                    onClick={() => handleOpenRetire(tmpl)}
                                    className="btn btn-danger btn-sm"
                                    style={{ padding: "0.4rem 0.65rem", minHeight: "32px", fontSize: "0.75rem" }}
                                    title="Retire this template"
                                  >
                                    Retire
                                  </button>
                                </>
                              )}
                            </div>
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        ) : (
          /* DELIVERY QUEUE & LOGS VIEW */
          <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
            {/* Toolbar */}
            <div className="notif-toolbar">
              <input
                type="text"
                placeholder="Filter by recipient email or template code..."
                value={deliverySearch}
                onChange={(e) => setDeliverySearch(e.target.value)}
                className="notif-search-input"
              />

              <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", flexWrap: "wrap" }}>
                <select
                  aria-label="Filter by delivery status"
                  value={deliveryStatusFilter}
                  onChange={(e) => setDeliveryStatusFilter(e.target.value)}
                  className="notif-select"
                >
                  <option value="">All Statuses</option>
                  <option value="queued">Queued</option>
                  <option value="sent">Sent</option>
                  <option value="failed">Failed</option>
                  <option value="retrying">Retrying</option>
                </select>

                <select
                  aria-label="Filter by delivery channel"
                  value={deliveryChannelFilter}
                  onChange={(e) => setDeliveryChannelFilter(e.target.value)}
                  className="notif-select"
                >
                  <option value="">All Channels</option>
                  <option value="email">Email</option>
                  <option value="in_app">In-App</option>
                  <option value="sms">SMS</option>
                  <option value="webhook">Webhook</option>
                </select>
              </div>
            </div>

            {/* Deliveries Table */}
            <div className="product-table-container">
              <div className="table-responsive">
                <table className="enterprise-table" aria-label="Notification Delivery Queue">
                  <thead>
                    <tr>
                      <th scope="col" style={{ width: "24%" }}>Recipient</th>
                      <th scope="col" style={{ width: "22%" }}>Template & Channel</th>
                      <th scope="col" style={{ width: "12%" }}>Status</th>
                      <th scope="col" style={{ width: "10%" }}>Attempts</th>
                      <th scope="col" style={{ width: "14%" }}>Timestamps</th>
                      <th scope="col" style={{ width: "10%" }}>Diagnostics</th>
                      <th scope="col" style={{ width: "8%", textAlign: "right" }}>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {deliveries.length === 0 ? (
                      <tr>
                        <td colSpan={7} style={{ padding: "3rem", textAlign: "center" }}>
                          <p style={{ fontWeight: 600, color: "var(--text-primary)" }}>
                            No notification deliveries recorded
                          </p>
                          <p className="text-caption" style={{ marginTop: "0.25rem" }}>
                            Deliveries will appear here as automated system notifications are triggered.
                          </p>
                        </td>
                      </tr>
                    ) : (
                      deliveries.map((del) => (
                        <tr key={del.id} className="table-row">
                          {/* Recipient */}
                          <td>
                            <div style={{ fontWeight: 600, color: "var(--text-primary)" }}>
                              {del.recipient_email}
                            </div>
                            {del.recipient_user && (
                              <div className="text-caption" style={{ fontFamily: "var(--font-code)" }}>
                                User ID: {del.recipient_user.slice(0, 8)}…
                              </div>
                            )}
                          </td>

                          {/* Template & Channel */}
                          <td>
                            <div style={{ fontWeight: 500, color: "var(--text-primary)" }}>
                              {del.template_name || del.template_code}
                            </div>
                            <div style={{ display: "flex", alignItems: "center", gap: "0.4rem", marginTop: "0.2rem" }}>
                              <span className="notif-code-pill">{del.template_code}</span>
                              <span style={{ color: "var(--text-muted)" }}>•</span>
                              <span className="notif-channel-tag">{del.channel || "email"}</span>
                            </div>
                          </td>

                          {/* Status */}
                          <td>
                            <span
                              className={`notif-status-badge ${
                                del.status === "sent"
                                  ? "notif-status-active"
                                  : del.status === "failed"
                                  ? "notif-status-danger"
                                  : del.status === "retrying"
                                  ? "notif-status-warning"
                                  : "notif-status-queued"
                              }`}
                            >
                              &bull; {del.status}
                            </span>
                          </td>

                          {/* Attempts */}
                          <td>
                            <span style={{ fontFamily: "var(--font-code)", fontWeight: 600 }}>
                              {del.retry_count}
                            </span>
                            <span style={{ color: "var(--text-muted)", fontSize: "0.75rem" }}>
                              {" "}
                              / {del.max_retries}
                            </span>
                          </td>

                          {/* Timestamps */}
                          <td>
                            <div style={{ fontSize: "0.75rem", color: "var(--text-secondary)" }}>
                              Queued: {new Date(del.queued_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })}
                            </div>
                            {del.sent_at && (
                              <div style={{ fontSize: "0.72rem", color: "var(--status-success)" }}>
                                Sent: {new Date(del.sent_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })}
                              </div>
                            )}
                            {del.failed_at && (
                              <div style={{ fontSize: "0.72rem", color: "var(--status-danger)" }}>
                                Failed: {new Date(del.failed_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })}
                              </div>
                            )}
                          </td>

                          {/* Diagnostics */}
                          <td>
                            {del.failure_reason ? (
                              <button
                                type="button"
                                onClick={() => setViewingDelivery(del)}
                                className="notif-diag-btn"
                                title="Click to inspect failure reason"
                              >
                                View Error
                              </button>
                            ) : (
                              <span style={{ color: "var(--text-muted)", fontSize: "0.75rem" }}>
                                Clean
                              </span>
                            )}
                          </td>

                          {/* Actions */}
                          <td style={{ textAlign: "right" }}>
                            {del.status === "sent" ? (
                              <span style={{ color: "var(--text-muted)", fontSize: "0.75rem", fontWeight: 500 }}>
                                Delivered
                              </span>
                            ) : (
                              <button
                                type="button"
                                onClick={() => handleRetryDelivery(del.id)}
                                disabled={retryingDeliveryId === del.id}
                                className="btn btn-primary btn-sm"
                                style={{ minHeight: "30px", padding: "0.25rem 0.65rem", fontSize: "0.75rem" }}
                                title="Safely re-attempt delivery execution"
                              >
                                <RefreshIcon size={12} className={retryingDeliveryId === del.id ? "animate-spin" : ""} />
                                <span>{retryingDeliveryId === del.id ? "Retrying…" : "Retry"}</span>
                              </button>
                            )}
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}

        {/* ------------------------------------------------------------- */}
        {/* PREVIEW MODAL DIALOG                                          */}
        {/* ------------------------------------------------------------- */}
        {previewTemplate && (
          <div className="notif-modal-backdrop" role="dialog" aria-modal="true">
            <div className="notif-modal-card notif-modal-lg">
              <div className="notif-modal-header">
                <div>
                  <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                    <h2 className="heading-title">Preview: {previewTemplate.name}</h2>
                    <span className="notif-version-pill">v{previewTemplate.version}</span>
                  </div>
                  <div className="text-caption" style={{ marginTop: "0.2rem" }}>
                    Code: <strong style={{ color: "var(--text-primary)" }}>{previewTemplate.code}</strong> &bull; Channel: {previewTemplate.channel.toUpperCase()}
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => setPreviewTemplate(null)}
                  className="dialog-close-btn"
                  aria-label="Close preview modal"
                >
                  <CloseIcon size={18} />
                </button>
              </div>

              <div className="notif-modal-body">
                {previewError && (
                  <div className="notif-alert-banner notif-alert-error">
                    <AlertCircleIcon size={16} />
                    <span>{previewError}</span>
                  </div>
                )}

                {previewLoading ? (
                  <div style={{ padding: "3rem", display: "flex", justifyContent: "center" }}>
                    <LoadingSpinner label="Resolving server template variables..." />
                  </div>
                ) : previewResult ? (
                  <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
                    {/* Unresolved Variables Banner */}
                    {previewResult.unresolved_variables && previewResult.unresolved_variables.length > 0 && (
                      <div className="notif-alert-banner notif-alert-warning">
                        <AlertCircleIcon size={16} style={{ flexShrink: 0 }} />
                        <div>
                          <strong>Unresolved template variables: </strong>
                          {previewResult.unresolved_variables.map((v) => (
                            <code key={v} style={{ margin: "0 0.25rem", padding: "0.1rem 0.35rem", background: "var(--status-warning-bg)", borderRadius: "4px" }}>
                              {`{{ ${v} }}`}
                            </code>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Simulated Email Envelope Card */}
                    <div className="notif-envelope">
                      <div className="notif-envelope-header">
                        <div className="notif-envelope-row">
                          <span className="notif-envelope-label">From:</span>
                          <span className="notif-envelope-val">Envisage System &lt;notifications@envisage.internal&gt;</span>
                        </div>
                        <div className="notif-envelope-row">
                          <span className="notif-envelope-label">To:</span>
                          <span className="notif-envelope-val">Alex Mercer &lt;alex@example.com&gt;</span>
                        </div>
                        <div className="notif-envelope-row">
                          <span className="notif-envelope-label">Subject:</span>
                          <span style={{ fontWeight: 600, color: "var(--text-primary)" }}>
                            {previewResult.rendered_subject}
                          </span>
                        </div>
                      </div>

                      <div className="notif-envelope-body">
                        {previewResult.rendered_body || (
                          <span style={{ color: "var(--text-muted)", fontStyle: "italic" }}>
                            Reference: {previewResult.body_ref}
                          </span>
                        )}
                      </div>
                    </div>

                    {/* Detected Variables Chips */}
                    {previewResult.supported_variables && previewResult.supported_variables.length > 0 && (
                      <div>
                        <span className="text-caption" style={{ fontWeight: 600, textTransform: "uppercase", display: "block", marginBottom: "0.4rem" }}>
                          Detected Template Variables:
                        </span>
                        <div style={{ display: "flex", flexWrap: "wrap", gap: "0.4rem" }}>
                          {previewResult.supported_variables.map((v) => (
                            <span key={v} className="notif-variable-chip">
                              {`{{ ${v} }}`}
                            </span>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Expandable Context JSON Editor */}
                    <details className="notif-details-accordion">
                      <summary style={{ cursor: "pointer", fontWeight: 600, fontSize: "0.8125rem", color: "var(--text-primary)", display: "flex", justifyContent: "space-between" }}>
                        <span>Customize Sample Context (JSON)</span>
                        <span style={{ fontSize: "0.75rem", color: "var(--brand-primary)" }}>Edit Variables ▾</span>
                      </summary>
                      <div style={{ marginTop: "0.75rem", display: "flex", flexDirection: "column", gap: "0.5rem" }}>
                        <textarea
                          rows={5}
                          value={previewContextJson}
                          onChange={(e) => setPreviewContextJson(e.target.value)}
                          className="form-input"
                          style={{ fontFamily: "var(--font-code)", fontSize: "0.75rem" }}
                        />
                        <div style={{ display: "flex", justifyContent: "flex-end" }}>
                          <button
                            type="button"
                            onClick={handleExecutePreview}
                            disabled={previewLoading}
                            className="btn btn-secondary btn-sm"
                          >
                            Re-render Preview
                          </button>
                        </div>
                      </div>
                    </details>
                  </div>
                ) : null}
              </div>

              <div className="notif-modal-footer">
                <button
                  type="button"
                  onClick={() => setPreviewTemplate(null)}
                  className="btn btn-secondary btn-sm"
                >
                  Close Preview
                </button>
              </div>
            </div>
          </div>
        )}

        {/* ------------------------------------------------------------- */}
        {/* NEW VERSION MODAL DIALOG                                      */}
        {/* ------------------------------------------------------------- */}
        {versioningTemplate && (
          <div className="notif-modal-backdrop" role="dialog" aria-modal="true">
            <form onSubmit={handleCreateNewVersion} className="notif-modal-card">
              <div className="notif-modal-header">
                <div>
                  <h2 className="heading-title">Author New Version</h2>
                  <div className="text-caption" style={{ marginTop: "0.2rem" }}>
                    {versioningTemplate.name} (v{versioningTemplate.version} → v{versioningTemplate.version + 1})
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => setVersioningTemplate(null)}
                  className="dialog-close-btn"
                  aria-label="Close modal"
                >
                  <CloseIcon size={18} />
                </button>
              </div>

              <div className="notif-modal-body">
                {versionError && (
                  <div className="notif-alert-banner notif-alert-error">
                    <AlertCircleIcon size={16} />
                    <span>{versionError}</span>
                  </div>
                )}

                <div className="form-group">
                  <label className="form-label">
                    Subject Line Template <span style={{ color: "var(--status-danger)" }}>*</span>
                  </label>
                  <input
                    type="text"
                    required
                    value={newSubject}
                    onChange={(e) => setNewSubject(e.target.value)}
                    placeholder="e.g. You have been invited to join {{ org_name }}"
                    className="form-input"
                  />
                  <span className="text-caption" style={{ marginTop: "0.25rem" }}>
                    Available tags: <code>{"{{ org_name }}"}</code>, <code>{"{{ role_name }}"}</code>, <code>{"{{ activation_url }}"}</code>
                  </span>
                </div>

                <div className="form-group">
                  <label className="form-label">
                    Body Reference / Template Key <span style={{ color: "var(--status-danger)" }}>*</span>
                  </label>
                  <input
                    type="text"
                    required
                    value={newBodyRef}
                    onChange={(e) => setNewBodyRef(e.target.value)}
                    placeholder="e.g. templates/auth/user_invitation_v2.html"
                    className="form-input"
                    style={{ fontFamily: "var(--font-code)" }}
                  />
                  <span className="text-caption" style={{ marginTop: "0.25rem" }}>
                    Server template identifier or storage path (zero plaintext secrets).
                  </span>
                </div>

                <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginTop: "0.5rem" }}>
                  <input
                    type="checkbox"
                    id="trans-toggle"
                    checked={newIsTransactional}
                    onChange={(e) => setNewIsTransactional(e.target.checked)}
                    style={{ width: "16px", height: "16px", cursor: "pointer" }}
                  />
                  <label htmlFor="trans-toggle" style={{ fontSize: "0.8125rem", color: "var(--text-primary)", cursor: "pointer" }}>
                    Transactional notification (exempt from promotional opt-outs)
                  </label>
                </div>
              </div>

              <div className="notif-modal-footer">
                <button
                  type="button"
                  onClick={() => setVersioningTemplate(null)}
                  className="btn btn-secondary btn-sm"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={versionSubmitting}
                  className="btn btn-primary btn-sm"
                >
                  {versionSubmitting ? "Publishing…" : `Publish Version v${versioningTemplate.version + 1}`}
                </button>
              </div>
            </form>
          </div>
        )}

        {/* ------------------------------------------------------------- */}
        {/* RETIRE CONFIRMATION MODAL                                     */}
        {/* ------------------------------------------------------------- */}
        {retiringTemplate && (
          <div className="notif-modal-backdrop" role="dialog" aria-modal="true">
            <div className="notif-modal-card" style={{ maxWidth: "460px" }}>
              <div className="notif-modal-header">
                <div>
                  <h2 className="heading-title" style={{ color: "var(--status-danger)" }}>
                    Retire Notification Template
                  </h2>
                  <div className="text-caption">
                    {retiringTemplate.code} (v{retiringTemplate.version})
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => setRetiringTemplate(null)}
                  className="dialog-close-btn"
                  aria-label="Close"
                >
                  <CloseIcon size={18} />
                </button>
              </div>

              <div className="notif-modal-body">
                {retireError && (
                  <div className="notif-alert-banner notif-alert-error">
                    <AlertCircleIcon size={16} />
                    <span>{retireError}</span>
                  </div>
                )}
                <p className="text-body">
                  Are you sure you want to retire <strong style={{ color: "var(--text-primary)" }}>'{retiringTemplate.name}'</strong>?
                  Retired templates will no longer be selected for new automated dispatches. Historical delivery logs remain intact.
                </p>
              </div>

              <div className="notif-modal-footer">
                <button
                  type="button"
                  onClick={() => setRetiringTemplate(null)}
                  className="btn btn-secondary btn-sm"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={handleConfirmRetire}
                  disabled={retireSubmitting}
                  className="btn btn-danger btn-sm"
                >
                  {retireSubmitting ? "Retiring…" : "Confirm Retirement"}
                </button>
              </div>
            </div>
          </div>
        )}

        {/* ------------------------------------------------------------- */}
        {/* DIAGNOSTICS MODAL                                             */}
        {/* ------------------------------------------------------------- */}
        {viewingDelivery && (
          <div className="notif-modal-backdrop" role="dialog" aria-modal="true">
            <div className="notif-modal-card" style={{ maxWidth: "520px" }}>
              <div className="notif-modal-header">
                <div>
                  <h2 className="heading-title">Delivery Diagnostics</h2>
                  <div className="text-caption" style={{ fontFamily: "var(--font-code)" }}>
                    {viewingDelivery.id}
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => setViewingDelivery(null)}
                  className="dialog-close-btn"
                  aria-label="Close"
                >
                  <CloseIcon size={18} />
                </button>
              </div>

              <div className="notif-modal-body" style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
                <div>
                  <span className="text-caption" style={{ fontWeight: 600, display: "block" }}>Recipient Email:</span>
                  <div style={{ fontFamily: "var(--font-code)", fontSize: "0.875rem", color: "var(--text-primary)" }}>
                    {viewingDelivery.recipient_email}
                  </div>
                </div>

                <div>
                  <span className="text-caption" style={{ fontWeight: 600, display: "block" }}>Failure Diagnostic Message:</span>
                  <div style={{
                    padding: "0.75rem",
                    borderRadius: "8px",
                    background: "var(--status-danger-bg)",
                    border: "1px solid var(--status-danger-border)",
                    color: "var(--status-danger)",
                    fontFamily: "var(--font-code)",
                    fontSize: "0.75rem",
                    whiteSpace: "pre-wrap",
                    wordBreak: "break-word"
                  }}>
                    {viewingDelivery.failure_reason || "No diagnostic details recorded."}
                  </div>
                </div>

                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.5rem" }}>
                  <div>
                    <span className="text-caption">Attempts:</span>
                    <div style={{ fontWeight: 600, color: "var(--text-primary)" }}>
                      {viewingDelivery.retry_count} / {viewingDelivery.max_retries}
                    </div>
                  </div>
                  <div>
                    <span className="text-caption">Queued At:</span>
                    <div style={{ fontSize: "0.75rem", color: "var(--text-primary)" }}>
                      {new Date(viewingDelivery.queued_at).toLocaleString()}
                    </div>
                  </div>
                </div>
              </div>

              <div className="notif-modal-footer">
                <button
                  type="button"
                  onClick={() => setViewingDelivery(null)}
                  className="btn btn-secondary btn-sm"
                >
                  Close
                </button>
              </div>
            </div>
          </div>
        )}

        {/* ------------------------------------------------------------- */}
        {/* COMPREHENSIVE NATIVE SCOPED DESIGN SYSTEM STYLES              */}
        {/* ------------------------------------------------------------- */}
        <style>{`
          .notif-page-container {
            max-width: 1320px;
            margin: 0 auto;
            padding: 2rem 1.5rem 4rem 1.5rem;
            display: flex;
            flex-direction: column;
            gap: 1.5rem;
          }

          .notif-page-header {
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            gap: 1rem;
            flex-wrap: wrap;
            padding-bottom: 1.25rem;
            border-bottom: 1px solid var(--border-glass);
          }

          .notif-title-row {
            display: flex;
            align-items: center;
            gap: 0.75rem;
          }

          .notif-badge-pill {
            display: inline-flex;
            align-items: center;
            padding: 0.2rem 0.65rem;
            border-radius: 999px;
            font-size: 0.75rem;
            font-weight: 600;
            background: var(--brand-primary-light);
            color: var(--brand-primary);
            border: 1px solid var(--border-glass);
          }

          .notif-alert-banner {
            display: flex;
            align-items: center;
            gap: 0.75rem;
            padding: 0.75rem 1rem;
            border-radius: 10px;
            font-size: 0.8125rem;
          }

          .notif-alert-error {
            background: var(--status-danger-bg);
            border: 1px solid var(--status-danger-border);
            color: var(--status-danger);
          }

          .notif-alert-success {
            background: var(--status-success-bg);
            border: 1px solid var(--status-success-border);
            color: var(--status-success);
          }

          .notif-alert-warning {
            background: var(--status-warning-bg);
            border: 1px solid var(--status-warning-border);
            color: var(--status-warning);
          }

          .notif-alert-dismiss {
            background: transparent;
            border: none;
            color: inherit;
            cursor: pointer;
            opacity: 0.7;
            padding: 0.2rem;
            display: flex;
            align-items: center;
            justify-content: center;
          }

          .notif-alert-dismiss:hover {
            opacity: 1;
          }

          /* KPI Indicators */
          .notif-kpi-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(230px, 1fr));
            gap: 1rem;
          }

          .notif-kpi-card {
            background: var(--glass-surface-elevated);
            border: 1px solid var(--border-glass);
            border-radius: 12px;
            padding: 1.25rem;
            box-shadow: var(--shadow-sm);
            display: flex;
            flex-direction: column;
            gap: 0.4rem;
            transition: border-color 0.15s ease;
          }

          .notif-kpi-card:hover {
            border-color: var(--border-strong);
          }

          .notif-kpi-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            font-size: 0.75rem;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            color: var(--text-muted);
          }

          .notif-kpi-dot {
            width: 8px;
            height: 8px;
            border-radius: 50%;
          }

          .notif-dot-brand { background: var(--brand-primary); }
          .notif-dot-success { background: var(--status-success); }
          .notif-dot-warning { background: var(--status-warning); }
          .notif-dot-danger { background: var(--status-danger); }

          .notif-kpi-value {
            font-size: 1.85rem;
            font-weight: 700;
            color: var(--text-primary);
            line-height: 1.1;
          }

          .notif-text-success { color: var(--status-success); }
          .notif-text-warning { color: var(--status-warning); }
          .notif-text-danger { color: var(--status-danger); }

          .notif-kpi-caption {
            font-size: 0.75rem;
            color: var(--text-muted);
          }

          /* Tabs */
          .notif-tabs-bar {
            display: flex;
            gap: 1.5rem;
            border-bottom: 1px solid var(--border-glass);
          }

          .notif-tab-btn {
            background: transparent;
            border: none;
            border-bottom: 2px solid transparent;
            padding: 0.75rem 0.25rem;
            font-size: 0.875rem;
            font-weight: 500;
            font-family: inherit;
            color: var(--text-muted);
            cursor: pointer;
            display: inline-flex;
            align-items: center;
            gap: 0.5rem;
            transition: all 0.15s ease;
          }

          .notif-tab-btn:hover {
            color: var(--text-primary);
          }

          .notif-tab-active {
            color: var(--brand-primary);
            border-bottom-color: var(--brand-primary);
            font-weight: 600;
          }

          .notif-tab-count {
            padding: 0.1rem 0.5rem;
            border-radius: 999px;
            font-size: 0.72rem;
            background: var(--glass-surface-sunken);
            border: 1px solid var(--border-subtle);
            color: var(--text-muted);
          }

          .notif-tab-active .notif-tab-count {
            background: var(--brand-primary-light);
            border-color: var(--border-glass);
            color: var(--brand-primary);
            font-weight: 700;
          }

          /* Toolbar */
          .notif-toolbar {
            background: var(--glass-surface-elevated);
            border: 1px solid var(--border-glass);
            border-radius: 12px;
            padding: 0.875rem 1rem;
            display: flex;
            justify-content: space-between;
            align-items: center;
            gap: 1rem;
            flex-wrap: wrap;
          }

          .notif-search-input {
            flex: 1;
            min-width: 240px;
            max-width: 440px;
            background: var(--input-bg);
            border: 1px solid var(--input-border);
            border-radius: 8px;
            padding: 0.5rem 0.85rem;
            font-size: 0.8125rem;
            color: var(--text-primary);
            outline: none;
            transition: border-color 0.15s ease;
          }

          .notif-search-input:focus {
            border-color: var(--brand-primary);
            box-shadow: 0 0 0 3px var(--brand-primary-light);
          }

          .notif-select {
            background: var(--input-bg);
            border: 1px solid var(--input-border);
            border-radius: 8px;
            padding: 0.5rem 0.85rem;
            font-size: 0.8125rem;
            color: var(--text-primary);
            outline: none;
            cursor: pointer;
            transition: border-color 0.15s ease;
          }

          .notif-select:focus {
            border-color: var(--brand-primary);
            box-shadow: 0 0 0 3px var(--brand-primary-light);
          }

          /* Pill & Chips */
          .notif-code-pill {
            display: inline-block;
            margin-top: 0.25rem;
            padding: 0.15rem 0.45rem;
            border-radius: 4px;
            font-family: var(--font-code);
            font-size: 0.72rem;
            background: var(--glass-surface-sunken);
            border: 1px solid var(--border-subtle);
            color: var(--text-muted);
          }

          .notif-channel-tag {
            display: inline-flex;
            align-items: center;
            padding: 0.15rem 0.5rem;
            border-radius: 4px;
            font-size: 0.72rem;
            font-weight: 600;
            text-transform: uppercase;
            background: var(--glass-surface-sunken);
            border: 1px solid var(--border-subtle);
            color: var(--text-secondary);
          }

          .notif-version-pill {
            display: inline-flex;
            align-items: center;
            padding: 0.15rem 0.45rem;
            border-radius: 999px;
            font-family: var(--font-code);
            font-size: 0.75rem;
            font-weight: 600;
            background: rgba(59, 130, 246, 0.12);
            color: #3b82f6;
            border: 1px solid rgba(59, 130, 246, 0.25);
          }

          .notif-subject-preview {
            display: inline-flex;
            flex-wrap: wrap;
            align-items: center;
            gap: 0.25rem;
            font-size: 0.8125rem;
            color: var(--text-primary);
          }

          .notif-variable-chip {
            display: inline-flex;
            align-items: center;
            padding: 0.1rem 0.4rem;
            border-radius: 4px;
            font-family: var(--font-code);
            font-size: 0.72rem;
            font-weight: 600;
            background: var(--brand-primary-light);
            color: var(--brand-primary);
            border: 1px solid rgba(99, 102, 241, 0.25);
          }

          /* Status Badges */
          .notif-status-badge {
            display: inline-flex;
            align-items: center;
            gap: 0.3rem;
            padding: 0.2rem 0.6rem;
            border-radius: 999px;
            font-size: 0.72rem;
            font-weight: 700;
            text-transform: uppercase;
          }

          .notif-status-active {
            background: var(--status-success-bg);
            color: var(--status-success);
            border: 1px solid var(--status-success-border);
          }

          .notif-status-retired {
            background: var(--status-neutral-bg);
            color: var(--status-neutral);
            border: 1px solid var(--status-neutral-border);
          }

          .notif-status-draft {
            background: var(--status-warning-bg);
            color: var(--status-warning);
            border: 1px solid var(--status-warning-border);
          }

          .notif-status-danger {
            background: var(--status-danger-bg);
            color: var(--status-danger);
            border: 1px solid var(--status-danger-border);
          }

          .notif-status-warning {
            background: var(--status-warning-bg);
            color: var(--status-warning);
            border: 1px solid var(--status-warning-border);
          }

          .notif-status-queued {
            background: rgba(59, 130, 246, 0.12);
            color: #3b82f6;
            border: 1px solid rgba(59, 130, 246, 0.3);
          }

          .notif-diag-btn {
            background: transparent;
            border: none;
            color: var(--status-danger);
            font-size: 0.75rem;
            font-weight: 600;
            cursor: pointer;
            text-decoration: underline;
            padding: 0;
          }

          .notif-diag-btn:hover {
            color: #dc2626;
          }

          .notif-loading-panel {
            background: var(--glass-surface-elevated);
            border: 1px solid var(--border-glass);
            border-radius: 14px;
            padding: 4rem 2rem;
            display: flex;
            align-items: center;
            justify-content: center;
          }

          /* Modals */
          .notif-modal-backdrop {
            position: fixed;
            inset: 0;
            z-index: 9999;
            background: rgba(0, 0, 0, 0.65);
            backdrop-filter: blur(8px);
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 1rem;
            animation: notifFadeIn 0.15s ease-out;
          }

          .notif-modal-card {
            background: var(--glass-surface-elevated);
            border: 1px solid var(--border-glass);
            border-radius: 16px;
            box-shadow: var(--shadow-lg);
            width: 100%;
            max-width: 580px;
            max-height: 90vh;
            display: flex;
            flex-direction: column;
            overflow: hidden;
            animation: notifScaleUp 0.15s ease-out;
          }

          .notif-modal-lg {
            max-width: 760px;
          }

          .notif-modal-header {
            padding: 1.25rem 1.5rem;
            border-bottom: 1px solid var(--border-subtle);
            display: flex;
            align-items: center;
            justify-content: space-between;
          }

          .notif-modal-body {
            padding: 1.25rem 1.5rem;
            overflow-y: auto;
            flex: 1;
            display: flex;
            flex-direction: column;
            gap: 1rem;
          }

          .notif-modal-footer {
            padding: 1rem 1.5rem;
            border-top: 1px solid var(--border-subtle);
            background: var(--glass-surface-sunken);
            display: flex;
            align-items: center;
            justify-content: flex-end;
            gap: 0.75rem;
            flex-shrink: 0;
          }

          /* Simulated Email Envelope */
          .notif-envelope {
            border: 1px solid var(--border-glass);
            border-radius: 10px;
            overflow: hidden;
          }

          .notif-envelope-header {
            background: var(--glass-surface-sunken);
            border-bottom: 1px solid var(--border-subtle);
            padding: 0.85rem 1rem;
            display: flex;
            flex-direction: column;
            gap: 0.35rem;
            font-size: 0.75rem;
          }

          .notif-envelope-row {
            display: flex;
            gap: 0.5rem;
          }

          .notif-envelope-label {
            width: 55px;
            font-weight: 600;
            color: var(--text-muted);
          }

          .notif-envelope-val {
            font-family: var(--font-code);
            color: var(--text-secondary);
          }

          .notif-envelope-body {
            background: var(--bg-app);
            padding: 1.25rem;
            font-size: 0.8125rem;
            color: var(--text-primary);
            line-height: 1.6;
            white-space: pre-wrap;
            min-height: 140px;
          }

          .notif-details-accordion {
            background: var(--glass-surface-sunken);
            border: 1px solid var(--border-subtle);
            border-radius: 10px;
            padding: 0.75rem 1rem;
          }

          @keyframes notifFadeIn {
            from { opacity: 0; }
            to { opacity: 1; }
          }

          @keyframes notifScaleUp {
            from { opacity: 0; transform: scale(0.96); }
            to { opacity: 1; transform: scale(1); }
          }
        `}</style>
      </div>
    </AppShell>
  );
};
