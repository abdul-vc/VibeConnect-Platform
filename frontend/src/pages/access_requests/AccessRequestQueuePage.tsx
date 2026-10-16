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
    const styles: Record<AccessRequestStatus, { bg: string; text: string; label: string }> = {
      pending: { bg: "rgba(245, 158, 11, 0.15)", text: "#f59e0b", label: "Pending Review" },
      approved: { bg: "rgba(34, 197, 94, 0.15)", text: "#22c55e", label: "Approved" },
      denied: { bg: "rgba(239, 68, 68, 0.15)", text: "#ef4444", label: "Denied" },
      cancelled: { bg: "rgba(148, 163, 184, 0.15)", text: "#94a3b8", label: "Cancelled" },
    };
    const s = styles[status] || styles.pending;
    return (
      <span
        style={{
          display: "inline-flex",
          alignItems: "center",
          padding: "0.25rem 0.625rem",
          borderRadius: "9999px",
          fontSize: "0.75rem",
          fontWeight: 600,
          backgroundColor: s.bg,
          color: s.text,
        }}
      >
        {s.label}
      </span>
    );
  };

  return (
    <AppShell>
      <div style={{ maxWidth: "1280px", margin: "0 auto", padding: "1.5rem" }}>
        {/* Header */}
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "flex-start",
            marginBottom: "1.5rem",
            flexWrap: "wrap",
            gap: "1rem",
          }}
        >
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
              <ShieldCheckIcon size={24} />
              <h1 style={{ fontSize: "1.5rem", fontWeight: 700, margin: 0 }}>
                Access Requests & Approvals
              </h1>
            </div>
            <p
              style={{
                fontSize: "0.875rem",
                color: "var(--text-secondary, #94a3b8)",
                margin: "0.25rem 0 0 0",
              }}
            >
              Review pending product access requests, enforce ceiling quotas, and log immutable decisions.
            </p>
          </div>

          <Link
            to="/access-requests/new"
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: "0.5rem",
              padding: "0.625rem 1rem",
              backgroundColor: "var(--color-primary, #6366f1)",
              color: "#ffffff",
              borderRadius: "0.375rem",
              fontWeight: 500,
              fontSize: "0.875rem",
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
            gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))",
            gap: "1rem",
            marginBottom: "1.5rem",
          }}
        >
          <div
            style={{
              padding: "1.25rem",
              backgroundColor: "var(--bg-card, #1e293b)",
              borderRadius: "0.75rem",
              border: "1px solid var(--border-color, #334155)",
            }}
          >
            <div style={{ fontSize: "0.75rem", color: "var(--text-muted, #94a3b8)", textTransform: "uppercase", fontWeight: 600 }}>
              Total Requests
            </div>
            <div style={{ fontSize: "1.5rem", fontWeight: 700, marginTop: "0.25rem" }}>
              {summary.total}
            </div>
          </div>
          <div
            style={{
              padding: "1.25rem",
              backgroundColor: "var(--bg-card, #1e293b)",
              borderRadius: "0.75rem",
              border: "1px solid rgba(245, 158, 11, 0.3)",
            }}
          >
            <div style={{ fontSize: "0.75rem", color: "#f59e0b", textTransform: "uppercase", fontWeight: 600 }}>
              Pending Approvals
            </div>
            <div style={{ fontSize: "1.5rem", fontWeight: 700, marginTop: "0.25rem", color: "#f59e0b" }}>
              {summary.pending}
            </div>
          </div>
          <div
            style={{
              padding: "1.25rem",
              backgroundColor: "var(--bg-card, #1e293b)",
              borderRadius: "0.75rem",
              border: "1px solid rgba(34, 197, 94, 0.3)",
            }}
          >
            <div style={{ fontSize: "0.75rem", color: "#22c55e", textTransform: "uppercase", fontWeight: 600 }}>
              Approved
            </div>
            <div style={{ fontSize: "1.5rem", fontWeight: 700, marginTop: "0.25rem", color: "#22c55e" }}>
              {summary.approved}
            </div>
          </div>
          <div
            style={{
              padding: "1.25rem",
              backgroundColor: "var(--bg-card, #1e293b)",
              borderRadius: "0.75rem",
              border: "1px solid rgba(239, 68, 68, 0.3)",
            }}
          >
            <div style={{ fontSize: "0.75rem", color: "#ef4444", textTransform: "uppercase", fontWeight: 600 }}>
              Denied
            </div>
            <div style={{ fontSize: "1.5rem", fontWeight: 700, marginTop: "0.25rem", color: "#ef4444" }}>
              {summary.denied}
            </div>
          </div>
        </div>

        {/* Filter Bar */}
        <div
          style={{
            display: "flex",
            gap: "1rem",
            marginBottom: "1rem",
            flexWrap: "wrap",
            alignItems: "center",
          }}
        >
          <div style={{ position: "relative", flex: 1, minWidth: "240px" }}>
            <span
              style={{
                position: "absolute",
                left: "0.75rem",
                top: "50%",
                transform: "translateY(-50%)",
                color: "var(--text-muted, #94a3b8)",
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
                padding: "0.625rem 0.75rem 0.625rem 2.25rem",
                backgroundColor: "var(--bg-card, #1e293b)",
                border: "1px solid var(--border-color, #334155)",
                borderRadius: "0.375rem",
                color: "var(--text-primary, #f8fafc)",
                fontSize: "0.875rem",
                outline: "none",
                boxSizing: "border-box",
              }}
            />
          </div>

          <div style={{ minWidth: "160px" }}>
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
                padding: "0.625rem 0.75rem",
                backgroundColor: "var(--bg-card, #1e293b)",
                border: "1px solid var(--border-color, #334155)",
                borderRadius: "0.375rem",
                color: "var(--text-primary, #f8fafc)",
                fontSize: "0.875rem",
                outline: "none",
                boxSizing: "border-box",
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
              padding: "0.625rem",
              backgroundColor: "var(--bg-card, #1e293b)",
              border: "1px solid var(--border-color, #334155)",
              borderRadius: "0.375rem",
              color: "var(--text-muted, #94a3b8)",
              cursor: "pointer",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
            }}
          >
            <RotateCcwIcon size={16} />
          </button>
        </div>

        {/* Content Table */}
        <div
          style={{
            backgroundColor: "var(--bg-card, #1e293b)",
            borderRadius: "0.75rem",
            border: "1px solid var(--border-color, #334155)",
            overflow: "hidden",
          }}
        >
          {isLoading ? (
            <div style={{ padding: "3rem", textAlign: "center", color: "var(--text-muted, #94a3b8)" }}>
              Loading access requests...
            </div>
          ) : errorMessage ? (
            <div
              style={{
                padding: "3rem",
                textAlign: "center",
                color: "#ef4444",
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                gap: "0.75rem",
              }}
            >
              <AlertCircleIcon size={24} />
              <span>{errorMessage}</span>
              <button
                onClick={fetchRequests}
                style={{
                  padding: "0.5rem 1rem",
                  backgroundColor: "var(--color-primary, #6366f1)",
                  color: "#ffffff",
                  border: "none",
                  borderRadius: "0.375rem",
                  cursor: "pointer",
                }}
              >
                Try Again
              </button>
            </div>
          ) : requests.length === 0 ? (
            <div style={{ padding: "3rem", textAlign: "center", color: "var(--text-muted, #94a3b8)" }}>
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
                      borderBottom: "1px solid var(--border-color, #334155)",
                      backgroundColor: "rgba(15, 23, 42, 0.4)",
                    }}
                  >
                    <th style={{ padding: "0.875rem 1rem", fontWeight: 600 }}>Requester</th>
                    <th style={{ padding: "0.875rem 1rem", fontWeight: 600 }}>Organization</th>
                    <th style={{ padding: "0.875rem 1rem", fontWeight: 600 }}>Product</th>
                    <th style={{ padding: "0.875rem 1rem", fontWeight: 600 }}>Requested At</th>
                    <th style={{ padding: "0.875rem 1rem", fontWeight: 600 }}>Status</th>
                    <th style={{ padding: "0.875rem 1rem", fontWeight: 600 }}>Reason / Decision</th>
                    <th style={{ padding: "0.875rem 1rem", fontWeight: 600, textAlign: "right" }}>
                      Actions
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {requests.map((req) => {
                    const isRequesterSelf = user?.id === req.requester_id;
                    const latestDecision = req.decisions?.[0];

                    return (
                      <tr
                        key={req.id}
                        style={{
                          borderBottom: "1px solid var(--border-color, #334155)",
                        }}
                      >
                        <td style={{ padding: "0.875rem 1rem" }}>
                          <div style={{ fontWeight: 500 }}>{req.requester_name || "User"}</div>
                          <div style={{ fontSize: "0.75rem", color: "var(--text-muted, #94a3b8)" }}>
                            {req.requester_email}
                          </div>
                        </td>
                        <td style={{ padding: "0.875rem 1rem" }}>
                          {req.organization_name || req.organization_code || "—"}
                        </td>
                        <td style={{ padding: "0.875rem 1rem" }}>
                          <div style={{ fontWeight: 500 }}>{req.product_name || req.product_code || "—"}</div>
                        </td>
                        <td style={{ padding: "0.875rem 1rem", color: "var(--text-muted, #94a3b8)" }}>
                          {formatDateTime(req.requested_at)}
                        </td>
                        <td style={{ padding: "0.875rem 1rem" }}>{getStatusBadge(req.status)}</td>
                        <td
                          style={{
                            padding: "0.875rem 1rem",
                            maxWidth: "250px",
                            overflow: "hidden",
                            textOverflow: "ellipsis",
                            whiteSpace: "nowrap",
                          }}
                          title={latestDecision?.reason || req.reason}
                        >
                          {latestDecision?.reason ? (
                            <span>
                              <strong>Decision:</strong> {latestDecision.reason}
                            </span>
                          ) : req.reason ? (
                            <span>{req.reason}</span>
                          ) : (
                            <span style={{ color: "var(--text-muted, #94a3b8)" }}>—</span>
                          )}
                        </td>
                        <td style={{ padding: "0.875rem 1rem", textAlign: "right" }}>
                          {req.status === "pending" && (
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
                                      padding: "0.375rem 0.625rem",
                                      backgroundColor: "#22c55e",
                                      color: "#ffffff",
                                      border: "none",
                                      borderRadius: "0.25rem",
                                      fontSize: "0.75rem",
                                      fontWeight: 600,
                                      cursor: "pointer",
                                    }}
                                  >
                                    Approve
                                  </button>
                                  <button
                                    type="button"
                                    onClick={(e) => handleOpenDeny(req, e)}
                                    style={{
                                      padding: "0.375rem 0.625rem",
                                      backgroundColor: "#ef4444",
                                      color: "#ffffff",
                                      border: "none",
                                      borderRadius: "0.25rem",
                                      fontSize: "0.75rem",
                                      fontWeight: 600,
                                      cursor: "pointer",
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
                                    padding: "0.375rem 0.625rem",
                                    backgroundColor: "transparent",
                                    color: "var(--text-muted, #94a3b8)",
                                    border: "1px solid var(--border-color, #334155)",
                                    borderRadius: "0.25rem",
                                    fontSize: "0.75rem",
                                    fontWeight: 500,
                                    cursor: "pointer",
                                  }}
                                >
                                  Cancel
                                </button>
                              )}
                            </div>
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
                padding: "0.875rem 1rem",
                borderTop: "1px solid var(--border-color, #334155)",
                fontSize: "0.875rem",
                color: "var(--text-secondary, #94a3b8)",
                flexWrap: "wrap",
                gap: "0.5rem",
              }}
            >
              <div>
                Showing {(page - 1) * pageSize + 1} to{" "}
                {Math.min(page * pageSize, totalCount)} of {totalCount} requests
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                <button
                  type="button"
                  disabled={page <= 1}
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  aria-label="Previous Page"
                  style={{
                    padding: "0.375rem 0.625rem",
                    backgroundColor: "transparent",
                    border: "1px solid var(--border-color, #334155)",
                    borderRadius: "0.25rem",
                    color: "inherit",
                    cursor: page <= 1 ? "not-allowed" : "pointer",
                    opacity: page <= 1 ? 0.5 : 1,
                  }}
                >
                  <ChevronLeftIcon size={14} />
                </button>
                <span>
                  Page {page} of {totalPages}
                </span>
                <button
                  type="button"
                  disabled={page >= totalPages}
                  onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                  aria-label="Next Page"
                  style={{
                    padding: "0.375rem 0.625rem",
                    backgroundColor: "transparent",
                    border: "1px solid var(--border-color, #334155)",
                    borderRadius: "0.25rem",
                    color: "inherit",
                    cursor: page >= totalPages ? "not-allowed" : "pointer",
                    opacity: page >= totalPages ? 0.5 : 1,
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
