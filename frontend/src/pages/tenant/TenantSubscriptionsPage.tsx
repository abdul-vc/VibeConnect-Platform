import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { AppShell } from "../../components/AppShell.tsx";
import { billingApi, type BillingAccount } from "../../api/billing.ts";
import { subscriptionsApi } from "../../api/subscriptions.ts";
import type { SubscriptionListItem } from "../../api/types.ts";
import { LoadingSpinner } from "../../components/LoadingSpinner.tsx";
import { CreditCardIcon, LayersIcon } from "../../components/Icons.tsx";

export const TenantSubscriptionsPage: React.FC = () => {
  const [account, setAccount] = useState<BillingAccount | null>(null);
  const [subscription, setSubscription] = useState<SubscriptionListItem | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    const fetchSubscriptionData = async () => {
      try {
        const [accRes, subListRes] = await Promise.allSettled([
          billingApi.getTenantBillingAccount(),
          subscriptionsApi.list({ page_size: 1 }),
        ]);

        if (active) {
          if (accRes.status === "fulfilled") {
            setAccount(accRes.value);
          }
          if (subListRes.status === "fulfilled" && subListRes.value.results.length > 0) {
            setSubscription(subListRes.value.results[0]);
          }
        }
      } catch (err: unknown) {
        if (active) setError(err instanceof Error ? err.message : "Failed to load subscription details.");
      } finally {
        if (active) setLoading(false);
      }
    };
    void fetchSubscriptionData();
    return () => {
      active = false;
    };
  }, []);

  return (
    <AppShell>
      <div style={{ maxWidth: "1080px", margin: "0 auto", padding: "1.75rem 1rem" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "1.75rem" }}>
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <CreditCardIcon size={24} color="var(--brand-primary, #6366f1)" />
              <h1 style={{ fontSize: "1.5rem", fontWeight: 800, margin: 0, color: "var(--text-primary)" }}>
                Plan & Subscription
              </h1>
            </div>
            <p style={{ color: "var(--text-muted)", fontSize: "0.88rem", marginTop: 4 }}>
              Active SaaS subscription plan, billing lifecycle status, and quota entitlements.
            </p>
          </div>
          <Link
            to="/tenant/billing"
            className="btn-secondary"
            style={{ textDecoration: "none", display: "inline-flex", alignItems: "center", gap: 6, padding: "0.45rem 0.9rem", fontSize: "0.82rem" }}
          >
            Invoices & Payment History →
          </Link>
        </div>

        {error && (
          <div style={{ padding: "0.85rem 1rem", background: "rgba(239, 68, 68, 0.1)", border: "1px solid rgba(239, 68, 68, 0.3)", borderRadius: 8, color: "#f87171", marginBottom: "1.25rem", fontSize: "0.88rem" }}>
            {error}
          </div>
        )}

        {loading ? (
          <div style={{ display: "flex", justifyContent: "center", padding: "4rem" }}>
            <LoadingSpinner label="Loading subscription information…" />
          </div>
        ) : (
          <div style={{ display: "grid", gridTemplateColumns: "1fr", gap: "1.5rem" }}>
            {/* Active Subscription Overview */}
            <div
              style={{
                background: "var(--surface-card, #1e293b)",
                border: "1px solid var(--border-glass, rgba(255, 255, 255, 0.1))",
                borderRadius: 14,
                padding: "1.5rem",
              }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1.25rem" }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <LayersIcon size={20} color="var(--brand-primary, #6366f1)" />
                  <h2 style={{ fontSize: "1.1rem", fontWeight: 700, margin: 0, color: "var(--text-primary)" }}>
                    {subscription ? "Current Active Plan" : "Organization Billing Status"}
                  </h2>
                </div>
                <span
                  style={{
                    display: "inline-block",
                    padding: "3px 12px",
                    borderRadius: 999,
                    fontSize: "0.75rem",
                    fontWeight: 700,
                    background: (subscription?.status === "active" || account?.status === "active") ? "rgba(34, 197, 94, 0.15)" : "rgba(245, 158, 11, 0.15)",
                    color: (subscription?.status === "active" || account?.status === "active") ? "#4ade80" : "#fbbf24",
                    textTransform: "uppercase",
                  }}
                >
                  {subscription?.status || account?.status || "standard"}
                </span>
              </div>

              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: "1.25rem", fontSize: "0.88rem" }}>
                <div>
                  <span style={{ color: "var(--text-muted)", display: "block", fontSize: "0.78rem" }}>Plan Tier</span>
                  <strong style={{ fontSize: "1.1rem" }}>
                    {subscription?.plan_name_snapshot || "Standard Enterprise Tier"}
                  </strong>
                  <div style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>
                    Code: {subscription?.plan_code_snapshot || "standard-tier"}
                  </div>
                </div>
                <div>
                  <span style={{ color: "var(--text-muted)", display: "block", fontSize: "0.78rem" }}>Billing Cycle & Interval</span>
                  <strong style={{ textTransform: "capitalize" }}>
                    {subscription?.billing_interval || "Monthly"}
                  </strong>
                  <div style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>
                    Currency: {subscription?.currency?.toUpperCase() || account?.currency || "USD"}
                  </div>
                </div>
                <div>
                  <span style={{ color: "var(--text-muted)", display: "block", fontSize: "0.78rem" }}>Current Period Start</span>
                  <span>{subscription?.current_period_start ? new Date(subscription.current_period_start).toLocaleDateString() : (account?.created_at ? new Date(account.created_at).toLocaleDateString() : "—")}</span>
                </div>
                <div>
                  <span style={{ color: "var(--text-muted)", display: "block", fontSize: "0.78rem" }}>Current Period End</span>
                  <span>{subscription?.current_period_end ? new Date(subscription.current_period_end).toLocaleDateString() : "Continuous"}</span>
                </div>
              </div>
            </div>

            {/* Quick Links */}
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "1fr 1fr",
                gap: "1rem",
              }}
            >
              <Link
                to="/tenant/usage"
                style={{
                  background: "var(--surface-raised, #0f172a)",
                  border: "1px solid var(--border-glass, rgba(255, 255, 255, 0.1))",
                  borderRadius: 12,
                  padding: "1.25rem",
                  textDecoration: "none",
                  color: "inherit",
                }}
              >
                <h3 style={{ fontSize: "0.95rem", fontWeight: 700, margin: "0 0 6px 0", color: "var(--text-primary)" }}>
                  Usage & Quotas →
                </h3>
                <p style={{ margin: 0, fontSize: "0.82rem", color: "var(--text-muted)" }}>
                  Review API invocations, storage usage, and active learner meters against your subscription limits.
                </p>
              </Link>
              <Link
                to="/tenant/marketplace"
                style={{
                  background: "var(--surface-raised, #0f172a)",
                  border: "1px solid var(--border-glass, rgba(255, 255, 255, 0.1))",
                  borderRadius: 12,
                  padding: "1.25rem",
                  textDecoration: "none",
                  color: "inherit",
                }}
              >
                <h3 style={{ fontSize: "0.95rem", fontWeight: 700, margin: "0 0 6px 0", color: "var(--text-primary)" }}>
                  Explore Product Add-ons →
                </h3>
                <p style={{ margin: 0, fontSize: "0.82rem", color: "var(--text-muted)" }}>
                  Browse published catalog products and request access for additional modules.
                </p>
              </Link>
            </div>
          </div>
        )}
      </div>
    </AppShell>
  );
};
