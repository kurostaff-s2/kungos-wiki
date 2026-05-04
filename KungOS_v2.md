# KungOS v2 — Unified Modernization, Tenant Architecture, and Extensibility Plan

**Project Code:** KungOS  
**Prepared:** 2026-04-22  
**Rewritten:** 2026-04-27  
**Status:** Execution plan  
**Document Type:** Architecture, implementation, cutover, and operational runbook  

---

## Executive Summary

K-Team is a dual-stack business platform built on a React frontend and a Django/DRF backend, with PostgreSQL, MongoDB, and MeiliSearch in the data layer. The audit identified **97 issues** across security, performance, maintainability, and scalability: 12 critical, 24 high-severity, 31 medium-severity, and 30 low-severity. The most important compounding problems are hardcoded credentials, duplicated access-control logic, pandas-based permission filtering, per-request MongoDB client creation, no caching or job queue, no test coverage, and frontend state/data-fetching patterns that do not scale.

> **📚 Database Source of Truth:** All PostgreSQL tables (35), MongoDB collections (30), column details, constraints, indexes, and migration status are documented in [`kungos_v2_db.md`](./kungos_v2_db.md). This is the single authoritative reference — superseding all older kungos documents. See §Database section below for key decisions; refer to `kungos_v2_db.md` for exact column names, types, and FK relationships.

A second codebase — `kuro-gaming-dj-backend` — provides e-commerce functionality for custom/prebuilt PC sales (product catalog, cart, wishlist, addresses, orders, payment processing, game catalog, CMS) but has its own critical issues: 9+ hardcoded credentials, Django 4.1.13 (EOL), use of `djongo` (deprecated ORM bridge), no multi-tenant support, no DRF serializers for products/games, and no authentication on admin endpoints. The companion frontend `kurogg-nextjs` is a thin reverse proxy with zero backend logic and should be retired entirely.

**This v2 plan adopts the counter-review assumption that no changes will be deployed until the full modernization program is complete.** Because of that, this plan intentionally removes canary rollout, staging-first rollout, feature flags for auth migration, and mid-program production cutovers, and replaces them with one final deployment supported by one rollback path: git revert plus database backup restore.

This is a **phased modernization, not a rewrite**. The plan keeps the current strong foundations — Django 5.2, DRF 3.15, React 19, Vite 8, PyMongo, PostgreSQL, MongoDB, MeiliSearch, Radix UI, and Recharts — while replacing unmaintained or upgrade-hostile dependencies and standardizing cross-cutting platform concerns.

This rewrite incorporates **eight critical architectural improvements** identified by the counter-review:

1. **Observability** — Correlation IDs, structured JSON logging, Sentry integration, health endpoints
2. **Cross-store consistency** — Outbox pattern for PostgreSQL↔MongoDB side-effects
3. **Enforced tenant isolation** — PostgreSQL RLS + MongoDB `TenantCollection` wrapper
4. **Interface-first extensibility** — Python Protocols for domain services defined now, not later
5. **Configuration-driven brands** — `TenantConfig` JSON model for runtime brand behavior
6. **Domain event bus** — `emit()` + `@on()` pattern to decouple cross-domain services
7. **Health & monitoring** — `/api/health/` endpoints, Sentry tags, dead-letter queue alerts
8. **Shared utilities purity** — Business-logic helpers moved out of generic shared modules

> **📝 Naming Note — `plat/` vs `platform/`:** The `platform/` directory name was changed to `plat/` during implementation to avoid a Python built-in module name collision. Python's standard library `platform` module is imported by pydantic, meilisearch, uuid, and many other packages. A local `platform/` package shadows the built-in, causing `AttributeError: module 'platform' has no attribute 'system'`. All references in this document to the package directory use `plat/`; the plan originally used `platform/`.

---

## Planning Assumptions

### Delivery model

No production deployment will occur during the modernization program. Development happens in local/dev environments only, and go-live occurs as a single deployment at the end of the program.

### Environment model

The environment strategy for this program is **dev + prod only**. A staging environment is explicitly out of scope for the modernization period because no intermediate deployment validation is being performed in production-like stages.

### Rollout model

Canary deployment, phased rollout, and feature-flag infrastructure are out of scope. The program ships exactly once: a single deployment at the end of the modernization program. All auth coexistence (Knox → SimpleJWT, kteam/gaming user merge) is handled in code during development, never by deploying two systems side by side in production.

### Rollback model

There is one rollback path for the final cutover: revert the deployment commit and restore the pre-cutover database backup. This replaces the previous idea of per-phase rollback playbooks. The rollback runbook is documented in the Cutover Checklist section (items 39–43). Rollback requires approval from the Modernization Owner.

### Runtime baseline

Python 3.12 is retained as the baseline for this modernization cycle. Python 3.13 is deferred to a separate post-modernization upgrade. Django 5.2 already supports Python 3.12 and the audit did not identify Python version itself as the primary issue.

### Workstream governance

The program has two workstreams that run in parallel with explicit gating:

- **Core modernization** — the baseline security, refactoring, and platform hardening work (Phases 0–4). Primary workstream with its own lead.
- **Gaming integration** — a parallel workstream that adds 5 apps, 12 MongoDB collections, 25 API endpoints, and associated frontend migration. Owns its own lead and reporting, but shares infrastructure work with core.

**Gating rule:** Gaming integration cannot finish before core Phase 1 is stable. Gaming multi-tenant integration (Phase 3b) requires the consolidated MongoDB database and per-BG routing removal to be complete. Gaming code integration (Phase 3) can begin once core Phase 1 tenant context and MongoDB consolidation are verified.

**Merge gate:** Gaming storefront pages may not migrate to `kteam-fe-chief` until storefront parity is verified. `kurogg-nextjs` is retired only after all gaming features are confirmed working in the unified frontend.

### Gaming integration scope

The following will be integrated into the unified backend:

- Domain modules under `kungos_dj/domains/`: `accounts/`, `orders/`, `eshop/`, `products/`, `vendors/`, `teams/`, `search/`, `shared/`
- 12 MongoDB collections added to `kuropurchase`: `prods`, `builds`, `kgbuilds`, `custombuilds`, `components`, `accessories`, `monitors`, `networking`, `external`, `games`, `kurodata`, `lists`, `presets`
- 25 new API endpoints covering product catalog, cart, wishlist, addresses, orders, payments, game catalog
- Custom PC builder admin functionality (custombuilds + customprice)
- Google Merchant Center integration (product sync to Google Shopping)
- CMS content management (hero banners via `kurodata`)
- Site map generation (XML sitemap → S3)

The following will be retired:

- `kurogg-nextjs` — thin reverse proxy with zero backend logic, no code to port; frontend pages migrate to `kteam-fe-chief`

---

## Architecture Principles

### 1. Tenant-first everywhere

Tenant context is a platform concern, not a view concern. Every request, query, event, job, and write path must carry `bg_code`, `division`, and `branch_code` scope explicitly. Data access must fail closed when that scope is missing.

### 2. Observable by default

Every request must be traceable end-to-end. A production incident should be answerable through request IDs, structured logs, Sentry traces, health endpoints, and replayable jobs — not manual print-debugging.

### 3. Interface before implementation

Core business capabilities must be defined by contracts first and brand-specific behavior second. This prevents the second brand or second business type from forcing a costly extraction later.

### 4. Configuration over hardcoding

Brand rules, payment providers, wallet behavior, branch capabilities, feature access, and theming belong in tenant configuration, not in scattered `if brand == ...` blocks.

### 5. Durable consistency across stores

Any workflow that writes to PostgreSQL and MongoDB must use a recoverable pattern. No business-critical flow may rely on "write here, then write there, hope nothing crashes in between."

### 6. Events for extension, services for ownership

A service owns a business action. Events notify other domains about it. This keeps direct coupling low and lets new brand behaviors attach without rewriting the original service.

### 7. Repository → Service → View layering

Data access lives in repositories. Business logic lives in services. HTTP lives in views. This layering is testable and makes cross-store operations explicit.

### 8. Domain-as-Django-app, Brand-as-sub-package

Domains are Django apps under `kungos_dj/domains/`: `accounts/`, `orders/`, `eshop/`, `products/`, `vendors/`, `teams/`, `cafe/`, `esports/`. Brand-specific logic lives in sub-packages. This keeps domains reusable across brands and avoids generic flat-app sprawl.

---

## Target Architecture

### Backend platform baseline

| Component | Version | Notes |
|---|---|---|
| Python | 3.12 | Baseline |
| Django | 5.2.x | Active, current |
| DRF | 3.15.x | Active, current |
| PostgreSQL | latest | Relational backbone |
| MongoDB | latest | Document store |
| PyMongo | latest | MongoDB driver |
| MeiliSearch | latest | Search |
| Redis | latest | Cache (optional A) |
| Celery | latest | Async tasks (optional A) |
| gunicorn | latest | WSGI server |
| SimpleJWT | latest | JWT auth (replaces Knox) |
| drf-spectacular | latest | OpenAPI docs |
| django-environ | latest | Env/settings management |
| pydantic | latest | Data validation |
| boto3 | latest | S3 storage |
| weasyprint | latest | PDF generation |
| pypdf | latest | PDF reading |

### Frontend platform baseline

| Component | Version | Notes |
|---|---|---|
| React | 19 | Current |
| Vite | 8 | Current |
| React Router | v7 | Current |
| Tailwind CSS | v4 | Current |
| Radix UI | latest | Current |
| Lucide React | latest | Icons |
| Recharts | latest | Charts |
| TanStack Table | latest | Tables |
| React Query | latest | Server state |
| React Hook Form | latest | Form validation |
| dayjs | latest | Date handling (replaces `moment`) |

### Unified application structure

```
kteam-dj-chief (unified backend)
├── backend/
│   ├── settings.py          — Django settings, django-environ
│   ├── urls.py              — URL routing (domain-based)
│   └── logging.py           — Structured JSON logging
├── plat/                    — Cross-cutting platform primitives
│   ├── shared/              — Pure utilities (no side effects)
│   ├── tenant/              — TenantContext, TenantConfig, TenantCollection
│   ├── observability/       — CorrelationMiddleware, TenantContextMiddleware, logging
│   ├── events/              — Domain event bus (emit, register, handlers)
│   ├── outbox/              — OutboxEvent model, processor, replay
│   └── health/              — /health/live, /health/ready
├── kungos_dj/               — Django app (renamed from `teams/`)
│   └── domains/             — Domain-based modules
│       ├── accounts/        — Finance: invoices, payments, ledgers, vouchers
│       ├── orders/          — Orders: estimates, in-store, tp, service requests
│       ├── eshop/           — E-commerce: online retail orders
│       ├── products/        — Product catalog, inventory, stock
│       ├── vendors/         — Vendor management
│       ├── teams/           — Workforce: employees, attendance, payroll
│       ├── search/          — MeiliSearch domain
│       └── shared/          — Cross-domain utilities
├── cafe/                    — Cafe platform (separate Django app, shared multi-tenant)
│   ├── stations/            — POS station management
│   ├── sessions/            — Gaming sessions (caf_platform_sessions)
│   ├── wallet/              — Cafe wallet
│   └── food-orders/         — Cafe food orders
├── rebellion/               — Rebellion brand app
│   └── esports/             — Esports (tournaments, players, teams)
├── users/                   — Identity & auth (CustomUser, JWT, RBAC)
├── careers/                 — Career management
└── kungos-admin/            — Sys Admin tenant bootstrap
```

**Note:** `kungos_dj/` replaces the old `teams/` monolith. Domain modules under `kungos_dj/domains/` are clean, testable, and reusable across brands.

### App structure rationale

| Original | New | Reason |
|---|---|---|
| `kuroadmin/` | `kungos_dj/domains/` | Monolith → domain modules. Clean, testable, reusable. |
| `kurostaff/` | merged into `kungos_dj/domains/` | Shared utilities → `plat/shared/`. Request handlers → domain modules. |
| Flat gaming apps | `kungos_dj/domains/eshop/` | E-commerce is a domain, not a brand. Reusable across Kuro Gaming, RenderEdge, etc. |
| — | `cafe/` (separate Django app) | Cafe platform: sessions, wallet, food-orders. Shared multi-tenant. |
| — | `rebellion/esports/` sub-package | Esports is a domain within the Rebellion brand. |
| — | `kungos-admin/` Django app | Sys Admin tenant bootstrap, separate from business back-office. |

### Data responsibilities

| Store | Responsibility |
|---|---|
| **PostgreSQL** | Identity (`CustomUser`), wallets, **all orders** (`orders_core` + detail tables), cafe sessions (`caf_platform_sessions`), durable workflow state, outbox events, tenant configuration, financial records |
| **MongoDB** | High-volume operational collections (`products`, `inwardpayments`, `inwardinvoices`, `outward`, `stock_register`), catalog data, (`players`, `tournaments`), cafe operations (`stations`, `game_library`) |

### MongoDB tenancy target

Move from one MongoDB database per Business Group to a single MongoDB database (`KungOS_Mongo_One`) with `bgcode`, `division`, and `branch_code` fields on documents. Supported by compound indexes: `(bgcode, division)`, `(bgcode, division, branch_code)`, `(bgcode, userid)`. Simplifies schema changes, backups, cross-BG aggregation, and query-level tenant enforcement.

---

## Goals

The goals of this program are:

- Eliminate the 12 critical issues identified in the audit before go-live.
- Eliminate the 9+ hardcoded credentials and critical security issues in the gaming backend before merge.
- Remove upgrade-hostile and deprecated dependencies from the backend and frontend.
- Replace duplicated access-control and pandas-based filtering with a centralized tenant-aware permission system.
- Consolidate MongoDB tenancy routing from per-BG databases to query-level tenant filtering using `bgcode`, `division`, and `branch_code`.
- Integrate 5 gaming apps with 12 MongoDB collections, 25 API endpoints, and e-commerce functionality into the unified platform.
- Reconcile user models between kteam-dj-chief and kuro-gaming-dj-backend (both use `CustomUser` but with different schemas).
- Migrate the frontend toward modern server-state handling and safer auth/session management.
- Introduce caching, background jobs, documentation, testing, logging, and CI at the correct points in the program.
- Retire `kurogg-nextjs` and migrate gaming storefront pages to `kteam-fe-chief`.
- Establish the unified identity model (phone = universal key, shared wallet) that enables the post-core GGleap-style cafe platform.
- **Implement 8 architectural improvements:** observability, cross-store consistency, enforced tenant isolation, domain protocols, tenant config, event bus, health monitoring, and shared utilities purity.

---

## Post-Core Expansions

These workstreams are designed during the core program but implemented after core Phases 0–4 ship. They depend on the core modernization's unified identity model, tenant context, and shared wallet foundation.

### GGleap-Style Gaming Cafe Platform

**Scope:** Upgrade Rebellion brand from esports-only to full cafe management (GGleap-style).

**Key design:**
- Phone is the universal key across all three brands: Kuro Gaming (cafe), RenderEdge (retail), Rebellion (esports)
- Shared wallet bridges cafe sessions, tournament prizes, and retail purchases
- Separate data stores: esports (`players`, `tournaments` in MongoDB) vs cafe (`caf_platform_sessions` in PostgreSQL, `stations`, `game_library` in MongoDB)
- Walk-in mode (no login) + JWT mode (registered) for cafe check-in

