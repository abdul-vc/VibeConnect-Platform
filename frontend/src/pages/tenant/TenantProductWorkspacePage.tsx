/**
 * Tenant Product Embedded Workspace Page.
 *
 * Dedicated console page hosting the universal, product-agnostic EmbeddedProductWorkspace
 * inside the standard VibeConnect AppShell layout.
 *
 * Route: /tenant/workspace/:productId
 *
 * Preserves the existing left sidebar, header, navigation, and tenant context.
 */

import React, { useState, useEffect, useCallback, useRef } from "react";
import { useParams, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../../context/AuthContext.tsx";
import { AppShell } from "../../components/AppShell.tsx";
import { EmbeddedProductWorkspace } from "../../components/workspace/EmbeddedProductWorkspace.tsx";
import { tenantHomeApi } from "../../api/tenantHome.ts";
import type { TenantProductAccessItem } from "../../api/types.ts";
import { LoadingSpinner } from "../../components/LoadingSpinner.tsx";
import { AlertCircleIcon } from "../../components/Icons.tsx";

export const TenantProductWorkspacePage: React.FC = () => {
  const params = useParams<{ productId: string }>();
  const location = useLocation();
  const navigate = useNavigate();
  const { user } = useAuth();

  const productId = params.productId || location.pathname.split("/").pop();

  const currentTenantId = user?.active_context?.organization?.id;

  // Resolve product either from navigation state or fetch from tenant home
  const stateProduct = (location.state as { product?: TenantProductAccessItem } | null)?.product;
  const [product, setProduct] = useState<TenantProductAccessItem | null>(
    stateProduct ?? null
  );
  const [isLoading, setIsLoading] = useState<boolean>(!product);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const cachedProductsRef = useRef<readonly TenantProductAccessItem[] | null>(null);

  const fetchProductResolution = useCallback(async () => {
    if (!productId) {
      setErrorMessage("Missing product identifier.");
      setIsLoading(false);
      return;
    }

    setIsLoading(true);
    setErrorMessage(null);

    try {
      const homeData = await tenantHomeApi.getTenantHome();
      const allProducts: readonly TenantProductAccessItem[] =
        homeData.products && homeData.products.length > 0
          ? homeData.products
          : homeData.entitled_products ?? [];

      cachedProductsRef.current = allProducts;
      const found = allProducts.find((p) => p.id === productId || p.code === productId);
      if (found) {
        if (found.launchable === false && found.access_state !== "available") {
          const reason =
            found.access_state === "integration_pending"
              ? "Integration is pending for this product."
              : "Product access or assignment required.";
          setErrorMessage(reason);
        } else {
          setProduct(found);
        }
      } else {
        setErrorMessage("The requested product is not assigned or available for your account.");
      }
    } catch (err: unknown) {
      const detail =
        err && typeof err === "object" && "message" in err
          ? String((err as { message: string }).message)
          : "Failed to verify product access rights.";
      setErrorMessage(detail);
    } finally {
      setIsLoading(false);
    }
  }, [productId]);

  useEffect(() => {
    if (stateProduct && (stateProduct.id === productId || stateProduct.code === productId)) {
      setProduct(stateProduct);
      setIsLoading(false);
      setErrorMessage(null);
      return;
    }

    if (cachedProductsRef.current) {
      const found = cachedProductsRef.current.find(
        (p: TenantProductAccessItem) => p.id === productId || p.code === productId
      );
      if (found) {
        setProduct(found);
        setIsLoading(false);
        setErrorMessage(null);
        return;
      }
    }

    void fetchProductResolution();
  }, [productId, stateProduct, fetchProductResolution]);

  return (
    <AppShell fullWidth>
      {isLoading ? (
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            justifyContent: "center",
            minHeight: "450px",
            gap: "1rem",
            background: "var(--glass-surface-elevated)",
            border: "1px solid var(--border-glass)",
            borderRadius: "14px",
            padding: "3rem",
          }}
        >
          <LoadingSpinner
            fullScreen={false}
            label="Verifying product access and preparing workspace…"
          />
        </div>
      ) : errorMessage || !product ? (
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            justifyContent: "center",
            minHeight: "400px",
            textAlign: "center",
            background: "var(--glass-surface-elevated)",
            border: "1px solid var(--border-glass)",
            borderRadius: "14px",
            padding: "3rem 1.5rem",
          }}
        >
          <div
            style={{
              width: "48px",
              height: "48px",
              borderRadius: "12px",
              background: "var(--status-danger-bg)",
              color: "var(--status-danger)",
              display: "inline-flex",
              alignItems: "center",
              justifyContent: "center",
              marginBottom: "1rem",
              border: "1px solid var(--status-danger-border)",
            }}
          >
            <AlertCircleIcon size={24} />
          </div>
          <h2 style={{ fontSize: "1.125rem", fontWeight: 700, margin: "0 0 0.5rem 0", color: "var(--text-primary)" }}>
            Product Unavailable
          </h2>
          <p style={{ fontSize: "0.875rem", color: "var(--text-secondary)", maxWidth: "420px", margin: "0 0 1.5rem 0" }}>
            {errorMessage || "You do not have active entitlement to launch this product."}
          </p>
          <button
            type="button"
            onClick={() => navigate("/tenant/products")}
            className="btn-primary"
            style={{ padding: "0.55rem 1.25rem", fontSize: "0.875rem", cursor: "pointer" }}
          >
            Return to My Products
          </button>
        </div>
      ) : (
        <EmbeddedProductWorkspace
          product={product}
          organizationId={currentTenantId}
          onBackToProducts={() => navigate("/tenant/products")}
        />
      )}
    </AppShell>
  );
};
