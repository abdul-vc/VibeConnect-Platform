/**
 * Commercial Packaging Dialogs.
 *
 * Implements accessible, keyboard-trapped, focus-restoring modals for:
 * - Add Product to Plan
 * - Add Module to Product
 * - Add Capability to Module (grouped by Feature)
 * - Remove Packaging Item confirmation (with explicit cascade notices)
 */

import React, { useEffect, useRef, useState } from "react";
import { catalogApi } from "../../api/catalog.ts";
import { plansApi } from "../../api/plans.ts";
import { productsApi } from "../../api/products.ts";
import type {
  ProductCapabilityListItem,
  ProductFeatureListItem,
  ProductListItem,
  ProductModuleListItem,
} from "../../api/types.ts";
import { AlertCircleIcon, SearchIcon } from "../Icons.tsx";
import { FormErrorBanner, parseApiErrors, PlanModalShell } from "./PlanModalShell.tsx";

// ---------------------------------------------------------------------------
// 1. Add Product to Plan Dialog
// ---------------------------------------------------------------------------

interface AddPlanProductDialogProps {
  readonly isOpen: boolean;
  readonly onClose: () => void;
  readonly onSuccess: () => void;
  readonly versionId: string;
  readonly existingProductIds: ReadonlySet<string>;
  readonly triggerRef?: React.RefObject<HTMLElement | null>;
}

export const AddPlanProductDialog: React.FC<AddPlanProductDialogProps> = ({
  isOpen,
  onClose,
  onSuccess,
  versionId,
  existingProductIds,
  triggerRef,
}) => {
  const [search, setSearch] = useState("");
  const [products, setProducts] = useState<readonly ProductListItem[]>([]);
  const [selectedProductId, setSelectedProductId] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [generalError, setGeneralError] = useState<string | null>(null);
  const initialFocusRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    if (isOpen) {
      setSearch("");
      setSelectedProductId(null);
      setIsSubmitting(false);
      setGeneralError(null);
      loadProducts("");
    }
  }, [isOpen]);

  const loadProducts = async (query: string) => {
    try {
      setIsLoading(true);
      const res = await productsApi.list({ search: query ? query.trim() : undefined, page_size: 50 });
      setProducts(res.results);
    } catch {
      setGeneralError("Failed to load available products from catalog.");
    } finally {
      setIsLoading(false);
    }
  };

  const handleSearchChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const val = e.target.value;
    setSearch(val);
    loadProducts(val);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedProductId) {
      setGeneralError("Please select a product to add.");
      return;
    }

    try {
      setIsSubmitting(true);
      setGeneralError(null);
      await plansApi.addProduct(versionId, { product_id: selectedProductId });
      onSuccess();
      onClose();
    } catch (err: unknown) {
      const { generalError: errGen } = parseApiErrors(err);
      setGeneralError(errGen || "Failed to add product to plan.");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <PlanModalShell
      isOpen={isOpen}
      onClose={onClose}
      isSubmitting={isSubmitting}
      title="Package Product into Plan"
      subtitle="Select a product from the Product Registry to package into this draft plan version."
      onSubmit={handleSubmit}
      submitLabel="Add Product"
      submittingLabel="Adding..."
      submitDisabled={!selectedProductId}
      triggerRef={triggerRef}
      initialFocusRef={initialFocusRef}
    >
      <FormErrorBanner error={generalError} />

      <div className="form-group">
        <label htmlFor="search-available-products" className="form-label">
          Search Catalog Products
        </label>
        <div className="input-with-icon">
          <SearchIcon size={16} className="input-icon-left" />
          <input
            id="search-available-products"
            ref={initialFocusRef}
            type="search"
            className="form-input with-left-icon"
            placeholder="Search by product code or name..."
            value={search}
            onChange={handleSearchChange}
            disabled={isSubmitting}
          />
        </div>
      </div>

      <div className="catalog-selector-list" role="radiogroup" aria-label="Available products">
        {isLoading ? (
          <div className="p-4 text-center text-muted">Loading products...</div>
        ) : products.length === 0 ? (
          <div className="p-4 text-center text-muted">No matching products found.</div>
        ) : (
          products.map((p) => {
            const isAlreadyPackaged = existingProductIds.has(p.id);
            const isSelected = selectedProductId === p.id;
            return (
              <div
                key={p.id}
                className={`catalog-selector-item ${isSelected ? "selected" : ""} ${
                  isAlreadyPackaged ? "disabled" : ""
                }`}
                onClick={() => {
                  if (!isAlreadyPackaged && !isSubmitting) setSelectedProductId(p.id);
                }}
                role="radio"
                aria-checked={isSelected}
                aria-disabled={isAlreadyPackaged}
                tabIndex={isAlreadyPackaged ? -1 : 0}
                onKeyDown={(e) => {
                  if (e.key === " " || e.key === "Enter") {
                    e.preventDefault();
                    if (!isAlreadyPackaged && !isSubmitting) setSelectedProductId(p.id);
                  }
                }}
              >
                <div className="catalog-item-info">
                  <span className="catalog-item-name">{p.name}</span>
                  <span className="catalog-item-code">{p.code}</span>
                </div>
                {isAlreadyPackaged ? (
                  <span className="badge badge-neutral">Packaged</span>
                ) : (
                  <span className={`badge badge-${p.status === "active" ? "success" : "warning"}`}>
                    {p.status}
                  </span>
                )}
              </div>
            );
          })
        )}
      </div>
    </PlanModalShell>
  );
};

