/**
 * Commercial Pricing Dialogs.
 *
 * Implements accessible, keyboard-trapped, focus-restoring modals for:
 * - Create Price (INR, USD, EUR, GBP; Monthly, Quarterly, Annual)
 * - Edit Price (amount only, exact string preservation)
 * - Delete Price confirmation (readiness impact warning)
 */

import React, { useEffect, useRef, useState } from "react";
import { formatCurrencyDisplay, plansApi } from "../../api/plans.ts";
import type {
  PlanBillingInterval,
  PlanCurrency,
  PlanPriceListItem,
} from "../../api/types.ts";
import { AlertCircleIcon } from "../Icons.tsx";
import { FormErrorBanner, parseApiErrors, PlanModalShell } from "./PlanModalShell.tsx";

// Strict Money Regex: exactly 2 decimal places, no signs, no commas, no leading zeros before decimal unless '0'
export const MONEY_REGEX = /^(?:0|[1-9][0-9]*)\.[0-9]{2}$/;

export interface PriceValidationResult {
  readonly isValid: boolean;
  readonly error?: string;
}

/**
 * Pure price validation function.
 *
 * Rules:
 * 1. Must be a string.
 * 2. Cannot be empty.
 * 3. Whitespace rejected (no trim normalization allowed: `amount !== amount.trim()`).
 * 4. Must match canonical format: /^(?:0|[1-9][0-9]*)\.[0-9]{2}$/
 * 5. Upper bound: max 9999999999.99 (whole part length <= 10 digits without floating-point conversion).
 */
export function validatePriceAmount(amount: unknown): PriceValidationResult {
  if (typeof amount !== "string") {
    return { isValid: false, error: "Price amount must be provided as a string." };
  }
  if (!amount) {
    return { isValid: false, error: "Price amount is required." };
  }
  if (amount !== amount.trim()) {
    return { isValid: false, error: "Price amount cannot contain leading or trailing whitespace." };
  }
  if (!MONEY_REGEX.test(amount)) {
    return {
      isValid: false,
      error: "Price amount must be a valid non-negative decimal with exactly 2 decimal places (e.g., 0.00, 19.99).",
    };
  }
  const [whole] = amount.split(".");
  if (whole.length > 10) {
    return {
      isValid: false,
      error: "Price amount cannot exceed 9999999999.99.",
    };
  }
  return { isValid: true };
}

export function isValidMoneyString(val: string): boolean {
  return validatePriceAmount(val).isValid;
}

/**
 * Normalizes a raw price string to the canonical 2-decimal format.
 * Examples: "51" → "51.00", "51.5" → "51.50", "" → ""
 * Invalid / non-numeric input is returned as-is (let validation surface the error).
 */
export function normalizeAmountOnBlur(raw: string): string {
  const trimmed = raw.trim();
  if (!trimmed) return trimmed;
  const num = Number(trimmed);
  if (isNaN(num) || !isFinite(num)) return trimmed;
  // Guard upper bound before formatting
  if (num < 0 || num > 9999999999.99) return trimmed;
  return num.toFixed(2);
}

const SUPPORTED_CURRENCIES: readonly PlanCurrency[] = ["USD", "EUR", "GBP", "INR"];
const SUPPORTED_INTERVALS: readonly { value: PlanBillingInterval; label: string }[] = [
  { value: "monthly", label: "Monthly" },
  { value: "quarterly", label: "Quarterly" },
  { value: "annual", label: "Annual" },
];

// ---------------------------------------------------------------------------
// 1. Create Price Dialog
// ---------------------------------------------------------------------------

interface CreatePlanPriceDialogProps {
  readonly isOpen: boolean;
  readonly onClose: () => void;
  readonly onSuccess: () => void;
  readonly versionId: string;
  readonly triggerRef?: React.RefObject<HTMLElement | null>;
}

