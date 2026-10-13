/**
 * Plan Pricing Management Section.
 *
 * Provides a production-grade commercial pricing workspace for a PlanVersion:
 * - Server-paginated price table with currency/interval filters
 * - Exact string preservation for price amounts (zero parseFloat / Number conversion)
 * - Draft-only mutations (Create, Edit amount, Delete with cascade/readiness warning)
 * - Read-only freeze for Active and Retired versions
 * - Responsive desktop table and mobile/tablet cards
 */

import React, { useCallback, useEffect, useRef, useState } from "react";
import { formatCurrencyDisplay, plansApi } from "../../api/plans.ts";
import type {
  PlanBillingInterval,
  PlanCurrency,
  PlanPriceListItem,
  PlanPriceListParams,
  PlanVersionStatus,
} from "../../api/types.ts";
import {
  ChevronDownIcon,
  ChevronLeftIcon,
  ChevronRightIcon,
  EditIcon,
  FilterIcon,
  PlusIcon,
  TrashIcon,
} from "../Icons.tsx";
import {
  CreatePlanPriceDialog,
  DeletePlanPriceDialog,
  EditPlanPriceDialog,
} from "./PlanPriceDialogs.tsx";

interface PlanPricingSectionProps {
  readonly versionId: string;
  readonly versionStatus: PlanVersionStatus;
  readonly versionNumber: number;
  readonly onMutated: () => void;
}

