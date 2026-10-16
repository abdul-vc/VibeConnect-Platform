/**
 * Accessible Catalog Hierarchy Navigation Component.
 *
 * Renders a polished bordered glass navigation surface displaying the
 * ancestral trail (Product Registry > Product > Module > Feature),
 * with code chips, accessible separators, aria-current markers,
 * visible keyboard focus indicators, and responsive wrapping down to 320px.
 */

import React from "react";
import { Link } from "react-router-dom";
import { ChevronRightIcon } from "../Icons.tsx";

export interface HierarchyNavItem {
  readonly label: string;
  readonly path?: string;
  readonly code?: string;
}

interface CatalogHierarchyNavProps {
  readonly items: readonly HierarchyNavItem[];
}

export const CatalogHierarchyNav: React.FC<CatalogHierarchyNavProps> = ({
  items,
}) => {
  return (
    <nav aria-label="Catalog hierarchy navigation" className="catalog-hierarchy-nav">
      <ol className="hierarchy-nav-list">
        {items.map((item, index) => {
          const isLast = index === items.length - 1;
          return (
            <li key={index} className="hierarchy-nav-entry">
              {index > 0 && (
                <span className="hierarchy-nav-separator" aria-hidden="true">
                  <ChevronRightIcon size={14} />
                </span>
              )}
              {isLast || !item.path ? (
                <span
                  className="hierarchy-nav-current"
                  aria-current={isLast ? "page" : undefined}
                >
                  {item.code && (
                    <span className="product-code-pill hierarchy-nav-code-pill">
                      {item.code}
                    </span>
                  )}
                  <span className="hierarchy-nav-label" title={item.label}>
                    {item.label}
                  </span>
                </span>
              ) : (
                <Link
                  to={item.path}
                  className="hierarchy-nav-link"
                  title={item.label}
                >
                  {item.code && (
                    <span className="product-code-pill hierarchy-nav-code-pill">
                      {item.code}
                    </span>
                  )}
                  <span className="hierarchy-nav-label">{item.label}</span>
                </Link>
              )}
            </li>
          );
        })}
      </ol>

      <style>{`
        .catalog-hierarchy-nav {
          display: flex;
          align-items: center;
          width: 100%;
          background: var(--glass-surface);
          border: 1px solid var(--border-glass);
          border-radius: 12px;
          padding: 0.5rem 0.875rem;
          box-shadow: var(--shadow-sm);
          box-sizing: border-box;
        }

        .hierarchy-nav-list {
          display: flex;
          align-items: center;
          list-style: none;
          padding: 0;
          margin: 0;
          flex-wrap: wrap;
          row-gap: 0.375rem;
          column-gap: 0.375rem;
          width: 100%;
        }

        .hierarchy-nav-entry {
          display: inline-flex;
          align-items: center;
          gap: 0.375rem;
          font-size: 0.875rem;
          white-space: nowrap;
          flex-shrink: 0;
        }

        .hierarchy-nav-separator {
          color: var(--text-muted);
          display: inline-flex;
          align-items: center;
          flex-shrink: 0;
          opacity: 0.7;
        }

        .hierarchy-nav-link {
          color: var(--text-secondary);
          text-decoration: none;
          font-weight: 500;
          display: inline-flex;
          align-items: center;
          gap: 0.35rem;
          min-height: 40px;
          padding: 0.25rem 0.5rem;
          border-radius: 6px;
          transition: color 0.15s ease, background-color 0.15s ease;
          white-space: nowrap;
        }

        .hierarchy-nav-link:hover {
          color: var(--brand-primary);
          background: var(--glass-surface-hover, rgba(0, 0, 0, 0.04));
        }

        .hierarchy-nav-link:focus-visible {
          outline: 2px solid var(--brand-primary);
          outline-offset: 2px;
        }

        .hierarchy-nav-current {
          color: var(--text-primary);
          font-weight: 600;
          display: inline-flex;
          align-items: center;
          gap: 0.35rem;
          min-height: 40px;
          padding: 0.25rem 0.5rem;
          white-space: nowrap;
        }

        .hierarchy-nav-code-pill {
          font-size: 0.75rem;
          padding: 0.1rem 0.4rem;
          flex-shrink: 0;
        }

        .hierarchy-nav-label {
          max-width: 240px;
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
        }

        @media (max-width: 640px) {
          .catalog-hierarchy-nav {
            padding: 0.5rem 0.75rem;
          }

          .hierarchy-nav-link,
          .hierarchy-nav-current {
            min-height: 44px;
            padding: 0.25rem 0.375rem;
          }

          .hierarchy-nav-label {
            max-width: 140px;
          }
        }

        @media (max-width: 360px) {
          .catalog-hierarchy-nav {
            padding: 0.375rem 0.5rem;
          }

          .hierarchy-nav-entry {
            font-size: 0.8125rem;
            gap: 0.25rem;
          }

          .hierarchy-nav-link,
          .hierarchy-nav-current {
            min-height: 44px;
            padding: 0.2rem 0.3rem;
          }

          .hierarchy-nav-label {
            max-width: 95px;
          }

          .hierarchy-nav-code-pill {
            font-size: 0.6875rem;
            padding: 0.05rem 0.3rem;
          }
        }
      `}</style>
    </nav>
  );
};
