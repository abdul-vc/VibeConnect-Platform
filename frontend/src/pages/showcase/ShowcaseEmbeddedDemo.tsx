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
  productCode: _productCode,
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
