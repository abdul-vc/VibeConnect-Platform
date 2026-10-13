/**
 * Universal Embedded Product Workspace Component.
 *
 * Product-agnostic embedded workspace for all products launched from My Products.
 * Renders an authorized product destination inside the central console content area via an iframe,
 * keeping the top-level VibeConnect console shell, header, and left sidebar intact.
 *
 * Features:
 * - Product-agnostic: Dynamically consumes product metadata without product-specific branching.
 * - Authorized Launch: Consumes ssoApi.launch via the centralized API client.
 * - Responsive Iframe: Fills available console content area without nested scrollbars.
 * - Compact Loading State: Polished spinner and session preparation indicators.
 * - Resilient Error Handling: Detailed error states with safe retry action.
 * - Navigation: Return to My Products action preserving existing console routes.
 */

import React, { useState, useEffect, useCallback, useRef } from "react";
import { ssoApi } from "../../api/sso.ts";
import type { TenantProductAccessItem } from "../../api/types.ts";
import { LoadingSpinner } from "../LoadingSpinner.tsx";
import { ChevronLeftIcon, RotateCcwIcon, AlertCircleIcon, ShieldCheckIcon } from "../Icons.tsx";

export interface EmbeddedProductWorkspaceProps {
  readonly product: TenantProductAccessItem;
  readonly organizationId?: string;
  readonly onBackToProducts: () => void;
}

