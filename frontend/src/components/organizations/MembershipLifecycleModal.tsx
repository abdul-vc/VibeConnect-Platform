/**
 * Membership Lifecycle Confirmation Modal (Phase 2D Stage 5).
 *
 * Handles role mutation (member <-> tenant_admin) and lifecycle actions:
 * Suspend, Reactivate, End, and Restore with explicit confirmation and API error display.
 */

import React, { useId, useRef, useState } from "react";
import { membershipsApi } from "../../api/memberships.ts";
import type {
  MembershipType,
  OrganizationMembershipItem,
} from "../../api/types.ts";
import { ApiError } from "../../api/client.ts";
import { AlertCircleIcon, CloseIcon } from "../Icons.tsx";
import { useDialogAccessibility } from "../plans/PlanModalShell.tsx";

export type MembershipActionType =
  | "change_role"
  | "suspend"
  | "reactivate"
  | "end"
  | "restore";

interface MembershipLifecycleModalProps {
  readonly isOpen: boolean;
  readonly onClose: () => void;
  readonly onSuccess: (updated: OrganizationMembershipItem) => void;
  readonly membership: OrganizationMembershipItem | null;
  readonly action: MembershipActionType | null;
  readonly organizationId: string;
  readonly triggerRef?: React.RefObject<HTMLElement | null>;
}

