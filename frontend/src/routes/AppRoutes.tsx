import { FC, Suspense, lazy } from "react";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { ThemeProvider } from "../context/ThemeContext.tsx";
import { AuthProvider } from "../context/AuthContext.tsx";
import { ProtectedRoute } from "../components/ProtectedRoute.tsx";
import { LoadingSpinner } from "../components/LoadingSpinner.tsx";
import { LoginPage } from "../pages/LoginPage.tsx";
import { MasterSetupPage } from "../pages/MasterSetupPage.tsx";
import { ProductRegistryPage } from "../pages/ProductRegistryPage.tsx";
import { OrganizationRegistryPage } from "../pages/OrganizationRegistryPage.tsx";
import { OrganizationProductAccessPage } from "../pages/OrganizationProductAccessPage.tsx";
import { ActivityLogPage } from "../pages/ActivityLogPage.tsx";
import { NotFoundPage } from "../pages/NotFoundPage.tsx";
import { ErrorBoundary } from "../components/ErrorBoundary.tsx";

const ProductCatalogPage = lazy(() =>
  import("../pages/catalog/ProductCatalogPage.tsx").then((m) => ({
    default: m.ProductCatalogPage,
  }))
);
const ProductModuleDetailPage = lazy(() =>
  import("../pages/catalog/ProductModuleDetailPage.tsx").then((m) => ({
    default: m.ProductModuleDetailPage,
  }))
);
const ProductFeatureDetailPage = lazy(() =>
  import("../pages/catalog/ProductFeatureDetailPage.tsx").then((m) => ({
    default: m.ProductFeatureDetailPage,
  }))
);

const PlansListPage = lazy(() =>
  import("../pages/plans/PlansListPage.tsx").then((m) => ({
    default: m.PlansListPage,
  }))
);
const PlanDetailPage = lazy(() =>
  import("../pages/plans/PlanDetailPage.tsx").then((m) => ({
    default: m.PlanDetailPage,
  }))
);
const PlanVersionDetailPage = lazy(() =>
  import("../pages/plans/PlanVersionDetailPage.tsx").then((m) => ({
    default: m.PlanVersionDetailPage,
  }))
);

const SubscriptionsListPage = lazy(() =>
  import("../pages/subscriptions/SubscriptionsListPage.tsx").then((m) => ({
    default: m.SubscriptionsListPage,
  }))
);

const OrganizationDetailPage = lazy(() =>
  import("../pages/organizations/OrganizationDetailPage.tsx").then((m) => ({
    default: m.OrganizationDetailPage,
  }))
);

const TenantOnboardingWizard = lazy(() =>
  import("../pages/onboarding/TenantOnboardingWizard.tsx").then((m) => ({
    default: m.TenantOnboardingWizard,
  }))
);

const InvitationAcceptPage = lazy(() =>
  import("../pages/invitations/InvitationAcceptPage.tsx").then((m) => ({
    default: m.InvitationAcceptPage,
  }))
);

const BulkImportPage = lazy(() =>
  import("../pages/bulk_import/BulkImportPage.tsx").then((m) => ({
    default: m.BulkImportPage,
  }))
);

const AccessRequestQueuePage = lazy(() =>
  import("../pages/access_requests/AccessRequestQueuePage.tsx").then((m) => ({
    default: m.AccessRequestQueuePage,
  }))
);

const AccessRequestFormPage = lazy(() =>
  import("../pages/access_requests/AccessRequestFormPage.tsx").then((m) => ({
    default: m.AccessRequestFormPage,
  }))
);

const ShowcasePortfolioPage = lazy(() =>
  import("../pages/showcase/ShowcasePortfolioPage.tsx").then((m) => ({
    default: m.ShowcasePortfolioPage,
  }))
);

const ShowcasePresentPage = lazy(() =>
  import("../pages/showcase/ShowcasePresentPage.tsx").then((m) => ({
    default: m.ShowcasePresentPage,
  }))
);

