/**
 * Master Setup Foundation Page.
 *
 * Executive-grade control plane overview for VibeConnect Platform Owners.
 * High-density enterprise layout, 4-column balanced responsive grid,
 * and standardized, truthful security status overview.
 */

import React from "react";
import { AppShell } from "../components/AppShell.tsx";
import { useAuth } from "../context/AuthContext.tsx";
import {
  ShieldCheckIcon,
  LockIcon,
  CheckCircleIcon,
  UserIcon,
} from "../components/Icons.tsx";

export const MasterSetupPage: React.FC = () => {
  const { user } = useAuth();

  const securityFeatures = [
    {
      title: "Session Protection",
      status: "Active",
      badgeClass: "badge-success",
      description: "Server-side session with isolated cookies.",
      icon: <LockIcon size={18} />,
    },
    {
      title: "Platform Owner Access",
      status: "Authorized",
      badgeClass: "badge-success",
      description: "Backend authorization verified for this session.",
      icon: <UserIcon size={18} />,
    },
    {
      title: "Browser Token Policy",
      status: "Server-side",
      badgeClass: "badge-success",
      description: "Authentication tokens are not stored in browser storage.",
      icon: <ShieldCheckIcon size={18} />,
    },
    {
      title: "Login Rate Protection",
      status: "Protected",
      badgeClass: "badge-success",
      description: "Authentication attempts use endpoint-scoped throttling.",
      icon: <CheckCircleIcon size={18} />,
    },
  ];

  return (
    <AppShell>
      <div style={{ display: "flex", flexDirection: "column", gap: "1.75rem", minWidth: 0 }}>
        {/* Welcome Header */}
        <div style={{ display: "flex", flexDirection: "column", gap: "0.375rem" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", flexWrap: "wrap" }}>
            <h1 className="heading-hero" style={{ fontSize: "1.625rem" }}>
              Control Plane Overview
            </h1>
            <span className="badge badge-success" style={{ padding: "0.25rem 0.625rem" }}>
              <CheckCircleIcon size={12} />
              Session Verified
            </span>
          </div>
          <p className="text-body" style={{ maxWidth: "780px", fontSize: "0.875rem" }}>
            Welcome, <strong style={{ color: "var(--text-primary)" }}>{user?.full_name || user?.email}</strong>. Your authenticated Platform Owner session is active. VibeConnect’s secure control-plane foundation is ready for the next administrative modules.
          </p>
        </div>

        {/* 4-Card Responsive Grid (Resizes naturally with grid layout) */}
        <div className="security-cards-grid">
          {securityFeatures.map((item, index) => (
            <div
              key={index}
              className="overview-card"
            >
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  marginBottom: "0.875rem",
                }}
              >
                <div
                  style={{
                    width: "36px",
                    height: "36px",
                    borderRadius: "8px",
                    background: "var(--brand-primary-light)",
                    color: "var(--brand-primary)",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    flexShrink: 0,
                  }}
                >
                  {item.icon}
                </div>
                <span className={`badge ${item.badgeClass}`}>{item.status}</span>
              </div>
              <h2 className="heading-subtitle" style={{ fontSize: "0.9375rem", marginBottom: "0.35rem" }}>
                {item.title}
              </h2>
              <p className="text-caption" style={{ lineHeight: 1.5, margin: 0 }}>
                {item.description}
              </p>
            </div>
          ))}
        </div>

        {/* Foundation Readiness Card */}
        <div className="status-overview-panel">
          <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
            <div
              style={{
                width: "32px",
                height: "32px",
                borderRadius: "8px",
                background: "var(--status-success-bg)",
                color: "var(--status-success)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                flexShrink: 0,
              }}
            >
              <CheckCircleIcon size={18} />
            </div>
            <h3 style={{ fontSize: "0.9375rem", fontWeight: 600, color: "var(--text-primary)", margin: 0 }}>
              Platform Control Plane Initialized
            </h3>
          </div>
          <p className="text-caption" style={{ paddingLeft: "2.75rem", margin: 0 }}>
            All authentication protocols, CSRF protections, and session isolation parameters are operational.
          </p>
        </div>
      </div>

      <style>{`
        .security-cards-grid {
          display: grid;
          grid-template-columns: repeat(4, minmax(0, 1fr));
          gap: 1rem;
          min-width: 0;
        }

        .overview-card {
          background: var(--glass-surface-elevated);
          border: 1px solid var(--border-glass);
          border-radius: 12px;
          padding: 1.25rem;
          box-shadow: var(--shadow-sm);
          min-width: 0;
          display: flex;
          flex-direction: column;
          justifyContent: space-between;
          transition: border-color 0.15s ease, box-shadow 0.15s ease;
        }

        .overview-card:hover {
          border-color: var(--border-strong);
        }

        .status-overview-panel {
          background: var(--glass-surface-elevated);
          border: 1px solid var(--border-glass);
          border-radius: 12px;
          padding: 1.125rem 1.25rem;
          box-shadow: var(--shadow-sm);
          display: flex;
          flex-direction: column;
          gap: 0.35rem;
          min-width: 0;
        }

        @media (max-width: 1180px) {
          .security-cards-grid {
            grid-template-columns: repeat(2, minmax(0, 1fr));
          }
        }
        @media (max-width: 600px) {
          .security-cards-grid {
            grid-template-columns: 1fr;
          }
        }
      `}</style>
    </AppShell>
  );
};
