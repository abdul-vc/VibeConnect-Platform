/**
 * Reports & Dashboards Frontend Acceptance Tests (Phase 4F).
 *
 * Acceptance Criteria:
 * - One frontend test each for:
 *   1. owner page renders
 *   2. tenant page renders
 *   3. nav visibility
 */

import test from "node:test";
import assert from "node:assert/strict";
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
    location: { pathname: "/reports", search: "" },
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
    documentElement: {
      setAttribute: () => {},
      style: {
        setProperty: () => {},
      },
    },
    activeElement: null,
    addEventListener: () => {},
    removeEventListener: () => {},
    getElementById: () => null,
  };
}
if (typeof globalThis.localStorage === "undefined") {
  (globalThis as unknown as { localStorage: unknown }).localStorage = {
    getItem: () => null,
    setItem: () => {},
    removeItem: () => {},
  };
}

import { TENANT_MODULES_REGISTRY } from "../../config/tenantModules.ts";
import { AppShell } from "../../components/AppShell.tsx";
import { AuthContext } from "../../context/AuthContext.tsx";
import type { AuthContextType } from "../../context/AuthContext.tsx";
import { ThemeProvider } from "../../context/ThemeContext.tsx";
import type { AuthenticatedUser } from "../../api/types.ts";
import { ReportsPage } from "../../pages/owner/ReportsPage.tsx";
import { TenantReportsPage } from "../../pages/tenant/TenantReportsPage.tsx";

test("AC-1: Owner reports page renders successfully", () => {
  const ownerUser: AuthenticatedUser = {
    id: "user-owner-1",
    email: "owner@vibeconnect.io",
    full_name: "Platform Owner",
    is_platform_owner: true,
    active_context: {
      type: "platform_owner",
      organization: null,
      allowed_modules: [],
      effective_permissions: [],
    },
    available_contexts: [
      {
        type: "platform_owner",
        organization: null,
      },
    ],
  };

  const mockAuthContext: AuthContextType = {
    user: ownerUser,
    login: async (_payload) => {
      throw new Error("Not implemented");
    },
    logout: async () => {},
    selectContext: async () => {},
    refreshUser: async () => null,
    status: "authenticated" as const,
    error: null,
  };

  const html = renderToStaticMarkup(
    React.createElement(
      MemoryRouter,
      { initialEntries: ["/reports"] },
      React.createElement(
        ThemeProvider,
        null,
        React.createElement(
          AuthContext.Provider,
          { value: mockAuthContext },
          React.createElement(ReportsPage, null)
        )
      )
    )
  );

  assert.ok(html.includes("Platform Reports &amp; Analytics"), "Owner reports heading must render");
});

test("AC-2: Tenant reports page renders successfully", () => {
  const tenantUser: AuthenticatedUser = {
    id: "user-tenant-admin-1",
    email: "admin@apex.internal",
    full_name: "Apex Administrator",
    is_platform_owner: false,
    active_context: {
      type: "tenant",
      organization: {
        id: "org-apex-1",
        code: "apex",
        name: "Apex Dynamics",
      },
      allowed_modules: ["tenant_reports"],
      effective_permissions: ["reports.view"],
    },
    available_contexts: [
      {
        type: "tenant",
        organization: {
          id: "org-apex-1",
          code: "apex",
          name: "Apex Dynamics",
        },
      },
    ],
  };

  const mockAuthContext: AuthContextType = {
    user: tenantUser,
    login: async (_payload) => {
      throw new Error("Not implemented");
    },
    logout: async () => {},
    selectContext: async () => {},
    refreshUser: async () => null,
    status: "authenticated" as const,
    error: null,
  };

  const html = renderToStaticMarkup(
    React.createElement(
      MemoryRouter,
      { initialEntries: ["/tenant/reports"] },
      React.createElement(
        ThemeProvider,
        null,
        React.createElement(
          AuthContext.Provider,
          { value: mockAuthContext },
          React.createElement(TenantReportsPage, null)
        )
      )
    )
  );

  assert.ok(html.includes("Operational Reports"), "Tenant reports heading must render");
});

