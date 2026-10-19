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
  const entitledProducts: readonly TenantProductAccessItem[] =
    homeData?.entitled_products && homeData.entitled_products.length > 0
      ? homeData.entitled_products
      : (homeData?.products ?? []).filter((p) => p.access_state === "available");

  // Real aggregated metric: total eligible modules across assigned products
  const totalEligibleModules = entitledProducts.reduce(
    (acc, p) => acc + (p.eligible_modules?.length || 0),
    0
  );

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
                  background: "rgba(99, 102, 241, 0.08)",
                  border: "1px solid rgba(99, 102, 241, 0.2)",
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

            {/* Product Cards Grid or Empty State */}
            {entitledProducts.length === 0 ? (
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
                    No Applications Assigned Yet
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
                    but no applications or modules have been provisioned to your profile yet. Please
                    contact your organization administrator to assign product entitlements.
                  </p>
                </div>
              </div>
            ) : (
              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))",
                  gap: "1.25rem",
                }}
              >
                {entitledProducts.map((prod) => (
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
                            background: "rgba(99, 102, 241, 0.12)",
                            color: "rgb(99, 102, 241)",
                            border: "1px solid rgba(99, 102, 241, 0.25)",
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
                            background: "var(--status-success-bg)",
                            color: "var(--status-success)",
                            border: "1px solid var(--status-success-border)",
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
                          <span>Ready</span>
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
                      onClick={() => handleLaunchProduct(prod)}
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
                        cursor: "pointer",
                      }}
                    >
                      <span>Open Workspace</span>
                      <ChevronRightIcon size={14} />
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </AppShell>
  );
};
