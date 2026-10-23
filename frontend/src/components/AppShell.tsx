/**
 * Authenticated AppShell Layout Component.
 *
 * LMS-Grade Synchronized Navigation Architecture:
 * - Shared CSS grid-template-columns transition (80px -> 312px)
 * - Main workspace smoothly resizes and shifts with the sidebar (never covered or clipped)
 * - Zero backdrop-filter or clip-path on the desktop sidebar for 60fps rendering
 * - Solid theme-aware sidebar surface with clean vertical active indicator
 * - Accessible keyboard focus-within expansion and collapsed tooltips
 * - Mobile modal drawer (<768px) with backdrop blur and Escape key listener
 */

import React, { useState, useEffect, useCallback } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { useAuth } from "../context/AuthContext.tsx";
import { BrandMark } from "./BrandMark.tsx";
import { ThemeToggle } from "./ThemeToggle.tsx";
import { ContextSwitcher } from "./ContextSwitcher.tsx";
import { ImpersonationBanner } from "./ImpersonationBanner.tsx";
import {
  GridIcon,
  BoxIcon,
  BuildingIcon,
  LogOutIcon,
  UserIcon,
  MenuIcon,
  CloseIcon,
  ShieldCheckIcon,
  HistoryIcon,
  LayersIcon,
  CreditCardIcon,
  PlusIcon,
  UploadIcon,
  StarIcon,
  CodeIcon,
} from "./Icons.tsx";
import { TENANT_MODULES_REGISTRY } from "../config/tenantModules.ts";
import { tenantHomeApi } from "../api/tenantHome.ts";
import { showcaseApi } from "../api/showcase.ts";
import type { TenantProductAccessItem, ShowcaseProfile } from "../api/types.ts";

function renderTenantIcon(icon: string) {
  switch (icon) {
    case "grid":
      return <GridIcon size={18} />;
    case "box":
      return <BoxIcon size={18} />;
    case "shield":
      return <ShieldCheckIcon size={18} />;
    case "layers":
      return <LayersIcon size={18} />;
    case "upload":
      return <UploadIcon size={18} />;
    case "building":
      return <BuildingIcon size={18} />;
    case "user":
      return <UserIcon size={18} />;
    case "credit_card":
      return <CreditCardIcon size={18} />;
    case "history":
      return <HistoryIcon size={18} />;
    default:
      return <GridIcon size={18} />;
  }
}

interface NavSubItem {
  readonly id: string;
  readonly label: string;
  readonly code?: string;
  readonly path: string;
  readonly active: boolean;
  readonly product?: TenantProductAccessItem;
}

interface NavItem {
  readonly id: string;
  readonly label: string;
  readonly icon: React.ReactNode;
  readonly path: string;
  readonly active: boolean;
  readonly subItems?: readonly NavSubItem[];
}

interface NavSection {
  readonly title: string;
  readonly items: readonly NavItem[];
}

function getInitials(name?: string, fallbackRole?: string): string {
  if (name && name.trim().length > 0) {
    const parts = name.trim().split(/\s+/);
    if (parts.length >= 2) {
      return `${parts[0][0]}${parts[1][0]}`.toUpperCase();
    }
    return parts[0].slice(0, 2).toUpperCase();
  }
  if (fallbackRole) {
    if (fallbackRole.toLowerCase().includes("owner") || fallbackRole.toLowerCase().includes("super")) return "DP";
    if (fallbackRole.toLowerCase().includes("admin")) return "TA";
    if (fallbackRole.toLowerCase().includes("member")) return "TM";
  }
  return "VC";
}

interface AppShellProps {
  readonly children: React.ReactNode;
  readonly fullWidth?: boolean;
}

