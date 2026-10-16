/**
 * Segmented Theme Toggle Component.
 *
 * Executive-grade segmented switch showing both Sun and Moon options on desktop,
 * with accessible keyboard navigation and persistence.
 */

import React from "react";
import { useTheme } from "../context/ThemeContext.tsx";
import { SunIcon, MoonIcon } from "./Icons.tsx";

interface ThemeToggleProps {
  readonly className?: string;
  readonly compact?: boolean;
}

export const ThemeToggle: React.FC<ThemeToggleProps> = ({ className = "", compact = false }) => {
  const { theme, setTheme } = useTheme();

  return (
    <div
      role="radiogroup"
      aria-label="Color theme selection"
      className={className}
      style={{
        display: "inline-flex",
        alignItems: "center",
        padding: "3px",
        borderRadius: "9999px",
        background: "var(--glass-surface)",
        border: "1px solid var(--border-glass)",
        boxShadow: "var(--shadow-sm), var(--glass-inner-rim)",
        backdropFilter: "blur(12px)",
        WebkitBackdropFilter: "blur(12px)",
        userSelect: "none",
        gap: "2px",
      }}
    >
      {/* Light Option */}
      <button
        type="button"
        role="radio"
        aria-checked={theme === "light"}
        onClick={() => setTheme("light")}
        className="btn-ghost"
        style={{
          display: "flex",
          alignItems: "center",
          gap: "0.35rem",
          padding: compact ? "4px 8px" : "4px 10px",
          minHeight: "28px",
          minWidth: compact ? "28px" : "auto",
          borderRadius: "9999px",
          background: theme === "light" ? "var(--bg-solid-fallback)" : "transparent",
          color: theme === "light" ? "var(--text-primary)" : "var(--text-muted)",
          boxShadow: theme === "light" ? "0 1px 3px rgba(15, 23, 42, 0.12)" : "none",
          fontWeight: theme === "light" ? 600 : 500,
          fontSize: "0.75rem",
          border: theme === "light" ? "1px solid var(--border-glass)" : "1px solid transparent",
          cursor: "pointer",
          transition: "all 0.15s ease",
        }}
        title="Light theme"
      >
        <SunIcon size={13} style={{ color: theme === "light" ? "#f59e0b" : "currentColor" }} />
        {!compact && <span className="theme-toggle-label">Light</span>}
      </button>

      {/* Dark Option */}
      <button
        type="button"
        role="radio"
        aria-checked={theme === "dark"}
        onClick={() => setTheme("dark")}
        className="btn-ghost"
        style={{
          display: "flex",
          alignItems: "center",
          gap: "0.35rem",
          padding: compact ? "4px 8px" : "4px 10px",
          minHeight: "28px",
          minWidth: compact ? "28px" : "auto",
          borderRadius: "9999px",
          background: theme === "dark" ? "var(--glass-surface-hover)" : "transparent",
          color: theme === "dark" ? "var(--text-primary)" : "var(--text-muted)",
          boxShadow: theme === "dark" ? "0 1px 4px rgba(0, 0, 0, 0.4)" : "none",
          fontWeight: theme === "dark" ? 600 : 500,
          fontSize: "0.75rem",
          border: theme === "dark" ? "1px solid var(--border-glass)" : "1px solid transparent",
          cursor: "pointer",
          transition: "all 0.15s ease",
        }}
        title="Dark theme"
      >
        <MoonIcon size={13} style={{ color: theme === "dark" ? "var(--brand-primary)" : "currentColor" }} />
        {!compact && <span className="theme-toggle-label">Dark</span>}
      </button>

      <style>{`
        @media (max-width: 480px) {
          .theme-toggle-label {
            display: none;
          }
        }
      `}</style>
    </div>
  );
};
