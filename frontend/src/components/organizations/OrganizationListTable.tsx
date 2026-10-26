/**
 * Organization List Table & Mobile Card View Component.
 *
 * Renders the organization catalog in a high-density, accessible desktop table
 * and responsive mobile card layout with disabled edit controls for retired records.
 */

import React from "react";
import { Link } from "react-router-dom";
import type { OrganizationListItem } from "../../api/types.ts";
import { EditIcon } from "../Icons.tsx";
import { OrganizationStatusBadge } from "./OrganizationStatusBadge.tsx";

interface OrganizationListTableProps {
  readonly organizations: readonly OrganizationListItem[];
  readonly onEdit: (organization: OrganizationListItem, triggerElement: HTMLElement) => void;
}

export const OrganizationListTable: React.FC<OrganizationListTableProps> = ({
  organizations,
  onEdit,
}) => {
  const formatDate = (dateStr: string) => {
    try {
      return new Date(dateStr).toLocaleDateString("en-US", {
        month: "short",
        day: "numeric",
        year: "numeric",
      });
    } catch {
      return dateStr;
    }
  };

  return (
    <div className="organizations-table-container">
      {/* Desktop Table View */}
      <div className="desktop-table-view">
        <table className="data-table" aria-label="Organization Catalog">
          <thead>
            <tr>
              <th scope="col" style={{ width: "18%" }}>
                Organization Code
              </th>
              <th scope="col" style={{ width: "38%" }}>
                Name &amp; Description
              </th>
              <th scope="col" style={{ width: "16%" }}>
                Status
              </th>
              <th scope="col" style={{ width: "16%" }}>
                Registered
              </th>
              <th scope="col" style={{ width: "12%", textAlign: "right" }}>
                Actions
              </th>
            </tr>
          </thead>
          <tbody>
            {organizations.map((org) => {
              const isRetired = org.status === "retired";
              return (
                <tr key={org.id} className="table-row">
                  <td>
                    <span className="code-pill">{org.code}</span>
                  </td>
                  <td>
                    <div style={{ display: "flex", flexDirection: "column", gap: "0.2rem" }}>
                      <span style={{ fontWeight: 600, color: "var(--text-primary)" }}>{org.name}</span>
                      {org.description ? (
                        <span
                          style={{
                            fontSize: "0.8125rem",
                            color: "var(--text-secondary)",
                            lineHeight: 1.4,
                            maxWidth: "480px",
                          }}
                        >
                          {org.description}
                        </span>
                      ) : (
                        <span style={{ fontSize: "0.8125rem", color: "var(--text-muted)", fontStyle: "italic" }}>
                          No description provided
                        </span>
                      )}
                    </div>
                  </td>
                  <td>
                    <OrganizationStatusBadge status={org.status} />
                  </td>
                  <td>
                    <span style={{ fontSize: "0.8125rem", color: "var(--text-secondary)" }}>
                      {formatDate(org.created_at)}
                    </span>
                  </td>
                  <td style={{ textAlign: "right" }}>
                    <div style={{ display: "inline-flex", gap: "0.5rem", justifyContent: "flex-end", alignItems: "center" }}>
                      <Link
                        to={`/organizations/${org.id}`}
                        className="btn-gradient"
                        style={{
                          padding: "0.35rem 0.85rem",
                          fontSize: "0.75rem",
                          borderRadius: "8px",
                          fontWeight: 700,
                          textDecoration: "none",
                          display: "inline-flex",
                          alignItems: "center",
                        }}
                        aria-label={`View ${org.name}`}
                      >
                        View
                      </Link>
                      <button
                        type="button"
                        className="btn btn-secondary btn-sm"
                        onClick={(e) => onEdit(org, e.currentTarget)}
                        disabled={isRetired}
                        title={isRetired ? "Retired organizations are permanently closed and cannot be modified." : "Edit organization"}
                        aria-label={isRetired ? `Edit disabled: ${org.name} is retired` : `Edit ${org.name}`}
                        style={{
                          padding: "0.35rem 0.75rem",
                          fontSize: "0.75rem",
                          borderRadius: "8px",
                          opacity: isRetired ? 0.45 : 1,
                          cursor: isRetired ? "not-allowed" : "pointer",
                        }}
                      >
                        <EditIcon size={13} />
                        <span>Edit</span>
                      </button>
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Mobile Cards View (<768px) */}
      <div className="mobile-cards-view">
        {organizations.map((org) => {
          const isRetired = org.status === "retired";
          return (
            <div key={org.id} className="mobile-org-card">
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: "0.5rem" }}>
                <span className="code-pill">{org.code}</span>
                <OrganizationStatusBadge status={org.status} />
              </div>

              <div>
                <h3 style={{ fontSize: "1rem", fontWeight: 600, color: "var(--text-primary)", margin: "0.25rem 0 0.15rem 0" }}>
                  {org.name}
                </h3>
                {org.description && (
                  <p style={{ fontSize: "0.8125rem", color: "var(--text-secondary)", margin: 0, lineHeight: 1.4 }}>
                    {org.description}
                  </p>
                )}
              </div>

              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  paddingTop: "0.75rem",
                  borderTop: "1px solid var(--border-subtle)",
                  marginTop: "0.5rem",
                  gap: "0.5rem",
                  flexWrap: "wrap",
                }}
              >
                <span style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
                  Registered {formatDate(org.created_at)}
                </span>
                <div style={{ display: "flex", gap: "0.5rem" }}>
                  <Link
                    to={`/organizations/${org.id}`}
                    className="btn-gradient"
                    style={{
                      padding: "0.35rem 0.75rem",
                      fontSize: "0.75rem",
                      borderRadius: "8px",
                      textDecoration: "none",
                      fontWeight: 700,
                    }}
                    aria-label={`View ${org.name}`}
                  >
                    View
                  </Link>
                  <button
                    type="button"
                    className="btn btn-secondary btn-sm"
                    onClick={(e) => onEdit(org, e.currentTarget)}
                    disabled={isRetired}
                    title={isRetired ? "Retired organizations cannot be modified." : "Edit organization"}
                    aria-label={isRetired ? `Edit disabled: ${org.name} is retired` : `Edit ${org.name}`}
                    style={{ opacity: isRetired ? 0.45 : 1, borderRadius: "8px", fontSize: "0.75rem" }}
                  >
                    <EditIcon size={13} />
                    <span>Edit</span>
                  </button>
                </div>
              </div>
            </div>
          );
        })}
      </div>

      <style>{`
        .organizations-table-container {
          width: 100%;
          min-width: 0;
        }

        .desktop-table-view {
          display: block;
          overflow-x: auto;
          background: var(--glass-surface-elevated);
          border: 1px solid var(--border-glass);
          border-radius: 12px;
          box-shadow: var(--shadow-sm);
        }

        .data-table {
          width: 100%;
          border-collapse: collapse;
          text-align: left;
          font-size: 0.875rem;
        }

        .data-table th {
          padding: 0.875rem 1.25rem;
          font-weight: 600;
          font-size: 0.75rem;
          text-transform: uppercase;
          letter-spacing: 0.05em;
          color: var(--text-muted);
          border-bottom: 1px solid var(--border-subtle);
          background: var(--glass-surface);
        }

        .data-table td {
          padding: 1rem 1.25rem;
          border-bottom: 1px solid var(--border-subtle);
          vertical-align: middle;
        }

        .table-row:last-child td {
          border-bottom: none;
        }

        .table-row:hover {
          background: var(--glass-surface-hover);
        }

        .code-pill {
          display: inline-block;
          font-family: var(--font-code);
          font-size: 0.75rem;
          padding: 0.25rem 0.5rem;
          border-radius: 6px;
          background: var(--brand-primary-light);
          color: var(--brand-primary);
          border: 1px solid var(--border-glass);
          font-weight: 600;
          letter-spacing: -0.02em;
        }

        .mobile-cards-view {
          display: none;
          flex-direction: column;
          gap: 0.75rem;
        }

        .mobile-org-card {
          background: var(--glass-surface-elevated);
          border: 1px solid var(--border-glass);
          border-radius: 12px;
          padding: 1rem;
          display: flex;
          flex-direction: column;
          gap: 0.625rem;
          box-shadow: var(--shadow-sm);
        }

        @media (max-width: 768px) {
          .desktop-table-view {
            display: none;
          }
          .mobile-cards-view {
            display: flex;
          }
        }
      `}</style>
    </div>
  );
};
