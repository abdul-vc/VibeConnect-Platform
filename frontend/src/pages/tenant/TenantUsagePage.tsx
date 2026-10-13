/**
 * Tenant Usage & Quotas Page (Phase 4C).
 *
 * Route: /tenant/usage
 * Context Guard: tenant (requires tenant_usage / usage.view)
 */

import React, { useState, useEffect, useCallback } from "react";
import { AppShell } from "../../components/AppShell.tsx";
import { usageApi, type UsageBucketItem } from "../../api/usage.ts";
import { LoadingSpinner } from "../../components/LoadingSpinner.tsx";

export const TenantUsagePage: React.FC = () => {
  const [buckets, setBuckets] = useState<UsageBucketItem[]>([]);
  const [asOf, setAsOf] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const fetchUsage = useCallback(async () => {
    setIsLoading(true);
    setErrorMessage(null);
    try {
      const res = await usageApi.getTenantUsageSummary();
      setBuckets(res.buckets || []);
      setAsOf(res.as_of);
    } catch (err: unknown) {
      const msg = err && typeof err === "object" && "message" in err
        ? String((err as { message: string }).message)
        : "Failed to load usage & quota details.";
      setErrorMessage(msg);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    void fetchUsage();
  }, [fetchUsage]);

  return (
    <AppShell>
      <div style={{ padding: "2rem", maxWidth: "1200px", margin: "0 auto" }}>
        {/* Header */}
        <div style={{ marginBottom: "2rem", display: "flex", justifyContent: "space-between", alignItems: "flex-end" }}>
          <div>
            <h1
              className="heading-hero"
              style={{ fontSize: "1.75rem", margin: "0 0 0.5rem 0", color: "var(--text-primary)" }}
            >
              Usage & Quotas
            </h1>
            <p style={{ margin: 0, color: "var(--text-secondary)", fontSize: "0.9375rem" }}>
              Track resource consumption against your subscribed plan quota entitlements.
            </p>
          </div>
          {asOf && (
            <span style={{ fontSize: "0.8125rem", color: "var(--text-muted)" }}>
              As of {new Date(asOf).toLocaleString()}
            </span>
          )}
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

        {/* Meters Card Grid */}
        {isLoading ? (
          <div style={{ padding: "3rem", display: "flex", justifyContent: "center" }}>
            <LoadingSpinner label="Loading quota consumption..." />
          </div>
        ) : buckets.length === 0 ? (
          <div
            style={{
              background: "var(--glass-surface-elevated)",
              border: "1px solid var(--border-glass)",
              borderRadius: "12px",
              padding: "3rem",
              textAlign: "center",
              color: "var(--text-muted)",
            }}
          >
            No usage meters or quotas recorded for this organization.
          </div>
        ) : (
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))",
              gap: "1.5rem",
            }}
          >
            {buckets.map((b) => {
              const percentage = b.limit ? Math.min(Math.round((b.consumed / b.limit) * 100), 100) : 0;
              const isOver = b.is_over_limit || (b.limit !== null && b.consumed > b.limit);
              const progressColor = isOver
                ? "var(--status-error)"
                : percentage > 80
                ? "var(--status-warning)"
                : "var(--brand-primary)";

              return (
                <div
                  key={b.meter_key}
                  style={{
                    background: "var(--glass-surface-elevated)",
                    border: `1px solid ${isOver ? "var(--status-error-border)" : "var(--border-glass)"}`,
                    borderRadius: "12px",
                    padding: "1.5rem",
                    display: "flex",
                    flexDirection: "column",
                    gap: "1rem",
                    boxShadow: "var(--shadow-sm)",
                  }}
                >
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
                    <div>
                      <h3 style={{ margin: 0, fontSize: "1.125rem", color: "var(--text-primary)" }}>
                        {b.meter_name}
                      </h3>
                      <span style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
                        {b.meter_key} • {b.scope} scope
                      </span>
                    </div>
                    <span
                      style={{
                        padding: "0.2rem 0.5rem",
                        borderRadius: "4px",
                        fontSize: "0.75rem",
                        fontWeight: 600,
                        textTransform: "uppercase",
                        background: isOver ? "var(--status-error-bg)" : "var(--status-success-bg)",
                        color: isOver ? "var(--status-error)" : "var(--status-success)",
                        border: `1px solid ${isOver ? "var(--status-error-border)" : "var(--status-success-border)"}`,
                      }}
                    >
                      {isOver ? "Over Limit" : "Active"}
                    </span>
                  </div>

                  {/* Consumed / Limit */}
                  <div>
                    <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "0.5rem" }}>
                      <span style={{ fontSize: "1.25rem", fontWeight: 700, color: "var(--text-primary)" }}>
                        {Number(b.consumed).toLocaleString()}{" "}
                        <span style={{ fontSize: "0.875rem", fontWeight: 400, color: "var(--text-secondary)" }}>
                          / {b.limit !== null ? `${Number(b.limit).toLocaleString()} ${b.unit}` : `Unlimited ${b.unit}`}
                        </span>
                      </span>
                      {b.limit !== null && (
                        <span style={{ fontSize: "0.875rem", fontWeight: 600, color: progressColor }}>
                          {percentage}%
                        </span>
                      )}
                    </div>

                    {/* Progress Bar using CSS tokens */}
                    {b.limit !== null && (
                      <div
                        style={{
                          height: "8px",
                          width: "100%",
                          borderRadius: "4px",
                          background: "rgba(255, 255, 255, 0.08)",
                          overflow: "hidden",
                        }}
                      >
                        <div
                          style={{
                            height: "100%",
                            width: `${percentage}%`,
                            background: progressColor,
                            borderRadius: "4px",
                            transition: "width 0.3s ease",
                          }}
                        />
                      </div>
                    )}
                  </div>

                  {/* Period */}
                  <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", borderTop: "1px solid var(--border-glass)", paddingTop: "0.75rem" }}>
                    Billing Cycle: {new Date(b.period_start).toLocaleDateString()} - {new Date(b.period_end).toLocaleDateString()}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </AppShell>
  );
};
