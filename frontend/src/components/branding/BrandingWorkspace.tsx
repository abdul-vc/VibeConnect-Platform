/**
 * Branding Workspace Component (Phase 4A/4B).
 *
 * Provides:
 * - Allowlisted CSS Token Editor (brand_primary, brand_gradient, etc.)
 * - Live Refractive Glass Preview Card
 * - Asset Manager (Logo & Favicon upload with validation)
 * - Revision History with Publish, Rollback, and Preview actions
 * - Direct application via CSS custom properties
 */

import React, { useState, useEffect, useCallback, useMemo } from "react";
import {
  brandingApi,
  type BrandingProfile,
  type BrandingRevision,
  type SaveDraftPayload,
} from "../../api/branding.ts";
import { ApiError } from "../../api/client.ts";
import {
  RotateCcwIcon,
  ShieldCheckIcon,
  UploadIcon,
  EyeIcon,
  AlertCircleIcon,
  CheckCircleIcon,
  LayersIcon,
} from "../Icons.tsx";

const ALLOWLISTED_TOKENS = [
  { key: "brand_primary", label: "Brand Primary", type: "color", default: "#6366f1" },
  { key: "brand_primary_hover", label: "Brand Primary Hover", type: "color", default: "#4f46e5" },
  { key: "brand_primary_light", label: "Brand Primary Light", type: "text", default: "rgba(99, 102, 241, 0.16)" },
  { key: "brand_gradient", label: "Brand Gradient", type: "text", default: "linear-gradient(135deg, #6366f1 0%, #8b5cf6 50%, #38bdf8 100%)" },
  { key: "bg_app", label: "App Background", type: "color", default: "#070b14" },
  { key: "text_primary", label: "Primary Text", type: "color", default: "#f8fafc" },
  { key: "text_secondary", label: "Secondary Text", type: "color", default: "#94a3b8" },
  { key: "border_focus", label: "Focus Border", type: "color", default: "#6366f1" },
] as const;

interface BrandingWorkspaceProps {
  readonly title: string;
  readonly subtitle: string;
  readonly isOwner?: boolean;
  readonly organizationId?: string;
  readonly organizationName?: string;
}