export const AppShell: React.FC<AppShellProps> = ({ children, fullWidth = false }) => {
  const { user, logout } = useAuth();
  const [isLoggingOut, setIsLoggingOut] = useState(false);
  const [mobileDrawerOpen, setMobileDrawerOpen] = useState(false);
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(true);
  const location = useLocation();
  const navigate = useNavigate();

  const isOwnerContext = user?.active_context?.type === "platform_owner";
  const isMember =
    user?.active_context?.type === "tenant" &&
    user?.active_context?.membership_type === "member";
  const hasMultipleContexts = (user?.available_contexts?.length || 0) > 1;

  const [tenantProducts, setTenantProducts] = useState<readonly TenantProductAccessItem[]>([]);
  const [showcaseProfiles, setShowcaseProfiles] = useState<readonly ShowcaseProfile[]>([]);
  const [isShowcaseRevealed, setIsShowcaseRevealed] = useState<boolean>(() => {
    try {
      return sessionStorage.getItem("vc_showcase_submodules_revealed") === "true";
    } catch {
      return false;
    }
  });
  const [isTenantProductsRevealed, setIsTenantProductsRevealed] = useState<boolean>(() => {
    try {
      return sessionStorage.getItem("vc_tenant_products_revealed") === "true";
    } catch {
      return false;
    }
  });

  useEffect(() => {
    const handleShowcaseLaunched = () => {
      setIsShowcaseRevealed(true);
    };
    window.addEventListener("vibeconnect:showcase-launched", handleShowcaseLaunched);
    return () => {
      window.removeEventListener("vibeconnect:showcase-launched", handleShowcaseLaunched);
    };
  }, []);

  useEffect(() => {
    const handleTenantProductLaunched = () => {
      setIsTenantProductsRevealed(true);
    };
    window.addEventListener("vibeconnect:tenant-product-launched", handleTenantProductLaunched);
    return () => {
      window.removeEventListener("vibeconnect:tenant-product-launched", handleTenantProductLaunched);
    };
  }, []);

  useEffect(() => {
    let isCancelled = false;
    if (user?.active_context?.type === "tenant") {
      tenantHomeApi
        .getTenantHome()
        .then((data) => {
          if (!isCancelled) {
            const prods =
              data.products && data.products.length > 0
                ? data.products
                : data.entitled_products ?? [];
            setTenantProducts(prods);
          }
        })
        .catch(() => {
          // Non-blocking graceful fallback
        });
    } else if (isOwnerContext) {
      showcaseApi
        .listProfiles({ visibility: "published" })
        .then((data) => {
          if (!isCancelled && data?.results) {
            setShowcaseProfiles(data.results);
          }
        })
        .catch(() => {
          // Non-blocking graceful fallback
        });
    }
    return () => {
      isCancelled = true;
    };
  }, [user?.active_context?.type, user?.active_context?.organization?.id, isOwnerContext]);

  const handleLogout = async () => {
    setIsLoggingOut(true);
    try {
      sessionStorage.removeItem("vc_showcase_submodules_revealed");
      sessionStorage.removeItem("vc_tenant_products_revealed");
    } catch {
      // Safe fallback
    }
    setIsShowcaseRevealed(false);
    setIsTenantProductsRevealed(false);
    try {
      await logout();
    } catch {
      setIsLoggingOut(false);
    }
  };

  const closeDrawer = useCallback(() => {
    setMobileDrawerOpen(false);
  }, []);

  // Lock body scroll and listen for Escape key when mobile drawer is open
  useEffect(() => {
    if (mobileDrawerOpen) {
      document.body.style.overflow = "hidden";
      const handleKeyDown = (e: KeyboardEvent) => {
        if (e.key === "Escape") {
          closeDrawer();
        }
      };
      window.addEventListener("keydown", handleKeyDown);
      return () => {
        document.body.style.overflow = "";
        window.removeEventListener("keydown", handleKeyDown);
      };
    } else {
      document.body.style.overflow = "";
    }
  }, [mobileDrawerOpen, closeDrawer]);

  // Ensure every route navigation resets viewport scroll to top
  useEffect(() => {
    window.scrollTo(0, 0);
  }, [location.pathname]);

  const navSections: readonly NavSection[] = isOwnerContext
    ? [
        {
          title: "OVERVIEW",
          items: [
            {
              id: "overview",
              label: "Overview",
              icon: <GridIcon size={18} />,
              path: "/",
              active: location.pathname === "/",
            },
            {
              id: "reports",
              label: "Analytics & Health",
              icon: <GridIcon size={18} />,
              path: "/reports",
              active: location.pathname.startsWith("/reports"),
            },
          ],
        },
        {
          title: "CUSTOMER OPERATIONS",
          items: [
            {
              id: "organizations",
              label: "Organization Registry",
              icon: <BuildingIcon size={18} />,
              path: "/organizations",
              active: location.pathname.startsWith("/organizations"),
            },
            {
              id: "onboarding",
              label: "Tenant Onboarding",
              icon: <PlusIcon size={18} />,
              path: "/onboarding",
              active: location.pathname.startsWith("/onboarding"),
            },
            {
              id: "subscriptions",
              label: "Subscriptions",
              icon: <CreditCardIcon size={18} />,
              path: "/subscriptions",
              active: location.pathname.startsWith("/subscriptions"),
            },
            {
              id: "billing",
              label: "Billing & Invoices",
              icon: <CreditCardIcon size={18} />,
              path: "/billing",
              active: location.pathname.startsWith("/billing"),
            },
            {
              id: "users",
              label: "Central Users",
              icon: <UserIcon size={18} />,
              path: "/users",
              active: location.pathname.startsWith("/users"),
            },
            {
              id: "access-requests",
              label: "Access Requests & Approvals",
              icon: <ShieldCheckIcon size={18} />,
              path: "/access-requests",
              active: location.pathname.startsWith("/access-requests"),
            },
            {
              id: "support-console",
              label: "Support & Operations Console",
              icon: <ShieldCheckIcon size={18} />,
              path: "/support",
              active: location.pathname === "/support",
            },
            {
              id: "support-impersonation",
              label: "Audited Support Impersonation",
              icon: <ShieldCheckIcon size={18} />,
              path: "/support/impersonation",
              active: location.pathname.startsWith("/support/impersonation"),
            },
          ],
        },
        {
          title: "PLATFORM",
          items: [
            {
              id: "products",
              label: "Product Registry & Marketplace",
              icon: <BoxIcon size={18} />,
              path: "/products",
              active: location.pathname.startsWith("/products"),
            },
            {
              id: "plans",
              label: "Plans & Pricing",
              icon: <LayersIcon size={18} />,
              path: "/plans",
              active:
                location.pathname.startsWith("/plans") ||
                location.pathname.startsWith("/plan-versions"),
            },
            {
              id: "entitlements",
              label: "Product Access",
              icon: <ShieldCheckIcon size={18} />,
              path: "/organization-product-entitlements",
              active: location.pathname.startsWith("/organization-product-entitlements"),
            },
            {
              id: "showcase",
              label: "Product Showcase",
              icon: <StarIcon size={18} />,
              path: "/showcase",
              active: location.pathname.startsWith("/showcase"),
              subItems: isShowcaseRevealed
                ? showcaseProfiles.map((p) => ({
                    id: `showcase-sub-${p.product_code}`,
                    label: p.product_name,
                    code: p.product_code,
                    path: `/showcase?product=${encodeURIComponent(p.product_code)}&demo=true`,
                    active:
                      location.pathname.startsWith("/showcase") &&
                      location.search.toLowerCase().includes(`product=${encodeURIComponent(p.product_code).toLowerCase()}`),
                  }))
                : undefined,
            },
            {
              id: "usage",
              label: "Usage & Metering",
              icon: <GridIcon size={18} />,
              path: "/usage",
              active: location.pathname.startsWith("/usage"),
            },
            {
              id: "reconciliation",
              label: "Reconciliation",
              icon: <ShieldCheckIcon size={18} />,
              path: "/reconciliation",
              active: location.pathname.startsWith("/reconciliation"),
            },
            {
              id: "white-labeling",
              label: "White Labeling",
              icon: <LayersIcon size={18} />,
              path: "/white-labeling",
              active: location.pathname.startsWith("/white-labeling"),
            },
            {
              id: "notifications",
              label: "Notifications",
              icon: <LayersIcon size={18} />,
              path: "/notifications",
              active: location.pathname.startsWith("/notifications"),
            },
          ],
        },
        {
          title: "INFRASTRUCTURE",
          items: [
            {
              id: "developer-oversight",
              label: "Developer & API Console",
              icon: <CodeIcon size={18} />,
              path: "/owner/developer-oversight",
              active: location.pathname.startsWith("/owner/developer-oversight"),
            },
            {
              id: "integration-hub",
              label: "Integration Hub",
              icon: <LayersIcon size={18} />,
              path: "/integration",
              active: location.pathname === "/integration",
            },
            {
              id: "external-mappings",
              label: "External Mappings",
              icon: <LayersIcon size={18} />,
              path: "/integration/mappings",
              active: location.pathname.startsWith("/integration/mappings"),
            },
            {
              id: "lms-reconciliation",
              label: "LMS Reconciliation",
              icon: <ShieldCheckIcon size={18} />,
              path: "/integration/reconciliation",
              active: location.pathname.startsWith("/integration/reconciliation"),
            },
            {
              id: "bulk-import",
              label: "Data Import & Migration",
              icon: <UploadIcon size={18} />,
              path: "/bulk-import",
              active: location.pathname.startsWith("/bulk-import"),
            },
            {
              id: "activity-log",
              label: "Security, Privacy, Retention & Compliance",
              icon: <HistoryIcon size={18} />,
              path: "/activity-log",
              active: location.pathname.startsWith("/activity-log"),
            },
          ],
        },
      ]
    : user?.active_context?.type === "support"
    ? [
        {
          title: "CUSTOMER OPERATIONS",
          items: [
            {
              id: "support-console",
              label: "Support & Operations Console",
              icon: <ShieldCheckIcon size={18} />,
              path: "/support",
              active: location.pathname === "/support",
            },
            {
              id: "support-impersonation",
              label: "Audited Support Impersonation",
              icon: <ShieldCheckIcon size={18} />,
              path: "/support/impersonation",
              active: location.pathname.startsWith("/support/impersonation"),
            },
          ],
        },
      ]
    : isMember
    ? [
        {
          title: "OVERVIEW",
          items: [
            {
              id: "member-dashboard",
              label: "Dashboard",
              icon: <GridIcon size={18} />,
              path: "/tenant/dashboard",
              active: location.pathname === "/tenant/dashboard",
            },
          ],
        },
        {
          title: "PLATFORM",
          items: [
            {
              id: "my-products",
              label: "My Products & App Launcher",
              icon: <BoxIcon size={18} />,
              path: "/tenant/products",
              active:
                location.pathname.startsWith("/tenant/products") ||
                location.pathname.startsWith("/tenant/workspace"),
              subItems: isTenantProductsRevealed
                ? tenantProducts.map((p) => ({
                    id: `member-sub-prod-${p.id}`,
                    label: p.name,
                    code: p.code,
                    path: `/tenant/workspace/${p.id}`,
                    active: location.pathname === `/tenant/workspace/${p.id}`,
                    product: p,
                  }))
                : undefined,
            },
          ],
        },
      ]
    : [
        {
          title: "OVERVIEW",
          items: [
            ...TENANT_MODULES_REGISTRY.filter((mod) => {
              if (!mod.implemented) return false;
              if (mod.id !== "dashboard" && mod.id !== "reports-analytics") return false;
              if (mod.requiredModule && !user?.active_context?.allowed_modules?.includes(mod.requiredModule)) return false;
              if (mod.requiredPermission && !user?.active_context?.effective_permissions?.includes(mod.requiredPermission)) return false;
              return true;
            }).map((mod) => ({
              id: mod.id,
              label: mod.label,
              icon: renderTenantIcon(mod.icon),
              path: mod.path,
              active: mod.path === "/tenant" ? location.pathname === "/tenant" : location.pathname.startsWith(mod.path),
            })),
          ],
        },
        {
          title: "CUSTOMER OPERATIONS",
          items: (() => {
            const registryItems: NavItem[] = TENANT_MODULES_REGISTRY.filter((mod) => {
              if (!mod.implemented) return false;
              if (!["roles-permissions", "product-assignments", "bulk-user-onboarding", "access-requests", "users-memberships", "org-profile", "branding"].includes(mod.id)) return false;
              if (mod.requiredModule && !user?.active_context?.allowed_modules?.includes(mod.requiredModule)) return false;
              if (mod.requiredPermission && !user?.active_context?.effective_permissions?.includes(mod.requiredPermission)) return false;
              return true;
            }).map((mod) => ({
              id: mod.id,
              label: mod.label,
              icon: renderTenantIcon(mod.icon),
              path: mod.path,
              active: location.pathname.startsWith(mod.path),
            }));

            const canOnboardMembers =
              Boolean(user?.active_context?.allowed_modules?.includes("tenant_roles")) &&
              Boolean(user?.active_context?.effective_permissions?.includes("roles.assign"));

            if (canOnboardMembers) {
              const memberOnboardingItem: NavItem = {
                id: "member-onboarding",
                label: "Member Onboarding",
                icon: <UserIcon size={18} />,
                path: "/tenant/member-onboarding",
                active: location.pathname.startsWith("/tenant/member-onboarding"),
              };

              const bulkIdx = registryItems.findIndex((i) => i.id === "bulk-user-onboarding");
              if (bulkIdx !== -1) {
                registryItems.splice(bulkIdx, 0, memberOnboardingItem);
              } else {
                registryItems.push(memberOnboardingItem);
              }
            }

            return registryItems;
          })(),
        },
        {
          title: "PLATFORM",
          items: [
            ...TENANT_MODULES_REGISTRY.filter((mod) => {
              if (!mod.implemented) return false;
              if (!["my-products", "subscriptions-overview", "billing-invoices", "usage-quotas", "notifications"].includes(mod.id)) return false;
              if (mod.requiredModule && !user?.active_context?.allowed_modules?.includes(mod.requiredModule)) return false;
              if (mod.requiredPermission && !user?.active_context?.effective_permissions?.includes(mod.requiredPermission)) return false;
              return true;
            }).map((mod) => ({
              id: mod.id,
              label: mod.label,
              icon: renderTenantIcon(mod.icon),
              path: mod.path,
              active:
                mod.path === "/tenant/products"
                  ? location.pathname.startsWith("/tenant/products") || location.pathname.startsWith("/tenant/workspace")
                  : location.pathname.startsWith(mod.path),
              subItems:
                mod.path === "/tenant/products" && isTenantProductsRevealed
                  ? tenantProducts.map((p) => ({
                      id: `tenant-admin-sub-prod-${p.id}`,
                      label: p.name,
                      code: p.code,
                      path: `/tenant/workspace/${p.id}`,
                      active: location.pathname === `/tenant/workspace/${p.id}`,
                      product: p,
                    }))
                  : undefined,
            })),
            {
              id: "marketplace",
              label: "Marketplace",
              icon: <BoxIcon size={18} />,
              path: "/tenant/marketplace",
              active: location.pathname.startsWith("/tenant/marketplace"),
            },
          ],
        },
        {
          title: "INFRASTRUCTURE",
          items: [
            {
              id: "developer-console",
              label: "Developer & API Console",
              icon: <CodeIcon size={18} />,
              path: "/tenant/developer",
              active: location.pathname.startsWith("/tenant/developer"),
            },
            ...TENANT_MODULES_REGISTRY.filter((mod) => {
              if (!mod.implemented) return false;
              if (!["identity-providers", "security-policies", "audit-log", "tenant-settings"].includes(mod.id)) return false;
              if (mod.requiredModule && !user?.active_context?.allowed_modules?.includes(mod.requiredModule)) return false;
              if (mod.requiredPermission && !user?.active_context?.effective_permissions?.includes(mod.requiredPermission)) return false;
              return true;
            }).map((mod) => ({
              id: mod.id,
              label: mod.label,
              icon: renderTenantIcon(mod.icon),
              path: mod.path,
              active: location.pathname.startsWith(mod.path),
            })),
          ],
        },
      ].filter((section) => section.items.length > 0);

  const navItems: readonly NavItem[] = navSections.flatMap((s) => s.items);

  return (
    <div
      style={{
        minHeight: "100vh",
        display: "flex",
        flexDirection: "column",
        background: "var(--bg-app)",
        position: "relative",
        overflowX: "clip",
        width: "100%",
        maxWidth: "100vw",
      }}
    >
      {/* Top Sticky Header */}
      <header
        className="app-header"
        style={{
          position: "sticky",
          top: 0,
          zIndex: 30,
          height: "56px",
          background: "var(--glass-surface-elevated)",
          borderBottom: "1px solid var(--border-glass)",
          boxShadow: "var(--shadow-sm)",
          padding: "0 1.5rem",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: "1rem",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: "0.875rem" }}>
          {/* Mobile Drawer Trigger (Hidden on desktop) */}
          <button
            type="button"
            onClick={() => setMobileDrawerOpen(true)}
            className="btn-ghost mobile-nav-trigger"
            aria-expanded={mobileDrawerOpen}
            aria-label="Open navigation menu"
            style={{ display: "none", minWidth: "36px", minHeight: "36px" }}
          >
            <MenuIcon size={18} />
          </button>

          <BrandMark
            size="sm"
            showLabel={true}
            subtitle={
              user?.active_context?.type === "tenant"
                ? user.active_context.organization?.code || "Tenant"
                : "Control Plane"
            }
          />
        </div>

        {/* Header Right Actions */}
        <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
          {/* Desktop Context Switcher (Only shown if multiple contexts are available) */}
          {hasMultipleContexts && (
            <div className="desktop-context-switcher">
              <ContextSwitcher />
            </div>
          )}

          <ThemeToggle />

          {/* User Profile Indicator */}
          <div
            className="user-profile-indicator"
            style={{
              display: "flex",
              alignItems: "center",
              gap: "0.5rem",
              padding: "0.25rem 0.625rem",
              background: "var(--glass-surface)",
              border: "1px solid var(--border-glass)",
              borderRadius: "9999px",
              boxShadow: "var(--shadow-sm)",
            }}
          >
            <div
              style={{
                width: "26px",
                height: "26px",
                borderRadius: "50%",
                background: "var(--brand-primary-light)",
                color: "var(--brand-primary)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                flexShrink: 0,
              }}
            >
              <UserIcon size={14} />
            </div>
            <div
              className="user-profile-text"
              style={{ display: "flex", flexDirection: "column", textAlign: "left", maxWidth: "150px" }}
            >
              <span
                style={{
                  fontSize: "0.75rem",
                  fontWeight: 600,
                  color: "var(--text-primary)",
                  whiteSpace: "nowrap",
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                  lineHeight: 1.2,
                }}
              >
                {user?.full_name ||
                  (user?.active_context?.type === "tenant"
                    ? (isMember ? "Tenant Member" : "Tenant Admin")
                    : "Platform Owner")}
              </span>
              <span
                style={{
                  fontSize: "0.6875rem",
                  color: "var(--text-muted)",
                  whiteSpace: "nowrap",
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                  lineHeight: 1.2,
                }}
              >
                {user?.email}
              </span>
            </div>
          </div>

          {/* Sign Out Button */}
          <button
            type="button"
            onClick={handleLogout}
            disabled={isLoggingOut}
            className="btn-secondary header-sign-out-btn"
            style={{ padding: "0.4rem 0.75rem", minHeight: "36px" }}
            aria-label="Sign out of control plane"
          >
            <LogOutIcon size={14} />
            <span className="sign-out-label">{isLoggingOut ? "..." : "Sign Out"}</span>
          </button>
        </div>
      </header>

      {/* Mobile Dedicated Context Switcher Row (<768px) */}
      {hasMultipleContexts && (
        <div className="mobile-context-bar" role="region" aria-label="Organization context">
          <ContextSwitcher isMobile={true} />
        </div>
      )}

      {/* Main Synchronized Body (CSS Grid Controls Sidebar & Workspace Column) */}
      <div className={`app-shell-body ${isSidebarCollapsed ? "sidebar-is-collapsed" : "sidebar-is-expanded"}`}>
        {/* Desktop LMS-Style Sidebar */}
        <aside
          className={`desktop-sidebar ${isSidebarCollapsed ? "sidebar--collapsed" : "sidebar--expanded"}`}
          aria-label="Sidebar navigation"
        >
          <div className="sidebar-content-inner">
            {/* Top Bar with Hamburger Menu Toggle */}
            <div className="sidebar-top-bar">
              <button
                type="button"
                onClick={() => setIsSidebarCollapsed((prev) => !prev)}
                className="sidebar-hamburger-btn"
                aria-label={isSidebarCollapsed ? "Expand sidebar navigation" : "Collapse sidebar navigation"}
                aria-expanded={!isSidebarCollapsed}
                title={isSidebarCollapsed ? "Expand sidebar (☰)" : "Collapse sidebar (☰)"}
              >
                <MenuIcon size={18} />
              </button>
              {!isSidebarCollapsed && (
                <span className="sidebar-top-label">Navigation</span>
              )}
            </div>

            {/* Navigation Sections */}
            <nav className="sidebar-nav-container">
              {navSections.map((section) => (
                <div key={section.title} className="sidebar-section-group">
                  <div className="sidebar-section-header">
                    {section.title}
                  </div>
                  {section.items.map((item) => (
                    <div key={item.id} className="nav-item-wrapper">
                      <button
                        type="button"
                        onClick={() => navigate(item.path)}
                        className={`sidebar-nav-btn ${item.active ? "active" : ""}`}
                        aria-label={item.label}
                        aria-current={item.active ? "page" : undefined}
                      >
                        {/* Active Edge Indicator */}
                        {item.active && <span className="active-edge-indicator" aria-hidden="true" />}

                        <span className="sidebar-icon-box">
                          {item.icon}
                        </span>

                        <span className="sidebar-nav-label">
                          {item.label}
                        </span>
                      </button>

                      {/* Floating tooltip displayed only in collapsed mode */}
                      <span className="sidebar-tooltip" role="tooltip">
                        {item.label}
                      </span>

                      {/* Render dynamic submodules if present and expanded */}
                      {item.subItems && item.subItems.length > 0 && !isSidebarCollapsed && (
                        <div className="sidebar-submodules-container">
                          {item.subItems.map((sub) => (
                            <button
                              key={sub.id}
                              type="button"
                              onClick={(e) => {
                                e.stopPropagation();
                                navigate(sub.path, { state: { product: sub.product } });
                              }}
                              className={`sidebar-sub-btn ${sub.active ? "active" : ""}`}
                              title={sub.label}
                              aria-label={sub.label}
                            >
                              <span className="sidebar-sub-btn-dot" aria-hidden="true" />
                              <span className="sidebar-sub-btn-text">{sub.label}</span>
                            </button>
                          ))}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              ))}
            </nav>

            {/* Bottom User Card */}
            <div
              className="sidebar-user-card"
              title={
                isSidebarCollapsed
                  ? `${user?.full_name || (isOwnerContext ? "Demo Platform Owner" : isMember ? "Tenant Member" : "Tenant Admin")} (${isOwnerContext ? "SUPER ADMIN" : user?.active_context?.type === "support" ? "SUPPORT ADMIN" : isMember ? "TENANT MEMBER" : "TENANT ADMIN"})`
                  : undefined
              }
            >
              <div className="sidebar-user-avatar" aria-hidden="true">
                {getInitials(
                  user?.full_name,
                  isOwnerContext
                    ? "Platform Owner"
                    : isMember
                    ? "Tenant Member"
                    : "Tenant Admin"
                )}
              </div>
              {!isSidebarCollapsed && (
                <div className="sidebar-user-details">
                  <span
                    className="sidebar-user-name"
                    title={
                      user?.full_name ||
                      (isOwnerContext ? "Demo Platform Owner" : isMember ? "Tenant Member" : "Tenant Admin")
                    }
                  >
                    {user?.full_name ||
                      (isOwnerContext ? "Demo Platform Owner" : isMember ? "Tenant Member" : "Tenant Admin")}
                  </span>
                  <span className="sidebar-user-role">
                    {isOwnerContext
                      ? "SUPER ADMIN"
                      : user?.active_context?.type === "support"
                      ? "SUPPORT ADMIN"
                      : isMember
                      ? "TENANT MEMBER"
                      : "TENANT ADMIN"}
                  </span>
                </div>
              )}
            </div>
          </div>
        </aside>

        {/* Main Content Workspace (Resizes smoothly alongside sidebar) */}
        <main className={`app-main-workspace${fullWidth ? " app-main-workspace--full" : ""}`}>
          <div className={`workspace-inner-container${fullWidth ? " workspace-inner-container--full" : ""}`}>
            <ImpersonationBanner />
            {children}
          </div>
        </main>
      </div>

      {/* Mobile Modal Drawer (<768px) */}
      {mobileDrawerOpen && (
        <div
          role="dialog"
          aria-modal="true"
          aria-label="Navigation menu"
          style={{
            position: "fixed",
            inset: 0,
            zIndex: 50,
            display: "flex",
          }}
        >
          {/* Backdrop Overlay */}
          <div
            onClick={closeDrawer}
            style={{
              position: "absolute",
              inset: 0,
              background: "rgba(0, 0, 0, 0.6)",
              backdropFilter: "blur(4px)",
              WebkitBackdropFilter: "blur(4px)",
            }}
          />

          {/* Drawer Panel */}
          <div
            style={{
              position: "relative",
              width: "280px",
              maxWidth: "85vw",
              height: "100%",
              background: "var(--glass-surface-elevated)",
              borderRight: "1px solid var(--border-glass)",
              boxShadow: "var(--shadow-lg)",
              padding: "1.25rem",
              display: "flex",
              flexDirection: "column",
              gap: "1rem",
              zIndex: 1,
            }}
          >
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
              <BrandMark size="sm" showLabel={true} subtitle="Control Plane" />
              <button
                type="button"
                onClick={closeDrawer}
                className="btn-ghost"
                aria-label="Close navigation menu"
                style={{ minWidth: "32px", minHeight: "32px" }}
              >
                <CloseIcon size={18} />
              </button>
            </div>

            <div style={{ borderTop: "1px solid var(--border-subtle)", paddingTop: "0.75rem" }}>
              <div
                style={{
                  fontSize: "0.6875rem",
                  fontWeight: 700,
                  textTransform: "uppercase",
                  color: "var(--text-muted)",
                  padding: "0.25rem 0.5rem",
                  marginBottom: "0.5rem",
                  letterSpacing: "0.06em",
                }}
              >
                Navigation
              </div>
              {navItems.map((item) => (
                <div key={item.id} style={{ display: "flex", flexDirection: "column", gap: "2px" }}>
                  <button
                    type="button"
                    onClick={() => {
                      navigate(item.path);
                      closeDrawer();
                    }}
                    className="btn-ghost"
                    style={{
                      width: "100%",
                      justifyContent: "flex-start",
                      gap: "0.75rem",
                      padding: "0.625rem 0.75rem",
                      borderRadius: "8px",
                      background: item.active ? "var(--brand-primary-light)" : "transparent",
                      color: item.active ? "var(--brand-primary)" : "var(--text-secondary)",
                      fontWeight: item.active ? 600 : 500,
                    }}
                  >
                    {item.icon}
                    <span style={{ fontSize: "0.875rem" }}>{item.label}</span>
                  </button>

                  {item.subItems && item.subItems.length > 0 && (
                    <div
                      style={{
                        display: "flex",
                        flexDirection: "column",
                        gap: "2px",
                        marginLeft: "1.75rem",
                        paddingLeft: "0.75rem",
                        borderLeft: "1.5px solid var(--border-subtle)",
                      }}
                    >
                      {item.subItems.map((sub) => (
                        <button
                          key={sub.id}
                          type="button"
                          onClick={() => {
                            navigate(sub.path, { state: { product: sub.product } });
                            closeDrawer();
                          }}
                          style={{
                            display: "flex",
                            alignItems: "center",
                            gap: "0.5rem",
                            width: "100%",
                            padding: "0.375rem 0.6rem",
                            borderRadius: "6px",
                            background: sub.active ? "var(--brand-primary-light)" : "transparent",
                            color: sub.active ? "var(--brand-primary)" : "var(--text-secondary)",
                            fontWeight: sub.active ? 600 : 500,
                            fontSize: "0.8125rem",
                            border: "none",
                            cursor: "pointer",
                            textAlign: "left",
                          }}
                        >
                          <span
                            style={{
                              width: "5px",
                              height: "5px",
                              borderRadius: "50%",
                              background: sub.active ? "var(--brand-primary)" : "var(--text-muted)",
                              flexShrink: 0,
                            }}
                          />
                          <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                            {sub.label}
                          </span>
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>

            <div style={{ marginTop: "auto", borderTop: "1px solid var(--border-subtle)", paddingTop: "1rem" }}>
              <div style={{ fontSize: "0.75rem", color: "var(--text-secondary)", marginBottom: "0.75rem" }}>
                Signed in as <strong>{user?.email}</strong>
              </div>
              <button
                type="button"
                onClick={handleLogout}
                className="btn-secondary"
                style={{ width: "100%", justifyContent: "center" }}
              >
                <LogOutIcon size={14} />
                <span>Sign Out</span>
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Synchronized CSS Grid Styles */}
      <style>{`
        /* AppShell Body: CSS Grid Controls Sidebar & Workspace Synchronously */
        .app-shell-body {
          --sidebar-width: 56px;
          display: grid;
          grid-template-columns: var(--sidebar-width) minmax(0, 1fr);
          align-items: start;
          min-height: calc(100dvh - 56px);
          width: 100%;
          position: relative;
          transition: grid-template-columns 240ms cubic-bezier(0.16, 1, 0.3, 1);
          will-change: grid-template-columns;
        }

        .app-shell-body.sidebar-is-collapsed {
          --sidebar-width: 56px;
        }

        .app-shell-body.sidebar-is-expanded {
          --sidebar-width: 250px;
        }

        /* Persistent Sidebar Track Surface */
        .app-shell-body::before {
          content: "";
          position: absolute;
          top: 0;
          bottom: 0;
          left: 0;
          width: var(--sidebar-width);
          background: var(--glass-surface-elevated, #ffffff);
          border-right: 1px solid var(--border-subtle);
          pointer-events: none;
          z-index: 10;
          transition: width 240ms cubic-bezier(0.16, 1, 0.3, 1);
          will-change: width;
        }

        /* Desktop Sidebar Surface */
        .desktop-sidebar {
          width: var(--sidebar-width);
          min-width: 0;
          overflow: hidden;
          background: var(--glass-surface-elevated, #ffffff);
          border-right: 1px solid var(--border-subtle);
          display: flex;
          flex-direction: column;
          height: calc(100dvh - 56px);
          position: sticky;
          top: 56px;
          align-self: start;
          user-select: none;
          z-index: 20;
          contain: layout style;
          transition: width 240ms cubic-bezier(0.16, 1, 0.3, 1);
          will-change: width;
        }

        .sidebar-content-inner {
          width: 100%;
          height: 100%;
          display: flex;
          flex-direction: column;
          padding: 0.5rem 0;
          box-sizing: border-box;
          overflow: hidden;
        }

        /* Top Bar with Hamburger Menu Button */
        .sidebar-top-bar {
          display: flex;
          align-items: center;
          padding: 0.25rem 0.5rem 0.5rem;
          min-height: 40px;
          box-sizing: border-box;
          flex-shrink: 0;
        }

        .sidebar-is-collapsed .sidebar-top-bar {
          justify-content: center;
          padding: 0.25rem 0 0.5rem;
        }

        .sidebar-is-expanded .sidebar-top-bar {
          justify-content: space-between;
          padding: 0.25rem 0.75rem 0.5rem;
          border-bottom: 1px solid var(--border-subtle);
          margin-bottom: 0.25rem;
        }

        .sidebar-hamburger-btn {
          width: 38px;
          height: 38px;
          border-radius: 8px;
          border: 1px solid var(--border-subtle);
          background: var(--glass-surface, #f8fafc);
          color: var(--text-primary);
          cursor: pointer;
          display: flex;
          align-items: center;
          justify-content: center;
          transition: background-color 0.15s ease, border-color 0.15s ease, color 0.15s ease;
          outline: none;
          padding: 0;
          flex-shrink: 0;
        }

        .sidebar-hamburger-btn:hover {
          background: var(--glass-surface-hover, #f1f5f9);
          border-color: var(--brand-primary);
          color: var(--brand-primary);
        }

        .sidebar-hamburger-btn:focus-visible {
          outline: 2px solid var(--brand-primary);
          outline-offset: 1px;
        }

        .sidebar-top-label {
          font-size: 0.75rem;
          font-weight: 700;
          text-transform: uppercase;
          letter-spacing: 0.08em;
          color: var(--text-muted, #64748b);
        }

        /* Sleek Modern Unobtrusive Sidebar Navigation Scrollbar */
        .sidebar-nav-container {
          flex: 1;
          overflow-y: auto;
          overflow-x: hidden;
          display: flex;
          flex-direction: column;
          gap: 0.125rem;
          padding: 0 0.5rem;
          scrollbar-width: thin;
          scrollbar-color: #94a3b8 transparent;
        }

        .sidebar-nav-container::-webkit-scrollbar {
          width: 5px;
        }

        .sidebar-nav-container::-webkit-scrollbar-track {
          background: transparent;
        }

        .sidebar-nav-container::-webkit-scrollbar-thumb {
          background-color: #94a3b8;
          border-radius: 9999px;
        }

        .sidebar-nav-container::-webkit-scrollbar-thumb:hover {
          background-color: #64748b;
        }

        .sidebar-nav-container::-webkit-scrollbar-button {
          display: none !important;
          width: 0 !important;
          height: 0 !important;
        }

        /* Section Header */
        .sidebar-section-header {
          font-size: 0.6875rem;
          font-weight: 700;
          text-transform: uppercase;
          letter-spacing: 0.08em;
          color: var(--text-muted, #64748b);
          padding: 1.1rem 0.75rem 0.4rem;
          white-space: nowrap;
          transition: opacity 0.15s ease;
        }

        .sidebar-section-group:first-child .sidebar-section-header {
          padding-top: 0.35rem;
        }

        .sidebar-is-collapsed .sidebar-section-header {
          display: none;
        }

        /* Nav Item Wrapper & Button */
        .nav-item-wrapper {
          position: relative;
          width: 100%;
          box-sizing: border-box;
          margin-bottom: 1px;
        }

        .sidebar-nav-btn {
          position: relative;
          width: 100%;
          min-height: 38px;
          display: flex;
          align-items: center;
          background: transparent;
          border: none;
          border-radius: 8px;
          color: var(--text-primary);
          cursor: pointer;
          outline: none;
          font-family: inherit;
          transition: background-color 0.15s ease, color 0.15s ease;
          box-sizing: border-box;
        }

        .sidebar-is-expanded .sidebar-nav-btn {
          padding: 0.4rem 0.75rem;
          gap: 0.75rem;
          justify-content: flex-start;
        }

        .sidebar-is-collapsed .sidebar-nav-btn {
          padding: 0;
          width: 44px;
          height: 38px;
          margin: 0 auto;
          justify-content: center;
        }

        .sidebar-nav-btn:hover {
          background: rgba(0, 0, 0, 0.04);
        }

        .sidebar-nav-btn.active {
          background: #eef2ff;
          color: var(--brand-primary);
          font-weight: 600;
        }

        /* Active Far-Left Vertical Edge Indicator */
        .active-edge-indicator {
          position: absolute;
          left: 0;
          top: 6px;
          bottom: 6px;
          width: 3.5px;
          background: var(--brand-primary);
          border-radius: 0 4px 4px 0;
        }

        .sidebar-icon-box {
          flex: 0 0 auto;
          width: 20px;
          height: 20px;
          display: flex;
          align-items: center;
          justify-content: center;
          color: inherit;
        }

        .sidebar-nav-btn.active .sidebar-icon-box {
          color: var(--brand-primary);
        }

        .sidebar-nav-label {
          font-size: 0.8125rem;
          font-weight: 500;
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
          color: inherit;
          flex: 1;
          text-align: left;
        }

        .sidebar-is-collapsed .sidebar-nav-label {
          display: none;
        }

        .sidebar-nav-btn.active .sidebar-nav-label {
          font-weight: 600;
          color: var(--brand-primary);
        }

        /* Floating Tooltip in Collapsed Mode */
        .sidebar-tooltip {
          position: absolute;
          left: 54px;
          top: 50%;
          transform: translateY(-50%);
          background: var(--glass-surface-elevated, #ffffff);
          color: var(--text-primary);
          border: 1px solid var(--border-subtle);
          box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
          padding: 0.35rem 0.65rem;
          border-radius: 6px;
          font-size: 0.75rem;
          font-weight: 600;
          white-space: nowrap;
          pointer-events: none;
          opacity: 0;
          visibility: hidden;
          transition: opacity 0.12s ease, visibility 0.12s ease;
          z-index: 50;
        }

        .sidebar-is-collapsed .nav-item-wrapper:hover .sidebar-tooltip,
        .sidebar-is-collapsed .sidebar-nav-btn:focus-visible + .sidebar-tooltip {
          opacity: 1;
          visibility: visible;
        }

        .sidebar-is-expanded .sidebar-tooltip {
          display: none !important;
        }

        /* Submodule Styles */
        .sidebar-submodules-container {
          display: flex;
          flex-direction: column;
          gap: 2px;
          margin-top: 3px;
          margin-bottom: 5px;
          margin-left: 18px;
          padding-left: 10px;
          border-left: 1.5px solid var(--border-subtle);
        }

        .sidebar-sub-btn {
          display: flex;
          align-items: center;
          gap: 0.45rem;
          width: 100%;
          min-height: 28px;
          padding: 0.2rem 0.5rem;
          border-radius: 6px;
          background: transparent;
          border: none;
          color: var(--text-secondary);
          font-family: inherit;
          font-size: 0.8125rem;
          font-weight: 500;
          text-align: left;
          cursor: pointer;
          transition: background-color 140ms ease, color 140ms ease;
          box-sizing: border-box;
          outline: none;
        }

        .sidebar-sub-btn:hover {
          background: rgba(0, 0, 0, 0.03);
          color: var(--text-primary);
        }

        .sidebar-sub-btn.active {
          background: #eef2ff;
          color: var(--brand-primary);
          font-weight: 600;
        }

        .sidebar-sub-btn-dot {
          width: 5px;
          height: 5px;
          border-radius: 50%;
          background: #94a3b8;
          flex-shrink: 0;
          transition: background-color 140ms ease, transform 140ms ease;
        }

        .sidebar-sub-btn.active .sidebar-sub-btn-dot {
          background: var(--brand-primary);
          transform: scale(1.25);
        }

        .sidebar-sub-btn-text {
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
          min-width: 0;
        }

        /* Bottom User Card */
        .sidebar-user-card {
          border: 1px solid var(--border-subtle);
          border-radius: 12px;
          background: var(--glass-surface-elevated, #ffffff);
          box-shadow: 0 1px 3px rgba(0, 0, 0, 0.03);
          flex-shrink: 0;
          box-sizing: border-box;
          transition: width 240ms ease, margin 240ms ease, padding 240ms ease;
        }

        .sidebar-is-expanded .sidebar-user-card {
          margin: 0.5rem 0.65rem 0.25rem;
          padding: 0.65rem 0.75rem;
          display: flex;
          align-items: center;
          gap: 0.75rem;
        }

        .sidebar-is-collapsed .sidebar-user-card {
          margin: 0.5rem auto 0.25rem;
          padding: 0.25rem;
          width: 44px;
          height: 44px;
          display: flex;
          align-items: center;
          justify-content: center;
        }

        .sidebar-user-avatar {
          width: 36px;
          height: 36px;
          border-radius: 50%;
          background: #e0e7ff;
          color: #4338ca;
          display: flex;
          align-items: center;
          justify-content: center;
          font-weight: 700;
          font-size: 0.8125rem;
          flex-shrink: 0;
        }

        .sidebar-user-details {
          display: flex;
          flex-direction: column;
          min-width: 0;
          overflow: hidden;
          text-align: left;
        }

        .sidebar-user-name {
          font-size: 0.8125rem;
          font-weight: 700;
          color: var(--text-primary);
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
          line-height: 1.25;
        }

        .sidebar-user-role {
          font-size: 0.6875rem;
          font-weight: 700;
          color: #2563eb;
          letter-spacing: 0.04em;
          text-transform: uppercase;
          line-height: 1.2;
          margin-top: 1px;
        }

        /* Main Workspace Container */
        .app-main-workspace {
          min-width: 0;
          padding: 2rem 2.25rem;
          box-sizing: border-box;
        }

        .app-main-workspace--full {
          padding: 0.75rem 1rem !important;
        }

        .workspace-inner-container {
          max-width: 1360px;
          width: 100%;
          margin: 0 auto;
          min-width: 0;
        }

        .workspace-inner-container--full {
          max-width: 100% !important;
          width: 100% !important;
          margin: 0 !important;
        }

        .mobile-context-bar {
          display: none;
        }

        /* Responsive Breakpoints (<768px) */
        @media (max-width: 768px) {
          .app-shell-body {
            grid-template-columns: 1fr !important;
          }
          .app-shell-body::before {
            display: none !important;
          }
          .desktop-sidebar {
            display: none !important;
          }
          .mobile-nav-trigger {
            display: inline-flex !important;
            min-width: 44px !important;
            min-height: 44px !important;
          }
          .desktop-context-switcher {
            display: none !important;
          }
          .mobile-context-bar {
            display: block !important;
            width: 100% !important;
            padding: 0.375rem 0.75rem !important;
            background: var(--glass-surface-elevated) !important;
            border-bottom: 1px solid var(--border-glass) !important;
            box-sizing: border-box !important;
            position: sticky !important;
            top: 56px !important;
            z-index: 25 !important;
          }
          .user-profile-indicator {
            display: none !important;
          }
          .header-sign-out-btn {
            min-width: 44px !important;
            min-height: 44px !important;
            padding: 0.45rem !important;
          }
          .sign-out-label {
            display: none !important;
          }
          .app-main-workspace {
            padding: 1.25rem 1rem !important;
          }
        }

        @media (max-width: 480px) {
          .app-header {
            padding: 0 0.5rem !important;
            gap: 0.5rem !important;
          }
          .brandmark-text-container span:last-child {
            display: none !important;
          }
          .app-main-workspace {
            padding: 0.75rem 0.75rem !important;
          }
        }

        /* Reduced Motion Override */
        @media (prefers-reduced-motion: reduce) {
          .app-shell-body,
          .app-shell-body::before,
          .desktop-sidebar,
          .sidebar-section-header,
          .sidebar-nav-label,
          .status-label-text,
          .sidebar-submodules-container,
          .sidebar-sub-btn,
          .sidebar-sub-btn-dot {
            transition: none !important;
          }
        }
      `}</style>
    </div>
  );
};
