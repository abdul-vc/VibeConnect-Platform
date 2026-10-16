/**
 * Shared Date and Time Formatting Utilities.
 * Standardizes datetime rendering across all VibeConnect modules:
 * - formatDate: "Sep 23, 2026"
 * - formatDateTime: "Sep 23, 2026 · 11:36 AM" (browser-local timezone)
 */

export const formatDate = (isoString?: string | null): string => {
  if (!isoString) return "—";
  try {
    const d = new Date(isoString);
    if (isNaN(d.getTime())) return isoString;
    return d.toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
    });
  } catch {
    return isoString;
  }
};

export const formatDateTime = (isoString?: string | null): string => {
  if (!isoString) return "—";
  try {
    const d = new Date(isoString);
    if (isNaN(d.getTime())) return isoString;
    const datePart = d.toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
      year: "numeric",
    });
    const timePart = d.toLocaleTimeString("en-US", {
      hour: "numeric",
      minute: "2-digit",
      hour12: true,
    });
    return `${datePart} · ${timePart}`;
  } catch {
    return isoString;
  }
};
