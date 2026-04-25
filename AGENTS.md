# LLM Wiki

Central wiki at `~/llm-wiki/` — cross-project knowledge for the K-Team ecosystem and local AI stack.

## Structure

```
~/llm-wiki/              # Central wiki
├── raw/                 # Immutable. Drop files here. Never modify.
├── entities/            # Generated pages (people, tools, services)
├── decisions/           # ADR-style decisions
├── patterns/            # Reusable code patterns
├── anti-patterns/       # Things to avoid
├── index.md             # Content catalog — read first for queries
├── log.md               # Append-only operation log
└── AGENTS.md            # This file

Coding-Projects/<proj>/wiki/   # Per-project local wikis
├── components/             # React/Next.js components
├── modules/                # Django modules
├── bugs-resolved/          # Root cause + fix + prevention
├── conventions/            # Project-specific style rules
└── decisions/              # Project-specific decisions
```

## Key Rules

- **NEW SESSION DEFAULT**: Always read `~/llm-wiki/index.md` first, then relevant wiki pages, before touching any code. Understand the state of things from the wiki before consulting the codebase or reading large files.
- **Never modify `raw/`** — it's immutable source material
- **Use `[[wikilink]]` syntax** — required for cross-references and orphan detection
- **Update BOTH central wiki and project local wiki** when work touches both
- **Append to `log.md`** with format: `## [YYYY-MM-DD] <operation> | <title>`
- **Lint with `./lint.sh`** — checks orphans, missing frontmatter, stale entries

## Page Format

All generated pages need YAML frontmatter:

```yaml
---
tags: [django, backend]
created: 2026-04-15
updated: 2026-04-18
sources: [kteam-dj-be:src/auth/]
related: [[Knox Auth]]
status: stable  # stable | experimental | deprecated
---
```

Sections: `## Summary` (one paragraph), `## Details`, `## References`.

## Ops

**Ingest** a new source: read it, extract changes/patterns/anti-patterns, update/create wiki pages, update `index.md`, append to `log.md`. A single ingest may touch 5–15 pages.

**Query**: read `index.md` → relevant pages → raw sources if needed. File good answers back into the wiki.

## Architecture Snapshot

**kteam-dj-be** — Django/DRF backend: PostgreSQL (users, careers, access levels), MongoDB `kuropurchase` (inventory, orders, invoices), MeiliSearch. 155+ API endpoints across `/auth/`, `/kuroadmin/`, `/kurostaff/`, `/rebellion/`, `/careers/`.

**kteam-fe-react** — React 19 + Vite 8 + Redux 5 + Radix UI + Tailwind CSS v4 + React Router v7. 78+ frontend routes.

**Auth**: Knox token-based. Custom auth backend validates phone/username/email. Token stored in localStorage + Redux. Every request sends `Authorization: Token {token}`.

**Multi-tenant**: BusinessGroup model with per-entity permissions (45+ fields: 0=disabled, 1=view, 2=edit).

**Local AI**: Qwen3.6-35B-A3B (primary) + Qwen3.5-35B-A3B (secondary) + DeepSeek-R1-Distill-Qwen-32B (reasoning) via llama.cpp on ports 11434–11435. RTX 3090, CUDA 12.8.

## Anti-patterns (enforced)

- No inline API keys or credentials
- No cloud LLM dependencies (local-only)
- Minimize npm/pip dependencies
