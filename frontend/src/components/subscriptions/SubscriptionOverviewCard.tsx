/**
 * Subscription Overview Card Component.
 *
 * Displays commercial terms snapshot, lifecycle status, trial or billing period dates,
 * provenance metadata, and status-driven lifecycle action triggers.
 */

import React, { useState } from "react";
import { formatCurrencyDisplay } from "../../api/plans.ts";
import { subscriptionsApi } from "../../api/subscriptions.ts";
import type { SubscriptionDetail } from "../../api/types.ts";
import {
  AlertCircleIcon,
  CalendarIcon,
  CheckCircleIcon,
  EditIcon,
  RotateCcwIcon,
  ShieldCheckIcon,
  SlidersIcon,
} from "../Icons.tsx";
import { CancelSubscriptionDialog } from "./CancelSubscriptionDialog.tsx";
import { ChangePlanDialog } from "./ChangePlanDialog.tsx";
import { SubscriptionStatusBadge } from "./SubscriptionStatusBadge.tsx";
import { SuspendReactivateDialog } from "./SuspendReactivateDialog.tsx";

interface SubscriptionOverviewCardProps {
  readonly subscription: SubscriptionDetail;
  readonly onSubscriptionUpdated: (updatedSubscription: SubscriptionDetail) => void;
  readonly onReconciled?: () => void;
  readonly isOrganizationRetired?: boolean;
}

