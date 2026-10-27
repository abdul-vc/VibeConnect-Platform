/**
 * Universal Embedded Product Workspace Component.
 *
 * Product-agnostic embedded workspace for all products launched from My Products or Sidebar.
 * Renders an authorized product destination inside the central console content area via an edge-to-edge iframe,
 * keeping the top-level VibeConnect console shell, header, and left sidebar intact.
 */

import React, { useState, useEffect, useCallback, useRef } from "react";
import { ssoApi } from "../../api/sso.ts";
import type { TenantProductAccessItem } from "../../api/types.ts";
import { LoadingSpinner } from "../LoadingSpinner.tsx";
import { RotateCcwIcon, AlertCircleIcon } from "../Icons.tsx";

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

  const isMountedRef = useRef<boolean>(true);
  const launchGenRef = useRef<number>(0);

  const initiateLaunch = useCallback(async () => {
    const currentGen = ++launchGenRef.current;
    setIsLaunching(true);
    setLaunchError(null);
    setIsIframeLoading(true);
    setLaunchUrl(null);

    try {
      const response = await ssoApi.launch({
        product_id: product.id,
        organization_id: organizationId,
      });

      if (!isMountedRef.current || currentGen !== launchGenRef.current) return;

      if (response && response.redirect_url) {
        try {
          sessionStorage.setItem("vc_tenant_products_revealed", "true");
          window.dispatchEvent(new CustomEvent("vibeconnect:tenant-product-launched"));
        } catch {
          // Safe fallback
        }
        setLaunchUrl(response.redirect_url);
      } else {
        setLaunchError("Launch service did not return a valid destination URL.");
      }
    } catch (err: unknown) {
      if (!isMountedRef.current || currentGen !== launchGenRef.current) return;
      const detail =
        err && typeof err === "object" && "message" in err
          ? String((err as { message: string }).message)
          : "Failed to resolve product launch session.";
      setLaunchError(detail);
    } finally {
      if (isMountedRef.current && currentGen === launchGenRef.current) {
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

  const handleRetryFullLaunch = () => {
    void initiateLaunch();
  };

  return (
    <div
      style={{
        position: "relative",
        width: "100%",
        height: "calc(100dvh - 72px)",
        minHeight: "600px",
        display: "flex",
        flexDirection: "column",
        borderRadius: "8px",
        overflow: "hidden",
        boxSizing: "border-box",
        background: "var(--glass-surface-elevated)",
        border: "1px solid var(--border-subtle)",
      }}
    >
      {/* Workspace Controls Header */}
      <div
        id="workspace-top-bar"
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "0.6rem 1rem",
          background: "var(--glass-surface)",
          borderBottom: "1px solid var(--border-subtle)",
          zIndex: 10,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
          <span style={{ fontSize: "0.875rem", color: "var(--text-primary)", fontWeight: 700 }}>
            {product.name}
          </span>
          <span
            style={{
              fontSize: "0.75rem",
              color: "var(--text-secondary)",
              background: "var(--glass-surface-elevated)",
              padding: "0.15rem 0.5rem",
              borderRadius: "4px",
              border: "1px solid var(--border-subtle)",
              fontWeight: 600,
            }}
          >
            {product.code}
          </span>
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
          {launchUrl && (
            <button
              type="button"
              id="workspace-open-new-window-btn"
              onClick={() => window.open(launchUrl, "_blank", "noopener,noreferrer")}
              className="btn-primary"
              style={{
                padding: "0.35rem 0.75rem",
                fontSize: "0.75rem",
                fontWeight: 600,
                cursor: "pointer",
                display: "inline-flex",
                alignItems: "center",
                gap: "4px",
              }}
              title="Open product workspace in a new browser window"
            >
              <span>Open in New Window ↗</span>
            </button>
          )}
          <button
            type="button"
            onClick={onBackToProducts}
            className="btn-secondary"
            style={{
              padding: "0.35rem 0.75rem",
              fontSize: "0.75rem",
              fontWeight: 600,
              cursor: "pointer",
            }}
          >
            Return to My Products
          </button>
        </div>
      </div>

      {/* Workspace Header Toolbar */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "0.5rem 1rem",
          background: "var(--glass-surface)",
          borderBottom: "1px solid var(--border-subtle)",
          minHeight: "44px",
          boxSizing: "border-box",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
          <button
            type="button"
            onClick={onBackToProducts}
            className="btn-secondary"
            style={{ padding: "0.25rem 0.6rem", fontSize: "0.75rem", minHeight: "28px" }}
          >
            ← My Products
          </button>
          <span style={{ fontWeight: 600, fontSize: "0.875rem", color: "var(--text-primary)" }}>
            {product.name}
          </span>
          <span
            className="badge badge-neutral"
            style={{ fontSize: "0.6875rem", textTransform: "uppercase" }}
          >
            {product.code}
          </span>
        </div>
      </div>

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
          }}
        >
          <LoadingSpinner
            fullScreen={false}
            label={
              isLaunching
                ? `Validating entitlements for ${product.name} (${product.code})…`
                : `Loading ${product.name} (${product.code}) workspace…`
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

      {/* Central Full-Size Iframe */}
      {launchUrl && !launchError && (
        <iframe
          key={launchUrl || product.id}
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
            borderRadius: 0,
            background: "#ffffff",
            display: isIframeLoading ? "none" : "block",
          }}
        />
      )}
    </div>
  );
};
