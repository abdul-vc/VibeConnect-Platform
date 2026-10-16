/**
 * Entitlement List Table & Mobile Card View Component.
 *
 * Renders the organization-product entitlement catalog in a high-density, accessible desktop table
 * and responsive mobile card layout with disabled/read-only treatment for revoked records.
 */

import React from "react";
import type { EntitlementListItem } from "../../api/types.ts";
import { formatDateTime } from "../../config/dateUtils.ts";
import { EditIcon } from "../Icons.tsx";
import { EntitlementStatusBadge } from "./EntitlementStatusBadge.tsx";

interface EntitlementListTableProps {
  readonly entitlements: readonly EntitlementListItem[];
  readonly onEdit: (entitlement: EntitlementListItem, triggerElement: HTMLElement) => void;
}

export const EntitlementListTable: React.FC<EntitlementListTableProps> = ({
  entitlements,
  onEdit,
}) => {
  return (
    <div className="entitlements-table-container">
      {/* Desktop Table View */}
      <div className="desktop-table-view">
        <table className="data-table" aria-label="Organization Product Access Catalog">
          <thead>
            <tr>
              <th scope="col" style={{ width: "32%" }}>
                Organization
              </th>
              <th scope="col" style={{ width: "28%" }}>
                Product
              </th>
              <th scope="col" style={{ width: "14%" }}>
                Status
              </th>
              <th scope="col" style={{ width: "14%" }}>
                Created At
              </th>
              <th scope="col" style={{ width: "12%", textAlign: "right" }}>
                Actions
              </th>
            </tr>
          </thead>
          <tbody>
            {entitlements.map((ent) => {
              const isRevoked = ent.status === "revoked";
              const revokedDescId = `revoked-desc-${ent.id}`;

              return (
                <tr key={ent.id} className="table-row">
                  <td>
                    <div style={{ display: "flex", flexDirection: "column", gap: "0.25rem" }}>
                      <span style={{ fontWeight: 600, color: "var(--text-primary)" }}>
                        {ent.organization.name}
                      </span>
                      <div>
                        <span className="code-pill">{ent.organization.code}</span>
                      </div>
                    </div>
                  </td>
                  <td>
                    <div style={{ display: "flex", flexDirection: "column", gap: "0.25rem" }}>
                      <span style={{ fontWeight: 600, color: "var(--text-primary)" }}>
                        {ent.product.name}
                      </span>
                      <div>
                        <span className="code-pill">{ent.product.code}</span>
                      </div>
                    </div>
                  </td>
                  <td>
                    <EntitlementStatusBadge status={ent.status} />
                  </td>
                  <td>
                    <span style={{ fontSize: "0.8125rem", color: "var(--text-secondary)" }} title={ent.created_at}>
                      {formatDateTime(ent.created_at)}
                    </span>
                  </td>
                  <td style={{ textAlign: "right" }}>
                    {isRevoked ? (
                      <div>
                        <button
                          type="button"
                          className="btn btn-secondary btn-sm disabled-action-btn"
                          disabled={true}
                          aria-describedby={revokedDescId}
                          style={{
                            padding: "0.35rem 0.65rem",
                            opacity: 0.45,
                            cursor: "not-allowed",
                          }}
                        >
                          <EditIcon size={14} />
                          <span>Edit</span>
                        </button>
                        <span id={revokedDescId} className="sr-only">
                          Revoked access records are permanently closed.
                        </span>
                      </div>
                    ) : (
                      <button
                        type="button"
                        className="btn btn-secondary btn-sm"
                        onClick={(e) => onEdit(ent, e.currentTarget)}
                        title="Update lifecycle status"
                        aria-label={`Edit product access for ${ent.organization.name} - ${ent.product.name}`}
                        style={{ padding: "0.35rem 0.65rem" }}
                      >
                        <EditIcon size={14} />
                        <span>Edit</span>
                      </button>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Mobile Cards View (<768px) */}
      <div className="mobile-cards-view">
        {entitlements.map((ent) => {
          const isRevoked = ent.status === "revoked";
          const mobileRevokedDescId = `mobile-revoked-desc-${ent.id}`;

          return (
            <div key={ent.id} className="mobile-entitlement-card">
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: "0.5rem" }}>
                <div>
                  <span style={{ fontSize: "0.75rem", color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.05em" }}>
                    Organization
                  </span>
                  <h3 style={{ fontSize: "0.9375rem", fontWeight: 600, color: "var(--text-primary)", margin: "0.15rem 0 0.25rem 0" }}>
                    {ent.organization.name}
                  </h3>
                  <span className="code-pill">{ent.organization.code}</span>
                </div>
                <EntitlementStatusBadge status={ent.status} />
              </div>

              <div style={{ paddingTop: "0.5rem", borderTop: "1px solid var(--border-subtle)" }}>
                <span style={{ fontSize: "0.75rem", color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.05em" }}>
                  Product
                </span>
                <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginTop: "0.15rem" }}>
                  <span style={{ fontSize: "0.875rem", fontWeight: 600, color: "var(--text-primary)" }}>
                    {ent.product.name}
                  </span>
                  <span className="code-pill">{ent.product.code}</span>
                </div>
              </div>

              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  paddingTop: "0.75rem",
                  borderTop: "1px solid var(--border-subtle)",
                  marginTop: "0.25rem",
                }}
              >
                <span style={{ fontSize: "0.75rem", color: "var(--text-muted)" }} title={ent.created_at}>
                  Created At: {formatDateTime(ent.created_at)}
                </span>
                {isRevoked ? (
                  <div>
                    <button
                      type="button"
                      className="btn btn-secondary btn-sm disabled-action-btn"
                      disabled={true}
                      aria-describedby={mobileRevokedDescId}
                      style={{ opacity: 0.45, cursor: "not-allowed", minHeight: "44px", display: "inline-flex", alignItems: "center" }}
                    >
                      <EditIcon size={14} />
                      <span>Edit</span>
                    </button>
                    <span id={mobileRevokedDescId} className="sr-only">
                      Revoked access records are permanently closed.
                    </span>
                  </div>
                ) : (
                  <button
                    type="button"
                    className="btn btn-secondary btn-sm"
                    style={{ minHeight: "44px", display: "inline-flex", alignItems: "center" }}
                    onClick={(e) => onEdit(ent, e.currentTarget)}
                    title="Update lifecycle status"
                    aria-label={`Edit product access for ${ent.organization.name} - ${ent.product.name}`}
                  >
                    <EditIcon size={14} />
                    <span>Edit</span>
                  </button>
                )}
              </div>
            </div>
          );
        })}
      </div>

      <style>{`
        .entitlements-table-container {
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
          padding: 0.2rem 0.45rem;
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

        .mobile-entitlement-card {
          background: var(--glass-surface-elevated);
          border: 1px solid var(--border-glass);
          border-radius: 12px;
          padding: 1rem;
          display: flex;
          flex-direction: column;
          gap: 0.625rem;
          box-shadow: var(--shadow-sm);
        }

        .sr-only {
          position: absolute;
          width: 1px;
          height: 1px;
          padding: 0;
          margin: -1px;
          overflow: hidden;
          clip: rect(0, 0, 0, 0);
          white-space: nowrap;
          border: 0;
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
