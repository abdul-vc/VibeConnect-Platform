/**
 * Platform Owner White Labeling Page (Phase 4A/4B).
 *
 * Route: /white-labeling
 * Context Guard: platform_owner
 */

import React, { useState, useEffect } from "react";
import { Link } from "react-router-dom";
import { AppShell } from "../../components/AppShell.tsx";
import { BrandingWorkspace } from "../../components/branding/BrandingWorkspace.tsx";
import { organizationsApi } from "../../api/organizations.ts";
import type { OrganizationListItem } from "../../api/types.ts";

export const WhiteLabelingPage: React.FC = () => {
  const [organizations, setOrganizations] = useState<readonly OrganizationListItem[]>([]);
  const [selectedOrgId, setSelectedOrgId] = useState<string>("");

  useEffect(() => {
    organizationsApi.list({ page_size: 100 }).then((res) => {
      setOrganizations(res.results || []);
    }).catch(() => {
      // Graceful fallback
    });
  }, []);

  const selectedOrg = organizations.find((o) => o.id === selectedOrgId);

  return (
    <AppShell>
      <div style={{ padding: "2rem 2rem 0", maxWidth: "1400px", margin: "0 auto" }}>
        {/* Breadcrumbs & Profile Scope */}
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "1rem", marginBottom: "0.5rem" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", fontSize: "0.8125rem", color: "var(--text-muted)", fontWeight: 500 }}>
            <Link to="/" style={{ color: "var(--text-muted)", textDecoration: "none", transition: "color 0.15s" }}>Platform Owner</Link>
            <span>/</span>
            <span>Platform</span>
            <span>/</span>
            <span style={{ color: "var(--brand-primary)", fontWeight: 600 }}>White Labeling & Brand Control</span>
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
            <label htmlFor="select-org-profile" style={{ fontSize: "0.8125rem", color: "var(--text-secondary)", fontWeight: 500 }}>
              Profile Scope:
            </label>
          <select
            id="select-org-profile"
            value={selectedOrgId}
            onChange={(e) => setSelectedOrgId(e.target.value)}
            style={{
              padding: "0.375rem 0.75rem",
              borderRadius: "6px",
              background: "var(--glass-surface-elevated)",
              border: "1px solid var(--border-glass)",
              color: "var(--text-primary)",
              fontSize: "0.8125rem",
            }}
          >
            <option value="">Global Default Branding</option>
            {organizations.map((org) => (
              <option key={org.id} value={org.id}>
                Tenant: {org.name} ({org.code})
              </option>
            ))}
          </select>
        </div>
      </div>

      <BrandingWorkspace
        key={selectedOrgId || "global"}
        title="White Labeling & Brand Control"
        subtitle="Manage global LMS styling defaults and tenant-specific white labeling overrides."
        isOwner={true}
        organizationId={selectedOrgId || undefined}
        organizationName={selectedOrg?.name}
      />
    </div>
  </AppShell>
  );
};
