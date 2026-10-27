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
import { Link, useNavigate, useSearchParams } from "react-router-dom";
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
  LockIcon,
  ShieldCheckIcon,
  UserIcon,
} from "../../components/Icons.tsx";

interface ToggleSwitchProps {
  checked: boolean;
  disabled?: boolean;
  onChange: () => void;
  label?: string;
  sublabel?: string;
  activeColor?: string;
  size?: "sm" | "md";
  id?: string;
}

const ToggleSwitch: React.FC<ToggleSwitchProps> = ({
  checked,
  disabled = false,
  onChange,
  label,
  sublabel,
  activeColor = "var(--brand-primary, #3867f5)",
  size = "md",
  id,
}) => {
  const isSm = size === "sm";
  const width = isSm ? 38 : 46;
  const height = isSm ? 22 : 26;
  const thumbSize = isSm ? 16 : 20;
  const translate = isSm ? (checked ? 19 : 3) : (checked ? 23 : 3);

  return (
    <button
      id={id}
      type="button"
      role="switch"
      aria-checked={checked}
      disabled={disabled}
      onClick={(e) => {
        e.preventDefault();
        e.stopPropagation();
        if (!disabled) onChange();
      }}
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: "0.6rem",
        background: "transparent",
        border: "none",
        padding: "0.2rem 0.25rem",
        borderRadius: "9999px",
        cursor: disabled ? "not-allowed" : "pointer",
        opacity: disabled ? 0.65 : 1,
        transition: "opacity 0.2s ease",
      }}
    >
      <span
        style={{
          position: "relative",
          width: `${width}px`,
          height: `${height}px`,
          borderRadius: "9999px",
          backgroundColor: checked ? activeColor : "var(--glass-surface-sunken, rgba(148, 163, 184, 0.2))",
          border: `1.5px solid ${checked ? activeColor : "var(--border-subtle, rgba(148, 163, 184, 0.35))"}`,
          transition: "background-color 0.2s cubic-bezier(0.4, 0, 0.2, 1), border-color 0.2s ease, box-shadow 0.2s ease",
          display: "inline-block",
          flexShrink: 0,
          boxShadow: checked ? `0 2px 8px ${activeColor}40` : "none",
        }}
      >
        <span
          style={{
            position: "absolute",
            top: `${(height - thumbSize - 3) / 2}px`,
            left: `${translate}px`,
            width: `${thumbSize}px`,
            height: `${thumbSize}px`,
            borderRadius: "50%",
            backgroundColor: "#ffffff",
            boxShadow: "0 2px 5px rgba(0, 0, 0, 0.2)",
            transition: "left 0.2s cubic-bezier(0.4, 0, 0.2, 1)",
          }}
        />
      </span>
      {label && (
        <span style={{ display: "flex", flexDirection: "column", alignItems: "flex-start", textAlign: "left" }}>
          <span
            style={{
              fontSize: isSm ? "0.75rem" : "0.8125rem",
              fontWeight: 700,
              color: checked ? "var(--text-primary)" : "var(--text-muted)",
              letterSpacing: "-0.01em",
              userSelect: "none",
            }}
          >
            {label}
          </span>
          {sublabel && (
            <span style={{ fontSize: "0.6875rem", color: "var(--text-muted)", userSelect: "none" }}>{sublabel}</span>
          )}
        </span>
      )}
    </button>
  );
};

