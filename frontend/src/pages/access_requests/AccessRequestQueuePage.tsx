/**
 * Access Requests & Approvals Queue Workspace (Phase 3F).
 *
 * Implements the tenant/owner approver queue and request tracking:
 * - Summary KPI cards (Pending, Approved, Denied, Total)
 * - 300ms debounced server-side search by requester email/name/product
 * - Status filter & pagination
 * - Permission-gated actions (Approve, Deny with 1-500 char reason, Cancel)
 * - Responsive table with accessible modals
 */

import React, { useCallback, useEffect, useId, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { accessRequestsApi } from "../../api/accessRequests.ts";
import { ApiError } from "../../api/client.ts";
import type { AccessRequestItem, AccessRequestStatus } from "../../api/types.ts";
import { AppShell } from "../../components/AppShell.tsx";
import {
  AlertCircleIcon,
  CheckCircleIcon,
  ChevronLeftIcon,
  ChevronRightIcon,
  PlusIcon,
  RotateCcwIcon,
  SearchIcon,
  ShieldCheckIcon,
} from "../../components/Icons.tsx";
import { formatDateTime } from "../../config/dateUtils.ts";
import { useAuth } from "../../context/AuthContext.tsx";
import { ApproveRequestModal } from "../../components/access_requests/ApproveRequestModal.tsx";
import { DenyRequestModal } from "../../components/access_requests/DenyRequestModal.tsx";

export const AccessRequestQueuePage: React.FC = () => {
  const { user } = useAuth();
  const searchInputId = useId();
  const statusFilterId = useId();

  const isOwner = user?.active_context?.type === "platform_owner";
  const effectivePermissions = useMemo(() => {
    return new Set(user?.active_context?.effective_permissions ?? []);
  }, [user?.active_context?.effective_permissions]);

  const canApprove = isOwner || effectivePermissions.has("assignments.manage");

  // State
  const [requests, setRequests] = useState<readonly AccessRequestItem[]>([]);
  const [totalCount, setTotalCount] = useState<number>(0);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [notification, setNotification] = useState<{
    type: "success" | "warning";
    message: string;
  } | null>(null);

  // Filters & Pagination
  const [searchInput, setSearchInput] = useState<string>("");
  const [debouncedSearch, setDebouncedSearch] = useState<string>("");
  const [statusFilter, setStatusFilter] = useState<string>("");
  const [page, setPage] = useState<number>(1);
  const pageSize = 20;

  // Modals
  const [isApproveOpen, setIsApproveOpen] = useState<boolean>(false);
  const [isDenyOpen, setIsDenyOpen] = useState<boolean>(false);
  const [selectedRequest, setSelectedRequest] = useState<AccessRequestItem | null>(null);
  const triggerRef = useRef<HTMLElement | null>(null);

  // 300ms Debounce
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearch(searchInput);
      setPage(1);
    }, 300);
    return () => clearTimeout(timer);
  }, [searchInput]);

  // Load Requests
  const fetchRequests = useCallback(async () => {
    setIsLoading(true);
    setErrorMessage(null);

    try {
      const orgId = isOwner ? undefined : user?.active_context?.organization?.id;
      const response = await accessRequestsApi.listRequests({
        organization_id: orgId,
        status: (statusFilter || undefined) as AccessRequestStatus | undefined,
        search: debouncedSearch.trim() || undefined,
        page,
        page_size: pageSize,
      });

      setRequests(response.results);
      setTotalCount(response.count);
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setErrorMessage(err.message || "Failed to load access requests.");
      } else {
        setErrorMessage("An unexpected error occurred while loading requests.");
      }
    } finally {
      setIsLoading(false);
    }
  }, [isOwner, user?.active_context?.organization?.id, statusFilter, debouncedSearch, page, pageSize]);

  useEffect(() => {
    fetchRequests();
  }, [fetchRequests]);

  const handleOpenApprove = (req: AccessRequestItem, e: React.MouseEvent<HTMLElement>) => {
    triggerRef.current = e.currentTarget;
    setSelectedRequest(req);
    setIsApproveOpen(true);
  };

  const handleOpenDeny = (req: AccessRequestItem, e: React.MouseEvent<HTMLElement>) => {
    triggerRef.current = e.currentTarget;
    setSelectedRequest(req);
    setIsDenyOpen(true);
  };

  const handleCancelRequest = async (req: AccessRequestItem) => {
    if (!window.confirm("Are you sure you want to cancel this access request?")) {
      return;
    }
    try {
      await accessRequestsApi.cancelRequest(req.id);
      setNotification({
        type: "success",
        message: "Access request successfully cancelled.",
      });
      fetchRequests();
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setNotification({
          type: "warning",
          message: err.message || "Failed to cancel access request.",
        });
      }
    }
  };

  // Compute status summary
  const summary = useMemo(() => {
    let pending = 0;
    let approved = 0;
    let denied = 0;
    for (const r of requests) {
      if (r.status === "pending") pending++;
      else if (r.status === "approved") approved++;
      else if (r.status === "denied") denied++;
    }
    return { pending, approved, denied, total: totalCount };
  }, [requests, totalCount]);

  const totalPages = Math.ceil(totalCount / pageSize) || 1;

  const getStatusBadge = (status: AccessRequestStatus) => {
    const styles: Record<AccessRequestStatus, { bg: string; text: string; border: string; dot: string; label: string }> = {
      pending: {
        bg: "rgba(245, 158, 11, 0.12)",
        text: "var(--status-warning, #f59e0b)",
        border: "1px solid rgba(245, 158, 11, 0.25)",
        dot: "#f59e0b",
        label: "Pending Review",
      },
      approved: {
        bg: "rgba(16, 185, 129, 0.12)",
        text: "var(--status-success, #10b981)",
        border: "1px solid rgba(16, 185, 129, 0.25)",
        dot: "#10b981",
        label: "Approved",
      },
      denied: {
        bg: "rgba(239, 68, 68, 0.12)",
        text: "var(--status-danger, #ef4444)",
        border: "1px solid rgba(239, 68, 68, 0.25)",
        dot: "#ef4444",
        label: "Denied",
      },
      cancelled: {
        bg: "rgba(148, 163, 184, 0.12)",
        text: "var(--text-muted, #94a3b8)",
        border: "1px solid rgba(148, 163, 184, 0.25)",
        dot: "#94a3b8",
        label: "Cancelled",
      },
    };
    const s = styles[status] || styles.pending;
    return (
      <span
        style={{
          display: "inline-flex",
          alignItems: "center",
          gap: "0.35rem",
          padding: "0.25rem 0.65rem",
          borderRadius: "9999px",
          fontSize: "0.75rem",
          fontWeight: 700,
          backgroundColor: s.bg,
          color: s.text,
          border: s.border,
          whiteSpace: "nowrap",
        }}
      >
        <span style={{ width: "6px", height: "6px", borderRadius: "50%", background: s.dot }} />
        {s.label}
      </span>
    );
  };

  return (
    <AppShell>
      <div style={{ maxWidth: "1400px", margin: "0 auto", padding: "2rem" }}>
        {/* Breadcrumb Navigation */}
        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", fontSize: "0.8125rem", color: "var(--text-muted)", marginBottom: "1.25rem", fontWeight: 500 }}>
          <Link to="/" style={{ color: "var(--text-muted)", textDecoration: "none", transition: "color 0.15s" }}>Platform Owner</Link>
          <span>/</span>
          <span>Customer Operations</span>
          <span>/</span>
          <span style={{ color: "var(--brand-primary)", fontWeight: 600 }}>Access Requests & Approvals</span>
        </div>

        {/* Header */}
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "flex-start",
            marginBottom: "2rem",
            flexWrap: "wrap",
            gap: "1rem",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: "1rem" }}>
            <div
              style={{
                width: 48,
                height: 48,
                borderRadius: 14,
                background: "linear-gradient(135deg, rgba(56, 103, 245, 0.15) 0%, rgba(139, 92, 246, 0.15) 100%)",
                border: "1px solid rgba(56, 103, 245, 0.25)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                color: "var(--brand-primary)",
                boxShadow: "0 4px 12px rgba(56, 103, 245, 0.1)",
                flexShrink: 0,
              }}
            >
              <ShieldCheckIcon size={24} />
            </div>
            <div>
              <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
                <h1 className="heading-hero" style={{ fontSize: "1.75rem", fontWeight: 800, margin: 0, letterSpacing: "-0.02em", color: "var(--text-primary)" }}>
                  Access Requests & Approvals
                </h1>
                <span
                  style={{
                    background: "rgba(56, 103, 245, 0.1)",
                    color: "var(--brand-primary)",
                    padding: "0.2rem 0.65rem",
                    borderRadius: 999,
                    fontSize: "0.75rem",
                    fontWeight: 700,
                    border: "1px solid rgba(56, 103, 245, 0.2)",
                  }}
                >
                  {totalCount} Total
                </span>
              </div>
              <p
                style={{
                  fontSize: "0.9375rem",
                  color: "var(--text-secondary)",
                  margin: "0.25rem 0 0 0",
                }}
              >
                Review pending product access requests, enforce ceiling quotas, and log immutable decisions.
              </p>
            </div>
          </div>

          <Link
            to="/access-requests/new"
            className="btn btn-gradient"
            style={{
              textDecoration: "none",
            }}
          >
            <PlusIcon size={16} />
            <span>New Access Request</span>
          </Link>
        </div>

        {/* Notifications */}
        {notification && (
          <div
            role="status"
            aria-live="polite"
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              padding: "0.75rem 1rem",
              borderRadius: "0.5rem",
              marginBottom: "1.5rem",
              backgroundColor:
                notification.type === "success"
                  ? "rgba(34, 197, 94, 0.1)"
                  : "rgba(245, 158, 11, 0.1)",
              border: `1px solid ${
                notification.type === "success"
                  ? "rgba(34, 197, 94, 0.3)"
                  : "rgba(245, 158, 11, 0.3)"
              }`,
              color: notification.type === "success" ? "#22c55e" : "#f59e0b",
              fontSize: "0.875rem",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
              {notification.type === "success" ? (
                <CheckCircleIcon size={16} />
              ) : (
                <AlertCircleIcon size={16} />
              )}
              <span>{notification.message}</span>
            </div>
            <button
              onClick={() => setNotification(null)}
              style={{
                background: "transparent",
                border: "none",
                color: "inherit",
                cursor: "pointer",
                padding: "0.25rem",
              }}
            >
              ✕
            </button>
          </div>
        )}

        {/* KPI Summary Cards */}
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
            gap: "1.25rem",
            marginBottom: "1.75rem",
          }}
        >
          {/* 1. Total Requests */}
          <div
            style={{
              padding: "1.5rem",
              backgroundColor: "var(--glass-surface-elevated)",
              borderRadius: "16px",
              border: "1px solid var(--border-glass)",
              boxShadow: "var(--shadow-sm)",
              position: "relative",
              overflow: "hidden",
            }}
          >
            <div
              style={{
                position: "absolute",
                top: 0,
                left: 0,
                right: 0,
                height: "3px",
                background: "var(--brand-primary, #3867f5)",
              }}
            />
            <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", textTransform: "uppercase", fontWeight: 700, letterSpacing: "0.06em" }}>
              Total Requests
            </div>
            <div style={{ fontSize: "2rem", fontWeight: 800, marginTop: "0.35rem", color: "var(--text-primary)", letterSpacing: "-0.03em" }}>
              {summary.total}
            </div>
            <div style={{ fontSize: "0.75rem", color: "var(--text-secondary)", marginTop: "0.35rem" }}>
              All submitted requests across tenants
            </div>
          </div>

          {/* 2. Pending Approvals */}
          <div
            style={{
              padding: "1.5rem",
              backgroundColor: "var(--glass-surface-elevated)",
              borderRadius: "16px",
              border: "1px solid var(--border-glass)",
              boxShadow: "var(--shadow-sm)",
              position: "relative",
              overflow: "hidden",
            }}
          >
            <div
              style={{
                position: "absolute",
                top: 0,
                left: 0,
                right: 0,
                height: "3px",
                background: "var(--status-warning, #f59e0b)",
              }}
            />
            <div style={{ fontSize: "0.75rem", color: "var(--status-warning, #f59e0b)", textTransform: "uppercase", fontWeight: 700, letterSpacing: "0.06em" }}>
              Pending Approvals
            </div>
            <div style={{ fontSize: "2rem", fontWeight: 800, marginTop: "0.35rem", color: "var(--status-warning, #f59e0b)", letterSpacing: "-0.03em" }}>
              {summary.pending}
            </div>
            <div style={{ fontSize: "0.75rem", color: "var(--text-secondary)", marginTop: "0.35rem" }}>
              Awaiting administrator decision
            </div>
          </div>

          {/* 3. Approved */}
          <div
            style={{
              padding: "1.5rem",
              backgroundColor: "var(--glass-surface-elevated)",
              borderRadius: "16px",
              border: "1px solid var(--border-glass)",
              boxShadow: "var(--shadow-sm)",
              position: "relative",
              overflow: "hidden",
            }}
          >
            <div
              style={{
                position: "absolute",
                top: 0,
                left: 0,
                right: 0,
                height: "3px",
                background: "var(--status-success, #10b981)",
              }}
            />
            <div style={{ fontSize: "0.75rem", color: "var(--status-success, #10b981)", textTransform: "uppercase", fontWeight: 700, letterSpacing: "0.06em" }}>
              Approved
            </div>
            <div style={{ fontSize: "2rem", fontWeight: 800, marginTop: "0.35rem", color: "var(--status-success, #10b981)", letterSpacing: "-0.03em" }}>
              {summary.approved}
            </div>
            <div style={{ fontSize: "0.75rem", color: "var(--text-secondary)", marginTop: "0.35rem" }}>
              Granted tenant workspace entitlements
            </div>
          </div>

          {/* 4. Denied */}
          <div
            style={{
              padding: "1.5rem",
              backgroundColor: "var(--glass-surface-elevated)",
              borderRadius: "16px",
              border: "1px solid var(--border-glass)",
              boxShadow: "var(--shadow-sm)",
              position: "relative",
              overflow: "hidden",
            }}
          >
            <div
              style={{
                position: "absolute",
                top: 0,
                left: 0,
                right: 0,
                height: "3px",
                background: "var(--status-danger, #ef4444)",
              }}
            />
            <div style={{ fontSize: "0.75rem", color: "var(--status-danger, #ef4444)", textTransform: "uppercase", fontWeight: 700, letterSpacing: "0.06em" }}>
              Denied
            </div>
            <div style={{ fontSize: "2rem", fontWeight: 800, marginTop: "0.35rem", color: "var(--status-danger, #ef4444)", letterSpacing: "-0.03em" }}>
              {summary.denied}
            </div>
            <div style={{ fontSize: "0.75rem", color: "var(--text-secondary)", marginTop: "0.35rem" }}>
              Rejected requests with decision log
            </div>
          </div>
        </div>

        {/* Filter Bar */}
        <div
          style={{
            display: "flex",
            gap: "1rem",
            marginBottom: "1.5rem",
            flexWrap: "wrap",
            alignItems: "center",
            padding: "0.85rem 1.25rem",
            borderRadius: "14px",
            backgroundColor: "var(--glass-surface-elevated)",
            border: "1px solid var(--border-glass)",
            boxShadow: "var(--shadow-sm)",
          }}
        >
          <div style={{ position: "relative", flex: 1, minWidth: "260px" }}>
            <span
              style={{
                position: "absolute",
                left: "0.85rem",
                top: "50%",
                transform: "translateY(-50%)",
                color: "var(--text-muted)",
                display: "flex",
                alignItems: "center",
              }}
            >
              <SearchIcon size={16} />
            </span>
            <input
              id={searchInputId}
              type="text"
              placeholder="Search by requester email, name, or product..."
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              style={{
                width: "100%",
                padding: "0.65rem 0.85rem 0.65rem 2.4rem",
                backgroundColor: "var(--glass-surface-sunken)",
                border: "1px solid var(--border-glass)",
                borderRadius: "10px",
                color: "var(--text-primary)",
                fontSize: "0.875rem",
                outline: "none",
                boxSizing: "border-box",
                transition: "border-color 0.15s ease",
              }}
            />
          </div>

          <div style={{ minWidth: "180px" }}>
            <label htmlFor={statusFilterId} className="sr-only">Filter by Status</label>
            <select
              id={statusFilterId}
              value={statusFilter}
              onChange={(e) => {
                setStatusFilter(e.target.value);
                setPage(1);
              }}
              style={{
                width: "100%",
                padding: "0.65rem 0.85rem",
                backgroundColor: "var(--glass-surface-sunken)",
                border: "1px solid var(--border-glass)",
                borderRadius: "10px",
                color: "var(--text-primary)",
                fontSize: "0.875rem",
                outline: "none",
                boxSizing: "border-box",
                cursor: "pointer",
              }}
            >
              <option value="">All Statuses</option>
              <option value="pending">Pending</option>
              <option value="approved">Approved</option>
              <option value="denied">Denied</option>
              <option value="cancelled">Cancelled</option>
            </select>
          </div>

          <button
            type="button"
            onClick={fetchRequests}
            title="Refresh requests"
            style={{
              padding: "0.65rem 0.85rem",
              backgroundColor: "var(--glass-surface-sunken)",
              border: "1px solid var(--border-glass)",
              borderRadius: "10px",
              color: "var(--text-secondary)",
              cursor: "pointer",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              transition: "all 0.15s ease",
            }}
          >
            <RotateCcwIcon size={16} />
          </button>
        </div>

        {/* Content Table Container */}
        <div
          style={{
            backgroundColor: "var(--glass-surface-elevated)",
            borderRadius: "18px",
            border: "1px solid var(--border-glass)",
            boxShadow: "var(--shadow-sm)",
            overflow: "hidden",
          }}
        >
          {/* Card Header Strip */}
          <div
            style={{
              padding: "1.25rem 1.5rem",
              borderBottom: "1px solid var(--border-glass)",
              background: "var(--glass-surface-sunken)",
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              flexWrap: "wrap",
              gap: "0.75rem",
            }}
          >
            <div>
              <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                <span style={{ fontWeight: 800, fontSize: "1.05rem", color: "var(--text-primary)", letterSpacing: "-0.01em" }}>
                  Access Requests Registry
                </span>
                <span
                  style={{
                    fontSize: "0.72rem",
                    fontWeight: 700,
                    padding: "0.15rem 0.55rem",
                    borderRadius: "9999px",
                    backgroundColor: "rgba(56, 103, 245, 0.1)",
                    color: "var(--brand-primary, #3867f5)",
                    border: "1px solid rgba(56, 103, 245, 0.2)",
                  }}
                >
                  {totalCount} Requests
                </span>
              </div>
              <p style={{ margin: "0.2rem 0 0 0", fontSize: "0.8125rem", color: "var(--text-secondary)" }}>
                Audit trail of tenant-level product access requests and approvals
              </p>
            </div>
          </div>

          {isLoading ? (
            <div style={{ padding: "3.5rem", textAlign: "center", color: "var(--text-muted)" }}>
              Loading access requests...
            </div>
          ) : errorMessage ? (
            <div
              style={{
                padding: "3.5rem",
                textAlign: "center",
                color: "var(--status-danger, #ef4444)",
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                gap: "0.85rem",
              }}
            >
              <AlertCircleIcon size={28} />
              <span style={{ fontWeight: 600 }}>{errorMessage}</span>
              <button
                onClick={fetchRequests}
                style={{
                  padding: "0.6rem 1.25rem",
                  backgroundColor: "var(--brand-primary, #3867f5)",
                  color: "#ffffff",
                  border: "none",
                  borderRadius: "10px",
                  fontWeight: 700,
                  fontSize: "0.875rem",
                  cursor: "pointer",
                  boxShadow: "0 2px 10px rgba(56, 103, 245, 0.25)",
                }}
              >
                Try Again
              </button>
            </div>
          ) : requests.length === 0 ? (
            <div style={{ padding: "3.5rem", textAlign: "center", color: "var(--text-muted)", fontSize: "0.9375rem" }}>
              No access requests found matching the current criteria.
            </div>
          ) : (
            <div style={{ overflowX: "auto" }}>
              <table
                style={{
                  width: "100%",
                  borderCollapse: "collapse",
                  fontSize: "0.875rem",
                  textAlign: "left",
                }}
              >
                <thead>
                  <tr
                    style={{
                      borderBottom: "1px solid var(--border-glass)",
                      backgroundColor: "var(--glass-surface-sunken)",
                    }}
                  >
                    <th style={{ padding: "0.85rem 1.5rem", fontWeight: 700, fontSize: "0.72rem", letterSpacing: "0.06em", textTransform: "uppercase", color: "var(--text-secondary)" }}>
                      Requester
                    </th>
                    <th style={{ padding: "0.85rem 1.5rem", fontWeight: 700, fontSize: "0.72rem", letterSpacing: "0.06em", textTransform: "uppercase", color: "var(--text-secondary)" }}>
                      Organization
                    </th>
                    <th style={{ padding: "0.85rem 1.5rem", fontWeight: 700, fontSize: "0.72rem", letterSpacing: "0.06em", textTransform: "uppercase", color: "var(--text-secondary)" }}>
                      Product
                    </th>
                    <th style={{ padding: "0.85rem 1.5rem", fontWeight: 700, fontSize: "0.72rem", letterSpacing: "0.06em", textTransform: "uppercase", color: "var(--text-secondary)" }}>
                      Requested At
                    </th>
                    <th style={{ padding: "0.85rem 1.5rem", fontWeight: 700, fontSize: "0.72rem", letterSpacing: "0.06em", textTransform: "uppercase", color: "var(--text-secondary)" }}>
                      Status
                    </th>
                    <th style={{ padding: "0.85rem 1.5rem", fontWeight: 700, fontSize: "0.72rem", letterSpacing: "0.06em", textTransform: "uppercase", color: "var(--text-secondary)" }}>
                      Reason / Decision
                    </th>
                    <th style={{ padding: "0.85rem 1.5rem", fontWeight: 700, fontSize: "0.72rem", letterSpacing: "0.06em", textTransform: "uppercase", color: "var(--text-secondary)", textAlign: "right" }}>
                      Actions
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {requests.map((req, rIdx) => {
                    const isRequesterSelf = user?.id === req.requester_id;
                    const latestDecision = req.decisions?.[0];

                    return (
                      <tr
                        key={req.id}
                        style={{
                          borderBottom: rIdx < requests.length - 1 ? "1px solid var(--border-glass)" : "none",
                          transition: "background-color 0.15s ease",
                        }}
                        onMouseEnter={(e) => {
                          e.currentTarget.style.backgroundColor = "var(--glass-surface-hover)";
                        }}
                        onMouseLeave={(e) => {
                          e.currentTarget.style.backgroundColor = "transparent";
                        }}
                      >
                        <td style={{ padding: "1rem 1.5rem" }}>
                          <div style={{ display: "flex", alignItems: "center", gap: "0.65rem" }}>
                            <div
                              style={{
                                width: "32px",
                                height: "32px",
                                borderRadius: "8px",
                                background: "linear-gradient(135deg, rgba(56, 103, 245, 0.15) 0%, rgba(139, 92, 246, 0.15) 100%)",
                                border: "1px solid rgba(56, 103, 245, 0.25)",
                                display: "flex",
                                alignItems: "center",
                                justifyContent: "center",
                                color: "var(--brand-primary, #3867f5)",
                                fontWeight: 800,
                                fontSize: "0.75rem",
                                flexShrink: 0,
                              }}
                            >
                              {(req.requester_name || req.requester_email || "U").substring(0, 2).toUpperCase()}
                            </div>
                            <div>
                              <div style={{ fontWeight: 700, color: "var(--text-primary)", fontSize: "0.875rem" }}>
                                {req.requester_name || "User"}
                              </div>
                              <div style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
                                {req.requester_email}
                              </div>
                            </div>
                          </div>
                        </td>
                        <td style={{ padding: "1rem 1.5rem" }}>
                          <div style={{ fontWeight: 600, color: "var(--text-primary)" }}>
                            {req.organization_name || "—"}
                          </div>
                          {req.organization_code && (
                            <div style={{ marginTop: "0.15rem" }}>
                              <span
                                style={{
                                  fontSize: "0.6875rem",
                                  padding: "0.1rem 0.4rem",
                                  borderRadius: "4px",
                                  backgroundColor: "var(--glass-surface-sunken)",
                                  fontFamily: "var(--font-code)",
                                  color: "var(--text-muted)",
                                  border: "1px solid var(--border-subtle)",
                                }}
                              >
                                {req.organization_code}
                              </span>
                            </div>
                          )}
                        </td>
                        <td style={{ padding: "1rem 1.5rem" }}>
                          <div style={{ fontWeight: 700, color: "var(--text-primary)" }}>
                            {req.product_name || "—"}
                          </div>
                          {req.product_code && (
                            <div style={{ marginTop: "0.15rem" }}>
                              <span
                                style={{
                                  fontSize: "0.6875rem",
                                  padding: "0.1rem 0.4rem",
                                  borderRadius: "4px",
                                  backgroundColor: "rgba(56, 103, 245, 0.08)",
                                  fontFamily: "var(--font-code)",
                                  color: "var(--brand-primary, #3867f5)",
                                }}
                              >
                                {req.product_code}
                              </span>
                            </div>
                          )}
                        </td>
                        <td style={{ padding: "1rem 1.5rem", color: "var(--text-secondary)", fontSize: "0.8125rem", whiteSpace: "nowrap" }}>
                          {formatDateTime(req.requested_at)}
                        </td>
                        <td style={{ padding: "1rem 1.5rem" }}>{getStatusBadge(req.status)}</td>
                        <td
                          style={{
                            padding: "1rem 1.5rem",
                            maxWidth: "260px",
                            overflow: "hidden",
                            textOverflow: "ellipsis",
                            whiteSpace: "nowrap",
                            fontSize: "0.8125rem",
                          }}
                          title={latestDecision?.reason || req.reason}
                        >
                          {latestDecision?.reason ? (
                            <span style={{ color: "var(--text-primary)" }}>
                              <strong style={{ color: "var(--text-secondary)" }}>Decision:</strong> {latestDecision.reason}
                            </span>
                          ) : req.reason ? (
                            <span style={{ color: "var(--text-secondary)" }}>{req.reason}</span>
                          ) : (
                            <span style={{ color: "var(--text-muted)" }}>—</span>
                          )}
                        </td>
                        <td style={{ padding: "1rem 1.5rem", textAlign: "right" }}>
                          {req.status === "pending" ? (
                            <div
                              style={{
                                display: "inline-flex",
                                alignItems: "center",
                                gap: "0.5rem",
                                justifyContent: "flex-end",
                              }}
                            >
                              {canApprove && (
                                <>
                                  <button
                                    type="button"
                                    onClick={(e) => handleOpenApprove(req, e)}
                                    style={{
                                      padding: "0.4rem 0.75rem",
                                      background: "linear-gradient(135deg, #10b981 0%, #059669 100%)",
                                      color: "#ffffff",
                                      border: "none",
                                      borderRadius: "8px",
                                      fontSize: "0.75rem",
                                      fontWeight: 700,
                                      cursor: "pointer",
                                      boxShadow: "0 2px 8px rgba(16, 185, 129, 0.25)",
                                      transition: "transform 0.1s ease",
                                    }}
                                  >
                                    Approve
                                  </button>
                                  <button
                                    type="button"
                                    onClick={(e) => handleOpenDeny(req, e)}
                                    style={{
                                      padding: "0.4rem 0.75rem",
                                      background: "linear-gradient(135deg, #ef4444 0%, #dc2626 100%)",
                                      color: "#ffffff",
                                      border: "none",
                                      borderRadius: "8px",
                                      fontSize: "0.75rem",
                                      fontWeight: 700,
                                      cursor: "pointer",
                                      boxShadow: "0 2px 8px rgba(239, 68, 68, 0.25)",
                                      transition: "transform 0.1s ease",
                                    }}
                                  >
                                    Deny
                                  </button>
                                </>
                              )}
                              {(isRequesterSelf || canApprove) && (
                                <button
                                  type="button"
                                  onClick={() => handleCancelRequest(req)}
                                  style={{
                                    padding: "0.4rem 0.75rem",
                                    backgroundColor: "var(--glass-surface-sunken)",
                                    color: "var(--text-secondary)",
                                    border: "1px solid var(--border-glass)",
                                    borderRadius: "8px",
                                    fontSize: "0.75rem",
                                    fontWeight: 600,
                                    cursor: "pointer",
                                    transition: "all 0.15s ease",
                                  }}
                                >
                                  Cancel
                                </button>
                              )}
                            </div>
                          ) : (
                            <span style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>Logged</span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}

          {/* Pagination */}
          {!isLoading && totalCount > 0 && (
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                padding: "0.9rem 1.5rem",
                borderTop: "1px solid var(--border-glass)",
                backgroundColor: "var(--glass-surface-sunken)",
                fontSize: "0.8125rem",
                color: "var(--text-secondary)",
                flexWrap: "wrap",
                gap: "0.75rem",
              }}
            >
              <div>
                Showing <strong>{(page - 1) * pageSize + 1}</strong> to{" "}
                <strong>{Math.min(page * pageSize, totalCount)}</strong> of <strong>{totalCount}</strong> requests
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                <button
                  type="button"
                  disabled={page <= 1}
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  aria-label="Previous Page"
                  style={{
                    padding: "0.4rem 0.75rem",
                    backgroundColor: "var(--glass-surface-elevated)",
                    border: "1px solid var(--border-glass)",
                    borderRadius: "8px",
                    color: "var(--text-primary)",
                    cursor: page <= 1 ? "not-allowed" : "pointer",
                    opacity: page <= 1 ? 0.4 : 1,
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                  }}
                >
                  <ChevronLeftIcon size={14} />
                </button>
                <span style={{ fontWeight: 600, padding: "0 0.4rem" }}>
                  Page {page} of {totalPages}
                </span>
                <button
                  type="button"
                  disabled={page >= totalPages}
                  onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                  aria-label="Next Page"
                  style={{
                    padding: "0.4rem 0.75rem",
                    backgroundColor: "var(--glass-surface-elevated)",
                    border: "1px solid var(--border-glass)",
                    borderRadius: "8px",
                    color: "var(--text-primary)",
                    cursor: page >= totalPages ? "not-allowed" : "pointer",
                    opacity: page >= totalPages ? 0.4 : 1,
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                  }}
                >
                  <ChevronRightIcon size={14} />
                </button>
              </div>
            </div>
          )}
        </div>

        {/* Modals */}
        <ApproveRequestModal
          isOpen={isApproveOpen}
          requestItem={selectedRequest}
          onClose={() => {
            setIsApproveOpen(false);
            setSelectedRequest(null);
          }}
          onSuccess={() => {
            setNotification({
              type: "success",
              message: "Access request approved and product seat assigned successfully!",
            });
            fetchRequests();
          }}
          triggerRef={triggerRef}
        />

        <DenyRequestModal
          isOpen={isDenyOpen}
          requestItem={selectedRequest}
          onClose={() => {
            setIsDenyOpen(false);
            setSelectedRequest(null);
          }}
          onSuccess={() => {
            setNotification({
              type: "success",
              message: "Access request denied with recorded reason.",
            });
            fetchRequests();
          }}
          triggerRef={triggerRef}
        />
      </div>
    </AppShell>
  );
};
