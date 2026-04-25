---
tags: [nextjs, app-router, routing, frontend]
created: 2026-04-20
updated: 2026-04-20
sources: [rebellion-nextjs/, renderedge-nextjs/]
related: [[nextjs-dark-theme]]
status: stable
---

# Next.js 14 App Router

## Summary

Next.js 14 App Router conventions used across rebellion-nextjs and renderedge-nextjs projects.

## Key Conventions

- **Directory-based routing**: `src/app/<route>/page.jsx`
- **Layouts**: `src/app/layout.jsx` for shared layout, per-route layouts for nested sections
- **Server Components**: Default component type (no 'use client' unless needed)
- **Client Components**: Explicit 'use client' directive when interactivity required
- **Metadata API**: `generateMetadata()` function for SEO
- **Loading states**: `loading.jsx` files for skeleton UI
- **Error boundaries**: `error.jsx` and `global-error.jsx`

## Project Differences

- **rebellion-nextjs**: Next.js 14, single-site structure
- **renderedge-nextjs**: Next.js 16 with Turbopack, multiple sub-sites (workstations, servers, business-desktops)

## Anti-Patterns

- No Pages Router — use App Router consistently
- No unnecessary 'use client' — prefer Server Components
