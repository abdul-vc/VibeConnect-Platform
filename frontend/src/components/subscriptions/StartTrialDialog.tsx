/**
 * Start Subscription Trial Dialog.
 *
 * Platform Owner dialog to initiate a time-bounded subscription trial for an organization.
 */

import React, { useEffect, useId, useRef, useState } from "react";
import { plansApi } from "../../api/plans.ts";
import { subscriptionsApi } from "../../api/subscriptions.ts";
import type {
  PlanListItem,
  PlanPriceListItem,
  SubscriptionDetail,
} from "../../api/types.ts";
import {
  FormErrorBanner,
  PlanModalShell,
  parseApiErrors,
} from "../plans/PlanModalShell.tsx";
import { formatCurrencyDisplay } from "../../api/plans.ts";

interface StartTrialDialogProps {
  readonly isOpen: boolean;
  readonly onClose: () => void;
  readonly onSuccess: (subscription: SubscriptionDetail) => void;
  readonly organizationId: string;
  readonly organizationName: string;
  readonly triggerRef?: React.RefObject<HTMLElement | null>;
}

export const StartTrialDialog: React.FC<StartTrialDialogProps> = ({
  isOpen,
  onClose,
  onSuccess,
  organizationId,
  organizationName,
  triggerRef,
}) => {
  const baseId = useId();
  const [plans, setPlans] = useState<PlanListItem[]>([]);
  const [selectedPlanId, setSelectedPlanId] = useState<string>("");
  const [prices, setPrices] = useState<PlanPriceListItem[]>([]);
  const [selectedPriceId, setSelectedPriceId] = useState<string>("");
  const [trialDays, setTrialDays] = useState<number>(14);
  const [changeReason, setChangeReason] = useState<string>("");

  const [isLoadingPlans, setIsLoadingPlans] = useState<boolean>(false);
  const [isLoadingPrices, setIsLoadingPrices] = useState<boolean>(false);
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [generalError, setGeneralError] = useState<string | null>(null);

  const planSelectRef = useRef<HTMLSelectElement | null>(null);

  // Fetch eligible plans with active versions on open
  useEffect(() => {
    if (isOpen) {
      setSelectedPlanId("");
      setPrices([]);
      setSelectedPriceId("");
      setTrialDays(14);
      setChangeReason("");
      setFieldErrors({});
      setGeneralError(null);
      setIsSubmitting(false);

      const fetchPlans = async () => {
        setIsLoadingPlans(true);
        try {
          const res = await plansApi.list({ has_active_version: "true", page_size: 100 });
          const eligible = res.results.filter(
            (p) => p.active_version && p.active_version.status === "active"
          );
          setPlans(eligible as PlanListItem[]);
          if (eligible.length > 0) {
            setSelectedPlanId(eligible[0].id);
          }
        } catch {
          setGeneralError("Unable to load commercial plans.");
        } finally {
          setIsLoadingPlans(false);
        }
      };

      fetchPlans();
    }
  }, [isOpen]);

  // When selected plan changes, fetch prices for its active version
  useEffect(() => {
    if (!selectedPlanId) {
      setPrices([]);
      setSelectedPriceId("");
      return;
    }

    const selectedPlan = plans.find((p) => p.id === selectedPlanId);
    if (!selectedPlan?.active_version) {
      setPrices([]);
      setSelectedPriceId("");
      return;
    }

    const fetchPrices = async () => {
      setIsLoadingPrices(true);
      try {
        const res = await plansApi.listPrices(selectedPlan.active_version!.id, { page_size: 50 });
        setPrices(res.results as PlanPriceListItem[]);
        if (res.results.length > 0) {
          setSelectedPriceId(res.results[0].id);
        } else {
          setSelectedPriceId("");
        }
      } catch {
        setGeneralError("Unable to load prices for selected plan.");
      } finally {
        setIsLoadingPrices(false);
      }
    };

    fetchPrices();
  }, [selectedPlanId, plans]);

  const selectedPlan = plans.find((p) => p.id === selectedPlanId);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const errors: Record<string, string> = {};

    if (!selectedPlanId || !selectedPlan?.active_version) {
      errors.plan_version_id = "An active plan version must be selected.";
    }
    if (!selectedPriceId) {
      errors.plan_price_id = "A pricing tier must be selected.";
    }
    if (!trialDays || trialDays < 1 || trialDays > 365) {
      errors.trial_days = "Trial duration must be between 1 and 365 days.";
    }

    if (Object.keys(errors).length > 0) {
      setFieldErrors(errors);
      return;
    }

    setFieldErrors({});
    setGeneralError(null);
    setIsSubmitting(true);

    try {
      const created = await subscriptionsApi.startTrial({
        organization_id: organizationId,
        plan_version_id: selectedPlan!.active_version!.id,
        plan_price_id: selectedPriceId,
        trial_days: Number(trialDays),
        change_reason: changeReason.trim() || undefined,
      });
      onSuccess(created);
      onClose();
    } catch (err: unknown) {
      const { fieldErrors: fErrors, generalError: gError } = parseApiErrors(err);
      setFieldErrors(fErrors);
      setGeneralError(gError || "Failed to start trial subscription.");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <PlanModalShell
      isOpen={isOpen}
      onClose={onClose}
      isSubmitting={isSubmitting}
      title="Start Subscription Trial"
      subtitle={`Initiate a commercial trial for ${organizationName}.`}
      triggerRef={triggerRef}
      initialFocusRef={planSelectRef}
      onSubmit={handleSubmit}
      submitLabel="Start Trial"
      submittingLabel="Starting Trial..."
      submitDisabled={isLoadingPlans || isLoadingPrices || plans.length === 0 || prices.length === 0}
      maxWidth="540px"
    >
      <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
        <FormErrorBanner error={generalError} />

        {/* Plan Selection */}
        <div className="form-group">
          <label htmlFor={`${baseId}-plan`} className="form-label required">
            Commercial Plan
          </label>
          <select
            id={`${baseId}-plan`}
            ref={planSelectRef}
            className={`form-input ${fieldErrors.plan_version_id ? "input-error" : ""}`}
            value={selectedPlanId}
            onChange={(e) => setSelectedPlanId(e.target.value)}
            disabled={isSubmitting || isLoadingPlans}
          >
            {plans.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name} ({p.code}) — Active v{p.active_version?.version}
              </option>
            ))}
          </select>
          {fieldErrors.plan_version_id && (
            <span className="form-error-text">{fieldErrors.plan_version_id}</span>
          )}
          {plans.length === 0 && !isLoadingPlans && (
            <span className="text-caption" style={{ color: "var(--status-warning)" }}>
              No plans with an active version are currently available.
            </span>
          )}
        </div>

        {/* Pricing Tier Selection */}
        <div className="form-group">
          <label htmlFor={`${baseId}-price`} className="form-label required">
            Target Price &amp; Billing Interval
          </label>
          <select
            id={`${baseId}-price`}
            className={`form-input ${fieldErrors.plan_price_id ? "input-error" : ""}`}
            value={selectedPriceId}
            onChange={(e) => setSelectedPriceId(e.target.value)}
            disabled={isSubmitting || isLoadingPrices || prices.length === 0}
          >
            {prices.map((pr) => (
              <option key={pr.id} value={pr.id}>
                {formatCurrencyDisplay(pr.amount, pr.currency)} / {pr.billing_interval} ({pr.currency})
              </option>
            ))}
          </select>
          {fieldErrors.plan_price_id && (
            <span className="form-error-text">{fieldErrors.plan_price_id}</span>
          )}
          {prices.length === 0 && !isLoadingPrices && selectedPlanId && (
            <span className="text-caption" style={{ color: "var(--status-warning)" }}>
              No pricing options configured for the active version of this plan.
            </span>
          )}
        </div>

        {/* Trial Days */}
        <div className="form-group">
          <label htmlFor={`${baseId}-days`} className="form-label required">
            Trial Duration (Days)
          </label>
          <input
            id={`${baseId}-days`}
            type="number"
            min={1}
            max={365}
            className={`form-input ${fieldErrors.trial_days ? "input-error" : ""}`}
            value={trialDays}
            onChange={(e) => setTrialDays(parseInt(e.target.value, 10) || 0)}
            disabled={isSubmitting}
            aria-describedby={`${baseId}-days-hint`}
          />
          <span id={`${baseId}-days-hint`} className="form-hint">
            Standard trial window is 14 days. Trial terminates at 23:59:59 UTC on expiry.
          </span>
          {fieldErrors.trial_days && (
            <span className="form-error-text">{fieldErrors.trial_days}</span>
          )}
        </div>

        {/* Optional Change Reason */}
        <div className="form-group">
          <label htmlFor={`${baseId}-reason`} className="form-label">
            Audit Reason (Optional)
          </label>
          <input
            id={`${baseId}-reason`}
            type="text"
            maxLength={255}
            className="form-input"
            placeholder="e.g., Q3 enterprise customer evaluation"
            value={changeReason}
            onChange={(e) => setChangeReason(e.target.value)}
            disabled={isSubmitting}
          />
        </div>
      </div>
    </PlanModalShell>
  );
};
