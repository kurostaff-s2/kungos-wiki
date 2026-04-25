---
tags: [comparison, ui, ux, design-system, tailwind, mui]
created: 2026-04-20
updated: 2026-04-20
sources: [kteam-fe-chief:src/, minimal-material-kit:src/]
related: [[kteam-fe-react]], [[radix-ui-components]], [[redux-toolkit-state]], [[nextjs-dark-theme]]
status: stable
---

# kteam-fe-react vs minimal-material-kit — Design System Comparison

> Date: 2026-04-20
> Target project: `kteam-fe-react` (React 19 + Vite + Tailwind CSS v4 + Radix UI + shadcn/ui pattern + Redux Toolkit + React Router v7)
> Reference project: `minimal-ui-kit/material-kit-react` (MUI v5 + TypeScript + React)

## Summary

Side-by-side analysis of the kteam-fe-react design system against the Minimal Material Kit reference template. The target uses a Tailwind CSS utility-first approach with custom `.kt-*` component classes, while the reference uses MUI v5's `createTheme` system with `styled()` components. The comparison identifies 26 prioritized improvements across 5 severity tiers, with the top 5 changes (scroll-aware header, glassmorphic stat cards, animated searchbar, proper data tables, shared nav data) expected to deliver the biggest visual upgrade.

## Design System Architecture

| Aspect | kteam-fe-react | minimal-material-kit |
|--------|---------------|---------------------|
| Framework | Tailwind CSS v4 | MUI v5 + `styled()` |
| Theme source | `src/index.css` (16k+ lines of utilities) | `src/theme/core/` (modular TS files) |
| Color system | `.kt-btn--primary`, `.kt-stat-card--success` | `createTheme()` with `alpha()`, `brightness()`, `varAlpha()` |
| Shadows | Static `shadow-md`, `shadow-lg` | `custom-shadows.ts` — `z4`, `z8`, `z12` dynamic shadows |
| Layout vars | Hardcoded (260px sidebar, 64px header) | CSS vars: `--layout-nav-vertical-width`, `--layout-header-desktop-height` |
| Typography | Tailwind defaults + `.kt-h1` through `.kt-h6` | `typography.ts` — `h1` through `body3`, `button`, `caption` |
| Icon system | Lucide React (~150 icons) | Iconify (100k+ icons) + SVG Color wrapper |
| Chart lib | ApexCharts | ApexCharts (wrapped in custom `Chart` component) |
| Dark mode | CSS custom properties in `@media (prefers-color-scheme: dark)` | MUI `useColorScheme` with `ColorSchemeProvider` |

## Layout & Navigation

### kteam-fe-react
- Fixed sidebar 260px, collapsible to 72px via JS class toggling
- Fixed header 64px, no scroll effects
- Nav data duplicated in both `Sidebar.jsx` and `Header.jsx`
- No section grouping in sidebar (all items in one flat list)
- No active state indicator animation (just color change)

### minimal-material-kit
- Sidebar uses CSS vars for width transitions (120ms linear)
- Nav sections with collapsible expand/collapse headers
- Header has scroll-aware elevation (shadow appears on scroll)
- Header has glassmorphism backdrop blur on scroll
- Searchbar with slide-down animation + click-away dismiss
- Account popover with conic gradient avatar border + selected menu items

## Component Deep Dive

### Stat Cards
- **kteam-fe-react:** `.kt-stat-card` — simple card with icon, number, trend text. Flat design.
- **Reference:** Glassmorphic gradient background (135deg, lighter→light channels), sparkline chart inline, trending icon (up/down) positioned absolute, shape-square SVG watermark behind content.

