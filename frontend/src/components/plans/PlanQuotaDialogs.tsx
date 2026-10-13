/**
 * Commercial Quota Dialogs.
 *
 * Implements accessible, keyboard-trapped, focus-restoring modals for:
 * - Create Quota (Scope, Target, Key, Name, Unit, Limit Type, Limit Value, Hard Limit, Reset Period)
 * - Edit Quota (Name, Unit, Limit Type, Limit Value, Hard Limit, Reset Period; identity immutable)
 * - Delete Quota confirmation (readiness and commercial limit impact warning)
 *
 * Fully tenant-isolated and strictly adheres to Draft vs Active/Retired mutability.
 */

import React, { useEffect, useRef, useState } from "react";
import { plansApi } from "../../api/plans.ts";
import type {
  CreatePlanQuotaPayload,
  PlanCapabilityListItem,
  PlanModuleListItem,
  PlanProductListItem,
  PlanQuotaListItem,
  PlanQuotaLimitType,
  PlanQuotaResetPeriod,
  PlanQuotaScope,
  UpdatePlanQuotaPayload,
} from "../../api/types.ts";
import { AlertCircleIcon } from "../Icons.tsx";
import { FormErrorBanner, parseApiErrors, PlanModalShell } from "./PlanModalShell.tsx";

// ============================================================================
// PURE VALIDATORS & CONSTANTS
// ============================================================================

export const QUOTA_KEY_REGEX = /^[a-z0-9]+(?:[-_][a-z0-9]+)*$/;
export const QUOTA_UNIT_REGEX = /^[a-z0-9_]+$/;
export const CANONICAL_NUMERIC_REGEX = /^(?:0|[1-9][0-9]*)$/;
export const MAX_BIGINT_STR = "9223372036854775807";

export interface QuotaValidationResult {
  readonly isValid: boolean;
  readonly error?: string;
}

export const SUPPORTED_SCOPES: readonly { value: PlanQuotaScope; label: string }[] = [
  { value: "plan", label: "Plan (Version Level)" },
  { value: "product", label: "Product Level" },
  { value: "module", label: "Module Level" },
  { value: "capability", label: "Capability Level" },
];

export const SUGGESTED_UNITS: readonly string[] = [
  "count",
  "seats",
  "users",
  "credits",
  "requests",
  "api_calls",
  "gb",
  "mb",
  "domains",
  "projects",
  "minutes",
  "hours",
];
export const SUPPORTED_UNITS = SUGGESTED_UNITS;

export const SUPPORTED_RESET_PERIODS: readonly { value: PlanQuotaResetPeriod; label: string }[] = [
  { value: "never", label: "Never (Lifetime / Persistent)" },
  { value: "monthly", label: "Monthly" },
  { value: "annual", label: "Annual" },
];

/**
 * Validates quota key string.
 * Format: ^[a-z0-9]+(?:[-_][a-z0-9]+)*$, max length 64, no whitespace.
 */
export function validateQuotaKey(key: unknown): QuotaValidationResult {
  if (typeof key !== "string") {
    return { isValid: false, error: "Quota key must be provided as a string." };
  }
  if (!key) {
    return { isValid: false, error: "Quota key is required." };
  }
  if (key !== key.trim() || /\s/.test(key)) {
    return { isValid: false, error: "Quota key cannot contain whitespace." };
  }
  if (key.length > 64) {
    return { isValid: false, error: "Quota key cannot exceed 64 characters." };
  }
  if (key !== key.toLowerCase()) {
    return { isValid: false, error: "Quota key must be lowercase." };
  }
  if (!QUOTA_KEY_REGEX.test(key)) {
    return {
      isValid: false,
      error: "Quota key must be lowercase alphanumeric and may contain single hyphens or underscores (e.g. api_calls, max-storage).",
    };
  }
  return { isValid: true };
}

/**
 * Validates quota unit string.
 * Format: ^[a-z0-9_]+$, max length 32, lowercase, no whitespace.
 */
