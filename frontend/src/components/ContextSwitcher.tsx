/**
 * Accessible Context Switcher Component (Phase 2D).
 *
 * Replaces native <select> with a theme-aware, keyboard-accessible dropdown.
 * - Displays active context clearly (Platform Owner or Organization Name/Code)
 * - Desktop: bounded width with ellipsis and complete tooltip
 * - Mobile: viewport-safe full-width dropdown with >=44px touch targets
 * - Keyboard: Tab reaches trigger, Enter/Space opens, Arrows navigate, Escape closes, focus restores
 */

import React, { useState, useRef, useEffect, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext.tsx";
import { BuildingIcon, ShieldCheckIcon, ChevronDownIcon } from "./Icons.tsx";

interface ContextSwitcherProps {
  readonly isMobile?: boolean;
}

export const ContextSwitcher: React.FC<ContextSwitcherProps> = ({ isMobile = false }) => {
  const { user, selectContext } = useAuth();
  const navigate = useNavigate();

  const [isOpen, setIsOpen] = useState(false);
  const [highlightedIndex, setHighlightedIndex] = useState(-1);
  const triggerRef = useRef<HTMLButtonElement | null>(null);
  const menuRef = useRef<HTMLDivElement | null>(null);

  const availableContexts = user?.available_contexts || [];
  const activeContext = user?.active_context;

  const isOwner = activeContext?.type === "platform_owner";
  const activeLabel = isOwner
    ? "Platform Owner"
    : activeContext?.organization
    ? `${activeContext.organization.name} (${activeContext.organization.code})`
    : "Select Context";

  const closeMenu = useCallback(() => {
    setIsOpen(false);
    setHighlightedIndex(-1);
    triggerRef.current?.focus();
  }, []);

  // Close on outside click
  useEffect(() => {
    if (!isOpen) return;

    const handlePointerDown = (e: MouseEvent | TouchEvent) => {
      const target = e.target as Node;
      if (
        menuRef.current &&
        !menuRef.current.contains(target) &&
        triggerRef.current &&
        !triggerRef.current.contains(target)
      ) {
        setIsOpen(false);
        setHighlightedIndex(-1);
      }
    };

    document.addEventListener("mousedown", handlePointerDown);
    document.addEventListener("touchstart", handlePointerDown);
    return () => {
      document.removeEventListener("mousedown", handlePointerDown);
      document.removeEventListener("touchstart", handlePointerDown);
    };
  }, [isOpen]);

  // Keyboard navigation
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (!isOpen) {
      if (e.key === "Enter" || e.key === " " || e.key === "ArrowDown") {
        e.preventDefault();
        setIsOpen(true);
        setHighlightedIndex(0);
      }
      return;
    }

    switch (e.key) {
      case "Escape":
        e.preventDefault();
        closeMenu();
        break;
      case "ArrowDown":
        e.preventDefault();
        setHighlightedIndex((prev) =>
          prev < availableContexts.length - 1 ? prev + 1 : 0
        );
        break;
      case "ArrowUp":
        e.preventDefault();
        setHighlightedIndex((prev) =>
          prev > 0 ? prev - 1 : availableContexts.length - 1
        );
        break;
      case "Enter":
      case " ":
        e.preventDefault();
        if (highlightedIndex >= 0 && highlightedIndex < availableContexts.length) {
          handleSelect(availableContexts[highlightedIndex]);
        }
        break;
      case "Tab":
        setIsOpen(false);
        break;
    }
  };

  const handleSelect = async (ctx: (typeof availableContexts)[0]) => {
    setIsOpen(false);
    setHighlightedIndex(-1);
    try {
      if (ctx.type === "platform_owner") {
        await selectContext({ context_type: "platform_owner" });
        navigate("/");
      } else if (ctx.type === "tenant" && ctx.organization) {
        const res = (await selectContext({
          context_type: "tenant",
          organization_id: ctx.organization.id,
        })) as any;
        if (res?.active_context?.membership_type === "member" || ctx.membership_type === "member") {
          navigate("/tenant/dashboard");
        } else {
          navigate("/tenant");
        }
      }
    } catch {
      // Re-handled by auth context
    }
  };

  if (availableContexts.length <= 1) return null;

  return (
    <div
      style={{
        position: "relative",
        display: "inline-block",
        width: isMobile ? "100%" : "auto",
        minWidth: 0,
      }}
    >
      {/* Trigger Button */}
      <button
        ref={triggerRef}
        type="button"
        onClick={() => setIsOpen((prev) => !prev)}
        onKeyDown={handleKeyDown}
        aria-haspopup="listbox"
        aria-expanded={isOpen}
        aria-controls="context-switcher-listbox"
        aria-label={`Active context: ${activeLabel}. Click to change context.`}
        title={activeLabel}
        style={{
          display: "flex",
          alignItems: "center",
          gap: "0.5rem",
          padding: isMobile ? "0.5rem 0.75rem" : "0.35rem 0.65rem",
          minHeight: isMobile ? "44px" : "36px",
          width: isMobile ? "100%" : "auto",
          maxWidth: isMobile ? "100%" : "280px",
          background: "var(--glass-surface)",
          border: "1px solid var(--border-glass)",
          borderRadius: "8px",
          color: "var(--text-primary)",
          fontSize: "0.8125rem",
          fontWeight: 500,
          cursor: "pointer",
          outline: "none",
          transition: "all 0.15s ease",
          boxSizing: "border-box",
          justifyContent: "space-between",
        }}
        className="context-switcher-trigger"
      >
        <div style={{ display: "flex", alignItems: "center", gap: "0.45rem", minWidth: 0, flex: 1 }}>
          <span
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              color: isOwner ? "var(--status-success)" : "rgb(99, 102, 241)",
              flexShrink: 0,
            }}
          >
            {isOwner ? <ShieldCheckIcon size={15} /> : <BuildingIcon size={15} />}
          </span>
          <span
            style={{
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
              color: "var(--text-primary)",
              minWidth: 0,
            }}
          >
            {activeLabel}
          </span>
        </div>
        <span
          style={{
            display: "flex",
            alignItems: "center",
            transform: isOpen ? "rotate(180deg)" : "rotate(0deg)",
            transition: "transform 0.15s ease",
            color: "var(--text-muted)",
            flexShrink: 0,
            marginLeft: "0.25rem",
          }}
        >
          <ChevronDownIcon size={14} />
        </span>
      </button>

      {/* Dropdown Menu */}
      {isOpen && (
        <div
          ref={menuRef}
          id="context-switcher-listbox"
          role="listbox"
          aria-label="Available console contexts"
          style={{
            position: "absolute",
            top: "calc(100% + 4px)",
            left: isMobile ? 0 : "auto",
            right: 0,
            width: isMobile ? "100%" : "max-content",
            minWidth: isMobile ? "100%" : "220px",
            maxWidth: isMobile ? "100%" : "340px",
            background: "var(--glass-surface-elevated)",
            border: "1px solid var(--border-glass)",
            borderRadius: "10px",
            boxShadow: "var(--shadow-lg)",
            padding: "0.35rem",
            zIndex: 100,
            display: "flex",
            flexDirection: "column",
            gap: "0.2rem",
            boxSizing: "border-box",
            maxHeight: "320px",
            overflowY: "auto",
          }}
        >
          {availableContexts.map((ctx, idx) => {
            const isCtxOwner = ctx.type === "platform_owner";
            const isSelected =
              activeContext?.type === ctx.type &&
              (isCtxOwner || activeContext?.organization?.id === ctx.organization?.id);
            const isHighlighted = highlightedIndex === idx;
            const label = isCtxOwner
              ? "Platform Owner"
              : `${ctx.organization?.name} (${ctx.organization?.code})`;

            return (
              <div
                key={isCtxOwner ? "platform_owner" : `tenant:${ctx.organization?.id}`}
                role="option"
                aria-selected={isSelected}
                tabIndex={-1}
                onClick={() => handleSelect(ctx)}
                onMouseEnter={() => setHighlightedIndex(idx)}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "0.5rem",
                  padding: "0.625rem 0.75rem",
                  minHeight: "44px",
                  borderRadius: "6px",
                  background: isSelected
                    ? "var(--brand-primary-light)"
                    : isHighlighted
                    ? "var(--glass-surface-hover)"
                    : "transparent",
                  color: isSelected ? "var(--brand-primary)" : "var(--text-primary)",
                  cursor: "pointer",
                  fontSize: "0.8125rem",
                  fontWeight: isSelected ? 600 : 500,
                  transition: "background-color 0.12s ease",
                  boxSizing: "border-box",
                  userSelect: "none",
                }}
                title={label}
              >
                <span
                  style={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    color: isCtxOwner ? "var(--status-success)" : "rgb(99, 102, 241)",
                    flexShrink: 0,
                  }}
                >
                  {isCtxOwner ? <ShieldCheckIcon size={16} /> : <BuildingIcon size={16} />}
                </span>
                <span
                  style={{
                    flex: 1,
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                    whiteSpace: "nowrap",
                    minWidth: 0,
                  }}
                >
                  {label}
                </span>
                {isSelected && (
                  <span
                    style={{
                      fontSize: "0.6875rem",
                      padding: "0.15rem 0.4rem",
                      borderRadius: "4px",
                      background: "var(--brand-primary)",
                      color: "#ffffff",
                      fontWeight: 600,
                      flexShrink: 0,
                    }}
                  >
                    Active
                  </span>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};
