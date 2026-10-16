/**
 * Audit Log Table Component.
 *
 * Enterprise data table for desktop/tablet viewports (>=768px) and
 * responsive card list for mobile viewports (<768px) down to 320px.
 * Follows VibeConnect Apple-inspired Liquid Glass design standards.
 */

import React from "react";
import type { AuditLogListItem, AuditOperationSource } from "../../api/types.ts";
import {
  AUDIT_ACTION_LABELS as ACTION_LABELS,
  AUDIT_TARGET_TYPE_LABELS as TARGET_TYPE_LABELS,
  getAuditActionBadgeClass as getActionBadgeClass,
  formatUtcDateTime,
} from "../../api/audit.ts";
import { EyeIcon } from "../Icons.tsx";

interface AuditLogTableProps {
  readonly logs: readonly AuditLogListItem[];
  readonly onSelectLog: (log: AuditLogListItem, triggerElement: HTMLElement) => void;
  readonly isLoading?: boolean;
}

const SOURCE_LABELS: Record<AuditOperationSource, string> = {
  interactive: "Interactive",
  authentication: "Authentication",
  bulk_import: "Bulk Import",
  integration: "Integration",
};

export const AuditLogTable: React.FC<AuditLogTableProps> = ({ logs, onSelectLog, isLoading = false }) => {
  return (
    <div className="audit-table-container">
      {/* Desktop & Tablet Table (>=768px) */}
      <div className="table-responsive desktop-view">
        <table className="enterprise-table" aria-label="System Activity Logs">
          <thead>
            <tr>
              <th scope="col" style={{ width: "16%" }}>Timestamp (UTC)</th>
              <th scope="col" style={{ width: "15%" }}>Action</th>
              <th scope="col" style={{ width: "19%" }}>Target</th>
              <th scope="col" style={{ width: "17%" }}>Actor</th>
              <th scope="col" style={{ width: "11%" }}>Organization</th>
              <th scope="col" style={{ width: "11%" }}>Source</th>
              <th scope="col" style={{ width: "11%", textAlign: "right" }}>Details</th>
            </tr>
          </thead>
          <tbody>
            {logs.map((log) => {
              const actionLabel = ACTION_LABELS[log.action] ?? log.action;
              const badgeClass = getActionBadgeClass(log.action);
              const targetType = TARGET_TYPE_LABELS[log.target_type] ?? log.target_type;
              const sourceLabel = SOURCE_LABELS[log.operation_source] ?? log.operation_source;
              const formattedTime = formatUtcDateTime(log.timestamp);

              return (
                <tr key={log.id} className="table-row">
                  <td>
                    <span className="audit-timestamp" title={log.timestamp}>
                      {formattedTime}
                    </span>
                  </td>
                  <td>
                    <span className={`badge ${badgeClass}`}>
                      {actionLabel}
                    </span>
                  </td>
                  <td>
                    <div className="audit-target-col">
                      <span className="audit-target-repr" title={log.target_repr}>
                        {log.target_repr || "—"}
                      </span>
                      <span className="text-caption audit-target-type">
                        {targetType}
                      </span>
                    </div>
                  </td>
                  <td>
                    <div className="audit-actor-col">
                      <span className="audit-actor-name">
                        {log.actor.full_name || "System"}
                      </span>
                      <span className="text-caption audit-actor-email" title={log.actor.email}>
                        {log.actor.email || "—"}
                      </span>
                    </div>
                  </td>
                  <td>
                    {log.organization_id ? (
                      <span
                        className="audit-org-id"
                        title={log.organization_id}
                      >
                        {log.organization_id.substring(0, 8)}...
                      </span>
                    ) : (
                      <span className="text-muted">—</span>
                    )}
                  </td>
                  <td>
                    <span className="badge badge-neutral audit-source-badge">
                      {sourceLabel}
                    </span>
                  </td>
                  <td style={{ textAlign: "right" }}>
                    <button
                      type="button"
                      className="btn-secondary audit-action-btn"
                      onClick={(e) => onSelectLog(log, e.currentTarget)}
                      aria-label={`View details for ${actionLabel} at ${formattedTime}`}
                      disabled={isLoading}
                    >
                      <EyeIcon size={14} />
                      <span>Details</span>
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Mobile Card View (<768px) */}
      <div className="mobile-card-list">
        {logs.map((log) => {
          const actionLabel = ACTION_LABELS[log.action] ?? log.action;
          const badgeClass = getActionBadgeClass(log.action);
          const targetType = TARGET_TYPE_LABELS[log.target_type] ?? log.target_type;
          const sourceLabel = SOURCE_LABELS[log.operation_source] ?? log.operation_source;
          const formattedTime = formatUtcDateTime(log.timestamp);

          return (
            <div key={log.id} className="mobile-audit-card">
              <div className="mobile-card-header">
                <span className={`badge ${badgeClass}`}>
                  {actionLabel}
                </span>
                <span className="badge badge-neutral mobile-source-badge" title={`Operation Source: ${sourceLabel}`}>
                  {sourceLabel}
                </span>
              </div>

              <div className="mobile-card-body">
                <div className="mobile-field-row">
                  <span className="mobile-field-label">Target:</span>
                  <span className="mobile-field-value audit-target-repr" title={log.target_repr}>
                    {log.target_repr || "—"} <span className="text-caption">({targetType})</span>
                  </span>
                </div>
                <div className="mobile-field-row">
                  <span className="mobile-field-label">Actor:</span>
                  <span className="mobile-field-value">
                    {log.actor.full_name || "System"}{" "}
                    {log.actor.email && <span className="text-caption">({log.actor.email})</span>}
                  </span>
                </div>
                <div className="mobile-field-row">
                  <span className="mobile-field-label">Source:</span>
                  <span className="mobile-field-value">
                    <span className="badge badge-neutral mobile-source-badge">
                      {sourceLabel}
                    </span>
                  </span>
                </div>
                {log.organization_id && (
                  <div className="mobile-field-row">
                    <span className="mobile-field-label">Org ID:</span>
                    <span className="mobile-field-value font-mono">
                      {log.organization_id.substring(0, 8)}...
                    </span>
                  </div>
                )}
                <div className="mobile-field-row">
                  <span className="mobile-field-label">Time:</span>
                  <span className="mobile-field-value text-caption">
                    {formattedTime}
                  </span>
                </div>
              </div>

              <div className="mobile-card-footer">
                <button
                  type="button"
                  className="btn-secondary mobile-details-btn"
                  onClick={(e) => onSelectLog(log, e.currentTarget)}
                  aria-label={`View details for ${actionLabel} at ${formattedTime}`}
                  disabled={isLoading}
                >
                  <EyeIcon size={16} />
                  <span>View Details</span>
                </button>
              </div>
            </div>
          );
        })}
      </div>

      <style>{`
        .audit-table-container {
          background: var(--glass-surface-elevated);
          border: 1px solid var(--border-glass);
          border-radius: 14px;
          overflow: hidden;
          box-shadow: var(--shadow-sm);
        }

        .table-responsive {
          width: 100%;
          overflow-x: auto;
        }

        .enterprise-table {
          width: 100%;
          border-collapse: collapse;
          text-align: left;
          font-size: 0.875rem;
        }

        .enterprise-table thead th {
          background: var(--glass-surface-sunken);
          padding: 0.875rem 1.25rem;
          font-size: 0.75rem;
          font-weight: 600;
          color: var(--text-secondary);
          text-transform: uppercase;
          letter-spacing: 0.04em;
          border-bottom: 1px solid var(--border-subtle);
          white-space: nowrap;
        }

        .enterprise-table tbody td {
          padding: 0.875rem 1.25rem;
          border-bottom: 1px solid var(--border-subtle);
          vertical-align: middle;
        }

        .table-row:last-child td {
          border-bottom: none;
        }

        .table-row:hover {
          background: var(--glass-surface-hover);
        }

        .audit-timestamp {
          font-family: var(--font-code);
          font-size: 0.8125rem;
          color: var(--text-primary);
          white-space: nowrap;
        }

        .audit-target-col,
        .audit-actor-col {
          display: flex;
          flex-direction: column;
          gap: 0.15rem;
        }

        .audit-target-repr {
          font-weight: 600;
          color: var(--text-primary);
          max-width: 260px;
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }

        .audit-target-type {
          color: var(--text-muted);
        }

        .audit-actor-name {
          font-weight: 600;
          color: var(--text-primary);
        }

        .audit-actor-email {
          color: var(--text-secondary);
          max-width: 200px;
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }

        .audit-org-id {
          font-family: var(--font-code);
          font-size: 0.8125rem;
          color: var(--text-secondary);
          background: var(--glass-surface-sunken);
          padding: 0.15rem 0.45rem;
          border-radius: 4px;
          border: 1px solid var(--border-subtle);
        }

        .audit-source-badge {
          font-size: 0.75rem;
          white-space: nowrap;
        }

        .audit-action-btn {
          min-height: 44px;
          min-width: 44px;
          padding: 0.5rem 0.875rem;
          display: inline-flex;
          align-items: center;
          justify-content: center;
          gap: 0.375rem;
          font-size: 0.8125rem;
        }

        /* Mobile Card View (<768px) */
        .mobile-card-list {
          display: none;
          flex-direction: column;
          gap: 0.875rem;
          padding: 0.875rem;
        }

        .mobile-audit-card {
          background: var(--glass-surface);
          border: 1px solid var(--border-subtle);
          border-radius: 12px;
          padding: 1rem;
          display: flex;
          flex-direction: column;
          gap: 0.75rem;
          box-shadow: var(--shadow-sm);
        }

        .mobile-card-header {
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 0.5rem;
        }

        .mobile-source-badge {
          font-size: 0.6875rem;
        }

        .mobile-card-body {
          display: flex;
          flex-direction: column;
          gap: 0.4rem;
        }

        .mobile-field-row {
          display: flex;
          align-items: baseline;
          gap: 0.5rem;
          font-size: 0.8125rem;
        }

        .mobile-field-label {
          font-weight: 600;
          color: var(--text-muted);
          min-width: 60px;
          flex-shrink: 0;
        }

        .mobile-field-value {
          color: var(--text-primary);
          word-break: break-word;
        }

        .mobile-card-footer {
          padding-top: 0.75rem;
          border-top: 1px solid var(--border-subtle);
        }

        .mobile-details-btn {
          width: 100%;
          min-height: 44px;
          display: flex;
          align-items: center;
          justify-content: center;
          gap: 0.5rem;
          font-size: 0.875rem;
        }

        @media (max-width: 767px) {
          .desktop-view {
            display: none;
          }
          .mobile-card-list {
            display: flex;
          }
        }
      `}</style>
    </div>
  );
};
