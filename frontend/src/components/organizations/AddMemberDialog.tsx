/**
 * Add Organization Member Dialog (Phase 2D Stage 5).
 *
 * Platform Owner dialog to grant an active user membership in an organization.
 * Supports role selection (member vs tenant_admin) and surfaces conflict errors.
 */

import React, { useEffect, useId, useRef, useState } from "react";
import { membershipsApi } from "../../api/memberships.ts";
import { usersApi } from "../../api/users.ts";
import type {
  MembershipType,
  OrganizationMembershipItem,
  UserListItem,
} from "../../api/types.ts";
import { ApiError } from "../../api/client.ts";
import { AlertCircleIcon, CloseIcon, UserIcon } from "../Icons.tsx";
import { useDialogAccessibility } from "../plans/PlanModalShell.tsx";

interface AddMemberDialogProps {
  readonly isOpen: boolean;
  readonly onClose: () => void;
  readonly onSuccess: (membership: OrganizationMembershipItem) => void;
  readonly organizationId: string;
  readonly organizationName: string;
  readonly triggerRef?: React.RefObject<HTMLElement | null>;
}

export const AddMemberDialog: React.FC<AddMemberDialogProps> = ({
  isOpen,
  onClose,
  onSuccess,
  organizationId,
  organizationName,
  triggerRef,
}) => {
  const baseId = useId();
  const [users, setUsers] = useState<UserListItem[]>([]);
  const [selectedUserId, setSelectedUserId] = useState<string>("");
  const [customUserId, setCustomUserId] = useState<string>("");
  const [useCustomId, setUseCustomId] = useState<boolean>(false);
  const [membershipType, setMembershipType] = useState<MembershipType>("member");

  const [isLoadingUsers, setIsLoadingUsers] = useState<boolean>(false);
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  const [generalError, setGeneralError] = useState<string | null>(null);
  const [errorCode, setErrorCode] = useState<string | null>(null);

  const selectRef = useRef<HTMLSelectElement | null>(null);

  const { dialogRef } = useDialogAccessibility({
    isOpen,
    isSubmitting,
    onClose,
    triggerRef,
    initialFocusRef: selectRef,
  });

  // Load available active users on open
  useEffect(() => {
    if (isOpen) {
      setGeneralError(null);
      setErrorCode(null);
      setSelectedUserId("");
      setCustomUserId("");
      setUseCustomId(false);
      setMembershipType("member");

      const loadUsers = async () => {
        setIsLoadingUsers(true);
        try {
          const res = await usersApi.list({ status: "active", page_size: 100 });
          setUsers(res.results as UserListItem[]);
          if (res.results.length > 0) {
            setSelectedUserId(res.results[0].id);
          }
        } catch {
          // If list fails, fallback to manual UUID entry
          setUseCustomId(true);
        } finally {
          setIsLoadingUsers(false);
        }
      };

      loadUsers();
    }
  }, [isOpen]);

  if (!isOpen) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setGeneralError(null);
    setErrorCode(null);

    const targetUserId = useCustomId ? customUserId.trim() : selectedUserId;
    if (!targetUserId) {
      setGeneralError("Please select or specify a valid user.");
      return;
    }

    setIsSubmitting(true);
    try {
      const membership = await membershipsApi.create(organizationId, {
        user_id: targetUserId,
        membership_type: membershipType,
      });
      onSuccess(membership);
      onClose();
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        const data = err.data as { code?: string; detail?: string } | undefined;
        setErrorCode(data?.code || null);
        setGeneralError(data?.detail || err.message || "Failed to add member to organization.");
      } else {
        setGeneralError("An unexpected error occurred while adding the member.");
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
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={`${baseId}-title`}
        aria-describedby={`${baseId}-desc`}
        className="dialog-surface"
        style={{ maxWidth: "32rem" }}
      >
        {/* Header */}
        <div className="dialog-header">
          <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
            <div
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                width: "2.25rem",
                height: "2.25rem",
                borderRadius: "0.5rem",
                backgroundColor: "var(--color-primary-subtle)",
                color: "var(--color-primary)",
              }}
            >
              <UserIcon size={20} />
            </div>
            <div>
              <h2 id={`${baseId}-title`} className="dialog-title">
                Add Organization Member
              </h2>
              <p id={`${baseId}-desc`} className="dialog-subtitle">
                Assign an active user to {organizationName}
              </p>
            </div>
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

        {/* Form Body */}
        <form
          onSubmit={handleSubmit}
          style={{
            display: "flex",
            flexDirection: "column",
            flex: 1,
            minHeight: 0,
            overflow: "hidden",
          }}
        >
          <div className="dialog-body">
            {generalError && (
              <div
                className="alert-banner alert-banner-error"
                role="alert"
                style={{ marginBottom: "0.5rem" }}
              >
                <AlertCircleIcon size={18} />
                <div>
                  {errorCode && (
                    <div style={{ fontWeight: 600, fontSize: "0.75rem", marginBottom: "0.25rem" }}>
                      Error Code: {errorCode}
                    </div>
                  )}
                  <div>{generalError}</div>
                </div>
              </div>
            )}

          <div style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>
            {/* User Selection */}
            <div>
              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  marginBottom: "0.375rem",
                }}
              >
                <label
                  htmlFor={useCustomId ? `${baseId}-customUserId` : `${baseId}-userId`}
                  style={{
                    fontSize: "0.875rem",
                    fontWeight: 500,
                    color: "var(--text-primary)",
                  }}
                >
                  Platform User <span style={{ color: "var(--status-danger)" }}>*</span>
                </label>
                <button
                  type="button"
                  onClick={() => setUseCustomId(!useCustomId)}
                  style={{
                    background: "none",
                    border: "none",
                    color: "var(--color-primary)",
                    fontSize: "0.75rem",
                    cursor: "pointer",
                    padding: 0,
                  }}
                >
                  {useCustomId ? "Select from list" : "Enter User UUID"}
                </button>
              </div>

              {useCustomId ? (
                <input
                  id={`${baseId}-customUserId`}
                  type="text"
                  required
                  value={customUserId}
                  onChange={(e) => setCustomUserId(e.target.value)}
                  placeholder="e.g. 123e4567-e89b-12d3-a456-426614174000"
                  disabled={isSubmitting}
                  style={{
                    width: "100%",
                    padding: "0.625rem 0.75rem",
                    borderRadius: "0.375rem",
                    border: "1px solid var(--input-border)",
                    backgroundColor: "var(--input-bg)",
                    color: "var(--text-primary)",
                    fontSize: "0.875rem",
                    boxSizing: "border-box",
                  }}
                />
              ) : (
                <select
                  ref={selectRef}
                  id={`${baseId}-userId`}
                  required
                  value={selectedUserId}
                  onChange={(e) => setSelectedUserId(e.target.value)}
                  disabled={isSubmitting || isLoadingUsers}
                  style={{
                    width: "100%",
                    padding: "0.625rem 0.75rem",
                    borderRadius: "0.375rem",
                    border: "1px solid var(--input-border)",
                    backgroundColor: "var(--input-bg)",
                    color: "var(--text-primary)",
                    fontSize: "0.875rem",
                    boxSizing: "border-box",
                  }}
                >
                  {isLoadingUsers ? (
                    <option value="">Loading users...</option>
                  ) : users.length === 0 ? (
                    <option value="">No active users available</option>
                  ) : (
                    users.map((u) => (
                      <option key={u.id} value={u.id}>
                        {u.email} {u.full_name ? `(${u.full_name})` : ""}
                      </option>
                    ))
                  )}
                </select>
              )}
            </div>

            {/* Role / Membership Type */}
            <div>
              <label
                htmlFor={`${baseId}-membershipType`}
                style={{
                  display: "block",
                  fontSize: "0.875rem",
                  fontWeight: 500,
                  marginBottom: "0.375rem",
                  color: "var(--text-primary)",
                }}
              >
                Membership Role <span style={{ color: "var(--status-danger)" }}>*</span>
              </label>
              <select
                id={`${baseId}-membershipType`}
                value={membershipType}
                onChange={(e) => setMembershipType(e.target.value as MembershipType)}
                disabled={isSubmitting}
                style={{
                  width: "100%",
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
              <div
                style={{
                  fontSize: "0.8125rem",
                  color: "var(--text-secondary)",
                  marginTop: "0.375rem",
                }}
              >
                {membershipType === "tenant_admin"
                  ? "Tenant Administrators can access the Tenant Admin Console and manage organization users."
                  : "Standard Members can operate tenant product features without administrative access."}
              </div>
            </div>
          </div>
        </div>

        {/* Actions Footer */}
        <div className="dialog-footer">
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
            disabled={isSubmitting || (!selectedUserId && !customUserId.trim())}
          >
            {isSubmitting ? "Adding..." : "Add Member"}
          </button>
        </div>
      </form>
      </div>
    </div>
  );
};