export function validateQuotaUnit(unit: unknown): QuotaValidationResult {
  if (typeof unit !== "string") {
    return { isValid: false, error: "Quota unit must be provided as a string." };
  }
  if (!unit) {
    return { isValid: false, error: "Quota unit is required." };
  }
  if (unit !== unit.trim() || /\s/.test(unit)) {
    return { isValid: false, error: "Quota unit cannot contain whitespace." };
  }
  if (unit.length > 32) {
    return { isValid: false, error: "Quota unit cannot exceed 32 characters." };
  }
  if (unit !== unit.toLowerCase()) {
    return { isValid: false, error: "Quota unit must be lowercase." };
  }
  if (!QUOTA_UNIT_REGEX.test(unit)) {
    return {
      isValid: false,
      error: "Quota unit must be lowercase alphanumeric with underscores (e.g. gb, api_calls, requests).",
    };
  }
  return { isValid: true };
}

/**
 * Canonical quota numeric string rule:
 * value == "0" OR value matches ^[1-9][0-9]*$
 * Range: 0 through 9223372036854775807 without floating-point conversion.
 */
export function validateQuotaLimitValue(
  val: unknown,
  limitType: PlanQuotaLimitType
): QuotaValidationResult {
  if (limitType === "unlimited") {
    if (val !== null && val !== undefined && val !== "") {
      return { isValid: false, error: "Limit value must be null when limit type is unlimited." };
    }
    return { isValid: true };
  }

  if (typeof val !== "string") {
    return { isValid: false, error: "Limit value must be provided as a string." };
  }
  if (!val) {
    return { isValid: false, error: "Limit value is required when limit type is numeric." };
  }
  if (val !== val.trim() || /\s/.test(val)) {
    return { isValid: false, error: "Limit value cannot contain whitespace." };
  }
  if (!CANONICAL_NUMERIC_REGEX.test(val)) {
    return {
      isValid: false,
      error: `Invalid canonical quota format or leading zeros: '${val}'. Valid examples: 0, 1, 100.`,
    };
  }
  if (val.length > 19 || (val.length === 19 && val > MAX_BIGINT_STR)) {
    return {
      isValid: false,
      error: "Limit value out of 64-bit integer range (maximum 9223372036854775807).",
    };
  }
  return { isValid: true };
}

export function buildQuotaPatchPayload(
  original: PlanQuotaListItem,
  draft: {
    name: string;
    unit: string;
    limit_type: PlanQuotaLimitType;
    limit_value: string;
    is_hard_limit: boolean;
    reset_period: PlanQuotaResetPeriod;
  }
): { payload: UpdatePlanQuotaPayload; hasChanges: boolean } {
  const patch: Record<string, unknown> = {};

  const cleanName = draft.name.trim();
  if (cleanName !== original.name) {
    patch.name = cleanName;
  }

  if (draft.unit !== original.unit) {
    patch.unit = draft.unit;
  }

  if (draft.limit_type !== original.limit_type) {
    patch.limit_type = draft.limit_type;
  }

  const effectiveLimitValue = draft.limit_type === "unlimited" ? null : draft.limit_value;
  if (effectiveLimitValue !== original.limit_value) {
    patch.limit_value = effectiveLimitValue;
  }

  if (draft.is_hard_limit !== original.is_hard_limit) {
    patch.is_hard_limit = draft.is_hard_limit;
  }

  if (draft.reset_period !== original.reset_period) {
    patch.reset_period = draft.reset_period;
  }

  const keys = Object.keys(patch);
  return {
    payload: patch as UpdatePlanQuotaPayload,
    hasChanges: keys.length > 0,
  };
}

/**
 * Shared validation for the 6 mutable quota configuration fields.
 * Reusable across both Create and Edit quota dialogs.
 */
export function validateQuotaConfigValues(config: QuotaConfigValues): Record<string, string> {
  const errors: Record<string, string> = {};
  const cleanName = config.name.trim();
  if (!cleanName) {
    errors.name = "Quota name is required.";
  } else if (cleanName.length > 100) {
    errors.name = "Quota name cannot exceed 100 characters.";
  }

  const unitVal = validateQuotaUnit(config.unit);
  if (!unitVal.isValid && unitVal.error) {
    errors.unit = unitVal.error;
  }

  const limitVal = validateQuotaLimitValue(
    config.limitType === "unlimited" ? null : config.limitValue,
    config.limitType
  );
  if (!limitVal.isValid && limitVal.error) {
    errors.limit_value = limitVal.error;
  }

  return errors;
}

// ============================================================================
// SHARED CONFIGURATION FORM FIELDS
// ============================================================================

export interface QuotaConfigValues {
  readonly name: string;
  readonly unit: string;
  readonly limitType: PlanQuotaLimitType;
  readonly limitValue: string;
  readonly isHardLimit: boolean;
  readonly resetPeriod: PlanQuotaResetPeriod;
}