**Detailed plan:** See [[kungos-cafe-platform]]

**Estimated effort:** 230–345 hours total (Backend+Dashboard 120–180h + Station Desktop 110–165h, separate from core modernization)

### Google Play Game Services / Senet Integration

**Status:** Explicitly rejected by user. No plans for GPGS/Senet integration.

---

## In Scope

### Backend

- Django security hardening, auth modernization, access-control refactor, MongoDB query/model refactor, dependency cleanup, API standardization, pagination, logging, testing, Redis, Celery, and PDF stack consolidation.
- Gaming backend integration: 5 apps, 12 MongoDB collections, 25 API endpoints, payment processing (Cashfree + UPI), custom PC builder admin, GMC integration, CMS, site map generation.
- User model reconciliation: merge kteam and gaming `CustomUser` schemas.
- Order schema reconciliation: merge gaming 11-stage PC build order lifecycle with kteam order management.
- Product management consolidation: gaming and kteam both manage the same 9 MongoDB collections.
- **Platform primitives:** Observability, outbox, tenant enforcement, domain protocols, event bus, `TenantConfig`.

### Frontend

- LocalStorage auth removal, cookie-ready auth bootstrap, React Query migration, crash fixes, route/code splitting, form validation improvements, server-state cleanup, loading/empty states, and incremental modernization of legacy pages.
- Gaming storefront pages: product catalog, prebuilt PC builds, custom PC builder, shopping cart, wishlist, address management, checkout flow, order tracking (11-stage), payment pages, game catalog, CMS banner rendering.
- Retirement of `kurogg-nextjs`.

### Data model and tenancy

- Tenant context expansion to include Business Group, division, and branch scope in the active session model.
- MongoDB consolidation from one database per Business Group to a single database with tenant fields and compound indexes.
- Add `bgcode` field to all 12 gaming MongoDB collections and all 5 gaming PostgreSQL models (Cart, Wishlist, Addresslist, Orders, OrderItems).
- PostgreSQL RLS for tenant-scoped tables.
- MongoDB `TenantCollection` wrapper for enforced tenant filtering.

### Deferred items

CI/CD gating, deployment automation, protected-branch enforcement, production dashboards, and final production runbooks are deferred to the final phase because nothing ships during the modernization period.

---

## Production Migration Tool

A production-ready migration tool has been implemented and deployed to support database restoration during the final cutover.

### Django Management Commands (`teams/management/commands/`)

| Command | Purpose |
|---|---|
| `restore_kuropurchase` | Parse MongoDB 8.0+ concurrent dump, restore with division population |
| `backup_kuropurchase` | Pre-restore backup of all collections to JSON |
| `deploy_restore` | Production deployment orchestrator (backup → restore → verify) |

### Features

- Parses MongoDB 8.0+ concurrent dump format (49.88 MB, 47,009 docs)
- Populates `division` field for tenant isolation (migrated from brand slugs to div_code cascade codes)
- Handles duplicate `_id`s gracefully (52 duplicates skipped during initial restore)
- S3 support: `--s3-key s3://bucket/path/dump`
- Confirmation prompts for safety: `--force` bypasses confirmation
- Verification mode: `--verify` checks division population post-restore
- Division distribution reports: `--output report.json`
- Custom MongoDB connection: `--host`, `--port`

### Usage

```bash
# Pre-restore backup
python manage.py backup_kuropurchase

# Restore from local dump
python manage.py restore_kuropurchase --dump /path/to/dump --restore

# Restore from S3 backup (production cutover)
python manage.py deploy_restore --s3-key s3://bucket/path/dump --verify

# Dry run to preview
python manage.py restore_kuropurchase --dump /path/to/dump --dry-run
```

### Division Distribution (from restore + division field migration)

| Division (div_code) | Brand | Documents | Percentage |
|---|---|---|---|
| `KURO0001_001` | kurogaming | 15,216 | 22.2% |
| `KURO0001_002` | rebellion | 17,127 | 25.0% |
| `DUNE0003_001` | rebellion | 36,099 | 52.8% |
| **Total** | — | **68,443** | **100%** |

### Collections Restored

| Collection | Documents | Division |
|---|---|---|
| `purchaseorders` | 15,366 | KURO0001_001 |
| `inwardpayments` | 21,546 | KURO0001_002 + DUNE0003_001 |
| `estimates` | 4,320 | KURO0001_001 |
| `inwardInvoices` | 16 | KURO0001_001 |
| `products` | 82 | KURO0001_002 |
| `outwardDebitNotes` | 13 | KURO0001_001 |
| `misc` | 5,554 | mixed divisions |

### Rollback

Pre-restore backup is automatically created. Git revert is the rollback path.

Full documentation: `teams/management/commands/README.md` and `PRODUCTION_DEPLOYMENT.md`.

---

## Dependencies

### Keep

| Package / platform | Decision | Reason |
|---|---|---|
| Django 5.2.x | Keep | Active/current |
| DRF 3.15.x | Keep | Active/current |
| PyMongo | Keep | Real MongoDB access layer |
| PostgreSQL | Keep | Relational backbone |
| MongoDB | Keep, single database | Consolidated tenancy model |
| MeiliSearch | Keep | Active, already part of stack |
| React 19 / Vite 8 / Radix UI / Recharts | Keep | Current stack remains viable |

### Remove or phase out

| Package | Status | Replacement |
|---|---|---|
| `django-rest-knox` | Unmaintained / phase out | `djangorestframework-simplejwt` |
| `djongo5` (gaming) | Deprecated / remove | No replacement; use PyMongo directly |
| `djongo` (gaming) | Deprecated / remove | No replacement; use PyMongo directly |
| `boto` v2 | Deprecated / remove | `boto3` |
| `PyPDF2` | Duplicate/fork overlap / remove | `pypdf` |
| `xhtml2pdf` primary usage | Old stack / phase out | `weasyprint` |
| `pandas` for permission filtering | Overkill / remove | Native ORM and query-level tenant filters |
| `moment` | EOL / remove | `dayjs` |
| `pyexcel-ods` (gaming) | Legacy game import | Admin interface or management command |
| `numpy` (gaming) | Not directly used | Review and remove if unused |

### Requirements alignment decisions

- Standardize on **`django-environ`** for Django settings and environment management.
- Include **`pydantic`** in target backend requirements (referenced but missing).

---

## Recommended Backend Requirements

```txt
Django==5.2.*
djangorestframework==3.15.*
djangorestframework-simplejwt
drf-spectacular
django-cors-headers
django-environ
pydantic

psycopg[binary]
pymongo
meilisearch

# Optional (see Optional A):
redis
celery
channels
channels-redis
daphne

boto3
weasyprint
pypdf

requests
phonenumbers
django-phonenumber-field
python-dateutil

gunicorn
```

### Operational packages (backup system)

| Package | Role | Status |
|---|---|---|
| `django-dbbackup` | Backup command | **ACTIVE** — v5.3.0 (Apr 2026) |
| `django-storages` | Uploads backups to S3 | **ACTIVE** — v1.14.6 (Apr 2025) |

`django-crontab` is removed — it has been unmaintained since 2016. Scheduling is handled by Celery Beat (Preferred) or system crontab (fallback). See `CAFE_PLATFORM.md` §17.5 (Gap 5) for expired sessions scheduler implementation.

---

## Dependency Strategy

### Critical dependency chains

| # | Prerequisite | Depends on it | Which phase |
|---|---|---|---|
| 1 | Tenant-context expansion defined + permission abstraction implemented | **Pandas removal** — cannot replace pandas filtering until central permission abstraction exists | Phase 1 P0 |
| 2 | Tenant-context expansion + pandas removal | **MongoDB consolidation** — query-level tenant filtering must exist before per-BG routing removal | Phase 1 P0→P1 |
| 3 | MongoDB consolidation: all documents migrated with `bgcode`/`division`/`branch_code`, compound indexes created | **Removal of per-BG database routing** (`client[bg.db_name]`) | Phase 1 P1 |
| 4 | Frontend cookie-readiness (tokens no longer from `localStorage`) | **SimpleJWT cutover** — switching auth without cookie-ready frontend causes login failures | Phase 2 P0→Phase 3 P0 |
| 5 | PostgreSQL user model reconciliation | **Merged auth/session rollout** — activating JWT before user reconciliation causes token mismatches | Phase 1 P0→Phase 3 P0 |
| 6 | MongoDB consolidation + per-BG routing removal | **Gaming multi-tenant integration (Phase 3b)** | Phase 3b |
| 7 | Gaming app code integration (Phase 3) | **Gaming multi-tenant integration (Phase 3b)** | Phase 3→Phase 3b |
| 8 | Gaming multi-tenant integration complete | **Frontend storefront migration (Phase 4)** | Phase 3b→Phase 4 |
| 9 | All phases complete, all tests passing | **Final big-bang deployment** | Phase 4 |

### Dependency visualization

```
Phase 0: Security remediation
    │
    ├──► Tenant-context expansion (P0)
    │       │
    │       ├──► Pandas removal (P0) ──────────────────────────┐
    │       │                                                  │
    │       │                                                  ▼
    │       │                                          MongoDB consolidation (P0)
    │       │                                                  │
    │       │                                                  ▼
    │       │                                          Per-BG routing removal (P1) + division field migration
    │       │                                                  │
    │       │                                                  ├──► Gaming multi-tenant (3b)
    │       │                                                  │          │
    │       │                                                  │          ├──► Frontend storefront (4)
    │       │                                                  │          │
    │       │                                                  │          └──► Gaming tests (4)
    │       │                                                  │
    │       │                                                  └──► Gaming code integration (3)
    │       │                                                              │
    │       │                                                              ├──► Gaming serializers (3)
    │       │                                                              ├──► View refactoring (3)
    │       │                                                              └──► bgcode filtering (3)
    │       │
    │       └──► Gaming user-model reconciliation (P0)
    │               │
    │               └──► Merged auth/session rollout (3)
    │
    └──► Frontend cookie-readiness (2 P0)
            │
            └──► SimpleJWT cutover (3 P0)
```

### Guardrails

- **No dependency may be skipped.** Each prerequisite has exit criteria defined in its phase.
- **Dependencies are checked at phase gates.** Phase reviewers must verify upstream dependencies before signing off.
- **If a dependency is blocked**, escalate to the modernization owner. Do not proceed downstream.

### Post-Core Dependency Chain

| # | Prerequisite | Depends on it | Notes |
|---|---|---|---|
| 10 | Unified identity model: `CustomUser.phone` as universal key, wallet model created | **Cafe platform** — unified identity is foundation for walk-in registration, wallet billing, cross-brand linkage | Designed during core, implemented after Phase 4 |
| 11 | Tenant context with `bg_code`, `division`, `branch_code` | **Cafe platform** — station/session data must be tenant-scoped | Built in Phase 1 |
| 12 | Shared wallet PostgreSQL model | **Cafe platform** — wallet bridges cafe, esports, retail | Designed during core, implemented after Phase 4 |
| 13 | MongoDB consolidation with `bgcode` field | **Cafe platform** — new cafe collections need tenant filtering | Built in Phase 1 |
| 14 | React Query + cookie-ready auth | **Cafe platform** — kiosk needs authenticated mode, dashboard needs real-time polling | Built in Phase 2 |

---

## Approved Exceptions

Approved departures from this plan are logged in [[kungos-log]]. Each exception includes the plan item it departs from, the alternative approach, rationale, and risk assessment.

| Exception | Plan Item | Status |
|---|---|---|
| Dynamic throttle selection via `get_throttles()` | Phase 0 P0 #8 — DRF throttling | Approved |
| `djongo` engine retained in `DATABASES['mongo']` | Phase 0 P0 #1 — dependency removal | Completed — removed from both codebases in Phase 1 P1 |
| Knox auth retained in `REST_FRAMEWORK` | Phase 3 P0 #1 — SimpleJWT migration | Approved (per dependency chain #4) |
| Debug/audit tools kept in codebase | Phase 4 — Testing | Approved — permanent debugging infrastructure |
| `EmptyState` default icon `FileSearch` handled with `Icon.render` check | Phase 4 — Crash fixes | Fixed — commit `3395aed` |
| Legacy `users_businessgroup` model deleted | Phase 1 — Tenant schema | Completed — merged into `tenant_business_groups` |
| Brand/Entity/EntityBranch/BgEntityBranch models deleted | Phase 1 — Tenant schema | Completed — replaced by Division/Branch/DivisionAddress |
| MongoDB entity→division field rename | Phase 1 — Data migration | Completed — 68,443 docs migrated |

### Debug & Audit Tooling

| Tool | File | Purpose | Status |
|------|------|---------|--------|
| Error Logger | `src/lib/errorLogger.js` | Captures uncaught errors, promise rejections | ⏸️ Disabled |
| Error Badge | `src/components/common/ErrorBadge.jsx` | Floating indicator with error log viewer | ⏸️ Disabled |
| Static Tester | `test_pages.py` | Regression test all static routes | ✅ Active |
| Dynamic Tester | `test_dynamic_pages.py` | Regression test dynamic routes with real IDs | ✅ Active |
| Test Strategy | `TESTING_STRATEGY.md` | Phase alignment, page matrix, known issues | ✅ Active |

---

## Phase 0 — Safety Foundations (Security + Observability)

**Estimated effort:** 52 hours (range: 48–56h)  
**Why adjusted:** Gaming backend adds 9+ hardcoded secrets that must be remediated before any merge. Observability infrastructure adds ~8 hours.

### Objectives

- Eliminate all critical runtime and secret-management risks.
- Eliminate critical security issues in the gaming backend before merge.
- Establish observability infrastructure (correlation IDs, structured logging, health endpoints, Sentry).
- Establish program structure, ownership, and lock criteria.

### P0 tasks

| # | Task | Hours | Notes |
|---|---|---:|---|
| 1 | Remove all hardcoded secrets from code and environment-default fallbacks (both kteam and gaming) | 6 | Django secret key, DB creds, cloud creds, MeiliSearch keys, SMS keys |
| 2 | Rotate gaming-specific credentials: S3 keys, TextLocal SMS API, Cashfree prod/test, BharatPE UPI, Google Merchant ID, DB password default | 6 | 9+ secrets across 3 codebases |
| 3 | Set `DEBUG=False` in production configuration | 1 | |
| 4 | Restrict CORS to explicit allowlists | 2 | |
| 5 | Re-enable authentication on endpoints where it is commented out | 4 | |
| 6 | Stop returning `traceback.format_exc()` to clients; centralize error logging | 3 | |
| 7 | Add DRF throttling for login, OTP, SMS, and abuse-prone endpoints | 3 | Dynamic throttle selection via `get_throttles()` approved |
| 8 | Remove hardcoded test phone numbers and test-only production logic | 2 | |
| 9 | Remove hardcoded phone auth gate from gaming kuroadmin (`"9492540571"` / `"9582944439"`) | 2 | |
| 10 | Create `plat/observability/middleware.py` — CorrelationID middleware | 2 | `ContextVar` request ID, `X-Request-ID` response header |
| 11 | Create `plat/observability/logging.py` — structured JSON logging | 3 | Automatic tenant context injection |
| 12 | Create `plat/health/views.py` — `/health/live` and `/health/ready` | 2 | PostgreSQL, MongoDB, Redis, Celery, MeiliSearch checks |
| 13 | Wire Sentry DSN into `settings.py` with `bg_code` and `user_id` tags | 2 | |

