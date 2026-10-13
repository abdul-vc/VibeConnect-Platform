/**
 * Organization Detail & Subscriptions Management Page.
 *
 * Provides Platform Owners with comprehensive organization management,
 * featuring dedicated Subscriptions tab with commercial overview, snapshot entitlements matrix,
 * lifecycle history timeline, and direct provisioning dialogs.
 */

import React, { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { organizationsApi } from "../../api/organizations.ts";
import { subscriptionsApi } from "../../api/subscriptions.ts";
import type {
  OrganizationDetail,
  SubscriptionDetail,
  SubscriptionListItem,
} from "../../api/types.ts";
import { AppShell } from "../../components/AppShell.tsx";
import { CatalogHierarchyNav } from "../../components/catalog/CatalogHierarchyNav.tsx";
import {
  BuildingIcon,
  ChevronRightIcon,
  LayersIcon,
  PlusIcon,
  ShieldCheckIcon,
  UserIcon,
} from "../../components/Icons.tsx";
import { OrganizationMembersSection } from "../../components/organizations/OrganizationMembersSection.tsx";
import { OrganizationStatusBadge } from "../../components/organizations/OrganizationStatusBadge.tsx";
import { ConsoleFeatureCeilingsSection } from "../../components/organizations/ConsoleFeatureCeilingsSection.tsx";
import { CreateSubscriptionDialog } from "../../components/subscriptions/CreateSubscriptionDialog.tsx";
import { StartTrialDialog } from "../../components/subscriptions/StartTrialDialog.tsx";
import { SubscriptionEntitlementsMatrix } from "../../components/subscriptions/SubscriptionEntitlementsMatrix.tsx";
import { SubscriptionHistoryTimeline } from "../../components/subscriptions/SubscriptionHistoryTimeline.tsx";
import { SubscriptionOverviewCard } from "../../components/subscriptions/SubscriptionOverviewCard.tsx";

type OrgTab = "subscriptions" | "members" | "profile";

export const OrganizationDetailPage: React.FC = () => {
  const { organizationId } = useParams<{ organizationId: string }>();
  const navigate = useNavigate();

  const [organization, setOrganization] = useState<OrganizationDetail | null>(null);
  const [isOrgLoading, setIsOrgLoading] = useState<boolean>(true);
  const [orgError, setOrgError] = useState<string | null>(null);

  // Subscriptions State
  const [activeTab, setActiveTab] = useState<OrgTab>("subscriptions");
  const [subscriptions, setSubscriptions] = useState<SubscriptionListItem[]>([]);
  const [isSubsLoading, setIsSubsLoading] = useState<boolean>(true);
  const [subsError, setSubsError] = useState<string | null>(null);
  const [refreshCounter, setRefreshCounter] = useState<number>(0);

  // Dialog States
  const [isStartTrialOpen, setIsStartTrialOpen] = useState<boolean>(false);
  const [isCreateSubOpen, setIsCreateSubOpen] = useState<boolean>(false);
  const triggerRef = useRef<HTMLElement | null>(null);

  const fetchOrganization = useCallback(async () => {
    if (!organizationId) return;
    setIsOrgLoading(true);
    setOrgError(null);
    try {
      const data = await organizationsApi.get(organizationId);
      setOrganization(data);
    } catch {
      setOrgError("Unable to load organization details.");
    } finally {
      setIsOrgLoading(false);
    }
  }, [organizationId]);

  const fetchSubscriptions = useCallback(async () => {
    if (!organizationId) return;
    setIsSubsLoading(true);
    setSubsError(null);
    try {
      const res = await subscriptionsApi.list({
        organization_id: organizationId,
        ordering: "-created_at",
        page_size: 50,
      });
      setSubscriptions(res.results as SubscriptionListItem[]);
    } catch {
      setSubsError("Unable to load subscriptions.");
    } finally {
      setIsSubsLoading(false);
    }
  }, [organizationId]);

  useEffect(() => {
    fetchOrganization();
  }, [fetchOrganization]);

  useEffect(() => {
    fetchSubscriptions();
  }, [fetchSubscriptions, refreshCounter]);

  // Find the open subscription (active, trialing, suspended)
  const openSubscription = subscriptions.find((s) =>
    ["active", "trialing", "suspended"].includes(s.status)
  );

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

  const handleSubscriptionCreated = (_sub: SubscriptionDetail) => {
    void _sub;
    setRefreshCounter((c) => c + 1);
  };

  const handleSubscriptionUpdated = (_sub: SubscriptionDetail) => {
    void _sub;
    setRefreshCounter((c) => c + 1);
  };

  return (
    <AppShell>
      <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem", minWidth: 0 }}>
        {/* Navigation Breadcrumbs Context */}
        <CatalogHierarchyNav
          items={[
            { label: "Organizations", path: "/organizations" },
            {
              label: organization?.name || "Loading Organization...",
              code: organization?.code,
            },
          ]}
        />

        {/* Organization Header Error */}
        {orgError && (
          <div className="alert-banner alert-banner-error" role="alert">
            <span>{orgError}</span>
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              onClick={fetchOrganization}
              style={{ marginLeft: "auto" }}
            >
              Retry
            </button>
          </div>
        )}

        {/* Skeleton for Header */}
        {isOrgLoading && (
          <div className="registry-skeleton-container">
            <div className="skeleton-row" style={{ height: "100px" }} />
          </div>
        )}

        {/* Organization Header Card */}
        {!isOrgLoading && organization && (
          <div className="org-header-card">
            <div className="org-header-main">
              <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", flexWrap: "wrap" }}>
                <span className="product-code-pill" style={{ fontSize: "0.9375rem" }}>
                  {organization.code}
                </span>
                <h1 className="heading-hero" style={{ fontSize: "1.5rem", margin: 0 }}>
                  {organization.name}
                </h1>
                <OrganizationStatusBadge status={organization.status} />
              </div>
              {organization.description && (
                <p className="text-body" style={{ marginTop: "0.5rem", fontSize: "0.875rem", maxWidth: "760px" }}>
                  {organization.description}
                </p>
              )}
            </div>

            <div className="org-meta-strip">
              <div className="org-meta-cell">
                <span className="meta-label">Account Status</span>
                <span className="meta-value" style={{ textTransform: "capitalize" }}>
                  {organization.status}
                </span>
              </div>
              <div className="org-meta-cell">
                <span className="meta-label">Registered Date</span>
                <span className="meta-value">{formatDate(organization.created_at)}</span>
              </div>
              <div className="org-meta-cell">
                <span className="meta-label">Active Subscription</span>
                <span className="meta-value">
                  {openSubscription ? (
                    <span style={{ color: "var(--brand-primary)", fontWeight: 600 }}>
                      {openSubscription.plan_name_snapshot} ({openSubscription.status})
                    </span>
                  ) : (
                    <span style={{ color: "var(--text-muted)", fontStyle: "italic" }}>
                      None Active
                    </span>
                  )}
                </span>
              </div>
            </div>
          </div>
        )}

        {/* Tab Navigation */}
        <div className="org-tabs-bar" role="tablist">
          <button
            type="button"
            role="tab"
            aria-selected={activeTab === "subscriptions"}
            className={`org-tab-btn ${activeTab === "subscriptions" ? "active" : ""}`}
            onClick={() => setActiveTab("subscriptions")}
          >
            <LayersIcon size={16} />
            <span>Subscriptions</span>
            {subscriptions.length > 0 && (
              <span className="tab-counter-badge">{subscriptions.length}</span>
            )}
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={activeTab === "members"}
            className={`org-tab-btn ${activeTab === "members" ? "active" : ""}`}
            onClick={() => setActiveTab("members")}
          >
            <UserIcon size={16} />
            <span>Members</span>
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={activeTab === "profile"}
            className={`org-tab-btn ${activeTab === "profile" ? "active" : ""}`}
            onClick={() => setActiveTab("profile")}
          >
            <BuildingIcon size={16} />
            <span>Account Details &amp; Grants</span>
          </button>
        </div>

        {/* TAB 1: Subscriptions Management */}
        {activeTab === "subscriptions" && (
          <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }}>
            {/* Subscriptions Error Banner */}
            {subsError && (
              <div className="alert-banner alert-banner-error" role="alert">
                <span>{subsError}</span>
                <button
                  type="button"
                  className="btn btn-secondary btn-sm"
                  onClick={fetchSubscriptions}
                  style={{ marginLeft: "auto" }}
                >
                  Retry
                </button>
              </div>
            )}

            {/* Loading Skeleton */}
            {isSubsLoading && (
              <div className="registry-skeleton-container">
                <div className="skeleton-row" style={{ height: "140px" }} />
                <div className="skeleton-row" style={{ height: "140px" }} />
              </div>
            )}

            {!isSubsLoading && organization && (
              <>
                {/* 1. Open Subscription Overview (if present) */}
                {openSubscription ? (
                  <>
                    <SubscriptionOverviewCard
                      subscription={openSubscription}
                      onSubscriptionUpdated={handleSubscriptionUpdated}
                      onReconciled={() => setRefreshCounter((c) => c + 1)}
                      isOrganizationRetired={organization.status === "retired"}
                    />

                    {/* Snapshot Entitlements Matrix */}
                    <SubscriptionEntitlementsMatrix
                      subscriptionId={openSubscription.id}
                      refreshKey={refreshCounter}
                    />
                  </>
                ) : (
                  /* Truthful Empty State when no active/trialing/suspended subscription */
                  <div className="subscription-empty-banner">
                    <div className="empty-icon-circle">
                      <LayersIcon size={26} />
                    </div>
                    <h3 style={{ fontSize: "1.125rem", fontWeight: 600, color: "var(--text-primary)", margin: 0 }}>
                      No Open Subscription
                    </h3>
                    <p style={{ fontSize: "0.875rem", color: "var(--text-secondary)", maxWidth: "480px", margin: "0.25rem 0 0.75rem 0", textAlign: "center" }}>
                      {organization.name} does not currently hold an active, trialing, or suspended commercial subscription.
                    </p>

                    {organization.status === "retired" ? (
                      <div
                        style={{
                          marginTop: "0.5rem",
                          padding: "0.625rem 1rem",
                          background: "var(--glass-surface)",
                          border: "1px solid var(--border-subtle)",
                          borderRadius: "8px",
                          fontSize: "0.875rem",
                          color: "var(--text-secondary)",
                          textAlign: "center",
                          maxWidth: "480px",
                        }}
                      >
                        Organization is retired. Subscription provisioning is disabled.
                      </div>
                    ) : (
                      <div style={{ display: "flex", gap: "0.75rem", flexWrap: "wrap", justifyContent: "center" }}>
                        <button
                          type="button"
                          className="btn btn-secondary"
                          onClick={(e) => {
                            triggerRef.current = e.currentTarget;
                            setIsStartTrialOpen(true);
                          }}
                        >
                          <PlusIcon size={16} />
                          Start Trial
                        </button>
                        <button
                          type="button"
                          className="btn btn-primary"
                          onClick={(e) => {
                            triggerRef.current = e.currentTarget;
                            setIsCreateSubOpen(true);
                          }}
                        >
                          <PlusIcon size={16} />
                          Create Paid Subscription
                        </button>
                      </div>
                    )}
                  </div>
                )}

                {/* Subscription Lineage / History */}
                {organizationId && (
                  <SubscriptionHistoryTimeline
                    organizationId={organizationId}
                    currentSubscriptionId={openSubscription?.id}
                    refreshKey={refreshCounter}
                  />
                )}
              </>
            )}
          </div>
        )}

        {/* TAB 2: Organization Memberships */}
        {activeTab === "members" && organization && (
          <OrganizationMembersSection organization={organization} />
        )}

        {/* TAB 3: Account Details & Direct Entitlements Link */}
        {activeTab === "profile" && organization && (
          <div className="org-profile-container">
            <div className="profile-section-card">
              <h3 style={{ fontSize: "1rem", fontWeight: 700, margin: "0 0 1rem 0", color: "var(--text-primary)" }}>
                Organization Account Properties
              </h3>
              <div className="profile-grid">
                <div>
                  <span className="text-caption">Organization ID</span>
                  <p className="code-pill" style={{ marginTop: "0.25rem" }}>{organization.id}</p>
                </div>
                <div>
                  <span className="text-caption">Organization Code</span>
                  <p className="code-pill" style={{ marginTop: "0.25rem" }}>{organization.code}</p>
                </div>
                <div>
                  <span className="text-caption">Account Status</span>
                  <p style={{ fontWeight: 600, color: "var(--text-primary)", marginTop: "0.25rem", textTransform: "capitalize" }}>
                    {organization.status}
                  </p>
                </div>
                <div>
                  <span className="text-caption">Creation Timestamp</span>
                  <p style={{ fontSize: "0.875rem", color: "var(--text-secondary)", marginTop: "0.25rem" }}>
                    {organization.created_at}
                  </p>
                </div>
              </div>
            </div>

            {/* Direct Grants Navigation Card */}
            <div className="profile-section-card" style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "1rem" }}>
              <div>
                <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                  <ShieldCheckIcon size={18} style={{ color: "var(--brand-primary)" }} />
                  <h4 style={{ fontSize: "0.9375rem", fontWeight: 600, margin: 0, color: "var(--text-primary)" }}>
                    Direct Product Entitlements
                  </h4>
                </div>
                <p className="text-caption" style={{ margin: "0.25rem 0 0 0", color: "var(--text-secondary)" }}>
                  Manage tenant-level direct product grants independent of subscription tiers.
                </p>
              </div>

              <button
                type="button"
                className="btn btn-secondary btn-sm"
                onClick={() => navigate(`/organization-product-entitlements`)}
              >
                <span>View Product Access</span>
                <ChevronRightIcon size={14} />
              </button>
            </div>

            {/* Console Feature Ceilings & Module Policies Section */}
            <ConsoleFeatureCeilingsSection organizationId={organization.id} />
          </div>
        )}
      </div>

      {/* Dialogs for starting trial or direct paid subscription */}
      {organization && (
        <>
          <StartTrialDialog
            isOpen={isStartTrialOpen}
            onClose={() => setIsStartTrialOpen(false)}
            onSuccess={handleSubscriptionCreated}
            organizationId={organization.id}
            organizationName={organization.name}
            triggerRef={triggerRef}
          />

          <CreateSubscriptionDialog
            isOpen={isCreateSubOpen}
            onClose={() => setIsCreateSubOpen(false)}
            onSuccess={handleSubscriptionCreated}
            organizationId={organization.id}
            organizationName={organization.name}
            triggerRef={triggerRef}
          />
        </>
      )}

      <style>{`
        .org-header-card {
          background: var(--glass-surface-elevated);
          border: 1px solid var(--border-glass);
          border-radius: 14px;
          padding: 1.5rem;
          box-shadow: var(--shadow-sm);
          display: flex;
          flex-direction: column;
          gap: 1.25rem;
        }

        .org-meta-strip {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
          gap: 1rem;
          padding-top: 1rem;
          border-top: 1px solid var(--border-subtle);
        }

        .org-meta-cell {
          display: flex;
          flex-direction: column;
          gap: 0.25rem;
        }

        .org-tabs-bar {
          display: flex;
          align-items: center;
          gap: 0.5rem;
          border-bottom: 1px solid var(--border-subtle);
          padding-bottom: 0.5rem;
        }

        .org-tab-btn {
          display: inline-flex;
          align-items: center;
          gap: 0.5rem;
          padding: 0.6rem 1rem;
          border-radius: 8px;
          font-size: 0.875rem;
          font-weight: 500;
          color: var(--text-secondary);
          background: transparent;
          border: 1px solid transparent;
          cursor: pointer;
          transition: all 0.15s ease;
        }

        .org-tab-btn:hover {
          background: var(--glass-surface-hover);
          color: var(--text-primary);
        }

        .org-tab-btn.active {
          background: var(--brand-primary-light);
          color: var(--brand-primary);
          border-color: var(--border-glass);
          font-weight: 600;
        }

        @media (max-width: 640px) {
          .org-tabs-bar {
            display: flex;
            overflow-x: auto;
            -webkit-overflow-scrolling: touch;
            scrollbar-width: none;
            gap: 0.5rem;
            width: 100%;
            padding-bottom: 0.5rem;
          }

          .org-tabs-bar::-webkit-scrollbar {
            display: none;
          }

          .org-tab-btn {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            white-space: nowrap;
            flex-shrink: 0;
            min-height: 44px;
            padding: 0.5rem 0.875rem;
            font-size: 0.8125rem;
            gap: 0.4rem;
            box-sizing: border-box;
          }

          .org-tab-btn svg {
            flex-shrink: 0;
            width: 15px;
            height: 15px;
          }
        }

        .tab-counter-badge {
          font-size: 0.75rem;
          padding: 0.1rem 0.45rem;
          border-radius: 9999px;
          background: var(--glass-surface);
          border: 1px solid var(--border-subtle);
          color: var(--text-primary);
        }

        .subscription-empty-banner {
          background: var(--glass-surface-elevated);
          border: 1px dashed var(--border-strong);
          border-radius: 14px;
          padding: 3rem 1.5rem;
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
        }

        .org-profile-container {
          display: flex;
          flex-direction: column;
          gap: 1.25rem;
        }

        .profile-section-card {
          background: var(--glass-surface-elevated);
          border: 1px solid var(--border-glass);
          border-radius: 12px;
          padding: 1.5rem;
        }

        .profile-grid {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
          gap: 1.25rem;
        }
      `}</style>
    </AppShell>
  );
};
