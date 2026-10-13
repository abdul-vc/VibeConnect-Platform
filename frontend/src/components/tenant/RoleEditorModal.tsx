/**
 * Role Editor Modal (Phase 2E Stage 6).
 *
 * Supports:
 * - Create mode (name, lowercase snake_case code, description, permissions)
 * - Edit mode (name, immutable code, description, permissions)
 * - Dynamic grantable permissions loaded from /api/v1/tenant/access-catalog/
 * - Non-escalation protection and permission dependency validation (manage/assign require view)
 * - Safe preservation of unchanged permissions outside current actor catalog
 * - Accessible focus trapping, Esc dismissal, internal body scroll, and API error presentation
 */

import React, { useCallback, useEffect, useId, useMemo, useRef, useState } from "react";
import { ApiError } from "../../api/client.ts";
import { rolesApi } from "../../api/roles.ts";
import type {
  AccessCatalogResponse,
  AccessPermissionItem,
  CreateRolePayload,
  RoleItem,
  UpdateRolePayload,
} from "../../api/types.ts";
import { formatDateTime } from "../../config/dateUtils.ts";
import { AlertCircleIcon, CloseIcon, ShieldCheckIcon } from "../Icons.tsx";
import { useDialogAccessibility } from "../plans/PlanModalShell.tsx";

interface RoleEditorModalProps {
  readonly isOpen: boolean;
  readonly mode: "create" | "edit" | "view";
  readonly role?: RoleItem | null;
  readonly onClose: () => void;
  readonly onSuccess?: (role: RoleItem) => void;
  readonly triggerRef?: React.RefObject<HTMLElement | null>;
}

const CODE_REGEX = /^[a-z0-9]+(?:_[a-z0-9]+)*$/;

