/**
 * Invite User Dialog (Phase 3C).
 *
 * Provides Platform Owners and Tenant Admins with a modal dialog to issue
 * single-use user invitations with cryptographically hashed tokens,
 * automated email notification triggers, and immediate link generation.
 */

import React, { useId, useRef, useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { invitationsApi } from "../../api/invitations.ts";
import { organizationsApi } from "../../api/organizations.ts";
import type { IssueInvitationResponse, OrganizationListItem } from "../../api/types.ts";
import { ApiError } from "../../api/client.ts";
import {
  AlertCircleIcon,
  CheckCircleIcon,
  CloseIcon,
  CopyIcon,
  UserIcon,
} from "../Icons.tsx";
import { useDialogAccessibility } from "../plans/PlanModalShell.tsx";
import { formatDateTime } from "../../config/dateUtils.ts";

interface InviteUserDialogProps {
  readonly isOpen: boolean;
  readonly onClose: () => void;
  readonly onSuccess?: (invitation: IssueInvitationResponse) => void;
  readonly defaultOrganizationId?: string;
  readonly allowedMembershipTypes?: readonly ("member" | "admin")[];
  readonly triggerRef?: React.RefObject<HTMLElement | null>;
}

export const InviteUserDialog: React.FC<InviteUserDialogProps> = ({
  isOpen,
  onClose,
  onSuccess,
  defaultOrganizationId,
  allowedMembershipTypes,
  triggerRef,
}) => {
  const baseId = useId();
  const navigate = useNavigate();

  const [organizations, setOrganizations] = useState<readonly OrganizationListItem[]>([]);
  const [selectedOrgId, setSelectedOrgId] = useState<string>(defaultOrganizationId || "");
  const [email, setEmail] = useState<string>("");
  const [membershipType, setMembershipType] = useState<string>(
    allowedMembershipTypes && allowedMembershipTypes.length > 0 ? allowedMembershipTypes[0] : "member"
  );

  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  const [generalError, setGeneralError] = useState<string | null>(null);
  const [errorCode, setErrorCode] = useState<string | null>(null);
  const [issuedInvitation, setIssuedInvitation] = useState<IssueInvitationResponse | null>(null);
  const [copied, setCopied] = useState<boolean>(false);

  const emailInputRef = useRef<HTMLInputElement | null>(null);

  const { dialogRef } = useDialogAccessibility({
    isOpen,
    isSubmitting,
    onClose,
    triggerRef,
    initialFocusRef: emailInputRef,
  });

  // Load organizations if not pre-provided
  useEffect(() => {
    if (!isOpen) return;

    if (defaultOrganizationId) {
      setSelectedOrgId(defaultOrganizationId);
    } else {
      void organizationsApi.list({ page_size: 100 }).then((res) => {
        setOrganizations(res.results);
        if (res.results.length > 0 && !selectedOrgId) {
          setSelectedOrgId(res.results[0].id);
        }
      }).catch(() => {
        setGeneralError("Unable to load organizations for invitation.");
      });
    }
  }, [isOpen, defaultOrganizationId, selectedOrgId]);

  if (!isOpen) return null;

  const handleReset = () => {
    setEmail("");
    setMembershipType("member");
    setGeneralError(null);
    setErrorCode(null);
    setIssuedInvitation(null);
    setCopied(false);
  };

  const handleClose = () => {
    handleReset();
    onClose();
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setGeneralError(null);
    setErrorCode(null);

    const trimmedEmail = email.trim();
    if (!trimmedEmail) {
      setGeneralError("Please enter a valid email address.");
      return;
    }

    if (!selectedOrgId) {
      setGeneralError("Please select a target organization.");
      return;
    }

    setIsSubmitting(true);
    try {
      const response = await invitationsApi.issue({
        organization_id: selectedOrgId,
        email: trimmedEmail,
        membership_type: membershipType,
      });
      setIssuedInvitation(response);
      onSuccess?.(response);
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        const data = err.data as { code?: string; detail?: string } | undefined;
        setErrorCode(data?.code || null);
        setGeneralError(data?.detail || err.message || "Failed to issue invitation.");
      } else {
        setGeneralError("An unexpected error occurred while issuing the invitation.");
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  const invitationLink = issuedInvitation?.activation_url || (issuedInvitation?.raw_token
    ? `/invitations/accept/${issuedInvitation.raw_token}`
    : null);

  const handleCopyLink = () => {
    if (invitationLink && typeof navigator !== "undefined" && navigator.clipboard) {
      void navigator.clipboard.writeText(invitationLink);
      setCopied(true);
      setTimeout(() => setCopied(false), 2500);
    }
  };

  const handleNavigateToAccept = () => {
    if (issuedInvitation?.raw_token) {
      handleClose();
      navigate(`/invitations/accept/${issuedInvitation.raw_token}`);
    }
  };

  return (
    <div
      className="dialog-backdrop"
      onClick={(e) => {
        if (e.target === e.currentTarget && !isSubmitting) {
          handleClose();
        }
      }}
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={`${baseId}-title`}
        className="dialog-surface"
        style={{
          maxWidth: "34rem",
          maxHeight: "min(90dvh, 700px)",
        }}
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
                Invite New User
              </h2>
              <p id={`${baseId}-desc`} className="dialog-subtitle">
                Issue a secure, single-use activation invitation
              </p>
            </div>
          </div>
          <button
            type="button"
            className="dialog-close-btn"
            onClick={handleClose}
            disabled={isSubmitting}
            aria-label="Close dialog"
          >
            <CloseIcon size={18} />
          </button>
        </div>

        {/* Content */}
        {issuedInvitation ? (
          <div className="dialog-body" style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>
            <div
              style={{
                padding: "1rem",
                borderRadius: "8px",
                background: "rgba(16, 185, 129, 0.1)",
                border: "1px solid rgba(16, 185, 129, 0.25)",
                display: "flex",
                alignItems: "flex-start",
                gap: "0.75rem",
              }}
            >
              <CheckCircleIcon size={20} style={{ color: "rgb(16, 185, 129)", flexShrink: 0, marginTop: "0.15rem" }} />
              <div>
                <h4 style={{ margin: "0 0 0.25rem 0", color: "var(--text-primary)", fontSize: "0.9375rem" }}>
                  Invitation Issued Successfully
                </h4>
                <p style={{ margin: 0, fontSize: "0.8125rem", color: "var(--text-secondary)", lineHeight: 1.5 }}>
                  An activation notification has been queued for dispatch to <strong>{issuedInvitation.email}</strong>.
                  The single-use activation link is valid until {formatDateTime(issuedInvitation.expires_at)}.
                </p>
              </div>
            </div>

            {invitationLink && (
              <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                  <label style={{ fontSize: "0.8125rem", fontWeight: 600, color: "var(--text-primary)" }}>
                    One-Time Activation Link (Fallback)
                  </label>
                  <span style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
                    Bearer secret · Shown once
                  </span>
                </div>
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: "0.5rem",
                    padding: "0.5rem 0.75rem",
                    background: "var(--bg-app)",
                    border: "1px solid var(--border-glass)",
                    borderRadius: "6px",
                    fontFamily: "monospace",
                    fontSize: "0.8125rem",
                    overflowX: "auto",
                  }}
                >
                  <span style={{ flex: 1, wordBreak: "break-all" }}>{invitationLink}</span>
                  <button
                    type="button"
                    className="btn btn-secondary btn-sm"
                    onClick={handleCopyLink}
                    style={{ display: "inline-flex", alignItems: "center", gap: "0.35rem" }}
                  >
                    <CopyIcon size={14} />
                    <span>{copied ? "Copied" : "Copy"}</span>
                  </button>
                </div>
              </div>
            )}

            <div className="dialog-footer" style={{ borderTop: "none", padding: 0, marginTop: "0.5rem" }}>
              <button type="button" className="btn btn-secondary" onClick={handleClose}>
                Done
              </button>
              {issuedInvitation?.raw_token && (
                <button type="button" className="btn btn-primary" onClick={handleNavigateToAccept}>
                  Go to Activation Page
                </button>
              )}
            </div>
          </div>
        ) : (
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
                  style={{ marginBottom: "0.75rem" }}
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

              <div
                style={{
                  padding: "0.75rem 1rem",
                  borderRadius: "0.5rem",
                  backgroundColor: "var(--brand-primary-light)",
                  border: "1px solid var(--border-glass)",
                  color: "var(--text-secondary)",
                  fontSize: "0.8125rem",
                  lineHeight: 1.5,
                  marginBottom: "1rem",
                }}
              >
                Secure invitation flow creates a single-use SHA-256 hashed activation token and triggers the notification service for delivery.
              </div>

              <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
                {!defaultOrganizationId && (
                  <div>
                    <label
                      htmlFor={`${baseId}-org`}
                      style={{
                        display: "block",
                        fontSize: "0.875rem",
                        fontWeight: 500,
                        marginBottom: "0.375rem",
                        color: "var(--text-primary)",
                      }}
                    >
                      Target Organization <span style={{ color: "var(--status-danger)" }}>*</span>
                    </label>
                    <select
                      id={`${baseId}-org`}
                      className="registry-filter-select"
                      style={{ width: "100%", height: "2.5rem" }}
                      value={selectedOrgId}
                      onChange={(e) => setSelectedOrgId(e.target.value)}
                      required
                    >
                      <option value="">Select Organization...</option>
                      {organizations.map((org) => (
                        <option key={org.id} value={org.id}>
                          {org.name} ({org.code})
                        </option>
                      ))}
                    </select>
                  </div>
                )}

                <div>
                  <label
                    htmlFor={`${baseId}-email`}
                    style={{
                      display: "block",
                      fontSize: "0.875rem",
                      fontWeight: 500,
                      marginBottom: "0.375rem",
                      color: "var(--text-primary)",
                    }}
                  >
                    Invitee Email Address <span style={{ color: "var(--status-danger)" }}>*</span>
                  </label>
                  <input
                    ref={emailInputRef}
                    id={`${baseId}-email`}
                    type="email"
                    className="form-input"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="colleague@organization.com"
                    required
                    disabled={isSubmitting}
                    style={{ width: "100%" }}
                  />
                </div>

                <div>
                  <label
                    htmlFor={`${baseId}-membership`}
                    style={{
                      display: "block",
                      fontSize: "0.875rem",
                      fontWeight: 500,
                      marginBottom: "0.375rem",
                      color: "var(--text-primary)",
                    }}
                  >
                    Membership Type
                  </label>
                  <select
                    id={`${baseId}-membership`}
                    className="registry-filter-select"
                    style={{ width: "100%", height: "2.5rem" }}
                    value={membershipType}
                    onChange={(e) => setMembershipType(e.target.value)}
                    disabled={isSubmitting || (allowedMembershipTypes !== undefined && allowedMembershipTypes.length <= 1)}
                  >
                    {(!allowedMembershipTypes || allowedMembershipTypes.includes("member")) && (
                      <option value="member">Standard Member</option>
                    )}
                    {(!allowedMembershipTypes || allowedMembershipTypes.includes("admin")) && (
                      <option value="admin">Tenant Administrator</option>
                    )}
                  </select>
                </div>
              </div>
            </div>

            <div className="dialog-footer">
              <button
                type="button"
                className="btn btn-secondary"
                onClick={handleClose}
                disabled={isSubmitting}
              >
                Cancel
              </button>
              <button
                type="submit"
                className="btn btn-primary"
                disabled={isSubmitting || !email.trim() || !selectedOrgId}
              >
                {isSubmitting ? "Issuing Invitation..." : "Issue Invitation"}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
};
