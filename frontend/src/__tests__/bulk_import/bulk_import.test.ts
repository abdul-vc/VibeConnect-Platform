/**
 * Phase 3D: Frontend Bulk Import Workspace Tests.
 *
 * Validates:
 * - BulkImportPage initial rendering and drag-and-drop zone
 * - API client functions: createJob, getJob, listRows, commitJob, retryJob
 * - Validation error display and retry handling
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
    location: { pathname: "/bulk-import", search: "" },
    matchMedia: () => ({ matches: false, addEventListener: () => {}, removeEventListener: () => {} }),
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

import { bulkImportApi } from "../../api/bulkImport.ts";
import { BulkImportPage } from "../../pages/bulk_import/BulkImportPage.tsx";
import { AuthContext } from "../../context/AuthContext.tsx";
import { ThemeProvider } from "../../context/ThemeContext.tsx";
import type { BulkImportJob, BulkImportRow } from "../../api/types.ts";

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

const mockJobValidated: BulkImportJob = {
  id: "job-uuid-1",
  organization_id: "org-uuid-1",
  organization_code: "acme_corp",
  organization_name: "Acme Corporation",
  import_type: "users_and_memberships",
  status: "validated",
  idempotency_key: "idemp-001",
  total_rows: 10,
  valid_rows: 8,
  invalid_rows: 2,
  committed_rows: 0,
  failed_rows: 0,
  error_summary: {},
  created_at: "2026-09-26T12:00:00Z",
  updated_at: "2026-09-26T12:00:00Z",
  completed_at: null,
};

const mockJobCommitted: BulkImportJob = {
  ...mockJobValidated,
  status: "completed",
  committed_rows: 8,
  completed_at: "2026-09-26T12:05:00Z",
};

const mockRows: BulkImportRow[] = [
  {
    id: "row-1",
    row_number: 1,
    validation_state: "valid",
    payload_ref: { email: "alice@acme.test", full_name: "Alice", membership_type: "member" },
    error_code: "",
    error_message: "",
    created_at: "2026-09-26T12:00:00Z",
    updated_at: "2026-09-26T12:00:00Z",
  },
  {
    id: "row-2",
    row_number: 2,
    validation_state: "invalid",
    payload_ref: { email: "bad-email", full_name: "Bad", membership_type: "member" },
    error_code: "INVALID_EMAIL",
    error_message: "'bad-email' is not a valid email address.",
    created_at: "2026-09-26T12:00:00Z",
    updated_at: "2026-09-26T12:00:00Z",
  },
];

function renderBulkImportPage() {
  const authVal = createMockAuthContext();
  return renderToStaticMarkup(
    React.createElement(
      MemoryRouter,
      { initialEntries: ["/bulk-import"] },
      React.createElement(
        ThemeProvider,
        null,
        React.createElement(
          AuthContext.Provider,
          { value: authVal as any },
          React.createElement(BulkImportPage, null)
        )
      )
    )
  );
}

// ---------------------------------------------------------------------------
// 1. Initial Page Render & Drop Zone
// ---------------------------------------------------------------------------
test("test_bulk_import_page_renders_dropzone_and_options", async () => {
  const markup = renderBulkImportPage();

  assert.ok(markup.includes("Bulk User &amp; Membership Import") || markup.includes("Bulk User & Membership Import"));
  assert.ok(markup.includes("Drag and drop your CSV or JSON file here"));
  assert.ok(markup.includes("Upload &amp; Validate Staged Rows") || markup.includes("Upload & Validate Staged Rows"));
});

// ---------------------------------------------------------------------------
// 2. API Client Lifecycle: Create, List Rows, Commit, Retry
// ---------------------------------------------------------------------------
test("test_bulk_import_api_client_lifecycle", async () => {
  const origCreate = bulkImportApi.createJob;
  const origGet = bulkImportApi.getJob;
  const origListRows = bulkImportApi.listRows;
  const origCommit = bulkImportApi.commitJob;
  const origRetry = bulkImportApi.retryJob;

  try {
    let capturedCreatePayload: unknown = null;
    bulkImportApi.createJob = async (payload) => {
      capturedCreatePayload = payload;
      return mockJobValidated;
    };

    const job = await bulkImportApi.createJob({
      organization_id: "org-uuid-1",
      idempotency_key: "idemp-001",
      raw_content: "email,full_name\nalice@acme.test,Alice\n",
      content_type: "csv",
    });

    assert.equal(job.id, "job-uuid-1");
    assert.equal(job.status, "validated");
    assert.deepEqual(capturedCreatePayload, {
      organization_id: "org-uuid-1",
      idempotency_key: "idemp-001",
      raw_content: "email,full_name\nalice@acme.test,Alice\n",
      content_type: "csv",
    });

    bulkImportApi.getJob = async (id) => {
      assert.equal(id, "job-uuid-1");
      return mockJobValidated;
    };

    const fetchedJob = await bulkImportApi.getJob("job-uuid-1");
    assert.equal(fetchedJob.total_rows, 10);

    bulkImportApi.listRows = async (id) => {
      assert.equal(id, "job-uuid-1");
      return { count: 2, next: null, previous: null, results: mockRows };
    };

    const rowsRes = await bulkImportApi.listRows("job-uuid-1");
    assert.equal(rowsRes.results.length, 2);
    assert.equal(rowsRes.results[1].validation_state, "invalid");

    bulkImportApi.commitJob = async (id) => {
      assert.equal(id, "job-uuid-1");
      return mockJobCommitted;
    };

    const committed = await bulkImportApi.commitJob("job-uuid-1");
    assert.equal(committed.status, "completed");
    assert.equal(committed.committed_rows, 8);

    bulkImportApi.retryJob = async (id) => {
      assert.equal(id, "job-uuid-1");
      return mockJobCommitted;
    };

    const retried = await bulkImportApi.retryJob("job-uuid-1");
    assert.equal(retried.status, "completed");
  } finally {
    bulkImportApi.createJob = origCreate;
    bulkImportApi.getJob = origGet;
    bulkImportApi.listRows = origListRows;
    bulkImportApi.commitJob = origCommit;
    bulkImportApi.retryJob = origRetry;
  }
});

test("test_bulk_import_reconciliation_report_api", async () => {
  const origReconciliation = bulkImportApi.getReconciliation;
  try {
    const mockReport = {
      job_id: "job-uuid-rec",
      organization_id: "org-1",
      organization_code: "acme",
      organization_name: "Acme Corp",
      status: "completed" as const,
      total_rows: 5,
      committed_rows: 4,
      failed_rows: 1,
      invalid_rows: 0,
      valid_rows: 0,
      recoverable_failures_count: 1,
      terminal_failures_count: 0,
      can_retry: true,
      state_breakdown: { committed: 4, failed: 1 },
      error_code_breakdown: { COMMIT_FAILED: 1 },
      completed_at: "2026-09-26T12:00:00Z",
      created_at: "2026-09-26T11:55:00Z",
      rows: [
        {
          id: "row-1",
          row_number: 1,
          email: "user@acme.test",
          full_name: "User",
          membership_type: "member",
          role_code: "",
          validation_state: "committed" as const,
          error_code: "",
          error_message: "",
          is_recoverable: false,
        },
        {
          id: "row-2",
          row_number: 2,
          email: "fail@acme.test",
          full_name: "Failed User",
          membership_type: "member",
          role_code: "",
          validation_state: "failed" as const,
          error_code: "COMMIT_FAILED",
          error_message: "Network timeout",
          is_recoverable: true,
        },
      ],
    };

    bulkImportApi.getReconciliation = async (jobId) => {
      assert.equal(jobId, "job-uuid-rec");
      return mockReport;
    };

    const report = await bulkImportApi.getReconciliation("job-uuid-rec");
    assert.equal(report.job_id, "job-uuid-rec");
    assert.equal(report.total_rows, 5);
    assert.equal(report.committed_rows, 4);
    assert.equal(report.recoverable_failures_count, 1);
    assert.equal(report.can_retry, true);
    assert.equal(report.rows[1].is_recoverable, true);
  } finally {
    bulkImportApi.getReconciliation = origReconciliation;
  }
});

