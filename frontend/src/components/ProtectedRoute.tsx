import React from "react";
import { Navigate, useLocation } from "react-router-dom";
import { useAuth } from "../context/AuthContext.tsx";
import type { ConsoleContextType } from "../api/types.ts";
import { LoadingSpinner } from "./LoadingSpinner.tsx";
import { GlassPanel } from "./GlassPanel.tsx";
import { ShieldCheckIcon } from "./Icons.tsx";

interface ProtectedRouteProps {
  readonly children: React.ReactElement;
  readonly requiredContext?: ConsoleContextType | "owner";
  readonly requiredPermission?: string;
  readonly requiredModule?: string;
  readonly adminOnly?: boolean;
}

export const ProtectedRoute: React.FC<ProtectedRouteProps> = ({
  children,
  requiredContext,
  requiredPermission,
  requiredModule,
  adminOnly = false,
}) => {
  const { status, user, logout } = useAuth();
  const location = useLocation();

  if (status === "loading") {
    return <LoadingSpinner label="Verifying Session..." fullScreen />;
  }

  if (status === "unauthenticated" || !user) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  if (status === "forbidden") {
    return (
      <div
        style={{
          minHeight: "100vh",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          padding: "1.5rem",
          background: "var(--bg-app)",
          position: "relative",
        }}
      >
        <div className="ambient-bg" />
        <GlassPanel
          elevation="elevated"
          padding="xl"
          style={{ maxWidth: "480px", width: "100%", textAlign: "center", zIndex: 1 }}
        >
          <div
            style={{
              width: "56px",
              height: "56px",
              borderRadius: "16px",
              background: "var(--status-danger-bg)",
              border: "1px solid var(--status-danger-border)",
              color: "var(--status-danger)",
              display: "inline-flex",
              alignItems: "center",
              justifyContent: "center",
              marginBottom: "1.25rem",
            }}
          >
            <ShieldCheckIcon size={28} />
          </div>
          <h1 style={{ fontSize: "1.375rem", fontWeight: 700, marginBottom: "0.5rem" }}>
            Access Restricted
          </h1>
          <p style={{ color: "var(--text-secondary)", fontSize: "0.9375rem", lineHeight: 1.5, marginBottom: "1.75rem" }}>
            Your account does not have permission to access this console.
          </p>
          <button
            type="button"
            onClick={() => void logout()}
            className="btn-primary"
            style={{ width: "100%" }}
          >
            Return to Sign In
          </button>
        </GlassPanel>
      </div>
    );
  }

  // If no active context is set, redirect to context selection unless already there
  if (!user.active_context) {
    if (user.available_contexts.length > 0) {
      if (location.pathname !== "/select-context") {
        return <Navigate to="/select-context" replace />;
      }
      return children;
    }
    return (
      <div
        style={{
          minHeight: "100vh",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          padding: "1.5rem",
          background: "var(--bg-app)",
          position: "relative",
        }}
      >
        <div className="ambient-bg" />
        <GlassPanel
          elevation="elevated"
          padding="xl"
          style={{ maxWidth: "480px", width: "100%", textAlign: "center", zIndex: 1 }}
        >
          <h1 style={{ fontSize: "1.375rem", fontWeight: 700, marginBottom: "0.5rem" }}>
            No Console Access
          </h1>
          <p style={{ color: "var(--text-secondary)", fontSize: "0.9375rem", lineHeight: 1.5, marginBottom: "1.75rem" }}>
            Your account has no active organization memberships.
          </p>
          <button
            type="button"
            onClick={() => void logout()}
            className="btn-primary"
            style={{ width: "100%" }}
          >
            Return to Sign In
          </button>
        </GlassPanel>
      </div>
    );
  }

  const isTenantMember =
    user.active_context.type === "tenant" &&
    user.active_context.membership_type === "member";

  // Block tenant members from adminOnly routes
  if (adminOnly && isTenantMember) {
    return <Navigate to="/tenant/dashboard" replace />;
  }

  // Enforce context type if required by route (normalizing "owner" alias to "platform_owner")
  const targetContext = requiredContext === "owner" ? "platform_owner" : requiredContext;
  if (targetContext && user.active_context.type !== targetContext) {
    if (user.active_context.type === "platform_owner") {
      return <Navigate to="/" replace />;
    }
    if (user.active_context.type === "tenant") {
      return <Navigate to={isTenantMember ? "/tenant/dashboard" : "/tenant"} replace />;
    }
    return <Navigate to="/select-context" replace />;
  }

  // Enforce module if required by route (reads solely from user.active_context)
  if (requiredModule) {
    const isMemberAllowedPage =
      isTenantMember &&
      ((requiredModule === "tenant_my_products" && location.pathname === "/tenant/products") ||
        location.pathname === "/tenant/dashboard");

    if (!isMemberAllowedPage) {
      const allowedModules = user.active_context.allowed_modules ?? [];
      if (!allowedModules.includes(requiredModule)) {
        if (user.active_context.type === "tenant") {
          return <Navigate to={isTenantMember ? "/tenant/dashboard" : "/tenant"} replace />;
        }
        return <Navigate to="/" replace />;
      }
    }
  }

  // Enforce permission if required by route (reads solely from user.active_context)
  if (requiredPermission) {
    const isMemberAllowedPage =
      isTenantMember &&
      ((requiredPermission === "products.view" && location.pathname === "/tenant/products") ||
        location.pathname === "/tenant/dashboard");

    if (!isMemberAllowedPage) {
      if (user.is_platform_owner) {
        return children;
      }
      const effectivePermissions = user.active_context.effective_permissions ?? [];
      if (!effectivePermissions.includes(requiredPermission)) {
        if (user.active_context.type === "tenant") {
          return <Navigate to={isTenantMember ? "/tenant/dashboard" : "/tenant"} replace />;
        }
        return <Navigate to="/" replace />;
      }
    }
  }

  return children;
};
