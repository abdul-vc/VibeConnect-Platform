/**
 * Reusable Catalog Filter Toolbar Component.
 *
 * Provides shared search input, lifecycle status filter, and deterministic ordering controls
 * across all Product Catalog hierarchy levels (Modules, Features, Capabilities).
 * Adheres strictly to the VibeConnect Enterprise Frosted Pearl / Midnight Glass design system
 * with >=44px touch targets, unified icon adornments, robust form semantics, and full WCAG accessibility.
 */

import React, { useId } from "react";
import type { CatalogOrderingField } from "../../api/types.ts";
import {
  ChevronDownIcon,
  FilterIcon,
  SearchIcon,
  SlidersIcon,
} from "../Icons.tsx";

export interface CatalogOrderingOption {
  readonly value: CatalogOrderingField;
  readonly label: string;
}

export const DEFAULT_CATALOG_ORDERING_OPTIONS: readonly CatalogOrderingOption[] = [
  { value: "display_order", label: "Display Order (Default)" },
  { value: "-display_order", label: "Display Order (Reverse)" },
  { value: "name", label: "Name (A to Z)" },
  { value: "-name", label: "Name (Z to A)" },
  { value: "code", label: "Code (A to Z)" },
  { value: "-code", label: "Code (Z to A)" },
  { value: "-created_at", label: "Newest First" },
  { value: "created_at", label: "Oldest First" },
];

export interface CatalogFilterToolbarProps {
  readonly entityTypePlural: string;
  readonly searchInput: string;
  readonly onSearchChange: (value: string) => void;
  readonly searchPlaceholder?: string;
  readonly statusFilter: string;
  readonly onStatusChange: (status: string) => void;
  readonly ordering: CatalogOrderingField;
  readonly onOrderingChange: (ordering: CatalogOrderingField) => void;
  readonly orderingOptions?: readonly CatalogOrderingOption[];
  readonly disabled?: boolean;
}

export const CatalogFilterToolbar: React.FC<CatalogFilterToolbarProps> = ({
  entityTypePlural,
  searchInput,
  onSearchChange,
  searchPlaceholder,
  statusFilter,
  onStatusChange,
  ordering,
  onOrderingChange,
  orderingOptions = DEFAULT_CATALOG_ORDERING_OPTIONS,
  disabled = false,
}) => {
  const baseId = useId();
  const searchInputId = `${baseId}-search`;
  const statusSelectId = `${baseId}-status`;
  const orderingSelectId = `${baseId}-ordering`;

  return (
    <div className="registry-controls-bar" role="search" aria-label={`Filter and sort ${entityTypePlural}`}>
      {/* Search Input */}
      <div className="search-input-wrapper">
        <label htmlFor={searchInputId} className="sr-only">
          Search {entityTypePlural}
        </label>
        <span className="search-icon-adornment" aria-hidden="true">
          <SearchIcon size={16} />
        </span>
        <input
          id={searchInputId}
          name="search"
          type="search"
          className="registry-search-input"
          placeholder={searchPlaceholder ?? `Search ${entityTypePlural} by code or name...`}
          value={searchInput}
          onChange={(e) => onSearchChange(e.target.value)}
          aria-label={`Search ${entityTypePlural}`}
          disabled={disabled}
        />
      </div>

      {/* Status Filter */}
      <div className="status-filter-wrapper">
        <label htmlFor={statusSelectId} className="sr-only">
          Filter by lifecycle status
        </label>
        <span className="filter-icon-adornment" aria-hidden="true">
          <FilterIcon size={15} />
        </span>
        <select
          id={statusSelectId}
          name="status"
          className="registry-filter-select"
          value={statusFilter}
          onChange={(e) => onStatusChange(e.target.value)}
          aria-label="Filter by lifecycle status"
          disabled={disabled}
        >
          <option value="">All Statuses</option>
          <option value="draft">Draft</option>
          <option value="active">Active</option>
          <option value="retired">Retired</option>
        </select>
        <span className="filter-chevron-adornment" aria-hidden="true">
          <ChevronDownIcon size={15} />
        </span>
      </div>

      {/* Ordering Select */}
      <div className="ordering-select-wrapper">
        <label htmlFor={orderingSelectId} className="sr-only">
          Sort order
        </label>
        <span className="filter-icon-adornment" aria-hidden="true">
          <SlidersIcon size={15} />
        </span>
        <select
          id={orderingSelectId}
          name="ordering"
          className="registry-filter-select"
          value={ordering}
          onChange={(e) => onOrderingChange(e.target.value as CatalogOrderingField)}
          aria-label="Sort order"
          disabled={disabled}
        >
          {orderingOptions.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
        <span className="filter-chevron-adornment" aria-hidden="true">
          <ChevronDownIcon size={15} />
        </span>
      </div>
    </div>
  );
};
