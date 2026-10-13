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

interface AppShellProps {
  readonly children: React.ReactNode;
  readonly fullWidth?: boolean;
}

export const AppShell: React.FC<AppShellProps> = ({ children, fullWidth = false }) => {
  const { user, logout } = useAuth();
  const [isLoggingOut, setIsLoggingOut] = useState(false);
  const [mobileDrawerOpen, setMobileDrawerOpen] = useState(false);
  const location = useLocation();
  const navigate = useNavigate();

  const isOwnerContext = user?.active_context?.type === "platform_owner";
  const isMember =
    user?.active_context?.type === "tenant" &&
    user?.active_context?.membership_type === "member";
  const hasMultipleContexts = (user?.available_contexts?.length || 0) > 1;

  const handleLogout = async () => {
    setIsLoggingOut(true);
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

  const navItems = isOwnerContext
    ? [
        {
          id: "overview",
          label: "Overview",
          icon: <GridIcon size={18} />,
          path: "/",
          active: location.pathname === "/",
        },
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
          id: "subscriptions",
          label: "Subscriptions",
          icon: <CreditCardIcon size={18} />,
          path: "/subscriptions",
          active: location.pathname.startsWith("/subscriptions"),
        },
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
          id: "users",
          label: "Central Users",
          icon: <UserIcon size={18} />,
          path: "/users",
          active: location.pathname.startsWith("/users"),
        },
        {
          id: "entitlements",
          label: "Product Access",
          icon: <ShieldCheckIcon size={18} />,
          path: "/organization-product-entitlements",
          active: location.pathname.startsWith("/organization-product-entitlements"),
        },
        {
          id: "bulk-import",
          label: "Data Import & Migration",
          icon: <UploadIcon size={18} />,
          path: "/bulk-import",
          active: location.pathname.startsWith("/bulk-import"),
        },
        {
          id: "access-requests",
          label: "Access Requests & Approvals",
          icon: <ShieldCheckIcon size={18} />,
          path: "/access-requests",
          active: location.pathname.startsWith("/access-requests"),
        },
        {
          id: "showcase",
          label: "Product Showcase",
          icon: <StarIcon size={18} />,
          path: "/showcase",
          active: location.pathname.startsWith("/showcase"),
        },
        {
          id: "notifications",
          label: "Notifications",
          icon: <LayersIcon size={18} />,
          path: "/notifications",
          active: location.pathname.startsWith("/notifications"),
        },
        {
          id: "white-labeling",
          label: "White Labeling",
          icon: <LayersIcon size={18} />,
          path: "/white-labeling",
          active: location.pathname.startsWith("/white-labeling"),
        },
        {
          id: "usage",
          label: "Usage & Metering",
          icon: <GridIcon size={18} />,
          path: "/usage",
          active: location.pathname.startsWith("/usage"),
        },
        {
          id: "billing",
          label: "Billing & Invoices",
          icon: <CreditCardIcon size={18} />,
          path: "/billing",
          active: location.pathname.startsWith("/billing"),
        },
        {
          id: "reconciliation",
          label: "Reconciliation",
          icon: <ShieldCheckIcon size={18} />,
          path: "/reconciliation",
          active: location.pathname.startsWith("/reconciliation"),
        },
        {
          id: "reports",
          label: "Advanced Analytics, Adoption & Tenant Health",
          icon: <GridIcon size={18} />,
          path: "/reports",
          active: location.pathname.startsWith("/reports"),
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
          id: "activity-log",
          label: "Security, Privacy, Retention & Compliance",
          icon: <HistoryIcon size={18} />,
          path: "/activity-log",
          active: location.pathname.startsWith("/activity-log"),
        },
        {
          id: "developer-oversight",
          label: "Developer & API Console",
          icon: <CodeIcon size={18} />,
          path: "/owner/developer-oversight",
          active: location.pathname.startsWith("/owner/developer-oversight"),
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
      ]
    : user?.active_context?.type === "support"
    ? [
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
      ]
    : isMember
    ? [
        {
          id: "my-products",
          label: "My Products & Launcher",
          icon: <BoxIcon size={18} />,
          path: "/tenant/products",
          active:
            location.pathname.startsWith("/tenant/products") ||
            location.pathname.startsWith("/tenant/workspace"),
        },
      ]
    : [
        ...TENANT_MODULES_REGISTRY.filter((mod) => {
          if (!mod.implemented) return false;
          if (
            mod.requiredModule &&
            !user?.active_context?.allowed_modules?.includes(mod.requiredModule)
          ) {
            return false;
          }
          if (
            mod.requiredPermission &&
            !user?.active_context?.effective_permissions?.includes(mod.requiredPermission)
          ) {
            return false;
          }
          return true;
        }).map((mod) => ({
          id: mod.id,
          label: mod.label,
          icon: renderTenantIcon(mod.icon),
          path: mod.path,
          active:
            mod.path === "/tenant"
              ? location.pathname === "/tenant"
              : mod.path === "/tenant/products"
              ? location.pathname.startsWith("/tenant/products") ||
                location.pathname.startsWith("/tenant/workspace")
              : location.pathname.startsWith(mod.path),
        })),
        {
          id: "marketplace",
          label: "Marketplace",
          icon: <BoxIcon size={18} />,
          path: "/tenant/marketplace",
          active: location.pathname.startsWith("/tenant/marketplace"),
        },
        {
          id: "developer-console",
          label: "Developer & API Console",
          icon: <CodeIcon size={18} />,
          path: "/tenant/developer",
          active: location.pathname.startsWith("/tenant/developer"),
        },
      ];

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
      <div className="app-shell-body">
        {/* Desktop LMS-Style Sidebar */}
        <aside
          className="desktop-sidebar"
          aria-label="Sidebar navigation"
        >
          <div className="sidebar-content-inner">
            {/* Section Heading */}
            <div className="sidebar-section-header">
              Overview
            </div>

            {/* Navigation Items (Scrolls independently if needed) */}
            <nav style={{ flex: 1, overflowY: "auto", overflowX: "hidden", display: "flex", flexDirection: "column", gap: "0.25rem" }}>
              {navItems.map((item) => (
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
                      <span className="sidebar-icon-pill">
                        {item.icon}
                      </span>
                    </span>

                    <span className="sidebar-nav-label">
                      {item.label}
                    </span>
                  </button>

                  {/* Floating tooltip displayed only in collapsed state */}
                  <span className="sidebar-tooltip" role="tooltip">
                    {item.label}
                  </span>
                </div>
              ))}
            </nav>

            {/* Bottom Context Status */}
            <div className="sidebar-bottom-status">
              <div className="status-item-pill">
                <span className="status-icon-box">
                  {isOwnerContext ? (
                    <ShieldCheckIcon size={16} style={{ color: "var(--status-success)" }} />
                  ) : (
                    <BuildingIcon size={16} style={{ color: "rgb(99, 102, 241)" }} />
                  )}
                </span>
                <span className="status-label-text">
                  {isOwnerContext
                    ? "Platform Owner"
                    : isMember
                    ? `Member (${user?.active_context?.organization?.code || ""})`
                    : `Tenant Admin (${user?.active_context?.organization?.code || ""})`}
                </span>
              </div>
              <span className="sidebar-tooltip" role="tooltip">
                {isOwnerContext
                  ? "Platform Owner Active"
                  : isMember
                  ? `Member: ${user?.active_context?.organization?.name || ""}`
                  : `Tenant Admin: ${user?.active_context?.organization?.name || ""}`}
              </span>
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
                <button
                  key={item.id}
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
        /* AppShell Body: CSS Grid Controls Column Widths Synchronously */
        .app-shell-body {
          --sidebar-width: 56px;
          display: grid;
          grid-template-columns: var(--sidebar-width) minmax(0, 1fr);
          align-items: start;
          transition: grid-template-columns 200ms cubic-bezier(0.22, 1, 0.36, 1);
          min-height: calc(100dvh - 56px);
          width: 100%;
          position: relative;
        }

        /* Persistent Sidebar Track Surface covering full scrollable page height */
        .app-shell-body::before {
          content: "";
          position: absolute;
          top: 0;
          bottom: 0;
          left: 0;
          width: var(--sidebar-width);
          background: var(--glass-surface-elevated);
          border-right: 1px solid var(--border-subtle);
          pointer-events: none;
          z-index: 10;
          transition: width 200ms cubic-bezier(0.22, 1, 0.36, 1);
        }

        /* Hover & Focus-Within Expansion (Desktop fine pointer only) */
        @media (hover: hover) and (pointer: fine) and (min-width: 768px) {
          .app-shell-body:has(.desktop-sidebar:hover),
          .app-shell-body:has(.desktop-sidebar:focus-within) {
            --sidebar-width: 228px;
          }

          .app-shell-body:has(.desktop-sidebar:hover) .sidebar-section-header,
          .app-shell-body:has(.desktop-sidebar:focus-within) .sidebar-section-header {
            opacity: 1;
            transform: translateX(0);
            pointer-events: auto;
          }

          .app-shell-body:has(.desktop-sidebar:hover) .sidebar-nav-label,
          .app-shell-body:has(.desktop-sidebar:focus-within) .sidebar-nav-label {
            opacity: 1;
            transform: translateX(0);
            pointer-events: auto;
          }

          .app-shell-body:has(.desktop-sidebar:hover) .status-label-text,
          .app-shell-body:has(.desktop-sidebar:focus-within) .status-label-text {
            opacity: 1;
            transform: translateX(0);
            pointer-events: auto;
          }

          /* Suppress floating tooltips when sidebar is expanded */
          .app-shell-body:has(.desktop-sidebar:hover) .sidebar-tooltip,
          .app-shell-body:has(.desktop-sidebar:focus-within) .sidebar-tooltip {
            display: none !important;
          }
        }

        /* Desktop Sidebar Surface (Solid, 0 backdrop-filter, 0 clip-path) */
        .desktop-sidebar {
          width: 100%;
          min-width: 0;
          overflow: hidden;
          background: var(--glass-surface-elevated);
          border-right: 1px solid var(--border-subtle);
          display: flex;
          flex-direction: column;
          height: calc(100dvh - 56px);
          position: sticky;
          top: 56px;
          align-self: start;
          user-select: none;
          z-index: 20;
        }

        .sidebar-content-inner {
          width: 228px;
          height: 100%;
          display: flex;
          flex-direction: column;
          padding: 1.25rem 0;
          box-sizing: border-box;
        }

        /* Section Header */
        .sidebar-section-header {
          font-size: 0.6875rem;
          font-weight: 700;
          text-transform: uppercase;
          letter-spacing: 0.08em;
          color: var(--text-muted);
          padding: 0.25rem 1.5rem 0.5rem;
          white-space: nowrap;
          opacity: 0;
          transform: translateX(-8px);
          pointer-events: none;
          transition: opacity 120ms ease, transform 180ms cubic-bezier(0.22, 1, 0.36, 1);
        }

        /* Nav Item Wrapper & Button */
        .nav-item-wrapper {
          position: relative;
          width: 100%;
          padding: 0 0.25rem;
          box-sizing: border-box;
        }

        .sidebar-nav-btn {
          position: relative;
          width: 100%;
          height: 44px;
          display: flex;
          align-items: center;
          background: transparent;
          border: none;
          border-radius: 8px;
          color: var(--text-secondary);
          cursor: pointer;
          padding: 0;
          outline: none;
          font-family: inherit;
          transition: background-color 0.15s ease, color 0.15s ease;
        }

        .sidebar-nav-btn:hover {
          background: var(--glass-surface-hover);
          color: var(--text-primary);
        }

        .sidebar-nav-btn.active {
          background: var(--brand-primary-light);
          color: var(--brand-primary);
          font-weight: 600;
        }

        /* Active Far-Left Vertical Edge Indicator */
        .active-edge-indicator {
          position: absolute;
          left: -4px;
          top: 8px;
          bottom: 8px;
          width: 3px;
          background: var(--brand-primary);
          border-radius: 0 3px 3px 0;
        }

        .sidebar-icon-box {
          flex: 0 0 auto;
          width: 48px;
          height: 44px;
          display: flex;
          align-items: center;
          justify-content: center;
          flex-shrink: 0;
        }

        .sidebar-icon-pill {
          width: 34px;
          height: 34px;
          display: flex;
          align-items: center;
          justify-content: center;
          border-radius: 8px;
          transition: background-color 0.15s ease;
        }

        .sidebar-nav-label {
          font-size: 0.875rem;
          font-weight: 600;
          white-space: nowrap;
          opacity: 0;
          transform: translateX(-6px);
          pointer-events: none;
          transition: opacity 120ms ease, transform 180ms cubic-bezier(0.22, 1, 0.36, 1);
          padding-left: 0.25rem;
          color: var(--text-primary);
        }

        /* Collapsed Floating Tooltip */
        .sidebar-tooltip {
          position: absolute;
          left: 62px;
          top: 50%;
          transform: translateY(-50%);
          background: var(--glass-surface-elevated);
          color: var(--text-primary);
          border: 1px solid var(--border-glass);
          box-shadow: var(--shadow-md);
          padding: 0.35rem 0.65rem;
          border-radius: 6px;
          font-size: 0.75rem;
          font-weight: 600;
          white-space: nowrap;
          pointer-events: none;
          opacity: 0;
          visibility: hidden;
          transition: opacity 0.12s ease, visibility 0.12s ease;
          z-index: 40;
        }

        .nav-item-wrapper:hover .sidebar-tooltip,
        .sidebar-nav-btn:focus-visible + .sidebar-tooltip {
          opacity: 1;
          visibility: visible;
        }

        /* Bottom Status Area */
        .sidebar-bottom-status {
          position: relative;
          margin-top: auto;
          padding: 0.75rem 0.25rem 0;
          border-top: 1px solid var(--border-subtle);
        }

        .status-item-pill {
          height: 40px;
          display: flex;
          align-items: center;
          background: var(--glass-surface);
          border: 1px solid var(--border-subtle);
          border-radius: 8px;
          overflow: hidden;
        }

        .status-icon-box {
          width: 48px;
          height: 40px;
          display: flex;
          align-items: center;
          justify-content: center;
          flex-shrink: 0;
        }

        .status-label-text {
          font-size: 0.75rem;
          font-weight: 600;
          color: var(--text-secondary);
          white-space: nowrap;
          opacity: 0;
          transform: translateX(-6px);
          pointer-events: none;
          transition: opacity 120ms ease, transform 180ms cubic-bezier(0.22, 1, 0.36, 1);
          padding-right: 0.5rem;
        }

        .sidebar-bottom-status:hover .sidebar-tooltip {
          opacity: 1;
          visibility: visible;
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
          .sidebar-section-header,
          .sidebar-nav-label,
          .status-label-text {
            transition: none !important;
          }
        }
      `}</style>
    </div>
  );
};
