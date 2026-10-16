import React, { useEffect, useState } from "react";
import { AppShell } from "../../components/AppShell.tsx";
import { tenantHomeApi } from "../../api/tenantHome.ts";
import { organizationsApi } from "../../api/organizations.ts";
import type { TenantHomeResponse } from "../../api/types.ts";
import { LoadingSpinner } from "../../components/LoadingSpinner.tsx";
import { SlidersIcon, CheckCircleIcon } from "../../components/Icons.tsx";

export const TenantSettingsPage: React.FC = () => {
  const [data, setData] = useState<TenantHomeResponse | null>(null);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    const fetchOrg = async () => {
      try {
        const res = await tenantHomeApi.getTenantHome();
        if (active) {
          setData(res);
          setName(res.organization.name || "");
          // fetch full org description if available
          try {
            const orgDetail = await organizationsApi.get(res.organization.id);
            if (active && orgDetail.description) {
              setDescription(orgDetail.description);
            }
          } catch {
            // If tenant admin cannot read owner org detail endpoint, keep description empty
          }
        }
      } catch (err: unknown) {
        if (active) setError(err instanceof Error ? err.message : "Failed to load tenant settings.");
      } finally {
        if (active) setLoading(false);
      }
    };
    void fetchOrg();
    return () => {
      active = false;
    };
  }, []);

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!data?.organization?.id) return;
    setSaving(true);
    setError(null);
    setSuccessMsg(null);
    try {
      await organizationsApi.update(data.organization.id, {
        name: name.trim(),
        description: description.trim(),
      });
      setSuccessMsg("Organization settings updated successfully.");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to update organization settings.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <AppShell>
      <div style={{ maxWidth: "860px", margin: "0 auto", padding: "1.75rem 1rem" }}>
        <div style={{ marginBottom: "1.75rem" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <SlidersIcon size={24} color="var(--brand-primary, #6366f1)" />
            <h1 style={{ fontSize: "1.5rem", fontWeight: 800, margin: 0, color: "var(--text-primary)" }}>
              Tenant Settings
            </h1>
          </div>
          <p style={{ color: "var(--text-muted)", fontSize: "0.88rem", marginTop: 4 }}>
            Manage organization display metadata, branding preferences, and tenant-scoped configuration.
          </p>
        </div>

        {error && (
          <div
            style={{
              padding: "0.85rem 1rem",
              background: "rgba(239, 68, 68, 0.1)",
              border: "1px solid rgba(239, 68, 68, 0.3)",
              borderRadius: 8,
              color: "#f87171",
              marginBottom: "1.25rem",
              fontSize: "0.88rem",
            }}
          >
            {error}
          </div>
        )}

        {successMsg && (
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 8,
              padding: "0.85rem 1rem",
              background: "rgba(34, 197, 94, 0.1)",
              border: "1px solid rgba(34, 197, 94, 0.3)",
              borderRadius: 8,
              color: "#4ade80",
              marginBottom: "1.25rem",
              fontSize: "0.88rem",
            }}
          >
            <CheckCircleIcon size={18} color="#4ade80" />
            <span>{successMsg}</span>
          </div>
        )}

        {loading ? (
          <div style={{ display: "flex", justifyContent: "center", padding: "4rem" }}>
            <LoadingSpinner label="Loading tenant settings…" />
          </div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }}>
            {/* General Settings Form */}
            <div
              style={{
                background: "var(--surface-card, #1e293b)",
                border: "1px solid var(--border-glass, rgba(255, 255, 255, 0.1))",
                borderRadius: 14,
                padding: "1.5rem",
              }}
            >
              <h2 style={{ fontSize: "1.1rem", fontWeight: 700, margin: "0 0 1.25rem 0", color: "var(--text-primary)" }}>
                Organization Profile Settings
              </h2>
              <form onSubmit={handleSave} style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>
                <div>
                  <label style={{ display: "block", fontSize: "0.82rem", fontWeight: 600, color: "var(--text-muted)", marginBottom: 6 }}>
                    Organization Name
                  </label>
                  <input
                    type="text"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    required
                    style={{
                      width: "100%",
                      padding: "0.65rem 0.85rem",
                      borderRadius: 8,
                      border: "1px solid var(--border-glass, rgba(255, 255, 255, 0.15))",
                      background: "rgba(0, 0, 0, 0.2)",
                      color: "var(--text-primary, #fff)",
                      fontSize: "0.9rem",
                    }}
                  />
                </div>

                <div>
                  <label style={{ display: "block", fontSize: "0.82rem", fontWeight: 600, color: "var(--text-muted)", marginBottom: 6 }}>
                    Organization Description
                  </label>
                  <textarea
                    rows={3}
                    value={description}
                    onChange={(e) => setDescription(e.target.value)}
                    placeholder="Enter an optional description for this tenant organization..."
                    style={{
                      width: "100%",
                      padding: "0.65rem 0.85rem",
                      borderRadius: 8,
                      border: "1px solid var(--border-glass, rgba(255, 255, 255, 0.15))",
                      background: "rgba(0, 0, 0, 0.2)",
                      color: "var(--text-primary, #fff)",
                      fontSize: "0.9rem",
                      resize: "vertical",
                    }}
                  />
                </div>

                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem" }}>
                  <div>
                    <label style={{ display: "block", fontSize: "0.82rem", fontWeight: 600, color: "var(--text-muted)", marginBottom: 4 }}>
                      Organization Code (Immutable)
                    </label>
                    <input
                      type="text"
                      value={data?.organization.code || ""}
                      disabled
                      style={{
                        width: "100%",
                        padding: "0.6rem 0.85rem",
                        borderRadius: 8,
                        border: "1px solid rgba(255, 255, 255, 0.08)",
                        background: "rgba(255, 255, 255, 0.05)",
                        color: "var(--text-muted)",
                        fontSize: "0.85rem",
                        cursor: "not-allowed",
                      }}
                    />
                  </div>
                  <div>
                    <label style={{ display: "block", fontSize: "0.82rem", fontWeight: 600, color: "var(--text-muted)", marginBottom: 4 }}>
                      Tenant Identifier
                    </label>
                    <input
                      type="text"
                      value={data?.organization.id || ""}
                      disabled
                      style={{
                        width: "100%",
                        padding: "0.6rem 0.85rem",
                        borderRadius: 8,
                        border: "1px solid rgba(255, 255, 255, 0.08)",
                        background: "rgba(255, 255, 255, 0.05)",
                        color: "var(--text-muted)",
                        fontSize: "0.85rem",
                        cursor: "not-allowed",
                      }}
                    />
                  </div>
                </div>

                <div style={{ display: "flex", justifyContent: "flex-end", marginTop: 8 }}>
                  <button
                    type="submit"
                    disabled={saving}
                    style={{
                      padding: "0.6rem 1.5rem",
                      borderRadius: 8,
                      background: "var(--brand-primary, #6366f1)",
                      color: "#fff",
                      border: "none",
                      fontWeight: 600,
                      fontSize: "0.88rem",
                      cursor: saving ? "wait" : "pointer",
                      opacity: saving ? 0.7 : 1,
                    }}
                  >
                    {saving ? "Saving Changes…" : "Save Settings"}
                  </button>
                </div>
              </form>
            </div>

            {/* Tenant Quick Configuration Links */}
            <div
              style={{
                background: "var(--surface-card, #1e293b)",
                border: "1px solid var(--border-glass, rgba(255, 255, 255, 0.1))",
                borderRadius: 14,
                padding: "1.5rem",
              }}
            >
              <h2 style={{ fontSize: "1.1rem", fontWeight: 700, margin: "0 0 1rem 0", color: "var(--text-primary)" }}>
                Tenant Configuration Hub
              </h2>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: "1rem" }}>
                <a
                  href="/tenant/branding"
                  style={{
                    padding: "1rem",
                    borderRadius: 10,
                    background: "rgba(255, 255, 255, 0.03)",
                    border: "1px solid rgba(255, 255, 255, 0.08)",
                    textDecoration: "none",
                    color: "inherit",
                    display: "block",
                  }}
                >
                  <strong style={{ display: "block", color: "var(--text-primary)", fontSize: "0.95rem" }}>Branding & Theme</strong>
                  <span style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>Customize company logos, active color palettes, and portal themes.</span>
                </a>
                <a
                  href="/tenant/sso"
                  style={{
                    padding: "1rem",
                    borderRadius: 10,
                    background: "rgba(255, 255, 255, 0.03)",
                    border: "1px solid rgba(255, 255, 255, 0.08)",
                    textDecoration: "none",
                    color: "inherit",
                    display: "block",
                  }}
                >
                  <strong style={{ display: "block", color: "var(--text-primary)", fontSize: "0.95rem" }}>SSO & Authentication</strong>
                  <span style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>Inspect identity federation and product launcher SSO status.</span>
                </a>
                <a
                  href="/tenant/security"
                  style={{
                    padding: "1rem",
                    borderRadius: 10,
                    background: "rgba(255, 255, 255, 0.03)",
                    border: "1px solid rgba(255, 255, 255, 0.08)",
                    textDecoration: "none",
                    color: "inherit",
                    display: "block",
                  }}
                >
                  <strong style={{ display: "block", color: "var(--text-primary)", fontSize: "0.95rem" }}>Security & Sessions</strong>
                  <span style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>Review session isolation policies and operator impersonation safeguards.</span>
                </a>
              </div>
            </div>
          </div>
        )}
      </div>
    </AppShell>
  );
};
