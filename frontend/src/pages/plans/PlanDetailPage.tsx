/**
 * Plan Family Detail Page.
 *
 * Displays Plan presentation metadata, active version status, and
 * paginated Plan Versions list with lifecycle filtering and version creation.
 */

import React, { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { plansApi } from "../../api/plans.ts";
import type {
  PlanDetail,
  PlanVersionDetail,
  PlanVersionListItem,
  PlanVersionListParams,
} from "../../api/types.ts";
import { AppShell } from "../../components/AppShell.tsx";
import { CatalogHierarchyNav } from "../../components/catalog/CatalogHierarchyNav.tsx";
import {
  AlertCircleIcon,
  CheckCircleIcon,
  ChevronDownIcon,
  CloseIcon,
  EditIcon,
  FilterIcon,
  GlobeIcon,
  LayersIcon,
  PlusIcon,
} from "../../components/Icons.tsx";
import { CreatePlanVersionDialog, EditPlanDialog } from "../../components/plans/PlanDialogs.tsx";
import { CatalogHealthBadge, PlanVersionStatusBadge } from "../../components/plans/PlanStatusBadge.tsx";
import { parseApiErrors } from "../../components/plans/PlanModalShell.tsx";

export const PlanDetailPage: React.FC = () => {
  const { planId } = useParams<{ planId: string }>();
  const navigate = useNavigate();

  const [plan, setPlan] = useState<PlanDetail | null>(null);
  const [isPlanLoading, setIsPlanLoading] = useState<boolean>(true);
  const [planError, setPlanError] = useState<string | null>(null);

  // Visibility state
  const [isTogglingPublic, setIsTogglingPublic] = useState<boolean>(false);
  const [visibilityFeedback, setVisibilityFeedback] = useState<{
    type: "success" | "error";
    message: string;
  } | null>(null);

  // Versions List State
  const [versions, setVersions] = useState<PlanVersionListItem[]>([]);
  const [totalVersions, setTotalVersions] = useState<number>(0);
  const [versionPage, setVersionPage] = useState<number>(1);
  const pageSize = 10;

  const [statusFilter, setStatusFilter] = useState<string>("");
  const [ordering, setOrdering] = useState<string>("-version");
  const [isVersionsLoading, setIsVersionsLoading] = useState<boolean>(true);
  const [versionsError, setVersionsError] = useState<string | null>(null);

  // Dialog states
  const [isEditPlanOpen, setIsEditPlanOpen] = useState(false);
  const [isCreateVersionOpen, setIsCreateVersionOpen] = useState(false);
  const triggerRef = useRef<HTMLElement | null>(null);

  const fetchPlanDetail = useCallback(async () => {
    if (!planId) return;
    setIsPlanLoading(true);
    setPlanError(null);

    try {
      const data = await plansApi.get(planId);
      setPlan(data);
      setIsPlanLoading(false);
    } catch {
      setIsPlanLoading(false);
      setPlanError("Unable to load plan details. The plan may not exist or network failed.");
    }
  }, [planId]);

  const handleTogglePublic = async () => {
    if (!plan) return;
    setIsTogglingPublic(true);
    setVisibilityFeedback(null);
    const targetState = !plan.is_public;

    try {
      const updated = await plansApi.update(plan.id, { is_public: targetState });
      setPlan(updated);
      setVisibilityFeedback({
        type: "success",
        message: targetState
          ? "Plan is now visible in the public discovery catalog."
          : "Plan is now private (internal control plane only).",
      });
    } catch (err: unknown) {
      const { generalError, fieldErrors } = parseApiErrors(err);
      const msg =
        fieldErrors.is_public ||
        generalError ||
        (targetState
          ? "Cannot make plan public. Ensure the plan has an active healthy version with configured pricing and packaged products."
          : "Failed to update plan visibility.");
      setVisibilityFeedback({ type: "error", message: msg });
    } finally {
      setIsTogglingPublic(false);
    }
  };

  const fetchVersions = useCallback(async () => {
    if (!planId) return;
    setIsVersionsLoading(true);
    setVersionsError(null);

    try {
      const params: PlanVersionListParams = {
        page: versionPage,
        page_size: pageSize,
        status: statusFilter || undefined,
        ordering: ordering || undefined,
      };
      const data = await plansApi.listVersions(planId, params);
      setVersions(data.results as PlanVersionListItem[]);
      setTotalVersions(data.count);
      setIsVersionsLoading(false);
    } catch {
      setIsVersionsLoading(false);
      setVersionsError("Unable to load plan versions.");
    }
  }, [planId, versionPage, pageSize, statusFilter, ordering]);

  useEffect(() => {
    fetchPlanDetail();
  }, [fetchPlanDetail]);

  useEffect(() => {
    fetchVersions();
  }, [fetchVersions]);

  const handleEditPlanSuccess = (updated: PlanDetail) => {
    setPlan(updated);
    fetchPlanDetail();
  };

  const handleCreateVersionSuccess = (newVersion: PlanVersionDetail) => {
    fetchPlanDetail();
    fetchVersions();
    navigate(`/plan-versions/${newVersion.id}`);
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

  const totalVersionPages = Math.max(1, Math.ceil(totalVersions / pageSize));

  return (
    <AppShell>
      <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem", minWidth: 0 }}>
        {/* Bordered Hierarchy Navigation Context Strip */}
        <CatalogHierarchyNav
          items={[
            { label: "Plans & Pricing", path: "/plans" },
            {
              label: plan?.name || "Loading Plan...",
              code: plan?.code,
            },
          ]}
        />

        {/* Error State */}
        {planError && (
          <div className="alert-banner alert-banner-error" role="alert">
            <span>{planError}</span>
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              onClick={fetchPlanDetail}
              style={{ marginLeft: "auto" }}
            >
              Retry
            </button>
          </div>
        )}

        {/* Loading State */}
        {isPlanLoading && (
          <div className="registry-skeleton-container" aria-label="Loading plan details">
            <div className="skeleton-row" />
            <div className="skeleton-row" />
          </div>
        )}

        {/* Plan Family Summary Card */}
        {!isPlanLoading && plan && (
          <div className="plan-summary-card">
            {/* Inline Visibility Feedback Alert */}
            {visibilityFeedback && (
              <div
                className={`alert-box ${visibilityFeedback.type === "success" ? "alert-success" : "alert-danger"}`}
                style={{
                  marginBottom: "1rem",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  gap: "0.75rem",
                  padding: "0.625rem 0.875rem",
                  fontSize: "0.875rem",
                }}
                role="alert"
              >
                <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                  {visibilityFeedback.type === "success" ? (
                    <CheckCircleIcon size={16} style={{ flexShrink: 0 }} />
                  ) : (
                    <AlertCircleIcon size={16} style={{ flexShrink: 0 }} />
                  )}
                  <span>{visibilityFeedback.message}</span>
                </div>
                <button
                  type="button"
                  onClick={() => setVisibilityFeedback(null)}
                  style={{
                    background: "transparent",
                    border: "none",
                    color: "inherit",
                    cursor: "pointer",
                    padding: "2px",
                    display: "flex",
                    alignItems: "center",
                    opacity: 0.7,
                  }}
                  aria-label="Dismiss feedback"
                >
                  <CloseIcon size={14} />
                </button>
              </div>
            )}

            <div className="plan-summary-header" style={{ display: "flex", alignItems: "flex-start", gap: "1.25rem" }}>
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

              <div style={{ flex: 1 }}>
                <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", flexWrap: "wrap" }}>
                  <span className="product-code-pill" style={{ fontSize: "0.9375rem" }}>
                    {plan.code}
                  </span>
                  <h1 className="heading-hero" style={{ fontSize: "1.625rem", margin: 0, fontWeight: 800, letterSpacing: "-0.02em" }}>
                    {plan.name}
                  </h1>
                  <CatalogHealthBadge health={plan.catalog_health} />

                  {/* Public / Private Visibility Badge */}
                  {plan.is_public ? (
                    <span
                      className="status-badge badge-success"
                      style={{ display: "inline-flex", alignItems: "center", gap: "0.3rem" }}
                    >
                      <GlobeIcon size={13} />
                      <span>Public Discovery</span>
                    </span>
                  ) : (
                    <span
                      className="status-badge badge-neutral"
                      style={{ display: "inline-flex", alignItems: "center", gap: "0.3rem" }}
                    >
                      <span>Private (Internal)</span>
                    </span>
                  )}
                </div>
                {plan.description && (
                  <p className="text-body" style={{ marginTop: "0.5rem", fontSize: "0.875rem", maxWidth: "760px", color: "var(--text-secondary)" }}>
                    {plan.description}
                  </p>
                )}
              </div>

              <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", flexWrap: "wrap" }}>
                {/* Public Visibility Controlled Action Button */}
                <button
                  type="button"
                  className={`btn ${plan.is_public ? "btn-secondary" : "btn-gradient"} btn-sm`}
                  onClick={handleTogglePublic}
                  disabled={isTogglingPublic}
                  title={
                    plan.is_public
                      ? "Make plan private (removes from public discovery catalog)"
                      : "Make plan public (exposes in public discovery catalog; requires active healthy version)"
                  }
                  aria-label={plan.is_public ? "Make plan private" : "Make plan public"}
                >
                  <GlobeIcon size={14} />
                  <span>
                    {isTogglingPublic
                      ? "Updating..."
                      : plan.is_public
                      ? "Set to Private"
                      : "Publish to Catalog"}
                  </span>
                </button>

                <button
                  type="button"
                  className="btn btn-secondary btn-sm"
                  onClick={(e) => {
                    triggerRef.current = e.currentTarget;
                    setIsEditPlanOpen(true);
                  }}
                  aria-label={`Edit ${plan.name} presentation metadata`}
                  style={{ flexShrink: 0 }}
                >
                  <EditIcon size={14} />
                  Edit Plan
                </button>
              </div>
            </div>

            {/* Public Visibility Advisory Notice */}
            <div
              style={{
                fontSize: "0.75rem",
                color: "var(--text-muted)",
                background: "var(--glass-surface)",
                border: "1px solid var(--border-subtle)",
                borderRadius: "8px",
                padding: "0.4rem 0.75rem",
              }}
            >
              Public visibility allows prospective tenants to discover this plan via the public API. Only plans with an eligible, active, and healthy version with prices and packaged products can be made public.
            </div>

            {/* Key Metadata Row */}
            <div className="plan-meta-grid">
              <div className="plan-meta-item">
                <span className="meta-label">Active Version</span>
                <div style={{ marginTop: "0.25rem" }}>
                  {plan.active_version ? (
                    <div style={{ display: "inline-flex", alignItems: "center", gap: "0.4rem" }}>
                      <span className="product-code-pill">v{plan.active_version.version}</span>
                      <PlanVersionStatusBadge status={plan.active_version.status} />
                    </div>
                  ) : (
                    <span className="text-caption" style={{ fontStyle: "italic" }}>None (Draft Only)</span>
                  )}
                </div>
              </div>

              <div className="plan-meta-item">
                <span className="meta-label">Latest Version</span>
                <div style={{ marginTop: "0.25rem" }}>
                  {plan.latest_version ? (
                    <span className="product-code-pill">v{plan.latest_version.version} ({plan.latest_version.status})</span>
                  ) : (
                    "—"
                  )}
                </div>
              </div>

              <div className="plan-meta-item">
                <span className="meta-label">Total Versions</span>
                <span className="meta-value">{plan.total_versions_count}</span>
              </div>

              <div className="plan-meta-item">
                <span className="meta-label">Last Updated</span>
                <span className="meta-value">{formatDate(plan.updated_at)}</span>
              </div>
            </div>
          </div>
        )}

        {/* Plan Versions Section */}
        <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "0.75rem" }}>
            <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
              <h2 className="heading-section" style={{ margin: 0, fontSize: "1.25rem" }}>
                Plan Versions
              </h2>
              {!isVersionsLoading && (
                <span className="registry-count-badge">
                  {totalVersions} {totalVersions === 1 ? "Version" : "Versions"}
                </span>
              )}
            </div>

            {plan && (
              <button
                type="button"
                className="btn btn-gradient btn-sm"
                onClick={(e) => {
                  triggerRef.current = e.currentTarget;
                  setIsCreateVersionOpen(true);
                }}
              >
                <PlusIcon size={15} />
                Create Draft Version
              </button>
            )}
          </div>

          {/* Versions Controls Bar */}
          <div className="registry-controls-bar" style={{ flexWrap: "wrap", gap: "0.75rem" }}>
            <div className="status-filter-wrapper">
              <span className="filter-icon-adornment" aria-hidden="true">
                <FilterIcon size={15} />
              </span>
              <select
                className="registry-filter-select"
                value={statusFilter}
                onChange={(e) => {
                  setStatusFilter(e.target.value);
                  setVersionPage(1);
                }}
                aria-label="Filter versions by status"
              >
                <option value="">All Statuses</option>
                <option value="draft">Draft</option>
                <option value="active">Active</option>
                <option value="retired">Retired</option>
              </select>
              <span className="filter-chevron-adornment" aria-hidden="true">
                <ChevronDownIcon size={15} />
              </span>
            </div>

            <div className="status-filter-wrapper">
              <select
                className="registry-filter-select"
                value={ordering}
                onChange={(e) => {
                  setOrdering(e.target.value);
                  setVersionPage(1);
                }}
                aria-label="Sort versions order"
              >
                <option value="-version">Highest Version First</option>
                <option value="version">Lowest Version First</option>
                <option value="-created_at">Newest Created</option>
                <option value="created_at">Oldest Created</option>
              </select>
              <span className="filter-chevron-adornment" aria-hidden="true">
                <ChevronDownIcon size={15} />
              </span>
            </div>
          </div>

          {/* Versions Error Alert */}
          {versionsError && (
            <div className="alert-banner alert-banner-error" role="alert">
              <span>{versionsError}</span>
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                onClick={fetchVersions}
                style={{ marginLeft: "auto" }}
              >
                Retry
              </button>
            </div>
          )}

          {/* Loading Skeleton */}
          {isVersionsLoading && (
            <div className="registry-skeleton-container">
              <div className="skeleton-row" />
              <div className="skeleton-row" />
            </div>
          )}

          {/* Versions Table / Card List */}
          {!isVersionsLoading && !versionsError && (
            <>
              {versions.length > 0 ? (
                <>
                  <div className="product-table-container">
                    {/* Desktop & Tablet Table */}
                    <div className="table-responsive desktop-tablet-view">
                      <table className="enterprise-table" aria-label="Plan Versions">
                        <thead>
                          <tr>
                            <th scope="col" style={{ width: "12%" }}>Version</th>
                            <th scope="col" style={{ width: "14%" }}>Status</th>
                            <th scope="col" style={{ width: "32%" }}>Change Summary</th>
                            <th scope="col" style={{ width: "14%" }}>Catalog Health</th>
                            <th scope="col" style={{ width: "14%" }}>Updated</th>
                            <th scope="col" style={{ width: "14%", textAlign: "right" }}>Actions</th>
                          </tr>
                        </thead>
                        <tbody>
                          {versions.map((ver) => (
                            <tr key={ver.id} className="table-row">
                              <td>
                                <span className="product-code-pill">v{ver.version}</span>
                              </td>
                              <td>
                                <PlanVersionStatusBadge status={ver.status} />
                              </td>
                              <td>
                                <span className="product-name" style={{ fontWeight: 500 }}>
                                  {ver.change_summary || <span style={{ fontStyle: "italic", color: "var(--text-muted)" }}>No summary</span>}
                                </span>
                              </td>
                              <td>
                                <CatalogHealthBadge health={ver.catalog_health} />
                              </td>
                              <td>
                                <span className="text-caption">{formatDate(ver.updated_at)}</span>
                              </td>
                              <td style={{ textAlign: "right" }}>
                                <button
                                  type="button"
                                  className="btn btn-primary btn-sm"
                                  onClick={() => navigate(`/plan-versions/${ver.id}`)}
                                  aria-label={`View Version ${ver.version}`}
                                >
                                  View Version
                                </button>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>

                    {/* Mobile Card List View (<768px) */}
                    <div className="mobile-card-list">
                      {versions.map((ver) => (
                        <div key={ver.id} className="mobile-product-card">
                          <div className="mobile-card-header">
                            <span className="product-code-pill">Version {ver.version}</span>
                            <PlanVersionStatusBadge status={ver.status} />
                          </div>
                          <div className="mobile-card-body">
                            <p className="mobile-product-desc" style={{ color: "var(--text-primary)", fontWeight: 500 }}>
                              {ver.change_summary || "No summary provided."}
                            </p>
                            <div style={{ display: "flex", gap: "0.5rem", alignItems: "center", marginTop: "0.35rem" }}>
                              <span className="text-caption">Catalog Health:</span>
                              <CatalogHealthBadge health={ver.catalog_health} />
                            </div>
                          </div>
                          <div className="mobile-card-footer">
                            <span className="text-caption">Updated {formatDate(ver.updated_at)}</span>
                            <button
                              type="button"
                              className="btn btn-primary btn-sm"
                              onClick={() => navigate(`/plan-versions/${ver.id}`)}
                              aria-label={`View Version ${ver.version}`}
                              style={{ minHeight: "44px" }}
                            >
                              View Version
                            </button>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* Pagination Controls */}
                  {totalVersions > pageSize && (
                    <div className="pagination-bar">
                      <span className="text-caption">
                        Showing {(versionPage - 1) * pageSize + 1}–{Math.min(versionPage * pageSize, totalVersions)} of {totalVersions}
                      </span>
                      <div style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
                        <button
                          type="button"
                          className="btn btn-secondary btn-sm"
                          onClick={() => setVersionPage((p) => Math.max(p - 1, 1))}
                          disabled={versionPage <= 1}
                          aria-label="Previous page of versions"
                        >
                          Previous
                        </button>
                        <span className="pagination-page-indicator">
                          Page {versionPage} of {totalVersionPages}
                        </span>
                        <button
                          type="button"
                          className="btn btn-secondary btn-sm"
                          onClick={() => setVersionPage((p) => Math.min(p + 1, totalVersionPages))}
                          disabled={versionPage >= totalVersionPages}
                          aria-label="Next page of versions"
                        >
                          Next
                        </button>
                      </div>
                    </div>
                  )}
                </>
              ) : (
                <div className="registry-empty-card">
                  <div className="empty-icon-circle">
                    <LayersIcon size={24} />
                  </div>
                  <h3 className="empty-title">No versions found</h3>
                  <p className="empty-desc">
                    {statusFilter
                      ? `No versions match the selected status '${statusFilter}'.`
                      : "This plan has no allocated versions."}
                  </p>
                </div>
              )}
            </>
          )}
        </div>
      </div>

      {/* Dialogs */}
      <EditPlanDialog
        plan={plan}
        isOpen={isEditPlanOpen}
        onClose={() => setIsEditPlanOpen(false)}
        onSuccess={handleEditPlanSuccess}
        triggerRef={triggerRef}
      />

      {plan && (
        <CreatePlanVersionDialog
          planId={plan.id}
          planCode={plan.code}
          isOpen={isCreateVersionOpen}
          onClose={() => setIsCreateVersionOpen(false)}
          onSuccess={handleCreateVersionSuccess}
          triggerRef={triggerRef}
        />
      )}
    </AppShell>
  );
};
