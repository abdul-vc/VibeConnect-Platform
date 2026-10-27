/**
 * Envisage Brand Mark Component.
 *
 * Renders the authoritative Envisage brand logo asset with light/dark theme sensitivity
 * and optional tenant scope badge.
 */

import React from "react";
import logoLight from "../assets/envisage-logo.png";
import logoDark from "../assets/envisage-logo-dark.png";
import { useTheme } from "../context/ThemeContext.tsx";

interface BrandMarkProps {
  readonly size?: "sm" | "md" | "lg";
  readonly showLabel?: boolean;
  readonly subtitle?: string;
  readonly style?: React.CSSProperties;
}

export const BrandMark: React.FC<BrandMarkProps> = ({
  size = "md",
  subtitle,
  style,
}) => {
  let theme = "light";
  try {
    const themeContext = useTheme();
    theme = themeContext.theme;
  } catch {
    theme = "light";
  }

  const heights = {
    sm: "38px",
    md: "44px",
    lg: "52px",
  };

  const isControlPlaneText = subtitle?.toLowerCase().includes("control plane");

  return (
    <div
      className="envisage-brand-container"
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: "0.6rem",
        background: "transparent",
        userSelect: "none",
        ...style,
      }}
    >
      <img
        src={theme === "dark" ? logoDark : logoLight}
        alt="Envisage"
        className="envisage-brand-img"
        style={{
          height: heights[size],
          width: "auto",
          maxHeight: heights[size],
          display: "block",
        }}
      />

      {subtitle && !isControlPlaneText && (
        <span
          style={{
            fontSize: "0.75rem",
            color: "var(--text-secondary)",
            letterSpacing: "-0.01em",
            fontWeight: 600,
            background: "var(--glass-surface-sunken)",
            padding: "0.15rem 0.5rem",
            borderRadius: "6px",
            border: "1px solid var(--border-subtle)",
            fontFamily: "var(--font-code, monospace)",
          }}
        >
          {subtitle}
        </span>
      )}
    </div>
  );
};

