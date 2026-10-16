/**
 * Branding Frontend Acceptance Tests (Phase 4A/4B).
 *
 * Minimal test suite meeting Acceptance Criteria:
 * 1. Editor save (draft save with allowlisted tokens)
 * 2. Publish (publishes revision)
 * 3. Rollback (creates new revision copy)
 * 4. Nav visibility (White Labeling in Owner nav, Branding in Tenant nav)
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
    location: { pathname: "/white-labeling", search: "" },
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

import { brandingApi } from "../../api/branding.ts";
import { apiClient } from "../../api/client.ts";
import { ENDPOINTS } from "../../api/endpoints.ts";
import { TENANT_MODULES_REGISTRY } from "../../config/tenantModules.ts";
import { AppShell } from "../../components/AppShell.tsx";
import { AuthContext } from "../../context/AuthContext.tsx";
import type { AuthenticatedUser } from "../../api/types.ts";

test("AC-1: editor save sends allowlisted tokens to draft revision endpoint", async () => {
  let capturedUrl = "";
  let capturedPayload: unknown = null;

  const originalPost = apiClient.post;
  apiClient.post = (async <T,>(url: string, data?: unknown): Promise<T> => {
    capturedUrl = url;
    capturedPayload = data;
    return {
      id: "rev-draft-1",
      profile: "prof-1",
      revision_number: 1,
      status: "draft",
      tokens: (data as { tokens: Record<string, string> }).tokens,
      change_summary: (data as { change_summary: string }).change_summary,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    } as unknown as T;
  }) as typeof apiClient.post;

  try {
    const tokens = {
      brand_primary: "#4f46e5",
      brand_primary_hover: "#4338ca",
      bg_app: "#0a0e17",
    };
    const res = await brandingApi.saveDraft("prof-1", {
      tokens,
      change_summary: "Updated brand colors",
    });

    assert.strictEqual(capturedUrl, ENDPOINTS.BRANDING.REVISIONS("prof-1"));
    assert.deepStrictEqual((capturedPayload as { tokens: Record<string, string> }).tokens, tokens);
    assert.strictEqual(res.status, "draft");
    assert.strictEqual(res.revision_number, 1);
  } finally {
    apiClient.post = originalPost;
  }
});

test("AC-2: publish transitions revision to published status", async () => {
  let capturedUrl = "";

  const originalPost = apiClient.post;
  apiClient.post = (async <T,>(url: string): Promise<T> => {
    capturedUrl = url;
    return {
      id: "rev-draft-1",
      profile: "prof-1",
      revision_number: 1,
      status: "published",
      tokens: { brand_primary: "#4f46e5" },
      published_at: new Date().toISOString(),
      published_by: "user-1",
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    } as unknown as T;
  }) as typeof apiClient.post;

  try {
    const res = await brandingApi.publishRevision("rev-draft-1");
    assert.strictEqual(capturedUrl, ENDPOINTS.BRANDING.PUBLISH("rev-draft-1"));
    assert.strictEqual(res.status, "published");
    assert.ok(res.published_at);
  } finally {
    apiClient.post = originalPost;
  }
});

test("AC-3: rollback creates a new revision copy from target revision", async () => {
  let capturedUrl = "";

  const originalPost = apiClient.post;
  apiClient.post = (async <T,>(url: string): Promise<T> => {
    capturedUrl = url;
    return {
      id: "rev-rollback-2",
      profile: "prof-1",
      revision_number: 2,
      status: "published",
      tokens: { brand_primary: "#6366f1" },
      change_summary: "Rollback to revision #1",
      published_at: new Date().toISOString(),
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    } as unknown as T;
  }) as typeof apiClient.post;

  try {
    const res = await brandingApi.rollbackRevision("rev-target-1");
    assert.strictEqual(capturedUrl, ENDPOINTS.BRANDING.ROLLBACK("rev-target-1"));
    assert.strictEqual(res.revision_number, 2, "Rollback creates new revision copy");
    assert.strictEqual(res.status, "published");
  } finally {
    apiClient.post = originalPost;
  }
});

import { ThemeProvider } from "../../context/ThemeContext.tsx";

test("AC-4: nav visibility displays White Labeling in owner nav and Branding in tenant nav", () => {
  // 1. Verify owner nav renders "White Labeling"
  const ownerUser: AuthenticatedUser = {
    id: "user-owner",
    email: "owner@vibeconnect.io",
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
          { initialEntries: ["/white-labeling"] },
          React.createElement(AppShell, null, React.createElement("div", null, "Owner Content"))
        )
      )
    )
  );

  assert.ok(
    ownerHtml.includes("White Labeling"),
    "Owner navigation must contain 'White Labeling'"
  );

  // 2. Verify tenant registry entry and navigation
  const brandingModule = TENANT_MODULES_REGISTRY.find((m) => m.id === "branding");
  assert.ok(brandingModule, "TENANT_MODULES_REGISTRY must contain branding module");
  assert.strictEqual(brandingModule?.requiredModule, "tenant_branding");
  assert.strictEqual(brandingModule?.requiredPermission, "branding.view");
  assert.strictEqual(brandingModule?.implemented, true);

  const tenantUser: AuthenticatedUser = {
    id: "user-tenant",
    email: "tenant@vibeconnect.io",
    full_name: "Tenant Admin",
    is_platform_owner: false,
    active_context: {
      type: "tenant",
      organization: { id: "org-1", code: "ORG", name: "Org 1" },
      allowed_modules: ["tenant_dashboard", "tenant_branding"],
      effective_permissions: ["org.view", "branding.view"],
    },
    available_contexts: [
      {
        type: "tenant",
        organization: { id: "org-1", code: "ORG", name: "Org 1" },
      },
    ],
  };

  const tenantHtml = renderToStaticMarkup(
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
          { initialEntries: ["/tenant/branding"] },
          React.createElement(AppShell, null, React.createElement("div", null, "Tenant Content"))
        )
      )
    )
  );

  assert.ok(
    tenantHtml.includes("Branding"),
    "Tenant navigation must contain 'Branding' when user has tenant_branding and branding.view"
  );
});
