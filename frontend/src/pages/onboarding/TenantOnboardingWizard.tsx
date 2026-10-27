/**
 * Tenant Onboarding Wizard Page (Phase 3B / Phase 4 Extended).
 *
 * Platform Owner wizard for provisioning new tenant organizations end-to-end:
 * 1. Organization Profile (code, name, description)
 * 2. Admin Setup (email, full name)
 * 3. Commercial Plan Selection (active plans & prices, trial toggle)
 * 4. Product Entitlements (dynamic catalog list, multi-select toggles)
 * 5. Console Feature Ceilings (product modules/features & tenant console ceilings)
 * 6. Review & Confirm (summary of all 5 dimensions, atomic provisioning)
 * 7. Completed confirmation with direct navigation
 */

import React, { useCallback, useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { onboardingApi } from "../../api/onboarding.ts";
import { plansApi } from "../../api/plans.ts";
import type {
  OnboardingOptionsResponse,
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
  { key: "product_entitlements", label: "Product Entitlements", icon: <ShieldCheckIcon size={16} /> },
  { key: "feature_ceilings", label: "Console Feature Ceilings", icon: <LayersIcon size={16} /> },
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

  // Dynamic Options (Products, Modules, Features, Console Modules)
  const [options, setOptions] = useState<OnboardingOptionsResponse | null>(null);

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

  // Step 4: Product Entitlements State
  const [selectedProductIds, setSelectedProductIds] = useState<string[]>([]);

  // Step 5: Console Feature Ceilings State
  const [featureCeilings, setFeatureCeilings] = useState<{
    module_policies: Record<string, boolean>;
    permission_ceilings: Record<string, boolean>;
    product_modules: Record<string, boolean>;
    product_features: Record<string, boolean>;
  }>({
    module_policies: {},
    permission_ceilings: {},
    product_modules: {},
    product_features: {},
  });

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
      if (caseData.initial_admin_activation_url) {
        setActivationUrl(caseData.initial_admin_activation_url);
      }
      setOrgCode(caseData.organization_code || "");
      setOrgName(caseData.organization_name || "");
      setOrgDesc(caseData.organization_description || "");
      setAdminEmail(caseData.admin_email || "");
      setAdminFullName(caseData.admin_full_name || "");
      setSelectedPlanVersionId(caseData.plan_version || "");
      setSelectedPriceId(caseData.plan_price || "");
      setIsTrial(caseData.is_trial);

      if (caseData.selected_product_ids && Array.isArray(caseData.selected_product_ids)) {
        setSelectedProductIds(caseData.selected_product_ids as string[]);
      }

      if (caseData.feature_ceilings && typeof caseData.feature_ceilings === "object") {
        const fc = caseData.feature_ceilings as Record<string, any>;
        setFeatureCeilings({
          module_policies: fc.module_policies || {},
          permission_ceilings: fc.permission_ceilings || fc.permissions || {},
          product_modules: fc.product_modules || {},
          product_features: fc.product_features || {},
        });
      }

      // Load available plans and options in parallel
      const [plansRes, optionsRes] = await Promise.all([
        plansApi.list({ has_active_version: "true" }),
        onboardingApi.getOptions(),
      ]);
      setPlans(plansRes.results);
      setOptions(optionsRes);
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
        target_step: "product_entitlements",
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

  const handleToggleProduct = (productId: string) => {
    setSelectedProductIds((prev) =>
      prev.includes(productId) ? prev.filter((id) => id !== productId) : [...prev, productId]
    );
  };

  const handleNextFromProducts = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!currentCase) return;

    if (selectedProductIds.length === 0) {
      setGeneralError("Please select at least one product entitlement for this tenant.");
      return;
    }

    setFieldErrors({});
    setIsSubmitting(true);
    setGeneralError(null);
    try {
      const updated = await onboardingApi.transitionStep(currentCase.id, {
        target_step: "feature_ceilings",
        step_data: {
          selected_product_ids: selectedProductIds,
        },
      });
      setCurrentCase(updated);
    } catch {
      setGeneralError("Failed to save product entitlements.");
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleToggleProductModule = (moduleId: string) => {
    setFeatureCeilings((prev) => ({
      ...prev,
      product_modules: {
        ...prev.product_modules,
        [moduleId]: prev.product_modules[moduleId] === false ? true : false,
      },
    }));
  };

  const handleToggleProductFeature = (featureId: string) => {
    setFeatureCeilings((prev) => ({
      ...prev,
      product_features: {
        ...prev.product_features,
        [featureId]: prev.product_features[featureId] === false ? true : false,
      },
    }));
  };

  const handleToggleConsoleModule = (moduleKey: string, isCore: boolean) => {
    if (isCore) return;
    setFeatureCeilings((prev) => ({
      ...prev,
      module_policies: {
        ...prev.module_policies,
        [moduleKey]: prev.module_policies[moduleKey] === false ? true : false,
      },
    }));
  };

  const handleTogglePermissionCeiling = (permKey: string) => {
    setFeatureCeilings((prev) => ({
      ...prev,
      permission_ceilings: {
        ...prev.permission_ceilings,
        [permKey]: prev.permission_ceilings[permKey] === false ? true : false,
      },
    }));
  };

  const handleNextFromCeilings = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!currentCase) return;

    setFieldErrors({});
    setIsSubmitting(true);
    setGeneralError(null);

    const effectiveModulePolicies: Record<string, boolean> = { ...featureCeilings.module_policies };
    const effectivePermissionCeilings: Record<string, boolean> = { ...featureCeilings.permission_ceilings };
    const effectiveProductModules: Record<string, boolean> = { ...featureCeilings.product_modules };
    const effectiveProductFeatures: Record<string, boolean> = { ...featureCeilings.product_features };

    if (options?.console_modules) {
      for (const cm of options.console_modules) {
        if (!cm.is_core && effectiveModulePolicies[cm.key] === undefined) {
          effectiveModulePolicies[cm.key] = true;
        }
        if (cm.permissions) {
          for (const perm of cm.permissions) {
            if (effectivePermissionCeilings[perm.key] === undefined) {
              effectivePermissionCeilings[perm.key] = true;
            }
          }
        }
      }
    }

    if (options?.products) {
      for (const prod of options.products) {
        if (selectedProductIds.includes(prod.id) && prod.modules) {
          for (const mod of prod.modules) {
            if (effectiveProductModules[mod.id] === undefined) {
              effectiveProductModules[mod.id] = true;
            }
            if (mod.features) {
              for (const feat of mod.features) {
                if (effectiveProductFeatures[feat.id] === undefined) {
                  effectiveProductFeatures[feat.id] = true;
                }
              }
            }
          }
        }
      }
    }

    const payloadCeilings = {
      module_policies: effectiveModulePolicies,
      permission_ceilings: effectivePermissionCeilings,
      product_modules: effectiveProductModules,
      product_features: effectiveProductFeatures,
    };
    setFeatureCeilings(payloadCeilings);

    try {
      const updated = await onboardingApi.transitionStep(currentCase.id, {
        target_step: "review_confirm",
        step_data: {
          feature_ceilings: payloadCeilings,
        },
      });
      setCurrentCase(updated);
    } catch {
      setGeneralError("Failed to save console feature ceilings.");
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleFinalProvision = async () => {
    if (!currentCase) return;
    if (currentCase.status === "completed") {
      return;
    }
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
      const detailMsg = errorObj?.data?.detail;
      // If the case was already completed in the background, reload and show completion
      if (detailMsg && detailMsg.toLowerCase().includes("completed")) {
        try {
          const reloaded = await onboardingApi.getCase(currentCase.id);
          setCurrentCase(reloaded);
          if (reloaded.initial_admin_activation_url) {
            setActivationUrl(reloaded.initial_admin_activation_url);
          }
          return;
        } catch {
          // ignore
        }
      }
      setGeneralError(detailMsg || "Provisioning failed. Please check inputs and retry.");
    } finally {
      setIsSubmitting(false);
    }
  };

  const currentStep = currentCase?.current_step || "organization_profile";
  const isCompleted = currentCase?.status === "completed";

  // Filter selected products details for display
  const selectedProducts = (options?.products || []).filter((p) => selectedProductIds.includes(p.id));

  return (
    <AppShell>
      <div style={{ maxWidth: "920px", margin: "0 auto", display: "flex", flexDirection: "column", gap: "2rem" }}>
        {/* Wizard Header */}
        <div>
          <h1 className="heading-hero" style={{ margin: 0, fontSize: "1.75rem" }}>
            Tenant Onboarding Wizard
          </h1>
          <p className="text-body" style={{ marginTop: "0.5rem" }}>
            Provision a new tenant organization with isolated boundaries, administrator credentials, commercial packaging, product entitlements, and console feature ceilings.
          </p>
        </div>

        {/* Step Indicator (6 steps) */}
        <div
          role="navigation"
          aria-label="Onboarding Progress"
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(130px, 1fr))",
            gap: "0.5rem",
          }}
        >
          {STEPS.map((step, idx) => {
            const stepOrder = [
              "organization_profile",
              "admin_setup",
              "plan_selection",
              "product_entitlements",
              "feature_ceilings",
              "review_confirm",
              "completed",
            ];
            const currentIdx = stepOrder.indexOf(currentStep);
            const thisIdx = stepOrder.indexOf(step.key);
            const isDone = thisIdx < currentIdx || isCompleted;
            const isCurrent = currentStep === step.key && !isCompleted;

            return (
              <div
                key={step.key}
                className="glass-panel"
                style={{
                  padding: "0.75rem",
                  display: "flex",
                  alignItems: "center",
                  gap: "0.5rem",
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
                  {isDone ? <CheckCircleIcon size={16} /> : step.icon}
                </div>
                <div style={{ minWidth: 0 }}>
                  <div style={{ fontSize: "0.65rem", color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.05em" }}>
                    Step {idx + 1}
                  </div>
                  <div style={{ fontSize: "0.75rem", fontWeight: isCurrent ? 700 : 500, color: "var(--text-primary)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
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
          /* Step 7: Completed Screen */
          <div className="glass-panel-elevated" style={{ padding: "2.5rem", textAlign: "center" }}>
            <div style={{ color: "var(--status-success)", marginBottom: "1rem" }}>
              <CheckCircleIcon size={48} />
            </div>
            <h2 className="heading-title" style={{ fontSize: "1.5rem", margin: "0 0 0.5rem 0" }}>
              Organization Successfully Provisioned!
            </h2>
            <p className="text-body" style={{ maxWidth: "560px", margin: "0 auto 1.5rem auto" }}>
              <strong>{currentCase?.organization_name}</strong> (<code>{currentCase?.organization_code}</code>) is fully configured with administrator credentials, commercial packaging, direct product entitlements, and console feature policies.
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

            {!activationUrl && (
              <div
                className="glass-panel"
                style={{
                  maxWidth: "580px",
                  margin: "0 auto 1.75rem auto",
                  padding: "1rem 1.25rem",
                  textAlign: "center",
                  fontSize: "0.875rem",
                  color: "var(--text-secondary)",
                }}
              >
                An invitation email has been dispatched to <strong>{currentCase?.admin_email}</strong>. The administrator can also be managed directly from the Organization Registry.
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
                Step 3: Initial Commercial Plan & Packaging
              </h2>
              <p className="text-body">Select default commercial plan and billing tier boundaries.</p>
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
                {isSubmitting ? "Saving..." : "Continue to Product Entitlements →"}
              </button>
            </div>
          </form>
        ) : currentStep === "product_entitlements" ? (
          /* Step 4: Product Entitlements Form */
          <form onSubmit={handleNextFromProducts} className="glass-panel" style={{ padding: "2rem", display: "flex", flexDirection: "column", gap: "1.5rem" }}>
            <div>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
                <div>
                  <h2 className="heading-title" style={{ fontSize: "1.25rem", margin: "0 0 0.25rem 0" }}>
                    Step 4: Product Entitlements
                  </h2>
                  <p className="text-body">
                    Select which platform products the new tenant is entitled to use. Active products will be directly provisioned upon confirmation.
                  </p>
                </div>
                {options && options.products.length > 0 && (
                  <div style={{ display: "flex", gap: "0.5rem" }}>
                    <button
                      type="button"
                      className="btn btn-secondary"
                      style={{ fontSize: "0.75rem", padding: "0.3rem 0.6rem" }}
                      onClick={() => setSelectedProductIds(options.products.map((p) => p.id))}
                    >
                      Select All
                    </button>
                    <button
                      type="button"
                      className="btn btn-secondary"
                      style={{ fontSize: "0.75rem", padding: "0.3rem 0.6rem" }}
                      onClick={() => setSelectedProductIds([])}
                    >
                      Deselect All
                    </button>
                  </div>
                )}
              </div>
            </div>

            {(!options || options.products.length === 0) ? (
              <div className="glass-panel" style={{ padding: "2rem", textAlign: "center", color: "var(--text-secondary)" }}>
                No active products available in Product Registry.
              </div>
            ) : (
              <div style={{ display: "grid", gridTemplateColumns: "1fr", gap: "0.75rem" }}>
                {options.products.map((prod) => {
                  const isSelected = selectedProductIds.includes(prod.id);
                  const moduleCount = prod.modules?.length || 0;

                  return (
                    <div
                      key={prod.id}
                      onClick={() => handleToggleProduct(prod.id)}
                      className="glass-panel"
                      style={{
                        padding: "1rem 1.25rem",
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "space-between",
                        cursor: "pointer",
                        border: isSelected
                          ? "2px solid var(--brand-primary, #6366f1)"
                          : "1px solid var(--border-color, rgba(255,255,255,0.1))",
                        backgroundColor: isSelected
                          ? "rgba(99, 102, 241, 0.08)"
                          : "transparent",
                        borderRadius: "8px",
                        transition: "all 0.15s ease-in-out",
                      }}
                    >
                      <div style={{ display: "flex", alignItems: "flex-start", gap: "0.875rem" }}>
                        <input
                          type="checkbox"
                          checked={isSelected}
                          onChange={() => handleToggleProduct(prod.id)}
                          onClick={(e) => e.stopPropagation()}
                          style={{ marginTop: "0.25rem", cursor: "pointer", width: "16px", height: "16px" }}
                        />
                        <div>
                          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                            <span style={{ fontWeight: 700, fontSize: "0.95rem", color: "var(--text-primary)" }}>
                              {prod.name}
                            </span>
                            <span
                              style={{
                                fontSize: "0.7rem",
                                padding: "0.15rem 0.45rem",
                                borderRadius: "4px",
                                backgroundColor: "rgba(255, 255, 255, 0.08)",
                                fontFamily: "var(--font-code)",
                                color: "var(--text-muted)",
                              }}
                            >
                              {prod.code}
                            </span>
                          </div>
                          <p style={{ margin: "0.25rem 0 0 0", fontSize: "0.8125rem", color: "var(--text-secondary)" }}>
                            {prod.description || "No description provided."}
                          </p>
                        </div>
                      </div>

                      <div style={{ textAlign: "right", whiteSpace: "nowrap", paddingLeft: "1rem" }}>
                        <span
                          style={{
                            fontSize: "0.75rem",
                            color: moduleCount > 0 ? "var(--text-muted)" : "var(--text-muted)",
                          }}
                        >
                          {moduleCount} {moduleCount === 1 ? "module" : "modules"}
                        </span>
                        <div
                          style={{
                            fontSize: "0.75rem",
                            fontWeight: 600,
                            marginTop: "0.2rem",
                            color: isSelected ? "var(--brand-primary, #6366f1)" : "var(--text-muted)",
                          }}
                        >
                          {isSelected ? "Entitled ✓" : "Disabled"}
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}

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
              <button type="submit" className="btn btn-primary" disabled={isSubmitting}>
                {isSubmitting ? "Saving..." : "Continue to Console Feature Ceilings →"}
              </button>
            </div>
          </form>
        ) : currentStep === "feature_ceilings" ? (
          /* Step 5: Console Feature Ceilings Form */
          <form onSubmit={handleNextFromCeilings} className="glass-panel" style={{ padding: "2rem", display: "flex", flexDirection: "column", gap: "1.5rem" }}>
            <div>
              <h2 className="heading-title" style={{ fontSize: "1.25rem", margin: "0 0 0.25rem 0" }}>
                Step 5: Console Feature Ceilings
              </h2>
              <p className="text-body">
                Configure module policies and feature-level maximum ceilings for the entitled products and tenant workspace. Disabled features will be unavailable to tenant administrators and members.
              </p>
            </div>

            {/* Selected Products Feature Configuration */}
            <div>
              <h3 style={{ fontSize: "1rem", fontWeight: 700, margin: "0 0 0.75rem 0", color: "var(--text-primary)" }}>
                Product Feature Ceilings ({selectedProducts.length} Entitled {selectedProducts.length === 1 ? "Product" : "Products"})
              </h3>

              {selectedProducts.length === 0 ? (
                <div className="glass-panel" style={{ padding: "1.5rem", textAlign: "center", color: "var(--text-secondary)" }}>
                  No products selected in previous step. Return to Step 4 to select product entitlements.
                </div>
              ) : (
                <div style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>
                  {selectedProducts.map((prod) => {
                    const hasModules = prod.modules && prod.modules.length > 0;

                    return (
                      <div
                        key={prod.id}
                        className="glass-panel-elevated"
                        style={{
                          padding: "1.25rem",
                          border: "1px solid rgba(255,255,255,0.08)",
                          borderRadius: "8px",
                        }}
                      >
                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.75rem" }}>
                          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                            <span style={{ fontWeight: 700, fontSize: "0.95rem" }}>{prod.name}</span>
                            <span style={{ fontSize: "0.7rem", fontFamily: "var(--font-code)", color: "var(--text-muted)" }}>
                              ({prod.code})
                            </span>
                          </div>
                          <span style={{ fontSize: "0.75rem", color: "var(--status-success)" }}>
                            Product Entitled
                          </span>
                        </div>

                        {!hasModules ? (
                          <div
                            style={{
                              fontSize: "0.8125rem",
                              color: "var(--text-muted)",
                              fontStyle: "italic",
                              padding: "0.75rem",
                              background: "rgba(255, 255, 255, 0.02)",
                              borderRadius: "4px",
                            }}
                          >
                            No configurable modules or features defined in the catalog for this product.
                          </div>
                        ) : (
                          <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
                            {prod.modules.map((mod) => {
                              const isModEnabled = featureCeilings.product_modules[mod.id] !== false;
                              const hasFeatures = mod.features && mod.features.length > 0;

                              return (
                                <div
                                  key={mod.id}
                                  style={{
                                    padding: "0.75rem",
                                    borderRadius: "6px",
                                    backgroundColor: isModEnabled
                                      ? "rgba(99, 102, 241, 0.04)"
                                      : "rgba(0, 0, 0, 0.2)",
                                    border: isModEnabled
                                      ? "1px solid rgba(99, 102, 241, 0.2)"
                                      : "1px solid rgba(255, 255, 255, 0.05)",
                                  }}
                                >
                                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                                    <div>
                                      <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                                        <span style={{ fontWeight: 600, fontSize: "0.85rem" }}>{mod.name}</span>
                                        <span style={{ fontSize: "0.68rem", fontFamily: "var(--font-code)", color: "var(--text-muted)" }}>
                                          {mod.code}
                                        </span>
                                      </div>
                                      {mod.description && (
                                        <p style={{ margin: "0.2rem 0 0 0", fontSize: "0.75rem", color: "var(--text-secondary)" }}>
                                          {mod.description}
                                        </p>
                                      )}
                                    </div>

                                    <button
                                      type="button"
                                      className={`btn ${isModEnabled ? "btn-primary" : "btn-secondary"}`}
                                      style={{ fontSize: "0.72rem", padding: "0.25rem 0.6rem" }}
                                      onClick={() => handleToggleProductModule(mod.id)}
                                    >
                                      {isModEnabled ? "Module Enabled" : "Module Disabled"}
                                    </button>
                                  </div>

                                  {/* Sub-features if present */}
                                  {hasFeatures && isModEnabled && (
                                    <div style={{ marginTop: "0.5rem", paddingLeft: "1.25rem", display: "flex", flexDirection: "column", gap: "0.4rem" }}>
                                      {mod.features.map((feat) => {
                                        const isFeatEnabled = featureCeilings.product_features[feat.id] !== false;

                                        return (
                                          <div
                                            key={feat.id}
                                            style={{
                                              display: "flex",
                                              justifyContent: "space-between",
                                              alignItems: "center",
                                              padding: "0.4rem 0.6rem",
                                              borderRadius: "4px",
                                              backgroundColor: "rgba(255,255,255,0.03)",
                                            }}
                                          >
                                            <div>
                                              <span style={{ fontSize: "0.8rem", fontWeight: 500 }}>{feat.name}</span>
                                              <span style={{ fontSize: "0.68rem", fontFamily: "var(--font-code)", color: "var(--text-muted)", marginLeft: "0.4rem" }}>
                                                {feat.code}
                                              </span>
                                            </div>
                                            <button
                                              type="button"
                                              className={`btn ${isFeatEnabled ? "btn-primary" : "btn-secondary"}`}
                                              style={{ fontSize: "0.68rem", padding: "0.15rem 0.5rem" }}
                                              onClick={() => handleToggleProductFeature(feat.id)}
                                            >
                                              {isFeatEnabled ? "ON" : "OFF"}
                                            </button>
                                          </div>
                                        );
                                      })}
                                    </div>
                                  )}
                                </div>
                              );
                            })}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>

            {/* Tenant Console Modules & Permission Ceilings */}
            {options?.console_modules && options.console_modules.length > 0 && (
              <div style={{ marginTop: "0.5rem" }}>
                <h3 style={{ fontSize: "1rem", fontWeight: 700, margin: "0 0 0.75rem 0", color: "var(--text-primary)" }}>
                  Tenant Console Module Policies & Permission Ceilings
                </h3>

                <div style={{ display: "grid", gridTemplateColumns: "1fr", gap: "0.75rem" }}>
                  {options.console_modules.map((cm) => {
                    const isModEnabled = cm.is_core || featureCeilings.module_policies[cm.key] !== false;

                    return (
                      <div
                        key={cm.key}
                        className="glass-panel-elevated"
                        style={{
                          padding: "1rem",
                          border: "1px solid rgba(255,255,255,0.06)",
                          borderRadius: "8px",
                        }}
                      >
                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                          <div>
                            <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                              <span style={{ fontWeight: 600, fontSize: "0.875rem" }}>{cm.display_name}</span>
                              <span style={{ fontSize: "0.68rem", fontFamily: "var(--font-code)", color: "var(--text-muted)" }}>
                                {cm.key}
                              </span>
                              {cm.is_core && (
                                <span
                                  style={{
                                    fontSize: "0.65rem",
                                    padding: "0.1rem 0.4rem",
                                    borderRadius: "3px",
                                    backgroundColor: "rgba(99, 102, 241, 0.2)",
                                    color: "var(--brand-primary, #6366f1)",
                                    fontWeight: 600,
                                  }}
                                >
                                  Core (Locked)
                                </span>
                              )}
                            </div>
                            {cm.description && (
                              <p style={{ margin: "0.2rem 0 0 0", fontSize: "0.75rem", color: "var(--text-secondary)" }}>
                                {cm.description}
                              </p>
                            )}
                          </div>

                          <button
                            type="button"
                            disabled={cm.is_core}
                            className={`btn ${isModEnabled ? "btn-primary" : "btn-secondary"}`}
                            style={{
                              fontSize: "0.72rem",
                              padding: "0.25rem 0.6rem",
                              opacity: cm.is_core ? 0.7 : 1,
                              cursor: cm.is_core ? "not-allowed" : "pointer",
                            }}
                            onClick={() => handleToggleConsoleModule(cm.key, cm.is_core)}
                          >
                            {cm.is_core ? "Always Active" : isModEnabled ? "Enabled" : "Disabled"}
                          </button>
                        </div>

                        {/* Permissions ceilings under console module */}
                        {cm.permissions && cm.permissions.length > 0 && isModEnabled && (
                          <div style={{ marginTop: "0.6rem", paddingLeft: "1rem", display: "flex", flexDirection: "column", gap: "0.35rem" }}>
                            {cm.permissions.map((perm) => {
                              const isPermAllowed = featureCeilings.permission_ceilings[perm.key] !== false;

                              return (
                                <div
                                  key={perm.key}
                                  style={{
                                    display: "flex",
                                    justifyContent: "space-between",
                                    alignItems: "center",
                                    padding: "0.35rem 0.5rem",
                                    borderRadius: "4px",
                                    backgroundColor: "rgba(255,255,255,0.02)",
                                  }}
                                >
                                  <div>
                                    <span style={{ fontSize: "0.78rem" }}>{perm.display_name}</span>
                                    <span style={{ fontSize: "0.65rem", fontFamily: "var(--font-code)", color: "var(--text-muted)", marginLeft: "0.4rem" }}>
                                      {perm.key}
                                    </span>
                                  </div>
                                  <button
                                    type="button"
                                    className={`btn ${isPermAllowed ? "btn-primary" : "btn-secondary"}`}
                                    style={{ fontSize: "0.65rem", padding: "0.15rem 0.45rem" }}
                                    onClick={() => handleTogglePermissionCeiling(perm.key)}
                                  >
                                    {isPermAllowed ? "Allowed" : "Denied"}
                                  </button>
                                </div>
                              );
                            })}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            <div style={{ display: "flex", justifyContent: "space-between", marginTop: "1rem" }}>
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => {
                  if (currentCase) {
                    void onboardingApi
                      .transitionStep(currentCase.id, { target_step: "product_entitlements" })
                      .then((res) => setCurrentCase(res));
                  }
                }}
              >
                ← Back
              </button>
              <button type="submit" className="btn btn-primary" disabled={isSubmitting}>
                {isSubmitting ? "Saving..." : "Continue to Review & Provision →"}
              </button>
            </div>
          </form>
        ) : (
          /* Step 6: Review & Final Confirmation */
          <div className="glass-panel" style={{ padding: "2rem", display: "flex", flexDirection: "column", gap: "1.5rem" }}>
            <div>
              <h2 className="heading-title" style={{ fontSize: "1.25rem", margin: "0 0 0.25rem 0" }}>
                Step 6: Review & Provision Organization
              </h2>
              <p className="text-body">Confirm all tenant configuration parameters before executing the provisioning transaction.</p>
            </div>

            {/* Summary Grid */}
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
                <div style={{ fontWeight: 600 }}>{currentCase?.plan_name ? `${currentCase.plan_name} (v${currentCase.plan_version_number})` : "Direct custom entitlements"}</div>
              </div>
              <div>
                <span className="text-caption" style={{ textTransform: "uppercase" }}>Trial Period</span>
                <div style={{ fontWeight: 600 }}>{currentCase?.is_trial ? "14-Day Trial" : "Direct Active"}</div>
              </div>
            </div>

            {/* Product Entitlements Summary */}
            <div className="glass-panel-elevated" style={{ padding: "1.25rem" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.75rem" }}>
                <span className="text-caption" style={{ textTransform: "uppercase", fontWeight: 700 }}>
                  Entitled Products ({selectedProducts.length})
                </span>
              </div>
              {selectedProducts.length === 0 ? (
                <div style={{ fontSize: "0.8125rem", color: "var(--text-muted)" }}>None selected</div>
              ) : (
                <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem" }}>
                  {selectedProducts.map((p) => (
                    <span
                      key={p.id}
                      style={{
                        padding: "0.35rem 0.75rem",
                        borderRadius: "6px",
                        backgroundColor: "rgba(99, 102, 241, 0.12)",
                        border: "1px solid rgba(99, 102, 241, 0.25)",
                        fontSize: "0.8125rem",
                        fontWeight: 600,
                        color: "var(--text-primary)",
                      }}
                    >
                      {p.name} ({p.code})
                    </span>
                  ))}
                </div>
              )}
            </div>

            {/* Feature Ceilings Summary */}
            <div className="glass-panel-elevated" style={{ padding: "1.25rem" }}>
              <span className="text-caption" style={{ textTransform: "uppercase", fontWeight: 700, display: "block", marginBottom: "0.75rem" }}>
                Console Feature Ceilings & Policies
              </span>
              <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem", fontSize: "0.8125rem" }}>
                {selectedProducts.map((p) => {
                  const modCount = p.modules?.length || 0;
                  const disabledModCount = p.modules?.filter((m) => featureCeilings.product_modules[m.id] === false).length || 0;
                  const enabledModCount = modCount - disabledModCount;

                  return (
                    <div key={p.id} style={{ display: "flex", justifyContent: "space-between", padding: "0.35rem 0", borderBottom: "1px solid rgba(255,255,255,0.05)" }}>
                      <span><strong>{p.name}:</strong></span>
                      <span style={{ color: enabledModCount > 0 ? "var(--text-secondary)" : "var(--text-muted)" }}>
                        {modCount === 0 ? "Standard package" : `${enabledModCount} of ${modCount} modules active`}
                      </span>
                    </div>
                  );
                })}
              </div>
            </div>

            <div style={{ display: "flex", justifyContent: "space-between", marginTop: "1rem" }}>
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => {
                  if (currentCase) {
                    void onboardingApi
                      .transitionStep(currentCase.id, { target_step: "feature_ceilings" })
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
