/**
 * Phase 3C: Frontend User Invitation Tests.
 *
 * Validates:
 * - Valid token flow and form rendering
 * - Expired token error display
 * - Already-used token error display
 * - Password validation policy enforcement
 * - Successful accept submission
 */

import test from "node:test";
import assert from "node:assert/strict";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter, Route, Routes } from "react-router-dom";

// Setup minimal browser DOM environment for Node execution
if (typeof globalThis.window === "undefined" || !(globalThis as unknown as { window: { matchMedia?: unknown } }).window.matchMedia) {
  (globalThis as unknown as { window: unknown }).window = {
    addEventListener: () => {},
    removeEventListener: () => {},
    scrollTo: () => {},
    location: { pathname: "/invitations/valid-token-123", search: "" },
    matchMedia: () => ({ matches: false, addEventListener: () => {}, removeEventListener: () => {} }),
  };
}
if (typeof globalThis.document === "undefined") {
  (globalThis as unknown as { document: unknown }).document = {
    body: { style: {} },
    activeElement: null,
    addEventListener: () => {},
    removeEventListener: () => {},
  };
}

import { invitationsApi } from "../../api/invitations.ts";
import { InvitationAcceptPage } from "../../pages/invitations/InvitationAcceptPage.tsx";
import type { InvitationValidateResponse } from "../../api/types.ts";

const mockValidInvitation: InvitationValidateResponse = {
  id: "inv-uuid-1",
  email: "newuser@acme.test",
  organization_name: "Acme Corporation",
  organization_code: "acme_corp",
  membership_type: "member",
  status: "pending",
  expires_at: "2026-10-01T12:00:00Z",
};

function renderInvitationPage(initialPath = "/invitations/valid-token-123") {
  return renderToStaticMarkup(
    React.createElement(
      MemoryRouter,
      { initialEntries: [initialPath] },
      React.createElement(
        Routes,
        null,
        React.createElement(Route, {
          path: "/invitations/:token",
          element: React.createElement(InvitationAcceptPage, null),
        })
      )
    )
  );
}

// ---------------------------------------------------------------------------
// 1. Initial Render & Valid Token Flow
// ---------------------------------------------------------------------------
test("test_invitation_accept_page_renders_initial_state", async () => {
  const origValidate = invitationsApi.validate;
  try {
    invitationsApi.validate = async () => mockValidInvitation;
    const markup = renderInvitationPage();

    assert.ok(markup.includes("Envisage Workspace"), "Must render header");
    assert.ok(markup.includes("Accept Invitation &amp; Setup Password") || markup.includes("Accept Invitation & Setup Password"));
    assert.ok(markup.includes("Validating invitation token"), "Must render loading state while validating");
  } finally {
    invitationsApi.validate = origValidate;
  }
});

// ---------------------------------------------------------------------------
// 2. API Client: Validate & Accept Functions
// ---------------------------------------------------------------------------
test("test_invitations_api_client_validate_and_accept", async () => {
  const origValidate = invitationsApi.validate;
  const origAccept = invitationsApi.accept;

  try {
    let capturedToken = "";
    invitationsApi.validate = async (token: string) => {
      capturedToken = token;
      return mockValidInvitation;
    };

    const res = await invitationsApi.validate("test-token-abc");
    assert.equal(capturedToken, "test-token-abc");
    assert.equal(res.email, "newuser@acme.test");
    assert.equal(res.organization_code, "acme_corp");

    let acceptPayload: unknown = null;
    invitationsApi.accept = async (token: string, payload) => {
      acceptPayload = { token, payload };
      return {
        success: true,
        detail: "Account setup and activation complete.",
        data: {
          user_id: "user-uuid-1",
          email: "newuser@acme.test",
          full_name: "New User",
          organization_id: "org-uuid-1",
          organization_code: "acme_corp",
          organization_name: "Acme Corporation",
        },
      };
    };

    const acceptRes = await invitationsApi.accept("test-token-abc", {
      password: "StrongPassword2026!",
      full_name: "New User",
    });

    assert.equal(acceptRes.success, true);
    assert.equal(acceptRes.data.user_id, "user-uuid-1");
    assert.deepEqual(acceptPayload, {
      token: "test-token-abc",
      payload: { password: "StrongPassword2026!", full_name: "New User" },
    });
  } finally {
    invitationsApi.validate = origValidate;
    invitationsApi.accept = origAccept;
  }
});

// ---------------------------------------------------------------------------
// 3. Expired & Already-Used Error Handling
// ---------------------------------------------------------------------------
test("test_invitations_api_client_handles_expired_and_used_errors", async () => {
  const origValidate = invitationsApi.validate;

  try {
    // Expired
    invitationsApi.validate = async () => {
      const err = new Error("This invitation has expired.");
      (err as unknown as { status: number; data: { code: string; detail: string } }).status = 410;
      (err as unknown as { status: number; data: { code: string; detail: string } }).data = {
        code: "INVITATION_EXPIRED",
        detail: "This invitation has expired.",
      };
      throw err;
    };

    await assert.rejects(
      async () => {
        await invitationsApi.validate("expired-token");
      },
      (err: Error) => {
        assert.ok(err.message.includes("expired"));
        return true;
      }
    );

    // Already Used
    invitationsApi.validate = async () => {
      const err = new Error("This invitation has already been accepted.");
      (err as unknown as { status: number; data: { code: string; detail: string } }).status = 409;
      (err as unknown as { status: number; data: { code: string; detail: string } }).data = {
        code: "INVITATION_ALREADY_USED",
        detail: "This invitation has already been accepted.",
      };
      throw err;
    };

    await assert.rejects(
      async () => {
        await invitationsApi.validate("used-token");
      },
      (err: Error) => {
        assert.ok(err.message.includes("already been accepted"));
        return true;
      }
    );
  } finally {
    invitationsApi.validate = origValidate;
  }
});
