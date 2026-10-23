/**
 * Invite User / Member Onboarding Dialog (Phase 3C / Extended).
 *
 * Provides Platform Owners and Tenant Admins with a multi-step workflow:
 * 1. Member Details (email, membership type)
 * 2. Product Access (tenant-entitled products from selector)
 * 3. Feature Access (entitled modules/features per product constrained by ceilings)
 * 4. Review & Provision (summary, atomic invitation & pre-assignment issuance)
 */

import React, { useId, useRef, useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { assignmentsApi } from "../../api/assignments.ts";
import { invitationsApi } from "../../api/invitations.ts";
import { organizationsApi } from "../../api/organizations.ts";
import type {
  IssueInvitationResponse,
  OrganizationListItem,
  SelectorModuleItem,
  SelectorProductItem,
} from "../../api/types.ts";
import { ApiError } from "../../api/client.ts";
import {
  AlertCircleIcon,
  CheckCircleIcon,
  CloseIcon,
  CopyIcon,
  UserIcon,
} from "../Icons.tsx";
import { useDialogAccessibility } from "../plans/PlanModalShell.tsx";
import { formatDateTime } from "../../config/dateUtils.ts";

interface InviteUserDialogProps {
  readonly isOpen: boolean;
  readonly onClose: () => void;
  readonly onSuccess?: (invitation: IssueInvitationResponse) => void;
  readonly defaultOrganizationId?: string;
  readonly allowedMembershipTypes?: readonly ("member" | "admin")[];
  readonly triggerRef?: React.RefObject<HTMLElement | null>;
}

export const InviteUserDialog: React.FC<InviteUserDialogProps> = ({
  isOpen,
  onClose,
  onSuccess,
  defaultOrganizationId,
  allowedMembershipTypes,
  triggerRef,
}) => {
  const baseId = useId();
  const navigate = useNavigate();

  // Multi-step state: 1 = Details, 2 = Products, 3 = Features, 4 = Review
  const [currentStep, setCurrentStep] = useState<number>(1);

  const [organizations, setOrganizations] = useState<readonly OrganizationListItem[]>([]);
  const [selectedOrgId, setSelectedOrgId] = useState<string>(defaultOrganizationId || "");
  const [email, setEmail] = useState<string>("");
  const [membershipType, setMembershipType] = useState<string>(
    allowedMembershipTypes && allowedMembershipTypes.length > 0 ? allowedMembershipTypes[0] : "member"
  );

  // Step 2 & 3: Entitled Products & Modules State
  const [entitledProducts, setEntitledProducts] = useState<readonly SelectorProductItem[]>([]);
  const [selectedProductIds, setSelectedProductIds] = useState<string[]>([]);
  const [productModules, setProductModules] = useState<Record<string, readonly SelectorModuleItem[]>>({});
  const [selectedModuleIds, setSelectedModuleIds] = useState<string[]>([]);
  const [loadingSelectors, setLoadingSelectors] = useState<boolean>(false);

  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  const [generalError, setGeneralError] = useState<string | null>(null);
  const [errorCode, setErrorCode] = useState<string | null>(null);
  const [issuedInvitation, setIssuedInvitation] = useState<IssueInvitationResponse | null>(null);
  const [copied, setCopied] = useState<boolean>(false);

  const emailInputRef = useRef<HTMLInputElement | null>(null);

  const { dialogRef } = useDialogAccessibility({
    isOpen,
    isSubmitting,
    onClose,
    triggerRef,
    initialFocusRef: emailInputRef,
  });

  // Load organizations if not pre-provided
  useEffect(() => {
    if (!isOpen) return;

    if (defaultOrganizationId) {
      setSelectedOrgId(defaultOrganizationId);
    } else {
      void organizationsApi.list({ page_size: 100 }).then((res) => {
        setOrganizations(res.results);
        if (res.results.length > 0 && !selectedOrgId) {
          setSelectedOrgId(res.results[0].id);
        }
      }).catch(() => {
        setGeneralError("Unable to load organizations for invitation.");
      });
    }
  }, [isOpen, defaultOrganizationId, selectedOrgId]);

  // Load tenant entitled products from assignments selector
  useEffect(() => {
    if (!isOpen) return;
    setLoadingSelectors(true);
    void assignmentsApi
      .getSelectorProducts()
      .then((prods) => {
        setEntitledProducts(prods || []);
      })
      .catch(() => {
        setEntitledProducts([]);
      })
      .finally(() => {
        setLoadingSelectors(false);
      });
  }, [isOpen]);

  // Load modules when selected products change
  const fetchModulesForProduct = async (productId: string) => {
    if (productModules[productId]) return;
    try {
      const mods = await assignmentsApi.getSelectorModules(productId);
      setProductModules((prev) => ({ ...prev, [productId]: mods }));
      // Default all newly loaded modules to enabled
      const newModIds = mods.map((m) => m.id);
      setSelectedModuleIds((prev) => Array.from(new Set([...prev, ...newModIds])));
    } catch {
      // module load failure handled gracefully
    }
  };

  if (!isOpen) return null;

  const handleReset = () => {
    setCurrentStep(1);
    setEmail("");
    setMembershipType("member");
    setSelectedProductIds([]);
    setSelectedModuleIds([]);
    setGeneralError(null);
    setErrorCode(null);
    setIssuedInvitation(null);
    setCopied(false);
  };

  const handleClose = () => {
    handleReset();
    onClose();
  };

  // Step 1 -> Step 2
  const handleProceedFromDetails = (e: React.FormEvent) => {
    e.preventDefault();
    setGeneralError(null);
    const trimmedEmail = email.trim();
    if (!trimmedEmail) {
      setGeneralError("Please enter a valid email address.");
      return;
    }
    if (!/\S+@\S+\.\S+/.test(trimmedEmail)) {
      setGeneralError("Please enter a valid email address format.");
      return;
    }
    if (!selectedOrgId) {
      setGeneralError("Please select a target organization.");
      return;
    }

    if (membershipType === "admin") {
      // Skip product assignment for tenant admin invitation
      setCurrentStep(4);
    } else {
      setCurrentStep(2);
    }
  };

  // Step 2 -> Step 3
  const handleProceedFromProducts = async () => {
    setGeneralError(null);
    // Fetch modules for all selected products
    for (const pid of selectedProductIds) {
      await fetchModulesForProduct(pid);
    }
    setCurrentStep(3);
  };

  // Step 3 -> Step 4
  const handleProceedFromFeatures = () => {
    setGeneralError(null);
    setCurrentStep(4);
  };

  const handleToggleProduct = async (productId: string) => {
    const isCurrentlySelected = selectedProductIds.includes(productId);
    if (isCurrentlySelected) {
      setSelectedProductIds((prev) => prev.filter((id) => id !== productId));
      // Remove modules belonging to this product
      const modsForProd = productModules[productId] || [];
      const modIdsToRemove = new Set(modsForProd.map((m) => m.id));
      setSelectedModuleIds((prev) => prev.filter((id) => !modIdsToRemove.has(id)));
    } else {
      setSelectedProductIds((prev) => [...prev, productId]);
      await fetchModulesForProduct(productId);
    }
  };

  const handleToggleModule = (moduleId: string) => {
    setSelectedModuleIds((prev) =>
      prev.includes(moduleId) ? prev.filter((id) => id !== moduleId) : [...prev, moduleId]
    );
  };

  // Step 4: Final Provision Submit
  const handleFinalSubmit = async () => {
    setGeneralError(null);
    setErrorCode(null);
    setIsSubmitting(true);
    try {
      const response = await invitationsApi.issue({
        organization_id: selectedOrgId,
        email: email.trim().toLowerCase(),
        membership_type: membershipType,
        product_ids: selectedProductIds,
        module_ids: selectedModuleIds,
      });
      setIssuedInvitation(response);
      onSuccess?.(response);
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        const data = err.data as { code?: string; detail?: string } | undefined;
        setErrorCode(data?.code || null);
        setGeneralError(data?.detail || err.message || "Failed to provision member.");
      } else {
        setGeneralError("An unexpected error occurred while provisioning the member.");
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  const invitationLink = issuedInvitation?.activation_url || (issuedInvitation?.raw_token
    ? `/invitations/accept/${issuedInvitation.raw_token}`
    : null);

  const handleCopyLink = () => {
    if (invitationLink && typeof navigator !== "undefined" && navigator.clipboard) {
      void navigator.clipboard.writeText(invitationLink);
      setCopied(true);
      setTimeout(() => setCopied(false), 2500);
    }
  };

  const handleNavigateToAccept = () => {
    if (issuedInvitation?.raw_token) {
      handleClose();
      navigate(`/invitations/accept/${issuedInvitation.raw_token}`);
    }
  };

  return (
    <div
      className="dialog-backdrop"
      onClick={(e) => {
        if (e.target === e.currentTarget && !isSubmitting) {
          handleClose();
        }
      }}
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={`${baseId}-title`}
        className="dialog-surface"
        style={{
          maxWidth: "38rem",
          maxHeight: "min(90dvh, 760px)",
        }}
      >
        {/* Header */}
        <div className="dialog-header">
          <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
            <div
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                width: "2.25rem",
                height: "2.25rem",
                borderRadius: "0.5rem",
                backgroundColor: "var(--color-primary-subtle)",
                color: "var(--color-primary)",
              }}
            >
              <UserIcon size={20} />
            </div>
            <div>
              <h2 id={`${baseId}-title`} className="dialog-title">
                {membershipType === "member" ? "Member Onboarding" : "Invite Administrator"}
              </h2>
              <p id={`${baseId}-desc`} className="dialog-subtitle">
                Configure identity, products, and feature entitlements
              </p>
            </div>
          </div>
          <button
            type="button"
            className="dialog-close-btn"
            onClick={handleClose}
            disabled={isSubmitting}
            aria-label="Close dialog"
          >
            <CloseIcon size={18} />
          </button>
        </div>

        {/* Step Indicator (when not completed) */}
        {!issuedInvitation && membershipType === "member" && (
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(4, 1fr)",
              gap: "0.4rem",
              padding: "0.75rem 1.5rem 0 1.5rem",
            }}
          >
            {[
              { num: 1, label: "Identity" },
              { num: 2, label: "Products" },
              { num: 3, label: "Features" },
              { num: 4, label: "Provision" },
            ].map((st) => (
              <div
                key={st.num}
                style={{
                  padding: "0.4rem 0.5rem",
                  borderRadius: "4px",
                  fontSize: "0.72rem",
                  fontWeight: currentStep === st.num ? 700 : 500,
                  backgroundColor: currentStep === st.num
                    ? "rgba(99, 102, 241, 0.15)"
                    : currentStep > st.num
                    ? "rgba(16, 185, 129, 0.1)"
                    : "rgba(255, 255, 255, 0.04)",
                  color: currentStep === st.num
                    ? "var(--brand-primary, #6366f1)"
                    : currentStep > st.num
                    ? "var(--status-success)"
                    : "var(--text-muted)",
                  textAlign: "center",
                  borderLeft: currentStep === st.num ? "2px solid var(--brand-primary, #6366f1)" : "none",
                }}
              >
                {st.num}. {st.label}
              </div>
            ))}
          </div>
        )}

        {/* Content */}
        {issuedInvitation ? (
          /* Success Screen */
          <div className="dialog-body" style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>
            <div
              style={{
                padding: "1rem",
                borderRadius: "8px",
                background: "rgba(16, 185, 129, 0.1)",
                border: "1px solid rgba(16, 185, 129, 0.25)",
                display: "flex",
                alignItems: "flex-start",
                gap: "0.75rem",
              }}
            >
              <CheckCircleIcon size={20} style={{ color: "rgb(16, 185, 129)", flexShrink: 0, marginTop: "0.15rem" }} />
              <div>
                <h4 style={{ margin: "0 0 0.25rem 0", color: "var(--text-primary)", fontSize: "0.9375rem" }}>
                  Member Onboarded & Invitation Issued
                </h4>
                <p style={{ margin: 0, fontSize: "0.8125rem", color: "var(--text-secondary)", lineHeight: 1.5 }}>
                  Activation notification has been dispatched to <strong>{issuedInvitation.email}</strong> with configured product entitlements and feature permissions. Valid until {formatDateTime(issuedInvitation.expires_at)}.
                </p>
              </div>
            </div>

            {invitationLink && (
              <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                  <label style={{ fontSize: "0.8125rem", fontWeight: 600, color: "var(--text-primary)" }}>
                    One-Time Activation Link (Bearer Secret)
                  </label>
                  <span style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
                    Shown once · Copyable
                  </span>
                </div>
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: "0.5rem",
                    padding: "0.5rem 0.75rem",
                    background: "var(--bg-app)",
                    border: "1px solid var(--border-glass)",
                    borderRadius: "6px",
                    fontFamily: "monospace",
                    fontSize: "0.8125rem",
                    overflowX: "auto",
                  }}
                >
                  <span style={{ flex: 1, wordBreak: "break-all" }}>{invitationLink}</span>
                  <button
                    type="button"
                    className="btn btn-secondary btn-sm"
                    onClick={handleCopyLink}
                    style={{ display: "inline-flex", alignItems: "center", gap: "0.35rem" }}
                  >
                    <CopyIcon size={14} />
                    <span>{copied ? "Copied" : "Copy"}</span>
                  </button>
                </div>
              </div>
            )}

            <div className="dialog-footer" style={{ borderTop: "none", padding: 0, marginTop: "0.5rem" }}>
              <button type="button" className="btn btn-secondary" onClick={handleClose}>
                Done
              </button>
              {issuedInvitation?.raw_token && (
                <button type="button" className="btn btn-primary" onClick={handleNavigateToAccept}>
                  Go to Activation Page
                </button>
              )}
            </div>
          </div>
        ) : (
          <div
            style={{
              display: "flex",
              flexDirection: "column",
              flex: 1,
              minHeight: 0,
              overflow: "hidden",
            }}
          >
            <div className="dialog-body" style={{ overflowY: "auto" }}>
              {generalError && (
                <div
                  className="alert-banner alert-banner-error"
                  role="alert"
                  style={{ marginBottom: "0.75rem" }}
                >
                  <AlertCircleIcon size={18} />
                  <div>
                    {errorCode && (
                      <div style={{ fontWeight: 600, fontSize: "0.75rem", marginBottom: "0.25rem" }}>
                        Error Code: {errorCode}
                      </div>
                    )}
                    <div>{generalError}</div>
                  </div>
                </div>
              )}

              {/* Step 1: Member Identity */}
              {currentStep === 1 && (
                <form id={`${baseId}-step1`} onSubmit={handleProceedFromDetails} style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
                  {!defaultOrganizationId && (
                    <div>
                      <label
                        htmlFor={`${baseId}-org`}
                        style={{ display: "block", fontSize: "0.875rem", fontWeight: 500, marginBottom: "0.375rem" }}
                      >
                        Target Organization <span style={{ color: "var(--status-danger)" }}>*</span>
                      </label>
                      <select
                        id={`${baseId}-org`}
                        className="registry-filter-select"
                        style={{ width: "100%", height: "2.5rem" }}
                        value={selectedOrgId}
                        onChange={(e) => setSelectedOrgId(e.target.value)}
                        required
                      >
                        <option value="">Select Organization...</option>
                        {organizations.map((org) => (
                          <option key={org.id} value={org.id}>
                            {org.name} ({org.code})
                          </option>
                        ))}
                      </select>
                    </div>
                  )}

                  <div>
                    <label
                      htmlFor={`${baseId}-email`}
                      style={{ display: "block", fontSize: "0.875rem", fontWeight: 500, marginBottom: "0.375rem" }}
                    >
                      Member Email Address <span style={{ color: "var(--status-danger)" }}>*</span>
                    </label>
                    <input
                      ref={emailInputRef}
                      id={`${baseId}-email`}
                      type="email"
                      className="form-input"
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      placeholder="member@organization.com"
                      required
                      disabled={isSubmitting}
                      style={{ width: "100%" }}
                    />
                  </div>

                  <div>
                    <label
                      htmlFor={`${baseId}-membership`}
                      style={{ display: "block", fontSize: "0.875rem", fontWeight: 500, marginBottom: "0.375rem" }}
                    >
                      Membership Type
                    </label>
                    <select
                      id={`${baseId}-membership`}
                      className="registry-filter-select"
                      style={{ width: "100%", height: "2.5rem" }}
                      value={membershipType}
                      onChange={(e) => setMembershipType(e.target.value)}
                      disabled={isSubmitting || (allowedMembershipTypes !== undefined && allowedMembershipTypes.length <= 1)}
                    >
                      {(!allowedMembershipTypes || allowedMembershipTypes.includes("member")) && (
                        <option value="member">Standard Member</option>
                      )}
                      {(!allowedMembershipTypes || allowedMembershipTypes.includes("admin")) && (
                        <option value="admin">Tenant Administrator</option>
                      )}
                    </select>
                  </div>
                </form>
              )}

              {/* Step 2: Product Access */}
              {currentStep === 2 && (
                <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                    <div>
                      <h3 style={{ margin: 0, fontSize: "0.95rem", fontWeight: 700 }}>
                        Assign Products to Member
                      </h3>
                      <p style={{ margin: "0.2rem 0 0 0", fontSize: "0.8rem", color: "var(--text-secondary)" }}>
                        Select which tenant-entitled products this member should have access to.
                      </p>
                    </div>
                  </div>

                  {loadingSelectors ? (
                    <div style={{ padding: "2rem", textAlign: "center", color: "var(--text-muted)" }}>
                      Loading entitled products…
                    </div>
                  ) : entitledProducts.length === 0 ? (
                    <div className="glass-panel" style={{ padding: "1.5rem", textAlign: "center", color: "var(--text-muted)" }}>
                      No active products are entitled to this tenant.
                    </div>
                  ) : (
                    <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
                      {entitledProducts.map((p) => {
                        const isSelected = selectedProductIds.includes(p.id);

                        return (
                          <div
                            key={p.id}
                            onClick={() => void handleToggleProduct(p.id)}
                            style={{
                              padding: "0.75rem 1rem",
                              borderRadius: "6px",
                              cursor: "pointer",
                              border: isSelected
                                ? "1.5px solid var(--brand-primary, #6366f1)"
                                : "1px solid rgba(255,255,255,0.08)",
                              backgroundColor: isSelected
                                ? "rgba(99, 102, 241, 0.08)"
                                : "rgba(255,255,255,0.02)",
                              display: "flex",
                              alignItems: "center",
                              justifyContent: "space-between",
                            }}
                          >
                            <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
                              <input
                                type="checkbox"
                                checked={isSelected}
                                onChange={() => void handleToggleProduct(p.id)}
                                onClick={(e) => e.stopPropagation()}
                              />
                              <div>
                                <span style={{ fontWeight: 600, fontSize: "0.875rem" }}>{p.name}</span>
                                <span style={{ fontSize: "0.7rem", fontFamily: "var(--font-code)", color: "var(--text-muted)", marginLeft: "0.4rem" }}>
                                  {p.code}
                                </span>
                              </div>
                            </div>
                            <span style={{ fontSize: "0.75rem", fontWeight: 600, color: isSelected ? "var(--brand-primary, #6366f1)" : "var(--text-muted)" }}>
                              {isSelected ? "Assigned ✓" : "Excluded"}
                            </span>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              )}

              {/* Step 3: Console Feature Access */}
              {currentStep === 3 && (
                <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
                  <div>
                    <h3 style={{ margin: 0, fontSize: "0.95rem", fontWeight: 700 }}>
                      Member-Level Feature Access
                    </h3>
                    <p style={{ margin: "0.2rem 0 0 0", fontSize: "0.8rem", color: "var(--text-secondary)" }}>
                      Toggle access to specific modules within each assigned product, constrained by tenant ceilings.
                    </p>
                  </div>

                  {selectedProductIds.length === 0 ? (
                    <div className="glass-panel" style={{ padding: "1.5rem", textAlign: "center", color: "var(--text-muted)" }}>
                      Zero products selected. Member will have basic tenant membership with no product seats.
                    </div>
                  ) : (
                    <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
                      {selectedProductIds.map((pid) => {
                        const prod = entitledProducts.find((p) => p.id === pid);
                        const mods = productModules[pid] || [];

                        return (
                          <div
                            key={pid}
                            style={{
                              padding: "0.75rem 1rem",
                              borderRadius: "6px",
                              border: "1px solid rgba(255,255,255,0.08)",
                              backgroundColor: "rgba(255,255,255,0.02)",
                            }}
                          >
                            <div style={{ fontWeight: 700, fontSize: "0.875rem", marginBottom: "0.5rem" }}>
                              {prod?.name || "Product"}
                            </div>

                            {mods.length === 0 ? (
                              <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", fontStyle: "italic" }}>
                                All standard product capabilities enabled by default.
                              </div>
                            ) : (
                              <div style={{ display: "flex", flexDirection: "column", gap: "0.4rem" }}>
                                {mods.map((mod) => {
                                  const isEnabled = selectedModuleIds.includes(mod.id);

                                  return (
                                    <div
                                      key={mod.id}
                                      style={{
                                        display: "flex",
                                        justifyContent: "space-between",
                                        alignItems: "center",
                                        padding: "0.35rem 0.6rem",
                                        borderRadius: "4px",
                                        backgroundColor: isEnabled ? "rgba(99, 102, 241, 0.05)" : "transparent",
                                      }}
                                    >
                                      <div>
                                        <span style={{ fontSize: "0.8125rem", fontWeight: 500 }}>{mod.name}</span>
                                        <span style={{ fontSize: "0.68rem", fontFamily: "var(--font-code)", color: "var(--text-muted)", marginLeft: "0.4rem" }}>
                                          {mod.code}
                                        </span>
                                      </div>
                                      <button
                                        type="button"
                                        className={`btn ${isEnabled ? "btn-primary" : "btn-secondary"}`}
                                        style={{ fontSize: "0.68rem", padding: "0.15rem 0.5rem" }}
                                        onClick={() => handleToggleModule(mod.id)}
                                      >
                                        {isEnabled ? "Enabled" : "Disabled"}
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
              )}

              {/* Step 4: Review & Provision */}
              {currentStep === 4 && (
                <div style={{ display: "flex", flexDirection: "column", gap: "0.875rem" }}>
                  <div>
                    <h3 style={{ margin: 0, fontSize: "0.95rem", fontWeight: 700 }}>
                      Review Member Onboarding
                    </h3>
                    <p style={{ margin: "0.2rem 0 0 0", fontSize: "0.8rem", color: "var(--text-secondary)" }}>
                      Confirm configuration before provisioning the member account and access grants.
                    </p>
                  </div>

                  <div
                    style={{
                      padding: "1rem",
                      borderRadius: "6px",
                      backgroundColor: "rgba(255,255,255,0.03)",
                      border: "1px solid rgba(255,255,255,0.08)",
                      display: "grid",
                      gridTemplateColumns: "1fr 1fr",
                      gap: "0.75rem",
                      fontSize: "0.8125rem",
                    }}
                  >
                    <div>
                      <span style={{ color: "var(--text-muted)", display: "block", fontSize: "0.7rem", textTransform: "uppercase" }}>
                        Invitee Email
                      </span>
                      <strong>{email.trim()}</strong>
                    </div>
                    <div>
                      <span style={{ color: "var(--text-muted)", display: "block", fontSize: "0.7rem", textTransform: "uppercase" }}>
                        Role / Membership
                      </span>
                      <strong>{membershipType === "admin" ? "Tenant Administrator" : "Standard Member"}</strong>
                    </div>
                    <div>
                      <span style={{ color: "var(--text-muted)", display: "block", fontSize: "0.7rem", textTransform: "uppercase" }}>
                        Assigned Products
                      </span>
                      <strong>{selectedProductIds.length} Products</strong>
                    </div>
                    <div>
                      <span style={{ color: "var(--text-muted)", display: "block", fontSize: "0.7rem", textTransform: "uppercase" }}>
                        Enabled Modules
                      </span>
                      <strong>{selectedModuleIds.length} Modules</strong>
                    </div>
                  </div>

                  {selectedProductIds.length > 0 && (
                    <div style={{ display: "flex", flexWrap: "wrap", gap: "0.4rem" }}>
                      {selectedProductIds.map((pid) => {
                        const p = entitledProducts.find((item) => item.id === pid);
                        return (
                          <span
                            key={pid}
                            style={{
                              padding: "0.2rem 0.5rem",
                              borderRadius: "4px",
                              backgroundColor: "rgba(99, 102, 241, 0.15)",
                              fontSize: "0.75rem",
                              fontWeight: 600,
                            }}
                          >
                            {p?.name || pid}
                          </span>
                        );
                      })}
                    </div>
                  )}
                </div>
              )}
            </div>

            {/* Dialog Footer Actions */}
            <div className="dialog-footer">
              {currentStep > 1 ? (
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={() => setCurrentStep((prev) => prev - 1)}
                  disabled={isSubmitting}
                >
                  ← Back
                </button>
              ) : (
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={handleClose}
                  disabled={isSubmitting}
                >
                  Cancel
                </button>
              )}

              {currentStep === 1 && (
                <button
                  type="button"
                  className="btn btn-primary"
                  onClick={handleProceedFromDetails}
                  disabled={isSubmitting || !email.trim() || !selectedOrgId}
                >
                  {membershipType === "admin" ? "Review & Invite →" : "Next: Assign Products →"}
                </button>
              )}

              {currentStep === 2 && (
                <button
                  type="button"
                  className="btn btn-primary"
                  onClick={handleProceedFromProducts}
                  disabled={isSubmitting}
                >
                  Next: Feature Access →
                </button>
              )}

              {currentStep === 3 && (
                <button
                  type="button"
                  className="btn btn-primary"
                  onClick={handleProceedFromFeatures}
                  disabled={isSubmitting}
                >
                  Next: Review & Provision →
                </button>
              )}

              {currentStep === 4 && (
                <button
                  type="button"
                  className="btn btn-primary"
                  onClick={handleFinalSubmit}
                  disabled={isSubmitting || !email.trim() || !selectedOrgId}
                >
                  {isSubmitting ? "Provisioning Member..." : "Provision Member & Send Invitation ✓"}
                </button>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
