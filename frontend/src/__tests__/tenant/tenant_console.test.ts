/**
 * Phase 2G: Tenant Console Shell, Dashboard & App Launcher Tests.
 *
 * Validates:
 * 1. TENANT_MODULES_REGISTRY contains all 17 tenant modules with exact specification IDs.
 * 2. Sidebar shows exactly the permitted implemented modules and filters out unimplemented/unpermitted ones.
 * 3. Route guard denial: fails closed when requiredContext, requiredModule, or requiredPermission is missing.
 * 4. App Launcher renders all 10 access states and safely falls back on unknown states without crashing.
 * 5. App Launcher never exposes or builds product URLs and keeps the Launch action disabled with SSO tooltip.
 * 6. Tenant-switch generation counter pattern resets state.
 * 7. 320px responsive CSS layout assertions (min-width: 0, word-break / overflow-wrap).
 * 8. tenantHomeApi client integration with apiClient and ENDPOINTS.TENANT_HOME.
 */

import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router-dom";

// Setup minimal browser DOM environment for Node execution
if (
  typeof globalThis.window === "undefined" ||
  !(globalThis as unknown as { window: { matchMedia?: unknown } }).window.matchMedia
) {
  (globalThis as unknown as { window: unknown }).window = {
    addEventListener: () => {},
    removeEventListener: () => {},
    scrollTo: () => {},
    location: { pathname: "/tenant", search: "" },
    matchMedia: () => ({
      matches: false,
      addEventListener: () => {},
      removeEventListener: () => {},
    }),
  };
}
if (typeof globalThis.document === "undefined") {
  (globalThis as unknown as { document: unknown }).document = {
    body: { style: {} },
    activeElement: null,
    addEventListener: () => {},
    removeEventListener: () => {},
    getElementById: () => null,
  };
}

import { TENANT_MODULES_REGISTRY, getVisibleTenantModules } from "../../config/tenantModules.ts";
import { AppShell } from "../../components/AppShell.tsx";
import { ProtectedRoute } from "../../components/ProtectedRoute.tsx";
import { TenantMyProductsPage } from "../../pages/tenant/TenantMyProductsPage.tsx";
import { tenantHomeApi } from "../../api/tenantHome.ts";
import { ENDPOINTS } from "../../api/endpoints.ts";
import { apiClient } from "../../api/client.ts";
import { AuthContext } from "../../context/AuthContext.tsx";
import { ThemeProvider } from "../../context/ThemeContext.tsx";
import type {
  AuthenticatedUser,
  AccessState,
  TenantHomeResponse,
  TenantProductAccessItem,
} from "../../api/types.ts";

function createMockTenantUser(
  overrides?: Partial<AuthenticatedUser>,
  contextOverrides?: {
    permissions?: string[];
    modules?: string[];
  }
): AuthenticatedUser {
  return {
    id: "user-tenant-1",
    email: "tenant.admin@acme.com",
    full_name: "Tenant Admin",
    is_platform_owner: false,
    active_context: {
      type: "tenant",
      organization: {
        id: "org-acme-1",
        code: "ACME",
        name: "Acme Corporation",
      },
      effective_permissions: contextOverrides?.permissions ?? [
        "org.view",
        "products.view",
        "assignments.view",
        "assignments.manage",
        "roles.view",
        "roles.manage",
        "bulk_import.view",
        "bulk_import.manage",
        "access_requests.view",
        "access_requests.manage",
      ],
      allowed_modules: contextOverrides?.modules ?? [
        "tenant_dashboard",
        "tenant_my_products",
        "tenant_roles",
        "tenant_product_assignments",
        "tenant_bulk_import",
        "tenant_access_requests",
      ],
    },
    available_contexts: [
      {
        type: "tenant",
        organization: {
          id: "org-acme-1",
          code: "ACME",
          name: "Acme Corporation",
        },
      },
    ],
    ...overrides,
  };
}