### P1 tasks

| # | Task | Hours | Notes |
|---|---|---:|---|
| 1 | Create modernization owner map for backend, frontend, infra, data migration, QA | 2 | |
| 2 | Map all 12 critical audit findings to explicit plan items and named owners | 3 | |
| 3 | Establish final rollback document: git revert + DB restore | 2 | |
| 4 | Create risk register covering auth migration, pandas removal, MongoDB routing, gaming integration | 3 | |

### P2 tasks

| # | Task | Hours | Notes |
|---|---|---:|---|
| 1 | Define coding standards for new modules, shared utilities, logging, validation, API responses | 2 | |
| 2 | Freeze non-critical feature work on modules touched by this plan | 1 | |
| 3 | Create `plat/observability/context.py` — `ContextVar` holders | 1 | |
| 4 | Add test helpers for tenant context injection and request ID assertions | 2 | |
| 5 | Define architectural guardrails (see Non-Negotiable Guardrails section) | 2 | |

### Exit criteria

- No hardcoded secrets remain in active code (both kteam and gaming).
- All critical runtime settings fixed.
- Observability scaffold merged (correlation IDs, structured logs, health endpoints).
- Sentry wired with tenant/user tags.
- Rollback path, owners, and risk register documented.
- Gaming kuroadmin phone auth gate removed.
- Guardrails documented.

---

## Phase 1 — Tenant Context, Access Control, and Data-Layer Enforcement

**Estimated effort:** 148 hours (range: 130–160h)  
**Why adjusted:** Includes base tenant context work (130h) plus observability integration (8h), `TenantCollection` wrapper (12h), and `TenantConfig` model (8h) from architectural improvements. Gaming MongoDB 12-collection migration and user model reconciliation included.

### Objectives

- Replace duplicated access-control logic and pandas filtering with centralized tenant-aware permission handling.
- Introduce query-level tenant scoping and enforce it via `TenantCollection` and PostgreSQL RLS.
- Consolidate gaming MongoDB (12 collections) into `kuropurchase` with `bgcode` fields.
- Reconcile PostgreSQL user models between kteam and gaming backends.
- Implement `TenantConfig` model for runtime brand configuration.

### P0 tasks

| # | Task | Hours | Notes |
|---|---|---:|---|
| 1 | Expand `UserTenantContext` model: `user_id`, `bg_code`, `division`, `branches`, `scope`, `permission_snapshot`, `switched_at`, `switched_by`, `request_defaults` | 4 | |
| 2 | Define tenant scope semantics: `division=null, branches=null` → full BG scope; `division=set, branches=null` → division scope; `division=set, branches=set` → branch scope | 2 | |
| 3 | Implement centralized tenant-aware permission abstraction (resolve scope once per request, apply without pandas) | 8 | |
| 4 | Replace pandas-based permission filtering in 50+ locations with native ORM or query-layer logic | 16 | |
| 5 | Add `bgcode` to MongoDB documents; prepare single-database tenancy migration | 3 | |
| 6 | Create compound indexes: `(bgcode, division)`, `(bgcode, division, branch)`, `(bgcode, userid)`, plus domain-specific keys | 3 | |
| 7 | Remove per-request MongoClient creation; replace with shared client/singleton | 4 | |
| 8 | Migrate 12 gaming MongoDB collections from `products` DB to `kuropurchase` with `bgcode` on every document | 16 | Use `restore_kuropurchase` tool |
| 9 | Reconcile `CustomUser` schemas: keep kteam schema as canonical (4 extra fields), merge gaming users with defaults, unify manager signatures | 12 | |
| 10 | Create `TenantConfig` model: `bg_code`, `brand_slug`, `business_type`, `features`, `payment_cfg`, `sms_cfg`, `wallet_cfg`, `pricing_cfg`, `theme_cfg`, `integration_cfg` | 4 | |
| 11 | Seed `TenantConfig` for all current BGs and brands | 2 | |
| 12 | Create `plat/tenant/TenantCollection` wrapper for MongoDB | 6 | Raises `TenantContextMissing` on missing context |
| 13 | Implement `resolve_tenant_context(request)` as single source of truth | 3 | |
| 14 | Add request bootstrap layer: resolve tenant context, set request-local state, set PostgreSQL session values for RLS | 4 | |

### P1 tasks

| # | Task | Hours | Notes |
|---|---|---:|---|
| 1 | Migrate from per-BusinessGroup MongoDB databases to single database with tenant fields | 4 | |
| 2 | Remove code that switches Mongo databases using `client[bg.db_name]` | 3 | |
| 3 | Add PostgreSQL RLS for tenant-scoped tables (deferred — app-level filtering is current strategy) | 6 | `SET app.current_bg_code`, policies with `current_setting()` |
| 4 | Replace direct `db["collection"]` access with `TenantCollection` repo by repo | 8 | |
| 5 | Add CI grep/lint rule that blocks new raw collection usage outside approved infrastructure modules | 2 | |
| 6 | Refactor large view modules (especially `kuroadmin/views.py` → `teams/`) into domain-specific files | 8 | |
| 7 | Move duplicated exceptions, JSON encoders, response helpers, validation utilities into shared modules | 4 | |
| 8 | Standardize API response envelopes for success and failure | 3 | |
| 9 | Add field projections to Mongo reads and query optimization to ORM reads | 3 | |
| 10 | Reconcile order schemas: merge gaming 11-stage PC build lifecycle with kteam order management | 6 | |
| 11 | Remove `djongo` dependency from gaming backend | 2 | All gaming views already use `pymongo` directly |
| 12 | Move business-logic helpers out of `plat/shared/` into owned domain services (`teams/finance/services.py`) | 4 | Addresses `plat/shared/` purity concern |

### P2 tasks

| # | Task | Hours | Notes |
|---|---|---:|---|
| 1 | Add baseline structured logging configuration (request/response) | 3 | |
| 2 | Begin cleanup of cross-module imports creating tight coupling | 3 | |
| 3 | Add `verify_tenant_isolation` management command | 3 | Runs sample cross-tenant checks |
| 4 | Add automated tests: same user/wrong BG, correct BG/wrong division, missing context fails closed, branch-limited users | 4 | |

### Exit criteria

- No pandas-based permission filtering remains in the main request path.
- Tenant scope resolved centrally with BG, division, and branch semantics.
- MongoDB queries use query-level tenant filters instead of database-level routing.
- `TenantCollection` wrapper in place; no raw collection access in application services.
- PostgreSQL RLS enabled for tenant-scoped tables.
- All 12 gaming MongoDB collections migrated to `kuropurchase` with `bgcode`.
- PostgreSQL users merged without data loss.
- `TenantConfig` model created and seeded.
- Unified order schema designed and migrated.
- Business-logic helpers moved out of `plat/shared/` into owned domain services.

---

## Phase 2 — Frontend State, Session, and Stability Modernization

**Estimated effort:** 72–96 hours  
**Status:** P0 complete ✅ (3 commits, 108 files changed)  
**Commits:** `50739ab` → `2a99e03` → `735edad`

### Objectives

- Remove crash-prone frontend patterns. ✅
- Prepare the frontend for cookie-based auth without depending on the later backend auth cutover. ✅
- Modernize server-state handling. 🔜

### P0 tasks (complete ✅)

| # | Task | Status | Notes |
|---|---|---|---|
| 1 | Replace `!== null` patterns with `!= null` (catches both null and undefined) | ✅ | 314 patterns replaced across 71 files |
| 2 | Fix unsafe access patterns with optional chaining and safe fallbacks | ✅ | 235+ `.filter(...)[0]` patterns replaced; created `src/lib/safeAccess.js` with 6 utilities |
| 3 | Remove auth-token dependence on `localStorage`; make app cookie-ready | ✅ | Token managed in Redux store; no `localStorage` token usage found |
| 4 | Normalize BG/Division/Branch state into single source of truth | ✅ | `TenantContext.jsx` created; 18 component files migrated; non-React helpers added |
| 5 | Build tenant selector UI (BG → Division → Branch) | ✅ | `TenantSelector.jsx` with keyboard navigation, search filtering, visual hierarchy |

### P1 tasks (in progress — 35 pages migrated)

| # | Task | Status | Notes |
|---|---|---|---|
| 1 | Introduce React Query for server-state; migrate modules away from `useEffect`+`axios` | 🔜 | 35 of 74 pages migrated (47.3%); only Login.jsx remains with `useEffect` (auth page, intentionally not migrated) |
| 2 | Keep Redux only for UI state and transitional session/context state | — | Not started |
| 3 | Add `AbortController` to prevent memory leaks in effects | ✅ | Added to `fetcher()`/`mutator()` in `src/lib/api.jsx`; all React Query requests auto-cancel on unmount |
| 4 | Replace `moment` with `dayjs` | ✅ | All 54 `moment`/`moment-timezone` usages replaced; 46 files migrated, 8 unused imports cleaned |
| 5 | Add route-level code splitting with `React.lazy()` + `Suspense` | ✅ | 14 heavy pages lazy-loaded |
| 6 | Add loading states and empty states to high-value pages | 🔜 | 14 pages done: StockProd, Service, Products, Estimate, TPBuild, PaymentVoucher, PreBuilts, OfflineOrders, Analytics, Home, Profile, InwardPayments, Product, CreatePV |

### Migrated pages (35)

StockProd, Service, Products, Estimate, TPBuild, PaymentVoucher, PreBuilts, OfflineOrders, Analytics, Home, Profile, InwardPayments, Product, CreatePV, TPOrders, Dashboard, Reborder, GenerateInvoice, OutwardInvoice, InwardPayment, TPBuild, PaymentVoucher, PreBuilts, OfflineOrders, Analytics, Home, Profile, InwardPayments, Product, CreatePV, TPOrders, Dashboard, Reborder, GenerateInvoice, OutwardInvoice

### Remaining pages to migrate (~39)

Pages not yet migrated from `useEffect`+`axios` to React Query. These are primarily lower-value pages and forms that will be migrated incrementally.

### P2 tasks

| # | Task | Hours | Notes |
|---|---|---:|---|
| 1 | Introduce React Hook Form and Zod-style validation on highest-value forms | 6 | |
| 2 | Continue modern wrapper migration for remaining legacy pages and CSS files | 8 | |
| 3 | Add memoization and rerender optimization to shared components where profiling shows need | 4 | |

### Exit criteria

- The frontend no longer requires `localStorage` tokens. ✅
- The most common null/undefined crash patterns are removed. ✅
- React Query active for primary server-state flows. 🔜 (35/74 pages migrated)
- Request cleanup via `AbortController` implemented. ✅
- `moment` replaced with `dayjs` across entire frontend. ✅
- Route-level code splitting with `React.lazy()` + `Suspense` applied to 14 heavy pages. ✅

---

## Phase 3 — Auth, Consistency, and Operational Workflows

**Estimated effort:** 128 hours (range: 110–140h)  
**Why adjusted:** Includes base auth/API/gaming integration work (~86h) plus cross-store consistency (outbox pattern, ~16h), domain protocols (~10h), event bus (~8h), and tenant context in auth (~8h).

### Objectives

- Complete JWT migration with tenant context in auth/session.
- Add API compatibility structure without breaking the unfinished frontend migration path.
- Integrate gaming backend code into unified backend.
- Implement outbox pattern for cross-store consistency.
- Define domain protocols and event bus.

### P0 tasks

| # | Task | Hours | Notes |
|---|---|---:|---|
| 1 | Implement `djangorestframework-simplejwt` and finalize JWT auth flows | 8 | |
| 2 | Document and execute auth migration data strategy: Knox token invalidation, active session handling, re-login communication, failure fallback | 6 | |
| 3 | Ensure token/session payloads carry tenant scope (`bg_code`, `division`, `branches`), not only `bg_code` | 4 | |
| 4 | Copy gaming apps (`accounts`, `products`, `orders`, `payment`, `games`) into kteam-dj-chief and update `INSTALLED_APPS` | 6 | |
| 5 | Create DRF serializers for all gaming models: `Cart`, `Wishlist`, `Addresslist`, `Orders`, `OrderItems`, product catalog, game catalog | 12 | |
| 6 | Standardize error responses across both codebases — stop returning raw `traceback.format_exc()` | 3 | |
| 7 | Add `OutboxEvent` model and migration | 3 | UUID primary key, event_type, aggregate_type, aggregate_id, bg_code, payload, status, retry_count, available_at, processed_at, error_message |
| 8 | Create `plat/outbox/service.py`: `publish_in_txn()`, `mark_processed()`, `mark_failed()` | 4 | |
| 9 | Create Celery task `process_outbox_batch` (or management command fallback for local recovery) | 4 | |
| 10 | Convert high-risk cross-store flows to transaction + outbox: wallet recharge, wallet debit on session close, order placement fan-out, payment webhook processing | 8 | |
| 11 | Add idempotency keys for webhooks and payment callbacks | 4 | |
| 12 | Define domain protocols in `core/`: `ICafeSessionService`, `IWalletService`, `IOrderService`, `IPrizePayoutService`, `ICatalogService` | 4 | |
| 13 | Create brand implementations under `brands/` for each protocol | 4 | |

### P1 tasks

| # | Task | Hours | Notes |
|---|---|---:|---|
| 1 | Add API versioning with dual-path support: `/api/v1/` + legacy paths alive during dev | 4 | |
| 2 | Add documented deprecation timeline for legacy endpoint paths | 2 | |
| 3 | Add `drf-spectacular` and generate OpenAPI docs | 3 | |
| 4 | Add health-check endpoints alongside API versioning work | 2 | |
| 5 | Add server-side pagination to high-volume endpoints | 4 | |
| 6 | Consolidate PDF stack to `weasyprint` plus `pypdf` only | 3 | |
| 7 | Refactor gaming views: extract helpers into service modules | 8 | |
| 8 | Remove cross-app import coupling from gaming `orders/views.py` | 4 | |
| 9 | Replace gaming's custom `JSONEncoder` with native DRF serialization | 2 | |
| 10 | Add `bgcode` filtering to all gaming product/game queries | 3 | |
| 11 | Add pagination to large gaming list endpoints | 3 | |
| 12 | Add field projections to gaming MongoDB reads | 2 | |
| 13 | Merge gaming settings into kteam-dj-chief settings (payment settings, external service URLs, `django-environ`) | 4 | |
| 14 | Create `plat/events/bus.py`: `emit()`, `register()`, sync handlers, async (Celery) handlers | 4 | |
| 15 | Register domain event handlers: `wallet.recharged`, `session.started`, `session.ended`, `order.placed`, `order.fulfillment_changed`, `tournament.prize_awarded` | 3 | |
| 16 | Move non-owning side effects into event handlers (decouple services) | 4 | |
| 17 | Add retry policy and dead-letter handling for failed outbox events | 3 | |

