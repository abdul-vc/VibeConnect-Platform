/**
 * Audit Detail Dialog Component.
 *
 * Accessible modal dialog displaying the full immutable audit event,
 * snapshot actor attributes, domain target context, and safely rendered metadata.
 */

import React, { useEffect, useRef, useState } from "react";
import {
  AUDIT_ACTION_LABELS as ACTION_LABELS,
  AUDIT_TARGET_TYPE_LABELS as TARGET_TYPE_LABELS,
  getAuditActionBadgeClass as getActionBadgeClass,
  auditApi,
  formatUtcDateTime,
} from "../../api/audit.ts";
import { ApiError } from "../../api/client.ts";
import type { AuditLogDetail } from "../../api/types.ts";
import { CloseIcon, RotateCcwIcon } from "../Icons.tsx";

interface AuditDetailDialogProps {
  readonly logId: string | null;
  readonly isOpen: boolean;
  readonly onClose: () => void;
}

interface MetadataViewerProps {
  readonly data: unknown;
  readonly depth?: number;
  readonly maxDepth?: number;
}

const SafeMetadataViewer: React.FC<MetadataViewerProps> = ({
  data,
  depth = 0,
  maxDepth = 3,
}) => {
  if (data === null || data === undefined) {
    return <span className="meta-val-null">null</span>;
  }

  if (typeof data === "boolean") {
    return <span className="meta-val-bool">{data ? "true" : "false"}</span>;
  }

  if (typeof data === "number") {
    return <span className="meta-val-number">{data}</span>;
  }

  if (typeof data === "string") {
    return <span className="meta-val-string">"{data}"</span>;
  }

  if (depth >= maxDepth) {
    return <span className="meta-val-truncated">[Nested Object]</span>;
  }

  if (Array.isArray(data)) {
    if (data.length === 0) {
      return <span className="meta-val-empty">[]</span>;
    }
    return (
      <div className="meta-array-block">
        {data.map((item, index) => (
          <div key={index} className="meta-array-item">
            <span className="meta-index-label">[{index}]:</span>
            <SafeMetadataViewer data={item} depth={depth + 1} maxDepth={maxDepth} />
          </div>
        ))}
      </div>
    );
  }

  if (typeof data === "object") {
    const entries = Object.entries(data as Record<string, unknown>);
    if (entries.length === 0) {
      return <span className="meta-val-empty">{"{}"}</span>;
    }
    return (
      <div className="meta-object-block">
        {entries.map(([key, val]) => (
          <div key={key} className="meta-object-row">
            <span className="meta-object-key">{key}:</span>
            <div className="meta-object-val">
              <SafeMetadataViewer data={val} depth={depth + 1} maxDepth={maxDepth} />
            </div>
          </div>
        ))}
      </div>
    );
  }

  return <span className="meta-val-string">{String(data)}</span>;
};

