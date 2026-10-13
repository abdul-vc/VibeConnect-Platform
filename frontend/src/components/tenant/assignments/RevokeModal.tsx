/**
 * Revoke Assignment Modal (Phase 2F Part E).
 *
 * Implements revocation lifecycle action:
 * - Destructive visual treatment
 * - Clear explanation that the assignment will permanently end and the seat reservation released
 * - Requires reason (1-500 chars, whitespace trimmed)
 * - Field-level validation directly below input with aria-describedby and aria-live="polite"
 * - Submits to POST /api/v1/tenant/assignments/<id>/revoke/
 * - Prevents duplicate submission while pending
 * - Handles HTTP 409 stale conflicts by notifying and triggering refetch preserving filters
 * - Accessible dialog with Tab focus trap, Escape dismissal, and focus restoration
 */

import React, { useId, useRef, useState, useEffect } from "react";
import { assignmentsApi } from "../../../api/assignments.ts";
import { ApiError } from "../../../api/client.ts";
import type { UserProductAssignmentItem } from "../../../api/types.ts";
import { AlertCircleIcon, CloseIcon } from "../../Icons.tsx";
import { useDialogAccessibility } from "../../plans/PlanModalShell.tsx";

interface RevokeModalProps {
  readonly isOpen: boolean;
  readonly assignment: UserProductAssignmentItem | null;
  readonly onClose: () => void;
  readonly onSuccess: () => void;
  readonly onConflict: () => void;
  readonly triggerRef?: React.RefObject<HTMLElement | null>;
}

export const RevokeModal: React.FC<RevokeModalProps> = ({
  isOpen,
  assignment,
  onClose,
  onSuccess,
  onConflict,
  triggerRef,
}) => {
  const baseId = useId();
  const inputRef = useRef<HTMLTextAreaElement | null>(null);

  const [reason, setReason] = useState("");
  const [fieldError, setFieldError] = useState<string | null>(null);
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
      setFieldError(null);
      setGeneralError(null);
      setIsSubmitting(false);
    }
  }, [isOpen]);

  if (!isOpen || !assignment) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = reason.trim();
    if (!trimmed) {
      setFieldError("A reason is required to revoke an assignment.");
      inputRef.current?.focus();
      return;
    }
    if (trimmed.length > 500) {
      setFieldError("Revocation reason cannot exceed 500 characters.");
      inputRef.current?.focus();
      return;
    }

    setIsSubmitting(true);
    setFieldError(null);
    setGeneralError(null);

    try {
      await assignmentsApi.revokeAssignment(assignment.id, { reason: trimmed });
      onSuccess();
      onClose();
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        if (err.status === 409) {
          onConflict();
          onClose();
          return;
        }
        const data = err.data as Record<string, unknown> | undefined;
        const errObj = (data?.error && typeof data.error === "object") ? (data.error as Record<string, unknown>) : null;
        const details = (errObj?.details || data?.details) as Record<string, unknown> | undefined;
        if (details?.reason) {
          const rMsg = Array.isArray(details.reason) ? details.reason.join(" ") : String(details.reason);
          setFieldError(rMsg);
        } else {
          setGeneralError(errObj?.message ? String(errObj.message) : err.message);
        }
      } else {
        setGeneralError("An unexpected error occurred while revoking the assignment.");
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  const errorId = `${baseId}-reason-error`;

  return (
    <div
      className="dialog-backdrop"
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
        className="dialog-surface"
        style={{ maxWidth: "520px" }}
      >
        <div className="dialog-header">
          <div>
            <h2 id={`${baseId}-title`} className="dialog-title" style={{ color: "var(--status-danger, #ef4444)" }}>
              Revoke Assignment
            </h2>
            <p id={`${baseId}-desc`} className="dialog-subtitle">
              Permanently end access for {assignment.user.full_name} ({assignment.product.name}).
            </p>
          </div>
          <button
            type="button"
            className="dialog-close-btn"
            onClick={onClose}
            disabled={isSubmitting}
            aria-label="Close dialog"
          >
            <CloseIcon size={18} />
          </button>
        </div>

        <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column" }}>
          <div className="dialog-body" style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
            <div
              className="alert-box alert-danger"
              style={{
                background: "rgba(239, 68, 68, 0.1)",
                border: "1px solid rgba(239, 68, 68, 0.3)",
                color: "var(--status-danger, #ef4444)",
                fontSize: "0.8125rem",
                padding: "0.75rem",
                borderRadius: "8px",
              }}
            >
              This action is permanent. The assignment will end and its allocated product seat will immediately be released back into the available pool.
            </div>

            {generalError && (
              <div className="alert-box alert-danger" role="alert">
                <AlertCircleIcon size={16} style={{ flexShrink: 0 }} />
                <span>{generalError}</span>
              </div>
            )}

            <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
              <label htmlFor={`${baseId}-reason-input`} style={{ fontSize: "0.875rem", fontWeight: 600 }}>
                Revocation Reason <span style={{ color: "var(--status-danger, #ef4444)" }}>*</span>
              </label>
              <textarea
                ref={inputRef}
                id={`${baseId}-reason-input`}
                value={reason}
                onChange={(e) => {
                  setReason(e.target.value);
                  if (fieldError) setFieldError(null);
                }}
                disabled={isSubmitting}
                placeholder="State the reason for revoking this member's access (1-500 characters)..."
                rows={4}
                aria-describedby={fieldError ? errorId : undefined}
                aria-invalid={Boolean(fieldError)}
                style={{
                  width: "100%",
                  padding: "0.75rem",
                  borderRadius: "8px",
                  border: fieldError
                    ? "1px solid var(--status-danger, #ef4444)"
                    : "1px solid var(--border-glass)",
                  background: "var(--bg-input, rgba(0, 0, 0, 0.2))",
                  color: "var(--text-primary)",
                  fontSize: "0.875rem",
                  resize: "vertical",
                  boxSizing: "border-box",
                }}
              />
              <div
                id={errorId}
                aria-live="polite"
                style={{
                  minHeight: "1.25rem",
                  fontSize: "0.75rem",
                  color: "var(--status-danger, #ef4444)",
                  fontWeight: 500,
                }}
              >
                {fieldError || ""}
              </div>
            </div>
          </div>

          <div className="dialog-footer" style={{ padding: "1rem 1.5rem" }}>
            <button
              type="button"
              className="btn btn-secondary"
              onClick={onClose}
              disabled={isSubmitting}
            >
              Cancel
            </button>
            <button
              type="submit"
              className="btn btn-danger-action"
              disabled={isSubmitting}
            >
              {isSubmitting ? "Revoking..." : "Revoke Access"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
