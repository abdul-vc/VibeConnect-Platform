/**
 * ShowcasePresentPage – Fullscreen presentation mode.
 *
 * - Only published profiles
 * - No owner controls (no publish/unpublish/edit buttons)
 * - Product switcher sidebar
 * - Context preservation from portfolio page
 * - Reliable exit navigation to /showcase
 * - Actionable Live Demo diagnostics without dashboard redirects
 * Route: /showcase/present
 */
import { useEffect, useState, useCallback, useMemo } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { showcaseApi } from "../../api/showcase.ts";
import type { ShowcaseProfile, LaunchabilityContract } from "../../api/types.ts";
import { LoadingSpinner } from "../../components/LoadingSpinner.tsx";
import {
  ChevronLeftIcon,
  ShieldCheckIcon,
  AlertCircleIcon,
  SearchIcon,
  BoxIcon,
  ExternalLinkIcon,
} from "../../components/Icons.tsx";
import { ShowcaseEmbeddedDemo } from "./ShowcaseEmbeddedDemo.tsx";

export function ShowcasePresentPage() {
  const [searchParams] = useSearchParams();
  const [profiles, setProfiles] = useState<readonly ShowcaseProfile[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeIndex, setActiveIndex] = useState(0);
  const [category, setCategory] = useState("");
  const [launchContract, setLaunchContract] = useState<LaunchabilityContract | null>(null);
  const [showDemoModal, setShowDemoModal] = useState(false);
  const [isLaunching, setIsLaunching] = useState(false);
  const [launchError, setLaunchError] = useState<string | null>(null);
  const [demoLaunchUrl, setDemoLaunchUrl] = useState<string | null>(null);

  const targetCode = searchParams.get("product");
  const targetProfileId = searchParams.get("profileId");

  const load = useCallback(async (signal?: AbortSignal) => {
    setLoading(true);
    setError(null);
    try {
      const data = await showcaseApi.getPresentation(
        { category: category || undefined },
        signal
      );
      if (signal?.aborted) return;
      setProfiles(data);
      setError(null);

      // Preserve or resolve selected product context
      if (data.length > 0) {
        let foundIdx = -1;
        if (targetCode) {
          foundIdx = data.findIndex(
            (p) => p.product_code.toLowerCase() === targetCode.toLowerCase()
          );
        }
        if (foundIdx === -1 && targetProfileId) {
          foundIdx = data.findIndex((p) => p.id === targetProfileId);
        }
        if (foundIdx === -1) {
          // Check for LMS by default or first
          const lmsIdx = data.findIndex((p) => p.product_code.toLowerCase() === "lms");
          foundIdx = lmsIdx !== -1 ? lmsIdx : 0;
        }
        setActiveIndex(foundIdx >= 0 ? foundIdx : 0);
      }
    } catch (e: unknown) {
      if (signal?.aborted) return;
      const isCanceled =
        (e as { name?: string })?.name === "CanceledError" ||
        (e as { message?: string })?.message === "canceled" ||
        (e as { code?: string })?.code === "ERR_CANCELED";
      if (!isCanceled) {
        const msg = e instanceof Error ? e.message : "Failed to load presentation.";
        setError(msg || "Failed to load presentation.");
      }
    } finally {
      if (!signal?.aborted) {
        setLoading(false);
      }
    }
  }, [category, targetCode, targetProfileId]);

  useEffect(() => {
    const ctrl = new AbortController();
    load(ctrl.signal);
    return () => ctrl.abort();
  }, [load]);

  const active = profiles[activeIndex] ?? null;

  // Fetch launchability when active product changes
  useEffect(() => {
    if (!active) {
      setLaunchContract(null);
      return;
    }
    let cancelled = false;
    showcaseApi.getLaunchability(active.id).then((c) => {
      if (!cancelled) setLaunchContract(c);
    }).catch(() => {
      if (!cancelled) setLaunchContract({ launchable: false, reason: "CONFIG_UNAVAILABLE" });
    });
    return () => {
      cancelled = true;
    };
  }, [active?.id]);

  const handleStartLiveDemo = async () => {
    if (!active) return;
    setLaunchError(null);
    if (!launchContract?.launchable) {
      setShowDemoModal(true);
      return;
    }

    try {
      setIsLaunching(true);
      const res = await showcaseApi.launchDemo(active.id);
      if (res?.redirect_url) {
        setDemoLaunchUrl(res.redirect_url);
      } else {
        setLaunchError(`Launch failed: No destination URL returned by authorization service. Reference: ${active.id}`);
      }
    } catch (err: unknown) {
      const errMsg = err instanceof Error ? err.message : "Failed to initiate demo SSO launch.";
      setLaunchError(`Launch failed: ${errMsg} (Profile: ${active.product_code})`);
    } finally {
      setIsLaunching(false);
    }
  };

  const backUrl = useMemo(() => {
    if (!active) return "/showcase";
    return `/showcase?product=${encodeURIComponent(active.product_code)}&profileId=${encodeURIComponent(active.id)}`;
  }, [active]);

  return (
    <div
      id="showcase-present-root"
      style={{
        minHeight: "100vh",
        display: "flex",
        flexDirection: "column",
        background: "var(--bg-app, #070b14)",
        color: "var(--text-primary, #f8fafc)",
        fontFamily: "Inter, -apple-system, BlinkMacSystemFont, sans-serif",
      }}
    >
      {/* Top Presentation Bar */}
      <header
        style={{
          height: "56px",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "0 1.5rem",
          background: "var(--glass-surface-elevated, rgba(15, 23, 42, 0.95))",
          borderBottom: "1px solid var(--border-glass, rgba(255, 255, 255, 0.12))",
          zIndex: 10,
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: "0.875rem" }}>
          <span
            style={{
              fontSize: "0.875rem",
              fontWeight: 800,
              letterSpacing: "0.02em",
              color: "var(--text-primary)",
            }}
          >
            Product Showcase
          </span>
          <span
            style={{
              fontSize: "0.6875rem",
              fontWeight: 700,
              padding: "2px 8px",
              borderRadius: "4px",
              background: "var(--brand-primary-light, rgba(99, 102, 241, 0.16))",
              color: "var(--brand-primary, #6366f1)",
              textTransform: "uppercase",
              letterSpacing: "0.05em",
            }}
          >
            Presentation Mode
          </span>
        </div>

        <Link
          to={backUrl}
          id="showcase-present-back-btn"
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: "0.4rem",
            padding: "0.45rem 0.85rem",
            borderRadius: "6px",
            fontSize: "0.8125rem",
            fontWeight: 600,
            color: "var(--brand-primary, #6366f1)",
            background: "var(--glass-surface, rgba(255, 255, 255, 0.05))",
            border: "1px solid var(--border-glass, rgba(255, 255, 255, 0.14))",
            textDecoration: "none",
            transition: "all 0.15s ease",
          }}
        >
          <ChevronLeftIcon size={14} />
          <span>Back to Catalogue</span>
        </Link>
      </header>

      {/* Presentation Body */}
      <div style={{ display: "flex", flex: 1, minHeight: 0 }}>
        {/* Product Switcher Sidebar */}
        <aside
          style={{
            width: "280px",
            flexShrink: 0,
            borderRight: "1px solid var(--border-glass, rgba(255, 255, 255, 0.12))",
            background: "var(--glass-surface, rgba(15, 23, 42, 0.75))",
            display: "flex",
            flexDirection: "column",
            padding: "1rem 0",
          }}
        >
          <div style={{ padding: "0 1rem 0.75rem" }}>
            <div
              style={{
                fontSize: "0.72rem",
                fontWeight: 700,
                letterSpacing: "0.06em",
                textTransform: "uppercase",
                color: "var(--text-muted, #64748b)",
                marginBottom: 8,
              }}
            >
              Portfolio Products
            </div>
            <div style={{ position: "relative" }}>
              <input
                id="showcase-present-category-filter"
                value={category}
                onChange={(e) => setCategory(e.target.value)}
                placeholder="Filter products…"
                style={{
                  width: "100%",
                  padding: "0.45rem 0.65rem 0.45rem 2rem",
                  borderRadius: "6px",
                  border: "1px solid var(--border-glass, rgba(255, 255, 255, 0.12))",
                  background: "var(--glass-surface-sunken, rgba(4, 8, 18, 0.6))",
                  color: "var(--text-primary)",
                  fontSize: "0.8125rem",
                  boxSizing: "border-box",
                  outline: "none",
                }}
              />
              <div
                style={{
                  position: "absolute",
                  left: "0.6rem",
                  top: "50%",
                  transform: "translateY(-50%)",
                  color: "var(--text-muted)",
                  display: "flex",
                  alignItems: "center",
                }}
              >
                <SearchIcon size={13} />
              </div>
            </div>
          </div>

          <div style={{ flex: 1, overflowY: "auto", padding: "0.5rem 0.5rem" }}>
            {loading && (
              <div style={{ padding: "1.5rem 1rem", textAlign: "center" }}>
                <LoadingSpinner label="Loading presentation…" />
              </div>
            )}

            {!loading && profiles.length === 0 && (
              <div
                style={{
                  padding: "2rem 1rem",
                  textAlign: "center",
                  color: "var(--text-muted)",
                  fontSize: "0.8125rem",
                }}
              >
                No published products found.
              </div>
            )}

            {profiles.map((p, idx) => {
              const isSelected = idx === activeIndex;
              return (
                <button
                  key={p.id}
                  type="button"
                  id={`present-switcher-${p.product_code}`}
                  data-profile-id={p.id}
                  data-product-code={p.product_code}
                  onClick={() => {
                    setActiveIndex(idx);
                    setShowDemoModal(false);
                    setDemoLaunchUrl(null);
                  }}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    width: "100%",
                    textAlign: "left",
                    padding: "0.65rem 0.85rem",
                    borderRadius: "8px",
                    background: isSelected
                      ? "var(--brand-primary-light, rgba(99, 102, 241, 0.18))"
                      : "transparent",
                    border: isSelected
                      ? "1px solid var(--brand-primary, #6366f1)"
                      : "1px solid transparent",
                    cursor: "pointer",
                    marginBottom: 4,
                    transition: "all 0.15s ease",
                    boxSizing: "border-box",
                  }}
                >
                  <div style={{ minWidth: 0, flex: 1 }}>
                    <div
                      style={{
                        fontSize: "0.85rem",
                        fontWeight: isSelected ? 700 : 500,
                        color: isSelected ? "var(--text-primary)" : "var(--text-secondary)",
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                        whiteSpace: "nowrap",
                      }}
                    >
                      {p.product_name}
                    </div>
                  </div>
                  <span
                    style={{
                      fontSize: "0.68rem",
                      fontWeight: 700,
                      padding: "1px 5px",
                      borderRadius: "4px",
                      background: isSelected
                        ? "rgba(99, 102, 241, 0.25)"
                        : "var(--glass-surface-sunken, rgba(4, 8, 18, 0.4))",
                      color: isSelected ? "var(--brand-primary, #6366f1)" : "var(--text-muted)",
                      textTransform: "uppercase",
                      marginLeft: 6,
                    }}
                  >
                    {p.product_code}
                  </span>
                </button>
              );
            })}
          </div>
        </aside>

        {/* Main Presentation Canvas */}
        <main
          style={{
            flex: 1,
            padding: demoLaunchUrl ? "1.25rem 1.75rem" : "2.5rem 3.5rem",
            overflowY: "auto",
            display: "flex",
            flexDirection: "column",
            gap: demoLaunchUrl ? "1rem" : "2rem",
          }}
        >
          {demoLaunchUrl && active && (
            <ShowcaseEmbeddedDemo
              productName={active.product_name}
              productCode={active.product_code}
              launchUrl={demoLaunchUrl}
              onBack={() => setDemoLaunchUrl(null)}
              onReload={async () => {
                const res = await showcaseApi.launchDemo(active.id);
                if (res?.redirect_url) {
                  setDemoLaunchUrl(res.redirect_url);
                  return res.redirect_url;
                }
                return null;
              }}
              backLabel="Back to Presentation"
            />
          )}

          {!demoLaunchUrl && error && (
            <div
              style={{
                color: "var(--status-danger)",
                background: "var(--status-danger-bg)",
                border: "1px solid var(--status-danger-border)",
                padding: "1rem",
                borderRadius: "8px",
                fontSize: "0.875rem",
              }}
            >
              {error}
            </div>
          )}

          {!demoLaunchUrl && !loading && !error && !active && (
            <div
              style={{
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                justifyContent: "center",
                height: "50vh",
                color: "var(--text-muted)",
                gap: "1rem",
              }}
            >
              <BoxIcon size={40} />
              <div style={{ fontSize: "1.1rem", fontWeight: 600 }}>No published showcase profile selected</div>
              <Link
                to="/showcase"
                style={{
                  fontSize: "0.875rem",
                  color: "var(--brand-primary)",
                  textDecoration: "underline",
                }}
              >
                Return to Product Showcase
              </Link>
            </div>
          )}

          {!demoLaunchUrl && active && (
            <div style={{ display: "flex", flexDirection: "column", gap: "1.75rem", maxWidth: "1000px" }}>
              {/* Product Hero */}
              <div>
                <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", marginBottom: "0.75rem" }}>
                  <span
                    style={{
                      fontSize: "0.75rem",
                      fontWeight: 700,
                      padding: "3px 8px",
                      borderRadius: "4px",
                      background: "var(--brand-primary-light, rgba(99, 102, 241, 0.16))",
                      color: "var(--brand-primary, #6366f1)",
                      border: "1px solid var(--brand-primary-light)",
                      textTransform: "uppercase",
                      letterSpacing: "0.04em",
                    }}
                  >
                    {active.product_code}
                  </span>
                  <span
                    style={{
                      fontSize: "0.72rem",
                      fontWeight: 600,
                      color: "var(--status-success, #10b981)",
                      background: "var(--status-success-bg, rgba(16, 185, 129, 0.12))",
                      border: "1px solid var(--status-success-border)",
                      padding: "2px 8px",
                      borderRadius: "999px",
                    }}
                  >
                    Published
                  </span>
                </div>

                <h1
                  style={{
                    fontSize: "2.5rem",
                    fontWeight: 800,
                    color: "var(--text-primary)",
                    margin: 0,
                    letterSpacing: "-0.02em",
                    lineHeight: 1.2,
                  }}
                >
                  {active.product_name}
                </h1>

                {active.tagline ? (
                  <p
                    style={{
                      fontSize: "1.2rem",
                      color: "var(--text-secondary)",
                      marginTop: "0.75rem",
                      marginBottom: 0,
                      fontWeight: 400,
                      lineHeight: 1.5,
                    }}
                  >
                    {active.tagline}
                  </p>
                ) : null}
              </div>

              {/* Overview Section */}
              {active.overview ? (
                <div
                  style={{
                    background: "var(--glass-surface-elevated, rgba(24, 34, 56, 0.88))",
                    border: "1px solid var(--border-glass, rgba(255, 255, 255, 0.14))",
                    borderRadius: "14px",
                    padding: "1.75rem",
                    fontSize: "0.95rem",
                    lineHeight: 1.75,
                    color: "var(--text-primary)",
                    whiteSpace: "pre-line",
                    boxShadow: "var(--shadow-sm)",
                  }}
                >
                  {active.overview}
                </div>
              ) : null}

              {/* Media Showcase */}
              {active.media.length > 0 && (
                <div>
                  <div
                    style={{
                      fontSize: "0.75rem",
                      fontWeight: 700,
                      color: "var(--text-muted)",
                      textTransform: "uppercase",
                      letterSpacing: "0.06em",
                      marginBottom: "0.75rem",
                    }}
                  >
                    Product Media & Artifacts
                  </div>
                  <div
                    style={{
                      display: "grid",
                      gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))",
                      gap: "1rem",
                    }}
                  >
                    {active.media.map((m) => (
                      <div
                        key={m.id}
                        style={{
                          background: "var(--glass-surface-elevated, rgba(24, 34, 56, 0.8))",
                          border: "1px solid var(--border-glass, rgba(255, 255, 255, 0.12))",
                          borderRadius: "10px",
                          padding: "1rem",
                          display: "flex",
                          flexDirection: "column",
                          gap: "0.5rem",
                        }}
                      >
                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                          <span
                            style={{
                              fontSize: "0.68rem",
                              padding: "2px 6px",
                              borderRadius: "4px",
                              background: "var(--brand-primary-light, rgba(99, 102, 241, 0.12))",
                              color: "var(--brand-primary, #6366f1)",
                              textTransform: "uppercase",
                              fontWeight: 700,
                            }}
                          >
                            {m.media_type}
                          </span>
                        </div>
                        <div
                          style={{
                            fontSize: "0.875rem",
                            fontWeight: 600,
                            color: "var(--text-primary)",
                          }}
                        >
                          {m.title}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Launch Demo Bar */}
              <div
                style={{
                  marginTop: "0.5rem",
                  paddingTop: "1.5rem",
                  borderTop: "1px solid var(--border-subtle, rgba(255, 255, 255, 0.08))",
                  display: "flex",
                  flexDirection: "column",
                  gap: "1rem",
                }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: "1rem", flexWrap: "wrap" }}>
                  <button
                    type="button"
                    id="showcase-present-launch-btn"
                    onClick={handleStartLiveDemo}
                    disabled={isLaunching}
                    style={{
                      padding: "0.75rem 1.75rem",
                      borderRadius: "10px",
                      border: launchContract?.launchable
                        ? "none"
                        : "1px solid var(--border-glass, rgba(255, 255, 255, 0.15))",
                      background: launchContract?.launchable
                        ? "var(--brand-primary, #6366f1)"
                        : "var(--glass-surface-elevated, rgba(24, 34, 56, 0.8))",
                      color: launchContract?.launchable ? "#ffffff" : "var(--text-secondary, #94a3b8)",
                      cursor: isLaunching ? "not-allowed" : "pointer",
                      opacity: isLaunching ? 0.7 : 1,
                      fontSize: "0.9rem",
                      fontWeight: 700,
                      display: "inline-flex",
                      alignItems: "center",
                      gap: "0.5rem",
                      boxShadow: "var(--shadow-sm)",
                    }}
                  >
                    <ShieldCheckIcon size={16} />
                    <span>{isLaunching ? "Launching Demo…" : "Start Live Demo"}</span>
                  </button>

                  <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                    <div style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>
                      {launchContract?.launchable
                        ? "Ready for authorized demonstration."
                        : "Target environment readiness: " + (launchContract?.reason || "SSO_NOT_CONFIGURED")}
                    </div>
                    {launchContract?.launchable && launchContract.demo_user && (
                      <div style={{ fontSize: "0.72rem", color: "var(--brand-primary, #818cf8)" }}>
                        Actor: Platform Owner · Identity: {launchContract.demo_user} ({launchContract.demo_organization})
                      </div>
                    )}
                  </div>
                </div>

                {launchError && (
                  <div
                    style={{
                      background: "var(--status-danger-bg, rgba(239, 68, 68, 0.12))",
                      border: "1px solid var(--status-danger-border, rgba(239, 68, 68, 0.3))",
                      borderRadius: "8px",
                      padding: "0.875rem 1rem",
                      color: "var(--status-danger, #ef4444)",
                      fontSize: "0.85rem",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "space-between",
                      gap: "0.75rem",
                      maxWidth: "700px",
                    }}
                  >
                    <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                      <AlertCircleIcon size={16} />
                      <span>{launchError}</span>
                    </div>
                    <button
                      type="button"
                      onClick={() => setLaunchError(null)}
                      style={{
                        background: "transparent",
                        border: "none",
                        color: "var(--status-danger)",
                        cursor: "pointer",
                        fontWeight: 600,
                        fontSize: "0.75rem",
                      }}
                    >
                      Dismiss
                    </button>
                  </div>
                )}

                {/* Clear Actionable Diagnostic Notification */}
                {showDemoModal && (
                  <div
                    style={{
                      background: "var(--glass-surface-sunken, rgba(4, 8, 18, 0.85))",
                      border: "1px solid var(--border-glass, rgba(255, 255, 255, 0.16))",
                      borderRadius: "10px",
                      padding: "1.25rem",
                      display: "flex",
                      flexDirection: "column",
                      gap: "0.75rem",
                      maxWidth: "700px",
                    }}
                  >
                    <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                      <AlertCircleIcon size={18} color="var(--status-warning, #f59e0b)" />
                      <span style={{ fontSize: "0.95rem", fontWeight: 700, color: "var(--text-primary)" }}>
                        Demo Target Environment Unavailable
                      </span>
                    </div>

                    <p
                      style={{
                        fontSize: "0.85rem",
                        color: "var(--text-secondary)",
                        margin: 0,
                        lineHeight: 1.6,
                      }}
                    >
                      A live interactive demonstration for <strong>{active.product_name} ({active.product_code})</strong> cannot be launched at this time.
                      <br />
                      <strong>Diagnosis:</strong> <code>{launchContract?.reason || "SSO_NOT_CONFIGURED"}</code>.
                      <br />
                      The Platform Owner context does not hold an active tenant-user session. To launch live interactive previews, an allowlisted target demo environment or standalone showcase sandbox must be configured in Product Showcase settings.
                    </p>

                    <div style={{ display: "flex", gap: "0.75rem", marginTop: 4 }}>
                      <button
                        type="button"
                        onClick={() => setShowDemoModal(false)}
                        style={{
                          padding: "5px 14px",
                          borderRadius: "6px",
                          fontSize: "0.8125rem",
                          fontWeight: 600,
                          background: "var(--glass-surface)",
                          border: "1px solid var(--border-subtle)",
                          color: "var(--text-primary)",
                          cursor: "pointer",
                        }}
                      >
                        Acknowledge
                      </button>
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}
        </main>
      </div>
    </div>
  );
}
