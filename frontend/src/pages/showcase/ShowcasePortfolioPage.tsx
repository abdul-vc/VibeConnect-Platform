/**
 * ShowcasePortfolioPage – Executive Product Showcase & Interactive Sandbox Platform.
 * Routes: /showcase
 */
import { useEffect, useState, useCallback, useId, useMemo, useRef } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { AppShell } from "../../components/AppShell.tsx";
import { showcaseApi } from "../../api/showcase.ts";
import type { ShowcaseProfile, ShowcaseVisibility, LaunchabilityContract, ShowcaseLaunchConfig } from "../../api/types.ts";
import { LoadingSpinner } from "../../components/LoadingSpinner.tsx";
import {
  SearchIcon,
  ShieldCheckIcon,
  AlertCircleIcon,
  CheckCircleIcon,
  BoxIcon,
  LayersIcon,
  SlidersIcon,
  GlobeIcon,
  ArrowRightIcon,
  GridIcon,
} from "../../components/Icons.tsx";
import { ShowcaseEmbeddedDemo } from "./ShowcaseEmbeddedDemo.tsx";
import { ProductIcon } from "../../components/ProductIcons.tsx";

const VISIBILITY_OPTIONS: Array<{ value: ShowcaseVisibility | ""; label: string }> = [
  { value: "", label: "All Products" },
  { value: "published", label: "Published" },
  { value: "draft", label: "Draft" },
  { value: "hidden", label: "Hidden" },
];

function VisibilityBadge({ v }: { v: ShowcaseVisibility }) {
  const isPublished = v === "published";
  const isDraft = v === "draft";
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: "4px",
        padding: "3px 10px",
        borderRadius: "999px",
        fontSize: "0.72rem",
        fontWeight: 600,
        letterSpacing: "0.02em",
        background: isPublished
          ? "var(--status-success-bg, rgba(16, 185, 129, 0.12))"
          : isDraft
          ? "var(--status-neutral-bg, rgba(148, 163, 184, 0.1))"
          : "var(--status-warning-bg, rgba(245, 158, 11, 0.12))",
        color: isPublished
          ? "var(--status-success, #10b981)"
          : isDraft
          ? "var(--text-secondary, #94a3b8)"
          : "var(--status-warning, #f59e0b)",
        border: `1px solid ${
          isPublished
            ? "var(--status-success-border, rgba(16, 185, 129, 0.28))"
            : isDraft
            ? "var(--border-subtle, rgba(255, 255, 255, 0.1))"
            : "var(--status-warning-border, rgba(245, 158, 11, 0.28))"
        }`,
        textTransform: "capitalize",
      }}
    >
      <span
        style={{
          width: "6px",
          height: "6px",
          borderRadius: "50%",
          background: isPublished
            ? "var(--status-success, #10b981)"
            : isDraft
            ? "var(--text-muted, #94a3b8)"
            : "var(--status-warning, #f59e0b)",
        }}
      />
      {v}
    </span>
  );
}

function ShowcaseCard({
  profile,
  selected,
  onClick,
}: {
  profile: ShowcaseProfile;
  selected: boolean;
  onClick: () => void;
}) {
  const cardRef = useRef<HTMLButtonElement | null>(null);

  useEffect(() => {
    if (selected && cardRef.current) {
      cardRef.current.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
  }, [selected]);

  return (
    <button
      ref={cardRef}
      type="button"
      id={`showcase-card-${profile.product_code}`}
      data-testid={`showcase-card-${profile.product_code}`}
      data-profile-id={profile.id}
      data-product-code={profile.product_code}
      onClick={onClick}
      className={`showcase-card ${selected ? "selected" : ""}`}
      style={{
        display: "block",
        width: "100%",
        textAlign: "left",
        background: selected ? "var(--glass-surface-hover)" : "var(--glass-surface-elevated)",
        border: selected
          ? "1.5px solid var(--brand-primary)"
          : "1px solid var(--border-subtle)",
        borderRadius: "12px",
        padding: "0.875rem 1rem",
        cursor: "pointer",
        transition: "all 0.16s ease",
        boxShadow: selected
          ? "0 4px 18px rgba(99, 102, 241, 0.18), var(--shadow-sm)"
          : "var(--shadow-sm)",
        boxSizing: "border-box",
        position: "relative",
        flexShrink: 0,
        minHeight: "fit-content",
        overflow: "hidden",
      }}
    >
      {selected && (
        <div
          style={{
            position: "absolute",
            left: 0,
            top: 0,
            bottom: 0,
            width: "4px",
            background: "var(--brand-primary)",
            borderRadius: "0 2px 2px 0",
          }}
        />
      )}

      <div style={{ display: "flex", alignItems: "center", gap: "0.85rem" }}>
        {/* Professional Vector Product Icon */}
        <ProductIcon code={profile.product_code} size={38} />

        <div style={{ minWidth: 0, flex: 1 }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8 }}>
            <span
              style={{
                fontWeight: 700,
                fontSize: "0.95rem",
                color: "var(--text-primary)",
                overflow: "hidden",
                textOverflow: "ellipsis",
                whiteSpace: "nowrap",
                lineHeight: 1.35,
              }}
            >
              {profile.product_name}
            </span>
            <VisibilityBadge v={profile.visibility} />
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: "6px", marginTop: "3px" }}>
            <span
              style={{
                display: "inline-block",
                fontFamily: "var(--font-code, monospace)",
                fontSize: "0.68rem",
                fontWeight: 700,
                color: "var(--brand-primary)",
                background: "var(--brand-primary-light)",
                padding: "1px 6px",
                borderRadius: "4px",
                textTransform: "uppercase",
                letterSpacing: "0.04em",
              }}
            >
              {profile.product_code}
            </span>
            <span style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>
              Order #{profile.display_order}
            </span>
          </div>
        </div>
      </div>

      {profile.tagline ? (
        <div
          style={{
            marginTop: "0.6rem",
            fontSize: "0.8rem",
            color: "var(--text-secondary)",
            lineHeight: 1.45,
            display: "-webkit-box",
            WebkitLineClamp: 2,
            WebkitBoxOrient: "vertical",
            overflow: "hidden",
          }}
        >
          {profile.tagline}
        </div>
      ) : null}

      <div
        style={{
          marginTop: "0.65rem",
          paddingTop: "0.55rem",
          borderTop: "1px solid var(--border-subtle)",
          fontSize: "0.72rem",
          color: "var(--text-muted)",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
        }}
      >
        <span style={{ display: "inline-flex", alignItems: "center", gap: "4px" }}>
          <ShieldCheckIcon size={13} color="var(--status-success)" />
          <span style={{ color: "var(--status-success)", fontWeight: 600 }}>Demo Enabled</span>
        </span>
        <span>{profile.media.length} asset{profile.media.length === 1 ? "" : "s"}</span>
      </div>
    </button>
  );
}

