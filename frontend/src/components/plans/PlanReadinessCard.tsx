/**
 * Version Activation Readiness and Catalog Health Card.
 *
 * Displays Ready/Not Ready status, blockers, warnings, catalog health,
 * price/product counts, and stale catalog items cleanly.
 */

import React from "react";
import type { PlanReadinessResponse, PlanVersionStatus } from "../../api/types.ts";
import { AlertCircleIcon, CheckCircleIcon } from "../Icons.tsx";
import { CatalogHealthBadge } from "./PlanStatusBadge.tsx";

interface PlanReadinessCardProps {
  readonly readiness: PlanReadinessResponse | null;
  readonly isLoading: boolean;
  readonly versionStatus?: PlanVersionStatus | string;
  readonly onRefresh?: () => void;
}

export const PlanReadinessCard: React.FC<PlanReadinessCardProps> = ({
  readiness,
  isLoading,
  versionStatus = "draft",
  onRefresh,
}) => {
  if (isLoading) {
    return (
      <div className="plan-readiness-card" aria-busy="true">
        <div className="readiness-header">
          <div className="skeleton-row" style={{ width: "160px", height: "24px" }} />
          <div className="skeleton-row" style={{ width: "100px", height: "24px" }} />
        </div>
        <div style={{ marginTop: "1rem" }}>
          <div className="skeleton-row" style={{ width: "100%", height: "40px" }} />
        </div>
      </div>
    );
  }

  if (!readiness) {
    return null;
  }

  const { is_ready, blockers, warnings, prices_count, products_count, catalog_health, stale_items } =
    readiness;

  const isDraft = versionStatus === "draft";
  const isActive = versionStatus === "active";
  const isRetired = versionStatus === "retired";

  const sectionTitle = isDraft ? "Activation Readiness" : "Configuration Health";
  const cardAriaLabel = isDraft
    ? "Version activation readiness"
    : isRetired
    ? "Retired version configuration health snapshot"
    : "Active version configuration health";

  return (
    <div className="plan-readiness-card" aria-label={cardAriaLabel}>
      <div className="readiness-header">
        <div className="readiness-title-row">
          <span className="readiness-section-title">{sectionTitle}</span>
          {isDraft ? (
            <span
              className={`badge ${is_ready ? "badge-success" : "badge-danger"}`}
              style={{ fontSize: "0.8125rem", padding: "0.25rem 0.65rem" }}
            >
              {is_ready ? (
                <>
                  <CheckCircleIcon size={14} />
                  Ready for Activation
                </>
              ) : (
                <>
                  <AlertCircleIcon size={14} />
                  Not Ready ({blockers.length} {blockers.length === 1 ? "Blocker" : "Blockers"})
                </>
              )}
            </span>
          ) : isActive ? (
            <span
              className="badge badge-success"
              style={{ fontSize: "0.8125rem", padding: "0.25rem 0.65rem" }}
            >
              <CheckCircleIcon size={14} />
              Active Configuration
            </span>
          ) : (
            <span
              className="badge badge-neutral"
              style={{ fontSize: "0.8125rem", padding: "0.25rem 0.65rem" }}
            >
              <CheckCircleIcon size={14} />
              Retired Configuration Snapshot
            </span>
          )}
          <CatalogHealthBadge health={catalog_health} />
        </div>

        {onRefresh && (
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            onClick={onRefresh}
            style={{ fontSize: "0.75rem", padding: "0.25rem 0.5rem" }}
          >
            {isDraft ? "Refresh Readiness" : "Refresh Health"}
          </button>
        )}
      </div>

      {/* Metric Counters */}
      <div className="readiness-metrics-bar">
        <div className="readiness-metric-item">
          <span className="metric-label">Configured Prices</span>
          <span className="metric-value">{prices_count}</span>
        </div>
        <div className="readiness-metric-item">
          <span className="metric-label">Packaged Products</span>
          <span className="metric-value">{products_count}</span>
        </div>
        <div className="readiness-metric-item">
          <span className="metric-label">Stale Items</span>
          <span className="metric-value" style={{ color: stale_items.length > 0 ? "var(--status-warning)" : undefined }}>
            {stale_items.length}
          </span>
        </div>
      </div>

      {/* Blockers List */}
      {blockers.length > 0 && (
        <div className="readiness-issues-section blockers-section" role="alert">
          <h4 className="readiness-issues-title blockers-title">
            <AlertCircleIcon size={16} />
            {isDraft ? "Activation Blockers" : "Configuration Issues"} ({blockers.length})
          </h4>
          <ul className="readiness-issues-list">
            {blockers.map((b, idx) => (
              <li key={idx} className="readiness-issue-item blocker-item">
                {b}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Warnings List */}
      {warnings.length > 0 && (
        <div className="readiness-issues-section warnings-section">
          <h4 className="readiness-issues-title warnings-title">
            <AlertCircleIcon size={16} />
            Warnings ({warnings.length})
          </h4>
          <ul className="readiness-issues-list">
            {warnings.map((w, idx) => (
              <li key={idx} className="readiness-issue-item warning-item">
                {w}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Stale Catalog Items */}
      {stale_items.length > 0 && (
        <div className="readiness-stale-section">
          <h4 className="readiness-stale-title">Degraded Catalog References</h4>
          <div className="stale-items-grid">
            {stale_items.map((item) => (
              <div key={`${item.type}-${item.id}`} className="stale-item-pill">
                <span className="stale-type-tag">{item.type}</span>
                <span className="stale-code">{item.code}</span>
                <span className="stale-name">{item.name}</span>
                <span className="stale-status-muted">({item.status})</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};
