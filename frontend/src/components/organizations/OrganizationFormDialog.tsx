/**
 * Organization Form Dialog Component.
 *
 * Accessible modal dialog for registering and editing organizations with client-side validation,
 * irreversible lifecycle warnings, focus trapping, and double-submit prevention.
 */

import React, { useEffect, useRef, useState } from "react";
import { organizationsApi } from "../../api/organizations.ts";
import type {
  CreateOrganizationPayload,
  OrganizationDetail,
  OrganizationListItem,
  OrganizationStatus,
  UpdateOrganizationPayload,
} from "../../api/types.ts";
import { AlertCircleIcon, CloseIcon } from "../Icons.tsx";

interface OrganizationFormDialogProps {
  readonly isOpen: boolean;
  readonly mode: "create" | "edit";
  readonly organization: OrganizationListItem | null;
  readonly onClose: () => void;
  readonly onSuccess: (organization: OrganizationDetail) => void;
  readonly triggerRef?: React.RefObject<HTMLElement | null>;
}

const CODE_REGEX = /^[a-z0-9]+(?:[-_][a-z0-9]+)*$/;

export const OrganizationFormDialog: React.FC<OrganizationFormDialogProps> = ({
  isOpen,
  mode,
  organization,
  onClose,
  onSuccess,
  triggerRef,
}) => {
  const [code, setCode] = useState<string>("");
  const [name, setName] = useState<string>("");
  const [description, setDescription] = useState<string>("");
  const [status, setStatus] = useState<OrganizationStatus>("draft");

  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [generalError, setGeneralError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);

  const dialogRef = useRef<HTMLDivElement | null>(null);
  const firstInputRef = useRef<HTMLInputElement | null>(null);

  // Initialize or reset form state when dialog opens or target changes
  useEffect(() => {
    if (isOpen) {
      if (mode === "edit" && organization) {
        setCode(organization.code);
        setName(organization.name);
        setDescription(organization.description || "");
        setStatus(organization.status);
      } else {
        setCode("");
        setName("");
        setDescription("");
        setStatus("draft");
      }
      setFieldErrors({});
      setGeneralError(null);
      setIsSubmitting(false);

      // Autofocus on first editable field
      setTimeout(() => {
        if (firstInputRef.current) {
          firstInputRef.current.focus();
        }
      }, 50);
    }
  }, [isOpen, mode, organization]);

  // Focus trap & Escape key listener
  useEffect(() => {
    if (!isOpen) return;

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        if (!isSubmitting) {
          handleClose();
        }
      } else if (e.key === "Tab") {
        if (!dialogRef.current) return;
        const focusableElements = dialogRef.current.querySelectorAll<HTMLElement>(
          'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
        );
        if (focusableElements.length === 0) return;

        const firstElement = focusableElements[0];
        const lastElement = focusableElements[focusableElements.length - 1];

        if (e.shiftKey && document.activeElement === firstElement) {
          e.preventDefault();
          lastElement.focus();
        } else if (!e.shiftKey && document.activeElement === lastElement) {
          e.preventDefault();
          firstElement.focus();
        }
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, isSubmitting]);

  const handleClose = () => {
    if (isSubmitting) return;
    onClose();
    if (triggerRef?.current) {
      triggerRef.current.focus();
    }
  };

  const validateForm = (): boolean => {
    const errors: Record<string, string> = {};

    if (mode === "create") {
      const normalizedCode = code.trim().toLowerCase();
      if (!normalizedCode) {
        errors.code = "Organization code is required.";
      } else if (normalizedCode.length > 50) {
        errors.code = "Organization code must be 50 characters or fewer.";
      } else if (!CODE_REGEX.test(normalizedCode)) {
        errors.code =
          "Organization code must contain only lowercase alphanumeric characters, with optional single hyphens or underscores between characters.";
      }
    }

    const trimmedName = name.trim();
    if (!trimmedName) {
      errors.name = "Organization name is required.";
    } else if (trimmedName.length > 150) {
      errors.name = "Organization name must be 150 characters or fewer.";
    }

    const trimmedDesc = description.trim();
    if (trimmedDesc.length > 1000) {
      errors.description = "Description must be 1000 characters or fewer.";
    }

    setFieldErrors(errors);
    return Object.keys(errors).length === 0;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!validateForm()) return;

    setIsSubmitting(true);
    setGeneralError(null);
    setFieldErrors({});

    try {
      if (mode === "create") {
        const payload: CreateOrganizationPayload = {
          code: code.trim().toLowerCase(),
          name: name.trim(),
          description: description.trim() || undefined,
        };
        const result = await organizationsApi.create(payload);
        setIsSubmitting(false);
        onSuccess(result);
        handleClose();
      } else if (mode === "edit" && organization) {
        const payload: UpdateOrganizationPayload = {
          name: name.trim(),
          description: description.trim(),
          status,
        };
        const result = await organizationsApi.update(organization.id, payload);
        setIsSubmitting(false);
        onSuccess(result);
        handleClose();
      }
    } catch (err: any) {
      setIsSubmitting(false);
      if (err?.data && typeof err.data === "object") {
        const errors: Record<string, string> = {};
        for (const [key, value] of Object.entries(err.data)) {
          if (Array.isArray(value)) {
            errors[key] = value.join(" ");
          } else if (typeof value === "string") {
            errors[key] = value;
          }
        }
        if (errors.detail && Object.keys(errors).length === 1) {
          setGeneralError(errors.detail);
        } else {
          setFieldErrors(errors);
        }
      } else {
        setGeneralError(err?.message || "An unexpected error occurred. Please try again.");
      }
    }
  };

  if (!isOpen) return null;

  // Allowed lifecycle options for edit mode based on current status
  const getAllowedStatuses = (): OrganizationStatus[] => {
    if (!organization) return ["draft"];
    switch (organization.status) {
      case "draft":
        return ["draft", "active", "retired"];
      case "active":
        return ["active", "suspended", "retired"];
      case "suspended":
        return ["suspended", "active", "retired"];
      case "retired":
        return ["retired"];
      default:
        return ["draft"];
    }
  };

  return (
    <div
      className="dialog-backdrop"
      onClick={(e) => {
        if (e.target === e.currentTarget && !isSubmitting) {
          handleClose();
        }
      }}
      role="presentation"
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="dialog-title"
        aria-describedby="dialog-description"
        className="dialog-panel"
      >
        {/* Dialog Header */}
        <div className="dialog-header">
          <div>
            <h2 id="dialog-title" className="dialog-title">
              {mode === "create" ? "Register Organization" : "Edit Organization"}
            </h2>
            <p id="dialog-description" className="dialog-desc">
              {mode === "create"
                ? "Add a new customer organization to the Envisage control plane."
                : `Update identity and lifecycle parameters for ${organization?.name}.`}
            </p>
          </div>
          <button
            type="button"
            className="dialog-close-btn"
            onClick={handleClose}
            disabled={isSubmitting}
            aria-label="Close dialog"
          >
            <CloseIcon size={18} />
          </button>
        </div>

        {/* General Error Banner */}
        {generalError && (
          <div className="dialog-alert-error" role="alert">
            <AlertCircleIcon size={16} />
            <span>{generalError}</span>
          </div>
        )}

        {/* Dialog Form */}
        <form onSubmit={handleSubmit} noValidate className="dialog-form">
          {/* Organization Code Field */}
          <div className="form-group">
            <label htmlFor="org-code-input" className="form-label">
              Organization Code <span className="required-asterisk">*</span>
            </label>
            {mode === "create" ? (
              <>
                <input
                  ref={firstInputRef}
                  id="org-code-input"
                  type="text"
                  className={`form-input code-input ${fieldErrors.code ? "input-error" : ""}`}
                  placeholder="e.g. acme-corp"
                  value={code}
                  onChange={(e) => setCode(e.target.value)}
                  disabled={isSubmitting}
                  maxLength={50}
                  aria-invalid={!!fieldErrors.code}
                  aria-describedby={fieldErrors.code ? "org-code-error" : "org-code-help"}
                />
                <span id="org-code-help" className="form-help-text">
                  Stable machine-readable identifier. Lowercase letters, numbers, single hyphens or underscores.
                </span>
              </>
            ) : (
              <>
                <input
                  id="org-code-input"
                  type="text"
                  className="form-input code-input disabled-input"
                  value={code}
                  disabled={true}
                  readOnly={true}
                  aria-describedby="org-code-readonly-help"
                />
                <span id="org-code-readonly-help" className="form-help-text">
                  Organization code is immutable after creation.
                </span>
              </>
            )}
            {fieldErrors.code && (
              <span id="org-code-error" className="field-error-message" role="alert">
                {fieldErrors.code}
              </span>
            )}
          </div>

          {/* Organization Name Field */}
          <div className="form-group">
            <label htmlFor="org-name-input" className="form-label">
              Organization Name <span className="required-asterisk">*</span>
            </label>
            <input
              ref={mode === "edit" ? firstInputRef : undefined}
              id="org-name-input"
              type="text"
              className={`form-input ${fieldErrors.name ? "input-error" : ""}`}
              placeholder="e.g. Acme Corporation"
              value={name}
              onChange={(e) => setName(e.target.value)}
              disabled={isSubmitting}
              maxLength={150}
              aria-invalid={!!fieldErrors.name}
              aria-describedby={fieldErrors.name ? "org-name-error" : undefined}
            />
            {fieldErrors.name && (
              <span id="org-name-error" className="field-error-message" role="alert">
                {fieldErrors.name}
              </span>
            )}
          </div>

          {/* Description Field */}
          <div className="form-group">
            <label htmlFor="org-desc-input" className="form-label">
              Description <span className="optional-tag">(Optional)</span>
            </label>
            <textarea
              id="org-desc-input"
              className={`form-textarea ${fieldErrors.description ? "input-error" : ""}`}
              placeholder="High-level summary of the organization account..."
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              disabled={isSubmitting}
              maxLength={1000}
              rows={3}
              aria-invalid={!!fieldErrors.description}
              aria-describedby={fieldErrors.description ? "org-desc-error" : undefined}
            />
            {fieldErrors.description && (
              <span id="org-desc-error" className="field-error-message" role="alert">
                {fieldErrors.description}
              </span>
            )}
          </div>

          {/* Lifecycle Status Field (Edit Mode Only) */}
          {mode === "edit" && organization && (
            <div className="form-group">
              <label htmlFor="org-status-select" className="form-label">
                Lifecycle Status
              </label>
              <select
                id="org-status-select"
                className="form-select"
                value={status}
                onChange={(e) => setStatus(e.target.value as OrganizationStatus)}
                disabled={isSubmitting || organization.status === "retired"}
                aria-describedby={status === "retired" ? "org-retired-warning" : undefined}
              >
                {getAllowedStatuses().map((st) => (
                  <option key={st} value={st}>
                    {st.charAt(0).toUpperCase() + st.slice(1)}
                  </option>
                ))}
              </select>

              {/* Irreversible Action Warning for Retirement */}
              {status === "retired" && organization.status !== "retired" && (
                <div id="org-retired-warning" className="dialog-alert-warning" role="alert">
                  <AlertCircleIcon size={16} />
                  <span>
                    <strong>Warning:</strong> Retiring an organization is a permanent and irreversible action. Once retired, the organization cannot be reactivated or edited.
                  </span>
                </div>
              )}
            </div>
          )}

          {/* Dialog Actions */}
          <div className="dialog-footer">
            <button
              type="button"
              className="btn btn-secondary"
              onClick={handleClose}
              disabled={isSubmitting}
            >
              Cancel
            </button>
            <button
              type="submit"
              className="btn btn-primary"
              disabled={isSubmitting}
            >
              {isSubmitting
                ? mode === "create"
                  ? "Registering..."
                  : "Saving..."
                : mode === "create"
                ? "Register Organization"
                : "Save Changes"}
            </button>
          </div>
        </form>
      </div>

      <style>{`
        .dialog-backdrop {
          position: fixed;
          inset: 0;
          z-index: 50;
          background: rgba(0, 0, 0, 0.65);
          backdrop-filter: blur(4px);
          -webkit-backdrop-filter: blur(4px);
          display: flex;
          align-items: center;
          justify-content: center;
          padding: 1rem;
          overflow-y: auto;
        }

        .dialog-panel {
          position: relative;
          width: 100%;
          max-width: 520px;
          background: var(--glass-surface-elevated);
          border: 1px solid var(--border-glass);
          border-radius: 16px;
          box-shadow: var(--shadow-lg);
          padding: 1.5rem;
          display: flex;
          flex-direction: column;
          gap: 1.25rem;
          box-sizing: border-box;
          max-height: 90vh;
          overflow-y: auto;
        }

        .dialog-header {
          display: flex;
          align-items: flex-start;
          justify-content: space-between;
          gap: 1rem;
        }

        .dialog-title {
          font-size: 1.25rem;
          font-weight: 700;
          color: var(--text-primary);
          margin: 0;
        }

        .dialog-desc {
          font-size: 0.8125rem;
          color: var(--text-secondary);
          margin: 0.25rem 0 0 0;
          line-height: 1.4;
        }

        .dialog-close-btn {
          background: transparent;
          border: none;
          color: var(--text-muted);
          cursor: pointer;
          padding: 0.25rem;
          border-radius: 6px;
          display: flex;
          align-items: center;
          justify-content: center;
          transition: color 0.15s ease, background-color 0.15s ease;
        }

        .dialog-close-btn:hover:not(:disabled) {
          color: var(--text-primary);
          background: var(--glass-surface-hover);
        }

        .dialog-alert-error {
          display: flex;
          align-items: center;
          gap: 0.5rem;
          padding: 0.75rem 1rem;
          border-radius: 8px;
          background: var(--status-error-bg);
          border: 1px solid var(--status-error-border);
          color: var(--status-error);
          font-size: 0.8125rem;
        }

        .dialog-alert-warning {
          display: flex;
          align-items: flex-start;
          gap: 0.5rem;
          padding: 0.75rem 1rem;
          border-radius: 8px;
          background: var(--status-warning-bg);
          border: 1px solid var(--status-warning-border);
          color: var(--status-warning);
          font-size: 0.8125rem;
          line-height: 1.4;
          margin-top: 0.5rem;
        }

        .dialog-form {
          display: flex;
          flex-direction: column;
          gap: 1.125rem;
        }

        .form-group {
          display: flex;
          flex-direction: column;
          gap: 0.35rem;
        }

        .form-label {
          font-size: 0.8125rem;
          font-weight: 600;
          color: var(--text-primary);
        }

        .required-asterisk {
          color: var(--status-error);
        }

        .optional-tag {
          font-size: 0.75rem;
          font-weight: 400;
          color: var(--text-muted);
        }

        .form-input,
        .form-select,
        .form-textarea {
          width: 100%;
          min-height: 42px;
          padding: 0.5rem 0.875rem;
          font-size: 0.875rem;
          font-family: inherit;
          border-radius: 8px;
          border: 1px solid var(--input-border);
          background: var(--input-bg);
          color: var(--text-primary);
          outline: none;
          box-sizing: border-box;
          transition: border-color 0.15s ease, box-shadow 0.15s ease;
        }

        .code-input {
          font-family: var(--font-code);
          font-size: 0.8125rem;
        }

        .disabled-input {
          opacity: 0.65;
          cursor: not-allowed;
          background: var(--glass-surface-sunken);
        }

        .form-input:focus,
        .form-select:focus,
        .form-textarea:focus {
          border-color: var(--input-border-focus);
          box-shadow: 0 0 0 3px var(--brand-primary-light);
        }

        .input-error {
          border-color: var(--status-error) !important;
        }

        .input-error:focus {
          box-shadow: 0 0 0 3px var(--status-error-bg) !important;
        }

        .form-help-text {
          font-size: 0.75rem;
          color: var(--text-muted);
          line-height: 1.3;
        }

        .field-error-message {
          font-size: 0.75rem;
          color: var(--status-error);
          font-weight: 500;
        }

        .dialog-footer {
          display: flex;
          align-items: center;
          justify-content: flex-end;
          gap: 0.75rem;
          padding-top: 0.75rem;
          border-top: 1px solid var(--border-subtle);
          margin-top: 0.5rem;
        }
      `}</style>
    </div>
  );
};
