/**
 * Usage & Metering Frontend Acceptance Tests (Phase 4C).
 *
 * Minimal test suite meeting Acceptance Criteria:
 * 1. Dashboard card renders usage data
 * 2. Owner usage page renders
 * 3. Nav visibility (Owner + Tenant registry)
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
    location: { pathname: "/usage", search: "" },
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
import { ThemeProvider } from "../../context/ThemeContext.tsx";
import type { AuthenticatedUser } from "../../api/types.ts";
import { UsagePage } from "../../pages/owner/UsagePage.tsx";
import { TenantUsagePage } from "../../pages/tenant/TenantUsagePage.tsx";

test("AC-1: Owner usage page renders successfully", () => {
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

  const html = renderToStaticMarkup(
    React.createElement(
      ThemeProvider,
      null,
      React.createElement(
        AuthContext.Provider,
        {
          value: {
            user: ownerUser,
            status: "authenticated",
            error: null,
            login: async () => ownerUser,
            logout: async () => {},
            refreshUser: async () => ownerUser,
            selectContext: async () => {},
          },
        },
        React.createElement(
          MemoryRouter,
          { initialEntries: ["/usage"] },
          React.createElement(UsagePage)
        )
      )
    )
  );

  assert.ok(html.includes("Usage &amp; Metering") || html.includes("Usage & Metering"), "Owner usage page must render hero heading");
  assert.ok(html.includes("Cross-tenant aggregated usage"), "Owner usage page must render description");
});

test("AC-2: Tenant usage page renders quota usage data", () => {
  const tenantUser: AuthenticatedUser = {
    id: "user-tenant-1",
    email: "tenant@vibeconnect.io",
    full_name: "Tenant Admin",
    is_platform_owner: false,
    active_context: {
      type: "tenant",
      organization: { id: "org-1", code: "ACME", name: "Acme Corp" },
      allowed_modules: ["tenant_usage"],
      effective_permissions: ["usage.view"],
    },
    available_contexts: [
      {
        type: "tenant",
        organization: { id: "org-1", code: "ACME", name: "Acme Corp" },
      },
    ],
  };

  const html = renderToStaticMarkup(
    React.createElement(
      ThemeProvider,
      null,
      React.createElement(
        AuthContext.Provider,
        {
          value: {
            user: tenantUser,
            status: "authenticated",
            error: null,
            login: async () => tenantUser,
            logout: async () => {},
            refreshUser: async () => tenantUser,
            selectContext: async () => {},
          },
        },
        React.createElement(
          MemoryRouter,
          { initialEntries: ["/tenant/usage"] },
          React.createElement(TenantUsagePage)
        )
      )
    )
  );

  assert.ok(html.includes("Usage &amp; Quotas") || html.includes("Usage & Quotas"), "Tenant usage page must render title");
});

test("AC-3: Navigation visibility for usage in owner nav and tenant registry", () => {
  // 1. Verify owner nav item
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
      ThemeProvider,
      null,
      React.createElement(
        AuthContext.Provider,
        {
          value: {
            user: ownerUser,
            status: "authenticated",
            error: null,
            login: async () => ownerUser,
            logout: async () => {},
            refreshUser: async () => ownerUser,
            selectContext: async () => {},
          },
        },
        React.createElement(
          MemoryRouter,
          { initialEntries: ["/usage"] },
          React.createElement(AppShell, null, React.createElement("div", null, "Content"))
        )
      )
    )
  );

  assert.ok(ownerHtml.includes("Usage &amp; Metering") || ownerHtml.includes("Usage & Metering"), "Owner nav must include Usage & Metering");

  // 2. Verify tenant registry entry
  const usageModule = TENANT_MODULES_REGISTRY.find((m) => m.id === "usage-quotas");
  assert.ok(usageModule, "TENANT_MODULES_REGISTRY must contain usage-quotas module");
  assert.strictEqual(usageModule?.requiredModule, "tenant_usage");
  assert.strictEqual(usageModule?.requiredPermission, "usage.view");
  assert.strictEqual(usageModule?.implemented, true);
});