test("AC-3: Navigation visibility for Owner and Tenant reports", () => {
  // 1. Owner Nav
  const ownerUser: AuthenticatedUser = {
    id: "user-owner-1",
    email: "owner@vibeconnect.io",
    full_name: "Platform Owner",
    is_platform_owner: true,
    active_context: {
      type: "platform_owner",
      organization: null,
      allowed_modules: [],
      effective_permissions: [],
    },
    available_contexts: [
      {
        type: "platform_owner",
        organization: null,
      },
    ],
  };

  const ownerHtml = renderToStaticMarkup(
    React.createElement(
      MemoryRouter,
      { initialEntries: ["/reports"] },
      React.createElement(
        ThemeProvider,
        null,
        React.createElement(
          AuthContext.Provider,
          {
            value: {
              user: ownerUser,
              login: async (_payload: import("../../api/types.ts").LoginPayload) => {
                throw new Error("Not implemented");
              },
              logout: async () => {},
              selectContext: async () => {},
              refreshUser: async () => null,
              status: "authenticated" as const,
              error: null,
            } satisfies AuthContextType,
          },
          React.createElement(AppShell, null, React.createElement("div", null, "Inner"))
        )
      )
    )
  );

  assert.ok(
    ownerHtml.includes("Advanced Analytics, Adoption &amp; Tenant Health") ||
    ownerHtml.includes("Advanced Analytics, Adoption & Tenant Health") ||
    ownerHtml.includes("Reports &amp; Analytics") ||
    ownerHtml.includes("Reports & Analytics"),
    "AppShell must contain Reports link for owner"
  );
  assert.ok(
    ownerHtml.includes('aria-label="Advanced Analytics, Adoption &amp; Tenant Health"') ||
    ownerHtml.includes('aria-label="Advanced Analytics, Adoption & Tenant Health"') ||
    ownerHtml.includes('aria-label="Reports &amp; Analytics"') ||
    ownerHtml.includes('aria-label="Reports & Analytics"'),
    "Owner nav button must have aria-label for Reports"
  );

  // 2. Tenant Nav with permission
  const tenantUser: AuthenticatedUser = {
    id: "user-tenant-1",
    email: "admin@apex.internal",
    full_name: "Apex Admin",
    is_platform_owner: false,
    active_context: {
      type: "tenant",
      organization: {
        id: "org-apex-1",
        code: "apex",
        name: "Apex Dynamics",
      },
      allowed_modules: ["tenant_reports"],
      effective_permissions: ["reports.view"],
    },
    available_contexts: [
      {
        type: "tenant",
        organization: {
          id: "org-apex-1",
          code: "apex",
          name: "Apex Dynamics",
        },
      },
    ],
  };

  const tenantHtml = renderToStaticMarkup(
    React.createElement(
      MemoryRouter,
      { initialEntries: ["/tenant/reports"] },
      React.createElement(
        ThemeProvider,
        null,
        React.createElement(
          AuthContext.Provider,
          {
            value: {
              user: tenantUser,
              login: async (_payload: import("../../api/types.ts").LoginPayload) => {
                throw new Error("Not implemented");
              },
              logout: async () => {},
              selectContext: async () => {},
              refreshUser: async () => null,
              status: "authenticated" as const,
              error: null,
            } satisfies AuthContextType,
          },
          React.createElement(AppShell, null, React.createElement("div", null, "Inner"))
        )
      )
    )
  );

  assert.ok(
    !tenantHtml.includes("Advanced Analytics, Adoption &amp; Tenant Health") &&
    !tenantHtml.includes("Advanced Analytics, Adoption & Tenant Health"),
    "Tenant nav must not render Reports & Analytics when hidden from tenant console"
  );

  // 3. Verify tenant registry entry is commented out / hidden from tenant console
  const reportsModule = TENANT_MODULES_REGISTRY.find((m) => m.id === "reports-analytics");
  assert.strictEqual(reportsModule, undefined, "reports-analytics module must be hidden from tenant registry");
});