export const AuditDetailDialog: React.FC<AuditDetailDialogProps> = ({
  logId,
  isOpen,
  onClose,
}) => {
  const [detail, setDetail] = useState<AuditLogDetail | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const detailAbortControllerRef = useRef<AbortController | null>(null);
  const detailSeqRef = useRef<number>(0);
  const dialogRef = useRef<HTMLDivElement | null>(null);
  const closeButtonRef = useRef<HTMLButtonElement | null>(null);

  // Fetch detail data with sequence guards and abort controllers
  const fetchDetail = () => {
    if (!logId) return;

    detailAbortControllerRef.current?.abort();
    const currentSeq = ++detailSeqRef.current;
    const controller = new AbortController();
    detailAbortControllerRef.current = controller;

    setIsLoading(true);
    setError(null);

    auditApi
      .get(logId, controller.signal)
      .then((data) => {
        if (controller.signal.aborted || currentSeq !== detailSeqRef.current) return;
        setDetail(data);
        setIsLoading(false);
      })
      .catch((err: unknown) => {
        if (controller.signal.aborted || currentSeq !== detailSeqRef.current) return;
        const msg = err instanceof ApiError ? err.message : "Failed to load audit event details.";
        setError(msg);
        setIsLoading(false);
      });
  };

  useEffect(() => {
    if (isOpen && logId) {
      fetchDetail();
    } else {
      detailAbortControllerRef.current?.abort();
      detailSeqRef.current++;
      setDetail(null);
      setError(null);
      setIsLoading(false);
    }

    return () => {
      detailAbortControllerRef.current?.abort();
      detailSeqRef.current++;
    };
  }, [isOpen, logId]);

  // Exact body-scroll locking and previous value restoration
  useEffect(() => {
    if (!isOpen) return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    return () => {
      document.body.style.overflow = previousOverflow;
    };
  }, [isOpen]);

  // Focus trap, Escape key listener, and initial focus
  useEffect(() => {
    if (!isOpen) return;

    // Focus close button on mount
    const timer = setTimeout(() => {
      closeButtonRef.current?.focus();
    }, 50);

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        onClose();
        return;
      }

      if (e.key === "Tab" && dialogRef.current) {
        const focusableElements = dialogRef.current.querySelectorAll<HTMLElement>(
          'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
        );
        if (focusableElements.length === 0) return;

        const firstElement = focusableElements[0];
        const lastElement = focusableElements[focusableElements.length - 1];

        if (e.shiftKey) {
          if (document.activeElement === firstElement) {
            e.preventDefault();
            lastElement.focus();
          }
        } else {
          if (document.activeElement === lastElement) {
            e.preventDefault();
            firstElement.focus();
          }
        }
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => {
      clearTimeout(timer);
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  const handleBackdropClick = (e: React.MouseEvent<HTMLDivElement>) => {
    if (e.target === e.currentTarget) {
      onClose();
    }
  };

  return (
    <div
      className="audit-dialog-backdrop"
      onClick={handleBackdropClick}
      role="presentation"
    >
      <div
        className="audit-dialog-container"
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="audit-detail-title"
      >
        {/* Header */}
        <div className="audit-dialog-header">
          <div className="audit-dialog-header-info">
            <div className="audit-dialog-title-row">
              <h2 id="audit-detail-title" className="heading-subtitle">
                Audit Event Details
              </h2>
              {detail && (
                <span className={`badge ${getActionBadgeClass(detail.action)}`}>
                  {ACTION_LABELS[detail.action] ?? detail.action}
                </span>
              )}
            </div>
            <span className="text-caption font-mono audit-dialog-id">
              Event ID: {detail ? detail.id : logId}
            </span>
          </div>
          <button
            type="button"
            className="btn-ghost audit-dialog-close-btn"
            onClick={onClose}
            aria-label="Close details dialog"
            ref={closeButtonRef}
          >
            <CloseIcon size={20} />
          </button>
        </div>

        {/* Content Body */}
        <div className="audit-dialog-body">
          {isLoading && (
            <div className="audit-dialog-loading">
              <span className="spinner-icon" style={{ display: "inline-block", width: "24px", height: "24px" }}>
                <RotateCcwIcon size={24} />
              </span>
              <p className="text-body">Loading immutable event data...</p>
            </div>
          )}

          {!isLoading && error && (
            <div className="alert-box alert-danger">
              <div>
                <p style={{ fontWeight: 600, marginBottom: "0.25rem" }}>Error Loading Detail</p>
                <p>{error}</p>
                <button
                  type="button"
                  className="btn-secondary"
                  style={{ marginTop: "0.75rem", minHeight: "36px" }}
                  onClick={fetchDetail}
                >
                  <RotateCcwIcon size={14} />
                  <span>Retry</span>
                </button>
              </div>
            </div>
          )}

          {!isLoading && !error && detail && (
            <div className="audit-dialog-sections">
              {/* Event Metadata */}
              <div className="audit-detail-section">
                <h3 className="audit-section-title">Event Information</h3>
                <div className="audit-detail-grid">
                  <div className="audit-detail-item">
                    <span className="audit-item-label">Action:</span>
                    <span className="audit-item-value">{ACTION_LABELS[detail.action] ?? detail.action}</span>
                  </div>
                  <div className="audit-detail-item">
                    <span className="audit-item-label">Timestamp (UTC):</span>
                    <span className="audit-item-value font-mono">{formatUtcDateTime(detail.timestamp)}</span>
                  </div>
                  <div className="audit-detail-item">
                    <span className="audit-item-label">Operation Source:</span>
                    <span className="audit-item-value">{detail.operation_source}</span>
                  </div>
                  <div className="audit-detail-item">
                    <span className="audit-item-label">Correlation ID:</span>
                    <span className="audit-item-value font-mono">{detail.correlation_id || "—"}</span>
                  </div>
                </div>
              </div>

              {/* Actor Snapshot */}
              <div className="audit-detail-section">
                <h3 className="audit-section-title">Actor Snapshot</h3>
                <div className="audit-detail-grid">
                  <div className="audit-detail-item">
                    <span className="audit-item-label">Full Name:</span>
                    <span className="audit-item-value">{detail.actor.full_name || "System"}</span>
                  </div>
                  <div className="audit-detail-item">
                    <span className="audit-item-label">Email:</span>
                    <span className="audit-item-value font-mono">{detail.actor.email || "—"}</span>
                  </div>
                  <div className="audit-detail-item">
                    <span className="audit-item-label">Actor ID:</span>
                    <span className="audit-item-value font-mono">{detail.actor.id || "—"}</span>
                  </div>
                </div>
              </div>

              {/* Target Information */}
              <div className="audit-detail-section">
                <h3 className="audit-section-title">Target Context</h3>
                <div className="audit-detail-grid">
                  <div className="audit-detail-item">
                    <span className="audit-item-label">Target Type:</span>
                    <span className="audit-item-value">{TARGET_TYPE_LABELS[detail.target_type] ?? detail.target_type}</span>
                  </div>
                  <div className="audit-detail-item">
                    <span className="audit-item-label">Target ID:</span>
                    <span className="audit-item-value font-mono" style={{ overflowWrap: "anywhere", wordBreak: "break-all" }} title={detail.target_id}>{detail.target_id}</span>
                  </div>
                  <div className="audit-detail-item" style={{ gridColumn: "1 / -1" }}>
                    <span className="audit-item-label">Representation:</span>
                    <span className="audit-item-value" style={{ overflowWrap: "anywhere", wordBreak: "break-word" }} title={detail.target_repr}>{detail.target_repr || "—"}</span>
                  </div>
                  <div className="audit-detail-item">
                    <span className="audit-item-label">Organization ID:</span>
                    <span className="audit-item-value font-mono" style={{ overflowWrap: "anywhere", wordBreak: "break-all" }} title={detail.organization_id || undefined}>{detail.organization_id || "—"}</span>
                  </div>
                </div>
              </div>

              {/* Allowlisted Event Metadata */}
              <div className="audit-detail-section">
                <h3 className="audit-section-title">Allowlisted Event Metadata</h3>
                <div className="metadata-viewer-container">
                  {detail.metadata && Object.keys(detail.metadata).length > 0 ? (
                    <SafeMetadataViewer data={detail.metadata} />
                  ) : (
                    <span className="text-caption text-muted">No additional metadata recorded for this event.</span>
                  )}
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="audit-dialog-footer">
          <button
            type="button"
            className="btn-secondary audit-dialog-close-action"
            onClick={onClose}
          >
            Close
          </button>
        </div>
      </div>

      <style>{`
        .audit-dialog-backdrop {
          position: fixed;
          inset: 0;
          z-index: 50;
          background: rgba(7, 11, 20, 0.75);
          backdrop-filter: blur(8px);
          -webkit-backdrop-filter: blur(8px);
          display: flex;
          align-items: center;
          justify-content: center;
          padding: 1rem;
          overflow-y: auto;
        }

        .audit-dialog-container {
          background: var(--glass-surface-elevated);
          border: 1px solid var(--border-glass);
          border-radius: 16px;
          box-shadow: var(--shadow-lg), var(--glass-inner-rim);
          width: 100%;
          max-width: 680px;
          max-height: 90vh;
          display: flex;
          flex-direction: column;
          overflow: hidden;
        }

        .audit-dialog-header {
          display: flex;
          align-items: center;
          justify-content: space-between;
          padding: 1.125rem 1.5rem;
          border-bottom: 1px solid var(--border-subtle);
          background: var(--glass-surface-sunken);
          gap: 1rem;
        }

        .audit-dialog-header-info {
          display: flex;
          flex-direction: column;
          gap: 0.25rem;
          min-width: 0;
        }

        .audit-dialog-title-row {
          display: flex;
          align-items: center;
          gap: 0.625rem;
          flex-wrap: wrap;
        }

        .audit-dialog-id {
          display: block;
          color: var(--text-muted);
          margin-top: 0.15rem;
          word-break: break-all;
        }

        .audit-dialog-close-btn {
          min-height: 44px;
          min-width: 44px;
          display: flex;
          align-items: center;
          justify-content: center;
          cursor: pointer;
        }

        .audit-dialog-body {
          padding: 1.5rem;
          overflow-y: auto;
          flex: 1;
        }

        .audit-dialog-loading {
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          gap: 0.75rem;
          padding: 3rem 1rem;
          color: var(--text-secondary);
        }

        .audit-dialog-sections {
          display: flex;
          flex-direction: column;
          gap: 1.25rem;
        }

        .audit-detail-section {
          background: var(--glass-surface);
          border: 1px solid var(--border-subtle);
          border-radius: 10px;
          padding: 1rem;
        }

        .audit-section-title {
          font-size: 0.8125rem;
          font-weight: 700;
          color: var(--text-secondary);
          text-transform: uppercase;
          letter-spacing: 0.05em;
          margin-bottom: 0.75rem;
          border-bottom: 1px solid var(--border-subtle);
          padding-bottom: 0.35rem;
        }

        .audit-detail-grid {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
          gap: 0.75rem;
        }

        .audit-detail-item {
          display: flex;
          flex-direction: column;
          gap: 0.2rem;
          font-size: 0.8125rem;
        }

        .audit-item-label {
          font-weight: 600;
          color: var(--text-muted);
        }

        .audit-item-value {
          color: var(--text-primary);
          word-break: break-word;
        }

        /* Safe Metadata Viewer Styles */
        .metadata-viewer-container {
          background: var(--glass-surface-sunken);
          border: 1px solid var(--border-subtle);
          border-radius: 8px;
          padding: 0.875rem;
          font-family: var(--font-code);
          font-size: 0.8125rem;
          max-height: 40vh;
          overflow-y: auto;
          word-break: break-all;
        }

        .meta-val-null {
          color: var(--text-muted);
          font-style: italic;
        }

        .meta-val-bool {
          color: var(--brand-primary);
          font-weight: 600;
        }

        .meta-val-number {
          color: var(--status-warning);
          font-weight: 600;
        }

        .meta-val-string {
          color: var(--text-primary);
          white-space: pre-wrap;
          word-break: break-word;
        }

        .meta-val-truncated,
        .meta-val-empty {
          color: var(--text-muted);
        }

        .meta-array-block,
        .meta-object-block {
          border-left: 2px solid var(--border-glass);
          padding-left: 0.625rem;
          margin: 0.25rem 0;
          display: flex;
          flex-direction: column;
          gap: 0.35rem;
        }

        .meta-array-item,
        .meta-object-row {
          display: flex;
          flex-direction: column;
          gap: 0.15rem;
        }

        @media (min-width: 500px) {
          .meta-array-item,
          .meta-object-row {
            flex-direction: row;
            align-items: baseline;
            gap: 0.5rem;
          }
        }

        .meta-index-label,
        .meta-object-key {
          color: var(--text-secondary);
          font-weight: 600;
          flex-shrink: 0;
        }

        .meta-object-val {
          flex: 1;
        }

        .audit-dialog-footer {
          display: flex;
          justify-content: flex-end;
          padding: 1rem 1.5rem;
          border-top: 1px solid var(--border-subtle);
          background: var(--glass-surface-sunken);
        }

        .audit-dialog-close-action {
          min-height: 44px;
          min-width: 100px;
        }
      `}</style>
    </div>
  );
};