// ---------------------------------------------------------------------------
// 2. Add Module to Product Dialog
// ---------------------------------------------------------------------------

interface AddPlanModuleDialogProps {
  readonly isOpen: boolean;
  readonly onClose: () => void;
  readonly onSuccess: () => void;
  readonly versionId: string;
  readonly planProductId: string;
  readonly productId: string;
  readonly productCode: string;
  readonly productName: string;
  readonly existingModuleIds: ReadonlySet<string>;
  readonly triggerRef?: React.RefObject<HTMLElement | null>;
}

export const AddPlanModuleDialog: React.FC<AddPlanModuleDialogProps> = ({
  isOpen,
  onClose,
  onSuccess,
  versionId,
  planProductId,
  productId,
  productCode,
  productName,
  existingModuleIds,
  triggerRef,
}) => {
  const [search, setSearch] = useState("");
  const [modules, setModules] = useState<readonly ProductModuleListItem[]>([]);
  const [selectedModuleId, setSelectedModuleId] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [generalError, setGeneralError] = useState<string | null>(null);
  const initialFocusRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    if (isOpen) {
      setSearch("");
      setSelectedModuleId(null);
      setIsSubmitting(false);
      setGeneralError(null);
      loadModules("");
    }
  }, [isOpen, productId]);

  const loadModules = async (query: string) => {
    try {
      setIsLoading(true);
      const res = await catalogApi.modules.list({
        product_id: productId,
        search: query ? query.trim() : undefined,
        page_size: 50,
      });
      setModules(res.results);
    } catch {
      setGeneralError("Failed to load available catalog modules.");
    } finally {
      setIsLoading(false);
    }
  };

  const handleSearchChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const val = e.target.value;
    setSearch(val);
    loadModules(val);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedModuleId) {
      setGeneralError("Please select a module to add.");
      return;
    }

    try {
      setIsSubmitting(true);
      setGeneralError(null);
      await plansApi.addModule(versionId, {
        plan_product_id: planProductId,
        module_id: selectedModuleId,
      });
      onSuccess();
      onClose();
    } catch (err: unknown) {
      const { generalError: errGen } = parseApiErrors(err);
      setGeneralError(errGen || "Failed to add module to product.");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <PlanModalShell
      isOpen={isOpen}
      onClose={onClose}
      isSubmitting={isSubmitting}
      title="Add Module to Product"
      subtitle={`Packaging module into ${productName} (${productCode})`}
      onSubmit={handleSubmit}
      submitLabel="Add Module"
      submittingLabel="Adding..."
      submitDisabled={!selectedModuleId}
      triggerRef={triggerRef}
      initialFocusRef={initialFocusRef}
    >
      <FormErrorBanner error={generalError} />

      <div className="form-group">
        <label htmlFor="search-available-modules" className="form-label">
          Search Catalog Modules for {productCode}
        </label>
        <div className="input-with-icon">
          <SearchIcon size={16} className="input-icon-left" />
          <input
            id="search-available-modules"
            ref={initialFocusRef}
            type="search"
            className="form-input with-left-icon"
            placeholder="Search modules..."
            value={search}
            onChange={handleSearchChange}
            disabled={isSubmitting}
          />
        </div>
      </div>

      <div className="catalog-selector-list" role="radiogroup" aria-label="Available modules">
        {isLoading ? (
          <div className="p-4 text-center text-muted">Loading modules...</div>
        ) : modules.length === 0 ? (
          <div className="p-4 text-center text-muted">No modules found for this product.</div>
        ) : (
          modules.map((m) => {
            const isAlreadyPackaged = existingModuleIds.has(m.id);
            const isSelected = selectedModuleId === m.id;
            return (
              <div
                key={m.id}
                className={`catalog-selector-item ${isSelected ? "selected" : ""} ${
                  isAlreadyPackaged ? "disabled" : ""
                }`}
                onClick={() => {
                  if (!isAlreadyPackaged && !isSubmitting) setSelectedModuleId(m.id);
                }}
                role="radio"
                aria-checked={isSelected}
                aria-disabled={isAlreadyPackaged}
                tabIndex={isAlreadyPackaged ? -1 : 0}
                onKeyDown={(e) => {
                  if (e.key === " " || e.key === "Enter") {
                    e.preventDefault();
                    if (!isAlreadyPackaged && !isSubmitting) setSelectedModuleId(m.id);
                  }
                }}
              >
                <div className="catalog-item-info">
                  <span className="catalog-item-name">{m.name}</span>
                  <span className="catalog-item-code">{m.code}</span>
                </div>
                {isAlreadyPackaged ? (
                  <span className="badge badge-neutral">Packaged</span>
                ) : (
                  <span className={`badge badge-${m.status === "active" ? "success" : "warning"}`}>
                    {m.status}
                  </span>
                )}
              </div>
            );
          })
        )}
      </div>
    </PlanModalShell>
  );
};

