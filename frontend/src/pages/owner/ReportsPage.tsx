/**
 * Platform Owner Reports & Analytics Page (Phase 4F & 6E).
 *
 * Route: /reports
 * Context Guard: platform_owner
 */

import React, { useState, useEffect } from "react";
import { Link } from "react-router-dom";
import { AppShell } from "../../components/AppShell.tsx";
import { LoadingSpinner } from "../../components/LoadingSpinner.tsx";
import {
  reportsApi,
  type OwnerReportsSummary,
  type OwnerAnalyticsResponse,
} from "../../api/reports.ts";
import {
  SlidersIcon,
  BuildingIcon,
  CreditCardIcon,
  LayersIcon,
} from "../../components/Icons.tsx";

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
        {/* Breadcrumbs */}
        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", fontSize: "0.8125rem", color: "var(--text-muted)", marginBottom: "1.25rem", fontWeight: 500 }}>
          <Link to="/" style={{ color: "var(--text-muted)", textDecoration: "none", transition: "color 0.15s" }}>Platform Owner</Link>
          <span>/</span>
          <span>Overview</span>
          <span>/</span>
          <span style={{ color: "var(--brand-primary)", fontWeight: 600 }}>Reports & Analytics</span>
        </div>

        {/* Header */}
        <div style={{ display: "flex", alignItems: "center", gap: "1rem", marginBottom: "2rem" }}>
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
            <SlidersIcon size={24} />
          </div>
          <div>
            <h1
              className="heading-hero"
              style={{ fontSize: "1.75rem", margin: "0 0 0.25rem 0", color: "var(--text-primary)", fontWeight: 800, letterSpacing: "-0.02em" }}
            >
              Platform Reports & Analytics
            </h1>
            <p style={{ margin: 0, color: "var(--text-secondary)", fontSize: "0.9375rem" }}>
              Cross-tenant aggregate telemetry across organizations, product adoptions, usage volume, and verified 6E analytics metrics.
            </p>
          </div>
        </div>

        {/* Tab Navigation */}
        <div
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: "0.375rem",
            background: "var(--glass-surface-elevated)",
            padding: "0.375rem",
            borderRadius: "12px",
            border: "1px solid var(--border-glass)",
            marginBottom: "2rem",
          }}
        >
          <button
            type="button"
            onClick={() => setActiveTab("summary")}
            style={{
              padding: "0.55rem 1.25rem",
              borderRadius: "8px",
              border: "none",
              background: activeTab === "summary" ? "linear-gradient(135deg, #3867f5 0%, #2952cc 100%)" : "transparent",
              color: activeTab === "summary" ? "#ffffff" : "var(--text-secondary)",
              fontWeight: 600,
              cursor: "pointer",
              fontSize: "0.875rem",
              boxShadow: activeTab === "summary" ? "0 4px 12px rgba(56, 103, 245, 0.25)" : "none",
              transition: "all 0.15s ease",
            }}
          >
            Platform Overview
          </button>
          <button
            type="button"
            onClick={() => setActiveTab("analytics")}
            style={{
              padding: "0.55rem 1.25rem",
              borderRadius: "8px",
              border: "none",
              background: activeTab === "analytics" ? "linear-gradient(135deg, #3867f5 0%, #2952cc 100%)" : "transparent",
              color: activeTab === "analytics" ? "#ffffff" : "var(--text-secondary)",
              fontWeight: 600,
              cursor: "pointer",
              fontSize: "0.875rem",
              boxShadow: activeTab === "analytics" ? "0 4px 12px rgba(56, 103, 245, 0.25)" : "none",
              transition: "all 0.15s ease",
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
                  padding: "1rem 1.25rem",
                  background: "var(--status-danger-bg)",
                  border: "1px solid var(--status-danger-border)",
                  borderRadius: "10px",
                  color: "var(--status-danger)",
                  marginBottom: "1.5rem",
                  fontSize: "0.875rem",
                  fontWeight: 500,
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
                  background: "var(--glass-surface-elevated)",
                  borderRadius: "14px",
                  border: "1px solid var(--border-glass)",
                  boxShadow: "var(--shadow-sm)",
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
                      background: "var(--glass-surface-elevated)",
                      borderRadius: "14px",
                      padding: "1.5rem",
                      border: "1px solid var(--border-glass)",
                      boxShadow: "var(--shadow-sm)",
                      position: "relative",
                      overflow: "hidden",
                      display: "flex",
                      flexDirection: "column",
                      justifyContent: "space-between",
                    }}
                  >
                    <div
                      style={{
                        position: "absolute",
                        top: 0,
                        left: 0,
                        right: 0,
                        height: "3px",
                        background: "linear-gradient(90deg, #3867f5 0%, #18a6e8 100%)",
                      }}
                    />
                    <div>
                      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "0.875rem" }}>
                        <span
                          style={{
                            fontSize: "0.75rem",
                            fontWeight: 700,
                            textTransform: "uppercase",
                            letterSpacing: "0.06em",
                            color: "var(--text-secondary)",
                          }}
                        >
                          Organizations
                        </span>
                        <div
                          style={{
                            width: "32px",
                            height: "32px",
                            borderRadius: "8px",
                            background: "var(--surface-soft-blue)",
                            color: "var(--brand-primary)",
                            display: "flex",
                            alignItems: "center",
                            justifyContent: "center",
                          }}
                        >
                          <BuildingIcon size={16} />
                        </div>
                      </div>
                      <div
                        style={{
                          fontSize: "2.5rem",
                          fontWeight: 800,
                          color: "var(--text-primary)",
                          letterSpacing: "-0.03em",
                          lineHeight: 1.1,
                          marginBottom: "1rem",
                        }}
                      >
                        {data.organizations.total}
                      </div>
                    </div>
                    <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem", fontSize: "0.8125rem" }}>
                      <span
                        style={{
                          display: "inline-flex",
                          alignItems: "center",
                          gap: "0.375rem",
                          padding: "0.25rem 0.625rem",
                          borderRadius: "9999px",
                          background: "var(--status-success-bg)",
                          color: "var(--status-success)",
                          border: "1px solid var(--status-success-border)",
                          fontWeight: 600,
                        }}
                      >
                        ● {data.organizations.active} active
                      </span>
                      <span
                        style={{
                          display: "inline-flex",
                          alignItems: "center",
                          gap: "0.375rem",
                          padding: "0.25rem 0.625rem",
                          borderRadius: "9999px",
                          background: "var(--glass-surface-sunken)",
                          color: "var(--text-secondary)",
                          border: "1px solid var(--border-subtle)",
                          fontWeight: 500,
                        }}
                      >
                        {data.organizations.inactive} inactive
                      </span>
                    </div>
                  </div>

                  {/* Commercial Health */}
                  <div
                    style={{
                      background: "var(--glass-surface-elevated)",
                      borderRadius: "14px",
                      padding: "1.5rem",
                      border: "1px solid var(--border-glass)",
                      boxShadow: "var(--shadow-sm)",
                      position: "relative",
                      overflow: "hidden",
                      display: "flex",
                      flexDirection: "column",
                      justifyContent: "space-between",
                    }}
                  >
                    <div
                      style={{
                        position: "absolute",
                        top: 0,
                        left: 0,
                        right: 0,
                        height: "3px",
                        background: "linear-gradient(90deg, #6656e8 0%, #9b4dff 100%)",
                      }}
                    />
                    <div>
                      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "0.875rem" }}>
                        <span
                          style={{
                            fontSize: "0.75rem",
                            fontWeight: 700,
                            textTransform: "uppercase",
                            letterSpacing: "0.06em",
                            color: "var(--text-secondary)",
                          }}
                        >
                          Active Subscriptions
                        </span>
                        <div
                          style={{
                            width: "32px",
                            height: "32px",
                            borderRadius: "8px",
                            background: "var(--surface-soft-lavender)",
                            color: "var(--brand-violet)",
                            display: "flex",
                            alignItems: "center",
                            justifyContent: "center",
                          }}
                        >
                          <CreditCardIcon size={16} />
                        </div>
                      </div>
                      <div
                        style={{
                          fontSize: "2.5rem",
                          fontWeight: 800,
                          color: "var(--text-primary)",
                          letterSpacing: "-0.03em",
                          lineHeight: 1.1,
                          marginBottom: "1rem",
                        }}
                      >
                        {data.commercial.active_subscriptions}
                      </div>
                    </div>
                    <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem", fontSize: "0.8125rem" }}>
                      <span
                        style={{
                          display: "inline-flex",
                          alignItems: "center",
                          gap: "0.375rem",
                          padding: "0.25rem 0.625rem",
                          borderRadius: "9999px",
                          background: "var(--surface-soft-blue)",
                          color: "var(--brand-primary)",
                          border: "1px solid rgba(56, 103, 245, 0.2)",
                          fontWeight: 600,
                        }}
                      >
                        Invoices: {data.commercial.total_invoices} ({data.commercial.paid_invoices} paid)
                      </span>
                      {data.commercial.open_reconciliations > 0 && (
                        <span
                          style={{
                            display: "inline-flex",
                            alignItems: "center",
                            gap: "0.375rem",
                            padding: "0.25rem 0.625rem",
                            borderRadius: "9999px",
                            background: "var(--status-warning-bg)",
                            color: "var(--status-warning)",
                            border: "1px solid var(--status-warning-border)",
                            fontWeight: 600,
                          }}
                        >
                          ⚠ {data.commercial.open_reconciliations} open issues
                        </span>
                      )}
                    </div>
                  </div>

                  {/* Ingested Usage */}
                  <div
                    style={{
                      background: "var(--glass-surface-elevated)",
                      borderRadius: "14px",
                      padding: "1.5rem",
                      border: "1px solid var(--border-glass)",
                      boxShadow: "var(--shadow-sm)",
                      position: "relative",
                      overflow: "hidden",
                      display: "flex",
                      flexDirection: "column",
                      justifyContent: "space-between",
                    }}
                  >
                    <div
                      style={{
                        position: "absolute",
                        top: 0,
                        left: 0,
                        right: 0,
                        height: "3px",
                        background: "linear-gradient(90deg, #0faf83 0%, #18a6e8 100%)",
                      }}
                    />
                    <div>
                      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "0.875rem" }}>
                        <span
                          style={{
                            fontSize: "0.75rem",
                            fontWeight: 700,
                            textTransform: "uppercase",
                            letterSpacing: "0.06em",
                            color: "var(--text-secondary)",
                          }}
                        >
                          Usage Events
                        </span>
                        <div
                          style={{
                            width: "32px",
                            height: "32px",
                            borderRadius: "8px",
                            background: "var(--surface-soft-mint)",
                            color: "var(--brand-teal)",
                            display: "flex",
                            alignItems: "center",
                            justifyContent: "center",
                          }}
                        >
                          <LayersIcon size={16} />
                        </div>
                      </div>
                      <div
                        style={{
                          fontSize: "2.5rem",
                          fontWeight: 800,
                          color: "var(--text-primary)",
                          letterSpacing: "-0.03em",
                          lineHeight: 1.1,
                          marginBottom: "1rem",
                        }}
                      >
                        {Number(data.usage.total_events).toLocaleString()}
                      </div>
                    </div>
                    <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem", fontSize: "0.8125rem" }}>
                      <span
                        style={{
                          display: "inline-flex",
                          alignItems: "center",
                          gap: "0.375rem",
                          padding: "0.25rem 0.625rem",
                          borderRadius: "9999px",
                          background: "var(--glass-surface-sunken)",
                          color: "var(--text-secondary)",
                          border: "1px solid var(--border-subtle)",
                          fontWeight: 500,
                        }}
                      >
                        Buckets: {data.usage.total_buckets}
                      </span>
                      <span
                        style={{
                          display: "inline-flex",
                          alignItems: "center",
                          gap: "0.375rem",
                          padding: "0.25rem 0.625rem",
                          borderRadius: "9999px",
                          background: data.usage.over_limit_buckets > 0 ? "var(--status-danger-bg)" : "var(--status-success-bg)",
                          color: data.usage.over_limit_buckets > 0 ? "var(--status-danger)" : "var(--status-success)",
                          border: `1px solid ${data.usage.over_limit_buckets > 0 ? "var(--status-danger-border)" : "var(--status-success-border)"}`,
                          fontWeight: 600,
                        }}
                      >
                        {data.usage.over_limit_buckets > 0 ? `⚠ ${data.usage.over_limit_buckets} Over-quota` : "✓ Within Quota"}
                      </span>
                    </div>
                  </div>
                </div>

                {/* Product Adoption Table */}
                <div
                  style={{
                    background: "var(--glass-surface-elevated)",
                    borderRadius: "14px",
                    border: "1px solid var(--border-glass)",
                    boxShadow: "var(--shadow-sm)",
                    overflow: "hidden",
                  }}
                >
                  <div
                    style={{
                      padding: "1.25rem 1.5rem",
                      borderBottom: "1px solid var(--border-glass)",
                      background: "var(--glass-surface-sunken)",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "space-between",
                      gap: "1rem",
                    }}
                  >
                    <div>
                      <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
                        <h2 style={{ margin: 0, fontSize: "1.125rem", fontWeight: 700, color: "var(--text-primary)" }}>
                          Product Adoption Across Tenants
                        </h2>
                        <span
                          style={{
                            fontSize: "0.75rem",
                            fontWeight: 600,
                            padding: "0.2rem 0.65rem",
                            borderRadius: "9999px",
                            background: "rgba(56, 103, 245, 0.1)",
                            color: "var(--brand-primary)",
                            border: "1px solid rgba(56, 103, 245, 0.2)",
                          }}
                        >
                          {data.product_adoption.length} Products
                        </span>
                      </div>
                      <p style={{ margin: "0.25rem 0 0 0", fontSize: "0.8125rem", color: "var(--text-secondary)" }}>
                        Aggregate tenant provisioning and adoption across registered catalog applications
                      </p>
                    </div>
                  </div>

                  {data.product_adoption.length === 0 ? (
                    <div style={{ padding: "3rem", textAlign: "center", color: "var(--text-secondary)" }}>
                      No catalog products found.
                    </div>
                  ) : (
                    <div style={{ overflowX: "auto" }}>
                      <table style={{ width: "100%", borderCollapse: "collapse", textAlign: "left" }}>
                        <thead>
                          <tr
                            style={{
                              borderBottom: "1px solid var(--border-glass)",
                              background: "var(--glass-surface-sunken)",
                            }}
                          >
                            <th style={{ padding: "0.875rem 1.5rem", fontSize: "0.75rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.05em", color: "var(--text-secondary)" }}>
                              Product Name
                            </th>
                            <th style={{ padding: "0.875rem 1.5rem", fontSize: "0.75rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.05em", color: "var(--text-secondary)" }}>
                              Product Code
                            </th>
                            <th style={{ padding: "0.875rem 1.5rem", fontSize: "0.75rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.05em", color: "var(--text-secondary)", textAlign: "right" }}>
                              Adopted Tenants
                            </th>
                          </tr>
                        </thead>
                        <tbody>
                          {data.product_adoption.map((prod) => (
                            <tr
                              key={prod.product_id}
                              style={{
                                borderBottom: "1px solid var(--border-glass)",
                                transition: "background 0.15s ease",
                              }}
                              onMouseEnter={(e) => {
                                e.currentTarget.style.background = "var(--glass-surface-hover)";
                              }}
                              onMouseLeave={(e) => {
                                e.currentTarget.style.background = "transparent";
                              }}
                            >
                              <td style={{ padding: "1rem 1.5rem" }}>
                                <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
                                  <div
                                    style={{
                                      width: "32px",
                                      height: "32px",
                                      borderRadius: "8px",
                                      background: "var(--surface-soft-blue)",
                                      border: "1px solid rgba(56, 103, 245, 0.2)",
                                      display: "flex",
                                      alignItems: "center",
                                      justifyContent: "center",
                                      color: "var(--brand-primary)",
                                      fontWeight: 700,
                                      fontSize: "0.875rem",
                                      flexShrink: 0,
                                    }}
                                  >
                                    {prod.product_name.charAt(0).toUpperCase()}
                                  </div>
                                  <div>
                                    <div style={{ fontWeight: 600, color: "var(--text-primary)", fontSize: "0.9375rem" }}>
                                      {prod.product_name}
                                    </div>
                                  </div>
                                </div>
                              </td>
                              <td style={{ padding: "1rem 1.5rem" }}>
                                <span
                                  style={{
                                    fontFamily: "var(--font-code, monospace)",
                                    fontSize: "0.8125rem",
                                    padding: "0.25rem 0.625rem",
                                    borderRadius: "6px",
                                    background: "var(--glass-surface-sunken)",
                                    border: "1px solid var(--border-subtle)",
                                    color: "var(--text-secondary)",
                                    fontWeight: 500,
                                  }}
                                >
                                  {prod.product_code}
                                </span>
                              </td>
                              <td style={{ padding: "1rem 1.5rem", textAlign: "right" }}>
                                <span
                                  style={{
                                    display: "inline-flex",
                                    alignItems: "center",
                                    gap: "0.375rem",
                                    padding: "0.35rem 0.85rem",
                                    borderRadius: "9999px",
                                    fontSize: "0.8125rem",
                                    fontWeight: 700,
                                    background: prod.adopted_tenants_count > 0 ? "rgba(56, 103, 245, 0.1)" : "var(--status-neutral-bg)",
                                    color: prod.adopted_tenants_count > 0 ? "var(--brand-primary)" : "var(--text-muted)",
                                    border: `1px solid ${prod.adopted_tenants_count > 0 ? "rgba(56, 103, 245, 0.25)" : "var(--border-subtle)"}`,
                                  }}
                                >
                                  {prod.adopted_tenants_count} {prod.adopted_tenants_count === 1 ? "tenant" : "tenants"}
                                </span>
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
                flexWrap: "wrap",
                gap: "1rem",
                marginBottom: "1.5rem",
                background: "var(--glass-surface-elevated)",
                padding: "1rem 1.5rem",
                borderRadius: "14px",
                border: "1px solid var(--border-glass)",
                boxShadow: "var(--shadow-sm)",
              }}
            >
              <div>
                <span style={{ fontSize: "0.875rem", color: "var(--text-secondary)", marginRight: "0.75rem" }}>
                  Query Window (Enforced Max 90 Days):
                </span>
                <span
                  style={{
                    fontWeight: 600,
                    color: "var(--text-primary)",
                    padding: "0.2rem 0.6rem",
                    borderRadius: "6px",
                    background: "var(--glass-surface-sunken)",
                    border: "1px solid var(--border-subtle)",
                    fontSize: "0.8125rem",
                  }}
                >
                  {analyticsData
                    ? `${analyticsData.time_window.start_date.split("T")[0]} to ${analyticsData.time_window.end_date.split("T")[0]} (${analyticsData.time_window.days} days)`
                    : "Loading..."}
                </span>
              </div>
              <div style={{ display: "flex", gap: "0.5rem" }}>
                {[30, 60, 90].map((d) => (
                  <button
                    key={d}
                    type="button"
                    onClick={() => handleDaysChange(d)}
                    disabled={isAnalyticsLoading}
                    style={{
                      padding: "0.45rem 0.95rem",
                      borderRadius: "8px",
                      border: daysFilter === d ? "1px solid var(--brand-primary)" : "1px solid var(--border-subtle)",
                      background: daysFilter === d ? "linear-gradient(135deg, #3867f5 0%, #2952cc 100%)" : "transparent",
                      color: daysFilter === d ? "#ffffff" : "var(--text-secondary)",
                      cursor: isAnalyticsLoading ? "not-allowed" : "pointer",
                      fontSize: "0.8125rem",
                      fontWeight: 600,
                      boxShadow: daysFilter === d ? "0 2px 8px rgba(56, 103, 245, 0.25)" : "none",
                      transition: "all 0.15s ease",
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
                  padding: "1rem 1.25rem",
                  background: "var(--status-danger-bg)",
                  border: "1px solid var(--status-danger-border)",
                  borderRadius: "10px",
                  color: "var(--status-danger)",
                  marginBottom: "1.5rem",
                  fontSize: "0.875rem",
                  fontWeight: 500,
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
                  background: "var(--glass-surface-elevated)",
                  borderRadius: "14px",
                  border: "1px solid var(--border-glass)",
                  boxShadow: "var(--shadow-sm)",
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
                      background: "var(--glass-surface-elevated)",
                      borderRadius: "14px",
                      padding: "1.5rem",
                      border: "1px solid var(--border-glass)",
                      boxShadow: "var(--shadow-sm)",
                      position: "relative",
                      overflow: "hidden",
                    }}
                  >
                    <div
                      style={{
                        position: "absolute",
                        top: 0,
                        left: 0,
                        right: 0,
                        height: "3px",
                        background: "linear-gradient(90deg, #3867f5 0%, #8a45f6 100%)",
                      }}
                    />
                    <h3
                      style={{
                        margin: "0 0 0.5rem 0",
                        fontSize: "0.75rem",
                        textTransform: "uppercase",
                        letterSpacing: "0.06em",
                        fontWeight: 700,
                        color: "var(--text-secondary)",
                      }}
                    >
                      Global Seat Utilization
                    </h3>
                    <div style={{ fontSize: "2.25rem", fontWeight: 800, color: "var(--text-primary)", letterSpacing: "-0.03em", marginBottom: "0.25rem" }}>
                      {analyticsData.seat_utilization.total_active_seats} <span style={{ fontSize: "1.125rem", fontWeight: 500, color: "var(--text-secondary)" }}>Seats</span>
                    </div>
                    <p style={{ margin: 0, fontSize: "0.8125rem", color: "var(--text-secondary)" }}>
                      Across <strong style={{ color: "var(--text-primary)" }}>{analyticsData.seat_utilization.active_tenants}</strong> active tenant organizations
                    </p>
                  </div>

                  {/* SSO Launch Activity */}
                  <div
                    style={{
                      background: "var(--glass-surface-elevated)",
                      borderRadius: "14px",
                      padding: "1.5rem",
                      border: "1px solid var(--border-glass)",
                      boxShadow: "var(--shadow-sm)",
                      position: "relative",
                      overflow: "hidden",
                    }}
                  >
                    <div
                      style={{
                        position: "absolute",
                        top: 0,
                        left: 0,
                        right: 0,
                        height: "3px",
                        background: "linear-gradient(90deg, #0faf83 0%, #18a6e8 100%)",
                      }}
                    />
                    <h3
                      style={{
                        margin: "0 0 0.5rem 0",
                        fontSize: "0.75rem",
                        textTransform: "uppercase",
                        letterSpacing: "0.06em",
                        fontWeight: 700,
                        color: "var(--text-secondary)",
                      }}
                    >
                      SSO Launch Activity
                    </h3>
                    <div style={{ fontSize: "2.25rem", fontWeight: 800, color: "var(--text-primary)", letterSpacing: "-0.03em", marginBottom: "0.25rem" }}>
                      {analyticsData.sso_launch_activity.codes_validated} <span style={{ fontSize: "1.125rem", fontWeight: 500, color: "var(--text-secondary)" }}>exchanged</span>
                    </div>
                    <div style={{ fontSize: "0.8125rem", color: "var(--text-secondary)" }}>
                      <span>
                        Codes issued: <strong style={{ color: "var(--text-primary)" }}>{analyticsData.sso_launch_activity.codes_issued}</strong> in window
                      </span>
                    </div>
                  </div>

                  {/* Integration Health Distribution */}
                  <div
                    style={{
                      background: "var(--glass-surface-elevated)",
                      borderRadius: "14px",
                      padding: "1.5rem",
                      border: "1px solid var(--border-glass)",
                      boxShadow: "var(--shadow-sm)",
                      position: "relative",
                      overflow: "hidden",
                    }}
                  >
                    <div
                      style={{
                        position: "absolute",
                        top: 0,
                        left: 0,
                        right: 0,
                        height: "3px",
                        background: "linear-gradient(90deg, #0faf83 0%, #eba52f 50%, #e65768 100%)",
                      }}
                    />
                    <h3
                      style={{
                        margin: "0 0 0.5rem 0",
                        fontSize: "0.75rem",
                        textTransform: "uppercase",
                        letterSpacing: "0.06em",
                        fontWeight: 700,
                        color: "var(--text-secondary)",
                      }}
                    >
                      Integration Health Trend
                    </h3>
                    <div style={{ display: "flex", gap: "1.25rem", marginTop: "0.75rem" }}>
                      <div>
                        <div style={{ fontSize: "1.5rem", fontWeight: 800, color: "var(--status-success)" }}>
                          {analyticsData.integration_health_distribution.healthy}
                        </div>
                        <div style={{ fontSize: "0.75rem", fontWeight: 600, color: "var(--text-secondary)" }}>Healthy</div>
                      </div>
                      <div>
                        <div style={{ fontSize: "1.5rem", fontWeight: 800, color: "var(--status-warning)" }}>
                          {analyticsData.integration_health_distribution.degraded}
                        </div>
                        <div style={{ fontSize: "0.75rem", fontWeight: 600, color: "var(--text-secondary)" }}>Degraded</div>
                      </div>
                      <div>
                        <div style={{ fontSize: "1.5rem", fontWeight: 800, color: "var(--status-danger)" }}>
                          {analyticsData.integration_health_distribution.unhealthy}
                        </div>
                        <div style={{ fontSize: "0.75rem", fontWeight: 600, color: "var(--text-secondary)" }}>Unhealthy</div>
                      </div>
                    </div>
                    <div style={{ marginTop: "0.5rem", fontSize: "0.75rem", color: "var(--text-muted)" }}>
                      Component-level evaluation across active tenants
                    </div>
                  </div>

                  {/* Impersonation & Support Activity */}
                  <div
                    style={{
                      background: "var(--glass-surface-elevated)",
                      borderRadius: "14px",
                      padding: "1.5rem",
                      border: "1px solid var(--border-glass)",
                      boxShadow: "var(--shadow-sm)",
                      position: "relative",
                      overflow: "hidden",
                    }}
                  >
                    <div
                      style={{
                        position: "absolute",
                        top: 0,
                        left: 0,
                        right: 0,
                        height: "3px",
                        background: "linear-gradient(90deg, #6656e8 0%, #18a6e8 100%)",
                      }}
                    />
                    <h3
                      style={{
                        margin: "0 0 0.5rem 0",
                        fontSize: "0.75rem",
                        textTransform: "uppercase",
                        letterSpacing: "0.06em",
                        fontWeight: 700,
                        color: "var(--text-secondary)",
                      }}
                    >
                      Impersonation Governance
                    </h3>
                    <div style={{ fontSize: "2.25rem", fontWeight: 800, color: "var(--text-primary)", letterSpacing: "-0.03em", marginBottom: "0.25rem" }}>
                      {analyticsData.impersonation_metrics.total_sessions} <span style={{ fontSize: "1.125rem", fontWeight: 500, color: "var(--text-secondary)" }}>Sessions</span>
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
                    background: "var(--glass-surface-elevated)",
                    borderRadius: "14px",
                    border: "1px solid var(--border-glass)",
                    boxShadow: "var(--shadow-sm)",
                    overflow: "hidden",
                  }}
                >
                  <div
                    style={{
                      padding: "1.25rem 1.5rem",
                      borderBottom: "1px solid var(--border-glass)",
                      background: "var(--glass-surface-sunken)",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "space-between",
                      gap: "1rem",
                    }}
                  >
                    <div>
                      <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
                        <h2 style={{ margin: 0, fontSize: "1.125rem", fontWeight: 700, color: "var(--text-primary)" }}>
                          Product Adoption & User Assignments
                        </h2>
                        <span
                          style={{
                            fontSize: "0.75rem",
                            fontWeight: 600,
                            padding: "0.2rem 0.65rem",
                            borderRadius: "9999px",
                            background: "rgba(56, 103, 245, 0.1)",
                            color: "var(--brand-primary)",
                            border: "1px solid rgba(56, 103, 245, 0.2)",
                          }}
                        >
                          {analyticsData.product_adoption.length} Products
                        </span>
                      </div>
                      <p style={{ margin: "0.25rem 0 0 0", fontSize: "0.8125rem", color: "var(--text-secondary)" }}>
                        Entitled tenant organizations and granular assigned user quotas
                      </p>
                    </div>
                  </div>

                  {analyticsData.product_adoption.length === 0 ? (
                    <div style={{ padding: "3rem", textAlign: "center", color: "var(--text-secondary)" }}>
                      No product adoption records found.
                    </div>
                  ) : (
                    <div style={{ overflowX: "auto" }}>
                      <table style={{ width: "100%", borderCollapse: "collapse", textAlign: "left" }}>
                        <thead>
                          <tr
                            style={{
                              borderBottom: "1px solid var(--border-glass)",
                              background: "var(--glass-surface-sunken)",
                            }}
                          >
                            <th style={{ padding: "0.875rem 1.5rem", fontSize: "0.75rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.05em", color: "var(--text-secondary)" }}>
                              Product Name
                            </th>
                            <th style={{ padding: "0.875rem 1.5rem", fontSize: "0.75rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.05em", color: "var(--text-secondary)" }}>
                              Product Code
                            </th>
                            <th style={{ padding: "0.875rem 1.5rem", fontSize: "0.75rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.05em", color: "var(--text-secondary)", textAlign: "right" }}>
                              Entitled Tenants
                            </th>
                            <th style={{ padding: "0.875rem 1.5rem", fontSize: "0.75rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.05em", color: "var(--text-secondary)", textAlign: "right" }}>
                              Assigned Users
                            </th>
                          </tr>
                        </thead>
                        <tbody>
                          {analyticsData.product_adoption.map((p) => (
                            <tr
                              key={p.product_id}
                              style={{
                                borderBottom: "1px solid var(--border-glass)",
                                transition: "background 0.15s ease",
                              }}
                              onMouseEnter={(e) => {
                                e.currentTarget.style.background = "var(--glass-surface-hover)";
                              }}
                              onMouseLeave={(e) => {
                                e.currentTarget.style.background = "transparent";
                              }}
                            >
                              <td style={{ padding: "1rem 1.5rem" }}>
                                <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
                                  <div
                                    style={{
                                      width: "32px",
                                      height: "32px",
                                      borderRadius: "8px",
                                      background: "var(--surface-soft-blue)",
                                      border: "1px solid rgba(56, 103, 245, 0.2)",
                                      display: "flex",
                                      alignItems: "center",
                                      justifyContent: "center",
                                      color: "var(--brand-primary)",
                                      fontWeight: 700,
                                      fontSize: "0.875rem",
                                      flexShrink: 0,
                                    }}
                                  >
                                    {p.product_name.charAt(0).toUpperCase()}
                                  </div>
                                  <div>
                                    <div style={{ fontWeight: 600, color: "var(--text-primary)", fontSize: "0.9375rem" }}>
                                      {p.product_name}
                                    </div>
                                  </div>
                                </div>
                              </td>
                              <td style={{ padding: "1rem 1.5rem" }}>
                                <span
                                  style={{
                                    fontFamily: "var(--font-code, monospace)",
                                    fontSize: "0.8125rem",
                                    padding: "0.25rem 0.625rem",
                                    borderRadius: "6px",
                                    background: "var(--glass-surface-sunken)",
                                    border: "1px solid var(--border-subtle)",
                                    color: "var(--text-secondary)",
                                    fontWeight: 500,
                                  }}
                                >
                                  {p.product_code}
                                </span>
                              </td>
                              <td style={{ padding: "1rem 1.5rem", textAlign: "right" }}>
                                <span
                                  style={{
                                    display: "inline-flex",
                                    alignItems: "center",
                                    gap: "0.375rem",
                                    padding: "0.35rem 0.85rem",
                                    borderRadius: "9999px",
                                    fontSize: "0.8125rem",
                                    fontWeight: 700,
                                    background: "rgba(56, 103, 245, 0.1)",
                                    color: "var(--brand-primary)",
                                    border: "1px solid rgba(56, 103, 245, 0.25)",
                                  }}
                                >
                                  {p.entitled_tenants}
                                </span>
                              </td>
                              <td style={{ padding: "1rem 1.5rem", textAlign: "right" }}>
                                <span
                                  style={{
                                    display: "inline-flex",
                                    alignItems: "center",
                                    gap: "0.375rem",
                                    padding: "0.35rem 0.85rem",
                                    borderRadius: "9999px",
                                    fontSize: "0.8125rem",
                                    fontWeight: 700,
                                    background: "var(--status-success-bg)",
                                    color: "var(--status-success)",
                                    border: "1px solid var(--status-success-border)",
                                  }}
                                >
                                  {Number(p.assigned_users).toLocaleString()}
                                </span>
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
        )}
      </div>
    </AppShell>
  );
};
