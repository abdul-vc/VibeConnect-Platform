/**
 * Enterprise Global Search Dropdown Component.
 *
 * Provides a normal, direct in-header search bar with an attached dropdown menu:
 * - Direct in-place typing right in the header bar (no full-screen modal or screen dimming).
 * - Real-time, tenant-isolated live search queries across Organizations, Members, Roles, Products, and Navigation.
 * - Keyboard navigation (Arrow Up/Down, Enter to select, Escape to close, Ctrl+K to focus).
 * - Click-outside dismissible dropdown.
 *
 * Exclusively consumes centralized API domain services with zero hardcoded URLs.
 */

import React, { useState, useEffect, useRef, useMemo, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import type { AuthenticatedUser, TenantProductAccessItem } from "../../api/types.ts";
import { organizationsApi } from "../../api/organizations.ts";
import { usersApi } from "../../api/users.ts";
import { productsApi } from "../../api/products.ts";
import { membershipsApi } from "../../api/memberships.ts";
import { rolesApi } from "../../api/roles.ts";
import {
  SearchIcon,
  CloseIcon,
  BuildingIcon,
  UserIcon,
  BoxIcon,
  GridIcon,
  ShieldCheckIcon,
  CreditCardIcon,
  CodeIcon,
  LayersIcon,
  StarIcon,
  HistoryIcon,
  PlusIcon,
} from "../Icons.tsx";

export interface GlobalSearchBarProps {
  readonly user: AuthenticatedUser | null;
  readonly tenantProducts?: readonly TenantProductAccessItem[];
}

export interface SearchResultItem {
  readonly id: string;
  readonly category: string;
  readonly title: string;
  readonly subtitle?: string;
  readonly badge?: string;
  readonly badgeVariant?: "success" | "warning" | "info" | "neutral" | "danger";
  readonly icon: React.ReactNode;
  readonly path: string;
  readonly actionHint?: string;
}

export const GlobalSearchBar: React.FC<GlobalSearchBarProps> = ({
  user,
  tenantProducts = [],
}) => {
  const navigate = useNavigate();
  const containerRef = useRef<HTMLDivElement | null>(null);
  const inputRef = useRef<HTMLInputElement | null>(null);
  const listRef = useRef<HTMLDivElement | null>(null);

  const [query, setQuery] = useState("");
  const [isOpen, setIsOpen] = useState(false);
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [isLoading, setIsLoading] = useState(false);

  // Dynamic live search state
  const [liveOrganizations, setLiveOrganizations] = useState<SearchResultItem[]>([]);
  const [liveUsers, setLiveUsers] = useState<SearchResultItem[]>([]);
  const [liveProducts, setLiveProducts] = useState<SearchResultItem[]>([]);
  const [liveMembers, setLiveMembers] = useState<SearchResultItem[]>([]);
  const [liveRoles, setLiveRoles] = useState<SearchResultItem[]>([]);

  const isOwnerContext = user?.active_context?.type === "platform_owner";
  const isTenantContext = user?.active_context?.type === "tenant";
  const isMember = isTenantContext && user?.active_context?.membership_type === "member";
  const isTenantAdmin = isTenantContext && !isMember;
  const currentOrgId = user?.active_context?.organization?.id;

  // Global Ctrl+K / Cmd+K shortcut listener to focus header search
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        inputRef.current?.focus();
        setIsOpen(true);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => {
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, []);

  // Click-outside listener to close dropdown
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (
        containerRef.current &&
        !containerRef.current.contains(e.target as Node)
      ) {
        setIsOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, []);

  // Console Navigation Modules for instant navigation
  const consoleNavItems: SearchResultItem[] = useMemo(() => {
    if (isOwnerContext) {
      return [
        {
          id: "nav-overview",
          category: "Console Navigation",
          title: "Overview",
          subtitle: "Platform metrics, KPIs, and executive health summary",
          icon: <GridIcon size={16} />,
          path: "/",
        },
        {
          id: "nav-organizations",
          category: "Console Navigation",
          title: "Organization Registry",
          subtitle: "Tenant enterprises, domains, and lifecycle status",
          icon: <BuildingIcon size={16} />,
          path: "/organizations",
        },
        {
          id: "nav-users",
          category: "Console Navigation",
          title: "Central Users",
          subtitle: "Directory of global identities and authentication records",
          icon: <UserIcon size={16} />,
          path: "/users",
        },
        {
          id: "nav-onboarding",
          category: "Console Navigation",
          title: "Tenant Onboarding",
          subtitle: "Multi-tenant enterprise provisioning wizard",
          icon: <PlusIcon size={16} />,
          path: "/onboarding",
        },
        {
          id: "nav-subscriptions",
          category: "Console Navigation",
          title: "Subscriptions",
          subtitle: "Active enterprise contracts, terms, and auto-renewals",
          icon: <CreditCardIcon size={16} />,
          path: "/subscriptions",
        },
        {
          id: "nav-billing",
          category: "Console Navigation",
          title: "Billing & Invoices",
          subtitle: "Invoicing schedules, settlements, and payment history",
          icon: <CreditCardIcon size={16} />,
          path: "/billing",
        },
        {
          id: "nav-showcase",
          category: "Console Navigation",
          title: "Product Showcase",
          subtitle: "Interactive portfolio and live launchable products",
          icon: <StarIcon size={16} />,
          path: "/showcase",
        },
        {
          id: "nav-usage",
          category: "Console Navigation",
          title: "Usage & Metering",
          subtitle: "Real-time consumption counters and seat limits",
          icon: <GridIcon size={16} />,
          path: "/usage",
        },
        {
          id: "nav-reconciliation",
          category: "Console Navigation",
          title: "Reconciliation",
          subtitle: "Entitlement auditing and automated quota repair",
          icon: <ShieldCheckIcon size={16} />,
          path: "/reconciliation",
        },
        {
          id: "nav-reports",
          category: "Console Navigation",
          title: "Reports & Analytics",
          subtitle: "Exportable revenue, utilization, and tenant reports",
          icon: <GridIcon size={16} />,
          path: "/reports",
        },
        {
          id: "nav-developer",
          category: "Console Navigation",
          title: "Developer Console",
          subtitle: "System API endpoints, token credentials, and webhooks",
          icon: <CodeIcon size={16} />,
          path: "/owner/developer-oversight",
        },
        {
          id: "nav-integration",
          category: "Console Navigation",
          title: "Integration Hub",
          subtitle: "Enterprise connector health and webhook pipelines",
          icon: <LayersIcon size={16} />,
          path: "/integration",
        },
        {
          id: "nav-compliance",
          category: "Console Navigation",
          title: "Security & Compliance",
          subtitle: "Immutable platform audit trail and security events",
          icon: <HistoryIcon size={16} />,
          path: "/activity-log",
        },
      ];
    }

    if (isTenantAdmin) {
      return [
        {
          id: "nav-tenant-overview",
          category: "Console Navigation",
          title: "Tenant Overview",
          subtitle: "Organization health, member seats, and product usage",
          icon: <GridIcon size={16} />,
          path: "/tenant",
        },
        {
          id: "nav-tenant-members",
          category: "Console Navigation",
          title: "Member Directory",
          subtitle: "Manage enterprise team members and permissions",
          icon: <UserIcon size={16} />,
          path: "/tenant/members",
        },
        {
          id: "nav-tenant-member-onboarding",
          category: "Console Navigation",
          title: "Member Onboarding",
          subtitle: "Invite new team members and assign workspace roles",
          icon: <UserIcon size={16} />,
          path: "/tenant/member-onboarding",
        },
        {
          id: "nav-tenant-roles",
          category: "Console Navigation",
          title: "Roles & Permissions",
          subtitle: "Custom RBAC roles and module access controls",
          icon: <ShieldCheckIcon size={16} />,
          path: "/tenant/roles",
        },
        {
          id: "nav-tenant-products",
          category: "Console Navigation",
          title: "My Products & App Launcher",
          subtitle: "Launch subscribed enterprise software products",
          icon: <BoxIcon size={16} />,
          path: "/tenant/products",
        },
        {
          id: "nav-tenant-subscriptions",
          category: "Console Navigation",
          title: "Subscriptions Overview",
          subtitle: "Active tier plans, quotas, and renewal dates",
          icon: <CreditCardIcon size={16} />,
          path: "/tenant/subscriptions",
        },
        {
          id: "nav-tenant-billing",
          category: "Console Navigation",
          title: "Billing & Invoices",
          subtitle: "Enterprise invoices, receipts, and payment status",
          icon: <CreditCardIcon size={16} />,
          path: "/tenant/billing",
        },
        {
          id: "nav-tenant-usage",
          category: "Console Navigation",
          title: "Usage & Quotas",
          subtitle: "Monitor active seat quotas and storage consumption",
          icon: <GridIcon size={16} />,
          path: "/tenant/usage",
        },
        {
          id: "nav-tenant-marketplace",
          category: "Console Navigation",
          title: "Marketplace",
          subtitle: "Discover and request additional enterprise modules",
          icon: <BoxIcon size={16} />,
          path: "/tenant/marketplace",
        },
        {
          id: "nav-tenant-developer",
          category: "Console Navigation",
          title: "Developer & API Console",
          subtitle: "Tenant API keys, webhooks, and sandbox testing",
          icon: <CodeIcon size={16} />,
          path: "/tenant/developer",
        },
        {
          id: "nav-tenant-security",
          category: "Console Navigation",
          title: "Security Policies",
          subtitle: "MFA enforcement, IP allowlisting, and session timeouts",
          icon: <ShieldCheckIcon size={16} />,
          path: "/tenant/security",
        },
        {
          id: "nav-tenant-idp",
          category: "Console Navigation",
          title: "Identity Providers",
          subtitle: "SAML 2.0 and OIDC single sign-on integration",
          icon: <ShieldCheckIcon size={16} />,
          path: "/tenant/idp",
        },
        {
          id: "nav-tenant-audit",
          category: "Console Navigation",
          title: "Audit Log",
          subtitle: "Organization activity log and user actions",
          icon: <HistoryIcon size={16} />,
          path: "/tenant/audit",
        },
        {
          id: "nav-tenant-settings",
          category: "Console Navigation",
          title: "Tenant Settings",
          subtitle: "Organization profile, domain, and localization",
          icon: <BuildingIcon size={16} />,
          path: "/tenant/settings",
        },
      ];
    }

    if (isMember) {
      return [
        {
          id: "nav-member-workspace",
          category: "Console Navigation",
          title: "Workspace App Launcher",
          subtitle: "Access all your assigned tools and applications",
          icon: <BoxIcon size={16} />,
          path: "/tenant",
        },
        {
          id: "nav-member-profile",
          category: "Console Navigation",
          title: "My Profile",
          subtitle: "View account settings and assigned permissions",
          icon: <UserIcon size={16} />,
          path: "/tenant/profile",
        },
        {
          id: "nav-member-notifications",
          category: "Console Navigation",
          title: "Notifications",
          subtitle: "Workspace alerts and system announcements",
          icon: <LayersIcon size={16} />,
          path: "/tenant/notifications",
        },
      ];
    }

    // Support or fallback
    return [
      {
        id: "nav-support-overview",
        category: "Console Navigation",
        title: "Support Console",
        subtitle: "Customer operations, ticket routing, and diagnostics",
        icon: <ShieldCheckIcon size={16} />,
        path: "/owner/support-console",
      },
    ];
  }, [isOwnerContext, isTenantAdmin, isMember]);

  // Filtered navigation items matching query
  const filteredNavItems = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) {
      // When dropdown opens with empty query, show top navigation quick links
      return consoleNavItems.slice(0, 5);
    }
    return consoleNavItems.filter(
      (item) =>
        item.title.toLowerCase().includes(q) ||
        (item.subtitle && item.subtitle.toLowerCase().includes(q))
    );
  }, [consoleNavItems, query]);

  // Entitled products items matching query (for Tenant Admin & Member)
  const entitledProductItems: SearchResultItem[] = useMemo(() => {
    if (!isTenantContext || !tenantProducts.length) return [];
    const q = query.trim().toLowerCase();
    const matching = q
      ? tenantProducts.filter(
          (p) =>
            p.name.toLowerCase().includes(q) ||
            p.code.toLowerCase().includes(q) ||
            (p.description && p.description.toLowerCase().includes(q))
        )
      : tenantProducts;

    return matching.map((p) => ({
      id: `entitled-prod-${p.id}`,
      category: "Products & Workspaces",
      title: p.name,
      subtitle: p.description || `Product Code: ${p.code}`,
      badge: "Launchable",
      badgeVariant: "success",
      icon: <BoxIcon size={16} />,
      path: `/tenant/workspace/${p.id}`,
      actionHint: "Launch Workspace ↵",
    }));
  }, [isTenantContext, tenantProducts, query]);

  // Debounced real-time live queries
  useEffect(() => {
    const trimmed = query.trim();
    if (!trimmed) {
      setLiveOrganizations([]);
      setLiveUsers([]);
      setLiveProducts([]);
      setLiveMembers([]);
      setLiveRoles([]);
      setIsLoading(false);
      return;
    }

    const abortController = new AbortController();
    setIsLoading(true);

    const debounceTimer = setTimeout(async () => {
      try {
        if (isOwnerContext) {
          // Fetch real-time Organizations, Users, and Products concurrently
          const [orgsRes, usersRes, prodsRes] = await Promise.allSettled([
            organizationsApi.list({ search: trimmed, page_size: 5 }, abortController.signal),
            usersApi.list({ search: trimmed, page_size: 5 }, abortController.signal),
            productsApi.list({ search: trimmed, page_size: 5 }, abortController.signal),
          ]);

          if (orgsRes.status === "fulfilled" && orgsRes.value?.results) {
            setLiveOrganizations(
              orgsRes.value.results.map((org) => ({
                id: `org-${org.id}`,
                category: "Organizations",
                title: org.name,
                subtitle: `Domain/Code: ${org.code}`,
                badge: org.status.toUpperCase(),
                badgeVariant: org.status === "active" ? "success" : "neutral",
                icon: <BuildingIcon size={16} />,
                path: `/organizations?search=${encodeURIComponent(org.code || org.name)}`,
                actionHint: "View in Registry ↵",
              }))
            );
          }

          if (usersRes.status === "fulfilled" && usersRes.value?.results) {
            setLiveUsers(
              usersRes.value.results.map((u) => ({
                id: `user-${u.id}`,
                category: "Central Users",
                title: u.full_name || u.email,
                subtitle: u.email,
                badge: u.status.toUpperCase(),
                badgeVariant: u.status === "active" ? "success" : "warning",
                icon: <UserIcon size={16} />,
                path: `/users?search=${encodeURIComponent(u.email)}`,
                actionHint: "View User ↵",
              }))
            );
          }

          if (prodsRes.status === "fulfilled" && prodsRes.value?.results) {
            setLiveProducts(
              prodsRes.value.results.map((prod) => ({
                id: `prod-${prod.id}`,
                category: "Products & Registry",
                title: prod.name,
                subtitle: prod.description || `Code: ${prod.code}`,
                badge: prod.status.toUpperCase(),
                badgeVariant: prod.status === "active" ? "success" : "neutral",
                icon: <BoxIcon size={16} />,
                path: `/showcase?product=${encodeURIComponent(prod.code)}&demo=true`,
                actionHint: "Open in Showcase ↵",
              }))
            );
          }
        } else if (isTenantAdmin && currentOrgId) {
          // Fetch real-time Members and Roles concurrently
          const [membersRes, rolesRes] = await Promise.allSettled([
            membershipsApi.list(
              currentOrgId,
              { search: trimmed, page_size: 5 },
              abortController.signal
            ),
            rolesApi.listRoles({ page: 1, page_size: 20 }, abortController.signal),
          ]);

          if (membersRes.status === "fulfilled" && membersRes.value?.results) {
            setLiveMembers(
              membersRes.value.results.map((m) => ({
                id: `member-${m.id}`,
                category: "Organization Members",
                title: m.user?.full_name || m.user?.email || "Member",
                subtitle: m.user?.email,
                badge: m.membership_type === "tenant_admin" ? "ADMIN" : "MEMBER",
                badgeVariant: m.membership_type === "tenant_admin" ? "info" : "neutral",
                icon: <UserIcon size={16} />,
                path: `/tenant/members?search=${encodeURIComponent(m.user?.email || "")}`,
                actionHint: "View Member ↵",
              }))
            );
          }

          if (rolesRes.status === "fulfilled" && rolesRes.value?.results) {
            const matchedRoles = rolesRes.value.results.filter(
              (r) =>
                r.name.toLowerCase().includes(trimmed.toLowerCase()) ||
                (r.description && r.description.toLowerCase().includes(trimmed.toLowerCase()))
            );
            setLiveRoles(
              matchedRoles.slice(0, 5).map((r) => ({
                id: `role-${r.id}`,
                category: "Roles & Permissions",
                title: r.name,
                subtitle: r.description || `Assigned Members: ${r.assigned_members_count}`,
                badge: `${r.assigned_members_count} Users`,
                badgeVariant: "neutral",
                icon: <ShieldCheckIcon size={16} />,
                path: "/tenant/roles",
                actionHint: "Configure Role ↵",
              }))
            );
          }
        }
      } catch {
        // Safe graceful non-blocking error handling
      } finally {
        if (!abortController.signal.aborted) {
          setIsLoading(false);
        }
      }
    }, 240);

    return () => {
      clearTimeout(debounceTimer);
      abortController.abort();
    };
  }, [query, isOwnerContext, isTenantAdmin, currentOrgId]);

  // Combine and order all results
  const flattenedResults: SearchResultItem[] = useMemo(() => {
    const list: SearchResultItem[] = [];

    // Prioritize Live Entitled Products for Tenant Members/Admins
    if (entitledProductItems.length > 0) {
      list.push(...entitledProductItems);
    }

    // Live Organizations
    if (liveOrganizations.length > 0) {
      list.push(...liveOrganizations);
    }

    // Live Central Users
    if (liveUsers.length > 0) {
      list.push(...liveUsers);
    }

    // Live Organization Members
    if (liveMembers.length > 0) {
      list.push(...liveMembers);
    }

    // Live Products (Platform Owner)
    if (liveProducts.length > 0) {
      list.push(...liveProducts);
    }

    // Live Roles (Tenant Admin)
    if (liveRoles.length > 0) {
      list.push(...liveRoles);
    }

    // Navigation and Modules
    if (filteredNavItems.length > 0) {
      list.push(...filteredNavItems);
    }

    return list;
  }, [
    entitledProductItems,
    liveOrganizations,
    liveUsers,
    liveMembers,
    liveProducts,
    liveRoles,
    filteredNavItems,
  ]);

  // Clamp selected index
  useEffect(() => {
    if (selectedIndex >= flattenedResults.length) {
      setSelectedIndex(Math.max(0, flattenedResults.length - 1));
    }
  }, [flattenedResults.length, selectedIndex]);

  // Handle item navigation
  const handleSelectItem = useCallback(
    (item: SearchResultItem) => {
      setIsOpen(false);
      setQuery("");
      inputRef.current?.blur();
      navigate(item.path);
    },
    [navigate]
  );

  // Keyboard navigation inside input
  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (!isOpen) {
      if (e.key === "ArrowDown" || e.key === "Enter") {
        setIsOpen(true);
      }
      return;
    }

    if (e.key === "ArrowDown") {
      e.preventDefault();
      setSelectedIndex((prev) =>
        prev < flattenedResults.length - 1 ? prev + 1 : 0
      );
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setSelectedIndex((prev) =>
        prev > 0 ? prev - 1 : Math.max(0, flattenedResults.length - 1)
      );
    } else if (e.key === "Enter") {
      e.preventDefault();
      if (flattenedResults[selectedIndex]) {
        handleSelectItem(flattenedResults[selectedIndex]);
      }
    } else if (e.key === "Escape") {
      e.preventDefault();
      setIsOpen(false);
      inputRef.current?.blur();
    }
  };

  // Group items by category for structured visual display
  const groupedResults = useMemo(() => {
    const groups: { [key: string]: SearchResultItem[] } = {};
    for (const item of flattenedResults) {
      if (!groups[item.category]) {
        groups[item.category] = [];
      }
      groups[item.category].push(item);
    }
    return groups;
  }, [flattenedResults]);

  const placeholderText = isOwnerContext
    ? "Search organizations, users, products, or modules..."
    : isTenantAdmin
    ? "Search members, entitled products, roles, or modules..."
    : "Search assigned tools, workspaces, or settings...";

  return (
    <div
      className="header-search-container"
      ref={containerRef}
      style={{ position: "relative" }}
    >
      {/* Real In-Header Search Input Bar */}
      <div
        className={`header-search-bar ${isOpen ? "focused" : ""}`}
        onClick={() => {
          inputRef.current?.focus();
          setIsOpen(true);
        }}
      >
        <SearchIcon
          size={14}
          style={{
            color: isOpen ? "var(--brand-primary)" : "var(--text-muted)",
            flexShrink: 0,
            transition: "color 0.15s ease",
          }}
        />
        <input
          ref={inputRef}
          type="text"
          className="header-search-input"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setIsOpen(true);
            setSelectedIndex(0);
          }}
          onFocus={() => setIsOpen(true)}
          onKeyDown={handleKeyDown}
          placeholder={placeholderText}
          aria-label="Search across platform"
          aria-autocomplete="list"
          autoComplete="off"
          spellCheck="false"
        />

        {isLoading && <div className="header-search-spinner" title="Loading live data..." />}

        {query.length > 0 && !isLoading && (
          <button
            type="button"
            className="header-search-clear-btn"
            onClick={(e) => {
              e.stopPropagation();
              setQuery("");
              setSelectedIndex(0);
              inputRef.current?.focus();
            }}
            aria-label="Clear search"
          >
            <CloseIcon size={12} />
          </button>
        )}

        <kbd className="header-search-kbd">Ctrl K</kbd>
      </div>

      {/* Normal Attached Dropdown Menu (No backdrop/dialogue box) */}
      {isOpen && (
        <div
          className="header-search-dropdown"
          ref={listRef}
          role="listbox"
          aria-label="Search suggestions"
        >
          {flattenedResults.length === 0 ? (
            <div className="header-search-empty">
              <SearchIcon size={24} style={{ opacity: 0.35, marginBottom: "0.5rem" }} />
              <div className="header-search-empty-title">
                No matching results found for &ldquo;{query}&rdquo;
              </div>
              <div className="header-search-empty-hint">
                {isOwnerContext
                  ? "Try searching by organization name, central user email, product title, or console module."
                  : isTenantAdmin
                  ? "Try searching by member email, entitled product name, or role title."
                  : "Try searching by workspace product name."}
              </div>
            </div>
          ) : (
            <div className="header-search-results-list">
              {Object.entries(groupedResults).map(([category, items]) => (
                <div key={category} className="header-search-group">
                  <div className="header-search-group-header">
                    <span>{category}</span>
                    <span className="header-search-group-count">{items.length}</span>
                  </div>
                  {items.map((item) => {
                    const globalIdx = flattenedResults.findIndex((r) => r.id === item.id);
                    const isSelected = globalIdx === selectedIndex;

                    return (
                      <div
                        key={item.id}
                        className={`header-search-item ${isSelected ? "selected" : ""}`}
                        onClick={() => handleSelectItem(item)}
                        onMouseEnter={() => setSelectedIndex(globalIdx)}
                        role="option"
                        aria-selected={isSelected}
                      >
                        <div className="header-search-item-icon">{item.icon}</div>
                        <div className="header-search-item-content">
                          <div className="header-search-item-title-row">
                            <span className="header-search-item-title">{item.title}</span>
                            {item.badge && (
                              <span
                                className={`header-search-badge ${
                                  item.badgeVariant || "neutral"
                                }`}
                              >
                                {item.badge}
                              </span>
                            )}
                          </div>
                          {item.subtitle && (
                            <div className="header-search-item-subtitle">{item.subtitle}</div>
                          )}
                        </div>
                        <div className="header-search-item-action">
                          {item.actionHint || "Open ↵"}
                        </div>
                      </div>
                    );
                  })}
                </div>
              ))}
            </div>
          )}

          {/* Dropdown Footer with Shortcuts */}
          <div className="header-search-dropdown-footer">
            <div className="header-search-shortcuts">
              <span className="search-shortcut-item">
                <kbd>↑</kbd> <kbd>↓</kbd> navigate
              </span>
              <span className="search-shortcut-item">
                <kbd>↵</kbd> select
              </span>
              <span className="search-shortcut-item">
                <kbd>esc</kbd> close
              </span>
            </div>
            <div className="header-search-status">
              <span className="live-dot" /> Real-time search
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

