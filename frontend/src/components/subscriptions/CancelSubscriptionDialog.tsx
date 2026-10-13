/**
 * Cancel Subscription Dialog.
 *
 * Platform Owner confirmation dialog to cancel an active/trialing/suspended subscription.
 * Cancellation is an irreversible terminal state.
 */

import React, { useEffect, useId, useRef, useState } from "react";
import { subscriptionsApi } from "../../api/subscriptions.ts";
import type { SubscriptionDetail } from "../../api/types.ts";
import {
  FormErrorBanner,
  PlanModalShell,
  parseApiErrors,
} from "../plans/PlanModalShell.tsx";
import { AlertCircleIcon } from "../Icons.tsx";

interface CancelSubscriptionDialogProps {
  readonly isOpen: boolean;
  readonly onClose: () => void;
  readonly onSuccess: (cancelledSub: SubscriptionDetail) => void;
  readonly subscription: SubscriptionDetail;
  readonly triggerRef?: React.RefObject<HTMLElement | null>;
}

export const CancelSubscriptionDialog: React.FC<CancelSubscriptionDialogProps> = ({
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

  const reasonInputRef = useRef<HTMLInputElement | null>(null);

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
      const cancelled = await subscriptionsApi.cancel(subscription.id, {
        reason: reason.trim() || undefined,
      });
      onSuccess(cancelled);
      onClose();
    } catch (err: unknown) {
      const { generalError: gError } = parseApiErrors(err);
      setGeneralError(gError || "Failed to cancel subscription.");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <PlanModalShell
      isOpen={isOpen}
      onClose={onClose}
      isSubmitting={isSubmitting}
      title="Cancel Subscription"
      subtitle={`Permanently cancel subscription for ${subscription.organization_name}.`}
      triggerRef={triggerRef}
      initialFocusRef={reasonInputRef}
      onSubmit={handleSubmit}
      submitLabel="Yes, Cancel Subscription"
      submittingLabel="Cancelling..."
      submitVariant="danger"
      maxWidth="500px"
    >
      <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
        <FormErrorBanner error={generalError} />

        {/* Warning Callout */}
        <div
          className="alert-box alert-danger"
          style={{ display: "flex", alignItems: "flex-start", gap: "0.75rem" }}
          role="alert"
        >
          <AlertCircleIcon size={18} style={{ flexShrink: 0, marginTop: "2px" }} />
          <div style={{ fontSize: "0.875rem", lineHeight: 1.4 }}>
            <strong>Warning: This action cannot be undone.</strong>
            <p style={{ margin: "0.25rem 0 0 0" }}>
              Cancelling will immediately terminate access under <strong>{subscription.plan_name_snapshot}</strong>. The organization will have no active subscription until a new one is created.
            </p>
          </div>
        </div>

        {/* Cancellation Reason */}
        <div className="form-group">
          <label htmlFor={`${baseId}-reason`} className="form-label">
            Cancellation Reason (Optional)
          </label>
          <input
            id={`${baseId}-reason`}
            ref={reasonInputRef}
            type="text"
            maxLength={255}
            className="form-input"
            placeholder="e.g., Customer requested termination"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            disabled={isSubmitting}
          />
        </div>
      </div>
    </PlanModalShell>
  );
};
