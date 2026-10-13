\---

name: vibeconnect-design

description: Enforce VibeConnect's executive-grade design system (Frosted Pearl / Midnight Glass themes) for all UI work. Trigger on any component, page, or layout request.

\---



\# VibeConnect Design Rules



\- Use existing themes only: Frosted Pearl (light), Midnight Glass (dark). Never introduce new colors outside the approved palette.

\- No generic AI-SaaS look: no purple-blue gradient hero sections, no default Bootstrap spacing, no stock icon sets outside Tabler/Lucide.

\- Typography: consistent scale, max 2 font weights.

\- All interactive controls minimum 44px touch target.

\- Desktop: tables. Mobile: cards. Always both.

\- Match existing AppShell, navigation rail, and focus-state patterns already in the codebase — inspect existing components before creating new ones.

\- Prefer shadcn/ui + Tailwind for consistency with the existing stack.

