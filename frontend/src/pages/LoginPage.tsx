/**
 * Platform Owner Login Page.
 *
 * Apple-inspired Liquid Glass authentication portal with dark/light theming,
 * segmented theme toggle, password visibility toggle, and privacy-first copy.
 */

import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext.tsx";
import { ThemeToggle } from "../components/ThemeToggle.tsx";
import { BrandMark } from "../components/BrandMark.tsx";
import { GlassPanel } from "../components/GlassPanel.tsx";
import {
  LockIcon,
  EyeIcon,
  EyeOffIcon,
  AlertCircleIcon,
  ShieldCheckIcon,
  ArrowRightIcon,
} from "../components/Icons.tsx";

export const LoginPage: React.FC = () => {
  const { login, status } = useAuth();
  const navigate = useNavigate();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMessage(null);

    const trimmedEmail = email.trim();
    if (!trimmedEmail || !password) {
      setErrorMessage("Please enter both your email address and password.");
      return;
    }

    setIsSubmitting(true);
    try {
      const authenticatedUser = await login({ email: trimmedEmail, password });
      if (authenticatedUser.active_context?.type === "platform_owner") {
        navigate("/", { replace: true });
      } else if (authenticatedUser.active_context?.type === "tenant") {
        if (authenticatedUser.active_context.membership_type === "member") {
          navigate("/tenant/dashboard", { replace: true });
        } else {
          navigate("/tenant", { replace: true });
        }
      } else if (authenticatedUser.available_contexts.length > 0) {
        navigate("/select-context", { replace: true });
      } else {
        navigate("/", { replace: true });
      }
    } catch (err: unknown) {
      if (err instanceof Error) {
        setErrorMessage(err.message);
      } else {
        setErrorMessage("Authentication failed. Please verify your credentials.");
      }
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
      {/* Ambient Radial Canvas */}
      <div className="ambient-bg" />

      {/* Top Bar with Brand & Segmented Theme Switch */}
      <header
        style={{
          position: "relative",
          zIndex: 10,
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "1.25rem 2rem",
          maxWidth: "1320px",
          width: "100%",
          margin: "0 auto",
        }}
      >
        <BrandMark size="sm" showLabel={true} subtitle="Control Plane" />
        <ThemeToggle />
      </header>

      {/* Main Login Composition */}
      <main
        style={{
          flex: 1,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          padding: "1.5rem",
          position: "relative",
          zIndex: 1,
        }}
      >
        <div
          style={{
            maxWidth: "920px",
            width: "100%",
            margin: "0 auto",
          }}
        >
          <GlassPanel
            elevation="elevated"
            padding="none"
            style={{
              overflow: "hidden",
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))",
            }}
          >
            {/* Left Brand Panel */}
            <div
              className="login-brand-panel"
              style={{
                padding: "2.5rem 2rem",
                background: "linear-gradient(135deg, var(--brand-primary-light) 0%, transparent 100%)",
                borderRight: "1px solid var(--border-glass)",
                display: "flex",
                flexDirection: "column",
                justifyContent: "space-between",
                gap: "2rem",
              }}
            >
              <div>
                <div
                  className="badge badge-primary"
                  style={{ marginBottom: "1.25rem" }}
                >
                  <ShieldCheckIcon size={13} />
                  Enterprise Control Plane
                </div>
                <h1 className="heading-title" style={{ marginBottom: "0.75rem" }}>
                  Unified Platform Architecture
                </h1>
                <p className="text-body" style={{ lineHeight: 1.6 }}>
                  Centralized control with privacy-first authentication and robust domain isolation across enterprise services.
                </p>
              </div>

              {/* Security Feature Highlight Card */}
              <div
                style={{
                  padding: "1.25rem",
                  background: "var(--glass-surface)",
                  borderRadius: "12px",
                  border: "1px solid var(--border-subtle)",
                }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: "0.625rem", marginBottom: "0.5rem" }}>
                  <div
                    style={{
                      width: "8px",
                      height: "8px",
                      borderRadius: "50%",
                      background: "var(--status-success)",
                      boxShadow: "0 0 6px var(--status-success)",
                    }}
                  />
                  <span style={{ fontSize: "0.8125rem", fontWeight: 600, color: "var(--text-primary)" }}>
                    Secure Session Architecture
                  </span>
                </div>
                <p style={{ fontSize: "0.75rem", color: "var(--text-secondary)", lineHeight: 1.5 }}>
                  Server-side session validation with isolated cookie policies and endpoint-scoped rate protection.
                </p>
              </div>

              <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", flexWrap: "wrap" }}>
                <span className="badge badge-neutral">Server-Side Sessions</span>
                <span className="badge badge-neutral">Protected Access</span>
              </div>
            </div>

            {/* Right Authentication Form */}
            <div style={{ padding: "2.5rem 2rem", display: "flex", flexDirection: "column", justifyContent: "center" }}>
              <div style={{ marginBottom: "1.5rem" }}>
                <div
                  style={{
                    fontSize: "0.75rem",
                    fontWeight: 700,
                    textTransform: "uppercase",
                    letterSpacing: "0.05em",
                    color: "var(--brand-primary)",
                    marginBottom: "0.25rem",
                  }}
                >
                  Console Access
                </div>
                <h2 style={{ fontSize: "1.375rem", fontWeight: 700 }}>
                  Welcome back
                </h2>
                <p className="text-caption" style={{ marginTop: "0.25rem" }}>
                  Sign in with your credentials to access your console.
                </p>
              </div>

              {errorMessage && (
                <div className="alert-box alert-danger" role="alert">
                  <AlertCircleIcon size={16} style={{ flexShrink: 0, marginTop: "2px", color: "var(--status-danger)" }} />
                  <div>{errorMessage}</div>
                </div>
              )}

              <form onSubmit={handleSubmit} noValidate>
                <div className="form-group">
                  <label htmlFor="email" className="form-label">
                    Email address
                  </label>
                  <div className="form-input-container">
                    <input
                      id="email"
                      type="email"
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      disabled={isSubmitting || status === "loading"}
                      placeholder="name@organization.com"
                      required
                      autoComplete="username"
                      className="form-input"
                    />
                  </div>
                </div>

                <div className="form-group" style={{ marginBottom: "1.5rem" }}>
                  <label htmlFor="password" className="form-label">
                    Password
                  </label>
                  <div className="form-input-container">
                    <input
                      id="password"
                      type={showPassword ? "text" : "password"}
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      disabled={isSubmitting || status === "loading"}
                      placeholder="••••••••••••"
                      required
                      autoComplete="current-password"
                      className="form-input form-input-with-icon-right"
                    />
                    <button
                      type="button"
                      onClick={() => setShowPassword(!showPassword)}
                      className="input-icon-right"
                      aria-label={showPassword ? "Hide password" : "Show password"}
                      title={showPassword ? "Hide password" : "Show password"}
                    >
                      {showPassword ? <EyeOffIcon size={16} /> : <EyeIcon size={16} />}
                    </button>
                  </div>
                </div>

                <button
                  type="submit"
                  disabled={isSubmitting || status === "loading"}
                  className="btn-primary"
                  style={{ width: "100%" }}
                >
                  {isSubmitting ? (
                    <>
                      <div
                        className="spinner-icon"
                        style={{
                          width: "15px",
                          height: "15px",
                          border: "2px solid rgba(255, 255, 255, 0.3)",
                          borderTopColor: "#ffffff",
                          borderRadius: "50%",
                        }}
                      />
                      <span>Authenticating...</span>
                    </>
                  ) : (
                    <>
                      <span>Sign In</span>
                      <ArrowRightIcon size={15} />
                    </>
                  )}
                </button>
              </form>

              <div
                style={{
                  marginTop: "1.5rem",
                  paddingTop: "1rem",
                  borderTop: "1px solid var(--border-subtle)",
                  textAlign: "center",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  gap: "0.5rem",
                  color: "var(--text-muted)",
                  fontSize: "0.75rem",
                }}
              >
                <LockIcon size={13} />
                <span>Protected by VibeConnect Session Security</span>
              </div>
            </div>
          </GlassPanel>
        </div>
      </main>
    </div>
  );
};