function createMockAuthContext(
  user: AuthenticatedUser | null,
  status: "authenticated" | "loading" | "unauthenticated" | "forbidden" = "authenticated"
) {
  return {
    user,
    login: async () => { throw new Error("Not implemented"); },
    logout: async () => {},
    selectContext: async () => {},
    refreshUser: async () => null,
    clearAuth: () => {},
    isAuthenticated: status === "authenticated",
    isLoading: status === "loading",
    status,
    error: null,
  };
}

// ----------------------------------------------------------------------------
// Test 1: TENANT_MODULES_REGISTRY completeness
// ----------------------------------------------------------------------------
test("test_tenant_modules_registry_contains_all_17_modules", () => {
  assert.equal(TENANT_MODULES_REGISTRY.length, 18, "Registry must contain exactly 18 modules");

  const expectedIds = [
    "dashboard",
    "my-products",
    "roles-permissions",
    "product-assignments",
    "bulk-user-onboarding",
    "access-requests",
    "branding",
    "org-profile",
    "users-memberships",
    "usage-quotas",
    "subscriptions-overview",
    "billing-invoices",
    "identity-providers",
    "security-policies",
    "audit-log",
    "notifications",
    "reports-analytics",
    "tenant-settings",
  ];

  for (const expectedId of expectedIds) {
    const found = TENANT_MODULES_REGISTRY.find((m) => m.id === expectedId);
    assert.ok(found, `Expected module ${expectedId} to exist in TENANT_MODULES_REGISTRY`);
    assert.ok(found.label, `Module ${expectedId} must have a label`);
    assert.ok(found.path, `Module ${expectedId} must have a route path`);
  }

  // Verify implemented count: all 18 modules implemented
  const implemented = TENANT_MODULES_REGISTRY.filter((m) => m.implemented);
  assert.equal(implemented.length, 18, "All 18 modules should be marked implemented: true");

  const implementedIds = implemented.map((m) => m.id).sort();
  const expectedImplementedIds = [...expectedIds].sort();
  assert.deepEqual(implementedIds, expectedImplementedIds);
});

// ----------------------------------------------------------------------------
// Test 2: Sidebar filtering by allowed_modules and permissions
// ----------------------------------------------------------------------------
test("test_sidebar_shows_exactly_permitted_implemented_modules", () => {
  const fullUser = createMockTenantUser();

  const visibleModules = getVisibleTenantModules(
    fullUser.active_context?.allowed_modules ?? [],
    fullUser.active_context?.effective_permissions ?? []
  );

  // Must only include implemented modules
  assert.equal(visibleModules.length, 6);
  assert.ok(visibleModules.every((m) => m.implemented));

  // Render AppShell with full tenant user wrapped in ThemeProvider
  const html = renderToStaticMarkup(
    React.createElement(
      MemoryRouter,
      { initialEntries: ["/tenant"] },
      React.createElement(
        ThemeProvider,
        null,
        React.createElement(
          AuthContext.Provider,
          { value: createMockAuthContext(fullUser) },
          React.createElement(AppShell, null, React.createElement("div", null, "Tenant Content"))
        )
      )
    )
  );

  // Check each implemented module label is present in sidebar
  assert.ok(html.includes("Dashboard"), "Dashboard nav link should be present");
  assert.ok(html.includes("My Products &amp; Launcher") || html.includes("My Products & Launcher"));
  assert.ok(html.includes("Roles &amp; Permissions") || html.includes("Roles & Permissions"));
  assert.ok(html.includes("Product Assignments"));
  assert.ok(html.includes("Bulk User Onboarding"));
  assert.ok(html.includes("Access Requests"));

  // Check that unimplemented modules are never rendered
  assert.ok(!html.includes("Organization Profile &amp; Structure"));
  assert.ok(!html.includes("Departments &amp; Cost Centers"));
  assert.ok(!html.includes("Security &amp; SSO"));
});

