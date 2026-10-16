/**
 * Assign Role Modal (Phase 2E Stage 6).
 *
 * Allows Tenant Admins with 'roles.assign' permission to:
 * - Reassign administrative roles for active, suspended, or ended Tenant Admins
 * - Reset role to system default (system_tenant_admin) via { role_id: null }
 * - Visually detect and disable roles exceeding the actor's current effective permissions
 * - Refresh AuthContext via refreshUser() if the actor reassigns their own role
 * - Present precise backend error codes (e.g. LAST_ADMIN_PROTECTION, INSUFFICIENT_PRIVILEGES)
 */

import React, { useCallback, useEffect, useId, useMemo, useRef, useState } from "react";
import { ApiError } from "../../api/client.ts";
import { rolesApi } from "../../api/roles.ts";
import type {
  AdministrativeMembershipItem,
  RoleItem,
} from "../../api/types.ts";
import { useAuth } from "../../context/AuthContext.tsx";
import { AlertCircleIcon, ChevronDownIcon, CloseIcon, ShieldCheckIcon, UserIcon } from "../Icons.tsx";
import { useDialogAccessibility } from "../plans/PlanModalShell.tsx";

interface AssignRoleModalProps {
  readonly isOpen: boolean;
  readonly membership: AdministrativeMembershipItem | null;
  readonly onClose: () => void;
  readonly onSuccess: (updated: AdministrativeMembershipItem) => void;
  readonly triggerRef?: React.RefObject<HTMLElement | null>;
}