export function ShowcasePortfolioPage() {
  const searchId = useId();
  const [searchParams, setSearchParams] = useSearchParams();
  const [profiles, setProfiles] = useState<readonly ShowcaseProfile[]>([]);
  const [count, setCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [visibility, setVisibility] = useState<ShowcaseVisibility | "">("");
  const [selected, setSelected] = useState<ShowcaseProfile | null>(null);
  const [actionPending, setActionPending] = useState(false);
  const [actionMsg, setActionMsg] = useState<string | null>(null);
  const [launchContract, setLaunchContract] = useState<LaunchabilityContract | null>(null);
  const [showDemoDialog, setShowDemoDialog] = useState(false);
  const [demoLaunchUrl, setDemoLaunchUrl] = useState<string | null>(null);
  const [showConfigModal, setShowConfigModal] = useState(false);
  const [launchConfig, setLaunchConfig] = useState<ShowcaseLaunchConfig | null>(null);
  const [configLoading, setConfigLoading] = useState(false);
  const [configSaving, setConfigSaving] = useState(false);
  const [configError, setConfigError] = useState<string | null>(null);
  const [cfgLaunchMode, setCfgLaunchMode] = useState("demo_only");
  const [cfgEnvId, setCfgEnvId] = useState("");
  const [cfgOrgCode, setCfgOrgCode] = useState("");
  const [cfgUserEmail, setCfgUserEmail] = useState("");
  const [cfgNotes, setCfgNotes] = useState("");

  const selectedParamCode = searchParams.get("product");
  const selectedParamId = searchParams.get("profileId");

  const load = useCallback(
    async (signal?: AbortSignal) => {
      setLoading(true);
      setError(null);
      try {
        const result = await showcaseApi.listProfiles(
          { search: search || undefined, visibility: visibility || undefined },
          signal
        );
        if (signal?.aborted) return;
        setProfiles(result.results);
        setCount(result.count);
        setError(null);

        // Auto-select resolution
        if (result.results.length > 0) {
          let target = result.results.find(
            (p) =>
              (selectedParamCode && p.product_code.toLowerCase() === selectedParamCode.toLowerCase()) ||
              (selectedParamId && p.id === selectedParamId)
          );
          if (!target && selected) {
            target = result.results.find((p) => p.id === selected.id);
          }
          if (!target) {
            target = result.results.find((p) => p.product_code.toLowerCase() === "lms") || result.results[0];
          }
          if (target) {
            setSelected(target);
          }
        }
      } catch (e: unknown) {
        if (signal?.aborted) return;
        const isCanceled =
          (e as { name?: string })?.name === "CanceledError" ||
          (e as { message?: string })?.message === "canceled" ||
          (e as { code?: string })?.code === "ERR_CANCELED";
        if (!isCanceled) {
          const msg = e instanceof Error ? e.message : "Failed to load showcase profiles.";
          setError(msg || "Failed to load showcase profiles.");
        }
      } finally {
        if (!signal?.aborted) {
          setLoading(false);
        }
      }
    },
    [search, visibility, selectedParamCode, selectedParamId, selected]
  );

  useEffect(() => {
    const ctrl = new AbortController();
    load(ctrl.signal);
    return () => ctrl.abort();
  }, [search, visibility]);

  // Load launchability whenever selected profile changes
  useEffect(() => {
    if (!selected) {
      setLaunchContract(null);
      return;
    }
    let cancelled = false;
    showcaseApi
      .getLaunchability(selected.id)
      .then((c) => {
        if (!cancelled) setLaunchContract(c);
      })
      .catch(() => {
        if (!cancelled) setLaunchContract({ launchable: false, reason: "CHECK_FAILED" });
      });
    return () => {
      cancelled = true;
    };
  }, [selected?.id]);

  const isDemoParam = searchParams.get("demo") === "true";
  const lastLaunchedIdRef = useRef<string | null>(null);

  // Sync selected with query param when user navigates or switches
  useEffect(() => {
    if (selectedParamCode && profiles.length > 0) {
      const match = profiles.find(
        (p) => p.product_code.toLowerCase() === selectedParamCode.toLowerCase()
      );
      if (match && match.id !== selected?.id) {
        setSelected(match);
      }
    }
  }, [selectedParamCode, profiles, selected?.id]);

  // When demo mode is active, automatically obtain a fresh launch grant for the selected product
  useEffect(() => {
    if (isDemoParam && selected && lastLaunchedIdRef.current !== selected.id) {
      lastLaunchedIdRef.current = selected.id;
      showcaseApi
        .launchDemo(selected.id)
        .then((res) => {
          if (res?.redirect_url) {
            setDemoLaunchUrl(res.redirect_url);
          }
        })
        .catch((err) => {
          const msg = err instanceof Error ? err.message : "Failed to launch demo.";
          setActionMsg(`Demo launch failed: ${msg}`);
        });
    }
  }, [isDemoParam, selected?.id]);

  const handleSelect = (profile: ShowcaseProfile) => {
    setSelected(profile);
    setActionMsg(null);
    setDemoLaunchUrl(null);
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev);
      next.set("product", profile.product_code);
      next.set("profileId", profile.id);
      return next;
    });
  };

  const handlePublish = async () => {
    if (!selected) return;
    setActionPending(true);
    setActionMsg(null);
    try {
      const updated = await showcaseApi.publishProfile(selected.id);
      setSelected(updated);
      setProfiles((prev) => prev.map((p) => (p.id === updated.id ? updated : p)));
      setActionMsg("Profile published successfully.");
    } catch {
      setActionMsg("Failed to publish profile.");
    } finally {
      setActionPending(false);
    }
  };

  const handleUnpublish = async () => {
    if (!selected) return;
    setActionPending(true);
    setActionMsg(null);
    try {
      const updated = await showcaseApi.unpublishProfile(selected.id);
      setSelected(updated);
      setProfiles((prev) => prev.map((p) => (p.id === updated.id ? updated : p)));
      setActionMsg("Profile unpublished successfully.");
    } catch {
      setActionMsg("Failed to unpublish profile.");
    } finally {
      setActionPending(false);
    }
  };

  const handleLiveDemoClick = async () => {
    if (!selected) return;
    if (!launchContract?.launchable) {
      setShowDemoDialog(true);
      return;
    }
    setActionPending(true);
    setActionMsg(null);
    try {
      const res = await showcaseApi.launchDemo(selected.id);
      if (res?.redirect_url) {
        setDemoLaunchUrl(res.redirect_url);
      } else {
        setActionMsg(`Demo launch failed: no redirect URL returned (Profile: ${selected.id}).`);
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to launch demo.";
      setActionMsg(`Demo launch failed: ${msg} (Profile: ${selected.product_code})`);
    } finally {
      setActionPending(false);
    }
  };

  const handleOpenConfig = async () => {
    if (!selected) return;
    setShowConfigModal(true);
    setConfigLoading(true);
    setConfigError(null);
    try {
      const cfg = await showcaseApi.getLaunchConfig(selected.id);
      setLaunchConfig(cfg);
      setCfgLaunchMode(cfg.launch_mode || "demo_only");
      setCfgEnvId(cfg.target_environment || "");
      const policy = (cfg.policy || {}) as Record<string, string>;
      setCfgOrgCode(policy.demo_organization_code || "");
      setCfgUserEmail(policy.demo_user_email || "");
      setCfgNotes(cfg.notes || "");
    } catch (err: unknown) {
      setConfigError(err instanceof Error ? err.message : "Failed to load launch configuration.");
    } finally {
      setConfigLoading(false);
    }
  };

  const handleSaveConfig = async () => {
    if (!selected) return;
    setConfigSaving(true);
    setConfigError(null);
    try {
      await showcaseApi.updateLaunchConfig(selected.id, {
        launch_mode: cfgLaunchMode,
        target_environment: cfgEnvId || null,
        policy: {
          demo_organization_code: cfgOrgCode.trim(),
          demo_user_email: cfgUserEmail.trim(),
        },
        notes: cfgNotes,
      });
      setShowConfigModal(false);
      setActionMsg("Demo configuration updated successfully.");
      const updatedContract = await showcaseApi.getLaunchability(selected.id);
      setLaunchContract(updatedContract);
    } catch (err: unknown) {
      setConfigError(err instanceof Error ? err.message : "Failed to save launch configuration.");
    } finally {
      setConfigSaving(false);
    }
  };

  const presentUrl = useMemo(() => {
    if (!selected) return "/showcase/present";
    return `/showcase/present?product=${encodeURIComponent(selected.product_code)}&profileId=${encodeURIComponent(selected.id)}`;
  }, [selected]);

  const publishedCount = useMemo(() => {
    return profiles.filter((p) => p.visibility === "published").length;
  }, [profiles]);

  return (
    <AppShell fullWidth={Boolean(demoLaunchUrl && selected)}>
      {demoLaunchUrl && selected ? (
        <ShowcaseEmbeddedDemo
          productName={selected.product_name}
          productCode={selected.product_code}
          launchUrl={demoLaunchUrl}
          onBack={() => {
            setDemoLaunchUrl(null);
            lastLaunchedIdRef.current = null;
            setSearchParams((prev) => {
              const next = new URLSearchParams(prev);
              next.delete("demo");
              return next;
            });
          }}
          onReload={async () => {
            const res = await showcaseApi.launchDemo(selected.id);
            if (res?.redirect_url) {
              setDemoLaunchUrl(res.redirect_url);
              return res.redirect_url;
            }
            return null;
          }}
          backLabel="Back to Product Showcase"
        />
      ) : (
        <div className="showcase-layout-container">
          {/* Executive Page Header */}
          {/* Breadcrumb Navigation */}
          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", fontSize: "0.8125rem", color: "var(--text-muted)", marginBottom: "1.25rem", fontWeight: 500 }}>
            <Link to="/" style={{ color: "var(--text-muted)", textDecoration: "none", transition: "color 0.15s" }}>Platform Owner</Link>
            <span>/</span>
            <span>Platform</span>
            <span>/</span>
            <span style={{ color: "var(--brand-primary)", fontWeight: 600 }}>Enterprise Product Showcase</span>
          </div>

          <div className="showcase-page-header" style={{ marginBottom: "2rem" }}>
            <div style={{ display: "flex", alignItems: "center", gap: "1rem" }}>
              <div
                style={{
                  width: 48,
                  height: 48,
                  borderRadius: 14,
                  background: "linear-gradient(135deg, rgba(56, 103, 245, 0.15) 0%, rgba(139, 92, 246, 0.15) 100%)",
                  border: "1px solid rgba(56, 103, 245, 0.25)",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  color: "var(--brand-primary)",
                  boxShadow: "0 4px 12px rgba(56, 103, 245, 0.1)",
                  flexShrink: 0,
                }}
              >
                <BoxIcon size={24} />
              </div>

              <div>
                <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
                  <h1 className="heading-hero" style={{ fontSize: "1.75rem", margin: 0, fontWeight: 800, letterSpacing: "-0.02em", color: "var(--text-primary)" }}>
                    Platform Product Portfolio
                  </h1>
                  <span
                    style={{
                      background: "rgba(56, 103, 245, 0.1)",
                      color: "var(--brand-primary)",
                      padding: "0.2rem 0.65rem",
                      borderRadius: 999,
                      fontSize: "0.75rem",
                      fontWeight: 700,
                      border: "1px solid rgba(56, 103, 245, 0.2)",
                    }}
                  >
                    {publishedCount} Active Profiles
                  </span>
                </div>
                <p className="showcase-header-subtitle" style={{ margin: "0.25rem 0 0 0", color: "var(--text-secondary)", fontSize: "0.9375rem" }}>
                  Interactive live demos, enterprise product profiles, and presentation mode.
                </p>
              </div>
            </div>

            <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
              <Link
                to={presentUrl}
                id="showcase-present-mode-link"
                className="btn btn-gradient"
                style={{
                  textDecoration: "none",
                  display: "inline-flex",
                  alignItems: "center",
                  gap: "0.5rem",
                }}
              >
                <LayersIcon size={16} />
                <span>Present Mode</span>
                <ArrowRightIcon size={14} />
              </Link>
            </div>
          </div>

          {/* Quick Metrics Bar */}
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(210px, 1fr))",
              gap: "1rem",
            }}
          >
            <div
              style={{
                background: "var(--glass-surface-elevated)",
                border: "1px solid var(--border-subtle)",
                borderRadius: "10px",
                padding: "0.85rem 1.15rem",
                display: "flex",
                alignItems: "center",
                gap: "0.85rem",
                boxShadow: "var(--shadow-sm)",
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
                }}
              >
                <GridIcon size={18} />
              </div>
              <div>
                <div style={{ fontSize: "0.72rem", color: "var(--text-muted)", textTransform: "uppercase", fontWeight: 700, letterSpacing: "0.04em" }}>
                  Total Catalog
                </div>
                <div style={{ fontSize: "1.2rem", fontWeight: 800, color: "var(--text-primary)" }}>
                  {profiles.length} Products
                </div>
              </div>
            </div>

            <div
              style={{
                background: "var(--glass-surface-elevated)",
                border: "1px solid var(--border-subtle)",
                borderRadius: "10px",
                padding: "0.85rem 1.15rem",
                display: "flex",
                alignItems: "center",
                gap: "0.85rem",
                boxShadow: "var(--shadow-sm)",
              }}
            >
              <div
                style={{
                  width: "36px",
                  height: "36px",
                  borderRadius: "8px",
                  background: "var(--status-success-bg)",
                  color: "var(--status-success)",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                }}
              >
                <ShieldCheckIcon size={18} />
              </div>
              <div>
                <div style={{ fontSize: "0.72rem", color: "var(--text-muted)", textTransform: "uppercase", fontWeight: 700, letterSpacing: "0.04em" }}>
                  Live Demo Status
                </div>
                <div style={{ fontSize: "1.2rem", fontWeight: 800, color: "var(--status-success)" }}>
                  All Ready Online
                </div>
              </div>
            </div>

            <div
              style={{
                background: "var(--glass-surface-elevated)",
                border: "1px solid var(--border-subtle)",
                borderRadius: "10px",
                padding: "0.85rem 1.15rem",
                display: "flex",
                alignItems: "center",
                gap: "0.85rem",
                boxShadow: "var(--shadow-sm)",
              }}
            >
              <div
                style={{
                  width: "36px",
                  height: "36px",
                  borderRadius: "8px",
                  background: "var(--status-neutral-bg)",
                  color: "var(--text-secondary)",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                }}
              >
                <CheckCircleIcon size={18} />
              </div>
              <div>
                <div style={{ fontSize: "0.72rem", color: "var(--text-muted)", textTransform: "uppercase", fontWeight: 700, letterSpacing: "0.04em" }}>
                  Published Status
                </div>
                <div style={{ fontSize: "1.2rem", fontWeight: 800, color: "var(--text-primary)" }}>
                  {publishedCount} Published
                </div>
              </div>
            </div>

            <div
              style={{
                background: "var(--glass-surface-elevated)",
                border: "1px solid var(--border-subtle)",
                borderRadius: "10px",
                padding: "0.85rem 1.15rem",
                display: "flex",
                alignItems: "center",
                gap: "0.85rem",
                boxShadow: "var(--shadow-sm)",
              }}
            >
              <div
                style={{
                  width: "36px",
                  height: "36px",
                  borderRadius: "8px",
                  background: "rgba(168, 85, 247, 0.12)",
                  color: "#a855f7",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                }}
              >
                <GlobeIcon size={18} />
              </div>
              <div>
                <div style={{ fontSize: "0.72rem", color: "var(--text-muted)", textTransform: "uppercase", fontWeight: 700, letterSpacing: "0.04em" }}>
                  Sandbox Targets
                </div>
                <div style={{ fontSize: "1.2rem", fontWeight: 800, color: "var(--text-primary)" }}>
                  Isolated & SSO
                </div>
              </div>
            </div>
          </div>

          {/* 2-Column Split View */}
          <div className="showcase-main-grid">
            {/* Left Column: Filter + Product List */}
            <div className="showcase-sidebar">
              {/* Search Box */}
              <div>
                <label htmlFor={searchId} className="showcase-filter-group-label">
                  Filter Products
                </label>
                <div className="showcase-search-box">
                  <input
                    id={searchId}
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                    placeholder="Search by title, code or keyword…"
                    className="showcase-search-input"
                  />
                  <div className="showcase-search-icon">
                    <SearchIcon size={15} />
                  </div>
                </div>
              </div>

              {/* Segmented Control for Visibility */}
              <div>
                <div className="showcase-filter-group-label">Visibility Scope</div>
                <div className="showcase-segmented-control">
                  {VISIBILITY_OPTIONS.map((opt) => {
                    const isActive = visibility === opt.value;
                    return (
                      <button
                        key={opt.value}
                        type="button"
                        id={`filter-visibility-${opt.value || "all"}`}
                        onClick={() => setVisibility(opt.value)}
                        className={`showcase-segmented-btn ${isActive ? "active" : ""}`}
                      >
                        {opt.label}
                      </button>
                    );
                  })}
                </div>
              </div>

              {/* Meta row */}
              <div className="showcase-meta-row">
                <span>Showing <strong>{profiles.length}</strong> of {count} products</span>
                {search && (
                  <button
                    type="button"
                    onClick={() => setSearch("")}
                    className="showcase-clear-btn"
                  >
                    Clear Filter
                  </button>
                )}
              </div>

              {loading && <LoadingSpinner label="Loading showcase catalog…" />}
              {error && (
                <div
                  style={{
                    color: "var(--status-danger)",
                    background: "var(--status-danger-bg)",
                    border: "1px solid var(--status-danger-border)",
                    borderRadius: "8px",
                    padding: "0.75rem",
                    fontSize: "0.8125rem",
                  }}
                >
                  {error}
                </div>
              )}

              {!loading && !error && profiles.length === 0 && (
                <div
                  style={{
                    padding: "2.5rem 1rem",
                    textAlign: "center",
                    color: "var(--text-muted)",
                    border: "1px dashed var(--border-glass)",
                    borderRadius: "12px",
                    fontSize: "0.85rem",
                    background: "var(--glass-surface-sunken)",
                  }}
                >
                  No products match the selected criteria.
                </div>
              )}

              {/* Product Cards Stack */}
              <div className="showcase-cards-list">
                {profiles.map((p) => (
                  <ShowcaseCard
                    key={p.id}
                    profile={p}
                    selected={selected?.id === p.id}
                    onClick={() => handleSelect(p)}
                  />
                ))}
              </div>
            </div>

            {/* Right Column: Selected Product Command Center (Pinned & Responsive) */}
            <div className="showcase-detail-column">
              {!selected ? (
                <div className="showcase-detail-empty">
                  <BoxIcon size={36} color="var(--brand-primary)" />
                  <span style={{ fontWeight: 600 }}>Select a product to view profile and launch options</span>
                </div>
              ) : (
                <div key={selected.id} className="showcase-detail-panel">
                  {/* Product Header */}
                  <div className="showcase-detail-header">
                    <div style={{ display: "flex", alignItems: "flex-start", gap: "1rem" }}>
                      <ProductIcon code={selected.product_code} size={56} />

                      <div>
                        <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", flexWrap: "wrap" }}>
                          <h2 className="showcase-detail-title">{selected.product_name}</h2>
                          <span className="showcase-badge-code">{selected.product_code}</span>
                          <VisibilityBadge v={selected.visibility} />
                        </div>

                        <div className="showcase-detail-subtitle">
                          Registry Status: <strong style={{ color: "var(--text-primary)" }}>{selected.product_status}</strong> · Display Position: #{selected.display_order}
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* Interactive Live Demo Sandbox Card */}
                  <div
                    style={{
                      background: "var(--glass-surface-sunken)",
                      border: "1px solid var(--border-subtle)",
                      borderRadius: "12px",
                      padding: "1.25rem 1.5rem",
                      display: "flex",
                      flexDirection: "column",
                      gap: "1rem",
                    }}
                  >
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "0.5rem" }}>
                      <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                        <span
                          style={{
                            display: "inline-flex",
                            alignItems: "center",
                            gap: "5px",
                            padding: "3px 10px",
                            borderRadius: "999px",
                            fontSize: "0.75rem",
                            fontWeight: 700,
                            background: launchContract?.launchable
                              ? "var(--status-success-bg)"
                              : "var(--status-warning-bg)",
                            color: launchContract?.launchable
                              ? "var(--status-success)"
                              : "var(--status-warning)",
                            border: `1px solid ${
                              launchContract?.launchable
                                ? "var(--status-success-border)"
                                : "var(--status-warning-border)"
                            }`,
                          }}
                        >
                          <span
                            style={{
                              width: "7px",
                              height: "7px",
                              borderRadius: "50%",
                              background: launchContract?.launchable
                                ? "var(--status-success)"
                                : "var(--status-warning)",
                            }}
                          />
                          {launchContract?.launchable ? "Interactive Live Demo Online" : "Configuration Action Required"}
                        </span>

                        {launchContract?.environment_name && (
                          <span style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>
                            Environment: <strong>{launchContract.environment_name}</strong>
                          </span>
                        )}
                      </div>

                      {launchContract?.target_environment?.base_url && (
                        <a
                          href={launchContract.target_environment.base_url}
                          target="_blank"
                          rel="noreferrer"
                          style={{
                            fontSize: "0.78rem",
                            color: "var(--brand-primary)",
                            textDecoration: "none",
                            display: "inline-flex",
                            alignItems: "center",
                            gap: "4px",
                            fontWeight: 600,
                          }}
                        >
                          <GlobeIcon size={14} />
                          <span>Direct URL Target</span>
                        </a>
                      )}
                    </div>

                    {/* Launch & Config Actions Bar */}
                    <div style={{ display: "flex", gap: "0.75rem", flexWrap: "wrap", alignItems: "center" }}>
                      <button
                        type="button"
                        id="showcase-live-demo-btn"
                        onClick={handleLiveDemoClick}
                        disabled={actionPending}
                        style={{
                          padding: "0.65rem 1.4rem",
                          borderRadius: "8px",
                          fontSize: "0.85rem",
                          fontWeight: 700,
                          background: launchContract?.launchable
                            ? "var(--brand-primary)"
                            : "var(--glass-surface)",
                          color: launchContract?.launchable
                            ? "#ffffff"
                            : "var(--text-secondary)",
                          border: `1px solid ${
                            launchContract?.launchable ? "transparent" : "var(--border-glass)"
                          }`,
                          cursor: actionPending ? "not-allowed" : "pointer",
                          opacity: actionPending ? 0.7 : 1,
                          display: "inline-flex",
                          alignItems: "center",
                          gap: "0.5rem",
                          boxShadow: launchContract?.launchable
                            ? "0 4px 14px rgba(79, 70, 229, 0.35)"
                            : "none",
                          transition: "all 0.15s ease",
                        }}
                      >
                        <ShieldCheckIcon size={16} />
                        <span>
                          {actionPending
                            ? "Launching Sandbox…"
                            : `Launch Interactive Demo (${launchContract?.reason || "SSO"})`}
                        </span>
                      </button>

                      <button
                        type="button"
                        id="showcase-configure-demo-btn"
                        onClick={handleOpenConfig}
                        style={{
                          padding: "0.65rem 1.15rem",
                          borderRadius: "8px",
                          fontSize: "0.8125rem",
                          fontWeight: 600,
                          background: "var(--glass-surface-elevated)",
                          color: "var(--text-primary)",
                          border: "1px solid var(--border-subtle)",
                          cursor: "pointer",
                          display: "inline-flex",
                          alignItems: "center",
                          gap: "0.4rem",
                          boxShadow: "var(--shadow-sm)",
                        }}
                      >
                        <SlidersIcon size={15} />
                        <span>Configure Target</span>
                      </button>

                      <Link
                        to={presentUrl}
                        style={{
                          padding: "0.65rem 1.15rem",
                          borderRadius: "8px",
                          fontSize: "0.8125rem",
                          fontWeight: 600,
                          textDecoration: "none",
                          background: "var(--glass-surface-elevated)",
                          color: "var(--text-primary)",
                          border: "1px solid var(--border-subtle)",
                          display: "inline-flex",
                          alignItems: "center",
                          gap: "0.4rem",
                          boxShadow: "var(--shadow-sm)",
                        }}
                      >
                        <LayersIcon size={15} />
                        <span>Present Mode</span>
                      </Link>

                      {selected.visibility !== "published" ? (
                        <button
                          type="button"
                          id="showcase-publish-btn"
                          onClick={handlePublish}
                          disabled={actionPending}
                          style={{
                            padding: "0.65rem 1.15rem",
                            borderRadius: "8px",
                            fontWeight: 600,
                            fontSize: "0.8125rem",
                            cursor: actionPending ? "not-allowed" : "pointer",
                            background: "var(--status-success-bg)",
                            color: "var(--status-success)",
                            border: "1px solid var(--status-success-border)",
                          }}
                        >
                          Publish Profile
                        </button>
                      ) : (
                        <button
                          type="button"
                          id="showcase-unpublish-btn"
                          onClick={handleUnpublish}
                          disabled={actionPending}
                          style={{
                            padding: "0.65rem 1.15rem",
                            borderRadius: "8px",
                            border: "1px solid var(--status-warning-border)",
                            background: "var(--status-warning-bg)",
                            color: "var(--status-warning)",
                            fontWeight: 600,
                            fontSize: "0.8125rem",
                            cursor: actionPending ? "not-allowed" : "pointer",
                          }}
                        >
                          Unpublish Profile
                        </button>
                      )}
                    </div>

                    {launchContract?.launchable && launchContract.demo_user && (
                      <div
                        style={{
                          fontSize: "0.78rem",
                          color: "var(--text-secondary)",
                          display: "flex",
                          alignItems: "center",
                          gap: "8px",
                        }}
                      >
                        <span>Demo Principal:</span>
                        <code
                          style={{
                            background: "var(--glass-surface-elevated)",
                            padding: "2px 8px",
                            borderRadius: "5px",
                            border: "1px solid var(--border-subtle)",
                            color: "var(--brand-primary)",
                            fontWeight: 600,
                          }}
                        >
                          {launchContract.demo_user}
                        </code>
                        <span>({launchContract.demo_organization})</span>
                      </div>
                    )}
                  </div>

                  {actionMsg && (
                    <div
                      style={{
                        fontSize: "0.8125rem",
                        padding: "0.75rem 1rem",
                        borderRadius: "8px",
                        color: actionMsg.startsWith("Failed") || actionMsg.startsWith("Demo launch failed")
                          ? "var(--status-danger)"
                          : "var(--status-success)",
                        background: actionMsg.startsWith("Failed") || actionMsg.startsWith("Demo launch failed")
                          ? "var(--status-danger-bg)"
                          : "var(--status-success-bg)",
                        border: `1px solid ${
                          actionMsg.startsWith("Failed") || actionMsg.startsWith("Demo launch failed")
                            ? "var(--status-danger-border)"
                            : "var(--status-success-border)"
                        }`,
                        display: "flex",
                        alignItems: "center",
                        gap: "0.5rem",
                      }}
                    >
                      {actionMsg.startsWith("Failed") || actionMsg.startsWith("Demo launch failed") ? (
                        <AlertCircleIcon size={16} />
                      ) : (
                        <CheckCircleIcon size={16} />
                      )}
                      <span>{actionMsg}</span>
                    </div>
                  )}

                  {/* Diagnostic Demo Dialog */}
                  {showDemoDialog && (
                    <div
                      style={{
                        background: "var(--status-warning-bg)",
                        border: "1px solid var(--status-warning-border)",
                        borderRadius: "10px",
                        padding: "1rem 1.25rem",
                        display: "flex",
                        flexDirection: "column",
                        gap: "0.625rem",
                      }}
                    >
                      <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                        <AlertCircleIcon size={16} color="var(--status-warning)" />
                        <span style={{ fontSize: "0.875rem", fontWeight: 700, color: "var(--text-primary)" }}>
                          Live Demo Configuration Diagnostic
                        </span>
                      </div>
                      <p
                        style={{
                          fontSize: "0.8125rem",
                          color: "var(--text-secondary)",
                          margin: 0,
                          lineHeight: 1.5,
                        }}
                      >
                        Interactive Live Demo for product <strong>{selected.product_name}</strong> is currently unconfigured.
                        <br />
                        Reason: <code>{launchContract?.reason || "LAUNCH_CONFIG_NOT_FOUND"}</code>.
                        <br />
                        Platform Owner context cannot initiate tenant-user SSO launch without an active tenant membership assignment. To enable live showcase demonstrations, register an allowlisted Demo Environment target in Product Showcase configuration.
                      </p>
                      <div style={{ display: "flex", justifyContent: "flex-end" }}>
                        <button
                          type="button"
                          onClick={() => setShowDemoDialog(false)}
                          style={{
                            padding: "4px 12px",
                            borderRadius: "6px",
                            fontSize: "0.75rem",
                            fontWeight: 600,
                            background: "var(--glass-surface-elevated)",
                            border: "1px solid var(--border-subtle)",
                            color: "var(--text-primary)",
                            cursor: "pointer",
                          }}
                        >
                          Dismiss
                        </button>
                      </div>
                    </div>
                  )}

                  {/* Tagline Box */}
                  <div>
                    <div className="showcase-section-title">Tagline & Executive Hook</div>
                    <div
                      style={{
                        padding: "0.85rem 1.15rem",
                        borderRadius: "8px",
                        background: "var(--glass-surface-elevated)",
                        border: "1px solid var(--border-subtle)",
                        borderLeft: "4px solid var(--brand-primary)",
                        fontSize: "0.95rem",
                        fontStyle: "italic",
                        color: "var(--text-primary)",
                        lineHeight: 1.5,
                      }}
                    >
                      {selected.tagline ? `"${selected.tagline}"` : "No tagline defined for this product."}
                    </div>
                  </div>

                  {/* Product Overview Box */}
                  <div>
                    <div className="showcase-section-title">Product Description & Scope</div>
                    <div className="showcase-overview-box">
                      {selected.overview || <span style={{ color: "var(--text-muted)", fontStyle: "italic" }}>No overview narrative provided.</span>}
                    </div>
                  </div>

                  {/* Media Assets Section */}
                  <div>
                    <div className="showcase-section-title">
                      Showcase Media & Visual Assets ({selected.media.length})
                    </div>
                    {selected.media.length === 0 ? (
                      <div
                        style={{
                          padding: "1.25rem",
                          textAlign: "center",
                          color: "var(--text-muted)",
                          fontSize: "0.85rem",
                          background: "var(--glass-surface-sunken)",
                          borderRadius: "10px",
                          border: "1px dashed var(--border-subtle)",
                        }}
                      >
                        No presentation slides or media captures attached to this product showcase.
                      </div>
                    ) : (
                      <div className="showcase-media-grid">
                        {selected.media.map((m) => (
                          <div key={m.id} className="showcase-media-card">
                            <span
                              style={{
                                fontSize: "0.68rem",
                                padding: "2px 6px",
                                borderRadius: "4px",
                                background: "var(--brand-primary-light)",
                                color: "var(--brand-primary)",
                                textTransform: "uppercase",
                                fontWeight: 700,
                              }}
                            >
                              {m.media_type}
                            </span>
                            <div
                              style={{
                                fontSize: "0.8125rem",
                                fontWeight: 600,
                                color: "var(--text-primary)",
                                marginTop: 6,
                              }}
                            >
                              {m.title}
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>

                  {/* Platform Owner Demo Configuration Modal */}
                  {showConfigModal && (
                    <div className="showcase-modal-overlay">
                      <div className="showcase-modal-dialog">
                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                          <div>
                            <h3 style={{ margin: 0, fontSize: "1.1rem", fontWeight: 700, color: "var(--text-primary)" }}>
                              Configure Demo Environment
                            </h3>
                            <div style={{ fontSize: "0.78rem", color: "var(--text-muted)", marginTop: 2 }}>
                              {selected.product_name} ({selected.product_code})
                            </div>
                          </div>
                          <button
                            type="button"
                            onClick={() => setShowConfigModal(false)}
                            style={{
                              background: "transparent",
                              border: "none",
                              color: "var(--text-muted)",
                              cursor: "pointer",
                              fontSize: "1.25rem",
                              lineHeight: 1,
                            }}
                          >
                            ×
                          </button>
                        </div>

                        {configLoading ? (
                          <div style={{ padding: "2rem", textAlign: "center" }}>
                            <LoadingSpinner label="Loading launch configuration…" />
                          </div>
                        ) : (
                          <>
                            {configError && (
                              <div
                                style={{
                                  background: "var(--status-danger-bg)",
                                  border: "1px solid var(--status-danger-border)",
                                  borderRadius: "8px",
                                  padding: "0.75rem",
                                  color: "var(--status-danger)",
                                  fontSize: "0.8125rem",
                                }}
                              >
                                {configError}
                              </div>
                            )}

                            <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
                              <div>
                                <label style={{ display: "block", fontSize: "0.78rem", fontWeight: 600, color: "var(--text-secondary)", marginBottom: 4 }}>
                                  Target Demo Environment
                                </label>
                                <select
                                  id="cfg-target-env"
                                  value={cfgEnvId}
                                  onChange={(e) => setCfgEnvId(e.target.value)}
                                  style={{
                                    width: "100%",
                                    padding: "0.55rem 0.75rem",
                                    borderRadius: "8px",
                                    border: "1px solid var(--border-glass)",
                                    background: "var(--input-bg)",
                                    color: "var(--text-primary)",
                                    fontSize: "0.85rem",
                                    outline: "none",
                                  }}
                                >
                                  <option value="">-- Select Target Environment --</option>
                                  {(launchConfig?.available_environments ?? []).map((env) => (
                                    <option key={env.id} value={env.id}>
                                      {env.name} ({env.base_url})
                                    </option>
                                  ))}
                                </select>
                              </div>

                              <div>
                                <label style={{ display: "block", fontSize: "0.78rem", fontWeight: 600, color: "var(--text-secondary)", marginBottom: 4 }}>
                                  Launch Mode
                                </label>
                                <select
                                  id="cfg-launch-mode"
                                  value={cfgLaunchMode}
                                  onChange={(e) => setCfgLaunchMode(e.target.value)}
                                  style={{
                                    width: "100%",
                                    padding: "0.55rem 0.75rem",
                                    borderRadius: "8px",
                                    border: "1px solid var(--border-glass)",
                                    background: "var(--input-bg)",
                                    color: "var(--text-primary)",
                                    fontSize: "0.85rem",
                                    outline: "none",
                                  }}
                                >
                                  <option value="demo_only">Demo Only (Dedicated Sandbox)</option>
                                  <option value="direct_sso">Direct SSO Launch</option>
                                  <option value="standalone_sandbox">Standalone Sandbox</option>
                                </select>
                              </div>

                              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.75rem" }}>
                                <div>
                                  <label style={{ display: "block", fontSize: "0.78rem", fontWeight: 600, color: "var(--text-secondary)", marginBottom: 4 }}>
                                    Demo Org Code
                                  </label>
                                  <input
                                    id="cfg-org-code"
                                    type="text"
                                    value={cfgOrgCode}
                                    onChange={(e) => setCfgOrgCode(e.target.value)}
                                    placeholder="e.g. boss-demo-org"
                                    style={{
                                      width: "100%",
                                      padding: "0.55rem 0.75rem",
                                      borderRadius: "8px",
                                      border: "1px solid var(--border-glass)",
                                      background: "var(--input-bg)",
                                      color: "var(--text-primary)",
                                      fontSize: "0.85rem",
                                      boxSizing: "border-box",
                                      outline: "none",
                                    }}
                                  />
                                </div>
                                <div>
                                  <label style={{ display: "block", fontSize: "0.78rem", fontWeight: 600, color: "var(--text-secondary)", marginBottom: 4 }}>
                                    Demo User Email
                                  </label>
                                  <input
                                    id="cfg-user-email"
                                    type="email"
                                    value={cfgUserEmail}
                                    onChange={(e) => setCfgUserEmail(e.target.value)}
                                    placeholder="e.g. superadmin@gmail.com"
                                    style={{
                                      width: "100%",
                                      padding: "0.55rem 0.75rem",
                                      borderRadius: "8px",
                                      border: "1px solid var(--border-glass)",
                                      background: "var(--input-bg)",
                                      color: "var(--text-primary)",
                                      fontSize: "0.85rem",
                                      boxSizing: "border-box",
                                      outline: "none",
                                    }}
                                  />
                                </div>
                              </div>

                              <div>
                                <label style={{ display: "block", fontSize: "0.78rem", fontWeight: 600, color: "var(--text-secondary)", marginBottom: 4 }}>
                                  Operational Notes
                                </label>
                                <textarea
                                  id="cfg-notes"
                                  value={cfgNotes}
                                  onChange={(e) => setCfgNotes(e.target.value)}
                                  rows={2}
                                  placeholder="Operational launch guidelines..."
                                  style={{
                                    width: "100%",
                                    padding: "0.55rem 0.75rem",
                                    borderRadius: "8px",
                                    border: "1px solid var(--border-glass)",
                                    background: "var(--input-bg)",
                                    color: "var(--text-primary)",
                                    fontSize: "0.85rem",
                                    boxSizing: "border-box",
                                    outline: "none",
                                    resize: "none",
                                  }}
                                />
                              </div>
                            </div>

                            <div style={{ display: "flex", justifyContent: "flex-end", gap: "0.75rem", marginTop: "0.5rem" }}>
                              <button
                                type="button"
                                onClick={() => setShowConfigModal(false)}
                                disabled={configSaving}
                                style={{
                                  padding: "0.5rem 1rem",
                                  borderRadius: "8px",
                                  fontSize: "0.8125rem",
                                  fontWeight: 600,
                                  background: "var(--glass-surface-elevated)",
                                  border: "1px solid var(--border-subtle)",
                                  color: "var(--text-secondary)",
                                  cursor: "pointer",
                                }}
                              >
                                Cancel
                              </button>
                              <button
                                type="button"
                                id="cfg-save-btn"
                                onClick={handleSaveConfig}
                                disabled={configSaving}
                                style={{
                                  padding: "0.5rem 1.25rem",
                                  borderRadius: "8px",
                                  fontSize: "0.8125rem",
                                  fontWeight: 600,
                                  background: "var(--brand-primary)",
                                  color: "#ffffff",
                                  border: "none",
                                  cursor: configSaving ? "not-allowed" : "pointer",
                                  opacity: configSaving ? 0.7 : 1,
                                }}
                              >
                                {configSaving ? "Saving…" : "Save Configuration"}
                              </button>
                            </div>
                          </>
                        )}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </AppShell>
  );
}