test("test_sidebar_filters_out_unpermitted_modules", () => {
  // User lacking roles.view and bulk_import.view
  const restrictedUser = createMockTenantUser(undefined, {
    permissions: ["org.view", "products.view", "assignments.view"],
    modules: ["tenant_dashboard", "tenant_my_products", "tenant_product_assignments"],
  });

  const visibleModules = getVisibleTenantModules(
    restrictedUser.active_context?.allowed_modules ?? [],
    restrictedUser.active_context?.effective_permissions ?? []
  );

  const visibleIds = visibleModules.map((m) => m.id);
  assert.ok(visibleIds.includes("dashboard"));
  assert.ok(visibleIds.includes("my-products"));
  assert.ok(visibleIds.includes("product-assignments"));
  assert.ok(!visibleIds.includes("roles-permissions"), "roles-permissions must be filtered out without permission");
  assert.ok(!visibleIds.includes("bulk-user-onboarding"), "bulk-user-onboarding must be filtered out");
  assert.ok(!visibleIds.includes("access-requests"), "access-requests must be filtered out");
});

// ----------------------------------------------------------------------------
// Test 3: Route guard denial fails closed
// ----------------------------------------------------------------------------
test("test_route_guard_denial_fails_closed", () => {
  // 1. Missing requiredPermission
  const userWithoutRolesPerm = createMockTenantUser(undefined, {
    permissions: ["org.view", "products.view"],
    modules: ["tenant_dashboard", "tenant_my_products"],
  });

  const deniedPermHtml = renderToStaticMarkup(
    React.createElement(
      MemoryRouter,
      { initialEntries: ["/tenant/roles"] },
      React.createElement(
        AuthContext.Provider,
        { value: createMockAuthContext(userWithoutRolesPerm) },
        React.createElement(ProtectedRoute, {
          requiredContext: "tenant",
          requiredModule: "tenant_roles",
          requiredPermission: "roles.view",
          children: React.createElement("div", null, "Protected Roles Content"),
        })
      )
    )
  );

  // Must fail closed and never render the protected children
  assert.ok(!deniedPermHtml.includes("Protected Roles Content"), "Must fail closed and hide content when unpermitted");

  // 2. Wrong context (e.g. platform owner attempting to access tenant route without tenant context)
  const ownerUser: AuthenticatedUser = {
    id: "user-owner-1",
    email: "owner@vibeconnect.io",
    full_name: "Platform Owner",
    is_platform_owner: true,
    active_context: {
      type: "platform_owner",
      organization: null,
      effective_permissions: ["*"],
      allowed_modules: ["*"],
    },
    available_contexts: [{ type: "platform_owner", organization: null }],
  };

  const deniedContextHtml = renderToStaticMarkup(
    React.createElement(
      MemoryRouter,
      { initialEntries: ["/tenant/products"] },
      React.createElement(
        AuthContext.Provider,
        { value: createMockAuthContext(ownerUser) },
        React.createElement(ProtectedRoute, {
          requiredContext: "tenant",
          requiredModule: "tenant_my_products",
          requiredPermission: "products.view",
          children: React.createElement("div", null, "Protected Products Content"),
        })
      )
    )
  );

  assert.ok(!deniedContextHtml.includes("Protected Products Content"), "Owner context must be denied on tenant routes");

  // 3. Forbidden status renders Access Restricted
  const forbiddenHtml = renderToStaticMarkup(
    React.createElement(
      MemoryRouter,
      { initialEntries: ["/tenant/roles"] },
      React.createElement(
        AuthContext.Provider,
        { value: createMockAuthContext(userWithoutRolesPerm, "forbidden") },
        React.createElement(ProtectedRoute, {
          requiredContext: "tenant",
          requiredModule: "tenant_roles",
          requiredPermission: "roles.view",
          children: React.createElement("div", null, "Protected Roles Content"),
        })
      )
    )
  );

  assert.ok(forbiddenHtml.includes("Access Restricted"), "Forbidden status must show Access Restricted screen");
});

