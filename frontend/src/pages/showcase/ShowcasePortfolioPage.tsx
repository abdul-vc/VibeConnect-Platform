/**
 * ShowcasePortfolioPage – Owner-side showcase portfolio grid with filters and
 * a detail panel. Routes: /showcase
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
} from "../../components/Icons.tsx";
import { ShowcaseEmbeddedDemo } from "./ShowcaseEmbeddedDemo.tsx";

const VISIBILITY_OPTIONS: Array<{ value: ShowcaseVisibility | ""; label: string }> = [
  { value: "", label: "All" },
  { value: "published", label: "Published" },
  { value: "draft", label: "Draft" },
  { value: "hidden", label: "Hidden" },
];

function VisibilityBadge({ v }: { v: ShowcaseVisibility }) {
  const styleMap: Record<ShowcaseVisibility, { bg: string; color: string; border: string }> = {
    published: {
      bg: "var(--status-success-bg, rgba(16, 185, 129, 0.12))",
      color: "var(--status-success, #10b981)",
      border: "var(--status-success-border, rgba(16, 185, 129, 0.28))",
    },
    draft: {
      bg: "var(--status-neutral-bg, rgba(148, 163, 184, 0.1))",
      color: "var(--status-neutral, #94a3b8)",
      border: "var(--status-neutral-border, rgba(148, 163, 184, 0.22))",
    },
    hidden: {
      bg: "var(--status-warning-bg, rgba(245, 158, 11, 0.12))",
      color: "var(--status-warning, #f59e0b)",
      border: "var(--status-warning-border, rgba(245, 158, 11, 0.28))",
    },
  };
  const current = styleMap[v] ?? styleMap.draft;

  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        padding: "3px 10px",
        borderRadius: "999px",
        fontSize: "0.72rem",
        fontWeight: 600,
        letterSpacing: "0.02em",
        background: current.bg,
        color: current.color,
        border: `1px solid ${current.border}`,
        textTransform: "capitalize",
      }}
    >
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
  return (
    <button
      type="button"
      id={`showcase-card-${profile.product_code}`}
      data-testid={`showcase-card-${profile.product_code}`}
      data-profile-id={profile.id}
      data-product-code={profile.product_code}
      onClick={onClick}
      style={{
        display: "block",
        width: "100%",
        textAlign: "left",
        background: selected ? "var(--glass-surface-hover, rgba(26, 38, 64, 0.85))" : "var(--glass-surface, rgba(15, 23, 42, 0.72))",
        border: selected
          ? "1.5px solid var(--brand-primary, #6366f1)"
          : "1px solid var(--border-glass, rgba(255, 255, 255, 0.14))",
        borderRadius: "12px",
        padding: "1rem 1.15rem",
        cursor: "pointer",
        transition: "all 0.18s ease",
        boxShadow: selected ? "0 0 0 1px var(--brand-primary, #6366f1), var(--shadow-sm)" : "var(--shadow-sm)",
        boxSizing: "border-box",
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 8 }}>
        <div style={{ minWidth: 0, flex: 1 }}>
          <div
            style={{
              fontWeight: 700,
              fontSize: "0.95rem",
              color: "var(--text-primary, #f8fafc)",
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
            }}
          >
            {profile.product_name}
          </div>
          <div
            style={{
              display: "inline-block",
              fontSize: "0.72rem",
              fontWeight: 700,
              color: "var(--brand-primary, #6366f1)",
              background: "var(--brand-primary-light, rgba(99, 102, 241, 0.12))",
              padding: "1px 6px",
              borderRadius: "4px",
              marginTop: 4,
              textTransform: "uppercase",
              letterSpacing: "0.04em",
            }}
          >
            {profile.product_code}
          </div>
        </div>
        <VisibilityBadge v={profile.visibility} />
      </div>

      {profile.tagline ? (
        <div
          style={{
            marginTop: 8,
            fontSize: "0.82rem",
            color: "var(--text-secondary, #94a3b8)",
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
          marginTop: 10,
          paddingTop: 8,
          borderTop: "1px solid var(--border-subtle, rgba(255, 255, 255, 0.08))",
          fontSize: "0.72rem",
          color: "var(--text-muted, #64748b)",
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
        }}
      >
        <span>Order #{profile.display_order}</span>
        <span>{profile.media.length} media asset{profile.media.length === 1 ? "" : "s"}</span>
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

  const isDemoParam = searchParams.get("demo") === "true";
  const lastLaunchedIdRef = useRef<string | null>(null);

  // Sync selected with query param when user navigates or switches via sidebar
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
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            gap: "1.25rem",
            padding: "1.5rem",
            minHeight: "100%",
            boxSizing: "border-box",
          }}
        >
          {/* Page Header */}
          <div
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              flexWrap: "wrap",
              gap: "1rem",
              borderBottom: "1px solid var(--border-subtle, rgba(255, 255, 255, 0.08))",
              paddingBottom: "1rem",
            }}
          >
            <div>
              <h1
                style={{
                  fontSize: "1.375rem",
                  fontWeight: 800,
                  color: "var(--text-primary, #f8fafc)",
                  margin: 0,
                  letterSpacing: "-0.01em",
                }}
              >
                Product Showcase
              </h1>
              <p
                style={{
                  fontSize: "0.85rem",
                  color: "var(--text-secondary, #94a3b8)",
                  margin: "4px 0 0 0",
                }}
              >
                Enterprise portfolio management, product profiles, and presentation mode.
              </p>
            </div>

            <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
              <Link
                to={presentUrl}
                id="showcase-present-mode-link"
                className="btn-primary"
                style={{
                  padding: "0.55rem 1.15rem",
                  borderRadius: "8px",
                  fontSize: "0.8125rem",
                  fontWeight: 600,
                  textDecoration: "none",
                  display: "inline-flex",
                  alignItems: "center",
                  gap: "0.5rem",
                  background: "var(--brand-primary, #6366f1)",
                  color: "#ffffff",
                  boxShadow: "var(--shadow-sm)",
                }}
              >
                <LayersIcon size={15} />
                <span>Present Mode</span>
              </Link>
            </div>
          </div>
          {/* 2-Column Layout */}
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "340px 1fr",
              gap: "1.5rem",
              alignItems: "start",
            }}
          >
          {/* Left Column: Filter + Product List */}
          <div
            style={{
              display: "flex",
              flexDirection: "column",
              gap: "1rem",
            }}
          >
            {/* Search Input */}
            <div>
              <label
                htmlFor={searchId}
                style={{
                  fontSize: "0.75rem",
                  fontWeight: 600,
                  color: "var(--text-secondary)",
                  display: "block",
                  marginBottom: 6,
                  textTransform: "uppercase",
                  letterSpacing: "0.04em",
                }}
              >
                Search Products
              </label>
              <div style={{ position: "relative" }}>
                <input
                  id={searchId}
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder="Filter by product name…"
                  style={{
                    width: "100%",
                    padding: "0.55rem 0.75rem 0.55rem 2.25rem",
                    borderRadius: "8px",
                    border: "1px solid var(--border-glass, rgba(255, 255, 255, 0.14))",
                    background: "var(--glass-surface, rgba(15, 23, 42, 0.7))",
                    color: "var(--text-primary)",
                    fontSize: "0.85rem",
                    boxSizing: "border-box",
                    outline: "none",
                  }}
                />
                <div
                  style={{
                    position: "absolute",
                    left: "0.75rem",
                    top: "50%",
                    transform: "translateY(-50%)",
                    color: "var(--text-muted)",
                    display: "flex",
                    alignItems: "center",
                  }}
                >
                  <SearchIcon size={14} />
                </div>
              </div>
            </div>

            {/* Visibility Filters */}
            <div>
              <div
                style={{
                  fontSize: "0.75rem",
                  fontWeight: 600,
                  color: "var(--text-secondary)",
                  marginBottom: 6,
                  textTransform: "uppercase",
                  letterSpacing: "0.04em",
                }}
              >
                Visibility
              </div>
              <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                {VISIBILITY_OPTIONS.map((opt) => {
                  const isActive = visibility === opt.value;
                  return (
                    <button
                      key={opt.value}
                      type="button"
                      id={`filter-visibility-${opt.value || "all"}`}
                      onClick={() => setVisibility(opt.value)}
                      style={{
                        padding: "4px 11px",
                        borderRadius: "999px",
                        fontSize: "0.75rem",
                        fontWeight: 600,
                        border: isActive
                          ? "1.5px solid var(--brand-primary, #6366f1)"
                          : "1px solid var(--border-glass, rgba(255, 255, 255, 0.12))",
                        background: isActive
                          ? "var(--brand-primary-light, rgba(99, 102, 241, 0.16))"
                          : "var(--glass-surface, rgba(15, 23, 42, 0.6))",
                        color: isActive
                          ? "var(--brand-primary, #6366f1)"
                          : "var(--text-secondary, #94a3b8)",
                        cursor: "pointer",
                        transition: "all 0.15s ease",
                      }}
                    >
                      {opt.label}
                    </button>
                  );
                })}
              </div>
            </div>

            <div
              style={{
                fontSize: "0.75rem",
                color: "var(--text-muted)",
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                borderBottom: "1px solid var(--border-subtle)",
                paddingBottom: 6,
              }}
            >
              <span>{count} product{count !== 1 ? "s" : ""} registered</span>
            </div>

            {loading && <LoadingSpinner label="Loading portfolio…" />}
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
                }}
              >
                No showcase profiles match the selected criteria.
              </div>
            )}

            <div style={{ display: "flex", flexDirection: "column", gap: "0.625rem" }}>
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

          {/* Right Column: Selected Product Detail Panel */}
          <div>
            {!selected ? (
              <div
                style={{
                  height: "380px",
                  display: "flex",
                  flexDirection: "column",
                  alignItems: "center",
                  justifyContent: "center",
                  color: "var(--text-muted)",
                  fontSize: "0.9rem",
                  border: "1px dashed var(--border-glass)",
                  borderRadius: "16px",
                  background: "var(--glass-surface, rgba(15, 23, 42, 0.4))",
                  gap: "0.75rem",
                }}
              >
                <BoxIcon size={32} />
                <span>Select a product to view showcase profile details</span>
              </div>
            ) : (
              <div
                style={{
                  background: "var(--glass-surface-elevated, rgba(24, 34, 56, 0.88))",
                  border: "1px solid var(--border-glass, rgba(255, 255, 255, 0.14))",
                  borderRadius: "16px",
                  padding: "1.75rem",
                  boxShadow: "var(--shadow-sm)",
                  display: "flex",
                  flexDirection: "column",
                  gap: "1.5rem",
                }}
              >
                {/* Header Section */}
                <div
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "flex-start",
                    gap: "1rem",
                    flexWrap: "wrap",
                    borderBottom: "1px solid var(--border-subtle, rgba(255, 255, 255, 0.08))",
                    paddingBottom: "1.25rem",
                  }}
                >
                  <div>
                    <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
                      <h2
                        style={{
                          fontSize: "1.35rem",
                          fontWeight: 800,
                          color: "var(--text-primary)",
                          margin: 0,
                        }}
                      >
                        {selected.product_name}
                      </h2>
                      <span
                        style={{
                          padding: "2px 8px",
                          borderRadius: "4px",
                          fontSize: "0.75rem",
                          fontWeight: 700,
                          background: "var(--brand-primary-light, rgba(99, 102, 241, 0.12))",
                          color: "var(--brand-primary, #6366f1)",
                          border: "1px solid var(--brand-primary-light)",
                          textTransform: "uppercase",
                        }}
                      >
                        {selected.product_code}
                      </span>
                    </div>
                    <div
                      style={{
                        fontSize: "0.78rem",
                        color: "var(--text-muted)",
                        marginTop: 4,
                      }}
                    >
                      Status: {selected.product_status} · Order #{selected.display_order}
                    </div>
                  </div>

                  <div style={{ display: "flex", alignItems: "center", gap: "0.625rem" }}>
                    <VisibilityBadge v={selected.visibility} />
                  </div>
                </div>

                {/* Tagline & Overview */}
                <div>
                  <div
                    style={{
                      fontSize: "0.75rem",
                      fontWeight: 700,
                      color: "var(--text-muted)",
                      textTransform: "uppercase",
                      letterSpacing: "0.05em",
                      marginBottom: 6,
                    }}
                  >
                    Tagline
                  </div>
                  <p
                    style={{
                      fontSize: "0.95rem",
                      fontWeight: 500,
                      color: "var(--text-primary)",
                      margin: "0 0 1rem 0",
                      lineHeight: 1.5,
                    }}
                  >
                    {selected.tagline || <span style={{ color: "var(--text-muted)", fontStyle: "italic" }}>No tagline defined.</span>}
                  </p>

                  <div
                    style={{
                      fontSize: "0.75rem",
                      fontWeight: 700,
                      color: "var(--text-muted)",
                      textTransform: "uppercase",
                      letterSpacing: "0.05em",
                      marginBottom: 6,
                    }}
                  >
                    Product Overview
                  </div>
                  <div
                    style={{
                      fontSize: "0.875rem",
                      color: "var(--text-secondary)",
                      lineHeight: 1.65,
                      background: "var(--glass-surface-sunken, rgba(4, 8, 18, 0.6))",
                      padding: "1rem 1.25rem",
                      borderRadius: "10px",
                      border: "1px solid var(--border-subtle)",
                      whiteSpace: "pre-line",
                    }}
                  >
                    {selected.overview || <span style={{ color: "var(--text-muted)", fontStyle: "italic" }}>No overview provided.</span>}
                  </div>
                </div>

                {/* Media Section */}
                <div>
                  <div
                    style={{
                      fontSize: "0.75rem",
                      fontWeight: 700,
                      color: "var(--text-muted)",
                      textTransform: "uppercase",
                      letterSpacing: "0.05em",
                      marginBottom: 8,
                    }}
                  >
                    Media Assets ({selected.media.length})
                  </div>
                  {selected.media.length === 0 ? (
                    <div
                      style={{
                        padding: "1rem",
                        textAlign: "center",
                        color: "var(--text-muted)",
                        fontSize: "0.8125rem",
                        background: "var(--glass-surface-sunken, rgba(4, 8, 18, 0.4))",
                        borderRadius: "8px",
                        border: "1px dashed var(--border-subtle)",
                      }}
                    >
                      No media assets attached to this profile.
                    </div>
                  ) : (
                    <div
                      style={{
                        display: "grid",
                        gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))",
                        gap: "0.75rem",
                      }}
                    >
                      {selected.media.map((m) => (
                        <div
                          key={m.id}
                          style={{
                            background: "var(--glass-surface-sunken, rgba(4, 8, 18, 0.6))",
                            border: "1px solid var(--border-subtle)",
                            borderRadius: "8px",
                            padding: "0.75rem",
                          }}
                        >
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

                {/* Launch Readiness & Actions */}
                <div
                  style={{
                    borderTop: "1px solid var(--border-subtle, rgba(255, 255, 255, 0.08))",
                    paddingTop: "1.25rem",
                    display: "flex",
                    flexDirection: "column",
                    gap: "1rem",
                  }}
                >
                  <div style={{ display: "flex", gap: "0.75rem", flexWrap: "wrap", alignItems: "center" }}>
                    {selected.visibility !== "published" ? (
                      <button
                        type="button"
                        id="showcase-publish-btn"
                        onClick={handlePublish}
                        disabled={actionPending}
                        className="btn-primary"
                        style={{
                          padding: "0.55rem 1.25rem",
                          borderRadius: "8px",
                          fontWeight: 600,
                          fontSize: "0.8125rem",
                          cursor: actionPending ? "not-allowed" : "pointer",
                          opacity: actionPending ? 0.6 : 1,
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
                          padding: "0.55rem 1.25rem",
                          borderRadius: "8px",
                          border: "1px solid var(--status-warning-border, #f59e0b)",
                          background: "var(--status-warning-bg, rgba(245, 158, 11, 0.1))",
                          color: "var(--status-warning, #f59e0b)",
                          fontWeight: 600,
                          fontSize: "0.8125rem",
                          cursor: actionPending ? "not-allowed" : "pointer",
                          opacity: actionPending ? 0.6 : 1,
                        }}
                      >
                        Unpublish Profile
                      </button>
                    )}

                    <Link
                      to={presentUrl}
                      style={{
                        padding: "0.55rem 1.15rem",
                        borderRadius: "8px",
                        fontSize: "0.8125rem",
                        fontWeight: 600,
                        textDecoration: "none",
                        background: "var(--glass-surface-sunken)",
                        color: "var(--text-primary)",
                        border: "1px solid var(--border-glass)",
                        display: "inline-flex",
                        alignItems: "center",
                        gap: "0.4rem",
                      }}
                    >
                      <LayersIcon size={14} />
                      <span>Present Mode</span>
                    </Link>

                    <button
                      type="button"
                      id="showcase-live-demo-btn"
                      onClick={handleLiveDemoClick}
                      disabled={actionPending}
                      style={{
                        padding: "0.55rem 1.15rem",
                        borderRadius: "8px",
                        fontSize: "0.8125rem",
                        fontWeight: 600,
                        background: launchContract?.launchable
                          ? "var(--brand-primary, #6366f1)"
                          : "var(--glass-surface-sunken)",
                        color: launchContract?.launchable
                          ? "#ffffff"
                          : "var(--text-muted, #64748b)",
                        border: `1px solid ${
                          launchContract?.launchable
                            ? "var(--brand-primary)"
                            : "var(--border-subtle)"
                        }`,
                        cursor: actionPending ? "not-allowed" : "pointer",
                        opacity: actionPending ? 0.7 : 1,
                        display: "inline-flex",
                        alignItems: "center",
                        gap: "0.4rem",
                      }}
                    >
                      <ShieldCheckIcon size={14} />
                      <span>{actionPending ? "Launching…" : `Live Demo (${launchContract?.reason || "SSO"})`}</span>
                    </button>

                    <button
                      type="button"
                      id="showcase-configure-demo-btn"
                      onClick={handleOpenConfig}
                      style={{
                        padding: "0.55rem 1.15rem",
                        borderRadius: "8px",
                        fontSize: "0.8125rem",
                        fontWeight: 600,
                        background: "var(--glass-surface-sunken)",
                        color: "var(--text-secondary)",
                        border: "1px solid var(--border-subtle)",
                        cursor: "pointer",
                        display: "inline-flex",
                        alignItems: "center",
                        gap: "0.4rem",
                      }}
                    >
                      <SlidersIcon size={14} />
                      <span>Configure Demo</span>
                    </button>

                    {launchContract?.launchable && launchContract.demo_user && (
                      <span
                        style={{
                          fontSize: "0.75rem",
                          color: "var(--brand-primary, #818cf8)",
                          paddingLeft: "0.25rem",
                        }}
                      >
                        Demo: {launchContract.demo_user} ({launchContract.demo_organization})
                      </span>
                    )}
                  </div>

                  {actionMsg && (
                    <div
                      style={{
                        fontSize: "0.8125rem",
                        color: actionMsg.startsWith("Failed")
                          ? "var(--status-danger)"
                          : "var(--status-success)",
                        display: "flex",
                        alignItems: "center",
                        gap: "0.4rem",
                      }}
                    >
                      {actionMsg.startsWith("Failed") ? (
                        <AlertCircleIcon size={14} />
                      ) : (
                        <CheckCircleIcon size={14} />
                      )}
                      <span>{actionMsg}</span>
                    </div>
                  )}

                  {/* Diagnostic Demo Dialog */}
                  {showDemoDialog && (
                    <div
                      style={{
                        background: "var(--glass-surface-sunken, rgba(4, 8, 18, 0.8))",
                        border: "1px solid var(--border-glass, rgba(255, 255, 255, 0.14))",
                        borderRadius: "10px",
                        padding: "1rem 1.25rem",
                        display: "flex",
                        flexDirection: "column",
                        gap: "0.625rem",
                      }}
                    >
                      <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                        <AlertCircleIcon size={16} color="var(--status-warning, #f59e0b)" />
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
                            background: "var(--glass-surface)",
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

                  {/* Platform Owner Demo Configuration Modal */}
                  {showConfigModal && (
                    <div
                      style={{
                        position: "fixed",
                        top: 0,
                        left: 0,
                        right: 0,
                        bottom: 0,
                        backgroundColor: "rgba(0, 0, 0, 0.75)",
                        backdropFilter: "blur(6px)",
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                        zIndex: 1000,
                        padding: "1rem",
                      }}
                    >
                      <div
                        style={{
                          background: "var(--glass-surface-elevated, #0f172a)",
                          border: "1px solid var(--border-glass, rgba(255, 255, 255, 0.16))",
                          borderRadius: "14px",
                          width: "100%",
                          maxWidth: "520px",
                          padding: "1.75rem",
                          boxShadow: "0 25px 50px -12px rgba(0, 0, 0, 0.5)",
                          display: "flex",
                          flexDirection: "column",
                          gap: "1.25rem",
                        }}
                      >
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
                                  background: "var(--status-danger-bg, rgba(239, 68, 68, 0.12))",
                                  border: "1px solid var(--status-danger-border, rgba(239, 68, 68, 0.3))",
                                  borderRadius: "8px",
                                  padding: "0.75rem",
                                  color: "var(--status-danger, #ef4444)",
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
                                    border: "1px solid var(--border-glass, rgba(255, 255, 255, 0.15))",
                                    background: "var(--glass-surface-sunken, rgba(4, 8, 18, 0.8))",
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
                                    border: "1px solid var(--border-glass, rgba(255, 255, 255, 0.15))",
                                    background: "var(--glass-surface-sunken, rgba(4, 8, 18, 0.8))",
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
                                      border: "1px solid var(--border-glass, rgba(255, 255, 255, 0.15))",
                                      background: "var(--glass-surface-sunken, rgba(4, 8, 18, 0.8))",
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
                                    placeholder="e.g. demo.member@demotenant.test"
                                    style={{
                                      width: "100%",
                                      padding: "0.55rem 0.75rem",
                                      borderRadius: "8px",
                                      border: "1px solid var(--border-glass, rgba(255, 255, 255, 0.15))",
                                      background: "var(--glass-surface-sunken, rgba(4, 8, 18, 0.8))",
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
                                  Notes
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
                                    border: "1px solid var(--border-glass, rgba(255, 255, 255, 0.15))",
                                    background: "var(--glass-surface-sunken, rgba(4, 8, 18, 0.8))",
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
                                  background: "var(--glass-surface)",
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
                                className="btn-primary"
                                style={{
                                  padding: "0.5rem 1.25rem",
                                  borderRadius: "8px",
                                  fontSize: "0.8125rem",
                                  fontWeight: 600,
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
              </div>
            )}
          </div>
        </div>
      </div>
    )}
  </AppShell>
);
}
