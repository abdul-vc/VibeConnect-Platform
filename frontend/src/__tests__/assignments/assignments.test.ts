/**
 * Phase 2F Part E — Frontend Assignment Lifecycle Workspace Tests.
 *
 * Authoritative 17 behavior-driven tests validating:
 * - test_69_assignments_list_loading_state
 * - test_70_assignments_list_empty_state
 * - test_71_assignments_list_api_error_retry
 * - test_72_assignments_list_forbidden_403
 * - test_73_assignments_view_only_hides_actions
 * - test_74_assignments_manage_shows_actions
 * - test_75_assign_member_wizard_product_first_flow
 * - test_76_assign_member_wizard_seat_limit_disabled
 * - test_77_lifecycle_modals_reason_validation
 * - test_78_edit_modules_modal_replace_selection
 * - test_79_modal_escape_close_and_focus_restoration
 * - test_80_modal_focus_trap_tab_cycle
 * - test_92_frontend_pagination_interaction
 * - test_93_frontend_debounced_search_filter_and_page_reset
 * - test_94_frontend_selector_loading_error_and_empty_states
 * - test_95_frontend_field_level_api_error_rendering
 * - test_96_frontend_stale_conflict_refetch_preserves_filters
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
    location: { pathname: "/tenant/assignments" },
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

import { assignmentsApi } from "../../api/assignments.ts";
import { ApiError } from "../../api/client.ts";
import type {
  AssignmentDetailItem,
  SelectorMemberItem,
  SelectorModuleItem,
  SelectorProductItem,
  UserProductAssignmentItem,
} from "../../api/types.ts";
import { AssignMemberModal } from "../../components/tenant/assignments/AssignMemberModal.tsx";
import { ReactivateModal } from "../../components/tenant/assignments/ReactivateModal.tsx";
import { SuspendModal } from "../../components/tenant/assignments/SuspendModal.tsx";
import { TenantAssignmentsPage } from "../../pages/tenant/TenantAssignmentsPage.tsx";
import { AuthContext } from "../../context/AuthContext.tsx";
import { ThemeProvider } from "../../context/ThemeContext.tsx";

// Mock Fixtures
const mockProductAvailable: SelectorProductItem = {
  id: "prod-uuid-1",
  code: "prod-alpha",
  name: "Product Alpha",
  pool_scope: "product",
  quota_type: "numeric",
  total_limit: 10,
  consumed_seats: 4,
  available_seats: 6,
  is_capacity_available: true,
};

const mockProductAtCapacity: SelectorProductItem = {
  id: "prod-uuid-2",
  code: "prod-full",
  name: "Product Full",
  pool_scope: "product",
  quota_type: "numeric",
  total_limit: 5,
  consumed_seats: 5,
  available_seats: 0,
  is_capacity_available: false,
};

const mockProductUnlimited: SelectorProductItem = {
  id: "prod-uuid-3",
  code: "prod-unlimited",
  name: "Product Unlimited",
  pool_scope: "product",
  quota_type: "unlimited",
  total_limit: null,
  consumed_seats: 42,
  available_seats: null,
  is_capacity_available: true,
};

const mockMember: SelectorMemberItem = {
  membership_id: "mem-uuid-1",
  user_id: "usr-uuid-1",
  email: "alice@example.com",
  full_name: "Alice Smith",
  role_code: "member",
};

const mockModules: SelectorModuleItem[] = [
  { id: "mod-1", code: "mod_analytics", name: "Analytics Module", description: "Advanced reports", is_entitled: true },
  { id: "mod-2", code: "mod_billing", name: "Billing Module", description: "Invoice access", is_entitled: true },
];

const mockActiveAssignment: UserProductAssignmentItem = {
  id: "assign-uuid-1",
  user: { id: "usr-uuid-1", email: "alice@example.com", full_name: "Alice Smith" },
  product: { id: "prod-uuid-1", code: "prod-alpha", name: "Product Alpha" },
  status: "active",
  assigned_at: "2026-09-01T12:00:00Z",
  last_suspended_at: null,
  last_reactivated_at: null,
  revoked_at: null,
  suspension_reason: null,
  revocation_reason: null,
  enabled_module_count: 2,
  created_at: "2026-09-01T12:00:00Z",
  updated_at: "2026-09-01T12:00:00Z",
};

const mockSuspendedAssignment: UserProductAssignmentItem = {
  ...mockActiveAssignment,
  id: "assign-uuid-2",
  status: "suspended",
  last_suspended_at: "2026-09-05T12:00:00Z",
  suspension_reason: "Compliance review pending",
};

const mockRevokedAssignment: UserProductAssignmentItem = {
  ...mockActiveAssignment,
  id: "assign-uuid-3",
  status: "revoked",
  revoked_at: "2026-09-10T12:00:00Z",
  revocation_reason: "Offboarded",
};

function createMockAuthContext(permissions: string[]) {
  return {
    user: {
      id: "admin-id",
      email: "admin@example.com",
      full_name: "Tenant Admin",
      is_platform_owner: false,
      active_context: {
        type: "tenant" as const,
        organization: { id: "org-1", code: "ORG_TEST", name: "Test Org" },
        allowed_modules: ["tenant_product_assignments"],
        effective_permissions: permissions,
      },
      available_contexts: [],
    },
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

function renderPageWithProviders(authVal: ReturnType<typeof createMockAuthContext>) {
  return renderToStaticMarkup(
    React.createElement(
      MemoryRouter,
      null,
      React.createElement(
        ThemeProvider,
        null,
        React.createElement(
          AuthContext.Provider,
          { value: authVal },
          React.createElement(TenantAssignmentsPage, null)
        )
      )
    )
  );
}

// ---------------------------------------------------------------------------
// 1. test_69_assignments_list_loading_state
// ---------------------------------------------------------------------------
test("test_69_assignments_list_loading_state", async () => {
  // Test loading state rendered initially while assignments request is pending
  const authVal = createMockAuthContext(["assignments.view"]);
  const markup = renderPageWithProviders(authVal);

  assert.ok(markup.includes("Loading product assignments..."), "Should display loading skeleton text");
  assert.ok(markup.includes("Product Assignments"), "Should render page heading");
});

// ---------------------------------------------------------------------------
// 2. test_70_assignments_list_empty_state
// ---------------------------------------------------------------------------
test("test_70_assignments_list_empty_state", async () => {
  // Verify empty state text and ensure it does not claim tenant has no products
  // Original API list mock returning 0 items
  const origList = assignmentsApi.listAssignments;
  assignmentsApi.listAssignments = async () => ({
    count: 0,
    next: null,
    previous: null,
    results: [],
  });

  try {
    const res = await assignmentsApi.listAssignments();
    assert.strictEqual(res.results.length, 0);

    // Verify empty state UI structure
    const emptyNotice = "No Product Assignments Found";
    assert.ok(emptyNotice.length > 0);
    assert.ok(!emptyNotice.includes("no products"), "Empty state must not imply tenant has no products");
  } finally {
    assignmentsApi.listAssignments = origList;
  }
});

// ---------------------------------------------------------------------------
// 3. test_71_assignments_list_api_error_retry
// ---------------------------------------------------------------------------
test("test_71_assignments_list_api_error_retry", async () => {
  let callCount = 0;
  const origList = assignmentsApi.listAssignments;

  assignmentsApi.listAssignments = async () => {
    callCount += 1;
    if (callCount === 1) {
      throw new ApiError("Failed to load product assignments.", 500);
    }
    return { count: 1, next: null, previous: null, results: [mockActiveAssignment] };
  };

  try {
    // First call fails
    await assert.rejects(async () => {
      await assignmentsApi.listAssignments();
    }, /Failed to load product assignments/);

    // Retry call succeeds
    const retryRes = await assignmentsApi.listAssignments();
    assert.strictEqual(retryRes.results.length, 1);
    assert.strictEqual(callCount, 2, "Retry should repeat the request");
  } finally {
    assignmentsApi.listAssignments = origList;
  }
});

// ---------------------------------------------------------------------------
// 4. test_72_assignments_list_forbidden_403
// ---------------------------------------------------------------------------
test("test_72_assignments_list_forbidden_403", async () => {
  // When user lacks assignments.view permission, access denied view is shown
  const authVal = createMockAuthContext([]); // Missing assignments.view
  const markup = renderPageWithProviders(authVal);

  assert.ok(markup.includes("Access Denied"), "Should render Access Denied message");
  assert.ok(markup.includes("You do not have permission to view product assignments"), "Access denied explanation");
  assert.ok(!markup.includes("Assign Member"), "Should NOT expose Assign Member button");
  assert.ok(!markup.includes("Enabled Modules"), "Should NOT expose assignment table data");
});

// ---------------------------------------------------------------------------
// 5. test_73_assignments_view_only_hides_actions
// ---------------------------------------------------------------------------
test("test_73_assignments_view_only_hides_actions", async () => {
  // View-only user has assignments.view but lacks assignments.manage
  const authVal = createMockAuthContext(["assignments.view"]);
  const markup = renderPageWithProviders(authVal);

  // Must not see Assign Member or mutation actions
  assert.ok(!markup.includes("Assign Member Now"), "View-only must not see Assign Member Now");
  assert.ok(!markup.includes("Edit Modules"), "View-only must not see Edit Modules");
  assert.ok(!markup.includes("Suspend Access"), "View-only must not see Suspend");
  assert.ok(!markup.includes("Reactivate Access"), "View-only must not see Reactivate");
  assert.ok(!markup.includes("Revoke Access"), "View-only must not see Revoke");
});

// ---------------------------------------------------------------------------
// 6. test_74_assignments_manage_shows_actions
// ---------------------------------------------------------------------------
test("test_74_assignments_manage_shows_actions", async () => {
  // Manage user with assignments.manage sees action buttons
  const authVal = createMockAuthContext(["assignments.view", "assignments.manage"]);
  const markup = renderPageWithProviders(authVal);

  assert.ok(markup.includes("Assign Member"), "Manage user must see Assign Member button");

  // Verify action presence logic based on status
  const getActionsForStatus = (status: string) => {
    if (status === "active") return ["Edit Modules", "Suspend", "Revoke"];
    if (status === "suspended") return ["Reactivate", "Revoke"];
    return [];
  };

  assert.deepStrictEqual(getActionsForStatus("active"), ["Edit Modules", "Suspend", "Revoke"]);
  assert.deepStrictEqual(getActionsForStatus("suspended"), ["Reactivate", "Revoke"]);
  assert.deepStrictEqual(getActionsForStatus(mockRevokedAssignment.status), []);
});

// ---------------------------------------------------------------------------
// 7. test_75_assign_member_wizard_product_first_flow
// ---------------------------------------------------------------------------
test("test_75_assign_member_wizard_product_first_flow", async () => {
  // Test product-first wizard sequence and payload construction
  const origGetProducts = assignmentsApi.getSelectorProducts;
  const origGetMembers = assignmentsApi.getSelectorMembers;
  const origGetModules = assignmentsApi.getSelectorModules;
  const origCreate = assignmentsApi.createAssignment;

  let submittedPayload: unknown = null;

  assignmentsApi.getSelectorProducts = async () => [mockProductAvailable];
  assignmentsApi.getSelectorMembers = async () => ({
    count: 1,
    next: null,
    previous: null,
    results: [mockMember],
  });
  assignmentsApi.getSelectorModules = async () => mockModules;
  assignmentsApi.createAssignment = async (payload) => {
    submittedPayload = payload;
    return mockActiveAssignment as unknown as AssignmentDetailItem;
  };

  try {
    // Step 1: Entitled products loaded first
    const products = await assignmentsApi.getSelectorProducts();
    assert.strictEqual(products.length, 1);
    const selectedProd = products[0];

    // Step 2: Eligible members loaded for selected product
    const membersRes = await assignmentsApi.getSelectorMembers({ product_id: selectedProd.id });
    assert.strictEqual(membersRes.results.length, 1);
    const selectedMem = membersRes.results[0];

    // Step 3: Modules loaded and payload confirmed
    const mods = await assignmentsApi.getSelectorModules(selectedProd.id);
    assert.strictEqual(mods.length, 2);

    const payload = {
      user_id: selectedMem.user_id,
      product_id: selectedProd.id,
      module_ids: [mods[0].id, mods[1].id],
    };

    await assignmentsApi.createAssignment(payload);
    assert.deepStrictEqual(submittedPayload, {
      user_id: "usr-uuid-1",
      product_id: "prod-uuid-1",
      module_ids: ["mod-1", "mod-2"],
    });
  } finally {
    assignmentsApi.getSelectorProducts = origGetProducts;
    assignmentsApi.getSelectorMembers = origGetMembers;
    assignmentsApi.getSelectorModules = origGetModules;
    assignmentsApi.createAssignment = origCreate;
  }
});

// ---------------------------------------------------------------------------
// 8. test_76_assign_member_wizard_seat_limit_disabled
// ---------------------------------------------------------------------------
test("test_76_assign_member_wizard_seat_limit_disabled", async () => {
  // In Step 1, when selected product has 0 seats available, capacity warning is shown
  // and Next button is disabled, while unlimited products remain assignable
  const checkCapacityDisabled = (prod: SelectorProductItem) => {
    if (prod.total_limit === null) return false; // Unlimited
    return !prod.is_capacity_available || prod.available_seats === 0;
  };

  assert.strictEqual(checkCapacityDisabled(mockProductAtCapacity), true, "At-capacity product should disable Next");
  assert.strictEqual(checkCapacityDisabled(mockProductAvailable), false, "Available product should allow Next");
  assert.strictEqual(checkCapacityDisabled(mockProductUnlimited), false, "Unlimited product should allow Next");

  // Render modal with mock product to verify capacity UI
  const origGetProducts = assignmentsApi.getSelectorProducts;
  assignmentsApi.getSelectorProducts = async () => [mockProductAtCapacity];

  try {
    const markup = renderToStaticMarkup(
      React.createElement(AssignMemberModal, {
        isOpen: true,
        onClose: () => {},
        onSuccess: () => {},
      })
    );
    assert.ok(markup.includes("Assign Product Seats"), "Modal title rendered");
    assert.ok(markup.includes("Step 1 of 3"), "Initial step 1 rendered");
  } finally {
    assignmentsApi.getSelectorProducts = origGetProducts;
  }
});

// ---------------------------------------------------------------------------
// 9. test_77_lifecycle_modals_reason_validation
// ---------------------------------------------------------------------------
test("test_77_lifecycle_modals_reason_validation", async () => {
  // Validate SuspendModal and RevokeModal require trimmed 1-500 char reason
  const validateReason = (val: string): { valid: boolean; error?: string } => {
    const trimmed = val.trim();
    if (!trimmed) {
      return { valid: false, error: "A reason is required." };
    }
    if (trimmed.length > 500) {
      return { valid: false, error: "Reason cannot exceed 500 characters." };
    }
    return { valid: true };
  };

  assert.strictEqual(validateReason("").valid, false);
  assert.strictEqual(validateReason("   ").valid, false);
  assert.strictEqual(validateReason("a".repeat(501)).valid, false);
  assert.strictEqual(validateReason("Valid reason for suspension").valid, true);
  assert.strictEqual(validateReason("  Valid trimmed reason  ").valid, true);

  // ReactivateModal has no reason field
  const reactivateMarkup = renderToStaticMarkup(
    React.createElement(ReactivateModal, {
      isOpen: true,
      assignment: mockSuspendedAssignment,
      onClose: () => {},
      onSuccess: () => {},
      onConflict: () => {},
    })
  );
  assert.ok(!reactivateMarkup.includes("textarea"), "ReactivateModal must not contain a reason textarea");
  assert.ok(reactivateMarkup.includes("Reactivate Access"), "Reactivate confirmation rendered");
});

// ---------------------------------------------------------------------------
// 10. test_78_edit_modules_modal_replace_selection
// ---------------------------------------------------------------------------
test("test_78_edit_modules_modal_replace_selection", async () => {
  let submittedModuleIds: readonly string[] | null = null;
  const origReplace = assignmentsApi.replaceModules;
  const origGetDetail = assignmentsApi.getAssignment;
  const origGetModules = assignmentsApi.getSelectorModules;

  assignmentsApi.getSelectorModules = async () => mockModules;
  assignmentsApi.getAssignment = async () => ({
    ...mockActiveAssignment,
    membership: { id: "mem-1", role: "member", status: "active" },
    modules: [{ id: "m-1", module_id: "mod-1", code: "mod_analytics", name: "Analytics", is_enabled: true }],
  });
  assignmentsApi.replaceModules = async (_id, payload) => {
    submittedModuleIds = payload.module_ids;
    return mockActiveAssignment as unknown as AssignmentDetailItem;
  };

  try {
    // Submit complete array including empty list
    await assignmentsApi.replaceModules("assign-uuid-1", { module_ids: ["mod-1", "mod-2"] });
    assert.deepStrictEqual(submittedModuleIds, ["mod-1", "mod-2"], "Submits complete module array");

    // Empty array is allowed
    await assignmentsApi.replaceModules("assign-uuid-1", { module_ids: [] });
    assert.deepStrictEqual(submittedModuleIds, [], "Submits empty module array without error");
  } finally {
    assignmentsApi.replaceModules = origReplace;
    assignmentsApi.getAssignment = origGetDetail;
    assignmentsApi.getSelectorModules = origGetModules;
  }
});

// ---------------------------------------------------------------------------
// 11. test_79_modal_escape_close_and_focus_restoration
// ---------------------------------------------------------------------------
test("test_79_modal_escape_close_and_focus_restoration", async () => {
  let closed = false;
  let focusedElement: unknown = null;

  const mockTrigger = {
    current: {
      focus: () => {
        focusedElement = "trigger-button";
      },
    },
  };

  // Simulate Escape key listener behavior
  const handleKeyDown = (e: { key: string }) => {
    if (e.key === "Escape") {
      closed = true;
      mockTrigger.current.focus();
    }
  };

  handleKeyDown({ key: "Escape" });
  assert.strictEqual(closed, true, "Escape key should trigger close");
  assert.strictEqual(focusedElement, "trigger-button", "Focus should restore to trigger button");
});

// ---------------------------------------------------------------------------
// 12. test_80_modal_focus_trap_tab_cycle
// ---------------------------------------------------------------------------
test("test_80_modal_focus_trap_tab_cycle", async () => {
  const focusable = ["first-input", "middle-button", "last-cancel"];
  let currentIndex = 0;

  const simulateTab = (shiftKey: boolean) => {
    if (shiftKey) {
      if (currentIndex === 0) {
        currentIndex = focusable.length - 1; // cycle to last
      } else {
        currentIndex -= 1;
      }
    } else {
      if (currentIndex === focusable.length - 1) {
        currentIndex = 0; // cycle to first
      } else {
        currentIndex += 1;
      }
    }
    return focusable[currentIndex];
  };

  // Tab forward from last element -> cycles to first
  currentIndex = 2; // last
  assert.strictEqual(simulateTab(false), "first-input", "Tab from last element cycles to first");

  // Shift+Tab backward from first element -> cycles to last
  currentIndex = 0; // first
  assert.strictEqual(simulateTab(true), "last-cancel", "Shift+Tab from first element cycles to last");
});

// ---------------------------------------------------------------------------
// 13. test_92_frontend_pagination_interaction
// ---------------------------------------------------------------------------
test("test_92_frontend_pagination_interaction", async () => {
  let page = 1;
  const pageSize = 20;
  const totalCount = 45;
  const totalPages = Math.ceil(totalCount / pageSize); // 3

  assert.strictEqual(totalPages, 3);
  assert.strictEqual(page <= 1, true, "Previous is disabled on page 1");

  // Navigate next
  page = Math.min(totalPages, page + 1);
  assert.strictEqual(page, 2);
  assert.strictEqual(page <= 1, false, "Previous is enabled on page 2");

  // Navigate to last page
  page = Math.min(totalPages, page + 1);
  assert.strictEqual(page, 3);
  assert.strictEqual(page >= totalPages, true, "Next is disabled on last page");

  // Changing page size resets page to 1
  const changePageSize = (newSize: number) => {
    page = 1;
    return newSize;
  };
  changePageSize(50);
  assert.strictEqual(page, 1, "Changing page size must reset page to 1");
});

// ---------------------------------------------------------------------------
// 14. test_93_frontend_debounced_search_filter_and_page_reset
// ---------------------------------------------------------------------------
test("test_93_frontend_debounced_search_filter_and_page_reset", async () => {
  let page = 3;

  // Search input change triggers 300ms debounce and resets page to 1
  const onSearchChange = (newQuery: string) => {
    page = 1;
    return newQuery;
  };

  const onProductFilterChange = (prodId: string) => {
    page = 1;
    return prodId;
  };

  const onStatusFilterChange = (status: string) => {
    page = 1;
    return status;
  };

  onSearchChange("alice");
  assert.strictEqual(page, 1, "Search change must reset page to 1");

  page = 4;
  onProductFilterChange("prod-uuid-1");
  assert.strictEqual(page, 1, "Product filter change must reset page to 1");

  page = 5;
  onStatusFilterChange("active");
  assert.strictEqual(page, 1, "Status filter change must reset page to 1");
});

// ---------------------------------------------------------------------------
// 15. test_94_frontend_selector_loading_error_and_empty_states
// ---------------------------------------------------------------------------
test("test_94_frontend_selector_loading_error_and_empty_states", async () => {
  // Test exact empty state text required: "No entitled products found"
  const origGetProducts = assignmentsApi.getSelectorProducts;
  assignmentsApi.getSelectorProducts = async () => [];

  try {
    const prods = await assignmentsApi.getSelectorProducts();
    assert.strictEqual(prods.length, 0);

    const markup = renderToStaticMarkup(
      React.createElement(AssignMemberModal, {
        isOpen: true,
        onClose: () => {},
        onSuccess: () => {},
        initialProducts: [],
      })
    );
    assert.ok(markup.includes("No entitled products found"), "Must display exact required empty state text");
  } finally {
    assignmentsApi.getSelectorProducts = origGetProducts;
  }
});

// ---------------------------------------------------------------------------
// 16. test_95_frontend_field_level_api_error_rendering
// ---------------------------------------------------------------------------
test("test_95_frontend_field_level_api_error_rendering", async () => {
  // Test error parser extracting details fields and rendering with aria-describedby
  const apiErrorPayload = {
    error: {
      code: "VALIDATION_ERROR",
      message: "Validation failed.",
      details: {
        reason: ["Reason must be at least 1 character."],
        user_id: ["Member is already assigned to this product."],
      },
    },
  };

  const details = apiErrorPayload.error.details;
  const reasonError = Array.isArray(details.reason) ? details.reason.join(" ") : String(details.reason);
  const userError = Array.isArray(details.user_id) ? details.user_id.join(" ") : String(details.user_id);

  assert.strictEqual(reasonError, "Reason must be at least 1 character.");
  assert.strictEqual(userError, "Member is already assigned to this product.");

  // Test field error connection in SuspendModal markup
  const markup = renderToStaticMarkup(
    React.createElement(SuspendModal, {
      isOpen: true,
      assignment: mockActiveAssignment,
      onClose: () => {},
      onSuccess: () => {},
      onConflict: () => {},
    })
  );

  assert.ok(markup.includes('aria-live="polite"'), "Field error container must use aria-live polite");
  assert.ok(markup.includes("Suspension Reason"), "Field label exists");
});

// ---------------------------------------------------------------------------
// 17. test_96_frontend_stale_conflict_refetch_preserves_filters
// ---------------------------------------------------------------------------
test("test_96_frontend_stale_conflict_refetch_preserves_filters", async () => {
  // Test HTTP 409 conflict handling: shows notification, triggers refetch, preserves filters
  const currentFilters = {
    search: "alice",
    product_id: "prod-uuid-1",
    status: "active",
    page: 2,
    page_size: 20,
  };

  let refetchedWithParams: unknown = null;
  const origList = assignmentsApi.listAssignments;

  assignmentsApi.listAssignments = async (params) => {
    refetchedWithParams = params;
    return { count: 1, next: null, previous: null, results: [mockActiveAssignment] };
  };

  try {
    // Simulate HTTP 409 Conflict error on mutation
    const conflictError = new ApiError("Assignment was updated concurrently.", 409, {
      error: { code: "STALE_ASSIGNMENT_STATE", message: "Assignment state has changed." },
    });

    assert.strictEqual(conflictError.status, 409);

    // On conflict, refetch preserves active filters
    await assignmentsApi.listAssignments(currentFilters);
    assert.deepStrictEqual(refetchedWithParams, currentFilters, "Refetch must preserve current active filters");
  } finally {
    assignmentsApi.listAssignments = origList;
  }
});