interface QuotaConfigFieldsProps {
  readonly values: QuotaConfigValues;
  readonly fieldErrors: Record<string, string>;
  readonly isSubmitting: boolean;
  readonly onChange: (patch: Partial<QuotaConfigValues>) => void;
  readonly nameInputRef?: React.Ref<HTMLInputElement>;
}

const QuotaConfigFields: React.FC<QuotaConfigFieldsProps> = ({
  values,
  fieldErrors,
  isSubmitting,
  onChange,
  nameInputRef,
}) => (
  <>
    <div className="plan-form-row" style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem" }}>
      <div className="form-group">
        <label htmlFor="quota-name-input" className="form-label required">
          Display Name
        </label>
        <input
          ref={nameInputRef}
          id="quota-name-input"
          type="text"
          className={`form-input ${fieldErrors.name ? "input-error" : ""}`}
          placeholder="e.g. API Calls"
          value={values.name}
          onChange={(e) => onChange({ name: e.target.value })}
          disabled={isSubmitting}
          maxLength={100}
          aria-invalid={Boolean(fieldErrors.name)}
          aria-describedby={fieldErrors.name ? "name-error" : undefined}
        />
        {fieldErrors.name && (
          <span id="name-error" className="field-error-text" role="alert">
            {fieldErrors.name}
          </span>
        )}
      </div>

      <div className="form-group">
        <label htmlFor="quota-unit-input" className="form-label required">
          Unit
        </label>
        <input
          id="quota-unit-input"
          type="text"
          list="quota-units-list"
          className={`form-input ${fieldErrors.unit ? "input-error" : ""}`}
          placeholder="e.g. count, gb, seats"
          value={values.unit}
          onChange={(e) => onChange({ unit: e.target.value })}
          disabled={isSubmitting}
          maxLength={32}
          aria-invalid={Boolean(fieldErrors.unit)}
          aria-describedby={fieldErrors.unit ? "unit-error" : undefined}
        />
        <datalist id="quota-units-list">
          {SUPPORTED_UNITS.map((u) => (
            <option key={u} value={u} />
          ))}
        </datalist>
        {fieldErrors.unit && (
          <span id="unit-error" className="field-error-text" role="alert">
            {fieldErrors.unit}
          </span>
        )}
      </div>
    </div>

    <div className="plan-form-row" style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem" }}>
      <div className="form-group">
        <label htmlFor="quota-limit-type-select" className="form-label required">
          Limit Type
        </label>
        <select
          id="quota-limit-type-select"
          className="form-select"
          value={values.limitType}
          onChange={(e) => onChange({ limitType: e.target.value as PlanQuotaLimitType })}
          disabled={isSubmitting}
        >
          <option value="numeric">Numeric Limit</option>
          <option value="unlimited">Unlimited (No Ceiling)</option>
        </select>
      </div>

      <div className="form-group">
        <label htmlFor="quota-limit-value-input" className="form-label required">
          Limit Value
        </label>
        {values.limitType === "unlimited" ? (
          <input
            id="quota-limit-value-input"
            type="text"
            className="form-input"
            value="Unlimited (null)"
            disabled
            style={{ fontStyle: "italic", background: "var(--bg-card-secondary)" }}
          />
        ) : (
          <input
            id="quota-limit-value-input"
            type="text"
            className={`form-input ${fieldErrors.limit_value ? "input-error" : ""}`}
            placeholder="e.g. 0, 100, 1000"
            value={values.limitValue}
            onChange={(e) => onChange({ limitValue: e.target.value })}
            disabled={isSubmitting}
            maxLength={19}
            aria-invalid={Boolean(fieldErrors.limit_value)}
            aria-describedby={fieldErrors.limit_value ? "limit-error" : "limit-hint"}
          />
        )}
        <span id="limit-hint" className="text-caption" style={{ color: "var(--text-muted)" }}>
          {values.limitType === "unlimited"
            ? "No numeric ceiling applied."
            : "Exact integer string from 0 to 9223372036854775807."}
        </span>
        {fieldErrors.limit_value && (
          <span id="limit-error" className="field-error-text" role="alert">
            {fieldErrors.limit_value}
          </span>
        )}
      </div>
    </div>

    <div className="plan-form-row" style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem" }}>
      <div className="form-group">
        <label htmlFor="quota-reset-period-select" className="form-label required">
          Reset Period
        </label>
        <select
          id="quota-reset-period-select"
          className="form-select"
          value={values.resetPeriod}
          onChange={(e) => onChange({ resetPeriod: e.target.value as PlanQuotaResetPeriod })}
          disabled={isSubmitting}
        >
          {SUPPORTED_RESET_PERIODS.map((rp) => (
            <option key={rp.value} value={rp.value}>
              {rp.label}
            </option>
          ))}
        </select>
      </div>

      <div className="form-group" style={{ alignSelf: "center", paddingTop: "1.25rem" }}>
        <label style={{ display: "flex", alignItems: "center", gap: "0.5rem", cursor: "pointer" }}>
          <input
            type="checkbox"
            checked={values.isHardLimit}
            onChange={(e) => onChange({ isHardLimit: e.target.checked })}
            disabled={isSubmitting}
          />
          <span style={{ fontSize: "0.875rem", fontWeight: 500 }}>
            Hard Limit (Strictly enforces ceiling)
          </span>
        </label>
      </div>
    </div>
  </>
);

