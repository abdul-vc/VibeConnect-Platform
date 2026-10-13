/**
 * Subscription Status Badge Component.
 *
 * Renders consistent, accessible status badges for subscription lifecycle states:
 * - trialing: In-progress evaluation period (badge-primary/info)
 * - active: Active commercial paid subscription (badge-success)
 * - suspended: Suspended service (badge-warning)
 * - cancelled: Explicitly cancelled subscription (badge-danger)
 * - expired: Expired trial / term (badge-neutral)
 */

import React from "react";
import type { SubscriptionStatus } from "../../api/types.ts";

interface SubscriptionStatusBadgeProps {
  readonly status: SubscriptionStatus;
  readonly size?: "sm" | "md";
}

export const SubscriptionStatusBadge: React.FC<SubscriptionStatusBadgeProps> = ({
  status,
  size = "md",
}) => {
  const getBadgeConfig = (s: SubscriptionStatus) => {
    switch (s) {
      case "active":
        return {
          label: "Active Paid",
          className: "badge-success",
          dotColor: "var(--status-success)",
        };
      case "trialing":
        return {
          label: "Trialing",
          className: "badge-primary",
          dotColor: "var(--brand-primary)",
        };
      case "suspended":
        return {
          label: "Suspended",
          className: "badge-warning",
          dotColor: "var(--status-warning)",
        };
      case "cancelled":
        return {
          label: "Cancelled",
          className: "badge-danger",
          dotColor: "var(--status-danger)",
        };
      case "expired":
        return {
          label: "Expired",
          className: "badge-neutral",
          dotColor: "var(--text-muted)",
        };
      default:
        return {
          label: s,
          className: "badge-neutral",
          dotColor: "var(--text-muted)",
        };
    }
  };

  const config = getBadgeConfig(status);

  return (
    <span
      className={`status-badge ${config.className} ${size === "sm" ? "badge-sm" : ""}`}
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: "0.375rem",
        fontWeight: 600,
        textTransform: "capitalize",
      }}
    >
      <span
        style={{
          width: size === "sm" ? "6px" : "7px",
          height: size === "sm" ? "6px" : "7px",
          borderRadius: "50%",
          backgroundColor: config.dotColor,
          flexShrink: 0,
        }}
        aria-hidden="true"
      />
      <span>{config.label}</span>
    </span>
  );
};
