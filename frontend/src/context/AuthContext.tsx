/**
 * Authentication Context & Provider.
 *
 * In-memory authentication state lifecycle. Zero tokens in browser storage.
 * Authoritative authentication state committed solely after successful /me confirmation.
 */

import React, { createContext, useContext, useEffect, useState, useCallback } from "react";
import { apiClient, ApiError } from "../api/client.ts";
import type {
  AuthenticatedUser,
  ContextSelectionPayload,
  ContextSelectionResponse,
  LoginPayload,
} from "../api/types.ts";

export type AuthStatus = "loading" | "authenticated" | "unauthenticated" | "forbidden";

export interface AuthContextType {
  readonly user: AuthenticatedUser | null;
  readonly status: AuthStatus;
  readonly error: string | null;
  readonly login: (payload: LoginPayload) => Promise<AuthenticatedUser>;
  readonly logout: () => Promise<void>;
  readonly refreshUser: () => Promise<AuthenticatedUser | null>;
  readonly selectContext: (payload: ContextSelectionPayload) => Promise<ContextSelectionResponse | void>;
}

export const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<AuthenticatedUser | null>(null);
  const [status, setStatus] = useState<AuthStatus>("loading");
  const [error, setError] = useState<string | null>(null);

  const refreshUser = useCallback(async (): Promise<AuthenticatedUser | null> => {
    try {
      await apiClient.auth.initCsrf();
      const currentUser = await apiClient.auth.getCurrentUser();
      setUser(currentUser);
      setStatus("authenticated");
      setError(null);
      return currentUser;
    } catch (err: unknown) {
      setUser(null);
      if (err instanceof ApiError && err.status === 403) {
        setStatus("forbidden");
        const data = err.data as { code?: string; detail?: string } | undefined;
        setError(data?.detail || "Access restricted.");
      } else {
        setStatus("unauthenticated");
        setError(null);
      }
      return null;
    }
  }, []);

  useEffect(() => {
    void refreshUser();
  }, [refreshUser]);

  const login = useCallback(
    async (payload: LoginPayload): Promise<AuthenticatedUser> => {
      setError(null);
      try {
        await apiClient.auth.initCsrf();
        await apiClient.auth.login(payload);
        // Authoritative state confirmation from /me
        const confirmedUser = await apiClient.auth.getCurrentUser();
        setUser(confirmedUser);
        setStatus("authenticated");
        return confirmedUser;
      } catch (err: unknown) {
        setUser(null);
        if (err instanceof ApiError) {
          const data = err.data as { code?: string; detail?: string } | undefined;
          if (err.status === 401) {
            setStatus("unauthenticated");
            throw new Error(data?.detail || "Invalid credentials or unauthorized account.");
          }
          if (err.status === 403) {
            if (data?.code === "NO_CONSOLE_ACCESS") {
              setStatus("unauthenticated");
              throw new Error(data.detail || "No active console access.");
            }
            setStatus("forbidden");
            throw new Error(data?.detail || "Access restricted.");
          }
          if (err.status === 429) {
            throw new Error("Too many login attempts. Please try again later.");
          }
          if (err.status === 400) {
            throw new Error("Please provide a valid email and password.");
          }
        }
        setStatus("unauthenticated");
        throw new Error("Authentication failed. Please check your credentials and try again.");
      }
    },
    []
  );

  const selectContext = useCallback(
    async (payload: ContextSelectionPayload): Promise<ContextSelectionResponse> => {
      const res = await apiClient.auth.selectContext(payload);
      await refreshUser();
      return res;
    },
    [refreshUser]
  );

  const logout = useCallback(async () => {
    try {
      await apiClient.auth.logout();
      setUser(null);
      setStatus("unauthenticated");
      setError(null);
    } catch {
      // If server logout fails, do not falsely claim session was destroyed
      setError("Logout encountered an unexpected server error.");
      throw new Error("Failed to log out from server session.");
    }
  }, []);

  const value: AuthContextType = {
    user,
    status,
    error,
    login,
    logout,
    refreshUser,
    selectContext,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
};

export function useAuth(): AuthContextType {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}