export const BrandingWorkspace: React.FC<BrandingWorkspaceProps> = ({
  title,
  subtitle,
  isOwner = false,
  organizationId,
  organizationName,
}) => {
  const [profile, setProfile] = useState<BrandingProfile | null>(null);
  const [revisions, setRevisions] = useState<BrandingRevision[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [isSaving, setIsSaving] = useState<boolean>(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [actionSuccess, setActionSuccess] = useState<string | null>(null);

  // Editor Draft State
  const [editorTokens, setEditorTokens] = useState<Record<string, string>>({
    brand_primary: "#6366f1",
    brand_primary_hover: "#4f46e5",
    brand_primary_light: "rgba(99, 102, 241, 0.16)",
    brand_gradient: "linear-gradient(135deg, #6366f1 0%, #8b5cf6 50%, #38bdf8 100%)",
    bg_app: "#070b14",
    text_primary: "#f8fafc",
    text_secondary: "#94a3b8",
    border_focus: "#6366f1",
  });
  const [changeSummary, setChangeSummary] = useState<string>("");
  const [selectedLogoId, setSelectedLogoId] = useState<string | null>(null);
  const [selectedFaviconId, setSelectedFaviconId] = useState<string | null>(null);
  const [activeAssetPreview, setActiveAssetPreview] = useState<{ logo?: string; favicon?: string }>({});

  // Active Draft Revision
  const draftRevision = useMemo(
    () => revisions.find((r) => r.status === "draft") || null,
    [revisions]
  );

  // Load Profile & Revisions
  const loadBrandingData = useCallback(async () => {
    setIsLoading(true);
    setActionError(null);
    try {
      const profiles = await brandingApi.getProfiles(organizationId);
      let targetProfile = profiles[0] || null;

      if (!targetProfile && !organizationId) {
        // If owner global profiles list
        targetProfile = profiles.find((p) => p.is_global) || profiles[0] || null;
      }

      if (targetProfile) {
        setProfile(targetProfile);
        const revs = await brandingApi.getRevisions(targetProfile.id);
        setRevisions(revs);

        // Prepopulate editor tokens from draft or active revision
        const currentRev = revs.find((r) => r.status === "draft") || targetProfile.active_revision || revs[0];
        if (currentRev?.tokens) {
          setEditorTokens((prev) => ({
            ...prev,
            ...currentRev.tokens,
          }));
          setSelectedLogoId(currentRev.logo_asset?.id || null);
          setSelectedFaviconId(currentRev.favicon_asset?.id || null);
          setActiveAssetPreview({
            logo: currentRev.logo_asset?.file_data,
            favicon: currentRev.favicon_asset?.file_data,
          });
        }
      }
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : "Failed to load branding profile";
      setActionError(msg);
    } finally {
      setIsLoading(false);
    }
  }, [organizationId]);

  useEffect(() => {
    loadBrandingData();
  }, [loadBrandingData]);

  // Apply preview tokens to CSS variables within a preview container
  const previewStyles = useMemo(() => {
    return {
      "--brand-primary": editorTokens.brand_primary,
      "--brand-primary-hover": editorTokens.brand_primary_hover,
      "--brand-primary-light": editorTokens.brand_primary_light,
      "--brand-gradient": editorTokens.brand_gradient,
      "--bg-app": editorTokens.bg_app,
      "--text-primary": editorTokens.text_primary,
      "--text-secondary": editorTokens.text_secondary,
      "--border-focus": editorTokens.border_focus,
    } as React.CSSProperties;
  }, [editorTokens]);

  const handleTokenChange = (key: string, value: string) => {
    setEditorTokens((prev) => ({ ...prev, [key]: value }));
  };

  const handleSaveDraft = async () => {
    if (!profile) return;
    setIsSaving(true);
    setActionError(null);
    setActionSuccess(null);
    try {
      const payload: SaveDraftPayload = {
        tokens: editorTokens,
        logo_asset_id: selectedLogoId,
        favicon_asset_id: selectedFaviconId,
        change_summary: changeSummary || "Draft update",
      };
      const saved = await brandingApi.saveDraft(profile.id, payload);
      setActionSuccess(`Draft revision #${saved.revision_number} saved.`);
      setChangeSummary("");
      await loadBrandingData();
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : "Failed to save draft";
      setActionError(msg);
    } finally {
      setIsSaving(false);
    }
  };

  const handlePublish = async (revisionId: string) => {
    setIsSaving(true);
    setActionError(null);
    setActionSuccess(null);
    try {
      const published = await brandingApi.publishRevision(revisionId);
      setActionSuccess(`Revision #${published.revision_number} published successfully.`);
      // Apply tokens globally to documentElement
      if (published.tokens) {
        Object.entries(published.tokens).forEach(([k, v]) => {
          document.documentElement.style.setProperty(`--${k.replace(/_/g, "-")}`, v);
        });
      }
      await loadBrandingData();
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : "Failed to publish revision";
      setActionError(msg);
    } finally {
      setIsSaving(false);
    }
  };

  const handleRollback = async (revisionId: string) => {
    setIsSaving(true);
    setActionError(null);
    setActionSuccess(null);
    try {
      const rolledBack = await brandingApi.rollbackRevision(revisionId);
      setActionSuccess(
        `Rollback created new published revision #${rolledBack.revision_number} from target revision.`
      );
      if (rolledBack.tokens) {
        Object.entries(rolledBack.tokens).forEach(([k, v]) => {
          document.documentElement.style.setProperty(`--${k.replace(/_/g, "-")}`, v);
        });
      }
      await loadBrandingData();
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : "Failed to rollback revision";
      setActionError(msg);
    } finally {
      setIsSaving(false);
    }
  };

  const handleLoadRevisionToPreview = (rev: BrandingRevision) => {
    if (rev.tokens) {
      setEditorTokens((prev) => ({ ...prev, ...rev.tokens }));
    }
    if (rev.logo_asset) {
      setSelectedLogoId(rev.logo_asset.id);
      setActiveAssetPreview((prev) => ({ ...prev, logo: rev.logo_asset?.file_data }));
    }
    if (rev.favicon_asset) {
      setSelectedFaviconId(rev.favicon_asset.id);
      setActiveAssetPreview((prev) => ({ ...prev, favicon: rev.favicon_asset?.file_data }));
    }
    setActionSuccess(`Loaded revision #${rev.revision_number} into live preview.`);
  };

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>, assetType: "logo" | "favicon") => {
    if (!profile || !e.target.files || e.target.files.length === 0) return;
    const file = e.target.files[0];
    const reader = new FileReader();

    reader.onload = async () => {
      const base64Data = reader.result as string;
      try {
        setIsSaving(true);
        setActionError(null);
        const asset = await brandingApi.uploadAsset(profile.id, {
          asset_type: assetType,
          file_name: file.name,
          content_type: file.type || (file.name.endsWith(".svg") ? "image/svg+xml" : "image/png"),
          file_data: base64Data,
        });

        if (assetType === "logo") {
          setSelectedLogoId(asset.id);
          setActiveAssetPreview((prev) => ({ ...prev, logo: asset.file_data }));
        } else {
          setSelectedFaviconId(asset.id);
          setActiveAssetPreview((prev) => ({ ...prev, favicon: asset.file_data }));
        }
        setActionSuccess(`Uploaded ${assetType} (${asset.file_name}) successfully.`);
      } catch (err) {
        const msg = err instanceof ApiError ? err.message : `Failed to upload ${assetType}`;
        setActionError(msg);
      } finally {
        setIsSaving(false);
      }
    };

    reader.readAsDataURL(file);
  };

  return (
    <div className="branding-workspace-container" style={{ padding: "2rem", maxWidth: "1400px", margin: "0 auto" }}>
      {/* Header */}
      <div style={{ marginBottom: "2rem" }}>
        <h1 style={{ fontSize: "1.75rem", fontWeight: 700, color: "var(--text-primary)", margin: 0 }}>
          {title}
        </h1>
        <p style={{ color: "var(--text-secondary)", fontSize: "0.9375rem", marginTop: "0.5rem" }}>
          {subtitle} {organizationName ? `(${organizationName})` : ""}
        </p>

        {/* Status Pills */}
        <div style={{ display: "flex", gap: "1rem", marginTop: "1rem", alignItems: "center" }}>
          <span
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: "0.375rem",
              padding: "0.25rem 0.75rem",
              borderRadius: "9999px",
              fontSize: "0.8125rem",
              fontWeight: 600,
              background: profile?.is_global ? "rgba(99, 102, 241, 0.15)" : "rgba(16, 185, 129, 0.15)",
              color: profile?.is_global ? "var(--brand-primary)" : "var(--status-success)",
              border: "1px solid var(--border-subtle)",
            }}
          >
            <ShieldCheckIcon size={14} />
            {profile?.is_global ? "Global Brand Profile" : "Tenant Organization Profile"}
          </span>

          <span
            style={{
              padding: "0.25rem 0.625rem",
              borderRadius: "9999px",
              fontSize: "0.75rem",
              fontWeight: 500,
              background: "var(--glass-surface-elevated)",
              color: "var(--text-secondary)",
              border: "1px solid var(--border-glass)",
            }}
          >
            {isOwner ? "Owner Master Controls" : "Tenant Admin View"}
          </span>

          {isLoading ? (
            <span style={{ fontSize: "0.8125rem", color: "var(--text-muted)" }}>Loading profile...</span>
          ) : profile?.active_revision ? (
            <span style={{ fontSize: "0.8125rem", color: "var(--text-secondary)" }}>
              Active Published Revision: <strong>#{profile.active_revision.revision_number}</strong>
            </span>
          ) : (
            <span style={{ fontSize: "0.8125rem", color: "var(--status-warning)" }}>
              No published revision — Falling back to Global Default
            </span>
          )}
        </div>
      </div>

      {/* Notifications */}
      {actionError && (
        <div
          role="alert"
          style={{
            padding: "0.875rem 1.25rem",
            marginBottom: "1.5rem",
            borderRadius: "8px",
            background: "var(--status-danger-bg)",
            border: "1px solid var(--status-danger-border)",
            color: "var(--status-danger)",
            display: "flex",
            alignItems: "center",
            gap: "0.75rem",
          }}
        >
          <AlertCircleIcon size={18} />
          <span>{actionError}</span>
        </div>
      )}

      {actionSuccess && (
        <div
          role="status"
          style={{
            padding: "0.875rem 1.25rem",
            marginBottom: "1.5rem",
            borderRadius: "8px",
            background: "var(--status-success-bg)",
            border: "1px solid var(--status-success-border)",
            color: "var(--status-success)",
            display: "flex",
            alignItems: "center",
            gap: "0.75rem",
          }}
        >
          <CheckCircleIcon size={18} />
          <span>{actionSuccess}</span>
        </div>
      )}

      {/* Workspace Grid */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "2rem" }}>
        {/* Left Column: Theme Editor & Assets */}
        <div style={{ display: "flex", flexDirection: "column", gap: "2rem" }}>
          {/* Token Editor Card */}
          <div
            style={{
              padding: "1.5rem",
              borderRadius: "12px",
              background: "var(--glass-surface)",
              border: "1px solid var(--border-glass)",
            }}
          >
            <h2 style={{ fontSize: "1.125rem", fontWeight: 600, color: "var(--text-primary)", marginBottom: "1rem" }}>
              CSS Custom Property Tokens
            </h2>
            <p style={{ fontSize: "0.8125rem", color: "var(--text-secondary)", marginBottom: "1.5rem" }}>
              Customizations conform strictly to the allowlisted token schema.
            </p>

            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem" }}>
              {ALLOWLISTED_TOKENS.map((token) => (
                <div key={token.key} style={{ display: "flex", flexDirection: "column", gap: "0.375rem" }}>
                  <label
                    htmlFor={`token-${token.key}`}
                    style={{ fontSize: "0.8125rem", fontWeight: 500, color: "var(--text-secondary)" }}
                  >
                    {token.label}
                  </label>
                  <div style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
                    {token.type === "color" && (
                      <input
                        type="color"
                        value={editorTokens[token.key]?.startsWith("#") ? editorTokens[token.key] : "#6366f1"}
                        onChange={(e) => handleTokenChange(token.key, e.target.value)}
                        style={{
                          width: "36px",
                          height: "36px",
                          padding: "2px",
                          borderRadius: "6px",
                          border: "1px solid var(--border-glass)",
                          cursor: "pointer",
                          background: "transparent",
                        }}
                      />
                    )}
                    <input
                      id={`token-${token.key}`}
                      type="text"
                      value={editorTokens[token.key] || ""}
                      onChange={(e) => handleTokenChange(token.key, e.target.value)}
                      style={{
                        flex: 1,
                        padding: "0.5rem 0.75rem",
                        fontSize: "0.875rem",
                        borderRadius: "6px",
                        border: "1px solid var(--border-glass)",
                        background: "var(--glass-surface-sunken)",
                        color: "var(--text-primary)",
                      }}
                    />
                  </div>
                </div>
              ))}
            </div>

            {/* Change Summary & Save Draft */}
            <div style={{ marginTop: "1.5rem", borderTop: "1px solid var(--border-glass)", paddingTop: "1.25rem" }}>
              <label
                htmlFor="change-summary"
                style={{ display: "block", fontSize: "0.8125rem", fontWeight: 500, color: "var(--text-secondary)", marginBottom: "0.5rem" }}
              >
                Change Summary
              </label>
              <input
                id="change-summary"
                type="text"
                placeholder="e.g. Modernized primary gradient and focus ring"
                value={changeSummary}
                onChange={(e) => setChangeSummary(e.target.value)}
                style={{
                  width: "100%",
                  padding: "0.5rem 0.75rem",
                  fontSize: "0.875rem",
                  borderRadius: "6px",
                  border: "1px solid var(--border-glass)",
                  background: "var(--glass-surface-sunken)",
                  color: "var(--text-primary)",
                  marginBottom: "1rem",
                  boxSizing: "border-box",
                }}
              />

              <div style={{ display: "flex", gap: "1rem" }}>
                <button
                  type="button"
                  id="btn-save-draft"
                  onClick={handleSaveDraft}
                  disabled={isSaving || !profile}
                  style={{
                    padding: "0.625rem 1.25rem",
                    borderRadius: "8px",
                    fontWeight: 600,
                    fontSize: "0.875rem",
                    background: "var(--brand-primary)",
                    color: "#ffffff",
                    border: "none",
                    cursor: isSaving ? "not-allowed" : "pointer",
                    display: "inline-flex",
                    alignItems: "center",
                    gap: "0.5rem",
                  }}
                >
                  <LayersIcon size={16} />
                  {isSaving ? "Saving..." : "Save Draft"}
                </button>

                {draftRevision && (
                  <button
                    type="button"
                    id="btn-publish-draft"
                    onClick={() => handlePublish(draftRevision.id)}
                    disabled={isSaving}
                    style={{
                      padding: "0.625rem 1.25rem",
                      borderRadius: "8px",
                      fontWeight: 600,
                      fontSize: "0.875rem",
                      background: "var(--status-success)",
                      color: "#ffffff",
                      border: "none",
                      cursor: isSaving ? "not-allowed" : "pointer",
                      display: "inline-flex",
                      alignItems: "center",
                      gap: "0.5rem",
                    }}
                  >
                    <ShieldCheckIcon size={16} />
                    Publish Draft (Rev #{draftRevision.revision_number})
                  </button>
                )}
              </div>
            </div>
          </div>

          {/* Asset Manager Card */}
          <div
            style={{
              padding: "1.5rem",
              borderRadius: "12px",
              background: "var(--glass-surface)",
              border: "1px solid var(--border-glass)",
            }}
          >
            <h2 style={{ fontSize: "1.125rem", fontWeight: 600, color: "var(--text-primary)", marginBottom: "1rem" }}>
              Brand Assets
            </h2>
            <p style={{ fontSize: "0.8125rem", color: "var(--text-secondary)", marginBottom: "1.5rem" }}>
              Upload logo (max 2MB) and favicon (max 500KB). Formats: PNG, JPEG, WebP, SVG.
            </p>

            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1.5rem" }}>
              {/* Logo Upload */}
              <div style={{ border: "1px dashed var(--border-glass)", borderRadius: "8px", padding: "1rem", textAlign: "center" }}>
                <span style={{ fontSize: "0.875rem", fontWeight: 600, color: "var(--text-primary)", display: "block", marginBottom: "0.5rem" }}>
                  Brand Logo
                </span>
                {activeAssetPreview.logo ? (
                  <div style={{ marginBottom: "0.75rem" }}>
                    <img
                      src={activeAssetPreview.logo}
                      alt="Brand Logo Preview"
                      style={{ maxHeight: "48px", maxWidth: "100%", objectFit: "contain" }}
                    />
                  </div>
                ) : (
                  <div style={{ color: "var(--text-muted)", fontSize: "0.75rem", marginBottom: "0.75rem" }}>
                    No custom logo uploaded
                  </div>
                )}
                <label
                  htmlFor="upload-logo"
                  style={{
                    display: "inline-flex",
                    alignItems: "center",
                    gap: "0.375rem",
                    padding: "0.375rem 0.75rem",
                    borderRadius: "6px",
                    background: "var(--glass-surface-elevated)",
                    color: "var(--text-primary)",
                    fontSize: "0.75rem",
                    cursor: "pointer",
                    border: "1px solid var(--border-glass)",
                  }}
                >
                  <UploadIcon size={14} />
                  Choose Logo
                </label>
                <input
                  id="upload-logo"
                  type="file"
                  accept="image/png,image/jpeg,image/webp,image/svg+xml"
                  onChange={(e) => handleFileUpload(e, "logo")}
                  style={{ display: "none" }}
                />
              </div>

              {/* Favicon Upload */}
              <div style={{ border: "1px dashed var(--border-glass)", borderRadius: "8px", padding: "1rem", textAlign: "center" }}>
                <span style={{ fontSize: "0.875rem", fontWeight: 600, color: "var(--text-primary)", display: "block", marginBottom: "0.5rem" }}>
                  Brand Favicon
                </span>
                {activeAssetPreview.favicon ? (
                  <div style={{ marginBottom: "0.75rem" }}>
                    <img
                      src={activeAssetPreview.favicon}
                      alt="Brand Favicon Preview"
                      style={{ maxHeight: "32px", maxWidth: "32px", objectFit: "contain" }}
                    />
                  </div>
                ) : (
                  <div style={{ color: "var(--text-muted)", fontSize: "0.75rem", marginBottom: "0.75rem" }}>
                    No custom favicon uploaded
                  </div>
                )}
                <label
                  htmlFor="upload-favicon"
                  style={{
                    display: "inline-flex",
                    alignItems: "center",
                    gap: "0.375rem",
                    padding: "0.375rem 0.75rem",
                    borderRadius: "6px",
                    background: "var(--glass-surface-elevated)",
                    color: "var(--text-primary)",
                    fontSize: "0.75rem",
                    cursor: "pointer",
                    border: "1px solid var(--border-glass)",
                  }}
                >
                  <UploadIcon size={14} />
                  Choose Favicon
                </label>
                <input
                  id="upload-favicon"
                  type="file"
                  accept="image/png,image/x-icon,image/svg+xml"
                  onChange={(e) => handleFileUpload(e, "favicon")}
                  style={{ display: "none" }}
                />
              </div>
            </div>
          </div>
        </div>

        {/* Right Column: Live Preview & Revision History */}
        <div style={{ display: "flex", flexDirection: "column", gap: "2rem" }}>
          {/* Live Preview Card */}
          <div
            style={{
              padding: "1.5rem",
              borderRadius: "12px",
              background: "var(--glass-surface)",
              border: "1px solid var(--border-glass)",
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1rem" }}>
              <h2 style={{ fontSize: "1.125rem", fontWeight: 600, color: "var(--text-primary)", margin: 0 }}>
                Live Refractive Preview
              </h2>
              <span style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>Simulated LMS Surface</span>
            </div>

            {/* Scoped CSS Token Container */}
            <div
              className="preview-viewport"
              style={{
                ...previewStyles,
                background: "var(--bg-app)",
                padding: "1.5rem",
                borderRadius: "10px",
                border: "2px solid var(--border-focus)",
                transition: "all 0.2s ease-in-out",
              }}
            >
              {/* Header Preview */}
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  paddingBottom: "1rem",
                  borderBottom: "1px solid rgba(255, 255, 255, 0.1)",
                  marginBottom: "1.25rem",
                }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
                  {activeAssetPreview.logo ? (
                    <img
                      src={activeAssetPreview.logo}
                      alt="Brand Logo"
                      style={{ maxHeight: "32px", maxWidth: "120px", objectFit: "contain" }}
                    />
                  ) : (
                    <div
                      style={{
                        padding: "0.5rem 0.75rem",
                        borderRadius: "8px",
                        background: "var(--brand-gradient)",
                        color: "#ffffff",
                        fontWeight: 700,
                        fontSize: "0.875rem",
                      }}
                    >
                      EN
                    </div>
                  )}
                  <span style={{ fontWeight: 700, color: "var(--text-primary)", fontSize: "1rem" }}>
                    Envisage
                  </span>
                </div>
                <div style={{ display: "flex", gap: "0.5rem" }}>
                  <button
                    type="button"
                    style={{
                      padding: "0.375rem 0.75rem",
                      borderRadius: "6px",
                      background: "var(--brand-primary)",
                      color: "#ffffff",
                      fontSize: "0.75rem",
                      fontWeight: 600,
                      border: "none",
                    }}
                  >
                    Action Button
                  </button>
                </div>
              </div>

              {/* Sample Card */}
              <div
                style={{
                  padding: "1rem",
                  borderRadius: "8px",
                  background: "rgba(255, 255, 255, 0.05)",
                  border: "1px solid rgba(255, 255, 255, 0.1)",
                }}
              >
                <span
                  style={{
                    display: "inline-block",
                    padding: "0.25rem 0.5rem",
                    borderRadius: "4px",
                    background: "var(--brand-primary-light)",
                    color: "var(--brand-primary)",
                    fontSize: "0.75rem",
                    fontWeight: 600,
                    marginBottom: "0.5rem",
                  }}
                >
                  Featured Badge
                </span>
                <h4 style={{ margin: "0 0 0.5rem 0", color: "var(--text-primary)", fontSize: "0.9375rem" }}>
                  Theming & Personalization Engine
                </h4>
                <p style={{ margin: 0, color: "var(--text-secondary)", fontSize: "0.8125rem", lineHeight: 1.5 }}>
                  Allowlisted custom properties dynamically update the learning experience while preserving tenant
                  isolation and visual harmony.
                </p>
              </div>
            </div>
          </div>

          {/* Revision History & Lifecycle */}
          <div
            style={{
              padding: "1.5rem",
              borderRadius: "12px",
              background: "var(--glass-surface)",
              border: "1px solid var(--border-glass)",
            }}
          >
            <h2 style={{ fontSize: "1.125rem", fontWeight: 600, color: "var(--text-primary)", marginBottom: "1rem" }}>
              Revision History & Rollback
            </h2>
            <p style={{ fontSize: "0.8125rem", color: "var(--text-secondary)", marginBottom: "1rem" }}>
              Published revisions are immutable. Rollbacks create a new published revision copy.
            </p>

            <div style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.8125rem" }}>
                <thead>
                  <tr style={{ borderBottom: "1px solid var(--border-glass)", color: "var(--text-secondary)", textAlign: "left" }}>
                    <th style={{ padding: "0.75rem 0.5rem" }}>Rev #</th>
                    <th style={{ padding: "0.75rem 0.5rem" }}>Status</th>
                    <th style={{ padding: "0.75rem 0.5rem" }}>Summary</th>
                    <th style={{ padding: "0.75rem 0.5rem" }}>Published</th>
                    <th style={{ padding: "0.75rem 0.5rem", textAlign: "right" }}>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {revisions.map((rev) => (
                    <tr key={rev.id} style={{ borderBottom: "1px solid var(--border-subtle)" }}>
                      <td style={{ padding: "0.75rem 0.5rem", fontWeight: 600, color: "var(--text-primary)" }}>
                        #{rev.revision_number}
                      </td>
                      <td style={{ padding: "0.75rem 0.5rem" }}>
                        <span
                          style={{
                            padding: "0.2rem 0.5rem",
                            borderRadius: "4px",
                            fontSize: "0.75rem",
                            fontWeight: 600,
                            background:
                              rev.status === "published"
                                ? "rgba(16, 185, 129, 0.15)"
                                : rev.status === "draft"
                                ? "rgba(245, 158, 11, 0.15)"
                                : "rgba(148, 163, 184, 0.15)",
                            color:
                              rev.status === "published"
                                ? "var(--status-success)"
                                : rev.status === "draft"
                                ? "var(--status-warning)"
                                : "var(--text-muted)",
                          }}
                        >
                          {rev.status.toUpperCase()}
                        </span>
                      </td>
                      <td style={{ padding: "0.75rem 0.5rem", color: "var(--text-secondary)", maxWidth: "180px", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                        {rev.change_summary || "—"}
                      </td>
                      <td style={{ padding: "0.75rem 0.5rem", color: "var(--text-muted)" }}>
                        {rev.published_at ? new Date(rev.published_at).toLocaleDateString() : "—"}
                      </td>
                      <td style={{ padding: "0.75rem 0.5rem", textAlign: "right" }}>
                        <div style={{ display: "inline-flex", gap: "0.5rem", justifyContent: "flex-end" }}>
                          <button
                            type="button"
                            title="Preview Revision"
                            onClick={() => handleLoadRevisionToPreview(rev)}
                            style={{
                              padding: "0.3rem 0.5rem",
                              borderRadius: "4px",
                              background: "transparent",
                              border: "1px solid var(--border-glass)",
                              color: "var(--text-primary)",
                              cursor: "pointer",
                            }}
                          >
                            <EyeIcon size={14} />
                          </button>

                          {rev.status === "draft" && (
                            <button
                              type="button"
                              id={`btn-publish-${rev.revision_number}`}
                              onClick={() => handlePublish(rev.id)}
                              disabled={isSaving}
                              style={{
                                padding: "0.3rem 0.6rem",
                                borderRadius: "4px",
                                background: "var(--status-success)",
                                color: "#ffffff",
                                border: "none",
                                cursor: "pointer",
                                fontSize: "0.75rem",
                                fontWeight: 600,
                              }}
                            >
                              Publish
                            </button>
                          )}

                          {rev.status !== "draft" && (
                            <button
                              type="button"
                              id={`btn-rollback-${rev.revision_number}`}
                              onClick={() => handleRollback(rev.id)}
                              disabled={isSaving}
                              style={{
                                padding: "0.3rem 0.6rem",
                                borderRadius: "4px",
                                background: "var(--glass-surface-elevated)",
                                border: "1px solid var(--border-glass)",
                                color: "var(--text-primary)",
                                cursor: "pointer",
                                fontSize: "0.75rem",
                                display: "inline-flex",
                                alignItems: "center",
                                gap: "0.25rem",
                              }}
                            >
                              <RotateCcwIcon size={12} />
                              Rollback
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))}
                  {revisions.length === 0 && (
                    <tr>
                      <td colSpan={5} style={{ textAlign: "center", padding: "2rem", color: "var(--text-muted)" }}>
                        No revisions found. Save a draft to create your first revision.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
