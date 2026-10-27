/**
 * Platform Owner Subscriptions Overview & Management Page.
 *
 * Provides Platform Owners with comprehensive subscription inventory overview:
 * - Server-side search with sequence guards
 * - Lifecycle status filtering (trialing, active, suspended, cancelled, expired)
 * - Sorting by creation date, status, and period end
 * - Immutable commercial snapshot presentation
 * - Server-side pagination and responsive desktop table / mobile cards
 */

import React, { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { formatCurrencyDisplay } from "../../api/plans.ts";
import { subscriptionsApi } from "../../api/subscriptions.ts";
import type {
  SubscriptionListItem,
  SubscriptionListParams,
  SubscriptionStatus,
} from "../../api/types.ts";
import { AppShell } from "../../components/AppShell.tsx";
import {
  CalendarIcon,
  ChevronDownIcon,
  CreditCardIcon,
  FilterIcon,
  LayersIcon,
  SearchIcon,
} from "../../components/Icons.tsx";
import { SubscriptionStatusBadge } from "../../components/subscriptions/SubscriptionStatusBadge.tsx";

export const SubscriptionsListPage: React.FC = () => {
  const navigate = useNavigate();

  const [subscriptions, setSubscriptions] = useState<SubscriptionListItem[]>([]);
  const [totalCount, setTotalCount] = useState<number>(0);
  const [page, setPage] = useState<number>(1);
  const pageSize = 10;

  const [searchInput, setSearchInput] = useState<string>("");
  const [debouncedSearch, setDebouncedSearch] = useState<string>("");
  const [statusFilter, setStatusFilter] = useState<string>("");
  const [ordering, setOrdering] = useState<string>("-created_at");

  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [liveAnnouncement, setLiveAnnouncement] = useState<string>("");

  const requestSeqRef = useRef<number>(0);

  // Debounce search input (300ms)
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearch(searchInput.trim());
      setPage(1);
    }, 300);
    return () => clearTimeout(timer);
  }, [searchInput]);

  const handleStatusFilterChange = (newStatus: string) => {
    setStatusFilter(newStatus);
    setPage(1);
  };

  const handleOrderingChange = (newOrdering: string) => {
    setOrdering(newOrdering);
    setPage(1);
  };

  const fetchSubscriptions = useCallback(async () => {
    const currentSeq = ++requestSeqRef.current;
    setIsLoading(true);
    setError(null);
    setLiveAnnouncement("Loading subscriptions inventory...");

    try {
      const params: SubscriptionListParams = {
        page,
        page_size: pageSize,
        search: debouncedSearch || undefined,
        status: (statusFilter as SubscriptionStatus) || undefined,
        ordering: ordering || undefined,
      };

      const response = await subscriptionsApi.list(params);

      if (currentSeq === requestSeqRef.current) {
        setSubscriptions(response.results as SubscriptionListItem[]);
        setTotalCount(response.count);
        setIsLoading(false);
        setLiveAnnouncement(
          `Loaded ${response.results.length} subscriptions. Total ${response.count} accounts.`
        );
      }
    } catch {
      if (currentSeq === requestSeqRef.current) {
        setIsLoading(false);
        const msg = "Unable to load subscriptions. Please check your connection and try again.";
        setError(msg);
        setLiveAnnouncement(msg);
      }
    }
  }, [page, pageSize, debouncedSearch, statusFilter, ordering]);

  useEffect(() => {
    fetchSubscriptions();
  }, [fetchSubscriptions]);

  const formatDate = (dateStr?: string | null) => {
    if (!dateStr) return "—";
    try {
      return new Date(dateStr).toLocaleDateString("en-US", {
        month: "short",
        day: "numeric",
        year: "numeric",
      });
    } catch {
      return dateStr;
    }
  };

  const getPeriodInfo = (sub: SubscriptionListItem) => {
    if (sub.status === "trialing") {
      return { date: formatDate(sub.trial_ends_at), label: "Trial Expiry" };
    }
    if (sub.status === "active" || sub.status === "suspended") {
      return { date: formatDate(sub.current_period_end), label: "Period End" };
    }
    if (sub.status === "cancelled") {
      return sub.current_period_end
        ? { date: formatDate(sub.current_period_end), label: "Period End" }
        : { date: formatDate(sub.trial_ends_at), label: "Trial Expiry" };
    }
    if (sub.status === "expired") {
      return { date: formatDate(sub.trial_ends_at), label: "Trial Expired" };
    }
    return { date: formatDate(sub.current_period_end || sub.trial_ends_at), label: "Period End" };
  };

  const totalPages = Math.max(1, Math.ceil(totalCount / pageSize));

  useEffect(() => {
    if (page > totalPages && totalCount > 0) {
      setPage(totalPages);
    }
  }, [page, totalPages, totalCount]);

  return (
    <AppShell>
      {/* Live Region for Screen Readers */}
      <div className="sr-only" aria-live="polite" aria-atomic="true">
        {liveAnnouncement}
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: "1.75rem", minWidth: 0 }}>
        {/* Breadcrumbs */}
        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", fontSize: "0.8125rem", color: "var(--text-muted)" }}>
          <span>Platform Owner</span>
          <span>/</span>
          <span>Customer Operations</span>
          <span>/</span>
          <span style={{ color: "var(--brand-primary, #3867f5)", fontWeight: 600 }}>Subscriptions Management</span>
        </div>

        {/* Page Header */}
        <div className="registry-page-header" style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "1.25rem" }}>
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
              <CreditCardIcon size={24} />
            </div>
            <div>
              <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", flexWrap: "wrap" }}>
                <h1 style={{ fontSize: "1.625rem", fontWeight: 800, margin: 0, color: "var(--text-primary)", letterSpacing: "-0.02em" }}>
                  Subscriptions Management
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
                    {totalCount} {totalCount === 1 ? "Subscription" : "Subscriptions"}
                  </span>
                )}
              </div>
              <p style={{ margin: "0.25rem 0 0 0", fontSize: "0.875rem", color: "var(--text-secondary)", lineHeight: 1.5, maxWidth: "780px" }}>
                Comprehensive inventory of customer subscriptions across all organizations. Monitor commercial snapshots, lifecycle statuses, evaluation trials, and billing periods.
              </p>
            </div>
          </div>
        </div>

        {/* Filter & Search Bar */}
        <div className="registry-controls-bar" style={{ flexWrap: "wrap" }}>
          {/* Search Box */}
          <div className="search-input-wrapper">
            <span className="search-icon-adornment" aria-hidden="true">
              <SearchIcon size={16} />
            </span>
            <input
              type="search"
              className="registry-search-input"
              placeholder="Search by organization name/code or plan name/code..."
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              aria-label="Search subscriptions"
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
              onChange={(e) => handleStatusFilterChange(e.target.value)}
              aria-label="Filter subscriptions by status"
            >
              <option value="">All Statuses</option>
              <option value="trialing">Trialing</option>
              <option value="active">Active Paid</option>
              <option value="suspended">Suspended</option>
              <option value="cancelled">Cancelled</option>
              <option value="expired">Expired</option>
            </select>
            <span className="filter-chevron-adornment" aria-hidden="true">
              <ChevronDownIcon size={15} />
            </span>
          </div>

          {/* Ordering Sort */}
          <div className="status-filter-wrapper">
            <select
              className="registry-filter-select"
              value={ordering}
              onChange={(e) => handleOrderingChange(e.target.value)}
              aria-label="Sort subscriptions order"
            >
              <option value="-created_at">Newest Provisioned</option>
              <option value="created_at">Oldest Provisioned</option>
              <option value="status">Status (Ascending)</option>
              <option value="-status">Status (Descending)</option>
              <option value="-current_period_end">Period End (Latest)</option>
              <option value="current_period_end">Period End (Earliest)</option>
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
              onClick={fetchSubscriptions}
              style={{ marginLeft: "auto" }}
            >
              Retry
            </button>
          </div>
        )}

        {/* Loading Skeleton */}
        {isLoading && (
          <div className="registry-skeleton-container" aria-label="Loading subscriptions">
            <div className="skeleton-row" />
            <div className="skeleton-row" />
            <div className="skeleton-row" />
          </div>
        )}

        {/* Table or Empty State */}
        {!isLoading && !error && (
          <>
            {subscriptions.length > 0 ? (
              <>
                <div className="subscriptions-table-container">
                  {/* Desktop View (>=1024px) */}
                  <div className="desktop-table-view table-card-container">
                    <div className="table-card-scroll">
                      <table className="data-table" style={{ minWidth: "940px" }} aria-label="Subscriptions Inventory">
                        <thead>
                          <tr className="subscriptions-desktop-grid subscriptions-grid-header">
                            <th scope="col">Organization</th>
                            <th scope="col">Plan &amp; Version</th>
                            <th scope="col">Commercial Terms</th>
                            <th scope="col">Status</th>
                            <th scope="col">Period / Trial</th>
                            <th scope="col" style={{ textAlign: "center" }}>Actions</th>
                          </tr>
                        </thead>
                        <tbody>
                          {subscriptions.map((sub) => {
                            const period = getPeriodInfo(sub);
                            return (
                              <tr key={sub.id} className="table-row subscriptions-desktop-grid">
                                <td>
                                  <div style={{ display: "flex", flexDirection: "column", gap: "0.2rem" }}>
                                    <span style={{ fontWeight: 600, color: "var(--text-primary)", overflowWrap: "anywhere", wordBreak: "break-word" }}>
                                      {sub.organization_name}
                                    </span>
                                    <span className="code-pill" style={{ width: "fit-content" }}>
                                      {sub.organization_code}
                                    </span>
                                  </div>
                                </td>
                                <td>
                                  <div style={{ display: "flex", flexDirection: "column", gap: "0.2rem" }}>
                                    <div style={{ display: "flex", alignItems: "center", gap: "0.4rem", flexWrap: "wrap" }}>
                                      <span style={{ fontWeight: 600, color: "var(--text-primary)" }}>
                                        {sub.plan_name_snapshot}
                                      </span>
                                      <span className="product-code-pill">v{sub.version_number_snapshot}</span>
                                    </div>
                                    <span className="text-caption" style={{ color: "var(--text-muted)" }}>
                                      {sub.plan_code_snapshot}
                                    </span>
                                  </div>
                                </td>
                                <td>
                                  <div style={{ display: "flex", flexDirection: "column", gap: "0.15rem" }}>
                                    <span style={{ fontWeight: 700, color: "var(--brand-primary)" }}>
                                      {formatCurrencyDisplay(sub.amount, sub.currency)}
                                    </span>
                                    <span className="text-caption" style={{ textTransform: "capitalize" }}>
                                      per {sub.billing_interval}
                                    </span>
                                  </div>
                                </td>
                                <td>
                                  <SubscriptionStatusBadge status={sub.status} />
                                </td>
                                <td>
                                  <div style={{ display: "flex", flexDirection: "column", gap: "0.15rem" }}>
                                    <span style={{ fontSize: "0.8125rem", color: "var(--text-primary)", whiteSpace: "nowrap" }}>
                                      {period.date}
                                    </span>
                                    <span className="text-caption" style={{ color: "var(--text-muted)", whiteSpace: "nowrap" }}>
                                      {period.label}
                                    </span>
                                  </div>
                                </td>
                                <td style={{ textAlign: "center" }}>
                                  <button
                                    type="button"
                                    className="btn btn-primary btn-sm"
                                    onClick={() => navigate(`/organizations/${sub.organization_id}`)}
                                    aria-label={`Manage subscription for ${sub.organization_name}`}
                                  >
                                    <span>Manage</span>
                                  </button>
                                </td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                  </div>

                  {/* Mobile Cards View (<1024px) */}
                  <div className="mobile-cards-view">
                    {subscriptions.map((sub) => {
                      const period = getPeriodInfo(sub);
                      return (
                        <div key={sub.id} className="mobile-sub-card">
                          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: "0.5rem" }}>
                            <span className="code-pill">{sub.organization_code}</span>
                            <SubscriptionStatusBadge status={sub.status} />
                          </div>

                          <div>
                            <h3 style={{ fontSize: "1rem", fontWeight: 600, color: "var(--text-primary)", margin: "0.25rem 0 0.15rem 0", overflowWrap: "anywhere", wordBreak: "break-word" }}>
                              {sub.organization_name}
                            </h3>
                            <p style={{ fontSize: "0.8125rem", color: "var(--text-secondary)", margin: 0, overflowWrap: "anywhere", wordBreak: "break-word" }}>
                              {sub.plan_name_snapshot} (v{sub.version_number_snapshot}) • {formatCurrencyDisplay(sub.amount, sub.currency)} / {sub.billing_interval}
                            </p>
                          </div>

                          <div
                            style={{
                              display: "flex",
                              justifyContent: "space-between",
                              alignItems: "center",
                              paddingTop: "0.75rem",
                              borderTop: "1px solid var(--border-subtle)",
                              marginTop: "0.5rem",
                              gap: "0.5rem",
                              flexWrap: "wrap",
                            }}
                          >
                            <span style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
                              <CalendarIcon size={12} style={{ display: "inline", verticalAlign: "middle", marginRight: "3px" }} />
                              {`${period.label}: ${period.date}`}
                            </span>

                            <button
                              type="button"
                              className="btn btn-primary btn-sm"
                              style={{ minHeight: "44px", display: "inline-flex", alignItems: "center" }}
                              onClick={() => navigate(`/organizations/${sub.organization_id}`)}
                              aria-label={`Manage subscription for ${sub.organization_name}`}
                            >
                              <span>Manage</span>
                            </button>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>

                {/* Pagination Controls */}
                {totalCount > pageSize && (
                  <div className="pagination-bar">
                    <span className="text-caption">
                      Showing {(page - 1) * pageSize + 1}–{Math.min(page * pageSize, totalCount)} of {totalCount}
                    </span>
                    <div style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
                      <button
                        type="button"
                        className="btn btn-secondary btn-sm"
                        onClick={() => setPage((p) => Math.max(p - 1, 1))}
                        disabled={page <= 1}
                        aria-label="Previous page"
                      >
                        Previous
                      </button>
                      <span className="pagination-page-indicator">
                        Page {page} of {totalPages}
                      </span>
                      <button
                        type="button"
                        className="btn btn-secondary btn-sm"
                        onClick={() => setPage((p) => Math.min(p + 1, totalPages))}
                        disabled={page >= totalPages}
                        aria-label="Next page"
                      >
                        Next
                      </button>
                    </div>
                  </div>
                )}
              </>
            ) : (
              /* Empty State */
              <div className="registry-empty-card">
                <div className="empty-icon-circle">
                  <LayersIcon size={28} />
                </div>
                {searchInput || statusFilter ? (
                  <>
                    <h3 className="empty-title">No matching subscriptions found</h3>
                    <p className="empty-desc">
                      No subscription records matched your query or status filter. Try clearing your search or resetting filters.
                    </p>
                    <button
                      type="button"
                      className="btn btn-secondary btn-sm"
                      onClick={() => {
                        setSearchInput("");
                        setStatusFilter("");
                        setPage(1);
                      }}
                    >
                      Clear Filters
                    </button>
                  </>
                ) : (
                  <>
                    <h3 className="empty-title">No subscriptions provisioned</h3>
                    <p className="empty-desc">
                      There are currently no active, trialing, or past subscriptions provisioned across organizations.
                    </p>
                    <button
                      type="button"
                      className="btn btn-primary"
                      onClick={() => navigate("/organizations")}
                    >
                      Browse Organizations
                    </button>
                  </>
                )}
              </div>
            )}
          </>
        )}
      </div>

      <style>{`
        .subscriptions-table-container {
          width: 100%;
          min-width: 0;
        }

        .mobile-sub-card {
          background: var(--glass-surface-elevated);
          border: 1px solid var(--border-glass);
          border-radius: 12px;
          padding: 1rem;
          display: flex;
          flex-direction: column;
          gap: 0.625rem;
          box-shadow: var(--shadow-sm);
        }
      `}</style>
    </AppShell>
  );
};
