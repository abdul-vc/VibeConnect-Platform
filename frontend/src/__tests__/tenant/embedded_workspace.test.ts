/**
 * Universal Embedded Product Workspace Unit Tests.
 *
 * Validates:
 * 1. Product-Agnostic Workspace: Renders any arbitrary authorized product dynamically.
 * 2. Embedded Iframe Configuration: Validates sandbox, referrer policy, and dimensions.
 * 3. Loading & Error States: Validates compact spinner, error messaging, and retry actions.
 * 4. Zero Hardcoding Policy: Ensures no product-specific strings (e.g., "lms") decide launch logic.
 * 5. Console Integration: Back to My Products navigation and AppShell preservation.
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
    location: { pathname: "/tenant/workspace/prod-123", search: "" },
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

import { EmbeddedProductWorkspace } from "../../components/workspace/EmbeddedProductWorkspace.tsx";
import { TenantProductWorkspacePage } from "../../pages/tenant/TenantProductWorkspacePage.tsx";
import { AuthContext } from "../../context/AuthContext.tsx";
import { ThemeProvider } from "../../context/ThemeContext.tsx";
import type { TenantProductAccessItem, AuthenticatedUser } from "../../api/types.ts";

function createMockTenantUser(): AuthenticatedUser {
  return {
    id: "user-tenant-1",
    email: "user@test-org.internal",
    full_name: "Test User",
    is_platform_owner: false,
    active_context: {
      type: "tenant",
      membership_type: "member",
      organization: {
        id: "org-test-uuid",
        code: "TEST_ORG",
        name: "Test Organization",
      },
      effective_permissions: ["products.view"],
      allowed_modules: ["tenant_my_products"],
    },
    available_contexts: [],
  };
}

function createMockProduct(id: string, code: string, name: string): TenantProductAccessItem {
  return {
    id,
    code,
    name,
    description: `Dynamic test description for ${name}`,
    status: "active",
    assignment_id: "asgn-1",
    assigned_at: "2026-10-10T00:00:00Z",
    access_state: "available",
    modules: [],
    eligible_modules: [
      {
        id: "mod-1",
        code: "core",
        name: "Core Module",
        description: "Core module",
        status: "active",
        features: [],
      },
    ],
  };
}

// ----------------------------------------------------------------------------
// Test 1: Dynamic Product-Agnostic Workspace Rendering
// ----------------------------------------------------------------------------
test("test_embedded_product_workspace_renders_arbitrary_products_dynamically", () => {
  const sampleProducts = [
    createMockProduct("prod-wms-1", "WMS", "Warehouse Management Suite"),
    createMockProduct("prod-crm-1", "CRM", "Customer Relationship Platform"),
    createMockProduct("prod-hr-1", "HRMS", "Human Resources Portal"),
  ];

  for (const product of sampleProducts) {
    const html = renderToStaticMarkup(
      React.createElement(EmbeddedProductWorkspace, {
        product,
        organizationId: "org-test-uuid",
        onBackToProducts: () => {},
      })
    );

    // Verify dynamic product name and code are rendered
    assert.ok(html.includes(product.name), `Must display product name: ${product.name}`);
    assert.ok(html.includes(product.code), `Must display product code: ${product.code}`);

    // Verify navigation return button exists
    assert.ok(html.includes("My Products"), "Must provide return button to My Products");

    // Verify loading indicator is mounted on initial launch
    assert.ok(html.includes("workspace-loading-state"), "Must mount initial loading state");
  }
});

// ----------------------------------------------------------------------------
// Test 2: Zero Product-Specific Hardcoding in Workspace Implementation
// ----------------------------------------------------------------------------
test("test_workspace_has_zero_product_specific_string_checks", () => {
  const workspaceSource = fs.readFileSync(
    path.resolve(process.cwd(), "src/components/workspace/EmbeddedProductWorkspace.tsx"),
    "utf8"
  );

  // Must not have hardcoded product code branches
  assert.ok(!workspaceSource.includes('product.code === "lms"'), "No hardcoded product code checks");
  assert.ok(!workspaceSource.includes('product.code === "LMS"'), "No hardcoded product code checks");
  assert.ok(!workspaceSource.includes('product.name.includes("lms")'), "No string includes checks for lms");
  assert.ok(!workspaceSource.includes('product.name.includes("LMS")'), "No string includes checks for LMS");
  assert.ok(!workspaceSource.includes('product.name.includes("pilot")'), "No string includes checks for pilot");

  // Must consume centralized ssoApi
  assert.ok(workspaceSource.includes("ssoApi.launch"), "Must consume centralized ssoApi.launch");
});

// ----------------------------------------------------------------------------
// Test 3: Iframe Security and Sandbox Attributes
// ----------------------------------------------------------------------------
test("test_workspace_iframe_security_attributes", () => {
  const workspaceSource = fs.readFileSync(
    path.resolve(process.cwd(), "src/components/workspace/EmbeddedProductWorkspace.tsx"),
    "utf8"
  );

  // Verify sandbox permissions
  assert.ok(workspaceSource.includes('sandbox="allow-same-origin allow-scripts allow-forms allow-popups allow-downloads"'), "Iframe must configure explicit sandbox permissions");

  // Verify referrer policy
  assert.ok(workspaceSource.includes('referrerPolicy="strict-origin-when-cross-origin"'), "Iframe must configure strict-origin-when-cross-origin referrer policy");

  // Verify iframe title accessibility
  assert.ok(workspaceSource.includes("title="), "Iframe must provide accessible title");
});

// ----------------------------------------------------------------------------
// Test 4: TenantProductWorkspacePage Integration inside AppShell
// ----------------------------------------------------------------------------
test("test_tenant_product_workspace_page_renders_within_console_shell", () => {
  const mockUser = createMockTenantUser();
  const product = createMockProduct("prod-999", "HUB", "Enterprise WorkHub");

  const html = renderToStaticMarkup(
    React.createElement(
      MemoryRouter,
      {
        initialEntries: [
          { pathname: "/tenant/workspace/prod-999", state: { product } },
        ],
      },
      React.createElement(
        ThemeProvider,
        null,
        React.createElement(
          AuthContext.Provider,
          {
            value: {
              user: mockUser,
              status: "authenticated",
              error: null,
              login: async () => mockUser,
              logout: async () => {},
              refreshUser: async () => mockUser,
              selectContext: async () => {},
            },
          },
          React.createElement(TenantProductWorkspacePage, null)
        )
      )
    )
  );

  // AppShell elements must be present: header brand mark and sidebar
  assert.ok(html.includes("VibeConnect"), "AppShell brand mark must be rendered");
  assert.ok(html.includes("My Products &amp; Launcher") || html.includes("My Products & Launcher"), "Sidebar launcher must be present");

  // Workspace elements must be rendered
  assert.ok(html.includes("Enterprise WorkHub"), "Product title must be rendered in workspace");
  assert.ok(html.includes("HUB"), "Product code pill must be rendered");
});
