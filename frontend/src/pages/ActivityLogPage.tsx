/**
 * Activity Log Management Page.
 *
 * Dedicated Platform Owner portal for reviewing immutable system-wide audit logs.
 * Supports debounced search, action/target/source filtering, inclusive UTC date ranges,
 * deterministic ordering, server-side pagination with out-of-range 404 recovery,
 * accessible detail inspection, and full responsive support.
 */

import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  AUDIT_ACTION_LABELS,
  AUDIT_TARGET_TYPE_LABELS,
  auditApi,
  type RetentionEvaluationResponse,
} from "../api/audit.ts";
import { ApiError } from "../api/client.ts";
import type {
  AuditAction,
  AuditLogListItem,
  AuditLogListParams,
  AuditLogListResponse,
  AuditOrderingField,
  AuditTargetType,
} from "../api/types.ts";
import { AppShell } from "../components/AppShell.tsx";
import { AuditDetailDialog } from "../components/audit/AuditDetailDialog.tsx";
import { AuditLogTable } from "../components/audit/AuditLogTable.tsx";
import {
  AlertCircleIcon,
  ChevronDownIcon,
  ChevronLeftIcon,
  ChevronRightIcon,
  CloseIcon,
  HistoryIcon,
  RotateCcwIcon,
  SearchIcon,
  ShieldCheckIcon,
} from "../components/Icons.tsx";

const ACTION_OPTIONS: Array<{ value: AuditAction; label: string }> = (
  Object.keys(AUDIT_ACTION_LABELS) as AuditAction[]
).map((key) => ({
  value: key,
  label: AUDIT_ACTION_LABELS[key],
}));

const TARGET_TYPE_OPTIONS: Array<{ value: AuditTargetType; label: string }> = (
  Object.keys(AUDIT_TARGET_TYPE_LABELS) as AuditTargetType[]
).map((key) => ({
  value: key,
  label: AUDIT_TARGET_TYPE_LABELS[key],
}));

const ORDERING_OPTIONS: Array<{ value: AuditOrderingField; label: string }> = [
  { value: "-timestamp", label: "Newest First (Default)" },
  { value: "timestamp", label: "Oldest First" },
  { value: "-action", label: "Action (Z to A)" },
  { value: "action", label: "Action (A to Z)" },
  { value: "-target_type", label: "Target Type (Z to A)" },
  { value: "target_type", label: "Target Type (A to Z)" },
];

