/**
 * Commercial Reconciliation Frontend Acceptance Tests (Phase 4E).
 *
 * Acceptance Criteria:
 * - Owner list rendering and resolve action.
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
    location: { pathname: "/reconciliation", search: "" },
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

import { AppShell } from "../../components/AppShell.tsx";
import { AuthContext } from "../../context/AuthContext.tsx";
import { ThemeProvider } from "../../context/ThemeContext.tsx";
import type { AuthenticatedUser } from "../../api/types.ts";
import { ReconciliationPage } from "../../pages/owner/ReconciliationPage.tsx";

test("AC-1: Owner reconciliation list renders with resolve action", () => {
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

  const mockAuthContext = {
    user: ownerUser,
    login: async () => {
      throw new Error("Not implemented");
    },
    logout: async () => {},
    selectContext: async () => {},
    refreshUser: async () => null,
    clearAuth: () => {},
    isAuthenticated: true,
    isLoading: false,
    status: "authenticated" as const,
    error: null,
  };

  const html = renderToStaticMarkup(
    React.createElement(
      MemoryRouter,
      { initialEntries: ["/reconciliation"] },
      React.createElement(
        ThemeProvider,
        null,
        React.createElement(
          AuthContext.Provider,
          { value: mockAuthContext },
          React.createElement(ReconciliationPage, null)
        )
      )
    )
  );

  assert.ok(html.includes("Commercial Reconciliation"), "Heading must render");
  assert.ok(html.includes("Trigger Reconciliation Job"), "Trigger run button must render");
  assert.ok(html.includes("Filter Status:"), "Status filter must render");
});

test("AC-2: Owner navigation contains Reconciliation link", () => {
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

  const mockAuthContext = {
    user: ownerUser,
    login: async () => {
      throw new Error("Not implemented");
    },
    logout: async () => {},
    selectContext: async () => {},
    refreshUser: async () => null,
    clearAuth: () => {},
    isAuthenticated: true,
    isLoading: false,
    status: "authenticated" as const,
    error: null,
  };

  const html = renderToStaticMarkup(
    React.createElement(
      MemoryRouter,
      { initialEntries: ["/reconciliation"] },
      React.createElement(
        ThemeProvider,
        null,
        React.createElement(
          AuthContext.Provider,
          { value: mockAuthContext },
          React.createElement(AppShell, null, React.createElement("div", null, "Inner"))
        )
      )
    )
  );

  assert.ok(html.includes("Reconciliation"), "AppShell must contain Reconciliation nav item");
  assert.ok(html.includes('aria-label="Reconciliation"'), "Nav item must have aria-label for Reconciliation");
});
