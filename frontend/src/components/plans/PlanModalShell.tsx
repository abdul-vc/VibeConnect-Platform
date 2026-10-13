/**
 * Shared Plan Modal Shell Primitive.
 *
 * Lightweight, fully accessible dialog shell shared across:
 * - Plan & Version lifecycle dialogs
 * - Plan Pricing dialogs
 * - Plan Packaging dialogs
 *
 * Provides:
 * - Body scroll lock
 * - Focus trapping (Tab / Shift+Tab cycle)
 * - Initial focus targeting
 * - Focus restoration to triggerRef on close
 * - Esc key dismissal (guarded during submission)
 * - Backdrop click dismissal (guarded during submission)
 * - Accessible ARIA labels and descriptions
 * - Standardized footer with submitting protection
 */

import React, { useEffect, useId, useRef } from "react";
import { AlertCircleIcon, CloseIcon } from "../Icons.tsx";

// ---------------------------------------------------------------------------
// Reusable Dialog Accessibility Hook
// ---------------------------------------------------------------------------

export function useDialogAccessibility({
  isOpen,
  isSubmitting,
  onClose,
  triggerRef,
  initialFocusRef,
}: {
  isOpen: boolean;
  isSubmitting: boolean;
  onClose: () => void;
  triggerRef?: React.RefObject<HTMLElement | null>;
  initialFocusRef?: React.RefObject<HTMLElement | null>;
}) {
  const dialogRef = useRef<HTMLDivElement | null>(null);
  const lastActiveElementRef = useRef<HTMLElement | null>(null);

  // Lock body scroll while open
  useEffect(() => {
    if (isOpen) {
      const original = document.body.style.overflow;
      document.body.style.overflow = "hidden";
      return () => {
        document.body.style.overflow = original;
      };
    }
  }, [isOpen]);

  // Track trigger and restore focus on dialog close
  useEffect(() => {
    if (isOpen) {
      lastActiveElementRef.current = (triggerRef?.current || document.activeElement) as HTMLElement | null;
    } else if (lastActiveElementRef.current) {
      const elToFocus = triggerRef?.current || lastActiveElementRef.current;
      lastActiveElementRef.current = null;
      setTimeout(() => {
        elToFocus?.focus?.();
      }, 50);
    }
  }, [isOpen, triggerRef]);

  // Initial focus management
  useEffect(() => {
    if (isOpen) {
      const timer = setTimeout(() => {
        if (initialFocusRef?.current) {
          initialFocusRef.current.focus();
        } else if (dialogRef.current) {
          const focusable = dialogRef.current.querySelectorAll<HTMLElement>(
            'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"]):not([disabled])'
          );
          if (focusable.length > 0) {
            focusable[0].focus();
          } else {
            dialogRef.current.focus();
          }
        }
      }, 50);
      return () => clearTimeout(timer);
    }
  }, [isOpen, initialFocusRef]);

  // Focus trap (Tab / Shift+Tab) and Escape key listener
  useEffect(() => {
    if (!isOpen) return;

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !isSubmitting) {
        e.preventDefault();
        onClose();
        return;
      }

      if (e.key === "Tab" && dialogRef.current) {
        const elements = dialogRef.current.querySelectorAll<HTMLElement>(
          'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"]):not([disabled])'
        );
        const focusable = Array.from(elements).filter(
          (el) =>
            !el.hasAttribute("disabled") &&
            el.getAttribute("aria-hidden") !== "true" &&
            (el.offsetWidth > 0 || el.offsetHeight > 0 || el.getClientRects().length > 0)
        );

        if (focusable.length === 0) {
          e.preventDefault();
          return;
        }

        const first = focusable[0];
        const last = focusable[focusable.length - 1];

        // If focus is outside dialogRef.current, bring it inside immediately
        if (!dialogRef.current.contains(document.activeElement)) {
          e.preventDefault();
          if (e.shiftKey) {
            last.focus();
          } else {
            first.focus();
          }
          return;
        }

        if (e.shiftKey) {
          if (document.activeElement === first || document.activeElement === dialogRef.current) {
            e.preventDefault();
            last.focus();
          }
        } else {
          if (document.activeElement === last) {
            e.preventDefault();
            first.focus();
          }
        }
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, isSubmitting, onClose]);

  return { dialogRef };
}

// ---------------------------------------------------------------------------
// Error Parser Helper
// ---------------------------------------------------------------------------