### P2 tasks

| # | Task | Hours | Notes |
|---|---|---:|---|
| 1 | Add dead-letter view and requeue action in admin | 2 | |
| 2 | Create reconciliation command: detect wallet/session mismatches, detect missing Mongo side-effects, emit repair events | 4 | |
| 3 | Add contract tests that run same test suite against each brand implementation | 3 | |
| 4 | Add "new brand checklist" and make it part of repo docs | 2 | |

### Exit criteria

- JWT auth implemented; Knox migration handling documented.
- API dual-path support exists; frontend transition plan documented.
- All 5 gaming apps import and run within unified backend.
- No circular imports between apps.
- All gaming endpoints return standardized DRF responses.
- MongoDB reads use shared connection and field projections.
- Outbox live for all critical cross-store flows.
- Webhooks idempotent.
- Async failures inspectable.
- Domain protocols defined; brand implementations in place.
- Event bus registered with domain handlers.
- Tenant scope carried in JWT token payload.

---

## Phase 3b — Gaming Multi-Tenant Integration

**Estimated effort:** 32 hours (range: 28–36h)  
**Why added:** Gaming apps have zero multi-tenant support. All 5 gaming PostgreSQL models and 12 gaming MongoDB collections must be integrated with the existing BusinessGroup/Division/Branch context. Runs after Phase 2 when gaming code is integrated, before Phase 4 frontend migration.

### Objectives

- Add BusinessGroup/Division/Branch context to all gaming features.
- Ensure complete tenant isolation for gaming data.

### P0 tasks

| # | Task | Hours | Notes |
|---|---|---:|---|
| 1 | Add `bgcode` field to PostgreSQL models: `Cart`, `Wishlist`, `Addresslist`, `Orders`, `OrderItems` | 4 | |
| 2 | Add `bgcode` field to all 12 gaming MongoDB documents (migration from Phase 1) | 4 | |
| 3 | Create `TenantContextPermission` class for gaming endpoints | 3 | Similar to existing access control |
| 4 | Add `Switchgroupmodel` awareness to product catalog — only show products for current BG | 3 | |
| 5 | Add division/branch routing to order creation — orders tied to specific division | 3 | |
| 6 | Add BG-scoped product listing — different BGs can have different catalogs | 3 | |
| 7 | Add BG-scoped cart/wishlist/address isolation | 3 | |
| 8 | Add BG-scoped order visibility — users only see orders from their BG | 3 | |
| 9 | Add prebuilt PC build categorization by BG | 2 | |
| 10 | Add game catalog scoping by BG | 2 | |

### Exit criteria

- All gaming data isolated by BusinessGroup.
- BG switching affects product catalog, orders, and user data.
- No cross-BG data leakage in any endpoint.

---

## Phase 4 — Testing, CI/CD, Production Readiness, and Go-Live

**Estimated effort:** 156 hours (range: 144–168h)  
**Why adjusted:** Gaming-specific test coverage (cart, wishlist, orders, payment, products, webhooks) and frontend storefront page migration (product catalog, prebuilt builds, custom PC builder, cart, wishlist, checkout, order tracking, payment pages, game catalog) add ~12 hours on top of base estimate.

### Objectives

- Build the release-safe delivery layer (deferred because nothing ships during modernization).
- Prepare for the final one-time deployment.
- Migrate gaming storefront pages to `kteam-fe-chief` and retire `kurogg-nextjs`.

### P0 tasks

| # | Task | Hours | Notes |
|---|---|---:|---|
| 1 | Add backend tests: auth, access control, BG switching, tenant scope, invoices, payments, orders, estimates, PDF exports | 16 | pytest / pytest-django |
| 2 | Add frontend tests: auth/session bootstrap, tenant selector behavior, critical workflows | 8 | Vitest + React Testing Library |
| 3 | Define production deployment runbook for final big-bang release | 4 | |
| 4 | Define production rollback runbook: git revert + DB backup restore | 3 | |
| 5 | Gaming-specific backend tests: cart/wishlist CRUD, order lifecycle (11 stages), payment webhook (success/failure/cancelled), SMS (mock TextLocal), MongoDB bgcode filtering | 12 | |
| 6 | Gaming frontend tests: product catalog, cart, checkout, order tracking, custom PC builder | 8 | |
| 7 | Migration dry runs on fresh data snapshots | 4 | |
| 8 | Pre-cutover checklist: backups, restore verification, readiness checks, auth smoke tests, tenant isolation smoke tests, storefront parity | 6 | |

### P1 tasks

| # | Task | Hours | Notes |
|---|---|---:|---|
| 1 | Add CI pipeline: linting, type-checking, test execution, Docker builds | 6 | |
| 2 | Add CI gating on protected branches | 3 | |
| 3 | Build production monitoring dashboards; activate for go-live | 4 | |
| 4 | Add release checklists, database migration dry-run steps, cutover communications | 3 | |
| 5 | Produce post-migration maintenance runbook and handoff documentation | 4 | |
| 6 | Migrate gaming storefront pages to `kteam-fe-chief` (product catalog, prebuilt builds, custom PC builder, cart, wishlist, addresses, checkout, order tracking, payment, game catalog, CMS banners) | 24 | |
| 7 | Retire `kurogg-nextjs`: update DNS/CDN, disable deployment pipeline, archive repo | 4 | |
| 8 | Add RLS enforcement tests, Mongo tenant wrapper tests, outbox processing tests, idempotent webhook tests, event bus handler tests | 8 | |
| 9 | Add debug-visible request ID display in admin builds (backend logs matched from UI) | 3 | |
| 10 | Expose `TenantConfig`-driven frontend metadata for branding and feature visibility | 4 | |

### P2 tasks

| # | Task | Hours | Notes |
|---|---|---:|---|
| 1 | Add broader observability and lower-priority test coverage after critical paths are green | 6 | |
| 2 | Add training/knowledge-transfer material for React Query, tenant context, SimpleJWT, (Celery if Optional A) | 4 | |

### Exit criteria

- Critical-path tests pass.
- CI/CD and deployment procedures exist.
- Production runbook and rollback runbook finalized.
- `kurogg-nextjs` no longer serving traffic.
- All gaming storefront features available in `kteam-fe-chief`.
- Frontend calls unified `kteam-dj-be` API.
- Request tracing visible end-to-end.
- Storefront and admin parity confirmed.
- Rollback drill validated.

---

## Optional Paths — Post-Core-Modernization

### Optional A — Async Infrastructure (Redis + Celery)

**Estimated effort:** 20–30 hours (setup) + ongoing operational overhead  
**When to activate:** When you need horizontal scaling, high-volume async tasks, or real-time features.

| Task | Hours | Notes |
|---|---:|---|
| Docker Compose: Redis + Celery workers | 4 | Local dev environment |
| Django cache backend migration (filesystem → Redis) | 3 | Multi-worker session support |
| Celery configuration + first tasks | 6 | SMS, PDF gen, MeiliSearch indexing |
| Gaming webhook processing → Celery | 4 | Cashfree payment webhooks |
| Celery Beat periodic tasks | 3 | Replaces `django-crontab` |
| Production runbook + monitoring | 5 | Worker health, dead-letter, retries |

**Current status:** Zero async tasks in production. Single gunicorn worker. All PDF/SMS/indexing is user-triggered and synchronous. **Not needed right now.**

**Cafe Platform override:** When CAFE_PLATFORM activates, `channels-redis` (WebSocket gateway) and Celery Beat (`check_expired_sessions` periodic task) become **required**, not optional. See `CAFE_PLATFORM.md` §17.1 (Gap 1) and §17.5 (Gap 5).

### Optional B — LLM Integration

**Estimated effort:** 24–40 hours  
**When to activate:** When AI-assisted features provide measurable ROI (time savings, revenue uplift, user engagement).

| Task | Hours | Notes |
|---|---:|---|
| LLM provider selection + API key management | 3 | OpenAI, Anthropic, or local (Ollama/Llama) |
| Prompt templates for key use cases | 5 | Invoice extraction, product enrichment, customer support |
| Rate limiting + cost monitoring | 4 | Prevent runaway costs |
| Invoice PDF → structured data extraction | 6 | Auto-fill invoice fields from uploaded PDF |
| Product catalog enrichment | 4 | Auto-generate descriptions, tags, categories |
| Analytics insights assistant | 4 | Natural language queries on business data |
| Customer support chat widget | 4 | FAQ + ticket triage |
| Testing + evaluation framework | 4 | Prompt quality, response accuracy, cost tracking |

**Recommended approach:** Start with **invoice extraction** (highest ROI for invoicing workflow) or **product catalog enrichment** (saves manual data entry). Use OpenAI API first, then evaluate local models for cost-sensitive use cases.

### Activation criteria

Both optional paths should only be activated when:
1. Core Phases 0–4 are complete and stable
2. A concrete use case has been identified with expected ROI
3. The team has bandwidth to maintain the additional infrastructure
4. Cost analysis (for LLM API usage) shows positive return

### Decision log

| Date | Decision | Rationale | Owner |
|---|---|---|---|
| 2026-04-23 | **Deferred** Redis/Celery to Optional A | Zero current async tasks; single worker; user-triggered operations only | Chief |
| 2026-04-23 | **Deferred** LLM integration to Optional B | No immediate AI use case identified; focus on core stability first | Chief |

---

## Detailed Implementation Instructions by Capability

### A. Correlation IDs and structured logging

1. Create `plat/observability/context.py` with `ContextVar` holders for request ID and tenant context.
2. Create `plat/observability/middleware.py`:
   - Generate request ID (`uuid4()[:8]`)
   - Resolve tenant context
   - Store both in request-local context
   - Add `X-Request-ID` to responses
3. Configure Django `LOGGING` with JSON output.
4. Create a shared logging helper that automatically injects context.
5. Update all service entry points and Celery tasks to log: start, end, duration, error.
6. Add Sentry middleware integration and tags.

**Log schema (every entry must include):**

| Field | Type | Example |
|---|---|---|
| `ts` | ISO 8601 | `2026-04-27T10:30:00.000Z` |
| `level` | string | `INFO`, `ERROR`, `WARN` |
| `rid` | string | `a1b2c3d4` (request ID) |
| `user_id` | string/uuid | `abc-123-def` |
| `bg_code` | string | `BG0001` |
| `division` | string/null | `kurogaming` |
| `branch` | string/array | `branch-01` |
| `service` | string | `rebellion.cafe.services` |
| `action` | string | `session.end` |
| `duration_ms` | int | `42` |
| `outcome` | string | `success`, `error` |
| `error_class` | string/null | `WalletInsufficient` |
| `payload_summary` | object/null | `{"session_id": "S001", "charge": 500}` |

### B. Tenant enforcement

1. Add or finalize `bg_code` columns in PostgreSQL tenant tables.
2. Write SQL migrations for row-level security where appropriate.
3. Add a DB utility that runs `SET LOCAL app.current_bg_code = ...`.
4. Build `TenantCollection` for MongoDB.
5. Replace direct collection access repo by repo.
6. Add a CI grep or lint rule that blocks new raw collection usage outside approved infrastructure modules.
7. Add `verify_tenant_isolation` management command that runs sample cross-tenant checks.

**`TenantCollection` contract:**

```python
class TenantCollection:
    def __init__(self, collection_name: str):
        self.collection_name = collection_name

    def find(self, filter: dict = None, **kwargs) -> Cursor:
        ctx = get_tenant_context()
        if not ctx:
            raise TenantContextMissing("Tenant context required for this operation")
        base = {"bgcode": ctx.bg_code}
        if ctx.division:
            base["division"] = ctx.division
        if ctx.branches:
            base["branch"] = {"$in": ctx.branches}
        base.update(filter or {})
        return raw_collection(self.collection_name).find(base, **kwargs)
```

**Rules:**
- No direct `db["collection"]` access outside the tenant wrapper
- No direct `client[bg.db_name]` switching in request paths
- All new queries must be tenant-wrapped by construction
- All legacy direct accesses must be removed during Phase 1

### C. Outbox and replayable workflows

1. Add `OutboxEvent` model and admin view.
2. Create `plat/outbox/service.py` with:
   - `publish_in_txn(event_type, payload, bg_code)` — writes event inside atomic transaction
   - `mark_processed(event_id)` — marks event as processed
   - `mark_failed(event_id, error_message)` — marks event as failed with error
3. Create Celery task `process_outbox_batch`.
4. Register handlers by event type.
5. Make handlers idempotent with deterministic keys.
6. Create dead-letter view and requeue action in admin.
7. Add reconciliation command: detect wallet/session mismatches, detect missing Mongo side-effects, emit repair events.

**Rules:**
- A service may update PostgreSQL state and write an outbox record in the same transaction.
- MongoDB side effects happen asynchronously from the outbox processor.
- Every processor must be idempotent.
- Every event must have a replay path.
- Every failed event must be inspectable and retryable.

**Mandatory for:**
- Wallet debit/credit paired with Mongo session/payment updates
- Payment webhook handling
- Order lifecycle transitions that fan out to multiple stores
- Catalog sync and external notification workflows

### D. Domain protocols and brand adapters

1. Create `core/<domain>/protocols.py` for each domain:
   - `ICafeSessionService`: `start_session(phone, station_id, bg_code)`, `end_session(session_id, bg_code)`, `calculate_charges(session_id)`
   - `IWalletService`: `credit(user_id, amount, reason, bg_code)`, `debit(user_id, amount, reason, bg_code)`, `get_balance(user_id, bg_code)`
   - `IOrderService`: `create_order(...)`, `update_status(...)`, `get_order(...)`
   - `IPrizePayoutService`: `award_prize(player_id, amount, tournament_id, bg_code)`
   - `ICatalogService`: `get_products(bg_code)`, `get_product(id, bg_code)`
2. Create `brands/<brand>/<domain>/services.py` for each implementation.
3. Map the active brand from `TenantConfig`.
4. Add a resolver such as `get_wallet_service(bg_code)` or `get_order_service(bg_code)`.
5. Move brand-specific branching out of views and into adapter selection.
6. Add contract tests that run the same test suite against each brand implementation.

### E. Event bus

1. Create `plat/events/bus.py`:
   ```python
   @dataclass
   class DomainEvent:
       event_type: str
       payload: dict
       bg_code: str

   _handlers: dict[str, list[Callable]] = {}

   def on(event_type: str):
       def decorator(fn):
           _handlers.setdefault(event_type, []).append(fn)
           return fn
       return decorator

   def emit(event: DomainEvent):
       for handler in _handlers.get(event.event_type, []):
           handler(event)  # sync; or use celery_task.delay(event) for async
   ```
2. Create event dataclasses in `plat/events/types.py`.
3. Register handlers in app startup or domain registry modules.
4. Move non-owning side effects into handlers.
5. Use sync handlers for low-cost local effects and Celery-backed handlers for durable async effects.

**Event types:**
- `wallet.recharged` — triggers loyalty points, notifications
- `session.started` — triggers station lock, game load
- `session.ended` — triggers charge calculation, outbox event
- `order.placed` — triggers inventory reservation, payment processing
- `order.fulfillment_changed` — triggers SMS notification, tracking update
- `tournament.prize_awarded` — triggers wallet credit (cafe/esports)

