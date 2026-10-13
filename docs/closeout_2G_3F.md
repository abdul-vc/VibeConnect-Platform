# Phase 2G – 3F Closeout Audit & Verification Evidence Pack

**Generated:** 2026-09-29  
**Platform:** VibeConnect Multi-Tenant SaaS Platform (Django + React)  
**Scope:** Phase 2G (Tenant Console, Launcher & Roles), Showcase (Portfolio & Presenter), Phase 3A–3F Remediation (Notifications, Onboarding, Invitations, Bulk Import, Async Queue, Access Control Hardening, and Access Requests).

---

## 1. Files and Migrations Changed Per Phase

### Phase 2G (Tenant Console, Launcher & Roles)
- **Migrations:**
  - `backend/apps/access_control/migrations/0004_tenant_modules_2g.py` (Bootstrapped `tenant_my_products`, `tenant_bulk_import`, `tenant_access_requests`, `products.view`, `bulk_import.view`, `bulk_import.manage`, `access_requests.view`, `access_requests.manage`)
- **Backend:**
  - `backend/apps/access_control/views.py` (Tenant access catalog, role policies, permission ceilings)
  - `backend/apps/access_control/urls.py`
  - `backend/apps/organizations/views.py` (Tenant home endpoint `/api/v1/tenant/home/`)
- **Frontend:**
  - `frontend/src/config/tenantModules.ts` (Authoritative 17-module registry)
  - `frontend/src/pages/tenant/TenantDashboardPage.tsx`
  - `frontend/src/pages/tenant/TenantMyProductsPage.tsx`
  - `frontend/src/pages/tenant/TenantRolesPage.tsx`
  - `frontend/src/pages/tenant/TenantAssignmentsPage.tsx`

### Showcase (Portfolio & Presenter)
- **Migrations:**
  - `backend/apps/showcase/migrations/0001_initial.py`
  - `backend/apps/showcase/migrations/0002_productlaunchconfig.py` (ProductLaunchConfig model & persistence)
- **Backend:**
  - `backend/apps/showcase/models.py` (ProductLaunchConfig, ShowcasePortfolio)
  - `backend/apps/showcase/views.py` (Launchability contract, portfolio, interactive demo)
  - `backend/apps/showcase/urls.py`
- **Frontend:**
  - `frontend/src/pages/showcase/ShowcasePortfolioPage.tsx`
  - `frontend/src/pages/showcase/ShowcasePresentPage.tsx`
  - `frontend/src/api/showcase.ts`

### Phase 3A (Notifications API & UI)
- **Migrations:**
  - `backend/apps/notifications/migrations/0001_initial.py`
  - `backend/apps/notifications/migrations/0002_backgroundjob.py` (Generic async task queue table)
  - `backend/apps/access_control/migrations/0005_tenant_modules_phase3.py` (Bootstrapped `tenant_notifications`, `notifications.view`, and `access_requests.decide`)
- **Backend:**
  - `backend/apps/notifications/models.py` (NotificationTemplate, NotificationDelivery, BackgroundJob)
  - `backend/apps/notifications/views.py` (Owner templates CRUD, new-version, retire, preview, and deliveries listing with channel/status filters; Tenant delivery logs)
  - `backend/apps/notifications/urls.py`
  - `backend/apps/notifications/management/commands/run_worker.py` (Async queue execution worker with `--once` and daemon polling)
- **Frontend:**
  - `frontend/src/api/notifications.ts` (Centralized `notificationsApi` client consuming `apiClient`)
  - `frontend/src/pages/notifications/OwnerNotificationsPage.tsx` (Owner template management, preview modal, delivery history)
  - `frontend/src/pages/notifications/TenantNotificationsPage.tsx` (Tenant notification delivery audit log)
  - `frontend/src/routes/AppRoutes.tsx` (Wired `/notifications` for owner and `/tenant/notifications` for tenant)
  - `frontend/src/components/AppShell.tsx` (Owner & tenant navigation links)
  - `frontend/src/config/tenantModules.ts` (Marked `notifications` module as implemented)

