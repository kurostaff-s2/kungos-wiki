---
tags: [nextjs, react, javascript, e-commerce, tailwind]
created: 2026-04-20
updated: 2026-04-20
sources: [renderedge-nextjs/README.md, renderedge-nextjs/src/]
related: [[nextjs-app-router]], [[tailwind-css-v3]]
status: stable
---

# renderedge-nextjs

## Summary

Next.js 16 static site for RenderEdge — high-performance workstation and server solutions for professionals. Built with Tailwind CSS 3, React 18, JavaScript, and Turbopack.

## Tech Stack

- **Framework:** Next.js 16
- **Styling:** Tailwind CSS 3
- **Language:** React 18 / JavaScript
- **Build:** Turbopack
- **Linting:** ESLint

## Pages

| Page | Description |
|------|-------------|
| `/` | Homepage with hero, products, and info sections |
| `/workstations` | Professional workstations overview |
| `/servers` | Rackmount servers overview |
| `/business-desktops` | Enterprise desktop solutions |
| `/professional-workstations/*` | Industry-specific workstation solutions |
| `/server-solutions/*` | Server solution pages |
| `/components` | Hardware component browser |
| `/contact-us` | Contact information |
| `/faq` | Frequently asked questions |

## Design System

### Colors

| Token | Hex | Usage |
|-------|-----|-------|
| `primary` | `#0a0a0a` | Headings, primary text |
| `secondary` | `#1a1a1a` | Secondary text |
| `accent` | `#2563eb` | Links, buttons, highlights |
| `muted` | `#6b7280` | Supporting text |
| `light` | `#f9fafb` | Backgrounds |

### Typography

- **Font:** Proxima Nova (primary), Inter / system-ui (fallback)
- **H1:** `clamp(1.75rem, 4vw, 3rem)` — fluid responsive sizing
- **H2:** `clamp(1.5rem, 3vw, 2.25rem)`
- **Body:** 1rem, 1.75 line-height

### Key Components

- `.container-max` — 1280px max-width centered container
- `.btn-primary` — Dark filled button
- `.btn-secondary` — Outlined white button
- `.btn-accent` — Blue accent button
- `.card-base` — White card with subtle border and shadow

## Running

```bash
npm run dev    # development server
npm run build  # production build
npm run export # static site export
npm run lint   # ESLint
```

## References

- [[nextjs-app-router]] — Next.js App Router patterns
- [[tailwind-css-v3]] — Tailwind CSS 3 conventions
