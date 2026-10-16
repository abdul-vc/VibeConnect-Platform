/**
 * Plan and PlanVersion Modal Dialogs.
 *
 * Implements accessible, keyboard-trapped, focus-restoring modals for:
 * - Create Plan
 * - Edit Plan presentation metadata
 * - Create Draft Version
 * - Edit Draft Version change summary
 * - Clone Version
 * - Activate Version confirmation
 * - Retire Version confirmation
 *
 * Consolidated using a lightweight PlanModalShell to eliminate duplicated
 * backdrop/surface/focus-trap/close/accessibility and footer boilerplate.
 */

import React, { useEffect, useId, useRef, useState } from "react";
import { plansApi } from "../../api/plans.ts";
import type {
  PlanDetail,
  PlanListItem,
  PlanReadinessResponse,
  PlanVersionDetail,
  PlanVersionListItem,
} from "../../api/types.ts";
import { AlertCircleIcon, CheckCircleIcon } from "../Icons.tsx";

import {
  PlanModalShell,
  FormErrorBanner,
  parseApiErrors,
} from "./PlanModalShell.tsx";

export { PlanModalShell, FormErrorBanner };

// ---------------------------------------------------------------------------
// 1. Create Plan Dialog
// ---------------------------------------------------------------------------

interface CreatePlanDialogProps {
  readonly isOpen: boolean;
  readonly onClose: () => void;
  readonly onSuccess: (plan: PlanDetail) => void;
  readonly triggerRef?: React.RefObject<HTMLElement | null>;
}

export const CreatePlanDialog: React.FC<CreatePlanDialogProps> = ({
  isOpen,
  onClose,
  onSuccess,
  triggerRef,
}) => {
  const baseId = useId();
  const [code, setCode] = useState("");
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [initialSummary, setInitialSummary] = useState("");
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [generalError, setGeneralError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const codeInputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    if (isOpen) {
      setCode("");
      setName("");
      setDescription("");
      setInitialSummary("");
      setFieldErrors({});
      setGeneralError(null);
      setIsSubmitting(false);
    }
  }, [isOpen]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const errors: Record<string, string> = {};
    if (!code.trim()) errors.code = "Plan code is required.";
    if (!name.trim()) errors.name = "Plan name is required.";

    if (Object.keys(errors).length > 0) {
      setFieldErrors(errors);
      return;
    }

    setFieldErrors({});
    setGeneralError(null);
    setIsSubmitting(true);

    try {
      const created = await plansApi.create({
        code: code.trim().toLowerCase(),
        name: name.trim(),
        description: description.trim(),
        initial_version_change_summary: initialSummary.trim() || undefined,
      });
      onSuccess(created);
      onClose();
    } catch (err) {
      setIsSubmitting(false);
      const parsed = parseApiErrors(err);
      setFieldErrors(parsed.fieldErrors);
      setGeneralError(parsed.generalError);
    }
  };

  return (
    <PlanModalShell
      isOpen={isOpen}
      onClose={onClose}
      isSubmitting={isSubmitting}
      title="Create Plan Family"
      subtitle="Establish a new commercial plan. Version 1 Draft is automatically initialized."
      triggerRef={triggerRef}
      initialFocusRef={codeInputRef}
      onSubmit={handleSubmit}
      submitLabel="Create Plan"
      submittingLabel="Creating..."
    >
      <FormErrorBanner error={generalError} />

      <div className="form-group-item">
        <label htmlFor={`${baseId}-code`} className="form-label">
          Plan Code <span style={{ color: "var(--status-danger)" }}>*</span>
        </label>
        <input
          ref={codeInputRef}
          id={`${baseId}-code`}
          type="text"
          className={`form-input ${fieldErrors.code ? "form-input-error" : ""}`}
          placeholder="e.g. enterprise-plus"
          value={code}
          onChange={(e) => setCode(e.target.value.toLowerCase())}
          disabled={isSubmitting}
        />
        <span className="form-hint">Lowercase alphanumeric with hyphens. Permanently immutable.</span>
        {fieldErrors.code && <span className="form-error">{fieldErrors.code}</span>}
      </div>

      <div className="form-group-item">
        <label htmlFor={`${baseId}-name`} className="form-label">
          Plan Name <span style={{ color: "var(--status-danger)" }}>*</span>
        </label>
        <input
          id={`${baseId}-name`}
          type="text"
          className={`form-input ${fieldErrors.name ? "form-input-error" : ""}`}
          placeholder="e.g. Enterprise Plus"
          value={name}
          onChange={(e) => setName(e.target.value)}
          disabled={isSubmitting}
        />
        {fieldErrors.name && <span className="form-error">{fieldErrors.name}</span>}
      </div>

      <div className="form-group-item">
        <label htmlFor={`${baseId}-description`} className="form-label">
          Description
        </label>
        <textarea
          id={`${baseId}-description`}
          className="form-input"
          rows={3}
          placeholder="Commercial positioning and scope..."
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          disabled={isSubmitting}
        />
        {fieldErrors.description && <span className="form-error">{fieldErrors.description}</span>}
      </div>

      <div className="form-group-item">
        <label htmlFor={`${baseId}-summary`} className="form-label">
          Initial Version Change Summary
        </label>
        <input
          id={`${baseId}-summary`}
          type="text"
          className="form-input"
          placeholder="Initial version"
          value={initialSummary}
          onChange={(e) => setInitialSummary(e.target.value)}
          disabled={isSubmitting}
        />
      </div>
    </PlanModalShell>
  );
};

