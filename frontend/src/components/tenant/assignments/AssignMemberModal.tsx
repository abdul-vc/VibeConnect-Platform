/**
 * Assign Member Modal (Phase 2F Part E).
 *
 * Implements a 3-step Product-First Wizard:
 * - Step 1: Product Selection & Capacity Assessment
 *   - Loads entitled products from GET /api/v1/tenant/assignments/selectors/products/
 *   - Displays total limit, consumed seats, available seats, pool scope, and quota type
 *   - When available_seats === 0 (or !is_capacity_available): renders a clear capacity warning
 *     banner, disables the Next button, and preserves the selected product so metrics remain inspectable
 *   - Unlimited capacity products (total_limit === null or quota_type === "unlimited") remain assignable
 *   - Displays exact empty text: "No entitled products found" when 0 products exist
 * - Step 2: Member Selection
 *   - Loads eligible members for selected product with server-side pagination & search
 *   - Retains selected member object across pagination and search queries
 *   - Preserves request generation counter to prevent race conditions
 * - Step 3: Modules & Confirmation
 *   - Loads entitled modules for the product with retryable error handling
 *   - Preserves user module toggles across Back/Next navigation for the same product
 *   - Submits payload { user_id, product_id, module_ids }
 * - On Success: closes modal, triggers notification, refetches list preserving filters
 * - Field-level API errors: extracts details errors and displays below matching field with aria-describedby and aria-live="polite"
 * - Full accessibility: focus trap, Escape dismissal, trigger restoration, and responsive 320px safety
 */

import React, { useId, useRef, useState, useEffect, useCallback, useMemo } from "react";
import { assignmentsApi } from "../../../api/assignments.ts";
import { ApiError } from "../../../api/client.ts";
import type {
  SelectorMemberItem,
  SelectorModuleItem,
  SelectorProductItem,
} from "../../../api/types.ts";
import {
  AlertCircleIcon,
  ChevronLeftIcon,
  ChevronRightIcon,
  CloseIcon,
  RotateCcwIcon,
  SearchIcon,
  UserIcon,
} from "../../Icons.tsx";
import { useDialogAccessibility } from "../../plans/PlanModalShell.tsx";

interface AssignMemberModalProps {
  readonly isOpen: boolean;
  readonly onClose: () => void;
  readonly onSuccess: () => void;
  readonly onConflict?: () => void;
  readonly triggerRef?: React.RefObject<HTMLElement | null>;
  readonly initialProducts?: readonly SelectorProductItem[];
  readonly initialLoading?: boolean;
}