export const EmbeddedProductWorkspace: React.FC<EmbeddedProductWorkspaceProps> = ({
  product,
  organizationId,
  onBackToProducts,
}) => {
  const [launchUrl, setLaunchUrl] = useState<string | null>(null);
  const [isLaunching, setIsLaunching] = useState<boolean>(true);
  const [launchError, setLaunchError] = useState<string | null>(null);
  const [isIframeLoading, setIsIframeLoading] = useState<boolean>(true);
  const [iframeKey, setIframeKey] = useState<number>(1);

  const isMountedRef = useRef<boolean>(true);

  const initiateLaunch = useCallback(async () => {
    setIsLaunching(true);
    setLaunchError(null);
    setIsIframeLoading(true);

    try {
      const response = await ssoApi.launch({
        product_id: product.id,
        organization_id: organizationId,
      });

      if (!isMountedRef.current) return;

      if (response && response.redirect_url) {
        setLaunchUrl(response.redirect_url);
      } else {
        setLaunchError("Launch service did not return a valid destination URL.");
      }
    } catch (err: unknown) {
      if (!isMountedRef.current) return;
      const detail =
        err && typeof err === "object" && "message" in err
          ? String((err as { message: string }).message)
          : "Failed to resolve product launch session.";
      setLaunchError(detail);
    } finally {
      if (isMountedRef.current) {
        setIsLaunching(false);
      }
    }
  }, [product.id, organizationId]);

  useEffect(() => {
    isMountedRef.current = true;
    void initiateLaunch();

    return () => {
      isMountedRef.current = false;
    };
  }, [initiateLaunch]);

  const handleReloadIframe = () => {
    setIsIframeLoading(true);
    setIframeKey((prev) => prev + 1);
  };

  const handleRetryFullLaunch = () => {
    void initiateLaunch();
  };

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        gap: "1rem",
        width: "100%",
        minWidth: 0,
        height: "100%",
        boxSizing: "border-box",
      }}
    >
      {/* Workspace Top Bar */}
      <div
        style={{
          background: "var(--glass-surface-elevated)",
          border: "1px solid var(--border-glass)",
          borderRadius: "12px",
          padding: "0.75rem 1.25rem",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: "1rem",
          flexWrap: "wrap",
          boxShadow: "var(--shadow-sm)",
          width: "100%",
          boxSizing: "border-box",
        }}
      >
        {/* Left: Back button & Product Info */}
        <div style={{ display: "flex", alignItems: "center", gap: "0.875rem", minWidth: 0 }}>
          <button
            type="button"
            id="workspace-back-btn"
            onClick={onBackToProducts}
            className="btn-secondary"
            title="Return to My Products"
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: "0.4rem",
              padding: "0.45rem 0.85rem",
              fontSize: "0.8125rem",
              fontWeight: 600,
              cursor: "pointer",
            }}
          >
            <ChevronLeftIcon size={14} />
            <span>My Products</span>
          </button>

          <div
            style={{
              height: "20px",
              width: "1px",
              background: "var(--border-subtle)",
            }}
          />

          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", minWidth: 0 }}>
            <span
              style={{
                display: "inline-flex",
                alignItems: "center",
                padding: "0.15rem 0.5rem",
                borderRadius: "5px",
                fontSize: "0.75rem",
                fontWeight: 700,
                background: "rgba(99, 102, 241, 0.12)",
                color: "rgb(99, 102, 241)",
                border: "1px solid rgba(99, 102, 241, 0.25)",
                textTransform: "uppercase",
                letterSpacing: "0.03em",
                whiteSpace: "nowrap",
              }}
            >
              {product.code}
            </span>

            <h1
              id="workspace-product-title"
              style={{
                fontSize: "1.125rem",
                fontWeight: 700,
                margin: 0,
                color: "var(--text-primary)",
                overflow: "hidden",
                textOverflow: "ellipsis",
                whiteSpace: "nowrap",
              }}
            >
              {product.name}
            </h1>
          </div>
        </div>

        {/* Right: Status badge & Actions */}
        <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", flexWrap: "wrap" }}>
          <span
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: "0.35rem",
              fontSize: "0.75rem",
              fontWeight: 600,
              padding: "0.25rem 0.65rem",
              borderRadius: "6px",
              background: launchError
                ? "var(--status-danger-bg)"
                : isLaunching || isIframeLoading
                ? "rgba(99, 102, 241, 0.1)"
                : "var(--status-success-bg)",
              color: launchError
                ? "var(--status-danger)"
                : isLaunching || isIframeLoading
                ? "rgb(99, 102, 241)"
                : "var(--status-success)",
              border: `1px solid ${
                launchError
                  ? "var(--status-danger-border)"
                  : isLaunching || isIframeLoading
                  ? "rgba(99, 102, 241, 0.25)"
                  : "var(--status-success-border)"
              }`,
            }}
          >
            <ShieldCheckIcon size={12} />
            {launchError
              ? "Launch Error"
              : isLaunching
              ? "Authorizing…"
              : isIframeLoading
              ? "Loading Workspace…"
              : "Active Session"}
          </span>

          {launchUrl && !launchError && (
            <button
              type="button"
              id="workspace-reload-btn"
              onClick={handleReloadIframe}
              title="Reload embedded view"
              className="btn-secondary"
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: "0.35rem",
                padding: "0.45rem 0.75rem",
                fontSize: "0.8125rem",
                fontWeight: 600,
                cursor: "pointer",
              }}
            >
              <RotateCcwIcon size={13} />
              <span>Reload</span>
            </button>
          )}
        </div>
      </div>

      {/* Main Workspace Frame Area */}
      <div
        style={{
          background: "var(--glass-surface-elevated)",
          border: "1px solid var(--border-glass)",
          borderRadius: "14px",
          padding: "0.25rem",
          display: "flex",
          flexDirection: "column",
          flex: 1,
          minHeight: "750px",
          height: "calc(100vh - 145px)",
          position: "relative",
          boxShadow: "var(--shadow-sm)",
          overflow: "hidden",
          width: "100%",
          boxSizing: "border-box",
        }}
      >
        {/* Loading Overlay */}
        {(isLaunching || isIframeLoading) && !launchError && (
          <div
            id="workspace-loading-state"
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
              background: "var(--glass-surface-elevated)",
              zIndex: 2,
              borderRadius: "10px",
            }}
          >
            <LoadingSpinner
              fullScreen={false}
              label={
                isLaunching
                  ? `Validating entitlements for ${product.name}…`
                  : `Loading ${product.name} interface into embedded workspace…`
              }
            />
          </div>
        )}

        {/* Error State */}
        {launchError && (
          <div
            id="workspace-error-state"
            style={{
              flex: 1,
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              justifyContent: "center",
              padding: "3rem 1.5rem",
              textAlign: "center",
              borderRadius: "10px",
              background: "var(--glass-surface)",
            }}
          >
            <div
              style={{
                width: "52px",
                height: "52px",
                borderRadius: "14px",
                background: "var(--status-danger-bg)",
                color: "var(--status-danger)",
                display: "inline-flex",
                alignItems: "center",
                justifyContent: "center",
                marginBottom: "1.25rem",
                border: "1px solid var(--status-danger-border)",
              }}
            >
              <AlertCircleIcon size={26} />
            </div>

            <h2
              style={{
                fontSize: "1.25rem",
                fontWeight: 700,
                color: "var(--text-primary)",
                margin: "0 0 0.5rem 0",
              }}
            >
              Unable to Launch {product.name}
            </h2>

            <p
              style={{
                fontSize: "0.875rem",
                color: "var(--text-secondary)",
                maxWidth: "480px",
                margin: "0 0 1.5rem 0",
                lineHeight: 1.5,
              }}
            >
              {launchError}
            </p>

            <div style={{ display: "flex", gap: "0.75rem", flexWrap: "wrap", justifyContent: "center" }}>
              <button
                type="button"
                id="workspace-retry-btn"
                onClick={handleRetryFullLaunch}
                className="btn-primary"
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  gap: "0.4rem",
                  padding: "0.6rem 1.25rem",
                  fontSize: "0.875rem",
                  fontWeight: 600,
                  cursor: "pointer",
                }}
              >
                <RotateCcwIcon size={14} />
                <span>Retry Launch</span>
              </button>

              <button
                type="button"
                onClick={onBackToProducts}
                className="btn-secondary"
                style={{
                  padding: "0.6rem 1.25rem",
                  fontSize: "0.875rem",
                  fontWeight: 600,
                  cursor: "pointer",
                }}
              >
                Return to My Products
              </button>
            </div>
          </div>
        )}

        {/* Central Iframe */}
        {launchUrl && !launchError && (
          <iframe
            key={iframeKey}
            id="embedded-product-iframe"
            title={`${product.name} Workspace`}
            src={launchUrl}
            onLoad={() => setIsIframeLoading(false)}
            sandbox="allow-same-origin allow-scripts allow-forms allow-popups allow-downloads"
            referrerPolicy="strict-origin-when-cross-origin"
            style={{
              width: "100%",
              height: "100%",
              flex: 1,
              border: "none",
              borderRadius: "10px",
              background: "#ffffff",
              display: isIframeLoading ? "none" : "block",
            }}
          />
        )}
      </div>
    </div>
  );
};
