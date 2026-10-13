/**
 * Suspend / Reactivate Subscription Dialog.
 *
 * Platform Owner dialog to either suspend an active subscription or reactivate a suspended subscription.
 */

import React, { useEffect, useId, useRef, useState } from "react";
import { subscriptionsApi } from "../../api/subscriptions.ts";
import type { SubscriptionDetail } from "../../api/types.ts";
import {
  FormErrorBanner,
  PlanModalShell,
  parseApiErrors,
} from "../plans/PlanModalShell.tsx";
import { AlertCircleIcon, CheckCircleIcon } from "../Icons.tsx";

interface SuspendReactivateDialogProps {
  readonly mode: "suspend" | "reactivate";
  readonly isOpen: boolean;
  readonly onClose: () => void;
  readonly onSuccess: (updatedSubscription: SubscriptionDetail) => void;
  readonly subscription: SubscriptionDetail;
  readonly triggerRef?: React.RefObject<HTMLElement | null>;
}

export const SuspendReactivateDialog: React.FC<SuspendReactivateDialogProps> = ({
  mode,
  isOpen,
  onClose,
  onSuccess,
  subscription,
  triggerRef,
}) => {
  const baseId = useId();
  const [reason, setReason] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [generalError, setGeneralError] = useState<string | null>(null);

  const inputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    if (isOpen) {
      setReason("");
      setGeneralError(null);
      setIsSubmitting(false);
    }
  }, [isOpen]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setGeneralError(null);
    setIsSubmitting(true);

    try {
      let updated: SubscriptionDetail;
      if (mode === "suspend") {
        updated = await subscriptionsApi.suspend(subscription.id, {
          reason: reason.trim() || undefined,
        });
      } else {
        updated = await subscriptionsApi.reactivate(subscription.id);
      }
      onSuccess(updated);
      onClose();
    } catch (err: unknown) {
      const { generalError: gError } = parseApiErrors(err);
      setGeneralError(
        gError || `Failed to ${mode === "suspend" ? "suspend" : "reactivate"} subscription.`
      );
    } finally {
      setIsSubmitting(false);
    }
  };

  const isSuspend = mode === "suspend";

  return (
    <PlanModalShell
      isOpen={isOpen}
      onClose={onClose}
      isSubmitting={isSubmitting}
      title={isSuspend ? "Suspend Subscription" : "Reactivate Subscription"}
      subtitle={
        isSuspend
          ? `Temporarily pause access for ${subscription.organization_name}.`
          : `Restore active access for ${subscription.organization_name}.`
      }
      triggerRef={triggerRef}
      initialFocusRef={isSuspend ? inputRef : undefined}
      onSubmit={handleSubmit}
      submitLabel={isSuspend ? "Suspend Subscription" : "Reactivate Subscription"}
      submittingLabel={isSuspend ? "Suspending..." : "Reactivating..."}
      submitVariant={isSuspend ? "danger" : "primary"}
      maxWidth="500px"
    >
      <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
        <FormErrorBanner error={generalError} />

        {isSuspend ? (
          <>
            <div
              className="alert-box alert-warning"
              style={{ display: "flex", alignItems: "flex-start", gap: "0.75rem" }}
              role="note"
            >
              <AlertCircleIcon size={18} style={{ flexShrink: 0, marginTop: "2px" }} />
              <div style={{ fontSize: "0.875rem", lineHeight: 1.4 }}>
                Suspending will put the organization into suspended state. Entitlement snapshots are preserved and can be restored at any time by reactivating.
              </div>
            </div>

            <div className="form-group">
              <label htmlFor={`${baseId}-reason`} className="form-label">
                Suspension Reason (Optional)
              </label>
              <input
                id={`${baseId}-reason`}
                ref={inputRef}
                type="text"
                maxLength={255}
                className="form-input"
                placeholder="e.g., Non-payment or administrative review"
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                disabled={isSubmitting}
              />
            </div>
          </>
        ) : (
          <div
            className="alert-box alert-success"
            style={{ display: "flex", alignItems: "flex-start", gap: "0.75rem" }}
            role="note"
          >
            <CheckCircleIcon size={18} style={{ flexShrink: 0, marginTop: "2px" }} />
            <div style={{ fontSize: "0.875rem", lineHeight: 1.4 }}>
              Reactivating will immediately restore the subscription to <strong>Active</strong> status under <strong>{subscription.plan_name_snapshot} (v{subscription.version_number_snapshot})</strong>.
            </div>
          </div>
        )}
      </div>
    </PlanModalShell>
  );
};
