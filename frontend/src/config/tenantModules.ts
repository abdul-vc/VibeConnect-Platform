/**
 * Tenant Console Module Registry (Phase 2G).
 *
 * Single authoritative specification of all 17 Tenant Admin console modules.
 * Used by AppShell to construct the navigation sidebar and by AppRoutes to
 * enforce permission and module gating without configuration drift.
 */

export interface TenantModuleDefinition {
  readonly id: string;
  readonly label: string;
  readonly icon: "grid" | "box" | "shield" | "layers" | "upload" | "building" | "user" | "credit_card" | "history";
  readonly path: string;
  readonly requiredModule?: string;
  readonly requiredPermission?: string;
  readonly implemented: boolean;
  readonly phase: string;
}

export const TENANT_MODULES_REGISTRY: readonly TenantModuleDefinition[] = [
  {
    id: "dashboard",
    label: "Dashboard",
    icon: "grid",
    path: "/tenant",
    requiredModule: undefined,
    requiredPermission: undefined,
    implemented: true,
    phase: "2G",
  },
  {
    id: "my-products",
    label: "My Products & Launcher",
    icon: "box",
    path: "/tenant/products",
    requiredModule: "tenant_my_products",
    requiredPermission: "products.view",
    implemented: true,
    phase: "2G",
  },
  {
    id: "roles-permissions",
    label: "Roles & Permissions",
    icon: "shield",
    path: "/tenant/roles",
    requiredModule: "tenant_roles",
    requiredPermission: "roles.view",
    implemented: true,
    phase: "2E",
  },
  {
    id: "product-assignments",
    label: "Product Assignments",
    icon: "layers",
    path: "/tenant/assignments",
    requiredModule: "tenant_product_assignments",
    requiredPermission: "assignments.view",
    implemented: true,
    phase: "2F",
  },
  {
    id: "bulk-user-onboarding",
    label: "Bulk User Onboarding",
    icon: "upload",
    path: "/tenant/bulk-import",
    requiredModule: "tenant_bulk_import",
    requiredPermission: "bulk_import.view",
    implemented: true,
    phase: "3D",
  },
  {
    id: "access-requests",
    label: "Access Requests",
    icon: "shield",
    path: "/tenant/access-requests",
    requiredModule: "tenant_access_requests",
    requiredPermission: "access_requests.view",
    implemented: true,
    phase: "3F",
  },
  {
    id: "branding",
    label: "Branding",
    icon: "layers",
    path: "/tenant/branding",
    requiredModule: "tenant_branding",
    requiredPermission: "branding.view",
    implemented: true,
    phase: "4A",
  },
  {
    id: "org-profile",
    label: "Profile & Structure",
    icon: "building",
    path: "/tenant/profile",
    requiredModule: "tenant_profile",
    requiredPermission: "profile.view",
    implemented: true,
    phase: "4A",
  },
  {
    id: "users-memberships",
    label: "Users & Memberships",
    icon: "user",
    path: "/tenant/users",
    requiredModule: "tenant_users",
    requiredPermission: "users.view",
    implemented: true,
    phase: "4B",
  },
  {
    id: "usage-quotas",
    label: "Usage & Quotas",
    icon: "grid",
    path: "/tenant/usage",
    requiredModule: "tenant_usage",
    requiredPermission: "usage.view",
    implemented: true,
    phase: "4C",
  },
  {
    id: "subscriptions-overview",
    label: "Subscriptions",
    icon: "credit_card",
    path: "/tenant/subscriptions",
    requiredModule: "tenant_subscriptions",
    requiredPermission: "subscriptions.view",
    implemented: true,
    phase: "4D",
  },
  {
    id: "billing-invoices",
    label: "Billing & Invoices",
    icon: "credit_card",
    path: "/tenant/billing",
    requiredModule: "tenant_billing",
    requiredPermission: "billing.view",
    implemented: true,
    phase: "4E",
  },
  {
    id: "identity-providers",
    label: "Identity & SSO",
    icon: "shield",
    path: "/tenant/sso",
    requiredModule: "tenant_sso",
    requiredPermission: "sso.view",
    implemented: true,
    phase: "4F",
  },
  {
    id: "security-policies",
    label: "Security & Sessions",
    icon: "shield",
    path: "/tenant/security",
    requiredModule: "tenant_security",
    requiredPermission: "security.view",
    implemented: true,
    phase: "4G",
  },
  {
    id: "audit-log",
    label: "Audit Log & Compliance",
    icon: "history",
    path: "/tenant/activity-log",
    requiredModule: "tenant_audit_log",
    requiredPermission: "audit.view",
    implemented: true,
    phase: "4H",
  },
  {
    id: "notifications",
    label: "Notifications",
    icon: "layers",
    path: "/tenant/notifications",
    requiredModule: "tenant_notifications",
    requiredPermission: "notifications.view",
    implemented: true,
    phase: "3A",
  },
  // # Hidden from tenant admin console:
  // {
  //   id: "reports-analytics",
  //   label: "Advanced Analytics, Adoption & Tenant Health",
  //   icon: "grid",
  //   path: "/tenant/reports",
  //   requiredModule: "tenant_reports",
  //   requiredPermission: "reports.view",
  //   implemented: true,
  //   phase: "4F",
  // },
  {
    id: "tenant-settings",
    label: "Tenant Settings",
    icon: "building",
    path: "/tenant/settings",
    requiredModule: "tenant_settings",
    requiredPermission: "settings.view",
    implemented: true,
    phase: "4J",
  },
];

export function getVisibleTenantModules(
  allowedModules: readonly string[],
  effectivePermissions: readonly string[]
): readonly TenantModuleDefinition[] {
  return TENANT_MODULES_REGISTRY.filter((mod) => {
    if (!mod.implemented) return false;
    if (mod.requiredModule && !allowedModules.includes(mod.requiredModule)) {
      return false;
    }
    if (mod.requiredPermission && !effectivePermissions.includes(mod.requiredPermission)) {
      return false;
    }
    return true;
  });
}

