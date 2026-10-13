/**
 * Tenant Roles & Permissions Workspace (Phase 2E Stage 6).
 *
 * Provides Tenant Administrators with:
 * - Two accessible tabs: "Roles" and "Administrative Assignments"
 * - Roles tab: Paginated system & custom roles, type/status badges, permission chips, member counts, actions
 * - Administrative Assignments tab: Tenant Admin memberships, status filter, assigned role display, reassignment
 * - Modals: RoleEditorModal (create/edit), RetireRoleDialog (destruction confirmation), AssignRoleModal (assignment)
 * - Liquid Glass visual design, high-contrast dark/light theme, full keyboard accessibility, responsive card layout
 */

import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ApiError } from "../../api/client.ts";
import { rolesApi } from "../../api/roles.ts";
import type {
  AdministrativeMembershipItem,
  RoleItem,
} from "../../api/types.ts";
import { AppShell } from "../../components/AppShell.tsx";
import {
  AlertCircleIcon,
  ChevronLeftIcon,
  ChevronRightIcon,
  FilterIcon,
  PlusIcon,
  RotateCcwIcon,
  ShieldCheckIcon,
  UserIcon,
} from "../../components/Icons.tsx";
import { formatDateTime } from "../../config/dateUtils.ts";
import { useAuth } from "../../context/AuthContext.tsx";
import { AssignRoleModal } from "../../components/tenant/AssignRoleModal.tsx";
import { RetireRoleDialog } from "../../components/tenant/RetireRoleDialog.tsx";
import { RoleEditorModal } from "../../components/tenant/RoleEditorModal.tsx";

type WorkspaceTab = "roles" | "assignments";

