/**
 * Organization Product Access Management Page.
 *
 * Provides Platform Owners with centralized organization-level product access management:
 * debounced search with sequence guards, independent server-side paginated organization,
 * product, and lifecycle filters, server-side pagination, accessible modal dialogs,
 * and truthful empty states.
 */

import React, { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { entitlementsApi } from "../api/entitlements.ts";
import { organizationsApi } from "../api/organizations.ts";
import { productsApi } from "../api/products.ts";
import type {
  EntitlementDetail,
  EntitlementListItem,
  OrganizationListItem,
  ProductListItem,
} from "../api/types.ts";
import { AppShell } from "../components/AppShell.tsx";
import { EntitlementFormDialog } from "../components/entitlements/EntitlementFormDialog.tsx";
import { EntitlementListTable } from "../components/entitlements/EntitlementListTable.tsx";
import {
  ChevronDownIcon,
  FilterIcon,
  PlusIcon,
  SearchIcon,
  ShieldCheckIcon,
} from "../components/Icons.tsx";

export const OrganizationProductAccessPage: React.FC = () => {
  // Main entitlements list state
  const [entitlements, setEntitlements] = useState<EntitlementListItem[]>([]);
  const [totalCount, setTotalCount] = useState<number>(0);
  const [page, setPage] = useState<number>(1);
  const pageSize = 10;

  const [searchInput, setSearchInput] = useState<string>("");
  const [debouncedSearch, setDebouncedSearch] = useState<string>("");
  const [statusFilter, setStatusFilter] = useState<string>("");

  // Organization filter state (server-side searchable and paginated)
  const [orgFilter, setOrgFilter] = useState<string>("");
  const [selectedOrgOption, setSelectedOrgOption] = useState<OrganizationListItem | null>(null);
  const [orgFilterSearch, setOrgFilterSearch] = useState<string>("");
  const [debouncedOrgFilterSearch, setDebouncedOrgFilterSearch] = useState<string>("");
  const [orgOptionPage, setOrgOptionPage] = useState<number>(1);
  const [totalOrgOptionCount, setTotalOrgOptionCount] = useState<number>(0);
  const [orgOptions, setOrgOptions] = useState<OrganizationListItem[]>([]);
  const [orgOptionsLoading, setOrgOptionsLoading] = useState<boolean>(false);
  const orgFilterSeqRef = useRef<number>(0);

  // Product filter state (server-side searchable and paginated)
  const [prodFilter, setProdFilter] = useState<string>("");
  const [selectedProdOption, setSelectedProdOption] = useState<ProductListItem | null>(null);
  const [prodFilterSearch, setProdFilterSearch] = useState<string>("");
  const [debouncedProdFilterSearch, setDebouncedProdFilterSearch] = useState<string>("");
  const [prodOptionPage, setProdOptionPage] = useState<number>(1);
  const [totalProdOptionCount, setTotalProdOptionCount] = useState<number>(0);
  const [prodOptions, setProdOptions] = useState<ProductListItem[]>([]);
  const [prodOptionsLoading, setProdOptionsLoading] = useState<boolean>(false);
  const prodFilterSeqRef = useRef<number>(0);

  const filterOptionPageSize = 20;

  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [liveAnnouncement, setLiveAnnouncement] = useState<string>("");
  const [refreshKey, setRefreshKey] = useState<number>(0);

  // Dialog state
  const [isDialogOpen, setIsDialogOpen] = useState<boolean>(false);
  const [dialogMode, setDialogMode] = useState<"create" | "edit">("create");
  const [selectedEntitlement, setSelectedEntitlement] = useState<EntitlementListItem | null>(null);
  const triggerRef = useRef<HTMLElement | null>(null);

  // Entitlement request sequence guard
  const requestSeqRef = useRef<number>(0);

  // Fetch Organization filter options (single page request, no all-pages loop)
  const fetchOrgOptions = useCallback(async (query: string, pageNum: number) => {
    const seq = ++orgFilterSeqRef.current;
    setOrgOptionsLoading(true);
    try {
      const res = await organizationsApi.list({
        search: query || undefined,
        page: pageNum,
        page_size: filterOptionPageSize,
      });
      if (seq === orgFilterSeqRef.current) {
        setOrgOptions(res.results as OrganizationListItem[]);
        setTotalOrgOptionCount(res.count);
        setOrgOptionsLoading(false);
      }
    } catch {
      if (seq === orgFilterSeqRef.current) {
        setOrgOptionsLoading(false);
      }
    }
  }, []);

  // Fetch Product filter options (single page request, no all-pages loop)
  const fetchProdOptions = useCallback(async (query: string, pageNum: number) => {
    const seq = ++prodFilterSeqRef.current;
    setProdOptionsLoading(true);
    try {
      const res = await productsApi.list({
        search: query || undefined,
        page: pageNum,
        page_size: filterOptionPageSize,
      });
      if (seq === prodFilterSeqRef.current) {
        setProdOptions(res.results as ProductListItem[]);
        setTotalProdOptionCount(res.count);
        setProdOptionsLoading(false);
      }
    } catch {
      if (seq === prodFilterSeqRef.current) {
        setProdOptionsLoading(false);
      }
    }
  }, []);

  // Debounced search trigger for Organization filter options (300ms)
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedOrgFilterSearch(orgFilterSearch.trim());
      setOrgOptionPage(1);
    }, 300);
    return () => clearTimeout(timer);
  }, [orgFilterSearch]);

  // Fetch Organization options when debounced query or option page changes
  useEffect(() => {
    fetchOrgOptions(debouncedOrgFilterSearch, orgOptionPage);
  }, [debouncedOrgFilterSearch, orgOptionPage, fetchOrgOptions]);

  // Debounced search trigger for Product filter options (300ms)
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedProdFilterSearch(prodFilterSearch.trim());
      setProdOptionPage(1);
    }, 300);
    return () => clearTimeout(timer);
  }, [prodFilterSearch]);

  // Fetch Product options when debounced query or option page changes
  useEffect(() => {
    fetchProdOptions(debouncedProdFilterSearch, prodOptionPage);
  }, [debouncedProdFilterSearch, prodOptionPage, fetchProdOptions]);

  // Debounce main search input (300ms)
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearch(searchInput.trim());
      setPage(1);
    }, 300);
    return () => clearTimeout(timer);
  }, [searchInput]);

  // Status filter handler (updates state only, letting effect perform fetch)
  const handleStatusFilterChange = (newStatus: string) => {
    setStatusFilter(newStatus);
    setPage(1);
  };

  // Selected-option preservation logic for Organization filter
  const displayedOrgOptions = selectedOrgOption && !orgOptions.some((o) => o.id === selectedOrgOption.id)
    ? [selectedOrgOption, ...orgOptions]
    : orgOptions;

  // Organization filter handler (updates state only, letting effect perform fetch after commit)
  const handleOrgFilterChange = (newOrgId: string) => {
    const found = displayedOrgOptions.find((o) => o.id === newOrgId) || null;
    setSelectedOrgOption(found);
    setOrgFilter(newOrgId);
    setPage(1);
  };

  // Selected-option preservation logic for Product filter
  const displayedProdOptions = selectedProdOption && !prodOptions.some((p) => p.id === selectedProdOption.id)
    ? [selectedProdOption, ...prodOptions]
    : prodOptions;

  // Product filter handler (updates state only, letting effect perform fetch after commit)
  const handleProdFilterChange = (newProdId: string) => {
    const found = displayedProdOptions.find((p) => p.id === newProdId) || null;
    setSelectedProdOption(found);
    setProdFilter(newProdId);
    setPage(1);
  };

  // Entitlement-list fetching effect driven strictly by committed state
  useEffect(() => {
    let isCancelled = false;
    const currentSeq = ++requestSeqRef.current;

    setIsLoading(true);
    setError(null);
    setLiveAnnouncement("Loading product access authorizations...");

    const params = {
      page,
      page_size: pageSize,
      search: debouncedSearch || undefined,
      status: statusFilter || undefined,
      organization_id: orgFilter || undefined,
      product_id: prodFilter || undefined,
    };

    entitlementsApi
      .list(params)
      .then((response) => {
        if (!isCancelled && currentSeq === requestSeqRef.current) {
          setEntitlements(response.results as EntitlementListItem[]);
          setTotalCount(response.count);
          setIsLoading(false);
          setLiveAnnouncement(
            `Loaded ${response.results.length} authorizations. Total ${response.count} records.`
          );
        }
      })
      .catch((err: any) => {
        if (!isCancelled && currentSeq === requestSeqRef.current) {
          setIsLoading(false);
          // Out-of-range page recovery: safely resets to page 1 only if page > 1, avoiding repeated 404 loops
          if ((err?.status === 404 || err?.response?.status === 404) && page > 1) {
            setPage(1);
            return;
          }
          const msg = "Unable to load product access authorizations. Please check your connection and try again.";
          setError(msg);
          setLiveAnnouncement(msg);
        }
      });

    return () => {
      isCancelled = true;
    };
  }, [page, pageSize, debouncedSearch, statusFilter, orgFilter, prodFilter, refreshKey]);

  const handleOpenCreate = (btnElement: HTMLElement) => {
    triggerRef.current = btnElement;
    setDialogMode("create");
    setSelectedEntitlement(null);
    setIsDialogOpen(true);
  };

  const handleOpenEdit = (ent: EntitlementListItem, btnElement: HTMLElement) => {
    triggerRef.current = btnElement;
    setDialogMode("edit");
    setSelectedEntitlement(ent);
    setIsDialogOpen(true);
  };

  const handleDialogSuccess = (ent: EntitlementDetail) => {
    if (dialogMode === "create") {
      setLiveAnnouncement(`Product access for ${ent.organization.name} - ${ent.product.name} registered.`);
    } else {
      setLiveAnnouncement(`Product access for ${ent.organization.name} updated to ${ent.status}.`);
    }
    setRefreshKey((k) => k + 1);
  };

  const totalPages = Math.max(1, Math.ceil(totalCount / pageSize));

  // Correct page if totalCount drops below current page bounds
  useEffect(() => {
    if (page > totalPages && totalCount > 0) {
      setPage(totalPages);
    }
  }, [page, totalPages, totalCount]);

  const isFiltered = Boolean(searchInput || statusFilter || orgFilter || prodFilter);

  const totalOrgOptionPages = Math.max(1, Math.ceil(totalOrgOptionCount / filterOptionPageSize));
  const totalProdOptionPages = Math.max(1, Math.ceil(totalProdOptionCount / filterOptionPageSize));

  return (
    <AppShell>
      {/* Live Region for Screen Readers */}
      <div className="sr-only" aria-live="polite" aria-atomic="true">
        {liveAnnouncement}
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem", minWidth: 0, padding: "2rem", maxWidth: "1400px", margin: "0 auto" }}>
        {/* Breadcrumb Navigation */}
        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", fontSize: "0.8125rem", color: "var(--text-muted)", marginBottom: "0.25rem", fontWeight: 500 }}>
          <Link to="/" style={{ color: "var(--text-muted)", textDecoration: "none", transition: "color 0.15s" }}>Platform Owner</Link>
          <span>/</span>
          <span>Customer Operations</span>
          <span>/</span>
          <span style={{ color: "var(--brand-primary)", fontWeight: 600 }}>Organization Product Access</span>
        </div>

        {/* Page Header */}
        <div className="registry-page-header" style={{ marginBottom: "0.5rem" }}>
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
              <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", flexWrap: "wrap" }}>
                <h1 className="heading-hero" style={{ margin: 0, fontSize: "1.75rem", fontWeight: 800, letterSpacing: "-0.02em", color: "var(--text-primary)" }}>
                  Organization Product Access
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
                  aria-label={`${totalCount} total product access records`}
                >
                  {totalCount} {totalCount === 1 ? "access record" : "access records"}
                </span>
              </div>
              <p className="registry-page-desc" style={{ marginTop: "0.25rem", color: "var(--text-secondary)", fontSize: "0.9375rem" }}>
                Manage product authorization grants for registered customer organizations.
              </p>
            </div>
          </div>

          <button
            type="button"
            className="btn btn-gradient"
            onClick={(e) => handleOpenCreate(e.currentTarget)}
            style={{ flexShrink: 0 }}
          >
            <PlusIcon size={16} />
            Register Product Access
          </button>
        </div>

        {/* Controls and Filter Toolbar */}
        <div className="registry-controls-grid">
          {/* Main Search */}
          <div className="search-input-wrapper">
            <span className="search-icon-adornment" aria-hidden="true">
              <SearchIcon size={16} />
            </span>
            <input
              type="search"
              className="registry-search-input"
              placeholder="Search authorizations by organization or product..."
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              aria-label="Search product access records"
            />
          </div>

          {/* Organization Filter with Independent Server-Side Search & Pagination */}
          <div className="filter-group-container">
            <div className="filter-wrapper">
              <span className="filter-icon-adornment" aria-hidden="true">
                <FilterIcon size={14} />
              </span>
              <select
                className="registry-filter-select"
                value={orgFilter}
                onChange={(e) => handleOrgFilterChange(e.target.value)}
                aria-label="Filter by organization"
              >
                <option value="">All Organizations</option>
                {displayedOrgOptions.map((o) => (
                  <option key={o.id} value={o.id}>
                    {o.name} ({o.code})
                  </option>
                ))}
              </select>
              <span className="filter-chevron-adornment" aria-hidden="true">
                <ChevronDownIcon size={14} />
              </span>
            </div>
            <div className="filter-inline-search-bar">
              <input
                type="search"
                className="filter-search-mini-input"
                placeholder="Filter org options..."
                value={orgFilterSearch}
                onChange={(e) => setOrgFilterSearch(e.target.value)}
                aria-label="Search organization options"
              />
              {totalOrgOptionCount > filterOptionPageSize && (
                <div className="filter-mini-pagination">
                  <button
                    type="button"
                    className="filter-mini-btn"
                    disabled={orgOptionPage <= 1 || orgOptionsLoading}
                    onClick={() => setOrgOptionPage((p) => Math.max(1, p - 1))}
                    aria-label="Previous page of organizations"
                  >
                    Prev
                  </button>
                  <span className="filter-mini-indicator" aria-live="polite">
                    {orgOptionPage}/{totalOrgOptionPages}
                  </span>
                  <button
                    type="button"
                    className="filter-mini-btn"
                    disabled={orgOptionPage >= totalOrgOptionPages || orgOptionsLoading}
                    onClick={() => setOrgOptionPage((p) => Math.min(totalOrgOptionPages, p + 1))}
                    aria-label="Next page of organizations"
                  >
                    Next
                  </button>
                </div>
              )}
            </div>
          </div>

          {/* Product Filter with Independent Server-Side Search & Pagination */}
          <div className="filter-group-container">
            <div className="filter-wrapper">
              <span className="filter-icon-adornment" aria-hidden="true">
                <FilterIcon size={14} />
              </span>
              <select
                className="registry-filter-select"
                value={prodFilter}
                onChange={(e) => handleProdFilterChange(e.target.value)}
                aria-label="Filter by product"
              >
                <option value="">All Products</option>
                {displayedProdOptions.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name} ({p.code})
                  </option>
                ))}
              </select>
              <span className="filter-chevron-adornment" aria-hidden="true">
                <ChevronDownIcon size={14} />
              </span>
            </div>
            <div className="filter-inline-search-bar">
              <input
                type="search"
                className="filter-search-mini-input"
                placeholder="Filter product options..."
                value={prodFilterSearch}
                onChange={(e) => setProdFilterSearch(e.target.value)}
                aria-label="Search product options"
              />
              {totalProdOptionCount > filterOptionPageSize && (
                <div className="filter-mini-pagination">
                  <button
                    type="button"
                    className="filter-mini-btn"
                    disabled={prodOptionPage <= 1 || prodOptionsLoading}
                    onClick={() => setProdOptionPage((p) => Math.max(1, p - 1))}
                    aria-label="Previous page of products"
                  >
                    Prev
                  </button>
                  <span className="filter-mini-indicator" aria-live="polite">
                    {prodOptionPage}/{totalProdOptionPages}
                  </span>
                  <button
                    type="button"
                    className="filter-mini-btn"
                    disabled={prodOptionPage >= totalProdOptionPages || prodOptionsLoading}
                    onClick={() => setProdOptionPage((p) => Math.min(totalProdOptionPages, p + 1))}
                    aria-label="Next page of products"
                  >
                    Next
                  </button>
                </div>
              )}
            </div>
          </div>

          {/* Status Filter */}
          <div className="filter-group-container">
            <div className="filter-wrapper">
              <span className="filter-icon-adornment" aria-hidden="true">
                <FilterIcon size={14} />
              </span>
              <select
                className="registry-filter-select"
                value={statusFilter}
                onChange={(e) => handleStatusFilterChange(e.target.value)}
                aria-label="Filter by lifecycle status"
              >
                <option value="">All Statuses</option>
                <option value="draft">Draft</option>
                <option value="active">Active</option>
                <option value="suspended">Suspended</option>
                <option value="revoked">Revoked</option>
              </select>
              <span className="filter-chevron-adornment" aria-hidden="true">
                <ChevronDownIcon size={14} />
              </span>
            </div>
          </div>
        </div>

        {/* Error Alert */}
        {error && (
          <div className="alert-banner alert-banner-error" role="alert">
            <span>{error}</span>
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              onClick={() => setRefreshKey((k) => k + 1)}
              style={{ marginLeft: "auto", minHeight: "44px", minWidth: "44px" }}
            >
              Retry
            </button>
          </div>
        )}

        {/* Loading State */}
        {isLoading ? (
          <div className="registry-loading-card" role="status" aria-label="Loading product authorizations">
            <div className="loading-spinner" aria-hidden="true" />
            <span style={{ fontSize: "0.875rem", color: "var(--text-secondary)" }}>
              Loading product access authorizations...
            </span>
          </div>
        ) : (
          <>
            {entitlements.length > 0 ? (
              <>
                {/* Entitlement Table & Mobile Cards */}
                <EntitlementListTable
                  entitlements={entitlements}
                  onEdit={handleOpenEdit}
                />

                {/* Table Footer with Pagination */}
                {totalPages > 1 && (
                  <div className="registry-pagination-bar">
                    <span className="pagination-info">
                      Showing {(page - 1) * pageSize + 1} to{" "}
                      {Math.min(page * pageSize, totalCount)} of {totalCount} authorizations
                    </span>
                    <div className="pagination-controls">
                      <button
                        type="button"
                        className="btn btn-secondary btn-sm"
                        onClick={() => setPage((p) => Math.max(p - 1, 1))}
                        disabled={page <= 1}
                        aria-label="Previous page"
                        style={{ minHeight: "44px", minWidth: "44px" }}
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
                        style={{ minHeight: "44px", minWidth: "44px" }}
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
                  <ShieldCheckIcon size={28} />
                </div>
                {isFiltered ? (
                  <>
                    <h3 className="empty-title">No matching authorizations found</h3>
                    <p className="empty-desc">
                      No product access records matched your active search query or filter. Try adjusting your search query or resetting filters.
                    </p>
                    <button
                      type="button"
                      className="btn btn-secondary btn-sm"
                      onClick={() => {
                        setSearchInput("");
                        setStatusFilter("");
                        setOrgFilter("");
                        setSelectedOrgOption(null);
                        setOrgFilterSearch("");
                        setOrgOptionPage(1);
                        setProdFilter("");
                        setSelectedProdOption(null);
                        setProdFilterSearch("");
                        setProdOptionPage(1);
                        setPage(1);
                      }}
                      style={{ minHeight: "44px" }}
                    >
                      Clear Filters
                    </button>
                  </>
                ) : (
                  <>
                    <h3 className="empty-title">No product access registered</h3>
                    <p className="empty-desc">
                      No customer organizations have been granted product access yet. Authorize an active organization to begin product entitlement management.
                    </p>
                    <button
                      type="button"
                      className="btn btn-primary"
                      onClick={(e) => handleOpenCreate(e.currentTarget)}
                      style={{ minHeight: "44px" }}
                    >
                      <PlusIcon size={16} />
                      Register First Product Access
                    </button>
                  </>
                )}
              </div>
            )}
          </>
        )}
      </div>

      {/* Register / Edit Entitlement Dialog */}
      <EntitlementFormDialog
        isOpen={isDialogOpen}
        mode={dialogMode}
        entitlement={selectedEntitlement}
        onClose={() => setIsDialogOpen(false)}
        onSuccess={handleDialogSuccess}
        triggerRef={triggerRef}
      />

      <style>{`
        .registry-page-header {
          display: flex;
          align-items: flex-start;
          justify-content: space-between;
          gap: 1rem;
          flex-wrap: wrap;
        }

        .registry-page-title {
          font-size: 1.5rem;
          font-weight: 700;
          color: var(--text-primary);
          margin: 0;
          letter-spacing: -0.02em;
        }

        .registry-count-badge {
          display: inline-flex;
          align-items: center;
          padding: 0.2rem 0.65rem;
          border-radius: 20px;
          font-size: 0.75rem;
          font-weight: 600;
          background: var(--brand-primary-light);
          color: var(--brand-primary);
          border: 1px solid var(--border-glass);
        }

        .registry-page-desc {
          font-size: 0.875rem;
          color: var(--text-secondary);
          margin: 0.35rem 0 0 0;
        }

        .registry-controls-grid {
          display: flex;
          align-items: flex-start;
          gap: 0.75rem;
          width: 100%;
          flex-wrap: wrap;
        }

        .search-input-wrapper {
          position: relative;
          flex: 2;
          min-width: 240px;
          display: flex;
          align-items: center;
        }

        .search-icon-adornment {
          position: absolute;
          left: 1rem;
          top: 50%;
          transform: translateY(-50%);
          color: var(--text-muted);
          pointer-events: none;
          display: flex;
          align-items: center;
          justify-content: center;
          z-index: 1;
        }

        .registry-search-input {
          width: 100%;
          min-height: 44px;
          height: 44px;
          padding: 0.5rem 1rem 0.5rem 2.5rem;
          font-size: 0.875rem;
          font-family: inherit;
          border-radius: 10px;
          border: 1px solid var(--input-border);
          background: var(--input-bg);
          color: var(--text-primary);
          outline: none;
          box-shadow: var(--shadow-sm);
          transition: border-color 0.15s ease, box-shadow 0.15s ease;
        }

        .registry-search-input:hover:not(:disabled) {
          border-color: var(--border-strong);
        }

        .registry-search-input:focus {
          border-color: var(--input-border-focus);
          box-shadow: 0 0 0 3px var(--brand-primary-light);
        }

        .filter-group-container {
          flex: 1;
          min-width: 220px;
          display: flex;
          flex-direction: column;
          gap: 0.35rem;
          box-sizing: border-box;
          background: var(--glass-surface);
          border: 1px solid var(--border-subtle);
          border-radius: 10px;
          padding: 0.35rem;
        }

        .filter-wrapper {
          position: relative;
          width: 100%;
          display: flex;
          align-items: center;
        }

        .filter-inline-search-bar {
          display: flex;
          align-items: center;
          gap: 0.35rem;
          width: 100%;
          box-sizing: border-box;
        }

        .filter-search-mini-input {
          flex: 1;
          min-width: 0;
          min-height: 32px;
          height: 32px;
          padding: 0.25rem 0.5rem;
          font-size: 0.75rem;
          font-family: inherit;
          border-radius: 6px;
          border: 1px solid var(--border-subtle);
          background: var(--glass-surface-elevated);
          color: var(--text-primary);
          outline: none;
          box-sizing: border-box;
          transition: border-color 0.15s ease, box-shadow 0.15s ease;
        }

        .filter-search-mini-input:focus {
          border-color: var(--input-border-focus);
          box-shadow: 0 0 0 2px var(--brand-primary-light);
        }

        .filter-mini-pagination {
          display: flex;
          align-items: center;
          gap: 0.25rem;
          flex-shrink: 0;
        }

        .filter-mini-btn {
          min-height: 32px;
          min-width: 32px;
          height: 32px;
          padding: 0.15rem 0.45rem;
          font-size: 0.75rem;
          font-weight: 500;
          font-family: inherit;
          border-radius: 6px;
          border: 1px solid var(--border-subtle);
          background: var(--glass-surface-elevated);
          color: var(--text-primary);
          cursor: pointer;
          display: inline-flex;
          align-items: center;
          justify-content: center;
          box-sizing: border-box;
          transition: background 0.15s ease, border-color 0.15s ease;
        }

        .filter-mini-btn:hover:not(:disabled) {
          background: var(--glass-surface-hover);
          border-color: var(--border-strong);
        }

        .filter-mini-btn:focus-visible {
          outline: none;
          border-color: var(--input-border-focus);
          box-shadow: 0 0 0 3px var(--brand-primary-light);
        }

        .filter-mini-btn:disabled {
          opacity: 0.5;
          cursor: not-allowed;
        }

        .filter-mini-indicator {
          font-size: 0.75rem;
          color: var(--text-muted);
          font-weight: 500;
          white-space: nowrap;
          padding: 0 0.25rem;
          min-width: 2.5rem;
          text-align: center;
        }

        .filter-icon-adornment {
          position: absolute;
          left: 0.75rem;
          top: 50%;
          transform: translateY(-50%);
          color: var(--text-muted);
          pointer-events: none;
          display: flex;
          align-items: center;
          justify-content: center;
          z-index: 1;
        }

        .filter-chevron-adornment {
          position: absolute;
          right: 0.75rem;
          top: 50%;
          transform: translateY(-50%);
          color: var(--text-muted);
          pointer-events: none;
          display: flex;
          align-items: center;
          justify-content: center;
          z-index: 1;
        }

        .registry-filter-select {
          width: 100%;
          min-height: 38px;
          height: 38px;
          padding: 0.35rem 2rem 0.35rem 2.1rem;
          font-size: 0.8125rem;
          font-weight: 500;
          font-family: inherit;
          border-radius: 8px;
          border: 1px solid var(--input-border);
          background: var(--input-bg);
          color: var(--text-primary);
          outline: none;
          appearance: none;
          -webkit-appearance: none;
          cursor: pointer;
          box-shadow: var(--shadow-sm);
          transition: border-color 0.15s ease, box-shadow 0.15s ease;
        }

        .registry-filter-select:hover {
          border-color: var(--border-strong);
        }

        .registry-filter-select:focus {
          border-color: var(--input-border-focus);
          box-shadow: 0 0 0 3px var(--brand-primary-light);
        }

        .registry-filter-select option {
          background: var(--bg-solid-fallback);
          color: var(--text-primary);
        }

        @media (max-width: 768px) {
          .registry-controls-grid {
            flex-direction: column;
            align-items: stretch;
          }

          .search-input-wrapper,
          .filter-group-container,
          .filter-wrapper {
            width: 100%;
            min-width: 100%;
          }
        }

        @media (max-width: 480px) {
          .filter-inline-search-bar {
            flex-direction: column;
            align-items: stretch;
            gap: 0.35rem;
          }

          .filter-search-mini-input {
            width: 100%;
          }

          .filter-mini-pagination {
            width: 100%;
            justify-content: space-between;
          }

          .filter-mini-btn {
            flex: 1;
            min-width: 36px;
            min-height: 36px;
          }
        }

        .alert-banner {
          display: flex;
          align-items: center;
          gap: 0.75rem;
          padding: 0.875rem 1.25rem;
          border-radius: 10px;
          font-size: 0.875rem;
        }

        .alert-banner-error {
          background: var(--status-error-bg);
          border: 1px solid var(--status-error-border);
          color: var(--status-error);
        }

        .registry-loading-card {
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          gap: 1rem;
          padding: 3.5rem 1.5rem;
          background: var(--glass-surface);
          border: 1px solid var(--border-glass);
          border-radius: 16px;
        }

        .loading-spinner {
          width: 32px;
          height: 32px;
          border: 3px solid var(--border-glass);
          border-top-color: var(--brand-primary);
          border-radius: 50%;
          animation: spin 0.8s linear infinite;
        }

        @keyframes spin {
          to { transform: rotate(360deg); }
        }

        .registry-pagination-bar {
          display: flex;
          align-items: center;
          justify-content: space-between;
          padding: 0.75rem 0.5rem;
          gap: 1rem;
          flex-wrap: wrap;
        }

        .pagination-info {
          font-size: 0.8125rem;
          color: var(--text-secondary);
        }

        .pagination-controls {
          display: flex;
          align-items: center;
          gap: 0.75rem;
        }

        .pagination-page-indicator {
          font-size: 0.8125rem;
          color: var(--text-primary);
          font-weight: 500;
        }

        .registry-empty-card {
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          text-align: center;
          padding: 4rem 2rem;
          background: var(--glass-surface);
          border: 1px dashed var(--border-glass);
          border-radius: 16px;
        }

        .empty-icon-circle {
          width: 56px;
          height: 56px;
          border-radius: 50%;
          background: var(--glass-surface-elevated);
          border: 1px solid var(--border-glass);
          color: var(--brand-primary);
          display: flex;
          align-items: center;
          justify-content: center;
          margin-bottom: 1rem;
        }

        .empty-title {
          font-size: 1.125rem;
          font-weight: 600;
          color: var(--text-primary);
          margin: 0 0 0.5rem 0;
        }

        .empty-desc {
          font-size: 0.875rem;
          color: var(--text-secondary);
          max-width: 420px;
          line-height: 1.5;
          margin: 0 0 1.25rem 0;
        }

        @media (prefers-reduced-motion: reduce) {
          .loading-spinner {
            animation: none !important;
          }
          .registry-search-input,
          .registry-filter-select,
          .filter-search-mini-input,
          .filter-mini-btn {
            transition: none !important;
          }
        }

        .sr-only {
          position: absolute;
          width: 1px;
          height: 1px;
          padding: 0;
          margin: -1px;
          overflow: hidden;
          clip: rect(0, 0, 0, 0);
          white-space: nowrap;
          border: 0;
        }
      `}</style>
    </AppShell>
  );
};
