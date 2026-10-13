/**
 * Theme Context & Provider.
 *
 * Provides centralized dark / light theming with seamless system preference fallback
 * and persistent storage exclusively for the visual 'vibeconnect_theme' key.
 */

import React, { createContext, useContext, useEffect, useState, useCallback } from "react";

export type Theme = "dark" | "light";

interface ThemeContextType {
  readonly theme: Theme;
  readonly toggleTheme: () => void;
  readonly setTheme: (theme: Theme) => void;
}

const THEME_STORAGE_KEY = "vibeconnect_theme";

const ThemeContext = createContext<ThemeContextType | undefined>(undefined);

function getInitialTheme(): Theme {
  if (typeof window === "undefined") {
    return "dark";
  }

  try {
    const stored = localStorage.getItem(THEME_STORAGE_KEY);
    if (stored === "dark" || stored === "light") {
      return stored;
    }
  } catch {
    // Fall back gracefully if storage is restricted
  }

  if (window.matchMedia && window.matchMedia("(prefers-color-scheme: light)").matches) {
    return "light";
  }

  return "dark";
}

export const ThemeProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [theme, setThemeState] = useState<Theme>(getInitialTheme);

  const applyTheme = useCallback((newTheme: Theme) => {
    setThemeState(newTheme);
    document.documentElement.setAttribute("data-theme", newTheme);
    try {
      localStorage.setItem(THEME_STORAGE_KEY, newTheme);
    } catch {
      // Storage access gracefully handled
    }
  }, []);

  useEffect(() => {
    // Ensure the root attribute matches the current state
    document.documentElement.setAttribute("data-theme", theme);
  }, [theme]);

  // Listen to system preference changes if user hasn't explicitly set a stored preference
  useEffect(() => {
    const mediaQuery = window.matchMedia("(prefers-color-scheme: dark)");
    const handleChange = (e: MediaQueryListEvent) => {
      try {
        const stored = localStorage.getItem(THEME_STORAGE_KEY);
        if (!stored) {
          applyTheme(e.matches ? "dark" : "light");
        }
      } catch {
        applyTheme(e.matches ? "dark" : "light");
      }
    };

    mediaQuery.addEventListener("change", handleChange);
    return () => mediaQuery.removeEventListener("change", handleChange);
  }, [applyTheme]);

  const toggleTheme = useCallback(() => {
    applyTheme(theme === "dark" ? "light" : "dark");
  }, [theme, applyTheme]);

  const setTheme = useCallback(
    (newTheme: Theme) => {
      applyTheme(newTheme);
    },
    [applyTheme]
  );

  return (
    <ThemeContext.Provider value={{ theme, toggleTheme, setTheme }}>
      {children}
    </ThemeContext.Provider>
  );
};

export function useTheme(): ThemeContextType {
  const context = useContext(ThemeContext);
  if (!context) {
    throw new Error("useTheme must be used within a ThemeProvider");
  }
  return context;
}
