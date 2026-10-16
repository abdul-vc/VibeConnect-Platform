/**
 * Integration Hub Frontend Tests (Phase 5A + 5B).
 *
 * Acceptance criteria:
 *   AC-FE-1: IntegrationHubPage renders the page heading and empty state.
 *   AC-FE-2: ExternalMappingsPage renders the instance selector and heading.
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
    location: { pathname: "/integration", search: "" },
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
import { IntegrationHubPage } from "../../pages/owner/IntegrationHubPage.tsx";
import { ExternalMappingsPage } from "../../pages/owner/ExternalMappingsPage.tsx";

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
  login: async (_payload) => { throw new Error("Not implemented"); },
  logout: async () => {},
  selectContext: async () => {},
  refreshUser: async () => null,
  status: "authenticated" as const,
  error: null,
};

function wrap(node: React.ReactElement, path = "/integration") {
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

test("AC-FE-1: IntegrationHubPage renders heading and empty state", () => {
  const html = wrap(React.createElement(IntegrationHubPage, null));
  assert.ok(html.includes("Integration Hub"), "Page must include 'Integration Hub' heading");
  // In SSR with no API responses, empty-state text is rendered
  assert.ok(
    html.includes("No connectors registered yet") || html.includes("Loading integration hub"),
    "Must render loading or empty state"
  );
});

test("AC-FE-2: ExternalMappingsPage renders heading and instance selector", () => {
  const html = wrap(React.createElement(ExternalMappingsPage, null), "/integration/mappings");
  assert.ok(html.includes("External Identity Mappings"), "Page must include 'External Identity Mappings' heading");
  assert.ok(
    html.includes("instance-select") || html.includes("Connector Instance"),
    "Must render the connector instance selector"
  );
});
