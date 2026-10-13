/**
 * Commercial Plan Quota Management Section.
 *
 * Provides a production-grade workspace for managing PlanQuotas under a PlanVersion:
 * - Server-paginated table with scope, search, and ordering filters (only approved backend params)
 * - Exact string preservation for limit values (zero Number / parseInt / parseFloat conversion)
 * - Target resolution across Plan, Product, Module, and Capability packaging levels
 * - Draft-only mutations (Create, Edit 6 mutable fields, Delete with readiness warning)
 * - Read-only freeze for Active and Retired versions
 * - Responsive desktop table and mobile/tablet card view
 */

import React, { useCallback, useEffect, useRef, useState } from "react";
import { plansApi } from "../../api/plans.ts";
import { formatDateTime } from "../../config/dateUtils.ts";
import type {
  PlanCapabilityListItem,
  PlanModuleListItem,
  PlanProductListItem,
  PlanQuotaListItem,
  PlanQuotaListParams,
  PlanQuotaScope,
  PlanVersionStatus,
} from "../../api/types.ts";
import {
  ChevronDownIcon,
  ChevronLeftIcon,
  ChevronRightIcon,
  EditIcon,
  FilterIcon,
  PlusIcon,
  SearchIcon,
  TrashIcon,
} from "../Icons.tsx";
import {
  CreatePlanQuotaDialog,
  DeletePlanQuotaDialog,
  EditPlanQuotaDialog,
  SUPPORTED_SCOPES,
} from "./PlanQuotaDialogs.tsx";

interface PlanQuotaSectionProps {
  readonly versionId: string;
  readonly versionStatus: PlanVersionStatus;
  readonly versionNumber: number;
  readonly refreshTrigger?: number;
  readonly onMutated: () => void;
  readonly onQuotasCountChange?: (count: number) => void;
}