const STEPS: { key: OnboardingStepName; label: string; icon: React.ReactNode }[] = [
  { key: "organization_profile", label: "Organization Details", icon: <BuildingIcon size={16} /> },
  { key: "admin_setup", label: "Administrator Setup", icon: <UserIcon size={16} /> },
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

  const handleGrantAllConsolePermissions = () => {
    if (!options?.console_modules) return;
    const newPerms: Record<string, boolean> = {};
    options.console_modules.forEach((cm) => {
      cm.permissions?.forEach((p) => {
        newPerms[p.key] = true;
      });
    });
    setFeatureCeilings((prev) => ({
      ...prev,
      permission_ceilings: {
        ...prev.permission_ceilings,
        ...newPerms,
      },
    }));
  };

  const handleRevokeAllNonCorePermissions = () => {
    if (!options?.console_modules) return;
    const newPerms: Record<string, boolean> = {};
    options.console_modules.forEach((cm) => {
      cm.permissions?.forEach((p) => {
        if (!cm.is_core) {
          newPerms[p.key] = false;
        }
      });
    });
    setFeatureCeilings((prev) => ({
      ...prev,
      permission_ceilings: {
        ...prev.permission_ceilings,
        ...newPerms,
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

  const stepOrder: OnboardingStepName[] = [
    "organization_profile",
    "admin_setup",
    "plan_selection",
    "product_entitlements",
    "feature_ceilings",
    "review_confirm",
  ];
  const currentStepIdx = stepOrder.indexOf(currentStep as OnboardingStepName);

  return (
    <AppShell>
      <div style={{ maxWidth: "1180px", margin: "1.5rem auto", padding: "0 1.25rem 3rem 1.25rem" }}>
        {/* Breadcrumb Navigation */}
        <nav style={{ display: "flex", alignItems: "center", gap: "0.5rem", fontSize: "0.8125rem", color: "var(--text-muted)", marginBottom: "1rem" }}>
          <Link to="/" style={{ color: "var(--text-muted)", textDecoration: "none" }}>Platform Owner</Link>
          <span>/</span>
          <Link to="/organizations" style={{ color: "var(--text-muted)", textDecoration: "none" }}>Organizations</Link>
          <span>/</span>
          <span style={{ color: "var(--text-primary)", fontWeight: 600 }}>Onboard New Tenant</span>
        </nav>

        {/* Page Header */}
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "2rem", flexWrap: "wrap", gap: "1rem" }}>
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", marginBottom: "0.35rem" }}>
              <div
                style={{
                  width: "36px",
                  height: "36px",
                  borderRadius: "10px",
                  background: "linear-gradient(135deg, var(--brand-primary) 0%, #4338ca 100%)",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  color: "#ffffff",
                  boxShadow: "0 4px 12px rgba(99, 102, 241, 0.3)",
                }}
              >
                <BuildingIcon size={20} />
              </div>
              <h1 style={{ fontSize: "1.625rem", fontWeight: 800, margin: 0, letterSpacing: "-0.025em", color: "var(--text-primary)" }}>
                Tenant Onboarding Wizard
              </h1>
            </div>
            <p style={{ color: "var(--text-muted)", fontSize: "0.875rem", margin: 0, lineHeight: 1.5 }}>
              Provision a new tenant organization with isolated boundaries, administrator credentials, commercial packaging, product entitlements, and console feature ceilings.
            </p>
          </div>
          <Link
            to="/organizations"
            className="btn btn-secondary"
            style={{ fontSize: "0.8125rem", textDecoration: "none", padding: "0.5rem 1rem", minHeight: "36px" }}
          >
            ← Back to Organizations
          </Link>
        </div>

        {/* Connected Step Navigation Rail (Matching Tenant Member Onboarding & Design #2) */}
        <div
          className="glass-panel"
          style={{
            padding: "1rem 1.5rem",
            borderRadius: "14px",
            marginBottom: "2rem",
            border: "1px solid var(--border-glass)",
            backgroundColor: "var(--glass-surface-elevated)",
            boxShadow: "var(--shadow-sm)",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", position: "relative" }}>
            {STEPS.map((step, idx) => {
              const isActive = currentStep === step.key && !isCompleted;
              const isStepDone = (currentStepIdx > idx && currentStepIdx !== -1) || isCompleted;
              const isClickable = isStepDone && !isCompleted;

              return (
                <React.Fragment key={step.key}>
                  {/* Step Node */}
                  <div
                    onClick={() => {
                      if (isClickable && currentCase) {
                        void onboardingApi
                          .transitionStep(currentCase.id, { target_step: step.key })
                          .then((res) => setCurrentCase(res));
                      }
                    }}
                    style={{
                      display: "flex",
                      flexDirection: "column",
                      alignItems: "center",
                      gap: "0.45rem",
                      cursor: isClickable ? "pointer" : "default",
                      zIndex: 2,
                      padding: "0.25rem 0.5rem",
                      borderRadius: "8px",
                      transition: "all 0.15s ease",
                    }}
                  >
                    <div
                      style={{
                        width: "38px",
                        height: "38px",
                        borderRadius: "50%",
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                        fontSize: "0.8125rem",
                        fontWeight: 700,
                        backgroundColor: isActive
                          ? "var(--brand-primary)"
                          : isStepDone
                          ? "var(--status-success)"
                          : "var(--glass-surface-sunken)",
                        color: isActive || isStepDone ? "#ffffff" : "var(--text-muted)",
                        border: isActive
                          ? "2px solid #ffffff"
                          : isStepDone
                          ? "none"
                          : "1px solid var(--border-glass)",
                        boxShadow: isActive
                          ? "0 0 0 4px var(--brand-primary-light), 0 4px 12px rgba(99, 102, 241, 0.35)"
                          : isStepDone
                          ? "0 2px 8px rgba(16, 185, 129, 0.3)"
                          : "none",
                        transition: "all 0.2s ease",
                      }}
                    >
                      {isStepDone ? "✓" : idx + 1}
                    </div>

                    <div style={{ textAlign: "center" }}>
                      <div
                        style={{
                          fontSize: "0.6875rem",
                          fontWeight: 700,
                          letterSpacing: "0.06em",
                          textTransform: "uppercase",
                          color: isActive
                            ? "var(--brand-primary)"
                            : isStepDone
                            ? "var(--status-success)"
                            : "var(--text-muted)",
                          marginBottom: "0.1rem",
                        }}
                      >
                        Step {idx + 1}
                      </div>
                      <div
                        style={{
                          fontSize: "0.8125rem",
                          fontWeight: isActive ? 700 : 500,
                          color: isActive
                            ? "var(--text-primary)"
                            : isStepDone
                            ? "var(--text-secondary)"
                            : "var(--text-muted)",
                          whiteSpace: "nowrap",
                        }}
                      >
                        {step.label}
                      </div>
                    </div>
                  </div>

                  {/* Connecting Rail Line */}
                  {idx < STEPS.length - 1 && (
                    <div
                      style={{
                        flex: 1,
                        height: "2px",
                        margin: "0 0.5rem 1.4rem 0.5rem",
                        backgroundColor: isStepDone
                          ? "var(--status-success)"
                          : "var(--border-subtle)",
                        transition: "background-color 0.25s ease",
                      }}
                    />
                  )}
                </React.Fragment>
              );
            })}
          </div>
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
        ) : (
          <div
            style={{
              width: "100%",
              maxWidth: "1000px",
              margin: "0 auto",
            }}
          >
            {currentStep === "organization_profile" ? (
              /* Step 1: Organization Profile Form */
              <form
                onSubmit={handleNextFromOrg}
                className="glass-panel"
                style={{
                  padding: "2.75rem 3rem",
                  borderRadius: "20px",
                  border: "1px solid var(--border-glass)",
                  backgroundColor: "var(--glass-surface-elevated)",
                  boxShadow: "var(--shadow-md)",
                  display: "flex",
                  flexDirection: "column",
                  gap: "2rem",
                  position: "relative",
                  overflow: "hidden",
                }}
              >
                <div
                  style={{
                    position: "absolute",
                    top: 0,
                    left: 0,
                    right: 0,
                    height: "4px",
                    background: "linear-gradient(90deg, #3867f5 0%, #8a45f6 50%, #0faf83 100%)",
                  }}
                />

                <div>
                  <span
                    style={{
                      display: "inline-flex",
                      alignItems: "center",
                      gap: "0.5rem",
                      padding: "0.3rem 0.85rem",
                      borderRadius: "9999px",
                      fontSize: "0.75rem",
                      fontWeight: 700,
                      letterSpacing: "0.08em",
                      textTransform: "uppercase",
                      backgroundColor: "rgba(56, 103, 245, 0.08)",
                      color: "var(--brand-primary)",
                      border: "1px solid rgba(56, 103, 245, 0.2)",
                      marginBottom: "0.85rem",
                    }}
                  >
                    <span style={{ width: "6px", height: "6px", borderRadius: "50%", background: "var(--brand-primary)" }} />
                    Step 01 of 06
                  </span>
                  <h2
                    style={{
                      fontSize: "1.75rem",
                      fontWeight: 800,
                      margin: "0 0 0.5rem 0",
                      letterSpacing: "-0.03em",
                      color: "var(--text-primary)",
                    }}
                  >
                    Step 1: Organization Profile
                  </h2>
                  <p
                    style={{
                      color: "var(--text-secondary)",
                      fontSize: "0.9375rem",
                      margin: 0,
                      lineHeight: 1.6,
                      maxWidth: "800px",
                    }}
                  >
                    Specify corporate identity parameters. The organization code creates an immutable, isolated tenant partition boundary.
                  </p>
                </div>

                {/* Provisioning Context Card */}
                <div
                  style={{
                    padding: "1.25rem 1.75rem",
                    borderRadius: "14px",
                    background: "linear-gradient(135deg, var(--surface-soft-blue) 0%, var(--surface-soft-lavender) 100%)",
                    border: "1px solid rgba(56, 103, 245, 0.18)",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    flexWrap: "wrap",
                    gap: "1.25rem",
                  }}
                >
                  <div style={{ display: "flex", alignItems: "center", gap: "1rem" }}>
                    <div
                      style={{
                        width: "48px",
                        height: "48px",
                        borderRadius: "12px",
                        backgroundColor: "#ffffff",
                        border: "1px solid rgba(56, 103, 245, 0.2)",
                        boxShadow: "0 4px 12px rgba(56, 103, 245, 0.12)",
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                        color: "var(--brand-primary)",
                        flexShrink: 0,
                      }}
                    >
                      <BuildingIcon size={24} />
                    </div>
                    <div>
                      <div
                        style={{
                          fontSize: "0.75rem",
                          textTransform: "uppercase",
                          fontWeight: 700,
                          color: "var(--brand-primary)",
                          letterSpacing: "0.06em",
                          marginBottom: "0.2rem",
                        }}
                      >
                        New Tenant Partition
                      </div>
                      <div
                        style={{
                          fontSize: "1.125rem",
                          fontWeight: 800,
                          color: "var(--text-primary)",
                          letterSpacing: "-0.01em",
                        }}
                      >
                        {orgName || "Enterprise Tenant"}
                      </div>
                    </div>
                  </div>

                  <div
                    style={{
                      display: "inline-flex",
                      alignItems: "center",
                      gap: "0.45rem",
                      padding: "0.35rem 0.85rem",
                      borderRadius: "9999px",
                      fontSize: "0.75rem",
                      fontWeight: 700,
                      backgroundColor: "var(--status-success-bg)",
                      border: "1px solid var(--status-success-border)",
                      color: "var(--status-success)",
                    }}
                  >
                    <span className="badge-dot" style={{ width: "6px", height: "6px", borderRadius: "50%", backgroundColor: "var(--status-success)" }} />
                    Isolated Partition
                  </div>
                </div>

                <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }}>
                  <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))", gap: "1.5rem" }}>
                    <div>
                      <label
                        htmlFor="onboarding-org-code"
                        style={{
                          display: "block",
                          fontSize: "0.875rem",
                          fontWeight: 700,
                          marginBottom: "0.5rem",
                          color: "var(--text-primary)",
                        }}
                      >
                        Organization Code <span style={{ color: "var(--status-danger)" }}>*</span>
                      </label>
                      <div style={{ position: "relative", display: "flex", alignItems: "center" }}>
                        <span className="input-icon-left" style={{ left: "1rem" }}>
                          <BuildingIcon size={18} />
                        </span>
                        <input
                          id="onboarding-org-code"
                          type="text"
                          className={`form-input input-text form-input-with-icon-left ${fieldErrors.orgCode ? "form-input-error" : ""}`}
                          placeholder="e.g. acme-corp"
                          value={orgCode}
                          onChange={(e) => setOrgCode(e.target.value.toLowerCase())}
                          style={{
                            width: "100%",
                            fontFamily: "var(--font-code)",
                            minHeight: "48px",
                            fontSize: "0.9375rem",
                            borderRadius: "10px",
                            paddingLeft: "2.75rem",
                            border: "1.5px solid var(--border-subtle)",
                          }}
                        />
                      </div>
                      {fieldErrors.orgCode ? (
                        <span className="form-error" style={{ marginTop: "0.4rem", display: "flex", alignItems: "center", gap: "0.35rem" }}>
                          <AlertCircleIcon size={14} /> {fieldErrors.orgCode}
                        </span>
                      ) : (
                        <span style={{ fontSize: "0.8125rem", color: "var(--text-muted)", marginTop: "0.4rem", display: "block" }}>
                          Unique immutable slug used for subdomain routing and database isolation.
                        </span>
                      )}
                    </div>

                    <div>
                      <label
                        htmlFor="onboarding-org-name"
                        style={{
                          display: "block",
                          fontSize: "0.875rem",
                          fontWeight: 700,
                          marginBottom: "0.5rem",
                          color: "var(--text-primary)",
                        }}
                      >
                        Organization Name <span style={{ color: "var(--status-danger)" }}>*</span>
                      </label>
                      <input
                        id="onboarding-org-name"
                        type="text"
                        className={`form-input input-text ${fieldErrors.orgName ? "form-input-error" : ""}`}
                        placeholder="e.g. Acme Corporation"
                        value={orgName}
                        onChange={(e) => setOrgName(e.target.value)}
                        style={{
                          width: "100%",
                          minHeight: "48px",
                          fontSize: "0.9375rem",
                          borderRadius: "10px",
                          padding: "0 1rem",
                          border: "1.5px solid var(--border-subtle)",
                        }}
                      />
                      {fieldErrors.orgName ? (
                        <span className="form-error" style={{ marginTop: "0.4rem", display: "flex", alignItems: "center", gap: "0.35rem" }}>
                          <AlertCircleIcon size={14} /> {fieldErrors.orgName}
                        </span>
                      ) : (
                        <span style={{ fontSize: "0.8125rem", color: "var(--text-muted)", marginTop: "0.4rem", display: "block" }}>
                          Official corporate entity name shown across all tenant portals.
                        </span>
                      )}
                    </div>
                  </div>

                  <div>
                    <label
                      htmlFor="onboarding-org-desc"
                      style={{
                        display: "block",
                        fontSize: "0.875rem",
                        fontWeight: 700,
                        marginBottom: "0.5rem",
                        color: "var(--text-primary)",
                      }}
                    >
                      Description
                    </label>
                    <textarea
                      id="onboarding-org-desc"
                      className="form-input input-text"
                      rows={3}
                      placeholder="Operational purpose, enterprise division, regional jurisdiction, or deployment notes..."
                      value={orgDesc}
                      onChange={(e) => setOrgDesc(e.target.value)}
                      style={{
                        width: "100%",
                        resize: "vertical",
                        borderRadius: "10px",
                        fontSize: "0.9375rem",
                        padding: "0.85rem 1rem",
                        border: "1.5px solid var(--border-subtle)",
                        minHeight: "100px",
                        lineHeight: 1.5,
                      }}
                    />
                  </div>
                </div>

                <div style={{ display: "flex", justifyContent: "flex-end", paddingTop: "0.75rem" }}>
                  <button
                    type="submit"
                    disabled={isSubmitting}
                    className="btn-gradient"
                    style={{
                      padding: "0.85rem 2.25rem",
                      minHeight: "48px",
                      fontSize: "0.9375rem",
                      fontWeight: 700,
                      borderRadius: "10px",
                      color: "#ffffff",
                      border: "none",
                      cursor: isSubmitting ? "not-allowed" : "pointer",
                      boxShadow: "0 4px 16px rgba(56, 103, 245, 0.32)",
                      transition: "all 0.2s ease",
                    }}
                  >
                    {isSubmitting ? "Saving..." : "Continue to Administrator Setup →"}
                  </button>
                </div>
              </form>
            ) : currentStep === "admin_setup" ? (
              /* Step 2: Administrator Setup Form */
              <form
                onSubmit={handleNextFromAdmin}
                className="glass-panel"
                style={{
                  padding: "2.75rem 3rem",
                  borderRadius: "20px",
                  border: "1px solid var(--border-glass)",
                  backgroundColor: "var(--glass-surface-elevated)",
                  boxShadow: "var(--shadow-md)",
                  display: "flex",
                  flexDirection: "column",
                  gap: "2rem",
                  position: "relative",
                  overflow: "hidden",
                }}
              >
                <div
                  style={{
                    position: "absolute",
                    top: 0,
                    left: 0,
                    right: 0,
                    height: "4px",
                    background: "linear-gradient(90deg, #3867f5 0%, #8a45f6 50%, #0faf83 100%)",
                  }}
                />

                <div>
                  <span
                    style={{
                      display: "inline-flex",
                      alignItems: "center",
                      gap: "0.5rem",
                      padding: "0.3rem 0.85rem",
                      borderRadius: "9999px",
                      fontSize: "0.75rem",
                      fontWeight: 700,
                      letterSpacing: "0.08em",
                      textTransform: "uppercase",
                      backgroundColor: "rgba(56, 103, 245, 0.08)",
                      color: "var(--brand-primary)",
                      border: "1px solid rgba(56, 103, 245, 0.2)",
                      marginBottom: "0.85rem",
                    }}
                  >
                    <span style={{ width: "6px", height: "6px", borderRadius: "50%", background: "var(--brand-primary)" }} />
                    Step 02 of 06
                  </span>
                  <h2
                    style={{
                      fontSize: "1.75rem",
                      fontWeight: 800,
                      margin: "0 0 0.5rem 0",
                      letterSpacing: "-0.03em",
                      color: "var(--text-primary)",
                    }}
                  >
                    Step 2: Initial Tenant Administrator
                  </h2>
                  <p
                    style={{
                      color: "var(--text-secondary)",
                      fontSize: "0.9375rem",
                      margin: 0,
                      lineHeight: 1.6,
                      maxWidth: "800px",
                    }}
                  >
                    Assign primary administrator credentials. A secure single-use invitation and activation link will be generated automatically.
                  </p>
                </div>

                {/* Context Card */}
                <div
                  style={{
                    padding: "1.25rem 1.75rem",
                    borderRadius: "14px",
                    background: "linear-gradient(135deg, var(--surface-soft-blue) 0%, var(--surface-soft-lavender) 100%)",
                    border: "1px solid rgba(56, 103, 245, 0.18)",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    flexWrap: "wrap",
                    gap: "1.25rem",
                  }}
                >
                  <div style={{ display: "flex", alignItems: "center", gap: "1rem" }}>
                    <div
                      style={{
                        width: "48px",
                        height: "48px",
                        borderRadius: "12px",
                        backgroundColor: "#ffffff",
                        border: "1px solid rgba(56, 103, 245, 0.2)",
                        boxShadow: "0 4px 12px rgba(56, 103, 245, 0.12)",
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                        color: "var(--brand-primary)",
                        flexShrink: 0,
                      }}
                    >
                      <UserIcon size={24} />
                    </div>
                    <div>
                      <div
                        style={{
                          fontSize: "0.75rem",
                          textTransform: "uppercase",
                          fontWeight: 700,
                          color: "var(--brand-primary)",
                          letterSpacing: "0.06em",
                          marginBottom: "0.2rem",
                        }}
                      >
                        Target Organization
                      </div>
                      <div
                        style={{
                          fontSize: "1.125rem",
                          fontWeight: 800,
                          color: "var(--text-primary)",
                          letterSpacing: "-0.01em",
                        }}
                      >
                        {orgName || currentCase?.organization_name || "Enterprise"} ({orgCode || currentCase?.organization_code || "—"})
                      </div>
                    </div>
                  </div>

                  <div
                    style={{
                      display: "inline-flex",
                      alignItems: "center",
                      gap: "0.45rem",
                      padding: "0.35rem 0.85rem",
                      borderRadius: "9999px",
                      fontSize: "0.75rem",
                      fontWeight: 700,
                      backgroundColor: "var(--status-success-bg)",
                      border: "1px solid var(--status-success-border)",
                      color: "var(--status-success)",
                    }}
                  >
                    <span className="badge-dot" style={{ width: "6px", height: "6px", borderRadius: "50%", backgroundColor: "var(--status-success)" }} />
                    Admin Role Binding
                  </div>
                </div>

                <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }}>
                  <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))", gap: "1.5rem" }}>
                    <div>
                      <label
                        htmlFor="onboarding-admin-email"
                        style={{
                          display: "block",
                          fontSize: "0.875rem",
                          fontWeight: 700,
                          marginBottom: "0.5rem",
                          color: "var(--text-primary)",
                        }}
                      >
                        Administrator Email <span style={{ color: "var(--status-danger)" }}>*</span>
                      </label>
                      <div style={{ position: "relative", display: "flex", alignItems: "center" }}>
                        <span className="input-icon-left" style={{ left: "1rem" }}>
                          <UserIcon size={18} />
                        </span>
                        <input
                          id="onboarding-admin-email"
                          type="email"
                          className={`form-input input-text form-input-with-icon-left ${fieldErrors.adminEmail ? "form-input-error" : ""}`}
                          placeholder="admin@organization.com"
                          value={adminEmail}
                          onChange={(e) => setAdminEmail(e.target.value)}
                          style={{
                            width: "100%",
                            minHeight: "48px",
                            fontSize: "0.9375rem",
                            borderRadius: "10px",
                            paddingLeft: "2.75rem",
                            border: "1.5px solid var(--border-subtle)",
                          }}
                        />
                      </div>
                      {fieldErrors.adminEmail ? (
                        <span className="form-error" style={{ marginTop: "0.4rem", display: "flex", alignItems: "center", gap: "0.35rem" }}>
                          <AlertCircleIcon size={14} /> {fieldErrors.adminEmail}
                        </span>
                      ) : (
                        <span style={{ fontSize: "0.8125rem", color: "var(--text-muted)", marginTop: "0.4rem", display: "block" }}>
                          The single-use activation credential and invitation email are dispatched here.
                        </span>
                      )}
                    </div>

                    <div>
                      <label
                        htmlFor="onboarding-admin-name"
                        style={{
                          display: "block",
                          fontSize: "0.875rem",
                          fontWeight: 700,
                          marginBottom: "0.5rem",
                          color: "var(--text-primary)",
                        }}
                      >
                        Administrator Full Name
                      </label>
                      <input
                        id="onboarding-admin-name"
                        type="text"
                        className="form-input input-text"
                        placeholder="e.g. Jane Doe"
                        value={adminFullName}
                        onChange={(e) => setAdminFullName(e.target.value)}
                        style={{
                          width: "100%",
                          minHeight: "48px",
                          fontSize: "0.9375rem",
                          borderRadius: "10px",
                          padding: "0 1rem",
                          border: "1.5px solid var(--border-subtle)",
                        }}
                      />
                    </div>
                  </div>
                </div>

                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", paddingTop: "0.75rem" }}>
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
                    style={{ padding: "0.75rem 1.5rem", borderRadius: "10px", fontWeight: 600, fontSize: "0.875rem", minHeight: "46px" }}
                  >
                    ← Back
                  </button>
                  <button
                    type="submit"
                    disabled={isSubmitting}
                    className="btn-gradient"
                    style={{
                      padding: "0.85rem 2.25rem",
                      minHeight: "48px",
                      fontSize: "0.9375rem",
                      fontWeight: 700,
                      borderRadius: "10px",
                      color: "#ffffff",
                      border: "none",
                      cursor: isSubmitting ? "not-allowed" : "pointer",
                      boxShadow: "0 4px 16px rgba(56, 103, 245, 0.32)",
                      transition: "all 0.2s ease",
                    }}
                  >
                    {isSubmitting ? "Saving..." : "Continue to Plan Selection →"}
                  </button>
                </div>
              </form>
            ) : currentStep === "plan_selection" ? (
          /* Step 3: Plan Selection Form */
          <form
            onSubmit={handleNextFromPlan}
            className="glass-panel"
            style={{
              padding: "2.75rem 3rem",
              borderRadius: "20px",
              border: "1px solid var(--border-glass)",
              backgroundColor: "var(--glass-surface-elevated)",
              boxShadow: "var(--shadow-md)",
              display: "flex",
              flexDirection: "column",
              gap: "2rem",
              position: "relative",
              overflow: "hidden",
            }}
          >
            <div
              style={{
                position: "absolute",
                top: 0,
                left: 0,
                right: 0,
                height: "4px",
                background: "linear-gradient(90deg, #3867f5 0%, #8a45f6 50%, #0faf83 100%)",
              }}
            />

            <div>
              <span
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  gap: "0.5rem",
                  padding: "0.3rem 0.85rem",
                  borderRadius: "9999px",
                  fontSize: "0.75rem",
                  fontWeight: 700,
                  letterSpacing: "0.08em",
                  textTransform: "uppercase",
                  backgroundColor: "rgba(56, 103, 245, 0.08)",
                  color: "var(--brand-primary)",
                  border: "1px solid rgba(56, 103, 245, 0.2)",
                  marginBottom: "0.85rem",
                }}
              >
                <span style={{ width: "6px", height: "6px", borderRadius: "50%", background: "var(--brand-primary)" }} />
                Step 03 of 06
              </span>
              <h2
                style={{
                  fontSize: "1.75rem",
                  fontWeight: 800,
                  margin: "0 0 0.5rem 0",
                  letterSpacing: "-0.03em",
                  color: "var(--text-primary)",
                }}
              >
                Step 3: Commercial Plan & Packaging
              </h2>
              <p
                style={{
                  color: "var(--text-secondary)",
                  fontSize: "0.9375rem",
                  margin: 0,
                  lineHeight: 1.6,
                  maxWidth: "800px",
                }}
              >
                Select commercial tier packaging and billing boundaries for this tenant organization.
              </p>
            </div>

            <div style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>
              <div>
                <label htmlFor="onboarding-plan-select" style={{ display: "block", fontSize: "0.8125rem", fontWeight: 600, marginBottom: "0.45rem", color: "var(--text-primary)" }}>
                  Available Active Plans
                </label>
                <select
                  id="onboarding-plan-select"
                  className="form-input input-text"
                  value={selectedPlanVersionId}
                  onChange={(e) => {
                    setSelectedPlanVersionId(e.target.value);
                    setSelectedPriceId("");
                  }}
                  style={{ width: "100%", minHeight: "42px", fontSize: "0.875rem", borderRadius: "8px" }}
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
                  <label htmlFor="onboarding-price-select" style={{ display: "block", fontSize: "0.8125rem", fontWeight: 600, marginBottom: "0.45rem", color: "var(--text-primary)" }}>
                    Pricing Interval & Currency
                  </label>
                  <select
                    id="onboarding-price-select"
                    className="form-input input-text"
                    value={selectedPriceId}
                    onChange={(e) => setSelectedPriceId(e.target.value)}
                    style={{ width: "100%", minHeight: "42px", fontSize: "0.875rem", borderRadius: "8px" }}
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
                <div
                  style={{
                    padding: "1rem 1.25rem",
                    borderRadius: "10px",
                    backgroundColor: "var(--surface-soft-blue)",
                    border: "1px solid rgba(56, 103, 245, 0.2)",
                    display: "flex",
                    alignItems: "center",
                    gap: "0.75rem",
                  }}
                >
                  <input
                    id="onboarding-trial-checkbox"
                    type="checkbox"
                    checked={isTrial}
                    onChange={(e) => setIsTrial(e.target.checked)}
                    style={{ width: "18px", height: "18px", cursor: "pointer" }}
                  />
                  <label htmlFor="onboarding-trial-checkbox" style={{ cursor: "pointer", fontSize: "0.875rem", fontWeight: 600, color: "var(--text-primary)" }}>
                    Provision as 14-day trial period (zero upfront payment required)
                  </label>
                </div>
              )}
            </div>

            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", paddingTop: "0.5rem" }}>
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
                style={{ padding: "0.55rem 1.15rem", borderRadius: "8px" }}
              >
                ← Back
              </button>
              <button
                type="submit"
                disabled={isSubmitting}
                className="btn-gradient"
                style={{
                  padding: "0.625rem 1.5rem",
                  minHeight: "42px",
                  fontSize: "0.875rem",
                  fontWeight: 600,
                  borderRadius: "8px",
                  color: "#ffffff",
                  border: "none",
                  cursor: isSubmitting ? "not-allowed" : "pointer",
                  boxShadow: "0 4px 14px rgba(56, 103, 245, 0.28)",
                }}
              >
                {isSubmitting ? "Saving..." : "Continue to Product Entitlements →"}
              </button>
            </div>
          </form>
        ) : currentStep === "product_entitlements" ? (
          /* Step 4: Product Entitlements Form */
          <form
            onSubmit={handleNextFromProducts}
            className="glass-panel"
            style={{
              padding: "2.75rem 3rem",
              borderRadius: "20px",
              border: "1px solid var(--border-glass)",
              backgroundColor: "var(--glass-surface-elevated)",
              boxShadow: "var(--shadow-md)",
              display: "flex",
              flexDirection: "column",
              gap: "2rem",
              position: "relative",
              overflow: "hidden",
            }}
          >
            <div
              style={{
                position: "absolute",
                top: 0,
                left: 0,
                right: 0,
                height: "4px",
                background: "linear-gradient(90deg, #3867f5 0%, #8a45f6 50%, #0faf83 100%)",
              }}
            />

            <div>
              <span
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  gap: "0.5rem",
                  padding: "0.3rem 0.85rem",
                  borderRadius: "9999px",
                  fontSize: "0.75rem",
                  fontWeight: 700,
                  letterSpacing: "0.08em",
                  textTransform: "uppercase",
                  backgroundColor: "rgba(56, 103, 245, 0.08)",
                  color: "var(--brand-primary)",
                  border: "1px solid rgba(56, 103, 245, 0.2)",
                  marginBottom: "0.85rem",
                }}
              >
                <span style={{ width: "6px", height: "6px", borderRadius: "50%", background: "var(--brand-primary)" }} />
                Step 04 of 06
              </span>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: "1rem", flexWrap: "wrap" }}>
                <div>
                  <h2
                    style={{
                      fontSize: "1.75rem",
                      fontWeight: 800,
                      margin: "0 0 0.5rem 0",
                      letterSpacing: "-0.03em",
                      color: "var(--text-primary)",
                    }}
                  >
                    Step 4: Product Entitlements
                  </h2>
                  <p
                    style={{
                      color: "var(--text-secondary)",
                      fontSize: "0.9375rem",
                      margin: 0,
                      lineHeight: 1.6,
                      maxWidth: "800px",
                    }}
                  >
                    Select which platform products the new tenant is entitled to use. Active products will be directly provisioned upon confirmation.
                  </p>
                </div>
                {options && options.products.length > 0 && (
                  <div style={{ display: "flex", gap: "0.5rem", flexShrink: 0 }}>
                    <button
                      type="button"
                      onClick={() => setSelectedProductIds(options.products.map((p) => p.id))}
                      style={{
                        fontSize: "0.75rem",
                        padding: "0.4rem 0.85rem",
                        borderRadius: "9999px",
                        fontWeight: 600,
                        border: "1px solid rgba(56, 103, 245, 0.3)",
                        background: "rgba(56, 103, 245, 0.1)",
                        color: "var(--brand-primary, #3867f5)",
                        cursor: "pointer",
                      }}
                    >
                      Select All
                    </button>
                    <button
                      type="button"
                      onClick={() => setSelectedProductIds([])}
                      style={{
                        fontSize: "0.75rem",
                        padding: "0.4rem 0.85rem",
                        borderRadius: "9999px",
                        fontWeight: 600,
                        border: "1px solid var(--border-color, rgba(255,255,255,0.12))",
                        background: "rgba(255, 255, 255, 0.04)",
                        color: "var(--text-secondary)",
                        cursor: "pointer",
                      }}
                    >
                      Deselect All
                    </button>
                  </div>
                )}
              </div>
            </div>

            {(!options || options.products.length === 0) ? (
              <div
                style={{
                  padding: "2.5rem 1.5rem",
                  textAlign: "center",
                  borderRadius: "12px",
                  border: "1px dashed var(--border-color, rgba(255,255,255,0.15))",
                  color: "var(--text-secondary)",
                }}
              >
                No active products available in Product Registry.
              </div>
            ) : (
              <div style={{ display: "grid", gridTemplateColumns: "1fr", gap: "0.875rem" }}>
                {options.products.map((prod) => {
                  const isSelected = selectedProductIds.includes(prod.id);
                  const moduleCount = prod.modules?.length || 0;

                  return (
                    <React.Fragment key={prod.id}>
                      <div
                        onClick={() => handleToggleProduct(prod.id)}
                        style={{
                          padding: "1.125rem 1.25rem",
                          display: "flex",
                          alignItems: "center",
                          justifyContent: "space-between",
                          cursor: "pointer",
                          border: isSelected
                            ? "2px solid var(--brand-primary, #3867f5)"
                            : "1px solid var(--border-color, rgba(255,255,255,0.08))",
                          backgroundColor: isSelected
                            ? "rgba(56, 103, 245, 0.07)"
                            : "rgba(255, 255, 255, 0.02)",
                          borderRadius: "12px",
                          boxShadow: isSelected ? "0 4px 16px rgba(56, 103, 245, 0.12)" : "none",
                          transition: "all 0.18s ease-in-out",
                        }}
                      >
                        <div style={{ display: "flex", alignItems: "flex-start", gap: "0.875rem" }}>
                          <input
                            type="checkbox"
                            checked={isSelected}
                            onChange={() => handleToggleProduct(prod.id)}
                            onClick={(e) => e.stopPropagation()}
                            style={{
                              marginTop: "0.2rem",
                              cursor: "pointer",
                              width: "18px",
                              height: "18px",
                              accentColor: "var(--brand-primary, #3867f5)",
                            }}
                          />
                          <div>
                            <div style={{ display: "flex", alignItems: "center", gap: "0.6rem" }}>
                              <span style={{ fontWeight: 700, fontSize: "0.95rem", color: "var(--text-primary)" }}>
                                {prod.name}
                              </span>
                              <span
                                style={{
                                  fontSize: "0.7rem",
                                  padding: "0.15rem 0.5rem",
                                  borderRadius: "6px",
                                  backgroundColor: "rgba(255, 255, 255, 0.06)",
                                  fontFamily: "var(--font-code)",
                                  color: "var(--text-muted)",
                                  border: "1px solid rgba(255,255,255,0.06)",
                                }}
                              >
                                {prod.code}
                              </span>
                            </div>
                            <p style={{ margin: "0.35rem 0 0 0", fontSize: "0.8125rem", color: "var(--text-secondary)", lineHeight: 1.45 }}>
                              {prod.description || "No description provided."}
                            </p>
                          </div>
                        </div>

                        <div style={{ textAlign: "right", whiteSpace: "nowrap", paddingLeft: "1rem" }}>
                          <span
                            style={{
                              fontSize: "0.75rem",
                              color: "var(--text-muted)",
                              fontWeight: 500,
                            }}
                          >
                            {moduleCount} {moduleCount === 1 ? "module" : "modules"}
                          </span>
                          <div
                            style={{
                              fontSize: "0.75rem",
                              fontWeight: 700,
                              marginTop: "0.25rem",
                              color: isSelected ? "var(--brand-primary, #3867f5)" : "var(--text-muted)",
                            }}
                          >
                            {isSelected ? "Entitled ✓" : "Disabled"}
                          </div>
                        </div>
                      </div>

                      {/* LMS-only Console Selection */}
                      {isSelected && (prod.code?.toLowerCase().includes("lms") || prod.name?.toLowerCase().includes("learning")) && (
                        <div
                          style={{
                            marginTop: "-0.375rem",
                            marginBottom: "0.5rem",
                            padding: "0.875rem 1.125rem",
                            borderRadius: "10px",
                            backgroundColor: "rgba(56, 103, 245, 0.05)",
                            border: "1px solid rgba(56, 103, 245, 0.2)",
                          }}
                          onClick={(e) => e.stopPropagation()}
                        >
                          <div style={{ display: "flex", alignItems: "center", gap: "0.6rem" }}>
                            <input
                              type="radio"
                              id={`lms-console-${prod.id}`}
                              name={`console-selection-${prod.id}`}
                              checked={true}
                              readOnly
                              style={{ accentColor: "var(--brand-primary, #3867f5)", cursor: "default" }}
                            />
                            <label
                              htmlFor={`lms-console-${prod.id}`}
                              style={{ fontSize: "0.85rem", fontWeight: 700, color: "var(--text-primary)", cursor: "default" }}
                            >
                              Tenant Console
                            </label>
                            <span
                              style={{
                                fontSize: "0.6875rem",
                                padding: "0.15rem 0.5rem",
                                borderRadius: "9999px",
                                backgroundColor: "rgba(56, 103, 245, 0.15)",
                                color: "var(--brand-primary, #3867f5)",
                                fontWeight: 700,
                              }}
                            >
                              Tenant Admin Option Only
                            </span>
                          </div>
                          <p style={{ margin: "0.35rem 0 0 1.6rem", fontSize: "0.75rem", color: "var(--text-secondary)" }}>
                            Tenant Onboarding provisions the initial Tenant Administrator. Only Tenant Console is available.
                          </p>
                        </div>
                      )}
                    </React.Fragment>
                  );
                })}
              </div>
            )}

            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: "1rem", paddingTop: "1.25rem", borderTop: "1px solid var(--border-color, rgba(255,255,255,0.08))" }}>
              <button
                type="button"
                onClick={() => {
                  if (currentCase) {
                    void onboardingApi
                      .transitionStep(currentCase.id, { target_step: "plan_selection" })
                      .then((res) => setCurrentCase(res));
                  }
                }}
                style={{
                  padding: "0.65rem 1.25rem",
                  borderRadius: "10px",
                  fontWeight: 600,
                  fontSize: "0.875rem",
                  border: "1px solid var(--border-color, rgba(255,255,255,0.12))",
                  background: "transparent",
                  color: "var(--text-secondary)",
                  cursor: "pointer",
                }}
              >
                ← Back
              </button>
              <button
                type="submit"
                className="btn-gradient"
                disabled={isSubmitting}
                style={{
                  padding: "0.75rem 1.75rem",
                  borderRadius: "10px",
                  fontWeight: 700,
                  fontSize: "0.875rem",
                  background: "linear-gradient(135deg, #3867f5 0%, #2952cc 100%)",
                  color: "#ffffff",
                  border: "none",
                  cursor: isSubmitting ? "not-allowed" : "pointer",
                  boxShadow: "0 4px 14px rgba(56, 103, 245, 0.28)",
                }}
              >
                {isSubmitting ? "Saving..." : "Continue to Console Feature Ceilings →"}
              </button>
            </div>
          </form>
        ) : currentStep === "feature_ceilings" ? (
          /* Step 5: Console Feature Ceilings Form */
          <form
            onSubmit={handleNextFromCeilings}
            className="glass-panel"
            style={{
              padding: "2.75rem 3rem",
              borderRadius: "20px",
              border: "1px solid var(--border-glass)",
              backgroundColor: "var(--glass-surface-elevated)",
              boxShadow: "var(--shadow-md)",
              display: "flex",
              flexDirection: "column",
              gap: "2.5rem",
              position: "relative",
              overflow: "hidden",
            }}
          >
            <div
              style={{
                position: "absolute",
                top: 0,
                left: 0,
                right: 0,
                height: "4px",
                background: "linear-gradient(90deg, #3867f5 0%, #8a45f6 50%, #0faf83 100%)",
              }}
            />

            {/* Header */}
            <div>
              <span
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  gap: "0.5rem",
                  padding: "0.3rem 0.85rem",
                  borderRadius: "9999px",
                  fontSize: "0.75rem",
                  fontWeight: 700,
                  letterSpacing: "0.08em",
                  textTransform: "uppercase",
                  backgroundColor: "rgba(56, 103, 245, 0.08)",
                  color: "var(--brand-primary)",
                  border: "1px solid rgba(56, 103, 245, 0.2)",
                  marginBottom: "0.85rem",
                }}
              >
                <span style={{ width: "6px", height: "6px", borderRadius: "50%", background: "var(--brand-primary)" }} />
                Step 05 of 06
              </span>
              <h2
                style={{
                  fontSize: "1.75rem",
                  fontWeight: 800,
                  margin: "0 0 0.5rem 0",
                  letterSpacing: "-0.03em",
                  color: "var(--text-primary)",
                }}
              >
                Step 5: Console Feature Ceilings & Policies
              </h2>
              <p
                style={{
                  color: "var(--text-secondary)",
                  fontSize: "0.9375rem",
                  margin: 0,
                  lineHeight: 1.6,
                  maxWidth: "850px",
                }}
              >
                Configure module policies and feature-level maximum ceilings for the entitled products and tenant admin console. Toggle any module or capability to immediately grant or restrict tenant access.
              </p>
            </div>

            {/* Quick Metrics Bar */}
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
                gap: "1rem",
                padding: "1.25rem 1.5rem",
                borderRadius: "14px",
                backgroundColor: "var(--glass-surface-sunken)",
                border: "1px solid var(--border-glass)",
              }}
            >
              <div>
                <span style={{ fontSize: "0.75rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--text-muted)", display: "block", marginBottom: "0.25rem" }}>
                  Entitled Products
                </span>
                <span style={{ fontSize: "1.375rem", fontWeight: 800, color: "var(--text-primary)", letterSpacing: "-0.02em" }}>
                  {selectedProducts.length}
                </span>
              </div>
              <div>
                <span style={{ fontSize: "0.75rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--text-muted)", display: "block", marginBottom: "0.25rem" }}>
                  Console Modules
                </span>
                <span style={{ fontSize: "1.375rem", fontWeight: 800, color: "var(--text-primary)", letterSpacing: "-0.02em" }}>
                  {options?.console_modules?.length || 0}
                </span>
              </div>
              <div>
                <span style={{ fontSize: "0.75rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--text-muted)", display: "block", marginBottom: "0.25rem" }}>
                  Active Granular Ceilings
                </span>
                <span style={{ fontSize: "1.375rem", fontWeight: 800, color: "var(--status-success, #10b981)", letterSpacing: "-0.02em" }}>
                  {(() => {
                    if (!options?.console_modules) return 0;
                    let total = 0;
                    options.console_modules.forEach((cm) => {
                      cm.permissions?.forEach((p) => {
                        if (featureCeilings.permission_ceilings[p.key] !== false) total++;
                      });
                    });
                    return total;
                  })()}{" "}
                  <span style={{ fontSize: "0.8125rem", fontWeight: 500, color: "var(--text-secondary)" }}>
                    of{" "}
                    {(() => {
                      if (!options?.console_modules) return 0;
                      let total = 0;
                      options.console_modules.forEach((cm) => {
                        total += cm.permissions?.length || 0;
                      });
                      return total;
                    })()}{" "}
                    caps
                  </span>
                </span>
              </div>
            </div>

            {/* SECTION 1: Product Feature Ceilings */}
            <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "0.75rem" }}>
                <div>
                  <h3
                    style={{
                      fontSize: "1.125rem",
                      fontWeight: 800,
                      margin: "0 0 0.25rem 0",
                      color: "var(--text-primary)",
                      letterSpacing: "-0.02em",
                      display: "flex",
                      alignItems: "center",
                      gap: "0.6rem",
                    }}
                  >
                    <span>Product Feature Ceilings</span>
                    <span
                      style={{
                        fontSize: "0.75rem",
                        fontWeight: 700,
                        padding: "0.2rem 0.65rem",
                        borderRadius: "9999px",
                        background: "rgba(56, 103, 245, 0.1)",
                        color: "var(--brand-primary, #3867f5)",
                        border: "1px solid rgba(56, 103, 245, 0.2)",
                      }}
                    >
                      {selectedProducts.length} Entitled {selectedProducts.length === 1 ? "Product" : "Products"}
                    </span>
                  </h3>
                  <p style={{ margin: 0, fontSize: "0.8125rem", color: "var(--text-secondary)" }}>
                    Module allocation and granular capability flags for entitled platform products.
                  </p>
                </div>
              </div>

              {selectedProducts.length === 0 ? (
                <div
                  style={{
                    padding: "2.5rem",
                    textAlign: "center",
                    borderRadius: "14px",
                    border: "1px dashed var(--border-glass)",
                    background: "var(--glass-surface-sunken)",
                    color: "var(--text-secondary)",
                    fontSize: "0.875rem",
                  }}
                >
                  No products selected in previous step. Return to Step 4 to select product entitlements.
                </div>
              ) : (
                <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
                  {selectedProducts.map((prod) => {
                    const hasModules = prod.modules && prod.modules.length > 0;

                    return (
                      <div
                        key={prod.id}
                        style={{
                          borderRadius: "14px",
                          border: "1px solid var(--border-glass)",
                          backgroundColor: "var(--glass-surface-elevated)",
                          boxShadow: "var(--shadow-sm)",
                          overflow: "hidden",
                        }}
                      >
                        {/* Product Header Row */}
                        <div
                          style={{
                            padding: "1rem 1.25rem",
                            background: "var(--glass-surface-sunken)",
                            borderBottom: hasModules ? "1px solid var(--border-glass)" : "none",
                            display: "flex",
                            justifyContent: "space-between",
                            alignItems: "center",
                            flexWrap: "wrap",
                            gap: "0.75rem",
                          }}
                        >
                          <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
                            <div
                              style={{
                                width: "34px",
                                height: "34px",
                                borderRadius: "8px",
                                background: "linear-gradient(135deg, rgba(56, 103, 245, 0.2) 0%, rgba(138, 69, 246, 0.2) 100%)",
                                border: "1px solid rgba(56, 103, 245, 0.3)",
                                display: "flex",
                                alignItems: "center",
                                justifyContent: "center",
                                color: "var(--brand-primary, #3867f5)",
                                fontWeight: 800,
                                fontSize: "0.875rem",
                              }}
                            >
                              {prod.code ? prod.code.substring(0, 2).toUpperCase() : "PR"}
                            </div>
                            <div>
                              <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                                <span style={{ fontWeight: 800, fontSize: "0.95rem", color: "var(--text-primary)" }}>{prod.name}</span>
                                <span
                                  style={{
                                    fontSize: "0.7rem",
                                    padding: "0.15rem 0.5rem",
                                    borderRadius: "6px",
                                    backgroundColor: "rgba(255, 255, 255, 0.06)",
                                    fontFamily: "var(--font-code)",
                                    color: "var(--text-secondary)",
                                    border: "1px solid var(--border-subtle)",
                                  }}
                                >
                                  {prod.code}
                                </span>
                              </div>
                              {prod.description && (
                                <p style={{ margin: "0.15rem 0 0 0", fontSize: "0.75rem", color: "var(--text-muted)" }}>
                                  {prod.description}
                                </p>
                              )}
                            </div>
                          </div>

                          <span
                            style={{
                              fontSize: "0.72rem",
                              fontWeight: 700,
                              color: "var(--status-success, #10b981)",
                              backgroundColor: "rgba(16, 185, 129, 0.12)",
                              border: "1px solid rgba(16, 185, 129, 0.25)",
                              padding: "0.25rem 0.75rem",
                              borderRadius: "9999px",
                              display: "inline-flex",
                              alignItems: "center",
                              gap: "0.35rem",
                            }}
                          >
                            <span style={{ width: "6px", height: "6px", borderRadius: "50%", background: "var(--status-success, #10b981)" }} />
                            Entitled Product ✓
                          </span>
                        </div>

                        {/* Product Body */}
                        <div style={{ padding: "1rem 1.25rem" }}>
                          {!hasModules ? (
                            <div
                              style={{
                                display: "flex",
                                alignItems: "center",
                                gap: "0.6rem",
                                padding: "0.75rem 1rem",
                                borderRadius: "10px",
                                background: "var(--glass-surface-sunken)",
                                border: "1px solid var(--border-subtle)",
                                color: "var(--text-secondary)",
                                fontSize: "0.8125rem",
                              }}
                            >
                              <CheckCircleIcon size={16} style={{ color: "var(--status-success, #10b981)", flexShrink: 0 }} />
                              <span>
                                <strong>Standard Platform Access:</strong> Fully entitled for this tenant workspace. All core capabilities are provisioned without granular sub-module restrictions.
                              </span>
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
                                      padding: "0.875rem 1rem",
                                      borderRadius: "10px",
                                      backgroundColor: isModEnabled ? "rgba(56, 103, 245, 0.04)" : "var(--glass-surface-sunken)",
                                      border: isModEnabled ? "1px solid rgba(56, 103, 245, 0.2)" : "1px solid var(--border-subtle)",
                                    }}
                                  >
                                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "0.75rem" }}>
                                      <div>
                                        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                                          <span style={{ fontWeight: 700, fontSize: "0.875rem", color: "var(--text-primary)" }}>{mod.name}</span>
                                          <span style={{ fontSize: "0.6875rem", fontFamily: "var(--font-code)", color: "var(--text-muted)" }}>
                                            {mod.code}
                                          </span>
                                        </div>
                                        {mod.description && (
                                          <p style={{ margin: "0.2rem 0 0 0", fontSize: "0.75rem", color: "var(--text-secondary)" }}>
                                            {mod.description}
                                          </p>
                                        )}
                                      </div>

                                      <ToggleSwitch
                                        checked={isModEnabled}
                                        onChange={() => handleToggleProductModule(mod.id)}
                                        label={isModEnabled ? "Module Active" : "Disabled"}
                                        activeColor="var(--brand-primary, #3867f5)"
                                        size="md"
                                      />
                                    </div>

                                    {/* Sub-features if present */}
                                    {hasFeatures && isModEnabled && (
                                      <div
                                        style={{
                                          marginTop: "0.75rem",
                                          paddingLeft: "1.25rem",
                                          display: "flex",
                                          flexDirection: "column",
                                          gap: "0.45rem",
                                          borderLeft: "2px solid rgba(56, 103, 245, 0.25)",
                                        }}
                                      >
                                        {mod.features.map((feat) => {
                                          const isFeatEnabled = featureCeilings.product_features[feat.id] !== false;

                                          return (
                                            <div
                                              key={feat.id}
                                              style={{
                                                display: "flex",
                                                justifyContent: "space-between",
                                                alignItems: "center",
                                                padding: "0.45rem 0.75rem",
                                                borderRadius: "8px",
                                                backgroundColor: "var(--glass-surface-elevated)",
                                                border: "1px solid var(--border-subtle)",
                                              }}
                                            >
                                              <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                                                <span style={{ fontSize: "0.8125rem", fontWeight: 600, color: "var(--text-primary)" }}>{feat.name}</span>
                                                <span style={{ fontSize: "0.6875rem", fontFamily: "var(--font-code)", color: "var(--text-muted)" }}>
                                                  {feat.code}
                                                </span>
                                              </div>

                                              <ToggleSwitch
                                                checked={isFeatEnabled}
                                                onChange={() => handleToggleProductFeature(feat.id)}
                                                label={isFeatEnabled ? "Feature ON" : "Feature OFF"}
                                                activeColor="var(--brand-primary, #3867f5)"
                                                size="sm"
                                              />
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
                      </div>
                    );
                  })}
                </div>
              )}
            </div>

            {/* SECTION 2: Tenant Console Module Policies & Permission Ceilings */}
            {options?.console_modules && options.console_modules.length > 0 && (
              <div style={{ display: "flex", flexDirection: "column", gap: "1.25rem", marginTop: "0.5rem" }}>
                <div
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "flex-start",
                    flexWrap: "wrap",
                    gap: "1rem",
                    paddingBottom: "0.75rem",
                    borderBottom: "1px solid var(--border-glass)",
                  }}
                >
                  <div>
                    <h3
                      style={{
                        fontSize: "1.25rem",
                        fontWeight: 800,
                        margin: "0 0 0.35rem 0",
                        color: "var(--text-primary)",
                        letterSpacing: "-0.025em",
                        display: "flex",
                        alignItems: "center",
                        gap: "0.6rem",
                      }}
                    >
                      <ShieldCheckIcon size={20} style={{ color: "var(--brand-primary, #3867f5)" }} />
                      <span>Tenant Console Module Policies & Permission Ceilings</span>
                    </h3>
                    <p style={{ margin: 0, fontSize: "0.875rem", color: "var(--text-secondary)", lineHeight: 1.5, maxWidth: "800px" }}>
                      Manage visibility and granular access rights for the tenant admin console. Toggle any module switch or individual permission ceiling below to grant or restrict administrator capabilities.
                    </p>
                  </div>

                  {/* Bulk Actions */}
                  <div style={{ display: "flex", gap: "0.6rem", flexWrap: "wrap" }}>
                    <button
                      type="button"
                      onClick={handleGrantAllConsolePermissions}
                      style={{
                        fontSize: "0.75rem",
                        padding: "0.45rem 0.85rem",
                        borderRadius: "8px",
                        fontWeight: 700,
                        border: "1px solid rgba(16, 185, 129, 0.35)",
                        background: "rgba(16, 185, 129, 0.12)",
                        color: "var(--status-success, #10b981)",
                        cursor: "pointer",
                        display: "inline-flex",
                        alignItems: "center",
                        gap: "0.4rem",
                        transition: "all 0.15s ease",
                      }}
                    >
                      <CheckCircleIcon size={14} />
                      Grant All Permissions
                    </button>
                    <button
                      type="button"
                      onClick={handleRevokeAllNonCorePermissions}
                      style={{
                        fontSize: "0.75rem",
                        padding: "0.45rem 0.85rem",
                        borderRadius: "8px",
                        fontWeight: 600,
                        border: "1px solid var(--border-glass)",
                        background: "var(--glass-surface-sunken)",
                        color: "var(--text-secondary)",
                        cursor: "pointer",
                        transition: "all 0.15s ease",
                      }}
                    >
                      Restrict Non-Core
                    </button>
                  </div>
                </div>

                {/* Console Modules Cards */}
                <div style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>
                  {options.console_modules.map((cm) => {
                    const isModEnabled = cm.is_core || featureCeilings.module_policies[cm.key] !== false;
                    const hasPerms = cm.permissions && cm.permissions.length > 0;

                    return (
                      <div
                        key={cm.key}
                        style={{
                          borderRadius: "16px",
                          border: `1px solid ${isModEnabled ? "var(--border-glass)" : "var(--border-subtle)"}`,
                          backgroundColor: "var(--glass-surface-elevated)",
                          boxShadow: "var(--shadow-sm)",
                          overflow: "hidden",
                          transition: "border-color 0.2s ease, opacity 0.2s ease",
                          opacity: isModEnabled ? 1 : 0.82,
                        }}
                      >
                        {/* Module Header Bar */}
                        <div
                          style={{
                            padding: "1.1rem 1.5rem",
                            background: isModEnabled ? "var(--glass-surface-sunken)" : "rgba(0, 0, 0, 0.05)",
                            borderBottom: hasPerms && isModEnabled ? "1px solid var(--border-glass)" : "none",
                            display: "flex",
                            justifyContent: "space-between",
                            alignItems: "center",
                            flexWrap: "wrap",
                            gap: "1rem",
                          }}
                        >
                          <div>
                            <div style={{ display: "flex", alignItems: "center", gap: "0.6rem", flexWrap: "wrap" }}>
                              <span style={{ fontWeight: 800, fontSize: "1rem", color: "var(--text-primary)", letterSpacing: "-0.01em" }}>
                                {cm.display_name}
                              </span>
                              <span
                                style={{
                                  fontSize: "0.6875rem",
                                  padding: "0.15rem 0.45rem",
                                  borderRadius: "6px",
                                  backgroundColor: "rgba(255, 255, 255, 0.06)",
                                  fontFamily: "var(--font-code)",
                                  color: "var(--text-muted)",
                                  border: "1px solid var(--border-subtle)",
                                }}
                              >
                                {cm.key}
                              </span>
                              {cm.is_core && (
                                <span
                                  style={{
                                    fontSize: "0.6875rem",
                                    padding: "0.15rem 0.55rem",
                                    borderRadius: "9999px",
                                    backgroundColor: "rgba(56, 103, 245, 0.12)",
                                    color: "var(--brand-primary, #3867f5)",
                                    fontWeight: 700,
                                    border: "1px solid rgba(56, 103, 245, 0.25)",
                                    display: "inline-flex",
                                    alignItems: "center",
                                    gap: "0.3rem",
                                  }}
                                >
                                  <LockIcon size={12} />
                                  Core System Module (Always Active)
                                </span>
                              )}
                            </div>
                            {cm.description && (
                              <p style={{ margin: "0.25rem 0 0 0", fontSize: "0.8125rem", color: "var(--text-secondary)", lineHeight: 1.45 }}>
                                {cm.description}
                              </p>
                            )}
                          </div>

                          {/* Master Module Toggle */}
                          <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
                            {cm.is_core ? (
                              <span
                                style={{
                                  fontSize: "0.75rem",
                                  fontWeight: 700,
                                  color: "var(--brand-primary, #3867f5)",
                                  background: "rgba(56, 103, 245, 0.08)",
                                  padding: "0.35rem 0.85rem",
                                  borderRadius: "9999px",
                                  border: "1px solid rgba(56, 103, 245, 0.2)",
                                  display: "inline-flex",
                                  alignItems: "center",
                                  gap: "0.35rem",
                                }}
                              >
                                <LockIcon size={12} />
                                Core (Locked Active)
                              </span>
                            ) : (
                              <ToggleSwitch
                                checked={isModEnabled}
                                onChange={() => handleToggleConsoleModule(cm.key, false)}
                                label={isModEnabled ? "Module Active" : "Module Disabled"}
                                sublabel={isModEnabled ? "Available in console" : "Hidden from console"}
                                activeColor="var(--brand-primary, #3867f5)"
                                size="md"
                              />
                            )}
                          </div>
                        </div>

                        {/* Granular Permissions Table */}
                        {hasPerms && isModEnabled ? (
                          <div style={{ overflowX: "auto" }}>
                            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.875rem" }}>
                              <thead>
                                <tr
                                  style={{
                                    background: "rgba(0, 0, 0, 0.02)",
                                    borderBottom: "1px solid var(--border-glass)",
                                  }}
                                >
                                  <th
                                    style={{
                                      textAlign: "left",
                                      padding: "0.75rem 1.5rem",
                                      fontSize: "0.6875rem",
                                      fontWeight: 700,
                                      letterSpacing: "0.06em",
                                      textTransform: "uppercase",
                                      color: "var(--text-muted)",
                                      width: "48%",
                                    }}
                                  >
                                    Feature / Granular Permission
                                  </th>
                                  <th
                                    style={{
                                      textAlign: "left",
                                      padding: "0.75rem 1.5rem",
                                      fontSize: "0.6875rem",
                                      fontWeight: 700,
                                      letterSpacing: "0.06em",
                                      textTransform: "uppercase",
                                      color: "var(--text-muted)",
                                      width: "28%",
                                    }}
                                  >
                                    System Permission Key
                                  </th>
                                  <th
                                    style={{
                                      textAlign: "right",
                                      padding: "0.75rem 1.5rem",
                                      fontSize: "0.6875rem",
                                      fontWeight: 700,
                                      letterSpacing: "0.06em",
                                      textTransform: "uppercase",
                                      color: "var(--text-muted)",
                                      width: "24%",
                                    }}
                                  >
                                    Access Control Ceiling
                                  </th>
                                </tr>
                              </thead>
                              <tbody>
                                {cm.permissions.map((perm, pIdx) => {
                                  const isPermAllowed = featureCeilings.permission_ceilings[perm.key] !== false;

                                  return (
                                    <tr
                                      key={perm.key}
                                      style={{
                                        borderBottom: pIdx < cm.permissions.length - 1 ? "1px solid var(--border-glass)" : "none",
                                        backgroundColor: isPermAllowed ? "transparent" : "rgba(0, 0, 0, 0.02)",
                                        transition: "background-color 0.15s ease",
                                      }}
                                    >
                                      <td style={{ padding: "0.85rem 1.5rem" }}>
                                        <div style={{ display: "flex", flexDirection: "column" }}>
                                          <span style={{ fontWeight: 600, color: "var(--text-primary)", fontSize: "0.875rem" }}>
                                            {perm.display_name}
                                          </span>
                                          {perm.description && (
                                            <span style={{ fontSize: "0.75rem", color: "var(--text-secondary)", marginTop: "0.15rem" }}>
                                              {perm.description}
                                            </span>
                                          )}
                                        </div>
                                      </td>
                                      <td style={{ padding: "0.85rem 1.5rem" }}>
                                        <span
                                          style={{
                                            fontSize: "0.75rem",
                                            fontFamily: "var(--font-code)",
                                            color: "var(--text-secondary)",
                                            padding: "0.2rem 0.5rem",
                                            borderRadius: "6px",
                                            backgroundColor: "var(--glass-surface-sunken)",
                                            border: "1px solid var(--border-subtle)",
                                            display: "inline-block",
                                          }}
                                        >
                                          {perm.key}
                                        </span>
                                      </td>
                                      <td style={{ padding: "0.85rem 1.5rem", textAlign: "right" }}>
                                        <div style={{ display: "inline-flex", alignItems: "center", justifyContent: "flex-end", gap: "0.6rem" }}>
                                          <span
                                            style={{
                                              fontSize: "0.72rem",
                                              fontWeight: 700,
                                              padding: "0.2rem 0.55rem",
                                              borderRadius: "6px",
                                              backgroundColor: isPermAllowed ? "rgba(16, 185, 129, 0.12)" : "rgba(148, 163, 184, 0.12)",
                                              color: isPermAllowed ? "var(--status-success, #10b981)" : "var(--text-muted)",
                                              border: isPermAllowed ? "1px solid rgba(16, 185, 129, 0.25)" : "1px solid var(--border-subtle)",
                                              userSelect: "none",
                                            }}
                                          >
                                            {isPermAllowed ? "Granted ✓" : "Restricted ✕"}
                                          </span>
                                          <ToggleSwitch
                                            checked={isPermAllowed}
                                            onChange={() => handleTogglePermissionCeiling(perm.key)}
                                            activeColor="var(--status-success, #10b981)"
                                            size="md"
                                          />
                                        </div>
                                      </td>
                                    </tr>
                                  );
                                })}
                              </tbody>
                            </table>
                          </div>
                        ) : !isModEnabled ? (
                          <div
                            style={{
                              padding: "1rem 1.5rem",
                              color: "var(--text-muted)",
                              fontSize: "0.8125rem",
                              fontStyle: "italic",
                              background: "rgba(0, 0, 0, 0.02)",
                              display: "flex",
                              alignItems: "center",
                              gap: "0.5rem",
                            }}
                          >
                            <span>Module is disabled for this tenant. All associated permissions are automatically revoked.</span>
                          </div>
                        ) : null}
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            {/* Navigation Buttons */}
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                marginTop: "1rem",
                paddingTop: "1.5rem",
                borderTop: "1px solid var(--border-glass)",
                flexWrap: "wrap",
                gap: "1rem",
              }}
            >
              <button
                type="button"
                onClick={() => {
                  if (currentCase) {
                    void onboardingApi
                      .transitionStep(currentCase.id, { target_step: "product_entitlements" })
                      .then((res) => setCurrentCase(res));
                  }
                }}
                style={{
                  padding: "0.75rem 1.5rem",
                  borderRadius: "10px",
                  fontWeight: 600,
                  fontSize: "0.875rem",
                  border: "1px solid var(--border-glass)",
                  background: "var(--glass-surface-sunken)",
                  color: "var(--text-secondary)",
                  cursor: "pointer",
                  transition: "all 0.15s ease",
                }}
              >
                ← Back to Product Entitlements
              </button>
              <button
                type="submit"
                className="btn-gradient"
                disabled={isSubmitting}
                style={{
                  padding: "0.85rem 2rem",
                  borderRadius: "10px",
                  fontWeight: 800,
                  fontSize: "0.9375rem",
                  background: "linear-gradient(135deg, #3867f5 0%, #2952cc 100%)",
                  color: "#ffffff",
                  border: "none",
                  cursor: isSubmitting ? "not-allowed" : "pointer",
                  boxShadow: "0 4px 16px rgba(56, 103, 245, 0.32)",
                  transition: "all 0.15s ease",
                }}
              >
                {isSubmitting ? "Saving Configuration..." : "Continue to Review & Provision →"}
              </button>
            </div>
          </form>
        ) : (
          /* Step 6: Review & Final Confirmation */
          <div
            className="glass-panel"
            style={{
              padding: "2.75rem 3rem",
              borderRadius: "20px",
              border: "1px solid var(--border-glass)",
              backgroundColor: "var(--glass-surface-elevated)",
              boxShadow: "var(--shadow-md)",
              display: "flex",
              flexDirection: "column",
              gap: "2.25rem",
              position: "relative",
              overflow: "hidden",
            }}
          >
            <div
              style={{
                position: "absolute",
                top: 0,
                left: 0,
                right: 0,
                height: "4px",
                background: "linear-gradient(90deg, #3867f5 0%, #8a45f6 50%, #0faf83 100%)",
              }}
            />

            {/* Header */}
            <div>
              <span
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  gap: "0.5rem",
                  padding: "0.3rem 0.85rem",
                  borderRadius: "9999px",
                  fontSize: "0.75rem",
                  fontWeight: 700,
                  letterSpacing: "0.08em",
                  textTransform: "uppercase",
                  backgroundColor: "rgba(16, 185, 129, 0.1)",
                  color: "var(--status-success, #10b981)",
                  border: "1px solid rgba(16, 185, 129, 0.25)",
                  marginBottom: "0.85rem",
                }}
              >
                <span style={{ width: "6px", height: "6px", borderRadius: "50%", background: "var(--status-success, #10b981)" }} />
                Step 06 of 06
              </span>
              <h2
                style={{
                  fontSize: "1.75rem",
                  fontWeight: 800,
                  margin: "0 0 0.5rem 0",
                  letterSpacing: "-0.03em",
                  color: "var(--text-primary)",
                }}
              >
                Step 6: Review & Provision Organization
              </h2>
              <p
                style={{
                  color: "var(--text-secondary)",
                  fontSize: "0.9375rem",
                  margin: 0,
                  lineHeight: 1.6,
                  maxWidth: "850px",
                }}
              >
                Confirm all tenant configuration parameters before executing the atomic provisioning transaction. Once confirmed, tenant databases, administrative credentials, subscriptions, and RBAC policies will be initialized.
              </p>
            </div>

            {/* 6-Dimensional Blueprint Grid */}
            <div>
              <h3
                style={{
                  fontSize: "0.875rem",
                  fontWeight: 700,
                  textTransform: "uppercase",
                  letterSpacing: "0.06em",
                  color: "var(--text-muted)",
                  margin: "0 0 0.85rem 0",
                  display: "flex",
                  alignItems: "center",
                  gap: "0.5rem",
                }}
              >
                <BuildingIcon size={16} style={{ color: "var(--brand-primary, #3867f5)" }} />
                <span>Tenant Partition & Commercial Specifications</span>
              </h3>

              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))",
                  gap: "1rem",
                }}
              >
                {/* 1. Org Entity */}
                <div
                  style={{
                    padding: "1.25rem 1.4rem",
                    borderRadius: "14px",
                    border: "1px solid var(--border-glass)",
                    background: "var(--glass-surface-sunken)",
                    display: "flex",
                    flexDirection: "column",
                    justifyContent: "space-between",
                  }}
                >
                  <span style={{ fontSize: "0.72rem", textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--text-muted)", fontWeight: 700 }}>
                    Organization Entity
                  </span>
                  <div style={{ margin: "0.5rem 0" }}>
                    <div style={{ fontWeight: 800, fontSize: "1.1rem", color: "var(--text-primary)", letterSpacing: "-0.01em" }}>
                      {currentCase?.organization_name}
                    </div>
                    <div style={{ marginTop: "0.25rem" }}>
                      <span
                        style={{
                          fontFamily: "var(--font-code)",
                          fontSize: "0.75rem",
                          fontWeight: 700,
                          padding: "0.15rem 0.5rem",
                          borderRadius: "6px",
                          backgroundColor: "rgba(56, 103, 245, 0.1)",
                          color: "var(--brand-primary, #3867f5)",
                          border: "1px solid rgba(56, 103, 245, 0.2)",
                        }}
                      >
                        {currentCase?.organization_code}
                      </span>
                    </div>
                  </div>
                  <span style={{ fontSize: "0.75rem", color: "var(--text-secondary)" }}>
                    Isolated Tenant Boundary
                  </span>
                </div>

                {/* 2. Admin Credentials */}
                <div
                  style={{
                    padding: "1.25rem 1.4rem",
                    borderRadius: "14px",
                    border: "1px solid var(--border-glass)",
                    background: "var(--glass-surface-sunken)",
                    display: "flex",
                    flexDirection: "column",
                    justifyContent: "space-between",
                  }}
                >
                  <span style={{ fontSize: "0.72rem", textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--text-muted)", fontWeight: 700 }}>
                    Primary Administrator
                  </span>
                  <div style={{ margin: "0.5rem 0" }}>
                    <div style={{ fontWeight: 800, fontSize: "1.05rem", color: "var(--text-primary)", letterSpacing: "-0.01em" }}>
                      {currentCase?.admin_full_name || "Administrator"}
                    </div>
                    <div style={{ fontSize: "0.8125rem", color: "var(--text-secondary)", marginTop: "0.2rem", wordBreak: "break-all" }}>
                      {currentCase?.admin_email}
                    </div>
                  </div>
                  <span style={{ fontSize: "0.75rem", color: "var(--brand-primary, #3867f5)", fontWeight: 600 }}>
                    Superuser & Owner Privileges
                  </span>
                </div>

                {/* 3. Commercial Tier */}
                <div
                  style={{
                    padding: "1.25rem 1.4rem",
                    borderRadius: "14px",
                    border: "1px solid var(--border-glass)",
                    background: "var(--glass-surface-sunken)",
                    display: "flex",
                    flexDirection: "column",
                    justifyContent: "space-between",
                  }}
                >
                  <span style={{ fontSize: "0.72rem", textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--text-muted)", fontWeight: 700 }}>
                    Commercial Subscription
                  </span>
                  <div style={{ margin: "0.5rem 0" }}>
                    <div style={{ fontWeight: 800, fontSize: "1.05rem", color: "var(--text-primary)", letterSpacing: "-0.01em" }}>
                      {currentCase?.plan_name ? `${currentCase.plan_name}` : "Direct Enterprise"}
                    </div>
                    {currentCase?.plan_version_number && (
                      <div style={{ marginTop: "0.2rem" }}>
                        <span style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
                          Version {currentCase.plan_version_number}
                        </span>
                      </div>
                    )}
                  </div>
                  <span style={{ fontSize: "0.75rem", color: "var(--text-secondary)" }}>
                    Automated Billing & Invoicing
                  </span>
                </div>

                {/* 4. Trial / Lifecycle Mode */}
                <div
                  style={{
                    padding: "1.25rem 1.4rem",
                    borderRadius: "14px",
                    border: "1px solid var(--border-glass)",
                    background: "var(--glass-surface-sunken)",
                    display: "flex",
                    flexDirection: "column",
                    justifyContent: "space-between",
                  }}
                >
                  <span style={{ fontSize: "0.72rem", textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--text-muted)", fontWeight: 700 }}>
                    Evaluation Mode
                  </span>
                  <div style={{ margin: "0.5rem 0" }}>
                    <span
                      style={{
                        fontSize: "0.8125rem",
                        fontWeight: 800,
                        padding: "0.3rem 0.75rem",
                        borderRadius: "9999px",
                        display: "inline-flex",
                        alignItems: "center",
                        gap: "0.4rem",
                        backgroundColor: currentCase?.is_trial ? "rgba(245, 158, 11, 0.12)" : "rgba(16, 185, 129, 0.12)",
                        color: currentCase?.is_trial ? "var(--status-warning, #f59e0b)" : "var(--status-success, #10b981)",
                        border: currentCase?.is_trial ? "1px solid rgba(245, 158, 11, 0.25)" : "1px solid rgba(16, 185, 129, 0.25)",
                      }}
                    >
                      <span
                        style={{
                          width: "6px",
                          height: "6px",
                          borderRadius: "50%",
                          background: currentCase?.is_trial ? "var(--status-warning, #f59e0b)" : "var(--status-success, #10b981)",
                        }}
                      />
                      {currentCase?.is_trial ? "14-Day Free Trial" : "Production Direct Active"}
                    </span>
                  </div>
                  <span style={{ fontSize: "0.75rem", color: "var(--text-secondary)" }}>
                    {currentCase?.is_trial ? "Self-expires unless converted" : "Immediate production access"}
                  </span>
                </div>

                {/* 5. Product Coverage */}
                <div
                  style={{
                    padding: "1.25rem 1.4rem",
                    borderRadius: "14px",
                    border: "1px solid var(--border-glass)",
                    background: "var(--glass-surface-sunken)",
                    display: "flex",
                    flexDirection: "column",
                    justifyContent: "space-between",
                  }}
                >
                  <span style={{ fontSize: "0.72rem", textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--text-muted)", fontWeight: 700 }}>
                    Product Entitlements
                  </span>
                  <div style={{ margin: "0.5rem 0" }}>
                    <div style={{ fontWeight: 800, fontSize: "1.375rem", color: "var(--brand-primary, #3867f5)", letterSpacing: "-0.02em" }}>
                      {selectedProducts.length} <span style={{ fontSize: "0.875rem", fontWeight: 600, color: "var(--text-primary)" }}>{selectedProducts.length === 1 ? "Product" : "Products"}</span>
                    </div>
                  </div>
                  <span style={{ fontSize: "0.75rem", color: "var(--text-secondary)" }}>
                    Multi-Tenant Catalog Access
                  </span>
                </div>

                {/* 6. Console Ceilings */}
                <div
                  style={{
                    padding: "1.25rem 1.4rem",
                    borderRadius: "14px",
                    border: "1px solid var(--border-glass)",
                    background: "var(--glass-surface-sunken)",
                    display: "flex",
                    flexDirection: "column",
                    justifyContent: "space-between",
                  }}
                >
                  <span style={{ fontSize: "0.72rem", textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--text-muted)", fontWeight: 700 }}>
                    Policy & Governance
                  </span>
                  <div style={{ margin: "0.5rem 0" }}>
                    <div style={{ fontWeight: 800, fontSize: "1.375rem", color: "var(--status-success, #10b981)", letterSpacing: "-0.02em" }}>
                      {(() => {
                        if (!options?.console_modules) return 0;
                        let count = 0;
                        options.console_modules.forEach((cm) => {
                          cm.permissions?.forEach((p) => {
                            if (featureCeilings.permission_ceilings[p.key] !== false) count++;
                          });
                        });
                        return count;
                      })()} <span style={{ fontSize: "0.875rem", fontWeight: 600, color: "var(--text-primary)" }}>Active Caps</span>
                    </div>
                  </div>
                  <span style={{ fontSize: "0.75rem", color: "var(--text-secondary)" }}>
                    Tenant RBAC Ceilings Configured
                  </span>
                </div>
              </div>
            </div>

            {/* Product Entitlements Showcase */}
            <div
              style={{
                padding: "1.5rem",
                borderRadius: "14px",
                border: "1px solid var(--border-glass)",
                background: "var(--glass-surface-sunken)",
              }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1rem", flexWrap: "wrap", gap: "0.5rem" }}>
                <span style={{ fontSize: "0.8125rem", textTransform: "uppercase", letterSpacing: "0.06em", fontWeight: 800, color: "var(--text-primary)", display: "flex", alignItems: "center", gap: "0.5rem" }}>
                  <LayersIcon size={16} style={{ color: "var(--brand-primary, #3867f5)" }} />
                  <span>Entitled Product Portfolio ({selectedProducts.length})</span>
                </span>
                <span style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
                  Configured in Step 4
                </span>
              </div>

              {selectedProducts.length === 0 ? (
                <div style={{ fontSize: "0.8125rem", color: "var(--text-muted)" }}>No products selected.</div>
              ) : (
                <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: "0.75rem" }}>
                  {selectedProducts.map((p) => {
                    const isLms = p.code?.toLowerCase().includes("lms") || p.name?.toLowerCase().includes("learning");
                    const modCount = p.modules?.length || 0;
                    const disabledModCount = p.modules?.filter((m) => featureCeilings.product_modules[m.id] === false).length || 0;
                    const enabledModCount = modCount - disabledModCount;

                    return (
                      <div
                        key={p.id}
                        style={{
                          padding: "0.85rem 1rem",
                          borderRadius: "10px",
                          backgroundColor: "var(--glass-surface-elevated)",
                          border: "1px solid var(--border-glass)",
                          display: "flex",
                          justifyContent: "space-between",
                          alignItems: "center",
                          gap: "0.75rem",
                        }}
                      >
                        <div>
                          <div style={{ display: "flex", alignItems: "center", gap: "0.45rem" }}>
                            <span style={{ fontWeight: 700, fontSize: "0.875rem", color: "var(--text-primary)" }}>
                              {p.name}
                            </span>
                            <span
                              style={{
                                fontSize: "0.6875rem",
                                padding: "0.1rem 0.4rem",
                                borderRadius: "4px",
                                backgroundColor: "rgba(255, 255, 255, 0.06)",
                                fontFamily: "var(--font-code)",
                                color: "var(--text-secondary)",
                              }}
                            >
                              {p.code}
                            </span>
                          </div>
                          <span style={{ fontSize: "0.72rem", color: "var(--text-muted)", display: "block", marginTop: "0.15rem" }}>
                            {modCount === 0 ? "Standard package" : `${enabledModCount} of ${modCount} modules active`}
                          </span>
                        </div>

                        {isLms ? (
                          <span
                            style={{
                              fontSize: "0.6875rem",
                              padding: "0.2rem 0.55rem",
                              borderRadius: "9999px",
                              backgroundColor: "rgba(56, 103, 245, 0.15)",
                              color: "var(--brand-primary, #3867f5)",
                              fontWeight: 700,
                              border: "1px solid rgba(56, 103, 245, 0.25)",
                              whiteSpace: "nowrap",
                            }}
                          >
                            Tenant Console
                          </span>
                        ) : (
                          <span
                            style={{
                              fontSize: "0.6875rem",
                              padding: "0.2rem 0.55rem",
                              borderRadius: "9999px",
                              backgroundColor: "rgba(16, 185, 129, 0.12)",
                              color: "var(--status-success, #10b981)",
                              fontWeight: 700,
                              whiteSpace: "nowrap",
                            }}
                          >
                            Entitled ✓
                          </span>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>

            {/* Tenant Admin Console Policies & Ceilings Matrix */}
            {options?.console_modules && options.console_modules.length > 0 && (
              <div
                style={{
                  padding: "1.5rem",
                  borderRadius: "14px",
                  border: "1px solid var(--border-glass)",
                  background: "var(--glass-surface-sunken)",
                }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1rem", flexWrap: "wrap", gap: "0.5rem" }}>
                  <span style={{ fontSize: "0.8125rem", textTransform: "uppercase", letterSpacing: "0.06em", fontWeight: 800, color: "var(--text-primary)", display: "flex", alignItems: "center", gap: "0.5rem" }}>
                    <ShieldCheckIcon size={16} style={{ color: "var(--brand-primary, #3867f5)" }} />
                    <span>Tenant Console Module & Permission Policies</span>
                  </span>
                  <span style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
                    Configured in Step 5
                  </span>
                </div>

                <div style={{ display: "flex", flexWrap: "wrap", gap: "0.6rem" }}>
                  {options.console_modules.map((cm) => {
                    const isModEnabled = cm.is_core || featureCeilings.module_policies[cm.key] !== false;
                    const activePermCount = cm.permissions?.filter((p) => featureCeilings.permission_ceilings[p.key] !== false).length || 0;
                    const totalPermCount = cm.permissions?.length || 0;

                    return (
                      <div
                        key={cm.key}
                        style={{
                          padding: "0.5rem 0.85rem",
                          borderRadius: "8px",
                          backgroundColor: isModEnabled ? "var(--glass-surface-elevated)" : "rgba(0, 0, 0, 0.05)",
                          border: isModEnabled ? "1px solid var(--border-glass)" : "1px solid var(--border-subtle)",
                          display: "inline-flex",
                          alignItems: "center",
                          gap: "0.5rem",
                          opacity: isModEnabled ? 1 : 0.6,
                        }}
                      >
                        <span style={{ fontWeight: 700, fontSize: "0.8125rem", color: isModEnabled ? "var(--text-primary)" : "var(--text-muted)" }}>
                          {cm.display_name}
                        </span>
                        {cm.is_core ? (
                          <span style={{ fontSize: "0.65rem", padding: "0.1rem 0.4rem", borderRadius: "9999px", background: "rgba(56, 103, 245, 0.12)", color: "var(--brand-primary, #3867f5)", fontWeight: 700 }}>
                            Core
                          </span>
                        ) : isModEnabled ? (
                          <span style={{ fontSize: "0.65rem", padding: "0.1rem 0.4rem", borderRadius: "9999px", background: "rgba(16, 185, 129, 0.12)", color: "var(--status-success, #10b981)", fontWeight: 700 }}>
                            {activePermCount}/{totalPermCount} perms
                          </span>
                        ) : (
                          <span style={{ fontSize: "0.65rem", padding: "0.1rem 0.4rem", borderRadius: "9999px", background: "rgba(148, 163, 184, 0.15)", color: "var(--text-muted)", fontWeight: 700 }}>
                            Disabled
                          </span>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            {/* Atomic Provisioning Guarantee Banner */}
            <div
              style={{
                padding: "1.25rem 1.5rem",
                borderRadius: "14px",
                border: "1px solid rgba(56, 103, 245, 0.25)",
                background: "linear-gradient(135deg, rgba(56, 103, 245, 0.06) 0%, rgba(16, 185, 129, 0.06) 100%)",
                display: "flex",
                alignItems: "center",
                gap: "1rem",
              }}
            >
              <div
                style={{
                  width: "42px",
                  height: "42px",
                  borderRadius: "10px",
                  background: "linear-gradient(135deg, var(--brand-primary, #3867f5) 0%, #0faf83 100%)",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  color: "#ffffff",
                  flexShrink: 0,
                  boxShadow: "0 4px 12px rgba(56, 103, 245, 0.3)",
                }}
              >
                <ShieldCheckIcon size={22} />
              </div>
              <div>
                <span style={{ fontSize: "0.875rem", fontWeight: 800, color: "var(--text-primary)", display: "block", letterSpacing: "-0.01em" }}>
                  Atomic Provisioning Protocol & Database Isolation
                </span>
                <p style={{ margin: "0.2rem 0 0 0", fontSize: "0.8125rem", color: "var(--text-secondary)", lineHeight: 1.45 }}>
                  Submitting this action initiates an atomic database transaction. The isolated tenant partition is stamped, administrator auth credentials generated, product subscriptions activated, and role ceilings committed.
                </p>
              </div>
            </div>

            {/* Navigation & Execution Bar */}
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                marginTop: "0.5rem",
                paddingTop: "1.5rem",
                borderTop: "1px solid var(--border-glass)",
                flexWrap: "wrap",
                gap: "1rem",
              }}
            >
              <button
                type="button"
                onClick={() => {
                  if (currentCase) {
                    void onboardingApi
                      .transitionStep(currentCase.id, { target_step: "feature_ceilings" })
                      .then((res) => setCurrentCase(res));
                  }
                }}
                style={{
                  padding: "0.75rem 1.5rem",
                  borderRadius: "10px",
                  fontWeight: 600,
                  fontSize: "0.875rem",
                  border: "1px solid var(--border-glass)",
                  background: "var(--glass-surface-sunken)",
                  color: "var(--text-secondary)",
                  cursor: "pointer",
                  transition: "all 0.15s ease",
                }}
              >
                ← Back to Console Feature Ceilings
              </button>
              <button
                type="button"
                className="btn-gradient"
                onClick={handleFinalProvision}
                disabled={isSubmitting}
                style={{
                  padding: "0.9rem 2.25rem",
                  borderRadius: "12px",
                  fontWeight: 800,
                  fontSize: "0.95rem",
                  background: "linear-gradient(135deg, #3867f5 0%, #0faf83 100%)",
                  color: "#ffffff",
                  border: "none",
                  cursor: isSubmitting ? "not-allowed" : "pointer",
                  boxShadow: "0 4px 20px rgba(56, 103, 245, 0.35)",
                  transition: "all 0.15s ease",
                }}
              >
                {isSubmitting ? "Provisioning Organization..." : "Execute & Complete Onboarding ✓"}
              </button>
            </div>
          </div>
        )}
      </div>
    )}
  </div>
</AppShell>
  );
};