// ---------------------------------------------------------------------------
// 2. Edit Plan Dialog
// ---------------------------------------------------------------------------

interface EditPlanDialogProps {
  readonly plan: PlanListItem | PlanDetail | null;
  readonly isOpen: boolean;
  readonly onClose: () => void;
  readonly onSuccess: (plan: PlanDetail) => void;
  readonly triggerRef?: React.RefObject<HTMLElement | null>;
}

export const EditPlanDialog: React.FC<EditPlanDialogProps> = ({
  plan,
  isOpen,
  onClose,
  onSuccess,
  triggerRef,
}) => {
  const baseId = useId();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [isPublic, setIsPublic] = useState(false);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [generalError, setGeneralError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const nameInputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    if (isOpen && plan) {
      setName(plan.name);
      setDescription(plan.description || "");
      setIsPublic(Boolean(plan.is_public));
      setFieldErrors({});
      setGeneralError(null);
      setIsSubmitting(false);
    }
  }, [isOpen, plan]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!plan) return;

    const trimmedName = name.trim();
    const trimmedDesc = description.trim();

    if (!trimmedName) {
      setFieldErrors({ name: "Plan name is required." });
      return;
    }

    if (
      trimmedName === plan.name &&
      trimmedDesc === (plan.description || "") &&
      isPublic === Boolean(plan.is_public)
    ) {
      setFieldErrors({ name: "No changes detected to save." });
      return;
    }

    setFieldErrors({});
    setGeneralError(null);
    setIsSubmitting(true);

    try {
      const updated = await plansApi.update(plan.id, {
        name: trimmedName,
        description: trimmedDesc,
        is_public: isPublic,
      });
      onSuccess(updated);
      onClose();
    } catch (err) {
      setIsSubmitting(false);
      const parsed = parseApiErrors(err);
      setFieldErrors(parsed.fieldErrors);
      setGeneralError(parsed.generalError);
    }
  };

  return (
    <PlanModalShell
      isOpen={isOpen}
      onClose={onClose}
      isSubmitting={isSubmitting}
      title={`Edit Plan: ${plan?.code || ""}`}
      subtitle="Update plan presentation and public catalog visibility."
      triggerRef={triggerRef}
      initialFocusRef={nameInputRef}
      onSubmit={handleSubmit}
      submitLabel="Save Changes"
      submittingLabel="Saving..."
    >
      <FormErrorBanner error={generalError} />

      <div className="form-group-item">
        <label className="form-label">Plan Code</label>
        <div className="form-readonly-pill">{plan?.code}</div>
        <span className="form-hint">Plan code is permanently immutable across all versions.</span>
      </div>

      <div className="form-group-item">
        <label htmlFor={`${baseId}-name`} className="form-label">
          Plan Name <span style={{ color: "var(--status-danger)" }}>*</span>
        </label>
        <input
          ref={nameInputRef}
          id={`${baseId}-name`}
          type="text"
          className={`form-input ${fieldErrors.name ? "form-input-error" : ""}`}
          value={name}
          onChange={(e) => setName(e.target.value)}
          disabled={isSubmitting}
        />
        {fieldErrors.name && <span className="form-error">{fieldErrors.name}</span>}
      </div>

      <div className="form-group-item">
        <label htmlFor={`${baseId}-description`} className="form-label">
          Description
        </label>
        <textarea
          id={`${baseId}-description`}
          className="form-input"
          rows={3}
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          disabled={isSubmitting}
        />
        {fieldErrors.description && <span className="form-error">{fieldErrors.description}</span>}
      </div>

      <div className="form-group-item" style={{ marginTop: "0.5rem" }}>
        <label
          htmlFor={`${baseId}-public`}
          style={{
            display: "flex",
            alignItems: "flex-start",
            gap: "0.75rem",
            cursor: "pointer",
          }}
        >
          <input
            id={`${baseId}-public`}
            type="checkbox"
            checked={isPublic}
            onChange={(e) => setIsPublic(e.target.checked)}
            disabled={isSubmitting}
            style={{ marginTop: "3px" }}
          />
          <div>
            <span style={{ fontWeight: 600, color: "var(--text-primary)", fontSize: "0.875rem" }}>
              Public Catalog Visibility
            </span>
            <p className="form-hint" style={{ margin: "0.2rem 0 0 0" }}>
              Exposes this plan on the public plans discovery endpoint. Requires an active, healthy plan version with prices and packaged products.
            </p>
          </div>
        </label>
        {fieldErrors.is_public && <span className="form-error">{fieldErrors.is_public}</span>}
      </div>
    </PlanModalShell>
  );
};