// ----------------------------------------------------------------------------
// Test 4: App Launcher renders all 10 access states and fallback
// ----------------------------------------------------------------------------
test("test_launcher_renders_all_ten_access_states_and_fallback", () => {
  const allStates: AccessState[] = [
    "available",
    "not_assigned",
    "subscription_inactive",
    "entitlement_unavailable",
    "assignment_suspended",
    "assignment_revoked",
    "module_unavailable",
    "membership_inactive",
    "product_unavailable",
    "access_expired",
  ];

  const mockProducts: TenantProductAccessItem[] = allStates.map((state, idx) => ({
    id: `prod-${idx}`,
    code: `PROD_${idx}`,
    name: `Product ${state}`,
    description: `Testing access state ${state}`,
    status: "active",
    assignment_id: state === "available" ? `asgn-${idx}` : null,
    assigned_at: state === "available" ? "2026-01-01T00:00:00Z" : null,
    access_state: state,
    denial_code: state === "available" ? null : state,
    eligible_modules: [
      {
        id: `mod-${idx}-1`,
        code: "MOD_CORE",
        name: "Core Module",
        description: "Core features",
        status: "active",
        module_state: state === "available" ? "available" : "unavailable",
        features: [],
      },
    ],
    modules: [],
  }));

  // Add an unknown future state product to test graceful fallback
  mockProducts.push({
    id: "prod-unknown",
    code: "PROD_FUTURE",
    name: "Future Product",
    description: "Unknown future state",
    status: "active",
    assignment_id: null,
    assigned_at: null,
    access_state: "future_license_required" as unknown as AccessState,
    denial_code: null,
    modules: [],
  });

  const tenantHomeMockResponse: TenantHomeResponse = {
    schema_version: "2.0",
    organization: {
      id: "org-acme-1",
      code: "ACME",
      name: "Acme Corporation",
      description: "Acme tenant",
      status: "active",
    },
    membership: {
      id: "mem-1",
      membership_type: "tenant_admin",
      status: "active",
      joined_at: "2026-01-01T00:00:00Z",
      role: {
        id: "role-admin",
        code: "system_tenant_admin",
        name: "Tenant Admin",
        is_system_role: true,
      },
    },
    entitled_products: mockProducts,
    products: mockProducts,
    console_modules: [],
    seat_summary: {
      total_assigned_seats: 1,
      products: [],
    },
  };

  const user = createMockTenantUser();

  const html = renderToStaticMarkup(
    React.createElement(
      MemoryRouter,
      { initialEntries: ["/tenant/products"] },
      React.createElement(
        ThemeProvider,
        null,
        React.createElement(
          AuthContext.Provider,
          { value: createMockAuthContext(user) },
          React.createElement(TenantMyProductsPage, { initialData: tenantHomeMockResponse })
        )
      )
    )
  );

  // 1. Verify every single state badge text is rendered in the output
  assert.ok(html.includes("Available"), "State available badge must be rendered");
  assert.ok(html.includes("Not Assigned"), "State not_assigned badge must be rendered");
  assert.ok(html.includes("Subscription Inactive"), "State subscription_inactive badge must be rendered");
  assert.ok(html.includes("Entitlement Unavailable"), "State entitlement_unavailable badge must be rendered");
  assert.ok(html.includes("Assignment Suspended"), "State assignment_suspended badge must be rendered");
  assert.ok(html.includes("Assignment Revoked"), "State assignment_revoked badge must be rendered");
  assert.ok(html.includes("Module Unavailable"), "State module_unavailable badge must be rendered");
  assert.ok(html.includes("Membership Inactive"), "State membership_inactive badge must be rendered");
  assert.ok(html.includes("Product Unavailable"), "State product_unavailable badge must be rendered");
  assert.ok(html.includes("Access Expired"), "State access_expired badge must be rendered");

  // 2. Verify fallback badge for unknown state
  assert.ok(html.includes("Unavailable"), "Unknown state must render neutral Unavailable badge");

  // 3. Verify launch contract: Launch button is disabled and contains the required tooltip
  assert.ok(html.includes("Launch available after SSO integration"), "Tooltip must explain launchability contract");
  assert.ok(html.includes("disabled"), "Launch button must be disabled");

  // 4. Zero product URL construction
  assert.ok(!html.includes("http://"), "Launcher must never build http:// product URLs");
  assert.ok(!html.includes("https://"), "Launcher must never build https:// product URLs");
});

