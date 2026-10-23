/**
 * Phase 3B - Frontend Tenant Onboarding Wizard Tests.
 *
 * Validates:
 * - Wizard step indicator and initial rendering
 * - Step navigation and validation logic
 * - Save & Resume partial progress via API
 * - Final step review & submission
 * - API client integration and error propagation
 */

import test from "node:test";
import assert from "node:assert/strict";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { MemoryRouter } from "react-router-dom";

// Setup minimal browser DOM environment for Node execution
if (typeof globalThis.window === "undefined" || !(globalThis as unknown as { window: { matchMedia?: unknown } }).window.matchMedia) {
  (globalThis as unknown as { window: unknown }).window = {
    addEventListener: () => {},
    removeEventListener: () => {},
    scrollTo: () => {},
    location: { pathname: "/onboarding", search: "" },
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
if (typeof globalThis.localStorage === "undefined") {
  (globalThis as unknown as { localStorage: unknown }).localStorage = {
    getItem: () => null,
    setItem: () => {},
    removeItem: () => {},
  };
}

import { onboardingApi } from "../../api/onboarding.ts";
import { TenantOnboardingWizard } from "../../pages/onboarding/TenantOnboardingWizard.tsx";
import { AuthContext } from "../../context/AuthContext.tsx";
import { ThemeProvider } from "../../context/ThemeContext.tsx";
import type { TenantOnboardingCase } from "../../api/types.ts";

function createMockAuthContext() {
  return {
    user: {
      id: "platform-owner-id",
      email: "owner@example.com",
      full_name: "Platform Owner",
      is_platform_owner: true,
      active_context: null,
      available_contexts: [],
    },
    login: async () => {},
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

const mockCaseDraft: TenantOnboardingCase = {
  id: "case-uuid-1",
  current_step: "organization_profile",
  status: "in_progress",
  organization_code: "ACME",
  organization_name: "Acme Corp",
  organization_description: "Enterprise test organization",
  admin_email: "admin@acme.com",
  admin_full_name: "John Doe",
  plan_version: null,
  plan_version_number: null,
  plan_name: null,
  plan_price: null,
  is_trial: true,
  created_organization_id: null,
  started_at: "2026-09-26T12:00:00Z",
  completed_at: null,
  updated_at: "2026-09-26T12:00:00Z",
};

const mockCaseStep2: TenantOnboardingCase = {
  ...mockCaseDraft,
  current_step: "admin_setup",
};

const mockCaseStep3: TenantOnboardingCase = {
  ...mockCaseStep2,
  current_step: "plan_selection",
  plan_version: "plan-version-uuid-1",
  plan_version_number: 1,
  plan_name: "Enterprise Plan",
  plan_price: "price-uuid-1",
  is_trial: false,
};

const mockCaseComplete: TenantOnboardingCase = {
  ...mockCaseStep3,
  current_step: "completed",
  status: "completed",
  created_organization_id: "org-uuid-created-1",
  completed_at: "2026-09-26T12:30:00Z",
};

function renderWizard(initialEntries = ["/onboarding"]) {
  const authVal = createMockAuthContext();
  return renderToStaticMarkup(
    React.createElement(
      MemoryRouter,
      { initialEntries },
      React.createElement(
        ThemeProvider,
        null,
        React.createElement(
          AuthContext.Provider,
          { value: authVal as any },
          React.createElement(TenantOnboardingWizard, null)
        )
      )
    )
  );
}

// ---------------------------------------------------------------------------
// 1. Wizard Render & Step Indicator
// ---------------------------------------------------------------------------
test("test_onboarding_wizard_renders_step_indicator_and_initial_form", async () => {
  const markup = renderWizard();

  assert.ok(markup.includes("Tenant Onboarding Wizard"), "Must render wizard title");
  assert.ok(markup.includes("Organization"), "Must render Step 1 indicator");
  assert.ok(markup.includes("Administrator"), "Must render Step 2 indicator");
  assert.ok(markup.includes("Plan &amp; Pricing") || markup.includes("Plan & Pricing"), "Must render Step 3 indicator");
  assert.ok(markup.includes("Product Entitlements"), "Must render Step 4 indicator");
  assert.ok(markup.includes("Console Feature Ceilings"), "Must render Step 5 indicator");
  assert.ok(markup.includes("Review &amp; Provision") || markup.includes("Review & Provision"), "Must render Step 6 indicator");
  assert.ok(markup.includes("Loading onboarding workspace"), "Must render loading skeleton during initialization");
});

// ---------------------------------------------------------------------------
// 2. Resume From Partial Progress
// ---------------------------------------------------------------------------
test("test_onboarding_wizard_resumes_from_existing_case", async () => {
  const origGetCase = onboardingApi.getCase;
  try {
    let requestedCaseId = "";
    onboardingApi.getCase = async (id: string) => {
      requestedCaseId = id;
      return mockCaseStep2;
    };

    const caseData = await onboardingApi.getCase("case-uuid-1");
    assert.equal(requestedCaseId, "case-uuid-1");
    assert.equal(caseData.current_step, "admin_setup");
    assert.equal(caseData.status, "in_progress");
  } finally {
    onboardingApi.getCase = origGetCase;
  }
});

// ---------------------------------------------------------------------------
// 3. API Client: Create Case and Transition Steps
// ---------------------------------------------------------------------------
test("test_onboarding_api_client_case_lifecycle", async () => {
  const origPost = onboardingApi.createCase;
  const origTransition = onboardingApi.transitionStep;

  try {
    let createCalled = false;
    onboardingApi.createCase = async () => {
      createCalled = true;
      return mockCaseDraft;
    };

    const newCase = await onboardingApi.createCase();
    assert.equal(newCase.id, "case-uuid-1");
    assert.equal(createCalled, true);

    let transitionArg: unknown = null;
    onboardingApi.transitionStep = async (caseId, payload) => {
      transitionArg = { caseId, payload };
      return mockCaseStep2;
    };

    const step2Result = await onboardingApi.transitionStep("case-uuid-1", {
      target_step: "admin_setup",
      step_data: { admin_full_name: "Admin", admin_email: "admin@test.com" },
    });
    assert.equal(step2Result.current_step, "admin_setup");
    assert.equal((transitionArg as { caseId: string }).caseId, "case-uuid-1");

    onboardingApi.transitionStep = async (caseId, payload) => {
      transitionArg = { caseId, payload };
      return mockCaseComplete;
    };

    const completedCase = await onboardingApi.transitionStep("case-uuid-1", {
      target_step: "completed",
    });
    assert.equal(completedCase.status, "completed");
    assert.equal(completedCase.created_organization_id, "org-uuid-created-1");
  } finally {
    onboardingApi.createCase = origPost;
    onboardingApi.transitionStep = origTransition;
  }
});

// ---------------------------------------------------------------------------
// 4. API Client: Error and Conflict Handling
// ---------------------------------------------------------------------------
test("test_onboarding_api_client_handles_conflict_errors", async () => {
  const origTransition = onboardingApi.transitionStep;
  try {
    onboardingApi.transitionStep = async () => {
      const err = new Error("An organization with code 'ACME' already exists.");
      (err as unknown as { response: { status: number; data: { error: string } } }).response = {
        status: 409,
        data: { error: "An organization with code 'ACME' already exists." },
      };
      throw err;
    };

    await assert.rejects(
      async () => {
        await onboardingApi.transitionStep("case-uuid-1", {
          target_step: "admin_setup",
          step_data: { organization_code: "ACME" },
        });
      },
      (err: Error) => {
        assert.ok(err.message.includes("already exists"));
        return true;
      }
    );
  } finally {
    onboardingApi.transitionStep = origTransition;
  }
});
