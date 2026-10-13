import React from "react";
import { AppShell } from "../../components/AppShell.tsx";
import { useAuth } from "../../context/AuthContext.tsx";
import { ShieldCheckIcon, UserIcon } from "../../components/Icons.tsx";

export const TenantSecurityPage: React.FC = () => {
  const { user } = useAuth();

  return (
    <AppShell>
      <div style={{ maxWidth: "1080px", margin: "0 auto", padding: "1.75rem 1rem" }}>
        <div style={{ marginBottom: "1.75rem" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <ShieldCheckIcon size={24} color="var(--brand-primary, #6366f1)" />
            <h1 style={{ fontSize: "1.5rem", fontWeight: 800, margin: 0, color: "var(--text-primary)" }}>
              Security & Session Governance
            </h1>
          </div>
          <p style={{ color: "var(--text-muted)", fontSize: "0.88rem", marginTop: 4 }}>
            Platform-enforced security baseline, tenant cryptographic isolation, and active session diagnostics.
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
            <strong>Governance Notice:</strong> Security baselines (30m session inactivity timeout, SameSite CSRF cookies, and audited impersonation logging) are enforced platform-wide to guarantee SOC2/multi-tenant compliance. Individual tenant overrides are managed under Platform Owner oversight.
          </div>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "1fr", gap: "1.5rem" }}>
          {/* Active Session Status */}
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
                Current Authenticated Session
              </h2>
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: "1.25rem", fontSize: "0.88rem" }}>
              <div>
                <span style={{ color: "var(--text-muted)", display: "block", fontSize: "0.78rem" }}>Authenticated User</span>
                <strong>{user?.email}</strong>
              </div>
              <div>
                <span style={{ color: "var(--text-muted)", display: "block", fontSize: "0.78rem" }}>Active Organization Context</span>
                <strong>{user?.active_context?.organization?.name || "Active"}</strong>
              </div>
              <div>
                <span style={{ color: "var(--text-muted)", display: "block", fontSize: "0.78rem" }}>Context Type</span>
                <span
                  style={{
                    display: "inline-block",
                    padding: "2px 8px",
                    borderRadius: 999,
                    fontSize: "0.72rem",
                    fontWeight: 700,
                    background: "rgba(99, 102, 241, 0.15)",
                    color: "#818cf8",
                    textTransform: "uppercase",
                  }}
                >
                  {user?.active_context?.type || "tenant"}
                </span>
              </div>
              <div>
                <span style={{ color: "var(--text-muted)", display: "block", fontSize: "0.78rem" }}>Isolation Level</span>
                <span style={{ color: "#4ade80", fontWeight: 600 }}>Strict Multi-Tenant Isolation</span>
              </div>
            </div>
          </div>

          {/* Security Enforcement Policies */}
          <div
            style={{
              background: "var(--surface-card, #1e293b)",
              border: "1px solid var(--border-glass, rgba(255, 255, 255, 0.1))",
              borderRadius: 14,
              padding: "1.5rem",
            }}
          >
            <h2 style={{ fontSize: "1.1rem", fontWeight: 700, margin: "0 0 1rem 0", color: "var(--text-primary)" }}>
              Active Security Controls
            </h2>

            <div style={{ display: "flex", flexDirection: "column", gap: 10, fontSize: "0.88rem" }}>
              <div style={{ padding: "0.75rem 1rem", background: "var(--surface-raised, #0f172a)", borderRadius: 8, border: "1px solid var(--border-glass, rgba(255, 255, 255, 0.08))" }}>
                <strong>Session Inactivity Policy:</strong> Automatic expiration after 30 minutes of idle inactivity.
              </div>
              <div style={{ padding: "0.75rem 1rem", background: "var(--surface-raised, #0f172a)", borderRadius: 8, border: "1px solid var(--border-glass, rgba(255, 255, 255, 0.08))" }}>
                <strong>CSRF Protection:</strong> Enforced SameSite Double-Submit cookie validation on all mutating API calls.
              </div>
              <div style={{ padding: "0.75rem 1rem", background: "var(--surface-raised, #0f172a)", borderRadius: 8, border: "1px solid var(--border-glass, rgba(255, 255, 255, 0.08))" }}>
                <strong>Audited Support Impersonation Protection:</strong> Any authorized support operator action is governed by ticket-referenced mandatory justification and displays an omnipresent visual notification banner.
              </div>
              <div style={{ padding: "0.75rem 1rem", background: "var(--surface-raised, #0f172a)", borderRadius: 8, border: "1px solid var(--border-glass, rgba(255, 255, 255, 0.08))" }}>
                <strong>Credential Storage:</strong> Argon2 / PBKDF2 cryptographic hashing; no plaintext password or API key secrets stored.
              </div>
            </div>
          </div>
        </div>
      </div>
    </AppShell>
  );
};