// ---------------------------------------------------------------------------
// 3. Create Draft Version Dialog
// ---------------------------------------------------------------------------

interface CreateVersionDialogProps {
  readonly planId: string;
  readonly planCode: string;
  readonly isOpen: boolean;
  readonly onClose: () => void;
  readonly onSuccess: (version: PlanVersionDetail) => void;
  readonly triggerRef?: React.RefObject<HTMLElement | null>;
}

export const CreatePlanVersionDialog: React.FC<CreateVersionDialogProps> = ({
  planId,
  planCode,
  isOpen,
  onClose,
  onSuccess,
  triggerRef,
}) => {
  const baseId = useId();
  const [changeSummary, setChangeSummary] = useState("");
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [generalError, setGeneralError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const inputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    if (isOpen) {
      setChangeSummary("");
      setFieldErrors({});
      setGeneralError(null);
      setIsSubmitting(false);
    }
  }, [isOpen]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    setFieldErrors({});
    setGeneralError(null);
    setIsSubmitting(true);

    try {
      const created = await plansApi.createVersion(planId, {
        change_summary: changeSummary.trim(),
      });
      onSuccess(created);
      onClose();
    } catch (err) {
      setIsSubmitting(false);
      const parsed = parseApiErrors(err);
      setFieldErrors(parsed.fieldErrors);
      setGeneralError(parsed.generalError);
    }
  };

  return (
    <PlanModalShell
      isOpen={isOpen}
      onClose={onClose}
      isSubmitting={isSubmitting}
      title={`Create Draft Version for ${planCode}`}
      subtitle="The backend will automatically assign the next sequential version number."
      triggerRef={triggerRef}
      initialFocusRef={inputRef}
      onSubmit={handleSubmit}
      submitLabel="Create Draft Version"
      submittingLabel="Creating..."
    >
      <FormErrorBanner error={generalError} />

      <div className="form-group-item">
        <label htmlFor={`${baseId}-summary`} className="form-label">
          Change Summary
        </label>
        <input
          ref={inputRef}
          id={`${baseId}-summary`}
          type="text"
          className={`form-input ${fieldErrors.change_summary ? "form-input-error" : ""}`}
          placeholder="e.g. Updated feature set and quota allocations"
          value={changeSummary}
          onChange={(e) => setChangeSummary(e.target.value)}
          disabled={isSubmitting}
        />
        <span className="form-hint">Summarize commercial changes planned in this version.</span>
        {fieldErrors.change_summary && (
          <span className="form-error">{fieldErrors.change_summary}</span>
        )}
      </div>
    </PlanModalShell>
  );
};

