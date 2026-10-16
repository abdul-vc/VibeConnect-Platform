/**
 * Commercial Packaging Hierarchy Section.
 *
 * Renders the 3-level commercial packaging hierarchy:
 * Product
 *   └── Module
 *         └── Feature context
 *               └── Capability
 *
 * Features are catalog context, not Plan packaging rows (Zero PlanFeature concept).
 * Row presence indicates inclusion (Zero is_included).
 * Fully tenant-isolated and respects Draft vs Active/Retired frozen lifecycle rules.
 */

import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { plansApi } from "../../api/plans.ts";
import type {
  PlanCapabilityListItem,
  PlanModuleListItem,
  PlanProductListItem,
  PlanVersionStatus,
} from "../../api/types.ts";
import {
  ChevronDownIcon,
  ChevronRightIcon,
  LayersIcon,
  PlusIcon,
  SearchIcon,
  TrashIcon,
} from "../Icons.tsx";
import {
  AddPlanCapabilityDialog,
  AddPlanModuleDialog,
  AddPlanProductDialog,
  PackagingItemType,
  RemovePackagingItemDialog,
} from "./PlanPackagingDialogs.tsx";

interface PlanPackagingSectionProps {
  readonly versionId: string;
  readonly versionStatus: PlanVersionStatus;
  readonly versionNumber: number;
  readonly onMutated: () => void;
}

