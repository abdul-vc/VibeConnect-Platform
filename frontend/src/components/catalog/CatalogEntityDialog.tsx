/**
 * Accessible Catalog Entity Form Dialog Component.
 *
 * Unified create/edit dialog for ProductModule, ProductFeature, and ProductCapability.
 * Implements strict runtime payload allowlisting, code-freeze validation,
 * WCAG-compliant focus trapping, Escape dismissal, and body-scroll lock restoration.
 */

import React, { useEffect, useId, useRef, useState } from "react";
import { catalogApi } from "../../api/catalog.ts";
import type {
  CatalogMetadataPatchPayload,
  CatalogStatus,
  CreateProductCapabilityPayload,
  CreateProductFeaturePayload,
  CreateProductModulePayload,
} from "../../api/types.ts";
import { AlertCircleIcon, CloseIcon } from "../Icons.tsx";

export type CatalogEntityType = "module" | "feature" | "capability";

export interface CatalogEntityFormData {
  readonly id: string;
  readonly code: string;
  readonly name: string;
  readonly description: string;
  readonly display_order: number;
  readonly status: CatalogStatus;
}

interface CatalogEntityDialogProps {
  readonly entityType: CatalogEntityType;
  readonly mode: "create" | "edit";
  readonly isOpen: boolean;
  readonly onClose: () => void;
  readonly onSuccess: () => void;
  readonly parentId: string;
  readonly parentLabel: string;
  readonly initialData?: CatalogEntityFormData | null;
  readonly triggerRef?: React.RefObject<HTMLElement | null>;
}

const CODE_REGEX = /^[a-z0-9]+(?:[-_][a-z0-9]+)*$/;

