---
tags: [radix-ui, components, accessibility, react, kteam-fe-react]
created: 2026-04-20
updated: 2026-04-20
sources: [kteam-fe-react/]
related: [[kteam-fe-react]], [[redux-toolkit-state]]
status: stable
---

# Radix UI Components

## Summary

Radix UI headless component patterns used in kteam-fe-react with shadcn/ui-style custom styling.

## Components Used

- @radix-ui/react-accordion
- @radix-ui/react-avatar
- @radix-ui/react-checkbox
- @radix-ui/react-dialog
- @radix-ui/react-dropdown-menu
- @radix-ui/react-hover-card
- @radix-ui/react-icons
- @radix-ui/react-label
- @radix-ui/react-menubar
- @radix-ui/react-navigation-menu
- @radix-ui/react-popover
- @radix-ui/react-progress
- @radix-ui/react-radio-group
- @radix-ui/react-select
- @radix-ui/react-separator
- @radix-ui/react-slot
- @radix-ui/react-switch
- @radix-ui/react-tabs
- @radix-ui/react-toast
- @radix-ui/react-toggle-group
- @radix-ui/react-tooltip

## Styling Pattern

- Radix provides headless, accessible primitives
- Custom styling via `@layer components` in Tailwind CSS
- class-variance-authority (CVA) for component variants
- tailwind-merge for class merging
- shadcn/ui-style component library in `src/components/ui/`

## Key Conventions

- All interactive elements must have proper aria-labels
- Focus management handled by Radix (no manual focus traps)
- Keyboard navigation supported by default
- Dark/light theme via CSS variables in index.css
