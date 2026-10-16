/**
 * Organization Memberships Management Section.
 *
 * Scoped to a specific organization. Allows Platform Owners to:
 * - View paginated list of memberships with user status and membership status.
 * - Search by user email or name.
 * - Filter by membership status (active, suspended, ended) and role (member, tenant_admin).
 * - Add a user as a member or tenant admin.
 * - Change membership role (member <-> tenant_admin).
 * - Suspend, reactivate, end, and restore memberships with clear confirmations and error display.
 */

import React, { useCallback, useEffect, useRef, useState } from "react";
import { membershipsApi } from "../../api/memberships.ts";
import type {
  MembershipStatus,
  MembershipType,
  OrganizationDetail,
  OrganizationMembershipItem,
} from "../../api/types.ts";
import {
  AlertCircleIcon,
  ChevronDownIcon,
  ChevronLeftIcon,
  ChevronRightIcon,
  FilterIcon,
  PlusIcon,
  SearchIcon,
  ShieldCheckIcon,
  UserIcon,
} from "../Icons.tsx";
import { AddMemberDialog } from "./AddMemberDialog.tsx";
import {
  MembershipActionType,
  MembershipLifecycleModal,
} from "./MembershipLifecycleModal.tsx";

interface OrganizationMembersSectionProps {
  readonly organization: OrganizationDetail;
}

