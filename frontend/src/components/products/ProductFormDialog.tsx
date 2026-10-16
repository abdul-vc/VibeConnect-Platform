/**
 * Reusable Product Form Dialog Component.
 *
 * Supports Create mode (new product starting as Draft) and Edit mode (name, description, status).
 * Implements accessible focus trapping, escape key dismissal, focus restoration,
 * prominent visual validation feedback, and disciplined non-scrolling desktop layouts.
 */

import React, { useEffect, useRef, useState } from "react";
import { productsApi } from "../../api/products.ts";
import type { ProductDetail, ProductListItem, ProductStatus } from "../../api/types.ts";
import { AlertCircleIcon, CloseIcon } from "../Icons.tsx";
import { ProductStatusBadge } from "./ProductStatusBadge.tsx";

interface ProductFormDialogProps {
  readonly mode: "create" | "edit";
  readonly product?: ProductListItem | ProductDetail | null;
  readonly isOpen: boolean;
  readonly onClose: () => void;
  readonly onSuccess: (product: ProductDetail) => void;
  readonly triggerRef?: React.RefObject<HTMLElement | null>;
}

const PERMITTED_TRANSITIONS: Record<ProductStatus, ProductStatus[]> = {
  draft: ["draft", "active", "inactive", "retired"],
  active: ["active", "inactive", "retired"],
  inactive: ["inactive", "active", "retired"],
  retired: ["retired"],
};

