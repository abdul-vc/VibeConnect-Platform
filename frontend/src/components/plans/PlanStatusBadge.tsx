/**
 * Plan & Version Status and Health Badges.
 *
 * Renders high-contrast, theme-aware, accessible lifecycle and catalog health badges.
 */

import React from "react";
import type { PlanCatalogHealth, PlanVersionStatus } from "../../api/types.ts";

interface PlanVersionStatusBadgeProps {
  readonly status: PlanVersionStatus;
}

const STATUS_CONFIG: Record<PlanVersionStatus, { label: string; className: string }> = {
  draft: {
    label: "Draft",
    className: "badge-draft",
  },
  active: {
    label: "Active",
    className: "badge-success",
  },
  retired: {
    label: "Retired",
    className: "badge-retired",
  },
};

export const PlanVersionStatusBadge: React.FC<PlanVersionStatusBadgeProps> = ({ status }) => {
  const config = STATUS_CONFIG[status] || { label: status, className: "badge-neutral" };

  return (
    <span className={`badge ${config.className}`}>
      <span className="badge-dot" aria-hidden="true" />
      {config.label}
    </span>
  );
};

interface CatalogHealthBadgeProps {
  readonly health: PlanCatalogHealth;
}

export const CatalogHealthBadge: React.FC<CatalogHealthBadgeProps> = ({ health }) => {
  const isHealthy = health === "healthy";
  return (
    <span className={`badge ${isHealthy ? "badge-success" : "badge-warning"}`}>
      <span className="badge-dot" aria-hidden="true" />
      {isHealthy ? "Healthy" : "Degraded"}
    </span>
  );
};