### Phase 3B (Onboarding Defect Fixes)
- **Backend:**
  - `backend/apps/onboarding/services.py`:
    - Enforced validation error raising when invitation issuance fails rather than silently swallowing.
    - Fixed `trial_days=0` handling to correctly invoke `create_active_subscription` when `not case.is_trial`.
    - Wrapped onboarding step provisioning inside `with transaction.atomic():` and persisted resumable `provisioning_failed` state on step exceptions.

### Phase 3C (Invitations Throttling)
- **Backend:**
  - `backend/config/settings/base.py`: Configured REST framework throttle rates for `invitation_issue` (30/min), `invitation_validate` (60/min), and `invitation_accept` (20/min).
  - `backend/.env.example`: Added default rate limit environment variables.
  - `backend/apps/invitations/views.py`: Applied `ScopedRateThrottle` on issuance, validation, and acceptance endpoints.

### Phase 3D (Bulk Import 202/Enqueue & Error Report)
- **Backend:**
  - `backend/apps/bulk_import/views.py`:
    - Updated `commit_import_job` and retry to enqueue async jobs and return HTTP 202 with `COMMITTING` status.
    - Implemented CSV error-report download endpoint at `/api/v1/bulk-import/jobs/<id>/error-report/`.
  - `backend/apps/bulk_import/services.py`: Implemented `generate_error_report_csv` stream service.
- **Frontend:**
  - `frontend/src/api/bulkImport.ts`: Added `getErrorReport` download method using centralized `apiClient`.
  - `frontend/src/pages/bulk_import/BulkImportPage.tsx`: Integrated error report download link.

### Phase 3E (Authorization Hardening)
- **Backend:**
  - Replaced hardcoded `membership_type == TENANT_ADMIN` bypasses in `backend/apps/bulk_import/views.py` and `backend/apps/access_requests/views.py` with `evaluate_access(user, "tenant", org.id)` permission checks (`bulk_import.manage`, `bulk_import.view`, `access_requests.decide`, and `access_requests.view`).
  - Added `backend/apps/access_control/migrations/0005_tenant_modules_phase3.py` to ensure `access_requests.decide` is explicitly bounded under `tenant_access_requests`.
  - Fixed test assertions in `backend/apps/access_control/tests/test_apis.py` and `backend/apps/access_control/tests/test_models.py` to account for the new module and permissions.

### Phase 3F (Access Requests Ceiling Re-validation)
- **Backend:**
  - Verified ceiling re-validation upon approval in `backend/apps/access_requests/services.py`: `approve_access_request` delegates assignment to `assign_user_to_product`, enforcing tenant permission ceiling bounds.

---

## 2. Requirement Status Table (2G, Showcase, 3A–3F)

| Phase | Requirement Description | Status | Verification Detail |
|---|---|---|---|
| **2G** | Authoritative 17-Module Tenant Console Registry | **Implemented** | Declared in `tenantModules.ts`; verified by test suite |
| **2G** | Tenant Launcher with 10 State Badges & Fallback | **Implemented** | Handled in `TenantMyProductsPage.tsx`; tested in test suite |
| **2G** | Tenant Home Endpoint `/api/v1/tenant/home/` | **Implemented** | Returns org, active context, modules, products, and metrics |
| **2G** | Route Guard Denials Fail Closed | **Implemented** | `ProtectedRoute.tsx` verifies context, module, and permission |
| **Showcase** | Product Portfolio & Interactive Presenter Mode | **Implemented** | `/showcase` and `/showcase/present` live |
| **Showcase** | ProductLaunchConfig Persistence & Contract | **Implemented** | `ProductLaunchConfig` model backed by DB and migration 0002 |
| **3A** | Notifications Template Management & Versioning | **Implemented** | CRUD, `new-version`, `retire`, `preview` endpoints active |
| **3A** | Notifications Delivery Audit Log & Filters | **Implemented** | Channel/status filtering in `/deliveries/` and UI logs |
| **3A** | Owner & Tenant Notifications Frontend UI | **Implemented** | `/notifications` (Owner) and `/tenant/notifications` (Tenant) |
| **3B** | Explicit Error on Invitation Failure | **Implemented** | Validation error raised; prevents incomplete onboarding state |
| **3B** | Trial vs Paid Subscription Segregation (`trial_days=0`) | **Implemented** | Invokes `create_active_subscription` when paid |
| **3B** | Atomic Step Execution with Resumable State | **Implemented** | `with transaction.atomic():` and `provisioning_failed` status |
| **3C** | Invitation Scoped Rate Limiting (Issue/Validate/Accept) | **Implemented** | Enforced via `ScopedRateThrottle` in DRF settings & views |
| **3D** | Bulk Import Commit HTTP 202 Async Enqueue | **Implemented** | Returns 202 with `BackgroundJob` creation and `COMMITTING` status |
| **3D** | CSV Error Report Download Endpoint & UI | **Implemented** | `/api/v1/bulk-import/jobs/<id>/error-report/` streams CSV |
| **3E** | RBAC Enforcement via `evaluate_access` | **Implemented** | Replaced `TENANT_ADMIN` checks with granular permission guards |
| **3F** | Access Request Ceiling Re-validation on Approval | **Implemented** | Enforced through `assign_user_to_product` in approval flow |

