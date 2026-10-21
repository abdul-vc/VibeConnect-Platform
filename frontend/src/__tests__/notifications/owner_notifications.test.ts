import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { ENDPOINTS } from "../../api/endpoints.ts";
import { notificationsApi } from "../../api/notifications.ts";

describe("Owner Notifications & Communications API Contract", () => {
  it("verifies endpoints use centralized configuration with no hardcoded domains", () => {
    assert.equal(ENDPOINTS.NOTIFICATIONS.TEMPLATES, "/api/v1/notifications/templates/");
    assert.equal(
      ENDPOINTS.NOTIFICATIONS.TEMPLATE_DETAIL("tmpl-123"),
      "/api/v1/notifications/templates/tmpl-123/"
    );
    assert.equal(
      ENDPOINTS.NOTIFICATIONS.NEW_VERSION("tmpl-123"),
      "/api/v1/notifications/templates/tmpl-123/new-version/"
    );
    assert.equal(
      ENDPOINTS.NOTIFICATIONS.RETIRE("tmpl-123"),
      "/api/v1/notifications/templates/tmpl-123/retire/"
    );
    assert.equal(
      ENDPOINTS.NOTIFICATIONS.PREVIEW("tmpl-123"),
      "/api/v1/notifications/templates/tmpl-123/preview/"
    );
    assert.equal(ENDPOINTS.NOTIFICATIONS.DELIVERIES, "/api/v1/notifications/deliveries/");
    assert.equal(
      ENDPOINTS.NOTIFICATIONS.RETRY("del-123"),
      "/api/v1/notifications/deliveries/del-123/retry/"
    );
  });

  it("verifies notificationsApi exposes all required operational methods", () => {
    assert.equal(typeof notificationsApi.listTemplates, "function");
    assert.equal(typeof notificationsApi.getTemplate, "function");
    assert.equal(typeof notificationsApi.createNewVersion, "function");
    assert.equal(typeof notificationsApi.retireTemplate, "function");
    assert.equal(typeof notificationsApi.previewTemplate, "function");
    assert.equal(typeof notificationsApi.listDeliveries, "function");
    assert.equal(typeof notificationsApi.retryDelivery, "function");
  });
});