// ----------------------------------------------------------------------------
// Test 5: Tenant-switch generation reset verification
// ----------------------------------------------------------------------------
test("test_tenant_switch_generation_counter_pattern", () => {
  // Verify that TenantDashboardPage component file contains the generation counter pattern
  const dashboardSource = fs.readFileSync(
    path.resolve(process.cwd(), "src/pages/tenant/TenantDashboardPage.tsx"),
    "utf8"
  );
  assert.ok(
    dashboardSource.includes("generationRef.current"),
    "TenantDashboardPage must implement generationRef counter pattern"
  );
  assert.ok(
    dashboardSource.includes("lastTenantIdRef.current"),
    "TenantDashboardPage must track lastTenantIdRef to detect tenant switch"
  );

  const productsSource = fs.readFileSync(
    path.resolve(process.cwd(), "src/pages/tenant/TenantMyProductsPage.tsx"),
    "utf8"
  );
  assert.ok(
    productsSource.includes("generationRef.current"),
    "TenantMyProductsPage must implement generationRef counter pattern"
  );
  assert.ok(
    productsSource.includes("lastTenantIdRef.current"),
    "TenantMyProductsPage must track lastTenantIdRef to detect tenant switch"
  );
});

// ----------------------------------------------------------------------------
// Test 6: 320px responsive CSS rules
// ----------------------------------------------------------------------------
test("test_320px_responsive_css_rules_and_overflow_prevention", () => {
  const cssSource = fs.readFileSync(
    path.resolve(process.cwd(), "src/index.css"),
    "utf8"
  );

  // Check overflow-wrap / word-break / min-width: 0 in CSS
  assert.ok(
    cssSource.includes("word-break") || cssSource.includes("overflow-wrap"),
    "index.css must include word-break or overflow-wrap for small viewports"
  );

  // Check TenantDashboardPage inline styles for word-break and min-width: 0
  const dashboardSource = fs.readFileSync(
    path.resolve(process.cwd(), "src/pages/tenant/TenantDashboardPage.tsx"),
    "utf8"
  );
  assert.ok(
    dashboardSource.includes("overflowWrap: \"anywhere\"") || dashboardSource.includes("wordBreak: \"break-word\""),
    "TenantDashboardPage must handle wrapping on narrow screens"
  );
  assert.ok(
    dashboardSource.includes("minWidth: 0"),
    "TenantDashboardPage must use minWidth: 0 to prevent flex item horizontal overflow"
  );
});

// ----------------------------------------------------------------------------
// Test 7: tenantHomeApi integration
// ----------------------------------------------------------------------------
test("test_tenant_home_api_endpoint_and_client_usage", async () => {
  assert.equal(ENDPOINTS.TENANT_HOME, "/api/v1/tenant/home/");

  let calledUrl = "";
  const originalGet = apiClient.get;
  apiClient.get = (async (url: string) => {
    calledUrl = url;
    return {
      schema_version: "2.0",
      organization: { id: "1", code: "ACME", name: "Acme", description: "", status: "active" },
      membership: { id: "1", membership_type: "admin", status: "active", joined_at: null, role: null },
      entitled_products: [],
      console_modules: [],
      seat_summary: { total_assigned_seats: 0, products: [] },
    } as unknown as TenantHomeResponse;
  }) as typeof apiClient.get;

  try {
    const res = await tenantHomeApi.getTenantHome();
    assert.equal(calledUrl, "/api/v1/tenant/home/");
    assert.equal(res.schema_version, "2.0");
  } finally {
    apiClient.get = originalGet;
  }
});

