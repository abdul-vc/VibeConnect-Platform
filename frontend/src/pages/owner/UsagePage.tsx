/**
 * Platform Owner Usage & Metering Page (Phase 4C).
 *
 * Route: /usage
 * Context Guard: platform_owner
 */

import React, { useState, useEffect, useCallback } from "react";
import { Link } from "react-router-dom";
import { AppShell } from "../../components/AppShell.tsx";
import { usageApi, type OwnerUsageBucket } from "../../api/usage.ts";
import { LoadingSpinner } from "../../components/LoadingSpinner.tsx";
import { GridIcon, RefreshIcon } from "../../components/Icons.tsx";

export const UsagePage: React.FC = () => {
  const [buckets, setBuckets] = useState<OwnerUsageBucket[]>([]);
  const [totalCount, setTotalCount] = useState<number>(0);
  const [page, setPage] = useState<number>(1);
  const [pageSize] = useState<number>(15);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const fetchUsageData = useCallback(async (currentPage: number) => {
    setIsLoading(true);
    setErrorMessage(null);
    try {
      const res = await usageApi.getOwnerUsage(currentPage, pageSize);
      setBuckets(res.results || []);
      setTotalCount(res.count || 0);
    } catch (err: unknown) {
      const msg = err && typeof err === "object" && "message" in err
        ? String((err as { message: string }).message)
        : "Failed to load usage data.";
      setErrorMessage(msg);
    } finally {
      setIsLoading(false);
    }
  }, [pageSize]);

  useEffect(() => {
    void fetchUsageData(page);
  }, [page, fetchUsageData]);

  const totalPages = Math.ceil(totalCount / pageSize) || 1;

  return (
    <AppShell>
      <div style={{ padding: "2rem", maxWidth: "1400px", margin: "0 auto" }}>
        {/* Breadcrumb Navigation */}
        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", fontSize: "0.8125rem", color: "var(--text-muted)", marginBottom: "1.25rem", fontWeight: 500 }}>
          <Link to="/" style={{ color: "var(--text-muted)", textDecoration: "none", transition: "color 0.15s" }}>Platform Owner</Link>
          <span>/</span>
          <span>Platform</span>
          <span>/</span>
          <span style={{ color: "var(--brand-primary)", fontWeight: 600 }}>Usage & Metering</span>
        </div>

        {/* Header */}
        <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", flexWrap: "wrap", gap: "1rem", marginBottom: "2rem" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "1rem" }}>
            <div
              style={{
                width: 48,
                height: 48,
                borderRadius: 14,
                background: "linear-gradient(135deg, rgba(56, 103, 245, 0.15) 0%, rgba(139, 92, 246, 0.15) 100%)",
                border: "1px solid rgba(56, 103, 245, 0.25)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                color: "var(--brand-primary)",
                boxShadow: "0 4px 12px rgba(56, 103, 245, 0.1)",
              }}
            >
              <GridIcon size={24} />
            </div>
            <div>
              <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
                <h1
                  className="heading-hero"
                  style={{ fontSize: "1.75rem", margin: 0, color: "var(--text-primary)", fontWeight: 800, letterSpacing: "-0.02em" }}
                >
                  Usage & Metering
                </h1>
                <span
                  style={{
                    background: "rgba(56, 103, 245, 0.1)",
                    color: "var(--brand-primary)",
                    padding: "0.2rem 0.65rem",
                    borderRadius: 999,
                    fontSize: "0.75rem",
                    fontWeight: 700,
                    border: "1px solid rgba(56, 103, 245, 0.2)",
                  }}
                >
                  {totalCount} Active Meters
                </span>
              </div>
              <p style={{ margin: "0.25rem 0 0", color: "var(--text-secondary)", fontSize: "0.9375rem" }}>
                Cross-tenant aggregated usage buckets, consumption volume, and quota compliance status.
              </p>
            </div>
          </div>
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            onClick={() => void fetchUsageData(page)}
            disabled={isLoading}
            style={{ display: "inline-flex", alignItems: "center", gap: "0.5rem" }}
          >
            <RefreshIcon size={14} />
            Refresh
          </button>
        </div>

        {/* Error State */}
        {errorMessage && (
          <div
            style={{
              padding: "1rem",
              borderRadius: "8px",
              background: "var(--status-error-bg)",
              color: "var(--status-error)",
              border: "1px solid var(--status-error-border)",
              marginBottom: "1.5rem",
              fontSize: "0.875rem",
            }}
          >
            {errorMessage}
          </div>
        )}

        {/* Content Table Card */}
        <div
          style={{
            background: "var(--glass-surface-elevated)",
            border: "1px solid var(--border-glass)",
            borderRadius: "12px",
            overflow: "hidden",
            boxShadow: "var(--shadow-sm)",
          }}
        >
          {isLoading ? (
            <div style={{ padding: "3rem", display: "flex", justifyContent: "center" }}>
              <LoadingSpinner label="Loading usage buckets..." />
            </div>
          ) : buckets.length === 0 ? (
            <div
              style={{
                padding: "3rem",
                textAlign: "center",
                color: "var(--text-muted)",
                fontSize: "0.9375rem",
              }}
            >
              No usage records found.
            </div>
          ) : (
            <div style={{ overflowX: "auto" }}>
              <table
                style={{
                  width: "100%",
                  borderCollapse: "collapse",
                  textAlign: "left",
                  fontSize: "0.875rem",
                }}
              >
                <thead>
                  <tr
                    style={{
                      borderBottom: "1px solid var(--border-glass)",
                      background: "rgba(255, 255, 255, 0.02)",
                    }}
                  >
                    <th style={{ padding: "0.875rem 1.25rem", color: "var(--text-secondary)", fontWeight: 600 }}>
                      Tenant
                    </th>
                    <th style={{ padding: "0.875rem 1.25rem", color: "var(--text-secondary)", fontWeight: 600 }}>
                      Meter
                    </th>
                    <th style={{ padding: "0.875rem 1.25rem", color: "var(--text-secondary)", fontWeight: 600 }}>
                      Consumed
                    </th>
                    <th style={{ padding: "0.875rem 1.25rem", color: "var(--text-secondary)", fontWeight: 600 }}>
                      Period Window
                    </th>
                    <th style={{ padding: "0.875rem 1.25rem", color: "var(--text-secondary)", fontWeight: 600 }}>
                      Quota Status
                    </th>
                    <th style={{ padding: "0.875rem 1.25rem", color: "var(--text-secondary)", fontWeight: 600 }}>
                      Last Updated
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {buckets.map((b) => (
                    <tr
                      key={b.id}
                      style={{
                        borderBottom: "1px solid var(--border-glass)",
                        transition: "background 0.15s ease",
                      }}
                    >
                      <td style={{ padding: "1rem 1.25rem", fontWeight: 600, color: "var(--text-primary)" }}>
                        {b.organization_name || b.organization_id}
                      </td>
                      <td style={{ padding: "1rem 1.25rem" }}>
                        <div style={{ color: "var(--text-primary)", fontWeight: 500 }}>{b.meter_name}</div>
                        <div style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>{b.meter_key}</div>
                      </td>
                      <td style={{ padding: "1rem 1.25rem", fontWeight: 600, color: "var(--text-primary)" }}>
                        {Number(b.consumed).toLocaleString()} <span style={{ fontSize: "0.8125rem", fontWeight: 400, color: "var(--text-secondary)" }}>{b.unit}</span>
                      </td>
                      <td style={{ padding: "1rem 1.25rem", color: "var(--text-secondary)", fontSize: "0.8125rem" }}>
                        {new Date(b.period_start).toLocaleDateString()} - {new Date(b.period_end).toLocaleDateString()}
                      </td>
                      <td style={{ padding: "1rem 1.25rem" }}>
                        <span
                          style={{
                            display: "inline-flex",
                            alignItems: "center",
                            padding: "0.2rem 0.5rem",
                            borderRadius: "4px",
                            fontSize: "0.75rem",
                            fontWeight: 600,
                            textTransform: "uppercase",
                            background: b.is_over_limit ? "var(--status-error-bg)" : "var(--status-success-bg)",
                            color: b.is_over_limit ? "var(--status-error)" : "var(--status-success)",
                            border: `1px solid ${b.is_over_limit ? "var(--status-error-border)" : "var(--status-success-border)"}`,
                          }}
                        >
                          {b.is_over_limit ? "Over Limit" : "Within Limit"}
                        </span>
                      </td>
                      <td style={{ padding: "1rem 1.25rem", color: "var(--text-muted)", fontSize: "0.8125rem" }}>
                        {new Date(b.updated_at).toLocaleString()}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* Pagination */}
          {!isLoading && buckets.length > 0 && (
            <div
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                padding: "1rem 1.25rem",
                borderTop: "1px solid var(--border-glass)",
                fontSize: "0.875rem",
                color: "var(--text-secondary)",
              }}
            >
              <div>
                Showing {((page - 1) * pageSize) + 1} to {Math.min(page * pageSize, totalCount)} of {totalCount} records
              </div>
              <div style={{ display: "flex", gap: "0.5rem" }}>
                <button
                  type="button"
                  className="btn btn-secondary btn-sm"
                  disabled={page <= 1}
                  onClick={() => setPage((p) => Math.max(p - 1, 1))}
                >
                  Previous
                </button>
                <span style={{ padding: "0.4rem 0.75rem", fontWeight: 600, color: "var(--text-primary)" }}>
                  {page} / {totalPages}
                </span>
                <button
                  type="button"
                  className="btn btn-secondary btn-sm"
                  disabled={page >= totalPages}
                  onClick={() => setPage((p) => Math.min(p + 1, totalPages))}
                >
                  Next
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </AppShell>
  );
};
