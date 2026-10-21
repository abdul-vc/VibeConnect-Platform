/**
 * VibeConnect Brand Mark Component.
 *
 * Refined refractive gradient monogram badge and crisp typography mark.
 */

import React from "react";

interface BrandMarkProps {
  readonly size?: "sm" | "md" | "lg";
  readonly showLabel?: boolean;
  readonly subtitle?: string;
}

export const BrandMark: React.FC<BrandMarkProps> = ({
  size = "md",
  showLabel = true,
  subtitle,
}) => {
  const iconSizes = {
    sm: { box: 36, font: "0.9375rem", text: "1.0625rem" },
    md: { box: 40, font: "1.0625rem", text: "1.1875rem" },
    lg: { box: 48, font: "1.25rem", text: "1.5rem" },
  };

  const currentSize = iconSizes[size];

  return (
    <div style={{ display: "inline-flex", alignItems: "center", gap: "0.75rem" }}>
      <div
        style={{
          width: `${currentSize.box}px`,
          height: `${currentSize.box}px`,
          borderRadius: size === "sm" ? "9px" : "10px",
          background: "var(--brand-primary)",
          boxShadow: "0 2px 8px rgba(37, 99, 235, 0.25)",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          color: "#ffffff",
          fontWeight: 700,
          fontSize: currentSize.font,
          letterSpacing: "-0.02em",
          userSelect: "none",
          flexShrink: 0,
        }}
        aria-hidden="true"
      >
        VC
      </div>

      {showLabel && (
        <div className="brandmark-text-container" style={{ display: "flex", flexDirection: "column" }}>
          <span
            style={{
              fontWeight: 700,
              fontSize: currentSize.text,
              letterSpacing: "-0.02em",
              lineHeight: 1.2,
              color: "var(--text-primary)",
            }}
          >
            VibeConnect
          </span>
          {subtitle && (
            <span
              style={{
                fontSize: "0.75rem",
                color: "var(--text-secondary)",
                letterSpacing: "-0.01em",
                fontWeight: 500,
              }}
            >
              {subtitle}
            </span>
          )}
        </div>
      )}
    </div>
  );
};
