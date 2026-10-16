/**
 * Approve Access Request Modal (Phase 3F).
 *
 * Confirms product seat grant and ceiling validation.
 * Displays seat limit or eligibility warnings if capacity is reached.
 */

import React, { useId, useRef, useState, useEffect } from "react";
import { accessRequestsApi } from "../../api/accessRequests.ts";
import { ApiError } from "../../api/client.ts";
import type { AccessRequestItem } from "../../api/types.ts";
import { CheckCircleIcon, CloseIcon, AlertCircleIcon } from "../Icons.tsx";
import { useDialogAccessibility } from "../plans/PlanModalShell.tsx";

interface ApproveRequestModalProps {
  readonly isOpen: boolean;
  readonly requestItem: AccessRequestItem | null;
  readonly onClose: () => void;
  readonly onSuccess: () => void;
  readonly triggerRef?: React.RefObject<HTMLElement | null>;
}

export const ApproveRequestModal: React.FC<ApproveRequestModalProps> = ({
  isOpen,
  requestItem,
  onClose,
  onSuccess,
  triggerRef,
}) => {
  const baseId = useId();
  const inputRef = useRef<HTMLTextAreaElement | null>(null);

  const [reason, setReason] = useState("");
  const [generalError, setGeneralError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const { dialogRef } = useDialogAccessibility({
    isOpen,
    isSubmitting,
    onClose,
    triggerRef,
    initialFocusRef: inputRef,
  });

  useEffect(() => {
    if (isOpen) {
      setReason("");
      setGeneralError(null);
      setIsSubmitting(false);
    }
  }, [isOpen]);

  if (!isOpen || !requestItem) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSubmitting(true);
    setGeneralError(null);

    try {
      await accessRequestsApi.approveRequest(requestItem.id, {
        reason: reason.trim(),
      });
      onSuccess();
      onClose();
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        if (err.status === 409) {
          setGeneralError(
            err.message ||
              "Seat capacity limit reached or request state changed. Cannot grant access at this time."
          );
        } else {
          setGeneralError(err.message || "Failed to approve access request.");
        }
      } else {
        setGeneralError("An unexpected error occurred while approving request.");
      }
      setIsSubmitting(false);
    }
  };

  const reasonId = `${baseId}-reason`;
  const generalErrorId = `${baseId}-general-error`;

  return (
    <div
      role="presentation"
      style={{
        position: "fixed",
        inset: 0,
        backgroundColor: "rgba(0, 0, 0, 0.6)",
        backdropFilter: "blur(4px)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 1000,
        padding: "1rem",
      }}
      onClick={(e) => {
        if (e.target === e.currentTarget && !isSubmitting) onClose();
      }}
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={`${baseId}-title`}
        aria-describedby={`${baseId}-desc`}
        style={{
          backgroundColor: "var(--bg-card, #1e293b)",
          color: "var(--text-primary, #f8fafc)",
          borderRadius: "0.75rem",
          border: "1px solid var(--border-color, #334155)",
          boxShadow: "0 25px 50px -12px rgba(0, 0, 0, 0.5)",
          maxWidth: "32rem",
          width: "100%",
          overflow: "hidden",
        }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            padding: "1.25rem 1.5rem",
            borderBottom: "1px solid var(--border-color, #334155)",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
            <div
              style={{
                width: "2rem",
                height: "2rem",
                borderRadius: "9999px",
                backgroundColor: "rgba(34, 197, 94, 0.15)",
                color: "#22c55e",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
              }}
            >
              <CheckCircleIcon size={18} />
            </div>
            <h2
              id={`${baseId}-title`}
              style={{ fontSize: "1.125rem", fontWeight: 600, margin: 0 }}
            >
              Approve Access Request
            </h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            disabled={isSubmitting}
            aria-label="Close dialog"
            style={{
              background: "transparent",
              border: "none",
              color: "var(--text-muted, #94a3b8)",
              cursor: isSubmitting ? "not-allowed" : "pointer",
              padding: "0.25rem",
              borderRadius: "0.375rem",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
            }}
          >
            <CloseIcon size={18} />
          </button>
        </div>

        <form onSubmit={handleSubmit} style={{ padding: "1.5rem" }}>
          <p
            id={`${baseId}-desc`}
            style={{
              fontSize: "0.875rem",
              color: "var(--text-secondary, #cbd5e1)",
              marginTop: 0,
              marginBottom: "1rem",
              lineHeight: 1.5,
            }}
          >
            Granting product seat assignment for{" "}
            <strong>{requestItem.requester_name || requestItem.requester_email}</strong> to{" "}
            <strong>{requestItem.product_name || requestItem.product_code || "Product"}</strong>.
            This action validates current seat availability and creates an active assignment immediately.
          </p>

          {generalError && (
            <div
              id={generalErrorId}
              role="alert"
              style={{
                display: "flex",
                alignItems: "center",
                gap: "0.5rem",
                padding: "0.75rem 1rem",
                backgroundColor: "rgba(239, 68, 68, 0.1)",
                border: "1px solid rgba(239, 68, 68, 0.3)",
                borderRadius: "0.5rem",
                color: "#f87171",
                fontSize: "0.875rem",
                marginBottom: "1rem",
              }}
            >
              <AlertCircleIcon size={16} />
              <span>{generalError}</span>
            </div>
          )}

          <div style={{ marginBottom: "1.25rem" }}>
            <label
              htmlFor={reasonId}
              style={{
                display: "block",
                fontSize: "0.875rem",
                fontWeight: 500,
                marginBottom: "0.5rem",
                color: "var(--text-primary, #f8fafc)",
              }}
            >
              Approval Notes (Optional)
            </label>
            <textarea
              id={reasonId}
              ref={inputRef}
              rows={3}
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              disabled={isSubmitting}
              maxLength={500}
              placeholder="Add optional notes or authorization details..."
              style={{
                width: "100%",
                padding: "0.625rem 0.75rem",
                backgroundColor: "var(--bg-input, #0f172a)",
                border: "1px solid var(--border-color, #334155)",
                borderRadius: "0.375rem",
                color: "var(--text-primary, #f8fafc)",
                fontSize: "0.875rem",
                outline: "none",
                resize: "vertical",
                boxSizing: "border-box",
              }}
            />
          </div>

          <div
            style={{
              display: "flex",
              justifyContent: "flex-end",
              gap: "0.75rem",
            }}
          >
            <button
              type="button"
              onClick={onClose}
              disabled={isSubmitting}
              style={{
                padding: "0.5rem 1rem",
                borderRadius: "0.375rem",
                border: "1px solid var(--border-color, #334155)",
                backgroundColor: "transparent",
                color: "var(--text-primary, #f8fafc)",
                fontSize: "0.875rem",
                fontWeight: 500,
                cursor: isSubmitting ? "not-allowed" : "pointer",
              }}
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isSubmitting}
              style={{
                padding: "0.5rem 1rem",
                borderRadius: "0.375rem",
                border: "none",
                backgroundColor: "#22c55e",
                color: "#ffffff",
                fontSize: "0.875rem",
                fontWeight: 500,
                cursor: isSubmitting ? "not-allowed" : "pointer",
                opacity: isSubmitting ? 0.7 : 1,
              }}
            >
              {isSubmitting ? "Approving..." : "Confirm & Grant Access"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
