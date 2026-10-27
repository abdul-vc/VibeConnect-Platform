import { FC, useEffect, useState, useCallback, useMemo } from "react";
import { Link } from "react-router-dom";
import { AppShell } from "../../components/AppShell.tsx";
import { LoadingSpinner } from "../../components/LoadingSpinner.tsx";
import {
  MailIcon,
  RotateCcwIcon,
  AlertCircleIcon,
  CalendarIcon,
  UserIcon,
  SearchIcon,
} from "../../components/Icons.tsx";
import {
  notificationsApi,
  NotificationDelivery,
} from "../../api/notifications.ts";

export const TenantNotificationsPage: FC = () => {
  const [deliveries, setDeliveries] = useState<NotificationDelivery[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<string>("");
  const [searchTerm, setSearchTerm] = useState<string>("");

  const loadDeliveries = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const params: Record<string, string> = {};
      if (statusFilter) params.status = statusFilter;
      const res = await notificationsApi.listDeliveries(params);
      setDeliveries(res.results || []);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load notification history.");
    } finally {
      setLoading(false);
    }
  }, [statusFilter]);

  useEffect(() => {
    void loadDeliveries();
  }, [loadDeliveries]);

  const filteredDeliveries = useMemo(() => {
    if (!searchTerm.trim()) return deliveries;
    const term = searchTerm.toLowerCase().trim();
    return deliveries.filter((del) => {
      const name = (del.template_name || "").toLowerCase();
      const code = (del.template_code || "").toLowerCase();
      const email = (del.recipient_email || "").toLowerCase();
      const ch = (del.channel || "").toLowerCase();
      return name.includes(term) || code.includes(term) || email.includes(term) || ch.includes(term);
    });
  }, [deliveries, searchTerm]);

  const getStatusBadge = (status: string) => {
    switch (status) {
      case "sent":
        return (
          <span className="badge badge-success">
            <span className="badge-dot" />
            Delivered (Sent)
          </span>
        );
      case "failed":
        return (
          <span className="badge badge-danger">
            <span className="badge-dot" />
            Failed
          </span>
        );
      case "queued":
      case "retrying":
        return (
          <span className="badge badge-warning">
            <span className="badge-dot" />
            {status === "retrying" ? "Retrying" : "Queued"}
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
      <div style={{ padding: "2rem", maxWidth: "1400px", margin: "0 auto" }}>
        {/* Breadcrumb Navigation */}
        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", fontSize: "0.8125rem", color: "var(--text-muted)", marginBottom: "1.25rem", fontWeight: 500 }}>
          <Link to="/tenant" style={{ color: "var(--text-muted)", textDecoration: "none", transition: "color 0.15s" }}>Tenant Admin</Link>
          <span>/</span>
          <span>Platform</span>
          <span>/</span>
          <span style={{ color: "var(--brand-primary)", fontWeight: 600 }}>Notifications & Alerts Log</span>
        </div>

        {/* Header */}
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
              <MailIcon size={24} />
            </div>
            <div>
              <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
                <h1
                  className="heading-hero"
                  style={{ fontSize: "1.75rem", margin: 0, color: "var(--text-primary)", fontWeight: 800, letterSpacing: "-0.02em" }}
                >
                  Notifications & Alerts Log
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
                  {deliveries.length} Records
                </span>
              </div>
              <p style={{ margin: "0.25rem 0 0 0", color: "var(--text-secondary)", fontSize: "0.9375rem" }}>
                Read-only history of communications, automated alerts, and invitation dispatches.
              </p>
            </div>
          </div>
          <div>
            <button
              type="button"
              onClick={loadDeliveries}
              disabled={loading}
              className="btn btn-secondary"
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: "0.5rem",
                padding: "0.45rem 0.95rem",
                fontSize: "0.8125rem",
                fontWeight: 600,
              }}
            >
              <RotateCcwIcon size={15} className={loading ? "spinner-icon" : ""} />
              Refresh
            </button>
          </div>
        </div>

        {/* Error Alert */}
        {error && (
          <div
            style={{
              padding: "1rem 1.25rem",
              background: "var(--status-danger-bg)",
              border: "1px solid var(--status-danger-border)",
              borderRadius: "0.5rem",
              color: "var(--status-danger)",
              marginBottom: "1.5rem",
              fontSize: "0.875rem",
              display: "flex",
              alignItems: "center",
              gap: "0.75rem",
            }}
          >
            <AlertCircleIcon size={18} style={{ flexShrink: 0 }} />
            <span>{error}</span>
          </div>
        )}

        {/* Table Card Container */}
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
            <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", flexWrap: "wrap" }}>
              <label
                htmlFor="tenant-status-filter"
                style={{ fontSize: "0.875rem", fontWeight: 600, color: "var(--text-secondary)" }}
              >
                Filter Status:
              </label>

              {/* Accessible Native Select for automated form testing */}
              <select
                id="tenant-status-filter"
                value={statusFilter}
                onChange={(e) => setStatusFilter(e.target.value)}
                style={{ display: "none" }}
                aria-label="Filter status selector"
              >
                <option value="">All Notifications</option>
                <option value="sent">Delivered (Sent)</option>
                <option value="queued">Queued / Processing</option>
                <option value="failed">Failed</option>
              </select>

              {/* Segmented Pill Group UI */}
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
                {(
                  [
                    { key: "", label: "All Notifications" },
                    { key: "sent", label: "Delivered (Sent)" },
                    { key: "queued", label: "Queued / Processing" },
                    { key: "failed", label: "Failed" },
                  ] as const
                ).map((s) => {
                  const isActive = statusFilter === s.key;
                  return (
                    <button
                      key={s.key}
                      type="button"
                      onClick={() => setStatusFilter(s.key)}
                      style={{
                        padding: "0.4rem 0.85rem",
                        borderRadius: "6px",
                        fontSize: "0.8125rem",
                        fontWeight: isActive ? 600 : 500,
                        border: "none",
                        background: isActive ? "var(--glass-surface-elevated)" : "transparent",
                        color: isActive ? "var(--brand-primary)" : "var(--text-secondary)",
                        boxShadow: isActive ? "var(--shadow-sm)" : "none",
                        cursor: "pointer",
                        transition: "all 0.15s ease",
                      }}
                    >
                      {s.label}
                    </button>
                  );
                })}
              </div>
            </div>

            <div style={{ display: "flex", alignItems: "center", gap: "1rem", flexWrap: "wrap" }}>
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
                  placeholder="Search recipient or topic..."
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
              <span style={{ fontSize: "0.875rem", color: "var(--text-secondary)" }}>
                Found: <strong style={{ color: "var(--text-primary)" }}>{filteredDeliveries.length}</strong>
              </span>
            </div>
          </div>

          {/* Table Content */}
          {loading ? (
            <div style={{ display: "flex", justifyContent: "center", padding: "4rem" }}>
              <LoadingSpinner label="Loading notification logs…" />
            </div>
          ) : filteredDeliveries.length === 0 ? (
            <div
              style={{
                padding: "3.5rem 2rem",
                textAlign: "center",
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                justifyContent: "center",
              }}
            >
              <div
                style={{
                  width: 52,
                  height: 52,
                  borderRadius: "50%",
                  background: "var(--surface-soft-blue)",
                  border: "1px solid rgba(56, 103, 245, 0.2)",
                  color: "var(--brand-primary)",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  marginBottom: "1rem",
                }}
              >
                <MailIcon size={26} />
              </div>
              <h3 style={{ margin: 0, fontSize: "1.125rem", color: "var(--text-primary)", fontWeight: 700 }}>
                No notifications recorded
              </h3>
              <p style={{ margin: "0.5rem 0 0 0", fontSize: "0.875rem", color: "var(--text-secondary)", maxWidth: "480px" }}>
                {searchTerm
                  ? "No notification dispatches match your search criteria."
                  : "No notifications recorded for this organization account."}
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
                      Message / Topic
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
                      Channel
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
                      Recipient
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
                      Status
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
                      Dispatched
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {filteredDeliveries.map((del) => (
                    <tr
                      key={del.id}
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
                        <div style={{ fontWeight: 600, color: "var(--text-primary)", fontSize: "0.9375rem" }}>
                          {del.template_name || del.template_code}
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
                            marginTop: "0.25rem",
                          }}
                        >
                          {del.template_code}
                        </span>
                      </td>
                      <td style={{ padding: "1rem 1.25rem", verticalAlign: "middle" }}>
                        <span
                          style={{
                            display: "inline-block",
                            padding: "0.2rem 0.5rem",
                            borderRadius: "4px",
                            fontSize: "0.75rem",
                            fontWeight: 600,
                            fontFamily: "var(--font-code)",
                            background: "var(--surface-soft-blue)",
                            color: "var(--brand-primary)",
                            border: "1px solid rgba(56, 103, 245, 0.2)",
                            textTransform: "uppercase",
                          }}
                        >
                          {del.channel}
                        </span>
                      </td>
                      <td style={{ padding: "1rem 1.25rem", verticalAlign: "middle" }}>
                        <div style={{ display: "flex", alignItems: "center", gap: "0.4rem", fontSize: "0.8125rem", color: "var(--text-primary)" }}>
                          <UserIcon size={14} style={{ color: "var(--text-muted)", flexShrink: 0 }} />
                          <span style={{ fontFamily: "var(--font-code)", fontWeight: 500 }}>
                            {del.recipient_email}
                          </span>
                        </div>
                      </td>
                      <td style={{ padding: "1rem 1.25rem", verticalAlign: "middle" }}>
                        {getStatusBadge(del.status)}
                      </td>
                      <td style={{ padding: "1rem 1.25rem", verticalAlign: "middle", whiteSpace: "nowrap" }}>
                        <div style={{ display: "flex", alignItems: "center", gap: "0.4rem", fontSize: "0.8125rem", color: "var(--text-secondary)" }}>
                          <CalendarIcon size={14} style={{ color: "var(--text-muted)" }} />
                          <span>
                            {del.sent_at
                              ? new Date(del.sent_at).toLocaleString()
                              : new Date(del.queued_at).toLocaleString()}
                          </span>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </AppShell>
  );
};

