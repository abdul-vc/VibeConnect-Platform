/**
 * Edit Modules Modal (Phase 2F Part E).
 *
 * Implements module replacement action:
 * - Loads entitled modules for the assignment's product
 * - Loads and displays current enabled module configuration
 * - Allows toggling modules via accessible checkboxes
 * - An empty module selection is fully valid and supported
 * - Submits the complete resulting module_ids array to PATCH /api/v1/tenant/assignments/<id>/modules/
 * - Prevents duplicate submission while pending
 * - Handles HTTP 409 stale conflicts by notifying and triggering refetch preserving filters
 * - Accessible dialog with Tab focus trap, Escape dismissal, and focus restoration
 */

import React, { useId, useRef, useState, useEffect, useCallback } from "react";
import { assignmentsApi } from "../../../api/assignments.ts";
import { ApiError } from "../../../api/client.ts";
import type { SelectorModuleItem, UserProductAssignmentItem } from "../../../api/types.ts";
import { AlertCircleIcon, CloseIcon, RotateCcwIcon } from "../../Icons.tsx";
import { useDialogAccessibility } from "../../plans/PlanModalShell.tsx";

interface EditModulesModalProps {
  readonly isOpen: boolean;
  readonly assignment: UserProductAssignmentItem | null;
  readonly onClose: () => void;
  readonly onSuccess: () => void;
  readonly onConflict: () => void;
  readonly triggerRef?: React.RefObject<HTMLElement | null>;
}