---

## 3. Live Route / Sidebar / Guard / Endpoint / Permission Matrix

### Platform Owner Console

| Route | Sidebar Label | Guard Requirement | Primary Backend Endpoint | Required Permission / Role |
|---|---|---|---|---|
| `/` | Overview | `requiredContext="platform_owner"` | `/api/v1/master-setup/` | Platform Owner |
| `/products` | Product Registry | `requiredContext="platform_owner"` | `/api/v1/products/` | Platform Owner |
| `/products/:id/catalog` | Product Catalog | `requiredContext="platform_owner"` | `/api/v1/products/<id>/catalog/` | Platform Owner |
| `/plans` | Plans & Pricing | `requiredContext="platform_owner"` | `/api/v1/plans/` | Platform Owner |
| `/subscriptions` | Subscriptions | `requiredContext="platform_owner"` | `/api/v1/subscriptions/` | Platform Owner |
| `/organizations` | Organization Registry | `requiredContext="platform_owner"` | `/api/v1/organizations/` | Platform Owner |
| `/onboarding` | Tenant Onboarding | `requiredContext="platform_owner"` | `/api/v1/onboarding/cases/` | Platform Owner |
| `/users` | Central Users | `requiredContext="platform_owner"` | `/api/v1/users/` | Platform Owner |
| `/organization-product-entitlements` | Product Access | `requiredContext="platform_owner"` | `/api/v1/organizations/entitlements/` | Platform Owner |
| `/bulk-import` | Data Import & Migration | `requiredContext="platform_owner"` | `/api/v1/bulk-import/jobs/` | Platform Owner |
| `/access-requests` | Access Requests & Approvals | `requiredContext="platform_owner"` | `/api/v1/access-requests/` | Platform Owner |
| `/showcase` | Product Showcase | `requiredContext="platform_owner"` | `/api/v1/showcase/portfolio/` | Platform Owner |
| `/showcase/present` | Showcase Presenter | `requiredContext="platform_owner"` | `/api/v1/showcase/contract/` | Platform Owner |
| `/notifications` | Notifications | `requiredContext="platform_owner"` | `/api/v1/notifications/templates/`, `/deliveries/` | Platform Owner |
| `/activity-log` | Activity Log | `requiredContext="platform_owner"` | `/api/v1/audit/logs/` | Platform Owner |

### Tenant Console

