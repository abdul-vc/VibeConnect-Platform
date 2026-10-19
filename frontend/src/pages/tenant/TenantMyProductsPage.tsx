/**
 * Tenant My Products & App Launcher Page (Phase 2G).
 *
 * Authoritative Application Launcher:
 * - Powered exclusively by GET /api/v1/tenant/home/ via tenantHomeApi
 * - Displays all evaluated products for the tenant user with access state badges
 * - Lists eligible modules and feature entitlements
 * - Disabled "Launch" action with tooltip ("Launch available after SSO integration")
 * - Strictly zero product URL construction (launchability contract only)
 * - Safe fallback for unknown future access_state values (neutral "Unavailable" badge)
 */

import React, { useState, useEffect, useRef, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../../context/AuthContext.tsx";
import { AppShell } from "../../components/AppShell.tsx";
import { tenantHomeApi } from "../../api/tenantHome.ts";
import type { AccessState, TenantHomeResponse, TenantProductAccessItem } from "../../api/types.ts";
import { LoadingSpinner } from "../../components/LoadingSpinner.tsx";
import { BoxIcon, ShieldCheckIcon, LayersIcon } from "../../components/Icons.tsx";
import { ssoApi } from "../../api/sso.ts";

interface AccessBadgeConfig {
  readonly label: string;
  readonly bg: string;
  readonly color: string;
  readonly border: string;
}

function getAccessStateBadge(state: string | undefined): AccessBadgeConfig {
  switch (state as AccessState) {
    case "available":
      return {
        label: "Available",
        bg: "var(--status-success-bg)",
        color: "var(--status-success)",
        border: "var(--status-success-border)",
      };
    case "not_assigned":
      return {
        label: "Not Assigned",
        bg: "var(--status-warning-bg)",
        color: "var(--status-warning)",
        border: "var(--status-warning-border)",
      };
    case "subscription_inactive":
      return {
        label: "Subscription Inactive",
        bg: "var(--status-danger-bg)",
        color: "var(--status-danger)",
        border: "var(--status-danger-border)",
      };
    case "entitlement_unavailable":
      return {
        label: "Entitlement Unavailable",
        bg: "var(--glass-surface)",
        color: "var(--text-muted)",
        border: "var(--border-subtle)",
      };
    case "assignment_suspended":
      return {
        label: "Assignment Suspended",
        bg: "var(--status-danger-bg)",
        color: "var(--status-danger)",
        border: "var(--status-danger-border)",
      };
    case "assignment_revoked":
      return {
        label: "Assignment Revoked",
        bg: "var(--status-danger-bg)",
        color: "var(--status-danger)",
        border: "var(--status-danger-border)",
      };
    case "module_unavailable":
      return {
        label: "Module Unavailable",
        bg: "var(--status-warning-bg)",
        color: "var(--status-warning)",
        border: "var(--status-warning-border)",
      };
    case "membership_inactive":
      return {
        label: "Membership Inactive",
        bg: "var(--status-danger-bg)",
        color: "var(--status-danger)",
        border: "var(--status-danger-border)",
      };
    case "product_unavailable":
      return {
        label: "Product Unavailable",
        bg: "var(--glass-surface)",
        color: "var(--text-muted)",
        border: "var(--border-subtle)",
      };
    case "access_expired":
      return {
        label: "Access Expired",
        bg: "var(--status-danger-bg)",
        color: "var(--status-danger)",
        border: "var(--status-danger-border)",
      };
    default:
      // Unknown future value fail-safe
      return {
        label: "Unavailable",
        bg: "var(--glass-surface)",
        color: "var(--text-muted)",
        border: "var(--border-subtle)",
      };
  }
}

export interface TenantMyProductsPageProps {
  readonly initialData?: TenantHomeResponse;
}

export const TenantMyProductsPage: React.FC<TenantMyProductsPageProps> = ({ initialData }) => {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [homeData, setHomeData] = useState<TenantHomeResponse | null>(initialData ?? null);
  const [isLoading, setIsLoading] = useState<boolean>(!initialData);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // Generation counter to handle tenant context switches safely
  const generationRef = useRef(0);
  const currentTenantId = user?.active_context?.organization?.id;
  const lastTenantIdRef = useRef<string | undefined>(currentTenantId);


  const handleLaunchProduct = (selectedProd: TenantProductAccessItem) => {
    navigate(`/tenant/workspace/${selectedProd.id}`, { state: { product: selectedProd } });
  };

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
            : "Failed to load products launcher data.";
        setErrorMessage(errorDetail);
        setIsLoading(false);
      }
    }
  }, []);

  // Tenant switch reset trigger
  useEffect(() => {
    if (lastTenantIdRef.current !== currentTenantId) {
      lastTenantIdRef.current = currentTenantId;
      setHomeData(null);
      void fetchTenantHome();
    }
  }, [currentTenantId, fetchTenantHome]);

  // Initial load
  useEffect(() => {
    if (!initialData) {
      void fetchTenantHome();
    }
  }, [fetchTenantHome, initialData]);

  const isMember =
    user?.active_context?.type === "tenant" &&
    user?.active_context?.membership_type === "member";

  const rawProducts: readonly TenantProductAccessItem[] =
    homeData?.products && homeData.products.length > 0
      ? homeData.products
      : homeData?.entitled_products ?? [];

  // For tenant members, strictly display only effective authorized products
  const products: readonly TenantProductAccessItem[] = isMember
    ? rawProducts.filter((p) => p.access_state === "available")
    : rawProducts;

  // Authoritative SSO capability status from backend per product and active tenant
  const [ssoPilotStatuses, setSsoPilotStatuses] = useState<Record<string, boolean>>({});

  useEffect(() => {
    let isCancelled = false;
    const checkPilotStatuses = async () => {
      if (!products || products.length === 0) return;
      const statusMap: Record<string, boolean> = {};
      await Promise.all(
        products.map(async (prod) => {
          try {
            const res = await ssoApi.getPilotStatus(prod.id, currentTenantId);
            if (!isCancelled && res) {
              statusMap[prod.id] = Boolean(res.sso_enabled);
            }
          } catch {
            statusMap[prod.id] = false;
          }
        })
      );
      if (!isCancelled) {
        setSsoPilotStatuses((prev) => ({ ...prev, ...statusMap }));
      }
    };

    void checkPilotStatuses();
    return () => {
      isCancelled = true;
    };
  }, [products, currentTenantId]);

  return (
    <AppShell>
      <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem", minWidth: 0 }}>
        {/* Page Header */}
        <div
          style={{
            background: "var(--glass-surface-elevated)",
            border: "1px solid var(--border-glass)",
            borderRadius: "14px",
            padding: "1.75rem",
            boxShadow: "var(--shadow-sm)",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.5rem" }}>
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
              <BoxIcon size={14} />
              Application Launcher
            </span>
          </div>

          <h1
            className="heading-hero"
            style={{ fontSize: "1.625rem", margin: 0, overflowWrap: "anywhere", wordBreak: "break-word" }}
          >
            My Products & App Launcher
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
            Authorized business applications and module packaging for {homeData?.organization?.name || "your organization"}.
          </p>
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
            <LoadingSpinner label="Loading application launcher..." />
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
                Unable to Load Products
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



        {/* Product Cards Grid */}
        {!isLoading && !errorMessage && (
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))",
              gap: "1.25rem",
              width: "100%",
            }}
          >
            {products.length === 0 && (
              <div
                style={{
                  gridColumn: "1 / -1",
                  background: "var(--glass-surface-elevated)",
                  border: "1px solid var(--border-glass)",
                  borderRadius: "12px",
                  padding: "3rem",
                  textAlign: "center",
                  color: "var(--text-secondary)",
                }}
              >
                <div
                  style={{
                    width: "48px",
                    height: "48px",
                    borderRadius: "12px",
                    background: "rgba(99, 102, 241, 0.1)",
                    color: "rgb(99, 102, 241)",
                    display: "inline-flex",
                    alignItems: "center",
                    justifyContent: "center",
                    marginBottom: "1rem",
                  }}
                >
                  <BoxIcon size={24} />
                </div>
                <h2 style={{ fontSize: "1.125rem", fontWeight: 700, margin: "0 0 0.5rem 0", color: "var(--text-primary)" }}>
                  No Products Available
                </h2>
                <p style={{ fontSize: "0.875rem", margin: 0, maxWidth: "420px", marginLeft: "auto", marginRight: "auto" }}>
                  Your organization does not have any active product assignments or entitlements at this time.
                </p>
              </div>
            )}

            {products.map((product) => {
              const badge = getAccessStateBadge(product.access_state);
              const isLaunchable = product.access_state === "available";
              const eligibleModules = product.eligible_modules ?? [];

              return (
                <div
                  key={product.id}
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
                  }}
                >
                  <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
                    {/* Card Top: Code & Badge */}
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: "0.5rem", flexWrap: "wrap" }}>
                      <span className="product-code-pill" style={{ fontSize: "0.75rem" }}>
                        {product.code}
                      </span>

                      <span
                        style={{
                          display: "inline-flex",
                          alignItems: "center",
                          padding: "0.2rem 0.55rem",
                          borderRadius: "6px",
                          fontSize: "0.75rem",
                          fontWeight: 600,
                          background: badge.bg,
                          color: badge.color,
                          border: `1px solid ${badge.border}`,
                          textTransform: "uppercase",
                          letterSpacing: "0.02em",
                        }}
                      >
                        {badge.label}
                      </span>
                    </div>

                    {/* Product Name & Description */}
                    <div>
                      <h2
                        style={{
                          fontSize: "1.25rem",
                          fontWeight: 700,
                          margin: "0 0 0.35rem 0",
                          color: "var(--text-primary)",
                          overflowWrap: "anywhere",
                        }}
                      >
                        {product.name}
                      </h2>
                      <p
                        style={{
                          fontSize: "0.875rem",
                          color: "var(--text-secondary)",
                          margin: 0,
                          lineHeight: 1.5,
                          overflowWrap: "anywhere",
                        }}
                      >
                        {product.description || "No description provided."}
                      </p>
                    </div>

                    {/* Denial Reason Note if not available */}
                    {product.denial_code && (
                      <div
                        style={{
                          padding: "0.5rem 0.75rem",
                          borderRadius: "6px",
                          background: "var(--glass-surface)",
                          border: "1px solid var(--border-subtle)",
                          fontSize: "0.8125rem",
                          color: "var(--text-muted)",
                        }}
                      >
                        <strong>Reason:</strong> {product.denial_code.replace(/_/g, " ")}
                      </div>
                    )}

                    {/* Eligible Modules List */}
                    <div>
                      <div
                        style={{
                          display: "flex",
                          alignItems: "center",
                          gap: "0.35rem",
                          fontSize: "0.75rem",
                          fontWeight: 700,
                          textTransform: "uppercase",
                          letterSpacing: "0.05em",
                          color: "var(--text-muted)",
                          marginBottom: "0.5rem",
                        }}
                      >
                        <LayersIcon size={12} />
                        <span>Eligible Modules ({eligibleModules.length})</span>
                      </div>

                      {eligibleModules.length > 0 ? (
                        <div style={{ display: "flex", flexWrap: "wrap", gap: "0.35rem" }}>
                          {eligibleModules.map((mod) => (
                            <span
                              key={mod.id}
                              style={{
                                display: "inline-flex",
                                alignItems: "center",
                                padding: "0.2rem 0.5rem",
                                borderRadius: "4px",
                                background: "var(--glass-surface)",
                                border: "1px solid var(--border-subtle)",
                                fontSize: "0.75rem",
                                color: "var(--text-primary)",
                              }}
                            >
                              {mod.name}
                            </span>
                          ))}
                        </div>
                      ) : (
                        <span style={{ fontSize: "0.8125rem", color: "var(--text-muted)" }}>
                          No active modules assigned or entitled.
                        </span>
                      )}
                    </div>
                  </div>

                  {/* Card Bottom: Launch Button */}
                  <div style={{ paddingTop: "0.75rem", borderTop: "1px solid var(--border-subtle)" }}>
                    {(() => {
                      const isSsoEnabled = Boolean(ssoPilotStatuses[product.id]);
                      const isPilotLaunchable = isLaunchable && (isSsoEnabled || product.code === "quiz");

                      return (
                        <>
                          <button
                            type="button"
                            id={`launch-btn-${product.id}`}
                            disabled={!isPilotLaunchable}
                            onClick={isPilotLaunchable ? () => handleLaunchProduct(product) : undefined}
                            title={
                              isPilotLaunchable
                                ? product.code === "quiz"
                                  ? "Launch Application"
                                  : "Launch Application via SSO"
                                : isLaunchable
                                ? "Launch available after SSO integration"
                                : `Launch unavailable: ${badge.label}`
                            }
                            className="btn-primary"
                            style={{
                              width: "100%",
                              opacity: isPilotLaunchable ? 1 : 0.6,
                              cursor: isPilotLaunchable ? "pointer" : "not-allowed",
                              display: "flex",
                              justifyContent: "center",
                              alignItems: "center",
                              gap: "0.5rem",
                            }}
                            aria-disabled={!isPilotLaunchable}
                          >
                            <ShieldCheckIcon size={16} />
                            <span>
                              {isPilotLaunchable
                                ? "Launch Product"
                                : isLaunchable
                                ? "Launch Product"
                                : `Unavailable (${badge.label})`}
                            </span>
                          </button>
                          <div
                            style={{
                              fontSize: "0.6875rem",
                              color: isPilotLaunchable ? "var(--status-success)" : "var(--text-muted)",
                              textAlign: "center",
                              marginTop: "0.35rem",
                            }}
                          >
                            {isPilotLaunchable
                              ? product.code === "quiz"
                                ? "Direct Launch — Ready to Launch"
                                : "SSO Pilot Enabled — Ready to Launch"
                              : "Launch available after SSO integration"}
                          </div>
                        </>
                      );
                    })()}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </AppShell>
  );
};
