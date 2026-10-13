/**
 * Plan Version Detail & Lifecycle Management Page.
 *
 * Provides Platform Owners with comprehensive lifecycle management for a specific version:
 * - Status-driven action controls (Draft: Edit, Clone, Activate, Retire; Active: Clone, Retire; Retired: Clone)
 * - Dynamic activation readiness card with blockers, warnings, and stale catalog items
 * - Read-only commercial configuration summary placeholder for Stage 1C-2
 * - Accessible modals with focus restoration
 */

import React, { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { plansApi } from "../../api/plans.ts";
import type {
  PlanDetail,
  PlanReadinessResponse,
  PlanVersionDetail,
} from "../../api/types.ts";
import { AppShell } from "../../components/AppShell.tsx";
import { formatDateTime } from "../../config/dateUtils.ts";
import { CatalogHierarchyNav } from "../../components/catalog/CatalogHierarchyNav.tsx";
import {
  CheckCircleIcon,
  CopyIcon,
  EditIcon,
  LayersIcon,
} from "../../components/Icons.tsx";
import {
  ActivatePlanVersionDialog,
  ClonePlanVersionDialog,
  EditPlanVersionDialog,
  RetirePlanVersionDialog,
} from "../../components/plans/PlanDialogs.tsx";
import { PlanReadinessCard } from "../../components/plans/PlanReadinessCard.tsx";
import { CatalogHealthBadge, PlanVersionStatusBadge } from "../../components/plans/PlanStatusBadge.tsx";
import { PlanPricingSection } from "../../components/plans/PlanPricingSection.tsx";
import { PlanPackagingSection } from "../../components/plans/PlanPackagingSection.tsx";
import { PlanQuotaSection } from "../../components/plans/PlanQuotaSection.tsx";

type CommercialTab = "overview" | "pricing" | "packaging" | "quotas";

export const PlanVersionDetailPage: React.FC = () => {
  const { versionId } = useParams<{ versionId: string }>();
  const navigate = useNavigate();

  const [version, setVersion] = useState<PlanVersionDetail | null>(null);
  const [parentPlan, setParentPlan] = useState<PlanDetail | null>(null);
  const [readiness, setReadiness] = useState<PlanReadinessResponse | null>(null);
  const [activeTab, setActiveTab] = useState<CommercialTab>("overview");
  const [quotasCount, setQuotasCount] = useState<number | null>(null);
  const [refreshCounter, setRefreshCounter] = useState<number>(0);

  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [isReadinessLoading, setIsReadinessLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // Dialog States
  const [isEditOpen, setIsEditOpen] = useState(false);
  const [isCloneOpen, setIsCloneOpen] = useState(false);
  const [isActivateOpen, setIsActivateOpen] = useState(false);
  const [isRetireOpen, setIsRetireOpen] = useState(false);
  const triggerRef = useRef<HTMLElement | null>(null);
  const tabsNavRef = useRef<HTMLDivElement | null>(null);

  const TAB_ORDER: CommercialTab[] = ["overview", "pricing", "packaging", "quotas"];

  const handleTabKeyDown = (e: React.KeyboardEvent) => {
    const currentIndex = TAB_ORDER.indexOf(activeTab);
    if (e.key === "ArrowRight") {
      e.preventDefault();
      const nextTab = TAB_ORDER[(currentIndex + 1) % TAB_ORDER.length];
      setActiveTab(nextTab);
      const nextBtn = tabsNavRef.current?.querySelector<HTMLButtonElement>(`#tab-${nextTab}`);
      nextBtn?.focus();
    } else if (e.key === "ArrowLeft") {
      e.preventDefault();
      const prevTab = TAB_ORDER[(currentIndex - 1 + TAB_ORDER.length) % TAB_ORDER.length];
      setActiveTab(prevTab);
      const prevBtn = tabsNavRef.current?.querySelector<HTMLButtonElement>(`#tab-${prevTab}`);
      prevBtn?.focus();
    }
  };

  useEffect(() => {
    if (tabsNavRef.current) {
      const activeBtn = tabsNavRef.current.querySelector<HTMLButtonElement>(".commercial-tab-btn.active");
      if (activeBtn) {
        activeBtn.scrollIntoView({ behavior: "smooth", block: "nearest", inline: "nearest" });
      }
    }
  }, [activeTab]);

  const fetchVersionDetail = useCallback(async () => {
    if (!versionId) return;
    setIsLoading(true);
    setError(null);

    try {
      const data = await plansApi.getVersion(versionId);
      setVersion(data);
      if (data.plan_id) {
        try {
          const planData = await plansApi.get(data.plan_id);
          setParentPlan(planData);
        } catch {
          // Non-critical parent plan fetch
        }
      }
      setIsLoading(false);
    } catch {
      setIsLoading(false);
      setError("Unable to load version details. The version may not exist or network failed.");
    }
  }, [versionId]);

  const fetchReadiness = useCallback(async () => {
    if (!versionId) return;
    setIsReadinessLoading(true);

    try {
      const data = await plansApi.getReadiness(versionId);
      setReadiness(data);
      setIsReadinessLoading(false);
    } catch {
      setIsReadinessLoading(false);
    }
  }, [versionId]);

  useEffect(() => {
    fetchVersionDetail();
    fetchReadiness();
  }, [fetchVersionDetail, fetchReadiness]);

  const handleEditSuccess = (updated: PlanVersionDetail) => {
    setVersion(updated);
    fetchVersionDetail();
  };

  const handleCloneSuccess = (cloned: PlanVersionDetail) => {
    navigate(`/plan-versions/${cloned.id}`);
  };

  const handleActivateSuccess = (activated: PlanVersionDetail) => {
    setVersion(activated);
    fetchVersionDetail();
    fetchReadiness();
  };

  const handleRetireSuccess = (retired: PlanVersionDetail) => {
    setVersion(retired);
    fetchVersionDetail();
    fetchReadiness();
  };

  const handleCommercialMutated = () => {
    setRefreshCounter((prev) => prev + 1);
    fetchReadiness();
    fetchVersionDetail();
  };

  const isDraft = version?.status === "draft";
  const isActive = version?.status === "active";
  const isRetired = version?.status === "retired";

  return (
    <AppShell>
      <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem", minWidth: 0 }}>
        {/* Bordered Hierarchy Navigation Context Strip */}
        <CatalogHierarchyNav
          items={[
            { label: "Plans & Pricing", path: "/plans" },
            {
              label: parentPlan?.name || "Plan",
              path: version ? `/plans/${version.plan_id}` : undefined,
              code: parentPlan?.code,
            },
            {
              label: version ? `Version ${version.version}` : "Version",
            },
          ]}
        />

        {/* Error Alert */}
        {error && (
          <div className="alert-banner alert-banner-error" role="alert">
            <span>{error}</span>
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              onClick={() => {
                fetchVersionDetail();
                fetchReadiness();
              }}
              style={{ marginLeft: "auto" }}
            >
              Retry
            </button>
          </div>
        )}

        {/* Loading Skeleton */}
        {isLoading && (
          <div className="registry-skeleton-container" aria-label="Loading version details">
            <div className="skeleton-row" />
            <div className="skeleton-row" />
            <div className="skeleton-row" />
          </div>
        )}

        {/* Version Summary Card & Actions */}
        {!isLoading && version && (
          <>
            <div className="plan-summary-card">
              <div className="plan-summary-header">
                <div>
                  <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", flexWrap: "wrap" }}>
                    <h1 className="heading-hero" style={{ fontSize: "1.5rem", margin: 0 }}>
                      Version {version.version}
                    </h1>
                    <PlanVersionStatusBadge status={version.status} />
                    <CatalogHealthBadge health={version.catalog_health} />
                  </div>

                  <p className="text-body" style={{ marginTop: "0.5rem", fontSize: "0.9375rem", fontWeight: 500 }}>
                    {version.change_summary || <span style={{ fontStyle: "italic", color: "var(--text-muted)" }}>No change summary provided.</span>}
                  </p>
                </div>

                {/* Status-Driven Actions Toolbar */}
                <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap", alignItems: "center" }}>
                  {/* Draft Actions: Edit, Clone, Activate, Retire */}
                  {isDraft && (
                    <>
                      <button
                        type="button"
                        className="btn btn-secondary btn-sm"
                        onClick={(e) => {
                          triggerRef.current = e.currentTarget;
                          setIsEditOpen(true);
                        }}
                      >
                        <EditIcon size={14} />
                        Edit Summary
                      </button>
                      <button
                        type="button"
                        className="btn btn-secondary btn-sm"
                        onClick={(e) => {
                          triggerRef.current = e.currentTarget;
                          setIsCloneOpen(true);
                        }}
                      >
                        <CopyIcon size={14} />
                        Clone
                      </button>
                      <button
                        type="button"
                        className="btn btn-primary btn-sm"
                        onClick={(e) => {
                          triggerRef.current = e.currentTarget;
                          setIsActivateOpen(true);
                        }}
                        style={{ background: "var(--status-success)", borderColor: "var(--status-success)" }}
                      >
                        <CheckCircleIcon size={14} />
                        Activate Version
                      </button>
                      <button
                        type="button"
                        className="btn btn-danger-action btn-sm"
                        onClick={(e) => {
                          triggerRef.current = e.currentTarget;
                          setIsRetireOpen(true);
                        }}
                      >
                        Retire
                      </button>
                    </>
                  )}

                  {/* Active Actions: Clone, Retire */}
                  {isActive && (
                    <>
                      <button
                        type="button"
                        className="btn btn-secondary btn-sm"
                        onClick={(e) => {
                          triggerRef.current = e.currentTarget;
                          setIsCloneOpen(true);
                        }}
                      >
                        <CopyIcon size={14} />
                        Clone to Draft
                      </button>
                      <button
                        type="button"
                        className="btn btn-danger-action btn-sm"
                        onClick={(e) => {
                          triggerRef.current = e.currentTarget;
                          setIsRetireOpen(true);
                        }}
                      >
                        Retire Version
                      </button>
                    </>
                  )}

                  {/* Retired Actions: Clone only */}
                  {isRetired && (
                    <button
                      type="button"
                      className="btn btn-secondary btn-sm"
                      onClick={(e) => {
                        triggerRef.current = e.currentTarget;
                        setIsCloneOpen(true);
                      }}
                    >
                      <CopyIcon size={14} />
                      Clone to Draft
                    </button>
                  )}
                </div>
              </div>

              {/* Version Timestamps & Lifecycle Metadata */}
              <div className="plan-meta-grid" style={{ marginTop: "1.25rem" }}>
                <div className="plan-meta-item">
                  <span className="meta-label">Activated At</span>
                  <span className="meta-value" title={version.activated_at || undefined}>{formatDateTime(version.activated_at)}</span>
                </div>

                <div className="plan-meta-item">
                  <span className="meta-label">Retired At</span>
                  <span className="meta-value" title={version.retired_at || undefined}>{formatDateTime(version.retired_at)}</span>
                </div>

                <div className="plan-meta-item">
                  <span className="meta-label">Created At</span>
                  <span className="meta-value" title={version.created_at}>{formatDateTime(version.created_at)}</span>
                </div>

                <div className="plan-meta-item">
                  <span className="meta-label">Last Updated</span>
                  <span className="meta-value" title={version.updated_at}>{formatDateTime(version.updated_at)}</span>
                </div>
              </div>
            </div>

            {/* Commercial Configuration Workspace */}
            <div className="commercial-tabs-container">
              <div className="commercial-tabs-nav-wrapper">
                <div
                  ref={tabsNavRef}
                  className="commercial-tabs-nav"
                  role="tablist"
                  aria-label="Plan Version Commercial Workspace"
                  onKeyDown={handleTabKeyDown}
                >
                  <button
                    type="button"
                    role="tab"
                    id="tab-overview"
                    aria-selected={activeTab === "overview"}
                    aria-controls="tabpanel-overview"
                    tabIndex={activeTab === "overview" ? 0 : -1}
                    className={`commercial-tab-btn ${activeTab === "overview" ? "active" : ""}`}
                    onClick={() => setActiveTab("overview")}
                  >
                    Overview &amp; Readiness
                  </button>
                  <button
                    type="button"
                    role="tab"
                    id="tab-pricing"
                    aria-selected={activeTab === "pricing"}
                    aria-controls="tabpanel-pricing"
                    tabIndex={activeTab === "pricing" ? 0 : -1}
                    className={`commercial-tab-btn ${activeTab === "pricing" ? "active" : ""}`}
                    onClick={() => setActiveTab("pricing")}
                  >
                    Pricing
                    {readiness !== null && (
                      <span className="commercial-tab-badge">
                        {readiness.prices_count}
                      </span>
                    )}
                  </button>
                  <button
                    type="button"
                    role="tab"
                    id="tab-packaging"
                    aria-selected={activeTab === "packaging"}
                    aria-controls="tabpanel-packaging"
                    tabIndex={activeTab === "packaging" ? 0 : -1}
                    className={`commercial-tab-btn ${activeTab === "packaging" ? "active" : ""}`}
                    onClick={() => setActiveTab("packaging")}
                  >
                    Product Packaging
                    {readiness !== null && (
                      <span className="commercial-tab-badge">
                        {readiness.products_count}
                      </span>
                    )}
                  </button>
                  <button
                    type="button"
                    role="tab"
                    id="tab-quotas"
                    aria-selected={activeTab === "quotas"}
                    aria-controls="tabpanel-quotas"
                    tabIndex={activeTab === "quotas" ? 0 : -1}
                    className={`commercial-tab-btn ${activeTab === "quotas" ? "active" : ""}`}
                    onClick={() => setActiveTab("quotas")}
                  >
                    Quotas
                    {quotasCount !== null && (
                      <span className="commercial-tab-badge">
                        {quotasCount}
                      </span>
                    )}
                  </button>
                </div>
              </div>

              {/* Tab 1: Overview & Readiness */}
              {activeTab === "overview" && (
                <div
                  id="tabpanel-overview"
                  role="tabpanel"
                  aria-labelledby="tab-overview"
                  style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}
                >
                  <PlanReadinessCard
                    readiness={readiness}
                    isLoading={isReadinessLoading}
                    versionStatus={version.status}
                    onRefresh={fetchReadiness}
                  />

                  <div className="plan-summary-card">
                    <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.75rem" }}>
                      <LayersIcon size={18} style={{ color: "var(--brand-primary)" }} />
                      <h3 className="heading-section" style={{ margin: 0, fontSize: "1.125rem" }}>
                        Commercial Configuration Summary
                      </h3>
                    </div>
                    <p className="text-body" style={{ fontSize: "0.875rem", margin: 0 }}>
                      This version packages <strong>{readiness?.products_count ?? 0} {readiness?.products_count === 1 ? "product" : "products"}</strong> with{" "}
                      <strong>{readiness?.prices_count ?? 0} {readiness?.prices_count === 1 ? "currency price definition" : "currency price definitions"}</strong> and{" "}
                      <strong>{quotasCount ?? 0} {quotasCount === 1 ? "commercial quota" : "commercial quotas"}</strong>.
                      Use the <strong>Pricing</strong>, <strong>Product Packaging</strong>, and <strong>Quotas</strong> tabs
                      above to manage commercial terms and usage limits.
                    </p>
                  </div>
                </div>
              )}

              {/* Tab 2: Pricing */}
              {activeTab === "pricing" && (
                <div id="tabpanel-pricing" role="tabpanel" aria-labelledby="tab-pricing">
                  <PlanPricingSection
                    versionId={version.id}
                    versionStatus={version.status}
                    versionNumber={version.version}
                    onMutated={handleCommercialMutated}
                  />
                </div>
              )}

              {/* Tab 3: Product Packaging */}
              {activeTab === "packaging" && (
                <div id="tabpanel-packaging" role="tabpanel" aria-labelledby="tab-packaging">
                  <PlanPackagingSection
                    versionId={version.id}
                    versionStatus={version.status}
                    versionNumber={version.version}
                    onMutated={handleCommercialMutated}
                  />
                </div>
              )}

              {/* Tab 4: Quotas */}
              {activeTab === "quotas" && (
                <div id="tabpanel-quotas" role="tabpanel" aria-labelledby="tab-quotas">
                  <PlanQuotaSection
                    versionId={version.id}
                    versionStatus={version.status}
                    versionNumber={version.version}
                    refreshTrigger={refreshCounter}
                    onMutated={handleCommercialMutated}
                    onQuotasCountChange={setQuotasCount}
                  />
                </div>
              )}
            </div>
          </>
        )}
      </div>

      {/* Dialogs */}
      <EditPlanVersionDialog
        version={version}
        isOpen={isEditOpen}
        onClose={() => setIsEditOpen(false)}
        onSuccess={handleEditSuccess}
        triggerRef={triggerRef}
      />

      <ClonePlanVersionDialog
        version={version}
        isOpen={isCloneOpen}
        onClose={() => setIsCloneOpen(false)}
        onSuccess={handleCloneSuccess}
        triggerRef={triggerRef}
      />

      <ActivatePlanVersionDialog
        version={version}
        readiness={readiness}
        isOpen={isActivateOpen}
        onClose={() => setIsActivateOpen(false)}
        onSuccess={handleActivateSuccess}
        triggerRef={triggerRef}
      />

      <RetirePlanVersionDialog
        version={version}
        isOpen={isRetireOpen}
        onClose={() => setIsRetireOpen(false)}
        onSuccess={handleRetireSuccess}
        triggerRef={triggerRef}
      />
    </AppShell>
  );
};
