/**
 * Platform Owner Central Users List Page (Phase 2D Stage 5).
 *
 * Provides Platform Owners with comprehensive central user inventory:
 * - Server-side search with debounce
 * - Lifecycle status filtering (active, suspended, disabled)
 * - Deterministic sorting
 * - Bounded pagination
 * - Direct lifecycle actions (Suspend, Reactivate, Disable)
 */

import React, { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { usersApi } from "../../api/users.ts";
import type {
  UserDetail,
  UserListItem,
  UserListParams,
  UserStatus,
} from "../../api/types.ts";
import { AppShell } from "../../components/AppShell.tsx";
import {
  ChevronDownIcon,
  FilterIcon,
  PlusIcon,
  SearchIcon,
  ShieldCheckIcon,
  UserIcon,
} from "../../components/Icons.tsx";
import { LoadingSpinner } from "../../components/LoadingSpinner.tsx";
import { formatDateTime } from "../../config/dateUtils.ts";
import { CreateUserDialog } from "../../components/users/CreateUserDialog.tsx";
import { InviteUserDialog } from "../../components/users/InviteUserDialog.tsx";
import {
  UserLifecycleAction,
  UserLifecycleModal,
} from "../../components/users/UserLifecycleModal.tsx";

export const CentralUsersListPage: React.FC = () => {
  const navigate = useNavigate();

  const [users, setUsers] = useState<UserListItem[]>([]);
  const [totalCount, setTotalCount] = useState<number>(0);
  const [page, setPage] = useState<number>(1);
  const pageSize = 10;

  const [searchInput, setSearchInput] = useState<string>("");
  const [debouncedSearch, setDebouncedSearch] = useState<string>("");
  const [statusFilter, setStatusFilter] = useState<string>("");
  const [ordering, setOrdering] = useState<string>("-created_at");

  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // Dialog & Modal States
  const [isCreateOpen, setIsCreateOpen] = useState<boolean>(false);
  const [isInviteOpen, setIsInviteOpen] = useState<boolean>(false);
  const [selectedUser, setSelectedUser] = useState<UserListItem | null>(null);
  const [lifecycleAction, setLifecycleAction] = useState<UserLifecycleAction | null>(null);
  const triggerRef = useRef<HTMLButtonElement | null>(null);

  const requestSeqRef = useRef<number>(0);

  // Debounce search input (300ms)
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearch(searchInput.trim());
      setPage(1);
    }, 300);
    return () => clearTimeout(timer);
  }, [searchInput]);

  const fetchUsers = useCallback(async () => {
    const currentSeq = ++requestSeqRef.current;
    setIsLoading(true);
    setError(null);

    try {
      const params: UserListParams = {
        page,
        page_size: pageSize,
        search: debouncedSearch || undefined,
        status: (statusFilter as UserStatus) || undefined,
        ordering: ordering || undefined,
      };

      const response = await usersApi.list(params);

      if (currentSeq === requestSeqRef.current) {
        setUsers(response.results as UserListItem[]);
        setTotalCount(response.count);
        setIsLoading(false);
      }
    } catch {
      if (currentSeq === requestSeqRef.current) {
        setIsLoading(false);
        setError("Unable to load central users. Please check your connection and try again.");
      }
    }
  }, [page, debouncedSearch, statusFilter, ordering]);

  useEffect(() => {
    fetchUsers();
  }, [fetchUsers]);

  const handleUserCreated = (_user: UserDetail) => {
    void _user;
    fetchUsers();
  };

  const handleLifecycleSuccess = (_user: UserDetail) => {
    void _user;
    fetchUsers();
  };

  const openLifecycleModal = (user: UserListItem, action: UserLifecycleAction) => {
    setSelectedUser(user);
    setLifecycleAction(action);
  };

  const getStatusBadge = (statusVal: UserStatus) => {
    const styles: Record<UserStatus, { bg: string; color: string; border: string; label: string }> = {
      active: {
        bg: "rgba(16, 185, 129, 0.12)",
        color: "rgb(5, 150, 105)",
        border: "rgba(16, 185, 129, 0.25)",
        label: "Active",
      },
      suspended: {
        bg: "rgba(245, 158, 11, 0.12)",
        color: "rgb(217, 119, 6)",
        border: "rgba(245, 158, 11, 0.25)",
        label: "Suspended",
      },
      disabled: {
        bg: "rgba(239, 68, 68, 0.12)",
        color: "rgb(220, 38, 38)",
        border: "rgba(239, 68, 68, 0.25)",
        label: "Disabled",
      },
    };
    const s = styles[statusVal] || styles.active;
    return (
      <span
        style={{
          display: "inline-flex",
          alignItems: "center",
          padding: "0.2rem 0.6rem",
          borderRadius: "9999px",
          fontSize: "0.75rem",
          fontWeight: 600,
          backgroundColor: s.bg,
          color: s.color,
          border: `1px solid ${s.border}`,
          textTransform: "capitalize",
        }}
      >
        {s.label}
      </span>
    );
  };

  const totalPages = Math.ceil(totalCount / pageSize) || 1;

  return (
    <AppShell>
      <div style={{ display: "flex", flexDirection: "column", gap: "1.75rem" }}>
        {/* Breadcrumbs */}
        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", fontSize: "0.8125rem", color: "var(--text-muted)" }}>
          <span>Platform Owner</span>
          <span>/</span>
          <span>Customer Operations</span>
          <span>/</span>
          <span style={{ color: "var(--brand-primary, #3867f5)", fontWeight: 600 }}>Central Users Directory</span>
        </div>

        {/* Page Header */}
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            flexWrap: "wrap",
            gap: "1.25rem",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: "1rem" }}>
            <div
              style={{
                width: "48px",
                height: "48px",
                borderRadius: "14px",
                background: "linear-gradient(135deg, rgba(56, 103, 245, 0.15) 0%, rgba(138, 69, 246, 0.15) 100%)",
                border: "1px solid rgba(56, 103, 245, 0.25)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                color: "var(--brand-primary, #3867f5)",
                flexShrink: 0,
              }}
            >
              <UserIcon size={24} />
            </div>
            <div>
              <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", flexWrap: "wrap" }}>
                <h1 style={{ margin: 0, fontSize: "1.625rem", fontWeight: 800, color: "var(--text-primary)", letterSpacing: "-0.02em" }}>
                  Central Users Directory
                </h1>
                {!isLoading && (
                  <span
                    style={{
                      fontSize: "0.75rem",
                      fontWeight: 700,
                      padding: "0.2rem 0.65rem",
                      borderRadius: "9999px",
                      background: "rgba(56, 103, 245, 0.1)",
                      border: "1px solid rgba(56, 103, 245, 0.22)",
                      color: "var(--brand-primary, #3867f5)",
                    }}
                  >
                    {totalCount} {totalCount === 1 ? "User" : "Users"}
                  </span>
                )}
              </div>
              <p style={{ margin: "0.25rem 0 0 0", color: "var(--text-secondary)", fontSize: "0.875rem", lineHeight: 1.5 }}>
                Directory of all centralized user identities and credentials across Envisage platform.
              </p>
            </div>
          </div>

          <div style={{ display: "flex", gap: "0.75rem", alignItems: "center", flexWrap: "wrap" }}>
            <button
              type="button"
              className="btn btn-secondary"
              onClick={() => setIsInviteOpen(true)}
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: "0.5rem",
                padding: "0.6rem 1.15rem",
                borderRadius: "10px",
                fontWeight: 600,
                fontSize: "0.875rem",
                border: "1px solid var(--border-color, rgba(255,255,255,0.12))",
                background: "transparent",
                color: "var(--text-primary)",
                cursor: "pointer",
              }}
            >
              <UserIcon size={16} />
              <span>Invite User</span>
            </button>
            <button
              ref={triggerRef}
              type="button"
              className="btn-gradient"
              onClick={() => setIsCreateOpen(true)}
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: "0.5rem",
                background: "linear-gradient(135deg, #3867f5 0%, #2952cc 100%)",
                border: "none",
                color: "#ffffff",
                boxShadow: "0 4px 14px rgba(56, 103, 245, 0.3)",
                borderRadius: "10px",
                padding: "0.65rem 1.35rem",
                fontWeight: 700,
                fontSize: "0.875rem",
                cursor: "pointer",
              }}
            >
              <PlusIcon size={16} />
              <span>Create User</span>
            </button>
          </div>
        </div>

        {/* Search & Filter Toolbar */}
        <div className="registry-controls-bar">
          {/* Search Box */}
          <div className="search-input-wrapper">
            <span className="search-icon-adornment" aria-hidden="true">
              <SearchIcon size={16} />
            </span>
            <input
              type="search"
              className="registry-search-input"
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              placeholder="Search by email or name..."
              aria-label="Search users"
            />
          </div>

          {/* Status Filter */}
          <div className="status-filter-wrapper">
            <span className="filter-icon-adornment" aria-hidden="true">
              <FilterIcon size={15} />
            </span>
            <select
              className="registry-filter-select"
              value={statusFilter}
              onChange={(e) => {
                setStatusFilter(e.target.value);
                setPage(1);
              }}
              aria-label="Filter by user status"
            >
              <option value="">All Statuses</option>
              <option value="active">Active</option>
              <option value="suspended">Suspended</option>
              <option value="disabled">Disabled</option>
            </select>
            <span className="filter-chevron-adornment" aria-hidden="true">
              <ChevronDownIcon size={15} />
            </span>
          </div>

          {/* Ordering */}
          <div className="ordering-select-wrapper">
            <select
              className="registry-filter-select"
              value={ordering}
              onChange={(e) => {
                setOrdering(e.target.value);
                setPage(1);
              }}
              aria-label="Sort users"
            >
              <option value="-created_at">Newest First</option>
              <option value="created_at">Oldest First</option>
              <option value="email">Email (A-Z)</option>
              <option value="-email">Email (Z-A)</option>
              <option value="full_name">Name (A-Z)</option>
            </select>
            <span className="filter-chevron-adornment" aria-hidden="true">
              <ChevronDownIcon size={15} />
            </span>
          </div>
        </div>

        {/* Error Alert */}
        {error && (
          <div className="alert-banner alert-banner-error" role="alert">
            <span>{error}</span>
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              onClick={fetchUsers}
              style={{ marginLeft: "auto" }}
            >
              Retry
            </button>
          </div>
        )}

        {/* Content Table / Cards */}
        {isLoading ? (
          <div style={{ padding: "3rem 0", display: "flex", justifyContent: "center" }}>
            <LoadingSpinner label="Loading central users..." />
          </div>
        ) : users.length === 0 ? (
          <div
            style={{
              padding: "3rem 1.5rem",
              textAlign: "center",
              backgroundColor: "var(--glass-surface-elevated)",
              border: "1px solid var(--border-glass)",
              borderRadius: "0.75rem",
            }}
          >
            <div style={{ color: "var(--text-muted)", marginBottom: "0.75rem" }}>
              <UserIcon size={36} />
            </div>
            <h3 style={{ margin: "0 0 0.5rem 0", fontSize: "1.125rem", color: "var(--text-primary)" }}>
              No users found
            </h3>
            <p style={{ margin: 0, color: "var(--text-secondary)", fontSize: "0.875rem" }}>
              {debouncedSearch || statusFilter
                ? "Try adjusting your search or status filter."
                : "Get started by creating the first platform user."}
            </p>
          </div>
        ) : (
          <>
            {/* Desktop Table View */}
            <div
              className="users-desktop-table"
              style={{
                backgroundColor: "var(--glass-surface-elevated)",
                border: "1px solid var(--border-glass)",
                borderRadius: "0.75rem",
                overflow: "hidden",
              }}
            >
              <div style={{ overflowX: "auto" }}>
                <table
                  style={{
                    width: "100%",
                    borderCollapse: "collapse",
                    textAlign: "left",
                    fontSize: "0.875rem",
                  }}
                >
                  <thead>
                    <tr
                      style={{
                        borderBottom: "1px solid var(--border-subtle)",
                        backgroundColor: "var(--glass-surface)",
                        color: "var(--text-secondary)",
                        fontSize: "0.75rem",
                        textTransform: "uppercase",
                        letterSpacing: "0.05em",
                      }}
                    >
                      <th style={{ padding: "0.75rem 1rem", minWidth: "200px" }}>User</th>
                      <th style={{ padding: "0.75rem 1rem", minWidth: "100px" }}>Status</th>
                      <th style={{ padding: "0.75rem 1rem", minWidth: "130px" }}>Role</th>
                      <th style={{ padding: "0.75rem 1rem", minWidth: "170px" }}>Created At</th>
                      <th style={{ padding: "0.75rem 1rem", textAlign: "center", minWidth: "220px" }}>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {users.map((u) => (
                      <tr
                        key={u.id}
                        style={{
                          borderBottom: "1px solid var(--border-subtle)",
                          transition: "background-color 0.15s ease",
                        }}
                        className="table-row-hover"
                      >
                        <td style={{ padding: "0.95rem 1rem" }}>
                          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                            <div
                              style={{
                                width: 38,
                                height: 38,
                                borderRadius: "50%",
                                background: "linear-gradient(135deg, rgba(56, 103, 245, 0.12), rgba(138, 69, 246, 0.18))",
                                color: "var(--brand-primary, #3867F5)",
                                display: "flex",
                                alignItems: "center",
                                justifyContent: "center",
                                fontWeight: 700,
                                fontSize: "0.82rem",
                                flexShrink: 0,
                                border: "1px solid rgba(56, 103, 245, 0.15)",
                              }}
                            >
                              {((u.full_name || u.email || "U").substring(0, 2)).toUpperCase()}
                            </div>
                            <div>
                              <div
                                style={{
                                  fontWeight: 650,
                                  color: "var(--text-primary)",
                                  maxWidth: "240px",
                                  overflow: "hidden",
                                  textOverflow: "ellipsis",
                                  whiteSpace: "nowrap",
                                }}
                                title={u.email}
                              >
                                {u.email}
                              </div>
                              {u.full_name && (
                                <div style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>
                                  {u.full_name}
                                </div>
                              )}
                            </div>
                          </div>
                        </td>
                        <td style={{ padding: "1rem" }}>{getStatusBadge(u.status)}</td>
                        <td style={{ padding: "1rem" }}>
                          {u.is_platform_owner ? (
                            <span
                              style={{
                                display: "inline-flex",
                                alignItems: "center",
                                gap: "0.25rem",
                                fontSize: "0.75rem",
                                fontWeight: 600,
                                color: "var(--color-primary, #3b82f6)",
                              }}
                            >
                              <ShieldCheckIcon size={14} />
                              Platform Owner
                            </span>
                          ) : (
                            <span style={{ fontSize: "0.8125rem", color: "var(--text-secondary)" }}>
                              Standard User
                            </span>
                          )}
                        </td>
                        <td
                          style={{ padding: "1rem", color: "var(--text-secondary)", whiteSpace: "nowrap" }}
                          title={u.created_at}
                        >
                          {formatDateTime(u.created_at)}
                        </td>
                        <td style={{ padding: "1rem", textAlign: "center", minWidth: "220px" }}>
                          <div style={{ display: "inline-flex", gap: "0.5rem", alignItems: "center", justifyContent: "center" }}>
                            <button
                              type="button"
                              className="btn btn-secondary btn-sm"
                              onClick={() => navigate(`/users/${u.id}`)}
                            >
                              View
                            </button>

                            {u.status === "active" && (
                              <button
                                type="button"
                                className="btn btn-secondary btn-sm"
                                onClick={() => openLifecycleModal(u, "suspend")}
                              >
                                Suspend
                              </button>
                            )}

                            {u.status === "suspended" && (
                              <button
                                type="button"
                                className="btn btn-secondary btn-sm"
                                onClick={() => openLifecycleModal(u, "reactivate")}
                              >
                                Reactivate
                              </button>
                            )}

                            {u.status !== "disabled" && (
                              <button
                                type="button"
                                className="btn btn-danger btn-sm"
                                onClick={() => openLifecycleModal(u, "disable")}
                              >
                                Disable
                              </button>
                            )}
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {/* Pagination Footer */}
              {totalPages > 1 && (
                <div
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    padding: "0.75rem 1rem",
                    borderTop: "1px solid var(--border-subtle)",
                    fontSize: "0.875rem",
                    color: "var(--text-secondary)",
                  }}
                >
                  <div>
                    Showing {users.length} of {totalCount} users (Page {page} of {totalPages})
                  </div>
                  <div style={{ display: "flex", gap: "0.5rem" }}>
                    <button
                      type="button"
                      className="btn btn-secondary btn-sm"
                      disabled={page <= 1}
                      onClick={() => setPage((p) => Math.max(p - 1, 1))}
                    >
                      Previous
                    </button>
                    <button
                      type="button"
                      className="btn btn-secondary btn-sm"
                      disabled={page >= totalPages}
                      onClick={() => setPage((p) => Math.min(p + 1, totalPages))}
                    >
                      Next
                    </button>
                  </div>
                </div>
              )}
            </div>

            {/* Mobile Cards View (<768px) */}
            <div className="users-mobile-cards">
              {users.map((u) => (
                <div
                  key={`user-card-${u.id}`}
                  style={{
                    padding: "1rem",
                    borderRadius: "0.75rem",
                    backgroundColor: "var(--glass-surface-elevated)",
                    border: "1px solid var(--border-glass)",
                    display: "flex",
                    flexDirection: "column",
                    gap: "0.75rem",
                  }}
                >
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: "0.5rem" }}>
                    <div style={{ minWidth: 0 }}>
                      <div
                        style={{
                          fontWeight: 600,
                          color: "var(--text-primary)",
                          fontSize: "0.9375rem",
                          wordBreak: "break-all",
                        }}
                      >
                        {u.email}
                      </div>
                      {u.full_name && (
                        <div style={{ fontSize: "0.8125rem", color: "var(--text-secondary)", marginTop: "0.15rem" }}>
                          {u.full_name}
                        </div>
                      )}
                    </div>
                    {getStatusBadge(u.status)}
                  </div>

                  <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem", alignItems: "center" }}>
                    {u.is_platform_owner ? (
                      <span
                        style={{
                          display: "inline-flex",
                          alignItems: "center",
                          gap: "0.25rem",
                          fontSize: "0.75rem",
                          fontWeight: 600,
                          padding: "0.15rem 0.5rem",
                          borderRadius: "6px",
                          backgroundColor: "var(--color-primary-subtle, rgba(59, 130, 246, 0.15))",
                          color: "var(--color-primary, #3b82f6)",
                          border: "1px solid var(--border-subtle)",
                        }}
                      >
                        <ShieldCheckIcon size={12} />
                        Platform Owner
                      </span>
                    ) : (
                      <span
                        style={{
                          fontSize: "0.75rem",
                          color: "var(--text-secondary)",
                          padding: "0.15rem 0.5rem",
                          borderRadius: "6px",
                          backgroundColor: "var(--glass-surface)",
                          border: "1px solid var(--border-subtle)",
                        }}
                      >
                        Standard User
                      </span>
                    )}

                    <span style={{ fontSize: "0.8125rem", color: "var(--text-muted)" }} title={u.created_at}>
                      Created At: {formatDateTime(u.created_at)}
                    </span>
                  </div>

                  <div
                    style={{
                      display: "flex",
                      flexWrap: "wrap",
                      gap: "0.5rem",
                      paddingTop: "0.5rem",
                      borderTop: "1px solid var(--border-subtle)",
                    }}
                  >
                    <button
                      type="button"
                      className="btn btn-secondary btn-sm"
                      onClick={() => navigate(`/users/${u.id}`)}
                      style={{ minHeight: "44px" }}
                    >
                      View Profile
                    </button>

                    {u.status === "active" && (
                      <button
                        type="button"
                        className="btn btn-secondary btn-sm"
                        onClick={() => openLifecycleModal(u, "suspend")}
                        style={{ minHeight: "44px" }}
                      >
                        Suspend
                      </button>
                    )}

                    {u.status === "suspended" && (
                      <button
                        type="button"
                        className="btn btn-secondary btn-sm"
                        onClick={() => openLifecycleModal(u, "reactivate")}
                        style={{ minHeight: "44px" }}
                      >
                        Reactivate
                      </button>
                    )}

                    {u.status !== "disabled" && (
                      <button
                        type="button"
                        className="btn btn-danger btn-sm"
                        onClick={() => openLifecycleModal(u, "disable")}
                        style={{ minHeight: "44px" }}
                      >
                        Disable
                      </button>
                    )}
                  </div>
                </div>
              ))}

              {/* Mobile Pagination */}
              {totalPages > 1 && (
                <div
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    padding: "0.75rem 0",
                    fontSize: "0.875rem",
                    color: "var(--text-secondary)",
                  }}
                >
                  <span>
                    Page {page} of {totalPages}
                  </span>
                  <div style={{ display: "flex", gap: "0.5rem" }}>
                    <button
                      type="button"
                      className="btn btn-secondary btn-sm"
                      disabled={page <= 1}
                      onClick={() => setPage((p) => Math.max(p - 1, 1))}
                    >
                      Prev
                    </button>
                    <button
                      type="button"
                      className="btn btn-secondary btn-sm"
                      disabled={page >= totalPages}
                      onClick={() => setPage((p) => Math.min(p + 1, totalPages))}
                    >
                      Next
                    </button>
                  </div>
                </div>
              )}
            </div>
          </>
        )}

        {/* Modals */}
        <CreateUserDialog
          isOpen={isCreateOpen}
          onClose={() => setIsCreateOpen(false)}
          onSuccess={handleUserCreated}
          triggerRef={triggerRef}
        />

        <InviteUserDialog
          isOpen={isInviteOpen}
          onClose={() => setIsInviteOpen(false)}
          onSuccess={() => fetchUsers()}
        />

        <UserLifecycleModal
          isOpen={lifecycleAction !== null}
          onClose={() => {
            setLifecycleAction(null);
            setSelectedUser(null);
          }}
          onSuccess={handleLifecycleSuccess}
          user={selectedUser}
          action={lifecycleAction}
        />

        <style>{`
          .users-mobile-cards {
            display: none;
          }
          @media (max-width: 767px) {
            .users-desktop-table {
              display: none !important;
            }
            .users-mobile-cards {
              display: flex !important;
              flex-direction: column;
              gap: 0.75rem;
            }
          }
        `}</style>
      </div>
    </AppShell>
  );
};
