/**
 * Entitlement Status Badge Component.
 *
 * Renders consistent, accessible lifecycle state indicators matching VibeConnect design tokens.
 */

import React from "react";
import type { EntitlementStatus } from "../../api/types.ts";

interface EntitlementStatusBadgeProps {
  readonly status: EntitlementStatus;
}

const STATUS_CONFIG: Record<
  EntitlementStatus,
  { label: string; bg: string; color: string; border: string }
> = {
  draft: {
    label: "Draft",
    bg: "var(--status-neutral-bg)",
    color: "var(--status-neutral)",
    border: "var(--status-neutral-border)",
  },
  active: {
    label: "Active",
    bg: "var(--status-success-bg)",
    color: "var(--status-success)",
    border: "var(--status-success-border)",
  },
  suspended: {
    label: "Suspended",
    bg: "var(--status-warning-bg)",
    color: "var(--status-warning)",
    border: "var(--status-warning-border)",
  },
  revoked: {
    label: "Revoked",
    bg: "var(--status-danger-bg)",
    color: "var(--status-danger)",
    border: "var(--status-danger-border)",
  },
};

export const EntitlementStatusBadge: React.FC<EntitlementStatusBadgeProps> = ({ status }) => {
  const config = STATUS_CONFIG[status] || STATUS_CONFIG.draft;

  return (
    <span
      className="entitlement-status-badge"
      style={{
        display: "inline-flex",
        alignItems: "center",
        padding: "0.2rem 0.6rem",
        borderRadius: "9999px",
        fontSize: "0.75rem",
        fontWeight: 600,
        textTransform: "capitalize",
        letterSpacing: "0.02em",
        background: config.bg,
        color: config.color,
        border: `1px solid ${config.border}`,
        whiteSpace: "nowrap",
      }}
    >
      {config.label}
    </span>
  );
};
