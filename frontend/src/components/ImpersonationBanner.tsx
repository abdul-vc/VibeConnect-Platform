/**
 * Persistent Impersonation Security Banner (Phase 6D).
 *
 * Requirements:
 * - Persistent, unmissable warning banner displayed while impersonation is active.
 * - Displays real operator identity AND target identity.
 * - Displays remaining time derived from server `expires_at` and refreshed from server.
 * - Triggers immediate exit when server returns 403 / session expired.
 * - Explicit "End Impersonation" action terminating the session server-side.
 */

import React, { useEffect, useState, useCallback } from "react";
import { useAuth } from "../context/AuthContext.tsx";
import {
  supportApi,
  type SupportImpersonationSessionData,
} from "../api/support.ts";
import {
  setActiveImpersonationSessionId,
  setOnImpersonationExpired,
} from "../api/client.ts";
import { ShieldCheckIcon, LogOutIcon } from "./Icons.tsx";

interface ImpersonationBannerProps {
  readonly onSessionEnded?: () => void;
}

export const ImpersonationBanner: React.FC<ImpersonationBannerProps> = ({
  onSessionEnded,
}) => {
  const { user } = useAuth();
  const [session, setSession] = useState<SupportImpersonationSessionData | null>(null);
  const [remainingSecs, setRemainingSecs] = useState<number>(0);
  const [isEnding, setIsEnding] = useState<boolean>(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const fetchActiveSession = useCallback(async () => {
    try {
      const active = await supportApi.getActiveImpersonationSession();
      if (active && active.status === "active") {
        setSession(active);
        setActiveImpersonationSessionId(active.id);
        setRemainingSecs(active.remaining_seconds);
      } else {
        setSession(null);
        setActiveImpersonationSessionId(null);
        if (onSessionEnded) {
          onSessionEnded();
        }
      }
    } catch {
      setSession(null);
      setActiveImpersonationSessionId(null);
    }
  }, [onSessionEnded]);

  // Initial fetch and server sync interval
  useEffect(() => {
    void fetchActiveSession();

    // Register 403 mid-session handler from API client
    setOnImpersonationExpired(() => {
      setSession(null);
      setActiveImpersonationSessionId(null);
      if (onSessionEnded) {
        onSessionEnded();
      }
    });

    const handleSessionStarted = () => {
      void fetchActiveSession();
    };
    window.addEventListener("impersonation-started", handleSessionStarted);

    // Re-verify authority with server every 30 seconds
    const serverSyncInterval = setInterval(() => {
      void fetchActiveSession();
    }, 30000);

    return () => {
      clearInterval(serverSyncInterval);
      window.removeEventListener("impersonation-started", handleSessionStarted);
      setOnImpersonationExpired(null);
    };
  }, [fetchActiveSession, onSessionEnded]);

  // Local second ticker between server syncs
  useEffect(() => {
    if (!session || remainingSecs <= 0) return;

    const ticker = setInterval(() => {
      setRemainingSecs((prev) => {
        if (prev <= 1) {
          // Trigger immediate server check when timer reaches 0
          void fetchActiveSession();
          return 0;
        }
        return prev - 1;
      });
    }, 1000);

    return () => clearInterval(ticker);
  }, [session, remainingSecs, fetchActiveSession]);

  const isTargetUser = Boolean(
    user && (user.id === session?.target_user || user.email === session?.target_user_email)
  );

  const handleEndSession = async () => {
    if (!session) return;
    setIsEnding(true);
    setErrorMessage(null);
    try {
      const terminationReason = isTargetUser
        ? "Target user terminated support investigation session."
        : "Operator concluded support investigation.";
      await supportApi.terminateImpersonationSession(session.id, terminationReason);
      setSession(null);
      setActiveImpersonationSessionId(null);
      if (onSessionEnded) {
        onSessionEnded();
      }
    } catch (err: unknown) {
      setErrorMessage(
        err instanceof Error ? err.message : "Failed to end impersonation session."
      );
    } finally {
      setIsEnding(false);
    }
  };

  if (!session) {
    return null;
  }

  const minutes = Math.floor(remainingSecs / 60);
  const seconds = remainingSecs % 60;
  const timeFormatted = `${minutes}:${seconds < 10 ? "0" : ""}${seconds}`;

  return (
    <div
      role="alert"
      aria-live="assertive"
      style={{
        background: isTargetUser
          ? "linear-gradient(90deg, rgba(180, 83, 9, 0.95), rgba(161, 98, 7, 0.95))"
          : "linear-gradient(90deg, rgba(234, 88, 12, 0.95), rgba(194, 65, 12, 0.95))",
        color: "#ffffff",
        padding: "0.625rem 1.25rem",
        borderRadius: "8px",
        marginBottom: "1rem",
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        gap: "1rem",
        boxShadow: "0 4px 12px rgba(234, 88, 12, 0.25)",
        flexWrap: "wrap",
        border: "1px solid rgba(255, 255, 255, 0.2)",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", flex: 1, minWidth: "280px" }}>
        <div
          style={{
            background: "rgba(255, 255, 255, 0.2)",
            borderRadius: "50%",
            width: "32px",
            height: "32px",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            flexShrink: 0,
          }}
        >
          <ShieldCheckIcon size={18} />
        </div>
        <div>
          <div style={{ fontSize: "0.875rem", fontWeight: 700, letterSpacing: "0.01em" }}>
            {isTargetUser
              ? "ACTIVE SUPPORT INVESTIGATION IN PROGRESS (AUDITED)"
              : "ACTIVE SUPPORT IMPERSONATION SESSION (AUDITED)"}
          </div>
          <div style={{ fontSize: "0.75rem", opacity: 0.95, marginTop: "2px" }}>
            {isTargetUser ? (
              <>
                Authorized Support Operator <strong>{session.operator_email}</strong> is investigating under Ticket{" "}
                <strong>#{session.ticket_reference || "N/A"}</strong>. All actions are immutably audited.
              </>
            ) : (
              <>
                Operator: <strong>{session.operator_email}</strong> &bull; Acting as:{" "}
                <strong>
                  {session.target_user_name} ({session.target_user_email})
                </strong>{" "}
                &bull; Organization: <strong>{session.target_organization_name}</strong>
              </>
            )}
          </div>
        </div>
      </div>

      <div style={{ display: "flex", alignItems: "center", gap: "1rem" }}>
        <div
          style={{
            background: "rgba(0, 0, 0, 0.25)",
            padding: "0.35rem 0.75rem",
            borderRadius: "6px",
            fontSize: "0.8125rem",
            fontWeight: 700,
            fontFamily: "monospace",
            display: "flex",
            alignItems: "center",
            gap: "0.5rem",
          }}
        >
          <span>EXPIRES IN:</span>
          <span style={{ color: remainingSecs < 300 ? "#fef08a" : "#ffffff" }}>
            {timeFormatted}
          </span>
        </div>

        <button
          type="button"
          onClick={handleEndSession}
          disabled={isEnding}
          style={{
            background: "#ffffff",
            color: isTargetUser ? "#b45309" : "#c2410c",
            border: "none",
            borderRadius: "6px",
            padding: "0.4rem 0.875rem",
            fontSize: "0.8125rem",
            fontWeight: 700,
            cursor: "pointer",
            display: "flex",
            alignItems: "center",
            gap: "0.4rem",
            transition: "opacity 150ms ease",
          }}
        >
          <LogOutIcon size={14} />
          <span>{isEnding ? "Ending..." : isTargetUser ? "Terminate Access" : "End Impersonation"}</span>
        </button>
      </div>

      {errorMessage && (
        <div style={{ width: "100%", fontSize: "0.75rem", color: "#fef08a", marginTop: "4px" }}>
          {errorMessage}
        </div>
      )}
    </div>
  );
};