// ---------------------------------------------------------------------------
// 3. Add Capability to Module Dialog
// ---------------------------------------------------------------------------

interface FeatureWithCapabilities {
  readonly feature: ProductFeatureListItem;
  readonly capabilities: readonly ProductCapabilityListItem[];
}

interface AddPlanCapabilityDialogProps {
  readonly isOpen: boolean;
  readonly onClose: () => void;
  readonly onSuccess: () => void;
  readonly versionId: string;
  readonly planModuleId: string;
  readonly moduleId: string;
  readonly moduleCode: string;
  readonly moduleName: string;
  readonly existingCapabilityIds: ReadonlySet<string>;
  readonly triggerRef?: React.RefObject<HTMLElement | null>;
}

export const AddPlanCapabilityDialog: React.FC<AddPlanCapabilityDialogProps> = ({
  isOpen,
  onClose,
  onSuccess,
  versionId,
  planModuleId,
  moduleId,
  moduleCode,
  moduleName,
  existingCapabilityIds,
  triggerRef,
}) => {
  const [search, setSearch] = useState("");
  const [featureGroups, setFeatureGroups] = useState<readonly FeatureWithCapabilities[]>([]);
  const [selectedCapabilityId, setSelectedCapabilityId] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [generalError, setGeneralError] = useState<string | null>(null);
  const initialFocusRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    if (isOpen) {
      setSearch("");
      setSelectedCapabilityId(null);
      setIsSubmitting(false);
      setGeneralError(null);
      loadFeaturesAndCapabilities("");
    }
  }, [isOpen, moduleId]);

  const loadFeaturesAndCapabilities = async (query: string) => {
    try {
      setIsLoading(true);
      const featRes = await catalogApi.features.list({
        module_id: moduleId,
        page_size: 50,
      });

      const groups: FeatureWithCapabilities[] = [];
      const lowerQuery = query.toLowerCase().trim();

      for (const feat of featRes.results) {
        const capRes = await catalogApi.capabilities.list({
          feature_id: feat.id,
          page_size: 100,
        });

        const filteredCaps = lowerQuery
          ? capRes.results.filter(
              (c) =>
                c.name.toLowerCase().includes(lowerQuery) ||
                c.code.toLowerCase().includes(lowerQuery) ||
                feat.name.toLowerCase().includes(lowerQuery)
            )
          : capRes.results;

        if (filteredCaps.length > 0) {
          groups.push({
            feature: feat,
            capabilities: filteredCaps,
          });
        }
      }

      setFeatureGroups(groups);
    } catch {
      setGeneralError("Failed to load module capabilities from catalog.");
    } finally {
      setIsLoading(false);
    }
  };

  const handleSearchChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const val = e.target.value;
    setSearch(val);
    loadFeaturesAndCapabilities(val);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedCapabilityId) {
      setGeneralError("Please select a capability to add.");
      return;
    }

    try {
      setIsSubmitting(true);
      setGeneralError(null);
      await plansApi.addCapability(versionId, {
        plan_module_id: planModuleId,
        capability_id: selectedCapabilityId,
      });
      onSuccess();
      onClose();
    } catch (err: unknown) {
      const { generalError: errGen } = parseApiErrors(err);
      setGeneralError(errGen || "Failed to add capability.");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <PlanModalShell
      isOpen={isOpen}
      onClose={onClose}
      isSubmitting={isSubmitting}
      title="Add Capability to Module"
      subtitle={`Packaging capability under ${moduleName} (${moduleCode})`}
      onSubmit={handleSubmit}
      submitLabel="Add Capability"
      submittingLabel="Adding..."
      submitDisabled={!selectedCapabilityId}
      triggerRef={triggerRef}
      initialFocusRef={initialFocusRef}
    >
      <FormErrorBanner error={generalError} />

      <div className="form-group">
        <label htmlFor="search-available-caps" className="form-label">
          Search Capabilities in {moduleCode}
        </label>
        <div className="input-with-icon">
          <SearchIcon size={16} className="input-icon-left" />
          <input
            id="search-available-caps"
            ref={initialFocusRef}
            type="search"
            className="form-input with-left-icon"
            placeholder="Search capabilities or features..."
            value={search}
            onChange={handleSearchChange}
            disabled={isSubmitting}
          />
        </div>
      </div>

      <div className="catalog-selector-list" role="radiogroup" aria-label="Available capabilities">
        {isLoading ? (
          <div className="p-4 text-center text-muted">Loading capabilities...</div>
        ) : featureGroups.length === 0 ? (
          <div className="p-4 text-center text-muted">No capabilities found for this module.</div>
        ) : (
          featureGroups.map((grp) => (
            <div key={grp.feature.id} className="feature-group-section">
              <div className="feature-group-header">
                <span className="feature-group-title">Feature: {grp.feature.name}</span>
                <span className="feature-group-code">({grp.feature.code})</span>
              </div>
              <div className="feature-group-caps">
                {grp.capabilities.map((c) => {
                  const isAlreadyPackaged = existingCapabilityIds.has(c.id);
                  const isSelected = selectedCapabilityId === c.id;
                  return (
                    <div
                      key={c.id}
                      className={`catalog-selector-item ${isSelected ? "selected" : ""} ${
                        isAlreadyPackaged ? "disabled" : ""
                      }`}
                      onClick={() => {
                        if (!isAlreadyPackaged && !isSubmitting) setSelectedCapabilityId(c.id);
                      }}
                      role="radio"
                      aria-checked={isSelected}
                      aria-disabled={isAlreadyPackaged}
                      tabIndex={isAlreadyPackaged ? -1 : 0}
                      onKeyDown={(e) => {
                        if (e.key === " " || e.key === "Enter") {
                          e.preventDefault();
                          if (!isAlreadyPackaged && !isSubmitting) setSelectedCapabilityId(c.id);
                        }
                      }}
                    >
                      <div className="catalog-item-info">
                        <span className="catalog-item-name">{c.name}</span>
                        <span className="catalog-item-code">{c.code}</span>
                      </div>
                      {isAlreadyPackaged ? (
                        <span className="badge badge-neutral">Packaged</span>
                      ) : (
                        <span className={`badge badge-${c.status === "active" ? "success" : "warning"}`}>
                          {c.status}
                        </span>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          ))
        )}
      </div>
    </PlanModalShell>
  );
};

// ---------------------------------------------------------------------------
// 4. Remove Packaging Item Confirmation Dialog (Cascade Impact)
// ---------------------------------------------------------------------------

export type PackagingItemType = "product" | "module" | "capability";

interface RemovePackagingItemDialogProps {
  readonly isOpen: boolean;
  readonly onClose: () => void;
  readonly onConfirm: () => Promise<void>;
  readonly itemType: PackagingItemType;
  readonly code: string;
  readonly name: string;
  readonly childModuleCount?: number;
  readonly childCapabilityCount?: number;
  readonly triggerRef?: React.RefObject<HTMLElement | null>;
}

export const RemovePackagingItemDialog: React.FC<RemovePackagingItemDialogProps> = ({
  isOpen,
  onClose,
  onConfirm,
  itemType,
  code,
  name,
  childModuleCount = 0,
  childCapabilityCount = 0,
  triggerRef,
}) => {
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [generalError, setGeneralError] = useState<string | null>(null);

  useEffect(() => {
    if (isOpen) {
      setIsSubmitting(false);
      setGeneralError(null);
    }
  }, [isOpen]);

  const handleAction = async () => {
    try {
      setIsSubmitting(true);
      setGeneralError(null);
      await onConfirm();
      onClose();
    } catch (err: unknown) {
      const { generalError: errGen } = parseApiErrors(err);
      setGeneralError(errGen || `Failed to remove ${itemType}.`);
      setIsSubmitting(false);
    }
  };

  const titles: Record<PackagingItemType, string> = {
    product: "Remove Packaged Product",
    module: "Remove Packaged Module",
    capability: "Remove Packaged Capability",
  };

  return (
    <PlanModalShell
      isOpen={isOpen}
      onClose={onClose}
      isSubmitting={isSubmitting}
      title={titles[itemType]}
      subtitle={`Removing ${name} (${code}) from plan version packaging`}
      onActionClick={handleAction}
      submitLabel={`Remove ${itemType.charAt(0).toUpperCase() + itemType.slice(1)}`}
      submittingLabel="Removing..."
      submitVariant="danger"
      triggerRef={triggerRef}
    >
      <FormErrorBanner error={generalError} />

      <div className="alert-box alert-danger" role="alert">
        <AlertCircleIcon size={16} style={{ flexShrink: 0 }} />
        <div>
          <strong>Cascade Warning:</strong>
          {itemType === "product" && (
            <p className="mt-1 mb-0">
              Removing this product will atomically remove its <strong>{childModuleCount}</strong> child module(s),{" "}
              <strong>{childCapabilityCount}</strong> child capability(ies), and any descendant server-side quota rows.
            </p>
          )}
          {itemType === "module" && (
            <p className="mt-1 mb-0">
              Removing this module will atomically remove its <strong>{childCapabilityCount}</strong> child
              capability(ies) and descendant quotas. The parent Product will remain packaged.
            </p>
          )}
          {itemType === "capability" && (
            <p className="mt-1 mb-0">
              Removing this capability will detach it and any targeted quotas. The parent Module and Product
              will remain packaged.
            </p>
          )}
        </div>
      </div>

      <p className="dialog-text">
        Are you sure you want to remove <strong>{name}</strong> (<code>{code}</code>)? This action cannot be undone on this draft version.
      </p>
    </PlanModalShell>
  );
};
