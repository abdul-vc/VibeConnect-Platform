/**
 * Product Catalog Page (Tier 1: Product Modules).
 *
 * Dedicated Platform Owner portal for managing functional modules belonging to one Product.
 * Implements verified parent context loading, ancestry verification, debounced search,
 * status filtering, deterministic ordering, server-side pagination with boolean-only URL safety,
 * accessible dialogs, and truthfully synchronized child counts.
 */

import React, { useCallback, useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { catalogApi, extractCatalogErrorMessage } from "../../api/catalog.ts";
import { productsApi } from "../../api/products.ts";
import type {
  CatalogOrderingField,
  CatalogStatus,
  ProductDetail,
  ProductModuleListItem,
} from "../../api/types.ts";
import { AppShell } from "../../components/AppShell.tsx";
import {
  AlertCircleIcon,
  ChevronLeftIcon,
  ChevronRightIcon,
  CloseIcon,
  LayersIcon,
  PlusIcon,
  RotateCcwIcon,
} from "../../components/Icons.tsx";
import { CatalogAncestorBanner } from "../../components/catalog/CatalogAncestorBanner.tsx";
import { CatalogHierarchyNav } from "../../components/catalog/CatalogHierarchyNav.tsx";
import {
  CatalogEntityDialog,
  type CatalogEntityFormData,
} from "../../components/catalog/CatalogEntityDialog.tsx";
import { CatalogFilterToolbar } from "../../components/catalog/CatalogFilterToolbar.tsx";
import { CatalogRetireDialog } from "../../components/catalog/CatalogRetireDialog.tsx";
import { ModuleListTable } from "../../components/catalog/ModuleListTable.tsx";

const ORDERING_OPTIONS: Array<{ value: CatalogOrderingField; label: string }> = [
  { value: "display_order", label: "Display Order (Default)" },
  { value: "-display_order", label: "Display Order (Reverse)" },
  { value: "name", label: "Name (A to Z)" },
  { value: "-name", label: "Name (Z to A)" },
  { value: "code", label: "Code (A to Z)" },
  { value: "-code", label: "Code (Z to A)" },
  { value: "-created_at", label: "Newest First" },
  { value: "created_at", label: "Oldest First" },
];

export const ProductCatalogPage: React.FC = () => {
  const { productId } = useParams<{ productId: string }>();
  const navigate = useNavigate();

  // Parent Product State
  const [product, setProduct] = useState<ProductDetail | null>(null);
  const [isProductLoading, setIsProductLoading] = useState<boolean>(true);
  const [productError, setProductError] = useState<string | null>(null);
  const productAbortRef = useRef<AbortController | null>(null);
  const productSeqRef = useRef<number>(0);

  // Module List State
  const [modules, setModules] = useState<ProductModuleListItem[]>([]);
  const [totalCount, setTotalCount] = useState<number>(0);
  const [hasNext, setHasNext] = useState<boolean>(false);
  const [hasPrevious, setHasPrevious] = useState<boolean>(false);
  const [page, setPage] = useState<number>(1);
  const pageSize = 20;

  // Filter & Search State
  const [searchInput, setSearchInput] = useState<string>("");
  const [debouncedSearch, setDebouncedSearch] = useState<string>("");
  const [statusFilter, setStatusFilter] = useState<string>("");
  const [ordering, setOrdering] = useState<CatalogOrderingField>("display_order");

  // Lifecycle State
  const [isListLoading, setIsListLoading] = useState<boolean>(true);
  const [listError, setListError] = useState<string | null>(null);
  const [mutationError, setMutationError] = useState<string | null>(null);
  const [liveAnnouncement, setLiveAnnouncement] = useState<string>("");
  const listAbortRef = useRef<AbortController | null>(null);
  const listSeqRef = useRef<number>(0);

  // Dialog State
  const [dialogMode, setDialogMode] = useState<"create" | "edit">("create");
  const [isDialogOpen, setIsDialogOpen] = useState<boolean>(false);
  const [selectedModule, setSelectedModule] = useState<CatalogEntityFormData | null>(null);

  // Retire Modal State
  const [isRetireOpen, setIsRetireOpen] = useState<boolean>(false);
  const [moduleToRetire, setModuleToRetire] = useState<ProductModuleListItem | null>(null);
  const triggerRef = useRef<HTMLElement | null>(null);

  // Debounce search input (300ms)
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearch(searchInput.trim());
      setPage(1);
    }, 300);
    return () => clearTimeout(timer);
  }, [searchInput]);

  // Load Parent Product Context
  const fetchProductContext = useCallback(async () => {
    if (!productId) return;

    productAbortRef.current?.abort();
    const currentSeq = ++productSeqRef.current;
    const controller = new AbortController();
    productAbortRef.current = controller;

    setIsProductLoading(true);
    setProductError(null);

    try {
      const data = await productsApi.get(productId);
      if (currentSeq === productSeqRef.current && !controller.signal.aborted) {
        setProduct(data);
        setIsProductLoading(false);
      }
    } catch (err: unknown) {
      if (currentSeq === productSeqRef.current && !controller.signal.aborted) {
        setIsProductLoading(false);
        setProductError("Product not found in registry. Please verify the URL.");
      }
    }
  }, [productId]);

  useEffect(() => {
    fetchProductContext();
    return () => {
      productAbortRef.current?.abort();
    };
  }, [fetchProductContext]);

  // Load Module List (only if Product context succeeded)
  const fetchModules = useCallback(async () => {
    if (!productId || isProductLoading || productError) return;

    listAbortRef.current?.abort();
    const currentSeq = ++listSeqRef.current;
    const controller = new AbortController();
    listAbortRef.current = controller;

    setIsListLoading(true);
    setListError(null);

    try {
      const params = {
        product_id: productId,
        page,
        page_size: pageSize,
        search: debouncedSearch || undefined,
        status: (statusFilter as CatalogStatus) || undefined,
        ordering,
      };

      const response = await catalogApi.modules.list(params, controller.signal);

      if (currentSeq === listSeqRef.current && !controller.signal.aborted) {
        setModules(response.results as ProductModuleListItem[]);
        setTotalCount(response.count);
        setHasNext(Boolean(response.next));
        setHasPrevious(Boolean(response.previous));
        setIsListLoading(false);
        setLiveAnnouncement(
          `Loaded ${response.results.length} modules. Total ${response.count} items.`
        );
      }
    } catch (err: unknown) {
      if (currentSeq === listSeqRef.current && !controller.signal.aborted) {
        setIsListLoading(false);
        // Out-of-range recovery
        const apiErr = err as { status?: number };
        if (apiErr.status === 404 && page > 1) {
          setPage(1);
          return;
        }
        const msg = "Unable to load product modules. Please verify your connection and try again.";
        setListError(msg);
        setLiveAnnouncement(msg);
      }
    }
  }, [productId, isProductLoading, productError, page, debouncedSearch, statusFilter, ordering]);

  useEffect(() => {
    fetchModules();
    return () => {
      listAbortRef.current?.abort();
    };
  }, [fetchModules]);

  // Dialog Handlers
  const handleOpenCreate = (btnElement: HTMLElement) => {
    triggerRef.current = btnElement;
    setDialogMode("create");
    setSelectedModule(null);
    setIsDialogOpen(true);
  };

  const handleOpenEdit = (module: ProductModuleListItem, btnElement: HTMLElement) => {
    triggerRef.current = btnElement;
    setDialogMode("edit");
    setSelectedModule({
      id: module.id,
      code: module.code,
      name: module.name,
      description: module.description,
      display_order: module.display_order,
      status: module.status,
    });
    setIsDialogOpen(true);
  };

  const handleOpenRetire = (module: ProductModuleListItem, btnElement: HTMLElement) => {
    triggerRef.current = btnElement;
    setModuleToRetire(module);
    setIsRetireOpen(true);
  };

  const handleActivate = async (module: ProductModuleListItem) => {
    setMutationError(null);
    try {
      setLiveAnnouncement(`Activating module ${module.name}...`);
      await catalogApi.modules.patch(module.id, { status: "active" });
      setLiveAnnouncement(`Module ${module.name} is now Active.`);
      fetchModules();
    } catch (err: unknown) {
      const msg = extractCatalogErrorMessage(err, "Failed to activate module.");
      setMutationError(msg);
      setLiveAnnouncement(`Error: ${msg}`);
    }
  };

  const handleRetireConfirm = async () => {
    if (!moduleToRetire) return;
    setMutationError(null);
    await catalogApi.modules.patch(moduleToRetire.id, { status: "retired" });
    fetchModules();
  };

  const handleDialogSuccess = () => {
    setMutationError(null);
    fetchModules();
  };

  // Render Product Loading State
  if (isProductLoading) {
    return (
      <AppShell>
        <div className="catalog-loading-container">
          <div className="skeleton-row" style={{ height: "48px" }} />
          <div className="skeleton-row" style={{ height: "80px" }} />
          <div className="skeleton-row" style={{ height: "300px" }} />
        </div>
      </AppShell>
    );
  }

  // Render Product Not Found Error
  if (productError || !product) {
    return (
      <AppShell>
        <div className="catalog-error-card">
          <div className="error-icon-circle">
            <AlertCircleIcon size={32} />
          </div>
          <h2 className="heading-title">Product Not Found</h2>
          <p className="text-body" style={{ maxWidth: "480px", textAlign: "center" }}>
            {productError || "The requested product could not be located in the platform registry."}
          </p>
          <Link to="/products" className="btn btn-primary" style={{ marginTop: "0.5rem" }}>
            <ChevronLeftIcon size={16} />
            Return to Product Registry
          </Link>
        </div>
      </AppShell>
    );
  }

  // Tier 1 Lifecycle Booleans (Centralized & Explicit)
  const isHierarchyTerminal = product.status === "retired";
  const canCreateDraftChild = !isHierarchyTerminal;
  const areAllActivationAncestorsActive = product.status === "active";
  const totalPages = Math.max(1, Math.ceil(totalCount / pageSize));

  return (
    <AppShell>
      {/* Accessible Live Region */}
      <div className="sr-only" aria-live="polite" aria-atomic="true">
        {liveAnnouncement}
      </div>

      <div className="catalog-page-layout">
        {/* Hierarchy Navigation */}
        <CatalogHierarchyNav
          items={[
            { label: "Product Registry", path: "/products" },
            { label: product.name, code: product.code },
          ]}
        />

        {/* Ancestor Context Banner */}
        <CatalogAncestorBanner
          ancestors={[
            {
              type: "product",
              id: product.id,
              code: product.code,
              name: product.name,
              status: product.status,
            },
          ]}
        />

        {/* Catalog Tier Header */}
        <div className="catalog-header-bar" style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: "1rem", marginBottom: "1.5rem" }}>
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
              <LayersIcon size={24} />
            </div>

            <div className="catalog-header-text">
              <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", flexWrap: "wrap" }}>
                <h1 className="heading-hero" style={{ margin: 0, fontSize: "1.75rem", fontWeight: 800, letterSpacing: "-0.02em", color: "var(--text-primary)" }}>
                  Product Modules
                </h1>
                {!isListLoading && (
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
                    {totalCount} {totalCount === 1 ? "Module" : "Modules"}
                  </span>
                )}
              </div>
              <p className="text-body" style={{ marginTop: "0.25rem", maxWidth: "720px", color: "var(--text-secondary)", fontSize: "0.9375rem" }}>
                Primary functional areas and service modules under{" "}
                <strong>{product.name}</strong>. Configure module status, display ordering, and nested features.
              </p>
            </div>
          </div>

          <div className="catalog-header-action">
            <button
              type="button"
              className="btn btn-gradient"
              onClick={(e) => handleOpenCreate(e.currentTarget)}
              disabled={!canCreateDraftChild}
              title={!canCreateDraftChild ? "Cannot register modules under a retired product" : "Register new module"}
            >
              <PlusIcon size={16} />
              Register Module
            </button>
          </div>
        </div>

        {/* Mutation Error Alert Banner */}
        {mutationError && (
          <div
            className="alert-box alert-danger"
            role="alert"
            aria-live="assertive"
            style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}
          >
            <AlertCircleIcon size={16} style={{ flexShrink: 0 }} />
            <span style={{ flex: 1 }}>{mutationError}</span>
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              onClick={() => setMutationError(null)}
              aria-label="Dismiss error"
              style={{ marginLeft: "auto" }}
            >
              <CloseIcon size={14} />
              Dismiss
            </button>
          </div>
        )}

        {/* Controls Bar: Search, Status Filter, Ordering */}
        <CatalogFilterToolbar
          entityTypePlural="modules"
          searchInput={searchInput}
          onSearchChange={setSearchInput}
          statusFilter={statusFilter}
          onStatusChange={(newStatus) => {
            setStatusFilter(newStatus);
            setPage(1);
          }}
          ordering={ordering}
          onOrderingChange={(newOrdering) => {
            setOrdering(newOrdering);
            setPage(1);
          }}
          orderingOptions={ORDERING_OPTIONS}
          disabled={isListLoading}
        />

        {/* Error Alert */}
        {listError && (
          <div className="alert-box alert-danger" role="alert">
            <AlertCircleIcon size={16} style={{ flexShrink: 0 }} />
            <span>{listError}</span>
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              onClick={fetchModules}
              style={{ marginLeft: "auto" }}
            >
              <RotateCcwIcon size={14} />
              Retry
            </button>
          </div>
        )}

        {/* Loading Skeleton */}
        {isListLoading && (
          <div className="catalog-skeleton-container" aria-label="Loading modules">
            <div className="skeleton-row" />
            <div className="skeleton-row" />
            <div className="skeleton-row" />
          </div>
        )}

        {/* Populated Table or Truthful Empty State */}
        {!isListLoading && !listError && (
          <>
            {modules.length > 0 ? (
              <>
                <ModuleListTable
                  modules={modules}
                  areAllActivationAncestorsActive={areAllActivationAncestorsActive}
                  onEdit={handleOpenEdit}
                  onActivate={handleActivate}
                  onRetire={handleOpenRetire}
                  onManageFeatures={(mod) =>
                    navigate(`/products/${product.id}/catalog/modules/${mod.id}`)
                  }
                />

                {/* Server-Side Pagination Bar */}
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
                        disabled={!hasPrevious || page <= 1}
                        aria-label="Previous page"
                      >
                        <ChevronLeftIcon size={14} />
                        Previous
                      </button>
                      <span className="pagination-page-indicator">
                        Page {page} of {totalPages}
                      </span>
                      <button
                        type="button"
                        className="btn btn-secondary btn-sm"
                        onClick={() => setPage((p) => Math.min(p + 1, totalPages))}
                        disabled={!hasNext || page >= totalPages}
                        aria-label="Next page"
                      >
                        Next
                        <ChevronRightIcon size={14} />
                      </button>
                    </div>
                  </div>
                )}
              </>
            ) : (
              /* Truthful Empty State */
              <div className="catalog-empty-card">
                <div className="empty-icon-circle">
                  <LayersIcon size={28} />
                </div>
                {searchInput || statusFilter ? (
                  <>
                    <h3 className="empty-title">No matching modules found</h3>
                    <p className="empty-desc">
                      No modules under {product.name} matched your search or status filter.
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
                    <h3 className="empty-title">No modules registered</h3>
                    <p className="empty-desc">
                      No functional modules have been configured under {product.name}. Register the first module to build your product hierarchy.
                    </p>
                    <button
                      type="button"
                      className="btn btn-primary"
                      onClick={(e) => handleOpenCreate(e.currentTarget)}
                      disabled={!canCreateDraftChild}
                      title={isHierarchyTerminal ? "Cannot register modules under a retired product" : "Register first module"}
                    >
                      <PlusIcon size={16} />
                      Register First Module
                    </button>
                  </>
                )}
              </div>
            )}
          </>
        )}
      </div>

      {/* Create / Edit Dialog */}
      <CatalogEntityDialog
        entityType="module"
        mode={dialogMode}
        isOpen={isDialogOpen}
        onClose={() => setIsDialogOpen(false)}
        onSuccess={handleDialogSuccess}
        parentId={product.id}
        parentLabel={`Product: ${product.name} (${product.code})`}
        initialData={selectedModule}
        triggerRef={triggerRef}
      />

      {/* Retire Confirmation Dialog */}
      <CatalogRetireDialog
        isOpen={isRetireOpen}
        entityTypeLabel="Module"
        entityName={moduleToRetire?.name || ""}
        entityCode={moduleToRetire?.code || ""}
        hasChildNotice={
          moduleToRetire && moduleToRetire.total_features_count > 0
            ? `This module currently has ${moduleToRetire.total_features_count} feature(s).`
            : undefined
        }
        onClose={() => setIsRetireOpen(false)}
        onConfirm={handleRetireConfirm}
        triggerRef={triggerRef}
      />
    </AppShell>
  );
};
