/**
 * Platform Owner Login Page.
 *
 * Apple-inspired Liquid Glass authentication portal with dark/light theming,
 * segmented theme toggle, password visibility toggle, and privacy-first copy.
 */

import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext.tsx";
import { useTheme } from "../context/ThemeContext.tsx";
import { ThemeToggle } from "../components/ThemeToggle.tsx";
import logoLight from "../assets/envisage-logo.png";
import logoDark from "../assets/envisage-logo-dark.png";
import {
  LockIcon,
  EyeIcon,
  EyeOffIcon,
  AlertCircleIcon,
  ArrowRightIcon,
} from "../components/Icons.tsx";

export const LoginPage: React.FC = () => {
  const { login, status } = useAuth();
  const { theme } = useTheme();
  const navigate = useNavigate();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  React.useEffect(() => {
    const originalBodyOverflow = document.body.style.overflow;
    const originalHtmlOverflow = document.documentElement.style.overflow;
    document.body.style.overflow = "hidden";
    document.documentElement.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = originalBodyOverflow;
      document.documentElement.style.overflow = originalHtmlOverflow;
    };
  }, []);

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
        height: "100vh",
        maxHeight: "100vh",
        display: "flex",
        flexDirection: "column",
        position: "relative",
        background: "var(--bg-app)",
        overflow: "hidden",
      }}
    >
      {/* Ambient background glow accents */}
      <div
        style={{
          position: "absolute",
          top: "-10%",
          left: "20%",
          width: "520px",
          height: "520px",
          borderRadius: "50%",
          background: "radial-gradient(circle, rgba(56, 103, 245, 0.09) 0%, transparent 70%)",
          filter: "blur(50px)",
          pointerEvents: "none",
        }}
      />
      <div
        style={{
          position: "absolute",
          bottom: "-10%",
          right: "20%",
          width: "520px",
          height: "520px",
          borderRadius: "50%",
          background: "radial-gradient(circle, rgba(155, 77, 255, 0.08) 0%, transparent 70%)",
          filter: "blur(50px)",
          pointerEvents: "none",
        }}
      />

      {/* Top Header Bar with Brand Logo on Top Left and Theme Switch on Top Right */}
      <header
        style={{
          position: "absolute",
          top: 0,
          left: 0,
          right: 0,
          zIndex: 10,
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "1.25rem 2rem",
          maxWidth: "1400px",
          margin: "0 auto",
          width: "100%",
          boxSizing: "border-box",
        }}
      >
        <div
          style={{
            display: "inline-flex",
            alignItems: "center",
            padding: "0.25rem 0",
            background: "transparent",
            boxShadow: "none",
            border: "none",
            transition: "opacity 0.2s ease",
          }}
        >
          <img
            src={theme === "dark" ? logoDark : logoLight}
            alt="Envisage Insights"
            style={{
              height: "54px",
              width: "auto",
              objectFit: "contain",
              display: "block",
            }}
          />
        </div>

        <ThemeToggle />
      </header>

      {/* Main Login Composition */}
      <main
        style={{
          height: "100vh",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          padding: "1rem",
          position: "relative",
          zIndex: 1,
          overflow: "hidden",
        }}
      >
        <div
          style={{
            maxWidth: "520px",
            width: "100%",
            margin: "0 auto",
            position: "relative",
            zIndex: 1,
          }}
        >
          <div
            className="glass-card"
            style={{
              padding: "2.5rem 2.5rem 2rem 2.5rem",
              display: "flex",
              flexDirection: "column",
              justifyContent: "center",
              background: "var(--glass-surface-elevated)",
              border: "1px solid var(--border-glass)",
              borderRadius: "18px",
              boxShadow: "var(--shadow-lg), var(--glass-inner-rim)",
            }}
          >
            <div style={{ marginBottom: "1.35rem" }}>
              <div
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  gap: "0.45rem",
                  padding: "0.25rem 0.65rem",
                  borderRadius: "999px",
                  background: "var(--brand-primary-light)",
                  border: "1px solid var(--border-subtle)",
                  marginBottom: "0.75rem",
                }}
              >
                <span
                  style={{
                    width: "7px",
                    height: "7px",
                    borderRadius: "50%",
                    background: "var(--brand-primary)",
                  }}
                />
                <span
                  style={{
                    fontSize: "0.71875rem",
                    fontWeight: 700,
                    textTransform: "uppercase",
                    letterSpacing: "0.08em",
                    color: "var(--brand-primary)",
                  }}
                >
                  Workspace Access
                </span>
              </div>
              <h2 style={{ fontSize: "1.7rem", fontWeight: 700, color: "var(--text-primary)", letterSpacing: "-0.02em", margin: 0 }}>
                Welcome Back 👋
              </h2>
              <p className="text-body" style={{ marginTop: "0.4rem", fontSize: "0.875rem", color: "var(--text-secondary)" }}>
                Sign in to your workspace and continue building the future together.
              </p>
            </div>

            {errorMessage && (
              <div className="alert-box alert-danger" role="alert" style={{ marginBottom: "1rem" }}>
                <AlertCircleIcon size={16} style={{ flexShrink: 0, marginTop: "2px", color: "var(--status-danger)" }} />
                <div>{errorMessage}</div>
              </div>
            )}

            <form onSubmit={handleSubmit} noValidate>
              <div className="form-group" style={{ marginBottom: "0.95rem" }}>
                <label htmlFor="email" className="form-label" style={{ fontSize: "0.84375rem", fontWeight: 600, color: "var(--text-secondary)", marginBottom: "0.35rem" }}>
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
                    style={{
                      background: "var(--input-bg)",
                      border: "1px solid var(--border-glass)",
                      color: "var(--text-primary)",
                      borderRadius: "10px",
                      padding: "0.75rem 1rem",
                      fontSize: "0.9375rem",
                    }}
                  />
                </div>
              </div>

              <div className="form-group" style={{ marginBottom: "1.2rem" }}>
                <label htmlFor="password" className="form-label" style={{ fontSize: "0.84375rem", fontWeight: 600, color: "var(--text-secondary)", marginBottom: "0.35rem" }}>
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
                    style={{
                      background: "var(--input-bg)",
                      border: "1px solid var(--border-glass)",
                      color: "var(--text-primary)",
                      borderRadius: "10px",
                      padding: "0.75rem 2.6rem 0.75rem 1rem",
                      fontSize: "0.9375rem",
                    }}
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword(!showPassword)}
                    className="input-icon-right"
                    aria-label={showPassword ? "Hide password" : "Show password"}
                    title={showPassword ? "Hide password" : "Show password"}
                    style={{ color: "var(--text-muted)", right: "12px" }}
                  >
                    {showPassword ? <EyeOffIcon size={18} /> : <EyeIcon size={18} />}
                  </button>
                </div>
              </div>

              <button
                type="submit"
                disabled={isSubmitting || status === "loading"}
                className="btn-primary"
                style={{
                  width: "100%",
                  padding: "0.78rem 1.4rem",
                  background: "var(--brand-gradient)",
                  border: "none",
                  borderRadius: "10px",
                  fontWeight: 600,
                  fontSize: "0.9375rem",
                  color: "#ffffff",
                  boxShadow: "0 4px 16px rgba(56, 103, 245, 0.35)",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  gap: "0.5rem",
                  cursor: "pointer",
                }}
              >
                {isSubmitting ? (
                  <>
                    <div
                      className="spinner-icon"
                      style={{
                        width: "16px",
                        height: "16px",
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
                    <ArrowRightIcon size={16} />
                  </>
                )}
              </button>
            </form>

            {/* Or Continue With - SSO Buttons */}
            <div style={{ marginTop: "1rem", textAlign: "center" }}>
              <div style={{ position: "relative", marginBottom: "0.75rem" }}>
                <div style={{ position: "absolute", top: "50%", left: 0, right: 0, height: "1px", background: "var(--border-subtle)" }} />
                <span
                  style={{
                    position: "relative",
                    background: "var(--glass-surface-elevated)",
                    padding: "0.15rem 0.75rem",
                    borderRadius: "999px",
                    border: "1px solid var(--border-subtle)",
                    fontSize: "0.75rem",
                    color: "var(--text-muted)",
                    fontWeight: 500,
                  }}
                >
                  Or continue with
                </span>
              </div>

              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.85rem" }}>
                <button
                  type="button"
                  onClick={() => setErrorMessage("Enterprise SSO redirect is managed by organization identity providers.")}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    gap: "0.5rem",
                    padding: "0.6rem 0.85rem",
                    borderRadius: "10px",
                    border: "1px solid var(--border-glass)",
                    background: "var(--glass-surface-sunken)",
                    fontSize: "0.84375rem",
                    fontWeight: 600,
                    color: "var(--text-primary)",
                    cursor: "pointer",
                    transition: "all 0.15s ease",
                    boxShadow: "var(--shadow-sm)",
                  }}
                >
                  <span style={{ fontWeight: 800, color: "#EA4335" }}>G</span>
                  Google
                </button>

                <button
                  type="button"
                  onClick={() => setErrorMessage("Enterprise SSO redirect is managed by organization identity providers.")}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    gap: "0.5rem",
                    padding: "0.6rem 0.85rem",
                    borderRadius: "10px",
                    border: "1px solid var(--border-glass)",
                    background: "var(--glass-surface-sunken)",
                    fontSize: "0.84375rem",
                    fontWeight: 600,
                    color: "var(--text-primary)",
                    cursor: "pointer",
                    transition: "all 0.15s ease",
                    boxShadow: "var(--shadow-sm)",
                  }}
                >
                  <span style={{ fontWeight: 800, color: "#00A4EF" }}>⊞</span>
                  Microsoft
                </button>
              </div>

              <div style={{ marginTop: "0.75rem", fontSize: "0.8125rem", color: "var(--text-secondary)" }}>
                New to Envisage?{" "}
                <span style={{ color: "var(--brand-primary)", fontWeight: 600, cursor: "pointer" }}>
                  Contact your admin
                </span>
              </div>
            </div>

            <div
              style={{
                marginTop: "0.75rem",
                paddingTop: "0.65rem",
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
              <span>Protected by Envisage Session Security</span>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
};
