/**
 * Accessible Catalog Entity Retirement Confirmation Dialog.
 *
 * Dedicated modal for executing terminal, status-only retirement operations.
 * Submits strictly `{ status: "retired" }` via generic PATCH, warns of
 * bottom-up child constraints, and displays server-side blocking errors prominently.
 */

import React, { useEffect, useId, useRef, useState } from "react";
import { AlertCircleIcon, CloseIcon } from "../Icons.tsx";

interface CatalogRetireDialogProps {
  readonly isOpen: boolean;
  readonly entityTypeLabel: string;
  readonly entityName: string;
  readonly entityCode: string;
  readonly hasChildNotice?: string;
  readonly onClose: () => void;
  readonly onConfirm: () => Promise<void>;
  readonly triggerRef?: React.RefObject<HTMLElement | null>;
}

export const CatalogRetireDialog: React.FC<CatalogRetireDialogProps> = ({
  isOpen,
  entityTypeLabel,
  entityName,
  entityCode,
  hasChildNotice,
  onClose,
  onConfirm,
  triggerRef,
}) => {
  const baseId = useId();
  const titleId = `${baseId}-title`;
  const subtitleId = `${baseId}-subtitle`;
  const errorBannerId = `${baseId}-error-banner`;

  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [statusAnnouncement, setStatusAnnouncement] = useState("");

  const dialogRef = useRef<HTMLDivElement | null>(null);
  const cancelButtonRef = useRef<HTMLButtonElement | null>(null);

  // Lock body scroll and restore exact previous value
  useEffect(() => {
    if (isOpen) {
      const originalOverflow = document.body.style.overflow;
      document.body.style.overflow = "hidden";
      return () => {
        document.body.style.overflow = originalOverflow;
      };
    }
  }, [isOpen]);

  // Reset state and focus cancel button on open (safe default)
  useEffect(() => {
    if (isOpen) {
      setIsSubmitting(false);
      setErrorMessage(null);
      setStatusAnnouncement("");
      const timer = setTimeout(() => {
        cancelButtonRef.current?.focus();
      }, 50);
      return () => clearTimeout(timer);
    }
  }, [isOpen]);

  // Escape key and Tab focus trap
  useEffect(() => {
    if (!isOpen) return;

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !isSubmitting) {
        e.preventDefault();
        handleClose();
        return;
      }

      if (e.key === "Tab" && dialogRef.current) {
        const focusable = dialogRef.current.querySelectorAll<HTMLElement>(
          'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
        );
        if (focusable.length === 0) return;

        const first = focusable[0];
        const last = focusable[focusable.length - 1];

        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, isSubmitting]);

  const handleClose = () => {
    onClose();
    setTimeout(() => {
      triggerRef?.current?.focus();
    }, 50);
  };

  const handleConfirm = async () => {
    if (isSubmitting) return;

    setIsSubmitting(true);
    setErrorMessage(null);
    setStatusAnnouncement(`Retiring ${entityTypeLabel.toLowerCase()}...`);

    try {
      await onConfirm();
      setStatusAnnouncement(`${entityTypeLabel} retired successfully.`);
      handleClose();
    } catch (err: unknown) {
      setIsSubmitting(false);
      const apiErr = err as { status?: number; data?: Record<string, unknown> };

      let msg = "Failed to retire catalog item. Please try again.";
      if (apiErr.data && typeof apiErr.data === "object") {
        if (Array.isArray(apiErr.data.status)) {
          msg = apiErr.data.status.join(" ");
        } else if (typeof apiErr.data.detail === "string") {
          msg = apiErr.data.detail;
        } else if (typeof apiErr.data.message === "string") {
          msg = apiErr.data.message;
        } else {
          msg = JSON.stringify(apiErr.data);
        }
      }
      setErrorMessage(msg);
      setStatusAnnouncement(msg);
    }
  };

  if (!isOpen) return null;

  return (
    <div
      className="dialog-backdrop"
      onClick={(e) => {
        if (e.target === e.currentTarget && !isSubmitting) handleClose();
      }}
    >
      <div className="sr-only" aria-live="polite" aria-atomic="true">
        {statusAnnouncement}
      </div>

      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={errorMessage ? `${errorBannerId} ${subtitleId}` : subtitleId}
        className="dialog-surface"
        style={{ maxWidth: "480px" }}
      >
        <div className="dialog-header">
          <div>
            <h2 id={titleId} className="dialog-title">
              Retire {entityTypeLabel}
            </h2>
            <p id={subtitleId} className="dialog-subtitle">
              Confirm terminal retirement for this catalog entity.
            </p>
          </div>
          <button
            type="button"
            className="dialog-close-btn"
            onClick={handleClose}
            disabled={isSubmitting}
            aria-label={`Close retire ${entityTypeLabel.toLowerCase()} dialog`}
          >
            <CloseIcon size={18} />
          </button>
        </div>

        <div className="dialog-body">
          {errorMessage && (
            <div id={errorBannerId} className="alert-box alert-danger" role="alert">
              <AlertCircleIcon size={16} style={{ flexShrink: 0 }} />
              <span>{errorMessage}</span>
            </div>
          )}

          <div className="retire-target-card">
            <span className="product-code-pill">{entityCode}</span>
            <span className="retire-target-name">{entityName}</span>
          </div>

          <div className="retire-warning-content">
            <p>
              <strong>Terminal State:</strong> Retiring this {entityTypeLabel.toLowerCase()} is{" "}
              <strong>permanent</strong>. Once retired, it cannot be transitioned back to Draft
              or Active.
            </p>
            {hasChildNotice && (
              <p className="retire-bottom-up-note">
                <strong>Bottom-Up Constraint:</strong> {hasChildNotice} If any active or draft child
                items remain, the server will block this retirement.
              </p>
            )}
          </div>

          <div className="dialog-footer">
            <button
              ref={cancelButtonRef}
              type="button"
              className="btn btn-secondary"
              onClick={handleClose}
              disabled={isSubmitting}
            >
              Cancel
            </button>
            <button
              type="button"
              className="btn btn-danger-action"
              onClick={handleConfirm}
              disabled={isSubmitting}
            >
              {isSubmitting ? "Retiring..." : `Retire ${entityTypeLabel}`}
            </button>
          </div>
        </div>
      </div>

      <style>{`
        .retire-target-card {
          background: var(--glass-surface-sunken);
          border: 1px solid var(--border-subtle);
          border-radius: 8px;
          padding: 0.75rem 1rem;
          display: flex;
          align-items: center;
          gap: 0.75rem;
        }

        .retire-target-name {
          font-weight: 600;
          font-size: 0.9375rem;
          color: var(--text-primary);
        }

        .retire-warning-content {
          font-size: 0.84375rem;
          color: var(--text-secondary);
          line-height: 1.5;
          display: flex;
          flex-direction: column;
          gap: 0.5rem;
        }

        .retire-bottom-up-note {
          color: var(--status-warning);
        }

        .btn-danger-action {
          background: var(--status-danger);
          color: #ffffff;
          border: 1px solid transparent;
          border-radius: 8px;
          padding: 0.5rem 1rem;
          min-height: 44px;
          font-size: 0.8125rem;
          font-weight: 600;
          cursor: pointer;
          transition: background-color 0.15s ease, transform 0.15s ease;
          display: inline-flex;
          align-items: center;
          justify-content: center;
        }

        .btn-danger-action:hover:not(:disabled) {
          background: #e11d48;
          transform: translateY(-1px);
        }

        .btn-danger-action:disabled {
          opacity: 0.6;
          cursor: not-allowed;
        }
      `}</style>
    </div>
  );
};
