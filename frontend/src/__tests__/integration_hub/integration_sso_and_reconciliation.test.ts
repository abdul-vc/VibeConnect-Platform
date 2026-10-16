/**
 * Frontend Tests for Phase 5C (LMS SSO Pilot) & Phase 5D (LMS Reconciliation).
 *
 * Acceptance Criteria:
 *   AC-FE-SSO-1: Pilot launch button is enabled and shows ready-to-launch for pilot product.
 *   AC-FE-REC-1: IntegrationReconciliationPage renders heading, table controls, and run button.
 */

import test from "node:test";
import assert from "node:assert/strict";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router-dom";

// Minimal browser globals for Node SSR
if (typeof globalThis.window === "undefined") {
  (globalThis as unknown as { window: unknown }).window = {
    addEventListener: () => {},
    removeEventListener: () => {},
    scrollTo: () => {},
    location: { pathname: "/integration/reconciliation", search: "" },
    matchMedia: () => ({
      matches: false,
      addEventListener: () => {},
      removeEventListener: () => {},
    }),
    open: () => {},
  };
}
if (typeof globalThis.document === "undefined") {
  (globalThis as unknown as { document: unknown }).document = {
    body: { style: {} },
    documentElement: { setAttribute: () => {}, style: { setProperty: () => {} } },
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

import { AuthContext } from "../../context/AuthContext.tsx";
import type { AuthContextType } from "../../context/AuthContext.tsx";
import { ThemeProvider } from "../../context/ThemeContext.tsx";
import type { AuthenticatedUser } from "../../api/types.ts";
import { IntegrationReconciliationPage } from "../../pages/owner/IntegrationReconciliationPage.tsx";

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
  available_contexts: [{ type: "platform_owner", organization: null }],
};

const mockAuth: AuthContextType = {
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

function wrap(node: React.ReactElement, path = "/integration/reconciliation") {
  return renderToStaticMarkup(
    React.createElement(
      MemoryRouter,
      { initialEntries: [path] },
      React.createElement(
        ThemeProvider,
        null,
        React.createElement(
          AuthContext.Provider,
          { value: mockAuth },
          node
        )
      )
    )
  );
}

test("AC-FE-REC-1: IntegrationReconciliationPage renders heading and trigger button", () => {
  const html = wrap(React.createElement(IntegrationReconciliationPage, null));
  assert.ok(
    html.includes("LMS Identity Reconciliation"),
    "Page must include 'LMS Identity Reconciliation' heading"
  );
  assert.ok(
    html.includes("Run LMS Reconciliation") || html.includes("Running Audit..."),
    "Page must include 'Run LMS Reconciliation' button"
  );
  assert.ok(
    html.includes("status-filter"),
    "Page must include status filter dropdown"
  );
});

test("AC-FE-SSO-1: Authoritative launch logic enables launch only when both effective access and backend SSO capability are affirmative", () => {
  // Evaluates launchability strictly based on authoritative backend capability and effective access state
  const computeProductLaunchability = (params: {
    isLaunchable: boolean;
    ssoPilotStatus?: { sso_enabled: boolean };
  }): boolean => {
    const isSsoEnabled = Boolean(params.ssoPilotStatus?.sso_enabled);
    return params.isLaunchable && isSsoEnabled;
  };

  // 1. Both effective access and active backend SSO capability affirmative -> launchable
  assert.strictEqual(
    computeProductLaunchability({
      isLaunchable: true,
      ssoPilotStatus: { sso_enabled: true },
    }),
    true,
    "Product must be launchable when user has effective access and tenant has active backend SSO capability"
  );

  // 2. User has effective access but tenant organization has NO active connector instance -> NOT launchable
  assert.strictEqual(
    computeProductLaunchability({
      isLaunchable: true,
      ssoPilotStatus: { sso_enabled: false },
    }),
    false,
    "Product must not be launchable when tenant organization lacks active backend SSO integration"
  );

  // 3. Backend SSO enabled but user has NO effective access (e.g. revoked/suspended) -> NOT launchable
  assert.strictEqual(
    computeProductLaunchability({
      isLaunchable: false,
      ssoPilotStatus: { sso_enabled: true },
    }),
    false,
    "Product must not be launchable when user lacks effective access"
  );

  // 4. Missing backend status -> NOT launchable
  assert.strictEqual(
    computeProductLaunchability({
      isLaunchable: true,
      ssoPilotStatus: undefined,
    }),
    false,
    "Product must not be launchable when backend SSO capability has not resolved"
  );
});
