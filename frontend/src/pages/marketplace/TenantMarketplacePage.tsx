/**
 * Tenant Marketplace Page (Phase 6A Stage 5).
 *
 * Polished, responsive, Liquid Glass product marketplace:
 * - Lists available, installed, and upcoming integration products
 * - Displays rich product cards with showcase media, badges, modules, and plans
 * - Detailed modal/drawer with modules, features, showcase media, and pricing
 * - Tenant Admin self-service enablement with plan selection and confirmation
 * - Early adoption request flow for integration-pending products
 * - Strict adherence to frozen Stage 2/3/4 contracts and centralized API utility
 */

import React, { useState, useEffect, useCallback, useId } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../../context/AuthContext.tsx";
import { AppShell } from "../../components/AppShell.tsx";
import { LoadingSpinner } from "../../components/LoadingSpinner.tsx";
import { GlassPanel } from "../../components/GlassPanel.tsx";
import {
  BoxIcon,
  ShieldCheckIcon,
  LayersIcon,
  RefreshIcon,
  CloseIcon,
  AlertCircleIcon,
  StarIcon,
} from "../../components/Icons.tsx";
import {
  marketplaceApi,
  type MarketplaceProductListItem,
  type MarketplaceProductDetail,
  type MarketplaceTenantState,
  type MarketplaceIntegrationStatus,
} from "../../api/marketplace.ts";
import { ApiError } from "../../api/client.ts";

interface StateBadgeConfig {
  readonly label: string;
  readonly bg: string;
  readonly color: string;
  readonly border: string;
}

function getTenantStateBadge(state: MarketplaceTenantState): StateBadgeConfig {
  switch (state) {
    case "installed":
      return {
        label: "Installed",
        bg: "var(--status-success-bg)",
        color: "var(--status-success)",
        border: "var(--status-success-border)",
      };
    case "available":
      return {
        label: "Available",
        bg: "rgba(99, 102, 241, 0.12)",
        color: "rgb(99, 102, 241)",
        border: "rgba(99, 102, 241, 0.3)",
      };
    case "request_pending":
      return {
        label: "Request Submitted",
        bg: "var(--status-warning-bg)",
        color: "var(--status-warning)",
        border: "var(--status-warning-border)",
      };
    case "integration_pending":
    default:
      return {
        label: "Integration Pending",
        bg: "var(--glass-surface)",
        color: "var(--text-muted)",
        border: "var(--border-subtle)",
      };
  }
}

function getIntegrationBadge(status: MarketplaceIntegrationStatus): StateBadgeConfig {
  if (status === "operational") {
    return {
      label: "Operational",
      bg: "rgba(16, 185, 129, 0.12)",
      color: "rgb(16, 185, 129)",
      border: "rgba(16, 185, 129, 0.3)",
    };
  }
  return {
    label: "Coming Soon",
    bg: "rgba(245, 158, 11, 0.12)",
    color: "rgb(245, 158, 11)",
    border: "rgba(245, 158, 11, 0.3)",
  };
}

