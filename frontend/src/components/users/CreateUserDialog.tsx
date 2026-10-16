/**
 * Create Central User Dialog (Phase 2D Stage 5).
 *
 * Platform Owner dialog to provision a new central user identity.
 * Displays explicit notice that unusable credentials are assigned and access activation is deferred.
 */

import React, { useId, useRef, useState } from "react";
import { usersApi } from "../../api/users.ts";
import type { UserDetail } from "../../api/types.ts";
import { ApiError } from "../../api/client.ts";
import { AlertCircleIcon, CloseIcon, UserIcon } from "../Icons.tsx";
import { useDialogAccessibility } from "../plans/PlanModalShell.tsx";

interface CreateUserDialogProps {
  readonly isOpen: boolean;
  readonly onClose: () => void;
  readonly onSuccess: (user: UserDetail) => void;
  readonly triggerRef?: React.RefObject<HTMLElement | null>;
}

export const CreateUserDialog: React.FC<CreateUserDialogProps> = ({
  isOpen,
  onClose,
  onSuccess,
  triggerRef,
}) => {
  const baseId = useId();
  const [email, setEmail] = useState<string>("");
  const [fullName, setFullName] = useState<string>("");
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  const [generalError, setGeneralError] = useState<string | null>(null);
  const [errorCode, setErrorCode] = useState<string | null>(null);

  const emailInputRef = useRef<HTMLInputElement | null>(null);

  const { dialogRef } = useDialogAccessibility({
    isOpen,
    isSubmitting,
    onClose,
    triggerRef,
    initialFocusRef: emailInputRef,
  });

  if (!isOpen) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setGeneralError(null);
    setErrorCode(null);

    const trimmedEmail = email.trim();
    if (!trimmedEmail) {
      setGeneralError("Please enter a valid email address.");
      return;
    }

    setIsSubmitting(true);
    try {
      const user = await usersApi.create({
        email: trimmedEmail,
        full_name: fullName.trim() || undefined,
      });
      setEmail("");
      setFullName("");
      onSuccess(user);
      onClose();
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        const data = err.data as { code?: string; detail?: string } | undefined;
        setErrorCode(data?.code || null);
        setGeneralError(data?.detail || err.message || "Failed to create user.");
      } else {
        setGeneralError("An unexpected error occurred while creating the user.");
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
          maxWidth: "32rem",
          maxHeight: "min(90dvh, 700px)",
        }}
      >
        {/* Header */}
        <div className="dialog-header">
          <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
            <div
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                width: "2.25rem",
                height: "2.25rem",
                borderRadius: "0.5rem",
                backgroundColor: "var(--color-primary-subtle)",
                color: "var(--color-primary)",
              }}
            >
              <UserIcon size={20} />
            </div>
            <div>
              <h2 id={`${baseId}-title`} className="dialog-title">
                Create Central User
              </h2>
              <p id={`${baseId}-desc`} className="dialog-subtitle">
                Provision a new platform user identity
              </p>
            </div>
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

        {/* Form */}
        <form
          onSubmit={handleSubmit}
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

            {/* Phase 2D Notice */}
            <div
              style={{
                padding: "0.75rem 1rem",
                borderRadius: "0.5rem",
                backgroundColor: "var(--brand-primary-light)",
                border: "1px solid var(--border-glass)",
                color: "var(--text-secondary)",
                fontSize: "0.8125rem",
                lineHeight: 1.5,
              }}
            >
              User identity created with unusable credentials. Sign-in credentials and access activation are deferred.
            </div>

            <div style={{ display: "flex", flexDirection: "column", gap: "1rem", marginTop: "0.25rem" }}>
              <div>
                <label
                  htmlFor={`${baseId}-email`}
                  style={{
                    display: "block",
                    fontSize: "0.875rem",
                    fontWeight: 500,
                    marginBottom: "0.375rem",
                    color: "var(--text-primary)",
                  }}
                >
                  Email Address <span style={{ color: "var(--status-danger)" }}>*</span>
                </label>
                <input
                  ref={emailInputRef}
                  id={`${baseId}-email`}
                  type="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="name@company.com"
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

              <div>
                <label
                  htmlFor={`${baseId}-fullName`}
                  style={{
                    display: "block",
                    fontSize: "0.875rem",
                    fontWeight: 500,
                    marginBottom: "0.375rem",
                    color: "var(--text-primary)",
                  }}
                >
                  Full Name
                </label>
                <input
                  id={`${baseId}-fullName`}
                  type="text"
                  value={fullName}
                  onChange={(e) => setFullName(e.target.value)}
                  placeholder="e.g. Jane Doe"
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
            </div>
          </div>

          {/* Footer Actions */}
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
              type="submit"
              className="btn btn-primary"
              disabled={isSubmitting || !email.trim()}
            >
              {isSubmitting ? "Creating..." : "Create User"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

