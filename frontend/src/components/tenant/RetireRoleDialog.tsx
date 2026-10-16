/**
 * Role Retirement Confirmation Dialog (Phase 2E Stage 6).
 *
 * Provides:
 * - Clear warning that retirement is irreversible in Phase 2E
 * - Explanation that roles referenced by any active, suspended, or ended memberships cannot be retired
 * - Destructive action styling (red button) with focus trapping
 * - Accurate display of backend error codes (e.g. ROLE_IN_USE, SYSTEM_ROLE_IMMUTABLE)
 * - Refreshes server state only upon success without optimistic mutations
 */

import React, { useId, useRef, useState } from "react";
import { ApiError } from "../../api/client.ts";
import { rolesApi } from "../../api/roles.ts";
import type { RoleItem } from "../../api/types.ts";
import { AlertCircleIcon, CloseIcon } from "../Icons.tsx";
import { useDialogAccessibility } from "../plans/PlanModalShell.tsx";

interface RetireRoleDialogProps {
  readonly isOpen: boolean;
  readonly role: RoleItem | null;
  readonly onClose: () => void;
  readonly onSuccess: (retiredRole: RoleItem) => void;
  readonly triggerRef?: React.RefObject<HTMLElement | null>;
}

export const RetireRoleDialog: React.FC<RetireRoleDialogProps> = ({
  isOpen,
  role,
  onClose,
  onSuccess,
  triggerRef,
}) => {
  const baseId = useId();
  const confirmBtnRef = useRef<HTMLButtonElement | null>(null);

  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  const [errorDetail, setErrorDetail] = useState<string | null>(null);
  const [errorCode, setErrorCode] = useState<string | null>(null);

  const { dialogRef } = useDialogAccessibility({
    isOpen,
    isSubmitting,
    onClose,
    triggerRef,
    initialFocusRef: confirmBtnRef,
  });

  const handleRetire = async () => {
    if (!role) return;
    setErrorDetail(null);
    setErrorCode(null);
    setIsSubmitting(true);

    try {
      const retired = await rolesApi.retireRole(role.id);
      onSuccess(retired);
      onClose();
    } catch (err) {
      if (err instanceof ApiError) {
        const d = err.data as { code?: string; detail?: string } | undefined;
        setErrorCode(d?.code || `HTTP_${err.status}`);
        setErrorDetail(d?.detail || err.message || "Failed to retire role.");
      } else {
        setErrorDetail("An unexpected network error occurred while retiring role.");
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  if (!isOpen || !role) return null;

  return (
    <div
      className="modal-backdrop"
      role="presentation"
      style={{
        position: "fixed",
        inset: 0,
        backgroundColor: "rgba(0, 0, 0, 0.65)",
        backdropFilter: "blur(6px)",
        WebkitBackdropFilter: "blur(6px)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: "1rem",
        zIndex: 1000,
        overflowY: "auto",
      }}
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={`${baseId}-title`}
        aria-describedby={`${baseId}-desc`}
        className="glass-panel"
        style={{
          width: "100%",
          maxWidth: "480px",
          display: "flex",
          flexDirection: "column",
          borderRadius: "14px",
          background: "var(--glass-surface-elevated)",
          border: "1px solid var(--border-glass)",
          boxShadow: "var(--shadow-lg)",
          overflow: "hidden",
        }}
      >
        {/* Header */}
        <div
          style={{
            padding: "1.25rem 1.5rem",
            borderBottom: "1px solid var(--border-subtle)",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
            <div
              style={{
                width: "28px",
                height: "28px",
                borderRadius: "50%",
                background: "var(--status-danger-bg)",
                border: "1px solid var(--status-danger-border)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                color: "var(--status-danger)",
              }}
            >
              <AlertCircleIcon size={16} />
            </div>
            <h2
              id={`${baseId}-title`}
              style={{
                margin: 0,
                fontSize: "1.125rem",
                fontWeight: 700,
                color: "var(--text-primary)",
              }}
            >
              Retire Role
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
              color: "var(--text-secondary)",
              cursor: isSubmitting ? "not-allowed" : "pointer",
              padding: "0.25rem",
              borderRadius: "6px",
              display: "flex",
            }}
          >
            <CloseIcon size={18} />
          </button>
        </div>

        {/* Content */}
        <div
          style={{
            padding: "1.25rem 1.5rem",
            display: "flex",
            flexDirection: "column",
            gap: "1rem",
          }}
        >
          <p
            id={`${baseId}-desc`}
            style={{
              margin: 0,
              fontSize: "0.875rem",
              color: "var(--text-secondary)",
              lineHeight: 1.5,
            }}
          >
            Are you sure you want to retire role{" "}
            <strong style={{ color: "var(--text-primary)" }}>{role.name}</strong> (
            <code style={{ fontFamily: "var(--font-code)", fontSize: "0.8125rem" }}>
              {role.code}
            </code>
            )?
          </p>

          <div
            style={{
              padding: "0.75rem 1rem",
              borderRadius: "8px",
              background: "var(--status-warning-bg)",
              border: "1px solid var(--status-warning-border)",
              color: "var(--status-warning)",
              fontSize: "0.8125rem",
              lineHeight: 1.5,
            }}
          >
            <p style={{ margin: "0 0 0.4rem 0" }}>
              <strong>Important:</strong> Role retirement is permanent and irreversible in Phase 2E.
            </p>
            <p style={{ margin: 0 }}>
              This role cannot be retired while it is assigned to any active, suspended, or ended Tenant Admin membership. Reassign every referenced membership first.
            </p>
          </div>

          {/* Error Banner */}
          {errorDetail && (
            <div
              role="alert"
              style={{
                padding: "0.75rem 1rem",
                borderRadius: "8px",
                background: "var(--status-danger-bg)",
                border: "1px solid var(--status-danger-border)",
                color: "var(--status-danger)",
                display: "flex",
                alignItems: "flex-start",
                gap: "0.5rem",
                fontSize: "0.875rem",
              }}
            >
              <AlertCircleIcon size={18} style={{ flexShrink: 0, marginTop: "2px" }} />
              <div>
                {errorCode && (
                  <strong style={{ display: "block", marginBottom: "0.15rem" }}>
                    [{errorCode}]
                  </strong>
                )}
                <span>{errorDetail}</span>
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div
          style={{
            padding: "1rem 1.5rem",
            borderTop: "1px solid var(--border-subtle)",
            background: "rgba(0, 0, 0, 0.15)",
            display: "flex",
            justifyContent: "flex-end",
            alignItems: "center",
            gap: "0.75rem",
          }}
        >
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
            type="button"
            className="btn btn-danger"
            onClick={handleRetire}
            disabled={isSubmitting}
          >
            {isSubmitting ? "Retiring..." : "Retire Role"}
          </button>
        </div>
      </div>
    </div>
  );
};
