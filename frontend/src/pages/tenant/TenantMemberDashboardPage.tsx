/**
 * Tenant Member Dashboard Page.
 *
 * Dedicated professional landing page for authenticated tenant Members.
 * Displays:
 * - Real authenticated member identity and organization context
 * - Authoritative assigned product overview and quick-launch cards
 * - Real module access summaries (zero fake metrics or counters)
 * - Accessible, responsive enterprise design matching VibeConnect tokens
 */

import React, { useState, useEffect, useRef, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../../context/AuthContext.tsx";
import { AppShell } from "../../components/AppShell.tsx";
import { tenantHomeApi } from "../../api/tenantHome.ts";
import type { TenantHomeResponse, TenantProductAccessItem } from "../../api/types.ts";
import { LoadingSpinner } from "../../components/LoadingSpinner.tsx";
import {
  BoxIcon,
  ShieldCheckIcon,
  LayersIcon,
  RotateCcwIcon,
  ChevronRightIcon,
  AlertCircleIcon,
} from "../../components/Icons.tsx";

export const TenantMemberDashboardPage: React.FC = () => {
  const { user } = useAuth();
  const navigate = useNavigate();

  const [homeData, setHomeData] = useState<TenantHomeResponse | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [selectedCategory, setSelectedCategory] = useState<string>("all");

  const generationRef = useRef(0);
  const currentTenantId = user?.active_context?.organization?.id;
  const lastTenantIdRef = useRef<string | undefined>(currentTenantId);

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
        const detail =
          err && typeof err === "object" && "message" in err
            ? String((err as { message: string }).message)
            : "Failed to load member dashboard.";
        setErrorMessage(detail);
        setIsLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    if (lastTenantIdRef.current !== currentTenantId) {
      lastTenantIdRef.current = currentTenantId;
      setHomeData(null);
      void fetchTenantHome();
    }
  }, [currentTenantId, fetchTenantHome]);

  useEffect(() => {
    void fetchTenantHome();
  }, [fetchTenantHome]);

  const organization = homeData?.organization ?? user?.active_context?.organization;
  const membership = homeData?.membership;
  const products: readonly TenantProductAccessItem[] =
    homeData?.products && homeData.products.length > 0
      ? homeData.products
      : homeData?.entitled_products ?? [];
  const entitledProducts: readonly TenantProductAccessItem[] = products.filter(
    (p) => p.access_state === "available" || p.launchable
  );

  // Real aggregated metric: total eligible modules across assigned products
  const totalEligibleModules = entitledProducts.reduce(
    (acc, p) => acc + (p.eligible_modules?.length || 0),
    0
  );

  const inferCategory = (code: string, name: string) => {
    const text = `${code} ${name}`.toLowerCase();
    if (text.includes("crm") || text.includes("hrms") || text.includes("desk") || text.includes("product")) return "productivity";
    if (text.includes("comm") || text.includes("chat") || text.includes("event") || text.includes("mail")) return "communication";
    if (text.includes("report") || text.includes("analy") || text.includes("audit") || text.includes("telemetry")) return "analytics";
    return "operations";
  };

  const categories = [
    { id: "all", label: "All", count: products.length },
    { id: "productivity", label: "Productivity", count: products.filter((p) => inferCategory(p.code, p.name) === "productivity").length },
    { id: "communication", label: "Communication", count: products.filter((p) => inferCategory(p.code, p.name) === "communication").length },
    { id: "operations", label: "Operations", count: products.filter((p) => inferCategory(p.code, p.name) === "operations").length },
    { id: "analytics", label: "Analytics", count: products.filter((p) => inferCategory(p.code, p.name) === "analytics").length },
  ].filter((c) => c.id === "all" || c.count > 0);

  const displayedProducts =
    selectedCategory === "all"
      ? products
      : products.filter((p) => inferCategory(p.code, p.name) === selectedCategory);

  const handleLaunchProduct = (product: TenantProductAccessItem) => {
    navigate(`/tenant/workspace/${product.id}`, { state: { product } });
  };

  return (
    <AppShell>
      <div style={{ display: "flex", flexDirection: "column", gap: "1.75rem", minWidth: 0 }}>
        {/* Welcome Hero Banner */}
        <div
          style={{
            background: "var(--glass-surface-elevated)",
            border: "1px solid var(--border-glass)",
            borderRadius: "14px",
            padding: "2rem",
            boxShadow: "var(--shadow-sm)",
            display: "flex",
            flexDirection: "column",
            gap: "1.25rem",
          }}
        >
          <div
            style={{
              display: "flex",
              alignItems: "flex-start",
              justifyContent: "space-between",
              gap: "1rem",
              flexWrap: "wrap",
            }}
          >
            <div style={{ minWidth: 0 }}>
              <div
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  gap: "0.5rem",
                  padding: "0.25rem 0.75rem",
                  borderRadius: "9999px",
                  background: "var(--surface-soft-lavender)",
                  border: "1px solid rgba(56, 103, 245, 0.2)",
                  color: "var(--brand-primary)",
                  fontSize: "0.75rem",
                  fontWeight: 600,
                  marginBottom: "0.75rem",
                }}
              >
                <span
                  style={{
                    width: "6px",
                    height: "6px",
                    borderRadius: "50%",
                    background: "var(--status-success)",
                  }}
                />
                <span>Member Portal</span>
                <span style={{ opacity: 0.5 }}>•</span>
                <span>{organization?.name || "Enterprise"}</span>
              </div>

              <h1
                style={{
                  fontSize: "1.625rem",
                  fontWeight: 700,
                  margin: "0 0 0.5rem 0",
                  color: "var(--text-primary)",
                  letterSpacing: "-0.02em",
                }}
              >
                Welcome back, {user?.full_name || user?.email || "Member"}
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
                Here is your centralized workspace overview. Access your assigned enterprise
                applications, specialized workflows, and tools below.
              </p>
            </div>

            <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", flexWrap: "wrap" }}>
              <button
                type="button"
                onClick={() => void fetchTenantHome()}
                className="btn-secondary"
                title="Refresh status"
                disabled={isLoading}
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  gap: "0.4rem",
                  padding: "0.5rem 0.85rem",
                  fontSize: "0.8125rem",
                  fontWeight: 600,
                  cursor: isLoading ? "not-allowed" : "pointer",
                }}
              >
                <RotateCcwIcon size={14} />
                <span>Refresh</span>
              </button>

              {entitledProducts.length > 0 && (
                <button
                  type="button"
                  onClick={() => handleLaunchProduct(entitledProducts[0])}
                  className="btn-gradient"
                  style={{
                    display: "inline-flex",
                    alignItems: "center",
                    gap: "0.4rem",
                    padding: "0.5rem 1rem",
                    fontSize: "0.8125rem",
                    fontWeight: 600,
                    borderRadius: "8px",
                    cursor: "pointer",
                    border: "none",
                    color: "#ffffff",
                    boxShadow: "0 4px 14px rgba(56, 103, 245, 0.3)",
                  }}
                >
                  <span>Launch App</span>
                  <ChevronRightIcon size={14} />
                </button>
              )}
            </div>
          </div>

          {/* Real Metrics Ribbon */}
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))",
              gap: "1rem",
              paddingTop: "1.25rem",
              borderTop: "1px solid var(--border-subtle)",
            }}
          >
            <div
              style={{
                padding: "0.875rem 1rem",
                background: "var(--glass-surface)",
                borderRadius: "10px",
                border: "1px solid var(--border-subtle)",
              }}
            >
              <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.05em" }}>
                Assigned Applications
              </div>
              <div style={{ fontSize: "1.5rem", fontWeight: 700, color: "var(--text-primary)", marginTop: "0.25rem" }}>
                {isLoading ? "—" : entitledProducts.length}
              </div>
            </div>

            <div
              style={{
                padding: "0.875rem 1rem",
                background: "var(--glass-surface)",
                borderRadius: "10px",
                border: "1px solid var(--border-subtle)",
              }}
            >
              <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.05em" }}>
                Active Modules
              </div>
              <div style={{ fontSize: "1.5rem", fontWeight: 700, color: "var(--text-primary)", marginTop: "0.25rem" }}>
                {isLoading ? "—" : totalEligibleModules}
              </div>
            </div>

            <div
              style={{
                padding: "0.875rem 1rem",
                background: "var(--glass-surface)",
                borderRadius: "10px",
                border: "1px solid var(--border-subtle)",
              }}
            >
              <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.05em" }}>
                Organization
              </div>
              <div
                style={{
                  fontSize: "1rem",
                  fontWeight: 600,
                  color: "var(--text-primary)",
                  marginTop: "0.5rem",
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                  whiteSpace: "nowrap",
                }}
              >
                {organization?.name || "Active Tenant"}
              </div>
            </div>

            <div
              style={{
                padding: "0.875rem 1rem",
                background: "var(--glass-surface)",
                borderRadius: "10px",
                border: "1px solid var(--border-subtle)",
              }}
            >
              <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.05em" }}>
                Access Authority
              </div>
              <div
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  gap: "0.35rem",
                  fontSize: "0.875rem",
                  fontWeight: 600,
                  color: "var(--status-success)",
                  marginTop: "0.5rem",
                }}
              >
                <ShieldCheckIcon size={14} />
                <span>{membership?.role?.name || "Authorized Member"}</span>
              </div>
            </div>
          </div>
        </div>

        {/* Content States */}
        {isLoading ? (
          <div
            style={{
              padding: "4rem 2rem",
              display: "flex",
              justifyContent: "center",
              alignItems: "center",
              background: "var(--glass-surface-elevated)",
              border: "1px solid var(--border-glass)",
              borderRadius: "14px",
            }}
          >
            <LoadingSpinner fullScreen={false} label="Loading assigned applications…" />
          </div>
        ) : errorMessage ? (
          <div
            style={{
              padding: "2.5rem 1.5rem",
              textAlign: "center",
              background: "var(--glass-surface-elevated)",
              border: "1px solid var(--border-glass)",
              borderRadius: "14px",
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              gap: "1rem",
            }}
          >
            <div
              style={{
                width: "48px",
                height: "48px",
                borderRadius: "12px",
                background: "var(--status-danger-bg)",
                color: "var(--status-danger)",
                display: "inline-flex",
                alignItems: "center",
                justifyContent: "center",
                border: "1px solid var(--status-danger-border)",
              }}
            >
              <AlertCircleIcon size={24} />
            </div>
            <div>
              <h3 style={{ margin: "0 0 0.5rem 0", color: "var(--text-primary)", fontSize: "1.125rem", fontWeight: 700 }}>
                Unable to Load Member Applications
              </h3>
              <p style={{ margin: 0, color: "var(--text-secondary)", fontSize: "0.875rem", maxWidth: "450px" }}>
                {errorMessage}
              </p>
            </div>
            <button
              type="button"
              onClick={() => void fetchTenantHome()}
              className="btn-primary"
              style={{ padding: "0.55rem 1.25rem", fontSize: "0.875rem", cursor: "pointer" }}
            >
              Retry
            </button>
          </div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>
            {/* Assigned Applications Section Header */}
            <div
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                gap: "1rem",
                flexWrap: "wrap",
              }}
            >
              <div>
                <h2
                  style={{
                    fontSize: "1.1875rem",
                    fontWeight: 700,
                    margin: "0 0 0.25rem 0",
                    color: "var(--text-primary)",
                  }}
                >
                  My Assigned Applications
                </h2>
                <p style={{ fontSize: "0.875rem", color: "var(--text-secondary)", margin: 0 }}>
                  Authorized business applications provisioned for your organization account.
                </p>
              </div>

              <button
                type="button"
                onClick={() => navigate("/tenant/products")}
                className="btn-secondary"
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  gap: "0.4rem",
                  padding: "0.5rem 0.85rem",
                  fontSize: "0.8125rem",
                  fontWeight: 600,
                  cursor: "pointer",
                }}
              >
                <span>App Launcher</span>
                <ChevronRightIcon size={14} />
              </button>
            </div>

            {/* Category Filter Pills matching Design #2 Screen 4 */}
            {products.length > 0 && categories.length > 1 && (
              <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", flexWrap: "wrap" }}>
                {categories.map((cat) => {
                  const isActive = selectedCategory === cat.id;
                  return (
                    <button
                      key={cat.id}
                      type="button"
                      onClick={() => setSelectedCategory(cat.id)}
                      style={{
                        padding: "0.35rem 0.85rem",
                        borderRadius: "9999px",
                        fontSize: "0.8125rem",
                        fontWeight: 600,
                        border: isActive ? "none" : "1px solid var(--border-subtle)",
                        background: isActive ? "var(--brand-gradient)" : "var(--glass-surface)",
                        color: isActive ? "#ffffff" : "var(--text-secondary)",
                        boxShadow: isActive ? "0 2px 8px rgba(56, 103, 245, 0.28)" : "none",
                        cursor: "pointer",
                        transition: "all 0.16s ease",
                      }}
                    >
                      {cat.label} ({cat.count})
                    </button>
                  );
                })}
              </div>
            )}

            {/* Product Cards Grid or Empty State */}
            {products.length === 0 ? (
              <div
                style={{
                  padding: "3.5rem 1.5rem",
                  textAlign: "center",
                  background: "var(--glass-surface-elevated)",
                  border: "1px solid var(--border-glass)",
                  borderRadius: "14px",
                  display: "flex",
                  flexDirection: "column",
                  alignItems: "center",
                  gap: "1rem",
                }}
              >
                <div
                  style={{
                    width: "56px",
                    height: "56px",
                    borderRadius: "14px",
                    background: "rgba(99, 102, 241, 0.08)",
                    color: "var(--brand-primary)",
                    display: "inline-flex",
                    alignItems: "center",
                    justifyContent: "center",
                    border: "1px solid rgba(99, 102, 241, 0.2)",
                  }}
                >
                  <BoxIcon size={28} />
                </div>
                <div>
                  <h3 style={{ margin: "0 0 0.5rem 0", color: "var(--text-primary)", fontSize: "1.125rem", fontWeight: 700 }}>
                    No Applications Available
                  </h3>
                  <p
                    style={{
                      margin: 0,
                      color: "var(--text-secondary)",
                      fontSize: "0.875rem",
                      maxWidth: "460px",
                      lineHeight: 1.5,
                    }}
                  >
                    You are an active member of <strong>{organization?.name || "this organization"}</strong>,
                    but no applications are registered or available at this time.
                  </p>
                </div>
              </div>
            ) : displayedProducts.length === 0 ? (
              <div
                style={{
                  padding: "2.5rem 1.5rem",
                  textAlign: "center",
                  background: "var(--glass-surface-elevated)",
                  border: "1px solid var(--border-glass)",
                  borderRadius: "14px",
                }}
              >
                <p style={{ color: "var(--text-secondary)", margin: 0, fontSize: "0.875rem" }}>
                  No applications found matching the selected category.
                </p>
              </div>
            ) : (
              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))",
                  gap: "1.25rem",
                }}
              >
                {displayedProducts.map((prod) => {
                  const isLaunchable = Boolean(prod.launchable ?? (prod.access_state === "available"));
                  const isAvailable = prod.access_state === "available";
                  const disabledReason =
                    prod.access_state === "integration_pending"
                      ? "Integration pending"
                      : prod.access_state === "not_assigned"
                      ? "Access or assignment required"
                      : !isLaunchable
                      ? "Integration pending"
                      : "Access unavailable";

                  return (
                    <div
                      key={prod.id}
                      style={{
                        background: "var(--glass-surface-elevated)",
                        border: "1px solid var(--border-glass)",
                        borderRadius: "14px",
                        padding: "1.5rem",
                        display: "flex",
                        flexDirection: "column",
                        justifyContent: "space-between",
                        gap: "1.25rem",
                        boxShadow: "var(--shadow-sm)",
                        transition: "transform 180ms ease, box-shadow 180ms ease, border-color 180ms ease",
                      }}
                    >
                      <div style={{ display: "flex", flexDirection: "column", gap: "0.875rem" }}>
                        {/* Card Top: Code badge and status */}
                        <div
                          style={{
                            display: "flex",
                            alignItems: "center",
                            justifyContent: "space-between",
                            gap: "0.5rem",
                          }}
                        >
                          <span
                            style={{
                              display: "inline-flex",
                              alignItems: "center",
                              padding: "0.15rem 0.5rem",
                              borderRadius: "5px",
                              fontSize: "0.75rem",
                              fontWeight: 700,
                              background: "var(--surface-soft-lavender)",
                              color: "var(--brand-primary)",
                              border: "1px solid rgba(56, 103, 245, 0.25)",
                              textTransform: "uppercase",
                              letterSpacing: "0.03em",
                            }}
                          >
                            {prod.code}
                          </span>

                          <span
                            style={{
                              display: "inline-flex",
                              alignItems: "center",
                              gap: "0.3rem",
                              padding: "0.2rem 0.55rem",
                              borderRadius: "9999px",
                              fontSize: "0.75rem",
                              fontWeight: 600,
                              background: isAvailable
                                ? "var(--status-success-bg)"
                                : prod.access_state === "integration_pending"
                                ? "rgba(234, 179, 8, 0.12)"
                                : "var(--glass-surface)",
                              color: isAvailable
                                ? "var(--status-success)"
                                : prod.access_state === "integration_pending"
                                ? "rgb(234, 179, 8)"
                                : "var(--text-muted)",
                              border: isAvailable
                                ? "1px solid var(--status-success-border)"
                                : prod.access_state === "integration_pending"
                                ? "1px solid rgba(234, 179, 8, 0.25)"
                                : "1px solid var(--border-subtle)",
                            }}
                          >
                            <span
                              style={{
                                width: "5px",
                                height: "5px",
                                borderRadius: "50%",
                                background: "currentColor",
                              }}
                            />
                            <span>{isAvailable ? "Ready" : disabledReason}</span>
                          </span>
                        </div>

                        {/* Title & Description */}
                        <div>
                          <h3
                            style={{
                              fontSize: "1.0625rem",
                              fontWeight: 700,
                              margin: "0 0 0.35rem 0",
                              color: "var(--text-primary)",
                            }}
                          >
                            {prod.name}
                          </h3>
                          <p
                            style={{
                              fontSize: "0.8125rem",
                              color: "var(--text-secondary)",
                              margin: 0,
                              lineHeight: 1.5,
                              display: "-webkit-box",
                              WebkitLineClamp: 2,
                              WebkitBoxOrient: "vertical",
                              overflow: "hidden",
                            }}
                          >
                            {prod.description || "Enterprise workspace and application services."}
                          </p>
                        </div>

                        {/* Eligible Modules chips */}
                        {prod.eligible_modules && prod.eligible_modules.length > 0 && (
                          <div>
                            <div
                              style={{
                                display: "flex",
                                alignItems: "center",
                                gap: "0.35rem",
                                fontSize: "0.6875rem",
                                fontWeight: 700,
                                color: "var(--text-muted)",
                                textTransform: "uppercase",
                                letterSpacing: "0.06em",
                                marginBottom: "0.4rem",
                              }}
                            >
                              <LayersIcon size={12} />
                              <span>Assigned Modules ({prod.eligible_modules.length})</span>
                            </div>

                            <div style={{ display: "flex", flexWrap: "wrap", gap: "0.35rem" }}>
                              {prod.eligible_modules.slice(0, 3).map((mod) => (
                                <span
                                  key={mod.id}
                                  style={{
                                    display: "inline-block",
                                    padding: "0.15rem 0.45rem",
                                    borderRadius: "4px",
                                    fontSize: "0.6875rem",
                                    fontWeight: 600,
                                    background: "var(--glass-surface)",
                                    border: "1px solid var(--border-subtle)",
                                    color: "var(--text-secondary)",
                                  }}
                                >
                                  {mod.name}
                                </span>
                              ))}
                              {prod.eligible_modules.length > 3 && (
                                <span
                                  style={{
                                    display: "inline-block",
                                    padding: "0.15rem 0.45rem",
                                    borderRadius: "4px",
                                    fontSize: "0.6875rem",
                                    fontWeight: 600,
                                    background: "var(--glass-surface)",
                                    border: "1px solid var(--border-subtle)",
                                    color: "var(--text-muted)",
                                  }}
                                >
                                  +{prod.eligible_modules.length - 3} more
                                </span>
                              )}
                            </div>
                          </div>
                        )}
                      </div>

                      {/* Action button */}
                      <button
                        type="button"
                        disabled={!isLaunchable}
                        onClick={isLaunchable ? () => handleLaunchProduct(prod) : undefined}
                        className="btn-primary"
                        style={{
                          width: "100%",
                          display: "inline-flex",
                          alignItems: "center",
                          justifyContent: "center",
                          gap: "0.45rem",
                          padding: "0.65rem 1rem",
                          fontSize: "0.875rem",
                          fontWeight: 600,
                          cursor: isLaunchable ? "pointer" : "not-allowed",
                          opacity: isLaunchable ? 1 : 0.6,
                        }}
                        aria-disabled={!isLaunchable}
                      >
                        <span>{isLaunchable ? "Open Workspace" : disabledReason}</span>
                        <ChevronRightIcon size={14} />
                      </button>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        )}
      </div>
    </AppShell>
  );
};
