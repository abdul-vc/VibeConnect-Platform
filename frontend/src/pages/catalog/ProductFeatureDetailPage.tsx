/**
 * Product Feature Detail Page (Tier 3: Product Capabilities).
 *
 * Dedicated Platform Owner portal for managing atomic capabilities belonging to one Feature.
 * Strictly validates deep route ancestry:
 *   module.product_id === product.id
 *   feature.product_id === product.id
 *   feature.module_id === module.id
 * Capabilities cannot be loaded or mutated until strict route ancestry is validated.
 */

import React, { useCallback, useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { catalogApi, extractCatalogErrorMessage } from "../../api/catalog.ts";
import { productsApi } from "../../api/products.ts";
import type {
  CatalogOrderingField,
  CatalogStatus,
  ProductCapabilityListItem,
  ProductDetail,
  ProductFeatureDetail,
  ProductModuleDetail,
} from "../../api/types.ts";
import { AppShell } from "../../components/AppShell.tsx";
import {
  AlertCircleIcon,
  ChevronLeftIcon,
  ChevronRightIcon,
  CloseIcon,
  KeyIcon,
  PlusIcon,
  RotateCcwIcon,
} from "../../components/Icons.tsx";
import { CapabilityListTable } from "../../components/catalog/CapabilityListTable.tsx";
import { CatalogAncestorBanner } from "../../components/catalog/CatalogAncestorBanner.tsx";
import { CatalogHierarchyNav } from "../../components/catalog/CatalogHierarchyNav.tsx";
import { CatalogEntityDialog, type CatalogEntityFormData } from "../../components/catalog/CatalogEntityDialog.tsx";
import { CatalogFilterToolbar } from "../../components/catalog/CatalogFilterToolbar.tsx";
import { CatalogRetireDialog } from "../../components/catalog/CatalogRetireDialog.tsx";

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

export const ProductFeatureDetailPage: React.FC = () => {
  const { productId, moduleId, featureId } = useParams<{
    productId: string;
    moduleId: string;
    featureId: string;
  }>();

  // Ancestor State
  const [product, setProduct] = useState<ProductDetail | null>(null);
  const [module, setModule] = useState<ProductModuleDetail | null>(null);
  const [feature, setFeature] = useState<ProductFeatureDetail | null>(null);
  const [isAncestorLoading, setIsAncestorLoading] = useState<boolean>(true);
  const [ancestorError, setAncestorError] = useState<string | null>(null);
  const [isHierarchyValid, setIsHierarchyValid] = useState<boolean>(false);
  const ancestorAbortRef = useRef<AbortController | null>(null);
  const ancestorSeqRef = useRef<number>(0);

  // Capability List State
  const [capabilities, setCapabilities] = useState<ProductCapabilityListItem[]>([]);
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
  const [selectedCapability, setSelectedCapability] = useState<CatalogEntityFormData | null>(null);

  // Retire Modal State
  const [isRetireOpen, setIsRetireOpen] = useState<boolean>(false);
  const [capabilityToRetire, setCapabilityToRetire] = useState<ProductCapabilityListItem | null>(null);
  const triggerRef = useRef<HTMLElement | null>(null);

  // Debounce search input (300ms)
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearch(searchInput.trim());
      setPage(1);
    }, 300);
    return () => clearTimeout(timer);
  }, [searchInput]);

  // Load and Verify Ancestor Context (Product + Module + Feature)
  const fetchAncestorContext = useCallback(async (isBackground = false) => {
    if (!productId || !moduleId || !featureId) return;

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
      // In parallel, fetch parent Product, Module, and Feature
      const [prodRes, modRes, featRes] = await Promise.all([
        productsApi.get(productId),
        catalogApi.modules.get(moduleId, controller.signal),
        catalogApi.features.get(featureId, controller.signal),
      ]);

      if (currentSeq === ancestorSeqRef.current && !controller.signal.aborted) {
        // Enforce strict 3-tier deep route ancestry verification
        const isModuleUnderProduct = modRes.product_id === prodRes.id;
        const isFeatureUnderProduct = featRes.product_id === prodRes.id;
        const isFeatureUnderModule = featRes.module_id === modRes.id;

        if (!isModuleUnderProduct || !isFeatureUnderProduct || !isFeatureUnderModule) {
          if (!isBackground) {
            setIsAncestorLoading(false);
            setIsHierarchyValid(false);
            setAncestorError(
              `Hierarchy Mismatch: Feature "${featRes.name}" (${featRes.code}) does not belong to Module "${modRes.name}" under Product "${prodRes.name}".`
            );
          }
          return;
        }

        setProduct(prodRes);
        setModule(modRes);
        setFeature(featRes);
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
            "Unable to load feature context. The feature, module, or product may not exist or has been removed."
          );
        } else {
          setMutationWarning(
            "Notice: Could not refresh feature counters. The capabilities list remains updated."
          );
        }
      }
    }
  }, [productId, moduleId, featureId]);

  useEffect(() => {
    fetchAncestorContext();
    return () => {
      ancestorAbortRef.current?.abort();
    };
  }, [fetchAncestorContext]);

  // Load Capabilities List (Only executed after 3-tier ancestry is strictly validated)
  const fetchCapabilities = useCallback(async () => {
    if (!featureId || !isHierarchyValid || isAncestorLoading || ancestorError) return;

    listAbortRef.current?.abort();
    const currentSeq = ++listSeqRef.current;
    const controller = new AbortController();
    listAbortRef.current = controller;

    setIsListLoading(true);
    setListError(null);

    try {
      const params = {
        feature_id: featureId,
        page,
        page_size: pageSize,
        search: debouncedSearch || undefined,
        status: (statusFilter as CatalogStatus) || undefined,
        ordering,
      };

      const response = await catalogApi.capabilities.list(params, controller.signal);

      if (currentSeq === listSeqRef.current && !controller.signal.aborted) {
        setCapabilities(response.results as ProductCapabilityListItem[]);
        setTotalCount(response.count);
        setHasNext(Boolean(response.next));
        setHasPrevious(Boolean(response.previous));
        setIsListLoading(false);
        setLiveAnnouncement(
          `Loaded ${response.results.length} capabilities. Total ${response.count} items.`
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
        const msg = "Unable to load feature capabilities. Please verify your connection and try again.";
        setListError(msg);
        setLiveAnnouncement(msg);
      }
    }
  }, [featureId, isHierarchyValid, isAncestorLoading, ancestorError, page, debouncedSearch, statusFilter, ordering]);

  useEffect(() => {
    if (isHierarchyValid) {
      fetchCapabilities();
    }
    return () => {
      listAbortRef.current?.abort();
    };
  }, [isHierarchyValid, fetchCapabilities]);

  // Dialog Handlers
  const handleOpenCreate = (btnElement: HTMLElement) => {
    triggerRef.current = btnElement;
    setDialogMode("create");
    setSelectedCapability(null);
    setIsDialogOpen(true);
  };

  const handleOpenEdit = (cap: ProductCapabilityListItem, btnElement: HTMLElement) => {
    triggerRef.current = btnElement;
    setDialogMode("edit");
    setSelectedCapability({
      id: cap.id,
      code: cap.code,
      name: cap.name,
      description: cap.description,
      display_order: cap.display_order,
      status: cap.status,
    });
    setIsDialogOpen(true);
  };

  const handleOpenRetire = (cap: ProductCapabilityListItem, btnElement: HTMLElement) => {
    triggerRef.current = btnElement;
    setCapabilityToRetire(cap);
    setIsRetireOpen(true);
  };

  const refreshAfterMutation = useCallback(async () => {
    setMutationError(null);
    await Promise.allSettled([
      fetchCapabilities(),
      fetchAncestorContext(true),
    ]);
  }, [fetchCapabilities, fetchAncestorContext]);

  const handleActivate = async (cap: ProductCapabilityListItem) => {
    try {
      setMutationError(null);
      setLiveAnnouncement(`Activating capability ${cap.name}...`);
      await catalogApi.capabilities.patch(cap.id, { status: "active" });
      setLiveAnnouncement(`Capability ${cap.name} is now Active.`);
      await refreshAfterMutation();
    } catch (err: unknown) {
      const msg = extractCatalogErrorMessage(err, "Failed to activate capability.");
      setMutationError(msg);
      setLiveAnnouncement(msg);
    }
  };

  const handleRetireConfirm = async () => {
    if (!capabilityToRetire) return;
    try {
      setMutationError(null);
      setLiveAnnouncement(`Retiring capability ${capabilityToRetire.name}...`);
      await catalogApi.capabilities.patch(capabilityToRetire.id, { status: "retired" });
      setLiveAnnouncement(`Capability ${capabilityToRetire.name} has been retired.`);
      await refreshAfterMutation();
    } catch (err: unknown) {
      const msg = extractCatalogErrorMessage(err, "Failed to retire capability.");
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
  if (ancestorError || !isHierarchyValid || !product || !module || !feature) {
    return (
      <AppShell>
        <div className="catalog-error-card">
          <div className="error-icon-circle">
            <AlertCircleIcon size={32} />
          </div>
          <h2 className="heading-title">Hierarchy Mismatch or Missing Feature</h2>
          <p className="text-body" style={{ maxWidth: "560px", textAlign: "center" }}>
            {ancestorError || "The requested feature does not belong to the specified product and module ancestry."}
          </p>
          <div style={{ display: "flex", gap: "0.75rem", marginTop: "0.75rem", flexWrap: "wrap", justifyContent: "center" }}>
            {productId && moduleId && (
              <Link
                to={`/products/${productId}/catalog/modules/${moduleId}`}
                className="btn btn-primary"
              >
                <ChevronLeftIcon size={16} />
                Return to Module Features
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

  // Tier 3 Lifecycle Booleans (Centralized & Explicit)
  const isHierarchyTerminal =
    product.status === "retired" || module.status === "retired" || feature.status === "retired";
  const canCreateDraftChild = !isHierarchyTerminal;
  const areAllActivationAncestorsActive =
    product.status === "active" && module.status === "active" && feature.status === "active";
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
            {
              label: module.name,
              code: module.code,
              path: `/products/${product.id}/catalog/modules/${module.id}`,
            },
            { label: feature.name, code: feature.code },
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
            {
              type: "feature",
              id: feature.id,
              code: feature.code,
              name: feature.name,
              status: feature.status,
            },
          ]}
        />

        {/* Catalog Tier Header */}
        <div className="catalog-header-bar">
          <div className="catalog-header-text">
            <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", flexWrap: "wrap" }}>
              <div className="tier-badge-icon">
                <KeyIcon size={20} />
              </div>
              <h1 className="heading-title" style={{ margin: 0 }}>
                Feature Capabilities
              </h1>
              {!isListLoading && (
                <span className="registry-count-badge">
                  {totalCount} {totalCount === 1 ? "Capability" : "Capabilities"}
                </span>
              )}
            </div>
            <p className="text-caption" style={{ marginTop: "0.25rem", maxWidth: "720px" }}>
              Atomic capabilities and permissions provided by{" "}
              <strong>{feature.name}</strong> ({feature.code}). These leaf items define granular tenant entitlements.
            </p>
          </div>

          <div className="catalog-header-action">
            <button
              type="button"
              className="btn btn-primary"
              onClick={(e) => handleOpenCreate(e.currentTarget)}
              disabled={!canCreateDraftChild}
              title={!canCreateDraftChild ? "Cannot register capabilities under a retired feature, module, or product" : "Register new capability"}
            >
              <PlusIcon size={16} />
              Register Capability
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
          entityTypePlural="capabilities"
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
              onClick={fetchCapabilities}
              style={{ marginLeft: "auto" }}
            >
              <RotateCcwIcon size={14} />
              Retry
            </button>
          </div>
        )}

        {/* Loading Skeleton */}
        {isListLoading && (
          <div className="catalog-skeleton-container" aria-label="Loading capabilities">
            <div className="skeleton-row" />
            <div className="skeleton-row" />
            <div className="skeleton-row" />
          </div>
        )}

        {/* Populated Table or Truthful Empty State */}
        {!isListLoading && !listError && (
          <>
            {capabilities.length > 0 ? (
              <>
                <CapabilityListTable
                  capabilities={capabilities}
                  areAllActivationAncestorsActive={areAllActivationAncestorsActive}
                  onEdit={handleOpenEdit}
                  onActivate={handleActivate}
                  onRetire={handleOpenRetire}
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
                  <KeyIcon size={28} />
                </div>
                {searchInput || statusFilter ? (
                  <>
                    <h3 className="empty-title">No matching capabilities found</h3>
                    <p className="empty-desc">
                      No capabilities under {feature.name} matched your search or status filter.
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
                    <h3 className="empty-title">No capabilities registered</h3>
                    <p className="empty-desc">
                      No atomic capabilities have been registered under {feature.name}. Register granular capabilities to enable tenant permissions and SKU packing.
                    </p>
                    <button
                      type="button"
                      className="btn btn-primary"
                      onClick={(e) => handleOpenCreate(e.currentTarget)}
                      disabled={!canCreateDraftChild}
                      title={isHierarchyTerminal ? "Cannot register capabilities under a retired feature, module, or product" : "Register first capability"}
                    >
                      <PlusIcon size={16} />
                      Register First Capability
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
        entityType="capability"
        parentId={feature.id}
        parentLabel={`Feature: ${feature.name} (${feature.code})`}
        initialData={selectedCapability}
        onClose={() => setIsDialogOpen(false)}
        onSuccess={handleDialogSuccess}
        triggerRef={triggerRef}
      />

      {/* Accessible Status-Only Retirement Dialog */}
      <CatalogRetireDialog
        isOpen={isRetireOpen}
        entityTypeLabel="Capability"
        entityCode={capabilityToRetire?.code || ""}
        entityName={capabilityToRetire?.name || ""}
        onClose={() => setIsRetireOpen(false)}
        onConfirm={handleRetireConfirm}
        triggerRef={triggerRef}
      />
    </AppShell>
  );
};
