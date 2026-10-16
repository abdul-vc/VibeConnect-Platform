/**
 * Access Request Form Page (Phase 3F).
 *
 * Allows a tenant user or administrator to submit a product access request.
 * Enforces zero hardcoding and consumes centralized API services.
 */

import React, { useEffect, useId, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { accessRequestsApi } from "../../api/accessRequests.ts";
import { productsApi } from "../../api/products.ts";
import { ApiError } from "../../api/client.ts";
import type { ProductListItem } from "../../api/types.ts";
import { AppShell } from "../../components/AppShell.tsx";
import {
  AlertCircleIcon,
  ChevronLeftIcon,
  ShieldCheckIcon,
} from "../../components/Icons.tsx";
import { useAuth } from "../../context/AuthContext.tsx";

export const AccessRequestFormPage: React.FC = () => {
  const { user } = useAuth();
  const navigate = useNavigate();

  const orgSelectId = useId();
  const productSelectId = useId();
  const reasonInputId = useId();

  const activeOrgId = user?.active_context?.organization?.id || "";
  const [selectedOrgId, setSelectedOrgId] = useState<string>(activeOrgId);
  const [selectedProductId, setSelectedProductId] = useState<string>("");
  const [reason, setReason] = useState<string>("");

  const [products, setProducts] = useState<readonly ProductListItem[]>([]);
  const [isLoadingProducts, setIsLoadingProducts] = useState<boolean>(true);
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  useEffect(() => {
    if (activeOrgId && !selectedOrgId) {
      setSelectedOrgId(activeOrgId);
    }
  }, [activeOrgId, selectedOrgId]);

  useEffect(() => {
    const fetchActiveProducts = async () => {
      setIsLoadingProducts(true);
      try {
        const response = await productsApi.list({ status: "active", page_size: 100 });
        setProducts(response.results);
        if (response.results.length > 0) {
          setSelectedProductId(response.results[0].id);
        }
      } catch (err: unknown) {
        if (err instanceof ApiError) {
          setErrorMessage(err.message || "Failed to load product catalog.");
        } else {
          setErrorMessage("Failed to load active products.");
        }
      } finally {
        setIsLoadingProducts(false);
      }
    };

    fetchActiveProducts();
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const errors: Record<string, string> = {};

    const orgToUse = selectedOrgId || activeOrgId;
    if (!orgToUse) {
      errors.organization = "Please select an organization context.";
    }
    if (!selectedProductId) {
      errors.product = "Please select a product.";
    }

    if (Object.keys(errors).length > 0) {
      setFieldErrors(errors);
      return;
    }

    setIsSubmitting(true);
    setErrorMessage(null);
    setFieldErrors({});

    try {
      await accessRequestsApi.createRequest({
        organization_id: orgToUse,
        product_id: selectedProductId,
        reason: reason.trim(),
      });

      navigate("/access-requests");
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        if (err.status === 409) {
          setErrorMessage(
            "A pending access request already exists for this product. Please wait for an administrator to review it."
          );
        } else {
          setErrorMessage(err.message || "Failed to submit access request.");
        }
      } else {
        setErrorMessage("An unexpected error occurred while submitting your request.");
      }
      setIsSubmitting(false);
    }
  };

  const availableOrgs = user?.available_contexts?.filter(
    (ctx) => ctx.type === "tenant" && ctx.organization
  ) || [];

  return (
    <AppShell>
      <div style={{ maxWidth: "768px", margin: "0 auto", padding: "1.5rem" }}>
        {/* Navigation Breadcrumb */}
        <div style={{ marginBottom: "1rem" }}>
          <Link
            to="/access-requests"
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: "0.25rem",
              color: "var(--text-muted, #94a3b8)",
              textDecoration: "none",
              fontSize: "0.875rem",
            }}
          >
            <ChevronLeftIcon size={16} />
            <span>Back to Access Requests</span>
          </Link>
        </div>

        {/* Header */}
        <div style={{ marginBottom: "1.5rem" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
            <ShieldCheckIcon size={24} />
            <h1 style={{ fontSize: "1.5rem", fontWeight: 700, margin: 0 }}>
              Request Product Access
            </h1>
          </div>
          <p
            style={{
              fontSize: "0.875rem",
              color: "var(--text-secondary, #94a3b8)",
              margin: "0.25rem 0 0 0",
            }}
          >
            Submit an access request for approval by an organization administrator.
          </p>
        </div>

        {/* Global Error Banner */}
        {errorMessage && (
          <div
            role="alert"
            style={{
              display: "flex",
              alignItems: "center",
              gap: "0.5rem",
              padding: "0.75rem 1rem",
              backgroundColor: "rgba(239, 68, 68, 0.1)",
              border: "1px solid rgba(239, 68, 68, 0.3)",
              borderRadius: "0.5rem",
              color: "#f87171",
              fontSize: "0.875rem",
              marginBottom: "1.5rem",
            }}
          >
            <AlertCircleIcon size={18} />
            <span>{errorMessage}</span>
          </div>
        )}

        {/* Request Form */}
        <div
          style={{
            backgroundColor: "var(--bg-card, #1e293b)",
            borderRadius: "0.75rem",
            border: "1px solid var(--border-color, #334155)",
            padding: "1.5rem",
          }}
        >
          <form onSubmit={handleSubmit}>
            {/* Organization context selection */}
            {availableOrgs.length > 1 ? (
              <div style={{ marginBottom: "1.25rem" }}>
                <label
                  htmlFor={orgSelectId}
                  style={{
                    display: "block",
                    fontSize: "0.875rem",
                    fontWeight: 500,
                    marginBottom: "0.5rem",
                  }}
                >
                  Organization <span style={{ color: "#ef4444" }}>*</span>
                </label>
                <select
                  id={orgSelectId}
                  value={selectedOrgId}
                  onChange={(e) => setSelectedOrgId(e.target.value)}
                  style={{
                    width: "100%",
                    padding: "0.625rem 0.75rem",
                    backgroundColor: "var(--bg-input, #0f172a)",
                    border: "1px solid var(--border-color, #334155)",
                    borderRadius: "0.375rem",
                    color: "var(--text-primary, #f8fafc)",
                    fontSize: "0.875rem",
                  }}
                >
                  {availableOrgs.map((ctx) => (
                    <option key={ctx.organization?.id} value={ctx.organization?.id}>
                      {ctx.organization?.name} ({ctx.organization?.code})
                    </option>
                  ))}
                </select>
              </div>
            ) : (
              <div style={{ marginBottom: "1.25rem" }}>
                <div style={{ fontSize: "0.875rem", color: "var(--text-muted, #94a3b8)" }}>
                  Organization Context:{" "}
                  <strong style={{ color: "var(--text-primary, #f8fafc)" }}>
                    {user?.active_context?.organization?.name || "Current Organization"}
                  </strong>
                </div>
              </div>
            )}

            {/* Product Selection */}
            <div style={{ marginBottom: "1.25rem" }}>
              <label
                htmlFor={productSelectId}
                style={{
                  display: "block",
                  fontSize: "0.875rem",
                  fontWeight: 500,
                  marginBottom: "0.5rem",
                }}
              >
                Target Product <span style={{ color: "#ef4444" }}>*</span>
              </label>
              {isLoadingProducts ? (
                <div style={{ fontSize: "0.875rem", color: "var(--text-muted, #94a3b8)" }}>
                  Loading active products...
                </div>
              ) : products.length === 0 ? (
                <div style={{ fontSize: "0.875rem", color: "#f59e0b" }}>
                  No active products available in catalog.
                </div>
              ) : (
                <select
                  id={productSelectId}
                  value={selectedProductId}
                  onChange={(e) => setSelectedProductId(e.target.value)}
                  style={{
                    width: "100%",
                    padding: "0.625rem 0.75rem",
                    backgroundColor: "var(--bg-input, #0f172a)",
                    border: `1px solid ${
                      fieldErrors.product ? "#ef4444" : "var(--border-color, #334155)"
                    }`,
                    borderRadius: "0.375rem",
                    color: "var(--text-primary, #f8fafc)",
                    fontSize: "0.875rem",
                  }}
                >
                  {products.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.name} ({p.code})
                    </option>
                  ))}
                </select>
              )}
              {fieldErrors.product && (
                <div style={{ color: "#ef4444", fontSize: "0.75rem", marginTop: "0.25rem" }}>
                  {fieldErrors.product}
                </div>
              )}
            </div>

            {/* Business Reason */}
            <div style={{ marginBottom: "1.5rem" }}>
              <label
                htmlFor={reasonInputId}
                style={{
                  display: "block",
                  fontSize: "0.875rem",
                  fontWeight: 500,
                  marginBottom: "0.5rem",
                }}
              >
                Business Justification / Reason
              </label>
              <textarea
                id={reasonInputId}
                rows={4}
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                maxLength={500}
                placeholder="Explain why you need access to this product..."
                style={{
                  width: "100%",
                  padding: "0.625rem 0.75rem",
                  backgroundColor: "var(--bg-input, #0f172a)",
                  border: "1px solid var(--border-color, #334155)",
                  borderRadius: "0.375rem",
                  color: "var(--text-primary, #f8fafc)",
                  fontSize: "0.875rem",
                  boxSizing: "border-box",
                }}
              />
              <div
                style={{
                  fontSize: "0.75rem",
                  color: "var(--text-muted, #94a3b8)",
                  textAlign: "right",
                  marginTop: "0.25rem",
                }}
              >
                {reason.length}/500
              </div>
            </div>

            {/* Actions */}
            <div
              style={{
                display: "flex",
                justifyContent: "flex-end",
                gap: "0.75rem",
              }}
            >
              <Link
                to="/access-requests"
                style={{
                  padding: "0.625rem 1rem",
                  borderRadius: "0.375rem",
                  border: "1px solid var(--border-color, #334155)",
                  color: "var(--text-primary, #f8fafc)",
                  textDecoration: "none",
                  fontSize: "0.875rem",
                  fontWeight: 500,
                  display: "inline-flex",
                  alignItems: "center",
                }}
              >
                Cancel
              </Link>
              <button
                type="submit"
                disabled={isSubmitting || isLoadingProducts || products.length === 0}
                style={{
                  padding: "0.625rem 1.25rem",
                  borderRadius: "0.375rem",
                  border: "none",
                  backgroundColor: "var(--color-primary, #6366f1)",
                  color: "#ffffff",
                  fontSize: "0.875rem",
                  fontWeight: 500,
                  cursor: isSubmitting ? "not-allowed" : "pointer",
                  opacity: isSubmitting ? 0.7 : 1,
                }}
              >
                {isSubmitting ? "Submitting Request..." : "Submit Access Request"}
              </button>
            </div>
          </form>
        </div>
      </div>
    </AppShell>
  );
};
