/**
 * Entitlement Form Dialog Component.
 *
 * Accessible modal dialog for registering and managing Organization-Product entitlements.
 * Implements active parent asynchronous search selectors with server-side pagination,
 * lifecycle state transitions, permanent revocation warnings without window.confirm,
 * focus trapping, and double-submit prevention.
 */

import React, { useCallback, useEffect, useRef, useState } from "react";
import { entitlementsApi } from "../../api/entitlements.ts";
import { organizationsApi } from "../../api/organizations.ts";
import { productsApi } from "../../api/products.ts";
import type {
  CreateEntitlementPayload,
  EntitlementDetail,
  EntitlementListItem,
  EntitlementStatus,
  OrganizationListItem,
  ProductListItem,
  UpdateEntitlementPayload,
} from "../../api/types.ts";
import { AlertCircleIcon, CloseIcon, SearchIcon } from "../Icons.tsx";

interface EntitlementFormDialogProps {
  readonly isOpen: boolean;
  readonly mode: "create" | "edit";
  readonly entitlement: EntitlementListItem | null;
  readonly onClose: () => void;
  readonly onSuccess: (entitlement: EntitlementDetail) => void;
  readonly triggerRef?: React.RefObject<HTMLElement | null>;
}

export const EntitlementFormDialog: React.FC<EntitlementFormDialogProps> = ({
  isOpen,
  mode,
  entitlement,
  onClose,
  onSuccess,
  triggerRef,
}) => {
  // Create mode state
  const [selectedOrgId, setSelectedOrgId] = useState<string>("");
  const [selectedProdId, setSelectedProdId] = useState<string>("");
  const [selectedOrgItem, setSelectedOrgItem] = useState<OrganizationListItem | null>(null);
  const [selectedProdItem, setSelectedProdItem] = useState<ProductListItem | null>(null);

  const [orgSearch, setOrgSearch] = useState<string>("");
  const [prodSearch, setProdSearch] = useState<string>("");
  const [orgPage, setOrgPage] = useState<number>(1);
  const [prodPage, setProdPage] = useState<number>(1);
  const selectorPageSize = 20;

  const [activeOrgs, setActiveOrgs] = useState<OrganizationListItem[]>([]);
  const [activeProds, setActiveProds] = useState<ProductListItem[]>([]);
  const [orgsLoading, setOrgsLoading] = useState<boolean>(false);
  const [prodsLoading, setProdsLoading] = useState<boolean>(false);
  const [totalActiveOrgs, setTotalActiveOrgs] = useState<number>(0);
  const [totalActiveProds, setTotalActiveProds] = useState<number>(0);

  // Edit mode state
  const [status, setStatus] = useState<EntitlementStatus>("draft");
  const [revocationConfirmed, setRevocationConfirmed] = useState<boolean>(false);

  // Mutation and error states
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [generalError, setGeneralError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);

  const dialogRef = useRef<HTMLDivElement | null>(null);
  const firstControlRef = useRef<HTMLSelectElement | HTMLInputElement | null>(null);

  // Request sequence guards
  const orgSeqRef = useRef<number>(0);
  const prodSeqRef = useRef<number>(0);

  // Fetch active organizations (server-side search + pagination)
  const fetchActiveOrgs = useCallback(async (query: string, pageNum: number) => {
    const seq = ++orgSeqRef.current;
    setOrgsLoading(true);
    try {
      const res = await organizationsApi.list({
        status: "active",
        search: query || undefined,
        page: pageNum,
        page_size: selectorPageSize,
      });
      if (seq === orgSeqRef.current) {
        setActiveOrgs(res.results as OrganizationListItem[]);
        setTotalActiveOrgs(res.count);
        setOrgsLoading(false);
      }
    } catch {
      if (seq === orgSeqRef.current) {
        setOrgsLoading(false);
      }
    }
  }, []);

  // Fetch active products (server-side search + pagination)
  const fetchActiveProds = useCallback(async (query: string, pageNum: number) => {
    const seq = ++prodSeqRef.current;
    setProdsLoading(true);
    try {
      const res = await productsApi.list({
        status: "active",
        search: query || undefined,
        page: pageNum,
        page_size: selectorPageSize,
      });
      if (seq === prodSeqRef.current) {
        setActiveProds(res.results as ProductListItem[]);
        setTotalActiveProds(res.count);
        setProdsLoading(false);
      }
    } catch {
      if (seq === prodSeqRef.current) {
        setProdsLoading(false);
      }
    }
  }, []);

  // Debounced search trigger for organizations (resets to page 1)
  useEffect(() => {
    if (!isOpen || mode !== "create") return;
    const timer = setTimeout(() => {
      setOrgPage(1);
      fetchActiveOrgs(orgSearch.trim(), 1);
    }, 300);
    return () => clearTimeout(timer);
  }, [orgSearch, isOpen, mode, fetchActiveOrgs]);

  // Debounced search trigger for products (resets to page 1)
  useEffect(() => {
    if (!isOpen || mode !== "create") return;
    const timer = setTimeout(() => {
      setProdPage(1);
      fetchActiveProds(prodSearch.trim(), 1);
    }, 300);
    return () => clearTimeout(timer);
  }, [prodSearch, isOpen, mode, fetchActiveProds]);

  // Reset or initialize state when opening
  useEffect(() => {
    if (isOpen) {
      if (mode === "edit" && entitlement) {
        setStatus(entitlement.status);
        setRevocationConfirmed(false);
      } else {
        setSelectedOrgId("");
        setSelectedProdId("");
        setSelectedOrgItem(null);
        setSelectedProdItem(null);
        setOrgSearch("");
        setProdSearch("");
        setOrgPage(1);
        setProdPage(1);
        setStatus("draft");
        setRevocationConfirmed(false);
        fetchActiveOrgs("", 1);
        fetchActiveProds("", 1);
      }
      setFieldErrors({});
      setGeneralError(null);
      setIsSubmitting(false);

      setTimeout(() => {
        if (firstControlRef.current) {
          firstControlRef.current.focus();
        }
      }, 50);
    }
  }, [isOpen, mode, entitlement, fetchActiveOrgs, fetchActiveProds]);

  // Focus trap and Escape key listener
  useEffect(() => {
    if (!isOpen) return;

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        if (!isSubmitting) {
          handleClose();
        }
      } else if (e.key === "Tab") {
        if (!dialogRef.current) return;
        const focusable = dialogRef.current.querySelectorAll<HTMLElement>(
          'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
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
    if (isSubmitting) return;
    onClose();
    if (triggerRef?.current) {
      triggerRef.current.focus();
    }
  };

  const getAllowedStatuses = (): EntitlementStatus[] => {
    if (!entitlement) return ["draft"];
    switch (entitlement.status) {
      case "draft":
        return ["draft", "active", "revoked"];
      case "active":
        return ["active", "suspended", "revoked"];
      case "suspended":
        return ["suspended", "active", "revoked"];
      case "revoked":
        return ["revoked"];
      default:
        return ["draft"];
    }
  };

  const validateForm = (): boolean => {
    const errors: Record<string, string> = {};

    if (mode === "create") {
      if (!selectedOrgId) {
        errors.organization_id = "Please select an active organization.";
      }
      if (!selectedProdId) {
        errors.product_id = "Please select an active product.";
      }
    }

    if (mode === "edit" && status === "revoked" && entitlement?.status !== "revoked") {
      if (!revocationConfirmed) {
        errors.revocation = "You must confirm that you understand this action permanently closes this access record.";
      }
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
        const payload: CreateEntitlementPayload = {
          organization_id: selectedOrgId,
          product_id: selectedProdId,
        };
        const result = await entitlementsApi.create(payload);
        setIsSubmitting(false);
        onSuccess(result);
        handleClose();
      } else if (mode === "edit" && entitlement) {
        const payload: UpdateEntitlementPayload = {
          status,
        };
        const result = await entitlementsApi.update(entitlement.id, payload);
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
        if (errors.non_field_errors) {
          setGeneralError(errors.non_field_errors);
        } else if (errors.detail && Object.keys(errors).length === 1) {
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

  const noActiveOrgsAvailable = !orgsLoading && totalActiveOrgs === 0 && !orgSearch;
  const noActiveProdsAvailable = !prodsLoading && totalActiveProds === 0 && !prodSearch;
  const canSubmitCreate = !noActiveOrgsAvailable && !noActiveProdsAvailable;

  const displayedOrgs = selectedOrgItem && !activeOrgs.some((o) => o.id === selectedOrgItem.id)
    ? [selectedOrgItem, ...activeOrgs]
    : activeOrgs;

  const displayedProds = selectedProdItem && !activeProds.some((p) => p.id === selectedProdItem.id)
    ? [selectedProdItem, ...activeProds]
    : activeProds;

  const totalOrgPages = Math.max(1, Math.ceil(totalActiveOrgs / selectorPageSize));
  const totalProdPages = Math.max(1, Math.ceil(totalActiveProds / selectorPageSize));

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
              {mode === "create" ? "Register Product Access" : "Update Product Access"}
            </h2>
            <p id="dialog-description" className="dialog-desc">
              {mode === "create"
                ? "Grant an active customer organization authorization to access a platform product."
                : `Manage authorization lifecycle status for ${entitlement?.organization.name}.`}
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

        {/* Form */}
        <form onSubmit={handleSubmit} noValidate className="dialog-form">
          {mode === "create" ? (
            <>
              {/* Organization Selector */}
              <div className="form-group">
                <label htmlFor="org-select" className="form-label">
                  Active Organization <span className="required-asterisk">*</span>
                </label>
                {noActiveOrgsAvailable ? (
                  <div className="dialog-alert-warning" role="alert">
                    <AlertCircleIcon size={16} />
                    <span>No active organizations available. Register and activate an organization first.</span>
                  </div>
                ) : (
                  <>
                    <div className="searchable-select-wrapper">
                      <div className="search-box-inner">
                        <SearchIcon size={14} />
                        <input
                          type="search"
                          className="search-inner-input"
                          placeholder="Search active organizations..."
                          value={orgSearch}
                          onChange={(e) => setOrgSearch(e.target.value)}
                          disabled={isSubmitting}
                          aria-label="Search active organizations"
                        />
                      </div>
                      <select
                        ref={firstControlRef as React.RefObject<HTMLSelectElement>}
                        id="org-select"
                        className={`form-select ${fieldErrors.organization_id ? "input-error" : ""}`}
                        value={selectedOrgId}
                        onChange={(e) => {
                          const val = e.target.value;
                          setSelectedOrgId(val);
                          const found = displayedOrgs.find((o) => o.id === val) || null;
                          setSelectedOrgItem(found);
                        }}
                        disabled={isSubmitting || orgsLoading}
                        aria-invalid={!!fieldErrors.organization_id}
                        aria-describedby={fieldErrors.organization_id ? "org-select-error" : "org-select-help"}
                      >
                        <option value="">-- Select an active organization --</option>
                        {displayedOrgs.map((o) => (
                          <option key={o.id} value={o.id}>
                            {o.name} ({o.code})
                          </option>
                        ))}
                      </select>

                      {/* Selector Pagination Controls */}
                      {totalActiveOrgs > selectorPageSize && (
                        <div
                          style={{
                            display: "flex",
                            justifyContent: "space-between",
                            alignItems: "center",
                            fontSize: "0.75rem",
                            padding: "0.25rem 0.1rem",
                          }}
                        >
                          <span style={{ color: "var(--text-muted)" }}>
                            Showing {activeOrgs.length} of {totalActiveOrgs} (Page {orgPage} of {totalOrgPages})
                          </span>
                          <div style={{ display: "flex", gap: "0.35rem" }}>
                            <button
                              type="button"
                              className="btn btn-secondary btn-sm"
                              disabled={orgPage <= 1 || orgsLoading}
                              onClick={() => {
                                const prev = orgPage - 1;
                                setOrgPage(prev);
                                fetchActiveOrgs(orgSearch.trim(), prev);
                              }}
                              style={{ minHeight: "36px", padding: "0.25rem 0.6rem", fontSize: "0.75rem" }}
                              aria-label="Previous page of organizations"
                            >
                              Prev
                            </button>
                            <button
                              type="button"
                              className="btn btn-secondary btn-sm"
                              disabled={orgPage >= totalOrgPages || orgsLoading}
                              onClick={() => {
                                const next = orgPage + 1;
                                setOrgPage(next);
                                fetchActiveOrgs(orgSearch.trim(), next);
                              }}
                              style={{ minHeight: "36px", padding: "0.25rem 0.6rem", fontSize: "0.75rem" }}
                              aria-label="Next page of organizations"
                            >
                              Next
                            </button>
                          </div>
                        </div>
                      )}
                    </div>
                    <span id="org-select-help" className="form-help-text">
                      Only active organizations can receive product access.
                    </span>
                  </>
                )}
                {fieldErrors.organization_id && (
                  <span id="org-select-error" className="field-error-message" role="alert">
                    {fieldErrors.organization_id}
                  </span>
                )}
              </div>

              {/* Product Selector */}
              <div className="form-group">
                <label htmlFor="prod-select" className="form-label">
                  Active Product <span className="required-asterisk">*</span>
                </label>
                {noActiveProdsAvailable ? (
                  <div className="dialog-alert-warning" role="alert">
                    <AlertCircleIcon size={16} />
                    <span>No active products available.</span>
                  </div>
                ) : (
                  <>
                    <div className="searchable-select-wrapper">
                      <div className="search-box-inner">
                        <SearchIcon size={14} />
                        <input
                          type="search"
                          className="search-inner-input"
                          placeholder="Search active products..."
                          value={prodSearch}
                          onChange={(e) => setProdSearch(e.target.value)}
                          disabled={isSubmitting}
                          aria-label="Search active products"
                        />
                      </div>
                      <select
                        id="prod-select"
                        className={`form-select ${fieldErrors.product_id ? "input-error" : ""}`}
                        value={selectedProdId}
                        onChange={(e) => {
                          const val = e.target.value;
                          setSelectedProdId(val);
                          const found = displayedProds.find((p) => p.id === val) || null;
                          setSelectedProdItem(found);
                        }}
                        disabled={isSubmitting || prodsLoading}
                        aria-invalid={!!fieldErrors.product_id}
                        aria-describedby={fieldErrors.product_id ? "prod-select-error" : "prod-select-help"}
                      >
                        <option value="">-- Select an active product --</option>
                        {displayedProds.map((p) => (
                          <option key={p.id} value={p.id}>
                            {p.name} ({p.code})
                          </option>
                        ))}
                      </select>

                      {/* Selector Pagination Controls */}
                      {totalActiveProds > selectorPageSize && (
                        <div
                          style={{
                            display: "flex",
                            justifyContent: "space-between",
                            alignItems: "center",
                            fontSize: "0.75rem",
                            padding: "0.25rem 0.1rem",
                          }}
                        >
                          <span style={{ color: "var(--text-muted)" }}>
                            Showing {activeProds.length} of {totalActiveProds} (Page {prodPage} of {totalProdPages})
                          </span>
                          <div style={{ display: "flex", gap: "0.35rem" }}>
                            <button
                              type="button"
                              className="btn btn-secondary btn-sm"
                              disabled={prodPage <= 1 || prodsLoading}
                              onClick={() => {
                                const prev = prodPage - 1;
                                setProdPage(prev);
                                fetchActiveProds(prodSearch.trim(), prev);
                              }}
                              style={{ minHeight: "36px", padding: "0.25rem 0.6rem", fontSize: "0.75rem" }}
                              aria-label="Previous page of products"
                            >
                              Prev
                            </button>
                            <button
                              type="button"
                              className="btn btn-secondary btn-sm"
                              disabled={prodPage >= totalProdPages || prodsLoading}
                              onClick={() => {
                                const next = prodPage + 1;
                                setProdPage(next);
                                fetchActiveProds(prodSearch.trim(), next);
                              }}
                              style={{ minHeight: "36px", padding: "0.25rem 0.6rem", fontSize: "0.75rem" }}
                              aria-label="Next page of products"
                            >
                              Next
                            </button>
                          </div>
                        </div>
                      )}
                    </div>
                    <span id="prod-select-help" className="form-help-text">
                      Only active products can be assigned.
                    </span>
                  </>
                )}
                {fieldErrors.product_id && (
                  <span id="prod-select-error" className="field-error-message" role="alert">
                    {fieldErrors.product_id}
                  </span>
                )}
              </div>
            </>
          ) : (
            <>
              {/* Edit Mode Read-Only Parents */}
              <div className="form-group">
                <span className="form-label">Organization</span>
                <div className="read-only-field">
                  <span style={{ fontWeight: 600, color: "var(--text-primary)" }}>
                    {entitlement?.organization.name}
                  </span>
                  <span className="code-pill">{entitlement?.organization.code}</span>
                </div>
              </div>

              <div className="form-group">
                <span className="form-label">Product</span>
                <div className="read-only-field">
                  <span style={{ fontWeight: 600, color: "var(--text-primary)" }}>
                    {entitlement?.product.name}
                  </span>
                  <span className="code-pill">{entitlement?.product.code}</span>
                </div>
              </div>

              {/* Lifecycle Status Select */}
              <div className="form-group">
                <label htmlFor="status-select" className="form-label">
                  Lifecycle Status
                </label>
                <select
                  ref={firstControlRef as React.RefObject<HTMLSelectElement>}
                  id="status-select"
                  className="form-select"
                  value={status}
                  onChange={(e) => setStatus(e.target.value as EntitlementStatus)}
                  disabled={isSubmitting || entitlement?.status === "revoked"}
                  aria-describedby={status === "revoked" ? "revocation-warning-banner" : undefined}
                >
                  {getAllowedStatuses().map((st) => (
                    <option key={st} value={st}>
                      {st.charAt(0).toUpperCase() + st.slice(1)}
                    </option>
                  ))}
                </select>
              </div>

              {/* Irreversible Revocation Warning Banner */}
              {status === "revoked" && entitlement?.status !== "revoked" && (
                <div id="revocation-warning-banner" className="dialog-alert-warning" role="alert">
                  <AlertCircleIcon size={18} />
                  <div>
                    <p style={{ margin: "0 0 0.5rem 0", fontWeight: 600 }}>Permanent Action Notice</p>
                    <p style={{ margin: "0 0 0.75rem 0", fontSize: "0.8125rem", lineHeight: 1.45 }}>
                      Revoking this entitlement permanently closes the current access record. This record cannot be changed again. If the organization purchases this product in the future, a new entitlement can be created.
                    </p>
                    <label style={{ display: "flex", alignItems: "center", gap: "0.5rem", cursor: "pointer", fontSize: "0.8125rem", fontWeight: 500, minHeight: "44px" }}>
                      <input
                        type="checkbox"
                        checked={revocationConfirmed}
                        onChange={(e) => setRevocationConfirmed(e.target.checked)}
                        disabled={isSubmitting}
                        aria-invalid={!!fieldErrors.revocation}
                        aria-describedby={fieldErrors.revocation ? "revocation-error" : undefined}
                      />
                      <span>I understand this access record will be permanently closed.</span>
                    </label>
                    {fieldErrors.revocation && (
                      <span id="revocation-error" className="field-error-message" role="alert" style={{ display: "block", marginTop: "0.35rem" }}>
                        {fieldErrors.revocation}
                      </span>
                    )}
                  </div>
                </div>
              )}
            </>
          )}

          {/* Dialog Footer Actions */}
          <div className="dialog-footer">
            <button
              type="button"
              className="btn btn-secondary"
              onClick={handleClose}
              disabled={isSubmitting}
              style={{ minHeight: "44px" }}
            >
              Cancel
            </button>
            <button
              type="submit"
              className="btn btn-primary"
              disabled={isSubmitting || (mode === "create" && !canSubmitCreate)}
              style={{ minHeight: "44px" }}
            >
              {isSubmitting
                ? mode === "create"
                  ? "Registering..."
                  : "Updating..."
                : mode === "create"
                ? "Register Product Access"
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
          min-width: 44px;
          min-height: 44px;
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
          gap: 0.625rem;
          padding: 0.875rem 1rem;
          border-radius: 8px;
          background: var(--status-warning-bg);
          border: 1px solid var(--status-warning-border);
          color: var(--status-warning);
          font-size: 0.8125rem;
          line-height: 1.4;
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

        .searchable-select-wrapper {
          display: flex;
          flex-direction: column;
          gap: 0.35rem;
        }

        .search-box-inner {
          display: flex;
          align-items: center;
          gap: 0.5rem;
          padding: 0.35rem 0.65rem;
          border-radius: 6px;
          border: 1px solid var(--input-border);
          background: var(--glass-surface);
          color: var(--text-muted);
          min-height: 44px;
        }

        .search-inner-input {
          border: none;
          background: transparent;
          color: var(--text-primary);
          font-size: 0.8125rem;
          width: 100%;
          outline: none;
        }

        .form-select {
          width: 100%;
          min-height: 44px;
          padding: 0.5rem 0.875rem;
          font-size: 0.875rem;
          font-family: inherit;
          border-radius: 8px;
          border: 1px solid var(--input-border);
          background: var(--input-bg);
          color: var(--text-primary);
          outline: none;
          box-sizing: border-box;
          cursor: pointer;
          transition: border-color 0.15s ease, box-shadow 0.15s ease;
        }

        .form-select:focus {
          border-color: var(--input-border-focus);
          box-shadow: 0 0 0 3px var(--brand-primary-light);
        }

        .form-select option {
          background: var(--bg-solid-fallback);
          color: var(--text-primary);
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

        .read-only-field {
          display: flex;
          align-items: center;
          justify-content: space-between;
          padding: 0.625rem 0.875rem;
          background: var(--glass-surface-sunken);
          border: 1px solid var(--border-glass);
          border-radius: 8px;
          min-height: 44px;
        }

        .code-pill {
          display: inline-block;
          font-family: var(--font-code);
          font-size: 0.75rem;
          padding: 0.2rem 0.45rem;
          border-radius: 6px;
          background: var(--brand-primary-light);
          color: var(--brand-primary);
          border: 1px solid var(--border-glass);
          font-weight: 600;
          letter-spacing: -0.02em;
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

        @media (prefers-reduced-motion: reduce) {
          .dialog-panel,
          .dialog-close-btn,
          .form-select {
            transition: none !important;
          }
        }
      `}</style>
    </div>
  );
};