| Route | Sidebar Label | Guard Requirement | Primary Backend Endpoint | Required Permission |
|---|---|---|---|---|
| `/tenant` | Dashboard | `requiredContext="tenant"` | `/api/v1/tenant/home/` | Active Tenant Member |
| `/tenant/products` | My Products & Launcher | `module="tenant_my_products"` | `/api/v1/tenant/products/` | `products.view` |
| `/tenant/roles` | Roles & Permissions | `module="tenant_roles"` | `/api/v1/tenant/roles/`, `/access-catalog/` | `roles.view` |
| `/tenant/assignments` | Product Assignments | `module="tenant_product_assignments"` | `/api/v1/tenant/assignments/` | `assignments.view` |
| `/tenant/bulk-import` | Bulk User Onboarding | `module="tenant_bulk_import"` | `/api/v1/bulk-import/jobs/` | `bulk_import.view` |
| `/tenant/access-requests` | Access Requests | `module="tenant_access_requests"` | `/api/v1/access-requests/` | `access_requests.view` |
| `/tenant/notifications` | Notifications | `module="tenant_notifications"` | `/api/v1/notifications/deliveries/` | `notifications.view` |

---

## 4. Test Totals & Exact Raw Command Outputs

### Check 1: Django System Check
- **Command:** `.\venv\Scripts\python.exe manage.py check`
- **Output:**
```
System check identified no issues (0 silenced).
```
- **Exit Code:** 0

### Check 2: Django Migrations Check
- **Command:** `.\venv\Scripts\python.exe manage.py makemigrations --check --dry-run`
- **Output:**
```
No changes detected
```
- **Exit Code:** 0

### Check 3: Scoped & Access Control Backend Test Suites
- **Scoped Backend Command:** `.\venv\Scripts\python.exe manage.py test apps.bulk_import apps.access_requests apps.notifications apps.onboarding apps.invitations`
- **Scoped Output:**
```
Ran 45 tests in 35.999s

OK
Destroying test database for alias 'default'...
Found 45 test(s).
System check identified no issues (0 silenced).
```
- **Exit Code:** 0

- **Access Control Suite Command:** `.\venv\Scripts\python.exe manage.py test apps.access_control`
- **Access Control Output:**
```
Ran 147 tests in 293.381s

OK
Destroying test database for alias 'default'...
Found 147 test(s).
System check identified no issues (0 silenced).
```
- **Exit Code:** 0