export const AssignMemberModal: React.FC<AssignMemberModalProps> = ({
  isOpen,
  onClose,
  onSuccess,
  onConflict,
  triggerRef,
  initialProducts,
  initialLoading,
}) => {
  const baseId = useId();
  const productSelectRef = useRef<HTMLSelectElement | null>(null);
  const memberSearchInputRef = useRef<HTMLInputElement | null>(null);
  const submitBtnRef = useRef<HTMLButtonElement | null>(null);
  const initialFocusRef = useRef<HTMLElement | null>(null);

  // Request generation refs to guard against stale async responses
  const productsReqGenRef = useRef(0);
  const membersReqGenRef = useRef(0);
  const modulesReqGenRef = useRef(0);

  // Wizard Step: 1 = Product, 2 = Member, 3 = Modules & Confirm
  const [step, setStep] = useState<1 | 2 | 3>(1);

  // Step 1: Product Selector Data
  const [products, setProducts] = useState<readonly SelectorProductItem[]>(initialProducts ?? []);
  const [selectedProductId, setSelectedProductId] = useState<string>(
    initialProducts && initialProducts.length > 0 ? initialProducts[0].id : ""
  );
  const [isProductsLoading, setIsProductsLoading] = useState<boolean>(
    initialLoading ?? (initialProducts ? false : true)
  );
  const [productsError, setProductsError] = useState<string | null>(null);

  // Step 2: Member Selector Data (paginated)
  const [members, setMembers] = useState<readonly SelectorMemberItem[]>([]);
  const [membersCount, setMembersCount] = useState<number>(0);
  const [memberPage, setMemberPage] = useState<number>(1);
  const memberPageSize = 10;
  const [selectedUserId, setSelectedUserId] = useState<string>("");
  const [selectedUserObj, setSelectedUserObj] = useState<SelectorMemberItem | null>(null);
  const [memberSearchInput, setMemberSearchInput] = useState<string>("");
  const [debouncedMemberSearch, setDebouncedMemberSearch] = useState<string>("");
  const [isMembersLoading, setIsMembersLoading] = useState<boolean>(false);
  const [membersError, setMembersError] = useState<string | null>(null);

  // Step 3: Module Selector Data
  const [modules, setModules] = useState<readonly SelectorModuleItem[]>([]);
  const [loadedModuleProductId, setLoadedModuleProductId] = useState<string | null>(null);
  const [selectedModuleIds, setSelectedModuleIds] = useState<Set<string>>(new Set());
  const [isModulesLoading, setIsModulesLoading] = useState<boolean>(false);
  const [modulesError, setModulesError] = useState<string | null>(null);

  // Submission & Error State
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  const [generalError, setGeneralError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  const { dialogRef } = useDialogAccessibility({
    isOpen,
    isSubmitting,
    onClose,
    triggerRef,
    initialFocusRef,
  });

  // Step 1: Load Entitled Products
  const loadProducts = useCallback(async () => {
    const reqId = ++productsReqGenRef.current;
    setIsProductsLoading(true);
    setProductsError(null);
    try {
      const data = await assignmentsApi.getSelectorProducts();
      if (reqId !== productsReqGenRef.current) return;
      setProducts(data);
      setSelectedProductId((prev) => {
        if (prev && data.some((p) => p.id === prev)) return prev;
        return data[0]?.id || "";
      });
    } catch {
      if (reqId !== productsReqGenRef.current) return;
      setProductsError("Unable to load entitled products. Please retry.");
    } finally {
      if (reqId === productsReqGenRef.current) {
        setIsProductsLoading(false);
      }
    }
  }, []);

  // Step 2: Load Eligible Members with pagination & search
  const loadMembers = useCallback(async (prodId: string, search: string, pageNum: number) => {
    if (!prodId) return;
    const reqId = ++membersReqGenRef.current;
    setIsMembersLoading(true);
    setMembersError(null);
    try {
      const data = await assignmentsApi.getSelectorMembers({
        product_id: prodId,
        search: search || undefined,
        page: pageNum,
        page_size: memberPageSize,
      });
      if (reqId !== membersReqGenRef.current) return;
      setMembers(data.results);
      setMembersCount(data.count);
    } catch {
      if (reqId !== membersReqGenRef.current) return;
      setMembersError("Unable to load eligible organization members. Please retry.");
    } finally {
      if (reqId === membersReqGenRef.current) {
        setIsMembersLoading(false);
      }
    }
  }, [memberPageSize]);

  // Step 3: Load Entitled Modules for selected product
  const loadModules = useCallback(async (prodId: string) => {
    if (!prodId) return;
    const reqId = ++modulesReqGenRef.current;
    setIsModulesLoading(true);
    setModulesError(null);
    try {
      const data = await assignmentsApi.getSelectorModules(prodId);
      if (reqId !== modulesReqGenRef.current) return;
      setModules(data);
      setSelectedModuleIds(new Set(data.map((m) => m.id)));
      setLoadedModuleProductId(prodId);
    } catch {
      if (reqId !== modulesReqGenRef.current) return;
      setModulesError("Unable to load entitled product modules. Please retry.");
    } finally {
      if (reqId === modulesReqGenRef.current) {
        setIsModulesLoading(false);
      }
    }
  }, []);

  // Reset wizard on opening
  useEffect(() => {
    if (isOpen) {
      setStep(1);
      setSelectedProductId(initialProducts && initialProducts.length > 0 ? initialProducts[0].id : "");
      setSelectedUserId("");
      setSelectedUserObj(null);
      setSelectedModuleIds(new Set());
      setLoadedModuleProductId(null);
      setMemberSearchInput("");
      setDebouncedMemberSearch("");
      setMemberPage(1);
      setGeneralError(null);
      setFieldErrors({});
      setIsSubmitting(false);
      if (!initialProducts) {
        void loadProducts();
      }
    } else {
      // Cancel pending async responses
      productsReqGenRef.current += 1;
      membersReqGenRef.current += 1;
      modulesReqGenRef.current += 1;
    }
  }, [isOpen, initialProducts, loadProducts]);

  // Debounce member search input (300ms)
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedMemberSearch(memberSearchInput);
      setMemberPage(1);
    }, 300);
    return () => clearTimeout(timer);
  }, [memberSearchInput]);

  // Trigger member loading on step 2, product, search, or page change
  useEffect(() => {
    if (isOpen && step === 2 && selectedProductId) {
      void loadMembers(selectedProductId, debouncedMemberSearch, memberPage);
    }
  }, [isOpen, step, selectedProductId, debouncedMemberSearch, memberPage, loadMembers]);

  // Focus management across wizard step changes
  useEffect(() => {
    if (!isOpen) return;
    if (step === 1) {
      productSelectRef.current?.focus();
    } else if (step === 2) {
      memberSearchInputRef.current?.focus();
    } else if (step === 3) {
      submitBtnRef.current?.focus();
    }
  }, [isOpen, step]);

  // Selected product object
  const selectedProduct = useMemo(() => {
    return products.find((p) => p.id === selectedProductId) || null;
  }, [products, selectedProductId]);

  // Capacity verification
  const isSelectedProductAtCapacity = useMemo(() => {
    if (!selectedProduct) return false;
    if (selectedProduct.quota_type === "unlimited" || selectedProduct.total_limit === null) {
      return false;
    }
    return !selectedProduct.is_capacity_available || selectedProduct.available_seats === 0;
  }, [selectedProduct]);

  // Product selection change handler
  const handleProductChange = (newProductId: string) => {
    if (newProductId === selectedProductId) return;
    setSelectedProductId(newProductId);
    // Explicitly clear dependent selections, errors, and cached module state
    setSelectedUserId("");
    setSelectedUserObj(null);
    setSelectedModuleIds(new Set());
    setLoadedModuleProductId(null);
    setMemberSearchInput("");
    setDebouncedMemberSearch("");
    setMemberPage(1);
    setMembers([]);
    setMembersCount(0);
    setMembersError(null);
    setModules([]);
    setModulesError(null);
    setFieldErrors({});
    setGeneralError(null);
  };

  // Coherent selected member for confirmation
  const selectedMember = useMemo(() => {
    if (selectedUserObj && selectedUserObj.user_id === selectedUserId) {
      return selectedUserObj;
    }
    return members.find((m) => m.user_id === selectedUserId) || null;
  }, [selectedUserObj, selectedUserId, members]);

  if (!isOpen) return null;

  // Handlers for Step Navigation
  const handleNextFromStep1 = () => {
    if (!selectedProduct || isSelectedProductAtCapacity || isProductsLoading || Boolean(productsError)) return;
    setStep(2);
  };

  const handleNextFromStep2 = () => {
    if (!selectedUserId || isMembersLoading || Boolean(membersError)) return;
    setStep(3);
    // Preserve module choices if navigating back and forth for the same product
    if (loadedModuleProductId !== selectedProductId) {
      void loadModules(selectedProductId);
    }
  };

  const handleBackToStep1 = () => {
    setStep(1);
  };

  const handleBackToStep2 = () => {
    setStep(2);
  };

  // Toggle Module Selection
  const handleToggleModule = (moduleId: string) => {
    setSelectedModuleIds((prev) => {
      const next = new Set(prev);
      if (next.has(moduleId)) {
        next.delete(moduleId);
      } else {
        next.add(moduleId);
      }
      return next;
    });
  };

  // Form Submission (Step 3)
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedProduct || !selectedUserId || isSubmitting || isModulesLoading || Boolean(modulesError)) {
      return;
    }

    setIsSubmitting(true);
    setGeneralError(null);
    setFieldErrors({});

    try {
      await assignmentsApi.createAssignment({
        user_id: selectedUserId,
        product_id: selectedProduct.id,
        module_ids: Array.from(selectedModuleIds),
      });
      onSuccess();
      onClose();
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        if (err.status === 409) {
          if (onConflict) onConflict();
          onClose();
          return;
        }
        const data = err.data as Record<string, unknown> | undefined;
        const errObj = (data?.error && typeof data.error === "object") ? (data.error as Record<string, unknown>) : null;
        const details = (errObj?.details || data?.details) as Record<string, unknown> | undefined;
        if (details && typeof details === "object") {
          const parsed: Record<string, string> = {};
          for (const [k, v] of Object.entries(details)) {
            parsed[k] = Array.isArray(v) ? v.join(" ") : String(v);
          }
          setFieldErrors(parsed);
        }
        setGeneralError(errObj?.message ? String(errObj.message) : err.message);
      } else {
        setGeneralError("An unexpected error occurred while assigning the member.");
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  const totalMemberPages = Math.max(1, Math.ceil(membersCount / memberPageSize));
  const isUnlimitedProduct = selectedProduct?.quota_type === "unlimited" || selectedProduct?.total_limit === null;

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
        aria-describedby={`${baseId}-desc`}
        className="dialog-surface"
        style={{ maxWidth: "620px", width: "100%", margin: "1rem" }}
      >
        <div className="dialog-header">
          <div>
            <h2 id={`${baseId}-title`} className="dialog-title">
              Assign Product Seats
            </h2>
            <p id={`${baseId}-desc`} className="dialog-subtitle">
              {step === 1 && "Step 1 of 3: Select product and verify seat capacity"}
              {step === 2 && "Step 2 of 3: Select eligible organization member"}
              {step === 3 && "Step 3 of 3: Configure enabled modules and confirm"}
            </p>
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

        <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column" }}>
          <div className="dialog-body" style={{ display: "flex", flexDirection: "column", gap: "1rem", maxHeight: "65vh", overflowY: "auto" }}>
            {generalError && (
              <div className="alert-box alert-danger" role="alert">
                <AlertCircleIcon size={16} style={{ flexShrink: 0 }} />
                <span>{generalError}</span>
              </div>
            )}

            {/* Step Indicator Progress Bar */}
            <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
              {[1, 2, 3].map((s) => (
                <div
                  key={s}
                  style={{
                    flex: 1,
                    height: "4px",
                    borderRadius: "2px",
                    background: s <= step ? "var(--brand-primary, #6366f1)" : "var(--border-glass, rgba(255, 255, 255, 0.1))",
                    transition: "background 0.2s ease",
                  }}
                />
              ))}
            </div>

            {/* ---------------- STEP 1: PRODUCT SELECTION ---------------- */}
            {step === 1 && (
              <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
                {productsError && (
                  <div
                    style={{
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "space-between",
                      padding: "0.75rem",
                      background: "rgba(239, 68, 68, 0.1)",
                      border: "1px solid rgba(239, 68, 68, 0.3)",
                      borderRadius: "8px",
                      color: "var(--status-danger, #ef4444)",
                      fontSize: "0.875rem",
                    }}
                  >
                    <span>{productsError}</span>
                    <button
                      type="button"
                      onClick={() => void loadProducts()}
                      className="btn btn-secondary btn-sm"
                    >
                      <RotateCcwIcon size={14} /> Retry
                    </button>
                  </div>
                )}

                {isProductsLoading ? (
                  <div style={{ padding: "3rem", textAlign: "center", color: "var(--text-secondary)" }}>
                    Loading entitled products...
                  </div>
                ) : products.length === 0 ? (
                  <div
                    style={{
                      padding: "2.5rem 1.5rem",
                      textAlign: "center",
                      color: "var(--text-secondary)",
                      background: "var(--glass-surface-elevated)",
                      borderRadius: "12px",
                      border: "1px solid var(--border-glass)",
                    }}
                  >
                    <h3 style={{ margin: "0 0 0.5rem 0", color: "var(--text-primary)", fontSize: "1rem" }}>
                      No entitled products found
                    </h3>
                    <p style={{ margin: 0, fontSize: "0.875rem" }}>
                      Your organization does not currently have any active product entitlements.
                    </p>
                  </div>
                ) : (
                  <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
                    <label htmlFor={`${baseId}-product-select`} style={{ fontSize: "0.875rem", fontWeight: 600 }}>
                      Select Entitled Product
                    </label>
                    <select
                      ref={productSelectRef}
                      id={`${baseId}-product-select`}
                      value={selectedProductId}
                      onChange={(e) => handleProductChange(e.target.value)}
                      aria-invalid={Boolean(fieldErrors.product_id)}
                      aria-describedby={fieldErrors.product_id ? `${baseId}-product-error` : undefined}
                      style={{
                        padding: "0.75rem",
                        borderRadius: "8px",
                        background: "var(--bg-input, rgba(0, 0, 0, 0.2))",
                        border: fieldErrors.product_id
                          ? "1px solid var(--status-danger, #ef4444)"
                          : "1px solid var(--border-glass)",
                        color: "var(--text-primary)",
                        fontSize: "0.875rem",
                      }}
                    >
                      {products.map((p) => {
                        const isUnlim = p.quota_type === "unlimited" || p.total_limit === null;
                        return (
                          <option key={p.id} value={p.id}>
                            {p.name} ({p.code}) — {isUnlim ? "Unlimited" : `${p.consumed_seats}/${p.total_limit} seats`}
                          </option>
                        );
                      })}
                    </select>

                    {/* Selected Product Metric Card */}
                    {selectedProduct && (
                      <div
                        style={{
                          padding: "1rem",
                          borderRadius: "10px",
                          background: "var(--glass-surface-elevated)",
                          border: "1px solid var(--border-glass)",
                          display: "flex",
                          flexDirection: "column",
                          gap: "0.75rem",
                        }}
                      >
                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: "0.5rem" }}>
                          <div>
                            <div style={{ fontWeight: 700, fontSize: "1rem", color: "var(--text-primary)" }}>
                              {selectedProduct.name}
                            </div>
                            <div style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
                              Code: {selectedProduct.code} • Pool: {selectedProduct.pool_scope} • Quota: {selectedProduct.quota_type}
                            </div>
                          </div>

                          {/* Capacity Status Badge */}
                          <span
                            style={{
                              padding: "0.25rem 0.6rem",
                              borderRadius: "9999px",
                              fontSize: "0.6875rem",
                              fontWeight: 700,
                              textTransform: "uppercase",
                              background: isSelectedProductAtCapacity
                                ? "rgba(239, 68, 68, 0.15)"
                                : "rgba(16, 185, 129, 0.15)",
                              color: isSelectedProductAtCapacity
                                ? "var(--status-danger, #ef4444)"
                                : "var(--status-success, #10b981)",
                            }}
                          >
                            {isSelectedProductAtCapacity ? "Full" : "Available"}
                          </span>
                        </div>

                        {/* Metric Tiles */}
                        <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: "0.5rem" }}>
                          <div style={{ padding: "0.5rem", borderRadius: "8px", background: "var(--glass-surface)", textAlign: "center" }}>
                            <div style={{ fontSize: "0.6875rem", color: "var(--text-muted)", textTransform: "uppercase", fontWeight: 600 }}>Total Limit</div>
                            <div style={{ fontSize: "1.125rem", fontWeight: 700, color: "var(--text-primary)", marginTop: "0.2rem" }}>
                              {isUnlimitedProduct ? "Unlimited" : selectedProduct.total_limit}
                            </div>
                          </div>
                          <div style={{ padding: "0.5rem", borderRadius: "8px", background: "var(--glass-surface)", textAlign: "center" }}>
                            <div style={{ fontSize: "0.6875rem", color: "var(--text-muted)", textTransform: "uppercase", fontWeight: 600 }}>Consumed</div>
                            <div style={{ fontSize: "1.125rem", fontWeight: 700, color: "var(--brand-primary, #6366f1)", marginTop: "0.2rem" }}>
                              {selectedProduct.consumed_seats}
                            </div>
                          </div>
                          <div style={{ padding: "0.5rem", borderRadius: "8px", background: "var(--glass-surface)", textAlign: "center" }}>
                            <div style={{ fontSize: "0.6875rem", color: "var(--text-muted)", textTransform: "uppercase", fontWeight: 600 }}>Available</div>
                            <div
                              style={{
                                fontSize: "1.125rem",
                                fontWeight: 700,
                                color: isSelectedProductAtCapacity
                                  ? "var(--status-danger, #ef4444)"
                                  : "var(--status-success, #10b981)",
                                marginTop: "0.2rem",
                              }}
                            >
                              {selectedProduct.available_seats === null ? "Unlimited" : selectedProduct.available_seats}
                            </div>
                          </div>
                        </div>

                        {/* Capacity Warning Banner */}
                        {isSelectedProductAtCapacity && (
                          <div
                            className="alert-box alert-danger"
                            style={{
                              background: "rgba(239, 68, 68, 0.1)",
                              border: "1px solid rgba(239, 68, 68, 0.3)",
                              color: "var(--status-danger, #ef4444)",
                              fontSize: "0.8125rem",
                              padding: "0.75rem",
                              borderRadius: "8px",
                              display: "flex",
                              alignItems: "center",
                              gap: "0.5rem",
                            }}
                          >
                            <AlertCircleIcon size={16} style={{ flexShrink: 0 }} />
                            <span>
                              This product has reached its total seat allocation limit. No additional members can be assigned until existing assignments are revoked or seat limits are increased.
                            </span>
                          </div>
                        )}
                      </div>
                    )}

                    {/* Field Level Error */}
                    {fieldErrors.product_id && (
                      <div
                        id={`${baseId}-product-error`}
                        aria-live="polite"
                        style={{ fontSize: "0.75rem", color: "var(--status-danger, #ef4444)", fontWeight: 500 }}
                      >
                        {fieldErrors.product_id}
                      </div>
                    )}
                  </div>
                )}
              </div>
            )}

            {/* ---------------- STEP 2: MEMBER SELECTION ---------------- */}
            {step === 2 && (
              <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
                <div style={{ position: "relative", width: "100%" }}>
                  <SearchIcon
                    size={16}
                    style={{ position: "absolute", left: "10px", top: "50%", transform: "translateY(-50%)", color: "var(--text-muted)" }}
                  />
                  <input
                    ref={memberSearchInputRef}
                    type="text"
                    placeholder="Search eligible members by name or email..."
                    value={memberSearchInput}
                    onChange={(e) => setMemberSearchInput(e.target.value)}
                    style={{
                      width: "100%",
                      padding: "0.625rem 0.75rem 0.625rem 2.25rem",
                      borderRadius: "8px",
                      background: "var(--bg-input, rgba(0, 0, 0, 0.2))",
                      border: "1px solid var(--border-glass)",
                      color: "var(--text-primary)",
                      fontSize: "0.875rem",
                      boxSizing: "border-box",
                    }}
                  />
                </div>

                {membersError && (
                  <div
                    style={{
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "space-between",
                      padding: "0.75rem",
                      background: "rgba(239, 68, 68, 0.1)",
                      border: "1px solid rgba(239, 68, 68, 0.3)",
                      borderRadius: "8px",
                      color: "var(--status-danger, #ef4444)",
                      fontSize: "0.875rem",
                    }}
                  >
                    <span>{membersError}</span>
                    <button
                      type="button"
                      onClick={() => selectedProduct && void loadMembers(selectedProduct.id, debouncedMemberSearch, memberPage)}
                      className="btn btn-secondary btn-sm"
                    >
                      <RotateCcwIcon size={14} /> Retry
                    </button>
                  </div>
                )}

                {isMembersLoading ? (
                  <div style={{ padding: "3rem", textAlign: "center", color: "var(--text-secondary)" }}>
                    Loading eligible members...
                  </div>
                ) : members.length === 0 ? (
                  <div
                    style={{
                      padding: "2rem 1.5rem",
                      textAlign: "center",
                      color: "var(--text-secondary)",
                      background: "var(--glass-surface-elevated)",
                      borderRadius: "12px",
                      border: "1px solid var(--border-glass)",
                    }}
                  >
                    <UserIcon size={32} style={{ color: "var(--text-muted)", marginBottom: "0.5rem" }} />
                    <p style={{ margin: 0, fontSize: "0.875rem" }}>
                      {debouncedMemberSearch.trim()
                        ? "No members match your search criteria."
                        : "No eligible organization members available for this product."}
                    </p>
                  </div>
                ) : (
                  <div
                    style={{
                      display: "flex",
                      flexDirection: "column",
                      gap: "0.5rem",
                      maxHeight: "280px",
                      overflowY: "auto",
                    }}
                  >
                    {members.map((m) => {
                      const isSelected = selectedUserId === m.user_id;
                      const radioId = `${baseId}-mem-${m.user_id}`;
                      return (
                        <label
                          key={m.membership_id}
                          htmlFor={radioId}
                          style={{
                            display: "flex",
                            alignItems: "center",
                            justifyContent: "space-between",
                            padding: "0.75rem 1rem",
                            borderRadius: "8px",
                            background: isSelected
                              ? "var(--brand-primary-light, rgba(99, 102, 241, 0.1))"
                              : "var(--glass-surface)",
                            border: isSelected
                              ? "1px solid var(--brand-primary)"
                              : "1px solid var(--border-glass)",
                            cursor: "pointer",
                            transition: "all 0.15s ease",
                          }}
                        >
                          <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
                            <input
                              id={radioId}
                              type="radio"
                              name="selected_member"
                              checked={isSelected}
                              onChange={() => {
                                setSelectedUserId(m.user_id);
                                setSelectedUserObj(m);
                                setFieldErrors((prev) => ({ ...prev, user_id: "" }));
                              }}
                              style={{ cursor: "pointer" }}
                            />
                            <div style={{ display: "flex", flexDirection: "column" }}>
                              <span style={{ fontSize: "0.875rem", fontWeight: 600, color: "var(--text-primary)", wordBreak: "break-word" }}>
                                {m.full_name}
                              </span>
                              <span style={{ fontSize: "0.75rem", color: "var(--text-muted)", wordBreak: "break-all" }}>
                                {m.email}
                              </span>
                            </div>
                          </div>
                          <span
                            style={{
                              fontSize: "0.6875rem",
                              fontWeight: 600,
                              padding: "0.2rem 0.5rem",
                              borderRadius: "6px",
                              background: "var(--glass-surface-elevated)",
                              color: "var(--text-secondary)",
                              textTransform: "uppercase",
                            }}
                          >
                            {m.role_code}
                          </span>
                        </label>
                      );
                    })}
                  </div>
                )}

                {/* Member Pagination Bar */}
                {membersCount > memberPageSize && (
                  <div
                    style={{
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "space-between",
                      fontSize: "0.8125rem",
                      paddingTop: "0.5rem",
                      borderTop: "1px solid var(--border-glass)",
                    }}
                  >
                    <span style={{ color: "var(--text-muted)" }}>
                      Page {memberPage} of {totalMemberPages} ({membersCount} members)
                    </span>
                    <div style={{ display: "flex", gap: "0.5rem" }}>
                      <button
                        type="button"
                        className="btn btn-secondary btn-sm"
                        disabled={memberPage <= 1 || isMembersLoading}
                        onClick={() => setMemberPage((p) => Math.max(1, p - 1))}
                      >
                        Previous
                      </button>
                      <button
                        type="button"
                        className="btn btn-secondary btn-sm"
                        disabled={memberPage >= totalMemberPages || isMembersLoading}
                        onClick={() => setMemberPage((p) => Math.min(totalMemberPages, p + 1))}
                      >
                        Next
                      </button>
                    </div>
                  </div>
                )}

                {/* Field Level Error */}
                {fieldErrors.user_id && (
                  <div
                    id={`${baseId}-user-error`}
                    aria-live="polite"
                    style={{ fontSize: "0.75rem", color: "var(--status-danger, #ef4444)", fontWeight: 500 }}
                  >
                    {fieldErrors.user_id}
                  </div>
                )}
              </div>
            )}

            {/* ---------------- STEP 3: MODULE SELECTION & CONFIRMATION ---------------- */}
            {step === 3 && (
              <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
                {/* Summary Card */}
                <div
                  style={{
                    padding: "0.875rem 1rem",
                    borderRadius: "10px",
                    background: "var(--glass-surface-elevated)",
                    border: "1px solid var(--border-glass)",
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    flexWrap: "wrap",
                    gap: "0.5rem",
                  }}
                >
                  <div>
                    <span style={{ fontSize: "0.75rem", color: "var(--text-muted)", textTransform: "uppercase", fontWeight: 600 }}>Member</span>
                    <div style={{ fontSize: "0.875rem", fontWeight: 700, color: "var(--text-primary)", wordBreak: "break-word" }}>
                      {selectedMember?.full_name} ({selectedMember?.email})
                    </div>
                  </div>
                  <div>
                    <span style={{ fontSize: "0.75rem", color: "var(--text-muted)", textTransform: "uppercase", fontWeight: 600 }}>Product</span>
                    <div style={{ fontSize: "0.875rem", fontWeight: 700, color: "var(--brand-primary, #6366f1)" }}>
                      {selectedProduct?.name}
                    </div>
                  </div>
                </div>

                {modulesError && (
                  <div
                    style={{
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "space-between",
                      padding: "0.75rem",
                      background: "rgba(239, 68, 68, 0.1)",
                      border: "1px solid rgba(239, 68, 68, 0.3)",
                      borderRadius: "8px",
                      color: "var(--status-danger, #ef4444)",
                      fontSize: "0.875rem",
                    }}
                  >
                    <span>{modulesError}</span>
                    <button
                      type="button"
                      onClick={() => selectedProduct && void loadModules(selectedProduct.id)}
                      className="btn btn-secondary btn-sm"
                    >
                      <RotateCcwIcon size={14} /> Retry
                    </button>
                  </div>
                )}

                {isModulesLoading ? (
                  <div style={{ padding: "3rem", textAlign: "center", color: "var(--text-secondary)" }}>
                    Loading entitled modules...
                  </div>
                ) : !modulesError && modules.length === 0 ? (
                  <div
                    style={{
                      padding: "2rem 1.5rem",
                      textAlign: "center",
                      color: "var(--text-secondary)",
                      background: "var(--glass-surface-elevated)",
                      borderRadius: "10px",
                      border: "1px solid var(--border-glass)",
                    }}
                  >
                    No entitled modules found for this product.
                  </div>
                ) : !modulesError && (
                  <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                      <span style={{ fontSize: "0.875rem", fontWeight: 600 }}>
                        Entitled Modules ({selectedModuleIds.size} of {modules.length} selected)
                      </span>
                      <div style={{ display: "flex", gap: "0.5rem" }}>
                        <button
                          type="button"
                          onClick={() => setSelectedModuleIds(new Set(modules.map((m) => m.id)))}
                          className="btn btn-secondary btn-sm"
                          disabled={isSubmitting}
                        >
                          Select All
                        </button>
                        <button
                          type="button"
                          onClick={() => setSelectedModuleIds(new Set())}
                          className="btn btn-secondary btn-sm"
                          disabled={isSubmitting}
                        >
                          Deselect All
                        </button>
                      </div>
                    </div>

                    <div
                      style={{
                        display: "flex",
                        flexDirection: "column",
                        gap: "0.5rem",
                        maxHeight: "260px",
                        overflowY: "auto",
                      }}
                    >
                      {modules.map((mod) => {
                        const isChecked = selectedModuleIds.has(mod.id);
                        const checkboxId = `${baseId}-mod-${mod.id}`;
                        return (
                          <label
                            key={mod.id}
                            htmlFor={checkboxId}
                            style={{
                              display: "flex",
                              alignItems: "flex-start",
                              gap: "0.75rem",
                              padding: "0.75rem",
                              borderRadius: "8px",
                              background: isChecked
                                ? "var(--brand-primary-light, rgba(99, 102, 241, 0.08))"
                                : "var(--glass-surface)",
                              border: isChecked
                                ? "1px solid var(--brand-primary, #6366f1)"
                                : "1px solid var(--border-glass)",
                              cursor: "pointer",
                            }}
                          >
                            <input
                              id={checkboxId}
                              type="checkbox"
                              checked={isChecked}
                              onChange={() => handleToggleModule(mod.id)}
                              disabled={isSubmitting}
                              style={{ marginTop: "0.2rem", cursor: "pointer" }}
                            />
                            <div style={{ display: "flex", flexDirection: "column" }}>
                              <span style={{ fontSize: "0.875rem", fontWeight: 600, color: "var(--text-primary)" }}>
                                {mod.name}
                              </span>
                              {mod.description && (
                                <span style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
                                  {mod.description}
                                </span>
                              )}
                            </div>
                          </label>
                        );
                      })}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>

          <div
            className="dialog-footer"
            style={{
              padding: "1rem 1.5rem",
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
            }}
          >
            {step === 1 && (
              <>
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={onClose}
                  disabled={isSubmitting}
                >
                  Cancel
                </button>
                <button
                  type="button"
                  className="btn btn-primary"
                  onClick={handleNextFromStep1}
                  disabled={
                    !selectedProduct ||
                    isSelectedProductAtCapacity ||
                    isProductsLoading ||
                    Boolean(productsError)
                  }
                >
                  Next: Select Member <ChevronRightIcon size={16} />
                </button>
              </>
            )}

            {step === 2 && (
              <>
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={handleBackToStep1}
                  disabled={isSubmitting}
                >
                  <ChevronLeftIcon size={16} /> Back to Products
                </button>
                <button
                  type="button"
                  className="btn btn-primary"
                  onClick={handleNextFromStep2}
                  disabled={!selectedUserId || isMembersLoading || Boolean(membersError)}
                >
                  Next: Modules <ChevronRightIcon size={16} />
                </button>
              </>
            )}

            {step === 3 && (
              <>
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={handleBackToStep2}
                  disabled={isSubmitting}
                >
                  <ChevronLeftIcon size={16} /> Back to Member
                </button>
                <button
                  ref={submitBtnRef}
                  type="submit"
                  className="btn btn-primary"
                  disabled={
                    isSubmitting ||
                    isModulesLoading ||
                    Boolean(modulesError) ||
                    !selectedUserId ||
                    !selectedProduct
                  }
                >
                  {isSubmitting ? "Assigning..." : "Confirm & Assign Seat"}
                </button>
              </>
            )}
          </div>
        </form>
      </div>
    </div>
  );
};