// ============================================================================
// CREATE PLAN QUOTA DIALOG
// ============================================================================

interface CreatePlanQuotaDialogProps {
  readonly isOpen: boolean;
  readonly versionId: string;
  readonly versionNumber: number;
  readonly triggerRef?: React.RefObject<HTMLElement | null>;
  readonly onClose: () => void;
  readonly onSuccess: () => void;
}

export const CreatePlanQuotaDialog: React.FC<CreatePlanQuotaDialogProps> = ({
  isOpen,
  versionId,
  versionNumber,
  triggerRef,
  onClose,
  onSuccess,
}) => {
  const [scope, setScope] = useState<PlanQuotaScope>("plan");
  const [selectedTargetId, setSelectedTargetId] = useState<string>("");
  const [quotaKey, setQuotaKey] = useState<string>("");
  const [config, setConfig] = useState<QuotaConfigValues>({
    name: "",
    unit: "count",
    limitType: "numeric",
    limitValue: "0",
    isHardLimit: true,
    resetPeriod: "never",
  });

  const [isLoadingTargets, setIsLoadingTargets] = useState<boolean>(false);
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  const [generalError, setGeneralError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  const [products, setProducts] = useState<readonly PlanProductListItem[]>([]);
  const [modules, setModules] = useState<readonly PlanModuleListItem[]>([]);
  const [capabilities, setCapabilities] = useState<readonly PlanCapabilityListItem[]>([]);

  const keyInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!isOpen) return;
    let isMounted = true;
    setIsLoadingTargets(true);

    Promise.all([
      plansApi.listProducts(versionId, { page_size: 100 }),
      plansApi.listModules(versionId, { page_size: 100 }),
      plansApi.listCapabilities(versionId, { page_size: 100 }),
    ])
      .then(([prodsRes, modsRes, capsRes]) => {
        if (!isMounted) return;
        setProducts(prodsRes.results);
        setModules(modsRes.results);
        setCapabilities(capsRes.results);
      })
      .catch((err: unknown) => {
        if (!isMounted) return;
        const { generalError: errGen } = parseApiErrors(err);
        setGeneralError(errGen || "Failed to load packaging targets for quota assignment.");
      })
      .finally(() => {
        if (isMounted) setIsLoadingTargets(false);
      });

    return () => {
      isMounted = false;
    };
  }, [isOpen, versionId]);

  useEffect(() => {
    setSelectedTargetId("");
    setFieldErrors((prev) => {
      const next = { ...prev };
      delete next.target_id;
      return next;
    });
  }, [scope]);

  useEffect(() => {
    if (isOpen) {
      setScope("plan");
      setSelectedTargetId("");
      setQuotaKey("");
      setConfig({
        name: "",
        unit: "count",
        limitType: "numeric",
        limitValue: "0",
        isHardLimit: true,
        resetPeriod: "never",
      });
      setGeneralError(null);
      setFieldErrors({});
    }
  }, [isOpen]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setGeneralError(null);

    const errors: Record<string, string> = {};

    const keyVal = validateQuotaKey(quotaKey);
    if (!keyVal.isValid && keyVal.error) errors.quota_key = keyVal.error;

    if (scope === "product" && !selectedTargetId) errors.target_id = "Please select a packaged product target.";
    else if (scope === "module" && !selectedTargetId) errors.target_id = "Please select a packaged module target.";
    else if (scope === "capability" && !selectedTargetId) errors.target_id = "Please select a packaged capability target.";

    const configErrors = validateQuotaConfigValues(config);
    Object.assign(errors, configErrors);

    if (Object.keys(errors).length > 0) {
      setFieldErrors(errors);
      return;
    }

    setFieldErrors({});
    setIsSubmitting(true);

    const payload: CreatePlanQuotaPayload = {
      scope,
      quota_key: quotaKey,
      name: config.name.trim(),
      unit: config.unit,
      limit_type: config.limitType,
      limit_value: config.limitType === "unlimited" ? null : config.limitValue,
      is_hard_limit: config.isHardLimit,
      reset_period: config.resetPeriod,
      plan_product_id: scope === "product" ? selectedTargetId : null,
      plan_module_id: scope === "module" ? selectedTargetId : null,
      plan_capability_id: scope === "capability" ? selectedTargetId : null,
    };

    try {
      await plansApi.createQuota(versionId, payload);
      onSuccess();
      onClose();
    } catch (err: unknown) {
      const { fieldErrors: errFields, generalError: errGen } = parseApiErrors(err);
      setGeneralError(errGen || "Failed to create quota. Please check your inputs.");
      setFieldErrors(errFields);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <PlanModalShell
      isOpen={isOpen}
      onClose={onClose}
      isSubmitting={isSubmitting}
      title="Create Plan Quota"
      subtitle={`Configure usage quota for Version ${versionNumber}.`}
      initialFocusRef={keyInputRef}
      triggerRef={triggerRef}
      onSubmit={handleSubmit}
      submitLabel="Create Quota"
      submittingLabel="Creating Quota..."
      submitDisabled={isSubmitting || isLoadingTargets}
      maxWidth="640px"
    >
      <FormErrorBanner error={generalError} />

      <div className="form-group">
        <label htmlFor="quota-scope-select" className="form-label required">
          Quota Scope
        </label>
        <select
          id="quota-scope-select"
          className="form-select"
          value={scope}
          onChange={(e) => setScope(e.target.value as PlanQuotaScope)}
          disabled={isSubmitting}
        >
          {SUPPORTED_SCOPES.map((s) => (
            <option key={s.value} value={s.value}>
              {s.label}
            </option>
          ))}
        </select>
        <span className="text-caption" style={{ color: "var(--text-muted)" }}>
          Defines the commercial granularity of the usage quota within Version {versionNumber}.
        </span>
      </div>

      {scope === "plan" ? (
        <div className="alert-box alert-info" style={{ margin: "0.25rem 0 1rem" }} role="status">
          <span>Applies to Plan Version {versionNumber} globally (no child packaging target required).</span>
        </div>
      ) : (
        <div className="form-group">
          <label htmlFor="quota-target-select" className="form-label required">
            Target {scope === "product" ? "Product" : scope === "module" ? "Module" : "Capability"}
          </label>
          {isLoadingTargets ? (
            <div className="skeleton-row" style={{ height: "38px" }} />
          ) : (
            <select
              id="quota-target-select"
              className={`form-select ${fieldErrors.target_id ? "input-error" : ""}`}
              value={selectedTargetId}
              onChange={(e) => setSelectedTargetId(e.target.value)}
              disabled={isSubmitting}
              aria-invalid={Boolean(fieldErrors.target_id)}
              aria-describedby={fieldErrors.target_id ? "target-error" : undefined}
            >
              <option value="">-- Select a packaged {scope} --</option>
              {scope === "product" &&
                products.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.product_code} — {p.product_name}
                  </option>
                ))}
              {scope === "module" &&
                modules.map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.module_code} ({m.module_name})
                  </option>
                ))}
              {scope === "capability" &&
                capabilities.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.capability_code} — {c.capability_name} [{c.feature_code}]
                  </option>
                ))}
            </select>
          )}
          {fieldErrors.target_id && (
            <span id="target-error" className="field-error-text" role="alert">
              {fieldErrors.target_id}
            </span>
          )}
        </div>
      )}

      <div className="form-group">
        <label htmlFor="quota-key-input" className="form-label required">
          Quota Key
        </label>
        <input
          ref={keyInputRef}
          id="quota-key-input"
          type="text"
          className={`form-input ${fieldErrors.quota_key ? "input-error" : ""}`}
          placeholder="e.g. api_calls"
          value={quotaKey}
          onChange={(e) => setQuotaKey(e.target.value)}
          disabled={isSubmitting}
          maxLength={64}
          aria-invalid={Boolean(fieldErrors.quota_key)}
          aria-describedby={fieldErrors.quota_key ? "key-error" : "key-hint"}
        />
        <span id="key-hint" className="text-caption" style={{ color: "var(--text-muted)" }}>
          Lowercase alphanumeric with hyphens/underscores.
        </span>
        {fieldErrors.quota_key && (
          <span id="key-error" className="field-error-text" role="alert">
            {fieldErrors.quota_key}
          </span>
        )}
      </div>

      <QuotaConfigFields
        values={config}
        fieldErrors={fieldErrors}
        isSubmitting={isSubmitting}
        onChange={(patch) => setConfig((prev) => ({ ...prev, ...patch }))}
      />
    </PlanModalShell>
  );
};

