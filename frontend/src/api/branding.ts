/**
 * Branding API Client Module (Phase 4A/4B).
 * Exclusively consumes centralized apiClient and ENDPOINTS.
 */

import { apiClient } from "./client.ts";
import { ENDPOINTS } from "./endpoints.ts";

export interface BrandAsset {
  id: string;
  profile: string;
  asset_type: "logo" | "favicon";
  file_name: string;
  content_type: string;
  file_size_bytes: number;
  file_data?: string;
  is_active: boolean;
  created_at: string;
}

export interface BrandingRevision {
  id: string;
  profile: string;
  revision_number: number;
  status: "draft" | "published" | "archived";
  tokens: Record<string, string>;
  logo_asset: BrandAsset | null;
  favicon_asset: BrandAsset | null;
  logo_asset_id?: string;
  favicon_asset_id?: string;
  published_at: string | null;
  published_by: string | null;
  change_summary: string;
  created_at: string;
  updated_at: string;
}

export interface BrandingProfile {
  id: string;
  organization: string | null;
  organization_name?: string | null;
  is_global: boolean;
  is_active: boolean;
  active_revision: BrandingRevision | null;
  active_revision_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface ActiveBrandingResponse {
  source: "tenant" | "global" | "default";
  profile_id: string | null;
  revision_id: string | null;
  tokens: Record<string, string>;
  logo_asset: BrandAsset | null;
  favicon_asset: BrandAsset | null;
}

export interface SaveDraftPayload {
  tokens?: Record<string, string>;
  logo_asset_id?: string | null;
  favicon_asset_id?: string | null;
  change_summary?: string;
}

export interface UploadAssetPayload {
  asset_type: "logo" | "favicon";
  file_name: string;
  content_type: string;
  file_data: string;
}

export const brandingApi = {
  getActiveBranding(organizationId?: string, signal?: AbortSignal) {
    const params = organizationId ? { organization_id: organizationId } : undefined;
    return apiClient.get<ActiveBrandingResponse>(ENDPOINTS.BRANDING.ACTIVE, { params, signal });
  },

  getProfiles(organizationId?: string, signal?: AbortSignal) {
    const params = organizationId ? { organization_id: organizationId } : undefined;
    return apiClient.get<BrandingProfile[]>(ENDPOINTS.BRANDING.PROFILES, { params, signal });
  },

  getProfile(profileId: string, signal?: AbortSignal) {
    return apiClient.get<BrandingProfile>(ENDPOINTS.BRANDING.PROFILE_DETAIL(profileId), { signal });
  },

  getRevisions(profileId: string, signal?: AbortSignal) {
    return apiClient.get<BrandingRevision[]>(ENDPOINTS.BRANDING.REVISIONS(profileId), { signal });
  },

  saveDraft(profileId: string, payload: SaveDraftPayload) {
    return apiClient.post<BrandingRevision>(ENDPOINTS.BRANDING.REVISIONS(profileId), payload);
  },

  updateRevision(revisionId: string, payload: SaveDraftPayload) {
    return apiClient.patch<BrandingRevision>(ENDPOINTS.BRANDING.REVISION_DETAIL(revisionId), payload);
  },

  publishRevision(revisionId: string) {
    return apiClient.post<BrandingRevision>(ENDPOINTS.BRANDING.PUBLISH(revisionId), {});
  },

  rollbackRevision(revisionId: string) {
    return apiClient.post<BrandingRevision>(ENDPOINTS.BRANDING.ROLLBACK(revisionId), {});
  },

  getPreview(revisionId: string, signal?: AbortSignal) {
    return apiClient.get<{ revision_id: string; status: string; tokens: Record<string, string>; logo_asset: BrandAsset | null; favicon_asset: BrandAsset | null }>(
      ENDPOINTS.BRANDING.PREVIEW(revisionId),
      { signal }
    );
  },

  uploadAsset(profileId: string, payload: UploadAssetPayload) {
    return apiClient.post<BrandAsset>(ENDPOINTS.BRANDING.ASSETS(profileId), payload);
  },
};
