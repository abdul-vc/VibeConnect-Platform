/**
 * Tenant Product Assignments Workspace (Phase 2F Part E).
 *
 * Implements authoritative tenant assignment management:
 * - Seat allocation summary cards with capacity progress indicator
 * - 300ms debounced server-side search by member name/email
 * - Product, status, and page-size filters with automatic page-reset to 1
 * - Desktop table with responsive card transformation below 768px (320px safe)
 * - Permission-based UI: view-only users see read-only information with all mutation actions hidden;
 *   manage users see Assign Member, Edit Modules, and status-valid lifecycle actions
 * - Full modal integration: AssignMemberModal, SuspendModal, ReactivateModal, RevokeModal, EditModulesModal
 * - HTTP 409 stale conflict handling: displays notification and refetches while preserving all active filters
 * - Handles loading skeleton, informative empty, retryable error, and 403 forbidden states
 */

import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { assignmentsApi } from "../../api/assignments.ts";
import { ApiError } from "../../api/client.ts";
import type {
  SelectorProductItem,
  UserProductAssignmentItem,
} from "../../api/types.ts";
import { AppShell } from "../../components/AppShell.tsx";
import {
  AlertCircleIcon,
  CheckCircleIcon,
  ChevronLeftIcon,
  ChevronRightIcon,
  LayersIcon,
  PlusIcon,
  RotateCcwIcon,
  SearchIcon,
  ShieldCheckIcon,
  UserIcon,
} from "../../components/Icons.tsx";
import { formatDateTime } from "../../config/dateUtils.ts";
import { useAuth } from "../../context/AuthContext.tsx";
import { AssignMemberModal } from "../../components/tenant/assignments/AssignMemberModal.tsx";
import { EditModulesModal } from "../../components/tenant/assignments/EditModulesModal.tsx";
import { ReactivateModal } from "../../components/tenant/assignments/ReactivateModal.tsx";
import { RevokeModal } from "../../components/tenant/assignments/RevokeModal.tsx";
import { SuspendModal } from "../../components/tenant/assignments/SuspendModal.tsx";