// ---------------------------------------------------------------------------
// 4. Edit Draft Change Summary Dialog
// ---------------------------------------------------------------------------

interface EditDraftDialogProps {
  readonly version: PlanVersionDetail | null;
  readonly isOpen: boolean;
  readonly onClose: () => void;
  readonly onSuccess: (version: PlanVersionDetail) => void;
  readonly triggerRef?: React.RefObject<HTMLElement | null>;
}

export const EditPlanVersionDialog: React.FC<EditDraftDialogProps> = ({
  version,
  isOpen,
  onClose,
  onSuccess,
  triggerRef,
}) => {
  const baseId = useId();
  const [changeSummary, setChangeSummary] = useState("");
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [generalError, setGeneralError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const inputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    if (isOpen && version) {
      setChangeSummary(version.change_summary || "");
      setFieldErrors({});
      setGeneralError(null);
      setIsSubmitting(false);
    }
  }, [isOpen, version]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!version) return;

    const trimmed = changeSummary.trim();
    if (trimmed === (version.change_summary || "")) {
      setFieldErrors({ change_summary: "No change summary modification detected." });
      return;
    }

    setFieldErrors({});
    setGeneralError(null);
    setIsSubmitting(true);

    try {
      const updated = await plansApi.updateVersion(version.id, {
        change_summary: trimmed,
      });
      onSuccess(updated);
      onClose();
    } catch (err) {
      setIsSubmitting(false);
      const parsed = parseApiErrors(err);
      setFieldErrors(parsed.fieldErrors);
      setGeneralError(parsed.generalError);
    }
  };

  return (
    <PlanModalShell
      isOpen={isOpen}
      onClose={onClose}
      isSubmitting={isSubmitting}
      title={`Edit Change Summary: Version ${version?.version}`}
      subtitle="Draft versions allow updating their commercial changelog."
      triggerRef={triggerRef}
      initialFocusRef={inputRef}
      onSubmit={handleSubmit}
      submitLabel="Update Summary"
      submittingLabel="Updating..."
    >
      <FormErrorBanner error={generalError} />

      <div className="form-group-item">
        <label htmlFor={`${baseId}-summary`} className="form-label">
          Change Summary
        </label>
        <input
          ref={inputRef}
          id={`${baseId}-summary`}
          type="text"
          className={`form-input ${fieldErrors.change_summary ? "form-input-error" : ""}`}
          value={changeSummary}
          onChange={(e) => setChangeSummary(e.target.value)}
          disabled={isSubmitting}
        />
        {fieldErrors.change_summary && (
          <span className="form-error">{fieldErrors.change_summary}</span>
        )}
      </div>
    </PlanModalShell>
  );
};

// ---------------------------------------------------------------------------
// 5. Clone Version Dialog
// ---------------------------------------------------------------------------

interface CloneVersionDialogProps {
  readonly version: PlanVersionListItem | PlanVersionDetail | null;
  readonly isOpen: boolean;
  readonly onClose: () => void;
  readonly onSuccess: (newDraft: PlanVersionDetail) => void;
  readonly triggerRef?: React.RefObject<HTMLElement | null>;
}

