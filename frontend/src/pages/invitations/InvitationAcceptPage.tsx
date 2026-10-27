/**
 * Phase 3C: User Invitation Acceptance and Password Setup Page.
 *
 * Provides single-use token verification, state-driven rendering (valid, expired,
 * already used, revoked), password policy enforcement, and atomic account activation.
 */

import React, { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { invitationsApi } from "../../api/invitations.ts";
import type { InvitationValidateResponse } from "../../api/types.ts";
import {
  AlertCircleIcon,
  CheckCircleIcon,
  LockIcon,
  ShieldCheckIcon,
  UserIcon,
} from "../../components/Icons.tsx";

type PageState =
  | "loading"
  | "valid"
  | "expired"
  | "already_used"
  | "revoked"
  | "invalid"
  | "success";

export const InvitationAcceptPage: React.FC = () => {
  const { token } = useParams<{ token: string }>();
  const navigate = useNavigate();

  const [pageState, setPageState] = useState<PageState>("loading");
  const [invitationData, setInvitationData] = useState<InvitationValidateResponse | null>(null);
  const [errorMessage, setErrorMessage] = useState<string>("");

  // Form inputs
  const [fullName, setFullName] = useState<string>("");
  const [password, setPassword] = useState<string>("");
  const [confirmPassword, setConfirmPassword] = useState<string>("");

  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  const [formError, setFormError] = useState<string | null>(null);

  useEffect(() => {
    if (!token) {
      setPageState("invalid");
      setErrorMessage("No invitation token provided.");
      return;
    }

    const abortController = new AbortController();

    const validateToken = async () => {
      setPageState("loading");
      setErrorMessage("");

      try {
        const data = await invitationsApi.validate(token, abortController.signal);
        setInvitationData(data);
        setPageState("valid");
      } catch (err: unknown) {
        const errorObj = err as {
          status?: number;
          data?: { code?: string; detail?: string };
        };
        const code = errorObj?.data?.code;
        const detail = errorObj?.data?.detail;

        if (code === "INVITATION_ALREADY_USED" || errorObj?.status === 409) {
          setPageState("already_used");
          setErrorMessage(detail || "This invitation has already been accepted.");
        } else if (code === "INVITATION_EXPIRED" || errorObj?.status === 410) {
          setPageState("expired");
          setErrorMessage(detail || "This invitation has expired.");
        } else if (code === "INVITATION_REVOKED") {
          setPageState("revoked");
          setErrorMessage(detail || "This invitation has been revoked.");
        } else {
          setPageState("invalid");
          setErrorMessage(detail || "Invalid or unrecognized invitation link.");
        }
      }
    };

    void validateToken();

    return () => abortController.abort();
  }, [token]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!token) return;

    if (password.length < 8) {
      setFormError("Password must be at least 8 characters long.");
      return;
    }
    if (password !== confirmPassword) {
      setFormError("Passwords do not match.");
      return;
    }

    setIsSubmitting(true);
    setFormError(null);

    try {
      await invitationsApi.accept(token, {
        password,
        full_name: fullName.trim() || undefined,
      });
      setPageState("success");
    } catch (err: unknown) {
      const errorObj = err as {
        status?: number;
        data?: { code?: string; detail?: string };
      };
      setFormError(errorObj?.data?.detail || "Failed to set password. Please try again.");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div
      style={{
        minHeight: "100vh",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: "2rem 1rem",
        background: "var(--bg-app)",
      }}
    >
      <div
        className="glass-panel-elevated"
        style={{
          width: "100%",
          maxWidth: "480px",
          padding: "2.5rem",
          borderRadius: "1rem",
          background: "var(--glass-surface-elevated)",
          border: "1px solid var(--border-glass)",
          boxShadow: "var(--shadow-lg)",
        }}
      >
        {/* Brand Header */}
        <div style={{ textAlign: "center", marginBottom: "2rem" }}>
          <div
            style={{
              display: "inline-flex",
              alignItems: "center",
              justifyContent: "center",
              width: "48px",
              height: "48px",
              borderRadius: "0.75rem",
              background: "var(--surface-soft-lavender)",
              color: "var(--brand-primary)",
              border: "1px solid rgba(56, 103, 245, 0.2)",
              marginBottom: "1rem",
            }}
          >
            <ShieldCheckIcon size={28} />
          </div>
          <h1 className="heading-title" style={{ fontSize: "1.5rem", margin: 0 }}>
            Envisage Workspace
          </h1>
          <p className="text-secondary" style={{ fontSize: "0.875rem", marginTop: "0.35rem" }}>
            Accept Invitation & Setup Password
          </p>
        </div>

        {/* State: Loading */}
        {pageState === "loading" && (
          <div style={{ textAlign: "center", padding: "2rem 0", color: "var(--text-secondary)" }}>
            <p>Validating invitation token...</p>
          </div>
        )}

        {/* State: Already Used */}
        {pageState === "already_used" && (
          <div style={{ textAlign: "center", display: "flex", flexDirection: "column", gap: "1rem" }}>
            <div style={{ color: "var(--status-warning, #f59e0b)", display: "flex", justifyContent: "center" }}>
              <AlertCircleIcon size={44} />
            </div>
            <h2 style={{ fontSize: "1.25rem", margin: 0, color: "var(--text-primary)" }}>
              Invitation Already Accepted
            </h2>
            <p className="text-body" style={{ fontSize: "0.875rem" }}>
              {errorMessage || "This invitation has already been accepted. You can log in using your existing account."}
            </p>
            <Link to="/login" className="btn btn-primary" style={{ marginTop: "0.5rem", textDecoration: "none" }}>
              Go to Login
            </Link>
          </div>
        )}

        {/* State: Expired */}
        {pageState === "expired" && (
          <div style={{ textAlign: "center", display: "flex", flexDirection: "column", gap: "1rem" }}>
            <div style={{ color: "var(--status-error, #ef4444)", display: "flex", justifyContent: "center" }}>
              <AlertCircleIcon size={44} />
            </div>
            <h2 style={{ fontSize: "1.25rem", margin: 0, color: "var(--text-primary)" }}>
              Invitation Expired
            </h2>
            <p className="text-body" style={{ fontSize: "0.875rem" }}>
              {errorMessage || "This invitation link has expired. Please contact your organization administrator to request a new invitation."}
            </p>
            <Link to="/login" className="btn btn-secondary" style={{ marginTop: "0.5rem", textDecoration: "none" }}>
              Return to Login
            </Link>
          </div>
        )}

        {/* State: Revoked / Invalid */}
        {(pageState === "revoked" || pageState === "invalid") && (
          <div style={{ textAlign: "center", display: "flex", flexDirection: "column", gap: "1rem" }}>
            <div style={{ color: "var(--status-error, #ef4444)", display: "flex", justifyContent: "center" }}>
              <AlertCircleIcon size={44} />
            </div>
            <h2 style={{ fontSize: "1.25rem", margin: 0, color: "var(--text-primary)" }}>
              Invalid Invitation Link
            </h2>
            <p className="text-body" style={{ fontSize: "0.875rem" }}>
              {errorMessage || "The invitation link is invalid or no longer active. Please check the URL and try again."}
            </p>
            <Link to="/login" className="btn btn-secondary" style={{ marginTop: "0.5rem", textDecoration: "none" }}>
              Return to Login
            </Link>
          </div>
        )}

        {/* State: Success */}
        {pageState === "success" && (
          <div style={{ textAlign: "center", display: "flex", flexDirection: "column", gap: "1rem" }}>
            <div style={{ color: "var(--status-success, #10b981)", display: "flex", justifyContent: "center" }}>
              <CheckCircleIcon size={48} />
            </div>
            <h2 style={{ fontSize: "1.35rem", margin: 0, color: "var(--text-primary)" }}>
              Account Activated!
            </h2>
            <p className="text-body" style={{ fontSize: "0.875rem" }}>
              Your password has been successfully configured and your organization access is active.
            </p>
            <button
              type="button"
              className="btn btn-primary"
              onClick={() => navigate("/login")}
              style={{ marginTop: "0.5rem" }}
            >
              Sign In to Your Account
            </button>
          </div>
        )}

        {/* State: Valid Form */}
        {pageState === "valid" && (
          <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>
            {/* Invitation Details Banner */}
            <div
              style={{
                padding: "0.875rem",
                borderRadius: "0.5rem",
                background: "var(--surface-soft-lavender)",
                border: "1px solid rgba(56, 103, 245, 0.2)",
                fontSize: "0.8125rem",
              }}
            >
              <div style={{ color: "var(--text-secondary)", marginBottom: "0.25rem" }}>
                Invited to: <strong>{invitationData?.organization_name}</strong> (<code>{invitationData?.organization_code}</code>)
              </div>
              <div style={{ color: "var(--text-secondary)" }}>
                Email: <strong>{invitationData?.email}</strong>
              </div>
            </div>

            {formError && (
              <div
                className="alert-banner alert-banner-error"
                role="alert"
                style={{ display: "flex", alignItems: "center", gap: "0.5rem", fontSize: "0.8125rem" }}
              >
                <AlertCircleIcon size={16} />
                <span>{formError}</span>
              </div>
            )}

            {/* Full Name */}
            <div>
              <label htmlFor="fullName" className="field-label" style={{ display: "block", marginBottom: "0.35rem" }}>
                Full Name
              </label>
              <div style={{ position: "relative" }}>
                <span
                  style={{
                    position: "absolute",
                    left: "0.75rem",
                    top: "50%",
                    transform: "translateY(-50%)",
                    color: "var(--text-muted)",
                  }}
                >
                  <UserIcon size={16} />
                </span>
                <input
                  id="fullName"
                  type="text"
                  className="input-field"
                  placeholder="e.g. Jane Doe"
                  value={fullName}
                  onChange={(e) => setFullName(e.target.value)}
                  style={{ paddingLeft: "2.25rem", width: "100%" }}
                  autoComplete="name"
                />
              </div>
            </div>

            {/* Password */}
            <div>
              <label htmlFor="password" className="field-label" style={{ display: "block", marginBottom: "0.35rem" }}>
                Choose Password <span style={{ color: "var(--status-error)" }}>*</span>
              </label>
              <div style={{ position: "relative" }}>
                <span
                  style={{
                    position: "absolute",
                    left: "0.75rem",
                    top: "50%",
                    transform: "translateY(-50%)",
                    color: "var(--text-muted)",
                  }}
                >
                  <LockIcon size={16} />
                </span>
                <input
                  id="password"
                  type="password"
                  required
                  className="input-field"
                  placeholder="At least 8 characters"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  style={{ paddingLeft: "2.25rem", width: "100%" }}
                  autoComplete="new-password"
                />
              </div>
            </div>

            {/* Confirm Password */}
            <div>
              <label htmlFor="confirmPassword" className="field-label" style={{ display: "block", marginBottom: "0.35rem" }}>
                Confirm Password <span style={{ color: "var(--status-error)" }}>*</span>
              </label>
              <div style={{ position: "relative" }}>
                <span
                  style={{
                    position: "absolute",
                    left: "0.75rem",
                    top: "50%",
                    transform: "translateY(-50%)",
                    color: "var(--text-muted)",
                  }}
                >
                  <LockIcon size={16} />
                </span>
                <input
                  id="confirmPassword"
                  type="password"
                  required
                  className="input-field"
                  placeholder="Re-enter password"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  style={{ paddingLeft: "2.25rem", width: "100%" }}
                  autoComplete="new-password"
                />
              </div>
            </div>

            <button
              type="submit"
              className="btn btn-primary"
              disabled={isSubmitting}
              style={{ marginTop: "0.5rem", width: "100%" }}
            >
              {isSubmitting ? "Activating Account..." : "Set Password & Join Organization"}
            </button>
          </form>
        )}
      </div>
    </div>
  );
};
