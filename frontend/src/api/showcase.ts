/**
 * Product Showcase Domain API – Phase 11.
 *
 * Consumes only the centralized apiClient and ENDPOINTS.
 */
import { apiClient } from "./client.ts";
import { ENDPOINTS } from "./endpoints.ts";
import type {
  CreateShowcaseProfilePayload,
  DemoEnvironment,
  HrmsAttendanceHistoryResponse,
  HrmsAttendanceResponse,
  HrmsDepartmentListResponse,
  HrmsEmployeeListResponse,
  HrmsHealthStatus,
  HrmsLeavesSummaryResponse,
  HrmsOrgStructureResponse,
  HrmsOverviewResponse,
  LaunchabilityContract,
  ReorderPayload,
  ShowcaseDemoLaunchResponse,
  ShowcaseLaunchConfig,
  ShowcaseProfile,
  ShowcaseProfileListResponse,
  UpdateShowcaseProfilePayload,
  VmsDocksResponse,
  VmsHealthStatus,
  VmsInventoryStockResponse,
  VmsOverviewResponse,
  VmsReportsSummary,
  VmsVehiclesResponse,
  VmsWavesResponse,
} from "./types.ts";

export interface ShowcaseListParams {
  readonly page?: number;
  readonly page_size?: number;
  readonly search?: string;
  readonly visibility?: string;
}