export const ClonePlanVersionDialog: React.FC<CloneVersionDialogProps> = ({
  version,
  isOpen,
  onClose,
  onSuccess,
  triggerRef,
}) => {
  const baseId = useId();
  const [changeSummary, setChangeSummary] = useState("");
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [generalError, setGeneralError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const inputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    if (isOpen && version) {
      setChangeSummary(`Cloned from Version ${version.version}`);
      setFieldErrors({});
      setGeneralError(null);
      setIsSubmitting(false);
    }
  }, [isOpen, version]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!version) return;

    setFieldErrors({});
    setGeneralError(null);
    setIsSubmitting(true);

    try {
      const cloned = await plansApi.cloneVersion(version.id, {
        change_summary: changeSummary.trim() || undefined,
      });
      onSuccess(cloned);
      onClose();
    } catch (err) {
      setIsSubmitting(false);
      const parsed = parseApiErrors(err);
      setFieldErrors(parsed.fieldErrors);
      setGeneralError(parsed.generalError);
    }
  };

  return (
    <PlanModalShell
      isOpen={isOpen}
      onClose={onClose}
      isSubmitting={isSubmitting}
      title={`Clone Version ${version?.version}`}
      subtitle="Create a new editable Draft version based on this configuration."
      triggerRef={triggerRef}
      initialFocusRef={inputRef}
      onSubmit={handleSubmit}
      submitLabel="Clone to Draft Version"
      submittingLabel="Cloning..."
    >
      <FormErrorBanner error={generalError} />

      <div
        style={{
          background: "var(--glass-surface-sunken)",
          border: "1px solid var(--border-subtle)",
          borderRadius: "8px",
          padding: "0.75rem 1rem",
          fontSize: "0.8125rem",
          lineHeight: 1.5,
          color: "var(--text-secondary)",
        }}
      >
        <p style={{ margin: 0 }}>
          Cloning creates a new <strong>Draft</strong> version. The source Version {version?.version} remains unchanged. All prices, packaging, and quotas will be replicated by the server.
        </p>
      </div>

      <div className="form-group-item">
        <label htmlFor={`${baseId}-summary`} className="form-label">
          New Version Change Summary (Optional)
        </label>
        <input
          ref={inputRef}
          id={`${baseId}-summary`}
          type="text"
          className={`form-input ${fieldErrors.change_summary ? "form-input-error" : ""}`}
          value={changeSummary}
          onChange={(e) => setChangeSummary(e.target.value)}
          disabled={isSubmitting}
        />
        {fieldErrors.change_summary && (
          <span className="form-error">{fieldErrors.change_summary}</span>
        )}
      </div>
    </PlanModalShell>
  );
};

// ---------------------------------------------------------------------------
// 6. Activate Version Confirmation Dialog
// ---------------------------------------------------------------------------

interface ActivateVersionDialogProps {
  readonly version: PlanVersionListItem | PlanVersionDetail | null;
  readonly readiness: PlanReadinessResponse | null;
  readonly isOpen: boolean;
  readonly onClose: () => void;
  readonly onSuccess: (version: PlanVersionDetail) => void;
  readonly triggerRef?: React.RefObject<HTMLElement | null>;
}

