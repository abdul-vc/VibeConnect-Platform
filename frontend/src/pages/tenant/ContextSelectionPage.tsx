/**
 * Context Selection Page (Phase 2D Stage 6).
 *
 * Presented when an authenticated user has multiple available console contexts
 * and no active context is selected, or when manually selecting a context.
 * Strictly consumes user.available_contexts provided by the backend.
 */

import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../../context/AuthContext.tsx";
import type { ConsoleContextSummary } from "../../api/types.ts";
import { BrandMark } from "../../components/BrandMark.tsx";
import { GlassPanel } from "../../components/GlassPanel.tsx";
import { ThemeToggle } from "../../components/ThemeToggle.tsx";
import {
  AlertCircleIcon,
  ArrowRightIcon,
  BuildingIcon,
  LogOutIcon,
  ShieldCheckIcon,
} from "../../components/Icons.tsx";

export const ContextSelectionPage: React.FC = () => {
  const { user, selectContext, logout } = useAuth();
  const navigate = useNavigate();

  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const availableContexts = user?.available_contexts || [];

  const handleSelect = async (ctx: ConsoleContextSummary) => {
    const key =
      ctx.type === "platform_owner"
        ? "platform_owner"
        : `tenant-${ctx.organization?.id}`;
    setSelectedKey(key);
    setError(null);
    setIsSubmitting(true);

    try {
      if (ctx.type === "platform_owner") {
        await selectContext({ context_type: "platform_owner" });
        navigate("/", { replace: true });
      } else if (ctx.type === "tenant" && ctx.organization) {
        const res = (await selectContext({
          context_type: "tenant",
          organization_id: ctx.organization.id,
        })) as any;
        if (res?.active_context?.membership_type === "member" || ctx.membership_type === "member") {
          navigate("/tenant/dashboard", { replace: true });
        } else {
          navigate("/tenant", { replace: true });
        }
      }
    } catch (err: unknown) {
      if (err instanceof Error) {
        setError(err.message);
      } else {
        setError("Failed to switch console context. Please try again.");
      }
      setSelectedKey(null);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div
      style={{
        minHeight: "100vh",
        display: "flex",
        flexDirection: "column",
        position: "relative",
        background: "var(--bg-app)",
        overflowX: "hidden",
      }}
    >
      <div className="ambient-bg" />

      {/* Top Header */}
      <header
        style={{
          position: "relative",
          zIndex: 10,
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "1rem 1.25rem",
          maxWidth: "1320px",
          width: "100%",
          margin: "0 auto",
          boxSizing: "border-box",
        }}
      >
        <BrandMark size="sm" showLabel={true} subtitle="Console" />
        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
          <ThemeToggle />
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            onClick={() => void logout()}
            aria-label="Sign out"
            style={{ minHeight: "40px", display: "inline-flex", alignItems: "center" }}
          >
            <LogOutIcon size={14} />
            <span>Sign Out</span>
          </button>
        </div>
      </header>

      {/* Main Container */}
      <main
        style={{
          flex: 1,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          padding: "1rem",
          position: "relative",
          zIndex: 1,
          width: "100%",
          boxSizing: "border-box",
        }}
      >
        <div style={{ maxWidth: "640px", width: "100%", minWidth: 0 }}>
          <GlassPanel elevation="elevated" padding="xl">
            <div style={{ textAlign: "center", marginBottom: "1.75rem" }}>
              <div
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  justifyContent: "center",
                  width: "48px",
                  height: "48px",
                  borderRadius: "12px",
                  background: "var(--brand-primary-light)",
                  color: "var(--brand-primary)",
                  marginBottom: "1rem",
                }}
              >
                <BuildingIcon size={24} />
              </div>
              <h1
                style={{
                  fontSize: "1.375rem",
                  fontWeight: 700,
                  margin: "0 0 0.5rem 0",
                  color: "var(--text-primary)",
                  overflowWrap: "anywhere",
                }}
              >
                Select Console Context
              </h1>
              <p
                style={{
                  fontSize: "0.875rem",
                  color: "var(--text-secondary)",
                  margin: 0,
                  lineHeight: 1.5,
                  overflowWrap: "anywhere",
                  wordBreak: "break-word",
                }}
              >
                Your account <strong style={{ overflowWrap: "anywhere", wordBreak: "break-all" }}>{user?.email}</strong> has access to multiple
                administrative workspaces. Choose an organization to enter its
                console.
              </p>
            </div>

            {error && (
              <div
                className="alert-box alert-danger"
                role="alert"
                style={{ marginBottom: "1.5rem" }}
              >
                <AlertCircleIcon
                  size={16}
                  style={{
                    flexShrink: 0,
                    marginTop: "2px",
                    color: "var(--status-danger)",
                  }}
                />
                <div>{error}</div>
              </div>
            )}

            <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
              {availableContexts.map((ctx, idx) => {
                const isOwner = ctx.type === "platform_owner";
                const key = isOwner
                  ? "platform_owner"
                  : `tenant-${ctx.organization?.id || idx}`;
                const isCurrentPending = selectedKey === key && isSubmitting;
                const isCurrentlyActive =
                  user?.active_context?.type === ctx.type &&
                  (isOwner ||
                    user?.active_context?.organization?.id ===
                      ctx.organization?.id);

                return (
                  <button
                    key={key}
                    type="button"
                    disabled={isSubmitting}
                    onClick={() => handleSelect(ctx)}
                    className="context-choice-btn"
                    style={{
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "space-between",
                      padding: "1rem",
                      borderRadius: "10px",
                      background: isCurrentlyActive
                        ? "var(--brand-primary-light)"
                        : "var(--glass-surface)",
                      border: isCurrentlyActive
                        ? "1px solid var(--border-glass)"
                        : "1px solid var(--border-subtle)",
                      cursor: isSubmitting ? "not-allowed" : "pointer",
                      textAlign: "left",
                      transition: "all 0.15s ease",
                      gap: "0.75rem",
                      width: "100%",
                      boxSizing: "border-box",
                      minHeight: "48px",
                    }}
                  >
                    <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", minWidth: 0, flex: 1 }}>
                      <div
                        style={{
                          width: "36px",
                          height: "36px",
                          borderRadius: "8px",
                          background: isOwner
                            ? "rgba(16, 185, 129, 0.12)"
                            : "rgba(99, 102, 241, 0.12)",
                          color: isOwner
                            ? "rgb(5, 150, 105)"
                            : "rgb(99, 102, 241)",
                          display: "flex",
                          alignItems: "center",
                          justifyContent: "center",
                          flexShrink: 0,
                        }}
                      >
                        {isOwner ? (
                          <ShieldCheckIcon size={20} />
                        ) : (
                          <BuildingIcon size={20} />
                        )}
                      </div>
                      <div style={{ minWidth: 0, flex: 1 }}>
                        <div
                          style={{
                            fontWeight: 600,
                            fontSize: "0.9375rem",
                            color: "var(--text-primary)",
                            wordBreak: "break-word",
                            overflowWrap: "anywhere",
                          }}
                        >
                          {isOwner
                            ? "Platform Owner Control Plane"
                            : ctx.organization?.name}
                        </div>
                        <div
                          style={{
                            fontSize: "0.8125rem",
                            color: "var(--text-secondary)",
                            marginTop: "0.15rem",
                            wordBreak: "break-word",
                            overflowWrap: "anywhere",
                          }}
                        >
                          {isOwner
                            ? "Manage catalog, subscriptions, organizations, and users"
                            : `Organization Code: ${ctx.organization?.code}`}
                        </div>
                      </div>
                    </div>

                    <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", flexShrink: 0 }}>
                      {isCurrentlyActive && (
                        <span
                          className="badge badge-primary"
                          style={{ fontSize: "0.75rem", flexShrink: 0 }}
                        >
                          Active
                        </span>
                      )}
                      {isCurrentPending ? (
                        <div
                          className="spinner-icon"
                          style={{
                            width: "14px",
                            height: "14px",
                            border: "2px solid var(--brand-primary)",
                            borderTopColor: "transparent",
                            borderRadius: "50%",
                            flexShrink: 0,
                          }}
                        />
                      ) : (
                        <ArrowRightIcon size={16} style={{ color: "var(--text-muted)", flexShrink: 0 }} />
                      )}
                    </div>
                  </button>
                );
              })}
            </div>
          </GlassPanel>
        </div>
      </main>

      <style>{`
        .context-choice-btn:hover:not(:disabled) {
          background: var(--glass-surface-hover) !important;
          border-color: var(--border-glass) !important;
          transform: translateY(-1px);
        }
      `}</style>
    </div>
  );
};
