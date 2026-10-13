/**
 * Create Active Subscription Dialog.
 *
 * Platform Owner dialog to directly provision an active paid subscription for an organization.
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

interface CreateSubscriptionDialogProps {
  readonly isOpen: boolean;
  readonly onClose: () => void;
  readonly onSuccess: (subscription: SubscriptionDetail) => void;
  readonly organizationId: string;
  readonly organizationName: string;
  readonly triggerRef?: React.RefObject<HTMLElement | null>;
}

export const CreateSubscriptionDialog: React.FC<CreateSubscriptionDialogProps> = ({
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
  const [currentPeriodStart, setCurrentPeriodStart] = useState<string>("");
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
      setCurrentPeriodStart("");
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

    if (Object.keys(errors).length > 0) {
      setFieldErrors(errors);
      return;
    }

    setFieldErrors({});
    setGeneralError(null);
    setIsSubmitting(true);

    try {
      const created = await subscriptionsApi.create({
        organization_id: organizationId,
        plan_version_id: selectedPlan!.active_version!.id,
        plan_price_id: selectedPriceId,
        current_period_start: currentPeriodStart.trim() ? new Date(currentPeriodStart).toISOString() : undefined,
        change_reason: changeReason.trim() || undefined,
      });
      onSuccess(created);
      onClose();
    } catch (err: unknown) {
      const { fieldErrors: fErrors, generalError: gError } = parseApiErrors(err);
      setFieldErrors(fErrors);
      setGeneralError(gError || "Failed to create subscription.");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <PlanModalShell
      isOpen={isOpen}
      onClose={onClose}
      isSubmitting={isSubmitting}
      title="Create Paid Subscription"
      subtitle={`Activate a commercial plan for ${organizationName}.`}
      triggerRef={triggerRef}
      initialFocusRef={planSelectRef}
      onSubmit={handleSubmit}
      submitLabel="Create Subscription"
      submittingLabel="Creating Subscription..."
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
            Price &amp; Billing Interval
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
        </div>

        {/* Current Period Start (Optional) */}
        <div className="form-group">
          <label htmlFor={`${baseId}-period-start`} className="form-label">
            Period Start Date (Optional)
          </label>
          <input
            id={`${baseId}-period-start`}
            type="datetime-local"
            className="form-input"
            value={currentPeriodStart}
            onChange={(e) => setCurrentPeriodStart(e.target.value)}
            disabled={isSubmitting}
            aria-describedby={`${baseId}-start-hint`}
          />
          <span id={`${baseId}-start-hint`} className="form-hint">
            Leave blank to begin period immediately. Period end is calculated based on interval.
          </span>
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
            placeholder="e.g., Direct purchase order conversion"
            value={changeReason}
            onChange={(e) => setChangeReason(e.target.value)}
            disabled={isSubmitting}
          />
        </div>
      </div>
    </PlanModalShell>
  );
};
