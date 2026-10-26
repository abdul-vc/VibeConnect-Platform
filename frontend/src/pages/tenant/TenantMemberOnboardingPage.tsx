/**
 * Tenant Member Onboarding Wizard Page.
 *
 * Dedicated, multi-step core wizard experience for Tenant Admins to onboard new members:
 * 1. Member Details (Full Name, Email address, Tenant Context)
 * 2. Role Configuration (Standard Member vs Existing Role vs Create Custom Role)
 * 3. Product Access (Dynamic entitled products with seat capacity)
 * 4. Console Feature Access (Dynamic product modules / feature toggles)
 * 5. Review & Provision (Consolidated summary, atomic creation & invitation link)
 */

import React, { useCallback, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { assignmentsApi } from "../../api/assignments.ts";
import { invitationsApi } from "../../api/invitations.ts";
import { rolesApi } from "../../api/roles.ts";
import type {
  AccessCatalogResponse,
  RoleItem,
  SelectorModuleItem,
  SelectorProductItem,
} from "../../api/types.ts";
import { AppShell } from "../../components/AppShell.tsx";
import {
  AlertCircleIcon,
  BoxIcon,
  BuildingIcon,
  CheckCircleIcon,
  LayersIcon,
  MailIcon,
  PlusIcon,
  RotateCcwIcon,
  ShieldCheckIcon,
  UserIcon,
} from "../../components/Icons.tsx";
import { LoadingSpinner } from "../../components/LoadingSpinner.tsx";
import { useAuth } from "../../context/AuthContext.tsx";

type WizardStep = "details" | "role" | "products" | "features" | "review";

const STEPS: { key: WizardStep; label: string; icon: React.ReactNode }[] = [
  { key: "details", label: "Member Details", icon: <UserIcon size={16} /> },
  { key: "role", label: "Role & Permissions", icon: <ShieldCheckIcon size={16} /> },
  { key: "products", label: "Product Access", icon: <BoxIcon size={16} /> },
  { key: "features", label: "Console Features", icon: <LayersIcon size={16} /> },
  { key: "review", label: "Review & Provision", icon: <CheckCircleIcon size={16} /> },
];

export const TenantMemberOnboardingPage: React.FC = () => {
  const { user } = useAuth();
  const navigate = useNavigate();

  const activeTenant = user?.active_context?.organization;
  const currentOrgId = activeTenant?.id;

  // Wizard Navigation
  const [currentStep, setCurrentStep] = useState<WizardStep>("details");
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  const [generalError, setGeneralError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  // Success / Provisioning State
  const [isProvisioned, setIsProvisioned] = useState<boolean>(false);
  const [activationUrl, setActivationUrl] = useState<string | null>(null);
  const [copiedLink, setCopiedLink] = useState<boolean>(false);

  // Step 1: Member Identity
  const [fullName, setFullName] = useState<string>("");
  const [email, setEmail] = useState<string>("");

  // Step 2: Role Configuration
  // "standard" | "existing" | "custom"
  const [roleMode, setRoleMode] = useState<"standard" | "existing" | "custom">("standard");
  const [availableRoles, setAvailableRoles] = useState<readonly RoleItem[]>([]);
  const [selectedRoleId, setSelectedRoleId] = useState<string>("");
  const [accessCatalog, setAccessCatalog] = useState<AccessCatalogResponse | null>(null);
  const [isLoadingRoles, setIsLoadingRoles] = useState<boolean>(false);

  // Sub-form for creating a new custom role
  const [newRoleName, setNewRoleName] = useState<string>("");
  const [newRoleCode, setNewRoleCode] = useState<string>("");
  const [newRoleDesc, setNewRoleDesc] = useState<string>("");
  const [newRolePermissions, setNewRolePermissions] = useState<string[]>([]);
  const [isCreatingRole, setIsCreatingRole] = useState<boolean>(false);
  const [roleCreationSuccess, setRoleCreationSuccess] = useState<string | null>(null);

  // Step 3: Product Access
  const [entitledProducts, setEntitledProducts] = useState<readonly SelectorProductItem[]>([]);
  const [selectedProductIds, setSelectedProductIds] = useState<string[]>([]);
  const [isLoadingProducts, setIsLoadingProducts] = useState<boolean>(false);
  const [lmsConsole, setLmsConsole] = useState<"normal_user_console" | "tenant_console">("normal_user_console");

  const isAdministrativeMember = roleMode !== "standard";

  // Step 4: Console Feature Access
  // Map of productId -> list of SelectorModuleItem
  const [productModulesMap, setProductModulesMap] = useState<Record<string, readonly SelectorModuleItem[]>>({});
  const [selectedModuleIds, setSelectedModuleIds] = useState<string[]>([]);
  const [isLoadingModules, setIsLoadingModules] = useState<boolean>(false);

  // ---------------------------------------------------------------------------
  // Data Loaders
  // ---------------------------------------------------------------------------

  // Load Roles and Access Catalog
  const loadRolesAndCatalog = useCallback(async () => {
    setIsLoadingRoles(true);
    try {
      const [rolesRes, catalogRes] = await Promise.all([
        rolesApi.listRoles({ page_size: 100 }),
        rolesApi.getAccessCatalog().catch(() => null),
      ]);
      setAvailableRoles(rolesRes.results || []);
      if (catalogRes) {
        setAccessCatalog(catalogRes);
      }
    } catch (err: unknown) {
      setGeneralError(err instanceof Error ? err.message : "Failed to load roles.");
    } finally {
      setIsLoadingRoles(false);
    }
  }, []);

  // Load Entitled Products
  const loadEntitledProducts = useCallback(async () => {
    setIsLoadingProducts(true);
    try {
      const products = await assignmentsApi.getSelectorProducts();
      setEntitledProducts(products || []);
    } catch (err: unknown) {
      setGeneralError(err instanceof Error ? err.message : "Failed to load entitled products.");
    } finally {
      setIsLoadingProducts(false);
    }
  }, []);

  // Load Modules for Selected Products
  const loadModulesForSelectedProducts = useCallback(async (productIds: string[]) => {
    if (productIds.length === 0) {
      setProductModulesMap({});
      return;
    }
    setIsLoadingModules(true);
    try {
      const results = await Promise.all(
        productIds.map(async (pid) => {
          try {
            const modules = await assignmentsApi.getSelectorModules(pid);
            return { productId: pid, modules };
          } catch {
            return { productId: pid, modules: [] as SelectorModuleItem[] };
          }
        })
      );
      const newMap: Record<string, readonly SelectorModuleItem[]> = {};
      results.forEach((r) => {
        newMap[r.productId] = r.modules;
      });
      setProductModulesMap(newMap);

      // By default, auto-enable all entitled modules for newly selected products
      const allEntitledModIds: string[] = [];
      results.forEach((r) => {
        r.modules.forEach((m) => {
          if (m.is_entitled) {
            allEntitledModIds.push(m.id);
          }
        });
      });
      setSelectedModuleIds((prev) => Array.from(new Set([...prev, ...allEntitledModIds])));
    } finally {
      setIsLoadingModules(false);
    }
  }, []);

  useEffect(() => {
    void loadRolesAndCatalog();
    void loadEntitledProducts();
  }, [loadRolesAndCatalog, loadEntitledProducts]);

  // When step changes to features, fetch modules if not already cached
  useEffect(() => {
    if (currentStep === "features") {
      void loadModulesForSelectedProducts(selectedProductIds);
    }
  }, [currentStep, selectedProductIds, loadModulesForSelectedProducts]);

  // ---------------------------------------------------------------------------
  // Step Navigation & Validation
  // ---------------------------------------------------------------------------

  const validateStep1 = (): boolean => {
    const errors: Record<string, string> = {};
    if (!fullName.trim()) {
      errors.fullName = "Member full name is required.";
    }
    if (!email.trim()) {
      errors.email = "Member email address is required.";
    } else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim())) {
      errors.email = "Please enter a valid email address.";
    }
    setFieldErrors(errors);
    return Object.keys(errors).length === 0;
  };

  const handleNextFromDetails = (e: React.FormEvent) => {
    e.preventDefault();
    if (!validateStep1()) return;
    setGeneralError(null);
    setCurrentStep("role");
  };

  const handleCreateCustomRole = async () => {
    if (!newRoleName.trim()) {
      setFieldErrors((prev) => ({ ...prev, newRoleName: "Role name is required." }));
      return;
    }
    if (!newRoleCode.trim()) {
      setFieldErrors((prev) => ({ ...prev, newRoleCode: "Role code is required." }));
      return;
    }

    setIsCreatingRole(true);
    setFieldErrors({});
    setGeneralError(null);
    try {
      const created = await rolesApi.createRole({
        name: newRoleName.trim(),
        code: newRoleCode.trim().toLowerCase().replace(/\s+/g, "_"),
        description: newRoleDesc.trim(),
        permission_keys: newRolePermissions,
      });

      // Refresh roles list and select the created role
      await loadRolesAndCatalog();
      setSelectedRoleId(created.id);
      setRoleMode("existing");
      setRoleCreationSuccess(`Custom role "${created.name}" created and selected!`);
      // Reset form
      setNewRoleName("");
      setNewRoleCode("");
      setNewRoleDesc("");
      setNewRolePermissions([]);
    } catch (err: unknown) {
      setGeneralError(err instanceof Error ? err.message : "Failed to create custom role.");
    } finally {
      setIsCreatingRole(false);
    }
  };

  const handleNextFromRole = (e: React.FormEvent) => {
    e.preventDefault();
    setGeneralError(null);
    if (roleMode === "existing" && !selectedRoleId) {
      setFieldErrors({ selectedRole: "Please select an existing role or choose Standard Member." });
      return;
    }
    if (roleMode === "custom") {
      setFieldErrors({ customRole: "Please create the custom role before proceeding, or switch to Standard Member." });
      return;
    }
    setFieldErrors({});
    if (roleMode === "standard" && lmsConsole === "tenant_console") {
      setLmsConsole("normal_user_console");
    }
    setCurrentStep("products");
  };

  const handleToggleProduct = (productId: string) => {
    setSelectedProductIds((prev) => {
      if (prev.includes(productId)) {
        return prev.filter((id) => id !== productId);
      } else {
        return [...prev, productId];
      }
    });
  };

  const handleNextFromProducts = (e: React.FormEvent) => {
    e.preventDefault();
    setGeneralError(null);
    setCurrentStep("features");
  };

  const handleToggleModule = (moduleId: string) => {
    setSelectedModuleIds((prev) => {
      if (prev.includes(moduleId)) {
        return prev.filter((id) => id !== moduleId);
      } else {
        return [...prev, moduleId];
      }
    });
  };

  const handleNextFromFeatures = (e: React.FormEvent) => {
    e.preventDefault();
    setGeneralError(null);
    setCurrentStep("review");
  };

  // ---------------------------------------------------------------------------
  // Step 5: Provision Member
  // ---------------------------------------------------------------------------

  const handleProvisionMember = async () => {
    if (!currentOrgId) {
      setGeneralError("No active tenant context found. Please refresh and select a tenant.");
      return;
    }

    setIsSubmitting(true);
    setGeneralError(null);

    const membershipType = roleMode === "standard" ? "member" : "tenant_admin";
    const roleIdToAssign = roleMode === "existing" && selectedRoleId ? selectedRoleId : null;

    try {
      const result = await invitationsApi.issue({
        organization_id: currentOrgId,
        email: email.trim().toLowerCase(),
        full_name: fullName.trim(),
        membership_type: membershipType,
        role_id: roleIdToAssign,
        product_ids: selectedProductIds,
        module_ids: selectedModuleIds,
        lms_console: lmsConsole,
      });

      setIsProvisioned(true);
      setActivationUrl(result.activation_url || null);
    } catch (err: unknown) {
      setGeneralError(err instanceof Error ? err.message : "Failed to provision member.");
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleResetWizard = () => {
    setCurrentStep("details");
    setIsProvisioned(false);
    setActivationUrl(null);
    setCopiedLink(false);
    setFullName("");
    setEmail("");
    setRoleMode("standard");
    setSelectedRoleId("");
    setSelectedProductIds([]);
    setSelectedModuleIds([]);
    setLmsConsole("normal_user_console");
    setGeneralError(null);
    setFieldErrors({});
    setRoleCreationSuccess(null);
  };

  const handleCopyLink = () => {
    if (!activationUrl) return;
    void navigator.clipboard.writeText(activationUrl);
    setCopiedLink(true);
    setTimeout(() => setCopiedLink(false), 2500);
  };

  const selectedRole = availableRoles.find((r) => r.id === selectedRoleId);
  const selectedProducts = entitledProducts.filter((p) => selectedProductIds.includes(p.id));

  // ---------------------------------------------------------------------------
  // Render Success Confirmation
  // ---------------------------------------------------------------------------

  if (isProvisioned) {
    return (
      <AppShell>
        <div style={{ maxWidth: "760px", margin: "2rem auto", padding: "0 1.25rem" }}>
          {/* Breadcrumb */}
          <nav style={{ display: "flex", alignItems: "center", gap: "0.5rem", fontSize: "0.8125rem", color: "var(--text-muted)", marginBottom: "1.25rem" }}>
            <Link to="/tenant/dashboard" style={{ color: "var(--text-muted)", textDecoration: "none" }}>Tenant Console</Link>
            <span>/</span>
            <Link to="/tenant/users" style={{ color: "var(--text-muted)", textDecoration: "none" }}>Members</Link>
            <span>/</span>
            <span style={{ color: "var(--text-primary)", fontWeight: 600 }}>Provisioning Success</span>
          </nav>

          <div
            className="glass-panel"
            style={{
              padding: "3rem 2.5rem",
              textAlign: "center",
              borderRadius: "16px",
              border: "1px solid var(--status-success-border)",
              background: "linear-gradient(180deg, var(--status-success-bg) 0%, rgba(255, 255, 255, 0.01) 100%)",
              boxShadow: "var(--shadow-lg)",
            }}
          >
            <div
              style={{
                width: "72px",
                height: "72px",
                borderRadius: "50%",
                backgroundColor: "var(--status-success-bg)",
                border: "2px solid var(--status-success-border)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                margin: "0 auto 1.5rem auto",
                boxShadow: "0 0 24px rgba(16, 185, 129, 0.25)",
              }}
            >
              <CheckCircleIcon size={40} color="var(--status-success)" />
            </div>

            <span
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: "0.35rem",
                padding: "0.25rem 0.75rem",
                borderRadius: "9999px",
                fontSize: "0.75rem",
                fontWeight: 700,
                letterSpacing: "0.06em",
                textTransform: "uppercase",
                backgroundColor: "var(--status-success-bg)",
                color: "var(--status-success)",
                marginBottom: "0.75rem",
              }}
            >
              Atomic Provisioning Complete
            </span>

            <h1
              style={{
                fontSize: "1.875rem",
                fontWeight: 800,
                letterSpacing: "-0.03em",
                margin: "0 0 0.75rem 0",
                color: "var(--text-primary)",
              }}
            >
              Member Successfully Onboarded!
            </h1>
            <p
              style={{
                color: "var(--text-secondary)",
                fontSize: "0.9375rem",
                lineHeight: 1.6,
                maxWidth: "560px",
                margin: "0 auto 2rem auto",
              }}
            >
              <strong style={{ color: "var(--text-primary)" }}>{fullName}</strong> ({email}) has been provisioned under{" "}
              <strong style={{ color: "var(--text-primary)" }}>{activeTenant?.name || "your organization"}</strong> with configured role assignments, product access, and security entitlements.
            </p>

            {activationUrl ? (
              <div
                style={{
                  padding: "1.5rem",
                  borderRadius: "12px",
                  backgroundColor: "var(--glass-surface-elevated)",
                  border: "1px solid var(--border-glass)",
                  boxShadow: "var(--shadow-sm)",
                  marginBottom: "2.25rem",
                  textAlign: "left",
                }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.75rem" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                    <span style={{ fontSize: "0.75rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--text-muted)" }}>
                      Account Activation & Invitation Link
                    </span>
                    <span className="badge badge-success" style={{ fontSize: "0.6875rem" }}>Single-Use</span>
                  </div>
                  <button
                    type="button"
                    onClick={handleCopyLink}
                    className="btn btn-secondary"
                    style={{
                      fontSize: "0.78125rem",
                      padding: "0.35rem 0.85rem",
                      minHeight: "30px",
                      display: "inline-flex",
                      alignItems: "center",
                      gap: "0.35rem",
                    }}
                  >
                    {copiedLink ? "Copied! ✓" : "Copy Link"}
                  </button>
                </div>
                <div
                  style={{
                    padding: "0.75rem 1rem",
                    borderRadius: "8px",
                    backgroundColor: "rgba(0, 0, 0, 0.35)",
                    border: "1px solid var(--border-subtle)",
                    fontFamily: "var(--font-code, monospace)",
                    fontSize: "0.8125rem",
                    color: "var(--brand-primary)",
                    wordBreak: "break-all",
                    lineHeight: 1.5,
                  }}
                >
                  {activationUrl}
                </div>
                <p style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginTop: "0.75rem", marginBottom: 0, display: "flex", alignItems: "center", gap: "0.4rem" }}>
                  <span>🔒</span> This cryptographically signed invitation link is valid for 7 days. The member can use it to set their password and activate their account.
                </p>
              </div>
            ) : null}

            <div style={{ display: "flex", gap: "0.875rem", justifyContent: "center", flexWrap: "wrap" }}>
              <button
                type="button"
                onClick={handleResetWizard}
                className="btn btn-secondary"
                style={{ padding: "0.625rem 1.25rem", minHeight: "40px" }}
              >
                <PlusIcon size={16} /> Onboard Another Member
              </button>
              <button
                type="button"
                onClick={() => navigate("/tenant/users")}
                className="btn btn-primary"
                style={{ padding: "0.625rem 1.25rem", minHeight: "40px" }}
              >
                <UserIcon size={16} /> View Organization Members
              </button>
            </div>
          </div>
        </div>
      </AppShell>
    );
  }

  // ---------------------------------------------------------------------------
  // Wizard Main Render
  // ---------------------------------------------------------------------------

  const stepOrder: WizardStep[] = ["details", "role", "products", "features", "review"];
  const currentStepIdx = stepOrder.indexOf(currentStep);

  return (
    <AppShell>
      <div style={{ maxWidth: "1180px", margin: "1.5rem auto", padding: "0 1.25rem 3rem 1.25rem" }}>
        {/* Breadcrumb Navigation */}
        <nav style={{ display: "flex", alignItems: "center", gap: "0.5rem", fontSize: "0.8125rem", color: "var(--text-muted)", marginBottom: "1rem" }}>
          <Link to="/tenant/dashboard" style={{ color: "var(--text-muted)", textDecoration: "none" }}>Tenant Admin</Link>
          <span>/</span>
          <Link to="/tenant/users" style={{ color: "var(--text-muted)", textDecoration: "none" }}>Members</Link>
          <span>/</span>
          <span style={{ color: "var(--text-primary)", fontWeight: 600 }}>Onboard New Member</span>
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
                <UserIcon size={20} />
              </div>
              <h1 style={{ fontSize: "1.625rem", fontWeight: 800, margin: 0, letterSpacing: "-0.025em", color: "var(--text-primary)" }}>
                Member Onboarding Wizard
              </h1>
            </div>
            <p style={{ color: "var(--text-muted)", fontSize: "0.875rem", margin: 0, lineHeight: 1.5 }}>
              Provision member identity, role configuration, product entitlements, and feature permissions in a unified workflow.
            </p>
          </div>
          <Link
            to="/tenant/users"
            className="btn btn-secondary"
            style={{ fontSize: "0.8125rem", textDecoration: "none", padding: "0.5rem 1rem", minHeight: "36px" }}
          >
            ← Back to Members
          </Link>
        </div>

        {/* Global Error Banner */}
        {generalError && (
          <div
            className="glass-panel"
            style={{
              padding: "1rem 1.25rem",
              borderRadius: "10px",
              marginBottom: "1.75rem",
              border: "1px solid var(--status-danger-border)",
              backgroundColor: "var(--status-danger-bg)",
              display: "flex",
              alignItems: "center",
              gap: "0.75rem",
              color: "var(--status-danger)",
              boxShadow: "var(--shadow-sm)",
            }}
          >
            <AlertCircleIcon size={20} />
            <span style={{ fontSize: "0.875rem", fontWeight: 500 }}>{generalError}</span>
          </div>
        )}

        {/* Connected Step Navigation Rail */}
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
              const isActive = currentStep === step.key;
              const isCompleted = currentStepIdx > idx;
              const isClickable = isCompleted;

              return (
                <React.Fragment key={step.key}>
                  {/* Step Node */}
                  <div
                    onClick={() => isClickable && setCurrentStep(step.key)}
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
                        width: "36px",
                        height: "36px",
                        borderRadius: "50%",
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                        fontSize: "0.8125rem",
                        fontWeight: 700,
                        backgroundColor: isActive
                          ? "var(--brand-primary)"
                          : isCompleted
                          ? "var(--status-success)"
                          : "var(--glass-surface-sunken)",
                        color: isActive || isCompleted ? "#ffffff" : "var(--text-muted)",
                        border: isActive
                          ? "2px solid #ffffff"
                          : isCompleted
                          ? "none"
                          : "1px solid var(--border-glass)",
                        boxShadow: isActive
                          ? "0 0 0 4px var(--brand-primary-light), 0 4px 12px rgba(99, 102, 241, 0.35)"
                          : isCompleted
                          ? "0 2px 8px rgba(16, 185, 129, 0.3)"
                          : "none",
                        transition: "all 0.2s ease",
                      }}
                    >
                      {isCompleted ? "✓" : idx + 1}
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
                            : isCompleted
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
                            : isCompleted
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
                        backgroundColor: isCompleted
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

        {/* =================================================================== */}
        {/* STEP 1: MEMBER DETAILS                                              */}
        {/* =================================================================== */}
        {currentStep === "details" && (
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))",
              gap: "1.75rem",
              alignItems: "start",
            }}
          >
            {/* Form Column */}
            <form
              onSubmit={handleNextFromDetails}
              className="glass-panel"
              style={{
                padding: "2.25rem",
                borderRadius: "16px",
                border: "1px solid var(--border-glass)",
                backgroundColor: "var(--glass-surface-elevated)",
                boxShadow: "var(--shadow-md)",
                display: "flex",
                flexDirection: "column",
                gap: "1.75rem",
              }}
            >
              {/* Step Header */}
              <div>
                <span
                  style={{
                    display: "inline-block",
                    padding: "0.2rem 0.6rem",
                    borderRadius: "6px",
                    fontSize: "0.6875rem",
                    fontWeight: 700,
                    letterSpacing: "0.06em",
                    textTransform: "uppercase",
                    backgroundColor: "var(--brand-primary-light)",
                    color: "var(--brand-primary)",
                    marginBottom: "0.5rem",
                  }}
                >
                  Step 01 of 05
                </span>
                <h2 style={{ fontSize: "1.375rem", fontWeight: 800, margin: "0 0 0.35rem 0", letterSpacing: "-0.02em", color: "var(--text-primary)" }}>
                  Step 1: Member Identity & Details
                </h2>
                <p style={{ color: "var(--text-muted)", fontSize: "0.875rem", margin: 0, lineHeight: 1.5 }}>
                  Enter the identity details for the new member. The account will be strictly isolated to your organization.
                </p>
              </div>

              {/* Target Organization Context Card */}
              <div
                style={{
                  padding: "1rem 1.25rem",
                  borderRadius: "12px",
                  backgroundColor: "var(--surface-soft-lavender)",
                  border: "1px solid rgba(138, 69, 246, 0.2)",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  flexWrap: "wrap",
                  gap: "1rem",
                }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: "0.85rem" }}>
                  <div
                    style={{
                      width: "40px",
                      height: "40px",
                      borderRadius: "10px",
                      backgroundColor: "#ffffff",
                      border: "1px solid var(--border-glass)",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      color: "var(--brand-primary)",
                      flexShrink: 0,
                    }}
                  >
                    <BuildingIcon size={20} />
                  </div>
                  <div>
                    <div style={{ fontSize: "0.6875rem", textTransform: "uppercase", fontWeight: 700, color: "var(--brand-primary)", letterSpacing: "0.06em" }}>
                      Target Organization
                    </div>
                    <div style={{ fontSize: "0.9375rem", fontWeight: 700, color: "var(--text-primary)" }}>
                      {activeTenant?.name || "Enterprise"}
                    </div>
                  </div>
                </div>

                <div
                  style={{
                    display: "inline-flex",
                    alignItems: "center",
                    gap: "0.45rem",
                    padding: "0.25rem 0.65rem",
                    borderRadius: "9999px",
                    fontSize: "0.75rem",
                    fontWeight: 600,
                    backgroundColor: "var(--status-success-bg)",
                    border: "1px solid var(--status-success-border)",
                    color: "var(--status-success)",
                  }}
                >
                  <span className="badge-dot" style={{ width: "6px", height: "6px", borderRadius: "50%", backgroundColor: "var(--status-success)" }} />
                  Tenant Isolated
                </div>
              </div>

              {/* Form Fields Grid */}
              <div style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>
                {/* Full Name */}
                <div>
                  <label style={{ display: "block", fontSize: "0.8125rem", fontWeight: 600, marginBottom: "0.45rem", color: "var(--text-primary)" }}>
                    Full Name <span style={{ color: "var(--status-danger)" }}>*</span>
                  </label>
                  <div style={{ position: "relative", display: "flex", alignItems: "center" }}>
                    <span className="input-icon-left">
                      <UserIcon size={16} />
                    </span>
                    <input
                      type="text"
                      placeholder="e.g. Jane Doe"
                      value={fullName}
                      onChange={(e) => setFullName(e.target.value)}
                      className={`form-input input-text form-input-with-icon-left ${fieldErrors.fullName ? "form-input-error" : ""}`}
                      style={{ minHeight: "42px", fontSize: "0.875rem", borderRadius: "8px" }}
                    />
                  </div>
                  {fieldErrors.fullName ? (
                    <span className="form-error" style={{ marginTop: "0.35rem" }}>
                      <AlertCircleIcon size={13} /> {fieldErrors.fullName}
                    </span>
                  ) : (
                    <span style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginTop: "0.35rem", display: "block" }}>
                      The legal or display name for this member.
                    </span>
                  )}
                </div>

                {/* Email Address */}
                <div>
                  <label style={{ display: "block", fontSize: "0.8125rem", fontWeight: 600, marginBottom: "0.45rem", color: "var(--text-primary)" }}>
                    Email Address <span style={{ color: "var(--status-danger)" }}>*</span>
                  </label>
                  <div style={{ position: "relative", display: "flex", alignItems: "center" }}>
                    <span className="input-icon-left">
                      <MailIcon size={16} />
                    </span>
                    <input
                      type="email"
                      placeholder="e.g. jane.doe@company.com"
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      className={`form-input input-text form-input-with-icon-left ${fieldErrors.email ? "form-input-error" : ""}`}
                      style={{ minHeight: "42px", fontSize: "0.875rem", borderRadius: "8px" }}
                    />
                  </div>
                  {fieldErrors.email ? (
                    <span className="form-error" style={{ marginTop: "0.35rem" }}>
                      <AlertCircleIcon size={13} /> {fieldErrors.email}
                    </span>
                  ) : (
                    <span style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginTop: "0.35rem", display: "block" }}>
                      Invitation link and account activations are routed here.
                    </span>
                  )}
                </div>
              </div>

              {/* Enterprise Security Callout */}
              <div
                style={{
                  padding: "0.85rem 1rem",
                  borderRadius: "10px",
                  backgroundColor: "var(--glass-surface-sunken)",
                  border: "1px solid var(--border-subtle)",
                  display: "flex",
                  alignItems: "flex-start",
                  gap: "0.75rem",
                  fontSize: "0.8125rem",
                  color: "var(--text-secondary)",
                  lineHeight: 1.5,
                }}
              >
                <div
                  style={{
                    width: "24px",
                    height: "24px",
                    borderRadius: "6px",
                    backgroundColor: "var(--brand-primary-light)",
                    color: "var(--brand-primary)",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    flexShrink: 0,
                    marginTop: "0.1rem",
                  }}
                >
                  <ShieldCheckIcon size={14} />
                </div>
                <div>
                  <strong style={{ color: "var(--text-primary)", display: "block" }}>
                    Atomic Zero-Trust Provisioning
                  </strong>
                  Account creation is atomic and deferred until final confirmation in Step 5.
                </div>
              </div>

              {/* Bottom Actions */}
              <div style={{ display: "flex", justifyContent: "flex-end", paddingTop: "0.5rem" }}>
                <button
                  type="submit"
                  className="btn-gradient"
                  style={{
                    padding: "0.625rem 1.5rem",
                    minHeight: "42px",
                    fontSize: "0.875rem",
                    fontWeight: 600,
                    borderRadius: "8px",
                    color: "#ffffff",
                    border: "none",
                    cursor: "pointer",
                    boxShadow: "0 4px 14px rgba(56, 103, 245, 0.28)",
                  }}
                >
                  Continue to Role Configuration →
                </button>
              </div>
            </form>

            {/* Right: "Let's get started!" Hero Card matching Screen 6 */}
            <div
              style={{
                background: "var(--glass-surface-elevated)",
                border: "1px solid var(--border-glass)",
                borderRadius: "16px",
                padding: "1.75rem",
                display: "flex",
                flexDirection: "column",
                gap: "1.25rem",
                boxShadow: "var(--shadow-sm)",
              }}
            >
              {/* Modern Cityscape / Gradient Artwork Banner */}
              <div
                style={{
                  width: "100%",
                  height: "140px",
                  borderRadius: "12px",
                  background: "linear-gradient(135deg, rgba(56, 103, 245, 0.12) 0%, rgba(138, 69, 246, 0.18) 100%)",
                  border: "1px solid rgba(56, 103, 245, 0.2)",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  position: "relative",
                  overflow: "hidden",
                }}
              >
                <div
                  style={{
                    position: "absolute",
                    width: "120px",
                    height: "120px",
                    borderRadius: "50%",
                    background: "radial-gradient(circle, rgba(56, 103, 245, 0.3) 0%, transparent 70%)",
                    top: "-20px",
                    left: "-20px",
                  }}
                />
                <div
                  style={{
                    position: "absolute",
                    width: "120px",
                    height: "120px",
                    borderRadius: "50%",
                    background: "radial-gradient(circle, rgba(138, 69, 246, 0.3) 0%, transparent 70%)",
                    bottom: "-20px",
                    right: "-20px",
                  }}
                />
                <div style={{ textAlign: "center", zIndex: 1 }}>
                  <div style={{ fontSize: "2.5rem", marginBottom: "0.25rem" }}>🚀</div>
                  <div style={{ fontSize: "0.75rem", fontWeight: 700, color: "var(--brand-primary)", textTransform: "uppercase", letterSpacing: "0.06em" }}>
                    Seamless Onboarding
                  </div>
                </div>
              </div>

              <div>
                <h3 style={{ fontSize: "1.125rem", fontWeight: 700, margin: "0 0 0.35rem 0", color: "var(--text-primary)" }}>
                  Let's get started!
                </h3>
                <p style={{ fontSize: "0.8125rem", color: "var(--text-secondary)", margin: 0, lineHeight: 1.5 }}>
                  Set up your organization member in a few simple steps and start managing their products and role permissions.
                </p>
              </div>

              {/* Live Preview Specs */}
              <div
                style={{
                  background: "var(--glass-surface-sunken)",
                  padding: "1rem",
                  borderRadius: "10px",
                  border: "1px solid var(--border-subtle)",
                  display: "flex",
                  flexDirection: "column",
                  gap: "0.6rem",
                  fontSize: "0.8125rem",
                }}
              >
                <div style={{ display: "flex", justifyContent: "space-between" }}>
                  <span style={{ color: "var(--text-muted)" }}>Target Org:</span>
                  <span style={{ fontWeight: 600, color: "var(--text-primary)" }}>{activeTenant?.name || "Enterprise"}</span>
                </div>
                <div style={{ display: "flex", justifyContent: "space-between" }}>
                  <span style={{ color: "var(--text-muted)" }}>Member Name:</span>
                  <span style={{ fontWeight: 600, color: fullName ? "var(--brand-primary)" : "var(--text-muted)" }}>
                    {fullName || "Awaiting input..."}
                  </span>
                </div>
                <div style={{ display: "flex", justifyContent: "space-between" }}>
                  <span style={{ color: "var(--text-muted)" }}>Target Email:</span>
                  <span style={{ fontWeight: 600, color: email ? "var(--brand-primary)" : "var(--text-muted)", wordBreak: "break-all" }}>
                    {email || "Awaiting input..."}
                  </span>
                </div>
              </div>

              <div
                style={{
                  fontSize: "0.75rem",
                  color: "var(--text-muted)",
                  lineHeight: 1.5,
                  padding: "0.75rem",
                  borderRadius: "8px",
                  border: "1px dashed var(--border-subtle)",
                  textAlign: "center",
                }}
              >
                🔐 Cryptographic invitation link will be generated automatically upon completion.
              </div>
            </div>
          </div>
        )}

        {/* =================================================================== */}
        {/* STEP 2: ROLE CONFIGURATION                                          */}
        {/* =================================================================== */}
        {currentStep === "role" && (
          <form
            onSubmit={handleNextFromRole}
            className="glass-panel"
            style={{
              padding: "2.5rem",
              borderRadius: "16px",
              border: "1px solid var(--border-glass)",
              backgroundColor: "var(--glass-surface-elevated)",
              boxShadow: "var(--shadow-md)",
              display: "flex",
              flexDirection: "column",
              gap: "2rem",
            }}
          >
            {/* Step Header */}
            <div>
              <span
                style={{
                  display: "inline-block",
                  padding: "0.2rem 0.6rem",
                  borderRadius: "6px",
                  fontSize: "0.6875rem",
                  fontWeight: 700,
                  letterSpacing: "0.06em",
                  textTransform: "uppercase",
                  backgroundColor: "var(--brand-primary-light)",
                  color: "var(--brand-primary)",
                  marginBottom: "0.5rem",
                }}
              >
                Step 02 of 05
              </span>
              <h2 style={{ fontSize: "1.375rem", fontWeight: 800, margin: "0 0 0.35rem 0", letterSpacing: "-0.02em", color: "var(--text-primary)" }}>
                Step 2: Role & Permissions Setup
              </h2>
              <p style={{ color: "var(--text-muted)", fontSize: "0.875rem", margin: 0, lineHeight: 1.5 }}>
                Configure whether this member operates as a standard member or has administrative role assignments. You can also create a new tenant-scoped custom role inline.
              </p>
            </div>

            {roleCreationSuccess && (
              <div
                style={{
                  padding: "0.875rem 1.25rem",
                  borderRadius: "10px",
                  backgroundColor: "var(--status-success-bg)",
                  border: "1px solid var(--status-success-border)",
                  color: "var(--status-success)",
                  fontSize: "0.875rem",
                  fontWeight: 500,
                  display: "flex",
                  alignItems: "center",
                  gap: "0.6rem",
                }}
              >
                <CheckCircleIcon size={18} />
                <span>{roleCreationSuccess}</span>
              </div>
            )}

            {/* Role Mode Selection Cards */}
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: "1.125rem" }}>
              {/* Option A: Standard Member */}
              <div
                onClick={() => {
                  setRoleMode("standard");
                  setSelectedRoleId("");
                  setFieldErrors({});
                }}
                className="glass-panel"
                style={{
                  padding: "1.375rem",
                  borderRadius: "12px",
                  cursor: "pointer",
                  border: roleMode === "standard"
                    ? "2px solid var(--brand-primary)"
                    : "1px solid var(--border-glass)",
                  backgroundColor: roleMode === "standard"
                    ? "var(--brand-primary-light)"
                    : "var(--glass-surface)",
                  boxShadow: roleMode === "standard"
                    ? "0 0 0 3px var(--brand-primary-light), var(--shadow-sm)"
                    : "var(--shadow-sm)",
                  transition: "all 0.15s ease",
                  display: "flex",
                  flexDirection: "column",
                  justifyContent: "space-between",
                }}
              >
                <div>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.875rem" }}>
                    <div
                      style={{
                        width: "36px",
                        height: "36px",
                        borderRadius: "8px",
                        backgroundColor: roleMode === "standard" ? "var(--brand-primary)" : "var(--glass-surface-sunken)",
                        color: roleMode === "standard" ? "#ffffff" : "var(--text-secondary)",
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                        transition: "all 0.15s ease",
                      }}
                    >
                      <UserIcon size={18} />
                    </div>
                    <span
                      style={{
                        fontSize: "0.6875rem",
                        fontWeight: 700,
                        padding: "0.15rem 0.5rem",
                        borderRadius: "9999px",
                        backgroundColor: "var(--status-success-bg)",
                        color: "var(--status-success)",
                      }}
                    >
                      Recommended
                    </span>
                  </div>
                  <div style={{ fontWeight: 700, fontSize: "0.9375rem", color: "var(--text-primary)", marginBottom: "0.35rem" }}>
                    Standard Member
                  </div>
                  <p style={{ fontSize: "0.8125rem", color: "var(--text-muted)", margin: 0, lineHeight: 1.45 }}>
                    Standard end-user access. User will only access assigned products and consumer workspace, with no tenant administration privileges.
                  </p>
                </div>

                <div style={{ marginTop: "1rem", display: "flex", alignItems: "center", gap: "0.45rem", fontSize: "0.75rem", color: roleMode === "standard" ? "var(--brand-primary)" : "var(--text-muted)", fontWeight: 600 }}>
                  <input
                    type="radio"
                    name="roleMode"
                    checked={roleMode === "standard"}
                    onChange={() => {
                      setRoleMode("standard");
                      setSelectedRoleId("");
                    }}
                    style={{ accentColor: "var(--brand-primary)" }}
                  />
                  <span>Select Standard</span>
                </div>
              </div>

              {/* Option B: Assign Existing Role */}
              <div
                onClick={() => {
                  setRoleMode("existing");
                  setFieldErrors({});
                }}
                className="glass-panel"
                style={{
                  padding: "1.375rem",
                  borderRadius: "12px",
                  cursor: "pointer",
                  border: roleMode === "existing"
                    ? "2px solid var(--brand-primary)"
                    : "1px solid var(--border-glass)",
                  backgroundColor: roleMode === "existing"
                    ? "var(--brand-primary-light)"
                    : "var(--glass-surface)",
                  boxShadow: roleMode === "existing"
                    ? "0 0 0 3px var(--brand-primary-light), var(--shadow-sm)"
                    : "var(--shadow-sm)",
                  transition: "all 0.15s ease",
                  display: "flex",
                  flexDirection: "column",
                  justifyContent: "space-between",
                }}
              >
                <div>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.875rem" }}>
                    <div
                      style={{
                        width: "36px",
                        height: "36px",
                        borderRadius: "8px",
                        backgroundColor: roleMode === "existing" ? "var(--brand-primary)" : "var(--glass-surface-sunken)",
                        color: roleMode === "existing" ? "#ffffff" : "var(--text-secondary)",
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                        transition: "all 0.15s ease",
                      }}
                    >
                      <ShieldCheckIcon size={18} />
                    </div>
                    <span
                      style={{
                        fontSize: "0.6875rem",
                        fontWeight: 700,
                        padding: "0.15rem 0.5rem",
                        borderRadius: "9999px",
                        backgroundColor: "var(--border-subtle)",
                        color: "var(--text-secondary)",
                      }}
                    >
                      {availableRoles.length} Roles
                    </span>
                  </div>
                  <div style={{ fontWeight: 700, fontSize: "0.9375rem", color: "var(--text-primary)", marginBottom: "0.35rem" }}>
                    Assign Existing Role
                  </div>
                  <p style={{ fontSize: "0.8125rem", color: "var(--text-muted)", margin: 0, lineHeight: 1.45 }}>
                    Assign an existing administrative role (Tenant Administrator, Support Manager, etc.) with preconfigured permission sets.
                  </p>
                </div>

                <div style={{ marginTop: "1rem", display: "flex", alignItems: "center", gap: "0.45rem", fontSize: "0.75rem", color: roleMode === "existing" ? "var(--brand-primary)" : "var(--text-muted)", fontWeight: 600 }}>
                  <input
                    type="radio"
                    name="roleMode"
                    checked={roleMode === "existing"}
                    onChange={() => setRoleMode("existing")}
                    style={{ accentColor: "var(--brand-primary)" }}
                  />
                  <span>Select Existing</span>
                </div>
              </div>

              {/* Option C: Create Custom Role */}
              <div
                onClick={() => {
                  setRoleMode("custom");
                  setFieldErrors({});
                }}
                className="glass-panel"
                style={{
                  padding: "1.375rem",
                  borderRadius: "12px",
                  cursor: "pointer",
                  border: roleMode === "custom"
                    ? "2px solid var(--brand-primary)"
                    : "1px solid var(--border-glass)",
                  backgroundColor: roleMode === "custom"
                    ? "var(--brand-primary-light)"
                    : "var(--glass-surface)",
                  boxShadow: roleMode === "custom"
                    ? "0 0 0 3px var(--brand-primary-light), var(--shadow-sm)"
                    : "var(--shadow-sm)",
                  transition: "all 0.15s ease",
                  display: "flex",
                  flexDirection: "column",
                  justifyContent: "space-between",
                }}
              >
                <div>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.875rem" }}>
                    <div
                      style={{
                        width: "36px",
                        height: "36px",
                        borderRadius: "8px",
                        backgroundColor: roleMode === "custom" ? "var(--brand-primary)" : "var(--glass-surface-sunken)",
                        color: roleMode === "custom" ? "#ffffff" : "var(--text-secondary)",
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                        transition: "all 0.15s ease",
                      }}
                    >
                      <PlusIcon size={18} />
                    </div>
                    <span
                      style={{
                        fontSize: "0.6875rem",
                        fontWeight: 700,
                        padding: "0.15rem 0.5rem",
                        borderRadius: "9999px",
                        backgroundColor: "var(--brand-primary-light)",
                        color: "var(--brand-primary)",
                      }}
                    >
                      Advanced
                    </span>
                  </div>
                  <div style={{ fontWeight: 700, fontSize: "0.9375rem", color: "var(--text-primary)", marginBottom: "0.35rem" }}>
                    + Create Custom Role
                  </div>
                  <p style={{ fontSize: "0.8125rem", color: "var(--text-muted)", margin: 0, lineHeight: 1.45 }}>
                    Define a new custom organization role with granular permission toggles and associate it directly with this member.
                  </p>
                </div>

                <div style={{ marginTop: "1rem", display: "flex", alignItems: "center", gap: "0.45rem", fontSize: "0.75rem", color: roleMode === "custom" ? "var(--brand-primary)" : "var(--text-muted)", fontWeight: 600 }}>
                  <input
                    type="radio"
                    name="roleMode"
                    checked={roleMode === "custom"}
                    onChange={() => setRoleMode("custom")}
                    style={{ accentColor: "var(--brand-primary)" }}
                  />
                  <span>Create Custom</span>
                </div>
              </div>
            </div>

            {/* Details for Option B: Existing Roles Selector */}
            {roleMode === "existing" && (
              <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <h3 style={{ fontSize: "0.9375rem", fontWeight: 700, margin: 0, color: "var(--text-primary)" }}>
                    Select Administrative Role
                  </h3>
                  <span style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
                    {availableRoles.length} roles grantable under this tenant
                  </span>
                </div>

                {isLoadingRoles ? (
                  <LoadingSpinner label="Loading roles..." />
                ) : availableRoles.length === 0 ? (
                  <div
                    style={{
                      padding: "1.5rem",
                      textAlign: "center",
                      borderRadius: "10px",
                      border: "1px dashed var(--border-glass)",
                      color: "var(--text-muted)",
                      fontSize: "0.875rem",
                    }}
                  >
                    No administrative roles available. Use "+ Create Custom Role" above.
                  </div>
                ) : (
                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.875rem" }}>
                    {availableRoles.map((role) => {
                      const isSelected = selectedRoleId === role.id;
                      return (
                        <div
                          key={role.id}
                          onClick={() => {
                            setSelectedRoleId(role.id);
                            setFieldErrors({});
                          }}
                          className="glass-panel"
                          style={{
                            padding: "1.125rem 1.25rem",
                            borderRadius: "10px",
                            cursor: "pointer",
                            border: isSelected
                              ? "2px solid var(--brand-primary)"
                              : "1px solid var(--border-glass)",
                            backgroundColor: isSelected
                              ? "var(--brand-primary-light)"
                              : "var(--glass-surface)",
                            boxShadow: isSelected
                              ? "0 0 0 2px var(--brand-primary-light), var(--shadow-sm)"
                              : "var(--shadow-sm)",
                            transition: "all 0.15s ease",
                          }}
                        >
                          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.35rem" }}>
                            <span style={{ fontWeight: 700, fontSize: "0.9375rem", color: "var(--text-primary)" }}>
                              {role.name}
                            </span>
                            <span
                              style={{
                                fontSize: "0.6875rem",
                                fontFamily: "var(--font-code, monospace)",
                                padding: "0.1rem 0.45rem",
                                borderRadius: "4px",
                                backgroundColor: "var(--border-subtle)",
                                color: "var(--text-secondary)",
                              }}
                            >
                              {role.code}
                            </span>
                          </div>
                          <p style={{ fontSize: "0.8125rem", color: "var(--text-muted)", margin: "0.35rem 0 0.75rem 0", lineHeight: 1.4 }}>
                            {role.description || "Administrative role for tenant operations."}
                          </p>
                          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                            <span style={{ fontSize: "0.75rem", color: "var(--brand-primary)", fontWeight: 600 }}>
                              {role.permission_keys?.length || 0} permissions included
                            </span>
                            {isSelected && (
                              <span style={{ fontSize: "0.75rem", color: "var(--brand-primary)", fontWeight: 700 }}>
                                Selected ✓
                              </span>
                            )}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
                {fieldErrors.selectedRole && (
                  <span className="form-error">
                    <AlertCircleIcon size={14} /> {fieldErrors.selectedRole}
                  </span>
                )}
              </div>
            )}

            {/* Details for Option C: Inline Role Creation */}
            {roleMode === "custom" && (
              <div
                style={{
                  padding: "1.5rem",
                  borderRadius: "12px",
                  backgroundColor: "var(--glass-surface)",
                  border: "1px solid var(--border-glass)",
                  display: "flex",
                  flexDirection: "column",
                  gap: "1.25rem",
                }}
              >
                <div>
                  <h3 style={{ fontSize: "1rem", fontWeight: 700, margin: "0 0 0.25rem 0", color: "var(--text-primary)" }}>
                    Create New Tenant-Scoped Custom Role
                  </h3>
                  <p style={{ fontSize: "0.8125rem", color: "var(--text-muted)", margin: 0 }}>
                    This role will be created under your active organization partition and assigned immediately to the member.
                  </p>
                </div>

                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem" }}>
                  <div>
                    <label style={{ display: "block", fontSize: "0.8125rem", fontWeight: 600, marginBottom: "0.35rem" }}>
                      Role Name <span style={{ color: "var(--status-danger)" }}>*</span>
                    </label>
                    <input
                      type="text"
                      placeholder="e.g. Course Reviewer"
                      value={newRoleName}
                      onChange={(e) => setNewRoleName(e.target.value)}
                      className={`form-input input-text ${fieldErrors.newRoleName ? "form-input-error" : ""}`}
                    />
                    {fieldErrors.newRoleName && (
                      <span className="form-error">{fieldErrors.newRoleName}</span>
                    )}
                  </div>
                  <div>
                    <label style={{ display: "block", fontSize: "0.8125rem", fontWeight: 600, marginBottom: "0.35rem" }}>
                      Role Code <span style={{ color: "var(--status-danger)" }}>*</span>
                    </label>
                    <input
                      type="text"
                      placeholder="e.g. course_reviewer"
                      value={newRoleCode}
                      onChange={(e) => setNewRoleCode(e.target.value)}
                      className={`form-input input-text ${fieldErrors.newRoleCode ? "form-input-error" : ""}`}
                    />
                    {fieldErrors.newRoleCode && (
                      <span className="form-error">{fieldErrors.newRoleCode}</span>
                    )}
                  </div>
                </div>

                <div>
                  <label style={{ display: "block", fontSize: "0.8125rem", fontWeight: 600, marginBottom: "0.35rem" }}>
                    Description
                  </label>
                  <input
                    type="text"
                    placeholder="Short summary of role responsibilities and privileges"
                    value={newRoleDesc}
                    onChange={(e) => setNewRoleDesc(e.target.value)}
                    className="form-input input-text"
                  />
                </div>

                {/* Permissions selector */}
                <div>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.5rem" }}>
                    <label style={{ fontSize: "0.8125rem", fontWeight: 600 }}>
                      Supported Role Permissions
                    </label>
                    <span style={{ fontSize: "0.75rem", color: "var(--brand-primary)", fontWeight: 600 }}>
                      {newRolePermissions.length} selected
                    </span>
                  </div>

                  {accessCatalog?.permissions && accessCatalog.permissions.length > 0 ? (
                    <div
                      style={{
                        maxHeight: "220px",
                        overflowY: "auto",
                        border: "1px solid var(--border-glass)",
                        borderRadius: "8px",
                        padding: "0.75rem",
                        display: "grid",
                        gridTemplateColumns: "1fr 1fr",
                        gap: "0.5rem",
                        backgroundColor: "var(--glass-surface-sunken)",
                      }}
                    >
                      {accessCatalog.permissions.map((p) => {
                        const isChecked = newRolePermissions.includes(p.key);
                        return (
                          <label
                            key={p.key}
                            style={{
                              display: "flex",
                              alignItems: "flex-start",
                              gap: "0.6rem",
                              fontSize: "0.8125rem",
                              cursor: "pointer",
                              padding: "0.45rem 0.65rem",
                              borderRadius: "6px",
                              backgroundColor: isChecked ? "var(--brand-primary-light)" : "var(--glass-surface)",
                              border: isChecked ? "1px solid var(--brand-primary)" : "1px solid var(--border-subtle)",
                              transition: "all 0.12s ease",
                            }}
                          >
                            <input
                              type="checkbox"
                              checked={isChecked}
                              onChange={() => {
                                setNewRolePermissions((prev) =>
                                  prev.includes(p.key) ? prev.filter((k) => k !== p.key) : [...prev, p.key]
                                );
                              }}
                              style={{ marginTop: "0.15rem", accentColor: "var(--brand-primary)" }}
                            />
                            <div>
                              <div style={{ fontWeight: 600, color: "var(--text-primary)" }}>{p.display_name}</div>
                              <div style={{ fontSize: "0.6875rem", color: "var(--text-muted)", fontFamily: "var(--font-code, monospace)" }}>
                                {p.key}
                              </div>
                            </div>
                          </label>
                        );
                      })}
                    </div>
                  ) : (
                    <div style={{ fontSize: "0.8125rem", color: "var(--text-muted)", fontStyle: "italic" }}>
                      Loading grantable permissions...
                    </div>
                  )}
                </div>

                <div style={{ display: "flex", justifyContent: "flex-end" }}>
                  <button
                    type="button"
                    onClick={handleCreateCustomRole}
                    className="btn btn-secondary"
                    disabled={isCreatingRole}
                    style={{ padding: "0.5rem 1.1rem", fontSize: "0.8125rem", fontWeight: 600 }}
                  >
                    {isCreatingRole ? "Creating Role..." : "Create & Select Role"}
                  </button>
                </div>
                {fieldErrors.customRole && (
                  <span className="form-error">
                    <AlertCircleIcon size={14} /> {fieldErrors.customRole}
                  </span>
                )}
              </div>
            )}

            {/* Bottom Actions */}
            <div style={{ display: "flex", justifyContent: "space-between", paddingTop: "0.5rem" }}>
              <button
                type="button"
                onClick={() => setCurrentStep("details")}
                className="btn btn-secondary"
                style={{ padding: "0.625rem 1.25rem", minHeight: "42px" }}
              >
                ← Back
              </button>
              <button
                type="submit"
                className="btn btn-primary"
                style={{
                  padding: "0.625rem 1.5rem",
                  minHeight: "42px",
                  fontSize: "0.875rem",
                  fontWeight: 600,
                }}
              >
                Continue to Product Access →
              </button>
            </div>
          </form>
        )}

        {/* =================================================================== */}
        {/* STEP 3: PRODUCT ACCESS                                              */}
        {/* =================================================================== */}
        {currentStep === "products" && (
          <form
            onSubmit={handleNextFromProducts}
            className="glass-panel"
            style={{
              padding: "2.5rem",
              borderRadius: "16px",
              border: "1px solid var(--border-glass)",
              backgroundColor: "var(--glass-surface-elevated)",
              boxShadow: "var(--shadow-md)",
              display: "flex",
              flexDirection: "column",
              gap: "2rem",
            }}
          >
            {/* Step Header */}
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: "1rem" }}>
              <div>
                <span
                  style={{
                    display: "inline-block",
                    padding: "0.2rem 0.6rem",
                    borderRadius: "6px",
                    fontSize: "0.6875rem",
                    fontWeight: 700,
                    letterSpacing: "0.06em",
                    textTransform: "uppercase",
                    backgroundColor: "var(--brand-primary-light)",
                    color: "var(--brand-primary)",
                    marginBottom: "0.5rem",
                  }}
                >
                  Step 03 of 05
                </span>
                <h2 style={{ fontSize: "1.375rem", fontWeight: 800, margin: "0 0 0.35rem 0", letterSpacing: "-0.02em", color: "var(--text-primary)" }}>
                  Step 3: Product Access & Entitlements
                </h2>
                <p style={{ color: "var(--text-muted)", fontSize: "0.875rem", margin: 0, lineHeight: 1.5 }}>
                  Select which entitled products this member can access. Only products entitled to your organization are displayed.
                </p>
              </div>

              {entitledProducts.length > 0 && (
                <div style={{ display: "flex", gap: "0.5rem" }}>
                  <button
                    type="button"
                    onClick={() => setSelectedProductIds(entitledProducts.map((p) => p.id))}
                    className="btn btn-secondary"
                    style={{ fontSize: "0.75rem", padding: "0.35rem 0.75rem", minHeight: "32px" }}
                  >
                    Select All
                  </button>
                  <button
                    type="button"
                    onClick={() => setSelectedProductIds([])}
                    className="btn btn-secondary"
                    style={{ fontSize: "0.75rem", padding: "0.35rem 0.75rem", minHeight: "32px" }}
                  >
                    Deselect All
                  </button>
                </div>
              )}
            </div>

            {isLoadingProducts ? (
              <LoadingSpinner label="Loading entitled products..." />
            ) : entitledProducts.length === 0 ? (
              <div
                style={{
                  padding: "3rem 2rem",
                  textAlign: "center",
                  borderRadius: "12px",
                  border: "1px dashed var(--border-glass)",
                  color: "var(--text-muted)",
                }}
              >
                <BoxIcon size={36} style={{ margin: "0 auto 1rem auto", opacity: 0.5 }} />
                <p style={{ margin: 0, fontWeight: 700, fontSize: "1rem", color: "var(--text-primary)" }}>
                  No Entitled Products Available
                </p>
                <p style={{ fontSize: "0.8125rem", marginTop: "0.35rem" }}>
                  Your organization does not currently hold active product entitlements. Please contact Platform Support to request product access.
                </p>
              </div>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
                {entitledProducts.map((prod) => {
                  const isSelected = selectedProductIds.includes(prod.id);
                  const isFull = !prod.is_capacity_available && prod.quota_type === "numeric";

                  return (
                    <div
                      key={prod.id}
                      style={{
                        display: "flex",
                        flexDirection: "column",
                        gap: "0.75rem",
                      }}
                    >
                      <div
                        onClick={() => !isFull && handleToggleProduct(prod.id)}
                        className="glass-panel"
                        style={{
                          padding: "1.25rem 1.5rem",
                          display: "flex",
                          alignItems: "center",
                          justifyContent: "space-between",
                          cursor: isFull ? "not-allowed" : "pointer",
                          opacity: isFull ? 0.6 : 1,
                          border: isSelected
                            ? "2px solid var(--brand-primary)"
                            : "1px solid var(--border-glass)",
                          backgroundColor: isSelected
                            ? "var(--brand-primary-light)"
                            : "var(--glass-surface)",
                          borderRadius: "12px",
                          boxShadow: isSelected
                            ? "0 0 0 2px var(--brand-primary-light), var(--shadow-sm)"
                            : "var(--shadow-sm)",
                          transition: "all 0.15s ease",
                        }}
                      >
                        <div style={{ display: "flex", alignItems: "center", gap: "1.125rem" }}>
                          <input
                            type="checkbox"
                            checked={isSelected}
                            disabled={isFull}
                            onChange={() => handleToggleProduct(prod.id)}
                            onClick={(e) => e.stopPropagation()}
                            style={{ width: "18px", height: "18px", accentColor: "var(--brand-primary)", cursor: isFull ? "not-allowed" : "pointer" }}
                          />

                          <div
                            style={{
                              width: "40px",
                              height: "40px",
                              borderRadius: "10px",
                              backgroundColor: isSelected ? "var(--brand-primary)" : "var(--glass-surface-sunken)",
                              color: isSelected ? "#ffffff" : "var(--text-secondary)",
                              display: "flex",
                              alignItems: "center",
                              justifyContent: "center",
                              transition: "all 0.15s ease",
                            }}
                          >
                            <BoxIcon size={20} />
                          </div>

                          <div>
                            <div style={{ display: "flex", alignItems: "center", gap: "0.6rem" }}>
                              <span style={{ fontWeight: 700, fontSize: "1rem", color: "var(--text-primary)" }}>
                                {prod.name}
                              </span>
                              <span
                                style={{
                                  fontSize: "0.6875rem",
                                  padding: "0.15rem 0.5rem",
                                  borderRadius: "4px",
                                  backgroundColor: "var(--border-subtle)",
                                  fontFamily: "var(--font-code, monospace)",
                                  color: "var(--text-secondary)",
                                  fontWeight: 600,
                                }}
                              >
                                {prod.code}
                              </span>
                            </div>
                            <p style={{ margin: "0.25rem 0 0 0", fontSize: "0.8125rem", color: "var(--text-muted)" }}>
                              Seat Quota: {prod.quota_type === "unlimited" ? "Unlimited seats available" : `${prod.consumed_seats} / ${prod.total_limit} seats assigned`}
                            </p>
                          </div>
                        </div>

                        <div style={{ textAlign: "right" }}>
                          <span
                            className={isSelected ? "badge badge-success" : isFull ? "badge" : "badge"}
                            style={{
                              backgroundColor: isSelected
                                ? "var(--status-success-bg)"
                                : isFull
                                ? "var(--status-danger-bg)"
                                : "var(--border-subtle)",
                              color: isSelected
                                ? "var(--status-success)"
                                : isFull
                                ? "var(--status-danger)"
                                : "var(--text-muted)",
                              border: "1px solid",
                              borderColor: isSelected
                                ? "var(--status-success-border)"
                                : isFull
                                ? "var(--status-danger-border)"
                                : "transparent",
                              fontWeight: 600,
                              fontSize: "0.75rem",
                            }}
                          >
                            {isSelected ? "Assigned ✓" : isFull ? "Capacity Reached" : "Available"}
                          </span>
                          {prod.available_seats !== null && (
                            <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginTop: "0.25rem" }}>
                              {prod.available_seats} {prod.available_seats === 1 ? "seat" : "seats"} left
                            </div>
                          )}
                        </div>
                      </div>

                      {/* LMS Console Selection Card (Mutually Exclusive Options) */}
                      {isSelected && (prod.code?.toLowerCase().includes("lms") || prod.name?.toLowerCase().includes("learning")) && (
                        <div
                          style={{
                            padding: "1.25rem 1.5rem",
                            borderRadius: "12px",
                            backgroundColor: "var(--glass-surface)",
                            border: "1px solid var(--border-glass)",
                            boxShadow: "var(--shadow-sm)",
                          }}
                          onClick={(e) => e.stopPropagation()}
                        >
                          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1rem" }}>
                            <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                              <span style={{ fontSize: "0.875rem", fontWeight: 700, color: "var(--text-primary)" }}>
                                LMS Console Assignment
                              </span>
                              <span className="badge" style={{ backgroundColor: "var(--brand-primary-light)", color: "var(--brand-primary)", fontSize: "0.6875rem" }}>
                                Target Portal
                              </span>
                            </div>
                            <span style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
                              Select target console experience for this member
                            </span>
                          </div>

                          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem" }}>
                            {/* Option 1: Normal User Console */}
                            <div
                              onClick={() => setLmsConsole("normal_user_console")}
                              style={{
                                padding: "1rem 1.25rem",
                                borderRadius: "10px",
                                cursor: "pointer",
                                border: lmsConsole === "normal_user_console"
                                  ? "2px solid var(--brand-primary)"
                                  : "1px solid var(--border-glass)",
                                backgroundColor: lmsConsole === "normal_user_console"
                                  ? "var(--brand-primary-light)"
                                  : "var(--glass-surface-sunken)",
                                display: "flex",
                                alignItems: "flex-start",
                                gap: "0.75rem",
                                transition: "all 0.15s ease",
                              }}
                            >
                              <input
                                type="radio"
                                id="lms-console-normal"
                                name="lms-console-selection"
                                value="normal_user_console"
                                checked={lmsConsole === "normal_user_console"}
                                onChange={() => setLmsConsole("normal_user_console")}
                                style={{ marginTop: "0.2rem", accentColor: "var(--brand-primary)", cursor: "pointer" }}
                              />
                              <div>
                                <div style={{ fontWeight: 700, fontSize: "0.875rem", color: "var(--text-primary)" }}>
                                  Normal User Console
                                </div>
                                <p style={{ margin: "0.25rem 0 0 0", fontSize: "0.78125rem", color: "var(--text-muted)", lineHeight: 1.4 }}>
                                  Regular user-facing LMS console (/dashboard). Safe for all member accounts.
                                </p>
                              </div>
                            </div>

                            {/* Option 2: Tenant Console */}
                            <div
                              onClick={() => {
                                if (isAdministrativeMember) {
                                  setLmsConsole("tenant_console");
                                }
                              }}
                              style={{
                                padding: "1rem 1.25rem",
                                borderRadius: "10px",
                                cursor: isAdministrativeMember ? "pointer" : "not-allowed",
                                opacity: isAdministrativeMember ? 1 : 0.65,
                                border: lmsConsole === "tenant_console"
                                  ? "2px solid var(--brand-primary)"
                                  : "1px solid var(--border-glass)",
                                backgroundColor: lmsConsole === "tenant_console"
                                  ? "var(--brand-primary-light)"
                                  : "var(--glass-surface-sunken)",
                                display: "flex",
                                alignItems: "flex-start",
                                gap: "0.75rem",
                                transition: "all 0.15s ease",
                              }}
                            >
                              <input
                                type="radio"
                                id="lms-console-tenant"
                                name="lms-console-selection"
                                value="tenant_console"
                                checked={lmsConsole === "tenant_console"}
                                disabled={!isAdministrativeMember}
                                onChange={() => {
                                  if (isAdministrativeMember) {
                                    setLmsConsole("tenant_console");
                                  }
                                }}
                                style={{
                                  marginTop: "0.2rem",
                                  accentColor: "var(--brand-primary)",
                                  cursor: isAdministrativeMember ? "pointer" : "not-allowed",
                                }}
                              />
                              <div>
                                <div style={{ display: "flex", alignItems: "center", gap: "0.45rem" }}>
                                  <span style={{ fontWeight: 700, fontSize: "0.875rem", color: "var(--text-primary)" }}>
                                    Tenant Console
                                  </span>
                                  {!isAdministrativeMember && (
                                    <span
                                      style={{
                                        fontSize: "0.6875rem",
                                        padding: "0.15rem 0.45rem",
                                        borderRadius: "4px",
                                        backgroundColor: "var(--status-danger-bg)",
                                        color: "var(--status-danger)",
                                        fontWeight: 600,
                                      }}
                                    >
                                      Admin Required
                                    </span>
                                  )}
                                </div>
                                <p style={{ margin: "0.25rem 0 0 0", fontSize: "0.78125rem", color: "var(--text-muted)", lineHeight: 1.4 }}>
                                  Tenant/admin-facing LMS console (/org-admin).
                                  {!isAdministrativeMember && " Only available for Tenant Administrators."}
                                </p>
                              </div>
                            </div>
                          </div>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}

            {/* Bottom Actions */}
            <div style={{ display: "flex", justifyContent: "space-between", paddingTop: "0.5rem" }}>
              <button
                type="button"
                onClick={() => setCurrentStep("role")}
                className="btn btn-secondary"
                style={{ padding: "0.625rem 1.25rem", minHeight: "42px" }}
              >
                ← Back
              </button>
              <button
                type="submit"
                className="btn btn-primary"
                style={{
                  padding: "0.625rem 1.5rem",
                  minHeight: "42px",
                  fontSize: "0.875rem",
                  fontWeight: 600,
                }}
              >
                Continue to Console Feature Access →
              </button>
            </div>
          </form>
        )}

        {/* =================================================================== */}
        {/* STEP 4: CONSOLE FEATURE ACCESS                                      */}
        {/* =================================================================== */}
        {currentStep === "features" && (
          <form
            onSubmit={handleNextFromFeatures}
            className="glass-panel"
            style={{
              padding: "2.5rem",
              borderRadius: "16px",
              border: "1px solid var(--border-glass)",
              backgroundColor: "var(--glass-surface-elevated)",
              boxShadow: "var(--shadow-md)",
              display: "flex",
              flexDirection: "column",
              gap: "2rem",
            }}
          >
            {/* Step Header */}
            <div>
              <span
                style={{
                  display: "inline-block",
                  padding: "0.2rem 0.6rem",
                  borderRadius: "6px",
                  fontSize: "0.6875rem",
                  fontWeight: 700,
                  letterSpacing: "0.06em",
                  textTransform: "uppercase",
                  backgroundColor: "var(--brand-primary-light)",
                  color: "var(--brand-primary)",
                  marginBottom: "0.5rem",
                }}
              >
                Step 04 of 05
              </span>
              <h2 style={{ fontSize: "1.375rem", fontWeight: 800, margin: "0 0 0.35rem 0", letterSpacing: "-0.02em", color: "var(--text-primary)" }}>
                Step 4: Console Feature & Module Access
              </h2>
              <p style={{ color: "var(--text-muted)", fontSize: "0.875rem", margin: 0, lineHeight: 1.5 }}>
                Configure individual product module permissions for the selected products. Member access is strictly bounded by your organization&apos;s feature ceilings.
              </p>
            </div>

            {selectedProducts.length === 0 ? (
              <div
                style={{
                  padding: "3rem 2rem",
                  textAlign: "center",
                  borderRadius: "12px",
                  border: "1px dashed var(--border-glass)",
                  color: "var(--text-muted)",
                }}
              >
                <LayersIcon size={36} style={{ margin: "0 auto 1rem auto", opacity: 0.5 }} />
                <p style={{ margin: 0, fontWeight: 700, fontSize: "1rem", color: "var(--text-primary)" }}>
                  No Products Selected
                </p>
                <p style={{ fontSize: "0.8125rem", marginTop: "0.35rem" }}>
                  Return to Step 3 if you wish to assign products and configure their respective modules.
                </p>
                <button
                  type="button"
                  onClick={() => setCurrentStep("products")}
                  className="btn btn-secondary"
                  style={{ marginTop: "1.25rem", fontSize: "0.8125rem" }}
                >
                  ← Go to Step 3: Product Access
                </button>
              </div>
            ) : isLoadingModules ? (
              <LoadingSpinner label="Loading product feature modules..." />
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }}>
                {selectedProducts.map((prod) => {
                  const modules = productModulesMap[prod.id] || [];

                  return (
                    <div
                      key={prod.id}
                      className="glass-panel"
                      style={{
                        padding: "1.5rem",
                        borderRadius: "12px",
                        border: "1px solid var(--border-glass)",
                        backgroundColor: "var(--glass-surface)",
                        boxShadow: "var(--shadow-sm)",
                      }}
                    >
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1rem" }}>
                        <div style={{ display: "flex", alignItems: "center", gap: "0.6rem" }}>
                          <span style={{ fontWeight: 700, fontSize: "1rem", color: "var(--text-primary)" }}>
                            {prod.name}
                          </span>
                          <span
                            style={{
                              fontSize: "0.6875rem",
                              padding: "0.15rem 0.5rem",
                              borderRadius: "4px",
                              backgroundColor: "var(--border-subtle)",
                              fontFamily: "var(--font-code, monospace)",
                              color: "var(--text-secondary)",
                              fontWeight: 600,
                            }}
                          >
                            {prod.code}
                          </span>
                        </div>
                        <span style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
                          {modules.length} {modules.length === 1 ? "module" : "modules"} registered
                        </span>
                      </div>

                      {modules.length === 0 ? (
                        <div style={{ fontSize: "0.8125rem", color: "var(--text-muted)", fontStyle: "italic", padding: "0.5rem 0" }}>
                          No granular modules registered for this product. Access is granted at product-level.
                        </div>
                      ) : (
                        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.75rem" }}>
                          {modules.map((mod) => {
                            const isEnabled = selectedModuleIds.includes(mod.id);
                            const isEntitled = mod.is_entitled;

                            return (
                              <div
                                key={mod.id}
                                onClick={() => isEntitled && handleToggleModule(mod.id)}
                                style={{
                                  padding: "0.75rem 1rem",
                                  borderRadius: "8px",
                                  border: isEnabled
                                    ? "1px solid var(--brand-primary)"
                                    : "1px solid var(--border-subtle)",
                                  backgroundColor: isEnabled
                                    ? "var(--brand-primary-light)"
                                    : "var(--glass-surface-sunken)",
                                  display: "flex",
                                  alignItems: "center",
                                  justifyContent: "space-between",
                                  cursor: isEntitled ? "pointer" : "not-allowed",
                                  opacity: isEntitled ? 1 : 0.5,
                                  transition: "all 0.12s ease",
                                }}
                              >
                                <div style={{ display: "flex", alignItems: "center", gap: "0.6rem" }}>
                                  <input
                                    type="checkbox"
                                    checked={isEnabled}
                                    disabled={!isEntitled}
                                    onChange={() => handleToggleModule(mod.id)}
                                    onClick={(e) => e.stopPropagation()}
                                    style={{ accentColor: "var(--brand-primary)", cursor: isEntitled ? "pointer" : "not-allowed" }}
                                  />
                                  <div>
                                    <div style={{ fontWeight: 600, fontSize: "0.84375rem", color: "var(--text-primary)" }}>
                                      {mod.name}
                                    </div>
                                    <div style={{ fontSize: "0.6875rem", color: "var(--text-muted)", fontFamily: "var(--font-code, monospace)" }}>
                                      {mod.code}
                                    </div>
                                  </div>
                                </div>
                                <span
                                  style={{
                                    fontSize: "0.6875rem",
                                    fontWeight: 700,
                                    padding: "0.15rem 0.45rem",
                                    borderRadius: "4px",
                                    backgroundColor: isEnabled
                                      ? "var(--brand-primary-light)"
                                      : !isEntitled
                                      ? "var(--status-danger-bg)"
                                      : "var(--border-subtle)",
                                    color: isEnabled
                                      ? "var(--brand-primary)"
                                      : !isEntitled
                                      ? "var(--status-danger)"
                                      : "var(--text-muted)",
                                  }}
                                >
                                  {isEnabled ? "Enabled" : !isEntitled ? "Not Entitled" : "Off"}
                                </span>
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

            {/* Bottom Actions */}
            <div style={{ display: "flex", justifyContent: "space-between", paddingTop: "0.5rem" }}>
              <button
                type="button"
                onClick={() => setCurrentStep("products")}
                className="btn btn-secondary"
                style={{ padding: "0.625rem 1.25rem", minHeight: "42px" }}
              >
                ← Back
              </button>
              <button
                type="submit"
                className="btn btn-primary"
                style={{
                  padding: "0.625rem 1.5rem",
                  minHeight: "42px",
                  fontSize: "0.875rem",
                  fontWeight: 600,
                }}
              >
                Review Configuration →
              </button>
            </div>
          </form>
        )}

        {/* =================================================================== */}
        {/* STEP 5: REVIEW & PROVISION                                          */}
        {/* =================================================================== */}
        {currentStep === "review" && (
          <div
            className="glass-panel"
            style={{
              padding: "2.5rem",
              borderRadius: "16px",
              border: "1px solid var(--border-glass)",
              backgroundColor: "var(--glass-surface-elevated)",
              boxShadow: "var(--shadow-md)",
              display: "flex",
              flexDirection: "column",
              gap: "2rem",
            }}
          >
            {/* Step Header */}
            <div>
              <span
                style={{
                  display: "inline-block",
                  padding: "0.2rem 0.6rem",
                  borderRadius: "6px",
                  fontSize: "0.6875rem",
                  fontWeight: 700,
                  letterSpacing: "0.06em",
                  textTransform: "uppercase",
                  backgroundColor: "var(--brand-primary-light)",
                  color: "var(--brand-primary)",
                  marginBottom: "0.5rem",
                }}
              >
                Step 05 of 05
              </span>
              <h2 style={{ fontSize: "1.375rem", fontWeight: 800, margin: "0 0 0.35rem 0", letterSpacing: "-0.02em", color: "var(--text-primary)" }}>
                Step 5: Review & Provision Member
              </h2>
              <p style={{ color: "var(--text-muted)", fontSize: "0.875rem", margin: 0, lineHeight: 1.5 }}>
                Verify the complete member configuration before provisioning. Account creation, role assignment, and entitlement provisioning will execute atomically.
              </p>
            </div>

            {/* Review Bento Cards Grid */}
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1.25rem" }}>
              {/* Card 1: Identity & Organization */}
              <div
                className="glass-panel"
                style={{
                  padding: "1.5rem",
                  borderRadius: "12px",
                  border: "1px solid var(--border-glass)",
                  backgroundColor: "var(--glass-surface)",
                  boxShadow: "var(--shadow-sm)",
                }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: "0.6rem", marginBottom: "1rem" }}>
                  <div
                    style={{
                      width: "32px",
                      height: "32px",
                      borderRadius: "8px",
                      backgroundColor: "var(--brand-primary-light)",
                      color: "var(--brand-primary)",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                    }}
                  >
                    <UserIcon size={16} />
                  </div>
                  <span style={{ fontWeight: 700, fontSize: "0.9375rem", color: "var(--text-primary)" }}>
                    Member Identity & Organization
                  </span>
                </div>
                <div style={{ display: "flex", flexDirection: "column", gap: "0.6rem", fontSize: "0.875rem" }}>
                  <div style={{ display: "flex", justifyContent: "space-between" }}>
                    <span style={{ color: "var(--text-muted)" }}>Full Name:</span>
                    <strong style={{ color: "var(--text-primary)" }}>{fullName}</strong>
                  </div>
                  <div style={{ display: "flex", justifyContent: "space-between" }}>
                    <span style={{ color: "var(--text-muted)" }}>Email:</span>
                    <strong style={{ color: "var(--text-primary)" }}>{email}</strong>
                  </div>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <span style={{ color: "var(--text-muted)" }}>Tenant Partition:</span>
                    <span style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
                      <strong style={{ color: "var(--text-primary)" }}>{activeTenant?.name}</strong>
                      <span
                        style={{
                          fontSize: "0.6875rem",
                          fontFamily: "var(--font-code, monospace)",
                          padding: "0.1rem 0.4rem",
                          borderRadius: "4px",
                          backgroundColor: "var(--border-subtle)",
                          color: "var(--text-secondary)",
                        }}
                      >
                        {activeTenant?.code}
                      </span>
                    </span>
                  </div>
                </div>
              </div>

              {/* Card 2: Role & Privileges */}
              <div
                className="glass-panel"
                style={{
                  padding: "1.5rem",
                  borderRadius: "12px",
                  border: "1px solid var(--border-glass)",
                  backgroundColor: "var(--glass-surface)",
                  boxShadow: "var(--shadow-sm)",
                }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: "0.6rem", marginBottom: "1rem" }}>
                  <div
                    style={{
                      width: "32px",
                      height: "32px",
                      borderRadius: "8px",
                      backgroundColor: "var(--brand-primary-light)",
                      color: "var(--brand-primary)",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                    }}
                  >
                    <ShieldCheckIcon size={16} />
                  </div>
                  <span style={{ fontWeight: 700, fontSize: "0.9375rem", color: "var(--text-primary)" }}>
                    Assigned Role & Privileges
                  </span>
                </div>
                <div style={{ display: "flex", flexDirection: "column", gap: "0.6rem", fontSize: "0.875rem" }}>
                  <div style={{ display: "flex", justifyContent: "space-between" }}>
                    <span style={{ color: "var(--text-muted)" }}>Membership Type:</span>
                    <span
                      className="badge"
                      style={{
                        backgroundColor: roleMode === "standard" ? "var(--border-subtle)" : "var(--brand-primary-light)",
                        color: roleMode === "standard" ? "var(--text-secondary)" : "var(--brand-primary)",
                        fontWeight: 600,
                      }}
                    >
                      {roleMode === "standard" ? "Standard Member" : "Tenant Administrator"}
                    </span>
                  </div>
                  <div style={{ display: "flex", justifyContent: "space-between" }}>
                    <span style={{ color: "var(--text-muted)" }}>Role:</span>
                    <strong style={{ color: "var(--text-primary)" }}>
                      {roleMode === "standard" ? "None (Standard User)" : selectedRole?.name || "Administrative Role"}
                    </strong>
                  </div>
                  {selectedRole && (
                    <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.78125rem", color: "var(--text-muted)", marginTop: "0.2rem" }}>
                      <span>Code: <code style={{ color: "var(--text-secondary)" }}>{selectedRole.code}</code></span>
                      <span style={{ color: "var(--brand-primary)", fontWeight: 600 }}>
                        {selectedRole.permission_keys?.length || 0} permissions grantable
                      </span>
                    </div>
                  )}
                </div>
              </div>
            </div>

            {/* Card 3: Products & Modules Assigned */}
            <div
              className="glass-panel"
              style={{
                padding: "1.5rem",
                borderRadius: "12px",
                border: "1px solid var(--border-glass)",
                backgroundColor: "var(--glass-surface)",
                boxShadow: "var(--shadow-sm)",
              }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1rem" }}>
                <div style={{ display: "flex", alignItems: "center", gap: "0.6rem" }}>
                  <div
                    style={{
                      width: "32px",
                      height: "32px",
                      borderRadius: "8px",
                      backgroundColor: "var(--brand-primary-light)",
                      color: "var(--brand-primary)",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                    }}
                  >
                    <BoxIcon size={16} />
                  </div>
                  <span style={{ fontWeight: 700, fontSize: "0.9375rem", color: "var(--text-primary)" }}>
                    Product & Feature Allocations
                  </span>
                </div>
                <span className="badge" style={{ backgroundColor: "var(--brand-primary-light)", color: "var(--brand-primary)", fontWeight: 600 }}>
                  {selectedProducts.length} Products, {selectedModuleIds.length} Modules
                </span>
              </div>

              {selectedProducts.length === 0 ? (
                <div style={{ fontSize: "0.875rem", color: "var(--text-muted)", padding: "0.5rem 0" }}>
                  No products or modules assigned. Member will be provisioned without direct product entitlements.
                </div>
              ) : (
                <div style={{ display: "flex", flexDirection: "column", gap: "0.875rem" }}>
                  {selectedProducts.map((p) => {
                    const modules = productModulesMap[p.id] || [];
                    const activeMods = modules.filter((m) => selectedModuleIds.includes(m.id));

                    return (
                      <div
                        key={p.id}
                        style={{
                          padding: "1rem 1.25rem",
                          borderRadius: "10px",
                          backgroundColor: "var(--glass-surface-sunken)",
                          border: "1px solid var(--border-subtle)",
                        }}
                      >
                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "0.5rem" }}>
                          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                            <strong style={{ fontSize: "0.9375rem", color: "var(--text-primary)" }}>
                              {p.name}
                            </strong>
                            <span
                              style={{
                                fontSize: "0.6875rem",
                                fontFamily: "var(--font-code, monospace)",
                                padding: "0.1rem 0.4rem",
                                borderRadius: "4px",
                                backgroundColor: "var(--border-subtle)",
                                color: "var(--text-secondary)",
                              }}
                            >
                              {p.code}
                            </span>
                          </div>
                          <span style={{ fontSize: "0.75rem", color: "var(--brand-primary)", fontWeight: 600 }}>
                            {activeMods.length} of {modules.length} modules enabled
                          </span>
                        </div>

                        {/* LMS Selected Console display */}
                        {(p.code?.toLowerCase().includes("lms") || p.name?.toLowerCase().includes("learning")) && (
                          <div style={{ marginTop: "0.5rem", fontSize: "0.8125rem", display: "flex", alignItems: "center", gap: "0.5rem" }}>
                            <span style={{ color: "var(--text-muted)" }}>Target Console:</span>
                            <span
                              style={{
                                fontWeight: 700,
                                fontSize: "0.75rem",
                                padding: "0.15rem 0.5rem",
                                borderRadius: "4px",
                                backgroundColor: lmsConsole === "tenant_console" ? "var(--brand-primary-light)" : "var(--border-subtle)",
                                color: lmsConsole === "tenant_console" ? "var(--brand-primary)" : "var(--text-primary)",
                                border: "1px solid",
                                borderColor: lmsConsole === "tenant_console" ? "var(--brand-primary)" : "transparent",
                              }}
                            >
                              {lmsConsole === "tenant_console" ? "Tenant Console (/org-admin)" : "Normal User Console (/dashboard)"}
                            </span>
                          </div>
                        )}

                        {activeMods.length > 0 && (
                          <div style={{ display: "flex", flexWrap: "wrap", gap: "0.4rem", marginTop: "0.625rem" }}>
                            {activeMods.map((m) => (
                              <span
                                key={m.id}
                                style={{
                                  fontSize: "0.71875rem",
                                  padding: "0.2rem 0.5rem",
                                  borderRadius: "4px",
                                  backgroundColor: "var(--brand-primary-light)",
                                  color: "var(--brand-primary)",
                                  fontWeight: 500,
                                }}
                              >
                                {m.name}
                              </span>
                            ))}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>

            {/* Bottom Actions */}
            <div style={{ display: "flex", justifyContent: "space-between", paddingTop: "0.5rem" }}>
              <button
                type="button"
                onClick={() => setCurrentStep("features")}
                className="btn btn-secondary"
                disabled={isSubmitting}
                style={{ padding: "0.625rem 1.25rem", minHeight: "42px" }}
              >
                ← Back
              </button>
              <button
                type="button"
                onClick={handleProvisionMember}
                className="btn btn-primary"
                disabled={isSubmitting}
                style={{
                  padding: "0.625rem 1.75rem",
                  minHeight: "44px",
                  fontWeight: 700,
                  fontSize: "0.875rem",
                  boxShadow: "0 4px 14px rgba(99, 102, 241, 0.4)",
                }}
              >
                {isSubmitting ? (
                  <span style={{ display: "inline-flex", alignItems: "center", gap: "0.5rem" }}>
                    <RotateCcwIcon size={16} /> Provisioning Member...
                  </span>
                ) : (
                  "Confirm & Provision Member ✓"
                )}
              </button>
            </div>
          </div>
        )}
      </div>
    </AppShell>
  );
};