export const EditModulesModal: React.FC<EditModulesModalProps> = ({
  isOpen,
  assignment,
  onClose,
  onSuccess,
  onConflict,
  triggerRef,
}) => {
  const baseId = useId();
  const firstCheckboxRef = useRef<HTMLInputElement | null>(null);

  const [modules, setModules] = useState<readonly SelectorModuleItem[]>([]);
  const [selectedModuleIds, setSelectedModuleIds] = useState<Set<string>>(new Set());
  const [isLoading, setIsLoading] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [generalError, setGeneralError] = useState<string | null>(null);

  const { dialogRef } = useDialogAccessibility({
    isOpen,
    isSubmitting,
    onClose,
    triggerRef,
    initialFocusRef: firstCheckboxRef,
  });

  const reqGenRef = useRef(0);

  const loadData = useCallback(async () => {
    if (!assignment) return;
    const reqId = ++reqGenRef.current;
    setIsLoading(true);
    setLoadError(null);
    setGeneralError(null);
    setSelectedModuleIds(new Set());
    setModules([]);

    try {
      const [modulesList, detail] = await Promise.all([
        assignmentsApi.getSelectorModules(assignment.product.id),
        assignmentsApi.getAssignment(assignment.id),
      ]);
      if (reqId !== reqGenRef.current) return;
      setModules(modulesList);
      const enabledIds = new Set(
        detail.modules.filter((m) => m.is_enabled).map((m) => m.module_id)
      );
      setSelectedModuleIds(enabledIds);
    } catch {
      if (reqId !== reqGenRef.current) return;
      setLoadError("Failed to load module configuration. Please try again.");
    } finally {
      if (reqId === reqGenRef.current) {
        setIsLoading(false);
      }
    }
  }, [assignment]);

  useEffect(() => {
    if (isOpen && assignment) {
      void loadData();
    }
  }, [isOpen, assignment, loadData]);

  if (!isOpen || !assignment) return null;

  const handleToggleModule = (moduleId: string) => {
    setSelectedModuleIds((prev) => {
      const next = new Set(prev);
      if (next.has(moduleId)) {
        next.delete(moduleId);
      } else {
        next.add(moduleId);
      }
      return next;
    });
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (isLoading || isSubmitting || Boolean(loadError)) {
      return;
    }
    setIsSubmitting(true);
    setGeneralError(null);

    try {
      await assignmentsApi.replaceModules(assignment.id, {
        module_ids: Array.from(selectedModuleIds),
      });
      onSuccess();
      onClose();
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        if (err.status === 409) {
          onConflict();
          onClose();
          return;
        }
        const data = err.data as Record<string, unknown> | undefined;
        const errObj = (data?.error && typeof data.error === "object") ? (data.error as Record<string, unknown>) : null;
        setGeneralError(errObj?.message ? String(errObj.message) : err.message);
      } else {
        setGeneralError("An unexpected error occurred while updating modules.");
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div
      className="dialog-backdrop"
      onClick={(e) => {
        if (e.target === e.currentTarget && !isSubmitting) onClose();
      }}
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={`${baseId}-title`}
        aria-describedby={`${baseId}-desc`}
        className="dialog-surface"
        style={{ maxWidth: "560px" }}
      >
        <div className="dialog-header">
          <div>
            <h2 id={`${baseId}-title`} className="dialog-title">
              Configure Modules
            </h2>
            <p id={`${baseId}-desc`} className="dialog-subtitle">
              Manage enabled modules for {assignment.user.full_name} ({assignment.product.name}).
            </p>
          </div>
          <button
            type="button"
            className="dialog-close-btn"
            onClick={onClose}
            disabled={isSubmitting}
            aria-label="Close dialog"
          >
            <CloseIcon size={18} />
          </button>
        </div>

        <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column" }}>
          <div className="dialog-body" style={{ display: "flex", flexDirection: "column", gap: "1rem", maxHeight: "60vh", overflowY: "auto" }}>
            {generalError && (
              <div className="alert-box alert-danger" role="alert">
                <AlertCircleIcon size={16} style={{ flexShrink: 0 }} />
                <span>{generalError}</span>
              </div>
            )}

            {loadError && (
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  padding: "0.75rem",
                  background: "rgba(239, 68, 68, 0.1)",
                  border: "1px solid rgba(239, 68, 68, 0.3)",
                  borderRadius: "8px",
                  color: "var(--status-danger, #ef4444)",
                  fontSize: "0.875rem",
                }}
              >
                <span>{loadError}</span>
                <button
                  type="button"
                  onClick={loadData}
                  className="btn btn-secondary btn-sm"
                  style={{ display: "inline-flex", alignItems: "center", gap: "0.25rem" }}
                >
                  <RotateCcwIcon size={14} />
                  <span>Retry</span>
                </button>
              </div>
            )}

            {isLoading ? (
              <div style={{ padding: "2rem", textAlign: "center", color: "var(--text-secondary)" }}>
                Loading available modules...
              </div>
            ) : modules.length === 0 ? (
              <div style={{ padding: "2rem", textAlign: "center", color: "var(--text-secondary)" }}>
                No modules configured for this product.
              </div>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
                <p style={{ margin: "0 0 0.5rem 0", fontSize: "0.8125rem", color: "var(--text-muted)" }}>
                  Select the modules this member is entitled to access. Deselecting all modules is permitted.
                </p>
                {modules.map((m, idx) => {
                  const isChecked = selectedModuleIds.has(m.id);
                  const checkboxId = `${baseId}-mod-${m.id}`;
                  return (
                    <label
                      key={m.id}
                      htmlFor={checkboxId}
                      style={{
                        display: "flex",
                        alignItems: "flex-start",
                        gap: "0.75rem",
                        padding: "0.75rem",
                        borderRadius: "8px",
                        background: isChecked ? "var(--brand-primary-light, rgba(99, 102, 241, 0.08))" : "var(--glass-surface)",
                        border: isChecked ? "1px solid var(--brand-primary)" : "1px solid var(--border-glass)",
                        cursor: "pointer",
                        transition: "all 0.15s ease",
                      }}
                    >
                      <input
                        ref={idx === 0 ? firstCheckboxRef : undefined}
                        id={checkboxId}
                        type="checkbox"
                        checked={isChecked}
                        onChange={() => handleToggleModule(m.id)}
                        disabled={isSubmitting}
                        style={{ marginTop: "0.2rem", width: "16px", height: "16px", cursor: "pointer" }}
                      />
                      <div style={{ display: "flex", flexDirection: "column" }}>
                        <span style={{ fontSize: "0.875rem", fontWeight: 600, color: "var(--text-primary)" }}>
                          {m.name} <span style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>({m.code})</span>
                        </span>
                        {m.description && (
                          <span style={{ fontSize: "0.75rem", color: "var(--text-secondary)", marginTop: "0.15rem" }}>
                            {m.description}
                          </span>
                        )}
                      </div>
                    </label>
                  );
                })}
              </div>
            )}
          </div>

          <div className="dialog-footer" style={{ padding: "1rem 1.5rem" }}>
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
              disabled={isSubmitting || isLoading || Boolean(loadError)}
            >
              {isSubmitting ? "Saving Modules..." : "Save Modules"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
