/**
 * User Invitations Domain API Client (Phase 3C).
 *
 * Exclusively consumes centralized apiClient and ENDPOINTS.
 */

import { apiClient } from "./client.ts";
import { ENDPOINTS } from "./endpoints.ts";
import type {
  AcceptInvitationPayload,
  AcceptInvitationResponse,
  InvitationValidateResponse,
  IssueInvitationPayload,
  IssueInvitationResponse,
} from "./types.ts";

export const invitationsApi = {
  /**
   * Issue a new user invitation.
   */
  async issue(payload: IssueInvitationPayload): Promise<IssueInvitationResponse> {
    return apiClient.post<IssueInvitationResponse>(ENDPOINTS.INVITATIONS.ISSUE, payload);
  },

  /**
   * Validate a single-use invitation token.
   */
  async validate(token: string, signal?: AbortSignal): Promise<InvitationValidateResponse> {
    return apiClient.get<InvitationValidateResponse>(ENDPOINTS.INVITATIONS.VALIDATE(token), { signal });
  },

  /**
   * Set password and accept the invitation.
   */
  async accept(token: string, payload: AcceptInvitationPayload): Promise<AcceptInvitationResponse> {
    return apiClient.post<AcceptInvitationResponse>(ENDPOINTS.INVITATIONS.ACCEPT(token), payload);
  },
};
