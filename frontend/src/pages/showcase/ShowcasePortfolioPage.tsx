/**
 * ShowcasePortfolioPage – Owner-side showcase portfolio grid with filters and
 * a detail panel. Routes: /showcase
 */
import { useEffect, useState, useCallback, useId, useMemo } from "react";
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
} from "../../components/Icons.tsx";
import { ShowcaseEmbeddedDemo } from "./ShowcaseEmbeddedDemo.tsx";

const VISIBILITY_OPTIONS: Array<{ value: ShowcaseVisibility | ""; label: string }> = [
  { value: "", label: "All" },
  { value: "published", label: "Published" },
  { value: "draft", label: "Draft" },
  { value: "hidden", label: "Hidden" },
];

function VisibilityBadge({ v }: { v: ShowcaseVisibility }) {
  const badgeClass =
    v === "published"
      ? "badge-success"
      : v === "hidden"
      ? "badge-warning"
      : "badge-neutral";

  return (
    <span className={`badge ${badgeClass}`} style={{ textTransform: "capitalize" }}>
      <span className="badge-dot" />
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
  const isDemoReady = profile.product_code === "qbr" && profile.visibility === "published";

  return (
    <button
      type="button"
      id={`showcase-card-${profile.product_code}`}
      data-testid={`showcase-card-${profile.product_code}`}
      data-profile-id={profile.id}
      data-product-code={profile.product_code}
      onClick={onClick}
      className={`showcase-card ${selected ? "selected" : ""}`}
    >
      <div className="showcase-card-header">
        <div style={{ minWidth: 0, flex: 1 }}>
          <div className="showcase-card-title">
            {profile.product_name}
          </div>
          <div className="showcase-card-badges">
            <span className="showcase-badge-code">
              {profile.product_code}
            </span>
            {profile.parent_product_code && (
              <span className="showcase-badge-suite">
                Suite: {profile.parent_product_code.toUpperCase()}
              </span>
            )}
            {profile.category && (
              <span className="showcase-badge-cat">
                {profile.category}
              </span>
            )}
          </div>
        </div>
        <VisibilityBadge v={profile.visibility} />
      </div>

      {profile.tagline ? (
        <div className="showcase-card-tagline">
          {profile.tagline}
        </div>
      ) : null}

      <div className="showcase-card-footer">
        <span
          className={`showcase-status-indicator ${
            isDemoReady ? "showcase-status-ready" : "showcase-status-catalog"
          }`}
        >
          {isDemoReady ? "● Live Demo Ready" : "○ Catalog Preview"}
        </span>
        <span>Order #{profile.display_order}</span>
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
  const [visibility, setVisibility] = useState<ShowcaseVisibility | "">("published");
  const [selected, setSelected] = useState<ShowcaseProfile | null>(null);
  const [selectedCategory, setSelectedCategory] = useState<string>("");
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

  const categories = useMemo(() => {
    const set = new Set<string>();
    profiles.forEach((p) => {
      if (p.category) set.add(p.category);
    });
    return Array.from(set).sort();
  }, [profiles]);

  const filteredProfiles = useMemo(() => {
    if (!selectedCategory) return profiles;
    return profiles.filter((p) => p.category === selectedCategory);
  }, [profiles, selectedCategory]);

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
            // Default to LMS if present, else first product
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
    showcaseApi.getLaunchability(selected.id).then((c) => {
      if (!cancelled) setLaunchContract(c);
    }).catch(() => {
      if (!cancelled) setLaunchContract({ launchable: false, reason: "CHECK_FAILED" });
    });
    return () => {
      cancelled = true;
    };
  }, [selected?.id]);

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
        const isNewTab =
          res.open_mode === "new_tab" ||
          launchContract.open_mode === "new_tab";

        if (isNewTab) {
          window.open(res.redirect_url, "_blank", "noopener,noreferrer");
          setActionMsg(`Opened ${selected.product_name} sandbox in a new browser tab.`);
        } else {
          setDemoLaunchUrl(res.redirect_url);
        }
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
        target_environment_id: cfgEnvId || null,
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

  return (
    <AppShell>
      <div className="showcase-layout-container">
        {/* Page Header */}
        <div className="showcase-page-header">
          <div>
            <div className="showcase-header-eyebrow">
              <BoxIcon size={14} />
              <span>Catalog & Portfolio</span>
            </div>
            <h1 className="showcase-header-title">
              Product Showcase
            </h1>
            <p className="showcase-header-subtitle">
              Enterprise portfolio management, product profiles, and presentation mode.
            </p>
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
            <Link
              to={presentUrl}
              id="showcase-present-mode-link"
              className="showcase-present-btn"
            >
              <LayersIcon size={15} />
              <span>Present Mode</span>
            </Link>
          </div>
        </div>

        {demoLaunchUrl && selected ? (
          <ShowcaseEmbeddedDemo
            productName={selected.product_name}
            productCode={selected.product_code}
            launchUrl={demoLaunchUrl}
            onBack={() => setDemoLaunchUrl(null)}
            backLabel="Back to Product Showcase"
          />
        ) : (
          /* 2-Column Layout */
          <div className="showcase-main-grid">
            {/* Left Column: Filter + Product List */}
            <div className="showcase-sidebar">
              {/* Search Input */}
              <div>
                <label htmlFor={searchId} className="showcase-filter-group-label">
                  Search Products
                </label>
                <div className="showcase-search-box">
                  <input
                    id={searchId}
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                    placeholder="Filter by product name…"
                    className="showcase-search-input"
                  />
                  <div className="showcase-search-icon">
                    <SearchIcon size={14} />
                  </div>
                </div>
              </div>

              {/* Visibility Filters */}
              <div>
                <div className="showcase-filter-group-label">
                  Visibility
                </div>
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

              {/* Category Filters */}
              {categories.length > 0 && (
                <div>
                  <div className="showcase-filter-group-label">
                    Category
                  </div>
                  <div className="showcase-category-chips">
                    <button
                      type="button"
                      id="filter-category-all"
                      onClick={() => setSelectedCategory("")}
                      className={`showcase-chip ${!selectedCategory ? "active" : ""}`}
                    >
                      All Categories
                    </button>
                    {categories.map((cat) => {
                      const isCatActive = selectedCategory === cat;
                      return (
                        <button
                          key={cat}
                          type="button"
                          id={`filter-category-${cat.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`}
                          onClick={() => setSelectedCategory(cat)}
                          className={`showcase-chip ${isCatActive ? "active" : ""}`}
                        >
                          {cat}
                        </button>
                      );
                    })}
                  </div>
                </div>
              )}

              <div className="showcase-meta-row">
                <span>{filteredProfiles.length} of {count} product{count !== 1 ? "s" : ""} shown</span>
                {selectedCategory && (
                  <button
                    type="button"
                    onClick={() => setSelectedCategory("")}
                    className="showcase-clear-btn"
                  >
                    Clear filter
                  </button>
                )}
              </div>

              {loading && <LoadingSpinner label="Loading portfolio…" />}
              {error && (
                <div className="alert-box alert-danger">
                  <AlertCircleIcon size={16} />
                  <span>{error}</span>
                </div>
              )}

              {!loading && !error && filteredProfiles.length === 0 && (
                <div className="showcase-detail-empty" style={{ height: "200px" }}>
                  <span>No showcase profiles match the selected criteria.</span>
                </div>
              )}

              <div className="showcase-cards-list">
                {filteredProfiles.map((p) => (
                  <ShowcaseCard
                    key={p.id}
                    profile={p}
                    selected={selected?.id === p.id}
                    onClick={() => handleSelect(p)}
                  />
                ))}
              </div>
            </div>

            {/* Right Column: Selected Product Detail Panel */}
            <div>
              {!selected ? (
                <div className="showcase-detail-empty">
                  <BoxIcon size={32} />
                  <span>Select a product to view showcase profile details</span>
                </div>
              ) : (
                <div className="showcase-detail-panel">
                  {/* Header Section */}
                  <div className="showcase-detail-header">
                    <div>
                      <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", flexWrap: "wrap" }}>
                        <h2 className="showcase-detail-title">
                          {selected.product_name}
                        </h2>
                        <span className="showcase-badge-code">
                          {selected.product_code}
                        </span>
                        {selected.parent_product_code && (
                          <span className="showcase-badge-suite">
                            Part of {selected.parent_product_code.toUpperCase()} Suite
                          </span>
                        )}
                        {selected.category && (
                          <span className="showcase-badge-cat">
                            {selected.category}
                          </span>
                        )}
                      </div>
                      <div className="showcase-detail-subtitle">
                        Status: <strong style={{ color: "var(--text-secondary)" }}>{selected.product_status}</strong> · Display Order: #{selected.display_order}
                      </div>
                    </div>

                    <div style={{ display: "flex", alignItems: "center", gap: "0.625rem" }}>
                      <span
                        className={`showcase-status-indicator ${
                          launchContract?.launchable ? "showcase-status-ready" : "showcase-status-catalog"
                        }`}
                        style={{ padding: "4px 8px" }}
                      >
                        <ShieldCheckIcon size={13} />
                        <span>{launchContract?.launchable ? "Live Demo Ready" : "Catalog Preview Only"}</span>
                      </span>
                      <VisibilityBadge v={selected.visibility} />
                    </div>
                  </div>

                  {/* Tagline & Overview */}
                  <div>
                    <div className="showcase-section-title">Tagline</div>
                    <p style={{ fontSize: "0.95rem", fontWeight: 500, color: "var(--text-primary)", margin: "0 0 1.25rem 0", lineHeight: 1.5 }}>
                      {selected.tagline || <span style={{ color: "var(--text-muted)", fontStyle: "italic" }}>No tagline defined.</span>}
                    </p>

                    <div className="showcase-section-title">Product Overview</div>
                    <div className="showcase-overview-box">
                      {selected.overview || <span style={{ color: "var(--text-muted)", fontStyle: "italic" }}>No overview provided.</span>}
                    </div>
                  </div>

                  {/* Media Section */}
                  <div>
                    <div className="showcase-section-title">
                      Media Assets ({selected.media.length})
                    </div>
                    {selected.media.length === 0 ? (
                      <div className="showcase-overview-box" style={{ textAlign: "center", color: "var(--text-muted)", padding: "1rem" }}>
                        No media assets attached to this profile.
                      </div>
                    ) : (
                      <div className="showcase-media-grid">
                        {selected.media.map((m) => (
                          <div key={m.id} className="showcase-media-card">
                            <span className="showcase-badge-code">
                              {m.media_type}
                            </span>
                            <div style={{ fontSize: "0.8125rem", fontWeight: 600, color: "var(--text-primary)", marginTop: 6 }}>
                              {m.title}
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>

                  {/* Launch Readiness & Actions */}
                  <div className="showcase-actions-bar">
                    {selected.visibility !== "published" ? (
                      <button
                        type="button"
                        id="showcase-publish-btn"
                        onClick={handlePublish}
                        disabled={actionPending}
                        className="btn-primary"
                        style={{ minHeight: "36px", padding: "0 1rem", fontSize: "0.8125rem" }}
                      >
                        Publish Profile
                      </button>
                    ) : (
                      <button
                        type="button"
                        id="showcase-unpublish-btn"
                        onClick={handleUnpublish}
                        disabled={actionPending}
                        className="btn-secondary"
                        style={{ minHeight: "36px", padding: "0 1rem", fontSize: "0.8125rem", color: "var(--status-warning)", borderColor: "var(--status-warning-border)" }}
                      >
                        Unpublish Profile
                      </button>
                    )}

                    <Link
                      to={presentUrl}
                      className="btn-secondary"
                      style={{ minHeight: "36px", padding: "0 1rem", fontSize: "0.8125rem", textDecoration: "none", display: "inline-flex", alignItems: "center", gap: "0.4rem" }}
                    >
                      <LayersIcon size={14} />
                      <span>Present Mode</span>
                    </Link>

                    <button
                      type="button"
                      id="showcase-live-demo-btn"
                      onClick={handleLiveDemoClick}
                      disabled={actionPending}
                      className={launchContract?.launchable ? "btn-primary" : "btn-secondary"}
                      style={{ minHeight: "36px", padding: "0 1rem", fontSize: "0.8125rem", display: "inline-flex", alignItems: "center", gap: "0.4rem" }}
                    >
                      <ShieldCheckIcon size={14} />
                      <span>
                        {actionPending
                          ? "Launching…"
                          : !launchContract?.launchable
                          ? `Demo Unavailable (${launchContract?.reason || "PENDING"})`
                          : "Launch Live Demo"}
                      </span>
                    </button>

                    <button
                      type="button"
                      id="showcase-configure-demo-btn"
                      onClick={handleOpenConfig}
                      className="btn-secondary"
                      style={{ minHeight: "36px", padding: "0 1rem", fontSize: "0.8125rem", display: "inline-flex", alignItems: "center", gap: "0.4rem" }}
                    >
                      <SlidersIcon size={14} />
                      <span>Configure Demo</span>
                    </button>

                    {launchContract?.launchable && launchContract.demo_user && (
                      <span style={{ fontSize: "0.75rem", color: "var(--brand-primary)", fontWeight: 500 }}>
                        Demo: {launchContract.demo_user} ({launchContract.demo_organization})
                      </span>
                    )}
                  </div>

                  {actionMsg && (
                    <div
                      className={`alert-box ${actionMsg.startsWith("Failed") ? "alert-danger" : "alert-success"}`}
                      style={{ marginBottom: 0 }}
                    >
                      {actionMsg.startsWith("Failed") ? (
                        <AlertCircleIcon size={15} />
                      ) : (
                        <CheckCircleIcon size={15} />
                      )}
                      <span>{actionMsg}</span>
                    </div>
                  )}

                  {/* Diagnostic Demo Dialog */}
                  {showDemoDialog && (
                    <div className="alert-box alert-danger" style={{ flexDirection: "column", gap: "0.5rem" }}>
                      <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                        <AlertCircleIcon size={16} />
                        <span style={{ fontSize: "0.875rem", fontWeight: 700 }}>
                          Live Demo Configuration Diagnostic
                        </span>
                      </div>
                      <p style={{ margin: 0, fontSize: "0.8125rem", lineHeight: 1.5 }}>
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
                          className="btn-secondary"
                          style={{ minHeight: "28px", padding: "0 0.75rem", fontSize: "0.75rem" }}
                        >
                          Dismiss
                        </button>
                      </div>
                    </div>
                  )}

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
                              <div className="alert-box alert-danger">
                                <AlertCircleIcon size={15} />
                                <span>{configError}</span>
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
                                  className="form-input"
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
                                  className="form-input"
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
                                    className="form-input"
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
                                    placeholder="e.g. demo.member@demotenant.test"
                                    className="form-input"
                                  />
                                </div>
                              </div>

                              <div>
                                <label style={{ display: "block", fontSize: "0.78rem", fontWeight: 600, color: "var(--text-secondary)", marginBottom: 4 }}>
                                  Notes
                                </label>
                                <textarea
                                  id="cfg-notes"
                                  value={cfgNotes}
                                  onChange={(e) => setCfgNotes(e.target.value)}
                                  rows={2}
                                  placeholder="Operational launch guidelines..."
                                  className="form-input"
                                  style={{ resize: "none" }}
                                />
                              </div>
                            </div>

                            <div style={{ display: "flex", justifyContent: "flex-end", gap: "0.75rem", marginTop: "0.5rem" }}>
                              <button
                                type="button"
                                onClick={() => setShowConfigModal(false)}
                                disabled={configSaving}
                                className="btn-secondary"
                                style={{ minHeight: "36px", padding: "0 1rem" }}
                              >
                                Cancel
                              </button>
                              <button
                                type="button"
                                id="cfg-save-btn"
                                onClick={handleSaveConfig}
                                disabled={configSaving}
                                className="btn-primary"
                                style={{ minHeight: "36px", padding: "0 1.25rem" }}
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
        )}
      </div>
    </AppShell>
  );
}
