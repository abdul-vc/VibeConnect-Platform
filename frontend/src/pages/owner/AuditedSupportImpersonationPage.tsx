import React, { useEffect, useState, useCallback } from "react";
import { Link } from "react-router-dom";
import { AppShell } from "../../components/AppShell.tsx";
import { supportApi } from "../../api/support.ts";
import { apiClient } from "../../api/client.ts";
import { ENDPOINTS } from "../../api/endpoints.ts";
import { setActiveImpersonationSessionId } from "../../api/client.ts";
import type { SupportImpersonationSessionData, EligibleTargetUser } from "../../api/support.ts";
import { ShieldCheckIcon, AlertCircleIcon, UserIcon, RotateCcwIcon, LockIcon, BuildingIcon } from "../../components/Icons.tsx";
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
      <div style={{ maxWidth: "1400px", margin: "0 auto", padding: "2rem" }}>
        {/* Breadcrumb Navigation */}
        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", fontSize: "0.8125rem", color: "var(--text-muted)", marginBottom: "1.25rem", fontWeight: 500 }}>
          <Link to="/" style={{ color: "var(--text-muted)", textDecoration: "none", transition: "color 0.15s" }}>Platform Owner</Link>
          <span>/</span>
          <span>Customer Operations</span>
          <span>/</span>
          <span style={{ color: "var(--brand-primary)", fontWeight: 600 }}>Audited Support Impersonation</span>
        </div>

        {/* Header */}
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "2rem", flexWrap: "wrap", gap: "1rem" }}>
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
              <ShieldCheckIcon size={24} />
            </div>
            <div>
              <h1 className="heading-hero" style={{ fontSize: "1.75rem", fontWeight: 800, margin: 0, letterSpacing: "-0.02em", color: "var(--text-primary)" }}>
                Audited Support Impersonation
              </h1>
              <p style={{ color: "var(--text-secondary)", fontSize: "0.9375rem", margin: "0.25rem 0 0 0" }}>
                Operational control plane for initiating, inspecting, and terminating audited support sessions with strict justification validation and session isolation.
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={() => void loadData()}
            className="btn btn-secondary btn-sm"
            style={{ display: "inline-flex", alignItems: "center", gap: "0.5rem" }}
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
                  background: "linear-gradient(135deg, rgba(234, 88, 12, 0.08) 0%, rgba(249, 115, 22, 0.03) 100%)",
                  border: "1.5px solid rgba(234, 88, 12, 0.35)",
                  borderRadius: 16,
                  padding: "1.5rem 1.75rem",
                  boxShadow: "var(--shadow-md)",
                }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1.25rem", flexWrap: "wrap", gap: "1rem" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                    <span style={{ display: "inline-block", width: 10, height: 10, borderRadius: "50%", background: "#f97316", boxShadow: "0 0 10px #f97316" }} />
                    <h2 style={{ fontSize: "1.125rem", fontWeight: 700, margin: 0, color: "var(--text-primary)", letterSpacing: "-0.01em" }}>
                      Active Impersonation Session
                    </h2>
                    <span style={{ fontSize: "0.75rem", fontWeight: 600, padding: "0.2rem 0.65rem", borderRadius: "999px", background: "rgba(234, 88, 12, 0.15)", color: "#ea580c", border: "1px solid rgba(234, 88, 12, 0.3)" }}>
                      Live Session
                    </span>
                  </div>
                  <button
                    type="button"
                    onClick={handleTerminateSession}
                    disabled={submitting}
                    className="btn"
                    style={{
                      background: "linear-gradient(135deg, #ef4444 0%, #dc2626 100%)",
                      color: "#fff",
                      border: "none",
                      borderRadius: 10,
                      padding: "0.55rem 1.35rem",
                      fontWeight: 700,
                      fontSize: "0.85rem",
                      cursor: submitting ? "not-allowed" : "pointer",
                      boxShadow: "0 2px 8px rgba(239, 68, 68, 0.3)",
                    }}
                  >
                    {submitting ? "Terminating…" : "Terminate Session"}
                  </button>
                </div>

                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: "1rem", fontSize: "0.88rem" }}>
                  <div style={{ background: "var(--glass-surface-elevated)", padding: "0.85rem 1rem", borderRadius: 10, border: "1px solid var(--border-glass)" }}>
                    <span style={{ color: "var(--text-muted)", display: "block", fontSize: "0.75rem", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.04em", marginBottom: 4 }}>Target User</span>
                    <strong style={{ color: "var(--text-primary)" }}>{activeSession.target_user_name || activeSession.target_user_email}</strong>
                    <div style={{ fontSize: "0.78rem", color: "var(--text-secondary)", marginTop: 2 }}>{activeSession.target_user_email}</div>
                  </div>
                  <div style={{ background: "var(--glass-surface-elevated)", padding: "0.85rem 1rem", borderRadius: 10, border: "1px solid var(--border-glass)" }}>
                    <span style={{ color: "var(--text-muted)", display: "block", fontSize: "0.75rem", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.04em", marginBottom: 4 }}>Target Organization</span>
                    <strong style={{ color: "var(--text-primary)" }}>{activeSession.target_organization_name || activeSession.target_organization}</strong>
                  </div>
                  <div style={{ background: "var(--glass-surface-elevated)", padding: "0.85rem 1rem", borderRadius: 10, border: "1px solid var(--border-glass)" }}>
                    <span style={{ color: "var(--text-muted)", display: "block", fontSize: "0.75rem", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.04em", marginBottom: 4 }}>Ticket Reference</span>
                    <code style={{ background: "var(--glass-surface-sunken)", padding: "0.2rem 0.5rem", borderRadius: 6, border: "1px solid var(--border-subtle)", fontSize: "0.82rem", color: "var(--brand-primary)", fontWeight: 700 }}>
                      {activeSession.ticket_reference || "N/A"}
                    </code>
                  </div>
                  <div style={{ background: "var(--glass-surface-elevated)", padding: "0.85rem 1rem", borderRadius: 10, border: "1px solid var(--border-glass)" }}>
                    <span style={{ color: "var(--text-muted)", display: "block", fontSize: "0.75rem", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.04em", marginBottom: 4 }}>Remaining Duration</span>
                    <strong style={{ color: "#f97316", fontSize: "1.05rem" }}>
                      {Math.max(0, Math.floor(activeSession.remaining_seconds / 60))}m {activeSession.remaining_seconds % 60}s
                    </strong>
                  </div>
                </div>

                {activeSession.reason && (
                  <div style={{ marginTop: "1rem", paddingTop: "0.85rem", borderTop: "1px dashed rgba(234, 88, 12, 0.3)", fontSize: "0.85rem" }}>
                    <span style={{ color: "var(--text-muted)", fontWeight: 600 }}>Operational Justification: </span>
                    <span style={{ color: "var(--text-secondary)", fontStyle: "italic" }}>{activeSession.reason}</span>
                  </div>
                )}
              </div>
            ) : (
              <div
                style={{
                  background: "var(--glass-surface-elevated)",
                  border: "1px solid var(--border-glass)",
                  borderRadius: 14,
                  padding: "1.1rem 1.5rem",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  boxShadow: "var(--shadow-sm)",
                  flexWrap: "wrap",
                  gap: "1rem",
                }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: "0.875rem" }}>
                  <div
                    style={{
                      width: 38,
                      height: 38,
                      borderRadius: 10,
                      background: "var(--surface-soft-blue)",
                      border: "1px solid rgba(56, 103, 245, 0.2)",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      color: "var(--brand-primary)",
                      flexShrink: 0,
                    }}
                  >
                    <UserIcon size={18} />
                  </div>
                  <div>
                    <div style={{ fontSize: "0.875rem", fontWeight: 600, color: "var(--text-primary)" }}>
                      Native Platform Owner Identity Active
                    </div>
                    <div style={{ fontSize: "0.8125rem", color: "var(--text-secondary)" }}>
                      No support impersonation session in progress. All actions and API calls are operating under your direct credentials.
                    </div>
                  </div>
                </div>

                <div
                  style={{
                    display: "inline-flex",
                    alignItems: "center",
                    gap: "0.4rem",
                    padding: "0.3rem 0.75rem",
                    borderRadius: "999px",
                    background: "var(--status-success-bg)",
                    border: "1px solid var(--status-success-border)",
                    color: "var(--status-success)",
                    fontSize: "0.75rem",
                    fontWeight: 600,
                  }}
                >
                  <span style={{ width: 6, height: 6, borderRadius: "50%", background: "var(--status-success)" }} />
                  Direct Operations
                </div>
              </div>
            )}

            {/* Initiate Form Card */}
            <div
              style={{
                background: "var(--glass-surface-elevated)",
                border: "1px solid var(--border-glass)",
                borderRadius: 16,
                boxShadow: "var(--shadow-md)",
                overflow: "hidden",
              }}
            >
              {/* Card Accent Top Bar */}
              <div style={{ height: 3, background: "var(--brand-gradient)" }} />

              <div style={{ padding: "1.75rem 2rem" }}>
                {/* Card Header */}
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: "1rem", marginBottom: "1.5rem" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: "0.875rem" }}>
                    <div
                      style={{
                        width: 40,
                        height: 40,
                        borderRadius: 12,
                        background: "var(--surface-soft-blue)",
                        border: "1px solid rgba(56, 103, 245, 0.25)",
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                        color: "var(--brand-primary)",
                        flexShrink: 0,
                      }}
                    >
                      <LockIcon size={20} />
                    </div>
                    <div>
                      <h2 style={{ fontSize: "1.125rem", fontWeight: 700, margin: 0, color: "var(--text-primary)", letterSpacing: "-0.01em" }}>
                        Initiate New Audited Session
                      </h2>
                      <p style={{ margin: "0.15rem 0 0 0", fontSize: "0.8125rem", color: "var(--text-secondary)" }}>
                        Establish a short-lived, strictly governed impersonation token for emergency tenant debugging and audit compliance.
                      </p>
                    </div>
                  </div>

                  <div
                    style={{
                      display: "inline-flex",
                      alignItems: "center",
                      gap: "0.4rem",
                      padding: "0.35rem 0.75rem",
                      borderRadius: "999px",
                      background: "var(--surface-soft-lavender)",
                      border: "1px solid rgba(155, 77, 255, 0.25)",
                      color: "var(--brand-indigo)",
                      fontSize: "0.75rem",
                      fontWeight: 600,
                    }}
                  >
                    <span style={{ width: 6, height: 6, borderRadius: "50%", background: "currentColor" }} />
                    30-Min Session Cap
                  </div>
                </div>

                {formError && (
                  <div
                    style={{
                      padding: "0.85rem 1.15rem",
                      background: "var(--status-danger-bg)",
                      border: "1px solid var(--status-danger-border)",
                      borderRadius: 10,
                      color: "var(--status-danger)",
                      marginBottom: "1.25rem",
                      fontSize: "0.875rem",
                      display: "flex",
                      alignItems: "center",
                      gap: "0.6rem",
                    }}
                  >
                    <AlertCircleIcon size={16} />
                    <span>{formError}</span>
                  </div>
                )}

                <form onSubmit={handleStartSession}>
                  <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: "1.25rem", marginBottom: "1.25rem" }}>
                    <div>
                      <label style={{ display: "flex", alignItems: "center", gap: "0.35rem", fontSize: "0.8125rem", fontWeight: 600, color: "var(--text-secondary)", marginBottom: "0.5rem" }}>
                        <BuildingIcon size={14} style={{ color: "var(--brand-primary)" }} />
                        <span>Organization</span>
                        <span style={{ color: "var(--status-danger)" }}>*</span>
                      </label>
                      <select
                        value={selectedOrgId}
                        onChange={(e) => setSelectedOrgId(e.target.value)}
                        disabled={submitting || Boolean(activeSession)}
                        style={{
                          width: "100%",
                          padding: "0.75rem 2.5rem 0.75rem 1rem",
                          borderRadius: 10,
                          background: "var(--input-bg, #ffffff)",
                          border: "1px solid var(--input-border, var(--border-subtle))",
                          color: "var(--text-primary)",
                          fontSize: "0.875rem",
                          boxShadow: "var(--shadow-sm)",
                          backgroundImage: `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='16' height='16' viewBox='0 0 24 24' fill='none' stroke='%2375829a' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='m6 9 6 6 6-6'/%3E%3C/svg%3E")`,
                          backgroundRepeat: "no-repeat",
                          backgroundPosition: "right 0.85rem center",
                          appearance: "none",
                          WebkitAppearance: "none",
                          cursor: submitting || Boolean(activeSession) ? "not-allowed" : "pointer",
                          opacity: activeSession ? 0.6 : 1,
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
                      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "0.5rem" }}>
                        <label style={{ display: "flex", alignItems: "center", gap: "0.35rem", fontSize: "0.8125rem", fontWeight: 600, color: "var(--text-secondary)" }}>
                          <UserIcon size={14} style={{ color: "var(--brand-primary)" }} />
                          <span>Eligible Target User</span>
                          <span style={{ color: "var(--status-danger)" }}>*</span>
                        </label>
                        {selectedOrgId && (
                          <span style={{ fontSize: "0.75rem", fontWeight: 500, color: "var(--text-muted)", background: "var(--glass-surface-sunken)", padding: "0.15rem 0.5rem", borderRadius: "999px", border: "1px solid var(--border-subtle)" }}>
                            {eligibleTargets.length} eligible
                          </span>
                        )}
                      </div>
                      <select
                        value={selectedTargetUserId}
                        onChange={(e) => setSelectedTargetUserId(e.target.value)}
                        disabled={submitting || Boolean(activeSession) || eligibleTargets.length === 0}
                        style={{
                          width: "100%",
                          padding: "0.75rem 2.5rem 0.75rem 1rem",
                          borderRadius: 10,
                          background: "var(--input-bg, #ffffff)",
                          border: "1px solid var(--input-border, var(--border-subtle))",
                          color: "var(--text-primary)",
                          fontSize: "0.875rem",
                          boxShadow: "var(--shadow-sm)",
                          backgroundImage: `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='16' height='16' viewBox='0 0 24 24' fill='none' stroke='%2375829a' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='m6 9 6 6 6-6'/%3E%3C/svg%3E")`,
                          backgroundRepeat: "no-repeat",
                          backgroundPosition: "right 0.85rem center",
                          appearance: "none",
                          WebkitAppearance: "none",
                          cursor: submitting || Boolean(activeSession) || eligibleTargets.length === 0 ? "not-allowed" : "pointer",
                          opacity: activeSession || eligibleTargets.length === 0 ? 0.6 : 1,
                        }}
                      >
                        {eligibleTargets.length === 0 ? (
                          <option value="">{selectedOrgId ? "No eligible target users found in this organization" : "Select organization first…"}</option>
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

                  <div style={{ marginBottom: "1.25rem" }}>
                    <label style={{ display: "block", fontSize: "0.8125rem", fontWeight: 600, color: "var(--text-secondary)", marginBottom: "0.5rem" }}>
                      Incident / Ticket Reference <span style={{ color: "var(--status-danger)" }}>*</span>
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
                        padding: "0.75rem 1rem",
                        borderRadius: 10,
                        background: "var(--input-bg, #ffffff)",
                        border: "1px solid var(--input-border, var(--border-subtle))",
                        color: "var(--text-primary)",
                        fontSize: "0.875rem",
                        boxSizing: "border-box",
                        boxShadow: "var(--shadow-sm)",
                        cursor: submitting || Boolean(activeSession) ? "not-allowed" : "text",
                        opacity: activeSession ? 0.6 : 1,
                      }}
                    />
                  </div>

                  <div style={{ marginBottom: "1.5rem" }}>
                    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "0.5rem" }}>
                      <label style={{ display: "block", fontSize: "0.8125rem", fontWeight: 600, color: "var(--text-secondary)" }}>
                        Justification & Root Cause Context <span style={{ color: "var(--status-danger)" }}>*</span>
                      </label>
                      <span style={{ fontSize: "0.75rem", color: reason.length > 450 ? "var(--status-warning)" : "var(--text-muted)", fontWeight: 500 }}>
                        {reason.length} / 500
                      </span>
                    </div>
                    <textarea
                      value={reason}
                      onChange={(e) => setReason(e.target.value)}
                      placeholder="Provide specific technical explanation and incident context for session initiation (max 500 characters)..."
                      maxLength={500}
                      rows={3}
                      disabled={submitting || Boolean(activeSession)}
                      style={{
                        width: "100%",
                        padding: "0.75rem 1rem",
                        borderRadius: 10,
                        background: "var(--input-bg, #ffffff)",
                        border: "1px solid var(--input-border, var(--border-subtle))",
                        color: "var(--text-primary)",
                        fontSize: "0.875rem",
                        fontFamily: "inherit",
                        lineHeight: 1.5,
                        boxSizing: "border-box",
                        boxShadow: "var(--shadow-sm)",
                        resize: "vertical",
                        cursor: submitting || Boolean(activeSession) ? "not-allowed" : "text",
                        opacity: activeSession ? 0.6 : 1,
                      }}
                    />
                  </div>

                  <div
                    style={{
                      display: "flex",
                      justifyContent: "space-between",
                      alignItems: "center",
                      paddingTop: "1.25rem",
                      borderTop: "1px solid var(--border-subtle)",
                      flexWrap: "wrap",
                      gap: "1rem",
                    }}
                  >
                    <div style={{ fontSize: "0.8125rem", color: "var(--text-muted)", display: "flex", alignItems: "center", gap: 8 }}>
                      <AlertCircleIcon size={16} style={{ color: "var(--brand-primary)", flexShrink: 0 }} />
                      <span>Sessions expire automatically after 30 minutes and emit immutable audit records.</span>
                    </div>
                    <button
                      type="submit"
                      disabled={submitting || Boolean(activeSession)}
                      className="btn btn-gradient"
                      style={{
                        padding: "0.75rem 1.75rem",
                        fontSize: "0.9rem",
                        fontWeight: 700,
                        borderRadius: 10,
                        cursor: submitting || Boolean(activeSession) ? "not-allowed" : "pointer",
                        opacity: activeSession ? 0.5 : 1,
                        boxShadow: "0 4px 14px rgba(56, 103, 245, 0.25)",
                        display: "inline-flex",
                        alignItems: "center",
                        gap: "0.5rem",
                      }}
                    >
                      {submitting ? (
                        <>
                          <span style={{ display: "inline-block", width: 14, height: 14, borderRadius: "50%", border: "2px solid rgba(255,255,255,0.3)", borderTopColor: "#fff", animation: "spin 0.8s linear infinite" }} />
                          Initiating Session…
                        </>
                      ) : (
                        <>
                          <ShieldCheckIcon size={18} />
                          Initiate Audited Session
                        </>
                      )}
                    </button>
                  </div>
                </form>
              </div>
            </div>
          </div>
        )}
      </div>
    </AppShell>
  );
};