export const CatalogEntityDialog: React.FC<CatalogEntityDialogProps> = ({
  entityType,
  mode,
  isOpen,
  onClose,
  onSuccess,
  parentId,
  parentLabel,
  initialData,
  triggerRef,
}) => {
  const baseId = useId();
  const titleId = `${baseId}-title`;
  const subtitleId = `${baseId}-subtitle`;
  const bannerErrorId = `${baseId}-banner-error`;
  const codeInputId = `${baseId}-code`;
  const codeHintId = `${baseId}-code-hint`;
  const codeErrorId = `${baseId}-code-error`;
  const nameInputId = `${baseId}-name`;
  const nameErrorId = `${baseId}-name-error`;
  const descInputId = `${baseId}-desc`;
  const descErrorId = `${baseId}-desc-error`;
  const orderInputId = `${baseId}-order`;
  const orderHintId = `${baseId}-order-hint`;
  const orderErrorId = `${baseId}-order-error`;

  const [code, setCode] = useState("");
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [displayOrder, setDisplayOrder] = useState(0);

  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [nonFieldError, setNonFieldError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [statusAnnouncement, setStatusAnnouncement] = useState("");

  const dialogRef = useRef<HTMLDivElement | null>(null);
  const codeInputRef = useRef<HTMLInputElement | null>(null);
  const nameInputRef = useRef<HTMLInputElement | null>(null);

  const entityTitle =
    entityType === "module"
      ? "Module"
      : entityType === "feature"
      ? "Feature"
      : "Capability";

  // Lock body scroll with exact previous overflow restoration
  useEffect(() => {
    if (isOpen) {
      const originalOverflow = document.body.style.overflow;
      document.body.style.overflow = "hidden";
      return () => {
        document.body.style.overflow = originalOverflow;
      };
    }
  }, [isOpen]);

  // Initialize or reset form state
  useEffect(() => {
    if (isOpen) {
      if (mode === "edit" && initialData) {
        setCode(initialData.code);
        setName(initialData.name);
        setDescription(initialData.description || "");
        setDisplayOrder(initialData.display_order ?? 0);
      } else {
        setCode("");
        setName("");
        setDescription("");
        setDisplayOrder(0);
      }
      setFieldErrors({});
      setNonFieldError(null);
      setIsSubmitting(false);
      setStatusAnnouncement("");

      // Focus first active editable input
      const timer = setTimeout(() => {
        if (mode === "create" || (mode === "edit" && initialData?.status === "draft")) {
          codeInputRef.current?.focus();
        } else {
          nameInputRef.current?.focus();
        }
      }, 50);
      return () => clearTimeout(timer);
    }
  }, [isOpen, mode, initialData]);

  // Handle Escape key and Tab focus trap
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

  const isCodeEditable = mode === "create" || (mode === "edit" && initialData?.status === "draft");

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (isSubmitting) return;

    // Client-side validation
    const errors: Record<string, string> = {};
    const trimmedCode = code.trim().toLowerCase();
    const trimmedName = name.trim();

    if (isCodeEditable) {
      if (!trimmedCode) {
        errors.code = `${entityTitle} code is required.`;
      } else if (trimmedCode.length > 50) {
        errors.code = `${entityTitle} code must be 50 characters or fewer.`;
      } else if (!CODE_REGEX.test(trimmedCode)) {
        errors.code = `${entityTitle} code must contain only lowercase alphanumeric characters, with optional single hyphens or underscores between characters.`;
      }
    }

    if (!trimmedName) {
      errors.name = `${entityTitle} name is required.`;
    } else if (trimmedName.length > 100) {
      errors.name = `${entityTitle} name must be 100 characters or fewer.`;
    }

    if (description.trim().length > 1000) {
      errors.description = `${entityTitle} description must be 1000 characters or fewer.`;
    }

    if (displayOrder < 0 || isNaN(displayOrder)) {
      errors.display_order = "Display order must be a non-negative integer.";
    }

    if (Object.keys(errors).length > 0) {
      setFieldErrors(errors);
      setNonFieldError(null);
      setStatusAnnouncement("Please correct the highlighted form errors.");
      if (errors.code && isCodeEditable) {
        codeInputRef.current?.focus();
      } else if (errors.name) {
        nameInputRef.current?.focus();
      }
      return;
    }

    setFieldErrors({});
    setNonFieldError(null);
    setIsSubmitting(true);
    setStatusAnnouncement(`Submitting ${entityTitle.toLowerCase()} details...`);

    try {
      if (mode === "create") {
        if (entityType === "module") {
          const payload: CreateProductModulePayload = {
            product_id: parentId,
            code: trimmedCode,
            name: trimmedName,
            description: description.trim(),
            display_order: Math.floor(displayOrder),
          };
          await catalogApi.modules.create(payload);
        } else if (entityType === "feature") {
          const payload: CreateProductFeaturePayload = {
            module_id: parentId,
            code: trimmedCode,
            name: trimmedName,
            description: description.trim(),
            display_order: Math.floor(displayOrder),
          };
          await catalogApi.features.create(payload);
        } else {
          const payload: CreateProductCapabilityPayload = {
            feature_id: parentId,
            code: trimmedCode,
            name: trimmedName,
            description: description.trim(),
            display_order: Math.floor(displayOrder),
          };
          await catalogApi.capabilities.create(payload);
        }
        setStatusAnnouncement(`${entityTitle} registered successfully.`);
        onSuccess();
        handleClose();
      } else if (mode === "edit" && initialData) {
        // Diff changes for metadata PATCH
        const diff: CatalogMetadataPatchPayload = {};

        if (isCodeEditable && trimmedCode !== initialData.code) {
          (diff as any).code = trimmedCode;
        }
        if (trimmedName !== initialData.name) {
          (diff as any).name = trimmedName;
        }
        if (description.trim() !== (initialData.description || "")) {
          (diff as any).description = description.trim();
        }
        if (Math.floor(displayOrder) !== initialData.display_order) {
          (diff as any).display_order = Math.floor(displayOrder);
        }

        if (Object.keys(diff).length === 0) {
          // Zero changes, close cleanly without request
          handleClose();
          return;
        }

        if (entityType === "module") {
          await catalogApi.modules.patch(initialData.id, diff);
        } else if (entityType === "feature") {
          await catalogApi.features.patch(initialData.id, diff);
        } else {
          await catalogApi.capabilities.patch(initialData.id, diff);
        }

        setStatusAnnouncement(`${entityTitle} updated successfully.`);
        onSuccess();
        handleClose();
      }
    } catch (err: unknown) {
      setIsSubmitting(false);
      const apiErr = err as { status?: number; data?: Record<string, unknown> };

      if (apiErr.data && typeof apiErr.data === "object") {
        const newFieldErrors: Record<string, string> = {};
        let generalError: string | null = null;

        Object.entries(apiErr.data).forEach(([key, val]) => {
          if (Array.isArray(val)) {
            newFieldErrors[key] = val.join(" ");
          } else if (typeof val === "string") {
            if (key === "detail" || key === "message" || key === "non_field_errors") {
              generalError = val;
            } else {
              newFieldErrors[key] = val;
            }
          } else if (typeof val === "object" && val !== null) {
            generalError = JSON.stringify(val);
          }
        });

        setFieldErrors(newFieldErrors);
        setNonFieldError(generalError);
        setStatusAnnouncement(generalError || "Please correct the highlighted form errors.");

        if (newFieldErrors.code && isCodeEditable) {
          codeInputRef.current?.focus();
        } else if (newFieldErrors.name) {
          nameInputRef.current?.focus();
        }
      } else {
        const msg = "A network error occurred. Please verify your connection and try again.";
        setNonFieldError(msg);
        setStatusAnnouncement(msg);
      }
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
        aria-describedby={subtitleId}
        className="dialog-surface"
      >
        <div className="dialog-header">
          <div>
            <h2 id={titleId} className="dialog-title">
              {mode === "create" ? `Register ${entityTitle}` : `Edit ${entityTitle}`}
            </h2>
            <p id={subtitleId} className="dialog-subtitle">
              {mode === "create"
                ? `Add a new platform-managed ${entityTitle.toLowerCase()} under ${parentLabel}.`
                : `Update metadata and ordering for this ${entityTitle.toLowerCase()}.`}
            </p>
          </div>
          <button
            type="button"
            className="dialog-close-btn"
            onClick={handleClose}
            disabled={isSubmitting}
            aria-label={`Close ${entityTitle.toLowerCase()} dialog`}
          >
            <CloseIcon size={18} />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="dialog-body" noValidate>
          {nonFieldError && (
            <div id={bannerErrorId} className="alert-box alert-danger" role="alert">
              <AlertCircleIcon size={16} style={{ flexShrink: 0 }} />
              <span>{nonFieldError}</span>
            </div>
          )}

          {/* Immediate Parent Context */}
          <div className="form-group-item">
            <label className="form-label">Immediate Parent</label>
            <div className="form-readonly-pill">{parentLabel}</div>
          </div>

          {/* Code Field */}
          <div className="form-group-item">
            <label htmlFor={codeInputId} className="form-label">
              {entityTitle} Code <span className="text-danger">*</span>
            </label>
            {isCodeEditable ? (
              <>
                <input
                  ref={codeInputRef}
                  id={codeInputId}
                  name="code"
                  type="text"
                  className={`form-input ${fieldErrors.code ? "form-input-error" : ""}`}
                  placeholder="e.g. analytics-reports, grading-service"
                  value={code}
                  onChange={(e) => {
                    setCode(e.target.value);
                    if (fieldErrors.code) {
                      setFieldErrors((prev) => {
                        const next = { ...prev };
                        delete next.code;
                        return next;
                      });
                    }
                  }}
                  disabled={isSubmitting}
                  maxLength={50}
                  aria-invalid={Boolean(fieldErrors.code)}
                  aria-describedby={fieldErrors.code ? codeErrorId : codeHintId}
                  required
                />
                {!fieldErrors.code ? (
                  <p id={codeHintId} className="form-hint">
                    Lowercase alphanumeric slug with hyphens or underscores (max 50 chars).
                  </p>
                ) : (
                  <p id={codeErrorId} className="form-error" role="alert">
                    <AlertCircleIcon size={14} style={{ flexShrink: 0 }} />
                    <span>{fieldErrors.code}</span>
                  </p>
                )}
              </>
            ) : (
              <>
                <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                  <input
                    id={codeInputId}
                    name="code"
                    type="text"
                    className="form-input form-input-readonly"
                    value={code}
                    readOnly
                    disabled
                  />
                  <span className="badge badge-neutral" style={{ flexShrink: 0 }}>
                    Immutable
                  </span>
                </div>
                <p className="form-hint">Code is permanently immutable after activation.</p>
              </>
            )}
          </div>

          {/* Name Field */}
          <div className="form-group-item">
            <label htmlFor={nameInputId} className="form-label">
              {entityTitle} Name <span className="text-danger">*</span>
            </label>
            <input
              ref={nameInputRef}
              id={nameInputId}
              name="name"
              type="text"
              className={`form-input ${fieldErrors.name ? "form-input-error" : ""}`}
              placeholder={`e.g. Comprehensive ${entityTitle}`}
              value={name}
              onChange={(e) => {
                setName(e.target.value);
                if (fieldErrors.name) {
                  setFieldErrors((prev) => {
                    const next = { ...prev };
                    delete next.name;
                    return next;
                  });
                }
              }}
              disabled={isSubmitting}
              maxLength={100}
              aria-invalid={Boolean(fieldErrors.name)}
              aria-describedby={fieldErrors.name ? nameErrorId : undefined}
              required
            />
            {fieldErrors.name && (
              <p id={nameErrorId} className="form-error" role="alert">
                <AlertCircleIcon size={14} style={{ flexShrink: 0 }} />
                <span>{fieldErrors.name}</span>
              </p>
            )}
          </div>

          {/* Description Field */}
          <div className="form-group-item">
            <label htmlFor={descInputId} className="form-label">
              Description <span className="text-muted">(Optional)</span>
            </label>
            <textarea
              id={descInputId}
              name="description"
              className={`form-input form-textarea ${fieldErrors.description ? "form-input-error" : ""}`}
              placeholder="Operational scope and purpose of this catalog item..."
              value={description}
              onChange={(e) => {
                setDescription(e.target.value);
                if (fieldErrors.description) {
                  setFieldErrors((prev) => {
                    const next = { ...prev };
                    delete next.description;
                    return next;
                  });
                }
              }}
              disabled={isSubmitting}
              maxLength={1000}
              rows={2}
              aria-invalid={Boolean(fieldErrors.description)}
              aria-describedby={fieldErrors.description ? descErrorId : undefined}
            />
            {fieldErrors.description && (
              <p id={descErrorId} className="form-error" role="alert">
                <AlertCircleIcon size={14} style={{ flexShrink: 0 }} />
                <span>{fieldErrors.description}</span>
              </p>
            )}
          </div>

          {/* Display Order Field */}
          <div className="form-group-item">
            <label htmlFor={orderInputId} className="form-label">
              Display Order
            </label>
            <input
              id={orderInputId}
              name="display_order"
              type="number"
              min={0}
              step={1}
              className={`form-input ${fieldErrors.display_order ? "form-input-error" : ""}`}
              value={displayOrder}
              onChange={(e) => {
                const val = parseInt(e.target.value, 10);
                setDisplayOrder(isNaN(val) ? 0 : Math.max(0, val));
              }}
              disabled={isSubmitting}
              style={{ maxWidth: "160px" }}
              aria-invalid={Boolean(fieldErrors.display_order)}
              aria-describedby={fieldErrors.display_order ? orderErrorId : orderHintId}
            />
            {fieldErrors.display_order ? (
              <p id={orderErrorId} className="form-error" role="alert">
                <AlertCircleIcon size={14} style={{ flexShrink: 0 }} />
                <span>{fieldErrors.display_order}</span>
              </p>
            ) : (
              <p id={orderHintId} className="form-hint">
                Non-negative integer controlling relative sort position.
              </p>
            )}
          </div>

          {/* Initial Status Notice in Create Mode */}
          {mode === "create" && (
            <div className="form-group-item">
              <label className="form-label">Initial Lifecycle Status</label>
              <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                <span className="badge badge-neutral">Draft</span>
                <span className="text-caption">
                  All new catalog items are initialized in Draft state.
                </span>
              </div>
            </div>
          )}

          {/* Footer Actions */}
          <div className="dialog-footer">
            <button
              type="button"
              className="btn btn-secondary"
              onClick={handleClose}
              disabled={isSubmitting}
            >
              Cancel
            </button>
            <button type="submit" className="btn btn-primary" disabled={isSubmitting}>
              {isSubmitting
                ? mode === "create"
                  ? "Registering..."
                  : "Saving..."
                : mode === "create"
                ? `Register ${entityTitle}`
                : "Save Changes"}
            </button>
          </div>
        </form>
      </div>

      <style>{`
        .form-textarea {
          min-height: 64px;
          resize: vertical;
        }
      `}</style>
    </div>
  );
};