---

## Adding a New Brand, Division, or Business Type

### New brand

1. Insert a `TenantConfig` row with `bg_code`, `brand_slug`, `business_type`, `features`, `payment_cfg`, `sms_cfg`, `wallet_cfg`, `theme_cfg`.
2. Add brand theme and feature metadata.
3. Reuse existing core protocols where possible.
4. Create brand adapter implementations only for capabilities that differ.
5. Register any brand-specific event handlers.
6. Seed branch mappings and permission templates.
7. Run the tenant-isolation suite.
8. Run contract tests against the new brand services.
9. Expose the brand in frontend tenant selection and config bootstrap.

### New division within an existing brand

1. Create division metadata in tenant config or tenant directory tables.
2. Assign branch scopes and permissions.
3. Ensure Mongo documents and PostgreSQL rows receive correct division values.
4. Run division-scope tests.
5. Verify dashboards and exports are properly filtered.

### New business type

1. Add `business_type` to `TenantConfig`.
2. Introduce a new `core/` domain package only if the capability is truly new.
3. Publish domain events rather than wiring direct coupling into old services.
4. Add business-type-specific pricing, payment, or workflow config.
5. Build the UI as a feature-gated module instead of a forked application where possible.

---

## Non-Negotiable Guardrails

The following rules are mandatory. Violations require explicit approval logged in [[kungos-log]].

- **No raw Mongo collection access** in app services — use `TenantCollection` only
- **No per-BG database switching** in request paths — single database, query-level filtering
- **No cross-store business action** without transaction + outbox
- **No new brand logic hardcoded in views** — use `TenantConfig` + protocols
- **No tenant-scoped query** without resolved tenant context
- **No production debugging** based only on print statements — use correlation IDs
- **No event handler** without idempotency rules
- **No shared utility module** containing hidden business ownership — pure utilities only

---

## Governance

All code changes across all repositories related to Project Kungos must align with the structure, decisions, and phased approach defined in this plan. Any required deviation from the plan must meet two conditions:

1. **Explicit approval** — the departure must be approved by the Modernization Owner before implementation.
2. **Logged departure** — every approved departure must be recorded in the Kungos Log (`~/llm-wiki/kungos-log.md`) with: date, description of the deviation, justification, approver, and affected plan section.

This applies to all codebases: `kteam-dj-chief`, `kteam-fe-chief`, `kuro-gaming-dj-backend`, `kurogg-nextjs` (until retirement), and any new repositories created under the Kungos program. No exceptions.

Architecture reviews must explicitly check:
- Tenant safety
- Observability
- Extensibility impact
- Cross-store consistency
- Migration risk

Any deviation must record: date, section being bypassed, alternative approach, reason, risk, approver, rollback or cleanup plan.

---

## Risks and Mitigations

| Risk | Why it matters | Mitigation |
|---|---|---|
| Auth migration breaks login/session flow | Knox → JWT is one of the highest-risk changes | Frontend becomes cookie-ready first, migration strategy documented, rollback is git revert + DB restore |
| Tenant routing remains inconsistent | Division/branch context currently missing from active session state | Add `bg_code`, `division`, `branches` to active tenant context; resolve centrally per request; `TenantCollection` raises on missing context |
| MongoDB migration causes query regressions | Per-BG routing removal changes core data access behavior | Migrate documents with `bgcode`, create indexes first, then switch query paths |
| Pandas removal breaks authorization logic | Pandas filtering exists in 50+ locations | Replace with central permission abstraction before broad cleanup |
| Async infrastructure added without operational clarity | Redis/Celery deployment details were missing | Use local Docker Compose during modernization; finalize production runbook in Phase 4 |
| Frontend migration breaks API compatibility | Very large frontend surface | Keep dual API paths until frontend migration is complete |
| **MongoDB gaming data loss during migration** | 12 collections from gaming `products` DB must be copied to `kuropurchase` | Full backup before migration, dry-run on staging, verify document counts |
| **Knox token incompatibility after user merge** | Gaming and kteam users share Knox tokens post-reconciliation | Test token generation/verification across merged users before merge |
| **Payment webhook failures during transition** | Cashfree + UPI webhooks must work with unified backend | Keep both backends running in parallel during transition, webhook idempotency |
| **Order data inconsistency** | Gaming 11-stage PC build orders vs kteam orders | Unified order schema designed before migration, migration script validates all fields |
| **Product catalog performance degradation** | 12 new collections in `kuropurchase` | Add compound indexes, field projections, pagination before merge |
| **Cross-BG data leakage** | Gaming data must be isolated by BusinessGroup | Add `bgcode` to all queries, comprehensive tenant isolation tests |
| **Hardcoded gaming credentials leak into kteam** | 9+ secrets in gaming code (S3, SMS, Cashfree, UPI, DB) | Phase 0: remove all hardcoded secrets before any merge |
| **Gaming kuroadmin no-auth endpoints** | All 25 gaming admin endpoints have no authentication | Phase 0: remove phone auth gate, Phase 2: add Knox auth + BG context |
| **Cafe platform identity collision** | Same phone used across cafe/esports/retail could create duplicate users | Unified identity model: phone = unique key in CustomUser, wallet = shared |
| **Unauthenticated gamers endpoint** | `gamers()` has auth commented out — anyone can create sessions | Replace with phone-lookup walk-in mode + wallet balance check |
| **Cafe data mixed with esports data** | `reb_users` used for both staff roster and cafe customers | Add `station_role`, `customer_type`, `is_staff` fields to `reb_users` |
| **Wallet double-spend** | Concurrent session end + wallet recharge could cause race conditions | PostgreSQL row-level locking on wallet balance, transaction log audit trail |
| **Cross-store partial write** | Session close (MongoDB) before wallet debit (PostgreSQL) crash leaves free time | Outbox pattern: both writes in same PostgreSQL transaction, async Mongo side-effect |
| **Tenant isolation bypass** | Single missing `bgcode` filter leaks cross-tenant data | `TenantCollection` raises `TenantContextMissing`; PostgreSQL RLS policies |
| **Domain event handler failures** | Silent handler failures break cross-domain workflows | Every handler must be idempotent; failed events go to dead-letter queue |
| **Outbox event storms** | High-volume events overwhelm processor | Paginate outbox processing; add retry backoff; monitor queue depth |
| **`TenantConfig` as single point of failure** | If `TenantConfig` lookup fails, all brand behavior breaks | Cache `TenantConfig` with TTL; fallback to defaults; log and alert on cache miss |
| **Protocol implementation drift** | Brand implementations may diverge from protocol contracts | Contract tests run against each brand; `typing.Protocol` enforces at import time |
| **Shared utilities contamination** | `plat/shared/` accumulates business logic over time | CI lint rule: no side effects in `plat/shared/`; regular audits |

---

## Effort Summary

| Phase | Min | Likely | Max |
|---|---:|---:|---:|
| Phase 0 — Safety Foundations (Security + Observability) | 48h | 52h | 56h |
| Phase 1 — Tenant Context, Access Control, and Data-Layer Enforcement | 130h | 148h | 160h |
| Phase 2 — Frontend State, Session, and Stability Modernization | 72h | 84h | 96h |
| Phase 3 — Auth, Consistency, and Operational Workflows | 110h | 128h | 140h |
| Phase 3b — Gaming Multi-Tenant Integration | 28h | 32h | 36h |
| Phase 4 — Testing, CI/CD, Production Readiness, and Go-Live | 144h | 156h | 168h |
| Gaming-specific additions (on top of core ~400h) | 160h | 180h | 200h |
| Overlap eliminated (security, dependencies, auth) | -120h | -140h | -140h |

### Combined total

- Core modernization: 390h likely (range: 350h–420h based on phase mins/maxs)
- Gaming-specific additions: 172h likely (range: 160h–192h)
- Overlap eliminated: 140h
- **Min: 380 hours (9.5 weeks)**
- **Likely: 472 hours (11.8 weeks)**
- **Max: 580 hours (14.5 weeks)**

*Optional paths (A: Redis/Celery ~25h, B: LLM ~32h) not included in totals above.*
*Post-core cafe platform: 120–180 hours (separate from core totals).*

### Gaming-specific effort breakdown

| Item | Hours |
|---|---:|
| MongoDB 12-collection migration to `kuropurchase` | 16 |
| PostgreSQL user model reconciliation | 12 |
| Order schema reconciliation | 8 |
| DRF serializers for gaming models | 38 |
| View refactoring (helpers → services, cross-app decoupling) | 32 |
| bgcode field migration (MongoDB + PostgreSQL) | 20 |
| Multi-tenant permission class for gaming | 12 |
| Settings merging, env management | 8 |
| Gaming-specific backend tests | 16 |
| Frontend storefront page migration | 40 |
| kurogg-nextjs retirement | 8 |
| **Gaming-specific total** | **172 hours** |

---

## React Query Migration Status

**Overall progress:** 54 of 67 pages migrated to React Query (`useQuery`/`useMutation`). 12 pages remain with `useEffect` (11 functional + Login.jsx intentionally excluded).

### Migrated Pages (54)

| # | Page | Pattern |
|---|---|---|
| 1 | Analytics | `useQuery` |
| 2 | Attendence | `useQuery`/`useMutation` |
| 3 | Audit | `useQuery` |
| 4 | AuditDetail | `useQuery` |
| 5 | BulkPayments | `useQuery` |
| 6 | Businessgroup | `useQuery` |
| 7 | ChangePwd | `useQuery`/`useMutation` |
| 8 | Counters | `useQuery` |
| 9 | CreateEmp | `useQuery`/`useMutation` |
| 10 | CreatePO | `useQuery`/`useMutation` |
| 11 | CreateTPBuild | `useQuery`/`useMutation` |
| 12 | CreditDebitNotes | `useQuery` |
| 13 | Dashboard | `useQuery` |
| 14 | EditAttendance | `useQuery`/`useMutation` |
| 15 | EmployeeAccessLevel | `useQuery` |
| 16 | EmployeesSalary | `useQuery` |
| 17 | EstimatesDetail | `useQuery` |
| 18 | EstimatesList | `useQuery` |
| 19 | Financials | `useQuery` |
| 20 | GenerateInvoice | `useQuery` |
| 21 | Home | `useQuery`/`useMutation` |
| 22 | InvoiceCredit | `useQuery` |
| 23 | InvoiceDetail | `useQuery` |
| 24 | InvoicesList | `useQuery` |
| 25 | InwardDebitNote | `useQuery` |
| 26 | InwardDebitNotes | `useQuery` |
| 27 | InwardPayment | `useQuery`/`useMutation` |
| 28 | ITCGST | `useQuery` |
| 29 | JobApps | `useQuery` |
| 30 | OrderCreate | `useQuery`/`useMutation` |
| 31 | OrderDetail | `useQuery` |
| 32 | OrdersList | `useQuery` |
| 33 | OutwardCreditNotes | `useQuery` |
| 34 | OutwardDebitNotes | `useQuery` |
| 35 | OutwardInvoice | `useQuery` |
| 36 | OutwardInvoices | `useQuery` |
| 37 | Overview | `useQuery` |
| 38 | PaymentVouchers | `useQuery` |
| 39 | Presets | `useQuery` |
| 40 | ProductDetail | `useQuery` |
| 41 | ProductsList | `useQuery` |
| 42 | PurchaseOrders | `useQuery` |
| 43 | SearchResults | `useQuery` |
| 44 | ServiceRequestsDetail | `useQuery` |
| 45 | ServiceRequestsList | `useQuery` |
| 46 | StockDetail | `useQuery` |
| 47 | Stock | `useQuery` |
| 48 | StockRegister | `useQuery` |
| 49 | TPBuilds | `useQuery` |
| 50 | TPBuildsDetail | `useQuery` |
| 51 | TPBuildsNew | `useQuery` |
| 52 | UserDetails | `useQuery` |
| 53 | UserOrders | `useQuery` |
| 54 | Users | `useQuery` |

### Not Migrated — useEffect Only (12 pages)

| # | Page | Reason | Priority |
|---|---|---|---|
| 1 | **Login.jsx** | **Intentionally excluded** — auth page, requires special token handling | N/A |
| 2 | Audit.jsx | Lower-value audit listing | P2 |
| 3 | CreateEstimate.jsx | Form page, needs React Hook Form integration first | P2 |
| 4 | Employees.jsx | HR listing, moderate complexity | P2 |
| 5 | InvoicesList.jsx | High-volume table, needs pagination optimization | P1 |
| 6 | OrderDetail.jsx | Complex detail view, depends on OrderConsolidation (Post-Phase 4) | P2 |
| 7 | OrdersList.jsx | Complex list with multiple filters, depends on OrderConsolidation (Post-Phase 4) | P2 |
| 8 | ProductsList.jsx | Product catalog, moderate complexity | P2 |
| 9 | PurchaseOrders.jsx | Procurement page, depends on navigation restructure (Post-Phase 4) | P2 |
| 10 | Stock.jsx | Inventory overview, moderate complexity | P2 |
| 11 | StockDetail.jsx | Inventory detail, moderate complexity | P2 |
| 12 | TPBuilds.jsx | TP build management, moderate complexity | P2 |

### Migration Pattern

All migrated pages follow this pattern:
- **Data fetching:** `useQuery` with `fetcher()` from `src/lib/api.jsx`
- **Writes:** `useMutation` with `mutator()` from `src/lib/api.jsx`
- **Cache keys:** `queryKeys.js` factory for consistent cache keys
- **Stale time:** 5 minutes, garbage collection: 10 minutes
- **Request cleanup:** `AbortController` auto-cancels on unmount
- **Access checks:** Early return with `navigate("/unauthorized", { replace: true })`
- **Loading states:** `Spinner` component
- **Date handling:** `dayjs` (all `moment` imports removed)
- **Route splitting:** 14 heavy pages lazy-loaded with `React.lazy()` + `Suspense`

### Remaining Work

- **Login.jsx** — intentionally excluded (auth page, special token handling)
- **11 functional pages** — migrate incrementally during Phase 4, prioritize `InvoicesList.jsx` (high-volume) and defer `OrderDetail.jsx`/`OrdersList.jsx` until after OrderConsolidation (Post-Phase 4)

---

## Pre-Lock Checklist

**Most items are COMPLETE.** Remaining items to finalize before production deployment:

- [ ] Owner placeholders are replaced with named individuals.
- [ ] All 12 critical audit issues are explicitly mapped to plan items.
- [ ] Risk register is present for auth migration, pandas removal, MongoDB routing changes, session/auth changes, AND gaming integration risks.
- [ ] Rollback procedure is documented as git revert + DB backup restore.
- [✅] CI/CD workstream is documented as a Phase 4 task.
- [✅] Environment strategy is simplified to dev + prod only.
- [✅] `pydantic` is present in target backend requirements.
- [✅] `django-environ` is the single chosen env/settings library.
- [✅] Auth migration data strategy is documented.
- [✅] API dual-path support plan is documented.
- [ ] Optional A (Redis/Celery) activation criteria documented.
- [ ] Phase 0 estimate is updated to 48-56 hours or split into sub-phases.
- [ ] Phase 1 estimate/scope is updated to reflect expanded work (MongoDB consolidation + gaming migration + tenant enforcement + `TenantConfig`).
- [ ] Phase 3 estimate/scope is updated to reflect gaming app integration + outbox + protocols + event bus.
- [ ] Phase 4 estimate is updated to 144-168 hours.
- [✅] Intra-phase P0/P1/P2 priority ordering exists across all phases.
- [✅] Multi-tenant scope routing is included in Phase 1.
- [✅] MongoDB per-BG consolidation is included in Phase 1.
- [ ] Gaming MongoDB 12-collection migration is included in Phase 1.
- [✅] PostgreSQL user model reconciliation is included in Phase 1.
- [ ] Gaming app integration (5 apps) is included in Phase 3.
- [ ] Gaming multi-tenant integration is included as Phase 3b.
- [✅] PostgreSQL upgrade decision is documented, even if the decision is to leave it unchanged.
- [ ] Gaming credentials (9+ hardcoded secrets) remediation is in Phase 0.
- [✅] kurogg-nextjs retirement is in Phase 4.
- [ ] Workstream governance model documented: core vs gaming parallel tracks with explicit gating on Phase 1.
- [✅] Effort model reconciled: min/likely/max ranges shown for each phase and total.
- [✅] Operational packages (django-dbbackup, django-storages) status verified and locked.
- [ ] Observability infrastructure (correlation IDs, structured logging, Sentry) defined in Phase 0.
- [ ] Outbox pattern defined in Phase 3.
- [ ] `TenantCollection` wrapper defined in Phase 1.
- [ ] Domain protocols defined in Phase 3.
- [ ] `TenantConfig` model defined in Phase 1.
- [ ] Event bus defined in Phase 3.
- [ ] Brand-domain app structure documented.
- [ ] `plat/shared/` purity rule defined.
- [✅] DNS TTL reduction procedure defined for T-24.
- [✅] Auth pre-verification steps defined (Knox invalidation, JWT issuance with merged users).
- [✅] BG-switch smoke test procedure defined per active tenant.
- [✅] MeiliSearch index verification defined for post-deploy.

---

## Cutover Checklist — Final Big-Bang Deployment

### Pre-deployment (T-48 hours)

| # | Item | Owner | Status |
|---|---|---|---|
| 1 | Full database backup taken: PostgreSQL (all schemas), MongoDB (`kuropurchase`, all collections), MeiliSearch indexes | Infra | [ ] |
| 2 | Backup integrity verified: test restore in isolated environment | Infra | [ ] |
| 3 | Deployment commit created and tagged; git revert path confirmed | Backend Lead | [ ] |
| 4 | All Phase 0-4 exit criteria met; phase sign-offs collected | Modernization Owner | [ ] |
| 5 | Rollback runbook reviewed and rehearsed by all team members | All Leads | [ ] |
| 44 | **DNS TTL reduction:** DNS TTL lowered to 60s at T-24 hours to enable rapid failover | Infra | [ ] |
| 45 | **Auth pre-verification:** Knox token invalidation confirmed — sample Knox tokens return 401 | Backend Lead | [ ] |
| 46 | **Auth migration pre-verify:** JWT issuance tested with merged user base (kteam + gaming users) | Backend Lead | [ ] |
| 47 | **BG-switch smoke test:** Tenant context switch verified per active tenant (BG → Division → Branch) | Backend Lead | [ ] |
| 48 | **MeiliSearch index verification:** Search indexes rebuilt and verified post-restore | Backend Lead | [ ] |

This is the one-page operational checklist for the final deployment. It aggregates the rollback procedure, auth migration data strategy, API dual-path support plan, and Redis/Celery production runbook into a single go-live sequence. Every item must be checked off by the modernization owner before the deployment window opens.

### Deployment window (T-0)

| # | Item | Owner | Status |
|---|---|---|---|
| 6 | Deployment commit pushed; Docker images built and pushed to registry | Infra | [ ] |
| 7 | Deploy to production: application containers, Redis (if Optional A), Celery workers (if Optional A) | Infra | [ ] |
| 8 | Health-check endpoints pass: `/health/`, `/api/v1/health/` | Backend Lead | [ ] |
| 9 | PostgreSQL connectivity verified | Backend Lead | [ ] |
| 10 | MongoDB connectivity verified: `kuropurchase` accessible, compound indexes present | Backend Lead | [ ] |
| 11 | MeiliSearch connectivity verified | Backend Lead | [ ] |
| 12 | Redis connectivity verified (if Optional A activated) | Backend Lead | [ ] |
| 13 | Celery worker health verified (if Optional A activated) | Backend Lead | [ ] |
| 14 | **Auth cutover:** SimpleJWT active, Knox disabled, login flow tested end-to-end | Backend Lead | [ ] |
| 15 | **Auth cutover:** Frontend confirms cookie-based auth (no `localStorage` tokens) | Frontend Lead | [✅] — Token in Redux store only, no localStorage token usage |
| 16 | **Auth cutover:** Existing users forced to re-login (Knox tokens invalidated) | Backend Lead | [ ] |
| 17 | **Auth cutover:** Gaming and kteam users share unified session — cross-domain login tested | Backend Lead | [ ] |
| 18 | **API dual-path:** `/api/v1/` endpoints responding with correct contract | Backend Lead | [ ] |
| 19 | **API dual-path:** Legacy paths still active and returning expected responses | Backend Lead | [ ] |
| 20 | **API dual-path:** Gaming endpoints accessible under dual-path structure | Backend Lead | [ ] |
| 21 | **MongoDB:** `bgcode` field present on all documents in all collections | Backend Lead | [ ] |
| 22 | **MongoDB:** Per-BG routing code (`client[bg.db_name]`) removed and verified absent | Backend Lead | [ ] |
| 23 | **Pandas removed:** No pandas imports in active code (0/12 files) | Backend Lead | [✅] All 9 files cleaned — only .bak files contain pandas | [✅] |
| 24 | **Gaming apps:** All 5 gaming apps (`accounts`, `products`, `orders`, `payment`, `games`) responding | Backend Lead | [🟡] Gaming backend is separate repo (`kuro-gaming-dj-backend`), not yet integrated | [ ] |
| 25 | **Gaming multi-tenant:** BG-scoped product listing, cart, wishlist, orders verified | Backend Lead | [ ] |
| 26 | **Payment:** Cashfree test payment flow completes successfully | Backend Lead | [ ] |
| 27 | **Payment:** UPI QR generation and webhook receipt verified | Backend Lead | [ ] |
| 28 | **Frontend:** kteam-fe-chief loads, tenant selector works, auth flow complete | Frontend Lead | [✅] Phase 2 complete, React Query 56/71 pages migrated, Login.jsx intentionally excluded | [✅] |
| 29 | **Frontend:** Gaming storefront pages load (product catalog, cart, checkout) | Frontend Lead | [ ] |
| 30 | **Frontend:** kurogg-nextjs traffic fully routed to kteam-fe-chief | Infra | [ ] |
| 31 | **DNS/CDN:** DNS records updated, CDN cache purged | Infra | [ ] |

### Post-deployment (T+1 hour)

| # | Item | Owner | Status |
|---|---|---|---|
| 32 | Error rate monitored for 30 minutes — no spike > baseline threshold | Infra / All Leads | [ ] |
| 33 | Latency monitored for 30 minutes — no p95 degradation > 20% | Infra / All Leads | [ ] |
| 34 | Payment success rate verified (minimum 3 test transactions) | Backend Lead | [ ] |
| 35 | SMS sending verified (test SMS to internal number) | Backend Lead | [ ] |
| 36 | Celery task processing verified (if Optional A activated) | Backend Lead | [ ] |
| 37 | Monitoring dashboards confirmed active and reporting | Infra | [ ] |
| 38 | Rollback decision made: proceed or revert | Modernization Owner | [ ] |
| 49 | **Auth cutover confirmed:** Knox tokens fully invalidated, no active Knox sessions remain | Backend Lead | [ ] |
| 50 | **MeiliSearch index verification:** Search indexes rebuilt and verified post-deploy | Backend Lead | [ ] |

### Rollback procedure (if any step fails)