export const SubscriptionOverviewCard: React.FC<SubscriptionOverviewCardProps> = ({
  subscription,
  onSubscriptionUpdated,
  onReconciled,
  isOrganizationRetired = false,
}) => {
  const [isChangePlanOpen, setIsChangePlanOpen] = useState(false);
  const [isCancelOpen, setIsCancelOpen] = useState(false);
  const [isSuspendOpen, setIsSuspendOpen] = useState(false);
  const [isReactivateOpen, setIsReactivateOpen] = useState(false);
  const [isConverting, setIsConverting] = useState(false);
  const [isReconciling, setIsReconciling] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionSuccess, setActionSuccess] = useState<string | null>(null);

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

  const handleConvertTrial = async () => {
    setActionError(null);
    setActionSuccess(null);
    setIsConverting(true);
    try {
      const converted = await subscriptionsApi.convertTrial(subscription.id);
      setActionSuccess("Trial successfully converted to Active Paid subscription.");
      onSubscriptionUpdated(converted);
    } catch (err: unknown) {
      const apiErr = err as { data?: { detail?: string | string[] } };
      const msg = Array.isArray(apiErr?.data?.detail)
        ? apiErr.data.detail.join(" ")
        : typeof apiErr?.data?.detail === "string"
        ? apiErr.data.detail
        : "Failed to convert trial to active paid.";
      setActionError(msg);
    } finally {
      setIsConverting(false);
    }
  };

  const handleReconcile = async () => {
    setActionError(null);
    setActionSuccess(null);
    setIsReconciling(true);
    try {
      const res = await subscriptionsApi.reconcile(subscription.id);
      if (res.repaired_count > 0) {
        setActionSuccess(`Reconciliation completed. Repaired ${res.repaired_count} missing snapshot records.`);
      } else {
        setActionSuccess("Reconciliation completed. Entitlement snapshots are in full sync with the plan version blueprint.");
      }
      if (onReconciled) onReconciled();
    } catch (err: unknown) {
      const apiErr = err as { data?: { detail?: string | string[] } };
      const msg = Array.isArray(apiErr?.data?.detail)
        ? apiErr.data.detail.join(" ")
        : typeof apiErr?.data?.detail === "string"
        ? apiErr.data.detail
        : "Failed to reconcile subscription entitlements.";
      setActionError(msg);
    } finally {
      setIsReconciling(false);
    }
  };

  const isTerminal = subscription.status === "cancelled" || subscription.status === "expired";
  const isTrialing = subscription.status === "trialing";
  const isActive = subscription.status === "active";
  const isSuspended = subscription.status === "suspended";

  return (
    <div className="subscription-overview-card">
      {/* Notifications / Alerts */}
      {actionError && (
        <div className="alert-box alert-danger" role="alert" style={{ marginBottom: "1rem" }}>
          <AlertCircleIcon size={16} style={{ flexShrink: 0 }} />
          <span>{actionError}</span>
        </div>
      )}

      {actionSuccess && (
        <div className="alert-box alert-success" role="status" style={{ marginBottom: "1rem" }}>
          <CheckCircleIcon size={16} style={{ flexShrink: 0 }} />
          <span>{actionSuccess}</span>
        </div>
      )}

      {/* Header Bar */}
      <div className="card-header-bar">
        <div style={{ display: "flex", flexDirection: "column", gap: "0.25rem" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "0.625rem", flexWrap: "wrap" }}>
            <span className="product-code-pill" style={{ fontSize: "0.875rem" }}>
              {subscription.plan_code_snapshot}
            </span>
            <h2 style={{ fontSize: "1.25rem", fontWeight: 700, color: "var(--text-primary)", margin: 0 }}>
              {subscription.plan_name_snapshot}
            </h2>
            <span className="product-code-pill">v{subscription.version_number_snapshot}</span>
            <SubscriptionStatusBadge status={subscription.status} />
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", flexWrap: "wrap", marginTop: "0.25rem" }}>
            <span style={{ fontSize: "1.125rem", fontWeight: 700, color: "var(--brand-primary)" }}>
              {formatCurrencyDisplay(subscription.amount, subscription.currency)}
            </span>
            <span className="text-caption" style={{ textTransform: "capitalize" }}>
              per {subscription.billing_interval}
            </span>
            {subscription.started_as_trial && (
              <span className="text-caption" style={{ color: "var(--text-muted)", fontStyle: "italic" }}>
                (Origin: Trial)
              </span>
            )}
            {subscription.previous_subscription_id && (
              <span className="text-caption" style={{ color: "var(--text-secondary)" }}>
                • Predecessor ID: {subscription.previous_subscription_id.slice(0, 8)}…
              </span>
            )}
          </div>
        </div>

        {/* Action Controls */}
        <div className="action-buttons-group">
          {isOrganizationRetired ? (
            <span
              className="text-caption"
              style={{
                fontStyle: "italic",
                color: "var(--text-muted)",
                padding: "0.4rem 0.6rem",
                background: "var(--glass-surface)",
                border: "1px solid var(--border-subtle)",
                borderRadius: "6px",
              }}
            >
              Organization retired — subscription actions disabled
            </span>
          ) : (
            <>
              {/* Reconcile Snapshot Button */}
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                onClick={handleReconcile}
                disabled={isReconciling}
                title="Reconcile missing product/module/capability/quota snapshots against plan blueprint"
                aria-label="Reconcile subscription entitlements"
              >
                <RotateCcwIcon size={14} />
                <span>{isReconciling ? "Reconciling..." : "Reconcile Snapshots"}</span>
              </button>

              {/* Trialing Actions */}
              {isTrialing && (
                <>
                  <button
                    type="button"
                    className="btn btn-primary btn-sm"
                    onClick={handleConvertTrial}
                    disabled={isConverting}
                    title="Convert trial immediately to paid active subscription"
                  >
                    <CheckCircleIcon size={14} />
                    <span>{isConverting ? "Converting..." : "Convert to Paid"}</span>
                  </button>
                  <button
                    type="button"
                    className="btn btn-secondary btn-sm"
                    onClick={() => setIsChangePlanOpen(true)}
                  >
                    <EditIcon size={14} />
                    <span>Change Plan</span>
                  </button>
                  <button
                    type="button"
                    className="btn btn-secondary btn-sm"
                    onClick={() => setIsSuspendOpen(true)}
                  >
                    <SlidersIcon size={14} />
                    <span>Suspend</span>
                  </button>
                  <button
                    type="button"
                    className="btn btn-danger-action btn-sm"
                    onClick={() => setIsCancelOpen(true)}
                  >
                    <span>Cancel</span>
                  </button>
                </>
              )}

              {/* Active Actions */}
              {isActive && (
                <>
                  <button
                    type="button"
                    className="btn btn-secondary btn-sm"
                    onClick={() => setIsChangePlanOpen(true)}
                  >
                    <EditIcon size={14} />
                    <span>Change Plan</span>
                  </button>
                  <button
                    type="button"
                    className="btn btn-secondary btn-sm"
                    onClick={() => setIsSuspendOpen(true)}
                  >
                    <SlidersIcon size={14} />
                    <span>Suspend</span>
                  </button>
                  <button
                    type="button"
                    className="btn btn-danger-action btn-sm"
                    onClick={() => setIsCancelOpen(true)}
                  >
                    <span>Cancel</span>
                  </button>
                </>
              )}

              {/* Suspended Actions */}
              {isSuspended && (
                <>
                  <button
                    type="button"
                    className="btn btn-primary btn-sm"
                    onClick={() => setIsReactivateOpen(true)}
                  >
                    <ShieldCheckIcon size={14} />
                    <span>Reactivate</span>
                  </button>
                  <button
                    type="button"
                    className="btn btn-secondary btn-sm"
                    onClick={() => setIsChangePlanOpen(true)}
                  >
                    <EditIcon size={14} />
                    <span>Change Plan</span>
                  </button>
                  <button
                    type="button"
                    className="btn btn-danger-action btn-sm"
                    onClick={() => setIsCancelOpen(true)}
                  >
                    <span>Cancel</span>
                  </button>
                </>
              )}

              {/* Terminal Read-only message */}
              {isTerminal && (
                <span
                  className="text-caption"
                  style={{
                    fontStyle: "italic",
                    color: "var(--text-muted)",
                    padding: "0.4rem 0.6rem",
                    background: "var(--glass-surface)",
                    borderRadius: "6px",
                  }}
                >
                  Subscription is closed and read-only.
                </span>
              )}
            </>
          )}
        </div>
      </div>

      {/* Commercial & Lifecycle Grid */}
      <div className="overview-details-grid">
        {/* Trial Period Info */}
        {subscription.trial_started_at && (
          <div className="overview-metric-cell">
            <span className="metric-label">
              <CalendarIcon size={14} />
              Trial Period
            </span>
            <span className="metric-value">
              {formatDate(subscription.trial_started_at)} – {formatDate(subscription.trial_ends_at)}
            </span>
          </div>
        )}

        {/* Current Billing Period */}
        <div className="overview-metric-cell">
          <span className="metric-label">
            <CalendarIcon size={14} />
            Current Period
          </span>
          <span className="metric-value">
            {formatDate(subscription.current_period_start)} – {formatDate(subscription.current_period_end)}
          </span>
        </div>

        {/* Terminal Timestamps if applicable */}
        {subscription.cancelled_at && (
          <div className="overview-metric-cell">
            <span className="metric-label" style={{ color: "var(--status-danger)" }}>
              Cancelled At
            </span>
            <span className="metric-value">
              {formatDateTime(subscription.cancelled_at)}
            </span>
          </div>
        )}

        {subscription.ended_at && (
          <div className="overview-metric-cell">
            <span className="metric-label" style={{ color: "var(--text-muted)" }}>
              Ended At
            </span>
            <span className="metric-value">
              {formatDateTime(subscription.ended_at)}
            </span>
          </div>
        )}

        {/* Created / Updated Provenance */}
        <div className="overview-metric-cell">
          <span className="metric-label">Provisioned At</span>
          <span className="metric-value">
            {formatDateTime(subscription.created_at)}
          </span>
          {subscription.created_by_email && (
            <span className="text-caption" style={{ color: "var(--text-muted)" }}>
              by {subscription.created_by_email}
            </span>
          )}
        </div>

        <div className="overview-metric-cell">
          <span className="metric-label">Last Transition</span>
          <span className="metric-value">
            {formatDateTime(subscription.updated_at)}
          </span>
          {subscription.updated_by_email && (
            <span className="text-caption" style={{ color: "var(--text-muted)" }}>
              by {subscription.updated_by_email}
            </span>
          )}
        </div>
      </div>

      {/* Reasons Row (if present) */}
      {(subscription.change_reason || subscription.suspension_reason || subscription.cancellation_reason) && (
        <div className="reasons-banner">
          {subscription.change_reason && (
            <div>
              <strong>Change Reason:</strong> {subscription.change_reason}
            </div>
          )}
          {subscription.suspension_reason && (
            <div style={{ color: "var(--status-warning)" }}>
              <strong>Suspension Reason:</strong> {subscription.suspension_reason}
            </div>
          )}
          {subscription.cancellation_reason && (
            <div style={{ color: "var(--status-danger)" }}>
              <strong>Cancellation Reason:</strong> {subscription.cancellation_reason}
            </div>
          )}
        </div>
      )}

      {/* Action Dialogs */}
      <ChangePlanDialog
        isOpen={isChangePlanOpen}
        onClose={() => setIsChangePlanOpen(false)}
        onSuccess={(successor) => {
          setActionSuccess(`Subscription plan changed to ${successor.plan_name_snapshot} v${successor.version_number_snapshot}.`);
          onSubscriptionUpdated(successor);
        }}
        subscription={subscription}
      />

      <CancelSubscriptionDialog
        isOpen={isCancelOpen}
        onClose={() => setIsCancelOpen(false)}
        onSuccess={(cancelled) => {
          setActionSuccess("Subscription cancelled.");
          onSubscriptionUpdated(cancelled);
        }}
        subscription={subscription}
      />

      <SuspendReactivateDialog
        mode="suspend"
        isOpen={isSuspendOpen}
        onClose={() => setIsSuspendOpen(false)}
        onSuccess={(suspended) => {
          setActionSuccess("Subscription suspended.");
          onSubscriptionUpdated(suspended);
        }}
        subscription={subscription}
      />

      <SuspendReactivateDialog
        mode="reactivate"
        isOpen={isReactivateOpen}
        onClose={() => setIsReactivateOpen(false)}
        onSuccess={(reactivated) => {
          setActionSuccess("Subscription reactivated to Active Paid status.");
          onSubscriptionUpdated(reactivated);
        }}
        subscription={subscription}
      />

      <style>{`
        .subscription-overview-card {
          background: var(--glass-surface-elevated);
          border: 1px solid var(--border-glass);
          border-radius: 14px;
          padding: 1.5rem;
          box-shadow: var(--shadow-sm);
          display: flex;
          flex-direction: column;
          gap: 1.25rem;
        }

        .card-header-bar {
          display: flex;
          align-items: flex-start;
          justify-content: space-between;
          gap: 1.25rem;
          flex-wrap: wrap;
        }

        .action-buttons-group {
          display: flex;
          align-items: center;
          gap: 0.5rem;
          flex-wrap: wrap;
        }

        .overview-details-grid {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
          gap: 1rem;
          padding-top: 1rem;
          border-top: 1px solid var(--border-subtle);
        }

        .overview-metric-cell {
          display: flex;
          flex-direction: column;
          gap: 0.25rem;
        }

        .metric-label {
          font-size: 0.75rem;
          font-weight: 600;
          text-transform: uppercase;
          letter-spacing: 0.05em;
          color: var(--text-muted);
          display: flex;
          align-items: center;
          gap: 0.35rem;
        }

        .metric-value {
          font-size: 0.875rem;
          font-weight: 600;
          color: var(--text-primary);
        }

        .reasons-banner {
          padding: 0.75rem 1rem;
          background: var(--glass-surface);
          border: 1px solid var(--border-glass);
          border-radius: 8px;
          font-size: 0.8125rem;
          display: flex;
          flex-direction: column;
          gap: 0.35rem;
          line-height: 1.4;
        }

        @media (max-width: 640px) {
          .card-header-bar {
            flex-direction: column;
            align-items: stretch;
          }
          .action-buttons-group {
            width: 100%;
          }
        }
      `}</style>
    </div>
  );
};
