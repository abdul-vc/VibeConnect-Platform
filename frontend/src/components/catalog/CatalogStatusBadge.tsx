/**
 * Catalog Status Badge Component.
 *
 * Renders consistent lifecycle state pills for CatalogStatus values:
 * - draft: neutral badge
 * - active: success badge
 * - retired: danger badge
 */

import React from "react";
import type { CatalogStatus } from "../../api/types.ts";

interface CatalogStatusBadgeProps {
  readonly status: CatalogStatus | string;
}

export const CatalogStatusBadge: React.FC<CatalogStatusBadgeProps> = ({ status }) => {
  const normalized = (status || "").toLowerCase();

  switch (normalized) {
    case "active":
      return <span className="badge badge-success">Active</span>;
    case "retired":
      return <span className="badge badge-danger">Retired</span>;
    case "draft":
    default:
      return <span className="badge badge-neutral">Draft</span>;
  }
};
