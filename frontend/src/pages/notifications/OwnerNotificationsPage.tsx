import React, { FC, useEffect, useState, useCallback } from "react";
import { AppShell } from "../../components/AppShell.tsx";
import { LoadingSpinner } from "../../components/LoadingSpinner.tsx";
import {
  notificationsApi,
  NotificationTemplate,
  NotificationDelivery,
  TemplatePreviewResponse,
} from "../../api/notifications.ts";

export const OwnerNotificationsPage: FC = () => {
  const [activeTab, setActiveTab] = useState<"templates" | "deliveries">("templates");
  const [templates, setTemplates] = useState<NotificationTemplate[]>([]);
  const [deliveries, setDeliveries] = useState<NotificationDelivery[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Status/Channel filters
  const [deliveryStatusFilter, setDeliveryStatusFilter] = useState<string>("");
  const [channelFilter, setChannelFilter] = useState<string>("");

  // Modals / Actions
  const [previewTemplate, setPreviewTemplate] = useState<NotificationTemplate | null>(null);
  const [previewResult, setPreviewResult] = useState<TemplatePreviewResponse | null>(null);
  const [previewContextJson, setPreviewContextJson] = useState<string>('{"user_name": "Valued User"}');
  const [previewLoading, setPreviewLoading] = useState(false);

  const [versioningTemplate, setVersioningTemplate] = useState<NotificationTemplate | null>(null);
  const [newSubject, setNewSubject] = useState("");
  const [newBodyRef, setNewBodyRef] = useState("");
  const [versionSubmitting, setVersionSubmitting] = useState(false);

  const loadTemplates = useCallback(async () => {
    try {
      const res = await notificationsApi.listTemplates();
      setTemplates(res.results || []);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load templates.");
    }
  }, []);

  const loadDeliveries = useCallback(async () => {
    try {
      const params: Record<string, string> = {};
      if (deliveryStatusFilter) params.status = deliveryStatusFilter;
      if (channelFilter) params.channel = channelFilter;
      const res = await notificationsApi.listDeliveries(params);
      setDeliveries(res.results || []);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load deliveries.");
    }
  }, [deliveryStatusFilter, channelFilter]);

  useEffect(() => {
    setLoading(true);
    setError(null);
    if (activeTab === "templates") {
      loadTemplates().finally(() => setLoading(false));
    } else {
      loadDeliveries().finally(() => setLoading(false));
    }
  }, [activeTab, loadTemplates, loadDeliveries]);

  const handleRetire = async (templateId: string) => {
    try {
      await notificationsApi.retireTemplate(templateId);
      await loadTemplates();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to retire template.");
    }
  };

  const handleCreateNewVersion = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!versioningTemplate) return;
    setVersionSubmitting(true);
    try {
      await notificationsApi.createNewVersion(versioningTemplate.id, {
        subject_template: newSubject,
        body_ref: newBodyRef,
      });
      setVersioningTemplate(null);
      setNewSubject("");
      setNewBodyRef("");
      await loadTemplates();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create new template version.");
    } finally {
      setVersionSubmitting(false);
    }
  };

  const handleExecutePreview = async () => {
    if (!previewTemplate) return;
    setPreviewLoading(true);
    try {
      let parsedContext: Record<string, unknown> = {};
      try {
        parsedContext = JSON.parse(previewContextJson);
      } catch {
        setError("Invalid JSON context for preview.");
        setPreviewLoading(false);
        return;
      }
      const res = await notificationsApi.previewTemplate(previewTemplate.id, parsedContext);
      setPreviewResult(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to preview template.");
    } finally {
      setPreviewLoading(false);
    }
  };

  return (
    <AppShell>
      <div className="space-y-6 max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-gray-900 dark:text-white">
            Notifications & Communications
          </h1>
          <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
            Control-plane management of versioned communication templates and asynchronous delivery logs.
          </p>
        </div>

        {error && (
          <div className="rounded-md bg-red-50 p-4 border border-red-200 dark:bg-red-900/30 dark:border-red-800">
            <p className="text-sm text-red-700 dark:text-red-400">{error}</p>
          </div>
        )}

        {/* Tab Selection */}
        <div className="border-b border-gray-200 dark:border-gray-800">
          <nav className="-mb-px flex space-x-8" aria-label="Tabs">
            <button
              type="button"
              onClick={() => setActiveTab("templates")}
              className={`whitespace-nowrap py-3 px-1 border-b-2 font-medium text-sm ${
                activeTab === "templates"
                  ? "border-indigo-500 text-indigo-600 dark:text-indigo-400"
                  : "border-transparent text-gray-500 hover:text-gray-700 dark:text-gray-400 hover:border-gray-300"
              }`}
            >
              Templates ({templates.length})
            </button>
            <button
              type="button"
              onClick={() => setActiveTab("deliveries")}
              className={`whitespace-nowrap py-3 px-1 border-b-2 font-medium text-sm ${
                activeTab === "deliveries"
                  ? "border-indigo-500 text-indigo-600 dark:text-indigo-400"
                  : "border-transparent text-gray-500 hover:text-gray-700 dark:text-gray-400 hover:border-gray-300"
              }`}
            >
              Delivery Queue ({deliveries.length})
            </button>
          </nav>
        </div>

        {loading ? (
          <div className="flex justify-center py-12">
            <LoadingSpinner label="Loading notification records…" />
          </div>
        ) : activeTab === "templates" ? (
          <div className="space-y-6">
            <div className="bg-white dark:bg-gray-900 shadow rounded-lg overflow-hidden border border-gray-200 dark:border-gray-800">
              <div className="overflow-x-auto">
                <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-800">
                  <thead className="bg-gray-50 dark:bg-gray-800/50">
                    <tr>
                      <th className="px-6 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">
                        Template Code & Name
                      </th>
                      <th className="px-6 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">
                        Channel
                      </th>
                      <th className="px-6 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">
                        Version
                      </th>
                      <th className="px-6 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">
                        Subject Template
                      </th>
                      <th className="px-6 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">
                        Status
                      </th>
                      <th className="px-6 py-3 text-right text-xs font-semibold text-gray-500 uppercase tracking-wider">
                        Actions
                      </th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-200 dark:divide-gray-800">
                    {templates.length === 0 ? (
                      <tr>
                        <td colSpan={6} className="px-6 py-8 text-center text-sm text-gray-500">
                          No notification templates configured.
                        </td>
                      </tr>
                    ) : (
                      templates.map((tmpl) => (
                        <tr key={tmpl.id} className="hover:bg-gray-50 dark:hover:bg-gray-800/40">
                          <td className="px-6 py-4 whitespace-nowrap">
                            <div className="font-medium text-gray-900 dark:text-white">{tmpl.name}</div>
                            <div className="text-xs text-gray-500 font-mono">{tmpl.code}</div>
                          </td>
                          <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-600 dark:text-gray-300 uppercase">
                            {tmpl.channel}
                          </td>
                          <td className="px-6 py-4 whitespace-nowrap text-sm font-semibold text-gray-700 dark:text-gray-300">
                            v{tmpl.version}
                          </td>
                          <td className="px-6 py-4 text-sm text-gray-600 dark:text-gray-300 max-w-xs truncate">
                            {tmpl.subject_template}
                          </td>
                          <td className="px-6 py-4 whitespace-nowrap">
                            <span
                              className={`inline-flex px-2 py-0.5 rounded text-xs font-semibold uppercase ${
                                tmpl.status === "active"
                                  ? "bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400"
                                  : tmpl.status === "retired"
                                  ? "bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-400"
                                  : "bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400"
                              }`}
                            >
                              {tmpl.status}
                            </span>
                          </td>
                          <td className="px-6 py-4 whitespace-nowrap text-right text-sm space-x-3">
                            <button
                              type="button"
                              onClick={() => {
                                setPreviewTemplate(tmpl);
                                setPreviewResult(null);
                              }}
                              className="text-indigo-600 hover:text-indigo-900 dark:text-indigo-400 font-medium"
                            >
                              Preview
                            </button>
                            {tmpl.status === "active" && (
                              <>
                                <button
                                  type="button"
                                  onClick={() => {
                                    setVersioningTemplate(tmpl);
                                    setNewSubject(tmpl.subject_template);
                                    setNewBodyRef(tmpl.body_ref);
                                  }}
                                  className="text-blue-600 hover:text-blue-900 dark:text-blue-400 font-medium"
                                >
                                  New Version
                                </button>
                                <button
                                  type="button"
                                  onClick={() => handleRetire(tmpl.id)}
                                  className="text-red-600 hover:text-red-900 dark:text-red-400 font-medium"
                                >
                                  Retire
                                </button>
                              </>
                            )}
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </div>

            {/* Preview Modal/Panel */}
            {previewTemplate && (
              <div className="bg-white dark:bg-gray-900 p-6 rounded-lg shadow border border-gray-200 dark:border-gray-800 space-y-4">
                <div className="flex justify-between items-center">
                  <h3 className="text-lg font-bold text-gray-900 dark:text-white">
                    Preview Template: {previewTemplate.name} (v{previewTemplate.version})
                  </h3>
                  <button
                    type="button"
                    onClick={() => setPreviewTemplate(null)}
                    className="text-gray-400 hover:text-gray-600 text-sm"
                  >
                    Close
                  </button>
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-700 dark:text-gray-300">
                    Template Context (JSON):
                  </label>
                  <textarea
                    rows={3}
                    value={previewContextJson}
                    onChange={(e) => setPreviewContextJson(e.target.value)}
                    className="mt-1 block w-full font-mono text-xs rounded border-gray-300 dark:bg-gray-800 dark:border-gray-700 p-2"
                  />
                </div>
                <button
                  type="button"
                  onClick={handleExecutePreview}
                  disabled={previewLoading}
                  className="px-4 py-2 bg-indigo-600 text-white rounded text-sm font-medium hover:bg-indigo-700"
                >
                  {previewLoading ? "Rendering…" : "Render Subject"}
                </button>
                {previewResult && (
                  <div className="p-4 bg-gray-50 dark:bg-gray-800 rounded border border-gray-200 dark:border-gray-700 space-y-2">
                    <div>
                      <span className="text-xs text-gray-500 font-semibold">Rendered Subject:</span>
                      <p className="text-sm font-medium text-gray-900 dark:text-white">
                        {previewResult.rendered_subject}
                      </p>
                    </div>
                    <div>
                      <span className="text-xs text-gray-500 font-semibold">Body Reference:</span>
                      <p className="text-xs font-mono text-gray-600 dark:text-gray-300">
                        {previewResult.body_ref}
                      </p>
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* New Version Form */}
            {versioningTemplate && (
              <form
                onSubmit={handleCreateNewVersion}
                className="bg-white dark:bg-gray-900 p-6 rounded-lg shadow border border-gray-200 dark:border-gray-800 space-y-4"
              >
                <div className="flex justify-between items-center">
                  <h3 className="text-lg font-bold text-gray-900 dark:text-white">
                    Create New Version: {versioningTemplate.name}
                  </h3>
                  <button
                    type="button"
                    onClick={() => setVersioningTemplate(null)}
                    className="text-gray-400 hover:text-gray-600 text-sm"
                  >
                    Cancel
                  </button>
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-700 dark:text-gray-300">
                    Subject Line Template:
                  </label>
                  <input
                    type="text"
                    required
                    value={newSubject}
                    onChange={(e) => setNewSubject(e.target.value)}
                    className="mt-1 block w-full text-sm rounded border-gray-300 dark:bg-gray-800 dark:border-gray-700 p-2"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-700 dark:text-gray-300">
                    Body Reference (Template Key):
                  </label>
                  <input
                    type="text"
                    required
                    value={newBodyRef}
                    onChange={(e) => setNewBodyRef(e.target.value)}
                    className="mt-1 block w-full text-sm rounded border-gray-300 dark:bg-gray-800 dark:border-gray-700 p-2 font-mono"
                  />
                </div>
                <div className="flex justify-end space-x-3">
                  <button
                    type="button"
                    onClick={() => setVersioningTemplate(null)}
                    className="px-4 py-2 border border-gray-300 rounded text-sm"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={versionSubmitting}
                    className="px-4 py-2 bg-indigo-600 text-white rounded text-sm font-medium hover:bg-indigo-700"
                  >
                    {versionSubmitting ? "Publishing…" : "Publish Monotonic Version"}
                  </button>
                </div>
              </form>
            )}
          </div>
        ) : (
          <div className="space-y-6">
            {/* Delivery Filters */}
            <div className="flex space-x-4">
              <select
                aria-label="Filter by delivery status"
                value={deliveryStatusFilter}
                onChange={(e) => setDeliveryStatusFilter(e.target.value)}
                className="text-sm rounded border-gray-300 dark:bg-gray-800 dark:border-gray-700 p-2"
              >
                <option value="">All Statuses</option>
                <option value="queued">Queued</option>
                <option value="sent">Sent</option>
                <option value="failed">Failed</option>
                <option value="retrying">Retrying</option>
              </select>
              <select
                aria-label="Filter by delivery channel"
                value={channelFilter}
                onChange={(e) => setChannelFilter(e.target.value)}
                className="text-sm rounded border-gray-300 dark:bg-gray-800 dark:border-gray-700 p-2"
              >
                <option value="">All Channels</option>
                <option value="email">Email</option>
                <option value="in_app">In-App</option>
                <option value="sms">SMS</option>
                <option value="webhook">Webhook</option>
              </select>
            </div>

            <div className="bg-white dark:bg-gray-900 shadow rounded-lg overflow-hidden border border-gray-200 dark:border-gray-800">
              <div className="overflow-x-auto">
                <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-800">
                  <thead className="bg-gray-50 dark:bg-gray-800/50">
                    <tr>
                      <th className="px-6 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">
                        Template
                      </th>
                      <th className="px-6 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">
                        Recipient
                      </th>
                      <th className="px-6 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">
                        Status
                      </th>
                      <th className="px-6 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">
                        Retries
                      </th>
                      <th className="px-6 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">
                        Queued At
                      </th>
                      <th className="px-6 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">
                        Diagnostics
                      </th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-200 dark:divide-gray-800">
                    {deliveries.length === 0 ? (
                      <tr>
                        <td colSpan={6} className="px-6 py-8 text-center text-sm text-gray-500">
                          No notification deliveries found.
                        </td>
                      </tr>
                    ) : (
                      deliveries.map((del) => (
                        <tr key={del.id} className="hover:bg-gray-50 dark:hover:bg-gray-800/40">
                          <td className="px-6 py-4 whitespace-nowrap">
                            <div className="font-medium text-gray-900 dark:text-white">{del.template_name}</div>
                            <div className="text-xs text-gray-500 font-mono">{del.template_code}</div>
                          </td>
                          <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-700 dark:text-gray-300">
                            {del.recipient_email}
                          </td>
                          <td className="px-6 py-4 whitespace-nowrap">
                            <span
                              className={`inline-flex px-2 py-0.5 rounded text-xs font-semibold uppercase ${
                                del.status === "sent"
                                  ? "bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400"
                                  : del.status === "failed"
                                  ? "bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400"
                                  : del.status === "retrying"
                                  ? "bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400"
                                  : "bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400"
                              }`}
                            >
                              {del.status}
                            </span>
                          </td>
                          <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-600 dark:text-gray-400">
                            {del.retry_count} / {del.max_retries}
                          </td>
                          <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                            {new Date(del.queued_at).toLocaleString()}
                          </td>
                          <td className="px-6 py-4 text-xs text-gray-500 max-w-xs truncate">
                            {del.failure_reason || "None"}
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}
      </div>
    </AppShell>
  );
};
