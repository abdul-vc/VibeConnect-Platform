/**
 * ShowcaseEmbeddedDemo – Embedded live product demo iframe workspace.
 *
 * Renders an authorized live demo session inside the Platform Owner Console
 * central workspace without top-level browser redirects.
 */
import React, { useState } from "react";
import { LoadingSpinner } from "../../components/LoadingSpinner.tsx";
import {
  ChevronLeftIcon,
  RotateCcwIcon,
  ShieldCheckIcon,
} from "../../components/Icons.tsx";

export interface ShowcaseEmbeddedDemoProps {
  readonly productName: string;
  readonly productCode: string;
  readonly launchUrl: string;
  readonly onBack: () => void;
  readonly backLabel?: string;
}

export const ShowcaseEmbeddedDemo: React.FC<ShowcaseEmbeddedDemoProps> = ({
  productName,
  productCode,
  launchUrl,
  onBack,
  backLabel = "Back to Presentation",
}) => {
  const [isIframeLoading, setIsIframeLoading] = useState<boolean>(true);
  const [iframeKey, setIframeKey] = useState<number>(1);

  const handleReload = () => {
    setIsIframeLoading(true);
    setIframeKey((prev) => prev + 1);
  };

  return (
    <div
      id="showcase-embedded-demo-workspace"
      style={{
        display: "flex",
        flexDirection: "column",
        gap: "1rem",
        width: "100%",
        minWidth: 0,
        height: "100%",
        flex: 1,
      }}
    >
      {/* Workspace Toolbar */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "0.6rem 1rem",
          background: "var(--glass-surface-elevated, rgba(15, 23, 42, 0.85))",
          border: "1px solid var(--border-glass, rgba(255, 255, 255, 0.12))",
          borderRadius: "10px",
          gap: "1rem",
          flexWrap: "wrap",
        }}
      >
        {/* Left: Back button & Product Info */}
        <div style={{ display: "flex", alignItems: "center", gap: "0.85rem", minWidth: 0 }}>
          <button
            type="button"
            id="showcase-exit-demo-btn"
            onClick={onBack}
            className="btn-secondary"
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: "0.35rem",
              padding: "0.45rem 0.85rem",
              fontSize: "0.8125rem",
              fontWeight: 600,
              cursor: "pointer",
              borderRadius: "6px",
              border: "1px solid var(--border-glass, rgba(255, 255, 255, 0.15))",
              background: "var(--glass-surface, rgba(255, 255, 255, 0.06))",
              color: "var(--text-primary, #f8fafc)",
              transition: "all 0.15s ease",
            }}
          >
            <ChevronLeftIcon size={14} />
            <span>{backLabel}</span>
          </button>

          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", minWidth: 0 }}>
            <span
              style={{
                display: "inline-flex",
                alignItems: "center",
                padding: "2px 7px",
                borderRadius: "4px",
                fontSize: "0.72rem",
                fontWeight: 700,
                background: "var(--brand-primary-light, rgba(99, 102, 241, 0.16))",
                color: "var(--brand-primary, #6366f1)",
                border: "1px solid var(--brand-primary-light, rgba(99, 102, 241, 0.25))",
                textTransform: "uppercase",
                letterSpacing: "0.03em",
                whiteSpace: "nowrap",
              }}
            >
              {productCode}
            </span>

            <h2
              id="showcase-demo-product-title"
              style={{
                fontSize: "1.05rem",
                fontWeight: 700,
                margin: 0,
                color: "var(--text-primary, #f8fafc)",
                overflow: "hidden",
                textOverflow: "ellipsis",
                whiteSpace: "nowrap",
              }}
            >
              {productName}
            </h2>
          </div>
        </div>

        {/* Right: Status badge & Actions */}
        <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", flexWrap: "wrap" }}>
          <span
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: "0.35rem",
              fontSize: "0.72rem",
              fontWeight: 600,
              padding: "0.25rem 0.65rem",
              borderRadius: "6px",
              background: isIframeLoading
                ? "var(--brand-primary-light, rgba(99, 102, 241, 0.12))"
                : "var(--status-success-bg, rgba(16, 185, 129, 0.12))",
              color: isIframeLoading
                ? "var(--brand-primary, #6366f1)"
                : "var(--status-success, #10b981)",
              border: `1px solid ${
                isIframeLoading
                  ? "var(--brand-primary-light, rgba(99, 102, 241, 0.25))"
                  : "var(--status-success-border, rgba(16, 185, 129, 0.25))"
              }`,
            }}
          >
            <ShieldCheckIcon size={12} />
            {isIframeLoading ? "Authenticating SSO…" : "Live Demo Active"}
          </span>

          <button
            type="button"
            id="showcase-demo-reload-btn"
            onClick={handleReload}
            title="Reload embedded view"
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: "0.35rem",
              padding: "0.4rem 0.75rem",
              fontSize: "0.78rem",
              fontWeight: 600,
              cursor: "pointer",
              borderRadius: "6px",
              border: "1px solid var(--border-glass, rgba(255, 255, 255, 0.15))",
              background: "var(--glass-surface, rgba(255, 255, 255, 0.05))",
              color: "var(--text-secondary, #94a3b8)",
              transition: "all 0.15s ease",
            }}
          >
            <RotateCcwIcon size={13} />
            <span>Reload</span>
          </button>
        </div>
      </div>

      {/* Main Workspace Frame Area */}
      <div
        style={{
          background: "var(--glass-surface-elevated, rgba(15, 23, 42, 0.95))",
          border: "1px solid var(--border-glass, rgba(255, 255, 255, 0.14))",
          borderRadius: "12px",
          padding: "0.25rem",
          display: "flex",
          flexDirection: "column",
          flex: 1,
          minHeight: "700px",
          height: "calc(100vh - 170px)",
          position: "relative",
          boxShadow: "var(--shadow-sm)",
          overflow: "hidden",
          width: "100%",
          boxSizing: "border-box",
        }}
      >
        {/* Loading Overlay */}
        {isIframeLoading && (
          <div
            id="showcase-demo-loading-state"
            style={{
              position: "absolute",
              top: 0,
              left: 0,
              right: 0,
              bottom: 0,
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              justifyContent: "center",
              gap: "1rem",
              background: "var(--glass-surface-elevated, rgba(15, 23, 42, 0.95))",
              zIndex: 2,
              borderRadius: "10px",
            }}
          >
            <LoadingSpinner
              fullScreen={false}
              label={`Loading ${productName} interactive workspace…`}
            />
          </div>
        )}

        {/* Central Iframe */}
        <iframe
          key={iframeKey}
          id="showcase-demo-iframe"
          title={`${productName} Live Demo Workspace`}
          src={launchUrl}
          onLoad={() => setIsIframeLoading(false)}
          sandbox="allow-same-origin allow-scripts allow-forms allow-popups allow-downloads"
          referrerPolicy="strict-origin-when-cross-origin"
          style={{
            width: "100%",
            height: "100%",
            flex: 1,
            border: "none",
            borderRadius: "8px",
            background: "#ffffff",
            display: isIframeLoading ? "none" : "block",
          }}
        />
      </div>
    </div>
  );
};
