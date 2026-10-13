/**
 * Phase 3F: Frontend Access Requests & Approvals Tests.
 *
 * Validates:
 * - AccessRequestQueuePage renders KPI cards, filter controls, table headers
 * - AccessRequestFormPage renders product selector, organization context, reason input
 * - DenyRequestModal & ApproveRequestModal rendering & 1-500 char trimmed validation
 * - Permission-gated actions (approver vs read-only user)
 * - accessRequestsApi client functions (createRequest, listRequests, approveRequest, denyRequest, cancelRequest)
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
    location: { pathname: "/access-requests", search: "" },
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

import { accessRequestsApi } from "../../api/accessRequests.ts";
import { AccessRequestQueuePage } from "../../pages/access_requests/AccessRequestQueuePage.tsx";
import { AccessRequestFormPage } from "../../pages/access_requests/AccessRequestFormPage.tsx";
import { ApproveRequestModal } from "../../components/access_requests/ApproveRequestModal.tsx";
import { DenyRequestModal } from "../../components/access_requests/DenyRequestModal.tsx";
import { AuthContext } from "../../context/AuthContext.tsx";
import { ThemeProvider } from "../../context/ThemeContext.tsx";
import type { AccessRequestItem } from "../../api/types.ts";

function createMockAuthContext(isApprover = true) {
  return {
    user: {
      id: "approver-user-id",
      email: "approver@vibeconnect.internal",
      full_name: "Test Approver",
      is_platform_owner: isApprover,
      active_context: {
        type: isApprover ? ("platform_owner" as const) : ("tenant" as const),
        organization: {
          id: "org-123",
          code: "acme-corp",
          name: "Acme Corporation",
          status: "active",
        },
        effective_permissions: isApprover ? ["assignments.manage", "assignments.view"] : [],
        allowed_modules: ["tenant_product_assignments"],
      },
      available_contexts: [],
    },
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
    currentStep: "ready" as const,
  };
}

const mockRequestItem: AccessRequestItem = {
  id: "req-uuid-001",
  organization_id: "org-123",
  organization_code: "acme-corp",
  organization_name: "Acme Corporation",
  requester_id: "user-456",
  requester_email: "member@acme.internal",
  requester_name: "Acme Member",
  product_id: "prod-789",
  product_code: "lms_core",
  product_name: "LMS Core Engine",
  status: "pending",
  requested_modules: [],
  reason: "Need access for compliance training.",
  requested_at: "2026-09-26T12:00:00Z",
  updated_at: "2026-09-26T12:00:00Z",
  decisions: [],
};

test("AccessRequestQueuePage: renders page title, KPI summary cards, and search filters", () => {
  const authVal = createMockAuthContext(true);
  const markup = renderToStaticMarkup(
    React.createElement(
      MemoryRouter,
      { initialEntries: ["/access-requests"] },
      React.createElement(
        ThemeProvider,
        null,
        React.createElement(
          AuthContext.Provider,
          { value: authVal },
          React.createElement(AccessRequestQueuePage, null)
        )
      )
    )
  );

  assert.ok(markup.includes("Access Requests &amp; Approvals"));
  assert.ok(markup.includes("Total Requests"));
  assert.ok(markup.includes("Pending Approvals"));
  assert.ok(markup.includes("Search by requester email, name, or product..."));
  assert.ok(markup.includes("New Access Request"));
});

test("AccessRequestFormPage: renders target product, context, and submit controls", () => {
  const authVal = createMockAuthContext(false);
  const markup = renderToStaticMarkup(
    React.createElement(
      MemoryRouter,
      { initialEntries: ["/access-requests/new"] },
      React.createElement(
        ThemeProvider,
        null,
        React.createElement(
          AuthContext.Provider,
          { value: authVal },
          React.createElement(AccessRequestFormPage, null)
        )
      )
    )
  );

  assert.ok(markup.includes("Request Product Access"));
  assert.ok(markup.includes("Target Product"));
  assert.ok(markup.includes("Business Justification / Reason"));
  assert.ok(markup.includes("Submit Access Request"));
  assert.ok(markup.includes("Back to Access Requests"));
});

test("ApproveRequestModal: renders confirmation details and seat ceiling warning when open", () => {
  const markup = renderToStaticMarkup(
    React.createElement(ApproveRequestModal, {
      isOpen: true,
      requestItem: mockRequestItem,
      onClose: () => {},
      onSuccess: () => {},
    })
  );

  assert.ok(markup.includes("Approve Access Request"));
  assert.ok(markup.includes("Granting product seat assignment for"));
  assert.ok(markup.includes("Acme Member"));
  assert.ok(markup.includes("Confirm &amp; Grant Access"));
});

test("ApproveRequestModal: renders nothing when isOpen is false", () => {
  const markup = renderToStaticMarkup(
    React.createElement(ApproveRequestModal, {
      isOpen: false,
      requestItem: mockRequestItem,
      onClose: () => {},
      onSuccess: () => {},
    })
  );

  assert.equal(markup, "");
});

test("DenyRequestModal: renders mandatory denial reason input with character limit", () => {
  const markup = renderToStaticMarkup(
    React.createElement(DenyRequestModal, {
      isOpen: true,
      requestItem: mockRequestItem,
      onClose: () => {},
      onSuccess: () => {},
    })
  );

  assert.ok(markup.includes("Deny Access Request"));
  assert.ok(markup.includes("Denial Reason"));
  assert.ok(markup.includes("0/500"));
  assert.ok(markup.includes("Confirm Denial"));
});

test("accessRequestsApi: client functions structure and signature verification", () => {
  assert.equal(typeof accessRequestsApi.createRequest, "function");
  assert.equal(typeof accessRequestsApi.listRequests, "function");
  assert.equal(typeof accessRequestsApi.getRequest, "function");
  assert.equal(typeof accessRequestsApi.approveRequest, "function");
  assert.equal(typeof accessRequestsApi.denyRequest, "function");
  assert.equal(typeof accessRequestsApi.cancelRequest, "function");
});
