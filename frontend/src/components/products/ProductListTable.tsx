/**
 * Product List Table Component.
 *
 * High-density enterprise table for desktop/tablet viewports and
 * adaptive responsive card list for mobile viewports (<768px).
 */

import React from "react";
import type { ProductListItem } from "../../api/types.ts";
import { EditIcon, LayersIcon } from "../Icons.tsx";
import { ProductStatusBadge } from "./ProductStatusBadge.tsx";

interface ProductListTableProps {
  readonly products: readonly ProductListItem[];
  readonly onEdit: (product: ProductListItem, triggerElement: HTMLElement) => void;
  readonly onManageCatalog?: (product: ProductListItem) => void;
}

export const ProductListTable: React.FC<ProductListTableProps> = ({
  products,
  onEdit,
  onManageCatalog,
}) => {
  const formatDate = (isoString: string) => {
    try {
      const d = new Date(isoString);
      return d.toLocaleDateString("en-US", {
        year: "numeric",
        month: "short",
        day: "numeric",
      });
    } catch {
      return isoString;
    }
  };

  return (
    <div className="product-table-container">
      {/* Desktop & Tablet Table */}
      <div className="table-responsive desktop-tablet-view">
        <table className="enterprise-table" aria-label="Product Catalog">
          <thead>
            <tr>
              <th scope="col" style={{ width: "14%" }}>Product Code</th>
              <th scope="col" style={{ width: "30%" }}>Name & Description</th>
              <th scope="col" style={{ width: "16%" }}>Status</th>
              <th scope="col" style={{ width: "16%" }}>Registered</th>
              <th scope="col" style={{ width: "24%", textAlign: "right" }}>Actions</th>
            </tr>
          </thead>
          <tbody>
            {products.map((item) => (
              <tr key={item.id} className="table-row">
                <td>
                  <span className="product-code-pill">{item.code}</span>
                </td>
                <td>
                  <div style={{ display: "flex", flexDirection: "column", gap: "0.2rem" }}>
                    <span className="product-name">{item.name}</span>
                    {item.description && (
                      <span className="product-description">{item.description}</span>
                    )}
                  </div>
                </td>
                <td>
                  <ProductStatusBadge status={item.status} />
                </td>
                <td>
                  <span className="text-caption">{formatDate(item.created_at)}</span>
                </td>
                <td style={{ textAlign: "right" }}>
                  <div
                    style={{
                      display: "inline-flex",
                      alignItems: "center",
                      gap: "0.5rem",
                      justifyContent: "flex-end",
                    }}
                  >
                    {onManageCatalog && (
                      <button
                        type="button"
                        className="btn btn-secondary btn-sm"
                        onClick={() => onManageCatalog(item)}
                        aria-label={`Manage Catalog for ${item.name}`}
                      >
                        <LayersIcon size={14} />
                        Manage Catalog
                      </button>
                    )}
                    <button
                      type="button"
                      className="btn btn-secondary btn-sm"
                      onClick={(e) => onEdit(item, e.currentTarget)}
                      aria-label={`Edit ${item.name}`}
                    >
                      <EditIcon size={14} />
                      Edit
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Mobile Card List View (<768px) */}
      <div className="mobile-card-list">
        {products.map((item) => (
          <div key={item.id} className="mobile-product-card">
            <div className="mobile-card-header">
              <span className="product-code-pill">{item.code}</span>
              <ProductStatusBadge status={item.status} />
            </div>
            <div className="mobile-card-body">
              <h3 className="mobile-product-name">{item.name}</h3>
              {item.description && (
                <p className="mobile-product-desc">{item.description}</p>
              )}
            </div>
            <div className="mobile-card-footer">
              <span className="text-caption">Registered {formatDate(item.created_at)}</span>
              <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
                {onManageCatalog && (
                  <button
                    type="button"
                    className="btn btn-secondary btn-sm"
                    onClick={() => onManageCatalog(item)}
                    aria-label={`Manage Catalog for ${item.name}`}
                    style={{ minHeight: "44px" }}
                  >
                    <LayersIcon size={14} />
                    Manage Catalog
                  </button>
                )}
                <button
                  type="button"
                  className="btn btn-secondary btn-sm"
                  onClick={(e) => onEdit(item, e.currentTarget)}
                  aria-label={`Edit ${item.name}`}
                  style={{ minHeight: "44px" }}
                >
                  <EditIcon size={14} />
                  Edit
                </button>
              </div>
            </div>
          </div>
        ))}
      </div>

      <style>{`
        .product-table-container {
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
          background: var(--bg-surface-subtle);
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
          background: var(--bg-surface-hover);
        }

        .product-code-pill {
          display: inline-flex;
          align-items: center;
          font-family: var(--font-code);
          font-size: 0.8125rem;
          font-weight: 500;
          letter-spacing: 0.02em;
          color: var(--brand-primary);
          background: var(--brand-primary-light);
          border: 1px solid rgba(99, 102, 241, 0.22);
          padding: 0.2rem 0.5625rem;
          border-radius: 6px;
          line-height: 1.2;
        }

        :root[data-theme="light"] .product-code-pill {
          color: var(--brand-primary);
          background: rgba(79, 70, 229, 0.08);
          border: 1px solid rgba(79, 70, 229, 0.2);
        }

        .product-name {
          font-weight: 600;
          color: var(--text-primary);
          font-size: 0.875rem;
        }

        .product-description {
          font-size: 0.78125rem;
          color: var(--text-secondary);
          line-height: 1.4;
          display: -webkit-box;
          -webkit-line-clamp: 2;
          -webkit-box-orient: vertical;
          overflow: hidden;
        }

        .btn-sm {
          padding: 0.35rem 0.75rem;
          font-size: 0.8125rem;
          display: inline-flex;
          align-items: center;
          gap: 0.375rem;
        }

        /* Mobile Card List */
        .mobile-card-list {
          display: none;
          flex-direction: column;
          gap: 0.75rem;
          padding: 0.75rem;
        }

        .mobile-product-card {
          background: var(--bg-surface);
          border: 1px solid var(--border-subtle);
          border-radius: 10px;
          padding: 1rem;
          display: flex;
          flex-direction: column;
          gap: 0.75rem;
        }

        .mobile-card-header {
          display: flex;
          align-items: center;
          justify-content: space-between;
        }

        .mobile-product-name {
          font-size: 0.9375rem;
          font-weight: 600;
          color: var(--text-primary);
          margin: 0;
        }

        .mobile-product-desc {
          font-size: 0.8125rem;
          color: var(--text-secondary);
          margin: 0.25rem 0 0 0;
          line-height: 1.4;
        }

        .mobile-card-footer {
          display: flex;
          align-items: center;
          justify-content: space-between;
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
