/**
 * Deny Access Request Modal (Phase 3F).
 *
 * Implements denial workflow with mandatory trimmed reason (1-500 chars).
 * Consistent with SuspendModal / RevokeModal design and accessibility patterns.
 */

import React, { useId, useRef, useState, useEffect } from "react";
import { accessRequestsApi } from "../../api/accessRequests.ts";
import { ApiError } from "../../api/client.ts";
import type { AccessRequestItem } from "../../api/types.ts";
import { AlertCircleIcon, CloseIcon } from "../Icons.tsx";
import { useDialogAccessibility } from "../plans/PlanModalShell.tsx";

interface DenyRequestModalProps {
  readonly isOpen: boolean;
  readonly requestItem: AccessRequestItem | null;
  readonly onClose: () => void;
  readonly onSuccess: () => void;
  readonly triggerRef?: React.RefObject<HTMLElement | null>;
}

export const DenyRequestModal: React.FC<DenyRequestModalProps> = ({
  isOpen,
  requestItem,
  onClose,
  onSuccess,
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

  if (!isOpen || !requestItem) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = reason.trim();
    if (!trimmed) {
      setFieldError("A reason is mandatory to deny an access request.");
      inputRef.current?.focus();
      return;
    }
    if (trimmed.length > 500) {
      setFieldError("Denial reason cannot exceed 500 characters.");
      inputRef.current?.focus();
      return;
    }

    setIsSubmitting(true);
    setFieldError(null);
    setGeneralError(null);

    try {
      await accessRequestsApi.denyRequest(requestItem.id, { reason: trimmed });
      onSuccess();
      onClose();
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setGeneralError(err.message || "Failed to deny access request.");
      } else {
        setGeneralError("An unexpected error occurred while denying request.");
      }
      setIsSubmitting(false);
    }
  };

  const reasonId = `${baseId}-reason`;
  const errorId = `${baseId}-error`;
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
                backgroundColor: "rgba(239, 68, 68, 0.15)",
                color: "#ef4444",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
              }}
            >
              <AlertCircleIcon size={18} />
            </div>
            <h2
              id={`${baseId}-title`}
              style={{ fontSize: "1.125rem", fontWeight: 600, margin: 0 }}
            >
              Deny Access Request
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
            Denying access for{" "}
            <strong>{requestItem.requester_name || requestItem.requester_email}</strong> to product{" "}
            <strong>{requestItem.product_name || requestItem.product_code || "Requested Product"}</strong>.
            Please explain the reason below.
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
              Denial Reason <span style={{ color: "#ef4444" }}>*</span>
            </label>
            <textarea
              id={reasonId}
              ref={inputRef}
              rows={3}
              value={reason}
              onChange={(e) => {
                setReason(e.target.value);
                if (fieldError) setFieldError(null);
              }}
              disabled={isSubmitting}
              maxLength={500}
              placeholder="Provide a clear explanation for this decision (1–500 characters)..."
              aria-describedby={fieldError ? errorId : undefined}
              aria-invalid={Boolean(fieldError)}
              style={{
                width: "100%",
                padding: "0.625rem 0.75rem",
                backgroundColor: "var(--bg-input, #0f172a)",
                border: `1px solid ${fieldError ? "#ef4444" : "var(--border-color, #334155)"}`,
                borderRadius: "0.375rem",
                color: "var(--text-primary, #f8fafc)",
                fontSize: "0.875rem",
                outline: "none",
                resize: "vertical",
                boxSizing: "border-box",
              }}
            />
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                marginTop: "0.25rem",
              }}
            >
              {fieldError ? (
                <div
                  id={errorId}
                  role="status"
                  aria-live="polite"
                  style={{ color: "#ef4444", fontSize: "0.75rem" }}
                >
                  {fieldError}
                </div>
              ) : (
                <span />
              )}
              <span
                style={{
                  fontSize: "0.75rem",
                  color: reason.length > 450 ? "#f59e0b" : "var(--text-muted, #94a3b8)",
                }}
              >
                {reason.length}/500
              </span>
            </div>
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
                backgroundColor: "#ef4444",
                color: "#ffffff",
                fontSize: "0.875rem",
                fontWeight: 500,
                cursor: isSubmitting ? "not-allowed" : "pointer",
                opacity: isSubmitting ? 0.7 : 1,
              }}
            >
              {isSubmitting ? "Denying..." : "Confirm Denial"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
