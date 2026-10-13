/**
 * Platform Owner Central User Detail Page (Phase 2D Stage 5).
 *
 * Displays detailed user profile attributes, permits updating allowed profile fields (full_name),
 * and provides direct lifecycle action controls (Suspend, Reactivate, Disable).
 */

import React, { useCallback, useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { usersApi } from "../../api/users.ts";
import type { UserDetail, UserStatus } from "../../api/types.ts";
import { ApiError } from "../../api/client.ts";
import { AppShell } from "../../components/AppShell.tsx";
import { formatDateTime } from "../../config/dateUtils.ts";
import { CatalogHierarchyNav } from "../../components/catalog/CatalogHierarchyNav.tsx";
import { ShieldCheckIcon, UserIcon } from "../../components/Icons.tsx";
import { LoadingSpinner } from "../../components/LoadingSpinner.tsx";
import {
  UserLifecycleAction,
  UserLifecycleModal,
} from "../../components/users/UserLifecycleModal.tsx";

export const CentralUserDetailPage: React.FC = () => {
  const { userId } = useParams<{ userId: string }>();

  const [user, setUser] = useState<UserDetail | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // Edit Profile State
  const [isEditing, setIsEditing] = useState<boolean>(false);
  const [fullNameInput, setFullNameInput] = useState<string>("");
  const [isSavingProfile, setIsSavingProfile] = useState<boolean>(false);
  const [profileError, setProfileError] = useState<string | null>(null);

  // Lifecycle Modal State
  const [lifecycleAction, setLifecycleAction] = useState<UserLifecycleAction | null>(null);

  const fetchUser = useCallback(async () => {
    if (!userId) return;
    setIsLoading(true);
    setError(null);
    try {
      const data = await usersApi.get(userId);
      setUser(data);
      setFullNameInput(data.full_name || "");
    } catch (err: unknown) {
      if (err instanceof ApiError && err.status === 404) {
        setError("User not found.");
      } else {
        setError("Unable to load user details. Please check your connection.");
      }
    } finally {
      setIsLoading(false);
    }
  }, [userId]);

  useEffect(() => {
    fetchUser();
  }, [fetchUser]);

  const handleSaveProfile = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!user) return;
    setIsSavingProfile(true);
    setProfileError(null);

    try {
      const updated = await usersApi.update(user.id, {
        full_name: fullNameInput.trim(),
      });
      setUser(updated);
      setIsEditing(false);
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        const data = err.data as { detail?: string } | undefined;
        setProfileError(data?.detail || err.message || "Failed to update profile.");
      } else {
        setProfileError("An unexpected error occurred.");
      }
    } finally {
      setIsSavingProfile(false);
    }
  };

  const handleLifecycleSuccess = (updated: UserDetail) => {
    setUser(updated);
    setFullNameInput(updated.full_name || "");
  };

  const getStatusBadge = (statusVal?: UserStatus) => {
    if (!statusVal) return null;
    const styles: Record<UserStatus, { bg: string; color: string; border: string; label: string }> = {
      active: {
        bg: "rgba(16, 185, 129, 0.12)",
        color: "rgb(5, 150, 105)",
        border: "rgba(16, 185, 129, 0.25)",
        label: "Active",
      },
      suspended: {
        bg: "rgba(245, 158, 11, 0.12)",
        color: "rgb(217, 119, 6)",
        border: "rgba(245, 158, 11, 0.25)",
        label: "Suspended",
      },
      disabled: {
        bg: "rgba(239, 68, 68, 0.12)",
        color: "rgb(220, 38, 38)",
        border: "rgba(239, 68, 68, 0.25)",
        label: "Disabled",
      },
    };
    const s = styles[statusVal] || styles.active;
    return (
      <span
        style={{
          display: "inline-flex",
          alignItems: "center",
          padding: "0.25rem 0.75rem",
          borderRadius: "9999px",
          fontSize: "0.8125rem",
          fontWeight: 600,
          backgroundColor: s.bg,
          color: s.color,
          border: `1px solid ${s.border}`,
          textTransform: "capitalize",
        }}
      >
        {s.label}
      </span>
    );
  };

  return (
    <AppShell>
      <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }}>
        {/* Navigation Breadcrumbs */}
        <CatalogHierarchyNav
          items={[
            { label: "Central Users", path: "/users" },
            { label: user?.email || "Loading User..." },
          ]}
        />

        {error && (
          <div className="alert-banner alert-banner-error" role="alert">
            <span>{error}</span>
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              onClick={fetchUser}
              style={{ marginLeft: "auto" }}
            >
              Retry
            </button>
          </div>
        )}

        {isLoading ? (
          <div style={{ padding: "3rem 0", display: "flex", justifyContent: "center" }}>
            <LoadingSpinner label="Loading user details..." />
          </div>
        ) : user ? (
          <>
            {/* Header Card */}
            <div
              style={{
                backgroundColor: "var(--glass-surface-elevated)",
                border: "1px solid var(--border-glass)",
                borderRadius: "0.75rem",
                padding: "1.5rem",
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                flexWrap: "wrap",
                gap: "1rem",
              }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: "1rem", flexWrap: "wrap" }}>
                <div
                  style={{
                    width: "3.5rem",
                    height: "3.5rem",
                    borderRadius: "0.75rem",
                    backgroundColor: "var(--color-primary-subtle, rgba(59, 130, 246, 0.15))",
                    color: "var(--color-primary, #3b82f6)",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    flexShrink: 0,
                  }}
                >
                  <UserIcon size={32} />
                </div>
                <div>
                  <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", flexWrap: "wrap" }}>
                    <h1 style={{ margin: 0, fontSize: "1.5rem", fontWeight: 700, color: "var(--text-primary)", wordBreak: "break-all" }}>
                      {user.full_name || user.email}
                    </h1>
                    {getStatusBadge(user.status)}
                    {user.is_platform_owner && (
                      <span
                        style={{
                          display: "inline-flex",
                          alignItems: "center",
                          gap: "0.25rem",
                          padding: "0.25rem 0.6rem",
                          borderRadius: "9999px",
                          fontSize: "0.75rem",
                          fontWeight: 600,
                          backgroundColor: "var(--color-primary-subtle, rgba(59, 130, 246, 0.15))",
                          color: "var(--color-primary, #3b82f6)",
                          border: "1px solid var(--border-subtle)",
                        }}
                      >
                        <ShieldCheckIcon size={14} />
                        Platform Owner
                      </span>
                    )}
                  </div>
                  <div style={{ color: "var(--text-secondary)", fontSize: "0.875rem", marginTop: "0.25rem", wordBreak: "break-all" }}>
                    {user.email}
                  </div>
                </div>
              </div>

              {/* Lifecycle Actions */}
              <div style={{ display: "flex", gap: "0.5rem", alignItems: "center", flexWrap: "wrap" }}>
                {user.status === "active" && (
                  <button
                    type="button"
                    className="btn btn-secondary"
                    style={{ minHeight: "44px", display: "inline-flex", alignItems: "center" }}
                    onClick={() => setLifecycleAction("suspend")}
                  >
                    Suspend
                  </button>
                )}

                {user.status === "suspended" && (
                  <button
                    type="button"
                    className="btn btn-success"
                    style={{ minHeight: "44px", display: "inline-flex", alignItems: "center" }}
                    onClick={() => setLifecycleAction("reactivate")}
                  >
                    Reactivate
                  </button>
                )}

                {user.status !== "disabled" && (
                  <button
                    type="button"
                    className="btn btn-danger"
                    style={{ minHeight: "44px", display: "inline-flex", alignItems: "center" }}
                    onClick={() => setLifecycleAction("disable")}
                  >
                    Disable
                  </button>
                )}

                {!user.email.startsWith("anonymized-") && !user.email.includes("system.service.actor") && (
                  <button
                    type="button"
                    className="btn btn-secondary"
                    style={{
                      minHeight: "44px",
                      display: "inline-flex",
                      alignItems: "center",
                      color: "var(--status-danger)",
                      borderColor: "rgba(239, 68, 68, 0.4)",
                    }}
                    onClick={() => setLifecycleAction("anonymize")}
                  >
                    Anonymize User (Privacy)
                  </button>
                )}
              </div>
            </div>

            {user.email.startsWith("anonymized-") && (
              <div
                style={{
                  padding: "1rem",
                  borderRadius: "0.5rem",
                  background: "rgba(59, 130, 246, 0.1)",
                  border: "1px solid rgba(59, 130, 246, 0.3)",
                  color: "var(--text-primary)",
                  fontSize: "0.875rem",
                  lineHeight: 1.5,
                }}
              >
                <strong>Phase 6F Privacy Notice:</strong> This user profile has been irreversibly anonymized and permanently deactivated. Personal identifying attributes were scrubbed and replaced with deterministic pseudonyms. Immutable historical forensic audit records remain intact.
              </div>
            )}

            {/* Profile Overview Card */}
            <div
              style={{
                backgroundColor: "var(--glass-surface-elevated)",
                border: "1px solid var(--border-glass)",
                borderRadius: "0.75rem",
                padding: "1.5rem",
              }}
            >
              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  marginBottom: "1.25rem",
                  borderBottom: "1px solid var(--border-subtle)",
                  paddingBottom: "0.75rem",
                }}
              >
                <h2 style={{ margin: 0, fontSize: "1.125rem", fontWeight: 600, color: "var(--text-primary)" }}>
                  Profile Attributes
                </h2>
                {!isEditing && (
                  <button
                    type="button"
                    className="btn btn-secondary btn-sm"
                    onClick={() => setIsEditing(true)}
                  >
                    Edit Profile
                  </button>
                )}
              </div>

              {isEditing ? (
                <form onSubmit={handleSaveProfile} style={{ maxWidth: "28rem" }}>
                  {profileError && (
                    <div
                      className="alert-banner alert-banner-error"
                      role="alert"
                      style={{ marginBottom: "1rem" }}
                    >
                      {profileError}
                    </div>
                  )}

                  <div style={{ marginBottom: "1rem" }}>
                    <label
                      htmlFor="edit-fullName"
                      style={{
                        display: "block",
                        fontSize: "0.875rem",
                        fontWeight: 500,
                        marginBottom: "0.375rem",
                        color: "var(--text-primary)",
                      }}
                    >
                      Full Name
                    </label>
                    <input
                      id="edit-fullName"
                      type="text"
                      value={fullNameInput}
                      onChange={(e) => setFullNameInput(e.target.value)}
                      disabled={isSavingProfile}
                      style={{
                        width: "100%",
                        padding: "0.5rem 0.75rem",
                        borderRadius: "0.375rem",
                        border: "1px solid var(--input-border)",
                        backgroundColor: "var(--input-bg)",
                        color: "var(--text-primary)",
                        fontSize: "0.875rem",
                        boxSizing: "border-box",
                      }}
                    />
                  </div>

                  <div style={{ display: "flex", gap: "0.5rem" }}>
                    <button
                      type="submit"
                      className="btn btn-primary btn-sm"
                      disabled={isSavingProfile}
                    >
                      {isSavingProfile ? "Saving..." : "Save Changes"}
                    </button>
                    <button
                      type="button"
                      className="btn btn-secondary btn-sm"
                      disabled={isSavingProfile}
                      onClick={() => {
                        setIsEditing(false);
                        setFullNameInput(user.full_name || "");
                        setProfileError(null);
                      }}
                    >
                      Cancel
                    </button>
                  </div>
                </form>
              ) : (
                <div
                  style={{
                    display: "grid",
                    gridTemplateColumns: "repeat(auto-fit, minmax(14rem, 1fr))",
                    gap: "1.25rem",
                  }}
                >
                  <div>
                    <div style={{ fontSize: "0.8125rem", color: "var(--text-muted)" }}>
                      User ID
                    </div>
                    <div style={{ fontFamily: "monospace", fontSize: "0.875rem", marginTop: "0.25rem", color: "var(--text-primary)", wordBreak: "break-all" }}>
                      {user.id}
                    </div>
                  </div>

                  <div>
                    <div style={{ fontSize: "0.8125rem", color: "var(--text-muted)" }}>
                      Email
                    </div>
                    <div style={{ fontSize: "0.875rem", fontWeight: 500, marginTop: "0.25rem", color: "var(--text-primary)", wordBreak: "break-all" }}>
                      {user.email}
                    </div>
                  </div>

                  <div>
                    <div style={{ fontSize: "0.8125rem", color: "var(--text-muted)" }}>
                      Full Name
                    </div>
                    <div style={{ fontSize: "0.875rem", marginTop: "0.25rem", color: "var(--text-primary)" }}>
                      {user.full_name || "—"}
                    </div>
                  </div>

                  <div>
                    <div style={{ fontSize: "0.8125rem", color: "var(--text-muted)" }}>
                      Auth Provider
                    </div>
                    <div style={{ fontSize: "0.875rem", textTransform: "capitalize", marginTop: "0.25rem", color: "var(--text-primary)" }}>
                      {user.auth_provider || "local"}
                    </div>
                  </div>

                  <div>
                    <div style={{ fontSize: "0.8125rem", color: "var(--text-muted)" }}>
                      Email Verified At
                    </div>
                    <div style={{ fontSize: "0.875rem", marginTop: "0.25rem", color: "var(--text-primary)" }} title={user.email_verified_at || undefined}>
                      {formatDateTime(user.email_verified_at)}
                    </div>
                  </div>

                  <div>
                    <div style={{ fontSize: "0.8125rem", color: "var(--text-muted)" }}>
                      Created At
                    </div>
                    <div style={{ fontSize: "0.875rem", marginTop: "0.25rem", color: "var(--text-primary)" }} title={user.created_at}>
                      {formatDateTime(user.created_at)}
                    </div>
                  </div>

                  <div>
                    <div style={{ fontSize: "0.8125rem", color: "var(--text-muted)" }}>
                      Updated At
                    </div>
                    <div style={{ fontSize: "0.875rem", marginTop: "0.25rem", color: "var(--text-primary)" }} title={user.updated_at}>
                      {formatDateTime(user.updated_at)}
                    </div>
                  </div>
                </div>
              )}
            </div>
          </>
        ) : null}

        {/* Lifecycle Confirmation Modal */}
        <UserLifecycleModal
          isOpen={lifecycleAction !== null}
          onClose={() => setLifecycleAction(null)}
          onSuccess={handleLifecycleSuccess}
          user={user}
          action={lifecycleAction}
        />
      </div>
    </AppShell>
  );
};
