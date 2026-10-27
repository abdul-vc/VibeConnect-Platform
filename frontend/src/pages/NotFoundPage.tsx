import type { FC } from "react";
import { Link } from "react-router-dom";
import { GlassPanel } from "../components/GlassPanel.tsx";
import { ThemeToggle } from "../components/ThemeToggle.tsx";
import { BrandMark } from "../components/BrandMark.tsx";

export const NotFoundPage: FC = () => {
  return (
    <div
      style={{
        minHeight: "100vh",
        display: "flex",
        flexDirection: "column",
        background: "var(--bg-app)",
        position: "relative",
      }}
    >
      <div className="ambient-bg" />

      <header
        style={{
          position: "relative",
          zIndex: 10,
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "1.25rem 2rem",
          maxWidth: "1320px",
          width: "100%",
          margin: "0 auto",
        }}
      >
        <BrandMark size="sm" showLabel={true} />
        <ThemeToggle />
      </header>

      <main
        style={{
          flex: 1,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          padding: "1.5rem",
          position: "relative",
          zIndex: 1,
        }}
      >
        <GlassPanel
          elevation="elevated"
          padding="xl"
          style={{ maxWidth: "440px", width: "100%", textAlign: "center" }}
        >
          <div
            style={{
              fontSize: "3.5rem",
              fontWeight: 800,
              background: "var(--brand-gradient)",
              WebkitBackgroundClip: "text",
              WebkitTextFillColor: "transparent",
              letterSpacing: "-0.04em",
              lineHeight: 1,
              marginBottom: "0.75rem",
            }}
          >
            404
          </div>
          <h1 style={{ fontSize: "1.375rem", fontWeight: 700, marginBottom: "0.5rem" }}>
            Route Not Found
          </h1>
          <p style={{ color: "var(--text-secondary)", fontSize: "0.875rem", lineHeight: 1.5, marginBottom: "1.75rem" }}>
            The requested control plane route does not exist or has been relocated.
          </p>
          <Link
            to="/"
            className="btn-primary"
            style={{ textDecoration: "none", width: "100%" }}
          >
            Return to Overview
          </Link>
        </GlassPanel>
      </main>
    </div>
  );
};