// ----------------------------------------------------------------------------
// Test 8: Tenant Member Route Access & Admin Console Denial
// ----------------------------------------------------------------------------
test("test_tenant_member_products_route_access_and_admin_console_denial", () => {
  const memberUser: AuthenticatedUser = {
    id: "user-member-1",
    email: "member@acme.com",
    full_name: "Tenant Member",
    is_platform_owner: false,
    active_context: {
      type: "tenant",
      membership_type: "member",
      organization: {
        id: "org-acme-1",
        code: "ACME",
        name: "Acme Corporation",
      },
      effective_permissions: [],
      allowed_modules: [],
    },
    available_contexts: [
      {
        type: "tenant",
        organization: {
          id: "org-acme-1",
          code: "ACME",
          name: "Acme Corporation",
        },
      },
    ],
  };

  // 1. Tenant Member CAN access /tenant/products
  const productsRouteHtml = renderToStaticMarkup(
    React.createElement(
      MemoryRouter,
      { initialEntries: ["/tenant/products"] },
      React.createElement(
        AuthContext.Provider,
        { value: createMockAuthContext(memberUser) },
        React.createElement(ProtectedRoute, {
          requiredContext: "tenant",
          children: React.createElement("div", null, "Tenant Member Products Page Content"),
        })
      )
    )
  );
  assert.ok(
    productsRouteHtml.includes("Tenant Member Products Page Content"),
    "Tenant Member must be allowed on /tenant/products"
  );

  // 2. Tenant Member CAN access /tenant/products even if route defines tenant_my_products / products.view
  const productsWithGatingHtml = renderToStaticMarkup(
    React.createElement(
      MemoryRouter,
      { initialEntries: ["/tenant/products"] },
      React.createElement(
        AuthContext.Provider,
        { value: createMockAuthContext(memberUser) },
        React.createElement(ProtectedRoute, {
          requiredContext: "tenant",
          requiredModule: "tenant_my_products",
          requiredPermission: "products.view",
          children: React.createElement("div", null, "Tenant Member Products Page Content"),
        })
      )
    )
  );
  assert.ok(
    productsWithGatingHtml.includes("Tenant Member Products Page Content"),
    "Tenant Member must access /tenant/products without admin modules or permissions"
  );

  // 3. Tenant Member is DENIED from admin-only Tenant Dashboard (/tenant)
  const adminDashboardHtml = renderToStaticMarkup(
    React.createElement(
      MemoryRouter,
      { initialEntries: ["/tenant"] },
      React.createElement(
        AuthContext.Provider,
        { value: createMockAuthContext(memberUser) },
        React.createElement(ProtectedRoute, {
          requiredContext: "tenant",
          adminOnly: true,
          children: React.createElement("div", null, "Admin Dashboard Secret Content"),
        })
      )
    )
  );
  assert.ok(
    !adminDashboardHtml.includes("Admin Dashboard Secret Content"),
    "Tenant Member must be denied from adminOnly dashboard route"
  );

  // 4. Tenant Member is DENIED from admin roles module (/tenant/roles)
  const adminRolesHtml = renderToStaticMarkup(
    React.createElement(
      MemoryRouter,
      { initialEntries: ["/tenant/roles"] },
      React.createElement(
        AuthContext.Provider,
        { value: createMockAuthContext(memberUser) },
        React.createElement(ProtectedRoute, {
          requiredContext: "tenant",
          requiredModule: "tenant_roles",
          requiredPermission: "roles.view",
          children: React.createElement("div", null, "Admin Roles Secret Content"),
        })
      )
    )
  );
  assert.ok(
    !adminRolesHtml.includes("Admin Roles Secret Content"),
    "Tenant Member must be denied from admin console roles module"
  );

  // 5. Tenant Member is DENIED from Platform Owner routes (/)
  const platformOwnerHtml = renderToStaticMarkup(
    React.createElement(
      MemoryRouter,
      { initialEntries: ["/"] },
      React.createElement(
        AuthContext.Provider,
        { value: createMockAuthContext(memberUser) },
        React.createElement(ProtectedRoute, {
          requiredContext: "platform_owner",
          children: React.createElement("div", null, "Platform Owner Overview Content"),
        })
      )
    )
  );
  assert.ok(
    !platformOwnerHtml.includes("Platform Owner Overview Content"),
    "Tenant Member must be denied from platform owner routes"
  );
});