const OwnerNotificationsPage = lazy(() =>
  import("../pages/notifications/OwnerNotificationsPage.tsx").then((m) => ({
    default: m.OwnerNotificationsPage,
  }))
);

const TenantNotificationsPage = lazy(() =>
  import("../pages/notifications/TenantNotificationsPage.tsx").then((m) => ({
    default: m.TenantNotificationsPage,
  }))
);

const WhiteLabelingPage = lazy(() =>
  import("../pages/branding/WhiteLabelingPage.tsx").then((m) => ({
    default: m.WhiteLabelingPage,
  }))
);

const TenantBrandingPage = lazy(() =>
  import("../pages/branding/TenantBrandingPage.tsx").then((m) => ({
    default: m.TenantBrandingPage,
  }))
);

const OwnerUsagePage = lazy(() =>
  import("../pages/owner/UsagePage.tsx").then((m) => ({
    default: m.UsagePage,
  }))
);

const OwnerBillingPage = lazy(() =>
  import("../pages/owner/BillingPage.tsx").then((m) => ({
    default: m.BillingPage,
  }))
);

const TenantUsagePage = lazy(() =>
  import("../pages/tenant/TenantUsagePage.tsx").then((m) => ({
    default: m.TenantUsagePage,
  }))
);

const TenantBillingPage = lazy(() =>
  import("../pages/tenant/TenantBillingPage.tsx").then((m) => ({
    default: m.TenantBillingPage,
  }))
);

const OwnerReconciliationPage = lazy(() =>
  import("../pages/owner/ReconciliationPage.tsx").then((m) => ({
    default: m.ReconciliationPage,
  }))
);

const OwnerReportsPage = lazy(() =>
  import("../pages/owner/ReportsPage.tsx").then((m) => ({
    default: m.ReportsPage,
  }))
);

const TenantReportsPage = lazy(() =>
  import("../pages/tenant/TenantReportsPage.tsx").then((m) => ({
    default: m.TenantReportsPage,
  }))
);

const OwnerIntegrationHubPage = lazy(() =>
  import("../pages/owner/IntegrationHubPage.tsx").then((m) => ({
    default: m.IntegrationHubPage,
  }))
);

const OwnerExternalMappingsPage = lazy(() =>
  import("../pages/owner/ExternalMappingsPage.tsx").then((m) => ({
    default: m.ExternalMappingsPage,
  }))
);

const OwnerIntegrationReconciliationPage = lazy(() =>
  import("../pages/owner/IntegrationReconciliationPage.tsx").then((m) => ({
    default: m.IntegrationReconciliationPage,
  }))
);

const CentralUsersListPage = lazy(() =>
  import("../pages/users/CentralUsersListPage.tsx").then((m) => ({
    default: m.CentralUsersListPage,
  }))
);
const CentralUserDetailPage = lazy(() =>
  import("../pages/users/CentralUserDetailPage.tsx").then((m) => ({
    default: m.CentralUserDetailPage,
  }))
);

const ContextSelectionPage = lazy(() =>
  import("../pages/tenant/ContextSelectionPage.tsx").then((m) => ({
    default: m.ContextSelectionPage,
  }))
);

const SupportConsolePage = lazy(() =>
  import("../pages/owner/SupportConsolePage.tsx").then((m) => ({
    default: m.SupportConsolePage,
  }))
);


const TenantDashboardPage = lazy(() =>
  import("../pages/tenant/TenantDashboardPage.tsx").then((m) => ({
    default: m.TenantDashboardPage,
  }))
);

const TenantMemberDashboardPage = lazy(() =>
  import("../pages/tenant/TenantMemberDashboardPage.tsx").then((m) => ({
    default: m.TenantMemberDashboardPage,
  }))
);

const TenantMyProductsPage = lazy(() =>
  import("../pages/tenant/TenantMyProductsPage.tsx").then((m) => ({
    default: m.TenantMyProductsPage,
  }))
);

