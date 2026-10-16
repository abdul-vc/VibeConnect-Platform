/**
 * Loading Spinner & Screen Component.
 *
 * Ambient liquid glass loading state with smooth pulsing indicator.
 */

import type { FC } from "react";

interface LoadingSpinnerProps {
  readonly label?: string;
  readonly fullScreen?: boolean;
}

export const LoadingSpinner: FC<LoadingSpinnerProps> = ({
  label = "Authenticating Session...",
  fullScreen = true,
}) => {
  const content = (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        gap: "1.25rem",
        padding: "2rem",
      }}
    >
      <div
        style={{
          position: "relative",
          width: "48px",
          height: "48px",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
        }}
      >
        <div
          style={{
            position: "absolute",
            inset: "-6px",
            borderRadius: "50%",
            background: "radial-gradient(circle, var(--brand-primary) 0%, transparent 70%)",
            opacity: 0.25,
            filter: "blur(6px)",
          }}
        />
        <div
          style={{
            width: "40px",
            height: "40px",
            borderRadius: "50%",
            border: "3px solid var(--border-glass)",
            borderTopColor: "var(--brand-primary)",
            animation: "spin 0.8s cubic-bezier(0.4, 0, 0.2, 1) infinite",
          }}
        />
      </div>

      {label && (
        <p
          style={{
            fontSize: "0.875rem",
            fontWeight: 500,
            color: "var(--text-secondary)",
            letterSpacing: "-0.01em",
          }}
        >
          {label}
        </p>
      )}
    </div>
  );

  if (fullScreen) {
    return (
      <div
        style={{
          minHeight: "100vh",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          background: "var(--bg-app)",
          position: "relative",
        }}
      >
        <div className="ambient-bg" />
        <div
          className="glass-panel"
          style={{
            padding: "1.5rem 2.5rem",
            borderRadius: "20px",
            position: "relative",
            zIndex: 1,
          }}
        >
          {content}
        </div>
      </div>
    );
  }

  return content;
};
