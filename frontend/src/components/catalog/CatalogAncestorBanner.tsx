/**
 * Catalog Ancestor Context Banner Component.
 *
 * Displays verified ancestor metadata (Product, Module, Feature),
 * lifecycle status badges, and critical operational warnings when
 * an ancestor is inactive or retired.
 */

import React from "react";
import { AlertCircleIcon, BoxIcon, LayersIcon, SlidersIcon } from "../Icons.tsx";
import { CatalogStatusBadge } from "./CatalogStatusBadge.tsx";
import { ProductStatusBadge } from "../products/ProductStatusBadge.tsx";

export interface AncestorContextItem {
  readonly type: "product" | "module" | "feature";
  readonly id: string;
  readonly code: string;
  readonly name: string;
  readonly status: string;
}

interface CatalogAncestorBannerProps {
  readonly ancestors: readonly AncestorContextItem[];
}

export const CatalogAncestorBanner: React.FC<CatalogAncestorBannerProps> = ({ ancestors }) => {
  const productAncestor = ancestors.find((a) => a.type === "product");
  const isProductDraft = productAncestor?.status === "draft";
  const isProductInactive = productAncestor?.status === "inactive";
  const isProductRetired = productAncestor?.status === "retired";

  const retiredNonProductAncestors = ancestors.filter((a) => a.type !== "product" && a.status === "retired");
  const draftNonProductAncestors = ancestors.filter((a) => a.type !== "product" && a.status === "draft");

  // Hierarchy is terminal if product or any ancestor in the chain is retired
  const isHierarchyTerminal = isProductRetired || retiredNonProductAncestors.length > 0;

  const getIcon = (type: "product" | "module" | "feature") => {
    switch (type) {
      case "product":
        return <BoxIcon size={16} />;
      case "module":
        return <LayersIcon size={16} />;
      case "feature":
        return <SlidersIcon size={16} />;
    }
  };

  const renderAncestorItems = (items: readonly AncestorContextItem[]) => {
    return items.map((item, idx) => (
      <React.Fragment key={item.id}>
        {idx > 0 && (idx === items.length - 1 ? " and " : ", ")}
        {item.type.charAt(0).toUpperCase() + item.type.slice(1)} (<code>{item.code}</code>)
      </React.Fragment>
    ));
  };

  return (
    <div className="ancestor-banner-container">
      {/* Ancestor Context Summary Cards */}
      <div className="ancestor-cards-grid">
        {ancestors.map((item) => (
          <div key={`${item.type}-${item.id}`} className="ancestor-card">
            <div className="ancestor-card-header">
              <span className="ancestor-icon" aria-hidden="true">
                {getIcon(item.type)}
              </span>
              <span className="ancestor-type-label">
                {item.type.charAt(0).toUpperCase() + item.type.slice(1)}
              </span>
              <div style={{ marginLeft: "auto" }}>
                {item.type === "product" ? (
                  <ProductStatusBadge status={item.status as any} />
                ) : (
                  <CatalogStatusBadge status={item.status as any} />
                )}
              </div>
            </div>
            <div className="ancestor-card-body">
              <span className="product-code-pill ancestor-code-pill">{item.code}</span>
              <span className="ancestor-name" title={item.name}>
                {item.name}
              </span>
            </div>
          </div>
        ))}
      </div>

      {/* Product Draft Notice */}
      {isProductDraft && (
        <div className="alert-box alert-info-custom" role="status">
          <AlertCircleIcon size={18} style={{ flexShrink: 0, marginTop: "0.15rem" }} />
          <div>
            <strong>Product Draft Notice:</strong> Parent product is currently in{" "}
            <span className="badge badge-neutral">Draft</span> status. Catalog definitions may be
            prepared as Draft. Descendant activation requires Product activation.
          </div>
        </div>
      )}

      {/* Product Inactive Notice */}
      {isProductInactive && (
        <div className="alert-box alert-warning-custom" role="status">
          <AlertCircleIcon size={18} style={{ flexShrink: 0, marginTop: "0.15rem" }} />
          <div>
            <strong>Operational Availability Notice:</strong> Parent product is currently{" "}
            <span className="badge badge-warning">Inactive</span>. Existing descendants are
            operationally unavailable. Draft creation and metadata preparation remain allowed.
            Activation is blocked until Product becomes active.
          </div>
        </div>
      )}

      {/* Product Retired Notice */}
      {isProductRetired && (
        <div className="alert-box alert-danger-custom" role="status">
          <AlertCircleIcon size={18} style={{ flexShrink: 0, marginTop: "0.15rem" }} />
          <div>
            <strong>Terminal Product Notice:</strong> Parent product is{" "}
            <span className="badge badge-danger">Retired</span>. Terminal read-only product hierarchy.
            New catalog children cannot be created. Existing descendants should already be retired.
          </div>
        </div>
      )}

      {/* Module / Feature Draft Notice */}
      {!isHierarchyTerminal && draftNonProductAncestors.length > 0 && (
        <div className="alert-box alert-info-custom" role="status">
          <AlertCircleIcon size={18} style={{ flexShrink: 0, marginTop: "0.15rem" }} />
          <div>
            <strong>Ancestor Draft Notice:</strong>{" "}
            {draftNonProductAncestors.length === 1 ? (
              <>
                Parent {renderAncestorItems(draftNonProductAncestors)} is currently in{" "}
                <span className="badge badge-neutral">Draft</span> status.
              </>
            ) : (
              <>
                Ancestors {renderAncestorItems(draftNonProductAncestors)} are currently in{" "}
                <span className="badge badge-neutral">Draft</span> status.
              </>
            )}{" "}
            Child definitions may be prepared as Draft if hierarchy is non-retired. Child activation
            requires every ancestor to be Active.
          </div>
        </div>
      )}

      {/* Module / Feature Retired Notice */}
      {!isProductRetired && retiredNonProductAncestors.length > 0 && (
        <div className="alert-box alert-danger-custom" role="status">
          <AlertCircleIcon size={18} style={{ flexShrink: 0, marginTop: "0.15rem" }} />
          <div>
            <strong>Terminal Ancestor Notice:</strong>{" "}
            {retiredNonProductAncestors.length === 1 ? (
              <>
                Parent {renderAncestorItems(retiredNonProductAncestors)} is{" "}
                <span className="badge badge-danger">Retired</span>.
              </>
            ) : (
              <>
                Ancestors {renderAncestorItems(retiredNonProductAncestors)} are{" "}
                <span className="badge badge-danger">Retired</span>.
              </>
            )}{" "}
            Terminal context. New children cannot be created.
          </div>
        </div>
      )}

      <style>{`
        .ancestor-banner-container {
          display: flex;
          flex-direction: column;
          gap: 0.75rem;
          width: 100%;
        }

        .ancestor-cards-grid {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
          gap: 0.75rem;
        }

        .ancestor-card {
          background: var(--glass-surface);
          border: 1px solid var(--border-glass);
          border-radius: 10px;
          padding: 0.75rem 1rem;
          display: flex;
          flex-direction: column;
          gap: 0.4rem;
          box-shadow: var(--shadow-sm);
        }

        .ancestor-card-header {
          display: flex;
          align-items: center;
          gap: 0.5rem;
        }

        .ancestor-icon {
          color: var(--brand-primary);
          display: flex;
          align-items: center;
        }

        .ancestor-type-label {
          font-size: 0.75rem;
          font-weight: 600;
          color: var(--text-muted);
          text-transform: uppercase;
          letter-spacing: 0.04em;
        }

        .ancestor-card-body {
          display: flex;
          align-items: center;
          gap: 0.5rem;
          min-width: 0;
        }

        .ancestor-code-pill {
          font-size: 0.75rem;
          padding: 0.15rem 0.45rem;
          flex-shrink: 0;
        }

        .ancestor-name {
          font-size: 0.875rem;
          font-weight: 600;
          color: var(--text-primary);
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }

        .alert-info-custom {
          background: var(--status-neutral-bg);
          border: 1px solid var(--status-neutral-border);
          color: var(--text-primary);
          border-radius: 8px;
          padding: 0.75rem 1rem;
          display: flex;
          align-items: flex-start;
          gap: 0.65rem;
          font-size: 0.8125rem;
          line-height: 1.45;
        }

        .alert-warning-custom {
          background: var(--status-warning-bg);
          border: 1px solid var(--status-warning-border);
          color: var(--text-primary);
          border-radius: 8px;
          padding: 0.75rem 1rem;
          display: flex;
          align-items: flex-start;
          gap: 0.65rem;
          font-size: 0.8125rem;
          line-height: 1.45;
        }

        .alert-danger-custom {
          background: var(--status-danger-bg);
          border: 1px solid var(--status-danger-border);
          color: var(--text-primary);
          border-radius: 8px;
          padding: 0.75rem 1rem;
          display: flex;
          align-items: flex-start;
          gap: 0.65rem;
          font-size: 0.8125rem;
          line-height: 1.45;
        }
      `}</style>
    </div>
  );
};
