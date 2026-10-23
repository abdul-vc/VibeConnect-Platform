/**
 * ShowcaseEmbeddedDemo – Embedded live product demo iframe workspace.
 *
 * Upgraded to full-size central workspace standard:
 * - Removed redundant internal top toolbar and header spacing
 * - Edge-to-edge full viewport iframe (calc(100dvh - 72px))
 * - Centered loading state with theme-aware spinner
 * - Floating, unobtrusive recovery controls (Reload, Open in Tab, Exit)
 * - Safe error handling with retry and return options
 */
import React, { useState, useEffect, useRef } from "react";
import { LoadingSpinner } from "../../components/LoadingSpinner.tsx";
import {
  AlertCircleIcon,
  RotateCcwIcon,
  ChevronLeftIcon,
} from "../../components/Icons.tsx";

export interface ShowcaseEmbeddedDemoProps {
  readonly productName: string;
  readonly productCode: string;
  readonly launchUrl: string;
  readonly onBack: () => void;
  readonly backLabel?: string;
  readonly onReload?: () => Promise<string | null | void>;
}

export const ShowcaseEmbeddedDemo: React.FC<ShowcaseEmbeddedDemoProps> = ({
  productName,
  productCode,
  launchUrl,
  onBack,
  backLabel = "Return to Catalog",
  onReload,
}) => {
  const [activeUrl, setActiveUrl] = useState<string>(launchUrl);
  const [isIframeLoading, setIsIframeLoading] = useState<boolean>(true);
  const [iframeKey, setIframeKey] = useState<number>(1);
  const [isReloading, setIsReloading] = useState<boolean>(false);
  const [reloadError, setReloadError] = useState<string | null>(null);
  const prevUrlRef = useRef<string>(launchUrl);

  useEffect(() => {
    setActiveUrl(launchUrl);
    setReloadError(null);
    setIsIframeLoading(true);
    setIframeKey((prev) => prev + 1);
  }, [launchUrl]);

  const handleReload = async () => {
    if (isReloading) return;
    setIsReloading(true);
    setIsIframeLoading(true);
    setReloadError(null);
    prevUrlRef.current = activeUrl;

    if (onReload) {
      try {
        const freshUrl = await onReload();
        if (freshUrl && typeof freshUrl === "string") {
          setActiveUrl(freshUrl);
          if (freshUrl === prevUrlRef.current) {
            setIframeKey((prev) => prev + 1);
          }
        } else {
          setIsIframeLoading(false);
          setReloadError("Failed to obtain a fresh launch grant. Please try again.");
        }
      } catch (err: unknown) {
        setIsIframeLoading(false);
        const msg = err instanceof Error ? err.message : "Failed to reload demo.";
        setReloadError(msg);
      } finally {
        setIsReloading(false);
      }
    } else {
      setIframeKey((prev) => prev + 1);
      setIsReloading(false);
    }
  };

  return (
    <div
      id="showcase-embedded-demo-workspace"
      style={{
        position: "relative",
        width: "100%",
        height: "calc(100dvh - 72px)",
        minHeight: "540px",
        display: "flex",
        flexDirection: "column",
        background: "var(--bg-app, #070b14)",
        overflow: "hidden",
      }}
    >
      {/* Floating Unobtrusive Quick-Action Pill (Top-Right) */}
      <div
        style={{
          position: "absolute",
          top: "12px",
          right: "16px",
          zIndex: 10,
          display: "flex",
          alignItems: "center",
          gap: "6px",
          padding: "4px 8px",
          borderRadius: "999px",
          background: "var(--glass-surface-elevated, rgba(15, 23, 42, 0.88))",
          backdropFilter: "blur(12px)",
          WebkitBackdropFilter: "blur(12px)",
          border: "1px solid var(--border-glass, rgba(255, 255, 255, 0.15))",
          boxShadow: "0 4px 16px rgba(0, 0, 0, 0.35)",
        }}
      >
        <span
          style={{
            fontSize: "0.7rem",
            fontWeight: 700,
            textTransform: "uppercase",
            color: "var(--brand-primary, #6366f1)",
            padding: "2px 6px",
            borderRadius: "4px",
            background: "var(--brand-primary-light, rgba(99, 102, 241, 0.12))",
          }}
        >
          {productCode}
        </span>

        <button
          type="button"
          id="showcase-demo-reload-btn"
          onClick={handleReload}
          disabled={isReloading}
          title="Reload demo with fresh grant"
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: "4px",
            padding: "4px 8px",
            fontSize: "0.75rem",
            fontWeight: 600,
            cursor: isReloading ? "not-allowed" : "pointer",
            borderRadius: "6px",
            border: "none",
            background: "transparent",
            color: "var(--text-secondary, #94a3b8)",
            transition: "color 0.15s ease",
          }}
        >
          <RotateCcwIcon size={12} />
          <span>{isReloading ? "Reloading…" : "Reload"}</span>
        </button>

        <a
          id="showcase-demo-open-tab-btn"
          href={activeUrl}
          target="_blank"
          rel="noopener noreferrer"
          title="Open demo in new tab"
          style={{
            display: "inline-flex",
            alignItems: "center",
            padding: "4px 6px",
            fontSize: "0.75rem",
            color: "var(--text-secondary, #94a3b8)",
            textDecoration: "none",
            borderRadius: "4px",
          }}
        >
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
            <polyline points="15 3 21 3 21 9" />
            <line x1="10" y1="14" x2="21" y2="3" />
          </svg>
        </a>

        <button
          type="button"
          id="showcase-exit-demo-btn"
          onClick={onBack}
          title={backLabel}
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: "3px",
            padding: "4px 8px",
            fontSize: "0.75rem",
            fontWeight: 600,
            cursor: "pointer",
            borderRadius: "6px",
            border: "1px solid var(--border-subtle, rgba(255, 255, 255, 0.1))",
            background: "var(--glass-surface, rgba(255, 255, 255, 0.05))",
            color: "var(--text-primary, #f8fafc)",
          }}
        >
          <ChevronLeftIcon size={12} />
          <span>Catalog</span>
        </button>
      </div>

      {/* Loading Overlay */}
      {isIframeLoading && !reloadError && (
        <div
          id="showcase-demo-loading-state"
          style={{
            position: "absolute",
            inset: 0,
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            justifyContent: "center",
            gap: "1rem",
            background: "var(--bg-app, #070b14)",
            zIndex: 4,
          }}
        >
          <LoadingSpinner
            fullScreen={false}
            label={`Connecting to ${productName} live demo workspace…`}
          />
        </div>
      )}

      {/* Error Recovery State */}
      {reloadError && (
        <div
          id="showcase-demo-reload-error"
          role="alert"
          style={{
            position: "absolute",
            inset: 0,
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            justifyContent: "center",
            gap: "1.25rem",
            padding: "2rem",
            background: "var(--bg-app, #070b14)",
            zIndex: 5,
            textAlign: "center",
          }}
        >
          <div
            style={{
              width: "56px",
              height: "56px",
              borderRadius: "14px",
              background: "var(--status-danger-bg)",
              color: "var(--status-danger)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
            }}
          >
            <AlertCircleIcon size={28} />
          </div>

          <div style={{ maxWidth: "460px" }}>
            <h2 style={{ fontSize: "1.25rem", fontWeight: 700, margin: "0 0 0.5rem 0", color: "var(--text-primary)" }}>
              Unable to Launch Demo
            </h2>
            <p style={{ fontSize: "0.875rem", color: "var(--text-secondary)", margin: 0 }}>
              {reloadError}
            </p>
          </div>

          <div style={{ display: "flex", gap: "0.75rem", marginTop: "0.5rem" }}>
            <button
              type="button"
              className="btn btn-primary"
              onClick={handleReload}
              style={{ display: "inline-flex", alignItems: "center", gap: "0.4rem" }}
            >
              <RotateCcwIcon size={14} />
              <span>Retry Launch</span>
            </button>
            <button
              type="button"
              className="btn btn-secondary"
              onClick={onBack}
            >
              <span>{backLabel}</span>
            </button>
          </div>
        </div>
      )}

      {/* Central Edge-to-Edge Iframe */}
      <iframe
        key={iframeKey}
        id="showcase-demo-iframe"
        title={`${productName} Live Demo Workspace`}
        src={activeUrl}
        onLoad={() => setIsIframeLoading(false)}
        referrerPolicy="strict-origin-when-cross-origin"
        style={{
          width: "100%",
          height: "100%",
          flex: 1,
          border: "none",
          display: reloadError ? "none" : "block",
          background: "#ffffff",
        }}
      />
    </div>
  );
};
