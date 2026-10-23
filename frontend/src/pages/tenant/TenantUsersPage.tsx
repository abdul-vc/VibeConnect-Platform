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
          <div style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
            {user?.active_context?.effective_permissions?.includes("roles.assign") && (
              <Link
                to="/tenant/member-onboarding"
                className="btn btn-primary"
                style={{ display: "inline-flex", alignItems: "center", gap: 6, padding: "0.45rem 0.9rem", fontSize: "0.82rem", textDecoration: "none" }}
              >
                <PlusIcon size={14} /> Member Onboarding Wizard
              </Link>
            )}
            <button
              type="button"
              onClick={() => setIsInviteOpen(true)}
              className="btn btn-secondary"
              disabled={!currentOrgId}
              style={{ display: "inline-flex", alignItems: "center", gap: 6, padding: "0.45rem 0.9rem", fontSize: "0.82rem" }}
            >
              <UserIcon size={14} /> Quick Invite
            </button>
            <button
              type="button"
              onClick={() => void loadMembers()}
              className="btn-secondary"
              style={{ display: "inline-flex", alignItems: "center", gap: 6, padding: "0.45rem 0.9rem", fontSize: "0.82rem" }}
            >
              <RotateCcwIcon size={14} /> Refresh
            </button>
          </div>
        </div>

        {error && (
          <div style={{ padding: "0.85rem 1rem", background: "rgba(239, 68, 68, 0.1)", border: "1px solid rgba(239, 68, 68, 0.3)", borderRadius: 8, color: "#f87171", marginBottom: "1.25rem", fontSize: "0.88rem" }}>
            {error}
          </div>
        )}

        {/* Filters */}
        <div style={{ display: "flex", gap: "1rem", marginBottom: "1.25rem", flexWrap: "wrap", alignItems: "center" }}>
          <div style={{ position: "relative", flex: 1, minWidth: "240px" }}>
            <span style={{ position: "absolute", left: 12, top: 10, color: "var(--text-muted)" }}>
              <SearchIcon size={16} />
            </span>
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search by name or email…"
              style={{
                width: "100%",
                padding: "0.55rem 0.75rem 0.55rem 2.25rem",
                borderRadius: 8,
                background: "var(--surface-raised, #0f172a)",
                border: "1px solid var(--border-glass, rgba(255, 255, 255, 0.15))",
                color: "var(--text-primary)",
                fontSize: "0.88rem",
                boxSizing: "border-box",
              }}
            />
          </div>

          <div style={{ display: "flex", gap: 6 }}>
            {["", "tenant_admin", "member"].map((type) => (
              <button
                key={type}
                type="button"
                onClick={() => setFilterType(type)}
                style={{
                  padding: "0.45rem 0.9rem",
                  borderRadius: 999,
                  fontSize: "0.78rem",
                  fontWeight: 600,
                  border: filterType === type ? "1.5px solid var(--brand-primary, #6366f1)" : "1px solid var(--border-glass, rgba(255, 255, 255, 0.1))",
                  background: filterType === type ? "rgba(99, 102, 241, 0.15)" : "var(--surface-card, #1e293b)",
                  color: filterType === type ? "var(--brand-primary, #6366f1)" : "var(--text-muted)",
                  cursor: "pointer",
                }}
              >
                {type === "" ? "All Members" : type === "tenant_admin" ? "Admins" : "Regular Members"}
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
              padding: "3rem 1.5rem",
              textAlign: "center",
              color: "var(--text-muted)",
              background: "var(--surface-card, #1e293b)",
              borderRadius: 14,
              border: "1px dashed var(--border-glass, rgba(255, 255, 255, 0.1))",
            }}
          >
            No organization members found matching your search.
          </div>
        ) : (
          <div
            style={{
              background: "var(--surface-card, #1e293b)",
              border: "1px solid var(--border-glass, rgba(255, 255, 255, 0.1))",
              borderRadius: 14,
              overflow: "hidden",
            }}
          >
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.88rem", textAlign: "left" }}>
              <thead>
                <tr style={{ borderBottom: "1px solid var(--border-glass, rgba(255, 255, 255, 0.1))", background: "rgba(0, 0, 0, 0.2)" }}>
                  <th style={{ padding: "0.85rem 1rem", color: "var(--text-muted)", fontWeight: 600 }}>User</th>
                  <th style={{ padding: "0.85rem 1rem", color: "var(--text-muted)", fontWeight: 600 }}>Membership Type</th>
                  <th style={{ padding: "0.85rem 1rem", color: "var(--text-muted)", fontWeight: 600 }}>Role</th>
                  <th style={{ padding: "0.85rem 1rem", color: "var(--text-muted)", fontWeight: 600 }}>Status</th>
                  <th style={{ padding: "0.85rem 1rem", color: "var(--text-muted)", fontWeight: 600 }}>Joined</th>
                </tr>
              </thead>
              <tbody>
                {filteredMembers.map((m) => (
                  <tr
                    key={m.id}
                    style={{
                      borderBottom: "1px solid var(--border-glass, rgba(255, 255, 255, 0.05))",
                    }}
                  >
                    <td style={{ padding: "0.85rem 1rem" }}>
                      <div style={{ fontWeight: 600, color: "var(--text-primary)" }}>{m.user.full_name || m.user.email}</div>
                      <div style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>{m.user.email}</div>
                    </td>
                    <td style={{ padding: "0.85rem 1rem" }}>
                      <span
                        style={{
                          display: "inline-block",
                          padding: "2px 8px",
                          borderRadius: 999,
                          fontSize: "0.72rem",
                          fontWeight: 700,
                          background: m.membership_type === "tenant_admin" ? "rgba(99, 102, 241, 0.15)" : "rgba(148, 163, 184, 0.15)",
                          color: m.membership_type === "tenant_admin" ? "#818cf8" : "#94a3b8",
                          textTransform: "uppercase",
                        }}
                      >
                        {m.membership_type === "tenant_admin" ? "Admin" : "Member"}
                      </span>
                    </td>
                    <td style={{ padding: "0.85rem 1rem", color: "var(--text-secondary)" }}>
                      {m.role?.name || "Standard Member"}
                    </td>
                    <td style={{ padding: "0.85rem 1rem" }}>
                      <span
                        style={{
                          display: "inline-block",
                          padding: "2px 8px",
                          borderRadius: 999,
                          fontSize: "0.72rem",
                          fontWeight: 700,
                          background: m.status === "active" ? "rgba(34, 197, 94, 0.15)" : "rgba(239, 68, 68, 0.15)",
                          color: m.status === "active" ? "#4ade80" : "#f87171",
                          textTransform: "capitalize",
                        }}
                      >
                        {m.status}
                      </span>
                    </td>
                    <td style={{ padding: "0.85rem 1rem", color: "var(--text-muted)", fontSize: "0.8rem" }}>
                      {m.joined_at ? new Date(m.joined_at).toLocaleDateString() : "—"}
                    </td>
                  </tr>
                ))}
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