### Check 4: Full Frontend Test Suite & Production Build
- **Command:** `cmd /c "npm test && npm run build"`
- **Output:**
```
✔ test_tenant_modules_registry_contains_all_17_modules (2.8142ms)
✔ test_sidebar_shows_exactly_permitted_implemented_modules (18.8509ms)
✔ test_sidebar_filters_out_unpermitted_modules (0.3559ms)
✔ test_route_guard_denial_fails_closed (4.5765ms)
✔ test_launcher_renders_all_ten_access_states_and_fallback (11.3457ms)
✔ test_tenant_switch_generation_counter_pattern (0.7881ms)
✔ test_320px_responsive_css_rules_and_overflow_prevention (0.6968ms)
✔ test_tenant_home_api_endpoint_and_client_usage (0.4203ms)
✔ src\__tests__\test-loader.mjs (198.6396ms)
ℹ tests 46
ℹ suites 0
ℹ pass 46
ℹ fail 0
ℹ cancelled 0
ℹ skipped 0
ℹ todo 0
ℹ duration_ms 1149.3628

> vibeconnect-frontend@1.0.0 build
> tsc -b && vite build

vite v6.4.3 building for production...
transforming...
✓ 209 modules transformed.
rendering chunks...
computing gzip size...
dist/index.html                                     0.57 kB │ gzip:   0.34 kB
dist/assets/index-CTMVRju5.css                     42.70 kB │ gzip:   7.31 kB
dist/assets/tenantHome-BOQZ5PYq.js                  0.14 kB │ gzip:   0.15 kB
dist/assets/invitations-nj2gVNrE.js                 0.25 kB │ gzip:   0.19 kB
dist/assets/users-DYgOAdtO.js                       0.47 kB │ gzip:   0.25 kB
dist/assets/accessRequests-DoO2tbkb.js              0.51 kB │ gzip:   0.25 kB
dist/assets/notifications-DzsIt9st.js               0.55 kB │ gzip:   0.28 kB
dist/assets/roles-CE5lvsFk.js                       1.02 kB │ gzip:   0.39 kB
dist/assets/showcase-C2ydigb4.js                    1.12 kB │ gzip:   0.40 kB
dist/assets/SubscriptionStatusBadge-CRrKi8kv.js     1.89 kB │ gzip:   0.78 kB
dist/assets/plans-C6TiHXK6.js                       2.43 kB │ gzip:   0.68 kB
dist/assets/catalog-L6r3rzbw.js                     2.74 kB │ gzip:   0.70 kB
dist/assets/UserLifecycleModal-B0Tv1eoR.js          4.19 kB │ gzip:   1.73 kB
dist/assets/PlanModalShell-D6yg3qDz.js              4.27 kB │ gzip:   1.68 kB
dist/assets/CatalogHierarchyNav-D46BMpHz.js         4.30 kB │ gzip:   1.05 kB
dist/assets/TenantNotificationsPage-BgQcyzS_.js     4.65 kB │ gzip:   1.50 kB
dist/assets/ShowcasePresentPage-L5OcoCOA.js         5.34 kB │ gzip:   1.90 kB
dist/assets/ContextSelectionPage-BNPFyNAs.js        5.62 kB │ gzip:   2.00 kB
dist/assets/AccessRequestFormPage-DYKfuyNS.js       6.54 kB │ gzip:   2.11 kB
dist/assets/InvitationAcceptPage-SHjcW4Kv.js        8.18 kB │ gzip:   2.28 kB
dist/assets/CentralUserDetailPage-Cn5aZKhW.js       8.20 kB │ gzip:   2.34 kB
dist/assets/ShowcasePortfolioPage-DyDe15az.js       8.44 kB │ gzip:   2.63 kB
dist/assets/TenantMyProductsPage-Dq6H2ecB.js        8.48 kB │ gzip:   2.42 kB
dist/assets/SubscriptionsListPage-Hq5yTSUL.js      11.40 kB │ gzip:   3.23 kB
dist/assets/PlansListPage-BZswe6Nr.js              12.09 kB │ gzip:   3.24 kB
dist/assets/PlanDetailPage-ilBY_V76.js             12.98 kB │ gzip:   3.67 kB
dist/assets/OwnerNotificationsPage-84C9Taaw.js     13.33 kB │ gzip:   2.87 kB
dist/assets/PlanStatusBadge-emS3VqFb.js            14.36 kB │ gzip:   3.84 kB
dist/assets/TenantOnboardingWizard-BHSwDah-.js     15.17 kB │ gzip:   3.95 kB
dist/assets/TenantDashboardPage-udBh_3wn.js        15.70 kB │ gzip:   3.19 kB
dist/assets/ProductCatalogPage-CIIuvHWy.js         17.00 kB │ gzip:   4.64 kB
dist/assets/ProductFeatureDetailPage-Dqh9pFs_.js   18.00 kB │ gzip:   5.02 kB
dist/assets/BulkImportPage-DOGgo7Du.js             18.69 kB │ gzip:   4.66 kB
dist/assets/ProductModuleDetailPage-BcfBrqae.js    18.70 kB │ gzip:   5.11 kB
dist/assets/AccessRequestQueuePage-CihydeNg.js     23.40 kB │ gzip:   5.25 kB
dist/assets/CentralUsersListPage-DMbV8Ygn.js       23.78 kB │ gzip:   5.51 kB
dist/assets/CatalogRetireDialog-D9EzmhJU.js        24.60 kB │ gzip:   6.37 kB
dist/assets/TenantAssignmentsPage-cMvewM-b.js      56.80 kB │ gzip:  10.68 kB
dist/assets/TenantRolesPage-B9W60LLw.js            59.39 kB │ gzip:  10.45 kB
dist/assets/PlanVersionDetailPage-CYQI7dq8.js      77.94 kB │ gzip:  16.86 kB
dist/assets/OrganizationDetailPage-BgpomgYK.js     99.02 kB │ gzip:  18.13 kB
dist/assets/index-Cy1qC6zQ.js                     459.31 kB │ gzip: 118.36 kB
✓ built in 1.97s
```
- **Exit Code:** 0