// ============================================================================
// EDIT PLAN QUOTA DIALOG
// ============================================================================

interface EditPlanQuotaDialogProps {
  readonly isOpen: boolean;
  readonly quota: PlanQuotaListItem | null;
  readonly resolvedTargetLabel: string;
  readonly triggerRef?: React.RefObject<HTMLElement | null>;
  readonly onClose: () => void;
  readonly onSuccess: () => void;
}

export const EditPlanQuotaDialog: React.FC<EditPlanQuotaDialogProps> = ({
  isOpen,
  quota,
  resolvedTargetLabel,
  triggerRef,
  onClose,
  onSuccess,
}) => {
  const [config, setConfig] = useState<QuotaConfigValues>({
    name: "",
    unit: "",
    limitType: "numeric",
    limitValue: "",
    isHardLimit: true,
    resetPeriod: "never",
  });

  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  const [generalError, setGeneralError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  const nameInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (isOpen && quota) {
      setConfig({
        name: quota.name,
        unit: quota.unit,
        limitType: quota.limit_type,
        limitValue: quota.limit_value ?? "0",
        isHardLimit: quota.is_hard_limit,
        resetPeriod: quota.reset_period,
      });
      setGeneralError(null);
      setFieldErrors({});
    }
  }, [isOpen, quota]);

  if (!quota) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setGeneralError(null);

    const errors: Record<string, string> = validateQuotaConfigValues(config);

    if (Object.keys(errors).length > 0) {
      setFieldErrors(errors);
      return;
    }

    const { payload, hasChanges } = buildQuotaPatchPayload(quota, {
      name: config.name,
      unit: config.unit,
      limit_type: config.limitType,
      limit_value: config.limitValue,
      is_hard_limit: config.isHardLimit,
      reset_period: config.resetPeriod,
    });

    if (!hasChanges) {
      setGeneralError("No changes detected.");
      return;
    }

    setFieldErrors({});
    setIsSubmitting(true);

    try {
      await plansApi.updateQuota(quota.id, payload);
      onSuccess();
      onClose();
    } catch (err: unknown) {
      const { fieldErrors: errFields, generalError: errGen } = parseApiErrors(err);
      setGeneralError(errGen || "Failed to update quota. Please check your inputs.");
      setFieldErrors(errFields);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <PlanModalShell
      isOpen={isOpen}
      onClose={onClose}
      isSubmitting={isSubmitting}
      title="Edit Plan Quota"
      subtitle={`Modify quota parameters for '${quota.name}'.`}
      initialFocusRef={nameInputRef}
      triggerRef={triggerRef}
      onSubmit={handleSubmit}
      submitLabel="Save Changes"
      submittingLabel="Saving Changes..."
      submitDisabled={isSubmitting}
      maxWidth="640px"
    >
      <FormErrorBanner error={generalError} />

      <div className="plan-identity-panel" style={{ marginBottom: "1.25rem" }}>
        <div className="plan-identity-row">
          <span className="meta-label">Quota Key</span>
          <span className="product-code-pill">{quota.quota_key}</span>
        </div>
        <div className="plan-identity-row">
          <span className="meta-label">Scope</span>
          <span className="badge badge-neutral" style={{ textTransform: "capitalize" }}>
            {quota.scope}
          </span>
        </div>
        <div className="plan-identity-row">
          <span className="meta-label">Target</span>
          <span style={{ fontWeight: 500 }}>{resolvedTargetLabel}</span>
        </div>
        <span className="text-caption" style={{ color: "var(--text-muted)", marginTop: "0.25rem" }}>
          Identity fields (version, scope, quota key, and target) are immutable after creation.
        </span>
      </div>

      <QuotaConfigFields
        values={config}
        fieldErrors={fieldErrors}
        isSubmitting={isSubmitting}
        onChange={(patch) => setConfig((prev) => ({ ...prev, ...patch }))}
        nameInputRef={nameInputRef}
      />
    </PlanModalShell>
  );
};

