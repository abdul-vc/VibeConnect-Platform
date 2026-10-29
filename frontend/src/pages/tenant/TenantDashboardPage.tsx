/**
 * Tenant Administrator Mission Control Dashboard.
 *
 * Route: /tenant
 * Context Guard: tenant (adminOnly)
 *
 * Authoritative Mission Control Dashboard for Tenant Administrators:
 * - Powered exclusively by GET /api/v1/tenant/home/ via tenantHomeApi & auditLogsApi
 * - Standardized enterprise visual hierarchy: Top Banner, 4-column KPI row,
 *   SVG Seat Allocation trend & Donut charts, Entitled Products Matrix,
 *   Administrative alerts, and Organization Activity timeline.
 * - Strictly tenant-scoped (zero cross-tenant data leakage).
 * - Theme-aware using CSS design tokens only.
 */

import React, { useState, useEffect, useRef, useCallback } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../../context/AuthContext.tsx";
import { AppShell } from "../../components/AppShell.tsx";
import { tenantHomeApi } from "../../api/tenantHome.ts";
import type { TenantHomeResponse, AuditLogListItem } from "../../api/types.ts";
import { auditApi, AUDIT_ACTION_LABELS } from "../../api/audit.ts";
import { LoadingSpinner } from "../../components/LoadingSpinner.tsx";
import {
  LayersIcon,
  RotateCcwIcon,
  ShieldCheckIcon,
  UserIcon,
  BoxIcon,
  CheckCircleIcon,
  AlertCircleIcon,
  ArrowRightIcon,
  PlusIcon,
} from "../../components/Icons.tsx";
import {
  TelemetryTrendChart,
  DonutDistributionChart,
} from "../../components/charts/MissionControlCharts.tsx";

const PRODUCT_PALETTE = [
  "#6366f1", // Indigo
  "#06b6d4", // Cyan
  "#10b981", // Emerald
  "#f59e0b", // Amber
  "#f43f5e", // Rose
  "#8b5cf6", // Purple
];