export const AssignRoleModal: React.FC<AssignRoleModalProps> = ({
  isOpen,
  membership,
  onClose,
  onSuccess,
  triggerRef,
}) => {
  const baseId = useId();
  const { user, refreshUser } = useAuth();
  const dropdownTriggerRef = useRef<HTMLButtonElement | null>(null);
  const dropdownMenuRef = useRef<HTMLDivElement | null>(null);

  const [roles, setRoles] = useState<readonly RoleItem[]>([]);
  const [selectedRoleId, setSelectedRoleId] = useState<string>("");
  const [isDropdownOpen, setIsDropdownOpen] = useState<boolean>(false);
  const [highlightedIndex, setHighlightedIndex] = useState<number>(-1);
  const [isLoadingRoles, setIsLoadingRoles] = useState<boolean>(false);
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  const [errorDetail, setErrorDetail] = useState<string | null>(null);
  const [errorCode, setErrorCode] = useState<string | null>(null);

  const { dialogRef } = useDialogAccessibility({
    isOpen,
    isSubmitting,
    onClose,
    triggerRef,
    initialFocusRef: dropdownTriggerRef,
  });

  // Actor effective permissions from context
  const actorEffectivePerms = useMemo(() => {
    return new Set(user?.active_context?.effective_permissions ?? []);
  }, [user?.active_context?.effective_permissions]);

  // Fetch active roles for selection
  const fetchRoles = useCallback(async () => {
    setIsLoadingRoles(true);
    setErrorDetail(null);
    setErrorCode(null);
    try {
      const res = await rolesApi.listRoles({ page_size: 100 });
      // Only active roles are selectable targets
      const activeRoles = res.results.filter((r) => r.status === "active");
      setRoles(activeRoles);
    } catch {
      setErrorDetail("Unable to load organization roles.");
    } finally {
      setIsLoadingRoles(false);
    }
  }, []);

  useEffect(() => {
    if (isOpen) {
      void fetchRoles();
      setErrorDetail(null);
      setErrorCode(null);
      setIsDropdownOpen(false);
      setHighlightedIndex(-1);
      // Pre-select current role
      if (membership?.role?.id) {
        setSelectedRoleId(membership.role.id);
      } else {
        setSelectedRoleId("SYSTEM_DEFAULT");
      }
    }
  }, [isOpen, membership, fetchRoles]);

  // Check if a role exceeds actor authority
  const isRoleBroaderThanActor = useCallback(
    (roleItem: RoleItem): boolean => {
      if (actorEffectivePerms.size === 0) return true;
      for (const pk of roleItem.permission_keys) {
        if (!actorEffectivePerms.has(pk)) {
          return true;
        }
      }
      return false;
    },
    [actorEffectivePerms]
  );

  // Structured selectable options list
  const selectableOptions = useMemo(() => {
    const opts = [
      {
        id: "SYSTEM_DEFAULT",
        name: "System Default — Tenant Administrator",
        description: "Reset to default platform Tenant Administrator role",
        disabled: false,
      },
    ];

    roles
      .filter((r) => !r.is_system_role)
      .forEach((r) => {
        const isBroader = isRoleBroaderThanActor(r);
        opts.push({
          id: r.id,
          name: `${r.name} (${r.code})`,
          description: isBroader ? "Exceeds your active authority" : r.description || "",
          disabled: isBroader,
        });
      });

    return opts;
  }, [roles, isRoleBroaderThanActor]);

  const activeOption = useMemo(() => {
    return selectableOptions.find((o) => o.id === selectedRoleId) || selectableOptions[0];
  }, [selectableOptions, selectedRoleId]);

  const isCurrentRole = useMemo(() => {
    if (!membership) return false;
    if (selectedRoleId === "SYSTEM_DEFAULT") {
      return Boolean(membership.role?.is_system_role);
    }
    return membership.role?.id === selectedRoleId;
  }, [membership, selectedRoleId]);

  // Close dropdown on outside click
  useEffect(() => {
    if (!isDropdownOpen) return;

    const handlePointerDown = (e: MouseEvent | TouchEvent) => {
      const target = e.target as Node;
      if (
        dropdownMenuRef.current &&
        !dropdownMenuRef.current.contains(target) &&
        dropdownTriggerRef.current &&
        !dropdownTriggerRef.current.contains(target)
      ) {
        setIsDropdownOpen(false);
      }
    };

    document.addEventListener("mousedown", handlePointerDown);
    document.addEventListener("touchstart", handlePointerDown);
    return () => {
      document.removeEventListener("mousedown", handlePointerDown);
      document.removeEventListener("touchstart", handlePointerDown);
    };
  }, [isDropdownOpen]);

  const handleDropdownKeyDown = (e: React.KeyboardEvent) => {
    if (!isDropdownOpen) {
      if (e.key === "Enter" || e.key === " " || e.key === "ArrowDown") {
        e.preventDefault();
        setIsDropdownOpen(true);
        const idx = selectableOptions.findIndex((o) => o.id === selectedRoleId);
        setHighlightedIndex(idx >= 0 ? idx : 0);
      }
      return;
    }

    switch (e.key) {
      case "Escape":
        e.preventDefault();
        e.stopPropagation();
        setIsDropdownOpen(false);
        dropdownTriggerRef.current?.focus();
        break;
      case "ArrowDown":
        e.preventDefault();
        setHighlightedIndex((prev) =>
          prev < selectableOptions.length - 1 ? prev + 1 : 0
        );
        break;
      case "ArrowUp":
        e.preventDefault();
        setHighlightedIndex((prev) =>
          prev > 0 ? prev - 1 : selectableOptions.length - 1
        );
        break;
      case "Enter":
      case " ": {
        e.preventDefault();
        if (highlightedIndex >= 0 && highlightedIndex < selectableOptions.length) {
          const targetOpt = selectableOptions[highlightedIndex];
          if (!targetOpt.disabled) {
            setSelectedRoleId(targetOpt.id);
            setIsDropdownOpen(false);
            dropdownTriggerRef.current?.focus();
          }
        }
        break;
      }
      case "Tab":
        setIsDropdownOpen(false);
        break;
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!membership) return;

    if (isCurrentRole) {
      // Harmless no-op close
      onClose();
      return;
    }

    setErrorDetail(null);
    setErrorCode(null);
    setIsSubmitting(true);

    try {
      const targetRoleId =
        selectedRoleId === "SYSTEM_DEFAULT" ? null : selectedRoleId;

      const updated = await rolesApi.assignMembershipRole(membership.id, {
        role_id: targetRoleId,
      });

      // If the actor reassigned their own membership role, refresh AuthContext immediately
      if (user && membership.user.id === user.id) {
        await refreshUser();
      }

      onSuccess(updated);
      onClose();
    } catch (err) {
      if (err instanceof ApiError) {
        const d = err.data as { code?: string; detail?: string } | undefined;
        setErrorCode(d?.code || `HTTP_${err.status}`);
        setErrorDetail(d?.detail || err.message || "Failed to assign role.");
      } else {
        setErrorDetail("An unexpected error occurred during role assignment.");
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  if (!isOpen || !membership) return null;

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
        padding: "0.5rem",
        zIndex: 1000,
        overflowY: "auto",
        boxSizing: "border-box",
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
          maxWidth: "520px",
          maxHeight: "calc(100dvh - 1rem)",
          display: "flex",
          flexDirection: "column",
          borderRadius: "14px",
          background: "var(--glass-surface-elevated)",
          border: "1px solid var(--border-glass)",
          boxShadow: "var(--shadow-lg)",
          overflow: "hidden",
          boxSizing: "border-box",
          minWidth: 0,
          margin: "auto",
        }}
      >
        {/* Header */}
        <div
          style={{
            padding: "1rem 1.25rem",
            borderBottom: "1px solid var(--border-subtle)",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: "0.5rem",
            boxSizing: "border-box",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", minWidth: 0 }}>
            <ShieldCheckIcon size={20} style={{ color: "var(--brand-primary)", flexShrink: 0 }} />
            <h2
              id={`${baseId}-title`}
              style={{
                margin: 0,
                fontSize: "1.0625rem",
                fontWeight: 700,
                color: "var(--text-primary)",
                overflowWrap: "anywhere",
              }}
            >
              Assign Administrator Role
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
              flexShrink: 0,
            }}
          >
            <CloseIcon size={18} />
          </button>
        </div>

        {/* Form */}
        <form
          onSubmit={handleSubmit}
          style={{
            display: "flex",
            flexDirection: "column",
            minHeight: 0,
            flex: 1,
            overflow: "hidden",
          }}
        >
          <div
            style={{
              padding: "1rem 1.25rem",
              display: "flex",
              flexDirection: "column",
              gap: "1rem",
              overflowY: "auto",
              flex: 1,
              minHeight: 0,
              minWidth: 0,
              boxSizing: "border-box",
            }}
          >
            <p
              id={`${baseId}-desc`}
              style={{
                margin: 0,
                fontSize: "0.8125rem",
                color: "var(--text-secondary)",
                lineHeight: 1.5,
              }}
            >
              Update the administrative role for this tenant administrator. Non-escalation rules
              require assigned capabilities to be a subset of your active authority.
            </p>

            {/* Error Banner */}
            {errorDetail && (
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
                  boxSizing: "border-box",
                  minWidth: 0,
                }}
              >
                <AlertCircleIcon size={18} style={{ flexShrink: 0, marginTop: "2px" }} />
                <div style={{ minWidth: 0, overflowWrap: "anywhere" }}>
                  {errorCode && (
                    <strong style={{ display: "block", marginBottom: "0.15rem" }}>
                      [{errorCode}]
                    </strong>
                  )}
                  <span>{errorDetail}</span>
                </div>
              </div>
            )}

            {/* Administrator Info Card */}
            <div
              style={{
                padding: "0.75rem 0.875rem",
                background: "rgba(0, 0, 0, 0.2)",
                borderRadius: "8px",
                border: "1px solid var(--border-subtle)",
                display: "flex",
                flexDirection: "column",
                gap: "0.5rem",
                minWidth: 0,
                boxSizing: "border-box",
              }}
            >
              <div style={{ display: "flex", alignItems: "flex-start", gap: "0.5rem", minWidth: 0 }}>
                <UserIcon size={16} style={{ color: "var(--text-muted)", flexShrink: 0, marginTop: "2px" }} />
                <div style={{ display: "flex", flexDirection: "column", minWidth: 0, flex: 1, overflowWrap: "anywhere", wordBreak: "break-word" }}>
                  <span
                    style={{
                      fontSize: "0.875rem",
                      fontWeight: 600,
                      color: "var(--text-primary)",
                      minWidth: 0,
                      overflowWrap: "anywhere",
                    }}
                  >
                    {membership.user.full_name}
                  </span>
                  <span
                    style={{
                      fontSize: "0.8125rem",
                      color: "var(--text-muted)",
                      minWidth: 0,
                      overflowWrap: "anywhere",
                      wordBreak: "break-all",
                    }}
                  >
                    ({membership.user.email})
                  </span>
                </div>
              </div>
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "0.75rem",
                  fontSize: "0.75rem",
                  flexWrap: "wrap",
                  minWidth: 0,
                }}
              >
                <div style={{ minWidth: 0, overflowWrap: "anywhere" }}>
                  <span style={{ color: "var(--text-muted)", marginRight: "0.25rem" }}>
                    Membership Status:
                  </span>
                  <span
                    style={{
                      fontWeight: 600,
                      textTransform: "capitalize",
                      color:
                        membership.status === "active"
                          ? "var(--status-success)"
                          : membership.status === "suspended"
                          ? "var(--status-warning)"
                          : "var(--text-muted)",
                    }}
                  >
                    {membership.status}
                  </span>
                </div>
                <div style={{ minWidth: 0, overflowWrap: "anywhere", wordBreak: "break-word" }}>
                  <span style={{ color: "var(--text-muted)", marginRight: "0.25rem" }}>
                    Current Role:
                  </span>
                  <span style={{ fontWeight: 600, color: "var(--text-primary)" }}>
                    {membership.role?.name || "System Tenant Admin"}
                  </span>
                </div>
              </div>
            </div>

            {/* Role Selection Dropdown */}
            <div style={{ position: "relative", minWidth: 0, width: "100%", boxSizing: "border-box" }}>
              <label
                id={`${baseId}-role-label`}
                htmlFor={`${baseId}-role-select-btn`}
                style={{
                  display: "block",
                  fontSize: "0.8125rem",
                  fontWeight: 600,
                  marginBottom: "0.35rem",
                  color: "var(--text-primary)",
                }}
              >
                Target Administrative Role <span style={{ color: "var(--status-danger)" }}>*</span>
              </label>

              {isLoadingRoles ? (
                <div style={{ fontSize: "0.8125rem", color: "var(--text-muted)", padding: "0.5rem 0" }}>
                  Loading available roles...
                </div>
              ) : (
                <div style={{ position: "relative", width: "100%", minWidth: 0, boxSizing: "border-box" }}>
                  {/* Dropdown Trigger Button */}
                  <button
                    ref={dropdownTriggerRef}
                    id={`${baseId}-role-select-btn`}
                    type="button"
                    onClick={() => setIsDropdownOpen((prev) => !prev)}
                    onKeyDown={handleDropdownKeyDown}
                    disabled={isSubmitting}
                    aria-haspopup="listbox"
                    aria-expanded={isDropdownOpen}
                    aria-labelledby={`${baseId}-role-label ${baseId}-role-select-btn`}
                    style={{
                      width: "100%",
                      minHeight: "42px",
                      padding: "0.55rem 0.75rem",
                      borderRadius: "8px",
                      border: "1px solid var(--border-glass)",
                      background: "var(--input-bg)",
                      color: "var(--text-primary)",
                      fontSize: "0.875rem",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "space-between",
                      gap: "0.5rem",
                      cursor: isSubmitting ? "not-allowed" : "pointer",
                      textAlign: "left",
                      boxSizing: "border-box",
                      minWidth: 0,
                    }}
                  >
                    <span
                      style={{
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                        whiteSpace: "nowrap",
                        minWidth: 0,
                        flex: 1,
                      }}
                    >
                      {activeOption?.name || "Select Role"}
                    </span>
                    <span
                      style={{
                        display: "flex",
                        alignItems: "center",
                        transform: isDropdownOpen ? "rotate(180deg)" : "rotate(0deg)",
                        transition: "transform 0.15s ease",
                        color: "var(--text-muted)",
                        flexShrink: 0,
                      }}
                    >
                      <ChevronDownIcon size={16} />
                    </span>
                  </button>

                  {/* Accessible Bounded Dropdown Listbox */}
                  {isDropdownOpen && (
                    <div
                      ref={dropdownMenuRef}
                      role="listbox"
                      aria-labelledby={`${baseId}-role-label`}
                      style={{
                        position: "absolute",
                        top: "calc(100% + 4px)",
                        left: 0,
                        right: 0,
                        width: "100%",
                        maxHeight: "200px",
                        overflowY: "auto",
                        background: "var(--glass-surface-elevated)",
                        border: "1px solid var(--border-glass)",
                        borderRadius: "8px",
                        boxShadow: "var(--shadow-lg)",
                        zIndex: 1100,
                        padding: "0.25rem",
                        display: "flex",
                        flexDirection: "column",
                        gap: "0.15rem",
                        boxSizing: "border-box",
                        minWidth: 0,
                      }}
                    >
                      {selectableOptions.map((opt, idx) => {
                        const isSelected = selectedRoleId === opt.id;
                        const isHighlighted = highlightedIndex === idx;

                        return (
                          <div
                            key={opt.id}
                            role="option"
                            aria-selected={isSelected}
                            aria-disabled={opt.disabled}
                            onClick={() => {
                              if (!opt.disabled) {
                                setSelectedRoleId(opt.id);
                                setIsDropdownOpen(false);
                                dropdownTriggerRef.current?.focus();
                              }
                            }}
                            onMouseEnter={() => setHighlightedIndex(idx)}
                            style={{
                              padding: "0.55rem 0.65rem",
                              borderRadius: "6px",
                              cursor: opt.disabled ? "not-allowed" : "pointer",
                              opacity: opt.disabled ? 0.5 : 1,
                              background: isSelected
                                ? "var(--brand-primary-subtle, rgba(99, 102, 241, 0.15))"
                                : isHighlighted
                                ? "rgba(255, 255, 255, 0.06)"
                                : "transparent",
                              border: isSelected
                                ? "1px solid var(--brand-primary, #6366f1)"
                                : "1px solid transparent",
                              display: "flex",
                              flexDirection: "column",
                              gap: "0.15rem",
                              minWidth: 0,
                              boxSizing: "border-box",
                            }}
                          >
                            <span
                              style={{
                                fontSize: "0.8125rem",
                                fontWeight: isSelected ? 600 : 500,
                                color: opt.disabled ? "var(--text-muted)" : "var(--text-primary)",
                                whiteSpace: "normal",
                                overflowWrap: "anywhere",
                                wordBreak: "break-word",
                              }}
                            >
                              {opt.name}
                            </span>
                            {opt.description && (
                              <span
                                style={{
                                  fontSize: "0.75rem",
                                  color: opt.disabled ? "var(--status-danger)" : "var(--text-muted)",
                                  whiteSpace: "normal",
                                  overflowWrap: "anywhere",
                                  wordBreak: "break-word",
                                }}
                              >
                                {opt.description}
                              </span>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              )}

              <span
                style={{
                  display: "block",
                  fontSize: "0.75rem",
                  color: "var(--text-muted)",
                  marginTop: "0.35rem",
                  lineHeight: 1.4,
                  minWidth: 0,
                  overflowWrap: "anywhere",
                }}
              >
                Resetting to default assigns the platform-wide system Tenant Administrator role.
              </span>
            </div>
          </div>

          {/* Footer */}
          <div
            style={{
              padding: "0.875rem 1.25rem",
              borderTop: "1px solid var(--border-subtle)",
              background: "rgba(0, 0, 0, 0.15)",
              display: "flex",
              justifyContent: "flex-end",
              alignItems: "center",
              gap: "0.75rem",
              flexWrap: "wrap",
              boxSizing: "border-box",
            }}
          >
            <button
              type="button"
              className="btn btn-secondary"
              onClick={onClose}
              disabled={isSubmitting}
              style={{ minHeight: "38px" }}
            >
              Cancel
            </button>
            <button
              type="submit"
              className="btn btn-primary"
              disabled={isSubmitting || isLoadingRoles}
              style={{ minHeight: "38px" }}
            >
              {isSubmitting ? "Assigning..." : isCurrentRole ? "Keep Current Role" : "Assign Role"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

