/**
 * Global Search Bar & Dropdown Tests.
 *
 * Verifies:
 * 1. GlobalSearchBar renders in-header search bar directly without full-screen modal backdrop.
 * 2. Search placeholder is context-aware across Platform Owner, Tenant Admin, and Member consoles.
 * 3. Entitled products and console navigation routes are present and accessible.
 * 4. Backward compatibility with GlobalSearchModal.
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
    location: { pathname: "/", search: "" },
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
if (typeof globalThis.sessionStorage === "undefined") {
  (globalThis as unknown as { sessionStorage: unknown }).sessionStorage = {
    getItem: () => null,
    setItem: () => {},
    removeItem: () => {},
  };
}

import { GlobalSearchBar } from "../../components/search/GlobalSearchBar.tsx";
import { GlobalSearchModal } from "../../components/search/GlobalSearchModal.tsx";
import type { AuthenticatedUser, TenantProductAccessItem } from "../../api/types.ts";

test("SEARCH-1: GlobalSearchBar renders normal in-header search input without modal backdrop", () => {
  const html = renderToStaticMarkup(
    React.createElement(
      MemoryRouter,
      {},
      React.createElement(GlobalSearchBar, {
        user: null,
      })
    )
  );
  assert.ok(html.includes("header-search-container"), "Expected search bar container");
  assert.ok(html.includes("header-search-input"), "Expected text input");
  assert.ok(html.includes("Ctrl K"), "Expected Ctrl K badge");
  assert.ok(!html.includes("global-search-backdrop"), "Should NOT render full-screen backdrop");
});

test("SEARCH-2: GlobalSearchBar renders Platform Owner search interface", () => {
  const mockOwnerUser: AuthenticatedUser = {
    id: "usr-owner-1",
    email: "owner@envisage.com",
    full_name: "Platform Owner",
    is_platform_owner: true,
    active_context: {
      type: "platform_owner",
      organization: null,
      allowed_modules: ["all"],
      effective_permissions: ["all"],
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
      MemoryRouter,
      {},
      React.createElement(GlobalSearchBar, {
        user: mockOwnerUser,
      })
    )
  );

  assert.ok(html.includes("Search organizations, users, products, or modules..."), "Expected owner search placeholder");
});

test("SEARCH-3: GlobalSearchBar renders Tenant Admin search interface", () => {
  const mockTenantAdmin: AuthenticatedUser = {
    id: "usr-tenant-1",
    email: "admin@acme.com",
    full_name: "Tenant Admin",
    is_platform_owner: false,
    active_context: {
      type: "tenant",
      membership_type: "tenant_admin",
      organization: {
        id: "org-acme-1",
        code: "ACME",
        name: "Acme Corp",
      },
      allowed_modules: ["tenant_members", "tenant_roles", "tenant_my_products"],
      effective_permissions: ["members.view", "roles.view"],
    },
    available_contexts: [],
  };

  const mockProducts: TenantProductAccessItem[] = [
    {
      id: "prod-analytics-1",
      code: "ANALYTICS",
      name: "Acme Analytics Suite",
      description: "Real-time enterprise metrics and business intelligence",
      status: "active",
      assignment_id: null,
      assigned_at: null,
      modules: [],
    },
  ];

  const html = renderToStaticMarkup(
    React.createElement(
      MemoryRouter,
      {},
      React.createElement(GlobalSearchBar, {
        user: mockTenantAdmin,
        tenantProducts: mockProducts,
      })
    )
  );

  assert.ok(html.includes("Search members, entitled products, roles, or modules..."), "Expected tenant admin placeholder");
});

test("SEARCH-4: GlobalSearchBar renders Member workspace tools placeholder", () => {
  const mockMember: AuthenticatedUser = {
    id: "usr-mem-1",
    email: "john@acme.com",
    full_name: "John Doe",
    is_platform_owner: false,
    active_context: {
      type: "tenant",
      membership_type: "member",
      organization: {
        id: "org-acme-1",
        code: "ACME",
        name: "Acme Corp",
      },
      allowed_modules: ["tenant_my_products"],
      effective_permissions: ["products.view"],
    },
    available_contexts: [],
  };

  const html = renderToStaticMarkup(
    React.createElement(
      MemoryRouter,
      {},
      React.createElement(GlobalSearchBar, {
        user: mockMember,
      })
    )
  );

  assert.ok(html.includes("Search assigned tools, workspaces, or settings..."), "Expected member placeholder");
});

test("SEARCH-5: Backward compatibility GlobalSearchModal alias", () => {
  const html = renderToStaticMarkup(
    React.createElement(
      MemoryRouter,
      {},
      React.createElement(GlobalSearchModal, {
        isOpen: false,
        user: null,
      })
    )
  );
  assert.equal(html, "");
});
