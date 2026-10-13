/**
 * Tenant Dashboard Page (Phase 2G).
 *
 * Authoritative Tenant Console Dashboard:
 * - Powered exclusively by GET /api/v1/tenant/home/ via tenantHomeApi
 * - Displays active organization status, membership authority, seat allocation pools,
 *   entitled products, and real operational alerts (zero mock metrics).
 * - Tenant context switch resets state via generation-counter pattern.
 * - Fully responsive down to 320px, theme-aware using CSS tokens only.
 */

import React, { useState, useEffect, useRef, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../../context/AuthContext.tsx";
import { AppShell } from "../../components/AppShell.tsx";
import { tenantHomeApi } from "../../api/tenantHome.ts";
import type { TenantHomeResponse } from "../../api/types.ts";
import { usageApi, type TenantUsageSummary } from "../../api/usage.ts";
import { LoadingSpinner } from "../../components/LoadingSpinner.tsx";
import {
  LayersIcon,
  RotateCcwIcon,
  ShieldCheckIcon,
  UploadIcon,
  UserIcon,
  BoxIcon,
} from "../../components/Icons.tsx";

export const TenantDashboardPage: React.FC = () => {
  const { user } = useAuth();
  const navigate = useNavigate();

  const [homeData, setHomeData] = useState<TenantHomeResponse | null>(null);
  const [usageData, setUsageData] = useState<TenantUsageSummary | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // Generation counter to handle tenant context switches safely
  const generationRef = useRef(0);
  const currentTenantId = user?.active_context?.organization?.id;
  const lastTenantIdRef = useRef<string | undefined>(currentTenantId);
  const hasMultipleContexts = (user?.available_contexts?.length || 0) > 1;

  const fetchTenantHome = useCallback(async () => {
    const currentGen = ++generationRef.current;
    setIsLoading(true);
    setErrorMessage(null);

    try {
      const data = await tenantHomeApi.getTenantHome();
      if (currentGen === generationRef.current) {
        setHomeData(data);
        setIsLoading(false);
      }
    } catch (err: unknown) {
      if (currentGen === generationRef.current) {
        const errorDetail =
          err && typeof err === "object" && "message" in err
            ? String((err as { message: string }).message)
            : "Failed to load tenant dashboard data.";
        setErrorMessage(errorDetail);
        setIsLoading(false);
      }
    }

    try {
      const usage = await usageApi.getTenantUsageSummary();
      if (currentGen === generationRef.current) {
        setUsageData(usage);
      }
    } catch {
      // Graceful non-blocking fallback if usage.view permission is not held or no usage recorded
    }
  }, []);

  // Tenant switch reset trigger
  useEffect(() => {
    if (lastTenantIdRef.current !== currentTenantId) {
      lastTenantIdRef.current = currentTenantId;
      setHomeData(null);
      setUsageData(null);
      void fetchTenantHome();
    }
  }, [currentTenantId, fetchTenantHome]);

  // Initial load
  useEffect(() => {
    void fetchTenantHome();
  }, [fetchTenantHome]);

  const organization = homeData?.organization ?? user?.active_context?.organization;
  const orgStatus = homeData?.organization?.status ?? "active";
  const membership = homeData?.membership;
  const seatSummary = homeData?.seat_summary;
  const entitledProducts = homeData?.entitled_products ?? [];
  const allProducts = homeData?.products ?? entitledProducts;

  // Real data-driven alerts
  const inactiveSubProducts = allProducts.filter(
    (p) => p.access_state === "subscription_inactive"
  );
  const suspendedAssignments = allProducts.filter(
    (p) => p.access_state === "assignment_suspended"
  );
  const exhaustedSeatPools = (seatSummary?.products ?? []).filter(
    (p) => p.is_capacity_available === false
  );
  const hasAlerts =
    inactiveSubProducts.length > 0 ||
    suspendedAssignments.length > 0 ||
    exhaustedSeatPools.length > 0;

  return (
    <AppShell>
      <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem", minWidth: 0 }}>
        {/* Top Header Card */}
        <div
          style={{
            background: "var(--glass-surface-elevated)",
            border: "1px solid var(--border-glass)",
            borderRadius: "14px",
            padding: "1.75rem",
            boxShadow: "var(--shadow-sm)",
            display: "flex",
            flexDirection: "column",
            gap: "1.25rem",
          }}
        >
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "flex-start",
              gap: "1rem",
              flexWrap: "wrap",
            }}
          >
            <div>
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "0.625rem",
                  marginBottom: "0.5rem",
                  flexWrap: "wrap",
                }}
              >
                <span
                  style={{
                    display: "inline-flex",
                    alignItems: "center",
                    gap: "0.35rem",
                    fontSize: "0.8125rem",
                    fontWeight: 600,
                    padding: "0.2rem 0.6rem",
                    borderRadius: "6px",
                    background: "rgba(99, 102, 241, 0.12)",
                    color: "rgb(99, 102, 241)",
                    border: "1px solid rgba(99, 102, 241, 0.25)",
                  }}
                >
                  <ShieldCheckIcon size={14} />
                  Tenant Admin Dashboard
                </span>

                {organization?.code && (
                  <span className="product-code-pill" style={{ fontSize: "0.8125rem" }}>
                    {organization.code}
                  </span>
                )}

                <span
                  style={{
                    display: "inline-flex",
                    alignItems: "center",
                    gap: "0.25rem",
                    fontSize: "0.75rem",
                    fontWeight: 600,
                    padding: "0.2rem 0.5rem",
                    borderRadius: "4px",
                    background:
                      orgStatus === "active"
                        ? "var(--status-success-bg)"
                        : "var(--status-warning-bg)",
                    color:
                      orgStatus === "active"
                        ? "var(--status-success)"
                        : "var(--status-warning)",
                    border: `1px solid ${
                      orgStatus === "active"
                        ? "var(--status-success-border)"
                        : "var(--status-warning-border)"
                    }`,
                    textTransform: "uppercase",
                  }}
                >
                  {orgStatus}
                </span>
              </div>

              <h1
                className="heading-hero"
                style={{
                  fontSize: "1.625rem",
                  margin: 0,
                  overflowWrap: "anywhere",
                  wordBreak: "break-word",
                }}
              >
                {organization?.name || "Organization Workspace"}
              </h1>
              <p
                className="text-body"
                style={{
                  marginTop: "0.35rem",
                  fontSize: "0.875rem",
                  color: "var(--text-secondary)",
                  overflowWrap: "anywhere",
                  wordBreak: "break-word",
                }}
              >
                Authenticated as{" "}
                <strong style={{ overflowWrap: "anywhere", wordBreak: "break-all" }}>
                  {user?.email}
                </strong>{" "}
                ({membership?.role?.name || "Tenant Administrator"}).
              </p>
            </div>

            {hasMultipleContexts && (
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                onClick={() => navigate("/select-context")}
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  gap: "0.4rem",
                  minHeight: "44px",
                }}
              >
                <RotateCcwIcon size={14} />
                <span>Switch Organization</span>
              </button>
            )}
          </div>
        </div>

        {/* Loading / Error States */}
        {isLoading && (
          <div
            style={{
              padding: "3rem",
              display: "flex",
              justifyContent: "center",
              alignItems: "center",
            }}
          >
            <LoadingSpinner label="Loading tenant dashboard..." />
          </div>
        )}

        {errorMessage && (
          <div
            role="alert"
            style={{
              padding: "1.25rem",
              borderRadius: "10px",
              background: "var(--status-danger-bg)",
              border: "1px solid var(--status-danger-border)",
              color: "var(--status-danger)",
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              gap: "1rem",
              flexWrap: "wrap",
            }}
          >
            <div>
              <strong style={{ display: "block", marginBottom: "0.25rem" }}>
                Error Loading Dashboard
              </strong>
              <span>{errorMessage}</span>
            </div>
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              onClick={() => void fetchTenantHome()}
            >
              Retry
            </button>
          </div>
        )}

        {!isLoading && !errorMessage && (
          <>
            {/* Real KPI Metrics Grid */}
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
                gap: "1rem",
                width: "100%",
              }}
            >
              {/* Card 1: Entitled Products */}
              <div
                style={{
                  background: "var(--glass-surface-elevated)",
                  border: "1px solid var(--border-glass)",
                  borderRadius: "12px",
                  padding: "1.25rem",
                  display: "flex",
                  flexDirection: "column",
                  gap: "0.5rem",
                }}
              >
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                  <span className="text-caption" style={{ color: "var(--text-secondary)", fontWeight: 600 }}>
                    Entitled Products
                  </span>
                  <div
                    style={{
                      width: "36px",
                      height: "36px",
                      borderRadius: "8px",
                      background: "rgba(99, 102, 241, 0.1)",
                      color: "rgb(99, 102, 241)",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                    }}
                  >
                    <BoxIcon size={18} />
                  </div>
                </div>
                <div style={{ fontSize: "1.75rem", fontWeight: 700, color: "var(--text-primary)" }}>
                  {entitledProducts.length}
                </div>
                <span style={{ fontSize: "0.8125rem", color: "var(--text-muted)" }}>
                  {allProducts.length} total catalog products evaluated
                </span>
              </div>

              {/* Card 2: Assigned Seats */}
              <div
                style={{
                  background: "var(--glass-surface-elevated)",
                  border: "1px solid var(--border-glass)",
                  borderRadius: "12px",
                  padding: "1.25rem",
                  display: "flex",
                  flexDirection: "column",
                  gap: "0.5rem",
                }}
              >
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                  <span className="text-caption" style={{ color: "var(--text-secondary)", fontWeight: 600 }}>
                    Assigned Seats
                  </span>
                  <div
                    style={{
                      width: "36px",
                      height: "36px",
                      borderRadius: "8px",
                      background: "var(--status-success-bg)",
                      color: "var(--status-success)",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                    }}
                  >
                    <LayersIcon size={18} />
                  </div>
                </div>
                <div style={{ fontSize: "1.75rem", fontWeight: 700, color: "var(--text-primary)" }}>
                  {seatSummary?.total_assigned_seats ?? 0}
                </div>
                <span style={{ fontSize: "0.8125rem", color: "var(--text-muted)" }}>
                  Across all active & suspended user allocations
                </span>
              </div>

              {/* Card 3: Administrative Role */}
              <div
                style={{
                  background: "var(--glass-surface-elevated)",
                  border: "1px solid var(--border-glass)",
                  borderRadius: "12px",
                  padding: "1.25rem",
                  display: "flex",
                  flexDirection: "column",
                  gap: "0.5rem",
                }}
              >
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                  <span className="text-caption" style={{ color: "var(--text-secondary)", fontWeight: 600 }}>
                    Access Role
                  </span>
                  <div
                    style={{
                      width: "36px",
                      height: "36px",
                      borderRadius: "8px",
                      background: "rgba(99, 102, 241, 0.1)",
                      color: "rgb(99, 102, 241)",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                    }}
                  >
                    <ShieldCheckIcon size={18} />
                  </div>
                </div>
                <div
                  style={{
                    fontSize: "1.25rem",
                    fontWeight: 700,
                    color: "var(--text-primary)",
                    overflowWrap: "anywhere",
                  }}
                >
                  {membership?.role?.name || "Tenant Administrator"}
                </div>
                <span style={{ fontSize: "0.8125rem", color: "var(--text-muted)" }}>
                  {membership?.role?.is_system_role ? "Built-in System Role" : "Custom Role"}
                </span>
              </div>

              {/* Card 4: Membership Status */}
              <div
                style={{
                  background: "var(--glass-surface-elevated)",
                  border: "1px solid var(--border-glass)",
                  borderRadius: "12px",
                  padding: "1.25rem",
                  display: "flex",
                  flexDirection: "column",
                  gap: "0.5rem",
                }}
              >
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                  <span className="text-caption" style={{ color: "var(--text-secondary)", fontWeight: 600 }}>
                    Membership Status
                  </span>
                  <div
                    style={{
                      width: "36px",
                      height: "36px",
                      borderRadius: "8px",
                      background: "var(--status-success-bg)",
                      color: "var(--status-success)",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                    }}
                  >
                    <UserIcon size={18} />
                  </div>
                </div>
                <div style={{ fontSize: "1.25rem", fontWeight: 700, color: "var(--text-primary)", textTransform: "capitalize" }}>
                  {membership?.status || "Active"}
                </div>
                <span style={{ fontSize: "0.8125rem", color: "var(--text-muted)" }}>
                  Type: {membership?.membership_type || "tenant_admin"}
                </span>
              </div>
            </div>

            {/* Usage & Quota Summary Card (Phase 4C) */}
            {usageData && usageData.buckets && usageData.buckets.length > 0 && (
              <div
                role="region"
                aria-label="Usage & Quota Summary"
                style={{
                  background: "var(--glass-surface-elevated)",
                  border: "1px solid var(--border-glass)",
                  borderRadius: "12px",
                  padding: "1.5rem",
                  display: "flex",
                  flexDirection: "column",
                  gap: "1.25rem",
                }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <div>
                    <h2 style={{ fontSize: "1.125rem", margin: 0, color: "var(--text-primary)" }}>
                      Usage & Quota Entitlements
                    </h2>
                    <span style={{ fontSize: "0.8125rem", color: "var(--text-muted)" }}>
                      Live consumption aggregated against active subscription limits
                    </span>
                  </div>
                  <button
                    type="button"
                    className="btn btn-secondary btn-sm"
                    onClick={() => navigate("/tenant/usage")}
                  >
                    View All Usage
                  </button>
                </div>

                <div
                  style={{
                    display: "grid",
                    gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))",
                    gap: "1rem",
                  }}
                >
                  {usageData.buckets.map((b) => {
                    const percentage = b.limit ? Math.min(Math.round((b.consumed / b.limit) * 100), 100) : 0;
                    const isOver = b.is_over_limit || (b.limit !== null && b.consumed > b.limit);
                    const progressColor = isOver
                      ? "var(--status-error)"
                      : percentage > 80
                      ? "var(--status-warning)"
                      : "var(--brand-primary)";

                    return (
                      <div
                        key={b.meter_key}
                        style={{
                          background: "rgba(255, 255, 255, 0.02)",
                          border: `1px solid ${isOver ? "var(--status-error-border)" : "var(--border-glass)"}`,
                          borderRadius: "8px",
                          padding: "1rem",
                          display: "flex",
                          flexDirection: "column",
                          gap: "0.5rem",
                        }}
                      >
                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                          <span style={{ fontWeight: 600, color: "var(--text-primary)", fontSize: "0.875rem" }}>
                            {b.meter_name}
                          </span>
                          <span
                            style={{
                              fontSize: "0.75rem",
                              fontWeight: 600,
                              color: isOver ? "var(--status-error)" : "var(--text-secondary)",
                            }}
                          >
                            {isOver ? "Over Limit" : b.limit !== null ? `${percentage}%` : "Unlimited"}
                          </span>
                        </div>
                        <div style={{ fontSize: "1.125rem", fontWeight: 700, color: "var(--text-primary)" }}>
                          {Number(b.consumed).toLocaleString()}{" "}
                          <span style={{ fontSize: "0.8125rem", fontWeight: 400, color: "var(--text-secondary)" }}>
                            / {b.limit !== null ? `${Number(b.limit).toLocaleString()} ${b.unit}` : b.unit}
                          </span>
                        </div>
                        {b.limit !== null && (
                          <div
                            style={{
                              height: "6px",
                              width: "100%",
                              borderRadius: "3px",
                              background: "rgba(255, 255, 255, 0.08)",
                              overflow: "hidden",
                            }}
                          >
                            <div
                              style={{
                                height: "100%",
                                width: `${percentage}%`,
                                background: progressColor,
                                borderRadius: "3px",
                              }}
                            />
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            {/* Operational Alerts Card (Rendered ONLY if real alert conditions exist) */}
            {hasAlerts && (
              <div
                role="region"
                aria-label="Operational Alerts"
                style={{
                  background: "var(--glass-surface-elevated)",
                  border: "1px solid var(--status-warning-border)",
                  borderRadius: "12px",
                  padding: "1.5rem",
                  display: "flex",
                  flexDirection: "column",
                  gap: "1rem",
                }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                  <span
                    style={{
                      width: "8px",
                      height: "8px",
                      borderRadius: "50%",
                      background: "var(--status-warning)",
                    }}
                  />
                  <h2 style={{ fontSize: "1rem", fontWeight: 700, margin: 0, color: "var(--text-primary)" }}>
                    Attention Required ({inactiveSubProducts.length + suspendedAssignments.length + exhaustedSeatPools.length})
                  </h2>
                </div>

                <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
                  {inactiveSubProducts.map((p) => (
                    <div
                      key={`alert-sub-${p.id}`}
                      style={{
                        padding: "0.75rem 1rem",
                        borderRadius: "8px",
                        background: "var(--status-warning-bg)",
                        border: "1px solid var(--status-warning-border)",
                        fontSize: "0.875rem",
                        color: "var(--text-primary)",
                      }}
                    >
                      <strong>{p.name}</strong> ({p.code}): Organization subscription is inactive or suspended. Product launch is paused.
                    </div>
                  ))}

                  {suspendedAssignments.map((p) => (
                    <div
                      key={`alert-assign-${p.id}`}
                      style={{
                        padding: "0.75rem 1rem",
                        borderRadius: "8px",
                        background: "var(--status-danger-bg)",
                        border: "1px solid var(--status-danger-border)",
                        fontSize: "0.875rem",
                        color: "var(--text-primary)",
                      }}
                    >
                      <strong>{p.name}</strong> ({p.code}): Your seat assignment is currently suspended.
                    </div>
                  ))}

                  {exhaustedSeatPools.map((pool) => (
                    <div
                      key={`alert-pool-${pool.product_id}`}
                      style={{
                        padding: "0.75rem 1rem",
                        borderRadius: "8px",
                        background: "var(--status-danger-bg)",
                        border: "1px solid var(--status-danger-border)",
                        fontSize: "0.875rem",
                        color: "var(--text-primary)",
                      }}
                    >
                      <strong>{pool.product_name}</strong> seat capacity reached: {pool.consumed_seats} / {pool.total_limit} seats assigned.
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Per-Product Seat Pool Capacity Table */}
            {Boolean(seatSummary?.products && seatSummary.products.length > 0) && (
              <div
                style={{
                  background: "var(--glass-surface-elevated)",
                  border: "1px solid var(--border-glass)",
                  borderRadius: "12px",
                  padding: "1.5rem",
                  display: "flex",
                  flexDirection: "column",
                  gap: "1rem",
                }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <h2 style={{ fontSize: "1.125rem", fontWeight: 700, margin: 0, color: "var(--text-primary)" }}>
                    Product Seat Capacity
                  </h2>
                  <button
                    type="button"
                    className="btn btn-secondary btn-sm"
                    onClick={() => navigate("/tenant/assignments")}
                  >
                    Manage Assignments
                  </button>
                </div>

                <div style={{ overflowX: "auto" }}>
                  <table
                    style={{
                      width: "100%",
                      borderCollapse: "collapse",
                      fontSize: "0.875rem",
                      textAlign: "left",
                    }}
                  >
                    <thead>
                      <tr style={{ borderBottom: "1px solid var(--border-subtle)" }}>
                        <th style={{ padding: "0.625rem 0.75rem", color: "var(--text-muted)", fontWeight: 600 }}>Product</th>
                        <th style={{ padding: "0.625rem 0.75rem", color: "var(--text-muted)", fontWeight: 600 }}>Pool Scope</th>
                        <th style={{ padding: "0.625rem 0.75rem", color: "var(--text-muted)", fontWeight: 600 }}>Quota Type</th>
                        <th style={{ padding: "0.625rem 0.75rem", color: "var(--text-muted)", fontWeight: 600 }}>Consumed</th>
                        <th style={{ padding: "0.625rem 0.75rem", color: "var(--text-muted)", fontWeight: 600 }}>Available</th>
                        <th style={{ padding: "0.625rem 0.75rem", color: "var(--text-muted)", fontWeight: 600 }}>Capacity</th>
                      </tr>
                    </thead>
                    <tbody>
                      {seatSummary?.products.map((p) => (
                        <tr key={p.product_id} style={{ borderBottom: "1px solid var(--border-subtle)" }}>
                          <td style={{ padding: "0.75rem", fontWeight: 600, color: "var(--text-primary)" }}>
                            {p.product_name} <span className="product-code-pill" style={{ marginLeft: "0.25rem" }}>{p.product_code}</span>
                          </td>
                          <td style={{ padding: "0.75rem", color: "var(--text-secondary)", textTransform: "capitalize" }}>
                            {p.pool_scope}
                          </td>
                          <td style={{ padding: "0.75rem", color: "var(--text-secondary)", textTransform: "capitalize" }}>
                            {p.quota_type}
                          </td>
                          <td style={{ padding: "0.75rem", fontWeight: 600, color: "var(--text-primary)" }}>
                            {p.consumed_seats}
                          </td>
                          <td style={{ padding: "0.75rem", color: "var(--text-secondary)" }}>
                            {p.available_seats !== null ? p.available_seats : "Unlimited"}
                          </td>
                          <td style={{ padding: "0.75rem" }}>
                            <span
                              style={{
                                display: "inline-flex",
                                alignItems: "center",
                                padding: "0.2rem 0.5rem",
                                borderRadius: "4px",
                                fontSize: "0.75rem",
                                fontWeight: 600,
                                background: p.is_capacity_available
                                  ? "var(--status-success-bg)"
                                  : "var(--status-danger-bg)",
                                color: p.is_capacity_available
                                  ? "var(--status-success)"
                                  : "var(--status-danger)",
                                border: `1px solid ${
                                  p.is_capacity_available
                                    ? "var(--status-success-border)"
                                    : "var(--status-danger-border)"
                                }`,
                              }}
                            >
                              {p.is_capacity_available ? "Seats Available" : "Exhausted"}
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {/* Quick Action Navigation Grid */}
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
                gap: "1rem",
                width: "100%",
                marginTop: "0.5rem",
                textAlign: "left",
              }}
            >
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => navigate("/tenant/products")}
                style={{
                  display: "flex",
                  flexDirection: "column",
                  alignItems: "flex-start",
                  padding: "1.25rem",
                  borderRadius: "10px",
                  height: "auto",
                  gap: "0.5rem",
                }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", fontWeight: 600, color: "var(--text-primary)" }}>
                  <BoxIcon size={18} />
                  <span>My Products & App Launcher</span>
                </div>
                <span style={{ fontSize: "0.8125rem", color: "var(--text-secondary)", fontWeight: 400 }}>
                  View entitled products, module trees, and launch authorized business applications.
                </span>
              </button>

              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => navigate("/tenant/assignments")}
                style={{
                  display: "flex",
                  flexDirection: "column",
                  alignItems: "flex-start",
                  padding: "1.25rem",
                  borderRadius: "10px",
                  height: "auto",
                  gap: "0.5rem",
                }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", fontWeight: 600, color: "var(--text-primary)" }}>
                  <LayersIcon size={18} />
                  <span>Product Assignments</span>
                </div>
                <span style={{ fontSize: "0.8125rem", color: "var(--text-secondary)", fontWeight: 400 }}>
                  Assign seats and entitled modules to organization users.
                </span>
              </button>

              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => navigate("/tenant/roles")}
                style={{
                  display: "flex",
                  flexDirection: "column",
                  alignItems: "flex-start",
                  padding: "1.25rem",
                  borderRadius: "10px",
                  height: "auto",
                  gap: "0.5rem",
                }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", fontWeight: 600, color: "var(--text-primary)" }}>
                  <ShieldCheckIcon size={18} />
                  <span>Roles & Permissions</span>
                </div>
                <span style={{ fontSize: "0.8125rem", color: "var(--text-secondary)", fontWeight: 400 }}>
                  Configure tenant-scoped security roles and module access policies.
                </span>
              </button>

              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => navigate("/tenant/bulk-import")}
                style={{
                  display: "flex",
                  flexDirection: "column",
                  alignItems: "flex-start",
                  padding: "1.25rem",
                  borderRadius: "10px",
                  height: "auto",
                  gap: "0.5rem",
                }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", fontWeight: 600, color: "var(--text-primary)" }}>
                  <UploadIcon size={18} />
                  <span>Bulk User Onboarding</span>
                </div>
                <span style={{ fontSize: "0.8125rem", color: "var(--text-secondary)", fontWeight: 400 }}>
                  Upload CSV/JSON rosters for staged validation and batch membership invitations.
                </span>
              </button>
            </div>
          </>
        )}
      </div>
    </AppShell>
  );
};