const TenantProductWorkspacePage = lazy(() =>
  import("../pages/tenant/TenantProductWorkspacePage.tsx").then((m) => ({
    default: m.TenantProductWorkspacePage,
  }))
);

const TenantMarketplacePage = lazy(() =>
  import("../pages/marketplace/TenantMarketplacePage.tsx").then((m) => ({
    default: m.TenantMarketplacePage,
  }))
);

const TenantRolesPage = lazy(() =>
  import("../pages/tenant/TenantRolesPage.tsx").then((m) => ({
    default: m.TenantRolesPage,
  }))
);

const TenantAssignmentsPage = lazy(() =>
  import("../pages/tenant/TenantAssignmentsPage.tsx").then((m) => ({
    default: m.TenantAssignmentsPage,
  }))
);

const TenantDeveloperConsolePage = lazy(() =>
  import("../pages/tenant/TenantDeveloperConsolePage.tsx").then((m) => ({
    default: m.TenantDeveloperConsolePage,
  }))
);

const OwnerDeveloperOversightPage = lazy(() =>
  import("../pages/owner/OwnerDeveloperOversightPage.tsx").then((m) => ({
    default: m.OwnerDeveloperOversightPage,
  }))
);

const AuditedSupportImpersonationPage = lazy(() =>
  import("../pages/owner/AuditedSupportImpersonationPage.tsx").then((m) => ({
    default: m.AuditedSupportImpersonationPage,
  }))
);

const TenantProfilePage = lazy(() =>
  import("../pages/tenant/TenantProfilePage.tsx").then((m) => ({
    default: m.TenantProfilePage,
  }))
);

const TenantUsersPage = lazy(() =>
  import("../pages/tenant/TenantUsersPage.tsx").then((m) => ({
    default: m.TenantUsersPage,
  }))
);

const TenantMemberOnboardingPage = lazy(() =>
  import("../pages/tenant/TenantMemberOnboardingPage.tsx").then((m) => ({
    default: m.TenantMemberOnboardingPage,
  }))
);

const TenantSubscriptionsPage = lazy(() =>
  import("../pages/tenant/TenantSubscriptionsPage.tsx").then((m) => ({
    default: m.TenantSubscriptionsPage,
  }))
);

const TenantSsoPage = lazy(() =>
  import("../pages/tenant/TenantSsoPage.tsx").then((m) => ({
    default: m.TenantSsoPage,
  }))
);

const TenantSecurityPage = lazy(() =>
  import("../pages/tenant/TenantSecurityPage.tsx").then((m) => ({
    default: m.TenantSecurityPage,
  }))
);

const TenantActivityLogPage = lazy(() =>
  import("../pages/tenant/TenantActivityLogPage.tsx").then((m) => ({
    default: m.TenantActivityLogPage,
  }))
);

const TenantSettingsPage = lazy(() =>
  import("../pages/tenant/TenantSettingsPage.tsx").then((m) => ({
    default: m.TenantSettingsPage,
  }))
);

const CatalogLoadingFallback: FC = () => (
  <div role="status" aria-live="polite">
    <LoadingSpinner label="Loading catalog…" fullScreen={true} />
  </div>
);

const PlansLoadingFallback: FC = () => (
  <div role="status" aria-live="polite">
    <LoadingSpinner label="Loading plans…" fullScreen={true} />
  </div>
);

const SubscriptionsLoadingFallback: FC = () => (
  <div role="status" aria-live="polite">
    <LoadingSpinner label="Loading subscriptions…" fullScreen={true} />
  </div>
);

const UsersLoadingFallback: FC = () => (
  <div role="status" aria-live="polite">
    <LoadingSpinner label="Loading users…" fullScreen={true} />
  </div>
);

const ContextLoadingFallback: FC = () => (
  <div role="status" aria-live="polite">
    <LoadingSpinner label="Loading console…" fullScreen={true} />
  </div>
);

