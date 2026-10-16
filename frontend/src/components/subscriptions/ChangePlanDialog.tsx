/**
 * Change Subscription Plan Dialog.
 *
 * Platform Owner dialog to upgrade/downgrade/switch subscription plans with immediate successor cutover.
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

interface ChangePlanDialogProps {
  readonly isOpen: boolean;
  readonly onClose: () => void;
  readonly onSuccess: (newSubscription: SubscriptionDetail) => void;
  readonly subscription: SubscriptionDetail;
  readonly triggerRef?: React.RefObject<HTMLElement | null>;
}

export const ChangePlanDialog: React.FC<ChangePlanDialogProps> = ({
  isOpen,
  onClose,
  onSuccess,
  subscription,
  triggerRef,
}) => {
  const baseId = useId();
  const [plans, setPlans] = useState<PlanListItem[]>([]);
  const [selectedPlanId, setSelectedPlanId] = useState<string>("");
  const [prices, setPrices] = useState<PlanPriceListItem[]>([]);
  const [selectedPriceId, setSelectedPriceId] = useState<string>("");
  const [changeReason, setChangeReason] = useState<string>("");

  const [isLoadingPlans, setIsLoadingPlans] = useState<boolean>(false);
  const [isLoadingPrices, setIsLoadingPrices] = useState<boolean>(false);
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [generalError, setGeneralError] = useState<string | null>(null);

  const planSelectRef = useRef<HTMLSelectElement | null>(null);

  // Fetch eligible plans on open
  useEffect(() => {
    if (isOpen) {
      setSelectedPlanId("");
      setPrices([]);
      setSelectedPriceId("");
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

  // When selected plan changes, fetch prices for active version
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
      errors.new_plan_version_id = "A target active plan version must be selected.";
    }
    if (!selectedPriceId) {
      errors.new_plan_price_id = "A target price tier must be selected.";
    }

    if (Object.keys(errors).length > 0) {
      setFieldErrors(errors);
      return;
    }

    setFieldErrors({});
    setGeneralError(null);
    setIsSubmitting(true);

    try {
      const successor = await subscriptionsApi.changePlan(subscription.id, {
        new_plan_version_id: selectedPlan!.active_version!.id,
        new_plan_price_id: selectedPriceId,
        change_reason: changeReason.trim() || undefined,
      });
      onSuccess(successor);
      onClose();
    } catch (err: unknown) {
      const { fieldErrors: fErrors, generalError: gError } = parseApiErrors(err);
      setFieldErrors(fErrors);
      setGeneralError(gError || "Failed to execute plan change.");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <PlanModalShell
      isOpen={isOpen}
      onClose={onClose}
      isSubmitting={isSubmitting}
      title="Change Subscription Plan"
      subtitle={`Transition ${subscription.organization_name} to a new plan tier.`}
      triggerRef={triggerRef}
      initialFocusRef={planSelectRef}
      onSubmit={handleSubmit}
      submitLabel="Confirm Plan Change"
      submittingLabel="Transitioning..."
      submitDisabled={isLoadingPlans || isLoadingPrices || plans.length === 0 || prices.length === 0}
      maxWidth="540px"
    >
      <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
        <FormErrorBanner error={generalError} />

        {/* Current Plan Summary Pill */}
        <div
          style={{
            padding: "0.75rem 1rem",
            background: "var(--glass-surface)",
            border: "1px solid var(--border-glass)",
            borderRadius: "10px",
            display: "flex",
            flexDirection: "column",
            gap: "0.25rem",
          }}
        >
          <span className="text-caption" style={{ fontWeight: 600, color: "var(--text-muted)" }}>
            Current Active Plan Snapshot
          </span>
          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", flexWrap: "wrap" }}>
            <span style={{ fontWeight: 600, color: "var(--text-primary)" }}>
              {subscription.plan_name_snapshot} ({subscription.plan_code_snapshot})
            </span>
            <span className="product-code-pill">v{subscription.version_number_snapshot}</span>
            <span className="text-caption">
              {formatCurrencyDisplay(subscription.amount, subscription.currency)} / {subscription.billing_interval}
            </span>
          </div>
        </div>

        {/* Informational Alert */}
        <div className="alert-box alert-info" role="note">
          <span>
            Executing a plan change terminates the current subscription immediately, creates an active successor subscription linked as a historical predecessor, and generates a fresh entitlement snapshot.
          </span>
        </div>

        {/* New Plan Selection */}
        <div className="form-group">
          <label htmlFor={`${baseId}-plan`} className="form-label required">
            Target Commercial Plan
          </label>
          <select
            id={`${baseId}-plan`}
            ref={planSelectRef}
            className={`form-input ${fieldErrors.new_plan_version_id ? "input-error" : ""}`}
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
          {fieldErrors.new_plan_version_id && (
            <span className="form-error-text">{fieldErrors.new_plan_version_id}</span>
          )}
        </div>

        {/* New Pricing Tier Selection */}
        <div className="form-group">
          <label htmlFor={`${baseId}-price`} className="form-label required">
            Target Price &amp; Billing Interval
          </label>
          <select
            id={`${baseId}-price`}
            className={`form-input ${fieldErrors.new_plan_price_id ? "input-error" : ""}`}
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
          {fieldErrors.new_plan_price_id && (
            <span className="form-error-text">{fieldErrors.new_plan_price_id}</span>
          )}
        </div>

        {/* Optional Change Reason */}
        <div className="form-group">
          <label htmlFor={`${baseId}-reason`} className="form-label">
            Change Reason (Optional)
          </label>
          <input
            id={`${baseId}-reason`}
            type="text"
            maxLength={255}
            className="form-input"
            placeholder="e.g., Annual renewal upgrade"
            value={changeReason}
            onChange={(e) => setChangeReason(e.target.value)}
            disabled={isSubmitting}
          />
        </div>
      </div>
    </PlanModalShell>
  );
};