export const PlanPackagingSection: React.FC<PlanPackagingSectionProps> = ({
  versionId,
  versionStatus,
  onMutated,
}) => {
  const isDraft = versionStatus === "draft";

  const [products, setProducts] = useState<readonly PlanProductListItem[]>([]);
  const [modules, setModules] = useState<readonly PlanModuleListItem[]>([]);
  const [capabilities, setCapabilities] = useState<readonly PlanCapabilityListItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchFilter, setSearchFilter] = useState("");

  // Hierarchy expand / collapse state
  const [expandedProductIds, setExpandedProductIds] = useState<Set<string>>(new Set());
  const [expandedModuleIds, setExpandedModuleIds] = useState<Set<string>>(new Set());

  // Dialog states
  const [isAddProductOpen, setIsAddProductOpen] = useState(false);

  const [addModuleTarget, setAddModuleTarget] = useState<{
    planProductId: string;
    productId: string;
    productCode: string;
    productName: string;
  } | null>(null);

  const [addCapabilityTarget, setAddCapabilityTarget] = useState<{
    planModuleId: string;
    moduleId: string;
    moduleCode: string;
    moduleName: string;
  } | null>(null);

  const [removeTarget, setRemoveTarget] = useState<{
    itemType: PackagingItemType;
    id: string;
    code: string;
    name: string;
    childModuleCount?: number;
    childCapabilityCount?: number;
  } | null>(null);

  const addProductTriggerRef = useRef<HTMLButtonElement | null>(null);

  const fetchPackaging = useCallback(async () => {
    try {
      setIsLoading(true);
      setError(null);
      const [prodRes, modRes, capRes] = await Promise.all([
        plansApi.listProducts(versionId, { page_size: 100 }),
        plansApi.listModules(versionId, { page_size: 100 }),
        plansApi.listCapabilities(versionId, { page_size: 100 }),
      ]);
      setProducts(prodRes.results);
      setModules(modRes.results);
      setCapabilities(capRes.results);

      // Auto-expand all loaded products on first load
      setExpandedProductIds((prev) => {
        if (prev.size === 0) {
          return new Set(prodRes.results.map((p) => p.id));
        }
        return prev;
      });
    } catch {
      setError("Failed to load commercial packaging data. Please check your network and retry.");
    } finally {
      setIsLoading(false);
    }
  }, [versionId]);

  useEffect(() => {
    fetchPackaging();
  }, [fetchPackaging]);

  const handleMutationSuccess = () => {
    fetchPackaging();
    onMutated();
  };

  // Grouping by stable parent IDs
  const modulesByPlanProductId = useMemo(() => {
    const map = new Map<string, PlanModuleListItem[]>();
    for (const m of modules) {
      const list = map.get(m.plan_product_id) || [];
      list.push(m);
      map.set(m.plan_product_id, list);
    }
    return map;
  }, [modules]);

  const capabilitiesByPlanModuleId = useMemo(() => {
    const map = new Map<string, PlanCapabilityListItem[]>();
    for (const c of capabilities) {
      const list = map.get(c.plan_module_id) || [];
      list.push(c);
      map.set(c.plan_module_id, list);
    }
    return map;
  }, [capabilities]);

  const existingProductIds = useMemo(() => new Set(products.map((p) => p.product_id)), [products]);
  const existingModuleIds = useMemo(() => new Set(modules.map((m) => m.module_id)), [modules]);
  const existingCapabilityIds = useMemo(() => new Set(capabilities.map((c) => c.capability_id)), [capabilities]);

  const toggleProductExpand = (id: string) => {
    setExpandedProductIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const toggleModuleExpand = (id: string) => {
    setExpandedModuleIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const handleConfirmRemove = async () => {
    if (!removeTarget) return;
    if (removeTarget.itemType === "product") {
      await plansApi.deleteProduct(removeTarget.id);
    } else if (removeTarget.itemType === "module") {
      await plansApi.deleteModule(removeTarget.id);
    } else if (removeTarget.itemType === "capability") {
      await plansApi.deleteCapability(removeTarget.id);
    }
    handleMutationSuccess();
  };

  // Filtering
  const filteredProducts = useMemo(() => {
    const query = searchFilter.toLowerCase().trim();
    if (!query) return products;

    return products.filter((p) => {
      const pMatches = p.product_name.toLowerCase().includes(query) || p.product_code.toLowerCase().includes(query);
      const childMods = modulesByPlanProductId.get(p.id) || [];
      const mMatches = childMods.some(
        (m) =>
          m.module_name.toLowerCase().includes(query) ||
          m.module_code.toLowerCase().includes(query) ||
          (capabilitiesByPlanModuleId.get(m.id) || []).some(
            (c) =>
              c.capability_name.toLowerCase().includes(query) ||
              c.capability_code.toLowerCase().includes(query) ||
              c.feature_name.toLowerCase().includes(query)
          )
      );
      return pMatches || mMatches;
    });
  }, [products, searchFilter, modulesByPlanProductId, capabilitiesByPlanModuleId]);

  return (
    <div className="packaging-workspace-section" style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>
      {/* Section Header */}
      <div className="section-header-row" style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: "1rem" }}>
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
            <h3 className="section-title" style={{ margin: 0, fontSize: "1.25rem" }}>
              Product Packaging Hierarchy
            </h3>
            <span className="badge badge-neutral">
              {products.length} {products.length === 1 ? "Product" : "Products"} • {modules.length} {modules.length === 1 ? "Module" : "Modules"} • {capabilities.length} {capabilities.length === 1 ? "Capability" : "Capabilities"}
            </span>
          </div>
          <p className="text-body" style={{ fontSize: "0.875rem", margin: "0.25rem 0 0" }}>
            Hierarchy: Product → Module → Feature Context → Capability. Adding or removing packaging cascades cleanly to descendants.
          </p>
        </div>

        {isDraft ? (
          <button
            ref={addProductTriggerRef}
            type="button"
            className="btn btn-primary"
            onClick={() => setIsAddProductOpen(true)}
            style={{ flexShrink: 0 }}
          >
            <PlusIcon size={16} />
            Package Product
          </button>
        ) : (
          <span className="badge badge-neutral" style={{ padding: "0.45rem 0.75rem", fontStyle: "italic" }}>
            Packaging is read-only ({versionStatus})
          </span>
        )}
      </div>

      {/* Search Toolbar */}
      {products.length > 0 && (
        <div className="registry-controls-bar" style={{ display: "flex", gap: "0.75rem" }}>
          <div className="search-input-wrapper" style={{ flex: 1, minWidth: "240px" }}>
            <span className="search-icon-adornment" aria-hidden="true">
              <SearchIcon size={16} />
            </span>
            <input
              type="search"
              className="registry-search-input"
              placeholder="Search packaged products, modules, features, or capabilities..."
              value={searchFilter}
              onChange={(e) => setSearchFilter(e.target.value)}
              aria-label="Filter packaging hierarchy"
            />
          </div>
        </div>
      )}

      {/* Error Alert */}
      {error && (
        <div className="alert-banner alert-banner-error" role="alert">
          <span>{error}</span>
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            onClick={fetchPackaging}
            style={{ marginLeft: "auto" }}
          >
            Retry
          </button>
        </div>
      )}

      {/* Loading Skeleton */}
      {isLoading && (
        <div className="registry-skeleton-container" aria-label="Loading packaging">
          <div className="skeleton-row" />
          <div className="skeleton-row" />
          <div className="skeleton-row" />
        </div>
      )}

      {/* Empty State */}
      {!isLoading && !error && products.length === 0 && (
        <div className="empty-state-container" style={{ padding: "3rem 1.5rem", textAlign: "center" }}>
          <div className="empty-state-icon" style={{ fontSize: "2rem", marginBottom: "0.75rem" }}>
            <LayersIcon size={32} />
          </div>
          <h4 className="empty-state-title" style={{ margin: 0 }}>
            No Products Packaged
          </h4>
          <p className="empty-state-desc" style={{ maxWidth: "460px", margin: "0.5rem auto 1.25rem" }}>
            {isDraft
              ? "Package at least one Product, Module, and Capability to fulfill readiness and activate this version."
              : "No products were packaged into this plan version."}
          </p>
          {isDraft && (
            <button
              type="button"
              className="btn btn-primary"
              onClick={() => setIsAddProductOpen(true)}
            >
              <PlusIcon size={16} />
              Package First Product
            </button>
          )}
        </div>
      )}

      {/* Hierarchy Tree */}
      {!isLoading && !error && products.length > 0 && (
        <div className="packaging-tree-container" role="tree" aria-label="Commercial packaging hierarchy">
          {filteredProducts.map((p) => {
            const isExpanded = expandedProductIds.has(p.id);
            const childModules = modulesByPlanProductId.get(p.id) || [];
            const totalCapsUnderProduct = childModules.reduce(
              (acc, m) => acc + (capabilitiesByPlanModuleId.get(m.id)?.length || 0),
              0
            );

            return (
              <div key={p.id} className="packaging-product-node" role="treeitem" aria-expanded={isExpanded}>
                {/* Product Header Row */}
                <div className="packaging-product-header">
                  <button
                    type="button"
                    className="btn-tree-toggle"
                    onClick={() => toggleProductExpand(p.id)}
                    aria-label={`${isExpanded ? "Collapse" : "Expand"} ${p.product_name}`}
                  >
                    {isExpanded ? <ChevronDownIcon size={16} /> : <ChevronRightIcon size={16} />}
                  </button>

                  <div className="packaging-product-identity">
                    <span className="product-code-pill font-mono font-bold">{p.product_code}</span>
                    <span className="packaging-item-title">{p.product_name}</span>
                    <span className="badge badge-neutral">
                      {childModules.length} {childModules.length === 1 ? "Module" : "Modules"}
                    </span>
                  </div>

                  {isDraft && (
                    <div className="packaging-node-actions" style={{ marginLeft: "auto", display: "inline-flex", gap: "0.5rem" }}>
                      <button
                        type="button"
                        className="btn btn-secondary btn-sm"
                        onClick={() =>
                          setAddModuleTarget({
                            planProductId: p.id,
                            productId: p.product_id,
                            productCode: p.product_code,
                            productName: p.product_name,
                          })
                        }
                      >
                        <PlusIcon size={14} />
                        Add Module
                      </button>
                      <button
                        type="button"
                        className="btn btn-secondary btn-sm btn-icon text-danger"
                        onClick={() =>
                          setRemoveTarget({
                            itemType: "product",
                            id: p.id,
                            code: p.product_code,
                            name: p.product_name,
                            childModuleCount: childModules.length,
                            childCapabilityCount: totalCapsUnderProduct,
                          })
                        }
                        title="Remove product"
                        aria-label={`Remove product ${p.product_name}`}
                      >
                        <TrashIcon size={14} />
                      </button>
                    </div>
                  )}
                </div>

                {/* Modules Container */}
                {isExpanded && (
                  <div className="packaging-modules-container" role="group">
                    {childModules.length === 0 ? (
                      <div className="packaging-empty-leaf text-muted">
                        No modules packaged for this product yet.
                        {isDraft && (
                          <button
                            type="button"
                            className="btn btn-link btn-sm"
                            onClick={() =>
                              setAddModuleTarget({
                                planProductId: p.id,
                                productId: p.product_id,
                                productCode: p.product_code,
                                productName: p.product_name,
                              })
                            }
                          >
                            Add Module
                          </button>
                        )}
                      </div>
                    ) : (
                      childModules.map((m) => {
                        const isModExpanded = expandedModuleIds.has(m.id);
                        const childCaps = capabilitiesByPlanModuleId.get(m.id) || [];

                        return (
                          <div key={m.id} className="packaging-module-node" role="treeitem" aria-expanded={isModExpanded}>
                            {/* Module Header Row */}
                            <div className="packaging-module-header">
                              <button
                                type="button"
                                className="btn-tree-toggle"
                                onClick={() => toggleModuleExpand(m.id)}
                                aria-label={`${isModExpanded ? "Collapse" : "Expand"} ${m.module_name}`}
                              >
                                {isModExpanded ? <ChevronDownIcon size={14} /> : <ChevronRightIcon size={14} />}
                              </button>

                              <div className="packaging-module-identity">
                                <span className="product-code-pill font-mono">{m.module_code}</span>
                                <span className="packaging-module-title">{m.module_name}</span>
                                <span className="badge badge-neutral text-caption">
                                  {childCaps.length} {childCaps.length === 1 ? "Capability" : "Capabilities"}
                                </span>
                              </div>

                              {isDraft && (
                                <div className="packaging-node-actions" style={{ marginLeft: "auto", display: "inline-flex", gap: "0.5rem" }}>
                                  <button
                                    type="button"
                                    className="btn btn-secondary btn-sm"
                                    onClick={() =>
                                      setAddCapabilityTarget({
                                        planModuleId: m.id,
                                        moduleId: m.module_id,
                                        moduleCode: m.module_code,
                                        moduleName: m.module_name,
                                      })
                                    }
                                  >
                                    <PlusIcon size={13} />
                                    Add Capability
                                  </button>
                                  <button
                                    type="button"
                                    className="btn btn-secondary btn-sm btn-icon text-danger"
                                    onClick={() =>
                                      setRemoveTarget({
                                        itemType: "module",
                                        id: m.id,
                                        code: m.module_code,
                                        name: m.module_name,
                                        childCapabilityCount: childCaps.length,
                                      })
                                    }
                                    title="Remove module"
                                    aria-label={`Remove module ${m.module_name}`}
                                  >
                                    <TrashIcon size={14} />
                                  </button>
                                </div>
                              )}
                            </div>

                            {/* Capabilities Container */}
                            {isModExpanded && (
                              <div className="packaging-capabilities-container" role="group">
                                {childCaps.length === 0 ? (
                                  <div className="packaging-empty-leaf text-muted">
                                    No capabilities packaged for this module.
                                    {isDraft && (
                                      <button
                                        type="button"
                                        className="btn btn-link btn-sm"
                                        onClick={() =>
                                          setAddCapabilityTarget({
                                            planModuleId: m.id,
                                            moduleId: m.module_id,
                                            moduleCode: m.module_code,
                                            moduleName: m.module_name,
                                          })
                                        }
                                      >
                                        Add Capability
                                      </button>
                                    )}
                                  </div>
                                ) : (
                                  <div className="capabilities-grid">
                                    {childCaps.map((c) => (
                                      <div key={c.id} className="capability-packaging-card" role="treeitem">
                                        <div className="capability-card-header">
                                          <div style={{ display: "flex", flexDirection: "column", gap: "0.2rem" }}>
                                            <span className="capability-card-name font-bold">
                                              {c.capability_name}
                                            </span>
                                            <span className="capability-card-code font-mono text-muted text-caption">
                                              {c.capability_code}
                                            </span>
                                          </div>
                                          {isDraft && (
                                            <button
                                              type="button"
                                              className="btn btn-secondary btn-sm btn-icon text-danger"
                                              onClick={() =>
                                                setRemoveTarget({
                                                  itemType: "capability",
                                                  id: c.id,
                                                  code: c.capability_code,
                                                  name: c.capability_name,
                                                })
                                              }
                                              title="Remove capability"
                                              aria-label={`Remove capability ${c.capability_name}`}
                                            >
                                              <TrashIcon size={13} />
                                            </button>
                                          )}
                                        </div>
                                        <div className="capability-card-footer">
                                          <span className="feature-context-badge">
                                            Feature: {c.feature_name} ({c.feature_code})
                                          </span>
                                        </div>
                                      </div>
                                    ))}
                                  </div>
                                )}
                              </div>
                            )}
                          </div>
                        );
                      })
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* Dialogs */}
      <AddPlanProductDialog
        isOpen={isAddProductOpen}
        onClose={() => setIsAddProductOpen(false)}
        onSuccess={handleMutationSuccess}
        versionId={versionId}
        existingProductIds={existingProductIds}
        triggerRef={addProductTriggerRef}
      />

      {addModuleTarget && (
        <AddPlanModuleDialog
          isOpen={Boolean(addModuleTarget)}
          onClose={() => setAddModuleTarget(null)}
          onSuccess={handleMutationSuccess}
          versionId={versionId}
          planProductId={addModuleTarget.planProductId}
          productId={addModuleTarget.productId}
          productCode={addModuleTarget.productCode}
          productName={addModuleTarget.productName}
          existingModuleIds={existingModuleIds}
        />
      )}

      {addCapabilityTarget && (
        <AddPlanCapabilityDialog
          isOpen={Boolean(addCapabilityTarget)}
          onClose={() => setAddCapabilityTarget(null)}
          onSuccess={handleMutationSuccess}
          versionId={versionId}
          planModuleId={addCapabilityTarget.planModuleId}
          moduleId={addCapabilityTarget.moduleId}
          moduleCode={addCapabilityTarget.moduleCode}
          moduleName={addCapabilityTarget.moduleName}
          existingCapabilityIds={existingCapabilityIds}
        />
      )}

      {removeTarget && (
        <RemovePackagingItemDialog
          isOpen={Boolean(removeTarget)}
          onClose={() => setRemoveTarget(null)}
          onConfirm={handleConfirmRemove}
          itemType={removeTarget.itemType}
          code={removeTarget.code}
          name={removeTarget.name}
          childModuleCount={removeTarget.childModuleCount}
          childCapabilityCount={removeTarget.childCapabilityCount}
        />
      )}
    </div>
  );
};