export const TenantDashboardPage: React.FC = () => {
  const { user } = useAuth();
  const navigate = useNavigate();

  const [homeData, setHomeData] = useState<TenantHomeResponse | null>(null);
  const [tenantLogs, setTenantLogs] = useState<readonly AuditLogListItem[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // Generation counter to handle tenant context switches safely
  const generationRef = useRef(0);
  const currentTenantId = user?.active_context?.organization?.id;
  const lastTenantIdRef = useRef<string | undefined>(currentTenantId);
  const hasMultipleContexts = (user?.available_contexts?.length || 0) > 1;

  const fetchTenantDashboard = useCallback(async () => {
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

    // Secondary non-blocking fetches
    try {
      const logsRes = await auditApi.listTenant({ page_size: 5, ordering: "-timestamp" }).catch(() => ({ results: [] }));
      if (currentGen === generationRef.current) {
        if (logsRes?.results) setTenantLogs(logsRes.results);
      }
    } catch {
      // Non-blocking telemetry fallback
    }
  }, []);

  // Tenant switch reset trigger
  useEffect(() => {
    if (lastTenantIdRef.current !== currentTenantId) {
      lastTenantIdRef.current = currentTenantId;
      setHomeData(null);
      setTenantLogs([]);
      void fetchTenantDashboard();
    }
  }, [currentTenantId, fetchTenantDashboard]);

  // Initial load
  useEffect(() => {
    void fetchTenantDashboard();
  }, [fetchTenantDashboard]);

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

  // Eligible modules total count
  const totalEligibleModules = entitledProducts.reduce(
    (acc, p) => acc + (p.eligible_modules?.length || 0),
    0
  );

  // Distribution chart segments for products
  const productSegments = entitledProducts.map((p, idx) => ({
    label: p.name,
    value: p.modules?.length || 1,
    color: PRODUCT_PALETTE[idx % PRODUCT_PALETTE.length],
  }));

  // Seat allocation trend
  const totalAssignedSeats = seatSummary?.total_assigned_seats ?? 0;
  const availableSeatsCount = (seatSummary?.products ?? []).reduce(
    (acc, p) => acc + (p.available_seats ?? 0),
    0
  );
  const seatTrendData = [
    { label: "Pool", value: Math.max(availableSeatsCount, 5) },
    { label: "Active", value: Math.max(totalAssignedSeats, 1) },
    { label: "Modules", value: Math.max(totalEligibleModules, 2) },
    { label: "Apps", value: Math.max(entitledProducts.length, 1) },
  ];

  return (
    <AppShell>
      <div style={{ display: "flex", flexDirection: "column", gap: "1.75rem", minWidth: 0, overflowWrap: "anywhere", paddingBottom: "2rem" }}>
        {/* Top Header Card */}
        <div
          style={{
            background: "var(--glass-surface-elevated)",
            border: "1px solid var(--border-glass)",
            borderRadius: "14px",
            padding: "1.5rem 1.75rem",
            boxShadow: "var(--shadow-sm)",
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            gap: "1.25rem",
            flexWrap: "wrap",
          }}
        >
          <div>
            <h1
              className="heading-hero"
              style={{ fontSize: "1.75rem", fontWeight: 800, margin: 0, color: "var(--text-primary)" }}
            >
              Organization Overview
            </h1>
            <p
              style={{
                margin: "0.25rem 0 0 0",
                fontSize: "0.875rem",
                color: "var(--text-secondary)",
                maxWidth: "760px",
              }}
            >
              Overview of seats, products, and activity for{" "}
              <strong style={{ color: "var(--text-primary)" }}>{organization?.name || "Organization"}</strong>.
            </p>
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", flexWrap: "wrap" }}>
            {hasMultipleContexts && (
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                onClick={() => navigate("/select-context")}
                style={{ display: "inline-flex", alignItems: "center", gap: "0.4rem", minHeight: "38px" }}
              >
                <RotateCcwIcon size={14} />
                <span>Switch Org</span>
              </button>
            )}
            {user?.active_context?.effective_permissions?.includes("roles.assign") && (
              <Link
                to="/tenant/member-onboarding"
                className="btn btn-secondary btn-sm"
                style={{ display: "inline-flex", alignItems: "center", gap: "0.4rem", minHeight: "38px", textDecoration: "none" }}
              >
                <PlusIcon size={14} />
                <span>Member Onboarding</span>
              </Link>
            )}
            <Link
              to="/tenant/users"
              className="btn btn-secondary btn-sm"
              style={{ display: "inline-flex", alignItems: "center", gap: "0.4rem", minHeight: "38px", textDecoration: "none" }}
            >
              <UserIcon size={14} />
              <span>Manage Users</span>
            </Link>
            <Link
              to="/tenant/products"
              className="btn btn-primary btn-sm"
              style={{ display: "inline-flex", alignItems: "center", gap: "0.4rem", minHeight: "38px", textDecoration: "none" }}
            >
              <BoxIcon size={14} />
              <span>App Launcher</span>
            </Link>
          </div>
        </div>

        {/* Loading Spinner */}
        {isLoading && (
          <div style={{ padding: "4rem", display: "flex", justifyContent: "center" }}>
            <LoadingSpinner label="Loading tenant dashboard telemetry..." />
          </div>
        )}

        {/* Error Alert */}
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
              <strong style={{ display: "block", marginBottom: "0.25rem" }}>Error Loading Dashboard</strong>
              <span>{errorMessage}</span>
            </div>
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              onClick={() => void fetchTenantDashboard()}
            >
              Retry
            </button>
          </div>
        )}

        {!isLoading && !errorMessage && (
          <>
            {/* Real KPI Metrics Grid (4 Columns) */}
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))",
                gap: "1.25rem",
                width: "100%",
              }}
            >
              {/* Card 1: Entitled Products */}
              <div
                style={{
                  background: "var(--glass-surface-elevated)",
                  border: "1px solid var(--border-glass)",
                  borderRadius: "14px",
                  padding: "1.25rem 1.5rem",
                  boxShadow: "var(--shadow-sm)",
                  display: "flex",
                  flexDirection: "column",
                  gap: "0.5rem",
                }}
              >
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                  <span
                    style={{
                      fontSize: "0.75rem",
                      fontWeight: 700,
                      letterSpacing: "0.04em",
                      textTransform: "uppercase",
                      color: "var(--text-secondary)",
                    }}
                  >
                    ENTITLED PRODUCTS
                  </span>
                  <div
                    style={{
                      width: "36px",
                      height: "36px",
                      borderRadius: "10px",
                      background: "var(--surface-soft-lavender)",
                      color: "var(--brand-primary)",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                    }}
                  >
                    <BoxIcon size={18} />
                  </div>
                </div>
                <div style={{ display: "flex", alignItems: "baseline", gap: "0.6rem" }}>
                  <span style={{ fontSize: "2rem", fontWeight: 800, color: "var(--text-primary)" }}>
                    {entitledProducts.length}
                  </span>
                  <span style={{ fontSize: "0.8125rem", fontWeight: 600, color: "var(--text-muted)" }}>
                    {allProducts.length} in catalog
                  </span>
                </div>
              </div>

              {/* Card 2: Assigned Seats */}
              <div
                style={{
                  background: "var(--glass-surface-elevated)",
                  border: "1px solid var(--border-glass)",
                  borderRadius: "14px",
                  padding: "1.25rem 1.5rem",
                  boxShadow: "var(--shadow-sm)",
                  display: "flex",
                  flexDirection: "column",
                  gap: "0.5rem",
                }}
              >
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                  <span
                    style={{
                      fontSize: "0.75rem",
                      fontWeight: 700,
                      letterSpacing: "0.04em",
                      textTransform: "uppercase",
                      color: "var(--text-secondary)",
                    }}
                  >
                    ASSIGNED SEATS
                  </span>
                  <div
                    style={{
                      width: "36px",
                      height: "36px",
                      borderRadius: "10px",
                      background: "var(--surface-soft-mint)",
                      color: "var(--status-success)",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                    }}
                  >
                    <UserIcon size={18} />
                  </div>
                </div>
                <div style={{ display: "flex", alignItems: "baseline", gap: "0.6rem" }}>
                  <span style={{ fontSize: "2rem", fontWeight: 800, color: "var(--text-primary)" }}>
                    {totalAssignedSeats}
                  </span>
                  <span style={{ fontSize: "0.8125rem", fontWeight: 600, color: "var(--status-success)" }}>
                    {availableSeatsCount} available pool
                  </span>
                </div>
              </div>

              {/* Card 3: Active Modules */}
              <div
                style={{
                  background: "var(--glass-surface-elevated)",
                  border: "1px solid var(--border-glass)",
                  borderRadius: "14px",
                  padding: "1.25rem 1.5rem",
                  boxShadow: "var(--shadow-sm)",
                  display: "flex",
                  flexDirection: "column",
                  gap: "0.5rem",
                }}
              >
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                  <span
                    style={{
                      fontSize: "0.75rem",
                      fontWeight: 700,
                      letterSpacing: "0.04em",
                      textTransform: "uppercase",
                      color: "var(--text-secondary)",
                    }}
                  >
                    ACTIVE MODULES
                  </span>
                  <div
                    style={{
                      width: "36px",
                      height: "36px",
                      borderRadius: "10px",
                      background: "var(--surface-soft-blue)",
                      color: "var(--brand-sky)",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                    }}
                  >
                    <LayersIcon size={18} />
                  </div>
                </div>
                <div style={{ display: "flex", alignItems: "baseline", gap: "0.6rem" }}>
                  <span style={{ fontSize: "2rem", fontWeight: 800, color: "var(--text-primary)" }}>
                    {totalEligibleModules}
                  </span>
                  <span style={{ fontSize: "0.8125rem", fontWeight: 600, color: "var(--status-success)" }}>
                    All entitled
                  </span>
                </div>
              </div>

              {/* Card 4: Organization Status */}
              <div
                style={{
                  background: "var(--glass-surface-elevated)",
                  border: "1px solid var(--border-glass)",
                  borderRadius: "14px",
                  padding: "1.25rem 1.5rem",
                  boxShadow: "var(--shadow-sm)",
                  display: "flex",
                  flexDirection: "column",
                  gap: "0.5rem",
                }}
              >
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                  <span
                    style={{
                      fontSize: "0.75rem",
                      fontWeight: 700,
                      letterSpacing: "0.04em",
                      textTransform: "uppercase",
                      color: "var(--text-secondary)",
                    }}
                  >
                    STATUS &amp; AUTHORITY
                  </span>
                  <div
                    style={{
                      width: "36px",
                      height: "36px",
                      borderRadius: "10px",
                      background: "var(--surface-soft-peach)",
                      color: "var(--status-warning)",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                    }}
                  >
                    <ShieldCheckIcon size={18} />
                  </div>
                </div>
                <div style={{ display: "flex", alignItems: "baseline", gap: "0.6rem" }}>
                  <span style={{ fontSize: "1.5rem", fontWeight: 800, color: "var(--text-primary)", textTransform: "uppercase" }}>
                    {orgStatus}
                  </span>
                  <span style={{ fontSize: "0.8125rem", fontWeight: 600, color: "var(--status-success)" }}>
                    {membership?.role?.name || "Administrator"}
                  </span>
                </div>
              </div>
            </div>

            {/* Middle Row: Seat Allocation Trend + Product Donut (60% / 40%) */}
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "minmax(0, 1.4fr) minmax(0, 1fr)",
                gap: "1.25rem",
                width: "100%",
              }}
            >
              <TelemetryTrendChart
                title="Capacity & Seat Utilization"
                subtitle="Allocated member seats and active module distribution"
                data={seatTrendData}
                strokeColor="var(--status-success, #10b981)"
                fillGradientId="seat-gradient"
              />
              <DonutDistributionChart
                title="Product Seat Allocation"
                subtitle="Seat distribution across assigned applications"
                segments={productSegments}
                totalLabel="Applications"
                totalValue={productSegments.length}
              />
            </div>

            {/* Entitled Products & Seat Pool Table */}
            <div
              style={{
                background: "var(--glass-surface-elevated)",
                border: "1px solid var(--border-glass)",
                borderRadius: "14px",
                padding: "1.5rem",
                boxShadow: "var(--shadow-sm)",
                display: "flex",
                flexDirection: "column",
                gap: "1rem",
              }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <div>
                  <h2 style={{ fontSize: "1.125rem", fontWeight: 700, margin: 0, color: "var(--text-primary)" }}>
                    Entitled products &amp; seat pools
                  </h2>
                  <p style={{ fontSize: "0.8125rem", color: "var(--text-secondary)", margin: "0.2rem 0 0 0" }}>
                    Assigned applications, module packaging and seat utilization
                  </p>
                </div>
                <Link
                  to="/tenant/products"
                  style={{
                    fontSize: "0.8125rem",
                    fontWeight: 600,
                    color: "var(--brand-primary)",
                    textDecoration: "none",
                    display: "inline-flex",
                    alignItems: "center",
                    gap: "0.25rem",
                  }}
                >
                  View App Launcher <ArrowRightIcon size={12} />
                </Link>
              </div>

              <div style={{ overflowX: "auto" }}>
                <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.875rem" }}>
                  <thead>
                    <tr style={{ borderBottom: "1px solid var(--border-subtle)", textAlign: "left" }}>
                      <th style={{ padding: "0.75rem 1rem", color: "var(--text-muted)", fontWeight: 600, fontSize: "0.75rem", textTransform: "uppercase" }}>
                        Product
                      </th>
                      <th style={{ padding: "0.75rem 1rem", color: "var(--text-muted)", fontWeight: 600, fontSize: "0.75rem", textTransform: "uppercase" }}>
                        Status
                      </th>
                      <th style={{ padding: "0.75rem 1rem", color: "var(--text-muted)", fontWeight: 600, fontSize: "0.75rem", textTransform: "uppercase" }}>
                        Seat Allocation
                      </th>
                      <th style={{ padding: "0.75rem 1rem", color: "var(--text-muted)", fontWeight: 600, fontSize: "0.75rem", textTransform: "uppercase" }}>
                        Eligible Modules
                      </th>
                      <th style={{ padding: "0.75rem 1rem", color: "var(--text-muted)", fontWeight: 600, fontSize: "0.75rem", textTransform: "uppercase", textAlign: "right" }}>
                        Workspace Action
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {entitledProducts.map((p) => {
                      const isAvailable = p.access_state === "available";
                      const prodSeat = (seatSummary?.products ?? []).find(
                        (sp) => sp.product_id === p.id
                      );
                      const consumed = prodSeat ? prodSeat.consumed_seats : (p.modules?.length || 0);
                      const total = prodSeat?.total_limit;
                      const pct = total ? Math.min((consumed / total) * 100, 100) : 100;
                      return (
                        <tr
                          key={p.id}
                          style={{
                            borderBottom: "1px solid var(--border-subtle)",
                            transition: "background 0.15s ease",
                          }}
                        >
                          <td style={{ padding: "0.85rem 1rem" }}>
                            <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
                              <div
                                style={{
                                  width: "34px",
                                  height: "34px",
                                  borderRadius: "8px",
                                  background: "rgba(99, 102, 241, 0.12)",
                                  color: "var(--brand-primary)",
                                  fontWeight: 700,
                                  fontSize: "0.75rem",
                                  display: "flex",
                                  alignItems: "center",
                                  justifyContent: "center",
                                  flexShrink: 0,
                                  textTransform: "uppercase",
                                }}
                              >
                                {p.code.slice(0, 3)}
                              </div>
                              <div>
                                <div style={{ fontWeight: 600, color: "var(--text-primary)" }}>
                                  {p.name}
                                </div>
                                <div style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
                                  {p.code} &bull; Enterprise SaaS
                                </div>
                              </div>
                            </div>
                          </td>
                          <td style={{ padding: "0.85rem 1rem" }}>
                            <span
                              style={{
                                display: "inline-flex",
                                alignItems: "center",
                                gap: "0.3rem",
                                padding: "0.2rem 0.55rem",
                                borderRadius: "999px",
                                fontSize: "0.72rem",
                                fontWeight: 700,
                                background: isAvailable ? "var(--status-success-bg)" : "var(--status-warning-bg)",
                                color: isAvailable ? "var(--status-success)" : "var(--status-warning)",
                                border: `1px solid ${isAvailable ? "var(--status-success-border)" : "var(--status-warning-border)"}`,
                                textTransform: "uppercase",
                              }}
                            >
                              &bull; {isAvailable ? "Available" : p.access_state || "Restricted"}
                            </span>
                          </td>
                          <td style={{ padding: "0.85rem 1rem" }}>
                            <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", maxWidth: "140px" }}>
                              <div
                                style={{
                                  flex: 1,
                                  height: "6px",
                                  background: "var(--border-subtle)",
                                  borderRadius: "3px",
                                  overflow: "hidden",
                                }}
                              >
                                <div
                                  style={{
                                    width: `${pct}%`,
                                    height: "100%",
                                    background: "var(--status-success)",
                                    borderRadius: "3px",
                                  }}
                                />
                              </div>
                              <span style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
                                {consumed} {total ? `/ ${total}` : "active"}
                              </span>
                            </div>
                          </td>
                          <td style={{ padding: "0.85rem 1rem" }}>
                            <div style={{ display: "flex", flexWrap: "wrap", gap: "0.35rem" }}>
                              {(p.eligible_modules ?? []).slice(0, 3).map((mod) => (
                                <span
                                  key={mod.id}
                                  style={{
                                    padding: "0.15rem 0.45rem",
                                    borderRadius: "4px",
                                    fontSize: "0.7rem",
                                    background: "var(--glass-surface)",
                                    color: "var(--text-secondary)",
                                    border: "1px solid var(--border-subtle)",
                                  }}
                                >
                                  {mod.name}
                                </span>
                              ))}
                              {(p.eligible_modules?.length || 0) > 3 && (
                                <span style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>
                                  +{p.eligible_modules!.length - 3} more
                                </span>
                              )}
                            </div>
                          </td>
                          <td style={{ padding: "0.85rem 1rem", textAlign: "right" }}>
                            <button
                              type="button"
                              className="btn btn-secondary btn-sm"
                              disabled={!p.launchable}
                              onClick={p.launchable ? () => navigate(`/tenant/workspace/${p.id}`, { state: { product: p } }) : undefined}
                              style={{
                                padding: "0.25rem 0.65rem",
                                fontSize: "0.75rem",
                                opacity: p.launchable ? 1 : 0.6,
                                cursor: p.launchable ? "pointer" : "not-allowed",
                              }}
                              title={p.launchable ? "Launch Workspace" : (p.access_state === "not_assigned" ? "Access or assignment required" : "Unavailable")}
                            >
                              Launch Workspace
                            </button>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>

            {/* Operational Lower Row (2 Columns: Alerts & Activity Timeline) */}
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))",
                gap: "1.25rem",
                width: "100%",
              }}
            >
              {/* Left: Administrative alerts */}
              <div
                style={{
                  background: "var(--glass-surface-elevated)",
                  border: "1px solid var(--border-glass)",
                  borderRadius: "14px",
                  padding: "1.5rem",
                  boxShadow: "var(--shadow-sm)",
                  display: "flex",
                  flexDirection: "column",
                  gap: "0.875rem",
                }}
              >
                <div>
                  <h2 style={{ fontSize: "1rem", fontWeight: 700, margin: 0, color: "var(--text-primary)" }}>
                    Administrative alerts &amp; quotas
                  </h2>
                  <p style={{ fontSize: "0.8125rem", color: "var(--text-secondary)", margin: "0.2rem 0 0 0" }}>
                    Entitlement conditions and seat pool thresholds
                  </p>
                </div>

                <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
                  {inactiveSubProducts.length > 0 || suspendedAssignments.length > 0 || exhaustedSeatPools.length > 0 ? (
                    <>
                      {inactiveSubProducts.map((p) => (
                        <div
                          key={p.id}
                          style={{
                            padding: "0.75rem",
                            borderRadius: "8px",
                            background: "var(--status-danger-bg)",
                            border: "1px solid var(--status-danger-border)",
                            display: "flex",
                            gap: "0.5rem",
                          }}
                        >
                          <AlertCircleIcon size={16} color="var(--status-danger)" />
                          <div style={{ fontSize: "0.8125rem" }}>
                            <strong>{p.name}:</strong> Subscription is inactive.
                          </div>
                        </div>
                      ))}
                      {exhaustedSeatPools.map((sp) => (
                        <div
                          key={sp.product_id}
                          style={{
                            padding: "0.75rem",
                            borderRadius: "8px",
                            background: "var(--status-warning-bg)",
                            border: "1px solid var(--status-warning-border)",
                            display: "flex",
                            gap: "0.5rem",
                          }}
                        >
                          <AlertCircleIcon size={16} color="var(--status-warning)" />
                          <div style={{ fontSize: "0.8125rem" }}>
                            <strong>{sp.product_name}:</strong> Seat capacity exhausted ({sp.consumed_seats}/{sp.total_limit ?? "Unlimited"}).
                          </div>
                        </div>
                      ))}
                    </>
                  ) : (
                    <div
                      style={{
                        padding: "1.25rem",
                        borderRadius: "8px",
                        background: "var(--status-success-bg)",
                        border: "1px solid var(--status-success-border)",
                        display: "flex",
                        alignItems: "center",
                        gap: "0.75rem",
                        color: "var(--status-success)",
                      }}
                    >
                      <CheckCircleIcon size={18} />
                      <div style={{ fontSize: "0.8125rem" }}>
                        All organizational product entitlements and seat pools are within capacity limits.
                      </div>
                    </div>
                  )}
                </div>
              </div>

              {/* Right: Activity timeline */}
              <div
                style={{
                  background: "var(--glass-surface-elevated)",
                  border: "1px solid var(--border-glass)",
                  borderRadius: "14px",
                  padding: "1.5rem",
                  boxShadow: "var(--shadow-sm)",
                  display: "flex",
                  flexDirection: "column",
                  gap: "0.875rem",
                }}
              >
                <div>
                  <h2 style={{ fontSize: "1rem", fontWeight: 700, margin: 0, color: "var(--text-primary)" }}>
                    Activity timeline
                  </h2>
                  <p style={{ fontSize: "0.8125rem", color: "var(--text-secondary)", margin: "0.2rem 0 0 0" }}>
                    Recent tenant-scoped access modifications and audit events
                  </p>
                </div>

                <div style={{ display: "flex", flexDirection: "column", gap: "0.85rem" }}>
                  {tenantLogs.length > 0 ? (
                    tenantLogs.map((log, idx) => (
                      <div
                        key={log.id || idx}
                        style={{
                          display: "flex",
                          alignItems: "flex-start",
                          gap: "0.75rem",
                          fontSize: "0.8125rem",
                        }}
                      >
                        <div
                          style={{
                            width: "24px",
                            height: "24px",
                            borderRadius: "50%",
                            background: "rgba(99, 102, 241, 0.12)",
                            color: "var(--brand-primary)",
                            display: "flex",
                            alignItems: "center",
                            justifyContent: "center",
                            flexShrink: 0,
                            marginTop: "2px",
                          }}
                        >
                          <LayersIcon size={12} />
                        </div>
                        <div style={{ flex: 1, minWidth: 0 }}>
                          <span style={{ fontWeight: 600, color: "var(--text-primary)" }}>
                            {log.actor?.email || "Tenant Administrator"}
                          </span>{" "}
                          <span style={{ color: "var(--text-secondary)" }}>
                            {AUDIT_ACTION_LABELS[log.action] || log.action || "modified tenant settings"}
                          </span>
                        </div>
                        <span style={{ fontSize: "0.7rem", color: "var(--text-muted)", whiteSpace: "nowrap" }}>
                          {log.timestamp ? new Date(log.timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : ""}
                        </span>
                      </div>
                    ))
                  ) : (
                    <div style={{ fontSize: "0.8125rem", color: "var(--text-muted)", padding: "1rem 0" }}>
                      No recent tenant administrative events recorded in current window.
                    </div>
                  )}
                </div>
              </div>
            </div>

            {/* Quick Actions Row matching Design #2 Screen 3 */}
            <div style={{ marginTop: "1rem" }}>
              <div style={{ marginBottom: "1rem" }}>
                <h2 style={{ fontSize: "1.0625rem", fontWeight: 700, margin: 0, color: "var(--text-primary)" }}>
                  Quick Actions
                </h2>
                <p style={{ fontSize: "0.8125rem", color: "var(--text-secondary)", margin: "0.2rem 0 0 0" }}>
                  Fast administrative operations for user seats, roles, and product access
                </p>
              </div>

              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))",
                  gap: "1rem",
                }}
              >
                {/* 1. Add Member */}
                <Link
                  to="/tenant-users"
                  className="quick-action-card"
                  style={{
                    background: "var(--glass-surface-elevated)",
                    border: "1px solid var(--border-glass)",
                    borderRadius: "14px",
                    padding: "1.125rem 1.25rem",
                    display: "flex",
                    alignItems: "center",
                    gap: "1rem",
                    textDecoration: "none",
                    boxShadow: "var(--shadow-sm)",
                    transition: "transform 0.18s cubic-bezier(0.16, 1, 0.3, 1), box-shadow 0.18s ease, border-color 0.18s ease",
                  }}
                >
                  <div
                    style={{
                      width: "44px",
                      height: "44px",
                      borderRadius: "12px",
                      background: "var(--surface-soft-lavender)",
                      color: "var(--brand-primary)",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      flexShrink: 0,
                    }}
                  >
                    <UserIcon size={20} />
                  </div>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: "0.875rem", fontWeight: 700, color: "var(--text-primary)" }}>
                      Invite Members
                    </div>
                    <div style={{ fontSize: "0.75rem", color: "var(--text-secondary)", marginTop: "2px" }}>
                      Onboard colleagues to organization
                    </div>
                  </div>
                  <ArrowRightIcon size={16} style={{ color: "var(--text-muted)", flexShrink: 0 }} />
                </Link>

                {/* 2. Manage Access */}
                <Link
                  to="/assignments"
                  className="quick-action-card"
                  style={{
                    background: "var(--glass-surface-elevated)",
                    border: "1px solid var(--border-glass)",
                    borderRadius: "14px",
                    padding: "1.125rem 1.25rem",
                    display: "flex",
                    alignItems: "center",
                    gap: "1rem",
                    textDecoration: "none",
                    boxShadow: "var(--shadow-sm)",
                    transition: "transform 0.18s cubic-bezier(0.16, 1, 0.3, 1), box-shadow 0.18s ease, border-color 0.18s ease",
                  }}
                >
                  <div
                    style={{
                      width: "44px",
                      height: "44px",
                      borderRadius: "12px",
                      background: "var(--surface-soft-blue)",
                      color: "#2563eb",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      flexShrink: 0,
                    }}
                  >
                    <LayersIcon size={20} />
                  </div>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: "0.875rem", fontWeight: 700, color: "var(--text-primary)" }}>
                      Manage Access
                    </div>
                    <div style={{ fontSize: "0.75rem", color: "var(--text-secondary)", marginTop: "2px" }}>
                      Assign products & user roles
                    </div>
                  </div>
                  <ArrowRightIcon size={16} style={{ color: "var(--text-muted)", flexShrink: 0 }} />
                </Link>

                {/* 3. View Reports */}
                <Link
                  to="/audit-logs"
                  className="quick-action-card"
                  style={{
                    background: "var(--glass-surface-elevated)",
                    border: "1px solid var(--border-glass)",
                    borderRadius: "14px",
                    padding: "1.125rem 1.25rem",
                    display: "flex",
                    alignItems: "center",
                    gap: "1rem",
                    textDecoration: "none",
                    boxShadow: "var(--shadow-sm)",
                    transition: "transform 0.18s cubic-bezier(0.16, 1, 0.3, 1), box-shadow 0.18s ease, border-color 0.18s ease",
                  }}
                >
                  <div
                    style={{
                      width: "44px",
                      height: "44px",
                      borderRadius: "12px",
                      background: "var(--surface-soft-mint)",
                      color: "#059669",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      flexShrink: 0,
                    }}
                  >
                    <ShieldCheckIcon size={20} />
                  </div>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: "0.875rem", fontWeight: 700, color: "var(--text-primary)" }}>
                      View Reports
                    </div>
                    <div style={{ fontSize: "0.75rem", color: "var(--text-secondary)", marginTop: "2px" }}>
                      Activity logs & security events
                    </div>
                  </div>
                  <ArrowRightIcon size={16} style={{ color: "var(--text-muted)", flexShrink: 0 }} />
                </Link>

                {/* 4. Request Product */}
                <Link
                  to="/showcase"
                  className="quick-action-card"
                  style={{
                    background: "var(--glass-surface-elevated)",
                    border: "1px solid var(--border-glass)",
                    borderRadius: "14px",
                    padding: "1.125rem 1.25rem",
                    display: "flex",
                    alignItems: "center",
                    gap: "1rem",
                    textDecoration: "none",
                    boxShadow: "var(--shadow-sm)",
                    transition: "transform 0.18s cubic-bezier(0.16, 1, 0.3, 1), box-shadow 0.18s ease, border-color 0.18s ease",
                  }}
                >
                  <div
                    style={{
                      width: "44px",
                      height: "44px",
                      borderRadius: "12px",
                      background: "var(--surface-soft-peach)",
                      color: "#d97706",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      flexShrink: 0,
                    }}
                  >
                    <PlusIcon size={20} />
                  </div>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: "0.875rem", fontWeight: 700, color: "var(--text-primary)" }}>
                      Explore Products
                    </div>
                    <div style={{ fontSize: "0.75rem", color: "var(--text-secondary)", marginTop: "2px" }}>
                      Discover modules & solutions
                    </div>
                  </div>
                  <ArrowRightIcon size={16} style={{ color: "var(--text-muted)", flexShrink: 0 }} />
                </Link>
              </div>
            </div>
          </>
        )}
      </div>
    </AppShell>
  );
};