export const PlanQuotaSection: React.FC<PlanQuotaSectionProps> = ({
  versionId,
  versionStatus,
  versionNumber,
  refreshTrigger,
  onMutated,
  onQuotasCountChange,
}) => {
  const isDraft = versionStatus === "draft";

  const [quotas, setQuotas] = useState<readonly PlanQuotaListItem[]>([]);
  const [totalCount, setTotalCount] = useState<number>(0);
  const [page, setPage] = useState<number>(1);
  const [pageSize] = useState<number>(10);
  const [scopeFilter, setScopeFilter] = useState<PlanQuotaScope | "all">("all");
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [debouncedSearch, setDebouncedSearch] = useState<string>("");
  const [ordering, setOrdering] = useState<"scope" | "quota_key" | "name">("scope");
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // Target label resolution maps
  const [productsMap, setProductsMap] = useState<Record<string, PlanProductListItem>>({});
  const [modulesMap, setModulesMap] = useState<Record<string, PlanModuleListItem>>({});
  const [capabilitiesMap, setCapabilitiesMap] = useState<Record<string, PlanCapabilityListItem>>({});

  // Dialog states
  const [isCreateOpen, setIsCreateOpen] = useState<boolean>(false);
  const [editingQuota, setEditingQuota] = useState<PlanQuotaListItem | null>(null);
  const [deletingQuota, setDeletingQuota] = useState<PlanQuotaListItem | null>(null);

  const createTriggerRef = useRef<HTMLButtonElement | null>(null);
  const editTriggerRef = useRef<HTMLButtonElement | null>(null);
  const deleteTriggerRef = useRef<HTMLButtonElement | null>(null);

  // Search debounce
  useEffect(() => {
    const handler = setTimeout(() => {
      setDebouncedSearch(searchQuery.trim());
      setPage(1);
    }, 300);
    return () => clearTimeout(handler);
  }, [searchQuery]);

  // Load packaging items for target label resolution
  const fetchPackagingContext = useCallback(async () => {
    try {
      const [prodsRes, modsRes, capsRes] = await Promise.all([
        plansApi.listProducts(versionId, { page_size: 100 }),
        plansApi.listModules(versionId, { page_size: 100 }),
        plansApi.listCapabilities(versionId, { page_size: 100 }),
      ]);

      const pMap: Record<string, PlanProductListItem> = {};
      for (const p of prodsRes.results) {
        pMap[p.id] = p;
      }
      setProductsMap(pMap);

      const mMap: Record<string, PlanModuleListItem> = {};
      for (const m of modsRes.results) {
        mMap[m.id] = m;
      }
      setModulesMap(mMap);

      const cMap: Record<string, PlanCapabilityListItem> = {};
      for (const c of capsRes.results) {
        cMap[c.id] = c;
      }
      setCapabilitiesMap(cMap);
    } catch {
      // Packaging context failure is non-blocking for list rendering
    }
  }, [versionId]);

  // Fetch paginated quotas
  const fetchQuotas = useCallback(async () => {
    try {
      setIsLoading(true);
      setError(null);

      const params: PlanQuotaListParams = {
        page,
        page_size: pageSize,
        ordering,
        ...(scopeFilter !== "all" ? { scope: scopeFilter } : {}),
        ...(debouncedSearch ? { search: debouncedSearch } : {}),
      };

      const res = await plansApi.listQuotas(versionId, params);
      setQuotas(res.results);
      setTotalCount(res.count);
      if (onQuotasCountChange) {
        onQuotasCountChange(res.count);
      }
    } catch {
      setError("Failed to load quotas for this version. Please check your network and retry.");
    } finally {
      setIsLoading(false);
    }
  }, [versionId, page, pageSize, ordering, scopeFilter, debouncedSearch, onQuotasCountChange]);

  // Initial load and refresh coordinator
  useEffect(() => {
    fetchQuotas();
    fetchPackagingContext();
  }, [fetchQuotas, fetchPackagingContext, refreshTrigger]);

  const handleMutationSuccess = () => {
    fetchQuotas();
    fetchPackagingContext();
    onMutated();
  };

  const resolveTargetLabel = useCallback(
    (quota: PlanQuotaListItem): string => {
      if (quota.scope === "plan") {
        return `Version ${versionNumber} (Global)`;
      }
      if (!quota.target_id) {
        return "Unassigned Target";
      }
      if (quota.scope === "product") {
        const prod = productsMap[quota.target_id];
        return prod ? `${prod.product_code} — ${prod.product_name}` : `Product ${quota.target_id.slice(0, 8)}...`;
      }
      if (quota.scope === "module") {
        const mod = modulesMap[quota.target_id];
        return mod ? `${mod.module_code} (${mod.module_name})` : `Module ${quota.target_id.slice(0, 8)}...`;
      }
      if (quota.scope === "capability") {
        const cap = capabilitiesMap[quota.target_id];
        return cap
          ? `${cap.capability_code} — ${cap.capability_name}`
          : `Capability ${quota.target_id.slice(0, 8)}...`;
      }
      return quota.target_id;
    },
    [versionNumber, productsMap, modulesMap, capabilitiesMap]
  );

  const totalPages = Math.ceil(totalCount / pageSize);

  return (
    <div className="commercial-section-container" style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>
      {/* Section Header */}
      <div className="section-header-row" style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: "1rem" }}>
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
            <h3 className="section-title" style={{ margin: 0, fontSize: "1.25rem" }}>
              Commercial Quotas
            </h3>
            <span className="badge badge-neutral">{totalCount} {totalCount === 1 ? "Quota" : "Quotas"}</span>
          </div>
          <p className="text-body" style={{ fontSize: "0.875rem", margin: "0.25rem 0 0" }}>
            Usage limits, volume allowances, and rate ceilings enforced across plan, product, module, and capability scopes.
          </p>
        </div>

        {isDraft ? (
          <button
            ref={createTriggerRef}
            type="button"
            className="btn btn-primary"
            onClick={() => setIsCreateOpen(true)}
            style={{ flexShrink: 0 }}
          >
            <PlusIcon size={16} />
            Add Quota
          </button>
        ) : (
          <span className="badge badge-neutral" style={{ padding: "0.45rem 0.75rem", fontStyle: "italic" }}>
            Quotas are read-only ({versionStatus})
          </span>
        )}
      </div>

      {/* Filter and Sorting Toolbar */}
      <div className="registry-controls-bar" style={{ display: "flex", flexWrap: "wrap", gap: "0.75rem", alignItems: "center" }}>
        {/* Search */}
        <div className="search-input-wrapper" style={{ minWidth: "220px", flex: "1 1 220px" }}>
          <span className="search-icon-adornment" aria-hidden="true">
            <SearchIcon size={16} />
          </span>
          <input
            type="search"
            className="registry-search-input"
            placeholder="Search key or name..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            aria-label="Search quotas"
          />
        </div>

        {/* Scope Filter */}
        <div className="status-filter-wrapper">
          <span className="filter-icon-adornment" aria-hidden="true">
            <FilterIcon size={15} />
          </span>
          <select
            className="registry-filter-select"
            value={scopeFilter}
            onChange={(e) => {
              setScopeFilter(e.target.value as PlanQuotaScope | "all");
              setPage(1);
            }}
            aria-label="Filter by quota scope"
          >
            <option value="all">Scope: All</option>
            {SUPPORTED_SCOPES.map((s) => (
              <option key={s.value} value={s.value}>
                {s.label}
              </option>
            ))}
          </select>
          <span className="filter-chevron-adornment" aria-hidden="true">
            <ChevronDownIcon size={15} />
          </span>
        </div>

        {/* Ordering */}
        <div className="status-filter-wrapper" style={{ marginLeft: "auto" }}>
          <select
            className="registry-filter-select"
            value={ordering}
            onChange={(e) => {
              setOrdering(e.target.value as "scope" | "quota_key" | "name");
              setPage(1);
            }}
            aria-label="Sort quotas"
          >
            <option value="scope">Sort: Scope</option>
            <option value="quota_key">Sort: Quota Key</option>
            <option value="name">Sort: Name</option>
          </select>
          <span className="filter-chevron-adornment" aria-hidden="true">
            <ChevronDownIcon size={15} />
          </span>
        </div>
      </div>

      {/* Error State */}
      {error && (
        <div className="alert-banner alert-banner-error" role="alert" style={{ marginBottom: "1rem" }}>
          <span>{error}</span>
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            onClick={fetchQuotas}
            style={{ marginLeft: "auto" }}
          >
            Retry
          </button>
        </div>
      )}

      {/* Loading Skeleton */}
      {isLoading && (
        <div className="registry-skeleton-container" aria-label="Loading quotas">
          <div className="skeleton-row" />
          <div className="skeleton-row" />
          <div className="skeleton-row" />
        </div>
      )}

      {/* Empty State */}
      {!isLoading && !error && quotas.length === 0 && (
        <div className="empty-state" style={{ padding: "2.5rem 1rem", textAlign: "center" }}>
          <p className="text-body" style={{ fontWeight: 500 }}>
            {debouncedSearch || scopeFilter !== "all"
              ? "No quotas match your filter criteria."
              : "No usage quotas configured for this version."}
          </p>
          <p className="text-caption" style={{ color: "var(--text-muted)", margin: "0.25rem 0 1rem" }}>
            {isDraft
              ? "Define usage limits at the Plan, Product, Module, or Capability level."
              : "This version does not have any quotas defined."}
          </p>
          {isDraft && !debouncedSearch && scopeFilter === "all" && (
            <button
              type="button"
              className="btn btn-primary btn-sm"
              onClick={() => setIsCreateOpen(true)}
            >
              <PlusIcon size={14} />
              Add First Quota
            </button>
          )}
        </div>
      )}

      {/* Quotas Desktop Table & Mobile Cards */}
      {!isLoading && !error && quotas.length > 0 && (
        <>
          {/* Desktop & Tablet Table (>=768px) */}
          <div className="desktop-tablet-view">
            <div className="table-responsive quota-table-container">
              <table className="table" aria-label="Plan quotas table">
                <thead>
                  <tr>
                    <th scope="col">Quota Key</th>
                    <th scope="col">Name</th>
                    <th scope="col">Scope</th>
                    <th scope="col">Target</th>
                    <th scope="col">Limit</th>
                    <th scope="col">Policy</th>
                    <th scope="col">Reset</th>
                    <th scope="col">Created At</th>
                    <th scope="col">Updated</th>
                    <th scope="col" style={{ textAlign: "right" }}>
                      Actions
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {quotas.map((q) => {
                    const targetLabel = resolveTargetLabel(q);
                    const isUnlimited = q.limit_type === "unlimited";

                    return (
                      <tr key={q.id}>
                        {/* Quota Key */}
                        <td>
                          <span className="product-code-pill" style={{ fontSize: "0.8125rem" }}>
                            {q.quota_key}
                          </span>
                        </td>

                        {/* Display Name */}
                        <td>
                          <span style={{ fontWeight: 500 }}>{q.name}</span>
                        </td>

                        {/* Scope */}
                        <td>
                          <span className="badge badge-neutral" style={{ textTransform: "capitalize" }}>
                            {q.scope}
                          </span>
                        </td>

                        {/* Target Label */}
                        <td>
                          <span
                            className="text-body text-truncate"
                            style={{ maxWidth: "220px", display: "inline-block", fontSize: "0.875rem" }}
                            title={targetLabel}
                          >
                            {targetLabel}
                          </span>
                        </td>

                        {/* Limit Value & Unit */}
                        <td>
                          {isUnlimited ? (
                            <span className="badge badge-quota-unlimited">Unlimited</span>
                          ) : (
                            <span className="badge badge-quota-numeric">
                              {q.limit_value} <span style={{ opacity: 0.8 }}>{q.unit}</span>
                            </span>
                          )}
                        </td>

                        {/* Policy: Hard vs Soft */}
                        <td>
                          <span
                            className={`badge ${q.is_hard_limit ? "badge-quota-hard" : "badge-quota-soft"}`}
                          >
                            {q.is_hard_limit ? "Hard Limit" : "Soft Limit"}
                          </span>
                        </td>

                        {/* Reset Period */}
                        <td>
                          <span className="badge badge-neutral" style={{ textTransform: "capitalize" }}>
                            {q.reset_period}
                          </span>
                        </td>

                        {/* Created At */}
                        <td className="text-caption" style={{ color: "var(--text-muted)" }} title={q.created_at}>
                          {formatDateTime(q.created_at)}
                        </td>

                        {/* Updated At */}
                        <td className="text-caption" style={{ color: "var(--text-muted)" }} title={q.updated_at}>
                          {formatDateTime(q.updated_at)}
                        </td>

                        {/* Actions */}
                        <td style={{ textAlign: "right", whiteSpace: "nowrap" }}>
                          {isDraft ? (
                            <div style={{ display: "inline-flex", gap: "0.375rem" }}>
                              <button
                                ref={editingQuota?.id === q.id ? editTriggerRef : undefined}
                                type="button"
                                className="btn btn-secondary btn-icon btn-sm"
                                onClick={(e) => {
                                  editTriggerRef.current = e.currentTarget;
                                  setEditingQuota(q);
                                }}
                                title={`Edit quota ${q.name}`}
                                aria-label={`Edit quota ${q.name}`}
                              >
                                <EditIcon size={14} />
                              </button>
                              <button
                                ref={deletingQuota?.id === q.id ? deleteTriggerRef : undefined}
                                type="button"
                                className="btn btn-danger-action btn-icon btn-sm"
                                onClick={(e) => {
                                  deleteTriggerRef.current = e.currentTarget;
                                  setDeletingQuota(q);
                                }}
                                title={`Remove quota ${q.name}`}
                                aria-label={`Remove quota ${q.name}`}
                              >
                                <TrashIcon size={14} />
                              </button>
                            </div>
                          ) : (
                            <span
                              className="text-caption"
                              style={{ color: "var(--text-muted)", fontStyle: "italic" }}
                            >
                              Frozen
                            </span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>

          {/* Mobile Card View (<768px down to 320px) */}
          <div className="mobile-card-list">
            {quotas.map((q) => {
              const targetLabel = resolveTargetLabel(q);
              const isUnlimited = q.limit_type === "unlimited";

              return (
                <div key={q.id} className="mobile-product-card">
                  <div className="mobile-card-header">
                    <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", flexWrap: "wrap" }}>
                      <span className="product-code-pill" style={{ fontSize: "0.8125rem" }}>
                        {q.quota_key}
                      </span>
                      <span style={{ fontWeight: 600, fontSize: "0.9375rem" }}>{q.name}</span>
                    </div>
                    <span className="badge badge-neutral" style={{ textTransform: "capitalize" }}>
                      {q.scope}
                    </span>
                  </div>

                  <div className="mobile-card-body">
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: "0.5rem" }}>
                      <span className="text-caption" style={{ color: "var(--text-muted)" }}>Target:</span>
                      <span className="text-body" style={{ fontWeight: 500, textAlign: "right" }} title={targetLabel}>
                        {targetLabel}
                      </span>
                    </div>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: "0.5rem" }}>
                      <span className="text-caption" style={{ color: "var(--text-muted)" }}>Limit:</span>
                      {isUnlimited ? (
                        <span className="badge badge-quota-unlimited">Unlimited</span>
                      ) : (
                        <span className="badge badge-quota-numeric">
                          {q.limit_value} <span style={{ opacity: 0.8 }}>{q.unit}</span>
                        </span>
                      )}
                    </div>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: "0.5rem" }}>
                      <span className="text-caption" style={{ color: "var(--text-muted)" }}>Policy &amp; Reset:</span>
                      <div style={{ display: "inline-flex", gap: "0.375rem", alignItems: "center" }}>
                        <span className={`badge ${q.is_hard_limit ? "badge-quota-hard" : "badge-quota-soft"}`}>
                          {q.is_hard_limit ? "Hard Limit" : "Soft Limit"}
                        </span>
                        <span className="badge badge-neutral" style={{ textTransform: "capitalize" }}>
                          {q.reset_period}
                        </span>
                      </div>
                    </div>
                  </div>

                  <div className="mobile-card-footer">
                    <span className="text-caption" style={{ color: "var(--text-muted)" }} title={q.updated_at}>
                      Updated {formatDateTime(q.updated_at)}
                    </span>
                    {isDraft ? (
                      <div style={{ display: "inline-flex", gap: "0.375rem" }}>
                        <button
                          ref={editingQuota?.id === q.id ? editTriggerRef : undefined}
                          type="button"
                          className="btn btn-secondary btn-icon btn-sm"
                          onClick={(e) => {
                            editTriggerRef.current = e.currentTarget;
                            setEditingQuota(q);
                          }}
                          title={`Edit quota ${q.name}`}
                          aria-label={`Edit quota ${q.name}`}
                        >
                          <EditIcon size={14} />
                        </button>
                        <button
                          ref={deletingQuota?.id === q.id ? deleteTriggerRef : undefined}
                          type="button"
                          className="btn btn-danger-action btn-icon btn-sm"
                          onClick={(e) => {
                            deleteTriggerRef.current = e.currentTarget;
                            setDeletingQuota(q);
                          }}
                          title={`Remove quota ${q.name}`}
                          aria-label={`Remove quota ${q.name}`}
                        >
                          <TrashIcon size={14} />
                        </button>
                      </div>
                    ) : (
                      <span className="text-caption" style={{ color: "var(--text-muted)", fontStyle: "italic" }}>
                        Frozen
                      </span>
                    )}
                  </div>
                </div>
              );
            })}
          </div>

          {/* Pagination Controls */}
          {totalPages > 1 && (
            <div
              className="pagination-controls"
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                marginTop: "1rem",
                padding: "0.5rem 0",
              }}
            >
              <span className="text-caption" style={{ color: "var(--text-muted)" }}>
                Showing {(page - 1) * pageSize + 1}–{Math.min(page * pageSize, totalCount)} of {totalCount} quotas
              </span>
              <div style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
                <button
                  type="button"
                  className="btn btn-secondary btn-sm"
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  disabled={page <= 1}
                  aria-label="Previous page"
                >
                  <ChevronLeftIcon size={14} />
                  Prev
                </button>
                <span className="text-caption" style={{ fontWeight: 500 }}>
                  Page {page} of {totalPages}
                </span>
                <button
                  type="button"
                  className="btn btn-secondary btn-sm"
                  onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                  disabled={page >= totalPages}
                  aria-label="Next page"
                >
                  Next
                  <ChevronRightIcon size={14} />
                </button>
              </div>
            </div>
          )}
        </>
      )}

      {/* Modals */}
      <CreatePlanQuotaDialog
        isOpen={isCreateOpen}
        versionId={versionId}
        versionNumber={versionNumber}
        triggerRef={createTriggerRef}
        onClose={() => setIsCreateOpen(false)}
        onSuccess={() => {
          setIsCreateOpen(false);
          handleMutationSuccess();
        }}
      />

      <EditPlanQuotaDialog
        isOpen={editingQuota !== null}
        quota={editingQuota}
        resolvedTargetLabel={editingQuota ? resolveTargetLabel(editingQuota) : ""}
        triggerRef={editTriggerRef}
        onClose={() => setEditingQuota(null)}
        onSuccess={() => {
          setEditingQuota(null);
          handleMutationSuccess();
        }}
      />

      <DeletePlanQuotaDialog
        isOpen={deletingQuota !== null}
        quota={deletingQuota}
        resolvedTargetLabel={deletingQuota ? resolveTargetLabel(deletingQuota) : ""}
        triggerRef={deleteTriggerRef}
        onClose={() => setDeletingQuota(null)}
        onSuccess={() => {
          setDeletingQuota(null);
          handleMutationSuccess();
        }}
      />
    </div>
  );
};
