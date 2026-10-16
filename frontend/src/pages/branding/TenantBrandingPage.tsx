/**
 * Tenant Organization Branding Page (Phase 4A/4B).
 *
 * Route: /tenant/branding
 * Context Guard: tenant
 */

import React from "react";
import { AppShell } from "../../components/AppShell.tsx";
import { BrandingWorkspace } from "../../components/branding/BrandingWorkspace.tsx";
import { useAuth } from "../../context/AuthContext.tsx";

export const TenantBrandingPage: React.FC = () => {
  const { user } = useAuth();
  const organization = user?.active_context?.organization;

  return (
    <AppShell>
      <BrandingWorkspace
        title="Organization Branding"
        subtitle="Customize your organization's theme colors, logo, and brand assets."
        isOwner={false}
        organizationId={organization?.id}
        organizationName={organization?.name}
      />
    </AppShell>
  );
};