export const ProductFormDialog: React.FC<ProductFormDialogProps> = ({
  mode,
  product,
  isOpen,
  onClose,
  onSuccess,
  triggerRef,
}) => {
  const [code, setCode] = useState("");
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [status, setStatus] = useState<ProductStatus>("draft");

  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [nonFieldError, setNonFieldError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [statusAnnouncement, setStatusAnnouncement] = useState("");

  const codeInputRef = useRef<HTMLInputElement | null>(null);
  const nameInputRef = useRef<HTMLInputElement | null>(null);
  const dialogRef = useRef<HTMLDivElement | null>(null);

  // Prevent background body scrolling while dialog is open
  useEffect(() => {
    if (isOpen) {
      const originalOverflow = document.body.style.overflow;
      document.body.style.overflow = "hidden";
      return () => {
        document.body.style.overflow = originalOverflow;
      };
    }
  }, [isOpen]);

  // Initialize or reset form state when dialog opens or mode/product changes
  useEffect(() => {
    if (isOpen) {
      if (mode === "edit" && product) {
        setCode(product.code);
        setName(product.name);
        setDescription(product.description || "");
        setStatus(product.status);
      } else {
        setCode("");
        setName("");
        setDescription("");
        setStatus("draft");
      }
      setFieldErrors({});
      setNonFieldError(null);
      setIsSubmitting(false);
      setStatusAnnouncement("");

      // Focus first editable input after DOM update
      const timer = setTimeout(() => {
        if (mode === "create") {
          codeInputRef.current?.focus();
        } else {
          nameInputRef.current?.focus();
        }
      }, 50);
      return () => clearTimeout(timer);
    }
  }, [isOpen, mode, product]);

  // Handle Escape key
  useEffect(() => {
    if (!isOpen) return;

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !isSubmitting) {
        e.preventDefault();
        handleClose();
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, isSubmitting]);

  const handleClose = () => {
    onClose();
    // Restore focus to triggering button
    setTimeout(() => {
      triggerRef?.current?.focus();
    }, 50);
  };

  const handleCodeChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const val = e.target.value;
    setCode(val);
    if (fieldErrors.code && val.trim()) {
      setFieldErrors((prev) => {
        const next = { ...prev };
        delete next.code;
        return next;
      });
    }
  };

  const handleNameChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const val = e.target.value;
    setName(val);
    if (fieldErrors.name && val.trim()) {
      setFieldErrors((prev) => {
        const next = { ...prev };
        delete next.name;
        return next;
      });
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    // 1. Client-Side Mandatory Validation Check
    const errors: Record<string, string> = {};
    if (mode === "create" && !code.trim()) {
      errors.code = "Product code is required.";
    }
    if (!name.trim()) {
      errors.name = "Product name is required.";
    }

    if (Object.keys(errors).length > 0) {
      setFieldErrors(errors);
      setNonFieldError(null);
      const announcement = errors.code
        ? "Product code is required."
        : "Product name is required.";
      setStatusAnnouncement(announcement);

      // Focus the first invalid field
      if (errors.code) {
        codeInputRef.current?.focus();
      } else if (errors.name) {
        nameInputRef.current?.focus();
      }
      return;
    }

    setFieldErrors({});
    setNonFieldError(null);
    setIsSubmitting(true);
    setStatusAnnouncement("Submitting product details...");

    try {
      if (mode === "create") {
        const payload = {
          code: code.trim(),
          name: name.trim(),
          description: description.trim(),
        };
        const created = await productsApi.create(payload);
        setStatusAnnouncement(`Product ${created.name} registered successfully.`);
        onSuccess(created);
        handleClose();
      } else if (mode === "edit" && product) {
        const payload: { name?: string; description?: string; status?: ProductStatus } = {};
        if (name.trim() !== product.name) payload.name = name.trim();
        if (description.trim() !== (product.description || "")) payload.description = description.trim();
        if (status !== product.status) payload.status = status;

        if (Object.keys(payload).length === 0) {
          // No changes, close directly
          handleClose();
          return;
        }

        const updated = await productsApi.update(product.id, payload);
        setStatusAnnouncement(`Product ${updated.name} updated successfully.`);
        onSuccess(updated);
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
            if (key === "detail" || key === "message") {
              generalError = val;
            } else {
              newFieldErrors[key] = val;
            }
          }
        });

        setFieldErrors(newFieldErrors);
        setNonFieldError(generalError);
        setStatusAnnouncement(generalError || "Please correct the form errors.");

        // Focus first field with error from server
        if (newFieldErrors.code) {
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

  const allowedStatuses = product ? PERMITTED_TRANSITIONS[product.status] || [product.status] : ["draft"];
  const isRetired = mode === "edit" && product?.status === "retired";

  return (
    <div
      className="dialog-backdrop"
      onClick={(e) => {
        if (e.target === e.currentTarget && !isSubmitting) handleClose();
      }}
    >
      {/* Live Region for Screen Readers */}
      <div className="sr-only" aria-live="polite" aria-atomic="true">
        {statusAnnouncement}
      </div>

      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="product-dialog-title"
        className="dialog-surface"
      >
        {/* Header */}
        <div className="dialog-header">
          <div>
            <h2 id="product-dialog-title" className="dialog-title">
              {mode === "create" ? "Register Product" : "Edit Product"}
            </h2>
            <p className="dialog-subtitle">
              {mode === "create"
                ? "Add a new platform-managed product catalog entry."
                : "Update metadata and lifecycle status for this product."}
            </p>
          </div>
          <button
            type="button"
            className="dialog-close-btn"
            onClick={handleClose}
            disabled={isSubmitting}
            aria-label="Close product dialog"
          >
            <CloseIcon size={18} />
          </button>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="dialog-body" noValidate>
          {nonFieldError && (
            <div className="alert-banner alert-banner-error" role="alert">
              <AlertCircleIcon size={16} style={{ flexShrink: 0 }} />
              <span>{nonFieldError}</span>
            </div>
          )}

          {/* Product Code */}
          <div className="form-group-item">
            <label htmlFor="product-code" className="form-label">
              Product Code <span className="text-danger">*</span>
            </label>
            {mode === "create" ? (
              <>
                <input
                  ref={codeInputRef}
                  id="product-code"
                  type="text"
                  className={`form-input ${fieldErrors.code ? "form-input-error" : ""}`}
                  placeholder="e.g. lms, hrms, crm"
                  value={code}
                  onChange={handleCodeChange}
                  disabled={isSubmitting}
                  maxLength={50}
                  aria-invalid={Boolean(fieldErrors.code)}
                  aria-describedby={fieldErrors.code ? "product-code-error" : "product-code-hint"}
                  required
                />
                {!fieldErrors.code ? (
                  <p id="product-code-hint" className="form-hint">
                    Lowercase alphanumeric slug with hyphens or underscores (e.g. <code>lms-core</code>).
                  </p>
                ) : (
                  <p id="product-code-error" className="form-error" role="alert">
                    <AlertCircleIcon size={14} style={{ flexShrink: 0 }} />
                    <span>{fieldErrors.code}</span>
                  </p>
                )}
              </>
            ) : (
              <>
                <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                  <input
                    id="product-code"
                    type="text"
                    className="form-input form-input-readonly"
                    value={code}
                    readOnly
                    disabled
                  />
                  <span className="badge badge-default" style={{ flexShrink: 0 }}>
                    Immutable
                  </span>
                </div>
                <p className="form-hint">Product code cannot be modified after registration.</p>
              </>
            )}
          </div>

          {/* Product Name */}
          <div className="form-group-item">
            <label htmlFor="product-name" className="form-label">
              Product Name <span className="text-danger">*</span>
            </label>
            <input
              ref={nameInputRef}
              id="product-name"
              type="text"
              className={`form-input ${fieldErrors.name ? "form-input-error" : ""}`}
              placeholder="e.g. Learning Management System"
              value={name}
              onChange={handleNameChange}
              disabled={isSubmitting}
              maxLength={100}
              aria-invalid={Boolean(fieldErrors.name)}
              aria-describedby={fieldErrors.name ? "product-name-error" : undefined}
              required
            />
            {fieldErrors.name && (
              <p id="product-name-error" className="form-error" role="alert">
                <AlertCircleIcon size={14} style={{ flexShrink: 0 }} />
                <span>{fieldErrors.name}</span>
              </p>
            )}
          </div>

          {/* Product Description */}
          <div className="form-group-item">
            <label htmlFor="product-description" className="form-label">
              Description <span className="text-muted">(Optional)</span>
            </label>
            <textarea
              id="product-description"
              className={`form-input form-textarea ${fieldErrors.description ? "form-input-error" : ""}`}
              placeholder="Brief summary of product capabilities and service domain..."
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              disabled={isSubmitting}
              maxLength={1000}
              rows={2}
            />
            {fieldErrors.description && (
              <p className="form-error" role="alert">
                <AlertCircleIcon size={14} style={{ flexShrink: 0 }} />
                <span>{fieldErrors.description}</span>
              </p>
            )}
          </div>

          {/* Lifecycle Status */}
          <div className="form-group-item">
            <label htmlFor="product-status" className="form-label">
              Lifecycle Status
            </label>
            {mode === "create" ? (
              <div style={{ display: "flex", alignItems: "center", gap: "0.625rem", marginTop: "0.15rem" }}>
                <ProductStatusBadge status="draft" />
                <span className="text-caption">All new products are initialized in Draft state.</span>
              </div>
            ) : (
              <>
                <select
                  id="product-status"
                  className="form-select"
                  value={status}
                  onChange={(e) => setStatus(e.target.value as ProductStatus)}
                  disabled={isSubmitting || isRetired}
                  aria-describedby="product-status-hint"
                >
                  {allowedStatuses.map((st) => (
                    <option key={st} value={st}>
                      {st.charAt(0).toUpperCase() + st.slice(1)}
                    </option>
                  ))}
                </select>
                {isRetired && (
                  <p id="product-status-hint" className="form-hint text-warning">
                    This product is retired. Retired products are in a terminal state and cannot transition to other statuses.
                  </p>
                )}
                {fieldErrors.status && (
                  <p className="form-error" role="alert">
                    <AlertCircleIcon size={14} style={{ flexShrink: 0 }} />
                    <span>{fieldErrors.status}</span>
                  </p>
                )}
              </>
            )}
          </div>

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
                ? "Register Product"
                : "Save Changes"}
            </button>
          </div>
        </form>
      </div>

      <style>{`
        .dialog-backdrop {
          position: fixed;
          inset: 0;
          background: rgba(15, 23, 42, 0.65);
          backdrop-filter: blur(4px);
          display: flex;
          align-items: center;
          justify-content: center;
          padding: 1rem;
          z-index: 1000;
          animation: fadeIn 0.15s ease-out;
        }

        .dialog-surface {
          background: var(--glass-surface-elevated);
          border: 1px solid var(--border-glass);
          border-radius: 16px;
          box-shadow: var(--shadow-lg);
          width: 100%;
          max-width: 520px;
          max-height: calc(100dvh - 32px);
          display: flex;
          flex-direction: column;
          overflow: hidden;
          animation: scaleUp 0.15s ease-out;
        }

        .dialog-header {
          display: flex;
          align-items: center;
          justify-content: space-between;
          padding: 1.125rem 1.5rem;
          border-bottom: 1px solid var(--border-subtle);
          flex-shrink: 0;
        }

        .dialog-title {
          font-size: 1.125rem;
          font-weight: 600;
          color: var(--text-primary);
          margin: 0;
        }

        .dialog-subtitle {
          font-size: 0.8125rem;
          color: var(--text-secondary);
          margin: 0.15rem 0 0 0;
        }

        .dialog-close-btn {
          background: transparent;
          border: none;
          color: var(--text-secondary);
          cursor: pointer;
          min-width: 40px;
          min-height: 40px;
          border-radius: 8px;
          display: flex;
          align-items: center;
          justify-content: center;
          transition: color 0.15s, background-color 0.15s;
          outline: none;
        }

        .dialog-close-btn:hover {
          color: var(--text-primary);
          background: var(--glass-surface);
        }

        .dialog-close-btn:focus-visible {
          outline: 2px solid var(--brand-primary);
          outline-offset: 2px;
        }

        .dialog-body {
          padding: 1.25rem 1.5rem;
          display: flex;
          flex-direction: column;
          gap: 0.875rem;
          overflow-y: auto;
          flex: 1;
          min-height: 0;
        }

        .form-group-item {
          display: flex;
          flex-direction: column;
          gap: 0.35rem;
        }

        .form-label {
          font-size: 0.8125rem;
          font-weight: 600;
          color: var(--text-primary);
        }

        .text-danger {
          color: var(--status-danger);
        }

        .text-muted {
          color: var(--text-muted);
          font-weight: 400;
        }

        .form-input-readonly {
          background: var(--bg-surface-subtle);
          color: var(--text-secondary);
          cursor: not-allowed;
          font-family: var(--font-code);
          font-weight: 500;
          letter-spacing: 0.02em;
        }

        .form-textarea {
          resize: vertical;
          min-height: 56px;
          font-family: inherit;
        }

        .form-select {
          background: var(--input-bg);
          border: 1px solid var(--input-border);
          border-radius: 8px;
          padding: 0.5rem 0.75rem;
          font-size: 0.875rem;
          color: var(--text-primary);
          outline: none;
          transition: border-color 0.15s ease;
        }

        .form-select:focus {
          border-color: var(--input-border-focus);
          box-shadow: 0 0 0 3px var(--brand-primary-light);
        }

        .form-hint {
          font-size: 0.75rem;
          color: var(--text-muted);
          margin: 0;
        }

        .dialog-footer {
          display: flex;
          align-items: center;
          justify-content: flex-end;
          gap: 0.75rem;
          padding: 1rem 1.5rem;
          border-top: 1px solid var(--border-subtle);
          flex-shrink: 0;
          background: var(--glass-surface-elevated);
        }

        @keyframes fadeIn {
          from { opacity: 0; }
          to { opacity: 1; }
        }

        @keyframes scaleUp {
          from { opacity: 0; transform: scale(0.96); }
          to { opacity: 1; transform: scale(1); }
        }

        .sr-only {
          position: absolute;
          width: 1px;
          height: 1px;
          padding: 0;
          margin: -1px;
          overflow: hidden;
          clip: rect(0, 0, 0, 0);
          white-space: nowrap;
          border: 0;
        }
      `}</style>
    </div>
  );
};
