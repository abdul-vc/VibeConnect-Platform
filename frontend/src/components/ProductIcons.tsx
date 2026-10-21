/**
 * Enterprise Product Vector Icons & Theme System.
 *
 * Provides tailored, high-precision SVG vector icons for each VibeConnect catalog product.
 * Replaces rudimentary 2-letter initials with bespoke, professional SaaS iconography.
 */
import React from "react";

interface ProductTheme {
  readonly gradient: string;
  readonly shadow: string;
  readonly iconColor: string;
  readonly border: string;
  readonly label: string;
}

const PRODUCT_THEMES: Record<string, ProductTheme> = {
  lms: {
    gradient: "linear-gradient(135deg, #2563eb 0%, #1d4ed8 100%)",
    shadow: "rgba(37, 99, 235, 0.28)",
    iconColor: "#ffffff",
    border: "rgba(37, 99, 235, 0.4)",
    label: "Learning Management System",
  },
  hrms: {
    gradient: "linear-gradient(135deg, #059669 0%, #047857 100%)",
    shadow: "rgba(5, 150, 105, 0.28)",
    iconColor: "#ffffff",
    border: "rgba(5, 150, 105, 0.4)",
    label: "Human Resource Management",
  },
  "vms-warehouse": {
    gradient: "linear-gradient(135deg, #d97706 0%, #b45309 100%)",
    shadow: "rgba(217, 119, 6, 0.28)",
    iconColor: "#ffffff",
    border: "rgba(217, 119, 6, 0.4)",
    label: "Warehouse Management System",
  },
  leasing: {
    gradient: "linear-gradient(135deg, #7c3aed 0%, #6d28d9 100%)",
    shadow: "rgba(124, 58, 237, 0.28)",
    iconColor: "#ffffff",
    border: "rgba(124, 58, 237, 0.4)",
    label: "Leasing & Property Management",
  },
  fieldsense: {
    gradient: "linear-gradient(135deg, #0284c7 0%, #0369a1 100%)",
    shadow: "rgba(2, 132, 199, 0.28)",
    iconColor: "#ffffff",
    border: "rgba(2, 132, 199, 0.4)",
    label: "FieldSense Operations Hub",
  },
  inventory: {
    gradient: "linear-gradient(135deg, #e11d48 0%, #be123c 100%)",
    shadow: "rgba(225, 29, 72, 0.28)",
    iconColor: "#ffffff",
    border: "rgba(225, 29, 72, 0.4)",
    label: "Inventory Management",
  },
  "crm-logicon": {
    gradient: "linear-gradient(135deg, #4f46e5 0%, #4338ca 100%)",
    shadow: "rgba(79, 70, 229, 0.28)",
    iconColor: "#ffffff",
    border: "rgba(79, 70, 229, 0.4)",
    label: "Logicon CRM",
  },
  mom: {
    gradient: "linear-gradient(135deg, #475569 0%, #334155 100%)",
    shadow: "rgba(71, 85, 105, 0.28)",
    iconColor: "#ffffff",
    border: "rgba(71, 85, 105, 0.4)",
    label: "Minutes of Meeting",
  },
  qbr: {
    gradient: "linear-gradient(135deg, #15803d 0%, #166534 100%)",
    shadow: "rgba(21, 128, 61, 0.28)",
    iconColor: "#ffffff",
    border: "rgba(21, 128, 61, 0.4)",
    label: "QBR – Excel Reports",
  },
  "audit-smart": {
    gradient: "linear-gradient(135deg, #dc2626 0%, #991b1b 100%)",
    shadow: "rgba(220, 38, 38, 0.28)",
    iconColor: "#ffffff",
    border: "rgba(220, 38, 38, 0.4)",
    label: "Audit Smart Compliance",
  },
  "vendor-invoice-management": {
    gradient: "linear-gradient(135deg, #0d9488 0%, #0f766e 100%)",
    shadow: "rgba(13, 148, 136, 0.28)",
    iconColor: "#ffffff",
    border: "rgba(13, 148, 136, 0.4)",
    label: "Vendor & Invoice Management",
  },
  quiz: {
    gradient: "linear-gradient(135deg, #ca8a04 0%, #a16207 100%)",
    shadow: "rgba(202, 138, 4, 0.28)",
    iconColor: "#ffffff",
    border: "rgba(202, 138, 4, 0.4)",
    label: "Interactive Quiz Hub",
  },
  "workshop-trinity": {
    gradient: "linear-gradient(135deg, #3b82f6 0%, #1d4ed8 100%)",
    shadow: "rgba(59, 130, 246, 0.28)",
    iconColor: "#ffffff",
    border: "rgba(59, 130, 246, 0.4)",
    label: "Trinity Workshop",
  },
  fieldops: {
    gradient: "linear-gradient(135deg, #ea580c 0%, #c2410c 100%)",
    shadow: "rgba(234, 88, 12, 0.28)",
    iconColor: "#ffffff",
    border: "rgba(234, 88, 12, 0.4)",
    label: "FieldOps Suite",
  },
  workhub: {
    gradient: "linear-gradient(135deg, #c026d3 0%, #a21caf 100%)",
    shadow: "rgba(192, 38, 211, 0.28)",
    iconColor: "#ffffff",
    border: "rgba(192, 38, 211, 0.4)",
    label: "WorkHub Workspace",
  },
  "ai-dashboard": {
    gradient: "linear-gradient(135deg, #8b5cf6 0%, #6d28d9 100%)",
    shadow: "rgba(139, 92, 246, 0.28)",
    iconColor: "#ffffff",
    border: "rgba(139, 92, 246, 0.4)",
    label: "Cognitive AI Dashboard",
  },
  "event-module": {
    gradient: "linear-gradient(135deg, #db2777 0%, #9d174d 100%)",
    shadow: "rgba(219, 39, 119, 0.28)",
    iconColor: "#ffffff",
    border: "rgba(219, 39, 119, 0.4)",
    label: "Divine Connect Events",
  },
  "video-content-generation": {
    gradient: "linear-gradient(135deg, #e11d48 0%, #9f1239 100%)",
    shadow: "rgba(225, 29, 72, 0.28)",
    iconColor: "#ffffff",
    border: "rgba(225, 29, 72, 0.4)",
    label: "Video Studio Pro",
  },
  ats: {
    gradient: "linear-gradient(135deg, #0284c7 0%, #075985 100%)",
    shadow: "rgba(2, 132, 199, 0.28)",
    iconColor: "#ffffff",
    border: "rgba(2, 132, 199, 0.4)",
    label: "Applicant Tracking System",
  },
  "sales-tracker": {
    gradient: "linear-gradient(135deg, #16a34a 0%, #15803d 100%)",
    shadow: "rgba(22, 163, 74, 0.28)",
    iconColor: "#ffffff",
    border: "rgba(22, 163, 74, 0.4)",
    label: "Sales Pulse Tracker",
  },
};

