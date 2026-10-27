/**
 * Product Registry Management Page.
 *
 * Provides Platform Owners with comprehensive product inventory management:
 * search with debouncing & sequence guards, lifecycle status filtering,
 * server-side pagination, accessible dialogs, and truthful empty states.
 */

import React, { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { productsApi } from "../api/products.ts";
import type { ProductDetail, ProductListItem } from "../api/types.ts";
import { AppShell } from "../components/AppShell.tsx";
import { BoxIcon, ChevronDownIcon, FilterIcon, PlusIcon, SearchIcon } from "../components/Icons.tsx";
import { ProductFormDialog } from "../components/products/ProductFormDialog.tsx";
import { ProductListTable } from "../components/products/ProductListTable.tsx";

export const ProductRegistryPage: React.FC = () => {
  const navigate = useNavigate();
  const [products, setProducts] = useState<ProductListItem[]>([]);
  const [totalCount, setTotalCount] = useState<number>(0);
  const [page, setPage] = useState<number>(1);
  const pageSize = 10;

  const [searchInput, setSearchInput] = useState<string>("");
  const [debouncedSearch, setDebouncedSearch] = useState<string>("");
  const [statusFilter, setStatusFilter] = useState<string>("");

  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [liveAnnouncement, setLiveAnnouncement] = useState<string>("");

  // Dialog State
  const [isDialogOpen, setIsDialogOpen] = useState<boolean>(false);
  const [dialogMode, setDialogMode] = useState<"create" | "edit">("create");
  const [selectedProduct, setSelectedProduct] = useState<ProductListItem | null>(null);
  const triggerRef = useRef<HTMLElement | null>(null);

  // Request sequence guard to discard out-of-order responses
  const requestSeqRef = useRef<number>(0);

  // Debounce search input (300ms)
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearch(searchInput.trim());
      setPage(1); // Reset page on search change
    }, 300);
    return () => clearTimeout(timer);
  }, [searchInput]);

  const handleStatusFilterChange = (newStatus: string) => {
    setStatusFilter(newStatus);
    setPage(1); // Reset page on status filter change
  };

  const fetchProducts = useCallback(async () => {
    const currentSeq = ++requestSeqRef.current;
    setIsLoading(true);
    setError(null);
    setLiveAnnouncement("Loading product catalog...");

    try {
      const params = {
        page,
        page_size: pageSize,
        search: debouncedSearch || undefined,
        status: statusFilter || undefined,
      };

      const response = await productsApi.list(params);

      // Only apply if this is the latest in-flight request
      if (currentSeq === requestSeqRef.current) {
        setProducts(response.results as ProductListItem[]);
        setTotalCount(response.count);
        setIsLoading(false);
        setLiveAnnouncement(`Loaded ${response.results.length} products. Total ${response.count} items.`);
      }
    } catch (err: unknown) {
      if (currentSeq === requestSeqRef.current) {
        setIsLoading(false);
        const msg = "Unable to load products. Please check your connection and try again.";
        setError(msg);
        setLiveAnnouncement(msg);
      }
    }
  }, [page, pageSize, debouncedSearch, statusFilter]);

  useEffect(() => {
    fetchProducts();
  }, [fetchProducts]);

  const handleOpenCreate = (btnElement: HTMLElement) => {
    triggerRef.current = btnElement;
    setDialogMode("create");
    setSelectedProduct(null);
    setIsDialogOpen(true);
  };

  const handleOpenEdit = (product: ProductListItem, btnElement: HTMLElement) => {
    triggerRef.current = btnElement;
    setDialogMode("edit");
    setSelectedProduct(product);
    setIsDialogOpen(true);
  };

  const handleManageCatalog = (product: ProductListItem) => {
    navigate(`/products/${product.id}/catalog`);
  };

  const handleDialogSuccess = (product: ProductDetail) => {
    if (dialogMode === "create") {
      setLiveAnnouncement(`Product ${product.name} registered.`);
    } else {
      setLiveAnnouncement(`Product ${product.name} updated.`);
    }
    fetchProducts();
  };

  const totalPages = Math.max(1, Math.ceil(totalCount / pageSize));

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
          <span>Platform</span>
          <span>/</span>
          <span style={{ color: "var(--brand-primary, #3867f5)", fontWeight: 600 }}>Product Registry & Marketplace</span>
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
              <BoxIcon size={24} />
            </div>
            <div>
              <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", flexWrap: "wrap" }}>
                <h1 style={{ fontSize: "1.625rem", fontWeight: 800, margin: 0, color: "var(--text-primary)", letterSpacing: "-0.02em" }}>
                  Product Registry
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
                    {totalCount} {totalCount === 1 ? "Product" : "Products"}
                  </span>
                )}
              </div>
              <p style={{ margin: "0.25rem 0 0 0", fontSize: "0.875rem", color: "var(--text-secondary)", lineHeight: 1.5, maxWidth: "780px" }}>
                Centralized catalog of platform-managed applications and services. Manage product lifecycles, configuration metadata, and downstream entitlement keys.
              </p>
            </div>
          </div>

          <button
            type="button"
            className="btn-gradient"
            onClick={(e) => handleOpenCreate(e.currentTarget)}
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: "0.5rem",
              padding: "0.65rem 1.35rem",
              borderRadius: "10px",
              fontWeight: 700,
              fontSize: "0.875rem",
              background: "linear-gradient(135deg, #3867f5 0%, #2952cc 100%)",
              color: "#ffffff",
              border: "none",
              cursor: "pointer",
              boxShadow: "0 4px 14px rgba(56, 103, 245, 0.3)",
              flexShrink: 0,
            }}
          >
            <PlusIcon size={16} />
            <span>Register Product</span>
          </button>
        </div>

        {/* Filter & Search Bar */}
        <div className="registry-controls-bar">
          {/* Search Box */}
          <div className="search-input-wrapper">
            <span className="search-icon-adornment" aria-hidden="true">
              <SearchIcon size={16} />
            </span>
            <input
              type="search"
              className="registry-search-input"
              placeholder="Search by code or product name..."
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              aria-label="Search products"
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
              onChange={(e) => handleStatusFilterChange(e.target.value)}
              aria-label="Filter by lifecycle status"
            >
              <option value="">All Statuses</option>
              <option value="draft">Draft</option>
              <option value="active">Active</option>
              <option value="inactive">Inactive</option>
              <option value="retired">Retired</option>
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
              onClick={fetchProducts}
              style={{ marginLeft: "auto" }}
            >
              Retry
            </button>
          </div>
        )}

        {/* Loading Skeleton */}
        {isLoading && (
          <div className="registry-skeleton-container" aria-label="Loading product catalog">
            <div className="skeleton-row" />
            <div className="skeleton-row" />
            <div className="skeleton-row" />
          </div>
        )}

        {/* Data Table or Empty States */}
        {!isLoading && !error && (
          <>
            {products.length > 0 ? (
              <>
                <ProductListTable
                  products={products}
                  onEdit={handleOpenEdit}
                  onManageCatalog={handleManageCatalog}
                />

                {/* Pagination Controls */}
                {totalCount > pageSize && (
                  <div className="pagination-bar">
                    <span className="text-caption">
                      Showing {(page - 1) * pageSize + 1}–{Math.min(page * pageSize, totalCount)} of {totalCount}
                    </span>
                    <div style={{ display: "flex", gap: "0.5rem" }}>
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
                  <BoxIcon size={28} />
                </div>
                {searchInput || statusFilter ? (
                  <>
                    <h3 className="empty-title">No matching products found</h3>
                    <p className="empty-desc">
                      No registered products matched your active filters. Try adjusting your query or resetting filters.
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
                    <h3 className="empty-title">No products registered</h3>
                    <p className="empty-desc">
                      The centralized product registry is currently empty. Register your first platform-managed product to begin.
                    </p>
                    <button
                      type="button"
                      className="btn btn-primary"
                      onClick={(e) => handleOpenCreate(e.currentTarget)}
                    >
                      <PlusIcon size={16} />
                      Register First Product
                    </button>
                  </>
                )}
              </div>
            )}
          </>
        )}
      </div>

      {/* Register / Edit Product Dialog */}
      <ProductFormDialog
        mode={dialogMode}
        product={selectedProduct}
        isOpen={isDialogOpen}
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

        .registry-controls-bar {
          display: flex;
          align-items: center;
          gap: 0.875rem;
          width: 100%;
        }

        .search-input-wrapper {
          position: relative;
          flex: 1;
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
          min-height: 48px;
          height: 48px;
          padding: 0.625rem 1rem 0.625rem 2.625rem;
          font-size: 0.875rem;
          font-family: inherit;
          border-radius: 10px;
          border: 1px solid var(--input-border);
          background: var(--input-bg);
          color: var(--text-primary);
          outline: none;
          box-shadow: var(--shadow-sm);
          transition: border-color 0.15s ease, box-shadow 0.15s ease, background-color 0.15s ease;
        }

        .registry-search-input::placeholder {
          color: var(--text-muted);
        }

        .registry-search-input:hover:not(:disabled) {
          border-color: var(--border-strong);
        }

        .registry-search-input:focus {
          border-color: var(--input-border-focus);
          box-shadow: 0 0 0 3px var(--brand-primary-light);
        }

        .status-filter-wrapper {
          position: relative;
          width: 210px;
          flex-shrink: 0;
          display: flex;
          align-items: center;
        }

        .filter-icon-adornment {
          position: absolute;
          left: 0.875rem;
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
          right: 0.875rem;
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
          min-height: 48px;
          height: 48px;
          padding: 0.625rem 2.25rem 0.625rem 2.35rem;
          font-size: 0.875rem;
          font-weight: 500;
          font-family: inherit;
          border-radius: 10px;
          border: 1px solid var(--input-border);
          background: var(--input-bg);
          color: var(--text-primary);
          outline: none;
          appearance: none;
          -webkit-appearance: none;
          -moz-appearance: none;
          cursor: pointer;
          box-shadow: var(--shadow-sm);
          transition: border-color 0.15s ease, box-shadow 0.15s ease, background-color 0.15s ease;
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
          .registry-controls-bar {
            flex-direction: column;
            align-items: stretch;
          }

          .status-filter-wrapper {
            width: 100%;
          }
        }

        .registry-skeleton-container {
          display: flex;
          flex-direction: column;
          gap: 0.75rem;
        }

        .skeleton-row {
          height: 64px;
          border-radius: 10px;
          background: var(--glass-surface-elevated);
          border: 1px solid var(--border-glass);
          animation: pulse 1.5s infinite ease-in-out;
        }

        @keyframes pulse {
          0%, 100% { opacity: 0.6; }
          50% { opacity: 0.3; }
        }

        .pagination-bar {
          display: flex;
          align-items: center;
          justify-content: space-between;
          padding: 0.75rem 0.25rem;
          flex-wrap: wrap;
          gap: 0.75rem;
        }

        .pagination-page-indicator {
          display: inline-flex;
          align-items: center;
          font-size: 0.8125rem;
          color: var(--text-secondary);
          padding: 0 0.5rem;
        }

        .registry-empty-card {
          background: var(--glass-surface-elevated);
          border: 1px solid var(--border-glass);
          border-radius: 16px;
          padding: 3.5rem 1.5rem;
          text-align: center;
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          gap: 0.75rem;
          box-shadow: var(--shadow-sm);
        }

        .empty-icon-circle {
          width: 56px;
          height: 56px;
          border-radius: 50%;
          background: var(--brand-primary-light);
          color: var(--brand-primary);
          display: flex;
          align-items: center;
          justify-content: center;
          margin-bottom: 0.25rem;
        }

        .empty-title {
          font-size: 1.125rem;
          font-weight: 600;
          color: var(--text-primary);
          margin: 0;
        }

        .empty-desc {
          font-size: 0.875rem;
          color: var(--text-secondary);
          max-width: 480px;
          margin: 0 0 0.75rem 0;
          line-height: 1.5;
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
