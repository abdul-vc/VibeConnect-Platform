import { FC, useEffect, useState, useCallback } from "react";
import { AppShell } from "../../components/AppShell.tsx";
import { LoadingSpinner } from "../../components/LoadingSpinner.tsx";
import {
  notificationsApi,
  NotificationDelivery,
} from "../../api/notifications.ts";

export const TenantNotificationsPage: FC = () => {
  const [deliveries, setDeliveries] = useState<NotificationDelivery[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<string>("");

  const loadDeliveries = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const params: Record<string, string> = {};
      if (statusFilter) params.status = statusFilter;
      const res = await notificationsApi.listDeliveries(params);
      setDeliveries(res.results || []);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load notification history.");
    } finally {
      setLoading(false);
    }
  }, [statusFilter]);

  useEffect(() => {
    loadDeliveries();
  }, [loadDeliveries]);

  return (
    <AppShell>
      <div className="space-y-6 max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-gray-900 dark:text-white">
            Notifications & Alerts Log
          </h1>
          <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
            Read-only history of communications, automated alerts, and invitation dispatches.
          </p>
        </div>

        {error && (
          <div className="rounded-md bg-red-50 p-4 border border-red-200 dark:bg-red-900/30 dark:border-red-800">
            <p className="text-sm text-red-700 dark:text-red-400">{error}</p>
          </div>
        )}

        {/* Filter bar */}
        <div className="flex justify-between items-center">
          <div className="flex space-x-3 items-center">
            <label htmlFor="tenant-status-filter" className="text-xs font-semibold text-gray-600 dark:text-gray-400 uppercase">
              Filter Status:
            </label>
            <select
              id="tenant-status-filter"
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="text-sm rounded border-gray-300 dark:bg-gray-800 dark:border-gray-700 p-2"
            >
              <option value="">All Notifications</option>
              <option value="sent">Delivered (Sent)</option>
              <option value="queued">Queued / Processing</option>
              <option value="failed">Failed</option>
            </select>
          </div>
          <button
            type="button"
            onClick={loadDeliveries}
            className="px-3 py-1.5 text-xs font-medium border border-gray-300 dark:border-gray-700 rounded hover:bg-gray-50 dark:hover:bg-gray-800"
          >
            Refresh
          </button>
        </div>

        {loading ? (
          <div className="flex justify-center py-12">
            <LoadingSpinner label="Loading notification logs…" />
          </div>
        ) : (
          <div className="bg-white dark:bg-gray-900 shadow rounded-lg overflow-hidden border border-gray-200 dark:border-gray-800">
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-800">
                <thead className="bg-gray-50 dark:bg-gray-800/50">
                  <tr>
                    <th className="px-6 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">
                      Message / Topic
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">
                      Channel
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">
                      Recipient
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">
                      Status
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-semibold text-gray-500 uppercase tracking-wider">
                      Dispatched
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-200 dark:divide-gray-800">
                  {deliveries.length === 0 ? (
                    <tr>
                      <td colSpan={5} className="px-6 py-8 text-center text-sm text-gray-500">
                        No notifications recorded for this organization account.
                      </td>
                    </tr>
                  ) : (
                    deliveries.map((del) => (
                      <tr key={del.id} className="hover:bg-gray-50 dark:hover:bg-gray-800/40">
                        <td className="px-6 py-4 whitespace-nowrap">
                          <div className="font-medium text-gray-900 dark:text-white">
                            {del.template_name || del.template_code}
                          </div>
                          <div className="text-xs text-gray-500 font-mono">{del.template_code}</div>
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-600 dark:text-gray-300 uppercase">
                          {del.channel}
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-700 dark:text-gray-300 font-mono">
                          {del.recipient_email}
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap">
                          <span
                            className={`inline-flex px-2 py-0.5 rounded text-xs font-semibold uppercase ${
                              del.status === "sent"
                                ? "bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400"
                                : del.status === "failed"
                                ? "bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400"
                                : "bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400"
                            }`}
                          >
                            {del.status}
                          </span>
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                          {del.sent_at
                            ? new Date(del.sent_at).toLocaleString()
                            : new Date(del.queued_at).toLocaleString()}
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>
    </AppShell>
  );
};