export const PlanPricingSection: React.FC<PlanPricingSectionProps> = ({
  versionId,
  versionStatus,
  versionNumber,
  onMutated,
}) => {
  const isDraft = versionStatus === "draft";

  const [prices, setPrices] = useState<readonly PlanPriceListItem[]>([]);
  const [totalCount, setTotalCount] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize] = useState(20);
  const [currencyFilter, setCurrencyFilter] = useState<PlanCurrency | "all">("all");
  const [intervalFilter, setIntervalFilter] = useState<PlanBillingInterval | "all">("all");
  const [ordering, setOrdering] = useState<"currency" | "billing_interval" | "amount" | "-amount">("currency");
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Dialog state
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [editingPrice, setEditingPrice] = useState<PlanPriceListItem | null>(null);
  const [deletingPrice, setDeletingPrice] = useState<PlanPriceListItem | null>(null);

  const createTriggerRef = useRef<HTMLButtonElement | null>(null);
  const editTriggerRef = useRef<HTMLButtonElement | null>(null);
  const deleteTriggerRef = useRef<HTMLButtonElement | null>(null);

  const fetchPrices = useCallback(async () => {
    try {
      setIsLoading(true);
      setError(null);
      const params: PlanPriceListParams = {
        page,
        page_size: pageSize,
        ordering,
        ...(currencyFilter !== "all" ? { currency: currencyFilter } : {}),
        ...(intervalFilter !== "all" ? { billing_interval: intervalFilter } : {}),
      };

      const res = await plansApi.listPrices(versionId, params);
      setPrices(res.results);
      setTotalCount(res.count);
    } catch {
      setError("Failed to load pricing for this version. Please check your network and retry.");
    } finally {
      setIsLoading(false);
    }
  }, [versionId, page, pageSize, currencyFilter, intervalFilter, ordering]);

  useEffect(() => {
    fetchPrices();
  }, [fetchPrices]);

  const handleMutationSuccess = () => {
    fetchPrices();
    onMutated();
  };

  const formatDate = (iso: string) => {
    try {
      return new Date(iso).toLocaleDateString(undefined, {
        year: "numeric",
        month: "short",
        day: "numeric",
      });
    } catch {
      return iso;
    }
  };

  const totalPages = Math.max(1, Math.ceil(totalCount / pageSize));

  return (
    <div className="pricing-workspace-section" style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>
      {/* Section Header */}
      <div className="section-header-row" style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: "1rem" }}>
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
            <h3 className="section-title" style={{ margin: 0, fontSize: "1.25rem" }}>
              Commercial Pricing
            </h3>
            <span className="badge badge-neutral">{totalCount} {totalCount === 1 ? "Price" : "Prices"}</span>
          </div>
          <p className="text-body" style={{ fontSize: "0.875rem", margin: "0.25rem 0 0" }}>
            Recurring commercial rates per currency and billing cycle. Exactly one rate allowed per currency/interval pair.
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
            Add Price
          </button>
        ) : (
          <span className="badge badge-neutral" style={{ padding: "0.45rem 0.75rem", fontStyle: "italic" }}>
            Pricing is read-only ({versionStatus})
          </span>
        )}
      </div>

      {/* Filter and Sorting Toolbar */}
      <div className="registry-controls-bar" style={{ display: "flex", flexWrap: "wrap", gap: "0.75rem" }}>
        {/* Currency Filter */}
        <div className="status-filter-wrapper">
          <span className="filter-icon-adornment" aria-hidden="true">
            <FilterIcon size={15} />
          </span>
          <select
            className="registry-filter-select"
            value={currencyFilter}
            onChange={(e) => {
              setCurrencyFilter(e.target.value as PlanCurrency | "all");
              setPage(1);
            }}
            aria-label="Filter prices by currency"
          >
            <option value="all">Currency: All</option>
            <option value="USD">USD ($)</option>
            <option value="EUR">EUR (€)</option>
            <option value="GBP">GBP (£)</option>
            <option value="INR">INR (₹)</option>
          </select>
          <span className="filter-chevron-adornment" aria-hidden="true">
            <ChevronDownIcon size={15} />
          </span>
        </div>

        {/* Interval Filter */}
        <div className="status-filter-wrapper">
          <span className="filter-icon-adornment" aria-hidden="true">
            <FilterIcon size={15} />
          </span>
          <select
            className="registry-filter-select"
            value={intervalFilter}
            onChange={(e) => {
              setIntervalFilter(e.target.value as PlanBillingInterval | "all");
              setPage(1);
            }}
            aria-label="Filter prices by billing interval"
          >
            <option value="all">Interval: All</option>
            <option value="monthly">Monthly</option>
            <option value="quarterly">Quarterly</option>
            <option value="annual">Annual</option>
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
              setOrdering(e.target.value as "currency" | "billing_interval" | "amount" | "-amount");
              setPage(1);
            }}
            aria-label="Sort prices"
          >
            <option value="currency">Sort: Currency</option>
            <option value="billing_interval">Sort: Billing Interval</option>
            <option value="amount">Sort: Price (Lowest)</option>
            <option value="-amount">Sort: Price (Highest)</option>
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
            onClick={fetchPrices}
            style={{ marginLeft: "auto" }}
          >
            Retry
          </button>
        </div>
      )}

      {/* Loading Skeleton */}
      {isLoading && (
        <div className="registry-skeleton-container" aria-label="Loading prices">
          <div className="skeleton-row" />
          <div className="skeleton-row" />
        </div>
      )}

      {/* Empty State */}
      {!isLoading && !error && prices.length === 0 && (
        <div className="empty-state-container" style={{ padding: "3rem 1.5rem", textAlign: "center" }}>
          <div className="empty-state-icon" style={{ fontSize: "2rem", marginBottom: "0.75rem" }}>
            💳
          </div>
          <h4 className="empty-state-title" style={{ margin: 0 }}>
            No Prices Configured
          </h4>
          <p className="empty-state-desc" style={{ maxWidth: "460px", margin: "0.5rem auto 1.25rem" }}>
            {isDraft
              ? "This draft version has no pricing yet. Add at least one price to satisfy activation readiness."
              : "No commercial prices were configured for this plan version."}
          </p>
          {isDraft && (
            <button
              type="button"
              className="btn btn-primary"
              onClick={() => setIsCreateOpen(true)}
            >
              <PlusIcon size={16} />
              Add First Price
            </button>
          )}
        </div>
      )}

      {/* Data Table */}
      {!isLoading && !error && prices.length > 0 && (
        <div className="product-table-container">
          <div className="table-responsive">
            <table className="enterprise-table" aria-label="Plan Version Pricing">
              <thead>
                <tr>
                  <th scope="col" style={{ width: "16%" }}>Currency</th>
                  <th scope="col" style={{ width: "22%" }}>Billing Interval</th>
                  <th scope="col" style={{ width: "22%" }}>Exact Amount</th>
                  <th scope="col" style={{ width: "20%" }}>Configured On</th>
                  <th scope="col" style={{ width: "20%", textAlign: "right" }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {prices.map((p) => (
                  <tr key={p.id} className="table-row">
                    <td>
                      <span className="product-code-pill font-mono font-bold">
                        {p.currency}
                      </span>
                    </td>
                    <td>
                      <span style={{ textTransform: "capitalize", fontWeight: 500 }}>
                        {p.billing_interval}
                      </span>
                    </td>
                    <td>
                      <span className="price-amount-display font-mono" style={{ fontSize: "1.05rem", fontWeight: 600 }}>
                        {formatCurrencyDisplay(p.amount, p.currency)}
                      </span>
                    </td>
                    <td>
                      <span className="text-caption" style={{ color: "var(--color-text-muted)" }}>
                        {formatDate(p.created_at)}
                      </span>
                    </td>
                    <td style={{ textAlign: "right" }}>
                      {isDraft ? (
                        <div style={{ display: "inline-flex", gap: "0.5rem", justifyContent: "flex-end" }}>
                          <button
                            type="button"
                            className="btn btn-secondary btn-sm btn-icon"
                            onClick={(e) => {
                              editTriggerRef.current = e.currentTarget;
                              setEditingPrice(p);
                            }}
                            title="Edit amount"
                            aria-label={`Edit ${formatCurrencyDisplay(p.amount, p.currency)} price`}
                          >
                            <EditIcon size={14} />
                          </button>
                          <button
                            type="button"
                            className="btn btn-secondary btn-sm btn-icon text-danger"
                            onClick={(e) => {
                              deleteTriggerRef.current = e.currentTarget;
                              setDeletingPrice(p);
                            }}
                            title="Remove price"
                            aria-label={`Remove ${formatCurrencyDisplay(p.amount, p.currency)} price`}
                          >
                            <TrashIcon size={14} />
                          </button>
                        </div>
                      ) : (
                        <span className="text-caption" style={{ fontStyle: "italic", color: "var(--color-text-muted)" }}>
                          Locked
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Pagination Controls */}
          {totalPages > 1 && (
            <div
              className="table-pagination-bar"
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                padding: "0.75rem 1rem",
                borderTop: "1px solid var(--color-border)",
              }}
            >
              <span className="text-caption">
                Showing page {page} of {totalPages} ({totalCount} total)
              </span>
              <div style={{ display: "inline-flex", gap: "0.5rem" }}>
                <button
                  type="button"
                  className="btn btn-secondary btn-sm"
                  disabled={page <= 1}
                  onClick={() => setPage((prev) => Math.max(1, prev - 1))}
                  aria-label="Previous page"
                >
                  <ChevronLeftIcon size={14} />
                  Prev
                </button>
                <button
                  type="button"
                  className="btn btn-secondary btn-sm"
                  disabled={page >= totalPages}
                  onClick={() => setPage((prev) => Math.min(totalPages, prev + 1))}
                  aria-label="Next page"
                >
                  Next
                  <ChevronRightIcon size={14} />
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Dialogs */}
      <CreatePlanPriceDialog
        isOpen={isCreateOpen}
        onClose={() => setIsCreateOpen(false)}
        onSuccess={handleMutationSuccess}
        versionId={versionId}
        triggerRef={createTriggerRef}
      />

      <EditPlanPriceDialog
        isOpen={Boolean(editingPrice)}
        onClose={() => setEditingPrice(null)}
        onSuccess={handleMutationSuccess}
        price={editingPrice}
        triggerRef={editTriggerRef}
      />

      <DeletePlanPriceDialog
        isOpen={Boolean(deletingPrice)}
        onClose={() => setDeletingPrice(null)}
        onSuccess={handleMutationSuccess}
        price={deletingPrice}
        versionNumber={versionNumber}
        triggerRef={deleteTriggerRef}
      />
    </div>
  );
};