export const TenantRolesPage: React.FC = () => {
  const { user } = useAuth();
  const organization = user?.active_context?.organization;
  const effectivePermissions = useMemo(() => {
    return new Set(user?.active_context?.effective_permissions ?? []);
  }, [user?.active_context?.effective_permissions]);

  const canManageRoles = effectivePermissions.has("roles.manage");
  const canAssignRoles = effectivePermissions.has("roles.assign");

  // Tab State
  const [activeTab, setActiveTab] = useState<WorkspaceTab>("roles");

  // ---------------------------------------------------------------------------
  // Roles Tab State
  // ---------------------------------------------------------------------------
  const [roles, setRoles] = useState<readonly RoleItem[]>([]);
  const [rolesCount, setRolesCount] = useState<number>(0);
  const [rolesPage, setRolesPage] = useState<number>(1);
  const [isRolesLoading, setIsRolesLoading] = useState<boolean>(true);
  const [rolesError, setRolesError] = useState<string | null>(null);
  const [rolesErrorCode, setRolesErrorCode] = useState<string | null>(null);

  // ---------------------------------------------------------------------------
  // Administrative Assignments Tab State
  // ---------------------------------------------------------------------------
  const [assignments, setAssignments] = useState<readonly AdministrativeMembershipItem[]>([]);
  const [assignmentsCount, setAssignmentsCount] = useState<number>(0);
  const [assignmentsPage, setAssignmentsPage] = useState<number>(1);
  const [statusFilter, setStatusFilter] = useState<string>("");
  const [isAssignmentsLoading, setIsAssignmentsLoading] = useState<boolean>(true);
  const [assignmentsError, setAssignmentsError] = useState<string | null>(null);
  const [assignmentsErrorCode, setAssignmentsErrorCode] = useState<string | null>(null);

  // ---------------------------------------------------------------------------
  // Modal States
  // ---------------------------------------------------------------------------
  const rolesTotalPages = Math.max(1, Math.ceil(rolesCount / 20));
  const assignmentsTotalPages = Math.max(1, Math.ceil(assignmentsCount / 20));

  const [isEditorOpen, setIsEditorOpen] = useState<boolean>(false);
  const [editorMode, setEditorMode] = useState<"create" | "edit" | "view">("create");
  const [selectedRole, setSelectedRole] = useState<RoleItem | null>(null);

  const [isRetireOpen, setIsRetireOpen] = useState<boolean>(false);
  const [roleToRetire, setRoleToRetire] = useState<RoleItem | null>(null);

  const [isAssignOpen, setIsAssignOpen] = useState<boolean>(false);
  const [targetMembership, setTargetMembership] = useState<AdministrativeMembershipItem | null>(null);

  const triggerRef = useRef<HTMLElement | null>(null);

  // ---------------------------------------------------------------------------
  // Data Fetching
  // ---------------------------------------------------------------------------
  const fetchRoles = useCallback(async () => {
    setIsRolesLoading(true);
    setRolesError(null);
    setRolesErrorCode(null);
    try {
      const res = await rolesApi.listRoles({ page: rolesPage, page_size: 20 });
      setRoles(res.results);
      setRolesCount(res.count);
    } catch (err) {
      if (err instanceof ApiError) {
        const d = err.data as { code?: string; detail?: string } | undefined;
        setRolesErrorCode(d?.code || `HTTP_${err.status}`);
        setRolesError(d?.detail || err.message || "Failed to load roles.");
      } else {
        setRolesError("An unexpected error occurred while loading roles.");
      }
    } finally {
      setIsRolesLoading(false);
    }
  }, [rolesPage]);

  const fetchAssignments = useCallback(async () => {
    setIsAssignmentsLoading(true);
    setAssignmentsError(null);
    setAssignmentsErrorCode(null);
    try {
      const res = await rolesApi.listAdminMemberships({
        page: assignmentsPage,
        page_size: 20,
        status: statusFilter || undefined,
      });
      setAssignments(res.results);
      setAssignmentsCount(res.count);
    } catch (err) {
      if (err instanceof ApiError) {
        const d = err.data as { code?: string; detail?: string } | undefined;
        setAssignmentsErrorCode(d?.code || `HTTP_${err.status}`);
        setAssignmentsError(d?.detail || err.message || "Failed to load administrative memberships.");
      } else {
        setAssignmentsError("An unexpected error occurred while loading assignments.");
      }
    } finally {
      setIsAssignmentsLoading(false);
    }
  }, [assignmentsPage, statusFilter]);

  useEffect(() => {
    if (activeTab === "roles") {
      void fetchRoles();
    } else {
      void fetchAssignments();
    }
  }, [activeTab, fetchRoles, fetchAssignments]);

  // ---------------------------------------------------------------------------
  // Action Handlers
  // ---------------------------------------------------------------------------
  const handleOpenCreateRole = (e: React.MouseEvent<HTMLElement>) => {
    triggerRef.current = e.currentTarget;
    setEditorMode("create");
    setSelectedRole(null);
    setIsEditorOpen(true);
  };

  const handleOpenViewRole = (r: RoleItem, e: React.MouseEvent<HTMLElement>) => {
    triggerRef.current = e.currentTarget;
    setEditorMode("view");
    setSelectedRole(r);
    setIsEditorOpen(true);
  };

  const handleOpenEditRole = (r: RoleItem, e: React.MouseEvent<HTMLElement>) => {
    triggerRef.current = e.currentTarget;
    setEditorMode("edit");
    setSelectedRole(r);
    setIsEditorOpen(true);
  };

  const handleOpenRetireRole = (r: RoleItem, e: React.MouseEvent<HTMLElement>) => {
    triggerRef.current = e.currentTarget;
    setRoleToRetire(r);
    setIsRetireOpen(true);
  };

  const handleOpenAssignModal = (m: AdministrativeMembershipItem, e: React.MouseEvent<HTMLElement>) => {
    triggerRef.current = e.currentTarget;
    setTargetMembership(m);
    setIsAssignOpen(true);
  };

  const handleRoleSaved = () => {
    void fetchRoles();
  };

  const handleRoleRetired = () => {
    void fetchRoles();
  };

  const handleAssignmentUpdated = () => {
    void fetchAssignments();
    void fetchRoles(); // Refresh assigned_members_count
  };

  return (
    <AppShell>
      <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem", minWidth: 0 }}>
        {/* Header Card */}
        <div
          style={{
            background: "var(--glass-surface-elevated)",
            border: "1px solid var(--border-glass)",
            borderRadius: "14px",
            padding: "1.5rem",
            boxShadow: "var(--shadow-sm)",
            display: "flex",
            justifyContent: "space-between",
            alignItems: "flex-start",
            flexWrap: "wrap",
            gap: "1rem",
          }}
        >
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.35rem" }}>
              <ShieldCheckIcon size={22} style={{ color: "var(--brand-primary)" }} />
              <h1 style={{ margin: 0, fontSize: "1.375rem", fontWeight: 700, color: "var(--text-primary)" }}>
                Roles & Permissions
              </h1>
            </div>
            <p style={{ margin: 0, fontSize: "0.875rem", color: "var(--text-secondary)", lineHeight: 1.5 }}>
              Manage administrative roles and fine-grained permissions for{" "}
              <strong style={{ color: "var(--text-primary)" }}>
                {organization?.name || "Active Tenant Organization"}
              </strong>
              .
            </p>
          </div>

          {canManageRoles && (
            <button
              type="button"
              className="btn btn-primary"
              onClick={handleOpenCreateRole}
              style={{ display: "inline-flex", alignItems: "center", gap: "0.4rem" }}
            >
              <PlusIcon size={16} />
              <span>Create Role</span>
            </button>
          )}
        </div>

        {/* Tab Navigation Bar */}
        <div
          role="tablist"
          style={{
            display: "flex",
            alignItems: "center",
            gap: "0.5rem",
            borderBottom: "1px solid var(--border-subtle)",
            paddingBottom: "0.5rem",
          }}
        >
          <button
            type="button"
            role="tab"
            aria-selected={activeTab === "roles"}
            aria-controls="panel-roles"
            id="tab-roles"
            onClick={() => setActiveTab("roles")}
            className={`org-tab-btn ${activeTab === "roles" ? "active" : ""}`}
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: "0.45rem",
              padding: "0.55rem 1rem",
              borderRadius: "8px",
              fontSize: "0.875rem",
              fontWeight: activeTab === "roles" ? 600 : 500,
              color: activeTab === "roles" ? "var(--brand-primary)" : "var(--text-secondary)",
              background: activeTab === "roles" ? "var(--brand-primary-light)" : "transparent",
              border: `1px solid ${activeTab === "roles" ? "var(--border-glass)" : "transparent"}`,
              cursor: "pointer",
            }}
          >
            <ShieldCheckIcon size={16} />
            <span>Roles</span>
            {rolesCount > 0 && (
              <span
                style={{
                  fontSize: "0.75rem",
                  padding: "0.1rem 0.45rem",
                  borderRadius: "9999px",
                  background: "rgba(0, 0, 0, 0.2)",
                  color: "var(--text-secondary)",
                }}
              >
                {rolesCount}
              </span>
            )}
          </button>

          <button
            type="button"
            role="tab"
            aria-selected={activeTab === "assignments"}
            aria-controls="panel-assignments"
            id="tab-assignments"
            onClick={() => setActiveTab("assignments")}
            className={`org-tab-btn ${activeTab === "assignments" ? "active" : ""}`}
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: "0.45rem",
              padding: "0.55rem 1rem",
              borderRadius: "8px",
              fontSize: "0.875rem",
              fontWeight: activeTab === "assignments" ? 600 : 500,
              color: activeTab === "assignments" ? "var(--brand-primary)" : "var(--text-secondary)",
              background: activeTab === "assignments" ? "var(--brand-primary-light)" : "transparent",
              border: `1px solid ${activeTab === "assignments" ? "var(--border-glass)" : "transparent"}`,
              cursor: "pointer",
            }}
          >
            <UserIcon size={16} />
            <span>Administrative Assignments</span>
            {assignmentsCount > 0 && (
              <span
                style={{
                  fontSize: "0.75rem",
                  padding: "0.1rem 0.45rem",
                  borderRadius: "9999px",
                  background: "rgba(0, 0, 0, 0.2)",
                  color: "var(--text-secondary)",
                }}
              >
                {assignmentsCount}
              </span>
            )}
          </button>
        </div>

        {/* =================================================================== */}
        {/* TAB 1: Roles List */}
        {/* =================================================================== */}
        {activeTab === "roles" && (
          <div id="panel-roles" role="tabpanel" aria-labelledby="tab-roles">
            {rolesError && (
              <div
                role="alert"
                style={{
                  padding: "0.875rem 1.25rem",
                  borderRadius: "10px",
                  background: "var(--status-danger-bg)",
                  border: "1px solid var(--status-danger-border)",
                  color: "var(--status-danger)",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  marginBottom: "1rem",
                  fontSize: "0.875rem",
                }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                  <AlertCircleIcon size={18} />
                  <span>
                    {rolesErrorCode ? `[${rolesErrorCode}] ` : ""}
                    {rolesError}
                  </span>
                </div>
                <button
                  type="button"
                  className="btn btn-secondary btn-sm"
                  onClick={fetchRoles}
                  style={{ display: "inline-flex", alignItems: "center", gap: "0.3rem" }}
                >
                  <RotateCcwIcon size={14} />
                  <span>Retry</span>
                </button>
              </div>
            )}

            {isRolesLoading ? (
              <div
                style={{
                  padding: "3rem",
                  textAlign: "center",
                  color: "var(--text-secondary)",
                  background: "var(--glass-surface-elevated)",
                  borderRadius: "12px",
                  border: "1px solid var(--border-glass)",
                }}
              >
                Loading organization roles...
              </div>
            ) : roles.length === 0 ? (
              <div
                style={{
                  padding: "3rem 1.5rem",
                  textAlign: "center",
                  color: "var(--text-secondary)",
                  background: "var(--glass-surface-elevated)",
                  borderRadius: "12px",
                  border: "1px solid var(--border-glass)",
                }}
              >
                <ShieldCheckIcon size={36} style={{ color: "var(--text-muted)", marginBottom: "0.5rem" }} />
                <h3 style={{ margin: "0 0 0.5rem 0", color: "var(--text-primary)", fontSize: "1rem" }}>
                  No Roles Found
                </h3>
                <p style={{ margin: 0, fontSize: "0.875rem" }}>
                  No roles match the current organization criteria.
                </p>
              </div>
            ) : (
              <>
                {/* Desktop Roles Table */}
                <div className="desktop-table-container">
                  <table
                    className="data-table"
                    style={{
                      width: "100%",
                      borderCollapse: "separate",
                      borderSpacing: 0,
                      background: "var(--glass-surface-elevated)",
                      borderRadius: "12px",
                      border: "1px solid var(--border-glass)",
                      overflow: "hidden",
                    }}
                  >
                    <thead>
                      <tr style={{ background: "rgba(0, 0, 0, 0.2)", textAlign: "left" }}>
                        <th style={{ padding: "0.85rem 1rem", fontSize: "0.75rem", fontWeight: 700, color: "var(--text-secondary)", textTransform: "uppercase" }}>
                          Role
                        </th>
                        <th style={{ padding: "0.85rem 1rem", fontSize: "0.75rem", fontWeight: 700, color: "var(--text-secondary)", textTransform: "uppercase" }}>
                          Type
                        </th>
                        <th style={{ padding: "0.85rem 1rem", fontSize: "0.75rem", fontWeight: 700, color: "var(--text-secondary)", textTransform: "uppercase" }}>
                          Status
                        </th>
                        <th style={{ padding: "0.85rem 1rem", fontSize: "0.75rem", fontWeight: 700, color: "var(--text-secondary)", textTransform: "uppercase" }}>
                          Permissions
                        </th>
                        <th style={{ padding: "0.85rem 1rem", fontSize: "0.75rem", fontWeight: 700, color: "var(--text-secondary)", textTransform: "uppercase", textAlign: "center" }}>
                          Assigned Members
                        </th>
                        <th style={{ padding: "0.85rem 1rem", fontSize: "0.75rem", fontWeight: 700, color: "var(--text-secondary)", textTransform: "uppercase" }}>
                          Created At
                        </th>
                        <th style={{ padding: "0.85rem 1rem", fontSize: "0.75rem", fontWeight: 700, color: "var(--text-secondary)", textTransform: "uppercase", textAlign: "center" }}>
                          Actions
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {roles.map((r, idx) => (
                        <tr
                          key={r.id}
                          style={{
                            borderTop: idx > 0 ? "1px solid var(--border-subtle)" : undefined,
                            transition: "background 0.15s ease",
                          }}
                        >
                          {/* Role Name and Code */}
                          <td style={{ padding: "0.85rem 1rem", verticalAlign: "middle" }}>
                            <div style={{ display: "flex", flexDirection: "column" }}>
                              <span style={{ fontWeight: 600, color: "var(--text-primary)", fontSize: "0.875rem" }}>
                                {r.name}
                              </span>
                              <span style={{ fontSize: "0.75rem", color: "var(--text-muted)", fontFamily: "var(--font-code)" }}>
                                {r.code}
                              </span>
                            </div>
                          </td>

                          {/* Type */}
                          <td style={{ padding: "0.85rem 1rem", verticalAlign: "middle" }}>
                            <span
                              style={{
                                fontSize: "0.75rem",
                                fontWeight: 600,
                                padding: "0.15rem 0.5rem",
                                borderRadius: "6px",
                                background: r.is_system_role
                                  ? "rgba(99, 102, 241, 0.12)"
                                  : "var(--glass-surface)",
                                color: r.is_system_role
                                  ? "rgb(99, 102, 241)"
                                  : "var(--text-secondary)",
                                border: `1px solid ${
                                  r.is_system_role
                                    ? "rgba(99, 102, 241, 0.25)"
                                    : "var(--border-subtle)"
                                }`,
                              }}
                            >
                              {r.is_system_role ? "System Role" : "Custom"}
                            </span>
                          </td>

                          {/* Status */}
                          <td style={{ padding: "0.85rem 1rem", verticalAlign: "middle" }}>
                            <span
                              style={{
                                fontSize: "0.75rem",
                                fontWeight: 600,
                                padding: "0.15rem 0.5rem",
                                borderRadius: "9999px",
                                textTransform: "capitalize",
                                background:
                                  r.status === "active"
                                    ? "var(--status-success-bg)"
                                    : "var(--status-neutral-bg)",
                                color:
                                  r.status === "active"
                                    ? "var(--status-success)"
                                    : "var(--text-muted)",
                                border: `1px solid ${
                                  r.status === "active"
                                    ? "var(--status-success-border)"
                                    : "var(--status-neutral-border)"
                                }`,
                              }}
                            >
                              {r.status}
                            </span>
                          </td>

                          {/* Permission Chips */}
                          <td style={{ padding: "0.85rem 1rem", verticalAlign: "middle", maxWidth: "320px" }}>
                            <div style={{ display: "flex", flexWrap: "wrap", gap: "0.3rem" }}>
                              {r.permission_keys.length === 0 ? (
                                <span style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
                                  No permissions
                                </span>
                              ) : (
                                r.permission_keys.map((pk) => (
                                  <span
                                    key={pk}
                                    style={{
                                      fontSize: "0.6875rem",
                                      padding: "0.1rem 0.4rem",
                                      borderRadius: "4px",
                                      background: "rgba(0, 0, 0, 0.2)",
                                      color: "var(--text-secondary)",
                                      border: "1px solid var(--border-subtle)",
                                      fontFamily: "var(--font-code)",
                                    }}
                                  >
                                    {pk}
                                  </span>
                                ))
                              )}
                            </div>
                          </td>

                          {/* Assigned Members */}
                          <td style={{ padding: "0.85rem 1rem", verticalAlign: "middle", textAlign: "center" }}>
                            <span
                              style={{
                                fontSize: "0.8125rem",
                                fontWeight: 600,
                                color: "var(--text-primary)",
                                padding: "0.2rem 0.55rem",
                                borderRadius: "6px",
                                background: "rgba(0, 0, 0, 0.15)",
                              }}
                            >
                              {r.assigned_members_count}
                            </span>
                          </td>

                          {/* Created At */}
                          <td style={{ padding: "0.85rem 1rem", verticalAlign: "middle", fontSize: "0.8125rem", color: "var(--text-secondary)", whiteSpace: "nowrap" }}>
                            {formatDateTime(r.created_at)}
                          </td>

                          {/* Actions */}
                          <td style={{ padding: "0.85rem 1rem", verticalAlign: "middle", textAlign: "center" }}>
                            <div style={{ display: "inline-flex", alignItems: "center", gap: "0.4rem", justifyContent: "center" }}>
                              <button
                                type="button"
                                className="btn btn-secondary btn-sm"
                                onClick={(e) => handleOpenViewRole(r, e)}
                                title="View complete role details"
                              >
                                View
                              </button>
                              {canManageRoles && !r.is_system_role && r.status === "active" && (
                                <>
                                  <button
                                    type="button"
                                    className="btn btn-secondary btn-sm"
                                    onClick={(e) => handleOpenEditRole(r, e)}
                                    title="Edit role metadata and permissions"
                                  >
                                    Edit
                                  </button>
                                  <button
                                    type="button"
                                    className="btn btn-secondary btn-sm"
                                    onClick={(e) => handleOpenRetireRole(r, e)}
                                    title="Retire unused custom role"
                                    style={{ color: "var(--status-danger)" }}
                                  >
                                    Retire
                                  </button>
                                </>
                              )}
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>

                {/* Mobile Roles Cards (< 768px) */}
                <div className="mobile-cards-container">
                  {roles.map((r) => (
                    <div
                      key={r.id}
                      style={{
                        background: "var(--glass-surface-elevated)",
                        border: "1px solid var(--border-glass)",
                        borderRadius: "12px",
                        padding: "1rem",
                        display: "flex",
                        flexDirection: "column",
                        gap: "0.75rem",
                        minWidth: 0,
                        overflow: "hidden",
                      }}
                    >
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: "0.5rem", flexWrap: "wrap" }}>
                        <div style={{ minWidth: 0, flex: "1 1 140px", wordBreak: "break-word", overflowWrap: "anywhere" }}>
                          <h3 style={{ margin: "0 0 0.15rem 0", fontSize: "1rem", fontWeight: 700, color: "var(--text-primary)", wordBreak: "break-word", overflowWrap: "anywhere" }}>
                            {r.name}
                          </h3>
                          <span style={{ fontSize: "0.75rem", color: "var(--text-muted)", fontFamily: "var(--font-code)", wordBreak: "break-all", overflowWrap: "anywhere", display: "inline-block" }}>
                            {r.code}
                          </span>
                        </div>
                        <div style={{ display: "flex", gap: "0.35rem", flexWrap: "wrap", flexShrink: 0 }}>
                          <span
                            style={{
                              fontSize: "0.6875rem",
                              fontWeight: 600,
                              padding: "0.15rem 0.45rem",
                              borderRadius: "4px",
                              background: r.is_system_role ? "rgba(99, 102, 241, 0.15)" : "var(--glass-surface)",
                              color: r.is_system_role ? "rgb(99, 102, 241)" : "var(--text-secondary)",
                              whiteSpace: "nowrap",
                            }}
                          >
                            {r.is_system_role ? "System" : "Custom"}
                          </span>
                          <span
                            style={{
                              fontSize: "0.6875rem",
                              fontWeight: 600,
                              padding: "0.15rem 0.45rem",
                              borderRadius: "9999px",
                              background: r.status === "active" ? "var(--status-success-bg)" : "var(--status-neutral-bg)",
                              color: r.status === "active" ? "var(--status-success)" : "var(--text-muted)",
                              whiteSpace: "nowrap",
                            }}
                          >
                            {r.status}
                          </span>
                        </div>
                      </div>

                      {r.description && (
                        <p style={{ margin: 0, fontSize: "0.8125rem", color: "var(--text-secondary)", lineHeight: 1.4, wordBreak: "break-word", overflowWrap: "anywhere" }}>
                          {r.description}
                        </p>
                      )}

                      {/* Permissions */}
                      <div>
                        <span style={{ fontSize: "0.75rem", color: "var(--text-muted)", display: "block", marginBottom: "0.25rem" }}>
                          Permissions:
                        </span>
                        <div style={{ display: "flex", flexWrap: "wrap", gap: "0.25rem" }}>
                          {r.permission_keys.map((pk) => (
                            <span
                              key={pk}
                              style={{
                                fontSize: "0.6875rem",
                                padding: "0.1rem 0.35rem",
                                borderRadius: "4px",
                                background: "rgba(0, 0, 0, 0.2)",
                                color: "var(--text-secondary)",
                                fontFamily: "var(--font-code)",
                                wordBreak: "break-all",
                                overflowWrap: "anywhere",
                              }}
                            >
                              {pk}
                            </span>
                          ))}
                        </div>
                      </div>

                      {/* Explicit Mobile Metadata Groups */}
                      <div
                        style={{
                          display: "flex",
                          flexDirection: "column",
                          gap: "0.4rem",
                          fontSize: "0.75rem",
                          color: "var(--text-muted)",
                          borderTop: "1px solid var(--border-subtle)",
                          paddingTop: "0.6rem",
                        }}
                      >
                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: "0.5rem", flexWrap: "wrap" }}>
                          <span>Assigned Members:</span>
                          <strong style={{ color: "var(--text-primary)" }}>{r.assigned_members_count}</strong>
                        </div>
                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: "0.5rem", flexWrap: "wrap" }}>
                          <span>Created At:</span>
                          <span style={{ color: "var(--text-secondary)" }}>{formatDateTime(r.created_at)}</span>
                        </div>
                      </div>

                      {/* Actions */}
                      <div style={{ display: "flex", gap: "0.5rem", marginTop: "0.25rem", flexWrap: "wrap" }}>
                        <button
                          type="button"
                          className="btn btn-secondary btn-sm"
                          onClick={(e) => handleOpenViewRole(r, e)}
                          style={{ flex: "1 1 70px" }}
                        >
                          View
                        </button>
                        {canManageRoles && !r.is_system_role && r.status === "active" && (
                          <>
                            <button
                              type="button"
                              className="btn btn-secondary btn-sm"
                              onClick={(e) => handleOpenEditRole(r, e)}
                              style={{ flex: "1 1 70px" }}
                            >
                              Edit
                            </button>
                            <button
                              type="button"
                              className="btn btn-secondary btn-sm"
                              onClick={(e) => handleOpenRetireRole(r, e)}
                              style={{ flex: "1 1 70px", color: "var(--status-danger)" }}
                            >
                              Retire
                            </button>
                          </>
                        )}
                      </div>
                    </div>
                  ))}
                </div>

                {/* Roles Pagination */}
                {rolesTotalPages > 1 && (
                  <div
                    style={{
                      display: "flex",
                      justifyContent: "space-between",
                      alignItems: "center",
                      marginTop: "1.25rem",
                      padding: "0.75rem 0",
                      flexWrap: "wrap",
                      gap: "0.75rem",
                    }}
                  >
                    <span style={{ fontSize: "0.8125rem", color: "var(--text-secondary)" }}>
                      Page {rolesPage} of {rolesTotalPages} ({rolesCount} total roles)
                    </span>
                    <div style={{ display: "flex", gap: "0.5rem" }}>
                      <button
                        type="button"
                        className="btn btn-secondary btn-sm"
                        onClick={() => setRolesPage((p) => Math.max(1, p - 1))}
                        disabled={rolesPage <= 1 || isRolesLoading}
                        style={{ display: "inline-flex", alignItems: "center", gap: "0.25rem" }}
                      >
                        <ChevronLeftIcon size={14} /> <span>Previous</span>
                      </button>
                      <button
                        type="button"
                        className="btn btn-secondary btn-sm"
                        onClick={() => setRolesPage((p) => Math.min(rolesTotalPages, p + 1))}
                        disabled={rolesPage >= rolesTotalPages || isRolesLoading}
                        style={{ display: "inline-flex", alignItems: "center", gap: "0.25rem" }}
                      >
                        <span>Next</span> <ChevronRightIcon size={14} />
                      </button>
                    </div>
                  </div>
                )}
              </>
            )}
          </div>
        )}

        {/* =================================================================== */}
        {/* TAB 2: Administrative Assignments List */}
        {/* =================================================================== */}
        {activeTab === "assignments" && (
          <div id="panel-assignments" role="tabpanel" aria-labelledby="tab-assignments">
            {/* Filter Toolbar */}
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                flexWrap: "wrap",
                gap: "0.75rem",
                marginBottom: "1rem",
              }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", flexWrap: "wrap" }}>
                <div style={{ display: "flex", alignItems: "center", gap: "0.35rem" }}>
                  <FilterIcon size={16} style={{ color: "var(--text-muted)" }} />
                  <span style={{ fontSize: "0.8125rem", color: "var(--text-secondary)", fontWeight: 600 }}>
                    Status:
                  </span>
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: "0.4rem", flexWrap: "wrap" }}>
                  {(["", "active", "suspended", "ended"] as const).map((st) => (
                    <button
                      key={st}
                      type="button"
                      onClick={() => {
                        setStatusFilter(st);
                        setAssignmentsPage(1);
                      }}
                      style={{
                        padding: "0.35rem 0.65rem",
                        borderRadius: "6px",
                        fontSize: "0.75rem",
                        fontWeight: statusFilter === st ? 600 : 500,
                        background: statusFilter === st ? "var(--brand-primary-light)" : "var(--glass-surface)",
                        color: statusFilter === st ? "var(--brand-primary)" : "var(--text-secondary)",
                        border: `1px solid ${statusFilter === st ? "var(--border-glass)" : "var(--border-subtle)"}`,
                        cursor: "pointer",
                        textTransform: "capitalize",
                        flexShrink: 0,
                      }}
                    >
                      {st === "" ? "All" : st}
                    </button>
                  ))}
                </div>
              </div>
            </div>

            {assignmentsError && (
              <div
                role="alert"
                style={{
                  padding: "0.875rem 1.25rem",
                  borderRadius: "10px",
                  background: "var(--status-danger-bg)",
                  border: "1px solid var(--status-danger-border)",
                  color: "var(--status-danger)",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  marginBottom: "1rem",
                  fontSize: "0.875rem",
                }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                  <AlertCircleIcon size={18} />
                  <span>
                    {assignmentsErrorCode ? `[${assignmentsErrorCode}] ` : ""}
                    {assignmentsError}
                  </span>
                </div>
                <button
                  type="button"
                  className="btn btn-secondary btn-sm"
                  onClick={fetchAssignments}
                  style={{ display: "inline-flex", alignItems: "center", gap: "0.3rem" }}
                >
                  <RotateCcwIcon size={14} />
                  <span>Retry</span>
                </button>
              </div>
            )}

            {isAssignmentsLoading ? (
              <div
                style={{
                  padding: "3rem",
                  textAlign: "center",
                  color: "var(--text-secondary)",
                  background: "var(--glass-surface-elevated)",
                  borderRadius: "12px",
                  border: "1px solid var(--border-glass)",
                }}
              >
                Loading administrative memberships...
              </div>
            ) : assignments.length === 0 ? (
              <div
                style={{
                  padding: "3rem 1.5rem",
                  textAlign: "center",
                  color: "var(--text-secondary)",
                  background: "var(--glass-surface-elevated)",
                  borderRadius: "12px",
                  border: "1px solid var(--border-glass)",
                }}
              >
                <UserIcon size={36} style={{ color: "var(--text-muted)", marginBottom: "0.5rem" }} />
                <h3 style={{ margin: "0 0 0.5rem 0", color: "var(--text-primary)", fontSize: "1rem" }}>
                  No Administrators Found
                </h3>
                <p style={{ margin: 0, fontSize: "0.875rem" }}>
                  No Tenant Admin memberships match the selected filter.
                </p>
              </div>
            ) : (
              <>
                {/* Desktop Assignments Table */}
                <div className="desktop-table-container">
                  <table
                    className="data-table"
                    style={{
                      width: "100%",
                      borderCollapse: "separate",
                      borderSpacing: 0,
                      background: "var(--glass-surface-elevated)",
                      borderRadius: "12px",
                      border: "1px solid var(--border-glass)",
                      overflow: "hidden",
                    }}
                  >
                    <thead>
                      <tr style={{ background: "rgba(0, 0, 0, 0.2)", textAlign: "left" }}>
                        <th style={{ padding: "0.85rem 1rem", fontSize: "0.75rem", fontWeight: 700, color: "var(--text-secondary)", textTransform: "uppercase" }}>
                          Administrator
                        </th>
                        <th style={{ padding: "0.85rem 1rem", fontSize: "0.75rem", fontWeight: 700, color: "var(--text-secondary)", textTransform: "uppercase" }}>
                          User Status
                        </th>
                        <th style={{ padding: "0.85rem 1rem", fontSize: "0.75rem", fontWeight: 700, color: "var(--text-secondary)", textTransform: "uppercase" }}>
                          Membership Status
                        </th>
                        <th style={{ padding: "0.85rem 1rem", fontSize: "0.75rem", fontWeight: 700, color: "var(--text-secondary)", textTransform: "uppercase" }}>
                          Assigned Role
                        </th>
                        <th style={{ padding: "0.85rem 1rem", fontSize: "0.75rem", fontWeight: 700, color: "var(--text-secondary)", textTransform: "uppercase" }}>
                          Joined At
                        </th>
                        <th style={{ padding: "0.85rem 1rem", fontSize: "0.75rem", fontWeight: 700, color: "var(--text-secondary)", textTransform: "uppercase", textAlign: "center" }}>
                          Actions
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {assignments.map((m, idx) => (
                        <tr
                          key={m.id}
                          style={{
                            borderTop: idx > 0 ? "1px solid var(--border-subtle)" : undefined,
                            transition: "background 0.15s ease",
                          }}
                        >
                          {/* Administrator Full Name & Email */}
                          <td style={{ padding: "0.85rem 1rem", verticalAlign: "middle" }}>
                            <div style={{ display: "flex", flexDirection: "column" }}>
                              <span style={{ fontWeight: 600, color: "var(--text-primary)", fontSize: "0.875rem" }}>
                                {m.user.full_name}
                              </span>
                              <span style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
                                {m.user.email}
                              </span>
                            </div>
                          </td>

                          {/* User Status */}
                          <td style={{ padding: "0.85rem 1rem", verticalAlign: "middle" }}>
                            <span
                              style={{
                                fontSize: "0.75rem",
                                fontWeight: 600,
                                padding: "0.15rem 0.5rem",
                                borderRadius: "9999px",
                                textTransform: "capitalize",
                                background:
                                  m.user.status === "active"
                                    ? "var(--status-success-bg)"
                                    : "var(--status-danger-bg)",
                                color:
                                  m.user.status === "active"
                                    ? "var(--status-success)"
                                    : "var(--status-danger)",
                                border: `1px solid ${
                                  m.user.status === "active"
                                    ? "var(--status-success-border)"
                                    : "var(--status-danger-border)"
                                }`,
                              }}
                            >
                              {m.user.status}
                            </span>
                          </td>

                          {/* Membership Status */}
                          <td style={{ padding: "0.85rem 1rem", verticalAlign: "middle" }}>
                            <span
                              style={{
                                fontSize: "0.75rem",
                                fontWeight: 600,
                                padding: "0.15rem 0.5rem",
                                borderRadius: "9999px",
                                textTransform: "capitalize",
                                background:
                                  m.status === "active"
                                    ? "var(--status-success-bg)"
                                    : m.status === "suspended"
                                    ? "var(--status-warning-bg)"
                                    : "var(--status-neutral-bg)",
                                color:
                                  m.status === "active"
                                    ? "var(--status-success)"
                                    : m.status === "suspended"
                                    ? "var(--status-warning)"
                                    : "var(--text-muted)",
                                border: `1px solid ${
                                  m.status === "active"
                                    ? "var(--status-success-border)"
                                    : m.status === "suspended"
                                    ? "var(--status-warning-border)"
                                    : "var(--status-neutral-border)"
                                }`,
                              }}
                            >
                              {m.status}
                            </span>
                          </td>

                          {/* Assigned Role */}
                          <td style={{ padding: "0.85rem 1rem", verticalAlign: "middle" }}>
                            <div style={{ display: "flex", alignItems: "center", gap: "0.45rem" }}>
                              <span style={{ fontWeight: 600, color: "var(--text-primary)", fontSize: "0.875rem" }}>
                                {m.role?.name || "Tenant Administrator"}
                              </span>
                              <span
                                style={{
                                  fontSize: "0.6875rem",
                                  fontWeight: 600,
                                  padding: "0.1rem 0.4rem",
                                  borderRadius: "4px",
                                  background: m.role?.is_system_role
                                    ? "rgba(99, 102, 241, 0.12)"
                                    : "var(--glass-surface)",
                                  color: m.role?.is_system_role
                                    ? "rgb(99, 102, 241)"
                                    : "var(--text-secondary)",
                                  border: `1px solid ${
                                    m.role?.is_system_role
                                      ? "rgba(99, 102, 241, 0.25)"
                                      : "var(--border-subtle)"
                                  }`,
                                }}
                              >
                                {m.role?.is_system_role ? "System" : "Custom"}
                              </span>
                            </div>
                          </td>

                          {/* Joined At */}
                          <td style={{ padding: "0.85rem 1rem", verticalAlign: "middle", fontSize: "0.8125rem", color: "var(--text-secondary)", whiteSpace: "nowrap" }}>
                            {formatDateTime(m.joined_at)}
                          </td>

                          {/* Actions */}
                          <td style={{ padding: "0.85rem 1rem", verticalAlign: "middle", textAlign: "center" }}>
                            {canAssignRoles ? (
                              <button
                                type="button"
                                className="btn btn-secondary btn-sm"
                                onClick={(e) => handleOpenAssignModal(m, e)}
                                title="Reassign administrative role"
                              >
                                Change Role
                              </button>
                            ) : (
                              <span style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
                                —
                              </span>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>

                {/* Mobile Assignments Cards (< 768px) */}
                <div className="mobile-cards-container">
                  {assignments.map((m) => (
                    <div
                      key={m.id}
                      style={{
                        background: "var(--glass-surface-elevated)",
                        border: "1px solid var(--border-glass)",
                        borderRadius: "12px",
                        padding: "1rem",
                        display: "flex",
                        flexDirection: "column",
                        gap: "0.75rem",
                        minWidth: 0,
                        overflow: "hidden",
                      }}
                    >
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: "0.5rem", flexWrap: "wrap" }}>
                        <div style={{ minWidth: 0, flex: "1 1 140px", wordBreak: "break-word", overflowWrap: "anywhere" }}>
                          <h3 style={{ margin: "0 0 0.15rem 0", fontSize: "1rem", fontWeight: 700, color: "var(--text-primary)", wordBreak: "break-word", overflowWrap: "anywhere" }}>
                            {m.user.full_name}
                          </h3>
                          <span style={{ fontSize: "0.75rem", color: "var(--text-muted)", wordBreak: "break-all", overflowWrap: "anywhere", display: "inline-block" }}>
                            {m.user.email}
                          </span>
                        </div>
                        <div style={{ display: "flex", gap: "0.35rem", flexWrap: "wrap", flexShrink: 0 }}>
                          <span
                            style={{
                              fontSize: "0.6875rem",
                              fontWeight: 600,
                              padding: "0.1rem 0.4rem",
                              borderRadius: "9999px",
                              background: m.status === "active" ? "var(--status-success-bg)" : m.status === "suspended" ? "var(--status-warning-bg)" : "var(--status-neutral-bg)",
                              color: m.status === "active" ? "var(--status-success)" : m.status === "suspended" ? "var(--status-warning)" : "var(--text-muted)",
                              border: `1px solid ${m.status === "active" ? "var(--status-success-border)" : m.status === "suspended" ? "var(--status-warning-border)" : "var(--status-neutral-border)"}`,
                              whiteSpace: "nowrap",
                            }}
                          >
                            Member: {m.status}
                          </span>
                          <span
                            style={{
                              fontSize: "0.6875rem",
                              fontWeight: 600,
                              padding: "0.1rem 0.4rem",
                              borderRadius: "9999px",
                              background: m.user.status === "active" ? "var(--status-success-bg)" : "var(--status-danger-bg)",
                              color: m.user.status === "active" ? "var(--status-success)" : "var(--status-danger)",
                              border: `1px solid ${m.user.status === "active" ? "var(--status-success-border)" : "var(--status-danger-border)"}`,
                              whiteSpace: "nowrap",
                            }}
                          >
                            User: {m.user.status}
                          </span>
                        </div>
                      </div>

                      <div
                        style={{
                          display: "flex",
                          justifyContent: "space-between",
                          alignItems: "center",
                          padding: "0.6rem 0.75rem",
                          borderRadius: "8px",
                          background: "rgba(0, 0, 0, 0.15)",
                          border: "1px solid var(--border-subtle)",
                          flexWrap: "wrap",
                          gap: "0.35rem",
                        }}
                      >
                        <span style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>Assigned Role:</span>
                        <div style={{ display: "flex", alignItems: "center", gap: "0.35rem", flexWrap: "wrap" }}>
                          <span style={{ fontSize: "0.8125rem", fontWeight: 600, color: "var(--text-primary)", wordBreak: "break-word" }}>
                            {m.role?.name || "Tenant Administrator"}
                          </span>
                          <span
                            style={{
                              fontSize: "0.6875rem",
                              padding: "0.05rem 0.35rem",
                              borderRadius: "3px",
                              background: m.role?.is_system_role ? "rgba(99, 102, 241, 0.15)" : "var(--glass-surface)",
                              color: m.role?.is_system_role ? "rgb(99, 102, 241)" : "var(--text-secondary)",
                              whiteSpace: "nowrap",
                            }}
                          >
                            {m.role?.is_system_role ? "System" : "Custom"}
                          </span>
                        </div>
                      </div>

                      <div style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
                        Joined: {formatDateTime(m.joined_at)}
                      </div>

                      {canAssignRoles && (
                        <button
                          type="button"
                          className="btn btn-secondary btn-sm"
                          onClick={(e) => handleOpenAssignModal(m, e)}
                          style={{ width: "100%", marginTop: "0.25rem" }}
                        >
                          Change Role
                        </button>
                      )}
                    </div>
                  ))}
                </div>

                {/* Assignments Pagination */}
                {assignmentsTotalPages > 1 && (
                  <div
                    style={{
                      display: "flex",
                      justifyContent: "space-between",
                      alignItems: "center",
                      marginTop: "1.25rem",
                      padding: "0.75rem 0",
                      flexWrap: "wrap",
                      gap: "0.75rem",
                    }}
                  >
                    <span style={{ fontSize: "0.8125rem", color: "var(--text-secondary)" }}>
                      Page {assignmentsPage} of {assignmentsTotalPages} ({assignmentsCount} total assignments)
                    </span>
                    <div style={{ display: "flex", gap: "0.5rem" }}>
                      <button
                        type="button"
                        className="btn btn-secondary btn-sm"
                        onClick={() => setAssignmentsPage((p) => Math.max(1, p - 1))}
                        disabled={assignmentsPage <= 1 || isAssignmentsLoading}
                        style={{ display: "inline-flex", alignItems: "center", gap: "0.25rem" }}
                      >
                        <ChevronLeftIcon size={14} /> <span>Previous</span>
                      </button>
                      <button
                        type="button"
                        className="btn btn-secondary btn-sm"
                        onClick={() => setAssignmentsPage((p) => Math.min(assignmentsTotalPages, p + 1))}
                        disabled={assignmentsPage >= assignmentsTotalPages || isAssignmentsLoading}
                        style={{ display: "inline-flex", alignItems: "center", gap: "0.25rem" }}
                      >
                        <span>Next</span> <ChevronRightIcon size={14} />
                      </button>
                    </div>
                  </div>
                )}
              </>
            )}
          </div>
        )}
      </div>

      {/* Modals */}
      <RoleEditorModal
        isOpen={isEditorOpen}
        mode={editorMode}
        role={selectedRole}
        onClose={() => setIsEditorOpen(false)}
        onSuccess={handleRoleSaved}
        triggerRef={triggerRef}
      />

      <RetireRoleDialog
        isOpen={isRetireOpen}
        role={roleToRetire}
        onClose={() => setIsRetireOpen(false)}
        onSuccess={handleRoleRetired}
        triggerRef={triggerRef}
      />

      <AssignRoleModal
        isOpen={isAssignOpen}
        membership={targetMembership}
        onClose={() => setIsAssignOpen(false)}
        onSuccess={handleAssignmentUpdated}
        triggerRef={triggerRef}
      />

      {/* Responsive styles */}
      <style>{`
        .desktop-table-container {
          display: block;
          overflow-x: auto;
        }
        .mobile-cards-container {
          display: none;
          flex-direction: column;
          gap: 1rem;
        }
        @media (max-width: 768px) {
          .desktop-table-container {
            display: none;
          }
          .mobile-cards-container {
            display: flex;
          }
        }
      `}</style>
    </AppShell>
  );
};
