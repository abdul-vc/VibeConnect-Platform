/**
 * Billing & Invoices Frontend Acceptance Tests (Phase 4D).
 *
 * Minimal test suite meeting Acceptance Criteria:
 * 1. Owner invoice list renders
 * 2. Tenant invoice view renders (read-only, no mutation actions)
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
    location: { pathname: "/billing", search: "" },
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
import { BillingPage } from "../../pages/owner/BillingPage.tsx";
import { TenantBillingPage } from "../../pages/tenant/TenantBillingPage.tsx";

test("AC-1: Owner invoice list renders successfully", () => {
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
          { initialEntries: ["/billing"] },
          React.createElement(BillingPage)
        )
      )
    )
  );

  assert.ok(html.includes("Billing &amp; Invoices") || html.includes("Billing & Invoices"), "Owner billing page must render hero heading");
  assert.ok(html.includes("Invoices"), "Owner billing page must render Invoices tab");
  assert.ok(html.includes("Billing Accounts"), "Owner billing page must render Billing Accounts tab");
});

test("AC-2: Tenant invoice view renders (read-only, no mutation actions)", () => {
  const tenantUser: AuthenticatedUser = {
    id: "user-tenant-1",
    email: "tenant@vibeconnect.io",
    full_name: "Tenant Admin",
    is_platform_owner: false,
    active_context: {
      type: "tenant",
      organization: { id: "org-1", code: "ACME", name: "Acme Corp" },
      allowed_modules: ["tenant_billing"],
      effective_permissions: ["billing.view"],
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
          { initialEntries: ["/tenant/billing"] },
          React.createElement(TenantBillingPage)
        )
      )
    )
  );

  assert.ok(html.includes("Billing &amp; Invoices") || html.includes("Billing & Invoices"), "Tenant billing page must render title");
  assert.ok(html.includes("Invoices History"), "Tenant billing page must render Invoices History");
  // Verify strictly read-only: no create invoice, edit invoice, delete invoice buttons
  assert.ok(!html.includes("Create Invoice"), "Tenant billing must NOT have Create Invoice action");
  assert.ok(!html.includes("Delete Invoice"), "Tenant billing must NOT have Delete Invoice action");
});

test("AC-3: Navigation visibility for billing in owner nav and tenant registry", () => {
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
          { initialEntries: ["/billing"] },
          React.createElement(AppShell, null, React.createElement("div", null, "Content"))
        )
      )
    )
  );

  assert.ok(ownerHtml.includes("Billing &amp; Invoices") || ownerHtml.includes("Billing & Invoices"), "Owner nav must include Billing & Invoices");

  // 2. Verify tenant registry entry
  const billingModule = TENANT_MODULES_REGISTRY.find((m) => m.id === "billing-invoices");
  assert.ok(billingModule, "TENANT_MODULES_REGISTRY must contain billing-invoices module");
  assert.strictEqual(billingModule?.requiredModule, "tenant_billing");
  assert.strictEqual(billingModule?.requiredPermission, "billing.view");
  assert.strictEqual(billingModule?.implemented, true);
});
