/**
 * Tenant Reports & Operational Analytics Page (Phase 4F & 6E).
 *
 * Route: /tenant/reports
 * Module: tenant_reports / reports.view
 */

import React, { useState, useEffect } from "react";
import { AppShell } from "../../components/AppShell.tsx";
import { LoadingSpinner } from "../../components/LoadingSpinner.tsx";
import {
  reportsApi,
  type TenantReportsSummary,
  type TenantAnalyticsResponse,
} from "../../api/reports.ts";

export const TenantReportsPage: React.FC = () => {
  const [activeTab, setActiveTab] = useState<"summary" | "analytics">("summary");

  // Summary State
  const [data, setData] = useState<TenantReportsSummary | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // Analytics State (Phase 6E)
  const [analyticsData, setAnalyticsData] = useState<TenantAnalyticsResponse | null>(null);
  const [isAnalyticsLoading, setIsAnalyticsLoading] = useState<boolean>(false);
  const [analyticsError, setAnalyticsError] = useState<string | null>(null);
  const [daysFilter, setDaysFilter] = useState<number>(30);

  useEffect(() => {
    let isMounted = true;
    async function loadTenantReports() {
      setIsLoading(true);
      setErrorMessage(null);
      try {
        const summary = await reportsApi.getTenantSummary();
        if (isMounted) setData(summary);
      } catch (err: unknown) {
        if (isMounted) {
          const msg =
            err && typeof err === "object" && "message" in err
              ? String((err as { message: string }).message)
              : "Failed to load operational reports.";
          setErrorMessage(msg);
        }
      } finally {
        if (isMounted) setIsLoading(false);
      }
    }
    void loadTenantReports();
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

      const res = await reportsApi.getTenantAnalytics(startStr, endStr);
      setAnalyticsData(res);
    } catch (err: unknown) {
      const msg =
        err && typeof err === "object" && "message" in err
          ? String((err as { message: string }).message)
          : "Failed to load operational analytics.";
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

  const getStatusBadge = (status: "healthy" | "degraded" | "unhealthy") => {
    switch (status) {
      case "healthy":
        return {
          label: "HEALTHY",
          bg: "rgba(16, 185, 129, 0.15)",
          color: "#34d399",
          border: "1px solid rgba(16, 185, 129, 0.3)",
        };
      case "degraded":
        return {
          label: "DEGRADED",
          bg: "rgba(245, 158, 11, 0.15)",
          color: "#fbbf24",
          border: "1px solid rgba(245, 158, 11, 0.3)",
        };
      case "unhealthy":
        return {
          label: "UNHEALTHY",
          bg: "rgba(239, 68, 68, 0.15)",
          color: "#f87171",
          border: "1px solid rgba(239, 68, 68, 0.3)",
        };
    }
  };

  return (
    <AppShell>
      <div style={{ padding: "2rem", maxWidth: "1200px", margin: "0 auto" }}>
        {/* Header */}
        <div style={{ marginBottom: "1.5rem" }}>
          <h1
            className="heading-hero"
            style={{ fontSize: "1.75rem", margin: "0 0 0.5rem 0", color: "var(--text-primary)" }}
          >
            Operational Reports & Health
          </h1>
          <p style={{ margin: 0, color: "var(--text-secondary)", fontSize: "0.9375rem" }}>
            Operational telemetry for your organization: seat allocations, integration component health indicators, and adoption trends.
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
            Operational Summary
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
            Component Health & Telemetry (6E)
          </button>
        </div>

        {/* Tab 1: Operational Summary */}
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
                <LoadingSpinner fullScreen={false} label="Loading operational reports..." />
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
                <p style={{ color: "var(--text-secondary)", margin: 0 }}>No telemetry data available.</p>
              </div>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: "2rem" }}>
                {/* Overview Summary Cards */}
                <div
                  style={{
                    display: "grid",
                    gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))",
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
                        margin: "0 0 1rem 0",
                        fontSize: "0.875rem",
                        textTransform: "uppercase",
                        letterSpacing: "0.05em",
                        color: "var(--text-secondary)",
                      }}
                    >
                      Assigned Seats
                    </h3>
                    <div style={{ fontSize: "2.25rem", fontWeight: 700, color: "var(--text-primary)", marginBottom: "0.5rem" }}>
                      {data.seat_utilization.total_assigned}
                    </div>
                    <div style={{ fontSize: "0.875rem", color: "var(--text-secondary)" }}>
                      Active product entitlements currently allocated to team members
                    </div>
                  </div>

                  {/* Active Subscription */}
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
                      Subscription Plan
                    </h3>
                    {data.subscription ? (
                      <>
                        <div style={{ fontSize: "1.5rem", fontWeight: 700, color: "var(--text-primary)", marginBottom: "0.5rem" }}>
                          {data.subscription.plan_name}
                        </div>
                        <div style={{ fontSize: "0.875rem", color: "var(--text-secondary)" }}>
                          Status:{" "}
                          <strong style={{ color: data.subscription.status === "active" ? "#34d399" : "#fbbf24" }}>
                            {data.subscription.status}
                          </strong>
                          {" | "}
                          {data.subscription.currency} {data.subscription.amount} / {data.subscription.billing_interval}
                        </div>
                      </>
                    ) : (
                      <div style={{ color: "var(--text-secondary)", fontSize: "0.9375rem" }}>
                        No active subscription found.
                      </div>
                    )}
                  </div>

                  {/* Billing Invoices */}
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
                      Invoices
                    </h3>
                    <div style={{ fontSize: "2.25rem", fontWeight: 700, color: "var(--text-primary)", marginBottom: "0.5rem" }}>
                      {data.invoices.total}
                    </div>
                    <div style={{ fontSize: "0.875rem", color: "var(--text-secondary)" }}>
                      <strong style={{ color: "#34d399" }}>{data.invoices.paid}</strong> paid invoices
                    </div>
                  </div>
                </div>

                {/* Metered Usage Buckets Table */}
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
                      Current Period Metered Usage
                    </h2>
                  </div>

                  {data.usage_buckets.length === 0 ? (
                    <div style={{ padding: "2rem", textAlign: "center", color: "var(--text-secondary)" }}>
                      No metered usage recorded for the current billing cycle.
                    </div>
                  ) : (
                    <table style={{ width: "100%", borderCollapse: "collapse", textAlign: "left" }}>
                      <thead>
                        <tr style={{ borderBottom: "1px solid var(--border-color)", background: "rgba(255,255,255,0.02)" }}>
                          <th style={{ padding: "0.75rem 1.5rem", fontSize: "0.8125rem", color: "var(--text-secondary)" }}>
                            METER
                          </th>
                          <th style={{ padding: "0.75rem 1.5rem", fontSize: "0.8125rem", color: "var(--text-secondary)" }}>
                            PERIOD
                          </th>
                          <th style={{ padding: "0.75rem 1.5rem", fontSize: "0.8125rem", color: "var(--text-secondary)", textAlign: "right" }}>
                            CONSUMPTION
                          </th>
                          <th style={{ padding: "0.75rem 1.5rem", fontSize: "0.8125rem", color: "var(--text-secondary)", textAlign: "center" }}>
                            QUOTA STATUS
                          </th>
                        </tr>
                      </thead>
                      <tbody>
                        {data.usage_buckets.map((b) => (
                          <tr key={b.meter_key} style={{ borderBottom: "1px solid var(--border-color)" }}>
                            <td style={{ padding: "1rem 1.5rem", fontWeight: 600, color: "var(--text-primary)" }}>
                              {b.meter_name}
                              <div style={{ fontSize: "0.75rem", color: "var(--text-secondary)", fontFamily: "monospace" }}>
                                {b.meter_key}
                              </div>
                            </td>
                            <td style={{ padding: "1rem 1.5rem", fontSize: "0.8125rem", color: "var(--text-secondary)" }}>
                              {new Date(b.period_start).toLocaleDateString()} &ndash; {new Date(b.period_end).toLocaleDateString()}
                            </td>
                            <td style={{ padding: "1rem 1.5rem", textAlign: "right", fontWeight: 600, color: "var(--text-primary)" }}>
                              {b.consumed} {b.unit}
                            </td>
                            <td style={{ padding: "1rem 1.5rem", textAlign: "center" }}>
                              <span
                                style={{
                                  display: "inline-block",
                                  padding: "0.25rem 0.625rem",
                                  borderRadius: "9999px",
                                  fontSize: "0.75rem",
                                  fontWeight: 600,
                                  background: b.is_over_limit ? "rgba(239, 68, 68, 0.15)" : "rgba(16, 185, 129, 0.15)",
                                  color: b.is_over_limit ? "#f87171" : "#34d399",
                                }}
                              >
                                {b.is_over_limit ? "OVER LIMIT" : "NORMAL"}
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

        {/* Tab 2: Component Health & Telemetry (6E) */}
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
                <LoadingSpinner fullScreen={false} label="Loading component telemetry..." />
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
                <p style={{ color: "var(--text-secondary)", margin: 0 }}>No telemetry data available.</p>
              </div>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: "2rem" }}>
                {/* Component-Level Health Indicators Box (Reused from 6C-2 - ZERO composite score) */}
                <div
                  style={{
                    background: "var(--bg-surface)",
                    borderRadius: "0.75rem",
                    padding: "1.5rem",
                    border: "1px solid var(--border-color)",
                  }}
                >
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1.25rem" }}>
                    <div>
                      <h2 style={{ margin: 0, fontSize: "1.125rem", color: "var(--text-primary)" }}>
                        Integration Component Indicators (Transparent, Non-Composite)
                      </h2>
                      <p style={{ margin: "0.25rem 0 0 0", fontSize: "0.8125rem", color: "var(--text-secondary)" }}>
                        Direct reflection of active connections, open failures, stuck jobs, and reconciliation status.
                      </p>
                    </div>
                    {(() => {
                      const badge = getStatusBadge(analyticsData.component_health_indicators.status);
                      return (
                        <span
                          style={{
                            padding: "0.35rem 0.75rem",
                            borderRadius: "9999px",
                            fontSize: "0.8125rem",
                            fontWeight: 700,
                            background: badge.bg,
                            color: badge.color,
                            border: badge.border,
                          }}
                        >
                          {badge.label}
                        </span>
                      );
                    })()}
                  </div>

                  <div
                    style={{
                      display: "grid",
                      gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))",
                      gap: "1rem",
                      paddingTop: "0.5rem",
                    }}
                  >
                    <div style={{ padding: "0.75rem", background: "rgba(255,255,255,0.02)", borderRadius: "0.5rem" }}>
                      <div style={{ fontSize: "0.75rem", color: "var(--text-secondary)" }}>Active Connectors</div>
                      <div style={{ fontSize: "1.25rem", fontWeight: 700, color: "#34d399" }}>
                        {analyticsData.component_health_indicators.active_connectors}
                      </div>
                    </div>
                    <div style={{ padding: "0.75rem", background: "rgba(255,255,255,0.02)", borderRadius: "0.5rem" }}>
                      <div style={{ fontSize: "0.75rem", color: "var(--text-secondary)" }}>Suspended Connectors</div>
                      <div style={{ fontSize: "1.25rem", fontWeight: 700, color: analyticsData.component_health_indicators.suspended_connectors > 0 ? "#fbbf24" : "var(--text-primary)" }}>
                        {analyticsData.component_health_indicators.suspended_connectors}
                      </div>
                    </div>
                    <div style={{ padding: "0.75rem", background: "rgba(255,255,255,0.02)", borderRadius: "0.5rem" }}>
                      <div style={{ fontSize: "0.75rem", color: "var(--text-secondary)" }}>Disconnected Connectors</div>
                      <div style={{ fontSize: "1.25rem", fontWeight: 700, color: analyticsData.component_health_indicators.disconnected_connectors > 0 ? "#f87171" : "var(--text-primary)" }}>
                        {analyticsData.component_health_indicators.disconnected_connectors}
                      </div>
                    </div>
                    <div style={{ padding: "0.75rem", background: "rgba(255,255,255,0.02)", borderRadius: "0.5rem" }}>
                      <div style={{ fontSize: "0.75rem", color: "var(--text-secondary)" }}>Open Failures</div>
                      <div style={{ fontSize: "1.25rem", fontWeight: 700, color: analyticsData.component_health_indicators.open_failures > 0 ? "#fbbf24" : "var(--text-primary)" }}>
                        {analyticsData.component_health_indicators.open_failures}
                      </div>
                    </div>
                    <div style={{ padding: "0.75rem", background: "rgba(255,255,255,0.02)", borderRadius: "0.5rem" }}>
                      <div style={{ fontSize: "0.75rem", color: "var(--text-secondary)" }}>Dead Letter Queue</div>
                      <div style={{ fontSize: "1.25rem", fontWeight: 700, color: analyticsData.component_health_indicators.dead_letter_failures > 0 ? "#f87171" : "var(--text-primary)" }}>
                        {analyticsData.component_health_indicators.dead_letter_failures}
                      </div>
                    </div>
                    <div style={{ padding: "0.75rem", background: "rgba(255,255,255,0.02)", borderRadius: "0.5rem" }}>
                      <div style={{ fontSize: "0.75rem", color: "var(--text-secondary)" }}>Stuck Provisioning Jobs</div>
                      <div style={{ fontSize: "1.25rem", fontWeight: 700, color: analyticsData.component_health_indicators.stuck_jobs > 0 ? "#f87171" : "var(--text-primary)" }}>
                        {analyticsData.component_health_indicators.stuck_jobs}
                      </div>
                    </div>
                  </div>
                </div>

                {/* 6E-1 Catalogue Metric Cards */}
                <div
                  style={{
                    display: "grid",
                    gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))",
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
                      Assigned Seats
                    </h3>
                    <div style={{ fontSize: "2rem", fontWeight: 700, color: "var(--text-primary)", marginBottom: "0.25rem" }}>
                      {analyticsData.seat_utilization.assigned_seats} Seats
                    </div>
                    <div style={{ fontSize: "0.8125rem", color: "var(--text-secondary)" }}>
                      Active user-product allocations in {analyticsData.organization.name}
                    </div>
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

                  {/* Impersonation Audit Activity */}
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
                      Support Audit Access
                    </h3>
                    <div style={{ fontSize: "2rem", fontWeight: 700, color: "var(--text-primary)", marginBottom: "0.25rem" }}>
                      {analyticsData.support_activity.impersonation_sessions_in_window}
                    </div>
                    <div style={{ fontSize: "0.8125rem", color: "var(--text-secondary)" }}>
                      Support impersonation sessions touching this organization in window
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
                      Product Allocation & Entitlements
                    </h2>
                  </div>

                  {analyticsData.product_adoption.length === 0 ? (
                    <div style={{ padding: "2rem", textAlign: "center", color: "var(--text-secondary)" }}>
                      No active product entitlements configured.
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
                            ALLOCATED USERS
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
                                  background: "rgba(16, 185, 129, 0.15)",
                                  color: "#34d399",
                                }}
                              >
                                {p.assigned_users_count}
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