export const RoleEditorModal: React.FC<RoleEditorModalProps> = ({
  isOpen,
  mode,
  role,
  onClose,
  onSuccess,
  triggerRef,
}) => {
  const baseId = useId();
  const nameInputRef = useRef<HTMLInputElement | null>(null);

  // Form & Detail State
  const [roleDetail, setRoleDetail] = useState<RoleItem | null>(role || null);
  const [name, setName] = useState<string>("");
  const [code, setCode] = useState<string>("");
  const [description, setDescription] = useState<string>("");
  const [selectedPermissions, setSelectedPermissions] = useState<Set<string>>(new Set());

  // Catalog & Async State
  const [catalog, setCatalog] = useState<AccessCatalogResponse | null>(null);
  const [isCatalogLoading, setIsCatalogLoading] = useState<boolean>(false);
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  const [errorDetail, setErrorDetail] = useState<string | null>(null);
  const [errorCode, setErrorCode] = useState<string | null>(null);
  const [validationError, setValidationError] = useState<string | null>(null);

  // Retain permissions existing on the role that might not be in actor's grantable catalog
  // (Preserved so metadata-only edits do not accidentally drop permissions)
  const [externalRolePermissions, setExternalRolePermissions] = useState<readonly string[]>([]);

  const { dialogRef } = useDialogAccessibility({
    isOpen,
    isSubmitting,
    onClose,
    triggerRef,
    initialFocusRef: nameInputRef,
  });

  // Fetch access catalog when modal opens
  const fetchCatalog = useCallback(async () => {
    setIsCatalogLoading(true);
    setErrorDetail(null);
    setErrorCode(null);
    try {
      const data = await rolesApi.getAccessCatalog();
      setCatalog(data);
    } catch (err) {
      if (err instanceof ApiError) {
        const d = err.data as { code?: string; detail?: string } | undefined;
        setErrorCode(d?.code || "CATALOG_ERROR");
        setErrorDetail(d?.detail || "Failed to load grantable access catalog.");
      } else {
        setErrorDetail("Network error loading permissions catalog.");
      }
    } finally {
      setIsCatalogLoading(false);
    }
  }, []);

  // Initialize or reset form state on open / role change
  useEffect(() => {
    if (isOpen) {
      void fetchCatalog();
      setErrorDetail(null);
      setErrorCode(null);
      setValidationError(null);

      if ((mode === "edit" || mode === "view") && role) {
        setRoleDetail(role);
        setName(role.name);
        setCode(role.code);
        setDescription(role.description || "");
        setSelectedPermissions(new Set(role.permission_keys));

        // Authoritative fresh fetch
        rolesApi
          .getRole(role.id)
          .then((fresh) => {
            setRoleDetail(fresh);
            setName(fresh.name);
            setCode(fresh.code);
            setDescription(fresh.description || "");
            setSelectedPermissions(new Set(fresh.permission_keys));
          })
          .catch(() => {
            // Keep passed-in role data if fetch fails
          });
      } else {
        setRoleDetail(null);
        setName("");
        setCode("");
        setDescription("");
        setSelectedPermissions(new Set());
        setExternalRolePermissions([]);
      }
    }
  }, [isOpen, mode, role, fetchCatalog]);

  // When catalog loads, identify any role permissions outside the actor's grantable catalog
  useEffect(() => {
    if (catalog && mode === "edit" && role) {
      const grantableKeys = new Set(catalog.permissions.map((p) => p.key));
      const outside = role.permission_keys.filter((k) => !grantableKeys.has(k));
      setExternalRolePermissions(outside);
    }
  }, [catalog, mode, role]);

  // Group catalog permissions by category
  const permissionsByCategory = useMemo(() => {
    if (!catalog) return {};
    const grouped: Record<string, AccessPermissionItem[]> = {};
    for (const perm of catalog.permissions) {
      const cat = perm.category || "General";
      if (!grouped[cat]) grouped[cat] = [];
      grouped[cat].push(perm);
    }
    return grouped;
  }, [catalog]);

  const handleTogglePermission = (permKey: string) => {
    setValidationError(null);
    setSelectedPermissions((prev) => {
      const next = new Set(prev);
      if (next.has(permKey)) {
        // User is attempting to deselect permKey
        if (permKey === "roles.view") {
          const hasDependent = next.has("roles.manage") || next.has("roles.assign");
          if (hasDependent) {
            setValidationError(
              "Cannot remove 'roles.view' while dependent permissions ('roles.manage' or 'roles.assign') are selected. Please deselect dependent permissions first."
            );
            return prev;
          }
        }
        next.delete(permKey);
      } else {
        // User is attempting to select permKey
        if (permKey === "roles.manage" || permKey === "roles.assign") {
          if (!next.has("roles.view")) {
            setValidationError(
              `Selecting '${permKey}' requires 'roles.view'. Please select 'View Roles & Permissions' first.`
            );
            return prev;
          }
        }
        next.add(permKey);
      }
      return next;
    });
  };

  const handleRemoveExternalPermission = (permKey: string) => {
    setSelectedPermissions((prev) => {
      const next = new Set(prev);
      next.delete(permKey);
      return next;
    });
    setExternalRolePermissions((prev) => prev.filter((k) => k !== permKey));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorDetail(null);
    setErrorCode(null);
    setValidationError(null);

    const trimmedName = name.trim();
    if (!trimmedName) {
      setValidationError("Role name is required.");
      return;
    }

    if (mode === "create") {
      const trimmedCode = code.trim();
      if (!trimmedCode) {
        setValidationError("Role code is required.");
        return;
      }
      if (!CODE_REGEX.test(trimmedCode)) {
        setValidationError(
          "Role code must be lowercase alphanumeric with single underscores between characters (e.g. audit_manager)."
        );
        return;
      }
    }

    // Validate permission dependencies against selected set
    if (selectedPermissions.has("roles.manage") && !selectedPermissions.has("roles.view")) {
      setValidationError("'roles.manage' requires 'roles.view' to be selected.");
      return;
    }
    if (selectedPermissions.has("roles.assign") && !selectedPermissions.has("roles.view")) {
      setValidationError("'roles.assign' requires 'roles.view' to be selected.");
      return;
    }

    setIsSubmitting(true);
    try {
      if (mode === "create") {
        const payload: CreateRolePayload = {
          name: trimmedName,
          code: code.trim(),
          description: description.trim() || undefined,
          permission_keys: Array.from(selectedPermissions),
        };
        const created = await rolesApi.createRole(payload);
        onSuccess?.(created);
        onClose();
      } else if (mode === "edit" && role) {
        // Detect if permissions actually changed
        const originalSet = new Set(role.permission_keys);
        const hasPermsChanged =
          originalSet.size !== selectedPermissions.size ||
          Array.from(selectedPermissions).some((p) => !originalSet.has(p));

        const payload: UpdateRolePayload = {
          name: trimmedName !== role.name ? trimmedName : undefined,
          description: description.trim() !== (role.description || "") ? description.trim() : undefined,
          permission_keys: hasPermsChanged ? Array.from(selectedPermissions) : undefined,
        };

        const updated = await rolesApi.updateRole(role.id, payload);
        onSuccess?.(updated);
        onClose();
      }
    } catch (err) {
      if (err instanceof ApiError) {
        const d = err.data as { code?: string; detail?: string } | undefined;
        setErrorCode(d?.code || `HTTP_${err.status}`);
        setErrorDetail(d?.detail || err.message || "Failed to save role.");
      } else {
        setErrorDetail("An unexpected error occurred while saving the role.");
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div
      className="modal-backdrop"
      role="presentation"
      style={{
        position: "fixed",
        inset: 0,
        backgroundColor: "rgba(0, 0, 0, 0.65)",
        backdropFilter: "blur(6px)",
        WebkitBackdropFilter: "blur(6px)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: "1rem",
        zIndex: 1000,
        overflowY: "auto",
      }}
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={`${baseId}-title`}
        aria-describedby={`${baseId}-desc`}
        className="glass-panel"
        style={{
          width: "100%",
          maxWidth: "600px",
          maxHeight: "90vh",
          display: "flex",
          flexDirection: "column",
          borderRadius: "14px",
          background: "var(--glass-surface-elevated)",
          border: "1px solid var(--border-glass)",
          boxShadow: "var(--shadow-lg)",
          overflow: "hidden",
        }}
      >
        {/* Header */}
        <div
          style={{
            padding: "1.25rem 1.5rem",
            borderBottom: "1px solid var(--border-subtle)",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
            <ShieldCheckIcon size={20} style={{ color: "var(--brand-primary)" }} />
            <h2
              id={`${baseId}-title`}
              style={{
                margin: 0,
                fontSize: "1.125rem",
                fontWeight: 700,
                color: "var(--text-primary)",
              }}
            >
              {mode === "create"
                ? "Create Administrative Role"
                : mode === "edit"
                ? "Edit Role"
                : "Role Details"}
            </h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            disabled={isSubmitting}
            aria-label="Close dialog"
            style={{
              background: "transparent",
              border: "none",
              color: "var(--text-secondary)",
              cursor: isSubmitting ? "not-allowed" : "pointer",
              padding: "0.25rem",
              borderRadius: "6px",
              display: "flex",
            }}
          >
            <CloseIcon size={18} />
          </button>
        </div>

        {/* Form Body - Scrollable */}
        <form
          id={`${baseId}-form`}
          onSubmit={handleSubmit}
          style={{
            display: "flex",
            flexDirection: "column",
            flex: 1,
            overflow: "hidden",
          }}
        >
          <div
            style={{
              padding: "1.25rem 1.5rem",
              overflowY: "auto",
              display: "flex",
              flexDirection: "column",
              gap: "1.25rem",
              flex: 1,
            }}
          >
            <p
              id={`${baseId}-desc`}
              style={{
                margin: 0,
                fontSize: "0.875rem",
                color: "var(--text-secondary)",
                lineHeight: 1.5,
              }}
            >
              {mode === "create"
                ? "Configure a custom administrative role for this organization. Permissions are limited to your current active authority."
                : mode === "edit"
                ? "Modify role metadata and capabilities. Code is permanent and cannot be altered."
                : "Authoritative details, capabilities, and lifecycle status for this administrative role."}
            </p>

            {/* View Mode Summary Metadata Grid */}
            {mode === "view" && (
              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "repeat(auto-fit, minmax(130px, 1fr))",
                  gap: "0.75rem",
                  padding: "0.85rem 1rem",
                  background: "rgba(0, 0, 0, 0.15)",
                  border: "1px solid var(--border-glass)",
                  borderRadius: "10px",
                }}
              >
                <div>
                  <span style={{ fontSize: "0.6875rem", color: "var(--text-muted)", display: "block" }}>Type</span>
                  <span
                    style={{
                      fontSize: "0.75rem",
                      fontWeight: 600,
                      color: roleDetail?.is_system_role ? "rgb(99, 102, 241)" : "var(--text-secondary)",
                    }}
                  >
                    {roleDetail?.is_system_role ? "System Role" : "Custom Role"}
                  </span>
                </div>
                <div>
                  <span style={{ fontSize: "0.6875rem", color: "var(--text-muted)", display: "block" }}>Status</span>
                  <span
                    style={{
                      fontSize: "0.75rem",
                      fontWeight: 600,
                      textTransform: "capitalize",
                      color: roleDetail?.status === "active" ? "var(--status-success)" : "var(--text-muted)",
                    }}
                  >
                    {roleDetail?.status ?? "active"}
                  </span>
                </div>
                <div>
                  <span style={{ fontSize: "0.6875rem", color: "var(--text-muted)", display: "block" }}>Assigned Members</span>
                  <span style={{ fontSize: "0.8125rem", fontWeight: 700, color: "var(--text-primary)" }}>
                    {roleDetail?.assigned_members_count ?? role?.assigned_members_count ?? 0}
                  </span>
                </div>
                <div>
                  <span style={{ fontSize: "0.6875rem", color: "var(--text-muted)", display: "block" }}>Created At</span>
                  <span style={{ fontSize: "0.75rem", color: "var(--text-secondary)", whiteSpace: "nowrap" }}>
                    {roleDetail?.created_at ? formatDateTime(roleDetail.created_at) : "—"}
                  </span>
                </div>
                <div>
                  <span style={{ fontSize: "0.6875rem", color: "var(--text-muted)", display: "block" }}>Updated At</span>
                  <span style={{ fontSize: "0.75rem", color: "var(--text-secondary)", whiteSpace: "nowrap" }}>
                    {roleDetail?.updated_at ? formatDateTime(roleDetail.updated_at) : "—"}
                  </span>
                </div>
              </div>
            )}

            {/* Error Banners */}
            {(validationError || errorDetail) && (
              <div
                role="alert"
                style={{
                  padding: "0.75rem 1rem",
                  borderRadius: "8px",
                  background: "var(--status-danger-bg)",
                  border: "1px solid var(--status-danger-border)",
                  color: "var(--status-danger)",
                  display: "flex",
                  alignItems: "flex-start",
                  gap: "0.5rem",
                  fontSize: "0.875rem",
                }}
              >
                <AlertCircleIcon size={18} style={{ flexShrink: 0, marginTop: "2px" }} />
                <div>
                  {errorCode && (
                    <strong style={{ display: "block", marginBottom: "0.15rem" }}>
                      [{errorCode}]
                    </strong>
                  )}
                  <span>{validationError || errorDetail}</span>
                </div>
              </div>
            )}

            {/* Role Name */}
            <div>
              <label
                htmlFor={`${baseId}-name`}
                style={{
                  display: "block",
                  fontSize: "0.8125rem",
                  fontWeight: 600,
                  marginBottom: "0.35rem",
                  color: "var(--text-primary)",
                }}
              >
                Role Name {mode !== "view" && <span style={{ color: "var(--status-danger)" }}>*</span>}
              </label>
              <input
                ref={nameInputRef}
                id={`${baseId}-name`}
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g. Audit Manager"
                disabled={isSubmitting || mode === "view"}
                readOnly={mode === "view"}
                maxLength={100}
                required={mode !== "view"}
                style={{
                  width: "100%",
                  padding: "0.55rem 0.75rem",
                  borderRadius: "8px",
                  border: "1px solid var(--border-glass)",
                  background: mode === "view" ? "rgba(0, 0, 0, 0.1)" : "var(--input-bg)",
                  color: "var(--text-primary)",
                  fontSize: "0.875rem",
                }}
              />
            </div>

            {/* Role Code */}
            <div>
              <label
                htmlFor={`${baseId}-code`}
                style={{
                  display: "block",
                  fontSize: "0.8125rem",
                  fontWeight: 600,
                  marginBottom: "0.35rem",
                  color: "var(--text-primary)",
                }}
              >
                Role Code{" "}
                {mode === "create" ? (
                  <span style={{ color: "var(--status-danger)" }}>*</span>
                ) : (
                  <span style={{ fontSize: "0.75rem", color: "var(--text-muted)", fontWeight: 400 }}>
                    (Immutable)
                  </span>
                )}
              </label>
              <input
                id={`${baseId}-code`}
                type="text"
                value={code}
                onChange={(e) => setCode(e.target.value.toLowerCase().trim())}
                placeholder="e.g. audit_manager"
                disabled={mode !== "create" || isSubmitting}
                readOnly={mode !== "create"}
                maxLength={50}
                required={mode === "create"}
                style={{
                  width: "100%",
                  padding: "0.55rem 0.75rem",
                  borderRadius: "8px",
                  border: "1px solid var(--border-glass)",
                  background: mode !== "create" ? "rgba(0, 0, 0, 0.1)" : "var(--input-bg)",
                  color: mode !== "create" ? "var(--text-secondary)" : "var(--text-primary)",
                  fontSize: "0.875rem",
                  fontFamily: "var(--font-code)",
                }}
              />
              {mode === "create" && (
                <span
                  style={{
                    display: "block",
                    fontSize: "0.75rem",
                    color: "var(--text-muted)",
                    marginTop: "0.25rem",
                  }}
                >
                  Lowercase letters, numbers, and single underscores only.
                </span>
              )}
            </div>

            {/* Description */}
            <div>
              <label
                htmlFor={`${baseId}-desc-input`}
                style={{
                  display: "block",
                  fontSize: "0.8125rem",
                  fontWeight: 600,
                  marginBottom: "0.35rem",
                  color: "var(--text-primary)",
                }}
              >
                Description
              </label>
              <textarea
                id={`${baseId}-desc-input`}
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder={mode === "view" ? "No description provided." : "Describe responsibilities and access scope..."}
                disabled={isSubmitting || mode === "view"}
                readOnly={mode === "view"}
                rows={2}
                maxLength={500}
                style={{
                  width: "100%",
                  padding: "0.55rem 0.75rem",
                  borderRadius: "8px",
                  border: "1px solid var(--border-glass)",
                  background: mode === "view" ? "rgba(0, 0, 0, 0.1)" : "var(--input-bg)",
                  color: "var(--text-primary)",
                  fontSize: "0.875rem",
                  resize: mode === "view" ? "none" : "vertical",
                }}
              />
            </div>

            {/* Permissions */}
            {mode === "view" ? (
              <div>
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    marginBottom: "0.5rem",
                  }}
                >
                  <label
                    style={{
                      fontSize: "0.8125rem",
                      fontWeight: 600,
                      color: "var(--text-primary)",
                    }}
                  >
                    Assigned Permissions
                  </label>
                  <span style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
                    {selectedPermissions.size} assigned
                  </span>
                </div>
                {selectedPermissions.size === 0 ? (
                  <div
                    style={{
                      padding: "1.25rem",
                      textAlign: "center",
                      color: "var(--text-muted)",
                      fontSize: "0.8125rem",
                      background: "rgba(0, 0, 0, 0.15)",
                      borderRadius: "8px",
                      border: "1px solid var(--border-subtle)",
                    }}
                  >
                    No permissions assigned to this role.
                  </div>
                ) : (
                  <div
                    style={{
                      display: "flex",
                      flexWrap: "wrap",
                      gap: "0.4rem",
                      padding: "0.75rem",
                      background: "rgba(0, 0, 0, 0.15)",
                      borderRadius: "8px",
                      border: "1px solid var(--border-subtle)",
                    }}
                  >
                    {Array.from(selectedPermissions).map((pk) => {
                      const catalogMatch = catalog?.permissions.find((p) => p.key === pk);
                      const detailMatch = roleDetail?.permissions?.find((p) => p.key === pk);
                      const displayName = catalogMatch?.display_name || detailMatch?.display_name || pk;
                      return (
                        <div
                          key={pk}
                          style={{
                            display: "inline-flex",
                            alignItems: "center",
                            gap: "0.35rem",
                            fontSize: "0.75rem",
                            padding: "0.25rem 0.55rem",
                            borderRadius: "6px",
                            background: "rgba(0, 0, 0, 0.25)",
                            border: "1px solid var(--border-subtle)",
                            color: "var(--text-primary)",
                          }}
                        >
                          <span style={{ fontWeight: 600 }}>{displayName}</span>
                          <span
                            style={{
                              fontSize: "0.6875rem",
                              color: "var(--text-muted)",
                              fontFamily: "var(--font-code)",
                            }}
                          >
                            ({pk})
                          </span>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            ) : (
              <div>
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    marginBottom: "0.5rem",
                  }}
                >
                  <label
                    style={{
                      fontSize: "0.8125rem",
                      fontWeight: 600,
                      color: "var(--text-primary)",
                    }}
                  >
                    Permissions
                  </label>
                  <span style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
                    {selectedPermissions.size} selected
                  </span>
                </div>

                {isCatalogLoading ? (
                  <div
                    style={{
                      padding: "1.5rem",
                      textAlign: "center",
                      color: "var(--text-secondary)",
                      fontSize: "0.875rem",
                    }}
                  >
                    Loading grantable permissions catalog...
                  </div>
                ) : (
                  <div
                    style={{
                      display: "flex",
                      flexDirection: "column",
                      gap: "0.75rem",
                      background: "rgba(0, 0, 0, 0.15)",
                      border: "1px solid var(--border-subtle)",
                      borderRadius: "8px",
                      padding: "0.75rem",
                    }}
                  >
                    {/* Permissions outside current actor catalog (read-only/removable) */}
                    {externalRolePermissions.length > 0 && (
                      <div
                        style={{
                          padding: "0.75rem 1rem",
                          background: "var(--status-warning-bg)",
                          border: "1px solid var(--status-warning-border)",
                          borderRadius: "8px",
                          marginBottom: "0.5rem",
                        }}
                      >
                        <div
                          style={{
                            fontSize: "0.8125rem",
                            fontWeight: 700,
                            color: "var(--status-warning)",
                            marginBottom: "0.35rem",
                          }}
                        >
                          Currently Assigned Unavailable Permissions
                        </div>
                        <p
                          style={{
                            margin: "0 0 0.5rem 0",
                            fontSize: "0.75rem",
                            color: "var(--text-secondary)",
                            lineHeight: 1.4,
                          }}
                        >
                          These permissions are currently assigned to this role but are unavailable for granting under your current authority or organization ceiling. They remain preserved unless you intentionally remove them below. Once removed, they cannot be re-granted.
                        </p>
                        <div style={{ display: "flex", flexWrap: "wrap", gap: "0.4rem" }}>
                          {externalRolePermissions.map((k) => (
                            <div
                              key={k}
                              style={{
                                display: "inline-flex",
                                alignItems: "center",
                                gap: "0.4rem",
                                fontSize: "0.75rem",
                                padding: "0.25rem 0.55rem",
                                borderRadius: "6px",
                                background: "rgba(0, 0, 0, 0.25)",
                                border: "1px solid var(--border-subtle)",
                                color: "var(--text-primary)",
                                fontFamily: "var(--font-code)",
                              }}
                            >
                              <span>{k}</span>
                              <span
                                style={{
                                  fontSize: "0.625rem",
                                  color: "var(--text-muted)",
                                  borderLeft: "1px solid var(--border-subtle)",
                                  paddingLeft: "0.35rem",
                                }}
                              >
                                Unavailable
                              </span>
                              <button
                                type="button"
                                onClick={() => handleRemoveExternalPermission(k)}
                                disabled={isSubmitting}
                                title={`Remove ${k} from role`}
                                aria-label={`Remove ${k} from role`}
                                style={{
                                  background: "transparent",
                                  border: "none",
                                  color: "var(--status-danger)",
                                  cursor: isSubmitting ? "not-allowed" : "pointer",
                                  padding: "0 0.15rem",
                                  fontSize: "0.9375rem",
                                  lineHeight: 1,
                                  fontWeight: 700,
                                }}
                              >
                                ×
                              </button>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {catalog && catalog.permissions.length === 0 ? (
                      <p
                        style={{
                          margin: 0,
                          fontSize: "0.8125rem",
                          color: "var(--text-muted)",
                          textAlign: "center",
                          padding: "0.5rem",
                        }}
                      >
                        No grantable permissions available in current active authority.
                      </p>
                    ) : (
                      Object.entries(permissionsByCategory).map(([category, perms]) => (
                        <div key={category}>
                          <div
                            style={{
                              fontSize: "0.75rem",
                              fontWeight: 700,
                              textTransform: "uppercase",
                              letterSpacing: "0.05em",
                              color: "var(--text-muted)",
                              marginBottom: "0.4rem",
                            }}
                          >
                            {category}
                          </div>
                          <div style={{ display: "flex", flexDirection: "column", gap: "0.4rem" }}>
                            {perms.map((p) => {
                              const isChecked = selectedPermissions.has(p.key);
                              return (
                                <label
                                  key={p.key}
                                  style={{
                                    display: "flex",
                                    alignItems: "flex-start",
                                    gap: "0.6rem",
                                    padding: "0.45rem 0.6rem",
                                    borderRadius: "6px",
                                    background: isChecked
                                      ? "var(--brand-primary-light)"
                                      : "transparent",
                                    border: `1px solid ${
                                      isChecked ? "var(--border-glass)" : "transparent"
                                    }`,
                                    cursor: isSubmitting ? "not-allowed" : "pointer",
                                    transition: "background 0.15s ease",
                                  }}
                                >
                                  <input
                                    type="checkbox"
                                    checked={isChecked}
                                    onChange={() => handleTogglePermission(p.key)}
                                    disabled={isSubmitting}
                                    style={{
                                      marginTop: "0.2rem",
                                      accentColor: "var(--brand-primary)",
                                      cursor: "pointer",
                                    }}
                                  />
                                  <div style={{ display: "flex", flexDirection: "column" }}>
                                    <span
                                      style={{
                                        fontSize: "0.8125rem",
                                        fontWeight: 600,
                                        color: isChecked
                                          ? "var(--text-primary)"
                                          : "var(--text-secondary)",
                                      }}
                                    >
                                      {p.display_name}
                                    </span>
                                    <span
                                      style={{
                                        fontSize: "0.75rem",
                                        color: "var(--text-muted)",
                                        fontFamily: "var(--font-code)",
                                      }}
                                    >
                                      {p.key}
                                    </span>
                                  </div>
                                </label>
                              );
                            })}
                          </div>
                        </div>
                      ))
                    )}
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Footer with Proper Inner Padding */}
          <div
            style={{
              padding: "1rem 1.5rem",
              borderTop: "1px solid var(--border-subtle)",
              background: "rgba(0, 0, 0, 0.15)",
              display: "flex",
              justifyContent: "flex-end",
              alignItems: "center",
              gap: "0.75rem",
            }}
          >
            {mode === "view" ? (
              <button
                type="button"
                className="btn btn-secondary"
                onClick={onClose}
              >
                Close
              </button>
            ) : (
              <>
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={onClose}
                  disabled={isSubmitting}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="btn btn-primary"
                  disabled={isSubmitting || isCatalogLoading}
                >
                  {isSubmitting
                    ? "Saving..."
                    : mode === "create"
                    ? "Create Role"
                    : "Save Changes"}
                </button>
              </>
            )}
          </div>
        </form>
      </div>
    </div>
  );
};
