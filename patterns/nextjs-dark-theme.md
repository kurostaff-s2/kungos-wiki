---
tags: [nextjs, dark-theme, tailwind, styling]
created: 2026-04-20
updated: 2026-04-20
sources: [rebellion-nextjs/, renderedge-nextjs/]
related: [[nextjs-app-router]]
status: stable
---

# Next.js Dark Theme

## Summary

Dark theme implementation pattern used across Next.js projects (rebellion-nextjs, renderedge-nextjs) with Tailwind CSS.

## Implementation

- **rebellion-nextjs**: Uses Tailwind CSS with custom dark theme colors, gradient accents, Space Grotesk + Inter fonts
- **renderedge-nextjs**: Uses Tailwind CSS v3 with dark primary (#0a0a0a), blue accent (#2563eb), Proxima Nova + Inter fonts

## Key Patterns

- Dark backgrounds with light text for main content
- Accent colors for CTAs, links, and interactive elements
- Gradient overlays for hero sections and cards
- Consistent spacing with Tailwind's spacing scale
- Semantic color usage (not hardcoded hex in JSX)

## Anti-Patterns

- No inline styles for theming — use Tailwind classes
- No hardcoded color values in components — define in Tailwind config
- No light/dark theme toggling (both projects are dark-only)
