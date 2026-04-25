---
tags: [nextjs, react, landing-page, tailwind]
created: 2026-04-20
updated: 2026-04-20
sources: [rebellion-nextjs/README.md, rebellion-nextjs/src/]
related: [[nextjs-dark-theme]], [[nextjs-app-router]], [[rebellion-esports]]
status: stable
---

# rebellion-nextjs

## Summary

Next.js 14 App Router landing page for Rebellion Esports, India's premier gaming café chain. Built with Tailwind CSS, Framer Motion, and Lucide React icons.

## Tech Stack

- **Framework:** Next.js 14 (App Router)
- **Styling:** Tailwind CSS
- **Animations:** Framer Motion
- **Icons:** Lucide React
- **Fonts:** Space Grotesk (headings), Inter (body)
- **Linting:** ESLint

## Project Structure

```
src/
├── app/
│   ├── layout.tsx      # Root layout, metadata, SEO, structured data
│   ├── page.tsx        # Landing page
│   └── globals.css     # Tailwind directives, custom styles
└── components/
    ├── Hero.tsx          # Hero section with animated background
    ├── Facilities.tsx    # PC Zone, Console Zone, VR, Racing Sim
    ├── Games.tsx         # Games library with categories
    ├── Pricing.tsx       # Pricing plans and add-ons
    ├── Branches.tsx      # Branch locations and details
    ├── Tournaments.tsx   # Upcoming tournaments
    ├── Navbar.tsx        # Responsive navigation
    └── Footer.tsx        # Footer with branch info
```

## Features

- Dark gaming theme with gradient accents
- Fully responsive (mobile → desktop)
- Smooth scroll animations (Framer Motion)
- SEO optimized (metadata, OpenGraph, Twitter cards)
- Schema.org structured data (LocalBusiness)
- Accessible (ARIA labels, semantic HTML)

## Branches

- **Madhapur** — HITEC City, 30+ PCs, PS5 Zone, VR Area
- **LB Nagar** — East Hyderabad, Console Zone, Racing Sim
- **Kompally** — Affiliate (Cafe Game Theory), LAN Events

## Running

```bash
npm install
npm run dev    # development server
npm run build  # production build (verify zero errors)
npm start      # production server
```

## References

- [[rebellion-nextjs/src/app/layout.tsx]] — SEO and structured data implementation
- [[rebellion-nextjs/src/components/Hero.tsx]] — Framer Motion animation patterns