export const TenantMarketplacePage: React.FC = () => {
  const { user } = useAuth();
  const navigate = useNavigate();

  const [products, setProducts] = useState<readonly MarketplaceProductListItem[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  // Detail Modal / Drawer state
  const [selectedProductCode, setSelectedProductCode] = useState<string | null>(null);
  const [detailData, setDetailData] = useState<MarketplaceProductDetail | null>(null);
  const [isLoadingDetail, setIsLoadingDetail] = useState<boolean>(false);
  const [detailError, setDetailError] = useState<string | null>(null);

  // Enable Modal state
  const [enableProductTarget, setEnableProductTarget] = useState<MarketplaceProductListItem | null>(null);
  const [selectedPlanVersionId, setSelectedPlanVersionId] = useState<string>("");
  const [isSubmittingEnable, setIsSubmittingEnable] = useState<boolean>(false);
  const [enableError, setEnableError] = useState<string | null>(null);

  // Request Modal state
  const [requestProductTarget, setRequestProductTarget] = useState<MarketplaceProductListItem | null>(null);
  const [requestedPlanId, setRequestedPlanId] = useState<string>("");
  const [requestNotes, setRequestNotes] = useState<string>("");
  const [isSubmittingRequest, setIsSubmittingRequest] = useState<boolean>(false);
  const [requestError, setRequestError] = useState<string | null>(null);

  const planSelectId = useId();
  const requestPlanSelectId = useId();
  const requestNotesId = useId();

  const fetchCatalog = useCallback(async () => {
    setIsLoading(true);
    setErrorMessage(null);
    try {
      const items = await marketplaceApi.listProducts();
      setProducts(items);
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        if (err.status === 403) {
          setErrorMessage("Access denied. Please ensure you are connected to an active organization.");
        } else {
          setErrorMessage(err.message || "Failed to load marketplace products.");
        }
      } else {
        setErrorMessage("An unexpected network error occurred while loading the marketplace.");
      }
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    void fetchCatalog();
  }, [fetchCatalog]);

  const openDetail = async (code: string) => {
    setSelectedProductCode(code);
    setIsLoadingDetail(true);
    setDetailError(null);
    setDetailData(null);
    try {
      const detail = await marketplaceApi.getProductDetail(code);
      setDetailData(detail);
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setDetailError(err.message || "Failed to load product details.");
      } else {
        setDetailError("Unable to retrieve product details at this time.");
      }
    } finally {
      setIsLoadingDetail(false);
    }
  };

  const closeDetail = () => {
    setSelectedProductCode(null);
    setDetailData(null);
    setDetailError(null);
  };

  const handleOpenEnable = async (product: MarketplaceProductListItem) => {
    setEnableProductTarget(product);
    setEnableError(null);
    setSelectedPlanVersionId("");
    // Pre-fetch detail if plans are needed for selection
    try {
      const detail = await marketplaceApi.getProductDetail(product.code);
      if (detail.plans && detail.plans.length > 0) {
        setSelectedPlanVersionId(detail.plans[0].plan_version_id);
      }
    } catch {
      // Non-blocking: plan selection is optional
    }
  };

  const handleConfirmEnable = async () => {
    if (!enableProductTarget) return;
    setIsSubmittingEnable(true);
    setEnableError(null);
    try {
      await marketplaceApi.enableProduct(enableProductTarget.code, {
        plan_version_id: selectedPlanVersionId || undefined,
      });
      setSuccessMessage(`Product "${enableProductTarget.name}" was successfully enabled for your organization.`);
      setEnableProductTarget(null);
      if (selectedProductCode === enableProductTarget.code) {
        closeDetail();
      }
      await fetchCatalog();
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        if (err.status === 422) {
          setEnableError("This product's integration is pending and cannot be enabled at this time.");
        } else if (err.status === 403) {
          setEnableError("Permission denied: Only active Tenant Administrators can enable products.");
        } else {
          setEnableError(err.message || "Failed to enable product.");
        }
      } else {
        setEnableError("A network error occurred while enabling the product.");
      }
    } finally {
      setIsSubmittingEnable(false);
    }
  };

  const handleOpenRequest = async (product: MarketplaceProductListItem) => {
    setRequestProductTarget(product);
    setRequestError(null);
    setRequestedPlanId("");
    setRequestNotes("");
    try {
      const detail = await marketplaceApi.getProductDetail(product.code);
      if (detail.plans && detail.plans.length > 0) {
        setRequestedPlanId(detail.plans[0].plan_version_id);
      }
    } catch {
      // Non-blocking
    }
  };

  const handleConfirmRequest = async () => {
    if (!requestProductTarget) return;
    setIsSubmittingRequest(true);
    setRequestError(null);
    try {
      await marketplaceApi.requestProduct(requestProductTarget.code, {
        requested_plan_id: requestedPlanId || undefined,
        notes: requestNotes.trim() || undefined,
      });
      setSuccessMessage(`Adoption request for "${requestProductTarget.name}" submitted successfully.`);
      setRequestProductTarget(null);
      if (selectedProductCode === requestProductTarget.code) {
        closeDetail();
      }
      await fetchCatalog();
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        if (err.status === 409) {
          setRequestError("A request for this product is already pending review.");
        } else if (err.status === 403) {
          setRequestError("Permission denied: Only active Tenant Administrators can submit product requests.");
        } else {
          setRequestError(err.message || "Failed to submit product request.");
        }
      } else {
        setRequestError("A network error occurred while submitting your request.");
      }
    } finally {
      setIsSubmittingRequest(false);
    }
  };

  return (
    <AppShell>
      <div style={{ maxWidth: "1280px", margin: "0 auto", padding: "1.5rem" }}>
        {/* Header */}
        <div style={{ marginBottom: "2rem" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.5rem" }}>
            <span
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: "0.35rem",
                padding: "0.2rem 0.6rem",
                borderRadius: "9999px",
                fontSize: "0.75rem",
                fontWeight: 600,
                background: "rgba(99, 102, 241, 0.12)",
                color: "rgb(99, 102, 241)",
                border: "1px solid rgba(99, 102, 241, 0.25)",
              }}
            >
              <LayersIcon size={13} />
              Enterprise Marketplace
            </span>
          </div>

          <h1
            className="heading-hero"
            style={{ fontSize: "1.875rem", margin: 0, fontWeight: 700 }}
          >
            Product Marketplace
          </h1>
          <p
            className="text-body"
            style={{
              marginTop: "0.35rem",
              fontSize: "0.9375rem",
              color: "var(--text-secondary)",
            }}
          >
            Browse, enable, and adopt enterprise products for {user?.active_context?.organization?.name || "your organization"}.
          </p>
        </div>

        {/* Global Notifications */}
        {successMessage && (
          <div
            role="status"
            aria-live="polite"
            style={{
              padding: "1rem 1.25rem",
              borderRadius: "10px",
              background: "var(--status-success-bg)",
              border: "1px solid var(--status-success-border)",
              color: "var(--status-success)",
              marginBottom: "1.5rem",
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: "0.6rem" }}>
              <ShieldCheckIcon size={18} />
              <span>{successMessage}</span>
            </div>
            <button
              type="button"
              className="btn btn-ghost btn-sm"
              onClick={() => setSuccessMessage(null)}
              aria-label="Dismiss message"
              style={{ padding: "0.2rem" }}
            >
              <CloseIcon size={16} />
            </button>
          </div>
        )}

        {/* Loading State */}
        {isLoading && (
          <div style={{ padding: "4rem 0", display: "flex", justifyContent: "center" }}>
            <LoadingSpinner label="Loading marketplace products..." />
          </div>
        )}

        {/* Error State */}
        {!isLoading && errorMessage && (
          <div
            role="alert"
            style={{
              padding: "1.5rem",
              borderRadius: "10px",
              background: "var(--status-danger-bg)",
              border: "1px solid var(--status-danger-border)",
              color: "var(--status-danger)",
              marginBottom: "1.5rem",
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              flexWrap: "wrap",
              gap: "1rem",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
              <AlertCircleIcon size={20} />
              <div>
                <strong style={{ display: "block" }}>Unable to Load Marketplace</strong>
                <span style={{ fontSize: "0.875rem" }}>{errorMessage}</span>
              </div>
            </div>
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              onClick={() => void fetchCatalog()}
            >
              <RefreshIcon size={14} style={{ marginRight: "0.35rem" }} />
              Retry
            </button>
          </div>
        )}

        {/* Empty State */}
        {!isLoading && !errorMessage && products.length === 0 && (
          <GlassPanel style={{ textAlign: "center", padding: "4rem 2rem" }}>
            <BoxIcon size={48} style={{ opacity: 0.4, marginBottom: "1rem" }} />
            <h3 style={{ margin: 0, fontSize: "1.125rem", color: "var(--text-primary)" }}>
              No Products Available
            </h3>
            <p style={{ color: "var(--text-secondary)", fontSize: "0.875rem", marginTop: "0.5rem" }}>
              There are currently no active products in the marketplace catalog.
            </p>
          </GlassPanel>
        )}

        {/* Product Cards Grid */}
        {!isLoading && !errorMessage && products.length > 0 && (
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fill, minmax(340px, 1fr))",
              gap: "1.5rem",
            }}
          >
            {products.map((prod) => {
              const stateBadge = getTenantStateBadge(prod.tenant_state);
              const integBadge = getIntegrationBadge(prod.integration_status);

              return (
                <GlassPanel
                  key={prod.id}
                  style={{
                    display: "flex",
                    flexDirection: "column",
                    justifyContent: "space-between",
                    padding: "1.5rem",
                    transition: "transform 0.2s ease, box-shadow 0.2s ease",
                  }}
                >
                  <div>
                    {/* Top Row: Icon + Badges */}
                    <div
                      style={{
                        display: "flex",
                        justifyContent: "space-between",
                        alignItems: "flex-start",
                        marginBottom: "1rem",
                        gap: "0.5rem",
                      }}
                    >
                      <div
                        style={{
                          width: "48px",
                          height: "48px",
                          borderRadius: "12px",
                          background: "var(--glass-surface-elevated)",
                          border: "1px solid var(--border-subtle)",
                          display: "flex",
                          alignItems: "center",
                          justifyContent: "center",
                          flexShrink: 0,
                          overflow: "hidden",
                        }}
                      >
                        {prod.icon_url ? (
                          <img
                            src={prod.icon_url}
                            alt=""
                            style={{ width: "100%", height: "100%", objectFit: "cover" }}
                          />
                        ) : (
                          <BoxIcon size={24} style={{ color: "rgb(99, 102, 241)" }} />
                        )}
                      </div>

                      <div style={{ display: "flex", flexWrap: "wrap", gap: "0.35rem", justifyContent: "flex-end" }}>
                        <span
                          style={{
                            fontSize: "0.75rem",
                            fontWeight: 600,
                            padding: "0.2rem 0.5rem",
                            borderRadius: "6px",
                            background: stateBadge.bg,
                            color: stateBadge.color,
                            border: `1px solid ${stateBadge.border}`,
                          }}
                        >
                          {stateBadge.label}
                        </span>
                        <span
                          style={{
                            fontSize: "0.75rem",
                            fontWeight: 600,
                            padding: "0.2rem 0.5rem",
                            borderRadius: "6px",
                            background: integBadge.bg,
                            color: integBadge.color,
                            border: `1px solid ${integBadge.border}`,
                          }}
                        >
                          {integBadge.label}
                        </span>
                      </div>
                    </div>

                    {/* Product Name & Tagline */}
                    <h2
                      style={{
                        fontSize: "1.2rem",
                        fontWeight: 600,
                        margin: 0,
                        color: "var(--text-primary)",
                      }}
                    >
                      {prod.name}
                    </h2>
                    {prod.tagline && (
                      <p
                        style={{
                          fontSize: "0.85rem",
                          fontWeight: 500,
                          color: "rgb(99, 102, 241)",
                          marginTop: "0.25rem",
                          marginBottom: "0.5rem",
                        }}
                      >
                        {prod.tagline}
                      </p>
                    )}
                    <p
                      style={{
                        fontSize: "0.875rem",
                        color: "var(--text-secondary)",
                        lineHeight: 1.45,
                        marginBottom: "1rem",
                        display: "-webkit-box",
                        WebkitLineClamp: 3,
                        WebkitBoxOrient: "vertical",
                        overflow: "hidden",
                      }}
                    >
                      {prod.description}
                    </p>

                    {/* Metadata summary */}
                    <div
                      style={{
                        display: "flex",
                        alignItems: "center",
                        gap: "0.75rem",
                        fontSize: "0.75rem",
                        color: "var(--text-muted)",
                        marginBottom: "1.25rem",
                      }}
                    >
                      <span>Code: <code style={{ color: "var(--text-primary)" }}>{prod.code}</code></span>
                      {prod.plans_count > 0 && (
                        <span>• {prod.plans_count} plan tier{prod.plans_count > 1 ? "s" : ""}</span>
                      )}
                    </div>
                  </div>

                  {/* Card Actions Footer */}
                  <div
                    style={{
                      display: "flex",
                      gap: "0.75rem",
                      alignItems: "center",
                      paddingTop: "1rem",
                      borderTop: "1px solid var(--border-subtle)",
                      flexWrap: "wrap",
                    }}
                  >
                    <button
                      type="button"
                      className="btn btn-secondary btn-sm"
                      onClick={() => void openDetail(prod.code)}
                      style={{ flex: 1 }}
                    >
                      View Details
                    </button>

                    {/* State Actions */}
                    {prod.tenant_state === "installed" && (
                      <button
                        type="button"
                        className="btn btn-outline btn-sm"
                        onClick={() => navigate("/tenant/products")}
                        style={{ flex: 1 }}
                      >
                        Go to My Products
                      </button>
                    )}

                    {prod.tenant_state === "available" && prod.can_enable && (
                      <button
                        type="button"
                        className="btn btn-primary btn-sm"
                        onClick={() => void handleOpenEnable(prod)}
                        style={{ flex: 1 }}
                      >
                        Enable Product
                      </button>
                    )}

                    {prod.tenant_state === "available" && !prod.can_enable && (
                      <span
                        style={{
                          fontSize: "0.75rem",
                          color: "var(--text-muted)",
                          padding: "0.4rem 0.6rem",
                        }}
                      >
                        Admin access required to enable
                      </span>
                    )}

                    {prod.tenant_state === "integration_pending" && prod.can_request && (
                      <button
                        type="button"
                        className="btn btn-secondary btn-sm"
                        onClick={() => void handleOpenRequest(prod)}
                        style={{ flex: 1 }}
                      >
                        Request Access
                      </button>
                    )}

                    {prod.tenant_state === "request_pending" && (
                      <button
                        type="button"
                        className="btn btn-secondary btn-sm"
                        disabled
                        style={{ flex: 1, opacity: 0.7 }}
                      >
                        Request Submitted
                      </button>
                    )}
                  </div>
                </GlassPanel>
              );
            })}
          </div>
        )}

        {/* Product Detail Modal */}
        {selectedProductCode && (
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="product-detail-title"
            style={{
              position: "fixed",
              top: 0,
              left: 0,
              right: 0,
              bottom: 0,
              backgroundColor: "rgba(0, 0, 0, 0.7)",
              backdropFilter: "blur(6px)",
              display: "flex",
              justifyContent: "center",
              alignItems: "center",
              zIndex: 1000,
              padding: "1.5rem",
            }}
            onClick={(e) => {
              if (e.target === e.currentTarget) closeDetail();
            }}
          >
            <div
              className="glass-panel"
              style={{
                width: "100%",
                maxWidth: "760px",
                maxHeight: "90vh",
                overflowY: "auto",
                background: "var(--bg-card)",
                borderRadius: "16px",
                border: "1px solid var(--border-subtle)",
                padding: "2rem",
                position: "relative",
              }}
            >
              <button
                type="button"
                className="btn btn-ghost btn-sm"
                onClick={closeDetail}
                aria-label="Close detail modal"
                style={{ position: "absolute", top: "1.25rem", right: "1.25rem" }}
              >
                <CloseIcon size={20} />
              </button>

              {isLoadingDetail && (
                <div style={{ padding: "3rem", display: "flex", justifyContent: "center" }}>
                  <LoadingSpinner label="Loading specifications..." />
                </div>
              )}

              {detailError && (
                <div
                  role="alert"
                  style={{
                    padding: "1rem",
                    borderRadius: "8px",
                    background: "var(--status-danger-bg)",
                    color: "var(--status-danger)",
                  }}
                >
                  {detailError}
                </div>
              )}

              {!isLoadingDetail && detailData && (
                <div>
                  {/* Top section: Badges + Title */}
                  <div style={{ display: "flex", gap: "0.5rem", marginBottom: "0.75rem", flexWrap: "wrap" }}>
                    <span
                      style={{
                        fontSize: "0.75rem",
                        fontWeight: 600,
                        padding: "0.2rem 0.6rem",
                        borderRadius: "6px",
                        ...getTenantStateBadge(detailData.tenant_state),
                        border: `1px solid ${getTenantStateBadge(detailData.tenant_state).border}`,
                      }}
                    >
                      {getTenantStateBadge(detailData.tenant_state).label}
                    </span>
                    <span
                      style={{
                        fontSize: "0.75rem",
                        fontWeight: 600,
                        padding: "0.2rem 0.6rem",
                        borderRadius: "6px",
                        ...getIntegrationBadge(detailData.integration_status),
                        border: `1px solid ${getIntegrationBadge(detailData.integration_status).border}`,
                      }}
                    >
                      {getIntegrationBadge(detailData.integration_status).label}
                    </span>
                  </div>

                  <h2
                    id="product-detail-title"
                    style={{ fontSize: "1.5rem", fontWeight: 700, margin: 0, color: "var(--text-primary)" }}
                  >
                    {detailData.name}
                  </h2>
                  {detailData.tagline && (
                    <p style={{ color: "rgb(99, 102, 241)", fontWeight: 500, margin: "0.35rem 0 1rem 0" }}>
                      {detailData.tagline}
                    </p>
                  )}

                  {/* Overview */}
                  <div style={{ marginBottom: "1.5rem" }}>
                    <h3 style={{ fontSize: "0.95rem", fontWeight: 600, marginBottom: "0.4rem" }}>
                      Overview
                    </h3>
                    <p style={{ color: "var(--text-secondary)", fontSize: "0.9rem", lineHeight: 1.5, margin: 0 }}>
                      {detailData.overview || detailData.description}
                    </p>
                  </div>

                  {/* Showcase Media */}
                  {detailData.media && detailData.media.length > 0 && (
                    <div style={{ marginBottom: "1.5rem" }}>
                      <h3 style={{ fontSize: "0.95rem", fontWeight: 600, marginBottom: "0.5rem" }}>
                        Preview Gallery
                      </h3>
                      <div
                        style={{
                          display: "flex",
                          gap: "0.75rem",
                          overflowX: "auto",
                          paddingBottom: "0.5rem",
                        }}
                      >
                        {detailData.media.map((m) => (
                          <div
                            key={m.id}
                            style={{
                              flexShrink: 0,
                              width: "220px",
                              height: "130px",
                              borderRadius: "10px",
                              overflow: "hidden",
                              border: "1px solid var(--border-subtle)",
                              background: "var(--glass-surface)",
                            }}
                          >
                            <img
                              src={m.url}
                              alt={m.title}
                              style={{ width: "100%", height: "100%", objectFit: "cover" }}
                            />
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Modules & Features */}
                  {detailData.modules && detailData.modules.length > 0 && (
                    <div style={{ marginBottom: "1.5rem" }}>
                      <h3 style={{ fontSize: "0.95rem", fontWeight: 600, marginBottom: "0.5rem" }}>
                        Included Modules & Features
                      </h3>
                      <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
                        {detailData.modules.map((mod) => (
                          <div
                            key={mod.id}
                            style={{
                              padding: "0.85rem",
                              borderRadius: "8px",
                              background: "var(--glass-surface)",
                              border: "1px solid var(--border-subtle)",
                            }}
                          >
                            <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                              <StarIcon size={14} style={{ color: "rgb(99, 102, 241)" }} />
                              <strong style={{ fontSize: "0.875rem" }}>{mod.name}</strong>
                              <span style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
                                ({mod.code})
                              </span>
                            </div>
                            {mod.description && (
                              <p style={{ fontSize: "0.8rem", color: "var(--text-secondary)", margin: "0.25rem 0 0.5rem 0" }}>
                                {mod.description}
                              </p>
                            )}
                            {mod.features && mod.features.length > 0 && (
                              <div style={{ display: "flex", flexWrap: "wrap", gap: "0.35rem", marginTop: "0.5rem" }}>
                                {mod.features.map((feat) => (
                                  <span
                                    key={feat.id}
                                    style={{
                                      fontSize: "0.72rem",
                                      padding: "0.15rem 0.45rem",
                                      borderRadius: "4px",
                                      background: "var(--glass-surface-elevated)",
                                      border: "1px solid var(--border-subtle)",
                                      color: "var(--text-primary)",
                                    }}
                                  >
                                    {feat.name}
                                  </span>
                                ))}
                              </div>
                            )}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Packaged Plans */}
                  {detailData.plans && detailData.plans.length > 0 && (
                    <div style={{ marginBottom: "1.5rem" }}>
                      <h3 style={{ fontSize: "0.95rem", fontWeight: 600, marginBottom: "0.5rem" }}>
                        Commercial Packaging & Plans
                      </h3>
                      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(220px, 1fr))", gap: "0.75rem" }}>
                        {detailData.plans.map((pl) => (
                          <div
                            key={pl.plan_version_id}
                            style={{
                              padding: "0.85rem",
                              borderRadius: "8px",
                              background: "var(--glass-surface)",
                              border: "1px solid var(--border-subtle)",
                            }}
                          >
                            <strong style={{ fontSize: "0.875rem", display: "block" }}>{pl.plan_name}</strong>
                            <span style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>Code: {pl.plan_code}</span>
                            {pl.prices && pl.prices.length > 0 && (
                              <div style={{ marginTop: "0.5rem" }}>
                                {pl.prices.map((pr, idx) => (
                                  <div key={idx} style={{ fontSize: "0.825rem", color: "rgb(99, 102, 241)", fontWeight: 600 }}>
                                    {pr.amount} {pr.currency} / {pr.billing_interval}
                                  </div>
                                ))}
                              </div>
                            )}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Detail Footer Actions */}
                  <div
                    style={{
                      display: "flex",
                      justifyContent: "flex-end",
                      gap: "0.75rem",
                      paddingTop: "1.25rem",
                      borderTop: "1px solid var(--border-subtle)",
                    }}
                  >
                    <button type="button" className="btn btn-secondary btn-sm" onClick={closeDetail}>
                      Close
                    </button>

                    {detailData.tenant_state === "installed" && (
                      <button
                        type="button"
                        className="btn btn-outline btn-sm"
                        onClick={() => navigate("/tenant/products")}
                      >
                        Go to My Products
                      </button>
                    )}

                    {detailData.tenant_state === "available" && detailData.can_enable && (
                      <button
                        type="button"
                        className="btn btn-primary btn-sm"
                        onClick={() => {
                          const target = detailData;
                          closeDetail();
                          void handleOpenEnable(target);
                        }}
                      >
                        Enable Product
                      </button>
                    )}

                    {detailData.tenant_state === "integration_pending" && detailData.can_request && (
                      <button
                        type="button"
                        className="btn btn-secondary btn-sm"
                        onClick={() => {
                          const target = detailData;
                          closeDetail();
                          void handleOpenRequest(target);
                        }}
                      >
                        Request Access
                      </button>
                    )}
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Enable Confirmation Modal */}
        {enableProductTarget && (
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="enable-modal-title"
            style={{
              position: "fixed",
              top: 0,
              left: 0,
              right: 0,
              bottom: 0,
              backgroundColor: "rgba(0, 0, 0, 0.7)",
              backdropFilter: "blur(6px)",
              display: "flex",
              justifyContent: "center",
              alignItems: "center",
              zIndex: 1100,
              padding: "1.5rem",
            }}
          >
            <div
              className="glass-panel"
              style={{
                width: "100%",
                maxWidth: "500px",
                background: "var(--bg-card)",
                borderRadius: "16px",
                border: "1px solid var(--border-subtle)",
                padding: "2rem",
              }}
            >
              <h2 id="enable-modal-title" style={{ fontSize: "1.3rem", fontWeight: 600, margin: "0 0 0.75rem 0" }}>
                Enable {enableProductTarget.name}
              </h2>
              <p style={{ color: "var(--text-secondary)", fontSize: "0.875rem", lineHeight: 1.5, margin: "0 0 1.25rem 0" }}>
                Enabling this product provisions an active entitlement for your organization. You will immediately be able to assign users and manage access via My Products.
              </p>

              {/* Plan Choice if available */}
              {selectedPlanVersionId && (
                <div style={{ marginBottom: "1.25rem" }}>
                  <label htmlFor={planSelectId} style={{ display: "block", fontSize: "0.8rem", fontWeight: 600, marginBottom: "0.35rem" }}>
                    Selected Plan Version
                  </label>
                  <input
                    id={planSelectId}
                    type="text"
                    className="form-control"
                    value={selectedPlanVersionId}
                    readOnly
                    style={{ fontSize: "0.85rem", opacity: 0.8 }}
                  />
                </div>
              )}

              {enableError && (
                <div
                  role="alert"
                  style={{
                    padding: "0.75rem",
                    borderRadius: "8px",
                    background: "var(--status-danger-bg)",
                    color: "var(--status-danger)",
                    fontSize: "0.85rem",
                    marginBottom: "1.25rem",
                  }}
                >
                  {enableError}
                </div>
              )}

              <div style={{ display: "flex", justifyContent: "flex-end", gap: "0.75rem" }}>
                <button
                  type="button"
                  className="btn btn-secondary btn-sm"
                  onClick={() => setEnableProductTarget(null)}
                  disabled={isSubmittingEnable}
                >
                  Cancel
                </button>
                <button
                  type="button"
                  className="btn btn-primary btn-sm"
                  onClick={() => void handleConfirmEnable()}
                  disabled={isSubmittingEnable}
                >
                  {isSubmittingEnable ? "Enabling..." : "Confirm & Enable"}
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Request Adoption Modal */}
        {requestProductTarget && (
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="request-modal-title"
            style={{
              position: "fixed",
              top: 0,
              left: 0,
              right: 0,
              bottom: 0,
              backgroundColor: "rgba(0, 0, 0, 0.7)",
              backdropFilter: "blur(6px)",
              display: "flex",
              justifyContent: "center",
              alignItems: "center",
              zIndex: 1100,
              padding: "1.5rem",
            }}
          >
            <div
              className="glass-panel"
              style={{
                width: "100%",
                maxWidth: "500px",
                background: "var(--bg-card)",
                borderRadius: "16px",
                border: "1px solid var(--border-subtle)",
                padding: "2rem",
              }}
            >
              <h2 id="request-modal-title" style={{ fontSize: "1.3rem", fontWeight: 600, margin: "0 0 0.75rem 0" }}>
                Request Access: {requestProductTarget.name}
              </h2>
              <p style={{ color: "var(--text-secondary)", fontSize: "0.875rem", lineHeight: 1.5, margin: "0 0 1.25rem 0" }}>
                Integration for this product is currently in progress. Submitting this adoption request notifies platform administration of your deployment interest.
              </p>

              {/* Plan Choice if available */}
              {requestedPlanId && (
                <div style={{ marginBottom: "1rem" }}>
                  <label htmlFor={requestPlanSelectId} style={{ display: "block", fontSize: "0.8rem", fontWeight: 600, marginBottom: "0.35rem" }}>
                    Preferred Plan Version
                  </label>
                  <input
                    id={requestPlanSelectId}
                    type="text"
                    className="form-control"
                    value={requestedPlanId}
                    readOnly
                    style={{ fontSize: "0.85rem", opacity: 0.8 }}
                  />
                </div>
              )}

              {/* Notes */}
              <div style={{ marginBottom: "1.25rem" }}>
                <label htmlFor={requestNotesId} style={{ display: "block", fontSize: "0.8rem", fontWeight: 600, marginBottom: "0.35rem" }}>
                  Adoption Notes (Optional)
                </label>
                <textarea
                  id={requestNotesId}
                  className="form-control"
                  rows={3}
                  maxLength={500}
                  placeholder="Estimated user count, target timeline, or special requirements..."
                  value={requestNotes}
                  onChange={(e) => setRequestNotes(e.target.value)}
                  style={{ fontSize: "0.85rem", resize: "vertical" }}
                />
              </div>

              {requestError && (
                <div
                  role="alert"
                  style={{
                    padding: "0.75rem",
                    borderRadius: "8px",
                    background: "var(--status-danger-bg)",
                    color: "var(--status-danger)",
                    fontSize: "0.85rem",
                    marginBottom: "1.25rem",
                  }}
                >
                  {requestError}
                </div>
              )}

              <div style={{ display: "flex", justifyContent: "flex-end", gap: "0.75rem" }}>
                <button
                  type="button"
                  className="btn btn-secondary btn-sm"
                  onClick={() => setRequestProductTarget(null)}
                  disabled={isSubmittingRequest}
                >
                  Cancel
                </button>
                <button
                  type="button"
                  className="btn btn-primary btn-sm"
                  onClick={() => void handleConfirmRequest()}
                  disabled={isSubmittingRequest}
                >
                  {isSubmittingRequest ? "Submitting..." : "Submit Request"}
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </AppShell>
  );
};
