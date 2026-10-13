/**
 * Subscription Entitlements Matrix Component.
 *
 * Displays the immutable hierarchy of subscription-owned entitlement snapshots:
 * - Packaged Products
 * - Packaged Modules
 * - Packaged Capabilities
 * - Commercial Quota Limits
 *
 * Strict isolation: direct organization product grants are separate and not intermingled.
 */

import React, { useCallback, useEffect, useState } from "react";
import { subscriptionsApi } from "../../api/subscriptions.ts";
import type {
  SubscriptionCapabilityEntitlement,
  SubscriptionEntitlementsResponse,
  SubscriptionModuleEntitlement,
  SubscriptionProductEntitlement,
  SubscriptionQuotaEntitlement,
} from "../../api/types.ts";
import {
  BoxIcon,
  GridIcon,
  KeyIcon,
  LayersIcon,
  ShieldCheckIcon,
} from "../Icons.tsx";

interface SubscriptionEntitlementsMatrixProps {
  readonly subscriptionId: string;
  readonly refreshKey?: number;
}

type EntitlementSubTab = "all" | "products" | "modules" | "capabilities" | "quotas";

export const SubscriptionEntitlementsMatrix: React.FC<SubscriptionEntitlementsMatrixProps> = ({
  subscriptionId,
  refreshKey = 0,
}) => {
  const [data, setData] = useState<SubscriptionEntitlementsResponse | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<EntitlementSubTab>("all");

  const fetchEntitlements = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const response = await subscriptionsApi.getEntitlements(subscriptionId);
      setData(response);
    } catch {
      setError("Unable to load subscription entitlement snapshots.");
    } finally {
      setIsLoading(false);
    }
  }, [subscriptionId]);

  useEffect(() => {
    fetchEntitlements();
  }, [fetchEntitlements, refreshKey]);

  if (isLoading) {
    return (
      <div className="registry-skeleton-container" aria-label="Loading entitlements snapshot">
        <div className="skeleton-row" style={{ height: "48px" }} />
        <div className="skeleton-row" style={{ height: "120px" }} />
      </div>
    );
  }

  if (error) {
    return (
      <div className="alert-banner alert-banner-error" role="alert">
        <span>{error}</span>
        <button
          type="button"
          className="btn btn-secondary btn-sm"
          onClick={fetchEntitlements}
          style={{ marginLeft: "auto" }}
        >
          Retry
        </button>
      </div>
    );
  }

  if (!data) return null;

  const { products, modules, capabilities, quotas } = data;
  const totalCount = products.length + modules.length + capabilities.length + quotas.length;

  return (
    <div className="entitlements-matrix-container">
      {/* Header Explanatory Strip */}
      <div className="matrix-header-strip">
        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
          <ShieldCheckIcon size={18} style={{ color: "var(--brand-primary)" }} />
          <h3 style={{ fontSize: "1rem", fontWeight: 700, color: "var(--text-primary)", margin: 0 }}>
            Subscription Entitlements Snapshot
          </h3>
          <span className="registry-count-badge">{totalCount} Entitlements</span>
        </div>
        <p className="text-caption" style={{ margin: "0.25rem 0 0 0", color: "var(--text-secondary)" }}>
          Immutable commercial rights provisioned for this subscription. Direct product grants are managed separately.
        </p>
      </div>

      {/* Sub-Filter Tabs */}
      <div className="matrix-tabs-bar" role="tablist" aria-label="Entitlement categories">
        <button
          type="button"
          role="tab"
          aria-selected={activeTab === "all"}
          className={`matrix-tab-btn ${activeTab === "all" ? "active" : ""}`}
          onClick={() => setActiveTab("all")}
        >
          All Items ({totalCount})
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={activeTab === "products"}
          className={`matrix-tab-btn ${activeTab === "products" ? "active" : ""}`}
          onClick={() => setActiveTab("products")}
        >
          <BoxIcon size={14} /> Products ({products.length})
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={activeTab === "modules"}
          className={`matrix-tab-btn ${activeTab === "modules" ? "active" : ""}`}
          onClick={() => setActiveTab("modules")}
        >
          <LayersIcon size={14} /> Modules ({modules.length})
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={activeTab === "capabilities"}
          className={`matrix-tab-btn ${activeTab === "capabilities" ? "active" : ""}`}
          onClick={() => setActiveTab("capabilities")}
        >
          <KeyIcon size={14} /> Capabilities ({capabilities.length})
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={activeTab === "quotas"}
          className={`matrix-tab-btn ${activeTab === "quotas" ? "active" : ""}`}
          onClick={() => setActiveTab("quotas")}
        >
          <GridIcon size={14} /> Quotas ({quotas.length})
        </button>
      </div>

      {/* 1. Packaged Products Section */}
      {(activeTab === "all" || activeTab === "products") && (
        <div className="matrix-section">
          <div className="section-title-row">
            <BoxIcon size={16} />
            <h4>Packaged Products ({products.length})</h4>
          </div>
          {products.length > 0 ? (
            <div className="matrix-items-grid">
              {products.map((prod: SubscriptionProductEntitlement) => (
                <div key={prod.id} className="matrix-card">
                  <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                    <span className="product-code-pill">{prod.product_code_snapshot}</span>
                    <span style={{ fontWeight: 600, color: "var(--text-primary)", fontSize: "0.875rem" }}>
                      {prod.product_name_snapshot}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="matrix-empty-row">No packaged products snapshotted in this subscription.</div>
          )}
        </div>
      )}

      {/* 2. Packaged Modules Section */}
      {(activeTab === "all" || activeTab === "modules") && (
        <div className="matrix-section">
          <div className="section-title-row">
            <LayersIcon size={16} />
            <h4>Packaged Modules ({modules.length})</h4>
          </div>
          {modules.length > 0 ? (
            <div className="matrix-items-grid">
              {modules.map((mod: SubscriptionModuleEntitlement) => (
                <div key={mod.id} className="matrix-card">
                  <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                    <span className="product-code-pill">{mod.module_code_snapshot}</span>
                    <span style={{ fontWeight: 600, color: "var(--text-primary)", fontSize: "0.875rem" }}>
                      {mod.module_name_snapshot}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="matrix-empty-row">No packaged modules snapshotted in this subscription.</div>
          )}
        </div>
      )}

      {/* 3. Packaged Capabilities Section */}
      {(activeTab === "all" || activeTab === "capabilities") && (
        <div className="matrix-section">
          <div className="section-title-row">
            <KeyIcon size={16} />
            <h4>Packaged Capabilities ({capabilities.length})</h4>
          </div>
          {capabilities.length > 0 ? (
            <div className="matrix-items-grid">
              {capabilities.map((cap: SubscriptionCapabilityEntitlement) => (
                <div key={cap.id} className="matrix-card">
                  <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                    <span className="product-code-pill">{cap.capability_code_snapshot}</span>
                    <span style={{ fontWeight: 600, color: "var(--text-primary)", fontSize: "0.875rem" }}>
                      {cap.capability_name_snapshot}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="matrix-empty-row">No packaged capabilities snapshotted in this subscription.</div>
          )}
        </div>
      )}

      {/* 4. Quotas Section */}
      {(activeTab === "all" || activeTab === "quotas") && (
        <div className="matrix-section">
          <div className="section-title-row">
            <GridIcon size={16} />
            <h4>Commercial Quota Limits ({quotas.length})</h4>
          </div>
          {quotas.length > 0 ? (
            <div className="quota-table-wrapper">
              {/* Desktop Quotas Presentation (>=768px) */}
              <div className="quota-desktop-view">
                <table className="data-table" aria-label="Subscription Quota Limits">
                  <thead>
                    <tr className="quota-desktop-grid quota-grid-header">
                      <th scope="col">Quota</th>
                      <th scope="col">Scope &amp; Target</th>
                      <th scope="col">Limit</th>
                      <th scope="col">Reset Period</th>
                      <th scope="col">Enforcement</th>
                    </tr>
                  </thead>
                  <tbody>
                    {quotas.map((q: SubscriptionQuotaEntitlement) => (
                      <tr key={q.id} className="table-row quota-desktop-grid">
                        <td>
                          <div style={{ display: "flex", flexDirection: "column", gap: "0.15rem" }}>
                            <span style={{ fontWeight: 600, color: "var(--text-primary)" }}>{q.name}</span>
                            <span className="code-pill" style={{ width: "fit-content" }}>
                              {q.quota_key}
                            </span>
                          </div>
                        </td>
                        <td>
                          <div style={{ display: "flex", flexDirection: "column", gap: "0.15rem" }}>
                            <span style={{ textTransform: "capitalize", fontWeight: 500 }}>
                              {q.scope} Scope
                            </span>
                            {q.target_code_snapshot && (
                              <span className="text-caption">
                                {q.target_name_snapshot} ({q.target_code_snapshot})
                              </span>
                            )}
                          </div>
                        </td>
                        <td>
                          <span style={{ fontWeight: 700, color: "var(--brand-primary)" }}>
                            {q.limit_type === "unlimited" ? "Unlimited" : `${q.limit_value} ${q.unit}`}
                          </span>
                        </td>
                        <td>
                          <span style={{ textTransform: "capitalize", fontSize: "0.8125rem" }}>
                            {q.reset_period}
                          </span>
                        </td>
                        <td>
                          <span
                            className={`status-badge ${q.is_hard_limit ? "badge-danger" : "badge-neutral"}`}
                            style={{ fontSize: "0.75rem" }}
                          >
                            {q.is_hard_limit ? "Hard Limit" : "Soft Limit"}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {/* Mobile Quotas Presentation (<768px Stacked Cards) */}
              <div className="quota-mobile-view">
                {quotas.map((q: SubscriptionQuotaEntitlement) => (
                  <div key={q.id} className="matrix-card" style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: "0.5rem" }}>
                      <div>
                        <span style={{ fontWeight: 600, color: "var(--text-primary)", fontSize: "0.875rem" }}>{q.name}</span>
                        <span className="code-pill" style={{ display: "block", width: "fit-content", marginTop: "0.2rem" }}>
                          {q.quota_key}
                        </span>
                      </div>
                      <span className={`status-badge ${q.is_hard_limit ? "badge-danger" : "badge-neutral"}`} style={{ fontSize: "0.75rem" }}>
                        {q.is_hard_limit ? "Hard Limit" : "Soft Limit"}
                      </span>
                    </div>
                    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.5rem", fontSize: "0.8125rem", paddingTop: "0.35rem", borderTop: "1px solid var(--border-subtle)" }}>
                      <div>
                        <span className="text-caption" style={{ color: "var(--text-muted)" }}>Scope / Target</span>
                        <p style={{ margin: "0.1rem 0 0 0", textTransform: "capitalize" }}>
                          {q.scope}{q.target_code_snapshot ? ` (${q.target_code_snapshot})` : ""}
                        </p>
                      </div>
                      <div>
                        <span className="text-caption" style={{ color: "var(--text-muted)" }}>Limit</span>
                        <p style={{ margin: "0.1rem 0 0 0", fontWeight: 700, color: "var(--brand-primary)" }}>
                          {q.limit_type === "unlimited" ? "Unlimited" : `${q.limit_value} ${q.unit}`}
                        </p>
                      </div>
                      <div>
                        <span className="text-caption" style={{ color: "var(--text-muted)" }}>Reset Period</span>
                        <p style={{ margin: "0.1rem 0 0 0", textTransform: "capitalize" }}>
                          {q.reset_period}
                        </p>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <div className="matrix-empty-row">No commercial quotas snapshotted in this subscription.</div>
          )}
        </div>
      )}

      <style>{`
        .entitlements-matrix-container {
          background: var(--glass-surface-elevated);
          border: 1px solid var(--border-glass);
          border-radius: 14px;
          padding: 1.5rem;
          display: flex;
          flex-direction: column;
          gap: 1.25rem;
          box-shadow: var(--shadow-sm);
        }

        .matrix-header-strip {
          display: flex;
          flex-direction: column;
          gap: 0.25rem;
          padding-bottom: 0.75rem;
          border-bottom: 1px solid var(--border-subtle);
        }

        .matrix-tabs-bar {
          display: flex;
          align-items: center;
          gap: 0.5rem;
          flex-wrap: wrap;
        }

        .matrix-tab-btn {
          display: inline-flex;
          align-items: center;
          gap: 0.4rem;
          padding: 0.4rem 0.8rem;
          border-radius: 8px;
          font-size: 0.8125rem;
          font-weight: 500;
          color: var(--text-secondary);
          background: var(--glass-surface);
          border: 1px solid var(--border-subtle);
          cursor: pointer;
          transition: all 0.15s ease;
        }

        .matrix-tab-btn:hover {
          background: var(--glass-surface-hover);
          color: var(--text-primary);
        }

        .matrix-tab-btn.active {
          background: var(--brand-primary-light);
          color: var(--brand-primary);
          border-color: var(--brand-primary);
          font-weight: 600;
        }

        .matrix-section {
          display: flex;
          flex-direction: column;
          gap: 0.75rem;
        }

        .section-title-row {
          display: flex;
          align-items: center;
          gap: 0.5rem;
          color: var(--text-secondary);
        }

        .section-title-row h4 {
          font-size: 0.875rem;
          font-weight: 600;
          text-transform: uppercase;
          letter-spacing: 0.05em;
          margin: 0;
          color: var(--text-primary);
        }

        .matrix-items-grid {
          display: grid;
          grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
          gap: 0.625rem;
        }

        .matrix-card {
          padding: 0.75rem 1rem;
          background: var(--glass-surface);
          border: 1px solid var(--border-subtle);
          border-radius: 8px;
          display: flex;
          align-items: center;
          justify-content: space-between;
        }

        .quota-table-wrapper {
          overflow-x: auto;
          border: 1px solid var(--border-subtle);
          border-radius: 8px;
          background: var(--glass-surface);
        }

        .matrix-empty-row {
          padding: 1rem;
          text-align: center;
          font-size: 0.8125rem;
          font-style: italic;
          color: var(--text-muted);
          background: var(--glass-surface);
          border: 1px dashed var(--border-subtle);
          border-radius: 8px;
        }
      `}</style>
    </div>
  );
};