// ============================================================================
// DELETE PLAN QUOTA DIALOG
// ============================================================================

interface DeletePlanQuotaDialogProps {
  readonly isOpen: boolean;
  readonly quota: PlanQuotaListItem | null;
  readonly resolvedTargetLabel: string;
  readonly triggerRef?: React.RefObject<HTMLElement | null>;
  readonly onClose: () => void;
  readonly onSuccess: () => void;
}

export const DeletePlanQuotaDialog: React.FC<DeletePlanQuotaDialogProps> = ({
  isOpen,
  quota,
  resolvedTargetLabel,
  triggerRef,
  onClose,
  onSuccess,
}) => {
  const [isDeleting, setIsDeleting] = useState<boolean>(false);
  const [generalError, setGeneralError] = useState<string | null>(null);

  const confirmBtnRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (isOpen) {
      setGeneralError(null);
    }
  }, [isOpen]);

  if (!quota) return null;

  const handleDelete = async () => {
    setIsDeleting(true);
    setGeneralError(null);

    try {
      await plansApi.deleteQuota(quota.id);
      onSuccess();
      onClose();
    } catch (err: unknown) {
      const { generalError: errGen } = parseApiErrors(err);
      setGeneralError(errGen || "Failed to delete plan quota.");
    } finally {
      setIsDeleting(false);
    }
  };

  const limitDisplay =
    quota.limit_type === "unlimited"
      ? "Unlimited"
      : `${quota.limit_value ?? "0"} ${quota.unit}`;

  return (
    <PlanModalShell
      isOpen={isOpen}
      onClose={onClose}
      isSubmitting={isDeleting}
      title="Remove Plan Quota"
      initialFocusRef={confirmBtnRef}
      triggerRef={triggerRef}
      onActionClick={handleDelete}
      submitLabel="Remove Quota"
      submittingLabel="Removing Quota..."
      submitVariant="danger"
      maxWidth="500px"
    >
      <FormErrorBanner error={generalError} />

      <div
        style={{
          display: "flex",
          gap: "0.75rem",
          alignItems: "flex-start",
          marginBottom: "1rem",
        }}
      >
        <div
          style={{
            padding: "0.5rem",
            borderRadius: "50%",
            background: "rgba(239, 68, 68, 0.1)",
            color: "var(--status-error)",
            flexShrink: 0,
          }}
        >
          <AlertCircleIcon size={24} />
        </div>
        <div>
          <p className="text-body" style={{ margin: 0, fontWeight: 500 }}>
            Are you sure you want to remove the quota{" "}
            <strong>{quota.name}</strong> ({quota.quota_key})?
          </p>
          <p
            className="text-caption"
            style={{ margin: "0.5rem 0 0", color: "var(--text-muted)" }}
          >
            Removing this quota permanently alters the commercial limits for this Draft
            version. It does not delete the underlying catalog target.
          </p>
        </div>
      </div>

      <div className="plan-identity-panel" style={{ marginBottom: "1.5rem" }}>
        <div className="plan-identity-row">
          <span className="meta-label">Scope</span>
          <span className="badge badge-neutral" style={{ textTransform: "capitalize" }}>
            {quota.scope}
          </span>
        </div>
        <div className="plan-identity-row">
          <span className="meta-label">Target</span>
          <span style={{ fontWeight: 500 }}>{resolvedTargetLabel}</span>
        </div>
        <div className="plan-identity-row">
          <span className="meta-label">Limit</span>
          <span style={{ fontWeight: 600 }}>{limitDisplay}</span>
        </div>
        <div className="plan-identity-row">
          <span className="meta-label">Enforcement</span>
          <span>{quota.is_hard_limit ? "Hard Limit" : "Soft Limit"}</span>
        </div>
        <div className="plan-identity-row">
          <span className="meta-label">Reset Period</span>
          <span style={{ textTransform: "capitalize" }}>{quota.reset_period}</span>
        </div>
      </div>
    </PlanModalShell>
  );
};
