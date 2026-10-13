/**
 * GlassPanel Container Component.
 *
 * Configurable liquid glass panel with translucent borders and soft inner highlights.
 */

import React from "react";

interface GlassPanelProps extends React.HTMLAttributes<HTMLDivElement> {
  readonly elevation?: "default" | "elevated" | "sunken";
  readonly padding?: "none" | "sm" | "md" | "lg" | "xl";
  readonly children: React.ReactNode;
}

export const GlassPanel: React.FC<GlassPanelProps> = ({
  elevation = "default",
  padding = "lg",
  className = "",
  style = {},
  children,
  ...props
}) => {
  const paddingMap = {
    none: "0",
    sm: "0.875rem",
    md: "1.25rem",
    lg: "1.75rem",
    xl: "2.5rem",
  };

  const elevationClass =
    elevation === "elevated"
      ? "glass-panel-elevated"
      : elevation === "sunken"
      ? "glass-panel"
      : "glass-panel";

  return (
    <div
      className={`${elevationClass} ${className}`}
      style={{
        padding: paddingMap[padding],
        ...(elevation === "sunken" ? { background: "var(--glass-surface-sunken)" } : {}),
        ...style,
      }}
      {...props}
    >
      {children}
    </div>
  );
};