const DEFAULT_THEME: ProductTheme = {
  gradient: "linear-gradient(135deg, #6366f1 0%, #4338ca 100%)",
  shadow: "rgba(99, 102, 241, 0.28)",
  iconColor: "#ffffff",
  border: "rgba(99, 102, 241, 0.4)",
  label: "Platform Product",
};

export function getProductTheme(code: string): ProductTheme {
  const normalized = (code || "").toLowerCase().trim();
  return PRODUCT_THEMES[normalized] || DEFAULT_THEME;
}

interface ProductIconProps {
  readonly code: string;
  readonly size?: number;
  readonly className?: string;
  readonly style?: React.CSSProperties;
}

export const ProductIcon: React.FC<ProductIconProps> = ({
  code,
  size = 38,
  className = "",
  style,
}) => {
  const theme = getProductTheme(code);
  const normalized = (code || "").toLowerCase().trim();
  const iconPixelSize = Math.max(16, Math.round(size * 0.54));

  const renderIconPaths = () => {
    switch (normalized) {
      case "lms":
        // Graduation cap / Academic learning
        return (
          <>
            <path d="M22 10v6M2 10l10-5 10 5-10 5z" />
            <path d="M6 12v5c3 3 9 3 12 0v-5" />
          </>
        );

      case "hrms":
        // People network / Organization
        return (
          <>
            <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" />
            <circle cx="9" cy="7" r="4" />
            <path d="M22 21v-2a4 4 0 0 0-3-3.87" />
            <path d="M16 3.13a4 4 0 0 1 0 7.75" />
          </>
        );

      case "vms-warehouse":
        // Warehouse Depot & Logistics Pallet
        return (
          <>
            <path d="M3 21h18M3 7v14M21 7v14M3 7l9-4 9 4" />
            <path d="M9 21v-7a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2v7" />
            <path d="M7 11h2M15 11h2" />
          </>
        );

      case "leasing":
        // Commercial Office Building / Real Estate
        return (
          <>
            <rect width="16" height="20" x="4" y="2" rx="2" ry="2" />
            <path d="M9 22v-4h6v4" />
            <path d="M8 6h.01M16 6h.01M12 6h.01M12 10h.01M16 10h.01M8 10h.01M12 14h.01M16 14h.01M8 14h.01" />
          </>
        );

      case "fieldsense":
        // Sensor telemetry & radar wave broadcast
        return (
          <>
            <circle cx="12" cy="12" r="2.5" />
            <path d="M16.24 7.76a6 6 0 0 1 0 8.49M7.76 16.24a6 6 0 0 1 0-8.49" />
            <path d="M19.07 4.93a10 10 0 0 1 0 14.14M4.93 19.07a10 10 0 0 1 0-14.14" />
          </>
        );

      case "inventory":
        // 3D Isometric Stacked Crates
        return (
          <>
            <path d="m7.5 4.27 9 5.15M21 8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16Z" />
            <path d="m3.3 7 8.7 5 8.7-5M12 22V12" />
          </>
        );

      case "crm-logicon":
        // Customer Relations & Partnership Target
        return (
          <>
            <circle cx="12" cy="8" r="4" />
            <path d="M6 21v-2a6 6 0 0 1 12 0v2" />
            <path d="m15 11 2 2 4-4" />
          </>
        );

      case "mom":
        // Meeting minutes ledger with checklist
        return (
          <>
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
            <polyline points="14 2 14 8 20 8" />
            <line x1="16" x2="8" y1="13" y2="13" />
            <line x1="16" x2="8" y1="17" y2="17" />
            <polyline points="10 9 9 9 8 9" />
          </>
        );

      case "qbr":
        // Executive Financial Spreadsheet & Growth Graph
        return (
          <>
            <rect width="18" height="18" x="3" y="3" rx="2" />
            <path d="M3 9h18M3 15h18M9 3v18M15 3v18" />
          </>
        );

      case "audit-smart":
        // Compliance Shield with Security Verification
        return (
          <>
            <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10" />
            <path d="m9 12 2 2 4-4" />
          </>
        );

      case "vendor-invoice-management":
        // Commercial Receipt & Billing Ledger
        return (
          <>
            <rect width="16" height="20" x="4" y="2" rx="2" />
            <line x1="8" x2="16" y1="6" y2="6" />
            <line x1="8" x2="16" y1="10" y2="10" />
            <line x1="8" x2="12" y1="14" y2="14" />
            <circle cx="15" cy="15" r="1.5" />
          </>
        );

      case "quiz":
        // Academic Award Trophy / Gamified Quiz Badge
        return (
          <>
            <path d="M6 9H4.5a2.5 2.5 0 0 1 0-5H6M18 9h1.5a2.5 2.5 0 0 0 0-5H18" />
            <path d="M4 22h16M10 14.66V17c0 .55-.45 1-1 1H8c-.55 0-1 .45-1 1v1h10v-1c0-.55-.45-1-1-1h-1c-.55 0-1-.45-1-1v-2.34" />
            <path d="M18 4H6v7a6 6 0 0 0 12 0V4Z" />
          </>
        );

      case "workshop-trinity":
        // Mechanical Engineering Tools
        return (
          <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z" />
        );

      case "fieldops":
        // Navigation Compass & Operations Pointer
        return (
          <>
            <circle cx="12" cy="12" r="10" />
            <polygon points="16.24 7.76 14.12 14.12 7.76 16.24 9.88 9.88 16.24 7.76" />
          </>
        );

      case "workhub":
        // Centralized Application Dock & Multi-workspace Grid
        return (
          <>
            <rect width="7" height="9" x="3" y="3" rx="1.5" />
            <rect width="7" height="5" x="14" y="3" rx="1.5" />
            <rect width="7" height="9" x="14" y="12" rx="1.5" />
            <rect width="7" height="5" x="3" y="16" rx="1.5" />
          </>
        );

      case "ai-dashboard":
        // Neural AI Sparkle & Cognitive Core
        return (
          <>
            <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83" />
            <circle cx="12" cy="12" r="3.5" />
          </>
        );

      case "event-module":
        // Event Stage & Conference Calendar
        return (
          <>
            <rect width="18" height="18" x="3" y="4" rx="2" ry="2" />
            <line x1="16" x2="16" y1="2" y2="6" />
            <line x1="8" x2="8" y1="2" y2="6" />
            <line x1="3" x2="21" y1="10" y2="10" />
            <polygon points="12 13 13.5 16 17 16.5 14.5 18.8 15 22.3 12 20.6 9 22.3 9.5 18.8 7 16.5 10.5 16 12 13" />
          </>
        );

      case "video-content-generation":
        // Studio Cinema Slate & Video Camera
        return (
          <>
            <path d="m22 8-6 4 6 4V8Z" />
            <rect width="14" height="12" x="2" y="6" rx="2" />
            <circle cx="9" cy="12" r="2" />
          </>
        );

      case "ats":
        // Applicant Tracking & Talent Recruitment
        return (
          <>
            <circle cx="10" cy="8" r="4" />
            <path d="M2 20v-2a6 6 0 0 1 12 0v2M19 11v6M22 14h-6" />
          </>
        );

      case "sales-tracker":
        // High-velocity Growth Revenue Trend
        return (
          <>
            <polyline points="22 7 13.5 15.5 8.5 10.5 2 17" />
            <polyline points="16 7 22 7 22 13" />
          </>
        );

      default:
        // Universal Product Cube
        return (
          <>
            <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z" />
            <polyline points="3.27 6.96 12 12.01 20.73 6.96" />
            <line x1="12" y1="22.08" x2="12" y2="12" />
          </>
        );
    }
  };

  const borderRadius = size >= 48 ? "14px" : size >= 36 ? "10px" : "8px";

  return (
    <div
      className={`product-icon-container ${className}`}
      style={{
        width: `${size}px`,
        height: `${size}px`,
        minWidth: `${size}px`,
        minHeight: `${size}px`,
        borderRadius,
        background: theme.gradient,
        color: theme.iconColor,
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        flexShrink: 0,
        boxShadow: `0 3px 12px ${theme.shadow}`,
        boxSizing: "border-box",
        border: `1px solid ${theme.border}`,
        position: "relative",
        userSelect: "none",
        ...style,
      }}
      aria-label={theme.label}
      title={theme.label}
    >
      <svg
        width={iconPixelSize}
        height={iconPixelSize}
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
        style={{
          filter: "drop-shadow(0 1px 1px rgba(0,0,0,0.25))",
          flexShrink: 0,
        }}
      >
        {renderIconPaths()}
      </svg>
    </div>
  );
};
