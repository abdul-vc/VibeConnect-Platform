/**
 * Re-export GlobalSearchBar for search components.
 */

export { GlobalSearchBar } from "./GlobalSearchBar.tsx";
export type { GlobalSearchBarProps, SearchResultItem } from "./GlobalSearchBar.tsx";

// Backward-compatible alias
import React from "react";
import { GlobalSearchBar, type GlobalSearchBarProps } from "./GlobalSearchBar.tsx";

export interface GlobalSearchModalProps extends GlobalSearchBarProps {
  readonly isOpen?: boolean;
  readonly onClose?: () => void;
}

export const GlobalSearchModal: React.FC<GlobalSearchModalProps> = (props) => {
  if (props.isOpen === false) return null;
  return <GlobalSearchBar user={props.user} tenantProducts={props.tenantProducts} />;
};
