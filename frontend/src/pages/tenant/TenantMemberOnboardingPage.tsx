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
        <div style={{ maxWidth: "800px", margin: "0 auto", padding: "2.5rem 1rem" }}>
          <div
            className="glass-panel"
            style={{
              padding: "2.5rem",
              textAlign: "center",
              borderRadius: "12px",
              border: "1px solid rgba(16, 185, 129, 0.3)",
              background: "linear-gradient(180deg, rgba(16, 185, 129, 0.05) 0%, rgba(0, 0, 0, 0) 100%)",
            }}
          >
            <div
              style={{
                width: "64px",
                height: "64px",
                borderRadius: "50%",
                backgroundColor: "rgba(16, 185, 129, 0.15)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                margin: "0 auto 1.5rem auto",
              }}
            >
              <CheckCircleIcon size={36} color="var(--color-success, #10b981)" />
            </div>

            <h1 style={{ fontSize: "1.75rem", fontWeight: 800, margin: "0 0 0.5rem 0", color: "var(--text-primary)" }}>
              Member Successfully Onboarded!
            </h1>
            <p style={{ color: "var(--text-muted)", fontSize: "0.95rem", maxWidth: "540px", margin: "0 auto 1.75rem auto" }}>
              <strong>{fullName}</strong> ({email}) has been provisioned under <strong>{activeTenant?.name || "your organization"}</strong> with configured role, product access, and feature permissions.
            </p>

            {activationUrl ? (
              <div
                style={{
                  padding: "1.25rem",
                  borderRadius: "8px",
                  backgroundColor: "rgba(255, 255, 255, 0.04)",
                  border: "1px solid var(--border-color)",
                  marginBottom: "2rem",
                  textAlign: "left",
                }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.5rem" }}>
                  <span style={{ fontSize: "0.8rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.05em", color: "var(--text-muted)" }}>
                    Account Activation & Invitation Link
                  </span>
                  <button
                    type="button"
                    onClick={handleCopyLink}
                    className="btn btn-secondary"
                    style={{ fontSize: "0.75rem", padding: "0.25rem 0.6rem" }}
                  >
                    {copiedLink ? "Copied! ✓" : "Copy Link"}
                  </button>
                </div>
                <div
                  style={{
                    padding: "0.6rem 0.75rem",
                    borderRadius: "4px",
                    backgroundColor: "rgba(0, 0, 0, 0.25)",
                    fontFamily: "var(--font-code, monospace)",
                    fontSize: "0.82rem",
                    color: "var(--brand-primary, #6366f1)",
                    wordBreak: "break-all",
                  }}
                >
                  {activationUrl}
                </div>
                <p style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginTop: "0.5rem", marginBottom: 0 }}>
                  This secure, single-use activation link expires in 7 days. The member can use it to set their password and activate their account.
                </p>
              </div>
            ) : null}

            <div style={{ display: "flex", gap: "0.75rem", justifyContent: "center" }}>
              <button
                type="button"
                onClick={handleResetWizard}
                className="btn btn-secondary"
                style={{ display: "inline-flex", alignItems: "center", gap: 6, padding: "0.55rem 1.1rem" }}
              >
                <PlusIcon size={14} /> Onboard Another Member
              </button>
              <button
                type="button"
                onClick={() => navigate("/tenant/users")}
                className="btn btn-primary"
                style={{ display: "inline-flex", alignItems: "center", gap: 6, padding: "0.55rem 1.1rem" }}
              >
                <UserIcon size={14} /> View Organization Members
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

  return (
    <AppShell>
      <div style={{ maxWidth: "1080px", margin: "0 auto", padding: "1.75rem 1rem" }}>
        {/* Header */}
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "1.5rem" }}>
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <UserIcon size={24} color="var(--brand-primary, #6366f1)" />
              <h1 style={{ fontSize: "1.5rem", fontWeight: 800, margin: 0, color: "var(--text-primary)" }}>
                Member Onboarding Wizard
              </h1>
            </div>
            <p style={{ color: "var(--text-muted)", fontSize: "0.88rem", marginTop: 4 }}>
              Provision member identity, role configuration, product entitlements, and feature permissions in a unified workflow.
            </p>
          </div>
          <Link
            to="/tenant/users"
            className="btn btn-secondary"
            style={{ fontSize: "0.82rem", textDecoration: "none" }}
          >
            ← Back to Members
          </Link>
        </div>

        {/* Global Error Banner */}
        {generalError && (
          <div
            className="glass-panel"
            style={{
              padding: "0.875rem 1.25rem",
              borderRadius: "8px",
              marginBottom: "1.5rem",
              border: "1px solid rgba(239, 68, 68, 0.4)",
              backgroundColor: "rgba(239, 68, 68, 0.08)",
              display: "flex",
              alignItems: "center",
              gap: "0.75rem",
              color: "var(--color-danger, #ef4444)",
            }}
          >
            <AlertCircleIcon size={20} />
            <span style={{ fontSize: "0.875rem" }}>{generalError}</span>
          </div>
        )}

        {/* Wizard Stepper Bar */}
        <div
          className="glass-panel"
          style={{
            padding: "0.75rem 1rem",
            borderRadius: "10px",
            marginBottom: "1.75rem",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            overflowX: "auto",
            gap: "0.5rem",
          }}
        >
          {STEPS.map((step, idx) => {
            const isActive = currentStep === step.key;
            const stepOrder: WizardStep[] = ["details", "role", "products", "features", "review"];
            const currentIdx = stepOrder.indexOf(currentStep);
            const isCompleted = currentIdx > idx;

            return (
              <div
                key={step.key}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "0.5rem",
                  padding: "0.4rem 0.75rem",
                  borderRadius: "6px",
                  backgroundColor: isActive
                    ? "rgba(99, 102, 241, 0.15)"
                    : isCompleted
                    ? "rgba(16, 185, 129, 0.1)"
                    : "transparent",
                  color: isActive
                    ? "var(--brand-primary, #6366f1)"
                    : isCompleted
                    ? "var(--color-success, #10b981)"
                    : "var(--text-muted)",
                  fontWeight: isActive ? 700 : 500,
                  fontSize: "0.85rem",
                  whiteSpace: "nowrap",
                }}
              >
                <div
                  style={{
                    width: "22px",
                    height: "22px",
                    borderRadius: "50%",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    fontSize: "0.75rem",
                    fontWeight: 700,
                    backgroundColor: isActive
                      ? "var(--brand-primary, #6366f1)"
                      : isCompleted
                      ? "var(--color-success, #10b981)"
                      : "rgba(255, 255, 255, 0.1)",
                    color: isActive || isCompleted ? "#ffffff" : "var(--text-muted)",
                  }}
                >
                  {isCompleted ? "✓" : idx + 1}
                </div>
                <span>{step.label}</span>
              </div>
            );
          })}
        </div>

        {/* =================================================================== */}
        {/* STEP 1: MEMBER DETAILS                                              */}
        {/* =================================================================== */}
        {currentStep === "details" && (
          <form onSubmit={handleNextFromDetails} className="glass-panel" style={{ padding: "2rem", display: "flex", flexDirection: "column", gap: "1.5rem" }}>
            <div>
              <h2 style={{ fontSize: "1.25rem", fontWeight: 700, margin: "0 0 0.25rem 0", color: "var(--text-primary)" }}>
                Step 1: Member Identity & Details
              </h2>
              <p style={{ color: "var(--text-muted)", fontSize: "0.875rem", margin: 0 }}>
                Enter the identity details for the new member. The account will be strictly isolated to your organization.
              </p>
            </div>

            {/* Active Tenant Context Card */}
            <div
              style={{
                padding: "1rem 1.25rem",
                borderRadius: "8px",
                backgroundColor: "rgba(99, 102, 241, 0.05)",
                border: "1px solid rgba(99, 102, 241, 0.2)",
                display: "flex",
                alignItems: "center",
                gap: "1rem",
              }}
            >
              <BuildingIcon size={24} color="var(--brand-primary, #6366f1)" />
              <div>
                <div style={{ fontSize: "0.75rem", textTransform: "uppercase", fontWeight: 700, color: "var(--text-muted)", letterSpacing: "0.05em" }}>
                  Target Organization
                </div>
                <div style={{ fontSize: "1rem", fontWeight: 700, color: "var(--text-primary)" }}>
                  {activeTenant?.name || "Active Organization"}
                </div>
                <div style={{ fontSize: "0.75rem", color: "var(--text-secondary)", fontFamily: "var(--font-code)" }}>
                  Code: {activeTenant?.code || "TENANT"} | ID: {currentOrgId}
                </div>
              </div>
            </div>

            {/* Form Fields */}
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1.25rem" }}>
              <div>
                <label style={{ display: "block", fontSize: "0.85rem", fontWeight: 600, marginBottom: "0.35rem", color: "var(--text-primary)" }}>
                  Full Name <span style={{ color: "var(--color-danger, #ef4444)" }}>*</span>
                </label>
                <input
                  type="text"
                  placeholder="e.g. Jane Doe"
                  value={fullName}
                  onChange={(e) => setFullName(e.target.value)}
                  className="input-text"
                  style={{ width: "100%", padding: "0.6rem 0.85rem" }}
                />
                {fieldErrors.fullName && (
                  <span style={{ fontSize: "0.75rem", color: "var(--color-danger, #ef4444)", marginTop: "0.25rem", display: "block" }}>
                    {fieldErrors.fullName}
                  </span>
                )}
              </div>

              <div>
                <label style={{ display: "block", fontSize: "0.85rem", fontWeight: 600, marginBottom: "0.35rem", color: "var(--text-primary)" }}>
                  Email Address <span style={{ color: "var(--color-danger, #ef4444)" }}>*</span>
                </label>
                <input
                  type="email"
                  placeholder="e.g. jane.doe@company.com"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="input-text"
                  style={{ width: "100%", padding: "0.6rem 0.85rem" }}
                />
                {fieldErrors.email && (
                  <span style={{ fontSize: "0.75rem", color: "var(--color-danger, #ef4444)", marginTop: "0.25rem", display: "block" }}>
                    {fieldErrors.email}
                  </span>
                )}
              </div>
            </div>

            <div
              style={{
                padding: "0.85rem 1rem",
                borderRadius: "6px",
                backgroundColor: "rgba(255, 255, 255, 0.03)",
                border: "1px solid var(--border-color)",
                fontSize: "0.8rem",
                color: "var(--text-muted)",
              }}
            >
              🔒 <strong>Security Policy:</strong> In accordance with zero hardcoding and secure credential policies, user creation is atomic and deferred until final provisioning in Step 5. No plain-text passwords are handled.
            </div>

            <div style={{ display: "flex", justifyContent: "flex-end", marginTop: "0.5rem" }}>
              <button type="submit" className="btn btn-primary" style={{ padding: "0.55rem 1.25rem" }}>
                Continue to Role Configuration →
              </button>
            </div>
          </form>
        )}

        {/* =================================================================== */}
        {/* STEP 2: ROLE CONFIGURATION                                          */}
        {/* =================================================================== */}
        {currentStep === "role" && (
          <form onSubmit={handleNextFromRole} className="glass-panel" style={{ padding: "2rem", display: "flex", flexDirection: "column", gap: "1.5rem" }}>
            <div>
              <h2 style={{ fontSize: "1.25rem", fontWeight: 700, margin: "0 0 0.25rem 0", color: "var(--text-primary)" }}>
                Step 2: Role & Permissions Setup
              </h2>
              <p style={{ color: "var(--text-muted)", fontSize: "0.875rem", margin: 0 }}>
                Configure whether this member operates as a standard member or has administrative role assignments. You can also create a new tenant-scoped custom role inline.
              </p>
            </div>

            {roleCreationSuccess && (
              <div
                style={{
                  padding: "0.75rem 1rem",
                  borderRadius: "6px",
                  backgroundColor: "rgba(16, 185, 129, 0.1)",
                  border: "1px solid rgba(16, 185, 129, 0.3)",
                  color: "var(--color-success, #10b981)",
                  fontSize: "0.85rem",
                  display: "flex",
                  alignItems: "center",
                  gap: 8,
                }}
              >
                <CheckCircleIcon size={16} />
                <span>{roleCreationSuccess}</span>
              </div>
            )}

            {/* Role Mode Selection Cards */}
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: "1rem" }}>
              {/* Option A: Standard Member */}
              <div
                onClick={() => {
                  setRoleMode("standard");
                  setSelectedRoleId("");
                  setFieldErrors({});
                }}
                className="glass-panel"
                style={{
                  padding: "1.25rem",
                  borderRadius: "8px",
                  cursor: "pointer",
                  border: roleMode === "standard"
                    ? "2px solid var(--brand-primary, #6366f1)"
                    : "1px solid var(--border-color)",
                  backgroundColor: roleMode === "standard"
                    ? "rgba(99, 102, 241, 0.08)"
                    : "transparent",
                  transition: "all 0.15s ease",
                }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.5rem" }}>
                  <input
                    type="radio"
                    name="roleMode"
                    checked={roleMode === "standard"}
                    onChange={() => {
                      setRoleMode("standard");
                      setSelectedRoleId("");
                    }}
                  />
                  <span style={{ fontWeight: 700, fontSize: "0.95rem", color: "var(--text-primary)" }}>
                    Standard Member
                  </span>
                </div>
                <p style={{ fontSize: "0.8rem", color: "var(--text-muted)", margin: 0 }}>
                  Standard end-user access. User will only access assigned products and consumer workspace, with no tenant administration privileges.
                </p>
              </div>

              {/* Option B: Assign Existing Role */}
              <div
                onClick={() => {
                  setRoleMode("existing");
                  setFieldErrors({});
                }}
                className="glass-panel"
                style={{
                  padding: "1.25rem",
                  borderRadius: "8px",
                  cursor: "pointer",
                  border: roleMode === "existing"
                    ? "2px solid var(--brand-primary, #6366f1)"
                    : "1px solid var(--border-color)",
                  backgroundColor: roleMode === "existing"
                    ? "rgba(99, 102, 241, 0.08)"
                    : "transparent",
                  transition: "all 0.15s ease",
                }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.5rem" }}>
                  <input
                    type="radio"
                    name="roleMode"
                    checked={roleMode === "existing"}
                    onChange={() => setRoleMode("existing")}
                  />
                  <span style={{ fontWeight: 700, fontSize: "0.95rem", color: "var(--text-primary)" }}>
                    Assign Existing Role
                  </span>
                </div>
                <p style={{ fontSize: "0.8rem", color: "var(--text-muted)", margin: 0 }}>
                  Assign an existing administrative role (Tenant Administrator, Support Manager, etc.) with preconfigured permission sets.
                </p>
              </div>

              {/* Option C: Create Custom Role */}
              <div
                onClick={() => {
                  setRoleMode("custom");
                  setFieldErrors({});
                }}
                className="glass-panel"
                style={{
                  padding: "1.25rem",
                  borderRadius: "8px",
                  cursor: "pointer",
                  border: roleMode === "custom"
                    ? "2px solid var(--brand-primary, #6366f1)"
                    : "1px solid var(--border-color)",
                  backgroundColor: roleMode === "custom"
                    ? "rgba(99, 102, 241, 0.08)"
                    : "transparent",
                  transition: "all 0.15s ease",
                }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.5rem" }}>
                  <input
                    type="radio"
                    name="roleMode"
                    checked={roleMode === "custom"}
                    onChange={() => setRoleMode("custom")}
                  />
                  <span style={{ fontWeight: 700, fontSize: "0.95rem", color: "var(--text-primary)" }}>
                    + Create Custom Role
                  </span>
                </div>
                <p style={{ fontSize: "0.8rem", color: "var(--text-muted)", margin: 0 }}>
                  Define a new custom organization role with granular permission toggles and associate it directly with this member.
                </p>
              </div>
            </div>

            {/* Details for Option B: Existing Roles Selector */}
            {roleMode === "existing" && (
              <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
                <h3 style={{ fontSize: "0.95rem", fontWeight: 700, margin: 0, color: "var(--text-primary)" }}>
                  Select Administrative Role
                </h3>
                {isLoadingRoles ? (
                  <LoadingSpinner label="Loading roles..." />
                ) : availableRoles.length === 0 ? (
                  <div style={{ fontSize: "0.85rem", color: "var(--text-muted)" }}>
                    No administrative roles available. Use "+ Create Custom Role" above.
                  </div>
                ) : (
                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.75rem" }}>
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
                            padding: "1rem",
                            borderRadius: "8px",
                            cursor: "pointer",
                            border: isSelected
                              ? "2px solid var(--brand-primary, #6366f1)"
                              : "1px solid var(--border-color)",
                            backgroundColor: isSelected
                              ? "rgba(99, 102, 241, 0.08)"
                              : "transparent",
                          }}
                        >
                          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                            <span style={{ fontWeight: 700, fontSize: "0.9rem", color: "var(--text-primary)" }}>
                              {role.name}
                            </span>
                            <span style={{ fontSize: "0.7rem", fontFamily: "var(--font-code)", color: "var(--text-muted)" }}>
                              {role.code}
                            </span>
                          </div>
                          <p style={{ fontSize: "0.78rem", color: "var(--text-secondary)", margin: "0.35rem 0" }}>
                            {role.description || "Administrative role for tenant operations."}
                          </p>
                          <div style={{ fontSize: "0.72rem", color: "var(--brand-primary, #6366f1)", fontWeight: 600 }}>
                            {role.permission_keys?.length || 0} permissions included
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
                {fieldErrors.selectedRole && (
                  <span style={{ fontSize: "0.75rem", color: "var(--color-danger, #ef4444)" }}>
                    {fieldErrors.selectedRole}
                  </span>
                )}
              </div>
            )}

            {/* Details for Option C: Inline Role Creation */}
            {roleMode === "custom" && (
              <div
                style={{
                  padding: "1.25rem",
                  borderRadius: "8px",
                  backgroundColor: "rgba(255, 255, 255, 0.02)",
                  border: "1px solid var(--border-color)",
                  display: "flex",
                  flexDirection: "column",
                  gap: "1rem",
                }}
              >
                <h3 style={{ fontSize: "0.95rem", fontWeight: 700, margin: 0, color: "var(--text-primary)" }}>
                  Create New Tenant-Scoped Custom Role
                </h3>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem" }}>
                  <div>
                    <label style={{ display: "block", fontSize: "0.8rem", fontWeight: 600, marginBottom: "0.25rem" }}>
                      Role Name *
                    </label>
                    <input
                      type="text"
                      placeholder="e.g. Course Reviewer"
                      value={newRoleName}
                      onChange={(e) => setNewRoleName(e.target.value)}
                      className="input-text"
                      style={{ width: "100%", padding: "0.5rem" }}
                    />
                    {fieldErrors.newRoleName && (
                      <span style={{ fontSize: "0.75rem", color: "var(--color-danger, #ef4444)" }}>
                        {fieldErrors.newRoleName}
                      </span>
                    )}
                  </div>
                  <div>
                    <label style={{ display: "block", fontSize: "0.8rem", fontWeight: 600, marginBottom: "0.25rem" }}>
                      Role Code *
                    </label>
                    <input
                      type="text"
                      placeholder="e.g. course_reviewer"
                      value={newRoleCode}
                      onChange={(e) => setNewRoleCode(e.target.value)}
                      className="input-text"
                      style={{ width: "100%", padding: "0.5rem" }}
                    />
                    {fieldErrors.newRoleCode && (
                      <span style={{ fontSize: "0.75rem", color: "var(--color-danger, #ef4444)" }}>
                        {fieldErrors.newRoleCode}
                      </span>
                    )}
                  </div>
                </div>

                <div>
                  <label style={{ display: "block", fontSize: "0.8rem", fontWeight: 600, marginBottom: "0.25rem" }}>
                    Description
                  </label>
                  <input
                    type="text"
                    placeholder="Short summary of role responsibilities"
                    value={newRoleDesc}
                    onChange={(e) => setNewRoleDesc(e.target.value)}
                    className="input-text"
                    style={{ width: "100%", padding: "0.5rem" }}
                  />
                </div>

                {/* Permissions selector */}
                <div>
                  <label style={{ display: "block", fontSize: "0.8rem", fontWeight: 600, marginBottom: "0.5rem" }}>
                    Supported Role Permissions ({newRolePermissions.length} selected)
                  </label>
                  {accessCatalog?.permissions && accessCatalog.permissions.length > 0 ? (
                    <div
                      style={{
                        maxHeight: "220px",
                        overflowY: "auto",
                        border: "1px solid var(--border-color)",
                        borderRadius: "6px",
                        padding: "0.5rem",
                        display: "grid",
                        gridTemplateColumns: "1fr 1fr",
                        gap: "0.5rem",
                      }}
                    >
                      {accessCatalog.permissions.map((p) => {
                        const isChecked = newRolePermissions.includes(p.key);
                        return (
                          <label
                            key={p.key}
                            style={{
                              display: "flex",
                              alignItems: "center",
                              gap: "0.5rem",
                              fontSize: "0.78rem",
                              cursor: "pointer",
                              padding: "0.25rem 0.5rem",
                              borderRadius: "4px",
                              backgroundColor: isChecked ? "rgba(99, 102, 241, 0.1)" : "transparent",
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
                            />
                            <div>
                              <div style={{ fontWeight: 600 }}>{p.display_name}</div>
                              <div style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>{p.key}</div>
                            </div>
                          </label>
                        );
                      })}
                    </div>
                  ) : (
                    <div style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>
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
                    style={{ padding: "0.45rem 0.9rem", fontSize: "0.82rem" }}
                  >
                    {isCreatingRole ? "Creating Role..." : "Create & Select Role"}
                  </button>
                </div>
                {fieldErrors.customRole && (
                  <span style={{ fontSize: "0.75rem", color: "var(--color-danger, #ef4444)" }}>
                    {fieldErrors.customRole}
                  </span>
                )}
              </div>
            )}

            <div style={{ display: "flex", justifyContent: "space-between", marginTop: "0.5rem" }}>
              <button
                type="button"
                onClick={() => setCurrentStep("details")}
                className="btn btn-secondary"
                style={{ padding: "0.55rem 1.25rem" }}
              >
                ← Back
              </button>
              <button type="submit" className="btn btn-primary" style={{ padding: "0.55rem 1.25rem" }}>
                Continue to Product Access →
              </button>
            </div>
          </form>
        )}

        {/* =================================================================== */}
        {/* STEP 3: PRODUCT ACCESS                                              */}
        {/* =================================================================== */}
        {currentStep === "products" && (
          <form onSubmit={handleNextFromProducts} className="glass-panel" style={{ padding: "2rem", display: "flex", flexDirection: "column", gap: "1.5rem" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
              <div>
                <h2 style={{ fontSize: "1.25rem", fontWeight: 700, margin: "0 0 0.25rem 0", color: "var(--text-primary)" }}>
                  Step 3: Product Access & Entitlements
                </h2>
                <p style={{ color: "var(--text-muted)", fontSize: "0.875rem", margin: 0 }}>
                  Select which entitled products this member can access. Only products entitled to your organization are displayed.
                </p>
              </div>
              {entitledProducts.length > 0 && (
                <div style={{ display: "flex", gap: "0.5rem" }}>
                  <button
                    type="button"
                    onClick={() => setSelectedProductIds(entitledProducts.map((p) => p.id))}
                    className="btn btn-secondary"
                    style={{ fontSize: "0.75rem", padding: "0.3rem 0.6rem" }}
                  >
                    Select All
                  </button>
                  <button
                    type="button"
                    onClick={() => setSelectedProductIds([])}
                    className="btn btn-secondary"
                    style={{ fontSize: "0.75rem", padding: "0.3rem 0.6rem" }}
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
                  padding: "2rem",
                  textAlign: "center",
                  borderRadius: "8px",
                  border: "1px dashed var(--border-color)",
                  color: "var(--text-muted)",
                }}
              >
                <BoxIcon size={32} style={{ margin: "0 auto 0.75rem auto", opacity: 0.6 }} />
                <p style={{ margin: 0, fontWeight: 600 }}>No Entitled Products Available</p>
                <p style={{ fontSize: "0.8rem", marginTop: 4 }}>
                  Your organization does not currently hold active product entitlements. Please contact Platform Support to request product access.
                </p>
              </div>
            ) : (
              <div style={{ display: "grid", gridTemplateColumns: "1fr", gap: "0.85rem" }}>
                {entitledProducts.map((prod) => {
                  const isSelected = selectedProductIds.includes(prod.id);
                  const isFull = !prod.is_capacity_available && prod.quota_type === "numeric";

                  return (
                    <div
                      key={prod.id}
                      onClick={() => !isFull && handleToggleProduct(prod.id)}
                      className="glass-panel"
                      style={{
                        padding: "1.1rem 1.25rem",
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "space-between",
                        cursor: isFull ? "not-allowed" : "pointer",
                        opacity: isFull ? 0.6 : 1,
                        border: isSelected
                          ? "2px solid var(--brand-primary, #6366f1)"
                          : "1px solid var(--border-color)",
                        backgroundColor: isSelected
                          ? "rgba(99, 102, 241, 0.08)"
                          : "transparent",
                        borderRadius: "8px",
                        transition: "all 0.15s ease",
                      }}
                    >
                      <div style={{ display: "flex", alignItems: "flex-start", gap: "1rem" }}>
                        <input
                          type="checkbox"
                          checked={isSelected}
                          disabled={isFull}
                          onChange={() => handleToggleProduct(prod.id)}
                          onClick={(e) => e.stopPropagation()}
                          style={{ marginTop: "0.25rem", width: "16px", height: "16px", cursor: isFull ? "not-allowed" : "pointer" }}
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
                          <p style={{ margin: "0.25rem 0 0 0", fontSize: "0.8rem", color: "var(--text-secondary)" }}>
                            Quota: {prod.quota_type === "unlimited" ? "Unlimited seats" : `${prod.consumed_seats} / ${prod.total_limit} seats assigned`}
                          </p>
                        </div>
                      </div>

                      <div style={{ textAlign: "right" }}>
                        <div
                          style={{
                            fontSize: "0.8rem",
                            fontWeight: 700,
                            color: isSelected
                              ? "var(--brand-primary, #6366f1)"
                              : isFull
                              ? "var(--color-danger, #ef4444)"
                              : "var(--text-muted)",
                          }}
                        >
                          {isSelected ? "Assigned ✓" : isFull ? "Capacity Reached" : "Disabled"}
                        </div>
                        {prod.available_seats !== null && (
                          <div style={{ fontSize: "0.72rem", color: "var(--text-muted)", marginTop: 2 }}>
                            {prod.available_seats} {prod.available_seats === 1 ? "seat" : "seats"} left
                          </div>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}

            <div style={{ display: "flex", justifyContent: "space-between", marginTop: "0.5rem" }}>
              <button
                type="button"
                onClick={() => setCurrentStep("role")}
                className="btn btn-secondary"
                style={{ padding: "0.55rem 1.25rem" }}
              >
                ← Back
              </button>
              <button type="submit" className="btn btn-primary" style={{ padding: "0.55rem 1.25rem" }}>
                Continue to Console Feature Access →
              </button>
            </div>
          </form>
        )}

        {/* =================================================================== */}
        {/* STEP 4: CONSOLE FEATURE ACCESS                                      */}
        {/* =================================================================== */}
        {currentStep === "features" && (
          <form onSubmit={handleNextFromFeatures} className="glass-panel" style={{ padding: "2rem", display: "flex", flexDirection: "column", gap: "1.5rem" }}>
            <div>
              <h2 style={{ fontSize: "1.25rem", fontWeight: 700, margin: "0 0 0.25rem 0", color: "var(--text-primary)" }}>
                Step 4: Console Feature & Module Access
              </h2>
              <p style={{ color: "var(--text-muted)", fontSize: "0.875rem", margin: 0 }}>
                Configure individual product module permissions for the selected products. Member access is strictly bounded by your organization&apos;s feature ceilings.
              </p>
            </div>

            {selectedProducts.length === 0 ? (
              <div
                style={{
                  padding: "2rem",
                  textAlign: "center",
                  borderRadius: "8px",
                  border: "1px dashed var(--border-color)",
                  color: "var(--text-muted)",
                }}
              >
                <LayersIcon size={32} style={{ margin: "0 auto 0.75rem auto", opacity: 0.6 }} />
                <p style={{ margin: 0, fontWeight: 600 }}>No Products Selected</p>
                <p style={{ fontSize: "0.8rem", marginTop: 4 }}>
                  Return to Step 3 if you wish to assign products and configure their respective modules.
                </p>
                <button
                  type="button"
                  onClick={() => setCurrentStep("products")}
                  className="btn btn-secondary"
                  style={{ marginTop: "1rem", fontSize: "0.8rem" }}
                >
                  ← Go to Step 3: Product Access
                </button>
              </div>
            ) : isLoadingModules ? (
              <LoadingSpinner label="Loading product feature modules..." />
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>
                {selectedProducts.map((prod) => {
                  const modules = productModulesMap[prod.id] || [];

                  return (
                    <div
                      key={prod.id}
                      className="glass-panel"
                      style={{
                        padding: "1.25rem",
                        borderRadius: "8px",
                        border: "1px solid var(--border-color)",
                      }}
                    >
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.75rem" }}>
                        <div>
                          <span style={{ fontWeight: 700, fontSize: "0.95rem", color: "var(--text-primary)" }}>
                            {prod.name}
                          </span>
                          <span
                            style={{
                              marginLeft: "0.5rem",
                              fontSize: "0.7rem",
                              padding: "0.1rem 0.4rem",
                              borderRadius: "4px",
                              backgroundColor: "rgba(255, 255, 255, 0.08)",
                              fontFamily: "var(--font-code)",
                              color: "var(--text-muted)",
                            }}
                          >
                            {prod.code}
                          </span>
                        </div>
                        <span style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
                          {modules.length} {modules.length === 1 ? "module" : "modules"} available
                        </span>
                      </div>

                      {modules.length === 0 ? (
                        <div style={{ fontSize: "0.8rem", color: "var(--text-muted)", fontStyle: "italic" }}>
                          No granular modules registered for this product. Access is granted at product-level.
                        </div>
                      ) : (
                        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.6rem" }}>
                          {modules.map((mod) => {
                            const isEnabled = selectedModuleIds.includes(mod.id);
                            const isEntitled = mod.is_entitled;

                            return (
                              <div
                                key={mod.id}
                                onClick={() => isEntitled && handleToggleModule(mod.id)}
                                style={{
                                  padding: "0.6rem 0.75rem",
                                  borderRadius: "6px",
                                  border: isEnabled
                                    ? "1px solid var(--brand-primary, #6366f1)"
                                    : "1px solid var(--border-color)",
                                  backgroundColor: isEnabled
                                    ? "rgba(99, 102, 241, 0.08)"
                                    : "rgba(255, 255, 255, 0.02)",
                                  display: "flex",
                                  alignItems: "center",
                                  justifyContent: "space-between",
                                  cursor: isEntitled ? "pointer" : "not-allowed",
                                  opacity: isEntitled ? 1 : 0.5,
                                }}
                              >
                                <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                                  <input
                                    type="checkbox"
                                    checked={isEnabled}
                                    disabled={!isEntitled}
                                    onChange={() => handleToggleModule(mod.id)}
                                    onClick={(e) => e.stopPropagation()}
                                  />
                                  <div>
                                    <div style={{ fontWeight: 600, fontSize: "0.82rem", color: "var(--text-primary)" }}>
                                      {mod.name}
                                    </div>
                                    <div style={{ fontSize: "0.7rem", color: "var(--text-muted)" }}>
                                      {mod.code}
                                    </div>
                                  </div>
                                </div>
                                <span
                                  style={{
                                    fontSize: "0.7rem",
                                    fontWeight: 600,
                                    color: isEnabled
                                      ? "var(--brand-primary, #6366f1)"
                                      : !isEntitled
                                      ? "var(--color-danger, #ef4444)"
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

            <div style={{ display: "flex", justifyContent: "space-between", marginTop: "0.5rem" }}>
              <button
                type="button"
                onClick={() => setCurrentStep("products")}
                className="btn btn-secondary"
                style={{ padding: "0.55rem 1.25rem" }}
              >
                ← Back
              </button>
              <button type="submit" className="btn btn-primary" style={{ padding: "0.55rem 1.25rem" }}>
                Review Configuration →
              </button>
            </div>
          </form>
        )}

        {/* =================================================================== */}
        {/* STEP 5: REVIEW & PROVISION                                          */}
        {/* =================================================================== */}
        {currentStep === "review" && (
          <div className="glass-panel" style={{ padding: "2rem", display: "flex", flexDirection: "column", gap: "1.5rem" }}>
            <div>
              <h2 style={{ fontSize: "1.25rem", fontWeight: 700, margin: "0 0 0.25rem 0", color: "var(--text-primary)" }}>
                Step 5: Review & Provision Member
              </h2>
              <p style={{ color: "var(--text-muted)", fontSize: "0.875rem", margin: 0 }}>
                Verify the complete member configuration before provisioning. Account creation, role assignment, and entitlement provisioning will execute atomically.
              </p>
            </div>

            {/* Review Cards Grid */}
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1.25rem" }}>
              {/* Card 1: Identity & Organization */}
              <div
                className="glass-panel"
                style={{
                  padding: "1.25rem",
                  borderRadius: "8px",
                  border: "1px solid var(--border-color)",
                }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.75rem" }}>
                  <UserIcon size={18} color="var(--brand-primary, #6366f1)" />
                  <span style={{ fontWeight: 700, fontSize: "0.95rem", color: "var(--text-primary)" }}>
                    Member Identity & Organization
                  </span>
                </div>
                <div style={{ display: "flex", flexDirection: "column", gap: "0.4rem", fontSize: "0.85rem" }}>
                  <div>
                    <span style={{ color: "var(--text-muted)" }}>Full Name: </span>
                    <strong style={{ color: "var(--text-primary)" }}>{fullName}</strong>
                  </div>
                  <div>
                    <span style={{ color: "var(--text-muted)" }}>Email: </span>
                    <strong style={{ color: "var(--text-primary)" }}>{email}</strong>
                  </div>
                  <div>
                    <span style={{ color: "var(--text-muted)" }}>Tenant Organization: </span>
                    <strong style={{ color: "var(--text-primary)" }}>{activeTenant?.name}</strong>{" "}
                    <span style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>({activeTenant?.code})</span>
                  </div>
                </div>
              </div>

              {/* Card 2: Role & Privileges */}
              <div
                className="glass-panel"
                style={{
                  padding: "1.25rem",
                  borderRadius: "8px",
                  border: "1px solid var(--border-color)",
                }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.75rem" }}>
                  <ShieldCheckIcon size={18} color="var(--brand-primary, #6366f1)" />
                  <span style={{ fontWeight: 700, fontSize: "0.95rem", color: "var(--text-primary)" }}>
                    Assigned Role & Privileges
                  </span>
                </div>
                <div style={{ display: "flex", flexDirection: "column", gap: "0.4rem", fontSize: "0.85rem" }}>
                  <div>
                    <span style={{ color: "var(--text-muted)" }}>Membership Type: </span>
                    <strong style={{ color: "var(--text-primary)" }}>
                      {roleMode === "standard" ? "Standard Member" : "Tenant Administrator"}
                    </strong>
                  </div>
                  <div>
                    <span style={{ color: "var(--text-muted)" }}>Role: </span>
                    <strong style={{ color: "var(--text-primary)" }}>
                      {roleMode === "standard" ? "None (Standard User)" : selectedRole?.name || "Administrative Role"}
                    </strong>
                  </div>
                  {selectedRole && (
                    <div style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
                      Code: {selectedRole.code} | {selectedRole.permission_keys?.length || 0} permissions grantable
                    </div>
                  )}
                </div>
              </div>
            </div>

            {/* Card 3: Products & Modules Assigned */}
            <div
              className="glass-panel"
              style={{
                padding: "1.25rem",
                borderRadius: "8px",
                border: "1px solid var(--border-color)",
              }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.75rem" }}>
                <BoxIcon size={18} color="var(--brand-primary, #6366f1)" />
                <span style={{ fontWeight: 700, fontSize: "0.95rem", color: "var(--text-primary)" }}>
                  Product & Feature Allocations ({selectedProducts.length} Products, {selectedModuleIds.length} Feature Modules)
                </span>
              </div>
              {selectedProducts.length === 0 ? (
                <div style={{ fontSize: "0.85rem", color: "var(--text-muted)" }}>
                  No products or modules assigned. Member will be provisioned without direct product entitlements.
                </div>
              ) : (
                <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
                  {selectedProducts.map((p) => {
                    const modules = productModulesMap[p.id] || [];
                    const activeMods = modules.filter((m) => selectedModuleIds.includes(m.id));

                    return (
                      <div
                        key={p.id}
                        style={{
                          padding: "0.75rem",
                          borderRadius: "6px",
                          backgroundColor: "rgba(255, 255, 255, 0.02)",
                          border: "1px solid var(--border-color)",
                        }}
                      >
                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                          <span style={{ fontWeight: 700, fontSize: "0.88rem", color: "var(--text-primary)" }}>
                            {p.name} ({p.code})
                          </span>
                          <span style={{ fontSize: "0.75rem", color: "var(--brand-primary, #6366f1)", fontWeight: 600 }}>
                            {activeMods.length} of {modules.length} modules enabled
                          </span>
                        </div>
                        {activeMods.length > 0 && (
                          <div style={{ display: "flex", flexWrap: "wrap", gap: "0.35rem", marginTop: "0.5rem" }}>
                            {activeMods.map((m) => (
                              <span
                                key={m.id}
                                style={{
                                  fontSize: "0.72rem",
                                  padding: "0.15rem 0.45rem",
                                  borderRadius: "4px",
                                  backgroundColor: "rgba(99, 102, 241, 0.12)",
                                  color: "var(--brand-primary, #6366f1)",
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

            <div style={{ display: "flex", justifyContent: "space-between", marginTop: "0.5rem" }}>
              <button
                type="button"
                onClick={() => setCurrentStep("features")}
                className="btn btn-secondary"
                disabled={isSubmitting}
                style={{ padding: "0.55rem 1.25rem" }}
              >
                ← Back
              </button>
              <button
                type="button"
                onClick={handleProvisionMember}
                className="btn btn-primary"
                disabled={isSubmitting}
                style={{ padding: "0.6rem 1.5rem", fontWeight: 700 }}
              >
                {isSubmitting ? (
                  <span style={{ display: "inline-flex", alignItems: "center", gap: 8 }}>
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
