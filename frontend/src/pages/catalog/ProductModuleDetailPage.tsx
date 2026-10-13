/**
 * Product Module Detail Page (Tier 2: Product Features).
 *
 * Dedicated Platform Owner portal for managing features belonging to one Module.
 * Strictly validates deep route ancestry: module.product_id === product.id before loading features.
 * Features cannot be loaded or mutated until strict route ancestry is validated.
 */

import React, { useCallback, useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { catalogApi, extractCatalogErrorMessage } from "../../api/catalog.ts";
import { productsApi } from "../../api/products.ts";
import type {
  CatalogOrderingField,
  CatalogStatus,
  ProductDetail,
  ProductFeatureListItem,
  ProductModuleDetail,
} from "../../api/types.ts";
import { AppShell } from "../../components/AppShell.tsx";
import {
  AlertCircleIcon,
  ChevronLeftIcon,
  ChevronRightIcon,
  CloseIcon,
  PlusIcon,
  RotateCcwIcon,
  SlidersIcon,
} from "../../components/Icons.tsx";
import { CatalogAncestorBanner } from "../../components/catalog/CatalogAncestorBanner.tsx";
import { CatalogHierarchyNav } from "../../components/catalog/CatalogHierarchyNav.tsx";
import {
  CatalogEntityDialog,
  type CatalogEntityFormData,
} from "../../components/catalog/CatalogEntityDialog.tsx";
import { CatalogFilterToolbar } from "../../components/catalog/CatalogFilterToolbar.tsx";
import { CatalogRetireDialog } from "../../components/catalog/CatalogRetireDialog.tsx";
import { FeatureListTable } from "../../components/catalog/FeatureListTable.tsx";

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

export const ProductModuleDetailPage: React.FC = () => {
  const { productId, moduleId } = useParams<{ productId: string; moduleId: string }>();
  const navigate = useNavigate();

  // Ancestor State
  const [product, setProduct] = useState<ProductDetail | null>(null);
  const [module, setModule] = useState<ProductModuleDetail | null>(null);
  const [isAncestorLoading, setIsAncestorLoading] = useState<boolean>(true);
  const [ancestorError, setAncestorError] = useState<string | null>(null);
  const [isHierarchyValid, setIsHierarchyValid] = useState<boolean>(false);
  const ancestorAbortRef = useRef<AbortController | null>(null);
  const ancestorSeqRef = useRef<number>(0);

  // Feature List State
  const [features, setFeatures] = useState<ProductFeatureListItem[]>([]);
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
  const [mutationWarning, setMutationWarning] = useState<string | null>(null);
  const [liveAnnouncement, setLiveAnnouncement] = useState<string>("");
  const listAbortRef = useRef<AbortController | null>(null);
  const listSeqRef = useRef<number>(0);

  // Dialog State
  const [dialogMode, setDialogMode] = useState<"create" | "edit">("create");
  const [isDialogOpen, setIsDialogOpen] = useState<boolean>(false);
  const [selectedFeature, setSelectedFeature] = useState<CatalogEntityFormData | null>(null);

  // Retire Modal State
  const [isRetireOpen, setIsRetireOpen] = useState<boolean>(false);
  const [featureToRetire, setFeatureToRetire] = useState<ProductFeatureListItem | null>(null);
  const triggerRef = useRef<HTMLElement | null>(null);

  // Debounce search input (300ms)
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearch(searchInput.trim());
      setPage(1);
    }, 300);
    return () => clearTimeout(timer);
  }, [searchInput]);

  // Load and Verify Ancestor Context (Product + Module)
  const fetchAncestorContext = useCallback(async (isBackground = false) => {
    if (!productId || !moduleId) return;

    ancestorAbortRef.current?.abort();
    const currentSeq = ++ancestorSeqRef.current;
    const controller = new AbortController();
    ancestorAbortRef.current = controller;

    if (!isBackground) {
      setIsAncestorLoading(true);
      setAncestorError(null);
      setIsHierarchyValid(false);
    }

    try {
      // In parallel, fetch parent Product and Module
      const [prodRes, modRes] = await Promise.all([
        productsApi.get(productId),
        catalogApi.modules.get(moduleId, controller.signal),
      ]);

      if (currentSeq === ancestorSeqRef.current && !controller.signal.aborted) {
        // Enforce strict deep route ancestry verification
        if (modRes.product_id !== prodRes.id) {
          if (!isBackground) {
            setIsAncestorLoading(false);
            setIsHierarchyValid(false);
            setAncestorError(
              `Hierarchy Mismatch: Module "${modRes.name}" (${modRes.code}) does not belong to Product "${prodRes.name}" (${prodRes.code}).`
            );
          }
          return;
        }

        setProduct(prodRes);
        setModule(modRes);
        setIsHierarchyValid(true);
        if (!isBackground) {
          setIsAncestorLoading(false);
        }
      }
    } catch (err: unknown) {
      if (currentSeq === ancestorSeqRef.current && !controller.signal.aborted) {
        if (!isBackground) {
          setIsAncestorLoading(false);
          setIsHierarchyValid(false);
          setAncestorError(
            "Unable to load product module context. The module or product may not exist or has been removed."
          );
        } else {
          setMutationWarning(
            "Notice: Could not refresh module counters. The features list remains updated."
          );
        }
      }
    }
  }, [productId, moduleId]);

  useEffect(() => {
    fetchAncestorContext();
    return () => {
      ancestorAbortRef.current?.abort();
    };
  }, [fetchAncestorContext]);

  // Load Features List (Only executed after ancestry is strictly validated)
  const fetchFeatures = useCallback(async () => {
    if (!moduleId || !isHierarchyValid || isAncestorLoading || ancestorError) return;

    listAbortRef.current?.abort();
    const currentSeq = ++listSeqRef.current;
    const controller = new AbortController();
    listAbortRef.current = controller;

    setIsListLoading(true);
    setListError(null);

    try {
      const params = {
        module_id: moduleId,
        page,
        page_size: pageSize,
        search: debouncedSearch || undefined,
        status: (statusFilter as CatalogStatus) || undefined,
        ordering,
      };

      const response = await catalogApi.features.list(params, controller.signal);

      if (currentSeq === listSeqRef.current && !controller.signal.aborted) {
        setFeatures(response.results as ProductFeatureListItem[]);
        setTotalCount(response.count);
        setHasNext(Boolean(response.next));
        setHasPrevious(Boolean(response.previous));
        setIsListLoading(false);
        setLiveAnnouncement(
          `Loaded ${response.results.length} features. Total ${response.count} items.`
        );
      }
    } catch (err: unknown) {
      if (currentSeq === listSeqRef.current && !controller.signal.aborted) {
        setIsListLoading(false);
        const apiErr = err as { status?: number };
        if (apiErr.status === 404 && page > 1) {
          setPage(1);
          return;
        }
        const msg = "Unable to load module features. Please verify your connection and try again.";
        setListError(msg);
        setLiveAnnouncement(msg);
      }
    }
  }, [moduleId, isHierarchyValid, isAncestorLoading, ancestorError, page, debouncedSearch, statusFilter, ordering]);

  useEffect(() => {
    if (isHierarchyValid) {
      fetchFeatures();
    }
    return () => {
      listAbortRef.current?.abort();
    };
  }, [isHierarchyValid, fetchFeatures]);

  // Dialog Handlers
  const handleOpenCreate = (btnElement: HTMLElement) => {
    triggerRef.current = btnElement;
    setDialogMode("create");
    setSelectedFeature(null);
    setIsDialogOpen(true);
  };

  const handleOpenEdit = (feat: ProductFeatureListItem, btnElement: HTMLElement) => {
    triggerRef.current = btnElement;
    setDialogMode("edit");
    setSelectedFeature({
      id: feat.id,
      code: feat.code,
      name: feat.name,
      description: feat.description,
      display_order: feat.display_order,
      status: feat.status,
    });
    setIsDialogOpen(true);
  };

  const handleOpenRetire = (feat: ProductFeatureListItem, btnElement: HTMLElement) => {
    triggerRef.current = btnElement;
    setFeatureToRetire(feat);
    setIsRetireOpen(true);
  };

  const refreshAfterMutation = useCallback(async () => {
    setMutationError(null);
    await Promise.allSettled([
      fetchFeatures(),
      fetchAncestorContext(true),
    ]);
  }, [fetchFeatures, fetchAncestorContext]);

  const handleActivate = async (feat: ProductFeatureListItem) => {
    try {
      setMutationError(null);
      setLiveAnnouncement(`Activating feature ${feat.name}...`);
      await catalogApi.features.patch(feat.id, { status: "active" });
      setLiveAnnouncement(`Feature ${feat.name} is now Active.`);
      await refreshAfterMutation();
    } catch (err: unknown) {
      const msg = extractCatalogErrorMessage(err, "Failed to activate feature.");
      setMutationError(msg);
      setLiveAnnouncement(msg);
    }
  };

  const handleRetireConfirm = async () => {
    if (!featureToRetire) return;
    try {
      setMutationError(null);
      setLiveAnnouncement(`Retiring feature ${featureToRetire.name}...`);
      await catalogApi.features.patch(featureToRetire.id, { status: "retired" });
      setLiveAnnouncement(`Feature ${featureToRetire.name} has been retired.`);
      await refreshAfterMutation();
    } catch (err: unknown) {
      const msg = extractCatalogErrorMessage(err, "Failed to retire feature.");
      setMutationError(msg);
      setLiveAnnouncement(msg);
    }
  };

  const handleDialogSuccess = () => {
    setMutationError(null);
    refreshAfterMutation();
  };

  // Render Ancestor Loading State
  if (isAncestorLoading) {
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

  // Render Ancestor or Hierarchy Error
  if (ancestorError || !isHierarchyValid || !product || !module) {
    return (
      <AppShell>
        <div className="catalog-error-card">
          <div className="error-icon-circle">
            <AlertCircleIcon size={32} />
          </div>
          <h2 className="heading-title">Hierarchy Mismatch or Missing Module</h2>
          <p className="text-body" style={{ maxWidth: "560px", textAlign: "center" }}>
            {ancestorError || "The requested module does not belong to the specified product ancestry."}
          </p>
          <div style={{ display: "flex", gap: "0.75rem", marginTop: "0.75rem", flexWrap: "wrap", justifyContent: "center" }}>
            {productId && (
              <Link to={`/products/${productId}/catalog`} className="btn btn-primary">
                <ChevronLeftIcon size={16} />
                Return to Product Modules
              </Link>
            )}
            <Link to="/products" className="btn btn-secondary">
              Product Registry
            </Link>
          </div>
        </div>
      </AppShell>
    );
  }

  // Tier 2 Lifecycle Booleans (Centralized & Explicit)
  const isHierarchyTerminal = product.status === "retired" || module.status === "retired";
  const canCreateDraftChild = !isHierarchyTerminal;
  const areAllActivationAncestorsActive = product.status === "active" && module.status === "active";
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
            { label: product.name, code: product.code, path: `/products/${product.id}/catalog` },
            { label: module.name, code: module.code },
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
            {
              type: "module",
              id: module.id,
              code: module.code,
              name: module.name,
              status: module.status,
            },
          ]}
        />

        {/* Catalog Tier Header */}
        <div className="catalog-header-bar">
          <div className="catalog-header-text">
            <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", flexWrap: "wrap" }}>
              <div className="tier-badge-icon">
                <SlidersIcon size={20} />
              </div>
              <h1 className="heading-title" style={{ margin: 0 }}>
                Module Features
              </h1>
              {!isListLoading && (
                <span className="registry-count-badge">
                  {totalCount} {totalCount === 1 ? "Feature" : "Features"}
                </span>
              )}
            </div>
            <p className="text-caption" style={{ marginTop: "0.25rem", maxWidth: "720px" }}>
              Functional features and sub-systems governed by{" "}
              <strong>{module.name}</strong> ({module.code}). Configure feature lifecycles and nested capabilities.
            </p>
          </div>

          <div className="catalog-header-action">
            <button
              type="button"
              className="btn btn-primary"
              onClick={(e) => handleOpenCreate(e.currentTarget)}
              disabled={!canCreateDraftChild}
              title={!canCreateDraftChild ? "Cannot register features under a retired module or product" : "Register new feature"}
            >
              <PlusIcon size={16} />
              Register Feature
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

        {/* Mutation Non-Destructive Warning Banner */}
        {mutationWarning && (
          <div
            className="alert-box alert-warning"
            role="status"
            aria-live="polite"
            style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}
          >
            <AlertCircleIcon size={16} style={{ flexShrink: 0 }} />
            <span style={{ flex: 1 }}>{mutationWarning}</span>
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              onClick={() => setMutationWarning(null)}
              aria-label="Dismiss warning"
              style={{ marginLeft: "auto" }}
            >
              <CloseIcon size={14} />
              Dismiss
            </button>
          </div>
        )}

        {/* Controls Bar: Search, Status Filter, Ordering */}
        <CatalogFilterToolbar
          entityTypePlural="features"
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
              onClick={fetchFeatures}
              style={{ marginLeft: "auto" }}
            >
              <RotateCcwIcon size={14} />
              Retry
            </button>
          </div>
        )}

        {/* Loading Skeleton */}
        {isListLoading && (
          <div className="catalog-skeleton-container" aria-label="Loading features">
            <div className="skeleton-row" />
            <div className="skeleton-row" />
            <div className="skeleton-row" />
          </div>
        )}

        {/* Populated Table or Truthful Empty State */}
        {!isListLoading && !listError && (
          <>
            {features.length > 0 ? (
              <>
                <FeatureListTable
                  features={features}
                  areAllActivationAncestorsActive={areAllActivationAncestorsActive}
                  onEdit={handleOpenEdit}
                  onActivate={handleActivate}
                  onRetire={handleOpenRetire}
                  onManageCapabilities={(feat) =>
                    navigate(
                      `/products/${product.id}/catalog/modules/${module.id}/features/${feat.id}`
                    )
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
                  <SlidersIcon size={28} />
                </div>
                {searchInput || statusFilter ? (
                  <>
                    <h3 className="empty-title">No matching features found</h3>
                    <p className="empty-desc">
                      No features under {module.name} matched your search or status filter.
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
                    <h3 className="empty-title">No features registered</h3>
                    <p className="empty-desc">
                      No features have been registered under {module.name}. Create your first feature to begin managing fine-grained capabilities.
                    </p>
                    <button
                      type="button"
                      className="btn btn-primary"
                      onClick={(e) => handleOpenCreate(e.currentTarget)}
                      disabled={!canCreateDraftChild}
                      title={isHierarchyTerminal ? "Cannot register features under a retired module or product" : "Register first feature"}
                    >
                      <PlusIcon size={16} />
                      Register First Feature
                    </button>
                  </>
                )}
              </div>
            )}
          </>
        )}
      </div>

      {/* Accessible Create / Edit Dialog */}
      <CatalogEntityDialog
        isOpen={isDialogOpen}
        mode={dialogMode}
        entityType="feature"
        parentId={module.id}
        parentLabel={`Module: ${module.name} (${module.code})`}
        initialData={selectedFeature}
        onClose={() => setIsDialogOpen(false)}
        onSuccess={handleDialogSuccess}
        triggerRef={triggerRef}
      />

      {/* Accessible Status-Only Retirement Dialog */}
      <CatalogRetireDialog
        isOpen={isRetireOpen}
        entityTypeLabel="Feature"
        entityCode={featureToRetire?.code || ""}
        entityName={featureToRetire?.name || ""}
        hasChildNotice={
          featureToRetire && featureToRetire.total_capabilities_count > 0
            ? `This feature currently has ${featureToRetire.total_capabilities_count} capability/capabilities.`
            : undefined
        }
        onClose={() => setIsRetireOpen(false)}
        onConfirm={handleRetireConfirm}
        triggerRef={triggerRef}
      />
    </AppShell>
  );
};
