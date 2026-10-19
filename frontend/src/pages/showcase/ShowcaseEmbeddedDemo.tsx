/**
 * ShowcaseEmbeddedDemo – Embedded live product demo workspace.
 *
 * Renders an authorized live demo session inside the Platform Owner Console
 * central workspace without top-level browser redirects or tab popups.
 *
 * For HRMS:
 * - Defaults directly to the no-login Live Demonstration Console powered by
 *   verified server-side JWT proxy connections, preventing upstream login screens.
 * - Provides immediate navigation to all 6 verified modules.
 * - Includes an upstream application tab with clear provider SSO documentation.
 */

import React, { useState } from "react";
import { LoadingSpinner } from "../../components/LoadingSpinner.tsx";
import {
  ChevronLeftIcon,
  RotateCcwIcon,
  ShieldCheckIcon,
  LayersIcon,
  BoxIcon,
  AlertCircleIcon,
  ExternalLinkIcon,
  CloseIcon,
} from "../../components/Icons.tsx";
import { VmsLiveShowcase } from "./VmsLiveShowcase.tsx";

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
  const isHrms = productCode.toLowerCase() === "hrms";
  const isVms =
    productCode.toLowerCase() === "vms-warehouse" ||
    productCode.toLowerCase() === "vms";
  const isFieldSense =
    productCode.toLowerCase() === "fieldsense" ||
    productCode.toLowerCase() === "fieldsence";
  const isSsoLaunch =
    Boolean(launchUrl) &&
    (launchUrl.includes("/sso/") ||
      launchUrl.includes("code=") ||
      launchUrl.includes("ticket="));

  // Only VMS unconfigured sandbox defaults to insights; HRMS and others launch live app
  const [activeTab, setActiveTab] = useState<"app" | "insights">(
    isVms && !isSsoLaunch ? "insights" : "app"
  );
  const [isIframeLoading, setIsIframeLoading] = useState<boolean>(true);
  const [iframeError, setIframeError] = useState<boolean>(false);
  const [iframeKey, setIframeKey] = useState<number>(1);

  const handleReload = () => {
    if (activeTab === "app") {
      setIsIframeLoading(true);
      setIframeError(false);
      setIframeKey((prev) => prev + 1);
    }
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
              {productName} Live Demo
            </h2>
          </div>
        </div>

        {/* Center: In-Window View Tabs if VMS (Demo Console vs Upstream Live Application) */}
        {isVms && (
          <div
            id="vms-workspace-tab-group"
            style={{
              display: "flex",
              background: "var(--glass-surface-sunken, rgba(4, 8, 18, 0.6))",
              borderRadius: "8px",
              padding: "3px",
              border: "1px solid var(--border-glass, rgba(255, 255, 255, 0.1))",
              gap: "2px",
            }}
          >
            <button
              type="button"
              id="vms-tab-api-insights-btn"
              onClick={() => setActiveTab("insights")}
              style={{
                padding: "0.35rem 0.85rem",
                borderRadius: "6px",
                fontSize: "0.8rem",
                fontWeight: 600,
                border: "none",
                cursor: "pointer",
                background: activeTab === "insights" ? "var(--brand-primary, #6366f1)" : "transparent",
                color: activeTab === "insights" ? "#ffffff" : "var(--text-secondary, #94a3b8)",
                display: "inline-flex",
                alignItems: "center",
                gap: "0.4rem",
                transition: "all 0.15s ease",
              }}
            >
              <LayersIcon size={14} />
              <span>API Metrics & Insights</span>
            </button>

            <button
              type="button"
              id="vms-tab-live-app-btn"
              onClick={() => setActiveTab("app")}
              style={{
                padding: "0.35rem 0.85rem",
                borderRadius: "6px",
                fontSize: "0.8rem",
                fontWeight: 600,
                border: "none",
                cursor: "pointer",
                background: activeTab === "app" ? "var(--brand-primary, #6366f1)" : "transparent",
                color: activeTab === "app" ? "#ffffff" : "var(--text-secondary, #94a3b8)",
                display: "inline-flex",
                alignItems: "center",
                gap: "0.4rem",
                transition: "all 0.15s ease",
              }}
            >
              <BoxIcon size={14} />
              <span>Live Application</span>
            </button>
          </div>
        )}

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
              background: "var(--status-success-bg, rgba(16, 185, 129, 0.12))",
              color: "var(--status-success, #10b981)",
              border: "1px solid var(--status-success-border, rgba(16, 185, 129, 0.25))",
            }}
          >
            <ShieldCheckIcon size={12} />
            <span>
              {activeTab === "insights"
                ? isVms
                  ? "WarehouseOS Sandbox · Live API"
                  : "PeoplePulse Sandbox · Live API"
                : isIframeLoading
                ? `Connecting ${productName}…`
                : isVms && isSsoLaunch
                ? "WarehouseOS · Live SSO Session"
                : isHrms && isSsoLaunch
                ? "PeoplePulse · Live SSO Session"
                : isFieldSense
                ? "FieldSense Hub · Live Sandbox"
                : "Live Application Embedded"}
            </span>
          </span>

          {activeTab === "app" && (
            <>
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

              <button
                type="button"
                id="showcase-demo-newtab-btn"
                onClick={() => window.open(launchUrl, "_blank", "noopener,noreferrer")}
                title="Open demo in a separate browser tab"
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
                <ExternalLinkIcon size={13} />
                <span>Open in Tab</span>
              </button>
            </>
          )}

          <button
            type="button"
            id="showcase-demo-close-btn"
            onClick={onBack}
            title="Close demo panel"
            style={{
              display: "inline-flex",
              alignItems: "center",
              justifyContent: "center",
              width: "32px",
              height: "32px",
              padding: 0,
              cursor: "pointer",
              borderRadius: "6px",
              border: "1px solid var(--border-glass, rgba(255, 255, 255, 0.15))",
              background: "var(--glass-surface, rgba(255, 255, 255, 0.05))",
              color: "var(--text-secondary, #94a3b8)",
              transition: "all 0.15s ease",
            }}
          >
            <CloseIcon size={15} />
          </button>
        </div>
      </div>

      {/* Main Workspace Frame Area */}
      <div
        id="showcase-embedded-canvas"
        style={{
          background: "var(--glass-surface-elevated, rgba(15, 23, 42, 0.95))",
          border: "1px solid var(--border-glass, rgba(255, 255, 255, 0.14))",
          borderRadius: "12px",
          padding: activeTab === "insights" ? "1rem" : "0.25rem",
          display: "flex",
          flexDirection: "column",
          flex: 1,
          minHeight: "700px",
          height: "calc(100vh - 170px)",
          position: "relative",
          boxShadow: "var(--shadow-sm)",
          overflow: activeTab === "insights" ? "auto" : "hidden",
          width: "100%",
          boxSizing: "border-box",
        }}
      >
        {isVms && activeTab === "insights" && (
          <div style={{ width: "100%", maxWidth: "1280px", margin: "0 auto", overflowY: "auto" }}>
            <VmsLiveShowcase
              isEmbedded={true}
              onLaunchExternal={() => window.open(launchUrl, "_blank", "noopener,noreferrer")}
            />
          </div>
        )}

        {isVms && activeTab === "app" && !isSsoLaunch && (
          <div
            style={{
              padding: "0.75rem 1rem",
              background: "rgba(59, 130, 246, 0.1)",
              borderBottom: "1px solid rgba(59, 130, 246, 0.2)",
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              gap: "0.75rem",
              fontSize: "0.8rem",
              color: "var(--text-secondary)",
              zIndex: 3,
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
              <AlertCircleIcon size={16} />
              <span>
                <strong>Notice:</strong> The upstream WarehouseOS application blocks iframe embedding via X-Frame-Options: DENY. For presentation without login screens, use the <strong>API Metrics & Insights</strong> tab or open the application in a separate browser tab.
              </span>
            </div>
            <div style={{ display: "flex", gap: "0.5rem" }}>
              <button
                type="button"
                onClick={() => window.open(launchUrl, "_blank", "noopener,noreferrer")}
                style={{
                  padding: "0.25rem 0.65rem",
                  borderRadius: "5px",
                  background: "var(--brand-primary, #3b82f6)",
                  border: "none",
                  color: "#ffffff",
                  fontSize: "0.75rem",
                  fontWeight: 600,
                  cursor: "pointer",
                  whiteSpace: "nowrap",
                }}
              >
                Open in New Tab
              </button>
              <button
                type="button"
                onClick={() => setActiveTab("insights")}
                style={{
                  padding: "0.25rem 0.65rem",
                  borderRadius: "5px",
                  background: "rgba(255, 255, 255, 0.1)",
                  border: "1px solid rgba(255, 255, 255, 0.15)",
                  color: "#ffffff",
                  fontSize: "0.75rem",
                  fontWeight: 600,
                  cursor: "pointer",
                  whiteSpace: "nowrap",
                }}
              >
                Switch to Demo Console
              </button>
            </div>
          </div>
        )}

        {/* Loading Overlay for App Iframe */}
        {activeTab === "app" && isIframeLoading && !iframeError && (
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
              label={`Loading ${productName} live application…`}
            />
          </div>
        )}

        {/* App Error State if iframe fails to render */}
        {activeTab === "app" && iframeError && (
          <div
            id="showcase-demo-error-state"
            style={{
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              justifyContent: "center",
              flex: 1,
              padding: "2.5rem 1.5rem",
              textAlign: "center",
              gap: "1rem",
              background: "var(--glass-surface-elevated, rgba(15, 23, 42, 0.95))",
              borderRadius: "10px",
            }}
          >
            <div
              style={{
                width: "48px",
                height: "48px",
                borderRadius: "50%",
                background: "rgba(239, 68, 68, 0.12)",
                border: "1px solid rgba(239, 68, 68, 0.25)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
              }}
            >
              <AlertCircleIcon size={24} color="var(--status-danger, #ef4444)" />
            </div>
            <h3 style={{ margin: 0, fontSize: "1.1rem", fontWeight: 700, color: "var(--text-primary, #f8fafc)" }}>
              Unable to Display Live Demo in Frame
            </h3>
            <p style={{ maxWidth: "460px", margin: 0, fontSize: "0.85rem", color: "var(--text-secondary, #94a3b8)", lineHeight: 1.5 }}>
              The application could not be rendered inside the in-page frame. You can launch the authenticated session directly in a separate browser tab.
            </p>
            <div style={{ display: "flex", gap: "0.75rem", marginTop: "0.5rem" }}>
              <button
                type="button"
                className="btn-primary"
                onClick={() => window.open(launchUrl, "_blank", "noopener,noreferrer")}
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  gap: "0.4rem",
                  padding: "0.5rem 1rem",
                  fontSize: "0.85rem",
                  fontWeight: 600,
                  borderRadius: "6px",
                  cursor: "pointer",
                }}
              >
                <ExternalLinkIcon size={14} />
                <span>Open in New Tab</span>
              </button>
              <button
                type="button"
                className="btn-secondary"
                onClick={handleReload}
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  gap: "0.4rem",
                  padding: "0.5rem 1rem",
                  fontSize: "0.85rem",
                  fontWeight: 600,
                  borderRadius: "6px",
                  cursor: "pointer",
                }}
              >
                <RotateCcwIcon size={14} />
                <span>Retry</span>
              </button>
            </div>
          </div>
        )}

        {/* Central Iframe embedding the actual product application */}
        {!iframeError && (
          <iframe
            key={iframeKey}
            id="showcase-demo-iframe"
            data-testid="showcase-demo-iframe"
            title={`${productName} Live Demo Workspace`}
            src={launchUrl}
            onLoad={() => setIsIframeLoading(false)}
            onError={() => {
              setIsIframeLoading(false);
              setIframeError(true);
            }}
            sandbox="allow-same-origin allow-scripts allow-forms allow-popups allow-downloads allow-modals"
            allow="clipboard-read; clipboard-write; fullscreen"
            referrerPolicy="strict-origin-when-cross-origin"
            style={{
              width: "100%",
              height: "100%",
              flex: 1,
              border: "none",
              borderRadius: "8px",
              background: "#ffffff",
              display: activeTab === "app" ? "block" : "none",
              opacity: isIframeLoading ? 0 : 1,
              transition: "opacity 0.2s ease-in-out",
            }}
          />
        )}
      </div>
    </div>
  );
};
