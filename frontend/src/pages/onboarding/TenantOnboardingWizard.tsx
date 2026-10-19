/**
 * Tenant Onboarding Wizard Page (Phase 3B).
 *
 * Platform Owner wizard for provisioning new tenant organizations end-to-end:
 * 1. Organization Profile (code, name, description)
 * 2. Admin Setup (email, full name)
 * 3. Commercial Plan Selection (active plans & prices, trial toggle)
 * 4. Review & Confirm (summary, idempotent provisioning, resume state)
 * 5. Completed confirmation with direct navigation
 */

import React, { useCallback, useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { onboardingApi } from "../../api/onboarding.ts";
import { plansApi } from "../../api/plans.ts";
import type {
  OnboardingStepName,
  PlanListItem,
  PlanPriceListItem,
  TenantOnboardingCase,
} from "../../api/types.ts";
import { AppShell } from "../../components/AppShell.tsx";
import {
  AlertCircleIcon,
  BuildingIcon,
  CheckCircleIcon,
  LayersIcon,
  ShieldCheckIcon,
  UserIcon,
} from "../../components/Icons.tsx";

const STEPS: { key: OnboardingStepName; label: string; icon: React.ReactNode }[] = [
  { key: "organization_profile", label: "Organization", icon: <BuildingIcon size={16} /> },
  { key: "admin_setup", label: "Administrator", icon: <UserIcon size={16} /> },
  { key: "plan_selection", label: "Plan & Pricing", icon: <LayersIcon size={16} /> },
  { key: "review_confirm", label: "Review & Provision", icon: <CheckCircleIcon size={16} /> },
];

export const TenantOnboardingWizard: React.FC = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();
  const caseIdFromUrl = searchParams.get("case_id");

  const [currentCase, setCurrentCase] = useState<TenantOnboardingCase | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  const [activationUrl, setActivationUrl] = useState<string | null>(null);
  const [copiedLink, setCopiedLink] = useState<boolean>(false);
  const [generalError, setGeneralError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  // Step 1: Organization State
  const [orgCode, setOrgCode] = useState<string>("");
  const [orgName, setOrgName] = useState<string>("");
  const [orgDesc, setOrgDesc] = useState<string>("");

  // Step 2: Admin State
  const [adminEmail, setAdminEmail] = useState<string>("");
  const [adminFullName, setAdminFullName] = useState<string>("");

  // Step 3: Plan Selection State
  const [plans, setPlans] = useState<readonly PlanListItem[]>([]);
  const [selectedPlanVersionId, setSelectedPlanVersionId] = useState<string>("");
  const [availablePrices, setAvailablePrices] = useState<readonly PlanPriceListItem[]>([]);
  const [selectedPriceId, setSelectedPriceId] = useState<string>("");
  const [isTrial, setIsTrial] = useState<boolean>(true);

  // Initialize or resume case
  const initializeCase = useCallback(async () => {
    setIsLoading(true);
    setGeneralError(null);
    try {
      let caseData: TenantOnboardingCase;
      if (caseIdFromUrl) {
        caseData = await onboardingApi.getCase(caseIdFromUrl);
      } else {
        caseData = await onboardingApi.createCase();
        setSearchParams({ case_id: caseData.id }, { replace: true });
      }
      setCurrentCase(caseData);
      setOrgCode(caseData.organization_code || "");
      setOrgName(caseData.organization_name || "");
      setOrgDesc(caseData.organization_description || "");
      setAdminEmail(caseData.admin_email || "");
      setAdminFullName(caseData.admin_full_name || "");
      setSelectedPlanVersionId(caseData.plan_version || "");
      setSelectedPriceId(caseData.plan_price || "");
      setIsTrial(caseData.is_trial);

      // Load available plans for selection step
      const plansRes = await plansApi.list({ has_active_version: "true" });
      setPlans(plansRes.results);
    } catch {
      setGeneralError("Failed to initialize or resume onboarding workflow. Please try again.");
    } finally {
      setIsLoading(false);
    }
  }, [caseIdFromUrl, setSearchParams]);

  useEffect(() => {
    void initializeCase();
  }, [initializeCase]);

  // Load prices when plan version selected
  useEffect(() => {
    if (!selectedPlanVersionId) {
      setAvailablePrices([]);
      return;
    }
    const loadPrices = async () => {
      try {
        const pricesRes = await plansApi.listPrices(selectedPlanVersionId);
        setAvailablePrices(pricesRes.results);
        if (pricesRes.results.length > 0 && !selectedPriceId) {
          setSelectedPriceId(pricesRes.results[0].id);
        }
      } catch {
        setAvailablePrices([]);
      }
    };
    void loadPrices();
  }, [selectedPlanVersionId, selectedPriceId]);

  const handleNextFromOrg = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!currentCase) return;
    const errors: Record<string, string> = {};
    if (!orgCode.trim()) errors.orgCode = "Organization code is required.";
    else if (!/^[a-z0-9]+(?:[-_][a-z0-9]+)*$/.test(orgCode.trim())) {
      errors.orgCode = "Code must be lowercase alphanumeric with hyphens or underscores.";
    }
    if (!orgName.trim()) errors.orgName = "Organization name is required.";
    if (Object.keys(errors).length > 0) {
      setFieldErrors(errors);
      return;
    }

    setFieldErrors({});
    setIsSubmitting(true);
    setGeneralError(null);
    try {
      const updated = await onboardingApi.transitionStep(currentCase.id, {
        target_step: "admin_setup",
        step_data: {
          organization_code: orgCode.trim(),
          organization_name: orgName.trim(),
          organization_description: orgDesc.trim(),
        },
      });
      setCurrentCase(updated);
    } catch (err: unknown) {
      const errorObj = err as { data?: Record<string, string[]> };
      if (errorObj?.data?.organization_code) {
        setFieldErrors({ orgCode: errorObj.data.organization_code[0] });
      } else {
        setGeneralError("Failed to save organization step. Please try again.");
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleNextFromAdmin = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!currentCase) return;
    const errors: Record<string, string> = {};
    if (!adminEmail.trim()) errors.adminEmail = "Administrator email is required.";
    else if (!/\S+@\S+\.\S+/.test(adminEmail.trim())) {
      errors.adminEmail = "Please enter a valid email address.";
    }
    if (Object.keys(errors).length > 0) {
      setFieldErrors(errors);
      return;
    }

    setFieldErrors({});
    setIsSubmitting(true);
    setGeneralError(null);
    try {
      const updated = await onboardingApi.transitionStep(currentCase.id, {
        target_step: "plan_selection",
        step_data: {
          admin_email: adminEmail.trim(),
          admin_full_name: adminFullName.trim(),
        },
      });
      setCurrentCase(updated);
    } catch {
      setGeneralError("Failed to save administrator details.");
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleNextFromPlan = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!currentCase) return;

    setFieldErrors({});
    setIsSubmitting(true);
    setGeneralError(null);
    try {
      const updated = await onboardingApi.transitionStep(currentCase.id, {
        target_step: "review_confirm",
        step_data: {
          plan_version_id: selectedPlanVersionId || null,
          plan_price_id: selectedPriceId || null,
          is_trial: isTrial,
        },
      });
      setCurrentCase(updated);
    } catch {
      setGeneralError("Failed to save plan configuration.");
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleFinalProvision = async () => {
    if (!currentCase) return;
    setIsSubmitting(true);
    setGeneralError(null);
    try {
      const updated = await onboardingApi.transitionStep(currentCase.id, {
        target_step: "completed",
        step_data: {},
      });
      setCurrentCase(updated);
      if (updated.initial_admin_activation_url) {
        setActivationUrl(updated.initial_admin_activation_url);
      }
    } catch (err: unknown) {
      const errorObj = err as { data?: { detail?: string } };
      setGeneralError(errorObj?.data?.detail || "Provisioning failed. Please check inputs and retry.");
    } finally {
      setIsSubmitting(false);
    }
  };

  const currentStep = currentCase?.current_step || "organization_profile";
  const isCompleted = currentCase?.status === "completed";

  return (
    <AppShell>
      <div style={{ maxWidth: "860px", margin: "0 auto", display: "flex", flexDirection: "column", gap: "2rem" }}>
        {/* Wizard Header */}
        <div>
          <h1 className="heading-hero" style={{ margin: 0, fontSize: "1.75rem" }}>
            Tenant Onboarding Wizard
          </h1>
          <p className="text-body" style={{ marginTop: "0.5rem" }}>
            Provision a new tenant organization with isolated workspace boundaries, administrator credentials, and packaging defaults.
          </p>
        </div>

        {/* Step Indicator */}
        <div
          role="navigation"
          aria-label="Onboarding Progress"
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(4, 1fr)",
            gap: "0.75rem",
          }}
        >
          {STEPS.map((step, idx) => {
            const stepOrder = ["organization_profile", "admin_setup", "plan_selection", "review_confirm", "completed"];
            const currentIdx = stepOrder.indexOf(currentStep);
            const thisIdx = stepOrder.indexOf(step.key);
            const isDone = thisIdx < currentIdx || isCompleted;
            const isCurrent = currentStep === step.key && !isCompleted;

            return (
              <div
                key={step.key}
                className="glass-panel"
                style={{
                  padding: "0.875rem",
                  display: "flex",
                  alignItems: "center",
                  gap: "0.625rem",
                  borderLeft: isCurrent
                    ? "3px solid var(--brand-primary)"
                    : isDone
                    ? "3px solid var(--status-success)"
                    : "3px solid transparent",
                  opacity: isCurrent || isDone ? 1 : 0.6,
                }}
              >
                <div
                  style={{
                    color: isDone ? "var(--status-success)" : isCurrent ? "var(--brand-primary)" : "var(--text-muted)",
                    display: "flex",
                  }}
                >
                  {isDone ? <CheckCircleIcon size={18} /> : step.icon}
                </div>
                <div style={{ minWidth: 0 }}>
                  <div style={{ fontSize: "0.7rem", color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.05em" }}>
                    Step {idx + 1}
                  </div>
                  <div style={{ fontSize: "0.8125rem", fontWeight: isCurrent ? 700 : 500, color: "var(--text-primary)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                    {step.label}
                  </div>
                </div>
              </div>
            );
          })}
        </div>

        {/* Global Error Banner */}
        {generalError && (
          <div className="alert-banner alert-banner-error" role="alert" style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
            <AlertCircleIcon size={18} />
            <span>{generalError}</span>
          </div>
        )}

        {/* Step Content */}
        {isLoading ? (
          <div className="glass-panel" style={{ padding: "3rem", textAlign: "center", color: "var(--text-secondary)" }}>
            Loading onboarding workspace…
          </div>
        ) : isCompleted ? (
          /* Step 5: Completed Screen */
          <div className="glass-panel-elevated" style={{ padding: "2.5rem", textAlign: "center" }}>
            <div style={{ color: "var(--status-success)", marginBottom: "1rem" }}>
              <CheckCircleIcon size={48} />
            </div>
            <h2 className="heading-title" style={{ fontSize: "1.5rem", margin: "0 0 0.5rem 0" }}>
              Organization Successfully Provisioned!
            </h2>
            <p className="text-body" style={{ maxWidth: "540px", margin: "0 auto 1.5rem auto" }}>
              <strong>{currentCase?.organization_name}</strong> (<code>{currentCase?.organization_code}</code>) is fully configured with administrator privileges assigned to <strong>{currentCase?.admin_email}</strong>.
            </p>

            {activationUrl && (
              <div
                className="glass-panel"
                style={{
                  maxWidth: "580px",
                  margin: "0 auto 1.75rem auto",
                  padding: "1.25rem",
                  textAlign: "left",
                  background: "rgba(99, 102, 241, 0.08)",
                  border: "1px solid rgba(99, 102, 241, 0.25)",
                  borderRadius: "8px",
                }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.4rem", color: "var(--brand-primary, #6366f1)", fontWeight: 600, fontSize: "0.875rem" }}>
                  <ShieldCheckIcon size={18} />
                  <span>Initial Tenant Admin Activation Link</span>
                </div>
                <p className="text-secondary" style={{ fontSize: "0.8125rem", margin: "0 0 0.75rem 0", lineHeight: 1.5 }}>
                  Bearer secret: Available at issuance if email delivery is delayed. Valid for single-use activation.
                </p>
                <div style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
                  <input
                    type="text"
                    readOnly
                    value={activationUrl}
                    className="input-field"
                    style={{ flex: 1, fontSize: "0.8125rem", fontFamily: "monospace" }}
                  />
                  <button
                    type="button"
                    className="btn btn-secondary"
                    onClick={() => {
                      if (typeof navigator !== "undefined" && navigator.clipboard) {
                        void navigator.clipboard.writeText(activationUrl);
                        setCopiedLink(true);
                        setTimeout(() => setCopiedLink(false), 2500);
                      }
                    }}
                    style={{ whiteSpace: "nowrap" }}
                  >
                    {copiedLink ? "Copied! ✓" : "Copy Link"}
                  </button>
                </div>
              </div>
            )}

            <div style={{ display: "flex", gap: "1rem", justifyContent: "center" }}>
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => navigate("/organizations")}
              >
                View Organization Registry
              </button>
              <button
                type="button"
                className="btn btn-primary"
                onClick={() => {
                  setActivationUrl(null);
                  setCopiedLink(false);
                  setSearchParams({}, { replace: true });
                  void initializeCase();
                }}
              >
                Onboard Another Organization
              </button>
            </div>
          </div>
        ) : currentStep === "organization_profile" ? (
          /* Step 1: Organization Profile Form */
          <form onSubmit={handleNextFromOrg} className="glass-panel" style={{ padding: "2rem", display: "flex", flexDirection: "column", gap: "1.5rem" }}>
            <div>
              <h2 className="heading-title" style={{ fontSize: "1.25rem", margin: "0 0 0.25rem 0" }}>
                Step 1: Organization Profile
              </h2>
              <p className="text-body">Specify corporate identity parameters. The organization code is immutable once provisioned.</p>
            </div>

            <div>
              <label htmlFor="onboarding-org-code" className="text-caption" style={{ fontWeight: 600, display: "block", marginBottom: "0.35rem" }}>
                Organization Code <span style={{ color: "var(--status-danger)" }}>*</span>
              </label>
              <input
                id="onboarding-org-code"
                type="text"
                className="input-field"
                placeholder="e.g. acme-corp"
                value={orgCode}
                onChange={(e) => setOrgCode(e.target.value.toLowerCase())}
                style={{ width: "100%", fontFamily: "var(--font-code)" }}
              />
              {fieldErrors.orgCode && (
                <div style={{ color: "var(--status-danger)", fontSize: "0.75rem", marginTop: "0.25rem" }}>
                  {fieldErrors.orgCode}
                </div>
              )}
            </div>

            <div>
              <label htmlFor="onboarding-org-name" className="text-caption" style={{ fontWeight: 600, display: "block", marginBottom: "0.35rem" }}>
                Organization Name <span style={{ color: "var(--status-danger)" }}>*</span>
              </label>
              <input
                id="onboarding-org-name"
                type="text"
                className="input-field"
                placeholder="e.g. Acme Corporation"
                value={orgName}
                onChange={(e) => setOrgName(e.target.value)}
                style={{ width: "100%" }}
              />
              {fieldErrors.orgName && (
                <div style={{ color: "var(--status-danger)", fontSize: "0.75rem", marginTop: "0.25rem" }}>
                  {fieldErrors.orgName}
                </div>
              )}
            </div>

            <div>
              <label htmlFor="onboarding-org-desc" className="text-caption" style={{ fontWeight: 600, display: "block", marginBottom: "0.35rem" }}>
                Description
              </label>
              <textarea
                id="onboarding-org-desc"
                className="input-field"
                rows={3}
                placeholder="Operational purpose, enterprise division, or notes..."
                value={orgDesc}
                onChange={(e) => setOrgDesc(e.target.value)}
                style={{ width: "100%", resize: "vertical" }}
              />
            </div>

            <div style={{ display: "flex", justifyContent: "flex-end", marginTop: "1rem" }}>
              <button type="submit" className="btn btn-primary" disabled={isSubmitting}>
                {isSubmitting ? "Saving..." : "Continue to Administrator Setup →"}
              </button>
            </div>
          </form>
        ) : currentStep === "admin_setup" ? (
          /* Step 2: Administrator Setup Form */
          <form onSubmit={handleNextFromAdmin} className="glass-panel" style={{ padding: "2rem", display: "flex", flexDirection: "column", gap: "1.5rem" }}>
            <div>
              <h2 className="heading-title" style={{ fontSize: "1.25rem", margin: "0 0 0.25rem 0" }}>
                Step 2: Initial Tenant Administrator
              </h2>
              <p className="text-body">Assign primary administrator credentials. A secure invitation will be generated automatically.</p>
            </div>

            <div>
              <label htmlFor="onboarding-admin-email" className="text-caption" style={{ fontWeight: 600, display: "block", marginBottom: "0.35rem" }}>
                Administrator Email <span style={{ color: "var(--status-danger)" }}>*</span>
              </label>
              <input
                id="onboarding-admin-email"
                type="email"
                className="input-field"
                placeholder="admin@organization.com"
                value={adminEmail}
                onChange={(e) => setAdminEmail(e.target.value)}
                style={{ width: "100%" }}
              />
              {fieldErrors.adminEmail && (
                <div style={{ color: "var(--status-danger)", fontSize: "0.75rem", marginTop: "0.25rem" }}>
                  {fieldErrors.adminEmail}
                </div>
              )}
            </div>

            <div>
              <label htmlFor="onboarding-admin-name" className="text-caption" style={{ fontWeight: 600, display: "block", marginBottom: "0.35rem" }}>
                Administrator Full Name
              </label>
              <input
                id="onboarding-admin-name"
                type="text"
                className="input-field"
                placeholder="e.g. Jane Doe"
                value={adminFullName}
                onChange={(e) => setAdminFullName(e.target.value)}
                style={{ width: "100%" }}
              />
            </div>

            <div style={{ display: "flex", justifyContent: "space-between", marginTop: "1rem" }}>
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => {
                  if (currentCase) {
                    void onboardingApi
                      .transitionStep(currentCase.id, { target_step: "organization_profile" })
                      .then((res) => setCurrentCase(res));
                  }
                }}
              >
                ← Back
              </button>
              <button type="submit" className="btn btn-primary" disabled={isSubmitting}>
                {isSubmitting ? "Saving..." : "Continue to Plan Selection →"}
              </button>
            </div>
          </form>
        ) : currentStep === "plan_selection" ? (
          /* Step 3: Plan Selection Form */
          <form onSubmit={handleNextFromPlan} className="glass-panel" style={{ padding: "2rem", display: "flex", flexDirection: "column", gap: "1.5rem" }}>
            <div>
              <h2 className="heading-title" style={{ fontSize: "1.25rem", margin: "0 0 0.25rem 0" }}>
                Step 3: Initial Commercial Plan & Entitlements
              </h2>
              <p className="text-body">Select default packaging plan and trial entitlement boundaries.</p>
            </div>

            <div>
              <label htmlFor="onboarding-plan-select" className="text-caption" style={{ fontWeight: 600, display: "block", marginBottom: "0.35rem" }}>
                Available Active Plans
              </label>
              <select
                id="onboarding-plan-select"
                className="input-field"
                value={selectedPlanVersionId}
                onChange={(e) => {
                  setSelectedPlanVersionId(e.target.value);
                  setSelectedPriceId("");
                }}
                style={{ width: "100%" }}
              >
                <option value="">No Plan (Direct custom entitlements only)</option>
                {plans.map((p) => (
                  <option key={p.id} value={p.active_version?.id || ""}>
                    {p.name} ({p.code}) — Version {p.active_version?.version || 1}
                  </option>
                ))}
              </select>
            </div>

            {selectedPlanVersionId && availablePrices.length > 0 && (
              <div>
                <label htmlFor="onboarding-price-select" className="text-caption" style={{ fontWeight: 600, display: "block", marginBottom: "0.35rem" }}>
                  Pricing Interval & Currency
                </label>
                <select
                  id="onboarding-price-select"
                  className="input-field"
                  value={selectedPriceId}
                  onChange={(e) => setSelectedPriceId(e.target.value)}
                  style={{ width: "100%" }}
                >
                  {availablePrices.map((pr) => (
                    <option key={pr.id} value={pr.id}>
                      {pr.currency} {pr.amount} / {pr.billing_interval}
                    </option>
                  ))}
                </select>
              </div>
            )}

            {selectedPlanVersionId && (
              <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                <input
                  id="onboarding-trial-checkbox"
                  type="checkbox"
                  checked={isTrial}
                  onChange={(e) => setIsTrial(e.target.checked)}
                />
                <label htmlFor="onboarding-trial-checkbox" className="text-caption" style={{ cursor: "pointer" }}>
                  Provision as 14-day trial period (zero upfront payment required)
                </label>
              </div>
            )}

            <div style={{ display: "flex", justifyContent: "space-between", marginTop: "1rem" }}>
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => {
                  if (currentCase) {
                    void onboardingApi
                      .transitionStep(currentCase.id, { target_step: "admin_setup" })
                      .then((res) => setCurrentCase(res));
                  }
                }}
              >
                ← Back
              </button>
              <button type="submit" className="btn btn-primary" disabled={isSubmitting}>
                {isSubmitting ? "Saving..." : "Review & Provision →"}
              </button>
            </div>
          </form>
        ) : (
          /* Step 4: Review & Final Confirmation */
          <div className="glass-panel" style={{ padding: "2rem", display: "flex", flexDirection: "column", gap: "1.5rem" }}>
            <div>
              <h2 className="heading-title" style={{ fontSize: "1.25rem", margin: "0 0 0.25rem 0" }}>
                Step 4: Review & Provision Organization
              </h2>
              <p className="text-body">Confirm parameters before executing the provisioning transaction.</p>
            </div>

            <div className="glass-panel-elevated" style={{ padding: "1.5rem", display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1.25rem" }}>
              <div>
                <span className="text-caption" style={{ textTransform: "uppercase" }}>Organization Code</span>
                <div style={{ fontWeight: 600, fontFamily: "var(--font-code)" }}>{currentCase?.organization_code}</div>
              </div>
              <div>
                <span className="text-caption" style={{ textTransform: "uppercase" }}>Organization Name</span>
                <div style={{ fontWeight: 600 }}>{currentCase?.organization_name}</div>
              </div>
              <div>
                <span className="text-caption" style={{ textTransform: "uppercase" }}>Administrator Email</span>
                <div style={{ fontWeight: 600 }}>{currentCase?.admin_email}</div>
              </div>
              <div>
                <span className="text-caption" style={{ textTransform: "uppercase" }}>Administrator Name</span>
                <div style={{ fontWeight: 600 }}>{currentCase?.admin_full_name || "—"}</div>
              </div>
              <div>
                <span className="text-caption" style={{ textTransform: "uppercase" }}>Commercial Plan</span>
                <div style={{ fontWeight: 600 }}>{currentCase?.plan_name ? `${currentCase.plan_name} (v${currentCase.plan_version_number})` : "None"}</div>
              </div>
              <div>
                <span className="text-caption" style={{ textTransform: "uppercase" }}>Trial Period</span>
                <div style={{ fontWeight: 600 }}>{currentCase?.is_trial ? "14-Day Trial" : "Direct Active"}</div>
              </div>
            </div>

            <div style={{ display: "flex", justifyContent: "space-between", marginTop: "1rem" }}>
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => {
                  if (currentCase) {
                    void onboardingApi
                      .transitionStep(currentCase.id, { target_step: "plan_selection" })
                      .then((res) => setCurrentCase(res));
                  }
                }}
              >
                ← Back
              </button>
              <button
                type="button"
                className="btn btn-primary"
                onClick={handleFinalProvision}
                disabled={isSubmitting}
              >
                {isSubmitting ? "Provisioning Organization..." : "Execute & Complete Onboarding ✓"}
              </button>
            </div>
          </div>
        )}
      </div>
    </AppShell>
  );
};