export function parseApiErrors(err: unknown): { fieldErrors: Record<string, string>; generalError: string | null } {
  const fieldErrors: Record<string, string> = {};
  let generalError: string | null = null;

  const apiErr = err as { status?: number; data?: Record<string, unknown>; message?: string };
  if (apiErr?.data && typeof apiErr.data === "object") {
    Object.entries(apiErr.data).forEach(([key, val]) => {
      if (Array.isArray(val)) {
        fieldErrors[key] = val.join(" ");
      } else if (typeof val === "string") {
        if (key === "detail" || key === "message" || key === "non_field_errors" || key === "__all__") {
          generalError = val;
        } else {
          fieldErrors[key] = val;
        }
      }
    });
  } else if (apiErr?.message) {
    generalError = apiErr.message;
  } else {
    generalError = "An unexpected error occurred. Please try again.";
  }

  return { fieldErrors, generalError };
}

// ---------------------------------------------------------------------------
// Shared Modal Shell Component
// ---------------------------------------------------------------------------

export interface PlanModalShellProps {
  readonly isOpen: boolean;
  readonly onClose: () => void;
  readonly isSubmitting: boolean;
  readonly title: string;
  readonly subtitle?: string;
  readonly triggerRef?: React.RefObject<HTMLElement | null>;
  readonly initialFocusRef?: React.RefObject<HTMLElement | null>;
  readonly maxWidth?: string;
  readonly onSubmit?: (e: React.FormEvent) => void;
  readonly onActionClick?: () => void;
  readonly submitLabel?: string;
  readonly submittingLabel?: string;
  readonly submitVariant?: "primary" | "danger";
  readonly submitDisabled?: boolean;
  readonly customFooter?: React.ReactNode;
  readonly children: React.ReactNode;
}

export const PlanModalShell: React.FC<PlanModalShellProps> = ({
  isOpen,
  onClose,
  isSubmitting,
  title,
  subtitle,
  triggerRef,
  initialFocusRef,
  maxWidth = "520px",
  onSubmit,
  onActionClick,
  submitLabel,
  submittingLabel,
  submitVariant = "primary",
  submitDisabled = false,
  customFooter,
  children,
}) => {
  const baseId = useId();
  const { dialogRef } = useDialogAccessibility({
    isOpen,
    isSubmitting,
    onClose,
    triggerRef,
    initialFocusRef,
  });

  if (!isOpen) return null;

  const footerContent = customFooter !== undefined ? customFooter : submitLabel ? (
    <div className="dialog-footer" style={{ padding: "1rem 1.5rem", marginTop: 0, flexShrink: 0 }}>
      <button
        type="button"
        className="btn btn-secondary"
        onClick={onClose}
        disabled={isSubmitting}
      >
        Cancel
      </button>
      <button
        type={onSubmit ? "submit" : "button"}
        className={`btn ${submitVariant === "danger" ? "btn-danger-action" : "btn-primary"}`}
        onClick={!onSubmit ? onActionClick : undefined}
        disabled={isSubmitting || submitDisabled}
      >
        {isSubmitting ? (submittingLabel || "Saving...") : submitLabel}
      </button>
    </div>
  ) : null;

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
        aria-describedby={subtitle ? `${baseId}-desc` : undefined}
        className="dialog-surface"
        style={{ maxWidth, maxHeight: "min(90dvh, 850px)" }}
      >
        <div className="dialog-header">
          <div>
            <h2 id={`${baseId}-title`} className="dialog-title">
              {title}
            </h2>
            {subtitle && (
              <p id={`${baseId}-desc`} className="dialog-subtitle">
                {subtitle}
              </p>
            )}
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

        {onSubmit ? (
          <form
            onSubmit={onSubmit}
            style={{ display: "flex", flexDirection: "column", flex: 1, minHeight: 0, overflow: "hidden" }}
          >
            <div className="dialog-body">
              {children}
            </div>
            {footerContent}
          </form>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", flex: 1, minHeight: 0, overflow: "hidden" }}>
            <div className="dialog-body">
              {children}
            </div>
            {footerContent}
          </div>
        )}
      </div>
    </div>
  );
};

export const FormErrorBanner: React.FC<{ readonly error: string | null }> = ({ error }) => {
  if (!error) return null;
  return (
    <div className="alert-box alert-danger" role="alert">
      <AlertCircleIcon size={16} style={{ flexShrink: 0 }} />
      <span>{error}</span>
    </div>
  );
};