export const ActivityLogPage: React.FC = () => {
  // Query & Filter State
  const [searchInput, setSearchInput] = useState<string>("");
  const [debouncedSearch, setDebouncedSearch] = useState<string>("");
  const [actionFilter, setActionFilter] = useState<string>("");
  const [targetTypeFilter, setTargetTypeFilter] = useState<string>("");
  const [dateFromInput, setDateFromInput] = useState<string>("");
  const [dateToInput, setDateToInput] = useState<string>("");
  const [ordering, setOrdering] = useState<AuditOrderingField>("-timestamp");

  // Pagination State
  const [page, setPage] = useState<number>(1);
  const pageSize = 20;

  // Data & Lifecycle State
  const [data, setData] = useState<AuditLogListResponse | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [liveAnnouncement, setLiveAnnouncement] = useState<string>("");

  // Dialog State
  const [selectedLogId, setSelectedLogId] = useState<string | null>(null);
  const [isDetailOpen, setIsDetailOpen] = useState<boolean>(false);
  const triggerRef = useRef<HTMLElement | null>(null);

  // Retention Evaluation Modal State (Phase 6F-3 Dry-Run)
  const [isRetentionModalOpen, setIsRetentionModalOpen] = useState<boolean>(false);
  const [retentionData, setRetentionData] = useState<RetentionEvaluationResponse | null>(null);
  const [isLoadingRetention, setIsLoadingRetention] = useState<boolean>(false);
  const [retentionError, setRetentionError] = useState<string | null>(null);

  const handleOpenRetentionEvaluation = async () => {
    setIsRetentionModalOpen(true);
    setIsLoadingRetention(true);
    setRetentionError(null);
    try {
      const resp = await auditApi.getRetentionEvaluation();
      setRetentionData(resp);
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setRetentionError(err.message);
      } else {
        setRetentionError("Failed to load data retention evaluation.");
      }
    } finally {
      setIsLoadingRetention(false);
    }
  };

  // Request Lifecycle Refs
  const listAbortControllerRef = useRef<AbortController | null>(null);
  const listSeqRef = useRef<number>(0);
  const hasRecoveredPage404Ref = useRef<boolean>(false);

  // Date range validation
  const isDateRangeReversed = useMemo(() => {
    if (!dateFromInput || !dateToInput) return false;
    return dateFromInput > dateToInput;
  }, [dateFromInput, dateToInput]);

  // Scroll to top on mount
  useEffect(() => {
    window.scrollTo(0, 0);
  }, []);

  // Debounce search input (300ms)
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearch(searchInput.trim());
      hasRecoveredPage404Ref.current = false;
      setPage(1);
    }, 300);

    return () => clearTimeout(timer);
  }, [searchInput]);

  // Reset page when filter controls change
  const handleActionChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    setActionFilter(e.target.value);
    hasRecoveredPage404Ref.current = false;
    setPage(1);
  };

  const handleTargetTypeChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    setTargetTypeFilter(e.target.value);
    hasRecoveredPage404Ref.current = false;
    setPage(1);
  };

  const handleDateFromChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setDateFromInput(e.target.value);
    hasRecoveredPage404Ref.current = false;
    setPage(1);
  };

  const handleDateToChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setDateToInput(e.target.value);
    hasRecoveredPage404Ref.current = false;
    setPage(1);
  };

  const handleOrderingChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    setOrdering(e.target.value as AuditOrderingField);
    hasRecoveredPage404Ref.current = false;
    setPage(1);
  };

  const handleClearFilters = () => {
    setSearchInput("");
    setDebouncedSearch("");
    setActionFilter("");
    setTargetTypeFilter("");
    setDateFromInput("");
    setDateToInput("");
    setOrdering("-timestamp");
    hasRecoveredPage404Ref.current = false;
    setPage(1);
  };

  // Fetch list data with cancellation and sequence guards
  const fetchAuditLogs = useCallback(() => {
    if (isDateRangeReversed) {
      return;
    }

    listAbortControllerRef.current?.abort();
    const currentSeq = ++listSeqRef.current;
    const controller = new AbortController();
    listAbortControllerRef.current = controller;

    setIsLoading(true);
    setError(null);
    setLiveAnnouncement("Loading activity logs...");

    // Construct query parameters with inclusive microsecond UTC date boundaries
    const params: AuditLogListParams = {
      page,
      page_size: pageSize,
      ordering,
      search: debouncedSearch || undefined,
      action: (actionFilter as AuditAction) || undefined,
      target_type: (targetTypeFilter as AuditTargetType) || undefined,
      date_from: dateFromInput ? `${dateFromInput}T00:00:00.000000Z` : undefined,
      date_to: dateToInput ? `${dateToInput}T23:59:59.999999Z` : undefined,
    };

    auditApi
      .list(params, controller.signal)
      .then((res) => {
        if (controller.signal.aborted || currentSeq !== listSeqRef.current) return;
        setData(res);
        setIsLoading(false);
        setLiveAnnouncement(
          `Showing ${res.results.length} activity logs. Page ${page} of ${Math.max(1, Math.ceil(res.count / pageSize))}. Total ${res.count} events.`
        );
      })
      .catch((err: unknown) => {
        if (controller.signal.aborted || currentSeq !== listSeqRef.current) return;

        // Out-of-range page 404 recovery (at most once per committed query state)
        if (err instanceof ApiError && err.status === 404 && page > 1 && !hasRecoveredPage404Ref.current) {
          hasRecoveredPage404Ref.current = true;
          setPage(1);
          return;
        }

        const msg = err instanceof ApiError ? err.message : "Failed to load activity logs.";
        setError(msg);
        setIsLoading(false);
        setLiveAnnouncement(`Error loading activity logs: ${msg}`);
      });
  }, [
    page,
    pageSize,
    debouncedSearch,
    actionFilter,
    targetTypeFilter,
    dateFromInput,
    dateToInput,
    ordering,
    isDateRangeReversed,
  ]);

  useEffect(() => {
    fetchAuditLogs();

    return () => {
      listAbortControllerRef.current?.abort();
      listSeqRef.current++;
    };
  }, [fetchAuditLogs]);

  // Dialog open & focus restoration handlers
  const handleOpenDetail = (log: AuditLogListItem, triggerElement: HTMLElement) => {
    triggerRef.current = triggerElement;
    setSelectedLogId(log.id);
    setIsDetailOpen(true);
  };

  const handleCloseDetail = () => {
    setIsDetailOpen(false);
    setSelectedLogId(null);
    if (triggerRef.current && document.contains(triggerRef.current)) {
      triggerRef.current.focus();
    }
  };

  // Pagination navigation handlers (strictly numeric page state)
  const handlePrevPage = () => {
    if (page > 1) {
      setPage((prev) => Math.max(1, prev - 1));
    }
  };

  const handleNextPage = () => {
    if (data?.next) {
      setPage((prev) => prev + 1);
    }
  };

  const hasActiveFilters = useMemo(() => {
    return (
      Boolean(debouncedSearch) ||
      Boolean(actionFilter) ||
      Boolean(targetTypeFilter) ||
      Boolean(dateFromInput) ||
      Boolean(dateToInput) ||
      ordering !== "-timestamp"
    );
  }, [debouncedSearch, actionFilter, targetTypeFilter, dateFromInput, dateToInput, ordering]);

  const totalPages = data ? Math.max(1, Math.ceil(data.count / pageSize)) : 1;

  return (
    <AppShell>
      <div className="activity-log-page-container">
        {/* Page-scoped always-mounted screen reader live region */}
        <div className="activity-log-sr-only sr-only" aria-live="polite" aria-atomic="true">
          {liveAnnouncement}
        </div>

        {/* Header Title Section */}
        <div className="activity-page-header">
          <div className="activity-title-group">
            <div className="activity-title-row">
              <h1 className="heading-title">Activity Log</h1>
              {data && (
                <span className="registry-count-badge" aria-label={`Total ${data.count} events recorded`}>
                  {data.count} {data.count === 1 ? "Event" : "Events"}
                </span>
              )}
            </div>
            <p className="text-body" style={{ marginTop: "0.25rem" }}>
              Immutable audit trail capturing master platform mutations, access updates, and authentication events.
            </p>
          </div>

          <div style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
            <button
              type="button"
              className="btn-secondary activity-retention-btn"
              onClick={handleOpenRetentionEvaluation}
              aria-label="Open Data Retention Evaluation (Dry-Run)"
            >
              <ShieldCheckIcon size={16} />
              <span>Retention Evaluation</span>
            </button>

            <button
              type="button"
              className="btn-secondary activity-refresh-btn"
              onClick={fetchAuditLogs}
              disabled={isLoading || isDateRangeReversed}
              aria-label="Refresh activity logs"
            >
              <span className={isLoading ? "spinner-icon" : ""}>
                <RotateCcwIcon size={16} />
              </span>
              <span>Refresh</span>
            </button>
          </div>
        </div>

        {/* Filter & Controls Panel */}
        <div className="glass-panel activity-filter-panel">
          <div className="filter-controls-grid">
            {/* Search Input */}
            <div className="filter-input-col search-col">
              <label htmlFor="audit-search-input" className="form-label">
                Search
              </label>
              <div className="form-input-container">
                <input
                  id="audit-search-input"
                  type="text"
                  className="form-input form-input-with-icon-right"
                  placeholder="Search target, actor, repr..."
                  value={searchInput}
                  onChange={(e) => setSearchInput(e.target.value)}
                  maxLength={100}
                />
                <span className="input-icon-right" aria-hidden="true">
                  <SearchIcon size={16} />
                </span>
              </div>
            </div>

            {/* Action Filter */}
            <div className="filter-input-col">
              <label htmlFor="audit-action-select" className="form-label">
                Action
              </label>
              <div className="form-input-container select-wrapper">
                <select
                  id="audit-action-select"
                  className="form-input"
                  value={actionFilter}
                  onChange={handleActionChange}
                >
                  <option value="">All Actions</option>
                  {ACTION_OPTIONS.map((opt) => (
                    <option key={opt.value} value={opt.value}>
                      {opt.label}
                    </option>
                  ))}
                </select>
                <span className="select-arrow-icon" aria-hidden="true">
                  <ChevronDownIcon size={16} />
                </span>
              </div>
            </div>

            {/* Target Type Filter */}
            <div className="filter-input-col">
              <label htmlFor="audit-target-select" className="form-label">
                Target Type
              </label>
              <div className="form-input-container select-wrapper">
                <select
                  id="audit-target-select"
                  className="form-input"
                  value={targetTypeFilter}
                  onChange={handleTargetTypeChange}
                >
                  <option value="">All Types</option>
                  {TARGET_TYPE_OPTIONS.map((opt) => (
                    <option key={opt.value} value={opt.value}>
                      {opt.label}
                    </option>
                  ))}
                </select>
                <span className="select-arrow-icon" aria-hidden="true">
                  <ChevronDownIcon size={16} />
                </span>
              </div>
            </div>

            {/* Date From Input */}
            <div className="filter-input-col">
              <label htmlFor="audit-date-from" className="form-label">
                Date From (UTC)
              </label>
              <div className="form-input-container">
                <input
                  id="audit-date-from"
                  type="date"
                  className={`form-input ${isDateRangeReversed ? "form-input-error" : ""}`}
                  value={dateFromInput}
                  onChange={handleDateFromChange}
                />
              </div>
            </div>

            {/* Date To Input */}
            <div className="filter-input-col">
              <label htmlFor="audit-date-to" className="form-label">
                Date To (UTC)
              </label>
              <div className="form-input-container">
                <input
                  id="audit-date-to"
                  type="date"
                  className={`form-input ${isDateRangeReversed ? "form-input-error" : ""}`}
                  value={dateToInput}
                  onChange={handleDateToChange}
                />
              </div>
            </div>

            {/* Ordering Select */}
            <div className="filter-input-col">
              <label htmlFor="audit-ordering-select" className="form-label">
                Sort Order
              </label>
              <div className="form-input-container select-wrapper">
                <select
                  id="audit-ordering-select"
                  className="form-input"
                  value={ordering}
                  onChange={handleOrderingChange}
                >
                  {ORDERING_OPTIONS.map((opt) => (
                    <option key={opt.value} value={opt.value}>
                      {opt.label}
                    </option>
                  ))}
                </select>
                <span className="select-arrow-icon" aria-hidden="true">
                  <ChevronDownIcon size={16} />
                </span>
              </div>
            </div>
          </div>

          {/* Date range validation inline error */}
          {isDateRangeReversed && (
            <div className="form-error" style={{ marginTop: "0.5rem" }}>
              'From' date cannot be after 'To' date.
            </div>
          )}

          {/* Active Filter Clear Control */}
          {hasActiveFilters && (
            <div className="active-filters-bar">
              <span className="text-caption">Filters are currently active.</span>
              <button
                type="button"
                className="btn-ghost clear-filters-btn"
                onClick={handleClearFilters}
              >
                Clear all filters
              </button>
            </div>
          )}
        </div>

        {/* Error Alert Box */}
        {error && (
          <div className="alert-box alert-danger" role="alert">
            <div>
              <p style={{ fontWeight: 600, marginBottom: "0.25rem" }}>Error Loading Activity Logs</p>
              <p>{error}</p>
              <button
                type="button"
                className="btn-secondary"
                style={{ marginTop: "0.75rem", minHeight: "38px" }}
                onClick={fetchAuditLogs}
              >
                <RotateCcwIcon size={14} />
                <span>Retry</span>
              </button>
            </div>
          </div>
        )}

        {/* Content Area */}
        <div className="activity-content-area">
          {isLoading && (
            <div className="glass-panel activity-loading-box">
              <span className="spinner-icon" style={{ display: "inline-block", width: "28px", height: "28px" }}>
                <RotateCcwIcon size={28} />
              </span>
              <p className="text-body" style={{ marginTop: "0.75rem" }}>
                Retrieving immutable audit records...
              </p>
            </div>
          )}

          {!isLoading && !error && data && data.results.length === 0 && (
            <div className="glass-panel activity-empty-box">
              <div className="activity-empty-icon">
                <HistoryIcon size={36} />
              </div>
              {hasActiveFilters ? (
                <>
                  <h2 className="heading-subtitle" style={{ marginBottom: "0.25rem" }}>
                    No Matching Activity Logs
                  </h2>
                  <p className="text-body" style={{ maxWidth: "420px", marginBottom: "1.25rem" }}>
                    No audit records match the current filter criteria. Try adjusting or clearing your active filters.
                  </p>
                  <button
                    type="button"
                    className="btn-secondary"
                    style={{ minHeight: "44px" }}
                    onClick={handleClearFilters}
                  >
                    Clear Filters
                  </button>
                </>
              ) : (
                <>
                  <h2 className="heading-subtitle" style={{ marginBottom: "0.25rem" }}>
                    No Activity Logs Recorded
                  </h2>
                  <p className="text-body" style={{ maxWidth: "420px" }}>
                    No administrative mutations or audit events have been logged yet.
                  </p>
                </>
              )}
            </div>
          )}

          {!isLoading && !error && data && data.results.length > 0 && (
            <>
              <AuditLogTable
                logs={data.results}
                onSelectLog={handleOpenDetail}
                isLoading={isLoading}
              />

              {/* Pagination Controls */}
              <div className="activity-pagination-bar">
                <div className="pagination-info">
                  <span className="text-caption">
                    Page <strong className="font-mono">{page}</strong> of <strong className="font-mono">{totalPages}</strong>
                    {" "}&bull; Total <strong className="font-mono">{data.count}</strong> records
                  </span>
                </div>

                <div className="pagination-actions">
                  <button
                    type="button"
                    className="btn-secondary pagination-btn"
                    onClick={handlePrevPage}
                    disabled={page <= 1 || !data.previous || isLoading}
                    aria-label="Go to previous page"
                  >
                    <ChevronLeftIcon size={16} />
                    <span>Previous</span>
                  </button>

                  <button
                    type="button"
                    className="btn-secondary pagination-btn"
                    onClick={handleNextPage}
                    disabled={!data.next || isLoading}
                    aria-label="Go to next page"
                  >
                    <span>Next</span>
                    <ChevronRightIcon size={16} />
                  </button>
                </div>
              </div>
            </>
          )}
        </div>

        {/* Modal Detail Dialog */}
        <AuditDetailDialog
          logId={selectedLogId}
          isOpen={isDetailOpen}
          onClose={handleCloseDetail}
        />

        {/* Retention Evaluation Modal Dialog (Phase 6F-3) */}
        {isRetentionModalOpen && (
          <div
            className="retention-modal-backdrop"
            role="presentation"
            onClick={() => setIsRetentionModalOpen(false)}
          >
            <div
              className="glass-panel retention-modal-card"
              role="dialog"
              aria-modal="true"
              aria-labelledby="retention-modal-title"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="retention-modal-header">
                <div>
                  <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                    <ShieldCheckIcon size={20} className="text-primary" />
                    <h2 id="retention-modal-title" className="heading-title" style={{ fontSize: "1.25rem", margin: 0 }}>
                      Data Retention Evaluation
                    </h2>
                    <span className="badge-warning" style={{ fontSize: "0.75rem", padding: "0.15rem 0.5rem", borderRadius: "9999px" }}>
                      PROPOSED &bull; DRY RUN ONLY
                    </span>
                  </div>
                  <p className="text-caption" style={{ marginTop: "0.25rem" }}>
                    Platform Owner preview of candidates eligible under proposed data retention rules.
                  </p>
                </div>
                <button
                  type="button"
                  className="btn-ghost"
                  onClick={() => setIsRetentionModalOpen(false)}
                  aria-label="Close retention evaluation modal"
                  style={{ padding: "0.25rem" }}
                >
                  <CloseIcon size={18} />
                </button>
              </div>

              {isLoadingRetention && (
                <div style={{ padding: "3rem 1rem", textAlign: "center" }}>
                  <div className="spinner-icon" style={{ margin: "0 auto 1rem", width: "24px", height: "24px" }} />
                  <p className="text-caption">Evaluating data retention candidate counts across governed models...</p>
                </div>
              )}

              {retentionError && (
                <div className="alert-banner alert-banner-danger" style={{ margin: "1rem" }}>
                  <AlertCircleIcon size={16} />
                  <span>{retentionError}</span>
                </div>
              )}

              {!isLoadingRetention && retentionData && (
                <div className="retention-modal-body">
                  <div className="retention-summary-banner">
                    <div className="retention-stat-card">
                      <span className="text-caption">Policy Status</span>
                      <strong className="font-mono">{retentionData.policy_status}</strong>
                    </div>
                    <div className="retention-stat-card">
                      <span className="text-caption">Total Candidates</span>
                      <strong className="font-mono text-warning" style={{ fontSize: "1.25rem" }}>
                        {retentionData.total_candidates}
                      </strong>
                    </div>
                    <div className="retention-stat-card">
                      <span className="text-caption">Execution Mode</span>
                      <strong className="text-success">Dry Run Only (Non-destructive)</strong>
                    </div>
                  </div>

                  <div className="alert-banner alert-banner-info" style={{ marginTop: "0.75rem", marginBottom: "1rem" }}>
                    <ShieldCheckIcon size={16} />
                    <span>{retentionData.disclaimer}</span>
                  </div>

                  <div className="retention-table-container">
                    <table className="retention-table" style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.85rem" }}>
                      <thead>
                        <tr style={{ borderBottom: "1px solid var(--border-color)", textAlign: "left", opacity: 0.8 }}>
                          <th style={{ padding: "0.5rem" }}>Category / Governed Model</th>
                          <th style={{ padding: "0.5rem" }}>Proposed Retention</th>
                          <th style={{ padding: "0.5rem", textAlign: "right" }}>Candidates Found</th>
                          <th style={{ padding: "0.5rem" }}>Dry-Run State</th>
                        </tr>
                      </thead>
                      <tbody>
                        {retentionData.categories.map((cat) => (
                          <tr key={cat.model} style={{ borderBottom: "1px solid var(--border-subtle)" }}>
                            <td style={{ padding: "0.5rem" }}>
                              <strong>{cat.label}</strong>
                              <div className="text-caption font-mono" style={{ fontSize: "0.75rem", opacity: 0.7 }}>{cat.model}</div>
                            </td>
                            <td style={{ padding: "0.5rem" }} className="font-mono">{cat.proposed_retention}</td>
                            <td style={{ padding: "0.5rem", textAlign: "right" }} className="font-mono">
                              <span style={{ fontWeight: cat.candidate_count > 0 ? "bold" : "normal" }}>
                                {cat.candidate_count}
                              </span>
                            </td>
                            <td style={{ padding: "0.5rem" }}>
                              <span className="badge-outline" style={{ fontSize: "0.75rem" }}>
                                Preserved (No Mutation)
                              </span>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              <div className="retention-modal-footer">
                <button
                  type="button"
                  className="btn-secondary"
                  onClick={() => setIsRetentionModalOpen(false)}
                >
                  Close Preview
                </button>
              </div>
            </div>
          </div>
        )}
      </div>

      <style>{`
        .activity-log-sr-only,
        .sr-only {
          position: absolute !important;
          width: 1px !important;
          height: 1px !important;
          padding: 0 !important;
          margin: -1px !important;
          overflow: hidden !important;
          clip: rect(0, 0, 0, 0) !important;
          white-space: nowrap !important;
          border: 0 !important;
        }

        .activity-log-page-container {
          padding: 0 0 2rem 0;
          max-width: 1400px;
          margin: 0 auto;
          width: 100%;
          display: flex;
          flex-direction: column;
          gap: 1.25rem;
          min-width: 0;
        }

        .activity-page-header {
          display: flex;
          align-items: flex-start;
          justify-content: space-between;
          gap: 1rem;
          flex-wrap: wrap;
        }

        .activity-title-group {
          flex: 1;
          min-width: 260px;
        }

        .activity-title-row {
          display: flex;
          align-items: center;
          gap: 0.75rem;
          flex-wrap: wrap;
        }

        .activity-refresh-btn {
          min-height: 44px;
          padding: 0.5rem 1.125rem;
          display: inline-flex;
          align-items: center;
          gap: 0.5rem;
        }

        /* Filter Panel */
        .activity-filter-panel {
          padding: 1.25rem;
          display: flex;
          flex-direction: column;
          gap: 0.75rem;
        }

        .filter-controls-grid {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
          gap: 0.875rem;
          align-items: flex-end;
        }

        .filter-input-col {
          display: flex;
          flex-direction: column;
          gap: 0.35rem;
        }

        .search-col {
          grid-column: span 2;
        }

        @media (max-width: 640px) {
          .search-col {
            grid-column: span 1;
          }
        }

        .select-wrapper {
          position: relative;
        }

        .select-wrapper select {
          appearance: none;
          -webkit-appearance: none;
          padding-right: 2rem;
          cursor: pointer;
        }

        .select-arrow-icon {
          position: absolute;
          right: 0.625rem;
          pointer-events: none;
          color: var(--text-muted);
          display: flex;
          align-items: center;
          justify-content: center;
        }

        .active-filters-bar {
          display: flex;
          align-items: center;
          justify-content: space-between;
          padding-top: 0.75rem;
          border-top: 1px solid var(--border-subtle);
          color: var(--text-secondary);
        }

        .clear-filters-btn {
          font-size: 0.8125rem;
          color: var(--brand-primary);
          text-decoration: underline;
          min-height: 36px;
        }

        /* Content States */
        .activity-content-area {
          display: flex;
          flex-direction: column;
          gap: 1rem;
        }

        .activity-loading-box,
        .activity-empty-box {
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          padding: 4rem 1.5rem;
          text-align: center;
        }

        .activity-empty-icon {
          width: 64px;
          height: 64px;
          border-radius: 16px;
          background: var(--glass-surface-sunken);
          border: 1px solid var(--border-glass);
          color: var(--text-muted);
          display: flex;
          align-items: center;
          justify-content: center;
          margin-bottom: 1rem;
        }

        /* Pagination Bar */
        .activity-pagination-bar {
          display: flex;
          align-items: center;
          justify-content: space-between;
          padding: 0.875rem 1.25rem;
          background: var(--glass-surface-elevated);
          border: 1px solid var(--border-glass);
          border-radius: 12px;
          flex-wrap: wrap;
          gap: 1rem;
        }

        .pagination-actions {
          display: flex;
          align-items: center;
          gap: 0.625rem;
        }

        .pagination-btn {
          min-height: 44px;
          min-width: 100px;
          display: inline-flex;
          align-items: center;
          justify-content: center;
          gap: 0.375rem;
        }

        .retention-modal-backdrop {
          position: fixed;
          top: 0;
          left: 0;
          right: 0;
          bottom: 0;
          background: rgba(0, 0, 0, 0.7);
          backdrop-filter: blur(4px);
          display: flex;
          align-items: center;
          justify-content: center;
          z-index: 9999;
          padding: 1.5rem;
        }

        .retention-modal-card {
          width: 100%;
          max-width: 850px;
          max-height: 85vh;
          overflow-y: auto;
          background: var(--surface-card, #1e293b);
          border: 1px solid var(--border-glass, rgba(255, 255, 255, 0.1));
          border-radius: 16px;
          display: flex;
          flex-direction: column;
          box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.5);
        }

        .retention-modal-header {
          display: flex;
          align-items: flex-start;
          justify-content: space-between;
          padding: 1.25rem 1.5rem;
          border-bottom: 1px solid var(--border-color, rgba(255, 255, 255, 0.1));
        }

        .retention-modal-body {
          padding: 1.25rem 1.5rem;
          display: flex;
          flex-direction: column;
          gap: 1rem;
        }

        .retention-summary-banner {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
          gap: 1rem;
        }

        .retention-stat-card {
          padding: 0.75rem 1rem;
          border-radius: 8px;
          background: rgba(255, 255, 255, 0.03);
          border: 1px solid var(--border-subtle, rgba(255, 255, 255, 0.05));
          display: flex;
          flex-direction: column;
          gap: 0.25rem;
        }

        .retention-table-container {
          overflow-x: auto;
          border: 1px solid var(--border-subtle, rgba(255, 255, 255, 0.08));
          border-radius: 8px;
        }

        .retention-modal-footer {
          padding: 1rem 1.5rem;
          border-top: 1px solid var(--border-color, rgba(255, 255, 255, 0.1));
          display: flex;
          justify-content: flex-end;
        }

        @media (max-width: 768px) {
          .activity-log-page-container {
            padding: 0 0 1.5rem 0;
          }

          .activity-pagination-bar {
            flex-direction: column;
            align-items: stretch;
            text-align: center;
          }

          .pagination-actions {
            justify-content: space-between;
            width: 100%;
          }

          .pagination-btn {
            flex: 1;
          }
        }
      `}</style>
    </AppShell>
  );
};