export const showcaseApi = {
  /** List showcase profiles with optional search/visibility filter. */
  async listProfiles(params?: ShowcaseListParams, signal?: AbortSignal): Promise<ShowcaseProfileListResponse> {
    return apiClient.get<ShowcaseProfileListResponse>(ENDPOINTS.SHOWCASE.PROFILES, { params, signal });
  },

  /** Get a single showcase profile by ID. */
  async getProfile(id: string): Promise<ShowcaseProfile> {
    return apiClient.get<ShowcaseProfile>(ENDPOINTS.SHOWCASE.PROFILE_DETAIL(id));
  },

  /** Create a new showcase profile. */
  async createProfile(payload: CreateShowcaseProfilePayload): Promise<ShowcaseProfile> {
    return apiClient.post<ShowcaseProfile>(ENDPOINTS.SHOWCASE.PROFILES, payload);
  },

  /** Partially update a showcase profile. */
  async updateProfile(id: string, payload: UpdateShowcaseProfilePayload): Promise<ShowcaseProfile> {
    return apiClient.patch<ShowcaseProfile>(ENDPOINTS.SHOWCASE.PROFILE_DETAIL(id), payload);
  },

  /** Publish a showcase profile. */
  async publishProfile(id: string): Promise<ShowcaseProfile> {
    return apiClient.post<ShowcaseProfile>(ENDPOINTS.SHOWCASE.PUBLISH(id), {});
  },

  /** Unpublish a showcase profile. */
  async unpublishProfile(id: string): Promise<ShowcaseProfile> {
    return apiClient.post<ShowcaseProfile>(ENDPOINTS.SHOWCASE.UNPUBLISH(id), {});
  },

  /** Reorder profiles. */
  async reorderProfiles(payload: ReorderPayload): Promise<void> {
    await apiClient.post<{ detail: string }>(ENDPOINTS.SHOWCASE.REORDER, payload);
  },

  /** Get launchability contract for a profile. */
  async getLaunchability(id: string): Promise<LaunchabilityContract> {
    return apiClient.get<LaunchabilityContract>(ENDPOINTS.SHOWCASE.LAUNCHABILITY(id));
  },

  /** Add media to a profile. */
  async addMedia(profileId: string, payload: object): Promise<unknown> {
    return apiClient.post<unknown>(ENDPOINTS.SHOWCASE.MEDIA(profileId), payload);
  },

  /** Delete a media item. */
  async deleteMedia(mediaId: string): Promise<void> {
    await apiClient.delete<void>(ENDPOINTS.SHOWCASE.MEDIA_DELETE(mediaId));
  },

  /** List demo environments for a product. */
  async listDemoEnvironments(productId: string): Promise<readonly DemoEnvironment[]> {
    return apiClient.get<readonly DemoEnvironment[]>(ENDPOINTS.SHOWCASE.DEMO_ENVS(productId));
  },

  /** Create demo environment. */
  async createDemoEnvironment(productId: string, payload: object): Promise<DemoEnvironment> {
    return apiClient.post<DemoEnvironment>(ENDPOINTS.SHOWCASE.DEMO_ENVS(productId), payload);
  },

  /** Update demo environment. */
  async updateDemoEnvironment(envId: string, payload: object): Promise<DemoEnvironment> {
    return apiClient.patch<DemoEnvironment>(ENDPOINTS.SHOWCASE.DEMO_ENV_DETAIL(envId), payload);
  },

  /** Delete demo environment. */
  async deleteDemoEnvironment(envId: string): Promise<void> {
    await apiClient.delete<void>(ENDPOINTS.SHOWCASE.DEMO_ENV_DETAIL(envId));
  },

  /** Presentation mode portfolio (published only). */
  async getPresentation(params?: { category?: string }, signal?: AbortSignal): Promise<readonly ShowcaseProfile[]> {
    return apiClient.get<readonly ShowcaseProfile[]>(ENDPOINTS.SHOWCASE.PRESENT, { params, signal });
  },

  /** Get launch config for a profile's product. */
  async getLaunchConfig(profileId: string): Promise<ShowcaseLaunchConfig> {
    return apiClient.get<ShowcaseLaunchConfig>(ENDPOINTS.SHOWCASE.LAUNCH_CONFIG(profileId));
  },

  /** Update launch config for a profile's product. */
  async updateLaunchConfig(profileId: string, payload: Partial<ShowcaseLaunchConfig>): Promise<ShowcaseLaunchConfig> {
    return apiClient.patch<ShowcaseLaunchConfig>(ENDPOINTS.SHOWCASE.LAUNCH_CONFIG(profileId), payload);
  },

  /** Launch demo environment for a profile via authorized Showcase SSO. */
  async launchDemo(profileId: string): Promise<ShowcaseDemoLaunchResponse> {
    return apiClient.post<ShowcaseDemoLaunchResponse>(ENDPOINTS.SHOWCASE.LAUNCH_DEMO(profileId), {});
  },

  /** HRMS Live Sandbox demonstration endpoints */
  hrms: {
    /** Probe health of upstream HRMS sandbox */
    async getHealth(): Promise<HrmsHealthStatus> {
      return apiClient.get<HrmsHealthStatus>(ENDPOINTS.SHOWCASE.HRMS_HEALTH);
    },

    /** Fetch HRMS demonstration overview metrics */
    async getOverview(): Promise<HrmsOverviewResponse> {
      return apiClient.get<HrmsOverviewResponse>(ENDPOINTS.SHOWCASE.HRMS_OVERVIEW);
    },

    /** Fetch sanitized and paginated employee list */
    async getEmployees(params?: {
      department?: string;
      search?: string;
      page?: number;
      page_size?: number;
    }): Promise<HrmsEmployeeListResponse> {
      return apiClient.get<HrmsEmployeeListResponse>(ENDPOINTS.SHOWCASE.HRMS_EMPLOYEES, { params });
    },

    /** Fetch today's attendance summary and punch feed */
    async getAttendance(): Promise<HrmsAttendanceResponse> {
      return apiClient.get<HrmsAttendanceResponse>(ENDPOINTS.SHOWCASE.HRMS_ATTENDANCE);
    },

    /** Fetch organization department list for UI filtering */
    async getDepartments(): Promise<HrmsDepartmentListResponse> {
      return apiClient.get<HrmsDepartmentListResponse>(ENDPOINTS.SHOWCASE.HRMS_DEPARTMENTS);
    },

    /** Fetch historical attendance punch telemetry */
    async getAttendanceHistory(params?: {
      limit?: number;
      search?: string;
    }): Promise<HrmsAttendanceHistoryResponse> {
      return apiClient.get<HrmsAttendanceHistoryResponse>(ENDPOINTS.SHOWCASE.HRMS_ATTENDANCE_HISTORY, { params });
    },

    /** Fetch organizational structure (departments, designations, sites) */
    async getOrgStructure(): Promise<HrmsOrgStructureResponse> {
      return apiClient.get<HrmsOrgStructureResponse>(ENDPOINTS.SHOWCASE.HRMS_ORG_STRUCTURE);
    },

    /** Fetch leave approval status metrics */
    async getLeavesSummary(): Promise<HrmsLeavesSummaryResponse> {
      return apiClient.get<HrmsLeavesSummaryResponse>(ENDPOINTS.SHOWCASE.HRMS_LEAVES_SUMMARY);
    },
  },

  /** VMS (WarehouseOS) Live Sandbox demonstration endpoints */
  vms: {
    /** Probe health of upstream VMS sandbox */
    async getHealth(): Promise<VmsHealthStatus> {
      return apiClient.get<VmsHealthStatus>(ENDPOINTS.SHOWCASE.VMS_HEALTH);
    },

    /** Fetch VMS demonstration overview metrics and KPIs */
    async getOverview(): Promise<VmsOverviewResponse> {
      return apiClient.get<VmsOverviewResponse>(ENDPOINTS.SHOWCASE.VMS_OVERVIEW);
    },

    /** Fetch real-time inventory stock statistics */
    async getInventory(): Promise<VmsInventoryStockResponse> {
      return apiClient.get<VmsInventoryStockResponse>(ENDPOINTS.SHOWCASE.VMS_INVENTORY);
    },

    /** Fetch active dock bays and allocations */
    async getDocks(): Promise<VmsDocksResponse> {
      return apiClient.get<VmsDocksResponse>(ENDPOINTS.SHOWCASE.VMS_DOCKS);
    },

    /** Fetch active fulfillment waves */
    async getWaves(): Promise<VmsWavesResponse> {
      return apiClient.get<VmsWavesResponse>(ENDPOINTS.SHOWCASE.VMS_WAVES);
    },

    /** Fetch gate vehicles and yard queue */
    async getVehicles(): Promise<VmsVehiclesResponse> {
      return apiClient.get<VmsVehiclesResponse>(ENDPOINTS.SHOWCASE.VMS_VEHICLES);
    },

    /** Fetch operational reports summary */
    async getReports(): Promise<VmsReportsSummary> {
      return apiClient.get<VmsReportsSummary>(ENDPOINTS.SHOWCASE.VMS_REPORTS);
    },
  },
};