export const AppRoutes: FC = () => {
  return (
    <ErrorBoundary>
      <ThemeProvider>
        <AuthProvider>
          <BrowserRouter
            future={{
              v7_startTransition: true,
              v7_relativeSplatPath: true,
            }}
          >
            <Routes>
              <Route path="/login" element={<LoginPage />} />
              <Route
                path="/invitations/:token"
                element={
                  <Suspense fallback={<ContextLoadingFallback />}>
                    <InvitationAcceptPage />
                  </Suspense>
                }
              />
              <Route
                path="/invitations/accept/:token"
                element={
                  <Suspense fallback={<ContextLoadingFallback />}>
                    <InvitationAcceptPage />
                  </Suspense>
                }
              />
              <Route
                path="/bulk-import"
                element={
                  <ProtectedRoute requiredContext="platform_owner">
                    <Suspense fallback={<SubscriptionsLoadingFallback />}>
                      <BulkImportPage />
                    </Suspense>
                  </ProtectedRoute>
                }
              />
              <Route
                path="/access-requests"
                element={
                  <ProtectedRoute requiredContext="platform_owner">
                    <Suspense fallback={<SubscriptionsLoadingFallback />}>
                      <AccessRequestQueuePage />
                    </Suspense>
                  </ProtectedRoute>
                }
              />
              <Route
                path="/access-requests/new"
                element={
                  <ProtectedRoute requiredContext="platform_owner">
                    <Suspense fallback={<SubscriptionsLoadingFallback />}>
                      <AccessRequestFormPage />
                    </Suspense>
                  </ProtectedRoute>
                }
              />
              <Route
                path="/select-context"
                element={
                  <ProtectedRoute>
                    <Suspense fallback={<ContextLoadingFallback />}>
                      <ContextSelectionPage />
                    </Suspense>
                  </ProtectedRoute>
                }
              />
              <Route
                path="/tenant"
                element={
                  <ProtectedRoute requiredContext="tenant" adminOnly={true}>
                    <Suspense fallback={<ContextLoadingFallback />}>
                      <TenantDashboardPage />
                    </Suspense>
                  </ProtectedRoute>
                }
              />
              <Route
                path="/tenant/dashboard"
                element={
                  <ProtectedRoute requiredContext="tenant">
                    <Suspense fallback={<ContextLoadingFallback />}>
                      <TenantMemberDashboardPage />
                    </Suspense>
                  </ProtectedRoute>
                }
              />
              <Route
                path="/tenant/products"
                element={
                  <ProtectedRoute requiredContext="tenant">
                    <Suspense fallback={<ContextLoadingFallback />}>
                      <TenantMyProductsPage />
                    </Suspense>
                  </ProtectedRoute>
                }
              />
              <Route
                path="/tenant/workspace/:productId"
                element={
                  <ProtectedRoute requiredContext="tenant">
                    <Suspense fallback={<ContextLoadingFallback />}>
                      <TenantProductWorkspacePage />
                    </Suspense>
                  </ProtectedRoute>
                }
              />
              <Route
                path="/marketplace"
                element={
                  <ProtectedRoute requiredContext="tenant" adminOnly={true}>
                    <Suspense fallback={<ContextLoadingFallback />}>
                      <TenantMarketplacePage />
                    </Suspense>
                  </ProtectedRoute>
                }
              />
              <Route
                path="/tenant/marketplace"
                element={
                  <ProtectedRoute requiredContext="tenant" adminOnly={true}>
                    <Suspense fallback={<ContextLoadingFallback />}>
                      <TenantMarketplacePage />
                    </Suspense>
                  </ProtectedRoute>
                }
              />
              <Route
                path="/tenant/roles"
                element={
                  <ProtectedRoute
                    requiredContext="tenant"
                    requiredModule="tenant_roles"
                    requiredPermission="roles.view"
                  >
                    <Suspense fallback={<ContextLoadingFallback />}>
                      <TenantRolesPage />
                    </Suspense>
                  </ProtectedRoute>
                }
              />
              <Route
                path="/tenant/assignments"
                element={
                  <ProtectedRoute
                    requiredContext="tenant"
                    requiredModule="tenant_product_assignments"
                    requiredPermission="assignments.view"
                  >
                    <Suspense fallback={<ContextLoadingFallback />}>
                      <TenantAssignmentsPage />
                    </Suspense>
                  </ProtectedRoute>
                }
              />
              <Route
                path="/tenant/bulk-import"
                element={
                  <ProtectedRoute
                    requiredContext="tenant"
                    requiredModule="tenant_bulk_import"
                    requiredPermission="bulk_import.view"
                  >
                    <Suspense fallback={<SubscriptionsLoadingFallback />}>
                      <BulkImportPage />
                    </Suspense>
                  </ProtectedRoute>
                }
              />
              <Route
                path="/tenant/access-requests"
                element={
                  <ProtectedRoute
                    requiredContext="tenant"
                    requiredModule="tenant_access_requests"
                    requiredPermission="access_requests.view"
                  >
                    <Suspense fallback={<SubscriptionsLoadingFallback />}>
                      <AccessRequestQueuePage />
                    </Suspense>
                  </ProtectedRoute>
                }
              />
              <Route
                path="/tenant/access-requests/new"
                element={
                  <ProtectedRoute
                    requiredContext="tenant"
                    requiredModule="tenant_access_requests"
                    requiredPermission="access_requests.view"
                  >
                    <Suspense fallback={<SubscriptionsLoadingFallback />}>
                      <AccessRequestFormPage />
                    </Suspense>
                  </ProtectedRoute>
                }
              />
              <Route
                path="/tenant/notifications"
                element={
                  <ProtectedRoute
                    requiredContext="tenant"
                    requiredModule="tenant_notifications"
                    requiredPermission="notifications.view"
                  >
                    <Suspense fallback={<ContextLoadingFallback />}>
                      <TenantNotificationsPage />
                    </Suspense>
                  </ProtectedRoute>
                }
              />
              <Route
                path="/tenant/branding"
                element={
                  <ProtectedRoute
                    requiredContext="tenant"
                    requiredModule="tenant_branding"
                    requiredPermission="branding.view"
                  >
                    <Suspense fallback={<ContextLoadingFallback />}>
                      <TenantBrandingPage />
                    </Suspense>
                  </ProtectedRoute>
                }
              />
              <Route
                path="/tenant/usage"
                element={
                  <ProtectedRoute
                    requiredContext="tenant"
                    requiredModule="tenant_usage"
                    requiredPermission="usage.view"
                  >
                    <Suspense fallback={<ContextLoadingFallback />}>
                      <TenantUsagePage />
                    </Suspense>
                  </ProtectedRoute>
                }
              />
              <Route
                path="/tenant/billing"
                element={
                  <ProtectedRoute
                    requiredContext="tenant"
                    requiredModule="tenant_billing"
                    requiredPermission="billing.view"
                  >
                    <Suspense fallback={<ContextLoadingFallback />}>
                      <TenantBillingPage />
                    </Suspense>
                  </ProtectedRoute>
                }
              />
              <Route
                path="/tenant/reports"
                element={
                  <ProtectedRoute
                    requiredContext="tenant"
                    requiredModule="tenant_reports"
                    requiredPermission="reports.view"
                  >
                    <Suspense fallback={<ContextLoadingFallback />}>
                      <TenantReportsPage />
                    </Suspense>
                  </ProtectedRoute>
                }
              />
              <Route
                path="/tenant/developer"
                element={
                  <ProtectedRoute requiredContext="tenant" adminOnly={true}>
                    <Suspense fallback={<ContextLoadingFallback />}>
                      <TenantDeveloperConsolePage />
                    </Suspense>
                  </ProtectedRoute>
                }
              />
              <Route
                path="/tenant/profile"
                element={
                  <ProtectedRoute
                    requiredContext="tenant"
                    requiredModule="tenant_profile"
                    requiredPermission="profile.view"
                  >
                    <Suspense fallback={<ContextLoadingFallback />}>
                      <TenantProfilePage />
                    </Suspense>
                  </ProtectedRoute>
                }
              />
              <Route
                path="/tenant/users"
                element={
                  <ProtectedRoute
                    requiredContext="tenant"
                    requiredModule="tenant_users"
                    requiredPermission="users.view"
                  >
                    <Suspense fallback={<ContextLoadingFallback />}>
                      <TenantUsersPage />
                    </Suspense>
                  </ProtectedRoute>
                }
              />
              <Route
                path="/tenant/member-onboarding"
                element={
                  <ProtectedRoute
                    requiredContext="tenant"
                    requiredModule="tenant_roles"
                    requiredPermission="roles.assign"
                  >
                    <Suspense fallback={<ContextLoadingFallback />}>
                      <TenantMemberOnboardingPage />
                    </Suspense>
                  </ProtectedRoute>
                }
              />
              <Route
                path="/tenant/subscriptions"
                element={
                  <ProtectedRoute
                    requiredContext="tenant"
                    requiredModule="tenant_subscriptions"
                    requiredPermission="subscriptions.view"
                  >
                    <Suspense fallback={<ContextLoadingFallback />}>
                      <TenantSubscriptionsPage />
                    </Suspense>
                  </ProtectedRoute>
                }
              />
              <Route
                path="/tenant/sso"
                element={
                  <ProtectedRoute
                    requiredContext="tenant"
                    requiredModule="tenant_sso"
                    requiredPermission="sso.view"
                  >
                    <Suspense fallback={<ContextLoadingFallback />}>
                      <TenantSsoPage />
                    </Suspense>
                  </ProtectedRoute>
                }
              />
              <Route
                path="/tenant/security"
                element={
                  <ProtectedRoute
                    requiredContext="tenant"
                    requiredModule="tenant_security"
                    requiredPermission="security.view"
                  >
                    <Suspense fallback={<ContextLoadingFallback />}>
                      <TenantSecurityPage />
                    </Suspense>
                  </ProtectedRoute>
                }
              />
              <Route
                path="/tenant/activity-log"
                element={
                  <ProtectedRoute
                    requiredContext="tenant"
                    requiredModule="tenant_audit_log"
                    requiredPermission="audit.view"
                  >
                    <Suspense fallback={<ContextLoadingFallback />}>
                      <TenantActivityLogPage />
                    </Suspense>
                  </ProtectedRoute>
                }
              />
              <Route
                path="/tenant/settings"
                element={
                  <ProtectedRoute
                    requiredContext="tenant"
                    requiredModule="tenant_settings"
                    requiredPermission="settings.view"
                  >
                    <Suspense fallback={<ContextLoadingFallback />}>
                      <TenantSettingsPage />
                    </Suspense>
                  </ProtectedRoute>
                }
              />
              <Route
                path="/"
                element={
                  <ProtectedRoute requiredContext="platform_owner">
                    <MasterSetupPage />
                  </ProtectedRoute>
                }
              />
              <Route
                path="/products"
                element={
                  <ProtectedRoute requiredContext="platform_owner">
                    <ProductRegistryPage />
                  </ProtectedRoute>
                }
              />
              <Route
                path="/products/:productId/catalog"
                element={
                  <ProtectedRoute requiredContext="platform_owner">
                    <Suspense fallback={<CatalogLoadingFallback />}>
                      <ProductCatalogPage />
                    </Suspense>
                  </ProtectedRoute>
                }
              />
              <Route
                path="/products/:productId/catalog/modules/:moduleId"
                element={
                  <ProtectedRoute requiredContext="platform_owner">
                    <Suspense fallback={<CatalogLoadingFallback />}>
                      <ProductModuleDetailPage />
                    </Suspense>
                  </ProtectedRoute>
                }
              />
              <Route
                path="/products/:productId/catalog/modules/:moduleId/features/:featureId"
                element={
                  <ProtectedRoute requiredContext="platform_owner">
                    <Suspense fallback={<CatalogLoadingFallback />}>
                      <ProductFeatureDetailPage />
                    </Suspense>
                  </ProtectedRoute>
                }
              />
              <Route
                path="/plans"
                element={
                  <ProtectedRoute requiredContext="platform_owner">
                    <Suspense fallback={<PlansLoadingFallback />}>
                      <PlansListPage />
                    </Suspense>
                  </ProtectedRoute>
                }
              />
              <Route
                path="/plans/:planId"
                element={
                  <ProtectedRoute requiredContext="platform_owner">
                    <Suspense fallback={<PlansLoadingFallback />}>
                      <PlanDetailPage />
                    </Suspense>
                  </ProtectedRoute>
                }
              />
              <Route
                path="/plan-versions/:versionId"
                element={
                  <ProtectedRoute requiredContext="platform_owner">
                    <Suspense fallback={<PlansLoadingFallback />}>
                      <PlanVersionDetailPage />
                    </Suspense>
                  </ProtectedRoute>
                }
              />
              <Route
                path="/subscriptions"
                element={
                  <ProtectedRoute requiredContext="platform_owner">
                    <Suspense fallback={<SubscriptionsLoadingFallback />}>
                      <SubscriptionsListPage />
                    </Suspense>
                  </ProtectedRoute>
                }
              />
              <Route
                path="/organizations"
                element={
                  <ProtectedRoute requiredContext="platform_owner">
                    <OrganizationRegistryPage />
                  </ProtectedRoute>
                }
              />
              <Route
                path="/organizations/:organizationId"
                element={
                  <ProtectedRoute requiredContext="platform_owner">
                    <Suspense fallback={<SubscriptionsLoadingFallback />}>
                      <OrganizationDetailPage />
                    </Suspense>
                  </ProtectedRoute>
                }
              />
              <Route
                path="/onboarding"
                element={
                  <ProtectedRoute requiredContext="platform_owner">
                    <Suspense fallback={<SubscriptionsLoadingFallback />}>
                      <TenantOnboardingWizard />
                    </Suspense>
                  </ProtectedRoute>
                }
              />
              <Route
                path="/users"
                element={
                  <ProtectedRoute requiredContext="platform_owner">
                    <Suspense fallback={<UsersLoadingFallback />}>
                      <CentralUsersListPage />
                    </Suspense>
                  </ProtectedRoute>
                }
              />
              <Route
                path="/users/:userId"
                element={
                  <ProtectedRoute requiredContext="platform_owner">
                    <Suspense fallback={<UsersLoadingFallback />}>
                      <CentralUserDetailPage />
                    </Suspense>
                  </ProtectedRoute>
                }
              />
              <Route
                path="/organization-product-entitlements"
                element={
                  <ProtectedRoute requiredContext="platform_owner">
                    <OrganizationProductAccessPage />
                  </ProtectedRoute>
                }
              />
              <Route
                path="/activity-log"
                element={
                  <ProtectedRoute requiredContext="platform_owner">
                    <ActivityLogPage />
                  </ProtectedRoute>
                }
              />
              <Route
                path="/showcase"
                element={
                  <ProtectedRoute requiredContext="platform_owner">
                    <Suspense fallback={<CatalogLoadingFallback />}>
                      <ShowcasePortfolioPage />
                    </Suspense>
                  </ProtectedRoute>
                }
              />
              <Route
                path="/showcase/present"
                element={
                  <ProtectedRoute requiredContext="platform_owner">
                    <Suspense fallback={<CatalogLoadingFallback />}>
                      <ShowcasePresentPage />
                    </Suspense>
                  </ProtectedRoute>
                }
              />
              <Route
                path="/notifications"
                element={
                  <ProtectedRoute requiredContext="platform_owner">
                    <Suspense fallback={<SubscriptionsLoadingFallback />}>
                      <OwnerNotificationsPage />
                    </Suspense>
                  </ProtectedRoute>
                }
              />
              <Route
                path="/white-labeling"
                element={
                  <ProtectedRoute requiredContext="platform_owner">
                    <Suspense fallback={<SubscriptionsLoadingFallback />}>
                      <WhiteLabelingPage />
                    </Suspense>
                  </ProtectedRoute>
                }
              />
              <Route
                path="/usage"
                element={
                  <ProtectedRoute requiredContext="platform_owner">
                    <Suspense fallback={<SubscriptionsLoadingFallback />}>
                      <OwnerUsagePage />
                    </Suspense>
                  </ProtectedRoute>
                }
              />
              <Route
                path="/billing"
                element={
                  <ProtectedRoute requiredContext="platform_owner">
                    <Suspense fallback={<SubscriptionsLoadingFallback />}>
                      <OwnerBillingPage />
                    </Suspense>
                  </ProtectedRoute>
                }
              />
              <Route
                path="/reconciliation"
                element={
                  <ProtectedRoute requiredContext="platform_owner">
                    <Suspense fallback={<SubscriptionsLoadingFallback />}>
                      <OwnerReconciliationPage />
                    </Suspense>
                  </ProtectedRoute>
                }
              />
              <Route
                path="/reports"
                element={
                  <ProtectedRoute requiredContext="platform_owner">
                    <Suspense fallback={<SubscriptionsLoadingFallback />}>
                      <OwnerReportsPage />
                    </Suspense>
                  </ProtectedRoute>
                }
              />
              <Route
                path="/integration"
                element={
                  <ProtectedRoute requiredContext="platform_owner">
                    <Suspense fallback={<SubscriptionsLoadingFallback />}>
                      <OwnerIntegrationHubPage />
                    </Suspense>
                  </ProtectedRoute>
                }
              />
              <Route
                path="/integration/mappings"
                element={
                  <ProtectedRoute requiredContext="platform_owner">
                    <Suspense fallback={<SubscriptionsLoadingFallback />}>
                      <OwnerExternalMappingsPage />
                    </Suspense>
                  </ProtectedRoute>
                }
              />
              <Route
                path="/integration/reconciliation"
                element={
                  <ProtectedRoute requiredContext="platform_owner">
                    <Suspense fallback={<SubscriptionsLoadingFallback />}>
                      <OwnerIntegrationReconciliationPage />
                    </Suspense>
                  </ProtectedRoute>
                }
              />
              <Route
                path="/owner/developer-oversight"
                element={
                  <ProtectedRoute requiredContext="platform_owner">
                    <Suspense fallback={<SubscriptionsLoadingFallback />}>
                      <OwnerDeveloperOversightPage />
                    </Suspense>
                  </ProtectedRoute>
                }
              />
              <Route
                path="/support"
                element={
                  <ProtectedRoute requiredPermission="support.diagnostics.view">
                    <Suspense fallback={<SubscriptionsLoadingFallback />}>
                      <SupportConsolePage />
                    </Suspense>
                  </ProtectedRoute>
                }
              />
              <Route
                path="/support/impersonation"
                element={
                  <ProtectedRoute requiredPermission="support.diagnostics.view">
                    <Suspense fallback={<SubscriptionsLoadingFallback />}>
                      <AuditedSupportImpersonationPage />
                    </Suspense>
                  </ProtectedRoute>
                }
              />
              <Route path="*" element={<NotFoundPage />} />
            </Routes>
          </BrowserRouter>
        </AuthProvider>
      </ThemeProvider>
    </ErrorBoundary>
  );
};