export const OrganizationMembersSection: React.FC<OrganizationMembersSectionProps> = ({
  organization,
}) => {
  const [memberships, setMemberships] = useState<readonly OrganizationMembershipItem[]>([]);
  const [totalCount, setTotalCount] = useState<number>(0);
  const [totalPages, setTotalPages] = useState<number>(1);
  const [page, setPage] = useState<number>(1);
  const [pageSize] = useState<number>(15);

  const [search, setSearch] = useState<string>("");
  const [statusFilter, setStatusFilter] = useState<string>("");
  const [roleFilter, setRoleFilter] = useState<string>("");

  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // Dialog & Modal State
  const [isAddOpen, setIsAddOpen] = useState<boolean>(false);
  const [lifecycleModal, setLifecycleModal] = useState<{
    isOpen: boolean;
    membership: OrganizationMembershipItem | null;
    action: MembershipActionType;
  }>({
    isOpen: false,
    membership: null,
    action: "suspend",
  });

  const triggerRef = useRef<HTMLElement | null>(null);

  const fetchMemberships = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const res = await membershipsApi.list(organization.id, {
        page,
        page_size: pageSize,
        search: search.trim() || undefined,
        status: (statusFilter as MembershipStatus) || undefined,
        membership_type: (roleFilter as MembershipType) || undefined,
        ordering: "-created_at",
      });
      setMemberships(res.results);
      setTotalCount(res.count);
      setTotalPages(Math.max(1, Math.ceil(res.count / pageSize)));
    } catch {
      setError("Unable to load organization memberships. Please try again.");
    } finally {
      setIsLoading(false);
    }
  }, [organization.id, page, pageSize, search, statusFilter, roleFilter]);

  useEffect(() => {
    fetchMemberships();
  }, [fetchMemberships]);

  const handleSearchChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setSearch(e.target.value);
    setPage(1);
  };

  const handleStatusChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    setStatusFilter(e.target.value);
    setPage(1);
  };

  const handleRoleChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    setRoleFilter(e.target.value);
    setPage(1);
  };

  const openLifecycleModal = (
    membership: OrganizationMembershipItem,
    action: MembershipActionType,
    e: React.MouseEvent<HTMLElement>
  ) => {
    triggerRef.current = e.currentTarget;
    setLifecycleModal({
      isOpen: true,
      membership,
      action,
    });
  };

  const closeLifecycleModal = () => {
    setLifecycleModal((prev) => ({ ...prev, isOpen: false }));
  };

  const formatDate = (isoString?: string | null) => {
    if (!isoString) return "—";
    try {
      return new Date(isoString).toLocaleDateString("en-US", {
        year: "numeric",
        month: "short",
        day: "numeric",
      });
    } catch {
      return isoString;
    }
  };

  const getStatusBadgeStyle = (status: MembershipStatus) => {
    switch (status) {
      case "active":
        return {
          bg: "rgba(16, 185, 129, 0.12)",
          color: "rgb(5, 150, 105)",
          border: "rgba(16, 185, 129, 0.25)",
        };
      case "suspended":
        return {
          bg: "rgba(245, 158, 11, 0.12)",
          color: "rgb(217, 119, 6)",
          border: "rgba(245, 158, 11, 0.25)",
        };
      case "ended":
        return {
          bg: "rgba(239, 68, 68, 0.12)",
          color: "rgb(220, 38, 38)",
          border: "rgba(239, 68, 68, 0.25)",
        };
      default:
        return {
          bg: "rgba(156, 163, 175, 0.12)",
          color: "rgb(107, 114, 128)",
          border: "rgba(156, 163, 175, 0.25)",
        };
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>
      {/* Top Action & Search Bar */}
      <div
        className="registry-page-header"
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          gap: "1rem",
          flexWrap: "wrap",
        }}
      >
        <div className="registry-controls-bar" style={{ flex: "1 1 320px" }}>
          {/* Search Box */}
          <div className="search-input-wrapper">
            <span className="search-icon-adornment" aria-hidden="true">
              <SearchIcon size={16} />
            </span>
            <input
              type="search"
              className="registry-search-input"
              placeholder="Search members by email or name..."
              value={search}
              onChange={handleSearchChange}
              aria-label="Search members"
            />
          </div>

          {/* Status Dropdown Filter */}
          <div className="status-filter-wrapper">
            <span className="filter-icon-adornment" aria-hidden="true">
              <FilterIcon size={15} />
            </span>
            <select
              className="registry-filter-select"
              value={statusFilter}
              onChange={handleStatusChange}
              aria-label="Filter by membership status"
            >
              <option value="">All Statuses</option>
              <option value="active">Active</option>
              <option value="suspended">Suspended</option>
              <option value="ended">Ended</option>
            </select>
            <span className="filter-chevron-adornment" aria-hidden="true">
              <ChevronDownIcon size={15} />
            </span>
          </div>

          {/* Role Dropdown Filter */}
          <div className="status-filter-wrapper">
            <span className="filter-icon-adornment" aria-hidden="true">
              <ShieldCheckIcon size={15} />
            </span>
            <select
              className="registry-filter-select"
              value={roleFilter}
              onChange={handleRoleChange}
              aria-label="Filter by role"
            >
              <option value="">All Roles</option>
              <option value="member">Member</option>
              <option value="tenant_admin">Tenant Admin</option>
            </select>
            <span className="filter-chevron-adornment" aria-hidden="true">
              <ChevronDownIcon size={15} />
            </span>
          </div>
        </div>

        <button
          type="button"
          className="btn btn-primary"
          onClick={(e) => {
            triggerRef.current = e.currentTarget;
            setIsAddOpen(true);
          }}
          style={{ flexShrink: 0 }}
        >
          <PlusIcon size={16} />
          <span>Add Member</span>
        </button>
      </div>

      {/* Error Alert */}
      {error && (
        <div className="alert-banner alert-banner-error" role="alert">
          <AlertCircleIcon size={18} />
          <span>{error}</span>
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            onClick={fetchMemberships}
            style={{ marginLeft: "auto" }}
          >
            Retry
          </button>
        </div>
      )}

      {/* Loading Skeleton */}
      {isLoading && (
        <div className="registry-skeleton-container">
          <div className="skeleton-row" style={{ height: "60px" }} />
          <div className="skeleton-row" style={{ height: "60px" }} />
          <div className="skeleton-row" style={{ height: "60px" }} />
        </div>
      )}

      {/* Memberships Content: Desktop Table & Mobile Cards */}
      {!isLoading && (
        <>
          {memberships.length === 0 ? (
            <div
              style={{
                padding: "3rem 1.5rem",
                textAlign: "center",
                backgroundColor: "var(--glass-surface-elevated)",
                border: "1px solid var(--border-glass)",
                borderRadius: "0.75rem",
              }}
            >
              <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: "0.5rem" }}>
                <UserIcon size={32} style={{ color: "var(--text-muted)", opacity: 0.6 }} />
                <span style={{ fontWeight: 600, color: "var(--text-primary)" }}>No members found</span>
                <p style={{ fontSize: "0.875rem", color: "var(--text-secondary)", margin: 0 }}>
                  {search || statusFilter || roleFilter
                    ? "No memberships match your filter criteria."
                    : "No members have been assigned to this organization yet."}
                </p>
              </div>
            </div>
          ) : (
            <>
              {/* Desktop Table Card View */}
              <div className="members-desktop-table table-card-container">
                <div className="table-card-scroll">
                  <table aria-label="Organization Memberships">
                    <thead>
                      <tr>
                        <th scope="col" style={{ width: "20%", minWidth: "160px" }}>User</th>
                        <th scope="col" style={{ width: "10%", minWidth: "90px" }}>User Status</th>
                        <th scope="col" style={{ width: "12%", minWidth: "110px" }}>Membership Type</th>
                        <th scope="col" style={{ width: "14%", minWidth: "120px" }}>Assigned Role</th>
                        <th scope="col" style={{ width: "12%", minWidth: "110px" }}>Membership Status</th>
                        <th scope="col" style={{ width: "14%", minWidth: "130px" }}>Dates</th>
                        <th scope="col" style={{ textAlign: "center", minWidth: "190px" }}>Actions</th>
                      </tr>
                    </thead>
                  <tbody>
                    {memberships.map((m) => {
                      const badge = getStatusBadgeStyle(m.status);
                      const isUserActive = m.user.status === "active";
                      return (
                        <tr key={m.id}>
                          <td>
                            <div style={{ display: "flex", flexDirection: "column", gap: "0.15rem" }}>
                              <span
                                style={{
                                  fontWeight: 600,
                                  color: "var(--text-primary)",
                                  maxWidth: "220px",
                                  overflow: "hidden",
                                  textOverflow: "ellipsis",
                                  whiteSpace: "nowrap",
                                }}
                                title={m.user.email}
                              >
                                {m.user.email}
                              </span>
                              {m.user.full_name && (
                                <span style={{ fontSize: "0.8125rem", color: "var(--text-secondary)" }}>
                                  {m.user.full_name}
                                </span>
                              )}
                            </div>
                          </td>
                          <td>
                            <span
                              style={{
                                fontSize: "0.75rem",
                                fontWeight: 600,
                                padding: "0.15rem 0.5rem",
                                borderRadius: "9999px",
                                textTransform: "capitalize",
                                backgroundColor: isUserActive
                                  ? "rgba(16, 185, 129, 0.12)"
                                  : "rgba(239, 68, 68, 0.12)",
                                color: isUserActive ? "rgb(5, 150, 105)" : "rgb(220, 38, 38)",
                                border: `1px solid ${
                                  isUserActive
                                    ? "rgba(16, 185, 129, 0.25)"
                                    : "rgba(239, 68, 68, 0.25)"
                                }`,
                              }}
                            >
                              {m.user.status}
                            </span>
                          </td>
                          <td>
                            <span
                              style={{
                                display: "inline-flex",
                                alignItems: "center",
                                gap: "0.3rem",
                                fontSize: "0.8125rem",
                                fontWeight: 600,
                                padding: "0.2rem 0.55rem",
                                borderRadius: "6px",
                                backgroundColor:
                                  m.membership_type === "tenant_admin"
                                    ? "rgba(99, 102, 241, 0.12)"
                                    : "var(--glass-surface)",
                                color:
                                  m.membership_type === "tenant_admin"
                                    ? "rgb(99, 102, 241)"
                                    : "var(--text-secondary)",
                                border:
                                  m.membership_type === "tenant_admin"
                                    ? "1px solid rgba(99, 102, 241, 0.25)"
                                    : "1px solid var(--border-subtle)",
                              }}
                            >
                              {m.membership_type === "tenant_admin" && (
                                <ShieldCheckIcon size={13} />
                              )}
                              {m.membership_type === "tenant_admin" ? "Tenant Admin" : "Member"}
                            </span>
                          </td>
                          <td>
                            {m.membership_type === "tenant_admin" ? (
                              m.role ? (
                                <div style={{ display: "inline-flex", alignItems: "center", gap: "0.35rem" }}>
                                  <span
                                    style={{
                                      fontSize: "0.8125rem",
                                      fontWeight: 600,
                                      color: "var(--text-primary)",
                                    }}
                                  >
                                    {m.role.name}
                                  </span>
                                  <span
                                    style={{
                                      fontSize: "0.6875rem",
                                      padding: "0.1rem 0.35rem",
                                      borderRadius: "4px",
                                      background: m.role.is_system_role
                                        ? "rgba(99, 102, 241, 0.12)"
                                        : "var(--glass-surface)",
                                      color: m.role.is_system_role
                                        ? "rgb(99, 102, 241)"
                                        : "var(--text-secondary)",
                                      border: `1px solid ${
                                        m.role.is_system_role
                                          ? "rgba(99, 102, 241, 0.25)"
                                          : "var(--border-subtle)"
                                      }`,
                                    }}
                                  >
                                    {m.role.is_system_role ? "System" : "Custom"}
                                  </span>
                                </div>
                              ) : (
                                <span
                                  style={{ color: "var(--text-muted)", fontSize: "0.8125rem" }}
                                  title="Role unavailable"
                                >
                                  Role unavailable
                                </span>
                              )
                            ) : (
                              <span style={{ color: "var(--text-muted)", fontSize: "0.8125rem" }}>
                                —
                              </span>
                            )}
                          </td>
                          <td>
                            <span
                              style={{
                                fontSize: "0.75rem",
                                fontWeight: 600,
                                padding: "0.15rem 0.5rem",
                                borderRadius: "9999px",
                                textTransform: "capitalize",
                                backgroundColor: badge.bg,
                                color: badge.color,
                                border: `1px solid ${badge.border}`,
                              }}
                            >
                              {m.status}
                            </span>
                          </td>
                          <td>
                            <div style={{ display: "flex", flexDirection: "column", gap: "0.2rem", fontSize: "0.8125rem" }}>
                              <div>
                                <span style={{ color: "var(--text-muted)", fontSize: "0.75rem", marginRight: "0.25rem" }}>Joined:</span>
                                <span style={{ color: "var(--text-primary)" }}>{formatDate(m.created_at)}</span>
                              </div>
                              {m.ended_at && (
                                <div>
                                  <span style={{ color: "var(--color-error, #ef4444)", fontSize: "0.75rem", marginRight: "0.25rem" }}>Ended:</span>
                                  <span style={{ color: "var(--text-secondary)" }}>{formatDate(m.ended_at)}</span>
                                </div>
                              )}
                            </div>
                          </td>
                          <td style={{ textAlign: "center" }}>
                            <div
                              style={{
                                display: "inline-flex",
                                alignItems: "center",
                                gap: "0.4rem",
                                justifyContent: "center",
                                flexWrap: "wrap",
                              }}
                            >
                              {m.status === "active" && (
                                <>
                                  <button
                                    type="button"
                                    className="btn btn-secondary btn-sm"
                                    onClick={(e) => openLifecycleModal(m, "change_role", e)}
                                    title="Change role between Member and Tenant Admin"
                                  >
                                    Change Role
                                  </button>
                                  <button
                                    type="button"
                                    className="btn btn-secondary btn-sm"
                                    onClick={(e) => openLifecycleModal(m, "suspend", e)}
                                  >
                                    Suspend
                                  </button>
                                  <button
                                    type="button"
                                    className="btn btn-secondary btn-sm"
                                    style={{ color: "var(--color-error, #ef4444)" }}
                                    onClick={(e) => openLifecycleModal(m, "end", e)}
                                  >
                                    End
                                  </button>
                                </>
                              )}

                              {m.status === "suspended" && (
                                <>
                                  <button
                                    type="button"
                                    className="btn btn-secondary btn-sm"
                                    onClick={(e) => openLifecycleModal(m, "reactivate", e)}
                                  >
                                    Reactivate
                                  </button>
                                  <button
                                    type="button"
                                    className="btn btn-secondary btn-sm"
                                    style={{ color: "var(--color-error, #ef4444)" }}
                                    onClick={(e) => openLifecycleModal(m, "end", e)}
                                  >
                                    End
                                  </button>
                                </>
                              )}

                              {m.status === "ended" && (
                                <button
                                  type="button"
                                  className="btn btn-secondary btn-sm"
                                  onClick={(e) => openLifecycleModal(m, "restore", e)}
                                >
                                  Restore
                                </button>
                              )}
                            </div>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>

              {/* Mobile Cards View (<768px) */}
              <div className="members-mobile-cards">
                {memberships.map((m) => {
                  const badge = getStatusBadgeStyle(m.status);
                  const isUserActive = m.user.status === "active";
                  return (
                    <div
                      key={`card-${m.id}`}
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
                              wordBreak: "break-word",
                              overflowWrap: "anywhere",
                            }}
                            title={m.user.email}
                          >
                            {m.user.email}
                          </div>
                          {m.user.full_name && (
                            <div style={{ fontSize: "0.8125rem", color: "var(--text-secondary)", marginTop: "0.15rem", wordBreak: "break-word", overflowWrap: "anywhere" }}>
                              {m.user.full_name}
                            </div>
                          )}
                        </div>
                        <span
                          style={{
                            fontSize: "0.75rem",
                            fontWeight: 600,
                            padding: "0.15rem 0.5rem",
                            borderRadius: "9999px",
                            textTransform: "capitalize",
                            backgroundColor: badge.bg,
                            color: badge.color,
                            border: `1px solid ${badge.border}`,
                            flexShrink: 0,
                          }}
                        >
                          {m.status}
                        </span>
                      </div>

                      <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem", alignItems: "center" }}>
                        <span
                          style={{
                            fontSize: "0.75rem",
                            fontWeight: 600,
                            padding: "0.15rem 0.5rem",
                            borderRadius: "9999px",
                            textTransform: "capitalize",
                            backgroundColor: isUserActive
                              ? "rgba(16, 185, 129, 0.12)"
                              : "rgba(239, 68, 68, 0.12)",
                            color: isUserActive ? "rgb(5, 150, 105)" : "rgb(220, 38, 38)",
                            border: `1px solid ${
                              isUserActive
                                ? "rgba(16, 185, 129, 0.25)"
                                : "rgba(239, 68, 68, 0.25)"
                            }`,
                          }}
                        >
                          User: {m.user.status}
                        </span>

                        <span
                          style={{
                            display: "inline-flex",
                            alignItems: "center",
                            gap: "0.25rem",
                            fontSize: "0.75rem",
                            fontWeight: 600,
                            padding: "0.15rem 0.5rem",
                            borderRadius: "6px",
                            backgroundColor:
                              m.membership_type === "tenant_admin"
                                ? "rgba(99, 102, 241, 0.12)"
                                : "var(--glass-surface)",
                            color:
                              m.membership_type === "tenant_admin"
                                ? "rgb(99, 102, 241)"
                                : "var(--text-secondary)",
                            border:
                              m.membership_type === "tenant_admin"
                                ? "1px solid rgba(99, 102, 241, 0.25)"
                                : "1px solid var(--border-subtle)",
                          }}
                        >
                          {m.membership_type === "tenant_admin" && <ShieldCheckIcon size={12} />}
                          {m.membership_type === "tenant_admin" ? "Tenant Admin" : "Member"}
                        </span>

                        {m.membership_type === "tenant_admin" && (
                          <div
                            style={{
                              display: "inline-flex",
                              alignItems: "center",
                              gap: "0.3rem",
                              fontSize: "0.75rem",
                              color: "var(--text-secondary)",
                              padding: "0.15rem 0.45rem",
                              borderRadius: "6px",
                              background: "rgba(0, 0, 0, 0.15)",
                            }}
                          >
                            <span>Role: <strong>{m.role ? m.role.name : "Role unavailable"}</strong></span>
                            {m.role && (
                              <span
                                style={{
                                  fontSize: "0.625rem",
                                  padding: "0.05rem 0.25rem",
                                  borderRadius: "3px",
                                  background: m.role.is_system_role
                                    ? "rgba(99, 102, 241, 0.15)"
                                    : "var(--glass-surface)",
                                  color: m.role.is_system_role
                                    ? "rgb(99, 102, 241)"
                                    : "var(--text-muted)",
                                }}
                              >
                                {m.role.is_system_role ? "System" : "Custom"}
                              </span>
                            )}
                          </div>
                        )}
                      </div>

                      <div style={{ fontSize: "0.8125rem", display: "flex", flexDirection: "column", gap: "0.2rem" }}>
                        <div>
                          <span style={{ color: "var(--text-muted)", marginRight: "0.35rem" }}>Joined:</span>
                          <span style={{ color: "var(--text-primary)" }}>{formatDate(m.created_at)}</span>
                        </div>
                        {m.ended_at && (
                          <div>
                            <span style={{ color: "var(--color-error, #ef4444)", marginRight: "0.35rem" }}>Ended:</span>
                            <span style={{ color: "var(--text-secondary)" }}>{formatDate(m.ended_at)}</span>
                          </div>
                        )}
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
                        {m.status === "active" && (
                          <>
                            <button
                              type="button"
                              className="btn btn-secondary btn-sm"
                              style={{ minHeight: "44px", display: "inline-flex", alignItems: "center" }}
                              onClick={(e) => openLifecycleModal(m, "change_role", e)}
                            >
                              Change Role
                            </button>
                            <button
                              type="button"
                              className="btn btn-secondary btn-sm"
                              style={{ minHeight: "44px", display: "inline-flex", alignItems: "center" }}
                              onClick={(e) => openLifecycleModal(m, "suspend", e)}
                            >
                              Suspend
                            </button>
                            <button
                              type="button"
                              className="btn btn-secondary btn-sm"
                              style={{ minHeight: "44px", display: "inline-flex", alignItems: "center", color: "var(--color-error, #ef4444)" }}
                              onClick={(e) => openLifecycleModal(m, "end", e)}
                            >
                              End
                            </button>
                          </>
                        )}

                        {m.status === "suspended" && (
                          <>
                            <button
                              type="button"
                              className="btn btn-secondary btn-sm"
                              style={{ minHeight: "44px", display: "inline-flex", alignItems: "center" }}
                              onClick={(e) => openLifecycleModal(m, "reactivate", e)}
                            >
                              Reactivate
                            </button>
                            <button
                              type="button"
                              className="btn btn-secondary btn-sm"
                              style={{ minHeight: "44px", display: "inline-flex", alignItems: "center", color: "var(--color-error, #ef4444)" }}
                              onClick={(e) => openLifecycleModal(m, "end", e)}
                            >
                              End
                            </button>
                          </>
                        )}

                        {m.status === "ended" && (
                          <button
                            type="button"
                            className="btn btn-secondary btn-sm"
                            style={{ minHeight: "44px", display: "inline-flex", alignItems: "center" }}
                            onClick={(e) => openLifecycleModal(m, "restore", e)}
                          >
                            Restore
                          </button>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            </>
          )}
        </>
      )}

      {/* Pagination Footer */}
      {!isLoading && totalPages > 1 && (
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            marginTop: "0.5rem",
            fontSize: "0.875rem",
            color: "var(--text-secondary)",
          }}
        >
          <span>
            Showing {(page - 1) * pageSize + 1}–
            {Math.min(page * pageSize, totalCount)} of {totalCount} memberships
          </span>

          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              disabled={page <= 1}
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              aria-label="Previous Page"
            >
              <ChevronLeftIcon size={14} />
            </button>
            <span>
              Page {page} of {totalPages}
            </span>
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              disabled={page >= totalPages}
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              aria-label="Next Page"
            >
              <ChevronRightIcon size={14} />
            </button>
          </div>
        </div>
      )}

      {/* Add Member Dialog */}
      <AddMemberDialog
        isOpen={isAddOpen}
        onClose={() => setIsAddOpen(false)}
        onSuccess={fetchMemberships}
        organizationId={organization.id}
        organizationName={organization.name}
        triggerRef={triggerRef}
      />

      {/* Lifecycle / Action Confirmation Modal */}
      {lifecycleModal.membership && (
        <MembershipLifecycleModal
          isOpen={lifecycleModal.isOpen}
          onClose={closeLifecycleModal}
          onSuccess={fetchMemberships}
          organizationId={organization.id}
          membership={lifecycleModal.membership}
          action={lifecycleModal.action}
          triggerRef={triggerRef}
        />
      )}

      <style>{`
        .members-mobile-cards {
          display: none;
        }
        @media (max-width: 767px) {
          .members-desktop-table {
            display: none !important;
          }
          .members-mobile-cards {
            display: flex !important;
            flex-direction: column;
            gap: 0.75rem;
          }
        }
      `}</style>
    </div>
  );
};