### Tables
- **kteam-fe-react:** `Products.jsx` uses raw HTML `<table>` elements (Issues #1, #9 in project wiki).
- **Reference:** Uses MUI `DataGrid` with column definitions, sorting, filtering, pagination built-in.

### Forms
- **kteam-fe-react:** Basic `<input>` elements with `.kt-input` class, focus state via ring.
- **Reference:** MUI `Input` with `InputAdornment` (start/end icons), `disableUnderline`, themed focus states via `sx` props.

### Buttons
- **kteam-fe-react:** `.kt-btn` with variants (primary, secondary, ghost, link) — solid class-based approach.
- **Reference:** MUI `Button` with `variant`, `color`, `size` props, disabled state handling, `startIcon`/`endIcon` slots.

### Login Page
- **kteam-fe-react:** Two-panel layout (branding left, form right), good split-screen approach.
- **Reference:** Centered card layout, progress indicator for multi-step auth, `Backdrop` overlay for loading.

## Animation & Transition

| Feature | kteam-fe-react | minimal-material-kit |
|---------|---------------|---------------------|
| Sidebar collapse | JS class toggle, no easing | CSS transition 120ms linear via CSS vars |
| Header scroll effect | None | Backdrop blur + shadow fade-in |
| Searchbar | Static visible input | Slide-down animation with mount/unmount |
| Card hover | `.kt-card-hover` adds shadow | `hover:` states in sx prop with theme colors |
| Loading states | Spinner animation | LinearProgress with shimmer effect |
| Page transitions | None | Fade-in on route change |

## Responsive Behavior

### kteam-fe-react
- Sidebar collapses to icon-only at `lg` breakpoint
- Header has hamburger menu for mobile
- Dashboard grid: `grid-cols-1 md:grid-cols-2 lg:grid-cols-4`
- Login: two-panel visible only on `lg+`, single panel on mobile

### minimal-material-kit
- Sidebar: `xs` (drawer), `sm` (mini), `md+` (full)
- Header: `layoutQuery` prop controls responsive breakpoint
- Grid: `Grid size={{ xs: 12, sm: 6, md: 3 }}` — more granular control
- Content padding: `--layout-dashboard-content-pt/pb/px` CSS vars for responsive spacing

## Prioritized Improvement List

### P0 — High Impact / High Visibility

1. **Add scroll-aware header elevation** — Header should get a glassmorphic backdrop blur + shadow when user scrolls. Reference: `header-section.tsx` lines 111-115.
2. **Replace raw HTML tables with proper data table component** — `Products.jsx` uses `<table>` elements. Replace with `kt-data-table` or MUI `DataGrid`. Reference: MUI DataGrid column definitions.
3. **Redesign stat cards with glassmorphic gradients and sparkline charts** — Add gradient backgrounds, inline sparkline charts, and trend indicators. Reference: `AnalyticsWidgetSummary` component.
4. **Implement header searchbar with slide-down animation** — Replace static search input with icon-only button that expands. Reference: `searchbar.tsx`.
5. **Add glassmorphic backdrop to header on scroll** — Header background transitions from transparent to frosted glass. Reference: `backdrop-filter: blur(6px)`.

### P1 — Medium Impact / Architectural

6. **Extract nav data to shared source of truth** — Both `Sidebar.jsx` and `Header.jsx` have duplicate navigation arrays (Issue #7 in project wiki).
7. **Add collapsible sections to sidebar navigation** — Group nav items into collapsible sections like reference.
8. **Replace hardcoded layout values with CSS custom properties** — Hardcoded 260px/72px sidebar widths and 64px header height → CSS vars.
9. **Improve avatar/account popover with gradient border** — Reference uses `conic-gradient` border around avatar.
10. **Add page-level fade-in transitions** — Reference has fade-in on route change.

### P2 — Polish / Details

11. Add loading/shimmer states to all async components
12. Add hover/active micro-interactions to all interactive elements
13. Implement proper `focus-visible` styles for keyboard navigation
14. Add breadcrumb navigation
15. Unify icon system with Iconify
16. Add toast/notification system with animation
17. Add empty state illustrations
18. Implement dark mode toggle (not just OS detection)

### Quick Wins (Low Effort, High Visual Impact)

| # | Change | Effort | Impact |
|---|--------|--------|--------|
| 19 | Add `transition-all duration-150` to all buttons and cards | 30min | High |
| 20 | Add `backdrop-blur-sm` to header on scroll | 1hr | High |
| 21 | Add chevron icons to nav items with hover arrow indicator | 1hr | Medium |
| 22 | Replace inline SVG login logo with branded image | 30min | Medium |
| 23 | Add `line-clamp-1` to truncate long text in tables | 30min | Medium |
| 24 | Add `gap` and consistent `padding` to all grid layouts | 1hr | Medium |
| 25 | Add `cursor-pointer` and `select-none` to interactive elements | 30min | Low |
| 26 | Replace `react-switch` with `kt-switch` component | 1hr | Medium |

## References

- Project wiki: [[kteam-fe-react]] → `wiki/ui-ux-review.md` (13 existing issues documented)
- Reference repo: `minimal-ui-kit/material-kit-react` on GitHub
- Stat card reference: `minimal-material-kit/src/sections/overview/analytics-widget-summary.tsx`
- Header reference: `minimal-material-kit/src/layouts/core/header-section.tsx`
- Searchbar reference: `minimal-material-kit/src/layouts/components/searchbar.tsx`
- Account popover reference: `minimal-material-kit/src/layouts/components/account-popover.tsx`
- Dashboard layout: `minimal-material-kit/src/layouts/dashboard/layout.tsx`
- Theme palette: `minimal-material-kit/src/theme/core/palette.ts`
- Layout CSS vars: `minimal-material-kit/src/layouts/dashboard/css-vars.ts`
