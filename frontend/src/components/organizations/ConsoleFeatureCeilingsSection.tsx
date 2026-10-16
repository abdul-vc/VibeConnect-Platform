/**
 * Console Feature Ceilings Section (Phase 2E Stage 6).
 *
 * Provides Platform Owners with:
 * - Organization console module policy controls (tenant_landing core locked, tenant_roles toggleable)
 * - Focused confirmation modal when disabling tenant_roles module
 * - Permission ceiling controls for tenant_roles (roles.view, roles.manage, roles.assign)
 * - Strict dependency rule guidance (manage/assign require view)
 * - Server state refresh, rollback on failure, accessible toggles, and backend error presentation
 */

import React, { useCallback, useEffect, useRef, useState } from "react";
import { ApiError } from "../../api/client.ts";
import { rolesApi } from "../../api/roles.ts";
import type {
  ConsoleModulePolicyItem,
  PermissionCeilingItem,
} from "../../api/types.ts";
import { AlertCircleIcon, CloseIcon, RotateCcwIcon, ShieldCheckIcon } from "../Icons.tsx";
import { useDialogAccessibility } from "../plans/PlanModalShell.tsx";

interface ConsoleFeatureCeilingsSectionProps {
  readonly organizationId: string;
}

export const ConsoleFeatureCeilingsSection: React.FC<ConsoleFeatureCeilingsSectionProps> = ({
  organizationId,
}) => {
  const [policies, setPolicies] = useState<readonly ConsoleModulePolicyItem[]>([]);
  const [ceilings, setCeilings] = useState<readonly PermissionCeilingItem[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [errorCode, setErrorCode] = useState<string | null>(null);

  // Mutation in-flight tracking
  const [mutatingKey, setMutatingKey] = useState<string | null>(null);
  const [mutationError, setMutationError] = useState<string | null>(null);

  // Confirmation Modal state for disabling module
  const [confirmDisableModule, setConfirmDisableModule] = useState<ConsoleModulePolicyItem | null>(null);
  const triggerRef = useRef<HTMLElement | null>(null);

  const fetchData = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    setErrorCode(null);
    setMutationError(null);
    try {
      const [policiesRes, ceilingsRes] = await Promise.all([
        rolesApi.listConsolePolicies(organizationId),
        rolesApi.listPermissionCeilings(organizationId),
      ]);
      setPolicies(policiesRes);
      setCeilings(ceilingsRes);
    } catch (err) {
      if (err instanceof ApiError) {
        const d = err.data as { code?: string; detail?: string } | undefined;
        setErrorCode(d?.code || `HTTP_${err.status}`);
        setError(d?.detail || err.message || "Failed to load console policies.");
      } else {
        setError("Unable to load console feature policies and ceilings.");
      }
    } finally {
      setIsLoading(false);
    }
  }, [organizationId]);

  useEffect(() => {
    void fetchData();
  }, [fetchData]);

  // Handle module toggle
  const handleToggleModule = async (policy: ConsoleModulePolicyItem) => {
    if (policy.is_core) return; // Core modules cannot be disabled
    if (mutatingKey) return; // Prevent concurrent mutations

    if (policy.is_enabled) {
      // Disabling requires focused confirmation
      setConfirmDisableModule(policy);
      return;
    }

    // Enabling module
    await executeModuleUpdate(policy.module_key, true);
  };

  const executeModuleUpdate = async (moduleKey: string, isEnabled: boolean) => {
    setMutatingKey(`module_${moduleKey}`);
    setMutationError(null);
    try {
      const updated = await rolesApi.updateConsolePolicy(organizationId, moduleKey, {
        is_enabled: isEnabled,
      });
      setPolicies((prev) =>
        prev.map((p) => (p.module_key === moduleKey ? updated : p))
      );
      setConfirmDisableModule(null);
    } catch (err) {
      if (err instanceof ApiError) {
        const d = err.data as { code?: string; detail?: string } | undefined;
        setMutationError(
          d?.detail || `[${d?.code || "ERROR"}] Failed to update module policy.`
        );
      } else {
        setMutationError("Network error updating console module policy.");
      }
      // Refetch to guarantee server-authoritative state
      void fetchData();
    } finally {
      setMutatingKey(null);
    }
  };

  // Handle permission ceiling toggle
  const handleToggleCeiling = async (item: PermissionCeilingItem) => {
    if (mutatingKey) return;
    setMutationError(null);

    const willBeAllowed = !item.is_allowed;

    // Dependency Rule UX Check
    if (willBeAllowed) {
      // Enabling manage or assign requires view to be allowed
      if (item.permission_key === "roles.manage" || item.permission_key === "roles.assign") {
        const viewCeiling = ceilings.find((c) => c.permission_key === "roles.view");
        if (!viewCeiling?.is_allowed) {
          setMutationError(
            `Cannot allow '${item.display_name}' (${item.permission_key}) while 'roles.view' is denied. Please allow 'View Roles & Permissions' ceiling first.`
          );
          return;
        }
      }
    } else {
      // Disabling view requires manage and assign to be disabled first
      if (item.permission_key === "roles.view") {
        const dependentAllowed = ceilings.some(
          (c) =>
            (c.permission_key === "roles.manage" || c.permission_key === "roles.assign") &&
            c.is_allowed
        );
        if (dependentAllowed) {
          setMutationError(
            "Cannot disallow 'roles.view' while dependent permissions ('roles.manage' or 'roles.assign') are allowed in the ceiling. Please disallow dependent ceilings first."
          );
          return;
        }
      }
    }

    setMutatingKey(`ceiling_${item.permission_key}`);
    try {
      const updated = await rolesApi.updatePermissionCeiling(
        organizationId,
        item.permission_key,
        { is_allowed: willBeAllowed }
      );
      setCeilings((prev) =>
        prev.map((c) => (c.permission_key === item.permission_key ? updated : c))
      );
    } catch (err) {
      if (err instanceof ApiError) {
        const d = err.data as { code?: string; detail?: string } | undefined;
        setMutationError(
          d?.detail || `[${d?.code || "ERROR"}] Failed to update permission ceiling.`
        );
      } else {
        setMutationError("Network error updating permission ceiling.");
      }
      // Refetch to guarantee state rollback
      void fetchData();
    } finally {
      setMutatingKey(null);
    }
  };

  return (
    <div
      className="profile-section-card"
      style={{
        display: "flex",
        flexDirection: "column",
        gap: "1.25rem",
        background: "var(--glass-surface-elevated)",
        borderRadius: "14px",
        border: "1px solid var(--border-glass)",
        padding: "1.5rem",
      }}
    >
      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: "0.75rem" }}>
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
            <ShieldCheckIcon size={20} style={{ color: "var(--brand-primary)" }} />
            <h3 style={{ fontSize: "1.0625rem", fontWeight: 700, margin: 0, color: "var(--text-primary)" }}>
              Console Feature Ceilings
            </h3>
          </div>
          <p style={{ margin: "0.35rem 0 0 0", fontSize: "0.875rem", color: "var(--text-secondary)", lineHeight: 1.5 }}>
            Configure console modules and maximum capability ceilings for this tenant organization.
            Tenant administrators cannot grant capabilities beyond these policy ceilings.
          </p>
        </div>

        <button
          type="button"
          className="btn btn-secondary btn-sm"
          onClick={fetchData}
          disabled={isLoading || Boolean(mutatingKey)}
          style={{ display: "inline-flex", alignItems: "center", gap: "0.3rem" }}
        >
          <RotateCcwIcon size={14} />
          <span>Refresh</span>
        </button>
      </div>

      {/* Error Banners */}
      {(error || mutationError) && (
        <div
          role="alert"
          style={{
            padding: "0.75rem 1rem",
            borderRadius: "8px",
            background: "var(--status-danger-bg)",
            border: "1px solid var(--status-danger-border)",
            color: "var(--status-danger)",
            fontSize: "0.875rem",
            display: "flex",
            alignItems: "flex-start",
            gap: "0.5rem",
          }}
        >
          <AlertCircleIcon size={18} style={{ flexShrink: 0, marginTop: "2px" }} />
          <div>
            {errorCode && <strong style={{ display: "block" }}>[{errorCode}]</strong>}
            <span>{mutationError || error}</span>
          </div>
        </div>
      )}

      {isLoading ? (
        <div style={{ padding: "2rem", textAlign: "center", color: "var(--text-secondary)", fontSize: "0.875rem" }}>
          Loading console feature policies and ceilings...
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }}>
          {/* 1. Console Module Policies */}
          <div>
            <h4
              style={{
                fontSize: "0.8125rem",
                fontWeight: 700,
                textTransform: "uppercase",
                letterSpacing: "0.05em",
                color: "var(--text-muted)",
                margin: "0 0 0.75rem 0",
              }}
            >
              Tenant Console Modules
            </h4>

            <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
              {policies.map((p) => {
                const isMutating = mutatingKey === `module_${p.module_key}`;
                return (
                  <div
                    key={p.module_key}
                    style={{
                      padding: "1rem",
                      borderRadius: "10px",
                      background: "rgba(0, 0, 0, 0.15)",
                      border: "1px solid var(--border-subtle)",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "space-between",
                      gap: "1rem",
                      flexWrap: "wrap",
                    }}
                  >
                    <div style={{ flex: 1, minWidth: "200px" }}>
                      <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.25rem" }}>
                        <span style={{ fontSize: "0.9375rem", fontWeight: 600, color: "var(--text-primary)" }}>
                          {p.display_name}
                        </span>
                        <code style={{ fontSize: "0.75rem", color: "var(--text-muted)", fontFamily: "var(--font-code)" }}>
                          {p.module_key}
                        </code>
                        {p.is_core && (
                          <span
                            style={{
                              fontSize: "0.6875rem",
                              fontWeight: 600,
                              padding: "0.1rem 0.4rem",
                              borderRadius: "4px",
                              background: "rgba(99, 102, 241, 0.15)",
                              color: "var(--brand-primary)",
                            }}
                          >
                            Core Module
                          </span>
                        )}
                      </div>
                      <p style={{ margin: 0, fontSize: "0.8125rem", color: "var(--text-secondary)", lineHeight: 1.4 }}>
                        {p.description}
                      </p>
                      {p.is_core && (
                        <span style={{ display: "block", fontSize: "0.75rem", color: "var(--text-muted)", marginTop: "0.25rem" }}>
                          Core tenant landing is mandatory and cannot be disabled.
                        </span>
                      )}
                    </div>

                    {/* Toggle */}
                    <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                      <span
                        style={{
                          fontSize: "0.75rem",
                          fontWeight: 600,
                          color: p.is_enabled ? "var(--status-success)" : "var(--text-muted)",
                        }}
                      >
                        {p.is_enabled ? "Enabled" : "Disabled"}
                      </span>
                      <button
                        type="button"
                        role="switch"
                        aria-checked={p.is_enabled}
                        aria-label={`Toggle ${p.display_name} module`}
                        onClick={(e) => {
                          triggerRef.current = e.currentTarget;
                          handleToggleModule(p);
                        }}
                        disabled={p.is_core || isMutating || Boolean(mutatingKey)}
                        style={{
                          width: "44px",
                          height: "24px",
                          borderRadius: "12px",
                          background: p.is_enabled ? "var(--brand-primary)" : "rgba(255, 255, 255, 0.15)",
                          border: "none",
                          position: "relative",
                          cursor: p.is_core || isMutating || Boolean(mutatingKey) ? "not-allowed" : "pointer",
                          transition: "background 0.2s ease",
                          opacity: p.is_core ? 0.6 : 1,
                        }}
                      >
                        <span
                          style={{
                            display: "block",
                            width: "18px",
                            height: "18px",
                            borderRadius: "50%",
                            background: "#ffffff",
                            position: "absolute",
                            top: "3px",
                            left: p.is_enabled ? "23px" : "3px",
                            transition: "left 0.2s ease",
                            boxShadow: "0 1px 3px rgba(0,0,0,0.4)",
                          }}
                        />
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* 2. Permission Ceilings for tenant_roles */}
          <div>
            <h4
              style={{
                fontSize: "0.8125rem",
                fontWeight: 700,
                textTransform: "uppercase",
                letterSpacing: "0.05em",
                color: "var(--text-muted)",
                margin: "0 0 0.75rem 0",
              }}
            >
              Roles & Permissions Ceilings (tenant_roles)
            </h4>

            <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
              {ceilings.map((c) => {
                const isMutating = mutatingKey === `ceiling_${c.permission_key}`;
                return (
                  <div
                    key={c.permission_key}
                    style={{
                      padding: "0.875rem 1rem",
                      borderRadius: "10px",
                      background: "rgba(0, 0, 0, 0.15)",
                      border: "1px solid var(--border-subtle)",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "space-between",
                      gap: "1rem",
                      flexWrap: "wrap",
                    }}
                  >
                    <div style={{ flex: 1, minWidth: "200px" }}>
                      <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.25rem" }}>
                        <span style={{ fontSize: "0.875rem", fontWeight: 600, color: "var(--text-primary)" }}>
                          {c.display_name}
                        </span>
                        <code style={{ fontSize: "0.75rem", color: "var(--text-muted)", fontFamily: "var(--font-code)" }}>
                          {c.permission_key}
                        </code>
                      </div>
                      <p style={{ margin: 0, fontSize: "0.8125rem", color: "var(--text-secondary)", lineHeight: 1.4 }}>
                        {c.description}
                      </p>
                    </div>

                    {/* Toggle */}
                    <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                      <span
                        style={{
                          fontSize: "0.75rem",
                          fontWeight: 600,
                          color: c.is_allowed ? "var(--status-success)" : "var(--status-danger)",
                        }}
                      >
                        {c.is_allowed ? "Allowed" : "Blocked"}
                      </span>
                      <button
                        type="button"
                        role="switch"
                        aria-checked={c.is_allowed}
                        aria-label={`Toggle permission ceiling for ${c.display_name}`}
                        onClick={() => handleToggleCeiling(c)}
                        disabled={isMutating || Boolean(mutatingKey)}
                        style={{
                          width: "44px",
                          height: "24px",
                          borderRadius: "12px",
                          background: c.is_allowed ? "var(--brand-primary)" : "rgba(255, 255, 255, 0.15)",
                          border: "none",
                          position: "relative",
                          cursor: isMutating || Boolean(mutatingKey) ? "not-allowed" : "pointer",
                          transition: "background 0.2s ease",
                        }}
                      >
                        <span
                          style={{
                            display: "block",
                            width: "18px",
                            height: "18px",
                            borderRadius: "50%",
                            background: "#ffffff",
                            position: "absolute",
                            top: "3px",
                            left: c.is_allowed ? "23px" : "3px",
                            transition: "left 0.2s ease",
                            boxShadow: "0 1px 3px rgba(0,0,0,0.4)",
                          }}
                        />
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      )}

      {/* Disabling Confirmation Modal with accessible focus trapping and Escape handling */}
      <DisableModuleDialog
        isOpen={Boolean(confirmDisableModule)}
        policy={confirmDisableModule}
        isSubmitting={Boolean(mutatingKey)}
        onClose={() => setConfirmDisableModule(null)}
        onConfirm={() => {
          if (confirmDisableModule) {
            void executeModuleUpdate(confirmDisableModule.module_key, false);
          }
        }}
        triggerRef={triggerRef}
      />
    </div>
  );
};

interface DisableModuleDialogProps {
  readonly isOpen: boolean;
  readonly policy: ConsoleModulePolicyItem | null;
  readonly isSubmitting: boolean;
  readonly onClose: () => void;
  readonly onConfirm: () => void;
  readonly triggerRef?: React.RefObject<HTMLElement | null>;
}

const DisableModuleDialog: React.FC<DisableModuleDialogProps> = ({
  isOpen,
  policy,
  isSubmitting,
  onClose,
  onConfirm,
  triggerRef,
}) => {
  const cancelBtnRef = useRef<HTMLButtonElement | null>(null);
  const { dialogRef } = useDialogAccessibility({
    isOpen,
    isSubmitting,
    onClose,
    triggerRef,
    initialFocusRef: cancelBtnRef,
  });

  if (!isOpen || !policy) return null;

  return (
    <div
      className="dialog-backdrop modal-backdrop"
      role="presentation"
      onClick={(e) => {
        if (e.target === e.currentTarget && !isSubmitting) {
          onClose();
        }
      }}
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
        zIndex: 1100,
        overflowY: "auto",
      }}
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="disable-module-title"
        aria-describedby="disable-module-desc"
        className="glass-panel"
        style={{
          width: "100%",
          maxWidth: "480px",
          borderRadius: "14px",
          background: "var(--glass-surface-elevated)",
          border: "1px solid var(--border-glass)",
          boxShadow: "var(--shadow-lg)",
          padding: "1.5rem",
          display: "flex",
          flexDirection: "column",
          gap: "1rem",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "0.5rem" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
            <div
              style={{
                width: "28px",
                height: "28px",
                borderRadius: "50%",
                background: "var(--status-danger-bg)",
                border: "1px solid var(--status-danger-border)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                color: "var(--status-danger)",
              }}
            >
              <AlertCircleIcon size={16} />
            </div>
            <h3 id="disable-module-title" style={{ margin: 0, fontSize: "1.125rem", fontWeight: 700, color: "var(--text-primary)" }}>
              Disable {policy.display_name}?
            </h3>
          </div>
          <button
            type="button"
            className="btn-ghost"
            onClick={onClose}
            disabled={isSubmitting}
            aria-label="Close dialog"
            style={{ minWidth: "28px", minHeight: "28px", padding: "4px" }}
          >
            <CloseIcon size={16} />
          </button>
        </div>

        <p id="disable-module-desc" style={{ margin: 0, fontSize: "0.875rem", color: "var(--text-secondary)", lineHeight: 1.5 }}>
          Disabling the <strong>{policy.display_name}</strong> (
          <code>{policy.module_key}</code>) module policy will immediately remove
          the Roles & Permissions console workspace for all administrators in this organization.
        </p>

        <div
          style={{
            padding: "0.75rem",
            borderRadius: "8px",
            background: "var(--status-warning-bg)",
            border: "1px solid var(--status-warning-border)",
            color: "var(--status-warning)",
            fontSize: "0.8125rem",
          }}
        >
          Permission ceilings are preserved. You can re-enable this module at any time.
        </div>

        <div
          style={{
            display: "flex",
            justifyContent: "flex-end",
            gap: "0.75rem",
            paddingTop: "0.5rem",
          }}
        >
          <button
            ref={cancelBtnRef}
            type="button"
            className="btn btn-secondary"
            onClick={onClose}
            disabled={isSubmitting}
          >
            Cancel
          </button>
          <button
            type="button"
            className="btn btn-danger"
            onClick={onConfirm}
            disabled={isSubmitting}
          >
            {isSubmitting ? "Disabling..." : "Disable Module"}
          </button>
        </div>
      </div>
    </div>
  );
};
