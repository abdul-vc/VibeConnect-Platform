import React, { useEffect, useState, useCallback } from "react";
import { Link } from "react-router-dom";
import { AppShell } from "../../components/AppShell.tsx";
import { apiClient } from "../../api/client.ts";
import { ENDPOINTS } from "../../api/endpoints.ts";
import { LoadingSpinner } from "../../components/LoadingSpinner.tsx";
import { UserIcon, SearchIcon, RotateCcwIcon, PlusIcon } from "../../components/Icons.tsx";
import { useAuth } from "../../context/AuthContext.tsx";
import { InviteUserDialog } from "../../components/users/InviteUserDialog.tsx";

interface MemberRecord {
  id: string;
  user: {
    id: string;
    email: string;
    full_name: string;
    status: string;
  };
  membership_type: string;
  status: string;
  role: {
    id: string;
    code: string;
    name: string;
  } | null;
  joined_at: string | null;
}

export const TenantUsersPage: React.FC = () => {
  const { user } = useAuth();
  const currentOrgId = user?.active_context?.organization?.id;
  const [isInviteOpen, setIsInviteOpen] = useState(false);
  const [members, setMembers] = useState<readonly MemberRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [filterType, setFilterType] = useState<string>("");

  const loadMembers = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await apiClient.get<{ results: MemberRecord[] }>(
        ENDPOINTS.TENANT_ROLES.ADMIN_MEMBERSHIPS,
        { params: { membership_type: "all" } }
      );
      setMembers(res.results || []);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to load organization members.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadMembers();
  }, [loadMembers]);

  const filteredMembers = members.filter((m) => {
    if (filterType && m.membership_type !== filterType) return false;
    if (search) {
      const q = search.toLowerCase();
      const matchEmail = m.user.email.toLowerCase().includes(q);
      const matchName = (m.user.full_name || "").toLowerCase().includes(q);
      if (!matchEmail && !matchName) return false;
    }
    return true;
  });

  return (
    <AppShell>
      <div style={{ maxWidth: "1080px", margin: "0 auto", padding: "1.75rem 1rem" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "1.75rem" }}>
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <UserIcon size={24} color="var(--brand-primary, #6366f1)" />
              <h1 style={{ fontSize: "1.5rem", fontWeight: 800, margin: 0, color: "var(--text-primary)" }}>
                Users & Memberships
              </h1>
            </div>
            <p style={{ color: "var(--text-muted)", fontSize: "0.88rem", marginTop: 4 }}>
              Active users and organization memberships isolated strictly to your organization.
            </p>
          </div>
          <div style={{ display: "flex", gap: "0.625rem", alignItems: "center" }}>
            <button
              type="button"
              onClick={() => setIsInviteOpen(true)}
              className="btn btn-primary"
              disabled={!currentOrgId}
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: 7,
                padding: "0.55rem 1.15rem",
                fontSize: "0.85rem",
                fontWeight: 650,
                borderRadius: "10px",
                background: "linear-gradient(135deg, #3867F5 0%, #8A45F6 100%)",
                border: "none",
                color: "#FFFFFF",
                boxShadow: "0 4px 14px rgba(56, 103, 245, 0.28)",
                cursor: "pointer",
              }}
            >
              <PlusIcon size={16} /> + Invite User
            </button>
            {user?.active_context?.effective_permissions?.includes("roles.assign") && (
              <Link
                to="/tenant/member-onboarding"
                className="btn btn-secondary"
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  gap: 6,
                  padding: "0.5rem 0.95rem",
                  fontSize: "0.82rem",
                  textDecoration: "none",
                  borderRadius: "10px",
                  background: "var(--surface-card)",
                  border: "1px solid var(--border-subtle)",
                  color: "var(--text-secondary)",
                }}
              >
                Onboarding Wizard →
              </Link>
            )}
            <button
              type="button"
              onClick={() => void loadMembers()}
              className="btn-secondary"
              title="Refresh member list"
              style={{
                display: "inline-flex",
                alignItems: "center",
                justifyContent: "center",
                width: 38,
                height: 38,
                borderRadius: "10px",
                border: "1px solid var(--border-subtle)",
                background: "var(--surface-card)",
                color: "var(--text-secondary)",
                cursor: "pointer",
              }}
            >
              <RotateCcwIcon size={15} />
            </button>
          </div>
        </div>

        {error && (
          <div style={{ padding: "0.85rem 1rem", background: "rgba(239, 68, 68, 0.08)", border: "1px solid rgba(239, 68, 68, 0.25)", borderRadius: 10, color: "#ef4444", marginBottom: "1.25rem", fontSize: "0.88rem" }}>
            {error}
          </div>
        )}

        {/* Filters */}
        <div style={{ display: "flex", gap: "1rem", marginBottom: "1.25rem", flexWrap: "wrap", alignItems: "center", justifyContent: "space-between" }}>
          <div style={{ position: "relative", flex: 1, minWidth: "260px", maxWidth: "420px" }}>
            <span style={{ position: "absolute", left: 12, top: 11, color: "var(--text-muted)" }}>
              <SearchIcon size={16} />
            </span>
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search users by name or email…"
              className="form-input form-input-with-icon-left"
              style={{
                width: "100%",
                padding: "0.55rem 0.75rem 0.55rem 2.25rem",
                borderRadius: 10,
                background: "var(--surface-card)",
                border: "1px solid var(--border-subtle)",
                color: "var(--text-primary)",
                fontSize: "0.875rem",
                boxSizing: "border-box",
              }}
            />
          </div>

          <div style={{ display: "flex", gap: "0.5rem" }}>
            {[
              { type: "", label: "All Users", count: members.length },
              { type: "tenant_admin", label: "Admins", count: members.filter(m => m.membership_type === "tenant_admin").length },
              { type: "member", label: "Members", count: members.filter(m => m.membership_type === "member").length },
            ].map(({ type, label, count }) => (
              <button
                key={type}
                type="button"
                onClick={() => setFilterType(type)}
                style={{
                  padding: "0.45rem 0.95rem",
                  borderRadius: "9999px",
                  fontSize: "0.8125rem",
                  fontWeight: 600,
                  border: filterType === type ? "1.5px solid var(--brand-primary)" : "1px solid var(--border-subtle)",
                  background: filterType === type ? "linear-gradient(135deg, rgba(56, 103, 245, 0.12), rgba(138, 69, 246, 0.12))" : "var(--surface-card)",
                  color: filterType === type ? "var(--brand-primary)" : "var(--text-secondary)",
                  cursor: "pointer",
                  transition: "all 0.15s ease",
                  display: "inline-flex",
                  alignItems: "center",
                  gap: 6,
                  boxShadow: filterType === type ? "0 2px 8px rgba(56, 103, 245, 0.15)" : "none",
                }}
              >
                <span>{label}</span>
                <span
                  style={{
                    background: filterType === type ? "var(--brand-primary)" : "var(--surface-subtle, rgba(0,0,0,0.06))",
                    color: filterType === type ? "#FFFFFF" : "var(--text-muted)",
                    padding: "1px 6px",
                    borderRadius: "9999px",
                    fontSize: "0.72rem",
                    fontWeight: 700,
                  }}
                >
                  {count}
                </span>
              </button>
            ))}
          </div>
        </div>

        {loading ? (
          <div style={{ display: "flex", justifyContent: "center", padding: "4rem" }}>
            <LoadingSpinner label="Loading organization members…" />
          </div>
        ) : filteredMembers.length === 0 ? (
          <div
            style={{
              padding: "3.5rem 1.5rem",
              textAlign: "center",
              color: "var(--text-muted)",
              background: "var(--surface-card)",
              borderRadius: "16px",
              border: "1px dashed var(--border-subtle)",
            }}
          >
            No organization members found matching your search.
          </div>
        ) : (
          <div
            style={{
              background: "var(--surface-card)",
              border: "1px solid var(--border-subtle)",
              borderRadius: "16px",
              overflow: "hidden",
              boxShadow: "0 2px 10px rgba(25, 36, 58, 0.04)",
            }}
          >
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.875rem", textAlign: "left" }}>
              <thead>
                <tr style={{ borderBottom: "1px solid var(--border-subtle)", background: "var(--surface-subtle, #F8FAFF)" }}>
                  <th style={{ padding: "0.85rem 1.15rem", color: "var(--text-secondary)", fontWeight: 650, fontSize: "0.75rem", textTransform: "uppercase", letterSpacing: "0.05em" }}>User</th>
                  <th style={{ padding: "0.85rem 1.15rem", color: "var(--text-secondary)", fontWeight: 650, fontSize: "0.75rem", textTransform: "uppercase", letterSpacing: "0.05em" }}>Type</th>
                  <th style={{ padding: "0.85rem 1.15rem", color: "var(--text-secondary)", fontWeight: 650, fontSize: "0.75rem", textTransform: "uppercase", letterSpacing: "0.05em" }}>Role</th>
                  <th style={{ padding: "0.85rem 1.15rem", color: "var(--text-secondary)", fontWeight: 650, fontSize: "0.75rem", textTransform: "uppercase", letterSpacing: "0.05em" }}>Status</th>
                  <th style={{ padding: "0.85rem 1.15rem", color: "var(--text-secondary)", fontWeight: 650, fontSize: "0.75rem", textTransform: "uppercase", letterSpacing: "0.05em" }}>Joined</th>
                </tr>
              </thead>
              <tbody>
                {filteredMembers.map((m) => {
                  const initials = ((m.user.full_name || m.user.email || "U")
                    .split(" ")
                    .map((w) => w[0])
                    .join("")
                    .substring(0, 2)
                    .toUpperCase()) || "U";
                  const isActive = m.status === "active";

                  return (
                    <tr
                      key={m.id}
                      className="table-row"
                      style={{
                        borderBottom: "1px solid var(--border-subtle)",
                        transition: "background 0.15s ease",
                      }}
                    >
                      <td style={{ padding: "0.95rem 1.15rem" }}>
                        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                          <div
                            style={{
                              width: 38,
                              height: 38,
                              borderRadius: "50%",
                              background: "linear-gradient(135deg, rgba(56, 103, 245, 0.12), rgba(138, 69, 246, 0.18))",
                              color: "var(--brand-primary, #3867F5)",
                              display: "flex",
                              alignItems: "center",
                              justifyContent: "center",
                              fontWeight: 700,
                              fontSize: "0.82rem",
                              flexShrink: 0,
                              border: "1px solid rgba(56, 103, 245, 0.15)",
                            }}
                          >
                            {initials}
                          </div>
                          <div>
                            <div style={{ fontWeight: 650, color: "var(--text-primary)" }}>{m.user.full_name || m.user.email}</div>
                            <div style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>{m.user.email}</div>
                          </div>
                        </div>
                      </td>
                      <td style={{ padding: "0.95rem 1.15rem" }}>
                        <span
                          style={{
                            padding: "3px 10px",
                            borderRadius: "9999px",
                            fontSize: "0.75rem",
                            fontWeight: 600,
                            background: m.membership_type === "tenant_admin" ? "var(--surface-soft-lavender, #F0EDFF)" : "var(--surface-soft-blue, #EAF4FF)",
                            color: m.membership_type === "tenant_admin" ? "var(--brand-violet, #8A45F6)" : "var(--brand-primary, #3867F5)",
                            border: m.membership_type === "tenant_admin" ? "1px solid rgba(138, 69, 246, 0.25)" : "1px solid rgba(56, 103, 245, 0.2)",
                          }}
                        >
                          {m.membership_type === "tenant_admin" ? "Admin" : "Member"}
                        </span>
                      </td>
                      <td style={{ padding: "0.95rem 1.15rem", color: "var(--text-secondary)", fontWeight: 500 }}>
                        {m.role?.name || "Standard Member"}
                      </td>
                      <td style={{ padding: "0.95rem 1.15rem" }}>
                        <span
                          style={{
                            display: "inline-flex",
                            alignItems: "center",
                            gap: 5,
                            padding: "3px 10px",
                            borderRadius: "9999px",
                            fontSize: "0.75rem",
                            fontWeight: 650,
                            background: isActive ? "var(--surface-soft-mint, #E8FAF2)" : "var(--surface-soft-peach, #FFF3E9)",
                            color: isActive ? "#0FAF83" : "#F59E0B",
                            border: isActive ? "1px solid rgba(15, 175, 131, 0.25)" : "1px solid rgba(245, 158, 11, 0.25)",
                          }}
                        >
                          <span
                            style={{
                              width: 6,
                              height: 6,
                              borderRadius: "50%",
                              background: isActive ? "#0FAF83" : "#F59E0B",
                            }}
                          />
                          {m.status}
                        </span>
                      </td>
                      <td style={{ padding: "0.95rem 1.15rem", color: "var(--text-muted)", fontSize: "0.82rem" }}>
                        {m.joined_at ? new Date(m.joined_at).toLocaleDateString() : "—"}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}

        {currentOrgId && (
          <InviteUserDialog
            isOpen={isInviteOpen}
            onClose={() => setIsInviteOpen(false)}
            defaultOrganizationId={currentOrgId}
            allowedMembershipTypes={["member"]}
            onSuccess={() => {
              void loadMembers();
            }}
          />
        )}
      </div>
    </AppShell>
  );
};
