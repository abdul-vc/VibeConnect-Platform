import React, { useEffect, useState } from "react";
import { AppShell } from "../../components/AppShell.tsx";
import { apiClient } from "../../api/client.ts";
import { ENDPOINTS } from "../../api/endpoints.ts";
import { LoadingSpinner } from "../../components/LoadingSpinner.tsx";
import { ShieldCheckIcon, AlertCircleIcon, LayersIcon } from "../../components/Icons.tsx";

interface ExternalMappingItem {
  id: string;
  provider: string;
  provider_tenant_id: string;
  status: string;
}

export const TenantSsoPage: React.FC = () => {
  const [mappings, setMappings] = useState<readonly ExternalMappingItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    const fetchSso = async () => {
      try {
        // Attempt to fetch organization external tenant mappings if supported
        const res = await apiClient.get<{ results: ExternalMappingItem[] }>(
          ENDPOINTS.INTEGRATION.TENANT_MAPPINGS,
          { params: { page_size: 50 } }
        ).catch(() => ({ results: [] }));
        if (active) setMappings(res.results || []);
      } catch (err: unknown) {
        if (active) setError(err instanceof Error ? err.message : "Failed to load SSO integration state.");
      } finally {
        if (active) setLoading(false);
      }
    };
    void fetchSso();
    return () => {
      active = false;
    };
  }, []);

  return (
    <AppShell>
      <div style={{ maxWidth: "1080px", margin: "0 auto", padding: "1.75rem 1rem" }}>
        <div style={{ marginBottom: "1.75rem" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <ShieldCheckIcon size={24} color="var(--brand-primary, #6366f1)" />
            <h1 style={{ fontSize: "1.5rem", fontWeight: 800, margin: 0, color: "var(--text-primary)" }}>
              Organization SSO & Identity Federation
            </h1>
          </div>
          <p style={{ color: "var(--text-muted)", fontSize: "0.88rem", marginTop: 4 }}>
            Read-only status of platform SSO federation, token bindings, and external identity bindings for launched products.
          </p>
          <div
            style={{
              marginTop: "0.75rem",
              padding: "0.5rem 0.85rem",
              borderRadius: "6px",
              background: "rgba(99, 102, 241, 0.08)",
              border: "1px solid rgba(99, 102, 241, 0.2)",
              fontSize: "0.8rem",
              color: "var(--text-secondary)",
            }}
          >
            <strong>Platform Architecture Notice:</strong> Custom corporate SAML/OIDC identity provider configuration is centrally governed under Platform Owner oversight. Tenant admins can view active bindings and token parameters below.
          </div>
        </div>

        {error && (
          <div style={{ padding: "0.85rem 1rem", background: "rgba(239, 68, 68, 0.1)", border: "1px solid rgba(239, 68, 68, 0.3)", borderRadius: 8, color: "#f87171", marginBottom: "1.25rem", fontSize: "0.88rem" }}>
            {error}
          </div>
        )}

        {loading ? (
          <div style={{ display: "flex", justifyContent: "center", padding: "4rem" }}>
            <LoadingSpinner label="Loading SSO federation settings…" />
          </div>
        ) : (
          <div style={{ display: "grid", gridTemplateColumns: "1fr", gap: "1.5rem" }}>
            {/* Federation Status Card */}
            <div
              style={{
                background: "var(--surface-card, #1e293b)",
                border: "1px solid var(--border-glass, rgba(255, 255, 255, 0.1))",
                borderRadius: 14,
                padding: "1.5rem",
              }}
            >
              <h2 style={{ fontSize: "1.1rem", fontWeight: 700, margin: "0 0 1rem 0", color: "var(--text-primary)" }}>
                SSO Federation Protocol
              </h2>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: "1.25rem", fontSize: "0.88rem" }}>
                <div>
                  <span style={{ color: "var(--text-muted)", display: "block", fontSize: "0.78rem" }}>Federation Protocol</span>
                  <strong>OpenID Connect / OAuth 2.0 PKCE</strong>
                </div>
                <div>
                  <span style={{ color: "var(--text-muted)", display: "block", fontSize: "0.78rem" }}>Token Binding</span>
                  <strong>Signed RS256 JWT Exchange</strong>
                </div>
                <div>
                  <span style={{ color: "var(--text-muted)", display: "block", fontSize: "0.78rem" }}>Identity Propagation</span>
                  <span style={{ color: "#4ade80", fontWeight: 600 }}>Active (Strict Tenant-Isolated)</span>
                </div>
                <div>
                  <span style={{ color: "var(--text-muted)", display: "block", fontSize: "0.78rem" }}>Session Lifecycle</span>
                  <span>Synchronized with VibeConnect</span>
                </div>
              </div>
            </div>

            {/* Provider Bindings Card */}
            <div
              style={{
                background: "var(--surface-card, #1e293b)",
                border: "1px solid var(--border-glass, rgba(255, 255, 255, 0.1))",
                borderRadius: 14,
                padding: "1.5rem",
              }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: "1rem" }}>
                <LayersIcon size={18} color="var(--brand-primary, #6366f1)" />
                <h2 style={{ fontSize: "1.1rem", fontWeight: 700, margin: 0, color: "var(--text-primary)" }}>
                  Registered External Identity Bindings
                </h2>
              </div>

              {mappings.length === 0 ? (
                <div style={{ fontSize: "0.88rem", color: "var(--text-secondary)", lineHeight: 1.6 }}>
                  <p style={{ margin: "0 0 0.75rem 0" }}>
                    Your organization is bound to platform-level SSO federation for registered workspace applications (including Learning Management System).
                  </p>
                  <div
                    style={{
                      background: "rgba(99, 102, 241, 0.08)",
                      border: "1px solid rgba(99, 102, 241, 0.2)",
                      borderRadius: 8,
                      padding: "0.85rem 1rem",
                      fontSize: "0.82rem",
                      color: "var(--text-muted)",
                      display: "flex",
                      alignItems: "center",
                      gap: 8,
                    }}
                  >
                    <AlertCircleIcon size={16} color="var(--brand-primary, #6366f1)" />
                    <span>External SAML / OIDC corporate identity provider configurations are managed under Platform Owner oversight. Custom tenant identity connectors can be provisioned through the Integration Hub.</span>
                  </div>
                </div>
              ) : (
                <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                  {mappings.map((m) => (
                    <div
                      key={m.id}
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
                      <span>Provider: <strong>{m.provider}</strong></span>
                      <code>Tenant ID: {m.provider_tenant_id}</code>
                      <span style={{ color: "#4ade80", fontWeight: 600 }}>{m.status}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </AppShell>
  );
};
