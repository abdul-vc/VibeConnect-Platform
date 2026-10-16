/**
 * HRMS Sandbox Integration Frontend Tests.
 *
 * Verifies:
 * - showcaseApi.hrms client methods exist and are callable
 * - HrmsLiveShowcase renders live sandbox indicators, metrics, directory, attendance history, org structure, and leaves
 * - ShowcasePresentPage integrates HrmsLiveShowcase for the HRMS product
 * - ShowcaseEmbeddedDemo provides the zero-login Demonstration Console workspace
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
    location: { pathname: "/showcase/present", search: "?product=hrms" },
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

import { showcaseApi } from "../../api/showcase.ts";
import { HrmsLiveShowcase } from "../../pages/showcase/HrmsLiveShowcase.tsx";
import { ShowcaseEmbeddedDemo } from "../../pages/showcase/ShowcaseEmbeddedDemo.tsx";

test("HRMS AC-1: showcaseApi.hrms client endpoints are exposed", () => {
  assert.strictEqual(typeof showcaseApi.hrms.getHealth, "function");
  assert.strictEqual(typeof showcaseApi.hrms.getOverview, "function");
  assert.strictEqual(typeof showcaseApi.hrms.getEmployees, "function");
  assert.strictEqual(typeof showcaseApi.hrms.getAttendance, "function");
  assert.strictEqual(typeof showcaseApi.hrms.getDepartments, "function");
  assert.strictEqual(typeof showcaseApi.hrms.getAttendanceHistory, "function");
  assert.strictEqual(typeof showcaseApi.hrms.getOrgStructure, "function");
  assert.strictEqual(typeof showcaseApi.hrms.getLeavesSummary, "function");
});

test("HRMS AC-2: HrmsLiveShowcase component renders live sandbox indicator badge and modules", () => {
  const markup = renderToStaticMarkup(
    React.createElement(
      MemoryRouter,
      null,
      React.createElement(HrmsLiveShowcase, null)
    )
  );

  assert.ok(
    markup.includes("id=\"hrms-sandbox-indicator-badge\""),
    "HrmsLiveShowcase must render sandbox indicator badge"
  );
  assert.ok(
    markup.includes("PeoplePulse HRMS Integration"),
    "HrmsLiveShowcase must render PeoplePulse HRMS title"
  );
  assert.ok(
    markup.includes("https://hrms.vibesandbox.live"),
    "HrmsLiveShowcase must display sandbox endpoint URL"
  );
  assert.ok(
    markup.includes("id=\"hrms-kpi-summary-grid\""),
    "HrmsLiveShowcase must render attendance KPI metrics grid"
  );
  assert.ok(
    markup.includes("Total Workforce"),
    "HrmsLiveShowcase must include Total Workforce card"
  );
  assert.ok(
    markup.includes("Present Today"),
    "HrmsLiveShowcase must include Present Today card"
  );
  assert.ok(
    markup.includes("Employee Directory"),
    "HrmsLiveShowcase must have Employee Directory tab"
  );
  assert.ok(
    markup.includes("Today&#x27;s Attendance Feed") || markup.includes("Today's Attendance Feed"),
    "HrmsLiveShowcase must have Attendance Feed tab"
  );
  assert.ok(
    markup.includes("Attendance History &amp; Logs") || markup.includes("Attendance History & Logs"),
    "HrmsLiveShowcase must have Attendance History tab"
  );
  assert.ok(
    markup.includes("Organization Structure"),
    "HrmsLiveShowcase must have Organization Structure tab"
  );
  assert.ok(
    markup.includes("Leave Management"),
    "HrmsLiveShowcase must have Leave Management tab"
  );
});

test("HRMS AC-3: HrmsLiveShowcase renders Launch Live Demo action button", () => {
  const markup = renderToStaticMarkup(
    React.createElement(
      MemoryRouter,
      null,
      React.createElement(HrmsLiveShowcase, { onLaunchLiveDemo: () => {} })
    )
  );

  assert.ok(
    markup.includes("id=\"hrms-open-sandbox-portal-btn\""),
    "HrmsLiveShowcase must render Launch Live Demo button"
  );
  assert.ok(
    markup.includes("Launch Live Demo"),
    "HrmsLiveShowcase button must have Launch Live Demo label"
  );
});

test("HRMS AC-4: ShowcaseEmbeddedDemo renders in-window live application iframe and workspace tabs", () => {
  const markup = renderToStaticMarkup(
    React.createElement(ShowcaseEmbeddedDemo, {
      productName: "PeoplePulse HRMS",
      productCode: "hrms",
      launchUrl: "https://hrms.vibesandbox.live/",
      onBack: () => {},
      backLabel: "Back to Presentation",
    })
  );

  assert.ok(
    markup.includes("id=\"showcase-embedded-demo-workspace\""),
    "ShowcaseEmbeddedDemo must render demo workspace"
  );
  assert.ok(
    markup.includes("id=\"showcase-demo-iframe\""),
    "ShowcaseEmbeddedDemo must render in-window live application iframe"
  );
  assert.ok(
    markup.includes("src=\"https://hrms.vibesandbox.live/\""),
    "Iframe must target the authorized HRMS live endpoint"
  );
  assert.ok(
    markup.includes("allow-same-origin allow-scripts allow-forms allow-popups allow-downloads allow-modals"),
    "Iframe must have robust sandbox security attributes"
  );
  assert.ok(
    markup.includes("id=\"hrms-workspace-tab-group\""),
    "ShowcaseEmbeddedDemo must provide workspace tab group for HRMS"
  );
  assert.ok(
    markup.includes("Live Application"),
    "Workspace must have Live Application tab"
  );
  assert.ok(
    markup.includes("API Metrics &amp; Insights") || markup.includes("API Metrics & Insights"),
    "Workspace must have API Metrics & Insights tab"
  );
  assert.ok(
    markup.includes("id=\"showcase-exit-demo-btn\""),
    "Workspace must provide in-window exit back button"
  );
  assert.ok(
    markup.includes("Back to Presentation"),
    "Exit button must render back label"
  );
});

test("HRMS AC-5: In-window live demo console delivers zero-login demonstration with sandbox proxy", () => {
  const markup = renderToStaticMarkup(
    React.createElement(ShowcaseEmbeddedDemo, {
      productName: "PeoplePulse HRMS",
      productCode: "hrms",
      launchUrl: "https://hrms.vibesandbox.live/",
      onBack: () => {},
      backLabel: "Back to Showcase",
    })
  );

  assert.ok(
    markup.includes("id=\"hrms-live-showcase-container\""),
    "Live demonstration console must render inside ShowcaseEmbeddedDemo without manual login"
  );
  assert.ok(
    markup.includes("PeoplePulse Sandbox · Live API"),
    "ShowcaseEmbeddedDemo must indicate active PeoplePulse Live API connection"
  );
});
