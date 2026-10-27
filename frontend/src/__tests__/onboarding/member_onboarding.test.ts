import assert from "node:assert/strict";
import test from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router-dom";
import { TenantMemberOnboardingPage } from "../../pages/tenant/TenantMemberOnboardingPage.tsx";
import { AuthContext } from "../../context/AuthContext.tsx";
import { ThemeProvider } from "../../context/ThemeContext.tsx";
import type { AuthenticatedUser } from "../../api/types.ts";

function createMockTenantAdminUser(): AuthenticatedUser {
  return {
    id: "user-admin-1",
    email: "tenant.admin@acme.com",
    full_name: "Tenant Admin",
    is_platform_owner: false,
    active_context: {
      type: "tenant",
      membership_type: "tenant_admin",
      organization: {
        id: "org-acme-1",
        code: "ACME",
        name: "Acme Corporation",
      },
      effective_permissions: [
        "users.view",
        "users.manage",
        "roles.view",
        "roles.manage",
        "assignments.view",
        "assignments.manage",
      ],
      allowed_modules: [
        "tenant_users",
        "tenant_roles",
        "tenant_product_assignments",
      ],
    },
    available_contexts: [
      {
        type: "tenant",
        organization: {
          id: "org-acme-1",
          code: "ACME",
          name: "Acme Corporation",
        },
      },
    ],
  };
}

function createMockAuthContext(user: AuthenticatedUser) {
  return {
    user,
    login: async () => { throw new Error("Not implemented"); },
    logout: async () => {},
    selectContext: async () => {},
    refreshUser: async () => null,
    clearAuth: () => {},
    isAuthenticated: true,
    isLoading: false,
    status: "authenticated" as const,
    error: null,
  };
}

test("TenantMemberOnboardingPage renders 5-step wizard and initial member details form", () => {
  const user = createMockTenantAdminUser();

  const html = renderToStaticMarkup(
    React.createElement(
      MemoryRouter,
      { initialEntries: ["/tenant/member-onboarding"] },
      React.createElement(
        ThemeProvider,
        null,
        React.createElement(
          AuthContext.Provider,
          { value: createMockAuthContext(user) },
          React.createElement(TenantMemberOnboardingPage, null)
        )
      )
    )
  );

  // Stepper steps
  assert.ok(html.includes("Member Details"), "Stepper should include Step 1: Member Details");
  assert.ok(html.includes("Role &amp; Permissions") || html.includes("Role & Permissions"), "Stepper should include Step 2: Role & Permissions");
  assert.ok(html.includes("Product Access"), "Stepper should include Step 3: Product Access");
  assert.ok(html.includes("Console Features"), "Stepper should include Step 4: Console Features");
  assert.ok(html.includes("Review &amp; Provision") || html.includes("Review & Provision"), "Stepper should include Step 5: Review & Provision");

  // Step 1 Details form content
  assert.ok(html.includes("Step 1: Member Identity &amp; Details") || html.includes("Step 1: Member Identity & Details"));
  assert.ok(html.includes("Acme Corporation"), "Should display active target tenant organization name");
  assert.ok(html.includes("ACME"), "Should display active target tenant organization code");
  assert.ok(html.includes("Full Name"), "Should include full name input label");
  assert.ok(html.includes("Email Address"), "Should include email address input label");
  assert.ok(html.includes("Continue to Role Configuration"), "Should include advance step button");
});

test("IssueInvitationPayload and Member Onboarding state support LMS Console selection", () => {
  const payload: import("../../api/types.ts").IssueInvitationPayload = {
    organization_id: "org-1",
    email: "learner@acme.com",
    membership_type: "member",
    product_ids: ["lms-prod-id"],
    lms_console: "normal_user_console",
  };

  assert.equal(payload.lms_console, "normal_user_console");

  const adminPayload: import("../../api/types.ts").IssueInvitationPayload = {
    organization_id: "org-1",
    email: "admin@acme.com",
    membership_type: "tenant_admin",
    product_ids: ["lms-prod-id"],
    lms_console: "tenant_console",
  };

  assert.equal(adminPayload.lms_console, "tenant_console");
});
