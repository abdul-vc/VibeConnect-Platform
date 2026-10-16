import React, { useEffect, useState } from "react";
import { AppShell } from "../../components/AppShell.tsx";
import { tenantHomeApi } from "../../api/tenantHome.ts";
import type { TenantHomeResponse } from "../../api/types.ts";
import { LoadingSpinner } from "../../components/LoadingSpinner.tsx";
import { BuildingIcon, UserIcon, ShieldCheckIcon } from "../../components/Icons.tsx";

export const TenantProfilePage: React.FC = () => {
  const [data, setData] = useState<TenantHomeResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    const fetchProfile = async () => {
      try {
        const res = await tenantHomeApi.getTenantHome();
        if (active) setData(res);
      } catch (err: unknown) {
        if (active) setError(err instanceof Error ? err.message : "Failed to load organization profile.");
      } finally {
        if (active) setLoading(false);
      }
    };
    void fetchProfile();
    return () => {
      active = false;
    };
  }, []);

  return (
    <AppShell>
      <div style={{ maxWidth: "1080px", margin: "0 auto", padding: "1.75rem 1rem" }}>
        <div style={{ marginBottom: "1.75rem" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <BuildingIcon size={24} color="var(--brand-primary, #6366f1)" />
            <h1 style={{ fontSize: "1.5rem", fontWeight: 800, margin: 0, color: "var(--text-primary)" }}>
              Organization Profile & Structure
            </h1>
          </div>
          <p style={{ color: "var(--text-muted)", fontSize: "0.88rem", marginTop: 4 }}>
            Authoritative organization profile, administrative structure, and tenant isolation parameters.
          </p>
        </div>

        {error && (
          <div style={{ padding: "0.85rem 1rem", background: "rgba(239, 68, 68, 0.1)", border: "1px solid rgba(239, 68, 68, 0.3)", borderRadius: 8, color: "#f87171", marginBottom: "1.25rem", fontSize: "0.88rem" }}>
            {error}
          </div>
        )}

        {loading ? (
          <div style={{ display: "flex", justifyContent: "center", padding: "4rem" }}>
            <LoadingSpinner label="Loading organization profile…" />
          </div>
        ) : data ? (
          <div style={{ display: "grid", gridTemplateColumns: "1fr", gap: "1.5rem" }}>
            {/* Primary Details Card */}
            <div
              style={{
                background: "var(--surface-card, #1e293b)",
                border: "1px solid var(--border-glass, rgba(255, 255, 255, 0.1))",
                borderRadius: 14,
                padding: "1.5rem",
              }}
            >
              <h2 style={{ fontSize: "1.1rem", fontWeight: 700, margin: "0 0 1.25rem 0", color: "var(--text-primary)" }}>
                Organization Identity
              </h2>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: "1.25rem", fontSize: "0.88rem" }}>
                <div>
                  <span style={{ color: "var(--text-muted)", display: "block", fontSize: "0.78rem" }}>Organization Name</span>
                  <strong style={{ fontSize: "1rem" }}>{data.organization.name}</strong>
                </div>
                <div>
                  <span style={{ color: "var(--text-muted)", display: "block", fontSize: "0.78rem" }}>Organization Code</span>
                  <code>{data.organization.code}</code>
                </div>
                <div>
                  <span style={{ color: "var(--text-muted)", display: "block", fontSize: "0.78rem" }}>Tenant ID</span>
                  <code style={{ fontSize: "0.75rem" }}>{data.organization.id}</code>
                </div>
                <div>
                  <span style={{ color: "var(--text-muted)", display: "block", fontSize: "0.78rem" }}>Operational Status</span>
                  <span
                    style={{
                      display: "inline-block",
                      padding: "2px 10px",
                      borderRadius: 999,
                      fontSize: "0.75rem",
                      fontWeight: 700,
                      background: "rgba(34, 197, 94, 0.15)",
                      color: "#4ade80",
                      textTransform: "uppercase",
                    }}
                  >
                    {data.organization.status}
                  </span>
                </div>
              </div>
              {data.organization.description && (
                <div style={{ marginTop: "1rem", paddingTop: "1rem", borderTop: "1px solid var(--border-glass, rgba(255, 255, 255, 0.08))", fontSize: "0.88rem", color: "var(--text-secondary)" }}>
                  {data.organization.description}
                </div>
              )}
            </div>

            {/* Membership & Administrative Role */}
            <div
              style={{
                background: "var(--surface-card, #1e293b)",
                border: "1px solid var(--border-glass, rgba(255, 255, 255, 0.1))",
                borderRadius: 14,
                padding: "1.5rem",
              }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: "1.25rem" }}>
                <UserIcon size={18} color="var(--brand-primary, #6366f1)" />
                <h2 style={{ fontSize: "1.1rem", fontWeight: 700, margin: 0, color: "var(--text-primary)" }}>
                  Current Session Membership
                </h2>
              </div>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: "1rem", fontSize: "0.88rem" }}>
                <div>
                  <span style={{ color: "var(--text-muted)", display: "block", fontSize: "0.78rem" }}>Membership Type</span>
                  <strong>{data.membership.membership_type}</strong>
                </div>
                <div>
                  <span style={{ color: "var(--text-muted)", display: "block", fontSize: "0.78rem" }}>Assigned Role</span>
                  <strong>{data.membership.role?.name || "System Administrator"}</strong>
                </div>
                <div>
                  <span style={{ color: "var(--text-muted)", display: "block", fontSize: "0.78rem" }}>Membership Status</span>
                  <span style={{ color: "#4ade80", fontWeight: 600 }}>{data.membership.status}</span>
                </div>
                <div>
                  <span style={{ color: "var(--text-muted)", display: "block", fontSize: "0.78rem" }}>Joined Date</span>
                  <span>{data.membership.joined_at ? new Date(data.membership.joined_at).toLocaleDateString() : "Active"}</span>
                </div>
              </div>
            </div>

            {/* Seat Capacity Overview */}
            <div
              style={{
                background: "var(--surface-card, #1e293b)",
                border: "1px solid var(--border-glass, rgba(255, 255, 255, 0.1))",
                borderRadius: 14,
                padding: "1.5rem",
              }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: "1.25rem" }}>
                <ShieldCheckIcon size={18} color="var(--brand-primary, #6366f1)" />
                <h2 style={{ fontSize: "1.1rem", fontWeight: 700, margin: 0, color: "var(--text-primary)" }}>
                  License & Seat Structure
                </h2>
              </div>
              <div style={{ fontSize: "0.92rem", marginBottom: "1rem" }}>
                Total Assigned Seats: <strong>{data.seat_summary?.total_assigned_seats ?? 0}</strong>
              </div>
              {data.seat_summary?.products && data.seat_summary.products.length > 0 && (
                <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                  {data.seat_summary.products.map((p) => (
                    <div
                      key={p.product_id}
                      style={{
                        padding: "0.75rem 1rem",
                        background: "var(--surface-raised, #0f172a)",
                        border: "1px solid var(--border-glass, rgba(255, 255, 255, 0.08))",
                        borderRadius: 8,
                        display: "flex",
                        justifyContent: "space-between",
                        alignItems: "center",
                        fontSize: "0.85rem",
                      }}
                    >
                      <span><strong>{p.product_name}</strong> ({p.product_code})</span>
                      <span>
                        Consumed: <strong>{p.consumed_seats}</strong> / Limit: {p.total_limit ?? "Unlimited"}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        ) : null}
      </div>
    </AppShell>
  );
};