export const TenantAssignmentsPage: React.FC = () => {
  const { user } = useAuth();

  const effectivePermissions = useMemo(() => {
    return new Set(user?.active_context?.effective_permissions ?? []);
  }, [user?.active_context?.effective_permissions]);

  const canView = effectivePermissions.has("assignments.view");
  const canManage = effectivePermissions.has("assignments.manage");

  // Summary Products State
  const [selectorProducts, setSelectorProducts] = useState<readonly SelectorProductItem[]>([]);

  // List State
  const [assignments, setAssignments] = useState<readonly UserProductAssignmentItem[]>([]);
  const [totalCount, setTotalCount] = useState<number>(0);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [isForbidden, setIsForbidden] = useState<boolean>(!canView);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [notification, setNotification] = useState<{ type: "success" | "warning"; message: string } | null>(null);

  // Filter & Search State
  const [searchInput, setSearchInput] = useState<string>("");
  const [debouncedSearch, setDebouncedSearch] = useState<string>("");
  const [productFilter, setProductFilter] = useState<string>("");
  const [statusFilter, setStatusFilter] = useState<string>("");
  const [page, setPage] = useState<number>(1);
  const [pageSize, setPageSize] = useState<number>(20);

  // Selector Products State (Manager Only)
  const [isProductsLoading, setIsProductsLoading] = useState<boolean>(false);
  const [productsError, setProductsError] = useState<string | null>(null);

  // Modal States
  const [isAssignOpen, setIsAssignOpen] = useState<boolean>(false);
  const [isSuspendOpen, setIsSuspendOpen] = useState<boolean>(false);
  const [isReactivateOpen, setIsReactivateOpen] = useState<boolean>(false);
  const [isRevokeOpen, setIsRevokeOpen] = useState<boolean>(false);
  const [isEditModulesOpen, setIsEditModulesOpen] = useState<boolean>(false);
  const [activeAssignment, setActiveAssignment] = useState<UserProductAssignmentItem | null>(null);

  const triggerRef = useRef<HTMLElement | null>(null);
  const assignmentsReqGenRef = useRef(0);

  // Tenant context change detection
  const currentTenantId = user?.active_context?.organization?.id;
  const lastTenantIdRef = useRef<string | undefined>(currentTenantId);

  useEffect(() => {
    if (lastTenantIdRef.current !== currentTenantId) {
      lastTenantIdRef.current = currentTenantId;
      assignmentsReqGenRef.current += 1;
      setPage(1);
      setSearchInput("");
      setDebouncedSearch("");
      setProductFilter("");
      setStatusFilter("");
      setAssignments([]);
      setTotalCount(0);
      setErrorMessage(null);
      setNotification(null);
    }
  }, [currentTenantId]);

  // 300ms Debounce on Search Input
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearch(searchInput);
      setPage(1);
    }, 300);
    return () => clearTimeout(timer);
  }, [searchInput]);

  // Load Entitled Products for Summary Cards & Product Filter (Manager Only)
  const fetchProducts = useCallback(async () => {
    if (!canManage) {
      setSelectorProducts([]);
      setProductsError(null);
      return;
    }
    setIsProductsLoading(true);
    setProductsError(null);
    try {
      const prods = await assignmentsApi.getSelectorProducts();
      setSelectorProducts(prods);
    } catch (err: unknown) {
      if (err instanceof ApiError && err.status === 403) {
        setSelectorProducts([]);
      } else {
        setProductsError("Unable to load product capacity overview.");
      }
    } finally {
      setIsProductsLoading(false);
    }
  }, [canManage]);

  // Load Assignments List
  const fetchAssignments = useCallback(async () => {
    if (!canView) {
      setIsForbidden(true);
      setIsLoading(false);
      return;
    }

    const reqId = ++assignmentsReqGenRef.current;
    setIsLoading(true);
    setErrorMessage(null);
    setIsForbidden(false);

    try {
      const res = await assignmentsApi.listAssignments({
        page,
        page_size: pageSize,
        search: debouncedSearch || undefined,
        product_id: productFilter || undefined,
        status: statusFilter || undefined,
      });
      if (reqId !== assignmentsReqGenRef.current) return;
      setAssignments(res.results);
      setTotalCount(res.count);
      const newTotalPages = Math.max(1, Math.ceil(res.count / pageSize));
      if (page > newTotalPages && res.count > 0) {
        setPage(newTotalPages);
      }
    } catch (err: unknown) {
      if (reqId !== assignmentsReqGenRef.current) return;
      if (err instanceof ApiError) {
        if (err.status === 403) {
          setIsForbidden(true);
        } else {
          const d = err.data as { detail?: string; message?: string } | undefined;
          setErrorMessage(d?.detail || d?.message || err.message || "Failed to load product assignments.");
        }
      } else {
        setErrorMessage("An unexpected error occurred while loading assignments.");
      }
    } finally {
      if (reqId === assignmentsReqGenRef.current) {
        setIsLoading(false);
      }
    }
  }, [canView, page, pageSize, debouncedSearch, productFilter, statusFilter]);

  useEffect(() => {
    void fetchProducts();
  }, [fetchProducts]);

  useEffect(() => {
    void fetchAssignments();
  }, [fetchAssignments]);

  // Handlers for Filter Changes (resets page to 1)
  const handleProductFilterChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    setProductFilter(e.target.value);
    setPage(1);
  };

  const handleStatusFilterChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    setStatusFilter(e.target.value);
    setPage(1);
  };

  const handlePageSizeChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    setPageSize(Number(e.target.value));
    setPage(1);
  };

  // Handlers for Actions
  const handleOpenAssign = (e: React.MouseEvent<HTMLElement>) => {
    triggerRef.current = e.currentTarget;
    setIsAssignOpen(true);
  };

  const handleOpenSuspend = (item: UserProductAssignmentItem, e: React.MouseEvent<HTMLElement>) => {
    triggerRef.current = e.currentTarget;
    setActiveAssignment(item);
    setIsSuspendOpen(true);
  };

  const handleOpenReactivate = (item: UserProductAssignmentItem, e: React.MouseEvent<HTMLElement>) => {
    triggerRef.current = e.currentTarget;
    setActiveAssignment(item);
    setIsReactivateOpen(true);
  };

  const handleOpenRevoke = (item: UserProductAssignmentItem, e: React.MouseEvent<HTMLElement>) => {
    triggerRef.current = e.currentTarget;
    setActiveAssignment(item);
    setIsRevokeOpen(true);
  };

  const handleOpenEditModules = (item: UserProductAssignmentItem, e: React.MouseEvent<HTMLElement>) => {
    triggerRef.current = e.currentTarget;
    setActiveAssignment(item);
    setIsEditModulesOpen(true);
  };

  // Mutation Success / Conflict Handlers (preserving active filters)
  const handleMutationSuccess = (msg: string) => {
    setNotification({ type: "success", message: msg });
    void fetchAssignments();
    void fetchProducts();
  };

  const handleConflict = () => {
    setNotification({
      type: "warning",
      message: "The assignment was modified by another transaction. Assignment data has been refreshed.",
    });
    void fetchAssignments();
    void fetchProducts();
  };

  const totalPages = Math.max(1, Math.ceil(totalCount / pageSize));

  // Render Access Denied View when 403 or lacking view permission
  if (isForbidden || !canView) {
    return (
      <AppShell>
        <div
          style={{
            padding: "4rem 2rem",
            textAlign: "center",
            background: "var(--glass-surface-elevated)",
            borderRadius: "14px",
            border: "1px solid var(--border-glass)",
            maxWidth: "600px",
            margin: "2rem auto",
          }}
        >
          <ShieldCheckIcon size={48} style={{ color: "var(--status-danger, #ef4444)", marginBottom: "1rem" }} />
          <h2 style={{ margin: "0 0 0.5rem 0", color: "var(--text-primary)" }}>Access Denied</h2>
          <p style={{ color: "var(--text-secondary)", fontSize: "0.875rem", lineHeight: 1.5 }}>
            You do not have permission to view product assignments for this organization. Contact your administrator if you require access.
          </p>
        </div>
      </AppShell>
    );
  }

  return (
    <AppShell>
      <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem", minWidth: 0 }}>
        {/* Header Card */}
        <div
          style={{
            background: "var(--glass-surface-elevated)",
            border: "1px solid var(--border-glass)",
            borderRadius: "14px",
            padding: "1.5rem",
            boxShadow: "var(--shadow-sm)",
            display: "flex",
            justifyContent: "space-between",
            alignItems: "flex-start",
            flexWrap: "wrap",
            gap: "1rem",
          }}
        >
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.35rem" }}>
              <LayersIcon size={22} style={{ color: "var(--brand-primary)" }} />
              <h1 style={{ margin: 0, fontSize: "1.375rem", fontWeight: 700, color: "var(--text-primary)" }}>
                Product Assignments
              </h1>
            </div>
            <p style={{ margin: 0, fontSize: "0.875rem", color: "var(--text-secondary)", maxWidth: "680px" }}>
              Allocate product seats and module entitlements to organization members. Monitor real-time seat consumption and manage individual member access lifecycles.
            </p>
          </div>

          {canManage && (
            <button
              type="button"
              className="btn btn-primary"
              onClick={handleOpenAssign}
              style={{ display: "inline-flex", alignItems: "center", gap: "0.5rem", flexShrink: 0 }}
            >
              <PlusIcon size={16} />
              <span>Assign Member</span>
            </button>
          )}
        </div>

        {/* Global Notification Banner */}
        {notification && (
          <div
            className={`alert-box ${notification.type === "success" ? "alert-success" : "alert-warning"}`}
            style={{
              padding: "0.875rem 1.25rem",
              borderRadius: "10px",
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              gap: "0.75rem",
              background: notification.type === "success" ? "rgba(16, 185, 129, 0.15)" : "rgba(245, 158, 11, 0.15)",
              border: notification.type === "success" ? "1px solid rgba(16, 185, 129, 0.3)" : "1px solid rgba(245, 158, 11, 0.3)",
              color: notification.type === "success" ? "var(--status-success, #10b981)" : "var(--status-warning, #f59e0b)",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", fontSize: "0.875rem" }}>
              {notification.type === "success" ? <CheckCircleIcon size={18} /> : <AlertCircleIcon size={18} />}
              <span>{notification.message}</span>
            </div>
            <button
              type="button"
              onClick={() => setNotification(null)}
              className="btn-ghost"
              style={{ padding: "0.25rem", minHeight: "auto", color: "inherit" }}
              aria-label="Dismiss notification"
            >
              ✕
            </button>
          </div>
        )}

        {/* Seat Allocation Summary Section (Manager Only) */}
        {canManage && (selectorProducts.length > 0 || productsError || isProductsLoading) && (
          <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
            <h2 style={{ fontSize: "0.9375rem", fontWeight: 700, margin: 0, color: "var(--text-primary)" }}>
              Seat Allocation Overview
            </h2>
            {isProductsLoading && selectorProducts.length === 0 ? (
              <div style={{ padding: "1.5rem", textAlign: "center", color: "var(--text-secondary)" }}>
                Loading seat allocation overview...
              </div>
            ) : productsError ? (
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  padding: "0.75rem 1rem",
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
                  onClick={() => void fetchProducts()}
                  className="btn btn-secondary btn-sm"
                >
                  <RotateCcwIcon size={14} /> Retry Overview
                </button>
              </div>
            ) : (
              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))",
                  gap: "1rem",
                }}
              >
                {selectorProducts.map((p) => {
                  const isUnlimited = p.quota_type === "unlimited" || p.total_limit === null;
                  const percentage = isUnlimited || !p.total_limit || p.total_limit <= 0
                    ? 0
                    : Math.min(100, Math.round((p.consumed_seats / p.total_limit) * 100));

                  // Color Tokens: normal < 80%, warning 80% to <100%, danger at 100%
                  let progressColor = "var(--brand-primary, #6366f1)";
                  if (!isUnlimited) {
                    if (percentage >= 100) {
                      progressColor = "var(--status-danger, #ef4444)";
                    } else if (percentage >= 80) {
                      progressColor = "var(--status-warning, #f59e0b)";
                    }
                  }

                  return (
                    <div
                      key={p.id}
                      style={{
                        background: "var(--glass-surface-elevated)",
                        border: "1px solid var(--border-glass)",
                        borderRadius: "12px",
                        padding: "1.25rem",
                        boxShadow: "var(--shadow-sm)",
                        display: "flex",
                        flexDirection: "column",
                        gap: "0.75rem",
                      }}
                    >
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: "0.5rem" }}>
                        <div>
                          <div style={{ fontWeight: 700, fontSize: "0.9375rem", color: "var(--text-primary)" }}>
                            {p.name}
                          </div>
                          <div style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
                            {p.code} • Pool: {p.pool_scope} • Quota: {p.quota_type}
                          </div>
                        </div>
                        <span
                          style={{
                            fontSize: "0.6875rem",
                            fontWeight: 700,
                            padding: "0.2rem 0.5rem",
                            borderRadius: "9999px",
                            textTransform: "uppercase",
                            background: p.is_capacity_available
                              ? "rgba(16, 185, 129, 0.15)"
                              : "rgba(239, 68, 68, 0.15)",
                            color: p.is_capacity_available
                              ? "var(--status-success, #10b981)"
                              : "var(--status-danger, #ef4444)",
                          }}
                        >
                          {p.is_capacity_available ? "Available" : "Full"}
                        </span>
                      </div>

                      <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.8125rem" }}>
                        <span style={{ color: "var(--text-secondary)" }}>
                          Consumed: <strong>{p.consumed_seats}</strong>
                        </span>
                        <span style={{ color: "var(--text-secondary)" }}>
                          Limit: <strong>{isUnlimited ? "Unlimited" : p.total_limit}</strong>
                        </span>
                      </div>

                      {/* Progress representation */}
                      <div
                        role="progressbar"
                        aria-valuenow={isUnlimited ? undefined : p.consumed_seats}
                        aria-valuemin={0}
                        aria-valuemax={isUnlimited ? undefined : p.total_limit!}
                        aria-label={`${p.name} seat consumption`}
                        style={{
                          height: "6px",
                          borderRadius: "9999px",
                          background: "var(--border-subtle, rgba(255, 255, 255, 0.1))",
                          overflow: "hidden",
                        }}
                      >
                        <div
                          style={{
                            height: "100%",
                            width: isUnlimited ? "100%" : `${percentage}%`,
                            background: isUnlimited ? "var(--brand-primary)" : progressColor,
                            borderRadius: "9999px",
                            transition: "width 0.3s ease",
                          }}
                        />
                      </div>

                      <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", textAlign: "right" }}>
                        {isUnlimited
                          ? "Unlimited capacity"
                          : `${p.available_seats === null ? "Unlimited" : p.available_seats} seats remaining (${percentage}% used)`}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        )}

        {/* Filter & Search Bar */}
        <div
          style={{
            background: "var(--glass-surface-elevated)",
            border: "1px solid var(--border-glass)",
            borderRadius: "12px",
            padding: "1rem",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            flexWrap: "wrap",
            gap: "0.75rem",
          }}
        >
          {/* Search Input */}
          <div style={{ position: "relative", minWidth: "220px", flex: "1 1 280px" }}>
            <SearchIcon
              size={16}
              style={{ position: "absolute", left: "10px", top: "50%", transform: "translateY(-50%)", color: "var(--text-muted)" }}
            />
            <input
              type="text"
              placeholder="Search by member name or email..."
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              style={{
                width: "100%",
                padding: "0.55rem 0.75rem 0.55rem 2.25rem",
                borderRadius: "8px",
                background: "var(--bg-input, rgba(0, 0, 0, 0.2))",
                border: "1px solid var(--border-glass)",
                color: "var(--text-primary)",
                fontSize: "0.875rem",
                boxSizing: "border-box",
              }}
            />
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", flexWrap: "wrap" }}>
            {/* Product Filter (Manager Only) */}
            {canManage && selectorProducts.length > 0 && (
              <div style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
                <label htmlFor="filter-product" style={{ fontSize: "0.8125rem", color: "var(--text-muted)" }}>
                  Product:
                </label>
                <select
                  id="filter-product"
                  value={productFilter}
                  onChange={handleProductFilterChange}
                  style={{
                    padding: "0.45rem 0.75rem",
                    borderRadius: "8px",
                    background: "var(--bg-input, rgba(0, 0, 0, 0.2))",
                    border: "1px solid var(--border-glass)",
                    color: "var(--text-primary)",
                    fontSize: "0.8125rem",
                  }}
                >
                  <option value="">All Products</option>
                  {selectorProducts.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.name}
                    </option>
                  ))}
                </select>
              </div>
            )}

            {/* Status Filter */}
            <div style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
              <label htmlFor="filter-status" style={{ fontSize: "0.8125rem", color: "var(--text-muted)" }}>
                Status:
              </label>
              <select
                id="filter-status"
                value={statusFilter}
                onChange={handleStatusFilterChange}
                style={{
                  padding: "0.45rem 0.75rem",
                  borderRadius: "8px",
                  background: "var(--bg-input, rgba(0, 0, 0, 0.2))",
                  border: "1px solid var(--border-glass)",
                  color: "var(--text-primary)",
                  fontSize: "0.8125rem",
                }}
              >
                <option value="">All</option>
                <option value="active">Active</option>
                <option value="suspended">Suspended</option>
                <option value="revoked">Revoked</option>
              </select>
            </div>

            {/* Page Size Selector */}
            <div style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
              <label htmlFor="filter-pagesize" style={{ fontSize: "0.8125rem", color: "var(--text-muted)" }}>
                Rows:
              </label>
              <select
                id="filter-pagesize"
                value={pageSize}
                onChange={handlePageSizeChange}
                style={{
                  padding: "0.45rem 0.75rem",
                  borderRadius: "8px",
                  background: "var(--bg-input, rgba(0, 0, 0, 0.2))",
                  border: "1px solid var(--border-glass)",
                  color: "var(--text-primary)",
                  fontSize: "0.8125rem",
                }}
              >
                <option value={10}>10</option>
                <option value={20}>20</option>
                <option value={50}>50</option>
                <option value={100}>100</option>
              </select>
            </div>
          </div>
        </div>

        {/* API Error Banner with Retry */}
        {errorMessage && (
          <div
            style={{
              padding: "1rem",
              borderRadius: "10px",
              background: "rgba(239, 68, 68, 0.12)",
              border: "1px solid rgba(239, 68, 68, 0.3)",
              color: "var(--status-danger, #ef4444)",
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              fontSize: "0.875rem",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
              <AlertCircleIcon size={18} />
              <span>{errorMessage}</span>
            </div>
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              onClick={fetchAssignments}
              style={{ display: "inline-flex", alignItems: "center", gap: "0.3rem" }}
            >
              <RotateCcwIcon size={14} />
              <span>Retry</span>
            </button>
          </div>
        )}

        {/* Loading State Skeleton */}
        {isLoading ? (
          <div
            style={{
              padding: "3.5rem 1.5rem",
              textAlign: "center",
              color: "var(--text-secondary)",
              background: "var(--glass-surface-elevated)",
              borderRadius: "12px",
              border: "1px solid var(--border-glass)",
            }}
          >
            Loading product assignments...
          </div>
        ) : assignments.length === 0 ? (
          /* Empty State */
          <div
            style={{
              padding: "3.5rem 1.5rem",
              textAlign: "center",
              color: "var(--text-secondary)",
              background: "var(--glass-surface-elevated)",
              borderRadius: "12px",
              border: "1px solid var(--border-glass)",
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              gap: "0.75rem",
            }}
          >
            <UserIcon size={36} style={{ color: "var(--text-muted)" }} />
            <h3 style={{ margin: 0, color: "var(--text-primary)", fontSize: "1rem" }}>
              No Product Assignments Found
            </h3>
            <p style={{ margin: 0, fontSize: "0.875rem", maxWidth: "460px" }}>
              No member product assignments match your current search or filter criteria.
            </p>
            {canManage && (
              <button
                type="button"
                className="btn btn-primary btn-sm"
                onClick={handleOpenAssign}
                style={{ marginTop: "0.5rem" }}
              >
                Assign Member Now
              </button>
            )}
          </div>
        ) : (
          <>
            {/* Desktop Table View (>= 768px) */}
            <div className="desktop-table-container">
              <table
                className="data-table"
                style={{
                  width: "100%",
                  borderCollapse: "separate",
                  borderSpacing: 0,
                  background: "var(--glass-surface-elevated)",
                  borderRadius: "12px",
                  border: "1px solid var(--border-glass)",
                  overflow: "hidden",
                }}
              >
                <thead>
                  <tr style={{ background: "var(--glass-surface-sunken)", textAlign: "left" }}>
                    <th style={{ padding: "0.85rem 1rem", fontSize: "0.75rem", fontWeight: 700, color: "var(--text-secondary)", textTransform: "uppercase" }}>
                      Member
                    </th>
                    <th style={{ padding: "0.85rem 1rem", fontSize: "0.75rem", fontWeight: 700, color: "var(--text-secondary)", textTransform: "uppercase" }}>
                      Product
                    </th>
                    <th style={{ padding: "0.85rem 1rem", fontSize: "0.75rem", fontWeight: 700, color: "var(--text-secondary)", textTransform: "uppercase" }}>
                      Enabled Modules
                    </th>
                    <th style={{ padding: "0.85rem 1rem", fontSize: "0.75rem", fontWeight: 700, color: "var(--text-secondary)", textTransform: "uppercase" }}>
                      Status
                    </th>
                    <th style={{ padding: "0.85rem 1rem", fontSize: "0.75rem", fontWeight: 700, color: "var(--text-secondary)", textTransform: "uppercase" }}>
                      Assigned Date
                    </th>
                    {canManage && (
                      <th style={{ padding: "0.85rem 1rem", fontSize: "0.75rem", fontWeight: 700, color: "var(--text-secondary)", textTransform: "uppercase", textAlign: "right" }}>
                        Actions
                      </th>
                    )}
                  </tr>
                </thead>
                <tbody>
                  {assignments.map((item) => {
                    const isSuspended = item.status === "suspended";
                    const isRevoked = item.status === "revoked";
                    const isActive = item.status === "active";

                    return (
                      <tr
                        key={item.id}
                        style={{
                          borderBottom: "1px solid var(--border-subtle)",
                          transition: "background-color 0.15s ease",
                        }}
                      >
                        <td style={{ padding: "1rem", verticalAlign: "middle" }}>
                          <div style={{ display: "flex", flexDirection: "column" }}>
                            <span style={{ fontWeight: 600, color: "var(--text-primary)", fontSize: "0.875rem", wordBreak: "break-word" }}>
                              {item.user.full_name}
                            </span>
                            <span style={{ fontSize: "0.75rem", color: "var(--text-muted)", wordBreak: "break-all" }}>
                              {item.user.email}
                            </span>
                          </div>
                        </td>
                        <td style={{ padding: "1rem", verticalAlign: "middle" }}>
                          <div style={{ display: "flex", flexDirection: "column" }}>
                            <span style={{ fontWeight: 600, color: "var(--text-primary)", fontSize: "0.875rem" }}>
                              {item.product.name}
                            </span>
                            <span style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
                              {item.product.code}
                            </span>
                          </div>
                        </td>
                        <td style={{ padding: "1rem", verticalAlign: "middle" }}>
                          <span
                            style={{
                              display: "inline-flex",
                              padding: "0.2rem 0.5rem",
                              borderRadius: "6px",
                              fontSize: "0.75rem",
                              fontWeight: 600,
                              background: "var(--glass-surface)",
                              border: "1px solid var(--border-glass)",
                              color: "var(--text-secondary)",
                            }}
                          >
                            {item.enabled_module_count} {item.enabled_module_count === 1 ? "module" : "modules"}
                          </span>
                        </td>
                        <td style={{ padding: "1rem", verticalAlign: "middle" }}>
                          <span
                            style={{
                              display: "inline-block",
                              padding: "0.2rem 0.6rem",
                              borderRadius: "9999px",
                              fontSize: "0.6875rem",
                              fontWeight: 700,
                              textTransform: "uppercase",
                              background: isActive
                                ? "rgba(16, 185, 129, 0.15)"
                                : isSuspended
                                ? "rgba(245, 158, 11, 0.15)"
                                : "rgba(239, 68, 68, 0.15)",
                              color: isActive
                                ? "var(--status-success, #10b981)"
                                : isSuspended
                                ? "var(--status-warning, #f59e0b)"
                                : "var(--status-danger, #ef4444)",
                              border: isActive
                                ? "1px solid rgba(16, 185, 129, 0.3)"
                                : isSuspended
                                ? "1px solid rgba(245, 158, 11, 0.3)"
                                : "1px solid rgba(239, 68, 68, 0.3)",
                            }}
                          >
                            {item.status}
                          </span>
                        </td>
                        <td style={{ padding: "1rem", verticalAlign: "middle", fontSize: "0.8125rem", color: "var(--text-secondary)" }}>
                          {formatDateTime(item.assigned_at)}
                        </td>
                        {canManage && (
                          <td style={{ padding: "1rem", verticalAlign: "middle", textAlign: "right" }}>
                            <div style={{ display: "inline-flex", alignItems: "center", gap: "0.5rem" }}>
                              {isActive && (
                                <>
                                  <button
                                    type="button"
                                    onClick={(e) => handleOpenEditModules(item, e)}
                                    className="btn btn-secondary btn-sm"
                                    aria-label={`Edit modules for ${item.user.full_name}`}
                                  >
                                    Edit Modules
                                  </button>
                                  <button
                                    type="button"
                                    onClick={(e) => handleOpenSuspend(item, e)}
                                    className="btn btn-secondary btn-sm"
                                    aria-label={`Suspend access for ${item.user.full_name}`}
                                  >
                                    Suspend
                                  </button>
                                  <button
                                    type="button"
                                    onClick={(e) => handleOpenRevoke(item, e)}
                                    className="btn btn-danger-action btn-sm"
                                    aria-label={`Revoke access for ${item.user.full_name}`}
                                  >
                                    Revoke
                                  </button>
                                </>
                              )}
                              {isSuspended && (
                                <>
                                  <button
                                    type="button"
                                    onClick={(e) => handleOpenReactivate(item, e)}
                                    className="btn btn-primary btn-sm"
                                    aria-label={`Reactivate access for ${item.user.full_name}`}
                                  >
                                    Reactivate
                                  </button>
                                  <button
                                    type="button"
                                    onClick={(e) => handleOpenRevoke(item, e)}
                                    className="btn btn-danger-action btn-sm"
                                    aria-label={`Revoke access for ${item.user.full_name}`}
                                  >
                                    Revoke
                                  </button>
                                </>
                              )}
                              {isRevoked && (
                                <span style={{ fontSize: "0.75rem", color: "var(--text-muted)", fontStyle: "italic" }}>
                                  Revoked
                                </span>
                              )}
                            </div>
                          </td>
                        )}
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            {/* Mobile Responsive Cards View (< 768px, safe at 320px) */}
            <div className="mobile-cards-container" style={{ display: "none", flexDirection: "column", gap: "0.75rem" }}>
              {assignments.map((item) => {
                const isSuspended = item.status === "suspended";
                const isRevoked = item.status === "revoked";
                const isActive = item.status === "active";

                return (
                  <div
                    key={item.id}
                    style={{
                      background: "var(--glass-surface-elevated)",
                      border: "1px solid var(--border-glass)",
                      borderRadius: "12px",
                      padding: "1rem",
                      display: "flex",
                      flexDirection: "column",
                      gap: "0.75rem",
                      boxShadow: "var(--shadow-sm)",
                    }}
                  >
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: "0.5rem" }}>
                      <div style={{ minWidth: 0 }}>
                        <div style={{ fontWeight: 700, fontSize: "0.9375rem", color: "var(--text-primary)", wordBreak: "break-word" }}>
                          {item.user.full_name}
                        </div>
                        <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", wordBreak: "break-all" }}>
                          {item.user.email}
                        </div>
                      </div>
                      <span
                        style={{
                          flexShrink: 0,
                          padding: "0.2rem 0.5rem",
                          borderRadius: "9999px",
                          fontSize: "0.6875rem",
                          fontWeight: 700,
                          textTransform: "uppercase",
                          background: isActive
                            ? "rgba(16, 185, 129, 0.15)"
                            : isSuspended
                            ? "rgba(245, 158, 11, 0.15)"
                            : "rgba(239, 68, 68, 0.15)",
                          color: isActive
                            ? "var(--status-success, #10b981)"
                            : isSuspended
                            ? "var(--status-warning, #f59e0b)"
                            : "var(--status-danger, #ef4444)",
                        }}
                      >
                        {item.status}
                      </span>
                    </div>

                    <div style={{ fontSize: "0.8125rem", color: "var(--text-secondary)", display: "flex", justifyContent: "space-between" }}>
                      <span>Product: <strong>{item.product.name}</strong></span>
                      <span>{item.enabled_module_count} modules</span>
                    </div>

                    <div style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
                      Assigned: {formatDateTime(item.assigned_at)}
                    </div>

                    {canManage && !isRevoked && (
                      <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem", marginTop: "0.25rem", borderTop: "1px solid var(--border-subtle)", paddingTop: "0.75rem" }}>
                        {isActive && (
                          <>
                            <button
                              type="button"
                              onClick={(e) => handleOpenEditModules(item, e)}
                              className="btn btn-secondary btn-sm"
                              style={{ flex: "1 1 auto" }}
                            >
                              Edit Modules
                            </button>
                            <button
                              type="button"
                              onClick={(e) => handleOpenSuspend(item, e)}
                              className="btn btn-secondary btn-sm"
                              style={{ flex: "1 1 auto" }}
                            >
                              Suspend
                            </button>
                            <button
                              type="button"
                              onClick={(e) => handleOpenRevoke(item, e)}
                              className="btn btn-danger-action btn-sm"
                              style={{ flex: "1 1 auto" }}
                            >
                              Revoke
                            </button>
                          </>
                        )}
                        {isSuspended && (
                          <>
                            <button
                              type="button"
                              onClick={(e) => handleOpenReactivate(item, e)}
                              className="btn btn-primary btn-sm"
                              style={{ flex: "1 1 auto" }}
                            >
                              Reactivate
                            </button>
                            <button
                              type="button"
                              onClick={(e) => handleOpenRevoke(item, e)}
                              className="btn btn-danger-action btn-sm"
                              style={{ flex: "1 1 auto" }}
                            >
                              Revoke
                            </button>
                          </>
                        )}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>

            {/* Pagination Controls */}
            <div
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                padding: "0.75rem 0",
                flexWrap: "wrap",
                gap: "0.75rem",
              }}
            >
              <div style={{ fontSize: "0.8125rem", color: "var(--text-secondary)" }}>
                Showing {(page - 1) * pageSize + 1}–{Math.min(page * pageSize, totalCount)} of {totalCount} assignments
              </div>

              <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                <button
                  type="button"
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  disabled={page <= 1}
                  className="btn btn-secondary btn-sm"
                  aria-label="Previous page"
                  style={{ display: "inline-flex", alignItems: "center", gap: "0.25rem" }}
                >
                  <ChevronLeftIcon size={14} />
                  <span>Previous</span>
                </button>

                <span style={{ fontSize: "0.8125rem", fontWeight: 600, color: "var(--text-primary)", padding: "0 0.5rem" }}>
                  Page {page} of {totalPages}
                </span>

                <button
                  type="button"
                  onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                  disabled={page >= totalPages}
                  className="btn btn-secondary btn-sm"
                  aria-label="Next page"
                  style={{ display: "inline-flex", alignItems: "center", gap: "0.25rem" }}
                >
                  <span>Next</span>
                  <ChevronRightIcon size={14} />
                </button>
              </div>
            </div>
          </>
        )}
      </div>

      {/* Modals */}
      <AssignMemberModal
        isOpen={isAssignOpen}
        onClose={() => setIsAssignOpen(false)}
        onSuccess={() => handleMutationSuccess("Member assigned successfully.")}
        onConflict={handleConflict}
        triggerRef={triggerRef}
      />

      <SuspendModal
        isOpen={isSuspendOpen}
        assignment={activeAssignment}
        onClose={() => {
          setIsSuspendOpen(false);
          setActiveAssignment(null);
        }}
        onSuccess={() => handleMutationSuccess("Assignment suspended successfully.")}
        onConflict={handleConflict}
        triggerRef={triggerRef}
      />

      <ReactivateModal
        isOpen={isReactivateOpen}
        assignment={activeAssignment}
        onClose={() => {
          setIsReactivateOpen(false);
          setActiveAssignment(null);
        }}
        onSuccess={() => handleMutationSuccess("Assignment reactivated successfully.")}
        onConflict={handleConflict}
        triggerRef={triggerRef}
      />

      <RevokeModal
        isOpen={isRevokeOpen}
        assignment={activeAssignment}
        onClose={() => {
          setIsRevokeOpen(false);
          setActiveAssignment(null);
        }}
        onSuccess={() => handleMutationSuccess("Assignment revoked successfully.")}
        onConflict={handleConflict}
        triggerRef={triggerRef}
      />

      <EditModulesModal
        isOpen={isEditModulesOpen}
        assignment={activeAssignment}
        onClose={() => {
          setIsEditModulesOpen(false);
          setActiveAssignment(null);
        }}
        onSuccess={() => handleMutationSuccess("Assignment modules updated successfully.")}
        onConflict={handleConflict}
        triggerRef={triggerRef}
      />

      {/* Responsive View Styles */}
      <style>{`
        @media (max-width: 768px) {
          .desktop-table-container {
            display: none !important;
          }
          .mobile-cards-container {
            display: flex !important;
          }
        }
      `}</style>
    </AppShell>
  );
};
