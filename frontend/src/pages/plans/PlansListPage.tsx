/**
 * Platform Owner Plans & Pricing List Page.
 *
 * Full-featured management of commercial Plan families:
 * - Server-driven search and debouncing with sequence guards
 * - Multi-criteria filters: has active version, has draft version, catalog health
 * - Deterministic ordering and server-side pagination
 * - Responsive desktop table and mobile card layout
 * - Truthful empty and loading states
 */

import React, { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { plansApi } from "../../api/plans.ts";
import type { PlanDetail, PlanListItem, PlanListParams } from "../../api/types.ts";
import { AppShell } from "../../components/AppShell.tsx";
import {
  ChevronDownIcon,
  EditIcon,
  FilterIcon,
  LayersIcon,
  PlusIcon,
  RotateCcwIcon,
  SearchIcon,
} from "../../components/Icons.tsx";
import { CreatePlanDialog, EditPlanDialog } from "../../components/plans/PlanDialogs.tsx";
import { CatalogHealthBadge, PlanVersionStatusBadge } from "../../components/plans/PlanStatusBadge.tsx";

export const PlansListPage: React.FC = () => {
  const navigate = useNavigate();

  const [plans, setPlans] = useState<PlanListItem[]>([]);
  const [totalCount, setTotalCount] = useState<number>(0);
  const [page, setPage] = useState<number>(1);
  const pageSize = 10;

  // Search and Filter State
  const [searchInput, setSearchInput] = useState<string>("");
  const [debouncedSearch, setDebouncedSearch] = useState<string>("");
  const [hasActiveFilter, setHasActiveFilter] = useState<string>("all");
  const [hasDraftFilter, setHasDraftFilter] = useState<string>("all");
  const [healthFilter, setHealthFilter] = useState<string>("all");
  const [ordering, setOrdering] = useState<string>("name");

  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [liveAnnouncement, setLiveAnnouncement] = useState<string>("");

  // Dialog State
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [isEditOpen, setIsEditOpen] = useState(false);
  const [selectedPlan, setSelectedPlan] = useState<PlanListItem | null>(null);
  const triggerRef = useRef<HTMLElement | null>(null);

  // Request sequence guard
  const requestSeqRef = useRef<number>(0);

  // Debounce search input (300ms)
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearch(searchInput.trim());
      setPage(1);
    }, 300);
    return () => clearTimeout(timer);
  }, [searchInput]);

  const hasActiveFilters =
    Boolean(debouncedSearch) ||
    hasActiveFilter !== "all" ||
    hasDraftFilter !== "all" ||
    healthFilter !== "all" ||
    ordering !== "name";

  const handleResetFilters = () => {
    setSearchInput("");
    setDebouncedSearch("");
    setHasActiveFilter("all");
    setHasDraftFilter("all");
    setHealthFilter("all");
    setOrdering("name");
    setPage(1);
  };

  const fetchPlans = useCallback(async () => {
    const currentSeq = ++requestSeqRef.current;
    setIsLoading(true);
    setError(null);
    setLiveAnnouncement("Loading commercial plans...");

    try {
      const params: PlanListParams = {
        page,
        page_size: pageSize,
        search: debouncedSearch || undefined,
        has_active_version: hasActiveFilter !== "all" ? (hasActiveFilter as "true" | "false") : undefined,
        has_draft_version: hasDraftFilter !== "all" ? (hasDraftFilter as "true" | "false") : undefined,
        catalog_health: healthFilter !== "all" ? (healthFilter as "healthy" | "degraded") : undefined,
        ordering: ordering || undefined,
      };

      const response = await plansApi.list(params);

      if (currentSeq === requestSeqRef.current) {
        setPlans(response.results as PlanListItem[]);
        setTotalCount(response.count);
        setIsLoading(false);
        setLiveAnnouncement(`Loaded ${response.results.length} plans. Total ${response.count} items.`);
      }
    } catch {
      if (currentSeq === requestSeqRef.current) {
        setIsLoading(false);
        const msg = "Unable to load plans. Please check your connection and try again.";
        setError(msg);
        setLiveAnnouncement(msg);
      }
    }
  }, [page, pageSize, debouncedSearch, hasActiveFilter, hasDraftFilter, healthFilter, ordering]);

  useEffect(() => {
    fetchPlans();
  }, [fetchPlans]);

  const handleOpenCreate = (btnElement: HTMLElement) => {
    triggerRef.current = btnElement;
    setIsCreateOpen(true);
  };

  const handleOpenEdit = (plan: PlanListItem, btnElement: HTMLElement) => {
    triggerRef.current = btnElement;
    setSelectedPlan(plan);
    setIsEditOpen(true);
  };

  const handleCreateSuccess = (newPlan: PlanDetail) => {
    setLiveAnnouncement(`Plan ${newPlan.name} created successfully.`);
    fetchPlans();
    navigate(`/plans/${newPlan.id}`);
  };

  const handleEditSuccess = (updatedPlan: PlanDetail) => {
    setLiveAnnouncement(`Plan ${updatedPlan.name} updated successfully.`);
    fetchPlans();
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

  const totalPages = Math.max(1, Math.ceil(totalCount / pageSize));

  return (
    <AppShell>
      {/* Live Region for Screen Readers */}
      <div className="sr-only" aria-live="polite" aria-atomic="true">
        {liveAnnouncement}
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem", minWidth: 0 }}>
        {/* Page Header */}
        <div className="registry-page-header">
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", flexWrap: "wrap" }}>
              <h1 className="heading-hero" style={{ fontSize: "1.625rem", margin: 0 }}>
                Plans &amp; Pricing
              </h1>
              {!isLoading && (
                <span className="registry-count-badge">
                  {totalCount} {totalCount === 1 ? "Plan" : "Plans"}
                </span>
              )}
            </div>
            <p className="text-body" style={{ maxWidth: "780px", fontSize: "0.875rem", marginTop: "0.35rem" }}>
              Commercial packaging and versioned tier definitions. Configure immutable pricing, features, capabilities, and quotas across lifecycle releases.
            </p>
          </div>

          <button
            type="button"
            className="btn btn-primary"
            onClick={(e) => handleOpenCreate(e.currentTarget)}
            style={{ flexShrink: 0 }}
          >
            <PlusIcon size={16} />
            Create Plan
          </button>
        </div>

        {/* Filter & Search Bar */}
        <div className="registry-controls-bar" style={{ flexWrap: "wrap", gap: "0.75rem" }}>
          {/* Search Box */}
          <div className="search-input-wrapper" style={{ minWidth: "220px", flex: "1 1 220px" }}>
            <span className="search-icon-adornment" aria-hidden="true">
              <SearchIcon size={16} />
            </span>
            <input
              type="search"
              className="registry-search-input"
              placeholder="Search by code or plan name..."
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              aria-label="Search plans by code or name"
            />
          </div>

          {/* Has Active Version Filter */}
          <div className="status-filter-wrapper">
            <span className="filter-icon-adornment" aria-hidden="true">
              <FilterIcon size={15} />
            </span>
            <select
              className="registry-filter-select"
              value={hasActiveFilter}
              onChange={(e) => {
                setHasActiveFilter(e.target.value);
                setPage(1);
              }}
              aria-label="Filter by active version presence"
            >
              <option value="all">Active: All</option>
              <option value="true">Has Active Version</option>
              <option value="false">No Active Version</option>
            </select>
            <span className="filter-chevron-adornment" aria-hidden="true">
              <ChevronDownIcon size={15} />
            </span>
          </div>

          {/* Has Draft Version Filter */}
          <div className="status-filter-wrapper">
            <span className="filter-icon-adornment" aria-hidden="true">
              <FilterIcon size={15} />
            </span>
            <select
              className="registry-filter-select"
              value={hasDraftFilter}
              onChange={(e) => {
                setHasDraftFilter(e.target.value);
                setPage(1);
              }}
              aria-label="Filter by draft version presence"
            >
              <option value="all">Draft: All</option>
              <option value="true">Has Draft Version</option>
              <option value="false">No Draft Version</option>
            </select>
            <span className="filter-chevron-adornment" aria-hidden="true">
              <ChevronDownIcon size={15} />
            </span>
          </div>

          {/* Catalog Health Filter */}
          <div className="status-filter-wrapper">
            <span className="filter-icon-adornment" aria-hidden="true">
              <FilterIcon size={15} />
            </span>
            <select
              className="registry-filter-select"
              value={healthFilter}
              onChange={(e) => {
                setHealthFilter(e.target.value);
                setPage(1);
              }}
              aria-label="Filter by catalog health"
            >
              <option value="all">Health: All</option>
              <option value="healthy">Healthy</option>
              <option value="degraded">Degraded</option>
            </select>
            <span className="filter-chevron-adornment" aria-hidden="true">
              <ChevronDownIcon size={15} />
            </span>
          </div>

          {/* Ordering Selector */}
          <div className="status-filter-wrapper">
            <select
              className="registry-filter-select"
              value={ordering}
              onChange={(e) => {
                setOrdering(e.target.value);
                setPage(1);
              }}
              aria-label="Sort order"
            >
              <option value="name">Name (A–Z)</option>
              <option value="-name">Name (Z–A)</option>
              <option value="code">Code (A–Z)</option>
              <option value="-code">Code (Z–A)</option>
              <option value="-created_at">Newest First</option>
              <option value="created_at">Oldest First</option>
            </select>
            <span className="filter-chevron-adornment" aria-hidden="true">
              <ChevronDownIcon size={15} />
            </span>
          </div>

          {/* Clear Filters Action */}
          {hasActiveFilters && (
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              onClick={handleResetFilters}
              style={{ display: "inline-flex", alignItems: "center", gap: "0.35rem" }}
              aria-label="Reset all filters"
            >
              <RotateCcwIcon size={14} />
              Reset
            </button>
          )}
        </div>

        {/* Error Alert */}
        {error && (
          <div className="alert-banner alert-banner-error" role="alert">
            <span>{error}</span>
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              onClick={fetchPlans}
              style={{ marginLeft: "auto" }}
            >
              Retry
            </button>
          </div>
        )}

        {/* Loading Skeleton */}
        {isLoading && (
          <div className="registry-skeleton-container" aria-label="Loading plans list">
            <div className="skeleton-row" />
            <div className="skeleton-row" />
            <div className="skeleton-row" />
          </div>
        )}

        {/* Data Table or Empty States */}
        {!isLoading && !error && (
          <>
            {plans.length > 0 ? (
              <>
                <div className="product-table-container">
                  {/* Desktop & Tablet Table */}
                  <div className="table-responsive desktop-tablet-view">
                    <table className="enterprise-table" aria-label="Plans Directory">
                      <thead>
                        <tr>
                          <th scope="col" style={{ width: "16%" }}>Plan Code</th>
                          <th scope="col" style={{ width: "24%" }}>Name &amp; Description</th>
                          <th scope="col" style={{ width: "16%" }}>Active Version</th>
                          <th scope="col" style={{ width: "12%" }}>Latest</th>
                          <th scope="col" style={{ width: "12%" }}>Catalog Health</th>
                          <th scope="col" style={{ width: "20%", textAlign: "right" }}>Actions</th>
                        </tr>
                      </thead>
                      <tbody>
                        {plans.map((item) => (
                          <tr key={item.id} className="table-row">
                            <td>
                              <span className="product-code-pill">{item.code}</span>
                            </td>
                            <td>
                              <div style={{ display: "flex", flexDirection: "column", gap: "0.2rem" }}>
                                <span className="product-name">{item.name}</span>
                                {item.description && (
                                  <span className="product-description">{item.description}</span>
                                )}
                              </div>
                            </td>
                            <td>
                              {item.active_version ? (
                                <div style={{ display: "inline-flex", alignItems: "center", gap: "0.35rem" }}>
                                  <span className="product-code-pill">v{item.active_version.version}</span>
                                  <PlanVersionStatusBadge status={item.active_version.status} />
                                </div>
                              ) : (
                                <span className="text-caption" style={{ fontStyle: "italic" }}>None</span>
                              )}
                            </td>
                            <td>
                              {item.latest_version ? (
                                <span className="product-code-pill">v{item.latest_version.version}</span>
                              ) : (
                                "—"
                              )}
                              <span className="text-caption" style={{ display: "block", marginTop: "0.15rem" }}>
                                {item.total_versions_count} {item.total_versions_count === 1 ? "ver" : "vers"}
                              </span>
                            </td>
                            <td>
                              <CatalogHealthBadge health={item.catalog_health} />
                            </td>
                            <td style={{ textAlign: "right" }}>
                              <div
                                style={{
                                  display: "inline-flex",
                                  alignItems: "center",
                                  gap: "0.5rem",
                                  justifyContent: "flex-end",
                                }}
                              >
                                <button
                                  type="button"
                                  className="btn btn-primary btn-sm"
                                  onClick={() => navigate(`/plans/${item.id}`)}
                                  aria-label={`View plan ${item.name}`}
                                >
                                  <LayersIcon size={14} />
                                  View Plan
                                </button>
                                <button
                                  type="button"
                                  className="btn btn-secondary btn-sm"
                                  onClick={(e) => handleOpenEdit(item, e.currentTarget)}
                                  aria-label={`Edit ${item.name}`}
                                >
                                  <EditIcon size={14} />
                                  Edit
                                </button>
                              </div>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>

                  {/* Mobile Card List View (<768px) */}
                  <div className="mobile-card-list">
                    {plans.map((item) => (
                      <div key={item.id} className="mobile-product-card">
                        <div className="mobile-card-header">
                          <span className="product-code-pill">{item.code}</span>
                          <CatalogHealthBadge health={item.catalog_health} />
                        </div>
                        <div className="mobile-card-body">
                          <h3 className="mobile-product-name">{item.name}</h3>
                          {item.description && (
                            <p className="mobile-product-desc">{item.description}</p>
                          )}
                          <div style={{ display: "flex", gap: "0.5rem", alignItems: "center", marginTop: "0.5rem", flexWrap: "wrap" }}>
                            <span className="text-caption">
                              Active: {item.active_version ? `v${item.active_version.version}` : "None"}
                            </span>
                            <span className="text-caption">•</span>
                            <span className="text-caption">
                              Latest: {item.latest_version ? `v${item.latest_version.version}` : "—"} ({item.total_versions_count} total)
                            </span>
                          </div>
                        </div>
                        <div className="mobile-card-footer">
                          <span className="text-caption">Updated {formatDate(item.updated_at)}</span>
                          <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
                            <button
                              type="button"
                              className="btn btn-primary btn-sm"
                              onClick={() => navigate(`/plans/${item.id}`)}
                              aria-label={`View plan ${item.name}`}
                              style={{ minHeight: "44px" }}
                            >
                              <LayersIcon size={14} />
                              View Plan
                            </button>
                            <button
                              type="button"
                              className="btn btn-secondary btn-sm"
                              onClick={(e) => handleOpenEdit(item, e.currentTarget)}
                              aria-label={`Edit ${item.name}`}
                              style={{ minHeight: "44px" }}
                            >
                              <EditIcon size={14} />
                              Edit
                            </button>
                          </div>
                        </div>
                      </div>
                    ))}
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
              /* Truthful Empty State */
              <div className="registry-empty-card">
                <div className="empty-icon-circle">
                  <LayersIcon size={28} />
                </div>
                {hasActiveFilters ? (
                  <>
                    <h3 className="empty-title">No matching plans found</h3>
                    <p className="empty-desc">
                      No commercial plans matched your active search or filters. Try adjusting your query or resetting filters.
                    </p>
                    <button
                      type="button"
                      className="btn btn-secondary btn-sm"
                      onClick={handleResetFilters}
                    >
                      Clear Filters
                    </button>
                  </>
                ) : (
                  <>
                    <h3 className="empty-title">No plans established</h3>
                    <p className="empty-desc">
                      There are currently no commercial plans registered in the catalog. Create your first plan family to begin versioning and packaging.
                    </p>
                    <button
                      type="button"
                      className="btn btn-primary"
                      onClick={(e) => handleOpenCreate(e.currentTarget)}
                    >
                      <PlusIcon size={16} />
                      Create Plan
                    </button>
                  </>
                )}
              </div>
            )}
          </>
        )}
      </div>

      {/* Dialogs */}
      <CreatePlanDialog
        isOpen={isCreateOpen}
        onClose={() => setIsCreateOpen(false)}
        onSuccess={handleCreateSuccess}
        triggerRef={triggerRef}
      />

      <EditPlanDialog
        plan={selectedPlan}
        isOpen={isEditOpen}
        onClose={() => setIsEditOpen(false)}
        onSuccess={handleEditSuccess}
        triggerRef={triggerRef}
      />
    </AppShell>
  );
};
