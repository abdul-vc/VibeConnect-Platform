/**
 * Platform Owner Reports & Analytics Page (Phase 4F & 6E).
 *
 * Route: /reports
 * Context Guard: platform_owner
 */

import React, { useState, useEffect } from "react";
import { AppShell } from "../../components/AppShell.tsx";
import { LoadingSpinner } from "../../components/LoadingSpinner.tsx";
import {
  reportsApi,
  type OwnerReportsSummary,
  type OwnerAnalyticsResponse,
} from "../../api/reports.ts";

export const ReportsPage: React.FC = () => {
  const [activeTab, setActiveTab] = useState<"summary" | "analytics">("summary");

  // Summary State
  const [data, setData] = useState<OwnerReportsSummary | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // Analytics State (Phase 6E)
  const [analyticsData, setAnalyticsData] = useState<OwnerAnalyticsResponse | null>(null);
  const [isAnalyticsLoading, setIsAnalyticsLoading] = useState<boolean>(false);
  const [analyticsError, setAnalyticsError] = useState<string | null>(null);
  const [daysFilter, setDaysFilter] = useState<number>(30);

  useEffect(() => {
    let isMounted = true;
    async function loadReports() {
      setIsLoading(true);
      setErrorMessage(null);
      try {
        const summary = await reportsApi.getOwnerSummary();
        if (isMounted) setData(summary);
      } catch (err: unknown) {
        if (isMounted) {
          const msg =
            err && typeof err === "object" && "message" in err
              ? String((err as { message: string }).message)
              : "Failed to load platform reports.";
          setErrorMessage(msg);
        }
      } finally {
        if (isMounted) setIsLoading(false);
      }
    }
    void loadReports();
    return () => {
      isMounted = false;
    };
  }, []);

  const loadAnalytics = async (days: number) => {
    setIsAnalyticsLoading(true);
    setAnalyticsError(null);
    try {
      const end = new Date();
      const start = new Date();
      start.setDate(end.getDate() - days);
      const startStr = start.toISOString().split("T")[0];
      const endStr = end.toISOString().split("T")[0];

      const res = await reportsApi.getOwnerAnalytics(startStr, endStr);
      setAnalyticsData(res);
    } catch (err: unknown) {
      const msg =
        err && typeof err === "object" && "message" in err
          ? String((err as { message: string }).message)
          : "Failed to load analytics telemetry.";
      setAnalyticsError(msg);
    } finally {
      setIsAnalyticsLoading(false);
    }
  };

  useEffect(() => {
    if (activeTab === "analytics" && !analyticsData) {
      void loadAnalytics(daysFilter);
    }
  }, [activeTab]);

  const handleDaysChange = (newDays: number) => {
    setDaysFilter(newDays);
    void loadAnalytics(newDays);
  };

  return (
    <AppShell>
      <div style={{ padding: "2rem", maxWidth: "1400px", margin: "0 auto" }}>
        {/* Header */}
        <div style={{ marginBottom: "1.5rem" }}>
          <h1
            className="heading-hero"
            style={{ fontSize: "1.75rem", margin: "0 0 0.5rem 0", color: "var(--text-primary)" }}
          >
            Platform Reports & Analytics
          </h1>
          <p style={{ margin: 0, color: "var(--text-secondary)", fontSize: "0.9375rem" }}>
            Cross-tenant aggregate telemetry across organizations, product adoptions, usage volume, and verified 6E analytics metrics.
          </p>
        </div>

        {/* Tab Navigation */}
        <div style={{ display: "flex", gap: "1rem", borderBottom: "1px solid var(--border-color)", marginBottom: "2rem" }}>
          <button
            onClick={() => setActiveTab("summary")}
            style={{
              padding: "0.75rem 1.25rem",
              background: "none",
              border: "none",
              borderBottom: activeTab === "summary" ? "2px solid #3b82f6" : "2px solid transparent",
              color: activeTab === "summary" ? "#3b82f6" : "var(--text-secondary)",
              fontWeight: 600,
              cursor: "pointer",
              fontSize: "0.9375rem",
            }}
          >
            Platform Overview
          </button>
          <button
            onClick={() => setActiveTab("analytics")}
            style={{
              padding: "0.75rem 1.25rem",
              background: "none",
              border: "none",
              borderBottom: activeTab === "analytics" ? "2px solid #3b82f6" : "2px solid transparent",
              color: activeTab === "analytics" ? "#3b82f6" : "var(--text-secondary)",
              fontWeight: 600,
              cursor: "pointer",
              fontSize: "0.9375rem",
            }}
          >
            Verified Analytics & Telemetry (6E)
          </button>
        </div>

        {/* Tab 1: Standard Summary */}
        {activeTab === "summary" && (
          <div>
            {errorMessage && (
              <div
                style={{
                  padding: "1rem",
                  background: "rgba(239, 68, 68, 0.1)",
                  border: "1px solid rgba(239, 68, 68, 0.3)",
                  borderRadius: "0.5rem",
                  color: "#f87171",
                  marginBottom: "1.5rem",
                }}
              >
                {errorMessage}
              </div>
            )}

            {isLoading ? (
              <div style={{ display: "flex", justifyContent: "center", padding: "4rem" }}>
                <LoadingSpinner fullScreen={false} label="Loading reports..." />
              </div>
            ) : !data ? (
              <div
                style={{
                  padding: "3rem",
                  textAlign: "center",
                  background: "var(--bg-surface)",
                  borderRadius: "0.75rem",
                  border: "1px solid var(--border-color)",
                }}
              >
                <p style={{ color: "var(--text-secondary)", margin: 0 }}>No report data available.</p>
              </div>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: "2rem" }}>
                {/* Metric Cards Grid */}
                <div
                  style={{
                    display: "grid",
                    gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))",
                    gap: "1.5rem",
                  }}
                >
                  {/* Organization Health */}
                  <div
                    style={{
                      background: "var(--bg-surface)",
                      borderRadius: "0.75rem",
                      padding: "1.5rem",
                      border: "1px solid var(--border-color)",
                    }}
                  >
                    <h3
                      style={{
                        margin: "0 0 1rem 0",
                        fontSize: "0.875rem",
                        textTransform: "uppercase",
                        letterSpacing: "0.05em",
                        color: "var(--text-secondary)",
                      }}
                    >
                      Organizations
                    </h3>
                    <div style={{ fontSize: "2.25rem", fontWeight: 700, color: "var(--text-primary)", marginBottom: "0.5rem" }}>
                      {data.organizations.total}
                    </div>
                    <div style={{ display: "flex", gap: "1rem", fontSize: "0.875rem", color: "var(--text-secondary)" }}>
                      <span>
                        <strong style={{ color: "#34d399" }}>{data.organizations.active}</strong> active
                      </span>
                      <span>
                        <strong style={{ color: "#9ca3af" }}>{data.organizations.inactive}</strong> inactive
                      </span>
                    </div>
                  </div>

                  {/* Commercial Health */}
                  <div
                    style={{
                      background: "var(--bg-surface)",
                      borderRadius: "0.75rem",
                      padding: "1.5rem",
                      border: "1px solid var(--border-color)",
                    }}
                  >
                    <h3
                      style={{
                        margin: "0 0 1rem 0",
                        fontSize: "0.875rem",
                        textTransform: "uppercase",
                        letterSpacing: "0.05em",
                        color: "var(--text-secondary)",
                      }}
                    >
                      Active Subscriptions
                    </h3>
                    <div style={{ fontSize: "2.25rem", fontWeight: 700, color: "var(--text-primary)", marginBottom: "0.5rem" }}>
                      {data.commercial.active_subscriptions}
                    </div>
                    <div style={{ display: "flex", gap: "1rem", fontSize: "0.875rem", color: "var(--text-secondary)" }}>
                      <span>
                        Invoices: <strong>{data.commercial.total_invoices}</strong> ({data.commercial.paid_invoices} paid)
                      </span>
                      {data.commercial.open_reconciliations > 0 && (
                        <span style={{ color: "#fbbf24" }}>
                          <strong>{data.commercial.open_reconciliations}</strong> open issues
                        </span>
                      )}
                    </div>
                  </div>

                  {/* Ingested Usage */}
                  <div
                    style={{
                      background: "var(--bg-surface)",
                      borderRadius: "0.75rem",
                      padding: "1.5rem",
                      border: "1px solid var(--border-color)",
                    }}
                  >
                    <h3
                      style={{
                        margin: "0 0 1rem 0",
                        fontSize: "0.875rem",
                        textTransform: "uppercase",
                        letterSpacing: "0.05em",
                        color: "var(--text-secondary)",
                      }}
                    >
                      Usage Events
                    </h3>
                    <div style={{ fontSize: "2.25rem", fontWeight: 700, color: "var(--text-primary)", marginBottom: "0.5rem" }}>
                      {data.usage.total_events}
                    </div>
                    <div style={{ display: "flex", gap: "1rem", fontSize: "0.875rem", color: "var(--text-secondary)" }}>
                      <span>
                        Buckets: <strong>{data.usage.total_buckets}</strong>
                      </span>
                      <span style={{ color: data.usage.over_limit_buckets > 0 ? "#f87171" : "inherit" }}>
                        Over-quota: <strong>{data.usage.over_limit_buckets}</strong>
                      </span>
                    </div>
                  </div>
                </div>

                {/* Product Adoption Table */}
                <div
                  style={{
                    background: "var(--bg-surface)",
                    borderRadius: "0.75rem",
                    border: "1px solid var(--border-color)",
                    overflow: "hidden",
                  }}
                >
                  <div style={{ padding: "1.25rem 1.5rem", borderBottom: "1px solid var(--border-color)" }}>
                    <h2 style={{ margin: 0, fontSize: "1.125rem", color: "var(--text-primary)" }}>
                      Product Adoption Across Tenants
                    </h2>
                  </div>

                  {data.product_adoption.length === 0 ? (
                    <div style={{ padding: "2rem", textAlign: "center", color: "var(--text-secondary)" }}>
                      No catalog products found.
                    </div>
                  ) : (
                    <table style={{ width: "100%", borderCollapse: "collapse", textAlign: "left" }}>
                      <thead>
                        <tr style={{ borderBottom: "1px solid var(--border-color)", background: "rgba(255,255,255,0.02)" }}>
                          <th style={{ padding: "0.75rem 1.5rem", fontSize: "0.8125rem", color: "var(--text-secondary)" }}>
                            PRODUCT
                          </th>
                          <th style={{ padding: "0.75rem 1.5rem", fontSize: "0.8125rem", color: "var(--text-secondary)" }}>
                            CODE
                          </th>
                          <th style={{ padding: "0.75rem 1.5rem", fontSize: "0.8125rem", color: "var(--text-secondary)", textAlign: "right" }}>
                            ADOPTED TENANTS
                          </th>
                        </tr>
                      </thead>
                      <tbody>
                        {data.product_adoption.map((prod) => (
                          <tr key={prod.product_id} style={{ borderBottom: "1px solid var(--border-color)" }}>
                            <td style={{ padding: "1rem 1.5rem", fontWeight: 600, color: "var(--text-primary)" }}>
                              {prod.product_name}
                            </td>
                            <td style={{ padding: "1rem 1.5rem", fontSize: "0.875rem", color: "var(--text-secondary)", fontFamily: "monospace" }}>
                              {prod.product_code}
                            </td>
                            <td style={{ padding: "1rem 1.5rem", textAlign: "right", fontWeight: 600, color: "var(--text-primary)" }}>
                              <span
                                style={{
                                  display: "inline-block",
                                  padding: "0.25rem 0.625rem",
                                  borderRadius: "9999px",
                                  fontSize: "0.8125rem",
                                  background: "rgba(59, 130, 246, 0.15)",
                                  color: "#60a5fa",
                                }}
                              >
                                {prod.adopted_tenants_count}
                              </span>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </div>
              </div>
            )}
          </div>
        )}

        {/* Tab 2: Verified Analytics & Telemetry (6E) */}
        {activeTab === "analytics" && (
          <div>
            {/* Date-Range Selector */}
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                marginBottom: "1.5rem",
                background: "var(--bg-surface)",
                padding: "1rem 1.5rem",
                borderRadius: "0.75rem",
                border: "1px solid var(--border-color)",
              }}
            >
              <div>
                <span style={{ fontSize: "0.875rem", color: "var(--text-secondary)", marginRight: "1rem" }}>
                  Query Window (Enforced Max 90 Days):
                </span>
                <span style={{ fontWeight: 600, color: "var(--text-primary)" }}>
                  {analyticsData
                    ? `${analyticsData.time_window.start_date.split("T")[0]} to ${analyticsData.time_window.end_date.split("T")[0]} (${analyticsData.time_window.days} days)`
                    : "Loading..."}
                </span>
              </div>
              <div style={{ display: "flex", gap: "0.5rem" }}>
                {[30, 60, 90].map((d) => (
                  <button
                    key={d}
                    onClick={() => handleDaysChange(d)}
                    disabled={isAnalyticsLoading}
                    style={{
                      padding: "0.4rem 0.8rem",
                      borderRadius: "0.375rem",
                      border: "1px solid var(--border-color)",
                      background: daysFilter === d ? "var(--primary)" : "transparent",
                      color: daysFilter === d ? "#fff" : "var(--text-secondary)",
                      cursor: "pointer",
                      fontSize: "0.8125rem",
                      fontWeight: 500,
                    }}
                  >
                    Last {d} Days
                  </button>
                ))}
              </div>
            </div>

            {analyticsError && (
              <div
                style={{
                  padding: "1rem",
                  background: "rgba(239, 68, 68, 0.1)",
                  border: "1px solid rgba(239, 68, 68, 0.3)",
                  borderRadius: "0.5rem",
                  color: "#f87171",
                  marginBottom: "1.5rem",
                }}
              >
                {analyticsError}
              </div>
            )}

            {isAnalyticsLoading ? (
              <div style={{ display: "flex", justifyContent: "center", padding: "4rem" }}>
                <LoadingSpinner fullScreen={false} label="Computing verified analytics..." />
              </div>
            ) : !analyticsData ? (
              <div
                style={{
                  padding: "3rem",
                  textAlign: "center",
                  background: "var(--bg-surface)",
                  borderRadius: "0.75rem",
                  border: "1px solid var(--border-color)",
                }}
              >
                <p style={{ color: "var(--text-secondary)", margin: 0 }}>No analytics data loaded.</p>
              </div>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: "2rem" }}>
                {/* 6E-1 Catalogue Metric Cards */}
                <div
                  style={{
                    display: "grid",
                    gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))",
                    gap: "1.5rem",
                  }}
                >
                  {/* Seat Utilization */}
                  <div
                    style={{
                      background: "var(--bg-surface)",
                      borderRadius: "0.75rem",
                      padding: "1.5rem",
                      border: "1px solid var(--border-color)",
                    }}
                  >
                    <h3
                      style={{
                        margin: "0 0 0.5rem 0",
                        fontSize: "0.875rem",
                        textTransform: "uppercase",
                        letterSpacing: "0.05em",
                        color: "var(--text-secondary)",
                      }}
                    >
                      Global Seat Utilization
                    </h3>
                    <div style={{ fontSize: "2rem", fontWeight: 700, color: "var(--text-primary)", marginBottom: "0.25rem" }}>
                      {analyticsData.seat_utilization.total_active_seats} Seats
                    </div>
                    <p style={{ margin: 0, fontSize: "0.8125rem", color: "var(--text-secondary)" }}>
                      Across {analyticsData.seat_utilization.active_tenants} active tenant organizations
                    </p>
                  </div>

                  {/* SSO Launch Activity (Distinguishing Issued vs Validated) */}
                  <div
                    style={{
                      background: "var(--bg-surface)",
                      borderRadius: "0.75rem",
                      padding: "1.5rem",
                      border: "1px solid var(--border-color)",
                    }}
                  >
                    <h3
                      style={{
                        margin: "0 0 0.5rem 0",
                        fontSize: "0.875rem",
                        textTransform: "uppercase",
                        letterSpacing: "0.05em",
                        color: "var(--text-secondary)",
                      }}
                    >
                      SSO Launch Activity
                    </h3>
                    <div style={{ fontSize: "2rem", fontWeight: 700, color: "var(--text-primary)", marginBottom: "0.25rem" }}>
                      {analyticsData.sso_launch_activity.codes_validated} <span style={{ fontSize: "1rem", fontWeight: 500, color: "var(--text-secondary)" }}>exchanged</span>
                    </div>
                    <div style={{ fontSize: "0.8125rem", color: "var(--text-secondary)" }}>
                      <span>
                        Codes exchanged: <strong style={{ color: "var(--text-primary)" }}>{analyticsData.sso_launch_activity.codes_validated}</strong> | Codes issued: <strong style={{ color: "var(--text-primary)" }}>{analyticsData.sso_launch_activity.codes_issued}</strong> in window
                      </span>
                    </div>

                  </div>

                  {/* Integration Health Distribution */}
                  <div
                    style={{
                      background: "var(--bg-surface)",
                      borderRadius: "0.75rem",
                      padding: "1.5rem",
                      border: "1px solid var(--border-color)",
                    }}
                  >
                    <h3
                      style={{
                        margin: "0 0 0.5rem 0",
                        fontSize: "0.875rem",
                        textTransform: "uppercase",
                        letterSpacing: "0.05em",
                        color: "var(--text-secondary)",
                      }}
                    >
                      Integration Health Trend
                    </h3>
                    <div style={{ display: "flex", gap: "1rem", marginTop: "0.75rem" }}>
                      <div>
                        <div style={{ fontSize: "1.5rem", fontWeight: 700, color: "#34d399" }}>
                          {analyticsData.integration_health_distribution.healthy}
                        </div>
                        <div style={{ fontSize: "0.75rem", color: "var(--text-secondary)" }}>Healthy</div>
                      </div>
                      <div>
                        <div style={{ fontSize: "1.5rem", fontWeight: 700, color: "#fbbf24" }}>
                          {analyticsData.integration_health_distribution.degraded}
                        </div>
                        <div style={{ fontSize: "0.75rem", color: "var(--text-secondary)" }}>Degraded</div>
                      </div>
                      <div>
                        <div style={{ fontSize: "1.5rem", fontWeight: 700, color: "#f87171" }}>
                          {analyticsData.integration_health_distribution.unhealthy}
                        </div>
                        <div style={{ fontSize: "0.75rem", color: "var(--text-secondary)" }}>Unhealthy</div>
                      </div>
                    </div>
                    <div style={{ marginTop: "0.5rem", fontSize: "0.75rem", color: "var(--text-secondary)" }}>
                      Component-level evaluation across active tenants
                    </div>
                  </div>

                  {/* Impersonation & Support Activity */}
                  <div
                    style={{
                      background: "var(--bg-surface)",
                      borderRadius: "0.75rem",
                      padding: "1.5rem",
                      border: "1px solid var(--border-color)",
                    }}
                  >
                    <h3
                      style={{
                        margin: "0 0 0.5rem 0",
                        fontSize: "0.875rem",
                        textTransform: "uppercase",
                        letterSpacing: "0.05em",
                        color: "var(--text-secondary)",
                      }}
                    >
                      Impersonation Governance
                    </h3>
                    <div style={{ fontSize: "2rem", fontWeight: 700, color: "var(--text-primary)", marginBottom: "0.25rem" }}>
                      {analyticsData.impersonation_metrics.total_sessions} Sessions
                    </div>
                    <div style={{ fontSize: "0.8125rem", color: "var(--text-secondary)" }}>
                      {analyticsData.impersonation_metrics.total_sessions === 0 ? (
                        <span>No support sessions initiated in window</span>
                      ) : (
                        <span>
                          Avg duration: <strong>{analyticsData.impersonation_metrics.average_duration_seconds}s</strong>
                        </span>
                      )}
                    </div>
                  </div>
                </div>

                {/* Detailed Product Adoption Breakdown */}
                <div
                  style={{
                    background: "var(--bg-surface)",
                    borderRadius: "0.75rem",
                    border: "1px solid var(--border-color)",
                    overflow: "hidden",
                  }}
                >
                  <div style={{ padding: "1.25rem 1.5rem", borderBottom: "1px solid var(--border-color)" }}>
                    <h2 style={{ margin: 0, fontSize: "1.125rem", color: "var(--text-primary)" }}>
                      Product Adoption & User Assignments
                    </h2>
                  </div>

                  {analyticsData.product_adoption.length === 0 ? (
                    <div style={{ padding: "2rem", textAlign: "center", color: "var(--text-secondary)" }}>
                      No product adoption records found.
                    </div>
                  ) : (
                    <table style={{ width: "100%", borderCollapse: "collapse", textAlign: "left" }}>
                      <thead>
                        <tr style={{ borderBottom: "1px solid var(--border-color)", background: "rgba(255,255,255,0.02)" }}>
                          <th style={{ padding: "0.75rem 1.5rem", fontSize: "0.8125rem", color: "var(--text-secondary)" }}>
                            PRODUCT NAME
                          </th>
                          <th style={{ padding: "0.75rem 1.5rem", fontSize: "0.8125rem", color: "var(--text-secondary)" }}>
                            CODE
                          </th>
                          <th style={{ padding: "0.75rem 1.5rem", fontSize: "0.8125rem", color: "var(--text-secondary)", textAlign: "right" }}>
                            ENTITLED TENANTS
                          </th>
                          <th style={{ padding: "0.75rem 1.5rem", fontSize: "0.8125rem", color: "var(--text-secondary)", textAlign: "right" }}>
                            ASSIGNED USERS
                          </th>
                        </tr>
                      </thead>
                      <tbody>
                        {analyticsData.product_adoption.map((p) => (
                          <tr key={p.product_id} style={{ borderBottom: "1px solid var(--border-color)" }}>
                            <td style={{ padding: "1rem 1.5rem", fontWeight: 600, color: "var(--text-primary)" }}>
                              {p.product_name}
                            </td>
                            <td style={{ padding: "1rem 1.5rem", fontSize: "0.875rem", color: "var(--text-secondary)", fontFamily: "monospace" }}>
                              {p.product_code}
                            </td>
                            <td style={{ padding: "1rem 1.5rem", textAlign: "right", fontWeight: 600, color: "var(--text-primary)" }}>
                              <span
                                style={{
                                  display: "inline-block",
                                  padding: "0.25rem 0.625rem",
                                  borderRadius: "9999px",
                                  fontSize: "0.8125rem",
                                  background: "rgba(59, 130, 246, 0.15)",
                                  color: "#60a5fa",
                                }}
                              >
                                {p.entitled_tenants}
                              </span>
                            </td>
                            <td style={{ padding: "1rem 1.5rem", textAlign: "right", fontWeight: 600, color: "var(--text-primary)" }}>
                              <span
                                style={{
                                  display: "inline-block",
                                  padding: "0.25rem 0.625rem",
                                  borderRadius: "9999px",
                                  fontSize: "0.8125rem",
                                  background: "rgba(16, 185, 129, 0.15)",
                                  color: "#34d399",
                                }}
                              >
                                {p.assigned_users}
                              </span>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </AppShell>
  );
};
