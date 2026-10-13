/**
 * Product Status Badge Component.
 *
 * Renders consistent, high-contrast, theme-aware lifecycle badges.
 */

import React from "react";
import type { ProductStatus } from "../../api/types.ts";

interface ProductStatusBadgeProps {
  readonly status: ProductStatus;
}

const STATUS_CONFIG: Record<ProductStatus, { label: string; className: string }> = {
  draft: {
    label: "Draft",
    className: "badge-draft",
  },
  active: {
    label: "Active",
    className: "badge-success",
  },
  inactive: {
    label: "Inactive",
    className: "badge-inactive",
  },
  retired: {
    label: "Retired",
    className: "badge-retired",
  },
};

export const ProductStatusBadge: React.FC<ProductStatusBadgeProps> = ({ status }) => {
  const config = STATUS_CONFIG[status] || { label: status, className: "badge-default" };

  return (
    <span className={`badge ${config.className}`}>
      <span className="badge-dot" aria-hidden="true" />
      {config.label}
    </span>
  );
};
