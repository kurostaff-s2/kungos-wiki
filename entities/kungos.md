---
tags: [plan, modernization, backend, frontend, gaming]
created: 2026-04-22
updated: 2026-04-23
sources: [architecture-audit-and-recommendations.md, kuro-gaming-dj-backend analysis]
related: [[kteam-architecture-audit]], [[kteam-system-architecture]], [[kteam-dj-be]], [[kteam-fe-react]]
status: draft
---

# K-Team Stack Modernization Plan (Project Kungos)

## Summary

Master modernization plan for the K-Team platform (Project Code: **Kungos**). Covers phased remediation of 97 audit issues across kteam-dj-be (Django/DRF) and kteam-fe-chief (React 19), plus integration of the kuro-gaming-dj-backend e-commerce codebase (5 new apps, 12 MongoDB collections, 25 API endpoints). Estimated 340–520 hours (likely 420h / 10.5 weeks). Single deployment at program end with git revert + DB backup restore rollback path. Six phases (0–4 plus 3b) with P0/P1/P2 intra-phase prioritization. Two parallel workstreams: core modernization and gaming integration, with explicit gating on Phase 1 completion.

## Details

### Scope

- **Backend:** Django security hardening, auth modernization (Knox → SimpleJWT), access-control refactor, MongoDB consolidation (per-BG → single DB with `bgcode`), dependency cleanup, Redis/Celery, PDF stack consolidation, gaming app integration (accounts, products, orders, payment, games)
- **Frontend:** localStorage auth removal, cookie-ready bootstrap, React Query migration, crash fixes, code splitting, form validation, gaming storefront migration, kurogg-nextjs retirement
- **Data:** Tenant context expansion (bg_code, entity, branches), MongoDB 12-collection migration to `kuropurchase`, PostgreSQL user model reconciliation, order schema reconciliation

### Phases

| Phase | Min | Likely | Max |
|---|---|---|---|
| 0 — Security and Program Setup | 48h | 52h | 56h |
| 1 — Tenant Context, Access Control, Data-Layer Refactor | 120h | 130h | 140h |
| 2 — Frontend State, Session, Stability Modernization | 72h | 84h | 96h |
| 3 — Auth, Redis, Celery, API Compatibility, Operational Core | 104h | 116h | 128h |
| 3b — Gaming Multi-Tenant Integration | 28h | 32h | 36h |
| 4 — Testing, CI/CD, Production Readiness, Go-Live | 144h | 156h | 168h |
| Gaming-specific additions | 160h | 180h | 200h |
| Overlap eliminated | -120h | -140h | -140h |
| **Total** | **340h** | **420h** | **520h** |

### Governance

Two parallel workstreams with explicit gating:
- **Core modernization** (primary workstream, Phases 0–4)
- **Gaming integration** (parallel workstream, gates on core Phase 1 stability)

### Key decisions

- Python 3.12 baseline, Python 3.13 deferred
- `django-environ` for environment management
- SimpleJWT replaces Knox
- React Query for server state, Redux for UI state only
- Single MongoDB database with `bgcode` tenant field
- Single deployment at program end (no staging, no canary)
- Rollback: git revert + DB backup restore

## References

- Full plan: [[kungos]]
- Audit source: [[kteam-architecture-audit]]
- Counter-review: [[kteam-stack-modernization-plan-counter]]
- Gaming backend: kuro-gaming-dj-backend