export const ActivatePlanVersionDialog: React.FC<ActivateVersionDialogProps> = ({
  version,
  readiness,
  isOpen,
  onClose,
  onSuccess,
  triggerRef,
}) => {
  const [generalError, setGeneralError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const confirmButtonRef = useRef<HTMLButtonElement | null>(null);

  useEffect(() => {
    if (isOpen) {
      setGeneralError(null);
      setIsSubmitting(false);
    }
  }, [isOpen]);

  const hasBlockers = readiness ? !readiness.is_ready : false;

  const handleActivate = async () => {
    if (!version || hasBlockers) return;
    setGeneralError(null);
    setIsSubmitting(true);

    try {
      const activated = await plansApi.activateVersion(version.id);
      onSuccess(activated);
      onClose();
    } catch (err) {
      setIsSubmitting(false);
      const parsed = parseApiErrors(err);
      setGeneralError(parsed.generalError);
    }
  };

  return (
    <PlanModalShell
      isOpen={isOpen && !!version}
      onClose={onClose}
      isSubmitting={isSubmitting}
      title={`Activate Version ${version?.version}`}
      subtitle="Make this version the authoritative commercial definition."
      triggerRef={triggerRef}
      initialFocusRef={confirmButtonRef}
      onActionClick={handleActivate}
      submitLabel={`Activate Version ${version?.version}`}
      submittingLabel="Activating..."
      submitDisabled={hasBlockers}
    >
      <FormErrorBanner error={generalError} />

      <div className="retire-warning-content">
        <p>
          <strong>Commercial Immutability:</strong> Once activated, this version&apos;s prices,
          packaging, and quotas become <strong>permanently frozen</strong> and cannot be mutated.
        </p>
        <p>
          <strong>Automatic Supersession:</strong> If a prior Active version exists on this plan,
          it will be automatically and atomically transitioned to <strong>Retired</strong>.
        </p>
      </div>

      {/* Readiness Status Summary */}
      {readiness && (
        <div
          style={{
            background: readiness.is_ready ? "var(--status-success-bg)" : "var(--status-danger-bg)",
            border: `1px solid ${readiness.is_ready ? "var(--status-success-border)" : "var(--status-danger-border)"}`,
            borderRadius: "8px",
            padding: "0.75rem 1rem",
            marginTop: "0.75rem",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", fontWeight: 600 }}>
            {readiness.is_ready ? (
              <>
                <CheckCircleIcon size={16} style={{ color: "var(--status-success)" }} />
                <span style={{ color: "var(--status-success)" }}>Readiness Check Passed</span>
              </>
            ) : (
              <>
                <AlertCircleIcon size={16} style={{ color: "var(--status-danger)" }} />
                <span style={{ color: "var(--status-danger)" }}>
                  Activation Blocked ({readiness.blockers.length} {readiness.blockers.length === 1 ? "Blocker" : "Blockers"})
                </span>
              </>
            )}
          </div>
          {!readiness.is_ready && readiness.blockers.length > 0 && (
            <ul style={{ margin: "0.5rem 0 0 1.25rem", padding: 0, fontSize: "0.8125rem" }}>
              {readiness.blockers.map((b, i) => (
                <li key={i}>{b}</li>
              ))}
            </ul>
          )}
        </div>
      )}
    </PlanModalShell>
  );
};

// ---------------------------------------------------------------------------
// 7. Retire Version Confirmation Dialog
// ---------------------------------------------------------------------------

interface RetireVersionDialogProps {
  readonly version: PlanVersionListItem | PlanVersionDetail | null;
  readonly isOpen: boolean;
  readonly onClose: () => void;
  readonly onSuccess: (version: PlanVersionDetail) => void;
  readonly triggerRef?: React.RefObject<HTMLElement | null>;
}

export const RetirePlanVersionDialog: React.FC<RetireVersionDialogProps> = ({
  version,
  isOpen,
  onClose,
  onSuccess,
  triggerRef,
}) => {
  const [generalError, setGeneralError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const confirmButtonRef = useRef<HTMLButtonElement | null>(null);

  useEffect(() => {
    if (isOpen) {
      setGeneralError(null);
      setIsSubmitting(false);
    }
  }, [isOpen]);

  const handleRetire = async () => {
    if (!version) return;
    setGeneralError(null);
    setIsSubmitting(true);

    try {
      const retired = await plansApi.retireVersion(version.id);
      onSuccess(retired);
      onClose();
    } catch (err) {
      setIsSubmitting(false);
      const parsed = parseApiErrors(err);
      setGeneralError(parsed.generalError);
    }
  };

  const wasActive = version?.status === "active";

  return (
    <PlanModalShell
      isOpen={isOpen && !!version}
      onClose={onClose}
      isSubmitting={isSubmitting}
      title={`Retire Version ${version?.version}`}
      subtitle="Confirm permanent lifecycle retirement."
      triggerRef={triggerRef}
      initialFocusRef={confirmButtonRef}
      maxWidth="480px"
      onActionClick={handleRetire}
      submitLabel={`Retire Version ${version?.version}`}
      submittingLabel="Retiring..."
      submitVariant="danger"
    >
      <FormErrorBanner error={generalError} />

      <div className="retire-target-card">
        <span className="product-code-pill">Version {version?.version}</span>
        <span className="retire-target-name">{version?.status.toUpperCase()}</span>
      </div>

      <div className="retire-warning-content">
        <p>
          <strong>Terminal State:</strong> Retiring this version is <strong>permanent</strong> and
          cannot be undone. The version becomes completely read-only.
        </p>
        {wasActive && (
          <p className="retire-bottom-up-note">
            <strong>Active Version Warning:</strong> Retiring this version leaves the plan
            without an Active version until another Draft version is activated.
          </p>
        )}
      </div>
    </PlanModalShell>
  );
};
