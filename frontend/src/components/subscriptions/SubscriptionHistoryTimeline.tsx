/**
 * Subscription History & Predecessor Timeline Component.
 *
 * Displays the complete chronological lineage of subscriptions provisioned for an organization,
 * showing status transitions, plan upgrades/downgrades, and successor linkages.
 */

import React, { useCallback, useEffect, useState } from "react";
import { formatCurrencyDisplay } from "../../api/plans.ts";
import { subscriptionsApi } from "../../api/subscriptions.ts";
import type { SubscriptionListItem } from "../../api/types.ts";
import { CalendarIcon, HistoryIcon } from "../Icons.tsx";
import { SubscriptionStatusBadge } from "./SubscriptionStatusBadge.tsx";

interface SubscriptionHistoryTimelineProps {
  readonly organizationId: string;
  readonly currentSubscriptionId?: string;
  readonly refreshKey?: number;
}

export const SubscriptionHistoryTimeline: React.FC<SubscriptionHistoryTimelineProps> = ({
  organizationId,
  currentSubscriptionId,
  refreshKey = 0,
}) => {
  const [history, setHistory] = useState<SubscriptionListItem[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const fetchHistory = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const res = await subscriptionsApi.list({
        organization_id: organizationId,
        ordering: "-created_at",
        page_size: 50,
      });
      setHistory(res.results as SubscriptionListItem[]);
    } catch {
      setError("Unable to load subscription history.");
    } finally {
      setIsLoading(false);
    }
  }, [organizationId]);

  useEffect(() => {
    fetchHistory();
  }, [fetchHistory, refreshKey]);

  const formatDate = (dateStr?: string | null) => {
    if (!dateStr) return "—";
    try {
      return new Date(dateStr).toLocaleDateString("en-US", {
        month: "short",
        day: "numeric",
        year: "numeric",
      });
    } catch {
      return dateStr;
    }
  };

  const formatDateTime = (dateStr?: string | null) => {
    if (!dateStr) return "—";
    try {
      return new Date(dateStr).toLocaleString("en-US", {
        month: "short",
        day: "numeric",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      });
    } catch {
      return dateStr;
    }
  };

  if (isLoading) {
    return (
      <div className="registry-skeleton-container" aria-label="Loading subscription history">
        <div className="skeleton-row" style={{ height: "60px" }} />
        <div className="skeleton-row" style={{ height: "60px" }} />
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
          onClick={fetchHistory}
          style={{ marginLeft: "auto" }}
        >
          Retry
        </button>
      </div>
    );
  }

  if (history.length === 0) {
    return (
      <div className="timeline-empty-card">
        <HistoryIcon size={24} style={{ color: "var(--text-muted)" }} />
        <span className="text-caption" style={{ fontStyle: "italic" }}>
          No subscription lifecycle history recorded for this organization yet.
        </span>
      </div>
    );
  }

  return (
    <div className="subscription-timeline-container">
      <div className="timeline-header">
        <HistoryIcon size={16} style={{ color: "var(--brand-primary)" }} />
        <h3 style={{ fontSize: "0.9375rem", fontWeight: 700, margin: 0, color: "var(--text-primary)" }}>
          Subscription Lifecycle History ({history.length})
        </h3>
      </div>

      <div className="timeline-list">
        {history.map((item, index) => {
          const isCurrent = item.id === currentSubscriptionId;
          return (
            <div key={item.id} className={`timeline-node ${isCurrent ? "node-current" : ""}`}>
              <div className="timeline-marker-column">
                <div className={`timeline-dot ${isCurrent ? "dot-active" : ""}`} />
                {index < history.length - 1 && <div className="timeline-line" />}
              </div>

              <div className="timeline-content-card">
                <div className="timeline-card-header">
                  <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", flexWrap: "wrap" }}>
                    <span className="product-code-pill">{item.plan_code_snapshot}</span>
                    <span style={{ fontWeight: 600, color: "var(--text-primary)" }}>
                      {item.plan_name_snapshot}
                    </span>
                    <span className="product-code-pill">v{item.version_number_snapshot}</span>
                    <SubscriptionStatusBadge status={item.status} size="sm" />
                    {isCurrent && (
                      <span className="badge-primary" style={{ fontSize: "0.6875rem", padding: "0.15rem 0.4rem", borderRadius: "4px" }}>
                        Current
                      </span>
                    )}
                  </div>

                  <span className="text-caption" style={{ color: "var(--text-muted)" }}>
                    {formatDateTime(item.created_at)}
                  </span>
                </div>

                <div className="timeline-card-body">
                  <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", flexWrap: "wrap" }}>
                    <span style={{ fontWeight: 600, color: "var(--text-primary)", fontSize: "0.8125rem" }}>
                      {formatCurrencyDisplay(item.amount, item.currency)} / {item.billing_interval}
                    </span>
                    <span className="text-caption">
                      <CalendarIcon size={12} style={{ display: "inline", verticalAlign: "middle", marginRight: "4px" }} />
                      {item.started_as_trial
                        ? `Trial: ${formatDate(item.trial_started_at)} – ${formatDate(item.trial_ends_at)}`
                        : `Period: ${formatDate(item.current_period_start)} – ${formatDate(item.current_period_end)}`}
                    </span>
                  </div>

                  {item.change_reason && (
                    <div className="text-caption" style={{ color: "var(--text-secondary)" }}>
                      <strong>Reason:</strong> {item.change_reason}
                    </div>
                  )}

                  {item.cancellation_reason && (
                    <div className="text-caption" style={{ color: "var(--status-danger)" }}>
                      <strong>Cancellation Reason:</strong> {item.cancellation_reason}
                    </div>
                  )}

                  {item.suspension_reason && (
                    <div className="text-caption" style={{ color: "var(--status-warning)" }}>
                      <strong>Suspension Reason:</strong> {item.suspension_reason}
                    </div>
                  )}

                  {item.previous_subscription_id && (
                    <div className="text-caption" style={{ color: "var(--text-muted)" }}>
                      Predecessor: {item.previous_subscription_id.slice(0, 8)}…
                    </div>
                  )}
                </div>
              </div>
            </div>
          );
        })}
      </div>

      <style>{`
        .subscription-timeline-container {
          background: var(--glass-surface-elevated);
          border: 1px solid var(--border-glass);
          border-radius: 14px;
          padding: 1.5rem;
          display: flex;
          flex-direction: column;
          gap: 1.25rem;
          box-shadow: var(--shadow-sm);
        }

        .timeline-header {
          display: flex;
          align-items: center;
          gap: 0.5rem;
          padding-bottom: 0.75rem;
          border-bottom: 1px solid var(--border-subtle);
        }

        .timeline-empty-card {
          padding: 2rem;
          background: var(--glass-surface-elevated);
          border: 1px dashed var(--border-subtle);
          border-radius: 12px;
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          gap: 0.5rem;
          text-align: center;
        }

        .timeline-list {
          display: flex;
          flex-direction: column;
          gap: 0;
        }

        .timeline-node {
          display: flex;
          gap: 1rem;
          position: relative;
        }

        .timeline-marker-column {
          display: flex;
          flex-direction: column;
          align-items: center;
          width: 16px;
          flex-shrink: 0;
        }

        .timeline-dot {
          width: 12px;
          height: 12px;
          border-radius: 50%;
          background: var(--border-strong);
          border: 2px solid var(--bg-app);
          margin-top: 6px;
          z-index: 1;
        }

        .timeline-dot.dot-active {
          background: var(--brand-primary);
          box-shadow: 0 0 0 3px var(--brand-primary-light);
        }

        .timeline-line {
          width: 2px;
          flex: 1;
          background: var(--border-subtle);
          margin: 4px 0;
        }

        .timeline-content-card {
          flex: 1;
          background: var(--glass-surface);
          border: 1px solid var(--border-subtle);
          border-radius: 10px;
          padding: 0.875rem 1rem;
          margin-bottom: 1rem;
          display: flex;
          flex-direction: column;
          gap: 0.5rem;
        }

        .node-current .timeline-content-card {
          border-color: var(--brand-primary);
          background: var(--glass-surface-hover);
        }

        .timeline-card-header {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 0.75rem;
          flex-wrap: wrap;
        }

        .timeline-card-body {
          display: flex;
          flex-direction: column;
          gap: 0.35rem;
        }
      `}</style>
    </div>
  );
};
