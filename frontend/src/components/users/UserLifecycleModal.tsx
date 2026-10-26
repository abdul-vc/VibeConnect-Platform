/**
 * User Lifecycle Confirmation Modal (Phase 2D Stage 5).
 *
 * Handles consequential lifecycle transitions: Suspend, Reactivate, and Disable.
 * Displays explicit terminal warnings for Disable and surfaces API error codes.
 */

import React, { useId, useRef, useState } from "react";
import { usersApi } from "../../api/users.ts";
import type { UserDetail, UserListItem } from "../../api/types.ts";
import { ApiError } from "../../api/client.ts";
import { AlertCircleIcon, CloseIcon } from "../Icons.tsx";
import { useDialogAccessibility } from "../plans/PlanModalShell.tsx";

export type UserLifecycleAction = "suspend" | "reactivate" | "disable" | "anonymize";

interface UserLifecycleModalProps {
  readonly isOpen: boolean;
  readonly onClose: () => void;
  readonly onSuccess: (user: UserDetail) => void;
  readonly user: UserListItem | UserDetail | null;
  readonly action: UserLifecycleAction | null;
  readonly triggerRef?: React.RefObject<HTMLElement | null>;
}

export const UserLifecycleModal: React.FC<UserLifecycleModalProps> = ({
  isOpen,
  onClose,
  onSuccess,
  user,
  action,
  triggerRef,
}) => {
  const baseId = useId();
  const [reason, setReason] = useState<string>("");
  const [confirmedIrreversible, setConfirmedIrreversible] = useState<boolean>(false);
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  const [generalError, setGeneralError] = useState<string | null>(null);
  const [errorCode, setErrorCode] = useState<string | null>(null);

  const confirmButtonRef = useRef<HTMLButtonElement | null>(null);

  const { dialogRef } = useDialogAccessibility({
    isOpen,
    isSubmitting,
    onClose,
    triggerRef,
    initialFocusRef: confirmButtonRef,
  });

  if (!isOpen || !user || !action) return null;

  const getActionConfig = () => {
    switch (action) {
      case "suspend":
        return {
          title: "Suspend User Account",
          description: `Are you sure you want to suspend "${user.email}"? The user will immediately lose access to the platform and cannot authenticate until reactivated.`,
          buttonText: "Suspend User",
          buttonClass: "btn btn-danger",
          showReason: true,
          requireReason: false,
          requireConfirmation: false,
          isTerminal: false,
        };
      case "reactivate":
        return {
          title: "Reactivate User Account",
          description: `Are you sure you want to reactivate "${user.email}"? This will restore the account to active status, permitting sign-in and console access.`,
          buttonText: "Reactivate User",
          buttonClass: "btn btn-success",
          showReason: false,
          requireReason: false,
          requireConfirmation: false,
          isTerminal: false,
        };
      case "disable":
        return {
          title: "Disable User Account (Terminal)",
          description: `Are you sure you want to permanently disable "${user.email}"?`,
          buttonText: "Disable User Permanently",
          buttonClass: "btn btn-danger",
          showReason: true,
          requireReason: false,
          requireConfirmation: false,
          isTerminal: true,
        };
      case "anonymize":
        return {
          title: "Anonymize Platform User (Phase 6F Privacy)",
          description: `Irreversibly scrubs personal attributes for "${user.email}". Direct identifiers are replaced with pseudonymous values (anonymized-<uuid>@redacted.envisage.local), account is permanently disabled, and credentials revoked. Immutable historical audit logs remain intact as forensic fact.`,
          buttonText: "Anonymize & Deactivate User",
          buttonClass: "btn btn-danger",
          showReason: true,
          requireReason: true,
          requireConfirmation: true,
          isTerminal: true,
        };
    }
  };

  const config = getActionConfig();

  const handleConfirm = async (e: React.FormEvent) => {
    e.preventDefault();
    setGeneralError(null);
    setErrorCode(null);

    if (config.requireReason && reason.trim().length < 3) {
      setGeneralError("A mandatory justification of at least 3 characters is required.");
      return;
    }

    if (config.requireConfirmation && !confirmedIrreversible) {
      setGeneralError("Explicit confirmation of irreversible de-identification is required.");
      return;
    }

    setIsSubmitting(true);

    try {
      let updated: UserDetail;
      if (action === "suspend") {
        updated = await usersApi.suspend(user.id, { reason: reason.trim() || undefined });
      } else if (action === "reactivate") {
        updated = await usersApi.reactivate(user.id);
      } else if (action === "disable") {
        updated = await usersApi.disable(user.id, { reason: reason.trim() || undefined });
      } else {
        const res = await usersApi.anonymize(user.id, {
          reason: reason.trim(),
          confirmation: true,
        });
        updated = res;
      }
      setReason("");
      setConfirmedIrreversible(false);
      onSuccess(updated);
      onClose();
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        const data = err.data as { code?: string; detail?: string } | undefined;
        setErrorCode(data?.code || null);
        setGeneralError(data?.detail || err.message || `Failed to ${action} user.`);
      } else {
        setGeneralError(`An unexpected error occurred while attempting to ${action} user.`);
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div
      className="dialog-backdrop"
      onClick={(e) => {
        if (e.target === e.currentTarget && !isSubmitting) {
          onClose();
        }
      }}
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={`${baseId}-title`}
        className="dialog-surface"
        style={{
          maxWidth: "30rem",
          maxHeight: "min(90dvh, 650px)",
        }}
      >
        {/* Header */}
        <div className="dialog-header">
          <h2
            id={`${baseId}-title`}
            className="dialog-title"
            style={{
              color: config.isTerminal ? "var(--status-danger)" : "var(--text-primary)",
            }}
          >
            {config.title}
          </h2>
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

        <form
          onSubmit={handleConfirm}
          style={{
            display: "flex",
            flexDirection: "column",
            flex: 1,
            minHeight: 0,
            overflow: "hidden",
          }}
        >
          <div className="dialog-body">
            {generalError && (
              <div
                className="alert-banner alert-banner-error"
                role="alert"
                style={{ marginBottom: "0.5rem" }}
              >
                <AlertCircleIcon size={18} />
                <div>
                  {errorCode && (
                    <div style={{ fontWeight: 600, fontSize: "0.75rem", marginBottom: "0.25rem" }}>
                      Error Code: {errorCode}
                    </div>
                  )}
                  <div>{generalError}</div>
                </div>
              </div>
            )}

            {config.isTerminal && (
              <div
                className="alert-banner alert-banner-error"
                role="alert"
                style={{ marginBottom: "0.5rem" }}
              >
                <div>
                  <strong>Caution:</strong>{" "}
                  {action === "anonymize"
                    ? "Anonymization is irreversible and permanently removes direct identifiers. Historical immutable audit records are retained."
                    : "Disabling an account is strictly terminal in Phase 2D. Once disabled, this account cannot be reactivated or modified."}
                </div>
              </div>
            )}

            <p style={{ margin: "0 0 0.5rem 0", fontSize: "0.9375rem", color: "var(--text-secondary)", lineHeight: 1.5 }}>
              {config.description}
            </p>

            {config.showReason && (
              <div style={{ marginTop: "0.5rem" }}>
                <label
                  htmlFor={`${baseId}-reason`}
                  style={{
                    display: "block",
                    fontSize: "0.875rem",
                    fontWeight: 500,
                    marginBottom: "0.375rem",
                    color: "var(--text-primary)",
                  }}
                >
                  {config.requireReason ? "Mandatory Justification / Reason *" : "Reason (Optional)"}
                </label>
                <input
                  id={`${baseId}-reason`}
                  type="text"
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                  placeholder={config.requireReason ? "e.g. GDPR Article 17 Right to Erasure Request" : "Reason for audit log"}
                  disabled={isSubmitting}
                  style={{
                    width: "100%",
                    padding: "0.625rem 0.75rem",
                    borderRadius: "0.375rem",
                    border: "1px solid var(--input-border)",
                    backgroundColor: "var(--input-bg)",
                    color: "var(--text-primary)",
                    fontSize: "0.875rem",
                    boxSizing: "border-box",
                  }}
                />
              </div>
            )}

            {config.requireConfirmation && (
              <div style={{ marginTop: "1rem", display: "flex", alignItems: "flex-start", gap: "0.5rem" }}>
                <input
                  id={`${baseId}-confirm-checkbox`}
                  type="checkbox"
                  checked={confirmedIrreversible}
                  onChange={(e) => setConfirmedIrreversible(e.target.checked)}
                  disabled={isSubmitting}
                  style={{ marginTop: "0.25rem", cursor: "pointer" }}
                />
                <label
                  htmlFor={`${baseId}-confirm-checkbox`}
                  style={{
                    fontSize: "0.8125rem",
                    color: "var(--text-primary)",
                    lineHeight: 1.4,
                    cursor: "pointer",
                  }}
                >
                  I confirm this irreversible de-identification action and understand that live account access will be terminated.
                </label>
              </div>
            )}
          </div>

          {/* Action Buttons */}
          <div className="dialog-footer">
            <button
              type="button"
              className="btn btn-secondary"
              onClick={onClose}
              disabled={isSubmitting}
            >
              Cancel
            </button>
            <button
              ref={confirmButtonRef}
              type="submit"
              className={config.buttonClass}
              disabled={isSubmitting}
            >
              {isSubmitting ? "Processing..." : config.buttonText}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
