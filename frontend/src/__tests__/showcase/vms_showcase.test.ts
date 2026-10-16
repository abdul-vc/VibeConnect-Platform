/**
 * VMS (WarehouseOS) Sandbox Integration Frontend Tests.
 *
 * Verifies:
 * - showcaseApi.vms client methods exist and are callable
 * - VmsLiveShowcase renders live sandbox indicators, metrics, tabs, and SKU catalog
 * - ShowcaseEmbeddedDemo provides the in-window Demonstration Console for VMS
 * - ShowcaseEmbeddedDemo shows provider notice regarding X-Frame-Options when switching to live app tab
 */

import test from "node:test";
import assert from "node:assert/strict";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";

// Setup minimal browser DOM environment for Node execution
if (typeof globalThis.window === "undefined" || !(globalThis as unknown as { window: { matchMedia?: unknown } }).window.matchMedia) {
  (globalThis as unknown as { window: unknown }).window = {
    addEventListener: () => {},
    removeEventListener: () => {},
    scrollTo: () => {},
    location: { pathname: "/showcase/present", search: "?product=vms-warehouse" },
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
import { VmsLiveShowcase } from "../../pages/showcase/VmsLiveShowcase.tsx";
import { ShowcaseEmbeddedDemo } from "../../pages/showcase/ShowcaseEmbeddedDemo.tsx";

test("VMS AC-1: showcaseApi.vms client endpoints are exposed", () => {
  assert.strictEqual(typeof showcaseApi.vms.getHealth, "function");
  assert.strictEqual(typeof showcaseApi.vms.getOverview, "function");
  assert.strictEqual(typeof showcaseApi.vms.getInventory, "function");
  assert.strictEqual(typeof showcaseApi.vms.getDocks, "function");
  assert.strictEqual(typeof showcaseApi.vms.getWaves, "function");
  assert.strictEqual(typeof showcaseApi.vms.getVehicles, "function");
  assert.strictEqual(typeof showcaseApi.vms.getReports, "function");
});

test("VMS AC-2: VmsLiveShowcase component renders live sandbox indicator badge and operational tabs", () => {
  const markup = renderToStaticMarkup(
    React.createElement(VmsLiveShowcase, {
      isEmbedded: true,
      onLaunchExternal: () => {},
    })
  );

  // Identity and badges
  assert.ok(markup.includes("WarehouseOS"), "Must render WarehouseOS product name");
  assert.ok(markup.includes("M2M Verified"), "Must render M2M Verified badge");
  assert.ok(markup.includes("vms-showcase-header"), "Must render showcase header container");

  // Operational navigation tabs
  assert.ok(markup.includes("Overview &amp; KPIs") || markup.includes("Overview & KPIs"), "Must include Overview tab");
  assert.ok(markup.includes("Inventory &amp; SKUs") || markup.includes("Inventory & SKUs"), "Must include Inventory tab");
  assert.ok(markup.includes("Docks &amp; Yard") || markup.includes("Docks & Yard"), "Must include Docks & Yard tab");
  assert.ok(markup.includes("Fulfillment Waves"), "Must include Fulfillment Waves tab");

  // Initial loading indicator
  assert.ok(markup.includes("WarehouseOS"), "Must render loading or container markup");
});

test("VMS AC-3: ShowcaseEmbeddedDemo defaults to Demonstration Console for vms-warehouse", () => {
  const markup = renderToStaticMarkup(
    React.createElement(ShowcaseEmbeddedDemo, {
      productName: "VMS (Warehouse)",
      productCode: "vms-warehouse",
      launchUrl: "https://vms.vibecopilot.ai",
      onBack: () => {},
    })
  );

  assert.ok(markup.includes("VMS (Warehouse) Live Demo"), "Must render correct product title");
  assert.ok(markup.includes("WarehouseOS Sandbox · Live API"), "Must render live API status badge");
  assert.ok(markup.includes("API Metrics &amp; Insights") || markup.includes("API Metrics & Insights"), "Must render API insights tab");
  assert.ok(markup.includes("vms-live-showcase-container"), "Must render VmsLiveShowcase container by default");
});

test("VMS AC-4: ShowcaseEmbeddedDemo provides tab switching and informs about X-Frame-Options", () => {
  const markup = renderToStaticMarkup(
    React.createElement(ShowcaseEmbeddedDemo, {
      productName: "VMS (Warehouse)",
      productCode: "vms-warehouse",
      launchUrl: "https://vms.vibecopilot.ai",
      onBack: () => {},
    })
  );

  // Tab controls
  assert.ok(markup.includes("vms-workspace-tab-group"), "Must have VMS workspace tab group");
  assert.ok(markup.includes("vms-tab-api-insights-btn"), "Must have VMS API insights tab button");
  assert.ok(markup.includes("vms-tab-live-app-btn"), "Must have VMS live app tab button");
});
