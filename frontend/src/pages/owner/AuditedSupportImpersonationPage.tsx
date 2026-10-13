import React, { useEffect, useState, useCallback } from "react";
import { AppShell } from "../../components/AppShell.tsx";
import { supportApi } from "../../api/support.ts";
import { apiClient } from "../../api/client.ts";
import { ENDPOINTS } from "../../api/endpoints.ts";
import { setActiveImpersonationSessionId } from "../../api/client.ts";
import type { SupportImpersonationSessionData, EligibleTargetUser } from "../../api/support.ts";
import { ShieldCheckIcon, AlertCircleIcon, UserIcon, RotateCcwIcon } from "../../components/Icons.tsx";
import { LoadingSpinner } from "../../components/LoadingSpinner.tsx";

export const AuditedSupportImpersonationPage: React.FC = () => {
  const [activeSession, setActiveSession] = useState<SupportImpersonationSessionData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [successNotice, setSuccessNotice] = useState<string | null>(null);

  // Form states
  const [organizations, setOrganizations] = useState<Array<{ id: string; name: string; code: string }>>([]);
  const [selectedOrgId, setSelectedOrgId] = useState<string>("");
  const [eligibleTargets, setEligibleTargets] = useState<readonly EligibleTargetUser[]>([]);
  const [selectedTargetUserId, setSelectedTargetUserId] = useState<string>("");
  const [ticketRef, setTicketRef] = useState<string>("");
  const [reason, setReason] = useState<string>("");
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const fetchActiveSession = useCallback(async () => {
    try {
      const res = await supportApi.getActiveImpersonationSession();
      setActiveSession(res);
      if (res) {
        setActiveImpersonationSessionId(res.id);
      }
    } catch {
      // safe fallback
      setActiveSession(null);
    }
  }, []);

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      await fetchActiveSession();
      // Load organizations for target selection
      const orgRes = await apiClient.get<{ results: Array<{ id: string; name: string; code: string }> }>(
        ENDPOINTS.ORGANIZATIONS.LIST,
        { params: { page_size: 100, status: "active" } }
      );
      setOrganizations(orgRes.results || []);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to load support impersonation context.");
    } finally {
      setLoading(false);
    }
  }, [fetchActiveSession]);

  useEffect(() => {
    void loadData();
  }, [loadData]);

  // Load eligible targets when org changes
  useEffect(() => {
    if (!selectedOrgId) {
      setEligibleTargets([]);
      setSelectedTargetUserId("");
      return;
    }
    let isCancelled = false;
    const fetchTargets = async () => {
      try {
        const targets = await supportApi.getEligibleTargets(selectedOrgId);
        if (!isCancelled) {
          setEligibleTargets(targets);
          if (targets.length > 0) {
            setSelectedTargetUserId(targets[0].id);
          } else {
            setSelectedTargetUserId("");
          }
        }
      } catch {
        if (!isCancelled) {
          setEligibleTargets([]);
          setSelectedTargetUserId("");
        }
      }
    };
    void fetchTargets();
    return () => {
      isCancelled = true;
    };
  }, [selectedOrgId]);

  const handleStartSession = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormError(null);
    setSuccessNotice(null);

    const cleanTicket = ticketRef.trim();
    const cleanReason = reason.trim();

    if (!selectedOrgId) {
      setFormError("Target organization is required.");
      return;
    }
    if (!selectedTargetUserId) {
      setFormError("Target user selection is required.");
      return;
    }
    if (!cleanTicket) {
      setFormError("Mandatory ticket / incident reference is required (e.g., TICKET-1042).");
      return;
    }
    if (!cleanReason) {
      setFormError("Mandatory justification / reason is required (up to 500 characters).");
      return;
    }

    setSubmitting(true);
    try {
      const session = await supportApi.createImpersonationSession({
        target_organization_id: selectedOrgId,
        target_user_id: selectedTargetUserId,
        ticket_reference: cleanTicket,
        reason: cleanReason,
      });
      setActiveSession(session);
      setActiveImpersonationSessionId(session.id);
      setSuccessNotice(`Audited impersonation session successfully initiated for ${session.target_user_email}.`);
      setTicketRef("");
      setReason("");
      window.dispatchEvent(new Event("impersonation-started"));
    } catch (err: unknown) {
      setFormError(err instanceof Error ? err.message : "Failed to initiate impersonation session.");
    } finally {
      setSubmitting(false);
    }
  };

  const handleTerminateSession = async () => {
    if (!activeSession) return;
    setSubmitting(true);
    setError(null);
    try {
      await supportApi.terminateImpersonationSession(activeSession.id);
      setActiveSession(null);
      setActiveImpersonationSessionId(null);
      setSuccessNotice("Impersonation session terminated and logged to immutable audit trail.");
      window.dispatchEvent(new Event("impersonation-ended"));
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to terminate session.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <AppShell>
      <div style={{ maxWidth: "1080px", margin: "0 auto", padding: "1.75rem 1rem" }}>
        {/* Header */}
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "1.75rem" }}>
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <ShieldCheckIcon size={24} color="var(--brand-primary, #6366f1)" />
              <h1 style={{ fontSize: "1.5rem", fontWeight: 800, margin: 0, color: "var(--text-primary)" }}>
                Audited Support Impersonation
              </h1>
            </div>
            <p style={{ color: "var(--text-muted)", fontSize: "0.88rem", marginTop: 4 }}>
              Operational control plane for initiating, inspecting, and terminating audited support sessions with strict justification validation and session isolation.
            </p>
          </div>
          <button
            type="button"
            onClick={() => void loadData()}
            className="btn-secondary"
            style={{ display: "inline-flex", alignItems: "center", gap: 6, padding: "0.45rem 0.9rem", fontSize: "0.82rem" }}
          >
            <RotateCcwIcon size={14} /> Refresh
          </button>
        </div>

        {error && (
          <div style={{ padding: "0.85rem 1rem", background: "rgba(239, 68, 68, 0.1)", border: "1px solid rgba(239, 68, 68, 0.3)", borderRadius: 8, color: "#f87171", marginBottom: "1.25rem", fontSize: "0.88rem" }}>
            {error}
          </div>
        )}

        {successNotice && (
          <div style={{ padding: "0.85rem 1rem", background: "rgba(34, 197, 94, 0.1)", border: "1px solid rgba(34, 197, 94, 0.3)", borderRadius: 8, color: "#4ade80", marginBottom: "1.25rem", fontSize: "0.88rem" }}>
            {successNotice}
          </div>
        )}

        {loading ? (
          <div style={{ display: "flex", justifyContent: "center", padding: "4rem" }}>
            <LoadingSpinner label="Loading impersonation operational state…" />
          </div>
        ) : (
          <div style={{ display: "grid", gridTemplateColumns: "1fr", gap: "1.5rem" }}>
            {/* Active Session Card */}
            {activeSession ? (
              <div
                style={{
                  background: "rgba(234, 88, 12, 0.08)",
                  border: "1.5px solid rgba(234, 88, 12, 0.35)",
                  borderRadius: 14,
                  padding: "1.5rem",
                }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1rem" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <span style={{ display: "inline-block", width: 10, height: 10, borderRadius: "50%", background: "#f97316", boxShadow: "0 0 8px #f97316" }} />
                    <h2 style={{ fontSize: "1.1rem", fontWeight: 700, margin: 0, color: "var(--text-primary)" }}>
                      Active Impersonation Session
                    </h2>
                  </div>
                  <button
                    type="button"
                    onClick={handleTerminateSession}
                    disabled={submitting}
                    style={{
                      background: "#ef4444",
                      color: "#fff",
                      border: "none",
                      borderRadius: 8,
                      padding: "0.5rem 1.25rem",
                      fontWeight: 700,
                      fontSize: "0.85rem",
                      cursor: submitting ? "not-allowed" : "pointer",
                    }}
                  >
                    {submitting ? "Terminating…" : "Terminate Session"}
                  </button>
                </div>

                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: "1rem", fontSize: "0.88rem" }}>
                  <div>
                    <span style={{ color: "var(--text-muted)", display: "block", fontSize: "0.78rem" }}>Target User</span>
                    <strong>{activeSession.target_user_name || activeSession.target_user_email}</strong>
                    <div style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>{activeSession.target_user_email}</div>
                  </div>
                  <div>
                    <span style={{ color: "var(--text-muted)", display: "block", fontSize: "0.78rem" }}>Target Organization</span>
                    <strong>{activeSession.target_organization_name || activeSession.target_organization}</strong>
                  </div>
                  <div>
                    <span style={{ color: "var(--text-muted)", display: "block", fontSize: "0.78rem" }}>Ticket Reference</span>
                    <code>{activeSession.ticket_reference || "N/A"}</code>
                  </div>
                  <div>
                    <span style={{ color: "var(--text-muted)", display: "block", fontSize: "0.78rem" }}>Remaining Duration</span>
                    <strong style={{ color: "#f97316" }}>{Math.max(0, Math.floor(activeSession.remaining_seconds / 60))}m {activeSession.remaining_seconds % 60}s</strong>
                  </div>
                </div>

                {activeSession.reason && (
                  <div style={{ marginTop: "1rem", paddingTop: "0.85rem", borderTop: "1px dashed rgba(234, 88, 12, 0.25)", fontSize: "0.85rem" }}>
                    <span style={{ color: "var(--text-muted)" }}>Operational Justification: </span>
                    <em>{activeSession.reason}</em>
                  </div>
                )}
              </div>
            ) : (
              <div
                style={{
                  background: "var(--glass-surface-sunken, rgba(15, 23, 42, 0.4))",
                  border: "1px solid var(--border-glass, rgba(255, 255, 255, 0.1))",
                  borderRadius: 14,
                  padding: "1.25rem 1.5rem",
                  display: "flex",
                  alignItems: "center",
                  gap: 12,
                  color: "var(--text-muted)",
                }}
              >
                <UserIcon size={20} />
                <span>No active support impersonation session in progress. All actions are currently operating under your native Platform Owner identity.</span>
              </div>
            )}

            {/* Initiate Form Card */}
            <div
              style={{
                background: "var(--surface-card, #1e293b)",
                border: "1px solid var(--border-glass, rgba(255, 255, 255, 0.1))",
                borderRadius: 14,
                padding: "1.75rem",
              }}
            >
              <h3 style={{ fontSize: "1.05rem", fontWeight: 700, margin: "0 0 1rem 0", color: "var(--text-primary)" }}>
                Initiate New Audited Session
              </h3>

              {formError && (
                <div style={{ padding: "0.75rem 1rem", background: "rgba(239, 68, 68, 0.1)", border: "1px solid rgba(239, 68, 68, 0.3)", borderRadius: 8, color: "#f87171", marginBottom: "1rem", fontSize: "0.85rem" }}>
                  {formError}
                </div>
              )}

              <form onSubmit={handleStartSession}>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem", marginBottom: "1rem" }}>
                  <div>
                    <label style={{ display: "block", fontSize: "0.8rem", fontWeight: 600, color: "var(--text-secondary)", marginBottom: 4 }}>
                      Organization <span style={{ color: "#ef4444" }}>*</span>
                    </label>
                    <select
                      value={selectedOrgId}
                      onChange={(e) => setSelectedOrgId(e.target.value)}
                      disabled={submitting || Boolean(activeSession)}
                      style={{
                        width: "100%",
                        padding: "0.6rem 0.75rem",
                        borderRadius: 8,
                        background: "var(--surface-raised, #0f172a)",
                        border: "1px solid var(--border-glass, rgba(255, 255, 255, 0.15))",
                        color: "var(--text-primary)",
                        fontSize: "0.88rem",
                      }}
                    >
                      <option value="">Select Target Organization…</option>
                      {organizations.map((org) => (
                        <option key={org.id} value={org.id}>
                          {org.name} ({org.code})
                        </option>
                      ))}
                    </select>
                  </div>

                  <div>
                    <label style={{ display: "block", fontSize: "0.8rem", fontWeight: 600, color: "var(--text-secondary)", marginBottom: 4 }}>
                      Eligible Target User <span style={{ color: "#ef4444" }}>*</span>
                    </label>
                    <select
                      value={selectedTargetUserId}
                      onChange={(e) => setSelectedTargetUserId(e.target.value)}
                      disabled={submitting || Boolean(activeSession) || eligibleTargets.length === 0}
                      style={{
                        width: "100%",
                        padding: "0.6rem 0.75rem",
                        borderRadius: 8,
                        background: "var(--surface-raised, #0f172a)",
                        border: "1px solid var(--border-glass, rgba(255, 255, 255, 0.15))",
                        color: "var(--text-primary)",
                        fontSize: "0.88rem",
                      }}
                    >
                      {eligibleTargets.length === 0 ? (
                        <option value="">{selectedOrgId ? "No eligible target users found" : "Select organization first…"}</option>
                      ) : (
                        eligibleTargets.map((u) => (
                          <option key={u.id} value={u.id}>
                            {u.full_name} ({u.email}) — [{u.membership_type}]
                          </option>
                        ))
                      )}
                    </select>
                  </div>
                </div>

                <div style={{ marginBottom: "1rem" }}>
                  <label style={{ display: "block", fontSize: "0.8rem", fontWeight: 600, color: "var(--text-secondary)", marginBottom: 4 }}>
                    Incident / Ticket Reference <span style={{ color: "#ef4444" }}>*</span>
                  </label>
                  <input
                    type="text"
                    value={ticketRef}
                    onChange={(e) => setTicketRef(e.target.value)}
                    placeholder="e.g. INC-8291 or SUPPORT-1042"
                    maxLength={100}
                    disabled={submitting || Boolean(activeSession)}
                    style={{
                      width: "100%",
                      padding: "0.6rem 0.75rem",
                      borderRadius: 8,
                      background: "var(--surface-raised, #0f172a)",
                      border: "1px solid var(--border-glass, rgba(255, 255, 255, 0.15))",
                      color: "var(--text-primary)",
                      fontSize: "0.88rem",
                      boxSizing: "border-box",
                    }}
                  />
                </div>

                <div style={{ marginBottom: "1.25rem" }}>
                  <label style={{ display: "block", fontSize: "0.8rem", fontWeight: 600, color: "var(--text-secondary)", marginBottom: 4 }}>
                    Justification & Root Cause Context <span style={{ color: "#ef4444" }}>*</span>
                  </label>
                  <textarea
                    value={reason}
                    onChange={(e) => setReason(e.target.value)}
                    placeholder="Provide specific technical explanation for session initiation (max 500 characters)..."
                    maxLength={500}
                    rows={3}
                    disabled={submitting || Boolean(activeSession)}
                    style={{
                      width: "100%",
                      padding: "0.6rem 0.75rem",
                      borderRadius: 8,
                      background: "var(--surface-raised, #0f172a)",
                      border: "1px solid var(--border-glass, rgba(255, 255, 255, 0.15))",
                      color: "var(--text-primary)",
                      fontSize: "0.88rem",
                      boxSizing: "border-box",
                      resize: "vertical",
                    }}
                  />
                  <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", textAlign: "right" }}>
                    {reason.length}/500
                  </div>
                </div>

                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <div style={{ fontSize: "0.78rem", color: "var(--text-muted)", display: "flex", alignItems: "center", gap: 6 }}>
                    <AlertCircleIcon size={14} /> Sessions expire automatically after 30 minutes and emit immutable audit records.
                  </div>
                  <button
                    type="submit"
                    disabled={submitting || Boolean(activeSession)}
                    className="btn-primary"
                    style={{
                      padding: "0.6rem 1.5rem",
                      fontSize: "0.88rem",
                      fontWeight: 700,
                      cursor: submitting || Boolean(activeSession) ? "not-allowed" : "pointer",
                      opacity: activeSession ? 0.5 : 1,
                    }}
                  >
                    {submitting ? "Initiating…" : "Initiate Audited Session"}
                  </button>
                </div>
              </form>
            </div>
          </div>
        )}
      </div>
    </AppShell>
  );
};