export const CreatePlanPriceDialog: React.FC<CreatePlanPriceDialogProps> = ({
  isOpen,
  onClose,
  onSuccess,
  versionId,
  triggerRef,
}) => {
  const [currency, setCurrency] = useState<PlanCurrency>("USD");
  const [billingInterval, setBillingInterval] = useState<PlanBillingInterval>("monthly");
  const [amount, setAmount] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [generalError, setGeneralError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const initialFocusRef = useRef<HTMLSelectElement | null>(null);

  useEffect(() => {
    if (isOpen) {
      setCurrency("USD");
      setBillingInterval("monthly");
      setAmount("");
      setIsSubmitting(false);
      setGeneralError(null);
      setFieldErrors({});
    }
  }, [isOpen]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setGeneralError(null);
    setFieldErrors({});

    const validation = validatePriceAmount(amount);
    if (!validation.isValid) {
      setFieldErrors({ amount: validation.error || "Invalid price amount." });
      return;
    }

    try {
      setIsSubmitting(true);
      await plansApi.createPrice(versionId, {
        currency,
        billing_interval: billingInterval,
        amount,
      });
      onSuccess();
      onClose();
    } catch (err: unknown) {
      const { fieldErrors: errFields, generalError: errGen } = parseApiErrors(err);
      setFieldErrors(errFields);
      setGeneralError(errGen || "Failed to create price. Please check your inputs.");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <PlanModalShell
      isOpen={isOpen}
      onClose={onClose}
      isSubmitting={isSubmitting}
      title="Add Plan Price"
      subtitle="Configure recurring commercial pricing for this plan version."
      onSubmit={handleSubmit}
      submitLabel="Add Price"
      submittingLabel="Adding Price..."
      triggerRef={triggerRef}
      initialFocusRef={initialFocusRef}
    >
      <FormErrorBanner error={generalError} />

      <div className="form-group">
        <label htmlFor="create-price-currency" className="form-label">
          Currency <span className="text-danger">*</span>
        </label>
        <select
          id="create-price-currency"
          ref={initialFocusRef}
          className={`form-input form-select ${fieldErrors.currency ? "input-error" : ""}`}
          value={currency}
          onChange={(e) => setCurrency(e.target.value as PlanCurrency)}
          disabled={isSubmitting}
        >
          {SUPPORTED_CURRENCIES.map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </select>
        {fieldErrors.currency && <span className="field-error">{fieldErrors.currency}</span>}
      </div>

      <div className="form-group">
        <label htmlFor="create-price-interval" className="form-label">
          Billing Interval <span className="text-danger">*</span>
        </label>
        <select
          id="create-price-interval"
          className={`form-input form-select ${fieldErrors.billing_interval ? "input-error" : ""}`}
          value={billingInterval}
          onChange={(e) => setBillingInterval(e.target.value as PlanBillingInterval)}
          disabled={isSubmitting}
        >
          {SUPPORTED_INTERVALS.map((inv) => (
            <option key={inv.value} value={inv.value}>
              {inv.label}
            </option>
          ))}
        </select>
        {fieldErrors.billing_interval && (
          <span className="field-error">{fieldErrors.billing_interval}</span>
        )}
      </div>

      <div className="form-group">
        <label htmlFor="create-price-amount" className="form-label">
          Amount <span className="text-danger">*</span>
        </label>
        <input
          id="create-price-amount"
          type="text"
          inputMode="decimal"
          className={`form-input ${fieldErrors.amount ? "input-error" : ""}`}
          placeholder="e.g. 19.99"
          value={amount}
          onChange={(e) => setAmount(e.target.value)}
          onBlur={(e) => setAmount(normalizeAmountOnBlur(e.target.value))}
          disabled={isSubmitting}
          aria-describedby="create-price-amount-hint"
        />
        <span id="create-price-amount-hint" className="form-hint">
          Enter any amount (e.g. 51, 19.99). Normalized to 2 decimal places.
        </span>
        {fieldErrors.amount && <span className="field-error">{fieldErrors.amount}</span>}
      </div>
    </PlanModalShell>
  );
};

// ---------------------------------------------------------------------------
// 2. Edit Price Dialog
// ---------------------------------------------------------------------------

interface EditPlanPriceDialogProps {
  readonly isOpen: boolean;
  readonly onClose: () => void;
  readonly onSuccess: () => void;
  readonly price: PlanPriceListItem | null;
  readonly triggerRef?: React.RefObject<HTMLElement | null>;
}

export const EditPlanPriceDialog: React.FC<EditPlanPriceDialogProps> = ({
  isOpen,
  onClose,
  onSuccess,
  price,
  triggerRef,
}) => {
  const [amount, setAmount] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [generalError, setGeneralError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const initialFocusRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    if (isOpen && price) {
      setAmount(price.amount);
      setIsSubmitting(false);
      setGeneralError(null);
      setFieldErrors({});
    }
  }, [isOpen, price]);

  if (!price) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setGeneralError(null);
    setFieldErrors({});

    const validation = validatePriceAmount(amount);
    if (!validation.isValid) {
      setFieldErrors({ amount: validation.error || "Invalid price amount." });
      return;
    }

    if (amount === price.amount) {
      setGeneralError("Price amount is unchanged.");
      return;
    }

    try {
      setIsSubmitting(true);
      await plansApi.updatePrice(price.id, { amount });
      onSuccess();
      onClose();
    } catch (err: unknown) {
      const { fieldErrors: errFields, generalError: errGen } = parseApiErrors(err);
      setFieldErrors(errFields);
      setGeneralError(errGen || "Failed to update price.");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <PlanModalShell
      isOpen={isOpen}
      onClose={onClose}
      isSubmitting={isSubmitting}
      title="Edit Plan Price"
      subtitle="Update amount for this pricing interval. Currency and interval are immutable."
      onSubmit={handleSubmit}
      submitLabel="Save Amount"
      submittingLabel="Saving..."
      triggerRef={triggerRef}
      initialFocusRef={initialFocusRef}
    >
      <FormErrorBanner error={generalError} />

      <div className="form-group">
        <label className="form-label">Currency</label>
        <input
          type="text"
          className="form-input"
          value={price.currency}
          readOnly
          disabled
        />
      </div>

      <div className="form-group">
        <label className="form-label">Billing Interval</label>
        <input
          type="text"
          className="form-input"
          value={price.billing_interval.toUpperCase()}
          readOnly
          disabled
        />
      </div>

      <div className="form-group">
        <label htmlFor="edit-price-amount" className="form-label">
          Amount <span className="text-danger">*</span>
        </label>
        <input
          id="edit-price-amount"
          ref={initialFocusRef}
          type="text"
          inputMode="decimal"
          className={`form-input ${fieldErrors.amount ? "input-error" : ""}`}
          value={amount}
          onChange={(e) => setAmount(e.target.value)}
          onBlur={(e) => setAmount(normalizeAmountOnBlur(e.target.value))}
          disabled={isSubmitting}
        />
        <span className="form-hint">Enter any amount (e.g. 51, 19.99). Normalized to 2 decimal places.</span>
        {fieldErrors.amount && <span className="field-error">{fieldErrors.amount}</span>}
      </div>
    </PlanModalShell>
  );
};

// ---------------------------------------------------------------------------
// 3. Delete Price Dialog
// ---------------------------------------------------------------------------

interface DeletePlanPriceDialogProps {
  readonly isOpen: boolean;
  readonly onClose: () => void;
  readonly onSuccess: () => void;
  readonly price: PlanPriceListItem | null;
  readonly versionNumber: number;
  readonly triggerRef?: React.RefObject<HTMLElement | null>;
}

export const DeletePlanPriceDialog: React.FC<DeletePlanPriceDialogProps> = ({
  isOpen,
  onClose,
  onSuccess,
  price,
  versionNumber,
  triggerRef,
}) => {
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [generalError, setGeneralError] = useState<string | null>(null);

  useEffect(() => {
    if (isOpen) {
      setIsSubmitting(false);
      setGeneralError(null);
    }
  }, [isOpen]);

  if (!price) return null;

  const handleConfirm = async () => {
    try {
      setIsSubmitting(true);
      setGeneralError(null);
      await plansApi.deletePrice(price.id);
      onSuccess();
      onClose();
    } catch (err: unknown) {
      const { generalError: errGen } = parseApiErrors(err);
      setGeneralError(errGen || "Failed to remove price.");
      setIsSubmitting(false);
    }
  };

  return (
    <PlanModalShell
      isOpen={isOpen}
      onClose={onClose}
      isSubmitting={isSubmitting}
      title="Remove Plan Price"
      subtitle={`Remove ${formatCurrencyDisplay(price.amount, price.currency)} (${price.billing_interval}) from Version ${versionNumber}`}
      onActionClick={handleConfirm}
      submitLabel="Remove Price"
      submittingLabel="Removing..."
      submitVariant="danger"
      triggerRef={triggerRef}
    >
      <FormErrorBanner error={generalError} />

      <div className="alert-box alert-warning" role="alert">
        <AlertCircleIcon size={16} style={{ flexShrink: 0 }} />
        <span>
          Removing this price may prevent Version {versionNumber} from reaching activation readiness
          if no other prices remain configured.
        </span>
      </div>

      <p className="dialog-text">
        Are you sure you want to remove the <strong>{price.billing_interval}</strong> price of{" "}
        <strong>
          {formatCurrencyDisplay(price.amount, price.currency)}
        </strong>{" "}
        from Version {versionNumber}?
      </p>
    </PlanModalShell>
  );
};
