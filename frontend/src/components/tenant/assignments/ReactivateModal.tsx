/**
 * Reactivate Assignment Modal (Phase 2F Part E).
 *
 * Implements reactivation lifecycle action:
 * - Clear confirmation message
 * - No reason input field
 * - Submits to POST /api/v1/tenant/assignments/<id>/reactivate/
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

interface ReactivateModalProps {
  readonly isOpen: boolean;
  readonly assignment: UserProductAssignmentItem | null;
  readonly onClose: () => void;
  readonly onSuccess: () => void;
  readonly onConflict: () => void;
  readonly triggerRef?: React.RefObject<HTMLElement | null>;
}

export const ReactivateModal: React.FC<ReactivateModalProps> = ({
  isOpen,
  assignment,
  onClose,
  onSuccess,
  onConflict,
  triggerRef,
}) => {
  const baseId = useId();
  const confirmBtnRef = useRef<HTMLButtonElement | null>(null);

  const [generalError, setGeneralError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const { dialogRef } = useDialogAccessibility({
    isOpen,
    isSubmitting,
    onClose,
    triggerRef,
    initialFocusRef: confirmBtnRef,
  });

  useEffect(() => {
    if (isOpen) {
      setGeneralError(null);
      setIsSubmitting(false);
    }
  }, [isOpen]);

  if (!isOpen || !assignment) return null;

  const handleConfirm = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSubmitting(true);
    setGeneralError(null);

    try {
      await assignmentsApi.reactivateAssignment(assignment.id);
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
        setGeneralError(errObj?.message ? String(errObj.message) : err.message);
      } else {
        setGeneralError("An unexpected error occurred while reactivating the assignment.");
      }
    } finally {
      setIsSubmitting(false);
    }
  };

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
        style={{ maxWidth: "480px" }}
      >
        <div className="dialog-header">
          <div>
            <h2 id={`${baseId}-title`} className="dialog-title">
              Reactivate Assignment
            </h2>
            <p id={`${baseId}-desc`} className="dialog-subtitle">
              Restore product access for {assignment.user.full_name}.
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

        <form onSubmit={handleConfirm} style={{ display: "flex", flexDirection: "column" }}>
          <div className="dialog-body" style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
            {generalError && (
              <div className="alert-box alert-danger" role="alert">
                <AlertCircleIcon size={16} style={{ flexShrink: 0 }} />
                <span>{generalError}</span>
              </div>
            )}

            <p style={{ margin: 0, fontSize: "0.875rem", color: "var(--text-secondary)", lineHeight: 1.5 }}>
              Are you sure you want to reactivate access to <strong>{assignment.product.name}</strong> for{" "}
              <strong>{assignment.user.full_name}</strong> ({assignment.user.email})? Their previous module
              configuration will be restored.
            </p>
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
              ref={confirmBtnRef}
              type="submit"
              className="btn btn-primary"
              disabled={isSubmitting}
            >
              {isSubmitting ? "Reactivating..." : "Reactivate Access"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