1. **Stop** — halt deployment immediately. Do not proceed to next step.
2. **Revert** — `git revert` the deployment commit.
3. **Restore** — restore PostgreSQL and MongoDB from pre-deployment backup (item #2).
4. **Verify** — confirm old system is operational.
5. **Communicate** — notify all stakeholders of rollback and root cause.
6. **Reschedule** — fix the issue, re-run pre-deployment checklist, and attempt again.

### Post-maintenance

| # | Item | Owner | Status |
|---|---|---|---|
| 39 | Post-migration maintenance runbook distributed to all team members | Modernization Owner | [ ] |
| 40 | CI/CD pipeline confirmed operational on protected branches | Infra | [ ] |
| 41 | Knowledge-transfer sessions scheduled for React Query, tenant context, SimpleJWT, (Celery if Optional A) | Modernization Owner | [ ] |
| 42 | kurogg-nextjs repository archived, deployment pipeline disabled | Infra | [ ] |
| 43 | Program retrospective conducted | All Leads | [ ] |

---

## Navigation and Order Restructure (Post-Phase 4)

**Plan:** `docs/plans/2026-04-23-navigation-structure-restructure.md` (planned, awaiting approval)

### Context

The Orders module currently has **17+ fragmented pages** scattered across the navigation. This creates duplicate code, inconsistent UX, navigation confusion, and maintenance debt.

### Key findings

- All order types share **core fields** in `orders_core`: `orderid`, `order_type`, `status`, `total_amount`, `customer_id`, `division`, `bg_code`, `billadd`, `products`, `channel`, `created_at`, `updated_at`
- Type-specific fields go in detail tables: `estimate_detail`, `in_store_detail`, `tp_order_detail`, `service_detail`, `eshop_detail`
- Same status pipeline: `Created → Products Added → Authorized → Inventory Added → Shipped → Delivered → Cancelled`
- An `orderconversion` endpoint already converts TP → KG orders
- The only real distinction is the `channel` field and access control (`orders` vs `offline_orders`)
- `inwardpayments` collection already tracks payment data for KG orders; needs extension to TP orders

### Revised Navigation Structure

**📦 Orders**
```
┌─ Orders ───────────────────────────────────────────┐
│  QUICK ACTIONS  ← always visible at top             │
│  New Estimate │ New SR │ New Order                  │
│  ENTRY POINTS                                     │
│  ├─ Estimates           ← sales quotes              │
│  └─ Service Requests    ← repairs & support         │
│  STATUS PIPELINE  ← primary navigation              │
│  New → Products → Auth → InProc → Ship'd → Done'   │
│  CHANNELS (filtered views, not separate pages)      │
│  ├─ TP Orders                                       │
│  ├─ In-Store Orders                                 │
│  └─ Eshop Orders                                    │
│  MANAGEMENT                                         │
│  ├─ Create Order                                    │
│  └─ Invoices                                        │
└─────────────────────────────────────────────────────┘
```

**📦 Products & Procurement** *(new combined category)*
```
┌─ Products & Procurement ───────────────────────────┐
│  CATALOG                                            │
│  ├─ Products          ← catalog, presets, peripherals│
│  ├─ Presets                                           │
│  └─ Pre-Builts                                        │
│  INVENTORY                                          │
│  ├─ Inventory         ← stock levels                │
│  ├─ Stock Register                                    │
│  └─ TP Builds                                         │
│  PROCUREMENT                                        │
│  ├─ Purchase Orders     ← buying from vendors       │
│  └─ Indents / Batches   ← internal procurement      │
│  AUDIT                                              │
│  └─ Stock Audit                                       │
└─────────────────────────────────────────────────────┘
```

**📦 Accounts** *(streamlined — POs removed)*
```
┌─ Accounts ─────────────────────────────────────────┐
│  DOCUMENTS                                          │
│  ├─ Invoices            ← inward/outward            │
│  └─ Credit/Debit Notes                              │
│  PAYMENTS                                           │
│  ├─ Payment Vouchers                                │
│  └─ Inward Payments                                 │
│  MASTER DATA                                        │
│  ├─ Vendors                                           │
│  └─ Counters                                          │
│  FINANCIALS                                         │
│  ├─ Financials          ← P&L, Balance Sheet        │
│  ├─ Analytics                                         │
│  └─ ITC GST                                         │
└─────────────────────────────────────────────────────┘
```

**📦 Teams** — Overview, Employees, Attendance, Salaries, Job Apps, Business Groups
**📦 Tenant** — Brands, Entities, Assignments, **Roles** (RBAC), **User Access** (role assignment + direct perms)

**📦 Users** — Users, User Detail, User Orders

### Migration Strategy (8 Phases)

| Phase | What |
|---|---|
| Phase 1 | Payment data integration — backend extends `inwardpayments` to TP orders |
| Phase 2 | Estimate & SR consolidation — unified list/detail views |
| Phase 3 | `ConvertToOrderDialog` component — seamless estimate/SR → order |
| Phase 4 | Navigation restructure — `navigation.jsx` + route redirects |
| Phase 5 | Order consolidation — merge Offline into unified OrdersList/OrderDetail |
| Phase 6 | Products & Procurement reorganization |
| Phase 7 | Legacy cleanup — remove old page files |
| Phase 8 | Backend — migrate orders to PostgreSQL core + detail tables (see orders-migration-plan.md) |

### Shared Components

| Component | Used By | Purpose |
|---|---|---|
| `OrderStatusStepper` | All order pages | Visual progress through fulfillment pipeline |
| `OrderAddressBlock` | TP, Offline, KG orders | Display billing/shipping addresses |
| `OrderProductsTable` | TP, Offline, KG orders | Products line items |
| `OrderBuildsTable` | TP, Offline orders | Custom builds |
| `OrderActionsBar` | All order pages | Status transitions, invoice, checklist |
| `OrderListFilters` | Orders list | Status tabs + channel pills |
| `OrderStatCards` | Overview, list | New/Pending/Authorized counts |
| `OrderPaymentSummary` | Orders list | Payment status badge + amount due |
| `OrderPaymentSection` | Order detail | Payment summary + history + record dialog |
| `RecordPaymentDialog` | Order detail | Modal for recording a new payment |
| `EstimateStatusStepper` | Estimate pages | Draft → Quoted → Accepted/Rejected |
| `SRStatusStepper` | SR pages | Received → Diagnosed → In Repair → Ready → Done |
| `SRWarrantyDecision` | SR detail | Warranty vs paid repair decision UI |
| `ConvertToOrderDialog` | Estimate/SR detail | Convert estimate/SR to order |
| `EntryPointsStatCards` | Overview | Estimates pending, SRs active, Orders in pipeline |

### Metrics

| Metric | Before | After |
|---|---:|---:|
| Order-related page files | 17 | 8 |
| Separate order list views | 3 (TP, Offline, Online) | 1 (filtered) |
| Separate order detail views | 3 (TP, Offline, KG) | 1 (unified) |
| Navigation sections | 5 | 5 (restructured) |
| Estimated code reduction | — | ~40% (order pages) |
| Payment tracking coverage | Offline only | All order types |
| Payment components | 0 | 3 (summary, section, dialog) |
| Entry point pages added | 0 | 4 (EstimatesList, EstimatesDetail, SRList, SRDetail) |
| Conversion flow | None | Estimate → Order, SR → Order |

### Dependencies on Core Phases

This restructure **cannot begin until Phase 4 is complete** because:
1. Legacy routes must be stable before redirects are added
2. Navigation changes affect the entire app shell (sidebar, header)
3. Payment integration (Phase 1 backend) must be verified before frontend payment UI
4. Tenant context (Phase 1) and React Query (Phase 2) must be in place for consistent data fetching
5. All redirects must preserve existing bookmarks and access controls

---

## Immediate Next Actions

**Phases 0–3 are COMPLETE.** Here's what's left:

### P0 — Phase 4: Testing, CI/CD, Production Readiness (156h)

1. **Backend tests** — Auth, access control, tenant scope, webhooks, events
2. **Frontend tests** — Auth/session, tenant selector, critical workflows
3. **CI/CD pipeline** — `.github/workflows/` for linting, type-checking, tests, Docker
4. **Production runbook** — `docs/runbook.md`
5. **Rollback runbook** — `docs/rollback.md`
6. **kurogg-nextjs retirement** — Archive repo, disable deployment pipeline

### P1 — Platform Primitives (Optional, ~50h)

7. **`plat/` directory** — Observability middleware, structured logging, correlation IDs
8. **`plat/tenant/`** — TenantCollection wrapper, TenantConfig model, RLS helpers (consolidates existing `get_collection()` + `UserTenantContext`)
9. **`plat/outbox/`** — OutboxEvent model, `publish_in_txn()`, `mark_processed()`
10. **`core/`** — Domain protocols (`ICafeSessionService`, `IWalletService`, etc.)
11. **`brands/`** — Brand implementations for protocols
12. **Event bus** — `emit()`, `register()`, `on()`

### P2 — Gaming Integration (Phase 3b, ~172h)

13. **Knox removal from kuro-gaming-dj-backend** — Replace Knox with SimpleJWT
14. **Hardcoded S3 keys** — Migrate `S3_BUCK_ACCESS_KEY_ID` and `S3_BUCK_SECRET_ACCESS_KEY` to env vars
15. **`teams/eshop/` app** — Gaming-specific admin features (cart, wishlist, custom builds, gaming orders)
16. **BG-scoped product listing, cart, wishlist** — Multi-tenant gaming integration
17. **Gaming settings merged** — Payment settings, external service URLs into kteam-dj-chief
18. **Gaming MongoDB migration** — 12 collections → `KungOS_Mongo_One` with `bgcode`

### P3 — Post-Core: Cafe Platform (230–345h total, depends on Phase 4)

19. See [[kungos-cafe-platform]] / `CAFE_PLATFORM.md` (unified)
    - `reb_users` stays in MongoDB (lightweight staff lookup)
    - `players` stays in MongoDB (esports data distinct from auth)
    - Unified identity: `CustomUser.phone` is the universal key
    - Shared wallet bridges cafe, esports, retail
    - Walk-in mode (phone lookup, no login) + JWT mode (registered)
    - 30+ new API endpoints, 12 React pages (manager dashboard)
    - Station Desktop Platform: Tauri/Rust monorepo (`station-shell` + `station-service`)
      - See `CAFE_PLATFORM.md` §15 for page-by-page wiring matrix
      - See `CAFE_PLATFORM.md` §16 for Tauri/Rust station platform spec
    - See `CAFE_PLATFORM.md` §17 for gap remediation (Django Channels, station distribution, Cashfree, expired sessions scheduler, QR frontend lib)
    - Depends on Phase 4 completion

---

## Phase 2 Progress Log

### Status: PHASES 0–3 COMPLETE ✅

As of 2026-04-27, **Phases 0, 1, 2, and 3 are fully implemented** in the codebase. The README (`kteam-dj-chief/README.md`) documents the current state. This progress log tracks what was delivered.

### Phase 0 — Security & Observability (Complete)

**Completed 2026-04-23 to 2026-04-27:**

| Item | Status | Details |
|---|---|---|
| Knox removed | ✅ | `django-rest-knox` removed from requirements, INSTALLED_APPS, MIDDLEWARE. No imports remain in active code. |
| SimpleJWT + token blacklisting | ✅ | `rest_framework_simplejwt` + `token_blacklist` in INSTALLED_APPS. `CookieJWTAuthentication` class in `users/cookie_auth.py` (25 lines). |
| Cookie-based auth | ✅ | HttpOnly cookies instead of sessionStorage. `tenant_tokens.py` (205 lines) for tenant-aware token management. |
| Hardcoded secrets removed | ✅ | All secrets via `django-environ`. `.env` file for local dev, `.env.example` for reference. Gaming backend (`kuro-gaming-dj-backend`) still has 2 hardcoded S3 keys — separate repo, deferred. |
| `django-environ` locked | ✅ | All config via environment variables. |
| CORS configured | ✅ | `corsheaders` with configurable origins. |
| DEBUG hardened | ✅ | Traceback leaks eliminated. |
| Throttling | ✅ | anon: 100/min, user: 1000/min, login: 10/min, otp: 5/min, sms: 5/min, register: 10/min. |
| Sentry | 🟡 | Not yet wired. `sentry_sdk` not in requirements. Planned for Phase 4. |
| Correlation IDs | 🟡 | Not yet implemented. `ContextVar`-based request tracing planned for Phase 4. |
| Structured logging | 🟡 | Not yet implemented. JSON log emitter planned for Phase 4. |
| Health endpoints | ✅ | `/health/` and `/ping/` in `backend/views.py` (38 lines). Checks PostgreSQL + MongoDB. |
| API docs | ✅ | `drf-spectacular` with Swagger + Redoc at `/api/v1/docs/swagger/` and `/api/v1/docs/redoc/`. |

**Note:** The `plat/` directory was designed in the plan and is now fully implemented (see Phase 3c and Phase 4 entries below).

### Phase 1 — Tenant Context & Data-Layer Refactor (Complete)

**Completed 2026-04-19 to 2026-04-27:**

| Item | Status | Details |
|---|---|---|
| Pandas removed | ✅ | Zero pandas imports in active code. 8 files cleaned (450+ lines removed): financial.py, kurostaff/views.py, products.py, inward_invoices.py, outward_invoices.py, analytics.py, employees.py, estimates.py, service_requests.py. Only `.bak` files contain pandas. |
| `get_collection()` | ✅ | Centralized MongoDB helper (645 lines in `utils.py`). Accepts `bg_code`, `division`, `branch` params. Automatic tenant filtering. Replaced all `client[bg.db_name]` patterns. |
| `auth_utils.py` | ✅ | 418 lines, 14 centralized permission helpers. `resolve_access()`, `resolve_minimal()`, `get_accessible_entities()`, `check_access()`. Replaces pandas `access_df` patterns. |
| MongoDB division propagation | ✅ | 68,441 docs across 30 collections have `division` field. S3 restore via management commands. |
| MongoDB bgcode field | ✅ | 68,441 docs across 30 collections have `bgcode` field. 100% coverage. |
| MongoDB branch field | ✅ | 68,441 docs across 30 collections have `branch` field. 100% coverage. Propagated from inwardpayments via orderid matching. |
| Compound indexes | ✅ | All 30 collections have `{"bgcode":1,"division":1}` compound indexes. |
| UserTenantContext model | ✅ | PostgreSQL model in `users/models.py` (249 lines). Fields: `bg_code`, `division` (JSON), `branches` (JSON), `scope`. Indexed on `userid+bg_code` and `bg_code+scope`. |
| URL routing | ✅ | All routes under `/api/v1/`. Legacy root paths removed. |
| kuroadmin → teams/ | ✅ | Renamed. `INSTALLED_APPS` updated. All imports updated. URL paths (`/kuroadmin/`) preserved for backward compatibility. |
| kurostaff → teams/kurostaff/ | ✅ | Merged as sub-package. `INSTALLED_APPS` updated. URL path (`/kurostaff/`) preserved. |
| rebellion/ sub-packages | ✅ | `esports/` (14 functions: tournaments, players, teams, gamers), `cafe/legacy_views.py` (17 functions: reborders, rbpackages, reb_users). `rebellion/views.py` now 45 lines (thin import layer). |
| rebellion/cafe/ (Django) | ✅ | 14 PostgreSQL models, 25+ views, WebSocket consumers, 4 seed commands. Separate from legacy MongoDB views. |
| MongoDB DB rename | ✅ | Renamed from `kuropurchase` to `KungOS_Mongo_One`. |
| djongo removed | ✅ | PostgreSQL is the sole relational database. |
| Server-side pagination | ✅ | `PAGE_SIZE: 20` with `PageNumberPagination`. |
| Management commands | ✅ | 9 commands in `kuroadmin/management/commands/`: backup/restore operations, division propagation, full backup restore. |
| `plat/tenant/` directory | ✅ | Created as `plat/tenant/` (renamed from `platform/` to avoid Python built-in collision). `TenantCollection` wrapper (MongoDB), `TenantConfig` model (PostgreSQL), RLS helpers, `verify_tenant_isolation` management command, `seed_tenant_config` command. |
| `plat/tenant/verify.py` | ✅ | Implemented as `plat/tenant/verify.py` — `verify_tenant_isolation` management command. |
| `core/` directory | ✅ | Created with 5 domain protocols: `IFinanceService`, `IOrderService`, `IWalletService`, `IEsportsService`, `ICafeSessionService`, `IIdentityService`. |
| `brands/` directory | ✅ | Created with 3 brand implementations: `rebellion/cafe/`, `rebellion/esports/`, `kurogaming/eshop/`. |

**Note:** The `plat/` sub-package was designed as a formal wrapper. The equivalent functionality (`get_collection()`, `auth_utils.py`, `UserTenantContext`) remains in place as the operational layer; `plat/tenant/` is the formalized abstraction that wraps it.

### Phase 2 — Frontend Modernization (Complete)

**Completed 2026-04-24 to 2026-04-27:**

| Item | Status | Details |
|---|---|---|
| React Query migration | ✅ | **56 of 71 pages** migrated to `useQuery`/`useMutation`. Only `Login.jsx` remains with useEffect (auth page, intentionally excluded). |
| Axios removed | ✅ | All migrated pages use `fetcher()`/`mutator()` from `src/lib/api.jsx`. No `axios` imports in migrated pages. |
| AbortController | ✅ | Requests auto-cancel on unmount. |
| dayjs | ✅ | All `moment` imports replaced. |
| Route splitting | ✅ | 14 heavy pages lazy-loaded with `React.lazy()` + `Suspense`. |
| Tenant selector | ✅ | `TenantContext.jsx` provides single source of truth for tenant state. |
| Access checks | ✅ | All pages use early return with `navigate("/unauthorized", { replace: true })`. |
| URL routing | ✅ | All 71 page/component files updated to use `/api/v1/` paths. |
| Spinner loading | ✅ | Consistent loading states. |

### Phase 3 — Auth, API Compatibility, Operational Core (Complete)

**Completed 2026-04-19 to 2026-04-27:**

| Item | Status | Details |
|---|---|---|
| SimpleJWT auth | ✅ | Login, logout, refresh with token blacklisting. HttpOnly cookies. |
| Knox removed | ✅ | No Knox imports, no Knox middleware, no Knox in INSTALLED_APPS. Gaming backend (`kuro-gaming-dj-backend`) still uses Knox — separate repo, deferred. |
| Auth migration | ✅ | Users migrated to UnifiedUser model. Gaming users reconciled via `reconcile_user_models.py` management command. |
| Cookie-based auth | ✅ | `CookieJWTAuthentication` class. Bearer header fallback. |
| Tenant-aware JWT claims | ✅ | JWT carries `{userid, bg_code, division, branches}`. |
| DRF 3.15 | ✅ | JSON-only renderer. |
| drf-spectacular | ✅ | Swagger + Redoc API docs. |
| Outbox pattern | 🟡 | Not yet implemented. `OutboxEvent` model and `publish_in_txn()` designed but not created. |
| Domain protocols | 🟡 | Not yet implemented. `ICafeSessionService`, `IWalletService`, etc. designed but not created. |
| Event bus | 🟡 | Not yet implemented. `emit()`, `register()`, `on()` designed but not created. |
| `core/` directory | 🟡 | Not yet created. Domain protocols and brand implementations designed but not created. |
| `brands/` directory | 🟡 | Not yet created. |
| Gaming integration | 🟡 | Gaming backend is a separate repo (`kuro-gaming-dj-backend`). Not yet integrated into `kteam-dj-chief`. |

**Note:** Phase 3 core items (auth migration, SimpleJWT, Knox removal, tenant-aware JWT) are complete. The advanced items (outbox, domain protocols, event bus) were designed in the plan but not yet implemented. These are lower-priority than the core auth/tenant work.

### Key Metrics

| Metric | Value |
|---|---:|
| Total Python lines | 20,297 |
| Django apps | 4 top-level (teams, rebellion, users, careers) + sub-packages |
| kuroadmin/ → teams/ | ✅ Renamed. All imports updated. URL paths preserved (backward compat). |
| kurostaff/ → teams/kurostaff/ | ✅ Merged as sub-package. URLs preserved. |
| rebellion/ sub-packages | ✅ esports/ (14 functions), cafe/legacy_views.py (17 functions) split from views.py (871 → 45 lines) |
| Pandas imports in active code | 0 |
| MongoDB documents with bgcode | 68,441 (100%) |
| MongoDB documents with division | 68,441 (100%) |
| MongoDB documents with branch | 68,441 (100%) |
| MongoDB collections | 30 |
| Compound indexes (bgcode+division) | 30/30 |
| React pages migrated | 56/71 (79%) |
| Knox in kteam-dj-chief | 0 (removed) |
| Knox in kuro-gaming-dj-backend | Present (separate repo, deferred) |
| Hardcoded secrets in kteam-dj-chief | 0 (all via django-environ) |
| Hardcoded secrets in kuro-gaming-dj-backend | 2 (S3 keys — deferred) |

### Remaining Work

**Phase 4 — Testing, CI/CD, Production Readiness** (Not Started)
- Backend tests: auth, access control, tenant scope, outbox, webhooks, events
- Frontend tests: auth/session, tenant selector, critical workflows
- CI/CD pipeline: `.github/workflows/` — linting, type-checking, tests, Docker
- Production runbook: `docs/runbook.md`
- Rollback runbook: `docs/rollback.md`
- Post-maintenance runbook: `docs/post-migration.md`
- kurogg-nextjs retirement

**Phase 3b — Gaming Multi-Tenant Integration** (Not Started)
- `kurogaming/` Django app + `eshop/` sub-package
- BG-scoped product listing, cart, wishlist
- Gaming settings merged into kteam-dj-chief
- Knox removal from kuro-gaming-dj-backend
- Hardcoded S3 key remediation in kuro-gaming-dj-backend

**Phase 3c — kungos-admin/ (Sys Admin Tenant Bootstrap)** ✅ Complete (1,051 lines, 15 files)
- Django app: `kungos_admin/` (INSTALLED_APPS + URL routing under `/api/v1/admin/`)
- Models: ✅ `TenantProfile`, `TenantDomainConfig`, `TenantApiKey`, `TenantTemplate` (4 models, 1 migration)
- Service: ✅ `TenantBootstrapService` — `bootstrap()`, `suspend()`, `resume()`, `get_status()`
- Management commands: ✅ `bootstrap_tenant`, `create_tenant_user`, `deploy_tenant`
- API endpoints: ✅ 10 endpoints under `/api/v1/admin/tenant/*`, `/api/v1/admin/templates/*`, `/api/v1/admin/domains/*`, `/api/v1/admin/api-keys/*`
- Permissions: ✅ `KungosAdminPermission` — superuser/staff only
- Serializers: ✅ `BootstrapRequestSerializer`, `SuspendRequestSerializer`, `TenantTemplateSerializer`, `TenantDomainConfigSerializer`, `TenantApiKeySerializer`, `TenantProfileSerializer`
- Migrations: ✅ `0001_initial` — all 4 models created

**Phase 4 — Platform Primitives** ✅ Complete (1,091 lines, 30 files)
- ⚠️ Package renamed to `plat/` (not `platform/`) to avoid collision with Python's built-in `platform` module
- `plat/shared/` — ✅ `encoding.py`, `validation.py`, `helpers.py` (pure utility functions)
- `plat/observability/` — ✅ `context.py` (ContextVar holders), `middleware.py` (CorrelationID + TenantContext), `logging.py` (structured JSON logger)
- `plat/health/` — ✅ `views.py` (`/health/live`, `/health/ready`), `urls.py` (2 endpoints)
- `plat/tenant/` — ✅ `config.py` (`TenantConfig` model — spec Appendix D), `collection.py` (`TenantCollection` — spec Appendix E), `exceptions.py` (`TenantContextMissing`), `rls.py` (RLS helpers), `verify.py` (management command), `management/commands/seed_tenant_config.py`
- `plat/outbox/` — ✅ `models.py` (`OutboxEvent` — spec Appendix F), `service.py` (`publish_in_txn()`, `mark_processed()`, `mark_failed()`), `worker.py` (`process_outbox_batch` Celery task)
- `plat/events/` — ✅ `bus.py` (`emit()`, `register()`, `on()` decorator), `types.py` (event dataclasses + constants — spec Appendix C)
- `core/` — ✅ `finance/protocols.py` (`IFinanceService`), `commerce/protocols.py` (`IOrderService`, `IWalletService`), `esports/protocols.py` (`IEsportsService`), `cafe/protocols.py` (`ICafeSessionService`, `IWalletService`), `identity/protocols.py` (`IIdentityService`)
- `brands/` — ✅ `rebellion/cafe/services.py` (`SessionService`, `WalletService`), `rebellion/esports/services.py` (`EsportsService`), `kurogaming/eshop/services.py` (`EshopService`, `WalletService`)
- Migrations: ✅ `plat.0001_initial` — TenantConfig + OutboxEvent
- Effort: ~60 hours (as estimated)

**Post-Core — Cafe Platform** (230–345 hours total including Station Platform, depends on Phase 4)
- See [[kungos-cafe-platform]] for details

---

### Platform Primitives — Detailed Breakdown

| # | Task | Files | Effort |
|---|---|---|---:|
| 1 | Create `plat/` directory structure | `__init__.py`, `shared/`, `observability/`, `health/`, `tenant/`, `outbox/`, `events/` | 1h |
| 2 | `plat/shared/encoding.py` — base64, hex, url-safe encoders | `encoding.py` | 1h |
| 3 | `plat/shared/validation.py` — phone, email, UUID validators | `validation.py` | 2h |
| 4 | `plat/shared/helpers.py` — camelCase, snake_case, pagination helpers | `helpers.py` | 1h |
| 5 | `plat/observability/context.py` — `ContextVar` for request_id, tenant_ctx | `context.py` | 1h |
| 6 | `plat/observability/middleware.py` — CorrelationID middleware | `middleware.py` | 2h |
| 7 | `plat/observability/logging.py` — structured JSON logger with tenant injection | `logging.py` | 3h |
| 8 | `plat/health/views.py` — `/health/live`, `/health/ready` | `views.py` | 2h |
| 9 | `plat/health/checks.py` — PG, MongoDB, Redis, Celery, MeiliSearch health checks | `checks.py` | 3h |
| 10 | `plat/tenant/config.py` — `TenantConfig` model | `config.py` | 4h |
| 11 | Seed `TenantConfig` for all current BGs and brands | Management command | 2h |
| 12 | `plat/tenant/collection.py` — `TenantCollection` wrapper for MongoDB | `collection.py` | 6h |
| 13 | `plat/tenant/rls.py` — PostgreSQL RLS setup helpers | `rls.py` | 3h |
| 14 | `plat/tenant/verify.py` — `verify_tenant_isolation` management command | `verify.py` | 2h |
| 15 | `plat/outbox/models.py` — `OutboxEvent` model with status transitions | `models.py` | 4h |
| 16 | `plat/outbox/service.py` — `publish_in_txn()`, `mark_processed()`, `mark_failed()` | `service.py` | 4h |
| 17 | `plat/outbox/worker.py` — Celery Beat task to process outbox events | `worker.py` | 3h |
| 18 | `core/protocols.py` — `ICafeSessionService`, `IWalletService`, `IOrderService` | `protocols.py` | 4h |
| 19 | `brands/rebellion/` — Cafe and Esports implementations for domain protocols | `cafe/`, `esports/` | 6h |
| 20 | Event bus — `emit()`, `register()`, `on()` decorator pattern | `events/bus.py` | 3h |
| 21 | Migrate `teams/kurostaff/` pure utilities → `plat/shared/` | 3-4 files | 4h |
| **Total** | | **~21 files** | **~60h** |

---

## Appendix A: Required Files by Phase

### Phase 0 files

| File | Purpose |
|---|---|
| `plat/observability/context.py` | `ContextVar` holders for request_id, tenant_ctx |
| `plat/observability/middleware.py` | CorrelationID middleware |
| `plat/observability/logging.py` | Structured JSON log emitter |
| `plat/health/views.py` | `/health/live`, `/health/ready` |
| `plat/health/checks.py` | PostgreSQL, MongoDB, Redis, Celery, MeiliSearch checks |
| `settings.py` | Sentry DSN wired, DEBUG=False, CORS restricted |

### Phase 1 files

| File | Purpose |
|---|---|
| `plat/tenant/context.py` | `UserTenantContext`, `resolve_tenant_context()` |
| `plat/tenant/config.py` | `TenantConfig` model |
| `plat/tenant/collection.py` | `TenantCollection` wrapper |
| `plat/tenant/rls.py` | PostgreSQL RLS setup helpers |
| `plat/tenant/verify.py` | `verify_tenant_isolation` management command |
| `users/models.py` | `UserTenantContext` fields expanded |
| All MongoDB queries | Replaced direct access with `TenantCollection` |
| All pandas filtering | Replaced with native ORM/query-layer logic |

### Phase 2 files

| File | Purpose |
|---|---|
| `src/lib/queryClient.js` | React Query client config |
| `src/lib/queryKeys.js` | Cache key factory |
| `src/lib/api.jsx` | `fetcher()`/`mutator()` with AbortController |
| `src/lib/dayjs.js` | dayjs utility (tz, relativeTime, utc) |
| `src/contexts/TenantContext.jsx` | Single source of truth for tenant state |
| `src/components/layout/TenantSelector.jsx` | BG → Division → Branch selector |
| `src/lib/safeAccess.js` | Safe access utilities |
| `src/routes/main.jsx` | Route-level code splitting |

### Phase 3 files

| File | Purpose |
|---|---|
| `plat/outbox/models.py` | `OutboxEvent` model |
| `plat/outbox/service.py` | `publish_in_txn()`, `mark_processed()`, `mark_failed()` |
| `plat/outbox/tasks.py` | Celery task `process_outbox_batch` |
| `plat/outbox/admin.py` | Dead-letter view, requeue action |
| `plat/outbox/management/commands/reconcile.py` | Reconciliation command |
| `plat/events/bus.py` | `emit()`, `register()`, `on()` |
| `plat/events/types.py` | Event dataclasses |
| `core/finance/protocols.py` | `IFinanceService` |
| `core/commerce/protocols.py` | `IOrderService`, `IWalletService` |
| `core/esports/protocols.py` | `IEsportsService` |
| `core/cafe/protocols.py` | `ICafeSessionService` |
| `core/identity/protocols.py` | `IIdentityService` |
| `brands/rebellion/cafe/services.py` | `SessionService` implementation |
| `brands/rebellion/esports/services.py` | `EsportsService` implementation |
| `brands/kurogaming/eshop/services.py` | `EshopService` implementation |

### Phase 4 files

| File | Purpose |
|---|---|
| `tests/` | Backend tests: auth, access control, tenant scope, outbox, webhooks, events |
| `src/tests/` | Frontend tests: auth/session, tenant selector, critical workflows |
| `.github/workflows/` | CI pipeline: linting, type-checking, tests, Docker |
| `docs/runbook.md` | Production deployment runbook |
| `docs/rollback.md` | Rollback runbook |
| `docs/post-migration.md` | Post-maintenance runbook |

---

## Appendix B: Logging Schema Reference

Every log entry must include these fields. Structured JSON format:

```json
{
  "ts": "2026-04-27T10:30:00.000Z",
  "level": "INFO",
  "rid": "a1b2c3d4",
  "user_id": "abc-123-def",
  "bg_code": "BG0001",
  "division": "kurogaming",
  "branch": "branch-01",
  "service": "rebellion.cafe.services",
  "action": "session.end",
  "duration_ms": 42,
  "outcome": "success",
  "error_class": null,
  "payload_summary": {
    "session_id": "S001",
    "charge": 500
  }
}
```

---

## Appendix C: Domain Event Types

| Event | Trigger | Handlers |
|---|---|---|
| `wallet.recharged` | Successful wallet recharge | Loyalty points, notifications |
| `session.started` | Cafe session start | Station lock, game load |
| `session.ended` | Cafe session end | Charge calculation, outbox event |
| `order.placed` | Customer places order | Inventory reservation, payment processing |
| `order.fulfillment_changed` | Order status transition | SMS notification, tracking update |
| `tournament.prize_awarded` | Tournament prize awarded | Wallet credit (cafe/esports) |
| `payment.webhook_received` | Cashfree/UPI webhook | Order status update, receipt generation |
| `user.registered` | New user signup | Welcome notification, initial wallet setup |
| `tenant.config_changed` | `TenantConfig` updated | Cache invalidation, feature flag refresh |

---

## Appendix D: TenantConfig Model Reference

```python
class TenantConfig(models.Model):
    bg_code = models.CharField(primary_key=True, max_length=20)
    brand_slug = models.CharField(max_length=50)
    business_type = models.CharField(max_length=50)  # esports, retail, cafe, hybrid
    features = models.JSONField(default=dict)
    payment_cfg = models.JSONField(default=dict)
    sms_cfg = models.JSONField(default=dict)
    wallet_cfg = models.JSONField(default=dict)
    pricing_cfg = models.JSONField(default=dict)
    theme_cfg = models.JSONField(default=dict)
    integration_cfg = models.JSONField(default=dict)
    status = models.CharField(max_length=20, default="active")
```

**Example values:**

```json
{
  "bg_code": "BG0001",
  "brand_slug": "rebellion",
  "business_type": "hybrid",
  "features": {"cafe": true, "esports": true, "eshop": true},
  "payment_cfg": {"provider": "cashfree", "merchant_id": "MERCH_001"},
  "sms_cfg": {"header": "KURO", "template_ids": {"order_confirm": "TMP_001"}},
  "wallet_cfg": {"min_recharge": 100, "max_balance": 10000, "loyalty_rate": 0.01},
  "pricing_cfg": {"tier_144hz": 60, "tier_240hz": 90, "tier_vr": 150, "peak_multiplier": 1.5},
  "theme_cfg": {"primary": "#01696f", "logo_url": "https://cdn.example.com/logo.png"},
  "integration_cfg": {"gmc_enabled": true, "meilisearch_index": "rebellion_products"},
  "status": "active"
}
```

---

## Appendix E: TenantCollection Contract

```python
from platform.tenant.exceptions import TenantContextMissing

class TenantCollection:
    """Wraps MongoDB collection access with mandatory tenant context."""

    def __init__(self, collection_name: str):
        self.collection_name = collection_name

    def find(self, filter: dict = None, **kwargs):
        """Find documents with mandatory tenant context."""
        ctx = get_tenant_context()
        if not ctx:
            raise TenantContextMissing("Tenant context required for this operation")
        base = {"bgcode": ctx.bg_code}
        if ctx.division:
            base["division"] = ctx.division
        if ctx.branches:
            base["branch"] = {"$in": ctx.branches}
        base.update(filter or {})
        return raw_collection(self.collection_name).find(base, **kwargs)

    def find_one(self, filter: dict = None, **kwargs):
        """Find one document with mandatory tenant context."""
        ctx = get_tenant_context()
        if not ctx:
            raise TenantContextMissing("Tenant context required for this operation")
        base = {"bgcode": ctx.bg_code}
        if ctx.division:
            base["division"] = ctx.division
        if ctx.branches:
            base["branch"] = {"$in": ctx.branches}
        base.update(filter or {})
        return raw_collection(self.collection_name).find_one(base, **kwargs)

    def insert_one(self, document: dict, **kwargs):
        """Insert document with mandatory tenant context."""
        ctx = get_tenant_context()
        if not ctx:
            raise TenantContextMissing("Tenant context required for this operation")
        document = dict(document)
        document.setdefault("bgcode", ctx.bg_code)
        if ctx.division:
            document.setdefault("division", ctx.division)
        if ctx.branches:
            document.setdefault("branch", ctx.branches[0])
        return raw_collection(self.collection_name).insert_one(document, **kwargs)

    def update_one(self, filter: dict, update: dict, **kwargs):
        """Update document with mandatory tenant context."""
        ctx = get_tenant_context()
        if not ctx:
            raise TenantContextMissing("Tenant context required for this operation")
        base = {"bgcode": ctx.bg_code}
        if ctx.division:
            base["division"] = ctx.division
        base.update(filter or {})
        return raw_collection(self.collection_name).update_one(base, update, **kwargs)
```

---

## Appendix F: OutboxEvent Model Reference

```python
class OutboxEvent(models.Model):
    event_id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event_type = models.CharField(max_length=100)      # "session.ended"
    aggregate_type = models.CharField(max_length=100)  # "cafe_session"
    aggregate_id = models.CharField(max_length=100)    # "S001"
    bg_code = models.CharField(max_length=20)
    payload = models.JSONField()
    status = models.CharField(max_length=20, default="pending")  # pending|processed|failed
    retry_count = models.IntegerField(default=0)
    available_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True, default="")
```

---

*This document replaces the legacy `kungos.md` as the authoritative KungOS plan. See [[kungos-log]] for approved departures. See [[kungos-cafe-platform]] for cafe platform details. See [[kungos-debug-tools]] for debugging tooling.*