export const MembershipLifecycleModal: React.FC<MembershipLifecycleModalProps> = ({
  isOpen,
  onClose,
  onSuccess,
  membership,
  action,
  organizationId,
  triggerRef,
}) => {
  const baseId = useId();
  const [newRole, setNewRole] = useState<MembershipType>("member");
  const [reason, setReason] = useState<string>("");
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  const [generalError, setGeneralError] = useState<string | null>(null);
  const [errorCode, setErrorCode] = useState<string | null>(null);

  const confirmButtonRef = useRef<HTMLButtonElement | null>(null);

  const { dialogRef } = useDialogAccessibility({
    isOpen,
    isSubmitting,
    onClose,
    triggerRef,
    initialFocusRef: confirmButtonRef,
  });

  if (!isOpen || !membership || !action) return null;

  const getActionConfig = () => {
    const userEmail = membership.user?.email || "this user";
    switch (action) {
      case "change_role":
        return {
          title: "Change Membership Role",
          description: `Update the membership role for ${userEmail}.`,
          buttonText: "Update Role",
          buttonClass: "btn btn-primary",
          showRoleSelect: true,
          showReason: false,
        };
      case "suspend":
        return {
          title: "Suspend Organization Membership",
          description: `Are you sure you want to suspend membership for ${userEmail}? The user will immediately lose access to this organization.`,
          buttonText: "Suspend Membership",
          buttonClass: "btn btn-danger",
          showRoleSelect: false,
          showReason: true,
        };
      case "reactivate":
        return {
          title: "Reactivate Organization Membership",
          description: `Are you sure you want to reactivate membership for ${userEmail}? The user will regain access to this organization.`,
          buttonText: "Reactivate Membership",
          buttonClass: "btn btn-success",
          showRoleSelect: false,
          showReason: false,
        };
      case "end":
        return {
          title: "End Organization Membership",
          description: `Are you sure you want to end membership for ${userEmail}? This will terminate their active membership and record the termination timestamp.`,
          buttonText: "End Membership",
          buttonClass: "btn btn-danger",
          showRoleSelect: false,
          showReason: true,
        };
      case "restore":
        return {
          title: "Restore Ended Membership",
          description: `Are you sure you want to restore the ended membership for ${userEmail}? The prior joined and ended timestamps will be preserved in the audit log, and the membership will return to active status.`,
          buttonText: "Restore Membership",
          buttonClass: "btn btn-success",
          showRoleSelect: false,
          showReason: false,
        };
    }
  };

  const config = getActionConfig();

  const handleConfirm = async (e: React.FormEvent) => {
    e.preventDefault();
    setGeneralError(null);
    setErrorCode(null);
    setIsSubmitting(true);

    try {
      let updated: OrganizationMembershipItem;
      if (action === "change_role") {
        updated = await membershipsApi.updateType(organizationId, membership.id, {
          membership_type: newRole,
        });
      } else if (action === "suspend") {
        updated = await membershipsApi.suspend(organizationId, membership.id, {
          reason: reason.trim() || undefined,
        });
      } else if (action === "reactivate") {
        updated = await membershipsApi.reactivate(organizationId, membership.id);
      } else if (action === "end") {
        updated = await membershipsApi.end(organizationId, membership.id, {
          reason: reason.trim() || undefined,
        });
      } else {
        updated = await membershipsApi.restore(organizationId, membership.id);
      }
      setReason("");
      onSuccess(updated);
      onClose();
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        const data = err.data as { code?: string; detail?: string; message?: string } | undefined;
        setErrorCode(data?.code || null);
        setGeneralError(data?.detail || data?.message || err.message || `Failed to perform ${action}.`);
      } else {
        setGeneralError("An unexpected error occurred.");
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div
      className="dialog-backdrop"
      onClick={(e) => {
        if (e.target === e.currentTarget && !isSubmitting) {
          onClose();
        }
      }}
      style={{
        padding: "0.5rem",
        boxSizing: "border-box",
        overflowX: "hidden",
      }}
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={`${baseId}-title`}
        aria-describedby={`${baseId}-desc`}
        className="dialog-surface"
        style={{
          width: "100%",
          maxWidth: "30rem",
          minWidth: 0,
          margin: "auto",
          boxSizing: "border-box",
          overflowX: "hidden",
          maxHeight: "calc(100dvh - 1rem)",
        }}
      >
        {/* Header */}
        <div
          className="dialog-header"
          style={{
            minWidth: 0,
            boxSizing: "border-box",
            gap: "0.75rem",
          }}
        >
          <h2
            id={`${baseId}-title`}
            className="dialog-title"
            style={{
              minWidth: 0,
              flex: 1,
              overflowWrap: "anywhere",
              wordBreak: "break-word",
            }}
          >
            {config.title}
          </h2>
          <button
            type="button"
            className="dialog-close-btn"
            onClick={onClose}
            disabled={isSubmitting}
            aria-label="Close dialog"
            style={{ flexShrink: 0 }}
          >
            <CloseIcon size={18} />
          </button>
        </div>

        <form
          onSubmit={handleConfirm}
          style={{
            display: "flex",
            flexDirection: "column",
            flex: 1,
            minHeight: 0,
            minWidth: 0,
            overflow: "hidden",
            boxSizing: "border-box",
            width: "100%",
          }}
        >
          <div
            className="dialog-body"
            style={{
              minWidth: 0,
              boxSizing: "border-box",
              overflowX: "hidden",
              overflowY: "auto",
              wordBreak: "break-word",
              overflowWrap: "anywhere",
            }}
          >
            {generalError && (
              <div
                className="alert-banner alert-banner-error"
                role="alert"
                style={{
                  marginBottom: "1rem",
                  minWidth: 0,
                  boxSizing: "border-box",
                  alignItems: "flex-start",
                  overflowWrap: "anywhere",
                  wordBreak: "break-word",
                }}
              >
                <AlertCircleIcon size={18} style={{ flexShrink: 0, marginTop: "2px" }} />
                <div
                  style={{
                    minWidth: 0,
                    flex: 1,
                    overflowWrap: "anywhere",
                    wordBreak: "break-word",
                  }}
                >
                  {errorCode && (
                    <div
                      style={{
                        fontWeight: 600,
                        fontSize: "0.75rem",
                        marginBottom: "0.25rem",
                        overflowWrap: "anywhere",
                        wordBreak: "break-word",
                      }}
                    >
                      Error Code: {errorCode}
                    </div>
                  )}
                  <div
                    style={{
                      overflowWrap: "anywhere",
                      wordBreak: "break-word",
                      lineHeight: 1.45,
                    }}
                  >
                    {generalError}
                  </div>
                </div>
              </div>
            )}

            <p
              id={`${baseId}-desc`}
              style={{
                margin: "0 0 1.25rem 0",
                fontSize: "0.9375rem",
                color: "var(--text-secondary)",
                lineHeight: 1.5,
                minWidth: 0,
                overflowWrap: "anywhere",
                wordBreak: "break-word",
              }}
            >
              {config.description}
            </p>

            {config.showRoleSelect && (
              <div style={{ marginBottom: "1.25rem", minWidth: 0 }}>
                <label
                  htmlFor={`${baseId}-newRole`}
                  style={{
                    display: "block",
                    fontSize: "0.875rem",
                    fontWeight: 500,
                    marginBottom: "0.375rem",
                    color: "var(--text-primary)",
                  }}
                >
                  Select New Role <span style={{ color: "var(--status-danger)" }}>*</span>
                </label>
                <select
                  id={`${baseId}-newRole`}
                  value={newRole}
                  onChange={(e) => setNewRole(e.target.value as MembershipType)}
                  disabled={isSubmitting}
                  style={{
                    width: "100%",
                    minWidth: 0,
                    maxWidth: "100%",
                    padding: "0.625rem 0.75rem",
                    borderRadius: "0.375rem",
                    border: "1px solid var(--input-border)",
                    backgroundColor: "var(--input-bg)",
                    color: "var(--text-primary)",
                    fontSize: "0.875rem",
                    boxSizing: "border-box",
                  }}
                >
                  <option value="member">Standard Member</option>
                  <option value="tenant_admin">Tenant Administrator</option>
                </select>
              </div>
            )}

            {config.showReason && (
              <div style={{ marginBottom: "1.25rem", minWidth: 0 }}>
                <label
                  htmlFor={`${baseId}-reason`}
                  style={{
                    display: "block",
                    fontSize: "0.875rem",
                    fontWeight: 500,
                    marginBottom: "0.375rem",
                    color: "var(--text-primary)",
                  }}
                >
                  Reason (Optional)
                </label>
                <input
                  id={`${baseId}-reason`}
                  type="text"
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                  placeholder="Reason for audit log"
                  disabled={isSubmitting}
                  style={{
                    width: "100%",
                    minWidth: 0,
                    maxWidth: "100%",
                    padding: "0.625rem 0.75rem",
                    borderRadius: "0.375rem",
                    border: "1px solid var(--input-border)",
                    backgroundColor: "var(--input-bg)",
                    color: "var(--text-primary)",
                    fontSize: "0.875rem",
                    boxSizing: "border-box",
                  }}
                />
              </div>
            )}
          </div>

          {/* Actions Footer */}
          <div
            className="dialog-footer"
            style={{
              minWidth: 0,
              boxSizing: "border-box",
              width: "100%",
            }}
          >
            <button
              type="button"
              className="btn btn-secondary"
              onClick={onClose}
              disabled={isSubmitting}
            >
              Cancel
            </button>
            <button
              ref={confirmButtonRef}
              type="submit"
              className={config.buttonClass}
              disabled={isSubmitting}
            >
              {isSubmitting ? "Processing..." : config.buttonText}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

