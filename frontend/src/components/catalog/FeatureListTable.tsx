/**
 * Product Feature List Table Component.
 *
 * High-density desktop enterprise table with local scrolling for tablets
 * and adaptive responsive cards for mobile viewports (<768px).
 * Implements strict lifecycle action gating based on stored and ancestor statuses.
 */

import React from "react";
import type { ProductFeatureListItem } from "../../api/types.ts";
import { EditIcon, KeyIcon } from "../Icons.tsx";
import { CatalogStatusBadge } from "./CatalogStatusBadge.tsx";

interface FeatureListTableProps {
  readonly features: readonly ProductFeatureListItem[];
  readonly areAllActivationAncestorsActive: boolean;
  readonly onEdit: (feature: ProductFeatureListItem, triggerElement: HTMLElement) => void;
  readonly onActivate: (feature: ProductFeatureListItem) => void;
  readonly onRetire: (feature: ProductFeatureListItem, triggerElement: HTMLElement) => void;
  readonly onManageCapabilities: (feature: ProductFeatureListItem) => void;
}

export const FeatureListTable: React.FC<FeatureListTableProps> = ({
  features,
  areAllActivationAncestorsActive,
  onEdit,
  onActivate,
  onRetire,
  onManageCapabilities,
}) => {
  return (
    <div className="catalog-table-wrapper">
      {/* Desktop & Tablet Table View */}
      <div className="table-responsive desktop-tablet-view">
        <table className="enterprise-table" aria-label="Product Features">
          <thead>
            <tr>
              <th scope="col" style={{ width: "16%" }}>Feature Code</th>
              <th scope="col" style={{ width: "28%" }}>Name & Description</th>
              <th scope="col" style={{ width: "10%" }}>Order</th>
              <th scope="col" style={{ width: "12%" }}>Status</th>
              <th scope="col" style={{ width: "14%" }}>Capabilities</th>
              <th scope="col" style={{ width: "20%", textAlign: "right" }}>Actions</th>
            </tr>
          </thead>
          <tbody>
            {features.map((item) => {
              const isDraft = item.status === "draft";
              const isRetired = item.status === "retired";

              return (
                <tr key={item.id} className="table-row">
                  <td>
                    <span className="product-code-pill">{item.code}</span>
                  </td>
                  <td>
                    <div style={{ display: "flex", flexDirection: "column", gap: "0.2rem" }}>
                      <span className="catalog-item-name">{item.name}</span>
                      {item.description && (
                        <span className="catalog-item-desc">{item.description}</span>
                      )}
                    </div>
                  </td>
                  <td>
                    <span className="text-caption">{item.display_order}</span>
                  </td>
                  <td>
                    <CatalogStatusBadge status={item.status} />
                  </td>
                  <td>
                    <div style={{ display: "flex", alignItems: "center", gap: "0.35rem" }}>
                      <span className="badge badge-neutral" style={{ fontSize: "0.75rem" }}>
                        {item.active_capabilities_count} / {item.total_capabilities_count} Active
                      </span>
                    </div>
                  </td>
                  <td style={{ textAlign: "right" }}>
                    <div className="actions-cell">
                      <button
                        type="button"
                        className="btn btn-secondary btn-sm"
                        onClick={() => onManageCapabilities(item)}
                        aria-label={`${isRetired ? "View" : "Manage"} capabilities for ${item.name}`}
                      >
                        <KeyIcon size={14} />
                        <span>{isRetired ? "View Capabilities" : "Capabilities"}</span>
                      </button>

                      {isDraft && (
                        <button
                          type="button"
                          className="btn btn-secondary btn-sm btn-activate"
                          onClick={() => onActivate(item)}
                          disabled={!areAllActivationAncestorsActive}
                          title={!areAllActivationAncestorsActive ? "Parent product and module must both be Active to activate feature" : "Activate feature"}
                          aria-label={`Activate ${item.name}`}
                        >
                          Activate
                        </button>
                      )}

                      {!isRetired && (
                        <button
                          type="button"
                          className="btn btn-secondary btn-sm"
                          onClick={(e) => onEdit(item, e.currentTarget)}
                          aria-label={`Edit ${item.name}`}
                        >
                          <EditIcon size={14} />
                          Edit
                        </button>
                      )}

                      {!isRetired && (
                        <button
                          type="button"
                          className="btn btn-secondary btn-sm btn-retire"
                          onClick={(e) => onRetire(item, e.currentTarget)}
                          aria-label={`Retire ${item.name}`}
                        >
                          Retire
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Mobile Card List View (<768px) */}
      <div className="mobile-card-list">
        {features.map((item) => {
          const isDraft = item.status === "draft";
          const isRetired = item.status === "retired";

          return (
            <div key={item.id} className="mobile-catalog-card">
              <div className="mobile-card-top">
                <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                  <span className="product-code-pill">{item.code}</span>
                  <span className="text-caption">Order: {item.display_order}</span>
                </div>
                <CatalogStatusBadge status={item.status} />
              </div>

              <div className="mobile-card-middle">
                <h3 className="mobile-item-title">{item.name}</h3>
                {item.description && (
                  <p className="mobile-item-desc">{item.description}</p>
                )}
                <div style={{ marginTop: "0.35rem" }}>
                  <span className="badge badge-neutral" style={{ fontSize: "0.75rem" }}>
                    {item.active_capabilities_count} / {item.total_capabilities_count} Active Capabilities
                  </span>
                </div>
              </div>

              <div className="mobile-card-actions">
                <button
                  type="button"
                  className="btn btn-secondary btn-sm"
                  onClick={() => onManageCapabilities(item)}
                  style={{ flex: 1, minHeight: "44px" }}
                >
                  <KeyIcon size={14} />
                  <span>{isRetired ? "View Capabilities" : "Capabilities"}</span>
                </button>

                {isDraft && (
                  <button
                    type="button"
                    className="btn btn-secondary btn-sm btn-activate"
                    onClick={() => onActivate(item)}
                    disabled={!areAllActivationAncestorsActive}
                    title={!areAllActivationAncestorsActive ? "Parent product and module must both be Active to activate feature" : "Activate feature"}
                    style={{ minHeight: "44px" }}
                  >
                    Activate
                  </button>
                )}

                {!isRetired && (
                  <button
                    type="button"
                    className="btn btn-secondary btn-sm"
                    onClick={(e) => onEdit(item, e.currentTarget)}
                    style={{ minHeight: "44px" }}
                  >
                    <EditIcon size={14} />
                    Edit
                  </button>
                )}

                {!isRetired && (
                  <button
                    type="button"
                    className="btn btn-secondary btn-sm btn-retire"
                    onClick={(e) => onRetire(item, e.currentTarget)}
                    style={{ minHeight: "44px" }}
                  >
                    Retire
                  </button>
                )}
              </div>
            </div>
          );
        })}
      </div>

      <style>{`
        .catalog-table-wrapper {
          background: var(--glass-surface-elevated);
          border: 1px solid var(--border-glass);
          border-radius: 12px;
          overflow: hidden;
          box-shadow: var(--shadow-sm);
        }

        .table-responsive {
          width: 100%;
          overflow-x: auto;
        }

        .enterprise-table {
          width: 100%;
          border-collapse: collapse;
          text-align: left;
          font-size: 0.875rem;
        }

        .enterprise-table thead th {
          background: var(--glass-surface-sunken);
          padding: 0.875rem 1.25rem;
          font-size: 0.75rem;
          font-weight: 600;
          color: var(--text-secondary);
          text-transform: uppercase;
          letter-spacing: 0.04em;
          border-bottom: 1px solid var(--border-subtle);
        }

        .enterprise-table tbody td {
          padding: 1rem 1.25rem;
          border-bottom: 1px solid var(--border-subtle);
          vertical-align: middle;
        }

        .table-row:last-child td {
          border-bottom: none;
        }

        .table-row:hover {
          background: var(--glass-surface-hover);
        }

        .catalog-item-name {
          font-weight: 600;
          color: var(--text-primary);
          font-size: 0.875rem;
          overflow-wrap: anywhere;
        }

        .catalog-item-desc {
          font-size: 0.78125rem;
          color: var(--text-secondary);
          line-height: 1.4;
          display: -webkit-box;
          -webkit-line-clamp: 2;
          -webkit-box-orient: vertical;
          overflow: hidden;
        }

        .actions-cell {
          display: inline-flex;
          align-items: center;
          justify-content: flex-end;
          gap: 0.4rem;
          flex-wrap: wrap;
        }

        .btn-activate {
          color: var(--status-success);
        }

        .btn-activate:hover:not(:disabled) {
          border-color: var(--status-success-border);
          background: var(--status-success-bg);
        }

        .btn-retire {
          color: var(--status-danger);
        }

        .btn-retire:hover:not(:disabled) {
          border-color: var(--status-danger-border);
          background: var(--status-danger-bg);
        }

        /* Mobile Card List */
        .mobile-card-list {
          display: none;
          flex-direction: column;
          gap: 0.75rem;
          padding: 0.75rem;
        }

        .mobile-catalog-card {
          background: var(--glass-surface);
          border: 1px solid var(--border-subtle);
          border-radius: 10px;
          padding: 1rem;
          display: flex;
          flex-direction: column;
          gap: 0.75rem;
        }

        .mobile-card-top {
          display: flex;
          align-items: center;
          justify-content: space-between;
          flex-wrap: wrap;
          gap: 0.5rem;
        }

        .mobile-item-title {
          font-size: 0.9375rem;
          font-weight: 600;
          color: var(--text-primary);
          margin: 0;
          overflow-wrap: anywhere;
        }

        .mobile-item-desc {
          font-size: 0.8125rem;
          color: var(--text-secondary);
          margin: 0.25rem 0 0 0;
          line-height: 1.4;
        }

        .mobile-card-actions {
          display: flex;
          align-items: center;
          gap: 0.5rem;
          flex-wrap: wrap;
          padding-top: 0.75rem;
          border-top: 1px solid var(--border-subtle);
        }

        @media (max-width: 767px) {
          .desktop-tablet-view {
            display: none;
          }
          .mobile-card-list {
            display: flex;
          }
        }
      `}</style>
    </div>
  );
};
